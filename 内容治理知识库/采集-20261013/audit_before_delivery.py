#!/usr/bin/env python3
"""交付前全表体检（2026-10-15，Owner 要发给业务侧前）。

查四层：
  A 列级 —— 每列非空率 / 值域 / 分布（业务侧看到的就是这些）
  B 行级交叉核验 —— 状态·结论·数量·置信度·汇总·链接 六者自洽
  C 链接可达 —— 逐个把报告拉一遍（不是看格式，是真去取）
  D 交付风险 —— 业务侧最可能误解/追问的地方，逐条给证据与建议

输出 out/audit_before_delivery.json + 屏幕报告。
"""
import collections, glob, html, json, os, re, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'out')
B = os.path.join(HERE, 'backup_pass_rerun_20261015-105156')
SNAP = os.path.join(B, 'own70_view_final.ndjson')
LARK = os.path.expanduser('~/.dsh/bin/lark-cli')
BASE, TABLE = 'RY2UbCRjXaeeWwscUPScVN5AnQc', 'tblavfbMDMeRsulo'
LINK_COL = '10/14重跑报告链接'


def plain(cell):
    if cell is None:
        return ''
    if isinstance(cell, str):
        return cell
    if isinstance(cell, (int, float)):
        return str(cell)
    if isinstance(cell, list):
        return ''.join(str(s.get('text') or s.get('link') or s.get('name') or '') if isinstance(s, dict) else str(s) for s in cell)
    if isinstance(cell, dict):
        return str(cell.get('text') or cell.get('link') or cell.get('name') or '')
    return str(cell)


def strip_tags(c):
    t = re.sub(r'<br\s*/?>', '\n', c)
    t = re.sub(r'</(p|li|h[1-6]|td|tr)>', '\n', t)
    return html.unescape(re.sub(r'<[^>]+>', '', t))


def tok_of(cell):
    m = re.search(r'/docx/([A-Za-z0-9]+)', plain(cell))
    return m.group(1) if m else None


def fetch_doc(tok, cache_dir):
    p = os.path.join(cache_dir, f'{tok}.txt')
    if os.path.exists(p):
        return open(p, encoding='utf-8').read(), 'cached'
    q = subprocess.run([LARK, 'docs', '+fetch', '--doc', tok, '--profile', 'dsh-kb', '--as', 'bot'],
                       capture_output=True, text=True, cwd='/tmp')
    try:
        c = json.loads(q.stdout)['data']['document']['content']
    except Exception:
        return None, f'拉不到（{(q.stdout or q.stderr or "")[:80]}）'
    open(p, 'w', encoding='utf-8').write(c)
    return c, 'fetched'


