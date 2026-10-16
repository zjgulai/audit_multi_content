#!/usr/bin/env python3
"""把 **80 行的报告链接一次补齐**（Owner 2026-10-15：「80条补齐所有的 报告链接，本次补齐，不要优化落知识库」）。

★ 边界（照 Owner 原话）：**只补数据，不做优化、不落知识库** ——
   不改引擎、不写 `PMO/已修问题.jsonl`、不 ingest 任何条目；这一支只碰 `10/14重跑报告链接` 一列。

取值优先级（逐行取**最新**的一条，取不到就留空并在报告里点名，**绝不编**）：
  ① 格子里那条报告链接（`→ 查看完整问题清单与修改建议：<url>`）—— 这一行**这一次**审查的产物；
  ② 卡上那条（台账 `message_ids` 取回真卡，卡里有 `/docx/<token>`）—— 1–2 条的行只在卡上有；
  ③ 结论表里**同素材最新**那一行的 `报告链接`（图片/视频行按 `[图片]图注：` 前缀、文案行按原文前缀）；
  ④ 台账 `report_url`（按 内容 ID）。

用法：
  python3 backfill_all_report_links.py            # 干跑：逐行打印将写什么、取自哪
  python3 backfill_all_report_links.py --apply
"""
# ★ 2026-10-16（Owner 改名同步）：这一列的名字**不许写死** —— 名字与判据都在 link_col.py
from link_col import LINK_COL_CANDIDATES, resolve_from_fields, pick_link  # noqa: E402
import argparse, json, os, re, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
BACKUP = os.path.join(HERE, 'backup_pass_rerun_20261015-105156')
LARK = os.path.expanduser('~/.dsh/bin/lark-cli')
BASE, TABLE, RESULT_TABLE = 'RY2UbCRjXaeeWwscUPScVN5AnQc', 'tblavfbMDMeRsulo', 'tblCXPQVzfFWWCon'
LEDGER = '/Users/lute/Project/audit_multi_content/PMO/shouheng-state/batch-review.json'
COL = LINK_COL_CANDIDATES[1]   # ★ 见 link_col.py：改名后这里会被 resolve 覆盖
#: ⑤ 跑批日志里「[i/N] <内容ID>」之后那句「📄 合并报告已建（问题数 N）：<docx 链接>」——
#   PASS 行往往**只有这一处**留着报告链接（格子按 §5.3.2 不带链接、卡上也没有）。
LOGLINKS = {}


def harvest_log_links(paths):
    """从跑批日志按行号顺序配对：`[i/N] <内容ID>` ⇒ 其后第一条 `/docx/` 链接。"""
    for p in paths:
        if not os.path.exists(p):
            continue
        cur = None
        for line in open(p, encoding='utf-8', errors='ignore'):
            m = re.match(r'\[\d+/\d+\]\s+([A-Za-z0-9_\-]+)', line.strip())
            if m:
                cur = m.group(1)
                continue
            if cur:
                u = docx_of(line)
                if u and cur not in LOGLINKS:
                    LOGLINKS[cur] = u
    return LOGLINKS


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


def docx_of(s):
    m = re.search(r'https://[^\s)]+/docx/[A-Za-z0-9]+', str(s or ''))
    return m.group(0) if m else ''


def read_table(table, out):
    subprocess.run([LARK, 'base', '+record-list', '--base-token', BASE, '--table-id', table,
                    '--limit', '2000', '--format', 'ndjson', '--output', out, '--overwrite',
                    '--profile', 'dsh-kb', '--as', 'bot'], capture_output=True, text=True, cwd='/tmp')
    return [json.loads(l) for l in open(out, encoding='utf-8') if l.strip()]


def fetch_cards(led):
    mids = [m for v in led.values() if isinstance(v, dict) for m in (v.get('message_ids') or [])]
    cards = {}
    for i in range(0, len(mids), 50):
        q = subprocess.run([LARK, 'im', '+messages-mget', '--message-ids', ','.join(mids[i:i + 50]),
                            '--profile', 'dsh-kb', '--as', 'bot', '--json'],
                           capture_output=True, text=True, cwd='/tmp')
        try:
            for m in json.loads(q.stdout)['data']['messages']:
                cards[m['message_id']] = m.get('content', '')
        except Exception:
            pass
    return cards


