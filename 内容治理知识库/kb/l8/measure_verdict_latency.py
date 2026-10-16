#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""measure_verdict_latency.py —— PRD §12「性能」三档的**真口径**实测。

## 口径（**Owner 2026-10-12 亲口裁定，不是自创**）

> 「单条文字 ≤ 10 秒；图片 ≤ 20 秒；视频 ≤ 60 秒 ==》指的是**飞书侧守衡回复的时间**
>  比如：我发文字给守衡，守衡 10s 内可以回复我结果」

⇒ 量的是 **`tIngress` → 守衡发出「结果卡」（reply-card）**。

## 与既有两条判据的分工（**三条不许混着说**）

| 判据 | 量什么 | 现状 |
|---|---|---|
| `measure_group_response.py` | ingress → **回执卡**（PRD §12「可用性 ≤5s」） | 6 次观测，中位 1063 ms ✅ |
| **本件** | ingress → **结果卡**（PRD §12「性能」三档） | ← 就是它 |
| `perf_measure.py` | **证据层地板**（`KB_ENTRY=selftest`，不含 agent/LLM/发布） | 文字 5.145 s |

★ 前两者是**用户感知的时间**；第三者**不是** —— `perf-latest.md` 原先拿它当「性能达标」证据，
  在 Owner 这条口径下**不成立**（它明确排除了 agent 与 LLM，而回复时间大头正在那里）。

## 数据来源与配对规则（**如实写出来，因为它有歧义**）

读守衡日志 `PMO/logs/ws_daemon.log`（只读）。事件四类，各自锚点：

    ingress       `★ 收到消息`（带 [+N s] 时间戳）
    gate          `🧭 送审闸门：text|media —— …`（无时间戳 ⇒ 取**最近一个**时间戳，仅用于排序）
    reply         `✓ 已发送 … [reply-card]`（带时间戳）← **这就是「结果卡」**
    verdict_line  `📋 PRD §5.3 结论行：…`（无时间戳，用来确认这张卡带结论）

**配对**：把每条 reply-card 归给**最近一条「有送审闸门、且还没配过卡」的 ingress**。
若在它之前又有别的送审 ingress 起跑过 ⇒ 该单记 `ambiguous`，**不计入统计**（宁少不假）。

**模态**：`送审闸门：text` ⇒ 文字（门槛 10 s）；`media —— 带了媒材（图 N 张）` ⇒ 图片（20 s）；
`（视频 N 段）` ⇒ 视频（60 s）。

## 纪律

1. **只读** —— 不写库、不碰飞书、不改守衡。
2. **样本少就照实说** —— 只报 n / min / 中位 / max，**不声称 P95/P99**。
3. **没有观测 ⇒ `no_reading`，退出码 3** —— **不许当成达标**（这是 fail-open 方向，最坏一类）。
4. **判据必须能判假** —— `--selftest` 含反向对照（喂一条超门槛 ⇒ 精确 FAIL）与变异测试。

## 用法

    python3 kb/l8/measure_verdict_latency.py              # 读守衡日志汇总
    python3 kb/l8/measure_verdict_latency.py --selftest    # 自证（纯夹具，不读真日志）
