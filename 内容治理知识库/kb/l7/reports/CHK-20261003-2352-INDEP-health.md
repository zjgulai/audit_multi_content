# 知识库体检 · CHK-20261003-2352-INDEP

> 体检档（`kb-check` §1 六道统一闸门 ＋ `kb_check` 工具 ＋ 逐层闸门 `l0_gate…l7_gate` ＋ 逐层收口核）
> 库根：`/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理`
> 执行窗口：2026-10-03 23:33–23:52（**时点快照**，见 §五 并发警告）
> 只报不改：本次未修任何数据，未加 `--apply`，未写 `kb/l0…l6`。

## 一、统一闸门体检表（6 道）

| # | 闸门 | 命令 | 退出码 | 结论 | 关键证据 |
|---|---|---|---|---|---|
| ① | 登记表自检 | `l7/scripts/skills_check.py` | 0 | **过** | 五类问题 1–5 全 0；本项目 40 个生产成员应装已装 40；未登记 selftest 62 条（归类项，不算错误）；12 个带 source 未安装故跳过副本比对 |
| ② | 层契约自检 | `l7/scripts/layers_check.py` | 0 | **过** | 8 层齐 / 12 必填字段齐 / 引擎路径存在 / cwd·解释器合规 / DAG 非线形且无环 / 六类 0 |
| ③ | 路由表对账 | `l7/scripts/routes_reconcile.py <winners>` | **2**（缺今日输入）／1（参考跑） | **未判定** ＋ 参考红 | 无今日赢家表（全库仅 `_eval-kb-manage/blind_*.winners.txt`，2026-09-29）；参考跑见 §四 F-3 |
| ④ | 链路收口核验 | `l8/workflow_check.py CHK-20261003-2336-INDEP` | 1 | **合法变红 ×2 ＋ 已分类变红 ×1** | 9 段里 ②③⑥ FAIL；逐项见 §四 F-5。落盘 `kb/l8/workflow_check_CHK-20261003-2336-INDEP.json` |
| ⑤ | 信封闸门 | `tools/envelope_gate.py`；`l8/envelope_census.py` | 0／0 | **过** | 活路径 1,824 文件 0 信封态；全库 8,695 md 中 1,079 个信封态**全部**落在 `l3/_archive`（569，证据本体）与 `.work/hostlib.bak`（510，可再生） |
| ⑥ | 投影一致性 | `l8/projection_reconcile.py` | 1 | **真漂移** | R1/R2/R4 红：视图落后权威库；R3/R5/R6 过。根因见 §四 F-2 |
| — | 健康分（`kb_check` 工具） | — | ok=false | **不通过（未熔断）** | 健康分 **79.1** > 熔断线 60；`ok = errors==0 && !breaker`，454 条 E026 使 ok=false |
| — | 逐层闸门 | `l7/scripts/l0..l7_gate.py` | 8×0 | **8 层闸门全过** | L0 真差异 0；L1 缓存 169 条全可复用；L2 五项判据 0 违规；L3 证据全可回指；L4 C1–C6 全过；L5 实质 4 项 PASS；L6 只读 4 项过；L7 六要素覆盖 100% |
| — | 逐层新鲜度 | `l7/scripts/freshness.py` | 0 | **过** | L0 1.7 天 / L1 1.5–2.0 天 / L2 2.5 天 / L3 1.0–1.7 天 / L4 1.1 天 / L5 2.4 小时 / L6 1.7 天；L1/L2/L3 查询档均「✅ 可调」 |

`kb_check` 维度：新鲜度 1.00 ｜ 三件套完整率 1.00 ｜ 一致性 1.00 ｜ **孤岛率 0.94（阈值 ≤0.2，超标）** ｜ 覆盖率 0.92（35/38，未命中 Q21/Q22/Q38）｜ 利用率 0.23 ｜ 幻觉率无数据。条目基线：消失 0 / 治理字段被原地改 0 / 正文有改动 0。验收契约 `content-governance-hostlib-20260923`：status `derived-view`、productionReady **false**，未达条件 3/3，阻断码 `OWNER_ACCEPTANCE_INCOMPLETE` / `FINAL_RECEIPT_MISSING` / `DATASET_NOT_BUSINESS_AUTHORIZED`。

## 二、逐层收口表（L0–L7）

「落盘档」指层侧落章件里 `dry_run` / `applied` 的实测值，不是脚本自述。

