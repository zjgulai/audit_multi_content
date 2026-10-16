# 改动单：`reserved_unused_segments` 从「硬编码字面量」改成「派生」

日期 2026-10-12 ｜ 层 L4 ｜ 动到的文件：`kb/.work/l4_article.py`（活引擎）、`kb/l4/registry/l4.json`（台账）

---

## 0. 一句话

`kb/l4/registry/l4.json` 的 `numbering.totals.reserved_unused_segments` 把**已在用的 E-2**
列进「未用」，与**同一份 totals** 里的 `segments_used` 自相矛盾。
病根不是那一个字母 E，是**这个键原本是一张手写的硬编码字面量**，
而 `l4_article.py` 的 `totals` 是**整块承接**的 ⇒ 错值**每跑一次就被原样重发一次**。
本次把它改成**派生**（真源 = `numbering.block_by_library` 的 `state`），并订正已存下来的那个值。

---

## 1. 缺陷（每条可核）

### 1.1 同一份 dict 自己打自己

```
segments_used            = [E-1, E-2, S-1, W-1, W-2, W-3]      ← E-2 在「已用」
reserved_unused_segments = [W-4, W-5, W-6, S-2, E-2, P-1]      ← E-2 又在「未用」
```

而权威的逐段状态写着 E-2 是已发：

```
kb/l4/registry/l4.json → numbering.block_by_library.external_standard.E-2.state == "issued"
                        （label = clause（法条型））
numbering.e2_ledger_patch = {run: 20261001-1015, segment: E-2, added: 123, …}
```

`clause.jsonl` 真有 123 条（E-2.1 … E-2.123）。
⇒「未用」那一侧是错的，且**不是陈年笔误**。

### 1.2 出处：它是一张手写表

`kb/l7/_backups/interp-20260929-175116/.work/batch9_assign.py:121`

```python
"reserved_unused_segments":[f"{p}" for p,lib in [("W-4","wording"),("W-5","wording"),
    ("W-6","wording"),("S-2","internal_sample"),("E-2","external_standard"),
    ("P-1","product_desc")]],
```

写它的时候（2026-09-29）E-2 确实还预留 —— 那份表当时是对的。
20261001-1015 的 `e2_ledger_patch` 把 E-2 的 `state` 改成 `issued` 时，**没有人同步这张表**。

### 1.3 为什么它此后**每次跑批都会重生**

`kb/.work/l4_article.py`（`layers.yaml::L4.engine` 在册的活引擎）里有：

```python
prev_totals = dict(prev_numbering.get("totals") or {})   # ← 整块承接旧 totals
prev_totals.update({ ... "segments_used": sorted(merged_issued),
                         "libraries_used": sorted({...}) })   # ← 这两个是现算的
```

`reserved_unused_segments` **不在 update 里** ⇒ 它**原样带着旧字面量往下走**。
`kb/.work/l4_ledger_repair.py:204` 同样是 `{**旧 totals, …}` 展开。
⇒ 相邻两个键，一个现算、一个手写；手写的那个**永远追不上** state 的变化。

### 1.4 它已经在往外扩散

`kb/l4/runs/E2E-20261012-1205-L4-dryrun.json`（今日 12:05 的端到端验收留痕）里：

```
.numbering.totals.reserved_unused_segments = ["W-4","W-5","W-6","S-2","E-2","P-1"]
```

⇒ 不是躺着的台账笔误，是**每份 run 快照都在复述这个错**。

### 1.5 活消费者：零

全仓搜 `reserved_unused_segments`，命中只有：`.work/` 里的一次性脚本与注释、
一份 `_backups/`、以及 `l4.json` 自己。`l4_gate.py` / `l7_gate.py` **都不核这个键**。
⇒ 修它对闸门无影响，也就**不能靠闸门发现它** —— 这正是它活了 11 天的原因。

---

## 2. 改了什么

### 2.1 代码：让它派生（`kb/.work/l4_article.py`）

在 `prev_totals.update({…})` 里补一项，与 `segments_used` / `libraries_used` **同一个口**：

```python
"reserved_unused_segments": sorted(
    seg for _lib, _segs in BLOCK_BY_LIB.items()
    for seg, _info in (_segs or {}).items()
    if _info.get("state") == "reserved_unused"
),
```

