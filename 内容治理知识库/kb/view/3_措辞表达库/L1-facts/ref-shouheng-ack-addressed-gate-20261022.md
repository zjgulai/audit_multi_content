---
id: ref-shouheng-ack-addressed-gate-20261022
title: "[参考实现] 回执前置必须先过「这条是不是在对我说话」（2026-10-22）：群里没 @ 守衡也回「⏳ 处理中…完成后会在此回复」，随后 not_mentioned 直接不回复"
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
summary: 回执前置（2026-10-20 为「先回一句再读素材」而加）原先只判 reviewGate.isSubmission（关键词/媒材），没有一道门问「这条消息是不是在对我说话」；而下游 §4 有独立规则「群聊里不 @ 不理（not_mentioned）」。两条各自都对，合起来＝先说「我在处理」、再不理你：10-22 10:21 群 oc_49a7… 消息 om_x100b62a37c9fc8b4dc0ba2a61cc3e7d（未 @ 守衡）收到一张 62 字「【⏳ 处理中…】完整审核正在运行，完成后会在此回复」，此后台账里再没有第二条 —— 承诺发出去、链一次都没起。修法：抽出唯一判据 addressedToMe()（私聊恒真；群里看 feishu.isBotMentioned），回执前置与 §4 共用这一份；赶在 readInboundContent（读图+OCR+画面读数，实测 5.8s、抖动 27.8s）之前用 bodyToText+resolveMentions 做早判，拿到正文后用权威读数覆盖；两者分歧时打一行读数（回执撤不回，至少让它在日志里看得见）。判据：test_agent 34e（没 @ ⇒ 0 张回执且 reason=not_mentioned）＋34f 反向对照（@ 了 ⇒ 恰好 1 张）。
asks:
  - 群里一条消息没 @ 守衡，为什么它还会先回一张「处理中」？
  - 回执前置与「不 @ 不理」这两条规则为什么会打架，判据现在收在哪一处？
  - 为什么「早判」不能直接复用 readInboundContent 的 mention 还原？
  - 改完之后怎么证「没 @ 就一张回执都不发」，反向对照是什么？
  - 这条能不能当成「群里所有消息都会被及时回执」的依据？
  - 线上复活这条修复需要满足什么条件（重启闸门怎么走）？
not_proves: 不能证明任何一条具体内容能不能发 —— 它讲的是回执的触发条件，不是审查结论；不能证明「群里没 @ 守衡的消息都会被处理」——恰恰相反，本条确认它们**不**会被处理，也不该发回执；不能证明回执文案本身合规（「完成后会在此回复」这句话的兑现由链的完成率决定，不由本条的判据保证）；不能证明早判与权威读数永远一致（两者用了同一份正文与同一个 isBotMentioned，仍可能因 bodyToText 与 readInboundContent 的正文差异而分歧，分歧只留读数、不自动补救）；不能替代 3_措辞表达库 的任何条款；不能证明线上已生效（要重启守衡才加载新代码，重启必须走 AGENTS.md §2.7 闸门）。
forbidden: 不许据本条把「群里没 @ 也回执」读成「守衡在群里对所有消息负责」；不许把「没 @ 不发回执」当成「没 @ 的消息不用看」（该规则一直是不 @ 不理）；不许据本条声称回执文案的兑现率有保证；不许把本条的判据（34e/34f）当成链跑通与否的证据；不许在没重启的情况下声称线上行为已改。
corroborated_by:
  - PMO/守衡-假回执-回执前置先过对我说话-20261022.md（留底件：逐字台账、根因、修法、部署与回读）
  - tools/test_agent.mjs（34e 没 @ ⇒ 0 张回执 + reason=not_mentioned；34f 反向对照：@ 了 ⇒ 恰好 1 张）
  - tools/agent/agent.mjs（addressedToMe() 单一判据；回执前置 if (gateEarly?.yes && addressedToMe())；§4 复用同一函数）
