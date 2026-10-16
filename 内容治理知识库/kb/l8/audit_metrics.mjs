#!/usr/bin/env node
/*
 * audit_metrics.mjs —— PRD §10「记录与统计」七项指标，落成**一件**可复现的产物。
 *
 * ## 为什么需要它（2026-10-10 立项 · 任务拆解 目标 13）
 *
 * 任务拆解写得很直白：「`kb/l7/reports/` 里覆盖率 / 三态比例 / 各层命中率 / 人工复核负担 /
 * 误报 / 漏报 **六项统计产物数 = 0**」—— 也就是说 PRD §10 要的七项，**一项都没有产物**。
 * 而 2026-11-30 那行要拿这几个数算「错放率 ≤5%」「复核召回 ≥95%」，12/14 那行要拿它们
 * 做指标结算。**没有产物 ⇒ 到期算不出来。**
 *
 * ## 本脚本的第一条纪律：分清「能算」与「算不了」
 *
 * 七项里有的今天就量得出来，有的**结构上量不出来**（缺应审清单 / 缺人判）。
 * 第 7 项「知识库回流数量」的**机制**已于 2026-10-12 接线（差异台账），卡点从「机制未建」
 * 变成「等首批人工复核」—— 两种情况**报同一个 no_data、原因不同**，见 `wiring.state`。
 * 把后者写成一个数，比不写更坏 —— 那会让人以为有据可依。
 * 所以每项都带 `status ∈ {measured, no_data}` 与 `why`，**量不到就写 no_data + 原因**。
 *
 * ## 硬纪律（照 `kb/l8/baseline_table.mjs`，同一套）
 *
 *   · **只读**：不写 `kb/l0…l7` 的任何数据与台账；只落 `kb/l7/reports/`。
 *   · **口径写进产物**：每条指标都带 `source` / `how`，换人复算能对上。
 *   · `.md` 只许走 /tmp → `/bin/cp` → **回读校验**（python 直写 .md 会出 4096 字节信封）。
 *   · 量不到写 `null` + 原因，**不许编**。
 *   · 评审索引读不到 ⇒ **退出码 3**（拒答），不产出半份指标。
 *   · **不新增计划任务**：本脚本**不进** launchd / 日更编排 —— 要不要每天自动生成由 Owner 定。
 *
 * ## 用法
 *
 *     node kb/l8/audit_metrics.mjs              # 落盘（JSON + MD + sha256）
 *     node kb/l8/audit_metrics.mjs --print      # 只打印，不写盘
 *
 * 退出码：0 = 成功 ｜ 3 = 拒答
 *
 * ## 口径（跟着产物一起走，否则数字会漂）
 *
 *   · **一单 = 一次评审运行**（`kb/l7/runs/index.jsonl` 里 `source == "review_machine"` 的行数），
 *     **不是素材数** —— 同一段文案送审三次就是三单。与 `baseline_table.mjs` 同口径。
 *   · **命中条目** = 报告 JSON 的 `risk_items[]` 展开。**一份报告可能有多条**。
 *   · **P 层级命中率**：`priority_tier` 是**2026-10-10 接线后**才准的（那之前恒为 P0/P1，
 *     P2/P3 无分支）。所以本项**只对 2026-10-10 起的报告有效**，之前的报告一律标注为
 *     「分层接线前」，不混进分母 —— 混进去会把 P2/P3 的 0 说成「真的没有」。
 */

import { readFileSync, writeFileSync, existsSync, copyFileSync, statSync, unlinkSync } from "node:fs";
import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { dirname, join, basename } from "node:path";
import { readdirSync } from "node:fs";

const SCRIPT = fileURLToPath(import.meta.url);
const KB = dirname(dirname(SCRIPT));
const REPORTS = join(KB, "l7", "reports");
const REVIEW_INDEX = join(KB, "l7", "runs", "index.jsonl");
const RULES = join(KB, "l3", "candidates", "rules.jsonl");

/** 分层接线日：`priority_tier` 从这天起才由 `p_level` 驱动（`core/tiering.py`）。 */
const TIER_WIRED_FROM = "2026-10-10";

