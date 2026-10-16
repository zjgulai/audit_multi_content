---
name: kb-canonical-lookup
description: |
  Momcozy 内容治理知识库 **L4（定稿与发布层）** 的**只读查询**入口：
  查一条规则的**条款号**、查一个条款号对应哪条规则、查这条规则**定稿了没有**
  （canonical 状态 / 是否已发号 / 是否 stable）。
  当用户问「这条规则的条款号是多少 / 这个条款号对应哪条规则 / 这条规则定稿了吗 /
  进 canonical 了吗 / 发号了吗 / 条款号怎么分配的 / 这条还是草案吗 /
  L4 里有没有这条 / canonical 里有多少条」时使用。
  触发词：条款号是多少、条款号对应哪条规则、article_no、规则定稿了吗、进 canonical 了吗、
  发号了吗、canonical 状态、L4 查询、定稿与发布、kb-canonical-lookup。
  本 skill **只读**：不写库、不发号、不晋升。发号 / 晋升 canonical 是写操作，
  由 **kb-pipeline** 在 `--apply` 下编排 `kb/.work/l4_article.py` 执行。
  不适用（各自点名）：
    · 已经给出三态结论、要追问**结论的依据** → 走 **kb-content-review**；
    · 判断一段内容能不能发 → 走 **kb-review**；
    · 这个是不是 P0 → 走 **kb-p0-check**；召回单元 / 查资料 → 走 **kb-recall**；
    · 跑 L0 到 L7 / 同步知识库 → 走 **kb-pipeline**；
    · 知识库体检 / 闸门 → 走 **kb-check**。
version: "1.0.0"
last_updated: 2026-09-29
license: "Proprietary — Momcozy internal use only"
complexity: "simple"
compatibility:
  claude: { status: "native" }
  kimi: { status: "native" }
  cursor: { status: "native" }
  gpt: { status: "bridge", limitations: ["JSONL 解析需适配"] }
  minimax: { status: "bridge", limitations: ["长表需分页"] }
  dsh: { status: "native", notes: "只读，kbpy 同机可用" }
  codex: { status: "native" }
---

# kb-canonical-lookup —— L4 定稿与发布层 · 只读查询

**一句话**：回答"**这条规则的条款号是多少、定稿了没有**"。**只读，不写库。**

## 1. 数据在哪

| 项 | 位置 |
|---|---|
| 定稿记录（**四个形态，共 1242 条**） | `kb/l4/canonical/wording_entry.jsonl`（56）· `wording_revision_pair.jsonl`（453）· `sample_case.jsonl`（358）· `scoped_clause.jsonl`（375） |
| ⚠️ **不要查这个** | `kb/l4/canonical/rules.jsonl` —— **恒 0 字节 / 0 行**，是历史迁移留痕（保留不删）。查它一定返回空，不是"这条没定稿"。 |
| 注册表 / 发号方案 | `kb/l4/registry/*.json`（含每文件的 `lines` / `sha256` / `source` / `duplicate_source_rows`） |
| 运行记录 | `kb/l4/runs/<RUN>-*.json` |
| 引擎（**写操作，本 skill 不调**） | `kb/.work/l4_article.py RUN` · `l4_integrity.py` · `l4_report.py` |

cwd 必须是 `kb/` 的上一级（`~/.dsh/Momcozy知识库`）。

## 2. 两个查询

### 2.1 规则 → 条款号（"这条规则的条款号是多少"）

**要查的是那四个形态文件，不是 `rules.jsonl`**（后者 0 字节）。四个文件逐行一条 JSON，
每条都带 `article_no` + `anchor` + `authority`（实测样例见下）：

```bash
cd ~/.dsh/Momcozy知识库
# ① 先在四个形态文件里逐字命中（grep 够用，不用起 python）
grep -n "<rule_id 或关键词>" kb/l4/canonical/{wording_entry,wording_revision_pair,sample_case,scoped_clause}.jsonl | head
# ② 取出条款号字段
#    ⚠️ `kb/kbpy -` **不行**：kbpy 只接受文件路径（`[ -f "$target" ] || exit 2`），不读 stdin。
#    一次性片段用文档化的显式解释器写法；要复用就写成临时脚本再 `kb/kbpy <脚本>`。
KB_INTERP_OK=1 /usr/bin/python3 - <<'PY'
import json, glob
for f in glob.glob('kb/l4/canonical/*.jsonl'):
    if f.endswith('rules.jsonl'):
        continue                      # ← 0 字节的历史留痕，跳过
    for line in open(f, encoding='utf-8'):
        r = json.loads(line)
        if '<关键词>' in json.dumps(r, ensure_ascii=False):
            print(f.split('/')[-1], '|', r.get('article_no'), '|', r.get('anchor'))
PY
```
**实测样例**（可直接复现）：`kb/l4/canonical/wording_entry.jsonl` 第 1 行
→ `article_no="W-1.1"`、`anchor="#广告文案明细/recvuJYdOb61lT/命中片段"`、
`authority="expert"`、`cite_check.evidence_units=9`。

### 2.2 条款号 → 规则（"这个条款号对应哪条规则"）

同一批四个形态文件，按 `article_no` 反查（形如 `W-1.1`；前缀与形态对应：
`W-` = wording_entry / wording_revision_pair，`S-` = sample_case，`C-` = scoped_clause —— **以
`kb/l4/registry/l4.json` 的编号方案为准，不要凭前缀猜**）。

### 2.3 定稿了没有（"进 canonical 了吗"）

看 `kb/l4/registry/*.json` 的 `canonical.state` 与逐文件 `status`；
再按 `rule_id` 在**四个形态文件**里是否命中（**跳过 `rules.jsonl`**），**命中 = 已定稿（已发号）**，
未命中 = 仍是 `kb/l3/candidates/rules.jsonl` 里的候选。

## 3. 输出契约（照这个格式答，别自由发挥）

```
条款号：<article_no>
规则：<rule_id> · <一句话规则原文>
定稿状态：stable（已发号） | 仍是候选（未发号）
来源：kb/l4/canonical/<file>.jsonl #<行号>
source_sha256：<...>
证据级：L? ｜ 有效期：valid_until
```

**查不到就写"知识库查不到"** —— 不许用相近规则顶替，也不许从 L3 候选外推成"已定稿"。

## 4. 红线

- **不写**：不调 `l4_article.py`、不改 canonical、不补号。
- **不混淆 L3 与 L4**：`kb/l3/candidates/rules.jsonl` 是**候选**，`kb/l4/canonical/` 才是**定稿**。
  把候选说成定稿 = 引用越级。
- **条款号是引用契约的一部分**：引用时必须与 `kb/l7/registry/l7.json` 的 citation_contract 一致。

## 5. 何时停下来问人

- 条款号在同一 `rule_id` 上出现两个不同值 → 报冲突，**不要挑一个**。
- canonical 注册表的 `sha256` 与实际文件不符 → 只报告，交 `kb-check` / `kb-repair`。
- 用户要"给它发个号" → 那是写操作，交 `kb-pipeline`（`--apply`）。
