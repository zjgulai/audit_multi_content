# workflow_check 修复记录 · `REPAIR-20261004-1226-WF`（第 8 轮）

- **用户指令**：「workflow_check 没过，帮我把失败项按原因码修掉，修完复跑。」
- **交表时点**：`2026-10-04 12:33 CST`
- **库根（cwd）**：`/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理`
- **闸门**：`kb/kbpy l8/workflow_check.py`（门④，无干跑档，跑它即写 `kb/l8/workflow_check_<RUN>.json`）
- **run_id**：修前 `CHK-20261004-1226-WFREP`（`at=12:27:22`）／ 修后 `CHK-20261004-1233-WFREP`（`at=12:30:57`）
- **纪律**：未加 `--apply` / `--write-gate`；未删任何锁或认领文件；**未改任何判据**；未改 `kb/l0~l6` 任何数据或台账；
  **未写任何 run 记录**；未抢循环认领；未重启服务；未向飞书发布任何东西。

---

## 0. 一句话结论（先读这条，它和你的预期不一样）

> **失败项按原因码「修不掉」——不是我没修，是本库登记的原因码明文规定不许这么修。**
> 复跑后 `workflow_check` **9 段里只剩 ②③ 红**，其余 7 段全 PASS。而 ②③ 对应的原因码
> `kb/l7/registry/failure-playbook.yaml → gate_red.workflow_check` 写着：
> 「②③ 属**已登记判据漂移** ⇒ **无需修数据**；要它们转绿必须**改判据，单独走一轮**」，
> 且该条 `forbidden` 明写「不许为了让 ②③ 变绿去改写历史 run 记录里的 artifact sha」「不许把 L3 回滚到 1527 行时代」。
> ⇒ 本轮按原因码的 `reopen_when` 走了**合规的默认动作＝只登记**（「基线漂移，非缺陷」+ 附原始读数）。
> **真正需要你点头的那个决定，见 §5**——同一个决定已连续 8 轮无人回答。

---

## 1. 修前 / 修后 同一条闸门对照（退出码与逐段判定）

**修前**：`sh kb/kbpy l8/workflow_check.py CHK-20261004-1226-WFREP` → **退出码 1**
**修后**：`sh kb/kbpy l8/workflow_check.py CHK-20261004-1233-WFREP` → **退出码 1**

| 段 | 修前 | 修后 | 本轮动作 |
|---|---|---|---|
| ① 环境与版本纪律 | PASS | PASS | — |
| **② 权威库 l0~l6 未被改动** | **FAIL** | **FAIL** | 只登记（原因码明令不许修数据） |
| **③ 前序产物哈希（45 项）** | **FAIL**（20 项 mismatch） | **FAIL**（同 20 项） | 只登记 ＋ 补做来源审计 |
| ④ 分层库 → 生成器 → 视图 | PASS | PASS | — |
| ⑤ 装载位 → 加载器（读工具+体检） | PASS | PASS | — |
| ⑥ 文档可见性（agent 能否读到） | PASS | PASS | 上轮实质红**已修且未复发**（独立复核见 §2.3） |
| ⑦ 消费侧 skill 可用 | PASS | PASS | — |
| ⑧ 工作台与服务 | PASS | PASS | — |
| ⑨ 写入侧（ingest 闸门 + 落盘通道） | PASS | PASS | — |
| **裁决** | **FAIL** | **FAIL** | — |

**逐段读数比对**（脚本实测，非肉眼）：两次运行的 `legs[①…⑨].detail` 以
`json.dumps(..., sort_keys=True, ensure_ascii=False)` 逐段比对 ⇒ **9/9 `identical`**
⇒ 本轮登记**没有引入任何回归**，也**没有改变任何判据**（预期之内：本文件不被任何闸门读）。

**修后闸门输出（原文）**：

```
知识库工作流体检 · CHK-20261004-1233-WFREP · 2026-10-04 12:30:57
  PASS  ① 环境与版本纪律
  FAIL  ② 权威库 l0~l6 未被改动
  FAIL  ③ 前序产物哈希（45 项）
  PASS  ④ 分层库 → 生成器 → 视图
  PASS  ⑤ 装载位 → 加载器（读工具+体检）
  PASS  ⑥ 文档可见性（agent 能否读到）
  PASS  ⑦ 消费侧 skill 可用
  PASS  ⑧ 工作台与服务
  PASS  ⑨ 写入侧（ingest 闸门 + 落盘通道）
  裁决：FAIL（未过：['② 权威库 l0~l6 未被改动', '③ 前序产物哈希（45 项）']）
```

