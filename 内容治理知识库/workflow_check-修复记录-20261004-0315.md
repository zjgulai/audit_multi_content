# workflow_check 失败项 · 按原因码处置记录（2026-10-04 第 4 轮 · kb-repair）

- **库根**：`/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理`（cwd = 库根）
- **闸门**：`kb/l8/workflow_check.py`（9 段；无干跑档，跑一次写一份 `kb/l8/workflow_check_<RUN>.json`）
- **触发**：用户「workflow_check 没过，帮我把失败项按原因码修掉，修完复跑」
- **前 3 轮记录**：`workflow_check-修复记录-20261004-0035.md` / `…-0153.md` / `…-0232.md`

## 0. 一句话结论（先给不好听的那句）

**本轮真修的段数 = 0。** 复跑后 `workflow_check` 仍是 **FAIL**，未过项仍是 **②③** 两段。

这不是「没干活」，而是**按原因码该这么办**：②③ 在本库 `kb/l7/registry/failure-playbook.yaml → gate_red.workflow_check`
里被**明确登记为「冻结基线 vs 活库」这一类（判据过期，不是数据坏了）**，且该条 `forbidden` 写着
「**不许把 ②③ 的判据就地改宽而不同时报批（改判据要单独走一轮）**」。
kb-repair 的原因码对照表对 `workflow_check` 第 ② 段红给的修法原文就是：
「**合法变红**，写"基线漂移"结论，**不要"修"**」。

⇒ **按原因码，「修」这个动作在 ②③ 上被本库自己的登记禁止。** 要把它们真变绿，只能改判据，
而那需要你点头（见 §5）。**我没有替你点这个头。**

---

## 1. 修前 / 修后对照（同一条闸门 · 附命令与退出码）

| 时点 | RUN | 命令 | 退出码 | 未过 |
|---|---|---|---|---|
| 修前（本轮复现） | `CHK-20261004-REPAIR-BEFORE` | `sh kb/kbpy l8/workflow_check.py CHK-20261004-REPAIR-BEFORE` | **1** | ②③ |
| 修后（本轮交付） | `REPAIR-AFTER-20261004-0315` | `sh kb/kbpy l8/workflow_check.py REPAIR-AFTER-20261004-0315` | **1** | ②③ |
| 修后确认（本记录落盘后再跑） | `REPAIR-FINAL-20261004-0315` | 同上（换 RUN） | **1** | ②③ |

```
修前：FAIL ② · FAIL ③ · 其余 7 段全 PASS
修后：FAIL ② · FAIL ③ · 其余 7 段全 PASS      ← 判定集合未变（这是"没偷改"的证据）
```

**②③ 的读数「修前 = 修后」逐字节相同**（`json.dumps(sort_keys=True)` 比对 `legs[②].detail` 与 `legs[③].detail`
→ 两段均 `True`）。本轮只写了一个**没有任何闸门读**的登记文件，所以判定**理应**一字不变 —— 实测正是如此。

**⑥ 上一轮修的那一段：本轮未复发**（`其他` 桶 = 0；不可读 510 个全在判据本就容忍的 `他人产物 hostlib` 桶）。
`REPAIR-FINAL` 这一跑是为了证明**本记录自身（一个新增 `.md`）没有把 ⑥ 重新弄红**：
实测 `不可读 510 {'他人产物 hostlib': 510}`，`其他` 仍为 0 ⇒ **⑥ 稳定 PASS**。
（本记录用 `write` 工具落盘，实测 python `getsize` = 宿主 `statSync` = 13066、`NUL=0` ⇒ 明文，非信封态。）

---

## 2. 失败项的定性（原因码 = 判据写死在了一个已经过去的时点）

### ② 权威库 l0~l6 未被改动

| 子项 | 读数 | 定性 |
|---|---|---|
| l0 / l1 / l2 三棵树 vs L5 基线 | `match_L5_baseline` **全 true** | 相符，漂移不在 l0~l2 |
| `l3_base1018_matches_L6` | false | **判据过期** |
| `l3_whole1527_matches_L4` | false | **判据过期** |

