---
asks:
  - 重启闸门为什么会一直报「有 1 条还没走完、现在重启会把它掐断」，而根本没有消息在处理？
  - "`--force-inflight` 这个开关为什么不该被日常用到？"
  - C1 报的「把守衡卸下/停掉」到底是哪一行、为什么是误报？
  - 收窄 C1 的扫描范围时，怎么保证不把真正的绕过也放过去？
  - 这两个缺陷的共同形状是什么（为什么归成一条）？
  - 线上生效需要满足什么条件（哪些改动要重启）？
collection: 3_措辞表达库
corroborated_by:
  - PMO/守衡-体检后一轮修复-20261022.md（留底件：两条缺陷、改法、读数、未做项）
  - tools/verify_shouheng_ops.py（I1–I4 事件计数成对；C6–C8 launchctl 按目标）
  - tools/ws_daemon.mjs（三个非消息 handler 的销账出口）
  - PMO/已修问题.jsonl（FIX-055 / FIX-056 两条逐字登记）
created_at: 2026-10-22
data_level: L2
evidence_group: rule
evidence_level: L2
forbidden: 不许据本条把「闸门永久报在用」当成「守衡真的在跑一堆任务」；不许把 C1 的收窄读成「可以随便 launchctl bootout 别的作业」（它只是不再把**别的作业**误报成停守衡）；不许把「事件销账成对」当成「每条消息都会被回答」；不许据本条声称 `--force-inflight` 可以用得放心。
half_life_days: 180
id: ref-shouheng-restart-gate-accounting-20261022
kb_class: []
kind: fact
not_proves: 不能证明任何一条具体内容能不能发 —— 它是工程侧判据的缺陷与修法；不能证明重启是安全的 —— 闸门的「正在处理中」只是其中一道读数，重启前还看「群里最后一条消息距今多久」与「会影响哪些改动」；不能证明当前实例已经修好（ws_daemon 改动要重启才加载）；不能证明 C1 收窄后没有新洞（只钉住了三条边界：点名守衡必报 / 点名别的作业不报 / 变量目标仍报）；不能替代 3_措辞表达库 的任何条款；不能证明事件计数这个读法本身最优（它只让 events 与 done 能闭合）。
owner: 刘华丽
pii:
  detected: false
  masked: false
  strategy: 未检出自然人信息：正文只写文件路径、函数名、判据 ID 与读数。
provenance:
  anchor: PMO/守衡-体检后一轮修复-20261022.md#一、本轮做了什么（逐条带读数）
  confidence: 确定
sensitivity_level: L2
source:
  captured_at: 2026-10-22
  fingerprint: 64b0accb22609fb1
  kind: file
  ref: /Users/lute/project/audit_multi_content/PMO/守衡-体检后一轮修复-20261022.md
summary: 重启闸门的两处「判据的输入比它的语义大」：① 计数只记入口不记出口 —— restart_shouheng.sh 用 events > handled+skipped+failed+uncaught 判「还在处理」，而 ws_daemon.mjs 的 bot.added / bot.deleted / card.action.trigger 三个非消息事件只 events++、从不销账 ⇒ 收到过一次这类事件，差值永久 ≥1，闸门此后每次都拒绝重启，人只能被迫 --force-inflight；修法是三个 handler 各补出口（handled / failed / try-finally 的 skipped）。② 扫描只看动词不看目标 —— verify_shouheng_ops 的 C1 把 deploy_skill_growth.sh 里 launchctl bootout com.kb.skill-growth（装它自己的作业）误报成「把守衡卸下/停掉」，恒红一项；修法是按目标收窄：点名守衡必报、点名别的作业不报、目标不明（含 $LABEL）仍报，并以 C6–C8 三条反向对照钉住。读数：verify_shouheng_ops 85 → 89 项全绿。
tier: L1
title: "[参考实现] 重启闸门的两处「判据比输入大」（2026-10-22）：事件只记入口不记出口 ⇒ 闸门永久拒绝重启；C1 只看动词不看目标 ⇒ 恒红一条假红"
topic: 知识
valid_until: 2027-04-20
---

# 重启闸门的两处「判据比输入大」（2026-10-22）

两条各自独立，却是同一个病：**判据读的那个量，与它声称覆盖的事不是一回事。**

## 一、计数只记入口不记出口 ⇒ 闸门成砖头（FIX-055）

`tools/restart_shouheng.sh` 的「正在处理中」判据是：

```python
events > handled + skipped + failed + uncaught   # ⇒ 有事件还没走完
```

而 `tools/ws_daemon.mjs` 里三个**非消息**事件只 `counters.events++`、从不记任何 done：
`im.chat.member.bot.added_v1` / `bot.deleted_v1` / `card.action.trigger`。

⇒ 只要收到过一次这类事件，差值就**永久 ≥ 1**，闸门此后**每次都拒绝重启**，
人只能被迫用 `--force-inflight` —— 而那个开关存在的意义正是「不该被日常用到」。
「闸门成砖头」与「闸门被绕过」是同一件事的两面。

修法：`bot.added` 的欢迎语分支成功 `handled++`、发不出去 `failed++`；
`bot.deleted` / `card.action.trigger` 用 `try/finally` 记 `skipped++`（中途抛异常也照样销账 ——
崩掉的那个事件不该把闸门永久卡死）。

## 二、扫描只看动词不看目标 ⇒ 一条假红长期占位（FIX-056）

`verify_shouheng_ops.py` 的 C1 恒红一项：`deploy_skill_growth.sh: 把守衡卸下/停掉`。
而该脚本实际执行的是 `launchctl bootout gui/$(id -u)/com.kb.skill-growth` ——
装它**自己的** launchd 作业；全文件 grep `shouheng` 零命中。

根因：`launchctl (bootout|unload|stop)` 只匹配动词。而 §2.7 那条规矩的对象是
「守护进程（守衡）」，不是「任何 launchd 作业」—— 判据实现比它引用的规矩更宽。
一条假红会挤掉一个真问题（§2.1.1），而且它会让人开始不看这份报告。

修法（收窄的边界两条，缺一条就是挖洞）：
1. 点名守衡（`com.shouheng` / `ws_daemon` / `run_shouheng.sh`）⇒ **一律报**；
2. 没点名守衡但点名了**别的** `com.*` 作业 ⇒ 不报；
3. 两者都没点名（含 `$LABEL` 变量写法）⇒ **仍按可疑报**。

## 判据

- `verify_shouheng_ops.py` **I1–I4**：I1 扫 `ws_daemon.mjs` 每个 `counters.events++`
  到下一个 events++ 之间必须有「走完」计数；I2/I3 成对反向对照（只 events++ ⇒ 报；配对 ⇒ 不报）；
  I4 点名三类 handler 必须都在（防判据替不存在的代码作证）。
- 同文件 **C6–C8**：点名守衡必报 / 点名别的作业不报 / 变量目标仍报。

## 读数

`python3 tools/verify_shouheng_ops.py`：85 → **89 项全绿**（C1 由 1 处 → 0 处）。

## 部署边界

`ws_daemon.mjs` 的销账改动要重启才生效；本轮**没有**为它单独重启
（同日 10:52 那次重启是为另一条修复 FIX-054）。

## 边界

见 `not_proves`：本条不保证「任何事件都会在有限时间内销账」—— 它只保证**这三个 handler** 有出口；
也不保证 `--force-inflight` 永远不会被用到（真卡住时它仍是唯一出路）。
