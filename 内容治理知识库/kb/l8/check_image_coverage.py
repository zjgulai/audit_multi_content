#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_image_coverage.py —— 「源侧有图、库里到底有没有」的**唯一判据**（L0 字节 + L1 OCR）。

为什么必须有它（2026-10-20 实测，不是预防性设计）
────────────────────────────────────────────────
库里有 8 个层闸门、四道审计，但**没有任何一条在比对三份 token 集合**：
**源侧图片 token / L0 字节 / L1 OCR**。
实测后果（同一天）：源表 339 张，L0 只 304 张 ——
  · 30 张停在 `sha256_state=metadata_only`（台账有行、字节从来没下过）；
  · 5 张在新增记录上连台账行都没有（`ingest_l0_new_records.py` 的附件处理是 `--attachments` 独立模式）；
而日更摘要第 ③ 类「图片附件」写的是**「已对齐」**。**看起来是绿的。**

判据形状（只做三件事）
──────────────────────
  ① 取「源侧」token 集：默认读 **L0 记录**（离线可跑）；给 `--live <ndjson>` 则读飞书实拉快照（更严）
  ② 取 L0 字节集：`kb/l0/attachments/<表>/<rid>/<token>.png` 的真实文件名
  ③ 取 L1 OCR 集：`kb/l1/2_内部正负样本库/media_<table>_<rid>.json` 的 `media_refs[].file_token`
  三个集合做差；**任一非空 ⇒ 退出码 3**，并逐条点名 `record_id / file_token / 缺在哪一层`。

边界
────
  · 只读：不下载、不写库、不建目录（快照只落 /tmp）。
  · 「OCR 文本为空」不算缺口 —— 图上本来没字是合法结果；**缺的是"这张图没进过 OCR"**。
  · `--selftest` 是**反向对照**：造两种缺口（源多一张 / L1 少一张），判据必须精确变红；
    再造一份全齐的，必须变绿。少了这一半，这就是一条恒绿的注释。

用法
────
  python3 kb/l8/check_image_coverage.py
  python3 kb/l8/check_image_coverage.py --live kb/l8/_stage/feishu-align/<RUN>/tbld8qE92YaY38Yz.ndjson
  python3 kb/l8/check_image_coverage.py --selftest
