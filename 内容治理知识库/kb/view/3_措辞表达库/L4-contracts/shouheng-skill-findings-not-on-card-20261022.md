---
asks:
  - 卡上只显示 1 条而判定主体判了 5 条，差在哪一步
  - 库侧 3 条命中为什么压成 1 条
  - 判定主体散文里的问题怎么变成卡面条目
collection: 3_措辞表达库
corroborated_by:
  - "PMO/logs/ws_daemon.log :: 2026-10-22T06:13 双轨｜模型侧 0 条 / 1006ms｜库侧 REVIEW/3 条 ⇒ 合并 1 条"
  - "engine-20261022-141117-98974.json :: 3 条 risk_items 位置/类目全同"
  - "PMO/守衡-判定主体条目没上卡-20261022.md :: 离线复现 kb=3 merged=1"
created_at: 2026-10-22
created_from:
  knowledge_layer: L7 评审链 · 卡片成形
  raw_cases:
    - 2026-10-22 Breastfeeding Month 横幅单（om_x100b62aec31ce4a0b0fd90e05aec96e）
  source_docs:
    - PMO/守衡-判定主体条目没上卡-20261022.md
data_level: internal
evidence_level: L2
half_life_days: 180
id: shouheng-skill-findings-not-on-card-20261022
kind: judgment
last_validated: 2026-10-22
not_proves:
  - 不证明模型侧 1006ms 返回空数组是退化还是真的没发现问题
  - 不证明修后卡面符合 PRD §17 字数上限（实测 873 字 / 上限 100，该模块只报读数不阻断）
  - 不证明视频/链接单的判定主体条目也会被抽到 —— 本次只实测图片单
owner: 刘华丽
pii:
  detected: false
  masked: false
  strategy: none
provenance:
  anchor: 同一单的 answer / sidecar / ws_daemon.log 三处时间戳与记录 id reczz28QLyG5cVHj
  confidence: 确定
  method: 本仓实测 + 离线复现（同一份真实回答与真实旁挂喂进 mergeFindings）
  record_id: reczz28QLyG5cVHj
  ref: PMO/守衡-判定主体条目没上卡-20261022.md
  type: run
rollback_to: PMO/守衡-判定主体条目没上卡-20261022.md §三 修法（回退：删 skill_findings.mjs 与 agent.mjs 里那次调用）
sensitivity_level: L2
source:
  captured_at: 2026-10-22T14:30:00+08:00
  fingerprint: d8137cf5706dfa5f
  kind: file
  record_ids:
    - reczz28QLyG5cVHj
  ref: /Users/lute/project/audit_multi_content/PMO/守衡-判定主体条目没上卡-20261022.md
summary: 卡内逐条来自双轨合并结果；库侧抽机读旁挂 risk_items。引擎只给负面样本命中且位置/类目全同 ⇒ 压成 1 条；判定主体判在散文里的实质问题没有结构化产者 ⇒ 上不了卡。修法：skill_findings.mjs 从「问题清单」抽「描述｜位置｜改：…」并入合并（source='model'，不单独定 BLOCK），origin_track='skill' 留痕。
tier: L4
title: 判定主体判出的问题为什么上不了卡：卡内条目只认结构化产者
topic: 守衡审查链 · 卡片条目来源
valid_until: 2027-04-20
validated_by: 刘华丽
verification:
  independent_sources: 2
  non_obvious: 1
  predictive: 2
  score: 0.833
  verdict: pass
---

## 病灶

卡内逐条来自双轨合并结果。库侧条目抽的是机读旁挂 `risk_items`（结构化优先）。
2026-10-22 那一单引擎只给 3 条负面样本命中，位置全是「顶部，图 1 第 1 处」、类目全「品牌信任与声誉」
⇒ 按「位置相同 + 类目相同 = 同一问题」压成 **1 条**。

判定主体（`图片安全审查` skill）判出的 5 条在**散文**里，**没有结构化产者** ⇒ 一条都没上卡。
形状：**散文没有失败信号**。

## 修法

`tools/agent/skill_findings.mjs` 只抽不判，从「八、分级结论 → 问题清单」抽「描述｜位置｜改：…」。
合并语义一个字没改：`source='model'`（并集、倾向 REVIEW、不单独定 BLOCK、不参与 PASS）；
另用 `origin_track='skill'` 留痕，落表 `sides` 分得开 skill 与 model。

## 四条边界

无位置即丢；标「参考/非本图判定/降权」即丢；严重度只给 REVIEW；抽不到要出声。

## 判据

skill_findings 7/7；dual_track 55/55；test_agent 303/303；verify_cards 350/350。