| 层 | 层闸门 | 最新层侧落章（run_id） | 时间 | 落盘档 | 收口判定 |
|---|---|---|---|---|---|
| L0 | 0 | `PIPE-20261003-2305-L0` | 10-03 23:10 | `dry_run=true / applied=false` | 闸门过；**本批未真落盘** |
| L1 | 0 | `REV-202610031826-momcozy-pump-L1` | 10-03 20:38 | `dry_run=true / applied=false` | 闸门过；**本批未真落盘** |
| L2 | 0 | `20261003-2117` | 10-03 21:17 | `dry_run=false / applied=true` | **已真落盘**（唯一真落盘的层） |
| **L3** | 0 | `20261002-2101` | **10-02 21:02** | `applied=true` | **❌ 收口未闭**（见 §四 F-1：候选件 10-02 22:45 被覆盖式重写，无 run 记录、无 rules.jsonl 归档、4 个治理字段消失） |
| L4 | 0 | `REVIEW-20261003-2311-吸奶器静音续航-L4` | 10-03 23:12 | `dry_run=true / applied=false`，`verdict=FAIL` | 闸门过；落章为预演，且自检 3 项 FAIL（已登记判据漂移） |
| L5 | 0 | `REVIEW-20261003-2311-吸奶器静音续航-L5` | 10-03 23:12 | `dry_run=true / applied=false`，`verdict=FAIL` | 闸门过（实质 4 项 PASS）；自检 2 项基线 FAIL（已登记） |
| L6 | 0 | `REVIEW-20261003-2311-吸奶器静音续航-L6` | 10-03 23:14 | `dry_run=true / applied=false`，`verdict=FAIL` | 闸门过（只读 4 项）；`vector_traceability` **真红待裁** |
| L7 | 0 | `REVIEW-20261003-2311-吸奶器静音续航-L7` | 10-03 23:14 | 记账件，`products=[]`、`layer_stamps_*` 全空 | **留痕未闭**（见 §四 F-4） |

逐层闸门全过 ≠ 逐层收口闭合：闸门读的是**库内数据形态**，收口读的是**「这一层这一批到底动没动、留没留痕」**。

## 三、最新批次逐层审计（`skill_invocation_audit.py` = 唯一那把尺子）

| BASE | L4 | L5 | L6 | L7 |
|---|---|---|---|---|
| `REVIEW-20261003-2233-吸奶器静音续航` | ✅ 红0 黄1 | ✅ 红0 黄1 | ✅ 红0 黄1 | ✅ 红0 黄0（豁免） |
| `REVIEW-20261003-2311-吸奶器静音续航` | ✅ 红0 黄1 | ✅ 红0 黄1 | ✅ 红0 黄1 | ✅ 红0 黄0（豁免） |
| `REVIEW-20261003-LISTING`（**进行中**） | ✅ 红0 黄1 | ✅ 红0 黄1 | ⚪ **no-data / 退出码 2** | ✅ 红0 黄0（豁免） |

- 黄 `E5` = 落章来自预演台账 ⇒ 只证明「逐层调用机制通了」，**不构成该层真落盘的证据**。
- LISTING 的 L6 尚未记账（命令级锁此刻被 `kb_pipeline.py` 持着），**该批未收口**。
- L7 在审计里被**显式豁免**（kb-check 不是 L7 的层主）⇒ L7 的绿**不是**收口证据，必须另看 `kb/l7/runs/<RUN>-L7.json` 的 `products` 与 `layer_stamps`。

结论报告侧：`kb/l7/reports/rv-20261003-231515.review.md`（BASE=2311）由引擎产出，判定主体 `文案合规审查`（mode=declared，本会话已加载 文案合规审查／产品宣称核验）。引擎 json（`/tmp/kb-review-rv-20261003-231515.json`）里四层留痕**齐备**（exit/红/黄/子会话 全有），但报告正文渲染成 `None`；飞书发布留痕 `published=None`（同批 21:27 那份为 `published=True`、`record=recvwWzL57nvYL`）—— 见 §四 F-4。

## 四、失败项清单（对象 ＋ 原因码 ＋ 要人做什么 ＋ 复开条件）

### F-1【真坏·高】L3 被覆盖式重写，**无层侧落章、无 rules.jsonl 归档**，4 个治理字段消失

**对象**：`kb/l3/candidates/rules.jsonl`（mtime 2026-10-02 22:45）

