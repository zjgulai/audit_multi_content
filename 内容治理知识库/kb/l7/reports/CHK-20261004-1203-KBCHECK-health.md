# 知识库体检表 · CHK-20261004-1203-KBCHECK

- **库根（cwd）**：`/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理`
- **RUN**：`CHK-20261004-1203-KBCHECK`｜**读数时点**：2026-10-04 12:03–12:07
- **档位**：体检档（`kb-check` skill 六道闸门）＋ 逐层总闸 ＋ 宿主尺子 `kb_check`
- **纪律**：本表**只报不改**。未加任何 `--apply` / `--write-gate`；未删锁、未删副本、未改任何判据。
  唯一写盘 = 门④ 的 `kb/l8/workflow_check_<RUN>.json`（无干跑档，已在跑前声明）＋本报告文件本身。
- **拿本表之前先知道三件事**（否则会把三种红混成一种）：
  1. **「知识库健康」不是一把尺子**。本表用了三把：六道闸门（skill 自带的跨层编排）、
     逐层总闸 `kb_pipeline.py --check`（12 道只读闸门）、宿主尺子 `kb_check`（健康分 + 错误码）。
     三把的判据不同，**读数不同不矛盾**，但**不能互相替代**。
  2. **宿主尺子判「不通过」的原因不是分数低**：健康分 **79.2 ≥ 熔断线 60（未熔断）**，
     `ok = (错误数 == 0) && !熔断`（`~/.dsh/plugins/dsh-kb/lib/index.js:649` 实测该表达式）
     ⇒ 判失败的直接原因是 **454 个 `E026` 非空**；**孤岛率 0.94 不参与这条判定**（alerts 不进 `ok`）。
     「79.2 所以还行」与「孤岛率超标所以判失败」两种说法都不成立。
  3. **并发背景**：本表读数时点，近 30 分钟内 `kb/` 有 **59** 个文件被写（会话外写入者：
     批量评测/修复那一路，`_eval-L0L7-gap-20261003/batch-progress.json` 当时仍 `running`）。
     `kb/.work/.kb.lock` 当时**不存在**。⇒ 本表是**时点快照**，不是稳定态。

---

## 1. 体检表（闸门 → 退出码 → 结论 → 证据）

| # | 闸门 | 命令（cwd = 库根） | 退出码 | 结论 | 证据 |
|---|---|---|---|---|---|
| ① | 登记表自检 | `sh kb/kbpy l7/scripts/skills_check.py` | **0** | ✅ 过 | 五类问题全 0（应装未装 0 / 装了没登记 0 / 副本不一致 0 / 依赖缺失 0 / 自测缺失 0）；本项目要用 40 个、已装 40 个 |
| ② | 层契约 | `sh kb/kbpy l7/scripts/layers_check.py` | **0** | ✅ 过 | 8 层齐、cwd/python/envelope 齐、引擎路径存在、DAG 非线形；六类问题合计 0 |
| ③ | 路由表对账 | `sh kb/kbpy l7/scripts/routes_reconcile.py kb/l7/reports/<RUN>-routes-winners.json` | **2** | ⚪ 判据缺陷（**缺输入**） | `kb/l7/reports/` 下无任何 `*routes-winners*` 文件；赢家表是**触发评测的运行时产物、全库无生成者** ⇒ 缺输入 exit 2，**不是**「65 条全不一致」 |
| ④ | 链路收口 | `sh kb/kbpy l8/workflow_check.py CHK-20261004-1203-KBCHECK` | **1** | 🟡 **混合**：②③ 合法变红 ＋ ⑥ 真坏；其余 6 段 PASS | 9 段 PASS 6 / FAIL 3（② 权威库未被改动、③ 前序产物哈希 45 项、⑥ 文档可见性）；产物 `kb/l8/workflow_check_CHK-20261004-1203-KBCHECK.json`；裁决 `FAIL` |
| ⑤a | 信封闸门（默认范围） | `python3 tools/envelope_gate.py` | **0** | ✅ 过 | 扫 1985 个 `.py/.txt/.md`：信封态 **0**、读不到 0、两读者一致 |
| ⑤a′ | 信封闸门（**全工作区**，判据读者=消费方） | `python3 tools/envelope_gate.py --reader consumer .` | **1** | 🔴 **真坏（2 只）** | 扫 2893 个文件｜信封态 **2**（`|Δ| = 4096`）｜两读者**不一致 ⇒ 报红**（PATH 读者只判出 0 ⇒ 用 PATH 读者会得**假绿**） |
| ⑤b | 信封普查（库自带，只扫 `.md`） | `sh kb/kbpy l8/envelope_census.py` | **0** | ✅ 过 | 扫 10394 个 `.md`，1079 个 node 侧读不到**全部已分类**（569 刻意归档 ＋ 510 可再生备份）；活路径 0 |
| ⑥ | 投影一致性 | `sh kb/kbpy l8/projection_reconcile.py` | **1** | 🔴 **真坏（3/6）** | ❌R1 `source_sha256`｜❌R2 509 条条目指纹｜❌R4 2036 处治理字段未传导；✅R3/R5/R6 |
| ⑦ | 逐层总闸（**加跑**） | `sh kb/kbpy l7/scripts/kb_pipeline.py --check` | **1** | 🔴 **有问题（1 条）** | 8 层里 7 层闸门通过；**L0 闸门未过 exit=1**；零写自证 ✅（4001 个产物 mtime 变化 0） |
| ⑧ | 宿主尺子（**加跑**） | `kb_check`（宿主工具） | — | ❌ **不通过** | 健康分 **79.2**（熔断线 60，**未熔断**）｜错误 **454×E026**（唯一让 `ok=false` 的东西）｜告警 2218×W020 ＋ 10×W021｜提示 1×H005 |

