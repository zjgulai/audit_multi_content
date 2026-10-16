# 补充优化包 —— L0–L7 八件 skill（root-skill-creator 格式合规）

> 产出：2026-10-04 ｜ 作者：本会话（**补充优化**，非主评测线）
> **状态更新（21:50）：已按用户「你改」授权，应用到主线 `_eval-L1L7-gap-20261004/fix/` 与 `mounts/`（限 L1–L7 七件）。**
> 应用留痕：`../_eval-L1L7-gap-20261004/_补充优化已应用-请先读-20261004.md`
> 可整包回滚：`../_eval-L1L7-gap-20261004/_archive-供补充优化-应用前-20261004/`

---

## ★ 应用记录（2026-10-04 21:50）

底本 = **主线 21:31 的现役 fix**（不是本包 17:20 的旧稿 —— 直接覆盖会回退掉它新增的
`导出手机号身份证 / 只翻译已抽正文 / 只审字幕` 三类负例）。本包只做**格式层增量**：

| # | 改动 | 结果 |
|---|---|---|
| ① | description 触发句提到第一句 | **7/7** |
| ② | 补 `触发词：` 行（把「」列表一分为二，**不删词**） | **6/7**（`kb-ingest-extractor` 余量不足，**如实未补**） |
| ③ | 新建 `references/gotchas.md`（错误+修正 / 不处理 X 句） | **7/7**，共 39 条错误·修正对 |
| ④ | 正文补 gotchas 指针 | **7/7** |
| ⑤ | 补「停用条件」节 | `kb-p0-check` / `kb-recall` / `kb-check` 三件 |
| ⑥ | 版本升 minor + 重建挂载位与 `freeze-manifest` | **7/7 `diff=[]`、校验失败 0、mount==fix** |
| ⑦ | 清掉继承文件的 4096 字节信封（**内容 sha 未变**） | fix 与 mounts 均 0 信封 |

**逐字保留**：主线的「★以下优先于上面的触发词，一律不加载」块与「判归：」块；
**触发词丢失 = 0**（逐件词条数比对）。
**未碰**：L0 线（`_eval-L0L7-gap-20261003/`，sha 与 mtime 均未变）、主线的 `zz-mount-probe` 等自建探针、用例/口径/阈值/打分器、`runs/`。

新版本：ingest **1.5.0** / media **1.4.0** / clause **2.4.0** / canonical **1.6.0** /
p0 **1.5.0** / recall **1.5.0** / check **1.4.0**（sha 见 `out/sha-after.txt`）。

> ⚠️ **主线那两份分数（clause 73.0 / media 69.5）现在双重过期**，不得直接出报告 —— 见应用留痕第三节。

---

---

## 0. 这个包是什么、不是什么

| | |
|---|---|
| **是** | 按 `root-skills-creator` 既有规格，对 8 件 skill 做的**格式合规审计**与**可直接落地的优化副本** |
| **不是** | 不是评测报告，不含任何分数。分数归主线的 `root-skills-eval` 轨道 A/B/C |
| **没做** | **没有**写 `_eval-*/fix/`、**没有**写 `mounts/`、**没有**写 `kb/l7/skills/`、**没有**写桌面 |

### 为什么单独开一棵树

主线的评测靶点是**冻结挂载位**（`mounts/*/freeze-manifest.json` 要求 `diff=[]`），
盲测正在（或即将）对着它跑。**任何对这棵树的改写都会让"评的是哪一份"失去证据**。
⇒ 本包的一切改动只落 `optimized/<skill>/`，与主线物理隔离。

---

## 1. 目录

```
_supp-creator-audit-20261004/
├── README.md                                  ← 本文件（含应用条件）
├── creator格式合规审计-8件-20261004.md         ← 逐项审计 + 证据
├── kept-removed-moved-8件-20261004.md          ← 清单⑤交付物
├── 上线前10项审查清单-8件-20261004.md           ← 清单⑥逐项
├── tools/
│   ├── desc_lint.py            description 合规 lint（只读）
│   ├── measure_desc.py         候选 description 的 500 字窗口测量
│   └── build_optimized.py      建优化副本（只写 optimized/，带保真自证）
├── out/
│   ├── desc-candidates.json    8 条改写后的 description
│   ├── gotchas.json            8 套 gotchas 条目
│   ├── apply-plan.json         源路径映射
│   └── descriptions-dump.txt   优化前 frontmatter 原文（复核用）
└── optimized/<skill>/          8 棵优化副本（= fix 副本 + 本包改动）
```

---

## 2. 改了什么（仅两类）

### ① description 改为「首句即触发条件」

**改动前**（8/8 同病）：首句是**功能陈述**，触发条件排在第二句，且无「触发词：」块。

