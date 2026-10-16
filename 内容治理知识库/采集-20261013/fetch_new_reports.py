#!/usr/bin/env python3
"""把 80 行的**新版**报告云文档（10/14 重跑那一版）全量拉下来，供逐行比对。

新版令牌从守衡台账 `PMO/shouheng-state/batch-review.json` 取 ——
跟随器往 `10/14重跑报告链接` 写的就是台账里那个 `report_url`（见 follow_writeback.py:107/123），
所以台账与表是同一个来源；而**旧**链接由跟随器还原回 `报告链接`（orig_links.json 里也有）。

落点 out/reports_new/<内容ID>.json —— 与 fetch_old_reports.py 同一命名口径：
**按内容 ID 对齐，不靠顺序**（顺序对齐错过一次）。
"""
import json, os, re, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'out', 'reports_new')
LEDGER = '/Users/lute/Project/audit_multi_content/PMO/shouheng-state/batch-review.json'
LARK = os.path.expanduser('~/.dsh/bin/lark-cli')
os.makedirs(OUT, exist_ok=True)

orig = json.load(open(os.path.join(HERE, 'out', 'orig_links.json'), encoding='utf-8'))
led = json.load(open(LEDGER, encoding='utf-8'))['items']

want = {}
for cid in orig:                       # ← 以 80 行为准，不从台账反推（台账是超集）
    d = led.get(cid) or {}
    m = re.search(r'/docx/([A-Za-z0-9]+)', str(d.get('report_url') or ''))
    want[cid] = m.group(1) if m else None
nohref = [k for k, v in want.items() if not v]

ok = skip = fail = 0
for cid, tok in sorted(want.items()):
    if not tok:
        continue
    p = os.path.join(OUT, f'{cid}.json')
    if os.path.exists(p) and os.path.getsize(p) > 200 and os.environ.get('FORCE') != '1':
        skip += 1
        continue
    for attempt in (1, 2):
        r = subprocess.run([LARK, 'docs', '+fetch', '--doc', tok,
                            '--profile', 'dsh-kb', '--as', 'bot'],
                           capture_output=True, text=True)
        if r.returncode == 0 and len(r.stdout) > 200:
            open(p, 'w', encoding='utf-8').write(r.stdout); ok += 1
            break
        if attempt == 2:
            fail += 1
            print(f'  ✗ {cid} ({tok}) rc={r.returncode} {r.stderr.strip()[:120]}')
        time.sleep(1.2)

print(f'新报告：新拉 {ok} ｜ 已有 {skip} ｜ 失败 {fail} ｜ 台账里没 report_url {len(nohref)} {nohref[:4]}')
json.dump(want, open(os.path.join(HERE, 'out', 'new_link_map.json'), 'w'),
          ensure_ascii=False, indent=1)
