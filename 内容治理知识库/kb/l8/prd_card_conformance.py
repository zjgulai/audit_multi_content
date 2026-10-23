#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""prd_card_conformance.py —— 用 PRD §17 / §5.3.3 的尺子量**真实卡面**（读数档 · 非阻断）

## 它解决什么（2026-10-19）

`prd17_check.py`（§17 结论模板字数）与 `prd533_check.py`（§5.3.3 字数/位置/依据/语言）
两把尺建好当天，**没有任何东西在跑它们**：

  · `ci/run_gates.py` 的 **20 道**闸门里 PRD 相关 **0 道**；
  · `watch_review_readiness.py` 对 `prd17|prd533|prd532` **0 命中**。

本库口径是「**判据不接线 = 注释**」（AGENTS.md）。本件就是那根线：
把「拿**真卡面**量两把尺」做成一道可被 CI / 定时任务调用的闸门（id `prd_card_conformance`）。

## 为什么量「真卡面」而不是手搓样张

手搓样张只能证明「尺子会算」；证明不了「**我们出的卡对不对**」。
⇒ 夹具走**真产者** `kb/l5/p0_fastpath.py`（P0 快路），拿 stdout 的第一段当卡面。
这是**同一条**产者给守衡卡片供字的那条路（`_prd_block`），不是另写一份渲染。

## 判据口径：存量登记、只对**变差**响

登记件 `kb/l7/registry/prd-card-known-drift.yaml`（与 `l4-known-duplicates` / `perf-known-drift` 同款）：

  · 读数 > 登记值 ⇒ **WARN**（退出码 3；非阻断，**不改 runner 退出码**）
  · 读数 < 登记值 ⇒ 通过，但**提示下调登记**（不许静默变绿）
  · 未登记的超限   ⇒ WARN
  · 逐条四格缺一（位置/原因/依据/建议）、或结论行不合 §5.3.4 措辞 ⇒ WARN

★ 为什么不是「超限即红」：§17 的 **C1**（≥3 档 ≤100 字）今天实测就超（108/100）。
  按「超限即红」接线，CI 第一天就必红 ⇒ 红灯变噪音 ⇒ 又回到「没人看」。
  这是本库已经栽过的坑（`perf-known-drift.yaml` 头部写着同一句话）。

## 退出码（照 `view_foreign` 的惯例，**只退 0 或 3**）

  0  全部读数 ≤ 登记值，且无缺格/措辞问题（或 `--selftest` 全过）
  3  有读数变差 / 未登记超限 / 缺格 / 判据自证失败 / 真源读不到  ⇒ 非阻断闸门记 **WARN**
  **永不 1/2**：非阻断闸门退 1/2 会被 runner 记成 ERROR 并把 CI 打红（`run_gates.py` 注释实测），
  而本件的本意是「读数」，不是「红灯」。

## 口径里两处**解释**（PRD 没写死，必须摆明）

1. **§5.3.3 的「描述」** = 逐条首行**去掉 `【类别-子类】` 标签**之后的部分（位置 + 引文）。
   PRD §5.3.4 样张 `1.【合规-绝对化】图 2 文字"最安全"。` 里，`【…】` 是维度标签，
   不是描述正文；把它算进 50 字里等于让「维度名长一点」就超限。
2. **字数口径** = `visible_no_url`（去链接、去 markdown 标记、去空白），与 `prd17_check` 同一口径。

用法
    sh kb/kbpy l8/prd_card_conformance.py             # 人看读数
    sh kb/kbpy l8/prd_card_conformance.py --json      # 机读（CI 用）
    sh kb/kbpy l8/prd_card_conformance.py --selftest  # 反向对照：证明它不是恒绿
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent          # kb/l8
KB = HERE.parent                                # kb/
REGISTRY = KB / "l7" / "registry" / "prd-card-known-drift.yaml"
KBPY = KB / "kbpy"
CARD_PRODUCER = "l5/p0_fastpath.py"             # 相对 kb/（kbpy 内部会 cd 到 kb/）
TIMEOUT_S = 120

