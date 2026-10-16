# 体检表样例（格式参考，数字是示例不是实况）

> 每次体检按这个形状交付：**闸门 → 退出码 → 结论 → 证据**。
> 结论只允许四种：`过` / `真坏` / `合法变红` / `判据缺陷`（口径见 `SKILL.md` §4）。

| # | 闸门 | 命令 | 退出码 | 结论 | 证据 |
|---|---|---|---|---|---|
| ① | 登记表自检 | `kb/kbpy l7/scripts/skills_check.py` | 0 | 过 | 五类问题全 0（应装未装 0 / 未登记 0 / 副本不一致 0 / 依赖缺失 0 / 自测缺失 0） |
| ② | 层契约 | `kb/kbpy l7/scripts/layers_check.py` | 0 | 过 | 8 层齐、cwd/python/envelope 齐、引擎路径存在 |
| ③ | 路由表对账 | `kb/kbpy l7/scripts/routes_reconcile.py kb/l7/reports/<RUN>-routes-winners.json` | **2** | 判据缺陷（缺输入） | `kb/l7/reports/` 下无 `*routes-winners*`；赢家表是运行时产物、全库无生成者 ⇒ **缺输入 exit 2，不是"全不一致"** |
| ④ | 链路收口 | `kb/kbpy l8/workflow_check.py <RUN>` | 1 | 合法变红 | 第 ② 段冻结基线在活库必然漂移；附漂移文件清单（本次 N 个） |
| ⑤ | 信封闸门 | `python3 tools/envelope_gate.py` / `kb/kbpy l8/envelope_census.py` | 0 / 0 | 过 | 差值恒 4096 的信封态 0 个（`.py`/`.txt` 用前者，`.md` 用后者） |
| ⑥ | 投影一致性 | `kb/kbpy l8/projection_reconcile.py` | 0 | 过 | view 与权威库逐项一致 |

## 失败项清单（同一张表的下半段）

| 对象 | 原因码 | 要人做什么 | 复开条件 |
|---|---|---|---|
| 门③ 输入 | `MISSING_INPUT` | 按 `kb-manage` 的触发电测生成 `<RUN>-routes-winners.json` 放进 `kb/l7/reports/` | 文件存在且格式可解析 ⇒ 重跑门③ 得 exit 0 |
| 门④ 第②段 | `BASELINE_DRIFT` | 确认漂移是活库正常变更还是真被改坏 | 人工确认后更新冻结基线或修复 |

## 纪律

- **不许把工具 bug 报成数据缺陷**：见 `references/gotchas.md` 四条判据缺陷。
- **"层已跑完"类结论必须带 run_id + 时间戳**（本库存在并发写入者）。
- 本 skill **只报不改**：真坏项交 `kb-repair`，本表不改任何东西。
