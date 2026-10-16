#!/usr/bin/env python3
"""重新采集「图片」35 条（Owner 2026-10-15）：链接1 独立站 15 / 链接2 亚马逊 10 / 链接3 社媒 10。

口径（与文案同一套来源比例 15/10/10；Owner 建议图片照文案比例采）：
  · 每个条目 = **图片直链** ＋ 图注 ＋ 来源页（与表里既有图片行的形态一致）；
  · 品类覆盖：吸奶器 / 清洗机 / 婴儿监控器；美国区；
  · 图片是媒材本身，**没有**文案那套「采成文章 / 900 字截断」的问题。

⚠️ 社媒图片（链接3）：Instagram / TikTok 帖图需要登录态，纯抓取拿不到 ——
   本脚本用 **Momcozy 官方 YouTube 视频封面**（美国频道）作为社媒图片，
   并在图注里**写明来源是视频封面**，不冒充 IG/TikTok 原图。

输出：out/tupian35.json
"""
import argparse, json, os, re, time, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'out')
UA = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/122 Safari/537.36',
      'Accept-Language': 'en-US,en;q=0.9'}
CATS = [('吸奶器', r'breast ?pump|pumping|wearable pump|\bpump\b'),
        ('清洗机', r'bottle washer|\bwasher\b|steriliz|deepclean|kleanpal'),
        ('婴儿监控器', r'baby monitor|\bmonitor\b|\bbm0\d')]
#: ★★ 2026-10-15 修（Owner：「必须是 吸奶器/清洗机/婴儿监控器，有 5 个不是的」）——
#   病灶：原先 `吸奶器` 的 pattern 里含 **`milk`**、`婴儿监控器` 里含 **`playard|bassinet`**：
#     · 「Momcozy Formula Dispenser Instant **Milk** Modulator」被判成吸奶器；
#     · 「Baby **Playard** Bundles」「Changing Table for Baby **Playard**」被判成婴儿监控器；
#   而 `collect_social` 还有一条「凑够 10 条就往下补」的兜底 ⇒ 游戏床视频、科隆展会视频被补进来。
#   实测 35 张里 **5 张越界**（3 独立站 + 2 社媒）。
#   ⇒ 现在两道闸：**关键词收紧** ＋ 下面 `EXCLUDE`（主品不是这三类的，一律不要）＋ 落盘前 `assert_in_scope`。
EXCLUDE = (r'playard|bassinet|changing table|stroller|sleep sack|swaddle|sound machine|belly band|'
           r'storage bags|formula dispenser|bottle warmer|bottle cooler|detergent|\bwipes?\b|'
           r'cologne|baby show|recap|giveaway|deals?\b')
IN_CAT_WORDS = r'breast ?pump|pumping|wearable pump|\bpump\b|washer|steriliz|deepclean|kleanpal|monitor|bm0\d'


def fetch(u, timeout=40):
    return urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=timeout).read().decode('utf-8', 'ignore')


def cat_of(s):
    """★ 主品归类：**先按 EXCLUDE 排除**（成套里带一个在类产品的不算越界），再按收紧后的关键词。

    判据自证在 `--selftest`：干净样本不红；注入 `playard` / `formula dispenser` 必须精确变红。
    """
    t = (s or '').lower()
    if re.search(EXCLUDE, t) and not re.search(IN_CAT_WORDS, t):
        return None
    # ★ 取**最先出现**的那一类（不是列表顺序）：一条标题里可能同时出现两类词，例如
    #   「How to Use Momcozy DeepClean **Bottle Washer** for Bottles and **Pumps**」——
    #   按列表顺序会判成"吸奶器"（错，这条讲的是清洗机）。实测这类混排有 1 条。
    best = None
    for name, pat in CATS:
        m = re.search(pat, t)
        if m and (best is None or m.start() < best[0]):
            best = (m.start(), name)
    return best[1] if best else None


