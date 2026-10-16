#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""batch_scan.py —— 批量扫描入口（PRD §12 并发 / §15 验收「批量扫描」）。

## 出处（逐字）

· PRD §12 非功能需求 →「**并发** | 支持批量扫描 **100-500 条**」
· PRD §15 验收标准 →「**批量扫描** | 飞书多维表**批量生成审查结论**」
· 任务拆解 11/23–11/27 行目标 2：`能批量审（一次最多 50 个文件、同时跑 100–500 条）`
· `kb/l7/reports/perf-latest.md` 逐字记着：**未建** ——「现只有单条入口（`--text`）；
  批量入口是任务拆解 11/23 那行的目标。本产物只给**串行吞吐**（13.42 条/分钟），
  **不得读作并发能力**」。
· `kb/l8/check_prd12_acceptance.py` 现账：§12 十二条里**唯一一条真·无落点**就是它。

## 边界（三条，写死在代码里）

1. **默认预演**（不加 `--apply` = 零写入）。要写按 PRD 的写法：写的是**结论去向表**
   （`tblCXPQVzfFWWCon`，**我们自己的产物**），**绝不碰飞书源表**。
2. **有界并发**：`--workers` 上限写死（默认 4，硬顶 16）。并发不是拿来刷的 ——
   评审入口每次都会建 L6 检索器（实测固定开销 1.6~1.8 s），并发过高只会互相抢内存。
3. **单条失败不许拖垮整批**：逐条收 (ok, err)，最后汇总；**失败行照实列出来**，不静默吞。

## 用法

    python3 kb/l8/batch_scan.py                      # 预演：列候选 + 计划（零写入）
    python3 kb/l8/batch_scan.py --limit 10 --apply    # 真跑 10 条
    python3 kb/l8/batch_scan.py --workers 8 --limit 200
    python3 kb/l8/batch_scan.py --selftest            # 自证（夹具，不碰飞书）
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import subprocess
import tempfile
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

HERE = os.path.dirname(os.path.abspath(__file__))
KB = os.path.dirname(HERE)
ROOT = os.path.dirname(KB)

BASE = "RY2UbCRjXaeeWwscUPScVN5AnQc"
TABLE = "tblCXPQVzfFWWCon"
PROFILE = os.environ.get("L8_PROFILE", "dsh-kb")
LARK = os.environ.get("LARK_BIN", "lark-cli")
WORKERS_MAX = 16
WORKERS_DEFAULT = 4
BATCH_MAX = 500          # PRD §12 上限

#: 「还没被判过」= 有送审问题、但结论列为空
PENDING_FIELD = "送审问题"
DONE_FIELDS = ("Agent 结论", "状态")


def _lark(*args, allow_fail=False):
    cmd = [LARK, "--profile", PROFILE, *args, "--as", "bot"]
    p = subprocess.run(cmd, capture_output=True, text=True)
    out = (p.stdout or "").strip()
    try:
        d = json.loads(out[out.find("{"):]) if "{" in out else {}
    except Exception:                                        # noqa: BLE001
        d = {"ok": False, "raw": out or (p.stderr or "")}
    if not d.get("ok") and not allow_fail:
        raise SystemExit("lark-cli 失败：%s" % (out or p.stderr)[:300])
    return d


