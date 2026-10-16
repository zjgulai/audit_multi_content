# 体检表 ｜ CHK-20261004-0125-CLOSE ｜ 逐层收口核验 ｜ 2026-10-04 01:25–01:35

- **库根**：`/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理`（cwd = 库根；`~/.dsh/Momcozy知识库/kb` 软链经核指向此处 ⇒ 本次跑的是权威库真身，不是副本）
- **档位**：`kb-check` §1 **体检档**（六道统一闸门）＋ 新鲜度前置 ＋ `ci/run_gates.py` 12 把 ＋ ②d 四层 skill 调用审计
- **纪律**：**只报不改**。未传 `--apply`、未改 `kb/l0…l7` 数据与台账、未发布任何东西到飞书
- **本次落盘产物**：① 本表 `kb/l7/reports/CHK-20261004-0125-CLOSE-health.md`；
  ② `kb/l8/workflow_check_CHK-20261004-0125-CLOSE.json`（④ 道无干跑档，按设计写盘）；
  ③ `ci/out/gates-latest.{json,md}`（CI runner 覆盖写）；④ 原始读数 `_chk-run-CHK-20261004-0125-CLOSE/*.out`
- **被核对象**：批次 **`PIPE-20261003-2354`**（用户自述「刚跑完的最新一批」），层侧 RUN = `PIPE-20261003-2354-L0 … -L7`

---

## 0. 一句话结论

**「每层都跑到了」为真，「每层都收口了」不为真。** 8 层全到达、8 个 RUN 记账齐全、四层 skill 调用审计**红 0**；
但 **L0 与 L3 两层没在数据面闭上**，且**整批 8 层零落盘**——所有落章都是 `dry_run=True / applied=False`。

**用户口径需修正**：本批是**预演预检（dry-run）走通**，不是数据落地。
批次窗口（10-03 23:54 ～ 10-04 00:25）内 `kb/l0…l7` **非 `runs` 目录零改动**（`find` 实测空集），
且每层 `write_gate` 均记「未带 `--write-gate` 凭据 ⇒ 层引擎不得带 `--apply`」，`unauthorized_layers` 覆盖 L0–L7。

---

## 1. 新鲜度前置（只读，**不拒答**）

`sh kb/kbpy l7/scripts/freshness.py` → **退出码 0**：「各层关键 data 产物都不陈旧」。
逐层 age：L0 1.8 天 ｜ L1 2.1 / 1.5 天 ｜ L2 2.6 天 ｜ L3 1.1 / 1.7 天 ｜ L4 1.1 天 ｜ L5 **4.1 小时** ｜ L6 1.7 天。
L1/L2/L3 查询档 ✅ 可调。L6 索引(10-02 22:47) vs L3 规则(10-02 22:45)：索引不旧。
⇒ 本次**没有**「因超期而必须去跑写档链路」的理由。
★ 该脚本带 `--no-gates` 跑，屏上 `health=YELLOW` 是「没跑闸门」的产物，**不代表真实健康色**。

---

## 2. 六道统一闸门（kb-check 体检档）

| # | 闸门 | 退出码 | 判定 | 关键读数 |
|---|---|---|---|---|
| ① | 登记表自检 `skills_check.py` | **0** | ✅ 过 | 五类 `1=0 2=0 3=0 4=0 5=0`；要用 40 / 已装 40 / 还差 0；未登记 selftest 62 条（不算错） |
| ② | 层契约自检 `layers_check.py` | **0** | ✅ 过 | 层 8；六类全 0；无干跑档清单 0 条 |
| ③ | 路由对账（今日输入） | **2** | ⚠️ **未判定（缺输入·硬拒）** | 今日赢家表不存在 ⇒ 按设计 exit 2，**不报绿、不按「全不一致」静默跑** |
| ③b | 同上（对照，非今日判定） | **1** | ⚠️ **两口径并存，不可混用** | 默认用例集（65 条）→ **60/65**；邻居会话传 `--cases _eval-kb-manage/cases_v2.json`（115 条）→ **109/115** |
| ④ | 链路收口核验 `workflow_check.py` | **1** | 🟡 **9 段 2 红（②③）→ 合法变红** | 装载位 509 / 信封 0 / 健康分 **79.1** / 检索 `[111, 1, 509, 0]`；可见性 5008 md（不可读 510 全为 hostlib 可再生备份）；写入侧 `[E026] 内容质量分 52.1 < 60`、落盘 0、信封 0 |
| ⑤a | 信封闸门 `tools/envelope_gate.py` | **0** | ✅ 过 | 扫 **1861** 个文件｜信封态 **0**｜读不到 0；两读者（Electron node vs PATH node）交叉**一致** |
| ⑤b | 信封普查 `l8/envelope_census.py` | **0** | ✅ 过 | 扫 8734 个 `.md`，1079 读不到，**全部已分类**（刻意归档 569 ＋ 可再生备份 510）；结论 OK |
| ⑥ | 投影一致性 `projection_reconcile.py` | **1** | 🔴 **真坏 3/6** | ❌ R1 ❌ R2（509 条）❌ R4（`owner`/`half_life_days`/`valid_until`/`effective_from` 各 509 = **2036 处**）；✅ R3 / R5 / R6 |

