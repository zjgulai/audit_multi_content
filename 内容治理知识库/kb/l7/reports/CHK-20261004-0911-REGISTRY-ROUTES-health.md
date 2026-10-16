# 体检表 · registry ⇄ routes 对账（对峙用）

- run_id：`CHK-20261004-0911-REGISTRY-ROUTES` ｜ 实测窗口 2026-10-04 09:06–09:12 CST
- 库根（权威库真身）：`/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理`
- 档位：**体检档**（`kb-check`），重点 = `skills.yaml`（登记表）⇄ `routes.yaml`（路由表）⇄ `layers.yaml`（层契约）
- 写盘：仅本文件。④ `l8/workflow_check.py` **本会话未跑**（无干跑档、会写 kb/l8/），改读并发批 09:05 / 09:18 的输出。
- 并发：09:05–09:12 另有会话在跑同一批闸门（`_chk-run-CHK-20261004-0905/`）。未认领、未写 kb/l0…l7、未碰任何锁。

## 〇 前提审查（三条，先说）

1. 「两块」在本库实际是**三张表**：`skills.yaml`（有哪些成员）／`routes.yaml`（这句话该谁接）／`layers.yaml`（链路怎么跑）—— 依据 `routes.yaml:3-6` 自己的口径。只核两张会整块漏掉 B1（层主无路由）。
2. `routes.yaml` **就住在 `kb/l7/registry/` 目录里**，所以按「目录 vs 文件」理解"registry 和 routes 对不对得上"无从对账；有意义的对账是上面三张表之间。
3. 本主题**今天已查过两轮**并留档：`CHK-20261004-0300-REGISTRY-ROUTES-health.md`（A1–A9）、`CHK-20261004-0815-REGISTRY-ROUTES-health.md`。本单是**独立复跑**，结论与它们一致 —— 对峙时对方能主张的是「已知未修」，不是「没发现」。

## 一 闸门实测（退出码为实测值）

| # | 闸门 | 命令 | 退出码 | 判定 |
|---|---|---|---|---|
| ⓪ | preflight | `python3 .dsh/skills/kb-check/scripts/preflight.py` | 0 | 前置齐；**赢家表输入缺**（门③ 将 exit 2） |
| ① | 登记表自检 | `sh kb/kbpy l7/scripts/skills_check.py` | **0** | 过 · `1=0 2=0 3=0 4=0 5=0` · 71 行（本项目 52/宿主通用 19）· 装载位 59 目录 |
| ② | 层契约 | `sh kb/kbpy l7/scripts/layers_check.py` | **0** | 过 · 六类 0 · 8 层齐 · DAG 非线形 |
| ③ | 路由对账（契约路径） | `routes_reconcile.py kb/l7/reports/<RUN>-routes-winners.json` | **2** | 缺输入（**不是**"65 条全不一致"） |
| ③ | 路由对账（strict） | `routes_reconcile.py <借用的赢家表>` | **1** | 全轮命中 **0/65** —— 口径产物，见 B4 |
| ③ | 路由对账（`--alias`） | 同上 ＋ `--alias` | **1** | 全轮命中 **60/65**，①=5 ②=5，**④ 路由表自检 = 0** |
| ④ | 链路收口 | （并发批 09:05/09:18） | 1 | FAIL ②③⑥；**② 属合法变红**（活库冻结基线必然漂移） |
| ⑤ | 信封闸门 | `python3 tools/envelope_gate.py` | **0** | 1925 文件 · 信封态 **0** · 两读者一致 |
| ⑤ | 信封普查 | `sh kb/kbpy l8/envelope_census.py` | **0** | 10336 个 .md，1079 个 node 读不到，**全部已分类**（归档 569/备份 510） |
| ⑥ | 投影一致性 | `sh kb/kbpy l8/projection_reconcile.py` | **1** | 3/6 通过，漂移 R1/R2/R4 |
| — | 宿主全库体检 | `kb_check`（只读） | — | 健康分 **79.2**（熔断线 60）· 结论**不通过** —— 拉分项在本单主题之外（孤岛率 0.94 / E026 大量） |

## 二 对不上的地方（逐条给原始证据 + 行号 + 复现）

### B1 · 覆盖面对不上：16 个「本项目 · 生产」成员在 `routes.yaml` 里 **0 命中**（门④ 抓不到）

登记表实有 27 个 `kb-*`/`brand-*` 且 `status: 生产` 的成员；其中只有 **11 个**在 `routes.yaml` 里有身份（`to` 或 `chains.members`/`entry`），**16 个一个都没有**：

- **12 个专项 `brand-*`**（`skills.yaml:625,642,659,677,694,711,728,745,762,779,796,813`）—— 只有 `brand-content-review-agent` 有 route（`routes.yaml:86`）
- **3 个 `layers.yaml` 逐层认定的层主**：`kb-ingest-extractor`（`layers.yaml:154` L1 / `:201` L2）、`kb-media-extractor`（`:154`）、`kb-clause-extractor`（`:238` L3）
- **`brand-product-fact-curator`**（`skills.yaml:882`，生产、已装 `~/.dsh/skills/brand-product-fact-curator`）

