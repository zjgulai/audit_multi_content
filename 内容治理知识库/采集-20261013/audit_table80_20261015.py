#!/usr/bin/env python3
"""80 行整表核对：**数据准确性 + 一致性**（Owner 2026-10-15：「跑完后核对整个表格的数据准确性和一致性」）。

五组判据（全部机械可复算；每条都能指出是哪一行、错在哪）：

  A 结构与必填   —— 行数 / 内容 ID 唯一 / 类型三档 / 结论三态 / 状态三档（PRD §8.2）/ 数量非负
  B §5.3 格格式  —— 结论行 == Agent 结论；`问题数量 ≥ 3` ⇒ **必须有报告链接行**（§5.3.5）；
                    动作行与三态匹配（BLOCK=请修改后重新提交。／REVIEW=建议转 @… 复核。／PASS=…sign-off）；
                    分类计数 ＋「另有 N 条」**必须闭合到 `问题数量`**
  C 同源一致     —— 格里的链接 == `10/14重跑报告链接` 列；格 == **卡**（台账 message_id 取回真卡，
                    比动作行／计数行／链接行）；采集表 == **结论表最新同素材行**（结论／数量／置信度）
  D 素材质量     —— 乱码指纹 = 0（双编码）；品类**必须**在 吸奶器/清洗机/婴儿监控器 内；
                    图片=直链+图注、视频/文案有来源；素材长度非空
  E 人的列       —— 人工复核人／复核结论／sign-off 人／审核人／发布时间 **不被机器写入**（与基线比）

用法：
  python3 audit_table80_20261015.py                 # 全量核对
  python3 audit_table80_20261015.py --baseline      # 先落一份行基线（第一次跑时必须先落）
"""
import argparse, collections, importlib.util, json, os, re, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
LARK = os.path.expanduser('~/.dsh/bin/lark-cli')
BASE, TABLE, RESULT_TABLE = 'RY2UbCRjXaeeWwscUPScVN5AnQc', 'tblavfbMDMeRsulo', 'tblCXPQVzfFWWCon'
LEDGER = '/Users/lute/Project/audit_multi_content/PMO/shouheng-state/batch-review.json'
BASE_FILE = os.path.join(HERE, 'out', 'audit80_baseline.json')
MOJI = re.compile(r'[âÃï][\x80-\xbf]')
STATES_3 = ('待审', '已修改', '已发布')
CONCLUSIONS = ('PASS', 'REVIEW', 'BLOCK', 'NEEDS_INPUT')
HUMAN_COLS = ['人工复核人', '复核结论', 'sign-off 人', '审核人', '发布时间']


def load_collector():
    spec = importlib.util.spec_from_file_location('ct', os.path.join(HERE, 'collect_tupian35.py'))
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


def read_table(table, out):
    subprocess.run([LARK, 'base', '+record-list', '--base-token', BASE, '--table-id', table,
                    '--limit', '2000', '--format', 'ndjson', '--output', out, '--overwrite',
                    '--profile', 'dsh-kb', '--as', 'bot'], capture_output=True, text=True, cwd='/tmp')
    return [json.loads(l) for l in open(out, encoding='utf-8') if l.strip()]


def norm(s):
    return re.sub(r'\s+', ' ', str(s or '')).strip()


def cell_lines(cell):
    return [l.strip() for l in str(cell).splitlines() if l.strip()]


