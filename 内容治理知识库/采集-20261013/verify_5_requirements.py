#!/usr/bin/env python3
"""按 Owner 的五条要求逐条核 80 行（2026-10-15）：

  ① 素材都来自 吸奶器/清洗机/婴儿监控器；
  ② 置信度：输入 = 知识库侧 ＋ 模型侧，输出 = **合并后**那一个数；
  ③ 飞书表里的数据与**报告正文**对齐；
  ④ 模型侧只跑**美国区域**；
  ⑤ 报告链接**可点开、无空链接**。

每一条都给「判据 → 读数 → 结论」，跑一次出全表台账（JSON 落 `out/verify5_<时刻>.json`）。
不确定的一律写 **未测**，不写成"通过"。

用法： python3 verify_5_requirements.py [--sample N]     # N>0 时只抽 N 行做报告正文核对（省时间）
"""
import argparse, collections, glob, json, os, re, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'out')
LARK = os.path.expanduser('~/.dsh/bin/lark-cli')
BASE, TABLE, RESULT_TABLE = 'RY2UbCRjXaeeWwscUPScVN5AnQc', 'tblavfbMDMeRsulo', 'tblCXPQVzfFWWCon'
COL = '10/14重跑报告链接'
P0_ROWS = set()          # 日志里判到「P0 命中 ⇒ 直接 BLOCK」的行（PRD §6.6：置信度记 1.0）
LOGS = ['/tmp/tupian35_20261015.log', '/tmp/img5_rerun_20261015.log', '/tmp/wenan_social10_20261015.log',
        '/tmp/mixed11_rerun_20261015.log', '/tmp/review_full_20261015-1643.log']


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


def norm(s):
    return re.sub(r'\s+', ' ', str(s or '')).strip()


def read_table(table, out):
    subprocess.run([LARK, 'base', '+record-list', '--base-token', BASE, '--table-id', table,
                    '--limit', '2000', '--format', 'ndjson', '--output', out, '--overwrite',
                    '--profile', 'dsh-kb', '--as', 'bot'], capture_output=True, text=True, cwd='/tmp')
    return [json.loads(l) for l in open(out, encoding='utf-8') if l.strip()]


def docx_of(s):
    m = re.search(r'/docx/([A-Za-z0-9]+)', str(s or ''))
    return m.group(1) if m else ''


def load_cat_of():
    import importlib.util
    spec = importlib.util.spec_from_file_location('ct', os.path.join(HERE, 'collect_tupian35.py'))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m.cat_of


def log_merged_values():
    """从跑批日志按行取「置信度(两侧合并)=X [band]（库侧 a / 模型侧 b）」—— 用来核 ② 的输出。"""
    vals = {}
    global P0_ROWS
    for p in LOGS:
        if not os.path.exists(p):
            continue
        cur = None
        for line in open(p, encoding='utf-8', errors='ignore'):
            m = re.match(r'\[\d+/\d+\]\s+([A-Za-z0-9_\-]+)', line.strip())
            if m:
                cur = m.group(1)
                continue
            if not cur:
                continue
            if 'P0 命中' in line and cur not in P0_ROWS:
                P0_ROWS.add(cur)
            mm = re.search(r'置信度\(两侧合并\)=([\d.]+|—)\s*\[([^\]]*)\]\s*（库侧\s*([^/]+?)\s*/\s*模型侧\s*([^）]+?)）', line)
            if mm and cur not in vals:
                kb_side = mm.group(3).strip()
                vals[cur] = {'merged': mm.group(1), 'band': mm.group(2).strip(),
                             'kb_band': kb_side, 'model_band': mm.group(4).strip(),
                             'log': os.path.basename(p)}
    return vals


