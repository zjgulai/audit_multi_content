---
id: ref-shouheng-image-same-as-above-scene-fault-reply-20261022
title: "[规则执行] 视觉核对里的「同上」按上一条理由解析；画面读数没读到不许给三态结论、也不许让人重发原图"
collection: 3_措辞表达库
tier: L1
topic: 守衡图片审查/视觉核对判据与图单回话口径
kind: fact
summary: 真实私聊链的视觉核对表在「场景关系」一格写「同上」，旧判据按 2 字长度判成没给原因，整份合格报告被压成 NEEDS_INPUT；同一单的画面读数是端点 HTTP 402 余额不足（我们一眼没看到图），回话却让对方「请重新发送原图」，对方重发数次每次都同一句。修复：判据接受「同上」指代（只认紧邻上一条且结论相同），并新增「画面读数没读到 ⇒ 本单不出三态结论」这道单向闸；群里的那句话改成纯函数生成，写清没测完≠没问题、卡点在谁身上、现在重发有没有用。
owner: 刘华丽
evidence_level: L2
data_level: L2
sensitivity_level: L2
half_life_days: 180
created_at: 2026-10-22
valid_until: 2027-04-20
asks:
  - 图单回话说「视觉核对的结论没写清：场景关系（判未测但没给原因）」时，到底是谁的问题？
  - 视觉核对表里写「同上」算不算给了原因？判据怎么保证不被改松？
  - 画面读数没读到（画面模型 HTTP 402）时，图单应该给三态结论吗？
  - 守衡让人「重新发送原图」这句话什么时候是对的、什么时候是错的？
  - 怎么复现这次误拒与话术修复（哪条命令、先红后绿怎么证）？
not_proves: 不证明任何一张具体图片安全或合规；不证明模型视觉判断本身正确；不证明画面层端点已恢复（恰恰相反，本轮读数就是 402 余额不足）；不证明线上已生效（重启需按 AGENTS.md §2.7 取得同意）；不证明「同上」可以跨结论继承（跨结论一律判红）。
forbidden: 不得把「同上」当成无条件的理由继承（只认紧邻上一条且结论相同、且那条理由本身可用）；不得拿 OCR 文字冒充画面事实；不得在画面读数没读到时给出画面类三态结论；不得把端点故障说成对方素材的问题，更不得让人重发同一张图来「解决」我们这一侧的故障；不得把判据原话（判未测但没给原因、逐面板等）写进群里。
kb_class: []
evidence_group: coordinate
source:
  kind: file
  ref: /Users/lute/project/audit_multi_content/PMO/守衡-图单同上指代与请重发原图-20261022.md
  fingerprint: c2fe91b02ca4039f
  captured_at: 2026-10-22
provenance:
  anchor: PMO/守衡-图单同上指代与请重发原图-20261022.md#现象（Owner 当场把回话截图甩回来）
  confidence: 确定
pii:
  detected: false
  masked: false
  strategy: 只记录判据规则、回话口径与验收读数，不写图片里的人物与文字内容。
corroborated_by:
  - /Users/lute/project/audit_multi_content/tools/agent/visual_checklist.mjs
  - /Users/lute/project/audit_multi_content/tools/agent/agent.mjs
  - /Users/lute/project/audit_multi_content/tools/agent/scene.test.mjs
  - /Users/lute/project/audit_multi_content/tools/test_agent.mjs
  - /Users/lute/project/audit_multi_content/PMO/守衡-图单同上指代与请重发原图-20261022.md
---

## 故障事实（2026-10-22 19:36，生产实测）

私聊图片单（`om_x100b62ab067718a4b07f19a08c44374`）完整链跑成（166655 ms），群里收到：

> 这张图片的完整审查流程没有完成，暂不出 PASS / REVIEW / BLOCK 结论。视觉核对的结论没写清：场景关系（判"未测"但没给原因）。请重新发送原图，待图片安全审查 skill 完整执行（含逐面板视觉核对、规则与事实核查）后再给结论。

同一形状当天出现 4 次。

## 根因一：真实报告写「同上」，判据当成「没给原因」

那次链的原始回答（`kb/.work/last_chain_answer.txt`，base `20261022-193423`）第七节是合格表格：

```
| 产品状态 | **未测** | 画面层未测；OCR 里无产品名/产品物件可推 |
| 场景关系 | **未测** | 同上 |
```

