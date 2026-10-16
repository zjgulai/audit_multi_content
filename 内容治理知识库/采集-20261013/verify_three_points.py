#!/usr/bin/env python3
"""Owner 2026-10-15 指定的三条验收点（文案重跑批次）：

  ① **模型侧只跑美国区域** —— 模型侧条目里不得出现非美国辖区的合规要求（中国广告法/极限用语、
     医疗器械广告审查批准文号、GB/3C、欧盟 GDPR、英国 MHRA/CAP、加拿大/澳/日/韩…）。
  ② **不同问题取并集、相同问题去重取交集** —— 报告条目必须分侧标清（库侧/模型侧/两侧都命中），
     且**同一问题不许两侧各出一条**（跨侧引文重叠 = 该去重没去重）；表内「问题数量」= 去重后的条数。
  ③ **置信度两侧都有输出、最终取一个** —— 表里是**单个** 0–1 的数，且汇总格里写明这个数是怎么合并来的。

用法：python3 verify_three_points.py [--scope 文案|all]
"""
import argparse, collections, glob, html, json, os, re, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'out')
REP = os.path.join(OUT, 'reports_20261015')
LARK = os.path.expanduser('~/.dsh/bin/lark-cli')
BASE, TABLE = 'RY2UbCRjXaeeWwscUPScVN5AnQc', 'tblavfbMDMeRsulo'
LEDGER = '/Users/lute/Project/audit_multi_content/PMO/shouheng-state/batch-review.json'
LINK_COL = '10/14重跑报告链接'

NON_US = [('中国广告法/极限用语', r'广告法|极限用语|极限词|违禁词'), ('中国药监/批准文号', r'NMPA|药监局|医疗器械广告审查|批准文号'),
          ('中国国标/3C', r'\bGB\s?\d|3C 认证|CCC'), ('欧盟/GDPR/CE', r'GDPR|欧盟|europa\.eu|CE 认证'),
          ('英国 MHRA/CAP', r'MHRA|CAP Code|\.gov\.uk'), ('中国社媒/电商', r'小红书|抖音|微信|淘宝|天猫|京东|朋友圈'),
          ('其它辖区', r'加拿大|澳大利亚|日本|韩国|新加坡|印度')]
LABELS = [('库侧命中', r'有库内条款依据'), ('模型侧命中', r'无库内条款|无库内依据'),
          ('两侧都命中·结论一致', r'两侧都命中（可回源）'), ('两侧都命中·结论冲突', r'两侧都命中 · 结论冲突')]


def plain(c):
    if c is None:
        return ''
    if isinstance(c, str):
        return c
    if isinstance(c, (int, float)):
        return str(c)
    if isinstance(c, list):
        return ''.join(str(s.get('text') or s.get('link') or '') if isinstance(s, dict) else str(s) for s in c)
    return str(c)


def strip_tags(c):
    t = re.sub(r'<br\s*/?>', '\n', c)
    t = re.sub(r'</(p|li|h[1-6]|td|tr)>', '\n', t)
    return html.unescape(re.sub(r'<[^>]+>', '', t))


def norm(s):
    s = str(s or '').replace('\u2019', "'")
    return re.sub(r'\s+', ' ', s).strip().lower()


