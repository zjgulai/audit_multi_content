#!/usr/bin/env python3
"""换掉 5 张**越界**的图片素材（Owner 2026-10-15：「必须是 吸奶器/清洗机/婴儿监控器，
有 5 个不是的，你重新抓取素材，再重新跑」）。

越界的 5 行（按图注逐条核过，旧口径把它们的「主品」判错了）：
  · `MC-US-WEB-IMG-baby-playard-bundles-PIC`            Baby Playard Bundles（游戏床，家居品线）
  · `MC-US-WEB-IMG-changing-table-for-baby-playard`     Changing Table for Baby Playard（换尿布台）
  · `MC-US-WEB-IMG-momcozy-milk-formula-dispenser`      Formula Dispenser（奶粉分装器）
  · `MC-US-YT-_2RMfsj2BLQ-IMG`                          Baby Playard 视频封面
  · `MC-US-YT-_xyLF4_AgAw-IMG`                          Cologne Baby Show 2026 展会视频封面（**不是产品**）

替换件**从同一批源里按三品类补挑**（独立站 products.json / YouTube 频道）：
  · 3 张独立站：2 台**婴儿监控器**（BM04 / BM03S 纯监控器，不带游戏床）＋ 1 台**清洗机**（DeepClean Lite）
  · 2 张社媒：1 条吸奶器视频封面（Wellness 1 IBCLC 实测）＋ 1 条清洗机视频封面（DeepClean Lite 用法）
  为什么这么配：原三品类分布是 23/5/**2**，**监控器严重偏少**（配额要 6 张）⇒ 这次优先补监控器。

顺带把 `产品线` 列按**素材本身**对齐（原先填的是采集器那套粗判：亚马逊 10 行吸奶器写成「清洗机」、
社媒 8 行写成「婴儿监控器」；按既定口径「推不出就留空、不许填错」）。

判据：替换件一律过 `collect_tupian35.cat_of()` 这道同一个闸（越界即拒），脚本自带 `--selftest` 反向对照。

用法：
  python3 replace_out_of_scope_images.py            # 干跑
  python3 replace_out_of_scope_images.py --apply
"""
import argparse, importlib.util, json, os, re, subprocess, sys, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
BACKUP = os.path.join(HERE, 'backup_pass_rerun_20261015-105156')
LARK = os.path.expanduser('~/.dsh/bin/lark-cli')
BASE, TABLE = 'RY2UbCRjXaeeWwscUPScVN5AnQc', 'tblavfbMDMeRsulo'
UA = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/122 Safari/537.36'}

#: 越界行 → 替换件（`kind`: site=独立站商品 / yt=YouTube 封面）
PLAN = {
    'MC-US-WEB-IMG-baby-playard-bundles-PIC':
        {'kind': 'site', 'handle': '5-inch-dual-mode-smart-baby-monitor-bm04'},
    'MC-US-WEB-IMG-changing-table-for-baby-playard':
        {'kind': 'site', 'handle': '5-5-inch-full-hd-smart-non-wifi-baby-monitorbm03s'},
    'MC-US-WEB-IMG-momcozy-milk-formula-dispenser':
        {'kind': 'site', 'handle': 'momcozy-deepclean-lite-baby-bottle-washer-and-sterilizer'},
    'MC-US-YT-_2RMfsj2BLQ-IMG':
        {'kind': 'yt', 'video': 'eVpzSeahaAQ'},
    'MC-US-YT-_xyLF4_AgAw-IMG':
        {'kind': 'yt', 'video': 'v_WYO8laaPI'},
}


def load_collector():
    spec = importlib.util.spec_from_file_location('ct', os.path.join(HERE, 'collect_tupian35.py'))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def fetch(u, timeout=40):
    return urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=timeout).read().decode('utf-8', 'ignore')


def site_item(handle):
    ps = json.loads(fetch('https://momcozy.com/products.json?limit=250'))['products']
    p = next((x for x in ps if x['handle'] == handle), None)
    if not p:
        raise SystemExit(f'✗ 独立站找不到 {handle}')
    return {'cid': f'MC-US-WEB-IMG-{handle}', 'image': p['images'][0]['src'], 'caption': p['title'],
            'url': f'https://momcozy.com/products/{handle}', 'src': '独立站',
            'blob': ' '.join([p.get('title', ''), p.get('product_type', ''), ' '.join(p.get('tags') or [])])}


def yt_item(vid):
    h = fetch(f'https://www.youtube.com/watch?v={vid}')
    m = re.search(r'"title":"(.*?)"', h)
    title = m.group(1).encode().decode('unicode_escape') if m else vid
    return {'cid': f'MC-US-YT-{vid}-IMG', 'image': f'https://i.ytimg.com/vi/{vid}/maxresdefault.jpg',
            'caption': f'{title}（YouTube 视频封面 · 社媒图片待补 IG/TikTok 原图）',
            'url': f'https://www.youtube.com/watch?v={vid}', 'src': '社媒', 'blob': title}


def render(it):
    return f"{it['image']}\n\n图注：{it['caption']}\n来源页（美国站）：{it['url']}"


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


def read_table():
    out = '/tmp/tbl_img_fix.ndjson'
    subprocess.run([LARK, 'base', '+record-list', '--base-token', BASE, '--table-id', TABLE,
                    '--limit', '2000', '--format', 'ndjson', '--output', out, '--overwrite',
                    '--profile', 'dsh-kb', '--as', 'bot'], capture_output=True, text=True, cwd='/tmp')
    return [json.loads(l) for l in open(out, encoding='utf-8') if l.strip()]


