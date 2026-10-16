#!/usr/bin/env python3
"""重新采集「文案」35 条（Owner 2026-10-15）：链接1 独立站 15 / 链接2 亚马逊 10 / 链接3 社媒 10。

口径（Owner 定）：
  · **不审长文、不增加长度** —— 每条与「第一行」同量级（正文 ≤900 字），只保留文案本体；
  · **保留段落**（旧采集把短行丢掉再拼成一整块 ⇒ 报告说「第 4 段」在表里定位不到）；
  · 每个条目 = 标题 ＋ 正文 ＋ 来源行（美国站）；
  · 品类覆盖：吸奶器 / 清洗机 / 婴儿监控器；美国区。

输出：out/wenan35.json（可直接写表）＋ 屏幕清单。
用法：python3 collect_wenan35.py [--json out/wenan35.json]
"""
import argparse, html, json, os, re, time, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'out')
UA = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/122 Safari/537.36',
      'Accept-Language': 'en-US,en;q=0.9'}
LIMIT = 900          # 正文上限
TOTAL_CAP = 927      # 整条「采集数据」上限 = 第一行长度（Owner：不要增加长度）

CATS = [('吸奶器', r'breast pump|pumping|milk|nipple'), ('清洗机', r'washer|steriliz|clean|dryer'),
        ('婴儿监控器', r'baby monitor|monitor|playard|bassinet')]


def fetch(u, timeout=40):
    return urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=timeout).read().decode('utf-8', 'ignore')


def cat_of(s):
    s = (s or '').lower()
    for name, pat in CATS:
        if re.search(pat, s):
            return name
    return None


def clean_paras(b):
    """清洗 HTML，但**保留段落与要点**（旧采集 `paras(minlen=45)` 把短行整行丢掉，段落边界就没了）。"""
    b = re.sub(r'<(script|style)[^>]*>.*?</\1>', '', b or '', flags=re.S | re.I)
    b = re.sub(r'<li[^>]*>', '\n', b, flags=re.I)
    b = re.sub(r'</(p|div|h[1-6]|li|tr|table|br)>', '\n', b, flags=re.I)
    t = html.unescape(re.sub(r'<[^>]+>', ' ', b))
    lines = [re.sub(r'[ \t]+', ' ', x).strip() for x in t.split('\n')]
    out, buf = [], ''
    for ln in lines:
        if not ln:
            continue
        # 中文/短句行不并段；英文长行按 60 字并成一段（与旧样式一致，但不丢任何行）
        if re.search(r'[\u4e00-\u9fff]', ln) or len(ln) < 60:
            if buf:
                out.append(buf); buf = ''
            out.append(ln)
        else:
            buf = (buf + ' ' + ln).strip() if buf else ln
            if len(buf) >= 60:
                out.append(buf); buf = ''
    if buf:
        out.append(buf)
    return '\n'.join(out)


def clip(s, limit=LIMIT):
    s = s.strip()
    if len(s) <= limit:
        return s
    cut = s[:limit]
    # 尽量断在句末/段末，避免半截词（旧采集断在 'gettin' 这种）
    for sep in ('\n', '. ', '! ', '? '):
        i = cut.rfind(sep)
        if i > limit * 0.6:
            return cut[:i + len(sep)].strip()
    return cut.strip()


