#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""**PRD §5.3.3 输出字数与格式硬约束** —— 知识库侧的同一把尺。

真源：`kb/l7/registry/prd533-constraints.yaml`（取自飞书 PRD **正文** §5.3.3，rev 248，2026-10-19）。
守衡侧读同一个文件（`tools/agent/prd533.mjs`）—— **两仓共用一张表**。

四条（PRD 逐字）
  ① 单条问题：描述 ≤50 字、原因 ≤50 字、修改建议 ≤60 字（Owner 2026-10-21 实施覆盖）
  ② 位置：必须精确到「图 N 第 X 处」「视频 00:12」「正文第 X 段」
  ③ 依据：必须写「《文档名》第 X 条」或「规则 ID」，禁止写「相关法规」
  ④ 语言：客观、指令式；禁止「可能」「建议可以考虑」等废话（REVIEW 边界说明除外）

用法
    kb/kbpy l8/prd533_check.py --selftest
    kb/kbpy l8/prd533_check.py --json '{"description":"…","reason":"…","advice":"…","location":"正文第 1 段","basis":"《措辞表达库 v0》第 W-1.18 条"}'

★ 只读数、不阻断：三处与 Owner 既有裁定直接冲突（见 registry `conflicts` X1/X2/X3），等 Owner 裁。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REGISTRY = Path(__file__).resolve().parent.parent / "l7" / "registry" / "prd533-constraints.yaml"


def _raw() -> str:
    if not REGISTRY.is_file():
        raise SystemExit(f"[prd533] 找不到真源：{REGISTRY}")
    return REGISTRY.read_text(encoding="utf-8")


def _inline_maps(raw: str) -> list[dict]:
    out = []
    for line in raw.splitlines():
        m = re.match(r"^\s*-\s*\{(.+)\}\s*$", line)
        if not m:
            continue
        obj = {}
        for part in re.split(r",\s*(?=[A-Za-z_][\w-]*:)", m.group(1)):
            kv = re.match(r"^\s*([A-Za-z_][\w-]*):\s*(.*)$", part)
            if not kv:
                continue
            v = kv.group(2).strip().strip("'\"")
            obj[kv.group(1)] = int(v) if v.isdigit() else v
        out.append(obj)
    return out


def constraints() -> dict:
    raw = _raw()
    maps = _inline_maps(raw)
    fields = [m for m in maps if m.get("key") and m.get("limit") is not None]
    locs = [m for m in maps if m.get("id") and str(m.get("regex", "")).startswith("^")]
    basis_pats = [m for m in maps if m.get("id") and not str(m.get("regex", "")).startswith("^")]
    m = re.search(r"^\s*forbidden:\s*\[(.*?)\]\s*$", raw, re.M)
    basis_forbidden = ([x.strip().strip("'\"") for x in m.group(1).split(",")] if m else [])
    words = [x.strip().strip("'\"") for x in re.findall(r"word:\s*([^,}]+)", raw)]
    rev = re.search(r"^\s*revision:\s*(\d+)", raw, re.M)
    if not fields:
        raise SystemExit(f"[prd533] {REGISTRY} 里没解析出字段上限")
    return {"fields": fields, "location": locs, "basis_patterns": basis_pats,
            "basis_forbidden": [w for w in basis_forbidden if w],
            "language_forbidden": [w.strip() for w in words if w.strip()],
            "revision": int(rev.group(1)) if rev else None, "path": str(REGISTRY)}


def count_chars(text: str) -> int:
    t = str(text or "")
    t = re.sub(r"\[([^\]\n]*)\]\((?:https?:)?[^)\s]*\)", r"\1", t)
    t = re.sub(r"https?://[^\s)）]+", "", t)
    t = re.sub(r"[*`>|【】→#]", "", t)
    return len(re.sub(r"\s+", "", t))




#: **修改建议**的「字」怎么数：**标点不计**（Owner 2026-10-19：「修改建议是可以 30 字的，
#: **不带标点这些**，可以多写一些」）⇒ 量的是**实词字数**。
#:
#: 唯一真源在守衡侧 `tools/agent/prd533.mjs::countAdviceChars`（同一套字符集）；
#: 两条路必须逐项相等，否则「报告说合格、库里说超了」这种分歧会天天出现。
#: ⚠️ 只对 `advice` 这一格生效：描述 / 原因仍按 `count_chars`（Owner 说的是「修改建议」）。
#: ⚠️ 只去**标点**，`-` / `/` / `_` 不算标点（`best-selling` 里的连字符是词的一部分）。
ADVICE_PUNCT_RE = re.compile(r"[，。、；：！？…—～·「」『』（）【】《》〈〉“”‘’,.!?;:'\"()\[\]{}<>]")


def count_advice_chars(text: str) -> int:
    """修改建议的字数：勾掉标点后再数（与守衡侧同一口径）。"""
    t = re.sub(r"\[([^\]\n]*)\]\((?:https?:)?[^)\s]*\)", r"\1", str(text or ""))
    t = re.sub(r"https?://[^\s)）]+", "", t)
    t = re.sub(r"[*`>|【】→#]", "", t)
    t = re.sub(r"\s+", "", t)
    return len(ADVICE_PUNCT_RE.sub("", t))


def check_fields(item: dict) -> dict:
    rows = []
    for f in constraints()["fields"]:
        chars = (count_advice_chars(item.get(f["key"], ""))
                 if f["key"] == "advice" else count_chars(item.get(f["key"], "")))
        lim = int(f["limit"])
        rows.append({"key": f["key"], "label": f.get("label", f["key"]), "limit": lim,
                     "chars": chars, "over": max(0, chars - lim), "ok": chars <= lim})
    return {"rows": rows, "ok": all(r["ok"] for r in rows),
            "over_count": sum(1 for r in rows if not r["ok"])}


