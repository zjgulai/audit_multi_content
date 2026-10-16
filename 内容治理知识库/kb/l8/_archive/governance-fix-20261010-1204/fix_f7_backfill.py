#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""修复计划 F7 · 把三处假绿（half_life_days / valid_until / owner）补进**权威库**。

## 为什么必须补在权威库

`kb/view` 是**派生视图**，由 `gen-host-library.py` 每次重新生成。此前这三个字段的值
是生成器里的常量（`DERIVED_HALF_LIFE_DAYS = 180` / `OWNER = "刘华丽"`），所以：

  · 补在视图上 = 白补，下次重生成就没了；
  · 值来自**反规范化步骤**而不是权威库 ⇒ `kb_check` 的「新鲜度 1.00」是**假绿**
    （509 条的 `valid_until` 全是同一个 `created_at + 180`，不是"都新鲜"，是"都写了同一个数"）。

## 诚实边界（先讲清楚，别把它当数据）

1. **`half_life_days` 本质是政策值，不是事实。** 权威库与 L0 原始记录里**没有任何日期字段**
   （`effective_from`/`effective_to`/`superseded_at` 全空；13 张源表里只有 3 张有日期列，
   且只覆盖 **15/509** 条规则）。所以它只能由**有理由的政策**给出，不假装是从数据推出来的。
2. **`effective_from` 只能给「策略基线日」**，不是条文原始生效日 —— 源侧没有这个信息。
   这是本库的**源侧缺口**，要回源侧加日期列才能真解决。
3. **`owner` 只能给到「角色位」**（D4 已确认）。且 472/509 条规则没有 `rule_code`，
   无法按域路由 ⇒ 93% 只能落到「法务」。**真正的解法是补 `rule_code`**（见 F3 报告的发现）。

## 三档半衰期（轴：风险等级 + 来源域）

| 档 | 条件 | 值 | 理由 |
|---|---|---|---|
| A | `p_level = P0` | **365** | 法务红线，依据法规与监管口径，按年复核 |
| B | 来源是具体文案样本 / 批次性品线反馈 | **90** | 随投放周期与品线口径迭代，季度复核 |
| C | 其余措辞规则 | **180** | 中位保守值 |

顺序：A 优先于 B（P0 的红线属性比来源域更重要）。

## 四个 owner 角色位

按 `rule_code` 的域分组；无 `rule_code` 时以「法务」兜底。