### 1.1 门④ 第 ②③ 段为什么是「合法变红」而不是数据坏

- ② 段：`l0/l1/l2` 三棵树**全部** `match_L5_baseline = true`（files 4007 / 3152 / 887）
  ⇒ 漂移**只在 L3**（`l3_lines = 1018`、`l3_base1018_matches_L6 = false`、`l3_whole1527_matches_L4 = false`）。
  判据代码把哈希写死在**已过去的时点**（1018 行时代 vs 1527 行时代），活库结构上不可能相等。
- ③ 段：`checked 45 / mismatch 20`。其中 **17/20** 有 run 记录记过现 sha（含并发那一路
  `RT-20261004-LISTING-L{4,5,6}` @ 10:07–10:13），**3/20 无落章**。
- 两段均**逐字段相同**于 `kb/l7/registry/workflow-check-known-drift.yaml` 的登记（该文件自述
  「**今天没有任何闸门读本文件**」⇒ 登记**不给豁免**，复跑必然 FAIL）。这是第 8 次以上独立复现。
- ⇒ 按 `kb-check` skill §4 口径：**合法变红（基线漂移，非缺陷）**，**不许**为了让它们变绿去改历史
  run 记录的 sha、也不许把 L3 回滚到 1527 行。

### 1.2 门④ 第 ⑥ 段 + 门⑤a′ 是**同一件真坏**（2 只信封态 `.md`）

| 文件 | python `getsize`（真值） | 消费方 node `statSync` | 差 | mtime |
|---|---|---|---|---|
| `_eval-L0L7-gap-20261003/kb-check-fix/SKILL.md` | 7744 | 11840 | −4096 | **11:53** |
| `_eval-L0L7-gap-20261003/kb-l0-feishu-fix/SKILL.md` | 17351 | 21447 | −4096 | **11:47** |

- 两处**互相独立**命中：门⑤a′ 判 `|Δ|=4096` 报红；门④第⑥段 `buckets = {'其他': 2, '他人产物 hostlib': 510}`。
- **不在知识库装载位**：门④第⑤段装载位读数 `509 条 / 信封 0 / E001 None / E046 None`（`kb/view` 零信封）。
  受害的是这两份**交付副本**。
- **是复发**：11:33 的 `kb-repair` 单（`kb-repair-修复记录-20261004-1133-信封态.md`）修过同一批文件，
  之后 **11:47 / 11:53 又被并发那一路写回信封态**（写者用 python 通道落 `.md` ⇒ 4096 字节尾块）。

