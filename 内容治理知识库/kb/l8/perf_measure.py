#!/usr/bin/env python3
"""性能测量（任务拆解 目标 15 / 17 / 19 · PRD §12）。

## 为什么要有这个脚本

任务拆解 现状原文：目标 15「**未测**」、目标 17「**均未测**」、目标 19「**未测**」。
而 PRD §12 给的是**硬数字**：

| 项 | 要求 |
|---|---|
| 性能 | 单条文字 **≤ 10 s**；图片 **≤ 20 s**；视频 **≤ 60 s** |
| 并发 | 支持批量扫描 **100-500 条** |
| 可用性 | 飞书群 @Agent 响应时间 **≤ 5 s** |
| P0 层响应 | **≤ 1 s**（关键词/正则匹配） |
| 报告生成 | 问题 ≥ 3 时，报告链接生成 **≤ 30 s** |

库里此前只有一份 `kb/l7/reports/batch12-B-block-timing-20261002.md`，它自己声明了两条边界：
**「不含 agent 与 LLM 推断」**、**「未测：并发请求」**。目标 17/19 要的正是它没测的那几项。

## ★★ 一条踩过的坑（2026-10-10，**我自己造成的**，别再犯）

做本批测量时我用 `with_kb_evidence.py --text "<样板文本>"` 手敲了 **12 条端到端测试单**
做验证 —— 那些命令**会往 `kb/l7/runs/index.jsonl` 写真实评审记录**，
于是把三态比例与人工复核负担**污染了**（12 条清一色 BLOCK，把比例往 BLOCK 推）。

两个层面的教训，都要照办：

1. **测证据层**：本脚本已把报告隔离到 `SCRATCH`（`/tmp/kb-perf-scratch`）。
2. **测端到端（整链）**：**`with_kb_evidence.py` 没有「不记账」的开关** ⇒
   跑它就会在索引里留下一条。所以：
   · 要跑就**先记下 run_id**，跑完登记进 `kb/l8/audit_metrics.mjs` 的 `TEST_RUN_IDS`
     （那份排除表**按 run_id 精确点名**，不用文本特征 —— 文本特征会误伤历史测试单）。
   · 索引是**只追加的审计台账**，**不许改它、不许删行**；排除只作用于**统计口径**。

## 三条纪律

1. **本脚本只读**：不改库、不写飞书、不认领。它**只计时**。
2. **样本少就照实说**：只报 `min/median/max` 与 `n`，**不声称 P95/P99、不声称统计置信度**
   （承 `batch12` 那份报告的做法）。
3. **量不到就写 `no_data` + 原因**，**不编**。特别是：
   * **群响应 ≤5s** —— 含守衡侧与模型侧，**本机测不到**（那是另一仓库 + LLM 推断）；
   * **并发 100-500 条** —— 需要批量入口，**当前只有单条入口**。

## 用法

    python3 kb/l8/perf_measure.py --selftest          # 判据自证（不跑真测量）
    python3 kb/l8/perf_measure.py --evidence -n 3     # 量依据侧单条（默认文字）
    python3 kb/l8/perf_measure.py --soak -n 5         # 并发/串行批量摸底
    python3 kb/l8/perf_measure.py --out <path.json>   # 落盘
"""

from __future__ import annotations

import argparse
import io
import json
import os
import statistics
import subprocess
import sys
import time

KB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(KB)
REVIEW = os.path.join(KB, "l7", "skills", "kb-content-review", "scripts", "review.py")
P0_SCRIPT = os.path.join(KB, "l5", "p0_fastpath.py")
LEDGER_DEFAULT = os.path.join(KB, "l7", "reports", "perf-latest.json")

#: P0 命中夹具（**逐字固定**，可复现；实测 hit=True / H05）。
P0_FIXTURE = "吸奶器M5 SMART，是最好的吸奶器，这句能过审吗？"

#: PRD §12 的门槛。**唯一口径**，改这里。
THRESHOLDS_S = {"text": 10, "image": 20, "video": 60,
                "report": 30, "p0_fastpath": 1}

