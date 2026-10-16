# 体检表 · CHK-20261004-1130-REGISTRY-ROUTES

- 运行时刻：2026-10-04 11:22–11:35
- 库根：`/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理`
- 档位：**体检档**（`kb-check` §0），本次**重点 = registry(skills.yaml) ⇄ routes.yaml**
- 并发状态：**另有一批会话在同一时刻跑同一套闸门**（PID 50073 `_chk-run-CHK-20261004-1118-AG/sweep.sh`；
  `kb/.work/.publish.lock` 11:22 在场；`kb/l7/runs/` 11:18–11:20 有新落章）。本表对写入型闸门做了回避，见门④。

## 一、六道闸门（体检档）

| # | 闸门 | 退出码 | 结论 | 证据 |
|---|---|---|---|---|
| ① | `l7/scripts/skills_check.py` 登记表自检 | **0** | 过 | 五类问题 `1=0 2=0 3=0 4=0 5=0`；本项目要用 40（生产 40 / 候选 0 / 规划 0），已装 40 |
| ② | `l7/scripts/layers_check.py` 层契约自检 | **0** | 过 | 六类问题全 0；层数 8（L0…L7）、DAG 无环 |
| ③ | `l7/scripts/routes_reconcile.py` 路由表对账 | **2**（缺输入）／**1**（喂历史赢家表） | **缺输入 = 真缺口**（产物全库不存在）；喂 03:24 赢家表 ⇒ 5 条不一致 | 见 RR-5、RR-4 |
| ④ | `l8/workflow_check.py` 链路收口 | **未跑（本会话）** | **未判定** | 该道无干跑档、会写 `kb/l8/` 并落 ingest 探针（`workflow_check.py:254-255`）；**并发会话正在跑同一道**，本会话回避 |
| ⑤a | `tools/envelope_gate.py` | **0** | 过 | 1965 文件 `正常 1965 ｜ 信封态 0 ｜ 读不到 0`；两读者交叉一致 |
| ⑤b | `l8/envelope_census.py` | **0** | 过 | 10375 个 `.md`，1079 个信封态**全部**落在 `l8/_archive/enveloped-20260923-1520/`（569）与 `.work/hostlib.bak-20260928-152220/`（510），均已分类 |
| ⑥ | `l8/projection_reconcile.py` 投影一致性 | **1** | **真坏** | `3/6 项通过`；R1 `source_sha256` `f27a14091b2bd782… → 743dc62398311b02…`；R2 509 条条目权威规则已变；R4 2036 处治理字段未传导 `{owner:509, half_life_days:509, valid_until:509, effective_from:509}` |

**附加（不在这六道里）**：`l7/scripts/skill_conformance.py` 四方对账（skill 文本↔注册表↔层契约↔磁盘）
→ **退出码 0，红 0、黄 93**（C2 1 / C3 58 / C4 34）。**C7 红 0** —— 但 C7 有个单向缺陷，见 RR-3。

**他会话同一时刻的 ④ 读数（非本会话产物，仅作参照）**：`_chk-run-CHK-20261004-1118-AG/④-workflow_check.out`
报 `FAIL ② 权威库 l0~l6 未被改动 / FAIL ③ 前序产物哈希（45 项）/ FAIL ⑥ 文档可见性`，裁决 `FAIL`，`__EXIT=1`。
⚠ 该会话的 `exitcodes.txt` 把这六道**全部记成 `exit=0`** —— 它的 `run()` 把 `$?` 取在 `echo "__EXIT=$?"` **之后**，
所以 `exit=0` 不可信，真值在日志里的 `__EXIT=` 行。**拿那行当证据会判错。**

## 二、重点：registry ⇄ routes 对不上的地方

### RR-1｜13 个专项里 **12 个**在路由表里没有任何机读条目

- `kb/l7/registry/routes.yaml:3` 自述：「这份表回答一件事：**这句话该谁接**」。
- `routes:` 共 **11 条**（`:62-136`），`to` 去重 **11 个 id**。
- 以 `brand-*` 作 `to` 的**只有 1 条**：`:86 to: brand-content-review-agent`。
- 13 个 `brand-*` 的其余 12 个，全文只出现在 `frozen_expectation.dir_name_map`（`:177-190`）——
  那是**冻结用例的期望映射**，不是路由条目。
- 同一文件自相矛盾：`chains.review.members` 只列 **3 个**（`:43`），
  而紧邻的 `note` 说「**13 个 brand-*** 是**消费侧子能力 / 链内成员**」（`:45-46`）。
- `:192-194` 又说「这 65 条的期望接走者**就是 13 个 brand-* 本身**，不是 kb-review / kb-content-review」。

**后果**：拿「AI 生成披露该谁接」去查 routes.yaml，**查不到**。
能回答的只有散文：`kb/l7/skills/kb-review/SKILL.md:58-74`（§0 让位表，13 行）
与 `kb/l7/skills/kb-manage/SKILL.md:74-95`（§1.2，**逐行相同的第二份**）。

