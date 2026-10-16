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
AS_ID, PROFILE = os.environ.get("L8_AS", "user"), os.environ.get("L8_PROFILE", "dsh-kb")
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


rep = json.load(open("kb/l8/runs/20260929-2030-url-unified-recrawl.json", encoding="utf-8"))
targets = [x for x in rep["results"] if not x.get("verdict", "").startswith("已重抓")]
feishu = [x for x in targets if "feishu.cn" in x["url"] or x["resource_key"].startswith("wiki:")
          or x["resource_key"].startswith("docx:")]
print(f"待补抓 {len(targets)} 条，其中飞书类 {len(feishu)} 条")

l0 = {}
for line in open("kb/l0/manifest.jsonl", encoding="utf-8"):
    if line.strip():
        r = json.loads(line)
        l0[r["resource_key"]] = r
l1_keys = set(json.loads(open("kb/l1/manifest_l1.jsonl", encoding="utf-8").readline()))
arts = {}
import glob
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
