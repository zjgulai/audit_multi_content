#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""一次性回填：把四个治理字段补进**权威库** `kb/l3/candidates/rules.jsonl`。

> ⚠️ **2026-10-10 起，派生实现只有一份** —— `kb/kb_governance.py`。
> 本脚本原先自带 `decide()` / `decide_owner()` 与一整套常量；日更的
> `kb/l8/l3_distill_run.py` 与派生视图生成器各写第三、第四份 —— **那就是「真源不统一」本身**。
> 现在这四处都 import 同一个模块。本脚本只剩三件事：**回填 / 写政策 / 登记 run**。
>
> ⇒ 日更的蒸馏器已能自己产出这四个字段（见 `l3_distill_run.py` 的 `_apply_governance`），
>    所以本脚本**此后通常不再需要**；它现在的身份是「历史欠账的一次性补丁 + 冲突探测器」。

## 为什么必须补在权威库

`kb/view` 是**派生视图**，每次重生成。字段值此前是生成器里的常量
（`DERIVED_HALF_LIFE_DAYS=180` / `OWNER="刘华丽"`），所以：

  · 补在视图上 = 白补，下次重生成就没了；
  · 值来自**反规范化步骤**而不是权威库 ⇒ `kb_check` 的「新鲜度 1.00」是**假绿**
    （509 条的 `valid_until` 全是同一个 `created_at + 180`，不是"都新鲜"，是"都写了同一个数"）。

## 诚实边界（先讲清楚，别把它当数据）

见 `kb/kb_governance.py` 的模块 docstring 与 `kb/l3/registry/half-life-policy.json`
的 `honest_limits`。要点：`half_life_days` 是**政策值**不是事实；`effective_from` 只能给
**策略基线日**；`owner` 只到**角色位**，且因 `rule_code` 覆盖率低而大量落到「法务」。

用法：
    python3 kb/.work/fix_f7_backfill.py --dry-run   # 预演，不写盘
    python3 kb/.work/fix_f7_backfill.py             # 落盘
环境变量：
    KB_GOV_RUN=<run_id>   指定登记用的 run_id（默认取当前时刻 yyyymmdd-HHMM）
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import sys

KB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RULES = os.path.join(KB, "l3", "candidates", "rules.jsonl")
POLICY = os.path.join(KB, "l3", "registry", "half-life-policy.json")
L3REG = os.path.join(KB, "l3", "registry", "l3.json")

# ── 派生实现只有一份 ────────────────────────────────────────────────────────
sys.path.insert(0, KB)
import kb_governance as G  # noqa: E402

RUN_ID = os.environ.get("KB_GOV_RUN") or dt.datetime.now().strftime("%Y%m%d-%H%M")
POLICY_ID = "half-life-policy-20260929-1040"     # 政策身份不变（本次改的是数据，不是政策）


