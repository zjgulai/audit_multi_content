#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_negative_image_fp.py —— 库内负面样本图的**图身份指纹索引**（2026-10-21）。

## 为什么要有它（病灶）
「库内图发到守衡必须命中」此前只靠 **OCR 文本**认图（图字节 sha 会被飞书重压缩打掉，
两套 OCR 读出来也不一样）。2026-10-21 那张德国海报实测：生产文本丢变音符号、夹水印行
⇒ 负面样本规则 0 命中 ⇒ PASS。**OCR 退化不可控，文本不能当身份。**

图身份（pHash + 像素相关）与 OCR 无关：同一张图重压缩后相关 ≥0.9988，画面不同的图 ≤0.31
（见 `_tmp-review/phash_validate2.json` 的实测）。本脚本把 339 张库内图的身份指纹落成索引，
供 `review.py --image` 的「图身份层」在评审时查。

## 数据源（只读）
  · 图字节：`kb/l1/media/media_tbld8qE92YaY38Yz_<record>/img_<seq>.png`（339 张，本地全有）
  · 记录/附件：`kb/l1/2_内部正负样本库/media_tbld8qE92YaY38Yz_<record>.json`（file_token 按 seq）
  · 图→规则：`kb/l3/candidates/negative_image_map.jsonl`（file_token → rule_ids / article_nos）

## 产物
  `kb/l3/candidates/negative_image_fp.jsonl`（一行一张图）
  {"sha256","record_id","seq","file_token","article_nos","rule_ids","phash","path"}

## 用法
  python3 kb/l8/build_negative_image_fp.py            # 重建索引
  python3 kb/l8/build_negative_image_fp.py --check    # 只校验（不写）
  python3 kb/l8/build_negative_image_fp.py --selftest # 判据自证：同一张图重压缩仍最近；异图不相近