用法：python3 kb/.work/fix_f7_backfill.py [--dry-run]
"""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import hashlib
import json
import os
import sys

KB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RULES = os.path.join(KB, "l3", "candidates", "rules.jsonl")
POLICY = os.path.join(KB, "l3", "registry", "half-life-policy.json")
L3REG = os.path.join(KB, "l3", "registry", "l3.json")

RUN_ID = "20260929-1040"
POLICY_ID = "half-life-policy-20260929-1040"
BASELINE = "2026-09-29"          # 策略基线日（非条文原始生效日 —— 源侧无该信息）

# 档 B 的来源表：具体文案样本 / 批次性品线反馈
TIER_B_SOURCES = {"广告文案明细", "W1卖点表达边界（品线反馈0910）"}

# owner 角色位：按规则码的域分组
ROLE_MED = {"H01", "H02", "H03", "H07", "U04"}            # 医疗功效 / 疼痛承诺
ROLE_PLAT = {"M01", "M03", "M04", "M05", "M06", "M07", "U02"}  # 平台与促销
ROLE_END = {"H04", "H05", "H06", "H08", "H09", "M02", "U01", "U03"}  # 背书 / 资质 / 安全承诺
OWNER_MED = "法务 + 医学顾问"
OWNER_PLAT = "法务 + 渠道负责人"
OWNER_END = "法务 + 产品负责人"
OWNER_DEFAULT = "法务"


def sha256_file(p: str) -> str:
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def decide(row: dict) -> tuple[int, str, str]:
    """返回 (half_life_days, tier, reason)"""
    if row.get("p_level") == "P0":
        return 365, "A", "p_level=P0 法务红线，依据法规与监管口径，按年复核"
    if (row.get("authority_source_table") or "") in TIER_B_SOURCES:
        return 90, "B", f"来源表「{row['authority_source_table']}」为具体文案样本/批次性品线反馈，随投放与品线口径迭代"
    return 180, "C", "其余措辞规则，取中位保守值"


def decide_owner(row: dict) -> str:
    code = row.get("rule_code") or ""
    if code in ROLE_MED:
        return OWNER_MED
    if code in ROLE_PLAT:
        return OWNER_PLAT
    if code in ROLE_END:
        return OWNER_END
    return OWNER_DEFAULT


def build_policy(dist: dict, owner_dist: dict, total: int) -> dict:
    return {
        "policy_id": POLICY_ID,
        "created_at": RUN_ID,
        "layer": "L3 蒸馏层 · 治理元数据",
        "status": "active",
        "owner": "法务 + 内容治理（角色位）",
        "scope": f"l3/candidates/rules.jsonl 全部 {total} 条规则",
        "why_this_file": (
            "half_life_days / valid_until / owner 此前是**派生视图生成器里的常量**"
            "（DERIVED_HALF_LIFE_DAYS=180、OWNER=刘华丽）。常量写在反规范化步骤里有两个后果："
            "① 补在视图上会随重生成丢失；② kb_check 的「新鲜度 1.00」是假绿 —— "
            "509 条 valid_until 全是同一个 created_at+180，不是「都新鲜」，是「都写了同一个数」。"
            "本文件把政策**搬进权威库并写明理由**，视图改为从库读。"
        ),
        "honest_limits": [
            "half_life_days 本质是**政策值**，不是从数据推出来的。权威库与 L0 原始记录里没有日期字段"
            "（effective_from/effective_to/superseded_at 全空；13 张源表只有 3 张有日期列，"
            "只覆盖 15/509 条规则）。",
            f"effective_from 只能给**策略基线日** {BASELINE}，不是条文原始生效日 —— 源侧没有该信息。"
            "这是**源侧缺口**，要回源侧加日期列才能真解决。",
            "owner 只到「角色位」（不写死人名）。且 472/509 条规则没有 rule_code，无法按域路由 ⇒ "
            f"93% 落到「{OWNER_DEFAULT}」。真正的解法是补 rule_code。",
        ],
        "validation": {
            "baseline_date": BASELINE,
            "valid_until_formula": "valid_until = effective_from + half_life_days",
            "never_resets_on_regeneration": True,
            "why_not_created_at_today": (
                "若用「重生成当天」算 valid_until，每次重生成都会把时钟归零 —— "
                "那又是另一种假绿（永远不过期）。用固定的 effective_from 算，"
                "条目才会**真的**到期，新鲜度才成为活指标。"
            ),
        },
        "half_life_tiers": {
            "A": {
                "condition": "p_level = P0",
                "half_life_days": 365,
                "why": "法务红线，依据法规与监管口径，按年复核",
                "count": dist.get("A", 0),
            },
            "B": {
                "condition": f"authority_source_table ∈ {sorted(TIER_B_SOURCES)}（且非 P0）",
                "half_life_days": 90,
                "why": "源自具体文案样本或批次性品线反馈，随投放周期与品线口径迭代，季度复核",
                "count": dist.get("B", 0),
            },
            "C": {
                "condition": "其余措辞规则",
                "half_life_days": 180,
                "why": "中位保守值 —— 与 PRD/技术方案里「措辞类 180」一致",
                "count": dist.get("C", 0),
            },
        },
        "tier_order": "A 优先于 B：P0 的红线属性比来源域更重要",
        "owner_roles": {
            "rule": "按 rule_code 的域分组；无 rule_code 时以「法务」兜底",
            OWNER_MED: {"rule_codes": sorted(ROLE_MED), "count": owner_dist.get(OWNER_MED, 0),
                        "why": "医疗功效 / 疼痛承诺类宣称，法务与医学共同把关"},
            OWNER_PLAT: {"rule_codes": sorted(ROLE_PLAT), "count": owner_dist.get(OWNER_PLAT, 0),
                         "why": "平台与促销类表述，涉及渠道政策，渠道负责人共同把关"},
            OWNER_END: {"rule_codes": sorted(ROLE_END), "count": owner_dist.get(OWNER_END, 0),
                        "why": "背书 / 资质 / 安全承诺类，需产品事实支撑，产品负责人共同把关"},
            OWNER_DEFAULT: {"rule_codes": [], "count": owner_dist.get(OWNER_DEFAULT, 0),
                            "why": f"无 rule_code ⇒ 无法按域路由，以法务兜底。**这是 rule_code 填充率仅 37/509 的后果**"},
        },
        "fields_backfilled": {
            "half_life_days": "新增（整数天数）",
            "valid_until": "新增（YYYY-MM-DD）= effective_from + half_life_days",
            "effective_from": "**原有字段、原为空串**，本次填入策略基线日",
            "effective_to": "保持空串（未定义失效终点；失效由 half_life_days/valid_until 表达）",
            "owner": "**原有字段、原为空串**，本次填入角色位",
        },
        "revisit": {
            "when": "任一档的 valid_until 到期前 30 天，或法规/平台政策发生变更时",
            "who": "法务 + 内容治理",
            "how": "改本文件的 half_life_days 并重跑 kb/.work/fix_f7_backfill.py；"
                   "改的是政策，不是逐条数据 —— 逐条数据由政策派生",
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    raw = open(RULES, encoding="utf-8").read().split("\n")
    kept_trailing = raw[-1] == ""
    lines = [l for l in raw if l.strip()]
    rows = [json.loads(l) for l in lines]
    print(f"rules.jsonl：{len(rows)} 行（全部为规则）")

    # 期望：解析→重序列化必须能逐字节复现（保证下面写回不改变任何既有字段的形态）
    probe = json.dumps(rows[0], ensure_ascii=False, sort_keys=True)
    if probe != lines[0]:
        print("❌ 序列化风格不匹配，写回会改变既有字节 —— 中止")
        return 2
    print("✅ 序列化自检通过：json.dumps(ensure_ascii=False, sort_keys=True) 逐字节复现原行")

    before_sha = sha256_file(RULES)
    dist = collections.Counter()
    owner_dist = collections.Counter()
    changes = 0
    for r in rows:
        hl, tier, _ = decide(r)
        dist[tier] += 1
        ow = decide_owner(r)
        owner_dist[ow] += 1
        vu = (dt.date.fromisoformat(BASELINE) + dt.timedelta(days=hl)).isoformat()
        # 只填空的 / 只加新的 —— 不覆盖任何已有非空值
        assert r.get("owner") in (None, ""), f"owner 非空，拒绝覆盖：{r.get('rule_id')}"
        assert r.get("effective_from") in (None, ""), f"effective_from 非空，拒绝覆盖：{r.get('rule_id')}"
        r["half_life_days"] = hl
        r["effective_from"] = BASELINE
        r["valid_until"] = vu
        r["owner"] = ow
        changes += 1

    print(f"\n── half_life 分布：A(P0/365)={dist['A']}  B(90)={dist['B']}  C(180)={dist['C']}")
    print(f"── owner 分布：")
    for k, v in owner_dist.most_common():
        print(f"     {v:4}  {k}")
    vus = collections.Counter((dt.date.fromisoformat(BASELINE) + dt.timedelta(days=decide(r)[0])).isoformat() for r in rows)
    print(f"── valid_until 取值（{len(vus)} 种）：" + "  ".join(f"{k}={v}" for k, v in sorted(vus.items())))
    print(f"── 回填行数：{changes}")

    policy = build_policy(dist, owner_dist, len(rows))

    if a.dry_run:
        print("\n[dry-run] 不写盘")
        return 0

    # ── 备份 ──────────────────────────────────────────────────────────────
    arch = os.path.join(KB, "l8", "_archive", "fix-20260929-094703")
    os.makedirs(arch, exist_ok=True)
    bak = os.path.join(arch, "rules.jsonl.before-F7")
    if not os.path.exists(bak):
        open(bak, "wb").write(open(RULES, "rb").read())
    print(f"\n备份：{os.path.relpath(bak, KB)}  sha256 {before_sha[:16]}…")

    # ── 写回 rules.jsonl（.jsonl 不受 trld 信封影响，python 写安全）─────────
    out = "\n".join(json.dumps(r, ensure_ascii=False, sort_keys=True) for r in rows)
    if kept_trailing:
        out += "\n"
    open(RULES, "w", encoding="utf-8").write(out)
    print(f"✅ 已写回 {os.path.relpath(RULES, KB)}  {len(out.encode())} 字节")

    # ── 写政策文件 ────────────────────────────────────────────────────────
    json.dump(policy, open(POLICY, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"✅ 已写入 {os.path.relpath(POLICY, KB)}")

    # ── 登记进 l3 registry ────────────────────────────────────────────────
    reg = json.load(open(L3REG, encoding="utf-8"))
    reg.setdefault("changes", []).append({
        "run_id": RUN_ID,
        "change": "backfill",
        "keys": ["half_life_days", "valid_until", "effective_from", "owner"],
        "rows": changes,
        "policy_file": "l3/registry/half-life-policy.json",
        "note": (
            "F7 拆假绿：把 half_life_days / valid_until / owner 从派生视图生成器的常量"
            "搬进权威库。仅**填空白字段与新增字段**，未覆盖任何既有非空值；"
            "未改动 rule_text / anchor / article_no 等任何被 C4 比对的内容字段 —— C4 不受影响。"
            f"写前 sha256 {before_sha[:16]}…"
        ),
    })
    json.dump(reg, open(L3REG, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"✅ 已登记进 {os.path.relpath(L3REG, KB)} 的 changes[]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