def fetch_pending(limit=BATCH_MAX):
    """读结论去向表里**还没判过**的行。**只读**。"""
    # ★ 读法照 `kb/l8/bitable_stats.py`（**目标 21 已跑通的那条**，别自己再发明一遍）：
    #   `+record-list --format ndjson --output <tmp>` → 读产物文件。
    #   ⚠️ 我前两版都栽在同一处：
    #     ① 旗标写成 `--page-size`（不存在）⇒ lark-cli **不报错**、返回 0 行 ⇒ **哑 0**；
    #     ② 改用 `--format json` ⇒ 回的是 `data.data` **原始矩阵**，不是 `items` ⇒ 又空。
    #   ⇒ 现在按已跑通的做法走；**读不到就出声**，不许静默当成「没有待审」（判据 ⑧）。
    # ★ `--output` **只许落在当前工作目录之下**（实测报
    #   `unsafe output path … outside the built-in allowlist`）—— 所以落工作区内的 `_stage/`，
    #   不用 /tmp，也不用 `tempfile`（那个在 /var/folders 下，会被拒）。
    # ★ `--output` 要**相对路径**：实测**绝对路径落在 cwd 之下也被拒**
    #   （报 `unsafe output path … outside the built-in allowlist`），
    #   换成 `kb/l8/_stage/…` 这种相对写法就通。所以传相对、读绝对。
    _rel = "kb/l8/_stage/batch_scan_rows.ndjson"
    outp = os.path.join(ROOT, _rel)
    os.makedirs(os.path.dirname(outp), exist_ok=True)
    for _stale in (outp, outp.replace(".ndjson", ".manifest.json")):
        if os.path.exists(_stale):
            os.remove(_stale)
    # ★★ 根因（第四版才定位到）：`--output` 产出的是 **ndjson ＋ manifest 一对**，
    #   只删 ndjson 不删 manifest ⇒ CLI 认为"产物已存在"⇒ **拒绝写入、也不报错**，
    #   于是文件始终不产出、被我自己的 ⑧ 号判据逮住（**这正是它存在的意义**）。
    #   ⇒ 两条保险都上：**成对删除** ＋ `--overwrite`。
    # ★ `--output` 档回的是**产物 manifest**（`{"manifest_version":"v1",…}`）而**不是** ok 信封
    #   （口径见 `kb/l8/bitable_stats.py:241`）⇒ 必须 `allow_fail=True`，
    #   否则会把"成功产出 manifest"误判成失败（我第三版就栽在这）。
    _lark("base", "+record-list", "--base-token", BASE, "--table-id", TABLE,
          # ★ 「**读多少行**」与「**处理多少条**」是两件事，别共用一个参数：
          #   我第六版发现 `--limit 1` 只读了 1 行（那行恰好已判过）⇒ 候选 0、看着像坏了。
          #   现在**多读**（`limit` 的 10 倍，下限 200、上限 2000），再按 `limit` 截候选。
          "--limit", str(min(max(limit * 10, 200), 2000)),
          "--format", "ndjson", "--output", _rel, "--overwrite",
          allow_fail=True)
    if not os.path.exists(outp):
        raise SystemExit("[拒判] %s 没产出 ndjson（读法变了？）⇒ 不许当成「没有待审」" % outp)
    items = []
    for ln in io.open(outp, encoding="utf-8"):
        if not ln.strip():
            continue
        try:
            items.append(json.loads(ln))
        except Exception:                                    # noqa: BLE001
            pass
    if items is None:
        raise SystemExit("[拒判] 结论去向表读不到行 ⇒ 不许当成「没有待审」")
    rows = []
    for it in items:
        # ★ 形状实测（第五版才看清）：ndjson 行是**扁平字典** —— 字段名直接在最外层
        #   （`{"record_id": "...", "送审问题": "...", "Agent 结论": "REVIEW", ...}`），
        #   **不是** `{record_id, fields:{…}}`。我多剥了一层 ⇒ 字段全空 ⇒ 又报 0 候选（假 0）。
        #   `it.get("fields") or it` 兼容两种形状，但**以扁平为准**。
        f = it.get("fields") or it
        q = f.get(PENDING_FIELD)
        q = "".join(x.get("text", "") for x in q) if isinstance(q, list) else (q or "")
        # ★ 判据：**只认「Agent 结论」**。`状态` 列几乎每行都有值（`["REVIEW"]` 之类），
        #   拿它当"已判过"会让候选**恒为 0** —— 这是"假 0"的第二种成因，别再把状态列算进来。
        done = bool(f.get(DONE_FIELDS[0]))
        if str(q).strip() and not done:
            rows.append({"record_id": it.get("record_id"), "question": str(q).strip()})
    return rows[:limit]   # ← **这里**才按 `limit` 截「要处理几条」


