# CHK-20261004-1245-KBCG 体检表（六道闸门 + 附加闸门 + 库自带 kb_check）

- **库根**：`/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理`（含 `kb/KB-ROOT.json`）
- **体检时刻**：2026-10-04 12:44–12:55（**快照读数**；本库存在并发写入者）
- **档位**：kb-check **体检档**（`references/gates.md` 的六道闸门一次性跑完）
- **预检查**：`python3 .dsh/skills/kb-check/scripts/preflight.py` → **exit 0**「前置齐，可开跑闸门」；唯一缺项 = **赢家表输入无**（预设门③ exit 2）
- **纪律声明**：本轮**唯一写盘** = 门④ 自身产物 `kb/l8/workflow_check_CHK-20261004-1245-KBCG.json`（该脚本**无干跑档**，跑前已声明）。其余闸门全只读。**未加 `--apply`、未改 kb/l0–l6 数据、未碰任何锁、未抢循环认领、未删任何文件。**
- **并发披露（重要）**：跑闸门期间 `ps` 实测**另有 ≥4 个会话在跑同一套闸门** —— `skills_check.py`、`kb_pipeline.py --check`、`l0…l7_gate.py` 循环、`workflow_check.py CHK-20261004-1243-KBCHECK` / `CHK-20261004-1244`、`routes_reconcile.py`、`projection_reconcile.py`、`envelope_gate.py`。另有 12:26 的 `kb-repair-workflow-R8` 在改 `workflow_check.py` 判据备份。⇒ 下表读数按**快照**口径读，`kb/.work/*_integrity.json` 这类滚动文件可能已被别的会话更新。
- **原始日志**：`kb/.work/kbcheck-CHK-20261004-1245-KBCG/`（每个闸门一份 `.out`，层 gate 另有 `.exit`）

---

## 一、六道闸门（kb-check 体检档，权威口径）

| # | 闸门 | 命令 | 跑没跑 | 退出码 | 结论 | 证据 |
|---|---|---|---|---|---|---|
| ① | 登记表自检 | `sh kb/kbpy l7/scripts/skills_check.py` | **跑了** | **0** | **过** | 五类问题 `1=0 2=0 3=0 4=0 5=0 ｜合计 0`；本项目要用 40（生产 40）/ 已装 40 / 还差 0；装载位 `~/.dsh/skills` 扫到 **59** 个目录；另「未登记 selftest」62 条（**不算错误**）；12 个未装条目跳过副本比对 |
| ② | 层契约 | `sh kb/kbpy l7/scripts/layers_check.py` | **跑了** | **0** | **过** | 层数 8（L0…L7 齐全）；六类问题 `1=0 2=0 3=0 4=0 5=0 6=0 ｜合计 0`；DAG 非线形：`L2←L1、L0`／`L3←L0、L2`／`L4←L2、L3`／`L5←L0、L2、L3`／`L6←L0、L2、L3`／`L7←L0、L3、L4、L5、L6`；「无干跑档清单」0 条 |
| ③ | 路由表对账 | `sh kb/kbpy l7/scripts/routes_reconcile.py kb/l7/reports/<RUN>-routes-winners.json` | **跑了（契约口径 + 两个补跑口径）** | **2**（契约路径）／**1**（strict 补跑）／**1**（alias 补跑） | **契约口径：未取得结论（缺输入，不是"全不一致"）**；**补跑口径：不一致 5 条，全部集中在同一个成员** | 契约路径无文件 → `环境错：赢家表不存在 …/kb/l7/reports/CHK-20261004-1245-KBCG-routes-winners.json`，退出码 **2**（全库唯一一份赢家表在 `_backups/` 里，不在契约路径）。补跑喂 `_eval-kb-manage/results_alias/routes-winners_20261004-0327-SUB.txt`（115 行 / 2026-10-04 03:27）：**strict** → exit 1，`①=65 ②=65 ④=0`，逐条全轮命中 **0/65**；**`--alias`** → exit 1，`①=5 ②=5 ④=0`，逐条全轮命中 **60/65（0.923）**，`④ 路由表自检 0 条` |
| ④ | 链路收口 | `sh kb/kbpy l8/workflow_check.py CHK-20261004-1245-KBCG` | **跑了**（⚠️ 写盘 1 个 json，已声明） | **1** | **合法变红 / 判据缺陷（内含 1 项真流程缺陷）** | 裁决 `FAIL`，未过 = `['② 权威库 l0~l6 未被改动', '③ 前序产物哈希（45 项）']`；另 7 段 `①④⑤⑥⑦⑧⑨` **全 PASS**。读数：装载位 509 条／信封 0／E001 None／E046 None／健康分 79.2；可见性 工作区 6328 md，不可读 510（**全在判据容忍的「他人产物 hostlib」桶**）；写入侧 `E026 内容质量分 52.1 < 60`、落盘 0 个（信封 0）。②③ 已在 `kb/l7/registry/workflow-check-known-drift.yaml` 登记为**判据过期**（该文件 `read_by_gate: none` ⇒ **不改变任何闸门判定**），已 8 轮独立复现且读数逐字段相同 |
| ⑤a | 信封闸门（`.py/.txt/.md`） | `python3 tools/envelope_gate.py` | **跑了** | **0** | **过** | 扫描 **2002** 个文件：`正常 2002 ｜信封态 0 ｜读不到 0`；两读者交叉核对（Python `getsize` vs node `statSync`）**一致** |
| ⑤b | 信封普查（库自带，只扫 `.md`） | `sh kb/kbpy l8/envelope_census.py` | **跑了 ×3** | **0 / 0 / 0** | **过**（本轮三次全绿） | 三次读数：扫 10413／10414／10414 个 `.md`，node 侧读不到 **1079** 个（差值 4096），**全部已分类**（刻意归档 569 / 可再生备份 510）⇒ `OK`。⚠️ 12:16 那份体检报告记过一次 **exit 1**（`l7/skills/视频安全审查/SKILL.md`）且随后自愈 —— **本轮三次均未复现**，如实记为「判据可能 flaky，本轮不可复现」 |
| ⑥ | 投影一致性 | `sh kb/kbpy l8/projection_reconcile.py` | **跑了 ×2** | **1 / 1** | **真坏（稳定复现）** | `3/6 项通过，漂移项 3`：`❌R1_source_sha256`（源文件 `rules` 在视图生成后变过 `f27a1409…→743dc623…`）、`❌R2_entry_fingerprint`（**509 条**条目的权威规则已变）、`❌R4_governance_passthrough`（**2036 处**治理字段未传导：`owner/half_life_days/valid_until/effective_from` 各 509）；`✅R3/R5/R6`。脚本自述修法：重跑 `kb/.work/gen-host-library.py` 到 staging 后回填 |