# ── 正则（卡面版式，全部来自 PRD §5.3.4 样张 + P0 快路实际输出）───────────────────
STATE_RE = re.compile(r"^【审查结论：(PASS|SUGGEST|REVIEW|BLOCK)】(.+)$")
ISSUE_RE = re.compile(r"共发现\s*(\d+)\s*处")
ITEM_HEAD_RE = re.compile(r"^(\d+)\.【([^】]+)】(.+)$")
FIELD_RE = re.compile(r"^\s*\*\*(原因|依据|建议)\*\*[：:](.+)$")
LOCATION_PATTERNS = (
    re.compile(r"图\s*\d+\s*第\s*\d+\s*处"),
    re.compile(r"视频\s*\d{1,2}:\d{2}"),
    re.compile(r"正文第\s*\d+\s*段"),
)


# ── 真源与尺子（惰性 import，避免把两把尺的顶层副作用带进来）────────────────────
def _load_module(name: str):
    import importlib.util  # noqa: PLC0415

    if str(HERE) not in sys.path:
        sys.path.insert(0, str(HERE))
    path = HERE / f"{name}.py"
    if not path.is_file():
        raise SystemExit(f"[prd_card] 找不到 {path}")
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_registry() -> dict:
    """读登记件。**读不到就抛** —— 兜底会把「没读进来」伪装成「都合规」。"""
    if not REGISTRY.is_file():
        raise SystemExit(f"[prd_card] 找不到登记件：{REGISTRY}")
    import yaml  # noqa: PLC0415

    return yaml.safe_load(REGISTRY.read_text(encoding="utf-8")) or {}


# ── 跑真产者，取卡面 ───────────────────────────────────────────────────────────
def render_card(text: str, ref: str) -> tuple[str, str]:
    """跑 P0 快路，返回 `(卡面, 原始 stdout)`。卡面 = 首个 `---` 分隔线之前的部分。"""
    if not KBPY.is_file():
        raise SystemExit(f"[prd_card] 找不到 kbpy：{KBPY}")
    p = subprocess.run(
        [str(KBPY), CARD_PRODUCER, "--text", text, "--report-ref", ref],
        cwd=str(KB.parent), capture_output=True, text=True, timeout=TIMEOUT_S,
    )
    out = p.stdout or ""
    if p.returncode != 0 or not out.strip():
        raise SystemExit(
            f"[prd_card] 产者跑失败（rc={p.returncode}）：{(p.stderr or '')[-400:]}")
    card = out.split("\n---\n")[0].rstrip()
    return card, out


# ── 解析卡面 ───────────────────────────────────────────────────────────────────
def parse_card(card: str) -> dict:
    lines = card.splitlines()
    state = None
    conclusion_line = ""
    for ln in lines:
        m = STATE_RE.match(ln.strip())
        if m:
            state = m.group(1)
            conclusion_line = ln.strip()
            break
    m = ISSUE_RE.search(card)
    issues = int(m.group(1)) if m else None
    items = []
    cur = None
    for ln in lines:
        head = ITEM_HEAD_RE.match(ln.strip())
        if head:
            if cur:
                items.append(cur)
            cur = {
                "index": int(head.group(1)),
                "category": head.group(2),
                "desc": head.group(3).strip(),
                "reason": None, "basis": None, "advice": None,
            }
            continue
        if cur is None:
            continue
        f = FIELD_RE.match(ln)
        if f:
            key = {"原因": "reason", "依据": "basis", "建议": "advice"}[f.group(1)]
            cur[key] = f.group(2).strip()
    if cur:
        items.append(cur)
    for it in items:
        it["location"] = None
        for pat in LOCATION_PATTERNS:
            mm = pat.search(it["desc"])
            if mm:
                it["location"] = mm.group(0)
                break
    return {"state": state, "issues": issues, "conclusion_line": conclusion_line,
            "items": items}


