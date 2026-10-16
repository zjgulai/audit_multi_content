#!/usr/bin/env node
// 只读：把 .work/recall-map-all.json + .work/l4-sleep-clauses.jsonl 拼成一份交付报告。
// 写盘走 node fs.writeFileSync（装载位写纪律：不用 python/perl/sed/cp 落 .md）。
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const ROOT = path.resolve(__dirname, "..");
const MAP = path.join(ROOT, ".work", "recall-map-all.json");
const L4 = path.join(ROOT, ".work", "l4-sleep-clauses.jsonl");
const OUT = path.join(ROOT, "l6召回-婴幼儿睡眠安全-条款号与原文-20260930.md");

const clamp = (s, n) => {
  if (s === null || s === undefined) return "";
  const t = String(s).replace(/\s+/g, " ").trim();
  return t.length <= n ? t : t.slice(0, n) + `…（截断，原 ${t.length} 字）`;
};

const rep = JSON.parse(fs.readFileSync(MAP, "utf8"));
const l4rows = fs.readFileSync(L4, "utf8").split("\n").filter(Boolean).map((l) => JSON.parse(l));
const l4ByArticle = new Map();
for (const r of l4rows) {
  if (!l4ByArticle.has(r.article_no)) l4ByArticle.set(r.article_no, r);
}

// 去重后的召回候选：unit_id -> {hits, queries, articles, kb_type, anchor, sha, excerpt, l2, l4}
const units = new Map();
const perQuery = [];
for (const rec of rep.recalls) {
  perQuery.push({ query: rec.query, mode: rec.mode, lists: (rec.lists_used || []).join("+"), n: rec.rows.length });
  for (const r of rec.rows) {
    let u = units.get(r.unit_id);
    if (!u) {
      u = {
        unit_id: r.unit_id, kb_type: r.kb_type, anchor: r.anchor, sha: r.source_sha256,
        table: r.table, lang: r.lang, excerpt: r.excerpt, l2: r.l2, l4: r.l4 || [],
        hits: 0, queries: [], bestRank: 999, maxScore: 0,
      };
      units.set(r.unit_id, u);
    }
    u.hits += 1;
    if (!u.queries.includes(rec.query)) u.queries.push(rec.query);
    if (r.rank < u.bestRank) u.bestRank = r.rank;
    if ((r.score || 0) > u.maxScore) u.maxScore = r.score;
    if ((!u.l4 || !u.l4.length) && r.l4 && r.l4.length) u.l4 = r.l4;
    if (!u.l2 && r.l2) u.l2 = r.l2;
  }
}

const withArticle = [...units.values()].filter((u) => u.l4 && u.l4.length);
const withoutArticle = [...units.values()].filter((u) => !u.l4 || !u.l4.length);
const recallArticles = new Set();
for (const u of withArticle) for (const a of u.l4) recallArticles.add(a.article_no);

const byForm = (f) => l4rows.filter((r) => r.form === f).map((r) => r.article_no).sort();
const wordingArts = byForm("revision_pair");
const sampleArts = l4rows.filter((r) => r.form === "sample_case").map((r) => r.article_no).sort();
const scopedArts = byForm("scoped_clause");

