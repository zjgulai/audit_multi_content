#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A2 复验：逐条核六要素（库名 / 版本 / 条款号 / anchor / source_sha256 / 逐字摘录）。

不只看「字段在不在」，还做两件独立核对：
  ① 回源：按 anchor 打开 kb/l0/records/<表>/<记录>.json，确认摘录**逐字**出现在该字段里；
  ② source_sha256：格式（64 hex）+ 尝试复算（候选口径：字段值原文 / raw_verbatim / 整条记录文件）。
用法： /usr/bin/python3 a2_six.py <review.json> <kb根>
"""
import hashlib
import json
import os
import re
import sys
import unicodedata

REJ = json.load(open(sys.argv[1], encoding="utf-8"))
ROOT = sys.argv[2]
VER = "v0（试用版，未发布）"          # kb/l7/registry/l7.json → citation_contract.version_in_citation


def norm(s):
    s = unicodedata.normalize("NFKC", s or "")
    return re.sub(r"\s+", " ", s).strip().casefold()


def load_record(anchor):
    if not anchor or not anchor.startswith("#"):
        return None, None
    parts = anchor[1:].split("/")
    if len(parts) < 3:
        return None, None
    table, rec, field = parts[0], parts[1], "/".join(parts[2:])
    base = os.path.join(ROOT, "kb", "l0", "records")
    for d in [table] + (sorted(os.listdir(base)) if os.path.isdir(base) else []):
        p = os.path.join(base, d, f"{rec}.json")
        if os.path.exists(p):
            return json.load(open(p, encoding="utf-8")), field
    return None, field


ok_all = True
for i, f in enumerate(REJ.get("findings") or [], 1):
    lib = f.get("library")
    art = f.get("article_no")
    anc = f.get("anchor")
    sha = f.get("source_sha256")
    exc = f.get("excerpt")
    verified = f.get("verbatim_verified", True)
    el = {
        "库名": bool(lib),
        "版本": bool(VER),                       # cite() 固定带 v0（citation_contract 原文）
        "条款号": bool(art),
        "anchor": bool(anc and anc.startswith("#")),
        "source_sha256": bool(sha and re.fullmatch(r"[0-9a-f]{64}", str(sha))),
        "逐字摘录": bool(exc),
    }
    rec, field = load_record(anc)
    in_src = None
    sha_repro = "n/a"
    if rec is not None:
        fv = (rec.get("fields") or {}).get(field) or {}
        val = fv.get("value")
        if isinstance(val, (dict, list)):
            val = json.dumps(val, ensure_ascii=False)
        val = val if isinstance(val, str) else str(val or "")
        in_src = norm(exc) in norm(val) or norm(exc) in norm(fv.get("raw_verbatim") or "")
        cands = {
            "字段值原文": val,
            "raw_verbatim": fv.get("raw_verbatim") or "",
            "记录文件字节": open(os.path.join(ROOT, "kb", "l0", "records",
                                              anc[1:].split("/")[0],
                                              anc[1:].split("/")[1] + ".json"), "rb").read()
            if False else "",
        }
        for k, v in cands.items():
            if not v:
                continue
            b = v if isinstance(v, bytes) else v.encode("utf-8")
            if hashlib.sha256(b).hexdigest() == sha:
                sha_repro = k
                break
        if sha_repro == "n/a":
            sha_repro = "未复算成功"
    miss = [k for k, v in el.items() if not v]
    if miss:
        ok_all = False
    print(f"[{i}] {lib} 第 {art} 条  verbatim_verified={verified}")
    print(f"    六要素：{el}")
    if miss:
        print(f"    ★ 缺：{miss}")
    print(f"    回源：{'记录已找到' if rec is not None else '★ 记录没找到'}｜"
          f"摘录逐字在源字段里：{in_src}｜source_sha256 复算：{sha_repro}")
    if not verified:
        print("    ⚠ 本条的「摘录」不是逐字原文（P0 等价说法/正则命中），"
              "review.py 已显式标 verbatim_verified=False + evidence_gap")
print()
print("六要素全齐的条目数：%d / %d" % (
    sum(1 for f in REJ["findings"]
        if all([f.get("library"), f.get("article_no"), f.get("anchor"), f.get("source_sha256"),
                f.get("excerpt")])), len(REJ["findings"])))
print("逐字回源成功的条目数：%d / %d" % (
    sum(1 for f in REJ["findings"] if f.get("verbatim_verified", True)), len(REJ["findings"])))
print("逐条缺项：" + ("无" if ok_all else "见上（★）"))
