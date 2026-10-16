# 闸门修复交付单 · kb-repair · REPAIR4-20261003

- **库根**：`/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理`
- **档位**：修复档（`kb-repair`），输入 = 一条已红的闸门
- **输入（修前那条红闸门）**：`kb/kbpy l8/workflow_check.py`（RUN=20261003-2309，2026-10-03 23:09:12，**退出码 1**）
- **本次动作**：按原因码定位 → **判定为不可修（合法变红）** → 复跑同一条闸门留证
  → 交回 `kb-pipeline`（附复开条件）

**一句话**：两个失败项（② 权威库 l0~l6 未被改动 / ③ 前序产物哈希 45 项）的原因码**都是「冻结基线 vs 活库漂移」**，
按本库既有口径属**合法变红**（`kb-repair` §2 明写「**不要"修"**」）。
把冻结基线改成今天的值＝**改数字而不是改事实**，本次**零变更**，复跑仍红 2（读数见 §1）。

---

## 1. 修前 / 修后对照（同一条命令、同一台机器）

| | 命令 | 退出码 | ② 读数 | ③ 读数 |
|---|---|---|---|---|
| **修前** 23:09:12 | `kb/kbpy l8/workflow_check.py` | **1** | `l0 match=false`（tree `469fd05ae274b035`）、`l1/l2=true`、`l3_base1018_matches_L6=false`、`l3_whole1527_matches_L4=false` | `checked=45 / mismatch=20` |
| **复跑** 23:11:52 | `kb/kbpy l8/workflow_check.py REPAIR4-20261003` | **1** | `l0/l1/l2 match=true`（tree `107ba46cc2a11dea`）、`l3_base1018_matches_L6=false`、`l3_whole1527_matches_L4=false` | `checked=45 / mismatch=20`（同一批 20 项） |

其余 7 腿两次都是 PASS：① 环境与版本纪律｜④ 分层库→生成器→视图（沙箱 510 md / 信封 0）｜
⑤ 装载位→加载器（509 条 / 信封 0 / 健康分 79.2 / 检索 4 查询全中）｜⑥ 文档可见性（信封仅剩 `他人产物 hostlib` 510）｜
⑦ 消费侧 skill 可用｜⑧ 工作台与服务｜⑨ 写入侧。

**⚠️ 两次读数差在哪**：`②` 的 `l0` 从 `false` 变 `true` —— 不是我修了什么，
而是**另一会话在这两分钟里把 `kb/.work/l5_integrity.json` 重写了两次**（`checked_at` 23:06:01 → 23:11:02）。
**同一条闸门在十分钟内自己变了一次读数**，这本身就是「基线是活的」的直接证据。

---

## 2. 原因码 → 定性 → 为什么不修

| 失败项 | 原因码 | 定性 | 依据 | 为什么"不修" |
|---|---|---|---|---|
| ② 权威库 l0~l6 未被改动 | 冻结基线 vs 活库漂移 | **合法变红** | `kb-repair/SKILL.md:59`「合法变红，写"基线漂移"结论，**不要"修"**」；`kb-check/SKILL.md:88,95` 同口径；`l7/registry/skills.yaml:1148` note | 判据是「与 09-23 冻结快照比」，活库天天在长 ⇒ 红是**设计内**的。改基线＝伪造"未改动" |
| ③ 前序产物哈希（45 项） | 基线记录了重建前的哈希 | **合法变红（同族）** | 同上；`kb/l7/reports/20260930-1425-health.md:84`、`20260930-134433-health.md:131` 已两次判为「基线漂移 + 判据缺陷，非数据缺陷」 | 20 项不匹配里 **0 项缺失、0 项内容受损**（§3 逐项核过）；红的原因是判据**写死读 09-23 那 4 个 run 记录** |

---

## 3. 独立取证（不引用闸门自己的结论，逐条自己复算）

**3.1 l3 候选文件是 append-only，前缀逐字节未变（排除"被改坏/丢数据"）**