const L = [];
L.push("# L6 召回 · 婴幼儿睡眠安全 —— 候选单元、条款号与原文");
L.push("");
L.push("> 本文件由只读召回 + 只读回填生成，**不写库、不改索引**。生成时间：2026-09-30 16:15（本会话）。");
L.push("> 生成脚本：`kb/.work/recall_to_article.py`（召回回落 L2/L4）+ `.work/report_recall_sleep.mjs`（本文件）。");
L.push("> 原始产物：`.work/l6-*.json`（召回）、`.work/recall-map-all.json`（回填）、`.work/l4-sleep-clauses.jsonl`（L4 睡眠条款全量）。");
L.push("");
L.push("## 0. 先说清口径（三条，别跳过）");
L.push("");
L.push("1. **L6 召回没有\"命中\"，只有\"候选\"**。`kb/l6/registry/l6.json` 明写「无命中阈值：检索器一律返回 Top-N」，");
L.push("   且 RRF 分只是名次的倒数（Top1 恒 ≈ 1/(60+1)），**分数不能当阈值用**。下面一律称候选。");
L.push("2. **L6 本身不产出条款号**。召回结果只带 `unit_id + anchor + source_sha256 + 文本片段`；");
L.push("   条款号（`article_no`）是 L4 canonical 的属性。本文件的条款号是**把召回到的 `unit_id` 回填到 `kb/l4/canonical/*.jsonl`**");
L.push("   （按 `unit_id` / `unit_ids` / `evidence_units[].unit_id` 匹配）得到的，回填链路写在每条的「回填依据」里。");
L.push("3. **范围不是全量**。索引覆盖 `kb/l6/SCOPE.txt` 白名单内的 4,206 条可用单元（源 `kb/l2/units.jsonl` 经 L3 口径过滤），");
L.push("   范围外的单元召不到；本库 `kb/l4/canonical/` 是**机器晋升**（判据 C1–C8 全过）、**人工抽查未做**，不能声称已过正式验收。");
L.push("");
L.push("## 1. 本次跑了几条召回");
L.push("");
L.push("| # | 检索词 | 模式 | 命中列表 | 返回条数 |");
L.push("|---|---|---|---|---|");
perQuery.forEach((q, i) => L.push(`| ${i + 1} | \`${q.query}\` | \`${q.mode}\` | \`${q.lists}\` | ${q.n} |`));
L.push("");
L.push(`五条检索合计返回 ${perQuery.reduce((a, b) => a + b.n, 0)} 行，去重后 **${units.size} 个候选单元**，`);
L.push(`其中 **${withArticle.length} 个单元在 L4 canonical 里有条款号**，其余 ${withoutArticle.length} 个只有 L2 正文、无条款号。`);
L.push("");
L.push("命令（复现用，cwd = `~/.dsh/Momcozy知识库`）：");
L.push("");
L.push("```bash");
L.push('kb/kbpy l6/retriever.py --query "婴幼儿睡眠安全" --top 10 --json');
L.push('kb/kbpy l6/retriever.py --query "婴幼儿睡眠安全" --top 10 --mode bm25_only --json');
L.push('kb/kbpy l6/retriever.py --query "infant safe sleep SIDS" --top 10 --json');
L.push('kb/kbpy l6/retriever.py --query "安全睡眠 仰卧 婴儿猝死综合征 同床睡眠" --top 10 --json');
L.push('kb/kbpy l6/retriever.py --query "婴儿床 床围 枕头 睡眠环境 窒息风险" --top 10 --json');
L.push("```");
L.push("");
L.push("---");
L.push("");
L.push("## 2. 召回到的候选里，**有条款号的**（条款号 + 原文）");
L.push("");
L.push(`共 ${withArticle.length} 个单元，对应 ${recallArticles.size} 个条款号（清单：${[...recallArticles].sort().join("、")}）。`);
L.push(`**但先别高兴**：这 ${recallArticles.size} 个条款号里，只有 \`W-2.36\`／\`W-2.122\`／\`W-2.72\` 是真正的「规则/改法」，`);
L.push("其余要么是**资料登记元数据**（`E-1.*`），要么是**顺带命中**（`W-1.22` 全部词是安全/绝对化用语，与睡眠无关；");
L.push("`W-2.73` 是「口径/标准不一致」整类汇总，内容主体是染发/束腹带）。真正的睡眠安全规则大多**没被这次召回带出来**，见第 4 节。");
L.push("");
for (const u of withArticle) {
  for (const a of u.l4) {
    const full = l4ByArticle.get(a.article_no);
    L.push(`### ${a.article_no}　form=\`${a.form}\`　status=\`${a.status}\`　kb_type=\`${a.kb_type}\``);
    L.push("");
    L.push(`- 召回单元：\`${u.unit_id}\`（best rank ${u.bestRank}，命中 ${u.hits} 次：${u.queries.map((q) => `\`${q}\``).join("、")}）`);
    L.push(`- L2 锚点：\`${u.anchor}\`｜source_sha256：\`${u.sha}\``);
    if (full && full.p_level) L.push(`- p_level：\`${full.p_level}\`｜risk_level：\`${full.risk_level}\``);
    if (full && full.rule_code) L.push(`- rule_code：\`${full.rule_code}\``);
    L.push("- 回填依据：L4 该条的 `unit_id`/`unit_ids`/`evidence_units` 含上述 `unit_id`");
    L.push("");
    L.push("**条款原文（逐字）**：");
    L.push("");
    const t = full && full.text ? full.text : u.l2 ? u.l2.text : u.excerpt;
    for (const line of String(t).split(/\n/)) L.push(`> ${line}`);
    L.push("");
    if (full && full.reason) {
      L.push(`**理由**：${clamp(full.reason, 700)}`);
      L.push("");
    }
    if (full && full.suggested_replacement && full.suggested_replacement !== full.text) {
      L.push(`**建议表达**：${clamp(full.suggested_replacement, 700)}`);
      L.push("");
    }
  }
}
L.push("---");
L.push("");
L.push("## 3. 召回到的候选里，**没有条款号的**（只有 L2 正文）");
L.push("");
L.push("> 这些单元确实被召回，但**不在 L4 canonical** —— 也就是说库还没给它们发条款号。");
L.push("> 要引用它们只能引 L2（`unit_id + anchor + source_sha256`），证据级低于 L3 规则 / L5 P0。");
L.push("");
L.push("| # | unit_id | kb_type | 锚点 | 来源表 | 正文首段（截断） | best rank |");
L.push("|---|---|---|---|---|---|---|");
withoutArticle
  .sort((a, b) => a.bestRank - b.bestRank)
  .forEach((u, i) => {
    const txt = u.l2 ? u.l2.text : u.excerpt;
    L.push(`| ${i + 1} | \`${u.unit_id}\` | ${u.kb_type} | \`${u.anchor}\` | ${u.table || ""} | ${clamp(txt, 160).replace(/\|/g, "\\|")} | ${u.bestRank} |`);
  });
