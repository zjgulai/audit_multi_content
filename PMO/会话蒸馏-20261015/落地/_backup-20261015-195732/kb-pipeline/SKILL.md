---
name: kb-pipeline
description: |
  Momcozy 内容治理知识库的**供给链入口**：按 `kb/l7/registry/layers.yaml` 把 L0 → L7
  整条链路编排跑一遍（对齐源层 → 抽取 → 切分 → 蒸馏 → 发号 → P0 → 索引 → 报告），
  **每到达一层就调用该层的 skill**（`layers.yaml` 每层的 `skill:` 字段），
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
version: "1.1.1"
last_updated: "2026-10-15"
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

**一句话**：本 skill 是**供给链**的入口。它只干一件事：**照 `layers.yaml` 把链路走完** ——
而"走"的方式是**逐层调用该层的 skill**：编排在本 skill，执行在该层 skill。
评审链（内容能不能用）走 `kb-review`，两者不重叠。

## 0. 两条红线

1. **不猜链路**：每一层的依赖、引擎、输入输出、幂等键、闸门、**以及该调哪个 skill**，全部以
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
cd "<本次库根>"                  # ★ cwd 必须是本次库根（29 个 l8 脚本用 "kb/..." 相对路径）
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

| 层 | **调用的 skill**（`layers.yaml` → `skill:`） | 该 skill 内部跑的引擎（读本层 `engine`） | 写档 |
|---|---|---|---|
| L0 | `kb-l0-feishu` | `kb/l8/align_l0_feishu.py` · `align_l0_schema.py` · `reconcile_l0_feishu.py` · `emit_l0_manifest_reconcile.py` | ✅ |
| L1 | `kb-ingest-extractor` → `kb-media-extractor`（**两个，按序**） | 读本层 `engine`（**不在此列清单** —— 契约 #4） | ✅ |
| L2 | `kb-ingest-extractor` | `kb/l8/l2_split_run.py RUN [--apply]` | ✅ |
| L3 | `kb-clause-extractor` | 读本层 `engine`（**不在此列清单**） | ✅（跑前必归档 `rejected.jsonl`） |
| L4 | `kb-canonical-lookup` | `kb/.work/l4_article.py RUN` · `l4_integrity.py` · `l4_report.py` | ✅（写档三条件，见 §2.5） |
| L5 | `kb-p0-check` | 读本层 `engine`（**不在此列清单**） | 读 `layers.yaml` 的 `skill_write`（唯一真源） |
| L6 | `kb-recall` | 读本层 `engine`（**不在此列清单**） | 读 `layers.yaml` 的 `skill_write`（唯一真源） |
| L7 | `kb-check`（跨层闸门，非层主） | `kb/l7/scripts/skills_check.py` · `kb/l8/workflow_check.py RUN` | 只读 |

> 本表**不列干跑档**：每层的 `write_mode` / `dry_run` / 逐脚本干跑档事实只在
> `kb/l7/registry/layers.yaml` 声明（唯一真源），见 §3。
> **"调哪个 skill"也以那张表为准**（`skill:` / `skill_write:` / `skill_note:`）——
> 本表只是把它读给人看；两处不一致时以 `layers.yaml` 为准，
> 由 `kb/l7/scripts/skill_conformance.py` 的 C7 逐层对账。

## 2.5 逐层调用契约（2026-09-30 起）

**循环（八层一层不跳）**：

```
读 layers.yaml 本层 skill:  →  用 skill 工具加载它  →  由它按本层 engine 执行本层
→  回 kb_pipeline.py 过本层闸门 + 记账  →  下一层
```

> **2026-10-01 更正**：上面这段此前只是**意图**，执行体只做到一半 ——
> `kb_pipeline.py --via-skill` 当时**只打印**「本层该调的 skill ＝ X」然后 `continue`
> （不起 subagent、不加载 skill、不落章）。后果是 `skill_invocation_audit.py` 的
> **E2 逐层无落章**恒定判红：声明念了一遍，调用一次也没发生。
> 契约 #5 因此从"意图描述"改成下面这条**可执行的驱动循环**。

