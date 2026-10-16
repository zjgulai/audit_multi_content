# 知识库体检表 · HEALTH-20261003-2321-C

- 库根：`/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理`
- 档位：**体检档**（`kb-check` §1 六道闸门一次性跑完）｜ 时间：2026-10-03 23:21:25 CST（墙钟）
- skill：`kb-check` v1.1.0（装载位 `~/.dsh/skills/kb-check/SKILL.md`，sha256 `fd26fccb…`）
- **只报不改**：本表不含任何修复动作；修复走 `kb-repair`。

> ⚠️ **并发声明（读数有效范围）**：跑本表期间 `ps` 实测另有 **≥3 个会话**在跑同一批闸门
> （`HEALTH-20261003-CHK2327` / `CHK-20261003-2319` / `HEALTH-20261003-2320`），
> 且 `kb_loop_claim.py status` = **无认领** ⇒ 不是"有人在合法持锁"，是**多会话无认领并发**。
> **本表读数只对 23:21:25 这一刻成立**；跨会话比对必须先看时间戳（见 §3）。

---

## 1. 体检表（闸门 → 退出码 → 结论 → 证据）

| # | 闸门 | 命令 | 退出码 | 结论 | 证据 |
|---|---|---|---|---|---|
| ① | 登记表 | `l7/scripts/skills_check.py` | **0** | **过** | 五类问题 `1=0 2=0 3=0 4=0 5=0`；本项目要用 40 个 / 已装 40 / 还差 0；扫到 59 个目录 |
| ② | 层契约 | `l7/scripts/layers_check.py` | **0** | **过** | 层数 8（应为 8）；六类问题合计 0；DAG 非线形（L7 ← L0/L3/L4/L5/L6） |
| ③ | 路由对账 | `l7/scripts/routes_reconcile.py <winners>` | **1** | **判据缺陷（假红）＋ 一处真实弱点** | 65 条**全部**报不一致；折回别名后 **60/65 三轮全中**（见 F-1 / F-2） |
| ④ | 链路收口 | `l8/workflow_check.py HEALTH-20261003-2321-C` | **1** | **合法变红**（9 腿 7 过 2 红） | 红在 ② 权威库未被改动、③ 前序产物哈希 45 项（见 F-3 / F-4） |
| ⑤a | 信封闸门 | `python3 tools/envelope_gate.py` | **0** | **过** | 扫描 1817 个文件 ｜ 信封态 **0** ｜ 两读者（消费方 Electron / PATH node）**一致** |
| ⑤b | 信封普查 | `l8/envelope_census.py` | **0** | **过** | 扫 8688 个 `.md`；差 4096 的 1079 个**全部已分类**（刻意归档 569 / 可再生过期备份 510） |
| ⑥ | 投影一致性 | `l8/projection_reconcile.py` | **1** | **投影漂移（落后 ≠ 坏）** | 3/6 通过；红 R1 / R2 / R4（见 F-5） |
| 附 | 新鲜度 | `l7/scripts/freshness.py` | **0** | **过** | L0–L6 各层关键 data 产物均不陈旧（最旧 L2 units 2.5 天） |

**④ 九腿逐腿**：① 环境与版本纪律 PASS ｜ ② — FAIL ｜ ③ — FAIL ｜ ④ 分层库→生成器→视图 PASS
（沙箱 510 md / 信封 0）｜ ⑤ 装载位→加载器 PASS（**509 条 / 信封 0 / E001 None / E046 None / 健康分 79.1**）｜
⑥ 文档可见性 PASS（工作区 4939 md，不可读 510，全属「他人产物 hostlib」桶）｜
⑦ 消费侧 skill 可用 PASS ｜ ⑧ 工作台与服务 PASS ｜ ⑨ 写入侧 PASS（落盘 0 个 / 信封 0）。

---

## 2. 失败项清单（对象 + 原因码 + 要人做什么 + 复开条件）

### F-1 ③ 路由对账 65/65 全红 —— **其中 65 条全是口径假红**（判据缺陷）

- **对象**：`kb/l7/scripts/routes_reconcile.py`，本次口径 `strict（只认逐字相等的成员 id）`
- **原因码**：**判据缺陷**。期望集来自 `_基线用例.json` 的 `skill` 字段，写的是**英文别名** `brand-*`；
  赢家表写的是**中文装载目录名**。strict 只认逐字相等 ⇒ 65 条**必然**全红，与路由正确与否无关。
