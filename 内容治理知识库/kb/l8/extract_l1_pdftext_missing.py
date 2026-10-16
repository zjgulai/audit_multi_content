#!/usr/bin/env python3
"""把「本地已有 PDF 原件、但 L1 件是 0 字」的产物**用 PDF 文本层**补出来（不是 OCR）。

## 为什么要有这个脚本（2026-10-08 实测踩出来的）

2026-10-08 从飞书取回 7 本外部资料 PDF 后，L1 件**全部是 0 字**，状态写着
`forbidden`（momcozy-in 5 本）或 `no_scope`（hapa8fkuicz 2 本）—— 那是**网页/wiki 直读**
那一遍留下的结论：bot 读不了这两个 wiki 节点的正文。

当时我据此判断「7 本全是扫描件，都要 OCR」。**这个判断是错的**，两处翻车：

  ① 判据用错了工具：`pdftotext -f 1 -l 5` 对其中几本返回 0 字，我就当成「无文本层」。
     真相是那几本 PDF 的**目录结构 poppler 读不了**（例如 Zqz7w1W9Zi 是 calibre 3.23 生成的，
     pdfinfo 直接报 `Couldn't find trailer dictionary`），而 **pypdf 读得动**。
  ② 判「扫描件」要看**全文**，不能只看前 5 页：`G5Gnwrzvwi` 前 5 页 0 字、全文却有 1354 字，
     `CDPHwzbbZi` 前 5 页 0 字、全文 110 字 —— 它们**是**扫描件（正确），
     但 `Acl7w1Ax3i`（WHO 产后护理指南，813,752 字）前 5 页就有 9676 字，
     差点被我一起丢进 OCR（把电子书当扫描件 OCR，等于用识别误差替换干净的排版文本）。

实测结论（7 本，pypdf 全量）：

    Zqz7w1W9ZiP7i8kXNTGc9cBGnVb   1303 页  626,416 字  ← 文本层，走本脚本
    Acl7w1Ax3iAY6GkW8rmcF5Bknkg    242 页  813,752 字  ← 文本层，走本脚本
    XVgVw8WZ3iZsTkkqEpwcbwjJnPh     47 页  254,553 字  ← 文本层，走本脚本
    FBjbwZbOaiLjeSk9M4rciLPrn7e    608 页        0 字  ← 真扫描件，走 ocr_scanned_pdfs.py
    G5Gnwrzvwi2a24k4eonccg9BnJg   289 页    1,354 字  ← 真扫描件
    VFlhwj2ITiexpxk463vczG34ndf   247 页        0 字  ← 真扫描件
    CDPHwzbbZi3RRnkdyHjcoxKQnm0   218 页      110 字  ← 真扫描件

## 口径（四条，缺一条就不动这个产物）

  ① L1 件 `char_count` 为 0 且 `segments` 为空 —— **绝不覆盖任何已有正文**；
  ② 本地有对应 PDF 原件（`--pdf-dir` 下 `<token>.pdf`），且**字节 sha256 与 L0 台账一致**；
  ③ 全文重抽字数 ≥ `--min-chars`（默认 200），否则判为扫描件并**跳过**（该走 OCR）；
  ④ 有 `--only` 时 token 必须点名命中（24 字符截断比较 —— PDF 文件名里的 token 是截断的）。

## 安全

  · L0 原件**只读**：只读字节，不写不改（原件是源，动了就没法回源）；
  · 旧产物先归档 `kb/l1/_archive/pdftext-fill-<RUN>/` 再写新的；
  · 写盘用 os.replace（先写 .tmp、回读自检、再替换），不留半成品；
  · `--no-ledger` 时**只写 L1 正文、不碰任何台账** —— 供「先落 L1/L2/L3、台账最后落」的排序使用。

## 用法

    python3 kb/l8/extract_l1_pdftext_missing.py <RUN>                          # 干跑
    python3 kb/l8/extract_l1_pdftext_missing.py <RUN> --apply
    python3 kb/l8/extract_l1_pdftext_missing.py <RUN> --apply --no-ledger
    python3 kb/l8/extract_l1_pdftext_missing.py <RUN> --only <token>[,<token>…]
"""
# ── 解释器守卫（与 l8 其它脚本同源）：不合格就用 kb/.kb-python 指定的解释器重跑自己 ──
import os as _os, sys as _sys
if not _os.environ.get("KB_INTERP_OK"):
    _d = _os.path.dirname(_os.path.abspath(__file__)); _cfg = None
    while True:
        _p = _os.path.join(_d, ".kb-python")
        if _os.path.isfile(_p):
            _cfg = _p; break
        _q = _os.path.dirname(_d)
        if _q == _d: break
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
import shutil
import sys
import time

