# 体检表 · registry ⇄ routes 对账（对峙用）

- run_id：`CHK-20261004-0958-REGISTRY-ROUTES` ｜ 实测窗口 2026-10-04 09:55–10:00 CST
- 库根（权威库真身）：`/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理`
- 档位：**体检档**（`kb-check`）。重点 = `skills.yaml`（有哪些成员）⇄ `routes.yaml`（这句话该谁接）⇄ `layers.yaml`（链路怎么跑）
- 写盘声明：④ 链路收口 **未跑**（无干跑档、无参数也写 `kb/l8/workflow_check_<RUN>.json`，见 `references/gates.md:51-53`）。
  本单只跑只读项 ①②③⑤⑥，**不写 kb/ 任何数据目录**，只写本文件。
- 并发声明：09:51–09:53 期间另有会话在写 `kb/l7/runs/`、`kb/l4/runs/`、`kb/view/_meta/query-log.ndjson`。
  `kb/.work/.kb.lock` 实测**不存在**（`ls kb/.work/.kb.lock` → No such file）；未认领、未碰任何锁。

## 〇 前提审查（先说三条，其中一条是提问本身的前提有误）

1. **「registry 和 routes 这两块」这个切法在本库不成立。** `routes.yaml` **就住在 `kb/l7/registry/` 目录里**
   （自述见 `routes.yaml:18 file: kb/l7/registry/routes.yaml`）。按「目录 vs 文件」理解这两个词，
   没有可对账的两个对象。有意义的对账是 `routes.yaml:3-6` 自己定的三张表之间：谁在册 / 谁接哪句话 / 链路怎么跑。
2. **本主题今天已被查过三轮并留档**：`kb/l7/reports/CHK-20261004-0300-REGISTRY-ROUTES-health.md`、
   `CHK-20261004-0815-REGISTRY-ROUTES-health.md`、`CHK-20261004-0911-REGISTRY-ROUTES-health.md`（后者 143 行，B1–B4）。
   本单是**独立复跑**：我的 F1/F2/F4 与 0911 的 B3/B2 结论一致、证据行号为我本轮自查。
   ⇒ 对峙时对方能主张的是「**已知未修**」，不能主张「没发现」。这一点必须先讲，否则一上桌就被打掉。
3. **本单未判定「路由质量」**。`--alias` 下仍红的 I1–I5 属冻结用例集自身歧义（`routes.yaml:238-255` 已登记），
   是路由质量问题、**不是 registry↔routes 表间问题**，引用时不要混（`CHK-20261004-0911` §五 同口径）。

## 一 闸门实测（退出码为实测值）

| # | 闸门 | 命令 | 退出码 | 判定 |
|---|---|---|---|---|
| ⓪ | preflight | `python3 .dsh/skills/kb-check/scripts/preflight.py` | 0 | 前置齐；**赢家表输入缺**（门③ 必 exit 2） |
| ① | 登记表自检 | `sh kb/kbpy l7/scripts/skills_check.py` | **0** | 过 · 五类 `1=0 2=0 3=0 4=0 5=0` · 71 行（本项目 52 / 宿主通用 19）· 装载位 59 目录 |
| ② | 层契约 | `sh kb/kbpy l7/scripts/layers_check.py` | **0** | 过 · 六类 0 · 8 层齐 · DAG 非线形 |
| ③ | 路由对账（契约路径） | `routes_reconcile.py kb/l7/reports/<RUN>-routes-winners.json` | **2** | **缺输入**（≠「65 条全不一致」，见 `references/gotchas.md:20-24`） |
| ④ | 链路收口 | —— | **未跑** | 无干跑档、会写 `kb/l8/`；本单不跑，避免与并发会话抢写 |
| ⑤ | 信封闸门 | `python3 tools/envelope_gate.py` | **0** | 1951 文件 · 信封态 **0** · 两读者一致 |
| ⑥ | 投影一致性 | `sh kb/kbpy l8/projection_reconcile.py` | **1** | 3/6 通过；漂移 R1/R2/R4（与 registry↔routes 无关，单列） |

## 二 registry ⇄ routes 对不上的地方（逐条：行号 + 原文 + 复现）

### F1 · 表声称「对账器用这张表」，对账器**从不读它** —— `dir_name_map` 是死键

**原文（`routes.yaml:176`）**：

```
  #: 对账器 kb/l7/scripts/routes_reconcile.py 的 --alias 口径用这张表把两边归一。
  dir_name_map:            # ← routes.yaml:177，13 行映射，:178-190
```

**实测不成立**：

```bash
grep -rn "frozen_expectation" --include=*.py .   # 0 命中
grep -rn "dir_name_map"      --include=*.py .   # 0 命中
```

