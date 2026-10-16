#!/usr/bin/env python3
"""4 本扫描版 PDF → 逐页转图 → macOS Vision OCR → 回写 L1 正文。

背景：20260929-2110 从飞书取回的 26 本外部资料 PDF 里，4 本无文本层（扫描件，约 260 页）：
      HBVpwOTQ(66页) / VX5fwLDZ(63页) / XhrkwZQZ(66页) / ZYoywsxY(65页)
流程：pdftoppm -r 150 -png 逐页转图 → osascript Vision 批量识别 → 拼正文写回 L1 产物 →
      更新 L0 台账（新增 sha256_input=pdf_ocr_v1）→ 删页图（只留文本）
用法：python3 kb/l8/ocr_scanned_pdfs.py 20260929-2200 [--apply] [--dpi 150] [--batch 12]
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
import re
import shutil
import subprocess
import sys
import time

RUN = sys.argv[1] if len(sys.argv) > 1 else "20260929-2200"
APPLY = "--apply" in sys.argv
DPI = int(sys.argv[sys.argv.index("--dpi") + 1]) if "--dpi" in sys.argv else 150
BATCH = int(sys.argv[sys.argv.index("--batch") + 1]) if "--batch" in sys.argv else 12
# 2026-10-08 补：① --only 外科式选本（否则每次都会把 15 本扫描件全部重 OCR 一遍，
#   其中 14 本早在 20260929-2200/2305 就做完了）；② --no-ledger 只写 L1 正文、
#   不追加 L0 台账 —— 供「先落 L1/L2/L3、台账最后落」的排序使用。
ONLY = [t for t in (sys.argv[sys.argv.index("--only") + 1].split(",") if "--only" in sys.argv else []) if t]
NO_LEDGER = "--no-ledger" in sys.argv
# 2026-10-08 补 --embedded：**poppler 读不了的 PDF** 走「抽内嵌页图」而不是 pdftoppm 渲染。
# 实测（本批 4 本扫描件）：poppler 只能渲染 FBjbwZbOai（608 页），另 3 本
#   G5Gnwrzvwi / VFlhwj2ITi / CDPHwzbbZi 全部报 `Couldn't read xref table` ⇒ 转图 **0 张**
#   ⇒ 若照原路跑，这 3 本会**静默产出 0 字**（脚本不报错，只写 0 字产物）。
# 抽内嵌页图为什么更好：这些扫描页每页就是**一整张内嵌 JPEG**（/DCTDecode），
#   1535×2382 px 铺在 368×571 pt 页面上 ⇒ 当量约 **300 DPI**，
#   而 `pdftoppm -r 150` 反而是**降采样**；且抽图是纯字节搬运，省掉整段渲染。
# 质量控制（不靠猜）：抽出的图**送同一台 Vision、同一段代码**；
#   已逐页看图核对过 3 页（目录页识别全对 / 章节扉页 9 字 / 全白页 0 字，均为真值）。
EMBEDDED = "--embedded" in sys.argv


def extract_embedded_pages(pdf, work):
    """按页抽内嵌图，落盘成 jpg/png，返回按页序的文件名列表（缺图的页留 None 占位）。"""
    from pypdf import PdfReader
    rd = PdfReader(pdf)
    out = []
    for pg in rd.pages:
        best = None
        try:
            for im in pg.images:
                if best is None or len(im.data) > len(best.data):
                    best = im
        except Exception:
            best = None
        if best is None:
            out.append(None); continue
        ext = os.path.splitext(best.name)[1].lower() or ".png"
        if ext not in (".jpg", ".jpeg", ".png"):
            ext = ".png"
        fp = f"{work}/e{len(out)+1:04d}{ext}"
        with open(fp, "wb") as fh:
            fh.write(best.data)
        out.append(fp)
    return out
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
        # 注意：PDF 文件名里的 token 是**截断到 24 字符**的（L1 件名里才是全量 token），
        # 所以两侧都截断再比 —— 直接 ==/startswith 会一个都匹配不上（2026-10-08 实测踩过）。
        if len(txt) < 200 and (not ONLY or any(tok[:24] == o[:24] for o in ONLY)):
            targets.append((tok, p, len(rd.pages)))
    except Exception as e:
        print(f"  ✗ {tok} 读取失败 {e}")
print(f"[{RUN}] 待 OCR 扫描件 {len(targets)} 本 / 共 {sum(t[2] for t in targets)} 页", flush=True)

# ★ 台账**读**与台账**写**是两件事（2026-10-08 修，踩过）：
#   `--no-ledger` 的语义是「不**写**台账」，而我第一版把**读**也一起关掉了 ⇒
#   `lat` 为空 ⇒ 下面 `key = next((k for k in lat if k.endswith(tok)), None)` 恒为 None
#   ⇒ `art_p` 为 None ⇒ **L1 正文一个字节都不写**，而脚本不报错、只把 0 字产物留着。
#   实测代价：CDPHwzbbZi 217 页 Vision 明明读出约 12.7 万字（我独立复算过前 24 页 = 14024 字），
#   却因为这条把正文全丢了。⇒ `lat` 必须**无条件读**（它只喂产物查找），`--no-ledger` 只挡 append。
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
    if EMBEDDED:
        imgs = extract_embedded_pages(pdf, work)
        missing = sum(1 for x in imgs if x is None)
        imgs = [x for x in imgs if x]
        print(f"  {tok}: {pages} 页 → 抽内嵌图 {len(imgs)} 张"
              f"（无图页 {missing}）（{time.time()-t0:.0f}s）", flush=True)
        if not imgs:                     # 兜底：抽不到就退回渲染，别静默产 0 字
            print("    ⚠️ 内嵌图 0 张 ⇒ 退回 pdftoppm 渲染", flush=True)
            subprocess.run(["pdftoppm", "-r", str(DPI), "-png", pdf, f"{work}/p"],
                           capture_output=True, timeout=7200)
            imgs = sorted(glob.glob(f"{work}/p*.png"))
            print(f"    退回渲染后获图 {len(imgs)} 张", flush=True)
    else:
        subprocess.run(["pdftoppm", "-r", str(DPI), "-png", pdf, f"{work}/p"],
                       capture_output=True, timeout=7200)
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
        # ★ 可见性守卫（2026-10-08 加）：读出正文却找不到产物/不回写，必须**喊出来**。
        #   加它的直接原因：`--no-ledger` 误关台账读取那次，217 页 12.7 万字正文被静默丢弃，
        #   而屏幕上只有一行「✓ 完成：0 字」—— 看起来像"这书没文字"，其实是回写没接上。
        if not art_p:
            print(f"  ⛔ {tok}：读出 {len(text)} 字，但**找不到对应 L1 产物**（key={key}）"
                  f"⇒ 正文未回写！请查 arts/lat 的匹配口径", flush=True)
        if art_p:
            old = json.load(open(art_p, encoding="utf-8"))
            segs = [{"kind": "paragraph", "text": text[j:j + 4000], "anchor": f"#l.1-{n}"}
                    for n, j in enumerate(range(0, len(text), 4000), 1)]
            new = dict(old)
            new.update({"source_sha256": sha(text), "extractor_version": "l1-0.1+pdfvision-20260929",
                        "status": "ok",
                        "status_reason": (f"扫描件 OCR："
                                          f"{'抽内嵌页图（/DCTDecode 原字节，当量约 300dpi）' if EMBEDDED else f'pdftoppm {DPI}dpi 转图'}"
                                          f" + macOS Vision 逐页识别，{pages} 页 → {len(text)} 字"),
                        "segments": segs, "segment_count": len(segs), "char_count": len(text),
                        "observed_at": RUN, "ocr_pages": pages,
                        "ocr_dpi": (None if EMBEDDED else DPI),
                        "ocr_pages_source": ("embedded_image" if EMBEDDED else "pdftoppm_render")})
            tmp = art_p + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(new, fh, ensure_ascii=False, indent=1)
            json.load(open(tmp, encoding="utf-8"))
            os.replace(tmp, art_p)
        if key and not NO_LEDGER:
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

json.dump({"run": RUN, "kind": "scanned_pdf_ocr", "dpi": DPI, "embedded": EMBEDDED, "only": ONLY,
           "ledger": ("deferred（--no-ledger：只写 L1 正文）" if NO_LEDGER else "written"),
           "results": report},
          open(f"kb/l8/runs/{RUN}-pdf-ocr.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"[完成] 报告 kb/l8/runs/{RUN}-pdf-ocr.json", flush=True)
