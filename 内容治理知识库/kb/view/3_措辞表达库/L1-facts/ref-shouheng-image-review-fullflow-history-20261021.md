---
id: ref-shouheng-image-review-fullflow-history-20261021
title: "[修复记录] 图片审核完整流程与历史审核分析/建议透传（2026-10-21）：skill 已加载 ≠ 流程完成，记录级相似 ≠ 本图精确命中，卡面不截断历史分析/建议"
collection: 3_措辞表达库
tier: L1
topic: 知识
kind: fact
evidence_level: L2
data_level: L2
sensitivity_level: L2
kb_class: []
evidence_group: coordinate
owner: 刘华丽
created_at: 2026-10-21
valid_until: 2027-01-19
half_life_days: 90
summary: 守衡图片审核的两项对外承诺与本地修复记录：A 图片审查必须真实加载「图片安全审查」skill 并逐图完成审核范围、视觉与 OCR、主张拆分、4A 规则符合性、4B 事实核查、图文一致性、五类视觉核对；skill 加载成功不等于流程完成，缺项一律 NEEDS_INPUT，最终回复不得从旧 REVIEW 回退。B 命中历史审核记录必须透传该记录完整的具体原因分析与非空建议，并标明记录级相似意见不能冒充本图精确命中；回复卡不得截断关键分析/建议，应折叠/扩展承载。在线复发证据为 2026-10-21 15:33 图消息 om_x100b62b2e23fb4bccf2e3d3545cda20 与 merged-2026-10-21T07_37_11.173Z-1792568231174.json：该单模型侧 0 条结果、回复只有一条记录级意见、reason/advice 由 89/51 字压成 45/26 字，完整历史分析未透传。本条不声称线上端到端已修复。
asks:
  - 图片审核为什么必须真实加载「图片安全审查」skill？加载成功算流程完成吗
  - 图片审核的完整流程包含哪几个阶段，缺一个阶段会怎样
  - 图片审查缺项时最终回复能不能继续用旧的 REVIEW，拒收状态怎么支配回复出口
  - 命中历史审核记录时，审查输出应该带哪些内容（原因分析、建议、来源记录、L0 链接）
  - 记录级相似意见能不能说成这张图的精确命中，精确命中需要什么证据
  - 回复卡可以截断历史分析或建议吗，应该怎么承载完整内容
  - 89 字原因和 51 字建议被压成 45/26 字，是哪一单、哪个文件、哪些字段的读数
  - 图片流程缺少完整阶段、模型侧 0 结果，这两件事在同一条在线记录里怎么核对
  - 这次修复改了哪些本地文件与 skill，判据在哪几行
  - 这条修复有没有做过线上端到端验证
not_proves: 不能证明图片审核已在线上端到端修复 —— 本条落库时没有新的飞书图片事件在新版本下走完整链，也没有重放该图；不能证明回复卡已经实现折叠/扩展承载完整历史分析（截至落库，卡面仍受 PRD 的 50/30 字上限，dual_track 无 history 渲染、无承载完整分析的折叠区）；不能证明在线 15:33 那单的最终回复为何仍回落到 REVIEW 的具体支路（只记录现象，未定位到某一行代码）；不能证明线上 L7 产物已印出「历史审核完整分析/历史源建议」两栏（15:35 的 .feishu.md 里查不到）；不能替代 PRD §5.3、PRD §5.8 的条款口径与法务意见；不能证明 339 张历史图之外的素材也适用；不能把本条当「流程已验收」的凭据。
forbidden: 不许据本条声称线上图片审核已修复或已验收；不许把「skill 加载成功」「coverage=complete」「--loaded-skill 自述」当成流程已完成的凭据；不许把 attribution=record_level 的相似召回写成「这张图命中」；不许在卡面用截断冒充完整历史分析（截断必须留「被截几字」的可回读痕迹，完整文本要能取到）；不许把记录级历史意见单独包装成已完成的本图审查结论；不许从 P0、历史送审链、双轨或模型原文回捞旧三态来填本单缺项的结论；不许改 PRD §5.3.3 的卡面上限来当作「已透传完整」；不许在没加图身份证据的情况下升级为本图精确命中。
corroborated_by:
  - tools/agent/visual_checklist.mjs::checkImageSkillWorkflow
  - tools/agent/agent.mjs::finalVerdict53ForTurn
  - PMO/守衡-图片审核skill完整执行修复-20261021.md#2026-10-21-后续：完整执行证据与最终回话一致性
  - PMO/守衡-图片历史分析建议透传-20261021.md#修复