**为什么是判据过期（可复算）**：`workflow_check.py:112-125` 拿**前缀哈希**去比**整文件哈希** ——
L4 那条基线取自 `kb/l4/runs/20260923-1445.json`（**1527 行时代**），活库 L3 现 **1018 行**
⇒「前 1527 行」**就是整个文件**，**结构上不可能相等**。要它变真只有「把 L3 回滚到 09-23」——
那会毁掉 2026-10-02 那轮蒸馏，`forbidden` 明令禁止。

### ③ 前序产物哈希（45 项里 20 项 mismatch）

**为什么是判据过期**：`workflow_check.py:128-137` 把 **2026-09-23** 四份历史 run 记录里的产物 sha
当成「今天仍不许变」的基线。09-23 之后每一层都被合法重建过（09-24 收敛、09-30 发号补齐、
10-01 批次5 真写、10-02 L3 重蒸、10-03 防线1 落地）⇒ 哈希**必然**变。

---

## 3. ★ 本轮新增的实质证据：20 项逐项来源审计（这是本轮真正干出来的东西）

前三轮只把 ③ 分成「17 项有来源 / 3 项无落章」。本轮**逐项查到具体出处**，并**首次把 3 项的真身查实**。

方法（只读、不采信脚本自述）：扫 `kb/l{3,4,5,6,7}/runs/*.json` 的全部 `artifacts[]`，
对 20 项 mismatch 逐项问「活库**现 sha** 是否被某条 run 记录记过」。

### 3.1 结论一：17/20 有 run 记录来源，且每项都不止一条

| 产物 | 记过现 sha 的 run 记录数 | 最新一条 |
|---|---|---|
| `kb/l3/candidates/rules.jsonl` | 35 | `RVW-LISTING-20261004-L4` |
| `kb/l5/registry/l5.json` | 43 | `RVW-LISTING-20261004-L5` |
| `kb/l6/bm25/docs.jsonl` | 41 | `RVW-LISTING-20261004-L6` |
| …（其余 14 项同形） | — | — |

最近的那条**几乎全停在 `RVW-LISTING-20261004-L{4,5,6}`** —— 那是**本轮并发会话**的跑批。
**这正是「判据恒红」的机制本身：活库每被合法推进一步，这条判据就多红一项。**
（拿"一个字节都不许动"当判据，等于把"库在用"判成"库坏了"。）

### 3.2 结论二：3/20 在 run 记录里查不到 —— 但**没有一项是无人认领的黑改**

| 产物 | 改动出处（本轮查实） |
|---|---|
| `kb/l7/skills/kb-content-review/scripts/review.py` | 2026-10-03「防线1 入口唯一化」同批，登记在 `kb/l7/registry/report-output-contract.yaml` 的 `applied_20261003` |
| `kb/l7/skills/kb-content-review/SKILL.md` | 同批「层前置」正文改动，`report-output-contract.yaml:381-383` 引到该文件 §层前置 |
| `kb/l7/registry/l7.json` | 见 §3.3 —— **本轮新查明** |

### 3.3 ★ 新查明：`l7.json` 的「未落章改写」真身 = 改了 **1 个字段**

前几轮把它记为「红里唯一有实质内容的真发现」，但**从没有人看过它到底改了什么**。本轮看了：

```
diff  kb/l7/_backups/batch18b-20261002-1201/l7.json.pre-edit  ←→  kb/l7/registry/l7.json
31c31
< "field_lives_in": "…canonical/*.jsonl（定稿，四个形态文件）+ …"
> "field_lives_in": "…canonical/*.jsonl（定稿，五个形态文件）+ …"
```

**差异只有一个字段、一处措辞：四个形态文件 → 五个形态文件。**
（pre-edit sha `766ac16b2e3ed104…`；现 sha `b36c86f74d86a0a7…`）

再看它的**出处**（也不是零）：

- `kb/l7/_backups/batch18b-20261002-1201/_NOTE.txt` 写着
  `2026-10-02 12:02:35  批次18 第1块 余下活声明点` —— 与文件 mtime **12:02:35 同一秒**；
