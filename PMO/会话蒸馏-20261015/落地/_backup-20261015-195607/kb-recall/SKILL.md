---
name: kb-recall
description: |
  Momcozy 内容治理知识库 **L6（召回层）** 的**只读检索**入口，并已并入原 `kb-retriever`：
  按 **BM25 + 向量**双索引召回知识单元，也支持面向本地知识库目录的分层索引导航式检索
  （遇 PDF / Excel 必须先读 references 学处理方法再检索，避免整文件加载）。
  当用户说「召回一下 / 检索单元 / 按语义召回 / BM25 召回 / 向量召回 / 召回 top-k /
  知识库里有哪些相关单元 / 帮我查一下知识库 / 查资料 / 检索信息 /
  从知识库目录回答问题 / 知识库检索 / 分层索引导航 / 查一下有没有相关规则 /
  这句话在库里能找到什么」时使用。
  触发词：召回、检索、查资料、知识库检索、检索信息、语义召回、BM25、向量召回、top-k、
  相关知识单元、查一下库里、从知识库目录回答问题、分层索引导航、PDF 读取、Excel 读取、
  渐进式检索、L6 召回、kb-recall（原 kb-retriever 已并入本 skill）。
  本 skill 的**查询档只读**：不改索引、不写库。
  重建 BM25 + 向量索引是写操作，**编排入口是 kb-pipeline**（整链）—— 本 skill **不给自己开写入口**；
  它只在**被 kb-pipeline 以层身份调用**时走正文 §4 的「写档档位」
  （三条件缺一不可：① 层身份调用 ② `--apply` ③ 人开闸）。
  不适用（各自点名）：
    · 查条款号 / 定稿了没有 → 走 **kb-canonical-lookup**；
    · 这个是 P0 吗 / 命中哪些 P0 模式 → 走 **kb-p0-check**；
    · 判断一段内容能不能发（要三态结论）→ 走 **kb-review**；
    · 已经给出结论、要追问依据 / 逐字摘录 → 走 **kb-content-review**；
    · 跑 L0 到 L7 / 同步知识库 / 重建索引 → 走 **kb-pipeline**；
    · 知识库体检 / 闸门 → 走 **kb-check**；问 skill 怎么分工 → 走 **kb-manage**。
version: "1.2.1"
last_updated: "2026-10-15"
license: "Proprietary — Momcozy internal use only"
complexity: "standard"
compatibility:
  claude: { status: "native" }
  kimi: { status: "native" }
  cursor: { status: "native" }
  gpt: { status: "bridge", limitations: ["脚本执行需适配"] }
  minimax: { status: "bridge", limitations: ["长结果需分页"] }
  dsh: { status: "native", notes: "查询档只读；写档档位由 kb-pipeline 以层身份调用；需 kb/kbpy（受管 python 缺 numpy/fastembed）" }
  codex: { status: "native" }
---

# kb-recall —— L6 召回层 · 只读检索（并入原 kb-retriever）+ 被调用时的写档档位

**一句话**：**查询档只读召回**。要么走 L6 双索引（BM25 + 向量），要么走本地目录的分层索引导航。
被 `kb-pipeline` 以层身份调用时，另走 §4 的写档档位（重建 BM25 + 向量索引）。

## 1. 解释器（硬约束，先读）

```bash
cd "<本次库根>"                   # ★ cwd = 本次库根（批次23 起；编排器按库根派生，不再是固定路径）
kb/kbpy l6/retriever.py --help    # 一律走 kbpy
```

受管 external-tools python **缺 numpy / fastembed**，而 L6 两者都要
（`kb/l6/retriever.py:245` `np.load(matrix.npy)`、`:249` `from fastembed import TextEmbedding`）。
配置在 `kb/.kb-python`（内容 `/usr/bin/python3`）。**不合格就报错退出，不静默降级。**

## 2. 两条检索通道 + 已知限制

- **L6 双索引召回（首选）**：检索器 `kb/l6/retriever.py`；索引 `kb/l6/bm25/` + `kb/l6/vectors/`；
  注册表 `kb/l6/registry/l6.json`（含 `retrieval_capability` / 模型 / 维度 / 已知限制）；
  范围 `kb/l6/SCOPE.txt`（**只覆盖可用单元的一个子集，不是全量**）。
  模式 `vector_plus_bm25`，模型 `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`（384 维，fp16 ONNX，本地 CPU）。
