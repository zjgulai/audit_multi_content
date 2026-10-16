# 知识库体检表 · 20261003-2251-healthcheck

- 库根：`…/知识库/内容治理` ｜ cwd = 本次库根
- 时间：2026-10-03 22:50–22:51 CST
- 档位：**体检档**（kb-check §1；非评审驱动循环档）
- 口径：本 skill 只报不改，全部命令默认只读；唯一写盘为 ④ `workflow_check.py` 的产物与 `/tmp` 沙箱

## 1. 三闸门退出码

| # | 闸门 | 命令 | 退出码 | 结论 |
|---|---|---|---|---|
| ① | 登记表自检 | `kb/kbpy l7/scripts/skills_check.py` | **0** | 过（五类问题 1=0 2=0 3=0 4=0 5=0） |
| ② | 层契约自检 | `kb/kbpy l7/scripts/layers_check.py` | **1** | 判据缺陷（8 条均为 `{kb_root}` 占位符误报，非数据缺陷） |
| ③ | 工作流整体体检 | `kb/kbpy l8/workflow_check.py 20261003-2251-healthcheck` | **1** | 混合：2 条合法变红 + 1 条真坏 + 1 条判据缺陷 |

## 2. 失败项清单

| 对象 | 原因码 | 定性 | 要人做什么 | 复开条件 |
|---|---|---|---|---|
| `layers.yaml` 各层 `cwd: "{kb_root}"` ×8 | `L4 cwd 不是存在的目录` | 判据缺陷 | 改 `layers_check.py:234` 先做占位符替换再 `isdir` | 8 条归 0 或该分支按占位符放行 |
| `kb/l3/candidates/rules.jsonl` | `l3_base1018_matches_L6=false` | 合法变红 | 无（基线=2026-09-23 冻结件，活库已增长） | 重冻基线并留 run_id + 时间戳 |
| 20 项 L4–L7 前序产物 | `③ 哈希不一致` | 合法变红 | 同上 | 同上 |
| 25 个顶层/工作区 `.md` | `⑥ 其他=25`（信封） | **真坏** | 用 node 通道重写为明文 | `其他` 桶归 0 |
| `kb/l7/skills/kb-content-review/scripts/review.py` | `--help` 退出码 2 | 判据缺陷 | 让 ⑦ 接受防线1 拒跑（或带 `KB_ENTRY=selftest`） | ⑦ 按新契约判 |

## 3. 证据

- ② 层数 8 / 必填字段 0 错 / 引擎路径 0 错 / DAG 0 错；仅「cwd 约定」8 条；`layers_check.py:242` 自认 `{kb_root}` 为**合法写法**。
- ③ ② 段：L0/L1/L2 树哈希 `match_L5_baseline` 全 true；仅 L3 漂移（`l3_lines=1018`）。
- ③ ⑥ 段：`md_total=4924`，`enveloped=594`；桶 `hostlib 510 / 冻结层 59 / 其他 25`。抽验 `l3-candidates-rules-定稿核对.md`：python 10306 vs node 14402，差值 **4096**。
- ③ ⑦ 段：`review_py_runnable=false`，help 首行＝`拒跑：本脚本是**内部引擎**，不是对外入口（防线1，2026-10-03）。`；实测 `--help` 退出码 **2**（防线生效，非损坏）。
- ④ 过关：沙箱 510 md / 信封 0；装载位 509 条 / E001 None / E046 None / 健康分 79.2（≥60）。
- ③ 产物：`kb/l8/workflow_check_20261003-2251-healthcheck.json`

## 4. 未判定

- 本轮为体检档，未跑 ③ 路由对账 `routes_reconcile.py`、⑤ 信封闸门 `envelope_gate.py` / `envelope_census.py`、⑥ 投影一致性 `projection_reconcile.py`（用户只点名三闸门）。
- 跑测期间 `kb/.work/publish.log`、`kb/.work/l5_integrity.json` 在 22:48 被其它进程写过 → 存在并发写入者；本表数值仅对上述 run_id 与时间戳有效。
