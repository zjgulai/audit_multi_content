# 体检表 ｜ CHK-20261004-0124-KBCK ｜ 2026-10-04 01:23–01:31

- **库根**：`/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理`（cwd = 库根）
- **档位**：`kb-check` §1 **体检档**（六道统一闸门）＋ 插件体检 `kb_check` ＋ L0 判定档 ＋ `ci/out` 既有读数
- **纪律**：只报不改。未传 `--apply`，未改 `kb/l0…l7` 数据与台账，未发布任何东西到飞书
- **落盘产物**：① 本表 `kb/l7/reports/CHK-20261004-0124-KBCK-health.md`；
  ② 逐条失败清单 `kb/l7/reports/CHK-20261004-0124-KBCK-failures.tsv`（2682 行：E026 454 ／ W020 2218 ／ W021 10，列 = `code / 条目 id / 分数或对端`）；
  ③ `kb/l8/workflow_check_CHK-20261004-0124-KBCK.json`（④ 无干跑档，按设计写盘）。
  ★ ②③ 均经 node 读回逐字节校验，两读者（python / node）读数一致、无 4096 字节信封

---

## 0. 一句话结论

**跑完六道闸门 + 插件体检 + L0 判定档：过 4（①②⑤a⑤b）、真坏 2 类（⑥ 投影、L0）、
未判定 1 道（③，缺今日赢家表）、合法变红 1 道（④ 的 ②③）。**
插件 `kb_check` 判 **不通过**（健康分 **79.1**，熔断线 60 未触；判失败的直接原因是 **454 条 E026 非空**）。
**六道闸门里没有一条是「脚本坏了」**；红闸门都有已登记的处置条目（见 §3）。
另有**并发风险**：另一个会话在 01:24 起跑同一套闸门（见 §5）。

---

## 1. 闸门读数

| # | 闸门 | 命令（cwd = 库根） | 退出码 | 判定 | 关键读数 |
|---|---|---|---|---|---|
| ① | 登记表自检 | `sh kb/kbpy l7/scripts/skills_check.py` | **0** | ✅ 过 | 五类 `1=0 2=0 3=0 4=0 5=0`；本项目要用 40 / 已装 40 / 还差 0；未登记 selftest 62 条（不算错） |
| ② | 层契约自检 | `sh kb/kbpy l7/scripts/layers_check.py` | **0** | ✅ 过 | 层数 8；六类全 0；引擎路径存在、cwd/解释器/DAG 扇出合规 |
| ③ | 路由表对账 | `sh kb/kbpy l7/scripts/routes_reconcile.py kb/l7/reports/CHK-20261004-0124-KBCK-routes-winners.json` | **2** | ⚠️ **未判定（缺今日输入）** | 赢家表不存在 ⇒ 按设计 exit 2，不报绿、也不静默按「全不一致」跑 |
| ③b | 同上（**参考口径**，非今日判定） | `… routes_reconcile.py --alias _eval-kb-manage/blind_after_r4.winners.txt` | **1** | ⚠️ 参考读数 | 逐条全轮命中 **60/65（92.3%）**；不一致 **5 条全在 I 组**；赢家表是 2026-09-29 19:32 的，已 5 天 |
| ④ | 链路收口核验 | `sh kb/kbpy l8/workflow_check.py CHK-20261004-0124-KBCK` | **1** | 🟡 **9 段 2 红（②③）→ 合法变红** | 装载位 509 / 信封 0 / 健康分 **79.1** / 检索 `[111, 1, 509, 0]`；⑥⑦⑧⑨ PASS |
| ⑤a | 信封闸门（.py/.txt/.md） | `python3 tools/envelope_gate.py` | **0** | ✅ 过 | 扫 **1861** 个文件｜信封态 **0**｜两读者交叉核对一致 |
| ⑤b | 信封普查（.md） | `sh kb/kbpy l8/envelope_census.py` | **0** | ✅ 过 | 扫 8734 个 `.md`，1079 读不到，**全部已分类**（刻意归档 569 ＋ 可再生备份 510） |
| ⑥ | 投影一致性 | `sh kb/kbpy l8/projection_reconcile.py` | **1** | 🔴 **真坏 3/6** | ❌ `R1_source_sha256` ❌ `R2_entry_fingerprint`（509 条）❌ `R4_governance_passthrough`（`owner`/`half_life_days`/`valid_until`/`effective_from` 各 509 = **2036 处**）；✅ R3/R5/R6 |
| — | 插件体检 `kb_check` | 工具调用 | — | 🔴 **不通过** | 健康分 **79.1**；E026 **454** ｜ W020 **2218** ｜ W021 **10** ｜ H005 1；孤岛率 **0.94**；验收契约 3 项未达 |
| — | L0 判定档（额外取证） | `sh kb/kbpy l7/scripts/l0_gate.py` | **1** | 🔴 **真坏** | 一致 612 ｜ 飞书多 10 ｜ 值变 0 ｜ **拉取失败 2** ⇒ 真差异 **2** |
| — | CI 12 把（**不是本次 RUN**） | `ci/out/gates-latest.md` @ **2026-10-04T01:18:27** | 1 | 🔴 红 `l0` 一把 | 过 11/12；其余 11 把全 PASS |

