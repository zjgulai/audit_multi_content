#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""measure_group_response.py —— 目标 19 后半：PRD §12「飞书群 @Agent 响应时间 ≤5 秒」实测。

## 出处（逐字）

· 任务拆解 10/12–10/16 行 **目标 19**：`【补·PRD §12/§5.1】单条时效实测（文字 ≤10s / 图片 ≤20s /
  视频 ≤60s）＋ 飞书群 @Agent 响应 ≤5s。`（**单条时效那半已达标**，见 `kb/l7/reports/perf-latest.md`）
· PRD §12 非功能需求 →「**可用性** | 飞书群 @Agent 响应时间 ≤ 5 秒」
· 与「P0 层响应 ≤1 秒」是**两条**：后者已实测 **0.15 s**；本条量的是**用户感知的那一下**。

## 为什么之前记的是「本机测不到」（已证伪）

`perf-latest.md` 写「本机测不到 —— 含守衡侧（另一仓库）与模型侧 LLM，需在守衡侧埋点」。
**但这个理由不成立**：守衡就在本机（launchd `com.shouheng.lark`，工作目录
`/Users/lute/Project/audit_multi_content/tools/`）⇒ **埋点可做**。已于 2026-10-10 埋好：
`tools/agent/agent.mjs` 在**回执卡发送完成**处打一行

    [metric] group_response_ms=NNN ack_decision_ms=NNN prd_limit_ms=5000 verdict=pass|FAIL chat=…

## 口径（**照已定口径，不是自创**）

「响应」= **回执卡**（`review_publish.mjs:47` 逐字：「P0 问题可先在飞书侧响应」——
回执卡在跑链**之前**发，P0 判定在其后 9.8~27 ms，**不计入这条预算**）。
⇒ 量的是 `tIngress → 回执卡发送完成`，**不是整链耗时**。整链是几十分钟的量级，那是另一条指标。

## 用法

    python3 kb/l8/measure_group_response.py             # 读守衡日志汇总
    python3 kb/l8/measure_group_response.py --selftest   # 自证（纯夹具，不读真日志）
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
LIMIT_MS = 5000
LINE_RE = re.compile(r"\[metric\]\s+group_response_ms=(\d+)"
                    r"(?:\s+ack_decision_ms=(\d+))?(?:\s+prep_ms=(\d+))?"
                    r"(?:.*?stage=(\w+))?(?:.*?ingress=(\w+))?")


def parse(text):
    """从日志文本里抽观测。**解析不了的行一律跳过并计数**，不许猜。"""
    rows, bad = [], 0
    for ln in text.splitlines():
        if "[metric]" not in ln:
            continue
        m = LINE_RE.search(ln)
        if not m:
            bad += 1
            continue
        rows.append({"group_response_ms": int(m.group(1)),
                     "ack_decision_ms": int(m.group(2)) if m.group(2) else None,
                     "prep_ms": int(m.group(3)) if m.group(3) else None,
                     # ★ 2026-10-20：`ingress` 是**这条读数可不可信**的标记。
                     #   只有 `create_time`（飞书服务端的消息时刻）才是 PRD §12 要量那一段；
                     #   没有这个字段（或 handle_entry）的是**旧口径**，量的是"进闸门之后"——
                     #   拿它当达标依据就是 10-20 之前那个错。
                     "ingress": m.group(5) if m.group(5) else None,
                     "stage": m.group(4) if m.group(4) else None})
    return rows, bad


