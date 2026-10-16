#!/usr/bin/env python3
"""L1 文本抽取：按 L0 台账抽取「带位置的文本段 + 表格行 + 媒体文本」。
kb/l0/ 全程只读；产物只写 kb/l1/。
"""
import json, os, re, hashlib, collections, sys

RUN = sys.argv[1]
L0, L1 = "kb/l0", "kb/l1"
SCANNER_L0 = "0.5"
EXTRACTOR_VERSION = "l1-0.1"
LINK_RE = re.compile(r'\[(?P<t>.*?)\]\((?P<u>https?://[^\)\s]+)\)', re.S)

def canon(o):
    return json.dumps(o, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

def sha_text(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

def norm_text(s):
    s = (s or "").replace("\r\n", "\n").replace("\r", "\n")
    s = "\n".join(l.rstrip() for l in s.split("\n"))
    return re.sub(r"\n{3,}", "\n\n", s).strip()

# ---------- L0 输入（只读）
registry = json.load(open(f"{L0}/registry/kb.json", encoding="utf-8"))
DIR_MAP, REV = registry["dir_map"], registry["dir_map_reverse"]
latest = {}
for line in open(f"{L0}/manifest.jsonl", encoding="utf-8"):
    if line.strip():
        r = json.loads(line)
        latest[r["resource_key"]] = r

# L0 资源文件里的 extra（补 source 细节）
def l0_extra(rk):
    d = REV[latest[rk]["kb_type"]]
    for fn in os.listdir(f"{L0}/{d}"):
        if not fn.endswith(".json"):
            continue
        p = f"{L0}/{d}/{fn}"
        e = json.load(open(p, encoding="utf-8"))
        if e.get("resource_key") == rk:
            return e
    return {}

# SCOPE 限制
SCOPE = None
if os.path.exists(f"{L1}/SCOPE.txt"):
    SCOPE = {x.strip() for x in open(f"{L1}/SCOPE.txt", encoding="utf-8") if x.strip() and not x.startswith("#")}
    print("SCOPE 生效:", SCOPE)

l0c = json.load(open("kb/.work/l1_content.json", encoding="utf-8"))
urlc = json.load(open("kb/.work/url_content.json", encoding="utf-8"))
gd = json.load(open("kb/.work/gdoc.json", encoding="utf-8"))
for k, v in gd.items():
    urlc[k] = {"url": k, "status": v["status"], "sha256": v["sha256"], "text_chars": v["extracted_text_chars"],
               "title": v["title"], "content": "", "status_reason": v["status_reason"]}
parent_records = {r["record_id"]: r
                  for r in (json.loads(l) for l in open("kb/.work/材料收集.ndjson", encoding="utf-8") if l.strip())}
base_enum = json.load(open("kb/.work/bases/enum.json", encoding="utf-8"))

ANCHOR_SPEC = {
    "version": "anchor-1.0",
    "principle": "锚点必须来自原文的物理位置，不得由模型编造；定位不到就写进报告的「无法定位锚点」清单，不硬编。",
    "by_resource_type": {
        "pdf": {"page": "#p.12", "table_cell": "#p.12/tbl.3/r.5", "note": "页号从 1 起"},
        "docx": {"heading": "#h.<标题路径>", "paragraph": "#para.35", "note": "有标题用标题路径"},
        "pptx": {"slide": "#s.7"},
        "xlsx": {"range": "#<Sheet>!B4:D9", "note": "保留单元格区域"},
        "md_txt": {"line_range": "#l.120-140", "heading": "#h.<标题路径>"},
        "image": {"index": "#img.<序号>", "region": "#img.2@r120,80,400,300"},
        "video": {"time_window": "#t.00:12:30-00:15:10"},
        "feishu_doc": {"block": "#block.<block_id>", "heading": "#h.<标题路径>"},
        "feishu_bitable_record": {"cell": "#<表名>/<record_id>/<字段名>"},
        "feishu_bitable_table": {"field": "#<表名>/field/<字段名>"},
        "feishu_bitable_base": {"table": "#<Base>/table/<表名>"},
        "url": {"line_range": "#l.120-140"},
    },
    "actual_usage": {},
}

# ---------- 分段器
HEAD_RE = re.compile(r'^(#{1,6})\s+(.*)$')

def seg_markdown(text, kind="docx", max_chars=1500):
    """按原文自然结构切段：标题 / 段落 / 列表项各成一段。返回 (segments, tables, unanchored)"""
    segs, tables, unanchored = [], [], []
    lines = (text or "").split("\n")
    heading_stack = []
    buf, buf_start, in_code, in_table = [], 0, False, False
    tbl_buf, tbl_start = [], 0

    def heading_path():
        return " / ".join(h for _, h in heading_stack) if heading_stack else ""

    def flush_para(end_idx):
        nonlocal buf, buf_start
        if not buf:
            return
        raw = "\n".join(buf).strip()
        if raw:
            hp = heading_path()
            anchor = f"#h.{hp}" if hp else f"#l.{buf_start+1}-{end_idx}"
            segs.append({"kind": "paragraph" if not raw.lstrip().startswith(("-", "*", "•")) else "list_item",
                         "text": raw, "anchor": anchor, "line_range": [buf_start + 1, end_idx]})
        buf, buf_start = [], end_idx + 1

    def flush_table(end_idx):
        nonlocal tbl_buf, tbl_start
        if not tbl_buf:
            return
        rows = []
        for i, rl in enumerate(tbl_buf):
            if re.match(r'^\s*\|[\s\-:|]+\|\s*$', rl):
                continue
            cells = [c.strip() for c in rl.strip().strip("|").split("|")]
            if not any(cells):
                continue
            rows.append({"row_index": i, "cells": cells,
                         "anchor": f"#l.{tbl_start+i+1}", "text": " | ".join(cells)})
        if rows:
            tables.append({"table_index": len(tables), "anchor": f"#l.{tbl_start+1}-{end_idx}",
                           "row_count": len(rows), "rows": rows,
                           "sheet_range": None, "source_format": "markdown"})
        tbl_buf, tbl_start = [], end_idx + 1

    i = 0
    for i, ln in enumerate(lines):
        if ln.strip().startswith("```"):
            flush_para(i - 1) if buf else None
            in_code = not in_code
            buf.append(ln)
            continue
        m = HEAD_RE.match(ln)
        if m and not in_code:
            flush_para(i - 1); flush_table(i - 1)
            lvl, title = len(m.group(1)), m.group(2).strip()
            heading_stack = [(l, h) for l, h in heading_stack if l < lvl]
            heading_stack.append((lvl, title))
            hp = heading_path()
            segs.append({"kind": "heading", "level": lvl, "text": title,
                         "anchor": f"#h.{hp}", "line_range": [i + 1, i + 1]})
            buf_start = i + 1
            continue
        is_tbl = ln.strip().startswith("|") and ln.strip().endswith("|")
        if is_tbl:
            flush_para(i - 1) if buf else None
            if not in_table:
                in_table, tbl_start = True, i
            tbl_buf.append(ln)
            continue
        if in_table:
            flush_table(i - 1); in_table = False
        if not ln.strip():
            flush_para(i - 1)
            buf_start = i + 1
            continue
        if not buf:
            buf_start = i
        buf.append(ln)
    flush_para(len(lines) - 1); flush_table(len(lines) - 1)
    return segs, tables, unanchored

def seg_plaintext(text, max_chars=1500):
    """网页正文：按空行/换行切段，锚点用行区间（原文物理行号）"""
    segs, tables = [], []
    lines = (text or "").split("\n")
    buf, start = [], 0
    out = []
    for i, ln in enumerate(lines):
        if not ln.strip():
            if buf:
                out.append((start, i - 1, "\n".join(buf).strip()))
                buf = []
            start = i + 1
            continue
        if not buf:
            start = i
        buf.append(ln)
    if buf:
        out.append((start, len(lines) - 1, "\n".join(buf).strip()))
    for s, e, t in out:
        if not t:
            continue
        kind = "heading" if (len(t) < 120 and not t.endswith((".", "。", "!", "！", ":", "：", ","))) else "paragraph"
        segs.append({"kind": kind, "text": t, "anchor": f"#l.{s+1}-{e+1}", "line_range": [s + 1, e + 1]})
    return segs, tables

# ---------- 处理顺序
ORDER = ["wording", "external_standard", "internal_sample", "product_desc", "unknown"]
BATCH_DIR = {k: REV[k] for k in ORDER}

os.makedirs(f"{L1}", exist_ok=True)
for k in ORDER:
    os.makedirs(f"{L1}/{REV[k]}", exist_ok=True)
for d in ("media", "index", "runs"):
    os.makedirs(f"{L1}/{d}", exist_ok=True)

# 幂等台账
MAN = f"{L1}/manifest_l1.jsonl"
prev = {}
if os.path.exists(MAN):
    for line in open(MAN, encoding="utf-8"):
        if line.strip():
            r = json.loads(line)
            prev[(r["resource_id"], r["extractor_version"], r["source_sha256"])] = r

def rid_of(rk):
    return re.sub(r'[^0-9A-Za-z._\-]+', '_', rk.replace(":", "__").replace("/", "_"))[:150]

records_out, skipped = [], []
batches = collections.defaultdict(lambda: collections.Counter())

for kb_type in ORDER:
    if SCOPE and BATCH_DIR[kb_type] not in SCOPE and kb_type not in SCOPE:
        continue
    batch = [r for r in latest.values() if r["kb_type"] == kb_type]
    for r in batch:
        rk = r["resource_key"]
        rid = rid_of(rk)
        src_sha = r["sha256"] or ""
        key = (rid, EXTRACTOR_VERSION, src_sha)
        old = prev.get(key)
        if old and old.get("status") in ("ok", "partial", "empty", "pending_ocr", "pending_transcribe",
                                        "no_scope", "forbidden", "unreachable"):
            skipped.append({"resource_id": rid, "reason": "unchanged", "prev_status": old["status"]})
            batches[kb_type]["unchanged"] += 1
            continue

        segs, tables, media_refs, status, status_reason, anchor_kind = [], [], [], "empty", "", None
        sk, sha_state = r["source_kind"], r["sha256_state"]

        if sha_state in ("no_scope", "forbidden", "unreachable"):
            status = {"no_scope": "no_scope", "forbidden": "forbidden", "unreachable": "unreachable"}[sha_state]
            status_reason = r["status_reason"] or "L0 未取到内容"
            if r["source_kind"] == "feishu_file":
                status_reason = (status_reason or "") + "；L1 可用的 Base 附件通道未覆盖该资源，仍按 L0 状态登记"

        elif r["source_kind"] == "feishu_doc":
            c = l0c.get(rk, {})
            content = c.get("content") or ""
            if not content:
                status, status_reason = "unreachable", "L0 缓存无正文"
            else:
                segs, tables, _ = seg_markdown(content, "docx")
                status = "ok" if (segs or tables) else "empty"
                anchor_kind = "feishu_doc"

        elif r["source_kind"] == "url":
            uc = urlc.get(rk[4:]) or urlc.get(rk) or {}
            content = norm_text(uc.get("content") or "")
            if len(content) < 200:
                status = "unreachable"
                status_reason = uc.get("status_reason") or "抓取未返回可解析正文（JS 渲染或 404）"
            else:
                segs, tables = seg_plaintext(content)
                status = "ok" if segs else "empty"
                anchor_kind = "url"

        elif r["source_kind"] == "feishu_bitable_record":
            if r["table_name"] == "材料收集":
                src = parent_records.get(r["record_id"])
            else:
                src = None
                for bt, bd in base_enum.items():
                    for tb in bd["tables"]:
                        if r["resource_key"].startswith(f"bitable:{bt}:") and tb["table_id"] == r["table_id"]:
                            for rec in tb["records"]:
                                if rec["record_id"] == r["record_id"]:
                                    src = rec
                                    break
                if src is None and r["table_name"] == "知识库分类说明":
                    for l in open("kb/.work/分类说明.ndjson", encoding="utf-8"):
                        if l.strip():
                            rec = json.loads(l)
                            if rec["record_id"] == r["record_id"]:
                                src = rec
                                break
            if src is None:
                status, status_reason = "unreachable", "L1 未能从抓取缓存定位该记录的字段原值"
            else:
                for fname, fval in src.items():
                    if fname in ("record_id",):
                        continue
                    if fval in (None, "", []):
                        continue
                    txt = fval
                    if isinstance(fval, list):
                        if fval and isinstance(fval[0], dict) and fval[0].get("file_token"):
                            for a in fval:
                                media_refs.append({"kind": "image", "file_token": a.get("file_token"),
                                                   "name": a.get("name"), "size": a.get("size"),
                                                   "anchor": f"#img.{len(media_refs)+1}",
                                                   "field_name": fname})
                            continue
                        txt = "、".join(str(x) for x in fval)
                    elif isinstance(fval, dict):
                        txt = canon(fval)
                    txt = str(txt)
                    if not txt.strip():
                        continue
                    segs.append({"kind": "field_value", "field_name": fname, "text": txt,
                                 "anchor": f"#{r['table_name']}/{r['record_id']}/{fname}"})
                status = "ok" if segs else "empty"
                anchor_kind = "feishu_bitable_record"

        elif r["source_kind"] in ("feishu_bitable_table", "feishu_bitable_base"):
            e = l0_extra(rk)
            fields = ((e.get("extra") or {}).get("field_count"))
            if r["source_kind"] == "feishu_bitable_table":
                for fn in (f for f in [] ):
                    pass
            # 结构本身不是内容：登记为结构段（可检索字段名/选项）
            st = []
            if r["source_kind"] == "feishu_bitable_table":
                for l in [json.loads(x) for x in open("kb/.work/l1.json", encoding="utf-8") and [] or []]:
                    pass
            status = "empty"
            status_reason = "结构资源（表/Base）没有正文文本：字段与选项属于 L0 结构指纹范围，L1 不重复抽为内容"

        else:
            status, status_reason = "unreachable", f"未支持的 source_kind={sk}"

        out = {
            "resource_id": rid,
            "resource_key": rk,
            "kb_type": kb_type,
            "source_kind": sk,
            "source_sha256": r["sha256"],
            "extractor_version": EXTRACTOR_VERSION,
            "status": status,
            "status_reason": status_reason,
            "anchor_spec": ANCHOR_SPEC["version"],
            "anchor_kind": anchor_kind,
            "source": {"table_name": r["table_name"], "record_id": r["record_id"],
                       "field_name": r["field_name"], "entry_url": r["entry_url"]},
            "l0_path": r["path"], "l0_depth": r["depth"], "l0_matched_rule": r["matched_rule"],
            "segments": segs,
            "tables": tables,
            "media_refs": media_refs,
            "segment_count": len(segs),
            "table_count": len(tables),
            "media_count": len(media_refs),
            "char_count": sum(len(s["text"]) for s in segs) + sum(len(rw["text"]) for t in tables for rw in t["rows"]),
            "observed_at": RUN,
        }
        with open(f"{L1}/{BATCH_DIR[kb_type]}/{rid}.json", "w", encoding="utf-8") as fh:
            json.dump(out, fh, ensure_ascii=False, indent=1)
            fh.write("\n")
        records_out.append(out)
        batches[kb_type][status] += 1
        if status not in ("ok", "partial"):
            batches[kb_type]["not_ok"] += 1

# ---------- 幂等台账（append-only）
with open(MAN, "a", encoding="utf-8") as fh:
    for o in records_out:
        fh.write(json.dumps({
            "resource_id": o["resource_id"], "resource_key": o["resource_key"],
            "kb_type": o["kb_type"], "source_kind": o["source_kind"],
            "source_sha256": o["source_sha256"], "extractor_version": o["extractor_version"],
            "status": o["status"], "status_reason": o["status_reason"],
            "segment_count": o["segment_count"], "table_count": o["table_count"],
            "media_count": o["media_count"], "char_count": o["char_count"],
            "observed_at": RUN,
        }, ensure_ascii=False, sort_keys=True) + "\n")

cur = {}
for line in open(MAN, encoding="utf-8"):
    if line.strip():
        r = json.loads(line)
        cur[(r["resource_id"], r["extractor_version"], r["source_sha256"])] = r

# ---------- index/l1.jsonl（产物投影）
n_idx = 0
with open(f"{L1}/index/l1.jsonl", "w", encoding="utf-8") as fh:
    for k in ORDER:
        d = f"{L1}/{BATCH_DIR[k]}"
        for fn in sorted(os.listdir(d)):
            if not fn.endswith(".json"):
                continue
            o = json.load(open(f"{d}/{fn}", encoding="utf-8"))
            si = 0
            for s in o["segments"]:
                si += 1
                fh.write(json.dumps({"seg_id": f"{o['resource_id']}#s{si}", "resource_id": o["resource_id"],
                                     "kb_type": o["kb_type"], "kind": s["kind"], "anchor": s["anchor"],
                                     "char_count": len(s["text"])}, ensure_ascii=False, sort_keys=True) + "\n")
                n_idx += 1
            for t in o["tables"]:
                for rw in t["rows"]:
                    si += 1
                    fh.write(json.dumps({"seg_id": f"{o['resource_id']}#t{t['table_index']}r{rw['row_index']}",
                                         "resource_id": o["resource_id"], "kb_type": o["kb_type"],
                                         "kind": "table_row", "anchor": rw["anchor"],
                                         "char_count": len(rw["text"])}, ensure_ascii=False, sort_keys=True) + "\n")
                    n_idx += 1

json.dump({"batches": {k: dict(v) for k, v in batches.items()},
           "records": [{k: o[k] for k in ("resource_id", "kb_type", "source_kind", "status", "status_reason",
                                          "segment_count", "table_count", "media_count", "char_count")}
                       for o in records_out],
           "skipped": skipped, "index_rows": n_idx, "manifest_rows": len(cur),
           "anchor_spec": ANCHOR_SPEC},
          open("kb/.work/l1_stats.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

print(f"本轮抽取资源 {len(records_out)} | 跳过(unchanged) {len(skipped)} | index 行 {n_idx} | 台账 {len(cur)}")
for k in ORDER:
    if batches[k]:
        b = batches[k]
        print(f"  {k:18s} ok={b.get('ok',0):4d} empty={b.get('empty',0):3d} "
              f"no_scope={b.get('no_scope',0):3d} forbidden={b.get('forbidden',0):2d} "
              f"unreachable={b.get('unreachable',0):2d} unchanged={b.get('unchanged',0):3d}")
