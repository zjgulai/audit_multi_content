---
name: kb-check
description: |
  当用户说「知识库体检 / 检查一下知识库 / 跑一遍所有闸门 / 闸门过没过 / 全库自检 / 知识库健康检查 / 信封闸门过一遍 / 登记表对不对 / skills_check / workflow_check」时使用。
  把全库各层的 check 一次跑完并汇总成一张体检表：登记表自检（应装未装 / 装了没登记 / 副本不一致 / 依赖缺失 / 自测缺失）、层契约自检、链路收口核验、信封闸门、投影一致性、路由表对账。**只报不改**。
  **欠定先追问、不加载**：只打本名 / 只有名词 / 指代不明 / 只要判据不要跑 → 先问清跑哪几道闸门。
  **破坏性 / 越权一律不加载**：修闸门 / 删副本 / rm -rf / 清空 / 套 token / 绕开流程改库。
  判归：闸门没过要修→kb-repair；跑 L0→L7 供给链→kb-pipeline；只对账 L0→kb-l0-feishu；能不能发→kb-review。
  触发词：知识库体检、全库自检、统一闸门、跑一遍所有闸门、闸门过没过、知识库健康检查、信封闸门、登记表自检、路由对账。
version: "1.3.0"
last_updated: 2026-10-04
license: "Proprietary — Momcozy internal use only"
complexity: "standard"
compatibility:
  claude: { status: "native" }
  kimi: { status: "native" }
  cursor: { status: "native" }
  gpt: { status: "bridge", limitations: ["长输出需分页"] }
  minimax: { status: "bridge", limitations: ["需中文优化"] }
  dsh: { status: "native", notes: "kbpy 同机可用" }
  codex: { status: "native" }
---

# kb-check —— 知识库统一闸门

**一句话**：本 skill **只报不改**。所有命令默认只读；任何修复动作走 `kb-repair`。

## 0. 两个档位（先分清，别混 —— 2026-10-03 加）

| 档位 | 跑哪几道 | 谁触发 | 写不写库 |
|---|---|---|---|
| **驱动循环档**（评审链里的 L7） | **只跑 `layers.yaml` 本层 `engine:` 声明的 3 道** | 逐层驱动循环的 L7 子会话 | **不写**（本层 `skill_write: false`） |
| **体检档**（本节 §1 的清单） | 6 道闸门一次性跑完 | 人 / 日检 | ⚠️ 其中 `workflow_check.py` **无干跑档、会写 `kb/l8/`** |

★ **引擎清单的唯一真源是 `kb/l7/registry/layers.yaml` 本层 `engine:`**。本节 §1 是**体检档**的编排，
**不是**循环的引擎清单；两者不一致时**以 `layers.yaml` 为准**（本库纪律：同一事实只写一处）。

2026-10-03 实测（循环档）：只跑了 `l7/scripts/skills_check.py` 与 `.work/l7_article_source_refresh.py`（干跑档），
`l8/workflow_check.py` 因**无干跑档且写盘**被跳过；L7 无层侧落章（三重代码级豁免）。
登记见 `kb/l7/registry/report-output-contract.yaml` 的 `applied_20261003.l7_declaration_conflicts_20261003`（L7-C1/C2/C3）。

## 1. 闸门清单（体检档：一次跑完，逐条给退出码）