**同时复跑登记表闸门**（因为本轮动了 `kb/l7/registry/*.yaml`，按 kb-repair 铁律必须复验）：
`sh kb/kbpy l7/scripts/skills_check.py` → **五类问题 `1=0 2=0 3=0 4=0 5=0 ｜合计 0`，退出码 0，结论「全过」**。

---

## 2. 第 8 轮独立复算（**不采信库内既有自述**，四项全部重做）

### 2.1 ② 段：L3 两条子判据「数学上不可能为真」（独立重算）

| 量 | 实测值 |
|---|---|
| `kb/l3/candidates/rules.jsonl` 行数 | **1018**（mtime `2026-10-02 22:45:07`） |
| 整文件 sha256 | `743dc62398311b0287e1e99fbcc438397ca8c721a0556d534cc69f3ee6eff840` |
| `sha(lines[:1018])` | 同上 ⇒ **== 整文件**（`True`） |
| `sha(lines[:1527])` | 同上 ⇒ **== 整文件**（`True`） |
| 基线 A：`kb/.work/l6_integrity.json` | `7d00454e80e2a1cc…`，自报 `lines=2036`（**2036 行时代**的整文件哈希） |
| 基线 B：`kb/l4/runs/20260923-1445.json` | `aa83d1f98bc86857…`（**09-23 / 1527 行时代**的整文件哈希） |

判据代码 `kb/l8/workflow_check.py:112-125` 的形态是「**前缀哈希** == **历史整文件哈希**」。
活库只有 1018 行 ⇒ 两条「前缀」都退化成整个文件 ⇒ 与两条**不同行数时代**的整文件哈希
**结构上不可能相等**（除非把 L3 回滚到 09-23，而那是 `forbidden`）。
且现行 sha 有出处：它就写在 `kb/l3/registry/l3.json` 的
`appended_fields.old_lines_untouched.sha256`（与活库逐字节一致）⇒ **这是「变了」，不是「坏了」**。

### 2.2 ③ 段：20 项 mismatch 的来源审计（独立扫 **1767** 份 run 记录）

本轮递归读取 `kb/l*/runs/*.json` 的**全部** `artifacts[]`（只读原始记录），对 20 项逐项问
「活库现 sha 是否被某条 run 记录记过」：

- **17/20 有来源**（现 sha 被更新的 run 记录记过；最新基本停在并发会话的 `RVW-LISTING-20261004-L{4,5,6}`）
  —— 例：`kb/l3/candidates/rules.jsonl` 40 条、`kb/l5/registry/l5.json` 48 条、`kb/l6/bm25/docs.jsonl` 44 条。
- **3/20 无 run 落章**：`kb/l7/registry/l7.json`、`kb/l7/skills/kb-content-review/SKILL.md`、
  `kb/l7/skills/kb-content-review/scripts/review.py` —— 与第 4–7 轮**逐项一致**。

★ **第 8 轮新增证据（前 7 轮没做过的这一层）**：对 20 项逐项做 `os.path.exists` 实测 ⇒
**20/20 全部存在、无一缺失**。判据只报「sha 不符」，**不区分「改了」与「没了」**；
本轮把这两种情形**分开验**，结果是**全是「改了」** ⇒ 连「有人偷删产物」这一层也一并排除。

### 2.3 ⑥ 段与信封面：实质红已修且未复发（独立复核）

- `workflow_check` 段⑥：**PASS**（不可读 510 个**全在判据本就容忍的** `他人产物 hostlib` 桶，`其他` 桶 = **0**）。
- 加宽口径独立复核：`python3 tools/envelope_gate.py --reader consumer .` ⇒
  扫 **2973** 个、**信封态 0**、**读不到 0**、退出码 **0**。
- ⇒ `11:47:15` / `11:53:38` 那两只信封态 `.md`（`_eval-L0L7-gap-20261003/` 下）
  **已由并发会话在 `12:14–12:16` 用 cp 通道修掉，本轮复核未复发**。

### 2.4 `kb/l7/registry/l7.json`「原地改写未落章」那一项（真发现，独立复验成立）

与 pre-edit 备份 `kb/l7/_backups/batch18b-20261002-1201/l7.json.pre-edit` **逐字段**比对：

