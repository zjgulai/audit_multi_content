# 体检表 · registry ↔ routes 独立复核（对峙用）

- 库根（= 权威库真身）：`/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理`
- 权威库 = `kb/`（含 `kb/KB-ROOT.json`）；`~/.dsh/Momcozy知识库/kb` 是指向本库的软链（`readlink` 实测），不是第二份
- 时间：2026-10-04 02:13
- 口径：**只读**。本单未跑 `l8/workflow_check.py` / `l8/projection_reconcile.py`（无干跑档、会写盘），未写权威库任何一个字节
- 本单回答一件事：**registry（`skills.yaml` / `layers.yaml`）与 routes（`routes.yaml`）对不对得上**
- 与 01:30 那份 `_chk-run-20261004-0130-REGISTRY-ROUTES/体检表-registry-routes-对账.md` 的关系：结论方向一致，**其中两处数字已复算纠正（见 §4）**

---

## 一、闸门实测（退出码为实测值）

| # | 闸门 | 命令 | 退出码 | 判定 |
|---|---|---|---|---|
| 1 | 登记表自检 | `kb/kbpy l7/scripts/skills_check.py` | **0** | 过 · 五类 1=0 2=0 3=0 4=0 5=0 |
| 2 | 层契约 | `kb/kbpy l7/scripts/layers_check.py` | **0** | 过 · 六类 0 · 8 层齐 |
| 3 | 路由表对账（**kb-check §1③ 的原文命令**） | `kb/kbpy l7/scripts/routes_reconcile.py kb/l7/reports/<RUN>-routes-winners.json` | **2** | 环境错：赢家表不存在 —— 库内 `kb/l7/reports/` 下**无任何** `*routes-winners*` |
| 4 | 全库体检 | `kb_check`（DSH 工具） | — | 健康分 **79.1**（熔断线 60）· 结论**不通过** |

闸门 4 的拉分项与本单主题**无关**（属条目内容维度）：孤岛率 0.94（阈值 ≤0.2）、`E026` 内容质量分 <60、`W020` 疑似重复 ×大量。
其余维度健康：新鲜度 1.00 / 三件套完整率 1.00 / 一致性 1.00 / 覆盖率 0.92 / 利用率 0.23。

---

## 二、对不上的地方（逐条给原始证据 + 行号）

### R1 · 注册表 40 个生产成员，路由表只覆盖 11 个；4 个**层主**零路由

- `skills.yaml`：`scope=本项目 且 status=生产` = **40** 个（YAML 解析实测，非估算）
- `routes.yaml`：**11** 条 routes，行号 `64 / 70 / 76 / 84 / 91 / 98 / 104 / 110 / 118 / 124 / 131`；**11** 个不同 `to`
- ⇒ **29 个生产成员没有任何 intent 级 route**
- 其中 **4 个是 `layers.yaml` 认的层主**，而 `routes.yaml` 全文 **0 次**提到它们：

| 成员 | 层主身份（layers.yaml） | 登记处 | route | 冻结用例 |
|---|---|---|---|---|
| `kb-ingest-extractor` | L1 `:154` · L2 `:201` | `skills.yaml:834` | 0 | 0 |
| `kb-media-extractor` | L1 `:154` | `skills.yaml:850` | 0 | 0 |
| `kb-clause-extractor` | L3 `:238` | `skills.yaml:866` | 0 | 0 |
| `brand-product-fact-curator` | 自称 L3（非层主） | `skills.yaml:882` | 0 | 0 |

「冻结用例 0 条」的实测依据：`/Users/lute/Desktop/skill/内容治理中文skill/_基线用例.json` 共 65 条，
期望成员**只有 13 个 `brand-*`**，上述 4 个各 **0** 条。

```bash
grep -c "kb-ingest-extractor"      kb/l7/registry/routes.yaml   # 0
grep -c "kb-media-extractor"       kb/l7/registry/routes.yaml   # 0
grep -c "kb-clause-extractor"      kb/l7/registry/routes.yaml   # 0
grep -c "brand-product-fact-curator" kb/l7/registry/routes.yaml # 0
```

