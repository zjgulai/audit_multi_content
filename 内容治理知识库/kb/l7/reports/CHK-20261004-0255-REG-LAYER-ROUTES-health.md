# 体检表 — registry 自检 / layer 契约 / 路由对账（三道）

- RUN：CHK-20261004-0255-REG-LAYER-ROUTES
- 时间：2026-10-04 02:55:57 CST（实测批跑，命令一次跑完）
- 范围：**用户点名的三道**（① 登记表自检 / ② 层契约 / ③ 路由对账）。④⑤⑥ 未跑，理由见「缺口说明」。
- 库根：`/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理`（cwd = 库根）
- 环境证据：跑前 `kb/.work/.kb.lock` 不存在；跑后 `kb/l7/registry/` 无改动 ⇒ **这三道均为只读，未写库**。

## 一、三道闸门

| # | 闸门 | 命令 | 退出码 | 判定 | 关键证据 |
|---|---|---|---|---|---|
| ① | 登记表自检 | `sh kb/kbpy l7/scripts/skills_check.py` | **0** | 过 | 登记 71 行（本项目 52 + 宿主通用 19）；装载位扫到 59 个目录；**五类问题 1=0 2=0 3=0 4=0 5=0**；本项目要用 40 个、已装 40 个、还差 0 个 |
| ② | 层契约 | `sh kb/kbpy l7/scripts/layers_check.py` | **0** | 过 | 层数 8（L0…L7 齐）；**六类问题全 0**：必填 12 字段齐 / 引擎路径存在 / cwd+解释器约定 / DAG 无环 / 干跑档声明；「无干跑档清单」0 条 |
| ③ | 路由对账 | `sh kb/kbpy l7/scripts/routes_reconcile.py _eval-kb-manage/blind_v2.winners.txt --cases _eval-kb-manage/cases_v2.json --alias` | **1** | 有对账不上 | 逐条全轮命中 **109/115 = 0.948**；④ 节路由表自检 **0 条**；② 节不一致 **6 条**（归因见下） |

② 的上游关系（脚本自报）：L0←外部源｜L1←L0｜L2←L1,L0｜L3←L0,L2｜L4←L2,L3｜L5←L0,L2,L3｜L6←L0,L2,L3｜L7←L0,L3,L4,L5,L6

## 二、③ 的 6 条不一致 —— 逐条归因

| 用例 | 期望 | 实际（三轮） | 归因 | 性质 |
|---|---|---|---|---|
| I1 | brand-ai-provenance-rights-review | 视频安全审查×3 | `routes.yaml:238-244` **已登记**：I1↔G3 近重复，同一意图两个归属 | 已知用例歧义 |
| I2 | 同上 | NONE / 图片安全审查 / NONE | `routes.yaml:253` **已登记**：用例未说模态，「补模态」这个处方本身是错的 | 已知用例欠定义 |
| I3 | 同上 | NONE / 正确 / NONE | **未登记**：三轮只中 1 轮 ⇒ 判不稳 | flaky，待判 |
| I4 | 同上 | 正确 / NONE / NONE | **未登记**：同上 | flaky，待判 |
| I5 | 同上 | 图片安全审查×2 / CLARIFY | `routes.yaml:247` **已登记**：I5↔F5 近重复，表里自认「这才是主因」 | 已知用例歧义 |
| kb-manage-4 | kb-manage | kb-manage / kb-manage / kb-pipeline | **未登记**：字面串冲突 —— 「知识库该更新了」在 `routes.yaml:65` 是 **kb-pipeline 的 say**，而用例拿它问「归属确认」 | 需人裁 |

**不是缺陷的一项（已复算排除）**：旧记录怀疑的 `AI 溯源与权利审查` 空格变体，已在 `routes_reconcile.py:120-163` 的 `canon()` 里修好；本次 I3/I4 的失败**不是**空格问题（第二轮就是正确命中），是轮次不稳。

## 三、缺口说明（「缺哪道」逐条答）

### 1. 缺的不是 ③ 这道闸门，是它的**当天输入**
- 本 skill 规定的产物名是 `kb/l7/reports/<RUN>-routes-winners.json`。实测：
  `find kb/l7/reports kb/l7/runs -name "*routes-winners*"` ⇒ **空**。**库内不存在任何赢家表。**
- 赢家表是**触发评测的运行时产物**（每条 prompt 每轮实际被谁接走），全库**没有任何脚本会自动生成它**。
- 反证实测：喂规定名 `kb/l7/reports/CHK-20261004-routes-winners.json` ⇒
  `环境错：赢家表不存在…` / **EXIT=2**（缺输入不报绿、不静默跑）。
