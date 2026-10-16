# 体检表 · CHK-20261004-1254-LUTE

- 档位：**体检档**（六道闸门一次性跑完）｜纪律：**只报不改**（修复走 kb-repair）
- 库根：`/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理`
- 跑表时刻：2026-10-04 12:52–12:57 CST｜执行：kb-check（含 predflight 只读预检查，结论「前置齐，可开跑」）
- run_id 与时间戳：本表结论对应 **CHK-20261004-1254-LUTE**；④ 门落盘 `kb/l8/workflow_check_CHK-20261004-1254-LUTE.json`（12:54:00）

---

## 一、闸门汇总（每道闸门 → 退出码 → 结论 → 证据）

| # | 闸门 | 命令 | 退出码 | 结论 | 证据 |
|---|---|---|---|---|---|
| ① | 登记表自检 | `kbpy l7/scripts/skills_check.py` | **0** | **过** | 五类问题 1=0 2=0 3=0 4=0 5=0；本项目应装 40 / 已装 40；参考 11、宿主通用 19 不参与判定；「未登记 selftest」62 条为单独归类、不算错误 |
| ② | 层契约 | `kbpy l7/scripts/layers_check.py` | **0** | **过** | 8 层齐（L0…L7）；六类问题全 0；DAG 非线形（L7←L0,L3,L4,L5,L6）；无干跑档清单 0 条 |
| ③a | 路由表对账（**名义输入**） | `kbpy l7/scripts/routes_reconcile.py kb/l7/reports/CHK-20261004-1254-LUTE-routes-winners.json` | **2** | **输入缺失**（不是数据坏） | 赢家表是触发评测的运行时产物，全库无生成者；`kb/l7/reports/` 下无 `*routes-winners*` |
| ③b | 路由表对账（存量赢家表，无 `--alias`） | `… _eval-kb-manage/results_alias/routes-winners_20261004-0327-SUB.txt` | **1** | **假红（口径错配）** | 65/65「全不一致」：赢家表写中文装载目录名、用例期望英文 id。**不得据 exit 1 报「路由全坏」** |
| ③c | 路由表对账（同一赢家表 + `--alias`） | `… 同上一文件 --alias` | **1** | **真不一致 5 条** | 逐条全轮命中 **60/65（0.923）**；5 条全部集中在 **I 组「AI 溯源与权利审查」** |
| ④ | 链路收口 | `kbpy l8/workflow_check.py CHK-20261004-1254-LUTE` | **1** | **3/9 段 FAIL**（逐段见下） | 落盘 4888B；裁决 FAIL（未过：②③⑥） |
| ⑤a | 信封闸门（库自带） | `kbpy l8/envelope_census.py` | **0** | **过** | 扫 10416 个 `.md`，1079 个 node 读不到 → 全部已分类：刻意归档 569 + 可再生的过期备份 510 ⇒ 结论 OK |
| ⑤b | 信封闸门（`.py/.txt/.md`） | `python3 tools/envelope_gate.py` | **0** | **过** | 扫 2005 文件；活路径信封态 **0**；两读者交叉核对一致 |
| ⑥ | 投影一致性 | `kbpy l8/projection_reconcile.py` | **1** | **真漂移 3/6** | R3/R5/R6 过；**R1/R2/R4 红**（根因见第三节） |

### ④ 逐段（9 段，3 FAIL）

| 段 | 结果 | 关键读数 |
|---|---|---|
| ① 环境与版本纪律 | PASS | 装载位 02:02:55；生成器 11:26:57 `408a6d079312b66f` 73520B；`l7/review.py` 12:44:03 `ed47c8f4b9bbc93f`；kb_version `v0` |
| ② 权威库 l0~l6 未被改动 | **FAIL** | l0/l1/l2 树指纹 `match_L5_baseline` **全 true（没漂）**；红在 **L3** |
| ③ 前序产物哈希（45 项） | **FAIL** | **20/45 不匹配**（清单见第四节第 6 项） |
| ④ 分层库 → 生成器 → 视图 | PASS | 生成器沙箱产出 510 md / 信封 0；node 读回断言通过 |
| ⑤ 装载位 → 加载器 | PASS | 509 条 / health **79.2** / E001 E046 均 None。**但**：孤岛率 0.941、利用率 0.227、`fm_ok 453/509`（56 条 frontmatter 不合规） |
| ⑥ 文档可见性 | **FAIL** | 6335 md 中 511 不可读 = **510「他人产物 hostlib」**（刻意归档/可再生备份）+ **1 真信封** `./_envctl-20261004-125012/py-write.md` |
| ⑦⑧⑨ | PASS | review.py 入口闸门 rc=2、真入口 rc=0；工作台 4317=200、hostlib 4508=200；ingest 闸门 E026 内容质量分 52.1<60 |

---

## 二、六条命令的退出码一览（便于照抄）