#: 固定输入（逐字固定，可复现）。**不许每次换文本** —— 换了就不可比。
FIXTURES = {
    "text": "Our breast pump is FDA approved and 100% safe. It increases milk supply in 3 days.",
    "text_long": ("Our breast pump is FDA approved and 100% safe for every mom. "
                  "It mimics your baby's natural nursing rhythm and is clinically proven "
                  "to increase milk supply in 3 days. The #1 best selling breast pump on Amazon, "
                  "now with a doctor recommended flange that prevents clogged ducts."),
    # 图片/视频：本机没有真实素材（L1 媒体区有，但抽取链是另一条）。**用 OCR 文本代输入**
    # 是**近似**，不是等价 —— 报告里必须写明。
    "image_ocr_proxy": "【图片 1 的图内文字】FDA approved. 100% safe. hospital grade. pain-free.",
    "video_asr_proxy": ("【视频口播转写】it mimics your baby's natural nursing rhythm, "
                        "clinically proven to increase milk supply in 3 days, "
                        "and it is 100% safe for baby."),
}


def _stats(xs):
    """只报 min/median/max —— **n 小就不装**（承 batch12 的口径）。"""
    xs = [x for x in xs if x is not None]
    if not xs:
        return None
    return {"n": len(xs), "min_s": round(min(xs), 3),
            "median_s": round(statistics.median(xs), 3),
            "max_s": round(max(xs), 3)}


#: ★★ 测量用的报告**必须落 scratch 目录**，不许进 `kb/l7/reports/`。
#: 为什么（2026-10-10 实测踩过，**我自己造成的**）：`review.py` 默认把报告写进
#: `kb/l7/reports/`，而 `perf_measure` 每次跑都新增一份 ⇒ 一小时内往那儿灌了 **31 份 `PERF-*`**，
#: 被 `audit_metrics.mjs` 当成「真评审报告」计进 `n_reports` 分母 ⇒ **测量污染了指标**。
#: ⇒ 测量产物与业务产物**物理隔离**。URL 是只读量，与报告落点无关。
SCRATCH = os.environ.get("KB_PERF_SCRATCH") or "/tmp/kb-perf-scratch"


def run_evidence(text, content_type="text", timeout=300):
    """跑一次依据侧，返回 (wall_s, trace_perf, 错误)。

    ★ 用 `KB_ENTRY=selftest`（隔离测试入口）—— 那条路**明确不带层前置与判定主体**，
      所以它的耗时是**证据层自己的地板**，不含四层前置。报告里必须写明这条边界。
    ★ 报告落 `SCRATCH`（见该常量注释）—— **不污染 `kb/l7/reports/`**。
    """
    os.makedirs(SCRATCH, exist_ok=True)
    env = dict(os.environ, KB_ENTRY="selftest")
    t0 = time.perf_counter()
    p = subprocess.run(
        [sys.executable, REVIEW, "--text", text, "--content-type", content_type,
         "--run-id", "PERF-%d" % int(time.time() * 1000),
         "--report-dir", SCRATCH, "--json"],
        capture_output=True, text=True, env=env, timeout=timeout)
    wall = time.perf_counter() - t0
    perf = None
    txt = (p.stdout or "")
    i = txt.find("{")
    if i >= 0:
        try:
            o = json.loads(txt[i:])
            perf = (o.get("trace") or {}).get("perf")
        except Exception:
            perf = None
    err = None
    if p.returncode not in (0, 3):
        err = "exit=%d %s" % (p.returncode, (p.stderr or "")[-200:])
    return wall, perf, err


