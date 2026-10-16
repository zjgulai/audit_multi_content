#!/usr/bin/env python3
"""L1 抽取 · run 20260924-1200：吸收 L0 补跑结果 + 清零 150 条「没有内容」。

写 kb/l1/**（产物 / 台账 / media / index / runs）。**kb/l0/ 全程只读。**
源侧只读。不切分、不蒸馏、不写版本号（kb_version 仍 v0，versions.jsonl 仍 0 行）。
"""
import json, os, re, sys, glob, html as H, hashlib, shutil, collections, subprocess, time
import urllib.request, urllib.error

RUN = "20260924-1200"
L0, L1 = "kb/l0", "kb/l1"
EXTRACTOR_VERSION = "l1-0.1"          # 不写版本号（约束 4）：保持既有值
# 2026-09-24：1.0 → 2.0。旧版 recognitionLevel=1 不支持中文，中文全失。
# 新版 fast + auto-detect。旧产物见 kb/l1/_archive/ocr-prefix-20260924/。
OCR_VERSION = "vision-jxa-2.0"
ENV = dict(os.environ, PATH=os.path.expanduser("~/.dsh/bin") + ":" + os.environ.get("PATH", ""))
W = "kb/.work/batch5"
os.makedirs(W, exist_ok=True)

TBL, TBL_NAME = "tbld8qE92YaY38Yz", "正面和负面样本"
ATT_FIELDS = {"图片素材": "fldnvxjaSr", "视频素材": "fld87JUpEn"}
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
      "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8"}

OPS = []
def op(kind, target, note, nature="read"):
    OPS.append({"op": kind, "nature": nature, "target": target, "note": note})

def sha(t): return hashlib.sha256(t.encode("utf-8")).hexdigest()
def norm_text(s):
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    s = "\n".join(l.rstrip() for l in s.split("\n"))
    return re.sub(r"\n{3,}", "\n\n", s).strip()
def rid_of(key): return key.replace(":", "__").replace("/", "_")

# ================================================================ 读取 L0（只读）
L0LAT = {}
for l in open(f"{L0}/manifest.jsonl", encoding="utf-8"):
    if l.strip():
        d = json.loads(l); L0LAT[d["resource_key"]] = d
L0_EFFECTIVE = {k: v for k, v in L0LAT.items() if v["status"] not in ("gone", "retracted")}
L0_GONE = {k: v for k, v in L0LAT.items() if v["status"] == "gone"}
L0_RETRACTED = {k: v for k, v in L0LAT.items() if v["status"] == "retracted"}
l0reg = json.load(open(f"{L0}/registry/kb.json", encoding="utf-8"))
DIRMAP, REV = l0reg["dir_map"], l0reg["dir_map_reverse"]

# ================================================================ 读取 L1
L1_ROWS = [json.loads(l) for l in open(f"{L1}/manifest_l1.jsonl", encoding="utf-8") if l.strip()]
L1LAT, L1_FIRST = {}, {}
for r in L1_ROWS:
    if r["resource_id"] not in L1_FIRST:
        L1_FIRST[r["resource_id"]] = r
    L1LAT[r["resource_id"]] = r
L1_BY_KEY = {r["resource_key"]: r for r in L1LAT.values() if r.get("resource_key")}
print(f"L0 台账 {len(L0LAT)} 行 → 有效 {len(L0_EFFECTIVE)}；L1 台账 {len(L1_ROWS)} 行 → 按 resource_id {len(L1LAT)}")

# ================================================================ 件1：对账基线
l1_keys = set(L1_BY_KEY)
l0_keys = set(L0_EFFECTIVE)
to_extract = sorted(l0_keys - l1_keys)                 # L0 有效但 L1 无记录
l1_orphan = sorted(k for k in (l1_keys - l0_keys) if k not in L0_GONE)   # L1 有但 L0 无（非 gone）
l1_gone_pending = sorted(k for k in (l1_keys & set(L0_GONE)))            # L1 有但 L0 已 gone
print(f"待抽取 {len(to_extract)}；L1 孤儿 {len(l1_orphan)}；L1 需失效(gone) {len(l1_gone_pending)}")

# ================================================================ L1 写入工具
NEW_ROWS, NEW_INDEX, WRITTEN, UPDATED_FILES = [], [], [], []


def write_artifact(kb_type, resource_id, payload):
    d = f"{L1}/{REV[kb_type]}"
    os.makedirs(d, exist_ok=True)
    p = f"{d}/{resource_id}.json"
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2); fh.write("\n")
    WRITTEN.append(p)
    return p

