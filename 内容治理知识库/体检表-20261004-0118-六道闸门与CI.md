# 体检表 ｜ CHK-20261004-0110-FULL ｜ 2026-10-04 01:09–01:18

- **库根**：`/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理`（cwd = 库根）
- **档位**：`kb-check` §1 **体检档**（六道统一闸门）＋ `ci/run_gates.py` 12 把（8 层闸门 + skills/layers/conformance/freshness）＋ 新鲜度前置
- **纪律**：**只报不改**。未传 `--apply`，未改 `kb/l0…l7` 数据与台账，未发布任何东西到飞书
- **本次落盘产物**：① 本表 `kb/l7/reports/CHK-20261004-0110-FULL-health.md`；
  ② `kb/l8/workflow_check_CHK-20261004-0110-FULL.json`（④ 道脚本无干跑档，按设计写盘）；
  ③ `ci/out/gates-latest.{json,md}`（CI runner 覆盖写）；④ 原始读数 `_chk-run-20261004-0110/*.out|.exit`
- **承接**：上一会话的 `_chk-run-CHK-20261004-0107-HLT` 在 ④ 处中断（`4-workflow_check.out` 0 字节），本表把它跑完并补齐 ③/⑤/⑥

---

## 0. 一句话结论

**跑完 18 道（六道统一闸门 + 12 把 CI），过 13、真坏 3 类、未判定 1 道、合法变红 1 类、判据缺陷 0 类。**
唯一**层**红仍是 **L0**（两条 `拉取失败`，取数身份问题、非数据坏），与 00:57 那轮读数**逐字相同** ⇒ 00:58 那次 `repair-l0-identity` 备份**没有**让 L0 转绿。
库级真坏是 **⑥ 投影对账 3/6**（根因已在 `failure-playbook.yaml → finding.l3_governance_backfill_lost` 登记为「L3 治理字段回填丢失」，属**报批动作**，不许按脚本自带 fix 提示直接重生成）。

---

## 1. 新鲜度前置（只读，**不拒答**）

`sh kb/kbpy l7/scripts/freshness.py` → **退出码 0**：「各层关键 data 产物都不陈旧」。
逐层 age：L0 1.8 天 ｜ L1 2.0 / 1.5 天 ｜ L2 2.6 天 ｜ L3 1.1 天 ｜ L4 1.1 天 ｜ L5 3.9 小时 ｜ L6 1.7 天。
⇒ 本次**没有**「因超期而必须去跑写档链路」的理由（① 不拒答、② 不强制）。
★ 该脚本带 `--no-gates` 跑，屏上的 `health=YELLOW` 是「没跑闸门」的产物，**不代表真实健康色**。

---

## 2. 六道统一闸门（kb-check 体检档）

| # | 闸门 | 命令（cwd = 库根） | 退出码 | 判定 | 关键读数 |
|---|---|---|---|---|---|
| ① | 登记表自检 | `sh kb/kbpy l7/scripts/skills_check.py` | **0** | ✅ 过 | 五类 `1=0 2=0 3=0 4=0 5=0`；本项目要用 40 / 已装 40 / 还差 0；未登记 selftest 62 条（不算错） |
| ② | 层契约自检 | `sh kb/kbpy l7/scripts/layers_check.py` | **0** | ✅ 过 | 层数 8；六类全 0；引擎路径存在、cwd/解释器/DAG 扇出均合规 |
| ③ | 路由表对账 | `sh kb/kbpy l7/scripts/routes_reconcile.py kb/l7/reports/CHK-20261004-0110-FULL-routes-winners.json` | **2** | ⚠️ **未判定（缺今日输入）** | 赢家表不存在（它是**触发评测的运行时产物**，全库无脚本自动生成）⇒ 按设计 exit 2，**不报绿也不静默按「全不一致」跑** |
| ③b | 同上（**对照**，非今日判定） | `… routes_reconcile.py --alias _eval-kb-manage/blind_v2.winners.txt` | **1** | ⚠️ 过期口径读数 | 逐条全轮命中 **60/65（92.3%）**；四节问题 ①=5 ④=0；该赢家表是 **2026-09-29 19:58** 的，已 5 天 |
| ④ | 链路收口核验 | `sh kb/kbpy l8/workflow_check.py CHK-20261004-0110-FULL` | **1** | 🟡 **9 段 2 红（②③）→ 合法变红** | 装载位 509 / 信封 0 / 健康分 **79.1** / 检索 `[111, 1, 509, 0]`；⑥ 文档可见性 PASS（不可读 510 全为 hostlib 可再生备份）；⑦⑧⑨ PASS |
| ⑤a | 信封闸门（.py/.txt/.md） | `python3 tools/envelope_gate.py` | **0** | ✅ 过 | 扫 **1853** 个文件｜信封态 **0**｜读不到 0；两读者（Electron node vs PATH node）交叉核对**一致** |
| ⑤b | 信封普查（.md） | `sh kb/kbpy l8/envelope_census.py` | **0** | ✅ 过 | 扫 8728 个 `.md`，1079 读不到，**全部已分类**（刻意归档 569 ＋ 可再生备份 510）；结论 OK |
| ⑥ | 投影一致性 | `sh kb/kbpy l8/projection_reconcile.py` | **1** | 🔴 **真坏 3/6** | ❌ `R1_source_sha256` ❌ `R2_entry_fingerprint`（509 条）❌ `R4_governance_passthrough`（`owner` / `half_life_days` / `valid_until` / `effective_from` 各 509 = **2036 处**）；✅ R3 / R5 / R6 |

