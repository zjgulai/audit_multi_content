# 知识库体检表 · RUN `CHK-20261004-0905`

- 库根：`/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理`
- 跑法：`kb-check` **体检档**（六道闸门一次性跑完）；预检查 `preflight.py` 先跑、结论「前置齐，可开跑」
- 跑的时刻：**2026-10-04 09:05–09:10 CST**（本文件写于 09:22 之后）
- 全程只对**门④**做了写盘（该闸门无干跑档），写的是它自己的 `kb/l8/workflow_check_CHK-20261004-0905.json`
- ⚠️ 本次 RUN id **与另一个会话撞车并被我方产物被覆盖**，见「失败项 F」

## 1. 体检表

| # | 闸门 | 命令 | 退出码 | 结论 | 证据（本轮原样读数） |
|---|---|---|---|---|---|
| ① | 登记表自检 | `kb/kbpy l7/scripts/skills_check.py` | **0** | **过** | 五类问题 `1=0 2=0 3=0 4=0 5=0 ｜合计 0`；本项目要用 40（生产 40）、已装 40、还差 0；装载位扫到 59 个目录；12 个 status=参考 的条目未比对（按设计） |
| ② | 层契约自检 | `kb/kbpy l7/scripts/layers_check.py` | **0** | **过** | 层数 8；六类问题 `1..6 全 0`；DAG 非线形（L7 ← L0/L3/L4/L5/L6） |
| ③ | 路由表对账 | `kb/kbpy l7/scripts/routes_reconcile.py kb/l7/reports/CHK-20261004-0905-routes-winners.json` | **2** | **未判定（缺输入，按设计拒跑）** | `环境错：赢家表不存在`；`kb/l7/reports/` 下无 `*routes-winners*`。赢家表是**触发评测的运行时产物**、全库无生成者 ⇒ 缺输入 exit 2 **不是**「65 条全不一致」 |
| ④ | 链路收口核验 | `kb/kbpy l8/workflow_check.py CHK-20261004-0905` | **1** | **9 段 4 红（②③⑥⑧）** | 裁决 `FAIL（未过：['② 权威库 l0~l6 未被改动','③ 前序产物哈希（45 项）','⑥ 文档可见性（agent 能否读到）','⑧ 工作台与服务']）`。②③ = **合法变红**；⑥⑧ = **真坏**。逐段见 §2 |
| ⑤a | 信封闸门（`.py/.txt/.md`） | `python3 tools/envelope_gate.py` | **0** | **过** | 扫 1925 件；信封态 **0**；两读者一致。⚠️ 该脚本 `SKIP_PREFIXES=("hostlib",)`，**故意不扫 `kb/.work/hostlib`** ⇒ 它的 0 **不能**读成「全库无信封」（见 §3） |
| ⑤b | 信封普查（库自带，只扫 `.md`） | `kb/kbpy l8/envelope_census.py` | **0** | **过** | 扫 10336 个 `.md`，读不到 1079 = 刻意归档 569 + 可再生备份 510，**活路径 0** ⇒ OK |
| ⑥ | 投影一致性 | `kb/kbpy l8/projection_reconcile.py` | **1** | **真坏 3/6** | ❌ `R1_source_sha256` ❌ `R2_entry_fingerprint`（509 条）❌ `R4_governance_passthrough`（**2036 处**）；✅ R3 / R5 / R6 |

退出码汇总：`0` → ① ② ⑤a ⑤b（4 道）；`1` → ④ ⑥（2 道）；`2` → ③（缺输入）。

## 2. 门④ 九段逐段

| 段 | 结论 | 读数 |
|---|---|---|
| ① 环境与版本纪律 | **PASS** | `canonical_bytes=0`、`versions_rows=0`、`kb_version=v0` |
| ② 权威库 l0~l6 未被改动 | **FAIL（合法变红）** | l0 `bd36cbb89dedb48f` 4007 件 `match=true`；l1 `099ad8afdc1a0be2` 3152 件 `true`；l2 `183f6265c0666688` 887 件 `true`；`l3_lines=1018`、`l3_base1018_matches_L6=false`、`l3_whole1527_matches_L4=false` ⇒ **漂移只在 L3** |
| ③ 前序产物哈希（45 项） | **FAIL（合法变红 + 1 项真发现）** | 核 45 项、**20 项 mismatch**；其中 `kb/l7/registry/l7.json` 是**真发现**（见失败项 B） |
| ④ 分层库 → 生成器 → 视图 | **PASS** | 沙箱重生成 **510 md / 信封 0**；装载位 513 md / 信封 0；加载器直读 `E001 None` `E046 None` |
| ⑤ 装载位 → 加载器 | **PASS** | `entries=509` / 信封 0 / `E001 None` / `E046 None` / **健康分 79.2** / 检索 `[111, 1, 509, 0]` |
| ⑥ 文档可见性 | **FAIL（真坏）** | 工作区 **6173 md**，不可读 **513**，`buckets={'其他': 3, '他人产物 hostlib': 510}` ⇒ `其他` 必须为 0，实为 **3** |
| ⑦ 消费侧 skill | **PASS** | 入口闸门生效、真入口 `with_kb_evidence.py` 可跑、`review_py_plaintext_write_patch=true` |
| ⑧ 工作台与服务 | **FAIL（真坏，间歇）** | `workbench_4317=000`、`kb_hostlib_4508_health=200`、`launchd_jobs=5` |
| ⑨ 写入侧 | **PASS** | ingest 闸门生效 `[E026] 内容质量分 52.1 < 60`；`落盘 0 个（信封 0）` |

