#!/usr/bin/env python3
"""置信度那一格的收口（Owner 2026-10-15「同意你的推荐」）：

  ① **有据的 2 行回填**（合并数在**当天运行日志**里逐字可查，不是猜的）；
  ② **无据的 5 行只补口径说明** —— 那 5 行的两侧合并数**没有落进任何留痕**
     （留底 md / 外发台账 / 结果表都没有那一行）⇒ **不编数**，只把这个 0 的含义写清楚；
  ③ **1 行不自洽写进口径说明**（`5pojASq2jdA-WEN`：结论 BLOCK，但合并置信度 0.85 落在
     PRD §6.6 的 0.70–0.89 档）—— Owner 裁：**结论以 BLOCK 为准**（库侧 BLOCK 不许降级），
     不自洽如实写出来，不为了 §6.6 把红线降成 REVIEW。

为什么口径说明一定要写进**格子里**：PRD §8.2 把 `置信度` 列为必录；而本库口径里 `0` 有专门语义
（= 引擎未做判定），与「读数缺失」「引擎给了数但没标定」**完全不是一件事**。
只填一个数不说它是什么意思 ⇒ 读表的人必然读错（这一格踩过一次：40 行 0 被当成"零风险"）。
数据源（逐字）：
  · `MC-US-YT-RLF9-789hh8-WEN`：`置信度(两侧合并)=0.85 [confirm]（库侧 — / 模型侧 confirm）`
  · `MC-US-YT-_xyLF4_AgAw`   ：`置信度(两侧合并)=0.93 [direct]（库侧 — / 模型侧 direct）`
  （两行都出自 `/tmp/wenan_social10_20261015.log`；与 `mergedConfidence()`「一侧没给就用另一侧」一致。）

用法：
  python3 backfill_confidence_notes.py            # 干跑
  python3 backfill_confidence_notes.py --apply
"""
import argparse, json, os, re, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
BACKUP = os.path.join(HERE, 'backup_pass_rerun_20261015-105156')
LARK = os.path.expanduser('~/.dsh/bin/lark-cli')
BASE, TABLE, RESULT_TABLE = 'RY2UbCRjXaeeWwscUPScVN5AnQc', 'tblavfbMDMeRsulo', 'tblCXPQVzfFWWCon'

#: 有据可查的合并数（来源见文件头）。**不在表里的行一律不回填。**
MERGED_ON_RECORD = {
    'MC-US-YT-RLF9-789hh8-WEN': (0.85, 'confirm', '两侧合并 · 库侧没给置信度 ⇒ 用模型侧（confirm）'),
    'MC-US-YT-_xyLF4_AgAw': (0.93, 'direct', '两侧合并 · 库侧没给置信度 ⇒ 用模型侧（direct）'),
}
UNCAL = ('★ 本数**未标定**（2026-10-15 双轨回归标定：同序不成立、≥0.90 档 8/8 判错）'
         '⇒ **不得用作分流依据**，只作标签留痕')
NOTE_MISSING = ('⚠️ 口径：这一格是 **0 = 读数缺失** —— 本单的**两侧合并数当时没有落进任何留痕**'
                '（留底/外发台账/结果表都查不到）⇒ 这个 0 **不是置信度**，也**不是**「引擎已判定为低把握」，'
                '更不是「零风险」；**不得用作分流依据**。'
                '要换成真数只能重跑这一行，而素材没有换版本（PRD §8.1/§10.1）⇒ 本库不重跑。')
NOTE_INCONSISTENT = ('⚠️ 口径：本单**结论 = BLOCK**，而两侧合并置信度 0.85 落在 PRD §6.6 的 '
                     '**0.70–0.89（该档写的是 REVIEW）** ⇒ 两者不自洽。'
                     '按 Owner 裁定：**结论以 BLOCK 为准**（库侧判 BLOCK，按单调性不许降级、红线优先），'
                     '不为对齐 §6.6 把红线降成 REVIEW；这个数**不作分流依据**，只作标签留痕。')

