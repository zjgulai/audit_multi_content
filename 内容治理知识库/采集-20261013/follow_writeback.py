#!/usr/bin/env python3
"""跟随写入器：批跑**每完成一条**就把结果写进采集表，**不等整批跑完**。

## 三件事（每次循环都做，不只对新完成的）

  ① 新报告 → 写进 `10/14重跑报告链接`
  ② `报告链接` → **还原成原始报告**（跑批器会把它刷成新链接，与库里 Owner 2026-10-06
     选定的方案 (c)「复用旧行已有的链接、不新建文档」不符）
  ③ ★ `问题数量` → **以 `10/14重跑报告链接` 那份报告声明的条数为准**，不一致就写正
     （Owner 2026-10-14 要求：「问题数量按照最新跑的报告中的数据来写，要对齐」）

⇒ ③ 做成**自检自愈**：每轮把**所有已有新链接的行**都核一遍，不是只核新完成的行。
   这样即便某一轮写入被跑批器的回填覆盖，下一轮会自动纠回来。

## 它只读账本、只写飞书表

  · 读：`PMO/shouheng-state/batch-review.json` 的 `answered_at` / `report_url` / `ran_from`
  · 写：采集表 `tblavfbMDMeRsulo` 的三列（`10/14重跑报告链接`、`报告链接`、`问题数量`）
  ⇒ **不碰跑批器、不碰账本**，两边不会互相踩。

用法：`python3 采集-20261013/follow_writeback.py [--until-done]`
"""
import argparse
import html
import json
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'out')
LARK = os.path.expanduser('~/.dsh/bin/lark-cli')
LEDGER = '/Users/lute/Project/audit_multi_content/PMO/shouheng-state/batch-review.json'
BASE, TABLE = 'RY2UbCRjXaeeWwscUPScVN5AnQc', 'tblavfbMDMeRsulo'
STATE = os.path.join(OUT, 'follow_writeback_state.json')
DOC_CACHE = os.path.join(OUT, 'doc_count_cache.json')
# ⚠ **UTC** —— 本轮 70 条起跑是本地 17:23 = UTC 09:23。账本的 `ran_from` 是 UTC ISO
#   （实测 `…09:23:18.718Z`）；拿本地时刻去比会**永远为假** ⇒ 一条都写不进去（踩过）。
RUN_STARTED = '2026-10-14T09:23'


def sh(args):
    return subprocess.run(args, capture_output=True, text=True)


def fetch_table():
    r = sh([LARK, 'base', '+record-list', '--base-token', BASE, '--table-id', TABLE,
            '--page-size', '200', '--format', 'json', '--profile', 'dsh-kb', '--as', 'bot'])
    return json.loads(r.stdout)['data']


def declared_count(tok, cache):
    """报告声明的条数。取不到返 None（**不猜**）。"""
    if tok in cache:
        return cache[tok]
    r = sh([LARK, 'docs', '+fetch', '--doc', tok, '--profile', 'dsh-kb', '--as', 'bot'])
    try:
        c = (json.loads(r.stdout or '{}').get('data') or {}).get('document', {}).get('content') or ''
    except Exception:
        c = ''
    t = re.sub(r'<br\s*/?>', '\n', c)
    t = re.sub(r'</(p|li|h[1-6]|td|tr)>', '\n', t)
    t = html.unescape(re.sub(r'<[^>]+>', '', t))
    n = None
    m = re.search(r'共发现\s*(\d+)\s*处', t)
    if m:
        n = int(m.group(1))
    else:
        m = re.search(r'问题数量[：:]\s*\**(\d+)', t)
        if m:
            n = int(m.group(1))
    cache[tok] = n
    return n