### R2 · 那 4 个成员：**注册表自己的块注释与自己的数据相反**（本单新增，最适合拿去对峙）

`skills.yaml:830-833` 原文：

```
830:  # ============================================================
831:  # 第三批 · 本项目计划要新建（scope: 本项目 · status: 规划）共 4 个
832:  # 尚无目录，信息从简：只登记 id + purpose + layer；selftest / source / depends_on_engine 一律 null
833:  # ============================================================
```

紧接着的数据（同一个文件、同一段落）：

| 字段 | 注释说 | 数据实际 | 行号 |
|---|---|---|---|
| `status` | 规划 | **生产** | `:836` `:852` `:868` `:884` |
| `source` | null | **`"l7/skills/kb-…/"`** | `:848` `:864` `:880` `:896` |
| `depends_on_engine` | null | **非空（3–5 个引擎）** | `:843` `:859` `:875` `:891` |
| `trigger_keywords` | 未提（=应与「不参与路由」一致） | **9 / 11 / 9 / 10 条** | `:838` `:854` `:870` `:886` |
| 目录 | 「尚无目录」 | **四个目录真装在 `~/.dsh/skills/`** | SKILL.md 8347 / 9262 / 10378 / 7500 字节 |
| 每条自己的 `output_path_note` | — | **写着「未装机（规划中）」** | `:842` `:858` `:874` |

- `:842` `:858` `:874` 的 `output_path_note: "未装机（规划中）…"` 与同一行的 `status: 生产` **直接打架**。
- `skills_check.py` 实测输出：「本项目要用：40 个（生产 40 + **候选 0 + 规划 0**）」⇒ 注释里的「规划 4 个」在数据里是 **0**。

### R3 · `kb-manage/SKILL.md` 是第三份抄本，且与注册表数据**相反**

- `~/.dsh/skills/kb-manage/SKILL.md:55-58`（表格 11–14 行）四行都写 **规划**：「本轮只登记，不安装」
- 同文件 `:60`：「**成员 1–10 是"入口/组件"，11–14 是"规划中的供给侧成员"（`status: 规划`，`trigger_keywords` 留空 = 不参与路由）**」
- 同文件 `:160`（生命周期表）：「规划 | 在 `skills.yaml` 登记一行 `status: 规划`，`trigger_keywords: []` | `kb-manage` | 无（不安装）」
- 库内工作副本 `kb/l7/skills/kb-manage/SKILL.md:55-58 / :60 / :160` **同文**（同一份事实抄两处）
- 实际：**生产** + 9–11 条触发词 + 已装 ⇒ **正在参与路由**，与 `:60` 的断言相反
- 附带：`kb-manage/SKILL.md §2.1`「家族级意图（14 个成员）」表**没有这 4 个的意图行**
- **这条不是新发现**：`_dump-20260930/另一个任务-梳理/助手回复全文.md:1048` 已记录
  「`skill_conformance` / `routes_reconcile` 不覆盖 status 与路由参与 | 两者报"红 0"，同时 `kb-manage/SKILL.md` 写 4 个成员"规划·不参与路由"（登记表：生产 + 9–11 条触发词）」
  ⇒ **2026-09-30 已知，至今未修**（本库纪律：「同一事实只写一处」，这里写了三处）

### R4 · `routes.yaml` 自述的层前置口径比代码旧一层（本单新增）

- `routes.yaml:50-51`：「逐层一 RUN：`<BASE>-L4 / -L5 / -L6 / -L7`；出报告前
  `skill_invocation_audit.py --run <BASE>-L{4,5,6}` 必须**红 0**」⇒ 只列 **3 层**
- 代码：`kb/l7/review-engine/core/with_kb_evidence.py:307`
  `LAYER_PREFLIGHT_LAYERS = ("L4", "L5", "L6", "L7")` ⇒ **4 层**
