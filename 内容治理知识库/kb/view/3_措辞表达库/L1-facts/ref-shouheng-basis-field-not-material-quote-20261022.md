---
id: ref-shouheng-basis-field-not-material-quote-20261022
title: "[参考实现] 依据文档链接不许拿送审素材原文冒充依据（2026-10-22）：没有外部文档就如实写「无外部依据」，不许凑「最像的来源」"
collection: 3_措辞表达库
tier: L1
topic: 知识
kind: fact
kb_class: []
owner: 刘华丽
created_at: 2026-10-22
valid_until: 2027-04-20
half_life_days: 180
evidence_level: L2
data_level: L2
sensitivity_level: L2
evidence_group: rule
summary: 报告与卡片的「依据文档链接」这一格原本会印「送审素材原文：「…」」—— 那不是依据，是问题描述（同一句话本来就印在「问题描述」与总览的「命中描述」两列里，而且点不开任何东西）。真因三层：① dual_track.mjs 的 materialEvidenceText() 只要模型侧条目带 excerpt 就把素材原文填进依据格，且它排在外部标准之后、独立语义复核之前 ⇒ 没挂上外部标准时必然落到这里；② model_side.mjs 提示词给了「图片的直接观察例外（source/source_url 可为 null，给 visual_anchor 即可）」⇒ 模型合法地不挂外部标准（真单 4 条全部 basis_kind=material、basis_cited=false）；③ 呈现口径把素材原文当依据。修法：删除 materialEvidenceText，换成 noExternalBasisText(f) —— 有 visual_anchor 印「无外部依据（原图观察：<锚点>；需人工核对）」，没有印「无外部依据（需人工核对）」；卡面 basisCard 新增 ^无外部依据 分支（不被长句压缩器砍成半句）；记录层 basis_kind 分出 visual_observation / material / 外部来源；上卡过滤器例外从「有素材原文」改成「有素材锚点」（摘掉的是冒充依据的原文，不是问题本身，Owner 同一轮选的是「4 条都留」）；提示词补 1c-2 与第 6 条的例外边界：资质/年限/背书/功效/对比这几类必须有外部文档，只有纯画面事实才允许只给 visual_anchor，且不许为了填满那一格去编法规或凑「最像的」来源。这一单已发布的报告用同一正文按新口径覆盖重发（docs +update overwrite，revision 5），diff 只有那 4 行。判据：dual_track --selftest 154 项（④b2/④b3 改成「不许出现链接 + 必须出现无外部依据 + 不许出现送审素材原文」）、merged_record.test ⑨（真实问题照旧在清单里）、model_side_limit.test ⑩（纯视觉条目带图像锚点、写无外部依据、不凭空冒链接）、verify_cards 350 项、test_agent 304 项。
asks:
  - 报告里「依据文档链接」这一格到底要放什么，为什么放送审素材原文是错的？
  - 模型侧靠看图判出来的问题，没有外部标准时这一格应该怎么写？
  - 为什么不能按类别映射一个「最像的」已登记标准把那一格填满？
  - 修完之后依据格只有哪几种写法，分别由哪一处代码决定？
  - 「依据格不印素材原文」与「真实问题不许被滤掉」怎么同时成立，判据在哪？
  - 接上外部标准这件事靠提示词还是靠代码，怎么证它没有变成软要求？
  - 同一天这两条裁定（4 条都留 / 没标准就写无外部依据）各自落在哪几行代码上？
not_proves: 不能证明模型侧以后就会挂外部标准 —— 提示词只是要求，模型照不照做要看下一单的真读数；本条只保证没挂上时依据格不撒谎。不能证明这 4 条问题本身成立或不成立（本条只改依据怎么印，不改判定内容与严重度）。不能证明外部链接与条款逐字对得上（那在 tools/verify_external.py）。不能证明线上已生效（守护进程重启后才加载新代码，重启必须走 AGENTS.md §2.7 闸门）。不能替代 3_措辞表达库 的任何条款。
source:
  kind: file
  ref: /Users/lute/project/audit_multi_content/PMO/守衡-依据格不许拿素材原文冒充依据-20261022.md
  fingerprint: cddd1a4f548400d1
  captured_at: 2026-10-22
corroborated_by:
  - PMO/守衡-依据格不许拿素材原文冒充依据-20261022.md（留底件：Owner 原话逐字、三层真因、修法表、判据与读数、部署边界）
  - tools/agent/dual_track.mjs（noExternalBasisText / basisCard 的 ^无外部依据 分支 / onMeta 的 basis_kind / 上卡过滤器）＋ tools/agent/dual_track.mjs --selftest 的 ④b2、④b3
  - tools/agent/merged_record.test.mjs ⑨ ＋ tools/agent/model_side_limit.test.mjs ⑩（真实问题不被滤掉；纯视觉条目带锚点且不冒链接）
  - 已发布报告 https://momcozy-in.feishu.cn/docx/TT71dAH3aobl3dxVc52cCShUnGe（revision 5，4 条依据格已改为「无外部依据（原图观察…）」）
