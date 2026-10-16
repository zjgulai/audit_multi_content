#!/usr/bin/env python3
"""把这 80 条测试数据的审查报告，从 `kb/l7/reports/` 里认出来并清出去。

## 为什么会有这些文件

不是谁手动放的：**`kb/l8/review_run.sh` 与 `review.py` 按契约把每次评审落一份本地件**
（`kb/l7/reports/<run>.md` ＋ `.json`；发布件另落 `rv-<run>.feishu.md`）。
评审链读 L4–L6、写报告 —— **它不写知识层**，所以这 80 条从来没进 L0–L7。
但本地件确实落在 `kb/l7/` 树里，与知识库的产物混在一处。

## 怎么认（内容特征，不靠文件名）

`rv-` 是另一套 run 命名，配不上 `<run>.json`；所以按**素材特征**认：
每一行的 URL / ASIN / 内容 ID 都是唯一的，出现在报告里即可判定这一份属于这 80 条。

用法：
  python3 采集-20261013/purge_test_reports.py            # 只出清单
  python3 采集-20261013/purge_test_reports.py --apply    # 备份 + 移出 kb/
"""
import argparse
import glob
import importlib.util
import json
import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
REPORTS = os.path.join(ROOT, "kb/l7/reports")

spec = importlib.util.spec_from_file_location("p", os.path.join(HERE, "parse_table80.py"))
P = importlib.util.module_from_spec(spec)
spec.loader.exec_module(P)


def tokens_of(rows):
    """每个内容 ID → 它独有的特征串。"""
    out = {}
    for r in rows:
        cid = r["内容 ID"]
        txt = re.sub(r"\[([^\]]*)\]\((https?://[^)]+)\)", r"\2", r["采集数据"] or "")
        toks = set()
        for u in re.findall(r"https?://[^\s|]+", txt):
            u = u.strip().rstrip("）)。,，")
            if len(u) >= 30:
                toks.add(u)
        # ASIN（Amazon 行）
        m = re.search(r"/dp/([A-Z0-9]{10})", txt)
        if m:
            toks.add(m.group(1))
        toks.add(cid)                      # 内容 ID 本身
        out[cid] = {t for t in toks if len(t) >= 10}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    rows = P.parse(os.path.join(HERE, "out/table80_after.txt"))
    toks = tokens_of(rows)
    alltok = {}
    for cid, s in toks.items():
        for t in s:
            alltok.setdefault(t, cid)
    print(f"80 行 → {len(alltok)} 个特征串")

    files = sorted(glob.glob(os.path.join(REPORTS, "*")))
    matched = {}
    for f in files:
        base = os.path.basename(f)
        if base.startswith("."):
            continue
        try:
            txt = open(f, encoding="utf-8", errors="ignore").read()
        except Exception:
            continue
        for t, cid in alltok.items():
            if t in txt:
                matched[f] = cid
                break

    # ── 信号 B：账本时间窗 ⇒ 补上「素材里不含 URL」的那些行（图片/视频）────────
    #   账本 `ran_from`(UTC) + `secs` ⇒ 本地时间窗 ⇒ 取窗内 mtime 的 <run>.json。
    #   实测该法能把 80 行**全部**映射到报告（见 `map80_to_reports.py`）。
    import datetime
    led = json.load(open("/Users/lute/Project/audit_multi_content/PMO/shouheng-state/batch-review.json",
                         encoding="utf-8"))["items"]
    jfiles = [(os.path.getmtime(f), f) for f in files if f.endswith(".json")]
    jfiles.sort()
    win = 0
    for r in rows:
        d = led.get(r["内容 ID"])
        if not d or not d.get("ran_from"):
            continue
        t0 = datetime.datetime.fromisoformat(d["ran_from"].replace("Z", "+00:00")).timestamp()
        t1 = t0 + float(d.get("secs") or 0) + 240
        cand = [f for m, f in jfiles if t0 - 60 <= m <= t1]
        if not cand:
            continue
        f = min(cand, key=lambda x: abs(os.path.getmtime(x) - t1))
        if f not in matched:
            matched[f] = r["内容 ID"]
            win += 1

    # ── 补同 run 的兄弟文件（`<run>.md` / `<run>.review.md`）──────────────────
    sib = 0
    for f in list(matched):
        base = os.path.basename(f)
        m = re.match(r"^(\d{8}-\d{6})\.json$", base)
        if not m:
            continue
        for ext in (".md", ".review.md"):
            g = os.path.join(REPORTS, m.group(1) + ext)
            if os.path.exists(g) and g not in matched:
                matched[g] = matched[f]
                sib += 1

    print(f"报告目录共 {len(files)} 个文件 ｜ **命中这 80 条的：{len(matched)}**"
          f"（特征串 {len(matched)-win-sib} ＋ 账本时间窗 {win} ＋ 同 run 兄弟 {sib}）")
    print()
    import collections
    bysuffix = collections.Counter(os.path.basename(f).split(".", 1)[1] for f in matched)
    for k, v in bysuffix.most_common():
        print(f"   .{k:<22} {v}")
    print()
    bycid = collections.Counter(matched.values())
    print(f"   覆盖到 {len(bycid)} / 80 个内容 ID")
    print()
    for f in sorted(matched):
        print(f"   {os.path.basename(f)}")

    if not a.apply:
        print("\n（预演。加 --apply 才移出。）")
        return

    import datetime
    KEEP = ("daily-health", "baseline-", "参数锁", "health.md")
    matched = {f: c for f, c in matched.items()
               if not any(k in os.path.basename(f) for k in KEEP)
               and not f.endswith((".sha256", ".csv", ".tsv"))}
    print(f"排除非评审产物（daily-health / baseline / sha256 / csv）后：{len(matched)}")
    dest = os.path.join(HERE, f"清出的80条报告_{datetime.datetime.now():%Y%m%d-%H%M%S}")
    os.makedirs(dest)
    n = 0
    for f in matched:
        shutil.copy2(f, os.path.join(dest, os.path.basename(f)))
        os.remove(f)
        n += 1
    print(f"\n已移出 {n} 个文件 -> {os.path.relpath(dest, ROOT)}")
    print(f"`kb/l7/reports/` 剩余：{len(os.listdir(REPORTS))} 个文件")


if __name__ == "__main__":
    sys.exit(main())