"""
# ── 解释器守卫（与库内其它 l8 脚本同一口径）────────────────────────────────
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

import json
import os
import sys
import tempfile

TABLE_ID = "tbld8qE92YaY38Yz"
TABLE_NAME = "负面样本"
FIELD = "图片素材"

L0_REC_DIR = "kb/l0/records/负面样本"
L0_ATT_DIR = "kb/l0/attachments/负面样本"
L1_MEDIA_DIR = "kb/l1/2_内部正负样本库"
L1_PREFIX = f"media_{TABLE_ID}_"


def tokens_from_records(rec_dir):
    """L0 记录 → {record_id: set(token)}。"""
    out = {}
    if not os.path.isdir(rec_dir):
        return out
    for fn in sorted(os.listdir(rec_dir)):
        if not fn.endswith(".json"):
            continue
        try:
            doc = json.load(open(os.path.join(rec_dir, fn), encoding="utf-8"))
        except Exception:
            continue
        rid = doc.get("record_id")
        if not rid:
            continue
        fv = (doc.get("fields") or {}).get(FIELD) or {}
        toks = {a.get("file_token") for a in (fv.get("value") or []) if isinstance(a, dict)}
        toks.discard(None)
        if toks:
            out[rid] = toks
    return out


def tokens_from_live(ndjson_path):
    """飞书实拉快照（record-list ndjson）→ {record_id: set(token)}。"""
    out = {}
    for line in open(ndjson_path, encoding="utf-8"):
        if not line.strip():
            continue
        rec = json.loads(line)
        rid = rec.get("record_id")
        toks = {a.get("file_token") for a in (rec.get(FIELD) or []) if isinstance(a, dict)}
        toks.discard(None)
        if rid and toks:
            out[rid] = toks
    return out


def tokens_from_l0_bytes(att_dir):
    """L0 附件目录 → {record_id: set(token)}（以**真实文件名**为准，不信台账）。"""
    out = {}
    if not os.path.isdir(att_dir):
        return out
    for rid in os.listdir(att_dir):
        d = os.path.join(att_dir, rid)
        if not os.path.isdir(d):
            continue
        toks = {fn.rsplit(".", 1)[0] for fn in os.listdir(d)
                if os.path.isfile(os.path.join(d, fn)) and os.path.getsize(os.path.join(d, fn)) > 0}
        if toks:
            out[rid] = toks
    return out


def tokens_from_l1(l1_dir, prefix):
    """L1 媒体文档 → {record_id: set(token)}（读 media_refs，不读 OCR 文本）。"""
    out = {}
    if not os.path.isdir(l1_dir):
        return out
    for fn in os.listdir(l1_dir):
        if not fn.startswith(prefix) or not fn.endswith(".json"):
            continue
        doc = json.load(open(os.path.join(l1_dir, fn), encoding="utf-8"))
        rid = doc.get("source", {}).get("record_id") or fn[len(prefix):-5]
        toks = {m.get("file_token") for m in (doc.get("media_refs") or []) if isinstance(m, dict)}
        toks.discard(None)
        out[rid] = toks
    return out


def tokens_from_l1_visual(l1_dir, prefix):
    """L1 媒体文档 → 有「画面读数」段的 token 集（kind=image_visual）。"""
    out = {}
    if not os.path.isdir(l1_dir):
        return out
    for fn in os.listdir(l1_dir):
        if not fn.startswith(prefix) or not fn.endswith(".json"):
            continue
        doc = json.load(open(os.path.join(l1_dir, fn), encoding="utf-8"))
        rid = doc.get("source", {}).get("record_id") or fn[len(prefix):-5]
        toks = set()
        for m in (doc.get("media_refs") or []):
            if isinstance(m, dict) and m.get("visual") and m.get("file_token"):
                toks.add(m["file_token"])
        for s2 in (doc.get("segments") or []):
            if s2.get("kind") == "image_visual" and s2.get("anchor"):
                pass
        if toks:
            out[rid] = toks
    return out


def gaps(src, other, layer):
    """src 有、other 没有的 token —— 逐条点名。"""
    out = []
    for rid in sorted(src):
        miss = src[rid] - other.get(rid, set())
        for tok in sorted(miss):
            out.append({"record_id": rid, "file_token": tok, "missing_in": layer})
    return out


def coverage(src, l0, l1, vis=None):
    s = sum(len(v) for v in src.values())
    a = sum(1 for rid in src for t in src[rid] if t in l0.get(rid, set()))
    b = sum(1 for rid in src for t in src[rid] if t in l1.get(rid, set()))
    c = sum(1 for rid in src for t in src[rid] if t in (vis or {}).get(rid, set()))
    return {"source_files": s, "l0_files": a, "l1_ocr_files": b, "l1_vision_files": c,
            "records_with_images": len(src)}


def run(src_dir=None, live=None):
    src = tokens_from_live(live) if live else tokens_from_records(src_dir or L0_REC_DIR)
    l0 = tokens_from_l0_bytes(L0_ATT_DIR)
    l1 = tokens_from_l1(L1_MEDIA_DIR, L1_PREFIX)
    vis = tokens_from_l1_visual(L1_MEDIA_DIR, L1_PREFIX)
    cov = coverage(src, l0, l1, vis)
    res = {"source": "live" if live else "l0_records", "coverage": cov,
           "gap_l0": gaps(src, l0, "l0_bytes"),
           "gap_l1": gaps(src, l1, "l1_ocr"),
           "gap_l1_vision": gaps(src, vis, "l1_vision"),
           "stale_l0": gaps(l0, src, "source")}
    return res


def selftest():
    """反向对照：造三种情形，判据必须分别给出 0 / 红 / 红。

    用**真函数**跑临时目录，不 mock —— 判据本身被真调用，才有意义。
    """
    cases = []
    with tempfile.TemporaryDirectory() as td:
        rec = os.path.join(td, "records"); att = os.path.join(td, "att"); l1 = os.path.join(td, "l1")
        for d in (rec, att, l1):
            os.makedirs(d)
        rid = "recTEST"
        json.dump({"record_id": rid, "fields": {FIELD: {"value": [
            {"file_token": "tokA", "name": "a.png", "size": 1},
            {"file_token": "tokB", "name": "b.png", "size": 1}]}}},
            open(os.path.join(rec, rid + ".json"), "w", encoding="utf-8"))
        os.makedirs(os.path.join(att, rid))
        for t in ("tokA", "tokB"):
            open(os.path.join(att, rid, t + ".png"), "w").write("x")
        json.dump({"resource_id": "media_" + rid, "source": {"record_id": rid},
                   "media_refs": [{"file_token": "tokA"}, {"file_token": "tokB"}]},
                  open(os.path.join(l1, "media_" + rid + ".json"), "w", encoding="utf-8"))
        g = gaps(tokens_from_records(rec), tokens_from_l0_bytes(att), "l0_bytes")
        cases.append(("全齐 → 缺口 0", len(g) == 0, g))
        # 缺口 1：源多一张（L0 没字节）
        json.dump({"record_id": rid, "fields": {FIELD: {"value": [
            {"file_token": "tokA"}, {"file_token": "tokB"}, {"file_token": "tokC"}]}}},
            open(os.path.join(rec, rid + ".json"), "w", encoding="utf-8"))
        g = gaps(tokens_from_records(rec), tokens_from_l0_bytes(att), "l0_bytes")
        cases.append(("源多一张 tokC → 精确报它", [x["file_token"] for x in g] == ["tokC"], g))
        # 缺口 2：L1 少一张（OCR 没跑过）
        g = gaps(tokens_from_records(rec), tokens_from_l1(l1, "media_"), "l1_ocr")
        cases.append(("L1 少 tokC → 精确报它", [x["file_token"] for x in g] == ["tokC"], g))
    ok = all(c[1] for c in cases)
    for name, okc, g in cases:
        print(("  ✅ " if okc else "  ❌ ") + name + ("" if okc else f"  ｜ {g}"))
    print(f"selftest {'PASS' if ok else 'FAIL'}（{sum(1 for c in cases if c[1])}/{len(cases)}）")
    return 0 if ok else 3


def main(argv):
    if "--selftest" in argv:
        return selftest()
    live = None
    if "--live" in argv:
        i = argv.index("--live")
        live = argv[i + 1] if i + 1 < len(argv) else None
        if not live or not os.path.exists(live):
            print(f"❌ --live 指向的快照不存在：{live}")
            return 2
    res = run(live=live)
    cov = res["coverage"]
    print(f"源：{res['source']} ｜ 记录 {cov['records_with_images']} 条 ｜ 图片 {cov['source_files']} 张")
    print(f"L0 字节：{cov['l0_files']} 张 ｜ L1 OCR：{cov['l1_ocr_files']} 张"
          f" ｜ L1 画面读数：{cov['l1_vision_files']} 张")
    bad = 0
    for key, label in (("gap_l0", "缺 L0 字节"), ("gap_l1", "缺 L1 OCR"),
                       ("gap_l1_vision", "缺画面读数")):
        if res[key]:
            bad += len(res[key])
            print(f"\n❌ {label}：{len(res[key])} 张")
            for x in res[key][:40]:
                print(f"   {x['record_id']} {x['file_token']}")
            if len(res[key]) > 40:
                print(f"   …（其余 {len(res[key]) - 40} 张略）")
    if res["stale_l0"]:
        print(f"\n⚠️ L0 有字节、源侧已没有：{len(res['stale_l0'])} 张（不判红，留档属正常）")
    if bad == 0 and cov["source_files"] > 0:
        print("\n✅ 覆盖完整：源侧每一张都有 L0 字节、都进过 L1 OCR、都有画面读数")
        return 0
    print(f"\n❌ 覆盖不完整：{bad} 张缺口（退出码 3）")
    return 3


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