RUN = next((a for a in sys.argv[1:] if not a.startswith("--")), time.strftime("%Y%m%d-%H%M"))
APPLY = "--apply" in sys.argv
NO_LEDGER = "--no-ledger" in sys.argv
ONLY = [t for t in (sys.argv[sys.argv.index("--only") + 1].split(",") if "--only" in sys.argv else []) if t]
MIN_CHARS = int(sys.argv[sys.argv.index("--min-chars") + 1]) if "--min-chars" in sys.argv else 200
PDF_DIR = sys.argv[sys.argv.index("--pdf-dir") + 1] if "--pdf-dir" in sys.argv else "kb/l0/attachments/外部资料库"
CHUNK = 4000
L1, L0 = "kb/l1", "kb/l0"


def sha(t):
    return hashlib.sha256(t.encode("utf-8")).hexdigest()


def fsha(p):
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for b in iter(lambda: fh.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def segsum(d):
    segs = d.get("segments")
    return sum(len(s.get("text") or "") for s in segs if isinstance(s, dict)) if isinstance(segs, list) else 0


# ── L0 台账：每个 resource_key 的**最新**行（口径与库内其它脚本一致：后写覆盖前写）──
lat0 = {}
for _l in open(f"{L0}/manifest.jsonl", encoding="utf-8"):
    if _l.strip():
        _r = json.loads(_l); lat0[_r["resource_key"]] = _r

# 可续跑：L1 台账行只许用既有键
L1_KEYS = set()
for _l in open(f"{L1}/manifest_l1.jsonl", encoding="utf-8"):
    if _l.strip():
        L1_KEYS |= set(json.loads(_l))

# ── 选目标：只碰「0 字 + 本地有 PDF」的产物 ──
targets, skipped = [], []
for p in sorted(glob.glob(f"{L1}/*/*.json")):
    if "/_archive/" in p:
        continue
    try:
        d = json.load(open(p, encoding="utf-8"))
    except Exception:
        continue
    tok = os.path.basename(p)[:-5].rsplit("_", 1)[-1]
    if ONLY and tok[:24] not in [o[:24] for o in ONLY]:
        continue
    if (d.get("char_count") or 0) != 0 or segsum(d) != 0:
        skipped.append((tok, "已有正文，不动")); continue
    pdf = f"{PDF_DIR}/{tok}.pdf"
    if not os.path.exists(pdf):
        skipped.append((tok, "本地无 PDF 原件")); continue
    targets.append((p, d, tok, pdf))

print(f"[{RUN}] PDF 文本层补正文{'【落盘】' if APPLY else '【干跑】'}"
      f"｜候选 {len(targets)} 个｜台账 {'deferred（--no-ledger）' if NO_LEDGER else '本轮同时落'}")

report, new_l1, new_l0, archived = [], [], [], []
for p, d, tok, pdf in targets:
    t0 = time.time()
    from pypdf import PdfReader
    import pypdf
    try:
        rd = PdfReader(pdf)
        n_pages = len(rd.pages)
        full = "".join((pg.extract_text() or "") for pg in rd.pages)
    except Exception as e:
        print(f"  ✗ {tok} 读取失败：{type(e).__name__}: {e}")
        report.append({"artifact": p, "token": tok, "ok": False, "error": f"{type(e).__name__}: {e}"})
        continue
    h_full = sha(full)
    row = lat0.get(d.get("resource_key")) or {}
    pdf_sha = fsha(pdf)
    declared_pdf_sha = row.get("sha256") if row.get("sha256_input") == "file_bytes" else None
    ent = {"artifact": p, "token": tok, "pdf": pdf, "pages": n_pages, "chars": len(full),
           "empty_pages": sum(1 for _s in full.split("\f") if not _s.strip()),
           "pdf_sha256": pdf_sha, "pdf_sha_matches_ledger": (declared_pdf_sha == pdf_sha)
           if declared_pdf_sha else None,
           "pypdf_version": pypdf.__version__, "seconds": round(time.time() - t0, 1),
           "ledger_row_sha256_input": row.get("sha256_input")}
    if len(full) < MIN_CHARS:
        # 判为扫描件：本脚本**不**处理，交 ocr_scanned_pdfs.py
        ent["ok"] = False
        ent["verdict"] = f"全文仅 {len(full)} 字 < {MIN_CHARS} ⇒ 判为扫描件，应交 OCR（本脚本不动）"
        report.append(ent)
        print(f"  – {tok}：{ent['verdict']}")
        continue
    segs = [{"kind": "paragraph", "text": full[j:j + CHUNK], "anchor": f"#l.1-{n}"}
            for n, j in enumerate(range(0, len(full), CHUNK), 1)]
    ent["ok"] = True
    ent["segments"] = len(segs)
    report.append(ent)
    print(f"  {tok}: {n_pages} 页 → {len(full)} 字 / {len(segs)} 段"
          f"｜原件 sha {'与台账一致 ✓' if ent['pdf_sha_matches_ledger'] else ('待核' if ent['pdf_sha_matches_ledger'] is None else '✗ 不一致')}"
          f"｜{ent['seconds']}s")

    if not APPLY:
        continue
    arch = f"{L1}/_archive/pdftext-fill-{RUN}"
    os.makedirs(arch, exist_ok=True)
    shutil.copy2(p, os.path.join(arch, os.path.basename(p)))
    archived.append(os.path.join(arch, os.path.basename(p)))
    new = dict(d)
    new.update({
        "source_sha256": h_full,
        "extractor_version": f"l1-0.1+pdftext-fill-{RUN}",
        "status": "ok",
        "status_reason": (f"2026-10-08 补正文：本产物此前是 0 字（{d.get('status')} —— 那是"
                          f"「wiki 正文直读」那一遍的结论，bot 读不到该节点正文）。"
                          f"原件 PDF 其实一直在本地（{pdf}），本次用 pypdf {pypdf.__version__} "
                          f"抽出 {len(full)} 字并分 {len(segs)} 段（{n_pages} 页，原件未改动）。"
                          f"未做 OCR —— 该 PDF 有可用的文本层，OCR 只会引入识别误差"),
        "char_count": len(full), "segment_count": len(segs), "segments": segs,
        "pdf_local_path": pdf, "pdf_pages": n_pages,
        "pdf_sha256": pdf_sha, "pdf_sha256_matches_l0": ent["pdf_sha_matches_ledger"],
        "extracted_from": "pdf_text_layer", "observed_at": RUN,
    })
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(new, fh, ensure_ascii=False, indent=1)
    json.load(open(tmp, encoding="utf-8"))          # 写完先自检能读
    os.replace(tmp, p)
    new_l1.append({"resource_id": d.get("resource_id"), "resource_key": d.get("resource_key"),
                   "kb_type": d.get("kb_type"), "source_kind": d.get("source_kind"),
                   "source_sha256": h_full, "extractor_version": new["extractor_version"],
                   "status": "ok", "status_reason": new["status_reason"],
                   "segment_count": len(segs), "char_count": len(full),
                   "media_count": d.get("media_count") or 0, "table_count": d.get("table_count") or 0,
                   "observed_at": RUN, "reconciled_by_run": RUN})
    if not NO_LEDGER and row:
        n = dict(row)
        n.update({"sha256": h_full, "sha256_prev": row.get("sha256"),
                  "sha256_input": "pdf_text_layer_v1", "sha256_state": "full",
                  "observed_at": RUN, "change": "l0_pdf_text_layer",
                  "status_reason": (f"L1 正文由本地 PDF 文本层补出（{n_pages} 页 → {len(full)} 字）；"
                                    f"原件字节未动 {pdf}")})
        new_l0.append(n)

if APPLY and new_l1:
    with open(f"{L1}/manifest_l1.jsonl", "a", encoding="utf-8") as fh:
        for r in new_l1:
            extra = set(r) - L1_KEYS
            assert not extra, f"L1 台账出现新键 {extra}（不许乱造键）"
            fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
    print(f"\n  [写入] L1 产物 {len([e for e in report if e.get('ok')])} 个｜L1 台账 +{len(new_l1)}"
          f"｜L0 台账 +{len(new_l0)}{'（--no-ledger，本轮不落）' if NO_LEDGER else ''}"
          f"｜旧产物归档 {len(archived)} 份 → {L1}/_archive/pdftext-fill-{RUN}/")
    if new_l0:
        with open(f"{L0}/manifest.jsonl", "a", encoding="utf-8") as fh:
            for r in new_l0:
                fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
elif APPLY:
    print("\n  没有可写入的目标")
else:
    print("\n  [干跑] 未落盘。加 --apply 才写")

json.dump({"run_id": RUN, "kind": "l1_pdftext_fill_from_local_pdf", "apply": APPLY,
           "no_ledger": NO_LEDGER, "min_chars": MIN_CHARS, "only": ONLY,
           "targets": len(targets), "filled": sum(1 for e in report if e.get("ok")),
           "chars_total": sum(e.get("chars") or 0 for e in report),
           "skipped_no_pdf_or_has_text": skipped, "results": report},
          open(f"kb/l8/runs/{RUN}-l1-pdftext-fill.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print(f"  [报告] kb/l8/runs/{RUN}-l1-pdftext-fill.json")