provenance:
  anchor: PMO/守衡-图片审核skill完整执行修复-20261021.md（全文，含「完整流程交付闸门」与 14:xx 拒收态下游约束）＋ PMO/守衡-图片历史分析建议透传-20261021.md（L0–L7 数据链审计与修复段）＋ PMO/shouheng-state/merged-reports/merged-2026-10-21T07_37_11.173Z-1792568231174.json（items[0].truncated）＋ tools/agent/visual_checklist.mjs:260-286（6 阶段 + 婴儿睡眠权威来源）＋ tools/agent/agent.mjs:114-120（finalVerdict53ForTurn）＋ tools/agent/dual_track.mjs:3819-3820（ADVICE_MAX=30 / CARD_REASON_MAX=50）
  confidence: 确定
pii:
  detected: false
  masked: false
  strategy: 未检出自然人信息：正文只有消息 ID、报告文件名、代码行号、统计读数与角色指称「Owner」；在线消息 ID 与 merged 报告名是系统标识，不含姓名、工号、联系方式
source:
  kind: file
  ref: /Users/lute/project/audit_multi_content/PMO/守衡-图片审核skill完整执行修复-20261021.md
  fingerprint: ad2c7c477e0548de
  captured_at: 2026-10-21
---

# 图片审核完整流程与历史审核分析/建议透传 —— 修复记录（2026-10-21）

> 本条记两项对外承诺的执行契约与本地修复，并把「已做 / 未做 / 未在线验证」分开写。
> **不声称已有线上端到端修复验证**，理由与读数见第六节。

## 一、触发：一次在线复发（2026-10-21 15:33–15:37 北京时间）

- 入站图片消息 `om_x100b62b2e23fb4bccf2e3d3545cda20`（`message_type=image`，1 张图，p2p 群 `oc_7775e2dacb6f2ebc9789cd6e681de5f7`；事件时间 `2026-10-21T07:33:35.987Z`，见 `PMO/logs/ws_events.jsonl`）。
- 该单最终记录 `PMO/shouheng-state/merged-reports/merged-2026-10-21T07_37_11.173Z-1792568231174.json`。
- 记录读数（逐字可复算）：
  - `state=REVIEW`、`total=1`、`sides={"knowledge-base":1}`、`has_report=false`；`kb.issue_count=4`，但最终只呈现 1 条。
  - `model={"count":0,"ok":false,"error":"输出里没有 JSON 数组"}` —— **模型侧 0 条结果**。
  - 唯一一条 `F-01` 是记录级相似意见：`reason` 写着「相似历史审核意见（point·参考）… ⚠️ 非本单素材逐字命中 … 按记录级意见展示；不代表本图独立判定」，`description=null`。
  - `truncated={"reason":true,"reason_full_chars":89,"reason_shown_chars":45,"advice":true,"advice_full_chars":51,"advice_shown_chars":26}`（PRD 计数口径，不含标点）—— 即**知识库 finding 的 reason/advice 分别从 89/51 字压成 45/26 字**。
- 同一单的 L7 报告 `kb/l7/reports/rv-20261021-153523.feishu.md`：4 条库内问题（与 `kb.issue_count=4` 对齐），但历史侧只给「L0 原文（截断 160 字）」与「修改建议：源记录未给改法」，**没有**「历史审核完整分析 / 历史源建议」两栏。

