#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""retire_excluded_candidates.py —— **候选层退场**（PRD §2.2 排除项）。

════════════════════════════════════════════════════════════════════════
为什么不用 `kb/l7/scripts/l4_retire.py`（先核过，别照名字用）
════════════════════════════════════════════════════════════════════════

`l4_retire.py` 的判据是「按 `article_no` 去 `kb/l4/canonical/<形态>.jsonl` 里找行」。
实测（2026-10-10）：要退场的这 **94 条候选在 canonical 里 0 行** ——
它们**有号**（在 `l4.json → numbering.issued` 里）但**没定稿**（canonical 仍是 375 条 ⑥ 元数据）。
⇒ `l4_retire.py` 会以「找不到该条款号」（退出码 3）告终。**它管的是定稿层，不是候选层。**

**但它的三条语义是对的，本件照抄**（`l4_retire.py` 抬头逐字）：
1. **绝不删号** —— `numbering.no_reuse`：「号码一经发出永久占用，不回收、不重发」；
2. **不删证据** —— 候选行一个字不动，退场只**另立声明**；
3. **重跑零写入** —— 已退场的再跑一次，不新增、不改动。

════════════════════════════════════════════════════════════════════════
落点：为什么是**声明件**而不是改候选件
════════════════════════════════════════════════════════════════════════

`kb/l3/candidates/scoped_clauses.jsonl` 是 **L3 蒸馏器的覆盖写目标**
（`l3_distill_run.py` 每次跑都整份重写）。把退场标记写进去 ⇒ **下次重跑就被抹掉**，
退场记录消失而没人知道。⇒ 落点必须是**重跑冲不掉的地方**：`kb/l3/registry/`。

代价照实说：候选件里那 94 行**仍然在盘上、仍然是 `status: provisional`** ——
本件**不改它们**。判据（`check_external_standard_supply.py` 的 E4）读声明件后
把它们**从「可为依据」的计数里剔除，但在报告里照打**（不可见的退场 = 藏证据）。

★ 而「下次重跑还会不会又蒸出这 94 条」这件事，已由**另一处**解决：
`kb/l8/l3_scope.py::exclusion_of` 2026-10-10 加的那道门（`rule_eligible_false`）
⇒ 重跑时它们**根本进不了蒸馏**。两件事互补：**那道门防复发，本件清存量。**

用法：

    python3 kb/l8/retire_excluded_candidates.py             # 预演（默认，零写入）
    python3 kb/l8/retire_excluded_candidates.py --apply     # 写声明件
    python3 kb/l8/retire_excluded_candidates.py --selftest  # 反向对照（不碰真库）
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
KB = os.path.dirname(HERE)
SOURCE_READONLY = os.path.join(KB, "l7", "registry", "source-readonly.yaml")
L2_UNITS = os.path.join(KB, "l2", "units.jsonl")
L3_SCOPED = os.path.join(KB, "l3", "candidates", "scoped_clauses.jsonl")
L4_REG = os.path.join(KB, "l4", "registry", "l4.json")
DECL = os.path.join(KB, "l3", "registry", "retired-candidates.yaml")


def _yaml():
    try:
        import yaml  # noqa: PLC0415
        return yaml
    except ImportError:  # pragma: no cover
        raise SystemExit("需要 pyyaml")


def _sha12(p: str) -> str:
    return hashlib.sha256(open(p, "rb").read()).hexdigest()[:12]