- `routes.yaml:52`：「现状：**文字约束**，未落成代码级阻断（登记见 `report-output-contract.yaml` 的 GAP-RO-5）」
- 代码实际已是**代码级默认阻断**：`with_kb_evidence.py:367`（`--require-layer-preflight`）、`:379`（`--decision-owner`）、
  `:425` 不给 BASE 且不给 `--allow-no-layer-preflight` ⇒ 拒答；`:455-482` 不给 `--decision-owner` 且不豁免 ⇒ 拒答
- 契约文件自己已改口径：`report-output-contract.yaml:277`
  「**主体已落地（2026-10-03：CLI 默认要求 ＋ API 等效留痕已部署）**；遗留一问：API 侧是否也改成「不带 BASE 即 409」」
- ⇒ **同一事实三处不一致**：`routes.yaml`（旧）／代码 + `report-output-contract.yaml`（新）。按 `routes.yaml` 去对峙会讲错版本。

### R5 · `mutual_not_for`：表里 **7 组**，码里只有 **6 组**被核（纠正前一份报告的口径）

- `routes.yaml:138` 标题：「互斥点名（**硬约束，对账器会核**）」
- `routes.yaml:140-165` 登记 **7** 组（行 `148 / 154 / 156 / 158 / 160 / 162 / 164`）
- `routes_reconcile.py:266-271` 硬编码 **7 对**，但**是另一套集合**（把 `pipeline↔l0` 拆成两条单向）：
  仅覆盖表里 6 组
- ⇒ 表里第 1 组 `routes.yaml:148` `pair: ["文案合规审查", "视频安全审查"]`（本次盲测暴露的真歧义）
  **从未被任何闸门核过**；把它从表里删掉，闸门输出一模一样
- 全库 `grep -rn "mutual_not_for" --include=*.py` ⇒ **0 命中**（脚本压根不读这个键）
- `routes_reconcile.py:13` 自称「④ 路由表自检：id 都在 `skills.yaml` 里、**互斥点名规则都成立**、两条链的入口 `not_for` 互相点名」⇒ 这句不成立

### R6 · 这条闸门**不在 CI、不在任何自动闸门里**（本单新增）

- `ci/run_gates.py:87-100` 的 12 条闸门 = `l0…l7` + `skills` + `layers` + `conformance` + `freshness`
- `grep -c routes ci/run_gates.py` ⇒ **0**
- ⇒ **注册表 ↔ 路由表的一致性从来没有被自动核过**；只有人手敲才跑，而一敲就是 `exit 2`（缺赢家表，见 §一 第 3 行）
- 全库唯一在调它的是临时脚本 `_gate-sweep-CHK-20261004-0212.sh:23-24`（库外，2026-10-04 02:12 现造），**不在库的闸门清单里**

### R7 · `routes.yaml` 内部：chain 的 `note` 与 `members` 数据不一致（本单新增）

- `routes.yaml:43` `members: [kb-review, kb-content-review, brand-content-review-agent]` ⇒ **3 个**
- `routes.yaml:45` note：「**13 个 brand-\* 是"消费侧子能力 / 链内成员"**」
- ⇒ 13 个 `brand-*` 里只有 1 个（`brand-content-review-agent`）真在 `members` 里；
  读数据结构的检查器看到 **3** 个成员，不是 15 个
- 附带：`送审登记`（`brand-review-intake-router`）在 `routes.yaml` 里**只出现在 `not_for` 文本**里（`:88`），不是任何 chain 的成员

### R8 · `layer` 字段落在所有闸门的缝里（复核，含本单新增的 L7 一条）

`skills.yaml` 的 `layer` 字段**没有任何闸门核**（`skills_check.py` 里 `layer` 只出现在打印/统计处）。实测不一致：

