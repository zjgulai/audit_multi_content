# CHK-20261004-1352-REG-ROUTES-health —— 体检表（重点：registry ⇄ routes 一致性）

- **库根**：`/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理/kb`（`KB-ROOT.json` 所在层）
- **执行**：kb-check 体检档（人触发）；cwd = 库根父目录 `<库根>`
- **时间**：2026-10-04 13:48–13:54 CST
- **本次 RUN**：`CHK-20261004-1352-REG-ROUTES`
- **写盘声明**：本体检**未跑④**（理由见 §1 与 §4）；本文件是本体检唯一落盘物（`kb/l7/reports/`，新建、不覆盖）。
- ⚠ **并发声明**：本次运行期间**另有至少 5 个 kb-check 会话在同时写库**，证据：
  `kb/.work/kbcheck-CHK-20261004-{1344,1346,1347,1349-SUB,1353-G123,1355-G46,1358-SELF}` 在 13:51–13:53 持续被写入，
  `kb/l8/workflow_check_CHK-20261004-1347.json` 于 13:51 落盘。⇒ 本次**主动放弃④**（它会写 `kb/l8/`），
  且本报告只对「我实测到的时刻」负责。

---

## 1. 闸门体检表

| # | 闸门 | 命令 | 退出码 | 结论 | 证据 |
|---|---|---|---|---|---|
| ① | 登记表自检 | `sh kb/kbpy l7/scripts/skills_check.py` | **0** | **过**（真绿） | 五类问题 1=0 2=0 3=0 4=0 5=0；本项目要用 40、已装 40、还差 0；另有「未登记 selftest」62 条（不算错误）、12 个 `status=参考` 条目跳过副本比对 |
| ② | 层契约自检 | `sh kb/kbpy l7/scripts/layers_check.py` | **0** | **过**（真绿） | 8 层齐、六类问题各 0；DAG `L7 ← L0、L3、L4、L5、L6` |
| ③ | 路由表对账 | `sh kb/kbpy l7/scripts/routes_reconcile.py kb/l7/reports/<RUN>-routes-winners.json` | **2** | **跑不了 —— 缺输入**（非数据坏） | stderr：`环境错：赢家表不存在 …/kb/l7/reports/CHK-20261004-1348-REG-LAY-ROUTES-routes-winners.json`；`kb/l7/reports/` 下无任何 `*routes-winners*` 文件；全库唯一 `*winners*` 在 `_backups` / `_eval-*` / `_chk-run-*` 下 |
| ③′ | （补救跑）同上，喂 2026-10-04 12:46 的真实赢家表 `_chk-run-CHK-20261004-1250-CLOSE/winners-used.txt --alias` | **1** | **④ 路由表自检 = 0 条（静态一致性过）；① 逐条对账 = 5 条不一致** | 5 条**全部**是 `brand-ai-provenance-rights-review`（I1–I5）；逐条全轮命中 60/65；抢走者计数 `NONE 6 / brand-video-safety-review 3 / brand-image-safety-review 3 / CLARIFY 1` |
| ④ | 链路收口核验 | 未跑 | — | **未跑（主动放弃）** | ① `workflow_check.py:278` `json.dump(res, open(out,"w"))` = 必写盘；② 已有别的会话在 13:51 写同一目录；③ 与 registry⇄routes 主题正交 |
| ⑤ | 信封闸门 | `sh kb/kbpy l8/envelope_census.py` ／ `python3 tools/envelope_gate.py` | **0 / 0** | **过**（真绿） | 普查：扫 10438 个 `.md`、1079 个信封态**全部已分类**（刻意归档 569 + 可再生备份 510）；gate：2046 个 `.py/.txt/.md`，信封态 0、读不到 0、两读者交叉核对一致 |
| ⑥ | 投影一致性 | `sh kb/kbpy l8/projection_reconcile.py`（不带 `--json-out` = 只读） | **1** | **真坏（3/6 漂移）** | `R1_source_sha256 ❌`（`f27a14091b2bd782… → 743dc62398311b02…`）、`R2_entry_fingerprint ❌`（509 条）、`R4_governance_passthrough ❌`（2036 处 = owner/half_life_days/valid_until/effective_from 各 509）；`R3/R5/R6 ✅`。**与 registry⇄routes 无关**，单独交 kb-repair |