"""
from __future__ import annotations

import argparse
import io
import os
import re
import statistics
import sys

DEFAULT_LOG = os.path.expanduser(
    "~/Project/audit_multi_content/PMO/logs/ws_daemon.log")

#: PRD §12「性能」行三档 —— **唯一口径，改这里**。
THRESHOLDS_MS = {"text": 10_000, "image": 20_000, "video": 60_000}

TS_RE = re.compile(r"^\[\+\s*([0-9.]+)s\]")
MEDIA_IMG_RE = re.compile(r"（图\s*\d+\s*张")
MEDIA_VID_RE = re.compile(r"（视频\s*\d+\s*段")


def parse(text):
    """日志文本 ⇒ (units, counters)。**解析不了的一律计数，不许静默。**"""
    units, cur = [], None
    pending = []                       # 已起跑、还没配到卡的送审单
    counters = {"ingress": 0, "gate": 0, "reply": 0, "verdict_line": 0,
                "duplicate": 0, "orphan_reply": 0, "nonmonotonic": 0, "restarts": 0}
    last_ts = None
    prev_ts = None
    for ln in text.splitlines():
        m = TS_RE.match(ln)
        # ★ 结论行**可能带也可能不带**时间戳（实测两种都有）—— 先无条件计数，免得漏成 0
        if "📋 PRD §5.3 结论行" in ln:
            counters["verdict_line"] += 1
        # ★ `[p0] 🚦 P0 命中` 那行**同样没有时间戳**（第一版把它写在带时间戳的分支里 ⇒ P0 单被误标成链单，
        #   自证 ⑩ 当场抓出来）。它**覆盖**闸门给的默认标 —— 判定是确定性的，不起链。
        if cur is not None and "🚦 P0 命中" in ln:
            cur["path"] = "p0"
        if m:
            t = float(m.group(1))
            # ★ [ +N s ] 是**进程内**计时 ⇒ 守衡一重启就归零。跨重启的配对会产生**负时延**，
            #   必须认出来并剔除（见下面 nonmonotonic），不许当成"很快"或"负数很快"。
            if prev_ts is not None and t < prev_ts - 60:
                counters["restarts"] += 1
            prev_ts = t
            last_ts = t
            if "★ 收到消息" in ln:
                counters["ingress"] += 1
                cur = {"t_in": t, "modality": None, "reply": None, "ambiguous": False,
                       "path": None}   # "p0" = P0 快路（不起链）｜ "chain" = 评审链
                units.append(cur)
            elif "卡片 receipt" in ln:
                pass
            elif "已发送" in ln and "[reply-card]" in ln:
                counters["reply"] += 1
                # 归给最近一条「有闸门、还没配卡」的送审单
                target = None
                for u in reversed(pending):
                    if u["reply"] is None:
                        target = u
                        break
                if target is None:
                    counters["orphan_reply"] += 1
                elif t < target["t_in"]:
                    # 跨重启 / 出屏序 ⇒ 时间不可比，**剔除并计数**（不许算成负的"很快"）
                    counters["nonmonotonic"] += 1
                    pending.remove(target)
                else:
                    target["reply"] = t
                    # 在它之后才起跑的其它送审单 ⇒ 这一配对准不准存疑
                    later = [u for u in pending if u is not target and u["t_in"] > target["t_in"]
                             and u["t_in"] < t]
                    if later:
                        target["ambiguous"] = True
                    pending.remove(target)
            elif "不回复（duplicate）" in ln:
                counters["duplicate"] += 1

        else:
            if "🧭 送审闸门" in ln and cur is not None:
                counters["gate"] += 1
                if "：text" in ln:
                    mod = "text"
                elif "：media" in ln:
                    if MEDIA_VID_RE.search(ln):
                        mod = "video"
                    elif MEDIA_IMG_RE.search(ln):
                        mod = "image"
                    else:
                        mod = "media_other"
                else:
                    mod = "unknown"
                cur["modality"] = mod
                if cur.get("path") is None:
                    cur["path"] = "chain"
                pending.append(cur)
    return units, counters


def _stats(vals, limit):
    if not vals:
        return {"n": 0, "limit_ms": limit, "verdict": "no_reading",
                "why": "**没有可配对的观测** ⇒ 判不了（**不许当成达标**）"}
    over = [v for v in vals if v > limit]
    return {"n": len(vals), "min_ms": vals[0], "median_ms": int(statistics.median(vals)),
            "max_ms": vals[-1], "over": len(over), "limit_ms": limit,
            "verdict": "pass" if not over else "FAIL",
            "why": ("全部 ≤ %d ms" % limit) if not over else
                   ("%d/%d 条超 %d ms（最慢 %d ms）" % (len(over), len(vals), limit, vals[-1]))}


def summarize_by_path(units, thresholds=None, include_ambiguous=False):
    """★ 按「P0 快路 / 评审链」分开统计 —— **不分开就看不见改动效果**
    （P0 单只占 ~16%，中位数是第 50 百分位，永远不动）。"""
    th = thresholds or THRESHOLDS_MS
    out = {}
    for mod, limit in th.items():
        for path in ("p0", "chain"):
            rows = [u for u in units if u.get("modality") == mod and u.get("path") == path
                    and u.get("reply") is not None
                    and (include_ambiguous or not u.get("ambiguous"))]
            out["%s/%s" % (mod, path)] = _stats(sorted(round((u["reply"] - u["t_in"]) * 1000) for u in rows), limit)
    return out


def summarize(units, thresholds=None, include_ambiguous=False):
    """纯函数：给 units ⇒ 结论。`--selftest` 直接喂夹具验它。"""
    th = thresholds or THRESHOLDS_MS
    out = {}
    for mod, limit in th.items():
        rows = [u for u in units
                if u.get("modality") == mod and u.get("reply") is not None
                and (include_ambiguous or not u.get("ambiguous"))]
        vals = sorted(round((u["reply"] - u["t_in"]) * 1000) for u in rows)
        if not vals:
            out[mod] = {"n": 0, "limit_ms": limit, "verdict": "no_reading",
                        "why": "**没有可配对的观测** ⇒ 判不了（**不许当成达标**）"}
            continue
        over = [v for v in vals if v > limit]
        out[mod] = {
            "n": len(vals), "min_ms": vals[0],
            "median_ms": int(statistics.median(vals)), "max_ms": vals[-1],
            "over": len(over), "limit_ms": limit,
            "verdict": "pass" if not over else "FAIL",
            "why": ("全部 ≤ %d ms" % limit) if not over else
                   ("%d/%d 条超 %d ms（最慢 %d ms）" % (len(over), len(vals), limit, vals[-1])),
        }
    return out


def run(path=DEFAULT_LOG, include_ambiguous=False):
    print("守衡回复时延 —— PRD §12「性能」三档（Owner 2026-10-12 裁定口径）")
    print("口径：**tIngress → 守衡发出结果卡（reply-card）**，即「我发消息 → 守衡回复我结果」")
    print("★ 与「回执卡 ≤5s」是两条：回执卡在跑链之前发，见 measure_group_response.py\n")
    if not os.path.exists(path):
        print("读不到守衡日志：%s" % path)
        print("⇒ 判不了。**这不等于达标**。")
        return 2
    text = io.open(path, encoding="utf-8", errors="ignore").read()
    units, c = parse(text)
    s = summarize(units, include_ambiguous=include_ambiguous)
    print("事件账：ingress %d ｜ 送审闸门 %d ｜ reply-card %d ｜ 结论行 %d ｜ duplicate %d "
          "｜ 无主卡片 %d ｜ **跨重启/出屏序被剔除 %d** ｜ 检出重启 %d"
          % (c["ingress"], c["gate"], c["reply"], c["verdict_line"],
             c["duplicate"], c["orphan_reply"], c["nonmonotonic"], c["restarts"]))
    if c["nonmonotonic"]:
        print("⚠️ 剔除的 %d 单是**守衡重启**造成的（`[+N s]` 是进程内计时，归零后跨重启不可比）"
              "—— 那是量法边界，**不是「很快」**。" % c["nonmonotonic"])
    amb = len([u for u in units if u.get("ambiguous")])
    print("配对：可统计 %d 单 ｜ **歧义被剔除 %d 单**（它之前另有送审起跑 ⇒ 宁少不假）"
          % (len([u for u in units if u.get("reply") and not u.get("ambiguous")]), amb))
    if include_ambiguous:
        print("⚠️ 本次带 --include-ambiguous：歧义单**也计入** ⇒ 数字偏乐观，报告里要写明。")
    print()
    worst = "pass"
    names = {"text": "文字", "image": "图片", "video": "视频"}
    for mod in ("text", "image", "video"):
        r = s[mod]
        if r["verdict"] == "no_reading":
            print("  %-4s 门槛 %6d ms ｜ %s" % (names[mod], r["limit_ms"], r["why"]))
            worst = "no_reading" if worst == "pass" else worst
            continue
        icon = "✅ 达标" if r["verdict"] == "pass" else "❌ **未达标**"
        print("  %-4s 门槛 %6d ms ｜ n=%-3d min %7d ｜ **中位 %7d** ｜ max %7d ｜ %s（%s）"
              % (names[mod], r["limit_ms"], r["n"], r["min_ms"], r["median_ms"], r["max_ms"],
                 icon, r["why"]))
        if r["verdict"] == "FAIL":
            worst = "FAIL"
    # ★ 分路读数（P0 快路 vs 评审链）—— 2026-10-12 加：P0 短卡改动只能在这一档上看出来
    bp = summarize_by_path(units, include_ambiguous=include_ambiguous)
    print()
    print("★ 分路（同一条门槛，但把两路拆开 —— P0 快路 ~16%／评审链 ~84%）：")
    for mod in ("text", "image", "video"):
        for path, nm in (("p0", "P0 快路"), ("chain", "评审链")):
            r = bp["%s/%s" % (mod, path)]
            if r["n"] == 0:
                continue
            icon = "✅" if r["verdict"] == "pass" else "❌"
            print("  %-4s %-6s n=%-3d min %7d ｜ **中位 %7d** ｜ max %7d ｜ %s"
                  % (names[mod], nm, r["n"], r["min_ms"], r["median_ms"], r["max_ms"], icon))
    print()
    if worst == "no_reading":
        print("结论：**没有观测 ⇒ 判不了**（不等于达标）")
    elif worst == "FAIL":
        print("结论：❌ **未达标** —— 按 Owner 口径，这三档量的是用户实际等的时间。")
        print("      登记处：kb/l7/registry/perf-known-drift.yaml（未登记者 = 新事件）")
    else:
        print("结论：✅ 三档全部达标")
    print("★ 边界：只报 n/min/中位/max，**不声称 P95/P99**；歧义单已剔除（宁少不假）。")
    return 3 if worst in ("FAIL", "no_reading") else 0


def selftest():
    res = []

    def ck(n, c, ex=""):
        res.append((n, bool(c), ex))

    def mk(mod, t_in, t_rep, amb=False):
        return {"t_in": t_in, "modality": mod, "reply": t_rep, "ambiguous": amb}

    # ① 解析：三种模态都认得出来
    log = ("[+100.000s] ★ 收到消息 chat=oc_x msg=om_1\n"
           "[agent] 🧭 送审闸门：text —— 命中送审词：审｜起链\n"
           "[+103.000s]    ✓ 已发送 om_a [reply-card]\n"
           "[+200.000s] ★ 收到消息 chat=oc_x msg=om_2\n"
           "[agent] 🧭 送审闸门：media —— 带了媒材（图 1 张）｜起链\n"
           "[+204.000s]    ✓ 已发送 om_b [reply-card]\n"
           "[+300.000s] ★ 收到消息 chat=oc_x msg=om_3\n"
           "[agent] 🧭 送审闸门：media —— 带了媒材（视频 1 段）｜起链\n"
           "[+330.000s]    ✓ 已发送 om_c [reply-card]\n")
    units, c = parse(log)
    ck("① 解析：3 条 ingress / 3 条闸门 / 3 张卡",
       c["ingress"] == 3 and c["gate"] == 3 and c["reply"] == 3,
       "ing=%d gate=%d rep=%d" % (c["ingress"], c["gate"], c["reply"]))
    ck("①b 模态识别：text / image / video 各 1",
       [u["modality"] for u in units] == ["text", "image", "video"],
       str([u["modality"] for u in units]))
    s = summarize(units)
    ck("①c 时延算对：3.0 / 4.0 / 30.0 s",
       [s[k]["median_ms"] for k in ("text", "image", "video")] == [3000, 4000, 30000],
       str([s[k]["median_ms"] for k in ("text", "image", "video")]))
    ck("①d 三档都达标", all(s[k]["verdict"] == "pass" for k in s), str({k: s[k]["verdict"] for k in s}))

    # ★ 反向对照：文字 11 s ⇒ 必须精确 FAIL（判据不是恒真）
    s2 = summarize([mk("text", 0.0, 11.0)])
    ck("② 反向对照：文字 11 s ⇒ 精确判 FAIL", s2["text"]["verdict"] == "FAIL", s2["text"]["verdict"])
    # ★ 反向对照：边界值 10.000 s 不算超（> 才算）
    s2b = summarize([mk("text", 0.0, 10.0)])
    ck("②b 边界：正好 10.000 s ⇒ 不算超（> 才算）", s2b["text"]["verdict"] == "pass",
       s2b["text"]["verdict"])
    # ★ 反向对照：没有观测 ⇒ no_reading，**不许当达标**
    s3 = summarize([])
    ck("③ 反向对照：无观测 ⇒ no_reading（不许当达标）",
       all(s3[k]["verdict"] == "no_reading" for k in s3), str(s3["text"]["verdict"]))
    # ★ 歧义单默认剔除，且剔除后不许被当成"没有观测"而误判达标
    s4 = summarize([mk("text", 0.0, 5.0, amb=True)])
    ck("④ 歧义单默认剔除 ⇒ 该档 no_reading（宁少不假）",
       s4["text"]["verdict"] == "no_reading", s4["text"]["verdict"])
    s5 = summarize([mk("text", 0.0, 5.0, amb=True)], include_ambiguous=True)
    ck("④b --include-ambiguous ⇒ 计入（数字偏乐观，要显式开）",
       s5["text"]["n"] == 1 and s5["text"]["verdict"] == "pass", str(s5["text"]))
    # ★ 反向对照：卡片找不到主 ⇒ 计数，不许静默丢
    _u, c2 = parse("[+1.000s]    ✓ 已发送 om_x [reply-card]\n")
    ck("⑤ 反向对照：无主卡片被计数（不许静默）", c2["orphan_reply"] == 1, str(c2["orphan_reply"]))
    # ⑥ 变异测试：门槛放宽到 10 倍 ⇒ ② 必须精确变假
    s6 = summarize([mk("text", 0.0, 11.0)], thresholds={"text": 110_000})
    ck("⑥ 变异测试：文字门槛放宽到 110 s ⇒ ② 精确变假", s6["text"]["verdict"] == "pass",
       s6["text"]["verdict"])
    # ⑦ 门槛表与 PRD §12 逐字对齐（改错门槛 = 整张表在说谎）
    ck("⑦ 门槛表 == PRD §12（10 / 20 / 60 s）",
       THRESHOLDS_MS == {"text": 10_000, "image": 20_000, "video": 60_000}, str(THRESHOLDS_MS))
    # ⑧ 媒体但分不出图/视频 ⇒ 不许塞进任何一档
    _u8, _c8 = parse("[+1.000s] ★ 收到消息 chat=x msg=y\n[agent] 🧭 送审闸门：media —— 带了媒材\n"
                     "[+9.000s]    ✓ 已发送 om_z [reply-card]\n")
    s8 = summarize(_u8)
    ck("⑧ 分不出图/视频的 media ⇒ 三档都 no_reading（不许硬塞）",
       all(s8[k]["n"] == 0 for k in s8), str({k: s8[k]["n"] for k in s8}))

    # ★ 反向对照：跨重启 ⇒ 出现**负时延**，必须被剔除并计数（不许算成"很快"）
    log_nm = ("[+900.000s] ★ 收到消息 chat=x msg=y\n"
              "[agent] 🧭 送审闸门：text —— 起链\n"
              "[+  5.000s]    ✓ 已发送 om_z [reply-card]\n")
    u_nm, c_nm = parse(log_nm)
    s_nm = summarize(u_nm)
    ck("⑨ 反向对照：跨重启的负时延被剔除并计数（不许当「很快」）",
       c_nm["nonmonotonic"] == 1 and c_nm["restarts"] == 1
       and s_nm["text"]["verdict"] == "no_reading",
       "nm=%d restarts=%d verdict=%s" % (c_nm["nonmonotonic"], c_nm["restarts"],
                                         s_nm["text"]["verdict"]))
    # ★ 反向对照：路径标注 —— P0 单必须标成 p0，链单必须标成 chain（标反了=分路读数假）
    _up, cp = parse("[+1.000s] ★ 收到消息 chat=x msg=a\n"
                    "[agent] 🧭 送审闸门：text —— 起链\n"
                    "[p0] 🚦 P0 命中 ⇒ 直接 BLOCK，不起链：H05｜48.297 ms\n"
                    "[+9.000s]    ✓ 已发送 om_a [reply-card]\n"
                    "[+100.000s] ★ 收到消息 chat=x msg=b\n"
                    "[agent] 🧭 送审闸门：text —— 起链\n"
                    "[+140.000s]    ✓ 已发送 om_b [reply-card]\n")
    ck("⑩ 分路标注：P0 单标 p0、链单标 chain（含**无 timestamp 的 `[p0]` 行**归给当前单）",
       [u.get("path") for u in _up] == ["p0", "chain"], str([u.get("path") for u in _up]))
    _sp = summarize_by_path(_up)
    ck("⑩b 分路读数拆开算：P0 档 8 s／链档 40 s 各自成账",
       _sp["text/p0"]["n"] == 1 and _sp["text/chain"]["median_ms"] == 40000,
       "%s / %s" % (_sp["text/p0"].get("median_ms"), _sp["text/chain"].get("median_ms")))

    # ★ 结论行计数不许漏成 0（实测它**带**时间戳，第一版漏了）
    _u9, c9 = parse("[+1.000s]    📋 PRD §5.3 结论行：BLOCK（来自 dual-track-merged）｜落点=x\n"
                    "    📋 PRD §5.3 结论行：PASS\n")
    ck("⑨b 结论行两种形态都计到（带/不带时间戳）", c9["verdict_line"] == 2, str(c9["verdict_line"]))

    print("measure_verdict_latency --selftest（PRD §12 性能三档 · Owner 2026-10-12 口径）")
    for n, c, ex in res:
        print("  %s %s%s" % ("✅" if c else "❌", n, ("　｜ " + ex) if ex else ""))
    bad = sum(1 for _, c, _e in res if not c)
    print("结果：%d/%d%s" % (len(res) - bad, len(res), "" if not bad else "  ← 有失败"))
    return 1 if bad else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--log", default=DEFAULT_LOG)
    ap.add_argument("--include-ambiguous", action="store_true",
                    help="把配对存疑的单也计入（默认剔除；开了数字偏乐观）")
    a = ap.parse_args()
    sys.exit(selftest() if a.selftest else run(a.log, a.include_ambiguous))
