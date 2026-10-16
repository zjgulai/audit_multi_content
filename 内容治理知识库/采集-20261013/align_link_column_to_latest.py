#!/usr/bin/env python3
"""把采集表 `10/14重跑报告链接` 那一列**对齐到与格内结论同源的那一份报告**。

Owner 2026-10-16 裁定（「① 链接换成与格内同源的最新那份」）。

── 为什么要做（实测，逐条可核）

  复跑会给同一行**新建**一份报告云文档（`review_publish.publishReportDoc` 每次 `docs +create`），
  而采集表那一列**从来没人写** —— 回填字段名叫 `报告链接`，可这一列叫 `10/14重跑报告链接`
  ⇒ `batch_review_runner.mjs::fieldsFrom` 按名字对不上就**跳过**它
  ⇒ 于是出现这种形状：**格内结论是新一轮的（1 处），链接点开却是上一轮那份（4 处）**。
  实测（2026-10-16）：37 行「表内链接 ≠ 台账里这一轮的报告」。
  其中 **27 行的格内数字与台账那份报告逐字一致**（同源 ⇒ 可以直接换链接），
  另外 10 行**不同源**（格内数字与那一轮报告对不上）⇒ **本脚本一行都不碰**，
  照实点名列出来交给人工 —— 那 10 行的问题不在链接，在格内结论本身（要重跑）。

── 判据（三道，缺一条都不换）

  ① 台账里有这一行**本轮**的 `report_url`，且与列内现值**不是同一个 token**；
  ② 那一份报告**打得开**、且正文里的 `共发现 N 处` **等于**格内 `问题数量`（同源判据）；
  ③ 目标列是**文本列**（本表实测是文本，不是 URL 列）⇒ 写 `[内容审查报告](<url>)` 这一种格式，
     顺带把历史里那种**嵌套重复**的坏形状（`[x](u](u)`）一起修直。

用法：
  python3 align_link_column_to_latest.py            # 干跑（默认，什么都不写）
  python3 align_link_column_to_latest.py --apply     # 真写（写前后各回读一次）
"""
# ★ 2026-10-16（Owner 改名同步）：这一列的名字**不许写死** —— 名字与判据都在 link_col.py
from link_col import LINK_COL_CANDIDATES, resolve_from_fields, pick_link  # noqa: E402
import argparse
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
LEDGER = os.path.expanduser('~/Project/audit_multi_content/PMO/shouheng-state/batch-review.json')
TEXT = '内容审查报告'


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
    p = '/tmp/link_align_tbl.ndjson'
    subprocess.run([LARK, 'base', '+record-list', '--base-token', BASE, '--table-id', TABLE,
                    '--limit', '2000', '--format', 'ndjson', '--output', p, '--overwrite',
                    '--profile', 'dsh-kb', '--as', 'bot'], capture_output=True, text=True, cwd='/tmp')
    return [json.loads(l) for l in open(p, encoding='utf-8') if l.strip()]