def measure_evidence(n, fixture="text", content_type="text"):
    walls, stages = [], []
    errs = []
    for k in range(n):
        w, perf, err = run_evidence(FIXTURES[fixture], content_type)
        walls.append(w)
        if perf:
            stages.append(perf)
        if err:
            errs.append(err)
    # 逐段取中位数
    stage_med = {}
    if stages:
        for key in ("p0_match_ms", "rule_layer_ms", "unit_layer_ms", "assemble_ms"):
            vals = [s.get(key) for s in stages if s.get(key) is not None]
            if vals:
                stage_med[key] = round(statistics.median(vals), 1)
    thr = THRESHOLDS_S.get(content_type, 10)
    med = statistics.median(walls) if walls else None
    return {
        "fixture": fixture, "content_type": content_type, "n": n,
        "wall": _stats(walls),
        "stage_median_ms": stage_med,
        "threshold_s": thr,
        "verdict": (None if med is None else ("pass" if med <= thr else "fail")),
        "errors": errs or None,
        "note": ("★ 这是**证据层地板**（`KB_ENTRY=selftest`，不含四层前置 / 判定主体 / 发布）。"
                 + ("" if content_type == "text" else
                    "★ 图片/视频一档是**用 OCR/ASR 文本代输入**的**近似**，"
                    "不含真实 OCR/ASR 与关键帧抽取成本 ⇒ **不能读成「图片链路 ≤20s 达标」**。")),
    }


def measure_batch(n, fixture="text"):
    """串行 N 条的吞吐摸底。

    ⚠️ PRD §12 要的是「**并发** 100-500 条」。本机**当前只有单条入口**
    （`with_kb_evidence.py --text`；批量入口是任务拆解 11/23 那行的目标）。
    ⇒ 本函数量的是**串行吞吐**，**不等于并发能力**，报告里必须分开写。
    """
    walls = []
    t0 = time.perf_counter()
    for _ in range(n):
        w, _, _ = run_evidence(FIXTURES[fixture])
        walls.append(w)
    total = time.perf_counter() - t0
    st = _stats(walls)
    return {
        "mode": "serial", "n": n, "total_s": round(total, 2),
        "per_item": st,
        "throughput_per_min": (round(n / total * 60, 2) if total else None),
        "concurrency_measured": False,
        "no_data_reason": ("PRD §12 要「并发 100-500 条」，而**当前只有单条入口** —— "
                           "批量入口是任务拆解 11/23 那行的目标，**尚未建**。"
                           "本项量的是**串行吞吐**，不得读作并发能力。"),
    }


# ══════════════════════════════════════════════════════════════════
# ★ 2026-10-12 补：§12「P0 层响应 ≤1s」与「报告生成 ≤30s」两档的**真量法**
#
# 为什么补：`kb/l7/reports/perf-latest.json` 里 `p0_judge` / `p0_with_report` 两行
# **全库没有任何写入方**（`grep -rn p0_judge kb/ ci/ tools/` = 0 命中），
# 也没有 `fixture` / `note` 字段 —— 它们是**手写进台账**的，追不出出处。
# 而台账顶部那句「生成命令：python3 kb/l8/perf_measure.py」对它们**不成立**。
# ⇒ 要么量出来，要么别写进台账。本函数就是量出来那一路（只读、无网络、不发布）。
# ══════════════════════════════════════════════════════════════════

def _p0_once(report_out=None, timeout=120):
    """跑一次 P0 快路 CLI，⇒ (wall_s, engine_ms, 返回码)。"""
    argv = [sys.executable, P0_SCRIPT, "--text", P0_FIXTURE, "--json"]
    if report_out:
        argv += ["--report-out", report_out]
    t0 = time.perf_counter()
    p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, cwd=ROOT)
    wall = time.perf_counter() - t0
    engine = None
    try:
        i = (p.stdout or "").find("{")
        engine = json.loads((p.stdout or "")[i:]).get("elapsed_ms")
    except Exception:                                          # noqa: BLE001
        engine = None
    return wall, engine, p.returncode