L.push("");
L.push("### 3.1 其中两条值得单独点出来");
L.push("");
const bookUnits = withoutArticle.filter((u) => /^#l\.1-/.test(u.anchor));
L.push(`- **整本书的 4,000 字切块被当成候选**：${bookUnits.map((u) => `\`${u.anchor}\``).join("、")} 都是《DK 科学育儿小百科·宝宝睡眠》按 4,000 字符切的大块`);
L.push("  （L2 `unit_type=clause`，一条 4,000 字）。它们在 hybrid 模式下把精确条目挤在后面，");
L.push("  这是 L6 已知限制（无重排、超长单元分段后段间语义依赖未建模）的表现，不是索引坏了。");
const wsUnit = withoutArticle.find((u) => u.unit_id === "c718fc1b02e3dc13ba4d");
if (wsUnit) {
  L.push("- **WS/T 579—2017《0 岁～5 岁儿童睡眠卫生指南》的正文已入库且能召回**（`c718fc1b02e3dc13ba4d`，4,989 字整篇一条），");
  L.push("  但它是**整篇正文件**，没有拆到条款级、也没有条款号 —— 想按条引用，得先走 `kb-clause-extractor` 拆条。");
}
L.push("");
L.push("---");
L.push("");
L.push("## 4. 反向补一遍：L4 canonical 里与婴幼儿睡眠相关的条款全清单");
L.push("");
L.push("> 上面第 2 节是「召回 → 条款号」；这一节是「条款号 → 有没有被召回」，用来回答");
L.push("> **「库里到底有多少条睡眠相关条款，这次召回了其中几条」**。");
L.push("");
L.push(`在 \`kb/l4/canonical/\` 四形态（共 1,242 条 stable）里，按「睡眠/睡姿/仰卧/窒息/猝死/SIDS/safe sleep/婴儿床/同床/夜灯/睡眠空间…」正则筛出 **${l4rows.length} 条**：`);
L.push("");
L.push(`- \`W-2.*\` 措辞修订对（revision_pair）：${wordingArts.length} 条 —— ${wordingArts.join(" ")}`);
L.push(`- \`S-1.*\` 正负样本（sample_case）：${sampleArts.length} 条 —— ${sampleArts.join(" ")}`);
L.push(`- \`E-1.*\` 定域条款（scoped_clause，**多为登记元数据，不是条款正文**）：${scopedArts.length} 条`);
L.push("");
L.push(`其中**被本次五条召回命中的**：${[...recallArticles].sort().join("、")}（${recallArticles.size} 条）。`);
L.push("");
L.push("未被命中的条款，原始正文（逐字，供人工核对）：");
L.push("");
const notRecalled = l4rows
  .filter((r) => !recallArticles.has(r.article_no) && r.form !== "scoped_clause")
  .sort((a, b) => a.article_no.localeCompare(b.article_no));