对账器真正用的归一来源是**另外两处**：

- `kb/l7/scripts/routes_reconcile.py:43-63` —— **硬编码** `ALIAS` 表（14 行，含 1 个遗留别名 `内容审查总控旧`）
- `kb/l7/scripts/routes_reconcile.py:243-248` —— 门④ 用 `skills.yaml` 的 `dir_name` 字段建 `dir_to_id`

⇒ **同一事实（登记 id → 中文装载名）在 4 个文件里各写一份**：

| # | 位置 | 行号 | 行数 |
|---|---|---|---|
| 1 | `kb/l7/registry/skills.yaml` `dir_name:` | 615 / 632 / 649 / 666 / 684 / 701 / 712 / 735 / 752 / 769 / 786 / 803 / 820 | 13 |
| 2 | `kb/l7/registry/routes.yaml` `frozen_expectation.dir_name_map` | 177–190 | 13 |
| 3 | `kb/l7/scripts/routes_reconcile.py` `ALIAS` | 43–63 | **14** |
| 4 | `_eval-kb-manage/kb_routes_score.py` | 35–49 | **14** |

**后果**：改 `routes.yaml:178-190` 那张表，对闸门**零影响**（没人读）；两张 14 行表才是实际生效的口径。
**落地差异**：13 个 brand-* 的映射四份一致（我逐条比对过），差异只在第 14 行（遗留别名 `内容审查总控旧`）——
它只存在于 #3/#4，`routes.yaml` 与 `skills.yaml` 都没有。

**要人做什么**：二选一 ——（a）让对账器真去读 `routes.yaml` 这张表，（b）把 `routes.yaml:176` 那句删掉/改写成
「本键仅供参考，实际口径在 `routes_reconcile.py:ALIAS`」。
**复开条件**：脚本侧出现对 `dir_name_map` 的真实读取，或 `:176` 的声明被删除/改写。

### F2 · 表声明「对账器会核」，第 1 组**从不被核** —— `mutual_not_for` 漏核

**原文（`routes.yaml:138`）**：`# ───── 互斥点名（硬约束，对账器会核）`
表里共 **7 组**（`:148` / `:154` / `:156` / `:158` / `:160` / `:162` / `:164`）。

**对账器硬编码 7 对（`routes_reconcile.py:327-332`）**：

```
327:     checks = [
328:         ("kb-pipeline", "kb-l0-feishu"), ("kb-l0-feishu", "kb-pipeline"),
329:         ("kb-l0-feishu", "kb-review"), ("kb-pipeline", "kb-review"),
330:         ("kb-pipeline", "kb-canonical-lookup"), ("kb-pipeline", "kb-p0-check"),
331:         ("kb-pipeline", "kb-recall"),
332:     ]
```

**不含 `routes.yaml:148` 那一组**：

```
148:   - pair: ["文案合规审查", "视频安全审查"]
```

```bash
grep -rn "mutual_not_for" --include=*.py .    # 0 命中
```

⇒ 表里第 1 组是**死规则**：写在「硬约束」标题下，从不被核；**再加第 8 组也不会被发现**。

**附带的口径不一致（同一个块内两种命名）**：`:148` 用**中文装载名**，`:154-164` 用**登记 id**。
而 `routes.yaml:11` 的口径只约束 `to` / `members`（「必须是 skills.yaml 里登记过的成员」），**不约束 `pair`**。
实测：`routes.yaml` 点名的 25 个 id 里，**2 个不在 `skills.yaml`** —— 就是 `文案合规审查`、`视频安全审查`。
（它们是真装载目录名，不是错名；问题在**块内命名不统一**，任何按 id 校的脚本都会把它俩判成"未登记"。）

**要人做什么**：二选一 ——（a）对账器读 `mutual_not_for` 逐组核（表即判据），（b）删掉 `:138` 的「对账器会核」，
并把 `:148` 改写成登记 id + `dir_name` 两写法之一，与 `:154-164` 统一。
**复开条件**：脚本侧出现对 `mutual_not_for` 的读取，或 `:138` 声明被删、`:148` 命名被统一。

### F3 · 门④ **单向核**：登记表里「该被路由的成员」有没有 route，永远报 0

**对账器只核一个方向（`routes_reconcile.py:283-298`）**：`to` / `members` / `entry` ∈ 登记表。
不核反方向（登记表成员 → 有没有 route）⇒ 这个方向永远是 0，**不能拿「④ = 0」当"对得上"的证据**。

**我实测的两个口径（差别很大，报数时必须带口径）**：

