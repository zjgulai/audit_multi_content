#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""失效锚点重映射（L3 候选 + L4 定稿）—— 默认**干跑**，`--apply` 才落盘。

## 治的是什么
飞书「负面样本」表重建后记录 ID 换代；L4 定稿 201 条 `sample_case` 的
`anchor`（`#正面和负面样本/<旧rec>/原文反馈`）指向已不存在的记录，
对应 L2 单元已于 2026-10-20T16:17:26 被 `prune-20261020-161725` 退役
⇒ `l4_gate` C4 红 201 ⇒ 评审链停在 L4（`layer_gate_red`，exit=4）⇒ 守衡报
「引擎 JSON 不新鲜 ⇒ 拒收」。

## 怎么改（只动**坐标字段**，不碰正文字段）
按 `_remap-gone-anchors-dryrun.py` 的配对结果，把命中行改成新坐标：

    anchor            → `#负面样本/<新rec>/<新字段>`
    source_sha256     → 目标 L2 单元的 `source_sha256`（闸门 C4 逐字比这一个）
    unit_id/unit_ids  → 目标单元的 `unit_id`
    resource_id       → `bitable__tbld8qE92YaY38Yz__<新rec>`
    cite_check        → {anchor, source_sha256, unit_ids, evidence_units:1,
                         anchors_in_l2:1, unresolvable:[]}（仅 L4 有）

**一个字不动**：`sample_body` / `article_no` / `case_id` / `status` / `polarity` /
`media_refs`（实测 201 条全为 `[]`）/ 其余治理字段 —— 所以 C1（号码唯一）、
C5（定稿与候选逐字相同）不受影响。

## 纪律
· 默认干跑；`--apply` 前**自动备份**（`*.bak-pre-remap-<ts>`），写**原子**（临时文件 + os.replace）；
· 每行改动落账 `kb/.work/remap-gone-anchors-<ts>.ndjson`（旧坐标 → 新坐标，逐条）；
· 写完**逐条回读**并与期望值比对，不一致就报错退出（非零）；
· 幂等：已改过的行（anchor 已是新值）不会被再改。

用法：
    python3 _remap-gone-anchors-apply.py                 # 干跑，打差异样例
    python3 _remap-gone-anchors-apply.py --apply         # 落盘
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import tempfile
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
KB = os.path.join(ROOT, "kb")
L3_CAND = os.path.join(KB, "l3/candidates/sample_cases.jsonl")
L4_CANON = os.path.join(KB, "l4/canonical/sample_case.jsonl")
WORK = os.path.join(KB, ".work")


def _load_matcher():
    """复用干跑脚本里的配对判据（单一真源，别在这里抄第二份）。"""
    p = os.path.join(ROOT, "_remap-gone-anchors-dryrun.py")
    spec = importlib.util.spec_from_file_location("_remap_dryrun", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def build_mapping(mod):
    """旧 anchor → {new_anchor, new_sha, new_unit_id, new_rec, tier, score}。

    并列时的取舍规则（Owner 授权）：**重合最高 → 记录 id 字典序最小**。
    规则化而不是随机，且落账可复核。
    """
    old = mod.load_old()
    new = mod.load_new()
    new_by_anchor = {n["new_anchor"]: n for n in new}

    hard_index = {}
    for n in new:
        h = mod.norm_hard(n["text"])
        if h:
            hard_index.setdefault(h, []).append(n)
    for n in new:
        n["_sh"] = mod.shingles(mod.norm_hard(n["text"]))
        n["_soft"] = mod.norm_soft(n["text"])

    mapping, retired = {}, []
    for o in old:
        oh, osf = mod.norm_hard(o["text"]), mod.norm_soft(o["text"])
        cands = []
        for n in hard_index.get(oh, []):
            cands.append((100, "A 逐字", n["new_anchor"]))
        if not cands and oh:
            for score, tier, n, cov in mod.best_for(new, oh, osf, mod.shingles(oh)):
                cands.append((score, tier, n["new_anchor"]))
        if not cands:
            retired.append((o["article_no"], o["old_anchor"]))
            continue
        top_score = max(c[0] for c in cands)
        top = [c for c in cands if c[0] == top_score]
        top.sort(key=lambda c: new_by_anchor[c[2]]["new_rec"])      # 记录 id 升序
        score, tier, anchor = top[0]
        n = new_by_anchor[anchor]
        mapping[o["old_anchor"]] = {
            "article_no": o["article_no"], "tier": tier, "score": score,
            "new_anchor": n["new_anchor"], "new_sha": n["new_sha"],
            "new_unit_id": n["new_unit_id"], "new_rec": n["new_rec"],
            "ties": len(top),
        }
    return mapping, retired


def rewrite(path, mapping, ts, apply_, ledger):
    """就地改坐标字段。返回 (命中行数, 改动条数)。"""
    if not os.path.exists(path):
        return 0, 0
    lines = open(path, encoding="utf-8").read().splitlines()
    hit = changed = 0
    out = []
    for line in lines:
        if not line.strip():
            out.append(line)
            continue
        d = json.loads(line)
        anc = d.get("anchor") or ""
        m = mapping.get(anc)
        if not m:
            out.append(line)                                     # 逐字节保留
            continue
        hit += 1
        before = json.dumps({k: d.get(k) for k in
                             ("anchor", "source_sha256", "unit_id", "resource_id")},
                            ensure_ascii=False)
        d["anchor"] = m["new_anchor"]
        d["source_sha256"] = m["new_sha"]
        d["unit_id"] = m["new_unit_id"]
        d["unit_ids"] = [m["new_unit_id"]]
        d["resource_id"] = "bitable__tbld8qE92YaY38Yz__" + m["new_rec"]
        cc = d.get("cite_check")
        if isinstance(cc, dict):
            cc["anchor"] = m["new_anchor"]
            cc["source_sha256"] = m["new_sha"]
            cc["unit_ids"] = [m["new_unit_id"]]
            cc["evidence_units"] = 1
            cc["anchors_in_l2"] = 1
            cc["unresolvable"] = []
            d["cite_check"] = cc
        changed += 1
        ledger.append({"file": os.path.basename(path), "article_no": d.get("article_no"),
                       "tier": m["tier"], "ties": m["ties"],
                       "before": json.loads(before),
                       "after": {"anchor": d["anchor"], "source_sha256": d["source_sha256"],
                                 "unit_id": d["unit_id"], "resource_id": d["resource_id"]}})
        out.append(json.dumps(d, ensure_ascii=False))
    if apply_ and changed:
        shutil.copy2(path, path + ".bak-pre-remap-" + ts)
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".remap-")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write("\n".join(out) + "\n")
        os.replace(tmp, path)                                    # 原子
    return hit, changed


