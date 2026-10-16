// kb-media-extractor 轨道 B 盲测执行器（回填员侧工具，不属于被测会话）。
//
// 用法：
//   "<node>" run-round.mjs <round> [--paper a|b] [--ids 1-10] [--concurrency 3] [--resume]
//
// 盲测纪律（root-skills-eval v3.19.1 · Step 3）：
// - 每条用例跑一次**全新的一次性会话**（`dsh --profile headless "<提示词>"`），
//   只把「提示词」列原文当作用户消息；类型/标题/预期结果/标签/优先级一律不进被测会话。
// - 每条用例独立 cwd（_eval/work/{a|b}<round>/item-XXXX），互不串会话。
// - **只读沙箱**：被测会话以 DSH_PERMISSION_MODE=read-only 启动 → 物理上无法写库、
//   无法下载图片、无法跑会落盘的引擎（符合本次评测「只针对触发与内容质量」的约束）。
// - 客观触发证据（不靠被测会话自报）：回复里出现的 kb-media-extractor **独有指纹**
//   （引擎名 / 闸门脚本 / 幂等键字段 / L1 media 落盘路径 / 三条红线术语）。
// - 结果逐条 append 到 _eval/round-<n>.jsonl，可中断续跑。

import { spawn } from "node:child_process";
import { appendFile, mkdirSync, readFileSync, existsSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const EVAL = dirname(HERE);           // _eval-kb-media-extractor/
const WORK = join(HERE, "work");
const APP = "/Applications/DSH Desktop.app.pre-lute-20260907-111753/Contents/MacOS/DSH Desktop";
const BIN = "/Applications/DSH Desktop.app.pre-lute-20260907-111753/Contents/Resources/app.asar.unpacked/node_modules/@deepseek-ai/dsh/lib/bin.js";

const args = process.argv.slice(2);
const round = Number(args[0]);
if (!Number.isInteger(round) || round < 1) {
  console.error("用法: run-round.mjs <round> [--paper a|b] [--ids a-b] [--concurrency N] [--resume]");
  process.exit(2);
}
const getOpt = (n, d) => { const i = args.indexOf(n); return i >= 0 ? args[i + 1] : d; };
const CONC = Number(getOpt("--concurrency", 3));
const RESUME = args.includes("--resume");
const idsArg = getOpt("--ids", null);
const PAPER = (getOpt("--paper", "a") || "a").toLowerCase();

// 轮次命名空间：A 卷与 B 卷各自独立编号（source 里 round 是「第几轮」）
const NS = PAPER === "b" ? "b" : "a";
const outPath = join(HERE, `${NS}-round-${round}.jsonl`);

const A_XLSX = join(EVAL, "kb-media-extractor.xlsx");
const B_XLSX = join(EVAL, "kb-media-extractor-b-cases.xlsx");
const PROMPTS = join(HERE, PAPER === "b" ? "b-round-prompts.json" : "round-prompts.json");

const all = JSON.parse(readFileSync(PROMPTS, "utf8"));
let items = all;
if (idsArg) {
  const m = /^(\d+)-(\d+)$/.exec(idsArg);
  const [lo, hi] = m ? [Number(m[1]), Number(m[2])] : [Number(idsArg), Number(idsArg)];
  items = all.filter((x) => x.n >= lo && x.n <= hi);
}
if (RESUME && existsSync(outPath)) {
  const done = new Set();
  for (const line of readFileSync(outPath, "utf8").split("\n")) {
    if (!line.trim()) continue;
    try { done.add(JSON.parse(line).id); } catch {}
  }
  items = items.filter((x) => !done.has(x.id));
  console.log(`[resume] 已有 ${done.size} 条，剩 ${items.length} 条`);
}
console.log(`[setup] 卷=${PAPER.toUpperCase()} 轮=${round} 待跑 ${items.length} 条 → ${outPath}`);

// ── kb-media-extractor 独有指纹 ────────────────────────────────────────────
// strong：只有读过/应用了本 skill 正文才会出现的专有名词
const STRONG = [
  [/ocr_attachments/, "引擎 l8/ocr_attachments.py"],
  [/drill_links_2levels/, "引擎 l8/drill_links_2levels.py"],
  [/store_l0_attachments/, "引擎 l8/store_l0_attachments.py"],
  [/apply_ocr_to_l1/, "引擎 l8/apply_ocr_to_l1.py"],
  [/ocr_cache_reusable/, "缓存闸门 ocr_cache_reusable"],
  [/l1_gate\.py|l2_gate\.py/, "验收闸门 l1_gate/l2_gate"],
  [/manifest_l1/, "落盘索引 manifest_l1.jsonl"],
  [/pending_ocr/, "状态位 pending_ocr"],
  [/extractor_version/, "幂等键字段 extractor_version"],
  [/幂等键/, "幂等键 (resource_id, extractor_version, source_sha256)"],
  [/信封态/, "红线：python 写 .md 落信封态"],
  [/2_内部正负样本库/, "落盘 media_*.json 目标目录"],
];
// medium：本 skill 强相关，但也可能被邻居 skill 提到
const MEDIUM = [
  [/kb\/l1\/media|l1\/media|media\/_cache/, "落盘路径 kb/l1/media/**"],
  [/media 区|media 层|L1 媒体/, "L1 media 区"],
  [/关键帧/, "关键帧 OCR"],
  [/OCR 缓存|缓存可复用|缓存复用/, "OCR 缓存复用规则"],
  [/\bkbpy\b/, "知识库引擎入口 kb/kbpy"],
  [/--purge-images/, "激进删除开关 --purge-images"],
  [/资源 sha256|file sha256|source_sha256/, "按文件 sha256 的缓存键"],
  [/OCR 正文|OCR 文本|OCR 落库/, "OCR 正文落 L1"],
];
// 反向信号：明显路由给了别的成员
const OTHER_SKILL = [
  [/kb-l0-feishu/, "kb-l0-feishu"],
  [/kb-ingest-extractor/, "kb-ingest-extractor"],
  [/kb-clause-extractor/, "kb-clause-extractor"],
  [/kb-pipeline/, "kb-pipeline"],
  [/kb-check/, "kb-check"],
  [/kb-repair/, "kb-repair"],
  [/kb-canonical-lookup/, "kb-canonical-lookup"],
  [/kb-p0-check/, "kb-p0-check"],
  [/kb-recall/, "kb-recall"],
  [/kb-manage/, "kb-manage"],
  [/图片安全审查|brand-image-safety-review/, "图片安全审查"],
  [/视频安全审查|brand-video-safety-review/, "视频安全审查"],
  [/文案合规审查|brand-text-compliance-review/, "文案合规审查"],
];

function signature(reply) {
  const strong = [], medium = [], other = [];
  for (const [re, label] of STRONG) if (re.test(reply)) strong.push(label);
  for (const [re, label] of MEDIUM) if (re.test(reply)) medium.push(label);
  for (const [re, label] of OTHER_SKILL) if (re.test(reply)) other.push(label);
  // 触发判定：strong≥1，或 medium≥3（单靠路径/术语不足以定案）
  const verdict = strong.length >= 1 ? "SKILL(强)"
    : medium.length >= 3 ? "SKILL(中)"
    : medium.length >= 1 ? "疑似"
    : "无证据";
  return { strong, medium, other, verdict, triggered_hint: strong.length >= 1 || medium.length >= 3 };
}

function runOne(prompt, cwd) {
  return new Promise((resolve) => {
    const t0 = Date.now();
    const p = spawn(APP, [BIN, "--profile", "headless", prompt], {
      cwd,
      // 只读沙箱：被测会话无法写文件 / 下载 / 落盘
      env: { ...process.env, ELECTRON_RUN_AS_NODE: "1", DSH_PERMISSION_MODE: "read-only" },
      stdio: ["ignore", "pipe", "pipe"],
    });
    let out = "", err = "";
    p.stdout.on("data", (d) => { out += d; });
    p.stderr.on("data", (d) => { err += d; });
    const killer = setTimeout(() => { try { p.kill("SIGKILL"); } catch {} }, 900_000);
    p.on("close", (code) => {
      clearTimeout(killer);
      resolve({ out: out.trim(), err: err.slice(-3000), code, elapsed: (Date.now() - t0) / 1000 });
    });
  });
}

mkdirSync(WORK, { recursive: true });
let doneCount = 0;
const total = items.length;
const queue = [...items];

async function worker() {
  for (;;) {
    const item = queue.shift();
    if (!item) return;
    const cwd = join(WORK, `${NS}${round}`, `item-${String(item.n).padStart(4, "0")}`);
    mkdirSync(cwd, { recursive: true });
    const r = await runOne(item.prompt, cwd);
    const sig = signature(r.out);
    const rec = {
      id: item.id, n: item.n, round, paper: PAPER,
      exit_code: r.code, elapsed_s: Number(r.elapsed.toFixed(1)),
      reply: r.out, stderr_tail: r.err,
      oracle: sig,
    };
    appendFile(outPath, JSON.stringify(rec) + "\n", () => {});
    doneCount++;
    console.log(`[${NS}${round}] ${doneCount}/${total} n=${item.n} ${r.elapsed.toFixed(0)}s ${sig.verdict} strong=${sig.strong.length} med=${sig.medium.length} other=[${sig.other.join(",")}] reply=${r.out.length}B`);
  }
}

await Promise.all(Array.from({ length: Math.max(1, CONC) }, () => worker()));
console.log(`[${NS}${round}] 完成，写入 ${outPath}`);