- **口径 A（只算 `to` / `chains.members` / `chains.entry`）**：
  `skills.yaml` 里 `scope=本项目 且 status=生产` 共 **40** 个，其中 **17** 个在 `routes.yaml` **0 命中**。
  但 17 里有 13 个是 `root-skills-*`(8) + `lark-*`(5) —— 它们 scope 虽写「本项目」，**不属本库路由范围**，
  属口径噪声。**剔掉后真正要主张的是 4 个**：
  - `kb-ingest-extractor` —— `layers.yaml:154`(L1) / `:201`(L2) 逐层认定的**层主**，routes 0 命中
  - `kb-media-extractor` —— `layers.yaml:154`(L1) 层主，routes 0 命中
  - `kb-clause-extractor` —— `layers.yaml:238`(L3) 层主，routes 0 命中
  - `brand-product-fact-curator` —— `skills.yaml:882`，生产、已装；**无 `dir_name`**；不在 `dir_name_map`；routes 0 命中
- **口径 B（把 `dir_name_map` 也算"有身份"）**：13 个 brand-* 有身份，剩的仍是上面那 **4** 个。

**相关原文**：

```
routes.yaml:35   members: [kb-pipeline, kb-l0-feishu, kb-canonical-lookup, kb-p0-check, kb-recall, kb-check, kb-repair]  ← 7 个，无 L1/L2/L3 层主
routes.yaml:43   members: [kb-review, kb-content-review, brand-content-review-agent]                                     ← 只 3 个
routes.yaml:45       13 个 brand-* 是**消费侧子能力 / 链内成员**，不单独对外当入口；
routes.yaml:81               "已能识别专项时交给 13 个 brand-*（见 kb-review 的让位表）",
```

- `:45` 说那 13 个**是链内成员**，可 `:43` 的 `members` 只列了 3 个、`brand-*` 只出现 1 个
  ⇒ **同一张表相邻两行的表与注不一致**。
- 12 个专项的真实归属写在**另一个文件**：`kb/l7/skills/kb-review/SKILL.md:58-74`（让位表，表体 13 行）；
  `routes.yaml:81` 只是**指向**它，未逐条登记。

**复现**：

```bash
grep -c kb-ingest-extractor     kb/l7/registry/routes.yaml   # 0
grep -c kb-media-extractor      kb/l7/registry/routes.yaml   # 0
grep -c kb-clause-extractor     kb/l7/registry/routes.yaml   # 0
grep -c brand-product-fact-curator kb/l7/registry/routes.yaml # 0
```

**要人做什么**：要么给这 4 个（或含 12 个专项）在 `routes.yaml` 补 route/链成员身份，
要么把 `:43`/`:45` 改成与数据一致（「不由本表路由，归属见 `kb-review` 让位表」）。

### F4 · 计数对不上：`routes.yaml` 6 处写「13 个 brand-*」，登记表实有 **14** 个

```
routes.yaml 写「13 个 brand-*」的行：23 / 45 / 81 / 171 / 192 / 205
skills.yaml 实有 `- id: brand-` 的 14 行：608 625 642 659 677 694 711 728 745 762 779 796 813 882
```

第 14 个 = `brand-product-fact-curator`（`skills.yaml:882`）：`scope=本项目`、`status=生产`、
装载目录名是**英文**（`~/.dsh/skills/brand-product-fact-curator`，与另外 13 个中文名不成体系）、
**无 `dir_name` 字段**、不在 `dir_name_map`（13 条，`routes.yaml:177-190`）、`routes.yaml` 全文 **0 命中**。

**后果**：它不进冻结用例集（13 × 5 = 65 条的期望成员表）⇒ **它的路由从未被任何闸门核过**。

**同一处滞后**：`skills.yaml:1105` 的块注释仍写「家族成员共 **14 个** …… 13 个 brand-* 是消费侧子能力……
不计入这 14 个」；`routes.yaml:46` 写「不计入 kb-manage 的 **14** 个成员」—— 两处 14 指的是不同集合，容易读串。

**要人做什么**：这是**口径裁定**不是补数据 —— 定它是「第 14 个专项」（补 route + `dir_name` + 用例）
还是「链内子能力」（改计数口径）。
**复开条件**：`routes.yaml` 的 brand-* 计数 == `skills.yaml` 的 14，或 `skills.yaml:882` 的 status 改成非生产并写明它不对外路由。

### F5 · 门③ 的契约输入**没有生产者**（最容易误读的一条，单列）

- 契约命令在 `references/gates.md:33`：`routes_reconcile.py kb/l7/reports/<RUN>-routes-winners.json`
- 实测 `kb/l7/reports/` 下 **0 个** winners 文件 ⇒ 按契约原样跑**恒 exit 2**（我实测 exit 2）
- **exit 2 = 缺输入**，**exit 1 = 真有不一致**；两者不许混说（`references/gotchas.md:20-24`，
  即 2026-10-03 修掉的那次「0 条 ⇒ 65 条全不一致 ⇒ exit 1」静默降级）

