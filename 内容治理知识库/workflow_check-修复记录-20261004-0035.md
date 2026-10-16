# workflow_check ②③ 修复记录（2026-10-04 · kb-repair）

- 库根：`/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理`（cwd = 库根）
- 解释器：`kb/kbpy`；闸门：`kb/l8/workflow_check.py`（**无干跑档**，跑一次写一份 `kb/l8/workflow_check_<RUN>.json`）
- 触发：用户「workflow_check 没过，帮我把失败项按原因码修掉，修完复跑」
- 本轮的结论一句话：**②③ 两段不是"能修的缺陷"，是"判据过期"；本轮按该原因码做登记留痕，复跑仍 FAIL，且我不改判据、不改数据。**

---

## 1. 修前 / 修后对照（同一条闸门）

| 时点 | RUN | 退出码 | 裁决 | 未过的小段 | 证据 |
|---|---|---|---|---|---|
| 修前（他人跑，触发本次） | `PIPE-20261003-2354-L7` | **1** | FAIL | ②、③ | `kb/l8/workflow_check_PIPE-20261003-2354-L7.json`（at 2026-10-04 00:19:59） |
| 修前（我独立复现） | `REPAIR-REPRO-20261004-0020` | **1** | FAIL | ②、③ | 读数与上一条逐字相同 |
| **修后（本轮交付）** | `REPAIR-AFTER-20261004-0035` | **1** | **FAIL（仍红，预期）** | ②、③ | 读数与修前逐字相同 |

三次跑的 ② 段原始读数：

```
l0/l1/l2 : match_L5_baseline = true / true / true      （漂移只在 L3）
l3_lines = 1018
l3_base1018_matches_L6 = false
l3_whole1527_matches_L4 = false
```

③ 段原始读数：`checked = 45`，`mismatch = 20`（清单见修后 JSON 的 `legs[2].detail.mismatch`）。

**为什么"修后仍红"是对的**：本轮只做**分类登记**，没有改判据、没有改数据 ⇒ 闸门判定**必须**一字不变。
反过来，如果登记完它变绿了，那才是出了事（说明我偷改了判据或数据）。

---

## 2. 失败项按原因码定性

| 对象 | 原因码 | 定性 | 依据 |
|---|---|---|---|
| `② 权威库 l0~l6 未被改动` | 冻结基线 vs 活库（判据过期） | **合法变红，非数据缺陷** | ① 判据实现是「拿**前缀**哈希比**整文件**哈希」：`workflow_check.py:112-125` 取活库前 1018 / 前 1527 行，去比 `l6_integrity.json`（2026-10-02 00:10:57，自报 lines=**2036**）与 `l4/runs/20260923-1445.json`（**1527 行**时代）的**整文件** sha ⇒ 只要文件行数不是那个数、或内容动过一字节，就恒为 false；把 L3 回滚到 09-23 才可能成立（禁止）。② 活库 L3 的每一次演进都有出处，见 §3。 |
| `③ 前序产物哈希（45 项）` | 拿 2026-09-23 的历史 run 记录当"当前基线"（判据过期） | **合法变红，但红里含 1 条真发现**（见 §3.3） | 4 份 09-23 run 记录是当时的事实；09-24 收敛、09-30 发号补齐、10-01 批次5 真写、10-02 L3 重蒸、10-03 防线1 落地之后，产物 hash **必然**变。判据的正確形式应是「与**最新**一次 run 记录申报一致」。 |

`kb-check` §3 的三种红里，这两段属第 2 种（**合法变红**）；**不是**第 1 种（真坏），也不是第 3 种（工具 bug）。

---

## 3. 来源审计（2026-10-04 独立复算，不采信脚本自述）

方法：扫 `kb/l*/runs/*.json` 共 **1360** 份 run 记录，对 20 项 mismatch 逐项查「**活库现 sha** 是否被更新的 run 记录记过」。

### 3.1 逐层闸门是绿的（说明数据面没坏）

同一轮的收口与逐层结果：`l0_gate` … `l7_gate` **全 exit 0**（见 `整链同步-PIPE-20261003-2354-L0-L7-链路结论.md` §②）；
L3 现行 1018 条自己有闸门证据：`kb/l3/runs/PIPE-20261003-2354-L3-dryrun.json` 报 `rules=1018`、
5 项 checks 全"通过"、`citations.bad=0`、`accounting.unaccounted=0`，且 `l3_gate.py` exit 0。