```
当前 kb/l3/candidates/rules.jsonl：1018 行 / 2778872 字节 / sha256 743dc62398311b02…
前 509 行 sha256 = acf77a6a0b05937db01661cb3bd03dd4400ffa6915b3ccd2d264bd6213489c0d
kb/.work/l5_integrity.json 的 prefix_sha256 = acf77a6a0b05937d…  → 逐字节一致：True
l5 基线：lines=1018 / baseline_lines=509 / appended_covers_baseline=True
```
⇒ 509 → 1018 是**追加**，旧块一个字节没动；不是截断、不是篡改。

**3.2 ③ 的 20 项：全部存在，无一缺失，mtime 全在基线之后**

逐项核 4 个 run 记录（`l4/runs/20260923-1445.json`、`l5/runs/20260923-1430.json`、
`l6/runs/20260923-1440.json`、`l7/runs/20260923-1500.json`）共 **45 项**：

```
23:09 与 23:11 两次复跑：mismatch = 同一批 20 项；existence = 20/20 True
mtime 区间：2026-09-29 20:00 … 2026-10-03 21:20（全部晚于 09-23 的基线记录）
```
⇒ 是「基线写死后又被重建」，不是「文件丢了」。

**3.3 20 项里 17 项已被**更晚的**run 记录逐字节背书（活链路其实已经重新记账了）**

扫 `kb/l*/runs/*.json`（10-01 以后）里 `artifacts[].sha256` 与**当前文件**一致的记录：

| 产物 | 有"当前哈希"留痕的更晚记录 |
|---|---|
| `kb/l6/registry/l6.json` | `kb/l6/runs/REVIEW-20261003-2311-…-L6-dryrun.json`（23:12）等 4 条 |
| `kb/l6/index/l6.jsonl` | 20 条（最近 `…2311-…-L6-dryrun` / `20261003-2227-L6-dryrun`） |
| `kb/l6/bm25/docs.jsonl`、`vectors/meta.json`、`retriever.py` | 各 35 条 |
| `kb/l6/selftest.json`、`kb/l6/benchmark.json` | 各 26 条 |
| `kb/l5/registry/l5.json` | 38 条 |
| `kb/l5/benchmark.json` | 19 条 |
| `kb/l4/registry/l4.json` | 5 条（含 `REVIEW-20261003-2233-…-L4-dryrun`） |
| `kb/l3/candidates/rules.jsonl` | `REVIEW-20261003-2311-…-L4-dryrun.json`：sha 一致 True |

⇒ **③ 不是"没人记账"，是"闸门只认 09-23 那 4 个记录文件"** —— 属判据陈旧，见 §4。

**3.4 剩 3 项（`l7/registry/l7.json`、`l7/skills/kb-content-review/SKILL.md`、`…/scripts/review.py`）无更晚记录背书**

```
kb/l7/registry/l7.json                              mtime 10-02 12:02  被 run 记录引用 1 次（仅 09-23 那次的旧哈希）
kb/l7/skills/kb-content-review/SKILL.md             mtime 10-03 12:50  引用 1 次（同上）
kb/l7/skills/kb-content-review/scripts/review.py    mtime 10-03 12:44  引用 1 次（同上）
```
这 3 项是**真·无背书漂移**（改了但没有任何更晚的 run 记录作证）。改动本身**有出处可查**：
`review.py` / `SKILL.md` 的时间戳对应 2026-10-03 的**防线1「入口唯一化」**改动
（登记在 `kb/l7/registry/report-output-contract.yaml` 的 `applied_20261003`，并已在
`kb/l7/reports/REPAIR-20261003-2300-health.md` 变更 6 留痕）；`l7.json` 的内部说明自称 2026-09-30 起改过（632 条口径），
但**它的 `run_id` 至今仍写 `20260923-1500`** —— 属**登记欠账**，不是数据损坏。

**3.5 ② 的 l0 读数在两次复跑间翻转：这是**竞态**，不是缺陷**

```
kb/.work/l5_integrity.json checked_at：2026-10-03 23:06:01 → 23:11:02（十分钟内被重写两次，不是本会话写的）
kb/l0 下唯一的新文件：kb/l0/runs/PIPE-20261003-2305-L0-dryrun.json（23:07 出现，23:10:09 被再写）
按 workflow_check 的 tree_fp 配方复算：kb/l0 全量 tree = 107ba46cc2a11dea == 当前基线（一致）
```
⇒ 23:09 那次红，是**另一会话的 L0 跑批在 23:07 往 `kb/l0/runs/` 落了一个 run 记录**，
而闸门的基线是 23:06 冻的。**闸门与活库写入并发**时读数就会翻转 ——
与 `kb-check/SKILL.md` §4 第 4 条（「本库实测存在并发写入者，只看文件状态会误判」）完全一致。

