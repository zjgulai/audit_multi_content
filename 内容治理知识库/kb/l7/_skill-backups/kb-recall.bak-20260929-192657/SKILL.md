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
  本 skill **只读**：不改索引、不写库。重建 BM25 + 向量索引是写操作，
  由 **kb-pipeline** 在 `--apply` 下编排 `kb/.work/l6_build.py RUN` 执行。
  不适用（各自点名）：
    · 查条款号 / 定稿了没有 → 走 **kb-canonical-lookup**；
    · 这个是 P0 吗 / 命中哪些 P0 模式 → 走 **kb-p0-check**；
    · 判断一段内容能不能发（要三态结论）→ 走 **kb-review**；
    · 已经给出结论、要追问依据 / 逐字摘录 → 走 **kb-content-review**；
    · 跑 L0 到 L7 / 同步知识库 / 重建索引 → 走 **kb-pipeline**；
    · 知识库体检 / 闸门 → 走 **kb-check**；问 skill 怎么分工 → 走 **kb-manage**。
version: "1.0.0"
last_updated: 2026-09-29
license: "Proprietary — Momcozy internal use only"
complexity: "standard"
compatibility:
  claude: { status: "native" }
  kimi: { status: "native" }
  cursor: { status: "native" }
  gpt: { status: "bridge", limitations: ["脚本执行需适配"] }
  minimax: { status: "bridge", limitations: ["长结果需分页"] }
  dsh: { status: "native", notes: "需 kb/kbpy（受管 python 缺 numpy/fastembed）" }
  codex: { status: "native" }
---

# kb-recall —— L6 召回层 · 只读检索（并入原 kb-retriever）

**一句话**：**只读召回**。要么走 L6 双索引（BM25 + 向量），要么走本地目录的分层索引导航。
**改索引是写操作，不在这里。**

## 1. 解释器（硬约束，先读）

L6 召回**必须**用库内约定解释器：

```bash
cd ~/.dsh/Momcozy知识库          # ★ cwd = kb/ 的上一级
kb/kbpy l6/retriever.py --help    # 一律走 kbpy
```

原因：受管 external-tools python **缺 numpy / fastembed**，而 L6 两者都要
（`kb/l6/retriever.py:245` `np.load(matrix.npy)`、`:249` `from fastembed import TextEmbedding`）。
配置在 `kb/.kb-python`（内容 `/usr/bin/python3`）。**不合格就报错退出，不静默降级。**

## 2. 两条检索通道

### 2.1 L6 双索引召回（首选）

| 项 | 位置 |
|---|---|
| 检索器 | `kb/l6/retriever.py` |
| BM25 索引 | `kb/l6/bm25/` |
| 向量索引 | `kb/l6/vectors/` |
| 注册表 | `kb/l6/registry/l6.json`（含 `retrieval_capability` / 模型 / 维度 / 已知限制） |
| 范围 | `kb/l6/SCOPE.txt`（L6 只覆盖可用单元的一个子集，**不是全量**） |
| 基准 / 自测 | `kb/l6/benchmark.json` · `kb/l6/selftest.json` |

**模式**：`vector_plus_bm25`，模型 `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`
（384 维，fp16 ONNX，本地 CPU）。

### 2.2 本地目录分层索引导航（原 `kb-retriever` 的能力，一并保留）

1. **先导航**：根目录与各级子目录的 `data_structure.md` 构成多级索引树；先读索引，再定文件。
2. **遇到 PDF / Excel 必须先读 references 学处理方法**，再处理文件：
   - PDF → `references/pdf_reading.md`（优先 `pdftotext`，表格用 `pdfplumber`）
   - Excel → `references/excel_reading.md` / `references/excel_analysis.md`（`pandas` + `nrows` 限制）
3. **渐进式检索**：`grep` / 局部读 / 分页处理，**不整文件加载**；检索轮次有上限。
4. 脚本：`scripts/convert_pdf_to_images.py`（无 shebang 的已知问题，用 `python3 <脚本>` 调用）。

> 原 `kb-retriever` 已于 2026-09-29 **并入本 skill**：它的触发语、分层导航流程、
> PDF/Excel references 全部迁到这里。`kb-retriever` 不再作为独立入口。

## 3. 输出契约

```
命中 N 条（模式：<vector_plus_bm25 | 目录导航>）
1) unit_id=<...> ｜ 锚点=<anchor> ｜ source_sha256=<...> ｜ 片段：<逐字摘录>
   …
覆盖范围：kb/l6/SCOPE.txt 声明的可用单元数（**不是全量**）
```

**必须带的三样**：`unit_id` / 锚点 / `source_sha256`。缺一样，下游（`kb-review`）
就没法把它当依据用。

## 4. 已知限制（来自 `l6/registry/l6.json`，别夸大能力）

- **跨语言只有弱对齐**：中文查询能拿到英文素材的较高相似度，**不等价于翻译级召回**。
- **同义改写受限**：2019 年的多语 MiniLM（384 维），对行业黑话 / 新造词区分有限。
- **规避型表述召回受限**：拼音、拆字、谐音、符号分隔、小语种本来就绕开字面，向量未必抓到。
- **无重排**：Top-N 只做 RRF 融合，长尾排序质量未校验。
- **无命中阈值**：一律返回 Top-N，**不带相关性阈值**；是否采纳由下游判定。
- **融合分不能当阈值用**：RRF 分只是名次的倒数（Top1 恒为 `1/(k+1)=0.016393`）。
- **覆盖不是全量**：`l6.json → scope.usable_units` 有明确分母，报召回率时必须用对分母。

## 5. 红线

- **只读**：不调 `l6_build.py`，不改索引，不写库。
- **不把 Top-N 当"命中"**：没有阈值就没有"命中"，只有"候选"。写结论时用"候选"。
- **不拿召回当依据级别**：L6 候选的证据级低于 L3 规则 / L5 P0，引用时要说清是哪一层。
- **不越过 SCOPE**：范围内的召回率不能当成全库召回率。

## 6. 何时停下来问人

- `kb/kbpy` 报"找不到合格解释器" → 报缺什么，不要退化成受管 python 硬跑。
- 召回结果为空 → 如实说"没有候选"，**不要**改成用常识答。
- 用户要"把索引重建一下" → 交 `kb-pipeline`（写操作 + `--apply`）。
- 召回队列里出现两条互相矛盾的单元 → 报冲突，交 `kb-check`，不要自己裁决。
