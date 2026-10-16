# workflow_check 失败项 · 按原因码处置记录（2026-10-04 · kb-repair 第 3 轮）

- **库根**：`/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理`（cwd = 库根）
- **闸门**：`kb/l8/workflow_check.py`（9 段；**无干跑档**，跑一次写一份 `kb/l8/workflow_check_<RUN>.json`）
- **触发**：用户「workflow_check 没过，帮我把失败项按原因码修掉，修完复跑」
- **用户指令 vs 本库登记的冲突（先摆出来）**：用户要「修掉」，但本库 **`kb/l7/registry/failure-playbook.yaml` → `gate_red.workflow_check`** 明写
  **forbidden：「不许把 ②③ 的判据就地改宽而不同时报批（改判据要单独走一轮）」**。
  我**没有**就地改判据，按该条 `reopen_when` 的**第二条路**执行：
  「本轮只做登记 ⇒ 结论写「**基线漂移，非缺陷**」并附本文件与原始读数」。
  ⇒ **要 ②③ 真变绿，只能单独走一轮「改判据」，需要你点头**（见 §6）。

---

## 1. 修前 / 修后对照（同一条闸门，贴在命令与退出码）

| 时点 | RUN | 命令 | 退出码 | 裁决 | 未过 | 证据 |
|---|---|---|---|---|---|---|
| 修前（他人跑，触发本次） | `PIPE-20261003-2354-L7` | `sh kb/kbpy l8/workflow_check.py PIPE-20261003-2354-L7` | **1** | FAIL | ②③ | `kb/l8/workflow_check_PIPE-20261003-2354-L7.json`（at 2026-10-04 00:19:59） |
| 修前（我独立复现 #1） | `REPAIR-20261004-0146` | 同上（换 RUN） | **1** | FAIL | ②③ | `kb/l8/workflow_check_REPAIR-20261004-0146.json`（at 01:46:10） |
| **修后（本轮交付）** | `REPAIR-AFTER-20261004-0153` | 同上（换 RUN） | **1** | **FAIL（仍红，预期）** | ②③ | `kb/l8/workflow_check_REPAIR-AFTER-20261004-0153.json`（at 01:47:47） |

**②③ 两段的原始读数，修前与修后 `json.dumps` 逐字节相同**（脚本比对结果：`identical readings: True`）：

```
② l0/l1/l2  match_L5_baseline = true / true / true    （tree bd36cbb89dedb48f / 099ad8afdc1a0be2 / 183f6265c0666688；4007 / 3152 / 887 文件）
   l3_lines = 1018
   l3_base1018_matches_L6   = false
   l3_whole1527_matches_L4  = false
③ checked = 45 ; mismatch = 20（清单见下方 §2；与首两次逐项一致）
其余 7 段（①④⑤⑥⑦⑧⑨）全 PASS
```

**为什么"修后仍红"是对的**：本轮只做**登记留痕**（改的是**没有任何闸门读**的登记文件），
**没改判据、没改数据** ⇒ 判据读数**必须**一字不变。反过来，如果登记完它变绿了，那才是出事
（说明我偷改了判据或数据）。这正是 `failure-playbook.yaml:154-158` 给这条红的处置口径。

---

## 2. 失败项按原因码定性（一个失败项一行）

原因码取自本库**登记在案的**路由键：`kb/l7/registry/failure-playbook.yaml → gate_red.workflow_check`。
三种「红」的口径取自 `kb-check §3`（真坏 / 合法变红 / 已知判据缺陷）与 `kb-check §2` 的判据缺陷表。