provenance:
  anchor: PMO/守衡-依据格不许拿素材原文冒充依据-20261022.md#一、现象（Owner 原话，逐字）
  confidence: 确定
pii:
  detected: false
---

# 依据文档链接不许拿送审素材原文冒充依据（2026-10-22）

## 现象（Owner 原话，逐字）

> 「依据文档链接，是需要提供证明这是个问题的外部链接，报告中提供的
> 「送审素材原文：「Ask Midwife Vic」」更像是问题描述。有4个问题都是如此」

真单 `https://momcozy-in.feishu.cn/docx/TT71dAH3aobl3dxVc52cCShUnGe` 的 5 条问题里，
4 条模型侧（F-01 / F-02 / F-04 / F-05）依据格全是 `送审素材原文：「…」`；
只有库侧那条 F-03 印的是 `《内部正负样本库…》第 N-1.376 条（链接：…）`。

## 真因（三层）

1. **渲染层**：`dual_track.mjs::materialEvidenceText(f)` —— 只要模型侧条目带 `excerpt`，
   依据段就取 `送审素材原文：「…」`，且它排在外部标准之后、独立语义复核之前
   ⇒ 没挂上外部标准时**必然**落到这里。
2. **解析层**：`model_side.mjs` 提示词 1c 与第 6 条写着「图片的直接观察例外：
   `source`/`source_url` 可为 null，给 `visual_anchor` 即可」⇒ 模型**合法地**不挂外部标准
   （合并记录里 4 条全部 `basis_kind:"material"`、`basis_cited:false`、`kb:null`）。
3. **呈现口径**：`excerpt` 本来就印在「问题描述」与总览「命中描述」两列
   ⇒ 依据格再印一遍 = 同一句话说两次，而且那一格**点不开任何东西**。

## 修法（五处代码 ＋ 一份已发布报告）

| # | 位置 | 改法 |
|---|---|---|
| 1 | `tools/agent/dual_track.mjs` | 删 `materialEvidenceText()`，换 `noExternalBasisText(f)`：有 `visual_anchor` ⇒「无外部依据（原图观察：<锚点>；需人工核对）」；没有 ⇒「无外部依据（需人工核对）」 |
| 2 | 同上（卡面 `basisCard`） | 新增 `^无外部依据` 分支：原样印出来（不被长句压缩器砍成半句），超 80 字才截 |
| 3 | 同上（`onMeta`） | `basis_kind` 分出 `visual_observation` / `material` / 外部来源；`basis_missing` 判据改成「有没有 `excerpt`」 |
| 4 | 同上（上卡过滤器） | 例外从「有素材原文」改成「有素材锚点」—— 摘掉的是**冒充依据的原文**，不是问题本身 |
| 5 | `tools/agent/model_side.mjs` | 提示词补 1c-2 与第 6 条例外边界：资质/年限/背书/功效/对比**必须有外部文档**；只有纯画面事实可以只给 `visual_anchor`；**不许为填满那一格去编法规或凑「最像的」来源** |
| 6 | 已发布报告 | 同一正文按新口径覆盖重发（`docs +update --command overwrite`，revision 5），diff 只有那 4 行依据格 |

## 判据（每一条都指得出位置）

- `node tools/agent/dual_track.mjs --selftest`：**154** / 0（④b2、④b3 改成三面钉：
  不许出现链接 / 必须出现「无外部依据」/ 不许出现「送审素材原文」与素材原文本身）。
- `node tools/agent/merged_record.test.mjs` ⑨：真实问题**照旧在清单里**（`total=1`），
  依据格不冒充依据，记录层仍答得出 `basis_kind=material`。
- `node tools/agent/model_side_limit.test.mjs` ⑩：纯视觉条目依据格**带图像锚点**、
  写「无外部依据」、**不凭空冒链接**。
- 其余回归：`merged_record` 10/0、`model_side_limit` 16/0、`model_side_taxonomy` 5/0、
  `merged_report` 13/0、`prd53_format` 30/0、`verify_cards` 350/0、`test_agent` 304/0。

## 界外（本条不能证明什么）

- 不证明模型侧以后会挂外部标准（提示词是要求，不是判据）；本条只保证「没挂上时不撒谎」。
- 不证明那 4 条问题成立与否（只改依据怎么印）。
- 不证明线上已生效（守护进程未重启）。
- 不证明外部链接与条款逐字对得上（那在 `tools/verify_external.py`）。