def measure_p0(n=3):
    """⇒ {"p0_judge": …, "p0_with_report": …}（形状与台账既有两行一致 + 出处字段）。"""
    os.makedirs(SCRATCH, exist_ok=True)
    rep = os.path.join(SCRATCH, "p0-report.md")
    walls, engines, rcs = [], [], []
    for _ in range(n):
        w, e, rc = _p0_once()
        walls.append(w)
        engines.append(e)
        rcs.append(rc)
    walls2 = []
    for _ in range(n):
        w, _e, _rc = _p0_once(report_out=rep)
        walls2.append(w)
    bad = [rc for rc in rcs if rc != 0]
    at = time.strftime("%Y-%m-%dT%H:%M:%S")
    prov = {"measured_by": "kb/l8/perf_measure.py::measure_p0",
            "argv": "python3 kb/l8/perf_measure.py --p0 -n %d" % n,
            "at": at, "fixture": P0_FIXTURE}
    med = statistics.median(walls2) if walls2 else None
    return {
        "p0_judge": {
            "wall": _stats(walls), "threshold_s": THRESHOLDS_S["p0_fastpath"],
            "engine_ms": _stats([e / 1000.0 for e in engines if e is not None]),
            "verdict": (None if med is None else
                        ("pass" if statistics.median(walls) <= THRESHOLDS_S["p0_fastpath"] else "fail")),
            "errors": ("退出码非 0：%s" % bad) if bad else None,
            "note": "★ 量的是**调一次 P0 快路 CLI 的墙钟**（含解释器启动）；"
                    "`engine_ms` 是引擎自报的匹配耗时（更小）。",
            "provenance": prov,
        },
        "p0_with_report": {
            "wall": _stats(walls2), "threshold_s": THRESHOLDS_S["report"],
            "verdict": (None if med is None else
                        ("pass" if med <= THRESHOLDS_S["report"] else "fail")),
            "note": "★ 同一夹具 + `--report-out`（把**完整报告**写到文件）的墙钟。"
                    "**不含**云文档创建与飞书落表（那两段属发布，不在这条预算里）。",
            "provenance": dict(prov, argv="python3 kb/l8/perf_measure.py --p0 -n %d（带 --report-out）" % n),
        },
    }


