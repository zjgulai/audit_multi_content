# 条目字段定义（`_meta/entry-schema.md`）

> 本文件是 `~/.dsh/plugins/dsh-kb/lib/kb.js` 里字段校验的**人类可读对照**。
> 权威来源是代码：`REQUIRED` / `SOURCE_REQUIRED` / `VERIFICATION_REQUIRED` / `PROVENANCE_REQUIRED` / `L4_ANCHORS`。
> 本文件**不被代码读取**（代码只在 `GUIDE.md` 缺失时的兜底提示里提到它），改这里不会改变闸门行为。
>
> 落盘位置：`<知识库根>/<子库>/<层目录>/<id>.md`，YAML frontmatter + Markdown 正文。

## 一、层目录（`tier` ↔ 目录名，写错报 E019）

| `tier` | 目录 | 收什么 |
|---|---|---|
| `L0` | `L0-raw` | 原文存档（反蒸馏四类住这层，**只许引用不许摘要**） |
| `L1` | `L1-facts` | 事实（`kind: fact`） |
| `L2` | `L2-concepts` | 判断（`kind: judgment`）—— **只收 judgment**（E023） |
| `L3` | `L3-graph` | 关系/图谱 |
| `L4` | `L4-contracts` | 契约（**只收 judgment**，且须带三个 L4 锚点） |

## 二、必填字段（19 个，缺任一即报错）

| 字段 | 说明 |
|---|---|
| `id` | 全局唯一，禁覆盖已存在的 id |
| `title` | 标题 |
| `tier` | `L0`/`L1`/`L2`/`L3`/`L4`，须与所在层目录一致 |
| `collection` | 子库 id，须在 `_meta/collections.yaml` 登记（否则 E018） |
| `topic` | 本项目口径（本库实际取值：`规则` / `知识` / `未登记规则码`） |
| `summary` | 一句话摘要 |
| `owner` | **具名人或角色位**，禁写「团队/大家/待定/TBD」等占位（在 `OWNER_PLACEHOLDERS` 里） |
| `kind` | `judgment` 或 `fact`（其他值报 E020） |
| `evidence_level` | `L1`–`L5` |
| `data_level` | 密级；**门控三件套之一**，非空率须 100% |
| `half_life_days` | **整数天数**（非整数报 E007）；低于 `intake.yaml` 的 `half_life_floor_days` 报 E029 |
| `created_at` | 创建日期（`YYYY-MM-DD`） |
| `valid_until` | 失效日期；**门控三件套之一**；当天仍算有效（日期级归一） |
| `asks` | **非空列表** —— 这条能回答什么 |
| `not_proves` | **非空** —— 不能由它证明什么（边界声明） |
| `source` | 见下 |
| `provenance` | 见下 |
| `sensitivity_level` | `L1`–`L4`；`L3`/`L4` 不得送公网 LLM（W008） |
| `pii` | 见下 |

### 门控三件套（`TRIPLET`，非空率必须 == 100%）

`data_level` / `valid_until` / `owner` —— 缺任一即 E014。

## 三、`source`（4 个子键必填）

| 子键 | 说明 |
|---|---|
| `kind` | 来源类型（须在枚举内，否则 W004） |
| `ref` | 来源引用（URL / 表名+记录号 / 文件路径） |
| `fingerprint` | 指纹；验不过拒收（E030） |
| `captured_at` | 抓取日期 |

> 粒度纪律（W023）：指纹只到「表/文档 @rev」粒度时，回源只能判断"这个表变过没有"，
> 判断不了"哪条记录变了" —— 能到记录级时应补 `source.record_ids`。

## 四、`provenance`（2 个子键必填）

| 子键 | 说明 |
|---|---|
| `anchor` | **原文物理位置**（`#para.35` / `#<表名>/<rec>/<字段>` / `#img.N[@r…]` / `#t.00:12:30-00:15:10`）。**不得编造**，定位不到就进「无法定位锚点」清单 |
| `confidence` | 确定性（本库取值：`确定` 等） |

## 五、`verification`（三重验证，5 个子键）

**只对 `kind: judgment` 且 `tier != L0` 的条目强制**（`needsVerification`）；
原文（`L0`）与事实（`fact`）免验 —— 它们靠 `source` + `evidence_level` 交代来源与可靠度。
缺 `verification` 报 **E021**。

