#!/usr/bin/env python3
"""把 `10/14重跑报告链接` 列对齐到**格里那一行的报告链接**（Owner：「新跑完的报告整个表格中的字段
要同步更新，数据要对齐」）。

口径（沿用本表既有约定，34 行的非空值就是这个格式）：
  · 格子有报告链接 ⇒ 该列写 `[内容审查报告](<那个链接>)`；
  · 格子没有链接行（PASS 行、问题数 <3 的逐条行）⇒ 该列**留空**，不编。
只比对 `/docx/<token>`，token 一致就不动；`--skip` 里的行不动（它们正在重跑，跑完再同步）。

  python3 sync_link_column.py                 # 干跑
  python3 sync_link_column.py --apply [--skip <内容ID> ...]
"""
# ★ 2026-10-16（Owner 改名同步）：这一列的名字**不许写死** —— 名字与判据都在 link_col.py
from link_col import LINK_COL_CANDIDATES, resolve_from_fields, pick_link  # noqa: E402
import argparse, json, os, re, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
BACKUP = os.path.join(HERE, 'backup_pass_rerun_20261015-105156')
LARK = os.path.expanduser('~/.dsh/bin/lark-cli')
BASE, TABLE = 'RY2UbCRjXaeeWwscUPScVN5AnQc', 'tblavfbMDMeRsulo'
COL = LINK_COL_CANDIDATES[1]   # ★ 见 link_col.py：改名后这里会被 resolve 覆盖


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


def read_table():
    out = '/tmp/tbl_sync_link.ndjson'
    subprocess.run([LARK, 'base', '+record-list', '--base-token', BASE, '--table-id', TABLE,
                    '--limit', '2000', '--format', 'ndjson', '--output', out, '--overwrite',
                    '--profile', 'dsh-kb', '--as', 'bot'], capture_output=True, text=True, cwd='/tmp')
    return [json.loads(l) for l in open(out, encoding='utf-8') if l.strip()]


def token_of(s):
    return (re.search(r'/docx/([A-Za-z0-9]+)', str(s or '')) or [None, None])[1]


def want_value(cell):
    """格子里的报告链接 ⇒ 该列应有的值；格子没有链接行 ⇒ 空串（**不编**）。"""
    m = re.search(r'https://[^\s)]+/docx/[A-Za-z0-9]+', str(cell or ''))
    if not m:
        return ''
    return '[内容审查报告](' + m.group(0) + ')'


def plan(rows, skip):
    patch, report = {}, []
    for r in rows:
        cid = plain(r.get('内容 ID'))
        if not cid.strip() or cid in skip:
            continue
        cell = plain(r.get('问题分类汇总'))
        if not cell.strip():
            continue
        cur = plain(r.get(COL))
        want = want_value(cell)
        if want and token_of(cur) != token_of(cell):
            patch[r['record_id']] = {COL: want}
            report.append((cid, f"「{token_of(cur) or '空'}」→「{token_of(cell)}」"))
        # ★ 2026-10-15：**不再清空**。原来这里写的是「格子里没有链接行 ⇒ 清空」，
        #   本意是「格子＜3 条时按 §5.3.5 不带链接」，但它把**从卡上补齐的那批**也抹掉了 ——
        #   而 Owner 要的是「80 条补齐所有的报告链接」（PASS 除外）。
        #   ⇒ 分工改成：**清空只由补齐脚本按 PASS 口径做**；本脚本只管「格子里有的，列里要一致」。
    return patch, report


def selftest():
    """反向对照：token 一致不许动；缺链接行不许编；token 不一致必须改。"""
    cell = '【审查结论：BLOCK】…\n\n→ 查看完整问题清单与修改建议：https://momcozy-in.feishu.cn/docx/AAA111\n\n请修改后重新提交。'
    nolink = '【审查结论：PASS】未发现已知底线风险，可转交 @sign-off 责任人 进行 sign-off。'
    rows = [
        {'record_id': 'A', '内容 ID': 'x1', '问题分类汇总': cell, COL: '[内容审查报告](https://momcozy-in.feishu.cn/docx/AAA111)'},
        {'record_id': 'B', '内容 ID': 'x2', '问题分类汇总': cell, COL: '[内容审查报告](https://momcozy-in.feishu.cn/docx/BBB222)'},
        {'record_id': 'C', '内容 ID': 'x3', '问题分类汇总': cell, COL: ''},
        {'record_id': 'D', '内容 ID': 'x4', '问题分类汇总': nolink, COL: '[内容审查报告](https://momcozy-in.feishu.cn/docx/CCC333)'},
    ]
    p, _ = plan(rows, set())
    ok1 = 'A' not in p
    ok2 = p.get('B', {}).get(COL, '').endswith('AAA111)')
    ok3 = p.get('C', {}).get(COL, '').endswith('AAA111)')
    ok4 = p.get('D', {}).get(COL) == ''
    for name, ok in (('token 一致 ⇒ 不动', ok1), ('token 不一致 ⇒ 改成格子那个', ok2),
                     ('列空 ⇒ 补格子那个', ok3), ('格子没链接行 ⇒ 清空、不编', ok4)):
        print(f"  {'✅' if ok else '✗'} {name}")
    return 0 if (ok1 and ok2 and ok3 and ok4) else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true')
    ap.add_argument('--selftest', action='store_true')
    ap.add_argument('--skip', nargs='*', default=[])
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    rows = read_table()
    patch, report = plan(rows, set(a.skip))
    print(f"将写 {len(patch)} 行（跳过 {len(a.skip)} 个正在重跑的行）")
    for cid, what in report[:40]:
        print(f"  {cid[:52]:52s} {what}")
    if len(report) > 40:
        print(f'  … 另有 {len(report) - 40} 行')
    if not a.apply:
        print('（未加 --apply：什么都没写）')
        return 0
    if patch:
        os.makedirs(BACKUP, exist_ok=True)
        json.dump({r['record_id']: plain(r.get(COL)) for r in rows if r['record_id'] in patch},
                  open(os.path.join(BACKUP, 'link_col_before_sync_20261015.json'), 'w', encoding='utf-8'),
                  ensure_ascii=False, indent=1)
        w = subprocess.run([LARK, 'base', '+record-batch-update', '--base-token', BASE, '--table-id', TABLE,
                            '--json', json.dumps({'update_records': patch}, ensure_ascii=False),
                            '--profile', 'dsh-kb', '--as', 'bot'], capture_output=True, text=True, cwd='/tmp')
        print(f"写入 {len(patch)} 行 ｜ rc={w.returncode}")
        if w.returncode != 0:
            return 3
    rows2 = read_table()
    ok = bad = 0
    for r in rows2:
        rid = r.get('record_id')
        if rid not in patch:
            continue
        if plain(r.get(COL)).strip() == patch[rid][COL].strip():
            ok += 1
        else:
            bad += 1
            print(f'  ✗ 回读不一致 {rid}')
    # 全表复核：凡是格子有链接、且不在 skip 里的行，该列 token 必须一致
    mis = []
    for r in rows2:
        cid = plain(r.get('内容 ID'))
        if cid in set(a.skip):
            continue
        cell = plain(r.get('问题分类汇总'))
        if '查看完整问题清单' in cell and token_of(cell) != token_of(plain(r.get(COL))):
            mis.append(cid)
    print(f"回读复核：一致 {ok} ｜ 不一致 {bad} ｜ 全表仍不一致 {len(mis)} {mis[:5]}")
    return 0 if (bad == 0 and not mis) else 4


if __name__ == '__main__':
    sys.exit(main())