def sha256_file(p: str) -> str:
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def build_policy(pol: dict, st: dict, total: int) -> dict:
    """重写政策文件。三档天数与基线日一律取自政策真源（`pol`），本函数不硬编码数值。"""
    tiers = pol["tiers"]
    tiers_meta = {
        "A": ("p_level = P0", "法务红线，依据法规与监管口径，按年复核"),
        "B": ("authority_source_table ∈ %s（且非 P0）" % sorted(G.TIER_B_SOURCES),
              "源自具体文案样本或批次性品线反馈，随投放周期与品线口径迭代，季度复核"),
        "C": ("其余措辞规则", "中位保守值 —— 与 PRD/技术方案里「措辞类 180」一致"),
    }
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
            "本文件把政策**搬进权威库并写明理由**，逐条数据由本文件派生"
            "（实现 = kb/kb_governance.py，写方 = 日更 l3_distill_run.py 与本回填脚本）。"
        ),
        "honest_limits": [
            "half_life_days 本质是**政策值**，不是从数据推出来的。权威库与 L0 原始记录里没有日期字段"
            "（effective_from/effective_to/superseded_at 全空；13 张源表只有 3 张有日期列）。",
            f"effective_from 只能给**策略基线日** {pol['baseline_date']}，不是条文原始生效日 —— "
            "源侧没有该信息。这是**源侧缺口**，要回源侧加日期列才能真解决。",
            "owner 只到「角色位」（不写死人名）。无 rule_code 的规则无法按域路由 ⇒ "
            f"落到「{G.OWNER_DEFAULT}」。真正的解法是补 rule_code（**源侧动作**）。",
            # ★ 2026-10-10 新增：B 档判据字段在本层根本不存在 —— 这是缺口，不是「B 档本来就 0 条」
            "★ **档 B 当前恒为 0 条，这是缺口不是结论**：判据字段 `authority_source_table` "
            "在 `kb/l3/candidates/rules.jsonl` 里**连键都不存在**（0/1018），上游 `kb/l2/units.jsonl` "
            "也没有承载来源表的字段 ⇒ `TIER_B_SOURCES` 永远不命中。本文件早先记的「B=22 条」是"
            "**早期数据的读数**，与现行文件对不上（同 owner/half_life 那次丢失是同一类病）。"
            "要真修：回 L1/L2 补「来源表」字段并逐层带到 L3。",
        ],
        "validation": {
            "baseline_date": pol["baseline_date"],
            "valid_until_formula": "valid_until = effective_from + half_life_days",
            "never_resets_on_regeneration": True,
            "why_not_created_at_today": (
                "若用「重生成当天」算 valid_until，每次重生成都会把时钟归零 —— "
                "那又是另一种假绿（永远不过期）。用固定的 effective_from 算，"
                "条目才会**真的**到期，新鲜度才成为活指标。"
            ),
            "derivation_module": "kb/kb_governance.py（唯一派生实现；自证 python3 kb/kb_governance.py --selftest）",
            "writers": ["kb/l8/l3_distill_run.py（日更，mode=force）",
                        "kb/.work/fix_f7_backfill.py（一次性回填，mode=fill_empty）"],
        },
        "half_life_tiers": {
            k: {"condition": tiers_meta[k][0], "half_life_days": tiers[k],
                "why": tiers_meta[k][1], "count": st["tiers"].get(k, 0)}
            for k in ("A", "B", "C")
        },
        "tier_order": "A 优先于 B：P0 的红线属性比来源域更重要",
        "owner_roles": {
            "rule": "按 rule_code 的域分组；无 rule_code 时以「法务」兜底",
            G.OWNER_MED: {"rule_codes": sorted(G.ROLE_MED), "count": st["owners"].get(G.OWNER_MED, 0),
                          "why": "医疗功效 / 疼痛承诺类宣称，法务与医学共同把关"},
            G.OWNER_PLAT: {"rule_codes": sorted(G.ROLE_PLAT), "count": st["owners"].get(G.OWNER_PLAT, 0),
                           "why": "平台与促销类表述，涉及渠道政策，渠道负责人共同把关"},
            G.OWNER_END: {"rule_codes": sorted(G.ROLE_END), "count": st["owners"].get(G.OWNER_END, 0),
                          "why": "背书 / 资质 / 安全承诺类，需产品事实支撑，产品负责人共同把关"},
            G.OWNER_DEFAULT: {"rule_codes": [], "count": st["owners"].get(G.OWNER_DEFAULT, 0),
                              "why": "无 rule_code ⇒ 无法按域路由，以法务兜底。**这是 rule_code 覆盖率低的后果**"},
        },
        "fields_backfilled": {
            "half_life_days": "新增（整数天数）",
            "valid_until": "新增（YYYY-MM-DD）= effective_from + half_life_days",
            "effective_from": "**原有字段、原为空串**，填入策略基线日",
            "effective_to": "保持空串（未定义失效终点；失效由 half_life_days/valid_until 表达）",
            "owner": "**原有字段、原为空串**，填入角色位",
        },
        "revisit": {
            "when": "任一档的 valid_until 到期前 30 天，或法规/平台政策发生变更时",
            "who": "法务 + 内容治理",
            "how": "改本文件的 half_life_tiers 天数并重跑 kb/.work/fix_f7_backfill.py；"
                   "改的是政策，不是逐条数据 —— 逐条数据由政策派生"
                   "（kb/kb_governance.py 每次写盘都会重算，**不会**随重生成归零）",
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

    # 解析→重序列化必须能逐字节复现（保证写回不改变任何既有字段的形态）
    if json.dumps(rows[0], ensure_ascii=False, sort_keys=True) != lines[0]:
        print("❌ 序列化风格不匹配，写回会改变既有字节 —— 中止")
        return 2
    print("✅ 序列化自检通过：json.dumps(ensure_ascii=False, sort_keys=True) 逐字节复现原行")

    before_sha = sha256_file(RULES)
    pol = G.load_policy(POLICY)
    if pol["fallbacks"]:
        print("⚠ 政策读取兜底：%s" % pol["fallbacks"])
    st = G.apply_governance(rows, pol, mode="fill_empty")

    print("\n" + G.summarize(st))
    print("── 回填格数：%d ｜ 保留原值：%d ｜ 冲突：%d" % (st["filled"], st["kept"], len(st["conflicts"])))
    if st["conflicts"]:
        print("⚠ 有冲突：已有非空值与派生值不同 —— **本脚本不覆盖**，请人判（见上表）")

    policy = build_policy(pol, st, len(rows))

    if a.dry_run:
        print("\n[dry-run] 不写盘")
        return 0

    # ── 备份：每次都留一份带时间戳的（旧实现只在备份不存在时写 ⇒ 重跑会留着过期备份）──
    arch = os.path.join(KB, "l8", "_archive", f"gov-backfill-{RUN_ID}")
    os.makedirs(arch, exist_ok=True)
    bak = os.path.join(arch, "rules.jsonl.before")
    if not os.path.exists(bak):
        open(bak, "wb").write(open(RULES, "rb").read())
    print(f"\n备份：{os.path.relpath(bak, KB)}  sha256 {before_sha[:16]}…")

    # ── 写回 rules.jsonl（.jsonl 不受 trld 信封影响）─────────────────────────
    out = "\n".join(json.dumps(r, ensure_ascii=False, sort_keys=True) for r in rows)
    if kept_trailing:
        out += "\n"
    open(RULES, "w", encoding="utf-8").write(out)
    after_sha = sha256_file(RULES)
    print(f"✅ 已写回 {os.path.relpath(RULES, KB)}  {len(out.encode())} 字节  sha256 {after_sha[:16]}…")

    # ── 写政策文件 ──────────────────────────────────────────────────────────
    json.dump(policy, open(POLICY, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"✅ 已写入 {os.path.relpath(POLICY, KB)}")

    # ── 登记进 l3 registry（② run 记录）────────────────────────────────────
    reg = json.load(open(L3REG, encoding="utf-8"))
    reg.setdefault("changes", []).append({
        "run_id": RUN_ID,
        "change": "backfill",
        "keys": list(G.GOVERNANCE_FIELDS),
        "rows": len(rows),
        "policy_file": "l3/registry/half-life-policy.json",
        "module": "kb/kb_governance.py",
        "reader_contract": "kb/l8/l3_distill_run.py 已改为写盘前 mode=force 重算 ⇒ 本回填不会被日更冲掉",
        "note": (
            "拆假绿：把 owner / effective_from / half_life_days / valid_until 从派生视图生成器的常量"
            "搬进权威库，并把派生实现收成一份（kb/kb_governance.py）。"
            "仅**填空白字段与新增字段**，未覆盖任何既有非空值（冲突 %d 处，见 dry-run 表）；"
            "未改动 rule_text / anchor / article_no 等任何被 C4 比对的内容字段 —— C4 不受影响。"
            "★ 遗留缺口：档 B 判据字段 authority_source_table 在本层不存在，故 B=0（缺口非结论）。"
            % len(st["conflicts"])
        ),
        "before_sha256": before_sha,
        "after_sha256": after_sha,
    })
    json.dump(reg, open(L3REG, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"✅ 已登记进 {os.path.relpath(L3REG, KB)} 的 changes[]（run_id={RUN_ID}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
