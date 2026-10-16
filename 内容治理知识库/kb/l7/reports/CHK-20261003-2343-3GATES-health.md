# 知识库三闸门体检 · registry 自检 / 层契约 / 路由对账

- RUN：`CHK-20261003-2343-3GATES`
- 时间：2026-10-03 23:39–23:42 CST（命令实测，非转录）
- 库根：`/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理`（cwd = 库根）
- 档位：**体检档**（人调用）；本 skill 只报不改
- 解释器：`kb/kbpy`（库内约定解释器；PyYAML 6.0.3）

## 1. 体检表（本次点名的三道）

| # | 闸门 | 脚本 | 退出码 | 判定 | 关键证据 |
|---|---|---|---|---|---|
| ① | registry 自检（登记表） | `kb/l7/scripts/skills_check.py` | **0** | **过** | 五类问题 1=0 2=0 3=0 4=0 5=0｜合计 0；登记 71 条（本项目 52 / 宿主通用 19），装载位扫到 59 目录；本项目生产 40 个、已装 40、还差 0；`status=参考` 11 个不安装；12 个登记了 `source` 但未安装 → 跳过副本比对（已列明，非错误）；62 条未登记 `selftest`（单独归类，不算错误） |
| ② | layer 契约 | `kb/l7/scripts/layers_check.py` | **0** | **过** | 六类问题全 0；层数 8（L0…L7，无重复）；必填 12 字段齐、`envelope` 取值合法、`python` = `${KB_PYTHON}`；引擎路径存在性 0 条；DAG 非线形：L2←L1,L0 ｜ L3←L0,L2 ｜ L4←L2,L3 ｜ L5←L0,L2,L3 ｜ L6←L0,L2,L3 ｜ L7←L0,L3,L4,L5,L6；「无干跑档」清单 0 条 |
| ③ | 路由对账 | `kb/l7/scripts/routes_reconcile.py` | **2** | **缺（缺输入，未判定）** | 不带参数：`error: the following arguments are required: winners`；带未存在的 `kb/l7/reports/RUN-routes-winners.json`：`环境错：赢家表不存在 …` + `缺输入时本闸门不得报绿，也不得静默按「全不一致」跑`。全库 `kb/l7/reports/` 无任何 `*-routes-winners.*`；`find ~ -maxdepth 6 -name '*routes-winners*'` 0 命中 |

## 2. ③ 为什么缺（缺的是输入，不是脚本）

**已确认事实**

1. 赢家表是**触发盲测的运行时产物**（每条 prompt 每轮实际被谁接走），**不是静态资产**：库里唯一引用 `winners` 的脚本就是 `routes_reconcile.py` 自己（读），**没有任何脚本生成它**（`grep -rn winners kb/l7/scripts/*.py` 只命中该文件）。
2. 规定产物名 = `kb/l7/reports/<RUN>-routes-winners.json`；该路径下现在没有这个文件，历史报告目录里也没有同族文件。
3. 2026-10-03 的修复把「静默降级」改成硬报错：旧实现按「0 条 ⇒ 65 条全不一致」跑完并 exit 1，不报错、不告警；现在缺输入直接 **exit 2**。所以今天这个红是**设计如此**，不是坏了。
4. 要今天的结论，必须先按 `kb-manage` 的触发电测重跑赢家表（冻结 65 条 `~/Desktop/skill/内容治理中文skill/_基线用例.json`，或 v2 115 条），再回灌本闸门。该动作**不在本次只读体检范围**。
5. 该闸门**没有被接进每日体检**：`grep -nE 'skills_check|layers_check|routes_reconcile' kb/l7/scripts/daily_health.py` → **0 命中**；`kb/l7/reports/2026-10-03-daily-health.md` 全文也不含「路由对账 / winners / routes_reconcile」。⇒ 这道闸门缺席不会在日常报告里显形。

**本次另跑的「代理对账」（只作参考，不构成今天的闸门结论）**

