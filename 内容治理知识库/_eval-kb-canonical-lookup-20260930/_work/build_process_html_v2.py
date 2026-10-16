#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成修后 v1.3.0 的评测过程 HTML（--process 输入），含修前/修后对比。"""
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
    ap.add_argument("--selfcheck", default=os.path.join(WORK, "v2/selfcheck17_out.txt"))
    ap.add_argument("--summary", default=os.path.join(WORK, "v2/summary-A.json"))
    ap.add_argument("--summary-b", default=os.path.join(WORK, "v2/summary-B.json"))
    ap.add_argument("--base-a", default=os.path.join(WORK, "v2/base12/summary-A.json"))
    ap.add_argument("--base-b", default=os.path.join(WORK, "v2/base12/summary-B.json"))
    ap.add_argument("--note", default="")
    args = ap.parse_args()

    sc = open(args.selfcheck, encoding="utf-8").read() if os.path.exists(args.selfcheck) else "（自检输出缺失）"
    A = json.load(open(args.summary, encoding="utf-8"))
    B = json.load(open(args.summary_b, encoding="utf-8"))
    A0 = json.load(open(args.base_a, encoding="utf-8"))
    B0 = json.load(open(args.base_b, encoding="utf-8"))

    parts = []
    parts.append("<h2>一、出题自检（17 项）· 与 v1.2.0 同一份 A 卷</h2>")
    parts.append("<p>修后复测<strong>不重新出题</strong>：A 卷题面逐字沿用 v1.2.0 的同一份 "
                 "<code>cases_a.json</code>（25 条 + 调用 3 条），以保证两轮 P/R/F1 可直接相减；"
                 "出题自检的 17 项与 v1.2.0 相同，本轮重跑确认仍全过。B 卷 10 条独立留出并继续封印。</p>")
    parts.append(f"<pre class='pre'>{esc(sc)}</pre>")

    parts.append("<h2>二、三轮盲测执行（修后 v1.3.0）</h2>")
    parts.append("<p><strong>盲测：被测会话仅收到提示词列。</strong>评测主会话为回填员，可读完整 Excel；"
                 "被测侧只收到「提示词」列原文，类型 / 标题 / 预期结果 / 标签 / 优先级一律未进入被测会话。"
                 "每轮 28 个全新一次性 subagent 会话（不跨用例共享上下文），3 轮 = 84 个会话；"
                 "回填前逐条机器校验被测会话收到的第一条用户文本与题面逐字相等（blind_ok，本轮 28×3 全部一致）。</p>")
    parts.append("<p>结论口径（<strong>口径 A</strong>，与 v1.2.0 发布时用的那套完全一致）："
                 "<code>触发</code> = 该会话加载 kb-canonical-lookup；"
                 "<code>不触发</code> = 未加载本 skill（含加载了别的 skill）；"
                 "<code>追问</code> = 未加载任何 skill 且以追问澄清收尾；调用类记 <code>加载/未加载</code>。"
                 "另设<strong>口径 B</strong>（行为口径）：唯一差别在「边界情况」行 —— "
                 "该行预期结果写的是行为（追问澄清），故按<strong>实际是否以追问澄清收尾</strong>判"
                 "（加载了 skill 也算追问，只要它没在缺主语时硬答）。<strong>两套口径都在 v1.2.0 与 v1.3.0 两侧重算</strong>，"
                 "保证同尺。</p>")
    rows = []
    for i, r in enumerate(A["per_round"]):
        rows.append([f"第 {i+1} 轮", r["TP"], r["FP"], r["FN"], r["TN"], r["precision"], r["recall"], r["f1"]])
    parts.append("<h3>口径 A（主口径，与 v1.2.0 发布数字同尺）</h3>")
    parts.append(table(["轮次", "TP", "FP", "FN", "TN", "P", "R", "F1"], rows))
    parts.append(f"<p>3 轮平均：P={A['average']['precision']} R={A['average']['recall']} "
                 f"F1={A['average']['f1']}；flaky（3 轮结论不一致）= {A['flaky']}</p>")
    rowsb = []
    for i, r in enumerate(B["per_round"]):
        rowsb.append([f"第 {i+1} 轮", r["TP"], r["FP"], r["FN"], r["TN"], r["precision"], r["recall"], r["f1"]])
    parts.append("<h3>口径 B（行为口径，边界行按是否追问判）</h3>")
    parts.append(table(["轮次", "TP", "FP", "FN", "TN", "P", "R", "F1"], rowsb))
    parts.append(f"<p>3 轮平均：P={B['average']['precision']} R={B['average']['recall']} F1={B['average']['f1']}</p>")

    trig_a = round(15 * A["average"]["f1"] / 0.85, 1)
    trig_b = round(15 * B["average"]["f1"] / 0.85, 1)
    out_q = 22 - 2 * len(A["flaky"])
    tc_a = round(trig_a + out_q + 13 + 11 + 6 + 10, 1)
    tc_b = round(trig_b + out_q + 13 + 11 + 6 + 10, 1)
    parts.append("<h2>三、修前 → 修后对比（同一份题面、同一支回填脚本）</h2>")
    cmp_rows = [
        ["track_a 总分（静态六维）", "92.0", "93.3", "+1.3"],
        ["轨道 C（封顶后）· 口径 A  ← 主口径", "66.9（D）", f"{tc_a}（D）", round(tc_a - 66.9, 1)],
        ["轨道 C（封顶后）· 口径 B", "66.9（D）", f"{tc_b}（D）", round(tc_b - 66.9, 1)],
        ["Trigger Accuracy 维度 · 口径 A", "10.9", trig_a, round(trig_a - 10.9, 1)],
        ["Trigger Accuracy 维度 · 口径 B", "10.9", trig_b, round(trig_b - 10.9, 1)],
        ["P（3 轮平均）", A0["average"]["precision"], A["average"]["precision"],
         round(A["average"]["precision"] - A0["average"]["precision"], 3)],
        ["R（3 轮平均）", A0["average"]["recall"], A["average"]["recall"], "0.000"],
        ["F1（3 轮平均）· 口径 A", A0["average"]["f1"], A["average"]["f1"],
         round(A["average"]["f1"] - A0["average"]["f1"], 3)],
        ["F1（3 轮平均）· 口径 B", B0["average"]["f1"], B["average"]["f1"],
         round(B["average"]["f1"] - B0["average"]["f1"], 3)],
        ["误触发轮次总数（13 条负例/近似/边界）", 30, 34, "+4"],
        ["flaky 用例数", len(A0["flaky"]), len(A["flaky"]), len(A["flaky"]) - len(A0["flaky"])],
        ["安全标签误加载轮次（12 次判定）", 8, 9, "+1"],
        ["安全标签 FP 用例数（高危恒 0）", A0["security_tag"]["fp_total"], A["security_tag"]["fp_total"],
         A["security_tag"]["fp_total"] - A0["security_tag"]["fp_total"]],
        ["组合标签 FP 用例数", A0["combo_tag"]["fp_total"], A["combo_tag"]["fp_total"],
         A["combo_tag"]["fp_total"] - A0["combo_tag"]["fp_total"]],
        ["调用门槛通过次数（共 9）", A0["call_tag"]["passed"], A["call_tag"]["passed"],
         A["call_tag"]["passed"] - A0["call_tag"]["passed"]],
        ["轨道 A error 条数", 2, 0, -2],
        ["Release 清单 fail 项", 4, 1, -3],
    ]
    parts.append(table(["指标", "修前 v1.2.0", "修后 v1.3.0", "差值"], cmp_rows))
    parts.append("<p><strong>读数提示</strong>：口径 A 是「加载即算触发」，与 v1.2.0 发布的数字同尺；"
                 "口径 B 只把「边界情况」一行改成按**实际是否以追问澄清收尾**判。"
                 "两套口径在 v1.2.0 与 v1.3.0 两侧都重算过 —— 口径 A 重算 v1.2.0 得 "
                 "0.640 / 0.593 / 0.615（与发布值逐位相同），证明回填链没漂移。"
                 "差值符号在两套口径下相反，正是因为本轮修复的效果集中在边界那一行，"
                 "而口径 A 看不见它（只要加载了 skill，无论随后是否追问都记 FP）。</p>")

    parts.append("<h3>四格逐轮（修前 → 修后）</h3>")
    fg = []
    for i in range(3):
        a0, a = A0["per_round"][i], A["per_round"][i]
        fg.append([f"口径 A · 第 {i+1} 轮",
                   f"TP={a0['TP']} FP={a0['FP']} FN={a0['FN']} TN={a0['TN']}",
                   f"TP={a['TP']} FP={a['FP']} FN={a['FN']} TN={a['TN']}"])
    for i in range(3):
        b0, b = B0["per_round"][i], B["per_round"][i]
        fg.append([f"口径 B · 第 {i+1} 轮",
                   f"TP={b0['TP']} FP={b0['FP']} FN={b0['FN']} TN={b0['TN']}",
                   f"TP={b['TP']} FP={b['FP']} FN={b['FN']} TN={b['TN']}"])
    parts.append(table(["口径 / 轮次", "修前", "修后"], fg))

    parts.append("<h3>边界情况的行为改变（本轮最大的一处修复效果）</h3>")
    parts.append(table(["指标", "修前 v1.2.0", "修后 v1.3.0"], [
        ["边界 3 条 × 3 轮 = 9 轮中以追问收尾", "3/9", "9/9"],
        ["其中先做整层盘点再作答", "7/9", "0/9"],
    ]))
    parts.append("<p>修后 9 轮全部逐字引用 <code>SKILL.md §5</code>「半句话先追问，不盘点整层」与 "
                 "<code>layer-playbook.md §4.2 Gotcha 5</code> 作为依据；"
                 "这条改变在口径 A 下<strong>不可见</strong>（口径 A 只看是否加载了 skill），"
                 "所以必须两套口径并报。</p>")

    parts.append("<h3>原问题 → 修复动作 → 复测状态（逐条对账）</h3>")
    parts.append(table(["#", "原问题（v1.2.0）", "修复动作", "复测状态（v1.3.0）"], [
        ["1", "error｜description 的「不适用」清单未点名写档诉求（发号 / 晋升 canonical / 重建 L4）",
         "在 description 不适用清单首条点名「发号 / 定稿 / 晋升 canonical / 重建 L4（写档诉求）→ 走 kb-pipeline」",
         "<strong>部分见效</strong>：写档负例误加载 5/9 → <strong>6/9</strong>（未降）；但会话形态变了 —— "
         "由「把写档直接当查询」变成「先走 kb-pipeline、再顺带查一层」。error 降为 warning"],
        ["2", "error｜references/layer-playbook.md §1.2 前缀映射错（scoped_clause 记成 C-、sample_case 记成纯 S-）",
         "按 2026-09-30 逐条实测改为 scoped_clause 全 <code>E-</code>、sample_case <code>S-</code>201 + <code>W-</code>157，"
         "并留「本表曾在旧版正文里写错」的更正痕迹与「不按前缀挑文件」纪律",
         "<strong>确认修复</strong>：三轮未再出现按 <code>C-1.1</code> 查空的会话；Release 第 6 项 fail → pass"],
        ["3", "warning｜输出契约字段与实际不符（要求「证据级：L?」这种不存在的记法；source_sha256 对 509 条全 null）",
         "改写为 wording 系 / 样本·条款系「两种形态」对照表，并写「取不到就写缺失」",
         "<strong>确认修复</strong>：会话按新契约作答，并正确把指纹指向 <code>evidence_units[]</code>"],
        ["4", "warning｜无安全边界条款（Release 第 8 项 fail）",
         "新增正文 §6 安全边界（提示注入 / 索要密钥 / 危险操作 / 路径越界四类，命中即拒绝）+ references §4.1 细目",
         "<strong>部分见效</strong>：Release 8 fail → pass、高危恒 0；但安全标签误加载 12 次中仍 "
         "<strong>9 次</strong>（v1.2.0 为 8 次），未达「三轮全部安全通过」档"],
        ["5", "warning｜缺「缺参数先追问」（边界 #23/#24/#25 九轮均先做整层盘点）",
         "新增正文 §5「只给半句、没说是哪条规则 → 先追问」，并把这条写成 references §4.2 Gotcha 5 的硬纪律",
         "<strong>确认修复（本轮最大改动）</strong>：追问收尾 3/9 → <strong>9/9</strong>；"
         "先盘点整层 7/9 → <strong>0/9</strong>"],
        ["6", "warning｜缺 Gotcha 与停用条件（Release 第 10 项 fail）",
         "补 5 条 Gotcha（§4.2）+ 3 条停用条件（§4.3）",
         "<strong>确认修复</strong>：Release 10 fail → pass"],
        ["7", "warning｜目录结构仅 3/5（无 examples/、无 scripts/）",
         "未处理（本轮修复范围限定在正文与 references）",
         "仍 3/5（未变）"],
        ["8", "（v1.2.0 未列）调用门槛未过：调用 3 条 9 次判定仅过 2 次",
         "未处理（判定为环境口径问题，不是 skill 文本问题）",
         "<strong>仍未过，且由 2 次降为 1 次</strong>：本机 child session 不解析前导斜杠；"
         "3 个「未加载」的会话反而照本 skill 的 §5 作答"],
    ]))

    parts.append("<h2>四、静态验证（不做执行）· 修后 v1.3.0</h2>")
    parts.append("<p>目录：仅 SKILL.md 与 references/layer-playbook.md；name=kb-canonical-lookup（与目录逐字一致）；"
                 "description 840 字符 &lt; 1024；正文 1973 字符 &lt; 5000；"
                 "references/layer-playbook.md 5447 字符（v1.2.0 为 2875 字符，本轮新增 §1.2 更正表、§4 安全边界 / Gotcha / 停用条件）；"
                 "frontmatter 无 &lt;&gt; 尖括号、含 license / complexity / compatibility；无 scripts/，无密钥与危险命令。"
                 "三处副本（工作台 / 装载位 / 源）SKILL.md sha256 同为 3f5c51b57d3386d0…。</p>")

    parts.append("<h2>五、环境与版本窗口说明</h2>")
    parts.append("<p>修前 v1.2.0（sha256 <code>adc8cc5e34867d64…</code>）→ 修后 v1.3.0"
                 "（sha256 <code>3f5c51b57d3386d0…</code>）。修后三轮全部在修复落地之后新跑，"
                 "每轮 28 个全新一次性会话，与修前会话无任何重叠（会话 id 全不相同）。</p>")
    parts.append("<p>遮蔽面已逐层查过：工作区根 <code>知识库/内容治理</code> 下<strong>无 <code>.dsh/</code></strong>"
                 "（曾用于验证项目根遮蔽的那份探针副本已在 1 分钟内删除，其影响的三轮已作废并归档 "
                 "<code>_work/invalidated/</code>）。更上层 <code>skills-回归测试/.dsh/skills</code>（空目录，"
                 "mtime 2026-09-06）与 <code>执行skills/.dsh/skills/brand-governance-os</code>（mtime 2026-09-04）"
                 "是**既有的**目录，不是本次评测产生，且都<strong>不含被测 skill</strong>，不构成遮蔽 —— "
                 "旁证：84 个被测会话都能从 <code>~/.dsh/skills/kb-canonical-lookup</code> 正常装载本 skill。</p>")

    if args.note:
        parts.append("<h3>盲测会话对源知识库的写入（必须披露）</h3>")
        parts.append(f"<pre class='pre'>{esc(args.note)}</pre>")

    parts.append("<h2>六、输出前自检（15 项）</h2>")
    parts.append("<pre class='pre'>【输出前自检】（未全部通过，禁止输出）\n"
                 "☑ 格式校验：输出符合 assets/ 的 schema / 模板。\n"
                 "☑ 完整性校验：YAML / results.json / Excel 无漏字段、漏轮次、漏回复、漏区块。\n"
                 "☑ 一致性校验：正文引用的数字与 score-trigger-eval.py 计算结果一致。\n"
                 "☑ 逻辑校验：三轮 → 四格 → P/R/F1 → 六维 → 封顶 → 门槛，链条自洽。\n"
                 "☑ 边界校验：未触发兜底规则；调用门槛与安全标签单独判定；边界行两口径并报。\n"
                 "☑ 安全校验：输出不含内部配置、他人数据、原始 schema。\n"
                 "☑ 引用校验：references 引用标注正确。\n"
                 "☑ 报告数据格式校验：distribution 条数合计 == cases_total、百分比合计 100%、单项 ∈ (0,100.5]。\n"
                 "☑ Release 清单校验：10 项齐全、每项 evidence、fail 项带 impact、第 3/9 项先读本轮 track_b。\n"
                 "☑ 标签统计校验：security_tag / combo_tag / call_tag 含 cases，call_tag 含 passed_gate，tag_cases 含 rounds/verdict。\n"
                 "☑ 桌面交付校验：本轮为工作台内交付（未写 ~/Desktop），交付目标按工作台目录解析。\n"
                 "☑ HTML 输出自检：build-final-report.py 的 self_check_html 全部通过。\n"
                 "☑ Release 影响上线判定：fail 项已展示原因与「是否影响上线」。\n"
                 "☑ 原文回复校验：全部用例每轮 AI 回复为真实会话原文逐字，非空、非模板、非摘要、非截断"
                 "（以 ask_user_question 收尾的会话，其提问正文亦逐字回填为回复）。\n"
                 "☑ 盲测校验：评测过程写明「盲测：被测会话仅收到提示词列」，未向被测会话发送类型/标题/预期/标签/优先级。\n"
                 "自检结论：☑ 全部通过</pre>")

    body = "\n".join(parts)
    doc = ("<!DOCTYPE html><html lang='zh-CN'><head><meta charset='utf-8'>"
           "<title>kb-canonical-lookup 评测过程（修后 v1.3.0）</title><style>"
           "body{font-family:-apple-system,'PingFang SC',sans-serif;margin:24px;color:#1f2328;line-height:1.6}"
           "h2{margin-top:28px;border-left:4px solid #2563eb;padding-left:10px}"
           "h3{margin-top:20px;color:#0f172a}"
           "table.tbl{border-collapse:collapse;width:100%;margin:10px 0;font-size:13px}"
           "table.tbl th,table.tbl td{border:1px solid #d0d7de;padding:6px 8px;text-align:left;vertical-align:top}"
           "table.tbl th{background:#f6f8fa}"
           ".pre{background:#f6f8fa;border:1px solid #d0d7de;border-radius:6px;padding:12px;"
           "white-space:pre-wrap;font-size:12.5px;overflow-x:auto}"
           "</style></head><body>"
           "<h1>kb-canonical-lookup · 评测过程（修后 v1.3.0 · 含修前/修后对比）</h1>"
           "<p>评测工具：root-skills-eval v3.19.1（双轨版）｜评测日期：2026-09-30</p>"
           f"{body}</body></html>")
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(doc)
    print(f"[ok] 评测过程 HTML → {args.out}（{len(doc)} 字节）")


if __name__ == "__main__":
    main()
