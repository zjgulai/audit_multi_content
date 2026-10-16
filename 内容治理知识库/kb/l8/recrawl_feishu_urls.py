#!/usr/bin/env python3
"""飞书类 URL 的专用补抓（HTTP 读不了飞书内部对象，必须走 API）。

背景：kb/l8/runs/20260929-2030-url-unified-recrawl.json 里 48 条失败中，绝大多数是
      *.feishu.cn/wiki|file|drive|share 链接以及两个裸 token 的 wiki 键。
本脚本按对象类型分流读取：
  wiki 节点 → wiki +node-get → 按 obj_type:
      docx → docs +fetch（取正文）
      bitable → base +table-list（表清单 + 记录数）
      sheet → sheets +workbook-info（工作表清单）
      file → drive +preview --type source_file（原件字节，落 L0 attachments）
  裸 token（键形如 wiki:xxx）→ 同上按 wiki 节点处理
  /drive/folder → drive +status（列目录；无权限则记录原因）
  /share/base/view → drive +inspect（定性）
产物：L0 台账追加（sha256_input=feishu_content_v1）+ L1 产物 + 运行记录
用法：python3 kb/l8/recrawl_feishu_urls.py 20260929-2045 [--apply]
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

RUN = sys.argv[1] if len(sys.argv) > 1 else "20260929-2045"
APPLY = "--apply" in sys.argv
AS_ID, PROFILE = os.environ.get("L8_AS", "bot"), os.environ.get("L8_PROFILE", "dsh-kb")
# ★ 2026-10-08 修正：原来默认 "user"。但 dsh-kb 这套 app 的 user 令牌 2026-10-05 已过期
#   ⇒ 不带 L8_AS=bot 时**整批 authentication 失败**（实测 40/40 全红，看着像"全都没权限"）。
#   本脚本读的是 Base / wiki / drive 对象，**主身份本来就该是 bot**（与 align_l0_feishu.py:55 同口径）。
ENV = dict(os.environ, PATH=os.path.expanduser("~/.dsh/bin") + ":" + os.environ.get("PATH", ""))
sha = lambda t: hashlib.sha256(t.encode("utf-8")).hexdigest()
SPACE = re.compile(r"\s+")


def sh(*a):
    p = subprocess.run(list(a), capture_output=True, text=True, encoding="utf-8",
                       errors="replace", env=ENV, timeout=600)
    try:
        return json.loads(p.stdout)
    except Exception:
        return {"ok": False, "error": {"message": (p.stdout or p.stderr)[:160]}}


def strip_html(h):
    h = re.sub(r"<(script|style|noscript)[^>]*>.*?</\1>", " ", h, flags=re.S | re.I)
    h = re.sub(r"</(p|li|div|h[1-6]|tr|section|article|ul|ol|td|th)>", "\n", h, flags=re.I)
    h = re.sub(r"<[^>]+>", " ", h)
    txt = H.unescape(h)
    keep = [SPACE.sub(" ", l).strip() for l in txt.split("\n")]
    return "\n".join(x for x in keep if x).strip()


# ★ 2026-10-08 修正：原来**写死读 09-29 那份报告**当目标清单 ——
#   拿 9 天前的「待补抓」名单当今天的目标，而期间那批资源早已被别的脚本补齐
#   ⇒ 实测它每跑一次都把**已经有内容的 40 条重新报成失败**（全是假红）。
#   改为**现算**：从 L0 台账取「飞书站内 / 裸 token」的活跃键，并排除已登记坏键。
#   `L0_FEISHU_SOURCE=report` 可退回旧口径（回退口，默认不用）。
def _is_bad_key(row):
    if not re.match(r"^https?://", (row.get("resource_key") or "").split(":", 1)[-1]):
        return True
    note = str(row.get("status_reason") or "") + str(row.get("change") or "")
    return ("坏键" in note) or ("bad_key" in note)


if os.environ.get("L0_FEISHU_SOURCE") == "report":
    rep = json.load(open("kb/l8/runs/20260929-2030-url-unified-recrawl.json", encoding="utf-8"))
    targets = [x for x in rep["results"] if not x.get("verdict", "").startswith("已重抓")]
    feishu = [x for x in targets if "feishu.cn" in x["url"] or x["resource_key"].startswith("wiki:")
              or x["resource_key"].startswith("docx:")]
    print(f"[旧口径] 待补抓 {len(targets)} 条，其中飞书类 {len(feishu)} 条")
else:
    _lat_now = {}
    for _l in open("kb/l0/manifest.jsonl", encoding="utf-8"):
        if _l.strip():
            _r = json.loads(_l)
            _lat_now[_r["resource_key"]] = _r
    feishu, _bad = [], []
    for _k, _r in _lat_now.items():
        if _r.get("status") in ("gone", "retracted"):
            continue
        if _r.get("source_kind") != "url" and not _k.startswith(("wiki:", "docx:")):
            continue
        _u = _k[4:] if _k.startswith("url:") else ""
        if "feishu.cn" not in _u and not _k.startswith(("wiki:", "docx:")):
            continue
        if _r.get("source_kind") == "url" and _is_bad_key(_r):
            _bad.append(_k)
            continue
        feishu.append({"resource_key": _k, "url": _u})
    # ★ 2026-10-08 再补一刀：只留**真的缺内容**的键。
    #   不加这条时 52 条全被选进来，其中大多数早已有 L1 产物或台账 full 指纹 ⇒ 又是假失败。
    # ★★ 同日第二轮修正：原先 `_have` 收的是「**有 L1 文件**的键」——
    #   与注释说的「缺内容」不是一回事：**0 字空壳也有文件**（status=forbidden / no_scope
    #   的那两条正是如此），于是它们被判成「不缺内容」而永不重试，脚本报「缺内容 0 条」=
    #   **假绿**。现在改为按**正文字数**判：char_count>0 才算有内容。
    _have = set()
    for _p in glob.glob("kb/l1/*/url__*.json") + glob.glob("kb/l2/by_kb/*/url__*.json"):
        try:
            _a = json.load(open(_p, encoding="utf-8"))
            if (_a.get("char_count") or 0) > 0:
                _have.add(_a["resource_key"])
        except Exception:
            pass
    _before = len(feishu)
    # ★★ 同日第三处修正：**空串 sha 不算指纹**。
    #   实测台账里有 3 条 url 键的 sha256 == sha256("")（e3b0c442…）却记着 sha256_state=full
    #   —— 那是「什么都没抽到」被当成了「抓完了」。它们因此对一切「缺内容」判据隐形，
    #   永不重试（其中 momcozy-in/file/… 与 drive/folder/… 的 L1 确实 0 字）。
    #   ⇒ 判据里把空串 sha 排除掉，让它们重新可见。根因（谁写进去的）另行登记，不在此处掩盖。
    EMPTY_SHA = hashlib.sha256(b"").hexdigest()
    feishu = [x for x in feishu
              if x["resource_key"] not in _have
              and not ((_lat_now.get(x["resource_key"], {}).get("sha256") or "") not in ("", EMPTY_SHA)
                       and str(_lat_now.get(x["resource_key"], {}).get("sha256_state")) == "full")]
    print(f"[现算] 台账里飞书类活跃键 {_before} 条 → 其中**缺内容**的 {len(feishu)} 条"
          f"（判据=正文字数 char_count>0 且台账指纹非空串；已排除坏键 {len(_bad)} 条）")

l0 = {}
for line in open("kb/l0/manifest.jsonl", encoding="utf-8"):
    if line.strip():
        r = json.loads(line)
        l0[r["resource_key"]] = r
l1_keys = set(json.loads(open("kb/l1/manifest_l1.jsonl", encoding="utf-8").readline()))
arts = {}
for f in glob.glob("kb/l1/*/url__*.json"):
    try:
        arts[json.load(open(f, encoding="utf-8"))["resource_key"]] = f
    except Exception:
        pass

out, l0rows, stored = [], [], []
for x in feishu:
    key, url = x["resource_key"], x["url"]
    ent = {"resource_key": key, "url": url}
    m = re.search(r"/(wiki|file|docx|sheets|base|drive/folder|share/base/view)/([A-Za-z0-9]+)", url)
    kind, tok = (m.group(1), m.group(2)) if m else (None, None)
    if key.startswith(("wiki:", "docx:")) and not tok:
        kind, tok = key.split(":", 1)[0], key.split(":", 1)[1]
    text, note = "", ""
    if kind == "drive/folder":
        st = sh("lark-cli", "drive", "+status", "--folder-token", tok, "--local-dir", "/tmp",
                "--as", AS_ID, "--profile", PROFILE)
        note = "drive 文件夹（容器）：" + ("可访问" if st.get("ok") else json.dumps(st.get("error"), ensure_ascii=False)[:100])
    elif kind == "share/base/view":
        ins = sh("lark-cli", "drive", "+inspect", "--url", url, "--as", AS_ID, "--profile", PROFILE)
        note = "分享视图链接：" + json.dumps((ins.get("data") or {}), ensure_ascii=False)[:120] if ins.get("ok") \
            else "分享视图链接：读取失败"
    else:
        n = sh("lark-cli", "wiki", "+node-get", "--node-token", tok, "--as", AS_ID, "--profile", PROFILE) \
            if kind in ("wiki",) or key.startswith("wiki:") else {"ok": True, "data": {"obj_token": tok, "obj_type": kind}}
        if not n.get("ok"):
            note = "wiki/对象解析失败：" + json.dumps(n.get("error"), ensure_ascii=False)[:110]
        else:
            d = n["data"]
            ot, obj = d.get("obj_type"), d.get("obj_token")
            ent["title"] = d.get("title")
            if ot == "docx":
                f = sh("lark-cli", "docs", "+fetch", "--doc", obj, "--as", AS_ID, "--profile", PROFILE)
                if f.get("ok"):
                    text = strip_html(f["data"]["document"].get("content") or "")
                    note = f"docx 正文 {len(text)} 字"
                else:
                    note = "docs +fetch 失败：" + json.dumps(f.get("error"), ensure_ascii=False)[:100]
            elif ot == "bitable":
                t = sh("lark-cli", "base", "+table-list", "--base-token", obj, "--as", AS_ID,
                       "--profile", PROFILE, "--format", "json")
                if t.get("ok"):
                    tabs = t["data"]["tables"]
                    text = "\n".join([f"{d.get('title') or obj}（bitable）"] +
                                     [f"{x['name']}（{x['id']}）记录 {x.get('records_count')}" for x in tabs])
                    note = f"bitable {len(tabs)} 张表"
                else:
                    note = "base +table-list 失败"
            elif ot == "sheet":
                m2 = sh("lark-cli", "sheets", "+workbook-info", "--spreadsheet-token", obj,
                        "--as", AS_ID, "--profile", PROFILE)
                if m2.get("ok"):
                    ss = m2["data"].get("sheets") or []
                    text = f"{d.get('title') or obj}（sheet）\n" + "\n".join(
                        f"{s.get('sheet_name')}（{s.get('sheet_id')}）{s.get('row_count')}×{s.get('column_count')}" for s in ss)
                    note = f"sheet {len(ss)} 个工作表"
                else:
                    note = "sheets 读取失败"
            elif ot == "file":
                p = f"/tmp/_ff_{tok}"
                r = sh("lark-cli", "drive", "+preview", "--file-token", obj, "--type", "source_file",
                       "--output", p, "--if-exists", "overwrite", "--as", AS_ID, "--profile", PROFILE)
                # ★★ 2026-10-08 假红根因修正：**以 lark-cli 回报的 output_path 为准**。
                #   它按真实类型给输出补扩展名 —— 实测 `--output /tmp/_ff_<tok>` 实际落成
                #   `/private/tmp/_ff_<tok>.pdf`。旧代码死看请求路径 `os.path.exists(p)`
                #   ⇒ **下载成功也判成失败**：30 条 wiki 内嵌文件全被误报成
                #   「file 取字节失败（export/预览均被拒）」，而实测同一调用 ok=true、
                #   25,243,689 字节 PDF 已落盘。判据只认回报路径，不认请求路径。
                _rp = (r.get("data") or {}).get("output_path") if r.get("ok") else None
                if _rp and os.path.exists(_rp):
                    p = _rp
                if r.get("ok") and os.path.exists(p):
                    b = open(p, "rb").read()
                    dd = f"kb/l0/attachments/材料收集/{tok}"
                    os.makedirs(dd, exist_ok=True)
                    ext = ".xlsx" if b[:2] == b"PK" and b[2:4] == b"\x03\x04" else ".bin"
                    dst = f"{dd}/{tok}{ext}"
                    shutil.copy2(p, dst)
                    stored.append({"key": key, "token": obj, "path": dst, "bytes": len(b),
                                   "sha256": hashlib.sha256(b).hexdigest()})
                    text = f"{d.get('title') or obj}（file，{len(b)} 字节，原件已存 {dst}）"
                    note = "file 原件已取（source_file 通道）"
                else:
                    note = "file 取字节失败（export/预览均被拒）"
            else:
                note = f"未处理 obj_type={ot}"
    ent.update({"chars": len(text), "note": note, "text": text})
    out.append(ent)
    if APPLY and len(text) >= 50:
        art_p = arts.get(key)
        if art_p:
            old = json.load(open(art_p, encoding="utf-8"))
            segs = [{"kind": "paragraph", "text": text, "anchor": "#正文"}]
            new = dict(old)
            new.update({"source_sha256": sha(text), "extractor_version": "l1-0.1+feishu-api-20260929",
                        "status": "ok", "status_reason": f"2026-09-29 飞书 API 补抓：{note}",
                        "segments": segs, "segment_count": len(segs), "char_count": len(text),
                        "observed_at": RUN})
            tmp = art_p + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(new, fh, ensure_ascii=False, indent=1)
            json.load(open(tmp, encoding="utf-8"))
            os.replace(tmp, art_p)
        row = l0.get(key)
        if row:
            n = dict(row)
            n.update({"sha256": sha(text), "sha256_input": "feishu_content_v1", "sha256_state": "full",
                      "sha256_prev": row.get("sha256"), "observed_at": RUN,
                      "change": "l0_feishu_url_api_recrawl", "status_reason": f"飞书 API 补抓：{note}"})
            l0rows.append(n)
    print(f"  {'✓' if len(text) >= 50 else '✗'} {url[:64]:<64} {note[:60]}")

if APPLY:
    with open("kb/l0/manifest.jsonl", "a", encoding="utf-8") as fh:
        for r in l0rows:
            fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
    print(f"\n[写入] L0 台账 +{len(l0rows)} 行（sha256_input=feishu_content_v1）| 原件入 L0 {len(stored)} 个")
json.dump({"run": RUN, "kind": "feishu_url_api_recrawl", "targets": len(feishu),
           "ok": sum(1 for x in out if x["chars"] >= 50), "results": out, "stored": stored},
          open(f"kb/l8/runs/{RUN}-feishu-url-recrawl.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"报告 kb/l8/runs/{RUN}-feishu-url-recrawl.json")
