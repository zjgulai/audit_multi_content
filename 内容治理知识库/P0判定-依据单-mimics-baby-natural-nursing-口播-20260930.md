# P0 判定 · 依据单 —— 口播「mimics baby's natural nursing」

> 提问入口：`kb-p0-check`（L5 P0 判定层 · **只读查询档**）
> 本次**只读**：未调 `l5_prep.py` / `l5_export.py`，未改 `p0_patterns.jsonl`，未发号、未晋升、未动 canonical 与台账。
> cwd：`…/skills-回归测试/知识库/内容治理`（= `kb/` 的上一级）

---

## 0. 一句话结论

**是 P0，触碰红线。** 命中 `H09`，匹配器 `match_note = BLOCK`。
**不是**「未命中」，也**不能**按「只是措辞建议」处理 —— 它是 P0 层最高优先级条目。

判据是**确定性命中**（命中即 P0），**不需要语义推断**。

---

## 1. L5 本层产出（确定性匹配）

```bash
cd …/知识库/内容治理
kb/kbpy l5/matcher.py --text "mimics baby's natural nursing" --json
```

```
是否 P0：是
命中模式：H09（pattern_id=p-d31dfbc932cb84ac，authority=expert，match_note=BLOCK）
命中片段：mimics baby's natural nursing
         命中方式 regex：\bmimic(s|king)?\b[^.]{0,30}\bbaby\b   span=[0,11]
whitelist_suppressed：0   ← 未被豁免规则吞掉
来源：kb/l5/p0_patterns.jsonl 第 6 行
```

`kb/kbpy l5/matcher.py --selftest` 复跑：**正例全命中、负例零误报**（exit 0）。自测正例里本就含
`Designed to mimic baby's natural nursing rhythm.` → HIT H09。

---

## 2. 变体实测（撇号/引号/语境 都试过）

| 输入 | 命中 | 说明 |
|---|---|---|
| `mimics baby's natural nursing`（**直撇号** U+0027） | **HIT H09 / P0 / BLOCK** | 用户给的原样，`whitelist_suppressed=0` |
| `mimics baby’s natural nursing`（**弯撇号** U+2019） | **HIT H09 ×2** | 模式表字面词 + regex 双命中 |
| `the motor mimics baby's natural nursing rhythm`（**句中**） | **HIT H09** | regex 覆盖 30 字符内的「mimic…baby」 |
| `mimicking baby natural nursing`（**词形变化**） | **HIT H09** | regex 覆盖 `mimic(s\|king)` |
| `inspired by natural nursing`（**允许替代**） | 0 命中 | 与 W-1.31 的豁免词一致 |
| `“mimics baby's natural nursing”`（**被引号包裹**） | 0 命中 | 见 §5.2，是豁免规则的已知盲区 |

**撇号字形不影响判定**：模式表字面词写的是弯撇号 `baby’s`，但 regex 分支照样命中直撇号写法 ——
**别指望靠改标点绕过去**。

---

## 3. 证据链（可回源）

| 项 | 值 |
|---|---|
| `anchor` | `#广告文案明细/recvuJYdOb61lT/命中片段` |
| `authority` | `expert` |
| `rule_id` / `rule_code` | `r-006445396c95aa10` / `H09` |
| `source_sha256` | `67875346a75bd2f81a40b387652d6824faefe083f61c025c5801034ab6d4074e` |

9 个证据单元 `unit_id`：`74d1ba6b94a5336853dd` · `0d3289c8b0363292fff1` · `cb3ae64719ed621f4e63` ·
`5f9f482b4bade3657b3b` · `0c2cc17745aa61d72ba5` · `6e4f7cd4b290ee3ce3d3` ·
`4db6e029b86b84d2bd23` · `ade7467190e6baa76b61` · `1430107f00011461366c`

**已回源核对**（L2）：

- `kb/l2/units.jsonl` → unit `74d1ba6b94a5336853dd`，`source_sha256` 与上表**逐字相同**，
  `rule_eligible=true`；
- 该单元正文：`H02:increase milk supply / H07:pain-free / H09:mimics baby,mimics baby’s natural nursing`；
- 同源记录 `bitable__Lk3Qb8y2QaVyZns6gprcVNE9nA0__recvuJYdOb61lT` 的 `Primary Text` 里，
  原广告逐字为 **`Mimics baby’s natural nursing with heated massage.`**（撇号实测 U+2019）。

---

## 4. 条款号（L4，跨层只读核对）

**条款号 = `W-1.1`**（`kb/l4/canonical/wording_entry.jsonl` 第 1 行；`status=stable`，`p_level=P0`，
`owner=法务 + 产品负责人`，`valid_until=2027-09-29` 未过期）。
三处一致：canonical 文件 / `kb/l4/registry/l4.json → numbering.issued["W-1"].assigned["r-006445396c95aa10"]` / 四形态文件全扫仅出现 1 次，号不歧义。

> 层归属：**P0 判定出自 L5**（`p0_patterns.jsonl` 第 6 行）；**条款号出自 L4**。
> 对外引用请分开写，别把 W-1.1 说成 L5 给的。
> 另：`W-1.1` 在 L4 侧 `source_sha256` 为 `null`，按 `l7.json → citation_contract.hard_gate` 过不了指纹硬闸门
> —— 要带指纹引用，用 L5 这条的 `67875346…`。

---

## 5. 边界（引用前必须知道）

1. **命中 P0 ≠ 泛泛的"违规结论"**：P0 是**最高优先级**口径。本条 `match_note=BLOCK`，属需拦截档；
   但**「能不能发」的三态结论不归 L5**，走 `kb-review` / 视频专项。
2. **引号包裹会被豁免吞掉（实测盲区）**：`whitelist` 里有一条
   `[「『"“][^」』"”]{0,80}[」』"”]`，本意是「别把**被引用的禁用词**（禁用词清单、审查文档里的引用）判成命中」。
   副作用：材质里若把这句话**原样打上引号**（如 `“mimics baby's natural nursing”`、`「…」`），
   匹配器会报 0 命中。所以本判定**只对「这就是文案本身」成立**，不对「别人在引用它」成立 ——
   拿到素材时先确认它是**实际播出的口播/字幕**，不是在引用。
3. **L3 与 L4/L5 的 `p_level` 不一致（既有、已核，交 `kb-check`）**：
   同一 `rule_id` 在 `kb/l3/candidates/rules.jsonl`（第 5、510 行）里 `p_level="P2"`，
   而 L5 模式表与 L4 `W-1.1` 都是 `P0`。全层分布：**L3 去重 509 条里 P0 = 0 条**（P1 493 / P2 16），
   而 L5 的选取口径白纸黑字写着 `p_level=P0`、`excluded.non_P0=488`（该算式反推上游应有 **21 条 P0**，
   与 L4 `wording_entry` 的 21 条 P0 吻合）。
   → **L5 / L4 的 P0 结论仍然成立且可复算**，但 **L3 侧现已无 P0 可查**；这是层间口径冲突，不是本 skill 能改的，
   按 `kb-p0-check` §3 规则**报冲突、交 `kb-check`**。
4. **未命中 ≠ 合规**：本 skill 只答「是不是 P0」，其余风险仍走 `kb-review`。

---

## 6. 处置建议（人裁）

- 该口播**删除或改写**；仿生表达只允许 `inspired by natural nursing`（参考自然哺乳节奏的设计思路），
  不得写成「模拟/复制/还原宝宝」的等效说法（同族红线另见 `W-1.31`）。
- 改稿后**重新过一遍** `l5/matcher.py --text "<改后全文>"`，确认 0 命中再回 `kb-review` 走三态。