**已核事实**：
1. 现文件 1,018 行 / 2,778,872 B；每规则恰好 **2 行**，同一规则两行**只差 `article_no`**（一行空、一行有号）。
2. 冻结基线（`kb/.work/l6_integrity.json` → `checks.frozen_layers.l3_candidates`，checked_at **2026-10-02 00:10:57**）记：**2,036 行 / 5,762,300 B / sha256 `7d00454e…`**，max_mtime 2026-10-02 00:07:19。
3. 4 个治理字段：`half_life_days`、`valid_until` **键消失**（`grep -c` = 0）；`owner`、`effective_from` 键在但**值为空串**（非空 0/1018）。
4. 下游 `kb/l4/canonical/*.jsonl` 六个文件共 **1,365 行全部**仍含这 4 个字段（`grep -c half_life_days` = 1365）⇒ 上游丢、下游有。
5. **层侧落章停在 `kb/l3/runs/20261002-2101.json`（10-02 21:02）**；10-02 22:44/22:45 那次重写**没有 L3 run 记录**（同批只留 `kb/l2/runs/20261002-2244.json` 与 `kb/l3/_archive/rejected-pre-20261002-2244.jsonl`、`-2251.jsonl`、`20261002-2230-prewrite/`）。
6. `kb/l3/_archive/20261002-2230-prewrite/` 里**只有 `rejected.jsonl`**，没有 `rules.jsonl`；全库搜不到任何 2,036 行的 `rules.jsonl` 副本（最大为 `kb/l3/history/rules.jsonl.bak-20260923-180909` = 1,527 行）⇒ **那次重写不可回滚**。

**未判定（不许拿行数当结论）**：2,036→1,018 究竟是「去重」还是「丢证据锚点行」。现结构（原始行 ＋ L4 追加发号行）符合 `layers.yaml` L4 声明的 `'a'` 追加语义，故**行数减半本身不足以判坏**；但 4 字段消失与「无落章、无归档」两条是独立事实。

**要人做什么**：① 裁定 10-02 22:44/22:45 那次重写是否应当保留 4 个治理字段；若属误丢 → 走 `kb-repair`，从 L4 canonical 与 `kb/l3/registry/half-life-policy.json` 回填（**不许原地手改**，按 AP14 留痕）；② 补 L3 的 run 记录；③ 把「跑 L3 前归档 `rules.jsonl`（不只 `rejected.jsonl`）」写进层红线。
**复开条件**：`grep -c half_life_days kb/l3/candidates/rules.jsonl` > 0，且 `kb/l3/runs/` 出现覆盖该次重写的 run 记录。

### F-2【真坏·高】宿主视图落后权威库 3 天（`projection_reconcile` R1/R2/R4）

**对象**：`kb/view`（`kb_*` 工具读的就是它）

**已核事实**：视图 `.md` 与 `kb/view/_meta/derivation.json` 最后写入 **2026-09-29 11:27:21**；源 `kb/l3/candidates/rules.jsonl` 最后写入 **2026-10-02 22:45**。R4 = 2,036 处治理字段未传导（`owner`/`half_life_days`/`valid_until`/`effective_from` 各 509）。
**要人做什么**：重跑 `kb/.work/gen-host-library.py` 到 staging 后按修法回填（`.md` 只走 node / `/bin/cp` 通道 ＋ 读回校验）。
**复开条件**：`projection_reconcile.py` 六项全绿（R4 归零）。

### F-3【未判定＋参考红·中】路由对账无今日输入；参考跑暴露 AI 溯源成员不命中

**对象**：`l7/scripts/routes_reconcile.py`

**已核事实**：① 无输入 ⇒ 退出码 2（`winners` 为必填位置参数）；② 用 2026-09-29 旧赢家表**不加 `--alias`** ⇒ 逐条命中 **0/65**（表里是英文 id、赢家表是中文装载目录名）；③ 加 `--alias` ⇒ **60/65**、F1 0.923（≥0.90 门槛），但逐条仍 **5 条不一致**，全在 I 组（`AI溯源与权利审查`）：I1 被`视频安全审查`接走 ×3；I2 `NONE`×3；I3/I4 记为 `AI 溯源与权利审查`（**带空格**，与目录名 `AI溯源与权利审查` 不逐字相同）后转 NONE；I5 前两轮带空格名、第三轮被`图片安全审查`接走。
**要人做什么**：① 按 `kb-manage` 触发电测**重新生成今日赢家表**后再跑本闸门；② 裁定 I 组：`NONE` 是「无人接」还是「记录缺」；带空格的名字是**赢家表写法问题**还是 skill 装载名问题。
**复开条件**：存在今日 `<RUN>-routes-winners.json`，且 `routes_reconcile.py --alias` 逐条命中 65/65。