def res_index(res_rows):
    """结论表按「素材键」索引：每个键下挂着**所有**同素材行（时间倒序）。

    为什么不是只留最新一条：最新那条可能**没有** `报告链接`（PASS/未发布那一版），
    而同一素材早一轮的行走过发布、是带链接的 —— Owner 要的是「80 行都有链接」，
    所以同一素材里**取第一条带链接的**（时间倒序里第一条），不是第一条。"""
    idx = {}
    for r in sorted(res_rows, key=lambda x: str(x.get('写入时间') or ''), reverse=True):
        s = norm(plain(r.get('送审问题')))
        key = ('img', s[:70]) if s.startswith('[图片]图注：') else ('txt', s[:120])
        idx.setdefault(key, []).append(r)
    return idx


def row_key(row):
    t = plain(row.get('内容类型')).strip()
    mat = plain(row.get('采集数据'))
    if t == '图片':
        m = re.search(r'图注：(.+)', mat)
        return ('img', ('[图片]图注：' + norm(m.group(1)))[:70]) if m else None
    if t == '视频':
        return ('img', ('[图片]图注：' + norm(mat.split('\n')[0]))[:70])
    return ('txt', norm(mat)[:120])


def pick_link(row, idx, led, cards):
    """按 ①格 ②卡 ③结论表 ④台账 ⑤跑批日志 取链接；都取不到回 ('', '无')。

    ★ 2026-10-15（Owner 口径）：「**PASS 不用输出报告**」⇒ PASS 行**一律不填**，
      即使卡上/旧记录里有一条链接也不填（那是历史版本或别的口径留下的）。
    """
    if plain(row.get('Agent 结论')).strip().upper() == 'PASS':
        return '', 'PASS 不输出报告'
    cid = plain(row.get('内容 ID'))
    cell = plain(row.get('问题分类汇总'))
    u = docx_of(cell)
    if u:
        return u, '①格子'
    mid = next(iter((led.get(cid) or {}).get('message_ids') or []), None)
    if mid and cards.get(mid):
        u = docx_of(cards[mid])
        if u:
            return u, '②卡'
    k = row_key(row)
    if k:
        for hit in idx.get(k) or []:
            u = docx_of(plain(hit.get('报告链接')))
            if u:
                return u, '③结论表'
    u = docx_of(str((led.get(cid) or {}).get('report_url') or ''))
    if u:
        return u, '④台账'
    u = LOGLINKS.get(cid, '')
    if u:
        return u, '⑤跑批留底日志'
    return '', '无'


def selftest():
    """反向对照：已有正确链接的行不许改；四处都取不到时**不许编**。"""
    rows = [{'record_id': 'A', '内容 ID': 'x1', '内容类型': '文案', '采集数据': 'mat',
             '问题分类汇总': '…\n→ 查看完整问题清单与修改建议：https://momcozy-in.feishu.cn/docx/AAA111\n',
             COL: '[内容审查报告](https://momcozy-in.feishu.cn/docx/AAA111)'},
            {'record_id': 'B', '内容 ID': 'x2', '内容类型': '文案', '采集数据': 'mat2',
             '问题分类汇总': '…no link…', COL: ''}]
    idx, led, cards = {}, {}, {'_': ''}
    p = plan(rows, idx, led, cards)[0]
    ok1 = 'A' not in p
    ok2 = 'B' not in p
    print(f"  {'✅' if ok1 else '✗'} 链接已对 ⇒ 不动")
    print(f"  {'✅' if ok2 else '✗'} 四处都取不到 ⇒ **留空**、不编")
    # 卡上有、格上没有 ⇒ 应写卡上那条
    led2 = {'x2': {'message_ids': ['m1']}}
    cards2 = {'m1': '<card>→ 查看完整问题清单与修改建议：[https://momcozy-in.feishu.cn/docx/BBB222](x)</card>'}
    p2 = plan(rows, {}, led2, cards2)[0]
    ok3 = p2.get('B', {}).get(COL, '').endswith('BBB222)')
    print(f"  {'✅' if ok3 else '✗'} 卡上有、格上没有 ⇒ 补卡上那条")
    return 0 if (ok1 and ok2 and ok3) else 1


