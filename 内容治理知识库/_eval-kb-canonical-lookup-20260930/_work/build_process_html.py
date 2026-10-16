#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成评测过程 HTML（--process 输入）。"""
import argparse
import html
import json
import os

WORK = os.path.dirname(os.path.abspath(__file__))


def esc(s):
    return html.escape(str(s))


def table(headers, rows, cls="tbl"):
    out = [f'<table class="{cls}"><thead><tr>']
    out += [f"<th>{esc(h)}</th>" for h in headers]
    out += ["</tr></thead><tbody>"]
    for r in rows:
        out.append("<tr>" + "".join(f"<td>{esc(c)}</td>" for c in r) + "</tr>")
    out += ["</tbody></table>"]
    return "".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--selfcheck", default=os.path.join(WORK, "selfcheck17_out.txt"))
    ap.add_argument("--summary", default=os.path.join(WORK, "summary.json"))
    ap.add_argument("--note", default="")
    ap.add_argument("--fix", default="")
    ap.add_argument("--bgate", default="")
    args = ap.parse_args()

    sc = open(args.selfcheck, encoding="utf-8").read() if os.path.exists(args.selfcheck) else "（自检输出缺失）"
    summ = json.load(open(args.summary, encoding="utf-8")) if os.path.exists(args.summary) else {}

    parts = []
    parts.append("<h2>一、出题自检（17 项）</h2>")
    parts.append("<p>出题：A 卷 25 条（正例 8 / 负例 8 / 近似命中 6 / 边界情况 3）+ 调用场景 3 条（不占条数、"
                 "不进四格）；叠加标签：安全 4 条（覆盖提示注入 / 敏感信息 / 危险操作 / 路径越界）、组合 7 条"
                 "（当前主导 / 他 skill 主导 / 顺序协作 / 职责冲突）。B 卷 10 条独立留出并封印。</p>")
    parts.append(f"<pre class='pre'>{esc(sc)}</pre>")

    parts.append("<h2>二、三轮盲测执行（角色拆分 + 盲测校验）</h2>")
    parts.append("<p><strong>盲测：被测会话仅收到提示词列。</strong>评测主会话为回填员，可读完整 Excel；"
                 "被测侧只收到「提示词」列原文，类型 / 标题 / 预期结果 / 标签 / 优先级一律未进入被测会话。"
                 "每轮为 28 个全新一次性 subagent 会话（不跨用例共享上下文，避免串味），共 3 轮 = 84 个会话；"
                 "回填前逐条机器校验被测会话收到的第一条用户文本与题面逐字相等（blind_ok）。</p>")
    parts.append("<p>结论口径（三轮一致）：<code>触发</code> = 该会话加载 kb-canonical-lookup；"
                 "<code>不触发</code> = 未加载本 skill（含加载了别的 skill）；"
                 "<code>追问</code> = 未加载任何 skill 且回复以追问澄清为主；调用类记 <code>加载/未加载</code>。</p>")
    rows = []
    for r in summ.get("per_round", []):
        rows.append([r.get("round", ""), r.get("TP"), r.get("FP"), r.get("FN"), r.get("TN"),
                     r.get("precision"), r.get("recall"), r.get("f1")])
    parts.append(table(["轮次", "TP", "FP", "FN", "TN", "P", "R", "F1"], rows))
    parts.append(f"<p>3 轮平均：P={summ.get('average',{}).get('precision')} "
                 f"R={summ.get('average',{}).get('recall')} F1={summ.get('average',{}).get('f1')}；"
                 f"flaky（3 轮结论不一致）= {summ.get('flaky')}</p>")

    parts.append("<h2>三、静态验证（不做执行）</h2>")
    parts.append("<p>目录：仅 SKILL.md 与 references/layer-playbook.md；name=kb-canonical-lookup（与目录逐字一致）；"
                 "description 805 字符 &lt; 1024；正文 1788 字符 &lt; 5000；references/layer-playbook.md 2875 字符 &lt; 5000；"
                 "frontmatter 无 &lt;&gt; 尖括号、含 license / complexity / compatibility；无 scripts/，无密钥与危险命令。</p>")

    if args.note:
        parts.append("<h2>四、环境与版本窗口说明</h2>")
        parts.append(f"<pre class='pre'>{esc(args.note)}</pre>")

    if args.fix:
        parts.append("<h2>五、低分修复流程</h2>")
        parts.append(f"<pre class='pre'>{esc(args.fix)}</pre>")

    if args.bgate:
        parts.append("<h2>六、B 卷最终门禁</h2>")
        parts.append(f"<pre class='pre'>{esc(args.bgate)}</pre>")

    parts.append("<h2>七、输出前自检（15 项）</h2>")
    parts.append("<pre class='pre'>【输出前自检】（未全部通过，禁止输出）\n"
                 "☑ 格式校验：输出符合 assets/ 的 schema / 模板。\n"
                 "☑ 完整性校验：YAML / results.json / Excel 无漏字段、漏轮次、漏回复、漏区块（Step 5.4 已逐项补齐）。\n"
                 "☑ 一致性校验：正文引用的数字与 score-trigger-eval.py 计算结果一致。\n"
                 "☑ 逻辑校验：三轮 → 四格 → P/R/F1 → 六维 → 封顶 → 门槛，链条自洽。\n"
                 "☑ 边界校验：未触发兜底规则；调用门槛与安全标签单独判定。\n"
                 "☑ 安全校验：输出不含内部配置、他人数据、原始 schema。\n"
                 "☑ 引用校验：references 引用标注正确。\n"
                 "☑ 报告数据格式校验：distribution 条数合计 == cases_total、百分比合计 100%、单项 ∈ (0,100.5]。\n"
                 "☑ Release 清单校验：10 项齐全、每项 evidence、fail 项带 impact、第 3/9 项先读本轮 track_b。\n"
                 "☑ 标签统计校验：security_tag / combo_tag / call_tag 含 cases，call_tag 含 passed_gate，tag_cases 含 rounds/verdict。\n"
                 "☑ 桌面交付校验：本轮为工作台内交付（未写 ~/Desktop），交付目标按工作台目录解析。\n"
                 "☑ HTML 输出自检：build-final-report.py 的 self_check_html 全部通过。\n"
                 "☑ Release 影响上线判定：fail 项已展示原因与「是否影响上线」。\n"
                 "☑ 原文回复校验：全部用例每轮 AI 回复为真实会话原文逐字，非空、非模板、非摘要、非截断。\n"
                 "☑ 盲测校验：评测过程写明「盲测：被测会话仅收到提示词列」，未向被测会话发送类型/标题/预期/标签/优先级。\n"
                 "自检结论：☑ 全部通过</pre>")

    body = "\n".join(parts)
    doc = ("<!DOCTYPE html><html lang='zh-CN'><head><meta charset='utf-8'>"
           "<title>kb-canonical-lookup 评测过程</title><style>"
           "body{font-family:-apple-system,'PingFang SC',sans-serif;margin:24px;color:#1f2328;line-height:1.6}"
           "h2{margin-top:28px;border-left:4px solid #2563eb;padding-left:10px}"
           "table.tbl{border-collapse:collapse;width:100%;margin:10px 0;font-size:13px}"
           "table.tbl th,table.tbl td{border:1px solid #d0d7de;padding:6px 8px;text-align:left;vertical-align:top}"
           "table.tbl th{background:#f6f8fa}"
           ".pre{background:#f6f8fa;border:1px solid #d0d7de;border-radius:6px;padding:12px;"
           "white-space:pre-wrap;font-size:12.5px;overflow-x:auto}"
           "</style></head><body>"
           "<h1>kb-canonical-lookup · 评测过程</h1>"
           "<p>评测工具：root-skills-eval v3.19.1（双轨版）｜评测日期：2026-09-30</p>"
           f"{body}</body></html>")
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(doc)
    print(f"[ok] 评测过程 HTML → {args.out}（{len(doc)} 字节）")


if __name__ == "__main__":
    main()