NOTE_HEAD = '⚠️ 口径：'
#: ④ 零值且无口径 ⇒ 补说明（**不改数**）。措辞只管「这个 0 是什么意思」，不替引擎编它没给的东西。
NOTE_ZERO = ('⚠️ 口径：本格 **0 ＝ 本单没有可用的置信度** —— 库侧未给该读数，两侧合并也没算出可用的数'
             '（该单运行留痕里写的是 `置信度(两侧合并)=—`）⇒ 这个 0 **不是**「引擎判定为低把握」、'
             '**更不是**「零风险」；**不得用作分流依据**。')


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


def with_note(cell, note):
    """把口径说明挂到格尾（已经在的不重复挂；动作行仍是最后一句'结论'，说明另起一段）。"""
    c = str(cell or '').rstrip()
    if note.split('——')[0][:24] in c:
        return c
    return c + '\n\n' + note


def plan(rows):
    """返回 {记录ID: 要写的字段} + 逐行理由。判据只有这一份（干跑与 selftest 共用）。"""
    out, why = {}, []
    for r in rows:
        # ★ 2026-10-16：**不再限定「文案」** —— 图片/视频行同样有 0 值的置信度，
        #   原先只在文案行上跑 ⇒ 29 个零值里只补到 10 行（漏 19 行）。
        cid = plain(r.get('内容 ID'))
        cell = plain(r.get('问题分类汇总'))
        if not cell.strip():
            continue
        conf = plain(r.get('置信度')).strip()
        act = plain(r.get('Agent 结论')).strip().upper()
        want, w = {}, []
        if cid in MERGED_ON_RECORD:
            val, band, basis = MERGED_ON_RECORD[cid]
            if conf != str(val):
                want['置信度'] = val
                w.append(f'回填置信度 {conf}→{val}（{band}，有据）')
            # 说明句式：**档位在前、出处一次说清**（别把 basis 原句抄两遍 —— 一读就像机器口吃）
            n = f'{NOTE_HEAD}置信度（两侧合并 · 档位 {band} · {basis.split("·")[-1].strip()}）：{UNCAL}'
            if '未标定' not in cell:
                want['问题分类汇总'] = with_note(cell, n)
                w.append('补「未标定」声明')
        elif conf in ('', '0'):
            note = NOTE_MISSING if '读数缺失' in cell else NOTE_ZERO
            if NOTE_HEAD not in cell:
                want['问题分类汇总'] = with_note(cell, note)
                w.append('补「0 的含义」口径（不改数）')
        if act == 'BLOCK' and conf == '0.85' and '不自洽' not in cell:
            want['问题分类汇总'] = with_note(want.get('问题分类汇总', cell), NOTE_INCONSISTENT)
            w.append('补「BLOCK 与 0.85 不自洽」口径')
        if want:
            out[r['record_id']] = want
            why.append((cid, act, conf, '／'.join(w)))
    return out, why


