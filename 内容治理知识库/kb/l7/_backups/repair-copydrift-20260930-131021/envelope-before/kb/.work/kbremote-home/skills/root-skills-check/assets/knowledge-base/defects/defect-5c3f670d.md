---
type: defect
title: 回填结论必须用规范词表否则 validate-only 四格归零
source_skill: agent-build-flow
source_report: ac4266e2802803f1
fingerprint: 5c3f670da86c5e59
ingested_at: 2026-09-15T13:07:54Z
---

## 现象
同一份产物，两条校验路径结论相反：
- `build-final-report.py --name X --version V --yaml ... --cases ... --process ...`（构建路径）
  → 输出前自检 15 项全部通过
- `build-final-report.py --validate-only --version V --yaml ... --cases <test-cases.html>`（独立核对路径）
  → 报 `v3.17.0：测试用例区与最终版本不一致——第 N 轮 TP：内联用例=0，最终版本 YAML=27` 一类，
  且第 2/3 轮四格大量算成 0

## 根因
`--validate-only` 会直接解析 `--cases` 指向的 **test-cases.html 原始文件**，而该文件里
每个轮次单元格是 `<span class='tag tag-触发'>触发</span><div class='resp'>…</div>`；
`_case_cell_verdict()` 要求单元格**以结论词开头**。若回填时把结论写成 skill 名（如 `agent-build-flow`）
而不是 `触发/不触发/加载/未加载`，解析器一律返回空串，四格大量归零。

## 判据
同页自算复现：
```python
seg  = bfr._table_segment_after(page, "全部用例与每轮 AI 原文回复", cs)
cases= bfr._parse_case_table(seg)
# 期望 len(cases)==用例数 且 每条 3 轮非空；否则就是单元格首词不合规
```
若自算四格与 YAML 逐格相等，说明**数据是对的**，问题只在单元格首词。

## 修正
- 回填 `results.json` 的「结论」**必须**用规范词表：`触发 / 不触发 / 追问 / 加载 / 未加载`；
  想让记录保留"实际加载了哪个 skill"，另开字段（本评测用「原始结论」）保存。
- 调用场景的结论主语是**被测 skill 本名**：加载了本名 → `加载`；未调用或加载了别的 skill → `未加载`。
- 单版本（未进入修复）核对用 `--validate-only` 且**不传 `--cases`**；`--cases` 路径的对账只适用于多版本场景。
