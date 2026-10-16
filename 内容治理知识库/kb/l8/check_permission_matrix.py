#!/usr/bin/env python3
"""权限矩阵核验（任务拆解 目标 16 · PRD §13 / §9）。

## 查什么（四条，都是「不查就会悄悄错」的）

| # | 判据 | 不查会怎样 |
|---|---|---|
| **P1** | PRD §13 的六类角色**一个不落**地出现在矩阵里 | 漏一类 = 那一类人没人管，而矩阵看起来是完整的 |
| **P2** | 矩阵里授予写的每一列**都真实存在于结论表** | 授予写一个不存在的列 = 矩阵在说谎，且永远发现不了 |
| **P3** | **机器列不许被任何人工角色写**（除 sign-off 的状态/发布时间，见 r2） | 人工写了机器列 ⇒ 下一轮机器覆盖掉，人白填（或反之，机器读数被人手改） |
| **P4** | **管理面三个角色位在结论表上零写权限**（§13 没给它们这条） | 给多了权限 = 越权，而没人会发现 |

## 三条纪律

1. **只读**：只读 `kb/l7/registry/permission-matrix.yaml` 与 `routing-policy.json`。**不碰飞书**。
2. **不编**：`routing_policy_key=null` 是**已声明的缺口**（照实留空），**不算** P2 的失败；
   但**谎报一个 key** 要算。
3. **反向对照**：`--selftest` 把上面四条**各造一遍缺陷**，尺子必须精确变红。

## 用法

    python3 kb/l8/check_permission_matrix.py             # 核（红 ⇒ 退出码 3）
    python3 kb/l8/check_permission_matrix.py --selftest  # 反向对照
"""

from __future__ import annotations

import argparse
import json
import os
import sys

KB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MATRIX = os.path.join(KB, "l7", "registry", "permission-matrix.yaml")
ROUTING = os.path.join(KB, "l7", "review-engine", "knowledge-base", "routing-policy.json")

#: PRD §13 的六类角色（**逐字拆成角色位** —— 原文「法务 / 医学 / 专家 / 北美」是一格四角色）。
PRD13_ROLE_CELLS = [
    "内容提交方", "法务", "医学", "专家", "北美",
    "Sign-off 负责人", "项目统筹", "IT / Agent 维护", "管理员",
]

#: 机器列：由引擎/发布件写，**人工角色不该授予写**。
MACHINE_FIELDS = ["内容 ID", "写入时间", "Agent 结论", "问题数量",
                  "置信度", "问题分类汇总", "报告链接"]

#: 管理面角色位：§13 给它们的职责不含「改结论」。
MANAGEMENT_ROLES = ["项目统筹", "IT / Agent 维护", "管理员"]

#: sign-off 允许写的人列（见矩阵 r2）
SIGNOFF_ALLOWED_WRITE = {"sign-off 人", "发布时间", "状态"}


def _load_yaml(p):
    try:
        import yaml
    except ImportError:
        print("需要 pyyaml", file=sys.stderr)
        raise SystemExit(2)
    with open(p, encoding="utf-8") as f:
        return yaml.safe_load(f)


def check(matrix=None, routing=None) -> tuple[list[str], dict]:
    """返回 (问题列表, 统计)。问题为空 = 过。"""
    m = matrix if matrix is not None else _load_yaml(MATRIX)
    r = routing if routing is not None else (
        json.load(open(ROUTING, encoding="utf-8")) if os.path.exists(ROUTING) else {})
    roles = m.get("roles") or {}
    fields = set((m.get("conclusion_table") or {}).get("fields_measured_20261010") or [])
    routing_keys = set((r.get("roles") or {}).keys())
    problems = []

    # ── P1 覆盖：PRD §13 六类角色一个不落 ──────────────────────────────
    # ★ 口径：**按矩阵自己声明的 `prd_role_cells` 映射判**，不靠名字撞上。
    #   为什么（2026-10-10 实测）：PRD §13 写「**医学**」「**北美**」，而本库
    #   `routing-policy.json` 的收敛名是「**医学顾问**」「**北美同事**」——
    #   靠名字比对会把这两个**真实存在**的角色位判成「缺」。别名关系必须**显式声明**。
    covered = set()
    for name, spec in roles.items():
        cells = spec.get("prd_role_cells") or []
        if not cells:
            problems.append("P1 %s 没声明 prd_role_cells（无法核它对应 PRD §13 哪一格）" % name)
        for c in cells:
            if c not in PRD13_ROLE_CELLS:
                problems.append("P1 %s 声明的 prd_role_cells=%r 不在 PRD §13 里（自创角色格）"
                                % (name, c))
            covered.add(c)
    for cell in PRD13_ROLE_CELLS:
        if cell not in covered:
            problems.append("P1 缺角色位：%s（PRD §13 有、矩阵没有任何角色声明覆盖它）" % cell)

    # ── P2 授予写的列必须真实存在 ─────────────────────────────────────
    for name, spec in roles.items():
        for f in (spec.get("write") or []):
            if fields and f not in fields:
                problems.append("P2 %s 被授予写一个不存在的列：%r" % (name, f))
        # P2b：`routing_policy_key` 非空就必须真在那个表里（**谎报 key 要抓**）
        k = spec.get("routing_policy_key")
        if k and routing_keys and k not in routing_keys:
            problems.append("P2b %s 的 routing_policy_key=%r 在 routing-policy 里不存在（谎报）"
                            % (name, k))

    # ── P3 机器列不许被人工角色写 ────────────────────────────────────
    for name, spec in roles.items():
        w = set(spec.get("write") or [])
        bad = w & set(MACHINE_FIELDS)
        if name == "Sign-off 负责人":
            bad = bad - SIGNOFF_ALLOWED_WRITE
        if bad:
            problems.append("P3 %s 被授予写机器列：%s" % (name, sorted(bad)))

    # ── P4 管理面零写权限 ───────────────────────────────────────────
    for name in MANAGEMENT_ROLES:
        w = (roles.get(name) or {}).get("write")
        if w:
            problems.append("P4 管理面角色 %s 被授予写 %s（§13 没给这条）" % (name, w))

    stats = {
        "n_roles": len(roles),
        "prd_role_cells": len(PRD13_ROLE_CELLS),
        "conclusion_fields": len(fields),
        "routing_keys": len(routing_keys),
        "roles_without_routing_key": sorted(n for n, s in roles.items()
                                            if not s.get("routing_policy_key")),
        "roles_with_write": sorted(n for n, s in roles.items() if s.get("write")),
    }
    return problems, stats