「同上」指的就是紧挨着上一条那句原因。旧 `basisOf()` 把该格原样当依据 ⇒ 2 字 < 判据下限 4 字 ⇒
判「没给原因」⇒ 整份报告被判成流程没完成。这是同一类接缝（判据输入范围 ≠ 生产输出形状）
在 FIX-062 之后的第五次：前几次是**别名**没覆盖，这次是**指代**没覆盖。

修复（`tools/agent/visual_checklist.mjs` 的 `resolveAnaphora()`）：只接受一种继承 ——
紧邻的上一条、**结论相同**、且那条理由本身可用（非空、不是另一句「同上」、≥4 字）。
三条缺一条就原样留着照旧判红。

## 根因二：卡点在我们这一侧，回话却让对方重发原图

同一单的画面读数是「**没读到**」：`画面模型 HTTP 402：{"message":"Insufficient Balance"}` ——
我们一眼都没看到那张图，画面类事实只能是「未测」。而回话让人重发原图，对方照做，每次同一句。
这句话同时犯了三件事：判据原话进群、把我们的端点故障说成对方素材的问题、没写清「没测完 ≠ 没问题」。

修复（`tools/agent/agent.mjs`）：

- `sceneFaultsOf(inbound)` —— 画面层三态分开（读到 / 读了没读到 / 这一单没跑；`skipped` 不算缺口）；
- `humanizeSceneError()` —— 端点报错压成「HTTP 402 · 额度不足」，整段 JSON 不进群；
- `imageWithholdReply({ visualGate, imageWorkflowGate, sceneFaults })` —— 群里那句人话，
  纯函数、可直接喂样本；写清「没测完 ≠ 没问题 / 卡在哪 / 现在重发有没有用 / 不承诺自动重跑」；
- **新增单向闸**：画面读数没读到 ⇒ 这一单也不出三态结论（`NEEDS_INPUT`）。理由与 2026-10-21
  那条「图没解析出来 ⇒ 不收」同形：PRD §5.1 把图片输入写成 OCR ＋ 基础视觉两半，
  画面这半没跑成时「视觉分析」无从执行，而判定主体照样能交出一份五类全「未测」的格式齐全清单 ——
  结论看起来像「审过了」。`P0` 确定性命中照旧豁免（PRD §6.3）。

## 判据落在哪（执行点）

| 判据 | 位置 | 反向对照 |
|---|---|---|
| 「同上」必须继承上一条理由 | `resolveAnaphora()` ＋ `scene.test.mjs` **S5m** | 上一条删掉原因 ⇒ 红；跨结论写「同上」⇒ 红；五类只写「未测」⇒ 红 |
| 回话不许让人重发原图、不许带判据术语 | `imageWithholdReply()` ＋ `test_agent.mjs` N4d ⑤c | 断言正文不含「请重新发送原图」、不含 `判"未测"`/`4A`/`4B`；必须含「没测完 ≠ 没问题」 |
| 画面读数没读到 ⇒ 不出结论 | 图单闸门 ＋ N4d ⑤d | 同一份回答 + 画面读数正常 ⇒ 不许被这道闸拦（防恒红） |

## 验收读数

- `node test/_replay_visual_checklist.mjs`：**生产原文回放 4 组全过** —— ①真实回答 `ok=true`，
  `场景关系` 的 basis 逐字等于上一条那句原因；②抽掉上一条原因 ⇒ 红；③跨结论「同上」⇒ 红；
  ④五类只写「未测」⇒ 红。旧实现下这一格 basis 只有「同上」两字 ⇒ 红，与生产事故同句。
- `node tools/agent/scene.test.mjs`：**33/33**（新增 S5m）。
- `node tools/test_agent.mjs`：**307 / 308**；唯一红项是「画面层·真跑试纸」，
  真因 `Insufficient Balance (HTTP 402)` —— 环境问题，本修无关。
- `node tools/verify_cards.mjs`：**350/350**；新话术过 `lintCopy` 零命中。

## 复用要点（防重复修复）

1. **判据的验收样本必须是真实链的原始输出**（原文在 `kb/.work/last_chain_answer.txt`），
   不许用理想散文；写完必须**先红后绿**各跑一次。
2. **「同上」这类指代**要按「紧邻 + 同结论 + 上一条可用」解析；别的继承一律不认。
3. **分开「我们这侧没读到」与「对方素材有问题」**：读数缺口的回话不许出现让对方重发素材的动作。
4. **话术也要做成纯函数**：内联在闸门里的字符串，判据够不着，只能等人截图（§2.4.7）。
