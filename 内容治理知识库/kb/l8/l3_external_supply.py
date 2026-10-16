#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""l3_external_supply.py —— L3 **外部标准供给量**的判据（#5 那条指标的常驻尺子）。

指标（口径来自 `改动单-外部标准抽取口径-20261010.md` ＋ `核定-自有站为何蒸不出规则与5的指标量错了-20261012.md`）：
    `kb/l3/candidates/scoped_clauses.jsonl` 的**唯一 `clause_id` 数**（＋行数）。
    为什么不是 `rules.jsonl` 里的 `external_standard`：那份文件的 `kb_type` 结构性恒为 `wording`
    ⇒ 那个数**恒为 0**，与「抓了多少外部标准」无关（**量错了产物**）。

★ 三态（退出码 0 / 4 / 3）：
    0 = 达标（≥ 门槛）｜ 4 = **未测：产物比产它的代码旧 ⇒ 还没重建**（不是不达标）｜ 3 = 低于门槛（红）

★★ 为什么「产物比代码旧」要单列一档（2026-10-12 实测栽过）：
    两个修复（`extract_office_batch.py` 的定长切 → 按行切；`l3_scope.py` 补 `GOOD_QUALITY_FLAGS` 白名单）
    是**今天 12:53** 落的，而真库产物 `scoped_clauses.jsonl` 还是 **10-10 16:56** 的
    ⇒ 指标在真库上仍是 **3,155**，而「+263（→3,418）」是**沙箱重建后**的读数。
    若判据只比门槛，会把这单报成「不达标」——**报错的症状**（该报的是"还没重建"）。
    这条与库内既有的 stale 族同源：**产物旧 ≠ 结果坏**。

用法：
    python3 kb/l8/l3_external_supply.py            # 人读；0/4/3
    python3 kb/l8/l3_external_supply.py --json
    python3 kb/l8/l3_external_supply.py --selftest # 反向对照（三个分支各喂一次真变异）