| # | 失败项（对象） | 原因码 | 定性 | 依据（可复算） | 本轮能否修 |
|---|---|---|---|---|---|
| 1 | `② l3_base1018_matches_L6` | `gate_red.workflow_check` / 判据过期 | **合法变红** | `workflow_check.py:112-125` 拿**前缀**哈希（活库前 1018 行）比**整文件**哈希：基线取自 `kb/.work/l6_integrity.json`（checked_at 2026-10-02 00:10:57，自报 **lines=2036**、sha `7d00454e…`），活库现 **1018 行 / `743dc62398311b02…`** ⇒ 「前 1018 行」= 整个文件，**结构上不可能相等** | ❌ 不改判据不能修 |
| 2 | `② l3_whole1527_matches_L4` | 同上 | **合法变红** | 基线取自 `kb/l4/runs/20260923-1445.json`（**1527 行时代**的整文件 sha）；活库 1018 行 ⇒ 「前 1527 行」= 整个文件，恒 false。把它变真只有一条路：**把 L3 回滚到 09-23** —— **明令禁止**（毁掉 2026-10-02 那轮蒸馏） | ❌ 同上 |
| 3 | `③` 45 项里的 **17 项** mismatch | `gate_red.workflow_check` / 判据过期 | **合法变红** | 判据把 **2026-09-23 四份 run 记录**当"当前基线"（`workflow_check.py:128-137`）。09-23 之后 L3→L7 每层都合法重建过 ⇒ 产物哈希**必然**变。**独立复算**：这 17 项的"活库现 sha"都能在**更新的** run 记录里查到出处 | ❌ 同上 |
| 4 | `③` 里 `kb/l7/registry/l7.json` | `gate_red.workflow_check` / **真发现** | **真坏（流程缺落章，非数据坏）** | mtime 2026-10-02 12:02:35，自报 `run_id` 仍是 `20260923-1500`，**没有任何 run 记录**记过现 sha `b36c86f74d86a0a7…`；`article_no_source.read_at` 停在 09-30 17:45:27；自报 `total_rules=632` 而 L3 现为 1018 ⇒ **原地改写未落章** | ⚠️ **本轮不做**：需开闸 + 与在跑的会话互斥（见 §5、§6） |
| 5 | `③` 里 `kb/l7/skills/kb-content-review/SKILL.md`、`.../scripts/review.py` | `gate_red.workflow_check` / 哈希级无落章 | **半真**：改动有文档出处、无哈希落章 | 2026-10-03「防线1 入口唯一化 + 层前置」改动，登记在 `kb/l7/registry/report-output-contract.yaml → applied_20261003`，但**没有** run 记录记这两个文件的现 sha | ⚠️ 同 #4（补落章属写档 + 需定义"补历史落章"的口径） |

**其余 7 段是实质判据，本轮实测全 PASS**（①环境与版本纪律 ②权威库 ③前序产物 之外的 ④⑤⑥⑦⑧⑨），
含 `④ 沙箱产出 510 md / 信封 0`、`⑤ 装载位 509 条 / 信封 0 / 健康分 79.1`、`⑦ 入口闸门生效（无 KB_ENTRY 拒跑 rc=2，真入口 rc=0）`、
`⑨ ingest 闸门正常拒收（E026 内容质量分 52.1 < 60）、落盘 0 个`。

---

## 3. 独立复算（不采信脚本自述，也不采信上一轮记录）

方法：把 20 项 mismatch 逐项拿去**扫全库 run 记录**（`kb/l*/runs/**/*.json`，本轮实测 **1469** 份可解析、0 份坏），
查「活库**现** sha 是否被**比 09-23 更新**的 run 记录记过」：

| 分类 | 数量 | 说明 |
|---|---|---|
| 有更新来源（⇒ 判据过期） | **17** | 例：`kb/l6/bm25/docs.jsonl`、`kb/l6/vectors/matrix.npy`、`kb/l6/retriever.py`、`kb/l6/selftest.json`、`kb/l5/registry/l5.json`、`kb/l3/candidates/rules.jsonl` 等 |
| **查不到任何落章** | **3** | `kb/l7/registry/l7.json`、`kb/l7/skills/kb-content-review/SKILL.md`、`kb/l7/skills/kb-content-review/scripts/review.py` |

