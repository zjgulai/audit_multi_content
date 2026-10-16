#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""门④ 第③段 · 20 项 mismatch 的来源审计（独立复算，只读）。

问题：workflow_check.py 第③段要求 2026-09-23 四份 run 记录里列的 45 个产物
「今天仍与记录里的 sha 相同」。活库每天在长 ⇒ 必然 FAIL。

本脚本只回答一个可证伪的问题：
  那 20 个 mismatch 的**现行 sha**，是否被某条**更新**的 run 记录（artifacts[]/其他字段里的 sha）记过？
  —— 有出处的 = 「已溯源的演进」；查不到出处的 = 「未落章改写」（这才是真发现）。

不采信任何登记文件的自述，只读原始 kb/l*/runs/*.json。
"""
import hashlib
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MISMATCH = [
    "kb/l3/candidates/rules.jsonl", "kb/l4/registry/l4.json", "kb/l5/registry/l5.json",
    "kb/l5/benchmark.json", "kb/l6/runs/build_runs.jsonl", "kb/l6/bm25/docs.jsonl",
    "kb/l6/bm25/meta.json", "kb/l6/bm25/postings_zh.jsonl", "kb/l6/bm25/postings_en.jsonl",
    "kb/l6/vectors/vectors.jsonl", "kb/l6/vectors/matrix.npy", "kb/l6/vectors/meta.json",
    "kb/l6/index/l6.jsonl", "kb/l6/registry/l6.json", "kb/l6/retriever.py",
    "kb/l6/selftest.json", "kb/l6/benchmark.json",
    "kb/l7/skills/kb-content-review/SKILL.md", "kb/l7/registry/l7.json",
    "kb/l7/skills/kb-content-review/scripts/review.py",
]
HEX32 = re.compile(r"\b[0-9a-f]{32}\b")
HEX64 = re.compile(r"\b[0-9a-f]{64}\b")


def sha16(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()[:16]


def main():
    cur = {}
    for rel in MISMATCH:
        p = os.path.join(ROOT, rel)
        cur[rel] = sha16(p) if os.path.exists(p) else None

    # 扫全部 run 记录，收集「哪份 run 记过哪个 sha16」
    hits = {rel: [] for rel in MISMATCH}
    scanned = 0
    for layer in ("l0", "l1", "l2", "l3", "l4", "l5", "l6", "l7"):
        d = os.path.join(ROOT, "kb", layer, "runs")
        if not os.path.isdir(d):
            continue
        for fn in sorted(os.listdir(d)):
            if not fn.endswith(".json"):
                continue
            fp = os.path.join(d, fn)
            scanned += 1
            try:
                txt = open(fp, "r", encoding="utf-8", errors="replace").read()
            except OSError:
                continue
            shas = set(HEX32.findall(txt)) | set(HEX64.findall(txt))
            for rel, s in cur.items():
                if s and any(x.startswith(s) or s.startswith(x[:16]) and len(x) >= 16 for x in shas):
                    hits[rel].append(os.path.relpath(fp, ROOT))

    sourced, unsourced = [], []
    for rel in MISMATCH:
        (sourced if hits[rel] else unsourced).append(rel)

    print("扫 run 记录：%d 份" % scanned)
    print("现行 sha 有 run 记录来源：%d/%d" % (len(sourced), len(MISMATCH)))
    for rel in sourced:
        print("   ✅ %-46s 现sha=%s ｜ %d 条记录记过，最新一条 %s"
              % (rel, cur[rel], len(hits[rel]), hits[rel][-1]))
    print("现行 sha 查不到来源：%d/%d" % (len(unsourced), len(MISMATCH)))
    for rel in unsourced:
        print("   ❌ %-46s 现sha=%s ｜ 0 条记录" % (rel, cur[rel]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
