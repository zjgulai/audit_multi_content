# 体检表 · registry ↔ routes 对账（对峙用）

- 库根（权威库真身）：`/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理`；权威库 = `kb/`（含 `kb/KB-ROOT.json`）
- RUN：`CHK-20261004-0300-REGISTRY-ROUTES` ｜ 实测窗口：2026-10-04 02:52–03:00 CST
- 口径：**只读**。未跑 `l8/workflow_check.py` / `l8/projection_reconcile.py`（**无干跑档、会写盘**）；未写 `kb/l0…l7` 任何一个数据字节。
- 并发提示（先说，因为它影响"这数字是谁的"）：`kb/l7/runs/index.jsonl` 的 mtime = **2026-10-04 02:55:35** ⇒ 本机**另有会话在跑**。本单不认领、不写库；下文数字均为 02:52–03:00 的只读快照。
- 与库内既有记录的关系：本主题已有两份前序台账 —— `_chk-run-20261004-0130-REGISTRY-ROUTES/体检表-registry-routes-对账.md`、`_chk-run-CHK-20261004-0213-REGISTRY-ROUTES/体检表-registry-routes-独立复核.md`。**本单未引用它们的结论**，全部重新实测；其中 02:13 那份触发了 02:25–02:26 的 `routes_reconcile.py` 修复，本单已按**修复后**的状态复核（见 A4）。

---

## 〇 前提审查（先说清口径，否则数字会被误读）

1. **「两块」实际是三张表**，不是两块：`skills.yaml`（登记表 = registry）／`routes.yaml`（路由表）／`layers.yaml`（层契约）。`routes.yaml:3-6` 自己就把三者写成互补关系。只核两张表会整块漏掉 **A1**（供给链成员表漏层主）——那一条恰恰只能靠 `layers.yaml` 才照得出来。
2. **`registry` 在本库不是目录名**，而是 `kb/l7/registry/` 里的 **`skills.yaml` 这份文件**。依据是 `routes.yaml:4` 原文：「`kb/l7/registry/skills.yaml`  答「有哪些成员」」。同目录另有 20 份 yaml，本次只核与路由相关的这三份。
3. **「对不上」有两种，混在一起就会拿错证据**：① 表与表之间的不一致（可对峙）；② 闸门的口径不一致（会让你把假红当成真坏）。本单分列在 §二 与 §三，**不要合并引用**。

---

## 一 闸门实测（退出码为实测值，非估算）

| # | 闸门 | 命令 | 退出码 | 判定 |
|---|---|---|---|---|
| 1 | 登记表自检 | `sh kb/kbpy l7/scripts/skills_check.py` | **0** | 过 · 五类 `1=0 2=0 3=0 4=0 5=0` · 解析 71 行（本项目 52 / 宿主通用 19）· 装载位扫到 **59** 个目录 · 结论「全过」 |
| 2 | 路由表对账（**默认 strict**） | `sh kb/kbpy l7/scripts/routes_reconcile.py _eval-kb-manage/blind_after_r4.winners.txt` | **1** | ①=65 ②=65 ④=0 —— **口径错，不是缺陷**，见 §三 B1 |
| 3 | 路由表对账（`--alias`，可比口径） | 同上 ＋ `--alias` | **1** | 逐条全轮命中 **60/65** · ①=5 ②=5 · **④ 路由表自检 = 0** |
| 4 | 按 `kb-check` §1③ 的**原文命令**跑 | `routes_reconcile.py kb/l7/reports/<RUN>-routes-winners.json` | **2** | 环境错：赢家表不存在（`kb/l7/reports/` 下 `*routes-winners*` **0 个**） |
| 5 | 全库体检（DSH `kb_check` 工具，只读） | `kb_check` | — | 健康分 **79.2**（熔断线 60）· 结论**不通过** —— 拉分项是本单主题**之外**的条目内容维度（孤岛率 0.94 / `E026` 大量 / `W020` 大量） |

