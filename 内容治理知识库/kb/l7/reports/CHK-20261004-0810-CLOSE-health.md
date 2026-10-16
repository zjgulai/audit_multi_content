# 全库统一闸门体检表 · `CHK-20261004-0810-CLOSE`

- 档位：**kb-check 体检档**（六道闸门一次跑完；含会写盘的第 ④ 道）
- 库根：`/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理`
- 跑的时刻：**2026-10-04 08:02 – 08:06**（本单亲跑，只读为主）
- 声明：第 ④ 道按要求会写盘 → 产出 `kb/l8/workflow_check_CHK-20261004-0810-CLOSE.json`；
  其余各道零写。**未认领全局单槽、未加 `--apply`、未改 kb/l0…l7 任何数据。**
- ⚠️ 并发：本单跑的同时，**另一会话正在跑同一套闸门**（08:02 起，RUN=`CHK-20261004-0802-HLT`，
  出自 `_eval-L0L7-gap-20261003/_fixrun-kb-check/` 的 kb-check 修复复测）。
  本表读数一律以 **08:03 前后**为准。

---

## 0. 先更正前提：**「刚跑完最新一批」不成立于整链**

| 说法 | 实测 |
|---|---|
| 「整条链路刚跑完」 | **未跑完**。最新两次整链尝试都**没出 L0**：`PIPE-20261004-0217`（02:16 认领 → 02:18 记账 → 02:20 释放）**停在 L0**；`PIPE-20261004-0303` **一层都没跑**（L0 闸门红 + 全局单槽被另一会话持有，两条阻断各自独立成立） |
| 最后一次**真正跑完**的整链 | `PIPE-20261003-2354`：L0 `23:56:55` / L1 `23:59:32` / L2 `00:00:45` / L3 `00:03:02` / L5 `00:09` / 链路结论 `00:21` —— 距本单约 8 小时 |
| 最近 60 分钟库内写入 | 只有 `kb/.work/publish.log`（发布循环，每 ~5 分钟一次，全程「内容没变，幂等重跑」） |

⇒ **「哪一层没闭上」的直接答案是 L0**：不是跑挂了，是 **L0 闸门红 → 编排器红线③「遇红即停」**，
层 skill 根本不会被调起（`kb_pipeline.py:835-838` 的 `break` 在 `:847` 的 `--via-skill` 分支之前）。

---

## 1. 表 A：统一闸门六道（kb-check 体检档）

| # | 闸门 | 命令 | 退出码 | 结论 | 证据（要点） |
|---|---|---|---|---|---|
| ① | 登记表自检 | `l7/scripts/skills_check.py` | **0** | ✅ **过** | 五类问题 1=0 2=0 3=0 4=0 5=0；本项目要用 40 个、已装 40 个、还差 0 |
| ② | 层契约 | `l7/scripts/layers_check.py` | **0** | ✅ **过** | 层数 8（L0…L7 齐全）、六类问题合计 0、DAG 引用合法无环 |
| ③ | 路由表对账 | `l7/scripts/routes_reconcile.py <winners>` | **2** | ⬜ **缺输入 ⇒ 未判定** | 赢家表 `.../CHK-20261004-0810-CLOSE-routes-winners.json` 不存在。**这不是「65 条全不一致」**（旧实现才会那样静默报 exit 1） |
| ④ | 链路收口 | `l8/workflow_check.py <RUN>` | **1** | ❌ **FAIL**（3 段红） | 红：② 权威库 l0~l6 未被改动 ／ ③ 前序产物哈希（45 项）／ ⑥ 文档可见性。其余 7 段 PASS |
| ⑤a | 信封闸门（.py/.txt/.md） | `tools/envelope_gate.py` | **1** | ❌ **真坏 1 个** ＋ 判据自报不可信 | 扫 1913 个文件：信封态 1 个（`.../CHK-20261004-0326-DSH-health.md`，python=20502 / node=24598，差 **−4096**）；另报「判据读者与 PATH 读者读数不一致」 |
| ⑤b | 信封闸门（库自带，只扫 .md） | `l8/envelope_census.py` | **1** | ❌ **真坏 1 个** | 扫 10324 个 .md：刻意归档 569 ✅ / 可再生过期备份 510 ✅ / **活路径 1 个 ❌（必须为 0）** |
| ⑥ | 投影一致性 | `l8/projection_reconcile.py` | **1** | ❌ **真坏**（3/6 通过） | R1 源指纹不符 ／ R2 509 条条目指纹全不符 ／ R4 2036 处治理字段未传导 |

