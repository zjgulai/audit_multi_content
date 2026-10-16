---
name: kb-content-review
description: |
  用 Momcozy 内容治理知识库（L0–L6）审查一段待审内容，按 PASS / REVIEW / BLOCK 三态给结论，
  并逐条给出可核对的依据（库名 + 版本 + 条款号 + 锚点 + source_sha256 + 逐字摘录）。
  当用户提交文案/脚本/字幕/详情页/广告创意/图片/视频并要求判断能不能用时使用；
  当出现"审查、审一下、合规检查、合规审查、内容审核、能不能发、会不会违规、能过审吗、有没有风险、踩线、禁用、敏感"
  或 "review / compliance check / is this compliant / will this pass / any risk" 等意图时使用；
  当用户追问某条结论的依据（"为什么判 BLOCK""依据是哪条规则"）时也使用。
  不适用：问知识库本身怎么建的（L0–L6、锚点、索引、规则来源等设计讨论）、工程操作类问题
  （文件在哪、索引怎么重建、跑哪个脚本）、没有审查意图的通用写作/翻译/润色、纯业务闲聊
  （育儿话题讨论、产品咨询）。这些不触发本 skill。
version: "1.0.0"
last_updated: 2026-09-23
complexity: "complex"
compatibility:
  claude: { status: "native" }
  kimi: { status: "native" }
  cursor: { status: "native" }
  gpt: { status: "bridge", limitations: ["渐进式披露需模拟"] }
  minimax: { status: "bridge", limitations: ["需中文优化"] }
  dsh: { status: "native", notes: "open agent skills 标准，SKILL.md 直接加载" }
  codex: { status: "native" }
---

# 内容审查（kb-content-review）

用知识库审一段内容，给三态结论 + 可核对的依据。**依据不足就拒答，不许拿常识补。**

本 skill 只有两段协议：**先查（检索协议），再答（引用契约）**。两段合在一个 skill 里，
但分开写清楚——只做检索不按格式引、或不检索直接答，都是幻觉。

## 何时不该使用

- 问知识库怎么建的（L0–L6、锚点、索引、"这条规则哪来的"）→ 直接讨论设计，不进审查流程
- 工程操作（文件在哪、索引怎么重建、跑哪个脚本）→ 按工程问题回答
- 通用写作 / 翻译 / 润色，没有审查意图 → 不触发
- 纯业务闲聊（育儿话题、产品咨询）→ 不触发

触发 ≠ 必须给结论：触发后仍要判断依据是否充分；不足就按 `no_hit_semantics` 拒答。

## 第一段：检索协议（查到什么）

**分层下探，顺序写死，不许跳层：**

1. **P0 确定性匹配** → `python3 kb/l5/matcher.py --text "<内容>" --json`
   退出码 1 = 命中，**命中即 BLOCK，不走向量**。
2. **规则层** → `kb/l3/candidates/rules.jsonl`（按 `kb_type` 与禁用片段逐字命中）。
   规则自带 `article_no`（L4 分配，**只读，不要自己编号**）。
3. **单元层** → `kb/l6/retriever.py`，**以 BM25 为主、向量为辅**：
   - 默认只跑 BM25；**只有 BM25 原始分低于门限时**才启用向量补召
   - 门限一律用**原始分**：BM25 ≥ `gate.bm25_raw_min`、余弦 ≥ `gate.vector_cosine_min`
   - **不要用 RRF 分当门限**：RRF 分恒为 `1/(60+k)`（实测恒在 0.016393），A/B 两组看起来一样高，没有区分度
   - **不要把等权 RRF 的 `hybrid` 当默认路径**：实测 p@3 从 0.958 掉到 0.542
   - 门限以下的只能标「参考」，**不能作为依据**
   - 读 `kb/l6/registry/l6.json` 的 `retrieval_capability.mode`：若为 `bm25_only`，
     检索结果与最终结论**必须显式标注「无语义召回」**
4. **原文层** → 按 `anchor` 回 `kb/l0/records/<表>/<记录>.json`（或 `kb/l0/snapshots/`）取逐字原文。

**相关性门限不是唯一判据**：实测 BM25 原始分在 A/B 两组仍有重叠（A 组中位 12.76 / 最低 5.32，
B 组中位 6.44 / 最高 10.02），所以**必须叠加规则判断——同时命中规则层才能算依据**。

**无命中即拒答**（本 skill 的核心职责）：L6 实测 B 组三种模式 hit@3 全为 0 却都返回了 Top3，
索引层没有拒答能力。拒答文案按 `no_hit_semantics` **原文**输出，并给：查了什么、用了几种模式、
为什么判断没有依据。**无命中不等于合规。**