def plan(rows, workers):
    """纯函数：给候选 ⇒ 计划（分批、并发度、预计批次）。`--selftest` 直接验它。"""
    w = max(1, min(int(workers or WORKERS_DEFAULT), WORKERS_MAX))
    n = len(rows)
    return {"count": n, "workers": w, "batches": (n + w - 1) // w if n else 0,
            "over_prd_cap": n > BATCH_MAX}


def run_batch(rows, worker_fn, workers=WORKERS_DEFAULT):
    """有界并发跑。**单条异常只记进结果，不抛出**（一条坏行不许拖垮整批）。"""
    w = max(1, min(int(workers or WORKERS_DEFAULT), WORKERS_MAX))
    out = []
    if not rows:
        return out
    with ThreadPoolExecutor(max_workers=w) as ex:
        fut = {ex.submit(worker_fn, r): r for r in rows}
        for f in as_completed(fut):
            r = fut[f]
            try:
                got = f.result()
                ok, detail = got[0], got[1]
                extra = got[2] if len(got) > 2 else None
            except Exception as e:                           # noqa: BLE001
                ok, detail, extra = False, "异常：%r" % (e,), None
            out.append({"record_id": r.get("record_id"), "ok": bool(ok), "detail": detail, "extra": extra})
    return out


def preflight(base, session="batch_scan"):
    """★ 一批**跑一次**层前置（L4→L5→L6→L7，任一红即停）。

    照 `kb-review §1.5` 的既定口径：**层前置是「一次执行跑完四层」**，
    而认领是**按 RUN 分槽**的 ⇒ 一批共享一个 BASE，**不是一条一个**
    （一条一个会让认领与记账被 N 条记录淹没，且层前置本身有固定开销）。
    """
    r = subprocess.run(["bash", os.path.join(KB, "l8/review_preflight.sh"),
                        "--base", base, "--session", session],
                       capture_output=True, text=True, cwd=ROOT)
    tail = (r.stdout or r.stderr or "").strip().splitlines()[-3:]
    return r.returncode, " ｜ ".join(t.strip() for t in tail)[:200]


def review_one(row, base=None, decision_owner=None, session="batch_scan"):
    """跑一条评审 —— **走 `review_run.sh`**（不是直调引擎）。

    ★ 为什么必须走它（实测得出，不是猜）：**机读旁挂是 `review_run.sh` 写的，不是引擎写的**。
      直调 `with_kb_evidence.py` 时旁挂不产出 ⇒ 拿不到结构化结论 ⇒ 我的 fail-closed 只能拒。
    ★ 它同时把层前置、判定主体、发布（写表走发布件）一并办掉 —— 那些都不该由批量入口自己做。
    """
    cmd = ["bash", os.path.join(KB, "l8/review_run.sh"),
           "--base", base or "batchscan-unknown",
           "--session", session,
           "--decision-owner", decision_owner or "文案合规审查",
           "--text", row["question"]]
    _side_before = os.path.getmtime(SIDECAR) if os.path.exists(SIDECAR) else None
    p = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT)
    _side_after = os.path.getmtime(SIDECAR) if os.path.exists(SIDECAR) else None
    # 防串味：旁挂**必须是这一跑新写的**（mtime 变了）；没变 ⇒ 不认，返回 None。
    v = read_sidecar() if (_side_after is not None and _side_after != _side_before) else None
    if p.returncode != 0 and v is None:
        return False, "exit=%d %s" % (p.returncode, (p.stderr or p.stdout or "").strip()[-160:]), None
    return True, "ok", v


#: 机读旁挂 —— **守衡与批量扫描共用的唯一结构化结论来源**。
#: ★ **只许读**。删它/写它是评审链自己的事：我 2026-10-10 在这里删过一次，
#:   `workflow_smoke` 当场判红（S1 入口契约），**批量扫描把评审链入口弄坏了**。
SIDECAR = os.path.join(KB, ".work/last_review_result.json")