### 1.3 宿主尺子 79.2 的构成（按 `lib/kb.js` 复算，非工具自报）

| 维度 | 值 | 阈值 | 进分方式 | 得分 |
|---|---|---|---|---|
| 新鲜度 | 1.00 | ≥ 0.9 | 值 | 1.0000 |
| 三件套完整率 | 1.00 | == 1.0 | 值 | 1.0000 |
| 一致性 | 1.00 | ≥ 0.95 | 值 | 1.0000 |
| **孤岛率** | **0.9411** | ≤ 0.2 | **1 − 值** | **0.0589** |
| 覆盖率 | 0.9211 | ≥ 0.8 | 值 | 0.9211 |
| 利用率 | 0.2283 | ≤ 0.3 | 1 − 值 | 0.7717 |
| 幻觉率 | 无数据 | ≤ 0.1 | 样本不足，**不进分母** | — |

6 项均值 = **79.19 → 79.2**（复算相符）。⇒ **孤岛率一项就吃掉约 15.7 分**：
若孤岛率降到阈值 0.2，同口径健康分 ≈ **91.5**。

### 1.4 E026 ×454 的形态（复算，用于判「系统性」还是「零散坏条目」）

- 命中范围：**全部**在 `3_措辞表达库/L1-facts/`，**454/509 条**（89.2%）低于 60 线。
- 总分分布**极窄**：中位 55.8、均值 56.0、最低 52.5、最高 59.9。
- 子项均值：长度 **2.2/20**｜密度 13.5/30｜去重 **20.0/20（全部满分）**｜语言 20.2/30。
- 判据（`lib/kb.js:708-712`）：`长度分 = min(20, n/500)`，`n` = 被评正文长度。
  长度分 2.2 ⇒ n ≈ 1100 字；本库条目正文长度中位 **1049** 字。
- **复算结论**：在密度/语言维持现状的前提下，单条正文要 **≥ ~3150 字**才能过 60 线。
  中位 1049 字 ⇒ **结构性过不了**，不是零散坏条目。

---

## 2. 失败项清单（对象 + 原因码 + 要人做什么 + 复开条件）

> 口径：**`owner` 与 `reopen_when` 一律取自 `kb/l7/registry/failure-playbook.yaml`（唯一真源）**；
> 该文件**没有登记**的项，本表**明写 `NO_PLAYBOOK_ENTRY`**，owner 栏标为「（本表建议，非登记）」——
> 按 playbook 自己的纪律：「连兜底都没有，就说『没有登记的处置办法』——**不许现编**」。

