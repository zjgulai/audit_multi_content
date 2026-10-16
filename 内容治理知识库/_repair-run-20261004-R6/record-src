# workflow_check 修复记录 · 2026-10-04 10:15 · RUN `REPAIR-20261004-R6`

**同一条用户指令的第 6 轮**（前 5 轮：`REPAIR-REPRO-20261004-0020` / `REPAIR-20261004-0146` /
`CHK-20261004-REPAIR-BEFORE` / `REPAIR-20261004-R5`，登记在 `kb/l7/registry/workflow-check-known-drift.yaml`）。

---

## 0. 结论（先说结果）

1. **本轮没有把 workflow_check 修绿，而且按原因码它就不该被"修绿"。**
   红的只有 ② 与 ③ 两段，原因码 = **「冻结基线 vs 活库漂移 / 判据写死在一个已经过去的时点」**，
   按 `kb-repair` §2 第 8 行 ⇒ **合法变红，写"基线漂移"结论，不要"修"**；
   按 `failure-playbook.yaml → gate_red.workflow_check` ⇒ **②③ 属判据过期，无需修数据**。
2. **7/9 段 PASS，无新的实质红**（第 5 轮起 ⑥ 段已转绿，本轮复测仍绿）。
3. **能让闸门变绿的只有一条路** = 改 `kb/l8/workflow_check.py` 的 ②③ 判据；
   该动作被 `failure-playbook.yaml` 的 `forbidden` 明令**要单独走一轮并报批** ⇒
   **本会话未获授权，不动手**，原样上报（见 §7）。
4. 本轮**没有**"为了让它变绿"去改任何历史哈希、回滚 L3、或改宽判据。

---

## 1. 输入：一条已红的闸门（必需，否则该走 kb-check）

```
知识库工作流体检 · CHK-20261004-1012-ISO · 2026-10-04 10:09:42
  FAIL  ② 权威库 l0~l6 未被改动
  FAIL  ③ 前序产物哈希（45 项）
  裁决：FAIL（未过：['② 权威库 l0~l6 未被改动', '③ 前序产物哈希（45 项）']）
```

## 2. 失败项 → 原因码 → 修法（逐条）

| 失败项 | 真因（本轮实测） | 原因码 | 按码的修法 | 本轮做了什么 |
|---|---|---|---|---|
| ② `l3_base1018_matches_L6` / `l3_whole1527_matches_L4` | 判据**拿前缀哈希比整文件哈希**，两条基线分属 2036 行与 1527 行时代 | 冻结基线漂移 / 判据过期 | **不修**（改判据要报批） | 独立重算证实"结构上不可能为真"，登记 |
| ② `l0/l1/l2 tree` | **三项全 match**（不是失败点） | — | — | 照打读数 |
| ③ 20/45 mismatch | 基线取自 **2026-09-23 四份历史 run 记录**，之后 L3→L7 每层都被合法重建过 | 同上 | 同上 | 逐项来源审计：17 有来源 / 3 无落章 |
| ③ `kb/l7/registry/l7.json` 一项 | **真发现**：原地改写**未落章**（mtime 10-02 12:02:35，`run_id` 仍自报 `20260923-1500`） | 不是假红，是**流程缺落章** | 开闸后跑 `l7_article_source_refresh.py <RUN> --apply` + 补 L7 run 记录 | **未做**（写 run 台账属开闸动作，且活库正被另一会话写） |

## 3. 独立复算（不采信登记文件的自述）

### 3.1 ② 的 L3 算术 —— 独立重算

```
L3 lines           = 1018
L3 whole sha256    = 743dc62398311b0287e1e99fbcc438397ca8c721a0556d534cc69f3ee6eff840
L3 [:1018] sha256  = 743dc623…  == whole ? True      ← 现行文件恰好 1018 行
L3 [:1527] sha256  = 743dc623…  == whole ? True      ← 与上一条同值
L6 基线 sha        = 7d00454e80e2a1cc…  lines=2036  (kb/.work/l6_integrity.json, checked_at 2026-10-02 00:10:57)
L4 基线 sha        = aa83d1f98bc86857…  (kb/l4/runs/20260923-1445.json, 1527 行时代)
l3.json 自记        = 743dc623…  (appended_fields.old_lines_untouched.sha256)
```

