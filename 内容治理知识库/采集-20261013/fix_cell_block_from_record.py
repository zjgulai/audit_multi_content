#!/usr/bin/env python3
"""把**不合规的那几格**按 PRD §5.3 + Owner 的 5 行格式，从**这一行自己的记录**重渲染 —— **不重跑**。

为什么会有这个脚本（Owner 2026-10-15：「为什么重跑35个文案？你要先查prd，清楚了以后再执行」）：
  单元格是**记录字段的渲染**（PRD §10.1 的 `issue_summary_by_category` / `report_url`），
  格式不对 ⇒ 重渲染即可；重跑是**另一件事**（PRD §8.1「已修改，重新提交」+ §10.1「重新提交生成新版本、
  新 review_id」），只该在素材换了版本时发生。

修哪三类格（都是**规则命中**，不是"看着不对"）：
  A. `问题数量 >= 3` 却**没有**「→ 查看完整问题清单与修改建议」那一行 ⇒ 违反 §5.3.3/§5.3.4/§5.3.5；
  B. 格里有内部行话「（本次没有并进任何逐条）」 ⇒ 那是过程读数，不是 PRD 结论块；
  C. 格里有「【逐条依据（落库留痕）】」整块 ⇒ 依据属**报告**（Owner：「我看报告就好，你为什么另开一列？」）。

渲染源 = 结论表里**与这行素材原文同源**的那一行（倒序取最新）+ 台账的 `report_url` 兜底。
动作行按状态取 PRD 原文：BLOCK = 「请修改后重新提交。」／REVIEW = 「建议转 @法务 @医学顾问 复核。」

用法：
  python3 fix_cell_block_from_record.py            # 干跑
  python3 fix_cell_block_from_record.py --apply
"""
import argparse, json, os, re, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
BACKUP = os.path.join(HERE, 'backup_pass_rerun_20261015-105156')
LARK = os.path.expanduser('~/.dsh/bin/lark-cli')
BASE, TABLE, RESULT_TABLE = 'RY2UbCRjXaeeWwscUPScVN5AnQc', 'tblavfbMDMeRsulo', 'tblCXPQVzfFWWCon'
LEDGER = '/Users/lute/Project/audit_multi_content/PMO/shouheng-state/batch-review.json'
ACT = {'BLOCK': '请修改后重新提交。', 'REVIEW': '建议转 @法务 @医学顾问 复核。'}
JARGON = '（本次没有并进任何逐条）'


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
    return re.sub(r'\s+', ' ', str(s or '')).strip().lower()


def read_table(table, out):
    subprocess.run([LARK, 'base', '+record-list', '--base-token', BASE, '--table-id', table,
                    '--limit', '2000', '--format', 'ndjson', '--output', out, '--overwrite',
                    '--profile', 'dsh-kb', '--as', 'bot'], capture_output=True, text=True, cwd='/tmp')
    return [json.loads(l) for l in open(out, encoding='utf-8') if l.strip()]


def build(rec_block, state, ledger_url):
    """把记录块渲染成 PRD §5.3 的格内容（结论行 / 逐条问题 / 分类 / 报告链接 / 动作）。"""
    blk = str(rec_block or '')
    blk = blk.split('【逐条依据')[0]                 # C：依据块不进格
    lines = [l.rstrip() for l in blk.splitlines()]
    head = next((l.strip() for l in lines if l.strip()), '')
    bullets = [l.strip() for l in lines if l.strip().startswith('·') and JARGON not in l]   # B
    link = next((l.strip() for l in lines if '查看完整问题清单' in l), '')
    if not link and ledger_url:
        link = f'→ 查看完整问题清单与修改建议：{ledger_url}'                                  # A：链接必须补上
    out = [head, '', '逐条问题', *bullets]
    if link:
        out += ['', link]
    tail = ACT.get(state)
    if tail:
        out += ['', tail]
    return '\n'.join(out).strip() + '\n'


ACTION_NOTE = re.compile(r'（其中 \d+/\d+ 条未匹配到方向：该转谁需要人确认）')