# ── 量一条夹具 ─────────────────────────────────────────────────────────────────
def measure(card: str, parsed: dict) -> dict:
    """返回逐项读数 + **结构问题**（缺格 / 措辞），结构问题与「超限」分开报。"""
    p17 = _load_module("prd17_check")
    p533 = _load_module("prd533_check")
    problems: list[str] = []

    if not parsed["state"]:
        problems.append("卡面没有 `【审查结论：<态>】` 结论行")
    if parsed["issues"] is None:
        problems.append("卡面结论行没有 `共发现 N 处`")

    r17 = None
    if parsed["state"] and parsed["issues"] is not None:
        r17 = p17.check(parsed["state"], parsed["issues"], card)

    fields = []
    for it in parsed["items"]:
        missing = [k for k in ("reason", "basis", "advice") if not it.get(k)]
        if missing:
            problems.append(
                f"第 {it['index']} 条缺字段：{'/'.join(missing)}（PRD §5.3.4 四格缺一即不合规）")
        if it["location"] is None:
            problems.append(
                f"第 {it['index']} 条位置不在 §5.3.3 的三种模式内：{it['desc'][:40]!r}")
        c = p533.check_item({
            "description": it["desc"],
            "reason": it.get("reason") or "",
            "advice": it.get("advice") or "",
            "location": it["location"] or "",
            "basis": it.get("basis") or "",
        })
        fields.append({
            "index": it["index"],
            "chars": {row["key"]: row["chars"] for row in c["fields"]["rows"]},
            "limits": {row["key"]: row["limit"] for row in c["fields"]["rows"]},
            "ok": c["ok"],
            "why": [row for row in c["fields"]["rows"] if not row["ok"]]
                   + ([] if c["location"]["ok"] else [{"location": c["location"]}])
                   + ([] if c["basis"]["ok"] else [{"basis": c["basis"]}]),
        })

    return {
        "state": parsed["state"],
        "issues": parsed["issues"],
        "chars": (r17 or {}).get("chars"),
        "limit": (r17 or {}).get("limit"),
        # ★ `check()` 不返回 scope，档位（逐条/整卡）由 `scope_of()` 单独给 —— 别猜。
        "scope": (p17.scope_of(parsed["state"], parsed["issues"])
                  if parsed["state"] and parsed["issues"] is not None else None),
        "over": (r17 or {}).get("over"),
        "ok17": (r17 or {}).get("ok"),
        # ★ 口径读数（2026-10-19「链接那行不计入」）：排除了几行、少了几个字、有没有 hazard
        "link_lines_excluded": (r17 or {}).get("link_lines_excluded"),
        "link_chars_excluded": (r17 or {}).get("link_chars_excluded"),
        "link_line_hazards": (r17 or {}).get("link_line_hazards") or [],
        "fields": fields,
        "problems": problems,
    }


# ── 与登记值比对 ───────────────────────────────────────────────────────────────
def compare(fx: dict, reading: dict) -> tuple[list[str], list[str]]:
    """返回 `(warnings, notes)`。warnings ⇒ 退 3；notes 只提示。"""
    reg = fx.get("registered") or {}
    warnings: list[str] = []
    notes: list[str] = []

    for p in reading["problems"]:
        warnings.append(f"{fx['id']}：{p}")

    if reading["chars"] is not None and reg.get("chars") is not None:
        delta = reading["chars"] - reg["chars"]
        if delta > 0:
            warnings.append(
                f"{fx['id']}：卡面字数**变差** {reg['chars']} → {reading['chars']}"
                f"（上限 {reading['limit']}，超 {reading['over']}）")
        elif delta < 0:
            notes.append(
                f"{fx['id']}：卡面字数好转 {reg['chars']} → {reading['chars']}"
                f" ⇒ 可下调 `prd-card-known-drift.yaml` 的登记值")
        if reading["limit"] != reg.get("limit"):
            warnings.append(
                f"{fx['id']}：档位上移 {reg.get('limit')} → {reading['limit']}"
                f"（PRD §17 真源可能被改过，去核 `prd17-limits.yaml`）")

    for fld in reading["fields"]:
        regf = (reg.get("fields") or {})
        for row in fld["why"]:
            if isinstance(row.get("key"), str):
                warnings.append(
                    f"{fx['id']}：第 {fld['index']} 条 {row.get('label')} "
                    f"{row.get('chars')} 字 > 上限 {row.get('limit')}（PRD §5.3.3）")
            else:
                warnings.append(f"{fx['id']}：第 {fld['index']} 条 {row}")
        for k, v in (fld["chars"] or {}).items():
            if k in regf and v > regf[k]:
                warnings.append(
                    f"{fx['id']}：第 {fld['index']} 条 `{k}` 字数变差 {regf[k]} → {v}")
    return warnings, notes


