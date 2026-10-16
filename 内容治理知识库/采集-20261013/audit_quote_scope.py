#!/usr/bin/env python3
"""引用同源判据（Owner 2026-10-15 批准）：报告里每条引文，必须能在**该行的素材**里逐字找到。

为什么要它：Owner 报的 bug ——「是让你采集文案，不是采集文章……采集了一句话，实际按照
整篇文章来评审」。这类不一致（采集范围 ≠ 评审范围）**没有任何东西会红**，于是只能靠人肉发现。
这条判据把它变成可判定的。

★ 口径**按内容类型分开**（不许一套判据套所有类型，那会造出 45 行假红）：
  · 文案      —— 素材 = 该行「采集数据」（表里那一份，就是评审该审的那一份）
  · 图片/视频 —— 素材 = 画面 OCR / 音轨字幕，**不在表里**（表里只有图注/标题/链接）
                ⇒ 引文落在表外是**正常**的；本判据对它只判「能不能核」：
                  报告若不带抽取件 ⇒ 记**未测**（未测不许当红 —— 库规：缺证据要看得见）

用法：
  python3 audit_quote_scope.py            # 只报
  python3 audit_quote_scope.py --json out/quote_scope.json
"""
import argparse, collections, glob, html, json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'out')
SNAP = os.path.join(HERE, 'backup_pass_rerun_20261015-105156', 'own70_view_final.ndjson')
REP_DIR = os.path.join(OUT, 'reports_20261015')
MIN_QUOTE = 8          # 少于 8 字的引文不判（噪声太大：`Fast`、`4 in 1` 这类满篇都是）


def plain(cell):
    if cell is None:
        return ''
    if isinstance(cell, str):
        return cell
    if isinstance(cell, (int, float)):
        return str(cell)
    if isinstance(cell, list):
        return ''.join(str(s.get('text') or s.get('link') or '') if isinstance(s, dict) else str(s) for s in cell)
    return str(cell)


def strip_tags(c):
    t = re.sub(r'<br\s*/?>', '\n', c)
    t = re.sub(r'</(p|li|h[1-6]|td|tr)>', '\n', t)
    return html.unescape(re.sub(r'<[^>]+>', '', t))


def norm(s):
    """归一化：折叠空白 / 统一弯引号 / 小写。**不做同义改写** —— 判据只认逐字。"""
    s = str(s or '').replace('\u2019', "'").replace('\u201c', '"').replace('\u201d', '"')
    return re.sub(r'\s+', ' ', s).strip().lower()


def quotes_of(report):
    """报告条目里的**引文**：只取「位置」那一段（`原因：` 之前），避免把模型自己的话当引文。
    去掉首尾省略号/句点 —— 报告用 `…xxx` 表示截断，那不是不逐字。"""
    out = []
    for blk in re.split(r'(?m)^\s*\d+[.、]\s*(?=【)', report)[1:]:
        seg = blk.split('建议：')[0].split('原因：')[0]
        for q in re.findall(r'[「"“`]([^」"”`]{6,90})[」"”`]', seg):
            q = re.sub(r'^[.．…\s]+|[.．…\s]+$', '', q)
            if len(q) >= MIN_QUOTE:
                out.append(q)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--json', default=os.path.join(OUT, 'quote_scope.json'))
    a = ap.parse_args()
    rows = [json.loads(l) for l in open(SNAP, encoding='utf-8') if l.strip()]
    docs = {os.path.basename(p)[:-4]: strip_tags(open(p, encoding='utf-8').read())
            for p in glob.glob(os.path.join(REP_DIR, '*.txt'))}

    stat = collections.Counter()
    bad, untested, detail = [], [], []
    for r in rows:
        cid = plain(r.get('内容 ID'))
        ctype = plain(r.get('内容类型'))
        m = re.search(r'/docx/([A-Za-z0-9]+)', plain(r.get('10/14重跑报告链接')))
        if not m:
            stat['无报告'] += 1
            continue
        rep = docs.get(m.group(1))
        if not rep:
            stat['报告未落盘'] += 1
            continue
        material = norm(plain(r.get('采集数据')))
        qs = quotes_of(rep)
        if not qs:
            # ★ 「报告没写引文」**不是**「同源通过」—— 判据无从比 ⇒ 记**未测**，不许算绿。
            stat[f'{ctype}·未测（报告没写引文）'] += 1
            untested.append({'cid': cid, 'ctype': ctype, 'n_quotes': 0, 'n_outside': 0,
                             'why': '报告的位置描述里没有可逐字比的引文（只有描述性指代）⇒ 无从核'})
            continue
        missing = [q for q in qs if norm(q) not in material]
        if ctype == '文案':
            if missing:
                stat['文案·引用越界'] += 1
                bad.append({'cid': cid, 'missing': missing[:3], 'n_missing': len(missing), 'n_quotes': len(qs)})
            else:
                stat['文案·同源'] += 1
        else:
            # 图片 / 视频：引文来自画面或音轨 ⇒ 落在表外是正常的。判「能不能核」。
            stat[f'{ctype}·引文不在表内（正常）'] += 1
            untested.append({'cid': cid, 'ctype': ctype, 'n_quotes': len(qs), 'n_outside': len(missing),
                             'why': '引文来自画面/音轨，而发布版报告不带抽取件 ⇒ 无从逐字核（未测，不算红）'})
        detail.append({'cid': cid, 'ctype': ctype, 'n_quotes': len(qs), 'n_missing': len(missing),
                       'missing': missing[:3]})

    print(f"══ 引用同源判据（{len(rows)} 行）══")
    for k in sorted(stat):
        print(f"   {k:<28} {stat[k]:>3} 行")
    print(f"\n── 文案类·引用越界（**要处理的**）：{len(bad)} 行 ──")
    for b in bad:
        print(f"   {b['cid']:<40} 越界 {b['n_missing']}/{b['n_quotes']} 条 ｜ 例：{b['missing'][:2]}")
    print(f"\n── **未测**（不当红，但必须看得见）：{len(untested)} 行 ──")
    print("   图片/视频：引文来自画面/音轨 ⇒ 表里搜不到是正常的；报告不带抽取件 ⇒ 无从核")
    print("   文案：报告那几条没写引文 ⇒ 无从核")
    json.dump({'stat': dict(stat), 'violations': bad, 'untested': untested, 'detail': detail},
              open(a.json, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(f"\n明细 → {a.json}")
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())