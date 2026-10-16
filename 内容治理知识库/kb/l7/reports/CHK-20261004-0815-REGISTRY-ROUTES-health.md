# 体检表 · CHK-20261004-0815-REGISTRY-ROUTES

- run_id : `CHK-20261004-0815-REGISTRY-ROUTES`
- 库根   : `/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理`
- 档位   : 体检档（kb-check），**重点 = 登记表 skills.yaml ⇄ 路由表 routes.yaml**
- 写盘   : 仅本文件（走 node 通道）。④/⑥ 本次**未自行跑**（会写盘），改读同批 08:02–08:04 sweep 的结果。

## 0. 六道闸门退出码

| # | 闸门 | 退出码 | 结论 |
|---|---|---|---|
| ⓪ | preflight | 0 | 前置齐（但门③ 契约输入缺） |
| ① | skills_check（登记表自检） | 0 | **过**，五类问题 0/0/0/0/0 |
| ② | layers_check（层契约） | 0 | **过**，六类 0 |
| ③ | routes_reconcile（路由对账） | 2 / 1 / 1 | 见 §1（三种输入面各一次） |
| ④ | workflow_check | 1 | FAIL ②③⑥（②属合法变红） |
| ⑤ | envelope_gate / envelope_census | 1 / 1 | 活路径信封 **1 个** |
| ⑥ | projection_reconcile | 1 | 3/6 通过，漂移 3 |

## 1. 门③ 三种输入面（这是最容易被误读的一道）

| 命令 | 退出码 | 结果 |
|---|---|---|
| `routes_reconcile.py`（不给 winners） | 2 | 用法错：winners 是位置参数 |
| `routes_reconcile.py kb/l7/reports/NOPE-routes-winners.json` | 2 | 环境错：赢家表不存在 |
| `routes_reconcile.py <真实赢家表>`（默认 strict） | 1 | 逐条全轮命中 **0/65** |
| `routes_reconcile.py <真实赢家表> --alias` | 1 | 逐条全轮命中 **60/65** |

真实赢家表不在契约路径下，唯一一份在：
`_eval-kb-manage/results_alias/routes-winners_20261004-0327-SUB.txt`（115 行）

## 2. 登记表 ⇄ 路由表：对得上的部分（避免误伤）

**id ⇄ 装载目录名映射，四处一致，0 不一致：**

| 来源 | 位置 | 条数 |
|---|---|---|
| `routes.yaml` `frozen_expectation.dir_name_map` | `kb/l7/registry/routes.yaml:177-190` | 13 |
| `skills.yaml` `dir_name` 字段 | `kb/l7/registry/skills.yaml:615,632,649,666,684,701,712,735,752,769,786,803,820` | 13 |
| 真实装载目录 + frontmatter `name:` | `~/.dsh/skills/<中文名>/SKILL.md` | 13 |
| 对账器内置 `ALIAS` | `kb/l7/scripts/routes_reconcile.py:43-64` | 14（含 1 条遗留别名） |
| 打分器内置 `ALIAS` | `_eval-kb-manage/kb_routes_score.py:33-49` | 14，与上表**逐行相同** |

- 门④ 路由表自检 **0 条**：`routes.yaml` 的 `to` / `chains.members` / `chains.entry` 全部命中登记表成员。
- 冻结用例集（65 条 / 13 个期望成员）与 `dir_name_map` 双向无缺口：用例期望有而没登记的 0 个，登记了而用例没出现的 0 个。

## 3. 对不上的四处（硬证据）

### 3.1 覆盖面对不上：冻结期望 13 个成员，routes 只给其中 1 个写了 route
- `kb/l7/registry/routes.yaml:9` 自称本表是「这句话该谁接」的**静态真源**。
- 实际 `routes:`（`routes.yaml:62-136`）只有 **11 条**，`to` 覆盖 **11 个**成员。
- 冻结基线要求 13 个 `brand-*` 各自接走；其中 **12 个在 routes.yaml 里没有任何 route**（只有 `brand-content-review-agent` 有，见 `routes.yaml:86`）。
- 这 12 个的归属实际写在**另一个文件**：`~/.dsh/skills/kb-review/SKILL.md:58-74` 的让位表（13 行，逐行点名中文装载名）。
- `routes.yaml:43` 的 `chains.review.members` 只列 3 个（`kb-review` / `kb-content-review` / `brand-content-review-agent`），而 `routes.yaml:45-46` 的文字说「13 个 brand-* 是链内成员」——**表与自己的注不一致**。
- 门④ 抓不到这个方向的缺口：`routes_reconcile.py:283-298` 只核「`to` 是否在登记表里」，不核「登记表里该被期望的成员有没有 route」。

### 3.2 计数对不上：routes 写「13 个 brand-*」，登记表实有 14 个
- `routes.yaml` 6 处写 13：行 `23 / 45 / 81 / 171 / 192 / 205`。
- `skills.yaml` 实有 **14** 个 `brand-*`：行 `608,625,642,659,677,694,711,728,745,762,779,796,813` + **`882`**。
- 多出来的是 **`brand-product-fact-curator`**（`skills.yaml:882`）：`scope=本项目`、`status=生产`、已装于 `~/.dsh/skills/brand-product-fact-curator`（**英文目录名**，与另外 13 个中文目录不成体系）、**无 `dir_name`**、**`routes.yaml` 全文 0 命中**。
- 后果：它不进 `dir_name_map`（13 条）、不进冻结用例集（13 个期望成员）⇒ 它的路由**从未被任何闸门核过**；`routes_reconcile.py:246` 靠 `d = r.get("dir_name") or r.get("id")` 兜底折回英文 id。
- 另：`skills.yaml:1105` 的 note 仍按「14 个家族成员 + 13 个 brand-*」计数，同样滞后于 14。