该单同时暴露两点：① 回复里没有完整流程段落（审核范围、逐图视觉与 OCR、主张清单、4A、4B、图文一致性、五类视觉清单都不在），最终却仍以 `REVIEW` 发出；② 历史意见只以一条 45/26 字的截断摘要出现，完整 89 字分析与 51 字建议既没进卡，也没以折叠区承载。

## 二、A：图片审核必须完整执行（契约）

1. **真实加载**「图片安全审查」skill：走 DSH `skill` 工具，并能从本会话日志观测到成功的工具调用。
2. **逐图视觉与 OCR**：本轮原图逐张读，给出画面读数与 OCR 文字（标明「读数不是原图」）。
3. **主张拆分与核查清单**：把图内文字与画面主张拆成可逐条核对的清单。
4. **4A 规则符合性**：知识库链路读数（`kb_review_chain` / `review_run.sh` 只作 4A 的一步、只跑一次）。
5. **4B 事实核查**：逐项核事实与来源；婴儿睡眠类必须给 AAP / HealthyChildren 等权威来源。
6. **图文一致性与信息完整性**：文字与对应画面/箭头/比例逐项配对，判断支持、矛盾或暗示。
7. **五类视觉核对清单**（含「婴儿睡眠位置」）：结论只能是 `有` / `无` / `未测`，`未测` 必须写原因。

硬约束：

- **skill 加载成功不等于流程完成**。`--loaded-skill`、`decision_owner.mode=declared`、`coverage=complete` 都只是声明字段，不是执行凭据。
- 任一阶段缺项、原图不可读、本会话没有真实 skill 调用证据 ⇒ 本单 `NEEDS_INPUT`，**不产出** PASS / REVIEW / BLOCK。
- **拒收状态必须支配最终回复出口**：不得从 P0、历史送审链、双轨记录、模型原文里回捞旧 `REVIEW`；落表与回复必须一致。

## 三、B：命中历史审核记录时的透传（契约与现状）

契约：

1. 命中历史记录 ⇒ 透传该记录**完整的具体原因分析**与**非空建议**，并附来源记录 ID 与 L0 链接，明确标成「历史意见 / 非本素材原文」。
2. `attribution=record_level` 的相似意见只能写作「同题材参考」，**不得**描述成本图精确命中；精确命中须有图身份层证据（`trace.image_identity.checked`、pHash 与像素相关达阈值）。
3. **回复卡不得截断**关键分析/建议。PRD §5.3.3 的字数上限只约束卡面摘要格；完整分析/建议应搬进折叠区（折叠/扩展），不能靠截断丢弃 —— 口径同「搬是搬，砍是砍」。

现状（必须分开看）：

- **数据侧字段已在**：`kb/l7/skills/kb-content-review/scripts/review.py`（2208–2209 行）把 `history_analysis` / `history_advice` 写进 finding，来源是 `history_case_for_record()`（563–564 行读 L4 案例，空则回落 L0 的「具体原因/分析」「建议」字段）；`kb/l7/review-engine/core/with_kb_evidence.py`（863–866 行）搬运 `history_rule_text` / `history_advice` / `history_record_id`；`kb/l7/review-engine/core/report_memory.py`（167–173 行）有「历史审核完整分析 / 历史源建议」分栏渲染代码。
- **在线产物没印出来**：15:35 的 `.feishu.md` 报告里查不到那两栏，只有 L0 原文截断 160 字。⇒ 字段存在 ≠ 线上可读。
- **卡面侧未做**：`tools/agent/dual_track.mjs` 仍以 `CARD_REASON_MAX=50`（3820 行）与 `ADVICE_MAX=30`（3819 行）压卡面；该文件全文**没有任何 `history` 渲染**，也没有承载完整历史分析的折叠区。`tools/agent/merged_record.mjs`（100–107 行）只记录「被截了几字」（`reason_full_chars` / `reason_shown_chars` 等），**记录里没有 `reason_full` / `history_analysis` / `history_advice` 文本** —— 也就是说，看到「89 字被压成 45 字」之后，**取不回那 89 字**。
- ⇒ 「库里有、命中后看不到」的断点已从 L7 下移到**报告渲染与回复卡这一跳**；数据侧修好不等于用户看得到。