### F-4【留痕缺口·中】最新一批报告里四层留痕渲染成 `None`，飞书发布留痕为空

**对象**：`kb/l7/reports/rv-20261003-231515.review.md`

**已核事实**：报告正文写 `L4/L5/L6/L7：run=None ｜ exit=None ｜ 红=None ｜ 黄=None ｜ 子会话=None`、`飞书发布：published=None`；而同一跑的引擎 json（`/tmp/kb-review-rv-20261003-231515.json` → `evidence_meta.layer_preflight.details`）四层 `run/exit/红/黄/skill_sessions` **齐备**；同一格式的早一份报告 `rv-20261003-212705.review.md` 四层值齐备且 `published=True`。全库（含 `~/.dsh/skills` 已装 skill）**搜不到**产出该段落的渲染器 ⇒ 该段为**会话自组**，非引擎产物。
**要人做什么**：裁定「层前置/判定主体/发布」三段是否应改为引擎产物（`feishu_publish.render()` 只渲染 BASE/mode/红合计/会话一行，且读的是 `evidence_meta.layer_preflight`）；在改之前，报告里这几段**不得当留痕证据**。
**复开条件**：报告该段可由脚本复算，或明确标注「人工填写」。

### F-5【合法／已分类】`workflow_check` 三段 FAIL 的逐条定性

| 段 | 实测 | 定性 |
|---|---|---|
| ② 权威库 l0~l6 未被改动 | l0/l1/l2 `match_L5_baseline=true`；l3 前缀与整份均不匹配基线（`l3_lines=1018`） | **合法变红**（冻结基线 vs 活库）；**但 l3 那半段指向 F-1**，不是单纯漂移 |
| ③ 前序产物哈希（45 项） | 20 项 mismatch（l3 候选 / l4 registry / l5 registry+benchmark / l6 全套 / l7 skills·registry） | **合法变红**（活库在跑；其中 `l7/skills/**` 是 10-03 三防线改动） |
| ⑥ 文档可见性 | 4,948 md 中 511 不可读：`他人产物 hostlib` 510 ＋ `其他` 1（`./ci/out/gates-latest.md`） | **已分类**：510 = `.work/hostlib.bak-20260928-152220`（可再生）；1 = CI 产物 |

### F-6【时点风险】同库多会话并发

本次窗口内实测：`kb/l7/reports/` 出现 `CHK-*`／`HEALTH-*`／`REG-*`／`REPAIR-*` 共 10 份体检表（23:20–23:45，**来自其他会话**）；`kb/l7/runs/index.jsonl` 在 23:20–23:47 被追加 10 行；23:43 起另一会话持有 `kb/.work/.kb-loop-claim.json`（session `39a1b1dd…`、base `REVIEW-20261003-LISTING`），23:47:25 命令级锁 `.kb.lock` 由 `kb_pipeline.py` 持有（`run_id=REVIEW-20261003-LISTING-L6`）。
⇒ 本表是**时点快照**；「最新一批」在核对过程中已从 `REVIEW-20261003-2311` 推进到 `REVIEW-20261003-LISTING`。任何「某层已跑完」的结论都必须带 run_id ＋ 时间戳（`layers.yaml` L2 notes 的纪律）。

## 五、结论

- **8 个层闸门（L0–L7）全过**，6 道统一闸门里 ①②⑤ 过、③ 未判定（缺今日输入）、④ 合法／已分类红、⑥ 真漂移。
- **收口没闭上的层**：**L3**（真坏·高：无落章、无归档、4 字段消失）；**L7**（留痕缺口：报告四层留痕为 None、最新批 L7 段 `products=[]`）；**宿主视图层**（真漂移：落后权威库 3 天）。L4/L5/L6 本批只有**预演**落章，机制收口成立、**真落盘未成立**。
- **未判定项**（宁可标未判定，不猜）：2,036→1,018 的行数语义；I 组路由 5 条的归因（NONE vs 名字不逐字相同）；F-4 的根因。