def summarize(rows, limit=LIMIT_MS):
    """纯函数：给观测 ⇒ 结论。`--selftest` 直接喂夹具验它。"""
    if not rows:
        return {"n": 0, "verdict": "no_reading",
                "why": "**没有观测** ⇒ 判不了（**不许当成达标**）"}
    # ★ 2026-10-20：**只拿真 ingress 的读数判达标**。旧口径的行照旧计入样本量，但不参与判定，
    #   否则新老两套口径混在一起，说出来的数既不诚实也不可比。
    honest = [r for r in rows if r.get("ingress") == "create_time"]
    n_legacy = len(rows) - len(honest)
    if not honest:
        # ★ 2026-10-20：**只有旧口径读数 ⇒ 判不了**，不是"达标"也不是"未达标"。
        #   旧口径（`handleMessage` 拿不到 tIngress，退化成"进闸门那一刻"）量的根本不是
        #   PRD §12 说的那一段；拿它判绿就是 10-20 之前那个错，判红则是拿旧尺子量新问题。
        return {"n": 0, "verdict": "no_reading", "n_all": len(rows), "legacy_n": n_legacy,
                "why": "只有**旧口径**读数（%d 条，无 `ingress=create_time`）⇒ 判不了；"
                       "要等重启后的下一次真实送审产生新口径观测" % n_legacy}
    basis = honest
    v = sorted(r["group_response_ms"] for r in basis)
    over = [x for x in v if x > limit]
    prep = sorted(r["prep_ms"] for r in rows if r.get("prep_ms") is not None)
    return {"n": len(v), "min": v[0], "median": int(statistics.median(v)), "max": v[-1],
            "p_over": len(over), "limit_ms": limit,
            # ★ 2026-10-20：`prep_ms` = 消息到达 → 进闸门（读素材那段）。没有这列就是「未测」，不许当 0。
            "prep_median": int(statistics.median(prep)) if prep else None,
            "prep_n": len(prep),
            "honest_n": len(honest), "legacy_n": n_legacy,
            "n_all": len(rows),
            "basis": "create_time",
            "verdict": "pass" if not over else "FAIL",
            "why": ("全部 ≤ %d ms" % limit) if not over else
                   ("%d/%d 条超 %d ms（最慢 %d ms）" % (len(over), len(v), limit, v[-1]))}


def run(path=DEFAULT_LOG):
    print("飞书群 @Agent 响应时延 —— 目标 19 后半（PRD §12 可用性行「≤ 5 秒」）")
    print("口径：**消息到达（飞书 create_time）** → **回执卡发送完成**；"
          "回执在读素材之前发（stage=early）；整链耗时不计入本条\n")
    if not os.path.exists(path):
        print("读不到守衡日志：%s" % path)
        print("⇒ 判不了。**这不等于达标** —— 要先把埋点跑到（重启守衡后产生真实送审）。")
        return 2
    text = io.open(path, encoding="utf-8", errors="ignore").read()
    rows, bad = parse(text)
    s = summarize(rows)
    if bad:
        print("⚠️ 有 %d 行带 [metric] 但解析不了（字段名变了？）—— 已跳过，未计入。" % bad)
    if s["verdict"] == "no_reading":
        print("观测数：0 ⇒ %s" % s["why"])
        if s.get("legacy_n"):
            print("   （旧口径 %d 条仍在，但**不计入判定**；它们量的是「进闸门之后」，不是「消息到达」。）"
                  % s["legacy_n"])
        print("   埋点已就位（agent.mjs 回执卡处）；**要等一次真实送审**才会产生观测。")
        return 3
    print("观测数 %d ｜ min %d ms ｜ **中位 %d ms** ｜ max %d ms ｜ 门槛 %d ms"
          % (s["n"], s["min"], s["median"], s["max"], s["limit_ms"]))
    if s.get("legacy_n"):
        print("⚠️ 另有 %d 条**旧口径**读数（无 `ingress=create_time`，量的是「进闸门之后」）"
              "—— 已排除在判定之外，不许拿来当达标依据（2026-10-20 之前那批）。" % s["legacy_n"])
    elif s.get("honest_n"):
        print("口径来源：%d 条全部带 `ingress=create_time`（飞书服务端的消息时刻）✅" % s["honest_n"])
    print("结论：%s —— %s" % ("✅ 达标" if s["verdict"] == "pass" else "❌ 未达标", s["why"]))
    if s.get("prep_median") is not None:
        print("其中「读素材那一段」（prep_ms，%d 条）：中位 %d ms —— 回执前置之后它**不该**再算进响应时延。"
              % (s["prep_n"], s["prep_median"]))
    print("★ 边界：只报 min/中位/max，**不声称 P95/P99**（样本量不足时不编统计置信度）。")
    return 0 if s["verdict"] == "pass" else 3


