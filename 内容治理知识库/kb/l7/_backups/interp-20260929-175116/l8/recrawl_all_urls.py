#!/usr/bin/env python3
"""150 条外部 URL 统一口径重抓（无头 Chrome + 块级取文本）。

为什么做：L0 的 url 摘要此前混了三种口径（原抓取器 url_text / 我的 strip 版 / 无头渲染版），
         互不可比。本批用**同一套渲染与取文本方法**重抓全部 URL，并把结果落到 L0 台账 + L1 产物 + L2 单元。

统一方法：
  ① 渲染：chrome --headless=new --virtual-time-budget=15000（去代码行后正文 <300 字则降级：
     旧 --headless + Safari UA + 25000 预算）
  ② 取文本：去 script/style/noscript → 块级标签换行 → 剥标签 → 反转义 → 丢短行与代码行（代码字符占比 >4%）
  ③ 摘要：sha256(取出的正文文本)，口径名 url_text_rendered_v1
  ④ 落盘：旧 L1 产物归档 → 写新产物（段=4000 字块）→ L1 manifest 追加 → L0 台账追加
     → L2 为新正文切单元、旧单元标 invalidated（正文变化时才做）
用法：python3 kb/l8/recrawl_all_urls.py 20260929-1900 [--apply] [--limit N]
"""
import glob
import hashlib
import html as H
import json
import os
import re
import shutil
import subprocess
import sys
import time

RUN = sys.argv[1] if len(sys.argv) > 1 else "20260929-1900"
APPLY = "--apply" in sys.argv
LIMIT = None
if "--limit" in sys.argv:
    LIMIT = int(sys.argv[sys.argv.index("--limit") + 1])
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
UA_NEW = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/122 Safari/537.36")
UA_SAFARI = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
             "(KHTML, like Gecko) Version/17.0 Safari/605.1.15")
ARCH = f"kb/l1/_archive/url-render-{RUN}"
CHUNK = 4000
sha = lambda t: hashlib.sha256(t.encode("utf-8")).hexdigest()
uidf = lambda *p: hashlib.sha1("|".join(str(x) for x in p).encode()).hexdigest()[:20]


def render(url, mode):
    """stdout→文件；文件大小连续 1.5s 不增长即认为渲染完成，立即 kill（Chrome 不会自己退出）。"""
    tag = abs(hash(url)) % 10**8
    tmp = f"/tmp/_chp_{os.getpid()}_{tag}.html"
    if mode == "new":
        args = [CHROME, "--headless=new", "--disable-gpu", "--no-sandbox",
                f"--user-data-dir=/tmp/chp-new-{tag}", "--lang=en-US",
                "--virtual-time-budget=8000", f"--user-agent={UA_NEW}", "--dump-dom", url]
    else:
        args = [CHROME, "--headless", "--disable-gpu", "--no-sandbox",
                f"--user-data-dir=/tmp/chp-legacy-{tag}", "--lang=en-US", "--window-size=1440,900",
                "--virtual-time-budget=12000", f"--user-agent={UA_SAFARI}", "--dump-dom", url]
    cap, quiet = (30, 1.5) if mode == "new" else (40, 2.0)
    with open(tmp, "wb") as fh:
        p = subprocess.Popen(args, stdout=fh, stderr=subprocess.DEVNULL)
        last, stable, t0 = -1, 0.0, time.time()
        while time.time() - t0 < cap:
            time.sleep(0.4)
            try:
                sz = os.path.getsize(tmp)
            except OSError:
                sz = 0
            if sz > 0 and sz == last:
                stable += 0.4
                if stable >= quiet and b"</html>" in open(tmp, "rb").read()[-400000:]:
                    break
            else:
                stable = 0.0
            last = sz
        try:
            p.kill()
        except Exception:
            pass
        try:
            p.wait(timeout=5)
        except Exception:
            pass
    try:
        h = open(tmp, "rb").read().decode("utf-8", "ignore")
    except Exception:
        h = ""
    for f in (tmp,):
        try:
            os.remove(f)
        except Exception:
            pass
    return h


