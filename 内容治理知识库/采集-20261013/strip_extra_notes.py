#!/usr/bin/env python3
"""把「问题分类汇总」格里**多余的 ⚠️ 口径说明**删掉（Owner 2026-10-16：「把多余口径删除」）。

为什么删（Owner 的两条裁定合起来读）：
  · 2026-10-15：「**这一格只放 PRD 的『审查结论』块，不要自己加其他内容**」；
  · 2026-10-16：「把多余口径删除」。
而这 12 格里的 ⚠️ 口径是我 2026-10-15 亲自挂上去的（`backfill_confidence_notes.py`，
当时的口径是 10-09 那句「口径必须跟数一起进表」）——**那条已被 10-15 的裁定取代**，
存量却没清 ⇒ 现在的表现是「同一格里既有 PRD 块、又有一段内部口径」。

删什么、不删什么（**判据只有一份**，干跑与 selftest 共用）：
  · 只认**行首**的 `⚠️ 口径：`（前面是换行或字符串开头）；
  · 只删它**到格尾**的那一段，且那一段里**不许**再出现 PRD 块的内容
    （`【审查结论` / `→ 查看完整问题清单` / `建议转 @` / `请修改后重新提交`）——
    命中就**拒改这一格**并出声（宁可不动，不许把 PRD 块切掉一半）；
  · 条目正文里出现的 ⚠️（实测真有一行：行 50 的建议里写着「⚠️ 本机取到 HTTP 404…」，
    它前面是空格、不是行首）**一个字都不碰**。

用法：
  python3 strip_extra_notes.py             # 干跑（只打印会改哪些格）
  python3 strip_extra_notes.py --apply     # 真写（先备份，写完回读核对）
  python3 strip_extra_notes.py --selftest  # 反向对照
"""
import argparse
import json
import os
import re
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
BACKUP = os.path.join(HERE, 'backup_strip_notes_20261016')
LARK = os.path.expanduser('~/.dsh/bin/lark-cli')
BASE, TABLE = 'RY2UbCRjXaeeWwscUPScVN5AnQc', 'tblavfbMDMeRsulo'
FIELD = '问题分类汇总'
MARK = '⚠️ 口径：'
#: 删除段里**不许**出现的东西（出现了就说明切到 PRD 块里面去了）
PRD_KEEP = ['【审查结论', '→ 查看完整问题清单', '建议转 @', '请修改后重新提交', '逐条问题']


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


def read_table(out='/tmp/tbl_strip.ndjson'):
    subprocess.run([LARK, 'base', '+record-list', '--base-token', BASE, '--table-id', TABLE,
                    '--limit', '2000', '--format', 'ndjson', '--output', out, '--overwrite',
                    '--profile', 'dsh-kb', '--as', 'bot'], capture_output=True, text=True, cwd='/tmp')
    return [json.loads(l) for l in open(out, encoding='utf-8') if l.strip()]


def tail_start(cell):
    """行首 `⚠️ 口径：` 的位置；没有就返回 -1。"""
    for m in re.finditer(re.escape(MARK), cell):
        i = m.start()
        if i == 0 or cell[i - 1] == '\n':
            return i
    return -1


def strip_cell(cell):
    """返回 (新格, 原因)。不改时新格 = 原格。"""
    c = str(cell or '')
    i = tail_start(c)
    if i < 0:
        return c, '没有行首口径'
    tail = c[i:]
    bad = [k for k in PRD_KEEP if k in tail]
    if bad:
        return c, '拒改：口径段里含 PRD 内容 ' + '／'.join(bad)
    new = c[:i].rstrip()
    if '【审查结论' not in new:
        return c, '拒改：删完就不剩 PRD 结论行了'
    return new, f'删掉口径段 {len(tail)} 字'


def plan(rows):
    out, why = {}, []
    for r in rows:
        cell = plain(r.get(FIELD))
        new, reason = strip_cell(cell)
        if new != cell:
            out[r['record_id']] = {FIELD: new}
            why.append((plain(r.get('内容 ID')), r['record_id'], reason, len(cell), len(new)))
    return out, why


def selftest():
    cases = [
        ('行首口径段 ⇒ 删掉，PRD 块留着',
         '【审查结论：REVIEW】共发现 2 处。\n\n逐条问题\n· 合规类问题：1 个\n\n请修改后重新提交。\n\n⚠️ 口径：本格 0 不是零风险。',
         True),
        ('条目正文里的 ⚠️（非行首）⇒ 一个字不碰',
         '【审查结论：REVIEW】共发现 1 处。\n\n1.【合规】图 1  —— 无库内依据\n   建议：先做 A，⚠️ 本机取到 HTTP 404\n\n请修改后重新提交。',
         False),
        ('口径段里若混进 PRD 内容 ⇒ 拒改（宁可不动）',
         '【审查结论：REVIEW】共发现 1 处。\n\n⚠️ 口径：说明\n\n请修改后重新提交。',
         False),
        ('本来就干净的格 ⇒ 不改',
         '【审查结论：PASS】未发现已知底线风险。\n\n建议转 @sign-off 责任人 进行 sign-off。',
         False),
    ]
    bad = 0
    for name, cell, want in cases:
        new, reason = strip_cell(cell)
        ok = (new != cell) == want
        bad += 0 if ok else 1
        print(f"  {'✅' if ok else '✗'} {name} ⇒ {reason}")
    print('selftest ' + ('全绿' if bad == 0 else f'{bad} 项红'))
    return 0 if bad == 0 else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true')
    ap.add_argument('--selftest', action='store_true')
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    rows = read_table()
    patch, why = plan(rows)
    print(f"表内 {len(rows)} 行 ｜ 命中待删 {len(patch)} 格")
    for cid, rid, reason, n0, n1 in why:
        print(f"  {cid[:46]:48s} {rid}  {n0}→{n1} 字  {reason}")
    if not a.apply:
        print('（未加 --apply：什么都没写）')
        return 0
    if not patch:
        return 0
    os.makedirs(BACKUP, exist_ok=True)
    before = {r['record_id']: plain(r.get(FIELD)) for r in rows if r['record_id'] in patch}
    json.dump(before, open(os.path.join(BACKUP, 'cells_before_20261016.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    w = subprocess.run([LARK, 'base', '+record-batch-update', '--base-token', BASE, '--table-id', TABLE,
                        '--json', json.dumps({'update_records': patch}, ensure_ascii=False),
                        '--profile', 'dsh-kb', '--as', 'bot'], capture_output=True, text=True, cwd='/tmp')
    print(f"写入 {len(patch)} 格 ｜ rc={w.returncode} {str(w.stdout or '')[:100]} {str(w.stderr or '')[:160]}")
    if w.returncode != 0:
        return 3
    # 回读核对：写下去的那一格必须**逐字**等于计划值，且不再含口径段
    after = {r['record_id']: plain(r.get(FIELD)) for r in read_table('/tmp/tbl_strip_after.ndjson')}
    miss = [rid for rid in patch if after.get(rid) != patch[rid][FIELD]]
    dirty = [rid for rid in patch if tail_start(after.get(rid, '')) >= 0]
    print(f"回读：{len(patch) - len(miss)}/{len(patch)} 与计划逐字一致 ｜ 仍带口径段 {len(dirty)} 格")
    for rid in miss[:5]:
        print('  ✗ 不一致', rid, repr(after.get(rid, '')[:60]))
    json.dump({rid: after[rid] for rid in patch}, open(os.path.join(BACKUP, 'cells_after_20261016.json'),
                                                       'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    return 0 if (not miss and not dirty) else 3


if __name__ == '__main__':
    raise SystemExit(main())
