---
name: kb-pipeline
description: |
  Momcozy 内容治理知识库的**供给链入口**：按 `kb/l7/registry/layers.yaml` 把 L0 → L7
  整条链路编排跑一遍（对齐源层 → 抽取 → 切分 → 蒸馏 → 发号 → P0 → 索引 → 报告），
  并在每层过闸门、按幂等键决定跳过还是重跑。
  当用户说「同步一下知识库 / 跑一遍知识库链路 / 知识库同步到最新 / 全链体检 /
  L0 到 L7 走一遍 / 知识库该更新了 / 把知识库更新到最新 / 整条链路走一遍 /
  全链路重建 / pipeline 跑一下」时使用。
  触发词：同步知识库、知识库同步、跑一遍知识库链路、知识库同步到最新、全链体检、
  L0 到 L7、整条链路、全链路重建、知识库该更新了、跑 pipeline、kb-pipeline。
  不适用（三条边界，各自点名）：
    · 只对账 L0、只看飞书侧改了什么、只跑每日同步 → 走 **kb-l0-feishu**（不跑下游）；
    · 单条内容能不能发 / 审一下 / 合规检查 → 走 **kb-review**（评审链，不是供给链）；
    · 查条款号 → 走 **kb-canonical-lookup**；是不是 P0 → 走 **kb-p0-check**；
      召回单元 / 查资料 → 走 **kb-recall**（这三个是只读查询，不重建索引）；
    · 只体检不跑链路 → 走 **kb-check**；闸门没过要修 → 走 **kb-repair**。
version: "1.0.0"
last_updated: 2026-09-29
license: "Proprietary — Momcozy internal use only"
complexity: "complex"
compatibility:
  claude: { status: "native" }
  kimi: { status: "native" }
  cursor: { status: "native" }
  gpt: { status: "bridge", limitations: ["长任务需分步"] }
  minimax: { status: "bridge", limitations: ["输出需压缩"] }
  dsh: { status: "native", notes: "kbpy + kb/.kb-python 同机可用" }
  codex: { status: "native" }
---

# kb-pipeline —— 知识库供给链入口（L0 → L7）

**一句话**：本 skill 是**供给链**的入口。它只干一件事：**照 `layers.yaml` 把链路走完**。
评审链（内容能不能用）走 `kb-review`，两者不重叠。

## 0. 两条红线

1. **不猜链路**：每一层的依赖、引擎、输入输出、幂等键、闸门，全部以
   `kb/l7/registry/layers.yaml` 为准。**改链路先改表，再改代码**。
2. **写操作只在 `--apply` 下**：带 `--apply` 的脚本先不带 `--apply` 跑一遍，拿到差异再决定。
   没有干跑档的脚本**一律不许"试跑"**——试跑就是真写盘。
   （截至 2026-09-30：会改库数据的 8 个脚本**均已有 `--apply` 干跑档**，逐条见 §3。）

## 1. 跑之前先答三个问题

| 问题 | 怎么看 |
|---|---|
| 现在在第几层、上一层跑完没有？ | 看**幂等键**，不看文件 mtime。每条"已跑完"结论都要带 **run_id + 时间戳** |
| 有别的写入者吗？ | 看 `kb/.work/.kb.lock`；`kb/l2/units.jsonl` **实测被别人写过**（10551 → 10650 行，本 agent 未写） |
| 解释器对不对？ | `kb/kbpy` （受管 python 缺 numpy / fastembed，L6 召回两者都要） |

```bash
cd ~/.dsh/Momcozy知识库        # ★ cwd 必须是 kb/ 的上一级（29 个 l8 脚本用 "kb/..." 相对路径）
kb/kbpy l8/_interp.py          # 报告解释器；不合格就报错退出，不静默降级
```

统一 run_id：`RUN=<YYYYMMDD-HHMM>`，所有产物挂在这个 RUN 下。

## 2. 链路（实测 DAG，**不是线性链**）

```
L0 ──┬─▶ L1 ──▶ L2 ──┬─▶ L3 ──┬─▶ L4
     │               │        ├─▶ L5
     │               │        └─▶ L6
     └───────────────┴─▶ L5   （L2 直接喂 P0）
                     └─▶ L6   （L2 直接喂索引）
```

- **L2 扇出到 L3 / L5 / L6**；**L3 扇出到 L4 / L5 / L6**。
- 所以 **L3 没跑完，不代表 L5 / L6 不能用**；**L2 跑完，L5 / L6 就可以先重建**。
- 完整字段（inputs / outputs / gate / write_mode / dry_run）逐层见 `layers.yaml`。