def build_patch(rows, cat_of, items):
    """判据只有一份：越界/找不到替换件一律拒（干跑与 selftest 共用）。"""
    patch, report = {}, []
    for r in rows:
        if plain(r.get('内容类型')) != '图片':
            continue
        cid = plain(r.get('内容 ID'))
        need = PLAN.get(cid)
        if need:
            it = items.get(cid)
            if not it:
                report.append((cid, '⚠️ 拿不到替换件 ⇒ 跳过（不编）'))
                continue
            k = cat_of(it['blob'])
            if k not in ('吸奶器', '清洗机', '婴儿监控器'):
                report.append((cid, f'✗ 替换件仍越界（判成 {k}）⇒ 拒'))
                continue
            patch[r['record_id']] = {'内容 ID': it['cid'], '采集数据': render(it), '产品线': k}
            report.append((cid, f"→ {it['cid']} ｜ {k} ｜ {it['caption'][:44]}"))
            continue
        # 其余行：只把 `产品线` 按素材对齐（推不出就留空 —— 本库既定口径，不许猜）
        k = cat_of(plain(r.get('采集数据'))[:400])
        want = k or ''
        if plain(r.get('产品线')).strip() != want:
            patch[r['record_id']] = {'产品线': want}
            report.append((cid, f"产品线 {plain(r.get('产品线')) or '（空）'} → {want or '（留空：推不出）'}"))
    return patch, report


def selftest(cat_of):
    """反向对照：合法的三类替换件不许被拒；越界替换件必须**精确**被拒。"""
    rows = [{'record_id': 'A', '内容类型': '图片', '内容 ID': 'MC-US-WEB-IMG-baby-playard-bundles-PIC',
             '采集数据': '', '产品线': ''}]
    good = {'MC-US-WEB-IMG-baby-playard-bundles-PIC':
            {'cid': 'MC-US-WEB-IMG-x', 'blob': 'Momcozy 5-Inch Dual-mode Smart Baby Monitor-BM04',
             'image': 'i', 'caption': 'c', 'url': 'u'}}
    bad = {'MC-US-WEB-IMG-baby-playard-bundles-PIC':
           {'cid': 'MC-US-WEB-IMG-y', 'blob': 'Baby Playard Bundles', 'image': 'i', 'caption': 'c', 'url': 'u'}}
    p1, r1 = build_patch(rows, cat_of, good)
    p2, r2 = build_patch(rows, cat_of, bad)
    ok1 = 'A' in p1 and p1['A'].get('产品线') == '婴儿监控器'
    ok2 = 'A' not in p2 and '拒' in r2[0][1]
    print(f"  {'✅' if ok1 else '✗'} 合法替换件（BM04 监控器）⇒ 接受并把产品线写成「婴儿监控器」")
    print(f"  {'✅' if ok2 else '✗'} 越界替换件（Playard）⇒ 精确拒绝：{r2[0][1]}")
    return 0 if (ok1 and ok2) else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true')
    ap.add_argument('--selftest', action='store_true')
    a = ap.parse_args()
    ct = load_collector()
    if a.selftest:
        return selftest(ct.cat_of)
    items = {}
    for old, need in PLAN.items():
        it = site_item(need['handle']) if need['kind'] == 'site' else yt_item(need['video'])
        items[old] = it
        print(f"替换件：{old}\n      → {it['cid']} ｜ {ct.cat_of(it['blob'])} ｜ {it['caption'][:60]}")
    # 采集器的闸门先过一遍（替换件必须全在三类里）
    ct.assert_in_scope([{'cid': v['cid'], 'caption': v['blob']} for v in items.values()])
    rows = read_table()
    patch, report = build_patch(rows, ct.cat_of, items)
    print(f"\n将写 {len(patch)} 行：")
    for cid, what in report:
        print(f"  {cid[:56]:56s} {what}")
    if not a.apply:
        print('（未加 --apply：什么都没写）')
        return 0
    if patch:
        os.makedirs(BACKUP, exist_ok=True)
        json.dump({r['record_id']: {k: plain(r.get(k)) for k in ('内容 ID', '采集数据', '产品线')}
                   for r in rows if r['record_id'] in patch},
                  open(os.path.join(BACKUP, 'img_before_scope_fix_20261015.json'), 'w', encoding='utf-8'),
                  ensure_ascii=False, indent=1)
        w = subprocess.run([LARK, 'base', '+record-batch-update', '--base-token', BASE, '--table-id', TABLE,
                            '--json', json.dumps({'update_records': patch}, ensure_ascii=False),
                            '--profile', 'dsh-kb', '--as', 'bot'], capture_output=True, text=True, cwd='/tmp')
        print(f"写入 {len(patch)} 行 ｜ rc={w.returncode} {str(w.stdout or '')[:90]} {str(w.stderr or '')[:150]}")
        if w.returncode != 0:
            return 3
    rows2 = read_table()
    ok = bad = 0
    for r in rows2:
        rid = r.get('record_id')
        if rid not in patch:
            continue
        for k, v in patch[rid].items():
            if plain(r.get(k)).strip() == str(v).strip():
                ok += 1
            else:
                bad += 1
                print(f'  ✗ 回读不一致 {rid} {k}')
    # 全表复核：图片 35 行**一条都不许越界**
    viol = [(plain(r.get('内容 ID')), ct.cat_of(plain(r.get('采集数据'))[:400]))
            for r in rows2 if plain(r.get('内容类型')) == '图片'
            and ct.cat_of(plain(r.get('采集数据'))[:400]) not in ('吸奶器', '清洗机', '婴儿监控器')]
    print(f"回读复核：一致 {ok} ｜ 不一致 {bad} ｜ 图片行仍越界 {len(viol)} {viol}")
    return 0 if (bad == 0 and not viol) else 4


if __name__ == '__main__':
    sys.exit(main())