**要人做什么**：要么按 `kb-manage` 的触发电测重新生成赢家表并**放进** `kb/l7/reports/`，
要么把 `references/gates.md:33` 的契约路径改成一个真有生产者的位置。

### 非发现（我核过、**不要**拿去主张，否则会被打回）

- `layers.yaml:539` `skill: [kb-check]`（L7 的 skill）vs `skills.yaml:1144` `layer: "—"` ——
  **不是对不上**：`layers.yaml:541-543` 自己写明「`kb-check` 是跨层统一闸门（注册表 layer 记「—」），
  不是 L7 的层主，所以『层 ↔ skill 双向一致』判据对它豁免」。这条已被机制解释，主张它会失分。
- `skills.yaml:127` `kb-content-review` 的 `layer: L7`，而 `layers.yaml:539` 的 L7 skill 是 `kb-check` ——
  两处口径不同但**不构成矛盾**（前者是"落在哪一层"，后者是"由谁执行"）。**属待确认**，不建议当硬冲突主张。
- 装载位目录名本身**全部存在**：13 个 `dir_name_map` 目标目录我逐个 `ls` 过，13/13 命中；
  11 个 `routes[].to` 的目标目录也 11/11 命中（含中文名的 `内容审查总控`）⇒ **"改成中文后选不到"这件事本轮不成立**。

## 三 口径纪律（引用时别走样）

- 门③ **exit 2 = 缺输入**；**exit 1 = 真有不一致**（且默认 strict 口径下 0/65 是**口径产物**，不是路由坏）。
- 门④ = 0 **不等于** registry↔routes 对得上 —— 它只核一个方向（F3）。
- 「13 个」（67 条口径）与「14 个」（登记表实有）**指的不是同一个集合**，报数必须带口径（F4）。
- 本单所有数字是 **2026-10-04 09:55–10:00 的只读快照**；期间另有会话在写 `kb/l7/runs/`，复跑数字可能变。
- ⑤ 信封态 0、⑥ 投影 R1/R2/R4 漂移 —— 与本单主题**无关**，不要混进 registry↔routes 的账。

## 四 复现命令（逐条可跑）

```bash
cd "/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理"
python3 .dsh/skills/kb-check/scripts/preflight.py                 # 0，且明示赢家表缺
sh kb/kbpy l7/scripts/skills_check.py                             # ① 0
sh kb/kbpy l7/scripts/layers_check.py                             # ② 0
sh kb/kbpy l7/scripts/routes_reconcile.py kb/l7/reports/NOPE.json # ③ 2（缺输入，非数据坏）

# F1 死键
grep -rn "frozen_expectation" --include=*.py .                    # 0
grep -rn "dir_name_map"       --include=*.py .                    # 0
sed -n '43,63p'   kb/l7/scripts/routes_reconcile.py               # 硬编码 ALIAS（14 行）
sed -n '243,248p' kb/l7/scripts/routes_reconcile.py               # 实际用 skills.yaml 的 dir_name
sed -n '173,190p' kb/l7/registry/routes.yaml                      # 被声称"被读"的那张表

# F2 漏核
grep -rn "mutual_not_for" --include=*.py .                        # 0
sed -n '138,165p' kb/l7/registry/routes.yaml                      # 表里 7 组
sed -n '327,332p' kb/l7/scripts/routes_reconcile.py               # 硬编码 7 对，无 文案/视频

# F3 单向核
sed -n '283,298p' kb/l7/scripts/routes_reconcile.py
grep -c kb-ingest-extractor kb/l7/registry/routes.yaml            # 0
grep -c brand-product-fact-curator kb/l7/registry/routes.yaml     # 0

# F4 计数
grep -n "13 个 brand" kb/l7/registry/routes.yaml                  # 6 处
grep -n "^  - id: brand-" kb/l7/registry/skills.yaml              # 14 条

# F5 输入
ls kb/l7/reports/ | grep -c winners                               # 0
```

## 五 交付口径（三种"红"的归类）

| 项 | 归类 | 说明 |
|---|---|---|
| F1 / F2 | **真坏（表↔代码契约不成立）** | 声明与实现不符，交 `kb-repair` 或裁口径 |
| F3 / F4 | **真坏（覆盖面/计数）** | 属口径裁定 + 补数据，需人裁 |
| F5 | **缺输入** | 非数据坏；要有赢家表才能跑门③ |
| ⑤ / ⑥ | ⑤ 过 / ⑥ 合法漂移 | 与本主题无关，单列 |
| `kb-check` 的 layer=「—」 | **非发现** | `layers.yaml:541-543` 已机制豁免 |
