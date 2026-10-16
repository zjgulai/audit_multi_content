#!/usr/bin/env python3
"""关掉「登记时缺 scope、从未读内容」的 L0 缺口（只补登记与指纹，不改飞书、不删旧行）。

## 背景

L0 台账里有若干早期行写着「缺少 xxx:read scope（已实测确认），未读取内容，不计算 sha256」，
`sha256_state=no_scope`。later 用户把 scope 补上了，但**这些行没人回头改** ——
于是台账至今宣称"读不到"，而实际上现在读得到。2026-09-30 实测剩 4 条：
1 个电子表格（sheets:spreadsheet:read）+ 3 个 slides（slides:presentation:read）。

覆盖矩阵把这两类都列为**硬性必核**（⑥ slides 取 XML 全文当正文、⑦ sheets 逐工作表取值），
且明说「不许因'CLI 没命令'判不可核」。所以这不是可选动作。

## 口径（照既有行）

指纹一律 `sha256_input=doc_text`、`sha256_state=full`，值 = 按 registry 的 normalization
规范化后的正文（newline=\n、去行尾空白、合并空行）。正文取处写进 status_reason：
    · slides → `slides +xml-get` 的 `xml_presentation.content`（XML 全文，矩阵⑥口径）
    · sheets → 既有抽取快照 kb/l1/sources/*__sheets-<token>.md（由 sheets +workbook-info/+cells-get 取得）
不为"补登记"而重新抓一遍正文：能用既有快照就用，并把快照路径写进原因。

旧的 no_scope 行**保留不动**（append-only，历史就是历史），只追加新行。

用法：
    python3 kb/l8/close_stale_scope_gaps.py <RUN>            # 干跑
    python3 kb/l8/close_stale_scope_gaps.py <RUN> --apply
"""
# ── 解释器守卫（与 l8 其它脚本同源）──
import os as _os, sys as _sys
if not _os.environ.get("KB_INTERP_OK"):
    _d = _os.path.dirname(_os.path.abspath(__file__)); _cfg = None
    while True:
        _p = _os.path.join(_d, ".kb-python")
        if _os.path.isfile(_p):
            _cfg = _p; break
        _q = _os.path.dirname(_d)
        if _q == _d: break
        _d = _q
    if _cfg:
        _want = next((l.split("#", 1)[0].strip() for l in open(_cfg, encoding="utf-8")
                      if l.split("#", 1)[0].strip()), "")
        _want = _os.path.expanduser(_want)
        if (_want and _os.access(_want, _os.X_OK)
                and _os.path.realpath(_want) != _os.path.realpath(_sys.executable)):
            _os.environ["KB_INTERP_OK"] = "1"
            _os.execve(_want, [_want, _os.path.abspath(__file__)] + _sys.argv[1:], dict(_os.environ))
# ──────────────────────────────────────

import glob
import hashlib
import json
import os
import subprocess
import sys
import time

APPLY = "--apply" in sys.argv
RUN = next((a for a in sys.argv[1:] if not a.startswith("--")), time.strftime("%Y%m%d-%H%M"))
L0 = "kb/l0"
LARK = os.path.expanduser("~/.dsh/bin/lark-cli")
AS_ID = os.environ.get("L8_AS", "user")
PROFILE = os.environ.get("L8_PROFILE", "dsh-kb")
REG = json.load(open(f"{L0}/registry/kb.json", encoding="utf-8"))
NORM = (REG.get("fingerprint_policy") or {}).get("normalization") or {}


def norm_text(s):
    """按 L0 registry 的 normalization 规范化正文（与既有 doc_text 指纹同口径）。"""
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    lines = [(l.rstrip() if NORM.get("strip_trailing_space", True) else l) for l in s.split("\n")]
    if NORM.get("collapse_blank_lines", True):
        out = []
        for l in lines:
            if l == "" and out and out[-1] == "":
                continue
            out.append(l)
        lines = out
    return "\n".join(lines)


def sha(t):
    return hashlib.sha256(t.encode("utf-8")).hexdigest()