**结论口径**（kb-check §4 四种）：**过** = ①②⑤a⑤b ｜ **真坏** = ⑥ ｜ **未取得** = ③（缺输入）｜ **合法变红/判据缺陷** = ④（②③）。

---

## 二、库自带 `kb_check` 体检（另一把尺子：健康分 + 维度）

**健康分 79.2（熔断线 60）—— 高于熔断线，但整体结论「不通过」。**

| 维度 | 读数 | 阈值 | 判定 |
|---|---|---|---|
| 新鲜度 | 1.00 | ≥ 0.9 | OK |
| 三件套完整率 | 1.00 | == 1.0 | OK |
| 一致性 | 1.00 | ≥ 0.95 | OK（未裁决冲突 0 条） |
| **孤岛率** | **0.94** | **≤ 0.2** | **超标** |
| 覆盖率 | 0.92（35/38） | ≥ 0.8 | OK（未命中 Q21／Q22／Q38；这是**召回**不是「能答」） |
| 利用率 | 0.23（累计 532 次查询／零结果 121 次 = 22.7%） | ≤ 0.3 | OK（从未被命中的条目 **423/509**） |
| 幻觉率 | —— | —— | **无数据**（未进分母，不凑分） |
| 条目基线 | 消失 0／治理字段被原地改 0／正文有改动 0／未入基线 0 | —— | OK |

错误与告警计数（本次实测）：**`E026` × 454**（内容质量分 < 60，最低 **52.5**；**454/509 条**命中）｜**`W020` × 2218**（疑似重复，**涉及 238 条**条目）｜`W021` × 10｜`H005` × 1（`index.status` 仍是 candidate）。

**验收契约** `content-governance-hostlib-20260923`｜owner 刘华丽｜status derived-view｜成熟度 draft｜**`productionReady false`**
- 谓词：`structural_completeness=true`｜`source_traceability=true`｜**`no_duplication=false`**｜`boundary_declared=true`
- 未达条件 **3/3**：`owner_acceptance`(未建)、`final_receipt`(未建)、`fixed_eval_set`(missing)
- 当前生效阻断码：`OWNER_ACCEPTANCE_INCOMPLETE`、`FINAL_RECEIPT_MISSING`、`DATASET_NOT_BUSINESS_AUTHORIZED`

---

## 三、各层 gate（附加，只读，本轮实跑）

