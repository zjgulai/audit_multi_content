# 体检表 · registry 自检 ⇄ layer 契约 ⇄ 路由对账（三闸门一次跑）

- run_id：`CHK-20261004-0916-REGISTRY-LAYER-ROUTES` ｜ 实测窗口 2026-10-04 09:16–09:18 CST
- 库根（权威库真身）：`/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理`
- 档位：**体检档**（`kb-check`，只报不改）；范围**只要这三道**（① 登记表自检 / ② 层契约 / ③ 路由对账）
- 写盘：仅本文件 ＋ 原始输出目录 `_chk-run-CHK-20261004-0916-REGISTRY-LAYER-ROUTES/`（6 个 txt）
- 并发：09:16 前后 `kb/l7/runs/`、`kb/l7/reports/`、`kb/l8/` 另有会话在写（10 分钟内 21 个文件被改）
  ⇒ **未认领、未写 kb/l0…l7 数据、未碰任何锁**；本单三个脚本均为只读
- 未跑：④ 链路收口 / ⑤ 信封 / ⑥ 投影（**不在本单范围**；④⑥ 无干跑档会写盘）

## 〇 前提审查（两条，先说）

1. **门③ ④ 节 = 0 不等于「registry ⇄ routes 对得上」**。`routes_reconcile.py` 的 ④ 节只做**单向核**
   （只核「`to`/`members`/`entry` 里的 id 在不在登记表」，不核「登记表里该被期望的成员有没有 route」）
   ⇒ 这个方向**结构上永远报 0**。本单已独立复现反方向的空洞（见二 · R1）。
2. **「三件事」实际是「三张表」**：`skills.yaml`（有哪些成员）／`layers.yaml`（链路怎么跑）／`routes.yaml`（这句话该谁接）。
   本单 ①② 都在查前两张，③ 才查第三张 —— 缺任何一张都整块漏。

## 一 闸门实测（退出码 = 实测值，原始输出见 `_chk-run-…/`）

| # | 闸门 | 命令 | 退出码 | 判定 |
|---|---|---|---|---|
| ⓪ | preflight | `python3 .dsh/skills/kb-check/scripts/preflight.py` | **0** | 前置齐；六道脚本全在；**明示赢家表输入缺** |
| ① | 登记表自检 | `sh kb/kbpy l7/scripts/skills_check.py` | **0** | **过** · 五类 `1=0 2=0 3=0 4=0 5=0` · 71 行（本项目 52 / 宿主通用 19）· 装载位 59 目录 · 本项目 40/40 已装 |
| ② | 层契约 | `sh kb/kbpy l7/scripts/layers_check.py` | **0** | **过** · 六类 `1=0 2=0 3=0 4=0 5=0 6=0` · 8 层齐 · DAG 非线形（L2/L3/L5/L6 多上游，L7 五上游） |
| ③-a | 路由对账（**契约路径**） | `routes_reconcile.py kb/l7/reports/<RUN>-routes-winners.json` | **2** | **缺输入 —— 这道没跑成**（不是"65 条全不一致"） |
| ③-b | 路由对账（strict，借表） | `routes_reconcile.py _eval-kb-manage/results_alias/routes-winners_20261004-0327-SUB.txt` | **1** | 全轮命中 **0/65** —— 口径产物（中文名未折回），见三 · C1 |
| ③-c | 路由对账（`--alias`，借表） | 同上 ＋ `--alias` | **1** | 全轮命中 **60/65 = 0.923**（门槛 0.90 过）· ①=5 ②=5 **④=0** · 5 条全落在 `brand-ai-provenance-rights-review` |

## 二 缺的那道：③ 的契约输入不存在（说清"为什么缺"）

**结论**：门③ **按契约原样跑恒 exit 2**，本单只能借一张**非契约位置**的赢家表出旁证。

**为什么缺 —— 三条，按可核对的顺序：**

1. **契约要的是运行时产物，不是静态资产。** `references/gates.md:33` 要求
   `kb/l7/reports/<RUN>-routes-winners.json`；它是「每条 prompt 每轮实际被谁接走」的**盲测结果**。
2. **全库没有生产者。** 本单实测 `find . -name "*routes-winners*"` 在库根范围内**只命中 1 个**，
   且**不在契约位置**：`_eval-kb-manage/results_alias/routes-winners_20261004-0327-SUB.txt`
   （115 行，mtime 2026-10-04 03:24:57）。`kb/l7/reports/` 下 winners 文件数 = **0**。
3. **要今天的数据必须先跑触发电测**（按 `kb-manage`），本单**不跑**：那是评测动作、不是体检动作，
   且与 09:16 正在写库的另一会话会撞车。

**为什么不能拿 ③-b/③-c 顶替**（诚实标注）：借来的表有**两处口径差**，都不是「数据坏」——
· 位置非契约：它在 `_eval-kb-manage/`（评测产物目录），不是 `kb/l7/reports/`；
· 时间滞后：03:24 生成，**早于**今日 08:10 的修复轮（`_repair-run-20261004-0810/`）与 09:0x 的并发批。

**判定**：③ 在契约口径下记账为 **未判定（缺输入）**，**不得报绿、也不得报红**。

## 三 对不上的地方（本单独立复现，逐条给证据）

### R1 · 门③ ④ 节 = 0 是**单向**的：16 个「生产」成员在 `routes.yaml` 里 0 命中

| id | routes.yaml 命中 |
|---|---|
| `kb-ingest-extractor`（`layers.yaml` L1/L2 层主） | **0** |
| `kb-media-extractor`（L1 层主） | **0** |
| `kb-clause-extractor`（L3 层主） | **0** |
| `brand-product-fact-curator`（登记 生产、已装） | **0** |

