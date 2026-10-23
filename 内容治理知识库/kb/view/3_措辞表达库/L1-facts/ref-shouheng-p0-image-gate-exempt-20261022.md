---
asks:
  - 群里只收到「本轮图片审查证据未通过」时，先查哪两处、为什么不是先查 OCR？
  - P0 命中与图单闸门为什么会恒撞车，PRD §6.3 的那句话落在这条链路的哪一步？
  - 为什么放行 P0 的单子不需要五类视觉核对与 skill 全流程七节？风险的哪个方向不受影响？
  - imageEvidenceFailure 里那一行早退，为什么连模型侧的结果也不再看？
  - 怎么证明这不是「把图单闸门整个关掉」？反向对照在哪一条？
  - 跳过闸门时为什么必须打日志，判据在哪一行？
  - 这条与 2026-10-21/22 陆续加的 P0 直达卡、图单视觉核对各自的关系是什么？
collection: 3_措辞表达库
corroborated_by:
  - PMO/守衡-P0图单被闸门藏掉-20261022.md（留底件：回话逐字、合并记录读数、根因两栏、修法表、自证读数、部署边界）
  - PMO/shouheng-state/merged-reports/merged-2026-10-22T07_30_42.698Z-1792654242699.json（同一单的合并记录：state=BLOCK、库侧 1 条、模型侧 2 条）
  - PMO/logs/ws_daemon.log 两道闸门的原始日志与 341 字回复行
  - tools/test_agent.mjs N4d2（行为级正向 + 两条反向对照）
  - PRD §6.3「命中即停止后续审查」与 kb/l5/p0_fastpath.py 的 out["state"]="BLOCK"
created_at: 2026-10-22
data_level: L2
evidence_group: rule
evidence_level: L2
half_life_days: 180
id: ref-shouheng-p0-image-gate-exempt-20261022
kb_class: []
kind: fact
not_proves: 不能证明 P0 的命中精度 —— 这一单 E-2.124（绝对化用语）命中的是图上「100%」，它是否真构成绝对化宣称属词表/模式表精度问题，本条只改「闸门不该藏掉已有结论」。不能证明「图 + @守衡、无正文」这种送审的体验已够好（现在会出 BLOCK 卡，但卡片是否自解释另议）。不能证明以后的单子都能拿到 BLOCK（只在 P0 命中时生效，非 P0 的图单仍要求视觉核对与 skill 全流程）。不能替代 3_措辞表达库 的任何条款。
owner: 刘华丽
pii:
  detected: false
provenance:
  anchor: PMO/守衡-P0图单被闸门藏掉-20261022.md#三、根因：两个各自都对的部件，合起来必然撞车（§2.4.5）
  confidence: 确定
sensitivity_level: L2
source:
  captured_at: 2026-10-22
  fingerprint: 535c7fb0dc00858e
  kind: file
  ref: /Users/lute/project/audit_multi_content/PMO/守衡-P0图单被闸门藏掉-20261022.md
summary: 群里收到一条「本轮图片审查证据未通过：本轮没有可核对的知识库引擎 JSON……请重新发送原图」的拒答（2026-10-22 15:30，om_x100b62aff6a2c22ccfd45eeca787bff：一张 momcozy 产品图 + @守衡，正文为空）。而同一时刻盘上已经有结论：库侧 P0 快路命中 V02／E-2.124（图上「100%」）、模型侧 2 条 REVIEW，双轨合并态 BLOCK，P0 报告与 p0DirectReply 都已备好。真因是接缝：P0 命中按 PRD §6.3「命中即停止后续审查」不起模型侧、不跑 L4→L7 与评审链；而 imageEvidenceFailure 要 res.engine（引擎 JSON）、checkVisualChecklist 与 checkImageSkillWorkflow 要判定主体写的五类视觉核对与 skill 全流程七节 —— 这些都是被 PRD 停掉的那段流程才会产出的东西 ⇒ 两道闸门必然红 ⇒ conclusion 被压成 NEEDS_INPUT、forcedReply 拼成拒答，且 forcedReply 在 handleMessage 里先于 p0DirectReply ⇒ 已确定的 BLOCK 被自己的闸门藏掉。修法两处：① imageEvidenceFailure 里 result.p0_fastpath 是对象就直接 return null（P0 读数在就不存在「没有引擎 JSON」；也顺带不看模型侧，命中即停它本就不该跑）；② runSubmissionGate 的图单闸门块加 p0GateExempt，条件改成 imageCount>0 && chainRan && !p0GateExempt，跳过时打一行日志说明为什么（不许静默跳过）。判据：tools/test_agent.mjs 新增 N4d2（行为级：P0+图 ⇒ 落表 BLOCK、forcedReply=null、imageReviewIncomplete=false、verdict53 有 BLOCK 行、p0DirectReply 是 BLOCK 卡），并带两条反向对照：摘掉 p0_fastpath 后同一张图仍必须被拒（否则等于把闸门整个关掉），以及 imageCount=0 的文字单不受这条闸门管辖。自证读数：test_agent 305/0（含 N4d2）、verify_cards 350/0、scene 29/29、merged_report 13/0、verify_shouheng_ops 全过（重启后 PID 2867、wsConnected=true）。
tier: L1
title: "[参考实现] P0 命中的图单不许被图单闸门藏掉（2026-10-22）：命中即停的流程，不许向它要后续审查的产物"
topic: 知识
valid_until: 2027-04-20
---

