# 体检表 · CHK-20261004-1209-REG-LAY-ROUTES

**范围**：用户点名的三道 —— ① 登记表自检 / ② 层契约 / ③ 路由对账
**档位**：`kb-check` **体检档的子集**（3 / 6 道），**不是**评审链 L7 驱动循环档
**库根（cwd）**：`/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理`
**执行时间**：2026-10-04 12:02 – 12:12（时间戳取自命令实测）
**纪律**：**只报不改** —— 未修数据、未加 `--apply`、未带 `--write-gate`、未删锁/副本/认领、未跑会写盘的 ④⑥、未写 `kb/` 任何文件
**原始输出**：`_chk-run-CHK-20261004-1209-REG-LAY-ROUTES/`（6 个文件，sha256 见 §4）
**来源标注**：`【实测】`＝本会话亲自跑出的输出；`【引用】`＝读库内既有登记文件

---

## 1. 正表

| # | 闸门 | 命令（cwd = 库根） | 退出码 | 结论 | 证据 |
|---|---|---|---|---|---|
| ① | 登记表自检 | `sh kb/kbpy l7/scripts/skills_check.py` | **0** | ✅ **过** | 五类问题 `1=0 2=0 3=0 4=0 5=0 ｜合计 0`；登记表 `kb/l7/registry/skills.yaml` 71 行（本项目 52 / 宿主通用 19）；本项目要用 40 / 已装 40 / 还差 0；装载位扫到 59 个目录；`status=参考` 11 个（只参考不安装）；宿主通用 19 个（不参与"应装未装"）；未登记 selftest 62 条（工具自注**单独归类、不算错误**）【实测】 |
| ② | 层契约自检 | `sh kb/kbpy l7/scripts/layers_check.py` | **0** | ✅ **过** | 契约表 `kb/l7/registry/layers.yaml`；层数 8（L0…L7、无重复）；六类问题 `1=0 2=0 3=0 4=0 5=0 6=0 ｜合计 0`；必填字段 12 个齐全非空、`python=${KB_PYTHON}`、`envelope` 取值合法；引擎路径存在性 0 条；DAG 非线形（`L7 ← L0、L3、L4、L5、L6`）；无干跑档清单 0 条【实测】 |
| ③-a | 路由对账（**契约输入路径**） | `sh kb/kbpy l7/scripts/routes_reconcile.py kb/l7/reports/<RUN>-routes-winners.json` | **2** | ⚪ **未判定（缺输入）**，**不是**"路由表全错" | 脚本原话：「环境错：赢家表不存在 …」「赢家表是**触发评测的运行时产物**，不是静态资产；缺输入时本闸门**不得报绿**，也不得静默按『全不一致』跑」；预检查（12:02）已确定性预告同一结论【实测】 |
| ③-b | 路由对账（**替代读数**：2026-10-04 03:24 旧赢家表 · `--alias`） | `… routes_reconcile.py _eval-kb-manage/results_alias/routes-winners_20261004-0327-SUB.txt --alias` | **1** | 🔶 **红 5 条，已登记为用例集缺陷（非 skill 缺陷）** | 用例 65 条、赢家表 115 条；逐条全轮命中 **60/65（0.923）**；四节问题 `①=5 ④=0`；5 条**全在 `brand-ai-provenance-rights-review`（I1–I5）**；抢走者计数 `NONE` 6 轮 / `视频安全审查` 3 / `图片安全审查` 3 / `CLARIFY` 1；其余 **12 个成员均 5/5 条 × 15/15 轮**；④ 路由表静态自检 **0 条**（id 存在性、互斥点名、两条链 `not_for` 互指均成立）【实测】＋根因【引用】`kb/l7/registry/routes.yaml:238 measured_20260929.known_conflict` |
| ③-c | 路由对账（同一旧赢家表 · **strict**） | `… routes_reconcile.py …（不带 --alias）` | **1** | ⚠️ **口径不匹配，不得读成"65 条全错"** | 逐条全轮命中 **0/65**、问题 `①=65`；原因：赢家表记**中文装载名**、用例期望侧是 `brand-*` **登记 id**，strict 逐字相等必然全不中 ⇒ 只有 `--alias` 是可比口径【实测】 |

**读 ③-b 前必须同时读**：`routes_reconcile.py` 的别名归一**已含空白变体折回**（`:122-151`，`AI 溯源与权利审查`→`AI溯源与权利审查`），
故这 5 条**不是**空格变体导致的判据缺陷；且判据口径是「三轮全一致且等于期望」，`I3/I4` 的失分来自有一轮 `NONE`。

---

## 2. 缺哪道、为什么缺

### 2.1 你点的三件里，③ **缺今日权威读数**（缺的是**输入**，不是闸门）

