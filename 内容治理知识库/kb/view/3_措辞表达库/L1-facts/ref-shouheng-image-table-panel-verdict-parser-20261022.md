---
id: ref-shouheng-image-table-panel-verdict-parser-20261022
title: "[规则执行] 图片审核表格的面板方位与结论格必须按实际输出形状解析"
collection: 3_措辞表达库
tier: L1
topic: 守衡图片审查/表格视觉核对
kind: fact
summary: 真实私聊报告以“上图/下图”复述睡姿，旧视觉解析器漏认方位导致已完成审查被误拒；表格结论还会被依据中的其他类别读数覆盖。规则与 S5l 反向样本记录如何避免同形问题重发。
owner: 刘华丽
evidence_level: L2
data_level: L2
sensitivity_level: L2
half_life_days: 180
created_at: 2026-10-22
valid_until: 2027-04-20
asks:
  - 图片报告已用“上图/下图”复述面板时，视觉核对器如何判定？
  - 表格结论格的依据提及其他类别时，如何避免串读？
  - 如何复现私聊图片审查误拒修复？
not_proves: 不证明模型视觉判断本身正确；不证明任意位置表述均可安全绑定面板；不证明后续任意图片的线上审核结果。
forbidden: 不得因为报告使用“上图/下图”而漏掉面板复述；不得扫描结论格后续依据来覆盖本行首个结论；不得将此解析修复当作图片内容事实正确性的证明。
kb_class: []
evidence_group: coordinate
source:
  kind: file
  ref: /Users/lute/project/audit_multi_content/PMO/守衡-图单表格睡姿明细误拒-20261022.md
  fingerprint: cb061eaea49ee87d
  captured_at: 2026-10-22
provenance:
  anchor: PMO/守衡-图单表格睡姿明细误拒-20261022.md#追加：18:13 重启后仍误拒的实际私聊
  confidence: 确定
pii:
  detected: false
  masked: false
  strategy: 只记录解析器规则、通用面板别名与验收判据，不写个人图片内容。
corroborated_by:
  - /Users/lute/project/audit_multi_content/tools/agent/visual_checklist.mjs
  - /Users/lute/project/audit_multi_content/tools/agent/scene.test.mjs
  - /Users/lute/project/audit_multi_content/tools/test_agent.mjs
  - /Users/lute/project/audit_multi_content/PMO/守衡-图单表格睡姿明细误拒-20261022.md
---

故障事实：完整私聊链的审核表逐面板写出“上图＝仰卧、下图＝仰卧”，视觉核对项也分别给出了结论与依据，但最终回复仍错误称流程未完成并要求重发原图。该链外发约耗时 7 分 26 秒；长连接与发消息均正常，错误发生在完整产物进入确定性视觉清单闸门时。

根因有两个接缝：第一，睡姿读数以“图 1 右下：仰卧”作为期望面板，而报告使用“上图/下图”措辞，面板方位别名没覆盖此方言，已写依据被当成遗漏；第二，表格结论格解析整格扫描，依据里引用另一项“场景关系＝有”可能盖过本行自己的首项“无”。于是成功生成的表格被误判为核对不完整。

执行规则落在 tools/agent/visual_checklist.mjs：上方轴别名包括“上图”，下方轴别名包括“下图”；表格结论仅取结论格首个分句。反向判据落在 tools/agent/scene.test.mjs 的 S5l：复现完整真实表格形状，断言上图/下图复述通过，同时睡眠位置结论仍为“无”，不被依据中的其他类别文字覆盖。实际链回答回放为 visualOk=true、sleepVerdict=无、workflowOk=true；scene.test.mjs 32/32，test_agent.mjs 308/308。

防止重复修复：只补提示词或只测理想散文不构成闭环。凡改视觉清单别名/表格解析，验收样本必须使用真实链的原始输出格式，并同时断言通过与结论不串项；有 FAIL 时先回放实际链回答经过同一个生产闸门，定位输出与解析器的接缝，再新增一个 FIX 根因条目，不得只把同一段说明反复写进技能。