| # | 契约 | 为什么 |
|---|---|---|
| 1 | **随调用传三件**：`RUN=<YYYYMMDD-HHMM>`、库根（`kb/` 的上一级）、**只跑本层** | 层 skill 默认是按人提问干活的；不传这三件它不知道自己现在在链路里 |
| 2 | **限档**：调 `kb-l0-feishu` 只许 `--check` / `--sync`，**禁 `--full`**（该档会越层重跑 L1→L2→L3 与 L6）；调 `kb-ingest-extractor` 在 L1 只做抽取、**不许跑 `l2_split_run.py`** | 越层执行 = 与"每层调该层 skill"重复跑同一层 |
| 3 | **禁回头**：层 skill 在链路里**不许再调 `kb-pipeline`** | 层 skill 正文都写着"整链 → kb-pipeline"，在链路里那是出边；回头即递归 |
| 4 | **引擎清单不复制**：层 skill 跑哪几个脚本，读 `layers.yaml` 本层 `engine` | 同一事实写两处，第二处必然过期（本库已因此返工三次） |
| 5 | **每层都由「能加载 skill 的执行者」执行**（不只是"重层"）：**skill 必须逐层用 skill 工具真加载进上下文**；**不要求一层一个 subagent** —— 一次执行里顺序跑完多层同样算（判据 = 层侧落章 + 记账，**不看会话粒度**；2026-10-05 澄清）；带**无进展超时**（默认 15 分钟，complex 放宽 25 分钟），以**磁盘落盘**为进度真源。执行体 = 下面的**驱动循环**，未走完循环不算调过 | 照 root-skills 家族的批量口径（`root-skills-batch-driver`；`root-skills-eval` 第 204 行的"无进展超时 + 看落盘、禁止无限等完成通知"）。"把 SKILL.md 加载进上下文"这件事**只在会话里有痕迹**，所以循环第 3–5 步必须为它留证 |
| 6 | **交接走磁盘**：层与层之间只通过 `kb/<layer>/runs/<RUN>*.json` 与各层台账交接，不靠上下文记忆 | 与 root-skills 家族一致：跨 skill 传参走产物，不走内存 |
| 7 | **写档三条件**（对 `skill_write: true` 的层）：① 由 kb-pipeline 以层身份调用 ② `--apply` ③ **人开闸** | 层 skill 的写档不是给用户直接触发的入口；缺任一条只许走查询档 |

### 驱动循环（可执行 —— 契约 #5 的执行体）

对**每一层 Lx**（拓扑序，一层不跳）：

1. **先过闸门**（本步**不跑层引擎**、**不记账**）：
   ```bash
   kb/kbpy l7/scripts/kb_pipeline.py --sync --via-skill --only Lx --gate-only --run <RUN>
   ```
   **为什么要 `--gate-only`**（2026-10-01 实测）：本循环对一个 RUN 会调编排器两次
   （第 1 步过闸门、第 5 步带上报），两次都记账的话 `kb/l7/runs/index.jsonl` 一个 RUN 落 **2 行**
   （`registry_echo` + `agent_reported`）→ 统计"跑了几层/几次"**系统性双计**，而且
   `kb/l7/runs/<RUN>.json` 被后者覆盖、前者只剩 index 里一行。
   实测：`RUN=20261001-1121` 在 index 里就是 2 行（11:20:45 / 11:21:29）。
   加 `--gate-only` 后一个 RUN 只剩 **1 行、且是最终态**。该开关与 `--apply` / `--invoked` /
   `--skill-session` 互斥（传了会被丢掉，故拒收、不静默）。
2. **读 Lx 的 skill**：从 `kb/l7/registry/layers.yaml` 的 `Lx.skill:` 现读（**不许抄进本文件** —— 契约 #4；
   也不许在脚本里硬编码）。**L1 声明两个**（`kb-ingest-extractor` → `kb-media-extractor`）时：
   **按序把两个都加载进上下文**（同一 subagent 连续加载、或分两个 subagent 都可以），
   并且**落章要带齐本层声明的两个 skill id** —— L1 的落章引擎（见 `layers.yaml` 的 `L1.engine` 末条）
   其 `--skill` 可**重复给出**，多值时写成列表（如 `skill: ["kb-ingest-extractor","kb-media-extractor"]`）。
   **只写一个会被 `skill_invocation_audit.py` 的 E3 判「落章与声明不符」**（2026-10-01 实测）。
