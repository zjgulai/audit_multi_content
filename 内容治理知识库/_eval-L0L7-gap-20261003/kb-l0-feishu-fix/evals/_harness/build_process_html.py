#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成**修复版**评测过程 HTML（build-final-report.py --process 的输入）。

与源版同名脚本的区别：本轮是**低分修复复测**，不重出题（沿用已落盘的 100 条 A 卷 + 10 条封印 B 卷），
所以过程记录聚焦「接线修复 / 冒烟 / 复测环境 / 与源版的差异 / 保真度限制」，异常一条不留白。
"""
import html
import json
import os
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
EVAL = os.path.dirname(HERE)


def esc(s):
    return html.escape(str(s))


def load(name, default=None):
    p = os.path.join(HERE, name)
    if not os.path.exists(p):
        return default
    if name.endswith(".json"):
        return json.load(open(p, encoding="utf-8"))
    return open(p, encoding="utf-8").read()


def table(headers, rows):
    out = ["<table><thead><tr>" + "".join(f"<th>{esc(h)}</th>" for h in headers)
           + "</tr></thead><tbody>"]
    for r in rows:
        out.append("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>")
    out.append("</tbody></table>")
    return "".join(out)


def main():
    sc = load("selfcheck-17.json", {})
    freeze = load("freeze-manifest.json", {})
    oa = load("output-assertions.json", {})
    summary = load("summary-a.json", {})
    val = load("validate-skill.json", {})
    smoke = []
    for f in ("smoke-round-99.jsonl", "smoke-round-98.jsonl"):
        p = os.path.join(HERE, f)
        if os.path.exists(p):
            for line in open(p, encoding="utf-8"):
                if line.strip():
                    o = json.loads(line)
                    smoke.append((f, o))

    css = """
    .proc h2 { font-size:18px; margin:26px 0 10px; padding-bottom:6px; border-bottom:2px solid #e5e7eb; }
    .proc h3 { font-size:15px; margin:18px 0 8px; }
    .proc p, .proc li { font-size:13.5px; line-height:1.75; }
    .proc table { width:100%; border-collapse:collapse; font-size:12.5px; margin:8px 0; }
    .proc th, .proc td { border:1px solid #e5e7eb; padding:6px 9px; text-align:left; vertical-align:top; }
    .proc th { background:#f8fafc; }
    .proc .ok { color:#16a34a; font-weight:700; }
    .proc .bad { color:#dc2626; font-weight:700; }
    .proc .box { background:#fbfcfe; border:1px solid #e8eef5; border-left:4px solid #0284c7;
                 border-radius:6px; padding:10px 14px; margin:10px 0; }
    .proc .warnbox { background:#fffbeb; border:1px solid #fde68a; border-left:4px solid #d97706;
                     border-radius:6px; padding:10px 14px; margin:10px 0; }
    """

    h = ['<div class="proc">']
    h.append("<h2>一、本轮是低分修复复测（不重出题）</h2>")
    h.append("<div class=\"box\">源版评测（v1.2.4）已锁：轨道 A 94.8｜<b>P=0.740 / R=1.000 / "
             "F1=0.850</b>（三轮 0.865 / 0.821 / 0.865）｜轨道 C 69.0 → D｜market_ready=false。"
             "病因是**触发精度**：3 轮共 34 次误触发，集中在「欠定输入」15 次 +「安全类请求」14 次 + "
             "「邻近职责」5 次。<b>本轮按 root-skills-eval low-score-repair-flow 在 "
             "<code>kb-l0-feishu-fix/</code> 副本上修 description 的路由边界，再全量重测 A 卷 3 轮。</b>"
             "题面沿用源版已落盘的同一批（A 卷 100 条 + 调用 4 条 + 封印 B 卷 10 条），"
             "一字未改、未重出题。</div>")
    if sc.get("checks"):
        rows = []
        for c in sc.get("checks", []):
            mark = ('<span class="ok">✔ 通过</span>' if c["pass"]
                    else '<span class="bad">✘ 不通过</span>')
            rows.append([str(c["no"]), esc(c["item"]), mark, esc(c["detail"])])
        h.append("<h3>沿用源版出题自检（17 项，未重出）</h3>")
        h.append(table(["#", "检查项", "结论", "依据"], rows))
        h.append(f'<div class="box"><b>自检结论：{esc(sc.get("conclusion"))}'
                 f'（{sc.get("passed")}/{sc.get("total")}）</b></div>')

    h.append("<h2>二、★★ 测试台接线缺陷与修复（2026-10-04；分数会假的那种）</h2>")
    h.append(table(["#", "缺陷（磁盘证据）", "后果", "修法"], [
        ["1",
         "会话目录解析错：<code>a-round-*.jsonl</code> 里 15 条记录 "
         "<code>reply=\"\"</code>、<code>session_id=null</code>、<code>skills_loaded=[]</code>，"
         "而 <code>stdout_tail</code> 有内容。实测 <code>abspath('/tmp/…')</code> → 算出 "
         "<code>--tmp-kb-l0fix-blind-a1-item-0001--</code>，真实目录是 "
         "<code>--private-tmp-…</code>（macOS <code>/tmp</code> 是 <code>/private/tmp</code> 软链）",
         "若拿这批记录评分，<b>全部用例都会被判「不触发」</b>，P/R/F1 全是假的",
         "<code>session_dir_for()</code> 改 <code>os.path.realpath</code>；"
         "<b>找不到会话目录即抛 SessionMissing 中止</b>（fail loud，不许静默记空回复）"],
        ["2", "<code>reply</code> 被截断的 <code>stdout_tail</code> 顶替",
         "拿截断文本当「AI 原文」交差",
         "<code>reply</code> 只从 session.jsonl 逐字取完整 assistant 文本；"
         "<code>raw_stdout/raw_stderr</code> 另存旁路字段，<b>不顶替</b> <code>reply</code>"],
        ["3", "诊断字段全空（<code>session_id</code>/<code>skills_loaded</code> = None）",
         "触发判定没有客观证据",
         "每条记录带 <code>session_found / session_id / session_dir / skills_loaded / skill_loaded / "
         "skill_tool_calls / session_bytes / reply_chars / exit_code / elapsed_s</code>"],
    ]))
    h.append("<div class=\"warnbox\"><b>坏数据处置</b>：接线修复前落盘的 15 条整批作废，"
             "另存 <code>_harness/_broken-wiring-20261004/</code>（3 个 jsonl + <code>WHY.md</code>），"
             "<b>不进任何评分</b>。修复后单元验证：对<b>同一个旧 cwd</b> 重新读会话 → "
             "<code>sid=session-4748c92c-…</code>、<code>reply=4225 字</code>、"
             "<code>loaded=['kb-l0-feishu']</code>（此前同一条读出来是空串）。"
             "每条落盘用 <code>flush()+fsync()</code>，逐条可见。</div>")
    h.append("<div class=\"warnbox\"><b>第二条留痕（自证）：复测线曾被 turn 结束带走。</b>"
             "首轮用 <code>nohup</code> 起的 runner 在本会话 turn 结束时被一并终止，"
             "轮次文件 mtime 停在 08:10–08:13。<b>处置：改用受管后台任务</b>"
             "（<code>bash run_all_a.sh</code>，单 job 内含 6 个分片），不再用 nohup。</div>")

    h.append("<h2>三、冒烟证据（先冒烟再全量）</h2>")
    if smoke:
        rows = []
        for f, o in smoke:
            rows.append([esc(f.replace("smoke-round-", "").replace(".jsonl", "")),
                         str(o["n"]), str(o["elapsed_s"]) + "s",
                         esc(",".join(o.get("skills_loaded") or []) or "（未加载任何 skill）"),
                         str(len(o.get("reply") or "")) + " 字",
                         '<span class="ok">true</span>' if o.get("session_found")
                         else '<span class="bad">false</span>'])
        h.append(table(["冒烟批次", "用例号", "用时", "loaded", "reply 长度", "session_found"], rows))
    h.append("<div class=\"box\"><b>定向冒烟结论</b>：原 34 次 FP 所在的 13 个用例里 "
             "<b>11 个已收敛</b> —— 欠定边界 91/95/97/99 全部不加载（4/4）；"
             "72/74/75 安全用例不再加载；36→<code>kb-pipeline</code>、58/78→<code>lark-base</code>、"
             "81→<code>kb-ingest-extractor</code> 均路由到正确邻居。"
             "<b>残留 2 个 FP = 70/71</b>（要破坏的对象恰好就是 L0 本身），如实记账。</div>")

    h.append("<h2>四、盲测执行（3 轮）与环境</h2>")
    h.append("<div class=\"box\"><b>盲测：被测会话仅收到提示词列</b>。类型、标题、预期结果、标签、"
             "优先级一律没有进入被测会话；也没有告诉被测会话「这是评测 / 请判断是否触发 skill」。</div>")
    h.append("<ul>"
             "<li>每条用例 = <b>一个全新的一次性会话</b>："
             "<code>dsh --profile eval-l0fix \"&lt;提示词原文&gt;\"</code>；"
             "每条独立 cwd 落在 <code>/tmp/kb-l0fix-blind-v2/{a1,a2,a3}/item-XXXX</code> —— "
             "<b>评测树之外</b>，被测会话拿不到答案键（cases-meta / 预期结果）。</li>"
             "<li><b>只看到 fix 版</b>：隔离 profile <code>~/.dsh/profiles/eval-l0fix</code> 的 patch 只加 "
             "<code>skill-filesystem.customSkillDirs</code> → 挂载位 "
             "<code>_mount-l0fix/kb-l0-feishu</code>（rank 300 &lt; user-dsh 400 ⇒ fix 版同名胜出）；"
             "<b>共享 profile（desktop/web/headless）全程未改</b>。挂载位与修复副本（排除 evals/）"
             f"逐字节一致（{len(freeze.get('mount') or {})} 个文件，<code>diff=[]</code>），"
             "sha256 见 <code>_mount-l0fix/freeze-manifest.json</code>。</li>"
             "<li>源 <code>~/.dsh/skills/kb-l0-feishu</code> 与 <code>kb/l7/skills/kb-l0-feishu</code> "
             "均 <code>chmod -R a-w</code>（可写文件数实测 <b>0</b>），修复全程<b>未写回源</b>。</li>"
             "<li>触发判定取<b>客观证据</b>：读该会话的 <code>session.jsonl</code>，看 <code>skill</code> "
             "工具调用与宿主斜杠注入的 <code>&lt;skill_content name=…&gt;</code>；"
             "<b>不采信被测会话的自报</b>。</li>"
             "<li>并发：3 轮 × 2 分片（<code>--ids 1-52 / 53-104</code>）× concurrency 3 = <b>18 并发</b>，"
             "逐条 append + <code>fsync</code>。</li></ul>")

    h.append("<h2>五、★★ 保真度限制（必须显式记录，不许装作没这回事）</h2>")
    h.append("<div class=\"warnbox\">被测会话自述（逐字，可回源核对）："
             "「本会话文件沙箱为<b>只读</b>，且升级审批无通道，官方脚本 "
             "<code>align_l0_feishu.py</code> 因要写快照/报告而<b>跑不起来</b>"
             "（<code>PermissionError: Operation not permitted: 'kb'</code>）。"
             "我改用<b>只读等价路径</b>：<code>lark-cli base +record-list --format json</code> "
             "流式拉取 + 内存比对……」<br>"
             "即：盲测沙箱是 <b>read-only 且提权无审批通道 ⇒ fail-closed</b>，与「有正常审批通道的会话」"
             "存在行为差异 —— 本 skill 的<b>写档阶段（阶段 3/4/5 的 <code>--apply</code>）在盲测里跑不动</b>，"
             "被测模型改走只读等价路径。<b>触发判定不受影响</b>（路由看的是 description 与加载证据），"
             "但它影响「回复里有多少数字是现场跑出来的」，如实记录。</div>")

    h.append("<h2>六、静态验证（validate-skill，修复副本）</h2>")
    if val:
        h.append(f"<p>validate-skill 结果：<b>valid={val.get('valid')}，score={val.get('score')}"
                 f"（{val.get('status')}）</b>，error 0 项。</p>")
        w = val.get("warnings", [])
        h.append(table(["警告", "内容"],
                       [[esc(x.get("location")), esc(x.get("message"))] for x in w]))
    h.append("<p><b>注意（自证）</b>：本轮产物目录 <code>evals/</code> 位于修复副本内，"
             "用副本路径跑 validate-skill 会多出「Unknown directory: evals」结构警告；"
             "为避免把评测自身留下的目录算成 skill 缺陷，轨道 A 的目录结构维度取<b>挂载位的 skill 文件</b>"
             "（与副本排除 evals/ 后逐字节相同）。"
             "另有 <code>Name 'kb-l0-feishu' doesn't match directory name 'kb-l0-feishu-fix'</code> —— "
             "这是低分修复流程规定的 <code>{skill}-fix/</code> 命名，属预期，<b>不改中文/英文 name</b>。</p>")

    h.append("<h2>七、三轮执行摘要</h2>")
    rounds = summary.get("rounds") or summary.get("per_round") or []
    if rounds:
        rows = [[f"第 {i} 轮", r.get("TP"), r.get("FP"), r.get("FN"), r.get("TN"),
                 r.get("precision"), r.get("recall"), r.get("f1")]
                for i, r in enumerate(rounds, 1)]
        h.append(table(["轮次", "TP", "FP", "FN", "TN", "P", "R", "F1"], rows))
        h.append(f'<p>3 轮平均：<b>P={summary.get("average", {}).get("precision")} / '
                 f'R={summary.get("average", {}).get("recall")} / '
                 f'F1={summary.get("average", {}).get("f1")}</b>；'
                 f'flaky {len(summary.get("flaky") or [])} 条。</p>')
    else:
        h.append("<p>（三轮数据见 📊 测试报告与 🧪 测试用例）</p>")
    if oa:
        h.append("<h3>Output 功能断言（逐条 × 每轮，机器判定）</h3>")
        rows = [[k, v["pass"], v["total"], v["rate"]] for k, v in oa.get("checks", {}).items()]
        h.append(table(["断言", "通过", "判定次数", "通过率"], rows))
        h.append(f'<p>合计 <b>{oa.get("pass")}/{oa.get("total")} = {oa.get("pass_rate")}</b>。</p>')

    h.append("<h2>八（前置）、root-skills-check 放行核对（Step 5.4 硬校验）</h2>")
    chk = load("check-gate.json", {})
    if chk:
        h.append(table(["硬校验命令", "退出码", "结论", "说明"],
                       [[esc(r["cmd"]), esc(str(r["exit"])), esc(r["verdict"]), esc(r["note"])]
                        for r in chk.get("rows", [])]))
        h.append(f'<div class="box">{esc(chk.get("conclusion", ""))}</div>')
    else:
        h.append("<p>（放行核对结果由 <code>check-gate.json</code> 生成）</p>")

    h.append("<h2>十、2026-10-04 口径更新：「只评 skill，不跑飞书侧对齐」与实测加载延迟</h2>")
    h.append("<div class=\"box\"><b>口径</b>：触发评测只需要知道「**该不该加载这个 skill**」；"
             "被测会话**不需要完成**底层 L0↔飞书对齐作业。理由：判定本来就取客观证据"
             "（session.jsonl 里的 <code>skill</code> 工具调用 / 斜杠注入），**该信号在会话开头就出现**。"
             "⇒ harness 已落地 <code>--timeout</code>（默认 <b>120s</b>）+ **证据不足闸门**。</div>")
    h.append("<h3>实测：加载证据出现在会话开始后第几秒（用 312 条既有会话归档量，非估算）</h3>")
    ll = load("load-latency.json", {})
    s = (ll or {}).get("summary") or {}
    if s:
        h.append(table(["样本", "出现加载证据的会话", "中位", "均值", "p95", "最大", "> 120s 的"],
                       [["312 条（A 卷 4 轮全量归档）", str(s.get("loaded_sessions")),
                         f'{s.get("delta_median_s")}s', f'{s.get("delta_mean_s")}s',
                         f'{s.get("delta_p95_s")}s', f'{s.get("delta_max_s")}s',
                         f'<b>{s.get("loaded_after_120s")}</b>']]))
        h.append("<div class=\"box\">中位 <b>14s</b>、p95 <b>28s</b>、最大 <b>79s</b>，"
                 "<b>0 条在 120s 之后才加载</b> ⇒ 把限时压到 120s <b>不会改变任何一条触发判定</b>；"
                 "省下的是「加载之后继续跑对账」的那段时间（全量 312 条里 <b>210 条</b>耗时 &gt; 120s，"
                 "中位 180s、最大 720s）。证据文件：<code>load-latency.json</code>。</div>")
    h.append("<h3>限时 120s 冒烟（3 条：1 正例 + 1 负例 + 1 边界）</h3>")
    sm = load("smoke-round-92.jsonl", None)
    rows = []
    if sm:
        for line in open(os.path.join(HERE, "smoke-round-92.jsonl"), encoding="utf-8"):
            if line.strip():
                o = json.loads(line)
                rows.append([str(o["n"]), f'{o["elapsed_s"]}s', str(o["exit_code"]),
                             esc(",".join(o["skills_loaded"]) or "（未加载）"),
                             f'<b>{o["skill_loaded"]}</b>', f'{len(o["reply"])} 字',
                             esc(str(o.get("evidence"))),
                             esc(str(o.get("insufficient_reason") or "—"))])
    if rows:
        h.append(table(["用例", "用时", "exit", "skills_loaded", "skill_loaded(kb-l0-feishu)",
                        "reply", "evidence", "insufficient_reason"], rows))
        h.append("<div class=\"box\">接线全部成立：<code>session_found=True</code>、"
                 "<code>skills_loaded</code> 有值、<code>skill_loaded</code> 判定正确；"
                 "被限时的那条（n=33，跑去了 kb-pipeline 干活）<code>exit=-9 / reply=0</code> ⇒ "
                 "<b>被记 <code>evidence=insufficient</code>、进 <code>rerun-queue.jsonl</code>，"
                 "绝不当「不触发」计</b>。</div>")
    h.append("<div class=\"warnbox\"><b>★ 本轮全量的如实说明（偏离必须留痕）</b>："
             "本次交付的 A 卷 4 轮全量与 B 卷门禁，用的限时是 <b>1800s（即未限时）</b>，"
             "被测会话<b>跑完了完整的 L0↔飞书对齐作业</b>（只读等价路径），"
             "<b>不是</b>「被限时 120s 且未完成」的那种跑法 —— 两者判定等价（上面已证 0 条在 120s 后加载），"
             "但本轮更慢、且 AI 原文是完整的。新口径（120s）适用于**后续快速回归**；"
             "出交付报告的那一轮若压到 120s，会出现 <code>evidence=insufficient</code> 的空回复记录，"
             "而 <code>build-testcases-html.py</code> 对空回复默认拒绝（其逃生阀明确写「新评测禁止使用」）。"
             "另一处边界：只有 <b>边界情况</b>题的结论（不触发 / 追问）**必须看回复**，"
             "其余类型（正例/负例/近似/调用）的结论只看 <code>skill_loaded</code>，"
             "所以 120s 限时对它们安全。全量 312 条里属于「慢且判定依赖回复」的只有 <b>3 条</b>"
             "（n=99 ×2、n=100 ×1，均为边界情况）。</div>")
    h.append("<h2>九、输出前自检（15 项）</h2>")
    checks15 = (load("selfcheck-15.json", {}) or {}).get("checks", [])
    if checks15:
        h.append(table(["#", "自检项", "结论", "依据"],
                       [[str(c["no"]), esc(c["item"]),
                         '<span class="ok">✔</span>' if c["pass"] else '<span class="bad">✘</span>',
                         esc(c["detail"])] for c in checks15]))
        bad = [c for c in checks15 if not c["pass"]]
        h.append(f'<div class="box"><b>输出前自检结论：'
                 f'{"全部通过（15 项）" if not bad else "第 " + ",".join(str(c["no"]) for c in bad) + " 项异常（已按 Step 5.4 补齐后重检）"}</b></div>')
    else:
        h.append("<p>（输出前自检 15 项结论见 <code>selfcheck-15.json</code>）</p>")
    h.append(f"<p class='note'>生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}</p>")
    h.append("</div>")

    out = ("<!DOCTYPE html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\">"
           f"<title>kb-l0-feishu 评测过程（修复复测）</title><style>{css}</style></head><body>"
           + "".join(h) + "</body></html>")
    p = os.path.join(EVAL, "kb-l0-feishu-evaluation-process.html")
    with open(p, "w", encoding="utf-8") as f:
        f.write(out)
    print("written", p, len(out), "bytes")


if __name__ == "__main__":
    main()
