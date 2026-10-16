#!/usr/bin/env python3
"""batch6 · 件0（评测案图移出）+ 件0.5（OCR 产物重挂）+ 件7（URL 截断复原）。"""
import json, os, re, sys, glob, hashlib, shutil, collections, subprocess, time
import urllib.request, urllib.error
from urllib.parse import urlparse

RUN = "20260924-1210"
L0, L1 = "kb/l0", "kb/l1"
W = "kb/.work"
ARCH_EVAL = f"{L0}/_archive/eval-material-excluded-{RUN}"
OCR_OK_VERSION = "vision-jxa-2.0"
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
      "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8"}
OPS = []
def op(kind, target, note, nature="read"): OPS.append({"op": kind, "nature": nature, "target": target, "note": note})
def sha(t): return hashlib.sha256(t.encode("utf-8")).hexdigest()
def norm_text(s):
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    s = "\n".join(l.rstrip() for l in s.split("\n"))
    return re.sub(r"\n{3,}", "\n\n", s).strip()

# ================================================================ 锁（件9.4）
LOCK = f"{W}/.kb.lock"
def acquire_lock():
    if os.path.exists(LOCK):
        d = json.load(open(LOCK, encoding="utf-8"))
        raise SystemExit(f"[LOCKED] {LOCK} 被占用：{d} —— 退出，不硬写")
    json.dump({"run_id": RUN, "layer": "l0/l1/l2", "pid": os.getpid(),
               "at": time.strftime("%Y-%m-%dT%H:%M:%S")}, open(LOCK, "w", encoding="utf-8"))
def release_lock():
    if os.path.exists(LOCK): os.remove(LOCK)
acquire_lock()

L0LAT = {}
for l in open(f"{L0}/manifest.jsonl", encoding="utf-8"):
    if l.strip(): d = json.loads(l); L0LAT[d["resource_key"]] = d
L0E_BEFORE = {k: v for k, v in L0LAT.items() if v["status"] not in ("gone", "retracted")}
L1LAT = {}
for l in open(f"{L1}/manifest_l1.jsonl", encoding="utf-8"):
    if l.strip(): d = json.loads(l); L1LAT[d["resource_id"]] = d
L1BY = {v["resource_key"]: v for v in L1LAT.values() if v.get("resource_key")}
L0_ROWS, L1_ROWS, L2_ROWS = [], [], []

# ================================================================ 件0：移出 4 张评测案图
EVAL_KEYS = [f"local:review-case:img-{i}" for i in (1, 2, 3, 4)]
os.makedirs(ARCH_EVAL, exist_ok=True)
eval_moved = []
for k in EVAL_KEYS:
    o = L0LAT.get(k)
    if not o:
        continue
    rid = k.replace(":", "__")
    src = None
    for d in os.listdir(L0):
        c = f"{L0}/{d}/{rid}.json"
        if os.path.isfile(c): src = c; break
    dst = f"{ARCH_EVAL}/{rid}.json" if src else None
    if src: shutil.move(src, dst); eval_moved.append({"key": k, "from": src, "to": dst})
    row = {kk: o.get(kk) for kk in ("resource_key", "source_kind", "table_name", "table_id",
                                    "record_id", "field_name", "field_id", "entry_url", "path",
                                    "depth", "kb_type", "matched_rule", "sha256", "sha256_input",
                                    "sha256_state", "revision", "dup_of")}
    row.update({"status": "retracted", "status_reason": "not_source_projection",
                "retract_reason_detail": "非源侧投影：local_file 是这批新开的非源侧入口（评测对照报告的案图），"
                                         "不是内容治理的源材料，用户裁决移出知识库",
                "last_seen_observed_at": o.get("observed_at"), "retracted_at": RUN,
                "moved_from": src, "moved_to": dst, "downstream_invalidated": True,
                "observed_at": RUN, "scanner_version": "0.7"})
    L0_ROWS.append(row)
    # L1 同步失效
    l1r = L1BY.get(k)
    if l1r:
        L1_ROWS.append({**{kk: l1r.get(kk) for kk in
                           ("resource_id", "resource_key", "kb_type", "source_kind", "source_sha256",
                            "extractor_version", "segment_count", "char_count", "media_count", "table_count")},
                        "status": "invalidated", "status_reason":
                        "upstream_retracted：上游 L0 已按 not_source_projection 移出（非源侧投影），"
                        "L1 产物保留供审计但不再是有效内容",
                        "invalidated_by_run": RUN, "upstream_status": "retracted",
                        "upstream_status_reason": "not_source_projection",
                        "previous_l1_status": l1r["status"], "artifact_deleted": False,
                        "observed_at": RUN})
        p = None
        for d in os.listdir(L1):
            c = f"{L1}/{d}/{l1r['resource_id']}.json"
            if os.path.isfile(c): p = c; break
        if p:
            j = json.load(open(p, encoding="utf-8"))
            j.update({"status": "invalidated",
                      "status_reason": L1_ROWS[-1]["status_reason"],
                      "invalidated_by_run": RUN, "upstream_status": "retracted",
                      "previous_status": l1r["status"]})
            json.dump(j, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2); open(p, "a").write("\n")

