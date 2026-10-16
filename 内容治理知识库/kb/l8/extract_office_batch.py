#!/usr/bin/env python3
"""把本地办公文档抽成 L1 正文：**PPTX 逐页取文字、XLSX 取单元格 + 给内嵌图走 OCR**。

## 为什么要有它（2026-10-08）

「材料收集」表里有 4 个附件从 2026-09-29 起就**已经下到本地**、L0 台账也登记了字节
（xlsx 6,223,475 / 3 个 pptx 各约 1.24 MB），但 **L1 从来没抽过** ——
每份 L1 只有 142–144 字（记录元数据），**正文一个字都没进库**。
`① ` 说明这不是「取不到」，是**抽取这一步缺了**。

## 实测到的两份真相（决定了本工具分两条路）

· **PPTX 有真文字**：3 份各 17–18 张幻灯片，约 11,500–14,000 字，
  内容是 `MOMCOZY · CREATOR CONTENT BRIEF`（达人创作简报：卖点优先级 / specs / 可用话术），
  对合规审查**直接有用**。⇒ 逐页取 `<a:t>` 文本 + 备注页。
· **XLSX 是图片型**：9 个工作表**单元格里合计只有 4 个字**，6.2 MB 全是
  **42 张内嵌 PNG**（`xl/media/`，被 9 个 `xl/drawings/drawing*.xml` 引用）。
  ⇒ 单元格抽取**必须**配 OCR，否则抽出来是空的（**这正是「抽了等于没抽」的陷阱**）。

## 锚点口径（照 `kb/l1/registry/l1.json` 的 `anchor_spec`，不自创）

    pptx → `#s.<页号>`（页号从 1 起）
    xlsx → `#<Sheet>!<单元格区域>`；内嵌图用 `#<Sheet>/#img.<序号>`

## OCR 复用

内嵌图的 OCR 走既有缓存 `kb/l1/media/_cache/<图片sha256>.json`
（`ocr_version=vision-jxa-2.0`，键 = 图片 sha256）——**命中就不重跑**。

## 用法

    python3 kb/l8/extract_office_batch.py <RUN>                    # 干跑
    python3 kb/l8/extract_office_batch.py <RUN> --apply
    python3 kb/l8/extract_office_batch.py <RUN> --apply --no-ledger
"""
# ── 解释器守卫（与 l8 其它脚本同源）──
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
import html
import json
import os
import re
import shutil
import subprocess
import sys
import time
import zipfile

RUN = next((a for a in sys.argv[1:] if not a.startswith("--")), time.strftime("%Y%m%d-%H%M"))
APPLY = "--apply" in sys.argv
NO_LEDGER = "--no-ledger" in sys.argv
BATCH = 12
CHUNK = 4000


def chunk_on_lines(text, target=CHUNK):
    """按**行边界**把 text 聚合成 <= target 的块；**逐字无损**（"".join(结果) == text）。

    ★ 2026-10-12 新增（改动单-外部标准抽取口径-20261010.md 的**真正病灶**在这里）：
      原先是 `csv[j:j+CHUNK]` 的**纯定长字符切** ⇒ 切点 100% 不落在行边界（实测 42 个切点
      落在行边界 0 个、词中间 13 个 = 31.0%），于是表的 CSV 被切在**行中／格中／词中**，
      再一路变成 L2 clause 单元、L3 `scoped_clause` 候选 —— 这就是那批
      「char_count 贴 4000、两端在词中间」的碎片的来源。
      改按行切之后，除最后一块外**每块都以 "\\n" 结尾** ⇒ 切点必然是行边界，
      **词中间在结构上不可能**。
    只有**单行本身**就超 target 时才退回字符切（这种行只能硬切，无法再按行分）。
    """
    out, cur, curlen = [], [], 0
    lines = text.split("\n")
    for i, line in enumerate(lines):
        need = len(line) + 1                      # +1 = 这一行自己的 \n
        if need > target:                         # 单行超长：先冲掉手上的，再硬切这一行
            if cur:
                out.append("\n".join(cur) + "\n")
                cur, curlen = [], 0
            for k in range(0, len(line), target):
                out.append(line[k:k + target])
            # ★ 这一行与下一行之间的 `\n` 必须补回来 —— 否则 `"".join(结果) != text`。
            #   （本函数第一版就漏了这一步，被往返断言当场抓住：`a\n` + 9000 字 + `\nb` 丢一个 `\n`。）
            if i < len(lines) - 1:
                out[-1] += "\n"
            continue
        if cur and curlen + need > target:
            out.append("\n".join(cur) + "\n")
            cur, curlen = [], 0
        cur.append(line)
        curlen += need
    if cur:
        out.append("\n".join(cur))
    return out