> 闸门 3 的 5 条不一致**全部**是 `brand-ai-provenance-rights-review`（I1–I5），与 `routes.yaml:238-255` 自己登记的「冻结用例集自身歧义」一致 —— 是**用例集**问题，不是 registry↔routes 问题。

---

## 二 对不上的地方（逐条给原始证据 + 行号）

### A1 · 4 个「已装 · 生产」成员在 `routes.yaml` 里 **0 次**出现；其中 3 个是 `layers.yaml` 认定的**层主**

登记表说它们是生产成员且已装：

| 成员 | 登记处 | `status` | `source` | 实装 |
|---|---|---|---|---|
| `kb-ingest-extractor` | `skills.yaml:834` | 生产 `:836` | 非 null `:848` | ✅ |
| `kb-media-extractor` | `skills.yaml:850` | 生产 `:852` | 非 null `:864` | ✅ |
| `kb-clause-extractor` | `skills.yaml:866` | 生产 `:868` | 非 null `:880` | ✅ |
| `brand-product-fact-curator` | `skills.yaml:882` | 生产 `:884` | 非 null `:896` | ✅ |

而 `routes.yaml` **全文一次都没提到**它们（复现命令见 §六）：

```
kb-ingest-extractor        命中 0 行
kb-media-extractor         命中 0 行
kb-clause-extractor        命中 0 行
brand-product-fact-curator 命中 0 行
```

更硬的一条：前三个是 `layers.yaml` 逐层认的**执行者**，却不在 `routes.yaml:35` 的供给链成员表里。

- `routes.yaml:35` 原文：
  `members: [kb-pipeline, kb-l0-feishu, kb-canonical-lookup, kb-p0-check, kb-recall, kb-check, kb-repair]`（7 个）
- `layers.yaml:154` `skill: [kb-ingest-extractor, kb-media-extractor]   # 按此序调：先抽取（ingest）→ 再 OCR / 附件（media）`
- `layers.yaml:201` `skill: [kb-ingest-extractor]`（L2）
- `layers.yaml:238` `skill: [kb-clause-extractor]`（L3）

⇒ 供给链（scope「知识库**数据**：L0 → L7」，`routes.yaml:33`）的成员表**不含真正跑 L1/L2/L3 的那三个成员**，却含只管闸门与修复的 `kb-check` / `kb-repair`。这属于**表间不一致**，不是「故意不写」——因为 `routes.yaml:11` 自己立的规矩是「`to` / `members` 里的每个 id 必须是登记过的成员」，而这三个**登记过、已装、生产**。

### A2 · `skills.yaml` **自己的块注释与自己的数据相反**（两处，最适合拿去对峙）

**第二批** —— 注释 `skills.yaml:588-591`：

```
589:  # 第二批 · 本项目要用、尚未装到 DSH 装载位（scope: 本项目 · status: 候选）共 14 个
590:  # 本阶段只登记，不安装
```

紧随其后的 14 行数据：**`kb-retriever` 是 `废弃`（`:594`），其余 13 个 `brand-*` 全是 `生产`**（`brand-content-review-agent :610`、`brand-review-intake-router :627`、`brand-policy-source-curator :644` …）。
⇒ 「候选 / 尚未装 / 只登记不安装」**14 条里 0 条成立**；这 13 个 `brand-*` 全在 `~/.dsh/skills/` 里。

**第三批** —— 注释 `skills.yaml:830-833`：

```
831:  # 第三批 · 本项目计划要新建（scope: 本项目 · status: 规划）共 4 个
832:  # 尚无目录，信息从简：只登记 id + purpose + layer；selftest / source / depends_on_engine 一律 null
```

| 注释说 | 数据实际 | 行号 |
|---|---|---|
| `status: 规划` | **生产** | `:836` `:852` `:868` `:884` |
| `source` = null | **非 null** | `:848` `:864` `:880` `:896` |
| `depends_on_engine` = null | **非 null（4/5/3/3 项）** | `:843` `:859` `:875` `:891` |

