#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""citation_integrity.py — 引用完整性回验：把 §11.2 的 `bad_cite` 变成可量的数。

做一件事：把**评审引擎已经产出的报告**逐条引文重新核一遍 ——
「这条结论引的那段摘录，今天还能在 L0 记录里逐字找到吗？」

## 判据（四桶，不分桶就不叫量过）

对每条引文（`risk_items[].evidence` 的 `anchor` + `excerpt`）：

| 桶 | 含义 |
|---|---|
| `ok` | `verify_excerpt(L0原文, 摘录)` 通过 —— 逐字可回源 |
| `declared_gap` | 验不过，**且报告自己标了 `verbatim_verified=False`** ⇒ 缺口是声明过的 |
| `silent_bad` | 验不过，**报告没标 False**（写了 True，或根本没这个字段）⇒ ★ **真 bad_cite** |
| `unresolvable` | 锚点解析不到 L0 件 —— 这是「**取不到**」，**不算** bad_cite，单列 |
| `no_anchor` | 有摘录但没有锚点 —— 同样单列，不混进 bad_cite |

**为什么非要分「declared_gap」与「silent_bad」**（2026-10-10 实测，本脚本的第一版差点报错）：
`review.py:860-905` 有一处**两条硬闸门撞车的裁决** —— 「红线不得因依据不能逐字回源而降级为消失」。
P0 正则/关键词/等价说法命中时，源侧本来就没有那句逐字原文（如 `\\bpain[\\s-]*(free|less)\\b`、
`boost milk`），引擎**照旧出 BLOCK**，但显式标 `verbatim_verified=False` + `evidence_gap`。
⇒ 那类**不是坏引用，是声明过的缺口**。把它们算进 bad_cite，就会得出
「引用完整性 8.7% 不合格」这种**把已披露的缺口当成隐瞒**的错误结论。
**要量的只有 `silent_bad`** —— 验不过却看不出来，才是真缺陷。

## 一把尺子，不造第二把

判据函数直接复用引擎本体：`review.resolve_anchor()`（锚点 → L0 原文）与
`review.verify_excerpt()`（NFKC + 空白折叠后逐字包含）。
本脚本**只做统计与分桶**，不自己实现比对。

## ★ 两个必须同时设的环境变量（2026-10-10 踩过，血的教训）

1. **`KB_INTERP_OK=1`** —— `review.py:21-40` 有个**解释器守卫**：`KB_INTERP_OK` 未设时，
   它用 `os.execve()` **把自己重新 exec 成脚本**。后果：`import review` 会**跑起整条引擎**
   （`__main__` 守卫被绕过），拿空 `--text` 出一份 `NEEDS_INPUT` 拒答报告、
   写 `kb/l7/reports/` 与 `kb/l7/runs/`、追加 `index.jsonl`。
   —— 我为此污染过活目录，归档在 `kb/l8/_archive/accidental-engine-run-20261010-1413/`。
2. **`KB_ENTRY=selftest`** —— `review.py` 的入口闸门（防线1）在 import 时就拦，
   只认 `KB_ENTRY ∈ {with_kb_evidence, kb_api, selftest}`。

本脚本在 `_import_engine()` 里设好这两个变量再 import，**import 完立刻还原**
（不留副作用给同进程的其它代码）。`selftest` 是闸门**自己文档里写的**参考实现口子。

## 零写入哨兵

评审链的产物目录是活目录。本脚本每次运行前后对 `kb/l7/reports/` 与 `kb/l7/runs/`
**做一次文件清单快照**，两次不一致就**大声失败**（退出码 4）——
让「检查器自己动了活链」这种事**不可能静默发生**。

## 用法

    python3 kb/l8/citation_integrity.py                 # 扫全部引擎报告
    python3 kb/l8/citation_integrity.py --limit 50      # 只扫最近 50 份
    python3 kb/l8/citation_integrity.py --json          # 只输出机读 JSON
    python3 kb/l8/citation_integrity.py --selftest      # 判据自证（不碰真库）
    python3 kb/l8/citation_integrity.py --selftest --mutate=treat-declared-as-silent
                                                        # 变异自证：把已声明缺口误算成静默 ⇒ 必须变红

输出：`kb/l8/citation_integrity_<run_id>.json`（+ stdout 一张 ≤14 行的表）

## 退出码

    0 = 静默 bad_cite 为 0
    1 = 用法/输入错误
    2 = ★ 发现静默 bad_cite
    3 = 没有可核引文（样本为空 —— **不等于通过**）
    4 = 零写入哨兵被触发
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
import time