def collect_site(n=15):
    ps = json.loads(fetch('https://momcozy.com/products.json?limit=250'))['products']
    want = {'吸奶器': 8, '清洗机': 3, '婴儿监控器': 4}
    out = []
    for p in ps:
        k = cat_of(p.get('title', '') + ' ' + p.get('product_type', '') + ' ' + ' '.join(p.get('tags') or []))
        if not k or not p.get('images'):
            continue
        if len([x for x in out if x['cat'] == k]) >= want.get(k, 0):
            continue
        img = p['images'][0]['src']
        out.append({'cat': k, 'src': '独立站', 'cid': f'MC-US-WEB-IMG-{p["handle"]}',
                    'image': img, 'caption': p['title'],
                    'url': f'https://momcozy.com/products/{p["handle"]}', 'kind': 'product'})
        if len(out) >= n:
            break
    return out[:n]


def collect_amazon(asins, n=10):
    out = []
    for a in asins:
        if len(out) >= n:
            break
        try:
            h = fetch(f'https://www.amazon.com/dp/{a["asin"]}')
        except Exception as e:
            print(f'   ⚠️ {a["asin"]} 抓取失败 {type(e).__name__}')
            continue
        t = re.search(r'id="productTitle"[^>]*>(.*?)</span>', h, re.S)
        title = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', t.group(1))).strip() if t else (a.get('title') or '')
        img = None
        m = re.search(r'"hiRes":"(https://[^"]+)"', h) or re.search(r'id="landingImage"[^>]*src="(https://[^"]+)"', h)
        if m:
            img = m.group(1).replace('\\u0026', '&')
        if not img:
            img = a.get('img')
        if not img or not title:
            print(f'   ⚠️ {a["asin"]} 没取到主图/标题，跳过')
            continue
        out.append({'cat': cat_of(title) or a.get('pline') or '—', 'src': '亚马逊',
                    'cid': f'MC-US-AMZ-{a["asin"]}-IMG', 'image': img, 'caption': title,
                    'url': f'https://www.amazon.com/dp/{a["asin"]}', 'kind': 'listing'})
        print(f'   ✅ {a["asin"]} 主图 {img[:70]}…')
        time.sleep(1.2)
    return out


def collect_social(n=10):
    cand = json.load(open(os.path.join(HERE, 'raw', 'yt_resolved.json'), encoding='utf-8'))
    # ★ 2026-10-15：把**频道 RSS 最新 15 条**并进候选池 —— 池子里一条监控器视频都没有，
    #   而新片里常有清洗机/吸奶器（实测 RSS 带来 `v_WYO8laaPI` DeepClean Lite 清洗机、
    #   `iV9POYKPrxs` 可穿戴吸奶器）⇒ 先扩池，才可能守住「一条都不能越界」。
    try:
        rss = fetch('https://www.youtube.com/feeds/videos.xml?channel_id=UClbPQanKwegT0tMBxSoBCZA')
        have = {v.get('videoId') for v in cand}
        for vid, title in zip(re.findall(r'<yt:videoId>(.*?)</yt:videoId>', rss),
                              re.findall(r'<media:title>(.*?)</media:title>', rss)):
            if vid not in have:
                cand.append({'videoId': vid, 'title': title.replace('&amp;', '&')})
        print(f'   RSS 并入后候选 {len(cand)} 条')
    except Exception as e:
        print(f'   ⚠️ RSS 取不到（{type(e).__name__}）⇒ 只用既有池')
    want = {'吸奶器': 5, '清洗机': 3, '婴儿监控器': 2}
    picked = []
    for cat, k in want.items():
        picked += [v for v in cand if cat_of(v.get('title', '')) == cat and v not in picked][:k]
    # ★★ 2026-10-15：**删掉那条「凑够 n 条就往下补」的兜底** —— 它正是游戏床视频、科隆展会视频
    #   混进来的路径。品类不够就**少几条**（宁少不滥），并把差额大声打出来让人补源。
    short = n - len(picked)
    if short > 0:
        print(f'   ⚠️ 三类视频只凑到 {len(picked)}/{n} 条（差 {short}）⇒ **不补品类外**，本批社媒就少这几条')
    out = []
    for v in picked[:n]:
        out.append({'cat': cat_of(v.get('title', '')), 'src': '社媒',
                    'cid': f'MC-US-YT-{v["videoId"]}-IMG',
                    'image': f'https://i.ytimg.com/vi/{v["videoId"]}/maxresdefault.jpg',
                    'caption': f'{v.get("title", "")}（YouTube 视频封面 · 社媒图片待补 IG/TikTok 原图）',
                    'url': f'https://www.youtube.com/watch?v={v["videoId"]}', 'kind': 'social-thumb'})
    return out


