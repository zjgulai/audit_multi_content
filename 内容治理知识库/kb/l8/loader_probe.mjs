#!/usr/bin/env node
/**
 * L8 · 加载器侧探针：**直接 import 加载器本体**（`~/.dsh/plugins/dsh-kb/lib/kb.js`），
 * 在 Electron 运行时里读装载位，把结果压成一小段 JSON 打到 stdout。
 *
 * 为什么不用 `kb_check` 工具：它会把 50 万字符的错误明细全打出来（实测 477 KB），
 * 没法当回归断言用。这里只要**计数**与**得分**。
 *
 * 用法：
 *   ELECTRON_RUN_AS_NODE=1 "<DSH>" kb/l8/loader_probe.mjs <root> <payload.json> [关键词,关键词,…]
 * 输出：一行 JSON（供 roundtrip_check.py 解析）。
 */
import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";

const LIB = path.join(process.env.HOME, ".dsh/plugins/dsh-kb/lib/kb.js");
const { check, collections, library, search } = await import(`file://${LIB}`);

const [root, payloadPath, kwArg] = process.argv.slice(2);
const FM_RE = /^---\r?\n([\s\S]*?)\r?\n---\r?\n?([\s\S]*)$/;
const sha256 = (b) => crypto.createHash("sha256").update(b).digest("hex");
const out = { root, loader: LIB, runtime: process.version };

// ── 体检（不写基线）────────────────────────────────────────────
let res = {};
try { res = check(root, { acceptBaseline: false }) ?? {}; } catch (e) { out.check_error = String(e.message); }
out.check_keys = Object.keys(res);
const hist = (arr) => (arr ?? []).reduce((m, x) => (m[x.code] = (m[x.code] ?? 0) + 1, m), {});
out.errors_total = (res.errors ?? []).length;
out.warnings_total = (res.warnings ?? []).length;
out.code_hist = { ...hist(res.warnings), ...hist(res.errors) };  // 同码合并（E/W 前缀不冲突）
out.health = res.health ?? res.summary?.health ?? null;
out.verdict = res.verdict ?? res.pass ?? res.summary?.verdict ?? null;
// 验收契约的机器判定（谓词/条件/阻断码/负例自检）—— 契约是不是在说真话，看这里
if (res.acceptance) {
  out.acceptance = {
    acceptance_id: res.acceptance.acceptance_id, status: res.acceptance.status,
    maturity: res.acceptance.maturity, productionReady: res.acceptance.productionReady,
    canonicalWrite: res.acceptance.canonicalWrite,
    predicates: res.acceptance.predicates, conditions: res.acceptance.conditions,
    blocked_codes: res.acceptance.blocked_codes, negative_checks: res.acceptance.negative_checks,
    machineWrites: res.acceptance.machineWrites,
  };
}

// ── 子库归属 ──────────────────────────────────────────────────
try {
  const cols = collections(root) ?? [];
  out.collections = cols.map((c) => ({ id: c.id, count: c.count ?? c.entry_count ?? c.entries ?? null, status: c.status ?? null }));
  out.library = library(root)?.name ?? null;
} catch (e) { out.collections_error = String(e.message); }