def selftest():
    res = []

    def ck(n, c, ex=""):
        res.append((n, bool(c), ex))

    # 新口径（2026-10-20 起）：带 `prep_ms` / `stage` / `ingress=create_time`
    ok_text = ("[agent] 处理一条\n"
               "[metric] group_response_ms=812 ack_decision_ms=760 prep_ms=52 prd_limit_ms=5000"
               " verdict=pass stage=early ingress=create_time chat=oc_x\n"
               "[metric] group_response_ms=1503 ack_decision_ms=1401 prep_ms=102 prd_limit_ms=5000"
               " verdict=pass stage=early ingress=create_time chat=oc_x\n")
    rows, bad = parse(ok_text)
    s = summarize(rows)
    ck("① 解析：2 行观测、0 行解析失败", len(rows) == 2 and bad == 0, "n=%d bad=%d" % (len(rows), bad))
    ck("①b 中位数算对（812/1503 → 1157）", s["median"] == 1157, "median=%s" % s.get("median"))
    ck("② 未超门槛 ⇒ pass", s["verdict"] == "pass", s["verdict"])
    # ★ 反向对照：**判据不是恒 pass** —— 喂一条超 5s 的，必须 FAIL
    over_text = ok_text + ("[metric] group_response_ms=9100 ack_decision_ms=120 prep_ms=0"
                           " prd_limit_ms=5000 verdict=FAIL stage=early ingress=create_time chat=oc_x\n")
    s2 = summarize(parse(over_text)[0])
    ck("③ 反向对照：一条 9100ms ⇒ 精确判 FAIL（判据不是恒真）",
       s2["verdict"] == "FAIL" and s2["p_over"] == 1, s2["verdict"])
    # ★ 反向对照：**空观测不许当达标**
    s3 = summarize([])
    ck("④ 反向对照：无观测 ⇒ no_reading（**不许当达标**）",
       s3["verdict"] == "no_reading", s3["verdict"])
    # ★ 反向对照：字段名变了 ⇒ 解析失败要看得见（不许静默当成"没有观测"）
    _r, b2 = parse("[metric] resp=100\n[metric] group_response_ms=abc\n")
    ck("⑤ 反向对照：坏行被计数（不许静默）", b2 == 2, "bad=%d" % b2)
    # ★ 2026-10-20（回执前置 + 真 ingress）：新字段要能被解析，缺列要看得见「未测」
    new_text = ("[metric] group_response_ms=900 ack_decision_ms=0 prep_ms=24200 prd_limit_ms=5000"
                " verdict=pass stage=early ingress=create_time chat=oc_x\n")
    rn, bn = parse(new_text)
    ck("⑦ 新格式（带 prep_ms / stage / ingress）解析成功",
       len(rn) == 1 and bn == 0 and rn[0]["prep_ms"] == 24200 and rn[0]["ingress"] == "create_time",
       "rows=%s bad=%d" % (rn, bn))
    sn = summarize(rn)
    ck("⑧ prep_ms 进汇总（24200）", sn.get("prep_median") == 24200, "prep_median=%s" % sn.get("prep_median"))
    # 老读法：带 ingress 但**没有 prep_ms**（0.383/1.401 那批形态）⇒ prep 记未测
    no_prep = ("[metric] group_response_ms=1401 ack_decision_ms=383 prd_limit_ms=5000"
               " stage=gate ingress=create_time chat=oc_x\n")
    so = summarize(parse(no_prep)[0])
    ck("⑨ 反向对照：无 prep_ms 时 prep 记 **未测**（None），不许当 0",
       so.get("prep_median") is None and so.get("prep_n") == 0,
       "prep_median=%s n=%s" % (so.get("prep_median"), so.get("prep_n")))
    # ★ 反向对照：**只有旧口径读数 ⇒ 判不了**（不许拿"进闸门之后"的数判达标）
    legacy_text = ("[metric] group_response_ms=812 ack_decision_ms=760 prd_limit_ms=5000"
                   " verdict=pass chat=oc_x\n")
    s_legacy = summarize(parse(legacy_text)[0])
    ck("⑩ 反向对照：只有旧口径读数（无 ingress）⇒ no_reading（不许当达标）",
       s_legacy["verdict"] == "no_reading", s_legacy.get("verdict"))
    ck("⑪ 新口径读数 ⇒ 正常判（900ms ∈ ≤5000 ⇒ pass）",
       summarize(parse(new_text)[0])["verdict"] == "pass", "pass")
    # ⑥ 变异测试：把门槛放宽到 99999 ⇒ ③ 必须精确变假
    s4 = summarize(parse(over_text)[0], limit=99999)
    ck("⑥ 变异测试：门槛放宽到 99999 ⇒ ③ 精确变假", s4["verdict"] == "pass", s4["verdict"])
    print("measure_group_response --selftest（目标 19 后半）")
    for n, c, ex in res:
        print("  %s %s%s" % ("✅" if c else "❌", n, ("　｜ " + ex) if ex else ""))
    bad_n = sum(1 for _, c, _e in res if not c)
    print("结果：%d/%d%s" % (len(res) - bad_n, len(res), "" if not bad_n else "  ← 有失败"))
    return 1 if bad_n else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--log", default=DEFAULT_LOG)
    a = ap.parse_args()
    sys.exit(selftest() if a.selftest else run(a.log))