⇒ 两条子判据要比的是 `743dc623…` vs `7d00454e…` / `aa83d1f9…`，
**在不回滚 L3（= 不得毁掉 2026-10-02 那轮蒸馏）的前提下数学上不可能相等**。
判据代码：`kb/l8/workflow_check.py:115-116,124-125`。
且活库 L3 的现 sha **就写在它自己的注册表里** ⇒ 这是"变了且有出处"，不是"坏了"。

### 3.2 ③ 的来源审计 —— 独立扫 `kb/l*/runs/*.json` 共 **1677** 份

只读原始 `artifacts[]`（不采信任何脚本自述），对 20 项 mismatch 逐项问
"活库**现** sha 是否被**某条 run 记录**记过"：

- **17/20 有来源**，且多数不止一条；最新的一条基本停在 **`RT-20261004-LISTING-L{4,5,6}`**（10:07–10:13）
  —— 那是**本轮的并发会话**在推库，正是"判据恒红"的机制本身。
- **3/20 无 run 落章**：`kb/l7/registry/l7.json`、`kb/l7/skills/kb-content-review/SKILL.md`、
  `kb/l7/skills/kb-content-review/scripts/review.py`。
  后两者有**文档出处**（`kb/l7/registry/report-output-contract.yaml` 的 `applied_20261003`
  `where_written` / `three_defenses_20261003`：2026-10-03「防线1 入口唯一化」＋「层前置」正文改动）。
- 与第 4/5 轮的 **17/3 划分逐项一致**。

### 3.3 `l7.json` 那一项 —— 逐字段实测（唯一带流程缺陷的一项）

```
cur sha: b36c86f74d86a0a7904bcc472e448f805c9bdcadde41904727f5272c20354159   mtime 2026-10-02 12:02:35
pre sha: 766ac16b2e3ed104918df46926214a4843ad0d36c3a05a5f7a86a143031d90f0   (kb/l7/_backups/batch18b-20261002-1201/l7.json.pre-edit)
field-level diffs: 1
   /article_no_source/field_lives_in
     pre : …canonical/*.jsonl（定稿，四个形态文件）+ …
     cur : …canonical/*.jsonl（定稿，五个形态文件）+ …
现 sha 被两份后续备份清单独立记过：kb/l7/_backups/{conclusion-destination-20261002-225030,
report-output-contract-20261002-230616}/kb_l7_registry.{pre,after}-state.sha256
```

⇒ 定性：**合法改动（内容正确）+ 流程缺落章**，不是"没人认领的黑改"。
缺的只有 `kb/l7/runs/*.json` 的 `artifacts[]` 落章。

## 4. 改了什么 / 没改什么

| | 文件 | 动作 |
|---|---|---|
| ✅ 改 | `kb/l7/registry/workflow-check-known-drift.yaml` | **登记**第 6 次复现（`raw_readings.repro_runs` 追加 1 条、`meta.last_reverified` 与 `pending_decision.still_unanswered_at` 更新、把 (C) 的真实效果写明）。**该文件今天没有任何脚本读它**（实测：全库仅 2 处散文引用，无代码 reader）⇒ **不改变任何闸门语义** |
| ✅ 写 | `kb/l8/workflow_check_REPAIR-20261004-R6{,POSTEDIT}.json` | 闸门自身产物（跑闸门必然落盘） |
| ✅ 写 | `_repair-run-20261004-R6/`（工作区） | 本轮证据 |
| ✅ 写 | `kb/l7/_backups/kb-repair-workflow-R6-20261004-1015/` | 回滚基线 |
| ❌ 未改 | `kb/l8/workflow_check.py` | **判据一行未动**（要报批） |
| ❌ 未改 | `kb/l0`–`kb/l6` 任何数据 | 数据一行未动 |
| ❌ 未改 | 四份历史 run 记录里的 artifact sha | 未伪造台账 |
| ❌ 未写 | `kb/l7/runs/*.json` 与 `runs/index.jsonl` | 未抢循环、未补落章 |

## 5. 变更协议 5 问（kb-repair 铁律①：答不出就不许动）

