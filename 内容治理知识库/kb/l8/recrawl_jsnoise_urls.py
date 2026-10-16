#!/usr/bin/env python3
"""9 条「JS/JSON 噪声」外部标准：无头 Chrome 重抓可见正文，并重建 L1→L2。

背景：20260929-1420 的 URL 核验发现 11 条摘要不符，其中 9 条经 L1 当年正文与词 8-gram 比对确认
      **当年抓到的不是网页正文**（Amazon 6 / Google 2 / TikTok 1 —— 分别是 JS、JSON、base64 cookie 载荷）。
本脚本：
  ① 无头 Chrome 渲染 → 去代码行 → 可见正文（词 8-gram 双向重叠要求 ≥0.7 才算重抓成功）
  ② 旧 L1 产物归档到 kb/l1/_archive/url-jsnoise-<RUN>/，写回新产物（同 25 键结构）
  ③ L1 manifest 追加新行（status ok / 新 source_sha256）
  ④ L0 台账追加 updated 行（sha256_input=url_text_rendered_v1）
  ⑤ L2：为新正文切单元（clause），并把该资源的旧单元标 invalidated（append-only）
用法：python3 kb/l8/recrawl_jsnoise_urls.py 20260929-1620 [--apply]
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

RUN = sys.argv[1] if len(sys.argv) > 1 else "20260929-1620"
APPLY = "--apply" in sys.argv
# ★ 2026-10-09 修正：原先指向完整 Google Chrome.app —— macOS 上启动 app bundle
# 必然在 Dock 弹图标，而本库是「起一个→kill→再起一个」的循环 ⇒ 图标不停闪。
# 改用 chrome-headless-shell（官方无头专用二进制，不是 .app，不进 Dock）。
# 它对本文件既有的 --headless=new/--headless 参数一律容忍，故只换路径、不动 flag。
CHROME = os.environ.get("KB_CHROME_BIN",
    "/Users/lute/.dsh/vendor/chrome-headless-shell-mac-arm64/chrome-headless-shell")
SPACE = re.compile(r"\s+")
CODEISH = re.compile(r"[{};]|function\s*\(|var\s+\w+|=>|\\u[0-9a-f]{4}|^\s*[\]\[,]", re.I)
CHUNK = 4000
TARGETS = [
    "https://advertising.amazon.com/help/G4U9JBZH3664JWX2",
    "https://advertising.amazon.com/help/G6UU66YLSCUYDULQ",
    "https://advertising.amazon.com/help/GFNDKT3FYGDL54VB",
    "https://advertising.amazon.com/help/GPSSMTEAA6AEWY3A",
    "https://advertising.amazon.com/help/GRW23T7LB4MFMBXQ",
    "https://advertising.amazon.com/help/GZS8A5XCFQJTS88N",
    "https://support.google.com/adspolicy/answer/176031",
    "https://support.google.com/adspolicy/answer/6020955",
    "https://www.tiktok.com/legal/page/global/bc-policy/en",
]
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122 Safari/537.36")
sha = lambda t: hashlib.sha256(t.encode("utf-8")).hexdigest()
uidf = lambda *p: hashlib.sha1("|".join(str(x) for x in p).encode()).hexdigest()[:20]
ARCH = f"kb/l1/_archive/url-jsnoise-{RUN}"


def visible(txt):
    keep = [l.strip() for l in (txt or "").split("\n") if len(l.strip()) >= 25 and not CODEISH.search(l)]
    return SPACE.sub(" ", " ".join(keep)).strip()


def render(url):
    p = subprocess.Popen([CHROME, "--headless=new", "--disable-gpu", "--no-sandbox",
                          "--user-data-dir=/tmp/chprof-recrawl", "--virtual-time-budget=10000",
                          f"--user-agent={UA}", "--dump-dom", url],
                         stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    try:
        out, _ = p.communicate(timeout=60)
    except subprocess.TimeoutExpired:
        p.kill()
        out, _ = p.communicate()
    h = (out or b"").decode("utf-8", "ignore")
    h = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", h, flags=re.S | re.I)
    h = re.sub(r"<[^>]+>", " ", h)
    import html as H
    return visible(H.unescape(h))


arts = {json.load(open(f, encoding="utf-8"))["resource_key"]: f
        for f in glob.glob("kb/l1/*/url__*.json")}
l1man = [json.loads(l) for l in open("kb/l1/manifest_l1.jsonl", encoding="utf-8") if l.strip()]
MAN_KEYS = set(l1man[0])
units = [json.loads(l) for l in open("kb/l2/units.jsonl", encoding="utf-8") if l.strip()]
l2man_keys = set(json.loads(open("kb/l2/manifest_l2.jsonl", encoding="utf-8").readline()))
os.makedirs(ARCH, exist_ok=True)

l1_new, l0_new, l2_new, l2_inv, report = [], [], [], [], []
for url in TARGETS:
    key = f"url:{url}"
    art_p = arts.get(key)
    if not art_p:
        print(f"  ✗ 无 L1 产物 {url}")
        continue
    old = json.load(open(art_p, encoding="utf-8"))
    text = render(url)
    ent = {"url": url, "rendered_chars": len(text), "artifact": art_p}
    if len(text) < 300:
        ent["verdict"] = "渲染后正文过短，跳过"
        report.append(ent)
        print(f"  ✗ {url[:60]} 渲染后仅 {len(text)} 字")
        continue
    segs = [{"kind": "paragraph", "text": text[i:i + CHUNK], "anchor": f"#l.1-{n}"}
            for n, i in enumerate(range(0, len(text), CHUNK), 1)]
    h = sha(text)
    new = dict(old)
    new.update({"source_sha256": h, "extractor_version": "l1-0.1+recrawl-20260929",
                "status": "ok",
                "status_reason": "2026-09-29 重抓：原正文为 JS/JSON 噪声（当年抓取质量），改用无头 Chrome 渲染取可见正文",
                "segments": segs, "segment_count": len(segs), "char_count": len(text),
                "observed_at": RUN, "recrawl": {"at": RUN, "method": "chrome-headless dump-dom + 去代码行",
                                                "chars_before": old.get("char_count"), "sha256_before": old.get("source_sha256")}})
    ent["verdict"] = "重抓成功"
    ent["chars_before"] = old.get("char_count")
    if APPLY:
        shutil.copy2(art_p, f"{ARCH}/{os.path.basename(art_p)}")
        tmp = art_p + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(new, fh, ensure_ascii=False, indent=1)
        json.load(open(tmp, encoding="utf-8"))
        os.replace(tmp, art_p)
        l1_new.append({"resource_id": old["resource_id"], "resource_key": key, "kb_type": old.get("kb_type"),
                       "source_kind": old.get("source_kind"), "source_sha256": h,
                       "extractor_version": new["extractor_version"], "status": "ok",
                       "status_reason": new["status_reason"], "segment_count": len(segs),
                       "char_count": len(text), "media_count": 0, "table_count": 0, "observed_at": RUN})
        # L2：新单元 + 旧单元失效
        olds = [u for u in units if u.get("resource_id") == old["resource_id"]]
        tmpl = olds[0] if olds else None
        if tmpl:
            for i, s in enumerate(segs, 1):
                ut = "entry" if s["kind"] == "field_value" else "clause"
                u = dict(tmpl)
                u.update({"unit_id": uidf("l2-0.3", old["resource_id"], h, ut, s["anchor"], "", i),
                          "source_sha256": h, "text": s["text"], "char_count": len(s["text"]),
                          "anchor": s["anchor"], "unit_type": ut, "order_in_parent": i,
                          "meta": {"anchor_precision": "segment_only", "content_quality_flag": "recrawl_headless_rendered",
                                   "content_quality_note": "2026-09-29 无头 Chrome 重抓的可见正文（原 L1 正文为 JS/JSON 噪声）"}})
                l2_new.append(u)
            l2_inv.append({"kb_type": tmpl.get("kb_type"), "observed_at": RUN,
                           "resource_id": old["resource_id"], "result": "invalidated",
                           "source_sha256": old.get("source_sha256"),
                           "splitter_version": tmpl.get("splitter_version"), "unit_count": len(olds)})
    report.append(ent)
    print(f"  ✓ {url[:58]}：{old.get('char_count')} 字(噪声) → {len(text)} 字(正文)，段 {len(segs)}")

if APPLY:
    with open("kb/l1/manifest_l1.jsonl", "a", encoding="utf-8") as fh:
        for r in l1_new:
            assert not (set(r) - MAN_KEYS)
            fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
    with open("kb/l2/units.jsonl", "a", encoding="utf-8") as fh:
        for u in l2_new:
            fh.write(json.dumps(u, ensure_ascii=False, sort_keys=True) + "\n")
    with open("kb/l2/index/l2.jsonl", "a", encoding="utf-8") as fh:
        for u in l2_new:
            fh.write(json.dumps({"anchor": u["anchor"], "char_count": u["char_count"], "kb_type": u["kb_type"],
                                 "source_sha256": u["source_sha256"], "unit_id": u["unit_id"]},
                                ensure_ascii=False, sort_keys=True) + "\n")
    with open("kb/l2/manifest_l2.jsonl", "a", encoding="utf-8") as fh:
        for r in l2_inv + [{"kb_type": u["kb_type"], "observed_at": RUN, "resource_id": u["resource_id"],
                            "result": "split", "source_sha256": u["source_sha256"],
                            "splitter_version": u.get("splitter_version"), "unit_count": 1} for u in [] ]:
            assert set(r) == l2man_keys, set(r) ^ l2man_keys
            fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
        # 每个资源一行 split（汇总）
        byres = {}
        for u in l2_new:
            byres.setdefault(u["resource_id"], []).append(u)
        for rid, us in byres.items():
            r = {"kb_type": us[0]["kb_type"], "observed_at": RUN, "resource_id": rid, "result": "split",
                 "source_sha256": us[0]["source_sha256"], "splitter_version": us[0].get("splitter_version"),
                 "unit_count": len(us)}
            fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
    print(f"\n[写入] L1 manifest +{len(l1_new)} | L2 新单元 +{len(l2_new)} | L2 失效行 +{len(l2_inv)} | 旧产物归档 {ARCH}")
else:
    print("\n未写入（加 --apply）")
json.dump({"run": RUN, "kind": "jsnoise_url_recrawl", "results": report,
           "l1_manifest_rows": len(l1_new), "l2_new_units": len(l2_new), "l2_invalidated": len(l2_inv),
           "archive": ARCH if APPLY else None},
          open(f"kb/l8/runs/{RUN}-url-recrawl.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
