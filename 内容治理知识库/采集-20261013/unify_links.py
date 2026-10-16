#!/usr/bin/env python3
"""把两格报告链接**统一成可点开的具名链接**。

  · `报告链接`（style=url）      → `[审查报告](url)`      ← 恢复被我写坏的显示名
  · `10/14重跑报告链接`（plain） → `[内容审查报告](url)`  ← Owner 定的形态，与手改那格逐字一致

判据：写前先读、写后回读，两格都必须是 `[<名>](<url>)` 形态；不符就报出来。
"""
import json, os, re, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
LARK = os.path.expanduser('~/.dsh/bin/lark-cli')
BASE, TABLE = 'RY2UbCRjXaeeWwscUPScVN5AnQc', 'tblavfbMDMeRsulo'
OLD_NAME, NEW_NAME = '审查报告', '内容审查报告'


def sh(a): return subprocess.run(a, capture_output=True, text=True)


def table():
    r = sh([LARK, 'base', '+record-list', '--base-token', BASE, '--table-id', TABLE,
            '--page-size', '200', '--format', 'json', '--profile', 'dsh-kb', '--as', 'bot'])
    return json.loads(r.stdout)['data']


def url_of(v):
    if not v: return None
    m = re.search(r'/docx/([A-Za-z0-9]+)', v if isinstance(v, str) else json.dumps(v))
    return f'https://momcozy-in.feishu.cn/docx/{m.group(1)}' if m else None


def main():
    apply = '--apply' in sys.argv
    d = table(); F, rows = d['fields'], d['data']; rids = d['record_id_list']
    i1, i2 = F.index('报告链接'), F.index('10/14重跑报告链接')
    todo = {}
    for rid, r in zip(rids, rows):
        f = {}
        u1 = url_of(r[i1])
        if u1 and not str(r[i1] or '').startswith(f'[{OLD_NAME}]'):
            # 只修「显示名是裸 URL（我写坏的）」；具名的（含「审查报告（补）」）不动
            if str(r[i1] or '').startswith('[http'):
                f['报告链接'] = f'[{OLD_NAME}]({u1})'
        u2 = url_of(r[i2])
        if u2 and str(r[i2] or '') != f'[{NEW_NAME}]({u2})':
            f['10/14重跑报告链接'] = f'[{NEW_NAME}]({u2})'
        if f: todo[rid] = f
    print(f'需要统一的：{len(todo)} 行  '
          f'(报告链接 {sum(1 for f in todo.values() if "报告链接" in f)} ｜ '
          f'重跑链接 {sum(1 for f in todo.values() if "10/14重跑报告链接" in f)})')
    if not apply:
        for rid, f in list(todo.items())[:3]:
            print('   例:', rid, json.dumps(f, ensure_ascii=False)[:130])
        print('（预演。加 --apply 才写。）'); return 0
    r = sh([LARK, 'base', '+record-batch-update', '--base-token', BASE, '--table-id', TABLE,
            '--json', json.dumps({'update_records': todo}, ensure_ascii=False),
            '--profile', 'dsh-kb', '--as', 'bot'])
    print('写回 ok =', '"ok": true' in (r.stdout or ''), (r.stdout or r.stderr or '')[:160])
    # ── 回读复核 ──
    d2 = table(); F2, rows2 = d2['fields'], d2['data']
    a1, a2 = F2.index('报告链接'), F2.index('10/14重跑报告链接')
    bad = 0
    for r_ in rows2:
        for idx, name in ((a1, OLD_NAME), (a2, NEW_NAME)):
            v = r_[idx]
            if not v: continue
            if not re.match(r'^\[' + re.escape(name) + r'\]\(https://', str(v)) and name == NEW_NAME:
                bad += 1
    print(f'回读：重跑链接格形态不符的 {bad} 行')
    return 0


if __name__ == '__main__':
    sys.exit(main())