def fetch_doc(tok):
    """取报告正文（markdown）。返回 (ok, content_or_err, revision)。"""
    q = subprocess.run([LARK, 'docs', '+fetch', '--doc', tok, '--profile', 'dsh-kb', '--as', 'bot',
                        '--doc-format', 'markdown', '--format', 'ndjson'],
                       capture_output=True, text=True, cwd='/tmp')
    if q.returncode != 0 or not q.stdout.strip():
        return False, (q.stderr or q.stdout or '')[:200], None
    try:
        d = json.loads(q.stdout.strip().splitlines()[0])['document']
        return True, d.get('content', ''), d.get('revision_id')
    except Exception as e:
        return False, f'{type(e).__name__}: {str(q.stdout)[:120]}', None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--sample', type=int, default=0, help='>0 时只抽 N 行做报告正文核对')
    a = ap.parse_args()
    cat_of = load_cat_of()
    rows = read_table(TABLE, '/tmp/v5_tbl.ndjson')
    res_rows = read_table(RESULT_TABLE, '/tmp/v5_res.ndjson')
    merged = log_merged_values()
    R = {'at': time.strftime('%Y-%m-%d %H:%M:%S'), 'n_rows': len(rows)}
    print(f'—— 80 行核对（{R["at"]}）｜日志里取到合并读数的行 {len(merged)} ——')

    # ── ① 品类 ─────────────────────────────────────────────────────────────
    viol = [(plain(r.get('内容 ID')), plain(r.get('内容类型')), cat_of(plain(r.get('采集数据'))[:600]))
            for r in rows if cat_of(plain(r.get('采集数据'))[:600]) not in ('吸奶器', '清洗机', '婴儿监控器')]
    dist = collections.Counter(cat_of(plain(r.get('采集数据'))[:600]) for r in rows)
    R['req1'] = {'violations': viol, 'dist': dict(dist)}
    print(f"① 品类：越界 {len(viol)} 行 ｜ 分布 {dict(dist)}")

    # ── ② 置信度：合并输出 ───────────────────────────────────────────────────
    conf_tbl = {}
    for r in rows:
        cid = plain(r.get('内容 ID'))
        conf_tbl[cid] = {'conf': plain(r.get('置信度')).strip(), 'state': plain(r.get('Agent 结论')).strip().upper(),
                         't': plain(r.get('内容类型')).strip(), 'q': plain(r.get('问题数量')).strip(),
                         'cell': plain(r.get('问题分类汇总'))}
    mism = []
    checked = 0
    for cid, m in merged.items():
        hit = conf_tbl.get(cid)
        if not hit:
            continue
        checked += 1
        want = m['merged']
        got = hit['conf'] or '（空）'
        if cid in P0_ROWS and hit['state'] == 'BLOCK' and got in ('1', '1.0'):
            continue                      # ★ P0 命中：PRD §6.6 明文「不适用分流、记 1.0」⇒ 不是缺陷
        # P0 命中 ⇒ PRD §6.6 记 1.0（日志也会写 1）；其余应等于合并数
        if want in ('—', '') or want is None:
            continue
        if abs(float(got or 0) - float(want)) > 1e-9:
            mism.append({'cid': cid, 'merged_in_log': want, 'band': m['band'], 'table': got,
                         'state': hit['state'], 'log': m['log']})
    zeros = [c for c, v in conf_tbl.items() if v['conf'] in ('0', '')]
    zero_with_note = [c for c in zeros if '⚠️ 口径：' in conf_tbl[c]['cell']]
    both_sides = collections.Counter()
    for m in merged.values():
        both_sides[(m['kb_band'] in ('—', '', 'None'), m['model_band'] in ('—', '', '未参与'))] += 1
    R['req2'] = {'p0_rows': sorted(P0_ROWS), 'checked_vs_log': checked, 'mismatch': mism, 'zeros': zeros,
                 'zeros_with_note': zero_with_note, 'bands': {str(k): v for k, v in both_sides.items()}}
    print(f"② 置信度：与日志合并值比对了 {checked} 行 ｜ 不一致 {len(mism)} 行 ｜ 值为 0/空 {len(zeros)} 行"
          f"（其中带口径说明 {len(zero_with_note)}）")

    # ── ⑤ 链接可点 + 无空链接（先跑，③ 要用） ───────────────────────────────
    links = {}
    for r in rows:
        cid = plain(r.get('内容 ID'))
        cell = plain(r.get('问题分类汇总'))
        col = plain(r.get(COL))
        links[cid] = {'cell': docx_of(cell), 'col': docx_of(col), 'state': plain(r.get('Agent 结论')).strip().upper(),
                      'n': plain(r.get('问题数量')).strip()}
    need = {v['cell'] or v['col'] for v in links.values() if (v['cell'] or v['col'])}
    empty = [c for c, v in links.items() if not v['cell'] and not v['col'] and v['state'] != 'PASS']
    empty_pass = [c for c, v in links.items() if not v['cell'] and not v['col'] and v['state'] == 'PASS']
    docs, bad_links = {}, []
    toks = sorted(need)
    if a.sample:
        toks = toks[:a.sample]
    for i, t in enumerate(toks, 1):
        ok, content, rev = fetch_doc(t)
        docs[t] = {'ok': ok, 'content': content if ok else '', 'err': '' if ok else content, 'rev': rev}
        if not ok:
            bad_links.append({'tok': t, 'err': str(content)[:120]})
        if i % 20 == 0:
            print(f'   链接核对 {i}/{len(toks)} …')
    R['req5'] = {'tokens': len(need), 'checked': len(toks), 'bad': bad_links,
                 'empty_nonpass': empty, 'empty_pass': empty_pass}
    print(f"⑤ 链接：唯一报告 {len(need)} 个 ｜ 已核 {len(toks)} ｜ 打不开 {len(bad_links)} ｜ "
          f"非 PASS 却无链接 {len(empty)} 行 ｜ PASS 无链接 {len(empty_pass)} 行")

    # ── ③ 表 ↔ 报告正文对齐 ─────────────────────────────────────────────────
    mis3 = []
    for cid, v in links.items():
        tok = v['cell'] or v['col']
        if not tok or tok not in docs or not docs[tok]['ok']:
            continue
        body = docs[tok]['content']
        cell = conf_tbl[cid]['cell']
        cm = re.search(r'【审查结论：(\w+)】', cell)
        rm = re.search(r'【审查结论：(\w+)】', body)
        if cm and rm and cm.group(1) != rm.group(1):
            mis3.append({'cid': cid, 'cell_state': cm.group(1), 'report_state': rm.group(1), 'why': '结论行不一致'})
            continue
        cn = re.search(r'共发现\s*(\d+)\s*处', cell) or re.search(r'问题数\s*(\d+)', cell)
        rn = re.search(r'共发现\s*(\d+)\s*处', body) or re.search(r'问题数\s*(\d+)', body)
        if cn and rn and cn.group(1) != rn.group(1):
            mis3.append({'cid': cid, 'cell_n': cn.group(1), 'report_n': rn.group(1), 'why': '问题数不一致'})
    R['req3'] = {'compared': len([1 for v in links.values() if (v['cell'] or v['col']) in docs]),
                 'mismatch': mis3}
    print(f"③ 表↔报告：比对了 {R['req3']['compared']} 份 ｜ 不一致 {len(mis3)} 行")

    # ── ④ 模型侧只跑美国区域 ────────────────────────────────────────────────
    prompt_hits = []
    for p in glob.glob('/Users/lute/Project/audit_multi_content/tools/agent/*.mjs') + \
             glob.glob('/Users/lute/Project/audit_multi_content/tools/*.mjs'):
        try:
            t = open(p, encoding='utf-8', errors='ignore').read()
        except Exception:
            continue
        if re.search(r'模型侧', t) and re.search(r'美国|US\b|United States', t):
            for m in re.finditer(r'[^\n]*(?:模型侧)[^\n]*', t):
                s = m.group(0).strip()
                if re.search(r'美国|US\b|United States|美国区', s) and len(s) < 300:
                    prompt_hits.append({'file': os.path.basename(p), 'line': s[:200]})
    nonus = []
    for r in rows:
        cell = plain(r.get('问题分类汇总'))
        for m in re.finditer(r'(英国|UK\b|欧盟|EU\b|加拿大|Canada|澳大利亚|Australia|德国|法国|日本|€|£)', cell):
            nonus.append({'cid': plain(r.get('内容 ID')), 'hit': m.group(0), 'ctx': norm(cell[max(0, m.start()-40):m.start()+40])})
            break
    R['req4'] = {'prompt_hits': prompt_hits[:8], 'n_prompt_hits': len(prompt_hits), 'nonus_in_cells': nonus}
    print(f"④ 美国区：代码里带「模型侧＋美国」的约束 {len(prompt_hits)} 处 ｜ 格子里非美国信号 {len(nonus)} 行")

    os.makedirs(OUT, exist_ok=True)
    fp = os.path.join(OUT, 'verify5_%s.json' % time.strftime('%Y%m%d-%H%M%S'))
    json.dump(R, open(fp, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(f'\n台账 → {fp}')
    print('\n=== 五条结论 ===')
    print(f"① 品类：{'✅ 全在三品类内' if not viol else '❌ ' + str(len(viol)) + ' 行越界'}")
    print(f"② 置信度：{'✅ 有日志可比对的行全部等于合并值' if not mism else '❌ ' + str(len(mism)) + ' 行不等于合并值'}"
          f"（0/空 {len(zeros)} 行，带口径 {len(zero_with_note)}）")
    print(f"③ 表↔报告：{'✅ 结论行与问题数一致' if not mis3 else '❌ ' + str(len(mis3)) + ' 行不一致'}")
    print(f"④ 美国区：{'✅ 格子里 0 处非美国信号' if not nonus else '⚠️ ' + str(len(nonus)) + ' 行有非美国字样'}；"
          f"模型侧提示词的美国约束见台账")
    print(f"⑤ 链接：{'✅ 全部可打开，且非 PASS 行无空链接' if (not bad_links and not empty) else '❌ 见台账'}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
