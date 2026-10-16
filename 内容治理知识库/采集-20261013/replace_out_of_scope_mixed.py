#!/usr/bin/env python3
"""换掉 **11 行越界素材**（Owner 2026-10-15：「同意，马上执行」）—— 文案 9 ／ 视频 1 ／ 图片 1。

越界行（按**标题/商品名**判，正文不算；判据 = `collect_tupian35.cat_of`，与图片那 5 张同一把尺子）：
  文案 · `breastmilk-storage-bags`（储奶袋）、`baby-bottle-cooler`（母乳冷却器）、`best-nipple-cream`（乳头霜）、
        `breast-milk-collector`（集乳器）、`100-natural-nipple-cream-…`（乳头霜）、`baby-playard-bundles-WEN`（游戏床）、
        `playard-playmat-giraffe-bundle`（游戏床+爬行垫）、`MC-US-YT-_2RMfsj2BLQ`（游戏床视频文案）、
        `MC-US-YT-_xyLF4_AgAw`（科隆展会视频文案）
  视频 · `MC-US-YT-cFMhzoIYjI0`（母乳喂养支持视频，非产品）
  图片 · `momcozy-portable-breast-pump-cleaner-spray`（吸奶器配件清洁喷雾 —— 既不是吸奶器本体、也不是清洗机；Owner 裁定算越界）

替换来源 = **同一批源**：独立站（collections/products）→ 文案/图片；YouTube 频道（既有池 + RSS）→ 文案/视频。
**优先补监控器**（三品类里最缺：全表 吸奶器 44 ／ 清洗机 16 ／ 婴儿监控器 10）。
素材形态**照原样**（文案 = 标题 + 正文 + 来源页；视频 = 标题 + 链接 + 缩略图 + 发布日；图片 = 直链 + 图注 + 来源页）。

用法：
  python3 replace_out_of_scope_mixed.py            # 干跑
  python3 replace_out_of_scope_mixed.py --apply
"""
import argparse, importlib.util, json, os, re, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
BACKUP = os.path.join(HERE, 'backup_pass_rerun_20261015-105156')
LARK = os.path.expanduser('~/.dsh/bin/lark-cli')
BASE, TABLE = 'RY2UbCRjXaeeWwscUPScVN5AnQc', 'tblavfbMDMeRsulo'
CHANNEL = 'UClbPQanKwegT0tMBxSoBCZA'

#: 越界行（内容 ID）→ 用什么补
PLAN = {
    'MC-US-WEB-COL-breastmilk-storage-bags': 'site_copy',
    'MC-US-WEB-COL-baby-bottle-cooler': 'site_copy',
    'MC-US-WEB-COL-best-nipple-cream': 'site_copy',
    'MC-US-WEB-COL-breast-milk-collector': 'site_copy',
    'MC-US-WEB-IMG-100-natural-nipple-cream-for-breastfeeding-lanolin-free': 'site_copy',
    'MC-US-WEB-IMG-baby-playard-bundles-WEN': 'site_copy',
    'MC-US-WEB-IMG-playard-playmat-giraffe-bundle': 'site_copy',
    'MC-US-YT-_2RMfsj2BLQ': 'yt_copy',
    'MC-US-YT-_xyLF4_AgAw': 'yt_copy',
    'MC-US-YT-cFMhzoIYjI0': 'yt_video',
    'MC-US-WEB-IMG-momcozy-portable-breast-pump-cleaner-spray': 'site_image',
}
CAT_RANK = {'婴儿监控器': 0, '清洗机': 1, '吸奶器': 2}      # 越缺越优先


def load(mod, path):
    spec = importlib.util.spec_from_file_location(mod, os.path.join(HERE, path))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


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
    out = '/tmp/tbl_mixed.ndjson'
    subprocess.run([LARK, 'base', '+record-list', '--base-token', BASE, '--table-id', TABLE,
                    '--limit', '2000', '--format', 'ndjson', '--output', out, '--overwrite',
                    '--profile', 'dsh-kb', '--as', 'bot'], capture_output=True, text=True, cwd='/tmp')
    return [json.loads(l) for l in open(out, encoding='utf-8') if l.strip()]


