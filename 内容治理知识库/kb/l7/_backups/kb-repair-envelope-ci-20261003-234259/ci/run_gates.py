#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""run_gates.py —— 把 kb/l7/scripts 下的闸门脚本收成一个**可被 CI / 定时任务调用**的统一入口。

## 它解决什么

八把层闸门（l0_gate.py … l7_gate.py）加上四把家族闸门（skills_check / layers_check /
skill_conformance / freshness）各说各的退出码、各打各的屏。CI 与 launchd 需要的是：
**一次调用、一张表、一个可判定的退出码、一份机读产物**。

## 退出码（CI 就照这个判）

  0  全过（所有 blocking 闸门 exit 0）
  1  有闸门判红（exit 1）
  2  有闸门「无法计算」（exit 2）—— 与红**分档**：红是数据不对，2 是判据算不出来
  3  runner 自身故障（找不到 kbpy / 超时以外的基础设施问题）

## 与库内纪律的关系（三条，没省）

1. **只读**：本 runner 只调闸门脚本，不传 `--apply`，不碰 `kb/l0…l6` 数据与台账。
   （`l5_gate` 会写它自己的 `kb/.work/l5_integrity.json` —— 那是自检器的证据件，不是层产物，
   闸门自己已在该文件头注明。）
2. **不抢锁**：本 runner **不调** `kb_loop_claim.py`、**不调** `kb_pipeline.py --apply`。
   因此它可以在 CI 上随时跑，不与每日 08:30 的写档循环抢 `kb/.work/.kb.lock`。
3. **freshness 不 blocking**：`freshness.py` 的退出码 3 是「供给链超期」，
   库内口径写明「超期是**去跑链路**的理由，不是拒答的理由」。
   → 本 runner 把它记为 PASS_WITH_WARN，**不**让 CI 变红（否则红灯会变成没人看的噪音）。

用法：
    python3 ci/run_gates.py                 # 跑全部，人看表
    python3 ci/run_gates.py --json          # 额外打印机读汇总
    python3 ci/run_gates.py --outdir ci/out # 落盘 JSON + Markdown 报告
    python3 ci/run_gates.py --only l0 l4 l7 # 只跑指定几把
    python3 ci/run_gates.py --strict-warn   # 把 WARN 也算失败（用于发布前门禁）
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
KB_ROOT = os.path.dirname(HERE)          # 含 KB-ROOT.json 的那一层（权威库根）
KB_DIR = os.path.join(KB_ROOT, "kb")     # kb/ 本体：kbpy 的脚本路径基准
KBPY = os.path.join(KB_DIR, "kbpy")

# 每把闸门：id、脚本路径、是否 blocking、说明
#
# ⚠️ 路径口径（实测踩过，2026-10-03）：`kb/kbpy` 内部 `cd` 到自己的目录（即 `kb/`），
#    所以它接收的脚本路径是**相对 `kb/`** 的 —— 传 `kb/l7/scripts/l0_gate.py` 会被拼成
#    `kb/kb/l7/scripts/l0_gate.py` 并报「找不到脚本」。
#    → 此处存**相对 `kb/`** 的路径（`KBPY_REL`）；要拼库根绝对路径时走 `os.path.join(KB_DIR, …)`。
#
# ⚠️ 参数**不统一**（实测踩过，2026-10-03）：八把层闸门支持 `--json --quiet`，
#    但 `freshness.py` **没有 `--quiet`** —— 传了会 argparse 报错、退出码 2（看起来像"判据算不出来"）。
#    → 每把闸门自带 flags，别假设「大家都一样」。
DEFAULT_FLAGS = ["--json", "--quiet"]

GATES = [
    ("l0", "l7/scripts/l0_gate.py", True, DEFAULT_FLAGS, "L0 判定档：原始差异 − 预期 = 真差异"),
    ("l1", "l7/scripts/l1_gate.py", True, DEFAULT_FLAGS, "L1 独立复算：OCR 缓存复用门槛逐条核"),
    ("l2", "l7/scripts/l2_gate.py", True, DEFAULT_FLAGS, "L2 独立复算：unit_count 口径逐条点名"),
    ("l3", "l7/scripts/l3_gate.py", True, DEFAULT_FLAGS, "L3 独立复算：证据可回指 L2 单元"),
    ("l4", "l7/scripts/l4_gate.py", True, DEFAULT_FLAGS, "L4 独立复算：promotion_rule C1–C6"),
    ("l5", "l7/scripts/l5_gate.py", True, DEFAULT_FLAGS, "L5 包装分类：实质 4 项 + 基线项登记"),
    ("l6", "l7/scripts/l6_gate.py", True, DEFAULT_FLAGS, "L6 只读档：可用单元/向量/倒排/版本纪律"),
    ("l7", "l7/scripts/l7_gate.py", True, DEFAULT_FLAGS, "L7 引用契约前置条件"),
    ("skills", "l7/scripts/skills_check.py", True, DEFAULT_FLAGS, "登记表自检：应装未装 / 副本不一致"),
    ("layers", "l7/scripts/layers_check.py", True, DEFAULT_FLAGS, "layers.yaml 层契约表自检"),
    ("conformance", "l7/scripts/skill_conformance.py", True, DEFAULT_FLAGS,
     "四方对账：文本↔注册表↔层契约↔磁盘"),
    ("freshness", "l7/scripts/freshness.py", False, ["--json"],
     "供给链新鲜度（超期=去跑链路的理由，不是红灯）"),
]

