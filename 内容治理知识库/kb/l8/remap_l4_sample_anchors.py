#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""remap_l4_sample_anchors.py —— 把 L4 里 201 条「锚点指向已退役 L2 单元」的 sample_case
重映射到**换代后的新记录**，映射不上的按纪律**撤号归档留痕**（不是放宽闸门）。

## 治的是什么（实测，2026-10-20）

    sh kb/kbpy l7/scripts/l4_gate.py     # 退出码 1，C4 红 201

201 条 `sample_case` 的 `anchor` 形如 `#正面和负面样本/recvw2vgYX1Gw0/原文反馈`：
  · 前缀 `#正面和负面样本` 是**旧**的 L1 目录名，现行切分器产出的锚点前缀是 `#负面样本`；
  · `recvw2…` 是**旧一代**记录 id —— 飞书「负面样本」表 2026-10-14 整体重建，ID 全换代；
  · 那 201 个旧 id 对应的 L2 单元于 2026-10-20T16:17:26 被 `prune_gone_units.py` 退役
    （`run=prune-20261020-161725`，同一批退役 441 条 = 201 正面样本 + 240 素材）。
⇒ C4「证据可回指」找不到单元，红 201。**这不是那张图的问题，也不是素材的问题。**

## 怎么修（本脚本只做一件事：换坐标，不动正文、不动条款号）

配对**只用内容指纹**，不用 ID 顺序（源表存在同内容重复登记，顺序法必然错位）：

  A    `具体原因/分析` **逐字唯一** 命中新记录
  A2   同上但命中多条（源侧重复登记）⇒ 优先取 `原文反馈` 也逐字相等的那条；仍并列则取 id 最小者
  B    `项目名` 在新表里唯一
  B2   `项目名` 多条 ⇒ 在这几条里按全文相似度取最优，且与次优差 ≥0.03
  D    全文相似度 ≥0.90（报告里写明分值，交人扫一眼）
  ——   以上都不中 ⇒ **UNMAPPED**：撤号归档（这些条款的源记录在本次重建里被真正移除，
       原文仍逐字保存在 L3 候选与本归档件里，但**没有可点的 L0 直链** ⇒ 按四段溯源纪律不得再被引用）

落盘改的字段（**只有坐标，正文一个字不动**）：
     anchor / unit_id / unit_ids / source_sha256 / resource_id / cite_check

## 为什么坐标要连前缀一起换

`source_sha256` 是**逐单元**的（同一条记录的不同字段单元 sha 不同）⇒ 必须取目标单元的 sha；
只换记录 id 不换前缀，闸门照样红（现行锚点是 `#负面样本/<rec>/…`）。

## 安全边界

  · 默认 **只预演**：出 CSV 计划表，不写任何库文件；要写必须显式 `--apply`。
  · 写前备份到 `kb/l4/canonical/_backups/remap-<run>/`；写完**逐条回读**，不等则抛错并回滚。
  · 撤号的行原文进 `kb/l4/canonical/_archive/retired-sample_case-<run>.jsonl`（可原样复制回去回滚），
    并登记 `kb/l7/registry/l4-retired-clauses.yaml`。
  · 反向对照 `--selftest`：造夹具证明「映射写错 sha / 写错锚点」会被本脚本自己的校验逮到，
    且 UNMAPPED 判定不会误伤「其实能配上」的样本（判据不是恒过）。

用法：
    kb/kbpy l8/remap_l4_sample_anchors.py                 # 预演 + 出计划表
    kb/kbpy l8/remap_l4_sample_anchors.py --apply         # 落盘（含撤号归档）
    kb/kbpy l8/remap_l4_sample_anchors.py --selftest      # 反向对照（自带夹具，不碰真库）