```
Momcozy 内容治理知识库 **L4（定稿与发布层）**的**只读查询**入口：查**条款号**、…。   ← 功能陈述
当用户问「这条规则的条款号是多少/…」时使用。                                        ← 触发条件在第二句
```

**改动后**（以 kb-canonical-lookup 为例）：

```
当用户问「这条规则的条款号是多少 / 这个条款号对应哪条规则 / …」时使用。   ← 第一句即触发条件
查 L4（定稿与发布层）的条款号、条款号反查规则、canonical 定稿状态（已发号 / stable）。**查询档只读**：…
**欠定先追问、不加载**：…   **写档与破坏性一律不加载**：…
判归：要依据→kb-content-review；…
触发词：条款号是多少、条款号对应哪条规则、article_no、规则定稿了吗、进 canonical 了吗、发号了吗。
```

**八件折叠后长度 419–493，全部 ≤ 500；窗内不可见规则单元 = 0（改前 7/8 有不可见单元）。**

### ② 新增 `references/gotchas.md`（「错误 + 修正」强模式）

7 件原本**没有任何 gotchas**；`kb-l0-feishu` 本来就有（79 行人工台账）⇒ 对它**逐字保留、只追加**。

每条按 `**错误**：… / **修正**：…` 成对写，并含 creator 清单②要求的
**「本 skill 不处理 X，即使措辞看起来相似」**句式（8/8 已入档，共 44 条错误/修正对）。

**为什么放 references 而不是正文**：三件正文余量极小 ——
`kb-l0-feishu` 7979/8000（余 21）、`kb-media-extractor` 3945/4000（余 55）、
`kb-canonical-lookup` 1951/2000（余 49）。往正文塞 gotchas 会**直接触发家族校验器 ERROR**
（正文超限 ⇒ `apply_error_cap` ⇒ 轨道 C 封顶 ≤79、`market_ready=false`）。
⇒ 这正是 creator 清单③「长资料移 references/」的用法。

---

## 3. 自证（都可复跑）

| 项 | 结果 |
|---|---|
| 家族 `validate-skill.py` × 8 | **8/8 `✅ Validation passed!`**，无 ERROR；94–96 分 |
| `desc_lint.py` × 8 | 8/8 折叠 ≤500、首句触发、有触发词块、有边界、说法数 ≥15、不可见单元 0 |
| 保真自证（`build_optimized.py` 内建） | 副本与源**逐文件 sha256** 只在 `SKILL.md` + `references/gotchas.md` 两处不同（实测差异条目 = 2/件），其余全等；不等即 `SystemExit` 拒跑 |
| 落盘无信封自证 | **本包自己生成的 16 个文件**（8×`SKILL.md` + 8×`references/gotchas.md`；L0 的那份为在人工台账后追加）磁盘大小 == 内容长度。**继承自源的 25 个文件仍带源侧那个头** —— 那是**故意的**：保真要求副本与源逐文件 sha256 全等（实测 25/25 相等），我不许顺手"修"它们（见 §6） |
| 冻结靶点未动 | `fix/`、`mounts/`、`kb/l7/skills/` 全程只读（本包无任何写入路径指向它们） |

复跑命令：

```bash
cd <内容治理>/_supp-creator-audit-20261004
python3 tools/measure_desc.py out/desc-candidates.json
python3 tools/build_optimized.py                 # 重建 optimized/（带保真 + 信封双重自证）
python3 tools/desc_lint.py optimized/kb-*
python3 ~/.dsh/skills/root-skills-eval/scripts/validate-skill.py optimized/<skill>
```

---

## 6. ⚠ 本次踩到的 4096 字节信封：**是什么、影响面到哪为止**（已实测，别误传）

### 6.1 现象

`build_optimized.py` 首版生成的 16 个文件，宿主 `read` 工具全部报 **`binary file`**，
而 `file` 命令却显示 `Unicode text, UTF-8 text`。

### 6.2 实测机理

**由 `python3` 进程写出的文件，在「部分读法」下比内容多 4096 字节前置头**（raw 头形如 `887d1cd8…`，
前 4096 字节里有 4063 个 NUL）。该段是**变换过的**，`skip 4096` 取不回原文
（实测 `python 视角内容 != raw[4096:]`）⇒ **不能靠偏移还原，只能重发**。

但**不同读者看到的不是同一份字节** —— 这点最关键：

| 读者 | 看到的是 |
|---|---|
| `python3` `open().read()` | **干净**（内容长度） |
| `node` `fs.readFileSync` | **干净**（实测 `mounts/checkfix/kb-check/SKILL.md` → 6733 字节、首行 `---`） |
| `stat` / `dd`（raw POSIX） | **带 4096 头**（`stat` 大小 = 内容 + 4096） |
| **宿主 `read` 工具** | **带 4096 头** ⇒ 报 `binary file` |

写盘对照（同机同时刻）：