```
changed fields: 1
  .article_no_source.field_lives_in
    pre : …（定稿，四个形态文件）…
    post: …（定稿，五个形态文件）…
run_id: 20260923-1500  |  article_no_source.read_at: 2026-09-30 17:45:27
```

⇒ 差异**恰好 1 个字段、一处措辞**，是一次**内容上正确的声明点更正**，但**没有 run 记录落章**。
**定性：合法改动 + 流程缺落章**（不是无人认领的黑改）⇒ 这是 ③ 里**唯一**的真流程缺陷。

---

## 3. ★ 两处对库内既有分析的**更正**（第 8 轮新发现）

### 更正 1：`real_findings[0].impact` 那句是**单位不可比**的误报

原文（已撤回）：「该块的计数与叙述已落后于现库：`total_rules` 自报 632，而 L3 现为 1018」。

- `632` = **规则类形态条数**的**跨文件**计数：`wording_entry 56 + wording_revision_pair 453 + external_standard_clause 123 = 632`。
- `1018` = `kb/l3/candidates/rules.jsonl` 的**行数**（509 条 × 2 行）。
- 第 8 轮实测：`rules.jsonl` 1018 行 ⇒ 509 条；`external_standard.jsonl` 246 行 ⇒ 123 条
  ⇒ **现库仍正好 632**。
- ⇒ **`total_rules` 并没过期**；原句把一个没坏的数字报成了「落后」。

### 更正 2：真正过期的字段是另外 6 个（以干跑差异清单为准）

干跑（**未加 `--apply`，零写盘**）`kb/.work/l7_article_source_refresh.py CHK-20261004-1226-WFREP` 实测差异：

| 字段 | 旧 → 新 |
|---|---|
| `total_outputs_note` | canonical 落盘 **1242 → 1365** |
| `candidate_rows` | **1997 → 2730** |
| `field_lives_in` | 措辞进一步精确化（「五个形态文件」→ 显式列名 + 迁移留痕说明） |
| `read_at` | `2026-09-30 17:45:27` → 本次 |
| `read_at_previous` / `candidate_rows_note` / `refreshed_by` | 随之更新 |

**`total_rules` 不在差异清单里** ⇒ 与「更正 1」**互证**。
⇒ 「计数落后现库」这个判断本身成立，但**落后的是 `total_outputs_note` / `candidate_rows`，不是 `total_rules`**。

---

## 4. 失败项清单（对象 ＋ 原因码 ＋ 分类 ＋ 本轮动作 ＋ 复开条件）

| # | 对象 | 闸门·退出码 | 原因码 | 分类 | 本轮动作 | 复开条件 |
|---|---|---|---|---|---|---|
| RED-1 | ② 段两条 L3 子判据（前缀哈希 vs 历史整文件哈希） | ④ `exit 1` | `gate_red.workflow_check`（判据过期） | 🟡 **合法变红**（基线漂移，非缺陷） | 只登记 ＋ 独立重算证明「数学上不可能为真」 | 授权改判据后复跑 `exit 0`（见 §5 (A)） |
| RED-2 | ③ 段 20 项 mismatch | ④ `exit 1` | 同上 | 🟡 **合法变红**（17/20 已溯源）＋ **1 项真流程缺陷** | 只登记 ＋ 来源审计 ＋ 存在性实测（20/20 存在） | 同上；流程缺陷见 RED-3 |
| **RED-3** | `kb/l7/registry/l7.json` 原地改写**未落章**（计数与快照落后现库） | ④ `exit 1`（③ 内一项） | `real_findings.l7_registry_inplace_write_without_run_record` | 🔴 **真坏**（流程缺落章，非数据损坏） | **未动** —— 修它要开闸写档，须授权 | 跑 `l7_article_source_refresh.py <RUN> --apply` ＋ 补 L7 run 记录 |
| AMB-1 | ④ 段⑦⑧⑨等 7 段 | — | — | ✅ 全 PASS | 无需动作 | — |
| GAP-1 | ⑥ `R4` 判据**不覆盖** `p_level`/`risk_level` 实质分歧 | — | 判据覆盖面缺口 | ⚠️ **判据缺口**（非数据缺陷） | 只登记（在 `failure-playbook.yaml:187` 条目下） | 加判据属机制改动，须报批 |