- **本地目录分层索引导航**（原 `kb-retriever` 的能力，一并保留）：先读各级 `data_structure.md` 定文件；
  遇 PDF 读 `references/pdf_reading.md`、遇 Excel 读 `references/excel_reading.md` / `excel_analysis.md`；
  `grep` / 局部读 / 分页，**不整文件加载**。

**已知限制（不许夸大能力）与输出契约 → `references/layer-playbook.md`。**
（要点：跨语言只有弱对齐；同义改写受限；规避型表述召回受限；无重排；**无命中阈值**，
一律返回 Top-N；RRF 分不能当阈值；覆盖不是全量。故写结论时用「**候选**」不用「命中」。）

## 3. 红线

- **查询档不写**：不调 `kb/.work/l6_build.py`，不改索引，不写库。写档只在 §4 的档位下发生。
- **不把 Top-N 当「命中」**：没有阈值就没有「命中」，只有「候选」。
- **不拿召回当依据级别**：L6 候选的证据级低于 L3 规则 / L5 P0，引用时要说清是哪一层。
- **不越过 SCOPE**：范围内的召回率不能当成全库召回率。
- 引用必须带 `unit_id` + 锚点 + `source_sha256` 三样，缺一样下游就没法当依据用。

## 4. 写档档位（只被 kb-pipeline 以层身份调用时走）

**三条件缺一不可**：① 由 `kb-pipeline` 以层身份调用 ② 带 `--apply` ③ 人开闸。
**它不是给用户直接触发的入口** —— 本 skill **刻意不加**「重建索引」类触发词，
用户说「把索引重建一下」仍走 `kb-pipeline`。

跑哪几个引擎**不写在本文**：读 `kb/l7/registry/layers.yaml` 的 **L6 层 `engine`**（唯一真源）；
本层两个引擎都归本 skill（`l6_build.py` 建索引 + `l6_bench.py` 性能验收）。
写档红线（kbpy 硬约束 / 双幂等键 / `write_if_changed` 守卫 / `SCOPE.txt` 是人工白名单 /
跑完回 `l6_gate.py`，它是只读档、有 4 项明写没跑）→ `references/layer-playbook.md` §写档。

## 5. 何时停下来问人

- `kb/kbpy` 报「找不到合格解释器」→ 报缺什么，**不要退化成受管 python 硬跑**。
- 召回结果为空 → 如实说「没有候选」，**不要**改成用常识答。
- 用户要「把索引重建一下」→ 那是**整链的活**：走 `kb-pipeline`（由它调本 skill 的写档档位）。
- 召回队列里出现两条互相矛盾的单元 → 报冲突，交 `kb-check`，不要自己裁决。
---

## 会话蒸馏回灌（2026-10-15）

本 skill 的知识面由**会话蒸馏**持续回灌，两个文件：

- `references/会话蒸馏回灌.md` —— 从 2026-10-05~10-15 的 DSH 会话里蒸出来的
  **可执行动作 / 禁止动作 / 风险点**，每条都带**可回源的依据指针**（`case_id` + `会话:seq` + 逐字引文）。
- `references/自生长台账.md` —— 每轮长了什么、回验过没过、闸门结果。

**怎么用**：

- 处理相关任务**之前**先读这两个文件 —— 里面是别人真踩过的形状，不是通用建议。
- 它们**不修改本 skill 的任何指令**：**与上文任何一条冲突时，以上文为准**。
- 里面的条目是 **E2（草稿级、可审查、未获批）**，不是已批准的规则；要拿它下结论前先看它的依据指针。

**它怎么长**：每日 04:10 由 `com.kb.skill-growth` 自动**追加**（只追加、不改已有行）。
护栏写在 `kb/l7/registry/skill-growth.yaml`：frontmatter / 触发词 / 正文**机器一律不许改**，
每条指针必须逐字回源，一条不过整轮不写，写完必须过 `skills_check.py` 第 3 类否则回滚。