**③ 的口径说明（别把参考读数当通过）**：`routes.yaml` 用英文 canonical id（`brand-ai-provenance-rights-review`），
赢家表用中文装载目录名（`AI溯源与权利审查`）。**不加 `--alias` 会得到 0/65，那是口径差异、不是路由全坏**；
加了 `--alias` 得 60/65。**本次正式结论仍是「未判定」**（缺本次 RUN 产出的赢家表）。

**④ 的 9 段逐段**：`PASS ①环境与版本纪律` ｜ `FAIL ②权威库 l0~l6 未被改动` ｜ `FAIL ③前序产物哈希（45 项，实测 mismatch 20 项）` ｜
`PASS ④分层库→生成器→视图` ｜ `PASS ⑤装载位→加载器` ｜ `PASS ⑥文档可见性` ｜ `PASS ⑦消费侧 skill 可用` ｜
`PASS ⑧工作台与服务` ｜ `PASS ⑨写入侧`（⑨ 内含 `[E026] 内容质量分 52.1 < 60`，落盘 0 个、信封 0）。

---

## 2. 已转绿（对照 2026-09-30 那轮）

| 上轮 F# | 上轮问题 | 本轮读数 |
|---|---|---|
| F1/F2 | `kb-media-extractor` / `kb-l0-feishu` 副本不一致 | ① 第 3 类 = **0** |
| F3/F4 | 两个活路径信封文件 | ⑤a/⑤b 活路径信封 = **0** |

---

## 3. 失败项清单（对象 + 原因码 + 要人做什么 + 复开条件）

> 「要人做什么 / 复开条件」一律取 `kb/l7/registry/failure-playbook.yaml` 与各 registry 的**既有登记**（真源，不现编）；
> 没有登记条目的，**照实写「无登记处置」**，不给自造办法。