```
①  skills_check.py                                             → 0
②  layers_check.py                                             → 0
③  routes_reconcile.py <名义输入，不存在>                        → 2   ← 缺输入
③  routes_reconcile.py <存量赢家表>                              → 1   ← 口径错配假红
③  routes_reconcile.py <存量赢家表> --alias                      → 1   ← 真不一致 5 条
④  workflow_check.py CHK-20261004-1254-LUTE                     → 1   ← ②③⑥ FAIL
⑤  envelope_census.py                                           → 0
⑤  tools/envelope_gate.py                                       → 0
⑥  projection_reconcile.py                                      → 1   ← R1/R2/R4 红
```

---

## 三、关键发现：⑥ 的根因，以及「重跑生成器」是个陷阱

### 3.1 ⑥ 的红是同一件事的三个面

`projection_reconcile.py` 判定：视图 `kb/view` 由 2026-09-29 的 `rules.jsonl` 派生，而该源文件此后被改写。

- **R1**：源文件指纹 `f27a14091b2bd782… → 743dc62398311b02…`（p0 指纹一致 `470e3fbad21489b9`）
- **R2**：**509/509 条**条目指纹全部失效
- **R4**：2036 处 = 4 个治理字段 × 509 条
- R3（集合对齐 509=509、无多无缺）、R5（落盘 vs manifest）、R6（tier↔目录）**过**

### 3.2 根因（已实测）

权威侧 `kb/l3/candidates/rules.jsonl` **不再携带**这些字段：

| 字段 | 当前权威侧有值行数 |
|---|---|
| `owner` / `half_life_days` / `valid_until` / `effective_from` | **0 / 1018** |
| `authority_source_table` | **0 / 1018** |
| `p_level` | 仅 `P1`(986) / `P2`(32) —— **无 P0** |
| `risk_level` | 全部 `unknown`（1018/1018） |

而行数本身也变了：当前 **1018 行 = 509 rule_id × 2**；而 2026-09-23 记账基线对应 **1527 行 = 3 × 509**。
按 ④② 的口径实测：`b1018 = b1527 = 743dc623…`，L6 记账基线 `7d00454e…`、L4 记账基线 `aa83d1f9…`（`kb/l4/runs/20260923-1445.json`）**两者都不匹配** ⇒ 内容确已变（不是「文件没动却被判漂移」）。

而**已装视图里的这 4 个字段是对的、且严格吻合政策**：

- `half_life_days`：365×21 / 90×22 / 180×466
- 对应 `kb/l3/registry/half-life-policy.json` 的 A/B/C 三档 `count` **21 / 22 / 466 逐数吻合**
- `valid_until` = 策略基线日 2026-09-29 + 半衰期 → 2027-09-29 / 2026-12-28 / 2027-03-28；`effective_from` 恒为 2026-09-29
- `owner`：4 种取值（法务 474、法务 + 产品负责人 14、法务 + 渠道负责人 13、法务 + 医学顾问 8）

⇒ **视图不是「错的」，它是「旧的」；真正被掏空的是权威侧。**

### 3.3 陷阱：现在就重跑生成器 = 把政策值换成兜底常量

闸门输出里写的修法是「重跑 `kb/.work/gen-host-library.py` 到 staging 后回填」。**今天照做会主动毁掉这批数据**，依据有二：

1. 读代码：生成器（F8，2026-09-29）从**权威行**读这 4 个字段；缺则回落
   `OWNER_FALLBACK = "法务"`(:92)、`DERIVED_HALF_LIFE_DAYS = 180`(:93)、`valid_until = 今日+180`、`effective_from = 今日`，并记入 `governance_fallbacks`。