- 用**最新可得**的运行时产物 `_eval-kb-manage/blind_v2.winners.txt`（mtime 2026-09-29 19:58，115 条，与 `cases_v2.json` 的 id 集逐条对齐）：
  - 逐条全轮命中 **109/115**（门槛 F1 ≥ 0.90）；② 不一致 **6 条**；④ 路由表自检 **0 条**；**exit 1**。
  - 6 条：I1–I5（`brand-ai-provenance-rights-review`）+ `kb-manage-4`（第 3 轮被 `kb-pipeline` 接走）。
- 该结果**不能当今天用**，两条硬理由：① 数据是 **4 天前**的；② `kb/l7/registry/routes.yaml` **2026-10-03 06:53** 改过，路由表已不是当时的表。
- I 组这 5 条是**路由表自己已登记**的未过门槛项，不是新发现：`routes.yaml:230` 记 `brand-ai-provenance-rights-review: 0.440`（★ 未过），`routes.yaml:238 known_conflict` 记「I1↔G3 近重复 / I2 欠定义 / I5↔F5 近重复（未解，主因）」，并给出结论「不再改用例、也不再调 description」。
- 另一份**冻结基线赢家表**（`blind_before_v2.winners.txt`，mtime 2026-09-29 18:37，65 条，翻译前）实测 **59/65 不一致、exit 1** —— 这是**翻译前**的旧环境状态，把它当今天结果就是本闸门明令禁止的「静默全不一致」误判，**故不作为结论**，仅留证。
- 判据细节（不是数据缺陷）：赢家表里 `AI 溯源与权利审查`（**带空格**）未被子目录名 `AI溯源与权利审查` 折叠，`ALIAS` 无该变体；对这些用例不改变结论（其余两轮本就是 `NONE`），但会让「被谁抢走」计数虚增 2 次。

## 3. 失败项清单（③）

| 对象 | 原因码 | 要人做什么 | 复开条件 |
|---|---|---|---|
| 路由对账闸门（缺输入） | 脚本未给码，属环境错 `exit 2` | 按 `kb-manage` 触发电测重跑一轮赢家表（65 或 115 条 × 3 轮），落 `kb/l7/reports/<RUN>-routes-winners.json`（或 `.txt`，`id|r1|r2|r3`） | 该文件存在且 `routes_reconcile.py <文件>` 跑出确定结论（exit 0 或 1） |

## 4. 本次未跑的三道（不在三件套内，且其中一道会写库）

| 闸门 | 未跑原因 |
|---|---|
| ④ 链路收口核验 `kb/l8/workflow_check.py <RUN>` | **无干跑档**，不加任何参数也会写 `kb/l8/workflow_check_<RUN>.json`；另：本次实测有别的会话正在跑它（见下） |
| ⑤ 信封闸门 | 命令行未点名；`tools/envelope_gate.py`（覆盖 .py/.txt/.md）与 `kb/l8/envelope_census.py`（只扫 .md）均未执行 |
| ⑥ 投影一致性 `kb/l8/projection_reconcile.py` | 命令行未点名 |

## 5. 并发观测（§5 要求先确认）

- `kb/.work/.kb.lock` **不存在**（无命令级锁持有）⇒ 本次三道均为只读，不受影响。
- 但 `ps aux` 实测**另有会话/批次正在跑闸门**（23:41）：`kb/l8/workflow_check.py REPAIR-PREFIX-20261003-2345`（pid 684）、`kb/l8/workflow_check.py REG-20261003-2345`（pid 99503）、`kb/l8/envelope_census.py`（pid 1289）、`kb/l8/align_l0_schema.py 20261003-2337`，以及一个跑 ①–⑥ 的批处理脚本；`kb/.work/publish.log`（23:39:53）与 `kb/.work/l5_integrity.json`（23:39:46）均在 30 分钟内被写过。
- 结论：**①②③ 的读数有效**（只读、且关键文件未被上述进程改写）；但 ④⑤⑥ 的读数**此刻不保证稳定**，要跑请等这批收工或另起唯一 RUN。
