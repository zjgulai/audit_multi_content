#!/usr/bin/env python3
"""4 本扫描版 PDF → 逐页转图 → macOS Vision OCR → 回写 L1 正文。

背景：20260929-2110 从飞书取回的 26 本外部资料 PDF 里，4 本无文本层（扫描件，约 260 页）：
      HBVpwOTQ(66页) / VX5fwLDZ(63页) / XhrkwZQZ(66页) / ZYoywsxY(65页)
流程：pdftoppm -r 150 -png 逐页转图 → osascript Vision 批量识别 → 拼正文写回 L1 产物 →
      更新 L0 台账（新增 sha256_input=pdf_ocr_v1）→ 删页图（只留文本）
用法：python3 kb/l8/ocr_scanned_pdfs.py 20260929-2200 [--apply] [--dpi 150] [--batch 12]
"""
import glob
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time

RUN = sys.argv[1] if len(sys.argv) > 1 else "20260929-2200"
APPLY = "--apply" in sys.argv
DPI = int(sys.argv[sys.argv.index("--dpi") + 1]) if "--dpi" in sys.argv else 150
BATCH = int(sys.argv[sys.argv.index("--batch") + 1]) if "--batch" in sys.argv else 12
PDF_DIR = "kb/l0/attachments/外部资料库"
def sha(t): return hashlib.sha256(t.encode("utf-8")).hexdigest()

# 找出需要 OCR 的（文本层 <200 字）
targets = []
for p in sorted(glob.glob(f"{PDF_DIR}/*.pdf")):
    tok = os.path.basename(p)[:-4]
    try:
        from pypdf import PdfReader
        rd = PdfReader(p)
        txt = "".join((pg.extract_text() or "") for pg in rd.pages[:5])
        if len(txt) < 200:
            targets.append((tok, p, len(rd.pages)))
    except Exception as e:
        print(f"  ✗ {tok} 读取失败 {e}")
print(f"[{RUN}] 待 OCR 扫描件 {len(targets)} 本 / 共 {sum(t[2] for t in targets)} 页", flush=True)

lat = {}
for line in open("kb/l0/manifest.jsonl", encoding="utf-8"):
    if line.strip():
        r = json.loads(line)
        lat[r["resource_key"]] = r
arts = {}
for f in glob.glob("kb/l1/*/url__*.json"):
    try:
        d = json.load(open(f, encoding="utf-8"))
        arts[d["resource_key"]] = f
    except Exception:
        pass

report = []
for tok, pdf, pages in targets:
    t0 = time.time()
    work = f"/tmp/_ocrpdf_{tok}"
    shutil.rmtree(work, ignore_errors=True)
    os.makedirs(work, exist_ok=True)
    subprocess.run(["pdftoppm", "-r", str(DPI), "-png", pdf, f"{work}/p"],
                   capture_output=True, timeout=1800)
    imgs = sorted(glob.glob(f"{work}/p*.png"))
    print(f"  {tok}: {pages} 页 → 转图 {len(imgs)} 张（{time.time()-t0:.0f}s）", flush=True)
    page_texts = []
    for i in range(0, len(imgs), BATCH):
        chunk = imgs[i:i + BATCH]
        outj = f"{work}/_b{i//BATCH:03d}.json"
        subprocess.run(["osascript", "-l", "JavaScript", "kb/.work/ocr.jxa.js", outj, *chunk],
                       capture_output=True, timeout=900)
        by = {}
        if os.path.exists(outj):
            try:
                for d in json.load(open(outj, encoding="utf-8")):
                    by[d.get("file")] = "\n".join(l.get("text", "") for l in (d.get("lines") or []))
            except Exception:
                pass
        for img in chunk:
            page_texts.append(by.get(img, ""))
        print(f"    批 {i//BATCH+1}：{len(chunk)} 页 → 累计 {sum(len(t) for t in page_texts)} 字"
              f"（{time.time()-t0:.0f}s）", flush=True)
    text = "\n\n".join(f"[p{n}]\n{t}" for n, t in enumerate(page_texts, 1) if t.strip())
    ent = {"token": tok, "pages": pages, "chars": len(text), "seconds": round(time.time() - t0)}
    report.append(ent)
    if APPLY and len(text) >= 200:
        key = next((k for k in lat if k.endswith(tok)), None)
        art_p = arts.get(key) if key else None
        if art_p:
            old = json.load(open(art_p, encoding="utf-8"))
            segs = [{"kind": "paragraph", "text": text[j:j + 4000], "anchor": f"#l.1-{n}"}
                    for n, j in enumerate(range(0, len(text), 4000), 1)]
            new = dict(old)
            new.update({"source_sha256": sha(text), "extractor_version": "l1-0.1+pdfvision-20260929",
                        "status": "ok",
                        "status_reason": f"2026-09-29 扫描件 OCR：pdftoppm {DPI}dpi 转图 + macOS Vision 逐页识别，"
                                         f"{pages} 页 → {len(text)} 字",
                        "segments": segs, "segment_count": len(segs), "char_count": len(text),
                        "observed_at": RUN, "ocr_pages": pages, "ocr_dpi": DPI})
            tmp = art_p + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(new, fh, ensure_ascii=False, indent=1)
            json.load(open(tmp, encoding="utf-8"))
            os.replace(tmp, art_p)
        if key:
            row = lat[key]
            n = dict(row)
            n.update({"sha256": sha(text), "sha256_prev": row.get("sha256"),
                      "sha256_input": "pdf_ocr_v1", "sha256_state": "full", "observed_at": RUN,
                      "change": "l0_pdf_ocr_text",
                      "status_reason": f"扫描件 OCR（Vision，{pages} 页 → {len(text)} 字）；原件字节仍存 {row.get('local_path')}"})
            with open("kb/l0/manifest.jsonl", "a", encoding="utf-8") as fh:
                fh.write(json.dumps(n, ensure_ascii=False, sort_keys=True) + "\n")
    shutil.rmtree(work, ignore_errors=True)      # 页图用完即删
    print(f"  ✓ {tok} 完成：{ent['chars']} 字 / {ent['seconds']}s（页图已删）", flush=True)

json.dump({"run": RUN, "kind": "scanned_pdf_ocr", "dpi": DPI, "results": report},
          open(f"kb/l8/runs/{RUN}-pdf-ocr.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"[完成] 报告 kb/l8/runs/{RUN}-pdf-ocr.json", flush=True)
