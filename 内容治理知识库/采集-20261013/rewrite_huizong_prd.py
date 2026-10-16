#!/usr/bin/env python3
"""按 PRD §5.3 重写 80 行的「问题分类汇总」（Owner 2026-10-15 裁定：覆盖旧值、不建新字段）。

新格内容 = PRD 摘要块（结论行 / 分类计数 / 报告链接行 / 动作行）
         + 【逐条依据（落库留痕）】（每条带依据 url；无源的如实标注，**不编 url**）
         + 原格里那两句口径说明（置信度按 0 记 / 产品线·渠道留空）—— 原样保留，删不删由 Owner 定。

用法：
  python3 rewrite_huizong_prd.py --dry-run      # 只打印预览，不写
  python3 rewrite_huizong_prd.py --apply        # 真写（写前整表快照）
"""
import argparse, collections, glob, html, json, os, re, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'out')
B = os.path.join(HERE, 'backup_pass_rerun_20261015-105156')
SNAP = os.path.join(B, 'own70_view_fresh.ndjson')   # 每次跑前重拉（链接列会被跟随器/手工改）
LARK = os.path.expanduser('~/.dsh/bin/lark-cli')
BASE, TABLE = 'RY2UbCRjXaeeWwscUPScVN5AnQc', 'tblavfbMDMeRsulo'
LINK_COL = '10/14重跑报告链接'

ACTION_REVIEW = '建议转 @法务 @医学顾问 复核。'
ACTION_BLOCK = '请修改后重新提交。'


def plain(cell):
    if cell is None:
        return ''
    if isinstance(cell, str):
        return cell
    if isinstance(cell, (int, float)):
        return str(cell)
    if isinstance(cell, list):
        return ''.join(str(s.get('text') or s.get('link') or '') if isinstance(s, dict) else str(s) for s in cell)
    if isinstance(cell, dict):
        return str(cell.get('text') or cell.get('link') or '')
    return str(cell)


def tok_of(cell):
    m = re.search(r'/docx/([A-Za-z0-9]+)', plain(cell))
    return m.group(1) if m else None


def strip_tags(c):
    t = re.sub(r'<br\s*/?>', '\n', c)
    t = re.sub(r'</(p|li|h[1-6]|td|tr)>', '\n', t)
    return html.unescape(re.sub(r'<[^>]+>', '', t))


def load_report(tok):
    p = os.path.join(OUT, 'reports_20261015', f'{tok}.txt')
    if not os.path.exists(p):
        return None
    return strip_tags(open(p, encoding='utf-8').read())


def parse_items(report):
    """报告 → 逐条（分类 / 一句话位置 / 原因 / 依据 / url / 标签）。全部取自报告原文，不编。"""
    items = []
    for blk in re.split(r'(?m)^\s*\d+[.、]\s*(?=【)', report)[1:]:
        one = ' '.join(blk.split())
        cat = re.match(r'【([^】]{1,24})】', one)
        lab = re.search(r'(有库内条款依据|无库内条款 · 依据为外部标准|无库内依据 · 建议转人工|两侧都命中[^—]*)', one)
        reason = re.search(r'原因：(.*?)(?=依据：|建议：|$)', one)
        basis = re.search(r'依据：(.*?)(?=建议：|$)', one)
        sug = re.search(r'建议：(.*)$', one)
        loc = one[cat.end():] if cat else one
        loc = loc.split('原因：')[0].split('——')[0].strip(' ｜·-—')
        url = re.search(r'https?://\S+', one)
        items.append({
            'cat': cat.group(1) if cat else '未分类',
            'label': lab.group(1).strip() if lab else '',
            'loc': loc[:60],
            'reason': (reason.group(1).strip() if reason else '')[:60],
            'basis': (basis.group(1).strip() if basis else ''),
            'sug': (sug.group(1).strip() if sug else ''),
            'url': url.group(0).rstrip('）)') if url else None,
            'raw': one,
        })
    return items


def prd_head(report, concl, n):
    """结论行：直接从报告里逐字取（报告本来就是 PRD 那行）。"""
    m = re.search(r'【审查结论：\w+】共发现\s*\d+\s*处[^。]*。', report or '')
    if m:
        return m.group(0)
    verb = '必须修改' if concl == 'BLOCK' else '需人工确认'
    return f'【审查结论：{concl}】共发现 {n} 处{verb}。'