3. **在执行者会话里跑本层**（一次执行可顺序跑完多层；**skill 仍须逐层真加载**），task 里必须写清**六件事**：
   ① 用 **skill 工具把 `<skill-id>` 加载进上下文再执行** —— 这是"逐层调用"的本体，不是"打印一句该调谁"；
   ② 按 `layers.yaml` 的 `Lx.engine` 执行本层（引擎清单现读，不抄）；
   ③ `RUN=<RUN>`；库根 = `kb/` 的上一级（先 `cd` 到那里再跑）；**只跑 Lx**；
   ④ **越层禁止**（契约 #2）、**不许回头调 kb-pipeline**（契约 #3）；
   ⑤ 跑完把 `skill=<skill-id>` **落章**进 `kb/lx/runs/<RUN>*.json` —— 落章由**执行本层的那个进程**写
      （如 L2：`kb/kbpy l8/l2_split_run.py <RUN> --skill <skill-id>`），
      **宿主编排会话与编排器都不得代它写**（代写就是 `registry_echo`：该字段结构上不可能为假，不能当证据）；
   ⑥ 会话标识带上层与 skill（如 `kb-layer-L2-kb-ingest-extractor`），并把会话 id 报回编排器。
4. **以磁盘落盘为完成判据**：`kb/lx/runs/<RUN>*` 出现且带 `skill` 字段 → 本层完成；
   没出现就按无进展超时处置（默认 15 分钟，complex 放宽 25 分钟），**禁止无限等"完成通知"**。
5. **落章验过 → 记账带上报**（这一步才让 `skill_evidence` 从 `registry_echo` 变成 `agent_reported`）：
   ```bash
   kb/kbpy l7/scripts/kb_pipeline.py --sync --via-skill --only Lx --run <RUN> \
       --invoked <skill-id> --skill-session Lx=<会话标识>
   ```
   本步是这一个 RUN **唯一**一次记账（第 1 步已 `--gate-only` 让位），落的就是最终态；
   `kb/l7/runs/index.jsonl` 里这个 RUN 因此**只有 1 行**。

   > **★ 事实更正（2026-10-01，批次6 实测）**：上面这句**只在「一个 RUN 一层」时成立**。
   > **多层 RUN 上不成立** —— 循环对每层都走一次第 5 步，于是：
   > · `kb/l7/runs/index.jsonl` 会落 **N 行**（一层一行）；
   > · `kb/l7/runs/<RUN>.json` 是**单文件、被最后一层覆盖**，只剩最后一层的
   >   `extra.layers` / `skill_sessions`。
   > **实测**：`RUN=20261001-1650` 跑了 L3→L4→L5→L6 四层 ⇒ `index.jsonl` **4 行**
   > （16:52:04 / 16:54:57 / 16:57:50 / 19:24:18），`<RUN>.json` 只剩 L6。
   > **后果（重要）**：`skill_invocation_audit.py --run <RUN>` 的绿**只覆盖最后一层** ——
   > 该 RUN 实测自报「① 本 run 涉及 **1 层：L6**」，**E2/E3 只核了 4 层里的 1 层**。
   > ⇒ 多层 RUN 上，这条审计**不足以**证明四层都调过 skill。
   > **现在靠人核补足**：逐层读层侧落章原件
   > `kb/l{3,4,5,6}/runs/<RUN>.json`，核每份的顶层 `skill` 是否等于 `layers.yaml` 本层 `skill:`、
   > 且 `applied=true`（**不新造闸门脚本** —— 见上文「不许为它新建闸门脚本」）。
   > 记账逻辑的改法（一次记账覆盖多层 / index 按层分文件）**不在本批**，要单独一批。
6. **下一层**（回到第 1 步）。

**本循环的两条验收（缺一不算做完 —— 只过第 1 条就是"尺子绿了、目标没到"）**：

```bash
# ① 机器判据：三方一致（声明 = 记账 = 落章）
kb/kbpy l7/scripts/skill_invocation_audit.py --run <RUN>        # 期望：红 0，退出码 0
# ② 加载留痕：extra.skill_sessions 给出执行该层的会话标识（人核）
python3 -c "import json;print(json.load(open('kb/l7/runs/<RUN>.json'))['extra']['skill_sessions'])"
```

⚠️ ① 只能证明「该层引擎被跑过 + 落章注明了执行者」，**证明不了**「agent 真把 SKILL.md 加载进了上下文」
（E1 核的是上报、E2 核的是层侧落章，落章的 skill 值本身是调用者从表里读出来传进去的）。
所以 ② 不是可选加分项：打开那个会话，看**会话产物里确实有加载该 skill / 读 SKILL.md 的动作** ——
不接受"我加载了"这句话本身。② **人核即可，不许为它新建闸门脚本**（不造第 7 把尺子）。

⚠️ **还要看 ① 的黄里有没有 E5**（2026-10-01 加）：「落章来自预演」是**黄**，不是红 ——
含义是**这条绿只证明「逐层调用机制通了」，不是「该层真落盘过」**（判据原先不读 `dry_run`/`applied`，
预演台账一样能让 E2 变绿）。要"落盘证据"就得真带 `--apply` 跑该层，那时 E5 才会消失。
**E5 不许改成红**：红 = 不算数，黄 = 需人裁；做成红等于拿错误的尺子量对的流程（机制验证会永远红）。