- **独立复算（本次亲算，不引闸门自己的结论）**：用 `kb/l7/registry/routes.yaml` 的
  `frozen_expectation.dir_name_map`（13 条）折回后，同一批 65 条：

  | 赢家表 | 折回中文名后三轮全中 | strict 逐字全中 |
  |---|---|---|
  | `blind_v2.winners.txt`（③ 本轮实际吃的那张） | **60 / 65** | 0 / 65 |
  | `blind_after_r3` / `blind_after_r4` / `blind_after` | **60 / 65** | 0 / 65 |
  | `blind_before_v2.winners.txt`（改动前基线） | 6 / 65 | 0 / 65 |

  ⇒ 折回后 **F1 = 60/65 = 0.923 ≥ 0.90 门槛 = 过门槛**；且"改动前 6/65 → 改动后 60/65"证明这处口径
  **不是无意义的**，改动确实生效。**65 条红里 0 条是真错**。
- **要人做什么**：给 `routes_reconcile.py` 加 `--fold-alias`（建议默认开），或把 `_基线用例.json`
  的期望值直接改写成装载目录名 —— **两处取其一，别两处各写一份**（本库纪律：同一事实只写一处）。
- **复开条件**：折回别名后重跑，逐条全轮命中 ≥ 0.90 且**退出码 0**。

### F-2 ③ 残余 5 条 —— 一个成员**真实不稳**（真坏级，但范围收敛到 1 个成员）

- **对象**：`brand-ai-provenance-rights-review` → `AI溯源与权利审查`，用例 **I1–I5**
- **证据**：折回别名后仍然错的 **5 条全部是 I1–I5**（不是散落）；`I1` 在 **4 张赢家表里稳定错成
  「视频安全审查」**（`blind_v2` / `blind_after_r3` / `blind_after_r4` / `blind_after` 一致）；
  I2–I5 三轮漂移（NONE / 图片安全审查 / 视频安全审查 / CLARIFY 交替）。
- **原因推测（个人判断，非结论）**：`AI溯源与权利审查` 与 `视频安全审查` 的 description 都含
  「AI 生成 / AI 痕迹」字样，让位边界未拉开 —— 但这只是**推测**，成立条件是两者的触发短语重叠度高，
  需读两份 SKILL.md 的 description 才能证实/推翻。
- **要人做什么**：对齐这两个成员的让位边界（按 `kb/l7/registry/routes.yaml` 的让位表口径改，不要另抄一份）。
- **复开条件**：I1–I5 三轮全中。

### F-3 ④ ②腿：权威库 `l0~l6`「未被改动」 —— **合法变红**

- **原因码**：**合法变红**（判据 = 与 09-23 冻结快照比；活库天天在长 ⇒ 红是**设计内**的）
- **本次读数**：`l0 tree=107ba46cc2a11dea`（4006 文件）／`l1 tree=9f6b2e91141312c3`（3151 文件）／
  `l2 tree=86f33aa4aac61756`（886 文件）—— **三项与 L5 基线均 `match=true`**；
  红实际落在 `l3_base1018_matches_L6=false` 与 `l3_whole1527_matches_L4=false`。
- **要人做什么**：**不用修**（`kb-repair` §2 明写「合法变红，写'基线漂移'结论，**不要"修"**」）。
  要的是**重冻基线** —— 属写动作，**需单独报批**；把基线改成今天的值 = 改数字而不是改事实。
- **复开条件**：基线重冻后复跑，② 腿 PASS。

### F-4 ④ ③腿：前序产物哈希 45 项中 20 项不匹配 —— **合法变红（同族）**

- **原因码**：**合法变红**。判据**写死读 09-23 那 4 个 run 记录**，而产物此后持续重生成。
- **本次读数**：`checked=45 / mismatch=20`。20 项与 `REPAIR4`（23:11:52 复跑）**同一批、逐项一致**；
  **20/20 全部存在，0 缺失**（无被删、无受损）。不匹配项集中在 `l3/l4/l5/l6` 的构建产物与 registry
  （`kb/l3/candidates/rules.jsonl`、`kb/l6/bm25/*`、`kb/l6/vectors/*`、`kb/l6/index/l6.jsonl`、
  `kb/l7/registry/l7.json`、`kb/l7/skills/kb-content-review/**` 等）。
- **要人做什么**：把判据从"写死 09-23"改成"读**最新** run 记录"（属判据改动，不是数据修复）。
- **复开条件**：同 F-3。

### F-5 ⑥ 投影漂移 3 项 —— **投影落后 ≠ 坏**

