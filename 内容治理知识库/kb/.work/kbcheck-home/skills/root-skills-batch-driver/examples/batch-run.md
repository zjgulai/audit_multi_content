# 一次完整批跑示例

> 假设要把 `./skills/` 下 3 个 skill 批量评测完，驱动会话（dsh agent）按本 skill 编排。

## 1. 扫描 + 建立 checkpoint

```bash
printf '%s' '{"action":"scan","skills_dir":"./skills","state_path":"./batch-progress.json"}' \
  | python3 scripts/batch-driver.py
```

```json
{"ok": true, "total": 3, "pending": ["a-skill", "b-skill", "c-skill"],
 "running": [], "done": [], "stuck": [], "skipped": []}
```

## 2. 逐个启动 eval subagent 并标记 running

对每个 pending，驱动会话启动一个 `root-skills-eval` subagent 评测该 skill，然后：

```bash
printf '%s' '{"action":"record","state_path":"./batch-progress.json","skill":"a-skill",
  "status":"running","complexity":"standard","note":"启动评测 subagent"}' \
  | python3 scripts/batch-driver.py
```

## 3. 心跳监控（循环）

```bash
printf '%s' '{"action":"heartbeat","progress_dir":"./skills/a-skill/evals","timeout_minutes":15}' \
  | python3 scripts/batch-driver.py
```

- `stale:false` → 继续等，隔段时间再心跳。
- `stale:true` → 查盘 `./skills/a-skill/evals/`：
  - 有报告 → `record done`；
  - 部分完成 → `record`（event_type `resume` 或 `restart`，note 记录选择）；
  - 无产物 → `record`（event_type `restart`），重启 subagent。

## 4. 完成一个收尾一个

```bash
printf '%s' '{"action":"record","state_path":"./batch-progress.json","skill":"a-skill",
  "status":"done","report_path":"./skills/a-skill/evals/report.html","score":91,"note":"done"}' \
  | python3 scripts/batch-driver.py
```

## 5. 汇总

```bash
printf '%s' '{"action":"summary","state_path":"./batch-progress.json","skills_dir":"./skills"}' \
  | python3 scripts/batch-driver.py
```

输出 `batch_summary`（total/evaluated/passed/failed/unscored + 状态分桶）+ 事件清单 +
`repeat_attempt_skills`（连续中断标记）。

## 6. 断点续跑

中途进程退出后，重新执行第 1 步的 `scan`（同一 `state_path`），`done` 的 skill 不会被
重新拉进 `pending`，直接从上次断点继续。
