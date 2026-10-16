# 体检表 · CHK-20261004-1344 ｜ 全库六道闸门（体检档）

- 交表时点：2026-10-04 CST（RUN 起 13:44，止 13:48）
- 库根（cwd）：`/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理`
- 档位：**体检档**（六道闸门一次跑完）；本 skill **只报不改**
- 本单写盘（**开跑前已声明**，见 `kb/.work/kbcheck-CHK-20261004-1344/00-declare`）：
  ① `kb/l8/workflow_check_CHK-20261004-1344.json`（门④ 无干跑档）；② 本表落 `kb/l7/reports/CHK-20261004-1344-health.md`；
  ③ 原始读数 `kb/.work/kbcheck-CHK-20261004-1344/`（`01.out`…`06.out` ＋ 各自 `.exit` ＋ `03b-substitute.out` ＋ `00-declare`，**均为无后缀文件**，不会被信封闸门扫到）
- **复跑留痕**：13:53 把 ① ② ③ ⑤a ⑤b ⑥ 六道**只读闸门**原命令复跑一轮并落 `.exit`（首轮 13:45–13:46 只落了 `04.exit`）；
  **七个退出码与首轮逐个相同**（`01=0 02=0 03=2 04=1 05a=0 05b=0 06=1`）⇒ 本表读数在并发环境下**可复现**
- 标注约定：【事实】= 命令/文件实测可回源核对；【推测】= 有依据但未被证据闭合；【观点】= 判断，不是结论；【未判定】= 现有材料判不了，留给人

---

## 0. 周会只看这一屏

| 对象 | 读数 | 一句话 |
|---|---|---|
| ① 登记表自检 | **过**（exit 0） | 五类问题全 0；本项目 40/40 已装 |
| ② 层契约 | **过**（exit 0） | 8 层齐、DAG 非线形、引擎路径存在、六类问题全 0 |
| ③ 路由表对账 | **红（exit 2）· 判据缺陷（缺输入）** | 赢家表不存在 ⇒ 缺输入，**不是「路由 65 条全不一致」** |
| ④ 链路收口 | **红（exit 1）· 合法变红** | 9 段 7 PASS / 2 FAIL，红的 2 段全在比对 **2026-09-23 冻结基线**，已 **11 天**没有信号能力 |
| ⑤ 信封闸门 | **过**（exit 0 / 0） | `.py/.txt/.md` 活路径 2031 件信封 0；`.md` 普查 10430 件，1079 件读不到但**已全部归类**（569 证据本体 + 510 可再生备份） |
| ⑥ 投影一致性 | **红（exit 1）· 真坏 3/6** | `kb/view` ⇄ 权威库对不上；**本次复核修正了前序报告的定性与修法**（见 §3） |
| 尺 宿主 `kb_check`（辅证，非六道闸门） | **不通过** | 健康分 **79.2**（熔断线 60，**未熔断**）；错误项非空，故判不通过 |

**要人做的只有 3 件**（详见 §7）：
1. **⑥ 治理字段归属与视图重生成 —— 最高优先**：权威库 L3 现在**一行都没有** `owner/half_life_days/valid_until/effective_from`，值只活在派生视图里。
   ⇒ **在把值写回 L3 之前，不要按前序报告的建议「授权重生成视图回填」** —— 那会退回兜底常量（`法务` / `180` / `生成日+180`），把 509 条的逐条政策值抹平。**这一条与前序报告的推荐动作方向相反，请在本周会上裁。**
2. **③ 赢家表**：按 `kb-manage` 触发电测重新生成 `<RUN>-routes-winners.json` 放到 `kb/l7/reports/`，门③ 才有真读数。
3. **④ 第②③段基线**：已 11 天恒红（262 份历史读数里 ②红 256 / ③红 259）。**人裁**：重新锚定基线，或显式豁免 —— 别再把它的红当新回归报警。

**〔观点〕一条流程观察**：本次体检时段内，同一套只读闸门**至少 6 个 RUN 在 6 分钟内并发跑**（实测 RUN ID 见 §6）。读数彼此一致（算是独立复现），但这是**重复劳动**，且会互相干扰（门④ 第⑧段瞬时红、信封闸门自命中）。周会若要省人力，值得先定「一天/一周跑几次、谁跑」。

---

## 1. 体检读数（退出码为管道截断前先取的 `$?`）