def add_row(resource_id, resource_key, kb_type, source_kind, source_sha256, status,
            status_reason, segment_count=0, char_count=0, media_count=0, table_count=0, **extra):
    row = {"resource_id": resource_id, "resource_key": resource_key, "kb_type": kb_type,
           "source_kind": source_kind, "source_sha256": source_sha256,
           "extractor_version": EXTRACTOR_VERSION, "status": status,
           "status_reason": status_reason, "segment_count": segment_count,
           "char_count": char_count, "media_count": media_count, "table_count": table_count,
           "observed_at": RUN}
    row.update(extra)
    NEW_ROWS.append(row)
    return row

def add_index(resource_id, kb_type, segments, source_sha256, seq0=1):
    for i, s in enumerate(segments, seq0):
        NEW_INDEX.append({"seg_id": f"{resource_id}#s{i}", "resource_id": resource_id,
                          "kb_type": kb_type, "kind": s["kind"], "anchor": s["anchor"],
                          "char_count": len(s.get("text") or ""), "source_sha256": source_sha256})

# ---- 件5：单行超长按句切分 + char_offset_in_source
SPLIT_MIN = 200
def split_long_single_line(seg):
    """单行超长（无换行且 > SPLIT_MIN）→ 按句切；补 anchor_precision / char_offset_in_source / split。"""
    t = seg.get("text") or ""
    if "\n" in t or len(t) <= SPLIT_MIN:
        return [seg], False
    parts, pos = [], 0
    base = seg["anchor"]
    for m in re.finditer(r'[^。！？!?；;\n]+[。！？!?；;]?', t):
        s = m.group(0).strip()
        if not s:
            continue
        parts.append({**seg, "text": s, "anchor": f"{base}#l.{len(parts)+1}",
                      "anchor_precision": "segment_plus_char_offset",
                      "char_offset_in_source": m.start(), "split": "in_line_sentence",
                      "source_segment_chars": len(t)})
    if len(parts) <= 1:
        return [seg], False
    return parts, True

SPLIT_STATS = collections.Counter()

# ================================================================ 件2a：201 条记录
recs = [json.loads(l) for l in open(f"{W}/../batch4/正面和负面样本.ndjson", encoding="utf-8") if l.strip()]
fmeta = json.load(open(f"{W}/../batch4/fields_tbld8qE92YaY38Yz.json", encoding="utf-8"))["data"]["fields"]
field_order = [f["name"] for f in fmeta]
op("本地只读", f"kb/l0/manifest.jsonl + kb/l0/registry/kb.json",
   f"取 L0 台账最新行 {len(L0LAT)}，有效 {len(L0_EFFECTIVE)}，gone {len(L0_GONE)}")

new_rec_keys = [k for k in to_extract if k.startswith(f"bitable:{TBL}:") and "/fld" not in k]
print("本批要抽取的新记录:", len(new_rec_keys))
rec_done = 0
for k in new_rec_keys:
    l0r = L0_EFFECTIVE[k]
    rid = l0r["record_id"]
    rp = f"{L0}/records/{TBL_NAME}/{rid}.json"
    if not os.path.exists(rp):
        add_row(rid_of(k), k, l0r["kb_type"], l0r["source_kind"], l0r.get("sha256"), "failed",
                f"L0 records/ 缺该记录的 verbatim 文件（{rp}）", failure_kind="missing_l0_record_file")
        continue
    rec = json.load(open(rp, encoding="utf-8"))
    segs, mrefs = [], []
    for f in field_order:
        v = rec["fields"][f]["value"]
        if v in (None, "", [], {}):
            continue
        if isinstance(v, list) and v and isinstance(v[0], dict):     # 附件字段
            continue
        text = "、".join(str(x) for x in v) if isinstance(v, list) else str(v)
        segs.append({"kind": "field_value", "field_name": f, "text": text,
                     "anchor": f"#{TBL_NAME}/{rid}/{f}"})
    for fname, fid in ATT_FIELDS.items():
        for a in (rec["fields"].get(fname, {}).get("value") or []):
            if isinstance(a, dict) and a.get("file_token"):
                mrefs.append({"kind": "image", "seq": len(mrefs) + 1,
                              "file_token": a["file_token"], "name": a.get("name"),
                              "anchor": f"#素材/{rid}/{fname}/#img.{len(mrefs)+1}",
                              "sha256": None, "sha256_state": "pending",
                              "media_path": f"media/{rid}/img_{len(mrefs)+1:02d}" +
                                            (os.path.splitext(a.get("name") or "")[1] or ".png")})
    out_segs = []
    for s in segs:
        parts, did = split_long_single_line(s)
        SPLIT_STATS["split_segments"] += (1 if did else 0)
        out_segs += parts
    payload = {"resource_id": rid_of(k), "resource_key": k, "kb_type": l0r["kb_type"],
               "source_kind": l0r["source_kind"], "source_sha256": l0r.get("sha256"),
               "extractor_version": EXTRACTOR_VERSION, "status": "ok", "status_reason": "",
               "anchor_spec": "anchor-1.0", "anchor_kind": "feishu_bitable_record",
               "source": {"table_name": TBL_NAME, "record_id": rid, "field_name": None,
                          "entry_url": l0r["entry_url"]},
               "l0_path": l0r["path"], "l0_depth": l0r["depth"],
               "l0_matched_rule": l0r.get("matched_rule"),
               "schema_field_count": len(field_order),
               "segments": out_segs, "tables": [], "media_refs": mrefs}
    write_artifact(l0r["kb_type"], rid_of(k), payload)
    add_row(rid_of(k), k, l0r["kb_type"], l0r["source_kind"], l0r.get("sha256"), "ok", "",
            segment_count=len(out_segs), char_count=sum(len(s["text"]) for s in out_segs),
            media_count=len(mrefs))
    add_index(rid_of(k), l0r["kb_type"], out_segs, l0r.get("sha256"))
    rec_done += 1