def check_location(location: str) -> dict:
    s = str(location or "").strip()
    for p in constraints()["location"]:
        try:
            if re.match(str(p["regex"]), s):
                return {"ok": True, "pattern": p["id"], "value": s}
        except re.error:
            continue
    return {"ok": False, "pattern": None, "value": s,
            "want": " / ".join(str(p.get("sample", "")) for p in constraints()["location"])}


def check_basis(basis: str) -> dict:
    C = constraints()
    s = str(basis or "")
    hit = None
    for p in C["basis_patterns"]:
        try:
            if re.search(str(p["regex"]), s):
                hit = p["id"]
                break
        except re.error:
            continue
    banned = [w for w in C["basis_forbidden"] if w and w in s]
    return {"ok": bool(hit) and not banned, "pattern": hit, "banned": banned}


def check_language(text: str) -> dict:
    s = str(text or "")
    hits = [w for w in constraints()["language_forbidden"] if w and w in s]
    return {"ok": not hits, "hits": hits}


def check_item(item: dict) -> dict:
    f = check_fields(item)
    loc = check_location(item.get("location", ""))
    bas = check_basis(item.get("basis", ""))
    lang = check_language("\n".join(str(item.get(k, "")) for k in ("description", "reason", "advice", "basis")))
    return {"fields": f, "location": loc, "basis": bas, "language": lang,
            "ok": f["ok"] and loc["ok"] and bas["ok"] and lang["ok"],
            "revision": constraints()["revision"]}


def selftest() -> int:
    bad: list[str] = []

    def eq(name, got, want):
        if got != want:
            bad.append(f"{name} —— 期望 {want!r}，实得 {got!r}")
            print(f"  ❌ {name}")
        else:
            print(f"  ✅ {name}")

    print("=== PRD §5.3.3 输出字数与格式硬约束（知识库侧）自证 ===")
    C = constraints()
    eq("① 三个字段上限 = 50/50/60（实施覆盖）", [(f["key"], f["limit"]) for f in C["fields"]],
       [("description", 50), ("reason", 50), ("advice", 60)])
    eq("①b 真源带 PRD 版本", isinstance(C["revision"], int), True)
    eq("② 描述恰好 50 字 ⇒ 合规", check_fields({"description": "字" * 50})["rows"][0]["ok"], True)
    eq("②b 描述 51 字 ⇒ 超 1", check_fields({"description": "字" * 51})["rows"][0]["over"], 1)
    eq("②c 建议 61 字 ⇒ 超 1", check_fields({"advice": "字" * 61})["rows"][2]["over"], 1)
    eq("②d 反向对照：同 31 字放进原因 ⇒ 合规", check_fields({"reason": "字" * 31})["rows"][1]["ok"], True)
    eq("③ 三个样张都合规", [check_location(s)["ok"] for s in ("图 1 第 2 处", "视频 00:12", "正文第 3 段")],
       [True, True, True])
    eq("③b 反向对照：四种不合格形状全红",
       [check_location(s)["ok"] for s in ("全文", "正文第 4 段（DoubleFit Flange, Ultimate Comfort）末句", "图 1", "正文第三段")],
       [False, False, False, False])
    eq("④ 《文档名》第 X 条 ⇒ 合规", check_basis("《措辞表达库 v0》第 W-1.18 条 ← 命中「x」")["ok"], True)
    eq("④b 纯规则 ID（H02）⇒ 合规", check_basis("H02")["ok"], True)
    eq("④c 「相关法规」⇒ 红", check_basis("依据：相关法规")["ok"], False)
    eq("④d 反向对照：「相关法律法规」也要红", len(check_basis("建议参考相关法律法规")["banned"]) > 0, True)
    eq("⑤ 「可能」命中", check_language("可能会被平台判为站外引流")["ok"], False)
    eq("⑤b 「建议可以考虑」命中", check_language("建议可以考虑改一下")["ok"], False)
    eq("⑤c 干净文本不误报", check_language("删去「100%」，改为具体表述。")["ok"], True)
    good = check_item({"description": "逐字命中「boosts milk」", "reason": "绝对化用语",
                       "advice": "删去「100%」。", "location": "正文第 1 段",
                       "basis": "《措辞表达库 v0》第 W-1.18 条"})
    eq("⑥ 四条全过 ⇒ ok", good["ok"], True)
    badloc = check_item({"description": "逐字命中「boosts milk」", "reason": "绝对化用语",
                         "advice": "删去「100%」。", "location": "全文",
                         "basis": "《措辞表达库 v0》第 W-1.18 条"})
    eq("⑥b 反向对照：只换位置 ⇒ 红", [badloc["ok"], badloc["fields"]["ok"]], [False, True])
    print(f"\n自证：通过 {len(bad) == 0 and 'all' or '—'} / 失败 {len(bad)}")
    for b in bad:
        print(f"   ❌ {b}")
    return 1 if bad else 0


def main() -> int:
    ap = argparse.ArgumentParser(description="PRD §5.3.3 硬约束（知识库侧）")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--json", help="一条问题内容的 JSON（description/reason/advice/location/basis）")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    if not a.json:
        ap.error("给 --json 或 --selftest")
    r = check_item(json.loads(a.json))
    print(json.dumps(r, ensure_ascii=False, indent=2))
    return 0 if r["ok"] else 3


if __name__ == "__main__":
    sys.exit(main())