链条断裂在**方向**上：`routes.yaml` 只登记「从哪个入口进」，不登记「链路里的层主由谁接」；
而 `layers.yaml:154/201/238` 明确把这三个层主写成层 `skill:`。⇒ **同一事实两张表都只写一半。**

要人做什么：在 `routes.yaml` 给这 16 个补 route / 链成员身份，或把 `routes.yaml:43-46` 的措辞
改成与数据一致（"不由本表路由，归属见 `kb-review` 让位表"）。复开条件：这 16 个 id 命中数全 ≥1。

### R2 · 计数对不上：`routes.yaml` 6 处写「13 个 brand-*」，登记表实有 **14**

```
grep -c "13 个 brand" kb/l7/registry/routes.yaml   → 6
grep -c "^  - id: brand-" kb/l7/registry/skills.yaml → 14
```
第 14 个是 `brand-product-fact-curator`（英文目录名、无 `dir_name`）⇒ 不进 `dir_name_map`、
不进冻结用例集、**路由从未被任何闸门核过**。要人做什么：**口径裁定**（补第 14 条 route，还是改计数口径）。

### R3 · 表里声明了、脚本从不读（**死键**，门③ 自己也抓不到）

```
grep -rn "frozen_expectation" --include=*.py --include=*.sh .  → 0（脚本侧）
grep -rn "mutual_not_for"     --include=*.py --include=*.sh .  → 0（脚本侧）
```
`routes.yaml:176` 写着「对账器 `--alias` 口径**用这张表**归一」，`routes.yaml:138` 写着「互斥点名
**硬约束，对账器会核**」—— **两句都不成立**：对账器用的是自己硬编码的 `ALIAS`（`:43-64`）与 7 对互斥（`:327-332`）。
⇒ 改 `routes.yaml` 这两个键**对闸门零影响**。要人做什么：让脚本读它，或删掉这两句不成立的声明。

### R4 · ③-c 的 5 条红**不是表间问题，是路由质量问题**（引用时别混）

`--alias` 下 5 条全红（I1–I5）**全部**期望 `brand-ai-provenance-rights-review`：

```
I1 NONE→视频安全审查×3 ｜ I2 NONE/图片安全审查/NONE ｜ I3 NONE/AI 溯源与权利审查/NONE
I4 AI 溯源与权利审查/NONE/NONE ｜ I5 图片安全审查/图片安全审查/CLARIFY
被抢走：NONE 6 次 · 图片安全审查 3 · 视频安全审查 3 · CLARIFY 1
```
`routes.yaml:238-255` 已把这一组登记为**冻结用例集自身歧义**（I1↔G3、I5↔F5 近重复，I2 欠模态），
并写明"不再继续改用例、也不再调 description"。⇒ **属已知未决的路由质量问题，不是 registry↔routes 表间不一致。**

## 四 三个脚本各自的"零"该怎么读

| 脚本 | 它的 0 意味着 | **不**意味着 |
|---|---|---|
| ① `skills_check.py` | 五类问题全 0：应装未装 / 未登记 / 副本不一致 / 依赖缺失 / 自测缺失 | 不代表成员路由对；不代表 selftest 都登记了（本单 **62 条未登记 selftest**，归类「不算错误」） |
| ② `layers_check.py` | 8 层齐、字段齐、引擎路径存在、DAG 合法、"无干跑档清单"可见 | 不代表各层真的跑过（本单未跑任何层） |
| ③ `routes_reconcile.py` | **只有 ④ 节**表示「路由表引用的 id 都在登记表里」 | ④=0 **不等于** registry↔routes 对得上（仅单向核，见 R1） |

## 五 口径纪律（引用本单时别走样）

- 门③ **exit 2 = 缺输入**；**exit 1 = 真有不一致**（或 strict 口径产物）。**两者不是一回事。**
- ③-b 的 `0/65` 是**口径产物**（strict 模式下中文装载名不折回 `brand-*`），**不是 65 条路由全错**；
  同表 `--alias` 即 `60/65`。
- ① ② 的 `0` 是**实测 0**，不是"没扫到"；两者都实扫（① 装载位 59 目录；② 8 层 12 字段）。
- 本单所有数字是 **09:16–09:18 的只读快照**；期间另有会话在写，复跑数字可能变。
- 本单**未跑** ④⑤⑥，**未做**任何修复（修复走 `kb-repair`）。

## 六 复现命令（逐条可跑）

```bash
cd "/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理"
python3 .dsh/skills/kb-check/scripts/preflight.py                       # 0
sh kb/kbpy l7/scripts/skills_check.py                                   # ① 0
sh kb/kbpy l7/scripts/layers_check.py                                   # ② 0
sh kb/kbpy l7/scripts/routes_reconcile.py kb/l7/reports/X-routes-winners.json   # ③ 2（缺输入，恒）
W=_eval-kb-manage/results_alias/routes-winners_20261004-0327-SUB.txt
sh kb/kbpy l7/scripts/routes_reconcile.py "$W"                          # ③ 1（strict 0/65）
sh kb/kbpy l7/scripts/routes_reconcile.py "$W" --alias                  # ③ 1（alias 60/65，④=0）
for k in kb-ingest-extractor kb-media-extractor kb-clause-extractor brand-product-fact-curator; do
  echo "$k $(grep -c -- "$k" kb/l7/registry/routes.yaml)"; done          # 全 0
grep -c "^  - id: brand-" kb/l7/registry/skills.yaml                    # 14
grep -c "13 个 brand" kb/l7/registry/routes.yaml                        # 6
grep -rn "frozen_expectation\|mutual_not_for" --include=*.py --include=*.sh . | grep -v _chk-run  # 0
```