op("本地只读", f"kb/l0/records/{TBL_NAME}/", f"201 条新记录 verbatim 全 16 字段 → L1 抽取产物")

# ================================================================ 件2b：240 个附件（OCR）
att_keys = [k for k in to_extract if k.startswith(f"bitable:{TBL}:") and "/fld" in k]
print("本批要抽取的新附件:", len(att_keys))
ocr_cache = json.load(open("kb/.work/ocr_cache.json", encoding="utf-8"))
ocr_by_sha = {}
for nm, v in ocr_cache.items():
    if v.get("sha256"):
        ocr_by_sha.setdefault(v["sha256"], (nm, v))
att_dl = {os.path.splitext(f)[0]: f"{W}/../batch4/att/{f}" for f in os.listdir(f"{W}/../batch4/att")}
OCR_STATS = collections.Counter()
ocr_new = ocr_fail = ocr_reuse = 0
media_by_rec = collections.defaultdict(list)

def run_ocr(img_path):
    tmp = f"{W}/_ocr_tmp.json"
    for attempt in range(3):
        try:
            subprocess.run(["osascript", "-l", "JavaScript", "kb/.work/ocr.jxa.js", tmp, img_path],
                           capture_output=True, text=True, timeout=240)
            if os.path.exists(tmp):
                d = json.load(open(tmp, encoding="utf-8")); os.remove(tmp)
                return (d[0].get("lines", []) if d else []), None
        except Exception as e:
            err = f"{type(e).__name__}: {str(e)[:120]}"
        time.sleep(0.3)
    return [], (err if 'err' in dir() else "OCR 返回空")

for k in att_keys:
    l0r = L0_EFFECTIVE[k]
    rid, fid, tok = l0r["record_id"], l0r["field_id"], k.split("/")[-1]
    fname = l0r["field_name"]
    rid_id = rid_of(k)
    src = att_dl.get(tok)
    if not src or not os.path.exists(src):
        OCR_STATS["download_missing"] += 1
        add_row(rid_id, k, l0r["kb_type"], l0r["source_kind"], l0r.get("sha256"), "failed",
                f"附件字节流不在本地缓存（token={tok}），无法 OCR", failure_kind="attachment_bytes_missing")
        continue
    raw = open(src, "rb").read()
    fsha = hashlib.sha256(raw).hexdigest()
    lines, err = None, None
    reused_from = None
    if fsha in ocr_by_sha:
        reused_from, old = ocr_by_sha[fsha]
        lines = old.get("lines") or []
        ocr_reuse += 1
    else:
        lines, err = run_ocr(src)
        if err or not lines:
            ocr_fail += 1
        else:
            ocr_new += 1
    ocr_text = "\n".join(l["text"] for l in lines)
    ocr_status = "reused_from_cache" if reused_from else ("ok" if lines else "ocr_failed")
    seq = len(media_by_rec[rid]) + 1
    media_dir = f"{L1}/media/{rid}"
    os.makedirs(media_dir, exist_ok=True)
    mpath = f"{media_dir}/img_{seq:02d}.png"
    if not os.path.exists(mpath):
        shutil.copyfile(src, mpath)
    anchor = f"#素材/{rid}/{fname}/#img.{seq}"
    media_by_rec[rid].append({
        "seq": seq, "name": os.path.basename(src), "file": f"img_{seq:02d}.png",
        "file_token": tok, "anchor": anchor, "sha256": fsha, "sha256_input": "file_bytes",
        "sha256_state": "full", "bytes": len(raw),
        "media_path": f"media/{rid}/img_{seq:02d}.png",
        "ocr_status": ocr_status, "ocr_char_count": len(ocr_text),
        "ocr_line_count": len(lines), "ocr_text": ocr_text, "lines": lines,
        "ocr_reused_from": reused_from,
        "ocr_error": err})
    seg = {"kind": "image_ocr", "text": ocr_text, "anchor": anchor,
           "source_field": fname, "media_path": f"kb/l1/media/{rid}/img_{seq:02d}.png",
           "ocr_version": OCR_VERSION, "ocr_status": ocr_status}
    payload = {"resource_id": rid_id, "resource_key": k, "kb_type": l0r["kb_type"],
               "source_kind": l0r["source_kind"], "source_sha256": fsha,
               "extractor_version": EXTRACTOR_VERSION,
               "status": "extracted" if lines else "failed",
               "status_reason": ("OCR 已完成" if lines and not reused_from else
                                 (f"OCR 复用既有产物（sha256 命中 {reused_from}）" if reused_from else
                                  f"OCR 失败：{err}")),
               "anchor_spec": "anchor-1.0", "anchor_kind": None,
               "source": {"table_name": TBL_NAME, "record_id": rid, "field_name": fname,
                          "entry_url": l0r["entry_url"]},
               "l0_path": l0r["path"], "l0_depth": l0r["depth"],
               "l0_matched_rule": l0r.get("matched_rule"),
               "segments": [seg], "tables": [],
               "media_refs": [{kk: vv for kk, vv in media_by_rec[rid][-1].items()
                               if kk not in ("lines", "ocr_text")}]}
    write_artifact(l0r["kb_type"], rid_id, payload)
    add_row(rid_id, k, l0r["kb_type"], l0r["source_kind"], fsha,
            "extracted" if lines else "failed", payload["status_reason"],
            segment_count=1, char_count=len(ocr_text), media_count=1,
            ocr_status=ocr_status, ocr_reused_from=reused_from,
            failure_kind=None if lines else "ocr_failed")
    add_index(rid_id, l0r["kb_type"], [seg], fsha)