| 写盘方式 | 结果 |
|---|---|
| `open().write()`（python） | **+4096** ✗ |
| python 输出重定向到文件（`python3 -c ... > f`） | **+4096** ✗ |
| `shutil.copyfile`（python） | **+4096** ✗ |
| `printf ... > f`（纯 shell） | 干净 ✓ |
| `/bin/cp` | 干净 ✓ |
| `node -e "fs.writeFileSync"` | 干净 ✓ |
| `base64 -d > f`（非 python 进程写） | 干净 ✓ |

### 6.3 ★ 影响面 —— **它不破坏评测**（本会话实跑验证，勿当成阻塞项）

我一度怀疑它会**让冻结靶点加载不了**（那会让 L1–L7 盲测全变 FN）。**实测否定**：

主线 L1L7 线的 `fix/` 与 `mounts/` 里 **101 个文件中有 48 个带这个头**
（`mounts/*/kb-*/SKILL.md` 与多份 `references/*.md` 在内）；而 L0 线的
`_eval-L0L7-gap-20261003/_mount-l0fix`、`_mount-recallfix` 是**干净的**。

用**主线自己的 harness**（`run_round.py`，spawn 的是 `node …/dsh/lib/bin.js`）
对带头的 `mounts/checkfix/kb-check/SKILL.md` 实跑一条调用题：

```
[a1] 1/1 n=51 214.0s exit=0 loaded=['kb-check'] reply=2105B
skill_loaded = True    skills_loaded = ['kb-check']
```

⇒ **skill 正常加载、正常执行**（回复还用了 skill 自己的 `CHK-<时间戳>` 命名约定）。
顺带验到：`eval-checkfix` profile + 挂载位这条链路**端到端可用**。

**根因**：skill 加载器是 node，node 看到的是干净内容。
**结论**：这是**读者视角差异**，**不是**文件损坏，**不构成评测阻塞**。

### 6.4 那还剩下什么真影响 —— `read` 工具读不了（工作流隐患）

真正会疼的是：**任何用宿主 `read` 工具去审这些 SKILL.md 的 agent，都会拿到 `binary file`**
（本会话第一次审 `mounts/canonfix/…/SKILL.md` 就撞上了，当时还误判成"并发写入"）。
表现为「文件明明存在、也明明有内容，但读不出来」——排查成本高，且容易被误当成权限或编码问题。

### 6.5 建议（不紧急，但值得做）

1. 本包已把 `write_clean()` 固化进 `build_optimized.py`：内容经 stdin 交给 **`base64 -d`**
   （非 python 进程）落盘，并**回读校验内容 + 磁盘大小**，不符即 fail-loud。重建后 **15/15 干净**。
2. 主线的 `prep_skill.py` / `apply_description.py` 若用 python `open().write()` 落 `.md`，
   **同样会带**这个头。要不要顺手加一个「磁盘大小 == 内容长度」的落盘自检，**属主线决策，本包不代为改动**。
3. ⚠️ 但**不要**因此把冻结靶点重写一遍 —— §6.3 已实测加载正常，
   在评测进行中重写靶点才是真正的风险（会让 `freeze-manifest` 与已跑证据对不上）。

---

## 4. 应用条件（**必读**，不满足就别应用）

1. **只能整批应用，不能中途替换。** `final-delivery-spec.md`「版本一致性」：
   最终报告的 `eval_info.version` 必须等于交付 fix 目录的 `SKILL.md version`；
   **生成报告后禁止再改 fix 而不重生成报告**。
2. **必须重跑盲测。** description 是路由的输入，改了它 = 改了被测对象 ⇒
   A 卷 3 轮 + 调用门槛 + B 卷门禁**全部要重跑**，旧分数一律作废。
   本包**没有**跑过任何盲测，因此**本包不含任何分数，也不构成任何"通过"的依据**。
3. **须补 positive / negative loading 用例。** creator 清单①附加项：
   「禁止随意拓宽 description：任何拓宽都必须同时补 positive loading 与 negative loading 用例」。
   本包**只改 description、未动任何用例**（改用例属评测口径，本包不碰）⇒
   应用前应把这 8 条 description 的意图词与负例各补进用例集。
4. **当前窗口**：截至本包落盘，`_eval-L1L7-gap-20261004/runs/` **仍为空**
   （L1–L7 盲测尚未开始）⇒ 若要在本轮的评测里生效，须在开跑前应用并**重建 freeze-manifest**。
   若主线已开跑，则本包只能作为**下一轮**的输入。

---

## 5. 一句话

主线负责「跑评测、出报告」；本包负责「让 8 件 skill 的 description 与 gotchas
**符合 root-skill-creator 的写法规格**」。两件事产物不同、互不覆盖，
但**必须在同一版本上会合**（见 §4.1/4.2）。
