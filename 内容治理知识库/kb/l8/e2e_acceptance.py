#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""e2e_acceptance.py —— **端到端跑通记录**（本行交付物 2「10 条真实内容跑通记录」）。

════════════════════════════════════════════════════════════════════════
它答什么
════════════════════════════════════════════════════════════════════════
「一条真实内容送进去，能不能**出结论**、能不能**给依据**」——**逐条**落成可核记录，
而不是一个「累计 N 单」的总数（那个数已被证明会被重跑抬高，见
`kb/l8/review_run_count.py` 与《交付-评审台账观测者污染》）。

每条记七样（缺的**照实写缺**，不代填）：
  ① 送审素材（sha256 前 12）
  ② 三态 ＋ 问题数 ＋ 非权威候选数（`authoritative is False`）
  ③ **逐条四段溯源**：条款号 / 锚点 / source_sha256 / L0 飞书直链 —— 齐 k/n、**缺哪一段**
  ④ 层前置 `mode`（`enforced` 才是走完四层；`waived_by_caller` 要写出来）
  ⑤ 判定主体 `mode` ＋ 本会话**申报加载过**的 skill
  ⑥ 耗时
  ⑦ 发布状态（本工具默认 `--no-publish-to-feishu`：**不写生产表**）

★ 引擎版本指纹：跑之前/之后各取一次关键文件的 sha256。**两次不一致 ⇒ 记录标 INC**，
  因为这时 10 条不是同一个引擎判的（比"看着像成功"更该看见的东西）。

跑法（层前置由链自己的入口做，见 `kb/l8/review_preflight.sh`）：
    bash kb/l8/review_preflight.sh --base <BASE> --session <会话>
    python3 kb/l8/e2e_acceptance.py --base <BASE> --n 10
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

KB = Path(__file__).resolve().parent.parent
ROOT = KB.parent
ENGINE = KB / "l7" / "review-engine" / "core" / "with_kb_evidence.py"
SET = KB / "l7" / "registry" / "regression-set.yaml"
SAFE = KB / ".work" / "_safe_write.py"

#: 引擎版本指纹要覆盖的文件（一改就可能让三态变）
FINGERPRINT_FILES = (
    "kb/l7/review-engine/core/with_kb_evidence.py",
    "kb/l7/review-engine/core/review_engine.py",
    "kb/l7/review-engine/core/tiering.py",
    "kb/l7/skills/kb-content-review/scripts/review.py",
    "kb/l3/candidates/rules.jsonl",
    "kb/l5/p0_patterns.jsonl",
)


def fingerprint() -> dict:
    out = {}
    for rel in FINGERPRINT_FILES:
        p = ROOT / rel
        try:
            out[rel] = hashlib.sha256(p.read_bytes()).hexdigest()[:16]
        except OSError:
            out[rel] = "缺失"
    return out


# ── 判据：逐条四段溯源（**纯函数**，自证靠它喂样本）─────────────────────────
SEGMENTS = ("条款号", "锚点", "source_sha256", "L0直链")


def segments_of(item: dict) -> dict:
    """一条 finding 的**四段**齐不齐。判据只看 `decision.risk_items[].evidence`。

    ★ 为什么逐条而不是报告级：`workflow_smoke` 的 S4 查的是**报告文本里有没有**这三样 ——
      一份报告可以整体有、**某一条没有**。库规逐字是「**拿不出四段的结论，不许出现**」，
      要求是**逐条**的。
    """
    ev = item.get("evidence") if isinstance(item.get("evidence"), dict) else {}
    return {
        "条款号": bool(str(ev.get("article_no") or "").strip()),
        "锚点": bool(str(ev.get("anchor") or "").strip()),
        "source_sha256": bool(str(ev.get("source_sha256") or "").strip()),
        "L0直链": bool(str(ev.get("l0_entry_url") or "").strip()),
    }


def _is_library_basis(item: dict) -> bool:
    """这一条**是不是库内依据**（要不要受四段考核）。

    ★ 两类**不是**：
      · `authoritative is False` —— `rule_engine.scan_text()` 的**非权威候选**（源规则已被取代）；
      · `coverage_gap is True` —— **覆盖缺口哨兵**（`with_kb_evidence.py:1105`）：
        它明写「覆盖缺口说明（**不是内容问题**）」且 `issue_count` 记 0。
    ★ 实测教训（2026-10-12 首次跑批）：不排掉哨兵 ⇒ 那条 REVIEW 报「四段齐 0/1」，
      **是假警报** —— 与我在《交付-非权威候选的声明落地》里批的正是同一类错（把设计行为当缺陷）。
    """
    return item.get("authoritative") is not False and not item.get("coverage_gap")