| # | 对象 | 原因码 | 要人做什么 | 复开条件 |
|---|---|---|---|---|
| F1 | L0 闸门 / 飞书两张表（`tbl8AI00JZO1iZtp` 专家修订汇总表、`tblVdl0jdK9G4ld3` 内容公式） | `gate_red.L0`（**已登记**） | owner **内容治理数据组（刘华丽）**：先 `lark-cli auth status --profile dsh-kb` 把「bot 那条路」与「回落身份」**分开**（2026-10-04 实测是「两者同时不可用」那一种），再决定修法；读 `l0-expected-diffs.yaml` 的 `resolved[EX-2/EX-3]`。**禁止**把 `pull_failed` 写进 `expected` 去「声明掉」 | `l0_gate.py` 退出 0 |
| F2 | 门④ 第 ②③ 段（`l0~l6` 树哈希 / 前序产物 45 项中的 17 项） | `BASELINE_DRIFT`（**已登记**，判据过期） | owner **维护 `kb/l7/registry` 的人（判定）＋ 各层层主（数据面）**：本轮**只做登记**，结论写「基线漂移，非缺陷」并附原始读数。要它们转绿必须**改判据、单独走一轮**。**禁止**改写历史 run 记录的 sha 或回滚 L3 | 改判据后复跑 `exit 0`；或本轮**只登记** ⇒ 结论写「基线漂移，非缺陷」 |
| F3 | `kb/l7/registry/l7.json`（③ 段 20 项里**唯一被认定为真发现**的那一项） | `NO_RUN_STAMP`（原地改写未落章） | owner 同上（`gate_red.workflow_check` 条目明文）：**开闸后**跑 `kb/.work/l7_article_source_refresh.py <RUN> --apply`，并**补一条 L7 run 记录**。注意该项**不在写档白名单**内 | ③ 段该项的现 sha 有 run 落章可查 |
| F4 | `_eval-L0L7-gap-20261003/kb-check-fix/SKILL.md`、`.../kb-l0-feishu-fix/SKILL.md` | `ENVELOPE_STATE_NEW`（🔴 本轮复发） | 由**产生它的那一路**（批量评测/修复）用 `node`／`/bin/cp` 通道重写这两份；或交 `kb-repair` 处置。**不是知识库本体问题，别去动 `kb/l0…l7`** | `envelope_gate.py --reader consumer .` 信封态 **0**，且门④第⑥段 `其他` 桶 **0** |
| F5 | 投影 `kb/view` ⇄ 权威分层库（R1 / R2 / R4） | `PROJECTION_DRIFT`（**已登记**） | owner **内容治理数据组（刘华丽）＋ L3 层主（判定）**；`kb-repair` 只做分类与登记。★**不要**按脚本自带 `fix` 提示去重生成视图——playbook 实测它**修不了 R4**（L3 四字段现为空，判据等价于要求留空），且**会造假绿**（把逐条治理值降级为统一常量并归零有效期时钟） | `projection_reconcile.py` 退出 0（R1/R2/R4 同时绿） |
| F6 | `kb/l3/candidates/rules.jsonl` 的 `owner / half_life_days / valid_until / effective_from`（R4 的**根因**） | `finding.l3_governance_backfill_lost`（**已登记**） | owner **L3 层主（数据面）＋ 维护 registry 的人（登记面）**：**先报批**（`kb-repair` 无权直接改 `kb/l0…l6`）→ `fix_f7_backfill.py` → `fix_f7_verify_c4.py` → **补 L3 run 记录**（本次丢失正是「改了没落章」）→ 重出视图 → 复跑闸门。本轮实测现状：`half_life_days` / `valid_until` **键都不存在**（0 行），`owner` / `effective_from` 键存在但**非空 0/1018** | `fix_f7_probe.py` 显示四字段 **509/509 非空**，且 `projection_reconcile.py` 退出 0 |
| F7 | 门③ 缺输入（赢家表） | `MISSING_INPUT`（**已登记**为判据设计） | 交 **`kb-manage`／人**：按触发电测重生成 `<RUN>-routes-winners.json`（65 题 × 3 轮）放进 `kb/l7/reports/`。**不许**伪造赢家表充数 | 文件存在且格式可解析 ⇒ 复跑门③ 得 `exit 0` |
| F8 | 宿主尺子的 **454×E026**（**判「不通过」的那把尺子**） | `E026` ＋ **`NO_PLAYBOOK_ENTRY`** | ⚠ **库内既没有 owner、也没有 `reopen_when`、也不进日报**（`failure-playbook.yaml` 329 行 28 个 entry 里 `E026` **零命中**，本轮复测；`daily_health.py` 只覆盖 L0–L7 逐层闸门）。⇒ **要分派必须先补登记**：由**维护 `kb/l7/registry` 的人 ＋ 知识库负责人**按 playbook 既有形状（`symptom/owner/do/command/forbidden/reopen_when`）补条目。业务侧另一件要人裁的：60 线 + `长度分 = n/500` 的口径是否适配本库**短条目**形态（见 §1.4 复算）| `failure-playbook.yaml` 出现对应 entry id，**且**有一条例行出口消费它（日报或某闸门） |
| F9 | 孤岛率 **0.94**（阈值 ≤ 0.2，超 4.7 倍） | `ISLAND_RATE` ＋ **`NO_PLAYBOOK_ENTRY`** | **不影响「不通过」判定**（alerts 不进 `ok`）。属**业务动作**：来源表提供**真实关联列**后重建 `complements` 边（实测现只有 **30/509** 条带任何 link 字段，且全是 `complements`）。**不许靠删条目降率**。**先由人裁定阈值/口径是否现实，再谈数据动作** | 孤岛率 ≤ 0.2（前提是口径先被裁定为现实） |
| F10 | `W020` ×2218 疑似重复 | `NEARDUP_SUSPECT` ＋ **`NO_PLAYBOOK_ENTRY`** | 工具自注「**机器只报疑似，判归人**」。要么合并（**新建 + `supersedes` 留痕，不许原地改写**），要么把两者分工写进 `summary` | 人裁后疑似项收敛 |
| F11 | `W021` ×10 疑似数值矛盾 | `NUMERIC_CONFLICT_SUSPECT` ＋ **`NO_PLAYBOOK_ENTRY`** | 同上，且工具明文「属数值冲突的走 `governance.yaml`，**不许自动裁决**」 | 人裁 |
| F12 | 验收契约 `content-governance-hostlib-20260923`（owner **刘华丽**） | `OWNER_ACCEPTANCE_INCOMPLETE` / `FINAL_RECEIPT_MISSING` / `DATASET_NOT_BUSINESS_AUTHORIZED` | 未达条件 **3/3**：`owner_acceptance(未建)` / `final_receipt(未建)` / `fixed_eval_set(missing)`；谓词 `no_duplication=false`（契约自己承认）。`status=draft`、`productionReady=false` 是**它确实还没达**，不是谦虚 | 三项条件建成且 `productionReady` 转 true |
| F13 | `_meta/index-status.yaml` 的 `index.status` | `H005`（**提示，不计缺口**） | 仍是 `candidate`（`version_key` 未声明）⇒ 检索排序**未经 UAT 复核**。别把未复核的排序当定稿 | 声明 `version_key` 并做 UAT 复核 |

