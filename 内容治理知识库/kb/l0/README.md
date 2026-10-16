# L0 原始库 · 内容治理知识库

本目录是「Momcozy 知识库-内容治理知识库」的 **L0 原始库**。L0 只做两件事：
**把源侧对象登记下来**、**算出确定性指纹**，供后续层做变更判定。
L0 不解析正文、不切分内容、不判定业务域。

- 本次 run_id：`20260923-1117`　|　scanner_version：`0.5`
- 入口：`https://momcozy-in.feishu.cn/base/GnRZbIuXraCzf0sGr2UcmZ62nfc?table=tblMGtPfe8ZUsEdP&view=vewHCQJrgo`
- 筛选：`材料审核状态 == 通过`　|　下钻：**存全链、用两层**（链条记到第 3 层，规则提取只用前两层）

## 目录名 ↔ kb_type 对照表

| 目录名（人读） | kb_type（机器键） | label | 本类条数 |
|---|---|---|---|
| `1_外部标准库/` | `external_standard` | 外部标准库 | 55 |
| `2_内部正负样本库/` | `internal_sample` | 内部正负样本库 | 7 |
| `3_措辞表达库/` | `wording` | 措辞表达库 | 301 |
| `4_产品描述库/` | `product_desc` | 产品描述库 | 4 |
| `9_未归类/` | `unknown` | 未归类（不猜） | 37 |

> 机器判断分类一律查 `registry/kb.json` 的 `dir_map` / `dir_map_reverse`，**不要硬编码中文目录名**。
> 分类只能靠重跑改，**不要手工 `mv` 或重命名文件**。

## 目录与文件

| 路径 | 作用 |
|---|---|
| `1_外部标准库/` … `9_未归类/` | 每个资源一个 json，库内平铺；**每个文件内部都带 `kb_type` 字段** |
| `records/<源表名>/` | 记录级留痕，字段原值 verbatim；公式/查找字段只存表达式＋依赖字段 |
| `registry/kb.json` | `dir_map` / `kb_types` / `rules` / `field_roles` / `fingerprint_policy` / `kb_version` |
| `links/graph.jsonl` | 下钻边表，深度到第 3 层 |
| `manifest.jsonl` | append-only 台账，主键 `(resource_key, observed_at)` |
| `index/l0.jsonl` | 台账投影（5 字段，不含正文） |
| `candidates/<run_id>.json` | 本次时点切片，**未验收，不可作为最终依据** |
| `runs/<run_id>.json` | 筛选快照（命中＋排除留痕） |
| `runs/<run_id>.report.md` | 本次报告 |
| `runs/<run_id>.ops.log` | 全部外部调用＋读写性质 |
| `../versions/versions.jsonl` | 版本账本，本轮 **0 条版本行** |
| `../versions/VERSIONS.md` | 由 `versions.jsonl` 投影生成，不许手工维护 |

## 只读约束

源侧零改动：本轮对外部只有读调用，无任何 `create / update / delete / move / permission` 写调用；
不在飞书侧建标记字段、不回写状态、不改权限。全部调用见 `runs/20260923-1117.ops.log`。
所有写入只落在本工作区的 `kb/` 下，`kb/` 不在任何飞书同步目录内。

## 指纹

统一 sha256，但**必须写明对什么算**（`sha256_input`）：
`doc_text` / `record_fields` / `file_bytes` / `url_text` / `structure`。
规范化确定性：UTF-8、`\n`、去行尾空白、折叠空行、键排序、剔除 `last_modified_time` / `last_modified_by`。
读不到内容时 `sha256: null` 并写明原因（`sha256_state`）。

## 版本号是两层，不要混成一个字段

| 字段 | 含义 | 例子 |
|---|---|---|
| `kb_version` | **每类库独立**的版本号 | `external_standard: v3` |
| `release_id` | **组合发布号**，跨库一次性发布 | `rel-0007` |

L0 阶段两者都不产生：`kb_version` 恒为 `v0`，不出现 `release_id`。
