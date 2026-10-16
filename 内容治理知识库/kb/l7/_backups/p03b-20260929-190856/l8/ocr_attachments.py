#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""规则③：附件图片**用 OCR 提取** —— 产物落 L1，L0 只读（用户 2026-09-29 口径①③）。

与既有 `kb/.work/l1_media.py` 的差异：
  · 输入改为**当前飞书侧**的 负面样本 记录（`feishu-负面样本.ndjson`，108 条），不再读旧抓取的 `正负样本.ndjson`；
  · 字段名用**现名** `图片素材`（field_id fldnvxjaSr 未变；旧名 `具体内容（截图/文案/OCR）` 已退役）；
  · 身份显式 `--as bot --profile dsh-kb`（用户 token 已过期）；
  · OCR 按批调用 `ocr.jxa.js`（一次多图），过 `kb_ocr_gate.ocr_cache_reusable` 闸门；
  · 每条图片算 sha256 作为 `source_sha256`（锚点+哈希成对，符合 anchor_sha256_binding）。

用法：python3 kb/l8/ocr_attachments.py <run_id>
产物：kb/l1/media/media_<table>_<rid>/img_NN.ext + ocr.json
      kb/l1/2_内部正负样本库/<rid>.json（资源文档，含 OCR 段）
      kb/l1/media/<run>.manifest.json（统计与闸门结果）
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

import glob
import hashlib
import json
import os
import subprocess
import sys
import time

WS = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
os.chdir(WS)
sys.path.insert(0, "kb/.work")
from kb_ocr_gate import ocr_cache_reusable, OCR_OK_VERSION  # noqa: E402
# ── 干跑档 · 开关解析（P0-3 · 2026-09-29 补）───────────────────────────────
# 必须早于 RUN 解析：把 --apply 从 argv 里剔除，避免它被当成位置参数 run_id。
APPLY = "--apply" in sys.argv
if APPLY:
    sys.argv.remove("--apply")
# ──────────────────────────────────────────────────────────────────────────

RUN = sys.argv[1] if len(sys.argv) > 1 else time.strftime("%Y%m%d-%H%M")
# 身份：默认用户身份（刘华丽）—— 附件字节下载需要 drive:file:download，bot 身份对同一 pair 报 403
AS_ID = os.environ.get("L8_AS", "user")
PROFILE = os.environ.get("L8_PROFILE", "dsh-kb")
PURGE = "--purge-images" in sys.argv      # OCR 出文本后删除本地图片（只留文本 + sha256）
BASE, TABLE = "GnRZbIuXraCzf0sGr2UcmZ62nfc", "tbld8qE92YaY38Yz"
L1 = "kb/l1"
FIELD_IMG, FID_IMG = "图片素材", "fldnvxjaSr"
FIELD_VID, FID_VID = "视频素材", "fld87JUpEn"
EXTRACTOR_VERSION = "l1-0.1"
ENV = dict(os.environ, PATH=os.path.expanduser("~/.dsh/bin") + ":" + os.environ.get("PATH", ""))
os.makedirs(f"{L1}/media", exist_ok=True)
os.makedirs(f"{L1}/2_内部正负样本库", exist_ok=True)
sha = lambda b: hashlib.sha256(b).hexdigest()

records = [json.loads(l) for l in open("kb/l8/_stage/feishu-compare/feishu-负面样本.ndjson", encoding="utf-8") if l.strip()]
print(f"[OCR] 记录 {len(records)} 条；字段 {FIELD_IMG}({FID_IMG}) / {FIELD_VID}({FID_VID})")

# 1) 下载全部图片
todo = []           # (rid, seq, token, name, out)
for r in records:
    rid = r["record_id"]
    seq = 0
    for a in (r.get(FIELD_IMG) or []):
        if not a.get("file_token"):
            continue
        seq += 1
        ext = os.path.splitext(a.get("name") or "")[1] or ".png"
        out = f"{L1}/media/media_{TABLE}_{rid}/img_{seq:02d}{ext}"
        todo.append((rid, seq, a["file_token"], a.get("name"), out))
print(f"[OCR] 图片附件 {len(todo)} 张")
stats = {"images": len(todo), "downloaded": 0, "download_failed": 0, "ocr_batches": 0,
         "ocr_ok": 0, "ocr_empty": 0, "gate_rejected": 0, "videos_skipped": 0}