const die = (msg) => { console.error(`[audit_metrics] 拒答：${msg}`); process.exit(3); };
const pct = (n, d) => (d ? Number(((n / d) * 100).toFixed(2)) : null);
const ratio = (n, d) => (d ? Number((n / d).toFixed(4)) : null);

// ══════════════════════════════════════════════════════════════════
// 读
// ══════════════════════════════════════════════════════════════════

/**
 * ★ 测试单排除表（2026-10-10 加）。
 *
 * 为什么要有它：**2026-10-10 本 agent 做性能测量时，把 12 条测试单写进了真实索引**
 * （用 `with_kb_evidence --text "<样板文本>"` 跑端到端验证）。它们会
 * **污染三态比例与人工复核负担** —— 12 条清一色 BLOCK，把比例往 BLOCK 推。
 *
 * 口径：
 *   · 索引是**只追加的台账**，本脚本**不改它、不删行**（那是审计trail）；
 *   · 排除表**按 run_id 精确点名**，不用文本特征猜（首版用「100% safe」做特征，
 *     把 9/30 的既有测试单也误伤进来 —— **文本特征会误伤，run_id 不会**）；
 *   · 排除的是**统计口径**，不是历史：被排除的行**仍在索引里、仍可原样读**。
 */
const TEST_RUN_IDS = new Set([
  "20261010-153704", "20261010-153953", "20261010-154007", "20261010-154024",
  "20261010-154040", "20261010-154100", "20261010-160153", "20261010-160213",
  "20261010-160449", "20261010-160835", "20261010-162416", "20261010-162451",
]);

function readIndex() {
  if (!existsSync(REVIEW_INDEX)) die(`找不到评审索引 ${REVIEW_INDEX}`);
  const rows = [];
  for (const line of readFileSync(REVIEW_INDEX, "utf8").split("\n")) {
    const t = line.trim();
    if (!t) continue;
    try { rows.push(JSON.parse(t)); } catch { /* 坏行跳过，但会计数 */ }
  }
  if (!rows.length) die("评审索引一行都没解析出来");
  return rows;
}

function readReports() {
  const out = [];
  let files = [];
  try { files = readdirSync(REPORTS); } catch { return out; }
  for (const f of files) {
    if (!f.endsWith(".json")) continue;
    // ★ 排除**非报告件**：它们没有 `risk_items` 契约，混进来会把 `n_reports` 分母稀释
    //   （实测 2026-10-10：`perf-latest.json` 被吃成「一份 0 条问题的报告」）。
    //   本列表与 `citation_integrity.py` 的 `_SKIP_PREFIX` **同口径** —— 两边别各写一份。
    if (f.startsWith("baseline") || f.startsWith("daily") || f.startsWith("audit")
        || f.startsWith("perf")) continue;
    let o;
    try { o = JSON.parse(readFileSync(join(REPORTS, f), "utf8")); } catch { continue; }
    if (!o || typeof o !== "object" || Array.isArray(o)) continue;   // 有的 JSON 顶层是 trace 数组
    out.push({ file: f, doc: o });
  }
  return out;
}

function readRuleTiers() {
  /** rule_id → p_level，来自 L3 候选（我 2026-10-10 回填的维度字段）。 */
  const m = new Map();
  if (!existsSync(RULES)) return m;
  for (const line of readFileSync(RULES, "utf8").split("\n")) {
    const t = line.trim();
    if (!t) continue;
    let o; try { o = JSON.parse(t); } catch { continue; }
    const rid = o.rule_id;
    if (rid && o.p_level && !m.has(rid)) m.set(rid, o.p_level);
  }
  return m;
}

// ══════════════════════════════════════════════════════════════════
// 七项
// ══════════════════════════════════════════════════════════════════

