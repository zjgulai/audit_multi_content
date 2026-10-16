# kb-recall · 层操作手册（L6 召回层）

> 本文件是 `kb-recall/SKILL.md` 的**详情页**（渐进式披露）。
> SKILL.md 只留「解释器硬约束 / 两条通道要点 / 红线 / 写档档位指针」；判据与写档细目在这里。
> cwd 一律 `~/.dsh/Momcozy知识库`（= `kb/` 的上一级）。

---

## 一、两条检索通道（细目）

### 1.1 L6 双索引召回（首选）

| 项 | 位置 |
|---|---|
| 检索器 | `kb/l6/retriever.py`（`--query` / `--top` / `--mode` / `--kb-type` / `--json` / `--selftest`，**不写盘**） |
| BM25 索引 | `kb/l6/bm25/`（`docs` / `postings_zh` / `postings_en` / `meta`） |
| 向量索引 | `kb/l6/vectors/`（`vectors.jsonl` / `matrix.npy` / `meta.json`） |
| 注册表 | `kb/l6/registry/l6.json`（`retrieval_capability` / 模型 / 维度 / 已知限制） |
| 范围 | `kb/l6/SCOPE.txt`（L6 只覆盖可用单元的一个子集，**不是全量**） |
| 基准 / 自测 | `kb/l6/benchmark.json` · `kb/l6/selftest.json` |

**模式**：`vector_plus_bm25`，模型 `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`
（384 维，fp16 ONNX，本地 CPU）。

### 1.2 本地目录分层索引导航（原 `kb-retriever` 的能力，一并保留）

1. **先导航**：根目录与各级子目录的 `data_structure.md` 构成多级索引树；先读索引，再定文件。
2. **遇到 PDF / Excel 必须先读 references 学处理方法**，再处理文件：
   - PDF → `references/pdf_reading.md`（优先 `pdftotext`，表格用 `pdfplumber`）
   - Excel → `references/excel_reading.md` / `references/excel_analysis.md`（`pandas` + `nrows` 限制）
3. **渐进式检索**：`grep` / 局部读 / 分页处理，**不整文件加载**；检索轮次有上限。
4. 脚本：`scripts/convert_pdf_to_images.py`（无 shebang 的已知问题，用 `python3 <脚本>` 调用）。

> 原 `kb-retriever` 已于 2026-09-29 **并入本 skill**：它的触发语、分层导航流程、
> PDF/Excel references 全部迁到这里。`kb-retriever` 不再作为独立入口。

---

## 二、输出契约

```
命中 N 条（模式：<vector_plus_bm25 | 目录导航>）
1) unit_id=<...> ｜ 锚点=<anchor> ｜ source_sha256=<...> ｜ 片段：<逐字摘录>
   …
覆盖范围：kb/l6/SCOPE.txt 声明的可用单元数（**不是全量**）
```

**必须带的三样**：`unit_id` / 锚点 / `source_sha256`。缺一样，下游（`kb-review`）
就没法把它当依据用。

---

## 三、已知限制（来自 `l6/registry/l6.json`，别夸大能力）

- **跨语言只有弱对齐**：中文查询能拿到英文素材的较高相似度，**不等价于翻译级召回**。
- **同义改写受限**：2019 年的多语 MiniLM（384 维），对行业黑话 / 新造词区分有限。
- **规避型表述召回受限**：拼音、拆字、谐音、符号分隔、小语种本来就绕开字面，向量未必抓到。
- **无重排**：Top-N 只做 RRF 融合，长尾排序质量未校验。
- **无命中阈值**：一律返回 Top-N，**不带相关性阈值**；是否采纳由下游判定。
- **融合分不能当阈值用**：RRF 分只是名次的倒数（Top1 恒为 `1/(k+1)=0.016393`）。
- **覆盖不是全量**：`l6.json → scope.usable_units` 有明确分母，报召回率时必须用对分母。

---

## 四、写档（只被 `kb-pipeline` 以层身份调用时走）

### 4.1 三条件（缺一不可，缺任一条只许停在查询档）

| # | 条件 | 怎么判 |
|---|---|---|
| ① | **由 kb-pipeline 以层身份调用** | 调用方是 `kb-pipeline`，且带 `RUN=<YYYYMMDD-HHMM>` 与「只跑 L6」 |
| ② | **`--apply`** | 不带即预演；预演只报「会写什么」，不落盘 |
| ③ | **人开闸** | 写档白名单见 `kb_pipeline.py` 的 `SYNC_ALLOWED`；越界要人点名 `--allow-beyond-policy` |

### 4.2 写档跑什么

**引擎清单不写在本节** —— 读 `kb/l7/registry/layers.yaml` **L6 层的 `engine`**（唯一真源）。
本层两个引擎都由本 skill 认领（2026-09-30 收口）：

| 引擎 | 干什么 | 谁认领 |
|---|---|---|
| `kb/.work/l6_build.py RUN` | 建索引（向量 + BM25） | 本 skill |
| `kb/.work/l6_bench.py` | 性能验收 | 本 skill（**此前无任何层 skill 认领，本轮补上**） |

`RUN` 用调用方传进来的那个 run_id，**不要自己造 run_id**。

### 4.3 写档红线（L6 专有）

- **解释器硬约束**：一律 `kb/kbpy`。受管 python 缺 `numpy` / `fastembed`，
  而建索引两者都要（`kb/l6/retriever.py:245` `np.load(matrix.npy)`、`:249` `from fastembed import TextEmbedding`）。
  **不合格就报错退出，不静默降级。**
- **幂等键是双键**：向量 `(unit_id, segment_index, content_hash, model, dim, quantization)`；
  BM25 `(unit_id, content_hash, tokenizer_version)`。同口径重跑应是**幂等空操作**
  （实测：BM25 本次切词 0 条、索引无变化不重写；向量新增/变更 0、embedding 调用 0 次）。
- **有守卫**：`write_if_changed` —— 内容未变则不重写；**不要为了「跑一遍」去动 `SCOPE.txt`**。
- **`SCOPE.txt` 是人工核定白名单**：它决定哪些单元进索引；改它 = 改召回范围，属人的动作。
- **跑完回闸门**：`kb/kbpy l7/scripts/l6_gate.py`；该闸门是**只读档**，有 4 项明写「没跑」
  （③重跑幂等 ⑥分段拼接 ⑦倒排词频 ⑨冻结基线）—— **别把「闸门过」说成「索引全对上」**。
  需要完整档（会重建索引）时由**人**跑 `kb/.work/l6_integrity.py <RUN>`，不许在无人值守里跑。
