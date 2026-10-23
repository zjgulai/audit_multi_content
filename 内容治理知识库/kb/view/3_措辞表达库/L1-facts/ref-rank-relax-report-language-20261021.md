---
asks:
  - 排名/最高级（best/#1/No.1/最佳/最好/最高级）为什么曾经仍被判 P0，放开的口径为什么没生效
  - 「口径说明本身被当成触发词」是哪个机制造成的、怎么防
  - 报告里的「逐字命中」为什么印出来是一整条正则源码
  - 「原因」里为什么会出现规则自己的口径说明（…放开，不再判险）
  - 同一句送审为什么被数成 4 处而记录里只有 2 处
  - 生成器与现表漂移时，重建会不会把出列的词静默补回来
  - 改完之后哪些判据盯着这件事（含反向对照）
collection: 3_措辞表达库
corroborated_by:
  - /Users/lute/project/audit_multi_content/PMO/守衡-排名放开与报告后台语言-20261021.md（三处根因、裁定 A、全部读数）
  - /Users/lute/project/audit_multi_content/内容治理知识库/kb/l5/p0_patterns.jsonl（variant_sources.relaxed_by_ruling 留痕）
  - /Users/lute/project/audit_multi_content/内容治理知识库/kb/l5/matcher.py（SELFTEST：放开族 6 条必须 MISS ＋ 100%/最安全/纯天然必须 HIT）
  - /Users/lute/project/audit_multi_content/内容治理知识库/kb/l8/p0_regression.py（排名族从正例挪到反向对照）
created_at: 2026-10-21
data_level: L2
evidence_group: coordinate
evidence_level: L2
forbidden: 不许据本条判断某条素材能不能发；不许把「放开」理解成整族放宽（100% / 纯天然 / 最安全 / 数量类销量宣称仍在 P0）；不许可据本条直接删 P0 词表里的其它词；不许把「非阻断提示」写成 findings 或计入问题数；不许在没跑 matcher/p0_regression 的情况下声称判据已落地。
half_life_days: 180
id: ref-rank-relax-report-language-20261021
kb_class: []
kind: fact
not_proves: 不能证明线上那单已复测通过（端到端复测未做）；不能证明生成器与现表已一致（现表 19 条 vs 可导出 17 条，重建被 P0 扩容守卫拦着）；不能证明其它 rule_code 的边界表述没有同类问题（实测还有 8 处漂移）；不能证明 V02 的 reason 文本已更新（仍写着「最好/最佳一类」）；不能替代措辞表达库的条款判断。
owner: 刘华丽
pii:
  detected: false
  masked: false
  strategy: 未检出自然人信息：正文为判据与读数，素材原文只是一句规则口径说明
provenance:
  anchor: PMO/守衡-排名放开与报告后台语言-20261021.md#二、三处根因
  confidence: 确定
sensitivity_level: L2
source:
  captured_at: 2026-10-21
  fingerprint: ad4b9b2f10f17739
  kind: file
  ref: /Users/lute/project/audit_multi_content/PMO/守衡-排名放开与报告后台语言-20261021.md
summary: 2026-10-21 Owner 两条：审查报告不许出现后台语言；既然 09-09 口径放开了 best/#1/No.1/最佳/最好，为什么还判成问题。根因三处：① 10-19 的出列只过滤 literal/synonym，H05/V03 的正则（#1、最…高…）照旧命中；② 10-21 把规则自己的边界表述（含「…放开，不再判险」）灌进了 patterns，于是「说明已放开」的句子成了「没放开」的证据；③ 报告把 matched[].pattern（正则源码）当「逐字命中」印、把 kb/l3/…jsonl# 这类库内路径印进建议与依据、把 L3 reason 里的口径说明印进「原因」。另有一处：P0 快路的回执被逐行正则又解析了一遍，同一句被数成 4 处（记录里 kb.issue_count=2）。裁定 A：排名/最高级一族退出 P0、不进问题清单，中文事实性排名降为非阻断提示。落地：模式表出列并留痕（relaxed_by_ruling）、生成器加 RELAXED_TERMS/RELAXED_REGEX/RELAXED_BND_RE（重建不回填）、p0_fastpath 印真实命中文字＋去口径括号＋不印库内路径＋RANK_ADVISORY_RX 非阻断提示、dual_track 不再二次解析回执。
tier: L1
title: 排名/最高级一族退出 P0 ＋ 审查报告去后台语言：判据落在哪（Owner 2026-10-21 裁定 A）
topic: 判定口径变更 / 报告生成 / 口径落地执行点
valid_until: 2027-04-19
---

