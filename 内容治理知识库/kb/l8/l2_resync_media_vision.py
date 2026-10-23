#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""l2_resync_media_vision.py —— 把 L1 的**画面读数**同步进 L2 的媒体单元（只做缺失的部分）。

背景（Owner 2026-10-20 第 5 轮要求：「L2 必须 L1 内容同步」）
────────────────────────────────────────────────────────────
实测缺口：L1 媒体文档里已有 `image_visual` 段（339 条画面读数），
而 L2 的 130 个媒体单元是**加画面之前**切的，**0 个**含画面读数。
⇒ 链路上 L2 与 L1 不一致：规则虽然直接读 L1 拿到了画面，但「L0→L1→L2→L3」这条链在 L2 断了。

做法（照 L2 既有语义，不发明新形态）
────────────────────────────────────
  · 每个媒体资源**重切一个 sample 单元**，文本 = `[image_ocr] …` + `[image_visual] …`（与 `l2_split_run.py` 的拼法一致）；
  · 超 `MAX_UNIT_CHARS(8000)` 时**按段回退**（同 l2_split 的既有兜底），每段用自己的 anchor；
  · 旧单元**不删**，写 `kb/l2/retired_units.jsonl` 退役（与 `l2_align_current.py` 同一套账）；
  · 新单元 `source_sha256` = sha256(单元文本) —— 有 sha 才能被 L3 的 evidence 回指；
  · 幂等：新单元 id 已存在 ⇒ 跳过（重跑不重复追加）。