结论与上一轮（2026-10-04 00:35）**逐项一致** ⇒ 这是**稳定的判据常量**，不是偶发抖动：

> 其中 `kb/l4/registry/l4.json` / `kb/l6/registry/l6.json` 的"更新来源"来自**本轮并发会话**的 dryrun 记录
> （`REVIEW-20261004-0140-静音续航-LISTING-{L4,L6}-dryrun.json`）—— **活库在被别的会话推着长**，
> 这正是第 ③ 段判据恒红的机制。

---

## 4. 本轮实际改了什么（变更记录 + 五问 + 回滚）

| # | 文件 | 动作 | 为什么 |
|---|---|---|---|
| 1 | `kb/l8/workflow_check_REPAIR-20261004-0146.json` | 新增（**闸门自己写的**） | 修前复现读数 |
| 2 | `kb/l8/workflow_check_REPAIR-AFTER-20261004-0153.json` | 新增（**闸门自己写的**） | 修后复跑读数（`kb-check §1` 已声明该脚本无干跑档、跑即写盘） |
| 3 | `kb/l7/registry/workflow-check-known-drift.yaml` | **更新**：`raw_readings.repro_runs` 追加第 3 次复现；`meta.last_reverified`；`stale_criteria[1].evidence` 补第 3 轮复算（1469 份记录 / 17+3） | 按 §2 表 #1-#3 的原因码，这条红的正确处置就是**登记**；把「判据过期 + 可复现」的证据钉住 |

**变更协议 5 问**（kb-repair 铁律①）：

| 问 | 答 |
|---|---|
| 读者 | 跑 `kb-check` 体检档的人 / 看 workflow_check 报告的人 / 准备把 ②③ 修绿的人 / 写日报的人 |
| 写者 | 本轮 kb-repair 会话；后续由维护 `kb/l7/registry` 的人（owner：刘华丽）按 `owner_action` 更新 |
| 判据 | **本文件不被任何脚本读**（`meta.read_by_gate: none`）⇒ **不改变任何闸门判定**；它只把 ②③ 定性为判据过期并留证 |
| 通道 | `write` 工具写 `.yaml`（`.yaml`/`.json` 不走 4096 字节信封）；写后按**两读者**核对：python `getsize` **17198** == 宿主 Electron `statSync` **17198** ✓ 非信封态 |
| 回滚 | `cp kb/l7/_backups/kb-repair-workflow-check-20261004-0152/workflow-check-known-drift.yaml kb/l7/registry/`（回滚基线已取，见下） |

**回滚基线**：`kb/l7/_backups/kb-repair-workflow-check-20261004-0152/`
（`workflow-check-known-drift.yaml` sha256 `853f48f721a71163…`、`failure-playbook.yaml` sha256 `d8d528d780387ff2…`，各 15248 B / 24224 B，均为改动前副本）

**改完按 kb-repair §5 复核**：`sh kb/kbpy l7/scripts/skills_check.py` → **五类 `1=0 2=0 3=0 4=0 5=0`，退出码 0**（动 `kb/l7/registry/*.yaml` 后必须复核这一条）。

---

## 5. 本轮**没做**的动作（逐条对应禁令，避免被读成"已修好"）

| 没做 | 依据 |
|---|---|
| **没有**就地改宽 `②③` 判据（`workflow_check.py:112-137` 一字未动） | `failure-playbook.yaml:157`「不许把 ②③ 的判据就地改宽而**不同时报批**」 |
| **没有**改写 `kb/l{4,5,6,7}/runs/20260923-*.json` 里的 artifact sha | `:155`「那是**伪造台账**」 |
| **没有**把 L3 回滚到 1527 行时代 | `:156`「那是**毁掉** 2026-10-02 的蒸馏成果」 |
| **没有**跑 `.work/l7_article_source_refresh.py --apply` | `:151-152` 明写「**开闸后**跑」；且本轮**库内另有会话在跑循环**（见 §7），单槽认领不许抢 |
| **没有**动 `kb/l0…l6` 的任何数据或台账 | 本库纪律：修法涉及 l0–l6 ⇒ **先停、报批** |
| 临时 `.md` 落盘走 `write` 工具（非 python 直写），写后两读者核对 | 本库纪律：python 写 `.py/.txt/.md` 会落 4096 字节信封 |