def verify(path, mapping):
    """回读核对：改过的行必须 anchor/sha/unit_id 全部等于期望值。"""
    bad = []
    n = 0
    for line in open(path, encoding="utf-8"):
        if not line.strip():
            continue
        d = json.loads(line)
        anc = d.get("anchor") or ""
        for m in mapping.values():
            # L3 候选里同一 case 有两行（一行 article_no 为 null 的编号前行），按 anchor 认，article_no 缺失时也认
            if anc == m["new_anchor"] and d.get("article_no") in (m["article_no"], None):
                n += 1
                if d.get("source_sha256") != m["new_sha"] or d.get("unit_id") != m["new_unit_id"]:
                    bad.append((d.get("article_no"), "sha/unit_id 不符"))
                cc = d.get("cite_check")
                if isinstance(cc, dict) and (cc.get("anchor") != anc
                                             or cc.get("source_sha256") != m["new_sha"]):
                    bad.append((d.get("article_no"), "cite_check 不符"))
    return n, bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    ts = time.strftime("%Y%m%d-%H%M%S")
    mod = _load_matcher()
    mapping, retired = build_mapping(mod)

    print("配对：可重指 %d 条 ｜ 无对应（交 l4_retire 退役）%d 条" % (len(mapping), len(retired)))
    from collections import Counter
    print("  档位：", dict(Counter(m["tier"].split()[0] for m in mapping.values())))
    print("  并列（≥2 候选并列）：%d 条（按「重合最高→记录 id 升序」收敛，已落账）"
          % sum(1 for m in mapping.values() if m["ties"] > 1))

    ledgers = []
    for path in (L3_CAND, L4_CANON):
        led = []
        hit, ch = rewrite(path, mapping, ts, a.apply, led)
        print("%-46s 命中 %3d 行 ｜ 改动 %3d 行" % (os.path.basename(path), hit, ch))
        ledgers.append((path, led))
        for row in led[:2]:
            print("   e.g. %s：%s → %s" % (row["article_no"], row["before"]["anchor"], row["after"]["anchor"]))

    if a.apply:
        os.makedirs(WORK, exist_ok=True)
        lp = os.path.join(WORK, "remap-gone-anchors-%s.ndjson" % ts)
        with open(lp, "w", encoding="utf-8") as fh:
            for _, led in ledgers:
                for row in led:
                    fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            for art, anc in retired:
                fh.write(json.dumps({"file": "-", "article_no": art, "action": "retire_pending",
                                     "before": {"anchor": anc}}, ensure_ascii=False) + "\n")
        print("\n账本：%s（%d 行）" % (os.path.relpath(lp, ROOT), sum(len(l) for _, l in ledgers) + len(retired)))
        for path, _ in ledgers:
            n, bad = verify(path, mapping)
            print("回读 %-30s 核对 %d 行 ｜ 不符 %d" % (os.path.basename(path), n, len(bad)))
            for b in bad[:3]:
                print("   ❌", b)
            if bad:
                return 3
        print("\n退役清单（%d 条，交 kb/l7/scripts/l4_retire.py）：" % len(retired))
        for art, _ in retired:
            print("  " + art)
    else:
        print("\n（干跑，未写任何文件。加 --apply 落盘）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