**三种红的归类**：真绿 = ①②⑤；缺输入 = ③（**不是**「65 条全不一致」）；真红 = ⑥；合法变红 = 本次未触发（未跑④）。
**判据缺陷**：本次未把任何工具 bug 报成数据缺陷（`~` 不 expanduser 那条在①里未触发：五类全 0）。

---

## 2. registry ⇄ routes 逐项对账（本次重点）

### 2.1 核过、**对得上**的（可复算）

| 检查 | 结果 | 证据 |
|---|---|---|
| `routes.yaml` 每个 `to` 都在 `skills.yaml` 登记 | **11/11 一致** | `routes.yaml:62-136` 的 11 个 `to` 全部命中 `skills.yaml` 的 `id` |
| `chains` 的 `entry`/`members` 都在登记表 | **3 链 11 成员全一致** | `routes.yaml:34-58` |
| 每条 route 都有 `not_for` | **11/11 有** | 对应 `routes_reconcile.py:290-292` 判据，④ 段 0 条 |
| `frozen_expectation.dir_name_map`（13） vs `skills.yaml` 的 `dir_name`（13） | **13/13 逐字一致** | `routes.yaml:177-190` ⇄ `skills.yaml:615,632,649,666,684,701,712,735,752,769,786,803,820` |
| 登记 `dir_name` vs `~/.dsh/skills/` 真实目录 | **13/13 目录存在** | 实测 `ls ~/.dsh/skills/` → `内容审查总控`、`送审登记`、…、`飞书审查流转` 全在；无英文 `brand-*` 残留（除 `brand-product-fact-curator`，见 2.2-ROUTE-03） |
| 冻结用例集 | **65 条 / 13 个期望成员 × 5 条**，与 `routes.yaml:23` 声称一致 | `/Users/lute/Desktop/skill/内容治理中文skill/_基线用例.json`（9871 B，2026-09-29 16:22） |
| 互斥点名首对（`文案合规审查` ⇄ `视频安全审查`）在正文里是否成立 | **成立**（各点名对方 1 次） | `~/.dsh/skills/文案合规审查/SKILL.md`、`~/.dsh/skills/视频安全审查/SKILL.md` |
| `skills.yaml` 的 `id` 唯一性 | **无重复、无空 id** | 71 条 |

### 2.2 **对不上**的（逐条给原始证据 + 行号）

#### REG-01（硬）供给链成员表与层契约对不上：3 个层主 skill 不在供给链成员里
- `routes.yaml:35`
  `members: [kb-pipeline, kb-l0-feishu, kb-canonical-lookup, kb-p0-check, kb-recall, kb-check, kb-repair]`（7 个）
- `layers.yaml` 各层 `skill:`（层主的**唯一真源**）：
  `L0`=`kb-l0-feishu`(`:109`)、`L1`=`[kb-ingest-extractor, kb-media-extractor]`(`:154`)、`L2`=`kb-ingest-extractor`(`:201`)、
  `L3`=`kb-clause-extractor`(`:238`)、`L4`=`kb-canonical-lookup`(`:294`)、`L5`=`kb-p0-check`(`:406`)、
  `L6`=`kb-recall`(`:452`)、`L7`=`kb-check`(`:539`)
- 集合差：**在 `layers.yaml` 当层主、却不在 `routes.yaml:35` 成员里的有 3 个** ——
  `kb-ingest-extractor`、`kb-media-extractor`、`kb-clause-extractor`（对应 L1/L2/L3）
- 这 3 个在 `skills.yaml` 里都是 `status: 生产 / scope: 本项目`：`:834-836`、`:850-852`、`:866-868`
- **数据本身不能自证谁对**：`chains.members` 的**语义未声明**（是「全部层主」还是「对外可路由的入口/查询型」？两张表都没写）。
  若本意是前者 ⇒ `routes.yaml:35` 漏 3 个；若本意是后者 ⇒ 该字段改个名/加注，否则每次对账都会撞。
  **需人裁定**。