## 3. ⑤a 与 ⑥ 不矛盾的说明（口径差别，别误读）

- `tools/envelope_gate.py` 默认根里含 `kb/.work`，但 `SKIP_PREFIXES = ("hostlib",)`（:`71`、:`178`）**主动跳过** `kb/.work/hostlib` ⇒ 它的「信封态 0」是**排除 hostlib 之后**的 0。
- 门④第⑥段用的是 `walk_md(".")` 全工作区，**不排除** hostlib ⇒ 它数到的 510 全在 `kb/.work/hostlib` 里。
- 本轮独立复算（`walk_md(".")` + `statSync` 同款判据，只读脚本放 `/tmp`）：总 `.md` **6173**、两读者不一致 **513** = hostlib **510** ＋ 其他 **3**；hostlib 共 3101 个 `.md`，其中 510 个是信封态。**与门④读数一致**。
- ⇒ 两把尺子覆盖不同人群，**不能互相替代**，也**不是**判据冲突（这一点 `references/gotchas.md` 已登记）。

## 4. 失败项清单

> 原因码带 ★ 的是**本次新拟**（库内没有登记过该码），分派时别当成注册表里的既有码；不带 ★ 的是库内既有登记。

| 对象 | 原因码 | 要人做什么 | 复开条件 |
|---|---|---|---|
| 门③ 的输入 `kb/l7/reports/<RUN>-routes-winners.json` | `MISSING_INPUT` | 按 `kb-manage` 的触发电测跑一轮，生成赢家表放进 `kb/l7/reports/`（**全库无生成者，必须人触发**） | 文件存在且可解析（`<id>\|<轮1>\|<轮2>\|<轮3>` 或 JSON）⇒ 重跑门③ 得 **exit 0** |
| `kb/l8/workflow_check.py:112-125` 判据 ＋ `kb/l3/candidates/rules.jsonl` | `BASELINE_DRIFT`（已登记：`kb/l7/registry/workflow-check-known-drift.yaml` → `stale_criteria[0]`） | **不要修数据**。请裁该文件 §未决事项 `pending_decision` 的 A/B/C：(A) 授权改判据（改成「与**最新** run 记录比＋来源可溯才降级」）并同时补 3 项落章；(B) 维持长期红；(C) 只补 3 项落章。**改判据要单独走一轮并报批。** 责任：`刘华丽` | 按 `owner_action` 改判据后复跑门④得 **exit 0**；或该段被新判据取代后从登记文件删除。**禁止**：改历史 run 记录的 artifact sha（伪造台账）、把 L3 回滚到 1527 行时代（毁掉 10-02 蒸馏成果） |
| ③ 里 `kb/l7/registry/l7.json`（**真发现**） | `l7_registry_inplace_write_without_run_record`（已登记，`:191`） | **开闸后**跑一次 `kb/.work/l7_article_source_refresh.py <RUN> --apply`，**并补一条 L7 run 记录**（该脚本是 layers.yaml 声明的 L7 引擎）。事实：mtime `2026-10-02 12:02:35`，`run_id` 仍写 `20260923-1500`，无任何 run 记录记过现 sha；实测差异只有 1 个字段（「**四个**形态文件」→「**五个**」），内容正确、**只差落章**；计数已落后现库（`total_rules` 自报 632 / L3 现 1018）。责任：`刘华丽` | 该项现 sha 出现在某条 run 记录的 `artifacts[]` 里；**整段**转绿仍须按上一行改判据 |
| `_eval-L0L7-gap-20261003/` 下 3 个 `.md`：`kb-l0-feishu-fix/SKILL.md`、`kb-l0-feishu-fix/references/CHANGELOG.md`、`kb-check-fix/SKILL.md` | ★ `ENVELOPE_NON_OWN_PRODUCT` | 让跑 `kb-l0-feishu` / `kb-check` **修复副本评测**的那个会话（或该评测负责人）用 **node / `/bin/cp` 通道**重写这 3 个文件（python 直写会带 4096 字节信封）；**跑批期间不要出体检结论**。责任：该评测的跑批人 | 复跑门④，第⑥段 `buckets['其他'] == 0`。注意该桶在近 12 次读数里于 **2↔3** 之间摆动（`他人产物 hostlib` 稳定 510）⇒ 单次转绿不算复开，要**连续两次**绿 |
| `kb/view/` ⇄ 权威分层库（`kb/l8/projection_reconcile.py`） | `gate_red.projection_reconcile`（已登记：`kb/l7/registry/failure-playbook.yaml:160`）；根因 `finding.l3_governance_backfill_lost`（同文件 `:187`） | **不许按脚本自带的 fix 提示直接重生成视图**（修不了 R4，且会把逐条治理值降级为常量、有效期时钟归零＝假绿）。正确顺序：① 报批后跑 `kb/.work/fix_f7_backfill.py` 补 L3 四字段 → ② `fix_f7_verify_c4.py` 复核不动内容字段 → ③ **补一条 L3 run 记录**记回填后 sha 与行数 → ④ 重出视图（`kb/l8/build_view.py --out kb/view`，staging + `repack_write.mjs` 明写回填）→ ⑤ 复跑本闸门 ＋ `l3_gate`。责任：内容治理数据组（`刘华丽`）＋ **L3 层主（判定）**；`kb-repair` 只做分类登记 | `python3 kb/.work/fix_f7_probe.py` 显示四字段 **509/509 非空**，且 `kb/kbpy l8/projection_reconcile.py` **退出 0**（R1/R2/R4 同时绿）。**禁止**：只补 `l3.json` 声明让它与空字段「对上」、把视图治理字段清空换绿、静默改小 `half-life-policy.json` 的 scope、就地改宽 R4 判据 |
| `http://127.0.0.1:4317/`（DSH Desktop pid 2827，launchd `com.workbench.app`） | ★ `GATE_RED_WORKBENCH_INTERMITTENT` | 工作台维护者查 4317 的**间歇性停顿**：端口有监听、4508 全程 200、`launchd_jobs` 恒 5 ⇒ **不是服务没起**。重点怀疑 `com.kb.publish`（launchd 每 300 s 一跑、实测端到端 18604 ms ＋ 26122 ms）与并发跑闸门把它压住 —— **这层因果我未证实，是推测**（要推翻它：在 publish 空闲窗口连打 4317 仍出现 4 s 超时） | 复跑门④第⑧段 `workbench_4317=200`，且**连续 3 次**复跑都稳定 200（单次 200 不算复开） |
| 本次 RUN `CHK-20261004-0905` | ★ `RUN_ID_COLLISION_AND_ARTIFACT_OVERWRITE` | 分派时提醒跑体检/审查循环的会话：**先** `kb_loop_claim.py claim --base <BASE>`（全局单槽，`exit 3`＝别抢），跑完 `release`；RUN id 加会话可辨识后缀（如 `-KBCK`）。责任：发起体检/审查的会话所有者 | 连续两次体检各自持认领、产物不被覆盖 |