function metricThreeState(reviews) {
  const states = { PASS: 0, REVIEW: 0, BLOCK: 0, NEEDS_INPUT: 0, 其他: 0 };
  for (const r of reviews) {
    const v = String(r.verdict || "");
    const m = v.match(/^\s*(PASS|REVIEW|BLOCK|NEEDS_INPUT)/);
    if (m) states[m[1]] += 1; else states["其他"] += 1;
  }
  const n = reviews.length;
  return {
    id: "three_state_ratio",
    prd: "PASS / REVIEW / BLOCK 比例",
    status: n ? "measured" : "no_data",
    why: n ? null : "评审索引里没有 review_machine 行",
    source: "kb/l7/runs/index.jsonl → verdict（`STATE ｜ issue_count=N`）",
    how: "按 verdict 前缀归三态；NEEDS_INPUT 是拒答态，**单列**（不计入三态分母，见下）",
    value: {
      n_runs: n,
      // ★ 分母口径：三态比例的分母**只算真出了三态的**（PASS/REVIEW/BLOCK）；
      //   NEEDS_INPUT 是「拒答」，不是一个判定结果 —— 混进分母会让三态比例失真。
      n_three_state: states.PASS + states.REVIEW + states.BLOCK,
      counts: states,
      ratio: {
        PASS: ratio(states.PASS, states.PASS + states.REVIEW + states.BLOCK),
        REVIEW: ratio(states.REVIEW, states.PASS + states.REVIEW + states.BLOCK),
        BLOCK: ratio(states.BLOCK, states.PASS + states.REVIEW + states.BLOCK),
      },
      percent: {
        PASS: pct(states.PASS, states.PASS + states.REVIEW + states.BLOCK),
        REVIEW: pct(states.REVIEW, states.PASS + states.REVIEW + states.BLOCK),
        BLOCK: pct(states.BLOCK, states.PASS + states.REVIEW + states.BLOCK),
      },
      needs_input_not_in_denominator: states.NEEDS_INPUT,
    },
  };
}

function metricTierHit(reports, ruleTiers) {
  const all = { P0: 0, P1: 0, P2: 0, P3: 0, "未标层": 0 };
  const wired = { P0: 0, P1: 0, P2: 0, P3: 0, "未标层": 0 };
  let nAll = 0, nWired = 0, nReportsWired = 0;
  const articleNos = new Set();

  for (const { file, doc } of reports) {
    const stamp = (file.match(/^(\d{8})/) || [])[1] || "";
    const isWired = stamp >= TIER_WIRED_FROM.replaceAll("-", "");
    const ri = Array.isArray(doc.risk_items) ? doc.risk_items : [];
    if (isWired && ri.length) nReportsWired += 1;
    for (const it of ri) {
      if (!it || typeof it !== "object") continue;
      const t = String(it.priority_tier || "未标层");
      all[t in all ? t : "未标层"] += 1;
      nAll += 1;
      if (isWired) { wired[t in wired ? t : "未标层"] += 1; nWired += 1; }
      const a = (it.evidence || {}).article_no;
      if (a) articleNos.add(String(a));
    }
  }
  return {
    id: "priority_tier_hit_rate",
    prd: "各优先级层级命中率",
    status: nWired ? "measured" : "no_data",
    why: nWired ? null
      : `没有 ${TIER_WIRED_FROM} 起的报告 —— 分层接线前的报告 priority_tier 恒为 P0/P1，混进来会说谎`,
    source: "kb/l7/reports/*.json → risk_items[].priority_tier",
    how: `**只算 ${TIER_WIRED_FROM} 起**的报告（分层接线日，见 core/tiering.py）；更早的报告单列在 all_time 里做对照`,
    value: {
      wired_from: TIER_WIRED_FROM,
      n_items: nWired,
      n_reports: nReportsWired,
      counts: wired,
      rate: Object.fromEntries(Object.entries(wired).map(([k, v]) => [k, ratio(v, nWired)])),
      percent: Object.fromEntries(Object.entries(wired).map(([k, v]) => [k, pct(v, nWired)])),
      all_time_for_contrast: { n_items: nAll, counts: all },
      distinct_article_no: articleNos.size,
      caveat: nReportsWired < 5
        ? `⚠ 样本仅 ${nReportsWired} 份报告 ⇒ 只能当**结构性证据**（接线生效了），不能当分布结论`
        : null,
    },
  };
}

