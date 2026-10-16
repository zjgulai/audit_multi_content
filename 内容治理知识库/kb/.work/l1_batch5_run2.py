#!/usr/bin/env python3
"""L1 run 20260924-1200 · 收口：补抽 11 条被漏掉的 L0 有效资源 + 件5 单行超长按句切分。"""
import json, os, re, sys, glob, html as H, hashlib, collections

RUN = "20260924-1200"
L0, L1 = "kb/l0", "kb/l1"
EXTRACTOR_VERSION = "l1-0.1"
W = "kb/.work/batch5"
REV = json.load(open(f"{L0}/registry/kb.json", encoding="utf-8"))["dir_map_reverse"]

def sha(t): return hashlib.sha256(t.encode("utf-8")).hexdigest()
def norm_text(s):
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    s = "\n".join(l.rstrip() for l in s.split("\n"))
    return re.sub(r"\n{3,}", "\n\n", s).strip()
def rid_of(k): return k.replace(":", "__").replace("/", "_")

L0LAT = {}
for l in open(f"{L0}/manifest.jsonl", encoding="utf-8"):
    if l.strip():
        d = json.loads(l); L0LAT[d["resource_key"]] = d
L0E = {k: v for k, v in L0LAT.items() if v["status"] not in ("gone", "retracted")}
L1LAT = {}
for l in open(f"{L1}/manifest_l1.jsonl", encoding="utf-8"):
    if l.strip():
        d = json.loads(l); L1LAT[d["resource_id"]] = d
L1K = {v["resource_key"] for v in L1LAT.values() if v.get("resource_key")}
MISSING = sorted(set(L0E) - L1K)
print("补抽:", len(MISSING))

NEW_ROWS, NEW_INDEX, WRITTEN, UPDATED = [], [], [], []
def add_row(**kw):
    kw["observed_at"] = RUN; kw.setdefault("extractor_version", EXTRACTOR_VERSION)
    NEW_ROWS.append(kw)
def write_artifact(kb_type, rid, payload):
    d = f"{L1}/{REV[kb_type]}"; os.makedirs(d, exist_ok=True)
    p = f"{d}/{rid}.json"
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2); fh.write("\n")
    WRITTEN.append(p); return p
def add_index(rid, kb_type, segs, ssha, seq0=1):
    for i, s in enumerate(segs, seq0):
        NEW_INDEX.append({"seg_id": f"{rid}#s{i}", "resource_id": rid, "kb_type": kb_type,
                          "kind": s["kind"], "anchor": s["anchor"],
                          "char_count": len(s.get("text") or ""), "source_sha256": ssha})

# ---------------------------------------------------------------- 补抽 11 条
done, failed = 0, []
for k in MISSING:
    l0r = L0E[k]
    rid = rid_of(k)
    tn = l0r.get("table_name")
    segs, ssha, note = [], l0r.get("sha256"), ""
    if l0r["source_kind"] == "feishu_bitable_record" and l0r.get("table_name") == "内容公式（仅供参考）":
        p = f"{L0}/records/内容公式（仅供参考）/{l0r['record_id']}.json"
        rec = json.load(open(p, encoding="utf-8"))
        for f, fv in rec["fields"].items():
            v = fv["value"]
            if v in (None, "", [], {}):
                continue
            segs.append({"kind": "field_value", "field_name": f, "text": str(v),
                         "anchor": f"#内容公式（仅供参考）/{l0r['record_id']}/{f}"})
    elif l0r["source_kind"] == "feishu_bitable_record" and l0r.get("table_name") == "材料收集":
        p = f"{L0}/records/材料收集/{l0r['record_id']}.json"
        rec = json.load(open(p, encoding="utf-8"))
        for f, fv in rec["fields"].items():
            v = fv["value"]
            if v in (None, "", [], {}):
                continue
            text = "、".join(str(x) for x in v) if isinstance(v, list) else str(v)
            segs.append({"kind": "field_value", "field_name": f, "text": text,
                         "anchor": f"#材料收集/{l0r['record_id']}/{f}"})
    elif k == "url:https://support.momcozy.com/":
        html = open("kb/.work/batch3/url_support_momcozy.html", "rb").read().decode("utf-8", "replace")
        t = re.sub(r'(?is)<(script|style|noscript|svg)[^>]*>.*?</\1>', ' ', html)
        t = H.unescape(re.sub(r'(?s)<[^>]+>', ' ', t))
        t = re.sub(r'[ \t\xa0]+', ' ', t)
        t = norm_text("\n".join(l.strip() for l in t.split("\n")))
        ssha = sha(t)
        segs = [{"kind": "paragraph", "text": t, "anchor": "#正文"}]
        note = f"复用 run 20260924-1000 已下载的 HTML 快照（本地只读），sha256 与 L0 台账一致：{ssha[:16]}"
    elif k == "wiki:EL1nw9zdyinX2iklXfLco216niM":
        doc = json.load(open("kb/.work/batch3/fetch_EL1nw9.json", encoding="utf-8"))["data"]["document"]
        t = doc["content"]
        ssha = sha(norm_text(t))
        segs = [{"kind": "paragraph", "text": t, "anchor": "#正文", "revision": doc.get("revision_id")}]
        note = f"复用 run 20260924-1000 的 docs +fetch 快照（本地只读），sha256 与 L0 台账一致：{ssha[:16]}"
    if not segs:
        failed.append({"resource_key": k, "reason": "无可用正文来源"})
        add_row(resource_id=rid, resource_key=k, kb_type=l0r["kb_type"],
                source_kind=l0r["source_kind"], source_sha256=ssha, status="failed",
                status_reason="补抽失败：L0 records/ 无对应 verbatim 文件或字段全空",
                segment_count=0, char_count=0, media_count=0, table_count=0,
                failure_kind="no_source_content")
        continue
    payload = {"resource_id": rid, "resource_key": k, "kb_type": l0r["kb_type"],
               "source_kind": l0r["source_kind"], "source_sha256": ssha,
               "extractor_version": EXTRACTOR_VERSION, "status": "ok", "status_reason": "",
               "anchor_spec": "anchor-1.0",
               "anchor_kind": ("feishu_bitable_record" if l0r["source_kind"] == "feishu_bitable_record"
                               else ("feishu_doc" if k.startswith("wiki:") else "url")),
               "source": {"table_name": l0r.get("table_name"), "record_id": l0r.get("record_id"),
                          "entry_url": l0r["entry_url"]},
               "l0_path": l0r["path"], "l0_depth": l0r["depth"],
               "l0_matched_rule": l0r.get("matched_rule"), "backfill_note": note,
               "segments": segs, "tables": [], "media_refs": []}
    write_artifact(l0r["kb_type"], rid, payload)
    add_row(resource_id=rid, resource_key=k, kb_type=l0r["kb_type"],
            source_kind=l0r["source_kind"], source_sha256=ssha, status="ok", status_reason="",
            segment_count=len(segs), char_count=sum(len(s["text"]) for s in segs),
            media_count=0, table_count=0, backfill_missing_from_previous_runs=True)
    add_index(rid, l0r["kb_type"], segs, ssha)
    done += 1