---

## 6. 要人做什么 + 复开条件（②③ 想真变绿，二选一，都要**单独走一轮**）

| 选项 | 谁做 | 做什么 | 代价 / 风险 |
|---|---|---|---|
| **A. 改判据（推荐，本库两处登记都指向它）** | 维护 `kb/l7/registry` 的人**报批**后授权 | ④ 把 `②` 改成「与**当前**基线比 + **来源可溯才降级**」（活库 sha 能在更新的 run 记录/注册表里找到出处 ⇒ 记「已溯源的演进」，照打读数不定红；**找不到出处的仍判红**）；⑤ 把 `③` 从「4 份固定历史记录」改成「**最新** run 记录申报 + 来源审计」 | 要**反向测试**：改完必须证明它**仍能抓到真漂移**（用 §2 表 #4 那类"未落章改写"当靶子），否则是把闸门改瞎。改判据文件 = `kb/l8/workflow_check.py`（**不是**登记文件） |
| **A′. 等价但更弱** | 同上 | 给 `workflow_check.py` 加 `--accept-frozen-baseline <RUN>`，把基线**显式前移**（保留原判据不动） | 闸门默认仍红，只有带参才绿 ⇒ 日报/体检档读到的还是 FAIL |
| **B. 本轮只做登记（**已按此执行**）** | 已做 | 结论写「基线漂移，非缺陷」+ 附登记文件与原始读数 | 闸门**仍 FAIL**（这是预期，不是没修） |
| **C. 修真发现（与 A 独立，可并行排期）** | 开闸后由人跑 | `kb/.work/l7_article_source_refresh.py <RUN> --apply`（刷新 `kb/l7/registry/l7.json` 计数与叙述）+ **补一条 L7 run 记录**；另议「补 10-03 防线1 两个文件的哈希落章」的口径 | 写 `kb/l7` 登记面；须**独占**（本轮另有会话在跑循环）。做完 ③ 里那条真发现才会消失，但 ②③ 其余 19 项**仍红** |

**复开条件（照 `failure-playbook.yaml:158` / `workflow-check-known-drift.yaml` 的 `reopen_when`）**：
「改判据后复跑 `exit 0`；或本段被新判据取代后从登记文件里删除」。

---

## 7. 并发与适用边界（如实披露）

- 本轮跑闸门时，**库内有另一个会话在用循环**：`kb/.work/.kb-loop-claim.json` = `REVIEW-20261004-0140-静音续航-LISTING`（pid 已退出、认领于 01:41:42，TTL 45 分钟，跑时未过期）。
  **我不抢认领、不跑任何层引擎、不写 `kb/l7/runs/index.jsonl`**；只写了 §4 那两个 `kb/l8` 报告 + 一个**不被任何脚本读**的登记 yaml。
- 并发旁证（说明"活库在动"不是我的动作）：⑤ 装载位维度 `利用率 0.2317 → 0.2322`、⑥ 工作区 `md 4996 → 5032`；
  但 **②③ 的失败集合逐字未变** ⇒ 本轮的 FAIL 不是并发抖动。
- **本记录**是 `workflow_check` **这一条闸门**的处置，**不等于知识库体检全过**：同一时段的体检表（`体检表-20261004-0131-全库六闸门.md`）
  另记 **⑥ 投影一致性 真坏 3/6**、**⑦ 层闸门 L0 红**、**③ 路由表对账 未判定（缺今日赢家表）**。要"全绿"得逐条排期。
