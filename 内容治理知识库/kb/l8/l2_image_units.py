#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""l2_image_units.py —— L2 **图片级单元**（2026-10-20；串图修复 ①）

## 为什么（实测病灶）

L2 的一条负面样本记录，`图片素材` 字段只产**一个字段级单元**，锚点是
`#素材/<rec>/图片素材/#img.1` —— 这个 `#img.1` 指的其实是**整个字段**（4 张图拼在一起），
所以「证据落在第几张图」在 L2/L6 里**没有坐标**：

  · 报告只能说「依据这条记录」，说不到「依据这张图」；
  · 归属判据（②）只能回 L1 媒体台账去取 sha/token；
  · 召回里同一段 OCR 被拼在一格里，逐图比对做不了。

## 本件做什么（只加坐标，不改判据）

对每条**现存**记录，把 L1 媒体台账里 `kind=image_ocr` 的**每个图段**提升为一个 L2 单元：

    anchor      = `#素材/<rec>/图片素材/#img.<seq>`   ← 图片级坐标（与 L1 段一致）
    unit_type   = image
    image_sha256 / file_token / seq / role(来自 image_roles)
    resource_id = **与字段级单元同一个**（`media_<tbl>_<rec>`）
                  ⇒ 下游「同源归并」（覆盖判据按 resource_id）一个字不用改

并把**字段级**单元的锚点从 `#素材/<rec>/图片素材/#img.1`（历史误用）改为
`#素材/<rec>/图片素材`，旧锚点留在 `legacy_anchors` 里（不丢引用）。

★ 边界：**不新增/不删除任何记录的判读**，也不改分数字段；只是把已经存在的 L1 图段
摆到 L2 的正确坐标上。幂等：重复跑不会产生第二份。

## 用法

    python3 kb/l8/l2_image_units.py            # 预演
    python3 kb/l8/l2_image_units.py --apply    # 落盘（重写 units.jsonl）
    python3 kb/l8/l2_image_units.py --selftest