def old_block(old_cell):
    """旧格里的【逐条依据（落库留痕）】原样取出（历史留痕，不动）。"""
    m = re.search(r'【逐条依据（落库留痕）】(.*)$', old_cell, re.S)
    return m.group(1).strip() if m else ''


def old_readings(old_cell):
    """旧格里那一段**读数**（双轨合并：卡内总数 N 处（库侧 X 条机器读数 ＋ 模型侧 Y 条…）／
    P0 快路边界 ／ 链没跑成 ／ 拒答原因码）—— Owner 2026-10-09：「库侧那个读数不许丢，
    留在汇总格里」。只摘掉「链已跑完（Ns）…核对落表。」这句**样板**（2026-10-15 说的噪声）。"""
    head = old_cell.split('【逐条依据（落库留痕）】')[0]
    head = re.sub(r'⚠️[^\n]*', '', head)                      # 口径行由 old_notes 单独取
    head = re.sub(r'链已跑完（\d+s）。结论原文见对话与报告；本行由守衡在链返回后核对落表。\s*', '', head)
    return [x.strip(' ｜|') for x in re.split(r'\n+', head) if x.strip(' ｜|')]


def old_notes(old_cell):
    """旧格里那几句口径说明（⚠️ …），原样保留。"""
    return [s.strip() for s in re.findall(r'⚠️[^\n]*', old_cell) if s.strip()]


