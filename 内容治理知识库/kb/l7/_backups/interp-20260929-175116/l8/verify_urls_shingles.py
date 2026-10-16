#!/usr/bin/env python3
"""5 条「摘要不同」页面：用词 n-gram 双向重叠判定内容是否变化（比整行逐字稳）。

方法：
  · 基准 = L1 里当年抓的正文（segments 拼接）
  · 对照 = 今天「裸 HTTP」与「无头 Chrome 渲染」两路
  · 都先做：去代码/JSON 噪声行 → 空白归一 → 取 8 词 shingle
  · 指标：A→B（当年正文有多少仍出现在今天）与 B→A（今天有多少是当年就有的）
  · 判定：min(A→B, B→A) ≥0.7 → 内容未变（差异来自口径/噪声）；
          A→B ≤0.4 → 内容已变；其余 → 部分变化，交人工
用法：python3 kb/l8/verify_urls_shingles.py 20260929-1540
"""
import glob
import html as H
import json
import re
import subprocess
import sys
import urllib.request

RUN = sys.argv[1] if len(sys.argv) > 1 else "20260929-1540"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122 Safari/537.36")
CODEISH = re.compile(r"[{};]|function\s*\(|var\s+\w+|=>|\\u[0-9a-f]{4}|^\s*[\]\[,]", re.I)
SPACE = re.compile(r"\s+")


def strip_original(h):
    h = re.sub(r"<(title|h1|h2|h3|h4|p|li|br|/p|/li|/h1|/h2|/h3|/h4)[^>]*>", "\n", h)
    h = re.sub(r"<[^>]+>", "", h)
    return re.sub(r"\n{2,}", "\n", H.unescape(h)).strip()


def visible(txt):
    """去代码行 → 空白归一。"""
    keep = [l.strip() for l in (txt or "").split("\n") if len(l.strip()) >= 25 and not CODEISH.search(l)]
    return SPACE.sub(" ", " ".join(keep)).strip()


def shingles(txt, n=8):
    w = (txt or "").split()
    return {" ".join(w[i:i + n]) for i in range(max(0, len(w) - n + 1))}


def headless_text(url, budget=9000, timeout=45):
    try:
        p = subprocess.Popen([CHROME, "--headless=new", "--disable-gpu", "--no-sandbox",
                              "--user-data-dir=/tmp/chprof-l8b", f"--virtual-time-budget={budget}",
                              f"--user-agent={UA}", "--dump-dom", url],
                             stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        try:
            out, _ = p.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            p.kill()
            out, _ = p.communicate()
        return strip_original(out.decode("utf-8", "ignore")) if out else ""
    except Exception:
        return ""


def overlap(a, b):
    if not a:
        return None
    return round(len(a & b) / len(a), 3)


rep = json.load(open("kb/l8/runs/20260929-1420-l0-url-verify.json", encoding="utf-8"))
targets = [e["resource_key"] for e in rep["results"] if e["verdict"] == "recomputed_differ"]
l1_files = glob.glob("kb/l1/*/url__*.json")

out = []
for key in targets:
    url = key.split(":", 1)[1]
    prev = ""
    for f in l1_files:
        try:
            d = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        if d.get("resource_key") == key:
            prev = "\n".join((s.get("text") or "") for s in (d.get("segments") or []))
            break
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "en"})
        with urllib.request.urlopen(req, timeout=25) as r:
            http_txt = strip_original(r.read().decode("utf-8", "ignore"))
    except Exception:
        http_txt = ""
    hl = headless_text(url)
    pv, hv, lv = visible(prev), visible(http_txt), visible(hl)
    ps, hs, ls = shingles(pv), shingles(hv), shingles(lv)
    a_h, b_h = overlap(ps, hs), overlap(hs, ps)
    a_l, b_l = overlap(ps, ls), overlap(ls, ps)
    def verdict(x, y):
        if x is None or y is None:
            return "无法判定（当年正文为空）"
        m = min(x, y)
        return "内容未变（差异来自口径/噪声）" if m >= 0.7 else ("内容已变" if x <= 0.4 or y <= 0.4 else "部分变化，需人工看")
    ent = {"url": url, "prev_visible_chars": len(pv), "prev_shingles": len(ps),
           "http_visible_chars": len(hv), "headless_visible_chars": len(lv),
           "prev_to_http": a_h, "http_to_prev": b_h, "verdict_http": verdict(a_h, b_h),
           "prev_to_headless": a_l, "headless_to_prev": b_l, "verdict_headless": verdict(a_l, b_l)}
    out.append(ent)
    print(f"  {url[:56]}")
    print(f"     当年正文 {len(pv)} 字（{len(ps)} 个 8-gram）")
    print(f"     裸HTTP   可见 {len(hv)} 字 | 当年→今 {a_h} 今→当年 {b_h} → {ent['verdict_http']}")
    print(f"     无头渲染 可见 {len(lv)} 字 | 当年→今 {a_l} 今→当年 {b_l} → {ent['verdict_headless']}")

json.dump({"run": RUN, "method": "词 8-gram 双向重叠（去代码行 + 空白归一）", "results": out},
          open(f"kb/l8/runs/{RUN}-url-content-verdict.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"\n报告 kb/l8/runs/{RUN}-url-content-verdict.json")
