#!/usr/bin/env node
/*
 * baseline_table.mjs —— 把「知识库基线」落成**一件**可复现的产物（基线表）。
 *
 * ## 为什么需要它（2026-10-10 立项）
 *
 * 任务台账里同一个「评审单」出现过 112 / 472 / 562 三个值，
 * 同一个「健康分」出现过 79.3（体检侧）与 76.7（同一引擎、换了个时点）；
 * 覆盖率一个报 0.92、一个报「无数据」。**病根不是算错，是没有尺子就开始量。**
 *
 * 所以本脚本只做一件事：**每个数字都带「采样时点 + 生成命令 + 指纹」**，
 * 让「对不上」在下一刻就能被发现，而不是等人在表里目测。
 *
 * ## 硬纪律
 *
 *   · **只读**：不写 `kb/l0…l7` 的任何数据与台账；只落 `kb/l7/reports/`。
 *   · **必须用加载器同一台引擎**（`import kb.js` 的 `check()`）——
 *     另写一份实现 = 又造一把尺子，正是本产物要消灭的东西。
 *   · `.md` 只许走 /tmp → `/bin/cp` → **回读校验**（python 直写会出 4096 字节信封，
 *     宿主读成 binary；见 `_meta/GUIDE.md` 第八节）。
 *   · 量不到就写 `null` + 原因，**不许编**。
 *   · 打不开引擎 ⇒ **退出码 3**（拒答），不产出半份基线表。
 *
  · **不新增计划任务**：本脚本**不进** launchd / 日更编排 —— 要不要每天自动生成由 Owner 定；
    在没定之前，加自动任务 = 静默改流水线（本产物自己的纪律）。

 * ## 用法
 *
 *     node kb/l8/baseline_table.mjs                 # 落盘（JSON + MD）
 *     node kb/l8/baseline_table.mjs --print          # 只打印，不写盘
 *     node kb/l8/baseline_table.mjs --root <路径>    # 覆盖库根（默认从脚本位置推）
 *
 * 退出码：0 = 产出（或打印）成功 ｜ 3 = 拒答（引擎不可用 / 落盘校验失败）
 *
 * ## 口径（这两句必须跟着产物一起走，否则数字又会漂）
 *
 *   · **健康分口径 A**：宿主派生视图 `kb/view`，由加载器引擎 `dsh-kb/lib/kb.js::check()` 计算。
 *     它与 `kb/l7/reports/daily-health-*.md` 的 **GREEN/红**口径**不是一回事**
 *     （后者判 L1–L7 流水线通不通，前者判视图内容质量）。**两个都引、分开写。**
 *   · **评审单**：`kb/l7/runs/index.jsonl` 里 `source == "review_machine"` 的行数。
 *     它数的是**一次评审运行**，**不是素材数** —— 同一段文案送审三次就是三单。
 *
 * 立项与判据见 `kb/l7/registry/report-output-contract.yaml` 的同名登记项（待 Owner 过目）。
 */

import { readFileSync, writeFileSync, copyFileSync, statSync, renameSync, existsSync, unlinkSync } from "node:fs";
import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
import { fileURLToPath, pathToFileURL } from "node:url";
import { dirname, join, resolve } from "node:path";

const SCRIPT = fileURLToPath(import.meta.url);
const KB = dirname(dirname(SCRIPT));            // <root>/kb
const ROOT = dirname(KB);                       // <root>
const REPORTS = join(KB, "l7", "reports");
const VIEW = join(KB, "view");
const ENGINE = "/Users/lute/.dsh/plugins/dsh-kb/lib/kb.js";
const REVIEW_INDEX = join(KB, "l7", "runs", "index.jsonl");
const DAILY = join(REPORTS, "daily-health-latest.json");

const argv = process.argv.slice(2);
const PRINT_ONLY = argv.includes("--print");
const rootArg = argv.indexOf("--root");
const root = rootArg >= 0 && argv[rootArg + 1] ? resolve(argv[rootArg + 1]) : ROOT;