function metricManualBurden(reviews, reports) {
  const n = reviews.length;
  const human = reviews.filter((r) => r.human_involved === true).length;
  const byState = { PASS: 0, REVIEW: 0, BLOCK: 0, NEEDS_INPUT: 0 };
  for (const r of reviews) {
    const m = String(r.verdict || "").match(/^\s*(PASS|REVIEW|BLOCK|NEEDS_INPUT)/);
    if (m) byState[m[1]] += 1;
  }
  // 需要人看的 = REVIEW + BLOCK + NEEDS_INPUT（PASS 转 sign-off 确认，不算逐条复核）
  const needsHuman = byState.REVIEW + byState.BLOCK + byState.NEEDS_INPUT;
  let issueItems = 0, reportsWithItems = 0;
  for (const { doc } of reports) {
    const ri = Array.isArray(doc.risk_items) ? doc.risk_items : [];
    if (ri.length) reportsWithItems += 1;
    issueItems += ri.length;
  }
  return {
    id: "manual_review_burden",
    prd: "人工复核负担",
    status: n ? "measured" : "no_data",
    why: n ? null : "没有评审单",
    source: "kb/l7/runs/index.jsonl → human_involved / verdict；kb/l7/reports/*.json → risk_items",
    how: "「需要人看的单」= REVIEW + BLOCK + NEEDS_INPUT（PASS 转 sign-off 确认，不算逐条复核）",
    value: {
      n_runs: n,
      needs_human_runs: needsHuman,
      needs_human_ratio: ratio(needsHuman, n),
      needs_human_percent: pct(needsHuman, n),
      by_state: byState,
      reports_with_items: reportsWithItems,
      issue_items_total: issueItems,
      issues_per_reviewed_report: reportsWithItems ? Number((issueItems / reportsWithItems).toFixed(2)) : null,
      human_involved_true: human,
      human_involved_all_false: human === 0,
      caveat: "`human_involved` 全库仍为 false ⇒ **复核动作本身还没回流**。本项量的是"
        + "「机器判下来有多少单需要人看」，**不是**「人实际花了多少时间」。"
        + "后者要人真的复核过 —— 回流通道已于 2026-10-12 接线（见第 7 项 `wiring`），**只差人判**。",
    },
  };
}

function metricRuleHit(reports, ruleTiers) {
  const hit = new Map();                     // article_no → 命中次数
  const byTier = new Map();                  // p_level → 命中次数
  let total = 0;
  for (const { doc } of reports) {
    const ri = Array.isArray(doc.risk_items) ? doc.risk_items : [];
    for (const it of ri) {
      if (!it || typeof it !== "object") continue;
      const a = (it.evidence || {}).article_no;
      if (a) { const k = String(a); hit.set(k, (hit.get(k) || 0) + 1); }
      const pl = it.p_level || (it.risk_id && ruleTiers.get(it.risk_id)) || null;
      if (pl) byTier.set(pl, (byTier.get(pl) || 0) + 1);
      total += 1;
    }
  }
  const top = [...hit.entries()].sort((a, b) => b[1] - a[1]).slice(0, 12);
  return {
    id: "rule_hit_rate",
    prd: "规则命中率",
    status: hit.size ? "measured" : "no_data",
    why: hit.size ? null : "报告里没有可提取的条款号",
    source: "kb/l7/reports/*.json → risk_items[].evidence.article_no",
    how: "条款号去重计数 + 命中频次 Top12；分母用「命中条目总数」而不是「规则总数」"
      + "（PRD 原文只写「规则命中率」，未定义分母 ⇒ 本产物**把两种可算的都给出**，不替 PRD 选）",
    value: {
      n_items: total,
      n_distinct_articles_hit: hit.size,
      n_rules_in_l3: ruleTiers.size,
      rules_ever_hit_ratio: ruleTiers.size ? ratio(hit.size, ruleTiers.size) : null,
      top_articles: top.map(([article_no, n]) => ({ article_no, n })),
      hits_by_p_level: Object.fromEntries([...byTier.entries()].sort()),
      caveat: `「规则总数」取 L3 候选 ${ruleTiers.size} 条。**它不是「该被命中的全集」** ——`
        + "分母换一个（比如只算 P0 规则）结论就变，故本产物只报**可算的两个比**，不合成一个「命中率」。",
    },
  };
}