for rid, seq, tok, name, out in todo:
    if os.path.exists(out) and os.path.getsize(out) > 0:
        stats["downloaded"] += 1
        continue
    os.makedirs(os.path.dirname(out), exist_ok=True)
    last = ""
    for _attempt in range(3):                      # 失败重试 3 次（网络/限流）
        p = subprocess.run(["lark-cli", "base", "+record-download-attachment", "--base-token", BASE,
                            "--table-id", TABLE, "--record-id", rid, "--file-token", tok,
                            "--output", out, "--overwrite", "--as", AS_ID, "--profile", PROFILE],
                           capture_output=True, text=True, encoding="utf-8", errors="replace",
                           env=ENV, timeout=180)
        if os.path.exists(out) and os.path.getsize(out) > 0:
            break
        last = (p.stdout or p.stderr or "")[:160].replace("\n", " ")
    if os.path.exists(out) and os.path.getsize(out) > 0:
        stats["downloaded"] += 1
    else:
        stats["download_failed"] += 1
        print(f"  下载失败 {rid} #{seq}: {last}")
for r in records:
    stats["videos_skipped"] += len(r.get(FIELD_VID) or [])
print(f"[OCR] 下载完成 {stats['downloaded']}/{stats['images']}"
      f"（身份 {AS_ID}/{PROFILE}；视频 {stats['videos_skipped']} 个不做 OCR）")

