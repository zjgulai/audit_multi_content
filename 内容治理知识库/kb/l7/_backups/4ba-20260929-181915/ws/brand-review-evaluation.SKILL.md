---
name: brand-review-evaluation
description: "Evaluate the local brand content review workflow against gold and regression sets, measuring three-state accuracy, BLOCK precision, PASS leakage, REVIEW recall, P0 misses, coverage, and human workload."
---

# Brand Review Evaluation

Use a versioned, human-labeled gold set with text, image, and video examples plus ambiguous and adversarial cases. Run `../../core/evaluator.py` to compute the metrics. Keep the expected decision and the rationale separate from the model output.

Report at least:

- three-state accuracy;
- BLOCK precision;
- PASS leakage rate;
- REVIEW recall;
- P0 miss rate;
- coverage and extraction failure rate;
- reviewer time or issue volume change.

Do not claim the PRD targets are met without a defined denominator, sample version, and human adjudication record. Use `dataset-health-audit` for record integrity, not as a substitute for label accuracy.