**红 2 道（④⑥）＋ 未判定 1 道（③）。其中没有一条是「脚本坏了」。**

### ④ 的 9 段逐段
`PASS ①环境与版本纪律` ｜ `FAIL ②权威库 l0~l6 未被改动` ｜ `FAIL ③前序产物哈希（45 项）` ｜
`PASS ④分层库→生成器→视图` ｜ `PASS ⑤装载位→加载器` ｜ `PASS ⑥文档可见性` ｜ `PASS ⑦消费侧 skill 可用` ｜
`PASS ⑧工作台与服务` ｜ `PASS ⑨写入侧`（⑨ 内含 `[E026] 内容质量分 52.1 < 60`，落盘 0 个、信封 0）

---

## 3. CI 12 把（`python3 ci/run_gates.py --outdir ci/out`）

**退出码 1 ｜ 过 11/12 ｜ 红 `['l0']` ｜ 无法计算 无 ｜ 非 blocking 报错 无 ｜ 基础设施 无 ｜ 告警 无**
（`ci/out/gates-latest.md`，生成时刻 **2026-10-04T01:18:27**）

| 闸门 | 状态 | 退出码 | 红数 | 耗时 |
|---|---|---|---|---|
| l0 | **RED** | 1 | 2 | 44.1s |
| l1 | PASS | 0 | 0 | 13.3s |
| l2 | PASS | 0 | 0 | 16.3s |
| l3 | PASS | 0 | 0 | 15.8s |
| l4 | PASS | 0 | 0 | 16.0s |
| l5 | PASS | 0 | 0 | 37.3s |
| l6 | PASS | 0 | 0 | 276.9s |
| l7 | PASS | 0 | 0 | 10.7s |
| skills | PASS | 0 | - | 9.9s |
| layers | PASS | 0 | - | 11.2s |
| conformance | PASS | 0 | 0 | 9.8s |
| freshness | PASS | 0 | - | 95.9s |

★ 与 **00:57:43** 那轮相比：**逐把状态完全一致**（同样只有 `l0` 红、同样红 2）。这 20 分钟里闸门读数没有变化。

★ **同日交叉核对**：`kb/l7/reports/2026-10-04-daily-health.md`（体检时刻 00:30:34，健康 **RED**）自报「过 7 ｜ 红 1 ｜ 层数 8」，
同样只有 **L0** 一道不通过 —— 与本表 §3 逐把读数一致。（本表**未**重跑 `daily_health.py`：同一天的产物已在，重跑会覆盖 `2026-10-04-daily-health.md`。）

---

## 4. 失败项 / 未判定项清单（对象 + 原因码 + 要人做什么 + 复开条件）

### 4.1【真坏·高·唯一红的层】L0 闸门红 —— 两张表拉不到，回落身份也失效
- **原因码**：`gate_red.L0`（登记件 `kb/l7/registry/l0-expected-diffs.yaml → resolved → EX-2/EX-3 → observed_20261004`）
- **读数**：`一致 612 ｜ 飞书多 10 ｜ L0多 0 ｜ 值变 0 ｜ 拉取失败 2 ｜ 身份回落 0`
  未声明差异 2 条：`专家修订汇总表(tbl8AI00JZO1iZtp)`、`内容公式（仅供参考）(tblVdl0jdK9G4ld3)`
- **性质**：**不是数据错，是取数身份问题**。bot「守衡」`91403 you don't have permission`；
  user 令牌 `token_missing`（登录态在 23:44→00:57 之间失效）。**是第三种组合**：bot 仍 91403 **且**回落身份也不可用。
- **要人做什么**（两条都在 registry 的 `owner_action` 原文里，CI 修不了）：
  ① 根治（不改代码）：飞书侧把「守衡」bot 加成该 Base 的**可阅读协作者**；
  ② 临时：`lark-cli auth login --profile dsh-kb --domain base --domain wiki`（Device Flow，需人授权）
- **不许做**：把这两条写进 `expected` 声明掉（该文件 `not_exemptable` 明令禁止），或把 `pull_failed` 从四类差异里摘掉。
- **复开条件**：`l0_gate.py` 退出 0（两表 `拉取失败 0`；`飞书多 10` 仍由 EX-1 覆盖）