// ── 条目总数 / frontmatter 解析成功数 ──────────────────────────
const payload = JSON.parse(fs.readFileSync(payloadPath, "utf8"));
const entries = payload.files.filter((f) => f.rel.startsWith("3_措辞表达库/"));
const readback = [];
for (const f of payload.files) {
  const p = path.join(root, f.rel);
  const row = { rel: f.rel, exists: fs.existsSync(p) };
  if (row.exists) {
    const b = fs.readFileSync(p);
    row.bytes = b.length;
    row.sha256 = sha256(b);
    const isEntry = f.rel.startsWith("3_措辞表达库/");
    if (isEntry) {
      const m = FM_RE.exec(b.toString("utf8"));
      row.fm_ok = Boolean(m);
      row.id_ok = Boolean(m) && /^id:\s*\S+/m.test(m[1]);
      row.kb_class_ok = Boolean(m) && /^kb_class:\s*\[措辞表达库\]/m.test(m[1]);
      // 正文/元字段逐字：**两边都归一掉 kb_class 行**再比。
      // 基准可能是生成器产出（自带 kb_class），也可能是本批早期原始载荷（没有这一行）。
      const norm = (t) => t.replace(/^kb_class: \[[^\]]*\]\n/m, "");
      const stripped = m ? norm(b.toString("utf8")) : null;
      row.verbatim_ok = stripped === norm(f.text);
    }
  }
  readback.push(row);
}
out.files_total = readback.length;
out.files_missing = readback.filter((r) => !r.exists).length;
out.entries = entries.length;
out.entries_fm_ok = readback.filter((r) => r.fm_ok === true).length;
out.entries_id_ok = readback.filter((r) => r.id_ok === true).length;
out.entries_kb_class_ok = readback.filter((r) => r.kb_class_ok === true).length;
out.entries_verbatim_ok = readback.filter((r) => r.verbatim_ok === true).length;

// ── 随机 10 个（种子固定，可复现）读回 sha256 比对 ───────────────
const seedStr = payload.run_id ?? "l8";
const seeded = [...entries].sort((a, b) => sha256(Buffer.from(seedStr + a.rel)).localeCompare(sha256(Buffer.from(seedStr + b.rel))));
const pick = [];
for (let i = 0; i < 10 && i < seeded.length; i += 1) pick.push(seeded[Math.floor((i + 0.5) * seeded.length / 10)]);
out.sample10 = pick.map((f) => {
  const r = readback.find((x) => x.rel === f.rel);
  const live = path.join(root, f.rel);
  // 注意：探针只保证「载荷里的相对路径」在这份 root 下存在时才比对。
  // 换 root（例如库根已改成指向权威库的入口）时这些路径本来就不该存在 —— 那不是故障。
  if (!fs.existsSync(live)) {
    return { rel: f.rel, missing_in_this_root: true, sha256_match: null };
  }
  const b = fs.readFileSync(live);
  const norm = (t) => t.replace(/^kb_class: \[[^\]]*\]\n/m, "");   // 两边都归一
  const logical = norm(b.toString("utf8"));
  const want = norm(f.text);
  return {
    rel: f.rel, bytes: b.length,
    sha256_match: sha256(Buffer.from(logical, "utf8")) === sha256(Buffer.from(want, "utf8")),
    expected_sha256: sha256(Buffer.from(f.text, "utf8")).slice(0, 16),
    actual_sha256: sha256(Buffer.from(logical, "utf8")).slice(0, 16),
  };
});
out.sample10_present = out.sample10.filter((x) => !x.missing_in_this_root).length;
out.sample10_all_match = out.sample10_present > 0 && out.sample10.every((x) => x.sha256_match === true);

// ── 关键词检索（log:false，不写查询日志）────────────────────────
// 关键词前加 `!` = 负例：期望 0 命中（「查不到就说查不到」的机器判据）。
const kws = String(kwArg ?? "").split(",").map((s) => s.trim()).filter(Boolean);
out.search = kws.map((raw) => {
  const expectZero = raw.startsWith("!");
  const q = expectZero ? raw.slice(1) : raw;
  try {
    const r = search(root, { query: q, limit: 5, log: false });
    const matched = r.totalMatched ?? 0;
    return { query: q, expect_zero: expectZero, matched, entries: r.totalEntries,
             top1: r.candidates?.[0]?.id ?? null, passed: expectZero ? matched === 0 : matched >= 1 };
  } catch (e) { return { query: q, expect_zero: expectZero, error: String(e.message), passed: false }; }
});
out.search_all_hit = out.search.filter((x) => !x.expect_zero).every((x) => x.passed === true);
out.search_negative_ok = out.search.filter((x) => x.expect_zero).every((x) => x.passed === true);

console.log(JSON.stringify(out));