def collect_site():
    cs = json.loads(fetch('https://momcozy.com/collections.json?limit=250'))['collections']
    ps = json.loads(fetch('https://momcozy.com/products.json?limit=250'))['products']
    pool = []
    for c in cs:
        body = clean_paras(c.get('description'))
        k = cat_of(c.get('title', '') + ' ' + c.get('handle', ''))
        if k and 200 <= len(body):
            pool.append({'cat': k, 'title': c['title'], 'body': clip(body),
                         'url': f"https://momcozy.com/collections/{c['handle']}",
                         'cid': f"MC-US-WEB-COL-{c['handle']}", 'kind': 'collection'})
    for p in ps:
        body = clean_paras(p.get('body_html'))
        k = cat_of(p.get('title', '') + ' ' + p.get('product_type', '') + ' ' + ' '.join(p.get('tags') or []))
        if k and 200 <= len(body):
            pool.append({'cat': k, 'title': p['title'], 'body': clip(body),
                         'url': f"https://momcozy.com/products/{p['handle']}",
                         'cid': f"MC-US-WEB-IMG-{p['handle']}", 'kind': 'product'})
    # 品类配额：吸奶器 7 / 清洗机 4 / 监控器 4；同品类先 collection（页面文案）后 product
    want = {'吸奶器': 8, '清洗机': 2, '婴儿监控器': 5}
    pick, used = [], set()
    for cat, n in want.items():
        cand = [x for x in pool if x['cat'] == cat]
        cand.sort(key=lambda x: (x['kind'] != 'collection', len(x['body'])))
        for x in cand:
            if len([y for y in pick if y['cat'] == cat]) >= n:
                break
            if x['url'] in used:
                continue
            used.add(x['url']); pick.append({**x, 'src': '独立站'})
    return pick


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
        title = html.unescape(re.sub(r'\s+', ' ', t.group(1))).strip() if t else (a.get('title') or '')
        blk = re.search(r'id="feature-bullets"(.*?)</div>\s*</div>', h, re.S)
        bullets = []
        if blk:
            for m in re.finditer(r'<span class="a-list-item">(.*?)</span>', blk.group(1), re.S):
                x = html.unescape(re.sub(r'<[^>]+>', ' ', m.group(1)))
                x = re.sub(r'\s+', ' ', x).strip()
                if len(x) >= 25 and not x.lower().startswith(('make sure', 'see more')):
                    bullets.append(x)
        if not bullets:                      # 回落本地已抓件（并标注）
            bullets = [re.sub(r'\s+', ' ', html.unescape(b)).strip() for b in (a.get('bullets') or [])]
        if not title or not bullets:
            print(f'   ⚠️ {a["asin"]} 页面里没有标题/要点，跳过')
            continue
        k = cat_of(title)
        out.append({'cat': k or a.get('pline') or '—', 'title': title, 'body': clip('\n'.join(bullets)),
                    'url': f'https://www.amazon.com/dp/{a["asin"]}', 'cid': f'MC-US-AMZ-{a["asin"]}',
                    'kind': 'listing', 'src': '亚马逊', 'n_bullets': len(bullets)})
        print(f'   ✅ {a["asin"]} ｜ 标题 {len(title)} 字 ｜ 要点 {len(bullets)} 条 '
              f'｜ 正文裁到 {len(out[-1]["body"])} 字')
        time.sleep(1.2)
    return out


def json_unescape(raw):
    """把 HTML 里 `"shortDescription":"…"` 的**字面量正文**反转义成真字符串。

    ★ 为什么不能再用 `unicode_escape`：那个编解码器把 `str.encode()`（UTF-8 字节）按 **latin-1**
      读回去 ⇒ 任何非 ASCII 字符都会变成 `â\\x80\\x94` 这种双编码乱码。
      2026-10-15 实测：10 条社媒文案里 **9 条**中招并已写进飞书表。
    """
    try:
        return json.loads('"' + raw + '"')
    except Exception:
        try:                       # 兜底：字面量里有裸控制字符等非法 JSON 时，逐段退化为原文
            return raw.encode('utf-8').decode('utf-8')
        except Exception:
            return raw


def collect_social(n=10):
    """链接3 社媒：Momcozy 官方 YouTube（美国）。**按品类挑**，再抓每条的视频描述（=社媒文案）。"""
    cand = json.load(open(os.path.join(HERE, 'raw', 'yt_resolved.json'), encoding='utf-8'))
    tagged = []
    for v in cand:
        k = cat_of(v.get('title', ''))
        tagged.append({**v, 'cat': k or '—'})      # 品类不命中的也留着 —— 用来补足 10 条
    # 品类配额：吸奶器 5 / 清洗机 3 / 监控器 2（按可用量）
    want = {'吸奶器': 5, '清洗机': 3, '婴儿监控器': 2}
    pick = []
    for cat, k in want.items():
        for v in [x for x in tagged if x['cat'] == cat][:k]:
            pick.append(v)
    print(f'   品类命中 {sum(1 for x in tagged if x["cat"] != "—")} / {len(tagged)} 条')
    for v in tagged:                                  # 不足就按顺序补
        if len(pick) >= n:
            break
        if v not in pick:
            pick.append(v)
    pick = pick[:n]
    print(f'   候选 {len(tagged)} 条（按品类标注）⇒ 挑 {len(pick)} 条')
    out = []
    for v in pick:
        title, desc = v.get('title', ''), ''
        try:
            h = fetch(f"https://www.youtube.com/watch?v={v['videoId']}")
            m = re.search(r'"shortDescription":"(.*?)","isCrawlable"', h, re.S)
            if m:
                # ★ 2026-10-15 修：原先 `.encode().decode('unicode_escape')` —— 那一手会把
                #   **非 ASCII 的 UTF-8 字节按 latin-1 解读**，正文里的破折号/引号/emoji 全部变成
                #   `â\x80\x94` 这种双编码乱码（实测 9/10 条社媒文案中招，写进了表里）。
                #   正确做法 = 按 **JSON 字符串字面量**反转义（`\n` / `\"` / `\u2014` 都对，
                #   已经是 UTF-8 的字符原样保留）。
                desc = json_unescape(m.group(1))
        except Exception as e:
            print(f'   ⚠️ {v["videoId"]} 描述抓取失败 {type(e).__name__}')
        body = clean_paras(desc) if desc.strip() else ''
        out.append({'cat': v['cat'], 'title': title, 'body': clip(body),
                    'url': f"https://www.youtube.com/watch?v={v['videoId']}",
                    'cid': f"MC-US-YT-{v['videoId']}", 'kind': 'social', 'src': '社媒',
                    'n_desc': len(body)})
        time.sleep(0.8)
    return out