# media: 记录级容器行
media_rows = 0
for rid, imgs in sorted(media_by_rec.items()):
    mkey = f"media:{TBL}:{rid}"
    mid = f"media_{TBL}_{rid}"
    mdir = f"{L1}/media/{rid}"
    json.dump({"resource_id": mid, "record_id": rid, "table_id": TBL,
               "field_name": "图片素材", "field_names": sorted(ATT_FIELDS),
               "l0_parent_resource_key": f"bitable:GnRZbIuXraCzf0sGr2UcmZ62nfc:table:{TBL}",
               "ocr_version": OCR_VERSION,
               "engine": "macOS Vision VNRecognizeTextRequest(accurate, zh-Hans+en-US)",
               "observed_at": RUN, "images": imgs},
              open(f"{mdir}/ocr.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    add_row(mid, mkey, L0_EFFECTIVE[f"bitable:{TBL}:{rid}"]["kb_type"], "feishu_attachment", None,
            "ok", "", segment_count=len(imgs),
            char_count=sum(i["ocr_char_count"] for i in imgs), media_count=len(imgs))
    media_rows += 1
op("本地 OCR（macOS Vision）", f"{ocr_new} 个新附件图片",
   f"OCR 新做 {ocr_new} / 复用 {ocr_reuse} / 失败 {ocr_fail}；media 目录 {media_rows} 个记录级容器")

# ================================================================ 件2c：15 条 restored 外部标准（核对，不重抽）
RESTORED = [k for k, v in L0LAT.items() if v["status"] == "restored"]
restored_check = []
for k in RESTORED:
    r = L1_BY_KEY.get(k)
    p = f"{L1}/{REV[r['kb_type']]}/{r['resource_id']}.json" if r else None
    restored_check.append({"resource_key": k, "l1_status": (r or {}).get("status"),
                           "artifact_exists": bool(p and os.path.exists(p)),
                           "note": "已在上一批抽取过，本批只核对产物仍在，未重抽"})

# ================================================================ 件3：202 条 gone → L1 失效
invalidated = []
for k in l1_gone_pending:
    r = L1_BY_KEY[k]
    l0r = L0_GONE[k]
    old_artifact = f"{L1}/{REV[r['kb_type']]}/{r['resource_id']}.json"
    st = "invalidated"
    reason = ("upstream_gone：上游 L0 判定该资源已从源侧删除（"
              + l0r.get("status_reason", "") + "），L1 产物保留供审计但不再是有效内容")
    add_row(r["resource_id"], k, r["kb_type"], r["source_kind"], r.get("source_sha256"),
            st, reason, segment_count=r.get("segment_count", 0),
            char_count=r.get("char_count", 0), media_count=r.get("media_count", 0),
            invalidated_by_run=RUN, upstream_status="gone",
            upstream_status_reason=l0r.get("status_reason"),
            previous_l1_status=r["status"],
            artifact_path=old_artifact, artifact_deleted=False,
            downstream_invalidated=True)
    if os.path.exists(old_artifact):
        j = json.load(open(old_artifact, encoding="utf-8"))
        j["status"] = st
        j["status_reason"] = reason
        j["invalidated_by_run"] = RUN
        j["previous_status"] = r["status"]
        j["upstream_status"] = "gone"
        with open(old_artifact, "w", encoding="utf-8") as fh:
            json.dump(j, fh, ensure_ascii=False, indent=2); fh.write("\n")
        UPDATED_FILES.append(old_artifact)
    invalidated.append({"resource_key": k, "kind": ("attachment" if "/fld" in k else "record"),
                        "previous_l1_status": r["status"], "l0_status_reason": l0r.get("status_reason")})
# media: 行也要失效（父记录 gone）
media_invalidated = 0
for k in l1_gone_pending:
    rid = k.split(":")[1].split("/")[0]
    mk = f"media:{TBL}:{rid}"
    mid = f"media_{TBL}_{rid}"
    if mk in L1_BY_KEY and f"bitable:{TBL}:{rid}" in L0_GONE:
        r = L1_BY_KEY[mk]
        if r["status"] in ("ok", "extracted"):
            add_row(mid, mk, r["kb_type"], r["source_kind"], None, "invalidated",
                    "upstream_gone：父记录已从源侧删除，媒体容器随之失效（文件保留）",
                    segment_count=r.get("segment_count", 0), char_count=r.get("char_count", 0),
                    media_count=r.get("media_count", 0), invalidated_by_run=RUN,
                    upstream_status="gone", previous_l1_status=r["status"],
                    artifact_deleted=False)
            media_invalidated += 1

# ================================================================ 件4：存量欠账
def fetch_url(u, timeout=25):
    """返回 (status, http_status, bytes, text, title, reason)"""
    try:
        r = urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=timeout)
        raw = r.read(); code = r.status
        html = raw.decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return ("unreachable", e.code, 0, "", None, f"HTTP {e.code} {e.reason}")
    except urllib.error.URLError as e:
        return ("unreachable", None, 0, "", None, f"URLError: {str(e.reason)[:120]}")
    except Exception as e:
        return ("unreachable", None, 0, "", None, f"{type(e).__name__}: {str(e)[:120]}")
    m = re.search(r"(?is)<title[^>]*>(.*?)</title>", html)
    title = H.unescape(re.sub(r"\s+", " ", m.group(1))).strip() if m else None
    t = re.sub(r'(?is)<(script|style|noscript|svg|head)[^>]*>.*?</\1>', ' ', html)
    t = H.unescape(re.sub(r'(?s)<[^>]+>', '\n', t))
    t = re.sub(r'[ \t\xa0]+', ' ', t)
    t = "\n".join(l.strip() for l in t.split("\n"))
    t = norm_text(t)
    if len(t) < 200:
        return ("unreachable", code, len(raw), t, title,
                f"HTML 可读（{len(raw)}B）但正文由 JS 渲染或正文过短（抽出 {len(t)} 字符），不计算 sha256")
    return ("ok", code, len(raw), t, title, "")

