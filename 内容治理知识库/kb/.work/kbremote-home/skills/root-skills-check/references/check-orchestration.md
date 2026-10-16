# Check Orchestration - 如何编排 eval 闸门（引用，不复制）

本 skill 不重做核对流程。核对清单、字段定义、15 项自检的**唯一权威源**是：

> `root-skills-eval/references/trigger-eval-cases.md`
> - Step 5.4：输出前闸门（漏数据补齐 + 全部用例原文回补）
> - Step 5.5：输出前自检（15 项）

**禁止把上述内容复制粘贴进本 skill**。需要核对时，**只执行 Step 5.4 与 Step 5.5**。不要加载或重跑该文件的 Step 0–4（出题 / 三轮 / 打分 / 生成 HTML）。

## 硬校验：只调用 eval 现有 CLI（禁止调内部函数、禁止因此生成 HTML）

```bash
python3 {eval}/scripts/build-final-report.py --validate-only \
  --name {name} --version "最终" --yaml {report.yaml} \
  [--cases {test-cases.html}] [--html {final-report.html}]

python3 {eval}/scripts/build-testcases-html.py --check-only \
  --name {name} --results results.json [--b-results b-results.json]
```

| 校验 | CLI |
|------|-----|
| 数据完整性 + 补总数（内存回填，不写 HTML） | `build-final-report.py --validate-only --yaml …` |
| 用例区 A/B/调用/标签对账 | 同上，加 `--cases` |
| 已有最终报告自检 | 同上，加 `--html`（报告已存在时） |
| 原文回复自检 | `build-testcases-html.py --check-only` |

`--validate-only` / `--check-only` 失败以 exit 2 阻断；成功不写任何 HTML。出 HTML 仍由 eval 在闸门通过之后执行。

## 编排顺序

1. 读 `assets/knowledge-base/index.yaml`，用已沉淀的漏项模式与金标做对照（自动成长的读侧）。
2. 跑上面两条 CLI。
3. 有漏 → 按 eval Step 5.4 回填（只补证据不编造）；原文非原文 → 从会话归档逐字改回后再跑 CLI。
4. 全过 → 放行；补不回 → 阻断并列漏项。
5. 放行/回填成功后 → 执行自动成长（`references/distillation-rules.md`）。
6. 若交付 Excel / 报告清单：先读 `references/html-delivery.md`。eval 尚未生成最终 HTML 时，本步只准备入口，不代替 eval 出报告。

## 边界

- 出题、三轮执行、打分、生成 HTML → eval 负责，本 skill 不越权。
- 改 skill 正文 → opt；目录结构 → doctor。
- 本 skill 只新增「自动成长」，不新增第二套核对清单或第二份字段表。