**⚠️ 一处必须点明的口径**：RED-1 / RED-2 的「合法变红」**不提供任何当前健康信息** ——
既不是坏消息，**也不是好消息**。活库模式下 ②③ **拿不到绿**，所以
**不能把它们的 FAIL 读成「权威库被动过」，也不能把「已登记」读成「权威库没问题」**。

---

## 5. ★ 未决决定（**本单唯一卡点**，已连续 8 轮无人回答）

**能让 ②③ 变绿的路只有一条**：按 `workflow-check-known-drift.yaml → stale_criteria[].owner_action`
改 `kb/l8/workflow_check.py` 的 ②③ 两段判据（改成「**最新 run 记录 + 来源审计**」，查不到出处的改动**仍判红**）。
`failure-playbook.yaml → gate_red.workflow_check` 的 `forbidden` 明写这条要**单独走一轮并报批**，
故本轮**只登记、不动手**。请裁：

| 选项 | 内容 | 效果 |
|---|---|---|
| **(A)** | **授权改判据**（②③ 两段共约 15 行）＋ 补那 3 项落章；**含强制反向测试**：故意原地改一个层产物、不落章 ⇒ 新判据必须**仍判红** | **唯一能让闸门变绿的选项** |
| **(C)** | 只补 3 项落章（跑 `l7_article_source_refresh.py --apply` ＋ 补 L7 run 记录） | **数据卫生**（消掉 RED-3），但 ③ 仍有 **17 项** mismatch、② 两条仍假 ⇒ **复跑照样 FAIL** |
| **(B)** | 维持现状 | ②③ 长期红、体检恒 FAIL，只登记 |

**选项 (A) 的可落地草案**（`workflow-check-known-drift.yaml → option_A_impl_sketch`，**未应用，等批**）：

- **② 段新判据**：l0/l1/l2 **仍比 L5 基线**（这三棵树今天实测相符，判据有效，**不动**）；
  L3 改成「活库 sha 若能在**不早于** `kb/l3/registry/l3.json` 声明的最近一次演进的 run 记录里查到出处，
  记『**已溯源的演进**』（照打读数、不定红）；查不到出处才判红」。
- **③ 段新判据**：基线从「2026-09-23 那四份固定 run 记录」换成「**最新**一次申报该产物 sha 的 run 记录」；
  **查不到任何 run 记录出处**的改动**仍判红**（即 `l7.json` 那类「原地改写未落章」**照红**——**绊线不许一起拆掉**）。
- **反向测试（必做，否则等于把绊线拆了）**：① 故意原地改一个层产物、**不落章** ⇒ 新判据**必须仍判红**；
  ② 跑一次正常链路（产物 ＋ 落章）⇒ 新判据必须**绿**。①不过就不许合入。
- **成本**：改 `kb/l8/workflow_check.py` ②③ 两段（约 15 行）＋ 一个反向测试；**不动任何 `kb/l0~l6` 数据**。

**为什么本轮不能自己拍**：

1. **纪律层**：原因码 `forbidden` 明写「不许就地改宽 ②③ 的判据而不同时报批（改判据要单独走一轮）」。
2. **权限层**：本会话是**被委派的子 agent**，`ask_user_question` 被宿主**拒绝**
   （原文「human interaction is unavailable while the calling agent is owned by another live agent」）
   ⇒ **问不到人**，决定只能原样带回委派方。**未授权 ⇒ 未动判据、未改数据、未写 run 记录。**
3. **并发层**（第 8 轮实测）：跑闸门时**另有活会话在探测同一道闸门**
   （pid `59341`/`59348` 在跑 `kb/l8/workflow_check.py --help`），且 `12:24–12:28` 有
   `P0MILK-20261004-1219` 的 L4/L5/L6/L7 run 记录**连续落盘**；
   `kb_loop_claim.py status` 报「陈旧（可 `--take-over`）」但**确有活进程在写库**
   ⇒ 即便拿到 (A)/(C) 授权，**也要等这个会话收工**才能补落章。本轮**不抢、不 claim、不写任何 run 记录**。
   ⚠ 与第 6/7 轮同一条教训：**「陈旧认领」≠「槽是空的」**。

---

## 6. 变更记录（改了哪些文件 ＋ 五问 ＋ 回滚）

**本轮唯一实质改动**：`kb/l7/registry/workflow-check-known-drift.yaml`（**登记文件**，第 8 轮追加 ＋ 一处更正）