def build(row, report):
    concl = row.get('Agent 结论') or ''
    n = row.get('问题数量') or 0
    conf = row.get('置信度')
    old = plain(row.get('问题分类汇总'))
    url = ('https://momcozy-in.feishu.cn/docx/' + tok_of(row.get(LINK_COL))) if tok_of(row.get(LINK_COL)) else ''
    items = parse_items(report) if report else []
    parts = []

    if concl == 'PASS':
        head = '【审查结论：PASS】未发现已知底线风险，可转交 @sign-off 责任人（未配置）进行 sign-off。'
        parts.append(head)
    elif n >= 3:
        parts.append(prd_head(report, concl, n))
        counts = collections.Counter(i['cat'] for i in items)
        rows = [f'· {k}类问题：{v} 个' for k, v in counts.most_common()]
        if not rows:
            rows = ['·（本次没有并进任何逐条）']
        if n > len(items):
            rows.append(f'· 另有 **{n - len(items)} 条**（明细在报告里）')
        parts.append('\n'.join(rows))
        if url:
            parts.append(f'→ 查看完整问题清单与修改建议：{url}')
        parts.append(ACTION_BLOCK if concl == 'BLOCK' else ACTION_REVIEW)
    else:
        parts.append(prd_head(report, concl, n))
        blocks = []
        for i, it in enumerate(items, 1):
            blk = f"{i}.【{it['cat']}】{it['loc']}"
            if it['label']:
                blk += f" —— {it['label']}"
            if it['reason']:
                blk += f"\n   原因：{it['reason']}"
            if it['basis']:
                blk += f"\n   依据：{it['basis']}"
            if it['sug']:
                blk += f"\n   建议：{it['sug']}"
            blocks.append(blk)
        if blocks:
            parts.append('\n\n'.join(blocks))
            # 报告声明 N 处、却只列出 M 条（M4 那一类）⇒ 差额要有一行交代，
            # 否则读者把列出的条数当成全部（「卡内算术不闭合」）
            if n > len(items):
                parts.append(f'· 另有 **{n - len(items)} 条**（明细在报告里）')
        elif old_block(old):
            parts.append('【逐条依据（落库留痕）】\n' + old_block(old))
        else:
            # 报告自己就说「没有并进任何条目」—— 照实搬，别留一个让人以为漏填的空
            mk = re.search(r'（本单没有并进任何条目。）', report or '')
            parts.append(mk.group(0) if mk else '（本单没有并进任何逐条 —— 明细见报告）')
        parts.append(ACTION_BLOCK if concl == 'BLOCK' else ACTION_REVIEW)

    # ≥3：另附逐条依据（每条带 url；无源的照实标注）—— Owner 2026-10-15 第 2 条
    if concl != 'PASS' and n >= 3:
        lines = []
        for i, it in enumerate(items, 1):
            tail = it['basis'] or ('无库内依据 —— 本条报告未给依据（需人工复核）' if not it['url'] else '')
            if not tail and it['url']:
                tail = it['url']
            lines.append(f"{i}.【{it['cat']}】{it['loc']}｜{it['reason']} → {tail}".rstrip(' →'))
        if not lines and old_block(old):
            lines = [l for l in old_block(old).split('\n') if l.strip()]
        if lines:
            parts.append('【逐条依据（落库留痕）】\n' + '\n'.join(lines))

    notes = old_notes(old)
    # 口径说明只在真有对应读数时保留（置信度=0 那句必须留，否则那个 0 没人看得懂）
    keep = [s for s in notes if ('置信度' in s and '0' in s) or ('产品线' in s or '渠道' in s)]
    # ★ 2026-10-15：**读数句必须留在格里**（Owner 2026-10-09 裁定；守衡侧同一条由 V6 判据钉着）。
    #   上一版重写漏了它 —— 只剩 ⚠️ 口径行，于是「卡内总数 / 库侧 N 条机器读数」在表里消失。
    keep = old_readings(old) + keep
    if conf == 0 and not any('置信度' in s for s in keep):
        keep.insert(0, '⚠️ 置信度按 **0** 记 —— 0 = 引擎未做判定，不是「零风险」。')
    if keep:
        parts.append('\n'.join(keep))
    return '\n\n'.join(p for p in parts if p).strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--apply', action='store_true')
    a = ap.parse_args()
    rows = [json.loads(l) for l in open(SNAP, encoding='utf-8') if l.strip()]
    # record_id 映射（ndjson 不带 record_id ⇒ 拉 json 形态一次）
    r = subprocess.run([LARK, 'base', '+record-list', '--base-token', BASE, '--table-id', TABLE,
                        '--view-id', 'vewhS7Rwx0', '--page-size', '200', '--profile', 'dsh-kb',
                        '--as', 'bot', '--format', 'json'], capture_output=True, text=True)
    d = json.loads(r.stdout)['data']
    idx = d['fields'].index('内容 ID')
    rid = {row[idx]: d['record_id_list'][i] for i, row in enumerate(d['data'])}

    new = {}
    for row in rows:
        rep = load_report(tok_of(row.get(LINK_COL)))
        new[row['内容 ID']] = build(row, rep)
    json.dump(new, open(os.path.join(OUT, 'huizong_prd_new.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)

    stat = collections.Counter()
    for row in rows:
        old, nw = plain(row.get('问题分类汇总')), new[row['内容 ID']]
        stat['行数'] += 1
        stat['旧字'] += len(old)
        stat['新字'] += len(nw)
        if not re.search(r'·\s*[^·\n]{1,16}类问题', nw) and (row.get('问题数量') or 0) >= 3:
            stat['缺分类块'] += 1
        if not re.search(r'https?://|无库内依据|无库内条款', nw) and (row.get('问题数量') or 0) > 0:
            stat['缺依据'] += 1
    print('== 预览统计 ==')
    print(f"   行数 {stat['行数']} ｜ 旧 {stat['旧字']} 字 → 新 {stat['新字']} 字"
          f"（{stat['新字']*100//max(stat['旧字'],1)}%）")
    print(f"   ≥3 却没有分类块的行: {stat['缺分类块']} ｜ 有问题却既无 url 也无「无依据」标注的行: {stat['缺依据']}")

    show = ['MC-US-WEB-IMG-8435496550598', 'MC-US-WEB-IMG-7876725145798',
            'MC-US-WEB-COL-black-friday-breast-pumps', 'MC-US-AMT-unknown']
    for cid in show:
        if cid not in new:
            continue
        row = [x for x in rows if x['内容 ID'] == cid][0]
        print(f"\n----- {cid} ｜ {row.get('Agent 结论')}/{row.get('问题数量')} ｜ 新格 {len(new[cid])} 字 -----")
        print(new[cid][:1100])

    if not a.apply:
        print('\n（--dry-run：什么都没写）')
        return 0

    payload = {'update_records': {rid[cid]: {'问题分类汇总': nw} for cid, nw in new.items() if cid in rid}}
    json.dump(payload, open(os.path.join(OUT, 'huizong_prd_payload.json'), 'w', encoding='utf-8'),
              ensure_ascii=False)
    print(f"\n准备写 {len(payload['update_records'])} 行…")
    q = subprocess.run([LARK, 'base', '+record-batch-update', '--base-token', BASE, '--table-id', TABLE,
                        '--json', json.dumps(payload, ensure_ascii=False), '--profile', 'dsh-kb',
                        '--as', 'bot'], capture_output=True, text=True)
    print('rc', q.returncode, (q.stdout or '')[:200].replace('\n', ' '))
    if q.returncode != 0:
        print('ERR', q.stderr[:300]); return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())