| # | 对象 | 原因码 | 要人做什么 | 复开条件 |
|---|---|---|---|---|
| F1 | 飞书两张表：`专家修订汇总表 tbl8AI00JZO1iZtp`、`内容公式（仅供参考） tblVdl0jdK9G4ld3` | `gate_red.L0`（真差异 2 条，未声明） | **内容治理数据组（刘华丽）**。先读 `l0-expected-diffs.yaml → resolved[EX-2/EX-3] → observed_20261004`；再用 `lark-cli auth status --profile dsh-kb` 把「bot 那条路出了新问题」与「bot 与回落身份**同时**不可用」分开（该字段不在时两种可能都有）。**禁**：把 `pull_failed` 写进 `expected` 声明掉；改 `align_l0_feishu.py` 把 `pull_failed` 摘出去 | `kb/kbpy l7/scripts/l0_gate.py` **退出 0** |
| F2 | `kb/view` ⇄ 权威分层库（`kb/l3/candidates/rules.jsonl` 等） | `gate_red.projection_reconcile`；根因 = `finding.l3_governance_backfill_lost` | **L3 层主（数据面）＋ 维护 `kb/l7/registry` 的人（登记面）**。**报批后**按序：① 重跑 `kb/.work/fix_f7_backfill.py`；② 补一条 L3 run 记录（本次丢失正是「改了没落章」）；③ 重出投影视图；④ 复跑 `l3_gate` + `projection_reconcile`。**禁**：按脚本自带的 `fix` 提示直接重生成视图（R4 照样红，且逐条治理值被降级为常量、有效期时钟归零）；只补 `l3.json` 声明让它与空字段「对上」；静默改小 `half-life-policy.json` 的 scope | `fix_f7_probe` 显示四字段 **509/509 非空**，且 `projection_reconcile.py` **退出 0**（R1/R2/R4 同时绿） |
| F3 | `3_措辞表达库/L1-facts/` **454 个 md**（逐条清单见本 RUN 的 `…-failures.tsv` 的 `E026` 段） | `E026` 内容质量分 < 60（长度项普遍 1.5–2.8/20；分域 52.5–59.9） | **业务裁决（判归人）**：调派生阈值 **或** 补正文 —— 属「派生正文太短」的口径问题。**不是 `kb-repair` 能改的** | 插件 `kb_check` 结论 = **通过** |
| F4 | 疑似重复 **2218 对**，涉 190 主体条目 / 199 对端；连通分量 **12** 个，最大分量 **334 条**（占全库 509 的 66%） | `W020` | **人裁**（机器只报疑似）。二选一：合并（**新建 + `supersedes` 留痕，不许原地改写**）／把两者分工写进 `summary`。★ `failure-playbook.yaml` **没有 W020 条目** ⇒ 按纪律「**没有登记的处置办法**」，这里不给自造流程 | `kb_check` 的 W020 = 0，或逐簇登记为**已裁决**（`_meta` 有裁决留痕） |
| F5 | `cg-r-0384cb5e3fac494a`（W-2.4）与 9 条对端 | `W021` 疑似数值矛盾 ×10；键 `recvunn`（疑似字段名被截断/串行）＋ `命中表达`；取值不相交（6 vs 4、1 vs 2/3） | **人裁**：走 `governance.yaml` 裁决。**禁**：自动裁决 | 10 条归零，或登记为**已裁决/已撤回** |
| F6 | 全库条目引用关系 | 孤岛率 **0.94**（阈值 ≤ 0.2）；**472/509** 条无任何真实引用关系 | **来源表需提供真实关联列**（业务动作）—— 现值的 0.94 是 2026-09-29 按人确认的 W025 处置 B **去掉了合成边之后的真值** | 孤岛率 ≤ **0.2**（`_meta/health.yaml → alerts.island.max_ratio`） |
| F7 | `kb/view/_meta/acceptance.yaml`（`content-governance-hostlib-20260923`，owner **刘华丽**） | `OWNER_ACCEPTANCE_INCOMPLETE`、`FINAL_RECEIPT_MISSING`、`DATASET_NOT_BUSINESS_AUTHORIZED`；谓词 `no_duplication=false`（复用 W020 判据） | 补 **owner 人工验收**（`l4/canonical` 1365 条是**机器晋升**、人工抽查未做）＋ **final receipt** ＋ 把 `fixed_eval_set` 从 `missing` 补齐并取得业务授权 | `conditions` 三项不再为 `未建`/`missing`，`blocked_codes` 清空（`productionReady` 才可置 true） |
| F8 | `AI溯源与权利审查`（**注意**：装载目录名无空格；赢家表里记的是带空格的旧名） | 路由不一致：该成员 **0/5 条 ｜ 0/15 轮**，冻结基线 F1 **0.440 < 0.90**；不一致 5 条**全在 I 组**（I1 被「视频安全审查」抢走、I2 三轮全 `NONE`、I3/I4 第三轮 `NONE`、I5 被「图片安全审查」抢走） | **待裁**（`routes.yaml → known_conflict`）。已登记的根因：① `I1`↔`G3` 近重复；② **`I5`↔`F5` 近重复（登记为主因）**；③ `I2` 欠定义。**v2 改用例实验已执行且更差（0.222）**，登记结论是「**不再改用例、也不再调 description**」⇒ 现在缺的是**人拍板**：改用例集／接受该成员未过／合并或停用该成员。★ 另需先决定**是否重跑触发电测**产出今天的赢家表（否则 ③ 永远是「未判定」） | 用**本次 RUN** 的赢家表复跑，③ ① 节 = 0，且该成员 F1 ≥ **0.90** |
| F9 | `kb/l7/registry/l7.json` | `gate_red.workflow_check`（③ 内的**真发现**） | 该项是「原地改写未落章、计数落后现库」——**开闸后**跑 `kb/.work/l7_article_source_refresh.py <RUN> --apply` 并补 L7 run 记录。**禁**：改历史 run 记录里的 artifact sha（伪造台账）；把 L3 回滚到 1527 行时代；就地改宽 ②③ 判据而不同时报批 | ④ 改判据后复跑 **exit 0**；或本轮只做登记 ⇒ 结论写「**基线漂移，非缺陷**」并附回归文件与原始读数 |
| F10 | `_meta/index-status.yaml` | `H005`（提示级，**不是错误**） | 想得起就补：`index.status` 仍是 `candidate`、`version_key` 未声明 ⇒ **检索排序未经 UAT 复核，别当定稿** | `index.status` 转正 + 声明 `version_key`，或保持 `candidate` 但**别把排序当定稿** |
| F11 | 全库运行窗口 | `external_writer`（本次实测） | **同一时间只准一个会话跑这条循环**。跑前认领：`sh kb/kbpy l7/scripts/kb_loop_claim.py claim --base <BASE>`（**exit 3 = 已被占，停下来别抢**），跑完 `release`。**禁**：按 BASE 分槽（会放回双计事故） | 连续两次 `kb_pipeline.py --check` 的**零写自证都是 True** |