def render(it):
    body = it['body'].strip()
    tail = f"\n\n—— 来源（美国站）：{it['url']}" if it['src'] != '社媒' else \
           f"\n\n—— 来源（美国社媒 · YouTube）：{it['url']}"
    return f"{it['title']}\n\n{body}{tail}" if body else f"{it['title']}{tail}"


MOJI = re.compile(r'[âÃï][\x80-\xbf]')     # 双编码乱码指纹（UTF-8 被当 latin-1 读的产物）


def mojibake_hits(text):
    """返回乱码片段（空列表 = 干净）。判据本体，selftest 与落盘前闸门共用同一个函数。"""
    return MOJI.findall(str(text or ''))


def assert_no_mojibake(items):
    """★ 落盘前闸门（2026-10-15 加）：任何一条素材带双编码乱码 ⇒ **拒写并退非零**。

    为什么要有它：这次是**表里已经躺了 9 条乱码素材**、而且**评审是在乱码文本上判的**，
    才发现问题 —— 采集器当时没有任何东西会红。判据自证：`--selftest`（正例不红 + 注入乱码必红）。
    """
    bad = [(it.get('cid'), mojibake_hits(it.get('采集数据'))[:3]) for it in items
           if mojibake_hits(it.get('采集数据'))]
    if bad:
        print('✗ 采集数据里有双编码乱码 ⇒ 拒绝落盘：')
        for cid, hits in bad:
            print(f'   · {cid} 命中 {hits}')
        raise SystemExit(5)


def selftest():
    """反向对照：干净样本不许红；注入一个 `â\\x80\\x94` 必须精确变红。"""
    clean = [{'cid': 'X', '采集数据': 'Clean — text with “quotes” and ✅️ emoji'}]
    assert_no_mojibake(clean)                      # 不许抛
    dirty = [{'cid': 'X', '采集数据': 'Broken \u00e2\u0080\u0094 text'}]
    try:
        assert_no_mojibake(dirty)
    except SystemExit as e:
        print(f'✅ selftest：正例不红 ｜ 注入乱码精确变红（exit {e.code}，命中 {mojibake_hits(dirty[0]["采集数据"])}）')
        return 0
    print('✗ selftest 失败：注入乱码却没变红（判据恒绿）')
    return 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--json', default=os.path.join(OUT, 'wenan35.json'))
    ap.add_argument('--selftest', action='store_true')
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    print('① 独立站（链接1）…')
    site = collect_site()
    print(f"   取到 {len(site)} 条 ｜ 品类 {dict((k, sum(1 for x in site if x['cat'] == k)) for k in ('吸奶器','清洗机','婴儿监控器'))}")
    print('② 亚马逊（链接2）…')
    raw = json.load(open(os.path.join(HERE, '..', '采集-20261013b', 'raw', 'amazon_rows.json'), encoding='utf-8'))
    amz = collect_amazon(raw, 10)
    print(f"   取到 {len(amz)} 条")
    print('③ 社媒（链接3 · YouTube 美国频道）…')
    soc = collect_social(10)
    print(f"   取到 {len(soc)} 条")
    items = site + amz + soc
    for it in items:
        it['采集数据'] = render(it)[:TOTAL_CAP].rstrip()   # ★ 整条不超过第一行长度
    assert_no_mojibake(items)                             # ★ 落盘前闸门：有乱码 ⇒ 拒写、退 5
    json.dump(items, open(a.json, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(f"\n合计 {len(items)} 条（独立站 {len(site)} / 亚马逊 {len(amz)} / 社媒 {len(soc)}）")
    print(f"字数：min {min(len(x['采集数据']) for x in items)} / 中位 "
          f"{sorted(len(x['采集数据']) for x in items)[len(items)//2]} / max {max(len(x['采集数据']) for x in items)}")
    print(f"→ {a.json}")


if __name__ == '__main__':
    main()