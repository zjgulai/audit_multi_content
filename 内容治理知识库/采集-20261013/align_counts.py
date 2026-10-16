#!/usr/bin/env python3
"""核对 `问题数量` 与「10/14重跑报告链接」那份报告**声明的条数**是否一致。

判据（报告里两处都取，先取到为准）：
  · `【审查结论：X】共发现 N 处…`（P0 快路与合并报告都用这句）
  · `问题数量：**N**`
"""
import html, json, os, re, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
LARK = os.path.expanduser('~/.dsh/bin/lark-cli')
BASE, TABLE = 'RY2UbCRjXaeeWwscUPScVN5AnQc', 'tblavfbMDMeRsulo'
CACHE = os.path.join(HERE, 'out/doc_count_cache.json')


def fetch_table():
    r = subprocess.run([LARK, 'base', '+record-list', '--base-token', BASE, '--table-id', TABLE,
                        '--page-size', '200', '--format', 'json', '--profile', 'dsh-kb', '--as', 'bot'],
                       capture_output=True, text=True)
    return json.loads(r.stdout)['data']


def fetch_doc(tok):
    r = subprocess.run([LARK, 'docs', '+fetch', '--doc', tok, '--profile', 'dsh-kb', '--as', 'bot'],
                       capture_output=True, text=True)
    d = json.loads(r.stdout or '{}')
    c = (d.get('data') or {}).get('document', {}).get('content') or ''
    t = re.sub(r'<br\s*/?>', '\n', c)
    t = re.sub(r'</(p|li|h[1-6]|td|tr)>', '\n', t)
    return html.unescape(re.sub(r'<[^>]+>', '', t))


def declared(t):
    m = re.search(r'共发现\s*(\d+)\s*处', t)
    if m:
        return int(m.group(1))
    m = re.search(r'问题数量[：:]\s*\**(\d+)', t)
    return int(m.group(1)) if m else None


def main():
    d = fetch_table()
    F, rows, rids = d['fields'], d['data'], d['record_id_list']
    cache = json.load(open(CACHE, encoding='utf-8')) if os.path.exists(CACHE) else {}
    out = []
    for rid, r in zip(rids, rows):
        cid = r[F.index('内容 ID')]
        newu = r[F.index('10/14重跑报告链接')] or ''
        m = re.search(r'/docx/([A-Za-z0-9]+)', newu)
        if not m:
            continue
        tok = m.group(1)
        if tok not in cache:
            cache[tok] = declared(fetch_doc(tok))
        n_report = cache[tok]
        n_table = r[F.index('问题数量')]
        n_table = int(n_table) if isinstance(n_table, (int, float)) else (int(n_table) if str(n_table).isdigit() else None)
        out.append((rid, cid, tok, n_report, n_table))
    json.dump(cache, open(CACHE, 'w'), ensure_ascii=False, indent=1)
    bad = [x for x in out if x[3] != x[4]]
    print(f'已重跑行：{len(out)} ｜ 报告条数与表内一致：{len(out)-len(bad)} ｜ **不一致：{len(bad)}**')
    if bad:
        print(f"{'记录':<16}{'内容 ID':<40}{'报告':<8}{'表内':<6}")
        for rid, cid, tok, nr, nt in bad:
            print(f'{rid:<16}{cid:<40}{str(nr):<8}{str(nt):<6}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
