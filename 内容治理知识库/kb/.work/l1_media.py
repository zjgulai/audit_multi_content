#!/usr/bin/env python3
"""L1 媒体抽取：Base 附件图片 → 下载字节 → sha256(file_bytes) → macOS Vision OCR。

关键事实：`正面和负面样本` 表的 125 条记录**未被 L0 登记**（该表不在入口表 link 下钻路径上），
因此这 77 张图片没有对应的 L0 资源。处理方式：作为 **L1 媒体产物**登记，
挂到 L0 中确实存在的「表资源」bitable:GnRZbIuXraCzf0sGr2UcmZ62nfc:table:tbld8qE92YaY38Yz，
锚点用记录级自然位置 `#素材/<record_id>/具体内容（截图/文案/OCR）/#img.N`。
kb/l0/ 只读，不改。
"""
import json, os, re, subprocess, hashlib, collections, sys

RUN = sys.argv[1]
L0, L1 = "kb/l0", "kb/l1"
# 2026-09-24：1.0 → 2.0。旧版 recognitionLevel=1 不支持中文，中文全失。
# 新版 fast + auto-detect。旧产物见 kb/l1/_archive/ocr-prefix-20260924/。
EXTRACTOR_VERSION, OCR_VERSION = "l1-0.1", "vision-jxa-2.0"
BASE, IMG_TABLE = "GnRZbIuXraCzf0sGr2UcmZ62nfc", "tbld8qE92YaY38Yz"
FIELD = "具体内容（截图/文案/OCR）"
ENV = dict(os.environ, PATH=os.path.expanduser("~/.dsh/bin") + ":" + os.environ.get("PATH", ""))
DL = "kb/.work/att"
os.makedirs(DL, exist_ok=True)
os.makedirs(f"{L1}/media", exist_ok=True)
os.makedirs(f"{L1}/2_内部正负样本库", exist_ok=True)

rows = [json.loads(l) for l in open("kb/.work/正负样本.ndjson", encoding="utf-8") if l.strip()]
by_rec = collections.defaultdict(list)
for r in rows:
    v = r.get(FIELD)
    if v and isinstance(v, list):
        for i, a in enumerate(v, 1):
            if a.get("file_token"):
                by_rec[r["record_id"]].append({"seq": i, "file_token": a["file_token"],
                                               "name": a.get("name"), "size": a.get("size")})
total_imgs = sum(len(v) for v in by_rec.values())
print(f"图片附件总数 {total_imgs}，来自 {len(by_rec)} 条记录（125 条中 {len(by_rec)} 条带附件）")

L0_TABLE_KEY = f"bitable:{BASE}:table:{IMG_TABLE}"
l0rows = {}
for line in open(f"{L0}/manifest.jsonl", encoding="utf-8"):
    if line.strip():
        r = json.loads(line)
        l0rows[r["resource_key"]] = r
l0_parent = l0rows.get(L0_TABLE_KEY)
print("L0 中该表的资源:", L0_TABLE_KEY, "->", (l0_parent or {}).get("kb_type"), (l0_parent or {}).get("sha256_state"))

ops = [{"op": "base +record-download-attachment", "nature": "read",
        "target": f"bitable:{IMG_TABLE}", "note": f"下载 {total_imgs} 张配图字节流（字段 {FIELD}）"}]
stats = collections.Counter()
media_entries = []

