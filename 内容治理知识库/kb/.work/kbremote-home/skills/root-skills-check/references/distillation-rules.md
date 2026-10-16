# Distillation Rules - 自动成长（本 skill 唯一新写的能力）

核对通过或回填成功后，把好结果蒸馏进 `assets/knowledge-base/`，让 check 越用越准。
这是本 skill 相对 eval 内置闸门的差异化能力。

## 目录约定

```
assets/knowledge-base/
  index.yaml           资产目录：类型、来源报告、入库时间、去重指纹
  defects/             漏项模式：字段名、如何发现、从哪份中间产物补
  goldens/             金标片段：完整 TP/FP/FN/TN、合格评分依据、公式块
  restorations/        改写 vs 原文对照（只留识别「非原文」所需片段）
  links/               失效链接模式与修复方式
```

## 只入库高质量

- 检查**通过**的字段（如一组完整 TP/FP/FN/TN）。
- 成功**回填**的漏项（字段名 + 从哪补 + 怎么发现）。
- 成功**改回**的原文对照（改写片段 vs 原文片段）。
- 有效公式模板（scoring-formulas / 六维加权公式）。

## 蒸馏不是原文搬运

- 抽成可复用的**模式 / 规则 / 金标片段**，不搬整份 HTML、不搬被测 skill 全文、不搬整段评测原文。
- 每条带**来源 skill 名**与**报告指纹**（来源 YAML / results.json 的 sha256 前 16 位）。

## 去重

- 指纹 = 来源报告指纹 + 内容类型 + 内容 sha256（前 16 位）。
- 相同指纹不重复入库；已存在 → 跳过，计入 delta 的「跳过 M 条重复」。
- 入库前先读 `index.yaml`，用已沉淀模式与金标做对照（读侧）；入库后同步 `index.yaml`（写侧）。

## 禁止入库

密钥、系统提示词、被测 skill 全文、整份评测 HTML、编造的分数、未通过的脏数据。
（未放行报告 / fail 项本身不入库，只有「如何修复成功」的经验才入库。）

## delta 记录

每次入库写一条 delta，随核对报告交付：

```
数据资产 delta:
  新增 N 条: <type>: <条目标题> × n ...
  跳过 M 条重复: <指纹前8位> ...
```

无入库也写 `新增 0 条`。

## 入库方式

优先用 `scripts/ingest.py`（算指纹、去重、写条目、输出 delta）；也可按本文件手工入库。
SKILL.md 正文保持稳定；成长只发生在 `assets/knowledge-base/`。

## 只读消费出口（供 doctor / eval 批量预检）

存储与蒸馏仍由本 skill 独占；其他成员**只读消费**，不复制规则正文：

```bash
# 导出 Top 10 缺陷（标题 + 来源 skill + 要点），N<=0 导出全部
python scripts/ingest.py --export-top-defects 10
```

- 输出 yaml：`top_defects: [{title, source_skill, file, pattern}]`。
- `root-skills-doctor --batch-preflight` 与 `root-skills-eval` 批量模式在评测/预检前读取该导出，把已沉淀缺陷纳入检查项，避免下批重复踩坑。