- 现 sha `b36c86…` 被**后续两次备份清单**各记过两遍（pre-state 与 after-state）：
  `kb/l7/_backups/conclusion-destination-20261002-225030/kb_l7_registry.{pre,after}-state.sha256`、
  `kb/l7/_backups/report-output-contract-20261002-230616/kb_l7_registry.{pre,after}-state.sha256`；
- **缺的只有 run 记录**（`kb/l7/runs/*.json` 的 `artifacts[]` 里查不到现 sha）。

⇒ **定性收窄**：这是**合法改动 + 流程缺落章**，**不是**"没人认领的黑改"、更不是内容损坏。
前几轮把它当成"红里唯一有实质内容的"是对的（它确实是唯一带流程缺陷的一项），
但**严重度**应从中降到**低**（流程问题，非数据问题）。

**汇总一句话**：**③ 的 20 项里，没有一项能证明"有人偷改了权威库"** —— 而那正是 ③ 自称要证的事。

---

## 4. 本轮改了什么（变更记录 + 五问 + 回滚）

| # | 文件 | 动作 | 五问（kb-repair 铁律①） |
|---|---|---|---|
| 1 | `kb/l7/registry/workflow-check-known-drift.yaml` | **追加**第 4 次复现读数 + 逐项来源审计 + `l7.json` 的 `measured_diff`/`provenance` + `pending_decision` 段 | **读者**=跑体检/看报告/写日报/准备把 ②③ 修绿的人；**写者**=本轮 kb-repair；**判据**=**不改变任何闸门判定**（今天没有任何脚本读本文件，实测复跑读数逐字节未变）；**通道**=`edit` 工具写 `.yaml`（写后核验 python `getsize` = 宿主 `statSync` = **24438**，非信封态）；**回滚**=`cp kb/l7/_backups/kb-repair-workflow-drift-20261004-031137/workflow-check-known-drift.yaml.before kb/l7/registry/workflow-check-known-drift.yaml` |
| 2 | `kb/l7/_backups/kb-repair-workflow-drift-20261004-031137/` | **新建**（回滚基线） | 含改前副本（sha `b56588c5b1e8a77c…`）+ 本轮修前 JSON + `PATH.txt` |
| 3 | `kb/l8/workflow_check_CHK-20261004-REPAIR-BEFORE.json`、`…_REPAIR-AFTER-20261004-0315.json` | 新增（**闸门自己写的**） | 该脚本无干跑档，跑即写盘（`kb-check §1` 已声明） |
| 4 | 本文件 | 新增 | 交付记录 |

**改完按 kb-repair §5 复核**（本节动过 `kb/l7/registry/`，故三条旁证闸门都跑了）：

| 闸门 | 结果 |
|---|---|
| `sh kb/kbpy l7/scripts/skills_check.py` | **exit 0**，五类 `1=0 2=0 3=0 4=0 5=0` |
| `sh kb/kbpy l7/scripts/layers_check.py` | **exit 0**，六类 `1=0 2=0 3=0 4=0 5=0 6=0` |
| `python3 tools/envelope_gate.py` | **exit 0**：`正常 1906 ｜ 信封态 0 ｜ 读不到 0` |

---

## 5. ★ 未决事项：②③ 要真变绿，只能改判据 —— **请你裁**

同一条红已连续 **4 轮**。kb-repair 的纪律是「**同一条闸门修了两次还红 ⇒ 停，报"判据可能有缺陷"，附证据**」——
本轮执行的正是这一条：**在拿到明确授权前，不许动判据。**

三条路（我已写进 `workflow-check-known-drift.yaml` 的 `pending_decision` 段）：

- **(A) 授权改判据**：把 ②③ 改成 owner_action 里那条「**最新 run 记录 + 来源审计**」——
  逐产物比"最新一次申报的 sha"，**查不到出处的改动仍判红**。
  ⚠️ **单改判据还不够**：按新判据，那 3 项无落章项**仍然是红**，必须**同时补落章**。