**六道合计：过 2 ／ 缺输入未判定 1 ／ FAIL 3。体检结论：未过。**

---

## 2. 三种「红」的分类（kb-check §4 口径）

| 红 | 分类 | 依据 |
|---|---|---|
| ④ 的 ②、③ 两段 | **合法变红（基线漂移，非缺陷）** | 已登记于 `kb/l7/registry/workflow-check-known-drift.yaml`：判据写死在**已经过去的时点**（②拿 2026-09-23 / 10-02 快照比活库、③拿 2026-09-23 四份 run 的产物哈希当"不许变"基线）。**第 4 次独立复现**，②三项与③的 20 项 mismatch 与前三轮**逐字节相同**，20 项全部有出处。该文件明写「不被任何闸门读、复跑仍 FAIL、不算豁免」 |
| ④ 的 ⑥ 段 | **真坏（1 个是活库路径）** | 不可读 513 = `他人产物 hostlib` 510（判据本就容忍）＋ `其他` 3。这 3 个是：`_eval-L0L7-gap-20261003/kb-l0-feishu-fix/SKILL.md`、同目录 `references/CHANGELOG.md`（**评测批次产物，非库数据**）、`kb/l7/reports/CHK-20261004-0326-DSH-health.md`（**本库活路径**） |
| ⑤a 的「两读者不一致」 | **判据缺陷（半个）** | PATH 里的 node 判绿、判据读者（DSH Electron）判红。但 ⑤b（独立普查、同一判据读者）与 ④⑥ 同指这一个文件，且本单用宿主 `read` 工具**亲证读不到**（`Error: ... binary file`）⇒ **这一条是真坏，不是纯判据缺陷**；只有"PATH 读者判绿"那半边属判据缺陷 |
| ③ exit 2 | **缺输入（不是数据坏）** | 见 `references/gates.md` 门③输入契约；赢家表是触发评测的运行时产物，全库无生成者 |
| ⑥ 投影 R1/R2/R4 | **真坏，已登记处置** | `kb/l7/registry/failure-playbook.yaml → gate_red.projection_reconcile`（2026-10-04 实测同三条）；根因另登记为 `finding.l3_governance_backfill_lost`（L3 权威侧 4 个治理字段丢失） |

---

## 3. 表 B：八层收口（本单亲跑层闸门）

