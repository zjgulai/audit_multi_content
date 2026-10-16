#!/usr/bin/env python3
"""旧版 vs 新版审查报告，**逐行**比对（按内容 ID 对齐，不靠顺序）。

为什么另写一份（`cmp_reports.py` 只管那 10 条、且按**文件名顺序** zip 对齐）：
顺序对齐漏一行就整段错位，而这次要比 80 行、且新旧两侧都可能缺件。

核的六件事（都是「能不能对外交代」这一层）：
  ① 三态翻转（谁从 A 变成 B）
  ② 声明问题数变化
  ③ 依据层：库内条款依据 / 外部标准 / 无库内依据 的条数
  ④ 库内条款号集合变化（L4 溯源那一段）
  ⑤ 「同源·同题材引证」那条可疑依据出现次数（题材闸门要挡的就是它）
  ⑥ P0 快路有无

用法：python3 cmp_reports80.py [--md out/cmp80.md]
"""
import argparse, glob, html, json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'out')


def text_of(path):
    d = json.load(open(path, encoding='utf-8'))
    c = (d.get('data') or {}).get('document', {}).get('content') or ''
    t = re.sub(r'<br\s*/?>', '\n', c)
    t = re.sub(r'</(p|li|h[1-6]|td|tr)>', '\n', t)
    return html.unescape(re.sub(r'<[^>]+>', '', t))


def feats(t):
    f = {}
    m = re.search(r'【审查结论：(\w+)】', t)
    f['state'] = m.group(1) if m else '—'
    m = re.search(r'共发现\s*(\d+)\s*处', t) or re.search(r'问题数量[：:]\s*\**(\d+)', t)
    f['count'] = int(m.group(1)) if m else None
    f['cats'] = sorted(set(re.findall(r'【([^】]{2,12})】\s*(?:全文|素材正文|text)', t)))
    f['articles'] = sorted(set(re.findall(r'\b([SW]-1\.\d+)\b', t)))
    f['p0codes'] = sorted(set(re.findall(r'\b([HMU]\d{2})\b', t)))
    f['n_lib'] = len(re.findall(r'有库内条款依据', t))
    f['n_ext'] = len(re.findall(r'外部标准|support\.google|advertising\.amazon|fda\.gov', t))
    f['n_nolib'] = len(re.findall(r'无库内依据|需人工确认（本条无库内依据）', t))
    f['same_src'] = len(re.findall(r'同源/同题材引证', t))
    f['p0fast'] = bool(re.search(r'P0 快路', t))
    return f