for rid_rec in sorted(by_rec):
    items = by_rec[rid_rec]
    rid = f"media_{IMG_TABLE}_{rid_rec}"
    media_dir = f"{L1}/media/{rid}"
    os.makedirs(media_dir, exist_ok=True)
    imgs, segs = [], []
    for it in items:
        ext = os.path.splitext(it["name"] or "")[1] or ".png"
        out = f"{media_dir}/img_{it['seq']:02d}{ext}"
        if not os.path.exists(out):
            p = subprocess.run(["lark-cli", "base", "+record-download-attachment",
                                "--base-token", BASE, "--table-id", IMG_TABLE,
                                "--record-id", rid_rec, "--file-token", it["file_token"],
                                "--output", out], capture_output=True, text=True, env=ENV, timeout=180)
            if not os.path.exists(out):
                stats["download_failed"] += 1
                imgs.append({**it, "anchor": f"#img.{it['seq']}", "status": "download_failed",
                             "status_reason": (p.stdout or p.stderr)[:200]})
                continue
        raw = open(out, "rb").read()
        fsha = hashlib.sha256(raw).hexdigest()
        try:
            tmp = f"{DL}/_ocr_{it['seq']}.json"
            subprocess.run(["osascript", "-l", "JavaScript", "kb/.work/ocr.jxa.js", tmp, out],
                           capture_output=True, text=True, timeout=240)
            d = json.load(open(tmp, encoding="utf-8")) if os.path.exists(tmp) else []
            lines = d[0].get("lines", []) if d else []
            if os.path.exists(tmp):
                os.remove(tmp)
        except Exception as e:
            lines = []
            stats["ocr_failed"] += 1
        text = "\n".join(l["text"] for l in lines).strip()
        anchor = f"#素材/{rid_rec}/{FIELD}/#img.{it['seq']}"
        imgs.append({"seq": it["seq"], "name": it["name"], "file": os.path.basename(out),
                     "anchor": anchor, "sha256": fsha, "sha256_input": "file_bytes",
                     "sha256_state": "full", "bytes": len(raw),
                     "media_path": f"media/{rid}/{os.path.basename(out)}",
                     "ocr_status": "ok" if text else "empty",
                     "ocr_char_count": len(text), "ocr_line_count": len(lines),
                     "ocr_text": text,
                     "lines": [{"text": l["text"], "confidence": round(l.get("confidence", 0), 3),
                                "bbox": [round(x, 4) for x in l.get("bbox", [])]} for l in lines]})
        stats["image_ok"] += 1
        if text:
            stats["ocr_text_found"] += 1
            segs.append({"kind": "image_ocr", "text": text, "anchor": anchor,
                         "media_path": f"media/{rid}/{os.path.basename(out)}",
                         "ocr_engine": OCR_VERSION, "source_seq": it["seq"]})
        media_entries.append({"resource_id": rid, "record_id": rid_rec, "seq": it["seq"],
                              "anchor": anchor, "chars": len(text), "sha256": fsha})

    with open(f"{media_dir}/ocr.json", "w", encoding="utf-8") as fh:
        json.dump({"resource_id": rid, "record_id": rid_rec, "table_id": IMG_TABLE, "field_name": FIELD,
                   "l0_parent_resource_key": L0_TABLE_KEY, "ocr_version": OCR_VERSION,
                   "engine": "macOS Vision VNRecognizeTextRequest(accurate, zh-Hans+en-US)",
                   "images": imgs, "observed_at": RUN}, fh, ensure_ascii=False, indent=1)

    r = rows_by = next(x for x in rows if x["record_id"] == rid_rec)
    out_res = {
        "resource_id": rid, "resource_key": f"media:{IMG_TABLE}:{rid_rec}",
        "kb_type": "internal_sample", "source_kind": "feishu_attachment",
        "source_sha256": None, "extractor_version": EXTRACTOR_VERSION,
        "status": "ok" if segs else "empty",
        "status_reason": "" if segs else "图片已下载并算指纹，但 OCR 未识别出文本",
        "anchor_spec": "anchor-1.0", "anchor_kind": "image",
        "l0_parent_resource_key": L0_TABLE_KEY,
        "l0_note": "该记录的 125 条同表记录未被 L0 登记（不在入口表 link 下钻路径上），"
                   "故本资源以 L1 媒体产物形式登记，挂到 L0 中存在的表资源；kb/l0/ 未被修改",
        "source": {"table_name": "正面和负面样本", "record_id": rid_rec, "field_name": FIELD,
                   "entry_url": f"https://momcozy-in.feishu.cn/base/{BASE}?table={IMG_TABLE}&record={rid_rec}"},
        "record_context": {k: v for k, v in r.items() if k != FIELD and v not in (None, "", [])},
        "segments": segs, "tables": [], "media_refs": imgs,
        "segment_count": len(segs), "table_count": 0, "media_count": len(imgs),
        "char_count": sum(len(s["text"]) for s in segs),
        "ocr_version": OCR_VERSION, "observed_at": RUN,
    }
    with open(f"{L1}/2_内部正负样本库/{rid}.json", "w", encoding="utf-8") as fh:
        json.dump(out_res, fh, ensure_ascii=False, indent=1)
        fh.write("\n")

json.dump(ops, open("kb/.work/ops-att.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
json.dump({"stats": dict(stats), "media_entries": media_entries, "ocr_version": OCR_VERSION,
           "l0_parent": L0_TABLE_KEY, "records_with_media": len(by_rec), "images": total_imgs},
          open("kb/.work/l1_media.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("媒体统计:", dict(stats))
print(f"OCR 命中文本 {stats['ocr_text_found']}/{stats['image_ok']} 张；媒体资源 {len(by_rec)} 个")
