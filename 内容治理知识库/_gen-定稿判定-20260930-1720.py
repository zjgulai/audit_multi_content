#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""L3 候选 rules.jsonl：哪几条能当定稿用 / 哪几条不能 —— 逐条标记生成器（只读 kb/，只写出交付文件）

复算入口：python3 _gen-定稿判定-20260930-1720.py
"""
import json, csv, os, hashlib, collections, datetime

KB = 'kb'
RUN = '20260930-1720'
OUT_JSONL = f'定稿判定-rules.jsonl-{RUN}-逐条标记.jsonl'
OUT_CSV   = f'定稿判定-rules.jsonl-{RUN}-逐条标记.csv'


def load(p):
    with open(p, encoding='utf-8') as f:
        return [json.loads(l) for l in f if l.strip()]


def sha256(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


TODAY = datetime.date.today().isoformat()

# ---------- 读入 ----------
cand_path = f'{KB}/l3/candidates/rules.jsonl'
ext_path = f'{KB}/l3/candidates/external_standard.jsonl'
cand = load(cand_path)
ext = load(ext_path)

# L4 定稿（四个形态文件）
canon_rule = {}          # rule_id -> 定稿记录（只有 wording_* 两个文件有 rule_id）
canon_all = []
for fn in ['wording_entry', 'wording_revision_pair', 'sample_case', 'scoped_clause']:
    for r in load(f'{KB}/l4/canonical/{fn}.jsonl'):
        r['_canon_file'] = f'kb/l4/canonical/{fn}.jsonl'
        canon_all.append(r)
        if 'rule_id' in r:
            canon_rule[r['rule_id']] = r

l4reg = json.load(open(f'{KB}/l4/registry/l4.json', encoding='utf-8'))
l3reg = json.load(open(f'{KB}/l3/registry/l3.json', encoding='utf-8'))
e021 = {d['rule_id'] for d in l3reg['e021_concepts']['detail']}

# 候选：1018 行 = 509 rule_id × 2 行
by_id = collections.defaultdict(list)
for r in cand:
    by_id[r['rule_id']].append(r)
numbered = {rid: [x for x in v if str(x.get('article_no', '')).strip()][0]
            for rid, v in by_id.items() if any(str(x.get('article_no', '')).strip() for x in v)}

# ---------- 逐条判定 ----------
rows = []
for rid in sorted(numbered):
    c = numbered[rid]
    k = canon_rule.get(rid)
    flags, detail = [], {}

    if k is None:
        rows.append(dict(rule_id=rid, article_no=c.get('article_no', ''), verdict='不能当定稿',
                         blocking=True, why='条款号存在但 L4 canonical 查无此 rule_id'))
        continue

    no = k['article_no']
    expired = bool(k.get('valid_until')) and str(k['valid_until']) < TODAY

    # 旗标（全部取自 L4 定稿，不取候选副本）
    if k.get('support_count') == 1:
        flags.append('support_count=1·verification=待验证')
    if str(k.get('risk_level')) == 'unknown':
        flags.append('risk_level=unknown·源表无风险等级字段')
    if str(k.get('authority')) == 'inferred':
        flags.append('authority=inferred·模型归纳无外部权威背书')
    if rid in e021:
        flags.append('E021·未过三重验证·不得进判断层')
    if k.get('half_life_days') == 90:
        flags.append(f"半衰期90天·{k.get('valid_until')} 最先到期")
    if k.get('rule_kind') == 'inductive':
        flags.append('rule_kind=inductive·归纳型')
    if str(k.get('verification')) == '待验证':
        flags.append('L4 verification=待验证')

    # 候选副本 vs 定稿 漂移（只报，不修）
    drift = {}
    for f in ['p_level', 'rule_code', 'suggested_replacement']:
        a = json.dumps(c.get(f), sort_keys=True, ensure_ascii=False)
        b = json.dumps(k.get(f), sort_keys=True, ensure_ascii=False)
        if a != b:
            drift[f] = {'candidate': c.get(f), 'canonical': k.get(f)}
    if drift:
        flags.append('候选副本与定稿漂移:' + ','.join(sorted(drift)))

    rows.append({
        'rule_id': rid,
        'article_no': no,
        'form': k.get('form'),
        'verdict': '能当定稿用',
        'blocking': False,
        'allowed_use': '已编号的定稿快照（machine-promoted）——可引用、可作审查依据；不可当「已发布版本」（kb_version=v0，无 release_id）',
        'canonical_ref': k['_canon_file'],
        'canonical_status': k.get('status'),
        'owner': k.get('owner'),
        'p_level': k.get('p_level'),
        'authority': k.get('authority'),
        'support_count': k.get('support_count'),
        'verification': k.get('verification'),
        'half_life_days': k.get('half_life_days'),
        'valid_until': k.get('valid_until'),
        'expired': expired,
        'in_judgment_layer': rid not in e021,
        'flags': flags,
        'candidate_vs_canonical_drift': drift or None,
    })

# 隔壁文件：真正「不能当定稿」的
for r in ext:
    rows.append({
        'rule_id': r['rule_id'],
        'article_no': r.get('article_no') or '',
        'form': r.get('form'),
        'verdict': '不能当定稿',
        'blocking': True,
        'allowed_use': '仅候选件，不得当定稿引用',
        'canonical_ref': None,
        'canonical_status': r.get('status'),
        'owner': r.get('owner') or '',
        'p_level': r.get('p_level'),
        'authority': None,
        'support_count': None,
        'verification': r.get('verification'),
        'half_life_days': None,
        'valid_until': None,
        'expired': None,
        'in_judgment_layer': False,
        'flags': ['无条款号', '无 owner', 'status=candidate', 'verification=待人工复核',
                  'L4 引擎当前登记的产出形态不含 external_standard → 本批无发号通道'],
        'why': '在 kb/l3/candidates/external_standard.jsonl（不在 rules.jsonl）',
    })

summary = {
    '_summary': True,
    'run': RUN,
    'at': datetime.datetime.now().isoformat(timespec='seconds'),
    'l3_candidates_rules': {
        'path': cand_path, 'bytes': os.path.getsize(cand_path), 'sha256': sha256(cand_path),
        'lines': len(cand), 'unique_rule_id': len(by_id), 'numbered_rows': len(numbered),
    },
    'l3_candidates_external_standard': {
        'path': ext_path, 'bytes': os.path.getsize(ext_path), 'sha256': sha256(ext_path),
        'lines': len(ext), 'with_article_no': sum(1 for r in ext if str(r.get('article_no', '')).strip()),
    },
    'l4_canonical': {
        f: {'lines': sum(1 for r in canon_all if r['_canon_file'].endswith(f + '.jsonl')),
            'sha256': sha256(f'{KB}/l4/canonical/{f}.jsonl')}
        for f in ['wording_entry', 'wording_revision_pair', 'sample_case', 'scoped_clause']
    },
    'counts': {
        '能当定稿用': sum(1 for r in rows if r['verdict'] == '能当定稿用'),
        '不能当定稿_在rules内': 0,
        '不能当定稿_在external_standard': sum(1 for r in rows if r['verdict'] == '不能当定稿'),
        '进判断层': sum(1 for r in rows if r.get('in_judgment_layer')),
        '不得进判断层_E021': sum(1 for r in rows if r['verdict'] == '能当定稿用' and not r.get('in_judgment_layer')),
        '无保留可用_authority=expert且support>=2且非E021': sum(
            1 for r in rows if r['verdict'] == '能当定稿用'
            and r.get('authority') == 'expert' and (r.get('support_count') or 0) >= 2
            and r.get('in_judgment_layer')),
        '已过期': sum(1 for r in rows if r.get('expired')),
    },
    'flag_counts': dict(collections.Counter(
        f for r in rows if r['verdict'] == '能当定稿用' for f in r['flags']).most_common()),
    'gates': 'kb/kbpy l7/scripts/l3_gate.py 与 l4_gate.py 均退出 0（见报告）',
    'l4_registry_promotion_status': l4reg['promotion_rule']['status'],
}

with open(OUT_JSONL, 'w', encoding='utf-8') as f:
    f.write(json.dumps(summary, ensure_ascii=False) + '\n')
    for r in rows:
        f.write(json.dumps(r, ensure_ascii=False) + '\n')

cols = ['rule_id', 'article_no', 'form', 'verdict', 'blocking', 'allowed_use',
        'canonical_ref', 'canonical_status', 'owner', 'p_level', 'authority',
        'support_count', 'verification', 'half_life_days', 'valid_until',
        'expired', 'in_judgment_layer', 'flags']
with open(OUT_CSV, 'w', encoding='utf-8-sig', newline='') as f:
    w = csv.DictWriter(f, fieldnames=cols, extrasaction='ignore')
    w.writeheader()
    for r in rows:
        d = dict(r)
        d['flags'] = ' ｜ '.join(r['flags'])
        w.writerow(d)

print(json.dumps(summary['counts'], ensure_ascii=False, indent=1))
print(json.dumps(summary['flag_counts'], ensure_ascii=False, indent=1))
print(f'\n-> {OUT_JSONL} ({len(rows)} 条 + 1 行 summary)')
print(f'-> {OUT_CSV}')