def in_scope_violations(items):
    """越界条目（主品不是吸奶器/清洗机/婴儿监控器）—— 判据本体，落盘前闸门与 selftest 共用。"""
    return [(it.get('cid'), cat_of(it.get('caption', '')) or '—') for it in items
            if cat_of(it.get('caption', '')) not in ('吸奶器', '清洗机', '婴儿监控器')]


def assert_in_scope(items):
    """★ 落盘前闸门（2026-10-15 加）：任何一条越界 ⇒ **拒写并退非零**。

    为什么要有它：这次是**表里已经躺了 5 张越界图**、跑批都跑完了才发现；
    当时采集器没有任何东西会红。判据自证：`--selftest`（正例不红 ＋ 注入 playard 必红）。
    """
    bad = in_scope_violations(items)
    if bad:
        print('✗ 有越界素材（主品不在 吸奶器/清洗机/婴儿监控器 三类里）⇒ 拒绝落盘：')
        for cid, got in bad:
            print(f'   · {cid} ⇒ 判成 {got}')
        raise SystemExit(6)


def selftest():
    """反向对照：三类样本不许红；注入 playard / formula dispenser 必须精确变红。"""
    ok_items = [{'cid': 'A', 'caption': 'Momcozy V2 Pro Wearable Breast Pump'},
                {'cid': 'B', 'caption': 'Momcozy DeepClean D8 Bottle Washer, Sterilizer & Dryer'},
                {'cid': 'C', 'caption': 'Momcozy 5-Inch Dual-mode Smart Baby Monitor-BM04'}]
    assert_in_scope(ok_items)
    cases = [
        ('playard（旧口径会判成"婴儿监控器"）', 'Baby Playard Bundles'),
        ('formula dispenser（旧口径会判成"吸奶器"）', 'Momcozy Formula Dispenser Instant Milk Modulator'),
        ('展会视频', 'Come With Us to the Cologne Baby Show 2026 | Baby Products & Trends'),
    ]
    red = 0
    for name, cap in cases:
        try:
            assert_in_scope([{'cid': 'X', 'caption': cap}])
        except SystemExit as e:
            red += 1
            print(f'  ✅ 注入「{name}」⇒ 精确变红（exit {e.code}）')
        else:
            print(f'  ✗ 注入「{name}」却没红（判据恒绿）')
    print(f'  ✅ 三类干净样本不红 ｜ 注入 {red}/{len(cases)} 全部变红')
    return 0 if red == len(cases) else 1


def render(it):
    return (f"{it['image']}\n\n图注：{it['caption']}\n来源页（美国站）：{it['url']}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--json', default=os.path.join(OUT, 'tupian35.json'))
    ap.add_argument('--selftest', action='store_true')
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    print('① 独立站（链接1）…'); site = collect_site(15)
    print(f'   取到 {len(site)} 条 ｜ 品类 {dict((k, sum(1 for x in site if x["cat"] == k)) for k in ("吸奶器","清洗机","婴儿监控器"))}')
    print('② 亚马逊（链接2）…')
    raw = json.load(open(os.path.join(HERE, '..', '采集-20261013b', 'raw', 'amazon_rows.json'), encoding='utf-8'))
    amz = collect_amazon(raw, 10)
    print(f'   取到 {len(amz)} 条')
    print('③ 社媒（链接3 · YouTube 封面）…'); soc = collect_social(10)
    print(f'   取到 {len(soc)} 条')
    items = site + amz + soc
    for it in items:
        it['采集数据'] = render(it)
    assert_in_scope(items)                   # ★ 落盘前闸门：有越界 ⇒ 拒写、退 6
    json.dump(items, open(a.json, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(f"\n合计 {len(items)} 条（独立站 {len(site)} / 亚马逊 {len(amz)} / 社媒 {len(soc)}）")
    print(f"→ {a.json}")


if __name__ == '__main__':
    main()