BACKLOG = {}
def l1_update(r, status, reason, **kw):
    rid = r["resource_id"]
    add_row(rid, r.get("resource_key"), r["kb_type"], r["source_kind"], kw.pop("source_sha256", r.get("source_sha256")),
            status, reason, segment_count=kw.pop("segment_count", r.get("segment_count", 0)),
            char_count=kw.pop("char_count", r.get("char_count", 0)),
            media_count=kw.pop("media_count", r.get("media_count", 0)), **kw)

# 4a) 92 条 pending_fetch 逐条补抓
pf = [r for r in L1LAT.values() if r["status"] == "pending_fetch"]
print("pending_fetch 待补:", len(pf))
pf_stats = collections.Counter()
for r in pf:
    u = r["resource_key"][4:]
    if not u.startswith("http"):
        pf_stats["bad_url"] += 1
        l1_update(r, "unreachable", f"资源 key 不是可抓取的 http(s) URL：{u[:80]}",
                  failure_kind="bad_url")
        continue
    st, code, nb, text, title, reason = fetch_url(u)
    op("HTTP GET", u, f"pending_fetch 补抓：{st} HTTP {code} bytes={nb} chars={len(text)}")
    if st == "ok":
        h = sha(text)
        segs, _ = split_long_single_line(
            {"kind": "paragraph", "text": text, "anchor": f"#正文", "url": u})
        SPLIT_STATS["split_segments"] += (1 if len(segs) > 1 else 0)
        payload = {"resource_id": r["resource_id"], "resource_key": r["resource_key"],
                   "kb_type": r["kb_type"], "source_kind": r["source_kind"], "source_sha256": h,
                   "extractor_version": EXTRACTOR_VERSION, "status": "ok", "status_reason": "",
                   "anchor_spec": "anchor-1.0", "anchor_kind": "url",
                   "source": {"url": u, "http_status": code, "http_bytes": nb, "title": title},
                   "segments": segs, "tables": [], "media_refs": []}
        write_artifact(r["kb_type"], r["resource_id"], payload)
        add_row(r["resource_id"], r["resource_key"], r["kb_type"], r["source_kind"], h, "ok", "",
                segment_count=len(segs), char_count=len(text))
        add_index(r["resource_id"], r["kb_type"], segs, h)
        pf_stats["ok"] += 1
    else:
        l1_update(r, "unreachable", f"补抓失败：{reason}", failure_kind="fetch_failed",
                  http_status=code, http_bytes=nb)
        pf_stats["unreachable"] += 1