def exclusion_source(reg_path: str = SOURCE_READONLY) -> dict:
    """读权威排除声明。**fail-closed**：读不到 / 空清单 ⇒ 抛错。

    静默当成「没有排除项」会让本件产出一份**空退场名单**，
    而那看起来和「已经退干净了」一模一样 —— 本库栽过这一类。
    """
    try:
        d = _yaml().safe_load(open(reg_path, encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        raise SystemExit("[拒跑] 读不到 %s（%r）—— fail-closed" % (reg_path, e))
    blk = (d or {}).get("prd_scope_exclusions") or {}
    recs = blk.get("records") or []
    rids = {r.get("record_id") for r in recs if r.get("record_id")}
    if not rids:
        raise SystemExit("[拒跑] %s 里没有 prd_scope_exclusions.records —— "
                         "空清单会产出一份「看起来退干净了」的空名单" % reg_path)
    return {"rids": rids, "prd_clause": blk.get("prd_clause"),
            "authority": blk.get("authority"),
            "reason_code": (blk.get("implementation_status") or {})
            .get("reason_code") or "prd_scope_exclusion"}


def _rid_of(row: dict) -> str:
    s = str(row.get("resource_id") or "")
    return s.split("__")[-1] if "__" in s else s


def scan(units_path: str = L2_UNITS, scoped_path: str = L3_SCOPED,
         l4_path: str = L4_REG, src: dict | None = None) -> dict:
    """找出「出自已声明排除的记录、且已有条款号」的候选。"""
    src = src or exclusion_source()
    rids = src["rids"]
    excl_units = set()
    with open(units_path, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            u = json.loads(line)
            if _rid_of(u) in rids:
                excl_units.add(u.get("unit_id"))
    assigned = {}
    l4 = json.load(open(l4_path, encoding="utf-8"))
    for _seg, body in ((l4.get("numbering") or {}).get("issued") or {}).items():
        assigned.update(body.get("assigned") or {})
    # ★★ **按 `clause_id` 取最后一行** —— 这一步不能省（实测踩过）：
    #   `scoped_clauses.jsonl` 是**追加式**的：同一 `clause_id` 先有一行（无 `article_no`），
    #   发号后**另起一行只加 `article_no`**（与 `kb/.work/l4_article.py:398-419` 同口径）。
    #   实测：6310 行 ⇒ **只有 3155 个唯一 `clause_id`**，每条正好两行。
    #   「逐行读全部」会把候选数**读成两倍** —— 我第一版就栽在这：
    #   把 **47** 条读成了 **94** 条，还写进了报告。
    #   判据：`read_last_per_key` 同口径（`kb/l7/scripts/l4_retire.py:52` 逐字同款）。
    last = {}
    n_rows = 0
    with open(scoped_path, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            n_rows += 1
            c = json.loads(line)
            last[c.get("clause_id")] = c
    hits = []
    for c in last.values():
        if c.get("unit_id") in excl_units or _rid_of(c) in rids:
            cid = c.get("clause_id")
            hits.append({"clause_id": cid,
                         # 号以 **l4 台账**为准；候选行里的 `article_no` 是副本，两者不一致要看得见
                         "article_no": assigned.get(cid) or c.get("article_no"),
                         "article_no_in_candidate": c.get("article_no"),
                         "unit_id": c.get("unit_id"),
                         "resource_id": c.get("resource_id"),
                         "status_in_candidate": c.get("status")})
    hits.sort(key=lambda x: str(x.get("article_no") or ""))
    return {"rids": sorted(rids), "hits": hits,
            "n_rows_in_file": n_rows,
            "n_candidates": len(last),
            "n_hits": len(hits),
            "n_with_article_no": sum(1 for h in hits if h.get("article_no")),
            "excl_units": sorted(excl_units)}


def render(scan_res: dict, src: dict, sha_paths: dict | None = None) -> str:
    """产出声明件文本（含**依据件的 sha**，便于日后复核「这份名单基于哪一版数据」）。"""
    L = []
    L.append("# retired-candidates.yaml —— 候选层退场名单（PRD §2.2 排除项）")
    L.append("#")
    L.append("# 谁写它：`kb/l8/retire_excluded_candidates.py --apply`（**本件由脚本生成，人手别改**）")
    L.append("# 谁读它：`kb/l8/check_external_standard_supply.py` 的判据 **E4**")
    L.append("#")
    L.append("# 三条纪律（照抄 `kb/l7/scripts/l4_retire.py` 的语义，它在定稿层，本件在候选层）：")
    L.append("#   ① **绝不删号** —— `numbering.no_reuse`：号码一经发出永久占用，不回收、不重发；")
    L.append("#   ② **不删证据** —— 候选行**一个字没动**（仍在 `kb/l3/candidates/scoped_clauses.jsonl` 里、")
    L.append("#      仍是 `status: provisional`）；本件只**另立声明**；")
    L.append("#   ③ **重跑零写入** —— 名单由数据现算，同样的数据跑第二次产出同一份。")
    L.append("#")
    L.append("# ★ 为什么落在这里而不是候选件里：候选件是 L3 蒸馏器的**覆盖写目标**，")
    L.append("#   写进去下次重跑就被抹掉，退场记录消失而无人知道。")
    L.append("# ★ 「下次重跑还会不会又蒸出这批」由**另一处**解决：")
    L.append("#   `kb/l8/l3_scope.py::exclusion_of` 的 `rule_eligible_false` 那道门（防复发）；")
    L.append("#   本件管**清存量**。两件事互补。")
    L.append("")
    L.append("meta:")
    L.append("  generated_by: kb/l8/retire_excluded_candidates.py")
    L.append("  generated_at: \"%s\"" % _now())
    L.append("  authority: kb/l7/registry/source-readonly.yaml → prd_scope_exclusions")
    L.append("  checker: kb/l8/check_external_standard_supply.py（判据 E4）")
    L.append("  reason_code: %s" % src["reason_code"])
    sp = sha_paths or {"kb/l2/units.jsonl": L2_UNITS,
                       "kb/l3/candidates/scoped_clauses.jsonl": L3_SCOPED,
                       "kb/l4/registry/l4.json": L4_REG}
    L.append("  basis_sha256_12:")
    for _label, _p in sp.items():
        L.append("    %s: \"%s\"" % (_label, _sha12(_p) if os.path.exists(_p) else "missing"))
    L.append("  no_reuse_note: >")
    L.append("    号不回收 ⇒ 退场后这 %d 个 E-1 号**永久保留**，台账上会显示为")
    L.append("    「有号、无（可用）候选」。**那不是缺号，是退场。**")
    L.append("")
    L.append("counts:")
    L.append("  hits_total: %d" % scan_res["n_hits"])
    L.append("  hits_with_article_no: %d" % scan_res["n_with_article_no"])
    L.append("  retired: %d" % scan_res["n_hits"])
    L.append("")
    L.append("retired:")
    for h in scan_res["hits"]:
        L.append("  - clause_id: %s" % h["clause_id"])
        L.append("    article_no: %s" % (h.get("article_no") or "null"))
        L.append("    unit_id: %s" % h.get("unit_id"))
        L.append("    resource_id: %s" % h.get("resource_id"))
        L.append("    status: retired")
        L.append("    reason_code: %s" % src["reason_code"])
    L.append("")
    return "\n".join(L) + "\n"


def _now():
    import datetime
    return datetime.datetime.now().astimezone().replace(microsecond=0).isoformat()


def run(apply_now: bool, decl_path: str = DECL, reg_path: str = SOURCE_READONLY,
        **paths) -> int:
    src = exclusion_source(reg_path)
    res = scan(src=src, **paths)
    text = render(res, src, {"kb/l2/units.jsonl": paths.get("units_path", L2_UNITS),
                             "kb/l3/candidates/scoped_clauses.jsonl": paths.get("scoped_path", L3_SCOPED),
                             "kb/l4/registry/l4.json": paths.get("l4_path", L4_REG)})
    print("候选层退场（PRD §2.2 排除项）")
    print("-" * 70)
    print("  权威排除声明：kb/l7/registry/source-readonly.yaml → prd_scope_exclusions")
    print("  被排除的记录：%d 条" % len(src["rids"]))
    for r in res["rids"]:
        print("      %s" % r)
    print("  候选件：逐行 %d 行 ⇒ 按 clause_id 取最后一行 **%d 个候选**（追加式：发号另起一行）"
          % (res["n_rows_in_file"], res["n_candidates"]))
    print("  命中候选：**%d 条**（其中带条款号 %d 条）"
          % (res["n_hits"], res["n_with_article_no"]))
    print("  号段样本：%s" % "、".join("%s=%s" % (h["clause_id"][:14], h["article_no"])
                                      for h in res["hits"][:3]))
    print("  候选件**一个字节不动**；号**不回收**（no_reuse）")
    print("-" * 70)
    old = open(decl_path, encoding="utf-8").read() if os.path.exists(decl_path) else None
    # ★ 幂等判据**必须剔除 `generated_at`** —— 否则同一份数据跑第二次会因为时间戳不同
    #   而「有变化」，于是**备份 + 重写**：docstring 里写的「重跑零写入」就成了假话。
    #   实测踩过（第二次 --apply 真产生了 .bak 并重写了文件）。
    #   口径：**内容（除时间戳外）逐字相同 ⇒ 零写入，保留原有时间戳**。
    def _body(t):
        return "\n".join(x for x in t.splitlines() if not x.strip().startswith("generated_at:"))
    if not apply_now:
        # ★ `len(text)` 是**字符数**，不是字节数（中文 3 字节/字）——
        #   原先这行写「%d 字节」，和 `ls` 一比像是文件被改过（实测虚惊一次）。
        print("[预演] 将写入 %s（%d 字符 / %d 字节）—— 加 --apply 才落盘"
              % (decl_path, len(text), len(text.encode("utf-8"))))
        return 0
    if old is not None and _body(old) == _body(text):
        print("[零写入] %s 内容未变（同样的数据 ⇒ 同一份名单；保留原 generated_at）" % decl_path)
        return 0
    if old is not None:
        bak = decl_path + ".bak-" + _now().replace(":", "").replace("-", "")[:15]
        shutil.copy2(decl_path, bak)
        print("[备份] %s" % bak)
    os.makedirs(os.path.dirname(decl_path), exist_ok=True)
    # `.yaml` **不在** .md/.sh 中招名单里 ⇒ 直写安全（AGENTS.md 逐扩展名实测）；
    # 仍回读复核（写完能读回来才是保证）。
    with open(decl_path, "w", encoding="utf-8") as fh:
        fh.write(text)
    back = open(decl_path, encoding="utf-8").read()
    if back != text:
        raise SystemExit("回读不符：写 %d / 读 %d" % (len(text), len(back)))
    print("[落盘] %s（%d 字符 / %d 字节，回读一致）"
          % (decl_path, len(text), len(text.encode("utf-8"))))
    return 0


# ══════════════════════════════════════════════════════════════════════
# 反向对照
# ══════════════════════════════════════════════════════════════════════

def _selftest() -> int:
    ok = fail = 0
    fails: list[str] = []

    def ck(n, c, ex=""):
        nonlocal ok, fail
        if c:
            ok += 1
        else:
            fail += 1
            fails.append("%s %s" % (n, ex))

    d = tempfile.mkdtemp(prefix="retire-", dir="/tmp")
    try:
        units = os.path.join(d, "units.jsonl")
        scoped = os.path.join(d, "scoped.jsonl")
        l4 = os.path.join(d, "l4.json")
        reg = os.path.join(d, "sr.yaml")
        with open(units, "w", encoding="utf-8") as f:
            f.write(json.dumps({"unit_id": "u1", "resource_id": "bitable__t__recAAA"}) + "\n")
            f.write(json.dumps({"unit_id": "u2", "resource_id": "bitable__t__recBBB"}) + "\n")
        with open(scoped, "w", encoding="utf-8") as f:
            # ★ 夹具照**真件的追加式形状**造：c1 两行（发号后另起一行只加 article_no）
            f.write(json.dumps({"clause_id": "c1", "unit_id": "u1",
                                "resource_id": "bitable__t__recAAA", "status": "provisional"}) + "\n")
            f.write(json.dumps({"clause_id": "c1", "unit_id": "u1",
                                "resource_id": "bitable__t__recAAA", "status": "provisional",
                                "article_no": "E-1.1"}) + "\n")
            f.write(json.dumps({"clause_id": "c2", "unit_id": "u2",
                                "resource_id": "bitable__t__recBBB", "status": "provisional"}) + "\n")
        json.dump({"numbering": {"issued": {"E-1": {"assigned": {"c1": "E-1.1"}}}}},
                  open(l4, "w", encoding="utf-8"))
        _yaml().safe_dump({"prd_scope_exclusions": {
            "records": [{"record_id": "recAAA"}],
            "implementation_status": {"reason_code": "prd_scope_exclusion"}}},
            open(reg, "w", encoding="utf-8"), allow_unicode=True)

        # ① 只挑出被排除那一条
        src = exclusion_source(reg)
        res = scan(units, scoped, l4, src)
        ck("①只命中被排除的记录", [h["clause_id"] for h in res["hits"]] == ["c1"],
           res["hits"])
        ck("①a ★ 追加式去重：3 行 ⇒ 2 个候选（**不许逐行读**）",
           res["n_rows_in_file"] == 3 and res["n_candidates"] == 2,
           (res["n_rows_in_file"], res["n_candidates"]))
        ck("①a2 ★ 命中数不被行数翻倍（1 条，不是 2 条）", res["n_hits"] == 1, res["n_hits"])
        ck("①a3 号取最后一行那个", res["hits"][0]["article_no"] == "E-1.1",
           res["hits"][0])
        ck("①b 带号", res["n_with_article_no"] == 1, res["n_with_article_no"])
        ck("①c 非排除记录不被误伤", "c2" not in [h["clause_id"] for h in res["hits"]],
           res["hits"])

        # ② fail-closed：空排除清单 ⇒ 必须抛，不许产出空名单
        _yaml().safe_dump({"prd_scope_exclusions": {"records": []}},
                          open(reg, "w", encoding="utf-8"), allow_unicode=True)
        try:
            exclusion_source(reg)
            ck("②空清单必须 fail-closed", False, "没抛")
        except SystemExit:
            ck("②空清单必须 fail-closed", True)

        # ③ fail-closed：文件读不到 ⇒ 必须抛
        try:
            exclusion_source(os.path.join(d, "no-such.yaml"))
            ck("③读不到必须 fail-closed", False, "没抛")
        except SystemExit:
            ck("③读不到必须 fail-closed", True)

        # ④ 重跑零写入（同数据 ⇒ 同文本）
        _yaml().safe_dump({"prd_scope_exclusions": {
            "records": [{"record_id": "recAAA"}],
            "implementation_status": {"reason_code": "prd_scope_exclusion"}}},
            open(reg, "w", encoding="utf-8"), allow_unicode=True)
        src = exclusion_source(reg)
        r1 = scan(units, scoped, l4, src)
        t1 = render(r1, src)
        r2 = scan(units, scoped, l4, src)
        t2 = render(r2, src)
        # generated_at 会变 ⇒ 比去掉时间戳后的正文
        strip = lambda t: "\n".join(x for x in t.splitlines() if "generated_at" not in x)
        ck("④重跑零写入（正文逐字一致）", strip(t1) == strip(t2))

        # ⑤ 声明件里必须**逐条**列出、不许少报
        ck("⑤名单逐条列出（c1 只出现一次）",
       t1.count("clause_id: c1") == 1 and "retired: 1" in t1, t1[:200])
        ck("⑤0 夹具生效（c1 在名单里）", "clause_id: c1" in t1, t1[:200])
        ck("⑤b 号写进名单（不删号）", "article_no: E-1.1" in t1)
        ck("⑤c 记了依据件的 sha", "basis_sha256_12" in t1 and "scoped_clauses" in t1)

        # ⑥ 候选件**没被碰**（本件只写声明件）
        before = _sha12(scoped)
        run(True, decl_path=os.path.join(d, "decl.yaml"), reg_path=reg,
            units_path=units, scoped_path=scoped, l4_path=l4)
        ck("⑥候选件一个字节没动", _sha12(scoped) == before, (_sha12(scoped), before))
        _dt = open(os.path.join(d, "decl.yaml"), encoding="utf-8").read()
        ck("⑥b 声明件落盘", os.path.exists(os.path.join(d, "decl.yaml")))
        ck("⑥b2 ★ 这次走的是**夹具**注册表（名单里有 c1）", "clause_id: c1" in _dt, _dt[:300])
        # ⑥c 连跑两次 ⇒ 第二次零写入（不新增备份）
        r = run(True, decl_path=os.path.join(d, "decl.yaml"), reg_path=reg,
                units_path=units, scoped_path=scoped, l4_path=l4)
        ck("⑥c 第二次零写入", r == 0)
    finally:
        shutil.rmtree(d, ignore_errors=True)

    print("retire_excluded_candidates --selftest：%d/%d" % (ok, ok + fail))
    for f in fails:
        print("  ✗", f)
    return 0 if fail == 0 else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="候选层退场（PRD §2.2 排除项；不删号、不改候选件）")
    ap.add_argument("--apply", action="store_true", help="写声明件（默认预演）")
    ap.add_argument("--decl", default=DECL)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return _selftest()
    return run(a.apply, decl_path=a.decl)


if __name__ == "__main__":
    sys.exit(main())
