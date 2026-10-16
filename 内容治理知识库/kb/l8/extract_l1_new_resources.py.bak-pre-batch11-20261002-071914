#!/usr/bin/env python3
"""L1 对齐 L0：把新登记的 L0 资源抽进 L1，并把 L0 已 gone 的旧资源在 L1 里标失效。

为什么需要：L0 台账 20260929-1200 补齐后（+718 行），L0 活跃集 ⊖ L1 不再是 0；
本脚本按 L0 台账驱动 L1：
  1) L0 活跃 & L1 无行 → 抽取
     · feishu_bitable_record（负面样本 108 条）→ 逐字段 segment 产物 + manifest 行 + index 行
     · feishu_attachment（283 张图）→ 只登记 pending_ocr 行（字节未取：bot 403，见 runs/20260929-1155）
  2) L1 有行 & L0 已 gone/retracted → 追加 invalidated 行（不改旧行）
只追加、不删除；产物写盘带读回断言（首字节必须是 '{'）。
用法：python3 kb/l8/extract_l1_new_resources.py 20260929-1230 [--apply]
"""
# ── 解释器守卫（2026-09-29）：不合格就用 kb/.kb-python 指定的解释器重跑自己 ──
import os as _os, sys as _sys
if not _os.environ.get("KB_INTERP_OK"):
    _d = _os.path.dirname(_os.path.abspath(__file__)); _cfg = None
    while True:
        _p = _os.path.join(_d, ".kb-python")
        if _os.path.isfile(_p):
            _cfg = _p
            break
        _q = _os.path.dirname(_d)
        if _q == _d:
            break
        _d = _q
    if _cfg:
        _want = next((l.split("#", 1)[0].strip() for l in open(_cfg, encoding="utf-8")
                      if l.split("#", 1)[0].strip()), "")
        _want = _os.path.expanduser(_want)
        if (_want and _os.access(_want, _os.X_OK)
                and _os.path.realpath(_want) != _os.path.realpath(_sys.executable)):
            _os.environ["KB_INTERP_OK"] = "1"
            _os.execve(_want, [_want, _os.path.abspath(__file__)] + _sys.argv[1:], dict(_os.environ))
# ──────────────────────────────────────────────────────────────────────────

import collections
import hashlib
import json
import os
import sys

RUN = sys.argv[1] if len(sys.argv) > 1 else "20260929-1230"
APPLY = "--apply" in sys.argv
L0, L1 = "kb/l0", "kb/l1"
EXT = "l1-0.1"
REG = json.load(open(f"{L0}/registry/kb.json", encoding="utf-8"))
REV = REG["dir_map_reverse"]
TABLE_LABEL = {"tbld8qE92YaY38Yz": "负面样本"}


def canon(o):
    return json.dumps(o, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha(t):
    return hashlib.sha256(t.encode("utf-8")).hexdigest()


def rid_of(key):
    s = key.replace(":", "__").replace("/", "_")
    return s


def text_of(v):
    if isinstance(v, list):
        return "、".join(str(x) if not isinstance(x, dict) else json.dumps(x, ensure_ascii=False) for x in v)
    return "" if v is None else str(v)


# ---------- L0 最新状态 ----------
l0_latest = {}
for line in open(f"{L0}/manifest.jsonl", encoding="utf-8"):
    if line.strip():
        r = json.loads(line)
        l0_latest[r["resource_key"]] = r
l0_active = {k: v for k, v in l0_latest.items()
             if v["status"] not in ("gone", "retracted") and not k.startswith("audit:")}
l0_gone = {k for k, v in l0_latest.items() if v["status"] in ("gone", "retracted")}

# ---------- L1 最新状态 ----------
rows = [json.loads(l) for l in open(f"{L1}/manifest_l1.jsonl", encoding="utf-8") if l.strip()]
l1_latest = {}
for r in rows:
    l1_latest[r["resource_key"]] = r
MAN_KEYS = set(rows[0].keys())

# 产物键基准（用既有产物对齐）
base_art = f"{L1}/2_内部正负样本库/bitable__SKkkbdZi9aRuMzs7ob0cpSYHnQg__recvoyJ6L99PoN.json"
ART_KEYS = set(json.load(open(base_art, encoding="utf-8")).keys())

to_extract = sorted(k for k in l0_active if k not in l1_latest)
to_invalidate = sorted(k for k in l1_latest if k in l0_gone and l1_latest[k]["status"] not in ("invalidated", "retracted"))
# media 容器（resource_key = media:<tid>:<rid>）的 L0 亲本没了 → 一并失效
for k, r in l1_latest.items():
    if k.startswith("media:") and k not in to_invalidate:
        tid, rid = k.split(":")[1], k.split(":")[2]
        if f"bitable:{tid}:{rid}" in l0_gone and r["status"] not in ("invalidated", "retracted"):
            to_invalidate.append(k)
to_invalidate.sort()
plan = collections.Counter(l0_active[k]["source_kind"] for k in to_extract)
print(f"[计划] L0 活跃 ⊖ L1 = {len(to_extract)}  {dict(plan)}")
print(f"[计划] L1 需失效（L0 已 gone）= {len(to_invalidate)}")
print(f"[基准] artifact 键 {len(ART_KEYS)} 个 | manifest 键 {len(MAN_KEYS)} 个")
if not APPLY:
    print("\n未写入（加 --apply）")
    sys.exit(0)

new_man, new_idx, arts = [], [], []


def write_art(kb_type, rid, obj):
    assert set(obj) == ART_KEYS, (set(obj) ^ ART_KEYS)
    d = f"{L1}/{REV[kb_type]}"
    os.makedirs(d, exist_ok=True)
    p = f"{d}/{rid}.json"
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=1)
    with open(tmp, "rb") as fh:
        assert fh.read(1) == b"{", "产物被封装（信封），需换写法"
    json.load(open(tmp, encoding="utf-8"))
    os.replace(tmp, p)
    return p