def site_pool(w, ct, used):
    """独立站候选：collections（页面文案）+ products（文案 / 图片两用）。返回按「越缺越前」排序。"""
    cs = json.loads(ct.fetch('https://momcozy.com/collections.json?limit=250'))['collections']
    ps = json.loads(ct.fetch('https://momcozy.com/products.json?limit=250'))['products']
    out = []
    for c in cs:
        k = ct.cat_of(' '.join([c.get('title', ''), c.get('handle', '')]))
        body = w.clean_paras(c.get('description'))
        if k in CAT_RANK and len(body) >= 200 and f"MC-US-WEB-COL-{c['handle']}" not in used:
            out.append({'kind': 'site_copy', 'cat': k, 'cid': f"MC-US-WEB-COL-{c['handle']}",
                        'title': c['title'], 'body': w.clip(body),
                        'url': f"https://momcozy.com/collections/{c['handle']}"})
    for p in ps:
        blob = ' '.join([p.get('title', ''), p.get('product_type', ''), ' '.join(p.get('tags') or [])])
        k = ct.cat_of(blob)
        cid_i = f"MC-US-WEB-IMG-{p['handle']}"
        if k not in CAT_RANK or not p.get('images'):
            continue
        if cid_i not in used and p.get('body_html'):
            body = w.clean_paras(p['body_html'])
            if len(body) >= 200:
                out.append({'kind': 'site_copy', 'cat': k, 'cid': cid_i, 'title': p['title'], 'body': w.clip(body),
                            'url': f"https://momcozy.com/products/{p['handle']}"})
        if cid_i not in used:
            out.append({'kind': 'site_image', 'cat': k, 'cid': cid_i, 'title': p['title'],
                        'image': p['images'][0]['src'], 'url': f"https://momcozy.com/products/{p['handle']}"})
    out.sort(key=lambda x: CAT_RANK[x['cat']])
    return out


def yt_pool(w, ct, used):
    """YouTube 候选：既有解析池 + 频道 RSS（标题行）。文案用描述、视频用标题+链接+缩略图+发布日。"""
    cand = json.load(open(os.path.join(HERE, 'raw', 'yt_resolved.json'), encoding='utf-8'))
    rss = ''
    for attempt in range(3):
        try:
            rss = ct.fetch(f'https://www.youtube.com/feeds/videos.xml?channel_id={CHANNEL}')
            break
        except Exception as e:
            print(f'   ⚠️ RSS 第 {attempt+1} 次取不到（{type(e).__name__}）')
    try:
        have = {v.get('videoId') for v in cand}
        for vid, t in zip(re.findall(r'<yt:videoId>(.*?)</yt:videoId>', rss),
                          re.findall(r'<media:title>(.*?)</media:title>', rss)):
            if vid not in have:
                cand.append({'videoId': vid, 'title': t.replace('&amp;', '&')})
    except Exception as e:
        print(f'   ⚠️ RSS 取不到（{type(e).__name__}）')
    out = []
    for v in cand:
        vid, title = v.get('videoId'), v.get('title', '')
        k = ct.cat_of(title)
        if k not in CAT_RANK:
            continue
        if f'MC-US-YT-{vid}' not in used:
            out.append({'kind': 'yt_copy', 'cat': k, 'cid': f'MC-US-YT-{vid}-WEN', 'video': vid, 'title': title})
        if f'MC-US-YT-{vid}' not in used:
            out.append({'kind': 'yt_video', 'cat': k, 'cid': f'MC-US-YT-{vid}', 'video': vid, 'title': title})
    out.sort(key=lambda x: CAT_RANK[x['cat']])
    return out


def amz_pool(w, ct, used):
    """亚马逊候选（标题 + 要点 = listing 文案）。**只在 YouTube 侧凑不出同类时才用** ——
    社媒那条链的美国账号只有 YouTube 一路（IG/TikTok 要登录态），2026-10-15 实测频道可用的
    三品类新片只剩 2 条 ⇒ 有 2 行必须换个源，这里用它们同在「链接2」的那批 ASIN。"""
    raw = json.load(open(os.path.join(HERE, '..', '采集-20261013b', 'raw', 'amazon_rows.json'), encoding='utf-8'))
    out = []
    for a in raw:
        cid = f"MC-US-AMZ-{a['asin']}"
        k = ct.cat_of(a.get('title', ''))
        if k in CAT_RANK and cid not in used and a.get('bullets'):
            out.append({'kind': 'amz_copy', 'cat': k, 'cid': cid, 'title': a['title'],
                        'body': w.clip('\n'.join(a['bullets'])), 'url': f"https://www.amazon.com/dp/{a['asin']}",
                        'src': '亚马逊'})
    out.sort(key=lambda x: CAT_RANK[x['cat']])
    return out


