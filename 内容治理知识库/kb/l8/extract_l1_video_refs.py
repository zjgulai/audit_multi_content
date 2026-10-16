#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""L1 内嵌视频识别：把文档正文里 <figure><source mime="video/..."> 登记成 media_refs。

为什么要有它（2026-10-08 实测）：飞书文档把视频以
    <figure view-type="Preview"><source name="x.mp4" mime="video/mp4" size="..." token="..."/>
嵌在正文里。L1 抽取只取文本 ⇒ **视频元数据整批丢失**，
库里"看不见"这些视频（实测全库 11 个 / 约 614 MB，此前一个都没登记）。

**只登记，不下载**（公司规定：守衡不得下载/导出云文档）。
产物：写回各 L1 产物的 `media_refs`（kind="video"）+ `media_count`；正文与 sha 一律不动。

用法：python3 kb/l8/extract_l1_video_refs.py <RUN> [--apply]
      不带 --apply = 干跑（只打印，不写盘）
"""
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

import glob
import json
import re
import shutil
import tempfile
import time

RUN = _sys.argv[1] if len(_sys.argv) > 1 else time.strftime("%Y%m%d-%H%M")
APPLY = "--apply" in _sys.argv

FIG = re.compile(r'<figure[^>]*>(.*?)</figure>', re.S | re.I)
SRC = re.compile(r'<source\b([^>]*)/?>', re.I)
ATTR = re.compile(r'([\w-]+)="([^"]*)"')


def attrs(s):
    return {k: v for k, v in ATTR.findall(s)}


def media_of(d):
    mr = d.get("media_refs")
    return mr if isinstance(mr, list) else []


def scan_doc(path):
    with open(path, encoding="utf-8") as fh:
        d = json.load(fh)
    if not isinstance(d, dict):
        return None, [], "非 dict"
    segs = d.get("segments")
    if not isinstance(segs, list):
        return d, [], "segments 非 list"
    have = {str(m.get("file_token")) for m in media_of(d) if isinstance(m, dict)}
    found = []
    for si, s in enumerate(segs, 1):
        if not isinstance(s, dict):
            continue
        txt = s.get("text") or ""
        if "video/" not in txt.lower():
            continue
        anchor0 = str(s.get("anchor") or ("#seg.%d" % si))
        vi = 0
        for fig in FIG.findall(txt):
            for src in SRC.findall(fig):
                a = attrs(src)
                mime = str(a.get("mime") or "")
                if not mime.lower().startswith("video/"):
                    continue
                tok = a.get("token")
                if not tok or tok in have:
                    continue
                vi += 1
                found.append({
                    "kind": "video",
                    "seq": len(found) + 1,
                    "file_token": tok,
                    "name": a.get("name"),
                    "mime": mime,
                    "bytes": int(a["size"]) if str(a.get("size", "")).isdigit() else None,
                    "width": a.get("origin-width"),
                    "height": a.get("origin-height"),
                    "anchor": "%s#video.%d" % (anchor0, vi),
                    "sha256": None,
                    "sha256_state": "not_downloaded",
                    "media_path": None,
                    "note": "内嵌视频（只登记元数据，不下载；公司规定守衡不得下载/导出云文档）",
                    "observed_at": RUN,
                })
                have.add(str(tok))
    return d, found, None


def main():
    hits, total = [], 0
    for p in sorted(glob.glob("kb/l1/*/*.json")):
        d, found, err = scan_doc(p)
        if err or not found:
            continue
        hits.append((p, d, found))
        total += len(found)
    print("[%s] L1 内嵌视频识别%s" % (RUN, "（落盘）" if APPLY else "（干跑）"))
    print("  命中文件 %d 个 ｜ 新登记视频 %d 个" % (len(hits), total))
    for p, d, found in hits:
        print("   %-58s +%d" % (p.split("/")[-1][:56], len(found)))
        for v in found:
            mb = ("%.1f MB" % (v["bytes"] / 1024 / 1024)) if v["bytes"] else "?"
            print("        %-44s %9s  %s" % (str(v["name"])[:42], mb, v["file_token"]))
    if not APPLY:
        print("\n  [干跑] 未落盘。加 --apply 即写回 media_refs。")
        return 0
    written = 0
    for p, d, found in hits:
        bak = p + ".bak-pre-videorefs-%s" % RUN
        shutil.copyfile(p, bak)
        mr = list(media_of(d)) + found
        d = dict(d)
        d["media_refs"] = mr
        d["media_count"] = len(mr)
        d["observed_at"] = RUN
        d["status_reason"] = (str(d.get("status_reason") or "") +
                              "；2026-10-08 补登内嵌视频元数据 %d 个（不下载）" % len(found))[:400]
        fd, tmp = tempfile.mkstemp(suffix=".swtmp")
        with _os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(d, fh, ensure_ascii=False, indent=1)
        json.load(open(tmp, encoding="utf-8"))
        shutil.copyfile(tmp, p)
        back = json.load(open(p, encoding="utf-8"))
        assert len(back["media_refs"]) == len(mr), "回读不一致"
        written += 1
        print("   ✅ %s（media_refs %d）备份 %s" % (p.split("/")[-1][:48], len(mr), bak.split("/")[-1]))
    print("  已写回 %d 个文件" % written)
    return 0


if __name__ == "__main__":
    _sys.exit(main())