rows = [json.loads(l) for l in open(f"{L0}/manifest.jsonl", encoding="utf-8") if l.strip()]
MAN_KEYS = set()
for r in rows:
    MAN_KEYS |= set(r)
lat = {}
for r in rows:
    lat[r["resource_key"]] = r
stale = [(k, v) for k, v in lat.items()
         if v.get("sha256_state") == "no_scope" and "缺少" in str(v.get("status_reason") or "")]
print(f"[{RUN}] 待关的缺 scope 缺口: {len(stale)}｜{'落盘' if APPLY else '干跑'}")

out_rows, report = [], []
for key, old in sorted(stale):
    kind, tok = key.split(":", 1)
    text = rev = None
    src = None
    if kind == "slides":
        p = subprocess.run([LARK, "slides", "+xml-get", "--presentation", tok, "--as", AS_ID,
                            "--profile", PROFILE, "--json"], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=300)
        d = json.loads(p.stdout[p.stdout.find("{"):])
        if d.get("ok") is False:
            report.append({"key": key, "status": "still_unreachable",
                           "why": json.dumps(d.get("error"), ensure_ascii=False)[:200]})
            print(f"  ✗ {key} 仍读不到")
            continue
        xp = d["data"]["xml_presentation"]
        text = xp.get("content") or ""
        rev = d["data"].get("revision_id")
        src = f"slides +xml-get --presentation {tok}（XML 全文，矩阵⑥口径）"
    elif kind == "sheets":
        cands = sorted(glob.glob(f"kb/l1/sources/*__sheets-{tok}.md"))
        if not cands:
            report.append({"key": key, "status": "no_local_snapshot",
                           "why": "没有既有抽取快照；本脚本不为补登记而重抓正文"})
            print(f"  ✗ {key} 无既有快照，跳过（不重抓）")
            continue
        src = cands[-1]
        text = open(src, encoding="utf-8").read()
    else:
        report.append({"key": key, "status": "unsupported_kind", "why": kind})
        continue
    nt = norm_text(text)
    h = sha(nt)
    row = {k: old.get(k) for k in ("depth", "entry_url", "field_id", "field_name", "kb_type",
                                   "matched_rule", "path", "record_id", "rule_eligible",
                                   "rule_eligible_source", "scanner_version", "dup_of",
                                   "downstream_invalidated")}
    row.update({"change": "l0_stale_scope_gap_closed", "resource_key": key,
                "source_kind": old.get("source_kind"), "observed_at": RUN, "revision": rev,
                "sha256": h, "sha256_input": "doc_text", "sha256_state": "full",
                "status": "registered",
                "status_reason": ("scope 补齐后补登记：原行写「" + str(old.get("status_reason"))[:40]
                                  + "」，现按 " + str(src) + f" 取全文（{len(nt)} 字）计 sha256(doc_text)；"
                                  + "旧行保留不改")})
    missing = set(row) - MAN_KEYS
    if missing:
        raise SystemExit(f"[拒写] {key} 台账行出现既有权之外的新键 {sorted(missing)}")
    out_rows.append(row)
    report.append({"key": key, "status": "closed", "chars": len(nt), "sha256": h,
                   "revision": rev, "text_source": src})
    print(f"  ✓ {key}｜{len(nt)} 字｜rev={rev}｜sha {h[:12]}…｜来源 {str(src)[:60]}")

if APPLY and out_rows:
    with open(f"{L0}/manifest.jsonl", "a", encoding="utf-8") as fh:
        for r in out_rows:
            fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
    print(f"\n[写入] kb/l0/manifest.jsonl +{len(out_rows)} 行")
elif not APPLY:
    print("\n[干跑] 未落盘（加 --apply）")
json.dump({"run_id": RUN, "kind": "close_stale_scope_gaps", "found": len(stale),
           "closed": len(out_rows), "rows": out_rows, "report": report},
          open(f"kb/l8/runs/{RUN}-close-scope-gaps.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print(f"[报告] kb/l8/runs/{RUN}-close-scope-gaps.json")
