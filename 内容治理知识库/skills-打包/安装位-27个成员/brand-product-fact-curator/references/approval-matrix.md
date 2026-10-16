# 审批矩阵与判定口径

> 来源：`kb/l7/review-engine/knowledge-base/product-fact-approval-policy.json`（实读原文）
> `approval_policy_version = product-fact-approval-2026-09-24` ｜ `status = confirmed_by_user` ｜ `confirmed_at = 2026-09-24`

---

## 1. 角色矩阵（`matrix`）

| 宣称类型（claim kind） | 必需角色 |
|---|---|
| `verified_fact` | `product` |
| `objective_or_comparative_claim` | `product`、`legal` |
| `health_safety_efficacy_claim` | `product`、`legal`、`medical` |

→ 角色**全齐才算批准**；缺一个就是「未批准」，条目留在队列里，不得进活动库。

## 2. 健康 / 安全 / 功效判定词表（`health_safety_efficacy_tokens`）

命中下列任一 token 的宣称，按 `health_safety_efficacy_claim` 处理（需三角色）：

```text
health, medical, germ, safe, feeding, cross-contamination,
painless, milk flow, drainage
```

> 口径提示：这是一张**小写英文 token 表**，按原文照录。中文内容不在这张表里 ——
> 因此中文宣称的类型判定不能只靠这张表，需结合 `产品宣称核验` 的 claim 归一结果。

## 3. 另外两条硬口径

| 字段 | 值 | 含义 |
|---|---|---|
| `claim_wording_required` | `true` | 必须记录 **allowed wording**（`--approved-wording`）才算批准；只说"同意"不算 |
| `policy` | *"A claim phrase is not approved until the required roles approve it and an allowed wording is recorded."* | 上一条的原文 |

## 4. 引擎侧的取值域（写错会被 argparse 挡掉）

| 参数 | 合法值 |
|---|---|
| `--decision` | `approved` \| `rejected` \| `needs_input`（源码 `VALID_DECISIONS`） |
| `--role` | `product` \| `legal` \| `medical` |

**队列里实际出现的条目态（2026-09-30 实测）**：只有
`pending_product_owner` 与 `pending_product_legal_review` 两种，队列整体 `status=pending_owner_approval`。
→ 条目态与 `--decision` 的取值域是**两套词表**，不要混用：条目态描述"卡在谁那"，
`--decision` 描述"这一次裁决是什么"。

## 5. 事件幂等键（决定了重复提交的行为）

```text
event_id = "EVT-" + sha256("fact_id|decision|actor|role|approved_wording")[:20]
```

- 同一 `event_id` 再次提交 → `apply_event` 直接返回原队列（**no-op**）。
- 换了 actor 或 approved_wording → 是**另一个事件**，会新增一条审批记录。
