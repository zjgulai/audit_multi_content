#!/usr/bin/env python3
"""把 80 行的**旧**报告云文档（跑 10/14 重跑之前那一版）全量拉下来，供逐行比对。

旧令牌来自 out/orig_links.json（12:xx 建表快照里那一列的原值，之后被跟随器覆盖过）。
落点 out/reports_old/<内容ID>.json —— 用内容 ID 命名，**不靠顺序对齐**（顺序对齐过一次就错过）。
"""
import json, os, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'out', 'reports_old')
LARK = os.path.expanduser('~/.dsh/bin/lark-cli')
os.makedirs(OUT, exist_ok=True)

src = json.load(open(os.path.join(HERE, 'out', 'orig_links.json'), encoding='utf-8'))
only = set(sys.argv[1:])

ok = skip = fail = 0
for cid, v in sorted(src.items()):
    if only and cid not in only:
        continue
    tok = (v or {}).get('orig')
    if not tok:
        fail += 1
        print(f'  ✗ {cid} 没有旧令牌')
        continue
    p = os.path.join(OUT, f'{cid}.json')
    if os.path.exists(p) and os.path.getsize(p) > 200:
        skip += 1
        continue
    for attempt in (1, 2):
        r = subprocess.run([LARK, 'docs', '+fetch', '--doc', tok,
                            '--profile', 'dsh-kb', '--as', 'bot'],
                           capture_output=True, text=True)
        if r.returncode == 0 and len(r.stdout) > 200:
            open(p, 'w', encoding='utf-8').write(r.stdout)
            ok += 1
            break
        if attempt == 2:
            fail += 1
            print(f'  ✗ {cid} ({tok}) rc={r.returncode} {r.stderr.strip()[:120]}')
        time.sleep(1.2)

print(f'旧报告：新拉 {ok} ｜ 已有 {skip} ｜ 失败 {fail} ｜ 目录 {OUT}')
fail and sys.exit(1)
