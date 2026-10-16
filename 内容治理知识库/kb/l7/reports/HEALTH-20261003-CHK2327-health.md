# 知识库体检表 · kb-check 体检档 · HEALTH-20261003-CHK2327

- **库根**：`/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理`
- **RUN / 时间戳**：`HEALTH-20261003-CHK2327` ｜ 2026-10-03 23:19:2x – 23:20:5x（CST）
- **档位**：**体检档**（§1 六道闸门一次跑完）；**不是**评审链的 L7 驱动循环档
- **产出的写盘**：仅 `kb/l8/workflow_check_HEALTH-20261003-CHK2327.json`（④ 无干跑档，跑即写，RUN 名隔离）
- **并发声明（重要）**：本次跑闸门时，**另有两个会话正在跑同一套闸门**
  （`ps` 实测 23:19–23:20：`workflow_check.py HEALTH-20261003-2320`、`workflow_check.py CHK-20261003-2319`、
  `skills_check.py`、`layers_check.py` 同刻在跑；`.work/publish.log` 23:19 仍在长）。
  ④/⑥ 的写盘目标都是 **RUN 名隔离**（`workflow_check_{RUN}.json`、`ingest_probe_{RUN}.mjs`、`wfcheck-{RUN}/`），
  `projection_reconcile.py` 不给 `--json-out` 时**不写盘** ⇒ 本次未观察到共享文件争用。
  **但 ④ 的读数本身依赖活基线文件**（见 §4），这一点不受 RUN 隔离保护。

---

## 1. 体检表（闸门 → 退出码 → 结论 → 证据）

| # | 闸门 | 命令 | 退出码 | 结论 | 证据（本次实测读数） |
|---|---|---|---|---|---|
| ① | 登记表自检 `l7/scripts/skills_check.py` | 同左 | **0** | ✅ **过** | 五类问题 1–5 **全 0**；本项目要用 **40 / 已装 40 / 还差 0**；未登记 selftest 62 条（**不算错误**）；3 跳过（12 个登记了 source 但未安装）；lark-base 属「本地版本超前 CLI」不告警 |
| ② | 层契约 `l7/scripts/layers_check.py` | 同左 | **0** | ✅ **过** | 层数 **8（应为 8）**；六类问题 **全 0**；DAG **非线形**（L2←L1,L0 ／ L3←L0,L2 ／ L4←L2,L3 ／ L5,L6←L0,L2,L3 ／ L7←L0,L3,L4,L5,L6）；无干跑档清单 0 条 |
| ③ | 路由对账 `l7/scripts/routes_reconcile.py` | 规定产物名（不存在） | **2** | ⚠️ **跑不了：缺输入**（脚本按设计硬拒，**不报绿**） | `kb/l7/reports/HEALTH-20261003-CHK2327-routes-winners.json` 不存在 → `环境错：赢家表不存在` + 提示「运行时产物、缺输入不得报绿」 |
| ③′ | 同上（strict 口径） | `... _eval-kb-manage/blind_v2.winners.txt` | **1** | ⚠️ **口径不符，非数据缺陷** | 逐条 **0/65** 一致 —— strict「只认逐字相等的成员 id」，而赢家表记的是**真实装载目录名（中文）**，期望值写的是 **英文 id**；`routes.yaml:173-194` 的 `dir_name_map` 就是为这层归一而存在 |
| ③″ | 同上（`--alias` 口径） | `... blind_v2.winners.txt --alias` | **1** | ⚠️ **红，但证据已过期** | **60/65**；5 条全在 `AI溯源与权利审查` 组（I1–I5）。赢家表 mtime **09-29 19:58**，而三个判定 skill 的 `SKILL.md` mtime **10-03 12:51** ⇒ **这份证据比被测对象旧 4 天**，不得当今日路由状态的结论 |
| ④ | 链路收口核验 `l8/workflow_check.py HEALTH-20261003-CHK2327` | 同左 | **1** | ❌ **混合红：②③ = 合法变红；其余 7 腿 PASS** | `kb/l8/workflow_check_HEALTH-20261003-CHK2327.json`。PASS ①④⑤⑥⑦⑧⑨ ／ FAIL ②③。装载位 **509 条 / 信封 0 / E001 None / E046 None / 健康分 79.1**；检索 4 查询全中（`W-2.1`→111、`合规替代`→509、`量子纠缠配色调参`→0） |
| ⑤a | 信封闸门 `tools/envelope_gate.py` | `python3 tools/envelope_gate.py` | **0** | ✅ **过（本次为「真绿」）** | 扫 **1817** 文件（`.py .txt .md`）→ **信封态 0**，读不到 0；**两读者交叉核对一致**（判据读者=消费方 Electron；对照读者=PATH node）⇒ 22:52 那次的「静默假绿」已被 22:59:29 的修复封堵 |
| ⑤b | 信封普查 `l8/envelope_census.py` | 同左 | **0** | ✅ **过** | 扫 **8688** 个 `.md`，node 侧读不到 **1079**（差值恒 4096），**全部已分类**：刻意归档 **569** ＋ 可再生的过期备份 **510** → `结论：OK`（**活路径 0**） |
| ⑥ | 投影一致性 `l8/projection_reconcile.py` | 同左（**不给 `--json-out`，纯只读**） | **1** | ❌ **真坏（投影漂移，未修）** | **3/6** 通过：✅ R3_id_set ✅ R5_manifest_bytes ✅ R6_tier_dir ／ ❌ **R1_source_sha256**（源 `rules` 在视图生成后变过 `f27a1409… → 743dc623…`）❌ **R2_entry_fingerprint**（509 条条目的权威规则已变）❌ **R4_governance_passthrough**（**2036** 处治理字段未传导：`owner`/`half_life_days`/`valid_until`/`effective_from` 各 509） |