STATE_BY_EXIT = {0: "PASS", 1: "RED", 2: "BLOCKED", 124: "TIMEOUT", 127: "NO_RUNNER"}


def _parse_json_tail(text: str):
    """闸门用 --json 时把 JSON 混在人类可读屏里；取最后一个平衡的 {...} 块。"""
    start = text.find("{")
    while start != -1:
        depth = 0
        in_str = False
        esc = False
        for i in range(start, len(text)):
            ch = text[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start:i + 1])
                    except Exception:
                        break
        start = text.find("{", start + 1)
    return None


def run_one(gate_id, rel_path, blocking, flags, desc, timeout):
    # 存在性检查用**库根**拼绝对路径；喂给 kbpy 的仍是相对 kb/ 的路径（见 GATES 注释）
    script_abs = os.path.join(KB_DIR, rel_path)
    started = time.time()
    rec = {
        "gate": gate_id,
        "script": rel_path,
        "blocking": blocking,
        "desc": desc,
        "exit": None,
        "state": None,
        "red_total": None,
        "ok_field": None,
        "seconds": 0.0,
        "stderr": "",
        "json": None,
        "tail": "",
    }

    if not os.path.exists(KBPY):
        rec.update(state="NO_RUNNER", exit=127,
                   stderr="找不到 %s（kbpy 是库内约定的解释器入口）" % KBPY)
        return rec
    if not os.path.exists(script_abs):
        rec.update(state="MISSING_SCRIPT", exit=127,
                   stderr="脚本不存在：%s" % script_abs)
        return rec

    cmd = [KBPY, rel_path] + list(flags)
    try:
        p = subprocess.run(cmd, cwd=KB_ROOT, capture_output=True,
                           text=True, timeout=timeout)
        out, err, rc = p.stdout or "", p.stderr or "", p.returncode
    except subprocess.TimeoutExpired as e:
        out = (e.stdout or b"").decode("utf-8", "replace") if isinstance(e.stdout, bytes) else (e.stdout or "")
        err = "超时 %ss" % timeout
        rc = 124
    except Exception as e:                                    # noqa: BLE001
        out, err, rc = "", "runner 调用失败：%r" % (e,), 127

    rec["exit"] = rc
    rec["seconds"] = round(time.time() - started, 1)
    rec["stderr"] = err.strip()[-400:]
    rec["tail"] = "\n".join(out.strip().splitlines()[-8:])[-1200:]

    if rc not in STATE_BY_EXIT:
        rec["state"] = "FAILED"
    else:
        rec["state"] = STATE_BY_EXIT[rc]

    parsed = _parse_json_tail(out)
    if parsed:
        rec["json"] = parsed
        rec["ok_field"] = parsed.get("ok")
        for key in ("red_total", "real_diff_total", "C1_n"):
            if key in parsed and isinstance(parsed[key], int):
                rec["red_total"] = parsed[key]
                break
        if rc == 0 and rec["ok_field"] is False:
            rec["state"] = "RED"
            rec["note"] = "退出码 0 但 JSON ok=false —— 以 ok 为准，判红"
    elif rc == 0:
        rec["state"] = "PASS"

    # 非 blocking 闸门的分档（**不许静默**）：
    #   · 退出码 3 = 业务意义上的"超期/注意"（freshness 的口径）→ WARN
    #   · 退出码 1/2 = 该闸门自己就没跑成（数据红或判据算不出来）→ ERROR
    #   两者都进汇总，只是不单独把 CI 打红（除非 --strict-warn）。
    if not blocking:
        if rc == 3:
            rec["state"] = "WARN"
        elif rc in (1, 2):
            rec["state"] = "ERROR"
            rec["note"] = rec.get("note") or "非 blocking 闸门自己报错（退出码 %s），需人看" % rc
    return rec


