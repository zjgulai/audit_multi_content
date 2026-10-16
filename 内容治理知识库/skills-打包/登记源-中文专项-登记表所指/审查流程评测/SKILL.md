---
name: 审查流程评测
description: |
  评测审查流程本身的质量：三态准确率、打回判定准确度、高危漏检、覆盖率、复核召回与人工工作量（金标集/回归集）。触发词：审查流程评测、评估审查流程、审查流程准不准、三态准确率、打回判定准确度、金标集、回归集、漏放、该拦的漏掉、高危漏检、覆盖率、复核召回、人工工作量、回归评估、流程评测、review evaluation。何时不用：判断某条具体内容能不能发（走 内容审查总控）、专项检查（走对应专项 skill）。

  Evaluate the local brand content review workflow against gold and regression sets, measuring three-state accuracy, BLOCK precision, PASS leakage, REVIEW recall, P0 misses, coverage, and human workload.
version: "1.0.0"
complexity: "complex"
enabled: "true"
user-invocable: true
---

# Brand Review Evaluation

Use a versioned, human-labeled gold set with text, image, and video examples plus ambiguous and adversarial cases. Run `~/.dsh/Momcozy知识库/kb/l7/review-engine/core/evaluator.py` to compute the metrics. Keep the expected decision and the rationale separate from the model output.

Report at least:

- three-state accuracy;
- BLOCK precision;
- PASS leakage rate;
- REVIEW recall;
- P0 miss rate;
- coverage and extraction failure rate;
- reviewer time or issue volume change.

Do not claim the PRD targets are met without a defined denominator, sample version, and human adjudication record. Use `dataset-health-audit` for record integrity, not as a substitute for label accuracy.

## 强制链路里**不适用**（2026-10-03 加）

本 skill **不是素材审查入口**，所以**不套用**「层前置 → 引擎 → 发飞书」那条链 —— 它评的是**流程本身**（三态准确率 / 高危漏检 / 覆盖率）。

- 它跑的是金标集 / 回归集，**逐条**发飞书没有意义；结论以评测报告交付；
- 要引用某条判定的依据，回 `kb-content-review` 的引用契约（判据不重造）。

> 写清「不适用」是为了**别抢活**：照抄强制链路节会让本 skill 去跑别人的层前置 / 替专项下判，
> 而路由表的让位关系（`kb/l7/registry/routes.yaml`）不允许这样。