**执行侧开关**：`kb/kbpy l7/scripts/kb_pipeline.py --sync --via-skill [--only Lx] [--apply]
[--gate-only] [--invoked <skill-id>]… [--skill-session Lx=<会话标识>]…`
—— 该模式下**编排器不跑层引擎**（引擎归层 skill），只跑闸门 + 锁 + 记账；
`--gate-only` = 驱动循环第 1 步专用：只过闸门 + 持锁/释放，**不写 `kb/l7/runs/`**（免得一个 RUN 双计）；
`--invoked` = 本跑**实际加载过**的层 skill（不传 → `skill_evidence=registry_echo`，证据闸门判它不算数）；
`--skill-session` = 执行该层的会话标识，写进 `extra.skill_sessions`（**它不是落章**）。
默认关，不带 `--via-skill` 时行为与旧版一致。

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
kb/kbpy l7/scripts/skill_conformance.py # C7：层 ↔ skill 双向对账（本轮新增）
```

**"层已跑完"的合格结论长这样**：
`L2 于 2026-09-29 18:0x 由 RUN=20260929-1800 跑完，幂等键 (resource_id, source_sha256, splitter_version) 覆盖 10650 行，闸门=l2/registry 一致性，未发现并发写入。`
—— 没有 run_id 和时间戳的"跑完了"，不算结论。

**逐层调 skill 的模式下还要多一句**：`本层由 <skill-id> 执行`（run 记录里的 `skills` 字段）——
没写 skill id 的"层跑完了"，答不出"这一跑用了哪些 skill"。

## 5. 交付物

1. `kb/<layer>/runs/<RUN>-*.json`：逐层运行记录（存原始数据，不转述）。
2. **一段链路结论，固定四段**：① 本次跑了哪几层、跳过了哪几层（附幂等键证据）
   ② 逐层闸门结果 ③ 失败项 + 原因码 + 要人做什么 ④ 是否存在并发写入者。
3. **逐层 skill 调用清单**：`kb/l7/runs/<RUN>.json` 的 `skills` 字段（`--via-skill` 模式下由编排器写入）。
4. 变更记录（若改了 `layers.yaml`）：`kb/l7/reports/<RUN>-change-record.md`。

## 6. 何时停下来问人

- 要跑**新出现的**、还没有干跑档的写盘脚本（现有 8 个会改库数据的脚本均已补齐，见 §3）。
- **要写 `skill_write: false` 的层**（L5 / L6 / L7）：那三层的写档是显式登记的缺口，
  要么走旧口径的脚本兜底，要么先把该层 skill 档位化 —— 别让层 skill 去写它正文里写着"不调"的引擎。
- `kb/.work/.kb.lock` 存在，或 `kb/.work` 近 30 分钟有大量写入 → 可能有另一批在跑。
- 闸门红了但原因不明 → 只读取证，**不要先写**；要修走 `kb-repair`。
- 触发了 `kb/l0…l6` 数据或台账的写入 → 不在本 skill 授权范围内，先停。
---

## 会话蒸馏回灌（2026-10-15）

本 skill 的知识面由**会话蒸馏**持续回灌，两个文件：

- `references/会话蒸馏回灌.md` —— 从 2026-10-05~10-15 的 DSH 会话里蒸出来的
  **可执行动作 / 禁止动作 / 风险点**，每条都带**可回源的依据指针**（`case_id` + `会话:seq` + 逐字引文）。
- `references/自生长台账.md` —— 每轮长了什么、回验过没过、闸门结果。

**怎么用**：

- 处理相关任务**之前**先读这两个文件 —— 里面是别人真踩过的形状，不是通用建议。
- 它们**不修改本 skill 的任何指令**：**与上文任何一条冲突时，以上文为准**。
- 里面的条目是 **E2（草稿级、可审查、未获批）**，不是已批准的规则；要拿它下结论前先看它的依据指针。

**它怎么长**：每日 04:10 由 `com.kb.skill-growth` 自动**追加**（只追加、不改已有行）。
护栏写在 `kb/l7/registry/skill-growth.yaml`：frontmatter / 触发词 / 正文**机器一律不许改**，
每条指针必须逐字回源，一条不过整轮不写，写完必须过 `skills_check.py` 第 3 类否则回滚。