只读 kb/l0~l2，只写 kb/l3/candidates/negative_image_fp.jsonl。
"""
import argparse
import glob
import hashlib
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
KB = os.path.dirname(HERE)
WS = os.path.dirname(KB)
L1_MEDIA = os.path.join(KB, "l1", "media")
L1_TABLE = os.path.join(KB, "l1", "2_内部正负样本库")
MAP = os.path.join(KB, "l3", "candidates", "negative_image_map.jsonl")
OUT = os.path.join(KB, "l3", "candidates", "negative_image_fp.jsonl")
PREFIX = "media_tbld8qE92YaY38Yz_"


def _pil():
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = None
    return Image


def phash_of(im, size=32, hash_size=8):
    """64→56 bit pHash（DCT 低频 + 中位数阈值）。返回值同时给 int 与 hex。"""
    import numpy as np
    w, h = im.size
    f = max(1, min(w, h) // 128)
    if f > 1:
        im = im.reduce(f)
    g = im.convert("L").resize((size, size), _pil().LANCZOS)
    a = np.asarray(g, dtype=float)
    d = np.fft.rfft2(a)[:hash_size, :hash_size][1:, :]
    med = np.median(d)
    bits = (d > med).flatten()
    n = 0
    for b in bits:
        n = (n << 1) | (1 if b else 0)
    return n, bits.size


def corr_of(im_a, im_b, s=96):
    """96×96 灰度零均值相关（同一张图重压缩后 ≈1；异图 ≤0.31）。"""
    import numpy as np
    a = np.asarray(im_a.convert("L").resize((s, s), _pil().LANCZOS), dtype=float).flatten()
    b = np.asarray(im_b.convert("L").resize((s, s), _pil().LANCZOS), dtype=float).flatten()
    a = a - a.mean()
    b = b - b.mean()
    den = (a @ a) ** 0.5 * (b @ b) ** 0.5
    return float(a @ b / den) if den else 0.0


def _media_tokens():
    """record_id → {seq: file_token}。"""
    out = {}
    for p in glob.glob(os.path.join(L1_TABLE, PREFIX + "*.json")):
        rid = os.path.basename(p)[len(PREFIX):-5]
        try:
            d = json.load(open(p, encoding="utf-8"))
        except Exception:
            continue
        toks = {}
        for m in d.get("media_refs") or []:
            if m.get("seq") is not None and m.get("file_token"):
                toks[int(m["seq"])] = m["file_token"]
        out[rid] = toks
    return out


def _rule_map():
    tok = {}
    try:
        for line in open(MAP, encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            ft = d.get("file_token")
            if not ft:
                continue
            tok[ft] = {
                "rule_ids": list(d.get("rule_ids") or []),
                "article_nos": list(d.get("article_nos") or []),
                "record_id": d.get("record_id"),
            }
    except FileNotFoundError:
        pass
    return tok


def build():
    Image = _pil()
    toks = _media_tokens()
    rmap = _rule_map()
    rows = []
    for d in sorted(glob.glob(os.path.join(L1_MEDIA, PREFIX + "*"))):
        if not os.path.isdir(d):
            continue
        rid = os.path.basename(d)[len(PREFIX):]
        for p in sorted(glob.glob(os.path.join(d, "img_*.png"))):
            try:
                seq = int(os.path.basename(p).split("_")[1].split(".")[0])
            except Exception:
                seq = None
            with open(p, "rb") as fh:
                sha = hashlib.sha256(fh.read()).hexdigest()
            try:
                im = Image.open(p).convert("RGB")
            except Exception as e:                                  # noqa: BLE001
                print("skip（读不出）：%s（%s）" % (p, e), file=sys.stderr)
                continue
            n, _bits = phash_of(im)
            ft = (toks.get(rid) or {}).get(seq)
            m = rmap.get(ft) or {}
            rows.append({
                "sha256": sha,
                "record_id": rid,
                "seq": seq,
                "file_token": ft,
                "rule_ids": m.get("rule_ids") or [],
                "article_nos": m.get("article_nos") or [],
                "phash": "%x" % n,
                "path": os.path.relpath(p, KB),
            })
    return rows


def selftest(rows):
    """判据自证：①每张图重压缩后，最近邻是自己（或同一 sha 的副本）；②异图相关 ≤0.5。"""
    Image = _pil()
    import numpy as np
    by_sha = {}
    for r in rows:
        by_sha.setdefault(r["sha256"], []).append(r)
    ok = 0
    bad = []
    for r in rows:
        im = Image.open(os.path.join(KB, r["path"])).convert("RGB")
        w, h = im.size
        buf = io.BytesIO()
        im.resize((max(1, int(w * 0.8)), max(1, int(h * 0.8))), Image.LANCZOS).save(buf, format="JPEG", quality=70)
        q = Image.open(io.BytesIO(buf.getvalue())).convert("RGB")
        nq, _ = phash_of(q)
        # 最近邻：pHash 距离最小者
        best = None
        best_d = 10 ** 9
        for r2 in rows:
            d = bin(nq ^ int(r2["phash"], 16)).count("1")
            if d < best_d:
                best_d, best = d, r2
        same = best is not None and best["sha256"] == r["sha256"]
        # 相关确认（只对最近邻）
        conf = 0.0
        if best is not None:
            lib = Image.open(os.path.join(KB, best["path"])).convert("RGB")
            conf = corr_of(q, lib)
        if same and conf >= 0.90 and best_d <= 12:
            ok += 1
        else:
            bad.append((r["path"], best["path"] if best else None, best_d, round(conf, 3)))
    print("selftest：%d/%d 命中（同图 + 相关≥0.90 + pHash≤12）" % (ok, len(rows)))
    for b in bad[:8]:
        print("  ✗", b)
    # 反向对照：随机异图相关
    import random
    random.seed(7)
    worst = 0.0
    for _ in range(60):
        a, b = random.sample(rows, 2)
        if a["sha256"] == b["sha256"]:
            continue
        ca = corr_of(Image.open(os.path.join(KB, a["path"])).convert("RGB"),
                     Image.open(os.path.join(KB, b["path"])).convert("RGB"))
        worst = max(worst, ca)
    print("反向对照：异图两两相关最大值 %.3f（要求 ≤0.5）" % worst)
    return ok == len(rows) and worst <= 0.5


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    rows = build()
    print("图片：%d 张 ｜ 唯一 sha：%d ｜ 有规则：%d"
          % (len(rows), len({r["sha256"] for r in rows}),
             sum(1 for r in rows if r["rule_ids"])))
    if a.check:
        return 0
    if a.selftest:
        return 0 if selftest(rows) else 3
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    tmp = OUT + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
    os.replace(tmp, OUT)
    print("已写 %s（%d 行）" % (OUT, len(rows)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