def doc_n(tok):
    """那一份报告的 `共发现 N 处`（PASS 正文回 0；读不到回 None）。"""
    q = subprocess.run([LARK, 'docs', '+fetch', '--doc', tok, '--profile', 'dsh-kb', '--as', 'bot',
                        '--doc-format', 'markdown'], capture_output=True, text=True, cwd='/tmp')
    try:
        c = json.loads(q.stdout)['data']['document']['content']
    except Exception:                                            # noqa: BLE001
        return None
    m = re.search(r'共发现\s*(\d+)\s*处', c)
    if m:
        return int(m.group(1))
    return 0 if re.search(r'未发现已知底线风险', c) else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true')
    a = ap.parse_args()

    rows = read_table()
    led = json.load(open(LEDGER, encoding='utf-8')).get('items') or {}
    cand, skip, drop = [], [], []
    for i, r in enumerate(rows, 1):
        cid = plain(r.get('内容 ID'))
        cur = tok_of(plain(r.get(COL)))
        it = led.get(cid) or {}
        new = tok_of(it.get('report_url'))
        verdict = plain(r.get('Agent 结论')).strip().upper()
        # ── PASS 行：本轮**没有报告**（没有可并的条目 ⇒ 不建文档），
        #    而列里可能还挂着上一轮那份 ⇒ 会出现「格内 PASS/0、点开那份写着 4 处」。
        #    口径与本表既有规则一致：**清空只走 PASS 这条规则**（Owner 2026-10-16 ⑨）。
        if verdict == 'PASS' and cur:
            n_cur = doc_n(cur)
            if n_cur is None or n_cur > 0:
                drop.append({'row': i, 'cid': cid, 'record_id': r['record_id'], 'old': cur,
                             'old_doc_n': n_cur, 'why': f'格内 PASS/0，而那份报告写着 {n_cur} 处 ⇒ 清空'})
            continue
        if not new or new == cur:
            continue
        cell_n = plain(r.get('问题数量')).strip()
        n = doc_n(new)
        rec = {'row': i, 'cid': cid, 'record_id': r['record_id'], 'old': cur, 'new': new,
               'cell_n': cell_n, 'new_doc_n': n, 'sent_at': it.get('sent_at')}
        (cand if (n is not None and str(n) == cell_n) else skip).append(rec)

    print(f"采样 {len(rows)} 行 ｜ 同源可换 {len(cand)} ｜ 不同源（**一行不碰**）{len(skip)} "
          f"｜ PASS 行清空 {len(drop)}")
    for c in cand:
        print(f"  换 行{c['row']:>2} {c['old'] or '(空)'} → {c['new']}（两侧都是 {c['cell_n']} 处）｜{c['cid'][:42]}")
    for s in skip:
        print(f"  ⚠️ 不动 行{s['row']:>2} 格内={s['cell_n']} 该轮报告={s['new_doc_n']} "
              f"（**不同源** ⇒ 要重跑，不是换链接）｜{s['cid'][:42]}")
    for d in drop:
        print(f"  清 行{d['row']:>2} {d['old']} → (空)：{d['why']}｜{d['cid'][:42]}")
    if not a.apply:
        print('（未加 --apply：什么都没写）')
        return 0

    stamp = time.strftime('%Y%m%d-%H%M%S')
    os.makedirs(OUT, exist_ok=True)
    mapping = os.path.join(OUT, f'link_align_{stamp}.json')
    json.dump({'at': stamp, 'cand': cand, 'skipped': skip, 'cleared': drop},
              open(mapping, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

    patch = {c['record_id']: {COL: f'[{TEXT}](https://momcozy-in.feishu.cn/docx/{c["new"]})'}
             for c in cand}
    for d in drop:
        patch[d['record_id']] = {COL: ''}
    w = subprocess.run([LARK, 'base', '+record-batch-update', '--base-token', BASE, '--table-id', TABLE,
                        '--json', json.dumps({'update_records': patch}, ensure_ascii=False),
                        '--profile', 'dsh-kb', '--as', 'bot'], capture_output=True, text=True, cwd='/tmp')
    print(f"写入 {len(patch)} 行 ｜ rc={w.returncode} {str(w.stdout or w.stderr or '')[:120]}")
    if w.returncode != 0:
        return 3

    back = {r['record_id']: tok_of(plain(r.get(COL))) for r in read_table()}
    bad = [c for c in cand if back.get(c['record_id'], '') != c['new']]
    bad += [d for d in drop if back.get(d['record_id'], '') != '']
    print(f"回读：换成功 {len(cand) - len([c for c in bad if c in cand])}/{len(cand)}"
          f"｜清空成功 {len(drop) - len([d for d in bad if d in drop])}/{len(drop)}"
          + (f"｜**没生效 {len(bad)}**：{[x['row'] for x in bad]}" if bad else ''))
    print('对照表（旧→新）→', mapping)
    return 0 if not bad else 4


if __name__ == '__main__':
    sys.exit(main())