for key in to_extract:
    e = l0_active[key]
    rid = rid_of(key)
    sk = e["source_kind"]
    if sk == "feishu_bitable_record":
        tid = e["table_id"]
        label = TABLE_LABEL.get(tid, e.get("table_name") or tid)
        rec = json.load(open(f"{L0}/records/{label}/{e['record_id']}.json", encoding="utf-8"))
        segs = []
        for name, fd in rec["fields"].items():
            t = text_of(fd.get("value"))
            if not t:
                continue
            segs.append({"kind": "field_value", "field_name": name, "text": t,
                         "anchor": f"#{label}/{e['record_id']}/{name}"})
        chars = sum(len(s["text"]) for s in segs)
        art = {"resource_id": rid, "resource_key": key, "kb_type": e["kb_type"], "source_kind": sk,
               "source_sha256": e["sha256"], "extractor_version": EXT, "status": "ok", "status_reason": "",
               "anchor_spec": "anchor-1.0", "anchor_kind": sk,
               "source": {"table_name": label, "record_id": e["record_id"], "field_name": None,
                          "entry_url": e["entry_url"]},
               "l0_path": None, "l0_depth": e.get("depth"), "l0_matched_rule": e.get("matched_rule"),
               "segments": segs, "tables": [], "media_refs": [], "segment_count": len(segs),
               "table_count": 0, "media_count": 0, "char_count": chars, "observed_at": RUN}
        p = write_art(e["kb_type"], rid, art)
        arts.append(p)
        row = {"resource_id": rid, "resource_key": key, "kb_type": e["kb_type"], "source_kind": sk,
               "source_sha256": e["sha256"], "extractor_version": EXT, "status": "ok", "status_reason": "",
               "segment_count": len(segs), "char_count": chars, "media_count": 0, "table_count": 0,
               "observed_at": RUN}
        assert not (set(row) - MAN_KEYS), set(row) - MAN_KEYS
        new_man.append(row)
        for i, s in enumerate(segs, 1):
            new_idx.append({"anchor": s["anchor"], "char_count": len(s["text"]), "kb_type": e["kb_type"],
                            "resource_id": rid, "kind": s["kind"], "seg_id": f"{rid}#s{i}",
                            "source_sha256": e["sha256"]})
    elif sk == "feishu_attachment":
        row = {"resource_id": rid, "resource_key": key, "kb_type": e["kb_type"], "source_kind": sk,
               "source_sha256": None, "extractor_version": EXT, "status": "pending_ocr",
               "status_reason": "字节未取：bot 身份 media 下载 403（见 kb/l8/runs/20260929-1155）；"
                                "待下载权限或用户身份登录后补 OCR",
               "segment_count": 0, "char_count": 0, "media_count": 0, "table_count": 0, "observed_at": RUN}
        assert not (set(row) - MAN_KEYS), set(row) - MAN_KEYS
        new_man.append(row)
    else:
        print("  [跳过] 未处理 source_kind:", sk, key)

inv_rows = []
for key in to_invalidate:
    old = l1_latest[key]
    row = dict(old)
    row.update({"status": "invalidated", "status_reason":
                "L0 台账 20260929-1200：飞书侧整批替换，该记录已归档（status=gone）",
                "observed_at": RUN})
    inv_rows.append(row)

with open(f"{L1}/manifest_l1.jsonl", "a", encoding="utf-8") as fh:
    for r in new_man + inv_rows:
        fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
with open(f"{L1}/index/l1.jsonl", "a", encoding="utf-8") as fh:
    for r in new_idx:
        fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")

out = {"run": RUN, "layer": "l1", "driver": "kb/l8/extract_l1_new_resources.py",
       "l0_active": len(l0_active), "l0_gone": len(l0_gone),
       "extracted": len(to_extract), "extracted_by_kind": dict(plan),
       "artifacts": len(arts), "manifest_rows_appended": len(new_man),
       "index_rows_appended": len(new_idx), "invalidated_rows_appended": len(inv_rows),
       "pending_ocr": sum(1 for r in new_man if r["status"] == "pending_ocr"),
       "segments_total": sum(r["segment_count"] for r in new_man),
       "chars_total": sum(r["char_count"] for r in new_man)}
json.dump(out, open(f"kb/l1/runs/{RUN}.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"[写入] 抽取 {len(to_extract)}（产物 {len(arts)}）| manifest +{len(new_man)} | index +{len(new_idx)} | 失效 +{len(inv_rows)}")
print("        segments 合计", out["segments_total"], "| 字符合计", out["chars_total"], "| pending_ocr", out["pending_ocr"])
print("        run 记录 kb/l1/runs/%s.json" % RUN)
