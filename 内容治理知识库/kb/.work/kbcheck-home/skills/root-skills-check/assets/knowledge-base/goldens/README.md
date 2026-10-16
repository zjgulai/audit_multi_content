# goldens/ — 金标片段

每条金标一个文件，命名 `golden-<指纹前8位>.md`。只收「检查通过」的字段与合格评分依据，
不收未通过报告、不收整份 HTML、不收被测 skill 全文。

## 条目格式

```markdown
---
type: golden
source_skill: <被测 skill 名>
source_report: <来源报告指纹>
fingerprint: <sha256 前16位>
ingested_at: <ISO 时间>
---

## 完整 TP/FP/FN/TN（合格样例）
<每轮四格 + P/R/F1>

## 合格评分依据（basis）
<轨道 C 某维的合格 basis 原文>

## 公式模板
<scoring-formulas / 六维加权公式>
```
