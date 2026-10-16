# restorations/ — 改写 vs 原文对照

每条对照一个文件，命名 `restore-<指纹前8位>.md`。只留识别「非原文」所需的最小片段，
不整段搬运 AI 回复、不搬被测 skill 全文。

## 条目格式

```markdown
---
type: restoration
source_skill: <被测 skill 名>
source_report: <来源报告指纹>
fingerprint: <sha256 前16位>
ingested_at: <ISO 时间>
---

## 改写片段（如何被识别为非原文）
<空/模板句/摘要/截断 的片段>

## 原文片段（从会话归档逐字回填）
<真实原文片段>

## 识别要点
<这次是靠什么特征发现它不是原文的>
```