---

## 3. 本表**看见不了**的东西（体检自身的盲点）

1. **两个 `mode 000` 目录整块不可读**：`_eval-kb-check-20261004`、`_eval-kb-check-独立核验-20261003`
   （`d---------`，`ls` 即 `Permission denied`）⇒ 「6289 个 md」这类盘点**不含**它们，
   里面的信封态/坏文件**任何闸门都看不见**。
2. **⑤a 默认范围不含 `_eval-*` / `_chk-run-*`**（结构性看不见 F4 那两只）——只有 ⑤a′ 全工作区口径才看得见。
3. **利用率维度会被体检自身污染**：覆盖率测量走同一个 `search()`（源码已用 `log:false` 挡），
   但任何**忘了带 `log:false`** 的调用都会把「体检跑了几次」当成「人问了什么」。
4. **`kb_pipeline.py --check` 的 L0 红是「飞书侧只读探测」的结果**，其读数随 bot/回落身份的可用性漂移；
   它不是数据坏，是**取数能力**坏。

## 4. 与最近两份体检表的关系（不为好看而修饰）

- `体检表-CHK-20261004-1158-六道闸门.md`（12:00）与 `kb/l7/reports/CHK-20261004-1159-HEALTH.md`（11:59）
  是我这次读数**之前 4 分钟**的同类产物。本轮 **逐项相同**：①②⑤a⑤b 过、③ exit 2、④ ②③⑥ 红、
  ⑥ 投影 3/6、宿主 `kb_check` 不通过 / 79.2 / E026×454 / W020×2218 / W021×10 / 孤岛率 0.94。
- ⇒ **两会话独立调用、读数一致 ⇒ 该读数可复现**；但也说明**同一个体检在被反复跑**，
  而 F8（判「不通过」的那把尺子**零登记**）与 F4（信封态**复发**）**两轮都没被处置**。
- 按 `kb-check` skill §8 的停用条件 1：六道闸门**全部迁入 CI** 且**连续两轮零失败** ⇒ 日常体检才该改由 CI 承接。
  现在离那条线还很远（本轮仍 4 项红）。

---

**结论**：体检**不通过**（三把尺子里 ④⑥⑦⑧ 四项红）。
其中 **F1/F3/F4/F5/F6/F7** 是**实质真坏且已登记 owner**，可以直接照本表分派；
**F8/F9/F10/F11** 是**判「不通过」的那把尺子本身没有处置登记** ——
**这几项现在分派不出去，得先补 `failure-playbook.yaml` 的登记，再谈分派**。
