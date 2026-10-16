#!/usr/bin/env python3
"""把 80 行映射到它们各自的本地链报告，看**链实际收到的是什么**。

映射键：账本 `ran_from`(UTC) + `secs` ⇒ 本地时间窗 ⇒ 取窗内 mtime 的 `<run>.json`。
匹配质量如实打印（有多个/没有就标出来，不硬凑）。
"""
import datetime, glob, importlib.util, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
LEDGER = "/Users/lute/Project/audit_multi_content/PMO/shouheng-state/batch-review.json"

spec = importlib.util.spec_from_file_location("p", os.path.join(HERE, "parse_table80.py"))
p = importlib.util.module_from_spec(spec); spec.loader.exec_module(p)


def kind(t):
    if t.startswith("【待读的链接】"):
        return "链接占位符"
    if "没识别出文字" in t[:40]:
        return "图无文字"
    if t.startswith("【图片"):
        return "图片OCR"
    if t.startswith("【视频"):
        return "视频真内容"
    return "文案真内容" if len(t) >= 200 else f"其它<200({len(t)})"


def main():
    led = json.load(open(LEDGER, encoding="utf-8"))["items"]
    rows = p.parse(os.path.join(HERE, "out/table80_after.txt"))
    files = []
    for f in glob.glob(os.path.join(ROOT, "kb/l7/reports/2026*.json")):
        try:
            d = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(d, dict):
            continue
        t = (d.get("input_manifest") or {}).get("text") or ""
        files.append((os.path.getmtime(f), f, t))
    files.sort()

    stats = {}
    unmapped = []
    for r in rows:
        cid = r["内容 ID"]
        d = led.get(cid)
        if not d or not d.get("ran_from"):
            unmapped.append((cid, "账本无 ran_from")); continue
        t0 = datetime.datetime.fromisoformat(d["ran_from"].replace("Z", "+00:00")).timestamp()
        t1 = t0 + float(d.get("secs") or 0) + 240
        cand = [(m, f, t) for m, f, t in files if t0 - 60 <= m <= t1]
        if not cand:
            unmapped.append((cid, "时间窗内无报告")); continue
        m, f, t = min(cand, key=lambda x: abs(x[0] - t1))
        k = kind(t)
        stats.setdefault(k, []).append(cid)
    print("80 行 → 链实际收到的输入：")
    tot = 0
    for k, v in sorted(stats.items(), key=lambda x: -len(x[1])):
        print(f"   {k:<22} {len(v):>3}")
        tot += len(v)
    print(f"   {'（未映射）':<22} {len(unmapped):>3}")
    print(f"   ---- 合计 {tot + len(unmapped)}")
    print()
    for cid, why in unmapped[:10]:
        print("   未映射:", cid, "|", why)
    bad = sum(len(v) for k, v in stats.items()
              if k == "链接占位符" or k.startswith("其它<200") or k == "图无文字")
    print()
    print(f"★ 链**没拿到实质正文**的行：{bad}/80 = {bad/80:.0%}")


if __name__ == "__main__":
    sys.exit(main())
