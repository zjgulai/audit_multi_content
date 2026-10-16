---
title: 编排循环规范
doc_type: reference
module: root-skills-batch-driver
topic: orchestration-loop
status: stable
created: 2026-09-14
owner: self
source: human+ai
---

# 编排循环规范

本文件定义 `root-skills-batch-driver` 的编排循环、状态机与事件类型。
硬规则（无进展超时、查盘完成度、落盘为准、事件留痕）的**权威源**是
`root-skills-eval/references/batch-evaluation.md`，此处只定义本 skill 的实现。

## 1. 状态机

每个被测 skill 在 checkpoint 里的状态：

```
pending → running → done
   │         │
   │         ├─ (无进展超时且查盘判定中断) → stuck → 续接/重启 → running
   │         └─ (目录移除) → skipped
   └─ (目录移除) → skipped
```

| 状态 | 含义 | 进入条件 |
|------|------|----------|
| `pending` | 尚未启动 | scan 发现新 skill |
| `running` | 已启动评测 subagent | record `running`（attempts +1） |
| `done` | 已产出报告 | record `done`（附 report_path / score） |
| `stuck` | 判定无进展中断 | heartbeat stale + 查盘不完整 |
| `skipped` | 目录里已消失 | scan 时发现 skill 被移除 |

## 2. 无进展超时（heartbeat）

- 判据：`progress_dir` 下（递归）最新文件 mtime 距今 idle 秒数 > `timeout_minutes * 60`。
- 超时映射：`simple`/`standard` = 15 分钟，`complex` = 25 分钟（对齐 eval，100 条用例放宽）。
- 忽略 `__pycache__` / `.git`。
- 目录**无任何产物**时 `stale:false`（尚未产出不算卡死），避免误杀刚启动的 subagent。

## 3. 超时处置（查盘完成度）

心跳判 stale 后，先核对落盘产物决定处置：

| 落盘情况 | 处置 | 事件 |
|----------|------|------|
| 已有 `results*.json` + 报告 HTML | 已完成 → record `done` 收尾回填 | `done` |
| 有 `results*.json`（部分完成） | 原会话**续接**或**重启**（二选一，记录选择） | `resume` / `restart` |
| 无任何产物 | 重启（attempts +1） | `restart` |

## 4. 事件类型

| 类型 | 触发 |
|------|------|
| `start` | 启动评测（record `running`，默认 event_type） |
| `resume` | 超时后续接 |
| `restart` | 超时后重启 |
| `timeout` | 判定无进展超时 |
| `done` | 评测完成 |
| `skip` | skill 从目录移除 |

事件一律带 `ts` / `skill` / `type` / `note`，写入 checkpoint 的 `events[]`，随 `summary` 交付。

## 5. checkpoint（断点续跑）

- 文件：`batch-progress.json`，字段见 `scripts/batch-driver.py` 的 `load_state`。
- `scan` 幂等：已有状态保留，新 skill 记 `pending`，消失的 pending/running 记 `skipped`。
- 中断后重跑只需重新 `scan` 同一 `state_path`，即可从上次断点继续（不重跑 `done`）。
- checkpoint 损坏（非 JSON）→ 报错，不覆盖；先备份 `.corrupt-<ts>` 再重建。

## 6. 汇总（summary）

- `evaluated = |done|`；`passed/failed` 按 score 归档值 ≥/< 85 分；无法归档记 `unscored`。
- score 归档优先级：checkpoint 里的 `score` → 被测 skill 的 `evals/score.json` 的 `composite_100`。
- `repeat_attempt_skills`：`attempts >= 2` 的 skill（连续中断，供复盘单独标记）。

---

**最后更新**: 2026-09-14
