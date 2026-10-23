#!/usr/bin/env python3
"""把注册表的三格一次性盖到规则行上（措辞库 rules.jsonl ＋ 外部标准 external_standard.jsonl）。

纪律：
1. 先 dry-run：重算 diff（哪一行、哪个字段、从什么改成什么），并验证「不改时逐字节可复原」；
2. --apply 才写；写前把两份候选件逐字节备份到 kb/l3/_backups/rule-taxonomy-20261017/；
3. 原子写 + 写完逐条回读比对（638 条三格全等 + 其它字段一个字节不变）。
"""
import json, os, sys, hashlib, collections, argparse, shutil

KB = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(KB, 'kb', 'l3'))
import kb_rule_dimensions as dim

TAX = os.path.join(KB, 'kb/l3/registry/rule-taxonomy.json')
TARGETS = [('kb/l3/candidates/rules.jsonl', 'rules'),
           ('kb/l3/candidates/external_standard.jsonl', 'external_standard')]
BACKUP = os.path.join(KB, 'kb/l3/_backups/rule-taxonomy-20261017')
FIELDS = ('taxonomy_category', 'taxonomy_subcategory', 'p_level')


def sha(b):
    return hashlib.sha256(b).hexdigest()


def read_rows(p):
    return [json.loads(l) for l in open(os.path.join(KB, p), encoding='utf-8') if l.strip()]


def serialize(rows):
    return ''.join(json.dumps(r, ensure_ascii=False, sort_keys=True) + '\n' for r in rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true')
    a = ap.parse_args()
    tax = dim.load_taxonomy(TAX)
    print(f'注册表 {tax["version"]} ｜ {len(tax["by_rule"])} 条 ｜ owner={tax.get("owner")}')

    plan = {}
    for rel, src in TARGETS:
        raw = open(os.path.join(KB, rel), 'rb').read()
        rows = read_rows(rel)
        roundtrip = serialize(rows)
        same = (roundtrip.encode('utf-8') == raw)
        print(f'\n── {rel} ── {len(rows)} 行 ｜ 未改内容重序列化后逐字节一致：{same}')
        assert same, '序列化口径与盘上不一致 ⇒ 会制造无意义 diff，先查 sort_keys/换行'
        before = {r['rule_id']: {k: r.get(k) for k in FIELDS} for r in rows}
        st = dim.apply_taxonomy(rows, tax, mode='force')
        print(f'   盖 {st["matched"]} 条 / 表外 {st["unmatched"]} ｜ 字段改动 {st["stamped"]} 处 ｜ '
              f'p_level 变更 {st["p_level_changed"]} 条 ｜ 冲突 {len(st["conflicts"])}')
        # 逐条 diff：只允许这三格 + taxonomy_basis 变
        diffs = []
        for r in rows:
            b = before[r['rule_id']]
            for k in FIELDS:
                if b[k] != r.get(k):
                    diffs.append((r['rule_id'], r.get('article_no'), k, b[k], r.get(k)))
        allowed = set(FIELDS) | {'taxonomy_basis'}
        for r_old, r_new in zip(read_rows(rel), rows):
            extra = (set(r_new) - set(r_old)) - allowed
            assert not extra, f'越界字段：{extra}'
            changed = {k for k in r_old if r_old[k] != r_new.get(k)} - allowed
            assert not changed, f'越界改写：{changed}'
        print(f'   越界改动：0（除三格 + taxonomy_basis 外，逐行逐字段一个都没变）')
        by_field = collections.Counter(d[2] for d in diffs)
        print(f'   改动分布：{dict(by_field)}')
        plan[rel] = (raw, serialize(rows), diffs, st)

    total = sum(len(v[2]) for v in plan.values())
    print(f'\n合计改动 {total} 处（638 条规则的三格）')
    if not a.apply:
        print('[dry-run] 未写。加 --apply 落盘。')
        return 0

    os.makedirs(BACKUP, exist_ok=True)
    for rel, (raw, text, diffs, st) in plan.items():
        base = os.path.basename(rel)
        dst = os.path.join(BACKUP, base)
        open(dst, 'wb').write(raw)
        assert sha(open(dst, 'rb').read()) == sha(raw), '备份校验失败'
        print(f'[备份] {os.path.relpath(dst, KB)}  sha256={sha(raw)[:16]}')
        tmp = os.path.join(KB, rel) + '.tmp'
        open(tmp, 'w', encoding='utf-8').write(text)
        os.replace(tmp, os.path.join(KB, rel))
        back = open(os.path.join(KB, rel), 'rb').read()
        assert back.decode('utf-8') == text, '回读不一致'
        print(f'[写入] {rel}  sha256={sha(back)[:16]}  {len(back)} 字节')

    # ── 回读校验：638 条三格与注册表逐条全等；其它字段与备份逐条全等
    print('\n── 回读校验 ──')
    ok = bad = 0
    for rel, src in TARGETS:
        now = read_rows(rel)
        old = [json.loads(l) for l in open(os.path.join(BACKUP, os.path.basename(rel)), encoding='utf-8') if l.strip()]
        for r_now, r_old in zip(now, old):
            assert r_now['rule_id'] == r_old['rule_id']
            for k in r_old:
                if k in FIELDS:
                    continue
                if r_now.get(k) != r_old[k]:
                    bad += 1
                    print('  ✗ 非三格字段被改：', r_now['rule_id'], k)
            t = tax['by_rule'][r_now['rule_id']]
            if (r_now.get('taxonomy_category') == t['category']
                    and r_now.get('taxonomy_subcategory') == t['subcategory']
                    and r_now.get('p_level') == t['p_level']):
                ok += 1
            else:
                bad += 1
                print('  ✗ 三格不符：', r_now['rule_id'])
    print(f'  三格逐条全等 {ok}/{ok + bad} ｜ 异常 {bad}')
    cnt = collections.Counter(r['p_level'] for rel, _ in TARGETS for r in read_rows(rel) if tax['by_rule'].get(r['rule_id']))
    print(f'  按规则去重后的 p_level 分布：{dict(cnt)}')
    return 0 if bad == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