# 失败即停：一张都没下来就别往下写（上一次就是在这里空跑，写出 108 份 0 段文档）
if stats["images"] > 0 and stats["downloaded"] == 0:
    fail = {"run": RUN, "status": "aborted", "images": stats["images"],
            "downloaded": 0, "download_failed": stats["download_failed"],
            "identity": f"{AS_ID}/{PROFILE}",
            "reason": "全部图片下载失败 → 不写任何 L1 文档（避免空产物）"}
    json.dump(fail, open(f"{L1}/media/{RUN}.aborted.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"[中止] {stats['images']} 张全部下载失败，未写任何产物 → kb/l1/media/{RUN}.aborted.json")
    sys.exit(2)

# 2) 批量 OCR（先过缓存闸门）
ocr_text = {}       # out_path → lines
cache_dir = f"{L1}/media/_cache"
os.makedirs(cache_dir, exist_ok=True)
pending = []
for rid, seq, tok, name, out in todo:
    if not os.path.exists(out):
        continue
    raw = open(out, "rb").read()
    fsha = sha(raw)
    cp = os.path.join(cache_dir, f"{fsha}.json")
    if os.path.exists(cp):
        entry = json.load(open(cp, encoding="utf-8"))
        entry.setdefault("ocr_version", OCR_OK_VERSION)
        ok, why = ocr_cache_reusable(entry, len(raw))
        if ok:
            ocr_text[out] = entry.get("lines") or []
            stats["ocr_ok"] += 1
            continue
        else:
            stats["gate_rejected"] += 1
    pending.append((out, cp, fsha))
print(f"[OCR] 待 OCR {len(pending)} 张（缓存命中并过闸门 {stats['ocr_ok']}，闸门拒绝 {stats['gate_rejected']}）")

BATCH = 30
for i in range(0, len(pending), BATCH):
    chunk = pending[i:i + BATCH]
    outj = f"{cache_dir}/_batch_{i//BATCH:03d}.json"
    imgs = [c[0] for c in chunk]
    subprocess.run(["osascript", "-l", "JavaScript", "kb/.work/ocr.jxa.js", outj, *imgs],
                   capture_output=True, text=True, timeout=600, env=ENV)
    stats["ocr_batches"] += 1
    data = json.load(open(outj, encoding="utf-8")) if os.path.exists(outj) else []
    byfile = {d.get("file"): (d.get("lines") or []) for d in data}
    for out, cp, fsha in chunk:
        lines = byfile.get(out) or []
        text = "\n".join(l.get("text", "") for l in lines).strip()
        json.dump({"sha256": fsha, "sha256_state": "full", "ocr_version": OCR_OK_VERSION,
                   "ocr_text": text, "ocr_line_count": len(lines), "lines": lines,
                   "engine": "macOS Vision(VNRecognizeTextRequest)", "at": RUN},
                  open(cp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        ocr_text[out] = lines
        stats["ocr_ok" if text else "ocr_empty"] += 1
    if os.path.exists(outj):
        os.remove(outj)
    print(f"[OCR] 批 {i//BATCH+1}：{len(chunk)} 张（累计 ok {stats['ocr_ok']} / 空 {stats['ocr_empty']}）")

# 3) 写 L1 资源文档（每条记录一份）
by_rec = {}
for rid, seq, tok, name, out in todo:
    by_rec.setdefault(rid, []).append((seq, tok, name, out))
media_entries = []
for rid, items in sorted(by_rec.items()):
    r = next(x for x in records if x["record_id"] == rid)
    imgs, segs = [], []
    for seq, tok, name, out in sorted(items):
        raw = open(out, "rb").read() if os.path.exists(out) else b""
        fsha = sha(raw) if raw else None
        lines = ocr_text.get(out) or []
        text = "\n".join(l.get("text", "") for l in lines).strip()
        anchor = f"#素材/{rid}/{FIELD_IMG}/#img.{seq}"
        imgs.append({"seq": seq, "file_token": tok, "name": name, "bytes": len(raw),
                     "anchor": anchor, "sha256": fsha, "status": "ok" if text else "empty"})
        if text:
            segs.append({"seg_id": f"media_{TABLE}_{rid}#s{seq}", "anchor": anchor,
                         "source_sha256": fsha, "kind": "image_ocr", "text": text,
                         "char_count": len(text), "lines": len(lines)})
        media_entries.append({"resource_id": f"media_{TABLE}_{rid}", "record_id": rid, "seq": seq,
                              "anchor": anchor, "chars": len(text), "sha256": fsha})
    doc = {"resource_id": f"media_{TABLE}_{rid}", "resource_key": f"media:{TABLE}:{rid}",
           "kb_type": "internal_sample", "source_kind": "feishu_attachment",
           "source_sha256": None, "extractor_version": EXTRACTOR_VERSION,
           "status": "ok" if segs else "empty",
           "status_reason": "" if segs else "图片已下载并算指纹，但 OCR 未识别出文本",
           "anchor_spec": "anchor-1.0", "anchor_kind": "image",
           "l0_parent_resource_key": f"bitable:{BASE}:table:{TABLE}",
           "l0_note": "kb/l0 只读：本资源是 L1 媒体产物（用户口径①：优化 L1–L7 不动 L0）",
           "source": {"table_name": "负面样本", "record_id": rid, "field_name": FIELD_IMG,
                      "entry_url": f"https://momcozy-in.feishu.cn/base/{BASE}?table={TABLE}&record={rid}"},
           "record_context": {k: v for k, v in r.items() if k not in (FIELD_IMG, FIELD_VID) and v not in (None, "", [])},
           "segments": segs, "tables": [], "media_refs": imgs,
           "segment_count": len(segs), "table_count": 0, "media_count": len(imgs),
           "char_count": sum(len(s["text"]) for s in segs),
           "ocr_version": OCR_OK_VERSION, "observed_at": RUN}
# ── 干跑档 · 落盘闸门（P0-3 · 2026-09-29 补）───────────────────────────────
# 不带 --apply 时：**只预演、不落盘**，一个字节都不写。
if not APPLY:
    print("[dry-run] %s 未落盘。" % _os.path.basename(_os.path.abspath(__file__)))
    print("[dry-run] 本脚本会写入：L1 OCR：写 kb/l1/2_内部正负样本库/media_*.json、l1/media/*/ocr.json 与 manifest")
    print("[dry-run] 加 --apply 才落盘（补档原因：原先运行即写盘，已发生过一次未授权写入）")
    _sys.exit(0)
# ──────────────────────────────────────────────────────────────────────────
    json.dump(doc, open(f"{L1}/2_内部正负样本库/media_{TABLE}_{rid}.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    json.dump({"resource_id": doc["resource_id"], "record_id": rid, "table_id": TABLE, "field_name": FIELD_IMG,
               "field_id": FID_IMG, "l0_parent_resource_key": doc["l0_parent_resource_key"],
               "ocr_version": OCR_OK_VERSION, "engine": "macOS Vision VNRecognizeTextRequest",
               "images": imgs, "observed_at": RUN},
              open(f"{L1}/media/media_{TABLE}_{rid}/ocr.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

rep = {"run": RUN, "at": time.strftime("%Y-%m-%d %H:%M:%S"),
       "rule": "图片用 OCR 提取（用户 2026-09-29 口径③）", "l0_untouched": True,
       "table": TABLE, "field": f"{FIELD_IMG}({FID_IMG})", "records_with_images": len(by_rec),
       "stats": stats, "ocr_version": OCR_OK_VERSION,
       "identity": f"{AS_ID}/{PROFILE}",
       "segments_total": sum(1 for m in media_entries if m["chars"] > 0),
       "chars_total": sum(m["chars"] for m in media_entries)}

# 4) 用完即删图（用户口径：OCR 只是提取文案，图片不留）—— 文本与 sha256 已写进产物/缓存
if PURGE:
    purged = 0
    freed = 0
    for _rid, _seq, _tok, _name, out in todo:
        if os.path.exists(out):
            freed += os.path.getsize(out)
            os.remove(out)
            purged += 1
    rep["purge"] = {"images_deleted": purged, "bytes_freed": freed,
                    "kept": "OCR 文本 + file_bytes sha256（kb/l1/media/_cache/*.json 与 ocr.json）"}
    print(f"[清理] 删除本地图片 {purged} 张（释放 {freed/1048576:.1f} MB）；文本与 sha256 已保留")
json.dump(rep, open(f"{L1}/media/{RUN}.manifest.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"[OCR] 完成：记录 {len(by_rec)} 条 / 图片 {stats['images']} / OCR 出文本 {rep['segments_total']} 段 "
      f"/ 字符 {rep['chars_total']} → {L1}/media/{RUN}.manifest.json（L0 未改动）")