### 3.2 L3 的行数变迁（每一步都能对上出版物）

| 时点 | 行数 | 出处 |
|---|---|---|
| 2026-09-23 | 1527 | `kb/l3/history/rules-pre-converge-20260924-1230.jsonl` 实测 1527 行 |
| 2026-09-24 | 509 | 收敛步（`l3-known-drift.yaml` 的 `l3_append_only` 条记过） |
| 2026-10-02 00:07 | 2036 | `kb/.work/l6_integrity.json` 自报 `lines=2036` / sha `7d00454e…` |
| 现行 | **1018** | 活库 sha `743dc62398311b02…`，**同值写在** `kb/l3/registry/l3.json` 的 `appended_fields.old_lines_untouched.sha256`；mtime 2026-10-02 22:45:07 |

⇒ ②③ 的漂移是「L3 之后各层被合法重建」的下游效果，**不是权威库被偷改**。

### 3.3 20 项 mismatch 的来源

- **17 项有来源**：活库现 sha 出现在 09-23 之后的 run 记录里。例：`kb/l6/bm25/docs.jsonl`、`kb/l6/vectors/matrix.npy`、
  `kb/l6/retriever.py`、`kb/l6/selftest.json`、`kb/l6/index/l6.jsonl` 由 `PIPE-20261003-2354-L6`（10-04 00:18）记过；
  `kb/l4/registry/l4.json` 由 `REVIEW-20261003-LISTING-L4`（10-03 23:47）记过；
  `kb/l5/registry/l5.json` / `benchmark.json` 由 `RV-20261003-1057-L5`（10-03 11:01）记过。
- **3 项哈希级无落章**（改动本身有文档出处）：
  - `kb/l7/skills/kb-content-review/scripts/review.py` —— 2026-10-03「防线1 入口唯一化」（登记在 `report-output-contract.yaml` 的 `applied_20261003`）；
  - `kb/l7/skills/kb-content-review/SKILL.md` —— 同批「层前置」正文改动（`report-output-contract.yaml:381-383` 引到该文件）；
  - `kb/l7/registry/l7.json` —— **见下，这条是真发现**。
- **真发现（③ 不是全假红）**：`kb/l7/registry/l7.json` mtime = **2026-10-02 12:02:35**，但它自己声明的 `run_id` 仍是
  **20260923-1500**，**没有任何 run 记录**记过它现行 sha `b36c86f74d86a0a7…`，`article_no_source.read_at` 停在 09-30 17:45:27。
  ⇒ 一次**原地改写未落章**（这正是 ③ 本来该抓的事）。影响：该块计数落后现库 —— 自报 `total_rules=632` 而 L3 现为 1018；
  链路轮独立复算的真差异是 `total_outputs_note`（canonical 1242 → 1365）与 `candidate_rows`（1997 → 2730）。
  **要人做**：开闸后跑 `kb/.work/l7_article_source_refresh.py <RUN> --apply` 并补一条 L7 run 记录。

---

## 4. 本轮做了什么（3 个文件 · 变更协议 5 问 · 回滚）

| # | 文件 | 动作 | 五问 |
|---|---|---|---|
| 1 | `kb/l7/registry/workflow-check-known-drift.yaml` | **新建**：②③ 的逐项登记（原始读数 / 为什么是判据过期 / 来源审计 / 要人做什么 / forbidden / 复开条件 / 复算命令） | 读者=跑体检档与看报告的人；写者=kb-repair；判据=**不改变任何闸门判定**（今天没有脚本读它）；通道=write 工具写 `.yaml`（写后两读者核对差值 0）；回滚=`rm` 该文件 |
| 2 | `kb/l7/registry/layers.yaml` | 改 L7 段 `notes` 末条：把"② 段合法变红"扩成"②③ 段"，并**指到登记文件** + 写死三条禁令（不许改历史 run 记录 sha、不许回滚 L3、登记不会让它转绿） | 读者=层契约的读者；判据=只改说明文字，`layers_check.py` 六类仍全 0；通道=edit（.yaml 无信封，实测差值 0）；回滚=见下 |
| 3 | `kb/l7/registry/failure-playbook.yaml` | 新增处置条目 `gate_red.workflow_check`（symptom / owner / do / command / forbidden / reopen_when），把"看到 ②③ 红该怎么办"写进playbook | 同上；`layers_check`/`skills_check` 复跑均 exit 0 |