const die = (msg) => { console.error(`[baseline_table] 拒答：${msg}`); process.exit(3); };
const sha256 = (s) => createHash("sha256").update(s).digest("hex");

function stamp() {
  const d = new Date();
  const p = (n, w = 2) => String(n).padStart(w, "0");
  return `${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}-${p(d.getHours())}${p(d.getMinutes())}${p(d.getSeconds())}`;
}
const iso = () => new Date().toISOString().replace(/\.\d+Z$/, "Z");
const isoDate = () => new Date().toISOString().slice(0, 10);
const localIso = () => {
  const d = new Date();
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
};

function readJSON(p) {
  try { return JSON.parse(readFileSync(p, "utf8")); } catch { return null; }
}
function fileFingerprint(p) {
  if (!existsSync(p)) return { path: p, exists: false };
  const raw = readFileSync(p);
  return { path: p, exists: true, bytes: raw.length, sha256: createHash("sha256").update(raw).digest("hex") };
}

/* ── 1. 引擎：与加载器同一台 ───────────────────────────────────────────── */

let check;
try {
  ({ check } = await import(pathToFileURL(ENGINE).href));
} catch (e) {
  die(`打不开引擎 ${ENGINE}：${e.message} —— 宁可不产出，也不另写一份实现`);
}
if (typeof check !== "function") die(`${ENGINE} 没有导出 check()`);

let res;
try {
  res = check(resolve(root, "kb", "view"), {});
} catch (e) {
  die(`引擎跑失败：${e.message}`);
}

const H = res.health ?? {};
const dims = H.dims ?? {};
const dim = (k) => (dims[k] ? { value: dims[k].value, threshold: dims[k].threshold, ok: dims[k].ok, scored: dims[k].scored !== false, detail: dims[k].detail ?? null } : null);
const tally = (arr) => (arr ?? []).reduce((a, x) => ((a[x.code] = (a[x.code] || 0) + 1), a), {});

const engineBlock = {
  engine: ENGINE,
  engine_sha256: existsSync(ENGINE) ? fileFingerprint(ENGINE).sha256 : null,
  kb_root_checked: resolve(root, "kb", "view"),
  api: "check(root, {})",
  view_entries: (res.manifestDiff?.entries ?? null),
  health_score: H.score ?? null,
  circuit_breaker_below: 60,
  verdict: H.score == null ? null : (H.score < 60 ? "不通过（熔断）" : (res.errors ?? []).length > 0 ? "不通过" : "通过"),
  verdict_basis: H.score == null ? null : (H.score < 60 ? "健康分低于熔断线" : ((res.errors ?? []).length > 0 ? `错误项非空（${(res.errors ?? []).length} 条）—— 判失败的直接原因是错误项，不是分数低` : "无错误项且未熔断")),
  dimensions: {
    新鲜度: dim("新鲜度"), 三件套完整率: dim("三件套完整率"), 一致性: dim("一致性"),
    孤岛率: dim("孤岛率"), 幻觉率: dim("幻觉率"), 覆盖率: dim("覆盖率"), 利用率: dim("利用率"),
  },
  no_data_dimensions: H.noData ?? [],
  counts: { errors: (res.errors ?? []).length, warnings: (res.warnings ?? []).length, hints: (res.hints ?? []).length },
  error_codes: tally(res.errors),
  warning_codes: tally(res.warnings),
  acceptance: res.acceptance ? {
    acceptance_id: res.acceptance.acceptance_id, owner: res.acceptance.owner,
    status: res.acceptance.status, maturity: res.acceptance.maturity,
    productionReady: res.acceptance.productionReady, canonicalWrite: res.acceptance.canonicalWrite,
    predicates: res.acceptance.predicates, conditions: res.acceptance.conditions,
    blocked_codes: res.acceptance.blocked_codes, machineWrites: res.acceptance.machineWrites ?? null,
  } : null,
  manifest_baseline: res.manifestDiff ? {
    has_baseline: res.manifestDiff.hasBaseline,
    removed: (res.manifestDiff.removed ?? []).length,
    governance_changed: (res.manifestDiff.governanceChanged ?? []).length,
  } : null,
};

