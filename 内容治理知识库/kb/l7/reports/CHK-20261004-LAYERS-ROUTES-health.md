# 体检表 · 层契约与路由表核验 · 2026-10-04

**库根**：`/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理`
**权威库真身**：`kb/`（`KB-ROOT.json` 在 `kb/KB-ROOT.json`）
**口径**：`kb-check` 体检档（只报不改，全程零写库）
**本单直接回答**：① 8 层齐不齐 ② cwd / 引擎路径在不在 ③ 实际被谁接走 vs 路由表写谁

---

## 一、闸门结果

| 闸门 | 命令 | 退出码 | 结论 |
|---|---|---|---|
| 层契约（8 层 / cwd / 引擎路径 / DAG） | `kb/kbpy l7/scripts/layers_check.py` | **0** | 过 · 六类问题合计 0 |
| 登记表自检 | `kb/kbpy l7/scripts/skills_check.py` | **0** | 过 · 五类问题合计 0 |
| 路由表对账 | `kb/kbpy l7/scripts/routes_reconcile.py <赢家表> --cases _eval-kb-manage/cases_v2.json --alias` | **1** | 有对账不上 · 6 条（经归因仅 1~2 条需人裁） |
| 路由表自检（④ 节） | 同上（内置） | — | **0 条**：11 条 routes 的 `to` 全在登记表、chain 成员与入口全在册、7 组互斥点名在 SKILL.md 里逐字命中 |

### 1. 8 层齐不齐 —— 齐

`layers.yaml` 解析出 **8 条层记录**（应为 8），层完整性、必填 12 字段、引擎路径、cwd/解释器、DAG、干跑档**六类全 0**。

| 层 | `skill`（正文口径唯一真源） | `skill_write` | cwd | python | envelope |
|---|---|---|---|---|---|
| L0 | kb-l0-feishu | true | `{kb_root}` | `${KB_PYTHON}` | required |
| L1 | kb-ingest-extractor, kb-media-extractor | true | `{kb_root}` | `${KB_PYTHON}` | required |
| L2 | kb-ingest-extractor | true | `{kb_root}` | `${KB_PYTHON}` | required |
| L3 | kb-clause-extractor | true | `{kb_root}` | `${KB_PYTHON}` | required |
| L4 | kb-canonical-lookup | true | `{kb_root}` | `${KB_PYTHON}` | required |
| L5 | kb-p0-check | true | `{kb_root}` | `${KB_PYTHON}` | required |
| L6 | kb-recall | true | `{kb_root}` | `${KB_PYTHON}` | required |
| L7 | kb-check（跨层闸门，非层主） | **false** | `{kb_root}` | `${KB_PYTHON}` | required |

- **cwd 约定一致**：8 层全为 `{kb_root}`，检查器实测解析为本次库根，与 `KB-ROOT.json` 所在层一致。
- **引擎路径抽查（独立复算，不信工具自报）**：**30 个 engine 条目逐个 `os.path.exists`，缺失 0**。
  所用解释器 = `${KB_PYTHON}`，8 层一致。
- **DAG 非线形**（合格）：L2←L0,L1；L3←L0,L2；**L4←L2,L3；L5←L0,L2,L3；L6←L0,L2,L3**；L7←L0,L3,L4,L5,L6。
- 无干跑档清单：**0 条**。
- L7 `skill_write=false`，与全局规则「L7 是跨层闸门、不是层主」一致。
  `skill_note` 写明：`kb-check` 注册表 layer 记「—」，「层↔skill 双向一致」判据对它**豁免**。

### 2. 登记表 —— 过

已装 40/40、应装未装 0、装了没登记 0、副本不一致 0、依赖缺失 0、自测缺失 0。
装载位 `~/.dsh/skills` 扫到 59 个目录；登记表 71 行（本项目 52 + 宿主通用 19）。

---

## 二、路由表对账（实际被谁接走 vs 路由表写谁）

### 2.1 本次用的是什么输入 —— 必须看清

- `routes_reconcile.py` 的**默认**用例表是 `~/Desktop/skill/内容治理中文skill/_基线用例.json`（65 条，2026-09-29 16:22）。
- **库内不存在任何 `<RUN>-routes-winners.json`**（`kb/l7/reports/` 与 `kb/l7/runs/` 均无，全库 `find` 为空）。
  ⇒ 按 `kb-check` 正文原文命令跑，实测 **退出码 2 / 环境错：赢家表不存在**（不是假绿，是缺输入硬拒）。