#### ROUTE-01（硬）`mutual_not_for` 自称「对账器会核」，实测**零接线**，且漏掉 1 对
- 声明处 `routes.yaml:138`：`# ─── 互斥点名（硬约束，对账器会核）`，块体 `:140-165`，共 **7 对**
- 实现处 `routes_reconcile.py:327-332` 是**硬编码的 7 个元组**，**完全不读 `mutual_not_for`**：
  ```python
  checks = [
      ("kb-pipeline", "kb-l0-feishu"), ("kb-l0-feishu", "kb-pipeline"),
      ("kb-l0-feishu", "kb-review"), ("kb-pipeline", "kb-review"),
      ("kb-pipeline", "kb-canonical-lookup"), ("kb-pipeline", "kb-p0-check"),
      ("kb-pipeline", "kb-recall"),
  ]
  ```
- 实测接线：`grep -n 'mutual_not_for' kb/l7/scripts/*.py kb/l8/*.py tools/*.py` → **0 命中**
- 后果 ①：`routes.yaml:148-152` 的 `pair: ["文案合规审查","视频安全审查"]` **从未被核**（它是 7 对里唯一不在上面元组里的）
- 后果 ②：往 `routes.yaml` 加新 pair **不会改变任何检查结果** —— 该块是死配置（declared-but-never-read）
- **当前是否已出事**：**没有**。我手工核了这一对，两个 SKILL.md 各自点名对方（见 2.1 末行）。
  ⇒ 这是**潜在**缺口，不是既成缺陷；但「硬约束」四个字与「0 行接线」直接冲突，属**声明与实现不符**。

#### REG-02（硬）同一成员的 `status` 两处冲突：`kb-manage` 写「规划」，`skills.yaml` 写「生产」
- `~/.dsh/skills/kb-manage/SKILL.md:55-58`（成员 11–14，状态列逐字为「规划」）：
  `kb-ingest-extractor`(L1/L2)、`kb-media-extractor`(L1)、`kb-clause-extractor`(L3)、`brand-product-fact-curator`(L3)
- `~/.dsh/skills/kb-manage/SKILL.md:60`：`**成员 1–10 是"入口/组件"，11–14 是"规划中的供给侧成员"（\`status: 规划\`，\`trigger_keywords\` 留空 = 不参与路由）。**`
- `skills.yaml` 实际登记：`kb-ingest-extractor` `:836 status: 生产`；`kb-media-extractor` `:852 status: 生产`；
  `kb-clause-extractor` `:868 status: 生产`；`brand-product-fact-curator` `:884 status: 生产`
- 且这 4 个的 `trigger_keywords` **非空**（`:838`、`:854`、`:870`、`:886`），与 `:60` 的「留空 = 不参与路由」不符
- 全库 `status` 分布实测：`生产 59 / 废弃 1 / 参考 11`，**`规划` = 0**
- 连带：`skills.yaml` 的设计里 `status=候选/规划` 是「只登记不安装」的载体（`skills_check` 第 1b 类），
  既然 `规划=0`，**该机制当前恒空转**（1b 恒报 0 条）
- **需人裁定**：这 4 个到底装不装、参不参与路由。`kb-manage:55-58` 与 `skills.yaml:834-888` 必有一处要改。

#### ROUTE-02（硬）`routes.yaml` 的「现状」记载已陈旧，且与自己相邻两行矛盾
- **2a 层数自相矛盾**：`routes.yaml:50` 写四层 RUN `'<BASE>-L4 / -L5 / -L6 / -L7'`；
  `routes.yaml:51` 却写审计 `'skill_invocation_audit.py --run <BASE>-L{4,5,6}'`（**三层**）。
  代码侧实际是**四层**：`kb/l7/review-engine/core/with_kb_evidence.py:307`
  `LAYER_PREFLIGHT_LAYERS = ("L4", "L5", "L6", "L7")`，同文件 `:299-305` 注释明确
  「★ 2026-10-03 收紧：**L7 也进闸门**（原为 ("L4","L5","L6")）」，`:369` 帮助文本写 `--run <BASE>-L{4,5,6,7}`（L7 含在内）。
  ⇒ `routes.yaml:51` 的 `{4,5,6}` 是**收紧前的旧口径**。