| # | 闸门 | 命令 | 退出码 | 结论 | 关键读数 |
|---|---|---|---|---|---|
| ⓪ | 预检查（只读） | `python3 .dsh/skills/kb-check/scripts/preflight.py` | **0** | 前置齐 | 库根识别正确；7 个闸门脚本全在；门③ 输入**无** |
| ① | 登记表自检 | `sh kb/kbpy l7/scripts/skills_check.py` | **0** | **过** | 五类 `1=0 2=0 3=0 4=0 5=0`；生产 40/40 已装；3 条跳过（12 个未安装条目未比副本）；另 62 条「未登记 selftest」**单独归类、不算错误** |
| ② | 层契约 | `sh kb/kbpy l7/scripts/layers_check.py` | **0** | **过** | 层 L0–L7 共 8；必填 12 字段齐、引擎路径存在、cwd/解释器约定成立、DAG 非线形；六类 `1..6 = 0` |
| ③ | 路由表对账 | `sh kb/kbpy l7/scripts/routes_reconcile.py kb/l7/reports/CHK-20261004-1344-routes-winners.json` | **2** | **判据缺陷（缺输入）** | 脚本自述「缺输入时本闸门**不得报绿**，也不得静默按『全不一致』跑」 |
| ④ | 链路收口 | `sh kb/kbpy l8/workflow_check.py CHK-20261004-1344`（**无干跑档、已声明写盘**） | **1** | **合法变红（2 段）** | 9 段 7 PASS / 2 FAIL（②③）；13:45:58 → 13:47:40，用时 102s；产物 `kb/l8/workflow_check_CHK-20261004-1344.json` |
| ⑤a | 信封闸门（三件套） | `python3 tools/envelope_gate.py` | **0** | **过** | 扫 2031 个 `.py/.txt/.md`；信封态 **0**；两读者（宿主 Electron / PATH node）**一致** |
| ⑤b | 信封普查（库自带，只扫 `.md`） | `sh kb/kbpy l8/envelope_census.py` | **0** | **过** | 扫 10430 `.md`，1079 个 node 侧读不到，**已全部归类**（569 刻意归档=证据本体 / 510 可再生过期备份）⇒ 结论 `OK` |
| ⑥ | 投影一致性 | `sh kb/kbpy l8/projection_reconcile.py` | **1** | **真坏 3/6**（定性见 §3） | R1/R2/R4 红，R3/R5/R6 绿 |
| 尺 | 宿主 `kb_check`（**非六道闸门**，辅证） | 工具调用，**不带** `accept_baseline` | — | **不通过** | 健康分 **79.2**；错误 `E026×454`、告警 `W020×2218`、`W021×10`、提示 `H005×1`；条目基线 **消失 0 / 治理字段被原地改 0 / 正文有改动 0 / 未入基线 0** |

> 口径提醒（老坑，别混用两把尺子）：宿主 `kb_check` 的「一致性 1.00」是**条目级**，**不等于** ⑥ 的「投影一致性」；
> 前者比条目、后者比「视图 ⇄ 权威库」。**不要互相顶替。**

---

## 2. 门④ 逐段定性：两段红为什么不是真坏

| 段 | 结果 | 读数（本单实测） | 定性 |
|---|---|---|---|
| ① 环境与版本纪律 | PASS | `l4_canonical_bytes=0`、`versions_rows=0`、`kb_version=v0` | 过 |
| **② 权威库 l0~l6 未被改动** | **FAIL** | l0/l1/l2 与 L5 基线比对**均 true**；`l3_base1018_matches_L6=false`、`l3_whole1527_matches_L4=false`（`l3_lines=1018`） | **合法变红（冻结基线）**：比对对象是 `kb/.work/l5_integrity.json`、`kb/.work/l6_integrity.json`、`kb/l4/runs/20260923-1445.json` —— **2026-09-23 的基线**；活库模式下必红（`references/gotchas.md` 第 2 行） |
| **③ 前序产物哈希（45 项）** | **FAIL** | `checked=45`，不符 **20 项**：`l3/candidates/rules.jsonl`、`l4/registry/l4.json`、`l5/registry/l5.json`、`l5/benchmark.json`、`l6/**`（bm25/vectors/index/registry/selftest/benchmark/retriever.py）、`l7/registry/l7.json`、`l7/skills/kb-content-review/**` | **合法变红（同类冻结基线）**：核对对象是 2026-09-23 四份 run 记录里登记的 artifacts。**独立复核**：抽 10 个不符文件的 mtime 全部落在 **09-29 ～ 10-03，无一在 10-04** ⇒【推测】是「合法重跑过、基线没跟着更新」，不是这次被改坏 |
| ④ 分层库→生成器→视图 | PASS | 生成器 11:26:57 `408a6d079312b66f` 73520B；沙箱 510 md／信封 0 | 过 |
| ⑤ 装载位→加载器 | PASS | 509 条／信封 0／`E001 None` `E046 None`／健康分 79.2／检索 `[111, 1, 509, 0]` | 过 |
| ⑥ 文档可见性 | PASS | 工作区 6356 md，不可读 510，**全部**归「他人产物 hostlib」 | 过 |
| ⑦ 消费侧 skill 可用 | PASS | `review.py` 入口闸门生效；真入口 `with_kb_evidence.py` rc=0 | 过 |
| ⑧ 工作台与服务 | PASS | 本单 `workbench_4317=200`、`kb_hostlib_4508_health=200` | 过，但**本段有瞬时性**（前序多单实测过 `000`）⇒ 单次红不足以下「工作台坏了」的结论 |
| ⑨ 写入侧 | PASS | ingest 闸门 `[E026] 内容质量分 52.1 < 60`；落盘 0 个（信封 0） | 过 |

