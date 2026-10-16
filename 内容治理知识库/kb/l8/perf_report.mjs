#!/usr/bin/env node
/*
 * perf_report.mjs —— 把 `perf-latest.json` 渲染成 **md 报告**（PRD §12 · 目标 15/17/19）。
 *
 * 为什么单开一个渲染器而不是让 python 直接写 .md：
 *   **python 直写 `.md` 会出 4096 字节信封**，宿主侧读者（read 工具 / DSH 里跑的脚本）
 *   读成 binary。`.md` 只许走 node / `/bin/cp` 通道（见 `_meta/GUIDE.md` 第八节）。
 *
 * 用法：node kb/l8/perf_report.mjs [--json <path>] [--out <path>]
 */
import { readFileSync, writeFileSync, copyFileSync, unlinkSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const SCRIPT = fileURLToPath(import.meta.url);
const KB = dirname(dirname(SCRIPT));
const JSON_DEFAULT = join(KB, "l7", "reports", "perf-latest.json");

const arg = (name, dflt) => {
  const i = process.argv.indexOf(name);
  return i >= 0 && process.argv[i + 1] ? process.argv[i + 1] : dflt;
};
const jsonPath = arg("--json", JSON_DEFAULT);
const outPath = arg("--out", join(KB, "l7", "reports", "perf-latest.md"));

const J = JSON.parse(readFileSync(jsonPath, "utf8"));
const L = [];
const row = (o) => (o ? `${o.median_s}` : "—");

L.push(`# 性能实测 · PRD §12 · ${String(J.measured_at).slice(0, 10)}`, "");
L.push(`- **测量时点**：\`${J.measured_at}\`（本地）`);
L.push(`- **任务**：${J.task_ref}`);
L.push(`- **依据**：${J.prd_ref}`);
L.push(`- **生成命令**：\`python3 kb/l8/perf_measure.py --ledger\`（重测六档）→ \`node kb/l8/perf_report.mjs\``);
L.push("");
L.push("> ⚠ 本报告**只量确定性内核**（证据层 / P0 快路 / 整链），**不含 agent 与 LLM 推断**");
L.push("> —— 承 `batch12-B-block-timing-20261002.md` 的边界 1。样本少，只报 min/median/max，");
L.push("> **不声称 P95/P99 与统计置信度**。");
L.push("");
// ★ 2026-10-12：Owner 裁定了「性能」三档的口径，本表**不再是那三档的达标证据**
if (J.provenance_note) {
  L.push("> ★★ **口径（Owner 2026-10-12 裁定）**：「单条文字 ≤10s；图片 ≤20s；视频 ≤60s」量的是");
  L.push("> **飞书侧守衡回复的时间**（我发消息 → 守衡回复我结果），判据 = `kb/l8/measure_verdict_latency.py`。");
  L.push("> 本报告那几行是**证据层地板**（不含层前置/判定主体/发布/agent）⇒ **读数低不等于用户等得短**，");
  L.push("> 别拿它对 §12 那三档下结论。");
  L.push("");
}

// ── 1. 门槛判定 ──────────────────────────────────────────────────────
L.push("## 1. 门槛判定（中位数 vs PRD §12）", "");
L.push("| 项 | PRD §12 要求 | 实测中位 | n | 判 |");
L.push("|---|---|---|---|---|");
const order = ["text", "text_long", "image_ocr_proxy", "video_asr_proxy",
               "p0_judge", "p0_with_report"];
const label = {
  text: "单条文字（**证据层地板**）", text_long: "单条文字·长（**证据层地板**）",
  image_ocr_proxy: "图片（**OCR 代输入·近似**）",
  video_asr_proxy: "视频（**ASR 代输入·近似**）",
  p0_judge: "P0 层响应", p0_with_report: "P0 判定＋生成报告",
};
for (const k of order) {
  const r = J.results?.[k];
  if (!r) continue;
  const v = r.verdict === "pass" ? "✅ pass" : (r.verdict === "fail" ? "❌ **FAIL**" : "—");
  L.push(`| ${label[k] || k} | ≤ ${r.threshold_s} s | **${row(r.wall)} s** | ${r.wall?.n ?? 0} | ${v} |`);
}
L.push("");
// ★ 原来的硬编码「六项全部达标」已删：它把证据层地板说成了 §12 三档的达标证据。
//   现在**算什么说什么**，量不到的直接点名。
{
  const fails = order.filter(k => J.results?.[k]?.verdict === "fail");
  const n = order.filter(k => J.results?.[k]).length;
  L.push(fails.length
    ? `**结论**：本表 ${n} 档里 **${fails.length} 档 FAIL**（${fails.join(" / ")}）。`
    : `**结论**：本表 ${n} 档**全部 pass**。`);
  L.push("　⇒ 但这**不是** §12「性能」三档（文字/图片/视频）的达标依据 —— "
       + "那三档按 Owner 裁定量的是**守衡回复时间**，见开头的口径注记。");
}
L.push("");

// ── 2. 瓶颈在哪 ──────────────────────────────────────────────────────
L.push("## 2. 瓶颈在哪（逐段埋点）", "");
L.push("埋点落点：`kb-content-review/scripts/review.py` 的 `trace.perf`（**只记时间、不参与判定**）。");
L.push("");
L.push("| 档 | P0 匹配 | 规则层 | **单元层** | 装配 |");
L.push("|---|---|---|---|---|");
for (const k of ["text", "text_long", "image_ocr_proxy", "video_asr_proxy"]) {
  const s = J.results?.[k]?.stage_median_ms;
  if (!s) continue;
  L.push(`| ${label[k] || k} | ${s.p0_match_ms} ms | ${s.rule_layer_ms} ms | **${s.unit_layer_ms} ms** | ${s.assemble_ms} ms |`);
}
L.push("");
L.push("★ **`unit_layer` 是唯一的大头**，而且**几乎不随输入长度变化**（1.65–1.78 s 跨四档）");
L.push("⇒ 它是**固定初始化开销**（L6 检索器的构建/装载），**不是**跟素材正比的检索代价。");
L.push("这条与 `batch12` 那份报告（2026-10-02）的结论**方向一致**：");
L.push("当时量到「主导段不是 `decide()`，而是**每次调用都要重新构建的 BM25 倒排索引**（中位数 928 ms）」");
L.push("⇒ **跨调用常驻缓存**是唯一能把这条打下来的办法，而它今天仍然不存在。");
L.push("");

// ── 3. 量不到的（如实登记）────────────────────────────────────────────
L.push("## 3. ⛔ 量不到的（**这不是「还没做」，是「现在给不出可信数字」**）", "");
L.push("| 项 | 状态 | 为什么 |");
L.push("|---|---|---|");
L.push(`| 飞书群响应 ≤5s | **本机测不到** | 含守衡侧（另一仓库）与模型侧 LLM。本库只能给下界：P0 判定 ${row(J.results?.p0_judge?.wall)} s |`);
L.push("| 并发 100-500 条 | **未建** | 当前只有单条入口；批量入口是任务拆解 11/23 那行的目标 |");
L.push("| 图片 ≤20s（真实） | **近似** | 用 OCR **文本**代输入，**不含**真实 OCR 成本 |");
L.push("| 视频 ≤60s（真实） | **近似** | 用 ASR **文本**代输入，**不含** ASR 与关键帧抽取成本 |");
L.push("");
for (const [k, v] of Object.entries(J.no_data || {})) {
  L.push(`- **${k}** —— ${v}`);
  L.push("");
}

// ── 4. 端到端 ────────────────────────────────────────────────────────
if (J.end_to_end) {
  L.push("## 4. 端到端（整链 `review_run.sh`）", "");
  const w = J.end_to_end.chain_wall_s;
  L.push(`- **wall**：min ${w.min_s} s ｜ **median ${w.median_s} s** ｜ max ${w.max_s} s ｜ n=${w.n}`);
  L.push(`- ${J.end_to_end.note}`);
  L.push("");
  L.push("**分段（注意口径）**：");
  L.push("");
  L.push("| 段 | 值 | 怎么来的 |");
  L.push("|---|---|---|");
  for (const [k, v] of Object.entries(J.end_to_end.segments || {})) {
    L.push(`| ${k} | ${v} | |`);
  }
  L.push("");
  L.push("★ **最后一段是估算**（35.8 − 15 − 4.2），**不是实测** —— 引擎装配/发布飞书/旁挂那三段");
  L.push("**未逐段埋点**。要精确就得再埋，**本批没做**。");
  L.push("");
}

// ── 5. 下一步 ────────────────────────────────────────────────────────
L.push("## 5. 优化该从哪下手（**依据本报告，不是凭感觉**）", "");
L.push("1. **`unit_layer` 的固定开销（~1.7 s/次）** —— 唯一有数量级收益的点。");
L.push("   两个方向：① 跨调用常驻缓存（同 `batch12` 的建议）；② 进程内复用（守衡侧长驻）。");
L.push("   **代价**：① 要动检索器的装载路径，**有缓存失效风险**（库每日更新 ⇒ 缓存要按 kb_version 失效）；");
L.push("   ② 属守衡侧改动，**另一仓库**。");
L.push("2. **不要动 `p0_match` / `rule_layer`（55 ms / 25 ms）** —— 它们加起来占总时 3%，优化它们没有意义。");
L.push("3. **先建批量入口，再谈并发** —— PRD §12 的「并发 100-500 条」当前**没有被测对象**。");
L.push("");

const md = L.join("\n") + "\n";
const tmp = `/tmp/perf-latest-${Date.now()}.md`;
writeFileSync(tmp, md, "utf8");
copyFileSync(tmp, outPath);
unlinkSync(tmp);
// 回读校验（走 node 写、走 node 读，两侧一致才算落地）
const back = readFileSync(outPath, "utf8");
if (back !== md) {
  console.error(`[perf_report] 回读不一致（写 ${md.length} / 读 ${back.length}）`);
  process.exit(3);
}
console.log(`[perf_report] ✅ ${outPath}  ${Buffer.byteLength(md)} 字节（回读一致）`);