def check(rows, res_rows, cards, cat_of, baseline):
    V = collections.defaultdict(list)          # 违规登记：维度 → [明细]
    info = collections.Counter()

    # ── A 结构 ────────────────────────────────────────────────────────────────
    ids = [plain(r.get('内容 ID')) for r in rows]
    if len(rows) != 80:
        V['A 行数'].append(f'表里有 {len(rows)} 行（期望 80）')
    dup = {k for k, n in collections.Counter(ids).items() if n > 1 and k}
    if dup:
        V['A 内容ID唯一'].append(f'重复：{sorted(dup)}')
    for r in rows:
        cid = plain(r.get('内容 ID'))
        for col in ('内容 ID', '采集数据', '内容类型'):
            if not plain(r.get(col)).strip():
                V[f'A 必填-{col}'].append(cid or r.get('record_id'))
        t = plain(r.get('内容类型')).strip()
        if t not in ('文案', '图片', '视频'):
            V['A 内容类型'].append(f'{cid} ⇒ {t!r}')
        st = plain(r.get('状态')).strip()
        if st and st not in STATES_3:
            V['A 状态三档'].append(f'{cid} ⇒ {st!r}（PRD §8.2：待审/已修改/已发布）')
        concl = plain(r.get('Agent 结论')).strip().upper()
        if concl and concl not in CONCLUSIONS:
            V['A 结论三态'].append(f'{cid} ⇒ {concl!r}')
        info[f'类型-{t}'] += 1
        info[f'已填-{t}'] += 1 if plain(r.get('问题分类汇总')).strip() else 0
        info[f'结论-{concl or "空"}'] += 1

    # ── B §5.3 格格式 ─────────────────────────────────────────────────────────
    for r in rows:
        cid = plain(r.get('内容 ID'))
        cell = plain(r.get('问题分类汇总'))
        if not cell.strip():
            continue
        concl = plain(r.get('Agent 结论')).strip().upper()
        n = plain(r.get('问题数量')).strip()
        lines = cell_lines(cell)
        head = lines[0]
        m = re.search(r'【审查结论：(\w+)】', head)
        if not m:
            V['B 缺结论行'].append(f'{cid} ⇒ {head[:40]!r}')
        elif m.group(1).upper() != concl:
            V['B 结论行≠结论列'].append(f'{cid}：格里 {m.group(1)} vs 列 {concl}')
        if n and n.isdigit() and int(n) >= 3 and '查看完整问题清单' not in cell:
            V['B ≥3缺报告链接行'].append(f'{cid}（数量 {n}）')
        # ★ 动作行 = 以 `建议转` / `请修改后重新提交` 开头的那一行（口径说明可挂在其后，不算格式件）
        act = next((l for l in lines if l.startswith(('建议转', '请修改后重新提交'))), '')
        if not act:
            act = lines[-1] if lines else ''
        if concl == 'BLOCK' and '请修改后重新提交' not in act:
            V['B 动作行-BLOCK'].append(f'{cid} ⇒ {act[:40]!r}')
        if concl == 'REVIEW' and '复核' not in act:
            V['B 动作行-REVIEW'].append(f'{cid} ⇒ {act[:40]!r}')
        if concl == 'PASS' and 'sign-off' not in cell:
            V['B 动作行-PASS'].append(f'{cid} ⇒ {act[:40]!r}')
        # 分类汇总闭合：`· XX类问题：k 个` 之和 ＋「另有 n 条」 == 问题数量
        if n and n.isdigit():
            tot = sum(int(x) for x in re.findall(r'·\s*[^·\n]*?类问题：(\d+)\s*个', cell))
            other = re.search(r'另有\s*\*{0,2}(\d+)\s*条', cell)
            tot += int(other.group(1)) if other else 0
            if tot and tot != int(n):
                V['B 计数不闭合'].append(f'{cid}：计数合计 {tot} vs 问题数量 {n}')
        # PASS 行不该带报告链接行（§5.3.2：一句话 + 转 sign-off）
        if concl == 'PASS' and '查看完整问题清单' in cell:
            V['B PASS带链接'].append(cid)

    # ── C 同源一致 ────────────────────────────────────────────────────────────
    res_latest = {}
    for r in sorted(res_rows, key=lambda x: str(x.get('写入时间') or ''), reverse=True):
        k = norm(plain(r.get('送审问题')))[:120]
        if k and k not in res_latest:
            res_latest[k] = r

    def res_hit(row):
        """★ 按**素材类型**取键（跑批送往结论表的文本形态三种不一样，2026-10-15 校准时踩过）：
          · 文案 ⇒ `送审问题` = 素材原文 ⇒ 前 120 字**等值**匹配；
          · 图片 ⇒ `[图片]图注：<caption>` ⇒ 用**图注**做子串匹配（素材里的图直链它不存）；
          · 视频 ⇒ `[视频]<标题>…` ⇒ 用**标题行**做子串匹配。
        取**最新**那条（倒序里第一个命中）。"""
        t = plain(row.get('内容类型')).strip()
        mat = plain(row.get('采集数据'))
        if t == '图片':
            # ★ 必须带 `[图片]图注：` 前缀：同一件商品在表里**同时有文案行和图片行**（标题会撞），
            #   只按标题匹配会把文案行的记录当成本图片行的（2026-10-15 校准踩过：多出 5 条假红）。
            m = re.search(r'图注：(.+)', mat)
            key = ('[图片]图注：' + norm(m.group(1))[:50]) if m else ''
            finder = lambda x, k=key: k and norm(plain(x.get('送审问题'))).startswith(k)
        elif t == '视频':
            # ★ 视频行是**按封面图**送审的（跑批把缩略图当媒材发）⇒ 结论表里的 `送审问题` 长这样：
            #   `[图片]图注：<标题> …` —— 不再要求 `[视频]` 前缀（原先要求了，10 行全被判成"无同素材行"）。
            key = ('[图片]图注：' + norm(mat.split('\n')[0])[:50])
            finder = lambda x, k=key: k and norm(plain(x.get('送审问题'))).startswith(k)
        else:
            key = norm(mat)[:120]
            finder = lambda x, k=key: k and norm(plain(x.get('送审问题')))[:120] == k
        ordered = sorted(res_rows, key=lambda y: str(y.get('写入时间') or ''), reverse=True)
        return next((x for x in ordered if finder(x)), None)
    for r in rows:
        cid = plain(r.get('内容 ID'))
        cell = plain(r.get('问题分类汇总'))
        linkcol = plain(r.get('10/14重跑报告链接'))
        t_cell = (re.search(r'/docx/([A-Za-z0-9]+)', cell) or [None, None])[1]
        t_col = (re.search(r'/docx/([A-Za-z0-9]+)', linkcol) or [None, None])[1]
        if t_cell and t_col and t_cell != t_col:
            V['C 链接列≠格里链接'].append(f'{cid}：格 {t_cell[:10]} vs 列 {t_col[:10]}')
        if t_cell and not t_col:
            V['C 链接列空'].append(cid)
        hit = res_hit(r)
        if cell.strip() and not hit:
            V['C 结论表无同素材行'].append(cid)
        elif hit:
            for k in ('Agent 结论', '问题数量'):
                a, b = plain(r.get(k)).strip(), plain(hit.get(k)).strip()
                if a and b and a != b and not (k == '问题数量' and a in ('0',) and b in ('',)):
                    V[f'C 结论表≠采集表-{k}'].append(f'{cid}：{a!r} vs {b!r}')
            # 卡：动作行 / 计数行 / 链接行
            mid = None
            led = (cards.get('_ledger') or {})
            mid = next((m for m in (led.get(cid) or {}).get('message_ids') or []), None)
            c = cards.get(mid) if mid else None
            if c:
                # ★ 卡必须与**同一次**跑批比：台账里 message_id 可能指向**上一轮**的卡
                #   （今天 10-13/14/15 各跑过一轮）⇒ 卡里没有本行报告链接 token 的，判为**未测**，不当违规。
                t_cell_card = (re.search(r'/docx/([A-Za-z0-9]+)', cell) or [None, None])[1]
                if t_cell_card and t_cell_card not in c:
                    info['卡属上一轮（不判）'] += 1
                    c = None
            if c:
                ca = next((l.strip() for l in c.splitlines() if l.strip().startswith(('建议转', '请修改后重新提交'))), '')
                ce = next((l.strip() for l in cell_lines(cell) if l.startswith(('建议转', '请修改后重新提交'))), '')
                if ca and ce and ca != ce:
                    V['C 卡≠表-动作行'].append(f'{cid}：卡 {ca[:34]!r} vs 表 {ce[:34]!r}')
                if ('查看完整问题清单' in c) != ('查看完整问题清单' in cell):
                    V['C 卡≠表-链接行'].append(cid)

    # ── D 素材质量 ────────────────────────────────────────────────────────────
    for r in rows:
        cid = plain(r.get('内容 ID'))
        mat, t = plain(r.get('采集数据')), plain(r.get('内容类型')).strip()
        if MOJI.search(mat):
            V['D 乱码'].append(cid)
        if t in ('图片', '文案', '视频'):
            # 品类只能在三类内；判据用采集器**同一个** cat_of（图片行）+ 文案/视频按素材全文判
            k = cat_of(mat[:600])
            if k not in ('吸奶器', '清洗机', '婴儿监控器'):
                V[f'D 品类越界-{t}'].append(f'{cid} ⇒ {k}')
        if t == '图片' and 'http' not in mat:
            V['D 图片无直链'].append(cid)
        if t == '视频' and not re.search(r'(youtube\.com|youtu\.be|\.mp4)', mat):
            V['D 视频无来源'].append(cid)
        if not mat.strip():
            V['D 素材空'].append(cid)

    # ── E 人的列 ──────────────────────────────────────────────────────────────
    if baseline:
        for r in rows:
            rid = r.get('record_id')
            b = baseline.get(rid)
            if not b:
                continue
            for col in HUMAN_COLS:
                if plain(r.get(col)).strip() != str(b.get(col) or '').strip():
                    V[f'E 人的列被改-{col}'].append(f"{plain(r.get('内容 ID'))}：{b.get(col)!r} → {plain(r.get(col))!r}")
    return V, info


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--baseline', action='store_true')
    a = ap.parse_args()
    ct = load_collector()
    rows = read_table(TABLE, '/tmp/audit80_tbl.ndjson')
    res_rows = read_table(RESULT_TABLE, '/tmp/audit80_res.ndjson')
    # 卡：按台账 message_id 取回（一次批量）
    try:
        led = json.load(open(LEDGER, encoding='utf-8'))['items']
    except Exception:
        led = {}
    mids = [m for v in led.values() if isinstance(v, dict) for m in (v.get('message_ids') or [])]
    cards = {'_ledger': led}
    for i in range(0, len(mids), 50):
        q = subprocess.run([LARK, 'im', '+messages-mget', '--message-ids', ','.join(mids[i:i + 50]),
                            '--profile', 'dsh-kb', '--as', 'bot', '--json'],
                           capture_output=True, text=True, cwd='/tmp')
        try:
            for m_ in json.loads(q.stdout)['data']['messages']:
                cards[m_['message_id']] = m_.get('content', '')
        except Exception:
            pass
    if a.baseline:
        json.dump({r['record_id']: {c: plain(r.get(c)) for c in HUMAN_COLS} for r in rows},
                  open(BASE_FILE, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        print(f'已落人的列基线 → {BASE_FILE}')
    baseline = None
    if os.path.exists(BASE_FILE):
        baseline = json.load(open(BASE_FILE, encoding='utf-8'))
    V, info = check(rows, res_rows, cards, ct.cat_of, baseline)
    print('—— 结构读数 ——')
    for k in sorted(info):
        print(f'  {k}: {info[k]}')
    print(f'\n—— 违规 ——（取回卡 {len(cards) - 1} 张）')
    if not V:
        print('  ✅ 五组判据全过，0 违规')
    for k in sorted(V):
        print(f'  ❌ {k}（{len(V[k])}）')
        for x in V[k][:18]:
            print(f'       · {x}')
        if len(V[k]) > 18:
            print(f'       … 另有 {len(V[k]) - 18} 条')
    return 3 if V else 0


if __name__ == '__main__':
    sys.exit(main())
