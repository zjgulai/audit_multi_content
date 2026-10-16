# `kb/l3/candidates/rules.jsonl`：哪几条能当定稿用 / 哪几条不能

- **判定时间**：2026-09-30 16:08（CST）
- **被判文件**：`kb/l3/candidates/rules.jsonl` — 1018 行 ｜ 2,778,734 字节 ｜ `sha256 = aa83d1f98bc86857254bfa4f908ebd6d1a869f868cb04970522d154f776b0dac`
  （自 15:52 起未变，与 15:55 / 15:57 两次判定同一快照 → 那两份的结论今天仍然成立）
- **逐条标记**：`定稿判定-rules.jsonl-20260930-1608-逐条标记.jsonl` — 632 行，一条规则一行 + 1 行 summary

---

## 一、结论（两句话）

1. **`rules.jsonl` 里的 509 条规则，一条不落，全部已定稿** —— 全部已发条款号（`W-1.1…W-1.56` + `W-2.1…W-2.453`），全部命中 `kb/l4/canonical/` 的 `status=stable` 记录。
2. **"不能当定稿"的规则不在这个文件里** —— 在隔壁 `kb/l3/candidates/external_standard.jsonl`，**123 条**，全部是候选、全部没号，而且**现在也发不了号**。

| | 条数 | 在哪 | 一句话状态 |
|---|---|---|---|
| **能当定稿用** | **509** | `rules.jsonl`（每组带号的那一行） | 已编号的定稿快照，可直接引用 |
| **不能当定稿** | **123** | `external_standard.jsonl` | 候选件，无号、无 owner、待人工复核，且无段可发号 |

> 限定词必须一起说：这 509 条是**机器晋升（machine-promoted）**。
> 按 L4 层自己的口径 —— **只允许当「已编号的定稿快照」用，不允许当「已发布版本」用**
> （`kb_version` 仍 `v0`，不产生 `release_id`）。做引用、做审查依据：可以。说"我们发布了 v1 规则集"：不可以。

---

## 二、为什么"判一条"要先看穿一个坑

**这个文件是 1018 行 = 509 个 `rule_id` × 2 行**：

| 行的来历 | 行数 | `article_no` |
|---|---|---|
| L3 候选行（蒸馏产出） | 509 | **空** |
| L4 追加行（`l4_article.py` 发号后追加，旧行逐字节不动） | 509 | `W-1.x` / `W-2.x` |

**两行除 `article_no` 外逐字段完全相同**（实测 509 组，0 组例外）。
所以：

- 只看头 509 行、或只看 `article_no` 为空的那一行 → 会得出"一条都没定稿"的**错误结论**；
- 正确读法：**按 `rule_id` 分组，取带号的那一行**；或**直接以 `kb/l4/canonical/` 为准**。
- 判"定稿了没"**永远不要看候选文件里的 `article_no` 字段** —— 那个字段按约定就该是空的。

---

## 三、判定依据（四条，全部可复算）

| # | 检查 | 实测 |
|---|---|---|
| 1 | 带号行是否命中 L4 canonical | **509 / 509** 命中 `wording_entry.jsonl`(56) + `wording_revision_pair.jsonl`(453) |
| 2 | 双向差集 | 候选有定稿没有 **0**；定稿有候选没有 **0**；`rule_id` 一一对应 |
| 3 | 正文字段是否被改写 | `rule_text` / `anchor` / `evidence_units` / `evidence_digest` / `support_count` **0 处漂移**（canonical 只加不改） |
| 4 | 闸门 | `kb/kbpy l7/scripts/l4_gate.py` → **✅ 过（C1–C6 全过，退出码 0）**；另：canonical 1242 条 `article_no` 唯一 1242 个，`rules.jsonl` 带号行号唯一 509 个，无撞号 |

引用时必须带的一件东西：**每条都有 `owner`、`half_life_days`、`valid_until`**，且
`valid_until ∈ {2026-12-28, 2027-03-28, 2027-09-29}` —— **按 2026-09-30 算，无一条过期**。

---

## 四、509 条里需要标注、但不影响"能当定稿"的 6 类旗标

逐条旗标都写在逐条标记文件里（`flags` 字段）。数量如下：