def build_ledger(existing=LEDGER_DEFAULT, n=3, verbose=True):
    """重测**机器能测的四档 + P0 两档**，装配成与 `perf-latest.json` 同形状的台账。

    ★ 机器**测不了**的两类，**保留但标注出处**，不许冒充同一次实测：
      · `end_to_end`（整链 `review_run.sh`）—— 它会写生产表/云文档 ⇒ **不许为测性能重跑**；
      · `no_data`（群响应/并发/真媒体）—— 「量不到」本身就是要写下来的结论。
    """
    led = {}
    if existing and os.path.exists(existing):
        led = json.load(io.open(existing, encoding="utf-8"))
    res = led.setdefault("results", {})
    at = time.strftime("%Y-%m-%dT%H:%M:%S")
    for fixture, ctype in (("text", "text"), ("text_long", "text"),
                           ("image_ocr_proxy", "image"), ("video_asr_proxy", "video")):
        r = measure_evidence(n, fixture, ctype)
        r["provenance"] = {"measured_by": "kb/l8/perf_measure.py::measure_evidence",
                           "argv": "python3 kb/l8/perf_measure.py --evidence -n %d --fixture %s"
                                   % (n, fixture),
                           "at": at, "fixture": FIXTURES[fixture]}
        res[fixture] = r
        if verbose:
            print("  量完 %-18s 中位 %.3f s ⇒ %s" % (fixture, r["wall"]["median_s"], r["verdict"]))
    for k, v in measure_p0(n).items():
        res[k] = v
        if verbose:
            print("  量完 %-18s 中位 %.3f s ⇒ %s" % (k, v["wall"]["median_s"], v["verdict"]))
    led["measured_at"] = at
    led["task_ref"] = led.get("task_ref") or "任务拆解 10/12–10/16 行 · 目标 15/17/19"
    led["prd_ref"] = led.get("prd_ref") or "内容审查 Agent PRD v1.2 §12 非功能需求"
    if led.get("end_to_end"):
        led["end_to_end"]["provenance"] = {
            "kind": "archived", "measured_at": "2026-10-10",
            "measured_by": "当时会话留痕（review_run.sh 计时）",
            "why": "整链会写生产结论表行 + 云文档 ⇒ **不许为测性能重跑**；本条只作历史读数保留"}
    # ★ no_data 三句**不再手写**：能现读的现读，量不到的才写「量不到」。
    #   为什么改：原文写着「群响应本机测不到」/「批量入口尚未建」——
    #   而 2026-10-10 埋点就位、判据已给出 6 次观测；`batch_scan.py` 也已建成。
    #   硬编码的结论不会随判据更新 ⇒ 又是一处账实不符。
    gr_txt = "★ **本机可测**：埋点已就位（`tools/agent/agent.mjs` 回执卡处），" \
             "判据 = `kb/l8/measure_group_response.py`（口径：ingress → **回执卡**）。"
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import measure_group_response as _GR
        if os.path.exists(_GR.DEFAULT_LOG):
            _rows, _bad = _GR.parse(io.open(_GR.DEFAULT_LOG, encoding="utf-8",
                                            errors="ignore").read())
            _s = _GR.summarize(_rows)
            if _s["verdict"] == "no_reading":
                gr_txt += "　现读：**观测数 0**（等一次真实送审）⇒ 判不了，不许当达标。"
            else:
                gr_txt += "　现读：观测 **%d** 次 ｜ 中位 **%d ms** ｜ max %d ms ｜ 门槛 %d ms ⇒ %s。" % (
                    _s["n"], _s["median"], _s["max"], _s["limit_ms"],
                    "✅ 达标" if _s["verdict"] == "pass" else "❌ 未达标")
    except Exception as _e:                                    # noqa: BLE001
        gr_txt += "　现读失败：%r（**不许据此当达标**）。" % (_e,)
    led["no_data"] = {
        "group_response_5s": gr_txt,
        "concurrency_100_500": (
            "★ 入口**已建**：`kb/l8/batch_scan.py`（真读结论去向表 → 一批一次层前置 → 有界并发）。"
            "但**实测只跑过 1 条**（7.8 s）、**100-500 条从未压测** ⇒ 本项仍**不得读作并发能力**；"
            "逐条专项归属与结论写回也尚未做。串行吞吐见 `results.batch_serial`。"),
        "image_video_real": (
            "★ 图片/视频两档在**本台账**里是**用 OCR/ASR 文本代输入**的近似，"
            "**不含真实 OCR / ASR / 关键帧抽取成本** ⇒ 不能读成「图片链路 ≤20s 达标」。"
            "真实口径见 `kb/l8/measure_verdict_latency.py`（Owner 2026-10-12 裁定）。"),
    }
    if isinstance(res.get("batch_serial"), dict):
        res["batch_serial"]["no_data_reason"] = led["no_data"]["concurrency_100_500"]
    led["provenance_note"] = (
        "★ 2026-10-12：`results` 六档（四档证据层 + P0 两档）**逐条带 provenance**，"
        "由 `python3 kb/l8/perf_measure.py --ledger` 重测产出；`end_to_end` 标 archived（不许重跑）。"
        "★ 三档「性能」时限（文字/图片/视频）**不是本台账量的** —— Owner 2026-10-12 裁定"
        "其口径为「守衡回复时间」，判据 = `kb/l8/measure_verdict_latency.py`；"
        "本台账的四档是**证据层地板**，读数低不等于用户等得短。")
    return led