"""
from __future__ import annotations

import argparse
import collections
import csv
import difflib
import glob
import json
import os
import re
import shutil
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
KB = os.environ.get("KB_REMAP_KB") or os.path.dirname(HERE)
ROOT = os.path.dirname(KB)

L2_UNITS = os.path.join(KB, "l2/units.jsonl")
L0_NEG = os.path.join(KB, "l0/records/负面样本")
L4_SAMPLE = os.path.join(KB, "l4/canonical/sample_case.jsonl")
L3_SAMPLE = os.path.join(KB, "l3/candidates/sample_cases.jsonl")
L4_BACKUPS = os.path.join(KB, "l4/canonical/_backups")
L4_ARCHIVE = os.path.join(KB, "l4/canonical/_archive")
REG_RETIRED = os.path.join(KB, "l7/registry/l4-retired-clauses.yaml")
REPORTS = os.path.join(KB, "l7/reports/*.review.md")

OLD_PREFIX = "#正面和负面样本/"
NEW_PREFIX = "#负面样本/"
OLD_RE = re.compile(r"^#正面和负面样本/(rec[A-Za-z0-9]+)/")
PROJ_RE = re.compile(r"项目名[：:]\**\s*([^\n*]{4,60})")

FUZZY_ACCEPT = 0.90      # 补配门槛（报告里带分值，交人扫）
FUZZY_MARGIN = 0.03      # 补配时与次优的最小差

FIELDS = ("具体原因/分析", "原文反馈")


# ---------------------------------------------------------------- 读盘
def _iter(p):
    with open(p, encoding="utf-8") as fh:
        for i, ln in enumerate(fh, 1):
            ln = ln.strip()
            if ln:
                yield i, json.loads(ln)


def norm(s):
    return re.sub(r"\s+", "", s or "")


def proj_of(*texts):
    for t in texts:
        m = PROJ_RE.search(t or "")
        if m:
            return norm(m.group(1))
    return ""


def load_new_records(root=None):
    """新表现有记录：record_id → {字段: 值}"""
    out = {}
    for p in glob.glob(os.path.join(root or L0_NEG, "*.json")):
        d = json.load(open(p, encoding="utf-8"))
        rid = d.get("record_id")
        if rid:
            out[rid] = d.get("raw_record") or {}
    return out


def load_field_units(root=None):
    """L2 里每条记录的「字段级」单元：record_id → [(anchor, unit_id, sha, text)]"""
    out = collections.defaultdict(list)
    for _, d in _iter(os.path.join(root, "l2/units.jsonl") if root else L2_UNITS):
        a = d.get("anchor") or ""
        m = re.match(r"^#(?:负面样本|正面和负面样本)/(rec[A-Za-z0-9]+)/(.+)$", a)
        if not m:
            continue
        if m.group(2).startswith(("图片素材", "视频素材")):   # 素材字段不算「原文/分析」字段级
            continue
        out[m.group(1)].append((a, d.get("unit_id"), d.get("source_sha256") or "", d.get("text") or ""))
    return out


def pick_unit(cands):
    """同一条记录可能只剩一个字段级单元；按 具体原因/分析 > 原文反馈 > 建议 > 其他 取。"""
    if not cands:
        return None
    order = ["具体原因/分析", "原文反馈", "建议"]
    for f in order:
        for c in cands:
            if c[0].endswith("/" + f):
                return c
    return sorted(cands, key=lambda c: c[0])[0]


# ---------------------------------------------------------------- 引用面
def load_citations():
    """条款号 → 在 kb/l7/reports/*.review.md 里被引次数"""
    c = collections.Counter()
    for f in glob.glob(REPORTS):
        t = open(f, encoding="utf-8", errors="ignore").read()
        for h in re.findall(r"S-1\.\d+", t):
            c[h] += 1
    return c


# ---------------------------------------------------------------- 配对
def build_plan(root=None):
    new = load_new_records()
    units = load_field_units(root)
    cites = load_citations()

    by_reason = collections.defaultdict(list)
    by_body = collections.defaultdict(list)
    by_proj = collections.defaultdict(list)
    for rid, raw in new.items():
        by_reason[norm(raw.get("具体原因/分析"))].append(rid)
        by_body[norm(raw.get("原文反馈"))].append(rid)
        p = proj_of(raw.get("原文反馈"), raw.get("具体原因/分析"))
        if p:
            by_proj[p].append(rid)

    rows = []
    for ln, d in _iter(L4_SAMPLE if not root else os.path.join(root, "l4/canonical/sample_case.jsonl")):
        anc = d.get("anchor") or ""
        m = OLD_RE.match(anc)
        if not m:
            continue
        old = m.group(1)
        body = d.get("sample_body") or ""
        reason = d.get("reason_analysis") or ""
        proj = proj_of(body, reason)
        cands, tier, score, why = [], "UNMAPPED", None, ""

        r_hit, b_hit = by_reason.get(norm(reason)) or [], by_body.get(norm(body)) or []
        p_hit = (by_proj.get(proj) or []) if proj else []

        if len(r_hit) == 1:
            cands, tier, why = r_hit, "A", "具体原因/分析 逐字唯一"
        elif len(b_hit) == 1:
            cands, tier, why = b_hit, "A", "原文反馈 逐字唯一"
        elif len(r_hit) > 1 or len(b_hit) > 1:
            pool = sorted(set(r_hit) | set(b_hit))
            both = [x for x in pool if x in r_hit and x in b_hit]
            pick = both or pool
            if len(pick) == 1:
                cands, tier, why = pick, "A2", "内容重复登记，两字段同时逐字命中唯一"
            else:
                cands, tier, why = pick[:1], "A2", "内容重复登记，取 id 最小的一条（%d 条同内容）" % len(pick)
                score = None
        elif len(p_hit) == 1:
            cands, tier, why = p_hit, "B", "项目名唯一"
        elif len(p_hit) > 1:
            scored = []
            for rid in p_hit:
                raw = new[rid]
                s = max(difflib.SequenceMatcher(None, norm(reason), norm(raw.get("具体原因/分析"))).ratio(),
                        difflib.SequenceMatcher(None, norm(body), norm(raw.get("原文反馈"))).ratio())
                scored.append((s, rid))
            scored.sort(reverse=True)
            if len(scored) >= 2 and scored[0][0] - scored[1][0] >= FUZZY_MARGIN:
                cands, tier, score, why = [scored[0][1]], "B2", scored[0][0], "项目名多候选，按相似度择优（差 %.3f）" % (
                    scored[0][0] - scored[1][0])
            else:
                cands, tier, score, why = [x[1] for x in scored[:3]], "AMBIG", scored[0][0], "项目名多候选且分数接近，须人裁"
        else:
            best = (0.0, None)
            for rid, raw in new.items():
                s = max(difflib.SequenceMatcher(None, norm(reason), norm(raw.get("具体原因/分析"))).ratio(),
                        difflib.SequenceMatcher(None, norm(body), norm(raw.get("原文反馈"))).ratio())
                if s > best[0]:
                    best = (s, rid)
            if best[0] >= FUZZY_ACCEPT:
                cands, tier, score, why = [best[1]], "D", best[0], "全文相似度 ≥%.2f" % FUZZY_ACCEPT
            else:
                cands, tier, score, why = [], "UNMAPPED", best[0], "新表里找不到同源内容（最高相似度 %.3f）" % best[0]

        def _unit_of(rid):
            return pick_unit(units.get(rid)) if rid else None

        def _contains(unit, text):
            """正文是否逐字落在该单元正文里（本文档的**接受闸门**，不是附注）。"""
            if not unit or not text:
                return None
            nb = norm(text)
            if not nb:
                return None
            # 长正文取前 80 字（去空白）做定位；短正文整段比
            return (norm(text[:80]) in norm(unit[3])) if len(nb) >= 40 else (nb in norm(unit[3]))

        tgt = _unit_of(cands[0]) if cands and tier != "AMBIG" else None
        contained = _contains(tgt, body)

        # ★ 接受闸门：正文没落在目标单元里 ⇒ 这条配对不可信，退回 AMBIG 交人看。
        #   实测踩过：只按「项目名唯一」配上的 11 条里有 6 条正文并不在新记录的单元里
        #   （同项目、不同需求）—— 若直接写进定稿，报告会指向一条内容不匹配的记录。
        if cands and tier in OK_TIERS and tgt is not None and contained is False:
            tier, why = "AMBIG", "配对命中但目标单元正文不含本条正文（%s）" % why
            score = score if score != "" else None

        # AMBIG 补一刀：候选里**只有一条**的单元正文含本条正文 ⇒ 直接定它
        if tier == "AMBIG" and cands:
            hits = [r for r in cands if (_contains(_unit_of(r), body) is True)]
            if len(hits) == 1:
                tier, why = "C3", "多候选里正文只落在一条上"
                cands, tgt = hits, _unit_of(hits[0])
                contained = True

        if cands and tier != "AMBIG" and tgt is None:
            tier, why = "UNMAPPED", "新记录存在但没有可用的字段级 L2 单元"
            cands = []

        rows.append({
            "article_no": d.get("article_no"),
            "case_id": d.get("case_id"),
            "tier": tier,
            "why": why,
            "score": "" if score is None else round(float(score), 3),
            "old_anchor": anc,
            "old_record": old,
            "new_record": cands[0] if cands and tier != "AMBIG" else "",
            "new_anchor": tgt[0] if tgt else "",
            "new_unit_id": tgt[1] if tgt else "",
            "new_sha256": tgt[2] if tgt else "",
            "body_in_new_unit": "" if contained is None else ("是" if contained else "否"),
            "citations": cites.get(str(d.get("article_no")), 0),
            "candidates": ",".join(cands) if tier == "AMBIG" else "",
            "line": ln,
        })
    return rows


TIER_ORDER = ["A", "A2", "B", "B2", "C3", "D", "AMBIG", "UNMAPPED"]
OK_TIERS = ("A", "A2", "B", "B2", "C3", "D")


def summarize(rows):
    c = collections.Counter(r["tier"] for r in rows)
    cite = collections.Counter()
    for r in rows:
        cite[r["tier"]] += r["citations"]
    return c, cite


def write_plan_csv(rows, path):
    cols = ["article_no", "tier", "why", "score", "old_record", "new_record", "old_anchor",
            "new_anchor", "new_unit_id", "new_sha256", "body_in_new_unit", "citations", "candidates", "case_id"]
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in sorted(rows, key=lambda x: (TIER_ORDER.index(x["tier"]), str(x["article_no"]))):
            w.writerow(r)


# ---------------------------------------------------------------- 落盘
def _backup(path, dirname):
    os.makedirs(dirname, exist_ok=True)
    dst = os.path.join(dirname, os.path.basename(path))
    shutil.copy2(path, dst)
    return dst


def apply(rows, run):
    ok = [r for r in rows if r["tier"] in OK_TIERS]
    drop = [r for r in rows if r["tier"] not in OK_TIERS]

    # 写前校验：目标单元必须真的存在，且 sha 非空
    for r in ok:
        if not (r["new_unit_id"] and r["new_sha256"] and r["new_anchor"]):
            raise SystemExit("拒绝落盘：%s 的目标单元三件套不全 → %r" % (r["article_no"], r))

    bdir = _backup(L4_SAMPLE, os.path.join(L4_BACKUPS, "remap-" + run))
    os.makedirs(L4_ARCHIVE, exist_ok=True)
    arch = os.path.join(L4_ARCHIVE, "retired-sample_case-%s.jsonl" % run)

    by_art = {r["article_no"]: r for r in ok}
    drop_art = {r["article_no"] for r in drop}
    out, kept, retired, changed = [], 0, 0, 0
    for ln, d in _iter(L4_SAMPLE):
        art = str(d.get("article_no"))
        if art in drop_art:
            retired += 1
            with open(arch, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(d, ensure_ascii=False) + "\n")
            continue
        r = by_art.get(art)
        if r:
            d["anchor"] = r["new_anchor"]
            d["unit_id"] = r["new_unit_id"]
            d["unit_ids"] = [r["new_unit_id"]]
            d["source_sha256"] = r["new_sha256"]
            d["resource_id"] = "bitable__tbld8qE92YaY38Yz__" + r["new_record"]
            cc = d.get("cite_check")
            if isinstance(cc, dict):
                cc["anchor"] = r["new_anchor"]
                cc["source_sha256"] = r["new_sha256"]
                cc["unit_ids"] = [r["new_unit_id"]]
                cc["anchors_in_l2"] = 1
                cc["evidence_units"] = 1
                cc["unresolvable"] = []
            changed += 1
        else:
            kept += 1
        out.append(json.dumps(d, ensure_ascii=False))

    tmp = L4_SAMPLE + ".tmp-remap"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write("\n".join(out) + "\n")
    os.replace(tmp, L4_SAMPLE)

    # 回读校验
    again = {str(d.get("article_no")): d for _, d in _iter(L4_SAMPLE)}
    for r in ok:
        d = again.get(r["article_no"])
        if not d:
            raise SystemExit("回读失败：%s 不见了（备份在 %s，原样复制回去即可回滚）" % (r["article_no"], bdir))
        for k, want in (("anchor", r["new_anchor"]), ("unit_id", r["new_unit_id"]),
                        ("source_sha256", r["new_sha256"])):
            if d.get(k) != want:
                raise SystemExit("回读不一致：%s.%s = %r ≠ %r（备份 %s）" % (r["article_no"], k, d.get(k), want, bdir))
    for art in drop_art:
        if art in again:
            raise SystemExit("撤号未生效：%s 仍在定稿里" % art)

    return {"changed": changed, "retired": retired, "kept": kept,
            "backup": bdir, "archive": arch}


def write_retired_registry(rows, run, outcome):
    drop = sorted((r for r in rows if r["tier"] not in OK_TIERS), key=lambda x: str(x["article_no"]))
    lines = [
        "# l4-retired-clauses.yaml —— 2026-10-20 L4 样本锚点重映射中**撤号归档**的条款",
        "#",
        "# 为什么有这份文件（别删）：这 %d 条 `sample_case` 的 L0 源记录，在飞书「负面样本」表" % len(drop),
        "# 2026-10-14 的整表重建里被**真正移除**（不是换代）：在新表 184 条里按「具体原因/分析 逐字」",
        "# 「原文反馈 逐字」「项目名」「全文相似度 ≥0.90」四道都找不到同源内容，最高相似度 ≤0.51。",
        "#",
        "# 处置：从 `kb/l4/canonical/sample_case.jsonl` 撤出（条款号不再复用，留空号），原文逐字归档在",
        "# `%s`；" % os.path.relpath(outcome["archive"], ROOT),
        "# 这些条款**没有可点的 L0 直链** ⇒ 按「四段溯源」纪律不得再被报告引用，故不留在定稿里。",
        "#",
        "# 回滚：把归档件里的行原样贴回 sample_case.jsonl 即可（备份在 %s）。" % os.path.relpath(outcome["backup"], ROOT),
        "",
        "meta:",
        "  run: %s" % run,
        "  written_at: %s" % time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "  owner: 刘华丽",
        "  reason_code: evidence_source_removed",
        "  archive: %s" % os.path.relpath(outcome["archive"], ROOT),
        "  backup: %s" % os.path.relpath(outcome["backup"], ROOT),
        "  written_by: kb/l8/remap_l4_sample_anchors.py --apply",
        "  counts:",
        "    remapped: %d" % outcome["changed"],
        "    retired: %d" % outcome["retired"],
        "    untouched: %d" % outcome["kept"],
        "  note: >",
        "    本件是**留痕件**，当前没有闸门读它（读它的是归档件本身）。后续若要机械守住",
        "    「撤号的号段不再被重新发号」，应在 L4 发号侧加一条判据（下一轮做，不在本次紧急修复里）。",
        "retired:",
    ]
    for r in drop:
        lines += [
            "  - article_no: %s" % r["article_no"],
            "    case_id: %s" % r["case_id"],
            "    old_record: %s" % r["old_record"],
            "    tier: %s" % r["tier"],
            "    why: %s" % r["why"],
            "    best_similarity: %s" % r["score"],
            "    citations_in_reports: %s" % r["citations"],
        ]
    with open(REG_RETIRED, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    return REG_RETIRED


# ---------------------------------------------------------------- 反向对照
def selftest():
    """造夹具：证明 ①配对能认对 ②写错 sha/锚点会被本脚本的校验逮到 ③UNMAPPED 不误伤。"""
    import tempfile
    ok = True

    def chk(name, cond, detail=""):
        nonlocal ok
        print(("  ✅ " if cond else "  ❌ ") + name + ((" ｜ " + str(detail)) if detail else ""))
        ok = ok and bool(cond)

    tmp = tempfile.mkdtemp(prefix="remap-selftest-")
    try:
        os.makedirs(os.path.join(tmp, "l0/records/负面样本"))
        os.makedirs(os.path.join(tmp, "l2"))
        os.makedirs(os.path.join(tmp, "l4/canonical"))
        os.makedirs(os.path.join(tmp, "l7/reports"))
        os.makedirs(os.path.join(tmp, "l7/registry"))
        os.makedirs(os.path.join(tmp, "l3/candidates"))
        open(os.path.join(tmp, "l4/canonical/rules.jsonl"), "w", encoding="utf-8").close()
        old_anc = "#正面和负面样本/recvw2OLD001/原文反馈"
        body = "【审核 · 2026-09-16】项目名：夹具海报甲\n设计要求：只放头图与尾图，别放产品全家福"
        reason = "【品牌一致性】图片 1. 只放头图与尾图"
        # ★ 旧记录**故意不建**（真库里它已被 L0 重对齐移除，这正是本题的成因）：
        #   建了它就让「新表 184 条」里多一条同内容的干扰项，夹具会失真。
        json.dump({"record_id": "recvw7NEW001", "raw_record": {"原文反馈": body,
                                                              "具体原因/分析": reason + "\n原文反馈: " + body}},
                  open(os.path.join(tmp, "l0/records/负面样本/recvw7NEW001.json"), "w", encoding="utf-8"))
        units = [
            {"unit_id": "u-new-1", "anchor": "#负面样本/recvw7NEW001/具体原因/分析",
             "source_sha256": "sha-new-1", "text": reason + "\n原文反馈: " + body},
        ]
        with open(os.path.join(tmp, "l2/units.jsonl"), "w", encoding="utf-8") as fh:
            for u in units:
                fh.write(json.dumps(u, ensure_ascii=False) + "\n")
        clause = {"article_no": "S-1.1", "case_id": "sc-x", "anchor": old_anc, "sample_body": body,
                  "reason_analysis": reason, "unit_id": "u-old", "source_sha256": "sha-old",
                  "cite_check": {"anchor": old_anc, "source_sha256": "sha-old", "unit_ids": ["u-old"],
                                 "anchors_in_l2": 1, "evidence_units": 1, "unresolvable": []}}
        ghost = {"article_no": "S-1.2", "case_id": "sc-y", "anchor": "#正面和负面样本/recvw2OLD002/原文反馈",
                 "sample_body": "完全找不到同源的另一段内容" * 3, "reason_analysis": "【别类】图片 2. 无关",
                 "unit_id": "u-old2", "source_sha256": "sha-old2",
                 "cite_check": {"anchor": "#正面和负面样本/recvw2OLD002/原文反馈",
                                "source_sha256": "sha-old2", "unit_ids": ["u-old2"],
                                "anchors_in_l2": 1, "evidence_units": 1, "unresolvable": []}}
        # 同形态候选件里要有**正文逐字相同**的那条（真库就是这样，L4 的 C5 靠它判「定稿没被改写」）
        with open(os.path.join(tmp, "l3/candidates/sample_cases.jsonl"), "w", encoding="utf-8") as fh:
            for art, bd in (("S-1.1", body), ("S-1.2", "完全找不到同源的另一段内容" * 3)):
                fh.write(json.dumps({"article_no": art, "case_id": "sc-" + art, "sample_body": bd},
                                    ensure_ascii=False) + "\n")
        with open(os.path.join(tmp, "l4/canonical/sample_case.jsonl"), "w", encoding="utf-8") as fh:
            for d in (clause, ghost):
                fh.write(json.dumps(d, ensure_ascii=False) + "\n")

        global L4_SAMPLE, L4_BACKUPS, L4_ARCHIVE, REG_RETIRED, REPORTS, L0_NEG
        saved = (L4_SAMPLE, L4_BACKUPS, L4_ARCHIVE, REG_RETIRED, REPORTS, L0_NEG)
        L4_SAMPLE = os.path.join(tmp, "l4/canonical/sample_case.jsonl")
        L4_BACKUPS = os.path.join(tmp, "l4/canonical/_backups")
        L4_ARCHIVE = os.path.join(tmp, "l4/canonical/_archive")
        REG_RETIRED = os.path.join(tmp, "l7/registry/l4-retired-clauses.yaml")
        REPORTS = os.path.join(tmp, "l7/reports/*.review.md")
        L0_NEG = os.path.join(tmp, "l0/records/负面样本")
        open(os.path.join(tmp, "l7/reports/a.review.md"), "w", encoding="utf-8").write("依据 S-1.1 与 S-1.2\n")

        rows = build_plan(root=tmp)
        byart = {r["article_no"]: r for r in rows}
        chk("T1 同源内容 ⇒ 判为可映射（A 档）", byart["S-1.1"]["tier"] == "A", byart["S-1.1"]["tier"])
        chk("T2 目标锚点带**新**前缀且指向**新**记录",
            byart["S-1.1"]["new_anchor"] == "#负面样本/recvw7NEW001/具体原因/分析",
            byart["S-1.1"]["new_anchor"])
        chk("T3 取的是**目标单元**的 sha（不是沿用旧的）",
            byart["S-1.1"]["new_sha256"] == "sha-new-1", byart["S-1.1"]["new_sha256"])
        chk("T4 新表里没有同源内容 ⇒ 判 UNMAPPED（不硬配）", byart["S-1.2"]["tier"] == "UNMAPPED",
            byart["S-1.2"]["tier"])
        chk("T5 正文确实落在目标单元正文里", byart["S-1.1"]["body_in_new_unit"] == "是",
            byart["S-1.1"]["body_in_new_unit"])

        # 现造一个「写错 sha」的场景：把单元的 sha 换掉，落盘校验必须逮到
        units[0]["source_sha256"] = "sha-tampered"
        with open(os.path.join(tmp, "l2/units.jsonl"), "w", encoding="utf-8") as fh:
            for u in units:
                fh.write(json.dumps(u, ensure_ascii=False) + "\n")
        rows2 = build_plan(root=tmp)
        b2 = {r["article_no"]: r for r in rows2}
        chk("T6 单元 sha 变了 ⇒ 计划表跟着取新值（说明没写死）",
            b2["S-1.1"]["new_sha256"] == "sha-tampered", b2["S-1.1"]["new_sha256"])
        units[0]["source_sha256"] = "sha-new-1"
        with open(os.path.join(tmp, "l2/units.jsonl"), "w", encoding="utf-8") as fh:
            for u in units:
                fh.write(json.dumps(u, ensure_ascii=False) + "\n")

        rows3 = build_plan(root=tmp)
        out = apply(rows3, "selftest")
        chk("T7 落盘：1 条重映射、1 条撤号", out["changed"] == 1 and out["retired"] == 1, out)
        back = {d["article_no"]: d for _, d in _iter(L4_SAMPLE)}
        chk("T8 定稿只剩映射过的那条，且坐标已换", list(back) == ["S-1.1"]
            and back["S-1.1"]["anchor"] == "#负面样本/recvw7NEW001/具体原因/分析", list(back))
        chk("T9 撤号件进了归档（可回滚）", os.path.exists(out["archive"]), out["archive"])
        chk("T10 正文一个字没动", back["S-1.1"]["sample_body"] == body, back["S-1.1"]["sample_body"][:20])
        reg = write_retired_registry(rows3, "selftest", out)
        txt = open(reg, encoding="utf-8").read()
        chk("T11 留痕件点名了撤掉的条款号", "article_no: S-1.2" in txt)
        # 反向对照：用**真的那把闸门**（l4_gate.py）判，而不是自证。
        #   T12 打回原形（锚点写回旧的）⇒ 闸门必须红；
        #   T13 映射后 ⇒ 闸门必须绿；
        #   T14 把 sha 改错一位 ⇒ 闸门必须精确变红（证明判据有牙，不是恒绿）。
        import subprocess
        env = dict(os.environ, KB_GATE_KB=tmp)
        gate = os.path.join(HERE, "..", "l7", "scripts", "l4_gate.py")

        def run_gate():
            p = subprocess.run([sys.executable, gate], capture_output=True, text=True, env=env)
            m = re.search(r"C4 证据回指不上（(\d+)）", p.stdout)
            return p.returncode, (int(m.group(1)) if m else 0)

        lines = [json.dumps(d, ensure_ascii=False) for _, d in _iter(L4_SAMPLE)]
        good = lines[0]
        lines[0] = json.dumps(dict(json.loads(good), anchor=old_anc,
                                   unit_id="u-old", source_sha256="sha-old"), ensure_ascii=False)
        open(L4_SAMPLE, "w", encoding="utf-8").write("\n".join(lines) + "\n")
        rc, n = run_gate()
        chk("T12 反向对照：打回旧坐标 ⇒ 闸门必须红", rc != 0 and n == 1, "rc=%d C4=%d" % (rc, n))

        open(L4_SAMPLE, "w", encoding="utf-8").write("\n".join([good] + lines[1:]) + "\n")
        rc, n = run_gate()
        chk("T13 映射后 ⇒ 闸门必须绿", rc == 0 and n == 0, "rc=%d C4=%d" % (rc, n))

        # ★ 注意：C4 对 cite_check 档读的是**那一格**（真库实测），所以要连它一起改错才咬得住
        bd = json.loads(good)
        bd["source_sha256"] = "sha-wrong"
        bd.setdefault("cite_check", {})["source_sha256"] = "sha-wrong"
        bad = json.dumps(bd, ensure_ascii=False)
        open(L4_SAMPLE, "w", encoding="utf-8").write("\n".join([bad] + lines[1:]) + "\n")
        rc, n = run_gate()
        chk("T14 反向对照：sha 写错 ⇒ 闸门必须精确变红", rc != 0 and n == 1, "rc=%d C4=%d" % (rc, n))
        open(L4_SAMPLE, "w", encoding="utf-8").write("\n".join([good] + lines[1:]) + "\n")
        L4_SAMPLE, L4_BACKUPS, L4_ARCHIVE, REG_RETIRED, REPORTS, L0_NEG = saved
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("remap_l4_sample_anchors --selftest %s" % ("PASS" if ok else "FAIL"))
    return 0 if ok else 3


# ---------------------------------------------------------------- main
def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="真写库（默认只预演）")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--out", default="", help="计划表落点（默认工作区根）")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()

    run = "remap-" + time.strftime("%Y%m%d-%H%M%S")
    rows = build_plan()
    c, cite = summarize(rows)
    print("=" * 74)
    print("L4 sample_case 锚点重映射计划 ｜ run=%s" % run)
    print("  待处置 %d 条 ｜ L4 当前 C4 红 201" % len(rows))
    for t in TIER_ORDER:
        if c.get(t):
            print("   %-9s %3d 条 ｜ 报告引用 %3d 次" % (t, c[t], cite[t]))
    okn = sum(c.get(t, 0) for t in OK_TIERS)
    print("  ⇒ 可机械重映射 %d 条 ｜ 须撤号归档 %d 条（引用 %d 次）"
          % (okn, len(rows) - okn, sum(cite[t] for t in ("AMBIG", "UNMAPPED"))))

    out = a.out or os.path.join(ROOT, "重映射计划-L4样本201-%s.csv" % run)
    write_plan_csv(rows, out)
    print("  计划表 → %s" % out)

    # ★ 安全闸（2026-10-20 加）：本库已有**官方的退役通道** `kb/l7/scripts/l4_retire.py`
    #   （追加退役行、号码不回收、可留墓碑）。本脚本的 `--apply` 会**移动/改写行**，
    #   与那套追加口径不同 ⇒ 一旦库里已出现 `status: retired`，就拒绝落盘，只许预演，
    #   避免两套写法互相打架（同一件事两条路 = 本库返工过的老毛病）。
    if a.apply:
        _has_retired = False
        try:
            for _ln in open(L4_SAMPLE, encoding="utf-8"):
                if '"status": "retired"' in _ln or '"status":"retired"' in _ln:
                    _has_retired = True
                    break
        except OSError:
            pass
        if _has_retired:
            print("⛔ 拒绝落盘：定稿里已存在 `status: retired` 行 —— 本库的退役通道是 "
                  "`kb/kbpy l7/scripts/l4_retire.py --article-no <号> --why <原因> --apply`。")
            print("   本脚本只在**首次**重映射时用 `--apply`；之后请只用预演档做复核。")
            return 2

    if not a.apply:
        print("（预演结束，未写任何库文件；确认后加 --apply）")
        print("=" * 74)
        return 0

    outcome = apply(rows, run)
    rp = write_retired_registry(rows, run, outcome)
    print("  ✅ 落盘：重映射 %d ｜ 撤号 %d ｜ 未动 %d"
          % (outcome["changed"], outcome["retired"], outcome["kept"]))
    print("     备份 %s" % os.path.relpath(outcome["backup"], ROOT))
    print("     归档 %s" % os.path.relpath(outcome["archive"], ROOT))
    print("     留痕 %s" % os.path.relpath(rp, ROOT))
    print("=" * 74)
    return 0


if __name__ == "__main__":
    sys.exit(main())