- **(B) 维持现状**：完全合规、零风险，但 ②③ **长期红**、体检恒 FAIL —— 长期红的闸门会被值班的人忽略（这是真代价）。
- **(C) 只补 3 项落章，判据下一轮再谈**：补完 ②③ **仍红**（判据未改）。

**（A）与（C）都卡在同一件事上**：补落章 = 写 `kb/l7/runs/` 与 `index.jsonl` = **开闸写档 + 必须独占循环**。
2026-10-04 03:0x 实测：**循环被另一会话占着**（`kb/.work/.kb-loop-claim.json`，base `RVW-LISTING-20261004`；
其 pid 已死但**认领未过期**，且**确有活会话在写** run 记录与 `l7/runs/index.jsonl`）。
按并发纪律**不抢**：要接手须 `kb_loop_claim.py claim --base <BASE> --take-over`，**由人拍**。

**所以本轮我什么都没抢、什么都没写档** —— 见 §6。

---

## 6. 本轮**没有**做什么（如实披露，避免把"没做"读成"做了"）

- ❌ **没有**改 `kb/l8/workflow_check.py` 的 ②③ 判据（`forbidden` 要求单独一轮 + 报批）
- ❌ **没有**改写任何历史 run 记录的 artifact sha（那是伪造台账）
- ❌ **没有**把 L3 回滚去迎合判据
- ❌ **没有**写任何 run 记录、**没有**补落章（属开闸写档）
- ❌ **没有**碰 `kb/l0~l6` 的任何数据与台账
- ❌ **没有**抢循环认领（另一会话在跑，实测它在写 `kb/l7/runs/index.jsonl`）
- ❌ **没有**动 `l7.json` 本身 —— 它现 sha 被两条备份清单记着，任何改写都会再次改变 sha

**并发披露**：本轮跑闸门时，库内**另有一个活会话**在跑（循环认领 base `RVW-LISTING-20261004`），
它正在写各层 `runs/`、`l7/runs/index.jsonl`、`kb/.work/l4_integrity.json` 等。
我的 RUN 名与它不同 ⇒ **没有抢任何文件**。旁证：它推高了 ③ 的"最新来源"（§3.1 的 `RVW-LISTING-…`），
但 **②③ 的失败集合逐字节未变** ⇒ 结论不受并发影响。

**边界**：本记录**只是 `workflow_check` 这一条闸门**，**不等于知识库体检全过**。
同期的其他闸门（投影一致性、逐层闸门、路由表对账）另记在 `体检表-*.md`，要"全绿"得逐条排期。

---

## 7. 复算命令（只读，任何人可重跑）

```bash
cd "/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理"

# ① 复跑闸门（应仍 FAIL②③）
sh kb/kbpy l8/workflow_check.py <RUN>                        ; echo $?

# ② 证明"修前=修后 逐字节相同"（判据未被我偷改）
python3 - <<'EOF'
import json
leg=lambda r,n: json.dumps(next(l for l in json.load(open(r))["legs"] if l["leg"].startswith(n))["detail"],sort_keys=True,ensure_ascii=False)
B="kb/l8/workflow_check_CHK-20261004-REPAIR-BEFORE.json"; A="kb/l8/workflow_check_REPAIR-AFTER-20261004-0315.json"
print("② same:",leg(B,"②")==leg(A,"②"), "｜③ same:",leg(B,"③")==leg(A,"③"))
EOF

# ③ l7.json 的"真身"：差异只有一个字段
diff <(python3 -c "import json;print(json.dumps(json.load(open('kb/l7/_backups/batch18b-20261002-1201/l7.json.pre-edit')),ensure_ascii=False,indent=1,sort_keys=True))") \
     <(python3 -c "import json;print(json.dumps(json.load(open('kb/l7/registry/l7.json')),ensure_ascii=False,indent=1,sort_keys=True))")

# ④ 旁证闸门
sh kb/kbpy l7/scripts/skills_check.py ; sh kb/kbpy l7/scripts/layers_check.py ; python3 tools/envelope_gate.py
```