def plan(rows, idx, led, cards):
    patch, report = {}, []
    for r in rows:
        cid = plain(r.get('内容 ID'))
        if not cid.strip():
            continue
        u, src = pick_link(r, idx, led, cards)
        cur = docx_of(plain(r.get(COL)))
        if u and u != cur:
            patch[r['record_id']] = {COL: '[内容审查报告](' + u + ')'}
            report.append((cid, plain(r.get('内容类型')), src, (cur or '空')[-8:], u[-10:]))
        elif not u:
            report.append((cid, plain(r.get('内容类型')), src, (cur or '空')[-8:], '—'))
    return patch, report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true')
    ap.add_argument('--selftest', action='store_true')
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    rows = read_table(TABLE, '/tmp/links_tbl.ndjson')
    res_rows = read_table(RESULT_TABLE, '/tmp/links_res.ndjson')
    led = json.load(open(LEDGER, encoding='utf-8'))['items']
    cards = fetch_cards(led)
    harvest_log_links(['/tmp/tupian35_20261015.log', '/tmp/img5_rerun_20261015.log',
                       '/tmp/wenan_social10_20261015.log', '/tmp/review_full_20261015-1643.log'])
    print(f'⑤ 跑批日志里取到 {len(LOGLINKS)} 行的报告链接')
    idx = res_index(res_rows)
    patch, report = plan(rows, idx, led, cards)
    nolink = [x for x in report if x[4] == '—']
    print(f"80 行里：将写 {len(patch)} 行 ｜ 四处都取不到链接 {len(nolink)} 行")
    for cid, t, src, old, new in report[:30]:
        print(f"  {cid[:46]:46s} {t:3s} {src:6s} {old} → {new}")
    if len(report) > 30:
        print(f'  … 另有 {len(report) - 30} 行')
    if nolink:
        print('  ⚠️ 取不到链接的行（**留空、不编**）：')
        for cid, t, src, old, new in nolink:
            print(f'     · {cid}（{t}，列现值 {old}）')
    if not a.apply:
        print('（未加 --apply：什么都没写）')
        return 0
    if patch:
        os.makedirs(BACKUP, exist_ok=True)
        json.dump({r['record_id']: plain(r.get(COL)) for r in rows if r['record_id'] in patch},
                  open(os.path.join(BACKUP, 'link_col_before_backfill_all_20261015.json'), 'w', encoding='utf-8'),
                  ensure_ascii=False, indent=1)
        w = subprocess.run([LARK, 'base', '+record-batch-update', '--base-token', BASE, '--table-id', TABLE,
                            '--json', json.dumps({'update_records': patch}, ensure_ascii=False),
                            '--profile', 'dsh-kb', '--as', 'bot'], capture_output=True, text=True, cwd='/tmp')
        print(f"写入 {len(patch)} 行 ｜ rc={w.returncode} {str(w.stdout or '')[:80]}")
        if w.returncode != 0:
            return 3
    rows2 = read_table(TABLE, '/tmp/links_tbl2.ndjson')
    have = {r['record_id']: docx_of(plain(r.get(COL))) for r in rows2}
    ok = sum(1 for rid, v in have.items() if v)
    bad = [rid for rid in patch if have.get(rid, '') != docx_of(patch[rid][COL])]
    print(f"回读：80 行里**有链接** {ok} 行 ｜ 写入未生效 {len(bad)} 行 {bad[:4]}")
    return 0 if not bad else 4


if __name__ == '__main__':
    sys.exit(main())