| 问 | 答 |
|---|---|
| **读者** | 跑 kb-check 体检档的人 / 看 workflow_check 报告的人 / 下一轮准备"修 ②③"的人 / 写日报的人 |
| **写者** | 本会话（kb-repair 第 6 轮）；后续由维护 `kb/l7/registry` 的人按 `owner_action` 更新 |
| **判据** | 本文件**不改变任何闸门判定**（无脚本读它）；它只把 ②③ 定性为判据过期并留第 6 次证据 |
| **通道** | `edit` 工具（`.yaml` 不走 4096 字节信封；改完 `yaml.safe_load` 复核通过、6 条 repro_runs） |
| **回滚** | `cp kb/l7/_backups/kb-repair-workflow-R6-20261004-1015/workflow-check-known-drift.yaml.before kb/l7/registry/workflow-check-known-drift.yaml`（BEFORE.sha256 = `041e5c4dd952796368075e18b4a0e47fe4de5f271906cfd8063dab1f1e10748f`） |

## 6. 复跑证据（同一条闸门）

| 时点 | RUN | 结果 | 逐段比对 vs R6 |
|---|---|---|---|
| 修前（第三方跑） | `CHK-20261004-1012-ISO` @10:09:42 | FAIL（②③） | ②③ `identical: True` |
| 修前（本轮） | `REPAIR-20261004-R6` @10:13:05 | **FAIL（②③）**，exit 1 | 基线 |
| 修后·登记完 | `REPAIR-20261004-R6-POSTEDIT` @10:15:40 | FAIL（②③） | ②③ `same`；⑥ 仅 md 计数 6231→6232（并发会话加文件），**ok 均 True** |
| 修后·全写盘完 | `REPAIR-20261004-R6-FINAL` @10:17:10 | FAIL（②③ **＋⑧**） | ②③ `same`；**⑧ 翻红 —— 见 §9，探针脆性** |
| 修后·⑧ 复现性 | `REPAIR-20261004-R6-FINAL2` @10:19:23 | FAIL（②③） | ⑧ 回到 PASS ⇒ 上一条确为偶发 |

读数文件：`02-legs-overview.json` / `03-failed-legs-detail.json` / `06-postedit-rerun.out` /
`07-final-rerun.out` / `08-leg8-recheck.out`。
另跑 `skills_check.py` ⇒ **五类全 0、退出 0**（登记未污染登记表自检）；
`tools/envelope_gate.py` ⇒ **正常 1959 ｜ 信封态 0 ｜ 读不到 0，退出 0**；
本记录这个 .md 单独核验 ⇒ 信封 0（走 `cp` 通道交付）。

**"修好了"的判据本轮是**：②③ **照旧红**（这是对的）＋ **其余 7 段不因本轮改动而变红** ＋
登记文件 YAML 可解析 ＋ `skills_check` 五类全 0。**不是**"闸门 exit 0"。

## 7. ★ 未决事项：仍然卡在一次人的点头（第 6 轮）

`failure-playbook.yaml → gate_red.workflow_check.owner_action` 写死的顺序是"改判据要单独走一轮"，
`forbidden` 明写「**不许把 ②③ 的判据就地改宽而不同时报批**」。
**本会话是被委派的子 agent —— `ask_user_question` 被宿主拒绝**
（原文：`human interaction is unavailable while the calling agent is owned by another live agent`），
**第 6 轮仍问不到人** ⇒ 已把决定原样带回委派方。

请裁：

- **(A) 授权改判据** —— **唯一能让闸门变绿的路**。改 `kb/l8/workflow_check.py` 的 ②③ 为
  「**最新** run 记录 + **来源**审计」（查不到出处的改动仍判红），并做**反向测试**：
  故意原地改一个层产物、不落章 ⇒ 新判据**必须仍判红**。同时要给那 3 项补落章，否则按新判据它们仍红。
- **(B) 维持现状** —— ②③ 长期红、体检恒 FAIL，本轮只是登记 + 复跑。
- **(C) 只补 3 项落章** —— ★ **注意：这不会让闸门转绿**。补齐后 ③ 仍有 **17 项** mismatch
  （判据比的是 09-23 的四份固定历史记录），② 两条仍是假 ⇒ 复跑照样 FAIL。
  (C) 是**数据卫生**（消掉"未落章"这个流程缺陷），不是本次「修完复跑」能收口的那条路。

**走 (A)/(C) 的前置警告（第 6 轮新增实测）**：`kb_loop_claim.py status` 报的「陈旧（可 --take-over）」
**是假象** —— 认领记的 pid 49228 已不在，但**同一 BASE 的活进程仍在写库**
（实测 pid 57201 在跑 `kb_pipeline.py --sync --via-skill --only L6 --gate-only`，10:07–10:13 连续落
L4/L5/L6 的 run 记录）⇒ **"陈旧认领" ≠ "槽是空的"**，动手前必须先确认活进程真的停了，否则就是并发双写。