- 真实赢家表是**库外**运行时产物：`_eval-kb-manage/blind_v2.winners.txt`（115 条，**2026-09-29 19:58**）。
  与之配套的用例表是 `_eval-kb-manage/cases_v2.json`（115 条）——**id 与赢家表逐条对齐，缺 0**。
  默认 65 条用例的 id **全部**能在该赢家表里对上，故默认表也可用，只是覆盖窄一半。
- ⚠️ **赢家表是 5 天前的快照**。本节回答的是「09-29 那轮实际被谁接走」，**不是「今天被谁接走」**。
  09-30 之后库里有实质改动（AI 成员改名、L7 判据登记、workflow_check 修复），本节结论无法覆盖。

### 2.2 逐条结果

- **逐条全轮命中：109/115**（逐轮口径 353/345 中 344 命中）。
- 不一致 6 条；被抢走计数：NONE 6 次 / 视频安全审查 3 / 图片安全审查 3 / **AI 溯源（带空格）2** / CLARIFY 1 / kb-pipeline 1。
- 22/23 个成员全轮 15/15 命中；`kb-manage` 14/15；`AI溯源与权利审查` 0/15。

### 2.3 6 条不一致的归因（逐条定性，不合并）

| 用例 | 期望 | 实际（3 轮） | 定性 |
|---|---|---|---|
| I1 | AI溯源与权利审查 | 视频安全审查 ×3 | **合法/已知用例歧义** — `routes.yaml` 已登记 I1↔G3 近重复（同一意图两个归属） |
| I2 | AI溯源与权利审查 | NONE / 图片安全审查 / NONE | **合法/已知用例欠定义** — `routes.yaml` 已登记 I2「补模态」处方本身错误 |
| I3 | AI溯源与权利审查 | NONE / **AI 溯源与权利审查** / NONE | **已知判据缺陷（假阴）** — 见 2.4 |
| I4 | AI溯源与权利审查 | **AI 溯源与权利审查** / NONE / NONE | **已知判据缺陷（假阴）** — 见 2.4 |
| I5 | AI溯源与权利审查 | 图片安全审查 ×2 / CLARIFY | **已知用例歧义** — `routes.yaml` 已登记 I5↔F5 近重复（自认「这才是主因」） |
| `kb-manage-4` | kb-manage | kb-manage / kb-manage / **kb-pipeline** | **真·路由边界异议** — 见 2.5 |

### 2.4 I3/I4 是**判据缺陷，不是数据缺陷** —— 且此前登记的说明本身不准

- 事实（逐字核过）：当前装的成员目录名 = **`AI溯源与权利审查`（无空格）**，
  源目录 `~/Desktop/skill/内容治理中文skill/AI溯源与权利审查/SKILL.md` frontmatter `name: AI溯源与权利审查`，
  `skills.yaml` 的 `dir_name` = `AI溯源与权利审查`，`routes.yaml:186` 别名 = `AI溯源与权利审查`。**四处一致、全无空格。**
- 而 09-29 赢家表两行（第 43/44 行）记的是**旧名 `AI 溯源与权利审查`（带空格）**：
  `I3|NONE|AI 溯源与权利审查|NONE`、`I4|AI 溯源与权利审查|NONE|NONE`。
- 归因（我先误判、复算后推翻）：**不是** `routes_reconcile.py` 的 ALIAS 映射写错。
  我读了 `ALIAS`，其值为 `'AI溯源与权利审查'`、不含空格（`canon('AI 溯源与权利审查')` 原样返回，故不折叠）。
  根因是 **09-29 那轮盲测发生在改名之前**；`routes.yaml:233` 记明该改名是 **2026-09-30** 才做的。
  ⇒ 台账比它要核的现状**早一天**。
- **`AI 溯源与权利审查` 这个带空格形态如今只存在于历史件里**：`kb/l7/_backups/*`、`_skill-backups/*`、
  以及 09-29 赢家表。属「台账/快照写的是旧名」，非当前数据缺陷。
