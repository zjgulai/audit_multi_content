#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""L3 治理字段的**唯一派生实现**：owner / effective_from / half_life_days / valid_until。

════════════════════════════════════════════════════════════════════════════
为什么要有这个模块（「真源统一」这条任务的落地件）
════════════════════════════════════════════════════════════════════════════

`kb/l3/candidates/rules.jsonl` 是**评审链读得最多**的那个文件。它的四个治理字段
此前**三处各写一份**，而且互不一致：

  ① `kb/.work/fix_f7_backfill.py`（回填脚本）
     能算出正确值，但只在**人工跑时**生效 —— 跑完就没人管了。
  ② `kb/l8/l3_distill_run.py`（日更的 L3 蒸馏器）
     把 `owner=""` / `effective_from=""` **写死成空串**（5 处），
     且**根本不产** `half_life_days` / `valid_until`。
     ⇒ **①的回填成果会在下一次日更被原样写回空。**
  ③ `kb/.work/gen-host-library.py`（派生视图生成器）
     源为空时回落常量（`OWNER=法务` / `DERIVED_HALF_LIFE_DAYS=180`）。

2026-10-10 实测：文件里 `owner` / `effective_from` 键存在但 **1018 行全空**、
`half_life_days` / `valid_until` **键都不存在**；而 `kb/l3/registry/l3.json`
的 `changes[]` 至今还记着「已回填 509 行」——**声明与实文件不一致**。
`kb/l7/registry/failure-playbook.yaml::finding.l3_governance_backfill_lost` 记的就是这条。

本模块把「政策 → 逐条值」这段派生**收成一份**，两个调用方都 import 它：
    · `kb/l8/l3_distill_run.py` —— 写盘前对每行派生（**这才是根治**：日更自己就会产）
    · `kb/.work/fix_f7_backfill.py` —— 一次性回填（历史欠账）

════════════════════════════════════════════════════════════════════════════
诚实的边界（别把这些值当事实读）
════════════════════════════════════════════════════════════════════════════

· `half_life_days` 本质是**政策值**，不是从数据推出来的 —— 权威库与 L0 里没有日期字段。
· `effective_from` 只能给**策略基线日**，不是条文原始生效日（源侧没有该信息）。
· `owner` 只到**角色位**，不写死人名。且大多数规则没有 `rule_code` ⇒ 无法按域路由，
  只能落「法务」。真正的解法是补 `rule_code`（源侧动作）。
· **`valid_until` 不随重生成归零** —— 用固定的 `effective_from` 算，条目才会真的到期；
  若按「重生成当天」算，等于永远不过期，那是另一种假绿。

政策真源 = `kb/l3/registry/half-life-policy.json`。**改政策改那份 JSON**（三档天数、
基线日），本模块读它；本模块里的常量只是**离线兜底**，读不到政策文件时会记进
`policy_fallbacks`（不静默），`--selftest` 会核两者是否一致。

用法：
    python3 kb/kb_governance.py --selftest      # 自证（不碰任何库内文件）
    python3 kb/kb_governance.py --probe         # 只读：打印当前 rules.jsonl 的派生分布