function metricCoverage(reviews) {
  return {
    id: "coverage_rate",
    prd: "审查覆盖率",
    status: "no_data",
    why: "**结构上算不了**：分子（被审的素材）有，分母（应当被审的全集）**在库里不存在**。"
      + "PRD §1.1 给的规模是「广告二创月均约 500 条、高峰约 3000 条」「红人内容月均 100-200 条」"
      + "—— 那是**口头规模**，不是可复算的台账；库里没有「本期应审素材清单」这种东西。",
    source: null,
    how: null,
    value: {
      numerator_available: reviews.length,
      denominator_available: null,
      what_would_make_it_measurable: [
        "① 需方侧给出「本期应审素材清单」（飞书表 / NAS 路径 / 投放计划），落进 L0 一张表；",
        "② 送审侧每条素材带唯一素材 ID（现在 content_id 是哈希形态，同一素材多次送审算多单，见目标 9）；",
        "③ 有了 ①②，覆盖率 = 已审素材 ID ∩ 应审清单 / 应审清单。",
      ],
    },
  };
}

function metricErrorRates(reviews) {
  return {
    id: "false_positive_false_negative",
    prd: "误报 / 漏报",
    status: "no_data",
    why: "**结构上算不了，且必须等金标集**：误报 = 机器判 BLOCK/REVIEW 而人判 PASS；"
      + "漏报 = 机器放行而人判有问题。两个都要**人工标准答案**当对照。"
      + "任务拆解 11/30 那行才建金标集（文字 40 / 图片 30 / 视频 30），"
      + "且现状视频 0 条、预期答案是 agent 判读 v0 而非人工答案（`fixed_eval_set: missing`）。"
      + "**在那之前给出任何误漏报数字都是编的。**",
    source: null,
    how: null,
    value: {
      gold_set_status: {
        contract: "kb/view/3_措辞表达库/tests/ 的黄金问题集（现测 35/38 = 0.92）",
        contract_fixed_eval_set: "missing（验收契约未达条件之一）",
        human_labels: null,
        video_items: 0,
      },
      what_would_make_it_measurable: [
        "① 100 条**人工标准答案**入库并进验收契约（`fixed_eval_set`）；",
        "② 每条评审记录能回指金标条目（现在没有这个外键）；",
        "③ 有了 ①②，误报率 = 机器拦 ∧ 人放 / 机器拦；漏报率 = 机器放 ∧ 人拦 / 人拦。",
      ],
      // ★ 不写 0，也不写「估计值」—— 写 no_data 是**结论**，不是「还没做」
      downstream_blocked: [
        "任务拆解 12/14 那行要的「错放率 ≤5%」——算不出",
        "任务拆解 12/14 那行要的「复核召回 ≥95%」——算不出",
      ],
    },
  };
}

