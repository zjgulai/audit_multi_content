#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""规则②：材料链接**下钻两层**读取 —— 产物落 L1，不动 L0。

用户 2026-09-29 口径：
  ① L0 只跟飞书侧对齐；优化 L1–L7 时**不得动 L0** → 所以下钻产物写 `kb/l1/sources/`，
     不写既有的 `kb/l0/snapshots/`、也不追加 `kb/l0/links/graph.jsonl`（那两处属 L0 口径）。
  ② 链接要下钻两层：level 1 = 记录里的「材料链接」；level 2 = level-1 正文里出现的链接。

读法（与既有 L1 的 feishu_ops 一致）：
  · wiki:<node_token>   → `lark-cli wiki +node-get` 取 obj_token → 再按类型读
  · docx:<token>        → `lark-cli docs +fetch`
  · sheets:<token>      → `lark-cli sheets +meta` + `+read`（读首个工作表）
  · base/share 链接     → `HTTP GET`（curl）
  · 其他 URL            → `HTTP GET`（curl）
身份：应用身份（--as bot --profile dsh-kb），只读。

用法：python3 kb/l8/drill_links_2levels.py <run_id>
产物：kb/l1/sources/<run>.md（每份 level-1/2 正文快照）
      kb/l1/sources/<run>.jsonl（边表：record → level1 → level2，含 sha256/字节/host）
      kb/l1/sources/<run>.report.json（统计）
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
import json
import os
import re
import subprocess
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), ".work"))
# ★ 2026-10-09：本脚本写的 `kb/l1/sources/<RUN>__*.md` 是 `# 活路径` ——
#   python 直写会让宿主（含 agent 的 read 工具）多看到 4096 字节 ⇒ 读成 binary。
#   实测当天 73 个此类文件把 envelope_census 顶成 FAIL。只许走安全写盘通道。
import _safe_write as _sw              # noqa: E402

WS = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
os.chdir(WS)
LARK = os.path.expanduser("~/.dsh/bin/lark-cli")
# ── 干跑档 · 开关解析（P0-3d · 2026-09-29 补）───────────────────────────────
# 必须早于 RUN 解析：把 --apply 从 argv 里剔除，避免它被当成位置参数 run_id。
APPLY = "--apply" in sys.argv
if APPLY:
    sys.argv.remove("--apply")
# ──────────────────────────────────────────────────────────────────────────
RUN = sys.argv[1] if len(sys.argv) > 1 else time.strftime("%Y%m%d-%H%M")
OUT = "kb/l1/sources"
# ── 干跑档 · 落盘闸门（P0-3d · 2026-09-29 补）───────────────────────────────
# 位次判据：闸门必须早于本脚本的**第一个副作用**。本脚本副作用依次是
# ① 建 kb/l1/sources/ ② 调 lark-cli / curl 下钻读取 ③ 写正文快照与边表。
# 补档原因：它写的是 **kb/l1/sources/ 的 L1 数据**（不是「只写下钻报告」）——原先运行即写盘，
# 而早前 P0-3 的清单照 layers.yaml 一条错注释排范围，把它漏掉了。
if not APPLY:
    print("[dry-run] %s 未落盘。" % _os.path.basename(_os.path.abspath(__file__)))
    print("[dry-run] 本脚本会写入：L1 下钻：建 kb/l1/sources/、写 <run>__L1-<rid>.md 正文快照、"
          "<run>.jsonl 边表、<run>.report.json 统计")
    print("[dry-run] 加 --apply 才落盘（补档原因：原先运行即写盘，已发生过一次未授权写入）")
    _sys.exit(0)
# ──────────────────────────────────────────────────────────────────────────
os.makedirs(OUT, exist_ok=True)
ENV = dict(os.environ, PATH=os.path.expanduser("~/.dsh/bin") + ":" + os.environ.get("PATH", ""))
sha = lambda b: hashlib.sha256(b).hexdigest()
URL_RE = re.compile(r"https?://[^\s)\]\"'<>）】，。；]+")
edges, stats = [], {"level1_ok": 0, "level1_fail": 0, "level2_ok": 0, "level2_fail": 0, "records": 0}