⇒ 三条声明**逐条被同一文件的数据推翻**。这**就是** A1 里那批成员的来源（第三批 = A1 的 4 个成员）。

### A3 · `kb-manage` 的家族成员表把 4 个成员写成「规划 / 不安装」，与登记表对不上

`~/.dsh/skills/kb-manage/SKILL.md`（= 源 `kb/l7/skills/kb-manage/SKILL.md`）：

```
55: | 11 | `kb-ingest-extractor` | L1/L2 | 规划 | 素材 → 知识单元（本轮只登记，不安装） |
56: | 12 | `kb-media-extractor` | L1 | 规划 | 图片 / 音视频 → 可入库信息（本轮只登记） |
57: | 13 | `kb-clause-extractor` | L3 | 规划 | 外部标准 → 条款级单元（本轮只登记） |
58: | 14 | `brand-product-fact-curator` | L3 | 规划 | SKU 级产品事实基线（本轮只登记） |
60: **成员 1–10 是"入口/组件"，11–14 是"规划中的供给侧成员"（`status: 规划`，`trigger_keywords` 留空 = 不参与路由）。**
```

实测反驳：4 条 `status` 全是 **生产**（A2 表格），`trigger_keywords` **全部非空**（`:838` 10 条 / `:854` 11 条 / `:870` 9 条 / `:886` 10 条），且 4 个目录**都在** `~/.dsh/skills/`。
另：`skills.yaml` 的 `status` 实测分布是 **生产 59 / 参考 11 / 废弃 1**，**「规划」0 条**（`skills_check.py` 第 1b 类也报「候选 0 + 规划 0」）。
⇒ routes 侧（`kb-manage` 是路由表的管理面，`routes.yaml:54-58`）文档与 registry **三处不一致**：状态、触发词、装没装。`kb-check` 与 `kb-manage` 的正文我**没有**去逐字核（本次只核了与 registry/routes 直接相关的字段），这一条的范围就是上表这几行。

### A4 · `routes.yaml` 声称「对账器用本表归一」，**对账器实际不用**

`routes.yaml:175-177` 原文：

```
175:  #: 期望成员 id → 2026-09-29 并发中文翻译轮次后的**真实装载目录名**（= frontmatter name）。
176:  #: 对账器 kb/l7/scripts/routes_reconcile.py 的 --alias 口径用这张表把两边归一。
177:  dir_name_map:
```

实测：对账器**全文 0 命中** `dir_name_map` / `frozen_expectation` / `mutual_not_for`（复现见 §六），它用的是自己硬编码的 `ALIAS` 表（`routes_reconcile.py:42-65`）。
⇒ `:176` 这句是**陈述与代码不符**。而且这张映射被写了 **4 份**：`skills.yaml` 各条的 `dir_name`（13 条）、`routes.yaml:178-190`、`routes_reconcile.py:42-65`、`_eval-kb-manage/kb_routes_score.py:33-50`。
**这不是理论风险，昨天刚为此返工过**：`routes_reconcile.py:58-63` 的修复注释原文写着「`_eval-kb-manage/kb_routes_score.py` 的表里**本来就有**这一行，这里没有 —— 两张表**行数不同**（14 vs 13），是「两个打分器口径不一致」的真正源头」，修复方向是把行数补齐成一致。
另：`routes_reconcile.py:108-110` 自称「本表是**真源**」，而 `routes.yaml:176` 说真源是 routes.yaml 的 `dir_name_map` —— **两个文件互相指认对方为真源**。

### A5 · `routes.yaml` 说互斥点名是「硬约束，对账器会核」，**对账器漏核了表里的第 1 条**

`routes.yaml:138` 原文：`# ─────── 互斥点名（硬约束，对账器会核）`
`routes.yaml:148` 原文：`  - pair: ["文案合规审查", "视频安全审查"]`