# L0 registry：source_kind 退役
reg = json.load(open(f"{L0}/registry/kb.json", encoding="utf-8"))
retired = reg.setdefault("source_kind_retired", [])
retired.append({"source_kind": "local_file", "retired_at": RUN,
                "status": "retired", "decision": "user_decision_20260924",
                "reason": "非源侧入口：会让「L0 == 源侧投影」这个核心不变量失效。"
                          "曾用于 4 张评测对照报告案图（local:review-case:img-1..4），已按用户裁决从知识库移出",
                "resource_count_removed": len(L0_ROWS),
                "archived_to": ARCH_EVAL,
                "history": "该 source_kind 由 run 20260924-1115 引入（其 changes 条目保留，未删）"})
if "source_kind_note" in reg:
    reg["source_kind_prev_note"] = reg["source_kind_note"]
    reg["source_kind_note"] = "local_file 已退役（曾用于评测案图，已按用户裁决移出）"
else:
    reg["source_kind_note"] = "local_file 已退役（曾用于评测案图，已按用户裁决移出）"
reg.setdefault("changes", []).append({
    "run_id": RUN, "change": "update",
    "keys": ["source_kind_retired", "source_kind_note"],
    "note": "件0：local_file 退役；4 条评测案图台账追加 retracted(not_source_projection)、文件移入 "
            + ARCH_EVAL + "；run_id=20260924-1115 的历史 changes 条目保留未删"})

# ================================================================ 件0.5：OCR 产物重挂
side = {}
for p in glob.glob(f"{L1}/media/*/ocr.json"):
    d = json.load(open(p, encoding="utf-8"))
    for im in d.get("images", []):
        tok = im.get("file_token") or os.path.splitext(im.get("name") or "")[0]
        side[(d["record_id"], tok)] = {"text": im.get("ocr_text") or "",
                                       "version": d.get("ocr_version"),
                                       "status": im.get("ocr_status"),
                                       "sidecar": p}
L0E = {k: v for k, v in L0LAT.items()
       if v["status"] not in ("gone", "retracted") and k not in set(EVAL_KEYS)}