def extract(h):
    h = re.sub(r"<(script|style|noscript)[^>]*>.*?</\1>", " ", h, flags=re.S | re.I)
    h = re.sub(r"</(p|li|div|h[1-6]|tr|section|article|ul|ol|td|th|table)>", "\n", h, flags=re.I)
    h = re.sub(r"<br\s*/?>", "\n", h, flags=re.I)
    h = re.sub(r"<[^>]+>", " ", h)
    txt = H.unescape(h)
    out, seen = [], set()
    for line in txt.split("\n"):
        s = re.sub(r"\s+", " ", line).strip()
        if len(s) < 30:
            continue
        codey = sum(s.count(c) for c in "{};<>\\") / max(1, len(s))
        if codey > 0.04:
            continue
        if s not in seen:
            seen.add(s)
            out.append(s)
    return "\n".join(out).strip()


# ---- 载入 L0 的 150 条 url ----
l0rows = {}
for line in open("kb/l0/manifest.jsonl", encoding="utf-8"):
    if line.strip():
        r = json.loads(line)
        l0rows[r["resource_key"]] = r
urls = [(k, v) for k, v in l0rows.items()
        if v["source_kind"] == "url" and v["status"] not in ("gone", "retracted")]
urls.sort()
if LIMIT:
    urls = urls[:LIMIT]
print(f"[{RUN}] 待重抓 {len(urls)} 条（应用写入：{APPLY}）", flush=True)

arts = {}
for f in glob.glob("kb/l1/*/url__*.json"):
    try:
        d = json.load(open(f, encoding="utf-8"))
        arts[d["resource_key"]] = f
    except Exception:
        pass
l1_keys = set(json.loads(open("kb/l1/manifest_l1.jsonl", encoding="utf-8").readline()))
l2_keys = set(json.loads(open("kb/l2/manifest_l2.jsonl", encoding="utf-8").readline()))
units = [json.loads(l) for l in open("kb/l2/units.jsonl", encoding="utf-8") if l.strip()]
os.makedirs(ARCH, exist_ok=True)

LEGACY_ONLY = set()


def http_get(url):
    """HTTP 直取（多数站点服务端渲染，1-2 秒即可）；失败返回空串。"""
    import urllib.request
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA_NEW, "Accept-Language": "en,zh;q=0.8"})
        with urllib.request.urlopen(req, timeout=25) as r:
            raw = r.read()
        enc = "utf-8"
        m = re.search(rb'charset=["\']?([\w-]+)', raw[:4000], re.I)
        if m:
            enc = m.group(1).decode("ascii", "ignore")
        return extract(raw.decode(enc, "ignore"))
    except Exception:
        return ""


import threading
SPOOL = f"kb/l8/_stage/fetch-{RUN}.jsonl"
SPOOL_LOCK = threading.Lock()
HEAVY = threading.Semaphore(3)          # 无头浏览器最多 3 个并发