# ── 解释器守卫：与库内其它脚本同款（合格解释器由 kb/.kb-python 指定）──────────
if not os.environ.get("KB_INTERP_OK"):
    _d = os.path.dirname(os.path.abspath(__file__))
    _cfg = None
    while True:
        _p = os.path.join(_d, ".kb-python")
        if os.path.isfile(_p):
            _cfg = _p
            break
        _q = os.path.dirname(_d)
        if _q == _d:
            break
        _d = _q
    if _cfg:
        _want = next((l.split("#", 1)[0].strip() for l in open(_cfg, encoding="utf-8")
                      if l.split("#", 1)[0].strip()), "")
        _want = os.path.expanduser(_want)
        if (_want and os.access(_want, os.X_OK)
                and os.path.realpath(_want) != os.path.realpath(sys.executable)):
            os.environ["KB_INTERP_OK"] = "1"
            os.execve(_want, [_want, os.path.abspath(__file__)] + sys.argv[1:], dict(os.environ))

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REPORTS = os.path.join(ROOT, "kb", "l7", "reports")
RUNS = os.path.join(ROOT, "kb", "l7", "runs")
ENGINE_DIR = os.path.join(ROOT, "kb", "l7", "skills", "kb-content-review", "scripts")

#: 引用完整性要看的产物：引擎出的报告（含 risk_items[].evidence）。
#: 排除非报告件（aggregate / 每日体检 / 基线 / 索引 / 审计指标），它们没有 risk_items 契约。
#: ★ 2026-10-10 补 `audit-metrics`：`audit_metrics.mjs` 的产物也落在这个目录。
#:   实测它**当时没造成影响**（`audit-metrics-latest.json` 没有 `risk_items` ⇒ 被算成 0 条），
#:   但那是**巧合不是设计** —— 哪天有人给指标产物加个 `risk_items` 字段，
#:   它就会被当成一份报告混进「引文实例」分母，静默污染 bad_cite 率。
#:   所以在这里显式排除：**这个检查器看的是「引擎出的报告」，不是「这个目录里的所有 JSON」**。
_SKIP_PREFIX = ("daily-health", "baseline-", "l0-daily-sync", "index", "audit-metrics",
                # ★ 2026-10-10 补 `perf-`：`perf_report.mjs` 的产物也落这个目录，
                #   同样没有 `risk_items` 契约。**与 audit_metrics.mjs 的排除列表保持同口径。**
                "perf-")


def _import_engine():
    """import 引擎本体复用判据函数 —— **必须先把两个闸门变量设好**（见模块 docstring）。"""
    before = {k: os.environ.get(k) for k in ("KB_INTERP_OK", "KB_ENTRY")}
    os.environ["KB_INTERP_OK"] = "1"     # 绕开 review.py:21 的解释器守卫（否则它会 execve 跑起整条引擎）
    os.environ["KB_ENTRY"] = "selftest"  # 绕开入口闸门（防线1 文档里给参考实现留的口子）
    try:
        if ENGINE_DIR not in sys.path:
            sys.path.insert(0, ENGINE_DIR)
        import review  # noqa: E402
        return review
    finally:
        for k, v in before.items():      # import 完立刻还原，不给同进程留副作用
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _snapshot(dirs):
    """活目录文件清单快照（零写入哨兵用）。只列名字，不读内容。"""
    out = {}
    for d in dirs:
        try:
            out[d] = sorted(os.listdir(d))
        except OSError:
            out[d] = None
    return out