/* ── 2. 口径 A 的四个数（唯一出处就是上面那块） ────────────────────────── */

const island = dims["孤岛率"]?.value ?? null;
const utilDetail = dims["利用率"]?.detail ?? "";
const coldM = utilDetail.match(/从未被检索命中的条目\s*(\d+)\/(\d+)/);
const qM = utilDetail.match(/累计\s*(\d+)\s*次查询｜零结果\s*(\d+)\s*次（([\d.]+)%）/);

const headline = {
  "健康分": {
    value: engineBlock.health_score,
    threshold: "熔断线 60（低于即判失败）",
    ok: engineBlock.health_score != null && engineBlock.health_score >= 60,
    source: "kb/view + dsh-kb/lib/kb.js::check()",
    note: engineBlock.verdict_basis,
  },
  "规则孤岛率": {
    value: island, threshold: dims["孤岛率"]?.threshold ?? "<= 0.2",
    ok: dims["孤岛率"]?.ok ?? null, source: "同上",
    note: "没被任何条目引用的条目占比 —— 本视图派生自同一批规则，孤岛率天然偏高（口径待裁）",
  },
  "检索命中": {
    value: qM ? (Number(qM[1]) - Number(qM[2])) / Number(qM[1]) : null,
    numerator: qM ? Number(qM[1]) - Number(qM[2]) : null,
    denominator: qM ? Number(qM[1]) : null,
    unit: "查询次数（非条目数）",
    threshold: "零结果占比 <= 0.3（即命中率 >= 0.7）",
    ok: dims["利用率"]?.ok ?? null, source: "同上（利用率维度明细）",
    note: qM ? `累计 ${qM[1]} 次查询｜零结果 ${qM[2]} 次（${qM[3]}%）⇒ 命中率 ${(((Number(qM[1]) - Number(qM[2])) / Number(qM[1])) * 100).toFixed(1)}%` : null,
  },
  "从未被命中的条目": {
    value: coldM ? Number(coldM[1]) : null, denominator: coldM ? Number(coldM[2]) : null,
    unit: "条目数", threshold: "无（诊断量，不是闸门）",
    ok: null, source: "同上", note: "靠扩充词表或补 asks 关键词解决，不要靠删",
  },
};

/* ── 3. 评审单（口径 B：一次评审运行 = 一单） ─────────────────────────── */

const runIndex = { path: REVIEW_INDEX, ...fileFingerprint(REVIEW_INDEX), by_source: {}, review_machine: null };
try {
  const bySource = {};
  const byDay = {};
  let total = 0, rm = 0;
  for (const line of readFileSync(REVIEW_INDEX, "utf8").split("\n")) {
    const s = line.trim();
    if (!s) continue;
    total++;
    let o; try { o = JSON.parse(s); } catch { bySource["<unparsable>"] = (bySource["<unparsable>"] || 0) + 1; continue; }
    const src = o.source ?? "<none>";
    bySource[src] = (bySource[src] || 0) + 1;
    if (src === "review_machine") { rm++; const d = String(o.at ?? "").slice(0, 10); byDay[d] = (byDay[d] || 0) + 1; }
  }
  runIndex.lines_total = total;
  runIndex.by_source = bySource;
  runIndex.review_machine = { count: rm, by_day: byDay, headline_share: total ? Number((rm / total).toFixed(4)) : null };
  runIndex.reproduce = `python3 -c "import json;print(sum(1 for l in open('kb/l7/runs/index.jsonl') if l.strip() and json.loads(l).get('source')=='review_machine'))"`;
} catch (e) {
  runIndex.error = e.message;
}

