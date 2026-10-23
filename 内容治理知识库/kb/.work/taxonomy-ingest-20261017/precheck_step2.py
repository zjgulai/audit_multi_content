#!/usr/bin/env python3
"""步骤2 的前置核对：三字段是否「都符合」再入库。只读。
检查项：
 C1 638 行三字段非空
 C2 优先级 ∈ {P0,P1,P2,P3}，且分布与表头自述一致（63/243/213/119）
 C3 所属类别 ∈ 11 类枚举（含「未归类」）
 C4 所属子类 → 所属类别 是一对一（无同名子类挂两个类别），且与「规则占比」sheet 一致
 C5 「11类」sheet 里声明了含义的 11 个类别与表内出现集合一致
 C6 17 条 P0 快路 = p0_patterns.jsonl 的 rule_id 集合，且全部 P0
 C7 源「修订类型」缺失的那条（W-2.350）保持 KB 原值（不猜）
 C8 rule_id 与 KB 一一对应（509+129），无增减
 C9 每条 (类别,子类) 组合都出现在「规则占比」sheet 且条数一致
"""
import json, os, sys, collections
from openpyxl import load_workbook

KB = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
XLSX = os.path.expanduser('~/Desktop/规则清单-P0-P3-按等级-20261016.xlsx')
ok = fail = 0
def ck(name, cond, detail=""):
    global ok, fail
    if cond: ok += 1; print(f'  ✅ {name} {detail}')
    else:    fail += 1; print(f'  ❌ {name} {detail}')

wb = load_workbook(XLSX, data_only=True)
ws = wb['全部规则 (P0-P3)']
hdr = [ws.cell(row=5, column=c).value for c in range(1, 44)]
rows = []
for r in range(6, ws.max_row + 1):
    v = [ws.cell(row=r, column=c).value for c in range(1, 44)]
    if all(x is None for x in v): continue
    rows.append(dict(zip(hdr, v)))
print(f'表：{len(rows)} 行')

# KB 侧
kb = {}
for p in ('kb/l3/candidates/rules.jsonl', 'kb/l3/candidates/external_standard.jsonl'):
    for line in open(os.path.join(KB, p), encoding='utf-8'):
        if line.strip():
            r = json.loads(line)
            if p.endswith('external_standard.jsonl') or r.get('article_no'):
                kb[r['rule_id']] = r

print('\nC1 三字段非空')
ck('C1 优先级非空', all(str(r['优先级'] or '').strip() for r in rows))
ck('C1 所属类别非空', all(str(r['所属类别'] or '').strip() for r in rows))
ck('C1 所属子类非空', all(str(r['所属子类'] or '').strip() for r in rows))

print('\nC2 优先级枚举与分布')
dist = collections.Counter(r['优先级'] for r in rows)
ck('C2 枚举合法', set(dist) <= {'P0','P1','P2','P3'}, str(dict(dist)))
ck('C2 分布与表头一致 63/243/213/119',
   dict(dist) == {'P0':63,'P1':243,'P2':213,'P3':119}, str(dict(dist)))

print('\nC3 所属类别枚举')
cats = collections.Counter(r['所属类别'] for r in rows)
ws11 = wb['11类']
decl = [ws11.cell(row=i, column=1).value for i in range(2, ws11.max_row + 1)]
decl = [x.strip() for x in decl if x and str(x).strip()]
ck('C3 11类sheet 声明 12 项（11 类 + 未归类）', len(decl) == 12, f'声明 {len(decl)}：{decl}')
ck('C3 表内类别 ⊂ 声明集合', set(cats) <= set(decl), f'越界：{set(cats)-set(decl)}')
ck('C3 表内类别 11 个（未归类 0 条）', len(cats) == 11, f'{len(cats)} 个')
ck('C3 每类都有含义', all(str(ws11.cell(row=i, column=2).value or '').strip() for i in range(2, ws11.max_row + 1)))

print('\nC4 子类→类别 一对一')
m = collections.defaultdict(set)
for r in rows: m[r['所属子类']].add(r['所属类别'])
multi = {k: v for k, v in m.items() if len(v) > 1}
ck('C4 无子类挂在多个类别', not multi, str(list(multi)[:3]))
ck('C4 子类数 58（另有 1 个 0 条占位「（暂无命中）」只在占比 sheet）', len(m) == 58, f'{len(m)}')

print('\nC9 与「规则占比」sheet 一致')
wsr = wb['规则占比']
ratio = {}
for i in range(2, wsr.max_row + 1):
    c, s, n = (wsr.cell(row=i, column=j).value for j in (1, 2, 3))
    if c: ratio[(c, s)] = n
mine = collections.Counter((r['所属类别'], r['所属子类']) for r in rows)
placeholder = {('未归类', '（暂无命中）')}
ck('C9 占比 sheet ⊇ 表（唯一例外是 0 条占位行）',
   set(mine) <= set(ratio) and (set(ratio) - set(mine)) <= placeholder,
   f'仅表 {len(set(mine)-set(ratio))} 仅占比 {sorted(set(ratio)-set(mine))}')
ck('C9 每个组合条数一致', all(ratio[k] == mine[k] for k in set(ratio) & set(mine)),
   str([(k, ratio[k], mine[k]) for k in set(ratio) & set(mine) if ratio[k] != mine[k]][:3]))
ck('C9 占比 sheet 合计 638（占位行 0 条）', sum(ratio.values()) == sum(mine.values()) == 638, f'{sum(ratio.values())}')

print('\nC6 P0 快路 17 条')
p0pat = {json.loads(l)['rule_id'] for l in open(os.path.join(KB, 'kb/l5/p0_patterns.jsonl'), encoding='utf-8') if l.strip()}
fast = {r['规则ID(rule_id)'] for r in rows if str(r['可否被 P0 拦截']).startswith('✅')}
ck('C6 可拦截 17 条', len(fast) == 17, f'{len(fast)}')
ck('C6 与 p0_patterns 的 rule_id 完全一致', fast == p0pat, f'差 {len(fast ^ p0pat)}')
ck('C6 17 条全部标 P0', all(r['优先级'] == 'P0' for r in rows if r['规则ID(rule_id)'] in p0pat))
ck('C6 P0 里非快路 46 条', sum(1 for r in rows if r['优先级']=='P0') - len(fast) == 46)

print('\nC7 W-2.350 保持原值')
w = [r for r in rows if r['条款号'] == 'W-2.350']
if w:
    w = w[0]
    ck('C7 表值 == KB 原值', w['优先级'] == kb[w['规则ID(rule_id)']]['p_level'],
       f"表 {w['优先级']} / 库 {kb[w['规则ID(rule_id)']]['p_level']}")
else:
    ck('C7 找到 W-2.350', False, '表内无此条款号')

print('\nC8 rule_id 一一对应')
tids = {r['规则ID(rule_id)'] for r in rows}
ck('C8 集合相等', tids == set(kb), f'表独有 {len(tids-set(kb))} 库独有 {len(set(kb)-tids)}')

print(f'\n合计：通过 {ok} ｜ 不通过 {fail}')
sys.exit(0 if fail == 0 else 1)
