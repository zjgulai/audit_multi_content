#!/usr/bin/env python3
"""重建尾部 reverse test（不写任何文件）：
L3 重建器在写盘前会依次跑 apply_dimensions() → apply_taxonomy()。
本件用**入库前的备份行**（只有旧 p_level、没有三格）模拟那一步，验证：
  ① 重建后三格必须被注册表**复原**（人工口径不丢）；
  ② `apply_taxonomy` 不许改 `risk_level`（另一轴）；
  ③ **反证顺序**：把两步对调（先盖 p_level 再算维度）⇒ 那 63 条 P0 会被 P0 地板抬到 Critical
     ⇒ 说明「必须排在 apply_dimensions 之后」不是风格问题，是防一类真实改写。
"""
import json, os, sys, collections
KB = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(KB, 'kb', 'l3'))
import kb_rule_dimensions as dim

BK = os.path.join(KB, 'kb/l3/_backups/rule-taxonomy-20261017/rules.jsonl')
FIELDS = ('taxonomy_category', 'taxonomy_subcategory', 'p_level')


def load(bk):
    rows = {}
    for l in open(bk, encoding='utf-8'):
        if l.strip():
            r = json.loads(l)
            rows[r['rule_id']] = r          # last-wins，与引擎/重建口径一致
    return list(rows.values())


def main():
    ok = fail = 0
    def ck(n, c, d=''):
        nonlocal ok, fail
        if c: ok += 1; print(f'  ✅ {n} {d}')
        else: fail += 1; print(f'  ❌ {n} {d}')

    tax = dim.load_taxonomy()
    idx = dim.build_l0_index()
    base = load(BK)
    print(f'入库前备份：{len(base)} 条规则')

    # ① 正路：dimensions → taxonomy
    a = [dict(r) for r in base]
    dim.apply_dimensions(a, dim.l0_lookup(idx), mode='force')
    rl_after_dim = {r['rule_id']: r['risk_level'] for r in a}
    st = dim.apply_taxonomy(a, tax, mode='force')
    bad = [r['rule_id'] for r in a
           if (r['taxonomy_category'], r['taxonomy_subcategory'], r['p_level'])
           != (tax['by_rule'][r['rule_id']]['category'],
               tax['by_rule'][r['rule_id']]['subcategory'],
               tax['by_rule'][r['rule_id']]['p_level'])]
    ck('① 重建后三格被注册表复原', not bad, f'不符 {len(bad)} ｜ 盖 {st["matched"]} 条')
    ck('② apply_taxonomy 不改 risk_level',
       all(r['risk_level'] == rl_after_dim[r['rule_id']] for r in a), '')

    # ③ 反证：顺序对调
    b = [dict(r) for r in base]
    dim.apply_taxonomy(b, tax, mode='force')
    dim.apply_dimensions(b, dim.l0_lookup(idx), mode='force')
    # 反证判据：出现了「被 P0 地板提到 Critical」的条数；且比正路多
    up = sum(1 for r in b
             if r['risk_level'] == 'Critical' and rl_after_dim[r['rule_id']] != 'Critical')
    ck('③ 顺序对调会顺带抬高 risk_level（所以必须排在 dimensions 之后）',
       up > 0, f'对调后多提了 {up} 条到 Critical')

    print(f'合计：通过 {ok} ｜ 不通过 {fail}')
    return 0 if fail == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