| 子键 | 取值 | 说明 |
|---|---|---|
| `independent_sources` | `2` / `1` / `0` | 独立佐证 |
| `predictive` | `2` / `1` / `0` | 预测力 |
| `non_obvious` | `2` / `1` / `0` | 非常识 |
| `score` | 数字 | **必须能对上 `score_formula`**（`intake.yaml` 的 `得分 ÷ 6`，做算术一致性校验） |
| `verdict` | 字符串 | 按 `intake.yaml` 的 `triple_verification.verdict` 分档：`keep` / `review` / `discard` |

> ✅ **已处置（修复计划 F5 / F6，2026-09-29）**：原先 56 条 `form=entry` 落在 `L2-concepts`、
> `kind: judgment`，而 judgment 强制要求 `verification`（5 个子键）→ 报 `E021 × 56`。
> **没有**给它们补 `verification` —— 三重验证是**人工判断闸门**，派生视图替人打分
> 等于把闸门变成自我申报（`kb/l3/registry/l3.json` 排除这 56 条判断类概念用的是同一条理由）。
> 实际处置是**降层**：`tier: L2 → L1`、目录 `L2-concepts/ → L1-facts/`、`kind: judgment → fact`。
> E023 只禁止 `fact` 进 L2/L4，**L1-facts 收 fact 合法**，于是 E021 与 E023 同时不再适用。
> 实测：`E021 56 → 0`，`errors 508 → 452`（其余 452 条为 E026，见修复报告 F2 §三）。
>
> **回填路径**：等人工过完三重验证后，逐条补真的 `verification` 并升回 `L2-concepts` + `judgment`。
> `L2-concepts/` 目录保留为空，就是给这一步留的位置。

## 六、`L4-contracts` 额外三锚点（`L4_ANCHORS`）

`rollback_to` / `last_validated` / `validated_by`。

## 七、`pii`（P0 红线，E028）

| 子键 | 说明 |
|---|---|
| `detected` | **必须是布尔值**（非布尔报 E028） |
| `masked` | `detected: true` 时必须为 `true`，否则报「检出 PII 但未脱敏 —— 未脱敏不入库」 |
| `strategy` | `detected: true` 时必须写明脱敏策略（如 `mask-phone-keep4`） |

> **脱敏要在写入时做，不是输出时做。**

## 八、可选的反蒸馏/治理字段

| 字段 | 说明 |
|---|---|
| `forbidden` | 不许怎么用（如"不许把 P 级/风险等级当放行结论"） |
| `kb_class` | 出自哪一类素材（四类库），须在 `_meta/kb-classes.yaml` 枚举内（E046） |
| `evidence_group` | 拿来干什么（判断/检索/线索），须在 `_meta/evidence-groups.yaml` 枚举内（E043）；缺则报 W036 |
| `sensitivity_level` | 见上 |
| `derived_from` / `complements` / `contrasts_with` | **有类型的引用边**（DG8）。新条目用这三个，**不要用已弃用的 `related`**（W025）—— 一个字段表达三件事会让回源与重算无法机械化 |
| `supersedes` / `conflicts_with` / `conflict_status` | 生命周期与冲突 |

## 九、六个体检维度与三个「没有分母」的维度

| 维度 | 阈值 | 供数 |
|---|---|---|
| 新鲜度 | ≥ 0.90 | `valid_until` |
| 三件套完整率 | == 1.0 | `data_level`/`valid_until`/`owner` |
| 一致性 | ≥ 0.95 | 未裁决冲突占比 |
| 孤岛率 | ≤ 0.20 | 引用边（`LINK_KEYS`） |
| 覆盖率 | ≥ 0.80 | **黄金问题集** `<子库>/tests/golden-questions-*.md` |
| 利用率 | ≤ 0.30 | **查询日志** `_meta/query-log.ndjson` |
| 幻觉率 | ≤ 0.10 | **证据回验**（`min_coverage_to_score` 达标才进分母） |

> **健康分只在有分母的维度上算。** 后三维没有供数时为 `noData` 并被跳过 ——
> 所以「健康分 100」不等于「库没问题」：本库当前 508 个 error 与健康分 100 并存。