### 不算失败、但要知道的

- **④ ②③ 是合法变红**（活库模式下拿 09-23 冻结基线比对；`l3_base1018_matches_L6=false` / `l3_whole1527_matches_L4=false`；
  ③ mismatch 20 项含 `l3/candidates/rules.jsonl`、`l4/registry/l4.json`、`l6/**` 多数文件、`l7/skills/kb-content-review/**`）。
  ②③ 属**已登记判据漂移 ⇒ 无需修数据**；要它们转绿必须**改判据，单独走一轮**。
- **健康分 79.1 未触熔断（60）**；判失败的直接原因是 **454 条 E026 非空**（源码判据 `~/.dsh/plugins/dsh-kb/lib/index.js:648` → `ok = errors.length===0 && !breaker`）。孤岛率 0.94 只标 `!!`，不改变 `ok`。
- **利用率 0.23（≤0.3 ✅）**：累计 518 次查询、零结果 120 次（23.2%）、**从未被命中 426/509** ⇒ 冷条目靠**扩充词表 / 补 asks 关键词**解决，**不要靠删**。
- **覆盖率 0.92（≥0.8 ✅）**：35/38 黄金题命中；未命中 Q21、Q22、Q38；这是**召回**、不是「能答」。
- **未判定项（不猜）**：④ leg④/⑤ 的 `entries_fm_ok = 453/509`（56 条差）**没有任何闸门判它**，用途未知 —— 本次**不判定**。

---

## 4. 判据缺陷（工具/skill 的问题，不是数据缺陷）

| # | 位置 | 实测 | 影响 |
|---|---|---|---|
| D-1 | `kb-check` §1 ③ 写 `<RUN>-routes-winners.json` | 脚本要的是**赢家表 `.txt`**（`<id>\|<r1>\|<r2>\|<r3>`）；`kb/l7/reports/` 下**从无**此类文件，全库只有 `_eval-kb-manage/*.winners.txt` | ③ 结构性无法按 skill 原样跑 ⇒ **永远「未判定」**；应修 skill 的路径与说明 |
| D-2 | 不加 `--alias` 的默认口径 | 英文 id（`routes.yaml`）vs 中文装载名（赢家表） ⇒ **0/65** | 会把口径差异误报成「路由全坏」 |
| D-3 | 赢家表里 `AI 溯源与权利审查`（**带空格**） | 装载目录名是 `AI溯源与权利审查`（**无空格**，2026-09-30 已改名）；`routes.yaml:186` 的 `dir_name_map` 也是无空格 | I3/I4 的「不一致」里有一部分是**名字空格**造成的；判据未对赢家表侧做同一归一 |
| D-4 | `kb/l8/envelope_census.py` | **只扫 `.md`**；`.py`/`.txt` 要另跑 `tools/envelope_gate.py` | 两个脚本互补，谁也替代不了谁 |

---

## 5. 并发实测（必须上报）

本次体检窗口内，**另一个会话**在 01:24 起跑了**同一套**六道闸门（`_chk-run-CHK-20261004-0125/`）、
**两路** `ci/run_gates.py`（其中一路 `--outdir ci/out`）、以及多处 `kb_pipeline.py --check`。
它先跑 `3a-routes-missing` 得 **exit 2**、`3b-routes-oldref` 得 **60/65**、`4` 得 **exit 1**、`5a/5b` 得 **0**、`6` 得 **3/6** ——
**与本次逐条读数一致**（可复现性证据），但这正是本库纪律点名的场景：
**同一时间只准一个会话跑这条循环**（否则 `l7/runs/index.jsonl` 会双计、后跑者覆盖前者的记账行）。

---

**本次体检未修改任何闸门相关文件，未修复任何失败项。修复请走 `kb-repair`；涉及 `kb/l0…l6` 数据或台账的修法一律先停、报批。**
