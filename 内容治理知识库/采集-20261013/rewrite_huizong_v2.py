#!/usr/bin/env python3
# ⚠️⚠️ 2026-10-15 起**封存，不要再跑**（除非 Owner 明确要）────────────────────────
#   为什么封存：这一格现在由**守衡自己写**，而它的动作行是**按问题方向算出来的收件人**
#   （`建议转 @法务（未配置） @北美同事（未配置） 复核。（其中 6/7 条未匹配到方向…）`）。
#   本脚本只会拼 PRD 的逐字句（`建议转 @法务 @医学顾问 复核。`）——**跑一次就会把那行覆盖掉**。
#   ⇒ 保留它只为「需要一次性批量回填、且明确不要守衡那版动作行」的场合；默认拒绝运行。
"""按 Owner 2026-10-15 给的**逐字格式**重写表里那一格（只出 PRD 结论，不夹带内部读数）。

格式（Owner 原话，逐字）：
    【审查结论：BLOCK】共发现 9 处必须修改。
    逐条问题
    · 合规类问题：2 个
    · 措辞表达类问题：2 个
    · 产品描述类问题：1 个
    · 消费者安全类问题：1 个
    · 另有 3 条（明细在报告里）

    → 查看完整问题清单与修改建议：https://…/docx/…

    请修改后重新提交。

分档（PRD §5.3）：
  · ≥3 条 ⇒ 上面这个形状（分类汇总 + 报告链接 + 动作行；**逐条明细在报告里**）
  · 1–2 条 ⇒ 逐条展开（维度 · 位置 · 描述 / 原因 / 依据 / 建议）+ 动作行
  · PASS  ⇒ 一句话（§5.3.1）

**撤掉的东西**（它们此前挂在这一格里，Owner 2026-10-15 明确不要）：
  【逐条依据（落库留痕）】/「双轨合并：卡内总数…」读数句 / ⚠️ 口径说明 / 置信度合并口径句。

用法：python3 rewrite_huizong_v2.py [--apply]
"""
import argparse, collections, glob, html, json, os, re, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'out')
REP = os.path.join(OUT, 'reports_20261015')
LARK = os.path.expanduser('~/.dsh/bin/lark-cli')
BASE, TABLE = 'RY2UbCRjXaeeWwscUPScVN5AnQc', 'tblavfbMDMeRsulo'
LEDGER = '/Users/lute/Project/audit_multi_content/PMO/shouheng-state/batch-review.json'
LINK_COL = '10/14重跑报告链接'
ACTION_REVIEW = '建议转 @法务 @医学顾问 复核。'
ACTION_BLOCK = '请修改后重新提交。'


def plain(v):
    if v is None:
        return ''
    if isinstance(v, str):
        return v
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, list):
        return ''.join(str(s.get('text') or s.get('link') or '') if isinstance(s, dict) else str(s) for s in v)
    return str(v)


def strip_tags(c):
    t = re.sub(r'<br\s*/?>', '\n', c)
    t = re.sub(r'</(p|li|h[1-6]|td|tr)>', '\n', t)
    return html.unescape(re.sub(r'<[^>]+>', '', t))


def fetch_doc(tok):
    p = os.path.join(REP, f'{tok}.txt')
    if os.path.exists(p):
        return strip_tags(open(p, encoding='utf-8').read()), True
    q = subprocess.run([LARK, 'docs', '+fetch', '--doc', tok, '--profile', 'dsh-kb', '--as', 'bot'],
                       capture_output=True, text=True, cwd='/tmp')
    try:
        c = json.loads(q.stdout)['data']['document']['content']
    except Exception:
        return None, False
    open(p, 'w', encoding='utf-8').write(c)
    return strip_tags(c), True