实测：对账器的互斥点名清单是**硬编码**的 `routes_reconcile.py:327-332`，共 7 对，**每一对都只跟 `kb-pipeline` 家族有关**，**不含** `routes.yaml:148` 那一对：

```python
327:    checks = [
328:        ("kb-pipeline", "kb-l0-feishu"), ("kb-l0-feishu", "kb-pipeline"),
329:        ("kb-l0-feishu", "kb-review"), ("kb-pipeline", "kb-review"),
330:        ("kb-pipeline", "kb-canonical-lookup"), ("kb-pipeline", "kb-p0-check"),
331:        ("kb-pipeline", "kb-recall"),
332:    ]
```

⇒ 表里 7 条 pair，脚本核 7 条，但**集合不同**（脚本多一条反向、少表里的第 1 条）。这就是 ④ 恒等于 0 的原因之一 —— **④ = 0 ≠ 表里每条约束都成立**。
**实况是成立的**（所以这是"判据没接线"，不是"数据坏了"）：`~/.dsh/skills/文案合规审查/SKILL.md:4` 含「视频画面（走 视频安全审查）」，`~/.dsh/skills/视频安全审查/SKILL.md:4` 含「（走 文案合规审查）」。

### A6 · `routes.yaml:47-52` 的层前置陈述**已过期**（引用的是自己已改判的记录）

```
51: `skill_invocation_audit.py --run <BASE>-L{4,5,6}` 必须**红 0**。
52: 现状：**文字约束**，未落成代码级阻断（登记见 report-output-contract.yaml 的 GAP-RO-5）。
```

两处都被实测推翻：

- `:51` 只列 L4/L5/L6，而引擎实际要求**四层**：`kb/l7/review-engine/core/with_kb_evidence.py:307`
  `LAYER_PREFLIGHT_LAYERS = ("L4", "L5", "L6", "L7")`（`:305-306` 注释亦写明「L7 必须像 L4–L6 一样带 `--invoked …` 记账，否则审计红 → 本命令拒答」）。
- `:52` 说「未落成代码级阻断」，而它**自己引的** `GAP-RO-5` 的 `status` 字段（`kb/l7/registry/report-output-contract.yaml:277`）原文是：
  「主体已落地（2026-10-03：CLI 默认要求 ＋ API 等效留痕已部署）」。
  代码侧佐证：`report-output-contract.yaml:652-677` 的 `three_defenses_20261003`（三道防线：入口唯一化 / `--decision-owner` / `--loaded-skill` 申报）。
⇒ 这正是库内已因「同一事实写三处」返工过一次的形态（同一件事在 routes.yaml、report-output-contract.yaml、代码里各一份，**routes.yaml 那份先过期**）。

### A7 · 存在**第二张路由表**（`kb-manage §2.1`），已与 `routes.yaml` 漂移

`kb-manage/SKILL.md:99` 自己声明「真源 = `kb/l7/registry/routes.yaml`」，但 `:104-116` 又列了一张 11 行的路由表。两表**目标集合相同**（11 个），但：

1. **写法不统一**：`kb-manage:116` 的目标写 `内容审查总控`（**装载名**），`routes.yaml:86` 写 `brand-content-review-agent`（**登记 id**）。同一个目标两种写法，按字面比对就是 1 处不一致。
2. **触发语已漂移 8 行**（`routes.yaml` 为准，`kb-manage` 是过期副本）：

| kb-manage 行 | 目标 | kb-manage 有而 routes.yaml 没有 | routes.yaml 有而 kb-manage 没有 |
|---|---|---|---|
| `:108` | `kb-review` | — | 帮我审、评审一下、评审这条、这个评审一下、内容审核、合规审查、能过审吗 |
| `:109` | `kb-content-review` | — | 条款号、审查依据 |
| `:110` | `kb-canonical-lookup` | — | article_no |
| `:111` | `kb-p0-check` | 优先级是 P0 吗 | P0 模式清单、是不是最高优先级 |
| `:112` | `kb-recall` | 知识库里有哪些相关单元 | 按语义召回、向量召回、BM25 召回、分层索引导航 |
| `:113` | `kb-check` | — | 登记表自检 |
| `:114` | `kb-repair` | — | 不过就修、修复失败项、副本不一致帮我同步 |
| `:115` | `kb-manage` | 注册表 | skill 注册表、路由表、成员列表、新增一个知识库 skill 登记到哪 |