- `BLOCK_BY_LIB` 是该脚本 line 167 已有的权威源（`numbering.block_by_library`），非新造。
- 口径**照抄** `kb/.work/l7_article_source_refresh.py:91-98`（那边早就这么算了，还留着一次自我更正的注释）
  —— 取**段键短名**，因为 block 号跨库不唯一。
- `sorted()` 与相邻的 `segments_used` 一致。

### 2.2 台账：订正已存下来的那个值

`kb/.work/fix_l4_reserved_derived.py`（新，默认预演，`--apply` 才落）

- 归档：`kb/l4/_archive/l4.json.before-reserved-derived-20261012-122929`
  （sha256 `181e841b8e057cd6…`，**与归档前原件逐字节相同**，脚本自校验）
- 落盘后**逐键比对 8936 个叶键，差异恰好 1 处** —— 就是 `numbering.totals.reserved_unused_segments`
- 幂等：再跑一次判「已是派生值，零写入」
- 脚本**不自创口径**：断言的期望值 `[P-1, S-2, W-4, W-5, W-6]` 就是真引擎跑出来的产物，对不上就拒写

新值：`["P-1","S-2","W-4","W-5","W-6"]`（E-2 消失，且与 `segments_used` 交集为空）
`l4.json` 新 sha256：`16e2e2519e8a51bb…`

---

## 3. 反向对照（把缺陷真造一遍）

### 3.1 两向变异 —— 派生值必须跟着 `state` 动

在**镜像沙箱**里跑真引擎（`kb/l0..l3` 软链只读、`kb/l4` 真副本），先记跑前 sha，跑后核对：

| 变异 | 派生结果 |
|---|---|
| ① 基线（不变异） | `[P-1, S-2, W-4, W-5, W-6]` |
| ② `E-2.state` → `reserved_unused` | `[E-2, P-1, S-2, W-4, W-5, W-6]` ← 长回来了 |
| ③ `W-4.state` → `issued` | `[P-1, S-2, W-5, W-6]` ← 掉出去了 |

两向都对 ⇒ 值是真派生的，不是硬编码。

### 3.2 改前 / 改后 A/B —— 同一份真库现值喂两个版本

| | 输入 | 输出 |
|---|---|---|
| **A) 改前代码** | 真库现值 `[W-4,W-5,W-6,S-2,E-2,P-1]` | `[W-4,W-5,W-6,S-2,E-2,P-1]` ← **原样照抄，完全无视 E-2 已是 issued** |
| **B) 改后代码** | 同上 | `[P-1,S-2,W-4,W-5,W-6]` ← 消掉 E-2 |

A 这一行就是缺陷的定义：**它对 `state` 的变化完全瞎**。
（改前代码 = 从现文件里删掉本次新增的派生块，其余逐字不动。）

### 3.3 沙箱不碰真库

跑真引擎 `--apply` 期间的例外对照：真库 `kb/l3/candidates/*.jsonl` 四个候选件
sha256 **跑前跑后完全一致**（`39d7f25a… / 92694e86… / 225da7db… / 0e1aecde…`）。
引擎自报「追加 0 行、旧行逐字节未变 True」。

---

## 4. 尺子

13 道闸门**全部退出 0**（非零 0 条）：

```
l0_gate 0   l1_gate 0   l2_gate 0   l3_gate 0   l4_gate 0   l5_gate 0   l6_gate 0
l7_gate 0   layers_check 0   workflow_smoke 0   envelope_census 0
check_source_readonly 0   regression_gate 0
```

自测：`risk_category.py` 24/24 ｜ `kb_rule_dimensions.py` 55/55 ｜ `audit_sample.py` 26/26

> ⚠️ 更正：本会话此前报过的「11 道尺子」里有一个 **`btable_stats` —— 全仓不存在这个文件**。
> 那是笔记里记错的条目。上面这份是**真的跑出来**的清单（13 道）。

---

## 5. 回滚

```bash
cp kb/l4/_archive/l4.json.before-reserved-derived-20261012-122929 kb/l4/registry/l4.json
```
代码侧把 `kb/.work/l4_article.py` 里那段带 ★2026-10-12 标记的派生块删掉即回到改动前。

---

## 6. 本次**没有**做的事，以及为什么

### 6.1 「另 509 条 cite_check 也补上」—— **不做**（结论翻转）

