#!/usr/bin/env python3
"""2026-10-15 Owner 五问的取证脚本（只读）：
   Q2 表内 5 格 vs `10/14重跑报告链接` 那份报告，逐行逐格比；
   Q3 报告条目构成（库侧 / 模型侧）与条数；
   Q4 非美国口径强信号扫描 + 依据来源归类；
   Q5 三态分布。
输出：out/qa5_20261015.json（明细）+ 屏幕摘要。
"""
import json, os, re, subprocess, sys, collections, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'out')
LARK = os.path.expanduser('~/.dsh/bin/lark-cli')
SRC = os.path.join(HERE, 'backup_pass_rerun_20261015-105156', 'own70_view.ndjson')

NON_US = [
    ('中国广告法/极限用语', r'广告法|极限用语|极限词|违禁词|《广告法》'),
    ('医疗器械广告审查批准文号', r'医疗器械广告审查|批准文号|药监局|NMPA'),
    ('中国国标/3C', r'\bGB\s?\d|国家标准|3C|CCC 认证'),
    ('英国 MHRA/ASA-CAP', r'MHRA|\bASA\b|CAP Code|英国广告'),
    ('欧盟/GDPR/CE', r'GDPR|欧盟|\bCE\b 认证|European Union|\bEU\b'),
    ('中国社媒/电商平台', r'小红书|朋友圈|抖音|微信|淘宝|天猫|京东|拼多多|公众号'),
    ('中文语境信号', r'中文字幕|中文标签|北京时间|中文社群'),
    ('其它辖区', r'加拿大|澳大利亚|日本|韩国|新加坡|印度'),
]
SOURCES = [
    ('FDA', r'Food and Drug Administration|FDA'),
    ('FTC', r'Federal Trade Commission|\bFTC\b'),
    ('Amazon', r'Amazon'),
    ('Google', r'Google'),
    ('Meta', r'Meta|Facebook|Instagram'),
    ('DOL/PUMP Act', r'Department of Labor|PUMP Act|\bWHD\b'),
    ('HealthCare.gov', r'HealthCare\.gov'),
    ('无外部来源（模型自述）', r'通用经验|平台惯例|行业惯例|无外部来源'),
]


def fetch(tok, cache):
    if tok in cache:
        return cache[tok]
    r = subprocess.run([LARK, 'docs', '+fetch', '--doc', tok, '--profile', 'dsh-kb', '--as', 'bot'],
                       capture_output=True, text=True, cwd='/tmp')
    c = ''
    try:
        c = json.loads(r.stdout)['data']['document']['content'] or ''
    except Exception:
        c = ''
    cache[tok] = c
    return c