| 缺什么 | 为什么缺（【实测】核过，不是转述） | 谁能补 |
|---|---|---|
| `kb/l7/reports/<RUN>-routes-winners.json` | 全库**没有任何脚本会生成它**：`grep -rIn "routes-winners" kb/l7/scripts kb/l8 tools .dsh/skills` 只命中**消费方**（`routes_reconcile.py` 读、`kb-check` 文档写、`preflight.py` 查存在性）**与 `kb-manage/SKILL.md:126` 的命令注释**，**无一处写文件**；唯一现存的赢家表都是评测目录里的历史产物 ⇒ 契约路径缺失 ⇒ `exit 2` | 按 `kb-manage` 的**触发电测**真跑一遍（65 条 × 3 轮、每轮新 agent），产物按契约名落进 `kb/l7/reports/`，再重跑门③ |
| 现存的**最新**赢家表 | `_eval-kb-manage/results_alias/routes-winners_20261004-0327-SUB.txt`，mtime **2026-10-04 03:24:57**，距本次读数约 **8 小时 45 分** ⇒ ③-b 是**替代读数**，不是今日读数 | 同上 |

- `kb-check` 是**只报不改**，**不替人跑触发电测**（那是 `kb-manage` 的活，且要真跑 195 次判定）。
- 现存赢家表全清单（mtime 倒序）：`_eval-kb-manage/results_alias/routes-winners_20261004-0327-SUB.txt`（03:24）、
  `_eval-kb-manage/blind_v2.winners.txt`（09-29 19:58）、`blind_after_r4.winners.txt`（09-29 19:32）、
  `kb/l7/_backups/kb-repair-20261004-0225-routes-alias/blind_after_r4.winners.txt`（09-29 19:32）、`blind_after_r3`（19:01）、`blind_after`（18:52）、`blind_before_v2`（18:37）。**均不在契约路径。**

### 2.2 六道闸门里，这次**没跑**的另外三道（你没点名）

| # | 闸门 | 跑了吗 | 为什么没跑 |
|---|---|---|---|
| ④ | 链路收口核验 | ❌ | **会写盘**：`l8/workflow_check.py` 无干跑档，不加参数也写 `kb/l8/workflow_check_<RUN>.json` ⇒ 须先声明再跑；本次未获授权 |
| ⑤ | 信封闸门 | ❌ | 未点名（`tools/envelope_gate.py` 覆盖 `.py/.txt/.md`；`l8/envelope_census.py` **只扫 `.md`**，不可互相替代） |
| ⑥ | 投影一致性 | ❌ | 未点名；`preflight.py` 把 ⑥ 列入「**无干跑档**」清单，按严的一侧处置 |

> 本表**不构成六道闸门的体检结论**；③ 也**没有今日权威读数**。

---

## 3. 失败项清单（对象 ＋ 原因码 ＋ 要人做什么 ＋ 复开条件）

| 对象 | 原因码 | 要人做什么 | 复开条件 |
|---|---|---|---|
| 门③ 输入 | `MISSING_INPUT` | 按 `kb-manage` 触发电测生成 `<RUN>-routes-winners.json` 放进 `kb/l7/reports/` | 文件存在且可解析 ⇒ 重跑门③ |
| `brand-ai-provenance-rights-review`（I1–I5） | `KNOWN_CASE_CONFLICT`（已登记 `routes.yaml:238`） | 改**用例集**：合并 I1/G3、解 I5↔F5 近重复、给 I2 补模态；**不建议再改 description**（库内已判定为过拟合 judge） | 改完后复测该成员 F1 ≥ 0.90 且三轮一致 |

---

## 4. 原始输出 sha256（`_chk-run-CHK-20261004-1209-REG-LAY-ROUTES/`）

```
b486b6bb009008c72cbb2869b8268a3aeb3ba711bd7c726d063720b40d3af2a4  00-preflight.txt
ee549b71a4c90ce72aa06a9a7b6da4cc6a879a84d1b779c54cfffbc912706639  01-skills_check.txt
f7aae579bca0f92f38b99662e309f4a59fb7427276f3761641a74d533a4847b9  02-layers_check.txt
207218d28b58c4692599baba476abef8f47a7c1049fb3a033b26a0cd7114fd10  03a-nofile.txt
6d299f68a4c0e2493f6ca04aa5f4460ad0289e3a098980ecd56050f8a6125bff  03b-alias.txt
50c8e0b63d46053da95692d77a4bcebd622d49dd99ea8f2f9641288506afddaa  03c-strict.txt
```

## 5. 并发与环境（读数的前提）

- 本窗口内**有另一路会话在写同一个库**：`kb/l7/runs/` 有 11:33–12:07 的新文件（最新 `20261004-120747.json`）、
  `kb/l7/reports/CHK-20261004-1203-SUB-health.md`、`kb/l7/reports/CHK-20261004-1158-health.md`；
  本会话另见工作区 `_chk-run-CHK-20261004-1210-REG-LAY-ROUTES/`（12:02–12:07 落盘）。
- `kb/.work/.kb.lock` **不存在**；`kb_loop_claim.py status` = **无认领**。
- ⇒ ①② 是**活库快照**，不是冻结基线；要可复现的读数，需在无并发写入的窗口重跑（或先 `claim`）。
