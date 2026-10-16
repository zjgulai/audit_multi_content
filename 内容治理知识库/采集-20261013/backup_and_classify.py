#!/usr/bin/env python3
"""把目标表现有记录连同 record_id 全量导出（删除前的备份）。

同时按新的三类口径给每行打标：吸奶器 / 清洗机 / 婴儿监控器 / （不属于三类）。
"""
import json, subprocess, os, sys

HERE = os.path.dirname(__file__)
LARK = os.path.expanduser("~/.dsh/bin/lark-cli")
BASE = "RY2UbCRjXaeeWwscUPScVN5AnQc"
TABLE = "tblavfbMDMeRsulo"


def classify(blob):
    b = (blob or "").lower()
    if "baby monitor" in b or "video monitor" in b:
        return "婴儿监控器"
    if any(k in b for k in ["bottle washer", "steriliz", "bottle cleaner",
                            "deepclean", "kleanpal", "cleaning spray"]):
        return "清洗机"
    if any(k in b for k in ["breast pump", "wearable pump", "pumping", "milk collector",
                            "lactation", "milk storage", "breastmilk", "nipple cream",
                            "breast pad", "milk cooler", "breast milk"]):
        return "吸奶器"
    return None


def main():
    p = subprocess.run([LARK, "base", "+record-list", "--base-token", BASE, "--table-id", TABLE,
                        "--page-size", "200", "--profile", "dsh-kb", "--as", "bot",
                        "--format", "json"], capture_output=True, text=True)
    raw = p.stdout.strip()
    i = raw.find("{")
    if i < 0:
        print("CLI 没返回 JSON。原始输出前 500 字:\n", raw[:500]); sys.exit(3)
    d = json.loads(raw[i:])
    if not d.get("ok"):
        print("读失败:", d.get("error")); sys.exit(3)
    pl = d["data"]
    if pl.get("has_more"):
        print("⚠️ 还有更多页（>200 行），本脚本未分页 —— 需先分页再备份"); sys.exit(3)
    cols = pl["fields"]
    rows = [dict(zip(cols, r)) for r in pl["data"]]
    rids = pl.get("record_id_list") or []

    def cell(r, k):
        v = r.get(k)
        if isinstance(v, list):
            return "".join(x.get("text", "") if isinstance(x, dict) else str(x) for x in v)
        if isinstance(v, dict):
            return v.get("text") or v.get("name") or ""
        return v if v is not None else ""

    out = []
    for i, r in enumerate(rows):
        rec = {c: cell(r, c) for c in cols}
        rec["_record_id"] = rids[i] if i < len(rids) else None
        rec["_类别"] = classify(rec.get("采集数据", ""))
        out.append(rec)

    json.dump(out, open(os.path.join(HERE, "out", "backup_table_20261013.json"), "w"),
              ensure_ascii=False, indent=1)

    from collections import Counter
    c = Counter(r["_类别"] or "（不属于三类）" for r in out)
    print("备份完成:", len(out), "行  -> out/backup_table_20261013.json")
    print("分类:", dict(c))
    n_out = sum(1 for r in out if not r["_类别"])
    print(f"保留 {len(out)-n_out} 行 / 待删 {n_out} 行")
    print("待删的 record_id 数:", sum(1 for r in out if not r["_类别"] and r["_record_id"]))


if __name__ == "__main__":
    main()
