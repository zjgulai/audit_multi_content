# 体检表 · 全库自检（重点：信封闸门 / 路由对账）· 2026-10-04

**库根**：`/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理`
**RUN**：`CHK-20261004-0217-SELF`（2026-10-04 02:14:12 起）
**口径**：`kb-check` 体检档（只报不改）
**重点段**：`tools/envelope_gate.py`（信封闸门）、`l7/scripts/routes_reconcile.py`（路由对账）

> ⚠️ **并发提示**：本次运行期间，另有 ≥4 个会话在跑同一套闸门（PID 54997 跑 `CHK-20261004-0210-LAYERCLOSE`；
> 56783 / 57095 跑 `ci/run_gates.py`；57509 跑 `projection_reconcile`）。
> 而 `kb_loop_claim.py status` 报**无认领** —— 认领纪律当前未被任何会话执行。
> 本单对会写盘的闸门使用独立 RUN 名，未覆盖他人产物。

---

## 一、闸门总表

| # | 闸门 | 命令 | 退出码 | 结论 | 证据 |
|---|---|---|---|---|---|
| ① | 登记表自检 | `l7/scripts/skills_check.py` | **0** | ✅ 过 | 五类 0/0/0/0/0；本项目 40 装 40；副本比对 0 不一致 |
| ② | 层契约 | `l7/scripts/layers_check.py` | **0** | ✅ 过 | 六类全 0；8 层齐；DAG 非线形 |
| ③ | 路由对账（规范档） | `routes_reconcile.py <赢家表> --cases cases_v2.json --alias` | **1** | ⚠️ **过门槛但有 6 条对不上** | 109/115 = **0.948** ≥ 0.90 |
| ③' | 路由对账（strict） | 同上去掉 `--alias` | 1 | ❌ **假红（口径）** | 0/65 全不一致，实为别名口径 |
| ④ | 链路收口 | `l8/workflow_check.py` | **1** | ⚠️ 3 段红：2 合法漂移 + 1 游离件 | ②③ 基线漂移；⑥ 511 信封 |
| ⑤ | 信封闸门（活路径） | `tools/envelope_gate.py` | **0** | ✅ 过 | 1881 文件 / 0 信封 / 两读者一致 |
| ⑤' | 信封普查（仅 .md） | `l8/envelope_census.py` | **0** | ✅ 分类清楚 | 1079 信封 = 569 归档 + 510 可再生备份 |
| ⑤'' | 信封真值（shell 视角，本单加测） | `find -exec stat -f%z` vs `os.path.getsize` | — | ✅ **kb/ 活路径 0** | 1081 全在归档/备份(570+510) + 范围外 1 |
| ⑥ | 投影一致性 | `l8/projection_reconcile.py` | **1** | ❌ **真坏** | 3/6；R1/R2/R4 漂移 |
| ⑦ | 供给链零写自证 | `l7/scripts/kb_pipeline.py --check` | **1** | ⚠️ 零写 ✅ 但 L0 闸门红 | 4001 文件快照 0 变化；L0 `real_diff_total=2` |

---

## 二、重点段 1 · 信封闸门

**结论：绿是真的，但绿的含义比字面窄。**

- 活路径档 `envelope_gate.py`：扫 1881 个 `.py/.txt/.md`，信封态 **0**，退出码 0。
- 库自带普查 `envelope_census.py`：扫 10290 个 `.md`，1079 个「node 侧读不到」，但**全部分类**：
  569 刻意归档（`l8/_archive/enveloped-20260923-1520/`）+ 510 可再生的过期备份（`.work/hostlib.bak-*`）。结论 OK。
- **本单加测（真值普查，shell `stat -f%z` 当基准，10521 个 .md）**：差值恰 4096 者 **1081** 个 ——
  570 `_archive` + 510 `.work/hostlib*` + **1 工作区游离件**；**`kb/` 活路径上为 0**。
  ⇒ 与 ④ 段/普查的结论方向一致，**没有发现被漏掉的活路径信封**。