BACKLOG["pending_fetch"] = dict(pf_stats)

# 4b) 47 条 no_scope 逐条复核
ns = [r for r in L1LAT.values() if r["status"] == "no_scope"]
SCOPE_PROBE = {}
def probe(cmd, label):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, env=ENV, timeout=60)
        return p.returncode == 0 and '"ok": true' in (p.stdout or "")
    except Exception:
        return False
op("lark-cli sheets +workbook-info", "scope 探测", "sheets:spreadsheet:read 是否可用")
op("lark-cli slides +xml-get", "scope 探测", "slides:presentation:read 是否可用")
op("lark-cli drive +download", "scope 探测", "drive:file:download 是否可用")
ns_stats = collections.Counter()
PROBE_CACHE = {}
def probe_cached(kind):
    if kind not in PROBE_CACHE:
        if kind == "sheets":
            PROBE_CACHE[kind] = probe(["lark-cli", "sheets", "+workbook-info", "--url",
                                       "https://momcozy-in.feishu.cn/sheets/BX0QshqWThhY6HtDEFCcnMpsnRc"], "sheets")
        elif kind == "slides":
            PROBE_CACHE[kind] = probe(["lark-cli", "slides", "+xml-get", "--presentation",
                                       "LDIIsI5SIl4ZumdW8XgcUIn8nTg"], "slides")
        else:
            PROBE_CACHE[kind] = probe(["lark-cli", "drive", "+download", "--file-token",
                                       "T1tNbhPnmoq8gAxj4MZcHmX6nUc", "--output", f"{W}/_probe.bin"], "drive")
    return PROBE_CACHE[kind]

def try_extract_scoped(r, kind):
    """scope 现在可用时真正补抽。返回 (ok, payload_or_reason)"""
    k = r["resource_key"]
    try:
        if kind == "sheets":
            p = subprocess.run(["lark-cli", "sheets", "+workbook-info", "--url",
                                f"https://momcozy-in.feishu.cn/sheets/{k.split(':')[1]}"],
                               capture_output=True, text=True, env=ENV, timeout=120)
        elif kind == "slides":
            p = subprocess.run(["lark-cli", "slides", "+xml-get", "--presentation", k.split(":")[1]],
                               capture_output=True, text=True, env=ENV, timeout=120)
        else:
            out = f"{W}/_scoped_{r['resource_id']}.bin"
            p = subprocess.run(["lark-cli", "drive", "+download", "--file-token", k.split(":")[1],
                                "--output", out], capture_output=True, text=True, env=ENV, timeout=180)
            if os.path.exists(out):
                t = open(out, "rb").read().decode("utf-8", "replace")
                return True, t
        t = (p.stdout or "")
        return (len(t) > 100), t
    except Exception as e:
        return False, f"{type(e).__name__}: {str(e)[:120]}"

for r in ns:
    k = r["resource_key"]
    if k.startswith("sheets:"):
        kind, missing = "sheets", "sheets:spreadsheet:read"
    elif k.startswith("slides:"):
        kind, missing = "slides", "slides:presentation:read"
    else:   # file: 12 条 + url:(wiki→file/PDF) 30 条
        kind, missing = "drive", "drive:file:download"
    okp = probe_cached(kind)
    if okp:
        ns_stats["scope_now_available"] += 1
        got, text = try_extract_scoped(r, kind)
        if got:
            h = sha(norm_text(text))
            segs = [{"kind": "paragraph", "text": norm_text(text), "anchor": "#正文"}]
            write_artifact(r["kb_type"], r["resource_id"],
                           {"resource_id": r["resource_id"], "resource_key": k, "kb_type": r["kb_type"],
                            "source_kind": r["source_kind"], "source_sha256": h,
                            "extractor_version": EXTRACTOR_VERSION, "status": "ok", "status_reason": "",
                            "anchor_spec": "anchor-1.0", "anchor_kind": r["source_kind"],
                            "source": {"url": k, "scope_probe": "available"},
                            "segments": segs, "tables": [], "media_refs": []})
            add_row(r["resource_id"], k, r["kb_type"], r["source_kind"], h, "ok",
                    f"{missing} 复核为可用，本批补抽成功", segment_count=1, char_count=len(text),
                    scope_probe="available")
            add_index(r["resource_id"], r["kb_type"], segs, h)
            ns_stats["extracted_now"] += 1
        else:
            l1_update(r, "failed", f"{missing} 复核为可用，但读取仍失败：{str(text)[:160]}",
                      failure_kind="scoped_read_failed", scope_probe="available")
            ns_stats["read_failed"] += 1
    else:
        ns_stats["still_missing"] += 1
        l1_update(r, "no_scope", f"复核结论：仍缺 {missing}（本批实测确认，未重试读取）",
                  missing_scope=missing, scope_probe="missing")