def summarise_items(items) -> dict:
    """逐条汇总：`four_seg_ok` / `n` / `assessed` / `missing_count` / `missing_detail`。"""
    items = list(items or [])
    detail = {k: 0 for k in SEGMENTS}
    ok = 0
    assessed = 0
    for it in items:
        if not _is_library_basis(it):
            continue
        assessed += 1
        seg = segments_of(it)
        if all(seg.values()):
            ok += 1
        else:
            for k, v in seg.items():
                if not v:
                    detail[k] += 1
    return {"n": len(items), "assessed": assessed, "four_seg_ok": ok,
            "missing_count": sum(detail.values()), "missing_detail": detail}


def pick(n: int, set_path: Path = SET) -> list:
    """从回归集挑 n 条**真实素材**，按历史态分层取（覆盖 BLOCK/REVIEW/PASS/拒答）。"""
    import yaml
    d = yaml.safe_load(Path(set_path).read_text(encoding="utf-8")) or {}
    solid = d.get("solid") or []
    fragile = d.get("fragile") or []
    buckets = {}
    for c in solid:
        buckets.setdefault(str(c.get("expected")), []).append(c)
    order = ["BLOCK", "REVIEW", "PASS"]
    out, i = [], 0
    while len(out) < n - 1 and any(buckets.get(k) for k in order):
        k = order[i % len(order)]
        if buckets.get(k):
            out.append(dict(buckets[k].pop(0), _layer="solid"))
        i += 1
        if i > 200:
            break
    for c in fragile[: max(0, n - len(out))]:
        out.append(dict(c, _layer="fragile"))
    return out[:n]


def run_one(case: dict, base: str, owner: str, loaded: list, publish: bool) -> dict:
    t0 = time.time()
    cmd = [sys.executable, str(ENGINE), "--text", case["text"], "--json",
           "--require-layer-preflight", base,
           "--decision-owner", owner]
    for s in loaded:
        cmd += ["--loaded-skill", s]
    if not publish:
        cmd.append("--no-publish-to-feishu")
    env = dict(os.environ)
    env["KB_RUN_RECORD_SKIP"] = "1"          # 只读验收不进评审台账（口径见 run_record.record）
    rec = {"case_id": case["case_id"], "layer": case.get("_layer"),
           "expected_historical": case.get("expected"),
           "text_sha12": hashlib.sha256(case["text"].encode()).hexdigest()[:12]}
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=300,
                           cwd=str(ROOT), env=env)
        out = _decode(p.stdout or "")
    except Exception as e:                                     # noqa: BLE001
        rec.update({"state": None, "error": "%s: %s" % (type(e).__name__, e),
                    "elapsed_s": round(time.time() - t0, 1)})
        return rec
    dec = (out or {}).get("decision") or {}
    em = (out or {}).get("evidence_meta") or {}
    items = dec.get("risk_items") or []
    rec.update({
        "state": dec.get("decision") or dec.get("state"),
        "issue_count": dec.get("issue_count"),
        "candidate_n": sum(1 for i in items if i.get("authoritative") is False),
        "coverage_gap": any(bool(i.get("coverage_gap")) for i in items),
        "elapsed_s": round(time.time() - t0, 1),
        "layer_preflight_mode": (em.get("layer_preflight") or {}).get("mode")
                                or (dec.get("layer_preflight") or {}).get("mode"),
        "decision_owner_mode": (em.get("decision_owner") or {}).get("mode"),
        "decision_owner_warning": (em.get("decision_owner") or {}).get("warning"),
        "publish": (em.get("publish") or {}),
    })
    rec.update(summarise_items(items))
    return rec


def _decode(raw: str):
    d, dec = None, json.JSONDecoder()
    for cand in (raw,) + tuple(raw[k:] for k in range(len(raw)) if raw[k] == "{"):
        try:
            d, _ = dec.raw_decode(cand.lstrip())
            break
        except Exception:                                      # noqa: BLE001
            continue
    return d