def cli(*args):
    p = subprocess.run([LARK, *args, "--as", "bot", "--profile", "dsh-kb"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", env=ENV)
    return p.returncode, p.stdout + p.stderr


def curl(url):
    p = subprocess.run(["curl", "-sL", "--max-time", "25", "-A", "Mozilla/5.0", url],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", env=ENV)
    return p.returncode, p.stdout


def link_kind(url):
    m = re.search(r"/(wiki|docx|docs|sheets|base|file|drive)/([A-Za-z0-9]+)", url)
    if m:
        return m.group(1), m.group(2)
    if "feishu.cn" in url or "larksuite" in url:
        return "feishu-other", ""
    return "web", ""


def doc_text_of(out):
    """`lark-cli docs +fetch` 的返回 → **纯正文**。

    ★ 2026-10-13 加。为什么必须要它：`docs +fetch` 返回的是
      `{"ok":true,"identity":"bot","data":{"document":{"content":"<h3>…</h3><p>…</p>",
       "document_id":"…","revision_id":36}},"_notice":{…}}`
      —— **正文是 `data.document.content` 里的 HTML**，不是这个 JSON 信封本身。
      而在此之前**没有任何一层解包**：信封被当正文一路写进 `kb/l1/sources/*.md`、
      再被 `land_drill_into_l1.py` 落成 L1 产物、再被 L2 切成单元。
      实测（2026-10-13）：`kb/l1/sources` 的 `L1-*` 产物 **312/481 份**正文以 `{` 开头；
      `kb/l1/1_外部标准库/url__*.json` 亦然。
      ⇒ 解不出信封就**原样返回**（不抛错、不静默丢内容 —— 宁可留一次可见的失败）。
    """
    try:
        d = json.loads(out[out.index("{"):])
    except Exception:
        return out
    c = ((d.get("data") or {}).get("document") or {}).get("content")
    if not isinstance(c, str) or not c.strip():
        return out
    # HTML → 文本：保住**条款结构**（标题/列表），否则 L2 切不出条款、L3 锚不上位置。
    t = re.sub(r"<h([1-6])[^>]*>", lambda m: "\n\n" + "#" * int(m.group(1)) + " ", c)
    t = re.sub(r"</h[1-6]>", "\n", t)
    t = re.sub(r"<li[^>]*>", "\n- ", t)
    t = re.sub(r"</li>", "", t)
    t = re.sub(r"<br\s*/?>", "\n", t)
    t = re.sub(r"</(p|tr|div)>", "\n", t)
    t = re.sub(r"</t[dh]>", " | ", t)
    t = re.sub(r"<[^>]+>", "", t)
    for _a, _b in (("&nbsp;", " "), ("&lt;", "<"), ("&gt;", ">"), ("&quot;", '"'),
                   ("&#39;", "'"), ("&amp;", "&")):
        t = t.replace(_a, _b)
    t = re.sub(r"[ \t]+\n", "\n", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def fetch(url):
    """读一份链接 → (kind, title, text, token)。全部只读。"""
    kind, token = link_kind(url)
    if kind == "wiki":
        rc, out = cli("wiki", "+node-get", "--node-token", token)   # 修正：--token 已废弃
        obj = ""
        try:
            d = json.loads(out[out.index("{"):])
            # ★ 2026-10-13 修：返回体是 **`data.obj_token`**（无 `node` 包装）。
            #   实测 `wiki +node-get --node-token NB55wAq8liEOdKkquL2cgtPEnmg --as bot` 原样返回：
            #     {"ok":true,"identity":"bot","data":{"node_token":"NB55…","obj_token":"PXfBdjTw…",
            #                                         "obj_type":"docx","title":"内容审查 Agent PRD",…}}
            #   而旧码只读 `data.node.obj_token` ⇒ 恒为 "" ⇒ 掉到最后一条 `return "wiki"`，
            #   **把 node-get 的原始 JSON 当正文写进产物**，且 `ok = 非空 ∧ 无 error` 判**绿**。
            #   ⇒ 这类失败是**静默的**：产物有文件、统计 ok、正文是 JSON。
            #   两种形状都认（旧形状留着，避免本版 lark-cli 回退时又断）。
            _d = d.get("data") or {}
            _n = _d.get("node") or {}
            obj = _d.get("obj_token") or _n.get("obj_token") or ""
            otype = _d.get("obj_type") or _n.get("obj_type") or ""
            title = _d.get("title") or _n.get("title") or ""
        except Exception:
            otype, title = "", ""
        if obj and otype in ("docx", "doc"):
            rc2, out2 = cli("docs", "+fetch", "--doc", obj)   # ★ 2026-10-10 修：--token → --doc
            return "wiki→docx", title, doc_text_of(out2), obj
        if obj:
            return f"wiki→{otype or '?'}", title, out, obj
        return "wiki", title, out, token
    if kind in ("docx", "docs"):
        # ★ 2026-10-10 修：`--token` 已废弃 → `--doc`。实测该参数会让 lark-cli 直接返回
        #   `unknown flag "--token"` 报错 JSON，而**报错正文照样被写进产物文件**
        #   ⇒ 9 条 momcozy-in 链接因此判 fail（含 ⑧ 母婴设计常识清单的 docx）。
        rc, out = cli("docs", "+fetch", "--doc", token)
        return "docx", "", doc_text_of(out), token
    if kind == "sheets":
        # ★ 2026-10-10 修：`+workbook-meta` / `+read` 在本版 lark-cli 里不存在
        #   → 改 `+workbook-info` / `+cells-get`（两者已 --help 核实）。
        rc, meta = cli("sheets", "+workbook-info", "--spreadsheet-token", token)
        rc2, body = cli("sheets", "+cells-get", "--spreadsheet-token", token, "--range", "A1:Z200")
        return "sheets", "", meta + "\n" + body, token
    rc, out = curl(url)
    return kind, "", out, token


def save(tag, url, kind, title, text):
    b = text.encode("utf-8")
    name = f"{RUN}__{tag}.md"
    p = os.path.join(OUT, name)
    _sw.write_text(p, f"---\nsource_url: {url}\nkind: {kind}\ntitle: {title}\nfetched_at: {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
                      f"sha256: {sha(b)}\nbytes: {len(b)}\nrun: {RUN}\n---\n\n{text}\n")
    return os.path.relpath(p, WS), sha(b), len(b)


records = []
# ── 源清单（2026-10-10 扩源）────────────────────────────────────────────────
# 为什么要扩：原实现**只扫「材料收集」一张表、只读「材料链接」一个字段** ⇒
#   ⑥「APP资料库索引-睡眠RAG」（`kb/l0/records/外部资料库__数据表/`，base
#   `N2qkb2YxuatqGLsa4U4cFQxgnCe` / 表 `tblGFyycMc45RMga`）的 URL 落在
#   **「文件/链接」「资料名称」**两个字段里，**引擎盖不到它** —— 所以那 30 条带 URL 的记录
#   一直没被下钻，而 Owner 决策 2 明写「对 84 条带 URL 的记录做下钻，取它索引的真实资料」。
# 纪律：**只扩源，不改已有一张表的行为** —— 同表同字段、逐条追加；
#   产物落点/命名/边表形状一律不动（否则下游读者会断）。
SOURCES = [
    # (L0 记录目录名, 装 URL 的字段名列表)
    ("材料收集", ["材料链接"]),
    ("外部资料库__数据表", ["文件/链接", "资料名称"]),
]
for _tbl, _fields in SOURCES:
    for p in sorted(__import__("glob").glob(f"kb/l0/records/{_tbl}/*.json")):
        try:
            d = json.load(open(p, encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for _fn in _fields:
            val = ((d.get("fields") or {}).get(_fn) or {}).get("value")
            if not val:
                continue
            raw = val if isinstance(val, str) else json.dumps(val, ensure_ascii=False)
            if URL_RE.search(raw):
                records.append((d.get("record_id") or "", raw, _tbl, _fn))
# ── 登记件种子（2026-10-13 加）───────────────────────────────────────────────
# 为什么加：`kb/l7/registry/source-readonly.yaml → resources` 里登记着**独立登记的
#   源侧对象**（内容审查 Agent PRD，wiki→docx）。它**不在任何受控表里**，也没有
#   `kb/l0/records/` 记录与 `fields` blob ⇒ 上面那个「(表, 字段)」种子形状**盖不到它**。
#   实测后果：PRD 一直没被下钻 ⇒ L0 无记录、L1 无正文、L3 无规则、无条款号。
# 选择器**精确自限**：只取 L0 台账里 `rule_eligible_source == registered_source` 的行 ——
#   既有 10 条 `feishu_doc` 记录是 `material_collection_child_inherited`（表链接派生），
#   **一条都不碰**；将来新登记的源侧对象**自动**进来，不必回来改本件。
# 纪律：**只加一类种子，不改已有两张表的行为** —— 同表同字段、逐条追加；
#   产物落点/命名/边表形状一律不动。
REGISTERED_LABEL = "已登记来源"
for _ln in open("kb/l0/manifest.jsonl", encoding="utf-8"):
    if not _ln.strip():
        continue
    try:
        _m = json.loads(_ln)
    except ValueError:
        continue
    if (_m.get("source_kind") != "feishu_doc"
            or _m.get("rule_eligible_source") != "registered_source"
            or _m.get("status") in ("gone", "retracted")):
        continue
    _u = _m.get("entry_url")
    if not _u or not URL_RE.search(_u):
        continue
    # `resource_id` **不在 manifest 键集里**（manifest 行是固定 24 键，无 `source`）——
    # 实测踩过：从 manifest 读 `source.resource_id` 恒为空 ⇒ 退回 `resource_key`
    # ⇒ 文件名叫 `L1-docx:PXfBdjTw…`（带冒号，且丢掉了人可读的登记 id）。
    # 回 **L0 记录件**取（L0 是权威，`source` 块在那里面）。
    _rid, _rkind = "", ""
    for _rp in __import__("glob").glob("kb/l0/*/feishu_doc__*.json"):
        try:
            _rd = json.load(open(_rp, encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if _rd.get("resource_key") == _m.get("resource_key"):
            _s = _rd.get("source") or {}
            _rid, _rkind = _s.get("resource_id") or "", _s.get("resource_kind") or ""
            break
    records.append((_rid or _m.get("resource_key") or _u, _u,
                    REGISTERED_LABEL, _rkind or "feishu_wiki_docx"))

stats["records"] = len(records)
from collections import Counter as _C
print(f"[下钻] 待处理记录 {len(records)} 条｜按源：{dict(_C((r[2], r[3]) for r in records))}")

# ── 产物命名（★ 2026-10-10 修：一条记录出多个 URL 时不许互相覆盖）───────────────
# 病灶：`save(f"L1-{rid}", ...)` 是**一条记录一个文件名**。原来源只有「材料收集 × 材料链接」
#   一个字段 ⇒ 每条记录至多 1 个 URL，**撞不上**。扩源到 ⑥（「文件/链接」+「资料名称」
#   两个字段）后，**同一条记录会出 2 个 URL ⇒ 第二个把第一个的正文覆盖掉** ——
#   实测本次 64 条 level-1 边只落 52 个文件，**12 份正文被覆盖丢失**。
# 修法：同一记录出**多个** URL 时，文件名带上 **URL 的短哈希**（内容派生、可复算、
#   与行序无关）；只出 1 个 URL 时**沿用旧名 `L1-{rid}`**（既有下游按 `L1-<rid>` 解析的
#   读者不受影响）。
_rid_n = _C(r[0] for r in records)


def _tag1(rid, url):
    return (f"L1-{rid}" if _rid_n.get(rid, 1) <= 1
            else f"L1-{rid}-{sha(url.encode('utf-8'))[:8]}")


for rid, raw, _tbl, _fn in records:
    # 登记件种子与表记录种子的**来源身份不同**，边表里必须如实分开记 ——
    # 否则下游读 `from_id: record:…` 会去找一条根本不存在的表记录。
    _is_reg = (_tbl == REGISTERED_LABEL)
    _from_id = f"source:{rid}" if _is_reg else f"record:{rid}"
    _from_kind = "registered_source" if _is_reg else "feishu_bitable_record"
    m = URL_RE.search(raw)
    if not m:
        continue
    url1 = m.group(0)
    kind, title, text, token = fetch(url1)
    ok = len(text.strip()) > 0 and "error" not in text[:200].lower()
    stats["level1_ok" if ok else "level1_fail"] += 1
    f1, h1, b1 = save(_tag1(rid, url1), url1, kind, title, text)
    edges.append({"run": RUN, "depth": 1, "from_id": _from_id, "from_kind": _from_kind,
                  "from_table": _tbl, "label": _fn, "field_id": None, "to_id": f"{kind}:{token or url1}",
                  "url": url1, "status": "ok" if ok else "fail", "sha256": h1, "bytes": b1,
                  "artifact": f1, "observed_at": RUN})
    # level 2：从 level-1 正文里再取链接（最多 5 条，去重、排除自身）
    seen, n2 = set(), 0
    for url2 in URL_RE.findall(text):
        if url2 == url1 or url2 in seen or n2 >= 5:
            continue
        seen.add(url2)
        k2, t2, txt2, tok2 = fetch(url2)
        ok2 = len(txt2.strip()) > 0 and "error" not in txt2[:200].lower()
        stats["level2_ok" if ok2 else "level2_fail"] += 1
        f2, h2, b2 = save(f"L2-{rid}-{n2+1}", url2, k2, t2, txt2)
        edges.append({"run": RUN, "depth": 2, "from_id": f"{kind}:{token or url1}", "from_kind": kind,
                      "label": "正文内链接", "field_id": None, "to_id": f"{k2}:{tok2 or url2}",
                      "url": url2, "status": "ok" if ok2 else "fail", "sha256": h2, "bytes": b2,
                      "artifact": f2, "observed_at": RUN})
        n2 += 1

with open(os.path.join(OUT, f"{RUN}.jsonl"), "w", encoding="utf-8") as fh:
    for e in edges:
        fh.write(json.dumps(e, ensure_ascii=False) + "\n")
rep = {"run": RUN, "at": time.strftime("%Y-%m-%d %H:%M:%S"), "rule": "链接下钻两层（用户 2026-09-29 口径②）",
       "l0_untouched": True, "output_dir": OUT, "stats": stats, "edges": len(edges),
       "by_status": {s: sum(1 for e in edges if e["status"] == s) for s in ("ok", "fail")}}
json.dump(rep, open(os.path.join(OUT, f"{RUN}.report.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"[下钻] 完成：记录 {stats['records']} | level1 ok/fail {stats['level1_ok']}/{stats['level1_fail']} "
      f"| level2 ok/fail {stats['level2_ok']}/{stats['level2_fail']} | 边 {len(edges)}")
print(f"       产物 → {OUT}/{RUN}.jsonl 与 {OUT}/{RUN}.report.json（L0 未改动）")