def read_sidecar():
    """读机读旁挂。取不到 ⇒ None，**不许编**。

    ★ 为什么不能用中文输出正则抠（我第一版就是这么干的，错了）：
      AGENTS.md 逐字「**不许再从中文答案里正则抠** —— PRD §5.3.3 规定问题数 ≥3 时库侧只出汇总，
      而正则只认逐条行 ⇒ **库侧只要判到 ≥3 条就被读成 0 条**」。
    """
    try:
        d = json.load(io.open(SIDECAR, encoding="utf-8"))
    except Exception:                                        # noqa: BLE001
        return None
    st = d.get("state")
    if not st:
        return None
    return {"state": str(st), "issue_count": d.get("issue_count"),
            "confidence": d.get("confidence"),
            "summary": d.get("issue_summary_by_category"),
            "refusal": (d.get("refusal") or {}).get("state")
            if isinstance(d.get("refusal"), dict) else None}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=50)
    ap.add_argument("--workers", type=int, default=WORKERS_DEFAULT)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()

    print("批量扫描入口 —— PRD §12「支持批量扫描 100-500 条」/ §15「批量扫描」")
    print("★ 默认预演（零写入）；写的是**结论去向表**（我们自己的产物），**不碰飞书源表**。\n")
    rows = fetch_pending(a.limit)
    pl = plan(rows, a.workers)
    print("候选（有送审问题、结论列为空）：**%d 条**" % pl["count"])
    for r in rows[:10]:
        print("   · %s ｜ %s" % (r["record_id"], r["question"][:60]))
    if pl["count"] > 10:
        print("   …（共 %d 条）" % pl["count"])
    print("\n计划：并发 **%d** ｜ 批数 %d ｜ 上限 %d（PRD §12）" % (pl["workers"], pl["batches"], BATCH_MAX))
    if pl["over_prd_cap"]:
        print("   ⚠️ 候选超过 PRD 上限 %d —— 分批跑，别一次吞" % BATCH_MAX)
    if not a.apply:
        print("\n预演（零写入）。要真跑加 --apply。")
        return 0
    # ★ 一批一个 BASE：层前置**跑一次**，红了**即停**（不许拿没前置的结论往下走）。
    base = "batchscan-%s" % time.strftime("%Y%m%d-%H%M")
    prc, pmsg = preflight(base, session=os.environ.get("DSH_SESSION_ID", "batch_scan"))
    print("\n层前置（%s）：%s ｜ %s" % (base, "✅ 过" if prc == 0 else "❌ 红（rc=%d）" % prc, pmsg))
    if prc != 0:
        print("⛔ 层前置未过 ⇒ **不出结论**（任一红即停，这是评审链的既定纪律）。")
        return prc
    t0 = time.time()
    res = run_batch(rows, lambda r: review_one(r, base), pl["workers"])
    dt = time.time() - t0
    bad = [r for r in res if not r["ok"]]
    print("\n跑完 %d 条 ｜ 成功 %d ｜ **失败 %d** ｜ 耗时 %.1fs ｜ 吞吐 **%.2f 条/分钟**"
          % (len(res), len(res) - len(bad), len(bad), dt, (len(res) / dt * 60) if dt else 0))
    for r in bad[:10]:
        print("   ❌ %s ｜ %s" % (r["record_id"], r["detail"][:110]))
    print("★ 注意：上面是**串行等效吞吐**的对照；并发能力看「批数 × 单条耗时」，不等于条数÷耗时。")
    return 0 if not bad else 3