| 五问 | 答 |
|---|---|
| **读者** | 跑 `kb-check` 体检档的人 / 看 `workflow_check` 报告的人 / 准备把 ②③ 修绿的人 / 写日报的人 |
| **写者** | 本轮 kb-repair 会话；后续由维护 `kb/l7/registry` 的人按 `owner_action` 更新 |
| **判据** | 本文件**不改变任何闸门判定**（今天**没有任何脚本读它**，文件头已明写 `read_by_gate: none`）；它只把 ②③ 的失败定性为「判据过期」并留证 |
| **通道** | `edit` 工具写 `.yaml`（`.yaml`/`.json` 不走 4096 字节信封）；**写后已按两读者核对**：python `getsize` = node `statSync().size` = **49604** ⇒ 无信封 |
| **回滚** | `cp kb/l7/_backups/kb-repair-workflow-R8-20261004-1226/workflow-check-known-drift.yaml.before kb/l7/registry/workflow-check-known-drift.yaml`；或 `rm` 本文件回到第 7 轮登记前状态 |

**未改动、且必须保持未改动的**（原因码 `forbidden` 明令）：

- ❌ 未改 `kb/l8/workflow_check.py`（判据原样；备份对比：`workflow_check.py.before` sha `e5cb3ee6…` == 现文件）
- ❌ 未改写 `kb/l4|/l5|/l6|/l7/runs/20260923-*.json` 里的 artifact sha（那是伪造台账）
- ❌ 未回滚 L3 到 1527 行时代（那是毁掉 2026-10-02 的蒸馏成果）
- ❌ 未改 `kb/.work/l6_integrity.json` 的历史哈希
- ❌ 未碰 `kb/l0~l6` 任何数据与台账；未写任何 run 记录

**回滚基线**：`kb/l7/_backups/kb-repair-workflow-R8-20261004-1226/`

```
c19a32a30e10e720c4f574828e1a2b1a2f542ab55bc90373692616dda4495ede  workflow-check-known-drift.yaml.before
e5cb3ee62f05a949cde552d3ce715db4f64a7ae0caaa1dd3eb4a9dcc78121053  workflow_check.py.before
```

---

## 7. 写盘清单（先声明再跑）

| 路径 | 什么 |
|---|---|
| `kb/l8/workflow_check_CHK-20261004-1226-WFREP.json` | 门④ 无干跑档，跑它即写（修前） |
| `kb/l8/workflow_check_CHK-20261004-1233-WFREP.json` | 同上（修后复跑） |
| `kb/l7/registry/workflow-check-known-drift.yaml` | 本轮唯一实质改动（登记 ＋ 更正） |
| `kb/l7/_backups/kb-repair-workflow-R8-20261004-1226/` | 回滚基线 |
| `_repair-run-REPAIR-20261004-1226-WF/` | 本目录：9 份原始证据 |
| `workflow_check-修复记录-20261004-1226.md` | 本文件（工作区根 ＋ `kb/l7/reports/` 各一份，`/bin/cp` 通道落盘） |

**可复现命令**：

```bash
cd "/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理"
sh kb/kbpy l8/workflow_check.py <RUN>                    # ②③ 原始读数（仍是 FAIL）
sh kb/kbpy l7/scripts/skills_check.py                    # 五类全 0 / 退出码 0
python3 tools/envelope_gate.py --reader consumer .       # 信封态 0 / 退出码 0
sh kb/kbpy .work/l7_article_source_refresh.py <RUN>      # 干跑：l7.json 的 6 字段差异（不加 --apply）
python3 -c "import hashlib;p='kb/l3/candidates/rules.jsonl';print(hashlib.sha256(open(p,'rb').read()).hexdigest())"
```

---

## 8. 一句话收口

> **我按原因码执行了：原因码说 ②③「无需修数据、要绿必须改判据（单独报批）」，我就没动数据、没动判据，只做了登记 ＋ 独立复算。**
> **复跑结果与修前逐段 identical（9/9），闸门仍 FAIL 在 ②③ —— 这是预期内的「合规不变绿」。**
> **本轮带回的不是重复：新增了「20/20 产物存在、无一被删」这条排除性证据，并更正了库内一处单位不可比的误报（`total_rules` 并没坏）。**
> **要真变绿，请你拍 §5 的 (A)——那份改法的草案已经写好了，批了就能落地。**