**红 2 道（④⑥）＋ 未判定 1 道（③）。没有一条是「脚本坏了」。**

### ④ 的 9 段逐段
`PASS ①环境与版本纪律` ｜ `FAIL ②权威库 l0~l6 未被改动` ｜ `FAIL ③前序产物哈希（45 项）` ｜ `PASS ④分层库→生成器→视图` ｜
`PASS ⑤装载位→加载器` ｜ `PASS ⑥文档可见性` ｜ `PASS ⑦消费侧 skill 可用` ｜ `PASS ⑧工作台与服务` ｜ `PASS ⑨写入侧`

---

## 3. CI 12 把（`python3 ci/run_gates.py --outdir ci/out`）

**退出码 1 ｜ 过 11/12 ｜ 红 `['l0']` ｜ 无法计算 无 ｜ 非 blocking 报错 无 ｜ 基础设施 无 ｜ 告警 无**
（`ci/out/gates-latest.json`，生成时刻 **2026-10-04T01:33:15**）

| 闸门 | 状态 | 红数 | 耗时 | 闸门说明 |
|---|---|---|---|---|
| l0 | **RED** | **2** | 40.6s | L0 判定档：原始差异 − 预期 = 真差异 |
| l1 | PASS | 0 | 12.7s | L1 独立复算：OCR 缓存复用门槛逐条核 |
| l2 | PASS | 0 | 14.7s | L2 独立复算：unit_count 口径逐条点名 |
| l3 | PASS | 0 | 17.3s | L3 独立复算：证据可回指 L2 单元 |
| l4 | PASS | 0 | 19.6s | L4 独立复算：promotion_rule C1–C6 |
| l5 | PASS | 0 | 47.7s | L5 包装分类：实质 4 项 + 基线项登记 |
| l6 | PASS | 0 | 241.4s | L6 只读档：可用单元/向量/倒排/版本纪律 |
| l7 | PASS | 0 | 9.7s | — |
| skills / layers / conformance / freshness | PASS | — | 12.9 / 15.4 / 13.2 / 89.5s | — |

★ 与 **01:09–01:18** 那轮（`CHK-20261004-0110-FULL`）相比：**逐把状态完全一致**（同样只有 `l0` 红、同样红 2）。这 20 分钟里闸门读数没有变化。

---

## 4. ★ 逐层收口表（本次核心交付）

**批次 `PIPE-20261003-2354` ｜ 判定口径**：① 层侧落章存在？ ② 记账存在？ ③ 该层 CI 闸门？ ④ 四层审计？ ⑤ **批次窗口内该层数据真的变了吗？**

| 层 | 层侧落章（RUN 时刻） | `dry_run/applied` | CI 该层闸门 | ②d 调用审计 | 窗口内数据落地 | 新鲜度 | **收口判定** |
|---|---|---|---|---|---|---|---|
| **L0** | `PIPE-…-L0-dryrun.json` 23:56:56 | True / False | 🔴 **RED（红 2）** | — | ❌ 无 | 1.8 天 | ❌ **未闭（唯一红的层）** |
| L1 | `PIPE-…-L1-dryrun.json` 23:59:32 | True / False | ✅ PASS | — | ❌ 无 | 2.1 / 1.5 天 | 🟡 机制闭 / **未落盘** |
| L2 | `PIPE-…-L2-dryrun.json` 00:00:46 | True / False | ✅ PASS | — | ❌ 无 | 2.6 天 | 🟡 机制闭 / **未落盘** |
| **L3** | `PIPE-…-L3-dryrun.json` 00:03:03 | True / False | ✅ PASS（闸门自身绿） | — | ❌ 无 | 1.1 / 1.7 天 | ❌ **未闭（数据面，⑥ R4 根因在此）** |
| L4 | `…-L4-dryrun.json` ＋ `…-L4-canonical-dryrun.json` 00:06:44 | True / False | ✅ PASS | ✅ 退出 0 ｜红 0 ｜🟡 E5×1 | ❌ 无 | 1.1 天 | 🟡 机制闭 / **未落盘** |
| L5 | `PIPE-…-L5-dryrun.json` 00:09:47 | True / False | ✅ PASS | ✅ 退出 0 ｜红 0 ｜🟡 E5×1 | ❌ 无 | **4.1 小时** | 🟡 机制闭 / **未落盘** |
| L6 | `…-L6-dryrun.json` ＋ `…-L6-selftest-dryrun.json` 00:18:05 | True / False | ✅ PASS | ✅ 退出 0 ｜红 0 ｜🟡 E5×1 | ❌ 无 | 1.7 天 | 🟡 机制闭 / **未落盘** |
| L7 | **无层侧落章**（编排器自身记账 00:19:28） | — | ✅ PASS | ✅ 退出 0 ｜红 0 ｜⚪ 代码级豁免 | ❌ 无 | — | ✅ 闭（豁免成立） |

