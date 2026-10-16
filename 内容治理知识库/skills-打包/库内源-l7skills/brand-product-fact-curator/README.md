# brand-product-fact-curator

SKU 级产品事实基线的唯一写入者（L3）。把「事实提案 → 角色审批 → 活动事实库」这条链走对；
核验内容里的宣称不归它管（走 `产品宣称核验` / brand-product-claim-verifier）。

- **层**：L3（但**不写 `kb/l3/**`**，产物落在 `kb/l7/review-engine/knowledge-base/`）
- **引擎**：`kb/l7/review-engine/core/product_fact_queue.py`、`product_fact_approval.py`
- **登记**：`kb/l7/registry/skills.yaml` → `brand-product-fact-curator`
- **创建**：2026-09-30（N4 规划项落地），依据 `root-skills-creator` 标准

## Structure

```
brand-product-fact-curator/
├── README.md
├── SKILL.md
├── .skill-meta/
│   └── manifest.yaml
└── references/
    ├── redlines.md         三条红线的原文依据与反例
    ├── approval-matrix.md  角色矩阵、token 表、判定口径
    └── engine-map.md       引擎函数级映射与产物字段
```

## 三条红线（摘要）

1. **审批前活动事实库必须为空** —— `approved_facts` 只能由 `rebuild_library` 从已批准条目重建。
2. **角色矩阵不齐 = 没批准** —— `verified_fact→[product]`；比较类 `→[product,legal]`；健康/安全/功效 `→[product,legal,medical]`；且必须记录 allowed wording。
3. **证据必须是抓取到的快照** —— `fetch_status=="fetched"` 且 `snapshot_sha256` 非空。

## Usage

按 `SKILL.md` §3 的三条命令执行；`references/` 里的行号均对应 2026-09-30 的库内源码。
两个引擎**都没有 `--apply` 干跑档**，跑第 1 条命令前先备份队列。

## Compatibility

| 模型 | 状态 | 备注 |
|------|------|------|
| Claude / Cursor / Kimi / Codex | native | 完整支持 |
| DSH | native | `kbpy` + `kb/.kb-python` 同机可用 |
| GPT / MiniMax | bridge | 长任务需分步 / 输出需压缩 |

## 未验证项

**尚未过 `root-skills-eval` 触发盲测**（与同批 `kb-clause-extractor` 同一状态）。
