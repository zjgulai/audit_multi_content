# 自验 A：BLOCK 链路（run_id 20260923-1500）

## 送审内容（取自真实素材，非自编）

- 来源：`#广告文案明细/recvuJYdObxeKs/Primary Text`（表 `广告文案明细`，字段 `Primary Text`）
- 原文：`Gran oferta para miembros Momcozy | Recupera tu libertad. Extrae más leche fácilmente mientras trabajas. ¡Compra el tuyo hoy!`

## 完整链路输出（按第四节 BLOCK 模板原文）

```
【审查结论：BLOCK】共发现 1 处必须修改。

1.【功效宣称-催乳与通乳宣称】全文，H02:más leche
  原因：P0 规则命中：BLOCK；命中片段逐字来自来源记录字段 命中片段
  依据：《措辞表达库 v0（试用版，未发布）》第 W-1.18 条（链接：kb/l3/candidates/rules.jsonl#W-1.18）
  锚点：#广告文案明细/recvuJYdObxeKs/命中片段｜source_sha256：8f752d56731a13da07d5cb64853a52d4eb16b8828b5ee0c71576c13eefe910b5
  建议：「easier letdown」→ 删除/替换为：删除 more milk/增产催奶/催产素/长期奶量/裸奶阵排空承诺；合规替代为放松叙事+限定语，如 relaxation supports your natural let-down, which may help your flow（因为放松，自然奶阵可能更顺畅），只描述自然生理过程、不承诺产品带来结果；faster let-down/提高排空效率在拿到W1自身对照数据前禁用 ▸ 静音表述改客观参数（as low as 48 dB），避免 whisper/silent/ultra-quiet 绝对化；「increase milk suppl

请修改后重新提交。

---
检索轨迹摘要：P0 1 命中（19.657 ms）｜规则层 1 命中｜单元层 BM25 最高 97.9367（门限 8.0）｜向量补召 未启用｜无法满足引用契约 0 条
完整清单：kb/l7/reports/20260923-1500-a.review.md
```

## 4 个判据

| # | 判据 | 结果 | 证据 |
|---|---|---|---|
| 1 | 依据可引用（库名 + 版本 + 条款号 + 链接齐全） | ✅ | 条款号 ['W-1.18']｜库名 ['措辞表达库']｜链接行：`kb/l3/candidates/rules.jsonl#W-1.18` |
| 2 | 逐字摘录能回原文核对 | ✅ | 按**引用里的锚点**逐个解析到 kb/l0/records 的字段再比对：1 条摘录，逐字命中 1 条（NFKC + 空白折叠后比对） |
| 3 | 无命中会拒答 | ✅（由自验 B 验证） | 见 `kb/l7/selftest_b_refusal.md` |
| 4 | P0 命中 < 1 秒 | ✅ | 5 次实测：min 13.2 ms / max 19.5 ms（kb/l5/matcher.py 整进程含加载） |

## 引用三要素（逐条）

| 条款号 | 锚点 | source_sha256 | 回原文核对（字段 / 逐字） |
|---|---|---|---|
| W-1.18 | `#广告文案明细/recvuJYdObxeKs/命中片段` | `8f752d56731a13da07d5cb64853a52d4eb16b8828b5ee0c71576c13eefe910b5` | `kb/l0/records/广告文案风控库__广告文案明细/recvuJYdObxeKs.json` 字段 `命中片段` → ✅ 逐字一致 |

退出码：0（0 = 有结论）｜报告：`kb/l7/reports/20260923-1500-a.review.md`

## 附：另两种结论态的模板符合性（同一模板、真实捕获）

### PASS（命中允许表述「安全词」→ 覆盖成立 → 无问题）

送审：`具备 9 档可调吸力（suction levels），操作简单，方便携带。`

```
【审查结论：PASS】未发现已知底线风险，可转交 @sign-off 责任人（未配置） 进行 sign-off

---
检索轨迹摘要：P0 0 命中（16.304 ms）｜规则层 1 命中｜单元层 BM25 最高 10.428（门限 8.0）｜向量补召 未启用｜无法满足引用契约 0 条
完整清单：kb/l7/reports/20260923-1500-pass.review.md
```

### REVIEW（1 处需人工确认 → 逐条模板）

送审：`Comfortable hands-free pumping with adjustable suction levels. Consult your lactation consultant if you have concerns.`

```
【审查结论：REVIEW】共发现 1 处需人工确认。

1.【背书与资质-专业头衔与合作】全文，lactation consultant, ibclc, 母乳指导, 泌乳顾问, expert-tu
  原因：规则层逐字命中「lactation consultant」；p_level=P3 risk_level=待复核 authority=inferred（来源表 品线内容边界规则库）
  依据：《措辞表达库 v0（试用版，未发布）》第 W-1.48 条（链接：kb/l3/candidates/rules.jsonl#W-1.48）
  锚点：#品线内容边界规则库/recvuJP2jyHizA/检测关键词｜source_sha256：93e0189171f63e25214f8fe16020c7f6fdb1c150cc76e2cba9674f3e2b266ff5

建议转 @复核责任人（未配置） 复核。

---
检索轨迹摘要：P0 0 命中（20.955 ms）｜规则层 2 命中｜单元层 BM25 最高 16.7046（门限 8.0）｜向量补召 未启用｜无法满足引用契约 0 条
完整清单：kb/l7/reports/20260923-1500-review.review.md
```

### BLOCK（≥3 处 → 只出分类汇总 + 报告链接）

送审：`Experience pain-free pumping with our hospital grade pump. Get more milk in less time.`

```
【审查结论：BLOCK】共发现 5 处必须修改。

· 功效宣称类问题：3 个
· 背书与资质类问题：2 个

→ 查看完整问题清单与修改建议：kb/l7/reports/20260923-1500-block3.review.md

请修改后重新提交。

---
检索轨迹摘要：P0 2 命中（17.556 ms）｜规则层 12 命中｜单元层 BM25 最高 17.9593（门限 8.0）｜向量补召 未启用｜无法满足引用契约 0 条
完整清单：kb/l7/reports/20260923-1500-block3.review.md
```

三种结论态 + 两种分流（逐条 / 汇总）都已按 `kb/l7/output_template.md` 原文格式跑过。