def batch_update(payload):
    r = sh([LARK, 'base', '+record-batch-update', '--base-token', BASE, '--table-id', TABLE,
            '--json', json.dumps(payload, ensure_ascii=False), '--profile', 'dsh-kb', '--as', 'bot'])
    return '"ok": true' in (r.stdout or ''), (r.stdout or r.stderr or '')[:200]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--until-done', action='store_true')
    a = ap.parse_args()

    todo = json.load(open(os.path.join(OUT, 'todo70.json'), encoding='utf-8'))
    orig = json.load(open(os.path.join(OUT, 'orig_links.json'), encoding='utf-8'))
    done = set(json.load(open(STATE, encoding='utf-8'))) if os.path.exists(STATE) else set()
    cache = json.load(open(DOC_CACHE, encoding='utf-8')) if os.path.exists(DOC_CACHE) else {}
    print(f'待跟 {len(todo)} 条 ｜ 已跟 {len(done)} 条', flush=True)

    while True:
        led = json.load(open(LEDGER, encoding='utf-8'))['items']
        wrote = 0
        # ── ① ②：新完成的 → 写新链接 + 还原原始链接 ──
        for cid in todo:
            if cid in done or cid not in led:
                continue
            d = led[cid]
            if not d.get('answered_at') or not d.get('report_url'):
                continue
            if str(d.get('ran_from') or '') < RUN_STARTED:
                continue
            url = d['report_url']
            m = re.search(r'/docx/([A-Za-z0-9]+)', url)
            if not m:
                continue
            # ★★ 2026-10-14（Owner）：「输出的飞书报告链接，需要我点击下下一步就能打开的」。
            #   病灶：这两格的**形态**不一样，写错了就点不开 ——
            #     · `10/14重跑报告链接` 是 **style=plain 的文本格**：写**裸 URL** 存进去是纯文本，
            #       飞书不会自动转超链接（**API 写不触发 UI 那个自动链接**）⇒ 只能复制粘贴。
            #       手改一格验证过：写 **`[内容审查报告](url)`** 存成的形状与 UI 改的**逐字一致**。
            #     · `报告链接` 是 **style=url 的 URL 格**：要**对象式** `{link, text}` ——
            #       写裸字符串会退化成 `[url](url)`（显示名变成一长串 URL，虽然能点但没法看）。
            #   ⇒ 两格都写**具名链接**，点名统一成 Owner 定的「内容审查报告」/ 沿用它既有的「审查报告」。
            # ⚠️ **必须写字符串**（不能写 `{link,text}` 对象）：lark-cli 的 `+record-batch-update`
            #   只认 string/number/boolean/null/数组 —— 对象会回
            #   `800010701 Cell value does not match any supported shape`（实测踩过）。
            #   对象式是 SDK（`lw.updateRecords`）才认的形态。
            fields = {'10/14重跑报告链接': f'[内容审查报告]({url})'}
            if orig[cid]['orig']:
                fields['报告链接'] = f"[审查报告](https://momcozy-in.feishu.cn/docx/{orig[cid]['orig']})" 
            ok, out = batch_update({'update_records': {orig[cid]['rid']: fields}})
            if ok:
                done.add(cid)
                wrote += 1
                print(f"  ✅ 链接 {cid:<42} → {m.group(1)}", flush=True)
            else:
                print(f"  ❌ 链接 {cid} 写入失败：{out}", flush=True)
        json.dump(sorted(done), open(STATE, 'w'), ensure_ascii=False, indent=1)

        # ── ③ 自检自愈：**链接**与**问题数量**都以账本/新报告为准 ──
        #   ⚠️ 为什么链接也要自检：`done` 是**一次性标记**，而**一单可以重跑**
        #      （今天重跑过 3 轮：占位符修复、抬头修复、模型侧 fail-closed）。
        #      重跑后账本 `report_url` 换了，而 `done` 里还有它 ⇒ **跳过** ⇒
        #      表里那格永远指着旧报告（实测 5 行，逐条可核）。
        #      ⇒ 判据从「跟过没有」改成「**表里的值是不是账本那个**」，不符就写正。
        fixed = checked = relinked = 0
        try:
            led_now = json.load(open(LEDGER, encoding='utf-8'))['items']
            d = fetch_table()
            F, rows, rids = d['fields'], d['data'], d['record_id_list']
            ifields = {n: i for i, n in enumerate(F)}
            for rid, r in zip(rids, rows):
                cid = r[ifields['内容 ID']]
                newu = r[ifields['10/14重跑报告链接']] or ''
                # ③a 链接：账本有报告 ⇒ 表里必须就是它（且必须是具名可点形态）
                lurl = str((led_now.get(cid) or {}).get('report_url') or '')
                lm = re.search(r'/docx/([A-Za-z0-9]+)', lurl)
                if lm:
                    want = f'[内容审查报告]({lurl})'
                    if str(newu) != want:
                        ok, out = batch_update({'update_records': {rid: {'10/14重跑报告链接': want}}})
                        if ok:
                            relinked += 1
                            print(f"  🔗 链接重跟 {cid:<42} → {lm.group(1)}", flush=True)
                            newu = want
                        else:
                            print(f"  ❌ 链接写入失败 {cid}：{out}", flush=True)
                m = re.search(r'/docx/([A-Za-z0-9]+)', str(newu))
                if not m:
                    continue
                checked += 1
                nrep = declared_count(m.group(1), cache)
                cur = r[ifields['问题数量']]
                cur = int(cur) if isinstance(cur, (int, float)) else (
                    int(cur) if str(cur).strip().isdigit() else None)
                if nrep is None or nrep == cur:
                    continue
                ok, out = batch_update({'update_records': {rid: {'问题数量': nrep}}})
                if ok:
                    fixed += 1
                    print(f"  🔧 问题数量 {cid:<42} {cur} → {nrep}", flush=True)
                else:
                    print(f"  ❌ 问题数量写入失败 {rid}：{out}", flush=True)
            json.dump(cache, open(DOC_CACHE, 'w'), ensure_ascii=False, indent=1)
        except Exception as e:                                     # noqa: BLE001
            print(f'  ⚠️ 对齐自检这一轮没跑成（下轮再来）：{e}', flush=True)

        leftover = [c for c in todo if c not in done]
        print(f'[{time.strftime("%H:%M:%S")}] 已跟 {len(done)}/{len(todo)} ｜ 本轮新写 {wrote} '
              f'｜ 链接重跟 {relinked} ｜ 问题数量 核 {checked} 纠 {fixed} ｜ 还剩 {len(leftover)}', flush=True)
        if not a.until_done:
            return 0
        if not leftover:
            print('全部跟完 ✅', flush=True)
            return 0
        time.sleep(20)


if __name__ == '__main__':
    sys.exit(main())