# ══════════════════════════════════════════════════════════════════
# 反向对照（把缺陷真造一遍）
# ══════════════════════════════════════════════════════════════════

def _selftest() -> int:
    ok = fail = 0
    fails: list[str] = []

    def ck(name, cond, detail=""):
        nonlocal ok, fail
        if cond:
            ok += 1
        else:
            fail += 1
            fails.append("%s %s" % (name, detail))

    import copy
    real = _load_yaml(MATRIX)
    routing = json.load(open(ROUTING, encoding="utf-8"))

    # 基座：真件必须过
    probs, stats = check(real, routing)
    ck("①真件过", not probs, probs)
    ck("①b 角色数≥9", stats["n_roles"] >= 9, stats["n_roles"])

    # ② P1 反向：删掉「专家」⇒ 必须红
    m = copy.deepcopy(real); m["roles"].pop("专家", None)
    p, _ = check(m, routing)
    ck("②P1 缺角色位变红", any("P1 缺角色位：专家" in x for x in p), p[:3])

    # ③ P2 反向：给内容提交方授予写一个不存在的列 ⇒ 必须红
    m = copy.deepcopy(real); m["roles"]["内容提交方"]["write"].append("并不存在的列")
    p, _ = check(m, routing)
    ck("③P2 假列变红", any("P2 内容提交方" in x and "并不存在的列" in x for x in p), p[:3])

    # ④ P2b 反向：谎报一个 routing_policy_key ⇒ 必须红
    #   ★ 2026-10-12 改：原先拿 "expert" 当假 key —— 而 `expert` **当天真的补进了** `routing-policy`
    #     （#16 专家角色位，Owner 指示）⇒ 那个变异**不再是「谎报」**，断言射不出来（自证当场 7/8 红）。
    #     ⇒ 教训：**反向对照的变异值不许借用真实角色名**，否则真实件一演进，对照就失效。
    #     改用**真不存在**的 key，并加一条**正例**钉住「真 key 必须通过」。
    m = copy.deepcopy(real); m["roles"]["专家"]["routing_policy_key"] = "no_such_role_xyz"
    p, _ = check(m, routing)
    ck("④P2b 谎报 key 变红",
       any("P2b 专家" in x and "no_such_role_xyz" in x for x in p), p[:3])

    # ④b 正例：真实的 `expert` key 必须**不**红（补角色位是合法状态，别把它当缺陷）
    p2, _ = check(copy.deepcopy(real), routing)
    ck("④b 真 key `expert` 不红（补位是合法状态）",
       not any("P2b 专家" in x for x in p2), p2[:3])

    # ⑤ P3 反向：让人工角色写机器列 ⇒ 必须红
    m = copy.deepcopy(real); m["roles"]["法务"]["write"].append("Agent 结论")
    p, _ = check(m, routing)
    ck("⑤P3 写机器列变红", any("P3 法务" in x and "Agent 结论" in x for x in p), p[:3])

    # ⑥ P4 反向：给管理面加写权限 ⇒ 必须红
    m = copy.deepcopy(real); m["roles"]["项目统筹"]["write"] = ["复核结论"]
    p, _ = check(m, routing)
    ck("⑥P4 管理面越权变红", any("P4 管理面角色 项目统筹" in x for x in p), p[:3])

    # ⑦ ★ sign-off 是**有意的例外**：它写 `状态/发布时间/sign-off 人` 不该被判红
    m = copy.deepcopy(real)
    m["roles"]["Sign-off 负责人"]["write"] = ["sign-off 人", "发布时间", "状态"]
    p, _ = check(m, routing)
    ck("⑦sign-off 例外不误伤", not [x for x in p if "Sign-off" in x], p[:3])

    print("check_permission_matrix --selftest：%d/%d" % (ok, ok + fail))
    for f in fails:
        print("  ✗", f)
    return 0 if fail == 0 else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="权限矩阵核验（PRD §13 / §9）")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return _selftest()

    probs, stats = check()
    print("权限矩阵核验（只读；不碰飞书）")
    print("-" * 66)
    print("  角色位：%d ｜ PRD §13 角色格：%d ｜ 结论表字段：%d ｜ routing 角色位：%d"
          % (stats["n_roles"], stats["prd_role_cells"],
             stats["conclusion_fields"], stats["routing_keys"]))
    print("  ★ 无 routing 对应的角色位（**已声明的缺口**）：%s"
          % (", ".join(stats["roles_without_routing_key"]) or "无"))
    print("  可写结论表的角色位：%s" % (", ".join(stats["roles_with_write"]) or "无"))
    print("-" * 66)
    if probs:
        for x in probs:
            print("  ✗ %s" % x)
        print("结论：❌ 不过（%d 条）" % len(probs))
        return 3
    print("结论：✅ 过（P1 覆盖 / P2 列真实 / P2b key 真实 / P3 机器列 / P4 管理面零写）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