**输出检索轨迹**：`查询 → 各模式 Top-N + 原始分 → 采用/舍弃及理由 → 最终依据`。

### 门限与规则层判据（从 registry 读，不要写死）

读 `kb/l7/registry/l7.json`：`retrieval.gate`（`bm25_raw_min` / `vector_cosine_min` / `coverage_bm25_min`）、
`retrieval.no_hit_semantics`、`decision_rules`。判据变更只改 registry，不改本文件。

## 第二段：引用契约（怎么把依据写出来）

1. 格式：`《<库名> <版本>》第 <条款号> 条` + 可点链接
2. **必须带 `anchor` + `source_sha256`**：只有锚点不算完整定位（锚点是行号，会漂移）
3. **逐字摘录**，不许转述、概括、润色
4. 标注 **`事实` / `推断`**，给**置信度**（高 / 中 / 低）
5. **引用不到本地锚点的结论不许输出**——防幻觉硬闸门：锚点解析失败、`source_sha256` 对不上、
   摘录与原文不逐字一致，三者任一不满足就丢掉这条结论，并记入「无法满足引用契约的结论」清单
6. 库名只能用知识库真实存在的四类库：**外部标准库 / 内部正负样本库 / 措辞表达库 / 产品描述库**
   （映射见 `kb/l0/registry/kb.json` → `dir_map`；当前 509 条规则的 `kb_type` 全是 `wording`，
   所以引用库名一律《措辞表达库》）。**不许写《合规措辞库》《广告法禁用语》这类不存在的库名**。

## 输出

严格按 `kb/l7/output_template.md`：**1–2 个问题逐条输出，≥3 个只出分类汇总 + 报告链接**
（完整清单必须真的写到 `kb/l7/reports/<run_id>.review.md`，不能只说"详见报告"）。
PASS / REVIEW / BLOCK 尾部动作不同；责任人从 `registry.approvers` 读，**不写死人名**。
分类只能用 `kb/l7/registry/l7.json` 的受控词表；词表外的记 `未分类-未分类`，**不许自造类别**。

## 分层原因（避免误用）

检索与引用是同一能力的两个阶段（查 → 答），中间没有独立使用者；拆成两个 skill 的实际风险不对称：
只加载检索段 → 结论没按格式引；只加载引用段 → 没检索就作答，两种都是幻觉。
按四类库拆成四个 skill 也会把同一套协议复制四份，用 `kb_type` 参数区分即可。

## 参考实现与资源

- 本 skill 的可执行参考实现：`scripts/review.py`
  （`python3 scripts/review.py --text "<内容>"`；`--json` 出结构化结果；退出码 0 = 有结论，3 = 拒答）
> **路径约定**：脚本路径相对**本 skill 目录**；知识库侧资源相对**知识库根**。
> 知识库根由 `scripts/review.py` 自行定位，顺序是：`--kb-root` → 环境变量 `KB_ROOT` →
> 已知落点（本机：`~/Documents/skill-test/…/知识库/内容治理`，以及软链接
> `~/.dsh/Momcozy知识库/kb`）→ 从脚本位置向上找。**库根必须是权威分层库**：含
> `kb/KB-ROOT.json` 标记，或 `l0…l7` 六件套齐全（`l7/registry/l7.json`、`l3/candidates/rules.jsonl`、
> `l5/matcher.py`、`l6/retriever.py`、`l7/output_template.md`、`l0/registry/kb.json`）。
> **派生视图会被明确拒绝**（只有 `3_措辞表达库/` + `_meta/DERIVED.md` 的那种壳，是给工作台镜像吃的，
> 没有分层库）—— 认错库根会让 P0 matcher、BM25、门限、拒答语义全部无法执行，所以宁可报错。
> 库不在已知落点时显式指定：`python3 scripts/review.py --kb-root <知识库根> --text "…"`
> 或 `KB_ROOT=<知识库根> python3 scripts/review.py --text "…"`。
- 输出模板：`<知识库根>/kb/l7/output_template.md`
- 门限 / 词表 / 责任人 / 分流规则：`<知识库根>/kb/l7/registry/l7.json`
- 条款号来源：`<知识库根>/kb/l3/candidates/rules.jsonl` 的 `article_no`（L4 分配）+ `<知识库根>/kb/l4/registry/l4.json`
- 已知边界：视频时间戳位置表达**无素材、未验证**；向量仅在规避型查询上可能补召回，
  字面重合型查询上 BM25 更好（实测见 `kb/l7/selftest_d_paraphrase.md`）
