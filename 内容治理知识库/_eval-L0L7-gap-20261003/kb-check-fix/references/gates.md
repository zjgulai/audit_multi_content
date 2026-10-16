# 六道闸门（体检档）—— 命令 / 退出码 / 输入契约

> 由 `SKILL.md` 正文下沉（渐进式披露）。**体检档**编排，不是驱动循环的引擎清单 ——
> 循环档的引擎清单唯一真源是 `kb/l7/registry/layers.yaml` 本层 `engine:`。

## 前置

```bash
cd "<本次库根>"                     # ★ cwd = 本次库根；脚本里的相对路径全部相对它
python3 <本 skill 目录>/scripts/preflight.py    # 先跑只读预检查，看输入齐不齐
```

## ① 登记表自检

```bash
kb/kbpy l7/scripts/skills_check.py
```

判据：五类问题（应装未装 / 装了没登记 / 副本不一致 / 依赖缺失 / 自测缺失）**全 0**、退出码 0。
已知缺陷（`~` 路径不 expanduser）见 `gotchas.md`。

## ② 层契约自检

```bash
kb/kbpy l7/scripts/layers_check.py
```

判据：8 层齐全 + cwd / python / envelope 齐 + 引擎路径存在 + DAG 非线形。

## ③ 路由表对账

```bash
kb/kbpy l7/scripts/routes_reconcile.py kb/l7/reports/<RUN>-routes-winners.json
```

**输入契约（缺了会 exit 2，不是数据坏了）**：

- 赢家表是**触发评测的运行时产物**（每条 prompt 每轮实际被谁接走），**不是静态资产**；
  全库没有任何脚本会自动生成它。**缺输入 ⇒ 退出码 2**。
- 形态两种都认：`<id>|<第1轮>|<第2轮>|<第3轮>`（txt）或 `[{"id":…,"winners":[…]}]`（json）。
- 要今天的数据 ⇒ 先按 `kb-manage` 的触发电测重新生成赢家表。
- 2026-10-03 修：旧实现会静默按「0 条 ⇒ 65 条全不一致」跑完并 exit 1，不报错、不告警。
  所以看到 exit 1 与看到 exit 2 要说清楚是两件不同的事。

## ④ 链路收口核验

```bash
kb/kbpy l8/workflow_check.py <RUN>
```

⚠️ **无干跑档**：不加任何参数也会写 `kb/l8/workflow_check_<RUN>.json`（:`254-255`）。
⇒ **评审循环里不许跑它**；体检档要跑，先接受这次写盘（或单独报批开写档）。
第 ② 段用「权威库未被改动」的冻结基线 ⇒ **活库模式下变红是合法的**，见 `gotchas.md`。

## ⑤ 信封闸门

```bash
python3 tools/envelope_gate.py          # 覆盖 .py/.txt/.md
kb/kbpy l8/envelope_census.py           # 库自带，**只扫 .md**
```

判据：同一路径 Python `getsize` 与 node `statSync().size` 差值恒 4096 即信封态。
两者覆盖面不同，**不能互相替代** —— 见 `gotchas.md`。

## ⑥ 投影一致性

```bash
kb/kbpy l8/projection_reconcile.py      # ⚠️ 无干跑档，只读复核用，不要加写参数
```

## 汇总

逐道给：闸门 → 退出码 → 结论（过 / 真坏 / 合法变红 / 判据缺陷）→ 证据。
样例见 `../examples/health-table-example.md`。
