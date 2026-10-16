# 批次13 · A/B/C/D 收口报告

**执行时间**：2026-10-02 08:31 起（+08:00）
**token 状态**：08:31 检查 `user.status=ready / tokenStatus=valid`，`expiresAt=09:11:34`（约 40 分钟余量）
**做到哪一块**：见末节（按 §0 预算约定）

---

## D 块 · L0 闸门红 —— **根因查清，但 D-3 无法在本批达成（如实报红）**

### D-1 真拉证据（**成功**）

token 有效期内完成真拉，逐字结果：

```
$ L8_AS=user L8_PROFILE=dsh-kb kb/kbpy l8/align_l0_feishu.py 20261002-0832
[负面样本] 飞书=170 L0=170 一致=0 飞书多=0 L0多=0 值变=170
[材料收集] 飞书=32  L0=22  一致=0 飞书多=10 L0多=0 值变=22
[专家修订汇总表] 飞书=395 L0=395 一致=395 …
[内容公式（仅供参考）] 飞书=7 L0=7 一致=7 …
=== 汇总 ===
  一致 822 | 飞书多 10 | L0多 0 | 值变 192 | 拉取失败 0     ← ★ 拉取失败 0
```

| 项 | 实测值 |
|---|---|
| 真拉 RUN | `20261002-0832` |
| 报告 | `kb/l8/runs/20261002-0832-l0-align.json`（36,293 B） |
| 负面样本实际条数 | **170**（`feishu-align/20261002-0832/tbld8qE92YaY38Yz.ndjson`，rev=1754） |
| 材料收集实际条数 | **32** 飞书 / **22** 入 L0 |
| **拉取失败** | **0**（user 身份下两张 ACL 表也读到了：专家修订汇总表 395、内容公式 7） |

**物化暂存**（`materialize_l0_compare.py 20261002-0832 --apply`）：

```
feishu-材料收集.ndjson      2026-10-02T08:32:26
feishu-负面样本.ndjson      2026-10-02T08:32:26
PROVENANCE.json             align_run=20261002-0832
```

**以 `stage_fresh=True` 跑 reconcile（`20261002-0833`）**：

```json
{ "stage_read": "kb/l8/_stage/feishu-compare",
  "stage_fresh": true,
  "stage_mtime_min": "2026-10-02 08:32:26",
  "write_gate": "fresh",
  "actions": [ {"action":"claim_new","files":170}, {"action":"refresh_capture","files":22} ] }
```

⇒ **批12 的质疑被答复：170 / 22 是新鲜真值，不是陈旧暂存产物。**
（批12 那两遍确实是在 `stage_fresh=False` 下跑的；本批换真拉重证了一遍。）

### ★ 但真正的发现是：这 192 条「值变」**其实是比对口径缺陷，不是数据变更**

我按 `align_l0_feishu.py:150-156` 的**同一逻辑**逐条复算，差异字段分布只有一个键：

```
按 align 的逻辑，差异字段分布:
  record_id  x170
      快照=null
      L0  ="recvw7XIUg06K0"
  （其余业务字段差异 = 0）
```

**机制**（`kb/l8/align_l0_feishu.py:150`）：

```python
fvals = {k: v for k, v in fs[rid].items() if k not in ("record_id", "recordId")}   # ← 剥掉
lvals = {k: (fd or {}).get("value") for k, fd in (l0[rid][1].get("fields") or {}).items()}
for k in set(fvals) | set(lvals):                                                  # ← 比并集
    if canon(fvals.get(k)) != canon(lvals.get(k)):
```

- 飞书快照行的 `record_id` **被剥掉** ⇒ `fvals.get("record_id")` = `None`
- 而 L0 记录文件的 `fields` 字典**含 `record_id`**（`write_record` 用 `fields_of()` 的字段表建 `fields`，其中含 `record_id`，值 = 该记录 id）⇒ `lvals.get("record_id")` = `"recvw7XIUg06K0"`
- 比并集 ⇒ `canon(None) != canon("recvw...")` ⇒ **每条都判「变了」**

**业务字段层面：170 条负面样本里，业务字段差异 = 0 条。**

⇒ 所以 **`值变 192` 是「拿被剥掉的键去比」造出来的 192 条不存在的变更**，
与「L0 与飞书不一致」无关。已登记为 `CD-1`（`l0-expected-diffs.yaml → known_comparator_defect`）。

