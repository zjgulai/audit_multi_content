#!/usr/bin/env python3
"""把非记录类资源的「内容已变（drift）」同步进 L0（L0 = 飞书副本）。

本轮核验发现 4 条 drift（kb/l8/runs/20260929-1350-l0-nonrecord-verify.json）：
  wiki:Vzlwd1d9doXdJJxkJnWc4ya5ngb  docx「Meta近期在投文案」 rev 168 → 175
  docx:W2KodnZP3orVrAxxn5OcbmKtnxh  docx                      rev ?   → 4
  sheets:KzQ1sLVCbhFCIktRkdec9Onen6e 表格                    rev ?   → 422（原 no_scope，本轮首次读到）
  wiki:EsCdw2A7tiz67Rk8LgMce2TAnEh   表格                    rev ?   → 51

做法：抓最新内容 → 旧文件归档 → 按 L0 资源文件的 24 键结构重写 → 复验（读回 + 断言键集）
口径诚实性：原 doc 行 sha256_input="doc_text"（旧抓取器的正文口径，本轮实测 3 种常见口径都复现不了）。
           本次记 sha256_input="doc_text_refresh_v1" 并把旧摘要存进 sha256_prev —— 不冒充原口径。
用法：python3 kb/l8/refresh_l0_drifted.py 20260929-1400 [--apply]
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

import hashlib
import html as H
import json
import os
import re
import shutil
import subprocess
import sys

RUN = sys.argv[1] if len(sys.argv) > 1 else "20260929-1400"
APPLY = "--apply" in sys.argv
AS_ID, PROFILE = os.environ.get("L8_AS", "user"), os.environ.get("L8_PROFILE", "dsh-kb")
ENV = dict(os.environ, PATH=os.path.expanduser("~/.dsh/bin") + ":" + os.environ.get("PATH", ""))
ARCH = f"kb/l0/_archive/nonrecord-drift-refresh-{RUN}"

TARGETS = [
    ("wiki:Vzlwd1d9doXdJJxkJnWc4ya5ngb", "kb/l0/2_内部正负样本库/feishu_doc__Vzlwd1d9doXdJJxkJnWc4ya5ngb.json"),
    ("docx:W2KodnZP3orVrAxxn5OcbmKtnxh", "kb/l0/9_未归类/feishu_doc__W2KodnZP3orVrAxxn5OcbmKtnxh.json"),
    ("sheets:KzQ1sLVCbhFCIktRkdec9Onen6e", "kb/l0/4_产品描述库/feishu_sheet__KzQ1sLVCbhFCIktRkdec9Onen6e.json"),
    ("wiki:EsCdw2A7tiz67Rk8LgMce2TAnEh", "kb/l0/4_产品描述库/feishu_sheet__EsCdw2A7tiz67Rk8LgMce2TAnEh.json"),
]


def sh(*a):
    p = subprocess.run(list(a), capture_output=True, text=True, encoding="utf-8",
                       errors="replace", env=ENV, timeout=600)
    try:
        return json.loads(p.stdout)
    except Exception:
        return {"ok": False, "error": {"message": (p.stdout or p.stderr)[:160]}}


def strip_html(h):
    h = re.sub(r"<(title|h1|h2|h3|h4|p|li|br|tr|/p|/li|/h1|/h2|/h3|/h4)[^>]*>", "\n", h)
    h = re.sub(r"</t[dh]>", "\t", h)
    h = re.sub(r"<[^>]+>", "", h)
    return re.sub(r"\n{2,}", "\n", H.unescape(h)).strip()


summary = []
refreshed_rows = []          # 见文件尾「刷新结果必须追加进台账」那一段
for key, path in TARGETS:
    old = json.load(open(path, encoding="utf-8"))
    keyset = set(old)
    tok = key.split(":", 1)[1]
    kind = old["source_kind"]
    text, rev, note = None, None, ""
    if kind == "feishu_doc":
        obj = tok
        if key.startswith("wiki:"):
            n = sh("lark-cli", "wiki", "+node-get", "--node-token", tok, "--as", AS_ID, "--profile", PROFILE)
            if not n.get("ok"):
                print(f"  ✗ {key} wiki 解析失败"); continue
            obj = n["data"]["obj_token"]
        f = sh("lark-cli", "docs", "+fetch", "--doc", obj, "--as", AS_ID, "--profile", PROFILE)
        if not f.get("ok"):
            print(f"  ✗ {key} docs +fetch 失败"); continue
        doc = f["data"].get("document") or {}
        text = strip_html(doc.get("content") or "")
        rev = f["data"].get("revision_id") or doc.get("revision_id") or doc.get("revision")
        note = f"正文 {len(text)} 字；标题={doc.get('title')}"
    elif kind == "feishu_sheet":
        obj = tok
        if key.startswith("wiki:"):
            n = sh("lark-cli", "wiki", "+node-get", "--node-token", tok, "--as", AS_ID, "--profile", PROFILE)
            if n.get("ok"):
                obj = n["data"]["obj_token"]
        m = sh("lark-cli", "sheets", "+workbook-info", "--spreadsheet-token", obj, "--as", AS_ID, "--profile", PROFILE)
        if not m.get("ok"):
            print(f"  ✗ {key} workbook-info 失败"); continue
        rev = (m["data"].get("spreadsheet") or {}).get("revision") or m["data"].get("revision")
        sheets_ = (m["data"].get("sheets") or m["data"].get("sheet_list") or [])
        chunks = []
        for s in sheets_:
            sid, nm = s.get("sheet_id") or s.get("id"), s.get("title") or s.get("name")
            rows = (s.get("grid_properties") or {}).get("row_count") or 200
            c = sh("lark-cli", "sheets", "+cells-get", "--spreadsheet-token", obj, "--sheet-id", str(sid),
                   "--range", f"A1:Z{min(int(rows), 500)}", "--as", AS_ID, "--profile", PROFILE)
            if c.get("ok"):
                chunks.append({"sheet": nm, "sheet_id": sid, "cells": c.get("data")})
        if not chunks:
            print(f"  ✗ {key} 单元格读取失败"); continue
        text = json.dumps(chunks, ensure_ascii=False, sort_keys=True)
        note = f"{len(chunks)} 个工作表"
    h = hashlib.sha256(text.encode("utf-8")).hexdigest()
    new = json.loads(json.dumps(old, ensure_ascii=False))
    new.update({"sha256": h, "sha256_input": "doc_text_refresh_v1" if kind == "feishu_doc" else "sheet_cells_refresh_v1",
                "sha256_state": "full", "revision": rev, "status": "updated",
                "status_reason": f"非记录类核验发现 drift（rev {old.get('revision')} → {rev}），本批重抓同步；"
                                 f"摘要口径为 {RUN} 的刷新器（与原行 sha256_input 口径不同，原值存 sha256_prev）",
                "sha256_prev": old.get("sha256"), "sha256_input_prev": old.get("sha256_input"),
                "observed_at": RUN, "refreshed_at": RUN, "change": "l0_nonrecord_drift_refresh"})
    assert set(old) <= set(new)
    refreshed_rows.append(new)
    ent = {"resource_key": key, "file": path, "rev_before": old.get("revision"), "rev_after": rev,
           "sha256_before": old.get("sha256"), "sha256_after": h, "chars": len(text), "note": note}
    summary.append(ent)
    print(f"  ✓ {key} rev {old.get('revision')} → {rev}；{note}")
    if APPLY:
        os.makedirs(ARCH, exist_ok=True)
        dst = f"{ARCH}/{os.path.basename(path)}"
        shutil.copy2(path, dst)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(new, fh, ensure_ascii=False, indent=2)
        back = json.load(open(tmp, encoding="utf-8"))
        assert set(back) >= keyset and back["sha256"] == h
        os.replace(tmp, path)

# ── ★ 2026-10-09 接线：刷新结果**必须**追加进台账 ──────────────────────────────
# 病灶（实测）：本脚本把 `sha256_state: full` 写进**资源文件**（上面那个 `path`），
# 但**以前从不追加 `kb/l0/manifest.jsonl`** —— 而**全库读的是台账的最新行**。
# 结果：`sheets:KzQ1sLVCbhFCIktRkdec9Onen6e` 的**资源文件**早已是
# `full` / `sheet_cells_refresh_v1` / `revision 422`，**台账却永远停在 `no_scope`**
# （实测：自 20260923 起一直没变，20260929 与 20261009 两次核验都只是原样重报）。
# 连 `close_stale_scope_gaps.py` 也认不出它 —— 那个脚本要求 `no_scope` **且** reason 含「缺少」，
# 而后来的 verify 行把 reason 改成了「非记录类核验：ok」，关键词就丢了。
# ⇒ 用户会在缺口清单里看到一条**其实早就修好的**欠账。
# 与 `store_l0_attachments` / `verify_l0_urls` / `verify_l0_nonrecord2` **同形**：
# 写了资源件的刷新器，就要把那一行也记进台账（走库内既有去重器，未变的只刷 last_seen）。
if APPLY and refreshed_rows:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import l0_ledger as _l0_ledger
    _led = _l0_ledger.append_changed("kb/l0/manifest.jsonl", refreshed_rows, run=RUN)
    print(f"[台账] 追加 {_led['appended']} 行；跳过 {_led['skipped_unchanged']} 行（未变，已记 last_seen）")
elif refreshed_rows:
    print(f"[台账] 【干跑】将追加 {len(refreshed_rows)} 行（未变的不写）")

rep = {"run": RUN, "layer": "l0", "kind": "nonrecord_drift_refresh", "identity": f"{AS_ID}/{PROFILE}",
       "targets": summary, "archive": ARCH if APPLY else None,
       "note": "L0 内非记录类资源按飞书最新内容刷新；旧文件已归档（不删除）；摘要口径变化如实标注"}
json.dump(rep, open(f"kb/l8/runs/{RUN}-l0-nonrecord-refresh.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print(f"[{ '已刷新' if APPLY else '预演'}] {len(summary)}/4 条")