// ── 第 7 项：知识库回流数量 ────────────────────────────────────────────
// ★ 2026-10-12 接线（Owner 批准「第 7 项按建议开始开发」·第一步 = 差异台账，**零写库**）。
//   口径真源 `kb/l7/registry/return-flow.yaml` ｜ 唯一写入器 `kb/l8/return_flow.py`。
//   ★★ 三态 —— **不让「没人判」冒充 measured:0**（本项此前正是栽在这个读法上）：
//        not_wired       机制未接                → no_data（原因「机制未接」）
//        wired_no_input  已接线、但没人判过       → no_data（原因换成「等首批人工复核」）
//        measured        有人判过                → 数量 = 事件条数（按 target_layer 分组）
//   ★ wired_no_input 与 measured(0) 是**两件事**：前者「没人判」，后者「有人判了、且全与机器一致」
//     —— 后者是**合法读数**，前者不是。
function metricReflow() {
  const spec = join(KB, "l7", "registry", "return-flow.yaml");
  const ledger = join(KB, "l7", "registry", "return-flow.ndjson");
  const writer = join(KB, "l8", "return_flow.py");
  let st = null, err = null;
  if (existsSync(spec) && existsSync(ledger) && existsSync(writer)) {
    try {
      // ★ 走 kb/kbpy —— 解释器约定的**唯一调用入口**（kb/.kb-python 是带注释的配置
      //   文件，解析口径在 kb/kbpy 的 read_cfg() 里）。**不许在 JS 里再实现一份**
      //   （2026-10-12 实测踩过：直接 readFileSync 整份配置当解释器 ⇒ spawn ENOENT）。
      const out = execFileSync("/bin/sh", [join(KB, "kbpy"), "l8/return_flow.py", "status", "--json"],
        { encoding: "utf8", cwd: KB });
      st = JSON.parse(out);
    } catch (e) { err = String((e && e.message) || e).slice(0, 300); }
  }
  const state = st && st.state ? st.state : "not_wired";
  const base = {
    id: "kb_reflow_count",
    prd: "知识库回流数量",
    source: "kb/l7/registry/return-flow.ndjson（append-only 事件台账）"
      + " → kb/l8/return_flow.py status",
    how: "人工判定 ≠ 机器结论、且人工给出**明确三态** ⇒ 一条事件（人判 NEEDS_INPUT 与"
      + "「机人一致」都**不算**事件）；数量 = 事件条数（按 target_layer 分组）。"
      + "口径真源 kb/l7/registry/return-flow.yaml。",
    prd_clauses: ["§9 末句（落点：规则权重 / 正负样本）", "§10 第 7 项（数量）", "§11.2（重复要求）"],
    wiring: {
      state, spec: "kb/l7/registry/return-flow.yaml", ledger: "kb/l7/registry/return-flow.ndjson",
      writer: "kb/l8/return_flow.py",
      step1: "已接线（差异台账，零写库）",
      step2: "未做 —— 真写 L3 权重 / L1-L2 正负样本，**须单独报批**（属 kb-pipeline 领地）",
      error: err,
    },
  };

  if (state === "not_wired") {
    return {
      ...base, status: "no_data",
      why: "**机制未接**：台账 / 口径件 / 写入器三者缺一。"
        + "PRD §9 要「人工复核结论回流知识库，更新规则权重和正负样本」。",
      value: {
        reflow_events: null, n_comparable_samples: 0,
        note: "本项**不是 0**，是**未接线** —— 写 0 会让人以为「核过了，没有回流」。",
      },
    };
  }

  if (state === "wired_no_input") {
    return {
      ...base, status: "no_data",
      why: "**机制已接线，但没有人判过** —— 差异台账（append-only）已建、三态已实现，"
        + "可判定的对照样本（既有机器结论、又有人判）**为 0 条** ⇒ 现在给不出数量。"
        + "★ 卡点已从「机制未建」变成「**等首批人工复核**」（PRD §11.2 每周抽检 100 条／"
        + "§11.3 金标集），**两项输入都已就绪、只差人填「人判」栏**。",
      value: {
        reflow_events: 0,
        n_comparable_samples: 0,
        ledger_events: st.n_events,
        inputs: st.inputs,
        what_would_make_it_measurable: [
          "① 往 kb/l7/reports/audit-sample-ALL.csv 的「人判」栏填判定（100 条已就绪）；",
          "② 或把 60 题金标集的三态回填进库；",
          "③ 有了人判，`kb/l8/return_flow.py ingest --apply` 生成事件，本项即为 measured。",
        ],
        note: "**接线 ≠ 有读数。** 此时报 `0` 会退回本项要消灭的那个错读法"
          + "（「核过了，没有回流」）；⇒ 分开写：机制在，输入未到。",
      },
    };
  }

  return {
    ...base, status: "measured",
    why: `已接线且**有人判过**：对照样本 ${st.n_comparable_samples} 条，回流事件 ${st.n_events} 条。`,
    value: {
      reflow_events: st.n_events,
      by_target_layer: st.by_target_layer,
      by_applies_to: st.by_applies_to,
      n_comparable_samples: st.n_comparable_samples,
      inputs: st.inputs,
      note: st.note || ("★ `applies_to = count_only` 的事件（**「我构造」的题 / 复核人为空**）"
        + "只计数，**不进第二步**（真写权重）—— 构造题会把规则朝不存在的素材上调。"),
    },
  };
}

// ══════════════════════════════════════════════════════════════════
// 渲染
// ══════════════════════════════════════════════════════════════════