| 成员 | `skills.yaml` | `layers.yaml` 实际层主 |
|---|---|---|
| `kb-content-review` | `layer: L7`（`:127`） | **不是任何层的层主**（L7 的 `skill:` 是 `kb-check`，`layers.yaml:539`） |
| `kb-check` | `layer: "—"`（`:1144`） | 却是 **L7 的 `skill:`**（`layers.yaml:539`，同行注释自认「跨层统一闸门，不是 L7 的层主」） |
| `kb-pipeline` | `layer: "L0–L7"`（`:1112`） | 不是任何层的层主 |
| 14 个 `brand-*` | `layer: "L0–L7"` | 不是任何层的层主 |
| `brand-product-fact-curator` | `layer: "L3"`（`:888`） | L3 层主是 `kb-clause-extractor`（`:238`） |
| `kb-ingest-extractor` | `layer: "L1/L2"`（`:840`） | 拆成 L1(`:154`)、L2(`:201`) 两条 ⇒ 值不相等 |
| `kb-retriever` | `layer: "L0/L1"` `status: 废弃`（`:598`） | 不是任何层的层主 |
| `brand-content-review-agent` | `layer: "L0–L7"`（`:614`） | 不是任何层的层主 |

`layers.yaml:47` 白纸黑字写：「**「到某一层调哪个 skill」的唯一真源就是本表各层的 `skill:` 字段**」——
那么 `skills.yaml` 的 `layer` 字段要么该被核，要么该标明「仅描述、不承重」。

---

## 三、对得上的部分（别误伤）

- `routes.yaml` 的 **11 个 `to` 全部在** `skills.yaml` 登记表里（违规 0）
- 3 条 chain 的 `members` 与 `entry` **全部在册**（违规 0）
- 11 个 `to` 目标**全部被某条 chain 的 `members` 认领**（无游离 route）
- `dir_name_map`（`routes.yaml:177-190`）13 条 ↔ `skills.yaml` 各自 `dir_name` 字段 **13/13 逐字一致**
- `layers.yaml` 8 层的 `skill:` 字段**全部在登记表**
- `skills_check.py` 五类 0（应装未装 0 / 装了没登记 0 / 副本不一致 0 / 依赖缺失 0 / 自测缺失 0）
- `layers_check.py` 六类 0（层完整性 / 必填字段 / 引擎存在性 / cwd 解释器 / DAG / 干跑档声明）
- 09-29 之后**新增的 9 个成员**（`kb-check`/`kb-canonical-lookup`/`kb-l0-feishu`/`kb-manage`/`kb-p0-check`/`kb-pipeline`/`kb-recall`/`kb-repair`/`kb-review`）**全部已有 route**

---

## 四、对 01:30 那份报告的纠正（别把旧数字拿去对峙）

| 处 | 01:30 报告写的 | 本单复算 |
|---|---|---|
| `_chk-run-20261004-0130-REGISTRY-ROUTES/体检表-registry-routes-对账.md:50` | `mutual_not_for` 声明了 **8 组** | 实测 **7** 组（`grep -c '^  - pair:'` = 7） |
| 同报告 `:68` | 路由表「11 条 routes / **10 个不同 `to`**」 | 实测 **11 个不同 `to`**（11 条 route 各自唯一目标） |

其余结论（R1/R2/R4/R5/R6 的对应项、§6「别误伤」清单、健康分 79.1）本单复算**一致**。

---

## 五、本单的边界（诚实声明）

- 本单是**静态契约核验** ＋ 一份 **2026-09-29 运行时快照**（`_eval-kb-manage/blind_v2.winners.txt` 等）的间接引用，
  **不含**「今天实际被谁接走」。要今天的数，得按 `kb-manage` 的触发电测**重新生成赢家表**（`routes_reconcile.py` 唯一接受的输入）。
- §一 第 3 行的 `exit 2` 是**设计正确的行为**（缺输入拒绝报绿），不是缺陷；缺陷是「**输入从来没人产出**」＋「**没人自动跑**」（R6）。
- §二 R1/R3/R6/R7/R8 的「不一致」是**已确认事实**（可逐条复现）；
  R4 里「该以代码还是以 `routes.yaml` 为准」属**判断**，需人裁。
- 未跑 `l8/workflow_check.py`、`l8/projection_reconcile.py`（无干跑档、会写盘），未做信封闸门全量扫描。
