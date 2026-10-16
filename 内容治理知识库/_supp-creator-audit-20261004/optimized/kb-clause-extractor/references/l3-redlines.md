# L3 三条红线与归档事故复盘

> 读取条件：跑批前，或要跟人解释「为什么必须先归档」时读本文件。正文只留结论，细节在这里。

## 红线①：跑之前先归档

`kb/l8/l3_distill_run.py` 以 **`w` 模式**覆盖写 `kb/l3/rejected.jsonl`（写模式登记为
`overwrite_in_place_no_archive`）。所以「跑一遍蒸馏」这个动作**本身**就会吃掉上一版逐单元拒绝台账。

**跑批前的固定四步（顺序不能换）**

```bash
cd "<本次库根>"                               # cwd 必须是本次库根
RUN=$(date +%Y%m%d-%H%M)
mkdir -p kb/l3/_archive
/bin/cp kb/l3/rejected.jsonl kb/l3/_archive/rejected-pre-$RUN.jsonl   # ① 归档
shasum -a 256 kb/l3/_archive/rejected-pre-$RUN.jsonl kb/l3/rejected.jsonl  # ② 校验一致
kb/kbpy l8/l3_distill_run.py $RUN            # ③ 蒸馏（运行即落盘）
kb/kbpy l8/l3_reject_ledger_rebuild.py $RUN --apply   # ④ 台账重建
```

## 事故复盘：11,860 → 1,053

| 项 | 内容 |
|---|---|
| 现象 | 跑完一轮蒸馏后，逐单元拒绝台账从 **11,860 行**掉到 **1,053 行** |
| 原因 | 覆盖写模式，旧台账被原地截断；没有自动留底 |
| 后果 | 「我们试过、被谁拦、为什么」这段知识丢失；同一批素材会再被拒一遍而无人记得原因 |
| 可恢复性 | incident 记录为 `recoverable: false`；事故前 11,860 行仅存于 `kb/l3/runs/*.pre-snapshot.json`，**不是可直接复用的现台账** |
| 现行对策 | 归档做成红线（`kb-pipeline.py --sync` 的 `ARCHIVE_BEFORE_WRITE`）；蒸馏只许追加 |

**线上口径提醒**：现台账行数与历史事故前的 11,860 行**不同量纲**（现为逐单元级，事故前为资源级），
拿两个数直接比大小会得出错误结论 —— 这属已登记漂移，见 `kb/l7/registry/l3-known-drift.yaml`。

## 红线②：候选 ≠ 定稿

- `kb/l3/candidates/rules.jsonl` 里的行是 **`provisional` 候选**，`article_no` 一律为空。
- 定稿在 `kb/l4/canonical/*.jsonl`，条款号由 **L4** 分配（`numbering.issued` 台账，号永不复用）。
- 本层**不自造条款号**；把候选当定稿引用 = 引用越级。
- 发号是写操作，由 `kb-pipeline` 在 `--apply` 下编排 `kb/.work/l4_article.py` 执行。

## 红线③：证据逐条回指

每条候选的 `evidence_units[]` 必须能回指 L2 单元的三件套：

```
unit_id + source_sha256 + anchor
```

`kb/l7/scripts/l3_gate.py` 每天逐条核的就是这批引用（现库口径 **1,729 条**）。
回指不过 = 从 L3 点不回 L2 原文（单元不存在 / 指纹对不上 / 锚点漂了）。

## 只追加（A3）

蒸馏只**追加**行：既有候选行必须逐字节未变。判据是重跑后对旧行做逐字节比对，
不是比对行数 —— 行数相同也可能整段被重写过。

## 运行时依赖（原 frontmatter `compatibility` 的自由文本）

依赖库内引擎与闸门（不随本 skill 分发）：kb/kbpy、kb/l8/l3_distill_run.py、
kb/l8/l3_reject_ledger_rebuild.py、kb/l7/scripts/l3_gate.py、kb/l7/scripts/l7_gate.py；
运行时需要 kb/l3/ 写权限与 kb/l2/units.jsonl 只读权限。缺任一项时只出方案不出数。

## 正文原红线段（2026-10-04 由 SKILL.md §4 下沉，逐字保留）

**红线①（血泪）**：`l3_distill_run.py` 会以 `w` 模式覆盖 `kb/l3/rejected.jsonl`。
跑前必须把它复制到 `kb/l3/_archive/rejected-pre-<RUN>.jsonl` 并校验 sha256
（本库真的发生过：逐单元拒绝台账从 11,860 行掉到 1,053 行）。细则见 `references/l3-redlines.md`。

**红线②**：候选 ≠ 定稿。`kb/l3/candidates/rules.jsonl` 是候选；`kb/l4/canonical/*.jsonl` 才是定稿。
条款号由 **L4** 分配，本 skill **不自造条款号**。

**红线③**：证据逐条回指 —— 每条规则的 `evidence_units[]` 都要能回指 L2 单元的
`unit_id + source_sha256 + anchor`（`l3_gate.py` 每天逐条核的就是这批）。
