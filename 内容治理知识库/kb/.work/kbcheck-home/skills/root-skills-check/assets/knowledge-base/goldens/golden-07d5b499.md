---
type: golden
title: HTML一补必须含scoring-formulas
source_skill: 亚马逊Listing专家
source_report: 0cce427b546245c0
fingerprint: 07d5b4993bbe18fd
ingested_at: 2026-09-02T02:42:43Z
---

# 金标：最终 HTML 一·补必须含 id=scoring-formulas

`self_check_html` 硬校验：
- `id="scoring-formulas"`
- 文案含「总分 = Σ(分项得分 × 权重) ÷ 105」
- 「P = TP / (TP + FP)」
- 「轨道 B F1」
- 「总分 = Trigger + Output + Progressive + Safety + Script + Spec」

评测目录里的旧 final-report.html 可能缺这块；桌面交付物须用当前 `build-final-report.py` 重生，不要把缺公式的 eval 目录副本覆盖桌面已过检报告。