2. **实测**（我把生成器跑到 `/tmp/hl-probe-1254`，**未触碰 kb/**，exit 0）：
   509 条**全部**变成 `owner: 法务` / `half_life_days: 180` / `valid_until: 2027-04-02` / `effective_from: 2026-10-04` / `created_at: 2026-10-04`，
   `governance_fallbacks` = **509 条**。

后果：三档半衰期（365/90/180）**塌成一档**、到期日整体平移约 179 天、`effective_from` 从策略基线日改成当天。
政策文件自己写着 `never_resets_on_regeneration: true`，并明说「若用重生成当天算 valid_until，每次重生成都会把时钟归零 —— 那又是另一种假绿」。

> **正确顺序：先恢复权威侧 4 个字段 → 再重生成 → 最后回填。** 顺序反了就是把最后一份政策口径值覆盖掉。

### 3.4 可恢复性（供 kb-repair 用，本档不动手）

- **P0 标记（21 条）**：可从 `kb/l5/registry/l5.json` 的 `p0_disposition` 按 `rule_id` 逐条取回（含 rule_code / disposition / reason）。
- **A/B 档半衰期**：`kb/l4/_pre-rebuild-20260930-1550/wording_entry.jsonl` 56 行（90×22、365×21、180×13）覆盖 A+B 全量 + 13 条 C。
- **另一份口径不一致的载体**：`kb/l4/canonical/wording_entry.jsonl` 56 行（90×34、180×22）—— 与上一份**不同**，这个不一致本身也需人裁。
- **其余 C 档**：仅存于已装视图及其副本（`kb/view`、`kb/l8/_stage/view_W`、`kb/l7/_backups/projection-rebuild-20261004-020113/view`）。
  ⇒ **恢复动手前先保全 `kb/view`（只读，不要覆盖）**。

### 3.5 未判定（不猜）

L3 里 `P0` / `risk_level` 消失，是**有意迁移到 L5**，还是**改写时丢失**，我拿不出定论，标 **未判定**。
两边证据互斥：L5 的 `selection` 口径要求 `p_level = P0`（`excluded` 记 488 non-P0 / 21 P0），与当前 L3「无 P0」对不上；但 `l5.json` 的 `p0_disposition` 又保留了逐条 P0 处置，说明 L5 侧是有意管这件事的。**需层主裁决。**

---

## 四、失败项清单（对象 + 原因码 + 要人做什么 + 复开条件）

| # | 对象 | 原因码 | 要人做什么 | 复开条件 |
|---|---|---|---|---|
| 1 | `kb/l3/candidates/rules.jsonl` | `L3-GOV-FIELDS-LOST` | 裁决 3.5；恢复 `owner/half_life_days/valid_until/effective_from`（连带 `authority_source_table`、`p_level` P0、`risk_level`） | ⑥ 的 R1/R2/R4 复跑转绿（或生成器改从新落点读），且 ④② 的 L3 基线重新记账 |
| 2 | `kb/view`（投影） | `PROJ-STALE-SEP29` | **先**保全视图 → 恢复权威字段 → **最后**才重生成回填；**禁止先重生成**（见 3.3） | `projection_reconcile.py` 退出码 0 |
| 3 | `kb/l7/reports/<RUN>-routes-winners.json` | `ROUTES-NO-INPUT` | 按 kb-manage 触发电测重新生成**本轮**赢家表 | ③ 不再 exit 2 |
| 4 | I1–I5（AI 溯源与权利审查 5 条） | `ROUTE-MISS-I-GROUP` | 修该成员 description / 触发词：6 轮次无人接（NONE）、3 次被视频安全审查抢走、3 次被图片安全审查、1 次 CLARIFY | `--alias` 下 65/65 且 exit 0 |
| 5 | `./_envctl-20261004-125012/py-write.md` | `ENVELOPE-PY-WRITE-SCRATCH` | 会话草稿，改走 node/cp 通道；是否清理由人定（本档不动手） | ④⑥ 信封计数归 0 |
| 6 | L6 索引/向量全套、l4/l5 registry、`kb/l7/skills/kb-content-review/{SKILL.md,scripts/review.py}` 等 20 项 | `ARTIFACT-HASH-DRIFT` | **无并发写者时冻结重跑 ④**，再判是否需重记账（见第五节） | 冻结重跑后 ③ 剩余项为 0 或仅剩有意变更 |

---

## 五、并发声明与读数可信度

跑表期间**另有会话正在写库**（`kb/.work/kbcheck-CHK-20261004-1245-KBCG/` 的 gate*/layer* 输出 12:45–12:57；`kb/l7/runs/index.jsonl` 12:51/12:54/12:56/12:57；`kb/l7/review.py` mtime **12:44:03**；12:57 出现 `kb/.work/.kb.lock` 与 `.kb-loop-claim.json`）。

据此分级：

- **④ 的 ②③ 段 = 活库读数**。②的红**不是** l0/l1/l2 漂移（三者全 true），是 L3 内容确已变（3.2 已实测）；③的 20/45 不匹配含当日 12:44 被改的文件 ⇒ **冻结重跑前，不得当「数据坏了」追究**，也不得报绿。
- **⑥ 不受并发影响**：它的比对基准是 2026-09-29 的 `derivation.json` 记录，与谁在跑无关。⇒ **⑥ 是本档最可信的一条红**，也正是最该先处理的那条。
- ④⑥ 判「不可读」的 510 个文件，⑤ 判为「刻意归档 / 可再生」并给 OK —— **两把尺子对同一批文件口径不一致**，属判据口径问题，**需人裁，不是数据缺陷**。

---

## 六、写盘声明（本档全部足迹）

1. `kb/l8/workflow_check_CHK-20261004-1254-LUTE.json`（4888B）—— ④ 门固有落盘，**该门无干跑档**，跑前已声明。
2. 本文件 `kb/l7/reports/CHK-20261004-1254-LUTE-health.md`。

其余五道闸门与全部取证探针**只读**；生成器实测写到 `/tmp/hl-probe-1254`，**未动 `kb/`**。
**未执行任何破坏性动作**：未删锁、未删副本、未删库、未改 `kb/l0…l6` 任何数据。