def main():
    rows = [json.loads(l) for l in open(SRC, encoding='utf-8') if l.strip()]
    cache = {}
    detail = []
    for i, r in enumerate(rows, 1):
        cid = r['内容 ID']
        link = str(r.get('10/14重跑报告链接') or '')
        m = re.search(r'/docx/([A-Za-z0-9]+)', link)
        tok = m.group(1) if m else None
        zh = str(r.get('问题分类汇总') or '')
        rec = {'no': i, 'cid': cid, 'tok': tok, 'concl': r.get('Agent 结论'),
               'state': (r.get('状态') or [None])[0] if isinstance(r.get('状态'), list) else r.get('状态'),
               'conf': r.get('置信度'), 'cnt': r.get('问题数量'),
               'rep_state': None, 'rep_declared': None, 'rep_items': None,
               'side_lib': None, 'side_model': None, 'side_other': None,
               'sum_total': None, 'sum_lib': None, 'sum_model': None,
               'sum_items': len(re.findall(r'\n\s*\d+[.、]', zh)),
               'sum_tok': (re.search(r'/docx/([A-Za-z0-9]+)', zh).group(1)
                           if re.search(r'/docx/([A-Za-z0-9]+)', zh) else None),
               'conf0_note': ('置信度按 0 记' in zh or '这个 0 不是置信度' in zh or '0 = 引擎未做判定' in zh),
               'non_us': [], 'sources': []}
        if tok:
            c = fetch(tok, cache)
            mm = re.search(r'【审查结论：([A-Z_]+)】', c)
            rec['rep_state'] = mm.group(1) if mm else None
            mm = re.search(r'共发现\s*(\d+)\s*处', c)
            rec['rep_declared'] = int(mm.group(1)) if mm else None
            rec['rep_items'] = len(re.findall(r'<p>\s*\d+[.、]', c))
            # 条目分侧：库侧 = 「有库内条款依据」；模型侧 = 「无库内条款」
            rec['side_lib'] = len(re.findall(r'有库内条款依据', c))
            rec['side_model'] = len(re.findall(r'无库内条款', c))
            rec['side_other'] = max(0, (rec['rep_items'] or 0) - rec['side_lib'] - rec['side_model'])
            rec['non_us'] = [n for n, p in NON_US if re.search(p, c, re.I)]
            rec['sources'] = [n for n, p in SOURCES if re.search(p, c, re.I)]
            rec['rep_len'] = len(c)
        for k, pat in (('sum_total', r'卡内总数\s*\**(\d+)\s*处'), ('sum_lib', r'库侧\s*\**(\d+)\s*条'),
                       ('sum_model', r'模型侧\s*\**(\d+)\s*条')):
            mm = re.search(pat, zh)
            rec[k] = int(mm.group(1)) if mm else None
        detail.append(rec)
        if i % 10 == 0:
            print(f'  …{i}/80', flush=True)

    json.dump(detail, open(os.path.join(OUT, 'qa5_20261015.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)

    # ── 摘要 ──────────────────────────────────────────────────────────────
    P = print
    P('\n== Q2 五格 vs 报告 ==')
    no_tok = [d['cid'] for d in detail if not d['tok']]
    ok_c = [d for d in detail if d['tok'] and d['rep_state'] == d['concl']]
    bad_c = [(d['cid'], d['concl'], d['rep_state']) for d in detail if d['tok'] and d['rep_state'] != d['concl']]
    ok_n = [d for d in detail if d['tok'] and d['rep_declared'] == d['cnt']]
    bad_n = [(d['cid'], d['cnt'], d['rep_declared']) for d in detail if d['tok'] and d['rep_declared'] != d['cnt']]
    P(f'  无链接: {len(no_tok)} {no_tok}')
    P(f'  结论: 报告【X】== Agent 结论 {len(ok_c)}/79 ｜ 不一致 {len(bad_c)} {bad_c[:6]}')
    P(f'  问题数量: 报告「共发现 N 处」== 问题数量 {len(ok_n)}/79 ｜ 不一致 {len(bad_n)} {bad_n[:6]}')
    # ★ 2026-10-15：口径改了 —— `状态` 是**流程档位**（PRD §8.2：待审/已修改/已发布），
    #   三态归 `Agent 结论`。原来这里拿两者相等与否当判据，现在**按 PRD 判值域**。
    #   （旧口径下 80 行「状态==结论」看着全绿，恰恰是缺陷本身。）
    st_bad = [(d['cid'], d['state']) for d in detail if d['state'] not in ('待审', '已修改', '已发布')]
    P(f'  状态 ∈ PRD 三档（待审/已修改/已发布）: 越界的行 {len(st_bad)} {st_bad[:6]}')
    m4 = [(d['cid'], d['rep_declared'], d['rep_items']) for d in detail if d['tok'] and d['rep_declared'] != d['rep_items']]
    P(f'  M4 报告内部自洽（共发现 N == 逐条编号数）: 不自洽 {len(m4)}')
    m5 = [(d['cid'], d['sum_total'], d['cnt']) for d in detail if d['tok'] and d['sum_total'] not in (None, d['cnt'])]
    P(f'  M5 汇总「卡内总数」== 问题数量: 不一致 {len(m5)} {m5[:6]}')
    m6 = [(d['cid']) for d in detail if d['tok'] and d['sum_tok'] and d['sum_tok'] != d['tok']]
    P(f'  M6 汇总里的链接 == 链接列: 不一致 {len(m6)} {m6[:6]}')
    m9 = [(d['cid'], d['sum_items'], d['cnt']) for d in detail
          if d['tok'] and d['cnt'] and d['sum_items'] != d['cnt']]
    P(f'  M9 汇总逐条依据条数 == 问题数量: 不一致 {len(m9)} {m9[:6]}')
    c0 = [d for d in detail if d['conf'] == 0]
    c0n = [d for d in c0 if not d['conf0_note']]
    P(f'  置信度=0 的行 {len(c0)} ｜ 其中汇总没写 0 的口径说明 {len(c0n)} {[d["cid"] for d in c0n]}')
    P(f'  置信度 在 (0,1] 之外且 ≠0: {[ (d["cid"], d["conf"]) for d in detail if d["conf"] not in (0,) and not (d["conf"] and 0 < d["conf"] <= 1)]}')

    P('\n== Q3 报告条目构成（库侧/模型侧）==')
    both = [d for d in detail if d['tok'] and d['side_lib'] and d['side_model']]
    lib_only = [d['cid'] for d in detail if d['tok'] and d['side_lib'] and not d['side_model']]
    model_only = [d['cid'] for d in detail if d['tok'] and d['side_model'] and not d['side_lib']]
    P(f'  两测都有条目的报告: {len(both)} ｜ 只有库侧: {len(lib_only)} ｜ 只有模型侧: {len(model_only)}')
    P(f'  库侧条目合计 {sum(d["side_lib"] or 0 for d in detail)} ｜ 模型侧条目合计 {sum(d["side_model"] or 0 for d in detail)}')
    P(f'  其它标注（既非「有库内条款依据」也非「无库内条款」）合计 {sum(d["side_other"] or 0 for d in detail)}')
    eq = [d['cid'] for d in detail if d['tok'] and d['sum_total'] is not None and d['sum_lib'] is not None and d['sum_model'] is not None
          and d['sum_total'] == (d['sum_lib'] + d['sum_model'])]
    P(f'  汇总「卡内总数 == 库侧 + 模型侧」（即**没有去重**）的行: {len(eq)}/79')
    tsum = sum(1 for d in detail if d['tok'] and d['rep_declared'] == (d['side_lib'] or 0) + (d['side_model'] or 0))
    P(f'  报告「共发现 N 处 == 库侧 + 模型侧」的行: {tsum}/79')

    P('\n== Q4 非美国口径 ==')
    hits = [(d['cid'], d['non_us']) for d in detail if d['non_us']]
    P(f'  命中非美国强信号的行: {len(hits)}')
    for h in hits[:10]:
        P('   ', h)
    sc = collections.Counter(s for d in detail for s in d['sources'])
    P('  依据来源分布:', dict(sc))
    none_src = [d['cid'] for d in detail if d['tok'] and not d['sources']]
    P(f'  报告里没扫到任何来源名的行: {len(none_src)}')

    P('\n== Q5 三态分布 ==')
    P(' ', dict(collections.Counter(d['concl'] for d in detail)))
    for st in ('PASS',):
        P(f'  {st} 的行:', [(d['no'], d['cid'], d['cnt'], d['conf'], d['tok']) for d in detail if d['concl'] == st])


if __name__ == '__main__':
    main()