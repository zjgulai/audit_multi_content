#!/usr/bin/env python3
"""整表字段对齐：把「已跑完」的行在采集表里补齐/校正成**这一轮**的读数（Owner 2026-10-15：
「新跑完的报告整个表格中的字段要同步更新，数据要对齐」）。

对齐来源 = **台账（守衡自己的批跑台账）＋ 结论表最新那一行**，与跑批器 `writeBack` 同一套认领口径：
  · 素材原文前缀（归一化后前 120 字）＝ 这一单真正的键（内容 ID 在两侧不是一个体系，不能用）
  · 取结论表里**最新**的一条匹配行（按 `写入时间` 倒序）

对齐的字段（结论派生列 + 链接列）：
  Agent 结论 / 状态 / 问题数量 / 置信度 / 问题分类汇总 / 10/14重跑报告链接
**不碰**：人的格子（人工复核人 / 复核结论 / sign-off 人 / 审核人 / 发布时间）、素材列、内容类型。

用法：
  python3 align_table_from_ledger.py --scope 文案 --dry-run
  python3 align_table_from_ledger.py --scope 文案 --apply
"""
import argparse, collections, json, os, re, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'out')
B = os.path.join(HERE, 'backup_pass_rerun_20261015-105156')
LARK = os.path.expanduser('~/.dsh/bin/lark-cli')
BASE, TABLE = 'RY2UbCRjXaeeWwscUPScVN5AnQc', 'tblavfbMDMeRsulo'
RESULT_TABLE = 'tblCXPQVzfFWWCon'
LEDGER = '/Users/lute/Project/audit_multi_content/PMO/shouheng-state/batch-review.json'
LINK_COL = '10/14重跑报告链接'
SYNC = ['Agent 结论', '状态', '问题数量', '置信度', '问题分类汇总']


def plain(v):
    if v is None:
        return ''
    if isinstance(v, str):
        return v
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, list):
        return ''.join(str(s.get('text') or s.get('link') or s.get('name') or '') if isinstance(s, dict) else str(s) for s in v)
    if isinstance(v, dict):
        return str(v.get('text') or v.get('link') or v.get('name') or '')
    return str(v)


def norm(s):
    return re.sub(r'\s+', ' ', str(s or '')).strip().lower()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--scope', default='文案')
    ap.add_argument('--apply', action='store_true')
    a = ap.parse_args()
    led = json.load(open(LEDGER, encoding='utf-8'))['items']
    # 采集表
    q = subprocess.run([LARK, 'base', '+record-list', '--base-token', BASE, '--table-id', TABLE,
                        '--view-id', 'vewhS7Rwx0', '--page-size', '200', '--profile', 'dsh-kb',
                        '--as', 'bot', '--format', 'json'], capture_output=True, text=True, cwd='/tmp')
    d = json.loads(q.stdout)['data']; F = d['fields']
    I = {k: F.index(k) for k in ('内容 ID', '内容类型', '采集数据', LINK_COL, *SYNC)}
    # 结论表（倒序取最新）
    rp = '/tmp/result_table_for_align.ndjson'          # ★ CLI 的 --output 只认 /tmp 或 cwd 之下
    subprocess.run([LARK, 'base', '+record-list', '--base-token', BASE, '--table-id', RESULT_TABLE,
                    '--limit', '2000', '--format', 'ndjson', '--output', rp, '--overwrite',
                    '--profile', 'dsh-kb', '--as', 'bot'], capture_output=True, text=True, cwd='/tmp')
    res = [json.loads(l) for l in open(rp, encoding='utf-8') if l.strip()]
    res.sort(key=lambda r: str(r.get('写入时间') or ''), reverse=True)
    print(f"结论表 {len(res)} 行 ｜ 采集表 {len(d['data'])} 行 ｜ 范围 {a.scope}")

    stat = collections.Counter()
    patch, report = {}, []
    for i, row in enumerate(d['data']):
        if plain(row[I['内容类型']]) != a.scope:
            continue
        rid = d['record_id_list'][i]
        cid = plain(row[I['内容 ID']])
        mat = plain(row[I['采集数据']])
        L = led.get(cid) or {}
        if not L.get('answered_at'):
            stat['待跑（未对齐，正常）'] += 1
            continue
        want = {}
        # ① 链接列 ← 台账 report_url
        ru = str(L.get('report_url') or '')
        t_new = (re.search(r'/docx/([A-Za-z0-9]+)', ru) or [None, None])[1]
        t_cur = (re.search(r'/docx/([A-Za-z0-9]+)', plain(row[I[LINK_COL]])) or [None, None])[1]
        if t_new and t_new != t_cur:
            want[LINK_COL] = f'[内容审查报告]({ru})'
        # ② 结论派生列 ← 结论表最新匹配行
        key = norm(mat)[:120]
        hit = next((r for r in res if norm(r.get('送审问题'))[:120] == key), None)
        if not hit:
            hit = next((r for r in res if key and key[:60] in norm(r.get('送审问题'))), None)
        if hit:
            # ★ 链接也可以从结论表那一行直接取（`报告链接` 是链自己写的，跑批器按 PRD 不再写采集表那一列）
            rlink = plain(hit.get('报告链接'))
            t_r = (re.search(r'/docx/([A-Za-z0-9]+)', rlink) or [None, None])[1]
            if t_r and t_r != t_cur:
                want[LINK_COL] = f'[内容审查报告]({rlink})'
            for k in SYNC:
                v = hit.get(k)
                v = plain(v).strip() if k != '问题数量' and k != '置信度' else v
                if k in ('问题数量', '置信度'):
                    if v is None or v == '':
                        continue
                    v = float(v)
                    v = int(v) if v == int(v) else v
                if not str(v).strip():
                    continue
                if plain(row[I[k]]).strip() != str(v).strip():
                    want[k] = v
        else:
            stat['⚠️ 结论表里找不到这一单（需重跑）'] += 1
        if want:
            patch[rid] = want
            stat['需要写入的行'] += 1
            report.append({'cid': cid, 'fields': list(want)})
        else:
            stat['已对齐'] += 1
    print("对齐结果:", dict(stat))
    for r in report[:10]:
        print(f"   {r['cid'][:46]:<48} 补/改 {r['fields']}")
    if not a.apply:
        print("\n（--dry-run：什么都没写）")
        return 0
    if patch:
        shapshot = {rid: {k: plain(d['data'][[d['record_id_list'].index(rid)][0]][I[k]]) for k in v} for rid, v in patch.items()}
        json.dump(shapshot, open(os.path.join(B, 'align_before_values.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        w = subprocess.run([LARK, 'base', '+record-batch-update', '--base-token', BASE, '--table-id', TABLE,
                            '--json', json.dumps({'update_records': patch}, ensure_ascii=False),
                            '--profile', 'dsh-kb', '--as', 'bot'], capture_output=True, text=True, cwd='/tmp')
        print(f"\n写入 {len(patch)} 行 ｜ rc {w.returncode} {str(w.stdout or '')[:90]}")
    return 0


if __name__ == '__main__':
    sys.exit(main())