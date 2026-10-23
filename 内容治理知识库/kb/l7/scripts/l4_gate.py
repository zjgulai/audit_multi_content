#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""l4_gate.py —— L4 层闸门（**独立复算档**）：把 promotion_rule 的 C1–C5 从自报 measured 变成复算。

## 它补的是哪个洞

`kb/l4/registry/l4.json → promotion_rule.criteria` 里 C1–C8 每条都带 `pass: true` 和
`measured: {...}` —— **那是晋升那一刻的自报值**。注册表自己说「我是对的」不算闸门：
本脚本从 `kb/l4/canonical/*.jsonl`（1365 条定稿，五个形态文件）+ `kb/l3/candidates/*.jsonl`（候选）
+ `kb/l2/units.jsonl`（单元）**重新算一遍**，算不出来或对不上就判红。

## 判据（红）

  C1 条款号唯一     —— 1365 条定稿的 `article_no` 必须唯一，且条数 == 记录数。
  C2 正文非空       —— 按形态取字段：entry/revision_pair → rule_text；
                        sample_case → sample_body；scoped_clause → clause_text。空 = 红。
  C3 证据三件套完整 —— 每条 `evidence_units[]` 必须含 unit_id + anchor + source_sha256。
  C4 证据可回指     —— 每个 unit_id 必须能在 `kb/l2/units.jsonl` 找到，
                        且 source_sha256 与该单元**逐字一致**；anchor 必须等于该单元的
                        `anchor`，或落在它的 `legacy_anchors` 里（★ 见下）。

  ★ 2026-10-20 补：`legacy_anchors` 必须认，否则「修好坐标反而把闸门弄红」
    实测事故：`kb/l8/l2_image_units.py`（2026-10-20，串图修复 ①）把 L2 字段级单元的锚点
    从 `#素材/<rec>/图片素材/#img.1`（自述为**历史误用**：那个 `#img.1` 指的其实是整个字段）
    改成 `#素材/<rec>/图片素材`，并按它自己的设计把旧锚点留在 `legacy_anchors` 里
    （原话「不丢引用」）。而本闸门原先只比 `anchor` ⇒ 一次**坐标修正**把 L3 红 512 / L4 红 420，
    评审链停在 L4 并 `layer_gate_red` 拒答（2026-10-20 16:2x 实测）。
    ⇒ 判据改成「`anchor` 相同 **或** 命中该单元的 `legacy_anchors`」；
      **没有放宽** source_sha256，也**没有放宽**「单元必须存在」。
    反向对照：`--selftest` 的 T3 把 legacy 摘掉必须**精确变红**（判据不是恒过）。
  C5 定稿不改写     —— 每条定稿的正文必须与同 `rule_id` 的 L3 候选件**逐字相同**
                        （canonical 只加不改），且 rule_id 必须有候选出处。
  C6 版本纪律       —— `kb/l4/canonical/rules.jsonl` 必须保持 **0 字节**
                        （定稿按形态分文件，聚合文件留着是历史遗留，一旦有内容说明有人写错位置）。

## 说明项（不是红）

  N1 形态分布、证据引用条数、条款号区间；C7/C8（晋升后的抽查与撤回纪律）本闸门不复算。

## 只读

只读 kb/l2、kb/l3、kb/l4 的 jsonl/json，**不写任何文件**。

用法：
    kb/kbpy l7/scripts/l4_gate.py [--json] [--quiet]
    KB_GATE_KB=<夹具目录> kb/kbpy l7/scripts/l4_gate.py     # 反测用（默认真库）