**本单独立复算（自己算，不引用前单）**：`kb/l8/workflow_check_*.json` 共 **262 份**，② 红 **256** 次、③ 红 **259** 次；
**②③ 同时绿的最后一份 = `workflow_check_20260923-180808.json`（2026-09-23 18:08:09）**。
⇒【事实】这两段已 **11 天无信号能力**；把它们当「新回归」报警是错的。要恢复信号必须**重新锚定基线或显式豁免**——
**属机制改动，人裁范围，本单只报不改。**

---

## 3. 门⑥ 3/6：本次复核**修正了前序报告的定性与修法**（周会重点）

### 3.1 脚本自己的读数（本单实测）

```
投影对账：kb/view ⇄ 权威分层库        3/6 项通过，漂移项 3
  ❌ R1_source_sha256        源文件 rules 在视图生成后变过（f27a14091b2bd782… → 743dc62398311b02…）
  ❌ R2_entry_fingerprint    509 条条目的权威规则已变（任一字段）
  ❌ R4_governance_passthrough  2036 处治理字段未从权威库传导
        {"owner": 509, "half_life_days": 509, "valid_until": 509, "effective_from": 509}
  ✅ R3_id_set   ✅ R5_manifest_bytes   ✅ R6_tier_dir
```

### 3.2 逐项取证：R4 的「方向」与前序报告的读法不一样

| 项 | 【事实】实测 | 说明 |
|---|---|---|
| R4 的方向 | 取 `--json` 逐条样本：`{'field': 'owner', 'view': '法务 + 产品负责人', 'authority': ''}` | **视图有值、权威库侧为空**（不是「视图缺字段」） |
| 视图侧 | 509 条**全部**带四字段：`half_life_days` = 180×466 / 90×22 / 365×21；`owner` = 法务×474 / +产品×14 / +渠道×13 / +医学顾问×8；`effective_from` 全 = 2026-09-29 | 建扫 509 个视图条目 frontmatter（只读） |
| 权威侧 | `kb/l3/candidates/rules.jsonl` **1018 行**：`owner`/`effective_from` **全为空串**，`half_life_days`/`valid_until` **键都不存在**；**带这四个字段任意一值的行 = 0** | 逐行实测 |
| 政策侧 | `kb/l3/registry/half-life-policy.json`（`status=active`，`created_at=20260929-1040`）写着：`scope` = rules.jsonl 全部 509 条；三档 `half_life_days` = A(P0)365×21 / B 90×22 / C 180×466；四类 owner = 8/13/14/474；`fields_backfilled` 明确「`effective_from`/`owner` **原有字段原为空串，本次填入**」 | 政策写的三档数与四类 owner 数，与**视图实测分布逐项吻合** ⇒ 政策确实被执行过 |
| 执行脚本 | `kb/.work/fix_f7_backfill.py`（09-29 10:08）第 242 行写回 **`kb/l3/candidates/rules.jsonl`**，留 `rules.jsonl.before-F7` 备份，第 264 行登记进 `l3.json` | ⇒【事实】落点**本来是权威库 L3**，不是视图 |
| 生成器 | `kb/.work/gen-host-library.py` 906–935 行：四字段**从 L3 行（head）读**；读不到才走兜底 `OWNER_FALLBACK="法务"` / `DERIVED_HALF_LIFE_DAYS=180` / `valid_until=生成日+180`，并把兜底记进 `governance_fallbacks` | ⇒ **F8 已经在读 L3**；前序报告 §3「先修 F8（生成器是否读这 4 个字段）」这个开放问题**有答案了：读了，是 L3 空** |
| 留痕自相矛盾 | `kb/view/_meta/derivation.json`：`generated_at=2026-09-29`，自述「每次兜底都会记进 `governance_fallbacks`」，但 `governance_fallbacks` = **0 条**，而 509 条**全都有值**；`sources.rules.sha256 = f27a1409…` ≠ 当前 `743dc623…` |【事实】三处对不上 |