- `R1_source_sha256`：源文件 `rules` 在视图生成后变过（`f27a14091b2bd782… → 743dc62398311b02…`）
- `R2_entry_fingerprint`：**509 条**条目的权威规则已变
- `R4_governance_passthrough`：**2036 处**治理字段未从权威库传导
  （`owner` 509 / `half_life_days` 509 / `valid_until` 509 / `effective_from` 509）
- R3 / R5 / R6 通过（id 集合、manifest 字节、tier 目录均一致）
- **定性**：**投影落后**，不是数据损坏。⚠️ 但 `kb-check` §3 的"三种红"里**没有这一类** ——
  按 §3 第 1 条「退出码非 0 = 真坏」会被**误标成真坏**（与 `_eval-kb-check-独立核验-20261003` 的 I1 观察一致）。
- **要人做什么**：重跑 `kb/.work/gen-host-library.py` 到 staging 后回填；并按 I1 建议给 §3 补第四类「投影漂移」。
- **复开条件**：6/6 通过。

---

## 3. 并发事实（本次亲历，必须登记）

1. **同批闸门被 ≥3 个会话同时跑**：`ps` 实测 23:20 有三个 `kb/l8/workflow_check.py` 在飞
   （`HEALTH-20261003-CHK2327` / `CHK-20261003-2319` / `HEALTH-20261003-2320`），
   另有两个 `l8/envelope_census.py`、一个 `tools/envelope_gate.py`、两个 `l6_gate.py`。
2. **无人认领锁**：`kb_loop_claim.py status` = 「无认领：现在没有会话在跑这条循环（可以 claim）」，
   与该实测**直接矛盾** —— 纪律要求的是先 claim 再跑，实际是**无认领并发**。
3. **已出现双计形态**：`kb/l7/runs/index.jsonl` 在 `23:17:42` 与 `23:17:43` 落了**两行内容完全相同**的
   `l0_daily` run（`20261003-231742` / `20261003-231743`，同为 `kb-l0-feishu`、同一 verdict）。
4. **读数会在两分钟内自变**：④ ②腿的 `l0` 在 23:09=`false` → 23:11=`true`，不是有人修了什么，
   是**另一会话重写了 `kb/.work/l5_integrity.json`**（`checked_at` 23:06:01 → 23:11:02）。
   ⇒ 本库「层已跑完」类结论**必须带 run_id + 时间戳**，否则不可复现（`kb-check` §4.4 同口径）。
5. 本次 ④ 的沙箱是 **RUN 命名空间隔离**（`/tmp/l8-wfcheck/wfcheck-<RUN>`，`workflow_check.py:142-144`），
   ⇒ 并发跑 ④ **不会**互相覆盖读数。这一条是**已核**的，不是推测。

---

## 4. 汇总

- 六道闸门：**① ② ⑤ 三道过** ｜ **③ 一道 = 65 条口径假红 + 5 条真弱** ｜
  **④ 一道 = 合法变红（9 腿中 2 腿）** ｜ **⑥ 一道 = 投影漂移**。
- **无 error 级数据损坏**：③ 的 65 条红 0 条真错；④ 的 20 项不匹配 **0 缺失、0 受损**；
  ⑤ 活路径信封 **0**；装载位 509 条 / E001 `None` / E046 `None`。
- **要人动的只有两件**：F-1（`routes_reconcile` 别名折回，判据改动）、F-5（投影回填）。
  F-3/F-4 是**合法变红，不要"修"**；F-2 是一个成员的让位边界对齐。
- 本表由引擎实跑产出，退出码与读数逐条可复跑；**未知原因的红：无**（未出现"未判定"项）。

## 附：本表可复算命令

```bash
cd "/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理"
sh kb/kbpy l7/scripts/skills_check.py;                                    echo "① exit=$?"
sh kb/kbpy l7/scripts/layers_check.py;                                    echo "② exit=$?"
sh kb/kbpy l7/scripts/routes_reconcile.py _eval-kb-manage/blind_v2.winners.txt; echo "③ exit=$?"
sh kb/kbpy l8/workflow_check.py HEALTH-20261003-2321-C;                   echo "④ exit=$?"
python3 tools/envelope_gate.py;                                           echo "⑤a exit=$?"
sh kb/kbpy l8/envelope_census.py;                                         echo "⑤b exit=$?"
sh kb/kbpy l8/projection_reconcile.py;                                    echo "⑥ exit=$?"
sh kb/kbpy l7/scripts/freshness.py;                                       echo "附 exit=$?"
```