def selftest():
    """反向对照：合规格的行不许被改；三类该改的各造一行，必须**精确**命中。"""
    clean = {'内容 ID': 'X', '内容类型': '文案', '置信度': 0.85, 'Agent 结论': 'REVIEW',
             '问题分类汇总': '【审查结论：REVIEW】…\n\n建议转 @法务 @医学顾问 复核。'}
    good = [{'record_id': 'A', **clean,
             '问题分类汇总': clean['问题分类汇总'] + '\n\n⚠️ 口径：… ★ 本数**未标定**'}]
    cases = [
        ('合规格（非零、已带声明）不许改', good, {}),
        ('有据那行 conf=0 ⇒ 回填成 0.85 + 补声明', [{'record_id': 'B', **clean,
            '内容 ID': 'MC-US-YT-RLF9-789hh8-WEN', '置信度': 0}], {'B': ['置信度', '问题分类汇总']}),
        ('无据的 0 ⇒ 只补「读数缺失」，**不许**改数', [{'record_id': 'C', **clean,
            '内容 ID': 'MC-US-WEB-COL-x', '置信度': 0}], {'C': ['问题分类汇总']}),
        ('BLOCK+0.85 ⇒ 补「不自洽」', [{'record_id': 'D', **clean,
            '内容 ID': 'MC-US-YT-5pojASq2jdA-WEN', 'Agent 结论': 'BLOCK', '置信度': 0.85}],
         {'D': ['问题分类汇总']}),
        ('零值且无口径 ⇒ 只补说明、**不改数**', [{'record_id': 'E', **clean,
            '内容 ID': 'MC-US-WEB-IMG-x', '置信度': 0}], {'E': ['问题分类汇总']}),
    ]
    bad = 0
    for name, rows, want in cases:
        got, _ = plan(rows)
        keys = {k: sorted(v) for k, v in got.items()}
        ok = (keys == want)
        bad += 0 if ok else 1
        print(f"  {'✅' if ok else '✗'} {name} ⇒ {keys or '不改'}")
    print('selftest ' + ('全绿' if bad == 0 else f'{bad} 项红'))
    return 0 if bad == 0 else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true')
    ap.add_argument('--selftest', action='store_true')
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    rows = read_table(TABLE, '/tmp/tbl_conf.ndjson')
    patch, why = plan(rows)
    print(f"命中待改 {len(patch)} 格")
    for cid, act, conf, w in why:
        print(f"  {cid:34s} {act:6s} conf={conf or '—':5s} {w}")
    if not a.apply:
        print('（未加 --apply：什么都没写）')
        return 0
    if patch:
        os.makedirs(BACKUP, exist_ok=True)
        before = {rid: {k: plain(x.get('问题分类汇总') if k == '问题分类汇总' else x.get('置信度'))
                        for k in v} for rid, v in patch.items()
                  for x in rows if x.get('record_id') == rid}
        json.dump(before, open(os.path.join(BACKUP, 'conf_before_backfill_20261015.json'),
                               'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        w = subprocess.run([LARK, 'base', '+record-batch-update', '--base-token', BASE, '--table-id', TABLE,
                            '--json', json.dumps({'update_records': patch}, ensure_ascii=False),
                            '--profile', 'dsh-kb', '--as', 'bot'], capture_output=True, text=True, cwd='/tmp')
        print(f"写入采集表 {len(patch)} 格 ｜ rc={w.returncode} {str(w.stdout or '')[:90]} {str(w.stderr or '')[:150]}")
        if w.returncode != 0:
            return 3
        # 结果表同源：同素材那一行的 置信度 也要跟着改（卡/表/记录三处一个数）
        res = read_table(RESULT_TABLE, '/tmp/res_conf.ndjson')
        rpatch = {}
        for r in res:
            mat = re.sub(r'\s+', ' ', plain(r.get('送审问题'))).strip()[:120]
            for row in rows:
                if row.get('record_id') not in patch:
                    continue
                if '置信度' not in patch[row['record_id']]:
                    continue
                if re.sub(r'\s+', ' ', plain(row.get('采集数据'))).strip()[:120] != mat:
                    continue
                cid = plain(row.get('内容 ID'))
                if cid in MERGED_ON_RECORD:
                    rpatch[r['record_id']] = {'置信度': MERGED_ON_RECORD[cid][0]}
        if rpatch:
            w2 = subprocess.run([LARK, 'base', '+record-batch-update', '--base-token', BASE,
                                 '--table-id', RESULT_TABLE,
                                 '--json', json.dumps({'update_records': rpatch}, ensure_ascii=False),
                                 '--profile', 'dsh-kb', '--as', 'bot'], capture_output=True, text=True, cwd='/tmp')
            print(f"写入结果表 {len(rpatch)} 行 ｜ rc={w2.returncode}")
    rows2 = read_table(TABLE, '/tmp/tbl_conf_after.ndjson')
    ok = bad = 0
    for r in rows2:
        rid = r.get('record_id')
        if rid not in patch:
            continue
        for k, v in patch[rid].items():
            cur = plain(r.get(k))
            if (str(v).strip() in cur) if k == '问题分类汇总' else (abs(float(cur or 0) - float(v)) < 1e-9):
                ok += 1
            else:
                bad += 1
                print(f'  ✗ 回读不一致 {rid} {k}')
    print(f"回读复核：一致 {ok} ｜ 不一致 {bad}")
    return 0 if bad == 0 else 4


if __name__ == '__main__':
    sys.exit(main())