### 3.3 结论与「不要做什么」

- 【事实】**治理字段的值当前只活在派生视图里；权威库 L3 一行都没有。** 这与前序报告 §3「视图滞后、缺治理字段」的**方向相反**：
  视图不是缺，是**唯一持有者**。
- 【未判定】值是怎么从 L3 消失的：本地**无 git**，`kb/l3/_archive/20261002-2230-prewrite/` **只留了 `rejected.jsonl`、没留 `rules.jsonl`**，
  也找不到 sha = `f27a1409…` 的规则快照 ⇒ 「09-29 政策写入 L3 后，被 10-02 那次重写（rules.jsonl mtime 10-02 22:45、509 行 → 1018 行）抹掉」
  只是【推测】，**判不了**，需要回源核对或人裁。**不猜。**
- ⚠ **修法必须改序**：生成器在 L3 读不到值时**只会写兜底常量**（`法务` / `180` / `生成日+180`）。
  ⇒ 若按前序报告的建议「授权 → 重跑 `gen-host-library.py` 到 staging 后回填」，**509 条的逐条政策值会被抹平成一套常量**，
  正是 `half-life-policy.json` 自己警告过的「假绿」。
  **正确顺序：先把四字段写回 L3（或先裁定「视图才是真源」并把政策文件改口径），再谈重生成。**
- 修法（脚本自己打印，非杜撰）：R1/R2 的 `修法` = 「重跑生成器到 staging 后回填」；R4 的 `修法` = 「确认生成器是否从规则行读这 4 个字段（F8）」。
  两条修法**在本单取证下都不足以直接执行**，理由见上。
- **不许用 `rm -rf kb/view` 让它变绿**（老坑）：`kb/view/_meta/` 住着活状态（查询日志 / 账本 / 条目基线），删＋回填**不等于**复原。

---

## 4. 门③ 缺输入：替身赢家表**不可比**，不许当「路由坏了」用

- 名义输入 `kb/l7/reports/CHK-20261004-1344-routes-winners.json` 不存在 ⇒ **退出码 2**。
  全库唯一同类文件是 `_eval-kb-manage/results_alias/routes-winners_20261004-0327-SUB.txt`（115 条，另一批评测的产物）。
- 本单拿它**补测**（**非**本闸门名义输入）：退出码 **1**、strict 口径 **逐条全轮命中 0/65**（四节问题 ①=65）。
  **这不是路由坏了的证据**：用例期望英文 id（`brand-content-review-agent` 等），该赢家表记的是**中文装载名**（`内容审查总控`/`送审登记`…），
  strict 不折叠；脚本自打备注「本表口径含 alias 折回；要核对请用 `--alias` 一致的 results 目录」。
  ⇒ **替身输入不可比，门③ 仍按「缺输入」记。**
- 要今天的真结论：按 `kb-manage` 的触发电测**重新生成**赢家表，放到约定路径再跑（本单不做）。

---

## 5. 宿主 `kb_check` 尺子读数（辅证，非六道闸门）

- 健康分 **79.2**（熔断线 60）⇒ **未熔断**；判「不通过」是因为**错误项非空**，不是分数过线。
- 各维度：新鲜度 1.00 / 三件套 1.00 / 一致性 1.00（未裁决冲突 0）/ 覆盖率 0.92（35/38，未命中 Q21、Q22、Q38）/
  利用率 0.23（累计 532 次查询、零结果 121 次 = 22.7%）**均 OK**；
  **孤岛率 0.94（阈值 ≤0.2）标 `!!`** —— 423/509 条目从未被检索命中；脚本自述解法是「**扩充词表**或补 `asks` 关键词，**不要靠删**」。
