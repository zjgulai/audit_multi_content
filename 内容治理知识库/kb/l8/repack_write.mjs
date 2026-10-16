#!/usr/bin/env node
/**
 * L8 · R1 修复：把宿主库（装载位）的 .md 用**加载器同一运行时的明文写通道**重新落盘。
 *
 * 为什么必须由 node 来写（实验依据，见 kb/l8/diagnosis.md 的 E1/E3）：
 *   · python / perl 写 .md → 落盘后 bash 侧 `ls -l`、`stat`、`dd` 以及 **DSH Electron 运行时的
 *     readFileSync** 读到的是 4096 字节信封（首字节 88 7d 1c ?? 3a 05 f6 03）；
 *   · node（两个运行时都测了）/ /bin/cp / bash 内建重定向写 .md → 所有读取者都读到明文。
 *   加载器 `~/.dsh/plugins/dsh-kb/lib/kb.js` 的 `walk()`+`readFileSync` 落在「看懂信封」那一侧，
 *   于是 `splitFrontmatter` 失配 → meta=null → E001 × 509。修复方式就是换写通道。
 *
 * 本脚本不做的事：不改正文（正文逐字来自 kb/l8/repack_payload.json，写完逐文件比对），
 * 不删文件（旧的信封原始字节已由 repack_read.py 存进 kb/l8/_archive/enveloped-<run>/）。
 *
 * 用法：
 *   ELECTRON_RUN_AS_NODE=1 "<DSH>" kb/l8/repack_write.mjs \
 *     --payload kb/l8/repack_payload.json --root ~/.dsh/Momcozy知识库 \
 *     --stage kb/l8/_stage --out kb/l8/repack_write_report.json [--add-class 措辞表达库] [--dry]
 */
import fs from "node:fs";
import path from "node:path";
import os from "node:os";
import crypto from "node:crypto";
import { spawnSync } from "node:child_process";

// ── 参数 ────────────────────────────────────────────────────────
const argv = process.argv.slice(2);
const opt = { dry: false, addClass: null };
for (let i = 0; i < argv.length; i += 1) {
  const a = argv[i];
  if (a === "--dry") { opt.dry = true; continue; }
  const key = a.replace(/^--/, "");
  const val = argv[i + 1];
  if (val === undefined || val.startsWith("--")) { opt[key] = true; continue; }
  opt[key] = val; i += 1;
}
const expand = (p) => (p.startsWith("~") ? path.join(os.homedir(), p.slice(1)) : p);
const ROOT_WS = path.resolve(process.cwd());
const PAYLOAD = path.resolve(ROOT_WS, expand(opt.payload ?? "kb/l8/repack_payload.json"));
const KB_ROOT = path.resolve(expand(opt.root ?? "~/.dsh/Momcozy知识库"));
const STAGE = path.resolve(ROOT_WS, expand(opt.stage ?? "kb/l8/_stage"));
const OUT = path.resolve(ROOT_WS, expand(opt.out ?? "kb/l8/repack_write_report.json"));
const ADD_CLASS = typeof opt["add-class"] === "string" ? opt["add-class"] : null;
const ONLY = typeof opt.only === "string" ? opt.only : null;

// ── 与加载器逐字相同的 frontmatter 正则（kb.js:768 splitFrontmatter）──
//   /^---\r?\n([\s\S]*?)\r?\n---\r?\n?([\s\S]*)$/
const FM_RE = /^---\r?\n([\s\S]*?)\r?\n---\r?\n?([\s\S]*)$/;
const sha256 = (buf) => crypto.createHash("sha256").update(buf).digest("hex");

/** 只加归属字段，不动别的任何一行：插在 `collection:` 之后。 */
function addKbClass(text, value) {
  const m = FM_RE.exec(text);
  if (!m) return { text, added: false, why: "frontmatter 不匹配" };
  const head = text.slice(0, m[0].length - m[2].length); // `---\n…---\n`
  if (/^kb_class:.*$/m.test(m[1])) return { text, added: false, why: "已有 kb_class" };
  const lines = head.split("\n");
  let at = -1;
  for (let i = 0; i < lines.length; i += 1) if (/^collection:/.test(lines[i])) { at = i + 1; break; }
  if (at < 0) return { text, added: false, why: "frontmatter 里没有 collection: 行" };
  lines.splice(at, 0, `kb_class: [${value}]`);
  return { text: lines.join("\n") + m[2], added: true };
}

/** 写后立刻读回断言：字节数 + sha256 + （条目才要求）加载器正则能切出 frontmatter + 正文逐字未变。
 *  注意 `_meta/DERIVED.md`、`GUIDE.md`、`collections.yaml` 这类文件**本来就没有 frontmatter**，
 *  对它们只断言字节与哈希 —— 第一趟把它们判成失败是我这条断言写宽了，不是文件写坏了。 */