---

## 4. 未修项清单（**不是通过**：对象 + 原因码 + 要谁做 + 复开条件）

| 对象 | 原因码 | 定性 | 要谁做 | 复开条件 |
|---|---|---|---|---|
| ② 的 `l3_base1018_matches_L6` / `l3_whole1527_matches_L4` | 冻结记录 vs 活文件（且判据写死 `1018`/`1527` 两个历史行数） | **合法变红** | `kb-pipeline`：跑 L4/L5/L6 层侧自检重算基线（`kb/.work/l5_integrity.py` / `l6_integrity.py` 会写自己的快照） | 基线重算到**同一静止窗口**内的读数；否则复跑即翻 |
| ③ 的 17 项（有更晚记录背书） | 判据写死读 `kb/l{4,5,6,7}/runs/20260923-*.json` 四个文件（`workflow_check.py:129-130`） | **判据陈旧**（活链路已重新记账） | **需你点头**：把第③腿改成读**各层最新** run 记录（`kb/l7/runs/index.jsonl` 已有索引）—— 这是**机制改动**，会改变"防篡改探测器"的语义，不在 kb-repair 授权内 | 改判据后 ③ 的读数 = 最新记录的哈希，红才表示"真的没记账" |
| ③ 的 3 项（`l7/registry/l7.json`、`kb-content-review/SKILL.md`、`review.py`） | **真·无背书漂移**（登记欠账） | **真坏（轻）** | 补一次 L7 层跑留痕，或人工把这 3 处改动的出处登进 `kb/l7/registry/l7.json` / runs（**改 `run_id` 要按 §5 先答五问**） | 出现一条更晚的记录/登记，其 sha 与当前文件一致 |
| **本次修不动的前置阻塞** | **循环被另一会话占用** | — | 等它释放 | `kb_loop_claim.py status` 报"进行中 ｜ 会话=`de4a8f6a-b715-43d3-bdc2-5f857db05d5f` ｜ pid=3375 ｜ BASE=`REVIEW-20261003-2311-吸奶器静音续航`"，且 `kb/.work/.kb.lock` 存在、`kb/l4|l5|l6/runs/*2311*` 在 23:11-23:12 仍在落盘 ⇒ 按 `AGENTS.md` 并发纪律（同一时间只准一个会话跑这条循环）**本会话不得起 kb-pipeline** |

---

## 5. 变更记录（本次**零变更**）

**没有修改任何文件**。逐条声明未做的事：

- **未改冻结基线**（`kb/.work/l5_integrity.json`、`l6_integrity.json` 的 `frozen_layers` 哈希一个字节没动；
  注意它 23:06/23:11 的两次重写**不是本会话所为**，是并发会话的层跑写的）。
- **未改 kb/l0…l6 的数据与台账**（未 `--apply`、未写 run 记录、未动 `candidates/rules.jsonl`）。
- **未改** `kb/l7/registry/*.yaml`、未改任何判据脚本（`workflow_check.py` 本次未动）。
- **未认领循环锁**（`kb_loop_claim claim` **没有跑**）、未跑供给链。
- 本次唯一写入：闸门**既定产物** `kb/l8/workflow_check_REPAIR4-20261003.json`（该脚本无干跑档）＋ 本报告。

**回滚点**：不适用（零变更 ⇒ 无可回滚）。原文件备份目录沿用上一单的 `kb/l7/_backups/kb-repair-20261003-225435/`。

---

## 6. 纪律声明

- 写通道：本报告走 **harness `write`**（未用 python 直写 `.md`，不出 4096 信封）；判据只读复核。
- 结论口径按 `kb-check/SKILL.md` §3：**区分「变了」与「坏了」** —— ②③ 是**变了**（合法变红），
  ③ 的 3 项是**没登记**，**没有一项是数据损坏**；**不把判据陈旧报成数据缺陷**。
- 依赖的**外部事实**（并发会话、锁、claim）均带时间戳与命令，可回源复核（§3.5 / §4）。