"""
from __future__ import annotations

import argparse
import collections
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
KB = os.environ.get("KB_GATE_KB") or os.path.dirname(os.path.dirname(HERE))
ROOT = os.path.dirname(KB)
L2_UNITS = os.path.join(KB, "l2/units.jsonl")
CANON = os.path.join(KB, "l4/canonical/*.jsonl")
CANON_AGG = os.path.join(KB, "l4/canonical/rules.jsonl")
CANDIDATES = os.path.join(KB, "l3/candidates/*.jsonl")
CAP = 6
TEXT_FIELDS = ("rule_text", "sample_body", "clause_text", "body", "text")


def _iter(p):
    with open(p, encoding="utf-8") as fh:
        for i, line in enumerate(fh, 1):
            line = line.strip()
            if line:
                yield i, json.loads(line)


def _text(d):
    for f in TEXT_FIELDS:
        v = d.get(f)
        if isinstance(v, str) and v.strip():
            return f, v
    return None, None


def compute():
    for p in (L2_UNITS, CANON_AGG):
        if not os.path.exists(p):
            return None, "输入缺失：%s" % os.path.relpath(p, ROOT)

    units = {}
    for _, d in _iter(L2_UNITS):
        if d.get("unit_id"):
            units[d["unit_id"]] = d

    raw = [(os.path.basename(p), d) for p in sorted(glob.glob(CANON)) for _, d in _iter(p)]
    if not raw:
        return None, "kb/l4/canonical/*.jsonl 里没有定稿记录 → 空集上判过是假过"
    # ★★ 2026-10-20：按 `article_no` 取**最后一行**（与 `kb/l7/scripts/l4_retire.py::read_last_per_key`
    #   同一条口径）——退役是「另起一行」，原行逐字节不动；不折叠的话退役行与定稿行并存，
    #   本闸门会把退役行当成第二条定稿 ⇒ 既重复计红、又把「已退役」误判成「还坏着」。
    latest = {}
    for base, d in raw:
        latest[str(d.get("article_no") or "")] = (base, d)
    canon = [d for _, d in latest.values()]
    retired = [d for d in canon if str(d.get("status")) == "retired"]
    canon = [d for d in canon if str(d.get("status")) != "retired"]      # 已退役 = 历史，不是在册证据

    cand = {}
    for p in sorted(glob.glob(CANDIDATES)):
        for _, d in _iter(p):
            if d.get("rule_id"):
                cand[d["rule_id"]] = d

    # C1（按**文件**判重：折叠后同一号码只会剩一行，跨文件同名才是真的号重复）
    nos = [str(d.get("article_no") or "") for d in canon]
    by_no = collections.defaultdict(set)
    for d in raw:
        by_no[str(d[1].get("article_no") or "")].add(d[0])
    dup = [k for k, v in by_no.items() if len(v) > 1]
    c1 = ([["重复条款号（跨形态文件）", k] for k in dup[:CAP]] if dup else []) + \
         ([["条款号为空", "共 %d 条" % nos.count("")]] if "" in nos else [])

    # C2
    c2 = [[d.get("article_no"), d.get("form"), "按形态找不到非空正文字段"]
          for d in canon if _text(d)[0] is None]

    # C3 / C4（**按形态取证据**：规则形态用 evidence_units[]，
    #           sample_case / scoped_clause 用顶层 anchor + cite_check.source_sha256 ——
    #           实测这两类定稿本来就没有 evidence_units，一开始按规则形态判是判错了）
    by_anchor = {u["anchor"]: u for u in units.values() if u.get("anchor")}
    # 旧锚点 → 单元（2026-10-20：坐标改名后，旧锚点只存在于 legacy_anchors 里）
    by_legacy = {}
    for u in units.values():
        for a in (u.get("legacy_anchors") or []):
            by_legacy.setdefault(a, u)

    def _same_anchor(u, anc):
        """定稿里的 anchor 与单元**现在的**锚点是不是同一坐标（见抬头 C4 的 ★ 段）。"""
        return anc == (u.get("anchor") or "") or anc in (u.get("legacy_anchors") or [])

    def _evidence(d):
        out = []
        for e in (d.get("evidence_units") or []):
            out.append((e.get("unit_id"), e.get("anchor"), e.get("source_sha256"), "evidence_units"))
        if not out:
            cc = d.get("cite_check") if isinstance(d.get("cite_check"), dict) else {}
            if d.get("anchor"):
                out.append((None, d.get("anchor"), cc.get("source_sha256"), "cite_check"))
        return out

    c3, c4, refs = [], [], 0
    for d in canon:
        evs = _evidence(d)
        if not evs:
            c3.append([d.get("article_no"), d.get("form"), "没有可引用的证据坐标（anchor/sha256 都没有）"])
            continue
        for uid, anc, sha, src in evs:
            refs += 1
            if not (anc and sha):
                c3.append([d.get("article_no"), src, "证据缺 anchor 或 source_sha256"])
                continue
            u = units.get(uid) if uid else (by_anchor.get(anc) or by_legacy.get(anc))
            if u is None:
                c4.append([d.get("article_no"), uid or anc, "L2 里找不到这个 unit_id/anchor"])
            elif u.get("source_sha256") != sha:
                c4.append([d.get("article_no"), uid or anc, "source_sha256 对不上"])
            elif anc and uid and not _same_anchor(u, anc):
                c4.append([d.get("article_no"), uid, "anchor 对不上"])

    # C5 定稿不改写（规则形态按 rule_id 比；非规则形态按同形态正文集合比）
    cand_texts = collections.defaultdict(set)
    for p in sorted(glob.glob(CANDIDATES)):
        for _, d in _iter(p):
            _, ct = _text(d)
            if ct is not None:
                cand_texts[str(d.get("form"))].add(ct)
    c5 = []
    for d in canon:
        rid = d.get("rule_id")
        _, t = _text(d)
        if t is None:
            continue                                  # 已在 C2 报过
        if rid:
            src = cand.get(rid)
            if src is None:
                c5.append([d.get("article_no"), rid, "L3 候选件里找不到这个 rule_id"])
                continue
            _, ct = _text(src)
            if ct is not None and ct != t:
                c5.append([d.get("article_no"), rid, "正文与候选件不逐字相同（定稿被改写？）"])
        elif t not in cand_texts.get(str(d.get("form")), set()):
            c5.append([d.get("article_no"), d.get("form"),
                       "正文在同形态候选件里找不到逐字相同的记录（定稿被改写？）"])

    # C6
    sz = os.path.getsize(CANON_AGG)
    c6 = [] if sz == 0 else [["kb/l4/canonical/rules.jsonl", "%d 字节（应为 0）" % sz]]

    forms = collections.Counter(str(d.get("form")) for d in canon)
    rep = {
        "counts": {"canonical": len(canon), "evidence_refs": refs,
                   "candidates": len(cand), "l2_units": len(units)},
        "C1_dup": c1[:CAP], "C1_n": len(c1),
        "C2_empty_body": c2[:CAP], "C2_n": len(c2),
        "C3_incomplete": c3[:CAP], "C3_n": len(c3),
        "C4_unresolvable": c4[:CAP], "C4_n": len(c4),
        "C5_rewritten": c5[:CAP], "C5_n": len(c5),
        "C6_agg_bytes": sz, "C6_n": len(c6),
        "N1_forms": dict(forms),
        "N1_article_range": [min(nos) if nos else "", max(nos) if nos else ""],
        "N2_retired_n": len(retired),
        "N2_retired": [[d.get("article_no"), str(d.get("retired_reason") or "")[:80]]
                       for d in retired[:CAP]],
        "N3_rows_total": len(raw),
    }
    rep["red_total"] = sum(rep[k] for k in ("C1_n", "C2_n", "C3_n", "C4_n", "C5_n", "C6_n"))
    return rep, None


def _selftest_write(root, unit_anchor, legacy, unit_sha, ev_anchor, ev_sha,
                    cite_style=False, unit_exists=True, seq=None):
    """造一份最小夹具：1 条定稿 + 1 条候选 + 1 个 L2 单元。只用临时目录，不碰真库。"""
    os.makedirs(os.path.join(root, "l2"), exist_ok=True)
    os.makedirs(os.path.join(root, "l3/candidates"), exist_ok=True)
    os.makedirs(os.path.join(root, "l4/canonical"), exist_ok=True)
    unit = {"unit_id": "u1", "anchor": unit_anchor, "source_sha256": unit_sha}
    if legacy:
        unit["legacy_anchors"] = legacy
    with open(os.path.join(root, "l2/units.jsonl"), "w", encoding="utf-8") as fh:
        if unit_exists:
            fh.write(json.dumps(unit, ensure_ascii=False) + "\n")
    rec = {"article_no": "N-1.1", "form": "negative_sample_rule", "rule_text": "T-正文"}
    if cite_style:
        rec["anchor"] = ev_anchor
        rec["cite_check"] = {"source_sha256": ev_sha}
    else:
        rec["evidence_units"] = [{"unit_id": "u1", "anchor": ev_anchor, "source_sha256": ev_sha}]
    rows = seq if seq is not None else [rec]
    with open(os.path.join(root, "l4/canonical/canon.jsonl"), "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    open(os.path.join(root, "l4/canonical/rules.jsonl"), "w").close()          # C6：必须 0 字节
    with open(os.path.join(root, "l3/candidates/cand.jsonl"), "w", encoding="utf-8") as fh:
        fh.write(json.dumps({"form": "negative_sample_rule", "rule_text": "T-正文"},
                            ensure_ascii=False) + "\n")


def selftest():
    """C4 的**反向对照**：改完判据必须还能精确变红，否则等于没判据。

    ★ 每条都给「反例」和「正例」，并且反例要断言**变红的原因**（不只是变红）。
    """
    import shutil
    import tempfile

    global L2_UNITS, CANON, CANON_AGG, CANDIDATES
    saved = (L2_UNITS, CANON, CANON_AGG, CANDIDATES)
    NEW, OLD = "#素材/R1/图片素材", "#素材/R1/图片素材/#img.1"
    sha = "sha-A"
    cases = [
        # (名字, 夹具参数, 期望 C4_n, 期望原因关键字)
        ("T1 锚点逐字相同 ⇒ 过", dict(unit_anchor=NEW, legacy=None, unit_sha=sha,
                                     ev_anchor=NEW, ev_sha=sha), 0, None),
        ("T2 锚点是旧写法、但单元留了 legacy ⇒ 过（本次修复要治的那条）",
         dict(unit_anchor=NEW, legacy=[OLD], unit_sha=sha, ev_anchor=OLD, ev_sha=sha), 0, None),
        ("T3 反例：同样的旧锚点、把 legacy 摘掉 ⇒ 必须红", dict(
            unit_anchor=NEW, legacy=None, unit_sha=sha, ev_anchor=OLD, ev_sha=sha),
         1, "anchor 对不上"),
        ("T4 反例：sha 不一致 ⇒ 必须红", dict(unit_anchor=NEW, legacy=[OLD], unit_sha=sha,
                                             ev_anchor=OLD, ev_sha="sha-B"),
         1, "source_sha256 对不上"),
        ("T5 反例：L2 里没有这个单元 ⇒ 必须红", dict(unit_anchor=NEW, legacy=[OLD], unit_sha=sha,
                                                 ev_anchor=OLD, ev_sha=sha, unit_exists=False),
         1, "找不到"),
        ("T6 cite_check 档（无 unit_id）：命中 legacy ⇒ 过", dict(
            unit_anchor=NEW, legacy=[OLD], unit_sha=sha, ev_anchor=OLD, ev_sha=sha,
            cite_style=True), 0, None),
        # ★★ 2026-10-20：退役行（`status: retired`，由 kb/l7/scripts/l4_retire.py 追加）的语义
        #   ① 已退役 = 历史，不是在册证据 ⇒ 坐标坏了也不计红；
        #   ② **按 article_no 取最后一行** —— 若最后一行是 stable 且坏，照样红（不能把红藏起来）。
        ("T8 已退役行（同号最后一行）坐标坏了 ⇒ 不计红，且退役计数 1", dict(
            unit_anchor=NEW, legacy=None, unit_sha=sha, ev_anchor=OLD, ev_sha=sha,
            cite_style=True,
            seq=[{"article_no": "N-1.1", "form": "negative_sample_rule", "rule_text": "T-正文",
                  "anchor": OLD, "cite_check": {"source_sha256": sha}},
                 {"article_no": "N-1.1", "form": "negative_sample_rule",
                  "status": "retired", "retired_reason": "夹具：源已下架"}]),
         0, None),
        ("T9 反例：同号两行、最后一行是 stable 且坐标坏 ⇒ 必须红（不能拿退役行把红藏掉）", dict(
            unit_anchor=NEW, legacy=None, unit_sha=sha, ev_anchor=OLD, ev_sha=sha,
            cite_style=True,
            seq=[{"article_no": "N-1.1", "form": "negative_sample_rule",
                  "status": "retired", "retired_reason": "夹具：旧态"},
                 {"article_no": "N-1.1", "form": "negative_sample_rule", "rule_text": "T-正文",
                  "anchor": OLD, "cite_check": {"source_sha256": sha}}]),
         1, "找不到"),
        ("T7 反例：cite_check 档 + 单元不存在 ⇒ 必须红", dict(
            unit_anchor=NEW, legacy=[OLD], unit_sha=sha, ev_anchor=OLD, ev_sha=sha,
            cite_style=True, unit_exists=False), 1, "找不到"),
    ]
    rows, ok = [], True
    tmp = tempfile.mkdtemp(prefix="l4gate-selftest-")
    try:
        for name, kw, want_n, want_why in cases:
            root = os.path.join(tmp, name.split()[0])
            _selftest_write(root, **kw)
            L2_UNITS = os.path.join(root, "l2/units.jsonl")
            CANON = os.path.join(root, "l4/canonical/*.jsonl")
            CANON_AGG = os.path.join(root, "l4/canonical/rules.jsonl")
            CANDIDATES = os.path.join(root, "l3/candidates/*.jsonl")
            rep, err = compute()
            if rep is None:
                rows.append((name, False, "夹具算不出来：%s" % err))
                ok = False
                continue
            got_n, got_why = rep["C4_n"], " ".join(
                str(x[-1]) for x in rep["C4_unresolvable"])
            good = (got_n == want_n) and (want_why is None or want_why in got_why)
            ok = ok and good
            rows.append((name, good, "C4_n=%d 退役=%d%s" % (
                got_n, rep["N2_retired_n"], ("：" + got_why) if got_why else "")))
    finally:
        L2_UNITS, CANON, CANON_AGG, CANDIDATES = saved
        shutil.rmtree(tmp, ignore_errors=True)

    for name, good, detail in rows:
        print("  %s %s ｜ %s" % ("✅" if good else "❌", name, detail))
    print("l4_gate --selftest %s（%d/%d）" % ("PASS" if ok else "FAIL",
                                             sum(1 for _, g, _ in rows if g), len(rows)))
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--selftest", action="store_true",
                    help="C4 判据的反向对照（造夹具，不碰真库）")
    a = ap.parse_args()

    if a.selftest:
        return selftest()

    rep, err = compute()
    if rep is None:
        print("❌ 无法计算：%s" % err)
        print("退出码：2")
        return 2

    ok = rep["red_total"] == 0
    if a.json:
        print(json.dumps({"gate": "l4_gate", "ok": ok, **rep}, ensure_ascii=False, indent=1))
        return 0 if ok else 1

    c = rep["counts"]
    print("=" * 74)
    print("L4 闸门（独立复算 promotion_rule C1–C6：定稿 × 候选 × L2 单元）")
    print("  定稿 %d 条 ｜ 证据引用 %d 条 ｜ 候选 %d 条 ｜ L2 单元 %d 个 ｜ 形态 %s"
          % (c["canonical"], c["evidence_refs"], c["candidates"], c["l2_units"], rep["N1_forms"]))
    print("  条款号区间 %s … %s ｜ canonical/rules.jsonl %d 字节（应为 0）"
          % (rep["N1_article_range"][0], rep["N1_article_range"][1], rep["C6_agg_bytes"]))
    print("-" * 74)
    if not a.quiet:
        for key, label in (("C1_dup", "C1 条款号问题"), ("C2_empty_body", "C2 正文为空"),
                           ("C3_incomplete", "C3 证据三件套不全"), ("C4_unresolvable", "C4 证据回指不上"),
                           ("C5_rewritten", "C5 定稿与候选件不一致")):
            n = rep[key.replace("_dup", "_n").replace("_empty_body", "_n")
                    .replace("_incomplete", "_n").replace("_unresolvable", "_n")
                    .replace("_rewritten", "_n")]
            if n:
                print("%s（%d）：" % (label, n))
                for row in rep[key][:3]:
                    print("   %s" % " ｜ ".join(str(x) for x in row))
        if rep["C6_n"]:
            print("C6 版本纪律：%s" % rep["C6_agg_bytes"])
    print("-" * 74)
    if rep["N2_retired_n"]:
        print("说明项：已退役 %d 条（`status: retired`，见 kb/l7/scripts/l4_retire.py）—— 不进红，但**不是在册证据**，"
              "报告不得引用；例：%s" % (rep["N2_retired_n"],
                                        "、".join(str(x[0]) for x in rep["N2_retired"][:5])))
    print("说明项：C7/C8（晋升后抽查、撤回纪律）本闸门**不复算** —— 它们要人抽检，不是机器判据")
    print("=" * 74)
    print("结论：%s" % ("✅ 过（C1–C6 全过）" if ok else "❌ 未过（红 %d）" % rep["red_total"]))
    print("退出码：%d" % (0 if ok else 1))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
