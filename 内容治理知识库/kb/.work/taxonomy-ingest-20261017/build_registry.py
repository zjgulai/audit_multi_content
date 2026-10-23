#!/usr/bin/env python3
"""把桌面规则清单的 3 个治理字段落成 **持久注册表** kb/l3/registry/rule-taxonomy.json。

为什么要注册表而不是直接写规则行：
  `kb/l3/candidates/rules.jsonl` 是**上游重建的派生件**（`kb/l8/l3_distill_run.py` 覆盖写），
  `external_standard.jsonl` 同理（`kb/l8/l3_clause_distill.py` 重蒸某个资源时重建那些行）。
  往它们身上写人工口径，下一次重建就没了。⇒ 人工口径的**真源**放注册表，
  重建时由 `kb/l3/kb_rule_dimensions.py::apply_taxonomy()` 盖回规则行。

只读 Excel 与 KB；本脚本写 registry（--apply 才写）。
"""
import json, os, sys, hashlib, collections, argparse
from openpyxl import load_workbook

KB = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
XLSX = os.path.expanduser('~/Desktop/规则清单-P0-P3-按等级-20261016.xlsx')
OUT = os.path.join(KB, 'kb/l3/registry/rule-taxonomy.json')
CREATED = '2026-10-17'
TAXONOMY_VERSION = 'v1-20261017'


