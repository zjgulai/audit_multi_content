#!/usr/bin/env python3
"""
build-html-report.py - 由评测 YAML 报告 + 人类可读摘要生成专业 HTML 报告

输出单文件、自包含（内嵌 CSS）的 HTML，包含：
  1. 总结论（顶部醒目区块：一句话结论 + 三轨道摘要 + 可发布性判定）
  2. 人类可读摘要（完整嵌入 summary markdown，渲染为表格/徽章/进度条；
     含问题清单与优化路线，是问题/优化信息的唯一展示区块）
  3. 轨道 A 静态六维、轨道 B 触发评测（TP/FP/FN/TN、P/R/F1、3 轮一致性）、
     轨道 C 综合评分（六维 100 分制 + 等级）、安全标签小节
  4. 发布建议与结论

用法:
    python scripts/build-html-report.py {skill-name}-evaluation-report.yaml \\
        --summary {skill-name}-evaluation-summary.md \\
        --output {skill-name}-evaluation-report.html

依赖: 仅标准库（yaml 缺失时降级为文本渲染）。建议安装 PyYAML 获得完整表格。
"""

from __future__ import annotations

import argparse
import html
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False


CSS = """
:root {
  --bg: #f5f7fa; --card: #ffffff; --ink: #1f2937; --muted: #6b7280;
  --line: #e5e7eb; --accent: #2563eb; --ok: #16a34a; --warn: #d97706;
  --err: #dc2626; --info: #0284c7;
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--ink);
       font-family: -apple-system, "PingFang SC", "Microsoft YaHei", "Segoe UI", sans-serif;
       line-height: 1.6; }
.wrap { max-width: 1080px; margin: 0 auto; padding: 24px 20px 64px; }
h1 { font-size: 26px; margin: 0 0 4px; }
h2 { font-size: 20px; margin: 40px 0 14px; padding-bottom: 8px;
     border-bottom: 2px solid var(--line); }
h3 { font-size: 16px; margin: 24px 0 8px; }
.sub { color: var(--muted); font-size: 13px; margin-bottom: 18px; }
.card { background: var(--card); border: 1px solid var(--line); border-radius: 12px;
        padding: 18px 20px; margin-bottom: 16px; box-shadow: 0 1px 3px rgba(0,0,0,.04); }
.verdict { border-left: 6px solid var(--accent); background: linear-gradient(135deg,#eff6ff,#ffffff);
           padding: 20px 22px; border-radius: 12px; margin-bottom: 20px; }
.verdict h2 { border: none; margin: 0 0 8px; padding: 0; }
.badges { display: flex; flex-wrap: wrap; gap: 10px; margin: 12px 0; }
.badge { display: inline-flex; align-items: center; gap: 6px; padding: 6px 14px;
         border-radius: 999px; font-size: 13px; font-weight: 600; }
.badge-ok { background: #f0fdf4; color: var(--ok); border: 1px solid #bbf7d0; }
.badge-warn { background: #fffbeb; color: var(--warn); border: 1px solid #fde68a; }
.badge-err { background: #fef2f2; color: var(--err); border: 1px solid #fecaca; }
.badge-info { background: #f0f9ff; color: var(--info); border: 1px solid #bae6fd; }
.badge-accent { background: #eff6ff; color: var(--accent); border: 1px solid #bfdbfe; }
table { width: 100%; border-collapse: collapse; margin: 12px 0; font-size: 14px; }
th, td { border: 1px solid var(--line); padding: 8px 10px; text-align: left; vertical-align: top; }
th { background: #f8fafc; font-weight: 600; white-space: nowrap; }
tr:nth-child(even) td { background: #fafbfc; }
.score-num { font-size: 34px; font-weight: 800; color: var(--accent); }
.score-label { color: var(--muted); font-size: 13px; }
.grid3 { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 14px; }
.bar { height: 8px; border-radius: 999px; background: #e5e7eb; overflow: hidden; margin-top: 6px; }
.bar > span { display: block; height: 100%; border-radius: 999px; background: var(--accent); }
.issue { border-left: 4px solid; padding: 10px 14px; margin: 8px 0; background: var(--card);
         border-radius: 6px; border-top: 1px solid var(--line); border-right: 1px solid var(--line);
         border-bottom: 1px solid var(--line); }
.issue-error { border-left-color: var(--err); }
.issue-warning { border-left-color: var(--warn); }
.issue-info { border-left-color: var(--info); }
.tag { font-size: 12px; font-weight: 700; padding: 2px 8px; border-radius: 4px; margin-right: 8px; }
.tag-error { background: #fee2e2; color: var(--err); }
.tag-warning { background: #fef3c7; color: var(--warn); }
.tag-info { background: #e0f2fe; color: var(--info); }
.tag-p0 { background: #fee2e2; color: var(--err); }
.tag-p1 { background: #fef3c7; color: var(--warn); }
.tag-p2 { background: #e0f2fe; color: var(--info); }
.md-body h1, .md-body h2, .md-body h3 { margin-top: 24px; }
.md-body code { background: #f1f5f9; padding: 2px 6px; border-radius: 4px; font-size: 13px; }
.md-body blockquote { border-left: 4px solid var(--line); margin: 12px 0; padding: 4px 14px; color: var(--muted); }
.md-body hr { border: none; border-top: 1px solid var(--line); margin: 24px 0; }
.footer { color: var(--muted); font-size: 12px; text-align: center; margin-top: 40px; }
.sec-title { display: flex; align-items: center; gap: 10px; }
.sec-title .ico { font-size: 20px; }
pre { background: #0f172a; color: #e2e8f0; padding: 14px 16px; border-radius: 8px; overflow-x: auto; font-size: 13px; }
"""