**判据盲点（非数据缺陷）**：`envelope_gate.py` 的判据是
`abs(getsize_python − size_消费方读者) == 4096`（`tools/envelope_gate.py:198`）。
它测的是「**消费方读得到吗**」，**不是**「有没有信封」。实测反例：

```
_eval-L0L7-gap-20261003/kb-recall/evals/_eval/STATE.md   inode 94311294
  /usr/bin/stat -f%z  → 8962      （含 4096 字节二进制信封，偏移 4866 起为高熵随机字节）
  python os.stat()    → 4866      （首 4866 字节是合法 markdown）
  node statSync().size→ 4866
```
两读者**同时**剥离信封 ⇒ 差值 0 ⇒ 闸门判「正常」。要用「shell stat vs 读取器」这把尺子才看得见。
该文件**不在** `DEFAULT_ROOTS`（`kb/l0…l8`、`kb/.work`、`kb/view`、`kb/versions`、`tools`、`_eval-kb-manage`）内，
所以活路径档从来不扫它 —— 是 ④ 段（扫 `.`）把它抓成 `其他: 1` 的。

**输出口径小问题**：`envelope_gate.py` 把 `kb/.work` 列进「扫描范围」，却按
`SKIP_PREFIXES = ("hostlib",)`（`tools/envelope_gate.py:71`）静默跳过其中 3101 个 `.md`；
屏幕不提示跳过量。跳过本身**是刻意的、有代码注释**（「活路径不该有信封，备份里有一堆是历史事实」），
但列进范围却不说明，容易让人以为 1881 就是全部。

---

## 三、重点段 2 · 路由对账

### 3.1 输入：赢家表不在登记位置

`kb/l7/reports/<RUN>-routes-winners.json` **不存在** ⇒ 按契约**退出码 2**、不得报绿。
但赢家表**并非不存在**，只是不在该路径 —— 全库有 5 份，位于 `_eval-kb-manage/`：

| 文件 | mtime | 行数 |
|---|---|---|
| `blind_before_v2.winners.txt` | 09-29 18:37 | 65 |
| `blind_after.winners.txt` | 09-29 18:52 | 115 |
| `blind_after_r3.winners.txt` | 09-29 19:01 | 115 |
| `blind_after_r4.winners.txt` | 09-29 19:32 | 115 |
| **`blind_v2.winners.txt`（本单采用，最新）** | 09-29 19:58 | 115 |

⇒ 同级会话报的「环境错」应修正为「**登记位置缺失、数据在别处**」。
**时效**：这批赢家表是 **09-29** 的（5 天前），非「今天的数据」；
`routes.yaml` 之后若改过，本对账**无法区分**「路由坏了」与「路由表改了」。

### 3.2 结果

| 档位 | 命中 | 门槛 | 问题数 | 退出码 |
|---|---|---|---|---|
| strict（默认） | 0/65 | — | 65 | 1 |
| **规范档** `--cases cases_v2.json --alias` | **109/115 = 0.948** | ≥ 0.90 ✅ | **6** | 1 |

**strict 档的 65 条全是假红**：期望写英文别名 `brand-image-safety-review`，实际是中文装载名 `图片安全审查` ——
`routes.yaml:177` 的 `frozen_expectation.dir_name_map` 就是二者映射的**权威口径**。用 `--alias` 后归零。

**真不一致 6 条**（规范档）：

| 用例 | 期望 | 实际（3 轮） |
|---|---|---|
| I1 | AI溯源与权利审查 | 视频安全审查 / 视频安全审查 / 视频安全审查 |
| I2 | AI溯源与权利审查 | NONE / 图片安全审查 / NONE |
| I3 | AI溯源与权利审查 | NONE / **AI 溯源与权利审查** / NONE |
| I4 | AI溯源与权利审查 | **AI 溯源与权利审查** / NONE / NONE |
| I5 | AI溯源与权利审查 | 图片安全审查 / 图片安全审查 / CLARIFY |
| kb-manage-4 | kb-manage | kb-manage / kb-manage / **kb-pipeline** |