**两种读法（交人裁）**：
- 读法 A（真缺口）：routes.yaml 自称答「这句话该谁接」，却答不出 12/13 专项 ⇒ 要么补条目、要么改自述。
- 读法 B（设计如此）：宿主按 SKILL.md description 选 skill，routes.yaml 只是**事后对账表**、不是派发器 ⇒
  属「对账覆盖不全」，不是「路由缺失」。
- **哪种成立**：看 routes.yaml 有没有「本表是派发真源」这句话。实测：**没有**（`:8-15` 只说「静态真源」）。

### RR-2｜`brand-product-fact-curator`：登记了、装了，routes 与 layers 都不认识它

- `kb/l7/registry/skills.yaml:882-897`：`scope: 本项目` / **`status: 生产`** / `layer: "L3"` /
  10 条 `trigger_keywords` / `install_target: ~/.dsh/skills/`，且**实际已装**（`~/.dsh/skills/brand-product-fact-curator`）。
- `grep brand-product-fact-curator kb/l7/registry/routes.yaml kb/l7/registry/layers.yaml` → **0 命中**（两边都没有）。
- 计数口径差 **1**：routes.yaml 全文一律写「**13 个** brand-*」（`:23 :45 :171 :192`）、
  `dir_name_map` 13 键（`:177-190`）；而 `skills.yaml` 里 `brand-*` **共 14 个**。
- 更硬的一处：`kb/l7/skills/kb-manage/SKILL.md:41-60` 把它记为成员 #14、**`status: 规划`**，
  并总述「成员 11–14 是规划中的供给侧成员（`status: 规划`，`trigger_keywords` 留空 = **不参与路由**）」；
  而 `skills.yaml:882-897` 是 **`status: 生产` + 10 条触发词 + 已装**。**两处直接矛盾。**
  （同类：`kb-ingest-extractor` `skills.yaml:834-836`、`kb-media-extractor` `:850-852`、
  `kb-clause-extractor` `:866-868` —— 登记表全是 `status: 生产`；登记表 `scope=本项目` 里**没有一条 `规划`**。）

### RR-3｜C7「层 ↔ skill 双向一致」实为**单向**（闸门自身的缺口）

- 判据声明：`kb/l7/registry/layers.yaml:53`「判据在 `kb/l7/scripts/skill_conformance.py` 的 C7（层 ↔ skill 双向对账）」。
- 实现：`skill_conformance.py:108` 读 `layers.yaml` 的 `layers`；`:201-227` 的 C7 块**遍历层契约的 skill 清单**，
  检查对象是**登记表的 `layer` 字段**（`:226-227`）。**没有任何反向遍历**（按登记表的 `layer` 去层契约里找它）。
- 实测反向（本会话独立复算，脚本 `_chk-run-CHK-20261004-1130-REGISTRY-ROUTES/20-reverse-c7.py`）：
  - `kb-content-review`：登记表 `layer=L7`，`layers.yaml:539 skill: [kb-check]` 里**没有它**；
  - `brand-product-fact-curator`：登记表 `layer=L3`，`layers.yaml:238 skill: [kb-clause-extractor]` 里**没有它**。
- 结论：`skill_conformance` 本期 **红 0**，这两个不一致它**报不出来**。

### RR-4｜运行时产物里出现登记表不存在的名字，靠判据补丁兜住

- 赢家表 `_eval-kb-manage/results_alias/routes-winners_20261004-0327-SUB.txt:43-44` 写 `AI 溯源与权利审查`（**中间有空格**）。
- 登记名：`skills.yaml:752 dir_name: "AI溯源与权利审查"`（**无空格**）；装载位实目录
  `~/.dsh/skills/AI溯源与权利审查`（**无空格**，`ls` 实测）。
- 抹平机制：`routes_reconcile.py:135-139`（去空白装载名索引）+ `:160-162`（`canon` 归一）。
- ⇒ 闸门不报，但严格读：**赢家表这一侧的取值不是任何登记成员的 id、也不是任何 dir_name**。
  两边不是「对上」，是「被归一规则折上」。

### RR-5｜门③ 的输入产物全库不存在（长期状态）

- `kb-check/SKILL.md`（§1）规定产物名 = `kb/l7/reports/<RUN>-routes-winners.json`。
- 实测 `kb/l7/reports/` 下 `routes-winners` 命中 **0 个**；全库 `find` 只找到 `_eval-kb-manage/` 与
  备份目录下的历史赢家表。⇒ 门③ 现状只能 exit 2（缺输入）。
- 本次喂的是 `_eval-kb-manage/results_alias/routes-winners_20261004-0327-SUB.txt`（mtime **2026-10-04 03:24:57**，
  115 行；用例 = `~/Desktop/skill/内容治理中文 skill/_基线用例.json` 65 条）。
  结果：**exit 1**，①=5、④=0；逐条全轮命中 **60/65**（门槛 F1 ≥ 0.90）。
  不一致 **全在 `brand-ai-provenance-rights-review`**（I1–I5），抢走者 `NONE` 6 次 /
  `视频安全审查` 3 次 / `图片安全审查` 3 次 / `CLARIFY` 1 次。