# P0 命中的图单不许被图单闸门藏掉（2026-10-22）

## 现象（可复核的三个读数）

- 触发：`om_x100b62aff6a2c22ccfd45eeca787bff`（2026-10-22 15:30:15 北京，群 `oc_49a7cfb2861cffa4365ca8491f398d32`），
  `type=post`，**正文为空**，只有一张 2436×1110 的 momcozy 产品拼图 ＋ `@守衡`。
- 回话：341 字，逐字开头是「本轮图片审查证据未通过：本轮没有可核对的知识库引擎 JSON；图片审查状态未验证。暂不出 PASS / REVIEW / BLOCK…」。
- 同一时刻盘上的结论：合并记录 `merged-2026-10-22T07_30_42.698Z-1792654242699.json` —
  `state=BLOCK`、库侧 P0 1 条（`V02`／`E-2.124`，命中「100%」）、模型侧 2 条 `REVIEW`、`total=3`。

## 根因（接缝，不是单点）

| 部件 | 它是对的 | 它要什么 | P0 这一路为什么必然没有 |
|---|---|---|---|
| `imageEvidenceFailure()` | 防「没读过库就说合规」 | `res.engine` 与其中 `image_skill_gate` | P0 快路不走引擎，只回 `p0_fastpath` / `p0_findings` / `rendered` |
| `checkVisualChecklist()` ＋ `checkImageSkillWorkflow()` | 防「加载了 skill 但没做视觉核对」 | 判定主体写的五类视觉核对与七节全流程 | 命中即停（PRD §6.3），模型侧没跑 |

两道闸门任一红 ⇒ `conclusion='NEEDS_INPUT'` ＋ `visualGateRefusal` ⇒ `forcedReply`；
而 `handleMessage` 里 `g.forcedReply` 先于 `g.p0DirectReply` ⇒ 群里发拒答，BLOCK 卡不发。

## 修法（两处代码）

```js
// ① imageEvidenceFailure
if (result?.p0_fastpath && typeof result.p0_fastpath === 'object') return null;
// ② runSubmissionGate 的图单闸门块
const p0GateExempt = res?.p0_fastpath && typeof res.p0_fastpath === 'object';
if ((inbound?.imageCount ?? 0) > 0 && chainRan && !p0GateExempt) { … }
```

跳过时打一行：`🖼 P0 确定性命中 ⇒ 视觉核对 / skill 全流程闸门**不适用**（PRD §6.3 …）` —— 不许静默跳过。

## 为什么这个方向是安全的

P0 快路只出 `BLOCK`（`kb/l5/p0_fastpath.py` 里 `out["state"] = "BLOCK"`）。
两道闸门防的是**放行**；P0 只会更保守 ⇒ 少要这两样，风险方向不变。

## 判据（`node tools/test_agent.mjs` 的 `N4d2`）

- 正向：P0＋图 ⇒ 落表 `BLOCK`、`forcedReply=null`、`imageReviewIncomplete=false`、
  `verdict53` 有 BLOCK 行、`p0DirectReply` 是那张 BLOCK 卡。
- 反向对照①：摘掉 `p0_fastpath`，同一张图 ⇒ 仍必须 `NEEDS_INPUT` ＋ 拒答话术（证明闸门没被整体关掉）。
- 反向对照②：`imageCount=0` 的文字单不受这条闸门管辖。
- 另两条：`imageEvidenceFailure(P0, 1, {ok:true})` 与 `{ok:false}` 都必须是 `null`
  （命中即停 ⇒ 模型侧本就不该跑，不许把它当缺证据）。

## 自证读数

`test_agent` 305/0 ｜ `verify_cards` 350/0 ｜ `scene` 29/29 ｜ `merged_report` 13/0 ｜
`verify_shouheng_ops` 全过（重启后 PID 2867、`wsConnected=true`）。

## 部署与留痕

2026-10-22 15:56 经 `tools/restart_shouheng.sh --yes` 重启生效（PID 31004 → 2867，启动横幅计数 287，台账已写理由）；
重启后 `verify_shouheng_ops` 全过。修复记录：`PMO/已修问题.jsonl` 的 `FIX-060`。