- 抢走计数：`NONE` 6 · `视频安全审查` 3 · `图片安全审查` 3 · `AI 溯源与权利审查` 2 · `CLARIFY` 1。
- 逐成员命中率：**除 `AI溯源与权利审查` 0/5 条（0/15 轮）与 `kb-manage` 4/5 条（14/15 轮）外，其余全部 5/5 条、15/15 轮。**
- ④ 路由表自检：**0 条**。

### 3.3 第二个独立缺陷：名字里的空格

赢家表把该成员记成 `AI 溯源与权利审查`（**带空格**，`blind_v2` 里 2 次：I3 第 2 轮、I4 第 1 轮）；
而权威装载目录名是 `~/.dsh/skills/AI溯源与权利审查`（**无空格**），`dir_name_map` 的目标值同样无空格。
`canon()` 是**精确字典查找**（`routes_reconcile.py:100-102`，`ALIAS.get(n, n)`），带空格的变体**永不折回**。

⇒ 那 2 轮**本已接对却记为错**。故「**0/15 轮**」是**判据口径下的 0**，实际至少 2 轮接对。
真问题在于 I1 / I2 / I5 三轮皆错，**该成员确实路由失败**——但报告的「0/15」不是字面事实。

### 3.4 退出码口径

`routes_reconcile.py:408`：`exit_code = 0 if (①+④)==0 else 1` —— **与 F1 门槛无关**。
即「F1 过 0.90 门槛」**不等于**「闸门绿」。0.948 仍 exit 1。

---

## 四、其余闸门：失败项定性

### ④ `workflow_check.py`（RUN `CHK-20261004-0217-SELF`）

`PASS` ①④⑤⑦⑧⑨ ｜ `FAIL` ②③⑥ ｜ 装载位 509 条 / 信封 0 / 健康分 **79.1** / 检索 `[111,1,509,0]` 全命中

| 段 | 定性 | 依据 |
|---|---|---|
| ② 权威库 l0~l6 未被改动 | **合法变红（基线漂移）** | `l0/l1/l2` 均 `match_L5_baseline: **true**`；红在 l3：`l3_base1018_matches_L6: false`、`l3_whole1527_matches_L4: false`。活库模式下 L3 蒸馏推进 ⇒ 冻结基线必然失配 |
| ③ 前序产物哈希（45 项） | **合法变红（同上根因）** | 20 项不符，全为 L3→L7 前序产物 + `kb-content-review/SKILL.md`、`scripts/review.py`。**功能未坏的反证**：⑤⑦ 读同一批产物均 PASS（l6 索引 `[111,1,509,0]` 命中、检索可用、真入口 `with_kb_evidence.py` rc=0） |
| ⑥ 文档可见性 | **真坏（1 个游离件）+ 已知范围外** | 6076 md 中 511 信封 = **510 `kb/.work/hostlib*`**（可再生备份，判据不计入失败）+ **1 个 `其他`**：`./_eval-L0L7-gap-20261003/kb-recall/evals/_eval/STATE.md` |

**① 段的判据盲点（待裁）**：① 判 **PASS**，但同一段的原始值显示版本台账为空 ——
`kb/versions/versions.jsonl` 有效行 **0**、`l7.json` 的 `kb_version = 'v0'`、`l4_canonical_bytes = 0`。
即 ① 段并未实际断言「版本台账非空」。

**⑨ 段**：`[E026] 内容质量分 52.1 < 60`（长度 0.4/20 · 密度 5/30 · 去重 20/20 · 语言 26.7/30），
但 `落盘 0 个` ⇒ 未产生实际写入，不构成数据污染。

### ⑦ `kb_pipeline.py --check`：零写自证通过，但 L0 闸门红

零写自证：产出文件 mtime 快照 **4001 个，变化 0 个** ✅。
L1–L7 只读闸门全 `exit=0`；**L0 `exit=1`**：

```
real_diff_total: 2
uncovered: 专家修订汇总表（tbl8AI00JZO1iZtp）：拉取失败（**没有声明**）
           内容公式（仅供参考）（tblVdl0jdK9G4ld3）：拉取失败（**没有声明**）
EX-1 材料收集  only_feishu  10/10  预期内（声明口径，非漏抓）
```