- **2b 与同目录契约冲突**：`routes.yaml:52` 写
  `现状：**文字约束**，未落成代码级阻断（登记见 report-output-contract.yaml 的 GAP-RO-5）。`
  而 `kb/l7/registry/report-output-contract.yaml:277`（GAP-RO-5 的 `status`）写
  `主体已落地（2026-10-03：CLI 默认要求 ＋ API 等效留痕已部署）`；`with_kb_evidence.py:367-369` 的
  `--require-layer-preflight` 已**默认要求**（不给 BASE ⇒ `NEEDS_INPUT` / 退出码 3）。
  ⇒ 同一目录下两张表对同一件事的「现状」说法相反。

#### ROUTE-03（中）`routes.yaml` 自称「13 个 brand-* 是链内成员」，但结构里只装进了 1 个
- 声明 `routes.yaml:45`：`13 个 brand-* 是**消费侧子能力 / 链内成员**，不单独对外当入口；`
- 结构 `routes.yaml:43`：`members: [kb-review, kb-content-review, brand-content-review-agent]`
  ⇒ 3 个成员里 brand-* **只有 `brand-content-review-agent` 一个**，其余 **12 个不在链里**
- `routes:` 段（`:62-136`）的 11 个 `to` 里也没有这 12 个
- 但这 12 个是 `frozen_expectation`（`:173-194`）与 `measured_20260929`（`:198-255`）里**逐条计分的期望接走者**
- 它们的路由真源**只存在于 `kb-review` 正文的让位表**（实测：12 个中文名在 `~/.dsh/skills/kb-review/SKILL.md` 各命中 1–5 次）
- 另：`brand-product-fact-curator`（`skills.yaml:882-888`，`生产/本项目`）既不在任何 chain、也不在 `routes:` 段、也无 `dir_name`
- **对账方向缺口**：`routes_reconcile.py:283-298` 只核 **routes → skills**（`to`/`members` 是否登记过），
  **不核 skills → routes**（登记为生产的成员有没有路由去向）。而 `routes.yaml:11` 声明的规则也只写了前一个方向。
  ⇒ 方向上「单侧」，这 13 个成员的「无路由」**结构上不可见**（不是违反声明，是**无声明、无检查**）。

#### REG-03（中）同一事实三副本，且已出现 13 vs 14
- `routes.yaml:177-190` `dir_name_map` = **13 条**
- `kb/l7/scripts/routes_reconcile.py:43-64` `ALIAS` = **14 条**（多一个键 `内容审查总控旧`，`:63`）
- `_eval-kb-manage/kb_routes_score.py` 的 `ALIAS` = **14 条**（与 `routes_reconcile.py` 逐键逐值相同，实测 `==` 为 True）
- 当前**值没漂**：13 个共有键的取值三处一致（我按 AST 取值比对，`同键不同值: []`）
- 但**同一事实写在 3 处**（1 份 YAML + 2 份代码字面量），违反本库「同一事实只写一处」的纪律；
  且已经产生 13/14 的**条数分歧**（`routes_reconcile.py:59-62` 的注释自认这是「两个打分器口径不一致」的源头，靠人工同步维持）

#### 双写漂移（口径未声明 —— 只报事实，不判缺陷）
- `not_for` 在 `skills.yaml` 与 `routes.yaml` **两处都写**：11 个已路由成员的 `not_for` **11/11 逐字不同**
  （例：`kb-l0-feishu` skills.yaml 6 条 / routes.yaml 2 条；`kb-content-review` 13 条 / 2 条）
- `skills.yaml` 的 `trigger_keywords` 与 `routes.yaml` 的 `say` 是同一事实两处写，交集偏低：
  `brand-content-review-agent` 7 条 vs 5 条、**交集 1**；`kb-canonical-lookup` 10 vs 5、**交集 2**；
  `kb-p0-check` 11 vs 4、**交集 2**；`kb-manage` 17 vs 8、**交集 3**
- **没有任何契约要求这两处逐字相等**（`routes_reconcile.py:290` 只要求 `routes.yaml` 侧 `not_for` 非空）
  ⇒ 我**不判它是缺陷**；但两侧对同一句提示词给出不同触发依据，属**口径未声明**，需人定：以哪侧为准。

---

## 3. 失败项清单（对象 + 原因码 + 要人做什么 + 复开条件）