**回滚基线**：`kb/l7/_backups/kb-repair-workflow-②③-20261004-002649/`
（内含改动前 `layers.yaml`、`workflow_check.py`、两份修前闸门 JSON）

```bash
B="kb/l7/_backups/kb-repair-workflow-②③-20261004-002649"
cp "$B/layers.yaml" kb/l7/registry/layers.yaml            # 回滚 layers.yaml
git-less 环境无版本控制 ⇒ 以下两条需手工删：
rm kb/l7/registry/workflow-check-known-drift.yaml          # 回滚新登记文件
# failure-playbook.yaml 的回滚：删掉 id: gate_red.workflow_check 那一整块（36 行）
```

**改动后复跑的旁证**（证明没把别的契约弄坏）：
`skills_check.py` exit 0（五类 1=0 2=0 3=0 4=0 5=0）、`layers_check.py` exit 0（六类全 0）、
`tools/envelope_gate.py` exit 0（扫 1835 / 信封 0 / 读不到 0）。

---

## 5. 复跑结论

```
sh kb/kbpy l8/workflow_check.py REPAIR-AFTER-20261004-0035   →  exit 1
  FAIL ② 权威库 l0~l6 未被改动
  FAIL ③ 前序产物哈希（45 项）
  其余 7 段全 PASS；装载位 509 条 / 信封 0 / 健康分 79.1
```

**这是诚实的预期结果**：本轮按原因码做的是「登记」，不是「改判据」，所以判定必须不变。

---

## 6. 失败项清单（对象 + 原因码 + 要人做什么 + 复开条件）

| 对象 | 原因码 | 要人做什么 | 复开条件 |
|---|---|---|---|
| ② 权威库 l0~l6 未被改动 | 判据过期（冻结基线） | **改判据要单独走一轮**（见 §7-A）；或接受"基线漂移，非缺陷"的结论 | 改判据后复跑 exit 0 |
| ③ 前序产物哈希（45 项） | 判据过期（历史 run 记录当基线）+ 1 条真发现 | 同上；并把 ③ 改成"与最新 run 记录比 + 来源审计"，让"未落章改写"继续判红 | 同上 |
| `kb/l7/registry/l7.json` 原地改写未落章 | **真发现**（流程缺落章，非数据坏） | 开闸后跑 `l7_article_source_refresh.py <RUN> --apply` + 补 L7 run 记录（kb-repair 无权开 `--apply`） | `l7.json` 计数与现库一致，且有一条 L7 run 记录记它现行 sha |

---

## 7. 为什么没有"把红修绿"——三条路逐一否决

- **A. 改判据（推荐，但属"单独走一轮"）**：让 ②③ 变成「来源可溯才降级、查不到出处仍判红」。
  这是**改闸门语义**，按本库既定纪律（`l4-known-drift.yaml` 文件头："**改判据要单独走一轮**"）须由 owner 拍板，本轮不做。
- **B. 数据侧"修到与基线一致"**：唯一做法是把 L3 回滚到 1527 行时代的状态 —— 那会**毁掉 2026-10-02 那轮蒸馏**，
  且与 `l3_gate` 现行全绿的结论冲突。**禁止**。
- **C. 刷新冻结基线**：对 ③ 不可行 —— 它读的是 4 份 09-23 run 记录，改其中的 artifact sha 就是**伪造台账**；**禁止**。
  对 ② 的 `l3_whole1527` 也结构性不可达（活库 1018 行，判据取"前 1527 行"= 整文件）。
- **边界声明**：本轮**没有**碰 `kb/l0…l6` 的任何数据或台账，**没有**改任何判据，**没有**跑 `--apply`，
  **没有**动 `kb/l8/workflow_check.py`（它只被备份、未被修改）。

---

## 8. 复算命令（只读，任何人可重跑）

```bash
cd "/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理"
sh kb/kbpy l8/workflow_check.py <RUN>                      ; echo $?   # 现状：1（②③）
python3 -c "import hashlib;print(hashlib.sha256(open('kb/l3/candidates/rules.jsonl','rb').read()).hexdigest())"
python3 -c "import json;d=json.load(open('kb/l3/registry/l3.json'));print(d['appended_fields']['old_lines_untouched']['sha256'])"
sh kb/kbpy l7/scripts/skills_check.py ; sh kb/kbpy l7/scripts/layers_check.py
```