"""
import hashlib
import json
import os
import sys
import time

APPLY = "--apply" in sys.argv
if APPLY:
    sys.argv.remove("--apply")
RUN = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else time.strftime("%Y%m%d-%H%M")

L1_DIR = "kb/l1/2_内部正负样本库"
L2 = "kb/l2"
TABLE_ID = "tbld8qE92YaY38Yz"
PREFIX = "media_%s_" % TABLE_ID
SPLIT = "l2-0.3"
MAX_UNIT_CHARS = 8000


def uid(*p):
    return hashlib.sha1("|".join(str(x) for x in p).encode()).hexdigest()[:20]


def sha256(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def build_units(doc):
    """媒体文档 → 新单元列表（(unit_type, text, anchor)）。与 l2_split 的拼法一致。"""
    segs = [s for s in (doc.get("segments") or []) if (s.get("text") or "").strip()]
    if not segs:
        return []
    parts = ["[%s] %s" % (s.get("kind"), s["text"]) for s in segs]
    txt = "\n".join(parts)
    rid = doc["resource_id"]
    if len(txt) <= MAX_UNIT_CHARS:
        return [("sample", txt, segs[0].get("anchor") or "#素材/%s" % rid)]
    out = []
    for s, one in zip(segs, parts):
        if len(one) > MAX_UNIT_CHARS:          # 单段超限：按行切（同 l2_split 的兜底）
            buf, n = "", 0
            for line in one.splitlines(True):
                if len(buf) + len(line) > MAX_UNIT_CHARS:
                    n += 1
                    out.append(("sample", buf, "%s/p%d" % (s.get("anchor") or "#素材", n)))
                    buf = line
                else:
                    buf += line
            if buf:
                n += 1
                out.append(("sample", buf, "%s/p%d" % (s.get("anchor") or "#素材", n)))
        else:
            out.append(("sample", one, s.get("anchor") or "#素材/%s" % rid))
    return out


def main():
    docs = []
    for fn in sorted(os.listdir(L1_DIR)):
        if fn.startswith(PREFIX) and fn.endswith(".json"):
            docs.append(json.load(open(os.path.join(L1_DIR, fn), encoding="utf-8")))
    units = [json.loads(l) for l in open(os.path.join(L2, "units.jsonl"), encoding="utf-8") if l.strip()]
    retired_path = os.path.join(L2, "retired_units.jsonl")
    retired = set()
    if os.path.exists(retired_path):
        retired = {json.loads(l)["unit_id"] for l in open(retired_path, encoding="utf-8") if l.strip()}

    by_res = {}
    for u in units:
        by_res.setdefault(u["resource_id"], []).append(u)
    existing_ids = {u["unit_id"] for u in units}

    new_units, new_retire, stats = [], [], {"docs": 0, "already": 0, "units": 0, "retired": 0}
    for doc in docs:
        rid = doc["resource_id"]
        built = build_units(doc)
        if not built:
            continue
        stats["docs"] += 1
        want_ids = set()
        for ut, text, anchor in built:
            nsha = sha256(text)
            nid = uid(SPLIT, rid, nsha, ut, anchor, "", 1)
            want_ids.add(nid)
            if nid in existing_ids:
                continue
            new_units.append({
                "unit_id": nid, "resource_id": rid, "kb_type": doc.get("kb_type") or "internal_sample",
                "source_sha256": nsha, "text": text, "char_count": len(text), "anchor": anchor,
                "unit_type": ut, "heading_path": doc.get("source", {}).get("table_name") or "负面样本",
                "order_in_parent": 1, "parent_unit_id": None, "pair_ref": None,
                "meta": {"kind": "paragraph", "field_name": "图片素材"},
                "splitter_version": SPLIT, "splitter_version_backfilled_at": None,
                "rule_eligible": True, "rule_eligible_run": RUN,
                "rule_eligible_source": "media_vision_resync",
                "source_fields": ["图片素材"], "excluded_fields": [],
            })
        # 旧单元退役（同一资源、不在新集合里、且没退役过）
        for u in by_res.get(rid, []):
            if u["unit_id"] not in want_ids and u["unit_id"] not in retired:
                new_retire.append({
                    "unit_id": u["unit_id"], "resource_id": rid, "kb_type": u.get("kb_type"),
                    "char_count": u.get("char_count"), "reason": "媒体单元重切：并入画面读数（L1 image_visual）",
                    "retired_at": RUN, "retired_by": "l2_resync_media_vision",
                    "sha_current": u.get("source_sha256"),
                })
                retired.add(u["unit_id"])
        if want_ids and want_ids <= existing_ids:
            stats["already"] += 1
    stats["units"] = len(new_units)
    stats["retired"] = len(new_retire)

    print("媒体文档 %d ｜ 待新增单元 %d ｜ 待退役旧单元 %d ｜ 已同步跳过 %d"
          % (stats["docs"], stats["units"], stats["retired"], stats["already"]))
    for u in new_units[:3]:
        print("   + %s ｜ %d 字 ｜ %s" % (u["resource_id"], u["char_count"], u["anchor"]))
    if not APPLY:
        print("[dry-run] 未落盘（加 --apply）")
        return 0
    if new_retire:
        with open(retired_path, "a", encoding="utf-8") as fh:
            for r in new_retire:
                fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
    if new_units:
        with open(os.path.join(L2, "units.jsonl"), "a", encoding="utf-8") as fh:
            for u in new_units:
                fh.write(json.dumps(u, ensure_ascii=False, sort_keys=True) + "\n")
        with open(os.path.join(L2, "index", "l2.jsonl"), "a", encoding="utf-8") as fh:
            for u in new_units:
                fh.write(json.dumps({"anchor": u["anchor"], "char_count": u["char_count"],
                                     "kb_type": u["kb_type"], "source_sha256": u["source_sha256"],
                                     "unit_id": u["unit_id"]}, ensure_ascii=False, sort_keys=True) + "\n")
        byres = {}
        for u in new_units:
            byres[u["resource_id"]] = byres.get(u["resource_id"], 0) + 1
        with open(os.path.join(L2, "manifest_l2.jsonl"), "a", encoding="utf-8") as fh:
            for rid, n in byres.items():
                fh.write(json.dumps({"kb_type": "internal_sample", "observed_at": RUN,
                                     "resource_id": rid, "result": "split",
                                     "source_sha256": next(u["source_sha256"] for u in new_units
                                                           if u["resource_id"] == rid),
                                     "splitter_version": SPLIT, "unit_count": n,
                                     "reason": "媒体单元重切：并入画面读数"},
                                    ensure_ascii=False, sort_keys=True) + "\n")
    json.dump({"run": RUN, "at": time.strftime("%Y-%m-%d %H:%M:%S"), "stats": stats,
               "policy": "L2 媒体单元重切：并入 L1 image_visual；旧单元退役不删"},
              open(os.path.join(L2, "runs", "%s-resync-vision.json" % RUN), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("已落盘：units +%d / retired +%d / manifest +%d 资源"
          % (len(new_units), len(new_retire), len({u['resource_id'] for u in new_units})))
    return 0


if __name__ == "__main__":
    sys.exit(main())