- 附带修正一条**既有登记不准**：`kb/l7/reports/CHK-20261003-2343-3GATES-health.md:35` 写
  「`AI 溯源与权利审查`（带空格）未被子目录名折叠，**`ALIAS` 无该变体**」。
  实测 **ALIAS 里有该成员、只是键为英文 id**；该行的成因描述（「ALIAS 无该变体」）不成立，
  结论（「对这些用例不改变结论」）**成立**。
- **不能由此翻案的**：改名的目的是修「装了但选不到」，但**改名不需要重跑盲测这条不能倒推** ——
  赢家表是改名前快照，因此「改名后是否真能被选到」**本单无法判定**，需一轮新盲测。

### 2.5 `kb-manage-4` 是真·路由边界异议（唯一一条要人裁的）

- 用例原文：`「知识库该更新了」这个说法应该走哪个 skill？帮我确认一下归属。` 期望 `kb-manage`。
- **路由表（两处）都把该短语判给 kb-pipeline**：
  `routes.yaml` → `routes[0].say[5] = "知识库该更新了"`，`to: kb-pipeline`；
  `skills.yaml` → `skills[64]`（= `kb-pipeline`）`trigger_keywords[10] = "知识库该更新了"`。
- **同时** `skills.yaml` → `skills[62]`（= `kb-l0-feishu`）`not_for[0]` 里也写着「…知识库该更新了（走 kb-pipeline）」。
  ⇒ 短语归属在路由表内部**自洽**（归 kb-pipeline）。
- 但 `kb-manage` 自己的触发词含 **`该走哪个 skill`、`谁负责`、`知识库 skill 分工`**，与用例句的**元问题**（问归属）强匹配。
- 实测：**kb-manage 4/5 轮胜、kb-pipeline 1/5 轮胜**（`blind_after_r4` 那轮为 3/5 全给 kb-manage）。
- 这不是「表自相矛盾」，而是**「动作词归 A、问归属的元问题归 B」这条边界没写死**。
  要么给 `kb-manage` 的 `not_for` 补「知识库该更新了（走 kb-pipeline）」，要么承认该用例是边缘用例。
  —— **建议交人裁，本单只报不改。**

---

## 三、覆盖缺口（比 6 条不一致更值得看）

对账器 `routes_reconcile.py` 只**部分**覆盖路由表。以下结构**在读、未被断言**：

1. `routes.yaml.frozen_expectation.dir_name_map` —— 含 **13 个 brand-\* 专项**的目录名映射，**0 条断言**。
   ⇒ 「13 个专项各自的活」实际被谁接走，这个闸门**不看**。
2. `routes.yaml.measured_20260929` —— 含 23 个成员的路由分、`known_conflict` 长文，**纯注释，0 条断言**。
3. `routes.yaml.mutual_not_for` —— 表里登记 7 组，脚本却**硬编码 7 对**（第 266–271 行），
   **不读** `mutual_not_for`。⇒ 表与判据**靠人肉同步**，表里加第 8 组不会被闸门发现。
4. 其余成员的 `not_for`（13 个 brand-\*、`kb-check`、`kb-repair`、`kb-content-review`、
   `kb-ingest-extractor`、`kb-clause-extractor`、`kb-media-extractor`、`brand-product-fact-curator` 等）**未参与任何断言**。
5. `routes.yaml.chains`（supply / review / manage）只核「成员与入口在不在登记表」，**不核成员是否真互斥**。
6. 默认用例表 `_基线用例.json`（09-29 16:22）比 `cases_v2.json`（09-29 19:51）旧，且**只覆盖 65/115**。
7. `routes.yaml.meta` 里 `unknown_ok` / `isolated` 字段为**空值 []**（已登记，未回填口径）。

---

## 四、口径与纪律

- 本单**只报不改**（`kb-check` 档位），**未跑** `l8/workflow_check.py`（无干跑档、会写 `kb/l8/`）、
  **未跑** `projection_reconcile.py`（无干跑档）—— 这两道属体检档可选，跑它们会写盘，本单不代用户开写档。
- 若需补齐另外两道（链路收口 / 投影一致性）与信封闸门，请单独报批开写档。
- **「层已跑完」类结论必须带 run_id + 时间戳**；本单为**静态契约核验**，不含层执行结论。
- 结论与证据诚实：本单含一条**我先误判后自行推翻**的归因（AI 空格问题疑似工具 bug → 实为台账旧名），
  已在 §2.4 明写，未修饰。