### ⑥ `projection_reconcile.py`：3/6，真坏

| 检查 | 结果 |
|---|---|
| R3_id_set / R5_manifest_bytes / R6_tier_dir | ✅ |
| R1_source_sha256 | ❌ 源文件 rules 在视图生成后变过（`f27a14091b2bd782… → 743dc62398311b02…`） |
| R2_entry_fingerprint | ❌ **509 条**条目的权威规则已变 |
| R4_governance_passthrough | ❌ **2036 处**治理字段未传导：`owner` 509 · `half_life_days` 509 · `valid_until` 509 · `effective_from` 509 |

修法（工具自带）：重跑 `kb/.work/gen-host-library.py` 到 staging 后回填；R4 另需确认投影生成器是否从规则行读这 4 个字段（F8）。

---

## 五、失败项清单（对象 · 原因码 · 要人做什么 · 复开条件）

| # | 对象 | 定性 | 要人做什么 | 复开条件 |
|---|---|---|---|---|
| 1 | L0：`tbl8AI00JZO1iZtp`、`tblVdl0jdK9G4ld3` 拉取失败且未声明 | **真坏** | 补声明（若本就该排除）或修拉取 | `l0_gate.py` → exit 0 |
| 2 | 投影 R1/R2/R4（509 条 / 2036 处） | **真坏** | 重跑 `gen-host-library.py` 到 staging 回填；核 F8 | `projection_reconcile.py` → 6/6 |
| 3 | `workflow_check` ②③ 基线失配 | **合法漂移**（非缺陷） | 刷新冻结基线（先确认「变了」而非「坏了」） | exit 0 |
| 4 | `_eval-L0L7-gap-20261003/kb-recall/evals/_eval/STATE.md` 带信封 | **真坏（轻）** | 删除或移出工作区 | ⑥ 的 `其他` bucket 为空 |
| 5 | 路由：`AI溯源与权利审查` 0/5 条、0/15 轮 | **真坏** | 修该成员触发/让位（重点 I1/I2/I5） | 该成员 ≥ 4/5 条 |
| 6 | 路由：赢家表 `AI 溯源与权利审查` 空格变体 | **判据缺陷** | `canon()` 加空白归一化，或修 eval 写法 | 那 2 轮不再误判 |
| 7 | `envelope_gate.py` 列 `kb/.work` 为范围却静默跳 `hostlib*`（3101 md） | **判据缺陷（可读性）** | 屏幕打印跳过量与 `--all` 提示 | 输出含跳过量 |
| 8 | `workflow_check` ① PASS 但版本台账为空（`kb_version='v0'`、0 行） | **待裁（判据盲点）** | 人确认：空台账是预期还是缺登记 | ① 段显式断言台账非空 |
| 9 | `kb-manage-4` 第 3 轮被 `kb-pipeline` 抢走 | **真坏（轻）** | 核 kb-manage / kb-pipeline 点名互斥 | 5/5 条 |
| 10 | 路由对账输入不在登记路径 | **流程缺陷** | 约定赢家表落盘 `kb/l7/reports/<RUN>-routes-winners.json` | 该路径有文件 |
| 11 | `kb_loop_claim` 无认领但 ≥4 会话并发跑闸门 | **流程缺陷** | 跑前 `claim`、跑后 `release` | status 显示单一认领 |

---

## 六、本单未判定项（不猜）

- 信封可见性差异的**机制**：同一 inode 上 `/usr/bin/stat`(含子进程) 报 8962 而 python `os.stat()` 报 4866，
  已排除 `sitecustomize` / `usercustomize` / DYLD 注入 / xattr / PATH shim / 软链。
  机制**未查明**；但「该文件带 4096 字节二进制信封」是已确认事实（偏移 4866 起为高熵随机字节）。
- 版本台账为空的**意图**（上面第 8 项）。
- 赢家表 09-29 之后 `routes.yaml` 是否改过 —— 未查，故无法区分「路由坏了」与「路由表改了」。
