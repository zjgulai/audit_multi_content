#!/usr/bin/env python3
"""判据：**同一条内容不许拿到两个条款号**（发号幂等 —— 真判据版）。

## 为什么要它（2026-10-14 实测）

`l4_promote.py` 的 `promotion_basis` 里写着 **「C8 发号幂等（不新增号码）」**，
但 C8 的实现只核一件事：

    if cid not in world["assigned"]:
        bad.append("C8")     # 「该候选没有号（发号幂等要求号已在台账里）」

—— 它核的是「**这条候选在台账里有没有号**」，**从来没核过「同一内容会不会拿到第二个号」**。
⇒ 那是一句**名不副实的判据**：源表整体重建（record_id 换代）之后，同一条反例被当成新记录
重新蒸馏、**重新发号**，C8 一路绿灯。

实测代价：`S-1.159` 与 `S-1.296` 是**同一条反例**（`reason_analysis` 逐字相同、原件同为
「【9.21】社群9月Melissa直播海报*4张」），却各有一个条款号 —— 同一素材不同时间审出不同号，
**溯源直接对不上**。

## 判据

按**内容指纹**（不是 record_id、不是 anchor —— 那些正是换代会变的东西）分组：
  · `sample_case`  → `reason_analysis`，为空回落到 `sample_body`
  · `scoped_clause` → `clause_text`
指纹去空白、去图片/HTML 标记；**长度 < 10 字不参与**（空字段会把一堆条目塌成一组 —— 踩过）。

组内 >1 个条款号 ⇒ 重复。重复组**必须二选一**：
  · 要么已声明在 `kb/l7/registry/l4-known-duplicates.yaml`（已知、待人裁）
  · 要么组内已做 supersede 标记（`status=superseded` + `superseded_by`，且对侧有 `supersedes`）
两者都没有 ⇒ **红，退出码 3**。

## 边界（照实说）

  · 只覆盖**已知内容键**的两个形态（`sample_case` / `scoped_clause`）；
    其余形态（`entry`/`revision_pair`/`disclosure`/`substantiation`/…）的字段语义未核实，
    **不纳入判据**，但会在输出里列出「未覆盖条数」——**不假装覆盖了全库**。
  · 本判据**不改数据**，只报。

用法：`python3 kb/l8/check_clause_no_idempotency.py [--selftest] [--json]`
"""
import argparse
import collections
import glob
import hashlib
import json
import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
CANON = os.path.join(ROOT, "kb/l4/canonical")
LEDGER = os.path.join(ROOT, "kb/l7/registry/l4-known-duplicates.yaml")
MIN_LEN = 10


def nz(s):
    s = s or ""
    s = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", s)
    s = re.sub(r"<[^>]+>", "", s)
    return re.sub(r"\s+", "", s).strip()


def content_key(o):
    """返回 (form, 指纹) 或 None（无内容键）。"""
    form = o.get("form")
    if form == "sample_case":
        t = nz(o.get("reason_analysis")) or nz(o.get("sample_body"))
    elif form == "scoped_clause":
        t = nz(o.get("clause_text"))
    else:
        return None
    if len(t) < MIN_LEN:
        return None
    return (form, hashlib.sha256(t.encode("utf-8")).hexdigest()[:16]), t[:110]


def load_ledger():
    """已知重复组：{组指纹: 说明} —— yaml 读不到就当空（保守一侧：会红，不静默放行）。"""
    if not os.path.exists(LEDGER):
        return {}
    try:
        import yaml
        d = yaml.safe_load(open(LEDGER, encoding="utf-8")) or {}
    except Exception:
        return {}
    return {g.get("key"): g for g in (d.get("known_duplicate_groups") or []) if g.get("key")}


