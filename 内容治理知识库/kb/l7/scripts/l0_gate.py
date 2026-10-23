#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""l0_gate.py —— L0 层闸门（**判定档**）：把「原始差异」判成「真差异 / 预期内 / 已知阻断」。

## 它补的是哪个洞（实测依据）

库自带的 `kb/l8/align_l0_feishu.py --check` 报的是**原始**四类差异，判据是「四类差异全 0」。
但实测：`材料收集` 有 10 条记录**按声明就该排除**（`kb/l0/registry/kb.json → filter`
只收「材料审核状态 == 通过」）—— 它们会**永远**被算成「飞书多」，
于是 **L0 闸门永远红**。无人值守的日报每天报同一个假红，第三天就没人看了。

→ 本脚本把政策判断从对账器里**分出来**：
  * `align_l0_feishu.py`：**只报原始事实**（不动它，它是对的）；
  * `kb/l7/registry/l0-expected-diffs.yaml`：声明「哪些差异按声明就该存在」（带 evidence）；
  * **本脚本**：原始 − 预期 = **真差异**，只有真差异才判红。

## 输出纪律（**不许抹掉原始数**）

任何一次输出都同时给三个数：**原始 / 预期内 / 真差异**。
预期项只是被**分类出来**，不是被减掉不提。

## 判据

  真差异 == 0                    → 退出 0（过）
  真差异 > 0（实际多于预期）        → 退出 1（红）：**条数变了要重新评估，不是自动放宽**
  预期项实际 < 预期（少了）         → 退出 0，但打 ⚠️ 提示复核声明（可能是别人修好了，也可能口径变了）
  出现**没有声明**的差异表/类目      → 退出 1（红）

## 只读

只做两件事：跑 `align_l0_feishu.py --check`（其 --check 档自身零写）+ 读 YAML。
**不写 `kb/l0` 的任何东西**。

用法：
    kb/kbpy l7/scripts/l0_gate.py            # 判定档（默认，给人看）
    kb/kbpy l7/scripts/l0_gate.py --json     # 机器可读
    kb/kbpy l7/scripts/l0_gate.py --quiet    # 只出汇总
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
KB = os.path.dirname(os.path.dirname(HERE))          # …/kb
ROOT = os.path.dirname(KB)                            # kb/ 的上一级（cwd 约定）
KBPY = os.path.join(KB, "kbpy")
REPORTER = "l8/align_l0_feishu.py"          # ← 相对 kb/（kbpy 的解析基准），别写 kb/l8/...
EXPECT = os.path.join(KB, "l7/registry/l0-expected-diffs.yaml")

ROW = re.compile(r"^\[(?P<name>[^\]]+)\]\s+飞书=(?P<f>\d+)\s+L0=(?P<l>\d+)\s+一致=(?P<same>\d+)"
                 r"\s+飞书多=(?P<of>\d+)\s+L0多=(?P<ol>\d+)\s+值变=(?P<ch>\d+)\s*$")
FAIL = re.compile(r"^\[拉取失败\]\s+(?P<name>\S+?)\s+(?P<tid>\S+?):")
#: ★ 2026-10-19：对齐器多打的一行 —— 只有飞书有的**记录 id + 快照路径**。
#:   闸门要判的是「这几条是不是**都被 filter 排除**」，不是「一共几条」——
#:   条数只是那个判据的**影子**（2026-10-18 周更就是被影子打停的）。
IDS = re.compile(r"^\[only-feishu-ids\]\s*(?P<json>\{.*\})\s*$")
TOTALS = re.compile(r"一致\s+(?P<same>\d+)\s*\|\s*飞书多\s+(?P<of>\d+)\s*\|\s*L0多\s+(?P<ol>\d+)"
                    r"\s*\|\s*值变\s+(?P<ch>\d+)\s*\|\s*拉取失败\s+(?P<pf>\d+)")


def load_yaml(p):
    try:
        import yaml as _y
        return _y.safe_load(io.open(p, encoding="utf-8"))
    except Exception:
        # 库内降级：复用 skills_check 的内置解析器（与其余闸门一致，不因缺 PyYAML 就崩）
        sys.path.insert(0, HERE)
        import skills_check as SC
        return SC.parse_yaml_subset(io.open(p, encoding="utf-8").read())


