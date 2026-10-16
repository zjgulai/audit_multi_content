#!/usr/bin/env python3
"""文案 35 行重跑完成后的核对（Owner 要拿去验证，所以这份要能自证）。

四件事，缺一件都不算「执行完」：
  ① 回读一致性：35 行的 `Agent 结论/问题数量/置信度/问题分类汇总` 是否都落上了；
  ② 表 ↔ 报告同源：表里结论/数量 vs 链接那份报告的【审查结论】/「共发现 N 处」；
  ③ 链接列同步：`10/14重跑报告链接` 是否指向**这一轮**新报告（台账 report_url）；
  ④ 引用同源判据：报告引文是否逐字落在**这一轮新文案**里（今天那个 bug 的探针）。

用法：python3 post_wenan_rerun_check.py [--apply-links]
"""
import argparse, collections, glob, html, json, os, re, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'out')
REP = os.path.join(OUT, 'reports_20261015')
LARK = os.path.expanduser('~/.dsh/bin/lark-cli')
BASE, TABLE = 'RY2UbCRjXaeeWwscUPScVN5AnQc', 'tblavfbMDMeRsulo'
LEDGER = '/Users/lute/Project/audit_multi_content/PMO/shouheng-state/batch-review.json'
LINK_COL = '10/14重跑报告链接'


def plain(c):
    if c is None:
        return ''
    if isinstance(c, str):
        return c
    if isinstance(c, (int, float)):
        return str(c)
    if isinstance(c, list):
        return ''.join(str(s.get('text') or s.get('link') or '') if isinstance(s, dict) else str(s) for s in c)
    return str(c)


def strip_tags(c):
    t = re.sub(r'<br\s*/?>', '\n', c)
    t = re.sub(r'</(p|li|h[1-6]|td|tr)>', '\n', t)
    return html.unescape(re.sub(r'<[^>]+>', '', t))


def fetch_doc(tok):
    p = os.path.join(REP, f'{tok}.txt')
    if os.path.exists(p):
        return open(p, encoding='utf-8').read()
    q = subprocess.run([LARK, 'docs', '+fetch', '--doc', tok, '--profile', 'dsh-kb', '--as', 'bot'],
                       capture_output=True, text=True, cwd='/tmp')
    try:
        c = json.loads(q.stdout)['data']['document']['content']
    except Exception:
        return None
    open(p, 'w', encoding='utf-8').write(c)
    return c


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply-links', action='store_true')
    a = ap.parse_args()
    led = json.load(open(LEDGER, encoding='utf-8'))['items']
    q = subprocess.run([LARK, 'base', '+record-list', '--base-token', BASE, '--table-id', TABLE,
                        '--view-id', 'vewhS7Rwx0', '--page-size', '200', '--profile', 'dsh-kb',
                        '--as', 'bot', '--format', 'json'], capture_output=True, text=True, cwd='/tmp')
    d = json.loads(q.stdout)['data']
    f = d['fields']
    I = {k: f.index(k) for k in ('内容 ID', '内容类型', '状态', 'Agent 结论', '问题数量', '置信度',
                                 '问题分类汇总', LINK_COL, '采集数据')}
    rows = [(d['record_id_list'][i], r) for i, r in enumerate(d['data'])]
    wen = [(rid, r) for rid, r in rows if plain(r[I['内容类型']]) == '文案']
    print(f"══ ① 回读一致性（文案 {len(wen)} 行）══")
    miss = []
    for rid, r in wen:
        cid = plain(r[I['内容 ID']])
        d0 = led.get(cid) or {}
        lack = [k for k in ('Agent 结论', '问题数量', '置信度', '问题分类汇总') if not plain(r[I[k]]).strip()]
        if lack or not d0.get('answered_at'):
            miss.append((cid, lack, '未跑' if not d0.get('answered_at') else '字段空'))
    print(f"   四个结论字段齐全且台账已答: {len(wen)-len(miss)}/{len(wen)}")
    for m in miss[:8]:
        print(f"   ❌ {m[0][:44]:<46} 缺 {m[1] or '—'} ｜ {m[2]}")
    print(f"\n══ ② 表 ↔ 报告 同源 ══")
    bad2 = []
    link_fix = {}
    for rid, r in wen:
        cid = plain(r[I['内容 ID']])
        ru = (led.get(cid) or {}).get('report_url') or ''
        m = re.search(r'/docx/([A-Za-z0-9]+)', ru)
        tok = m.group(1) if m else None
        cur = re.search(r'/docx/([A-Za-z0-9]+)', plain(r[I[LINK_COL]]))
        if tok and (not cur or cur.group(1) != tok):
            link_fix[rid] = f'[内容审查报告]({ru})'
        if not tok:
            bad2.append((cid, '台账里没有这一轮的 report_url（报告可能没建）'))
            continue
        c = fetch_doc(tok)
        if not c:
            bad2.append((cid, f'报告拉不到 {tok}'))
            continue
        t = strip_tags(c)
        rs = re.search(r'【审查结论：(\w+)】', t)
        rd = re.search(r'共发现\s*(\d+)\s*处', t)
        concl, cnt = plain(r[I['Agent 结论']]), plain(r[I['问题数量']])
        if rs and concl and rs.group(1) != concl:
            bad2.append((cid, f'报告 {rs.group(1)} ≠ 表内 {concl}'))
        if rd and cnt and int(rd.group(1)) != int(float(cnt)):
            bad2.append((cid, f'报告「共发现 {rd.group(1)} 处」 ≠ 表内 {cnt}'))
    print(f"   结论/数量与报告一致: {len(wen)-len(bad2)}/{len(wen)}")
    for b in bad2[:8]:
        print(f"   ❌ {b[0][:44]:<46} {b[1]}")
    print(f"\n══ ③ 链接列同步 ══  需要更新 {len(link_fix)} 行")
    if link_fix and a.apply_links:
        payload = {'update_records': {rid: {LINK_COL: v} for rid, v in link_fix.items()}}
        w = subprocess.run([LARK, 'base', '+record-batch-update', '--base-token', BASE, '--table-id', TABLE,
                            '--json', json.dumps(payload, ensure_ascii=False), '--profile', 'dsh-kb',
                            '--as', 'bot'], capture_output=True, text=True, cwd='/tmp')
        print(f"   写入 rc {w.returncode}（{len(link_fix)} 行）")
    elif link_fix:
        print("   （加 --apply-links 才真写）")
    print(f"\n══ ④ 引用同源判据 ══")
    r2 = subprocess.run([sys.executable, os.path.join(HERE, 'audit_quote_scope.py')],
                        capture_output=True, text=True, cwd=HERE)
    for line in (r2.stdout or '').splitlines():
        if '文案' in line or '越界' in line:
            print('   ' + line.strip())
    json.dump({'miss': miss, 'bad2': bad2, 'link_fix': list(link_fix)}, open(os.path.join(OUT, 'post_wenan_check.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)


if __name__ == '__main__':
    main()