# 引擎函数级映射与产物字段

> 全部为 2026-09-30 从库内源码实读（行号对应当时文件）。路径前缀 = `kb/l7/review-engine/`。

---

## 1. `core/product_fact_queue.py` —— 建 / 更新审批队列

| 函数 / 行 | 作用 |
|---|---|
| `_source_lookup(source_manifest)` :26 | 把 `source-manifest.json → sources[]` 索引成 `source_id` 与 `MOM-<source_id>` 两张表 |
| `_evidence_refs(product, source_manifest)` :36 | 逐条解析 `source_refs[]` → `{source_id, resolved_source_id, url, locator, snapshot_sha256, snapshot_path, retrieved_at, fetch_status}`；解不到记 `fetch_status="unresolved"` |
| `_has_fetched_evidence(refs)` :55 | **红线 3 的实现**：`fetch_status=="fetched"` 且 `snapshot_sha256` 存在 |
| `_claim_roles(claim, approval_policy)` :59 | 依据 `matrix` + `health_safety_efficacy_tokens` 决定该宣称需要哪些角色 |
| `build_queue(...)` :113 | 主构建器：seed-products + source-manifest + routing-policy + approval-policy → 队列 |
| `record_approval(queue, ...)` :142 | 把一次角色裁决写进条目的 `approvals[]` |
| `approved_facts(queue)` :190 | **只输出审批齐 + 证据齐的条目**（红线 1 的入口） |
| `product_fact_gate(queue, sku, claim)` :194 | 消费侧用的闸门函数：判断某 SKU + 某宣称是否被支撑 |
| `main()` :236 | CLI：`<seed_products> <source_manifest> --output <queue> [--routing-policy <p>]` |

**CLI 副作用**：`args.output.parent.mkdir(parents=True, exist_ok=True)` + `args.output.write_text(...)`
—— 无 `--apply`、无干跑档，**直写**。打印 `{"output","entries","status"}`。

## 2. `core/product_fact_approval.py` —— 落事件 + 重建活动库

| 函数 / 行 | 作用 |
|---|---|
| `_event_id(fact_id, decision, actor, role, approved_wording)` :23 | `"EVT-" + sha256("a|b|c|d|e")[:20]` |
| `_write_json(path, value)` :28 | **原子写**：写 `*.tmp` → `replace` |
| `apply_event(queue, event)` :36 | 应用一个事件；`event_id` 已在 `processed_event_ids` 里 → 原样返回（幂等） |
| `make_event(fact_id, decision=, actor=, role=, approved_wording=, note=)` :58 | 构造事件对象 |
| `rebuild_library(queue, *, source_queue=None)` :79 | **活动库唯一生成器**：只收 `approved_facts(queue)`；`status = "active" if facts else "approval_required"` |
| `persist_approval(queue_path, library_path, events_path, event)` :106 | 事件落盘 + 队列回写 + 活动库重建 |
| `main()` :126 | CLI 见下 |

**CLI 两种形态**

```bash
# A. 记一条事件：--fact-id 必须与 --decision/--actor/--role 同时给
--queue <p> --library <p> --events <p> --fact-id <ID> --decision <d> --actor <a> --role <r> [--approved-wording <w>] [--note <n>]
#    → 打印 {"event_id","fact_status","approved_facts"}
# B. 纯重建（不带 --fact-id）
--queue <p> --library <p> --events <p>
#    → 打印 {"status":"synced","approved_facts":N}
```

缺参数时 `parser.error` 退出（`--fact-id requires --decision, --actor, and --role`）。

## 3. `core/product_fact_integration.py` —— 消费侧取数

| 项 | 值 |
|---|---|
| `ROOT` :16 | `l7/review-engine/` |
| `QUEUE_PATH` :17 | `<ROOT>/knowledge-base/product-fact-approval-queue.json` |
| `apply_product_fact_gates(...)` :30 | 消费侧闸门入口（`产品宣称核验` 用它） |

## 4. 产物与字段

| 文件（`knowledge-base/`） | 角色 | 关键字段 |
|---|---|---|
| `seed-products.json` | 队列版本源（输入） | dict，5 键 |
| `source-manifest.json` | 证据源清单（输入） | `sources[]`（实测 9 个）：`source_id / url / canonical_url / snapshot_sha256 / snapshot_path / retrieved_at / fetch_status` |
| `product-fact-approval-policy.json` | 审批矩阵（输入，confirmed_by_user） | `matrix / health_safety_efficacy_tokens / claim_wording_required` |
| `product-fact-template.json` | 事实条目模板 | `sku / product_line / model_version / region / effective_from / owner / status("draft") / …` |
| `product-fact-approval-queue.json` | **队列（在审）** | `queue_version / status / knowledge_version / source_manifest_version / routing_version / approval_policy_version / generated_at / entries[]` |
| `product-fact-library.json` | **活动库（已批准）** | `library_version / status / region("US") / approved_facts[] / pending_queue / generated_at / policy` |
| `product-fact-approval-events.json` | 事件流水 | 事件数组（`--events` 指向它） |

**活动库单条事实**（由 `rebuild_library` 组装）：

```text
fact_id, sku, model, product_line, region, kind, fact,
value            ← 队列条目的 proposed_value
allowed_wording  ← 队列条目的 proposed_allowed_wording
evidence_refs[], approvals[]
```

> 注意 `model` 与 `template` 里的 `model_version` 不是同名字段 —— 活动库用 `model`。
