#!/usr/bin/env python3
"""audit_sample.py —— 目标 14「每周人工抽检 100 条」（PRD §11.2 第 6 条）。

## 它实现 PRD 什么

| PRD | 逐字 | 本件怎么落 |
|---|---|---|
| **§11.2 保障机制 6** | 「**每周人工抽检 100 条**，评估准确率」 | 抽样 ＋ 出**给人填的**清单 |
| **§11.3 评估方式** | 「**准确率 = 三态结论一致数 / 总审查数**」 | `--score` 用**同一条公式**算人机一致率 |
| **§15 验收** | 「准确率 ｜ 整体 ≥ 90%」 | `--score` 直接给出对照读数 |

## 三条纪律

1. **只读库**：只读 `kb/l7/runs/index.jsonl`；只写 `kb/l7/reports/`。
2. **不替人判**：清单里「人判」「人判理由」「复核人」三列**一律留空**。
   「人工抽检」的**本体就是人判** —— 预填等于把这道工序删掉。已钉判据 ④（反向对照）。
3. **口径写进产物**：分层规则、seed、被排除的计数全部随产物走，换人复算能对上。

## ★ 为什么必须先「同一素材只留最早一次」（这条是实测逼出来的）

`kb/l7/runs/index.jsonl` 里**同一素材会被反复写入**：实测 2026-10-12 一天里，
回归集复跑往 index 写了 **441 条**同名素材的单子（100 条回归素材被跑了多轮）。
不去重的话：

| 三态 | 含重复 | 去重后 |
|---|---|---|
| BLOCK | 51.6% | **41.1%** |
| REVIEW | 34.4% | 42.3% |
| PASS | 13.0% | 14.9% |

⇒ **差 10.5 个百分点**。抽检池会被同一批素材灌满，抽出来的 100 条**不是 100 个独立样本**。

去重口径**照抄回归集自己的**（`regression-set.yaml → meta.dedup_rule` 逐字：
「同一素材（text sha256 前 12 位相同）只留**最早**那份（首判；复判带前一次上下文）」）——
本件按 `trigger` 归一化后的前 60 字做同一个键（index 里 `trigger` **只存 60 字摘要**，见下）。

⚠️ 已知边界：`trigger` 是**截断摘要**（长素材只留 60 字 ＋ `…`）⇒ 键是「前 60 字」而不是全文。
   两个素材前 60 字相同会被误并 —— 实测回归集 100 条素材并出 **70 个键**，
   即**至少有 30 条发生了这种合并**。**这是 index 的形状限制，不是本脚本的选择**；
   要根治得让 `review.py` 记账时多存一个 `text_sha8`。

## 口径分叉（**默认取保守侧**）

| 口径 | 池子 | 适合 | 风险 |
|---|---|---|---|
| **`--dedup`（默认）**：同一素材只留最早 | 实测 1013 → **253** | **准确率**（要独立样本） | 同一素材的多轮送审只算一条 |
| `--no-dedup`：全部审查单 | 1013 | 与 §11.3「**总审查数**」字面一致 | 同一素材反复送审会**重复计数**（最大一组 60 条同一句文案） |

PRD §11.3 的「总审查数」字面是**审查次数**，而准确率要的是**独立样本** —— 两者在
「同一素材被反复送审」时冲突。**默认取 `--dedup`**（保守：宁可样本少，不要样本假）。

## 用法

    python3 kb/l8/audit_sample.py --week 2026-W42          # 出清单（默认就是本周）
    python3 kb/l8/audit_sample.py --week 2026-W42 --n 100
    python3 kb/l8/audit_sample.py --score kb/l7/reports/audit-sample-2026-W42.csv
    python3 kb/l8/audit_sample.py --selftest
"""

from __future__ import annotations

import argparse
import collections
import csv
import datetime as dt
import hashlib
import io
import json
import os
import re
import sys

KB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUNS = os.path.join(KB, "l7", "runs", "index.jsonl")
REPORTS = os.path.join(KB, "l7", "reports")
sys.path.insert(0, os.path.join(KB, ".work"))
import _safe_write                                        # noqa: E402

#: 一单 = 一次评审运行（与 baseline_table.mjs / audit_metrics.mjs **同一口径**）
UNIT_SOURCE = "review_machine"

#: 登记过的污染（沿用 `regression-set.yaml → meta.excluded_patterns` 的两条）
POLLUTION_PATTERNS = (r"^PERF-", r"^TEST")

STATES = ("BLOCK", "REVIEW", "PASS", "NEEDS_INPUT")

