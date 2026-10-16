#!/usr/bin/env python3
"""算出「报告里引用的 L0 record_id 中，哪些已经点不开」= 回填清单。

判据：把每个被引用的 id 拿去它所属源表的**当前**记录集合里查；
不在 ⇒ 该直链已死。带单词边界，避免把 reclassification 这类英文词当成 id。
"""
import json, re, os, glob, subprocess, collections

HERE = os.path.dirname(__file__)
ROOT = os.path.abspath(os.path.join(HERE, ".."))
OUT = os.path.join(HERE, "out")
LARK = os.path.expanduser("~/.dsh/bin/lark-cli")

BASE_OF = {
    "tblMGtPfe8ZUsEdP": "GnRZbIuXraCzf0sGr2UcmZ62nfc",
    "tbld8qE92YaY38Yz": "GnRZbIuXraCzf0sGr2UcmZ62nfc",
    "tblZP8jG4tiUL98C": "GnRZbIuXraCzf0sGr2UcmZ62nfc",
    "tblcbk4XiW6471YN": "Lk3Qb8y2QaVyZns6gprcVNE9nA0",
    "tblD1MiUK1v5fdjD": "Lk3Qb8y2QaVyZns6gprcVNE9nA0",
    "tblqUTAKFkWheU49": "Lk3Qb8y2QaVyZns6gprcVNE9nA0",
    "tblLxUfPz4Wqp2na": "Lk3Qb8y2QaVyZns6gprcVNE9nA0",
    "tblGFyycMc45RMga": "N2qkb2YxuatqGLsa4U4cFQxgnCe",
    "tbl8AI00JZO1iZtp": "SKkkbdZi9aRuMzs7ob0cpSYHnQg",
    "tblVdl0jdK9G4ld3": "SKkkbdZi9aRuMzs7ob0cpSYHnQg",
}
NAME = {"tblMGtPfe8ZUsEdP": "材料收集", "tbld8qE92YaY38Yz": "负面样本",
        "tblZP8jG4tiUL98C": "知识库分类说明", "tblcbk4XiW6471YN": "广告文案明细",
        "tblD1MiUK1v5fdjD": "品线内容边界规则库", "tblqUTAKFkWheU49": "W1卖点表达边界",
        "tblLxUfPz4Wqp2na": "风险文案改写建议库", "tblGFyycMc45RMga": "外部资料库·数据表",
        "tbl8AI00JZO1iZtp": "专家修订汇总表", "tblVdl0jdK9G4ld3": "内容公式"}

# 14 位、前后不接字母数字 ⇒ 不会误吞 reclassification
ID_RE = re.compile(r"(?<![A-Za-z0-9])rec[A-Za-z0-9]{11}(?![A-Za-z0-9])")
SCAN_DIRS = ["kb/l7/reports", "."]


def current_ids(base, table):
    p = os.path.join(OUT, "l0probe", f"{table}.ndjson")
    if os.path.exists(p):
        ids = []
        for line in open(p, encoding="utf-8"):
            line = line.strip()
            if line:
                try:
                    ids.append(json.loads(line)["record_id"])
                except Exception:
                    pass
        if ids:
            return set(ids)
    outp = os.path.join(OUT, "l0probe", f"{table}.ndjson")
    subprocess.run([LARK, "base", "+record-list", "--base-token", base, "--table-id", table,
                    "--limit", "2000", "--format", "ndjson", "--output", outp,
                    "--profile", "dsh-kb", "--as", "bot"], capture_output=True, text=True)
    ids = []
    if os.path.exists(outp):
        for line in open(outp, encoding="utf-8"):
            line = line.strip()
            if line:
                try:
                    ids.append(json.loads(line)["record_id"])
                except Exception:
                    pass
    return set(ids)


def main():
    # 每个 id 的归属表（从本地 L0 件反查）
    owner = {}
    for f in glob.glob(os.path.join(ROOT, "kb/l0/*/feishu_bitable_record__*.json")):
        try:
            d = json.load(open(f))
        except Exception:
            continue
        s = d.get("source", {}) or {}
        if s.get("record_id"):
            owner.setdefault(s["record_id"], s.get("table_id"))

    # 扫报告，统计每个 id 出现在哪些文件
    hits = collections.defaultdict(set)
    for base in SCAN_DIRS:
        for dirpath, dirnames, filenames in os.walk(os.path.join(ROOT, base)):
            dirnames[:] = [d for d in dirnames if d not in
                           ("node_modules", ".git", "_archive", "raw", "l0probe")]
            if base == "." and dirpath != ROOT:
                continue                      # 只扫工作区根目录本层
            for fn in filenames:
                if not fn.endswith((".md", ".json", ".ndjson")):
                    continue
                p = os.path.join(dirpath, fn)
                try:
                    txt = open(p, encoding="utf-8", errors="ignore").read()
                except Exception:
                    continue
                for m in ID_RE.findall(txt):
                    hits[m].add(os.path.relpath(p, ROOT))

    print(f"报告里共引用 {len(hits)} 个不同 record_id")
    by_table = collections.defaultdict(set)
    for rid in hits:
        by_table[owner.get(rid)].add(rid)

    print(f"\n{'源表':<20}{'被引用 id':>9}{'已失效':>8}   涉及文件")
    print("-" * 72)
    dead_all = {}
    for t, ids in sorted(by_table.items(), key=lambda x: -len(x[1])):
        label = NAME.get(t) or ("（本地无 L0 件，归属不明）" if t is None else t)
        if not t or t not in BASE_OF:
            print(f"{label:<20}{len(ids):>9}{'—':>8}   {len(set().union(*[hits[i] for i in ids]))}")
            continue
        cur = current_ids(BASE_OF[t], t)
        dead = {i for i in ids if i not in cur}
        files = set().union(*[hits[i] for i in dead]) if dead else set()
        flag = "" if not dead else "  <<< 需回填"
        print(f"{label:<20}{len(ids):>9}{len(dead):>8}   {len(files)}{flag}")
        if dead:
            dead_all[t] = dead
    total_dead = sum(len(v) for v in dead_all.values())
    allfiles = set()
    for t, ids in dead_all.items():
        for i in ids:
            allfiles |= hits[i]
    json.dump({"dead": {k: sorted(v) for k, v in dead_all.items()},
               "files": sorted(allfiles), "hits": {k: sorted(v) for k, v in hits.items()}},
              open(os.path.join(OUT, "dead_l0_links.json"), "w"), ensure_ascii=False, indent=1)
    print("-" * 72)
    print(f"合计失效 {total_dead} 个 id，散落在 {len(allfiles)} 份文件里")
    print("清单已落 -> out/dead_l0_links.json")


if __name__ == "__main__":
    main()