## 四、本地执行点与改动文件

- `tools/agent/visual_checklist.mjs::checkImageSkillWorkflow()`（260–286 行）：6 个阶段 + 婴儿睡眠权威来源，缺一即 `ok=false`，`missing` 逐项列出。
- `tools/agent/agent.mjs`（1769 行）：`checkImageSkillWorkflow` 与五类视觉清单一起接入结论闸；缺项强制 `NEEDS_INPUT`。
- `tools/agent/agent.mjs::finalVerdict53ForTurn()`（114–120 行）：`imageReviewIncomplete` 时**无条件返回 `null`**，阻断 P0 / 链回执 / 回复文本的一切旧三态回落。
- `tools/agent/tools.mjs::reviewTaskFor()`（2137 行）：图片任务前置要求真实调用 skill 工具并逐条执行完整流程，`review_run.sh` 只作 4A 的一步。
- 活动 skill `~/.dsh/skills/图片安全审查/SKILL.md`「完整流程交付闸门（2026-10-21）」（139 行起）：逐段交付、缺失即 `NEEDS_INPUT`、并要求发布层让拒收态支配最终回复。
- `agent-skills/飞书内容审核工作流/SKILL.md`：把同一套完整执行与 fail-closed 写入版本库规程。
- 卡面相关：`tools/agent/dual_track.mjs`（3819–3820 行上限、3894–3902 行截断元数据）；`tools/agent/merged_record.mjs`（100–107 行）。

## 五、验收读数（PMO 留底记录，本条未重跑）

- `node tools/test_agent.mjs`：295/295（含 N4c 任务顺序、N4d 旧 REVIEW 对抗、N4g 并发隔离与原图路径断言）。
- `node tools/agent/review_workflow.test.mjs`：12/12；`node tools/agent/scene.test.mjs`：24/24。
- `python3 tools/verify_skill.py --workflow-check --controls`：规程与两组反向对照各 5/5。
- `python3 -B -m pytest -q kb/l7/review-engine/tests`：103/103；`self_negative.py --selftest`：19/19；`kb/l8/image_skill_gate_selftest.py`：6/6。
- 以上是**留底记录的读数**，不是本条落库时重跑的结果。

## 六、边界

- **没有线上端到端验证**：修复后没有新的飞书图片事件在新版本下走完整链，也没有重放该图。下一次获授权的真实图片审核，需同时核到：DSH 会话里有真实 `图片安全审查` 工具调用、`trace.image_identity.checked=1`、完整流程六段与五类视觉清单齐全；缺项则只回 `NEEDS_INPUT`，且落表与回复一致。
- 在线 15:33 那单为何仍回落到 `REVIEW`（而不是 `NEEDS_INPUT`），本条只记录现象，未定位到具体支路。
- 「回复卡折叠/扩展承载完整历史分析」**尚未落地**：卡面仍受 50/30 字上限，且没有承载完整文本的折叠区。
- 不替代 PRD §5.3 / §5.8 的条款口径，也不替代法务意见。

## 七、复现

```bash
# 在线记录（原因/建议被截几字，逐字可复算）
python3 - <<'PY'
import json
p='PMO/shouheng-state/merged-reports/merged-2026-10-21T07_37_11.173Z-1792568231174.json'
d=json.load(open(p,encoding='utf-8'))
print(d['model'], d['items'][0]['truncated'])
PY
# 卡面上限与截断元数据
grep -n "ADVICE_MAX = 30\|CARD_REASON_MAX = 50" tools/agent/dual_track.mjs
# 完整流程闸门
sed -n '260,290p' tools/agent/visual_checklist.mjs
# 历史分析字段（数据侧有 / 渲染侧没印）
grep -n "history_analysis\|history_advice" kb/l7/skills/kb-content-review/scripts/review.py
grep -c "历史审核完整分析" kb/l7/reports/rv-20261021-153523.feishu.md
```
