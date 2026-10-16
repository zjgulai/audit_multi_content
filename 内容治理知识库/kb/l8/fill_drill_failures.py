#!/usr/bin/env python3
"""补齐 20260929-1100 那次下钻失败的 5 条飞书侧边（用户身份）。

背景：kb/l1/sources/20260929-1100.jsonl 里 7 条 fail：
  · 5 条飞书侧（2 sheets / 2 wiki / 1 docx）—— 当时 bot 身份无权限，现已用用户身份打通
  · 2 条 Google 域外链接（csp.withgoogle.com / googleusercontent）—— 非飞书侧，按口径不抓，保持排除

产物：kb/l1/sources/<RUN>.jsonl（同 schema）+ 每条一个 .md 产物
      .md 用「python 写临时文件 → /bin/cp 落盘 → 首字节断言」避免信封（见 kb/l8/runs 的封装问题记录）
用法：python3 kb/l8/fill_drill_failures.py 20260929-1255 [--apply]
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
import subprocess
import sys

RUN = sys.argv[1] if len(sys.argv) > 1 else "20260929-1255"
APPLY = "--apply" in sys.argv
SRC = "kb/l1/sources/20260929-1100.jsonl"
OUT_SRC = "kb/l1/sources"
AS_ID, PROFILE = "user", "dsh-kb"
ENV = dict(os.environ, PATH=os.path.expanduser("~/.dsh/bin") + ":" + os.environ.get("PATH", ""))


def sh(*args):
    p = subprocess.run(list(args), capture_output=True, text=True, encoding="utf-8",
                       errors="replace", env=ENV, timeout=600)
    try:
        return json.loads(p.stdout)
    except Exception:
        return {"ok": False, "error": {"message": (p.stdout or p.stderr)[:200]}}


def strip_html(h):
    h = re.sub(r"<(title|h1|h2|h3|h4|p|li|br|tr|/p|/li|/h1|/h2|/h3|/h4)[^>]*>", "\n", h)
    h = re.sub(r"</t[dh]>", "\t", h)
    h = re.sub(r"<[^>]+>", "", h)
    return re.sub(r"\n{2,}", "\n", H.unescape(h)).strip()


def write_md(path, text):
    tmp = "/tmp/_l8_md.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(text)
    subprocess.run(["/bin/cp", tmp, path], check=True)
    with open(path, "rb") as fh:
        first = fh.read(1)
    assert first in (b"#", b"<", b"[", b"-", b"(") or first.isalnum(), f"{path} 疑似信封: {first!r}"
    return hashlib.sha256(open(path, "rb").read()).hexdigest(), os.path.getsize(path)


rows = [json.loads(l) for l in open(SRC, encoding="utf-8") if l.strip()]
bad = [r for r in rows if r["status"] != "ok"]
feishu = [r for r in bad if r["to_id"].split(":")[0] in ("sheets", "wiki", "docx")
          and "google" not in (r.get("url") or "").lower()]
print(f"[输入] 失败边 {len(bad)} → 飞书侧 {len(feishu)}，域外保留排除 {len(bad)-len(feishu)}")

out, arts = [], []
for r in feishu:
    kind, tok = r["to_id"].split(":", 1)
    status, note, text = "fail", "", ""
    if kind == "wiki":
        n = sh("lark-cli", "wiki", "+node-get", "--node-token", tok, "--as", AS_ID, "--profile", PROFILE)
        if n.get("ok"):
            d = n["data"]
            obj_type, obj_token, title = d.get("obj_type"), d.get("obj_token"), d.get("title")
            if obj_type == "docx":
                f = sh("lark-cli", "docs", "+fetch", "--doc", obj_token, "--as", AS_ID, "--profile", PROFILE)
                if f.get("ok"):
                    text = f"# {title}\n\n> 来自 wiki 节点 {tok}（{obj_type}:{obj_token}）\n\n" + strip_html(f["data"]["document"]["content"])
                    status = "ok"
                else:
                    note = f"docs +fetch 失败：{f.get('error',{}).get('message','')[:100]}"
            elif obj_type == "bitable":
                tl = sh("lark-cli", "base", "+table-list", "--base-token", obj_token, "--as", AS_ID, "--profile", PROFILE)
                if tl.get("ok"):
                    lines = [f"# {title}", "", f"> 来自 wiki 节点 {tok}（{obj_type}:{obj_token}）", "",
                             "| 表 | table_id | 记录数 |", "|---|---|---|"]
                    for t in tl["data"]["tables"]:
                        lines.append(f"| {t['name']} | `{t['id']}` | {t.get('records_count')} |")
                    text = "\n".join(lines) + "\n"
                    status = "ok"
                else:
                    note = f"base +table-list 失败：{tl.get('error',{}).get('message','')[:100]}"
            else:
                text = f"# {title}\n\n> wiki 节点 {tok} → obj_type={obj_type} obj_token={obj_token}\n"
                status = "ok"
        else:
            note = f"wiki +node-get 失败：{n.get('error',{}).get('message','')[:100]}"
    elif kind == "docx":
        f = sh("lark-cli", "docs", "+fetch", "--doc", tok, "--as", AS_ID, "--profile", PROFILE)
        if f.get("ok"):
            text = strip_html(f["data"]["document"]["content"])
            status = "ok"
        else:
            note = f"docs +fetch 失败：{f.get('error',{}).get('message','')[:100]}"
    elif kind == "sheets":
        m = sh("lark-cli", "sheets", "+workbook-info", "--spreadsheet-token", tok, "--as", AS_ID, "--profile", PROFILE)
        if m.get("ok"):
            title = (m.get("data", {}).get("spreadsheet", {}) or {}).get("title") or (m.get("data", {}) or {}).get("title")
            sheets_ = (m.get("data", {}) or {}).get("sheets") or (m.get("data", {}) or {}).get("sheet_list") or []
            lines = [f"# {title or tok}", "", f"> 电子表格 `{tok}`", ""]
            got = False
            for s in sheets_:
                sid = s.get("sheet_id") or s.get("id")
                nm = s.get("title") or s.get("name")
                rng = s.get("grid_properties", {}).get("row_count") if isinstance(s.get("grid_properties"), dict) else None
                last = min(int(rng), 300) if rng else 200
                c = sh("lark-cli", "sheets", "+cells-get", "--spreadsheet-token", tok,
                       "--sheet-id", str(sid), "--range", f"A1:Z{last}", "--as", AS_ID, "--profile", PROFILE)
                if c.get("ok"):
                    lines += [f"## {nm}（{sid}）", "", "```json",
                              json.dumps(c.get("data"), ensure_ascii=False)[:80000], "```", ""]
                    got = True
                else:
                    lines += [f"## {nm}（{sid}）", "", f"（读取失败：{c.get('error',{}).get('message','')[:120]}）", ""]
            text = "\n".join(lines) + "\n"
            status = "ok" if got else "fail"
            if not got:
                note = "sheets 内容读取失败"
        else:
            note = f"sheets 无权限：{m.get('error',{}).get('message','')[:120]}"

    row = dict(r)
    row.update({"run": RUN, "status": status, "observed_at": RUN})
    if status == "ok":
        art = f"{OUT_SRC}/{RUN}__{r['to_id'].replace(':', '-')}.md"
        sha, nbytes = write_md(art, text) if APPLY else (hashlib.sha256(text.encode()).hexdigest(), len(text.encode()))
        row.update({"sha256": sha, "bytes": nbytes, "artifact": art, "note": "20260929-1100 fail → 用户身份重取成功"})
        arts.append(art)
    else:
        row["note"] = note
    out.append(row)
    print(f"  {'✓' if status=='ok' else '✗'} depth={r['depth']} {r['from_id']} → {r['to_id']}  {note}")

if APPLY:
    with open(f"{OUT_SRC}/{RUN}.jsonl", "w", encoding="utf-8") as fh:
        for r in out:
            fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
    rep = {"run": RUN, "at": RUN, "rule": "补齐 20260929-1100 下钻失败的飞书侧边（用户身份）",
           "input_fail": len(bad), "feishu_fixed": sum(1 for r in out if r["status"] == "ok"),
           "still_fail": sum(1 for r in out if r["status"] != "ok"),
           "excluded_non_feishu": len(bad) - len(feishu),
           "excluded_detail": "Google 域外链接 2 条（csp.withgoogle.com / googleusercontent）按口径不抓",
           "artifacts": arts}
    json.dump(rep, open(f"{OUT_SRC}/{RUN}.report.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\n[写入] {OUT_SRC}/{RUN}.jsonl（{len(out)} 行）+ report；产物 {len(arts)} 个")
else:
    print("\n未写入（加 --apply）")
