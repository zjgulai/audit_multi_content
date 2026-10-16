#!/usr/bin/env python3
"""修「社媒文案」的双编码乱码（= 采集器把 UTF-8 当 latin-1 反转义造成的素材污染）。

病灶（2026-10-15 实测）：`collect_wenan35.py::collect_social` 用
`re.search(r'"shortDescription":"(.*?)","isCrawlable"')` 抓到的是 **JSON 字符串字面量**，
却用 `.encode().decode('unicode_escape')` 反转义 —— 那一手把已经是 UTF-8 的汉字/破折号/引号
按 latin-1 读回去 ⇒ 正文里 `—` 变成 `â\\x80\\x94`、`“` 变成 `â\\x80\\x9c`、`✅️` 变成 `â\\x9c\\x94ï¸\\x8f`。
后果有两层，第二层更贵：
  ① 表里交给业务侧看的素材本身是乱码；
  ② 依据「文案原文」做的评审，是在**被污染的文本**上判的 ⇒ 结论不可信。

本脚本只做一件事：**用修好的解码器重采这 10 条，覆盖表里的 `采集数据`**（不动其它任何列）。
  python3 fix_social_wenan_mojibake.py            # 干跑，打印将写什么
  python3 fix_social_wenan_mojibake.py --apply     # 真写（先备份旧值）
"""
import argparse, importlib.util, json, os, re, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
BACKUP = os.path.join(HERE, 'backup_pass_rerun_20261015-105156')
LARK = os.path.expanduser('~/.dsh/bin/lark-cli')
BASE, TABLE = 'RY2UbCRjXaeeWwscUPScVN5AnQc', 'tblavfbMDMeRsulo'
MOJI = re.compile(r'[âÃï][\x80-\xbf]')          # 双编码乱码的指纹


def load_collector():
    spec = importlib.util.spec_from_file_location('cw', os.path.join(HERE, 'collect_wenan35.py'))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


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
    out = '/tmp/tbl80_for_fix.ndjson'
    subprocess.run([LARK, 'base', '+record-list', '--base-token', BASE, '--table-id', TABLE,
                    '--limit', '2000', '--format', 'ndjson', '--output', out, '--overwrite',
                    '--profile', 'dsh-kb', '--as', 'bot'], capture_output=True, text=True, cwd='/tmp')
    return [json.loads(l) for l in open(out, encoding='utf-8') if l.strip()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true')
    a = ap.parse_args()

    cw = load_collector()
    soc = cw.collect_social(10)
    fresh = {}
    for it in soc:
        txt = cw.render(it)[:cw.TOTAL_CAP].rstrip()
        fresh[it['cid']] = txt                       # key = MC-US-YT-<videoId>
    bad = [k for k, v in fresh.items() if MOJI.search(v)]
    print(f"重采 {len(fresh)} 条 ｜ 仍乱码 {len(bad)} 条 {bad}")
    if bad:
        print("✗ 重采结果里仍有乱码 —— 不写，先把解码修对")
        return 2

    rows = read_table()
    patch, report, before = {}, [], {}
    for r in rows:
        if plain(r.get('内容类型')) != '文案':
            continue
        cid = plain(r.get('内容 ID'))
        if not cid.startswith('MC-US-YT-'):
            continue
        vid = cid[:-4] if cid.endswith('-WEN') else cid
        new = fresh.get(vid)
        if new is None:
            print(f"  ⚠️ {cid} 在重采结果里找不到（videoId {vid}）⇒ 跳过")
            continue
        cur = plain(r.get('采集数据'))
        if cur.strip() == new.strip():
            report.append((cid, '已一致', 0))
            continue
        before[r['record_id']] = cur
        patch[r['record_id']] = {'采集数据': new}
        report.append((cid, '将覆盖', len(new) - len(cur)))
    for cid, what, d in report:
        print(f"  {cid:34s} {what:6s} Δ长度 {d:+d}")
    print(f"合计将写 {len(patch)} 行")
    if not a.apply:
        print("（未加 --apply：什么都没写）")
        return 0
    if patch:
        os.makedirs(BACKUP, exist_ok=True)
        json.dump(before, open(os.path.join(BACKUP, 'social_wenan_mojibake_before_20261015.json'),
                               'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        w = subprocess.run([LARK, 'base', '+record-batch-update', '--base-token', BASE, '--table-id', TABLE,
                            '--json', json.dumps({'update_records': patch}, ensure_ascii=False),
                            '--profile', 'dsh-kb', '--as', 'bot'], capture_output=True, text=True, cwd='/tmp')
        print(f"写入 rc={w.returncode} {str(w.stdout or '')[:120]} {str(w.stderr or '')[:160]}")
        if w.returncode != 0:
            return 3
    # 回读复核：乱码必须为 0，且与重采结果逐字一致
    rows2 = read_table()
    n_ok = n_bad = n_diff = 0
    for r in rows2:
        cid = plain(r.get('内容 ID'))
        if plain(r.get('内容类型')) != '文案' or not cid.startswith('MC-US-YT-'):
            continue
        vid = cid[:-4] if cid.endswith('-WEN') else cid
        cur = plain(r.get('采集数据'))
        if MOJI.search(cur):
            n_bad += 1
            print(f"  ✗ 回读仍有乱码 {cid}")
        elif fresh.get(vid) and cur.strip() != fresh[vid].strip():
            n_diff += 1
            print(f"  ✗ 回读与重采不一致 {cid}")
        else:
            n_ok += 1
    print(f"回读复核：一致 {n_ok} ｜ 乱码 {n_bad} ｜ 不一致 {n_diff}")
    return 0 if (n_bad == 0 and n_diff == 0) else 4


if __name__ == '__main__':
    sys.exit(main())