## 8. 并发披露（诚实写全）

跑闸门与复跑时，**另一会话正持循环认领在写库**：`kb/.work/.kb-loop-claim.json` 记
base `RT-20261004-LISTING`（pid 49228）；`.kb.lock` 记 `RT-20261004-LISTING-L6` / pid 57201；
实测 pid 57201 在跑 L6 gate-only，并在 10:07–10:13 落了 L4/L5/L6 的 run 记录。
⇒ ③ 的"最新来源"里那些 `RT-20261004-LISTING-*` 就是它写的。
**本轮 RUN 名各不相同，未与它抢任何文件，未碰 `kb/l7/runs` 与 `runs/index.jsonl`，
未使用 `--take-over`。** ⑥ 段的工作区 md 计数会随它波动（6231→6232→6233），属已知正常。

## 9. ★ 第 6 轮新发现：⑧ 段是**探针脆性**，不是服务不可用（未擅自改）

第 4 次复跑（`...-FINAL` @10:17:10）⑧ 段翻红。**当场诊断，不是数据缺陷、也不是我改出来的**：

| 证据 | 读数 |
|---|---|
| 翻红那一次的 detail | `workbench_4317 = "000"`（curl 在 4s 内**没拿到状态码**）、`4508/health = 200`、`launchd_jobs = 5` |
| 立刻手工探活（同参数 `--max-time`） | 第 1 次 `000`、第 2/3 次 **200** |
| 之后连测 12 次（同 `--max-time 4`） | **200 × 12，非 200 = 0** |
| 端口与进程 | `127.0.0.1:4317` **在 LISTEN**（pid 2827，`/Applications/DSH Desktop…`）；`4508` 亦在听 |
| launchd | `com.workbench.app` = 2827（上次退出码 -15，即历史某次被 SIGTERM；当前在跑） |
| 同一条闸门 4 次连跑的 ⑧ | 200 / 200 / **000** / 200 ⇒ **偶发率 1/4** |

⇒ 根因是**判据实现脆**：⑧ 只 `curl` **一次**、`--max-time 4`、**无重试**，工作台瞬时拥塞
（当时并发会话正在密集写盘）就会把"服务活着"读成"服务死了"。**服务本身没停**。
⇒ 这属**实质判据**（不是 ②③ 那类冻结基线），但它红的原因是**探针**而不是被检对象。
**修法**（改 `kb/l8/workflow_check.py` 的 ⑧：`curl` 重试 2–3 次、短退避，只有**连续失败**才判红；
语义不变：服务真停仍判红）—— 与 ②③ 一样是**改闸门**，按纪律**要单独走一轮并报批**，
且要动的是**同一个文件**（`kb/l8/workflow_check.py`），故**本轮并入 §7 的待批项，未擅自改**。
在此之前：⑧ 偶发红**应复跑确认**再当天故障处理，不要直接当服务故障去重启 workbench。

## 10. 回滚

```bash
cd "<库根>"
cp kb/l7/_backups/kb-repair-workflow-R6-20261004-1015/workflow-check-known-drift.yaml.before \
   kb/l7/registry/workflow-check-known-drift.yaml
shasum -a 256 kb/l7/registry/workflow-check-known-drift.yaml   # 应为 041e5c4dd952796368075e18b4a0e47fe4de5f271906cfd8063dab1f1e10748f
rm -rf _repair-run-20261004-R6 kb/l8/workflow_check_REPAIR-20261004-R6*.json
# 备份内另存 kb/l8/workflow_check.py.before（本轮未改它，仅作对照）
```

## 11. 本轮产出的证据清单

| 文件 | 内容 |
|---|---|
| `01-workflow_check.out` | 第一次跑（R6）完整输出 + exit |
| `02-legs-overview.json` | 9 段 ok/FAIL 总览 |
| `03-failed-legs-detail.json` | ②③ 的原始读数（机器可读） |
| `06-postedit-rerun.out` | 登记后复跑 + envelope_gate + skills_check |
| `07-final-rerun.out` | 全部写盘完成后复跑（⑧ 在这里偶发红） |
| `08-leg8-recheck.out` | ⑧ 复现性验证（回到 PASS） |
| `record-src` | 本记录的源（无扩展名，经 `cp` 落到 .md，避免信封态） |