def build_material(item, w, ct):
    """素材形态**照原样**（与表里既有同类型行一致）。"""
    if item['kind'] == 'amz_copy':
        return w.render(item)[:w.TOTAL_CAP].rstrip()
    if item['kind'] == 'site_copy':
        return w.render({'title': item['title'], 'body': item['body'], 'url': item['url'], 'src': '独立站'})[:w.TOTAL_CAP].rstrip()
    if item['kind'] == 'site_image':
        return f"{item['image']}\n\n图注：{item['title']}\n来源页（美国站）：{item['url']}"
    if item['kind'] == 'yt_copy':
        h = ct.fetch(f"https://www.youtube.com/watch?v={item['video']}")
        m = re.search(r'"shortDescription":"(.*?)","isCrawlable"', h, re.S)
        desc = w.json_unescape(m.group(1)) if m else ''
        body = w.clean_paras(desc) if desc.strip() else ''
        return w.render({'title': item['title'], 'body': w.clip(body), 'url': f"https://www.youtube.com/watch?v={item['video']}", 'src': '社媒'})[:w.TOTAL_CAP].rstrip()
    # yt_video：标题 / 链接 / 缩略图 / 发布日（与既有视频行同形）
    h = ct.fetch(f"https://www.youtube.com/watch?v={item['video']}")
    d = re.search(r'"publishDate":"(.*?)"', h) or re.search(r'itemprop="datePublished" content="(.*?)"', h)
    return (f"{item['title']}\nhttps://www.youtube.com/watch?v={item['video']}\n"
            f"缩略图：https://i.ytimg.com/vi/{item['video']}/hqdefault.jpg\n"
            f"发布：{d.group(1) if d else '（未取到）'}")