| 层 | 层闸门 | 退出码 | 结论 | 要点 |
|---|---|---|---|---|
| **L0** | `l7/scripts/l0_gate.py` | **1** | ❌ **未过（真差异 2）** | 原始：一致 612 ／ 飞书多 10 ／ L0多 0 ／ 值变 0 ／ 拉取失败 2。分类：预期内 10（EX-1 材料收集）。**未声明差异 2**：`专家修订汇总表（tbl8AI00JZO1iZtp）`、`内容公式（仅供参考）（tblVdl0jdK9G4ld3）` 拉取失败 |
| L1 | `l1_gate.py` | 0 | ✅ 过 | 单图缓存 169 条，版本 `vision-jxa-2.0`，全部可复用 |
| L2 | `l2_gate.py` | 0 | ✅ 过 | 台账 2542 行 ／ 单元 12213 / 1681 资源；五项判据 0 违规（2 条偏差已登记） |
| L3 | `l3_gate.py` | 0 | ✅ 过 | 证据引用 3704 条全可回指；12 个自报键全声明 |
| L4 | `l4_gate.py` | 0 | ✅ 过 | 独立复算 C1–C6 全过；定稿 1365 条 ／ 证据 2585 条；canonical 0 字节（应为 0） |
| L5 | `l5_gate.py` | 0 | ✅ 过 | 实质 4 项全 PASS；2 项基线项（`frozen_layers` / `l3_append_only`）已登记为判据过期 |
| L6 | `l6_gate.py` | 0 | ✅ 过（**只读档**） | 可用单元 4261 ／ 向量 25874 ／ 倒排 4261。**完整档另 4 项本闸门未跑**（要写索引 / 要人看） |
| L7 | `l7_gate.py` | 0 | ✅ 过 | 六要素齐备 1365/1365 = 100% |
| — | `freshness.py`（只读） | 0 | ✅ 不陈旧 | L0 2.1 天 ／ L1 index 1.8 天 ／ L2 2.9 天 ／ L3 rules 1.4 天 ／ L5 10.8 小时。**该脚本带 `--no-gates`，其 health=YELLOW 不可当真实健康色读** |

### 3b. 每层最新 run 记录（「层已跑完」必须带 run_id + 时间戳）

| 层 | 最新 run 记录 | 时间戳 | 该记录 skill | verdict | 备注 |
|---|---|---|---|---|---|
| L0 | `PIPE-20261003-2354-L0-dryrun.json` | 10-03 23:56:55 | `kb-l0-feishu` | — | 预演档；`PIPE-20261004-0217` **无 L0 记录**（未到达） |
| L1 | `PIPE-20261003-2354-L1-dryrun.json` | 10-03 23:59:32 | `kb-ingest-extractor` + `kb-media-extractor` | — | 预演档 |
| L2 | `PIPE-20261003-2354-L2-dryrun.json` | 10-04 00:00:45 | `kb-ingest-extractor` | — | 预演档 |
| L3 | `PIPE-20261003-2354-L3-dryrun.json` | 10-04 00:03:02 | `kb-clause-extractor` | — | 预演档 |
| L4 | `RVW-LISTING-20261004-L4-dryrun.json` | 10-04 03:06:13 | `kb-canonical-lookup` | **FAIL** | 失败项：`l3_append_only` / `article_numbers` / `ledger_coverage` —— **三项都在 `l4-known-drift.yaml` 登记的 5 条判据过期名单里** |
| L5 | `RVW-LISTING-20261004-L5-dryrun.json` | 10-04 03:06:23 | `kb-p0-check` | **FAIL** | 失败项：`frozen_layers` / `l3_append_only` —— **两项都在 `l5-known-drift.yaml` 已登记** |
| L6 | `RVW-LISTING-20261004-L6-dryrun.json` | 10-04 03:11:16 | `kb-recall` | **FAIL** | 失败项：`vector_traceability` —— ⚠️ **全库无 `l6-known-drift.yaml`，此项未登记、本单未判定**（向量侧读数本身正常：25874×384、all_finite=true、范数≈1.0） |
| L7 | `kb/l7/runs/20261004-0805.json` | 10-04 08:05:52 | — | 过0/红0/未判8 ｜ 零写=True | **本单跑闸门期间由并发会话写入**，非本单产出 |

> L4/L5/L6 三份是**评审链**（`RVW-LISTING-20261004`）的层记录，不是供给链 `PIPE-*` 记录 —— 两列不可混读。

---

## 4. 失败项清单（对象 + 原因码 + 要人做什么 + 复开条件）