## 结论（先看这一句）

「放开」如果只写在规则的**文本**里，而触发它的**正则/词条**没跟着出列，系统就会继续判它 ——
本次就是：H05 的 `(?:no.?\s*1|#\s*1)\b` 与 `最\s*(…|高|…)` 还在表里，V03 另有一条同样的 `#1` 正则。

## 三处根因（都能指出行号）

1. **出列只覆盖字面词，不覆盖正则**
   `l5_export.py` 的 `exclude` 只过滤 `literal` / `synonym`；`regex_patterns` 原样进表。
   ⇒ 10-19「最佳/最好出列」之后，同一句话里的 `#1` 与 `最高级` 仍然命中。

2. **边界表述被当成触发词**
   10-21 为「规则边界表述送审也要命中」，把 11 条规则的边界表述逐字写进 `patterns`。
   H05 的边界表述正是那句「…按 2026-09-09 口径放开，海外广告允许，**不再判险**」
   ⇒ **说明「它已放开」的文字，成了「它没放开」的证据**。
   判据：边界表述里出现「放开 / 不再判险 / 允许」时，它是**口径说明**，不是规则名，不进触发词。

3. **报告把内部标识当业务字段印**
   - 「逐字命中」取的是 `matched[].pattern` —— 正则命中时那是**正则源码**；真实命中文字在
     `matched[].text`（匹配器已有），只是没搬。
   - 「原因」直接印 L3 的 `reason`：`H05 虚假安全承诺（…放开…不再判险）` —— 一条 P0 的原因里说「不再判险」。
   - 「修改建议 / 依据」兜底里印 `kb/l3/candidates/rules.jsonl#W-1.33` —— 业务侧点不开。

4. **同一张回执被数了两遍**
   P0 命中即停链，`answer` 就是由 `p0_findings` 渲染出的收据；`kbFindingsOf` 的逐行正则分支
   又把它解析成一份 ⇒ 2 条变 4 条（记录里 `kb.issue_count=2`、`total=4`，恒等式当场不成立）。
   判据：**P0 快路单的收据不是独立证据**，不许二次解析。

## 裁定（Owner 2026-10-21）

`#1 / No.1 / best / 最好 / 最佳 / 最高级` **不再判险、不进问题清单**；
`第一 / 销量第一` 这类中文事实性排名**不阻断**，只给一句「需补可核验依据」的提示。

**边界（不许外推）**：`100%` / `纯天然` / `最安全` 仍在 P0；数量类宣称（`销量 1 万台` / `sold 6 million`）
仍在 V03。PRD §7.3 第 3 条与 09-09 口径在这一个词族上冲突，本轮以 Owner 最新裁定为准。

## 执行点（指不出这些就是没落地）

- `kb/l5/matcher.py` SELFTEST：放开族 6 条必须 MISS；`100% safe` / `最安全` / `纯天然` 必须 HIT。
- `kb/l8/p0_regression.py`：`#1 breast pump` 从正例挪到**反向对照**（再加 2 条中文排名负例）。
- `kb/.work/l5_export.py`：`RELAXED_TERMS` / `RELAXED_REGEX` / `RELAXED_BND_RE` —— 重建不回填。
- `kb/l5/p0_patterns.jsonl`：`variant_sources.relaxed_by_ruling` 记下每次出列（可核、不静默）。
- `test/_probe_dedupe_report.mjs`：报告里不许出现正则源码 / `kb/…` 路径 / 规则码 / 本码 / 「不再判险」。

## 顺带查出来的两个真缺陷

1. 生成器 `--apply` 此前**根本跑不起来**：`BOUNDARY_BY_CODE`（715 行）调用 `norm`，而 `norm` 定义在 832 行
   ⇒ `NameError`。10-21 之后所有表改动**只可能是手改**。
2. `SALES_RANK_REGEX` 全是双反斜杠（raw string 里 `\\b` ＝字面反斜杠+b）⇒ 生成侧 7 条正则**一条都命不中**。

## 读数（当场跑过）

`matcher --selftest` ✅；`p0_fastpath --selftest` 65/0；`p0_regression` 175/175 漏报率 0；
口径说明那一句 `hit=False`；`sold 6 million units` 与 `100% safe` 仍按原口径命中；
`dual_track --selftest` 141/2、`test_agent` 296/3（两条/三条均为**存量红**，来自未提交的报告/建议改动）。