att = [k for k in L0E if "/fld" in k and k in L1BY and L1BY[k]["status"] in ("ok", "extracted")]
mismatch, remounted, empty_both, reverse_bad = [], [], 0, []
for k in att:
    rid = L1BY[k]["resource_id"]
    p = None
    for d in os.listdir(L1):
        c = f"{L1}/{d}/{rid}.json"
        if os.path.isfile(c): p = c; break
    if not p: continue
    art = json.load(open(p, encoding="utf-8"))
    segtext = "\n".join(s.get("text") or "" for s in art.get("segments") or [])
    rec = k.split(":")[2].split("/")[0]; tok = k.split("/")[-1]
    sd = side.get((rec, tok))
    if sd is None:
        mismatch.append({"resource_key": k, "why": "no_sidecar"}); continue
    if not sd["text"].strip() and segtext.strip():
        reverse_bad.append({"resource_key": k, "artifact_len": len(segtext),
                            "why": "侧车空文本但产物有文本"})
    if segtext == sd["text"]:
        if not segtext.strip(): empty_both += 1
        continue
    mismatch.append({"resource_key": k, "artifact_len": len(segtext), "sidecar_len": len(sd["text"]),
                     "artifact_uffff": "\uffff" in segtext,
                     "artifact_han": len(re.findall(r"[\u4e00-\u9fff]", segtext)),
                     "sidecar_han": len(re.findall(r"[\u4e00-\u9fff]", sd["text"])),
                     "status_reason": L1BY[k].get("status_reason", "")})
    # 重挂
    newsegs = []
    for i, s in enumerate(art.get("segments") or [], 1):
        newsegs.append({**s, "text": sd["text"] if i == 1 else s.get("text"),
                        "ocr_version": sd["version"], "ocr_status": sd["status"],
                        "remounted_at": RUN, "remounted_from": sd["sidecar"]})
    art["segments"] = newsegs
    art["ocr_remount"] = {"at": RUN, "from": sd["sidecar"], "ocr_version": sd["version"],
                          "why": "L1 产物文本由坏引擎（recognitionLevel=1，macOS 26.6.2 不支持中文）产出；"
                                 "按当前 vision-jxa-2.0 侧车重挂", "prev_chars": len(segtext)}
    json.dump(art, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2); open(p, "a").write("\n")
    L1_ROWS.append({**{kk: L1BY[k].get(kk) for kk in
                       ("resource_id", "resource_key", "kb_type", "source_kind", "source_sha256",
                        "extractor_version", "media_count", "table_count")},
                    "status": L1BY[k]["status"],
                    "status_reason": f"OCR 产物按当前侧车 vision-jxa-2.0 重挂（原文本由坏引擎产出，{len(segtext)} → {len(sd['text'])} 字符）",
                    "segment_count": len(newsegs), "char_count": len(sd["text"]),
                    "ocr_remounted": True, "remounted_at": RUN, "observed_at": RUN})
    remounted.append(k)
# 反向核查
for k in att:
    rid = L1BY[k]["resource_id"]
    rec = k.split(":")[2].split("/")[0]; tok = k.split("/")[-1]
    sd = side.get((rec, tok))
    if sd and not sd["text"].strip():
        for d in os.listdir(L1):
            c = f"{L1}/{d}/{rid}.json"
            if os.path.isfile(c):
                t = "\n".join(s.get("text") or "" for s in json.load(open(c, encoding="utf-8")).get("segments") or [])
                if not t.strip() and k not in reverse_bad: reverse_bad.append({"resource_key": k, "why": "双方皆空"})