def esc(text) -> str:
    return html.escape(str(text))


def _cell(v) -> str:
    """表格单元格防 None（v3.12.0）：None 显示「—」，绝不输出 None 字样。"""
    return "—" if v is None else str(v)


def _dim_score(v):
    """归一化维度条目：flat 数字（{trigger: 23.0}）或 {score/value: …} 字典。"""
    if isinstance(v, dict):
        for k in ("score", "value", "total"):
            if k in v:
                return v[k]
        return None
    return v


def _safe_link(match: re.Match) -> str:
    """仅允许 http(s)、mailto 与本地相对/绝对链接，拒绝 javascript/data scheme。"""
    label = match.group(1)
    href = html.unescape(match.group(2)).strip()
    parts = urlsplit(href)
    safe_scheme = parts.scheme.lower() in {"http", "https", "mailto"}
    safe_local = not parts.scheme and not href.startswith("//")
    if not href or any(ch in href for ch in "\r\n\t") or not (safe_scheme or safe_local):
        return f"{label} ({esc(href)})"
    return f'<a href="{html.escape(href, quote=True)}">{label}</a>'


def inline(txt: str) -> str:
    """行内 markdown → HTML：**bold**、`code`、[text](url)、*italic*（先转义再替换）。"""
    s = esc(txt)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", _safe_link, s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"<em>\1</em>", s)
    return s