def sha256_file(p):
    h = hashlib.sha256()
    with open(p, 'rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def load_excel():
    wb = load_workbook(XLSX, data_only=True)
    ws = wb['全部规则 (P0-P3)']
    hdr = [ws.cell(row=5, column=c).value for c in range(1, 44)]
    rows = []
    for r in range(6, ws.max_row + 1):
        v = [ws.cell(row=r, column=c).value for c in range(1, 44)]
        if all(x is None for x in v):
            continue
        rows.append(dict(zip(hdr, v)))
    ws11 = wb['11类']
    classes = []
    for i in range(2, ws11.max_row + 1):
        name = ws11.cell(row=i, column=1).value
        mean = ws11.cell(row=i, column=2).value
        if name and str(name).strip():
            classes.append({'name': str(name).strip(), 'meaning': (str(mean).strip() if mean else '')})
    return rows, classes


def load_kb():
    kb = {}
    for p, src in (('kb/l3/candidates/rules.jsonl', 'rules'),
                   ('kb/l3/candidates/external_standard.jsonl', 'external_standard')):
        for line in open(os.path.join(KB, p), encoding='utf-8'):
            if not line.strip():
                continue
            r = json.loads(line)
            if src == 'external_standard' or r.get('article_no'):
                kb[r['rule_id']] = dict(r, _src=src)
    return kb


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true')
    a = ap.parse_args()
    rows, classes = load_excel()
    kb = load_kb()
    p0_patterns = {json.loads(l)['rule_id']: json.loads(l).get('article_no')
                   for l in open(os.path.join(KB, 'kb/l5/p0_patterns.jsonl'), encoding='utf-8') if l.strip()}

    rules, sub2cat = [], {}
    for r in rows:
        rid = r['规则ID(rule_id)']
        k = kb[rid]
        cat, sub, plevel = r['所属类别'].strip(), r['所属子类'].strip(), r['优先级'].strip()
        sub2cat.setdefault(sub, set()).add(cat)
        rules.append({
            'rule_id': rid,
            'article_no': r['条款号'],
            'source': r['来源候选件'],
            'category': cat,
            'subcategory': sub,
            'p_level': plevel,
            'p_level_before': k.get('p_level'),     # 入库前的库内值（回滚/审计用）
            'p0_fastpath': rid in p0_patterns,       # 是否在 kb/l5/p0_patterns.jsonl 里
        })
    rules.sort(key=lambda x: (x['source'], x['article_no']))

    cls_counts = collections.Counter(x['category'] for x in rules)
    sub_counts = collections.Counter((x['category'], x['subcategory']) for x in rules)
    plevel_counts = collections.Counter(x['p_level'] for x in rules)

    reg = {
        'taxonomy_id': 'rule-taxonomy-' + TAXONOMY_VERSION,
        'taxonomy_version': TAXONOMY_VERSION,
        'created_at': CREATED,
        'layer': 'L3 规则层 · 规则归类与优先级（人工口径）',
        'status': 'active',
        'owner': '刘华丽',
        'approved_by': 'Owner（内容治理）',
        'what_it_is': (
            '把「所属类别 / 所属子类 / 优先级」三格落成**人工口径的注册表**，'
            '并声明它们在规则行上的字段名：`taxonomy_category` / `taxonomy_subcategory` / `p_level`。'
        ),
        'why_registry_not_rule_rows': (
            '`kb/l3/candidates/rules.jsonl` 与 `external_standard.jsonl` 都是**上游重建的派生件**'
            '（`kb/l8/l3_distill_run.py` / `kb/l8/l3_clause_distill.py` 会重建行）。'
            '人工口径写进派生件 ⇒ 下一次重建必然消失。⇒ 真源放本注册表，'
            '重建时由 `kb/l3/kb_rule_dimensions.py::apply_taxonomy()` 盖回规则行。'
        ),
        'source': {
            'file': XLSX,
            'sheet': '全部规则 (P0-P3)',
            'sha256': sha256_file(XLSX),
            'exported_at': '2026-10-16 21:05（原始导出）+ 2026-10-17 按类别/子类重标',
            'owner_statement': '规则从 DSH 知识库提取；所属类别 / 所属子类 / 优先级三格由 Owner 优化（重标）',
            'rows': len(rules),
            'by_source': dict(collections.Counter(x['source'] for x in rules)),
        },
        'classes': classes,
        'subclass_to_category': {k: sorted(v)[0] for k, v in sorted(sub2cat.items())},
        'class_counts': dict(cls_counts),
        'subclass_counts': {f'{c} / {s}': n for (c, s), n in sorted(sub_counts.items())},
        'p_level_counts': dict(plevel_counts),
        'p0_policy': {
            'p0_rules': plevel_counts.get('P0', 0),
            'p0_fastpath_rules': len(p0_patterns),
            'rule': (
                '★ `p_level=P0` 与「进 P0 快路」**不是同一件事**：'
                '快路集合 = `kb/l5/p0_patterns.jsonl`（现 17 条，法务签字台账 `kb/l5/registry/p0-legal-signoff-ledger.json`）；'
                '`p_level=P0` 是本表口径的优先级档（63 条）。'
                '表里这 17 条一律锁 P0（表跟随引擎），其余 46 条 P0 由评审链**规则层**命中并判 BLOCK，'
                '不走 ≤1s 快路、依据标「不可逐字回源」。'
            ),
            'locked_to_engine': sorted(x['article_no'] for x in rules if x['p0_fastpath']),
            'warning': (
                '`kb/.work/l5_export.py` 的 P0 选取口径是 `p_level == "P0"` ⇒ 本注册表落库后，'
                '若有人再跑 `l5_export.py --apply`，可导出条数会从 17 **变成 19**'
                '（多出 W-1.49 / W-1.5）。已在该文件加 fail-closed 守卫：'
                '导出集合与现表不等时必须显式 `--accept-p0-expansion`，否则拒写。'
            ),
        },
        'exceptions': [
            {
                'rule_id': next((x['rule_id'] for x in rules if x['article_no'] == 'W-2.350'), None),
                'article_no': 'W-2.350',
                'what': '源字段「修订类型」缺失 ⇒ **不猜**，优先级保持库内原值。',
                'p_level': next((x['p_level'] for x in rules if x['article_no'] == 'W-2.350'), None),
            }
        ],
        'field_names': {
            'taxonomy_category': '所属类别（11 类 + 未归类兜底；枚举见 classes）',
            'taxonomy_subcategory': '所属子类（58 个实有 + 1 个占位「（暂无命中）」）',
            'p_level': '优先级 P0–P3（PRD §6.2 四层；**覆盖原值**，原值见每条 p_level_before）',
        },
        'applied_by': 'kb/l3/kb_rule_dimensions.py::apply_taxonomy()（唯一实现）',
        'rebuild_wiring': [
            'kb/l8/l3_distill_run.py（措辞库 rules.jsonl 写盘前）',
            'kb/l8/l3_clause_distill.py（外部标准 external_standard.jsonl 写盘前）',
        ],
        'rollback': {
            'how': '每条 `p_level_before` 即入库前的库内值；把本注册表 status 置 "rolled_back" 后重跑 apply_taxonomy(mode="restore")，或直接按 p_level_before 回写。',
            'backup_dir': 'kb/l3/_backups/rule-taxonomy-20261017/',
        },
        'boundary': [
            '★ 本表只给「归类 + 优先级」两件事，**不动**规则正文 / 证据 / 条款号（逐条已核 0 处差异）。',
            '★ `risk_level`（PRD §6.5 风险等级）是**另一个轴**，本件不碰；不许由 `p_level` 推导它。',
            '★ 11 类体系是**第三套类目**（前两套：`l7.json.vocabulary.categories` 规则词表、'
            '`l4/canonical/sample_case.reason_category` 反例类目），与 PRD §5.3 四维（`risk-category-policy.json`）的映射**尚未裁**。',
        ],
        'rules': rules,
    }
    text = json.dumps(reg, ensure_ascii=False, indent=1) + '\n'
    print(f'注册表：{len(rules)} 条 ｜ 类别 {len(cls_counts)} 个 ｜ 子类 {len(sub2cat)} 个 ｜ '
          f'优先级 {dict(plevel_counts)} ｜ 快路 {len(p0_patterns)} 条')
    print(f'源 sha256：{reg["source"]["sha256"]}')
    print(f'目标：{os.path.relpath(OUT, KB)}  ({len(text)} 字节)')
    if not a.apply:
        print('[dry-run] 未写。加 --apply 落盘。')
        return 0
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    tmp = OUT + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as fh:
        fh.write(text)
    os.replace(tmp, OUT)
    back = json.load(open(OUT, encoding='utf-8'))
    assert len(back['rules']) == len(rules) and back['source']['sha256'] == reg['source']['sha256']
    print(f'✅ 已写并回读校验：{os.path.relpath(OUT, KB)}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
