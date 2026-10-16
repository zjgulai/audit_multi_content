# 反向对照：layers.yaml 的 inputs 补全（20261012-1437）

**被测改动**：`kb/l7/registry/layers.yaml` 各层 `inputs` 补全（L4 6→11 / L5 3→11 / L6 5→10 / L7 6→14，合计声明 **62** 条）。

**为什么测**：`inputs` 只被两处读 —— `kb_pipeline.py:1321`（存在性）与 `layers_check.py:44`（MANDATORY 字段）。
补全的唯一后果 = 让存在性检查覆盖更全。若它恒绿，则等于注释。

## 四步结果

| 步 | 动作 | 期望 | 实测 |
|---|---|---|---|
| ① | 基线 | 绿 | **exit 0**，硬问题：无 |
| ② | 移走 `kb/l3/registry/last_seen.json` | **精确变红** | **红**：`L5 输入缺失 1 个：['kb/l3/registry/last_seen.json']` |
| ③ | 逐字还原 | 回绿 | **exit 0**，硬问题：无 |
| ④ | 排除过滤是否承重 | 有诱饵 | 同名不同物诱饵 **25315** 个 |

② 的报错**同时点名了层（L5）与路径**，不是笼统"检查失败" ⇒ 尺子是有指向的。

## ④ 过滤承重（只读证法）

`inputs` 的排除模式 = `_backups|_archive|_skill-backups|/runs/|.bak`。
全库同名诱饵 **25315** 个，例如：

- 真身 `kb/l2/units.jsonl` ↔ 诱饵 `kb/l2/units.jsonl.bak-pre-t23-20261010-175559`
- 真身 `kb/l3/candidates/rules.jsonl` ↔ 诱饵 `kb/l3/_backups/pre-plevel-20261009-2010/rules.jsonl`
- 真身 `kb/l0/manifest.jsonl` ↔ 诱饵 `kb/l7/_backups/l0-sync-55-20261001/manifest.jsonl`

⇒ 若照单把历史引用补进 `inputs`，`--check` 会**永久红**（备份目录被清理即报缺失）。

## 本对照自身的坑（记一笔，防再犯）

用 `os.path.exists` 单口径自查时，曾把 **7 条**声明误报为"缺失"。真判据在
`kb_pipeline.py:1319-1328` 有三道我漏掉的守卫：`looks_like_path()`（散文行不查）、
`is_glob()+has_match()`（glob 须有匹配）、`strip_placeholder()`（`<sha256>` 模板先剥）。
**"我写的检查器报红" ≠ "真判据报红"** —— 报红前先读真判据的实现。

## 残留

**未覆盖**：本对照只证「输入**消失**」会红。**「输入内容变了」不会红**
（现无内容指纹消费者）—— 那属于异步拆分方案的范围，须单独报批。
