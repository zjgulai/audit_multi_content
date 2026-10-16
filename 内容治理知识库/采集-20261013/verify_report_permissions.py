#!/usr/bin/env python3
"""只读核对：**所有审查报告云文档**的链接分享设置是否 = tenant_readable。

为什么要单独一把尺子（Owner 2026-10-16 问「权限问题都解决了吗」）：
  · 11:38 那次是**挨个 patch + 回读**（319 份），但它量的是**那一刻**；
  · 之后**又跑过批**（复跑会 `docs +create` 建**新**报告文档）⇒ 新文档有没有跟着设权限，
    那次 patch 一个字都没说 —— 旧读数对**新文档**不成立。
  · 所以这把尺子按**现在**的真实指向收口（表里的链接 ＋ 台账里的 report_url），不看历史清单。

来源三处（去重后逐个回读）：
  ① 多维表「10/14重跑报告链接」列里**当前**的 docx token；
  ② `PMO/shouheng-state/batch-review.json` 每个 item 的 `report_url`（最近一次跑出来的）；
  ③ 11:38 那次的 319 份清单（`out/report_permission_*.json`）—— 防「表里没引用但仍是发布件」。

用法：
  python3 verify_report_permissions.py                 # 全量回读
  python3 verify_report_permissions.py --limit 20      # 抽查
  python3 verify_report_permissions.py --json out/perm_now.json
"""
import argparse, collections, concurrent.futures as cf, glob, json, os, re, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'out')
LARK = os.path.expanduser('~/.dsh/bin/lark-cli')
BASE, TABLE = 'RY2UbCRjXaeeWwscUPScVN5AnQc', 'tblavfbMDMeRsulo'
# ★ 2026-10-16：列名按 /报告链接/ 认（Owner 把「10/14重跑报告链接」改名为「报告链接」）
from link_col import pick_link                                  # noqa: E402
COL = '报告链接'
LEDGER = os.path.expanduser('~/Project/audit_multi_content/PMO/shouheng-state/batch-review.json')
WANT = 'tenant_readable'


def docx_of(s):
    m = re.search(r'/docx/([A-Za-z0-9]+)', str(s or ''))
    return m.group(1) if m else ''


def plain(v):
    if v is None: return ''
    if isinstance(v, str): return v
    if isinstance(v, list): return ''.join(str(s.get('text') or s.get('link') or '') if isinstance(s, dict) else str(s) for s in v)
    if isinstance(v, dict): return str(v.get('text') or v.get('link') or '')
    return str(v)


def sources():
    """返回 {token: [来源说明…]}"""
    src = collections.defaultdict(list)
    # ① 表里的链接
    out = '/tmp/perm_tbl.ndjson'
    subprocess.run([LARK, 'base', '+record-list', '--base-token', BASE, '--table-id', TABLE,
                    '--limit', '2000', '--format', 'ndjson', '--output', out, '--overwrite',
                    '--profile', 'dsh-kb', '--as', 'bot'], capture_output=True, text=True, cwd='/tmp')
    for l in open(out, encoding='utf-8'):
        if not l.strip(): continue
        r = json.loads(l)
        t = docx_of(pick_link(r))
        if t: src[t].append(f"表:{plain(r.get('内容 ID'))[:28]}")
    # ② 台账 report_url
    d = json.load(open(LEDGER, encoding='utf-8'))
    for k, it in (d.get('items') or {}).items():
        t = docx_of(it.get('report_url'))
        if t: src[t].append(f"台账:{k[:28]}")
    # ③ **历次** patch 清单（★ 取并集，不能只取最后一份）——
    #   11:38 那份 319 份、11:49 那份 41 份；只读最后一份会把 319 份里没被表/台账引用的漏掉，
    #   于是「366 → 152」这种读数看着像"少了一批"，其实是**这把尺子自己变窄了**（实测踩过）。
    for p in sorted(glob.glob(os.path.join(OUT, 'report_permission_*.json'))):
        j = json.load(open(p, encoding='utf-8'))
        for e in j.get('patched', []):
            src[e['tok']].append('历史patch清单')
    return src


def get_setting(tok):
    q = subprocess.run([LARK, 'drive', '+permission-get-setting', '--token', tok, '--type', 'docx',
                        '--profile', 'dsh-kb', '--as', 'bot'], capture_output=True, text=True, cwd='/tmp', timeout=60)
    try:
        return json.loads(q.stdout)['data']['permission_public']['link_share_entity'], ''
    except Exception:
        return None, (q.stderr or q.stdout or '')[:160].replace('\n', ' ')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--limit', type=int, default=0)
    ap.add_argument('--json')
    ap.add_argument('--workers', type=int, default=8)
    a = ap.parse_args()

    src = sources()
    toks = sorted(src)
    if a.limit: toks = toks[:a.limit]
    print(f'待回读 {len(toks)} 份（来源合并后去重）', flush=True)
    res, bad, err = {}, [], []
    t0 = time.time()
    with cf.ThreadPoolExecutor(max_workers=a.workers) as ex:
        futs = {ex.submit(get_setting, t): t for t in toks}
        for i, f in enumerate(cf.as_completed(futs), 1):
            t = futs[f]; v, e = f.result()
            res[t] = v
            if v != WANT:
                (bad if v is not None else err).append((t, v, e, src[t][:2]))
            if i % 25 == 0: print(f'  …{i}/{len(toks)}  {time.time()-t0:.0f}s', flush=True)
    print(f'\n== 结果（{time.time()-t0:.0f}s）==')
    print(f'tenant_readable: {sum(1 for v in res.values() if v==WANT)}/{len(res)}')
    if bad:
        print(f'❌ 不是 tenant_readable: {len(bad)}')
        for t, v, e, s in bad[:30]: print('   ', t, '->', v, s)
    if err:
        print(f'⚠️ 读不到设置: {len(err)}')
        for t, v, e, s in err[:30]: print('   ', t, '->', e, s)
    bysrc = collections.Counter()
    for t in toks:
        bysrc[tuple(sorted({s.split(':')[0] for s in src[t]}))] += 1
    print('\n按来源组合：')
    for k, v in bysrc.most_common(): print('   ', '+'.join(k), v)
    if a.json:
        json.dump({'at': time.strftime('%Y-%m-%d %H:%M:%S'), 'want': WANT, 'n': len(res),
                   'ok': sum(1 for v in res.values() if v == WANT),
                   'bad': [{'tok': t, 'got': v, 'src': s} for t, v, _, s in bad],
                   'err': [{'tok': t, 'err': e, 'src': s} for t, _, e, s in err],
                   'settings': res}, open(a.json, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        print('json ->', a.json)


if __name__ == '__main__':
    main()