# ── 自证（反向对照：证明它不是恒绿）────────────────────────────────────────────
def selftest() -> int:
    bad: list[str] = []

    def ck(name: str, ok: bool, extra: str = "") -> None:
        if ok:
            print(f"  ✅ {name}")
        else:
            bad.append(f"{name} {extra}")
            print(f"  ❌ {name} {extra}")

    print("=== prd_card_conformance 自证 ===")

    # ① 两把尺自己的自证必须先过（尺坏 ⇒ 读数无意义）
    for name in ("prd17_check", "prd533_check"):
        mod = _load_module(name)
        rc = mod.selftest()
        ck(f"① {name} 自证通过", rc == 0, f"rc={rc}")

    reg = load_registry()
    fixtures = reg.get("fixtures") or []
    ck("② 登记件可读且有夹具", len(fixtures) >= 2, f"n={len(fixtures)}")
    ref = (reg.get("meta") or {}).get("fixture_ref") or "https://x.y/z"

    # ③ 正常路径：真跑每个夹具，结构上不许有缺格/措辞问题
    readings = {}
    for fx in fixtures:
        card, _ = render_card(fx["text"], ref)
        parsed = parse_card(card)
        r = measure(card, parsed)
        readings[fx["id"]] = (card, parsed, r, fx)
        ck(f"③ {fx['id']} 卡面结构齐全（无缺格/无措辞问题）",
           not r["problems"], str(r["problems"]))
        w, _ = compare(fx, r)
        ck(f"③b {fx['id']} 读数未变差", not w, str(w))

    # ④ 反向对照 A：把登记值改小 10 ⇒ **必须**判 WARN（证明「变差会响」）
    fx0 = fixtures[0]
    card0, parsed0, _r0, _ = readings[fx0["id"]]
    fake = json.loads(json.dumps(fx0))
    fake["registered"]["chars"] = max(0, (fx0["registered"]["chars"] or 10) - 10)
    w, _ = compare(fake, measure(card0, parsed0))
    ck("④ 反向对照：登记值调小 10 ⇒ 必须报变差", any("变差" in x for x in w), str(w))

    # ⑤ 反向对照 B：把登记值改大 10 ⇒ **不许**报变差（只会提示下调）
    fake2 = json.loads(json.dumps(fx0))
    fake2["registered"]["chars"] = (fx0["registered"]["chars"] or 0) + 10
    w2, n2 = compare(fake2, measure(card0, parsed0))
    ck("⑤ 反向对照：登记值调大 10 ⇒ 不许报变差（只提示）",
       (not any("变差" in x for x in w2)) and bool(n2), f"w={w2} n={n2}")

    # ⑥ 反向对照 C：**删掉建议行**（卡面变短了）⇒ 必须仍判 WARN
    #    这一条是防「指标变好其实是因为少了内容」—— 只量字数会放过它。
    if parsed0["items"]:
        mut = card0.replace("**建议**：", "**备注**：")
        r6 = measure(mut, parse_card(mut))
        ck("⑥ 反向对照：把「建议」行改名 ⇒ 必须判缺格", bool(r6["problems"]), str(r6["problems"]))

    # ⑦ 反向对照 D：结论行措辞被改写 ⇒ 必须判问题
    mut7 = card0.replace("【审查结论：BLOCK】", "【证据】BLOCK：")
    r7 = measure(mut7, parse_card(mut7))
    ck("⑦ 反向对照：抹掉 `【审查结论：…】` ⇒ 必须判问题", bool(r7["problems"]), str(r7["problems"]))

    print(f"\n自证：{'全过' if not bad else '失败 ' + str(len(bad))}")
    for b in bad:
        print(f"   ❌ {b}")
    return 0 if not bad else 3


