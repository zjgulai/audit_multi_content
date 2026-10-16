#!/usr/bin/env python3
"""Owner 2026-10-16 追问：「80 条数据的**每个字段**内容和审查报告都是对应的吧？」——逐行逐字段核。

分三类说清楚（**不许混成一句"都对上了"**）：

  A. **报告里有对应物**（能逐字/逐数比）——
     `Agent 结论` ｜ `问题数量` ｜ `问题分类汇总`（分类计数 / 逐条明细 / 动作行）｜ `10/14重跑报告链接`
  B. **报告里根本没有这一格**（**无从比**，不是"对不上"）——
     `置信度` ｜ `状态` ｜ `产品线` ｜ `渠道` ｜ `送审版本` ｜ `内容 ID` ｜ `内容类型` ｜ `采集数据` ｜
     `审核人` ｜ `人工复核人` ｜ `复核结论` ｜ `sign-off 人` ｜ `发布时间`
     ⇒ 这几格改用**它们各自的源**核对：守衡台账（`write_back_fields` = 这条链当时写下去的值）／
       引擎旁挂／素材采集件。台账也没有的（人是空的、采集件另存）**如实标「无源可核」**。
  C. **格式合规**：格内是否混进了**不属于 PRD §5.3 块**的东西（口径行、双轨计数、机器读数、留底…）。

用法：
  python3 audit_fields_vs_report.py                      # 全量 80 行
  python3 audit_fields_vs_report.py --json out/x.json
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'out')
LARK = os.path.expanduser('~/.dsh/bin/lark-cli')
BASE, TABLE = 'RY2UbCRjXaeeWwscUPScVN5AnQc', 'tblavfbMDMeRsulo'
# ★ 2026-10-16（Owner 改名同步）：「10/14重跑报告链接」→ **「报告链接」**，同一个字段。
#   列名**不许写死**（写死过一次就出过事：批跑器那个"转超链接"的分支从来没执行，写出 7 格黑字）。
#   判据在 `link_col.py`（唯一一份），新旧名字都认。
from link_col import LINK_COL_CANDIDATES, pick_link            # noqa: E402
LINK_LABEL = '报告链接'                                        # 报表里显示用（跟 Owner 的新名字走）
COL = LINK_LABEL
LEDGER = os.path.expanduser('~/Project/audit_multi_content/PMO/shouheng-state/batch-review.json')

#: ★ 2026-10-16：**已查清、且有出处的**「格内 ≠ 台账快照」——写成数据不写成散文。
#:   判据：只有在**格内那份报告与台账那份是同一份**（同一轮）时才用得上它；
#:   跨轮的（基线过期）走上面那条分支，不靠这张表。
#:   逐条出处：
#:     · 行 46 `MC-US-YT-RLF9-789hh8-WEN` 的 `置信度`：格内 `0.85` 是 2026-10-15 的**有据回填**
#:       （`采集-20261013/backfill_confidence_notes.py`，依据是当轮运行日志逐字
#:        `置信度(两侧合并)=0.85 [confirm]（库侧 — / 模型侧 confirm）`，见
#:        `交付-置信度两侧合并-20261015.md`）；台账 `write_back_fields` 记的是**更早一次**写回的快照（0）。
KNOWN_DELTAS = {
    ('MC-US-YT-RLF9-789hh8-WEN', '置信度'):
        '格内 0.85 是 2026-10-15 有据回填（当轮日志逐字可查 `0.85 [confirm]`）；'
        '台账快照（更早一轮写回）记的是 0 —— 两个数各有出处，**格内那个有运行日志为证**',
}

PRD_CATS = ['合规', '消费者安全', '品牌信任', '经营风险', '产品准确性', '措辞表达', '人物肖像与 AI', '其他']
# 格内**不该有**的东西（不属于 PRD §5.3 块）——命中即"格式不合规"，逐条列出来
# ★ 判据要**窄**（第一版把条目正文里的「锚点」「复核」也算进去了 ⇒ 假红一片）：
#   只认"整行是内部读数"的那些行，不认正文里出现的词。
EXTRA_LINE_PAT = re.compile(r'^\s*(⚠️|注：|口径：|【置信度口径)|.*(双轨合并：卡内总数|两侧合并 · 档位|机器读数|留底：|未标定)')


def plain(v):
    if v is None:
        return ''
    if isinstance(v, str):
        return v
    if isinstance(v, list):
        return ''.join(plain(x) for x in v)
    if isinstance(v, dict):
        return str(v.get('link') or v.get('text') or '')
    return str(v)


def tok_of(s):
    m = re.search(r'/docx/([A-Za-z0-9]+)', str(s or ''))
    return m.group(1) if m else ''


def read_table():
    p = '/tmp/audit_fields_tbl.ndjson'
    subprocess.run([LARK, 'base', '+record-list', '--base-token', BASE, '--table-id', TABLE,
                    '--limit', '2000', '--format', 'ndjson', '--output', p, '--overwrite',
                    '--profile', 'dsh-kb', '--as', 'bot'], capture_output=True, text=True, cwd='/tmp')
    return [json.loads(l) for l in open(p, encoding='utf-8') if l.strip()]


def fetch_doc(t, tries=2):
    for k in range(tries):
        q = subprocess.run([LARK, 'docs', '+fetch', '--doc', t, '--profile', 'dsh-kb', '--as', 'bot',
                            '--doc-format', 'markdown'], capture_output=True, text=True, cwd='/tmp')
        try:
            return json.loads(q.stdout)['data']['document']['content']
        except Exception:                                        # noqa: BLE001
            if k + 1 < tries:
                time.sleep(1.5)
    return None



# ═══════════════════ 2026-10-16 新增的两条判据（纯函数：main 与 --selftest 共用）═══════════════════
def gap_verdict(report_text, n, n_items, cell):
    """报告「结论行处数 vs 逐条条数」怎么判。返回 (problems, notes)。"""
    probs, notes = [], []
    if n is None or n_items is None:
        return probs, notes
    gap = n - n_items
    exp_n = None
    if gap > 0:
        m = re.search(r'另有\s*(\d+)\s*条[^。]{0,40}?没有逐条明细', report_text or '')
        exp_n = int(m.group(1)) if m else None
    if gap != 0 and exp_n != gap:
        probs.append(f"报告自相矛盾：结论行写 {n} 处，逐条只有 {n_items} 条"
                     + (f"（末尾说明写的是 {exp_n} 条，对不上差额 {gap}）" if exp_n
                        else "，且报告里没有任何说明"))
    elif gap > 0:
        notes.append(f"报告已说明：结论行 {n} 处 ／ 逐条 {n_items} 条，"
                     f"差额 {gap} 条**没有逐条明细**（库侧只报到条数）")
        more = (re.search(r'·\s*另有\s*(\d+)\s*条', cell or '') or [None, None])[1]
        if more and '未并进明细' not in (cell or ''):
            probs.append(f"格内写「另有 {more} 条（明细在报告里）」，"
                         f"报告已写明这 {gap} 条**没有逐条明细** ⇒ 两句打架")
    return probs, notes


def ledger_verdict(got, wrote_s, link, led_tok, cid, field):
    """格内那一格 vs 台账快照（`write_back_fields`）怎么判。返回 (problem, note, verdict)。"""
    if got == wrote_s:
        return None, None, '✅'
    if led_tok and link and led_tok != link:
        return None, (f"{field}：格内 {got!r} ≠ 台账快照 {wrote_s!r}，"
                      f"但**格内那份报告与台账那份不是同一份**（{link} ≠ {led_tok}）"
                      f"⇒ 台账基线过期，以格内为准"), '✅（台账基线过期）'
    why = KNOWN_DELTAS.get((cid, field))
    if why:
        return None, f"{field}：格内 {got!r} ≠ 台账快照 {wrote_s!r} —— {why}", '✅（有据回填，见注）'
    return (f"{field}：格内 {got!r} ≠ 台账写回的 {wrote_s!r}（跑完之后被谁改过）", None, '❌')



def catmix_verdict(cat_counts, dims, gap=0):
    """格内「· XX类问题：N 个」↔ 报告逐条的类别 —— **逐类**核，不只核总数。

    为什么必须逐类（2026-10-16 Owner「再查一遍」时抓到的）：
      行 52 格内写「产品描述 1／合规 1／措辞表达 1」，而**链接列指的那份报告**是
      「产品描述 1／措辞表达 2」——**总数都是 3、逐类对不上** ⇒ 只核总数的尺子全绿，
      读者按列里的链接点开，看到的却是另一份报告。
    口径：`gap>0`（库侧明细没并进来）时，格内每一类都 ≥ 报告里那一类，且差额合计 == gap；
          没有缺口时**逐类必须完全相等**。
    """
    probs = []
    cell_c = {k: v for k, v in (cat_counts or {}).items() if not k.startswith('（另有')}
    rep_c = {}
    for d in (dims or []):
        rep_c[d] = rep_c.get(d, 0) + 1
    if not cell_c:
        return probs                                   # 逐条版式：不走这条
    # ⚠️ 明细缺口（gap）**不进这里比**：缺的那几条**连类别都不知道**，
    #   所以格内分类计数只反映"并进清单里那几条"，与报告的条目**逐类必须完全相等**。
    #   （第一版写成「差额合计 == gap」⇒ 5 行假红，当场改掉。）
    for k in sorted(set(cell_c) | set(rep_c)):
        a, b = cell_c.get(k, 0), rep_c.get(k, 0)
        if a == b:
            continue
        probs.append(f"分类对不上：格内「{k}」{a} 个 ／ 报告里 {b} 条"
                     + ('（**总数一样、逐类对不上** ⇒ 列里那份不是这一格对应的报告）'
                        if sum(cell_c.values()) == sum(rep_c.values()) else ''))
    return probs


def selftest():
    """反向对照：**没有说明**的差额必须照旧红；说明对不上差额也要红；跨轮的才允许不红。"""
    cases = [
        ('① 差额已说明（说明的 N == 差额）⇒ 不红，记 ℹ️',
         ('…共发现 9 处必须修改。\n1.【合规】x\n\n⚠️ 另有 3 条**没有逐条明细**…', 9, 6,
          '【审查结论：BLOCK】共发现 9 处必须修改。\n· 另有 3 条（**未并进明细**：库侧只报到条数）'), 'ok'),
        ('② 差额**没有说明** ⇒ 必须红',
         ('…共发现 9 处必须修改。\n1.【合规】x', 9, 6, '· 另有 3 条（明细在报告里）'), 'red'),
        ('③ 说明的 N 对不上差额 ⇒ 必须红',
         ('…共发现 9 处必须修改。\n1.【合规】x\n⚠️ 另有 2 条没有逐条明细', 9, 6, '· 另有 3 条（明细在报告里）'), 'red'),
        ('④ 说明有了、但格内仍写「明细在报告里」⇒ 两句打架，必须红',
         ('…共发现 9 处必须修改。\n1.【合规】x\n⚠️ 另有 3 条没有逐条明细', 9, 6, '· 另有 3 条（明细在报告里）'), 'red'),
        ('⑤ 差额为 0 ⇒ 一个字都不加',
         ('…共发现 3 处必须修改。\n1.【合规】x', 3, 3, '· 合规类问题：3 个'), 'ok'),
    ]
    bad = 0
    for name, (txt, n, ni, cell), want in cases:
        probs, notes = gap_verdict(txt, n, ni, cell)
        got = 'red' if probs else 'ok'
        good = (got == want) and (want != 'ok' or notes or n == ni)
        bad += 0 if good else 1
        print(f"  {'✅' if good else '✗'} {name} ⇒ {got}")
    for name, cc, dims, gap, want in [
        ('⑩ 逐类完全一致 ⇒ 绿', {'产品描述': 1, '合规': 1, '措辞表达': 1},
         ['产品描述', '合规', '措辞表达'], 0, False),
        ('⑪ 总数一样、**逐类对不上** ⇒ 必须红（行 52 那种）', {'产品描述': 1, '合规': 1, '措辞表达': 1},
         ['产品描述', '措辞表达', '措辞表达'], 0, True),
        ('⑫ 有明细缺口（缺口不进这一类比）⇒ 逐类相等就绿', {'合规': 1, '措辞表达': 2},
         ['合规', '措辞表达', '措辞表达'], 1, False),
        ('⑬ 格内某一类**少于**报告 ⇒ 必须红', {'合规': 2, '措辞表达': 1},
         ['合规', '措辞表达', '措辞表达'], 0, True),
    ]:
        got = bool(catmix_verdict(cc, dims, gap))
        good = (got == want)
        bad += 0 if good else 1
        print(f"  {'✅' if good else '✗'} {name} ⇒ {'red' if got else 'ok'}")
    led = [
        ('⑥ 台账基线过期（报告 token 不同）⇒ 不红',
         ('3', '4', 'AAA', 'BBB', 'X', '问题数量'), None),
        ('⑦ 同一份报告、值不同 ⇒ 必须红',
         ('3', '4', 'AAA', 'AAA', 'X', '问题数量'), 'red'),
        ('⑧ 值相同 ⇒ 绿', ('3', '3', 'AAA', 'AAA', 'X', '问题数量'), None),
        ('⑨ 已查清的有据回填 ⇒ 不红（出处在 KNOWN_DELTAS）',
         ('0.85', '0', 'AAA', 'AAA', 'MC-US-YT-RLF9-789hh8-WEN', '置信度'), None),
    ]
    for name, args, want in led:
        prob, note, verdict = ledger_verdict(*args)
        got = 'red' if prob else 'ok'
        good = ((got == 'red') == (want == 'red'))          # want=None ⇒ 期望"不红"
        bad += 0 if good else 1
        print(f"  {'✅' if good else '✗'} {name} ⇒ {got}")
    print('selftest ' + ('全绿' if bad == 0 else f'{bad} 项红'))
    return 0 if bad == 0 else 1


def parse_report(c):
    """报告正文 → {state, n, dims[], seen_action}。"""
    if c is None:
        return None
    m = re.search(r'【审查结论：(\w+)】', c)
    n = re.search(r'共发现\s*(\d+)\s*处', c)
    dims = re.findall(r'^\s*\d+\.【([^】]+)】', c, re.M)
    return {'state': m.group(1) if m else None,
            'n': int(n.group(1)) if n else None,
            'text': c,                       # ★ 2026-10-16：新判据要读报告末尾那句「没有逐条明细」说明
            'dims': dims,
            'n_items': len(dims),
            'action': ('请修改后重新提交' if '请修改后重新提交' in c else
                       ('建议转' if '建议转' in c else ('sign-off' if 'sign-off' in c else None)))}


def parse_cell(s):
    """格内 → {state, n, cats{}, items[], link, extras[], action}。"""
    m = re.search(r'【审查结论：(\w+)】', s)
    n = re.search(r'共发现\s*(\d+)\s*处', s)
    cats = {k: int(v) for k, v in re.findall(r'·\s*([^·\n]+?)类问题：\s*(\d+)\s*个', s)}
    # 「· 另有 N 条（明细在报告里）」也是**这一单的问题数的一部分** —— 不加上它，
    #   分类合计会凭空少一截（第一版就是因此把好几行判成"合计≠问题数"的假红）。
    more = re.search(r'·\s*另有\s*(\d+)\s*条', s)
    if more:
        cats['（另有，明细未并入）'] = int(more.group(1))
    items = re.findall(r'^\s*(\d+)\.【([^】]+)】(.*)$', s, re.M)
    extras = sorted({ln.strip()[:24] for ln in s.split('\n') if EXTRA_LINE_PAT.match(ln)})
    return {'state': m.group(1) if m else None,
            'n': int(n.group(1)) if n else None,
            'cell': s,                       # ★ 2026-10-16：判「另有 k 条」的措辞要用原格
            'cats': cats, 'cats_sum': sum(cats.values()),
            'items': [(i, d, rest.strip()[:60]) for i, d, rest in items],
            'n_items': len(items),
            'link': tok_of(re.search(r'https?://\S+', s).group(0)) if re.search(r'https?://\S+', s) else '',
            'extras': extras,
            'action': ('请修改后重新提交' if '请修改后重新提交' in s else
                       ('建议转' if '建议转' in s else ('sign-off' if 'sign-off' in s else None)))}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--json')
    ap.add_argument('--selftest', action='store_true', help='反向对照：两条新判据不许恒绿')
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    rows = read_table()
    led = json.load(open(LEDGER, encoding='utf-8')).get('items') or {}

    bad, nocmp, okn = [], [], 0
    explained = []      # ★ 2026-10-16：差额**已说明**的行（不算红 —— 报告末尾逐字写了为什么）
    field_stat = {}
    def bump(f, verdict):
        field_stat.setdefault(f, {}).setdefault(verdict, 0)
        field_stat[f][verdict] += 1

    for i, r in enumerate(rows, 1):
        g = lambda k: plain(r.get(k))          # noqa: E731
        cid = g('内容 ID')
        cell = g('问题分类汇总')
        pc = parse_cell(cell)
        more_claim = (re.search(r'·\s*另有\s*(\d+)\s*条', cell) or [None, None])[1]
        link = tok_of(pick_link(r))
        doc = fetch_doc(link) if link else None
        pr = parse_report(doc) if link else None
        it = led.get(cid) or {}
        wb = it.get('write_back_fields') or {}
        probs = []
        notes = []          # ★ 2026-10-16：『已说明』的读数（不算红，但要留痕）

        # ── A 组：报告里有的那几格 ───────────────────────────────────────────
        if link:
            if doc is None:
                probs.append('链接打不开（docs +fetch 失败）')
                for f in (LINK_LABEL, 'Agent 结论', '问题数量',
                          '问题分类汇总（一个字段：内容一致 ∧ 只放 PRD 块）'):
                    bump(f, '❌')
            else:
                bump(LINK_LABEL, '✅')
                if pr['state'] != pc['state']:
                    probs.append(f"结论：格内 {pc['state']} ／ 报告 {pr['state']}")
                    bump('Agent 结论', '❌')
                else:
                    bump('Agent 结论', '✅')
                if pr['n'] != pc['n']:
                    probs.append(f"问题数：格内 {pc['n']} ／ 报告 {pr['n']}")
                    bump('问题数量', '❌')
                else:
                    bump('问题数量', '✅')
                # ── 报告逐条条数 vs 报告自己写的 N（判据抽在 `gap_verdict()`，与 selftest 同一份）──
                _gp, _gn = gap_verdict(pr.get('text'), pr['n'], pr['n_items'], pc.get('cell'))
                probs.extend(_gp); notes.extend(_gn)
                # ★ 2026-10-16 加：**逐类**核（总数一样、类别不同 ⇒ 这不是这一格对应的那份报告）
                _gapn = max(0, (pr['n'] or 0) - (pr['n_items'] or 0))
                probs.extend(catmix_verdict(pc.get('cats'), pr.get('dims'), _gapn))
                # 格内分类计数合计 == N；格内逐条条数 == N（两种版式二选一）
                if pc['cats']:
                    if pc['cats_sum'] != pc['n']:
                        probs.append(f"格内分类计数合计 {pc['cats_sum']} ≠ 格内问题数 {pc['n']}")
                    if pc['n_items']:
                        probs.append('格内同时有分类计数与逐条明细（PRD 二选一）')
                elif pc['n_items']:
                    if pc['n_items'] != pc['n']:
                        probs.append(f"格内逐条 {pc['n_items']} 条 ≠ 格内问题数 {pc['n']}")
                else:
                    probs.append('格内既没有分类计数也没有逐条明细')
                # 动作行**只查格内自洽**（PRD §8.3 没要求报告带动作行；条目正文里的
                # 「建议转人工」是依据文案，不是动作行 —— 第一版拿它当动作行 ⇒ 一排假红）
                want_act = {'BLOCK': '请修改后重新提交', 'REVIEW': '建议转', 'PASS': 'sign-off'}.get(pc['state'])
                if want_act and pc['action'] != want_act:
                    probs.append(f"格内动作行与自己的结论不符：{pc['state']} 却写 {pc['action']}")
                _cnt_bad = any(p.startswith(('格内', '报告自相', '格内写')) for p in probs)
                _fmt_bad = bool(pc['extras'])
                bump('问题分类汇总（一个字段：内容一致 ∧ 只放 PRD 块）',
                     '❌' if (_cnt_bad or _fmt_bad) else '✅')
        else:
            # 没有链接的行：只有 PASS 允许（PRD：PASS 不出报告）
            if pc['state'] == 'PASS':
                bump(LINK_LABEL, '✅（PASS 无报告，符合口径）')
                bump('Agent 结论', '✅')
                bump('问题数量', '✅')
                bump('问题分类汇总（一个字段：内容一致 ∧ 只放 PRD 块）', '✅')
            else:
                probs.append(f"{pc['state'] or '(无结论)'} 却没有报告链接")
                for f in (LINK_LABEL, 'Agent 结论', '问题数量',
                          '问题分类汇总（一个字段：内容一致 ∧ 只放 PRD 块）'):
                    bump(f, '❌')

        # ── B 组：报告里没有的格 ⇒ 拿**各自的源**核（台账 write_back_fields）────
        if wb:
            for f in ('置信度', '状态', '问题数量', 'Agent 结论'):
                got = g(f).strip()
                wrote = wb.get(f)
                wrote_s = '' if wrote is None else str(wrote).strip()
                if wrote_s == '':
                    bump(f, '—（台账没记这一格）')
                    continue
                # ★★ 2026-10-16：**先分清两种"对不上"**（判据抽在 `ledger_verdict()`）——
                #   ① 台账**基线过期**（格内链接的报告 ≠ 台账那份报告）⇒ 记 ℹ️，以格内为准；
                #   ② 同一轮内被改过 ⇒ 照旧红，并点明"跑完之后被谁改过"。
                prob, note, verdict = ledger_verdict(got, wrote_s, link,
                                                     tok_of(str(it.get('report_url') or '')), cid, f)
                if prob: probs.append(prob)
                if note: notes.append(note)
                bump(f + '（对台账）', verdict)
        else:
            for f in ('置信度', '状态'):
                bump(f, '无源可核（台账没有这一单）')
        for f in ('产品线', '渠道', '送审版本', '内容 ID', '内容类型', '采集数据',
                  '审核人', '人工复核人', '复核结论', 'sign-off 人', '发布时间'):
            bump(f, '⊘ 报告里没有这一格（无从比）')

        # ── C 组：格内格式 ────────────────────────────────────────────────
        if pc['extras']:
            probs.append('格内混进非 PRD 内容：' + '、'.join(pc['extras']))
        # ★ `问题分类汇总` 只报**一次**（Owner 2026-10-16：「怎么有两个字段？只保留一个」）——
        #   它是一个字段，上面那两处 bump 已经把"内容一致 ∧ 只放 PRD 块"合成了一个判定。

        if probs:
            bad.append({'row': i, 'cid': cid, 'state': pc['state'], 'n': pc['n'], 'link': link,
                        'probs': probs, 'notes': notes})
        else:
            okn += 1
            if notes:
                explained.append({'row': i, 'cid': cid, 'notes': notes})

    print(f'80 行逐字段核对：全对 {okn} ｜ **有问题 {len(bad)}**'
          + (f' ｜ 其中 {len(explained)} 行的差额已在报告里说明（明细在库侧从未抽出）' if explained else ''))
    for e in explained[:8]:
        print(f"  ℹ️ 行 {e['row']} {e['cid'][:44]} —— " + '；'.join(e['notes'])[:130])
    for b in bad:
        print(f"  行{b['row']:>2} {b['state']}/{b['n']} {b['link'] or '(无链接)':<28} {'；'.join(b['probs'])}｜{b['cid'][:40]}")
    print('\n按字段：')
    for f, d in field_stat.items():
        print(f"  {f}: " + ' ｜ '.join(f'{k}×{v}' for k, v in sorted(d.items(), key=lambda x: -x[1])))
    if a.json:
        os.makedirs(OUT, exist_ok=True)
        json.dump({'at': time.strftime('%Y-%m-%d %H:%M:%S'), 'ok': okn, 'bad': bad,
                   'explained': explained, 'field_stat': field_stat}, open(a.json, 'w', encoding='utf-8'),
                  ensure_ascii=False, indent=1)
        print('留痕 →', a.json)
    return 0 if not bad else 3


if __name__ == '__main__':
    sys.exit(main())
