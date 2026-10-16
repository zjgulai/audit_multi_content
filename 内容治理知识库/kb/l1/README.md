# L1 文本抽取层 · 内容治理知识库

L1 从 **L0 台账**抽取「带位置的文本段 + 表格行 + 媒体文本」。**`kb/l0/` 全程只读**，
抽取产物一律写在 `kb/l1/`，L0 永远可重抽、可核对。

- 本次 run_id：`20260923-1215`　|　extractor_version：`l1-0.1`　|　OCR：`vision-jxa-1.0`
- 锚点规范版本：`anchor-1.0`（见 `kb/l0/registry/kb.json` 的 `anchor_spec` 与本目录报告）

## 目录名 ↔ kb_type（与 L0 一致）

| 目录 | kb_type | 资源数 |
|---|---|---|
| `1_外部标准库/` | `external_standard` | 55 |
| `2_内部正负样本库/` | `internal_sample` | 209 |
| `3_措辞表达库/` | `wording` | 301 |
| `4_产品描述库/` | `product_desc` | 4 |
| `9_未归类/` | `unknown` | 37 |

## 目录与文件

| 路径 | 作用 |
|---|---|
| `1_外部标准库/` … `9_未归类/` | 一个资源一个 json（结构同 L0，`kb_type` 直接继承 L0） |
| `media/<resource_id>/` | 图片原图 + `ocr.json`（逐行文本 + bbox + 置信度 + 文件 sha256） |
| `index/l1.jsonl` | 一行一个单元：`seg_id / resource_id / kb_type / kind / anchor / char_count` |
| `manifest_l1.jsonl` | 抽取台账，主键 `(resource_id, extractor_version, source_sha256)`，append-only |
| `runs/<run_id>.json` / `.report.md` / `.ops.log` | 运行快照 / 报告 / 外部调用台账 |
| `../l0/` | **只读**：L0 是原始登记的真相 |

## 资源 json 字段

`resource_id` / `kb_type` / `source_sha256` / `extractor_version` / `status` / `anchor_spec` /
`segments[]` / `tables[]` / `media_refs[]` / `observed_at`

`status` 枚举：`ok` | `empty` | `partial` | `pending_ocr` | `pending_transcribe` |
`no_scope` | `forbidden` | `unreachable`

## 锚点规范（anchor-1.0）

| 资源类型 | 锚点格式 |
|---|---|
| pdf | `#p.12` / 表格 `#p.12/tbl.3/r.5` |
| docx | `#h.<标题路径>` 或 `#para.35` |
| pptx | `#s.7` |
| xlsx | `#<Sheet>!B4:D9` |
| md / txt | `#l.120-140` 或 `#h.<标题路径>` |
| 图片 | `#img.<序号>` |
| 视频 | `#t.00:12:30-00:15:10` |
| 飞书文档 | `#block.<block_id>` 或 `#h.<标题路径>` |
| 飞书记录 | `#<表名>/<record_id>/<字段名>` |

**铁律：锚点必须来自原文的物理位置，不得编造。** 定位不到就进报告的「无法定位锚点」清单。

## 幂等

主键 `(resource_id, extractor_version, source_sha256)`。三者都没变 → `unchanged`，**跳过，不重跑 OCR/转写**。
只处理三类：台账里没有的、`source_sha256` 变了的、`extractor_version` 变了的。
