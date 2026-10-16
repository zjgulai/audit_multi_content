#!/usr/bin/env python3
"""5 条「摘要不同」的外部页面：判定「内容变了」还是「口径/抓取方式不同」。

决定性依据：L1（kb/l1/*/url__*.json）里**存着当年抓下来的正文**（segments[].text）。
本脚本对每条 URL 做三件事并互相比较：
  ① 当年正文（L1 存）        —— 基准
  ② 今天裸 HTTP + 当年 strip 口径
  ③ 今天无头 Chrome 渲染后的 DOM → strip
然后：
  · 从①里抽出「正文句子」（≥40 字、去掉代码/JSON/JS 行），看它们在②③里逐字还在不在 → 命中率
  · 统计三份文本的「代码噪声占比」，判断当年是不是抓到了 JS/JSON 垃圾
判定：命中率 ≥80% → 内容没变，差异来自口径；≤40% → 内容变了；中间 → 部分变化，需人工看。
用法：python3 kb/l8/verify_urls_headless.py 20260929-1520
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
import html as H
import json
import os
import re
import subprocess
import sys
import urllib.request

RUN = sys.argv[1] if len(sys.argv) > 1 else "20260929-1520"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122 Safari/537.36")
CODEISH = re.compile(r"[{};]|function\s*\(|var\s+\w+|=>|\\u[0-9a-f]{4}|^\s*[\]\[,]", re.I)


def strip_original(h):
    h = re.sub(r"<(title|h1|h2|h3|h4|p|li|br|/p|/li|/h1|/h2|/h3|/h4)[^>]*>", "\n", h)
    h = re.sub(r"<[^>]+>", "", h)
    return re.sub(r"\n{2,}", "\n", H.unescape(h)).strip()


def headless_text(url, budget=9000, timeout=45):
    try:
        p = subprocess.Popen(
            [CHROME, "--headless=new", "--disable-gpu", "--no-sandbox",
             "--user-data-dir=/tmp/chprof-l8", f"--virtual-time-budget={budget}",
             f"--user-agent={UA}", "--dump-dom", url],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        try:
            out, _ = p.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            p.kill()
            out, _ = p.communicate()
        return strip_original(out.decode("utf-8", "ignore")) if out else ""
    except Exception as e:
        return f"__ERR__{type(e).__name__}"


def content_lines(txt):
    out = []
    for ln in (txt or "").split("\n"):
        s = ln.strip()
        if len(s) < 40 or CODEISH.search(s):
            continue
        out.append(s)
    seen, uniq = set(), []
    for s in out:
        if s not in seen:
            seen.add(s)
            uniq.append(s)
    return uniq


def code_ratio(txt):
    ls = [l.strip() for l in (txt or "").split("\n") if l.strip()]
    if not ls:
        return 0.0
    return round(sum(1 for l in ls if CODEISH.search(l)) / len(ls), 3)


rep = json.load(open("kb/l8/runs/20260929-1420-l0-url-verify.json", encoding="utf-8"))
targets = [e["resource_key"] for e in rep["results"] if e["verdict"] == "recomputed_differ"]
print(f"待判定：{len(targets)} 条\n")

l1_files = glob.glob("kb/l1/*/url__*.json")
results = []
for key in targets:
    url = key.split(":", 1)[1]
    ent = {"resource_key": key, "url": url}
    # ① 当年正文（L1）
    prev = ""
    for f in l1_files:
        try:
            d = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        if d.get("resource_key") == key:
            prev = "\n".join((s.get("text") or "") for s in (d.get("segments") or []))
            ent["l1_file"] = f
            break
    # ② 今天裸 HTTP（当年口径）
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "en"})
        with urllib.request.urlopen(req, timeout=25) as r:
            raw = r.read()
        http_txt = strip_original(raw.decode("utf-8", "ignore"))
    except Exception as e:
        raw, http_txt = b"", ""
        ent["http_error"] = f"{type(e).__name__}"
    # ③ 无头渲染
    hl_txt = headless_text(url)

    cl = content_lines(prev)
    def hit(text):
        if not text or text.startswith("__ERR__") or not cl:
            return None
        n = sum(1 for s in cl if s in text)
        return round(n / len(cl), 3)
    ent.update({
        "prev_chars": len(prev), "prev_content_lines": len(cl), "prev_code_ratio": code_ratio(prev),
        "http_bytes": len(raw), "http_chars": len(http_txt), "http_code_ratio": code_ratio(http_txt),
        "headless_chars": len(hl_txt), "headless_code_ratio": code_ratio(hl_txt),
        "headless_sha256": hashlib.sha256(hl_txt.encode()).hexdigest()[:16] if hl_txt and not hl_txt.startswith("__ERR__") else None,
        "hit_in_http": hit(http_txt), "hit_in_headless": hit(hl_txt),
    })
    best = max([x for x in (ent["hit_in_http"], ent["hit_in_headless"]) if x is not None] or [0])
    ent["verdict"] = ("内容未变（差异来自口径/噪声）" if best >= 0.8
                      else "内容已变" if best <= 0.4 else "部分变化，需人工看")
    ent["prev_head"] = prev[:100]
    ent["headless_head"] = (hl_txt or "")[:100]
    results.append(ent)
    print(f"  {url[:56]}")
    print(f"     当年 {ent['prev_chars']} 字(代码行占比 {ent['prev_code_ratio']}) / 当年正文句 {len(cl)}")
    print(f"     裸HTTP {ent['http_chars']} 字(代码 {ent['http_code_ratio']}) 命中率 {ent['hit_in_http']}")
    print(f"     无头渲染 {ent['headless_chars']} 字(代码 {ent['headless_code_ratio']}) 命中率 {ent['hit_in_headless']}")
    print(f"     → {ent['verdict']}")

json.dump({"run": RUN, "method": "L1 当年正文为基准；句子逐字命中率；裸HTTP 与 无头Chrome 双通道",
           "results": results},
          open(f"kb/l8/runs/{RUN}-url-headless-verdict.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print(f"\n报告 kb/l8/runs/{RUN}-url-headless-verdict.json")