| # | 对象 | 原因码 | 要人做什么 | 复开条件 |
|---|---|---|---|---|
| **F1** | `kb/l7/reports/CHK-20261004-0326-DSH-health.md`（活路径信封态，宿主 read 工具读不到） | 信封态 `\|python−node\| = 4096` | 按本库通道重落这份报告（python 生成内容 → **无扩展名**临时件 → `/bin/cp` 落目标），或删掉后由该会话重出。**同批另 2 个（`_eval-…/kb-l0-feishu-fix/` 下的 SKILL.md、CHANGELOG.md）是评测批次产物，不属库数据**，另行处置 | `envelope_census.py` 活路径 = 0 且 `read` 工具可读该文件 |
| **F2** | `kb/view` ⇄ 权威库投影漂移（R1 / R2 / R4） | `failure-playbook.yaml → gate_red.projection_reconcile` | ⚠️ **不许**按脚本自带的 fix 提示「重跑生成器到 staging 后回填」直接重生成视图 —— 该条目明写它是**陷阱**：修不了 R4，且会把逐条治理值降级为常量、有效期时钟归零（假绿）。正路是先修 **L3 权威侧治理字段回填**（`finding.l3_governance_backfill_lost`，修 l0–l6 数据须**先停、报批**） | `projection_reconcile.py` 退出 0（R1/R2/R4 同时绿） |
| **F3** | L0 闸门真差异 2：`专家修订汇总表 tbl8AI00JZO1iZtp`、`内容公式（仅供参考） tblVdl0jdK9G4ld3` 拉取失败 | `gate_red.l0`（未声明差异一律判红，不许预豁免） | 人在浏览器侧完成飞书授权 / 复核这两张表；若确属预期，则按纪律登记进 `l0-expected-diffs.yaml`（**每条必须带 evidence + owner_action**，不许只改预期数） | `l0_gate.py` 退出 0 |
| **F4** | 门③ 路由对账 | 输入缺失（exit 2，**非数据坏**） | 按 `kb-manage` 的触发电测重新生成赢家表到 `kb/l7/reports/<RUN>-routes-winners.json` | 有赢家表输入且 `routes_reconcile.py` 退出 0 |
| **F5** | L6 `vector_traceability = FAIL`（`RVW-LISTING-20261004-L6`） | **未登记**（全库无 `l6-known-drift.yaml`） | 由 L6 层主判定：属"判据过期"就补登记 `l6-known-drift.yaml`；属数据坏就走修复 | 该判据要么被登记、要么被修绿；复跑 `l6_gate.py` 完整档 |
| — | ④ 的 ②、③ 两段 | 合法变红（冻结基线） | **不需要动作**（改判据要单独走一轮；本文件不被任何闸门读，复跑仍 FAIL 是预期） | — |

---

## 5. 未判定项（宁可标未判定，不猜）

1. **门③ 路由对账**：缺输入，**未判定**（不写成"通过"，也不写成"全不一致"）。
2. **L6 `vector_traceability`**：未登记、成因未判定（见 F5）。
3. **并发会话的读数**：另一会话 08:02 起在跑同一套闸门（RUN=`CHK-20261004-0802-HLT`），
   本表未采信其未落盘的中间输出；L7 `20261004-0805.json` 是它写的，非本单产出。

## 6. 数据来源

- 本单原始输出：`/tmp/kbchk-0810/`（`g1.txt` `g2.txt` `g3.txt` `g4.txt` `g5a.txt` `g5b.txt` `g6.txt`、`layer-l0…l7.txt`、`freshness.txt`）
- 本单闸门④结构件：`kb/l8/workflow_check_CHK-20261004-0810-CLOSE.json`
- 分类依据：`kb/l7/registry/{workflow-check-known-drift,l4-known-drift,l5-known-drift,l0-expected-diffs,failure-playbook}.yaml`
- 交叉参照（**非本单产出**）：`ci/out/gates-latest.md`（03:30，红：`l0`、`projection`）、`kb/l7/reports/CHK-20261004-0326-DSH-health.md`（**已信封，本单只能用 shell 读**）

**本单未写 `kb/l0…l7` 任何数据、未加 `--apply`、未做任何修复。**