def _rec(ok, real, n_exp):
    """run 记录：L0 每日只读对账这一趟（kb-l0-feishu 是 L0 的 owner）。"""
    try:
        import os as _o, sys as _s
        _s.path.insert(0, _o.path.dirname(_o.path.abspath(__file__)))
        from run_record import record as _rr
        _rr(source="l0_daily", trigger="L0 对齐（每日只读）", skills=["kb-l0-feishu"],
            commands=["kb/kbpy l7/scripts/l0_gate.py"],
            products=["kb/l7/reports/2026-09-30-daily-health.md"],   # 明细在日报里
            verdict="%s ｜ 真差异=%d ｜ 预期内=%d" % ("过" if ok else "未过", real, n_exp),
            human_involved=False)
    except Exception as exc:              # noqa: BLE001
        print("[warn] run_record 没写成：%r" % (exc,), file=sys.stderr)


# ══════════════════════════════════════════════════════════════════════════
# ★ 2026-10-19：`filter_assert` —— 声明内差异的判据从「**数条数**」换成「**逐条复算**」
# ══════════════════════════════════════════════════════════════════════════
# 为什么非换（2026-10-18 真事故）：EX-1 写的是「材料收集 only_feishu expected 11」，
#   而它真正该核的是「这 N 条是不是**都被 `kb/l0/registry/kb.json → filter` 排除**」
#   （filter 只收「材料审核状态 == 通过」）。**条数只是那个判据的影子**：
#   源侧只要多一条未审核材料，影子就变 ⇒ 闸门判红 ⇒ 整轮停在 L0（L1–L7 一周没跑）。
#   ⇒ 有 `filter_assert` 时就按逐条复算判；**读不到数据就回退计数**（fail-closed）。
def _judge_by_filter(info, spec):
    """逐条复算：只有飞书有的那些记录，是否**都已被 filter 排除**。

    返回 `(state, n_bad, why)`：

      · `True`  ⇒ 全部被排除 ⇒ **声明内**（条数变了也不红 —— 条数只是这个判据的影子）
      · `False` ⇒ 有记录**不该被排除** ⇒ 真差异（残差 = 违规条数）
      · `None`  ⇒ **判不了**（快照/字段缺）⇒ 调用方**必须回退计数** ——
        「无法证明干净」≠「证明干净」，这是 fail-closed 的唯一方向。

    `spec` 形如 `{"field": "材料审核状态", "not_in": ["通过"]}`：
    「值不在 not_in 里」= 被 filter 排除 = 它本来就不该入库。
    """
    if not isinstance(spec, dict) or not spec.get("field"):
        return None, 0, "声明里没有 filter_assert.field"
    fld = str(spec.get("field"))
    if not isinstance(info, dict) or not info.get("snap"):
        return None, 0, "对齐器没给出快照路径（拿不到逐条字段）"
    ids = info.get("ids") or []
    if not ids:
        return None, 0, "对齐器没给出 only_feishu 的记录 id"
    recs = {}
    try:
        with io.open(info["snap"], encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                r = json.loads(line)
                rid = r.get("record_id") or r.get("recordId")
                if rid:
                    recs[str(rid)] = r
    except Exception as e:                                    # noqa: BLE001
        return None, 0, "快照读不到（%r）" % (e,)
    bad = {str(x) for x in (spec.get("not_in") or [])}
    n_bad, missing = 0, 0
    for rid in ids:
        rec = recs.get(str(rid))
        if rec is None or fld not in rec:
            missing += 1
            continue
        v = rec.get(fld)
        vals = v if isinstance(v, list) else ([] if v is None else [v])
        if any(str(x) in bad for x in vals):
            n_bad += 1
    if missing:
        return None, n_bad, "%d 条在快照里查不到／没有 `%s` 字段" % (missing, fld)
    if n_bad:
        return False, n_bad, "%d 条 `%s` 命中 not_in=%s" % (n_bad, fld, sorted(bad))
    return True, 0, "%d 条 `%s` 均不在 %s" % (len(ids), fld, sorted(bad))


def _expected_verdict(act, exp, kind, fs_state=None, fs_bad=0, fs_why="", had_spec=False):
    """一条声明的判定 → `(verdict, residual, is_fewer)`。

    **`filter_assert` 优先于条数**：`only_feishu` 带它时，`act` 只用于展示与回退。
    `fs_state is None`（判不了）⇒ 走原来的计数判据，并把「为什么没按 filter 判」写进 verdict ——
    不许静默回退。
    """
    if kind == "only_feishu" and fs_state is True:
        return ("预期内（**按 filter 逐条复算**：%s）" % fs_why, 0, act < exp)
    if kind == "only_feishu" and fs_state is False:
        return ("**有 %d 条不满足 filter ⇒ 真差异**（%s）" % (fs_bad, fs_why),
                max(1, fs_bad), False)
    resid = max(0, act - exp)
    _na = (" ｜ ⚠️ filter 复算判不了（%s）⇒ **已回退计数**" % fs_why) if had_spec else ""
    if resid:
        return ("**实际多于预期 → 真差异**" + _na, resid, False)
    if act < exp:
        return ("⚠️ 少于预期，请复核声明" + _na, 0, True)
    return ("预期内" + _na, 0, False)


def _selftest():
    """反向对照：`filter_assert` 的四种形状**逐条喂**（不跑对账器、不碰飞书、零网络）。"""
    import tempfile
    ok = fail = 0

    def chk(name, cond, extra=""):
        nonlocal ok, fail
        if cond:
            ok += 1
            print("  ✅ %s %s" % (name, extra))
        else:
            fail += 1
            print("  ❌ %s %s" % (name, extra))

    spec = {"field": "材料审核状态", "not_in": ["通过"]}
    with tempfile.TemporaryDirectory() as t:
        def snap(rows):
            p = os.path.join(t, "x.ndjson")
            with io.open(p, "w", encoding="utf-8") as fh:
                for r in rows:
                    fh.write(json.dumps(r, ensure_ascii=False) + "\n")
            return p

        # ① 全部未审核 ⇒ 声明内；**条数 11 → 12 也不红**（这正是 2026-10-18 打停周更的形状）
        p = snap([{"record_id": "r%d" % i, "材料审核状态": []} for i in range(12)])
        st, nb, why = _judge_by_filter({"snap": p, "ids": ["r%d" % i for i in range(12)]}, spec)
        v, resid, _ = _expected_verdict(12, 11, "only_feishu", st, nb, why, True)
        chk("① 12 条全部未审核 ⇒ 声明内、真差异 0（**条数变了也不红**）",
            st is True and resid == 0 and "按 filter 逐条复算" in v, v)

        # ② 反向对照：有一条 = 通过 ⇒ 必须判真差异（放宽**不许吞掉真差异**）
        p = snap([{"record_id": "r0", "材料审核状态": ["通过"]}]
                 + [{"record_id": "r%d" % i, "材料审核状态": []} for i in range(1, 12)])
        st, nb, why = _judge_by_filter({"snap": p, "ids": ["r%d" % i for i in range(12)]}, spec)
        v, resid, _ = _expected_verdict(12, 11, "only_feishu", st, nb, why, True)
        chk("② 有 1 条「通过」⇒ 必须判**真差异**（吞掉真差异 ⇒ 本条精确变红）",
            st is False and resid >= 1, v)

        # ③ fail-closed：快照缺 / 字段缺 ⇒ 判不了 ⇒ **回退计数**（条数多了照样红）
        st, nb, why = _judge_by_filter({"snap": "/tmp/不存在-%d.ndjson" % os.getpid(),
                                        "ids": ["r0"]}, spec)
        v, resid, _ = _expected_verdict(12, 11, "only_feishu", st, nb, why, True)
        chk("③ 快照读不到 ⇒ 判不了 ⇒ **回退计数**且条数多了仍红（不许放行）",
            st is None and resid == 1 and "已回退计数" in v, v)
        p = snap([{"record_id": "r0"}])                       # 快照里没有该字段
        st, nb, why = _judge_by_filter({"snap": p, "ids": ["r0"]}, spec)
        chk("③b 快照里没有该字段 ⇒ 同样回退计数（无法证明 ≠ 证明干净）", st is None, why)

        # ④ 没写 filter_assert 的声明 ⇒ 行为一个字不变
        v, resid, _ = _expected_verdict(11, 11, "only_feishu")
        chk("④ 无 filter_assert ⇒ 原计数判据不变（11 == 11 ⇒ 预期内、真差异 0）",
            resid == 0 and v == "预期内", v)
        v, resid, _ = _expected_verdict(12, 11, "only_feishu")
        chk("④b 无 filter_assert + 条数多了 ⇒ 仍判真差异（没声明的一律老规矩）", resid == 1, v)

        # ⑤ 对齐器没给 ids 行（老版本 / 解析失败）⇒ 判不了 ⇒ 回退计数
        st, nb, why = _judge_by_filter(None, spec)
        chk("⑤ 对齐器没给 ids 行 ⇒ 判不了 ⇒ 回退计数", st is None, why)
    print("\n自证：通过 %d / 失败 %d" % (ok, fail))
    return 0 if fail == 0 else 1


def main():
    ap = argparse.ArgumentParser(description="L0 层闸门（判定档）")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--selftest", action="store_true",
                    help="反向对照：filter 复算的四种形状逐条喂（不跑对账器、不碰飞书）")
    args = ap.parse_args()
    if args.selftest:
        return _selftest()

    # ---- 1. 跑库内对账器（--check 只读档）
    p = subprocess.run([KBPY, REPORTER, "--check"], cwd=ROOT,
                       capture_output=True, text=True, timeout=900)
    raw = (p.stdout or "") + (p.stderr or "")

    tables, failed, totals, ids_by_table = {}, [], None, {}
    for line in raw.splitlines():
        s = line.strip()
        m = IDS.match(s)
        if m:
            try:
                _d = json.loads(m.group("json"))
            except Exception:                                 # noqa: BLE001
                _d = None
            if isinstance(_d, dict) and _d.get("table"):
                ids_by_table[str(_d["table"])] = _d
            continue
        m = ROW.match(s)
        if m:
            tables[m.group("name")] = {k: int(m.group(k)) for k in ("f", "l", "same", "of", "ol", "ch")}
            continue
        m = FAIL.match(s)
        if m:
            failed.append({"name": m.group("name"), "table_id": m.group("tid")})
            continue
        m = TOTALS.search(line)
        if m:
            totals = {k: int(m.group(k)) for k in ("same", "of", "ol", "ch", "pf")}

    if totals is None:
        print("环境错：读不出对账器的汇总行（对账器可能没跑起来）", file=sys.stderr)
        print(raw[-1500:], file=sys.stderr)
        return 2

    # ---- 2. 读声明
    try:
        doc = load_yaml(EXPECT) or {}
    except Exception as e:
        print("环境错：读不出 %s：%s" % (EXPECT, e), file=sys.stderr)
        return 2
    expected = doc.get("expected") or []

    # ---- 3. 逐条比对：实际 vs 预期
    rows, real_diffs, fewer = [], [], []
    covered = set()          # (table, kind) 已被声明覆盖
    for e in expected:
        tbl, kind = e.get("table"), e.get("kind")
        exp = int(e.get("expected", 0) or 0)
        _spec = e.get("filter_assert")
        _had = isinstance(_spec, dict) and bool(_spec.get("field"))
        fs_state, fs_bad, fs_why = None, 0, ""
        if kind == "only_feishu":
            act = (tables.get(tbl) or {}).get("of", 0)
            # ★ 2026-10-19：有 `filter_assert` ⇒ 判「这几条是否都被 filter 排除」，不再数条数。
            if _had:
                fs_state, fs_bad, fs_why = _judge_by_filter(ids_by_table.get(tbl), _spec)
        elif kind == "pull_failed":
            act = sum(1 for f in failed if f["name"] == tbl)
        else:
            act = 0
        covered.add((tbl, kind))
        verdict, resid, _fewer = _expected_verdict(
            act, exp, kind, fs_state=fs_state, fs_bad=fs_bad, fs_why=fs_why, had_spec=_had)
        rows.append({"id": e.get("id"), "table": tbl, "kind": kind,
                     "actual": act, "expected": exp, "residual": resid,
                     "verdict": verdict, "owner_action": e.get("owner_action", ""),
                     "filter_assert": ("按 filter 复算" if fs_state is not None
                                       else ("判不了→回退计数" if _had else None)),
                     "reason": (e.get("reason") or "").strip()})
        if resid:
            real_diffs.append(rows[-1])
        elif _fewer:
            fewer.append(rows[-1])

    # ---- 4. 有没有**没被声明覆盖**的差异（新表 / 新类目）
    uncovered = []
    for name, t in tables.items():
        if t["of"] and (name, "only_feishu") not in covered:
            uncovered.append("%s：飞书多 %d（**没有声明**）" % (name, t["of"]))
        if t["ol"]:
            uncovered.append("%s：L0多 %d（**不允许豁免**）" % (name, t["ol"]))
        if t["ch"]:
            uncovered.append("%s：值变 %d（**不允许豁免**）" % (name, t["ch"]))
    for f in failed:
        if (f["name"], "pull_failed") not in covered:
            uncovered.append("%s（%s）：拉取失败（**没有声明**）" % (f["name"], f["table_id"]))
    man_unreg = 0
    m = re.search(r"manifest 未登记的 L0 记录文件:\s*(\d+)", raw)
    if m:
        man_unreg = int(m.group(1))
        if man_unreg:
            uncovered.append("manifest 未登记的 L0 记录文件 %d 条（**不允许豁免**）" % man_unreg)

    exp_of = sum(r["actual"] for r in rows if r["kind"] == "only_feishu")
    exp_pf = sum(r["actual"] for r in rows if r["kind"] == "pull_failed")
    n_real = sum(r["residual"] for r in real_diffs) + len(uncovered)
    ok = (n_real == 0)

    # ---- 5. 输出
    _real = sys.stdout
    if args.json:
        sys.stdout = sys.stderr
    if not args.quiet:
        print("=" * 74)
        print("L0 层闸门（判定档） · %s" % ("过" if ok else "**未过**"))
        print("=" * 74)
        print("原始事实（来自 kb/l8/align_l0_feishu.py --check，**不抹掉**）：")
        print("  一致 %d ｜ 飞书多 %d ｜ L0多 %d ｜ 值变 %d ｜ 拉取失败 %d"
              % (totals["same"], totals["of"], totals["ol"], totals["ch"], totals["pf"]))
        print("分类：**预期内 %d**（飞书多 %d + 拉取失败 %d） ｜ **真差异 %d**"
              % (exp_of + exp_pf, exp_of, exp_pf, n_real))
        print()
        print("--- 预期差异声明（kb/l7/registry/l0-expected-diffs.yaml）---")
        for r in rows:
            print("  [%s] %s / %s：实际 %d，预期 %d → %s"
                  % (r["id"], r["table"], r["kind"], r["actual"], r["expected"], r["verdict"]))
            if r["residual"]:
                print("        ↳ 超出预期 %d，**判红**；要人做什么：%s" % (r["residual"], r["owner_action"]))
        if fewer:
            print()
            print("--- ⚠️ 少于预期的声明（请复核，不是错误）---")
            for r in fewer:
                print("  [%s] %s / %s：实际 %d < 预期 %d —— 可能已修好，也可能口径变了"
                      % (r["id"], r["table"], r["kind"], r["actual"], r["expected"]))
        print()
        print("--- 未声明的差异（一律判红，不许预豁免）--- %d 条" % len(uncovered))
        for u in uncovered:
            print("  · %s" % u)
        print()
        print("=" * 74)
        print("结论：%s" % ("✅ 过（真差异 0）" if ok else "❌ 未过（真差异 %d）" % n_real))
        print("退出码：%d" % (0 if ok else 1))

    if args.json:
        sys.stdout = _real
        print(json.dumps({
            "gate": "L0", "ok": ok, "exit_code": 0 if ok else 1,
            "raw": totals,
            "expected_rows": rows,
            "real_diff_total": n_real,
            "uncovered": uncovered,
            "fewer_than_expected": [r["id"] for r in fewer],
        }, ensure_ascii=False, indent=1))

    _rec(ok, n_real, 0)          # run 记录：放在最后，--quiet 也要记（否则等于没接）
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