| 旗标 | 条数 | 怎么读 |
|---|---|---|
| `risk_level=unknown` | 454 | 源表（专家修订汇总表）**没有风险等级字段**，L4 按 P1 兜底。不是缺数据，是源头没有 |
| `support_count=1` | 447 | 全是 `revision_pair`（一对修订天然只有一条支撑）。L3 政策：只有归纳型才算证据不足，而 26 条归纳型**全部** `support_count ≥ 2` |
| `authority=inferred` | 93 | **模型归纳、无外部权威背书**。引用这类要说明"这是归纳推断，不是外部标准" |
| `半衰期 90 天档` | 22 | `valid_until=2026-12-28`，**这批最先到期**，最近一次复核窗口 |
| `E021-派生视图未过三重验证` | 56 | **见下方专门说明** |
| 候选副本字段 ≠ L4 定稿（关键三项） | **49** | 见下方"以谁为准" |

### 4.1 那 56 条（全是 `form=entry`）要单独说一句

`kb/l3/registry/l3.json → e021_concepts` 把这 **56 条 `form=entry` 判为"未过三重验证、不得进判断层"**
（`verdicts: 已排除 × 56`），派生视图（`kb/.work/gen-host-library*.py` → L1-facts / L2-concepts）据此
把它们**降层为事实**，以绕开 `kb_check` 的 E021。

**这不等于"这 56 条不算定稿"**：定稿口径在 L4，它们在 canonical 里是 `status=stable`、有号、有 owner。
但**拿它们进评审链当判断依据时要另核** —— 这是人的抽查动作，机器判不了。
换句话说：**可以引用，但别把它们当成"已经过三重验证的判断规则"。**

### 4.2 一个 p_level 反直觉的例子（说明"以 L4 为准"）

`r-006445396c95aa10`（`W-1.1`）：候选副本写 `p_level=P2`，L4 定稿写 **`P0`**，理由写在 canonical 的
`p_level_basis`：「全部支撑记录的风险等级均为高危·红 → P0」。

三个关键字段的漂移共 **49 条**（其余 460 条一致），且**方向两边都有**，不是"L4 一律升级"：

| 字段 | 条数 | 方向（候选 → L4） |
|---|---|---|
| `p_level` | 42 | P1→P0 ×15 ｜ P2→P1 ×10 ｜ **P1→P2 ×7** ｜ P2→P0 ×6 ｜ P1→P3 ×4 |
| `rule_code` | 21 | 候选为空 → L4 补出 `H06/H07/H08…` |
| `suggested_replacement` | 12 | **候选值 12/12 都是多规则字符串拼接**，L4 换成了属于本条那条规则的替换建议 |

`p_level` 五个方向都出现，正是因为 canonical 逐条给了 `p_level_basis`
（454 条「专家修订表无风险等级字段，按 P1 处理」、其余按来源灯色/风险等级逐条判）。

**结论：候选文件不是定稿正文的可信来源；引用一律回 `kb/l4/canonical/`。**

---

## 五、"不能当定稿"的 123 条：在隔壁文件，且现在发不了号

`kb/l3/candidates/external_standard.jsonl`（123 行，`sha256 = 7e3ac8ae…`）实测：

| 字段 | 值 |
|---|---|
| `kb_type` | 全部 `external_standard` |
| `status` / `rule_status` | 全部 `candidate` / 全部 `provisional` |
| `article_no` | **全部为空（123/123 未发号）** |
| `verification` / `evidence_level` | 全部 `待人工复核` / 全部 `cited` |
| `owner` | **全部为空** |
| `form` | recommendation 36 ｜ substantiation 24 ｜ disclosure 18 ｜ prohibition 16 ｜ scope 15 ｜ mandate 14 |
| `applicable_jurisdiction` | 全部 `US` |

**为什么"现在也发不了号"**：L4 的编号方案 `numbering.form_block` 只有
`entry / revision_pair / boundary / saythis` 四个形态段，**与这六个 form 零交集**
（实测 `set(forms) ∩ form_block = ∅`）→ 无段可发。
要发号必须**先由人给这六个 form 定形态段（改编号方案）**，那是改编号方案的事，不是发号脚本能顺手做的。

另附：`kb/l4/canonical/rules.jsonl` **恒 0 字节**（历史迁移留痕，故意保留）。
查它取"没定稿"是**错的** —— 定稿在四个形态文件里。

---

## 六、判完之后，两件"别被台账带偏"的事（只报告，不改库）

1. **L4 台账 `l4.json` 里写着"canonical 是空的"**
   `canonical.state = "空（本批不写；定稿要过抽查闸门，抽查是人工环节，不在本批）"`，
   而 canonical 四个文件里明明躺着 **1242 条 `stable` 定稿** —— **台账与事实自相矛盾**。
   这是 15:50–15:53 那次 `kb-pipeline --via-skill` 重建的残留（备份在 `kb/l4/_pre-rebuild-20260930-1550/`，
   其 `canonical.state` 原话是「已填…共 1242 条定稿记录；status=stable」）。
   → **判"定稿了没"不要读这个字段**，要读 canonical 文件本身。