| 原因码 | 对象 | 要人做什么 | 复开条件 |
|---|---|---|---|
| `REG-01` | `routes.yaml:35` ⇄ `layers.yaml:152-238` | 裁定 `chains.supply.members` 语义；若「全部层主」则补 3 个 skill；若「入口/查询型」则给该字段加语义注释 | 两张表对「供给链成员」给同一答案，或字段语义写明并被接受 |
| `ROUTE-01` | `routes.yaml:138-165` ⇄ `routes_reconcile.py:327-332` | 二选一：① 让对账器**读** `mutual_not_for` 逐对核（含 `文案合规审查⇄视频安全审查`）；② 把 `routes.yaml:138` 的「对账器会核」改成「人工核」 | `grep mutual_not_for` 在检查脚本里非 0 命中，或声明改成与实现相符 |
| `REG-02` | `kb-manage/SKILL.md:55-60` ⇄ `skills.yaml:834-888` | 裁定这 4 个成员是「规划」还是「生产」；一致后同步另一处（含 `trigger_keywords` 是否留空） | 两处 `status` 相同，且 `skills_check` 第 1b 类能反映真实规划数 |
| `ROUTE-02` | `routes.yaml:50-52` | 把 `{4,5,6}` 改成 `{4,5,6,7}`；把「现状：文字约束」改成与 `report-output-contract.yaml:277` 一致 | `routes.yaml` 与 `with_kb_evidence.py:307` / GAP-RO-5 `status` 三处口径一致 |
| `ROUTE-03` | `routes.yaml:43,45` ＋ 12 个 brand-* ＋ `brand-product-fact-curator` | 二选一：① 把 12 个 brand-* 补进 `chains.review.members`；② 把 `:45` 的「链内成员」改成「由 `kb-review` 让位表分派、不在本表列条目」。并决定 `brand-product-fact-curator` 的去向 | `chains.review.members` 与 `:45` 的措辞一致；13 个成员的去向在静态真源里可见 |
| `REG-03` | `routes.yaml:177-190` ＋ `routes_reconcile.py:43-64` ＋ `kb_routes_score.py` | 定一个真源，另两处改为从真源读取（或生成） | 三处不再有独立字面量，或条数不再分歧 |
| `DIR-01` | `kb/l7/reports/` 缺 `*routes-winners*` | 决定赢家表放哪、谁生成；或把③的输入契约改成指向既有产物目录 | ③ 能从 `kb-check` 正文规定的路径跑起来（退出码 0/1，而非 2） |
| `PROJ-01` | `kb/view` ⇄ 权威库（R1/R2/R4） | 走 `kb-repair`（与本次主题无关，单独开单） | `projection_reconcile.py` 6/6 通过 |

---

## 4. 未跑与未判定（不许猜）

- **④ 链路收口核验**：**未跑**。理由（三条都成立）：`kb/l8/workflow_check.py:278` 必写盘；运行期已有别的会话在 13:51 写同一目录（并发纪律）；与本次 registry⇄routes 主题正交。⇒ 本次**不声明**「八层闸门全过」。
- **③ 的今日数据**：**拿不到**。`kb-check`/`kb-manage` 正文规定的产物名 `kb/l7/reports/<RUN>-routes-winners.json` 全库无生成者，实测 `find` 无任何该名文件。我用的赢家表是 **2026-10-04 12:46** 的历史产物，**不构成「今天路由仍是这样」的证据**；§1 ③′ 的 5 条不一致只说明**那份表**当时的状况。
- **⑥ 的真红**：与 registry⇄routes 无关，本次**只记录不归因**。
- 本体检**未跑任何写档引擎、未加 `--apply`、未删任何锁/副本**。

---

## 5. 结论一句话

registry 侧的**结构自检是绿的**（① ② 过，`routes.yaml` 的每个 id 都能在 `skills.yaml` 找到、13 个 `dir_name` 与磁盘目录 13/13 一致）；
但 **registry ⇄ routes 这两块「对不对得上」这件事，恰恰是全套闸门里唯一没有闸门覆盖的方向** ——
③ 因为缺赢家表**跑不起来**（退出码 2），且它的④段只核 `routes → skills` 单向；
在这个盲区里实测出 **4 处硬性不一致**（`REG-01` 供给链少 3 个层主、`ROUTE-01` 声明「会核」实际零接线并漏 1 对、
`REG-02` 4 个成员状态两处相反、`ROUTE-02` 陈旧口径且相邻两行自相矛盾）。