def flags_of(cell, n):
    """四条规则本体（干跑与自证共用同一份判据，别在两处各写一遍）。"""
    why = []
    if n and str(n).strip() not in ('', '0') and float(n) >= 3 and '查看完整问题清单' not in cell:
        why.append('A 缺报告链接行')
    if JARGON in cell:
        why.append('B 过程行话')
    if '【逐条依据' in cell:
        why.append('C 依据块进格')
    # ★ D（2026-10-15，Owner：「就按照卡的格式，这是跟 prd 对齐」）——
    #   动作行尾巴上那句「（其中 N/M 条未匹配到方向：该转谁需要人确认）」**卡上没有**，
    #   是表这一路自己多渲染的一句 ⇒ 表向卡看齐（同源纪律）。实测 7/10 行不一致，全是这一句。
    if ACTION_NOTE.search(cell):
        why.append('D 动作行多一句（卡上没有）')
    return why


def strip_action_note(cell):
    """去掉动作行尾巴那句括注（只删这一句，别的一个字不动）。"""
    return ACTION_NOTE.sub('', str(cell))


def selftest():
    """反向对照：合规格不许命中；四类缺陷各注入一次，必须**精确**命中对应规则。"""
    good = ('【审查结论：BLOCK】共发现 4 处必须修改。\n\n逐条问题\n· 合规类问题：2 个\n\n'
            '→ 查看完整问题清单与修改建议：https://x/docx/AAA\n\n请修改后重新提交。')
    rev = ('【审查结论：REVIEW】共发现 4 处需人工确认。\n\n逐条问题\n· 合规类问题：2 个\n\n'
           '→ 查看完整问题清单与修改建议：https://x/docx/AAA\n\n建议转 @法务 @医学顾问 复核。')
    cases = [
        ('合规格（n=4，有链接）', good, 4, []),
        ('合规格（REVIEW 卡那版）', rev, 4, []),
        ('A：n=4 但没链接行', good.replace('\n\n→ 查看完整问题清单与修改建议：https://x/docx/AAA', ''), 4, ['A 缺报告链接行']),
        ('A 反向：n=2 没链接行（1–2 条本就逐条输出，不算缺陷）', good.replace('共发现 4 处', '共发现 2 处'), 2, []),
        ('B：带内部行话', good + '\n·（本次没有并进任何逐条）', 4, ['B 过程行话']),
        ('C：依据块进格', good + '\n\n【逐条依据（落库留痕）】\n1.【合规】…', 4, ['C 依据块进格']),
        ('D：动作行多一句括注',
         rev.replace('复核。', '复核。（其中 2/5 条未匹配到方向：该转谁需要人确认）'), 4, ['D 动作行多一句（卡上没有）']),
        ('D 反向：括注在**别的**位置（不是那一句）', rev.replace('复核。', '复核。（补充说明）'), 4, []),
    ]
    bad = 0
    for name, cell, n, want in cases:
        got = flags_of(cell, n)
        ok = (got == want)
        bad += 0 if ok else 1
        print(f"  {'✅' if ok else '✗'} {name} ⇒ {got or '不命中'}")
    # 渲染器：记录块（含依据块 + 行话）⇒ 必须只剩 PRD 那 5 行
    rec = ('【审查结论：REVIEW】共发现 4 处需人工确认。\n\n· 合规类问题：2 个\n· 隐私类问题：1 个\n'
           '·（本次没有并进任何逐条）\n\n→ 查看完整问题清单与修改建议：https://x/docx/BBB\n\n'
           '建议转 @法务（未配置） 复核。\n\n【逐条依据（落库留痕）】\n1.【合规】…')
    out = build(rec, 'REVIEW', '')
    lines = [l for l in out.splitlines() if l.strip()]
    ok = (lines[0].startswith('【审查结论：REVIEW】') and lines[1] == '逐条问题'
          and lines[2] == '· 合规类问题：2 个' and JARGON not in out and '【逐条依据' not in out
          and lines[-2].startswith('→ 查看完整问题清单') and lines[-1] == '建议转 @法务 @医学顾问 复核。')
    print(f"  {'✅' if ok else '✗'} 渲染器：依据块/行话/「（未配置）」都清掉、5 行齐 ⇒ {len(lines)} 行")
    bad += 0 if ok else 1
    print('selftest ' + ('全绿' if bad == 0 else f'{bad} 项红'))
    return 0 if bad == 0 else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true')
    ap.add_argument('--selftest', action='store_true')
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    led = json.load(open(LEDGER, encoding='utf-8'))['items']
    rows = read_table(TABLE, '/tmp/tbl80_for_cellfix.ndjson')
    res = read_table(RESULT_TABLE, '/tmp/res_for_cellfix.ndjson')
    res.sort(key=lambda r: str(r.get('写入时间') or ''), reverse=True)
    idx = {}
    for r in res:
        k = norm(r.get('送审问题'))[:120]
        if k and k not in idx:
            idx[k] = r
    patch, report, before = {}, [], {}
    for r in rows:
        # ★ 2026-10-15：**不再限定「文案」** —— 规则 D（动作行尾巴那句括注）在图片/视频行上一样成立，
        #   原先只在文案行上跑，导致图片 22 行「卡≠表」一直没被清掉。
        cell = plain(r.get('问题分类汇总'))
        if not cell.strip():
            continue                                   # 空格子 = 还没审，交给跑批（不在这件的范围）
        n = plain(r.get('问题数量'))
        state = plain(r.get('Agent 结论')).strip()
        why = flags_of(cell, n)          # ★ 判据只有一份：干跑与 --selftest 共用
        if not why:
            continue
        cid = plain(r.get('内容 ID'))
        # ★ D 单独一支：**只删那一句**，其余一个字不动（不重渲染 —— 卡上其余部分本就是这个格式）
        if why == ['D 动作行多一句（卡上没有）']:
            new = strip_action_note(cell)
            if new.strip() == cell.strip():
                continue
            patch[r['record_id']] = {'问题分类汇总': new}
            before[r['record_id']] = cell
            report.append((cid, state, n, why[0], len(cell), len(new)))
            continue
        h = idx.get(norm(plain(r.get('采集数据')))[:120])
        block = plain((h or {}).get('问题分类汇总'))
        if not block.strip():
            print(f'  ⚠️ {cid} 结论表里找不到同源行 ⇒ 跳过（不编）')
            continue
        if state in ('PASS',) or not n or (n and float(n) == 0):
            new = block.split('【逐条依据')[0].strip().splitlines()[0] + '\n'
        else:
            new = build(block, state, str((led.get(cid) or {}).get('report_url') or ''))
        if new.strip() == cell.strip():
            continue
        patch[r['record_id']] = {'问题分类汇总': new}
        before[r['record_id']] = cell
        report.append((cid, state, n, '／'.join(why), len(cell), len(new)))
    print(f"命中待修 {len(patch)} 格")
    for cid, st, n, why, l0, l1 in report:
        print(f"  {cid:34s} {st:6s} n={n:>3s} {why:18s} {l0} → {l1} 字")
    if report:
        print('—— 预览（第一格）——')
        k = list(patch)[0]
        print(patch[k]['问题分类汇总'])
    if not a.apply:
        print('（未加 --apply：什么都没写）')
        return 0
    if patch:
        os.makedirs(BACKUP, exist_ok=True)
        json.dump(before, open(os.path.join(BACKUP, 'cells_before_format_fix_20261015.json'),
                               'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        w = subprocess.run([LARK, 'base', '+record-batch-update', '--base-token', BASE, '--table-id', TABLE,
                            '--json', json.dumps({'update_records': patch}, ensure_ascii=False),
                            '--profile', 'dsh-kb', '--as', 'bot'], capture_output=True, text=True, cwd='/tmp')
        print(f"写入 {len(patch)} 格 ｜ rc={w.returncode} {str(w.stdout or '')[:100]} {str(w.stderr or '')[:150]}")
        if w.returncode != 0:
            return 3
    rows2 = read_table(TABLE, '/tmp/tbl80_after_cellfix.ndjson')
    want = {rid: v['问题分类汇总'] for rid, v in patch.items()}
    ok = bad = 0
    for r in rows2:
        rid = r.get('record_id')
        if rid not in want:
            continue
        if plain(r.get('问题分类汇总')).strip() == want[rid].strip():
            ok += 1
        else:
            bad += 1
            print(f'  ✗ 回读不一致 {rid}')
    print(f"回读复核：一致 {ok} ｜ 不一致 {bad}")
    return 0 if bad == 0 else 4


if __name__ == '__main__':
    sys.exit(main())