- 本次实际使用的是**库外**产物 `_eval-kb-manage/blind_v2.winners.txt`（115 条，mtime **2026-09-29 19:58**），
  配套用例 `_eval-kb-manage/cases_v2.json`（19:51）。**两者同批、配对正确。**
- ⇒ **③ 的结论只对 2026-09-29 那批数据成立，不是"今天"的结论**（今天 2026-10-04）。要今天的数，只能按 kb-manage 的触发电测重新生成赢家表 —— 这不在三道闸门内。

### 2. ④⑤⑥ 不在这三道里（按你点名的范围交付）
- ④ `l8/workflow_check.py`：**无干跑档**，不加参数也会写 `kb/l8/workflow_check_<RUN>.json` ⇒ skill 明令评审循环里不许跑。
- ⑤ 信封闸门、⑥ 投影一致性：未跑。
- **实据**：`kb/l8/workflow_check_CHK-20261004-0255-WFP.json`（mtime 02:55:16）与 `CHK-20261004-0248.json`（02:53:29）**不是本次三道写的**；`ps` 实测另有进程正在跑 `l8/projection_reconcile.py` 与 `l7/scripts/skills_check.py` ⇒ **另一个会话正在跑六道闸门档**。

### 3. 闸门覆盖缺口（**没接线**，不是**接错了**）
- `routes.yaml.mutual_not_for` 登记 **7 组**，`routes_reconcile.py:326` **硬编码 7 对**；集合比对：
  差集 = `[(视频安全审查,文案合规审查)]` ⇒ **本库唯一带长解释、且是 2026-09-30 盲测 T20 修出来的那组互斥规则，0 断言。**
  该规则**事实上成立**（实测两份 SKILL.md 互相点名各 1 次），所以是覆盖缺口而非数据缺陷。
- `routes.yaml.frozen_expectation.dir_name_map`（13 个 brand-* 目录名映射）：`routes_reconcile.py` 里 **0 命中、不读它**（脚本用自带 ALIAS 表）。
  实测两者 **13/13 完全一致**（脚本另有 1 个遗留别名 `内容审查总控旧`）⇒ 无漂移，但**漂移了也不会被发现**。
- `routes.yaml.known_conflict` / `measured_20260929`：纯注释，0 断言。

### 4. 判据缺陷（本次**未触发**，登记备查）
- `skills_check.py` 第 4/5 类对 `depends_on_engine` / `selftest` **不做 expanduser** ⇒ 凡 `~` 开头路径会误报「不存在」。
  本次 4=0、5=0，**未触发**（不代表判据已修）。
- `skills_check.py` 另有「3 跳过」：12 个登记了 `source` 的条目尚未安装，未做副本比对（非错误，但**这部分副本一致性本次无证据**）。
- `skills_check.py` 「未登记 selftest」62 条（单独归类，不算错误）。

### 5. 并发警告（本次实测）
- 跑闸门时 `kb/.work/publish.log` mtime = 02:55:06、`kb/l8` 有新文件 ⇒ **有并发写入者**。
  三道闸门均为只读、`kb/l7/registry/` 在窗口内无改动，故本次三道的结果**未被污染**；
  但「库是静止的」这一前提**不成立**，任何「某层已跑完」类结论必须带 run_id + 时间戳。

## 四、要人做什么

| 对象 | 原因码 | 要人做什么 | 复开条件 |
|---|---|---|---|
| 赢家表 | ③ 输入过期（2026-09-29） | 按 kb-manage 触发电测重跑，产出 `kb/l7/reports/<RUN>-routes-winners.json` | 有当天赢家表后重跑 ③ |
| I1 / I2 / I5 | 用例集自身歧义（已登记） | 改用例：I1 与 G3 合并、I2 补模态、I5 与 F5 二选一 —— **不建议再改 skill description** | 用例修订后重测 |
| I3 / I4 | 轮次不稳（未登记） | 判是 flaky 还是真不稳（同批多跑几轮看命中分布） | 有轮次分布数据 |
| kb-manage-4 | 字面串冲突（未登记） | 人裁：给 kb-manage↔kb-pipeline 补 `mutual_not_for`，或改用例措辞 | 裁决落地 |
| 互斥规则 1 组 / dir_name_map | 覆盖缺口（0 断言） | 要不要接线属**机制改动，待裁** | 裁决落地 |
