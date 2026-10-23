---
id: ref-shouheng-feishu-link-split-20261022
title: "[参考实现] 飞书链接读不了（2026-10-22）：只读公网页的读取器把**任何**飞书链接都判成「非公网地址」；现在按域名分流，附件按红线不取"
collection: 3_措辞表达库
tier: L1
topic: 知识
kind: fact
kb_class: []
owner: 刘华丽
created_at: 2026-10-22
valid_until: 2027-04-20
half_life_days: 180
evidence_level: L2
data_level: L2
sensitivity_level: L2
evidence_group: rule
summary: 有人发给守衡一条飞书云空间链接（/file/…，一份 pptx brief），守衡回「链接内容未能读取（域名解析到非公网地址，已阻止读取）」。真因不是那条链接：链接工作流只有一条读法 —— link_reader.mjs 读匿名公网页面；飞书网页一律 302 到 accounts.feishu.cn（登录页），而本机 DNS 把该域名解析到私网地址 10.0.0.100，SSRF 守卫于是报「域名解析到非公网地址」。实测 /docx/、/base/、/file/ 三种飞书链接全部死在同一句 ⇒ 任何飞书链接都读不了，且报错把原因指到了 DNS。修法：新增 tools/agent/feishu_link.mjs，readLink() 是唯一分流点 —— 飞书域名按路径取只读正文（docx raw_content / sheets 值 / bitable 记录 / wiki get_node 再按 obj_type 分派），其余仍走公网页读取器；prepareLinkReview 默认 reader 换成分流器，并把 reader 抛出的分形态话术（红线不取 / 飞书没接口 / 权限或不存在）原样发出。云空间附件 /file/ 在飞书 OpenAPI 里没有原文读取接口、download 是唯一通道 ⇒ 按红线不下载不探测，回复改成「这是附件《…pptx》，按红线不取」＋替代路径。判据：feishu_link.test.mjs 10 项（含 lookalike 域名、附件零网络波次、两条路不串）、review_workflow.test.mjs 16 项（含话术原样透传、附件失败全链不发生）、test_agent 304 项（含接线）。三条反向对照各自实红过。
asks:
  - 为什么守衡读不了飞书链接，它报的「域名解析到非公网地址」到底指什么？
  - 这条报错为什么不是那条链接的问题，而是所有飞书链接的问题？
  - 飞书文档（docx / 表格 / 多维表格 / 知识库节点）现在是怎么被读进审核链的，分流点在哪一处？
  - 云空间附件（pptx / pdf / xlsx）为什么永远读不了，是权限问题还是策略问题？
  - 改完之后怎么证「飞书链接真的能读」「附件一次都没被下载」，反向对照是什么？
  - 哪些形态还是未测（wiki 实读、旧版 /docs/），怎么判断，不许说成通过？
  - 线上复活这条修复需要满足什么条件（重启闸门怎么走）？
not_proves: 不能证明任何一条具体内容能不能发 —— 它讲的是链接正文怎么进链，不是审查结论；不能证明 wiki 节点的正文读取在线上跑通过（两个样本一个 131005 not found、一个 131006 permission denied ⇒ 未测）；不能证明旧版 /docs/ 的 doc/v2 读取路径可用（无样本）；不能证明附件能被审核 —— 红线是策略，永远不取，本条只保证话说清楚；不能证明飞书文档读到的正文足以支撑一次审核；不能替代 3_措辞表达库 的任何条款；不能证明线上已生效（要重启守衡才加载新代码，重启必须走 AGENTS.md §2.7 闸门）。
forbidden: 不许据本条把「读了正文」说成「审过了」；不许把附件按红线不取说成「没权限」「能力还没做」或拿 DNS 当原因；不许在没重启的情况下声称线上已生效；不许把 wiki/旧版 docs 的未测说成通过；不许用本条去放宽 AGENTS.md §2.6 红线（附件仍不下载、不探测）。
corroborated_by:
  - PMO/守衡-飞书链接读不了-20261022.md（留底件：逐字回复、三层根因、修法与判据、现场实跑读数、未测项）
  - tools/agent/feishu_link.mjs ＋ tools/agent/feishu_link.test.mjs（分流判据是纯函数；附件形态零网络波次；lookalike 域名不许认成飞书）
  - tools/agent/review_gate.mjs（prepareLinkReview 默认 reader = readLink；error.shouhengReply 原样透传）＋ tools/test_agent.mjs（接线断言：两处默认值必须是 readLink）
source:
  kind: file
  ref: /Users/lute/project/audit_multi_content/PMO/守衡-飞书链接读不了-20261022.md
  fingerprint: f3c20db364dacbaf
  captured_at: 2026-10-22
provenance:
  anchor: PMO/守衡-飞书链接读不了-20261022.md#一、现象（逐字，生产）
  confidence: 确定