# ── 自证 ────────────────────────────────────────────────────────────────────
def selftest() -> int:
    ok = True

    def chk(name, cond, extra=""):
        nonlocal ok
        print(("  ✅ " if cond else "  ❌ ") + name + (("  " + extra) if extra and not cond else ""))
        ok = ok and bool(cond)

    def mk(**ev):
        base = {"article_no": "W-1.1", "anchor": "#x/rec/字段",
                "source_sha256": "a" * 64, "l0_entry_url": "https://momcozy-in.feishu.cn/x"}
        base.update(ev)
        return {"risk_id": "r-1", "evidence": base}

    print("e2e_acceptance 自证（四段溯源判据的反向对照）")
    s = summarise_items([mk()])
    chk("① 四段齐 ⇒ four_seg_ok=1 且 missing=0",
        s["four_seg_ok"] == 1 and s["missing_count"] == 0)
    for key, label in (("article_no", "条款号"), ("anchor", "锚点"),
                       ("source_sha256", "source_sha256"), ("l0_entry_url", "L0直链")):
        s2 = summarise_items([mk(**{key: ""})])
        chk("② 抽掉【%s】⇒ 精确报缺那一段" % label,
            s2["four_seg_ok"] == 0 and s2["missing_detail"][label] == 1,
            repr(s2["missing_detail"]))
    s3 = summarise_items([mk(), mk(l0_entry_url=""), mk(anchor="")])
    chk("③ 混批 ⇒ 齐 1／缺 2，且缺哪段分得开",
        s3["four_seg_ok"] == 1 and s3["missing_detail"]["L0直链"] == 1
        and s3["missing_detail"]["锚点"] == 1)
    # ★ 关键反向对照：**非权威候选不进四段考核**（它本来就不该有四段）
    s4 = summarise_items([mk(), {"risk_id": "US-X:0", "authoritative": False}])
    chk("④ 非权威候选**不参与**四段考核（assessed 只数库内依据）",
        s4["assessed"] == 1 and s4["four_seg_ok"] == 1 and s4["missing_count"] == 0)
    chk("⑤ 候选数单列（不许混进 n 或 assessed）", s4["n"] == 2 and s4["assessed"] == 1)
    # ★ 2026-10-12 首跑照出来的假警报：**覆盖缺口哨兵**也不是库内依据，不该受四段考核。
    s5 = summarise_items([mk(), {"risk_id": None, "coverage_gap": True, "severity": "REVIEW"}])
    chk("⑤b 覆盖缺口哨兵**不参与**四段考核（首跑时它报了「四段齐 0/1」，是假警报）",
        s5["assessed"] == 1 and s5["four_seg_ok"] == 1 and s5["missing_count"] == 0,
        repr(s5))
    s6 = summarise_items([])
    chk("⑥ 空输入 ⇒ 全 0，不崩", s6["n"] == 0 and s6["four_seg_ok"] == 0)
    _c = pick(10)
    chk("⑦ 选题覆盖四种历史态（BLOCK/REVIEW/PASS/拒答）",
        len(_c) == 10 and len({str(x.get("expected")) for x in _c}) >= 3,
        str(sorted({str(x.get("expected")) for x in _c})))
    print("结论：%s" % ("✅ 判据有反向对照" if ok else "❌ 有反向对照没红"))
    return 0 if ok else 3


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", help="四层前置 BASE（review_preflight.sh 跑出来的）")
    ap.add_argument("--n", type=int, default=10)
    ap.add_argument("--owner", default="文案合规审查", help="判定主体（load 目录名，中文）")
    ap.add_argument("--loaded-skill", action="append", default=["文案合规审查"])
    ap.add_argument("--publish", action="store_true", help="默认**不发布**（不写生产表）")
    ap.add_argument("--out", default=None)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    if not a.base:
        print("缺 --base：先用 bash kb/l8/review_preflight.sh --base <BASE> --session <会话>")
        return 2

    fp0 = fingerprint()
    cases = pick(a.n)
    print("端到端验收：%d 条真实素材 ｜ BASE=%s ｜ 判定主体=%s ｜ 发布=%s"
          % (len(cases), a.base, a.owner, "开" if a.publish else "关（不写生产表）"), flush=True)
    res = []
    for i, c in enumerate(cases, 1):
        r = run_one(c, a.base, a.owner, a.loaded_skill, a.publish)
        res.append(r)
        print("  [%2d/%d] %-16s %-8s → 三态 %-6s ｜ 问题 %-3s ｜ 候选 %-2s ｜ 四段齐 %s/%s"
              % (i, len(cases), r["case_id"], r.get("expected_historical"), r.get("state"),
                 r.get("issue_count"), r.get("candidate_n"),
                 r.get("four_seg_ok"), r.get("assessed")), flush=True)
    fp1 = fingerprint()
    mixed = [k for k in fp0 if fp0[k] != fp1.get(k)]

    out = Path(a.out) if a.out else (KB / "l7" / "reports" / ("e2e-acceptance-%s.jsonl"
                                                             % time.strftime("%Y%m%d-%H%M%S")))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in res),
                   encoding="utf-8")
    ok_n = sum(1 for r in res if r.get("state") in ("PASS", "REVIEW", "BLOCK"))
    full_n = sum(1 for r in res if r.get("assessed") and r.get("four_seg_ok") == r.get("assessed"))
    enf = sum(1 for r in res if str(r.get("layer_preflight_mode")) == "enforced")
    print("\n" + "=" * 74)
    print("出结论 %d/%d ｜ 四段**全齐** %d 条 ｜ 层前置 enforced %d/%d ｜ 引擎指纹变动 %s"
          % (ok_n, len(res), full_n, enf, len(res), mixed or "无"))
    print("逐条记录 → %s" % out)
    if mixed:
        print("⚠️ **INC**：跑批期间引擎文件被改过（%s）⇒ 这 %d 条不是同一个引擎判的" % (mixed, len(res)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
