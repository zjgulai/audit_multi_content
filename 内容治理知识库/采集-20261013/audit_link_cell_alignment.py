#!/usr/bin/env python3
"""收口核对：**80 行「格内结论 ↔ 点开那份报告」逐行对齐**（Owner 2026-10-16 的要求③）。

判据（每行三条，逐行真打开那份文档，不抽样）：
  ① 行内**有链接** ⇒ 那份报告打得开，且正文里的 `共发现 N 处` **等于**格内 `问题数量`；
  ② 行内**是 PASS** ⇒ 链接应为空（PRD：PASS 不出报告；本轮没建文档 ⇒ 没有可点的东西）；
  ③ 行内**非 PASS 但没有链接** ⇒ 点名列出来（要么该补、要么该说清为什么没有）。

输出：一份 JSON 留痕 + 屏幕上按行列出**对不上的行**（一行都没有才算收口）。

  python3 audit_link_cell_alignment.py
  python3 audit_link_cell_alignment.py --json out/final_align.json
"""
# ★ 2026-10-16（Owner 改名同步）：这一列的名字**不许写死** —— 名字与判据都在 link_col.py
from link_col import LINK_COL_CANDIDATES, resolve_from_fields, pick_link  # noqa: E402
import argparse
import concurrent.futures as cf
import json
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'out')
LARK = os.path.expanduser('~/.dsh/bin/lark-cli')
BASE, TABLE, COL = LINK_COL_CANDIDATES[1]   # ★ 见 link_col.py：改名后这里会被 resolve 覆盖


def plain(v):
    if v is None:
        return ''
    if isinstance(v, str):
        return v
    if isinstance(v, list):
        return ''.join(plain(x) for x in v)
    if isinstance(v, dict):
        return str(v.get('link') or v.get('text') or '')
    return str(v)


def tok_of(s):
    m = re.search(r'/docx/([A-Za-z0-9]+)', str(s or ''))
    return m.group(1) if m else ''


def read_table():
    p = '/tmp/final_align_tbl.ndjson'
    subprocess.run([LARK, 'base', '+record-list', '--base-token', BASE, '--table-id', TABLE,
                    '--limit', '2000', '--format', 'ndjson', '--output', p, '--overwrite',
                    '--profile', 'dsh-kb', '--as', 'bot'], capture_output=True, text=True, cwd='/tmp')
    return [json.loads(l) for l in open(p, encoding='utf-8') if l.strip()]


def doc_n(tok, tries=2):
    """那份报告的「共发现 N 处」。

    ★ 失败要**重试一次**再判「打不开」：实测第 45 行第一次 fetch 失败、第二次就成
      （并发 8 路打飞书会偶发限流）—— 把一次限流报成「链接打不开」是假红，
      而假红会让人去修一个没坏的东西（本库栽过：判据太宽 ⇒ 一条假红挤掉一个真问题）。
    """
    for k in range(tries):
        q = subprocess.run([LARK, 'docs', '+fetch', '--doc', tok, '--profile', 'dsh-kb', '--as', 'bot',
                            '--doc-format', 'markdown'], capture_output=True, text=True, cwd='/tmp')
        try:
            c = json.loads(q.stdout)['data']['document']['content']
        except Exception:                                        # noqa: BLE001
            if k + 1 < tries:
                time.sleep(1.5)
                continue
            return None, False
        m = re.search(r'共发现\s*(\d+)\s*处', c)
        if m:
            return int(m.group(1)), True
        if re.search(r'未发现已知底线风险', c):
            return 0, True
        return None, True
    return None, False
    m = re.search(r'共发现\s*(\d+)\s*处', c)
    if m:
        return int(m.group(1)), True
    if re.search(r'未发现已知底线风险', c):
        return 0, True
    return None, True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--json')
    a = ap.parse_args()
    rows = read_table()
    recs = []
    for i, r in enumerate(rows, 1):
        recs.append({'row': i, 'cid': plain(r.get('内容 ID')), 'verdict': plain(r.get('Agent 结论')).strip(),
                     'cell_n': plain(r.get('问题数量')).strip(),
                     'tok': tok_of(plain(r.get(COL))), 'link': plain(r.get(COL))})
    toks = sorted({x['tok'] for x in recs if x['tok']})
    with cf.ThreadPoolExecutor(max_workers=8) as ex:
        got = dict(zip(toks, ex.map(lambda t: doc_n(t), toks)))

    bad = []
    for x in recs:
        if x['tok']:
            n, opened = got.get(x['tok'], (None, False))
            x['doc_n'], x['doc_opened'] = n, opened
            if not opened:
                bad.append({**x, 'why': '链接打不开（docs +fetch 失败）'})
            elif x['verdict'].upper() == 'PASS':
                bad.append({**x, 'why': f"格内 PASS，却挂着报告链接（那份写着 {n} 处）"})
            elif n is None:
                bad.append({**x, 'why': '那份报告里既没有「共发现 N 处」也不是 PASS —— 读不出问题数'})
            elif str(n) != x['cell_n']:
                bad.append({**x, 'why': f"格内 {x['cell_n']} 处 ／ 报告 {n} 处"})
        else:
            x['doc_n'], x['doc_opened'] = None, False
            if x['verdict'].upper() != 'PASS':
                bad.append({**x, 'why': f"{x['verdict'] or '(无结论)'} 但没有报告链接"})
    out = {'at': time.strftime('%Y-%m-%d %H:%M:%S'), 'n': len(recs), 'bad_n': len(bad), 'bad': bad,
           'rows': [{k: v for k, v in x.items() if k != 'link'} for x in recs]}
    print(f"80 行收口核对：对齐 {len(recs) - len(bad)}/{len(recs)}" + (f"｜**对不上 {len(bad)}**" if bad else ' ✅'))
    for b in bad:
        print(f"  行{b['row']:>2} {b['verdict']:<7} 格内={b['cell_n']:<3} 链接={b['tok'] or '(空)':<26} {b['why']}｜{b['cid'][:44]}")
    if a.json:
        os.makedirs(OUT, exist_ok=True)
        json.dump(out, open(a.json, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        print('留痕 →', a.json)
    return 0 if not bad else 3


if __name__ == '__main__':
    sys.exit(main())
