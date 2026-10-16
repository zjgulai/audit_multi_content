# 修订 · `com.kb.gates` plist 的严格 XML 缺陷 ＋ 排期口径更正

日期 2026-10-13 ｜ 执行 Owner 指示「先做 ① 和 ②，**不要影响现有的工作流和输出格式**」

---

## 0. 一句话

① plist 注释里的 `--`（严格 XML 非法）已在**模板 ＋ 安装件**上修掉，**语义逐键相等**；
② 「每 30 分钟」那句的**真实位置不在 AGENTS.md**，已改在它真正所在的交付件里。
**launchd 未被触碰** —— 理由见 §2.3。

---

## 1. ★ 先更正我自己的两处说过头（这是本单最重要的部分）

| # | 我当时说 | 实测 | 影响 |
|---|---|---|---|
| ① | 「**重启后加载失败 ⇒ 每日闸门巡检会静默停掉**」 | **`plutil -lint` = OK**（Apple 自家 `CFPropertyList` 解析器接受它）；launchd 已加载、`calendarinterval` 状态 active | ⇒ **「静默停掉」这个风险不成立**。它只是**严格 XML（Python expat）非法**，不是 launchd 非法。我把「严格性缺陷」说成了「功能性故障」 |
| ② | 「**AGENTS.md** 说 com.kb.gates 是每 30 分钟」 | `grep com.kb.gates ~/.dsh/AGENTS.md` = **0 命中**。AGENTS.md 里「每 30 分钟」指的是 `com.kb.review-readiness`，**那句话是对的** | ⇒ 要改的是 `交付-1012至1016-结项与未达标说明-20261012.md:136`，不是 AGENTS.md |

**为什么还是修**：严格 XML 合法性是真性质（Python 工具链、其它语言的解析器都会拒），
一行就能修，且**修它零风险**。但结论要按实测说 —— 它是**整洁性/可移植性**缺陷，
不是「马上就要坏」的定时炸弹。

---

## 2. ① plist：改了什么、怎么证的

### 2.1 改了哪两个文件（**只动注释**）

| 文件 | 改动 |
|---|---|
| `ci/launchd/com.kb.gates.plist`（**模板** —— 不修它，重装就把缺陷带回来） | 5 处：`--apply` ×2 ＋ `` `--scope full` `` / `` `--scope` `` / `` `--scope core` `` ×3 |
| `~/Library/LaunchAgents/com.kb.gates.plist`（**装着的**） | 1 行：`不传 --apply，不调 … kb_pipeline.py --apply` |

改法：把那几个 flag 写成 `` `apply` 档 `` / `` `scope=full` `` —— **含义一字不变**，只是不再出现连续两个连字符。

### 2.2 三条断言（脚本内，不符即抛）

```
① strip_comments(改后) == strip_comments(改前)   ⇒ 注释之外**逐字未动**
② plistlib.load(改后去掉注释) == plistlib.load(改前去掉注释)  ⇒ **语义逐键相等**
③ plistlib.load(改后原文) 成功                    ⇒ 现**严格合法**
```
外加：回读一致（写完再读，不等就抛）；`plutil -lint` = OK。
备份：`~/Library/LaunchAgents/com.kb.gates.plist.bak-20261013`。

**实测未变**：`ProgramArguments` 仍是 `ci/run_gates.py --outdir "…"`（不带 `--scope` ⇒ 默认 core）；
`StartCalendarInterval` 仍是 `{Hour: 14, Minute: 0}`。

### 2.3 ★ 为什么**没有** `bootout + bootstrap`

我原先的 ① 里写了要重载验一次。**现在不做，三个理由**：

1. **没必要**：`plutil` 早已判 OK、launchd 已加载且排期 active ⇒ 重载不改变任何行为；
   严格合法性已由 `plistlib` 解析成功证明，不需要用重载来证。
2. **有风险**：重载是**唯一**可能弄坏一个**正在正常工作**的定时任务的步骤（bootout 成功、
   bootstrap 失败 ⇒ 任务变成未装载，比现在更坏）。
3. **违反本次约束**：Owner 明令「**不要影响现有的工作流**」。