pii:
  detected: false
---

# 飞书链接读不了（2026-10-22）—— 不是那条链接的问题，是**所有飞书链接**都读不了

## 现象（逐字，生产）

私聊 `oc_7775e2dacb6f2ebc9789cd6e681de5f7`，消息 `om_x100b62aee250a0accfe63d9f7ac7d50`（正文只有一条链接）：

```
https://momcozy-in.feishu.cn/file/IWbobAGHAoDcycxRFWNcBYd1nY6
```

守衡回（`PMO/logs/ws_outbound.jsonl` 逐字）：

```
链接内容未能读取（域名解析到非公网地址，已阻止读取），本次无法形成审核结论；
请提供可公开访问的页面或直接粘贴正文。未读取到的内容不会判为通过。
```

## 真因（三层，逐条可核）

1. 这条链接经 `drive/v1/metas/batch_query`（只读元数据）核实是**云空间附件**：`doc_type=file`、
   `title=【FINAL】Momcozy Wellness 1 红人Brief_职场妈妈版.pptx`。
2. 链接工作流只有一条读法：`tools/agent/link_reader.mjs` 读**匿名公网页面**。飞书网页一律 302 到
   `accounts.feishu.cn`（登录页），而本机 DNS 把该域名解析到私网地址 `10.0.0.100` ⇒ SSRF 守卫拦下
   ⇒ 报「域名解析到非公网地址」。**报错指向的是跳转后的登录域名，不是用户贴的那条链接。**
3. 同一条路复现 `/docx/`、`/base/`、`/file/` 三种飞书链接，**全部**死在同一句 ⇒ 任何飞书链接都读不了；
   就算 DNS 修好也读不到 —— 登录墙在那儿，匿名抓取本来就没有正文。

## 修法（分流点只有一个）

- 新增 `tools/agent/feishu_link.mjs`：`readLink()` 是**唯一**分流点。飞书域名按路径取只读正文
  （`/docx/`→`raw_content`、`/sheets/`→工作表值、`/base/`→记录、`/wiki/`→`get_node` 再按 `obj_type` 分派）；
  非飞书仍走 `readPublicPage`。分流判据 `classifyFeishuLink()` 是纯函数（可离线反向对照）。
- `review_gate.prepareLinkReview` 默认 reader 换成 `readLink`；失败时若 reader 抛了 `shouhengReply`
  （`FeishuLinkError`）就**原样发出**，不再改写成一句泛泛的「请提供可公开访问的页面」。
- `agent.mjs` 两处默认 `linkReader` 同步改成 `reviewGate.readLink`。
- 云空间附件 `/file/`（pptx / pdf / xlsx…）在飞书 OpenAPI 里没有原文读取接口，`download` 是唯一内容通道
  ⇒ 按 §2.6 红线**不下载、不探测**，回复「这是附件《…pptx》，按红线不取」＋替代路径（贴正文 / 转成飞书文档 / 发 docx 链接）。
  幻灯片、思维笔记、旧版 `/docs/` 同理说清「飞书没有该形态的正文读取接口」；接不通（权限/不存在）时把飞书回的 code 说出来。

## 判据与反向对照（三条都实红过）

- `tools/agent/feishu_link.test.mjs`（10 项）：五种形态认出 token；`feishu.cn.evil.com` / `notfeishu.cn`
  这类 lookalike **不许**认成飞书；附件形态**一次网络调用都没有**；分形态话术必须不同；两条路不许串。
- `tools/agent/review_workflow.test.mjs`（16 项，新增 4）：话术原样透传；附件失败 ⇒ 链/模型侧/落表全不发生；
  docx 读到了正文真进链输入；附件与「权限不足」话术必须不同。
- `tools/test_agent.mjs`（304 项，新增 1）：接线 —— 两处默认值必须是 `readLink`，`review_gate` 必须 re-export 同一个分流器。
- 反向对照实红：① 去掉 `error?.shouhengReply ??` ⇒ 透传用例红；② 把域名判据放宽成「含 feishu」⇒ lookalike 用例红；
  ③ 把一处默认值改回 `readPublicPage` ⇒ 接线用例红。三处各自恢复后重新全绿。

## 读数（现场实跑，2026-10-22）

| 样本 | 结果 |
|---|---|
| docx | ✅ 1048 字 |
| sheet | ✅ 732 字 |
| base | ✅ 30000 字（触顶；正文**开头**就写「没读全：共 4 张表只读前 3 张、1 张超 100 条只读前 100 条」） |
| wiki ×2 | ❌ 131005 not found / 131006 permission denied ⇒ **未测**，不是通过 |
| file（pptx） | ❌ 按红线不取（话术含标题与替代路径） |

## 边界

见 `not_proves`：wiki 实读与旧版 `/docs/` 未测；附件永远不取（策略）；线上要重启才生效。