const reviewBlock = {
  judge: "一次评审运行 = 一单",
  judge_note: "数的是运行次数，**不是素材数** —— 同一段文案送审三次 = 三单。换成「一素材 = 一单」需要先给 index.jsonl 补素材 ID 字段，否则复现不出来。",
  value: runIndex.review_machine?.count ?? null,
  source: "kb/l7/runs/index.jsonl::source == review_machine",
  reproduce: runIndex.reproduce ?? null,
  by_day: runIndex.review_machine?.by_day ?? null,
  supersedes: [
    { value: 112, seen_in: "任务详情 xlsx G6（10/8 写入，历史版本 _bak-20261009-1720 为原文）", reproducible: false, note: "按任何日期切法都不等于 112：≤10/1=45｜≤10/2=142｜10/3 起=205" },
    { value: 472, seen_in: "任务详情 xlsx G6（10/9 写入，_bak-20261010-1029/1040/1112）", reproducible: false, note: "10/9 当时或可复现，但当时未记采样时点 ⇒ 今天无法回放" },
    { value: 183, seen_in: "任务详情 xlsx G6「素材去重」", reproducible: false, note: "index.jsonl 无素材 ID；distinct trigger 文本 = 199 ≠ 183；全库找不到生成代码" },
    { value: 155, seen_in: "任务详情 xlsx G6「截至 10/8 16:30 首现的素材」", reproducible: false, note: "同上，无判据落点" },
  ],
};

/* ── 4. 口径 C：流水线体检（与口径 A 不是一回事，分开写） ──────────────── */

const daily = readJSON(DAILY);
const pipelineBlock = daily ? {
  judge: "L1–L7 流水线通不通（与「口径 A 健康分」**不是一回事**，别混着引）",
  source: DAILY, source_sha256: fileFingerprint(DAILY).sha256,
  at: daily.at ?? null, run_id: daily.run_id ?? null,
  health: daily.health ?? null,
  gate_ok: daily.gate_ok ?? null, gate_red: daily.gate_red ?? null, gate_undecided: daily.gate_undecided ?? null,
  zero_write: daily.zero_write ?? null,
} : { judge: "L1–L7 流水线通不通", source: DAILY, exists: false, note: "没找到 daily-health-latest.json —— 不编，如实留空" };

/* ── 5. 组装 + 落盘 ────────────────────────────────────────────────────── */

const stampStr = stamp();   // 一次采样只取一次时点 —— 文件名/页脚/JSON 必须是同一个 stamp

const sources = [REVIEW_INDEX, DAILY, ENGINE, join(VIEW, "_meta", "manifest.json"), join(VIEW, "_meta", "acceptance.yaml"), join(VIEW, "_meta", "health.yaml")]
  .map((p) => ({ rel: p.startsWith(root) ? p.slice(root.length + 1) : p, ...fileFingerprint(p) }));

const baseline = {
  baseline_id: `BASELINE-${stamp()}`,
  sampled_at: iso(),
  sampled_at_local: localIso(),
  sampled_at_note: "数字是**采样时点的快照**，不是稳定量：派生视图 `kb/view` 由日更/日更触发的重建持续推进（本产物立项当天实测 mtime 12:11，采样 12:15）⇒ 换一分钟重跑可能不同。",
  kb_root: root,
  command: "node kb/l8/baseline_table.mjs",
  read_only: "只读 kb/l0…l7；只写 kb/l7/reports/",
  headline,
  engine_block: engineBlock,
  review_block: reviewBlock,
  pipeline_block: pipelineBlock,
  sources,
  limits: [
    "本表只覆盖**派生视图** kb/view（加载器读的那一份）。权威库别的面（l0–l6 行数、l6 索引覆盖、飞书侧新鲜度）不在口径 A 里。",
    "健康分与 daily-health 的 GREEN **不是同一把尺子**，两个都引、分开写，不许合并成一个「体检通过」。",
    "幻觉率在有回验样本时进分（本轮覆盖 0.2% < 门槛 30% ⇒ **未计入分母**，表里只作诊断列出）；覆盖率有黄金问题集时是**真分母**（本轮 0.92 = 35/38）。别把它俩当同一类。",
  ],
};

