#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""l4_promote_negative_rules.py —— 把 L3 的负面样本规则（N-1.x）定稿进 L4（与 L3 逐字一致）。

口径（照 L4 既有形态与闸门 C1–C6）
──────────────────────────────────
  · 只做 **promotion**：`rule_text` / `action` / `evidence_units` / `image_refs` 原样搬运，
    一个字不改（L4 闸门 C5「定稿不改写」逐字比对）；
  · 条款号沿用 L3 的 **N-1.x**（Owner 2026-10-20 批准的新段；不并入 W/S/E 编号体系，
    L4 注册表里单独登记成 `negative_rule` 形态，见 `kb/l4/registry/l4.json` 的 canonical.files）；
  · 状态 `stable`，`promoted_from=provisional`，带 `promoted_at_run` 与 `promotion_basis`。

用法：kb/kbpy l8/l4_promote_negative_rules.py [RUN] [--apply]
"""
import hashlib
import json
import os
import sys
import time

APPLY = "--apply" in sys.argv
if APPLY:
    sys.argv.remove("--apply")
RUN = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else time.strftime("%Y%m%d-%H%M")

SRC = "kb/l3/candidates/negative_rules.jsonl"
DST = "kb/l4/canonical/negative_rule.jsonl"


def sha_of(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def main():
    if not os.path.exists(SRC):
        print("缺 L3 候选：%s" % SRC)
        return 2
    rows = []
    skipped = 0
    for line in open(SRC, encoding="utf-8"):
        if not line.strip():
            continue
        r = json.loads(line)
        # ★ 2026-10-20（Owner 决定）：`non_substantive`（只有「麻烦看看呀」这类客套话）**不进 L4 定稿**。
        #   理由：L4 是依据池/定稿层，客套话没有判定价值、会污染依据；它们**仍留在 L3**（可审计、「一条不丢」）。
        if r.get("rule_kind") == "non_substantive":
            skipped += 1
            continue
        rows.append({
            "article_no": r["article_no"],
            "rule_id": r["rule_id"],
            "form": "negative_sample_rule",
            "kb_type": r.get("kb_type", "internal_sample"),
            "kb_version": r.get("kb_version", "v0"),
            "rule_code": r.get("rule_code"),
            "rule_kind": r.get("rule_kind"),
            "confidence": r.get("confidence"),
            "rule_text": r["rule_text"],
            "action": r.get("action"),
            "applicable_scope": r.get("applicable_scope"),
            "evidence_units": r.get("evidence_units") or [],
            "image_refs": r.get("image_refs") or [],
            "record_ids": r.get("record_ids") or [],
            "source_table": r.get("source_table"),
            "polarity": r.get("polarity"),
            "status": "stable",
            "promoted_from": "provisional",
            "promoted_at_run": RUN,
            "promotion_basis": "L3 候选 → L4 定稿：正文逐字搬运，未改写（L4 闸门 C5）",
            "observed_at": RUN,
            "owner": r.get("owner") or "刘华丽",
        })
    art = [x["article_no"] for x in rows]
    dup = [a for a in set(art) if art.count(a) > 1]
    print("L3 候选 → 剔除 non_substantive %d 条 → 待定稿 %d 条 ｜ 条款号重复 %d"
          % (skipped, len(rows), len(dup)))
    if dup:
        print("❌ 条款号重复：%s" % dup[:5])
        return 3
    if not APPLY:
        print("[dry-run] 将写 %s（%d 行）；加 --apply 才落盘" % (DST, len(rows)))
        return 0
    os.makedirs(os.path.dirname(DST), exist_ok=True)
    tmp = DST + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
    os.replace(tmp, DST)
    reg_p = "kb/l4/registry/l4.json"
    reg = json.load(open(reg_p, encoding="utf-8"))
    files = reg.setdefault("canonical", {}).setdefault("files", {})
    files["negative_rule"] = {
        "path": DST, "lines": len(rows), "bytes": os.path.getsize(DST), "sha256": sha_of(DST),
        "source_rows": len(rows), "source": SRC, "duplicate_source_rows": 0,
        "source_rows_actual": len(rows), "form": "negative_sample_rule",
        "segment": "N-1.x（Owner 2026-10-20 批准的新条款号段，独立于 W/S/E 体系）",
        "promoted_at_run": RUN,
    }
    tmp2 = reg_p + ".tmp"
    with open(tmp2, "w", encoding="utf-8") as fh:
        json.dump(reg, fh, ensure_ascii=False, indent=1)
    os.replace(tmp2, reg_p)
    print("已定稿：%s（%d 行 / %d bytes）；注册表已登记 negative_rule" % (DST, len(rows), os.path.getsize(DST)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
