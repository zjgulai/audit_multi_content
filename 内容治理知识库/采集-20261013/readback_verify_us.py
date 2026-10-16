#!/usr/bin/env python3
"""写库后读回核验（以服务端为准）：确认新 80 行落对，且旧 80 行确实撤掉、另一批一行未动。"""
import json, subprocess, os, collections, sys

HERE = os.path.dirname(__file__)
LARK = os.path.expanduser("~/.dsh/bin/lark-cli")
BASE = "RY2UbCRjXaeeWwscUPScVN5AnQc"
TABLE = "tblavfbMDMeRsulo"
CATS = {"吸奶器", "清洗机", "婴儿监控器"}


def main():
    p = subprocess.run([LARK, "base", "+record-list", "--base-token", BASE, "--table-id", TABLE,
                        "--page-size", "200", "--profile", "dsh-kb", "--as", "bot",
                        "--format", "json"], capture_output=True, text=True)
    raw = p.stdout.strip()
    d = json.loads(raw[raw.find("{"):])
    pl = d["data"]
    cols = pl["fields"]
    rows = [dict(zip(cols, r)) for r in pl["data"]]

    def cell(r, k):
        v = r.get(k)
        if isinstance(v, list):
            return "".join(x.get("text", "") if isinstance(x, dict) else str(x) for x in v)
        if isinstance(v, dict):
            return v.get("text") or v.get("name") or ""
        return v if v is not None else ""

    recs = [{c: cell(r, c) for c in cols} for r in rows]
    import re
    # 分类判据要**互斥**：另一批的 id 形如 MC-AMZ-吸奶器-T01 / MC-SITE-... / MC-YT-吸奶器-V08，
    # 里面**带中文品类**；我旧版是 MC-YT-<videoId>（无中文）。用中文品类做区分键。
    OTHER_RE = re.compile(r"^MC-(SITE|AMZ|YT)-(吸奶器|清洗机|婴儿监控器)")
    mine_new, other, mine_old = [], [], []
    for r in recs:
        cid = r.get("内容 ID") or ""
        if cid.startswith("MC-US-"):
            mine_new.append(r)
        elif OTHER_RE.match(cid):
            other.append(r)
        else:
            mine_old.append(r)
    print(f"服务端总行数: {len(recs)}")
    print(f"  我的新版(MC-US-*): {len(mine_new)}")
    print(f"  我的旧版(残留?):   {len(mine_old)}")
    print(f"  另一批(未动):      {len(other)}")

    print("\n--- 我的新版构成 ---")
    print("  类型:", dict(collections.Counter(r["内容类型"] for r in mine_new)))
    print("  品类:", dict(collections.Counter(r["产品线"] for r in mine_new)))
    print("  渠道:", dict(collections.Counter(r["渠道"] for r in mine_new)))
    print("  状态:", dict(collections.Counter(str(r["状态"]) for r in mine_new)))

    errs = []
    want = {"文案": 35, "图片": 35, "视频": 10}
    got = collections.Counter(r["内容类型"] for r in mine_new)
    for k, v in want.items():
        if got.get(k, 0) != v:
            errs.append(f"{k} {got.get(k,0)} != {v}")
    bad = {r["产品线"] for r in mine_new} - CATS
    if bad:
        errs.append(f"品类越出三类: {bad}")
    if mine_old:
        errs.append(f"旧行没删干净: {len(mine_old)}")
    # 2026-10-13 第二轮：Owner 明确要求「去掉另外 80」⇒ 期望另一批为 0
    if other:
        errs.append(f"另一批应已清空，实际还剩 {len(other)} 行")
    if len(recs) != 80:
        errs.append(f"总行数应为 80，实际 {len(recs)}")

    print("\n--- 抽样 ---")
    for t in ("文案", "图片", "视频"):
        for r in mine_new:
            if r["内容类型"] == t:
                print(f"[{t}] {r['内容 ID']} | {r['产品线']} | {r['渠道']} | {r['状态']}")
                print("   ", str(r["采集数据"])[:150].replace("\n", " / "))
                break

    print("\n结论:", "全部通过" if not errs else "有问题 —— " + "; ".join(errs))
    sys.exit(0 if not errs else 3)


if __name__ == "__main__":
    main()