## 5. 本次的并发披露（结论可用性）

- 09:05–09:10 期间**另有会话在同一窗口跑同一套闸门**：`kb_loop_claim.py status` 在 09:10 报「**无认领**」，但同分钟出现了 `_chk-run-CHK-20261004-0905-CLOSE/`（09:06–09:10）、`g1..g6.txt`，以及 `kb/l8/workflow_check_CHK-20261004-0906.json`、`_0910-MTG.json`。
- `kb/l8/workflow_check_CHK-20261004-0905.json` 被我写在 **09:06:45**，随后被 **09:08:00** 那次覆盖（现存文件 `at=09:08:00`）。
- **结论仍可用**：我的 09:06:45 与那次 09:08:00 **除时间戳外逐字相同**（两次读数都见 `_chk-run-CHK-20261004-0905/④-workflow.txt` 与 `g4.txt`），09:08:47 / 09:08:50 两次的失败集合也相同（②③⑥⑧）。
- 但按本库契约「体检结论必须能追到 run_id」，这条**产物归属是脏的**——已按失败项 F 分派。

## 6. 纪律声明

- 本 skill **只报不改**：以上任何一项都没有被本轮回写；真坏项按上表交 `kb-repair` / 对应 owner。
- 本轮**未**执行任何破坏性动作：**未**删 `kb/.work/.kb.lock`（当时不存在）、**未**删副本、**未**开 `--apply`、**未**动 `kb/l0~l6` 数据与台账。
- 复现命令见各表格；门④ 的原始 json：`kb/l8/workflow_check_CHK-20261004-0905.json`（注意已被覆盖，见 §5）。