八个层 gate 脚本实测**写点全 0**（`grep -cE "open(...,'w')|write_text|json.dump|mkdir"` → 0），确认只读后跑。

| 层 | 命令 | 退出码 | 结论 | 证据 |
|---|---|---|---|---|
| L0 | `l7/scripts/l0_gate.py` | **1** | **真坏（真差异 2）** | 一致 612／飞书多 10／L0多 0／值变 0／**拉取失败 2**；`[EX-1] 材料收集 / only_feishu 实际 10 预期 10` 属预期内；**未声明差异 2 条**：`专家修订汇总表（tbl8AI00JZO1iZtp）`、`内容公式（仅供参考）（tblVdl0jdK9G4ld3）` **拉取失败且未声明** |
| L1 | `l1_gate.py` | 0 | 过 | 全部缓存可复用 |
| L2 | `l2_gate.py` | 0 | 过 | 五项判据 0 违规 |
| L3 | `l3_gate.py` | 0 | 过 | 证据全可回指 + 自报键全已声明 |
| L4 | `l4_gate.py` | 0 | 过 | C1–C6 全过 |
| L5 | `l5_gate.py` | 0 | 过 | 实质 4 项全 PASS；`frozen_layers`／`l3_append_only` 两项 FAIL **已登记为判据过期**（读 `l5-known-drift.yaml`，不判红） |
| L6 | `l6_gate.py` | 0 | 过 | 只读 4 项全过（完整档另行） |
| L7 | `l7_gate.py` | 0 | 过 | 前置条件全成立 |

---

## 四、失败项清单（对象 + 原因码 + 要人做什么 + 复开条件）

| # | 对象 | 原因码 | 要人做什么 | 复开条件 |
|---|---|---|---|---|
| F1 | 门③ 契约输入 | `MISSING_INPUT` | 按 `kb-manage` 的触发电测重生成 `<RUN>-routes-winners.json` 放进 `kb/l7/reports/` | 文件存在且可解析 ⇒ 门③ 拿到契约口径读数 |
| F2 | 门③ alias 口径 5 条不一致 | `ROUTE_TRIGGER_MISS` | **唯一不合格成员 = `brand-ai-provenance-rights-review`（AI溯源与权利审查）**：I1 被视频安全审查接走 ×3；I2 `NONE/图片安全审查/NONE`；I3 `NONE/AI溯源与权利审查/NONE`；I4 `AI溯源与权利审查/NONE/NONE`；I5 `图片安全审查×2/CLARIFY`。该成员 **0/5 条 ｜ 2/15 轮**，其余 12 名成员 **5/5 条 ｜ 15/15 轮** ⇒ 修它的触发描述/让位措辞 | 重跑触发电测 + 门③ alias 得 `②=0` |
| F3 | 门④ ②③ | `STALE_CRITERIA`（判据写死在过去的时点） | **不需"修数据"**，需**裁决改判据**：`kb/l7/registry/workflow-check-known-drift.yaml` 的 `pending_decision` 已连续 **8 轮**带回未答，选项 (A) 授权改判据 /(B) 维持长期红 /(C) 只补落章（**(C) 不能让闸门转绿**） | 按 `owner_action` 改判据并复跑得 exit 0，或该段被新判据取代 |
| F4 | 门④ ③ 中 1 项 | `INPLACE_WRITE_NO_RUN_RECORD` | `kb/l7/registry/l7.json` 原地改写未落章（自报 `run_id` 仍 `20260923-1500`）⇒ 开闸后跑一次 `l7_article_source_refresh.py <RUN> --apply` 并补一条 L7 run 记录 | 补落章后该项不再出现在 mismatch 清单 |
| F5 | 门⑥ 投影漂移 | `PROJECTION_DRIFT` | 重跑 `kb/.work/gen-host-library.py` 到 staging 后回填（R1/R2/R4 同源） | 复跑 `projection_reconcile.py` 得 `6/6` 且 exit 0 |
| F6 | registry 口径过期 | `CONTRACT_STALE` | `kb/l7/registry/routes.yaml:51` 写 `--run <BASE>-L{4,5,6}`，而 `report-output-contract.yaml:364,790` 与**代码** `with_kb_evidence.py:307 LAYER_PREFLIGHT_LAYERS = ("L4","L5","L6","L7")` 都是 **4 层** ⇒ 改 routes.yaml 那一行 | 三处口径一致（L7 在闸门内） |
| F7 | registry 声明失真 | `DECLARED_BUT_UNREAD` | `routes.yaml:138` 表头写「互斥点名（硬约束，**对账器会核**）」，但 `grep -rn mutual_not_for --include=*.py kb/` **0 命中**（对账器用硬编码 7 个元组）⇒ 第 1 对 `["文案合规审查","视频安全审查"]` **从未被任何检查覆盖**。要人做：补进对账器**或**改掉这句声明 | 声明的检查真的存在（或声明删掉） |
| F8 | kb_check `E026` × 454 | `CONTENT_QUALITY_LOW` | **454/509 条**条目内容质量分 < 60（最低 52.5，主要扣在「长度」与「密度」）⇒ 判断是**口径太严**还是**条目本身太薄**（属业务动作，机器只报） | 复跑 `kb_check` 该计数下降或口径经人裁定 |
| F9 | kb_check 孤岛率 0.94 | `ISLAND_RATE` | **472/509 条**与其他条目无任何真实引用关系 —— 要降下来需**来源表提供真实关联列**（业务动作，不许靠造合成边压指标） | 来源表补真实关联列后重新生成视图 |
| F10 | 验收契约 | `OWNER_ACCEPTANCE_INCOMPLETE`／`FINAL_RECEIPT_MISSING`／`DATASET_NOT_BUSINESS_AUTHORIZED` | 三个未达条件要人补：owner 验收、最终回执、固定评测集 ⇒ 当前 `productionReady false` | 三条件补齐后契约转 pass |
| F11 | kb_check `W020` × 2218 | `SUSPECT_DUPLICATE` | 疑似重复，**涉及 238 条**条目；脚本明写「机器只报疑似，**判归人**」 | 人工判：合并（新建 + `supersedes` 留痕）或把分工写进 summary |
| F12 | L0 层闸门 | `FEISHU_FETCH_FAILED` | 两张飞书表拉取失败且未声明：`专家修订汇总表`、`内容公式（仅供参考）` ⇒ 查拉取失败原因，或按 `l0-expected-diffs.yaml` 走声明流程 | `l0_gate.py` 真差异归 0 |