def _spool_append(rec):
    with SPOOL_LOCK:
        with open(SPOOL, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


def fetch_one(item):
    """两级策略：① HTTP 直取（快，覆盖多数站点）② 正文不足才上无头浏览器（限 3 并发）。
    每抓完一条立即写 spool，进程被杀也能续跑。"""
    key, row = item
    url = key.split(":", 1)[1]
    text, method = http_get(url), "http"
    if len(text) < 500:
        for mode in ("new", "legacy"):
            if len(text) >= 500:
                break
            with HEAVY:
                try:
                    t = extract(render(url, mode))
                except Exception:
                    t = ""
            if len(t) > len(text):
                text, method = t, mode
    rec = {"key": key, "text": text, "method": method, "chars": len(text)}
    _spool_append(rec)
    return rec

t0 = time.time()
done = {}
if os.path.exists(SPOOL):
    for l in open(SPOOL, encoding="utf-8"):
        if l.strip():
            r = json.loads(l)
            done[r["key"]] = r
    print(f"[续跑] spool 已有 {len(done)} 条，跳过", flush=True)
todo = [(k, v) for k, v in urls if k not in done]
from concurrent.futures import ThreadPoolExecutor
if todo:
    with ThreadPoolExecutor(max_workers=8) as ex:
        list(ex.map(fetch_one, todo))
fetched = []
for k, v in urls:
    r = done.get(k)
    if r is None and os.path.exists(SPOOL):
        for l in open(SPOOL, encoding="utf-8"):
            if l.strip():
                rr = json.loads(l)
                if rr["key"] == k:
                    r = rr
    if r is None:
        r = {"key": k, "text": "", "method": "none", "chars": 0}
    fetched.append((k, v, r["text"], r["method"]))
print(f"[抓取完成] {len(fetched)} 条（本轮新抓 {len(todo)}），用时 {time.time()-t0:.0f}s", flush=True)

l1_new, l0_new, l2_new, l2_inv, rep = [], [], [], [], []
for i, (key, row, text, method) in enumerate(fetched, 1):
    url = key.split(":", 1)[1]
    ent = {"resource_key": key, "url": url, "sha256_before": row.get("sha256"),
           "input_before": row.get("sha256_input")}
    ent.update({"method": method, "chars": len(text)})
    if len(text) < 300:
        ent["verdict"] = "渲染失败/正文过短"
        rep.append(ent)
        print(f"  [{i}/{len(urls)}] ✗ {url[:66]} 正文 {len(text)} 字", flush=True)
        continue
    h_new = sha(text)
    art_p = arts.get(key)
    old_art = json.load(open(art_p, encoding="utf-8")) if art_p else None
    changed = (row.get("sha256") != h_new)
    ent["verdict"] = "已重抓" + ("（正文与原摘要不同）" if changed else "（与原摘要一致）")
    if APPLY:
        if art_p and old_art:
            shutil.copy2(art_p, f"{ARCH}/{os.path.basename(art_p)}")
            segs = [{"kind": "paragraph", "text": text[j:j + CHUNK], "anchor": f"#l.1-{n}"}
                    for n, j in enumerate(range(0, len(text), CHUNK), 1)]
            new_art = dict(old_art)
            new_art.update({"source_sha256": h_new, "extractor_version": "l1-0.1+render-20260929",
                            "status": "ok",
                            "status_reason": f"2026-09-29 统一口径重抓（无头渲染 mode={method}）："
                                             f"{old_art.get('char_count')} 字 → {len(text)} 字",
                            "segments": segs, "segment_count": len(segs), "char_count": len(text),
                            "observed_at": RUN,
                            "recrawl": {"at": RUN, "method": f"chrome-{method} + 块级取文本",
                                        "chars_before": old_art.get("char_count"),
                                        "sha256_before": old_art.get("source_sha256")}})
            tmp = art_p + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(new_art, fh, ensure_ascii=False, indent=1)
            json.load(open(tmp, encoding="utf-8"))
            os.replace(tmp, art_p)
            l1_new.append({"resource_id": old_art["resource_id"], "resource_key": key,
                           "kb_type": old_art.get("kb_type"), "source_kind": old_art.get("source_kind"),
                           "source_sha256": h_new, "extractor_version": new_art["extractor_version"],
                           "status": "ok", "status_reason": new_art["status_reason"],
                           "segment_count": len(segs), "char_count": len(text),
                           "media_count": 0, "table_count": 0, "observed_at": RUN})
            if changed:
                olds = [u for u in units if u.get("resource_id") == old_art["resource_id"]]
                if olds:
                    tmpl = olds[0]
                    for n, s in enumerate(segs, 1):
                        u = dict(tmpl)
                        u.update({"unit_id": uidf("l2-0.3", old_art["resource_id"], h_new, "clause", s["anchor"], "", n),
                                  "source_sha256": h_new, "text": s["text"], "char_count": len(s["text"]),
                                  "anchor": s["anchor"], "unit_type": "clause", "order_in_parent": n,
                                  "meta": {"anchor_precision": "segment_only",
                                           "content_quality_flag": "recrawl_headless_rendered",
                                           "content_quality_note": "2026-09-29 统一口径无头渲染正文"}})
                        l2_new.append(u)
                    l2_inv.append({"kb_type": tmpl.get("kb_type"), "observed_at": RUN,
                                   "resource_id": old_art["resource_id"], "result": "invalidated",
                                   "source_sha256": old_art.get("source_sha256"),
                                   "splitter_version": tmpl.get("splitter_version"), "unit_count": len(olds)})
        n = dict(row)
        n.update({"sha256": h_new, "sha256_input": "url_text_rendered_v1", "sha256_state": "full",
                  "sha256_prev": row.get("sha256"), "observed_at": RUN, "change": "l0_url_unified_recrawl",
                  "status_reason": f"2026-09-29 统一口径重抓（无头渲染 {method}）：正文 {len(text)} 字"})
        l0_new.append(n)
    rep.append(ent)
    if i % 10 == 0 or i == len(urls):
        print(f"  [{i}/{len(urls)}] 用时 {time.time()-t0:.0f}s｜成功 {sum(1 for x in rep if x.get('verdict','').startswith('已重抓'))}"
              f"｜失败 {sum(1 for x in rep if x.get('verdict','').startswith('渲染失败'))}", flush=True)

if APPLY:
    with open("kb/l1/manifest_l1.jsonl", "a", encoding="utf-8") as fh:
        for r in l1_new:
            assert not (set(r) - l1_keys), set(r) - l1_keys
            fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
    with open("kb/l0/manifest.jsonl", "a", encoding="utf-8") as fh:
        for r in l0_new:
            fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
    with open("kb/l2/units.jsonl", "a", encoding="utf-8") as fh:
        for u in l2_new:
            fh.write(json.dumps(u, ensure_ascii=False, sort_keys=True) + "\n")
    with open("kb/l2/manifest_l2.jsonl", "a", encoding="utf-8") as fh:
        for r in l2_inv:
            assert set(r) == l2_keys, set(r) ^ l2_keys
            fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
        byres = {}
        for u in l2_new:
            byres.setdefault(u["resource_id"], []).append(u)
        for rid, us in byres.items():
            fh.write(json.dumps({"kb_type": us[0]["kb_type"], "observed_at": RUN, "resource_id": rid,
                                 "result": "split", "source_sha256": us[0]["source_sha256"],
                                 "splitter_version": us[0].get("splitter_version"),
                                 "unit_count": len(us)}, ensure_ascii=False, sort_keys=True) + "\n")
    print(f"\n[写入] L1 manifest +{len(l1_new)} | L0 台账 +{len(l0_new)} | L2 新单元 +{len(l2_new)} | L2 失效 +{len(l2_inv)}"
          f" | 旧产物归档 {ARCH}", flush=True)

json.dump({"run": RUN, "kind": "unified_url_recrawl", "method": "chrome headless(new→legacy) + 块级取文本",
           "total": len(urls), "ok": sum(1 for x in rep if x.get("verdict", "").startswith("已重抓")),
           "failed": sum(1 for x in rep if x.get("verdict", "").startswith("渲染失败")),
           "l1_rows": len(l1_new), "l0_rows": len(l0_new), "l2_new": len(l2_new), "l2_invalidated": len(l2_inv),
           "results": rep},
          open(f"kb/l8/runs/{RUN}-url-unified-recrawl.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"[完成] 报告 kb/l8/runs/{RUN}-url-unified-recrawl.json", flush=True)
