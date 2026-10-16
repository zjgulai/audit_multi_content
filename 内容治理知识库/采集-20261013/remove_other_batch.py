#!/usr/bin/env python3
"""撤掉「另一批」的 80 行，只留我的新版（MC-US-*）。

顺序（先备份再删，不静默）：
  1. 现读表，按 内容 ID 判据分出「我的新版 / 另一批」
  2. 把另一批**逐行全文**导出到 out/backup_other_batch.json（可恢复）
  3. 打印将删的 record_id 数量，交给调用方决定是否真删
判据互斥：我的新版以 MC-US- 开头；另一批形如 MC-(SITE|AMZ|YT)-(中文品类)。
"""
import json, subprocess, os, re, sys, collections

HERE = os.path.dirname(__file__)
OUT = os.path.join(HERE, "out")
LARK = os.path.expanduser("~/.dsh/bin/lark-cli")
BASE = "RY2UbCRjXaeeWwscUPScVN5AnQc"
TABLE = "tblavfbMDMeRsulo"
OTHER_RE = re.compile(r"^MC-(SITE|AMZ|YT)-(吸奶器|清洗机|婴儿监控器)")


def main():
    p = subprocess.run([LARK, "base", "+record-list", "--base-token", BASE, "--table-id", TABLE,
                        "--page-size", "200", "--profile", "dsh-kb", "--as", "bot",
                        "--format", "json"], capture_output=True, text=True)
    raw = p.stdout.strip()
    d = json.loads(raw[raw.find("{"):])
    if not d.get("ok"):
        print("读失败:", d.get("error")); sys.exit(3)
    pl = d["data"]
    cols = pl["fields"]
    rids = pl.get("record_id_list") or []
    recs = []
    for i, row in enumerate(pl["data"]):
        rec = dict(zip(cols, row))
        rec["_record_id"] = rids[i] if i < len(rids) else None
        recs.append(rec)

    def cid(r):
        v = r.get("内容 ID")
        if isinstance(v, list):
            return "".join(x.get("text", "") if isinstance(x, dict) else str(x) for x in v)
        return v or ""

    mine = [r for r in recs if cid(r).startswith("MC-US-")]
    other = [r for r in recs if OTHER_RE.match(cid(r))]
    rest = [r for r in recs if r not in mine and r not in other]

    print(f"现读总行数: {len(recs)}")
    print(f"  我的新版 MC-US-*: {len(mine)}")
    print(f"  另一批(待删):     {len(other)}")
    print(f"  其它(不明归属):   {len(rest)}")
    if rest:
        print("  !! 有归属不明的行，先别删：")
        for r in rest[:10]:
            print("     ", cid(r))

    # 备份另一批全文
    json.dump(other, open(os.path.join(OUT, "backup_other_batch.json"), "w"),
              ensure_ascii=False, indent=1)
    ids = [r["_record_id"] for r in other if r.get("_record_id")]
    json.dump(ids, open(os.path.join(OUT, "delete_ids_other.json"), "w"), indent=1)
    print(f"\n已备份另一批全文 -> out/backup_other_batch.json（{len(other)} 行）")
    print(f"待删 record_id: {len(ids)} 个")
    print("  另一批品类:", dict(collections.Counter(
        next((k for k in ["吸奶器", "清洗机", "婴儿监控器"] if k in cid(r)), "?") for r in other)))


if __name__ == "__main__":
    main()