硬证据：

```
routes.yaml:35  members: [kb-pipeline, kb-l0-feishu, kb-canonical-lookup, kb-p0-check, kb-recall, kb-check, kb-repair]   ← 7 个，不含 L1/L2/L3 层主
routes.yaml:43  members: [kb-review, kb-content-review, brand-content-review-agent]                                     ← 只 3 个
routes.yaml:45      13 个 brand-* 是**消费侧子能力 / 链内成员**，不单独对外当入口；
routes.yaml:46      由 kb-review 或 brand-content-review-agent 编排。它们不计入 kb-manage 的 14 个成员。
layers.yaml:154   skill: [kb-ingest-extractor, kb-media-extractor]   # 按此序调
layers.yaml:201   skill: [kb-ingest-extractor]
layers.yaml:238   skill: [kb-clause-extractor]
```

- `:43` 只列 3 个成员，`:45-46` 的文字却说那 13 个 brand-* **是链内成员** ⇒ **表与自己相邻两行的注不一致**。
- 门④ **单向核**：`routes_reconcile.py:283-298` 只核「`to`/`members`/`entry` ∈ 登记表」，不核「登记表里该被期望的成员有没有 route」⇒ 这个方向**永远报 0**。
- 12 个专项的实际归属写在**另一个文件**：`kb/l7/skills/kb-review/SKILL.md:58-74`（让位表，13 行）；`routes.yaml:81` 只是指向它，未逐条登记。

复现：

```bash
grep -c kb-ingest-extractor kb/l7/registry/routes.yaml    # 0
grep -c kb-media-extractor  kb/l7/registry/routes.yaml    # 0
grep -c kb-clause-extractor kb/l7/registry/routes.yaml    # 0
grep -c brand-product-fact-curator kb/l7/registry/routes.yaml  # 0
grep -n "^  - id: brand-" kb/l7/registry/skills.yaml      # 14 条
```

要人做什么：要么在 `routes.yaml` 给这 16 个补 route/链成员身份，要么把 `:45-46`、`:43` 的措辞改成与数据一致（"不由本表路由，归属见 kb-review 让位表"）。
复开条件：`routes.yaml` 里 16 个 id 的命中数全部 ≥1，或 `:43-46` 改成不再声称它们是链内成员。

### B2 · 计数对不上：`routes.yaml` 6 处写「13 个 brand-*」，登记表实有 **14** 个

```
routes.yaml 写 13 的行：23 / 45 / 81 / 171 / 192 / 205
skills.yaml 实有 14 个 brand-*：608 625 642 659 677 694 711 728 745 762 779 796 813 882
```

多出来的第 14 个是 `brand-product-fact-curator`（`skills.yaml:882-897`）：`scope=本项目`、`status=生产`、`source: l7/skills/brand-product-fact-curator/`、已装于 `~/.dsh/skills/brand-product-fact-curator`（**英文目录名**，与另外 13 个中文目录不成体系）、**无 `dir_name` 字段**、`routes.yaml` 全文 **0 命中**。

后果：它不进 `frozen_expectation.dir_name_map`（13 条，`routes.yaml:177-190`）、不进冻结用例集（13 个期望成员）⇒ **它的路由从未被任何闸门核过**。

同一处滞后还有：`skills.yaml:1105` 的块注释仍写「家族成员共 **14 个** …… 13 个 brand-* 是消费侧子能力，不计入这 14 个」。

要人做什么：定它是"第 14 个专项（补 route + `dir_name` + 用例）"还是"链内子能力（改计数口径）"—— 这是**口径裁定**，不是补数据。
复开条件：`routes.yaml` 的 brand-* 计数 == `skills.yaml` 的 14，或 `skills.yaml:882` 的 status 改成非生产并写明它不对外路由。

### B3 · 表里声明了、判据从不读（门③ 自己也抓不到）

1. **`frozen_expectation.dir_name_map`**（`routes.yaml:173-190`）—— `routes.yaml:176` 原文声称
   「对账器 `kb/l7/scripts/routes_reconcile.py` 的 `--alias` 口径**用这张表**把两边归一」。
   **实测不成立**：对账器全文 **0 命中** `frozen_expectation` / `dir_name_map`，它用的是自己**硬编码**的 `ALIAS`（`routes_reconcile.py:43-64`，14 行）。⇒ 同一事实两份，`routes.yaml` 那份是**死键**；改 `routes.yaml` 那张表对闸门无任何影响。
