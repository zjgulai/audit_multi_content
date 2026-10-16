# 红线依据与反例 —— brand-product-fact-curator

> 口径时间：2026-09-30。每条红线的「依据」都是从库内源码 / 策略文件实读的原文，
> 不是对设计意图的转述。源码行号对应 `kb/l7/review-engine/core/*.py`。

---

## 红线 1 · 审批前活动事实库必须为空

**依据（代码）**

- `product_fact_approval.py:79 rebuild_library(queue, *, source_queue=None)`
  只遍历 `approved_facts(queue)` 造 `approved_facts` 数组 —— **队列里没批准的进不来**。
- `product_fact_queue.py:190 approved_facts(queue)`
  = 只取「审批齐 + 证据齐」的条目。
- `product_fact_approval.py:89`：`"status": "active" if facts else "approval_required"`
  → 空库时 `status` **必须**是 `approval_required`。

**依据（策略原文）**

- `product-fact-library.json` 的 `policy`：
  *"Discovery pages and proposed facts cannot support automatic PASS until required product,
  legal, and medical approvals are recorded."*

**反例（都不许做）**

| 反例 | 为什么错 |
|---|---|
| 手工把 `seed-products.json` / 发现页条目塞进 `product-fact-library.json → approved_facts` | 绕过了 `rebuild_library`，等于自己造了一个"已批准"，下游 `产品宣称核验` 会当成事实用 |
| 看到 `approved_facts: []` 就去「补数据」 | 空库是设计态（判据：方案 §9 L3「owner 审批前活动事实库保持为空」）；补进去就是事故 |
| 直接 `'w'` 覆盖 `product-fact-library.json` | 该文件由 `rebuild_library` 生成，手工改会在下次重建时被无声覆盖，且期间对外是错的 |

---

## 红线 2 · 角色矩阵不齐 = 没批准

**依据**（`product-fact-approval-policy.json`）
`approval_policy_version = "product-fact-approval-2026-09-24"`，`status = confirmed_by_user`
（2026-09-24 用户已确认），`matrix` 见 `approval-matrix.md`。

`claim_wording_required: true`，`policy` 原文：
*"A claim phrase is not approved until the required roles approve it and an allowed wording is recorded."*

**反例**

- 健康 / 安全 / 功效类宣称只拿到 `product` 一个角色就放行 → 缺 `legal` + `medical`。
- 角色齐了但**没记 `--approved-wording`** → 仍不算批准（`claim_wording_required` 为 true）。

---

## 红线 3 · 证据必须是抓取到的快照

**依据（代码）**

- `product_fact_queue.py:55 _has_fetched_evidence(refs)`
  = `any(ref.fetch_status == "fetched" and ref.snapshot_sha256 ...)` —— 两个条件都要。
- `product_fact_queue.py:36 _evidence_refs()` 从 `source-manifest.json` 解析出
  `snapshot_sha256 / snapshot_path / retrieved_at / fetch_status`，
  解不到的记 `fetch_status: "unresolved"`。

**依据（消费侧原文）**

- `产品宣称核验`（brand-product-claim-verifier）SKILL.md：
  *"Never treat a generic product page as proof for a different model."*
  并把 `insufficient_evidence` / `out_of_scope` 默认判 REVIEW。

**反例**

- 引用 URL 但 `fetch_status` 不是 `fetched` → 属于 `insufficient_evidence`，不得支撑 PASS。
- 拿 A 型号的通用产品页去支撑 B 型号的宣称。

---

## 附带一条工程红线（不是判定口径，是操作安全）

两个引擎**都没有 `--apply` 干跑档**：
`product_fact_queue.py:236 main()` 解析完参数就直接
`args.output.parent.mkdir(...)` + `args.output.write_text(...)`；`product_fact_approval.py` 同理。

→ **跑第 1 条命令前先备份队列**，否则会把在审条目整体覆盖。
现行队列实测 33 条、`status=pending_owner_approval`（2026-09-30）。
