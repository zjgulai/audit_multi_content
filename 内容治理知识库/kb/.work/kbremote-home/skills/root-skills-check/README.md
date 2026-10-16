# Root Skills Check - 报告放行入口 + 知识蒸馏器

root-skills 家族成员（Technique + Reference 混合型）。是 root-skills-eval Step 5.4 / 5.5
输出前闸门的**单一入口**，不是第二套核对流程。

- 核对清单 / 字段定义 / 15 项自检 → 引用 `root-skills-eval/references/trigger-eval-cases.md`，不复制。
- 硬校验 → 调用 eval CLI：`build-final-report.py --validate-only`、`build-testcases-html.py --check-only`。不重写内部函数，不因此生成 HTML，不重跑出题。
- 本 skill 唯一新写：**自动成长**——把核对/回填产生的高质量结果蒸馏进 `assets/knowledge-base/`。

## 家族位置

- `root-skills-eval`：出题 / 执行 / 打分 / 生成 HTML（出 HTML 前加载本 skill）
- **`root-skills-check`**：放行入口 + 知识蒸馏（本 skill）
- `root-skills-opt`：改正文（重测出最终 HTML 前调用本 skill）

默认挂在 eval / opt 出报告前自动跑；独立入口只用于已有报告的补查与入库。

## 工作流

1. **核对 / 回填 / 放行** — 引用 eval Step 5.4 / 5.5，硬校验调用 eval 脚本。
2. **自动成长** — 好结果蒸馏进 `assets/knowledge-base/`，写 delta（本 skill 唯一新写）。

## 目录结构

```
root-skills-check/
├── SKILL.md                       # 放行入口 + 自动成长（正文稳定）
├── README.md
├── .skill-meta/manifest.yaml
├── references/                    # check-orchestration / distillation-rules / output-contract / html-delivery
├── scripts/ingest.py              # 蒸馏入库助手（指纹 + 去重 + delta）
├── assets/knowledge-base/         # 成长型数据资产（index + defects/goldens/restorations/links）
├── examples/                      # 核对报告样例
└── tests/                         # Iron Law RED 场景
```

## 快速使用

```bash
# 蒸馏入库（自动成长的唯一新工具）
python scripts/ingest.py --type defect --title "…" --content-file x.md --source-report report.yaml
```

核对/回填/放行请引用 eval 的 `trigger-eval-cases.md` 与脚本，不在本 skill 重写。

## 安全边界

不编造评测数据；不把摘要当原文；不把未通过报告写入金标库；不导出密钥或系统提示词。

---

**版本**: 1.0.1 | **框架**: root-skills