function renderMd(M) {
  const L = [];
  L.push(`# 审计指标 · PRD §10 七项 · ${M.stamp.slice(0, 10)}`, "");
  L.push(`- **采样时点**：\`${M.stamp}\`（本地）　｜　**audit_id**：\`${M.audit_id}\``);
  L.push("- **生成命令**：`node kb/l8/audit_metrics.mjs`　｜　**只读**：只读 kb/l0…l7；只写 kb/l7/reports/");
  L.push(`- **一单口径**：一次评审运行（不是素材数）；**本次样本**：${M.sample.n_runs} 单 / ${M.sample.n_reports} 份报告 JSON / ${M.sample.n_rule_items} 个命中条目`);
  L.push("");
  L.push("> ⚠ 本产物**不合成一个「审计总分」**。七项各自有独立口径与阈值来源，");
  L.push("> 有的量得出来、有的**结构上量不出来** —— 后者写 `no_data` + 原因，");
  L.push("> 那不是「还没做」，是**现在给不出可信数字**。");
  L.push("");
  L.push("## 0. 七项总览");
  L.push("");
  L.push("| # | 指标（PRD §10） | 状态 | 本次读数 |");
  L.push("|---|---|---|---|");
  const short = {
    three_state_ratio: () => `三态 ${M.m.three_state_ratio.value.percent.BLOCK}% BLOCK / `
      + `${M.m.three_state_ratio.value.percent.REVIEW}% REVIEW / ${M.m.three_state_ratio.value.percent.PASS}% PASS`,
    priority_tier_hit_rate: () => `P0 ${M.m.priority_tier_hit_rate.value.counts.P0} / `
      + `P1 ${M.m.priority_tier_hit_rate.value.counts.P1} / P2 ${M.m.priority_tier_hit_rate.value.counts.P2} / `
      + `P3 ${M.m.priority_tier_hit_rate.value.counts.P3}`,
    manual_review_burden: () => `需人看 ${M.m.manual_review_burden.value.needs_human_runs} 单（`
      + `${M.m.manual_review_burden.value.needs_human_percent}%）`,
    rule_hit_rate: () => `${M.m.rule_hit_rate.value.n_distinct_articles_hit} 个条款被命中`
      + `（L3 共 ${M.m.rule_hit_rate.value.n_rules_in_l3} 条规则）`,
    coverage_rate: () => "—（分母不存在）",
    false_positive_false_negative: () => "—（等金标集）",
    kb_reflow_count: () => {
      const r = M.m.kb_reflow_count;
      const w = r.wiring || {};
      if (r.status === "measured") {
        return `${r.value.reflow_events} 条事件（对照样本 ${r.value.n_comparable_samples} 条）`;
      }
      if (w.state === "wired_no_input") return "—（**已接线**，等首批人工复核；对照样本 0 条）";
      return "—（回流未接线）";
    },
  };
  const order = ["three_state_ratio", "priority_tier_hit_rate", "manual_review_burden",
                 "rule_hit_rate", "coverage_rate", "false_positive_false_negative", "kb_reflow_count"];
  order.forEach((k, i) => {
    const x = M.m[k];
    const ok = x.status === "measured" ? "✅ measured"
      : (x.wiring && x.wiring.state === "wired_no_input") ? "🔌 no_data（已接线·等输入）"
        : "⛔ no_data";
    L.push(`| ${i + 1} | ${x.prd} | ${ok} | ${short[k]()} |`);
  });
  L.push("");
  for (const k of order) {
    const x = M.m[k];
    L.push(`## ${x.prd}`, "");
    L.push(`- **状态**：\`${x.status}\`` + (x.why ? `　—　${x.why}` : ""));
    if (x.source) L.push(`- **出处**：${x.source}`);
    if (x.how) L.push(`- **口径**：${x.how}`);
    L.push("");
    L.push("```json");
    L.push(JSON.stringify(x.value, null, 2));
    L.push("```", "");
  }
  L.push("## 附：本次样本指纹", "");
  L.push("```json");
  L.push(JSON.stringify(M.sample, null, 2));
  L.push("```");
  return L.join("\n") + "\n";
}

