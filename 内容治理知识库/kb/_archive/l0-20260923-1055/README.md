# L0 原始库（内容治理知识库 · 原始登记层）

本目录是「内容治理知识库」的 **L0 原始库**。L0 只做一件事：**把源侧对象登记下来并算出指纹**，
供后续层做变更判定。L0 不理解内容、不切分内容、不判定业务归属。

---

## 一、只读约束（最高优先级）

1. **原目录零改动。** 不得修改、移动、重命名、删除、回写原始库（含飞书侧）的任何内容、
   字段、状态、权限。L0 阶段全部外部调用**只允许读**。
2. **不向飞书侧写入任何内容。** 不建「已处理 / 已入库」标记字段，不回写审核状态，不改权限。
3. **所有写入只允许落在本工作目录的 `kb/` 下。** 落库目录不在任何飞书同步目录内。
4. 外部调用的对象与读写性质逐条记入 `runs/<run_id>.ops.log`，跑完在报告里复核。

## 二、本阶段做什么

- 从入口链接递归展开（表 / 目录 / 文档，以及文档内指向的其他链接），下钻层数 **2**。
  记录时保留完整链条，规则提取只用前两层。
- 冻结**筛选快照**：只取「材料审核状态 = 通过」的记录；命中与排除（含原因）都登记。
- 每条记录一个 json，字段原值 verbatim 落库。
- 按 `link / attachment / image / video` 角色下钻，登记资源并算 **sha256** 指纹。
- 维护 append-only 台账 `manifest.jsonl`，并按 `resource_key` 做增量幂等（registered / unchanged /
  updated / retracted / restored / gone / no_permission）。
- 由台账投影出 `index/l0.jsonl` 与 `candidates/<run_id>.json`。

## 三、本阶段明确不做什么

- 不做结构化切分、不生成条款号、不做 OCR、不转写、不抽帧。
- 不判定 9 大业务域。
- 不调 embedding、不建向量索引。
- **不生成版本号、不做发布。** `registry` 里 `kb_version` 固定 `"v0"`；不产出 `releases/`。
- 不猜测归属、不补造字段。不确定的一律 `unknown`。
- 失败不静默跳过：登记为 `status_reason` 或 `status`（forbidden / not_found / unsupported / timeout），
  最多重试 2 次。

## 四、版本号是两层，不要混成一个字段

| 字段 | 含义 | 例子 |
|---|---|---|
| `kb_version` | **每类库独立**的版本号 | `external_standard: v3` |
| `release_id` | **组合发布号**，跨库一次性发布 | `rel-0007` |

L0 阶段两者都不产生：`kb_version` 恒为 `v0`，`release_id` 不出现。
`kb/versions/` 只放指针，不放内容副本。

## 五、语言约定

- **人读内容用中文**：`label`、说明文字、报告正文、规则 `note`。
- **机器键保持英文小写枚举**：`kb_type`、`status`、`source_kind`、`sha256_input`、`sha256_state`
  以及所有字段名。
- **正文一律保留原文，不翻译。**

## 六、目录与文件

| 路径 | 作用 |
|---|---|
| `README.md` | 本文件 |
| `registry/kb.json` | 表 / 字段 → `kb_type` 的映射规则、`field_roles`、指纹策略 |
| `records/<table>/<record_id>.json` | 记录字段原值 verbatim |
| `resources/<resource_id>.json` | 下钻到的资源登记信息（含 sha256） |
| `links/graph.jsonl` | 下钻边表 `{from_kind, from_id, to_kind, to_id, depth, field_id, status}` |
| `manifest.jsonl` | **append-only 台账**，主键 `(resource_key, observed_at)` |
| `index/l0.jsonl` | 台账投影，仅 `resource_key / kb_type / source_kind / status / entry_url`，不含正文 |
| `candidates/<run_id>.json` | 本次时点的台账视图切片，**未验收，不可作为最终依据** |
| `runs/<run_id>.json` | 本次运行的筛选快照与统计 |
| `runs/<run_id>.report.md` | 本次运行报告 |
| `runs/<run_id>.ops.log` | 本次全部外部调用台账（调用对象 + 读写性质） |
| `../versions/versions.jsonl` | 版本指针流水，L0 阶段**只有头部说明、零版本行** |
| `../versions/VERSIONS.md` | `versions.jsonl` 的投影，**必须由它生成，不许手工维护** |

## 七、指纹与幂等（要点）

- 指纹**统一 sha256**，但飞书对象没有统一的二进制流，所以每条资源必须写明 **`sha256_input`**
  （对什么算）：`doc_text` / `record_fields` / `file_bytes` / `url_text` / `structure`。
- 规范化必须**确定性**：同一内容在任意时间、任意顺序下算出的 sha256 必须一致。
  规则见 `registry/kb.json` 的 `fingerprint_policy.normalization`。规则一改必须全量重算并在报告里说明。
- `revision`（源侧版本号 / 更新时间）**只作辅助，不作变更判定主依据**。
- 台账 append-only：变更**追加新行**，用 `observed_at` 区分；取数取每个 `resource_key` 的最新一行。
  **不要重写整个 manifest。**