for (const r of notRecalled) {
  L.push(`**${r.article_no}**（${r.form}，p_level=${r.p_level || "-"}，锚点 \`${r.anchor}\`）`);
  L.push("");
  L.push(`> ${clamp(r.text, 400)}`);
  if (r.reason) L.push(`> 　理由：${clamp(r.reason, 240)}`);
  L.push("");
}
L.push("### 4.1 E-1.\* 这批要当心：它们是「资料登记元数据」，不是条款");
L.push("");
L.push("`scoped_clause` 的 `evidence_strength` 字段自己写着「资料登记元数据（field_value），非条款正文」。");
L.push("例如召回第 1 名 `E-1.225` 的全文就是 `About Sleep – CDC 睡眠推荐概览（含婴幼儿睡眠时长）` —— 这是**一条资料登记名**，");
L.push("不是一条可判定的规则。把 `E-1.*` 当条款引用会闹笑话。本次召回到的 E-1 号：");
L.push("");
L.push(`${[...recallArticles].filter((a) => a.startsWith("E-")).sort().join("、")}。`);
L.push("");
L.push("### 4.2 一处数据问题（顺带发现，交人工确认）");
L.push("");
L.push("`kb/l4/canonical/sample_case.jsonl` 里有一行 `form=sample_case` 却拿了 **`W-3.94`** 号（应为 `S-1.*`），");
L.push("锚点 `#广告文案明细/recvuJYdObzmjI/品线`，正文是广告素材登记行（含「襁褓巾」）。");
L.push("它同时也说明正则口径会把「襁褓巾」这种**只是产品名**的行捞进睡眠相关集合 —— 筛的是字面，不是语义。");
L.push("");
L.push("### 4.3 这 95 条里有相当一部分是「顺带命中」，别当成睡眠安全规则用");
L.push("");
L.push("上表的口径是**字面正则**（睡眠/婴儿床/襁褓/同床/夜灯…），它不判语义。逐个看过之后，分成三类：");
L.push("");
L.push("| 类别 | 大致数量 | 说明 |");
L.push("|---|---|---|");
L.push("| **A. 真·睡眠安全规则** | 十几条 | `W-2.*` 里谈睡眠安全/睡姿/睡姿风险/睡眠环境的改法：`W-2.34`（侧躺喂养证据不足）、`W-2.47`、`W-2.70`（左侧睡 vs 右侧睡，避开仰卧）、`W-2.72`（夜灯）、`W-2.103`（侧躺喂奶与同床 SIDS）、`W-2.122`、`W-2.36`；样本侧 `S-1.46`／`S-1.129`（预防扁头：睡姿与睡眠辅助用品误区） |");
L.push("| **B. 只是画面/产品名里有睡眠元素** | 多数 | `S-1.*` 里大量妈妈项目稿提到「宝宝在婴儿床里睡觉」「襁褓巾」「婴儿监视器」「熟睡的宝宝」，那是**素材描述**，不是安全规则；`W-2.166`、`W-3.94` 同类 |");
L.push("| **C. 登记元数据** | 42 条 | 全部 `E-1.*`，见 4.1 |");
L.push("");
L.push("B 类最容易被误引：它们的 `polarity` / `reason_category` 说的是那条素材的问题（多为品牌一致性、措辞），");
L.push("**不是**在给睡眠安全定规则。要用 B 类当依据，必须自己读 `reason_analysis` 判断。");
L.push("");
L.push("---");
L.push("");
L.push("## 5. 引用这几条时必须一起带上的边界");
L.push("");
L.push("- 有效期：L4 各条 `status=stable`，但 `kb/l4/canonical/` **无发布版本**（全库 `kb_version=v0`，`kb/versions/versions.jsonl` 只有注释）——不能当「已发布标准」引。");
L.push("- `p_level` / `risk_level` 是**分流标签**，不是放行结论；`suggested_replacement` **不许直接外发**。");
L.push("- **未命中 ≠ 合规**：这次没召回到，不说明内容没问题。");
L.push("- 本派生视图「Momcozy知识库 · 内容治理（派生视图）」的正文与权威库 `kb/l3/candidates/rules.jsonl`、`kb/l4/canonical/` 对不上时，**以权威库为准**。");
L.push("- 要出对外合规结论或引用具体数字/日期 → 必须回源按 `article_no` 核对（本文件已带锚点与 sha256，回源可直接用）。");
L.push("");

fs.writeFileSync(OUT, L.join("\n"), "utf8");
// 读回校验（node 通道自带校验：字节数与首行）
const back = fs.readFileSync(OUT, "utf8");
const bytes = fs.statSync(OUT).size;
console.log(`WROTE ${OUT}`);
console.log(`bytes=${bytes} chars=${back.length} lines=${back.split("\n").length}`);
console.log(`first_line=${JSON.stringify(back.split("\n")[0])}`);