**读法（三条，缺一条就会读错）**：
1. **没有哪一层「跑不通」** —— 8 层全部到达，8 个 RUN 记账齐全，四层审计红 0。
2. **L0 与 L3 在数据面没闭上** —— L0 是 CI 唯一红的层（取数身份问题，**不是数据坏**，见 §5.1）；L3 自身闸门绿但正是 ⑥ R4「2036 处治理字段未传导」的**根因所在**（见 §5.2）。
3. **整批零落盘** —— L1–L6 只算「机制闭」。`dry_run=True` 下 `products` 字段列出的数据文件**不是本批写的**（⚠️ 见 §5.4 的误读陷阱）。

### 4.1 ②d 四层 skill 调用审计（逐层一 RUN）
| RUN | 退出码 | 红 | 黄 | 说明 |
|---|---|---|---|---|
| `PIPE-20261003-2354-L4` | **0** | 0 | 🟡 `E5`×1 | 落章来自**预演台账**：只证明「逐层调用机制通了」，**不构成「该层真落盘」的证据** |
| `PIPE-20261003-2354-L5` | **0** | 0 | 🟡 `E5`×1 | 同上 |
| `PIPE-20261003-2354-L6` | **0** | 0 | 🟡 `E5`×1 | 同上 |
| `PIPE-20261003-2354-L7` | **0** | 0 | ⚪ | 豁免 L7：跨层闸门（`kb-check`）不是 L7 层主，且 L7 记账文件结构上不能自证 |

四层 `skill_evidence` 实测均为 **`agent_reported`**、`observed_skills: []`、`layer_stamps_applied: []`
⇒ 按本库纪律，这是**agent 自述档**，**不得当强证据**。

---

## 5. 失败项 / 未判定项清单（对象 + 原因码 + 要人做什么 + 复开条件）

### 5.1【真坏·高·唯一红的层】L0 闸门红 —— 两张表拉不到
- **原因码**：`gate_red.L0`（登记件 `kb/l7/registry/l0-expected-diffs.yaml → resolved → EX-2/EX-3 → observed_20261004`）
- **读数**：`拉取失败 2`、未声明差异 2 条：`专家修订汇总表(tbl8AI00JZO1iZtp)`、`内容公式（仅供参考）(tblVdl0jdK9G4ld3)`
- **性质**：**不是数据错，是取数身份问题** —— bot「守衡」91403 无权限，且回落 user 令牌 `token_missing`。
- **要人做什么**（registry 的 `owner_action` 原文两条）：
  ① 根治（不改代码）：飞书侧把「守衡」bot 加为该 Base 的**可阅读协作者**；
  ② 临时：`lark-cli auth login --profile dsh-kb --domain base --domain wiki`（Device Flow，需人授权）
- **不许做**：把这两条写进 `expected` 声明掉（该文件 `not_exemptable` 明令禁止），或把 `pull_failed` 从四类差异里摘掉。
- **复开条件**：`l0_gate.py` 退出 0（两表 `拉取失败 0`）

### 5.2【真坏·中·已登记根因】⑥ 投影对账 3/6 —— 根因是 **L3 治理字段回填丢失**
- **原因码**：`gate_red.projection_reconcile` ＋ `finding.l3_governance_backfill_lost`（`kb/l7/registry/failure-playbook.yaml`）
- **证据**：`kb/l3/candidates/rules.jsonl`（1018 行）里 `owner`/`effective_from` 键存在但**全空**，`half_life_days`/`valid_until` **键都不存在**；
  而 `kb/l3/registry/l3.json` 的 `changes[2]` **声称**已把这四个字段回填进 509 行 ⇒ **注册表声明与实文件不一致**。