def selftest(ct):
    """反向对照：三品类候选接受；越界候选（Playard / 储奶袋）精确拒绝。"""
    ok = [{'kind': 'site_copy', 'cat': ct.cat_of('Momcozy 5-Inch Dual-mode Smart Baby Monitor-BM04')},
          {'kind': 'site_image', 'cat': ct.cat_of('Momcozy DeepClean D8 Bottle Washer, Sterilizer & Dryer')}]
    bad = [ct.cat_of('Baby Playard Bundles'), ct.cat_of('Momcozy Formula Dispenser Instant Milk Modulator'),
           ct.cat_of('Momcozy Breastmilk Storage Bags, 200PCS Value Pack')]
    good = all(x['cat'] in CAT_RANK for x in ok)
    denied = all(b not in CAT_RANK for b in bad)
    print(f"  {'✅' if good else '✗'} 三品类候选 ⇒ 接受（监控器 / 清洗机）")
    print(f"  {'✅' if denied else '✗'} 越界候选（Playard／奶粉分装器／储奶袋）⇒ 全部判 None、不进候选：{bad}")
    return 0 if (good and denied) else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true')
    ap.add_argument('--selftest', action='store_true')
    a = ap.parse_args()
    ct = load('ct', 'collect_tupian35.py')          # ★ 判据：严格那把（与图片同一把尺子）
    w = load('cw', 'collect_wenan35.py')
    if a.selftest:
        return selftest(ct)
    rows = read_table()

    def base_id(cid):
        """去掉类型前缀/后缀后的**源标识** —— 去重要按源，不按整 ID：

        ① 同一条视频写成 `MC-US-YT-x`、`MC-US-YT-x-WEN`、`MC-US-YT-x-IMG` 是**三份同样的素材**
           （2026-10-15 干跑撞过：同一视频被补进 视频行 + 文案行，而它早就是某图片行的源）；
        ② 独立站同一个商品有两个 handle（`5-inch-dual-mode-…` 与 `momcozy-5-inch-dual-mode-…`）
           —— 2026-10-15 干跑也撞过（同一台 BM04 监控器被补进文案行，而已有图片行就是它）。
        所以：去前缀、去类型后缀、去前导 `momcozy-`，再小写比对。"""
        s2 = re.sub(r'^MC-US-(WEB-IMG|WEB-COL|AMZ|YT)-', '', str(cid).strip())
        s2 = re.sub(r'-(WEN|IMG)$', '', s2)
        s2 = re.sub(r'^momcozy-', '', s2)
        return s2.lower()

    used = {base_id(plain(r.get('内容 ID'))) for r in rows}
    sp, yp = site_pool(w, ct, used), yt_pool(w, ct, used)
    ap_ = amz_pool(w, ct, used)
    print(f'候选：独立站 {len(sp)} 条（文案 {sum(1 for x in sp if x["kind"]=="site_copy")} / 图片 {sum(1 for x in sp if x["kind"]=="site_image")}）'
          f'｜YouTube {len(yp)} 条（文案 {sum(1 for x in yp if x["kind"]=="yt_copy")} / 视频 {sum(1 for x in yp if x["kind"]=="yt_video")}）')
    plan_rows = [(r, PLAN[plain(r.get('内容 ID'))]) for r in rows if plain(r.get('内容 ID')) in PLAN]
    print(f'待换 {len(plan_rows)} 行')
    patch, chosen = {}, []
    for r, kind in plan_rows:
        cid = plain(r.get('内容 ID'))
        pool = sp if kind.startswith('site') else yp
        item = next((x for x in pool if x['kind'] == kind and base_id(x['cid']) not in used), None)
        if not item and kind == 'yt_copy':
            item = next((x for x in ap_ if base_id(x['cid']) not in used), None)
            if item:
                print(f'  ↪ {cid}：YouTube 侧没有可用的三品类新片 ⇒ 改用**亚马逊 listing 文案**（{item["cid"]}）')
        if not item:
            print(f'  ⚠️ {cid} 找不到同类候选 ⇒ 跳过（不编）')
            continue
        used.add(base_id(item['cid']))
        mat = build_material(item, w, ct)
        k = ct.cat_of(mat[:600])
        if k not in CAT_RANK:
            print(f'  ✗ {cid} 候选素材越界（判成 {k}）⇒ 拒：{item["cid"]}')
            continue
        patch[r['record_id']] = {'内容 ID': item['cid'], '采集数据': mat, '产品线': k}
        chosen.append((cid, item['cid'], k, plain(r.get('内容类型')), item['title'][:46]))
    print(f'\n将写 {len(patch)} 行：')
    for old, new, k, t, title in chosen:
        print(f'  [{t}] {old[:44]:44s} → {new[:52]:52s} {k:6s} {title}')
    if not a.apply:
        print('（未加 --apply：什么都没写）')
        return 0
    if patch:
        os.makedirs(BACKUP, exist_ok=True)
        json.dump({r['record_id']: {kk: plain(r.get(kk)) for kk in ('内容 ID', '采集数据', '产品线', 'Agent 结论', '问题数量', '问题分类汇总')}
                   for r in rows if r['record_id'] in patch},
                  open(os.path.join(BACKUP, 'mixed_before_scope_fix_20261015.json'), 'w', encoding='utf-8'),
                  ensure_ascii=False, indent=1)
        w2 = subprocess.run([LARK, 'base', '+record-batch-update', '--base-token', BASE, '--table-id', TABLE,
                             '--json', json.dumps({'update_records': patch}, ensure_ascii=False),
                             '--profile', 'dsh-kb', '--as', 'bot'], capture_output=True, text=True, cwd='/tmp')
        print(f"写入 {len(patch)} 行 ｜ rc={w2.returncode} {str(w2.stdout or '')[:80]} {str(w2.stderr or '')[:120]}")
        if w2.returncode != 0:
            return 3
    rows2 = read_table()
    ok = bad = 0
    for r in rows2:
        rid = r.get('record_id')
        if rid not in patch:
            continue
        for kk, v in patch[rid].items():
            if plain(r.get(kk)).strip() == str(v).strip():
                ok += 1
            else:
                bad += 1
                print(f'  ✗ 回读不一致 {rid} {kk}')
    viol = [(plain(r.get('内容 ID')), plain(r.get('内容类型')), ct.cat_of(plain(r.get('采集数据'))[:600]))
            for r in rows2 if ct.cat_of(plain(r.get('采集数据'))[:600]) not in CAT_RANK]
    print(f"回读：一致 {ok} ｜ 不一致 {bad} ｜ 全表仍越界 {len(viol)} 行 {viol}")
    return 0 if (bad == 0 and not viol) else 4


if __name__ == '__main__':
    sys.exit(main())
