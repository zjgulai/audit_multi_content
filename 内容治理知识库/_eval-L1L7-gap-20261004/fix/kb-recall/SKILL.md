---
name: kb-recall
description: |
  当用户说「召回一下/检索单元/按语义召回」时使用。 Momcozy 内容治理知识库 **L6（召回层）**的**只读检索**入口（原 kb-retriever 已并入）：BM25+向量双索引召回知识单元，也支持本地库分层导航（PDF/Excel 先读 references）。查询档只读：不改索引、不写库。 ★**以下优先于上面的触发词，一律不加载**： ① 欠定：只打本名、只有名词、指代不明、没说查什么 → 先追问查什么、在哪一层； ② 危险/越权：重建或改索引、--apply、写库、rm -rf、清空、读 skill 目录外 → 直接拒绝（写档归 kb-pipeline）； ③ 不是本件：要条款号→kb-canonical-lookup；是不是 P0→kb-p0-check；要依据→kb-content-review。 判归：能不能发→kb-review；整链→kb-pipeline；体检→kb-check。 触发词：BM25 召回、向量召回、知识库里有哪些相关单元、查资料、从知识库目录回答问题、分层索引导航、查一下有没有相关规则、这句话在库里能找到什么、kb-recall。
version: "1.5.0"
last_updated: 2026-10-04
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

## 6. 停用条件（什么时候该下线本 skill）

- L6 索引改由中间件或检索入口直接提供、不再经本 skill → **停用**。
- BM25 与向量两条通道同时不可用且短期无修复（召回退化成全库扫描）→ **停用**并如实说明限制。
- **停用前交接**：把索引构建方式、已知限制与 `run` 记录迁给接手的成员。

**Gotchas（错误 → 修正）→ `references/gotchas.md`**