def audit(report_paths, resolve, verify):
    """核心：逐条引文分桶。`resolve`/`verify` 注入，便于 selftest 换假库。"""
    buckets = {"ok": 0, "declared_gap": 0, "silent_bad": 0,
               "unresolvable": 0, "no_anchor": 0}
    silent_rows, declared_rows, unres_rows = [], [], []
    seen = set()
    n_rep = n_cit = 0
    errors = []

    for p in report_paths:
        try:
            with open(p, encoding="utf-8") as fh:
                d = json.load(fh)
        except Exception as exc:                     # 一份坏报告不能打死整轮
            errors.append({"report": p, "where": "load", "err": repr(exc)})
            continue
        if not isinstance(d, dict):
            continue
        n_rep += 1
        items = d.get("risk_items")
        if not isinstance(items, list):
            continue
        for it in items:
            if not isinstance(it, dict):
                continue
            ev = it.get("evidence")
            if not isinstance(ev, dict):
                continue
            excerpt, anchor = ev.get("excerpt"), ev.get("anchor")
            if not isinstance(excerpt, str) or not excerpt:
                continue
            n_cit += 1
            if (anchor, excerpt) in seen:            # 同一引文重复出现只算一次
                continue
            seen.add((anchor, excerpt))
            if not isinstance(anchor, str) or not anchor:
                buckets["no_anchor"] += 1
                continue
            try:
                src = resolve(anchor, ev.get("source_sha256"))
            except Exception as exc:
                errors.append({"report": p, "where": "resolve", "anchor": anchor, "err": repr(exc)})
                continue
            if not src:
                buckets["unresolvable"] += 1
                unres_rows.append({"anchor": anchor, "excerpt": excerpt[:60], "report": os.path.basename(p)})
                continue
            if verify(src.get("verbatim", ""), excerpt):
                buckets["ok"] += 1
                continue
            # 验不过 —— 关键二分：报告自己标了 False 吗？
            # 只认**显式 False**；缺字段 / 写了 True / 写了别的，一律算静默。
            if it.get("verbatim_verified") is False:
                buckets["declared_gap"] += 1
                declared_rows.append({"anchor": anchor, "excerpt": excerpt[:60],
                                      "article_no": it.get("article_no") or ev.get("article_no"),
                                      "gap": str(it.get("evidence_gap"))[:120],
                                      "report": os.path.basename(p)})
            else:
                buckets["silent_bad"] += 1
                silent_rows.append({"anchor": anchor, "excerpt": excerpt[:60],
                                    "l0_verbatim": str(src.get("verbatim"))[:60],
                                    "report_claimed_verified": it.get("verbatim_verified", "<字段缺失>"),
                                    "article_no": it.get("article_no") or ev.get("article_no"),
                                    "report": os.path.basename(p)})

    total = sum(buckets.values())
    return {"reports_scanned": n_rep, "citations": n_cit, "unique_citations": total,
            "buckets": buckets, "silent_bad": silent_rows,
            "declared_gap": declared_rows, "unresolvable": unres_rows,
            "errors": errors}


def _shape_of(basename):
    """按产物形态归类 —— 只描述文件名，**不做排除**（排除就是拿答案调尺子）。

    引擎报告契约形态 = `<run>.json`；带后缀的（如 `-aggregate.decision`）是另一类产物。
    """
    stem = basename[:-5] if basename.endswith(".json") else basename
    m = re.match(r"^\d{8}-\d{4,6}(.*)$", stem)
    suffix = m.group(1) if m else None
    if suffix == "":
        return "引擎报告 <run>.json"
    if suffix is None:
        return "非 <run> 形态"
    return f"其它产物 <run>{suffix}"