L1, L0 = "kb/l1", "kb/l0"
MEDIA = f"{L1}/media"
CACHE = f"{MEDIA}/_cache"
#: 「材料收集」表里那 4 个附件（record_id → (token, 扩展名)）
TARGETS = [
    ("recvvlGW0SSAeA", "L9DXbU4XxoZoTHxdKXzcTEwJnNe", "xlsx"),
    ("recvvrLzQETJyc", "IWbobAGHAoDcycxRFWNcBYd1nY6", "pptx"),
    ("recvvrLzQEjS4P", "HUngb4wwpovNsXxapcIcH2RZnyb", "pptx"),
    ("recvvrLzQErVcR", "T1tNbhPnmoq8gAxj4MZcHmX6nUc", "pptx"),
    # 在线表格（材料链接 → R3 外部标准）；L1 件已存在（wiki__BX0Qshq…），此前 no_scope/0 字
    ("BX0QshqWThhY6HtDEFCcnMpsnRc", "BX0QshqWThhY6HtDEFCcnMpsnRc", "sheets"),
]
TBL = "tblMGtPfe8ZUsEdP"


def sha_b(t):
    return hashlib.sha256(t.encode("utf-8")).hexdigest()


def sha_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for b in iter(lambda: fh.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


# ── OCR：复用缓存（键 = 图片 sha256）──
def ocr_image(path, work):
    """返回 (文本, 是否命中缓存)。命中 kb/l1/media/_cache/<sha>.json 就不重跑。"""
    data = open(path, "rb").read()
    h = hashlib.sha256(data).hexdigest()
    cf = f"{CACHE}/{h}.json"
    if os.path.exists(cf):
        try:
            c = json.load(open(cf, encoding="utf-8"))
            if c.get("ocr_version") == "vision-jxa-2.0" and c.get("sha256") == h:
                return c.get("ocr_text") or "", True
        except Exception:
            pass
    outj = f"{work}/_ocr_{h[:12]}.json"
    subprocess.run(["osascript", "-l", "JavaScript", "kb/.work/ocr.jxa.js", outj, path],
                   capture_output=True, timeout=600)
    txt = ""
    if os.path.exists(outj):
        try:
            for d in json.load(open(outj, encoding="utf-8")):
                txt += "\n".join(l.get("text", "") for l in (d.get("lines") or []))
        except Exception:
            pass
    if txt and APPLY:
        os.makedirs(CACHE, exist_ok=True)
        json.dump({"sha256": h, "sha256_state": "full", "ocr_version": "vision-jxa-2.0",
                   "ocr_text": txt, "engine": "macOS Vision(VNRecognizeTextRequest)", "at": RUN},
                  open(cf, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return txt, False


# ══════════════════════════ PPTX ══════════════════════════
def pptx_segments(path):
    z = zipfile.ZipFile(path)
    nums = sorted(int(re.search(r"(\d+)", n.split("/")[-1]).group(1))
                  for n in z.namelist() if re.match(r"ppt/slides/slide\d+\.xml$", n))

    def paras(xml):
        out = []
        for p in re.findall(r"<a:p>(.*?)</a:p>", xml, re.S):
            t = "".join(html.unescape(x) for x in re.findall(r"<a:t>(.*?)</a:t>", p, re.S))
            if t.strip():
                out.append(t.strip())
        return out

    segs, notes_pages = [], 0
    for n in nums:
        body = paras(z.read(f"ppt/slides/slide{n}.xml").decode("utf-8", "replace"))
        # ★ 2026-10-08 修：备注页编号**不与幻灯片编号一致**（实测 3 份共 51 张备注页，
        #   而我写死的 `notesSlide{n}.xml` 只对上了 3 张 ⇒ **会静默丢掉备注内容**）。
        #   正确做法：从 `ppt/slides/_rels/slide{n}.xml.rels` 反查它引用的 notesSlide。
        nt = []
        try:
            rx = z.read(f"ppt/slides/_rels/slide{n}.xml.rels").decode("utf-8", "replace")
            for tgt in re.findall(r'Target="([^"]*notesSlide\d+\.xml)"', rx):
                p2 = tgt.lstrip("/") if tgt.startswith("/") else ("ppt/" + tgt.replace("../", ""))
                if p2 in z.namelist():
                    nt = paras(z.read(p2).decode("utf-8", "replace"))
                    break
        except KeyError:
            pass
        if nt:
            notes_pages += 1
        txt = "\n".join(body)
        if nt:
            txt += "\n\n[备注]\n" + "\n".join(nt)
        if txt.strip():
            # ★ 2026-10-12：原为 `txt[:CHUNK]` + `txt[k:k+CHUNK]` 的**字符切**，且**所有块共用
            #   同一个 anchor `#s.{n}`** ⇒ ① 切在行中/词中；② 引用同一个锚点指不到具体是哪块。
            #   改为按行聚合（无损）＋ 多块时给 `#s.{n}/{i}` 区分。
            _pcs = chunk_on_lines(txt, CHUNK)
            for _i, _pc in enumerate(_pcs):
                segs.append({"kind": "paragraph", "text": _pc,
                             "anchor": f"#s.{n}" + (f"/{_i + 1}" if len(_pcs) > 1 else "")})
    return segs, len(nums), notes_pages


# ══════════════════════════ 飞书在线表格（sheets:）══════════════════════════
# 2026-10-08 加：`sheets:BX0QshqWThhY6HtDEFCcnMpsnRc`（材料链接 → R3 外部标准）此前 L1 是
# `no_scope`/0 字 —— **不是不该抽，是当时没有 sheets 抽取器**。实测 11 个子表约 17.1 万字。
# 本地没有它的字节，所以走 lark-cli 读（bot 即可，读权限现成）。
LARK = os.path.expanduser("~/.dsh/bin/lark-cli")


def _lark(*args, timeout=600):
    p = subprocess.run([LARK, *args], capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=timeout,
                       env={**os.environ, "PATH": os.path.expanduser("~/.dsh/bin") + ":" + os.environ.get("PATH", "")})
    try:
        return json.loads(p.stdout)
    except Exception:
        try:
            return json.loads(p.stderr)
        except Exception:
            return {"ok": False, "error": {"message": (p.stdout or p.stderr)[:200]}}


def sheets_segments(tok):
    """读一个飞书在线表格的所有子表，返回 (segments, 统计)。"""
    lst = _lark("sheets", "+sheet-list", "--spreadsheet-token", tok, "--profile", "dsh-kb", "--as", "bot")
    data = lst.get("data")
    items = data if isinstance(data, list) else ((data or {}).get("sheets") or [])
    segs, nrows, names = [], 0, []
    for it in items:
        sid = it.get("sheet_id") if isinstance(it, dict) else None
        if not sid:
            continue
        r = _lark("sheets", "+csv-get", "--spreadsheet-token", tok, "--sheet-id", sid,
                  "--profile", "dsh-kb", "--as", "bot")
        dd = r.get("data") or {}
        csv = dd.get("annotated_csv") or ""
        if not csv.strip():
            continue
        # sheet 名：取**整表**首个非空单元格（+sheet-list 不返回 title，这是可自证的替代）。
        # ★ 2026-10-08 修：第一版只扫前 8 行 ⇒ ①首格是 URL 的表拿到 `#https://alidocs…`；
        #   ②前 8 行全空的表回落成 sheet id（`#hccO1n`）。两条都不是人名，等于给不出锚点。
        #   现在：整表扫；URL / 超长文本 / 纯符号**不采用**，回落成 `sheet:<id>` 并**如实标注**。
        nm = None
        for line in csv.split("\n"):
            cells = [c.strip().strip('"') for c in re.sub(r"^\[row=\d+\]\s*", "", line).split(",")]
            for c in cells:
                if not c:
                    continue
                bad = (c.lower().startswith(("http://", "https://")) or len(c) > 60
                       or not any(ch.isalnum() or "\u4e00" <= ch <= "\u9fff" for ch in c))
                if bad:
                    continue
                nm = c[:40]; break
            if nm:
                break
        nm = nm or f"sheet:{sid}"
        names.append(nm)
        rng = dd.get("actual_range") or ""
        nrows += csv.count("\n") + 1
        # ★ 2026-10-12：原为 `csv[j:j+CHUNK]` 纯定长字符切 ⇒ 切在行中/格中/词中。
        #   改按行边界聚合（chunk_on_lines，逐字无损），切点必落在行边界。
        for j, piece in enumerate(chunk_on_lines(csv, CHUNK)):
            segs.append({"kind": "sheet_range", "text": piece,
                         "anchor": f"#{nm}!{rng.split('!')[-1]}" if j == 0 else f"#{nm}!（续）"})
    return segs, {"sheets": len(names), "rows": nrows, "names": names}


# ══════════════════════════ XLSX ══════════════════════════
def xlsx_segments(path, work, tok):
    import openpyxl
    segs, img_total, img_ocr, cache_hits = [], 0, 0, 0
    # ① 单元格文本（可能很少 —— 图片型表格）
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    cell_chars = 0
    for ws in wb.worksheets:
        rows = []
        for row in ws.iter_rows(values_only=True):
            cells = [("" if c is None else str(c)) for c in row]
            if any(c.strip() for c in cells):
                rows.append(" | ".join(cells).rstrip(" |"))
        if rows:
            txt = "\n".join(rows)
            cell_chars += len(txt)
            # ★ 2026-10-12：原为 `txt[:CHUNK]` = **静默截断**（表里 4000 字之后的行直接丢）。
            #   改为按行聚合的**无损**分块，续块锚点照飞书在线表的 `（续）` 惯例。
            for _i, _pc in enumerate(chunk_on_lines(txt, CHUNK)):
                segs.append({"kind": "table", "text": _pc,
                             "anchor": f"#{ws.title}!A1" if _i == 0 else f"#{ws.title}!（续）"})
    wb.close()
    # ② 内嵌图 → OCR。张 sheet ↔ drawing 的对应关系从 workbook 的 rels 推
    z = zipfile.ZipFile(path)
    media = sorted((n for n in z.namelist() if n.startswith("xl/media/")),
                   key=lambda s: int(re.search(r"(\d+)", s.split("/")[-1]).group(1))
                   if re.search(r"(\d+)", s.split("/")[-1]) else 0)
    # sheetN ↔ drawingN 映射（workbook.xml.rels + sheet rels）
    sheet_files = {}
    for n in z.namelist():
        m = re.match(r"xl/worksheets/sheet(\d+)\.xml$", n)
        if m:
            sheet_files[int(m.group(1))] = n
    # 逐个 drawing 读它引用的图片名
    draw_to_imgs = {}
    for n in z.namelist():
        m = re.match(r"xl/drawings/drawing(\d+)\.xml$", n)
        if not m:
            continue
        d = z.read(n).decode("utf-8", "replace")
        rels = f"xl/drawings/_rels/drawing{m.group(1)}.xml.rels"
        name2target = {}
        if rels in z.namelist():
            rx = z.read(rels).decode("utf-8", "replace")
            for rid, tgt in re.findall(r'Id="([^"]+)"[^>]*Target="([^"]+)"', rx):
                name2target[rid] = tgt
        imgs = []
        for rid in re.findall(r'r:embed="([^"]+)"', d):
            t = name2target.get(rid, "")
            if "media/" in t:
                imgs.append("xl/" + t.split("xl/", 1)[-1] if t.startswith("/xl/") else "xl/media/" + t.split("/")[-1])
        draw_to_imgs[int(m.group(1))] = imgs
    # 遍历 sheet，取其 drawing 的图
    for idx in sorted(sheet_files):
        sname = None
        # sheet 名从 workbook.xml 取
        try:
            wbx = z.read("xl/workbook.xml").decode("utf-8", "replace")
            names = re.findall(r'<sheet[^>]*name="([^"]+)"', wbx)
            sname = names[idx - 1] if idx - 1 < len(names) else f"sheet{idx}"
        except Exception:
            sname = f"sheet{idx}"
        d = z.read(sheet_files[idx]).decode("utf-8", "replace")
        m = re.search(r'r:id="(rId\d+)"[^>]*/>', d)
        # 用 sheet 的 rels 找 drawing
        srels = f"xl/worksheets/_rels/sheet{idx}.xml.rels"
        tgt = None
        if srels in z.namelist():
            rx = z.read(srels).decode("utf-8", "replace")
            for rid, t in re.findall(r'Id="([^"]+)"[^>]*Target="([^"]+)"', rx):
                if "drawing" in t:
                    tgt = int(re.search(r"(\d+)", t).group(1))
        if tgt is None:
            continue
        imgs = draw_to_imgs.get(tgt, [])
        for k, im in enumerate(imgs, 1):
            img_total += 1
            if im not in z.namelist():
                continue
            ext = os.path.splitext(im)[1].lower() or ".png"
            fp = f"{work}/x_{tok[:12]}_{idx}_{k}{ext}"
            with open(fp, "wb") as fh:
                fh.write(z.read(im))
            txt, hit = ocr_image(fp, work)
            cache_hits += hit
            if txt.strip():
                img_ocr += 1
                # ★ 2026-10-12：原为 `txt[:CHUNK]` = **静默截断**（OCR 超 4000 字的部分直接丢）。
                #   改为按行聚合的**无损**分块；锚点加 `/{i}` 以免多块撞同一个 anchor。
                _pcs = chunk_on_lines(txt, CHUNK)
                for _i, _pc in enumerate(_pcs):
                    segs.append({"kind": "image_ocr", "text": _pc,
                                 "anchor": f"#{sname}/#img.{k}" + (f"/{_i + 1}" if len(_pcs) > 1 else "")})
    return segs, img_total, img_ocr, cache_hits, cell_chars


# ══════════════════════════ 主流程 ══════════════════════════
lat0 = {}
for _l in open(f"{L0}/manifest.jsonl", encoding="utf-8"):
    if _l.strip():
        _r = json.loads(_l); lat0[_r["resource_key"]] = _r

plan = []
for rid, tok, ext in TARGETS:
    if ext == "sheets":                      # 在线表格：无本地字节，走 API
        plan.append({"rid": rid, "tok": tok, "ext": ext, "path": None}); continue
    hits = glob.glob(f"{L0}/attachments/材料收集/{rid}/*.{ext}")
    if not hits:
        print(f"  ✗ {rid} 本地无 .{ext}"); continue
    plan.append({"rid": rid, "tok": tok, "ext": ext, "path": hits[0]})

print(f"[{RUN}] 办公文档抽取{'【落盘】' if APPLY else '【干跑】'}｜目标 {len(plan)} 个")
report = []
for e in plan:
    t0 = time.time()
    work = f"/tmp/_office_{e['rid']}"
    shutil.rmtree(work, ignore_errors=True); os.makedirs(work, exist_ok=True)
    ent = {"rid": e["rid"], "token": e["tok"], "ext": e["ext"], "path": e["path"]}
    if e["ext"] == "pptx":
        segs, pages, nps = pptx_segments(e["path"])
        ent.update(pages=pages, notes_pages=nps)
    elif e["ext"] == "sheets":
        segs, st = sheets_segments(e["tok"])
        ent.update(**st)
    else:
        segs, imgs, iocr, hits, cellc = xlsx_segments(e["path"], work, e["tok"])
        ent.update(images=imgs, images_with_ocr=iocr, cache_hits=hits, cell_chars=cellc)
    chars = sum(len(s["text"]) for s in segs)
    ent.update(segments=len(segs), chars=chars, seconds=round(time.time() - t0, 1))
    report.append(ent)
    print(f"  {e['rid']} ({e['ext']}) → {len(segs)} 段 / {chars} 字"
          + (f"｜{ent.get('pages')} 页（备注 {ent.get('notes_pages')}）" if e['ext'] == 'pptx'
             else f"｜内嵌图 {ent.get('images')}（有 OCR {ent.get('images_with_ocr')}，"
                  f"命中缓存 {ent.get('cache_hits')}）｜单元格 {ent.get('cell_chars')} 字")
          + f"｜{ent['seconds']}s", flush=True)
    if not APPLY or chars < 100:
        if APPLY:
            print(f"     ⚠️ 抽出的字太少（{chars}）⇒ 不写产物，免得留下「抽了等于没抽」的空件")
        continue
    # 写 L1 产物
    # 产物名前缀实测为 `sheets__`（我第一版猜成 `wiki__` ⇒ 找不到产物、没写进去）
    art = (glob.glob(f"{L1}/*/sheets__{e['tok']}.json") if e["ext"] == "sheets"
           else glob.glob(f"{L1}/*/bitable__{TBL}__{e['rid']}.json"))
    if not art:
        print(f"     ⛔ 找不到 L1 产物 bitable__{TBL}__{e['rid']}.json ⇒ 未写")
        continue
    d = json.load(open(art[0], encoding="utf-8"))
    new = dict(d)
    new.update({"source_sha256": sha_b("".join(x["text"] for x in segs)),
                "extractor_version": f"l1-0.1+office-{RUN}", "status": "ok",
                "status_reason": (f"办公文档正文抽取（{'飞书在线表格：逐子表读 CSV' if e['ext']=='sheets' else ('PPTX 逐页取文字' if e['ext']=='pptx' else 'XLSX 单元格 + 内嵌图 Vision OCR')}）："
                                  f"{len(segs)} 段 / {chars} 字；原件 {e['path']}（未改动）"),
                "segments": segs, "segment_count": len(segs), "char_count": chars,
                "office_local_path": e["path"], "observed_at": RUN,
                "extracted_from": ("pptx_text" if e["ext"] == "pptx"
                                   else ("feishu_sheets_csv" if e["ext"] == "sheets"
                                         else "xlsx_cells+embedded_ocr"))})
    tmp = art[0] + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(new, fh, ensure_ascii=False, indent=1)
    json.load(open(tmp, encoding="utf-8"))
    os.replace(tmp, art[0])
    print(f"     ✓ 已写 {os.path.basename(art[0])}", flush=True)
    shutil.rmtree(work, ignore_errors=True)

json.dump({"run": RUN, "kind": "office_doc_extract", "apply": APPLY, "no_ledger": NO_LEDGER,
           "results": report}, open(f"kb/l8/runs/{RUN}-office-extract.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print(f"  [报告] kb/l8/runs/{RUN}-office-extract.json")