### 3.3 门③ 契约输入**没有生产者**，且默认口径恒红
- 契约命令（`references/gates.md:33`）：
  `kb/kbpy l7/scripts/routes_reconcile.py kb/l7/reports/<RUN>-routes-winners.json`
- 该路径下**没有任何** winners 文件 ⇒ 按契约跑**恒 exit 2**（`preflight.py:97` 同口径说明）。
- 全库 grep `routes-winners`：**只有消费方**（各 sweep/run 的调用行），**没有生产方** ⇒ 契约输入永远没人写。
- `--alias` 默认关闭（`routes_reconcile.py:218-219`，`action="store_true"`）⇒ **按契约原样跑，对中文名赢家表恒 0/65、exit 1**；真实口径要加 `--alias`（0/65 → 60/65）。
- 两种退出码含义不同，别混：「exit 2 = 缺输入」，「exit 1 = 真有不一致」。

### 3.4 数据面：赢家表里出现登记表和磁盘上都不存在的名字
- 赢家表第 43 行原文：`I3|NONE|AI 溯源与权利审查|NONE`；`hexdump` 头部 `49 33 7c 4e 4f 4e 45 7c 41 49 20` ⇒ 「AI」后**有一个 U+0020 空格**。
- 三处登记值都是**无空格**：`routes.yaml:186`、`skills.yaml:752`、真实 frontmatter `name: AI溯源与权利审查`。
- 磁盘上**不存在**带空格的装载目录（`find ~/.dsh -maxdepth 2 -name 'AI*溯源*'` → 仅无空格那一个）。
- 现状：已在**消费侧**兜住 —— `routes_reconcile.py:120-139` 的「空白不敏感装载名索引」把空白变体归一到登记值（注释自述：旧 `canon()` 只做 `.strip()`，I3/I4/I5 三轮共 5 次全误判）。
- **生产侧未修**：产出赢家表的那个环节仍会写出这个不存在的名字。下一份赢家表还会带。

## 4. 其他闸门（非本次重点，一并留证）

- **⑤ 信封闸门**：`tools/envelope_gate.py` 扫 1915 个文件 → 信封态 **1 个**：
  `kb/l7/reports/CHK-20261004-0326-DSH-health.md`（python=20502 / node=24598，差 **-4096**）。
  库自带 `l8/envelope_census.py` 独立佐证：`❌ 必须为 0 活路径 1 个`，同一个文件。
  后果：**node 侧读者（含 agent 的 read 工具）读不到这一份报告**。
  同目录 421 个 `.md` 中 420 个正常 —— 是**单点**，不是面。
- **④ 链路收口**（同批 sweep 08:02:42）：PASS ①④⑤⑦⑧⑨；FAIL ②权威库未被改动 / ③前序产物哈希（45 项）/ ⑥文档可见性（不可读 513）。
  其中 ② 属**合法变红**（活库模式下冻结基线必然漂移，见 `references/gotchas.md`）。
- **⑥ 投影一致性**：R1 源 sha 漂移 / R2 509 条权威规则已变 / R4 2036 处治理字段未传导；R3/R5/R6 通过。
- **装载位读数**（④ 段）：509 条 / 信封 0 / E001 None / E046 None / 健康分 **79.2**。

## 5. 复现命令（逐条可跑）

```bash
cd "/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理"
python3 .dsh/skills/kb-check/scripts/preflight.py
sh kb/kbpy l7/scripts/skills_check.py            # ① exit 0
sh kb/kbpy l7/scripts/layers_check.py            # ② exit 0
W=_eval-kb-manage/results_alias/routes-winners_20261004-0327-SUB.txt
sh kb/kbpy l7/scripts/routes_reconcile.py "$W"           # 门③ strict → 0/65, exit 1
sh kb/kbpy l7/scripts/routes_reconcile.py "$W" --alias   # 门③ alias  → 60/65, exit 1
python3 tools/envelope_gate.py                   # ⑤ exit 1
sh kb/kbpy l8/envelope_census.py                 # ⑤ exit 1
grep -n '13 个 brand' kb/l7/registry/routes.yaml                  # 6 处
grep -n '^  - id: brand-' kb/l7/registry/skills.yaml              # 14 条
grep -n 'product-fact-curator' kb/l7/registry/routes.yaml          # 0 命中
grep -n 'AI 溯源' _eval-kb-manage/results_alias/routes-winners_20261004-0327-SUB.txt
```

## 6. 口径纪律

- 门③ 的 **exit 2 是「缺输入」**，不是「路由表 65 条全不一致」。
- 门③ **默认 strict 的 0/65 是口径产物**，不是 65 条真不一致；真实不一致是 `--alias` 下的 **5 条**（I1–I5，全是 `brand-ai-provenance-rights-review` 一个成员）。
- ④ 的「②权威库未被改动」FAIL = 活库**合法变红**，不是坏了。
- `--alias` 下仍红的 5 条（I1–I5）**根因是用例集自身歧义**，`routes.yaml:238-255` 已登记：I1↔G3 近重复、I5↔F5 近重复、I2 欠定义；且写明「建议改用例、不再调 description」。
- §1 中「不给 winners → exit 2」与「winners 不存在 → exit 2」是**两种不同的 2**。

## 7. 并发留痕

本次体检期间（08:02–08:04）另有一批在跑同样六道闸门，产物在 `_chk-run-CHK-20261004-0810/`
（含 `04-workflow_check.txt` / `06-projection_reconcile.txt`；④ 已写 `kb/l8/workflow_check_CHK-20261004-0810.json`）。
本表 §4 的 ④/⑥ 读数取自那一批，**本会话未重复写盘**。
`kb/.work/.kb.lock` 本次全程不存在，两次查询均确认无锁。