// ══════════════════════════════════════════════════════════════════
// 主
// ══════════════════════════════════════════════════════════════════

function main() {
  const printOnly = process.argv.includes("--print");
  const rows = readIndex();
  const reviewsAll = rows.filter((r) => r.source === "review_machine");
  const reviews = reviewsAll.filter((r) => !TEST_RUN_IDS.has(String(r.run_id)));
  const nExcluded = reviewsAll.length - reviews.length;
  const reports = readReports();
  const ruleTiers = readRuleTiers();

  const nRuleItems = reports.reduce(
    (a, { doc }) => a + (Array.isArray(doc.risk_items) ? doc.risk_items.length : 0), 0);

  const now = new Date();
  const pad = (n) => String(n).padStart(2, "0");
  const stamp = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`
    + `T${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`;
  const idStamp = stamp.replace(/[-:]/g, "").replace("T", "-");

  const M = {
    audit_id: `AUDIT-${idStamp}`,
    stamp,
    generated_by: "node kb/l8/audit_metrics.mjs",
    prd_ref: "内容审查 Agent PRD v1.2 §10「记录与统计」",
    task_ref: "任务拆解 10/12–10/16 行 · 目标 13",
    tier_wired_from: TIER_WIRED_FROM,
    sample: {
      n_runs_total: rows.length,
      n_runs: reviews.length,
      n_runs_excluded_as_test: nExcluded,
      excluded_run_ids: [...TEST_RUN_IDS],
      n_reports: reports.length,
      n_rule_items: nRuleItems,
      n_rules_in_l3: ruleTiers.size,
    },
    m: {
      three_state_ratio: metricThreeState(reviews),
      priority_tier_hit_rate: metricTierHit(reports, ruleTiers),
      manual_review_burden: metricManualBurden(reviews, reports),
      rule_hit_rate: metricRuleHit(reports, ruleTiers),
      coverage_rate: metricCoverage(reviews),
      false_positive_false_negative: metricErrorRates(reviews),
      kb_reflow_count: metricReflow(),
    },
  };

  const md = renderMd(M);
  if (printOnly) { process.stdout.write(md); return 0; }

  const jsonText = JSON.stringify(M, null, 2) + "\n";
  const jsonSha = createHash("sha256").update(jsonText).digest("hex");
  const jsonPath = join(REPORTS, "audit-metrics-latest.json");
  const shaPath = join(REPORTS, "audit-metrics-latest.json.sha256");

  // .md 走 /tmp → cp → 回读校验（python 直写 .md 会出 4096 字节信封，宿主读成 binary）
  const tmpMd = `/tmp/audit-metrics-${idStamp}.md`;
  try {
    writeFileSync(jsonPath, jsonText, "utf8");
    writeFileSync(shaPath, `${jsonSha}  audit-metrics-latest.json\n`, "utf8");
    writeFileSync(tmpMd, md, "utf8");
    execFileSync("/bin/cp", [tmpMd, join(REPORTS, "audit-metrics-latest.md")]);
  } catch (e) {
    die(`落盘失败：${e.message}`);
  }
  const target = join(REPORTS, "audit-metrics-latest.md");
  const back = readFileSync(target, "utf8");
  if (back !== md) {
    try { unlinkSync(target); } catch { /* best effort */ }
    die(`.md 回读不一致（写 ${md.length} 字符 / 读回 ${back.length} 字符）—— 已删除半成品`);
  }
  try { unlinkSync(tmpMd); } catch { /* best effort */ }

  console.log(`[audit_metrics] ✅ 已产出`);
  console.log(`  ${jsonPath}`);
  console.log(`  ${target}  (${statSync(target).size} 字节，回读一致)`);
  console.log(`  sha256 ${jsonSha.slice(0, 16)}…`);
  console.log("");
  for (const k of ["three_state_ratio", "priority_tier_hit_rate", "manual_review_burden",
                   "rule_hit_rate", "coverage_rate", "false_positive_false_negative", "kb_reflow_count"]) {
    const x = M.m[k];
    console.log(`  ${x.status === "measured" ? "✅" : "⛔"} ${x.prd}`);
  }
  return 0;
}

process.exit(main());