（`:106` 目标 `kb-pipeline`、`:107` 目标 `kb-l0-feishu` 两行**一致**。）

⇒ 按库内纪律「同一事实只写一处」，`kb-manage §2.1` 应改成指针或与 `routes.yaml` 逐行同源；现状是**两处都在、且已不同**。

### A8 · 同一个事实两个数字：`45 次` vs `88/195`

- `routes.yaml:193`：`kb-content-review 此前在 195 次判定里抢走 45 次，是 7 个 brand-* 未过门槛的**唯一根因**；`
- `routes.yaml:205`：`before_65cases: "13 个 brand-* 中 **0 个**过门槛（6/65 逐条全轮命中；kb-content-review 抢走 88/195 次）"`

`skills.yaml:135`（`kb-content-review` 的 `note`）**两个数都写了**，并给了区分：45 = 方案原始口径，88/195 = 本 agent 复测 harness。另 `skills.yaml:1137`（`kb-review` 的 `note`）也用了 45。
⇒ **有解释，但解释只在 `skills.yaml` 里**；只引 `routes.yaml` 时，`:193` 与 `:205` 互相打脸。**引用时必须带上 `skills.yaml:135` 的区分**，否则这个数会被人当成矛盾。

### A9 · `skills.yaml` 的扫描备注仍是旧数

`skills.yaml:29-31` 写「扫描时刻 2026-09-29：33 个目录 … 装入 14 个候选 skill 后为 47 个，与 `skills_check.py` 的现场扫描一致（33 + 14 = 47）」；本次实测装载位 **59 个目录**（`skills_check.py` 实测输出）。
⇒ 该备注自称「行数对不上时以 `skills_check.py` 的实时扫描为准」，所以**不算缺陷**，但**引用 47 这个数就是错的**。属"过期提示"，登记在此以免被引用。

---

## 三 闸门口径不一致（这一节专治"拿错证据"）

### B1 · `kb-check §1③` 的原文命令**不带 `--alias`**，会给你 65 条假红

- `kb-check` 正文 §1③ 的原文命令是：
  `kb/kbpy l7/scripts/routes_reconcile.py kb/l7/reports/<RUN>-routes-winners.json` —— **没有 `--alias`**。
- 同一脚本自己的备注（`routes_reconcile.py:399`）却写：「F1 交叉核对默认跳过：**本表口径含 alias 折回**；要核对请用 `--alias` 一致的 results 目录」。
- 实测差异（**同一份赢家表**，`_eval-kb-manage/blind_after_r4.winners.txt`）：

| 口径 | 退出码 | ①不一致 | ④路由表自检 | 逐条全轮命中 |
|---|---|---|---|---|
| 默认 `strict` | 1 | **65** | 0 | 0/65 |
| `--alias` | 1 | **5** | 0 | 60/65 |

⇒ 65 条里有 **60 条是「期望写登记 id、实际记装载名」的命名空间差**，不是路由被抢走。**任何用默认口径贴出来的"65 条全不一致"都是假红**，别拿去对峙。

### B2 · 今天**没有本轮赢家表**，路由结论的时效是 2026-09-29

- `kb/l7/reports/` 下 `*routes-winners*` 命中 **0 个**（`kb-check`/`kb-manage` 都指向这个路径）。
- 唯一可用的赢家表是 `_eval-kb-manage/blind_after_r4.winners.txt`，**mtime = 2026-09-29 19:32**（115 行，其中冻结 65 条）。
- 缺输入时脚本**不会静默降级**：实测 `exit 2`，并打印「缺输入时本闸门**不得报绿**，也不得静默按「全不一致」跑」。
⇒ 「路由对得上/对不上」这句话，**当前只能限定为「相对 2026-09-29 那轮实测」**。要今天的结论，必须先按 `kb-manage` 的触发电测重跑赢家表。