def main():
    rows = [json.loads(l) for l in open(SNAP, encoding='utf-8') if l.strip()]
    fields = [k for k in rows[0].keys() if k != 'record_id']
    rep_cache = os.path.join(OUT, 'reports_20261015')
    os.makedirs(rep_cache, exist_ok=True)

    # ── A 列级 ──────────────────────────────────────────────────────────────
    print(f"══ A 列级体检（{len(rows)} 行 · 视图顺序）══")
    for k in fields:
        vals = [plain(r.get(k)) for r in rows]
        empty = sum(1 for v in vals if not v.strip())
        dist = collections.Counter(v for v in vals if v.strip())
        head = '  '.join(f'{v[:14]}×{n}' for v, n in dist.most_common(3))
        print(f"  {k:<16} 空 {empty:>2}/{len(rows)} ｜ 不同值 {len(dist):>3} ｜ {head[:96]}")

    # ── B/C 行级 ────────────────────────────────────────────────────────────
    print(f"\n══ B/C 行级交叉核验 + 链接可达 ══")
    findings = collections.defaultdict(list)
    per = []
    link_status = collections.Counter()
    for i, r in enumerate(rows, 1):
        cid = plain(r.get('内容 ID'))
        concl = plain(r.get('Agent 结论')).strip()
        state = plain(r.get('状态')).strip()
        cn = plain(r.get('问题数量')).strip()
        cnt = int(float(cn)) if cn else None
        conf = plain(r.get('置信度')).strip()
        summ = plain(r.get('问题分类汇总'))
        link = plain(r.get(LINK_COL))
        tok = tok_of(r.get(LINK_COL))
        rec = {'no': i, 'cid': cid, 'concl': concl, 'state': state, 'cnt': cnt,
               'conf': conf, 'tok': tok, 'link': link, 'bad': []}

        def bad(code, msg):
            rec['bad'].append([code, msg]); findings[code].append((i, cid, msg))

        # 值域
        if concl not in ('PASS', 'REVIEW', 'BLOCK') and cnt:
            bad('B1', f'Agent 结论 =「{concl}」不是三态')
        if state not in ('待审', '已修改', '已发布'):
            bad('B2', f'状态 =「{state}」不在 PRD 三档')
        if conf not in ('',) and not (0 <= float(conf) <= 1):
            bad('B3', f'置信度 {conf} 越界')
        # 汇总的形状
        head = re.search(r'【审查结论：(\w+)】共发现\s*(\d+)\s*处', summ)
        if cnt and not head:
            bad('B4', '汇总里没有 PRD 结论行')
        elif head and concl and head.group(1) != concl:
            bad('B5', f'汇总结论行 {head.group(1)} ≠ Agent 结论 {concl}')
        elif head and cnt is not None and int(head.group(2)) != cnt:
            bad('B6', f'汇总结论行「{head.group(2)} 处」 ≠ 问题数量 {cnt}')
        bullets = re.findall(r'·\s*([^·\n]{1,18}?)类问题：\s*(\d+)\s*个', summ)
        other = re.search(r'另有\s*\**\s*(\d+)\s*\**\s*条', summ)
        s_sum = sum(int(n) for _, n in bullets) + (int(other.group(1)) if other else 0)
        if cnt and bullets and s_sum != cnt and '没有并进任何' not in summ:
            bad('B7', f'分类计数 {s_sum} ≠ 问题数量 {cnt}')
        if cnt and cnt >= 3 and not bullets and '没有并进任何' not in summ:
            bad('B8', f'{cnt} 处问题却没有分类汇总块')
        if concl != 'PASS' and not re.search(r'请修改后重新提交。|建议转 @', summ):
            bad('B9', '汇总缺动作行')
        # 依据 url（Owner 10-15 第 2 条）
        if '【逐条依据（落库留痕）】' in summ:
            for b in re.split(r'(?m)^\s*\d+[.、]\s*', summ.split('【逐条依据（落库留痕）】')[-1])[1:]:
                if not re.search(r'https?://', b) and not re.search(r'无库内依据|无库内条款', b):
                    bad('B10', '有依据条既无 url 也无「无库内依据」标注'); break
        if conf == '0' and not re.search(r'按 \*\*0\*\* 记|不是「零风险」', summ):
            bad('B11', '置信度=0 但汇总没写口径')
        # 读数句（Owner 10-09：「库侧那个读数不许丢」）
        if cnt and not re.search(r'库侧 \d+ 条机器读数|本次未参与|未报内容问题|P0 快路|没跑成', summ):
            bad('B12', '汇总里没有双轨读数/边界句')
        # 链接可达
        if tok:
            c, how = fetch_doc(tok, rep_cache)
            link_status[how if c is not None else '拉不到'] += 1
            if c is None:
                bad('C1', f'报告拉不到：{tok}')
            else:
                t = strip_tags(c)
                m = re.search(r'【审查结论：(\w+)】', t)
                d = re.search(r'共发现\s*(\d+)\s*处', t)
                items = len(re.findall(r'(?m)^\s*\d+[.、]\s*【', t))
                rec['rep_state'] = m.group(1) if m else None
                rec['rep_declared'] = int(d.group(1)) if d else None
                rec['rep_items'] = items
                if m and concl and m.group(1) != concl:
                    bad('C2', f'报告结论 {m.group(1)} ≠ 表内 {concl}')
                if d and cnt is not None and int(d.group(1)) != cnt:
                    bad('C3', f'报告「共发现 {d.group(1)} 处」 ≠ 表内 {cnt}')
                if d and int(d.group(1)) != items:
                    bad('C4', f'报告自身不闭合：声明 {d.group(1)} 处、只列 {items} 条')
        elif cnt:
            bad('C5', f'有 {cnt} 处问题却没有报告链接')

        # D 交付风险（不算「错」，但业务侧会追问）
        if conf == '0':
            rec.setdefault('risk', []).append('置信度 0（引擎未判定的口径，业务侧易读成「零风险」）')
        for f in ('产品线', '渠道'):
            if not plain(r.get(f)).strip():
                rec.setdefault('risk', []).append(f'{f} 为空')
        emb = re.search(r'报告：\s*(\S+)', summ)
        if emb and tok_of(emb.group(1)) and tok_of(emb.group(1)) != tok:
            rec.setdefault('risk', []).append('汇总里的「报告：」与链接列**不是同一份**（P0 快路报告 vs 合并报告）')
        per.append(rec)

    print(f"  链接可达：{dict(link_status)}")
    print("\n  判据命中：")
    for code in sorted(findings):
        print(f"    {code:<4} {len(findings[code]):>3} 条 ｜ 例：{findings[code][0][1]} {findings[code][0][2]}")

    # ── D 交付风险汇总 ──────────────────────────────────────────────────────
    print("\n══ D 业务侧会追问的点（按行数排）══")
    risk = collections.Counter()
    for rec in per:
        for x in rec.get('risk', []):
            risk[x] += 1
    for k, v in risk.most_common():
        print(f"  {v:>3} 行 ｜ {k}")

    # ── 重复与一致性 ────────────────────────────────────────────────────────
    print("\n══ 重复检测 ══")
    for col in ('内容 ID', '采集数据', LINK_COL):
        c = collections.Counter(plain(r.get(col)) for r in rows if plain(r.get(col)).strip())
        dup = {k: v for k, v in c.items() if v > 1}
        print(f"  {col}: 不同值 {len(c)} ｜ 重复值 {len(dup)} 组"
              + (f"（最大 {max(dup.values())} 次，如 {list(dup)[0][:40]}）" if dup else ""))

    # ── E 引用同源（Owner 2026-10-15 批准；交付前必跑）────────────────────────────
    #   为什么要接进来：Owner 报的 bug「采集了一句话、按整篇文章评审」**没有任何东西会红**。
    #   判据按内容类型分口径（文案=表里那一份；图片/视频=引文来自画面/音轨 ⇒ 只判能不能核）。
    print("\n══ E 引用同源判据（报告引文 vs 该行素材）══")
    qs = os.path.join(HERE, 'audit_quote_scope.py')
    if os.path.exists(qs):
        out = subprocess.run([sys.executable, qs], capture_output=True, text=True, cwd=HERE)
        for line in (out.stdout or '').splitlines():
            if line.strip() and not line.startswith('明细'):
                print('  ' + line if not line.startswith('══') else line)
    else:
        print('  ⚠️ 判据脚本不在（audit_quote_scope.py）—— 这一节未测')

    json.dump({'findings': {k: v for k, v in findings.items()}, 'per_row': per,
               'link_status': dict(link_status)}, open(os.path.join(OUT, 'audit_before_delivery.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    print(f"\n明细 → out/audit_before_delivery.json")


if __name__ == '__main__':
    main()