上一轮我推荐「补」。核过判据之后**推翻自己**：

`kb/l7/scripts/l4_gate.py:108-116`（`l7_gate.py:128-134` 同构）：

```python
for e in (d.get("evidence_units") or []):        # 有 evidence_units ⇒ 就用它
    out.append((...))
if not out:                                      # ← 只有空集才回落到 cite_check
    ... cc.get("source_sha256")
```

各形态实际走哪支：

| 文件 | 行数 | `evidence_units` | 闸门走 |
|---|---|---|---|
| `clause.jsonl` | 123 | 有（各 1 个） | evidence_units |
| `sample_case.jsonl` | 473 | **无** | cite_check（已 473/473） |
| `scoped_clause.jsonl` | 375 | **无** | cite_check（已 375/375） |
| `wording_entry.jsonl` | 56 | 有（2–153 个） | evidence_units |
| `wording_revision_pair.jsonl` | 453 | 有（1–246 个） | evidence_units |

⇒ 那 509 条的 `cite_check.source_sha256 = null` **没有任何闸门会读**，
它们由 `evidence_units` 承担证据，C3/C4 本来就过。
**更关键的是口径**：wording 行有 **2–246 个**证据单元，
把 `[0]` 的 sha 投影成「这条的」sha，等于**拿一个单元的指纹冒充整条的** —— 那是**编**，不是留痕。

### 6.2 「我的 目标 2 是不是修了一道闸门红？」—— **不是**

同上表：`clause.jsonl` 有 `evidence_units`（各 1 个）⇒ 闸门走 evidence_units，
**`l4_gate`/`l7_gate` 从来没有因为 clause 的 `cite_check` 红过。**
所以 目标 2 那 123 条的补齐，性质是**补留痕**（xlsx 目标 2 的原话就是
「123 条**条款**的 `cite_check.source_sha256` = 0/123，这条承诺没有任何核对记录」），
**不是**修闸门红。交付件里当时的措辞若让人读成后者，以本条为准。

其中 `clause` 各只有 **1 个**证据单元 ⇒ 投影 `[0]` 是**无歧义**的，那一步仍然成立。

### 6.3 一条顺带发现（**未改**，登记待裁）

`kb/l7/scripts/l7_gate.py:120-121` 的注释写着「**条款形态**证据在顶层 anchor + `cite_check.source_sha256`」，
但**代码**（:128-134）是「先试 `evidence_units`，空才回落 `cite_check`」。
`clause` 有 `evidence_units` ⇒ 按代码走的**不是**注释说的那一支。
**注释与代码对「clause 走哪支」说法不一致。** 属措辞级漂移，不影响判定 ——
本次**不动**（不给自己加需求），在此登记。

---

## 7. 已知残留（照实说）

1. `kb/l4/registry/l4.json` 的 `inputs.base_sha256` 记的是 `3f7d50dc…`，
   而 `kb/l3/candidates/rules.jsonl` 现值是 `92694e86…`。
   **这不是新缺陷**：真库记的是今晨 03:30 日更**当时消费的** sha，
   而 `rules.jsonl` 是在 03:30 之后才被改动的 ⇒ 属正常的「日更落后于文件」，**下次日更自会对齐**。
2. 本次**没有**真跑 `l4_article.py --apply` 去写真库台账 —— 只改了代码 + 就地订正一个值。
   ⇒ 真库 `l4.json` 的 `run_id` 仍是 `daily-20261012-0330-L4`，**没有伪造一次「我跑过」的出处**。
   下次日更跑 L4 时，引擎会按新代码重算这个键，值不变（已幂等验证）。
3. `kb/l4/canonical/rules.jsonl` 是 **0 字节空壳**（六形态分文件之后的遗留）。
   509 条 wording 规则已在 `wording_entry`(56) + `wording_revision_pair`(453) = 509 ✅，不缺内容。**未动。**

---

## 8. 撞车核对

动手前查过：另一会话当时在 `kb/l5/*`（`p0_patterns.jsonl` / `matcher.py` / 法务签署台账 / `h02fix-20261012-1226` 跑批）
＋ `kb/.work/regression-*`。**与 `kb/l4/*` 不相交。**
`kb_loop_claim.py status` 当时报「无认领」。落盘窗口内 `kb/l4/` 无第三方写入。