def scan():
    groups = collections.defaultdict(list)
    uncovered = collections.Counter()
    for f in sorted(glob.glob(os.path.join(CANON, "*.jsonl"))):
        for line in open(f, encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            try:
                o = json.loads(line)
            except Exception:
                continue
            ck = content_key(o)
            if ck is None:
                uncovered[o.get("form")] += 1
                continue
            (form, fp), _ = ck
            groups[(form, fp)].append(o)
    dups = {k: v for k, v in groups.items() if len(v) > 1}
    return groups, dups, uncovered


def supersede_ok(members):
    """组内是否已做 supersede 标记（且入边/出边自洽）。"""
    nos = {m.get("article_no") for m in members}
    sup = {m.get("article_no") for m in members
           if m.get("status") == "superseded" and m.get("superseded_by")}
    # 对侧必须有 supersedes 指回来
    back = set()
    for m in members:
        for t in (m.get("supersedes") or []):
            back.add(t)
    return bool(sup) and sup <= back or (sup and sup.issubset(nos) and back)


def check(verbose=True):
    groups, dups, uncovered = scan()
    ledger = load_ledger()
    red, known, fixed = [], [], []
    for k, members in sorted(dups.items(), key=lambda x: -len(x[1])):
        nos = sorted(m.get("article_no") for m in members)
        fp = k[1]
        if fp in ledger:
            known.append((fp, k[0], nos))
        elif supersede_ok(members):
            fixed.append((fp, k[0], nos))
        else:
            red.append((fp, k[0], nos, nz(members[0].get("reason_analysis")
                                         or members[0].get("clause_text"))[:90]))
    if verbose:
        print(f"可比对条目 {sum(len(v) for v in groups.values())} ｜ "
              f"重复组 {len(dups)} ｜ 涉及条款号 {sum(len(v) for v in dups.values())}")
        print(f"  ✅ 已销号（supersede 标记齐）: {len(fixed)}")
        print(f"  📋 已在已知清单（待人裁）    : {len(known)}")
        print(f"  ❌ 未处理的重复组            : {len(red)}")
        if uncovered:
            print(f"  ⚠ 未纳入判据（内容键未核实的形态）: "
                  f"{dict(uncovered)} —— **本判据不假装覆盖它们**")
        if red:
            print("\n未处理的重复组（前 15）：")
            for fp, form, nos, head in red[:15]:
                print(f"   [{form}] {len(nos)} 个号 {nos[:4]} …  {head}")
    return red, known, fixed, uncovered


def selftest():
    """反向对照：把已知会红的样本真造出来，判据必须**精确变红**。"""
    ok = True
    checks = []

    def ck(name, cond, extra=""):
        nonlocal ok
        checks.append((name, cond, extra))
        if not cond:
            ok = False

    # ① 真重复（S-1.159/S-1.296 的形状）⇒ 必须判红
    a = {"form": "sample_case", "article_no": "S-TEST-A",
         "reason_analysis": "【品牌一致性】测试用重复内容，长度足够参与去重判别。", "status": "stable"}
    b = dict(a, article_no="S-TEST-B")
    ck("① 真重复 ⇒ 判红", not supersede_ok([a, b]))
    # ② 加了 supersede 标记（两侧齐）⇒ 判绿
    a2 = dict(a, status="superseded", superseded_by=["S-TEST-B"])
    b2 = dict(b, supersedes=["S-TEST-A"])
    ck("② supersede 两侧齐 ⇒ 判绿", supersede_ok([a2, b2]))
    # ③ 只标一侧（缺入边）⇒ 仍红
    ck("③ 只标被取代方、取代方没有 supersedes ⇒ 仍红", not supersede_ok([a2, b]))
    # ④ 内容不同 ⇒ 不该被判成一组
    c = dict(a, article_no="S-TEST-C", reason_analysis="完全不同的另一段内容，长度也够参与判别。")
    ck("④ 内容不同 ⇒ 指纹不同",
       content_key(a)[0] != content_key(c)[0])
    # ⑤ 空内容 ⇒ 不参与（不许塌组）
    e = {"form": "sample_case", "article_no": "S-TEST-E", "reason_analysis": ""}
    ck("⑤ 空内容 ⇒ 无内容键（不塌组）", content_key(e) is None)
    # ⑥ 未覆盖形态 ⇒ 明确返回 None（不假装覆盖）
    f = {"form": "revision_pair", "article_no": "W-TEST-F", "clause_text": "x" * 50}
    ck("⑥ 未核实形态 ⇒ 不纳入判据", content_key(f) is None)

    for name, cond, extra in checks:
        print(f"  {'✅' if cond else '❌'} {name} {extra}")
    print(f"\n自证：{sum(1 for _, c, _ in checks if c)}/{len(checks)} "
          f"{'通过' if ok else '**未通过**'}")
    return 0 if ok else 3


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        sys.exit(selftest())
    red, known, fixed, uncovered = check(verbose=not a.json)
    if a.json:
        print(json.dumps({"red": [{"key": r[0], "form": r[1], "article_nos": r[2]}
                                  for r in red],
                          "known": len(known), "fixed": len(fixed),
                          "uncovered_forms": uncovered}, ensure_ascii=False, indent=1))
    if red:
        print(f"\n❌ 有 {len(red)} 个重复组既没销号、也不在已知清单 ⇒ 退出码 3")
        sys.exit(3)
    print("\n✅ 无未处理的重复条款号")
    sys.exit(0)


if __name__ == "__main__":
    main()
