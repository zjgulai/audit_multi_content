# 误跑归档 · 2026-10-10 14:13:15

## 发生了什么

准备「逐字回验（bad_cite）」检查器时，我为了复用评审引擎唯一那把尺子
（`review.py::resolve_anchor` / `verify_excerpt`），用 `KB_ENTRY=selftest` **import** 了
`kb/l7/skills/kb-content-review/scripts/review.py`。

结果：**import 触发了引擎整条运行**（空 `--text`），产出一份 `NEEDS_INPUT` 拒答报告，
并写了 run 记录与 index 行。

## 归档了什么（从活目录移出）

| 文件 | 原位置 | 为什么必须移走 |
|---|---|---|
| `20261010-141315.json` | `kb/l7/reports/` | 伪报告。`content_id=text-e3b0c44298fc`（空串 sha256）、`issue_count=0`、`decision=NEEDS_INPUT`。留在 `reports/` 会被当成一份真评审报告，也会污染 bad_cite 统计口径 |
| `20261010-141315.md` | `kb/l7/reports/` | 同上（同一单的 markdown 面） |
| `20261010-1413.json` | `kb/l7/runs/` | 伪 run 记录（`source=daily_health`、`skills=['kb-check']`） |
| `index.jsonl.removed-line` | `kb/l7/runs/index.jsonl` 第 3724 行 | 该行断言「14:13:15 跑过一次 daily_health」，而实际没有 |

## 没有发生的（逐条核过，不是推断）

- **没发飞书**：报告 JSON 里 **不存在 `publish` 键**，`report_url=None`；
  引擎对 `NEEDS_INPUT` 拒发（设计如此），`kb/.work/publish.log` 的写入停在 14:08:57（那是供给侧发布，不是我的）。
- **没碰 L0–L6 任何数据**。
- **没碰评审链代码**（只读 + import）。
- **没碰 14:06:24 那单 run 记录**（`kb-freshness-` 前缀，来自 `freshness.py`，疑似 14:06 的就绪巡检；**不是我的，故保留**）。

## 复原核对

- `kb/l7/reports/*.json`：244 → **243**
- `kb/l7/runs/*.json`：3116 → **3115**
- `kb/l7/runs/index.jsonl`：3724 行 → **3723 行**，尾部停在 `2026-10-10T14:06:24`，
  改写前逐字节校验「前后缀一致、只摘一行」。

## 教训（写进失败手册）

**`kb/l7/skills/kb-content-review/scripts/review.py` 不可 import** —— 它的模块级行为
不只是「定义函数」，import 会跑整条引擎（含写报告、写 run 记录、走新鲜度闸门）。
要复用它的判据函数，必须走**受限前缀 exec**（只在定义区截断执行），或另找官方只读口。