⇒ 磁盘上的文件已是合法版本，**下次重启/重装自然生效**；**launchd 未被触碰**（已核：仍 in list、schedule active）。

### 2.4 没修的那一份，及理由

`ci/out/com.kb.gates.generated.plist`（2026-10-04 的**生成产物**）**保持原样**：

- 它的注释**早已被一次旧的 sed 替换弄坏**（反引号丢失、`full` 被写成 `core`、末行截断）——
  也就是说它与模板**原本就不一致**；
- 它是 `install-launchd.sh` 的**输出快照**，改它等于**篡改当时的产出记录**；重装会被重新生成（届时已合法）。

---

## 3. ② 排期口径：改在真实位置

```diff
- | 周期接线（每 30 分钟那班 `com.kb.gates`） | …
+ | 周期接线（**每日 14:00** 那班 `com.kb.gates`）※**2026-10-13 更正**：原写「每 30 分钟」——
+   实测安装件 `StartCalendarInterval` = `{Hour: 14, Minute: 0}`（每日一次）；
+   每 30 分钟那班是 `com.kb.review-readiness`。**接线结论不变**：
+   `p0_regression` / `verdict_latency` / `perf_bench` 都在 `core`（15 把）里，
+   launchd 不带 `--scope` ⇒ 默认 core ⇒ 下次 14:00 会跑到 | …
```

**只改了第 136 行**（逐行比对：155 行里仅此 1 行变化）。
**AGENTS.md 未改动** —— 它那句话本来就是对的（见 §1②）。

---

## 4. 顺带查出、**本次未处置**的一处漂移（等你裁）

三份 plist 的**实际运行范围并不一致**：

| 副本 | `ProgramArguments` | 覆盖闸门 |
|---|---|---|
| `ci/launchd/…`（模板） | `--scope full` | **17 把**（core 15 ＋ projection ＋ envelope） |
| `~/Library/LaunchAgents/…`（**装着的**） | 无 `--scope` ⇒ 默认 | **15 把**（core） |
| `ci/out/…generated.plist`（旧产物） | `--scope core` | 当时候的 core |

⇒ **模板说 17 把、实际跑 15 把**（`projection` / `envelope` 两把不在日常范围内）。
这**不是本单造成的**，且**修它 = 改工作流**（会让每日红从 0 变 1–2 把）⇒ **按本次约束不动**。

**我的推荐**：**暂不动**，只登记。理由：`projection` 实测真坏（3/6）、`l0` 也红，
把它们纳入日常会把每日巡检从「全绿」变成「天天红 1–2 把」——那是**要不要把已知真红暴露出来**的
决策，不该夹在「修个注释」里顺手做。代价：`envelope` 这把闸门目前只在 CI（GitHub/GitLab/Jenkins）里跑。

---

## 5. 尺子（改动后现跑）

| 尺子 | 结果 |
|---|---|
| `plutil -lint`（两份 plist） | **OK / OK** ✅ |
| `plistlib` 严格解析（两份 plist） | **成功** ✅ |
| `kb/l8/envelope_census.py`（.md 明文落盘） | **0** ✅ |
| `kb/l8/check_agents_md_drift.py`（main / `--selftest`） | **0 / 0** ✅（与改前一致） |
| `kb/l8/workflow_smoke.py` | **0** ✅ |
| `kb/l7/review-engine/tests/` 全量 | **101 passed** ✅ |
| `kb/l5/p0_fastpath.py --selftest` | **0** ✅ |
| `l3_gate` / `check_source_readonly` | **0 / 0** ✅ |
| `launchctl list` / `print` | 仍 in list，`calendarinterval` active，**未触碰** ✅ |

---

## 6. 本单**没有**做的

- **没有** `launchctl bootout/bootstrap/kickstart`（§2.3）
- **没有**改任何 `ProgramArguments` / 排期 / 输出目录（`--outdir` 原样）
- **没有**改 `ci/out/com.kb.gates.generated.plist`（§2.4）
- **没有**改 AGENTS.md（§1②）
- **没有**统一模板与安装件的 `--scope` 差异（§4，等你裁）
- **没有**跑 `run_gates.py` 全量（它是只读的，但本单不需要它的读数；下次 14:00 自然跑）