- **口径红线**：这是 **03:24 那一刻**的运行时读数，**不是今天**的。
  要今天的数 ⇒ 按 `kb-manage` 的触发电测重出赢家表（本次未做）。

### RR-6｜「让位表在哪」的指路三处不一致

- `~/.dsh/AGENTS.md:163`：「按 kb-review 让位表（**见 `kb/l7/registry/routes.yaml`** —— 别在这儿抄第二份）」。
- 实测 `routes.yaml` 顶层键 = `meta / chains / routes / mutual_not_for / frozen_expectation / measured_20260929`
  —— **没有让位表**；它自己在 `:49` `:81` 说「见 **kb-review** 的让位表」。
- 让位表正文实测在 `kb/l7/skills/kb-review/SKILL.md:58-74`。
- 且它是**两份**：`kb-review/SKILL.md:58-74` 与 `kb-manage/SKILL.md:74-95` 逐行相同 ——
  违反 `skills.yaml:36-38` 自己写的「同一事实只写一处」。

## 三、失败项清单（对象 + 原因码 + 要人做什么 + 复开条件）

⚠ **原因码**：本批 registry ⇄ routes 的缺口在 `kb/l7/registry/failure-playbook.yaml` 里
**没有登记的原因码**（最接近的 `conformance.red`（`:232`）本期是绿、`gate_missing.*`（`:240`）不适用）。
按该文件 `:12` 的纪律「连兜底都没有，就说『没有登记的处置办法』——**不许现编**」，
下表**不造码**，只标「待登记」。

| 对象 | 原因码 | 要人做什么 | 复开条件 |
|---|---|---|---|
| RR-1 12/13 专项无路由条目 | **待登记** | routes.yaml 负责人裁定读法 A/B；选 A 则补 `routes[]` 条目或把 `chains.review.members` 补全；选 B 则改 `:3` 自述 | 选 A：routes.yaml 能对 13 个专项逐条给出 `to`；选 B：`:3` 不再声称答「这句话该谁接」，且 `:45-46` 与 `:43` 口径一致 |
| RR-2 brand-product-fact-curator 三处对不上 | **待登记** | ① `kb-manage/SKILL.md:60,74` 与 `skills.yaml:884` 谁为准（`规划` vs `生产`）；② 若为生产，补 routes.yaml / layers.yaml 条目；③ 13→14 的计数口径全文对齐 | `kb-manage` §1 与 `skills.yaml` 的 status / 触发词 / 计数三处一致 |
| RR-3 C7 单向 | **待登记** | 给 `skill_conformance.py:201-227` 补反向遍历（登记表 `layer=Lx` ⇒ 必须在 `layers.yaml` 该层 `skill:` 里，`layer="—"` 继续豁免），或把判据名从「双向」改成「单向」 | C7 能报出 `kb-content-review`(L7) 与 `brand-product-fact-curator`(L3) 两个反向不一致，或判据名与实际一致 |
| RR-4 赢家表空白变体 | **待登记** | 修产生赢家表的电测侧（`kb-manage` 触发电测），让它写登记表的规范名；或把「去空白归一」从补丁升级为登记在案的判据 | 赢家表取值 ⊆ 登记 id ∪ dir_name |
| RR-5 门③ 无输入 | **待登记** | 定一个产生 `<RUN>-routes-winners.json` 的常规动作并写进 `kb-check`/`kb-manage`；否则门③ 永远 exit 2 | `kb/l7/reports/` 下存在当期 `*-routes-winners.json`，门③ 不再以「缺输入」为常态 |
| RR-6 让位表指路不一致 | **待登记** | `~/.dsh/AGENTS.md:163` 的「见 routes.yaml」改为「见 kb-review/SKILL.md §0」；删掉 `kb-manage/SKILL.md:74-95` 那份重复 | 三处指向同一真源，且真源只有一份 |
| ⑥ R1/R2/R4 投影漂移 | `gate_red.projection_reconcile`（已登记 `:160`） | 按闸门修法：重跑 `kb/.work/gen-host-library.py` 到 staging 后回填；R4 先确认生成器是否从规则行读那 4 个字段 | ⑥ 复跑 6/6 通过 |
| ④ 链路收口 | `gate_red.workflow_check`（已登记 `:142`） | 本会话未跑（并发回避）；要结论请单独开一次写档 | 单独跑一次 `l8/workflow_check.py <RUN>` 并接受写 `kb/l8/` |

## 四、本表的边界（没做的事，明确写出来）

1. **门④ 未跑** —— 无干跑档、会写 `kb/l8/` 并落 ingest 探针，且并发会话正在跑同一道。本表不代它下结论。
2. **门③ 的 5 条不一致是 03:24 的历史读数**，不是今天的；未重跑触发电测。
3. **rr-2 的「生产 vs 规划」我只核了登记表与 kb-manage 正文两处**；
   `status` 该是哪个属**人的裁定**，本表不判。
4. **`_chk-run-CHK-20261004-1118-AG/exitcodes.txt` 的 `exit=0` 不可采信**（harness 把 `$?` 取在 echo 之后）。
   该会话的真值在日志文件的 `__EXIT=` 行：③=2、④=1、⑥=1。
