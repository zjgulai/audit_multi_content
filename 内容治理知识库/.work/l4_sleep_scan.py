#!/usr/bin/env python3
"""只读：在 L4 canonical 四形态里找与婴幼儿睡眠安全相关的条款，输出条款号与正文。"""
import json, re, os, sys

# 本脚本放在 kb/.work/ 下运行（kb/kbpy .work/l4_sleep_scan.py），故上级即 kb/
BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "l4", "canonical")
PAT = re.compile(
    r"睡眠|睡姿|仰卧|仰睡|俯卧|趴睡|侧睡|窒息|猝死|SIDS|SUID|safe\s*sleep|bed\s*shar|"
    r"co-?sleep|婴儿床|婴儿睡|床围|防撞|枕头|sleep\s*sack|swaddle|襁褓|sleep\s*surface|"
    r"夜间看护|同床|分床|monitor.*sleep|sleep.*monitor",
    re.I,
)
FILES = ["wording_entry.jsonl", "wording_revision_pair.jsonl", "sample_case.jsonl", "scoped_clause.jsonl"]


def main():
    for f in FILES:
        p = os.path.join(BASE, f)
        if not os.path.exists(p):
            print(f"## {f}: MISSING")
            continue
        rows = []
        for line in open(p, encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            try:
                o = json.loads(line)
            except Exception:
                continue
            if PAT.search(json.dumps(o, ensure_ascii=False)):
                rows.append(o)
        print(f"## {f}: matched {len(rows)}")
        for o in rows:
            print(json.dumps({
                "article_no": o.get("article_no"),
                "form": o.get("form"),
                "status": o.get("status"),
                "kb_type": o.get("kb_type"),
                "anchor": o.get("anchor"),
                "unit_id": o.get("unit_id"),
                "source_sha256": o.get("source_sha256"),
                "clause_text": (o.get("clause_text") or o.get("text") or "")[:400],
            }, ensure_ascii=False))


if __name__ == "__main__":
    main()