"""
import glob
import hashlib
import json
import os
import sys
import tempfile

KB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
L1_MEDIA = os.path.join(KB, "l1", "2_内部正负样本库")
UNITS = os.path.join(KB, "l2", "units.jsonl")
ROLES = os.path.join(KB, "l3", "registry", "image_roles.json")
TABLE = "tbld8qE92YaY38Yz"


def _uid(*parts):
    return hashlib.sha1(("|".join(parts)).encode("utf-8")).hexdigest()[:20]


def load_image_segments():
    """rec -> [ {anchor, sha256, text, seq} ]，只取 image_ocr 且有字的段。"""
    out = {}
    for p in sorted(glob.glob(os.path.join(L1_MEDIA, "media_%s_*.json" % TABLE))):
        try:
            d = json.load(open(p, encoding="utf-8"))
        except Exception:                                  # noqa: BLE001
            continue
        rid = (d.get("source") or {}).get("record_id") or os.path.basename(p)[len("media_%s_" % TABLE):-5]
        rows = []
        for s in (d.get("segments") or []):
            if s.get("kind") != "image_ocr":
                continue
            a = s.get("anchor") or ""
            if "#img." not in a:
                continue
            try:
                seq = int(a.rsplit("#img.", 1)[1])
            except Exception:                              # noqa: BLE001
                seq = None
            rows.append({"anchor": a, "sha256": (s.get("source_sha256") or "").lower(),
                         "text": s.get("text") or "", "seq": seq})
        if rows:
            out[rid] = rows
    return out


def _roles():
    if not os.path.exists(ROLES):
        return {}
    d = json.load(open(ROLES, encoding="utf-8"))
    idx = {}
    for rid, p in (d.get("records") or {}).items():
        for im in (p.get("images") or []):
            if im.get("sha256"):
                idx[(rid, im["sha256"])] = im.get("role")
    return idx


def build(units, segs, roles):
    """返回 (new_units, stats)。幂等：已存在的图片级单元不重复生成。"""
    have = {(u.get("unit_type"), u.get("anchor")) for u in units}
    out, added, retagged = [], 0, 0
    for u in units:
        a = u.get("anchor") or ""
        rid = None
        if a.endswith("/图片素材/#img.1"):
            rid = a.split("/")[1] if a.startswith("#素材/") else None
        if rid and rid in segs and (u.get("unit_type") != "image") and ("image", a) not in have:
            n = dict(u)
            n["legacy_anchors"] = sorted(set((u.get("legacy_anchors") or []) + [a]))
            n["anchor"] = a.rsplit("/#img.1", 1)[0]
            n["unit_type"] = u.get("unit_type") or "media_field"
            retagged += 1
            out.append(n)
            continue
        out.append(u)
    for rid, rows in segs.items():
        base = [u for u in units if (u.get("resource_id") or "").startswith("media_%s_%s" % (TABLE, rid))]
        if not base:
            continue
        proto = base[0]
        for s in rows:
            if ("image", s["anchor"]) in have:
                continue
            text = (s.get("text") or "").strip()
            if not text:
                continue
            out.append({
                "unit_id": _uid(proto.get("resource_id") or rid, s["anchor"]),
                "resource_id": proto.get("resource_id"),
                "kb_type": proto.get("kb_type"),
                "anchor": s["anchor"], "unit_type": "image",
                "text": "[image_ocr] " + text,
                "heading_path": proto.get("heading_path"),
                "source_sha256": s.get("sha256") or proto.get("source_sha256"),
                "image_sha256": s.get("sha256"),
                "file_token": s["anchor"].rsplit("/", 1)[-1],
                "seq": s.get("seq"),
                "role": roles.get((rid, s.get("sha256") or "")),
                "char_count": len(text),
                "splitter_version": proto.get("splitter_version") or "l2-0.3",
                "order_in_parent": s.get("seq"),
            })
            added += 1
    return out, {"units_before": len(units), "units_after": len(out),
                 "image_units_added": added, "field_units_retagged": retagged}


def _write_atomic(path, rows):
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".tmp-l2img-")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    os.replace(tmp, path)


def selftest():
    segs = {"rec_a": [{"anchor": "#素材/rec_a/图片素材/#img.1", "sha256": "s1", "text": "hello", "seq": 1},
                      {"anchor": "#素材/rec_a/图片素材/#img.2", "sha256": "s2", "text": "world", "seq": 2}]}
    units = [{"unit_id": "u1", "resource_id": "media_%s_rec_a" % TABLE, "kb_type": "internal_sample",
              "anchor": "#素材/rec_a/图片素材/#img.1", "text": "hello world", "source_sha256": "x"}]
    out, st = build(units, segs, {("rec_a", "s2"): "shared_reference"})
    by_a = {u["anchor"]: u for u in out}
    cases = [
        ("① 每张图一个单元（#img.1 / #img.2 都在）",
         "#素材/rec_a/图片素材/#img.1" in by_a and "#素材/rec_a/图片素材/#img.2" in by_a, list(by_a)),
        ("② 图片级单元带 sha/token/seq/role",
         all(by_a[a].get("image_sha256") and by_a[a].get("seq") and by_a[a].get("file_token")
             for a in "#素材/rec_a/图片素材/#img.1 #素材/rec_a/图片素材/#img.2".split()),
         None),
        ("③ 字段级单元锚点改到字段（不再占用 #img.1），旧锚点留 legacy",
         "#素材/rec_a/图片素材" in [u["anchor"] for u in out]
         and any(u.get("legacy_anchors") for u in out), [u["anchor"] for u in out]),
        ("④ resource_id 与字段级同一个（下游同源归并不用改）",
         {u.get("resource_id") for u in out} == {"media_%s_rec_a" % TABLE}, None),
        ("⑤ 角色随图带上（shared_reference 落在 #img.2）",
         by_a["#素材/rec_a/图片素材/#img.2"].get("role") == "shared_reference", None),
    ]
    out2, st2 = build(out, segs, {})
    cases.append(("⑥ 幂等：再跑一遍不新增", st2["image_units_added"] == 0 and len(out2) == len(out), st2))
    ok = all(c[1] for c in cases)
    for name, okc, detail in cases:
        print(("  ✅ " if okc else "  ❌ ") + name + ("" if okc else "  ← " + str(detail)[:200]))
    print("l2_image_units --selftest %s（%d/%d）" % ("PASS" if ok else "FAIL",
                                                    sum(1 for c in cases if c[1]), len(cases)))
    return 0 if ok else 3


def main(argv):
    if "--selftest" in argv:
        return selftest()
    units = [json.loads(l) for l in open(UNITS, encoding="utf-8") if l.strip()]
    segs = load_image_segments()
    out, st = build(units, segs, _roles())
    print(json.dumps(st, ensure_ascii=False, indent=1))
    if "--apply" in argv:
        _write_atomic(UNITS, out)
        print("已重写 %s（%d 行，%.1f MB）" % (UNITS, len(out), os.path.getsize(UNITS) / 1e6))
        print("下一步（必须）：重建 L6 —— python3 kb/.work/l6_build.py <run_id> --apply")
    else:
        print("（预演：未落盘；--apply 才写）")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
