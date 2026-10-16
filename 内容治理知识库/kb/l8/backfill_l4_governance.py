#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""批次18 · 第2块（D）：治理字段三分档补齐 —— **政策层是唯一真源**。

## 补什么（批次18 实测缺口，按件分组）

    wording_entry            56 行  缺 baseline_date / never_resets_on_regeneration
    wording_revision_pair   453 行  缺 baseline_date / never_resets_on_regeneration
    sample_case             358 行  缺 half_life_days / baseline_date / valid_until / never_resets_on_regeneration
    scoped_clause           375 行  同上
    clause                  123 行  同上（该件还缺 authority/rule_kind/p_level_basis/
                                     authority_source_table/risk_evidence_records —— 那 5 个
                                     属「继承」范畴，本次**不在此处补**，另行处置）

## 口径（四条，写死）

1. **档位从政策文件读**（`kb/l3/registry/half-life-policy.json` 的 `half_life_tiers`），
   **不许在本脚本里另写一份档位表**。判档条件也读政策里的 `condition` 文本 —— 本次按
   `decide()` 的同源逻辑实现（A: p_level=P0 ／ B: authority_source_table ∈ TierB ／ C: 其余）。
2. **`baseline_date` 与 `effective_from` 的关系（用户点名要写清）**：
   政策文件 `fields_backfilled` 原文：`effective_from` 是「**原有字段、原为空串**，
   本次填入**策略基线日**」；且 `validation.baseline_date = "2026-09-29"`、
   `BASELINE = "2026-09-29"`（`fix_f7_backfill.py:58`）。
   ⇒ **`baseline_date` 就是 `effective_from` 的同一个值**，不是第三个日期口径。
   本次对 `effective_from` 为空的件（`sample_case`/`scoped_clause`/`clause`）：
   **两者都写 `2026-09-29`**；对已有 `effective_from` 的件：`baseline_date` 取该行
   **自己的** `effective_from`（若有值），否则取策略基线日。
3. **`valid_until = baseline_date + half_life_days`**（用户裁定的算式）。
   政策文件写的是 `= effective_from + half_life_days` —— 因上式关系，**两者等价**。
   ★ 用**固定基线**而非「重生成当天」，正是政策 `why_not_created_at_today` 要防的
   「每次重生成把时钟归零 ⇒ 永远不过期」那种假绿。
4. **`never_resets_on_regeneration = true`**：对**三档一律为 true**。
   理由即政策 `validation.never_resets_on_regeneration: true` —— 重生成不得重置时钟。

用法：`python3 kb/l8/backfill_l4_governance.py [--apply]`（不带则预演）
"""
import argparse
import datetime
import hashlib
import json
import os
import sys

WS = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
os.chdir(WS)

POLICY = "kb/l3/registry/half-life-policy.json"
CANON = "kb/l4/canonical"
# 形态文件（rules.jsonl 是 0 字节迁移留痕，**不计形态、不补**）
FORMS = [("wording_entry", "rule_id"), ("wording_revision_pair", "rule_id"),
         ("sample_case", "case_id"), ("scoped_clause", "clause_id"),
         ("clause", "rule_id")]


def load_policy():
    d = json.load(open(POLICY, encoding="utf-8"))
    tiers = d["half_life_tiers"]
    days = {k: int(v["half_life_days"]) for k, v in tiers.items()}
    if not days:
        raise SystemExit("❌ 政策文件 half_life_tiers 为空 —— 拒绝凭空造档位")
    return d, days


def tier_of(row, days, tier_b_sources):
    """判档 —— 与政策 condition 同源（此处按 fix_f7_backfill.decide() 的既有逻辑实现）。"""
    if row.get("p_level") == "P0":
        return "A", days["A"], "p_level=P0 法务红线"
    if (row.get("authority_source_table") or "") in tier_b_sources:
        return "B", days["B"], f"来源表「{row['authority_source_table']}」为样本/批次性反馈"
    return "C", days["C"], "其余措辞规则，中位保守值"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    pol, days = load_policy()
    baseline = pol["validation"]["baseline_date"]
    print(f"政策层：{POLICY}")
    print(f"  policy_id = {pol.get('policy_id')}")
    print(f"  档位天数  = {days}（**从政策文件读，脚本内不另写档位表**）")
    print(f"  baseline_date = {baseline}")

    # TierB 来源表：从政策 condition 文本解析（保持单一真源）
    import re
    cond_b = pol["half_life_tiers"]["B"].get("condition", "")
    tier_b_sources = set(re.findall(r"'([^']+)'", cond_b))
    print(f"  TierB 来源表（解析自政策 condition）= {sorted(tier_b_sources)}")
    print()

    report, changed_files = {}, []
    for name, idk in FORMS:
        p = f"{CANON}/{name}.jsonl"
        if not os.path.exists(p):
            continue
        rows = [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]
        before_sha = hashlib.sha256(open(p, "rb").read()).hexdigest()
        tier_dist = {}
        filled = 0
        out = []
        for r in rows:
            r = dict(r)
            t, hl, why = tier_of(r, days, tier_b_sources)
            tier_dist[t] = tier_dist.get(t, 0) + 1
            # baseline_date：优先本行 effective_from（有值），否则策略基线日
            ef = str(r.get("effective_from") or "").strip()
            bd = ef or baseline
            r["half_life_days"] = hl
            r["baseline_date"] = bd
            d0 = datetime.date.fromisoformat(bd)
            r["valid_until"] = (d0 + datetime.timedelta(days=hl)).isoformat()
            r["never_resets_on_regeneration"] = True
            # effective_from 原为空串的件：一并填入策略基线日（与政策 fields_backfilled 一致）
            if not ef:
                r["effective_from"] = baseline
            filled += 1
            out.append(r)
        # 写出：与 fix_l4_repromote.save() 同形（sort_keys，逐行 JSON）
        txt = "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in out)
        after_sha = hashlib.sha256(txt.encode()).hexdigest()
        report[name] = {"rows": len(rows), "tier_dist": tier_dist,
                        "sha_before": before_sha[:16], "sha_after": after_sha[:16],
                        "changed": before_sha != after_sha}
        if a.apply and before_sha != after_sha:
            tmp = p + ".tmp"
            open(tmp, "w", encoding="utf-8").write(txt)
            for l in open(tmp, encoding="utf-8"):
                json.loads(l)          # 落盘前逐行校验
            os.replace(tmp, p)
            changed_files.append(name)
        print(f"  {name:<24} {len(rows):>4} 行 ｜ 档位 {tier_dist} ｜ "
              f"{'**已写**' if (a.apply and before_sha != after_sha) else ('未变' if before_sha == after_sha else '待写')}")

    print()
    if a.apply:
        print(f"已写：{'、'.join(changed_files) if changed_files else '（无变化）'}")
    else:
        print("[预演] 未落盘。加 --apply 才写。")
    json.dump(report, open("kb/l4/runs/20261002-governance-backfill.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