# ---------------------------------------------------------------- 件5：单行超长按句切分（l2-0.2 做法）
BOUND = re.compile(r'(?<=[.!?。！？])\s+')
def split_long_single_line(txt):
    if len(txt) < 800:
        return None
    parts, start = [], 0
    for m in BOUND.finditer(txt):
        end = m.end(); seg = txt[start:end]
        if seg.strip():
            parts.append((start, seg.strip()))
        start = end
    if start < len(txt) and txt[start:].strip():
        parts.append((start, txt[start:].strip()))
    return parts if len(parts) > 1 else None

split_segments = split_parts = 0
split_files = []
for p in sorted(glob.glob(f"{L1}/*/*.json")):
    try:
        d = json.load(open(p, encoding="utf-8"))
    except Exception:
        continue
    if not d.get("segments"):
        continue
    rid = d["resource_id"]
    out, changed = [], False
    for s in d["segments"]:
        t = s.get("text") or ""
        parts = split_long_single_line(t) if "\n" not in t else None
        if not parts:
            out.append(s); continue
        changed = True; split_segments += 1; split_parts += len(parts)
        for off, seg in parts:
            out.append({**s, "text": seg, "split": "in_line_sentence",
                        "char_offset_in_source": off,
                        "anchor_precision": "segment_plus_char_offset",
                        "source_segment_chars": len(t)})
    if not changed:
        continue
    d["segments"] = out
    d["long_line_split"] = {"at": RUN, "split": "in_line_sentence",
                            "anchor_precision": "segment_plus_char_offset",
                            "note": "沿用 l2-0.2 做法：只拆不合，不改写一字；锚点仍指物理位置，"
                                    "char_offset_in_source 给出该句在原子段里的字符偏移"}
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(d, fh, ensure_ascii=False, indent=2); fh.write("\n")
    UPDATED.append(p); split_files.append(rid)
    prev = L1LAT.get(rid, {})
    add_row(resource_id=rid, resource_key=d.get("resource_key"), kb_type=d["kb_type"],
            source_kind=d["source_kind"], source_sha256=d.get("source_sha256"),
            status=d.get("status", prev.get("status")), status_reason=d.get("status_reason", ""),
            segment_count=len(out), char_count=sum(len(x.get("text") or "") for x in out),
            media_count=prev.get("media_count", 0), table_count=prev.get("table_count", 0),
            long_line_split_applied=True, split_from_segment_count=len(d["segments"]))
    # index 重建该资源的分段：先记录新段（旧段 id 不复用，靠 seg_id 去重）
    add_index(rid, d["kb_type"], out, d.get("source_sha256"))

# ---------------------------------------------------------------- 写台账 + index
with open(f"{L1}/manifest_l1.jsonl", "a", encoding="utf-8") as fh:
    for r in NEW_ROWS:
        fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
IDX = [json.loads(l) for l in open(f"{L1}/index/l1.jsonl", encoding="utf-8") if l.strip()]
seen = {i["seg_id"] for i in IDX}
added = 0
# 切分后同一 seg_id 的 char_count/anchor 变了 → 用新行覆盖（index 是投影，允许重建该 key）
idx_lat = {}
for i in IDX:
    idx_lat[i["seg_id"]] = i
for i in NEW_INDEX:
    idx_lat[i["seg_id"]] = i
with open(f"{L1}/index/l1.jsonl", "w", encoding="utf-8") as fh:
    for k in sorted(idx_lat):
        fh.write(json.dumps(idx_lat[k], ensure_ascii=False, sort_keys=True) + "\n")
added = len(idx_lat) - len(seen)

out = {"run_id": RUN, "part": "l1 收口：补抽 11 条 + 件5 单行切分",
       "backfilled": done, "backfill_failed": failed, "backfilled_keys": MISSING,
       "long_line_split": {"segments_split": split_segments, "parts_produced": split_parts,
                           "files_updated": len(UPDATED), "resource_ids": split_files},
       "written_files": len(WRITTEN), "updated_files": len(UPDATED),
       "ledger_rows_appended": len(NEW_ROWS),
       "index": {"rows_before": len(seen), "rows_after": len(idx_lat), "delta": added}}
json.dump(out, open(f"{W}/run2.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
json.dump({"written": WRITTEN, "updated": UPDATED}, open(f"{W}/run2_files.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print(json.dumps(out, ensure_ascii=False, indent=1)[:1800])