#: 清单列 —— 后三列**一律留空**（人判栏；判据 ④ 钉着）
COLUMNS = ["序号", "run_id", "送审时间", "机器结论", "问题数", "送审素材（摘要）",
           "人判", "人判理由", "复核人"]


def _norm_trigger(t) -> str:
    """trigger → 去重键。index 只存 60 字摘要 ⇒ 键就是「归一化后的前 60 字」。"""
    s = re.sub(r"\s+", " ", str(t or "").replace("…", "")).strip()
    return s[:60]


def _state_of(r) -> str:
    v = str(r.get("verdict") or "")
    head = v.split("｜")[0].split("|")[0].strip().upper()
    return head if head in STATES else "其他"


def _n_issues(r) -> str:
    m = re.search(r"issue_count=(\d+)", str(r.get("verdict") or ""))
    return m.group(1) if m else ""


def _week_of(iso: str) -> str:
    try:
        d = dt.date.fromisoformat(str(iso)[:10])
    except Exception:                                     # noqa: BLE001
        return ""
    y, w, _ = d.isocalendar()
    return "%d-W%02d" % (y, w)


def load_population(week: str | None = None, runs_path: str | None = None,
                    dedup: bool = True) -> tuple[list, dict]:
    """返回 (抽检池, 排除账)。**只读**。

    `runs_path` 可注入 —— **为了让自证走真路径**。首版自证在断言里把去重逻辑**重抄了一遍**，
    结果测的是副本：变异 M2（不去重）跑出来 25/25 全绿 ⇒ 那条判据是**恒绿的空转**。
    """
    rows = []
    with open(runs_path or RUNS, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    unit = [r for r in rows if r.get("source") == UNIT_SOURCE]

    ex = collections.Counter()
    keep1 = []
    for r in unit:
        t = str(r.get("trigger") or "")
        if any(re.search(p, t) for p in POLLUTION_PATTERNS):
            ex["污染单（PERF-*/TEST*）"] += 1
            continue
        keep1.append(r)

    # 同一素材只留最早一次（`dedup=False` 可关 —— 见下方「口径分叉」说明）
    groups = collections.defaultdict(list)
    for r in keep1:
        groups[_norm_trigger(r.get("trigger"))].append(r)
    deduped = []
    for _k, g in groups.items():
        g.sort(key=lambda x: (str(x.get("at") or ""), str(x.get("run_id") or "")))
        if dedup:
            deduped.append(g[0])
            ex["同一素材的复跑（丢弃）"] += len(g) - 1
        else:
            deduped.extend(g)
            ex["同一素材的复跑（保留，--no-dedup）"] += len(g) - 1
    deduped.sort(key=lambda x: (str(x.get("at") or ""), str(x.get("run_id") or "")))

    if week:
        deduped = [r for r in deduped if _week_of(r.get("at")) == week]
    return deduped, dict(ex)


def sample(pool: list, n: int) -> tuple[list, dict]:
    """**分层（按三态）× 等距**抽样 —— 完全确定性，不依赖随机数实现。"""
    by = collections.defaultdict(list)
    for r in pool:
        by[_state_of(r)].append(r)
    for k in by:
        by[k].sort(key=lambda x: (str(x.get("at") or ""), str(x.get("run_id") or "")))

    total = len(pool)
    if total == 0:
        return [], {"total": 0, "strata": {}}
    # 按比例分配 + 每层至少 1（再用「最大余额」补到 n）
    quota, rem = {}, []
    for k in STATES:
        L = len(by.get(k, []))
        if L == 0:
            quota[k] = 0
            continue
        exact = n * L / total
        quota[k] = min(L, max(1, int(exact)))
        rem.append((exact - int(exact), k))
    while sum(quota.values()) > n:
        k = max((k for k in STATES if quota[k] > 1), key=lambda k: quota[k], default=None)
        if k is None:
            break
        quota[k] -= 1
    for _f, k in sorted(rem, reverse=True):
        if sum(quota.values()) >= n:
            break
        if quota[k] < len(by.get(k, [])):
            quota[k] += 1

    out = []
    for k in STATES:
        L = by.get(k, [])
        q = quota.get(k, 0)
        if q <= 0 or not L:
            continue
        # 等距：第 i 个取 floor(i*L/q)
        for i in range(q):
            out.append(L[min(len(L) - 1, (i * len(L)) // q)])
    out.sort(key=lambda x: (str(x.get("at") or ""), str(x.get("run_id") or "")))
    return out, {"total": total, "strata": {k: {"pool": len(by.get(k, [])), "picked": quota.get(k, 0)}
                                            for k in STATES if by.get(k)}}


def render_csv(picked: list) -> str:
    """★ `lineterminator="\n"` 是必须的：`csv.writer` 默认 `\r\n`，
    而 `_safe_write` 回读时 universal newlines 把 `\r\n` 读成 `\n`
    ⇒ **每行少 1 字符**，回读复核必失败（实测 9426 → 9325，差 101 = 101 行）。"""
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(COLUMNS)
    for i, r in enumerate(picked, 1):
        w.writerow([i, r.get("run_id"), r.get("at"), _state_of(r), _n_issues(r),
                    _norm_trigger(r.get("trigger")),
                    "", "", ""])          # ★ 人判三列**留空**
    return buf.getvalue()


def score(path: str) -> int:
    """人判填好后算一致率。**口径 = PRD §11.3「准确率 = 三态结论一致数 / 总审查数」**。"""
    with open(path, encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    n = len(rows)
    filled, agree = 0, 0
    bad = []
    per = collections.Counter()
    for r in rows:
        h = str(r.get("人判") or "").strip().upper()
        if not h:
            continue
        if h not in STATES:
            bad.append((r.get("序号"), h))
            continue
        filled += 1
        m = str(r.get("机器结论") or "").strip().upper()
        per[(m, h)] += 1
        if m == h:
            agree += 1
    print("清单元数据：%d 条 ｜ 已填人判 %d 条" % (n, filled))
    if bad:
        print("❌ 人判取值非法 %d 处（只认 %s）：%s" % (len(bad), "/".join(STATES), bad[:5]))
        return 2
    if not filled:
        print("⛔ **还没有人判** —— 抽查记录为空。这不是「通过」，是**未测**（不许按 0 或 100 报）。")
        return 3
    print("★ 准确率（人机三态一致） = %d / %d = **%.4f**（PRD §15 门槛 ≥ 0.90）"
          % (agree, filled, agree / filled))
    print("   备注：本数是**抽检样本**上的读数，不是全量；未填的 %d 条不计入分母。" % (n - filled))
    print("   分布（机器→人判）：%s" % dict(per.most_common()))
    return 0


def _selftest() -> int:
    ok = fail = 0
    fails = []

    def ck(name, cond, detail=""):
        nonlocal ok, fail
        if cond:
            ok += 1
        else:
            fail += 1
            fails.append("%s %s" % (name, detail))

    def mk(i, state, at, trig=None):
        return {"run_id": "R%03d" % i, "at": at, "source": UNIT_SOURCE,
                "verdict": "%s ｜ issue_count=1" % state, "trigger": trig or ("素材%d intro" % i)}

    # ① ★ 走**真路径**（`load_population`）—— 不许在断言里重抄逻辑
    #    （首版就是重抄的 ⇒ 变异 M2「不去重」跑出 25/25 全绿，判据空转）
    import tempfile
    _fix = [mk(1, "BLOCK", "2026-10-01T00:00:00", "same intro"),
            mk(2, "REVIEW", "2026-10-02T00:00:00", "same intro"),
            mk(3, "PASS", "2026-10-03T00:00:00", "other intro"),
            mk(4, "BLOCK", "2026-10-04T00:00:00", "PERF-20261010 selftest")]
    with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False, encoding="utf-8") as fh:
        for r in _fix:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
        _fp = fh.name
    _pool, _ex = load_population(None, _fp)
    os.unlink(_fp)
    ck("① 复跑只留最早", [r["run_id"] for r in _pool] == ["R001", "R003"],
       "得到 %r（应为 R001 首判 ＋ R003 另一素材；R002 是复跑、R004 是污染）" % [r["run_id"] for r in _pool])
    ck("①b 排除账写对", _ex.get("同一素材的复跑（丢弃）") == 1 and _ex.get("污染单（PERF-*/TEST*）") == 1,
       "得到 %r" % _ex)
    pool = _fix

    # ② 污染单被排除
    ck("② PERF-* 认出", any(re.search(p, "PERF-20261010-1") for p in POLLUTION_PATTERNS))
    ck("②b TEST 认出", any(re.search(p, "TESTselftest x") for p in POLLUTION_PATTERNS))
    ck("②c 正常素材不误伤", not any(re.search(p, "FDA approved") for p in POLLUTION_PATTERNS))

    # ③ 三态从 verdict 取值（含分隔符两种写法）
    ck("③ 全角竖线", _state_of({"verdict": "BLOCK ｜ issue_count=2"}) == "BLOCK")
    ck("③b 半角竖线", _state_of({"verdict": "REVIEW | issue_count=0"}) == "REVIEW")
    ck("③c 未知不猜", _state_of({"verdict": "怪东西"}) == "其他")

    # ④ 样本量恰 n、且分层之和 == n
    pop = []
    for i, s in enumerate(["BLOCK"] * 50 + ["REVIEW"] * 30 + ["PASS"] * 15 + ["NEEDS_INPUT"] * 5):
        pop.append(mk(i, s, "2026-10-%02dT00:00:00" % (1 + i % 28)))
    for n in (100, 37, 8):
        picked, meta = sample(pop, n)
        ck("④ n=%d 恰 %d 条" % (n, n), len(picked) == n, "得到 %d" % len(picked))
        ck("④b n=%d 分层之和==n" % n, sum(v["picked"] for v in meta["strata"].values()) == n,
           "得到 %r" % meta["strata"])
        ck("④c n=%d 每层至少 1" % n,
           all(meta["strata"][k]["picked"] >= 1 for k in meta["strata"]), "得到 %r" % meta["strata"])
    # ④d ★ 分层**可复算**：按比例分（允许 ±1 的取整）
    picked, meta = sample(pop, 100)
    for k, v in meta["strata"].items():
        want = 100 * v["pool"] / len(pop)
        ck("④d[%s] 按比例" % k, abs(v["picked"] - want) <= 1.0,
           "抽 %d ／ 应约 %.1f" % (v["picked"], want))

    # ⑤ 确定性：同一池重跑，**逐字节相同**
    a = render_csv(sample(pop, 100)[0])
    b = render_csv(sample(list(reversed(pop)), 100)[0])
    ck("⑤ 与输入顺序无关（逐字节相同）", a == b, "两次渲染不同")

    # ⑥ ★★ 反向对照：**人判三列必须全空**（预填 = 把「人工抽检」这道工序删掉）
    csv_text = render_csv(sample(pop, 100)[0])
    rd = list(csv.DictReader(io.StringIO(csv_text)))
    ck("⑥ 人判栏全空（反向对照）",
       all(not str(r.get("人判") or "").strip() and not str(r.get("人判理由") or "").strip()
           and not str(r.get("复核人") or "").strip() for r in rd),
       "有人判列被预填")
    ck("⑥b 清单列名齐", list(rd[0].keys()) == COLUMNS, "得到 %r" % list(rd[0].keys()))

    # ⑦ 未填人判 ⇒ 不许报 0/100（必须报「未测」）
    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8") as fh:
        fh.write(csv_text)
        p0 = fh.name
    ck("⑦ 未填 ⇒ 退出码 3（未测，不是 0 分）", score(p0) == 3, "score() 未返回 3")
    os.unlink(p0)
    # ⑦b 填一半 ⇒ 分母只算已填
    rd = list(csv.DictReader(io.StringIO(csv_text)))
    for r in rd[:10]:
        r["人判"] = r["机器结论"]
    rd[10]["人判"] = "怪值"
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=COLUMNS)
    w.writeheader()
    w.writerows(rd)
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8") as fh:
        fh.write(buf.getvalue())
        p1 = fh.name
    ck("⑦b 非法人判取值 ⇒ 退出码 2", score(p1) == 2, "score() 未返回 2")
    os.unlink(p1)

    print("audit_sample --selftest：%d/%d" % (ok, ok + fail))
    for f in fails:
        print("  ✗", f)
    return 0 if fail == 0 else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="每周人工抽检 100 条（PRD §11.2-6 / §11.3）")
    ap.add_argument("--week", default=None, help="ISO 周，如 2026-W42；缺省=全部已去重池")
    ap.add_argument("--n", type=int, default=100)
    ap.add_argument("--no-dedup", action="store_true",
                    help="不去重（与 §11.3「总审查数」字面一致；同一素材反复送审会重复计数）")
    ap.add_argument("--score", default=None, help="对填好的清单算人机一致率")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()

    if a.selftest:
        return _selftest()
    if a.score:
        return score(a.score)

    pool, ex = load_population(a.week, dedup=not a.no_dedup)
    picked, meta = sample(pool, a.n)
    if not picked:
        print("⛔ 抽检池为空（week=%s）—— **未测**，不是「0 个问题」。" % a.week)
        return 3

    # ★ tag 必须带上口径 —— 否则 `--no-dedup` 会**覆盖**掉去重版（首版实测踩到）
    tag = (a.week or "ALL") + ("-nodup" if a.no_dedup else "")
    csv_p = os.path.join(REPORTS, "audit-sample-%s.csv" % tag)
    json_p = os.path.join(REPORTS, "audit-sample-%s.json" % tag)
    md_p = os.path.join(REPORTS, "audit-sample-%s.md" % tag)
    _safe_write.write_text(csv_p, render_csv(picked))

    st = collections.Counter(_state_of(r) for r in picked)
    doc = {
        "generated_at": dt.datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "generated_by": "kb/l8/audit_sample.py",
        "prd_ref": "§11.2-6「每周人工抽检 100 条，评估准确率」／§11.3「准确率 = 三态一致数 / 总审查数」",
        "week": tag, "n_requested": a.n, "n_picked": len(picked),
        "population": meta,
        "excluded": ex,
        "picked_by_state": dict(st),
        "unit_rule": "一单 = 一次评审运行（source == review_machine），与 baseline_table/audit_metrics 同口径",
        "dedup_rule": ("同一素材（trigger 归一化后前 60 字）**只留最早一次** —— 照 regression-set.yaml → meta.dedup_rule"
                       if not a.no_dedup else "**未去重**（--no-dedup，与 §11.3「总审查数」字面一致）"),
        "known_limit": "index 的 trigger 只存 60 字摘要（长素材截断＋…）⇒ 键是前 60 字不是全文；"
                       "两个素材前 60 字相同会被误并（实测回归集 100 条并出 70 个键）。"
                       "要根治得让 review.py 记账时多存 text_sha8。",
        "human_columns_are_blank": True,
    }
    _safe_write.write_text(json_p, json.dumps(doc, ensure_ascii=False, indent=1))

    L = ["# 每周人工抽检 · %s（首轮 %d 条）" % (tag, len(picked)), "",
         "- **PRD**：§11.2 第 6 条「每周人工抽检 100 条，评估准确率」",
         "- **清单位置**：`kb/l7/reports/audit-sample-%s.csv` —— 「人判 / 人判理由 / 复核人」**三列留空，等人填**" % tag,
         "- **怎么算**：填完跑 `python3 kb/l8/audit_sample.py --score %s`" % csv_p,
         "  口径 = §11.3「准确率 = 三态结论一致数 / 总审查数」；**一条没填时它报「未测」并退出码 3，不许报 0 或 100**。",
         "",
         "## 抽样口径（随产物走，换人可复算）", "",
         "| 项 | 值 |", "|---|---|",
         "| 一单口径 | 一次评审运行（`source == review_machine`） |",
         ("| 去重 | 同一素材（`trigger` 前 60 字）**只留最早一次** |" if not a.no_dedup
          else "| 去重 | **未去重**（`--no-dedup`）—— 同一素材反复送审会重复计数 |"),
         "| 分层 | 按三态，**按比例**分配，每层至少 1 |",
         "| 层内 | **等距**抽取（确定性，不依赖随机数实现） |",
         "| 抽检池 | %d 条 |" % meta["total"], ""]
    L += ["| 三态 | 池内 | 抽中 |", "|---|---|---|"]
    for k, v in meta["strata"].items():
        L.append("| %s | %d | %d |" % (k, v["pool"], v["picked"]))
    L += ["", "## 被排除的（**不静默**）", "", "| 项 | 条数 |", "|---|---|"]
    for k, v in (ex or {}).items():
        L.append("| %s | %d |" % (k, v))
    L += ["",
          "> ★ 这条去重不是洁癖：实测不去重时 **BLOCK 占比 51.6%、去重后 41.1%（差 10.5 个百分点）** ——",
          "> 抽出来的 100 条会**不是 100 个独立样本**。",
          "",
          "## 已知边界（照实说）", "",
          "- `trigger` 只存 **60 字摘要**（长素材截断 ＋ `…`）⇒ 去重键是「前 60 字」不是全文；",
          "  两个素材前 60 字相同会被误并（实测回归集 100 条并出 **70 个键**）。",
          "  **这是 index 的形状限制**；根治要 `review.py` 记账时多存 `text_sha8`。",
          "- 本件只**抽样与出清单**；「人工」那一步**必须人来做** —— 脚本不替人判。", ""]
    _safe_write.write_text(md_p, "\n".join(L))

    print("抽检池 %d 条（已排除：%s）" % (meta["total"], ex or "无"))
    print("抽中 %d 条：%s" % (len(picked), dict(st.most_common())))
    print("清单（给人填） ：%s" % csv_p)
    print("机读口径       ：%s" % json_p)
    print("摘要           ：%s" % md_p)
    print("★ 「人判 / 人判理由 / 复核人」三列**留空** —— 填完跑 --score。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
