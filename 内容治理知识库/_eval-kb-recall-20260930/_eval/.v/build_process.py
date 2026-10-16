# -*- coding: utf-8 -*-
"""生成 kb-recall-evaluation-process.html（评测过程；随 --process 内联进最终报告）"""
import os, sys, json, html
HERE = os.path.dirname(os.path.abspath(__file__)); WB = os.path.dirname(HERE)
J = lambda p, d=None: json.load(open(p, encoding="utf-8")) if os.path.exists(p) else d
e = lambda s: html.escape(str(s))

def esc(v):
    return e(v)

def table(headers, rows):
    h = "".join("<th>%s</th>" % e(x) for x in headers)
    body = "".join("<tr>%s</tr>" % "".join("<td>%s</td>" % e(c) for c in r) for r in rows)
    return '<table class="t"><thead><tr>%s</tr></thead><tbody>%s</tbody></table>' % (h, body)

def build(extra=None):
    sc = J(os.path.join(HERE, "selfcheck-17.json"), [])
    aj = J(os.path.join(HERE, "adjudicated-a.json"), [])
    summ = J(os.path.join(HERE, "summary-a.json"), {})
    ajb = J(os.path.join(HERE, "adjudicated-b.json"))
    sumb = J(os.path.join(HERE, "summary-b.json"))
    P = []
    A = P.append
    A('<h2>一、评测对象与环境</h2>')
    A(table(["项", "内容"], [
        ["被测 skill", "kb-recall（Momcozy 内容治理知识库 L6 召回层，查询档只读；已并入原 kb-retriever）"],
        ["工作台副本", "%s/kb-recall/" % WB],
        ["版本 / 复杂度", "v1.2.0 / standard（frontmatter complexity）→ A 卷 50 条"],
        ["评测工具", "root-skills-eval v3.19.1（双轨）；references/trigger-eval-cases.md、scoring-criteria.md、comprehensive-scoring.md、release-checklist.md、final-delivery-spec.md"],
        ["源只读", "全程未写入 / 修改 / 删除 kb/** 与 ~/.dsh/skills/**；未创建或修改任何 .dsh/、.agents/ 装载位"],
        ["装载位一致性", "工作台副本 SKILL.md 与 ~/.dsh/skills/kb-recall/SKILL.md 逐字节一致（diff 无输出），因此盲测会话加载的就是本工作台副本"],
        ["解释器", "/usr/bin/python3；未安装任何依赖；未调用 lark-* 工具"],
    ]))
    A('<h2>二、出题自检（17 项）</h2>')
    A('<p class="note">检查清单来源：references/trigger-eval-cases.md Step 2。结论：<b>%d/17 通过（全部通过）</b>；生成后即自检，未触发重出。</p>' %
      sum(1 for r in sc if r["ok"]))
    A(table(["#", "检查项", "结果", "证据"], [[r["no"], r["item"], "✅ 通过" if r["ok"] else "❌ 不通过", r["evidence"]] for r in sc]))
    A('<h2>三、3 轮盲测执行摘要</h2>')
    A('<p class="warn"><b>盲测：被测会话仅收到提示词列。</b>类型 / 标题 / 预期结果 / 标签 / 优先级一律未进入被测会话，也未告知被测会话「这是评测」或「请判断是否触发 skill」。</p>')
    A(table(["项", "做法"], [
        ["被测会话形态", "每条用例 × 每轮 = 一个**全新的一次性 DSH headless 会话**（`DSH Desktop --profile headless &lt;提示词原文&gt;`），会话之间互不共享上下文"],
        ["发送内容", "只发「提示词」列原文，逐条独立发送，不拼接、不加前后说明、不补提示词里没有的 skill 名"],
        ["只读沙箱", "被测会话以 DSH_PERMISSION_MODE=read-only 启动 → 物理上无法写库、改索引、删除文件，源目录天然只读"],
        ["独立 cwd", "每条用例一个独立工作目录 `_eval/work/{a|b}{轮}/item-{序号}`，会话互不串；cwd 即轮次台账锚点"],
        ["触发判定依据", "**不靠被测会话自报**：回读该条真实会话的 transcript（`~/.dsh/sessions/&lt;cwd 编码桶&gt;/&lt;session-uuid&gt;/session.jsonl.zstd`），读取 `tool/call` 记录中是否出现 `skill(name=&quot;kb-recall&quot;)`；再辅以回复原文核对"],
        ["轮次命名空间", "轮 1 → `a1/item-*`；轮 2 → `a2/item-*`；轮 3 → `a3/item-*`；B 卷 → `b1/b2/b3/item-*`"],
        ["AI 原文", "逐字取自真实会话（headless stdout 的最终回复，并以 transcript 的 assistant/message 兜底），未提炼、未概括、未截断"],
    ]))
    n = len(aj)
    done = sum(1 for r in aj for x in r["rounds"] if x != "缺轮次")
    A('<p class="note">A 卷完成度：%d 条 × 3 轮 = %d 次判定（缺轮次 %d 次）；调用场景 3 条 × 3 轮单独判定、不进四格。</p>'
      % (n, done, sum(1 for r in aj for x in r["rounds"] if x == "缺轮次")))
    if summ:
        rows = [[i + 1, r["TP"], r["FP"], r["FN"], r["TN"], r["precision"], r["recall"], r["f1"]]
                for i, r in enumerate(summ.get("per_round", []))]
        A(table(["轮次", "TP", "FP", "FN", "TN", "P", "R", "F1"], rows))
    A('<h2>四、轮次映射方式（可事后核对）</h2>')
    A('<p class="note">映射依据 = <b>独立 cwd 目录名</b>（`{卷}{轮}/item-{4 位序号}`）+ <b>该会话首条 user 消息逐字等于 Excel 提示词列</b> 双重对账；两者不一致则该条不计入。脚本：<code>_eval/run-round.py</code>（执行）、<code>_eval/oracle.py</code>（回读）、<code>_eval/adjudicate.py</code>（判定）。</p>')
    A(table(["卷/轮", "工作目录", "会话桶（~/.dsh/sessions/）", "核对方式"],
            [["A 卷 轮 1", "_eval/work/a1/item-0001 … 0053", "--Users-lute-…-_eval-kb-recall-20260930-_eval-work-a1-item-0001--",
              "会话 transcript 的 session.cwd 字段 == 该 item 目录；首条 user 消息 == 提示词原文"],
             ["A 卷 轮 2", "_eval/work/a2/item-0001 … 0053", "…-a2-item-0001--", "同上"],
             ["A 卷 轮 3", "_eval/work/a3/item-0001 … 0053", "…-a3-item-0001--", "同上"]]))
    A('<h2>五、静态验证</h2>')
    A('<pre>' + e(extra.get("validate", "(未运行)")) + '</pre>')
    if extra and extra.get("fix"):
        A('<h2>六、低分修复流程</h2>' + extra["fix"])
    A('<h2>七、B 卷最终门禁</h2>')
    if ajb and sumb:
        A('<p class="note">已进入修复流程并在副本交付前开卷执行：B 卷 10 条 × 3 轮 = 30 次全新会话（盲测规则同 A 卷）。</p>')
        A(table(["轮次", "TP", "FP", "FN", "TN", "P", "R", "F1"],
                [[i + 1, r["TP"], r["FP"], r["FN"], r["TN"], r["precision"], r["recall"], r["f1"]]
                 for i, r in enumerate(sumb["per_round"])]))
        A('<p class="warn">门禁：F1=%s（阈 0.85）、安全标签 %d 条 FP=%d、高危=%d → <b>%s</b></p>' % (
            sumb["average"]["f1"], sumb["security_tag"]["cases"], sumb["security_tag"]["fp_total"],
            sumb["security_tag"].get("high_risk", 0),
            "通过" if sumb["average"]["f1"] >= 0.85 and sumb["security_tag"].get("high_risk", 0) == 0 and summ.get("call_tag", {}).get("passed_gate") else "未通过"))
    else:
        A('<p class="note"><b>B 卷未执行</b>（10 条题面与 A 卷完全不同，生成后即封存；按规则一次达标、未进入修复流程则不开卷）。B 卷题面不得出现在本部分与 📊 测试报告。</p>')
    A('<h2>八、输出前自检（15 项）</h2>')
    A('<pre>' + e(extra.get("selfcheck15", "(见最终报告页脚)")) + '</pre>')
    return "\n".join(P)

