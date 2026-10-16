#!/usr/bin/env python3
"""核对「图上有中文」这类结论：**OCR 读出的中文字形，图上真的有吗**。

Owner 2026-10-16 第 17 行提问逐字：「审查报告中 图 1 内文字行「嫩圈o」「白」，图片中有吗？你验证下」

判据（三步，全部只读、可复现）：
  ① **逐字回放**：用**产线同一个** OCR 二进制（macOS Vision，语种表与 `vision.mjs::OCR_LANGS` 一致）
     读出该图全部行，挑出**含中日韩汉字**的行，连同**置信度 c 与归一化坐标 (x,y,w,h)** 一起打印；
  ② **像素级对照**：按坐标把那一行**原样裁出来放大**，存成 PNG —— 「图上到底印的是什么」由人/模型看，
     **不由 OCR 自己说了算**；
  ③ **稳定性对照（反证）**：把整图放大 2× 再 OCR 一次。同一处若**读出另一个汉字串**
     （实测第 17 行：「嫩圈o」→「小图」、「白」→「～～」），即证明它不是字形、是噪声。

用法：
  python3 verify_cjk_ocr_claims.py --rows 17,47,50,55
  python3 verify_cjk_ocr_claims.py --rows 17 --keep        # 保留临时图
"""
import argparse, json, os, re, shutil, subprocess, sys, tempfile, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
LARK = os.path.expanduser('~/.dsh/bin/lark-cli')
OCR = os.path.expanduser('~/Project/audit_multi_content/.tools/bin/ocr')
LANGS = ['zh-Hans', 'en-US', 'de-DE', 'fr-FR', 'es-ES']   # = vision.mjs::OCR_LANGS
BASE, TABLE = 'RY2UbCRjXaeeWwscUPScVN5AnQc', 'tblavfbMDMeRsulo'
CJK = re.compile(r'[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]')


def plain(v):
    if v is None: return ''
    if isinstance(v, str): return v
    if isinstance(v, list): return ''.join(str(s.get('text') or s.get('link') or '') if isinstance(s, dict) else str(s) for s in v)
    if isinstance(v, dict): return str(v.get('text') or v.get('link') or '')
    return str(v)


def read_rows():
    out = '/tmp/cjk_tbl.ndjson'
    subprocess.run([LARK, 'base', '+record-list', '--base-token', BASE, '--table-id', TABLE,
                    '--limit', '2000', '--format', 'ndjson', '--output', out, '--overwrite',
                    '--profile', 'dsh-kb', '--as', 'bot'], capture_output=True, text=True, cwd='/tmp')
    return [json.loads(l) for l in open(out, encoding='utf-8') if l.strip()]


def img_urls(cell):
    """采集数据里第一个**图片直链**（webp/jpg/png 结尾，或 cdn 上的）。视频行取封面同款。"""
    urls = re.findall(r'https?://[^\s\)\]]+', cell)
    for u in urls:
        if re.search(r'\.(webp|jpe?g|png|gif)(\?|$)', u, re.I):
            return u
    return ''


def ocr(path, langs=LANGS):
    q = subprocess.run([OCR, path, *langs], capture_output=True, text=True, timeout=120)
    try:
        return json.loads(q.stdout)
    except Exception:
        return {'ok': False, 'raw': q.stdout[:200], 'err': q.stderr[:200]}