- **要人做什么**：**先补 L3 治理字段**（属报批动作）→ 再重出视图（`kb/l8/build_view.py --out kb/view`，staging + `repack_write.mjs` 明写回填）→ 复跑本闸门与 `l3_gate`。
- **禁止**：按脚本自带 `fix` 提示直接「重跑生成器回填」。实测这是**陷阱**：R4 照样红，且会把逐条治理值（法务 474 / 法务+产品负责人 14 / 法务+渠道负责人 13 / 法务+医学顾问 8；half_life 90/365）**降级成统一常量**、`valid_until` 归零 —— 正是 `kb/l3/registry/half-life-policy.json` 禁止的假绿。
- **复开条件**：`projection_reconcile.py` 退出 0（R1/R2/R4 同时绿）

### 5.3【合法变红·已登记】④ 的第 ②③ 段
- ② 拿冻结快照比活库、③ 拿旧 run 记录的产物哈希当「不许变」基线。活库每天在跑，这种判据**必然** FAIL。
  登记件：`kb/l7/registry/workflow-check-known-drift.yaml`（文件头明写：**今天没有任何闸门读本文件**，登记只为分类留痕，复跑**仍然是 FAIL**）。
- **要人做什么**：把判据从「一个字节都不许动」改成「**改动都能追到出处**」—— 属**改判据，单独走一轮**，不在本次范围内。

### 5.4【口径陷阱·必须写进结论】L5 的 `products` 字段会误导人
- L5 记账把 `kb/l5/p0_patterns.jsonl`、`kb/l5/index/l5.jsonl`、`kb/l5/registry/l5.json` 等列为 `products`，
  但这些文件 mtime 全是 **10-03 21:18**，**早于本批 L5（00:09）** ⇒ 本批一个都没写（`applied=False`）。
- 例外核查：`kb/l5/runs/PIPE-20261003-2354-L5.p0_patterns.superseded.jsonl` 的 **ctime = 00:08:46（落在本批 L5 窗口内）**，
  但其 Birth/Modify = **21:18:13**，且与现役 `p0_patterns.jsonl` **sha256 逐字节相同**（`470e3fbad21489b9…`）
  ⇒ 它是**跑前内容的备份**，**不是新数据**。结论：**不构成数据落地，也非缺陷**，但 `products` 字段的读法必须带 `applied` 一起读。

### 5.5【未判定】③ 路由表对账 —— 且存在**两套不可混用的口径**
- **原因**：缺今日赢家表（运行时会话未曾生成）⇒ 按设计 exit 2（硬拒，非绿非红）。
- **口径分歧（我实测复算，不替人挑）**：同一份 `_eval-kb-manage/blind_v2.winners.txt`（**115 行**）——
  · 不传 `--cases` → 用默认用例集 `~/Desktop/skill/内容治理中文skill/_基线用例.json`（**65 条**）→ **60/65**
  · 传 `--cases _eval-kb-manage/cases_v2.json`（**115 条**）→ **109/115**
  两者分母不同、**不可互相替代**，且都冻结于 **2026-09-29**（已 5 天）。
- **要人做什么**：要今日判定 ⇒ 先按 `kb-manage` 的触发电测重新生成赢家表，再复跑 ③。
- **不许做**：拿 60/65 **或** 109/115 当今日 F1。本表两个数并列，**不做取舍**。

### 5.6【收口缺口·评审链·未判定入口】两条评审结论的判定主体与层前置**都没留痕**
- 对象：`kb/l7/runs/20261004-012126.json`、`20261004-012221.json`（`review_machine`，trigger「FDA 认证，宝宝用了不哭不闹。」，verdict `BLOCK ｜ issue_count=1`）
- 读数：`extra.decision_owner = **null**`、`extra.loaded_skills = **[]**`；对应报告 `kb/l7/reports/20261004-012121.json`、`20261004-012151.json` 的 **`evidence_meta = {}`（空）**，`knowledge_version: v0`
- 纪律后果：按本库防线口径，`evidence_meta` 为空 ⇒ **层前置与判定主体皆未留痕** ⇒ 该结论**不得当 PASS 依据**；
  而它是在「层前置未闭合」的状态下产出的。
- **我无法验证的**：它是走 `waived_by_caller` / `waived_by_api` / `selftest` 哪条入口 —— **本地件未记录该字段**，**不猜**，标**未判定**交人核。
- **要人做什么**：确认这两条结论的入口与用途；若属对外结论，须补层前置 + `--decision-owner` 重出。