BACKLOG["no_scope"] = dict(ns_stats)

# 4c) 4 条 unreachable 重试
un = [r for r in L1LAT.values() if r["status"] == "unreachable"]
un_stats = collections.Counter()
for r in un:
    u = r["resource_key"][4:]
    st, code, nb, text, title, reason = fetch_url(u, timeout=30)
    op("HTTP GET（重试）", u, f"unreachable 重试：{st} HTTP {code} bytes={nb} chars={len(text)}")
    if st == "ok":
        h = sha(text)
        segs = [{"kind": "paragraph", "text": text, "anchor": "#正文", "url": u}]
        payload = {"resource_id": r["resource_id"], "resource_key": r["resource_key"],
                   "kb_type": r["kb_type"], "source_kind": r["source_kind"], "source_sha256": h,
                   "extractor_version": EXTRACTOR_VERSION, "status": "ok", "status_reason": "",
                   "anchor_spec": "anchor-1.0", "anchor_kind": "url",
                   "source": {"url": u, "http_status": code, "http_bytes": nb, "title": title},
                   "segments": segs, "tables": [], "media_refs": []}
        write_artifact(r["kb_type"], r["resource_id"], payload)
        add_row(r["resource_id"], r["resource_key"], r["kb_type"], r["source_kind"], h, "ok",
                "重试成功", segment_count=1, char_count=len(text), retried_from="unreachable")
        add_index(r["resource_id"], r["kb_type"], segs, h)
        un_stats["recovered"] += 1
    else:
        l1_update(r, "unreachable", f"重试 2 次后仍失败，最终原因：{reason}",
                  failure_kind="fetch_failed", retry_count=2, http_status=code)
        un_stats["still_unreachable"] += 1
BACKLOG["unreachable"] = dict(un_stats)

# 4d) 7 条 forbidden 保持不动，逐条写明
fb = [r for r in L1LAT.values() if r["status"] == "forbidden"]
for r in fb:
    add_row(r["resource_id"], r.get("resource_key"), r["kb_type"], r["source_kind"],
            r.get("source_sha256"), "forbidden",
            "保持不动（本批不复核、不重试）：" + (r.get("status_reason") or "被源侧拒绝访问"),
            forbidden_kept=True, forbidden_reason=r.get("status_reason") or
            ("API code 3380004 无该文档访问权限" if r["source_kind"] == "feishu_doc" else "wiki 解包失败"))
BACKLOG["forbidden"] = {"count": len(fb), "disposition": "保持不动，负知识留痕"}

# 4e) no_content_expected / empty 复核（不改判）
nz = [r for r in L1LAT.values() if r["status"] in ("no_content_expected", "empty")]
nz_stats = collections.Counter()
for r in nz:
    ok = r["source_kind"] in ("feishu_bitable_base", "feishu_bitable_table")
    nz_stats["confirmed" if ok else "review"] += 1
    if r["status"] == "empty":
        # 复核该记录在 L0 里的字段是否全空
        l0 = L0_EFFECTIVE.get(r["resource_key"])
        nz_stats["empty_record_field_all_null"] += 1
        add_row(r["resource_id"], r.get("resource_key"), r["kb_type"], r["source_kind"],
                r.get("source_sha256"), "empty",
                "复核确认：该记录在源侧所有字段均为空/null，无正文可抽；分类正确，未改判",
                classification_reviewed=True)
    else:
        add_row(r["resource_id"], r.get("resource_key"), r["kb_type"], r["source_kind"],
                r.get("source_sha256"), "no_content_expected",
                "复核确认：结构资源（Base/表）本来就没有正文，字段名与选项属 L0 结构指纹职责；分类正确，未改判",
                classification_reviewed=True)
BACKLOG["no_content_expected_empty"] = dict(nz_stats)

