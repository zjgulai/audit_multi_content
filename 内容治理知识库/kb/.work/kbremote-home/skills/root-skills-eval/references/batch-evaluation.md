---
title: 批量评估指南
doc_type: reference
module: root-skills-eval
topic: batch-evaluation
status: stable
created: 2026-05-27
updated: 2026-09-04
owner: self
source: human+ai
---

# 批量评估指南

本文件定义 `root-skills-eval` 的批量评估模式详细规范。

## 触发方式

```bash
/root-skills-eval /path/to/skills --batch
/root-skills-eval /path/to/skills --batch --min-score=70    # 只评估低于70分的
/root-skills-eval /path/to/skills --batch --output-dir=./reports
```

## 批量评估流程

### Step 1: 遍历扫描

遍历 `skills/` 目录下所有子目录，识别合法 Skill（包含 SKILL.md）。

### Step 2: 逐个评估

对每个 Skill 执行标准六维度评估，生成独立 YAML 报告。

### Step 3: 汇总统计

聚合所有评估结果：

```yaml
batch_summary:
  total_skills: 80
  evaluated: 80
  passed: 75      # >= 85分
  failed: 5       # < 85分

  score_distribution:
    excellent(95+): 45
    good(85-94): 30
    needs_optimization(70-84): 4
    needs_refactor(<70): 1

  issue_aggregation:
    schema_compliance:
      total: 12
      auto_fixable: 8
    frontmatter_quality:
      total: 23
      auto_fixable: 15
    body_quality:
      total: 18
      auto_fixable: 10
    methodology_audit:
      total: 8
      auto_fixable: 0
    quality_gate:
      total: 5
      auto_fixable: 3
    directory_structure:
      total: 42
      auto_fixable: 42
```

### Step 4: 优先修复队列

按影响排序生成修复队列：

```yaml
priority_queue:
  p0:
    - skill: cbec-example-skill
      issue: S001 name格式错误
      impact: +3分
      fix_type: auto
  p1:
    - skill: mkt-example-skill
      issue: D004 缺少references/
      impact: +1分
      fix_type: auto
```

## 并行执行与子代理可靠性（硬性规则，v3.18.1）

批量评测常以"驱动会话 + 每批 2 个并行 subagent"运行（dsh 里由 agent 编排）。驱动必须遵守：

1. **无进展超时判定**：每个 subagent 连续 **N 分钟无写入/无产出**（默认 15 分钟；complex 100 条用例放宽到 25 分钟）即判定疑似中断，不得无限等待"完成通知"。
2. **超时处置**：先核对磁盘落盘（`results*.json` / `*-evaluation-report.yaml` / `*-final-report.html`）判断完成度：
   - 已完成 → 按现有结果收尾、回填 Excel；
   - 部分完成 → 在原会话断点**续接**，或**重启**该 skill 评测（二选一，记录选择）；
3. **进度以落盘为准**：计数以实际产出文件为准，不得只凭内存/记忆里的完成数。
4. **事件留痕**：中断/续接/重启事件写入批量摘要，供复盘（连续中断的 skill 单独标记）。

## 批量报告输出

### 文件命名

```
batch-eval-{timestamp}.yaml       # 完整汇总报告
batch-eval-{timestamp}-summary.md  # 人类可读摘要
batch-eval-{timestamp}.html        # 汇总 HTML 报告（总结论 + 人类可读摘要，局域网交付）
```

### 报告位置

默认保存到评估目录的 `eval-reports/` 子目录，生成后按 `trigger-eval-cases.md` Step 5 起局域网 HTTP 服务交付 HTML 链接。

## 与 root-skills-doctor 的联动

批量评估发现的问题可通过 `root-skills-doctor` 批量修复：

```bash
# 1. 批量评估，生成问题清单
/root-skills-eval ./skills --batch --output-dir=./reports

# 2. 用 doctor 批量修复结构问题
python root-skills-doctor/scripts/skill-doctor.py ./skills --batch

# 3. 重新评估验证
/root-skills-eval ./skills --batch
```

## 性能建议

- 80 个 Skill 的批量评估预计耗时 5-10 分钟
- 建议每周执行一次批量评估作为健康检查
- 大型仓库（>100 Skills）可分批评估

## Excel / 清单回填规范（v3.19.1）

批量评测完成后把结果回填进用户指定的 Excel（如「{项目}-Skills.xlsx」）时，**报告列必须写入可点击链接**，禁止只填本地绝对路径：

- 报告列单元格 = `=HYPERLINK("http://{host}:{port}/{skill}-final-report.html", "点击查看")`，其中 `{host}:{port}` 为局域网 HTTP 服务地址（由 `scripts/serve-lan.py` 或 `python3 -m http.server` 提供）；
- 回填的 修复版本 / 首次C / 修复后C / 上线 字段必须取自同一最终版评测（与最终版 YAML / 最终报告对账，见 `final-delivery-spec.md`）；
- 回填完成后逐行抽查：点击链接能在浏览器打开对应报告（HTTP 200）。

---

**最后更新**: 2026-09-07
