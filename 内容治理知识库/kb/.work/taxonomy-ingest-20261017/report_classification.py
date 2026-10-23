#!/usr/bin/env python3
"""按库内现状出一份「分类 / 条数 / 占比 / 优先级」台账（只读，读权威库规则行）。"""
import json, collections, os, sys
KB = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

rows = {}
for rel, src in (('kb/l3/candidates/rules.jsonl', '措辞库'),
                 ('kb/l3/candidates/external_standard.jsonl', '外部标准')):
    for line in open(os.path.join(KB, rel), encoding='utf-8'):
        if not line.strip():
            continue
        r = json.loads(line)
        if src == '外部标准' or r.get('article_no'):
            rows[r['rule_id']] = dict(r, _src=src)

N = len(rows)
PV = ('P0', 'P1', 'P2', 'P3')
cat_cnt = collections.Counter(r['taxonomy_category'] for r in rows.values())
cat_p = collections.defaultdict(collections.Counter)
cat_src = collections.defaultdict(collections.Counter)
for r in rows.values():
    cat_p[r['taxonomy_category']][r['p_level']] += 1
    cat_src[r['taxonomy_category']][r['_src']] += 1
from openpyxl import load_workbook
wb = load_workbook(os.path.expanduser('~/Desktop/规则清单-P0-P3-按等级-20261016.xlsx'), data_only=True)
ws11 = wb['11类']
meaning = {}
for i in range(2, ws11.max_row + 1):
    n = ws11.cell(row=i, column=1).value
    if n and str(n).strip():
        meaning[str(n).strip()] = (ws11.cell(row=i, column=2).value or '').strip()

def pct(n, d=N):
    return f'{100.0*n/d:.1f}%'

L = []
A = L.append
A(f'# 知识库现状分类台账（{N} 条规则）')
A('')
A('> 数据源：`kb/l3/candidates/rules.jsonl`（措辞库 ' +
  str(collections.Counter(r['_src'] for r in rows.values())['措辞库']) +
  ' 条）＋ `kb/l3/candidates/external_standard.jsonl`（外部标准 ' +
  str(collections.Counter(r['_src'] for r in rows.values())['外部标准']) +
  ' 条）。字段 = `taxonomy_category` / `taxonomy_subcategory` / `p_level`。')
A('')
A('## 一、11 个类别 · 条数 / 占比 / 优先级分布')
A('')
A('| # | 所属类别 | 条数 | 占比 | P0 | P1 | P2 | P3 | 措辞库 | 外部标准 |')
A('|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|')
for i, (c, n) in enumerate(cat_cnt.most_common(), 1):
    p = cat_p[c]
    A(f'| {i} | {c} | {n} | {pct(n)} | {p.get("P0",0)} | {p.get("P1",0)} | '
      f'{p.get("P2",0)} | {p.get("P3",0)} | {cat_src[c]["措辞库"]} | {cat_src[c]["外部标准"]} |')
A(f'| — | **合计** | **{N}** | **100%** | '
  f'**{sum(c["P0"] for c in cat_p.values())}** | **{sum(c["P1"] for c in cat_p.values())}** | '
  f'**{sum(c["P2"] for c in cat_p.values())}** | **{sum(c["P3"] for c in cat_p.values())}** | '
  f'**{sum(c["措辞库"] for c in cat_src.values())}** | **{sum(c["外部标准"] for c in cat_src.values())}** |')
A('')
A('## 二、类别含义（表内「11类」sheet 逐字）')
A('')
for c, n in cat_cnt.most_common():
    m = meaning.get(c, '')
    A(f'### {c}（{n} 条 · {pct(n)}）')
    A('')
    A('```')
    A(m)
    A('```')
    A('')
A('## 三、58 个子类 · 条数 / 优先级分布')
A('')
sub = collections.defaultdict(lambda: collections.Counter())
sub_cnt = collections.Counter()
for r in rows.values():
    sub[(r['taxonomy_category'], r['taxonomy_subcategory'])][r['p_level']] += 1
    sub_cnt[(r['taxonomy_category'], r['taxonomy_subcategory'])] += 1
cur = None
for (c, s), n in sorted(sub_cnt.items(), key=lambda kv: (-cat_cnt[kv[0][0]], -kv[1], kv[0][1])):
    if c != cur:
        A('')
        A(f'### {c}（{cat_cnt[c]} 条 · {pct(cat_cnt[c])}）')
        A('')
        A('| 所属子类 | 条数 | 占全库 | P0 | P1 | P2 | P3 |')
        A('|---|---:|---:|---:|---:|---:|---:|')
        cur = c
    p = sub[(c, s)]
    A(f'| {s} | {n} | {pct(n)} | {p.get("P0",0)} | {p.get("P1",0)} | {p.get("P2",0)} | {p.get("P3",0)} |')
A('')
A('## 四、优先级总表')
A('')
pl = collections.Counter(r['p_level'] for r in rows.values())
A('| 优先级 | 条数 | 占比 | 说明 |')
A('|---|---:|---:|---|')
desc = {
 'P0': f'命中即 BLOCK。其中 **17 条**在 `kb/l5/p0_patterns.jsonl`（≤1s 快路、置信度 1.0、有法务签字台账），另 {pl["P0"]-17} 条走评审链**规则层**判 BLOCK',
 'P1': '安全与准确性；命中红线 → BLOCK，其余转人工',
 'P2': '通识与常识；取保守侧 REVIEW',
 'P3': '措辞与表达；仅出建议，不改结论（PRD §6.3 执行规则3）',
}
for k in PV:
    A(f'| {k} | {pl.get(k,0)} | {pct(pl.get(k,0))} | {desc[k]} |')
A(f'| **合计** | **{N}** | **100%** | — |')
A('')
A('## 五、边界（照实说）')
A('')
A('1. **11 类这套类目不是源表字段、也不是 PRD 原文类目** —— 它是 2026-10-16 会话里由助手（我）提出的分类体系，'
  'Owner 采用后落库；`kb/` 内除本次注册表外**没有第二处**定义这 11 类（`grep 合规与受监管宣称 kb/` 只命中注册表）。'
  '⇒ 类目的权威性需要 Owner 签字；与库内既有两套类目（`l7.json.vocabulary.categories` 8 类规则词表、'
  '`sample_case.reason_category` 7 类反例类目）以及 PRD §5.3 四维（合规/消费者安全/产品描述/措辞表达）的映射**尚未裁**。')
A('2. **`p_level` 有两个读法**：评审链规则层读规则行（＝本表口径）；'
  '只看引擎实际读取的 509 条就是 P0 40 / P1 137 / P2 213 / P3 119；L5 侧读 manifest 富化（仍是旧值）。本表按**规则行**统计 638 条（含外部标准 129 条；外部标准不进评审链规则层）。')
A('3. 占比分母统一是 **638**（509 措辞 + 129 外部标准）。若只看评审链实际读取的 509 条，分母换成 509，占比会变。')

text = '\n'.join(L) + '\n'
out = os.path.join(KB, '交付-规则分类现状台账-20261017.md')
open(out, 'w', encoding='utf-8').write(text)
print(text[:3000])
print('...')
print(f'\n已写 {os.path.relpath(out, KB)}（{len(text)} 字节）')