def load(dirname):
    d = {}
    for p in sorted(glob.glob(os.path.join(OUT, dirname, '*.json'))):
        d[os.path.basename(p)[:-5]] = p
    return d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--md', default=os.path.join(OUT, 'cmp80.md'))
    a = ap.parse_args()

    old, new = load('reports_old'), load('reports_new')
    ids = sorted(set(old) | set(new))
    only_old = sorted(set(old) - set(new))
    only_new = sorted(set(new) - set(old))

    rows, flips = [], []
    for cid in ids:
        fo = feats(text_of(old[cid])) if cid in old else None
        fn = feats(text_of(new[cid])) if cid in new else None
        rows.append((cid, fo, fn))
        if fo and fn and fo['state'] != fn['state']:
            flips.append((cid, fo['state'], fn['state'], fo['count'], fn['count']))

    L = []
    add = L.append
    add('# 80 行审查报告：旧版 vs 10/14 重跑版（逐行）\n')
    add(f'- 旧版（`报告链接`）拿到 {len(old)} 份 ｜ 新版（`10/14重跑报告链接`）拿到 {len(new)} 份 ｜ 并集 {len(ids)} 行')
    if only_old:
        add(f'- ⚠️ **只有旧版、没有新版** {len(only_old)} 行：{"、".join(only_old[:8])}')
    if only_new:
        add(f'- ⚠️ **只有新版、没有旧版** {len(only_new)} 行：{"、".join(only_new[:8])}')
    add('')

    add('## ① 三态翻转\n')
    if not flips:
        add('**没有一行三态发生变化。**\n')
    else:
        add(f'**{len(flips)} 行三态变了：**\n')
        add('| 内容 ID | 旧 | 新 | 旧问题数 | 新问题数 |')
        add('|---|---|---|---|---|')
        for cid, so, sn, co, cn in flips:
            add(f'| `{cid}` | {so} | {sn} | {co if co is not None else "—"} | {cn if cn is not None else "—"} |')
        add('')

    def tally(k):
        o = sum((r[1] or {}).get(k, 0) for r in rows)
        n = sum((r[2] or {}).get(k, 0) for r in rows)
        return o, n

    add('## ② 总量（80 行合计）\n')
    add('| 维度 | 旧版 | 新版 | 差 |')
    add('|---|---|---|---|')
    for k, name in [('n_lib', '「有库内条款依据」出现次数'), ('n_ext', '「外部标准」出现次数'),
                    ('n_nolib', '「无库内依据」出现次数'), ('same_src', '「同源/同题材引证」出现次数')]:
        o, n = tally(k)
        add(f'| {name} | {o} | {n} | {n - o:+d} |')
    add(f'| P0 快路行数 | {sum(1 for r in rows if (r[1] or {}).get("p0fast"))} '
        f'| {sum(1 for r in rows if (r[2] or {}).get("p0fast"))} '
        f'| {sum(1 for r in rows if (r[2] or {}).get("p0fast")) - sum(1 for r in rows if (r[1] or {}).get("p0fast")):+d} |')
    add('')

    add('## ③ 逐行明细\n')
    add('| 内容 ID | 三态 旧→新 | 问题数 旧→新 | 库内依据 旧→新 | 外部标准 旧→新 | 同源引证 旧→新 | P0快路 |')
    add('|---|---|---|---|---|---|---|')
    for cid, fo, fn in rows:
        def g(f, k, d='—'):
            return d if not f else (f[k] if f[k] is not None else '—')
        add(f'| `{cid}` | {g(fo,"state")} → {g(fn,"state")} | {g(fo,"count")} → {g(fn,"count")} '
            f'| {g(fo,"n_lib",0)} → {g(fn,"n_lib",0)} | {g(fo,"n_ext",0)} → {g(fn,"n_ext",0)} '
            f'| {g(fo,"same_src",0)} → {g(fn,"same_src",0)} | {"是" if (fn or {}).get("p0fast") else "否"} |')
    add('')

    add('## ④ 条款号 / P0 规则码变了哪些行\n')
    n = 0
    for cid, fo, fn in rows:
        if not (fo and fn):
            continue
        if fo['articles'] != fn['articles'] or fo['p0codes'] != fn['p0codes']:
            n += 1
            add(f'- `{cid}`：条款 {fo["articles"] or "—"} → {fn["articles"] or "—"}；'
                f'规则码 {fo["p0codes"] or "—"} → {fn["p0codes"] or "—"}')
    if not n:
        add('（一行都没变）')
    add('')

    # ★ `.md` 必须走非中招通道：python 直写 `.md` 会让 **DSH 宿主**读到 +4096 字节
    #   （盘上是真值，受害的是宿主侧的读者 —— 本仓为此返工过一次）。
    sys.path.insert(0, os.path.join(HERE, '..', 'kb', '.work'))
    try:
        from _safe_write import write_text  # noqa
        write_text(a.md, '\n'.join(L))
    except Exception as e:                                   # pragma: no cover
        open(a.md, 'w', encoding='utf-8').write('\n'.join(L))
        print(f'⚠️ _safe_write 不可用（{e}）—— 已直写，`.md` 可能带信封，请用 node 复核')

    print(f'旧 {len(old)} ｜ 新 {len(new)} ｜ 三态翻转 {len(flips)} 行 ｜ 报告 {a.md}')
    for cid, so, sn, co, cn in flips:
        print(f'  {cid}: {so} → {sn}（问题数 {co} → {cn}）')


if __name__ == '__main__':
    main()