def crop_box(im, l, pad=0.012, target=900):
    from PIL import Image
    W, H = im.size
    x, y, w, h = l['x'], l['y'], l['w'], l['h']
    x0 = max(0, int((x - pad) * W)); x1 = min(W, int((x + w + pad) * W))
    y0 = max(0, int((1 - y - h - pad) * H)); y1 = min(H, int((1 - y + pad) * H))   # Vision 原点在左下
    c = im.crop((x0, y0, x1, y1))
    s = max(1, int(target / max(1, c.width)))
    return c.resize((c.width * s, c.height * s), Image.LANCZOS), (x0, y0, x1, y1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--rows', required=True, help='采集表行号，逗号分隔（1 起）')
    ap.add_argument('--keep', action='store_true')
    a = ap.parse_args()
    want = [int(s) for s in a.rows.split(',') if s.strip()]

    from PIL import Image
    rows = read_rows()
    work = os.path.join(tempfile.gettempdir(), 'cjkcheck')
    os.makedirs(work, exist_ok=True)
    report = {'at': __import__('time').strftime('%Y-%m-%d %H:%M:%S'), 'rows': {}}

    for n in want:
        r = rows[n - 1]
        cid = plain(r.get('内容 ID'))
        kind = plain(r.get('内容类型'))
        cell = plain(r.get('问题分类汇总'))
        url = img_urls(plain(r.get('采集数据')))
        d = os.path.join(work, f'row{n}')
        os.makedirs(d, exist_ok=True)
        print(f"\n{'='*78}\n行 {n} ｜ {kind} ｜ {cid}\n图：{url[:120]}")
        claims = sorted({m for m in CJK.findall(cell)})
        print(f"表内结论里出现的汉字字形：{''.join(claims) or '（无）'}")
        if not url:
            print('  ⚠️ 采集数据里没有图片直链 —— 无法核（如实记，不猜）')
            report['rows'][n] = {'cid': cid, 'kind': kind, 'img': None, 'note': 'no_image_url'}
            continue
        p = os.path.join(d, 'img')
        if not os.path.exists(p):
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=60) as f, open(p, 'wb') as g:
                shutil.copyfileobj(f, g)
        im = Image.open(p).convert('RGB')
        print(f'  图尺寸 {im.size}，字节 {os.path.getsize(p)}')
        d1 = ocr(p)
        if not d1.get('ok'):
            print('  ❌ OCR 失败：', d1); report['rows'][n] = {'cid': cid, 'ocr': 'fail'}; continue
        cjk_lines = [l for l in d1['lines'] if CJK.search(l['t'])]
        print(f"  OCR 共 {len(d1['lines'])} 行，其中含汉字 {len(cjk_lines)} 行：")
        rec = {'cid': cid, 'kind': kind, 'img': url, 'n_lines': len(d1['lines']), 'cjk': []}
        for l in cjk_lines:
            print(f"    · {l['t']!r}  置信度 {l['c']}  坐标 x={l['x']:.3f} y={l['y']:.3f} "
                  f"w={l['w']:.3f} h={l['h']:.3f}")
        # 稳定性对照：整图 2×
        p2 = os.path.join(d, 'img2x.png')
        if not os.path.exists(p2):
            im.resize((im.width * 2, im.height * 2), Image.LANCZOS).save(p2)
        d2 = ocr(p2)
        cjk2 = [l['t'] for l in (d2.get('lines') or []) if CJK.search(l['t'])]
        print(f"  2× 放大后 OCR：{len(d2.get('lines') or [])} 行，含汉字 {len(cjk2)} 行：{cjk2}")
        for l in cjk_lines:
            c, box = crop_box(im, l)
            fn = os.path.join(d, f"box_{len(rec['cjk'])+1}_{l['t']}.png".replace('/', '_'))
            c.save(fn)
            print(f"    → 裁图 {fn}（原图坐标 {box}，放大 {round(c.width/max(1,box[2]-box[0]))}×）")
            rec['cjk'].append({'t': l['t'], 'conf': l['c'], 'box': box, 'crop': fn,
                               'again_2x': [s for s in cjk2 if s != l['t']] or cjk2})
        rec['text'] = d1.get('text')
        report['rows'][n] = rec
        if not a.keep:
            pass
    out = os.path.join(HERE, 'out', f"cjk_check_{__import__('time').strftime('%Y%m%d-%H%M%S')}.json")
    json.dump(report, open(out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('\n留痕 ->', out)
    print('裁图目录 ->', work)


if __name__ == '__main__':
    main()
