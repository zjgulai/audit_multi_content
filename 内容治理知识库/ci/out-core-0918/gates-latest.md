# KB 闸门体检 ｜ 2026-10-04T09:29:30

库根：`/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理`

范围：`scope=core`（core=12 把 ｜ full=core+projection+envelope）

| 闸门 | 状态 | 退出码 | 红数 | 耗时 | 说明 |
|---|---|---|---|---|---|
| l0 | RED | 1 | 2 | 52.1s | L0 判定档：原始差异 − 预期 = 真差异 |
| l1 | PASS | 0 | 0 | 19.3s | L1 独立复算：OCR 缓存复用门槛逐条核 |
| l2 | PASS | 0 | 0 | 20.5s | L2 独立复算：unit_count 口径逐条点名 |
| l3 | PASS | 0 | 0 | 16.9s | L3 独立复算：证据可回指 L2 单元 |
| l4 | PASS | 0 | 0 | 15.9s | L4 独立复算：promotion_rule C1–C6 |
| l5 | PASS | 0 | 0 | 44.7s | L5 包装分类：实质 4 项 + 基线项登记 |
| l6 | PASS | 0 | 0 | 273.1s | L6 只读档：可用单元/向量/倒排/版本纪律 |
| l7 | PASS | 0 | 0 | 9.3s | L7 引用契约前置条件 |
| skills | PASS | 0 | - | 15.8s | 登记表自检：应装未装 / 副本不一致 |
| layers | PASS | 0 | - | 12.2s | layers.yaml 层契约表自检 |
| conformance | PASS | 0 | 0 | 12.1s | 四方对账：文本↔注册表↔层契约↔磁盘 |
| freshness | PASS | 0 | - | 96.3s | 供给链新鲜度（超期=去跑链路的理由，不是红灯） |

**退出码 1** ｜ 红：['l0'] ｜ 无法计算：无 ｜ 告警：无