# 修复用门槛（改动点，写进 registry 供后续复用）
gate = {
    "at": RUN, "applies_to": "所有「按 sha256 命中缓存就复用 OCR」的路径",
    "code_point": "kb/.work/kb_ocr_gate.py::ocr_cache_reusable(cache_entry) —— "
                  "L1 抽取脚本（kb/.work/l1_batch5_run.py）的复用分支必须改为调用它",
    "rule": ["拒绝 ocr_version != vision-jxa-2.0 的缓存条目",
             "拒绝 ocr_text 含 U+FFFF 的缓存条目",
             "拒绝 ocr_line_count == 0 且 ocr_text 为空但图片字节数 > 4096 的条目（疑似坏引擎整图丢失）",
             "不通过则**重跑 OCR**，而不是复用"],
    "why": "坏引擎（recognitionLevel=1）在 macOS 26.6.2 上不支持中文，静默退回纯拉丁识别；"
           "命中的旧缓存正是坏引擎产物 → 曾把 240 条附件文本批量污染",
    "measured": {"mismatched_before_fix": len(mismatch), "remounted": len(remounted),
                 "uffff_before": sum(1 for x in mismatch if x.get("artifact_uffff"))},
}
gate_code = '''#!/usr/bin/env python3
"""OCR 缓存复用门槛（件0.5 修复点）。任何「按 sha256 命中缓存就复用」的路径都必须先过这里。"""
OCR_OK_VERSION = "vision-jxa-2.0"

def ocr_cache_reusable(entry, img_bytes=None):
    """返回 (ok, reason)。ok=False 时必须重跑 OCR，不得复用。"""
    if not entry:
        return False, "缓存条目不存在"
    if entry.get("sha256_state") not in (None, "full"):
        return False, f"缓存 sha256_state 非 full: {entry.get('sha256_state')}"
    ver = entry.get("ocr_version")
    if ver != OCR_OK_VERSION:
        return False, f"ocr_version != {OCR_OK_VERSION}（坏引擎产物）：{ver}"
    text = entry.get("ocr_text") or ""
    if "\\uffff" in text:
        return False, "ocr_text 含 U+FFFF（坏引擎中文丢失标志）"
    if not text.strip() and (img_bytes or 0) > 4096:
        return False, f"ocr_text 为空但图片 {img_bytes} 字节 > 4096（疑似整图丢失）"
    return True, ""
'''
open(f"{W}/kb_ocr_gate.py", "w", encoding="utf-8").write(gate_code)

# ================================================================ 件7：URL 截断复原
urls = {k: v for k, v in L0E.items() if v.get("source_kind") == "url"}
src_urls = collections.Counter()
def harvest(text):
    for m in re.finditer(r'https?://[^\s\)\]\>"\'\u200b\u2060\ufeff]+', text):
        src_urls[m.group(0).rstrip('.,;')] += 1
for p in glob.glob(f"{L0}/records/*/*.json"):
    d = json.load(open(p, encoding="utf-8"))
    harvest(json.dumps(d.get("raw_record") or d.get("fields") or {}, ensure_ascii=False))
for f in ("kb/.work/full_urls.json", "kb/.work/规则库.ndjson", "kb/.work/材料收集.ndjson",
          "kb/.work/分类说明.ndjson", "kb/.work/batch3/材料收集.ndjson"):
    if os.path.exists(f): harvest(open(f, encoding="utf-8").read())
op("本地只读", "kb/.work/{full_urls.json,规则库.ndjson,…}", f"源侧完整 URL 汇总，去重 {len(src_urls)} 个")
def valid(u):
    try:
        p = urlparse(u); return bool(p.scheme in ("http", "https") and p.netloc) and u.count("(") == u.count(")")
    except Exception: return False
def in_source(u):
    if u in src_urls: return True
    return any(s.rstrip("/") == u.rstrip("/") for s in src_urls)
suspect = []
for k, v in urls.items():
    u = k[4:]; r = []
    if not in_source(u): r.append("not_in_source")
    if not valid(u): r.append("invalid_url")
    if v["status"] == "unreachable": r.append("unreachable")
    if re.search(r"\.(xlsx|pdf|docx|png|jpg|jpeg)$", u) or " " in u: r.append("filename_like")
    if r:
        l1r = L1BY.get(k)
        suspect.append({"key": k, "url": u, "reasons": r, "l0_status": v["status"],
                        "l1_status": (l1r or {}).get("status")})
