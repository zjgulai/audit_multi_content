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
import shutil
import subprocess
import sys
import time

RUN = sys.argv[1] if len(sys.argv) > 1 else "20260929-1900"
APPLY = "--apply" in sys.argv
LIMIT = None
if "--limit" in sys.argv:
    LIMIT = int(sys.argv[sys.argv.index("--limit") + 1])
# ★ 2026-10-09：渲染与取正文提到**共用件** `kb/l8/url_render_lib.py`。
#   为什么：核验脚本 `verify_l0_urls.py` 必须**按台账记的口径分派管线**才能复现
#   `url_text_rendered_v1` 的摘要（实测：不会渲染时 100/103 条永远对不上，只能写
#   「recomputed_differ」，而那**读起来像「内容变了」**——假信号）。
#   同一份实现**不许存两处**，所以由本脚本 import；行为与提出前逐字相同。
#   （UA 仍可用环境变量覆盖：`L0_UA_NEW` / `L0_UA_SAFARI` —— 假 Chrome UA 会被 FDA/CDC 整站拒。）
from url_render_lib import CHROME, UA_NEW, UA_SAFARI, render, extract  # noqa: E402,F401
ARCH = f"kb/l1/_archive/url-render-{RUN}"
CHUNK = 4000
sha = lambda t: hashlib.sha256(t.encode("utf-8")).hexdigest()
uidf = lambda *p: hashlib.sha1("|".join(str(x) for x in p).encode()).hexdigest()[:20]


# ★ 2026-10-09：`render()` / `extract()` 已移入共用件 `kb/l8/url_render_lib.py`（上面 import）。
#   删掉本地副本是为了**一份实现**：核验脚本要按口径复用同一套渲染+取正文。

# ---- 载入 L0 的 url（★ 2026-10-08 批次一同步修正：排除台账已标坏键的行）----
# 坏键 = 「材料链接」字段里的显示文本被当年抓取器当成了 URL 主机名（台账 09-29 已定性
# 并写「供下游忽略」）。本脚本原先没认这个标记，把它们当真 URL 去抓 → 正文 0 字、纯噪声。
def _is_bad_key(row):
    import re as _re
    if not _re.match(r"^https?://", (row.get("resource_key") or "").split(":", 1)[-1]):
        return True
    note = str(row.get("status_reason") or "") + str(row.get("change") or "")
    return ("坏键" in note) or ("bad_key" in note)

l0rows = {}
for line in open("kb/l0/manifest.jsonl", encoding="utf-8"):
    if line.strip():
        r = json.loads(line)
        l0rows[r["resource_key"]] = r
_all = [(k, v) for k, v in l0rows.items()
        if v["source_kind"] == "url" and v["status"] not in ("gone", "retracted")]
urls = [(k, v) for k, v in _all if not _is_bad_key(v)]
_bad = [k for k, v in _all if _is_bad_key(v)]
if _bad:
    print(f"  跳过台账已登记坏键 {len(_bad)} 条：{[b[:60] for b in _bad]}", flush=True)

# ---- ★ 2026-10-08：飞书站内对象分流出去 ----
# 为什么必须分（实测）：本脚本走 HTTP/无头渲染，而 *.feishu.cn 的 wiki/file/drive/share
# 需要登录态 —— **结构上不可能读到**。今天 RUN 20261008-5000 实测：145 条里 45 条失败，
# 其中 40 条全是这一类（正文 0 字），白跑约 40 分钟，还把它们报成「取不到」。
# 而这些键的正文**早就在库里**（走 kb/l8/recrawl_feishu_urls.py 的飞书 API 通道取原件
# PDF + 扫描件 OCR）：36 条已有正文、合计 10,730,271 字，最长一条 207 万字。
# ⇒ 本脚本不再啃飞书站内键；它们由 recrawl_feishu_urls.py 负责（含裸 token 键 wiki:/docx:）。
_FEISHU_HOST = re.compile(r"^https?://[^/]*\.feishu\.cn/", re.I)


def _is_feishu_internal(row):
    u = (row.get("resource_key") or "").split(":", 1)[-1]
    return bool(_FEISHU_HOST.match(u))


_feishu = [(k, v) for k, v in urls if _is_feishu_internal(v)]
urls = [(k, v) for k, v in urls if not _is_feishu_internal(v)]
if _feishu:
    print(f"  分流飞书站内键 {len(_feishu)} 条 → 交给 recrawl_feishu_urls.py"
          f"（HTTP 读不了登录态对象；其正文多已存在于 L1）", flush=True)
urls.sort()
if LIMIT:
    urls = urls[:LIMIT]
# ★ 2026-10-08：加 `--url-substr a,b,c` 子串筛选 —— 全量 145 条要跑 1 小时+，
#   而很多场合只需要重抓某一类（如 27 条监管/政策依据）。不传则行为不变（全量）。
if "--url-substr" in sys.argv:
    _pat = [s.strip().lower() for s in sys.argv[sys.argv.index("--url-substr") + 1].split(",") if s.strip()]
    _before = len(urls)
    urls = [(k, v) for k, v in urls if any(p in k.lower() for p in _pat)]
    print(f"  --url-substr 命中 {len(urls)}/{_before} 条（模式：{_pat}）", flush=True)
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

# ── ★ 2026-10-08 接线：重抓后**必须**登记退役，否则旧代正文继续留在 L6 索引里 ──
# 病灶实测（RUN 20261008-1240）：本脚本重切出 45 个新单元，但**没有**把被取代的旧单元
# 写进 `kb/l2/retired_units.jsonl` —— 于是 48 条旧正文（含 JS 噪声）在 L6 索引里又活了一轮，
# 得靠人手动补跑 `l2_align_current.py` 才收得掉。**这件事不该靠人记得。**
# 这里按 `l4_integrity.py` 调 `l4_article.py` 的既有先例，用 subprocess 接上；
# 失败不静默：打印退出码与非零告警，主流程退出码不受影响（重抓本身已完成）。
if APPLY:
    print("\n[接线] 重抓后自动登记退役（kb/l8/l2_align_current.py）…", flush=True)
    _rc = subprocess.run([sys.executable, "kb/l8/l2_align_current.py", RUN, "--apply", "--skill", "kb-recall"],
                         capture_output=True, text=True)
    _tail = [l for l in (_rc.stdout or "").strip().split("\n") if l.strip()][-4:]
    for _l in _tail:
        print("   " + _l, flush=True)
    if _rc.returncode != 0:
        print(f"   ⚠️ 退役登记失败（退出码 {_rc.returncode}）—— 旧代单元可能仍在 L6 索引里，"
              f"请手动跑：kb/kbpy l8/l2_align_current.py {RUN} --apply", flush=True)
    else:
        print("   ✅ 退役已登记（旧代单元不会再进索引）", flush=True)