# ────────────────────────── 自证 ──────────────────────────
def _selftest(mutate=None):
    """判据自证：在临时假库上验四桶 + 变异自证。绝不碰真库。"""
    import tempfile
    import shutil

    fails, checks = [], 0
    tmp = tempfile.mkdtemp(prefix="kb-cit-")
    try:
        # 假 L0：一条真记录，字段「命中片段」= "pain-free claim"
        recdir = os.path.join(tmp, "kb", "l0", "records", "假表")
        os.makedirs(recdir)
        with open(os.path.join(recdir, "recAAA.json"), "w", encoding="utf-8") as fh:
            json.dump({"record_id": "recAAA", "source_table": "假表",
                       "fields": {"命中片段": {"value": "pain-free claim"}}}, fh, ensure_ascii=False)

        def _resolve(anchor, sha):
            if not isinstance(anchor, str) or not anchor.startswith("#"):
                return None
            parts = anchor[1:].split("/")
            if len(parts) < 3:
                return None
            table, rec, field = parts[0], parts[1], "/".join(parts[2:])
            fp = os.path.join(tmp, "kb", "l0", "records", table, f"{rec}.json")
            if not os.path.isfile(fp):
                return None
            recj = json.load(open(fp, encoding="utf-8"))
            f = (recj.get("fields") or {}).get(field)
            if f is None:
                return None
            return {"verbatim": str(f.get("value"))}

        def _verify(verbatim, excerpt):
            v, e = " ".join(verbatim.split()), " ".join(excerpt.split())
            return bool(e) and e in v

        # 四桶各一条 + 一条故意「验不过却声称 True」的静默坏引用
        rep = {
            "risk_items": [
                {"verbatim_verified": True, "evidence": {"anchor": "#假表/recAAA/命中片段",
                                                         "excerpt": "pain-free"}},          # ok
                {"verbatim_verified": False, "evidence_gap": "regex 命中，源侧无逐字原文",
                 "evidence": {"anchor": "#假表/recAAA/命中片段", "excerpt": "\\bpain\\b"}},  # declared_gap
                {"verbatim_verified": True, "evidence": {"anchor": "#假表/recAAA/命中片段",
                                                         "excerpt": "boost milk"}},         # ★ silent_bad
                {"verbatim_verified": True, "evidence": {"anchor": "#假表/recZZZ/命中片段",
                                                         "excerpt": "x"}},                  # unresolvable
                {"verbatim_verified": True, "evidence": {"anchor": "", "excerpt": "y"}},    # no_anchor
                {"verbatim_verified": True, "evidence": {"anchor": "#假表/recAAA/命中片段",
                                                         "excerpt": "pain-free"}},          # 去重（与第 1 条同）
            ]
        }
        rp = os.path.join(tmp, "r.json")
        with open(rp, "w", encoding="utf-8") as fh:
            json.dump(rep, fh, ensure_ascii=False)

        res = audit([rp], _resolve, _verify)
        b = res["buckets"]

        def chk(name, cond):
            nonlocal checks
            checks += 1
            if not cond:
                fails.append(name)

        expect_silent = 0 if mutate == "treat-declared-as-silent" else 1
        if mutate == "treat-declared-as-silent":
            # 变异：把「已声明缺口」也算成静默 —— 自证必须对此变红。
            b = dict(b)
            b["silent_bad"] += b["declared_gap"]

        chk("① ok 恰好 1（逐字可回源）", b["ok"] == 1)
        chk("② declared_gap 恰好 1（报告自标 False）", b["declared_gap"] == 1)
        chk("③ silent_bad 恰好 1（验不过却声称 True）", b["silent_bad"] == expect_silent)
        chk("④ unresolvable 恰好 1（锚点解不到）", b["unresolvable"] == 1)
        chk("⑤ no_anchor 恰好 1", b["no_anchor"] == 1)
        chk("⑥ 去重生效：unique = 5 而非 6", res["unique_citations"] == 5)
        chk("⑦ citations 计数含重复 = 6", res["citations"] == 6)
        chk("⑧ 解析异常 0", res["errors"] == [])
        chk("⑨ silent_bad 明细带 L0 原文与报告自述值",
            bool(res["silent_bad"]) and "l0_verbatim" in res["silent_bad"][0]
            and res["silent_bad"][0]["report_claimed_verified"] is True)
        chk("⑩ declared_gap 明细带 evidence_gap 原话",
            bool(res["declared_gap"]) and "regex" in res["declared_gap"][0]["gap"])
        chk("⑪ 缺 verbatim_verified 字段 ⇒ 算静默（不许当已声明放行）",
            _count_missing_as_silent(_resolve, _verify))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print(f"[citation_integrity --selftest] {'变异 ' + mutate + ' ｜ ' if mutate else ''}"
          f"{checks - len(fails)}/{checks} 通过")
    for f in fails:
        print(f"  ✗ {f}")
    if mutate == "treat-declared-as-silent":
        print("  （变异模式：期望的『红』就是上面那几条 —— 报红才算自证成功）")
    return 1 if fails else 0


def _count_missing_as_silent(resolve, verify):
    """子判据：报告**没有** `verbatim_verified` 字段时，验不过必须算静默。"""
    import tempfile
    tmp = tempfile.mkdtemp(prefix="kb-cit2-")
    try:
        rp = os.path.join(tmp, "r.json")
        with open(rp, "w", encoding="utf-8") as fh:
            json.dump({"risk_items": [{"evidence": {"anchor": "#假表/recAAA/命中片段",
                                                    "excerpt": "boost milk"}}]}, fh, ensure_ascii=False)
        res = audit([rp], resolve, verify)
        return res["buckets"]["silent_bad"] == 1 and res["buckets"]["declared_gap"] == 0
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