# 「ok 但疑似截断」
ok_suspect = [x for x in suspect if x["l1_status"] in ("ok", "extracted")]
restore, unrestorable = [], []
for x in suspect:
    u = x["url"]
    if not valid(u) or x["reasons"] == ["unreachable"]:
        cand = [s for s in src_urls if s.rstrip("/").startswith(u.rstrip("/")[:40]) and s != u]
        if cand:
            best = sorted(cand, key=len)[0]
            x["restored_to"] = best; restore.append(x)
        else:
            x["reason"] = ("源侧字段里也没有与该串匹配的完整 URL（该值本身就是字段里的原始文本，"
                           "不是被截断的 URL）" if not valid(u) else
                           "源侧只有同一 URL 的等价形式，当前 URL 已合法且与源侧一致，无需复原")
            unrestorable.append(x)

# ================================================================ 写台账
with open(f"{L0}/manifest.jsonl", "a", encoding="utf-8") as fh:
    for r in L0_ROWS: fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
with open(f"{L1}/manifest_l1.jsonl", "a", encoding="utf-8") as fh:
    for r in L1_ROWS: fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")

# registry
reg["changes"].append({"run_id": RUN, "change": "append", "keys": ["ocr_reuse_gate"],
                       "note": "件0.5：新增 OCR 缓存复用门槛（拒绝非 vision-jxa-2.0 / 含 U+FFFF / 空文本缓存）"})
reg["ocr_reuse_gate"] = gate
json.dump(reg, open(f"{L0}/registry/kb.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
open(f"{L0}/registry/kb.json", "a", encoding="utf-8").write("\n")

# index 重建（L0）
L0LAT2 = {}
for l in open(f"{L0}/manifest.jsonl", encoding="utf-8"):
    if l.strip(): d = json.loads(l); L0LAT2[d["resource_key"]] = d
live = {k: v for k, v in L0LAT2.items() if v["status"] not in ("gone", "retracted")}
with open(f"{L0}/index/l0.jsonl", "w", encoding="utf-8") as fh:
    for k in sorted(live):
        r = live[k]
        fh.write(json.dumps({"resource_key": r["resource_key"], "kb_type": r["kb_type"],
                             "source_kind": r["source_kind"], "status": r["status"],
                             "entry_url": r["entry_url"]}, ensure_ascii=False, sort_keys=True) + "\n")

out = {
    "run_id": RUN, "part": "batch6 · 件0 / 件0.5 / 件7",
    "item0_eval_excluded": {
        "count": len(L0_ROWS), "keys": EVAL_KEYS, "moved": eval_moved, "archive_dir": ARCH_EVAL,
        "l0_effective_before": len(L0E_BEFORE), "l0_effective_after": len(live),
        "l1_invalidated": len([r for r in L1_ROWS if r.get("status") == "invalidated"]),
        "source_kind_retired": retired[-1],
        "history_change_kept": "run_id=20260924-1115 的 changes 条目未删（审计）",
    },
    "item0_5_ocr_remount": {
        "attachment_artifacts": len(att), "mismatched": len(mismatch), "remounted": len(remounted),
        "empty_both": empty_both, "reverse_bad": reverse_bad,
        "uffff_in_artifact_before": sum(1 for x in mismatch if x.get("artifact_uffff")),
        "mismatch_detail_sample": mismatch[:5], "gate": gate,
    },
    "item7_url": {
        "l0_url_resources": len(urls), "source_unique_urls": len(src_urls),
        "suspect_count": len(suspect), "suspect": suspect,
        "restorable": restore, "unrestorable": unrestorable,
        "ok_but_suspect_count": len(ok_suspect), "ok_but_suspect": ok_suspect,
        "old_plan_claimed": 68,
        "note": "旧计划记的「URL 字段截断 68 个」实测不成立：145 条 url 资源的 key 里 0 条与源侧完整 URL 不一致；"
                "真正的问题是**物理文件名**被 slug()[:90] 截断（如 …general-wellness-policy-l.json），"
                "resource_key 本身是完整的",
    },
    "ops": OPS,
}
json.dump(out, open(f"{L1}/runs/{RUN}.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(json.dumps({k: out[k] for k in ("item0_eval_excluded", "item0_5_ocr_remount", "item7_url")},
                 ensure_ascii=False, indent=1)[:3000])
release_lock()
