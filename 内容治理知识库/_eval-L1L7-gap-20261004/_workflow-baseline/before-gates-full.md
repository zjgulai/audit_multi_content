# KB 闸门体检 ｜ 2026-10-04T19:44:02

库根：`/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理`

范围：`scope=full`（core=12 把 ｜ full=core+projection+envelope）

| 闸门 | 状态 | 退出码 | 红数 | 耗时 | 说明 |
|---|---|---|---|---|---|
| l0 | RED | 1 | 2 | 26.7s | L0 判定档：原始差异 − 预期 = 真差异 |
| l1 | PASS | 0 | 0 | 6.1s | L1 独立复算：OCR 缓存复用门槛逐条核 |
| l2 | PASS | 0 | 0 | 6.7s | L2 独立复算：unit_count 口径逐条点名 |
| l3 | PASS | 0 | 0 | 6.8s | L3 独立复算：证据可回指 L2 单元 |
| l4 | PASS | 0 | 0 | 7.5s | L4 独立复算：promotion_rule C1–C6 |
| l5 | PASS | 0 | 0 | 18.2s | L5 包装分类：实质 4 项 + 基线项登记 |
| l6 | PASS | 0 | 0 | 85.0s | L6 只读档：可用单元/向量/倒排/版本纪律 |
| l7 | PASS | 0 | 0 | 3.9s | L7 引用契约前置条件 |
| skills | PASS | 0 | - | 4.8s | 登记表自检：应装未装 / 副本不一致 |
| layers | PASS | 0 | - | 4.0s | layers.yaml 层契约表自检 |
| conformance | PASS | 0 | 0 | 4.5s | 四方对账：文本↔注册表↔层契约↔磁盘 |
| freshness | PASS | 0 | - | 34.0s | 供给链新鲜度（超期=去跑链路的理由，不是红灯） |
| projection | RED | 1 | - | 4.6s | 投影对账：派生视图 kb/view ↔ 权威库漂移（R1–R6）—— 实测真坏 3/6 |
| envelope | RED | 1 | - | 6.1s | 信封闸门：python getsize vs 读端 statSync().size（活路径） |

**退出码 1** ｜ 红：['l0', 'projection', 'envelope'] ｜ 无法计算：无 ｜ 告警：无