```bash
cd "<本次库根>"                     # ★ cwd = 本次库根

# ① 登记表：五类问题全 0、退出码 0
kb/kbpy l7/scripts/skills_check.py

# ② 层契约：8 层齐全 + cwd/python/envelope 齐 + 引擎路径存在 + DAG 非线形
kb/kbpy l7/scripts/layers_check.py

# ③ 路由表对账：实际被谁接走 vs 路由表写谁
#    ⚠️ 赢家表是**触发评测的运行时产物**（每条 prompt 每轮实际被谁接走），**不是静态资产** ——
#       全库没有任何脚本会自动生成它。**缺输入 ⇒ 退出码 2**（2026-10-03 修：旧实现会静默按
#       「0 条 ⇒ 65 条全不一致」跑完并 exit 1，不报错、不告警）。
#       形态：`<id>|<第1轮>|<第2轮>|<第3轮>`（txt）或 `[{"id":…,"winners":[…]}]`（json）都认。
#       要今天的数据 ⇒ 先按 kb-manage 的触发电测重新生成赢家表。
kb/kbpy l7/scripts/routes_reconcile.py kb/l7/reports/<RUN>-routes-winners.json

# ④ 链路收口核验（活库模式下会合法变红，见 §3）
#    ⚠️ **无干跑档**：不加任何参数也会写 kb/l8/workflow_check_<RUN>.json（:254-255）
#    ⇒ **评审循环里不许跑它**；体检档要跑，先接受这次写盘（或单独报批开写档）
kb/kbpy l8/workflow_check.py <RUN>

# ⑤ 信封闸门：同一路径 Python getsize 与 node statSync().size 差值恒 4096 即信封态
python3 tools/envelope_gate.py          # 覆盖 .py/.txt/.md
kb/kbpy l8/envelope_census.py           # 库自带，**只扫 .md**

# ⑥ 投影一致性
kb/kbpy l8/projection_reconcile.py      # ⚠️ 无干跑档，只读复核用，不要加写参数
```

## 2. 判据缺陷（先知道，别被误导）

| 脚本 | 缺陷 | 规避 |
|---|---|---|
| `l7/scripts/skills_check.py` | 第 4/5 类判 `depends_on_engine` / `selftest` 路径**不做 `expanduser`**（第 1001–1002、1018–1019 行）→ 凡 `~` 开头的路径都会误报"不存在" | 这两个字段一律写**库根相对路径** |
| `l8/workflow_check.py` | 第 ② 段用「权威库未被改动」的**冻结基线** | 活库模式下变红是**合法**的，不等于坏了；要区分"变了"与"坏了" |
| `l8/envelope_census.py` | **只扫 `.md`** | `.py` / `.txt` 要另用 `tools/envelope_gate.py` |
| `l8/projection_reconcile.py` | **无干跑档** | 只做只读复核 |

## 3. 结论口径：区分三种"红"

1. **真坏** —— 路径不存在、副本不一致、退出码非 0。→ 交 `kb-repair`。
2. **合法变红** —— 活库模式下冻结基线比对（`workflow_check` 第 ② 段）。
   → 结论写"基线漂移，非缺陷"，并附漂移内容。
3. **已知判据缺陷** —— `~` 路径误报等（见 §2）。→ 结论写"判据缺陷，非数据缺陷"，
   **不许把工具 bug 报成数据缺陷**。

## 4. 交付物

1. 一张**体检表**：闸门 → 退出码 → 结论（过 / 真坏 / 合法变红 / 判据缺陷）→ 证据。
2. 失败项清单：**对象 + 原因码 + 要人做什么 + 复开条件**。
3. `kb/l7/reports/<RUN>-health.md` —— **仅体检档产出**；评审驱动的 L7 档**不写库**（`skill_write: false`），
   体检表以**会话正文**交付。写 `.md` 一律走 `node` / `/bin/cp` 通道（python 直写会带 4096 字节信封）。
4. **"层已跑完"类结论必须带 run_id + 时间戳**——本库实测存在并发写入者
   （`kb/l2/units.jsonl` 在未被本 agent 写入的情况下从 10551 行涨到 10650 行），只看文件状态会误判。

## 5. 何时停下来问人

- 闸门报出 `kb/l0…l6` 的数据/台账异常 → **只读取证，不要先写**。
- 发现 `.kb.lock` 或 `kb/.work` 近 30 分钟大量写入 → 可能有另一批在跑，先确认。
- 体检表里出现"未知原因"的红 → 宁可标"未判定"，不要猜。
## 6. 停用条件（什么时候该下线本 skill）

- 各层 check 被统一到单一 CI 入口、不再由本 skill 汇总 → **停用**。
- 家族侧 `skills_check.py` / `workflow_check.py` 被替换或合并 → **停用**并指向新入口。
- **停用前交接**：把闸门清单与「判据缺陷」表迁给接手方（这两块是本 skill 最贵的资产）。
**Gotchas（错误 → 修正）→ `references/gotchas.md`**