def _selftest() -> int:
    """判据自证（不跑真测量：把 run_evidence 换成桩）。"""
    global measure_evidence, _p0_once          # ⑦⑧ 要打桩；global 必须在函数体最前
    ok = fail = 0
    fails: list[str] = []

    def ck(name, cond, detail=""):
        nonlocal ok, fail
        if cond:
            ok += 1
        else:
            fail += 1
            fails.append("%s %s" % (name, detail))

    # ① 阈值表与 PRD §12 逐字对齐（改错门槛 = 整张表都在说谎）
    ck("①a 文字 10s", THRESHOLDS_S["text"] == 10, THRESHOLDS_S["text"])
    ck("①b 图片 20s", THRESHOLDS_S["image"] == 20, THRESHOLDS_S["image"])
    ck("①c 视频 60s", THRESHOLDS_S["video"] == 60, THRESHOLDS_S["video"])
    ck("①d 报告 30s", THRESHOLDS_S["report"] == 30, THRESHOLDS_S["report"])
    ck("①e P0 1s", THRESHOLDS_S["p0_fastpath"] == 1, THRESHOLDS_S["p0_fastpath"])

    # ② 只报 min/median/max，**不许偷偷报 P95**（样本少时那是装）
    st = _stats([1.0, 2.0, 3.0])
    ck("②a 三统计量齐", set(st) == {"n", "min_s", "median_s", "max_s"}, list(st))
    ck("②b 不报分位数", not any("p9" in k or "p5" in k for k in st), list(st))
    ck("②c 中位数对", st["median_s"] == 2.0, st["median_s"])
    ck("②d 空集返回 None", _stats([]) is None and _stats([None]) is None)

    # ③ 判定：中位数过门槛才算过（用最大值判会把偶发抖动当常态）
    class _Stub:
        def __init__(self, walls): self.walls = walls; self.i = 0
        def __call__(self, text, content_type="text", timeout=300):
            w = self.walls[self.i % len(self.walls)]; self.i += 1
            return w, {"p0_match_ms": 1, "rule_layer_ms": 2,
                       "unit_layer_ms": 3, "assemble_ms": 4}, None

    global run_evidence
    keep = run_evidence
    try:
        run_evidence = _Stub([1.0, 2.0, 3.0, 100.0])       # 中位 2.5 ≤ 10 ⇒ pass
        r = measure_evidence(4, "text", "text")
        ck("③a 中位数判过", r["verdict"] == "pass", r["verdict"])
        run_evidence = _Stub([20.0, 21.0, 22.0])           # 中位 21 > 10 ⇒ fail
        r = measure_evidence(3, "text", "text")
        ck("③b 中位数判不过", r["verdict"] == "fail", r["verdict"])
        # ③c 逐段取中位数
        ck("③c 逐段中位数", r["stage_median_ms"].get("unit_layer_ms") == 3,
           r["stage_median_ms"])
    finally:
        run_evidence = keep

    # ④ ★ 反例守则：图片/视频档**必须**带「近似」警告，不许读成达标
    r = measure_evidence(0, "image_ocr_proxy", "image")
    ck("④a 图片档带近似警告", "近似" in (r.get("note") or ""), r.get("note"))
    ck("④b n=0 时不装结论", r["verdict"] is None and r["wall"] is None, r["verdict"])

    # ⑤ ★ 并发那项**必须**如实写 no_data 原因
    b = measure_batch(0)
    ck("⑤a 并发标未测", b["concurrency_measured"] is False)
    ck("⑤b 并发给原因", "尚未建" in (b["no_data_reason"] or ""), b["no_data_reason"][:40])

    # ⑥b ★ 测量产物**不许落业务目录** —— 这条守的是「测量污染指标」那个真事故。
    #     （2026-10-10 实测：31 份 `PERF-*` 灌进 `kb/l7/reports/`，被 audit_metrics 计进分母）
    ck("⑥b scratch 隔离在 /tmp", SCRATCH.startswith("/tmp/"), SCRATCH)
    ck("⑥c scratch 不在 kb/l7/reports",
       os.path.join(KB, "l7", "reports") not in SCRATCH, SCRATCH)

    # ⑥ 固定输入**逐字固定**（换文本就不可比）
    ck("⑥a 输入固定", FIXTURES["text"] == FIXTURES["text"] and len(FIXTURES) >= 4)

    # ⑦ ★ 2026-10-12 新增的两档（P0 判定 / P0＋报告）必须有**真量法**与出处
    _keep_p0, _keep_ev = _p0_once, measure_evidence
    try:
        _p0_once = lambda report_out=None, timeout=120: (0.2, 15.0, 0)   # 桩：200 ms / 引擎 15 ms
        p0 = measure_p0(3)
        ck("⑦a 两档齐（p0_judge / p0_with_report）",
           set(p0) == {"p0_judge", "p0_with_report"}, str(sorted(p0)))
        ck("⑦b 两档都带 provenance（**这就是'补出处'那一条**）",
           all(v.get("provenance", {}).get("measured_by") for v in p0.values()),
           str([v.get("provenance", {}).get("measured_by") for v in p0.values()]))
        ck("⑦c 门槛取自 PRD（P0=1s / 报告=30s）",
           p0["p0_judge"]["threshold_s"] == 1 and p0["p0_with_report"]["threshold_s"] == 30,
           "%s / %s" % (p0["p0_judge"]["threshold_s"], p0["p0_with_report"]["threshold_s"]))
        ck("⑦d 200 ms 的桩 ⇒ 两档都 pass", all(v["verdict"] == "pass" for v in p0.values()),
           str([v["verdict"] for v in p0.values()]))
        # ★ 反向对照：桩放到 2 s ⇒ P0 档（门槛 1 s）必须精确 FAIL，报告档（门槛 30 s）仍 pass
        _p0_once = lambda report_out=None, timeout=120: (2.0, 15.0, 0)
        p0b = measure_p0(3)
        ck("⑦e 反向对照：2 s 的桩 ⇒ P0 档精确 FAIL、报告档仍 pass（判据不是恒真）",
           p0b["p0_judge"]["verdict"] == "fail" and p0b["p0_with_report"]["verdict"] == "pass",
           "%s / %s" % (p0b["p0_judge"]["verdict"], p0b["p0_with_report"]["verdict"]))

        # ⑧ 装配台账：六档都带 provenance；end_to_end **必须标 archived**（不许冒充同一次实测）
        import tempfile
        tmpd = tempfile.mkdtemp(prefix="perfled-")
        seed = os.path.join(tmpd, "seed.json")
        io.open(seed, "w", encoding="utf-8").write(json.dumps(
            {"results": {}, "end_to_end": {"chain_wall_s": {"n": 2, "median_s": 35.8},
                                           "note": "历史"}, "no_data": {"x": "y"}},
            ensure_ascii=False))
        measure_evidence = lambda n, fixture="text", content_type="text": {
            "fixture": fixture, "content_type": content_type, "n": n,
            "wall": {"n": n, "min_s": 1.0, "median_s": 2.0, "max_s": 3.0},
            "threshold_s": THRESHOLDS_S.get(content_type, 10), "verdict": "pass"}
        led = build_ledger(seed, 1, verbose=False)
        ck("⑧a 六档齐（四档证据层 + P0 两档）", len(led["results"]) == 6,
           str(sorted(led["results"])))
        ck("⑧b 六档**全**带 provenance",
           all(v.get("provenance", {}).get("measured_by") for v in led["results"].values()),
           str([k for k, v in led["results"].items() if not v.get("provenance")]))
        ck("⑧c end_to_end 标 archived（不许冒充同一次实测）",
           led["end_to_end"]["provenance"]["kind"] == "archived", "")
        # ★ no_data 三句**必须重新生成**（能现读的现读），不许把旧结论原样留着 ——
        #   旧文案实测写着「群响应本机测不到」（已过期：埋点已就位、观测已有 6 次）。
        nd = led.get("no_data") or {}
        ck("⑧d1 no_data 三键齐且**不再原样保留**旧文案",
           set(nd) == {"group_response_5s", "concurrency_100_500", "image_video_real"}
           and nd.get("group_response_5s") != "y", str(sorted(nd)))
        ck("⑧d2 群响应那句带**现读读数**（含观测数/中位）",
           "观测" in nd.get("group_response_5s", "") and "中位" in nd.get("group_response_5s", ""),
           nd.get("group_response_5s", "")[:80])
        # ★ 反向对照：把那句已知过期的说法写回去 ⇒ 本判据必须精确变红
        stale = dict(nd, group_response_5s="★ **本机测不到** —— 含守衡侧与模型侧 LLM。")
        ck("⑧d3 反向对照：过期说法「本机测不到」被认出（判据不是恒绿）",
           "本机测不到" in stale["group_response_5s"]
           and "本机测不到" not in nd.get("group_response_5s", ""), "反向对照成立")
        ck("⑧e 台账带口径注记（说清三档时限不是本台账量的）",
           "measure_verdict_latency" in led.get("provenance_note", ""), "")
        import shutil
        shutil.rmtree(tmpd, ignore_errors=True)
    finally:
        _p0_once, measure_evidence = _keep_p0, _keep_ev

    print("perf_measure --selftest：%d/%d" % (ok, ok + fail))
    for f in fails:
        print("  ✗", f)
    return 0 if fail == 0 else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="性能测量（PRD §12 · 目标 15/17/19）")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--evidence", action="store_true", help="量依据侧单条")
    ap.add_argument("--soak", action="store_true", help="串行批量摸底")
    ap.add_argument("-n", type=int, default=3)
    ap.add_argument("--fixture", default="text", choices=sorted(FIXTURES))
    ap.add_argument("--content-type", default="text", choices=["text", "image", "video"])
    ap.add_argument("--out", default=None)
    ap.add_argument("--p0", action="store_true",
                    help="量 §12「P0 层响应 ≤1s」与「报告生成 ≤30s」两档（本地、无网络、不发布）")
    ap.add_argument("--ledger", nargs="?", const=LEDGER_DEFAULT, default=None,
                    metavar="PATH",
                    help="重测机器能测的六档并**装配台账**（缺省 %s）；"
                         "end_to_end 保留但标 archived（整链不许为测性能重跑）" % LEDGER_DEFAULT)
    a = ap.parse_args()

    if a.selftest:
        return _selftest()

    res = {"measured_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
           "thresholds_s": THRESHOLDS_S,
           "boundaries": [
               "只量**确定性内核**（依据侧 / 引擎），**不含 agent 与 LLM 推断**（承 batch12 边界 1）。",
               "样本少 ⇒ 只报 min/median/max，**不声称 P95/P99 与统计置信度**。",
               "**群响应 ≤5s 本机测不到** —— 含守衡侧与模型侧，属另一仓库 + LLM。",
               "**并发 100-500 条未测** —— 当前只有单条入口。",
           ]}
    if a.evidence:
        res["evidence"] = measure_evidence(a.n, a.fixture, a.content_type)
    if a.soak:
        res["batch"] = measure_batch(a.n, a.fixture)
    if a.p0:
        res["results"] = measure_p0(a.n)
    if a.ledger:
        print("重测并装配台账（n=%d）……" % a.n, file=sys.stderr)
        led = build_ledger(a.ledger, a.n)
        txt2 = json.dumps(led, ensure_ascii=False, indent=1)
        with open(a.ledger, "w", encoding="utf-8") as fh:
            fh.write(txt2 + "\n")
        back = io.open(a.ledger, encoding="utf-8").read()
        if back != txt2 + "\n":
            print("回读不一致 ⇒ 拒收", file=sys.stderr)
            return 3
        print("已落盘并回读一致：%s" % a.ledger, file=sys.stderr)
        print(json.dumps({"measured_at": led["measured_at"],
                          "results": {k: v.get("wall", {}).get("median_s")
                                      for k, v in led["results"].items()},
                          "verdicts": {k: v.get("verdict") for k, v in led["results"].items()}},
                         ensure_ascii=False, indent=1))
        return 0

    txt = json.dumps(res, ensure_ascii=False, indent=1)
    print(txt)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(txt + "\n")
        print("\n已落盘：%s" % a.out, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