| 层 | 引擎 | 写模式 |
|---|---|---|
| L0 | `kb/l8/align_l0_feishu.py` · `align_l0_schema.py` · `reconcile_l0_feishu.py` · `emit_l0_manifest_reconcile.py` | 只读为主；写档 append |
| L1 | `kb/l8/extract_l1_new_resources.py RUN [--apply]` · `ocr_attachments.py` · `apply_ocr_to_l1.py` | append |
| L2 | `kb/l8/l2_split_run.py RUN [--apply]` | append |
| L3 | `kb/l8/l3_distill_run.py RUN` · `l3_reject_ledger_rebuild.py RUN [--apply]` | **overwrite_in_place_no_archive** ⚠️（实测**没有** `_archive`，跑前必须人工归档 `rejected.jsonl`） |
| L4 | `kb/.work/l4_article.py RUN` · `l4_integrity.py` · `l4_report.py` | append（发号） |
| L5 | `kb/.work/l5_prep.py RUN` → `l5_export.py RUN` · `l5_bench.py` | append |
| L6 | `kb/.work/l6_build.py RUN` · `l6_bench.py` | append（重建索引） |
| L7 | `kb/l7/scripts/skills_check.py` · `kb/l8/workflow_check.py RUN` | 只读 |

> 本表**不列干跑档**：每层的 `write_mode` / `dry_run` / 逐脚本干跑档事实只在
> `kb/l7/registry/layers.yaml` 声明（唯一真源），见 §3。

## 3. 干跑档状态

**判据不写在本节。** 逐层、逐脚本的干跑档事实（哪个脚本带 `--apply`、闸门位次是否早于第一个副作用）
**以 `kb/l7/registry/layers.yaml` 各层 `notes` 为唯一真源** —— 本文件与 `skills.yaml` 只引用、不复制。

> **2026-09-30 的教训（本节此前就是复制的受害者）**：本节原先照抄了一张「哪些脚本有 `--apply`」表，
> 与 `layers.yaml` 并存两份。结果是 `kb_pipeline.py` 按过期的那一份把 L3 判成「没有干跑档」，
> `--sync --all` 直接停在 L3，整链走不到 L4–L7。**同一事实写两处，第二处必然过期。**
> 已删表；要看逐脚本证据（含闸门位次的行号）请读 `layers.yaml` 对应层的 `notes`。

**`kb/l8/projection_reconcile.py` 是例外，不是缺口**：实测它是**只读对账器**
（只有 `--json` / `--json-out`，默认不写任何文件），因此**不需要**干跑档 —— 保留在
"只读复核"用途，不要给它加写参数。

**纪律不变**：① 不带 `--apply` 先跑一遍，拿差异再决定；② **新增脚本若没有干跑档，
一律不许"试跑"**（本库已发生过一次不可授权写入，溯源记录见
`kb/l2/runs/20260929-1754-l2-unscheduled-run.json`）。
`kb/l8/l2_split_run.py` 的 `--apply` 可作为**补干跑档的样板**。

## 4. 每层跑完的收口（不许只看文件状态）

```bash
kb/kbpy l8/workflow_check.py $RUN      # L7 收口核验
kb/kbpy l7/scripts/skills_check.py     # 登记表五类全 0
kb/kbpy l8/envelope_census.py          # 信封普查（只扫 .md）
```

**"层已跑完"的合格结论长这样**：
`L2 于 2026-09-29 18:0x 由 RUN=20260929-1800 跑完，幂等键 (resource_id, source_sha256, splitter_version) 覆盖 10650 行，闸门=l2/registry 一致性，未发现并发写入。`
—— 没有 run_id 和时间戳的"跑完了"，不算结论。

## 5. 交付物

1. `kb/<layer>/runs/<RUN>-*.json`：逐层运行记录（存原始数据，不转述）。
2. **一段链路结论，固定四段**：① 本次跑了哪几层、跳过了哪几层（附幂等键证据）
   ② 逐层闸门结果 ③ 失败项 + 原因码 + 要人做什么 ④ 是否存在并发写入者。
3. 变更记录（若改了 `layers.yaml`）：`kb/l7/reports/<RUN>-change-record.md`。

## 6. 何时停下来问人

- 要跑**新出现的**、还没有干跑档的写盘脚本（现有 8 个会改库数据的脚本均已补齐，见 §3）。
- `kb/.work/.kb.lock` 存在，或 `kb/.work` 近 30 分钟有大量写入 → 可能有另一批在跑。
- 闸门红了但原因不明 → 只读取证，**不要先写**；要修走 `kb-repair`。
- 触发了 `kb/l0…l6` 数据或台账的写入 → 不在本 skill 授权范围内，先停。