2. **`mutual_not_for`**（`routes.yaml:138-165`）—— `:138` 原文「互斥点名（**硬约束，对账器会核**）」，表里 7 组，第 1 组是 `:148 pair: ["文案合规审查", "视频安全审查"]`。
   **实测漏核**：对账器硬编码 7 对（`routes_reconcile.py:327-332`），**不含** `文案合规审查 ↔ 视频安全审查` 这一组。⇒ 表里写了、闸门不核；**再加第 8 组也不会被发现**。

复现（全库范围，排除备份/历史产物）：

```bash
grep -rn "frozen_expectation" --include=*.py --include=*.sh . | grep -v _chk-run   # 0 命中（脚本侧）
grep -rn "mutual_not_for"     --include=*.py --include=*.sh . | grep -v _chk-run   # 0 命中（脚本侧）
sed -n '283,298p' kb/l7/scripts/routes_reconcile.py    # 门④ 只读 routes/chains
sed -n '327,332p' kb/l7/scripts/routes_reconcile.py    # 硬编码 7 对，无 文案/视频
```

要人做什么：二选一 ——（a）让对账器读这两个键（表即判据），或（b）在 `routes.yaml` 明写"本键由 X 脚本读/仅供参考"，并删掉「对账器会核」「用这张表」这两句不成立的声明。
复开条件：脚本侧出现对这两个键的真实读取，或那两句声明被删除/改写。

### B4 · 门③ 的契约输入**没有生产者**，且默认口径恒红（再说一次，因为最容易误读）

- 契约命令在 `references/gates.md:33`：`routes_reconcile.py kb/l7/reports/<RUN>-routes-winners.json`。
- 该路径下 **0 个** winners 文件（preflight 已明示）⇒ 按契约原样跑**恒 exit 2**。
- 本单只能借 `_eval-kb-manage/results_alias/routes-winners_20261004-0327-SUB.txt`（115 行，mtime 2026-10-04 03:24:57）。
- 默认 `strict`（`--alias` 是 `store_true`，`:218-219`）⇒ 中文名赢家表恒 **0/65**；加 `--alias` 才 **60/65**。
- `--alias` 下仍红的 5 条（I1–I5）**全部**是 `brand-ai-provenance-rights-review`，`routes.yaml:238-255` 已登记为**冻结用例集自身歧义** ⇒ **这是路由质量问题，不是 registry↔routes 表间问题，引用时别混。**

## 三 本单与 08:08 那份的差异（诚实标注）

- **⑤ 已收口**：08:08 报告记「活路径信封 **1 个**」= `kb/l7/reports/CHK-20261004-0326-DSH-health.md`（diff **-4096**）。本单 09:11 实测该文件 `python getsize = 20502` / `node statSync = 20502` ⇒ 差值 **0**；`tools/envelope_gate.py` 扫 1925 文件、信封态 **0**，与并发批 09:05 的读数**完全一致**。⇒ 该项**由红转绿**。
- 08:08 的 B1/B2/B3/B4 四类，本单**逐条独立复现**，未发现已修（A1/A4/A5 与 `CHK-20261004-0300` 报告同名同结论）。
- ③ 本单与 08:08 用的是**同一份（也是唯一一份）**赢家表。

## 四 复现命令（逐条可跑）

```bash
cd "/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理"
python3 .dsh/skills/kb-check/scripts/preflight.py
sh kb/kbpy l7/scripts/skills_check.py                                   # ① 0
sh kb/kbpy l7/scripts/layers_check.py                                   # ② 0
W=_eval-kb-manage/results_alias/routes-winners_20261004-0327-SUB.txt
sh kb/kbpy l7/scripts/routes_reconcile.py "$W"                          # ③ 1（strict 0/65）
sh kb/kbpy l7/scripts/routes_reconcile.py "$W" --alias                  # ③ 1（alias 60/65，④=0）
python3 tools/envelope_gate.py                                          # ⑤ 0
sh kb/kbpy l8/envelope_census.py                                        # ⑤ 0
sh kb/kbpy l8/projection_reconcile.py                                   # ⑥ 1（3/6）
grep -n "13 个 brand" kb/l7/registry/routes.yaml                        # 6 处
grep -n "^  - id: brand-" kb/l7/registry/skills.yaml                    # 14 条
sed -n '283,298p;327,332p' kb/l7/scripts/routes_reconcile.py            # 门④ 单向核 + 硬编码 7 对
```

## 五 口径纪律（引用时别走样）

- 门③ **exit 2 = 缺输入**；**exit 1 = 真有不一致**（+ strict 口径产物）。
- 门③ ④ 节 = 0 **不等于** registry↔routes 对得上 —— 它只核一个方向（B1）。
- ④ 的「②权威库未被改动」FAIL = 活库**合法变红**，不是坏了。
- 本单所有数字是 **09:06–09:12 的只读快照**；期间另有会话在写（`kb/l7/runs/`、`kb/view/_meta/query-log.ndjson`），复跑数字可能变。