"""

from __future__ import annotations

import collections
import datetime as dt
import json
import os
import sys

KB = os.path.dirname(os.path.abspath(__file__))
RULES_DEFAULT = os.path.join(KB, "l3", "candidates", "rules.jsonl")
POLICY_DEFAULT = os.path.join(KB, "l3", "registry", "half-life-policy.json")

# ── 离线兜底（政策文件读不到时用；用了会记进 policy_fallbacks，不静默）──────────
FALLBACK_BASELINE = "2026-09-29"
FALLBACK_TIERS = {"A": 365, "B": 90, "C": 180}

# ── 判据（谓词留在代码里：政策文件目前用散文写它们，机器读不了）────────────────
#    档 B 的来源表：具体文案样本 / 批次性品线反馈
TIER_B_SOURCES = {"广告文案明细", "W1卖点表达边界（品线反馈0910）"}
#    owner 角色位：按 rule_code 的域分组
ROLE_MED = {"H01", "H02", "H03", "H07", "U04"}                    # 医疗功效 / 疼痛承诺
ROLE_PLAT = {"M01", "M03", "M04", "M05", "M06", "M07", "U02"}     # 平台与促销
ROLE_END = {"H04", "H05", "H06", "H08", "H09", "M02", "U01", "U03"}  # 背书 / 资质 / 安全
OWNER_MED = "法务 + 医学顾问"
OWNER_PLAT = "法务 + 渠道负责人"
OWNER_END = "法务 + 产品负责人"
OWNER_DEFAULT = "法务"

#: 本模块负责的四个字段（调用方据此做差集比对）
GOVERNANCE_FIELDS = ("owner", "effective_from", "half_life_days", "valid_until")


def load_policy(path: str | None = None) -> dict:
    """读政策文件里的**数值**。读不到/读不全 ⇒ 用兜底并留痕。

    返回：{"baseline_date": str, "tiers": {"A":int,"B":int,"C":int}, "fallbacks": [str,...],
           "policy_id": str|None, "path": str}
    谓词（哪张来源表算 B、哪个 rule_code 归哪个角色位）**不从这里读** —— 政策文件
    把它们写成散文（`condition` / `why`），不是机器可读结构；改谓词要改本模块的常量。
    """
    p = path or POLICY_DEFAULT
    out = {"baseline_date": FALLBACK_BASELINE, "tiers": dict(FALLBACK_TIERS),
           "fallbacks": [], "policy_id": None, "path": p}
    try:
        d = json.loads(open(p, encoding="utf-8").read())
    except Exception as e:                                          # noqa: BLE001
        out["fallbacks"].append("读不到政策文件 %s：%s ⇒ 用内置兜底值" % (p, e))
        return out
    out["policy_id"] = d.get("policy_id")
    bd = ((d.get("validation") or {}).get("baseline_date") or "").strip()
    if bd:
        out["baseline_date"] = bd
    else:
        out["fallbacks"].append("政策文件无 validation.baseline_date ⇒ 用兜底 %s" % FALLBACK_BASELINE)
    tiers = {}
    for k, v in (d.get("half_life_tiers") or {}).items():
        n = (v or {}).get("half_life_days") if isinstance(v, dict) else None
        if isinstance(n, int) and n > 0:
            tiers[k] = n
        else:
            out["fallbacks"].append("政策文件档 %s 无有效 half_life_days ⇒ 用兜底" % k)
    for k, n in FALLBACK_TIERS.items():
        tiers.setdefault(k, n)
    out["tiers"] = tiers
    return out


def tier_of(row: dict) -> tuple[str, str]:
    """返回 (档, 理由)。顺序 A > B > C：P0 的红线属性比来源域更重要。"""
    if row.get("p_level") == "P0":
        return "A", "p_level=P0 法务红线，依据法规与监管口径，按年复核"
    src = (row.get("authority_source_table") or "").strip()
    if src in TIER_B_SOURCES:
        return "B", "来源表「%s」为具体文案样本/批次性品线反馈，随投放与品线口径迭代" % src
    return "C", "其余措辞规则，取中位保守值"


def owner_of(row: dict) -> str:
    """按 rule_code 的域给角色位；无 rule_code ⇒ 法务兜底。"""
    code = (row.get("rule_code") or "").strip()
    if code in ROLE_MED:
        return OWNER_MED
    if code in ROLE_PLAT:
        return OWNER_PLAT
    if code in ROLE_END:
        return OWNER_END
    return OWNER_DEFAULT


def derive(row: dict, policy: dict | None = None) -> dict:
    """对**一行**算出四个治理字段。纯函数，不改 row。"""
    pol = policy or load_policy()
    tier, reason = tier_of(row)
    hl = pol["tiers"][tier]
    ef = pol["baseline_date"]
    vu = (dt.date.fromisoformat(ef) + dt.timedelta(days=hl)).isoformat()
    return {"owner": owner_of(row), "effective_from": ef,
            "half_life_days": hl, "valid_until": vu, "tier": tier, "tier_reason": reason}


def apply_governance(rows: list, policy: dict | None = None, mode: str = "force") -> dict:
    """就地为 rows 填四个字段。

    mode="force"      —— 一律按政策重算（**日更蒸馏器用这个**：p_level 会变，
                         继承旧值就是刻舟求剑）
    mode="fill_empty" —— 只填空的；已有非空值且**与派生值不同**时**拒绝覆盖**并记进
                         `conflicts`（**回填脚本用这个**：它不是权威写方，不许改已有的值）

    返回统计：{"rows","filled","kept","conflicts":[...],"tiers":Counter,"owners":Counter,
               "policy_fallbacks":[...]}
    """
    if mode not in ("force", "fill_empty"):
        raise ValueError("mode 只能是 force / fill_empty，收到 %r" % mode)
    pol = policy or load_policy()
    st = {"rows": len(rows), "filled": 0, "kept": 0, "conflicts": [],
          "tiers": collections.Counter(), "owners": collections.Counter(),
          "policy_fallbacks": list(pol.get("fallbacks") or [])}
    for r in rows:
        d = derive(r, pol)
        st["tiers"][d["tier"]] += 1
        st["owners"][d["owner"]] += 1
        if mode == "fill_empty":
            for k in GOVERNANCE_FIELDS:
                cur = r.get(k)
                if cur not in (None, ""):
                    if cur != d[k]:
                        st["conflicts"].append({"rule_id": r.get("rule_id"), "field": k,
                                                "current": cur, "derived": d[k]})
                    st["kept"] += 1
                    continue
                r[k] = d[k]
                st["filled"] += 1
        else:
            for k in GOVERNANCE_FIELDS:
                r[k] = d[k]
            st["filled"] += 1
    return st


def summarize(st: dict) -> str:
    t = st["tiers"]
    lines = ["── half_life 分布：A(P0/%s)=%d  B(%s)=%d  C(%s)=%d"
             % (FALLBACK_TIERS["A"], t.get("A", 0), FALLBACK_TIERS["B"], t.get("B", 0),
                FALLBACK_TIERS["C"], t.get("C", 0)),
             "── owner 分布："]
    for k, v in st["owners"].most_common():
        lines.append("     %4d  %s" % (v, k))
    if st["policy_fallbacks"]:
        lines.append("⚠ 政策读取兜底 %d 条：%s" % (len(st["policy_fallbacks"]), st["policy_fallbacks"]))
    if st["conflicts"]:
        lines.append("⚠ 拒绝覆盖 %d 处（已有值 ≠ 派生值，交人判）：" % len(st["conflicts"]))
        for c in st["conflicts"][:10]:
            lines.append("     %s.%s 当前=%r 派生=%r" % (c["rule_id"], c["field"], c["current"], c["derived"]))
    return "\n".join(lines)


def _load_rows(path: str) -> list:
    return [json.loads(l) for l in open(path, encoding="utf-8").read().split("\n") if l.strip()]


def _selftest() -> int:
    """自证（不碰任何库内文件）。"""
    ok = fail = 0

    def chk(name, cond, extra=""):
        nonlocal ok, fail
        if cond:
            ok += 1
            print("  ✅ %s" % name)
        else:
            fail += 1
            print("  ❌ %s %s" % (name, extra))

    print("① 政策读取")
    pol = load_policy()
    chk("读到政策文件（无兜底）", not pol["fallbacks"], pol["fallbacks"])
    chk("baseline_date 非空", bool(pol["baseline_date"]), pol["baseline_date"])
    chk("三档天数齐全且为正", all(isinstance(pol["tiers"].get(k), int) and pol["tiers"][k] > 0
                                  for k in ("A", "B", "C")), pol["tiers"])

    print("\n② 政策文件读不到时是否留痕（不许静默兜底）")
    p2 = load_policy("/tmp/不存在的政策文件.json")
    chk("缺文件 ⇒ 记 fallback", len(p2["fallbacks"]) == 1, p2["fallbacks"])
    chk("缺文件 ⇒ 仍有可用兜底值", p2["baseline_date"] == FALLBACK_BASELINE
        and p2["tiers"] == FALLBACK_TIERS, p2)

    print("\n③ 三档判据（A 优先于 B）")
    a = derive({"p_level": "P0", "rule_code": "H05", "authority_source_table": "广告文案明细"}, pol)
    chk("P0 且来源属 B ⇒ 判 A（A 优先于 B）", a["tier"] == "A", a)
    chk("A 档 half_life=365", a["half_life_days"] == pol["tiers"]["A"], a)
    b = derive({"p_level": "P1", "rule_code": "M01", "authority_source_table": "广告文案明细"}, pol)
    chk("非 P0 且来源属 B ⇒ 判 B", b["tier"] == "B", b)
    chk("B 档 half_life=90", b["half_life_days"] == pol["tiers"]["B"], b)
    c = derive({"p_level": "P1", "rule_code": "", "authority_source_table": ""}, pol)
    chk("其余 ⇒ 判 C", c["tier"] == "C", c)
    chk("C 档 half_life=180", c["half_life_days"] == pol["tiers"]["C"], c)

    print("\n④ valid_until = effective_from + half_life_days（且不随重生成归零）")
    for r in (a, b, c):
        want = (dt.date.fromisoformat(r["effective_from"]) + dt.timedelta(days=r["half_life_days"])).isoformat()
        chk("档 %s 的 valid_until 算式" % r["tier"], r["valid_until"] == want, r)
    chk("effective_from 恒为政策基线日（不是今天）", a["effective_from"] == pol["baseline_date"], a)
    chk("同一行算两次结果相同（不依赖调用时间）", derive({}, pol) == derive({}, pol))

    print("\n⑤ owner 角色位路由")
    chk("H01 ⇒ 医学", owner_of({"rule_code": "H01"}) == OWNER_MED)
    chk("M03 ⇒ 渠道", owner_of({"rule_code": "M03"}) == OWNER_PLAT)
    chk("H05 ⇒ 产品", owner_of({"rule_code": "H05"}) == OWNER_END)
    chk("无 rule_code ⇒ 法务兜底", owner_of({"rule_code": ""}) == OWNER_DEFAULT)
    chk("未知 rule_code ⇒ 法务兜底", owner_of({"rule_code": "ZZ9"}) == OWNER_DEFAULT)

    print("\n⑥ 两种模式的行为差")
    rows = [{"rule_id": "r1", "p_level": "P1", "rule_code": "M01"}, {"rule_id": "r2", "p_level": "P0"}]
    s1 = apply_governance(rows, pol, mode="force")
    chk("force：两行都被填", s1["filled"] == 2 and all(r.get("owner") for r in rows), s1)
    rows2 = [{"rule_id": "r1", "p_level": "P1", "rule_code": "M01", "owner": "人手改的值"}]
    s2 = apply_governance(rows2, pol, mode="fill_empty")
    chk("fill_empty：不覆盖已有的非空值", rows2[0]["owner"] == "人手改的值", rows2)
    chk("fill_empty：冲突被记下来（不静默）", len(s2["conflicts"]) == 1, s2["conflicts"])
    chk("fill_empty：同值不算冲突", apply_governance(
        [{"rule_id": "x", "p_level": "P1", "owner": OWNER_DEFAULT}], pol, mode="fill_empty"
    )["conflicts"] == [])
    try:
        apply_governance([], pol, mode="乱写")
        chk("非法 mode 报错", False)
    except ValueError:
        chk("非法 mode 报错", True)

    print("\n⑦ 本模块与政策文件的谓词是否仍对得上（防两处漂移）")
    try:
        raw = json.loads(open(POLICY_DEFAULT, encoding="utf-8").read())
        cond_b = ((raw.get("half_life_tiers") or {}).get("B") or {}).get("condition") or ""
        chk("政策 B 档 condition 里点到的来源表都在 TIER_B_SOURCES 里",
            all(s in cond_b for s in TIER_B_SOURCES), cond_b)
        roles = raw.get("owner_roles") or {}
        chk("政策 owner_roles 里点到的角色位都还在用",
            all(k in roles for k in (OWNER_MED, OWNER_PLAT, OWNER_END, OWNER_DEFAULT)),
            sorted(roles.keys()))
    except Exception as e:                                          # noqa: BLE001
        chk("读政策文件做交叉核对", False, str(e))

    print("\n" + "=" * 66)
    print("自证：%d 过 / %d 失败" % (ok, fail))
    return 0 if fail == 0 else 1


def _probe() -> int:
    """只读：打印当前 rules.jsonl 的派生分布，不改盘。"""
    rows = _load_rows(RULES_DEFAULT)
    pol = load_policy()
    st = apply_governance([dict(r) for r in rows], pol, mode="fill_empty")
    print("rules.jsonl：%d 行（只读探针，未落盘）" % st["rows"])
    print(summarize(st))
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    if "--probe" in sys.argv:
        raise SystemExit(_probe())
    print(__doc__)
    print("用法：--selftest（自证） / --probe（只读探针）")
    raise SystemExit(0)