# ────────────────────────── 主流程 ──────────────────────────
def main(argv=None):
    ap = argparse.ArgumentParser(description="引用完整性回验（§11.2 bad_cite）")
    ap.add_argument("--reports", default=REPORTS, help="报告目录（默认 kb/l7/reports）")
    ap.add_argument("--limit", type=int, default=0, help="只扫最近 N 份（0=全部）")
    ap.add_argument("--since", default=None, metavar="YYYY-MM-DD",
                    help="只看该日（含）之后写出的报告 —— **显式收窄口径，不改判据**。"
                         "用于把「历史遗留产物」与「当前引擎产出」分开报，而不是把它们排除掉")
    ap.add_argument("--json", action="store_true", help="只输出机读 JSON")
    ap.add_argument("--no-write", action="store_true", help="不落盘报告")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--mutate", default=None, choices=["treat-declared-as-silent"])
    a = ap.parse_args(argv)

    if a.selftest:
        return _selftest(a.mutate)

    review = _import_engine()

    paths = sorted(glob.glob(os.path.join(a.reports, "*.json")))
    paths = [p for p in paths if not os.path.basename(p).startswith(_SKIP_PREFIX)]
    if a.since:
        cut = time.mktime(time.strptime(a.since, "%Y-%m-%d"))
        paths = [p for p in paths if os.path.getmtime(p) >= cut]
    if a.limit:
        paths = sorted(paths, key=os.path.getmtime)[-a.limit:]

    # ★ 零写入哨兵：跑之前快照
    guard_dirs = [os.path.join(ROOT, "kb", "l7", "reports"), RUNS]
    before = _snapshot(guard_dirs)

    res = audit(paths, review.resolve_anchor, review.verify_excerpt)

    after = _snapshot(guard_dirs)
    if before != after:
        changed = [d for d in guard_dirs if before.get(d) != after.get(d)]
        print("!! 零写入哨兵被触发：本检查器动了活目录（这不是检查结果，是缺陷）", file=sys.stderr)
        for d in changed:
            b, af = set(before.get(d) or []), set(after.get(d) or [])
            print(f"   {d}: 新增 {sorted(af - b)} ｜ 消失 {sorted(b - af)}", file=sys.stderr)
        return 4

    b = res["buckets"]
    den = b["ok"] + b["silent_bad"] + b["declared_gap"]
    res["bad_cite_rate_silent"] = round(b["silent_bad"] / den, 4) if den else None
    res["bad_cite_rate_incl_declared"] = round((b["silent_bad"] + b["declared_gap"]) / den, 4) if den else None
    res["run_id"] = time.strftime("%Y%m%d-%H%M%S")
    res["generated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    res["interpreter"] = sys.executable
    res["reports_dir"] = a.reports
    res["since"] = a.since
    # 静默坏引用按**产物形态**归类（只描述，不排除）
    shapes = {}
    for r in res["silent_bad"]:
        k = _shape_of(r["report"])
        shapes.setdefault(k, []).append(r["report"])
    res["silent_bad_by_shape"] = {k: {"n": len(v), "reports": sorted(set(v))[:6]} for k, v in shapes.items()}
    res["verdict"] = ("PASS（无静默坏引用）" if b["silent_bad"] == 0 and den
                      else ("FAIL（存在静默坏引用）" if b["silent_bad"] else "无样本（不等于通过）"))

    if not a.no_write:
        out = os.path.join(ROOT, "kb", "l8", f"citation_integrity_{res['run_id']}.json")
        with open(out, "w", encoding="utf-8") as fh:
            json.dump(res, fh, ensure_ascii=False, indent=1)
        res["report_path"] = out

    if a.json:
        print(json.dumps(res, ensure_ascii=False, indent=1))
    else:
        print(f"引用完整性回验 ｜ 扫 {res['reports_scanned']} 份报告 ｜ 引文实例 {res['citations']} ｜ 去重 {res['unique_citations']}")
        print(f"  逐字可回源      ok            {b['ok']}")
        print(f"  已声明缺口      declared_gap  {b['declared_gap']}   （报告自标 verbatim_verified=False，非缺陷）")
        print(f"  ★ 静默坏引用    silent_bad    {b['silent_bad']}   ← 只有这个数才是 §11.2 的 bad_cite")
        print(f"  锚点解不到 L0   unresolvable  {b['unresolvable']}   （取不到 ≠ 坏引用，单列不并入）")
        print(f"  无锚点          no_anchor     {b['no_anchor']}")
        print(f"  静默 bad_cite 率 = {res['bad_cite_rate_silent']} ｜ 含已声明的缺口 = {res['bad_cite_rate_incl_declared']}")
        if res.get("since"):
            print(f"  口径：只看 {res['since']} 之后写出的报告")
        for k, v in res["silent_bad_by_shape"].items():
            print(f"  静默坏引用形态：{k} —— {v['n']} 条，例：{', '.join(v['reports'][:3])}")
        print(f"  结论：{res['verdict']}")
        if res.get("report_path"):
            print(f"  落盘：{os.path.relpath(res['report_path'], ROOT)}")
        for r in res["silent_bad"][:4]:
            print(f"    ✗ {r['anchor']} ｜ 摘录 {r['excerpt']!r} ｜ 报告自述 {r['report_claimed_verified']}")
        for r in res["declared_gap"][:2]:
            print(f"    · 已声明：{r['anchor']} ｜ {r['gap'][:70]}")

    if not den:
        return 3
    return 2 if b["silent_bad"] else 0


if __name__ == "__main__":
    sys.exit(main())
