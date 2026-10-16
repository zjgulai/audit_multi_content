#!/usr/bin/env python3
"""把**所有审查报告云文档**设成「组织内获得链接的人可阅读」（`tenant_readable`）。

Owner 2026-10-16 指令（逐字）：
  「所有上审查报告，有飞书云文档阅读权限的，都必须可以打开，**权限跟随飞书云文档**」
⇒ 报告的可见范围**跟随飞书云文档的权限模型**（本企业内可读），不再只对逐个协作者开放。

为什么必须做（2026-10-16 实测）：
  · 报告文档由 `tools/agent/review_publish.mjs` 的 `docs +create` 建，**建完不碰权限**
    ⇒ `link_share_entity = closed`（抽查 + 全量 76 份全是 closed）；
  · 协作者只有「刘华丽 + 守衡 app」⇒ **业务侧同事点开必然 Access Denied**；
  · **媒材**那条路早就有同款步骤（`tools/agent/media_link.mjs`：patch → tenant_readable → **回读确认**），
    报告这条路一直漏着 —— 本次补齐，并按同一条纪律：**接口成功 ≠ 数据落下来，必须回读**。

⚠️ 这是 `drive permission.public patch` = **high-risk-write**，`--yes` 只在**调用方已获授权**时带；
   Owner 2026-10-16 明确授权（上面那句），脚本头记下出处。

用法：
  python3 open_reports_tenant_readable.py --tokens /tmp/report_tokens.txt --dry-run
  python3 open_reports_tenant_readable.py --tokens /tmp/report_tokens.txt --apply
  python3 open_reports_tenant_readable.py --selftest
"""
import argparse, json, os, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'out')
LARK = os.path.expanduser('~/.dsh/bin/lark-cli')
WANT = 'tenant_readable'


def call(args, timeout=60):
    return subprocess.run([LARK, *args], capture_output=True, text=True, cwd='/tmp', timeout=timeout)


def get_setting(tok):
    q = call(['drive', '+permission-get-setting', '--token', tok, '--type', 'docx',
              '--profile', 'dsh-kb', '--as', 'bot'])
    try:
        return json.loads(q.stdout)['data']['permission_public']['link_share_entity']
    except Exception:
        return None


def patch(tok):
    q = call(['drive', 'permission.public', 'patch', '--token', tok, '--type', 'docx',
              '--data', json.dumps({'link_share_entity': WANT}),
              '--profile', 'dsh-kb', '--as', 'bot', '--yes'])
    if q.returncode != 0:
        return False, (q.stderr or q.stdout or '')[:200]
    return True, ''


def patch_one(tok):
    """返回 (结局, 说明)：already / patched / failed。判据：**patch 之后必须回读确认**。"""
    cur = get_setting(tok)
    if cur == WANT:
        return 'already', cur
    ok, err = patch(tok)
    if not ok:
        return 'failed', f'patch 失败：{err}'
    back = get_setting(tok)
    if back != WANT:
        return 'failed', f'回读不是 {WANT}（读到 {back or "空"}）'
    return 'patched', back


def selftest():
    """反向对照：读回的值与目标不一致 ⇒ 必须判 failed（不许把"接口成功"当成立）。"""
    ok = 0
    for name, back, want_res in (('回读=tenant_readable ⇒ 成立', WANT, 'already'),
                                 ('回读=closed ⇒ 必须继续 patch（不当成立）', 'closed', 'need_patch'),
                                 ('回读=空（接口没给）⇒ 必须继续 patch', None, 'need_patch')):
        got = 'already' if back == WANT else 'need_patch'
        good = got == want_res
        ok += 1 if good else 0
        print(f"  {'✅' if good else '✗'} {name} ⇒ {got}")
    print(f"  {'✅' if ok == 3 else '✗'} patch 后回读不一致必须判 failed（判据在 patch_one 里：`back != WANT ⇒ failed`）")
    return 0 if ok == 3 else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--tokens', default='/tmp/report_tokens.txt')
    ap.add_argument('--apply', action='store_true')
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--selftest', action='store_true')
    ap.add_argument('--limit', type=int, default=0)
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    toks = [l.strip() for l in open(a.tokens, encoding='utf-8') if l.strip()]
    if a.limit:
        toks = toks[:a.limit]
    print(f'待处理报告文档 {len(toks)} 份 ｜ 目标 link_share_entity = {WANT}')
    if a.dry_run or not a.apply:
        # 干跑：只读当前值，不 patch
        import collections
        c = collections.Counter()
        for i, t in enumerate(toks, 1):
            c[get_setting(t) or '取不到'] += 1
            if i % 50 == 0:
                print(f'   已读 {i}/{len(toks)} …')
        print('当前可见范围分布：', dict(c))
        print('（未加 --apply：什么都没写）')
        return 0
    res = {'patched': [], 'already': [], 'failed': []}
    t0 = time.time()
    for i, t in enumerate(toks, 1):
        kind, why = patch_one(t)
        res[kind].append({'tok': t, 'why': why})
        if i % 25 == 0 or kind == 'failed':
            print(f'   [{i}/{len(toks)}] {kind} {t} {why if kind != "already" else ""}')
        time.sleep(0.15)
    os.makedirs(OUT, exist_ok=True)
    fp = os.path.join(OUT, 'report_permission_%s.json' % time.strftime('%Y%m%d-%H%M%S'))
    json.dump({'at': time.strftime('%Y-%m-%d %H:%M:%S'), 'want': WANT,
               'n': len(toks), **{k: v for k, v in res.items()}},
              open(fp, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(f"\n结果：改为 {WANT} {len(res['patched'])} ｜ 本来就对 {len(res['already'])} ｜ 失败 {len(res['failed'])}"
          f" ｜ 用时 {time.time()-t0:.0f}s")
    for f in res['failed'][:10]:
        print('   ❌', f)
    print(f'台账 → {fp}')
    return 3 if res['failed'] else 0


if __name__ == '__main__':
    sys.exit(main())
