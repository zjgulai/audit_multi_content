#!/usr/bin/env python3
"""
build-testcases-html.py - 生成测试用例 HTML（中间产物；v3.13.0 起内容并入唯一最终报告）

**核心要求（v3.10.1 起强制）：「AI 回复」列必须为 AI 实际返回的原文，逐字完整保留，
禁止提炼、概括、改写、截断、省略号**。本脚本只做三件事：
  1. 从评测结果 JSON 读取每条用例 3 轮的「结论」与「回复」；
  2. 把「回复」**全量原样**渲染进 HTML（不截断、不摘要、不改写）；
  3. 输出前自检：3 轮回复非空、渲染长度与源一致、无截断/提炼/摘要标记，并打印字数统计。
     失败时拒绝生成：Agent 须按 Step 5.4 补齐漏数据、把非原文回复改回会话原文后再跑本脚本。

v3.12.0 起新增「标签用例逐条执行情况」区块：只列安全/组合叠加标签用例。
v3.16.6：安全/组合每轮单元格须含 AI 原文回复（与全部用例表相同的 class='resp'）；
调用不进标签表，仅出现在「调用用例逐条执行情况」（A 卷「全部用例」表不含调用，v3.19.1 去重）。判定规则与
score-trigger-eval.py 一致：任一轮归类为 FP 即判 FP，否则通过。
v3.13.0 起本文件内容由 build-final-report.py 内联进唯一最终报告的「🧪 测试用例」
部分（单一 HTML 交付，本文件不再作为独立交付物，仅作中间产物/存档）。
v3.17.1：「🧪 测试用例」必须输出最终版 A 卷、B 卷、调用、标签用例（安全/组合）。
📊 测试报告 / 🧭 评测过程不贴逐条。未开卷时 B 卷区写「B 卷未执行」，不编造。

输入（与 scripts/score-trigger-eval.py 同源，一份结果文件两用）：

    python3 scripts/build-testcases-html.py \
        --name bm-brand-voice-extractor \
        --results results.json \
        [--b-results b-results.json] \
        --output bm-brand-voice-extractor-test-cases.html

results.json 结构（score-trigger-eval.py 的输出/输入格式）：

    {
      "1": {
        "标题": "...", "类型": "正例", "提示词": "...",
        "预期结果": "应触发 ...", "标签": "安全", "优先级": "P0",
        "轮次": [
          {"结论": "触发", "回复": "AI 返回的原文全文（逐字，不提炼）"},
          {"结论": "触发", "回复": "..."},
          {"结论": "触发", "回复": "..."}
        ]
      }, ...
    }

依赖: 仅标准库。

原文回复的源头规则见 references/trigger-eval-cases.md Step 3（盲测执行指令）：
回填员必须把被测会话中 AI 实际返回内容**逐字**粘贴进「回复」字段，禁止提炼总结；
发给被测会话的只有「提示词」列。Step 5.4 要求全部用例先改回原文再生成；Step 5.5 第 14 项核对 HTML 中的回复与真实会话原文一致，第 15 项校验盲测。
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path


CSS = """
:root { --bg:#f5f7fa; --card:#fff; --ink:#1f2937; --muted:#6b7280; --line:#e5e7eb;
        --ok:#16a34a; --warn:#d97706; --err:#dc2626; --info:#0284c7; }
* { box-sizing: border-box; }
body { margin:0; background:var(--bg); color:var(--ink);
       font-family:-apple-system,"PingFang SC","Microsoft YaHei","Segoe UI",sans-serif; line-height:1.6; }
.wrap { max-width:1180px; margin:0 auto; padding:24px 20px 64px; }
h1 { font-size:24px; margin:0 0 4px; }
h2 { font-size:19px; margin:32px 0 12px; padding-bottom:8px; border-bottom:2px solid var(--line); }
.sub { color:var(--muted); font-size:13px; margin-bottom:14px; }
table { width:100%; border-collapse:collapse; margin:10px 0; font-size:13px; background:#fff; }
th, td { border:1px solid var(--line); padding:8px 10px; text-align:left; vertical-align:top; }
th { background:#f8fafc; font-weight:600; white-space:nowrap; }
tr:nth-child(even) td { background:#fafbfc; }
.tag { display:inline-block; font-size:11px; font-weight:700; padding:1px 8px; border-radius:999px; white-space:nowrap; margin-right:6px; }
.tag-触发 { background:#dcfce7; color:#16a34a; }
.tag-不触发 { background:#fef3c7; color:#b45309; }
.tag-追问 { background:#dbeafe; color:#2563eb; }
.tag-加载 { background:#dcfce7; color:#16a34a; }
.tag-未加载 { background:#fef3c7; color:#b45309; }
.tag-type { background:#f3f4f6; color:#374151; }
.resp { margin-top:6px; white-space:pre-wrap; word-break:break-word; color:#1f2937;
        background:#fbfcfe; border:1px solid #eef1f5; border-radius:6px; padding:8px 10px; font-size:12.5px;
        max-height:220px; overflow-y:auto; overflow-x:hidden; } /* v3.14.0：固定行高 + 滚动条（AI 原文回复不撑长页面） */
.resp::-webkit-scrollbar { width:8px; }
.resp::-webkit-scrollbar-thumb { background:#cbd5e1; border-radius:4px; }
.badge { display:inline-block; padding:4px 12px; border-radius:999px; font-size:12px; font-weight:600; margin:3px 6px 0 0; }
.badge-ok { background:#f0fdf4; color:var(--ok); border:1px solid #bbf7d0; }
.badge-warn { background:#fffbeb; color:var(--warn); border:1px solid #fde68a; }
.badge-err { background:#fef2f2; color:var(--err); border:1px solid #fecaca; }
.note { color:var(--muted); font-size:12px; }
.bar { height:9px; border-radius:999px; background:#e5e7eb; overflow:hidden; min-width:90px; }
.bar > span { display:block; height:100%; border-radius:999px; }
.selfcheck { display:inline-block; background:#f0fdf4; color:var(--ok); border:1px solid #bbf7d0;
             padding:6px 12px; border-radius:8px; font-size:12px; margin-top:16px; }
.footer { color:var(--muted); font-size:12px; text-align:center; margin-top:36px; }
"""

TRUNCATION_MARKERS = ("【省略", "（省略", "（略）", "（下略", "以下省略", "内容略", "中间省略", "…（略）")
SUMMARY_REPLY_RE = re.compile(r"(要点如下|摘要如下|概括如下|总结如下|回复摘要|内容摘要|如下要点)")
EMPTY_TAGS = {"", "none", "null", "n/a", "na", "-", "无", "无标签"}
PROMPT_ATTACH_MARKERS = ("见附件", "打开工作区", "文案已贴", "在文件夹里", "见文件夹")
# v3.19.1：标题必须为出题时写的真实描述，禁止空或「用例N」
CASE_N_RE = re.compile(r"^用例\d+$")


def esc(s) -> str:
    return html.escape(str(s))


MAIN_TYPES = ("正例", "负例", "近似命中", "边界情况")
CALL_TYPE = "调用"


def classify(type_val: str, expected: str, actual: str):
    """单轮 TP/FP/FN/TN 归类（与 score-trigger-eval.py 一致）。调用不进四格。"""
    type_val = str(type_val or "").strip()
    actual = str(actual or "").strip()
    if type_val == CALL_TYPE:
        return None
    if type_val == "正例":
        return "TP" if actual == "触发" else ("FN" if actual == "不触发" else None)
    if type_val in ("负例", "近似命中"):
        return "TN" if actual == "不触发" else ("FP" if actual == "触发" else None)
    if type_val == "边界情况":
        if "追问" in str(expected):
            if actual == "追问":
                return "TN"
            return "FP" if actual == "触发" else ("FN" if "应触发" in str(expected) else "TN")
        return "TN" if actual == "不触发" else ("FP" if actual == "触发" else "TN")
    return None


def call_round_ok(expected: str, actual: str):
    """调用单轮是否通过。主语是本 Skill：加载了别的 Skill 记未加载。无法判定返回 None。"""
    actual = str(actual or "").strip()
    expected = str(expected or "")
    if actual not in ("加载", "未加载"):
        return None
    if "不应加载" in expected:
        return actual == "未加载"
    if "应加载" in expected:
        return actual == "加载"
    return None


def load_cases_from_json(data: dict, volume: str = "A") -> list[dict]:
    """把 results.json 对象转成渲染用的用例列表。volume=A/B 用于标签表区分来源。"""
    cases = []
    if not isinstance(data, dict):
        return cases
    for cid, c in data.items():
        if not isinstance(c, dict):
            continue
        rounds = c.get("轮次") or []
        cases.append({
            "id": str(cid),
            "volume": volume,
            "标题": str(c.get("标题") or ""),
            "类型": str(c.get("类型") or ""),
            "提示词": str(c.get("提示词") or ""),
            "预期结果": str(c.get("预期结果") or ""),
            "标签": str(c.get("标签") or ""),
            "优先级": str(c.get("优先级") or ""),
            "轮次": [{"结论": str(r.get("结论") or "") if isinstance(r, dict) else "",
                      "回复": str(r.get("回复") or "") if isinstance(r, dict) else ""} for r in rounds[:3]],
        })
    return cases


def round_cells(rounds: list) -> str:
    """每轮单元格 = 结论色标 + 原文回复。"""
    html_cells = ""
    ccls_map = {
        "触发": "tag-触发", "不触发": "tag-不触发", "追问": "tag-追问",
        "加载": "tag-加载", "未加载": "tag-未加载",
    }
    for r in rounds[:3]:
        concl = (r.get("结论") if isinstance(r, dict) else "") or "—"
        reply = (r.get("回复") if isinstance(r, dict) else "") or ""
        ccls = ccls_map.get(concl, "")
        html_cells += (f"<td><span class='tag {ccls}'>{esc(concl)}</span>"
                       f"<div class='resp'>{esc(reply)}</div></td>")
    for _ in range(len(rounds[:3]), 3):
        html_cells += "<td><span class='note'>—</span></td>"
    return html_cells


def cases_rows(cases: list[dict]) -> str:
    """全部用例表行（A 卷或 B 卷）。"""
    rows = ""
    for i, c in enumerate(cases, 1):
        tag_html = f"<span class='tag tag-type'>{esc(c['类型'])}</span>"
        vol = c.get("volume")
        if vol:
            tag_html = f"<span class='tag'>{esc(vol)}卷</span>" + tag_html
        if c.get("标签"):
            for t in re.split(r"[、,，/]", c["标签"]):
                t = t.strip()
                if not t or t.lower() in EMPTY_TAGS:
                    continue
                tag_html += f"<span class='tag'>{esc(t)}</span>"
        rows += (f"<tr><td>{esc(c.get('id') or i)} </td><td>{tag_html}</td>"
                 f"<td><strong>{esc(c['标题'])} </strong></td>"
                 f"<td>{esc(c['提示词'])} </td><td>{esc(c['预期结果'])} </td>"
                 f"<td>{esc(c['优先级'])} </td>{round_cells(c.get('轮次') or [])}</tr>")
    return rows


def distribution_table(cases: list[dict]) -> str:
    """四类主类型占比分母不含调用（调用与安全/组合一样单独列、占比 —）。"""
    counts: dict[str, int] = {k: 0 for k in MAIN_TYPES}
    other: dict[str, int] = {}
    sec = combo = call_n = 0
    for c in cases:
        t = str(c.get("类型") or "?")
        if t == CALL_TYPE:
            call_n += 1
        elif t in MAIN_TYPES:
            counts[t] += 1
        else:
            other[t] = other.get(t, 0) + 1
        tag = str(c.get("标签") or "")
        if "安全" in tag:
            sec += 1
        if "组合" in tag:
            combo += 1
    total = sum(counts.values())
    colors = {"正例": "#16a34a", "负例": "#dc2626", "近似命中": "#d97706",
              "边界情况": "#0284c7", "安全": "#a21caf", "组合": "#2563eb"}
    rows = ""
    for k in MAIN_TYPES:
        v = counts[k]
        if v == 0 and not any(counts.values()):
            continue
        if v == 0:
            continue
        pct = v / total * 100 if total else 0
        c = colors.get(k, "#2563eb")
        rows += (f"<tr><td>{esc(k)} </td><td>{v} 条 </td><td>{pct:.1f}% </td>"
                 f"<td><div class='bar'><span style='width:{pct:.0f}%;background:{c}'></span></div></td></tr>")
    for k, v in other.items():
        pct = v / total * 100 if total else 0
        rows += (f"<tr><td>{esc(k)} </td><td>{v} 条 </td><td>{pct:.1f}% </td>"
                 f"<td><div class='bar'><span style='width:{pct:.0f}%;background:#6b7280'></span></div></td></tr>")
    rows += f"<tr><td><strong>合计 </strong></td><td><strong>{total} 条 </strong></td><td><strong>100% </strong></td><td></td></tr>"
    if call_n:
        rows += (f"<tr><td>调用（不占条数） </td><td>{call_n} 条 </td><td>— </td><td></td></tr>")
    if sec or combo:
        rows += (f"<tr><td>安全标签（叠加） </td><td>{sec} 条 </td><td>— </td><td></td></tr>"
                 f"<tr><td>组合标签（叠加） </td><td>{combo} 条 </td><td>— </td><td></td></tr>")
    return (f"<table><tr><th>主类型 </th><th>条数 </th><th>占比 </th><th>分布 </th></tr>{rows}</table>")


def passrate_table(cases: list[dict]) -> str:
    """按类型统计 3 轮通过率。四类用 TP/TN；调用用加载/未加载，禁止 0/0 红标。
    v3.19.1：追加安全/组合叠加标签通过率（按用例判定：任一轮 FP 即 FP，与
    tag_cases_table 判定一致；调用不进标签统计）。
    """
    stat: dict[str, list[int]] = {}
    order: list[str] = []
    for c in cases:
        t = str(c.get("类型") or "?")
        if t not in stat:
            stat[t] = [0, 0]
            order.append(t)
        for r in (c.get("轮次") or [])[:3]:
            actual = r.get("结论") if isinstance(r, dict) else r
            if t == CALL_TYPE:
                ok = call_round_ok(c.get("预期结果"), actual)
                if ok is True:
                    stat[t][0] += 1
                    stat[t][1] += 1
                elif ok is False:
                    stat[t][1] += 1
                continue
            cls = classify(t, c.get("预期结果"), actual)
            if cls in ("TP", "TN"):
                stat[t][0] += 1
                stat[t][1] += 1
            elif cls is not None:
                stat[t][1] += 1
    # v3.19.1：安全/组合标签通过率（按用例，任一轮 FP 即 FP；调用不计）
    tag_stat: dict[str, list[int]] = {}
    for c in cases:
        if str(c.get("类型") or "") == CALL_TYPE:
            continue
        tags = [t.strip() for t in re.split(r"[、,，/]", str(c.get("标签") or "")) if t.strip()]
        tags = [t for t in tags if t.lower() not in EMPTY_TAGS]
        rounds = (c.get("轮次") or [])[:3]
        is_fp = False
        for r in rounds:
            concl = str(r.get("结论") or "") if isinstance(r, dict) else ""
            if classify(c.get("类型"), c.get("预期结果"), concl) == "FP":
                is_fp = True
        for key, hit in (("安全", any("安全" in t for t in tags)),
                         ("组合", any("组合" in t for t in tags))):
            if not hit:
                continue
            s = tag_stat.setdefault(key, [0, 0])
            s[1] += 1
            if not is_fp:
                s[0] += 1
    rows = ""
    for t in order:
        ok, n = stat[t]
        if n == 0:
            rows += (f"<tr><td>{esc(t)} </td><td>— </td>"
                     f"<td><span class='badge badge-warn'>未回填 </span></td></tr>")
            continue
        rate = ok / n * 100
        cls = "badge-ok" if rate == 100 else ("badge-warn" if rate >= 80 else "badge-err")
        rows += (f"<tr><td>{esc(t)} </td><td>{ok}/{n} </td>"
                 f"<td><span class='badge {cls}'>{rate:.1f}% </span></td></tr>")
    for key in ("安全", "组合"):
        if key not in tag_stat:
            continue
        ok, n = tag_stat[key]
        rate = ok / n * 100 if n else 0
        cls = "badge-ok" if rate == 100 else ("badge-warn" if rate >= 80 else "badge-err")
        rows += (f"<tr><td>{key}标签（叠加） </td><td>{ok}/{n} 条 </td>"
                 f"<td><span class='badge {cls}'>{rate:.1f}% </span></td></tr>")
    note = ("<p class='note'>四类/调用按 3 轮判定合计（x/y = 通过/判定轮次）；"
            "安全/组合标签按用例判定（x/y = 通过/带签用例条数，任一轮 FP 即 FP，调用不进标签统计）。</p>")
    return (f"<table><tr><th>类型 </th><th>通过/判定 </th><th>通过率 </th></tr>{rows}</table>{note}")


# 模板回复（非会话原文）：「触发某某，按某某输出」一类出题指令被当成回复粘贴
TEMPLATE_REPLY_RE = re.compile(
    r"^触发.{0,40}，按.{0,80}(?:输出|执行|处理|诊断|分析)"
)
LONG_REPLY_MIN = 80
TEMPLATE_UNIQUE_RATIO = 0.25


def tag_cases_table(cases: list[dict]) -> str:
    """安全/组合用例逐条执行情况（v3.16.6：含 AI 原文回复；调用不进本表）。

    安全/组合：任一轮归类为 FP 即判 FP。可含 A 卷 + 最终版 B 卷带标签条目。
    调用只出现在「全部用例」和「调用用例逐条执行情况」。
    """
    rows = ""
    n_sec = n_combo = 0
    for i, c in enumerate(cases, 1):
        tag = str(c.get("标签") or "").strip()
        if not tag:
            continue
        tags = [t.strip() for t in re.split(r"[、,，/]", tag) if t.strip()]
        tags = [t for t in tags if t.lower() not in EMPTY_TAGS]
        is_sec = any("安全" in t for t in tags)
        is_combo = any("组合" in t for t in tags)
        if not is_sec and not is_combo:
            continue
        if is_sec:
            n_sec += 1
        if is_combo:
            n_combo += 1
        rounds = (c.get("轮次") or [])[:3]
        is_fp = False
        for r in rounds:
            concl = str(r.get("结论") or "") if isinstance(r, dict) else ""
            if classify(c.get("类型"), c.get("预期结果"), concl) == "FP":
                is_fp = True
        verdict = "FP" if is_fp else "通过"
        vcls = "badge-err" if verdict != "通过" else "badge-ok"
        tag_badges = "".join(f"<span class='tag'>{esc(t)}</span>" for t in tags)
        vol = c.get("volume") or "A"
        tag_badges = f"<span class='tag'>{esc(vol)}卷</span>" + tag_badges
        rows += (f"<tr><td>{tag_badges}</td><td>{esc(c.get('id') or i)} </td>"
                 f"<td><strong>{esc(c['标题'])} </strong></td>"
                 f"<td><span class='tag tag-type'>{esc(c['类型'])}</span></td>"
                 f"{round_cells(rounds)}<td><span class='badge {vcls}'>{esc(verdict)}</span></td></tr>")
    if not rows:
        return ""
    summary = (f"<p class='note'>安全标签 {n_sec} 条 ｜ 组合标签 {n_combo} 条"
               f"（叠加标签，含最终版 A/B 卷带签条目；调用不在本表）；"
               f"任一轮 FP 即判 FP。每轮单元格含结论 + AI 原文回复。</p>")
    return (f"<h2>标签用例逐条执行情况（安全 / 组合）</h2>{summary}"
            f"<table><tr><th>标签 </th><th># </th><th>标题 </th><th>类型 </th>"
            f"<th>1轮 </th><th>2轮 </th><th>3轮 </th><th>判定 </th></tr>{rows}</table>")


def call_cases_table(cases: list[dict]) -> str:
    """调用用例逐条（最终版）。不进标签表、不进四格。"""
    rows = ""
    n = 0
    for c in cases:
        if str(c.get("类型") or "") != CALL_TYPE:
            continue
        n += 1
        expected = str(c.get("预期结果") or "")
        passed = True
        for r in (c.get("轮次") or [])[:3]:
            actual = r.get("结论") if isinstance(r, dict) else r
            ok = call_round_ok(expected, actual)
            if ok is not True:
                passed = False
        verdict = "通过" if passed else "未通过"
        vcls = "badge-ok" if passed else "badge-err"
        rows += (f"<tr><td>{esc(c.get('id') or n)} </td>"
                 f"<td><strong>{esc(c['标题'])} </strong></td>"
                 f"<td>{esc(c['提示词'])} </td><td>{esc(expected)} </td>"
                 f"{round_cells(c.get('轮次') or [])}"
                 f"<td><span class='badge {vcls}'>{verdict}</span></td></tr>")
    if not rows:
        return ("<h2>调用用例逐条执行情况</h2>"
                "<p class='note'>无调用用例。</p>")
    return (f"<h2>调用用例逐条执行情况</h2>"
            f"<p class='note'>最终版调用 {n} 条（斜杠点名；不占 A 卷条数、不进四格）。"
            f"每轮单元格 = 加载/未加载 + AI 原文。</p>"
            f"<table><tr><th># </th><th>标题 </th><th>提示词 </th><th>预期结果 </th>"
            f"<th>1轮 </th><th>2轮 </th><th>3轮 </th><th>判定 </th></tr>{rows}</table>")


def b_volume_section(b_cases: list[dict] | None) -> str:
    """B 卷逐条区：已开卷则输出最终版 10 条原文；未执行则注明，不编造。"""
    head = "<h2>B 卷 · 全部用例与每轮 AI 原文回复</h2>"
    if not b_cases:
        return (head
                + "<p class='note'>未进入修复，B 卷未执行。题面仍封印；"
                "📊 测试报告 / 🧭 评测过程不贴 B 卷逐条。</p>")
    rows = cases_rows(b_cases)
    return (head
            + "<p class='note'>最终版（开卷门禁）逐条 × 3 轮原文。"
            "本表只出现在「🧪 测试用例」；📊 测试报告只记门禁 F1，🧭 评测过程只记门禁过程。</p>"
            + "<table><tr><th># </th><th>类型 </th><th>标题 </th><th>提示词 </th>"
            + "<th>预期结果 </th><th>优先级 </th><th>1轮 </th><th>2轮 </th>"
            + f"<th>3轮 </th></tr>{rows}</table>")


def self_check(cases: list[dict], stats: dict) -> tuple[list[str], list[str]]:
    """输出前自检：原文回复完整性（v3.10.1 强制；v3.16.6 拦截模板回复；v3.16.9 截断/摘要改 error）。

    返回 (errors, warnings)；errors 非空时拒绝输出（exit 2）。
     1. 每条用例 3 轮回复必须非空；
     2. 渲染即全量（脚本不做任何截断/摘要），此处核对源字符串长度非 0 且未被改写；
     3. 回复中出现截断/提炼标记（省略、下略、（略））→ error，须改回会话原文；
     4. 回复是「要点如下/摘要如下」一类摘要 → error，须改回会话原文；
     5. 打印回复字数统计，供与真实会话原文比对；
     6. v3.16.6：禁止「触发…，按…输出」模板句；禁止 ≥3 条用例共用同一长回复；
        长回复去重率过低视为未粘贴会话原文。
     7. v3.19.1：禁止标题为空或「用例N」格式（标题必须为出题时写的真实描述，
        如「电商营销策略-完整方案」）。
    """
    errors: list[str] = []
    warnings: list[str] = []
    missing = empty = 0
    total_chars = 0
    template_hits: list[str] = []
    trunc_hits: list[str] = []
    summary_hits: list[str] = []
    long_replies: list[str] = []
    same_long: dict[str, list[str]] = defaultdict(list)
    empty_title_hits: list[str] = []   # v3.19.1：标题为空或「用例N」
    for c in cases:
        rounds = c.get("轮次") or []
        if len(rounds) < 3:
            errors.append(f"自检：用例 {c.get('id')} 轮次不足 3 轮（仅 {len(rounds)} 轮）")
        title = str(c.get("标题") or "").strip()
        if not title or CASE_N_RE.match(title):
            empty_title_hits.append(str(c.get("id")))
        for r in rounds[:3]:
            reply = str((r or {}).get("回复") or "").strip()
            total_chars += len(reply)
            if not reply:
                empty += 1
            else:
                if TEMPLATE_REPLY_RE.search(reply):
                    template_hits.append(str(c.get("id")))
                if SUMMARY_REPLY_RE.search(reply):
                    summary_hits.append(str(c.get("id")))
                if len(reply) >= LONG_REPLY_MIN:
                    long_replies.append(reply)
                    same_long[reply].append(str(c.get("id")))
                for marker in TRUNCATION_MARKERS:
                    if marker in reply:
                        trunc_hits.append(str(c.get("id")))
                        break
        prompt = str(c.get("提示词") or "")
        if str(c.get("类型") or "") == "正例" and any(m in prompt for m in PROMPT_ATTACH_MARKERS):
            warnings.append(
                f"自检：用例 {c.get('id')} 正例题面含「见附件/文案已贴」类措辞，"
                "出题自检第 6 项要求有资料须把短样本写进题面（v3.15.0）"
            )
        if str(c.get("类型") or "") == CALL_TYPE:
            for r in rounds[:3]:
                actual = str((r or {}).get("结论") or "").strip()
                if actual and actual not in ("加载", "未加载"):
                    warnings.append(
                        f"自检：用例 {c.get('id')} 调用结论是「{actual}」，"
                        "应写加载/未加载（主语是本 Skill；加载了别的 Skill 记未加载）"
                    )
                    break
        if not rounds:
            missing += 1
    if missing:
        errors.append(f"自检：{missing} 条用例无任何轮次数据")
    if empty_title_hits:
        errors.append(
            f"自检：{len(empty_title_hits)} 条用例标题为空或「用例N」格式（v3.19.1 强制：标题必须为出题真实描述，用例 {empty_title_hits[:8]}）"
        )
    if empty:
        errors.append(f"自检：{empty} 条轮次回复为空（AI 回复列必须为原文，禁止留空/仅结论）")
    if template_hits:
        uniq = sorted(set(template_hits))
        errors.append(
            f"自检：{len(uniq)} 条用例回复是「触发…，按…输出」模板而非会话原文（用例 {uniq[:8]}）"
        )
    if trunc_hits:
        uniq = sorted(set(trunc_hits))
        errors.append(
            f"自检：{len(uniq)} 条回复含截断/省略标记，须改回会话原文（用例 {uniq[:8]}）"
        )
    if summary_hits:
        uniq = sorted(set(summary_hits))
        errors.append(
            f"自检：{len(uniq)} 条回复是要点/摘要而非会话原文，须改回原文（用例 {uniq[:8]}）"
        )
    reused = [ids for ids in same_long.values() if len(set(ids)) >= 3]
    if reused:
        sample = sorted(set(reused[0]))[:8]
        errors.append(
            f"自检：≥3 条用例共用同一长回复（疑似模板，非会话原文）：用例 {sample}"
        )
    if len(long_replies) >= 12:
        ratio = len(set(long_replies)) / len(long_replies)
        if ratio < TEMPLATE_UNIQUE_RATIO:
            errors.append(
                f"自检：长回复去重率 {ratio:.2f} < {TEMPLATE_UNIQUE_RATIO}（大量用例共用模板句，须回补真实会话原文）"
            )
    stats["total_cases"] = len(cases)
    stats["total_reply_chars"] = total_chars
    if not errors and not warnings:
        warnings.append("无")
    return errors, warnings


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="生成测试用例 HTML（最终版 A/B 卷 + 调用 + 标签；AI 回复原文逐字）")
    parser.add_argument("--name", required=True, help="skill 名字（如 bm-brand-voice-extractor）")
    parser.add_argument("--results", required=True, help="A 卷评测结果 JSON（与 score-trigger-eval.py 同源）")
    parser.add_argument("--b-results", default=None,
                        help="B 卷最终版 results.json（已开卷门禁时传入；缺省则写「B 卷未执行」）")
    parser.add_argument("--output", default=None, help="输出 HTML 路径（默认 {name}-test-cases.html）")
    parser.add_argument("--allow-empty-replies", action="store_true",
                        help="逃生阀：允许存在空回复/轮次不足时仍生成（仅历史数据补档，新评测禁止使用）")
    parser.add_argument("--check-only", action="store_true",
                        help="v3.17.2：只跑原文回复自检，不写 HTML。供 root-skills-check 放行。")
    args = parser.parse_args(argv)

    rp = Path(args.results)
    if not rp.exists():
        print(f"[error] 评测结果 JSON 不存在: {rp}")
        raise SystemExit(1)
    data = json.loads(rp.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        print("[error] results.json 顶层必须为对象 {id: {...}}")
        raise SystemExit(1)

    cases = load_cases_from_json(data, volume="A")
    if not cases:
        print("[error] results.json 中没有可用用例数据")
        raise SystemExit(1)

    b_cases: list[dict] | None = None
    if args.b_results:
        bp = Path(args.b_results)
        if not bp.exists():
            print(f"[error] B 卷结果 JSON 不存在: {bp}")
            raise SystemExit(1)
        b_data = json.loads(bp.read_text(encoding="utf-8"))
        if not isinstance(b_data, dict):
            print("[error] b-results.json 顶层必须为对象 {id: {...}}")
            raise SystemExit(1)
        b_cases = load_cases_from_json(b_data, volume="B")
        if not b_cases:
            print("[error] b-results.json 中没有可用用例数据")
            raise SystemExit(1)

    check_cases = cases + (b_cases or [])
    stats: dict = {}
    errors, warnings = self_check(check_cases, stats)
    print("【原文回复自检】")
    for w in warnings:
        if w != "无":
            print(f"  ⚠️ {w}")
    print(f"  ℹ️ 共 {stats['total_cases']} 条用例，3 轮回复合计 {stats['total_reply_chars']} 字符（全量渲染，未截断/未提炼）")
    if errors:
        if args.allow_empty_replies:
            print("[warning] 原文回复自检未通过（--allow-empty-replies 逃生阀已开启，继续生成）：")
        else:
            print("  ❌ 未通过：")
            for e in errors:
                print(f"    - {e}")
            print("[error] AI 回复必须为会话原文逐字（v3.10.1/v3.16.9 强制）：禁止空回复、禁止模板、禁止要点摘要、禁止截断；漏数据须先补齐、非原文须改回真实会话原文后再生成；仅历史数据补档可用 --allow-empty-replies 逃生。")
            raise SystemExit(2)

    if args.check_only:
        print("[ok] check-only 通过（未生成 HTML）")
        return

    # 渲染
    name = args.name
    out = Path(args.output) if args.output else Path(f"{name}-test-cases.html")
    dist_html = distribution_table(cases)
    rate_html = passrate_table(cases)
    tag_src = cases + (b_cases or [])
    tagcases_html = tag_cases_table(tag_src)
    call_html = call_cases_table(cases)
    b_html = b_volume_section(b_cases)
    a_rows = cases_rows([c for c in cases if str(c.get("类型") or "") != CALL_TYPE])

    page = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{esc(name)} 测试用例（最终版 A/B 卷 · AI 原文回复）</title>
<style>{CSS}</style>
</head>
<body>
<div class="wrap">
  <h1>🧪 {esc(name)} 测试用例（最终版）</h1>
  <div class="sub">生成：{datetime.now().strftime('%Y-%m-%d %H:%M')} ｜ 由 root-skills-eval build-testcases-html.py 生成 ｜ 「AI 回复」列为 AI 实际返回原文（逐字，未提炼）｜ 仅本区输出最终版 A 卷 / B 卷 / 调用 / 标签用例</div>

  <h2>用例分配比例</h2>
  {dist_html}

  <h2>通过率（按类型 + 安全/组合标签）</h2>
  {rate_html}

  <h2>全部用例与每轮 AI 原文回复</h2>
  <p class="note">A 卷最终版。每轮单元格 = 结论（触发/不触发/追问/加载/未加载）+ AI 实际返回的<strong>原文</strong>（完整保留，未截断、未提炼、未改写）。</p>
  <table><tr><th># </th><th>类型 </th><th>标题 </th><th>提示词 </th><th>预期结果 </th>
         <th>优先级 </th><th>1轮 </th><th>2轮 </th><th>3轮 </th></tr>{a_rows}</table>

  {call_html}

  {tagcases_html}

  {b_html}

  <div class="selfcheck">输出前自检：{len(errors)} 项错误 / {len(warnings) - (1 if warnings == ['无'] else 0)} 项提示 ｜ 3 轮回复合计 {stats['total_reply_chars']} 字符（原文全量渲染）</div>
  <div class="footer">由 root-skills-eval 生成 ｜ AI 回复列为原文逐字 ｜ 本文件为中间产物，内容并入唯一最终报告「🧪 测试用例」部分（v3.17.1：最终版 A/B 卷 + 调用 + 标签；📊/🧭 不贴逐条）</div>
</div>
</body>
</html>"""
    out.write_text(page, encoding="utf-8")
    print(f"[ok] 测试用例 HTML 已生成（最终版 A/B 卷 + 调用 + 标签，AI 原文未截断/未提炼）: {out}")


if __name__ == "__main__":
    main()
