# 核对报告样例（示例）

> 格式样例；核对清单与 15 项自检的字段定义见 `root-skills-eval/references/trigger-eval-cases.md`。

## 核对清单（pass/fail + 证据）

| # | 核对项 | 结果 | 证据 | 回填动作 |
|---|--------|------|------|----------|
| 1 | 轨道 B 每轮 TP/FP/FN/TN | pass | 3 轮四格齐全 | — |
| 2 | 轨道 C 每维评分依据 | pass | 六维 basis 齐全 | — |
| 3 | 全部用例每轮 AI 回复原文 | fail | case 7 轮 2 为摘要 | 从会话归档逐字改回 |
| 4 | 报告内链接失效 | pass | 锚点可解析 | — |
| 5 | scoring-formulas 公式块 | pass | 「一·补」含 id=scoring-formulas | — |
| 6 | 轨道 A/C 总分 | pass | track_a.total / track_c.total 写入 | — |
| 7 | 安全/组合/调用标签统计 | fail | call_tag 缺 passed_gate | 从调用执行记录补 |

（核对项明细以 eval `trigger-eval-cases.md` 为准，此处不复制。）

## 回填动作

- case 7 轮 2：从 `eval-{name}/round*_results.json` 逐字回填。
- `track_b.call_tag.passed_gate`：从调用场景执行记录补 `true`。

## 数据资产 delta

```
数据资产 delta:
  新增 2 条: defect: call_tag 缺 passed_gate；restoration: case7 摘要→原文对照
  跳过 1 条重复: 指纹 a1b2c3d4
```

## 放行结论

- 回填后重检全部通过 → **报告已放行**。