---

## 6. 并发观测（本表是**活库时点快照**，不是冻结基线）

- 跑前（01:23:45）：`kb_loop_claim.py status` = **无认领**；`kb/.work/.kb.lock` **不存在**。跑后（01:35）复查：**仍无认领、仍无锁**。
- 但**本表跑表期间确有另一会话在并行打同一个库**：01:24–01:33 新增
  `kb/l7/reports/CHK-20261004-0124-KBCK-health.md`、`CHK-20261004-0130-ALL-health.md`、`CHK-20261004-0133-3GATES-health.md`、`MTG-20261004-0127-health.md`
  与 `kb/l7/runs/20261004-012{1,2,3,4,5}.json` 等 —— **均非本会话产出**。
- **重复记账正在发生（我独立复算，非引用邻居）**：`kb/l7/runs/index.jsonl`
  **总行数 1113 ｜ 唯一 `run_id` 921 ｜ 重复多出 192 行**（`20261002-1940` 落 9 行、`20261002-1939` 8 行…）。
  邻居会话 01:24 读数为 189 ⇒ **10 分钟内又涨 3 行**。本库已登记的并发事故（index 双计、L7 记账被覆盖）**正在持续**。
- ⇒ 本表读数对应**各自命令的运行时刻**（01:25–01:35），**不能**读成「整个库此刻的冻结状态」；
  任何「已跑完 / 已修好」的结论必须带 run_id + 时间戳。
- 本次**未**认领循环锁、**未**跑任何写档链路（`--apply` 一次未传）。

---

## 7. 这份表**不能**拿去说什么（口径边界）

1. ③ 是**未判定**，不是「路由表坏了」；60/65 与 109/115 **都是过期口径**，不得当今日 F1。
2. `l0` 的红**不代表 L0 数据坏了** —— 是取数身份问题（§5.1）。
3. ④ 的 ②③ 是**判据过期**（合法变红），**不是**有人偷改权威库；**不许**当缺陷去「修数据」。
4. ⑥ 的红**不许**按脚本自带 fix 提示直接重生成视图（§5.2 的假绿陷阱）。
5. **「8 层全走完」≠「8 层已收口」**：本批 `dry_run` 全为 True、`applied` 全为 False，数据零落地；
   要落盘证据须带 `--write-gate` 凭据 + `--apply` **单独报批**重跑（§4 读法 3）。
6. 本表**只跑闸门**，**没有**跑 L0→L7 写档链路；`freshness` 的 `health=YELLOW` 不代表真实健康色。
7. 本次**没有**产出任何内容审查结论。

---

## 8. 命令回放（cwd = 库根）

```bash
RUN="CHK-20261004-0125-CLOSE"; D="_chk-run-$RUN"
sh kb/kbpy l7/scripts/freshness.py                                     # 前置：退出 0
sh kb/kbpy l7/scripts/skills_check.py                                  # ① 0
sh kb/kbpy l7/scripts/layers_check.py                                  # ② 0
sh kb/kbpy l7/scripts/routes_reconcile.py "kb/l7/reports/$RUN-routes-winners.json"   # ③ 2（缺输入）
sh kb/kbpy l7/scripts/routes_reconcile.py --alias _eval-kb-manage/blind_v2.winners.txt  # ③b 1（60/65）
sh kb/kbpy l8/workflow_check.py "$RUN"                                 # ④ 1（9 段 2 红，无干跑档）
python3 tools/envelope_gate.py                                         # ⑤a 0
sh kb/kbpy l8/envelope_census.py                                       # ⑤b 0
sh kb/kbpy l8/projection_reconcile.py                                  # ⑥ 1（3/6）
python3 ci/run_gates.py --outdir ci/out                                # CI 12 把：1（红 l0）
# 逐层收口：批次 PIPE-20261003-2354
for L in L4 L5 L6 L7; do sh kb/kbpy l7/scripts/skill_invocation_audit.py --run PIPE-20261003-2354-$L; done  # 全 0
for L in L0 L1 L2 L3 L4 L5 L6 L7; do sh kb/kbpy l7/scripts/freshness.py >/dev/null; done  # 层侧落章见 kb/lx/runs/
sh kb/kbpy l7/scripts/kb_loop_claim.py status                          # 跑前/跑后：无认领
```

**原始读数**：`_chk-run-CHK-20261004-0125-CLOSE/`（0-freshness、1-skills、2-layers、3/3b-routes、4-workflow、5a/5b-envelope、6-projection、audit-PIPE-…-L4/L5/L6/L7）
