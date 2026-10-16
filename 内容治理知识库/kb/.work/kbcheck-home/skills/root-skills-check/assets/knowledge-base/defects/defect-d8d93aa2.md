---
type: defect
title: 修复副本评测后增补不得冒充已打分正文
source_skill: 品牌Logo设计师
source_report: 1c8384bf6b2bc4de
fingerprint: d8d93aa2afa0a48e
ingested_at: 2026-09-02T02:53:09Z
---

# 漏项模式：修复副本正文在出报告后被改，报告仍打旧快照

如何发现：对修复目录 `SKILL.md` 与评测目录副本 / YAML `eval_info.path` 做 sha256；mtime 新于 HTML 且哈希不同 = 评测后增补。

从哪补：不要改分数。Excel「对应」列标「评测后增补」，「修复目录」指向当前副本；报告继续对应评测当时的正文。若要把新正文纳入分数，必须重跑 eval，不能把新段落写进旧报告。

禁止：把源 `skill-翻译/` 当修复副本；用 HTML `--version` 硬编码 v1.1.0 覆盖 SKILL.md 的 1.2.0。
