# 派生视图说明（内容治理知识库）

> 本目录由 `kb/.work/gen-host-library.py` 生成，**不是**人工灌入的权威知识库。
> 权威库在本工作区的分层库里：`kb/l0`（素材）→ `kb/l1/l2`（单元）→ `kb/l3`（规则）
> → `kb/l4`（条款号）→ `kb/l5`（P0 匹配）→ `kb/l6`（索引）。

## 为什么要有它

工作台（4317）的知识库是宿主库的**单向只读镜像**，判据是
`<根>/<子库>/L{0-raw,1-facts,2-concepts,3-graph,4-contracts}/*.md` + `_meta/collections.yaml`。
分层新库是 json/jsonl，镜像器扫不到任何条目 —— 这份视图就是给镜像器吃的那层壳。

## 生成规则（可复核）

| 事项 | 口径 |
|---|---|
| 条目粒度 | 按 `rule_id` 聚成 1 条（新库同一 rule 有 3 个行视图：entry / revision_pair / P0 行），**不是**按 1527 行 |
| 子库划分 | 按 `kb_type` 落目录：1_外部标准库 / 2_内部正负样本库 / 3_措辞表达库 / 4_产品描述库 / 9_未归类 |
| 层目录 | `form=entry → L2-concepts`，`form=revision_pair → L1-facts` |
| 正文 | 规则原文 / 命中表达 / 依据 / 处理方式照抄新库字段，**不做摘要式改写** |
| 缺省字段 | `half_life_days=180`、`owner=刘华丽`、`data_level=L2`、`valid_until = created_at + 180天` —— 新库没有这些字段，是派生缺省，**不是从库里读到的** |
| 不改的东西 | 生成过程只读新库；工作台侧是只读镜像（写入会被 `KbReadOnlyError` 拦） |

## 边界（用这条视图时必须知道）

1. 新库 l3 全部是 `provisional`，l4 canonical 仍为空 —— **派生视图不改变这个状态**，它一样没过正式验收。
2. 视图只覆盖「已归纳成规则」的那部分；l2 的 9261 条原始单元、l0 的 1256 份素材**没有**逐条搬进来。
3. 视图与分层库可能不同步：改了新库要重跑生成器 + 重装，见 `kb/.work/gen-host-library.py --out`。
4. `not_proves` / `forbidden` 每一条都写了 —— 别再外推（未命中 ≠ 合规）。