source:
  kind: file
  ref: /Users/lute/project/audit_multi_content/PMO/守衡-假回执-回执前置先过对我说话-20261022.md
  fingerprint: a8d517a70f30232d
  captured_at: 2026-10-22
provenance:
  anchor: PMO/守衡-假回执-回执前置先过对我说话-20261022.md#现象（逐字，生产）
  confidence: 确定
pii:
  detected: false
  masked: false
  strategy: 未检出自然人信息：正文只写群/消息 id、文件路径、判据名与读数；「Owner」为角色指称。
---

# 回执前置必须先过「这条是不是在对我说话」（2026-10-22）

## 现象（逐字，生产）

群 `oc_49a7cfb2861cffa4365ca8491f398d32`，消息 `om_x100b62a37c9fc8b4dc0ba2a61cc3e7d`
（正文「不应该出现历史审核意见作为依据」，@ 的是刘华丽、**没有 @ 守衡**）：

| 时刻 | 发生了什么 |
|---|---|
| 10:21:25 | 守衡回了一张 62 字卡：`【⏳ 处理中…】完整审核正在运行，完成后会在此回复；遇到故障会明确提示。` |
| 之后 | 同一个 chat 台账里**再没有第二条** |

`PMO/logs/ws_daemon.log` 逐行：

```
[agent] 🧭 回执前置：text —— 命中送审词：审、依据｜先回一句，再读素材
[+ 42.679s]    · 不回复（not_mentioned）
```

承诺发出去了、链一次都没起。

## 根因

「回执前置」（2026-10-20 为把回执从读素材之后提前到之前而加）判断发不发回执时只用
`reviewGate.isSubmission()` 一把尺子（正文关键词 / 媒材）；**没有一把尺子问「这条消息是不是在对我说话」**。
而下游 §4 有独立规则「群聊里不 @ 不理」（`not_mentioned` 直接 return）。
两条各自都对，合起来＝先说「我在处理」、再说「我不理你」。
这正是 AGENTS.md §2.4.2 的形状：一句对外说出去的话，**指不出哪一行在执行它**。

## 修法（一处判据，两处共用）

`tools/agent/agent.mjs`：

1. 新增 `addressedToMe()` —— 唯一判据：私聊恒真；群里看 `feishu.isBotMentioned()`。
   赶在 `readInboundContent`（读图 + OCR + 画面读数，实测 5.8s、抖动到 27.8s）之前，
   先用 `bodyToText` + `resolveMentions` 取一次「早判」；§3 拿到正文后用权威读数覆盖。
2. 回执前置加门：`if (gateEarly?.yes && addressedToMe())`。
3. §4 改调同一个函数（不再自己写一遍 `chatType==='group' && !botMentioned`）。
4. 早判与权威读数**分歧**时打一行读数 —— 回执撤不回，至少让它在日志里看得见。

## 判据与反向对照

- `test_agent` **34e**：群里没 @ 我、正文命中送审词 ⇒ **0 张回执**，且 `reason === 'not_mentioned'`。
- `test_agent` **34f**（反向对照）：群里 @ 了我、同一句 ⇒ **恰好 1 张** —— 否则这条只是在教它闭嘴。
- 把 `&& addressedToMe()` 拿掉 ⇒ 34e 当场红。

## 读数

`node tools/test_agent.mjs` **303 / 0**（既有 301 一条没改）；三例探针 3/3。

## 部署边界

改完要重启守衡才生效；重启走 `bash tools/restart_shouheng.sh`（先看不带 `--yes` 的读数，
同意后带 `--yes --why`）。本条修复已于 2026-10-22 10:52 经闸门重启生效（PID 85391 → 3352，
`restart-ledger` 记 `ok:true`）。

## 这条不能证明什么

见 `not_proves`：它只讲「回执在什么条件下发」，不保证回执的兑现率，也不改变「不 @ 不理」本身。