**汇总**：**过 4 道**（① ② ⑤a ⑤b）｜**跑不了 1 道**（③，缺今日输入）｜**真坏 1 道**（⑥）｜**合法变红 1 道（2 腿）**（④ 的 ②③）。

---

## 2. 失败项清单（对象 + 原因码 + 要人做什么 + 复开条件）

| # | 对象 | 原因码 | 要人做什么 | 复开条件 |
|---|---|---|---|---|
| F1 | ⑥ 投影漂移（R1/R2/R4） | `PROJ-DRIFT` ｜ **真坏** | 重跑 `kb/.work/gen-host-library.py` 到 staging 后回填（脚本自带修法）；R4 另需确认生成器是否真从规则行读 `owner/half_life_days/valid_until/effective_from`（F8）。**交回 `kb-pipeline`**（kb-repair 不自行重跑派生链） | `projection_reconcile.py` **6/6 且 exit 0** |
| F2 | ④ leg②「权威库 l0~l6 未被改动」 | `BASE-DRIFT` ｜ **合法变红** | **不要"修"**（改基线＝伪造"未改动"）。漂移是「与 09-23 冻结快照比、而活库每天在长」，设计内；**要处理就重冻基线 / 重跑并重新记账**，属 `kb-pipeline` | 冻结基线与活库在同一**静止窗口**内重算 ⇒ 复跑转 `true` |
| F3 | ④ leg③「前序产物哈希（45 项）」 | `BASE-DRIFT` ｜ **合法变红（同族）** | 同上；20 项 mismatch **全是重建过的产物**（`l3/candidates/rules.jsonl`、`l4/l5/l6` registry 与索引、`l6/bm25/*`、`l6/vectors/*`、`l7/registry/l7.json`、`kb-content-review/SKILL.md` 与 `scripts/review.py`）。后两者正是 **10-03 有意打的入口闸门（防线1）** | 同 F2；另需 `kb-pipeline` 重跑并重新记账那 4 个 run 记录 |
| F4 | ③ 路由对账 | `NO-WINNERS-TODAY` ｜ **缺输入，非缺陷** | 按 `kb-manage` 的触发电测**重新生成今日赢家表**（≥65 条 × 3 轮），落到 `kb/l7/reports/<RUN>-routes-winners.json`；本 skill 不代跑 | 赢家表存在 **且** `--alias` 口径下逐条全轮命中 **≥ 0.90** |

**不是失败项但必须看得见的 3 条**：

1. ① 的「未登记 selftest 62 条」——**不算错误**（登记表说明如此）。
2. ④ leg⑨ 打印里带 `[E026] 内容质量分 52.1 < 60`，但该腿判 **PASS**，因为 `landed: []`（**没有真的落盘**，是干跑侧的探针）⇒ **E026 未被消费，不代表本次有低质条目入过库**。
3. ④ leg⑥ 判 PASS，其 detail 里 **`enveloped: 510`**，全部落在豁免桶 `他人产物 hostlib` —— 与 ⑤b 的「可再生过期备份 510」**是同一批**（两边独立读数一致，互为交叉验证）。**该腿的 PASS 建立在这条豁免桶口径上，不是"零信封"**。

---

## 3. 三种"红"的区分（按 `kb-check` §3 口径）