---

## 四 疑似待裁（**不算**已确认缺陷，别当结论用）

### C1 · 裸词「条款号」被两个成员同时认领

`routes.yaml:92-93` 把 **`条款号`** 放进 `kb-content-review` 的 `say`；而 `routes.yaml:67-68` `:95` `:107-108` `:114-115` 共四处 `not_for` 都把「**查**条款号」指向 `kb-canonical-lookup`。
⇒ 「条款号」单说时该谁接，表里没有唯一答案。可能是**有意的**（「三态结论的依据」语境 vs 独立查询语境），但**需要人来裁一句话写进表**，否则这四行 `not_for` 与那一行 `say` 表面冲突。

### C2 · `AGENTS.md` 的「26 个 skill（14 + 12）」复现不出来

实测（装载位 `~/.dsh/skills/` 共 **59** 个目录）：
- `kb-*` / `brand-*` 目录 **14 个** ✅ 与「14」吻合；
- 中文名且属知识库家族的目录 **13 个**：`内容审查总控`、`送审登记`、`证据源维护`、`文案合规审查`、`产品宣称核验`、`图片安全审查`、`视频安全审查`、`美国本地化审查`、`AI溯源与权利审查`、`审查裁决`、`审查报告与记忆`、`审查流程评测`、`飞书审查流转`；
- 另有中文名但非审查家族的 `蒸馏`、`web-执行测试用例` 2 个。

⇒ 14 + 13 = **27**，与「26」差 1；「12 个中文专项成员」这个数**我复现不出来**（无论含不含 `蒸馏`/`web-执行测试用例`）。这条是**跨文档**口径问题（工作区指令 vs registry），不是 registry↔routes —— **要人给「12」的口径来源才能核**。

### C3 · `mutual_not_for` 第 1 条用装载名，与 `routes.yaml:11` 的措辞不齐

`routes.yaml:11` 立的口径是「`to` / `members` 里的每个 id 必须是登记过的成员」；`routes.yaml:148` 那一对写的是**装载名** `文案合规审查` / `视频安全审查`（登记 id 是 `brand-text-compliance-review` / `brand-video-safety-review`）。其余 6 对（`:154-165`）都用登记 id。
⇒ 严格说 `mutual_not_for` 不在 `to`/`members` 范围内，所以**不算违规**，属口径覆盖不全；但它是 `routes.yaml` 里**唯一一个混用命名空间**的地方，与前序 4 次因"两套名字"返工同源。

---

## 五 本次核不到的（诚实边界）

1. **路由结论的时效是 2026-09-29**（见 B2）——今天没有新赢家表，本单**不能**声称"今天对过账"。
2. **未跑** `l8/workflow_check.py`、`l8/projection_reconcile.py`：**无干跑档、会写盘**，而本机 02:55 仍有会话在写 `kb/l7/runs/index.jsonl`。要跑请单独报批。
3. **`kb_check` 健康分 79.2「不通过」**：拉分项是孤岛率 0.94、`E026`（内容质量分 <60，大量）、`W020`（疑似重复，大量）——**全部属条目内容维度，与本单主题无关**，不要混进 registry↔routes 的结论。
4. **未核** `kb/l0…l6` 的数据与台账（本单只读，未触碰）。
5. 本单**未逐字核** `kb-check` / `kb-manage` / 13 个 `brand-*` 的 SKILL.md 正文，只在 A3/A5 两处按需取了指定行（已在文中给出路径与行号）。
6. 数字均为 **02:52–03:00 的快照**；另一会话在跑，**复现时以你的实测值为准**。

---

## 六 复现命令清单（逐条可直接粘贴）