def build(concl, n, link_url, report):
    """按 Owner 的格式装一格。report 为 None ⇒ 只能给结论行 + 动作行。"""
    items = []
    if report:
        for blk in re.split(r'(?m)^\s*\d+[.、]\s*(?=【)', report)[1:]:
            one = ' '.join(blk.split())
            cat = re.match(r'【([^】]{1,24})】', one)
            items.append((cat.group(1) if cat else '未分类', one))
    head = ''
    if report:
        m = re.search(r'【审查结论：\w+】共发现\s*\d+\s*处[^。]*。', report)
        if m:
            head = m.group(0)
    if not head:
        head = f'【审查结论：{concl}】共发现 {n} 处' + ('必须修改。' if concl == 'BLOCK' else '需人工确认。')
    parts = [head]
    if concl == 'PASS':
        return '【审查结论：PASS】未发现已知底线风险，可转交 @sign-off 责任人（未配置）进行 sign-off。'
    if n >= 3:
        cats = collections.Counter(c for c, _ in items)
        rows = [f'· {k}类问题：{v} 个' for k, v in cats.most_common()]
        if not rows:
            rows = ['·（本次没有并进任何逐条）']
        if n > len(items):
            rows.append(f'· 另有 {n - len(items)} 条（明细在报告里）')     # ★ 不加粗（Owner 格式）
        parts.append('逐条问题\n' + '\n'.join(rows))
        if link_url:
            parts.append(f'→ 查看完整问题清单与修改建议：{link_url}')
        parts.append(ACTION_BLOCK if concl == 'BLOCK' else ACTION_REVIEW)
    else:
        blocks = []
        for i, (cat, one) in enumerate(items, 1):
            seg = one
            seg = re.sub(r'\s*——\s*(有库内条款依据|无库内条款 · 依据为外部标准|无库内依据 · 建议转人工|两侧都命中[^—]*)', '', seg)
            blocks.append(f'{i}.{seg}' if not seg.startswith('【') else f'{i}.{seg}')
        if blocks:
            parts.append('\n\n'.join(blocks))
        if link_url:
            parts.append(f'→ 查看完整问题清单与修改建议：{link_url}')
        parts.append(ACTION_BLOCK if concl == 'BLOCK' else ACTION_REVIEW)
    return '\n\n'.join(parts)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true')
    ap.add_argument('--force', action='store_true', help='明知会覆盖守衡算出的动作行，仍要跑')
    a = ap.parse_args()
    if not a.force:
        print('⛔ 本脚本已封存：这一格现在由守衡写（动作行按问题方向算）。')
        print('   真要跑（会覆盖守衡那版动作行）加 --force。')
        return 2
    led = json.load(open(LEDGER, encoding='utf-8'))['items']
    q = subprocess.run([LARK, 'base', '+record-list', '--base-token', BASE, '--table-id', TABLE,
                        '--view-id', 'vewhS7Rwx0', '--page-size', '200', '--profile', 'dsh-kb',
                        '--as', 'bot', '--format', 'json'], capture_output=True, text=True, cwd='/tmp')
    d = json.loads(q.stdout)['data']; F = d['fields']
    I = {k: F.index(k) for k in ('内容 ID', '内容类型', 'Agent 结论', '问题数量', LINK_COL, '问题分类汇总')}
    patch, stat = {}, collections.Counter()
    for i, row in enumerate(d['data']):
        cid = plain(row[I['内容 ID']]); concl = plain(row[I['Agent 结论']]).strip()
        if not concl:
            stat['无结论（待跑，跳过）'] += 1
            continue
        cn = plain(row[I['问题数量']]).strip()
        n = int(float(cn)) if cn else 0
        link = plain(row[I[LINK_COL]])
        m = re.search(r'/docx/([A-Za-z0-9]+)', link)
        url = re.search(r'https?://[^\s)]+', link)
        rep = None
        if m:
            rep, ok = fetch_doc(m.group(1))
            if not ok:
                stat['报告拉不到'] += 1
        new = build(concl, n, url.group(0) if url else '', rep)
        cur = plain(row[I['问题分类汇总']])
        if new.strip() != cur.strip():
            patch[d['record_id_list'][i]] = new
            stat['需重写'] += 1
        else:
            stat['已是新格式'] += 1
        if stat['需重写'] == 1 and 'preview' not in stat:
            stat['preview'] = 1
            print("—— 预览（第一行）——"); print(new[:520]); print("——")
    print("结果:", {k: v for k, v in stat.items() if k != 'preview'})
    if not a.apply:
        print("（未加 --apply：什么都没写）")
        return 0
    if patch:
        sn = os.path.join(HERE, 'backup_pass_rerun_20261015-105156', 'huizong_before_v2.json')
        json.dump({d['record_id_list'][i]: plain(r[I['问题分类汇总']]) for i, r in enumerate(d['data'])
                   if d['record_id_list'][i] in patch}, open(sn, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        w = subprocess.run([LARK, 'base', '+record-batch-update', '--base-token', BASE, '--table-id', TABLE,
                            '--json', json.dumps({'update_records': patch}, ensure_ascii=False),
                            '--profile', 'dsh-kb', '--as', 'bot'], capture_output=True, text=True, cwd='/tmp')
        print(f"写入 {len(patch)} 行 ｜ rc {w.returncode} {str(w.stdout or '')[:80]}")
    return 0


if __name__ == '__main__':
    sys.exit(main())