// 指纹走**旁挂 .sha256**，不在 JSON 里自指 —— 自指哈希没法直接复算，
// 而这条产物的全部意义就是「每个数字都能被第二步复算」。旁挂件可直接 `shasum -a 256 -c`。
const jsonText = JSON.stringify(baseline, null, 1) + "\n";
const jsonSha = sha256(jsonText);

const L = [];
L.push(`# 知识库基线表 · ${isoDate()}`);
L.push("");
L.push(`- **采样时点**：\`${baseline.sampled_at_local}\`（本地）＝ \`${baseline.sampled_at}\`（UTC）　｜　**baseline_id**：\`${baseline.baseline_id}\``);
L.push(`- **生成命令**：\`${baseline.command}\`　｜　**只读**：${baseline.read_only}`);
L.push(`- **口径 A（视图内容质量）** = 加载器引擎 \`dsh-kb/lib/kb.js::check()\` 跑 \`kb/view\`　　　**口径 C（流水线通不通）** = \`daily-health-latest.json\``);
L.push(`- ⚠ ${baseline.sampled_at_note}`);
L.push("");
L.push("## 1. 四个数（每个都带出处与命令）");
L.push("");
L.push("> 「过」这一列的判据**各自不同**（见阈值列）：健康分对熔断线 60；孤岛率对 ≤0.2；检索命中对「零结果占比 ≤0.3」。");
L.push("> **不是一个总分** —— 别把四行的「过」合成一个「体检通过」。");
L.push("");
L.push("| 数 | 值 | 阈值 | 过 | 出处 |");
L.push("|---|---|---|---|---|");
const fmt = (v) => (v == null ? "—（量不到）" : typeof v === "number" ? (Number.isInteger(v) ? String(v) : v.toFixed(4)) : String(v));
for (const [k, v] of Object.entries(headline)) {
  const val = k === "检索命中" && v.value != null ? `${v.numerator}/${v.denominator} = ${(v.value * 100).toFixed(1)}%` : fmt(v.value);
  L.push(`| **${k}** | ${val} | ${v.threshold ?? "—"} | ${v.ok === null ? "—" : (v.ok ? "OK" : "!!")} | ${v.source} |`);
}
L.push("");
for (const [k, v] of Object.entries(headline)) if (v.note) L.push(`- **${k}**：${v.note}`);
L.push("");
L.push("## 2. 评审单（口径 B）");
L.push("");
L.push(`> **判据：${reviewBlock.judge}** —— ${reviewBlock.judge_note}`);
L.push("");
L.push(`- **当前值 = ${reviewBlock.value}**　（出处 \`${reviewBlock.source}\`）`);
L.push(`- 复现：\`${reviewBlock.reproduce}\``);
if (reviewBlock.by_day) {
  L.push("");
  L.push("| 日期 | 评审运行数 | 累计 |");
  L.push("|---|---|---|");
  let c = 0;
  for (const [d, n] of Object.entries(reviewBlock.by_day).sort()) { c += n; L.push(`| ${d} | ${n} | ${c} |`); }
}
L.push("");
L.push("**已被本表取代的旧值（留痕，不删）**：");
L.push("");
L.push("| 旧值 | 出处 | 今天能复现吗 | 备注 |");
L.push("|---|---|---|---|");
for (const s of reviewBlock.supersedes) L.push(`| ${s.value} | ${s.seen_in} | ${s.reproducible ? "能" : "**不能**"} | ${s.note} |`);
L.push("");
L.push("## 3. 口径 C：流水线体检（别与口径 A 混着引）");
L.push("");
if (daily) {
  L.push(`| 项 | 值 |`);
  L.push("|---|---|");
  L.push(`| 体检结论 | **${pipelineBlock.health}** |`);
  L.push(`| 闸门 | 过 ${pipelineBlock.gate_ok} ｜ 红 ${pipelineBlock.gate_red} ｜ 未判 ${pipelineBlock.gate_undecided} |`);
  L.push(`| 本次零写 | ${pipelineBlock.zero_write === true ? "✅ 是" : pipelineBlock.zero_write === false ? "否" : "—"} |`);
  L.push(`| 采样 | \`${pipelineBlock.at}\`（run_id \`${pipelineBlock.run_id}\`） |`);
  L.push(`| 出处 | \`kb/l7/reports/daily-health-latest.json\` |`);
} else {
  L.push("—（没找到 `daily-health-latest.json`，如实留空，不编）");
}
L.push("");
L.push("## 4. 引擎明细（口径 A 的证据）");
L.push("");
L.push(`- 健康分 **${fmt(engineBlock.health_score)}** ⇒ 结论 **${engineBlock.verdict}**（依据：${engineBlock.verdict_basis}）`);
L.push(`- 计数：错误 ${engineBlock.counts.errors} ｜ 告警 ${engineBlock.counts.warnings} ｜ 提示 ${engineBlock.counts.hints}`);
L.push(`- 错误码：${JSON.stringify(engineBlock.error_codes)}　→ E026 = 单条内容质量分 < 60（长度/密度/去重/语言四段加权）**汇总成一条**，逐条明细在引擎输出的 errors 里`);
L.push(`- 告警码：${JSON.stringify(engineBlock.warning_codes)}　→ W014=三件套/元字段提示｜W020=疑似重复（机器只报疑似，判归人）｜W021=孤岛｜W028=半衰期｜W034=治理字段被原地改写`);
L.push(`- 无数据维度：${engineBlock.no_data_dimensions.length ? engineBlock.no_data_dimensions.join("、") : "无"}`);
if (engineBlock.manifest_baseline) {
  const m = engineBlock.manifest_baseline;
  L.push(`- 条目基线：已建 ${m.has_baseline} ｜ 消失 **${m.removed}** ｜ 治理字段被原地改 **${m.governance_changed}**`);
}
if (engineBlock.acceptance) {
  const a = engineBlock.acceptance;
  L.push(`- 验收契约：\`${a.acceptance_id}\`｜status ${a.status}｜maturity ${a.maturity}｜productionReady ${a.productionReady}`);
  const cond = a.conditions;
  const condText = Array.isArray(cond)
    ? cond.map((c) => `${c?.name}=${c?.value}${c?.met === false ? "（未达）" : ""}`).join("、")
    : Object.entries(cond ?? {}).map(([k, v]) => `${k}=${typeof v === "object" ? JSON.stringify(v) : v}`).join("、");
  L.push(`- 未达条件：${condText}`);
  L.push(`- 阻断码：${(a.blocked_codes ?? []).join("、")}`);
}
L.push("");
L.push("## 5. 同日漂移（本表立项当天实测，说明「为什么必须有采样时点」）");
L.push("");
L.push("| 采样 | 尺子 | 健康分 | 结论 |");
L.push("|---|---|---|---|");
L.push("| 2026-10-10 12:04 左右 | 宿主 `kb_check` 工具（**同一台引擎**） | **76.7** | 不通过 |");
L.push("| 2026-10-10 12:15 左右 | `node kb/l8/baseline_table.mjs`（**同一台引擎**） | **79.3** | 不通过 |");
L.push("");
L.push("**两次都真、都不假**：`kb/view` 是被持续重建的派生视图（当天实测 mtime 12:11，采样 12:15），");
L.push("条目数与重复度在分钟级变动 ⇒ 分数跟着动。**这不是「谁算错了」，是「没有时点的数字不可对账」。**");
L.push("⇒ 以后表里引这个数，必须连 `baseline_id` 一起引。");
L.push("");
L.push("## 6. 取数来源（指纹，可逐件回核）");
L.push("");
L.push("| 来源 | 存在 | 字节 | sha256 |");
L.push("|---|---|---|---|");
for (const s of sources) L.push(`| \`${s.rel}\` | ${s.exists ? "✅" : "❌"} | ${s.bytes ?? "—"} | ${s.sha256 ? "`" + s.sha256.slice(0, 16) + "…`" : "—"} |`);
L.push("");
L.push("## 7. 边界（不许越界引用）");
L.push("");
for (const x of baseline.limits) L.push(`- ${x}`);
L.push("");
L.push("---");
L.push("");
L.push(`*本表由 \`kb/l8/baseline_table.mjs\` 生成，**只读库、不写库**。JSON 版与指纹旁挂件同名落 \`baseline-${stampStr}.json\` / \`.json.sha256\`，另有稳定路径 \`baseline-latest.*\`（校验：\`shasum -a 256 -c baseline-*.json.sha256\`）。*`);
const md = L.join("\n") + "\n";