def md_to_html(md: str) -> str:
    """极简 markdown → HTML（支持标题/表格/列表/引用/代码/行内格式）。"""
    lines = md.splitlines()
    out = []
    in_table, in_list, in_code = False, False, False
    for raw in lines:
        line = raw.rstrip()
        if line.startswith("```"):
            in_code = not in_code
            out.append("<pre>" if in_code else "</pre>")
            continue
        if in_code:
            out.append(esc(line))
            continue
        if line.startswith("|") and line.endswith("|"):
            cells = [c.strip() for c in line.strip("|").split("|")]
            if not in_table:
                in_table = True
                out.append("<table>")
            if all(re.fullmatch(r":?-{3,}:?", c or "-") for c in cells):
                continue
            out.append("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in cells) + "</tr>")
            continue
        if in_table:
            in_table = False
            out.append("</table>")
        is_list_item = bool(re.match(r"^\s*[-*]\s+", line))
        if in_list and not is_list_item:
            in_list = False
            out.append("</ul>")
        if line.startswith(("# ", "## ", "### ", "#### ")):
            lvl = len(line) - len(line.lstrip("#"))
            txt = inline(line.lstrip("# ").strip())
            out.append(f"<h{lvl}>{txt}</h{lvl}>")
            continue
        if is_list_item:
            if not in_list:
                in_list = True
                out.append("<ul>")
            item_text = re.sub(r"^\s*[-*]\s+", "", line)
            out.append(f"<li>{inline(item_text)}</li>")
            continue
        if line.startswith(">"):
            out.append(f"<blockquote>{inline(line.lstrip('>').strip())}</blockquote>")
            continue
        if not line.strip():
            out.append("")
            continue
        out.append(f"<p>{inline(line)}</p>")
    if in_table:
        out.append("</table>")
    if in_list:
        out.append("</ul>")
    return "\n".join(out)


def verdict_badges(report: dict) -> str:
    """总结论徽章行。"""
    badges = []
    track_a = report.get("track_a", {})
    track_b = report.get("track_b", {})
    track_c = report.get("track_c", {})
    if track_a.get("total") is not None:
        badges.append(f'<span class="badge badge-accent">轨道A 静态 {track_a["total"]}/100</span>')
    f1 = (track_b.get("average") or {}).get("f1")
    if f1 is not None:
        badges.append(f'<span class="badge badge-ok">轨道B F1={f1}</span>')
    if track_c.get("total") is not None:
        grade = track_c.get("grade", "")
        badges.append(f'<span class="badge badge-accent">轨道C {track_c["total"]}/100 {esc(grade)}</span>')
    status = report.get("status", "")
    if status:
        cls = "badge-err" if status in ("needs_optimization", "needs_refactor") else "badge-ok"
        badges.append(f'<span class="badge {cls}">状态 {esc(status)}</span>')
    market = report.get("track_c", {}).get("market_ready")
    if market is not None:
        badges.append(f'<span class="badge {"badge-ok" if market else "badge-err"}">{"可发布" if market else "暂不可发布"}</span>')
    return '<div class="badges">' + "".join(badges) + "</div>"


def track_a_table(report: dict) -> str:
    dims = report.get("track_a", {}).get("dimensions", {})
    rows = ""
    labels = {
        "schema_compliance": "Schema 合规性", "frontmatter_quality": "Frontmatter 质量",
        "body_quality": "Body 内容质量", "methodology_audit": "方法论审计",
        "quality_gate": "质量门槛", "directory_structure": "目录结构",
    }
    for key, v in dims.items():
        score = _dim_score(v) if isinstance(v, dict) else v
        weight = v.get("weight") if isinstance(v, dict) else None
        if score is None:
            score = 0
        if weight is None:
            rows += (f"<tr><td>{labels.get(key, key)}</td><td>{_cell(score)}</td>"
                     f"<td>—</td><td>—</td><td>—</td></tr>")
        else:
            rows += (f"<tr><td>{labels.get(key, key)}</td><td>{_cell(score)}</td>"
                     f"<td>{int(weight*100)}%</td><td>{score*weight:.1f}</td>"
                     f"<td><div class='bar'><span style='width:{score}%'></span></div></td></tr>")
    return f"<table><tr><th>维度</th><th>得分</th><th>权重</th><th>加权</th><th>得分条</th></tr>{rows}</table>"


def track_b_table(report: dict) -> str:
    rounds = report.get("track_b", {}).get("rounds", [])
    rows = ""
    for i, r in enumerate(rounds, 1):
        if not isinstance(r, dict):
            r = {}
        label = r.get("round") or i
        rows += (f"<tr><td>第 {_cell(label)} 轮</td><td>{_cell(r.get('TP'))}</td><td>{_cell(r.get('FP'))}</td>"
                 f"<td>{_cell(r.get('FN'))}</td><td>{_cell(r.get('TN'))}</td><td>{_cell(r.get('precision'))}</td>"
                 f"<td>{_cell(r.get('recall'))}</td><td>{_cell(r.get('f1'))}</td></tr>")
    avg = report.get("track_b", {}).get("average", {})
    if not isinstance(avg, dict):
        avg = {}
    rows += (f"<tr><td><strong>平均</strong></td><td colspan='4'></td>"
             f"<td><strong>{_cell(avg.get('precision'))}</strong></td><td><strong>{_cell(avg.get('recall'))}</strong></td>"
             f"<td><strong>{_cell(avg.get('f1'))}</strong></td></tr>")
    return f"<table><tr><th>轮次</th><th>TP</th><th>FP</th><th>FN</th><th>TN</th><th>P</th><th>R</th><th>F1</th></tr>{rows}</table>"


def distribution_html(dist) -> str:
    """分布字段 → 徽章行（兼容 dict 与字符串）。"""
    if isinstance(dist, dict):
        return "".join(f'<span class="badge badge-accent">{esc(k)} {v}</span>' for k, v in dist.items())
    return esc(dist) if dist else ""


def track_c_table(report: dict) -> str:
    dims = report.get("track_c", {}).get("dimensions", {})
    labels = {
        "trigger_accuracy": "Trigger Accuracy", "output_quality": "Output Quality",
        "progressive_disclosure": "Progressive Disclosure", "safety_boundary": "Safety Boundary",
        "script_quality": "Script Quality", "specification_compliance": "Specification Compliance",
    }
    rows = ""
    for key, v in dims.items():
        score = _dim_score(v) if isinstance(v, dict) else v
        mx = v.get("max") if isinstance(v, dict) else None
        basis = v.get("basis", "") if isinstance(v, dict) else ""
        rows += (f"<tr><td>{labels.get(key, key)}</td><td>{_cell(score)}</td>"
                 f"<td>{_cell(mx)}</td><td>{esc(basis)}</td></tr>")
    return f"<table><tr><th>维度</th><th>得分</th><th>满分</th><th>评分依据</th></tr>{rows}</table>"


def issues_html(report: dict) -> str:
    issues = report.get("issues", [])
    if not issues:
        return '<p>✅ 无问题。</p>'
    out = []
    for it in issues:
        sev = it.get("severity", "info")
        cls = {"error": "issue-error", "warning": "issue-warning", "info": "issue-info"}.get(sev, "issue-info")
        tag = {"error": "tag-error", "warning": "tag-warning", "info": "tag-info"}.get(sev, "tag-info")
        out.append(
            f'<div class="issue {cls}"><span class="tag {tag}">{esc(sev.upper())}</span>'
            f'<strong>{esc(it.get("field", ""))}</strong>'
            f'<div>{esc(it.get("message", ""))}</div>'
            f'<div style="color:var(--muted);font-size:12px;margin-top:4px">fix_type: {esc(it.get("fix_type", ""))}</div></div>'
        )
    return "\n".join(out)


def security_section(report: dict) -> str:
    """安全标签小节：安全/组合标签用例统计（v3.9.0）+ 静态安全扫描结果。"""
    tb = report.get("track_b", {})
    sec_fp = [c for c in tb.get("systematic_fp", []) if "安全" in str(c.get("root_cause", ""))]
    issues = report.get("issues", [])
    sec_issues = [i for i in issues if any(k in str(i.get("message", "")).lower()
                                           for k in ("secret", "密钥", "注入", "越权", "危险", "泄露", "脱敏"))]
    total = tb.get("cases_main", 50)
    sec = tb.get("security_tag") or {}
    combo = tb.get("combo_tag") or {}
    sec_n = int(sec.get("cases") or 0) if isinstance(sec, dict) else 0
    combo_n = int(combo.get("cases") or 0) if isinstance(combo, dict) else 0
    parts = [f"<p>安全标签用例（叠加标签，不占主类型总数，共 {total} 条主用例）覆盖攻击面：提示注入、敏感信息泄露、危险操作、路径/权限越界。</p>"]
    if sec_n or combo_n:
        sec_fp_n = int(sec.get("fp_total") or 0) if isinstance(sec, dict) else 0
        combo_fp_n = int(combo.get("fp_total") or 0) if isinstance(combo, dict) else 0
        parts.append(
            "<h3>安全/组合标签用例统计（v3.9.0）</h3>"
            "<table><tr><th>标签</th><th>用例数</th><th>3 轮 FP</th><th>执行情况</th></tr>"
            f"<tr><td>安全</td><td>{sec_n}</td><td>{sec_fp_n}</td>"
            f"<td>{'✅ 全部通过' if sec_fp_n == 0 else '⚠️ 有误触发，需复查高危'}</td></tr>"
            f"<tr><td>组合</td><td>{combo_n}</td><td>{combo_fp_n}</td>"
            f"<td>{'✅ 路由归属全部符合预期' if combo_fp_n == 0 else '⚠️ 有路由误判'}</td></tr></table>"
        )
    if sec_issues:
        parts.append("<h3>安全相关静态问题</h3>" + issues_html({"issues": sec_issues}))
    else:
        parts.append("<p>✅ 静态安全扫描：scripts 无密钥 / 无 rm -rf / 无 curl|sh；references 无未脱敏数据。</p>")
    if sec_fp:
        parts.append(f"<h3>安全标签执行告警</h3><p>⚠️ {len(sec_fp)} 条安全标签用例出现误触发/风险，需复查。</p>")
    else:
        parts.append("<p>✅ 安全标签执行：未发现高危误触发（无密钥泄露、无危险命令执行、无越权读取）。</p>")
    return "\n".join(parts)


def quality_check_section(report: dict, xlsx_path: Path | None = None) -> str:
    """质量检查小节：DoD 5 项清单 + Sheet2 静态测试 17 项结果（可读 xlsx）。"""
    parts = []
    ta = report.get("track_a", {})
    qg = (ta.get("dimensions") or {}).get("quality_gate", {})
    qg_score = qg.get("score", "-") if isinstance(qg, dict) else "-"

    # DoD 5 项清单（质量门槛维度，基于轨道 A 维度分数 + issues 推导）
    dod = [
        ("单一职责明确", "一句话能说清做什么/不做什么"),
        ("差异化价值", "通过方法论审计或有竞争壁垒"),
        ("触发准确", "有明确触发词与 When to Use"),
        ("可测试", "有关键路径验证方式或测试用例"),
        ("可打包", "目录结构完整，无无效文件"),
    ]
    dims = ta.get("dimensions") or {}
    methodology = (dims.get("methodology_audit") or {}).get("score", 0) if isinstance(dims.get("methodology_audit"), dict) else 0
    frontmatter = (dims.get("frontmatter_quality") or {}).get("score", 0) if isinstance(dims.get("frontmatter_quality"), dict) else 0
    qg_dim = (dims.get("quality_gate") or {}).get("score", 0) if isinstance(dims.get("quality_gate"), dict) else 0
    issues = report.get("issues", [])
    issue_fields = " ".join(str(i.get("field", "")) + str(i.get("message", "")) for i in issues)
    avg_f1 = ((report.get("track_b") or {}).get("average") or {}).get("f1") or 0
    dod_status = {
        "单一职责明确": "pass" if "单一职责" not in issue_fields and "职责" not in issue_fields else "fail",
        "差异化价值": "pass" if methodology >= 70 else "fail",
        "触发准确": "pass" if frontmatter >= 80 and avg_f1 >= 0.90 else "fail",
        "可测试": "pass" if qg_dim >= 80 and not any(k in issue_fields for k in ("测试", "fixture", "可复现")) else "fail",
        "可打包": "pass" if not any(k in issue_fields for k in ("不可运行", "打包", "__pycache__", "空占位", "无效文件")) else "fail",
    }
    dod_rows = ""
    for label, desc in dod:
        st = dod_status[label]
        icon = "✅" if st == "pass" else "❌"
        dod_rows += f"<tr><td>{icon} {label}</td><td>{desc}</td><td>{'通过' if st == 'pass' else '未通过'}</td></tr>"

    parts.append(
        f'<div class="card"><h3>DoD 质量门槛清单（轨道A 质量门槛 {qg_score}/100）</h3>'
        f"<table><tr><th>检查项</th><th>标准</th><th>结论</th></tr>{dod_rows}</table></div>"
    )

    # Sheet2 静态测试结果（xlsx 存在时读取）
    if xlsx_path and xlsx_path.exists():
        try:
            import openpyxl
            wb = openpyxl.load_workbook(xlsx_path, data_only=True)
            ws = wb[wb.sheetnames[1]] if len(wb.sheetnames) > 1 else wb[wb.sheetnames[0]]
            headers = [str(c.value).strip() if c.value else "" for c in ws[1]]
            rows = ""
            for row in ws.iter_rows(min_row=2, values_only=True):
                if row[0] is None:
                    continue
                d = dict(zip(headers, row))
                result = str(d.get("结果", "")).strip()
                icon = "✅" if result == "通过" else ("❌" if result == "不通过" else "⚠️")
                rows += (f"<tr><td>{icon} {esc(d.get('检查项', ''))}</td><td>{esc(result)}</td>"
                         f"<td>{esc(d.get('证据', ''))}</td><td>{esc(d.get('说明', ''))}</td></tr>")
            parts.append(
                f'<div class="card"><h3>静态测试（{esc(xlsx_path.name)} Sheet2，共 {len(headers)} 列）</h3>'
                f"<table><tr><th>检查项</th><th>结果</th><th>证据</th><th>说明</th></tr>{rows}</table></div>"
            )
        except ImportError:
            parts.append("<p>⚠️ 读取 Excel 静态测试需要 openpyxl（python3 -m pip install openpyxl）。</p>")
        except Exception as e:  # noqa: BLE001
            parts.append(f"<p>⚠️ 读取静态测试失败：{esc(e)}</p>")
    else:
        parts.append("<p>ℹ️ 未提供用例 Excel，静态测试明细未渲染（可加 --checks {skill-name}.xlsx）。</p>")

    return "\n".join(parts)


def build(report_path: Path, summary_path: Path | None, out_path: Path, checks_path: Path | None = None) -> None:
    if not HAS_YAML:
        print("[warn] PyYAML 未安装（python3 -m pip install pyyaml），使用降级文本解析")
        report = _fallback_parse(report_path)
    else:
        report = yaml.safe_load(report_path.read_text(encoding="utf-8")) or {}

    info = report.get("eval_info", {})
    name = info.get("skill_name", report_path.stem)
    date = info.get("eval_date", datetime.now().strftime("%Y-%m-%d"))
    tool = f"{info.get('eval_tool', 'root-skills-eval')} v{info.get('eval_tool_version', '')}"

    summary_html = ""
    if summary_path and summary_path.exists():
        summary_html = (f'<div class="card"><h2>📄 人类可读摘要</h2>'
                        f'<div class="md-body">{md_to_html(summary_path.read_text(encoding="utf-8"))}</div></div>')

    rec = report.get("recommendation", {})
    if isinstance(rec, dict):
        rec_lines = "".join(f"<p><strong>{esc(k)}</strong>：{esc(v)}</p>" for k, v in rec.items())
        verdict_txt = rec.get("verdict", "")
    else:
        rec_lines = f"<p>{esc(rec)}</p>"
        verdict_txt = rec

    security = security_section(report)
    quality = quality_check_section(report, checks_path)

    page = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{esc(name)} 评测报告</title>
<style>{CSS}</style>
</head>
<body>
<div class="wrap">
  <h1>🛠️ {esc(name)} 评测报告</h1>
  <div class="sub">评测工具：{esc(tool)} ｜ 评测日期：{esc(date)} ｜ 生成：{datetime.now().strftime('%Y-%m-%d %H:%M')}</div>

  <div class="verdict">
    <h2>🎯 总结论</h2>
    {verdict_badges(report)}
    <div class="card" style="box-shadow:none">
      {rec_lines}
      {('<p><strong>一句话结论</strong>：' + esc(verdict_txt) + '</p>') if verdict_txt else ''}
    </div>
  </div>

  {summary_html}

  <div class="card">
    <div class="sec-title"><span class="ico">📊</span><h2 style="margin:0">轨道 A：静态六维评估</h2></div>
    <p>总分 <span class="score-num">{report.get('track_a', {}).get('total', '-')}</span>
       <span class="score-label">/ 100（{esc(report.get('track_a', {}).get('status', ''))}）</span></p>
    {track_a_table(report)}
  </div>

  <div class="card">
    <div class="sec-title"><span class="ico">🎯</span><h2 style="margin:0">轨道 B：触发评测（{esc(report.get('track_b', {}).get('cases_total', '-'))} 条 × 3 轮）</h2></div>
    <div class="badges">{distribution_html(report.get('track_b', {}).get('distribution', ''))}</div>
    {track_b_table(report)}
    <p>企业门槛：P ≥ 0.85、R ≥ 0.85、F1 ≥ 0.90 →
      <strong>{'✅ 达标' if report.get('track_b', {}).get('pass_enterprise_gate') else '❌ 未达标'}</strong></p>
  </div>

  <div class="card">
    <div class="sec-title"><span class="ico">🔒</span><h2 style="margin:0">安全标签维度</h2></div>
    {security}
  </div>

  <div class="card">
    <div class="sec-title"><span class="ico">🏅</span><h2 style="margin:0">轨道 C：综合评分</h2></div>
    <p>总分 <span class="score-num">{report.get('track_c', {}).get('total', '-')}</span>
       <span class="score-label">/ 100 ｜ {esc(report.get('track_c', {}).get('grade', ''))}</span></p>
    {track_c_table(report)}
  </div>

  <div class="card">
    <div class="sec-title"><span class="ico">🔍</span><h2 style="margin:0">质量检查</h2></div>
    {quality}
  </div>

  <div class="footer">由 root-skills-eval 生成 ｜ 结构化数据见 {esc(report_path.name)} ｜ 本页面为局域网可访问 HTML 交付物</div>
</div>
</body>
</html>"""
    out_path.write_text(page, encoding="utf-8")
    print(f"[ok] HTML 报告已生成: {out_path}")
    print(f"[ok] 局域网交付：在交付目录运行 python3 scripts/serve-lan.py --dir {out_path.parent} --port 8000")


def _first_colon(s: str):
    """第一个不在引号内的冒号位置（key: value 分割点）。"""
    quote = None
    for i, ch in enumerate(s):
        if quote:
            if ch == quote:
                quote = None
            continue
        if ch in "\"'":
            quote = ch
        elif ch == ":":
            return i
    return -1


def _parse_scalar(s: str):
    """YAML 标量 → Python 值（含引号/数字/布尔/内联 dict/list，剥离行内注释）。"""
    s = s.strip()
    # 行内注释（# 前有空格的才视为注释；引号内的 # 保留）
    if " #" in s:
        s = s.split(" #", 1)[0].rstrip()
    if s.startswith("{") and s.endswith("}"):
        inner = s[1:-1].strip()
        out = {}
        for part in _split_top(inner):
            i = _first_colon(part)
            if i > 0:
                k, v = part[:i], part[i + 1:]
                out[k.strip().strip("'\"").strip()] = _parse_scalar(v)
        return out
    if s.startswith("[") and s.endswith("]"):
        inner = s[1:-1].strip()
        return [_parse_scalar(x) for x in _split_top(inner) if x.strip()]
    if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
        return s[1:-1]
    if s in ("true", "True"):
        return True
    if s in ("false", "False"):
        return False
    if s in ("null", "None", "~"):
        return None
    try:
        return int(s)
    except ValueError:
        pass
    try:
        return float(s)
    except ValueError:
        pass
    return s


def _split_top(s: str) -> list[str]:
    """按顶层逗号分割（忽略引号与括号内），保留 key: value 配对。"""
    parts, buf, depth, quote = [], "", 0, None
    for ch in s:
        if quote:
            buf += ch
            if ch == quote:
                quote = None
            continue
        if ch in "\"'":
            quote, buf = ch, buf + ch
        elif ch in "{[(":
            depth, buf = depth + 1, buf + ch
        elif ch in "}])":
            depth, buf = depth - 1, buf + ch
        elif ch == "," and depth == 0:
            parts.append(buf)
            buf = ""
        else:
            buf += ch
    if buf.strip():
        parts.append(buf)
    return parts


def _fallback_parse(path: Path) -> dict:
    """PyYAML 缺失时降级：解析评测报告固定结构的 YAML 子集。"""
    text = path.read_text(encoding="utf-8")

    def section(name: str) -> str:
        m = re.search(rf"^{name}:\s*$", text, re.M)
        if not m:
            return ""
        rest = text[m.end():]
        nxt = re.search(r"^[A-Za-z_]+:\s*$", rest, re.M)
        end = nxt.start() if nxt else len(rest)
        return rest[:end]

    def kv_block(block: str) -> dict:
        d = {}
        for m in re.finditer(r"^\s*(\w+):\s*(.*)$", block, re.M):
            d[m.group(1)] = _parse_scalar(m.group(2))
        return d

    def list_of_dicts(block: str) -> list[dict]:
        out, cur = [], None
        for raw in block.splitlines():
            line = raw.rstrip()
            if not line.strip():
                continue
            if re.match(r"^\s*-\s+", line):
                if cur:
                    out.append(cur)
                cur = {}
                body = re.sub(r"^\s*-\s+", "", line)
                if ":" in body:
                    k, v = body.split(":", 1)
                    cur[k.strip()] = _parse_scalar(v)
            else:
                m = re.match(r"^\s{4,}(\w+):\s*(.*)$", line)
                if m and cur is not None:
                    cur[m.group(1)] = _parse_scalar(m.group(2))
        if cur:
            out.append(cur)
        return out

    def dim_block(block: str) -> dict:
        """解析 dimensions 下的逐行「key: {inline dict}」。"""
        d = {}
        for m in re.finditer(r"^\s*(\w+):\s*(\{.*\})\s*$", block, re.M):
            d[m.group(1)] = _parse_scalar(m.group(2))
        return d

    d: dict = {"eval_info": {}, "track_a": {}, "track_b": {}, "track_c": {}, "issues": [], "optimization_plan": []}

    m = re.search(r"skill_name:\s*(\S+)", text)
    if m:
        d["eval_info"]["skill_name"] = m.group(1)
    m = re.search(r"eval_date:\s*(\S+)", text)
    if m:
        d["eval_info"]["eval_date"] = m.group(1)
    m = re.search(r"eval_tool:\s*(\S+)", text)
    if m:
        d["eval_info"]["eval_tool"] = m.group(1)
    m = re.search(r"eval_tool_version:\s*(\S+)", text)
    if m:
        d["eval_info"]["eval_tool_version"] = m.group(1)

    ta = section("track_a")
    if ta:
        kv = kv_block(ta)
        d["track_a"]["total"] = kv.get("total")
        d["track_a"]["status"] = kv.get("status")
        d["track_a"]["dimensions"] = dim_block(ta)

    tb = section("track_b")
    if tb:
        kv = kv_block(tb)
        for k in ("cases_total", "cases_main", "cases_combo", "distribution", "pass_enterprise_gate"):
            if k in kv:
                d["track_b"][k] = kv[k]
        m_avg = re.search(r"average:\s*\{([^}]*)\}", tb)
        if m_avg:
            d["track_b"]["average"] = _parse_scalar("{" + m_avg.group(1) + "}")
        m_rounds = re.search(r"rounds:\s*\n((?:\s+-\s*\{[^\n]*\}\n?)+)", tb)
        if m_rounds:
            rounds = []
            for rm in re.finditer(r"-\s*\{([^}]*)\}", m_rounds.group(1)):
                rounds.append(_parse_scalar("{" + rm.group(1) + "}"))
            d["track_b"]["rounds"] = rounds

    tc = section("track_c")
    if tc:
        kv = kv_block(tc)
        d["track_c"]["total"] = kv.get("total")
        d["track_c"]["grade"] = kv.get("grade")
        d["track_c"]["market_ready"] = kv.get("market_ready")
        d["track_c"]["dimensions"] = dim_block(tc)

    d["issues"] = list_of_dicts(section("issues"))
    d["optimization_plan"] = list_of_dicts(section("optimization_plan"))

    m = re.search(r"^status:\s*(\S+)", text, re.M)
    if m:
        d["status"] = m.group(1)
    m = re.search(r"^recommendation:\s*$", text, re.M)
    if m:
        seg = text[m.end():]
        nxt = re.search(r"^[A-Za-z_]+:\s*$", seg, re.M)
        if nxt:
            seg = seg[:nxt.start()]
        rec = {}
        for rm in re.finditer(r"^\s+(\S.*?):\s*(.*)$", seg, re.M):
            rec[rm.group(1).strip()] = _parse_scalar(rm.group(2))
        d["recommendation"] = rec

    return d


def main() -> None:
    parser = argparse.ArgumentParser(description="由评测 YAML + 摘要生成专业 HTML 报告")
    parser.add_argument("report", type=Path, help="{skill-name}-evaluation-report.yaml 路径")
    parser.add_argument("--summary", type=Path, help="{skill-name}-evaluation-summary.md 路径（人类可读摘要）")
    parser.add_argument("--checks", type=Path, help="{skill-name}.xlsx 路径（读取 Sheet2 静态测试渲染质量检查）")
    parser.add_argument("--output", type=Path, help="输出 HTML 路径（默认与 report 同目录同名 .html）")
    args = parser.parse_args()
    if not args.report.exists():
        print(f"[error] 报告不存在: {args.report}")
        raise SystemExit(1)
    out = args.output or args.report.with_suffix(".html")
    build(args.report, args.summary, out, checks_path=args.checks)


if __name__ == "__main__":
    main()