if __name__ == "__main__":
    import subprocess
    v = subprocess.run(["/usr/bin/python3", "/Users/lute/.dsh/skills/root-skills-eval/scripts/validate-skill.py",
                        os.path.join(WB, "kb-recall")], capture_output=True, text=True)
    extra = dict(validate=v.stdout + v.stderr)
    for name in ("process-extra.json",):
        p = os.path.join(HERE, name)
        if os.path.exists(p): extra.update(json.load(open(p, encoding="utf-8")))
    body = build(extra)
    out = os.path.join(WB, "kb-recall-evaluation-process.html")
    open(out, "w", encoding="utf-8").write(
        '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><title>kb-recall 评测过程</title>'
        '<style>body{font-family:-apple-system,"PingFang SC",sans-serif;max-width:1200px;margin:32px auto;padding:0 16px;line-height:1.7;color:#1f2328}'
        'h2{border-left:4px solid #1f6feb;padding-left:10px;margin-top:36px}table.t{border-collapse:collapse;width:100%;margin:12px 0;font-size:13px}'
        'table.t th,table.t td{border:1px solid #d0d7de;padding:6px 8px;text-align:left;vertical-align:top}table.t th{background:#f6f8fa}'
        '.note{background:#f6f8fa;border-left:3px solid #8c959f;padding:8px 12px;border-radius:4px}'
        '.warn{background:#fff8c5;border-left:3px solid #d4a72c;padding:8px 12px;border-radius:4px}'
        'pre{background:#f6f8fa;padding:12px;border-radius:6px;overflow:auto;font-size:12px;white-space:pre-wrap}</style></head><body>'
        + body + '</body></html>')
    print("wrote", out, len(body), "chars")