- **真坏**：**F1（⑥ 投影漂移）**。判据是「视图 ⇄ 权威库」的现值对账，不是冻结基线；修法明确、未修。
- **合法变红（基线漂移，非缺陷）**：**F2 / F3**（④ 的 ②③）。依据：`kb-repair/SKILL.md:59`、`kb-check/SKILL.md` §3 同口径、`l7/registry/skills.yaml:1148` note；且 `REPAIR4-20261003-health.md` 已**零变更复跑**证明「不修也照样红、红了不代表坏」。
- **判据缺陷 / 输入口径问题（不是数据缺陷）**：**F4（③）**。strict 那 65/65 是**口径产物**（`dir_name_map` 未生效）；`--alias` 那 5 条是**证据过期**（09-29 的赢家表 vs 10-03 的 skill）。**不许把这两者报成"路由表坏了"。**
- **已知判据缺陷台账（本 skill §2）本次复现情况**：`skills_check` 的 `~` 路径误报（**本次未触发**：第 4/5 类均 0 条）；`workflow_check` 第②段冻结基线（**复现，F2**）；`envelope_census` 只扫 `.md`（**设计如此**，⑤a 补 `.py/.txt`）；`projection_reconcile` 无干跑档（**本次用"不给 `--json-out`"实现零写盘**）。

---

## 4. 与今晚先前读数的差异（转绿是"修好了"，不是"改判据"）

今晚 22:47–23:13 有多份体检/修复单在先（`kb/l7/reports/HK-20261003-2247-health.md`、`GATE-20261003-225211-health.md`、
`REPAIR-20261003-2300-health.md`、`REPAIR4-20261003-health.md`）。与本次读数对比：

| 项 | 22:47–22:53 读数 | **本次 23:20 读数** | 差异归因（有据） |
|---|---|---|---|
| ② `layers_check` | 红（cwd 占位符判据自相矛盾） | **0 过** | `REPAIR-20261003-2300` §变更1：`layers_check.py` 修 `{kb_root}` 判定 |
| ⑤a `envelope_gate` | **假绿**（静默换读者，换读者即翻红 72） | **0 过，且两读者交叉核对一致** | 同上 §变更2：读者改为消费方 Electron ＋ 交叉核对不一致即报红（`tools/envelope_gate.py` mtime 22:59:29） |
| ⑤b `envelope_census` | 红：活路径 **73** 个信封 | **0 过**（全库 1152→**1079**） | 同上 §变更3：**84 个信封态文件改回明文**（逻辑内容 sha256 逐条断言不变，留底在 `kb/l8/_archive/enveloped-repair-20261003-225606/`） |
| ④ leg⑥ / leg⑦ | 红（不可读 510 ／ 判据过期） | **PASS** | §变更3 修文件 ＋ §变更1 修脚本 |
| ④ leg② | 红，且 `l0 match` 在两分钟内 **false→true 自己翻过一次** | 红（`l0/l1/l2 match=true`、l3 两条 false） | **活基线**：`kb/.work/l5_integrity.json` 本次跑前 **23:18:07** 才被重写（我 23:20:08 取数）⇒ **该腿读数不是稳定量**，见下 |
| ⑥ 投影 | 红（真坏，未修） | 红（真坏，未修） | 一致：两次都判真坏，均在等 `kb-pipeline` |

**⚠️ 读数稳定性告警（本次独立确认）**：④ leg② 的输入是 `kb/.work/l5_integrity.json` / `l6_integrity.json`，
而这两个文件正被**并发的其它会话**改写（`l5_integrity.json` mtime **23:18:07**，且 `REPAIR4` 实测它 23:06→23:11 被重写两次）。
⇒ **同一分钟不同会话跑 ④，leg② 可能给出不同读数**。引用该腿时必须带 RUN + 时间戳，不得当稳定结论。

---

## 5. 本次不能闭环的项（不许拿本次读数当"全绿"）

1. **③ 结构性无法在今天闭环**：它的输入是触发电测的**运行时产物**，全库**没有任何生成器**（本次 `find` 全库无
   `*routes-winners*`，也无任何 **2026-10-03** 之后的 `.winners` 文件）。本 skill §1 已写明「要今天的数据 ⇒ 先按 kb-manage 的触发电测重新生成赢家表」。
2. **本次 ③ 用的是替代输入**（**明示**）：`_eval-kb-manage/blind_v2.winners.txt`（**2026-09-29 19:58**，115 行）。
   它是**近 4 天前的**运行时产物，**只能当历史参考**，不能当今日路由达标与否的依据。
3. **L0–L3 未跑**（本 skill 不做供给链）：本次是**体检档**，不触发 L0→L7；F1 的修法要跑派生链 ⇒ **交回 `kb-pipeline`**。

---

*本报告由 `kb-check` 体检档产出（`RUN=HEALTH-20261003-CHK2327`）；本 skill 只报不改，修复动作走 `kb-repair`。*