---

## 五、三种"红"的口径判定（kb-check §4）

1. **真坏** —— ⑥ 投影漂移（稳定复现 ×2）、L0 层闸门真差异 2。→ 交 `kb-repair`。
2. **合法变红** —— ④ 门 ⑥ 段工作区不可读 510 全在判据容忍桶；L5 的两项基线 FAIL 已由 `l5-known-drift.yaml` 登记。
3. **已知判据缺陷** —— ④ 门 ②③（判据把历史快照当当前基线，`read_by_gate: none`）、③ 门缺输入 exit 2、⑤b 判据曾 flaky。
4. **本轮未取得结论** —— ③ 门契约口径（缺输入），**不得报绿**。

> ⚠️ 特别提示：`workflow-check-known-drift.yaml` 与 `l4-known-drift.yaml` **不被任何脚本读**，登记它们**不会让任何闸门转绿**；只有 `l0-expected-diffs.yaml` / `l3-known-drift.yaml` / `l5-known-drift.yaml` 会改变闸门判定。**别把"已登记"读成"已通过"。**

---

## 六、要人拍板的事项（本轮无权代拍）

1. **门④ ②③ 的 (A)/(B)/(C)** —— 已连续 8 轮同一句话、同一结论，卡点只剩「要不要批 (A)」。能让闸门转绿的**只有 (A)**。
2. **门⑥ 回填** —— 要不要现在跑 `gen-host-library.py` 到 staging 并回填（会改 `kb/view/`，属写库动作）。
3. **F8/F9/F11** 三条属业务动作（条目质量口径、来源表关联列、疑似重复人工判定），机器只报疑似。

---

## 七、证据落点

- 原始日志：`kb/.work/kbcheck-CHK-20261004-1245-KBCG/`
  `gate1.out`／`gate2.out`／`gate3.out`(exit 2)／`gate3b.out`(strict)／`gate3c.out`(alias)／`gate4.out`／`gate5a.out`／`gate5b*.out`／`gate6*.out`／`layer-l{0..7}.out`(+`.exit`)
- 门④ 自身产物：`kb/l8/workflow_check_CHK-20261004-1245-KBCG.json`（**本轮唯一写盘**）
- 已知漂移登记：`kb/l7/registry/workflow-check-known-drift.yaml`（`read_by_gate: none`）
- 旁证复核（本轮独立实测，非转述）：`routes.yaml:51` vs `report-output-contract.yaml:364,790` vs `with_kb_evidence.py:307`；`mutual_not_for` 全仓代码 0 命中

> 本表**只报不改**。真坏项交 `kb-repair`；本文件不修改任何 `kb/l0–l6` 数据。