# ── 主流程 ─────────────────────────────────────────────────────────────────────
def run(as_json: bool) -> int:
    reg = load_registry()
    fixtures = reg.get("fixtures") or []
    ref = (reg.get("meta") or {}).get("fixture_ref") or "https://x.y/z"
    if not fixtures:
        print("[prd_card] 登记件里没有夹具 ⇒ 未测（不许报绿）")
        return 3

    readings, warnings, notes = [], [], []
    for fx in fixtures:
        card, _ = render_card(fx["text"], ref)
        r = measure(card, parse_card(card))
        w, n = compare(fx, r)
        warnings += w
        notes += n
        readings.append({
            "id": fx["id"],
            "state": r["state"],
            "issues": r["issues"],
            "chars": r["chars"],
            "limit": r["limit"],
            "scope": r["scope"],
            "over": r["over"],
            "registered_chars": (fx.get("registered") or {}).get("chars"),
            "known_conflict": fx.get("known_conflict"),
            "link_lines_excluded": r.get("link_lines_excluded"),
            "link_chars_excluded": r.get("link_chars_excluded"),
            "link_line_hazards": r.get("link_line_hazards"),
            "fields": [{"index": f["index"], "chars": f["chars"], "ok": f["ok"]}
                       for f in r["fields"]],
            "problems": r["problems"],
        })
        # ★ hazard：链接与结论/正文挤在同一行 ⇒ 口径**不会**排除它（fail-closed），
        #   但必须让人看见「这一行差点被当成链接行」。非阻断、只 WARN（同存量登记那条纪律）。
        for h in r.get("link_line_hazards") or []:
            warnings.append(f"{fx['id']}：链接与结论/正文同行 ⇒ 未排除（需把链接单独成行）：{h[:60]!r}")

    ok = not warnings
    payload = {
        "ok": ok,
        "gate": "prd_card_conformance",
        "registry": str(REGISTRY.relative_to(KB.parent)),
        "readings": readings,
        "warnings": warnings,
        "notes": notes,
        "known_conflicts": [c.get("id") for c in (reg.get("known_conflicts") or [])],
    }

    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print("=== PRD 卡面读数（§17 字数 ／ §5.3.3 硬约束）===")
        for r in readings:
            flag = "✅" if (r["over"] or 0) == 0 else f"⚠️ 超 {r['over']}"
            print(f"  {r['id']:<14} {r['state']} {r['issues']} 条 ⇒ "
                  f"{r['chars']} 字 / 上限 {r['limit']}（{r['scope']}；登记 "
                  f"{r['registered_chars']}） {flag}"
                  + (f" ［已知冲突 {r['known_conflict']}］" if r["known_conflict"] else "")
                  + (f"｜已排除链接行 {r['link_lines_excluded']} 行（−{r['link_chars_excluded']} 字）"
                     if r.get("link_lines_excluded") else ""))
            for f in r["fields"]:
                print(f"      · 第 {f['index']} 条字段字数 {f['chars']} ⇒ "
                      f"{'合规' if f['ok'] else '❌ 不合规'}")
            for p in r["problems"]:
                print(f"      ✗ {p}")
        for n in notes:
            print(f"  ℹ️  {n}")
        for w in warnings:
            print(f"  ⚠️  {w}")
        print(f"\n结论：{'PASS（读数未变差）' if ok else 'WARN（读数变差/结构缺格）—— 非阻断'}")
    return 0 if ok else 3


def main() -> int:
    ap = argparse.ArgumentParser(description="PRD §17/§5.3.3 真实卡面读数（非阻断闸门）")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    return run(a.json)


if __name__ == "__main__":
    sys.exit(main())