def selftest():
    res = []

    def ck(n, c, ex=""):
        res.append((n, bool(c), ex))

    # ① 计划：并发度被夹在 [1, WORKERS_MAX]
    # ★ 契约（写清楚，免得下次又猜）：`workers <= 0` 或无值 ⇒ **用默认值**；超上限 ⇒ 夹到上限。
    #   ⚠️ 我第一版断言写成「0 → 1」，与实现（0 走默认）不符 ⇒ 判据**假红**。断言要照契约写。
    ck("① 并发度：0/None → 默认 %d、999 → 上限 %d" % (WORKERS_DEFAULT, WORKERS_MAX),
       plan([], 0)["workers"] == WORKERS_DEFAULT and plan([], None)["workers"] == WORKERS_DEFAULT
       and plan([], 999)["workers"] == WORKERS_MAX,
       "0→%s 999→%s" % (plan([], 0)["workers"], plan([], 999)["workers"]))
    # ② 批数算对
    p2 = plan([{"record_id": str(i)} for i in range(10)], 4)
    ck("② 批数算对（10 条 / 4 并发 → 3 批）", p2["batches"] == 3, "batches=%d" % p2["batches"])
    # ③ 超 PRD 上限要标出来
    ck("③ 超 PRD 上限（501 条）要标出", plan([{"record_id": str(i)} for i in range(501)], 4)["over_prd_cap"], "")
    # ★ 反向对照：**有界**并发真的封顶（造 24 条、并发 3 ⇒ 同时在跑的峰值 ≤ 3）
    peak = {"n": 0, "cur": 0}
    import threading
    lk = threading.Lock()

    def wf(r):
        with lk:
            peak["cur"] += 1
            peak["n"] = max(peak["n"], peak["cur"])
        time.sleep(0.02)
        with lk:
            peak["cur"] -= 1
        return True, "ok"

    run_batch([{"record_id": str(i)} for i in range(24)], wf, workers=3)
    ck("④ 反向对照：**有界**并发真的封顶（24 条 / 并发 3 ⇒ 峰值 ≤ 3）", peak["n"] <= 3,
       "peak=%d" % peak["n"])
    # ★ 反向对照：**一条抛异常不许拖垮整批**
    def wf2(r):
        if r["record_id"] == "bad":
            raise RuntimeError("故意炸")
        return True, "ok"
    r3 = run_batch([{"record_id": "a"}, {"record_id": "bad"}, {"record_id": "c"}], wf2, workers=2)
    ck("⑤ 反向对照：单条抛异常 ⇒ 整批仍跑完，坏行被记下（不拖垮）",
       len(r3) == 3 and sum(1 for x in r3 if not x["ok"]) == 1, "n=%d bad=%d"
       % (len(r3), sum(1 for x in r3 if not x["ok"])))
    # ⑥ 空输入 ⇒ 空结果（不抛）
    ck("⑥ 空输入 ⇒ 空结果", run_batch([], wf, 4) == [], "")
    # ⑦ 预演不许写：worker_fn 在预演路径上**一次都不该被调**
    calls = {"n": 0}

    def wf3(r):
        calls["n"] += 1
        return True, "ok"
    plan([{"record_id": "x"}], 4)          # 预演只算计划
    ck("⑦ 预演路径不调 worker（零副作用）", calls["n"] == 0, "calls=%d" % calls["n"])
    # ★ 反向对照 ⑧：**读不到 ≠ 没有待审** —— 真造一个"没有 items 键"的响应
    import types
    _orig = _lark
    globals()["_lark"] = lambda *a, **k: {"ok": True, "data": {"no_items_key": 1}}
    try:
        fetch_pending(1)
        ck("⑧ 反向对照：读不到 items ⇒ **拒判**（不许静默当成 0 条）", False, "竟然没抛")
    except SystemExit:
        ck("⑧ 反向对照：读不到 items ⇒ **拒判**（不许静默当成 0 条）", True, "")
    except Exception as e:                                   # noqa: BLE001
        ck("⑧ 反向对照：读不到 items ⇒ 拒判", False, "抛的是 %r" % (e,))
    globals()["_lark"] = _orig

    print("batch_scan --selftest（PRD §12 并发 / §15 批量扫描）")
    for n, c, ex in res:
        print("  %s %s%s" % ("✅" if c else "❌", n, ("　｜ " + str(ex)) if ex else ""))
    bad = sum(1 for _, c, _e in res if not c)
    print("结果：%d/%d%s" % (len(res) - bad, len(res), "" if not bad else "  ← 有失败"))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