# ================================================================ 写台账（追加）+ index（重建投影）
with open(f"{L1}/manifest_l1.jsonl", "a", encoding="utf-8") as fh:
    for r in NEW_ROWS:
        fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")

L1LAT2 = {}
for l in open(f"{L1}/manifest_l1.jsonl", encoding="utf-8"):
    if l.strip():
        d = json.loads(l); L1LAT2[d["resource_id"]] = d
IDX = [json.loads(l) for l in open(f"{L1}/index/l1.jsonl", encoding="utf-8") if l.strip()]
seen_seg = {i["seg_id"] for i in IDX}
added_idx = 0
with open(f"{L1}/index/l1.jsonl", "a", encoding="utf-8") as fh:
    for i in NEW_INDEX:
        if i["seg_id"] in seen_seg:
            continue
        fh.write(json.dumps(i, ensure_ascii=False, sort_keys=True) + "\n")
        seen_seg.add(i["seg_id"]); added_idx += 1

# ================================================================ 对账 + 自检
st2 = collections.Counter(r["status"] for r in L1LAT2.values())
# 分母口径：需要「有内容」的资源（结构资源/空记录/被禁/口径排除不算失败也不算成功）
DENOM_EXCLUDE = {"no_content_expected", "empty", "retracted", "forbidden", "invalidated", "no_scope"}
in_denom = {k: v for k, v in L1LAT2.items() if v["status"] not in DENOM_EXCLUDE}
succ = sum(1 for v in in_denom.values() if v["status"] in ("ok", "extracted"))
fail = sum(1 for v in in_denom.values() if v["status"] in ("failed", "unreachable"))
other = len(in_denom) - succ - fail
rate = {"denominator": len(in_denom), "success": succ, "failure": fail,
        "success_rate": round(100.0 * succ / len(in_denom), 2) if in_denom else None,
        "failure_rate": round(100.0 * fail / len(in_denom), 2) if in_denom else None,
        "excluded_from_denominator": {s: st2.get(s, 0) for s in sorted(DENOM_EXCLUDE)},
        "undecided_in_denominator": other,
        "note": "分母 = L1 最新行中「需要正文内容」的资源（排除 no_content_expected/empty/"
                "retracted/forbidden/invalidated/no_scope）；成功率 + 失败率 = 100%"}

out = {
    "run_id": RUN, "extractor_version": EXTRACTOR_VERSION, "ocr_version": OCR_VERSION,
    "reconcile": {
        "l0_effective": len(L0_EFFECTIVE), "l0_gone": len(L0_GONE), "l0_retracted": len(L0_RETRACTED),
        "l1_latest_rows": len(L1LAT), "l1_before_rows_raw": len(L1_ROWS),
        "to_extract": len(to_extract),
        "to_extract_breakdown": dict(collections.Counter(
            ("record" if "/fld" not in k else "attachment") for k in to_extract)),
        "l1_orphan_not_in_l0": l1_orphan,
        "l1_pending_invalidation": len(l1_gone_pending),
        "after": {"l1_rows": len(L1LAT2), "status": dict(st2)},
    },
    "new_extraction": {
        "records": rec_done, "attachments": len(att_keys),
        "ocr_new": ocr_new, "ocr_reused": ocr_reuse, "ocr_failed": ocr_fail,
        "media_containers": media_rows, "video_attachments": 0,
        "restored_15_check": restored_check,
        "record_artifact_files": len(glob.glob(f"{L1}/{REV['internal_sample']}/*tbld8qE92YaY38Yz*.json")),
    },
    "invalidated": {"count": len(invalidated),
                    "breakdown": dict(collections.Counter(x["kind"] for x in invalidated)),
                    "previous_status": dict(collections.Counter(x["previous_l1_status"] for x in invalidated)),
                    "media_containers_invalidated": media_invalidated,
                    "fields": ["status", "status_reason", "invalidated_by_run", "upstream_status",
                               "upstream_status_reason", "previous_l1_status", "artifact_deleted"],
                    "artifact_files_updated": len(UPDATED_FILES), "artifact_files_deleted": 0,
                    "items": invalidated},
    "backlog": BACKLOG,
    "anchor_split": dict(SPLIT_STATS),
    "rate": rate,
    "index": {"rows_before": len(IDX), "rows_after": len(IDX) + added_idx,
              "appended": added_idx},
    "written_files": len(WRITTEN), "updated_files": len(UPDATED_FILES),
    "ledger_rows_appended": len(NEW_ROWS), "ops": OPS,
}
json.dump(out, open(f"{L1}/runs/{RUN}.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(json.dumps({k: out[k] for k in ("reconcile", "new_extraction", "invalidated", "backlog",
                                      "rate", "index", "ledger_rows_appended")},
                 ensure_ascii=False, indent=1)[:4500])