function verify(target, wantBuf, wantBody, wantFm) {
  let buf;
  try { buf = fs.readFileSync(target); } catch (e) { return { ok: false, why: `读回失败：${e.message}` }; }
  const txt = buf.toString("utf8");
  const m = FM_RE.exec(txt);
  const r = {
    read_bytes: buf.length, read_sha256: sha256(buf),
    bytes_ok: buf.length === wantBuf.length, sha_ok: sha256(buf) === sha256(wantBuf),
    needs_fm: wantFm, fm_regex_ok: wantFm ? Boolean(m) : null,
    body_ok: wantFm ? Boolean(m) && m[2] === wantBody : null,
    plaintext_head: wantFm ? txt.slice(0, 3) === "---" : null,
  };
  r.ok = r.bytes_ok && r.sha_ok && (!wantFm || (r.fm_regex_ok && r.body_ok));
  if (!r.ok) r.why = `bytes=${r.bytes_ok} sha=${r.sha_ok} fm=${r.fm_regex_ok} body=${r.body_ok}`;
  return r;
}

fs.mkdirSync(STAGE, { recursive: true });
const payload = JSON.parse(fs.readFileSync(PAYLOAD, "utf8"));
const files = payload.files.filter((f) => !ONLY || f.rel.includes(ONLY));

const rows = [];
let nWrite = 0, nCp = 0, nFail = 0, nClassAdded = 0;
for (const f of files) {
  const target = path.join(KB_ROOT, f.rel);
  const isEntry = !f.rel.startsWith("_meta/");
  let text = f.text;
  let classAdded = false;
  if (ADD_CLASS && isEntry) {
    const r = addKbClass(text, ADD_CLASS);
    text = r.text; classAdded = r.added;
    if (r.added) nClassAdded += 1;
  }
  const wantBuf = Buffer.from(text, "utf8");
  const m = FM_RE.exec(text);
  const wantBody = m ? m[2] : null;
  const wantFm = text.startsWith("---\n") || text.startsWith("---\r\n"); // 只有条目要求 frontmatter

  const pre = fs.existsSync(target) ? fs.lstatSync(target).size : -1; // 旧视图（信封）体积
  const row = {
    rel: f.rel, target, logical_bytes: wantBuf.length, pre_write_bytes_via_node: pre,
    logical_sha256: sha256(wantBuf), kb_class_added: classAdded, method: null,
  };

  if (opt.dry) {
    row.method = "dry-run";
    row.readback = verify(target, wantBuf, wantBody, wantFm); // dry：读的是旧内容，必然 fm 失配（就是故障现象）
    rows.push(row); continue;
  }

  fs.mkdirSync(path.dirname(target), { recursive: true });
  fs.writeFileSync(target, wantBuf);              // 明文写通道：node fs.writeFileSync
  let v = verify(target, wantBuf, wantBody, wantFm);
  let method = "node-writeFileSync";

  if (!v.ok) {
    // 兜底：node 写到 .txt（.txt 不被封装）→ /bin/cp（编译型二进制，实测明文）搬到 .md
    const stage = path.join(STAGE, `${sha256(wantBuf).slice(0, 16)}.txt`);
    fs.writeFileSync(stage, wantBuf);
    const sv = fs.readFileSync(stage);
    const stageOk = sv.length === wantBuf.length && sha256(sv) === sha256(wantBuf);
    row.stage_ok = stageOk;
    if (stageOk) {
      const cp = spawnSync("/bin/cp", [stage, target], { encoding: "utf8" });
      row.cp_status = cp.status;
      if (cp.status === 0) { v = verify(target, wantBuf, wantBody, wantFm); method = "cp-fallback"; }
    }
  }
  row.method = method;
  row.readback = v;
  if (v.ok) { if (method === "cp-fallback") nCp += 1; else nWrite += 1; } else nFail += 1;
  rows.push(row);
}

const summary = {
  payload: path.relative(ROOT_WS, PAYLOAD), kb_root: KB_ROOT,
  total: rows.length, node_write_ok: nWrite, cp_fallback_ok: nCp, failed: nFail,
  kb_class_added: nClassAdded, add_class_value: ADD_CLASS, dry: opt.dry,
  runtime: process.version, exec_path: process.execPath,
  bytes_in: rows.reduce((s, r) => s + r.logical_bytes, 0),
  pre_bytes_seen_by_node: rows.reduce((s, r) => s + (r.pre_write_bytes_via_node > 0 ? r.pre_write_bytes_via_node : 0), 0),
  entries_needing_fm: rows.filter((r) => r.readback?.needs_fm).length,
  fm_regex_ok: rows.filter((r) => r.readback?.fm_regex_ok === true).length,
  body_unchanged: rows.filter((r) => r.readback?.body_ok === true).length,
};
const report = {
  run_id: payload.run_id, generated_at: new Date().toISOString(),
  summary, files: rows,
};
fs.writeFileSync(OUT, JSON.stringify(report, null, 1));
console.log(JSON.stringify(summary, null, 1));
if (nFail) { console.error(`✗ ${nFail} 个文件读回断言失败`); process.exit(2); }