def main():
    ap = argparse.ArgumentParser(description="KB 闸门统一入口（只读；供 CI / 定时任务调用）")
    ap.add_argument("--json", action="store_true", help="额外打印机读汇总")
    ap.add_argument("--outdir", default=None, help="落盘 JSON + Markdown 报告到这个目录")
    ap.add_argument("--only", nargs="*", default=None, help="只跑这些 gate id")
    ap.add_argument("--timeout", type=int, default=600, help="单把闸门超时秒数（默认 600）")
    ap.add_argument("--strict-warn", action="store_true",
                    help="把 PASS_WITH_WARN（如 freshness 超期）也当失败")
    args = ap.parse_args()

    selected = [g for g in GATES if not args.only or g[0] in args.only]
    if not selected:
        print("没有匹配的闸门：%s" % args.only, file=sys.stderr)
        return 3

    print("=" * 74)
    print("KB 闸门统一入口  ｜ 库根 %s" % KB_ROOT)
    print("共 %d 把 ｜ 单把超时 %ss ｜ 本 runner 只读、不抢锁、不传 --apply" % (len(selected), args.timeout))
    print("=" * 74)

    results = []
    for gate_id, rel, blocking, flags, desc in selected:
        rec = run_one(gate_id, rel, blocking, flags, desc, args.timeout)
        results.append(rec)
        mark = {"PASS": "✅", "WARN": "⚠️", "ERROR": "🔶", "RED": "❌",
                "BLOCKED": "⛔", "TIMEOUT": "⏱️", "FAILED": "💥",
                "MISSING_SCRIPT": "💥", "NO_RUNNER": "💥"}.get(rec["state"], "?")
        extra = ""
        if rec["red_total"] is not None:
            extra = " ｜ 红 %s" % rec["red_total"]
        if rec["state"] == "BLOCKED":
            extra += " ｜ 判据算不出来（不是数据错）"
        print("%s %-12s %-16s %5.1fs%s" % (mark, gate_id, rec["state"], rec["seconds"], extra))
        if rec["state"] in ("RED", "BLOCKED", "FAILED", "TIMEOUT", "MISSING_SCRIPT", "NO_RUNNER"):
            if rec["tail"]:
                for line in rec["tail"].splitlines()[-4:]:
                    print("      │ %s" % line[:150])
        if rec["stderr"] and rec["state"] != "PASS":
            print("      │ stderr: %s" % rec["stderr"][:150])

    blocking_results = [r for r in results if r["blocking"]]
    red = [r["gate"] for r in blocking_results if r["state"] == "RED"]
    blocked = [r["gate"] for r in blocking_results if r["state"] == "BLOCKED"]
    infra = [r["gate"] for r in blocking_results
             if r["state"] in ("FAILED", "TIMEOUT", "MISSING_SCRIPT", "NO_RUNNER")]
    warn = [r["gate"] for r in results if r["state"] == "WARN"]
    errored = [r["gate"] for r in results if r["state"] == "ERROR"]
    passed = [r["gate"] for r in results if r["state"] == "PASS"]

    if red:
        code = 1
    elif blocked:
        code = 2
    elif infra or errored:
        code = 3
    elif warn and args.strict_warn:
        code = 1
    else:
        code = 0

    print("-" * 74)
    print("汇总：过 %d/%d ｜ 红 %s ｜ 无法计算 %s ｜ 非 blocking 报错 %s ｜ 基础设施 %s ｜ 告警 %s"
          % (len(passed), len(results), red or "无", blocked or "无",
             errored or "无", infra or "无", warn or "无"))
    print("退出码 %d ｜ %s" % (code, {
        0: "全过（告警不算失败；要严格加 --strict-warn）",
        1: "有红", 2: "有『无法计算』（判据算不出来，不是数据错）", 3: "runner 故障 / 非 blocking 闸门自身报错",
    }[code]))
    print("=" * 74)

    payload = {
        "runner": "kb-ci-run-gates",
        "kb_root": KB_ROOT,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "exit_code": code,
        "summary": {"passed": passed, "red": red, "blocked": blocked,
                    "errored": errored, "infra": infra,
                    "warn": warn, "total": len(results)},
        "gates": results,
    }

    if args.outdir:
        os.makedirs(args.outdir, exist_ok=True)
        jp = os.path.join(args.outdir, "gates-latest.json")
        with open(jp, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=1)
        mp = os.path.join(args.outdir, "gates-latest.md")
        lines = [
            "# KB 闸门体检 ｜ %s" % payload["generated_at"],
            "",
            "库根：`%s`" % KB_ROOT,
            "",
            "| 闸门 | 状态 | 退出码 | 红数 | 耗时 | 说明 |",
            "|---|---|---|---|---|---|",
        ]
        for r in results:
            lines.append("| %s | %s | %s | %s | %ss | %s |" % (
                r["gate"], r["state"], r["exit"],
                "-" if r["red_total"] is None else r["red_total"],
                r["seconds"], r["desc"]))
        lines += ["", "**退出码 %d** ｜ 红：%s ｜ 无法计算：%s ｜ 告警：%s" % (
            code, red or "无", blocked or "无", warn or "无")]
        with open(mp, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
        print("报告已落盘：\n  %s\n  %s" % (jp, mp))

    if args.json:
        print(json.dumps({k: v for k, v in payload.items() if k != "gates"},
                         ensure_ascii=False, indent=1))

    return code


if __name__ == "__main__":
    sys.exit(main())