### 4.2【真坏·中·已登记根因】⑥ 投影对账 3/6 —— 根因是 **L3 治理字段回填丢失**
- **原因码**：`gate_red.projection_reconcile` ＋ `finding.l3_governance_backfill_lost`（均在 `kb/l7/registry/failure-playbook.yaml`）
- **证据**：`kb/l3/candidates/rules.jsonl`（1018 行）里 `owner` / `effective_from` 键存在但**全空**，`half_life_days` / `valid_until` **键都不存在**；
  而 `kb/l3/registry/l3.json` 的 `changes[2]`（run 20260929-1040）**声称**已把这四个字段回填进 509 行 ⇒ **注册表声明与实文件不一致**。
- **要人做什么**：**先补 L3 治理字段**（属报批动作）→ 再重出视图（`kb/l8/build_view.py --out kb/view`，staging + `repack_write.mjs` 明写回填）→ 复跑本闸门与 `l3_gate`。
- **禁止**：按脚本自带 `fix` 提示直接「重跑生成器回填」。实测这是**陷阱**：R4 **照样红**，且会把逐条治理值（法务 474 / 法务+产品负责人 14 / 法务+渠道负责人 13 / 法务+医学顾问 8；half_life 90/365）**降级成统一常量**、`valid_until` 归零 —— 正是 `kb/l3/registry/half-life-policy.json` 禁止的假绿。
- **复开条件**：`projection_reconcile.py` 退出 0（R1/R2/R4 同时绿）

### 4.3【合法变红·已登记】④ 的第 ②③ 段
- ② 拿 2026-09-23 / 10-02 的**冻结快照**比活库、③ 拿 09-23 四份 run 记录的产物哈希当「不许变」基线（45 项 20 项 mismatch）。
  活库每天在跑，这种判据**必然** FAIL。登记件：`kb/l7/registry/workflow-check-known-drift.yaml`（文件头明写：**今天没有任何闸门读本文件**，登记只为分类留痕，复跑**仍然是 FAIL**）。
- **要人做什么**：把判据从「一个字节都不许动」改成「**改动都能追到出处**」—— 属**改判据，单独走一轮**，不在本次范围内。

### 4.4【未判定】③ 路由表对账
- **原因**：缺今日赢家表（运行时会话未曾生成）。
- **要人做什么**：要今日判定 ⇒ 先按 `kb-manage` 的触发电测重新生成赢家表，再复跑 ③。
- **不许做**：拿 5 天前的 `_eval-kb-manage/blind_v2.winners.txt` 的 60/65 当今日结论（本表已把它单列为「3b 对照」）。

---

## 5. 并发观测（本表是**活库快照**，不是冻结基线）

- 跑前 `kb_loop_claim.py status`：**无认领**；`kb/.work/.kb.lock` **不存在**。
- 但同一窗口内有**别的会话在写**：`kb/l7/runs/` 新增 `20261004-010357.json`、`20261004-010458.json`；
  `kb/l7/skills/kb-l0-feishu/references/gotchas.proposals.md`、`kb/l7/registry/{skills,failure-playbook,l0-expected-diffs}.yaml`
  在 00:42–01:00 间被改过（伴随 `kb/l7/_backups/…-20261004-0042 / -005758 / -005831` 三组备份）。
- ⇒ 本表读数对应**各自命令的运行时刻**（01:09–01:18），不能读成「整个库此刻的冻结状态」。
- 本库已登记过并发事故（同一 RUN 在 `index.jsonl` 落 2 行、L7 记账行被覆盖）⇒ **写档循环同一时间只准一个会话**；本次**未**认领循环锁、**未**跑任何写档链路。

---

## 6. 这份表**不能**拿去说什么（口径边界）

1. ③ 是**未判定**，不是「路由表坏了」；3b 那份 60/65 是**过期口径**，不得当今日 F1。
2. `l0` 的红**不代表 L0 数据坏了** —— 是取数身份问题（§4.1）。
3. ④ 的 ②③ 是**判据过期**（合法变红），**不是**有人偷改权威库；**不许**当缺陷去「修数据」。
4. ⑥ 的红**不许**按脚本自带 fix 提示直接重生成视图（§4.2 的假绿陷阱）。
5. 本次**没有任何审查结论**；工作区**仍没有待投素材**（见 `审查待执行-发布前全流程-20261004.md`）。
6. 本表**只跑闸门**，**没有**跑 L0→L7 写档链路；`freshness` 的 `health=YELLOW` 不代表真实健康色。

---

## 7. 命令回放

```bash
cd "/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理"
bash _chk-run-20261004-0110/run.sh                     # ① – ⑥ + 新鲜度（本次 8 个读数）
python3 ci/run_gates.py --outdir ci/out                # 12 把，只读；本次 exit 1（红=l0）
sh kb/kbpy l7/scripts/kb_loop_claim.py status          # 跑前并发核验：无认领
```