2. **同一次重建还写丢了 733 个已发号码**
   现台账 `numbering.issued` 只剩 `W-1`(56) + `W-2`(453) = **509**；备份台账是 **1242**（含 `W-3`157 / `S-1`201 / `E-1`375），
   `next_seq` 也丢了 `W-3=158 / S-1=202 / E-1=376` 三个续号游标。
   **这不影响本文件里 509 条的定稿成立**（canonical 文件本身没被动，闸门仍过），
   但意味着：**谁现在拿这份台账跑一次 `l4_article.py --apply`，`W-3/S-1/E-1` 三段会被当成从没发过号，从 1 重发 → 撞号。**
   修它要走 `kb-repair` 或人决定用备份回灌还是重发 —— 不是"顺手改一个字段"。

---

## 七、本次判定期间库里有别的写入者（如实标注，不影响结论）

按 `layers.yaml`「任何结论必须带 run_id + 时间戳」的口径记一笔：

- 判定期间（16:00–16:08）有**多个并行进程**在跑：`kb_pipeline.py --sync --all`（持锁
  `kb/.work/.kb.lock` = run `20260930-1605`, pid 68516）以及数个 `kb_pipeline.py --check`。
- **被判文件没被动**：`rules.jsonl` sha 全程 `aa83d1f9…`、`external_standard.jsonl` `7e3ac8ae…`，
  16:08:33 复核仍与判定快照一致；canonical 四个文件 sha 亦未变。
- **`kb/l4/registry/l4.json` 在 16:03:27 被写过一次**（41,347 B，`run_id` 仍是 `20260930-1550`）：
  我读到的字段值（`canonical.state` 为空、`promotion_rule.status=待抽查`、`numbering.issued` 仅 W-1/W-2、`assignments=509`）
  **与本次读取时刻一致**，第六节的结论按那一刻成立；但这个文件正被其他进程反复重写，
  **别把它当稳定快照** —— 复算第六节时请以当时的实测值为准。
- 本次是**只读判定**：除两个交付文件（在库目录之外、非 `kb/` 内）外未写任何库内文件。

---

## 八、复算方法

```bash
cd /Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理   # = kb/ 的上一级
kb/kbpy l7/scripts/l4_gate.py          # 退出 0 = C1–C6 全过

python3 - <<'PY'
import json
rows=[json.loads(l) for l in open('kb/l3/candidates/rules.jsonl') if l.strip()]
print('总行',len(rows),'｜唯一 rule_id',len({r['rule_id'] for r in rows}),
      '｜带号行',sum(1 for r in rows if r['article_no']))
canon={}
for f in ['wording_entry','wording_revision_pair']:
    for l in open(f'kb/l4/canonical/{f}.jsonl'):
        if l.strip():
            d=json.loads(l); canon[d['rule_id']]=d
num={r['rule_id']:r for r in rows if r['article_no']}
print('带号行命中 canonical:',sum(1 for k in num if k in canon),'/',len(num))
print('canonical 多出:',len(set(canon)-set(num)),'｜候选多出:',len(set(num)-set(canon)))
print('canonical status:',{canon[k]['status'] for k in num})
PY

# 123 条不能当定稿的
python3 -c "
import json;rows=[json.loads(l) for l in open('kb/l3/candidates/external_standard.jsonl') if l.strip()]
print('行',len(rows),'｜有号',sum(1 for r in rows if r['article_no']))"
```

---

## 九、交付物与关系

| 文件 | 是什么 |
|---|---|
| `定稿判定-rules.jsonl-20260930-1608-逐条标记.jsonl` | **本次交付**：632 条（509 能 + 123 不能）＋ 1 行 summary，每条给 `verdict` / `blocking` / `flags` / `canonical_ref` / `owner` / `valid_until` |
| `定稿判定-rules.jsonl-20260930-1608.md` | 本文件 |
| `定稿判定-rules.jsonl-20260930-1557.jsonl` | 15:57 的先例，**同一快照**；本次 509 条的判定与它**逐条 0 分歧**（交叉核对过），但只覆盖 509 条、不含 123 条 |
| `晋升请求-20260930-1557-阻断单.md` | 同一批数据上"晋升/改台账"请求的阻断留痕，§3 的台账损坏细节出自这里 |