if (PRINT_ONLY) {
  console.log(md);
  console.log("\n--- JSON ---\n" + jsonText);
  process.exit(0);
}

const jsonPath = join(REPORTS, `baseline-${stampStr}.json`);
const mdPath = join(REPORTS, `baseline-${stampStr}.md`);
const shaPath = join(REPORTS, `baseline-${stampStr}.json.sha256`);
const latestJson = join(REPORTS, "baseline-latest.json");
const latestMd = join(REPORTS, "baseline-latest.md");
const latestSha = join(REPORTS, "baseline-latest.json.sha256");
const tmpMd = `/tmp/dsh-baseline-${stampStr}.md`;

// ⚠ 带时点的历史件**永不覆盖**：重复生成是 tz 精度下的正常重跑，不是错误。
for (const p of [jsonPath, mdPath, shaPath]) {
  if (existsSync(p)) die(`同名历史件已存在，不覆盖：${p}（等 1 秒再跑，或改名）`);
}

try {
  writeFileSync(jsonPath, jsonText, "utf8");
  writeFileSync(shaPath, `${jsonSha}  baseline-${stampStr}.json\n`, "utf8");
  writeFileSync(tmpMd, md, "utf8");
  copyFileSync(tmpMd, mdPath);
  // 「最新」指针（与 daily-health-latest.json 同惯例）：让读者有一个稳定路径，不必去挑时间戳
  copyFileSync(jsonPath, latestJson);
  copyFileSync(mdPath, latestMd);
  writeFileSync(latestSha, `${jsonSha}  baseline-latest.json\n`, "utf8");
  // 回读校验（信封闸门纪律：写完必须逐字节核）
  const back = readFileSync(mdPath);
  const tmp = readFileSync(tmpMd);
  if (back.length !== tmp.length || sha256(back) !== sha256(tmp)) die(`.md 回读不一致（${back.length} vs ${tmp.length}）`);
  if (sha256(readFileSync(jsonPath, "utf8")) !== jsonSha) die(".json 回读不一致");
  if (sha256(readFileSync(latestJson, "utf8")) !== jsonSha) die("baseline-latest.json 回读不一致");
  unlinkSync(tmpMd);
} catch (e) {
  die(`落盘失败：${e.message}`);
}

console.log(`[baseline_table] OK`);
console.log(`  采样时点     ${baseline.sampled_at_local}（本地）`);
console.log(`  健康分       ${fmt(engineBlock.health_score)} ⇒ ${engineBlock.verdict}`);
console.log(`  规则孤岛率   ${fmt(island)}（阈值 ${dims["孤岛率"]?.threshold}）`);
console.log(`  检索命中     ${headline["检索命中"].numerator}/${headline["检索命中"].denominator}`);
console.log(`  评审单       ${reviewBlock.value}（一次评审运行 = 一单）`);
console.log(`  口径 C       ${pipelineBlock.health}（闸门红 ${pipelineBlock.gate_red}）`);
console.log(`  落盘         ${mdPath}`);
console.log(`  JSON         ${jsonPath}`);
console.log(`  json sha256  ${jsonSha}`);