- 缺口：`E026`（内容质量分 <60，集中在 `3_措辞表达库/L1-facts/`）**454** 条、`W020` 疑似重复 **2218** 组、
  `W021` 疑似数值矛盾 **10** 组、提示 `H005` **1** 条（检索排序未经 UAT 复核）。
  `W020/W021` 是**机器只报疑似、判归人**；合并须走「新建 + `supersedes` 留痕」，不许原地改写。
- 条目基线：**消失 0 / 治理字段被原地改 0 / 正文有改动 0 / 未入基线 0**（本次**未** `accept_baseline`）。
- 验收契约 `content-governance-hostlib-20260923`（owner 刘华丽）：`status=derived-view`、成熟度 `draft`、`productionReady=false`；
  谓词 `no_duplication=false`；未达条件 **3/3**（`owner_acceptance` 未建、`final_receipt` 未建、`fixed_eval_set` missing）；
  阻断码 `OWNER_ACCEPTANCE_INCOMPLETE`、`FINAL_RECEIPT_MISSING`、`DATASET_NOT_BUSINESS_AUTHORIZED`；`canonicalWrite=false`。
- 库存（`kb_collections`）：总库 = 「Momcozy知识库 · 内容治理（派生视图）」，根 `kb/view`；
  子库 **1 个**：`3_措辞表达库` 509 条，负责人 刘华丽，状态 `derived`，调用方「待定（内容审查 Agent 尚未立项编号）」。
- 幻觉率维度**无数据**（未进分母）。

---

## 6. 并发观察（**只读取证，未做任何处置**）

本单全程处于**多会话并发**环境（skill §6 要求的「先确认是否有另一批在跑」）：

| 观察 | 【事实】证据 |
|---|---|
| 同 6 分钟内至少 **6 个**同名体检 RUN | `kb/.work/kbcheck-CHK-20261004-1344`（本单）/ `-1346` / `-1349-SUB`；`_chk-run-CHK-20261004-1345-REG5` / `-1347-LAYERCLOSE` / `-1350-3GATES`；`13:47:23` `ps` 实测有 `workflow_check.py CHK-20261004-1349-SUB`、`CHK-20261004-1347-LAYERCLOSE` 在跑 |
| 读数**互相独立复现且一致** | `CHK-20261004-1346`：`01=0 02=0 03=2 04=1 05a=0 05b=0 06=1` —— **与本单逐项相同**；`1347-LAYERCLOSE`：`01=0 02=0 03=2 04=1 05a=0`；`1350-3GATES`：`01=0 02=0 05a=0` |
| 锁 / 认领状态 | `kb/.work/.kb.lock` **不存在**；`kb_loop_claim.py status` = 「无认领：现在没有会话在跑这条循环」⇒ **本单未删任何锁、未 `--take-over`、未认领** |
| 方法学（本单自查） | 本单 run 目录**只放无后缀文件**（`.out`/`.exit`/`00-declare`），故 ⑤a 扫 2031 件得 0，**未被「自己把自己扫成信封态」污染**（该陷阱只对 **python 写的 `.txt/.md`** 成立） |

【观点】并发本身不改变本单任何读数（各单一致），但它意味着**同一件事被重复做了 6 遍**；且门④ 第⑧段这类**瞬时指标**在并发争用下会闪红，容易被误读成「服务坏了」。

---

## 7. 失败项清单（交 `kb-repair` / 交人裁决）

