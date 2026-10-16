#!/usr/bin/env python3
"""比对新旧两份审查报告（内容级，不只看三态）。

抽取维度：三态 / 声明问题数 / 分类 / 依据条款号 / 依据类型计数 / 是否出现
「同源·同题材引证」那条可疑依据（题材闸门要挡的就是它）。
"""
import glob, html, json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))


def text_of(path):
    d = json.load(open(path, encoding='utf-8'))
    c = (d.get('data') or {}).get('document', {}).get('content') or ''
    t = re.sub(r'<br\s*/?>', '\n', c)
    t = re.sub(r'</(p|li|h[1-6]|td|tr)>', '\n', t)
    t = re.sub(r'<[^>]+>', '', t)
    return html.unescape(t)


def feats(t):
    f = {}
    m = re.search(r'【审查结论：(\w+)】', t)
    f['state'] = m.group(1) if m else '—'
    m = re.search(r'共发现\s*(\d+)\s*处', t) or re.search(r'问题数量[：:]\s*\**(\d+)', t)
    f['count'] = m.group(1) if m else '—'
    f['cats'] = sorted(set(re.findall(r'【([^】]{2,12})】\s*(?:全文|素材正文|text)', t)))
    f['articles'] = sorted(set(re.findall(r'\b([SW]-1\.\d+)\b', t)))
    f['p0codes'] = sorted(set(re.findall(r'\b([HMU]\d{2})\b', t)))
    f['n_lib'] = len(re.findall(r'有库内条款依据', t))
    f['n_ext'] = len(re.findall(r'外部标准|support\.google|advertising\.amazon|fda\.gov', t))
    f['n_nolib'] = len(re.findall(r'无库内依据|需人工确认（本条无库内依据）', t))
    f['same_src'] = len(re.findall(r'同源/同题材引证', t))
    f['p0fast'] = bool(re.search(r'P0 快路', t))
    return f


def main():
    old = sorted(glob.glob(os.path.join(HERE, 'out/reports_old/*.json')))
    new = sorted(glob.glob(os.path.join(HERE, 'out/reports_new/*.json')))
    if len(old) != len(new):
        print(f'份数不等：旧 {len(old)} 新 {len(new)}'); return 3
    out = []
    for o, n in zip(old, new):
        fo, fn = feats(text_of(o)), feats(text_of(n))
        assert os.path.basename(o)[:2] == os.path.basename(n)[:2]
        out.append((os.path.basename(o)[:2], fo, fn))
    print(f"{'#':<3}{'三态':<16}{'条数':<10}{'库内依据':<10}{'外部标准':<10}{'同源引证':<10}{'快路'}")
    print('-' * 92)
    for i, fo, fn in out:
        print(f"{i:<3}{fo['state']+' → '+fn['state']:<16}{fo['count']+' → '+fn['count']:<10}"
              f"{str(fo['n_lib'])+' → '+str(fn['n_lib']):<10}"
              f"{str(fo['n_ext'])+' → '+str(fn['n_ext']):<10}"
              f"{str(fo['same_src'])+' → '+str(fn['same_src']):<10}"
              f"{'是' if fn['p0fast'] else '否'}")
    print()
    print('=== 条款号变化 ===')
    for i, fo, fn in out:
        if fo['articles'] != fn['articles'] or fo['p0codes'] != fn['p0codes']:
            print(f"{i}  条款 {fo['articles']} → {fn['articles']}   规则码 {fo['p0codes']} → {fn['p0codes']}")
    print()
    print('=== 分类变化 ===')
    for i, fo, fn in out:
        if fo['cats'] != fn['cats']:
            print(f"{i}  {fo['cats']} → {fn['cats']}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