### D-2 声明原文

`kb/l7/registry/l0-expected-diffs.yaml` 新增 `EX-4` / `EX-5`（按既有 EX-n 体例），
每条带 `evidence`（可回指路径）+ `owner_action` + `reopen_when`：

- **EX-4** 负面样本 / `value_changed` / expected **170** / 依据：
  `20261002-0832-l0-align.json`（真拉，拉取失败 0）、`20261002-0833-l0-feishu-reconcile.json`
  （`stage_fresh=true` / `claim_new=170`）、`PROVENANCE.json`（物化来源=真拉）、
  逐字段复算（差异只有 `record_id`×170）
- **EX-5** 材料收集 / `value_changed` / expected **22** / 同一证据链

### ★★ D-3 **未达成，且原因是结构性的** —— 不掩盖

`l0_gate.py` 实测仍：

```
结论：❌ 未过（真差异 2）    退出码：1
```

**为什么「加了声明也不绿」**（读闸门源码实测，非推测）：

| 位置 | 硬编码 | 后果 |
|---|---|---|
| `kb/l7/scripts/l0_gate.py:129-139` | `kind` 只识别 `only_feishu` / `pull_failed`，**其它一律 `act = 0`** | 无论我写什么 kind，都拿不到 `ch` 计数 ⇒ 声明读成「少于预期」 |
| `kb/l7/scripts/l0_gate.py:160` | `if t["ch"]: uncovered.append("… 值变 %d（**不允许豁免**）")` | **只要 `值变` 非 0 就无条件判红，与 expected 声明无关** |

⇒ **「值变」这一类在本闸门里是结构性不可声明的。** EX-4/EX-5 的 `expected: 170/22`
**是「意图声明」，不是「生效声明」** —— 我把这句话写进了该 YAML 的注释里，**不假装它已经把闸门刷绿**。

**两条出路，两条都超出本批授权/边界，故本批不做**：

- **路径甲（推荐）**：修对账器 `kb/l8/align_l0_feishu.py:150` 的 `record_id` 比对口径
  ⇒ 值变自然回落 0 ⇒ 闸门绿，**且不是靠豁免绿的**。
- **路径乙**：给 `l0_gate.py` 加 `value_changed` 处理器 —— 那等于给「不允许豁免」的类目**开口子**，
  **风险更高，不推荐**。

**本批选择：保持红，如实报** —— 遵守你 §D-2「若证不出 ⇒ 保持红，不许为了把闸门刷绿而加声明」。
**注意我用词**：我**证出了**差异不存在（证据充分），但**证不出「它是可声明的预期差异」** ——
因为闸门没有那个机制。这两件事不同，我分开说，不含糊。

### D-3 三条判据实测

| # | 判据 | 实测 | 结论 |
|---|---|---|---|
| 1 | `l0_gate.py` exit=0 | **exit=1**，真差异 2（`值变 170` / `值变 22`） | ❌ **仍红**（原因：结构性，见上） |
| 2 | `daily_health.py` 闸门 过8/红0 | **过7/红1** | ❌ **未达成**（红 1 条 = L0 闸门红） |
| 3 | 零写自证仍为 True | **零写: True** | ✅ 保持 |

`daily_health` 改前 = 改后：`健康: RED ｜ 闸门 过7/红1/未判0 ｜ 零写: True`，
要人做 2 条（① L0 闸门红 ② L4 的 wording_entry.jsonl 落后 2.9 天）。
**本批未把 L0 那条刷绿**，如实保留。

### D-1 期间顺带修掉的一个**我自己**的缺陷（附）

批11 我加的新鲜度闸门初版扫**整个暂存目录**的最早 mtime，被目录里的无关陈旧件带偏：
`feishu-compare/login-qr.png`（Sep 29 10:12）导致 materially-fresh 的目录仍判「陈旧」⇒
**门禁变成永远过不去的死路**（实测 `exit=4`）。
已修为**只看本脚本真正要读的四个文件**（两个 `feishu-*.ndjson` + 两个 `fields-*.json`），
且**四个都必须在**（子集按最保守处理＝陈旧）。
这与批11 自测踩到的 `copy2` 保留 mtime 是**同一类错**：拿无关量当判据。
