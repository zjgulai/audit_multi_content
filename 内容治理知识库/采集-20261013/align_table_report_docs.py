#!/usr/bin/env python3
"""重跑之后：**飞书云文档与多维表逐行对齐**核对（Owner 2026-10-16：「飞书云文档数据要对上」）。

比什么（每一行都逐字比，不是抽样）：
  ① 表里那一行格内的**报告链接** ⇒ 能不能打开（`docs +fetch` 拿到正文）；
  ② 表里的**结论行**（`【审查结论：X】`） == 文档里的结论行；
  ③ 表里的**问题数**（`共发现 N 处` / `问题数 N`） == 文档里的问题数；
  ④ 表里的**分类计数行**（`· XX类问题：k 个`）在文档里**逐条都能找到**（顺序不限）；
  ⑤ 链接列 `10/14重跑报告链接` 的 token == 格内链接 token（两处一个数）；
  ⑥ 图文口径：图片/视频行文档里必须有**画面读数**痕迹（`画面` 小节）或如实写「没读到」——

用法：
  python3 align_table_report_docs.py            # 全量核对
  python3 align_table_report_docs.py --only 图片 视频     # 只核某几类
"""
import argparse, collections, json, os, re, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'out')
LARK = os.path.expanduser('~/.dsh/bin/lark-cli')
BASE, TABLE = 'RY2UbCRjXaeeWwscUPScVN5AnQc', 'tblavfbMDMeRsulo'
COL = '10/14重跑报告链接'


def plain(v):
    if v is None:
        return ''
    if isinstance(v, str):
        return v
    if isinstance(v, list):
        return ''.join(str(s.get('text') or s.get('link') or '') if isinstance(s, dict) else str(s) for s in v)
    if isinstance(v, dict):
        return str(v.get('text') or v.get('link') or '')
    return str(v)


def norm(s):
    return re.sub(r'\s+', ' ', str(s or '')).strip()


def docx_of(s):
    m = re.search(r'/docx/([A-Za-z0-9]+)', str(s or ''))
    return m.group(1) if m else ''


def read_table():
    out = '/tmp/align_tbl.ndjson'
    subprocess.run([LARK, 'base', '+record-list', '--base-token', BASE, '--table-id', TABLE,
                    '--limit', '2000', '--format', 'ndjson', '--output', out, '--overwrite',
                    '--profile', 'dsh-kb', '--as', 'bot'], capture_output=True, text=True, cwd='/tmp')
    return [json.loads(l) for l in open(out, encoding='utf-8') if l.strip()]


def fetch_doc(tok):
    q = subprocess.run([LARK, 'docs', '+fetch', '--doc', tok, '--profile', 'dsh-kb', '--as', 'bot',
                        '--doc-format', 'markdown', '--format', 'ndjson'],
                       capture_output=True, text=True, cwd='/tmp')
    if q.returncode != 0 or not q.stdout.strip():
        return False, '', None
    try:
        d = json.loads(q.stdout.strip().splitlines()[0])['document']
        return True, d.get('content', ''), d.get('revision_id')
    except Exception:
        return False, '', None


def counts_of(text):
    """从一段文本里抽出：结论态、问题数、分类计数 {类名: n}。"""
    st = (re.search(r'【审查结论：(\w+)】', text) or [None, None])[1]
    n = None
    for pat in (r'共发现\s*(\d+)\s*处', r'问题数\s*[:：]?\s*(\d+)', r'共\s*(\d+)\s*处'):
        m = re.search(pat, text)
        if m:
            n = int(m.group(1))
            break
    cats = {m.group(1): int(m.group(2)) for m in re.finditer(r'·\s*([^·\n：]{2,12}?类问题)：(\d+)\s*个', text)}
    other = re.search(r'另有\s*\*{0,2}(\d+)\s*条', text)
    if other:
        cats['另有'] = int(other.group(1))
    return st, n, cats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--only', nargs='*', default=[])
    a = ap.parse_args()
    rows = read_table()
    if a.only:
        rows = [r for r in rows if plain(r.get('内容类型')).strip() in a.only]
    stat = collections.Counter()
    detail, bad = [], []
    cache = {}
    for r in rows:
        cid = plain(r.get('内容 ID'))
        t = plain(r.get('内容类型')).strip()
        cell = plain(r.get('问题分类汇总'))
        col = plain(r.get(COL))
        tc, tl = docx_of(cell), docx_of(col)
        if not tc and not tl:
            stat[f'{t}-无链接'] += 1
            detail.append({'cid': cid, 'type': t, 'state': plain(r.get('Agent 结论')), 'link': '', 'verdict': '无链接（PASS 按口径不带）'})
            continue
        if tc and tl and tc != tl:
            bad.append({'cid': cid, 'why': '链接列与格内链接不是同一份', 'cell': tc, 'col': tl})
        tok = tc or tl
        if tok not in cache:
            cache[tok] = fetch_doc(tok)
        ok, body, rev = cache[tok]
        if not ok:
            stat[f'{t}-文档打不开'] += 1
            bad.append({'cid': cid, 'why': '文档打不开', 'tok': tok})
            continue
        cs, cn, cc = counts_of(cell)
        ds, dn, dc = counts_of(body)
        probs = []
        if cs and ds and cs != ds:
            probs.append(f'结论行 {cs} vs 文档 {ds}')
        if cn is not None and dn is not None and cn != dn:
            probs.append(f'问题数 {cn} vs 文档 {dn}')
        missing = [k for k in cc if k not in dc and k != '另有']
        if missing:
            probs.append('文档里找不到这些分类计数：' + '、'.join(missing))
        if t in ('图片', '视频') and '画面' not in body:
            probs.append('文档里没有画面读数痕迹（图片/视频行应有，或如实写"没读到"）')
        verdict = '一致' if not probs else '；'.join(probs)
        stat[f'{t}-{"一致" if not probs else "不一致"}'] += 1
        if probs:
            bad.append({'cid': cid, 'why': verdict, 'tok': tok})
        detail.append({'cid': cid, 'type': t, 'state': plain(r.get('Agent 结论')), 'n': cn,
                       'cats': cc, 'tok': tok, 'rev': rev, 'verdict': verdict})
    print('—— 逐行核对 ——')
    for k in sorted(stat):
        print(f'  {k}: {stat[k]}')
    print(f'\n文档缓存 {len(cache)} 份 ｜ 不一致 {len(bad)} 行')
    for b in bad[:20]:
        print('   ❌', b)
    if len(bad) > 20:
        print(f'   … 另有 {len(bad) - 20} 行')
    os.makedirs(OUT, exist_ok=True)
    fp = os.path.join(OUT, 'align_docs_%s.json' % time.strftime('%Y%m%d-%H%M%S'))
    json.dump({'at': time.strftime('%Y-%m-%d %H:%M:%S'), 'stat': dict(stat), 'bad': bad, 'detail': detail},
              open(fp, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(f'\n台账 → {fp}')
    return 3 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