```bash
cd "/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理"

# 闸门 1：登记表自检（预期 exit 0）
sh kb/kbpy l7/scripts/skills_check.py; echo "exit=$?"

# 闸门 2/3：路由表对账 —— 两种口径各跑一次，差别就是假红的量
sh kb/kbpy l7/scripts/routes_reconcile.py _eval-kb-manage/blind_after_r4.winners.txt;         echo "strict exit=$?"
sh kb/kbpy l7/scripts/routes_reconcile.py _eval-kb-manage/blind_after_r4.winners.txt --alias; echo "alias  exit=$?"

# 闸门 4：kb-check §1③ 的原文命令（预期 exit 2，赢家表不存在）
sh kb/kbpy l7/scripts/routes_reconcile.py kb/l7/reports/CHK-routes-winners.json; echo "exit=$?"

# A1：4 个已装生产成员在 routes.yaml 里 0 次出现
for s in kb-ingest-extractor kb-media-extractor kb-clause-extractor brand-product-fact-curator; do
  printf "%-28s %s\n" "$s" "$(grep -c -- "$s" kb/l7/registry/routes.yaml)"
done
grep -n "^    skill:" kb/l7/registry/layers.yaml          # L1/L2/L3 的执行者是谁

# A2：skills.yaml 自己的块注释 vs 自己的数据
sed -n '588,594p;608,612p' kb/l7/registry/skills.yaml     # 第二批「候选/不安装」+ 紧随的「生产」
sed -n '830,836p;843p;848p' kb/l7/registry/skills.yaml    # 第三批「规划 / source=null / depends_on_engine=null」

# A3：kb-manage 家族表（写「规划/不安装」）
sed -n '41,60p' ~/.dsh/skills/kb-manage/SKILL.md

# A4：对账器并不读 routes.yaml 的 dir_name_map（预期 0 命中）
grep -n -E "dir_name_map|frozen_expectation|mutual_not_for" kb/l7/scripts/routes_reconcile.py
sed -n '175,190p' kb/l7/registry/routes.yaml              # 声称「对账器用这张表」
sed -n '42,65p'   kb/l7/scripts/routes_reconcile.py       # 实际用的是这张硬编码表

# A5：互斥点名「硬约束，对账器会核」——脚本清单是硬编码且不含表里第 1 条
sed -n '138p;148p' kb/l7/registry/routes.yaml
sed -n '327,332p' kb/l7/scripts/routes_reconcile.py

# A6：层前置实际是四层；GAP-RO-5 自述已落地
grep -n "LAYER_PREFLIGHT_LAYERS" kb/l7/review-engine/core/with_kb_evidence.py
sed -n '275,277p' kb/l7/registry/report-output-contract.yaml

# A7：第二张路由表已漂移
sed -n '99,116p' ~/.dsh/skills/kb-manage/SKILL.md
sed -n '62,136p' kb/l7/registry/routes.yaml

# A8/A9：两个数字 / 旧扫描数
sed -n '193p;205p' kb/l7/registry/routes.yaml
sed -n '135p'      kb/l7/registry/skills.yaml
sed -n '26,31p'    kb/l7/registry/skills.yaml

# B2：今天有没有本轮赢家表（预期 0）
ls kb/l7/reports/ | grep -c winners
```

---

## 七 一句话结论

- **闸门层面**：登记表自检 **过**（exit 0）；路由表自检 ④ **0 条** —— 但 ④ 的口径**覆盖不全**（A5），所以「④ = 0」**不等于** routes 与 registry 全对得上。
- **表间层面**：确实对不上，**最硬的两条**是 **A1**（3 个层主不在供给链成员表里、4 个已装生产成员 0 次出现）与 **A2**（`skills.yaml` 自己的块注释被自己的数据逐条推翻）—— 这两条都有行号、可一行命令复现，**建议优先拿去对峙**。
- **引用纪律**：`strict` 口径的「65 条全不一致」是**假红**（B1）；路由结论的时效是 **2026-09-29**（B2）。这两条一定要带上，否则结论会被反打。