| # | 对象 | 原因码 | 要人做什么 | 复开条件 |
|---|---|---|---|---|
| 1 | **治理字段归属：`half_life_days`/`valid_until`/`owner`/`effective_from` 只在视图、L3 为 0 行**（门⑥ R4 + R1/R2） | `GOVERNANCE_FIELD_ORPHANED` | **人裁二选一**：(a) 把值写回 L3（依 `half-life-policy.json` 与 `fix_f7_backfill.py` 的路径）**再**重生成视图；(b) 裁定「视图为真源」并改政策文件口径。**裁定前不要跑视图重生成回填**（会退回兜底常量） | 门⑥ **6/6**，且 L3 与视图对同一 `rule_id` 的四字段一致 |
| 2 | 门③ 赢家表输入 | `MISSING_INPUT` | 按 `kb-manage` 触发电测生成 `kb/l7/reports/<RUN>-routes-winners.json` 放**约定路径** | 文件存在且可解析 ⇒ 门③ 得 **0 或 1**（**1 才是真结论**） |
| 3 | 门④ 第②③段基线 | `BASELINE_STALE`（262 份里 ②红 256 / ③红 259，已 11 天） | **人裁**：重新锚定基线 **或** 显式豁免 | 该段恢复信号能力（不再恒红） |
| 4 | `3_措辞表达库` 454 条 | `E026` 内容质量分<60 | 扩充词表 / 补 `asks` 关键词 / 补长度密度，**不要靠删** | `E026` = 0 |
| 5 | 措辞表达库 2218 组 / 10 组 | `W020` 疑似重复 / `W021` 疑似数值矛盾 | 机器只报疑似、**判归人**；合并走「新建 + `supersedes` 留痕」 | 人裁后归零 |
| 6 | 孤岛率 0.94（阈值 ≤0.2） | `ISLAND_RATE` | 扩词表 / 补 `asks`，**不要靠删条目** | 孤岛率 ≤ 0.2 |
| 7 | 验收契约未达 3/3 | `OWNER_ACCEPTANCE_INCOMPLETE`、`FINAL_RECEIPT_MISSING`、`DATASET_NOT_BUSINESS_AUTHORIZED` | 建 `owner_acceptance` / `final_receipt` / 业务授权数据集 | `productionReady=true` |
| 8 | `_meta/index-status.yaml` | `H005`（提示，非错误） | 检索排序未经 UAT 复核 —— 别把未复核的排序当定稿 | UAT 复核后改 `status` |
| 9 | 流程：同一套闸门短时重复跑 6 遍 | `REDUNDANT_RUNS` | 定「跑几次、谁跑、读哪一单」；或把六道闸门迁 CI（skill §8 停用条件 1） | 同一时段只有 1 单在跑 |

---

## 8. 本单做了什么 / 没做什么

**做了**：预检查（exit 0）；六道闸门逐条跑并**先取退出码再截断输出**；**13:53 六道只读闸门原命令复跑一轮、七个退出码逐个相同**（可复现）；门④ 跑前**声明写盘**；
门③ 用替身输入**补测**并标「不可比」；独立复算 262 份历史 ②③ 读数；独立抽 10 个不符文件核 mtime；
**对门⑥ 逐项取证**（509 条视图 frontmatter 实测 + L3 1018 行实测 + 政策文件 + 回填脚本 + 生成器源码 + `derivation.json`）；
宿主 `kb_check` 一次（**不带** `accept_baseline`）；与并发会话读数交叉核对；全程留痕在 `kb/.work/kbcheck-CHK-20261004-1344/`。

**没做（逐条）**：未 `rm -rf` 任何路径；未删副本 / 锁 / 认领；未 `--take-over`；未跑 `kb_pipeline` 或任何层引擎；
未 `accept_baseline`；**未写 `kb/view`**；未改 L3 任何一行；未修任何闸门红项；未发布飞书；未动 `kb/l0…l6` 数据与台账。

---

## 9. 复现命令

```bash
cd "/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理"
python3 .dsh/skills/kb-check/scripts/preflight.py                              # 0：cwd/脚本/输入齐否
sh kb/kbpy l7/scripts/skills_check.py                                          # 0
sh kb/kbpy l7/scripts/layers_check.py                                          # 0
sh kb/kbpy l7/scripts/routes_reconcile.py kb/l7/reports/CHK-20261004-1344-routes-winners.json   # 2（缺输入）
sh kb/kbpy l8/workflow_check.py CHK-20261004-1344                              # 1（②③ 合法变红；写 kb/l8/）
python3 tools/envelope_gate.py                                                 # 0
sh kb/kbpy l8/envelope_census.py                                               # 0
sh kb/kbpy l8/projection_reconcile.py                                          # 1（3/6）
sh kb/kbpy l8/projection_reconcile.py --json | python3 -c "import sys,json;print(json.load(sys.stdin)['checks']['R4_governance_passthrough']['samples'][:3])"
```

- 本单原始读数：`kb/.work/kbcheck-CHK-20261004-1344/`（`01.out`…`06.out` ＋ `.exit` ＋ `00-declare` ＋ `03b-substitute.out`）
- 前序同类：`kb/l7/reports/CHK-20261004-1329-health.md`、`kb/l7/reports/CHK-20261004-1306-health.md`
- sha 措辞红线：本表**未**声称任何 sha「重算通过」。文中的 sha 只作**指纹比对**（`f27a1409…` vs `743dc623…` 均取自脚本与文件实测）；
  L0 的 `sha256_input` 是 `record_fields` 字面量，本地 L0 件**不含**该 blob，**重算在本地结构上不可能**。