def quotes(blk):
    out = []
    for q in re.findall(r'[「"“`]([^」"”`]{4,90})[」"”`]', blk):
        q = re.sub(r'^[.．…\s]+|[.．…\s]+$', '', q)
        if len(q) >= 4:
            out.append(q)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--scope', default='文案')
    a = ap.parse_args()
    led = json.load(open(LEDGER, encoding='utf-8'))['items']
    q = subprocess.run([LARK, 'base', '+record-list', '--base-token', BASE, '--table-id', TABLE,
                        '--view-id', 'vewhS7Rwx0', '--page-size', '200', '--profile', 'dsh-kb',
                        '--as', 'bot', '--format', 'json'], capture_output=True, text=True, cwd='/tmp')
    d = json.loads(q.stdout)['data']; f = d['fields']
    I = {k: f.index(k) for k in ('内容 ID', '内容类型', 'Agent 结论', '问题数量', '置信度', '问题分类汇总',
                                 LINK_COL, '采集数据')}
    rows = [(d['record_id_list'][i], r) for i, r in enumerate(d['data'])]
    sel = [(rid, r) for rid, r in rows if (a.scope == 'all' or plain(r[I['内容类型']]) == a.scope)]
    done = [(rid, r) for rid, r in sel if (led.get(plain(r[I['内容 ID']])) or {}).get('answered_at')]
    print(f"══ 三条验收 ｜ 范围 {a.scope} ｜ 已跑完 {len(done)}/{len(sel)} 行 ══")

    # ── ① 模型侧只跑美国区域 ──────────────────────────────────────────────────
    print("\n① 模型侧是否只落美国口径")
    hits = []
    for rid, r in done:
        cid = plain(r[I['内容 ID']])
        ru = (led.get(cid) or {}).get('report_url') or ''
        m = re.search(r'/docx/([A-Za-z0-9]+)', ru)
        if not m:
            continue
        p = os.path.join(REP, f'{m.group(1)}.txt')
        if not os.path.exists(p):
            continue
        t = strip_tags(open(p, encoding='utf-8').read())
        for blk in re.split(r'(?m)^\s*\d+[.、]\s*(?=【)', t)[1:]:
            if not re.search(r'无库内条款|无库内依据', blk):      # 只看模型侧条目
                continue
            for name, pat in NON_US:
                if re.search(pat, blk, re.I):
                    hits.append((cid, name, ' '.join(blk.split())[:90]))
    print(f"   模型侧条目命中非美国信号的: {len(hits)} 处")
    for h in hits[:6]:
        print(f"   ❌ {h[0][:40]:<42} [{h[1]}] {h[2]}")

    # ── ② 并集 / 交集 ────────────────────────────────────────────────────────
    print("\n② 并集（不同问题）＋ 交集（同问题去重）")
    unmerged, mismatch, no_label = [], [], []
    stat = collections.Counter()
    for rid, r in done:
        cid = plain(r[I['内容 ID']])
        ru = (led.get(cid) or {}).get('report_url') or ''
        m = re.search(r'/docx/([A-Za-z0-9]+)', ru)
        if not m:
            continue
        p = os.path.join(REP, f'{m.group(1)}.txt')
        if not os.path.exists(p):
            continue
        t = strip_tags(open(p, encoding='utf-8').read())
        blocks = re.split(r'(?m)^\s*\d+[.、]\s*(?=【)', t)[1:]
        labs = collections.Counter()
        for blk in blocks:
            for name, pat in LABELS:
                if re.search(pat, blk):
                    labs[name] += 1
                    break
        stat.update(labs)
        cnt = plain(r[I['问题数量']])
        if cnt and int(float(cnt)) != len(blocks):
            mismatch.append((cid, cnt, len(blocks)))
        if blocks and not labs:
            no_label.append(cid)
        # 跨侧同一问题未去重：库侧条目 vs 模型侧条目 引文互相包含
        lib = [b for b in blocks if re.search(r'有库内条款依据', b)]
        mod = [b for b in blocks if re.search(r'无库内条款|无库内依据', b)]
        for x in lib:
            for y in mod:
                qx, qy = quotes(x), quotes(y)
                if any(len(u) >= 4 and any(u in v or v in u for v in qy if len(v) >= 4) for u in qx):
                    unmerged.append((cid, ' '.join(x.split())[:70]))
                    break
    print(f"   条目分侧统计: {dict(stat)}")
    print(f"   表内问题数量 == 去重后条目数: {len(done)-len(mismatch)}/{len(done)}"
          + (f" ｜ 不符 {mismatch[:3]}" if mismatch else ""))
    print(f"   **未去重的同一问题（两侧各出一条）: {len(unmerged)} 处**")
    for u in unmerged[:5]:
        print(f"   ❌ {u[0][:40]:<42} {u[1]}")
    print(f"   条目没有分侧标记的: {len(no_label)}")

    # ── ③ 置信度：两侧都有、最终一个 ─────────────────────────────────────────
    print("\n③ 置信度（单个值 + 合并口径）")
    bad3 = []
    for rid, r in done:
        cid = plain(r[I['内容 ID']])
        conf = plain(r[I['置信度']]).strip()
        summ = plain(r[I['问题分类汇总']])
        why = []
        try:
            v = float(conf)
            if not (0 <= v <= 1):
                why.append(f'越界 {conf}')
        except ValueError:
            why.append(f'不是单个数：{conf!r}')
        if not re.search(r'置信度', summ):
            why.append('汇总里没写置信度口径')
        if why:
            bad3.append((cid, conf, why))
    print(f"   单个 0–1 的值 且 汇总有置信度口径: {len(done)-len(bad3)}/{len(done)}")
    for b in bad3[:6]:
        print(f"   ❌ {b[0][:40]:<42} {b[1]!r} ｜ {b[2]}")


if __name__ == '__main__':
    main()