"""
from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARTIFACT = os.path.join(ROOT, "kb/l3/candidates/scoped_clauses.jsonl")
# 产这份产物的代码（任一比产物新 ⇒ 判「未重建」）
PRODUCERS = [os.path.join(ROOT, "kb/l8/extract_office_batch.py"),
             os.path.join(ROOT, "kb/l8/l3_scope.py")]
REGISTRY = os.path.join(ROOT, "kb/l7/registry/l3-external-supply.yaml")

DEFAULT_FLOOR = 3418          # 沙箱重建后的实测值（核定件 §61）；重建完成即应 ≥ 它


def _floor():
    """门槛真源 = 登记件；读不到回落常量（并如实说明）。"""
    try:
        import yaml
        d = yaml.safe_load(open(REGISTRY, encoding="utf-8")) or {}
        v = (d.get("metric") or {}).get("floor")
        if isinstance(v, int):
            return v, os.path.relpath(REGISTRY, ROOT)
    except Exception:                                           # noqa: BLE001
        pass
    return DEFAULT_FLOOR, "常量（登记件读不到）"


def count(artifact=ARTIFACT):
    """读产物：返回 (行数, 唯一 clause_id 数, 空 clause_id 行数)。"""
    rows = []
    with open(artifact, encoding="utf-8") as fh:
        for l in fh:
            if l.strip():
                rows.append(json.loads(l))
    ids = {r.get("clause_id") for r in rows if r.get("clause_id")}
    blank = sum(1 for r in rows if not r.get("clause_id"))
    return len(rows), len(ids), blank


def judge(artifact=ARTIFACT, producers=None, floor=None):
    """判据本体（纯函数，便于自证喂样本）。返回 (rc, detail)。"""
    producers = PRODUCERS if producers is None else producers
    floor = _floor()[0] if floor is None else floor
    d = {"artifact": os.path.relpath(artifact, ROOT), "floor": floor}
    if not os.path.exists(artifact):
        d["note"] = "产物不在 ⇒ 未测"
        return 4, d
    try:
        rows, uniq, blank = count(artifact)
    except Exception as e:                                      # noqa: BLE001
        d["note"] = f"读不动：{e!r} ⇒ 未测"
        return 4, d
    d.update({"rows": rows, "unique_clause_id": uniq, "blank_clause_id": blank})
    # ① 产物是否比产它的代码旧 ⇒ 「还没重建」（不是不达标）
    art_m = os.path.getmtime(artifact)
    newer = [os.path.relpath(p, ROOT) for p in producers
             if os.path.exists(p) and os.path.getmtime(p) > art_m]
    d["newer_producers"] = newer
    if newer:
        d["note"] = ("**产物比产它的代码旧 ⇒ 还没重建**："
                     + "、".join(newer) + " 比产物新")
        return 4, d
    # ② 达标 / 不达标
    if uniq >= floor:
        return 0, d
    d["note"] = f"唯一 clause_id {uniq} < 门槛 {floor}"
    return 3, d


# ══════════════════════════════════════════════════════════════════════════
# 第二个指标：`rules.jsonl` 的**条款号透传**不许退化（★2026-10-12 实测加的）
# ══════════════════════════════════════════════════════════════════════════
# 为什么它必须和上面那条指标长在同一把尺子上（实测，不是预防性设计）：
#   L3 重建会重写 `kb/l3/candidates/rules.jsonl`，而**引擎产的是一规则一行、`article_no=""`**；
#   盘上那份是 **1018 行**（L4 把**带条款号的副本**追加回来）。
#   ⇒ 一次朴素的重建就把 **509 个条款号清零**（夹具库实测：非空 509 → **0**）。
#   而它们在下游**只有这一个来源**：`kb/.work/l5_export.py:562-564`
#       article_no=(str(r.get("article_no") or "").strip() or None),
#       article_no_source="kb/l3/candidates/rules.jsonl#article_no"
#   ⇒ 清了它，`kb/l5/p0_patterns.jsonl` 的 **11 条条款号全变 None**
#      —— 那正是**目标 18「P0 红线法务逐条确认」那张台账（11 条）**要签的东西。
#   ★ 且**不会自愈**：L4 的写档要「人开闸」（`layers.yaml` L4 写档三条件）。
# 现行防线 = 引擎的**闸①b 内容同一性**（`l3_distill_run.py` 的 `CONTENT_ID`：按 rule_id 比
#   `evidence_digest`，509 条全等 ⇒ 不重写）。**本指标就是那道闸的常驻见证** ——
#   闸被人"清理"掉、或口径变了以后再重写，这里立刻红。
# 门槛 = 已发号规则数（号码一经发出永久占用 ⇒ 只增不减；新发号后把门槛往上调）。
RULES = os.path.join(ROOT, "kb/l3/candidates/rules.jsonl")
DEFAULT_RULES_FLOOR = 509


def _rules_floor():
    try:
        import yaml
        d = yaml.safe_load(open(REGISTRY, encoding="utf-8")) or {}
        v = ((d.get("metric_rules_article_no") or {}).get("floor"))
        if isinstance(v, int):
            return v, os.path.relpath(REGISTRY, ROOT)
    except Exception:                                           # noqa: BLE001
        pass
    return DEFAULT_RULES_FLOOR, "常量（登记件读不到）"


def count_rules_article_no(path=RULES):
    """(行数, 唯一 rule_id, article_no 非空行数)。"""
    rows = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]
    return (len(rows), len({r.get("rule_id") for r in rows}),
            sum(1 for r in rows if str(r.get("article_no") or "").strip()))


def judge_rules(path=RULES, floor=None):
    """条款号透传判据。返回 (rc, detail)：0 达标 ／ 4 未测 ／ 3 退化（红）。"""
    floor = _rules_floor()[0] if floor is None else floor
    d = {"artifact": os.path.relpath(path, ROOT), "floor": floor}
    if not os.path.exists(path):
        d["note"] = "rules.jsonl 不在 ⇒ 未测"
        return 4, d
    try:
        rows, uniq, na = count_rules_article_no(path)
    except Exception as e:                                      # noqa: BLE001
        d["note"] = f"读不动：{e!r} ⇒ 未测"
        return 4, d
    d.update({"rows": rows, "unique_rule_id": uniq, "article_no_nonempty": na})
    if na >= floor:
        return 0, d
    d["note"] = (f"条款号非空 **{na}** < 门槛 {floor} —— L4 追加回候选件的条款号**被抹掉了**。"
                 "下游只有这一个来源（`l5_export.py` 的 article_no_source），"
                 "⇒ `kb/l5/p0_patterns.jsonl` 的 11 条条款号会变 None（目标 18 法务签署台账失控）。"
                 "**不要手工补**：查引擎的闸①b（CONTENT_ID「内容同一性」）是不是被拆了，"
                 "并从 `kb/l3/_archive/<RUN>-prewrite/rules.jsonl` 取回旧件。")
    return 3, d


def read_backlog(artifact=ARTIFACT):
    """**信息档（只报不判红）**：候选里还没发号（`article_no` 空）的条数。

    ★ 为什么只报不判：候选未发号是**正常中间态**（L3 产候选 → L4 发号 → 抽查签字 → canonical），
      不是缺陷。把它做成红 = **造一条假红**（本库栽过：「一条假红会挤掉一个真问题」）。
    ★ 为什么非报不可：它是**不会自己消失的欠账** —— Owner 2026-10-12 裁定
      「263 条新条款**留到目标 5 收口一起发号**」；不摆在读数里就会忘。
      发号入口与前置：`python3 kb/.work/l4_article.py <RUN>`（默认干跑）＋ L4 写档三条件（**人开闸**）；
      发完再 `python3 kb/l8/l4_promote.py`（干跑出抽查单）→ 人签 → `--apply --signoff`。
    """
    last = {}
    for l in open(artifact, encoding="utf-8"):
        if l.strip():
            r = json.loads(l)
            last[r.get("clause_id")] = r
    un = [c for c, r in last.items() if not str(r.get("article_no") or "").strip()]
    return len(last), len(un)


def selftest():
    """反向对照：各分支喂**真变异**（现造临时产物，不碰真库）。"""
    import tempfile
    import time
    tmp = tempfile.mkdtemp()
    art = os.path.join(tmp, "scoped_clauses.jsonl")
    # 造一个「比代码新」的产物：写完把 mtime 推到未来
    with open(art, "w", encoding="utf-8") as fh:
        for i in range(5):
            fh.write(json.dumps({"clause_id": f"E-1.{i}", "kb_type": "external_standard"},
                                ensure_ascii=False) + "\n")
    future = time.time() + 3600
    os.utime(art, (future, future))
    old_code = os.path.join(tmp, "old_code.py")
    open(old_code, "w").close()
    os.utime(old_code, (time.time() - 3600, time.time() - 3600))
    chk = []

    def c(name, got, want):
        chk.append((name, got == want, got, want))

    c("① 达标（唯一数 ≥ 门槛）⇒ rc 0", judge(art, [old_code], floor=5)[0], 0)
    c("② 低于门槛 ⇒ rc 3（红）", judge(art, [old_code], floor=99)[0], 3)
    # 真变异：把「产它的代码」mtime 推到比产物新 ⇒ 必须判「未重建」（rc 4），**不是**判红
    newer_code = os.path.join(tmp, "new_code.py")
    open(newer_code, "w").close()
    os.utime(newer_code, (future + 3600, future + 3600))
    rc4, d4 = judge(art, [newer_code], floor=99)
    c("③ 反向对照：代码比产物新 ⇒ **未重建（rc 4）**，不许判红", rc4, 4)
    c("③b 且说明里点名了「还没重建」", "还没重建" in d4.get("note", ""), True)
    c("④ 产物不在 ⇒ rc 4（未测）", judge(os.path.join(tmp, "nope.jsonl"), [old_code], floor=1)[0], 4)

    # ── 指标二：条款号透传（反向对照 = **把缺陷真造一遍**：写一份条款号被清零的 rules.jsonl）──
    rp = os.path.join(tmp, "rules.jsonl")
    with open(rp, "w", encoding="utf-8") as fh:
        for i in range(3):
            fh.write(json.dumps({"rule_id": f"r-{i}", "article_no": f"W-1.{i}"},
                                ensure_ascii=False) + "\n")
    c("⑤ 条款号齐全 ⇒ rc 0", judge_rules(rp, floor=3)[0], 0)
    with open(rp, "w", encoding="utf-8") as fh:                 # 真变异：条款号清零
        for i in range(3):
            fh.write(json.dumps({"rule_id": f"r-{i}", "article_no": ""},
                                ensure_ascii=False) + "\n")
    rc5, d5 = judge_rules(rp, floor=3)
    c("⑥ 反向对照：条款号被清零 ⇒ **rc 3（红）**", rc5, 3)
    c("⑥b 且说明里点名了「被抹掉」与下游（p0_patterns）",
      ("被抹掉" in d5.get("note", "") and "p0_patterns" in d5.get("note", "")), True)
    c("⑦ 文件不在 ⇒ rc 4（未测，不是红）",
      judge_rules(os.path.join(tmp, "nope-rules.jsonl"), floor=3)[0], 4)
    c("⑧ 真库真身**现在**达标（≥ 登记件门槛）", judge_rules()[0], 0)

    # ── 信息档：待发号欠账 **只报不判红**（反向对照：欠账存在时 rc 必须仍为 0）──
    up = os.path.join(tmp, "unnumbered.jsonl")
    with open(up, "w", encoding="utf-8") as fh:
        for i in range(4):
            fh.write(json.dumps({"clause_id": f"E-1.{i}", "kb_type": "external_standard",
                                 "article_no": "" if i < 3 else f"E-1.{i}"},
                                ensure_ascii=False) + "\n")
    c("⑨ 待发号欠账**不许**影响 rc（欠账 ≠ 缺陷）", judge(up, [old_code], floor=4)[0], 0)
    c("⑨b 但欠账数要**报出来**", read_backlog(up)[1], 3)
    import shutil as _sh
    _sh.rmtree(tmp, ignore_errors=True)
    ok = True
    for name, good, got, want in chk:
        ok = ok and good
        print(f"  {'✅' if good else '❌'} {name}（实得 {got}／期望 {want}）")
    print("结论：%s" % ("✅ 两条指标共 %d 例全对（含两组反向对照），假红挡住了" % len(chk) if ok else "❌ 有分支不符"))
    return 0 if ok else 3


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    rc1, d1 = judge()
    rc2, d2 = judge_rules()
    # 合并口径：**红(3) 压过 未测(4) 压过 达标(0)** —— 一条真退化不许被另一条的"未测"盖住
    rc = 3 if 3 in (rc1, rc2) else (4 if 4 in (rc1, rc2) else 0)
    fl, src = _floor()
    fl2, src2 = _rules_floor()
    d1.update({"rc": rc1, "floor_source": src})
    d2.update({"rc": rc2, "floor_source": src2})
    # 信息档（只报不判红）：待发号欠账
    try:
        n_tot, n_un = read_backlog()
    except Exception as e:                                      # noqa: BLE001
        n_tot, n_un = None, None
        d2["backlog_error"] = repr(e)
    if a.json:
        print(json.dumps({"rc": rc, "metric": d1, "metric_rules_article_no": d2,
                          "backlog_unnumbered": n_un, "backlog_total": n_tot},
                         ensure_ascii=False, indent=1))
    else:
        print("L3 外部标准供给量（唯一 clause_id）")
        print(f"  产物：{d1.get('artifact')}｜行数 {d1.get('rows')}｜唯一 clause_id **{d1.get('unique_clause_id')}**"
              f"｜空 clause_id {d1.get('blank_clause_id')}")
        print(f"  门槛：{fl}（{src}）")
        if d1.get("newer_producers"):
            print(f"  ⏳ 未测：**还没重建** —— {'、'.join(d1['newer_producers'])} 比产物新")
            print("     ⇒ 想让它生效要重建 L3（写操作，走 kb-pipeline 那条链，别在这里顺手写）")
        elif rc1 == 0:
            print("  ✅ 达标")
        else:
            print(f"  ❌ 低于门槛：{d1.get('note')}")
        print("L3 条款号透传（rules.jsonl 的 article_no 非空数）")
        print(f"  产物：{d2.get('artifact')}｜行数 {d2.get('rows')}｜唯一 rule_id {d2.get('unique_rule_id')}"
              f"｜条款号非空 **{d2.get('article_no_nonempty')}**")
        print(f"  门槛：{fl2}（{src2}）")
        print("  ✅ 未退化（L5 的 P0 条款号仍有来源）" if rc2 == 0 else f"  {'❌' if rc2 == 3 else '⏳'} {d2.get('note')}")
        if n_un is not None:
            print("L3 待发号欠账（**只报不判红**：未发号是正常中间态，不是缺陷）")
            print(f"  候选 {n_tot} 条 ｜ **待发号 {n_un} 条** ⇒ 进不了 L4 定稿（C8「该候选没有号」）")
            print("  ★ Owner 2026-10-12 裁定：这 %d 条**留到目标 5 收口一起发号**。" % n_un)
            print("     续做入口：`python3 kb/.work/l4_article.py <RUN>`（默认干跑）→ 人开闸 → "
                  "`python3 kb/l8/l4_promote.py` 出抽查单 → 人签 → `--apply --signoff`")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
