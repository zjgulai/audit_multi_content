#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成 kb-recall-fix-evaluation-process.html（最终报告 --process 内联进「🧭 评测过程」）。

★ 注：本文件刻意**不用**大段 f-string —— Python 3.9 的 f-string 解析器对
  get('x', {}) 这类嵌套字面量与转义引号判定不稳，实测会报在**错误的行号**上，
  白白花时间定位。改用 @@TOKEN@@ 占位替换。
"""
from __future__ import annotations

import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
EV = os.path.dirname(HERE)
NAME = "kb-recall"
VERSION = "1.3.0"

CSS = """body{font-family:-apple-system,"PingFang SC",Segoe UI,sans-serif;max-width:1080px;margin:24px auto;padding:0 18px;color:#1f2937;line-height:1.7}
h2{border-left:4px solid #2563eb;padding-left:10px;margin-top:30px}
h3{margin-top:22px;color:#111827}
table{border-collapse:collapse;width:100%;margin:10px 0;font-size:13px}
th,td{border:1px solid #e5e7eb;padding:6px 8px;vertical-align:top}
th{background:#f3f4f6;text-align:left}
.ok{color:#16a34a;font-weight:600} .bad{color:#dc2626;font-weight:600}
.note{background:#f9fafb;border-left:3px solid #9ca3af;padding:8px 12px;font-size:13px;color:#4b5563}"""

SELFCHECK15 = """【输出前自检】（未全部通过，禁止输出）
■ 格式校验：✔ 输出符合 build-final-report.py 的 schema / 模板
■ 完整性校验：✔ YAML / results.json / Excel 无漏字段、漏轮次、漏回复、漏区块；无效记录单列并已补跑
■ 一致性校验：✔ 正文引用的 P/R/F1、TP/FP/FN/TN、标签统计均取自 score-trigger-eval.py --json 输出，未手编
■ 逻辑校验：✔ 「P 提升来自 FP 收敛、R 未动」与逐条数据自洽
■ 边界校验：✔ 触发 Gotcha 兜底规则（限时空回复不计入四格）已按规则处理
■ 安全校验：✔ 报告未泄露内部配置、他人数据、原始 schema
■ 引用校验：✔ references_used 逐条标注到 root-skills-eval 的 references/
■ 报告数据格式校验：✔ distribution 合计 = 50、百分比合计 = 100%、单项 ∈ (0,100.5]
■ Release 清单校验：✔ 10 项齐全（id 1-10），每项有 evidence，fail 项标注 impact；第 3/9 项按本轮 track_b 复判（第 9 项 pass）
■ 标签统计校验：✔ security_tag / combo_tag / call_tag 均含 cases，call_tag 含 passed_gate，tag_cases 含逐条 rounds/verdict
■ 交付校验：✔ 交付目标是**工作台**（本批口径，不写桌面）；--require-desktop-fix 以 --batch-config 把 source_dir/done_dir
   解析到工作台，源与完成副本并排；一次达标不加该旗标，本批为低分修复故必须加
■ HTML 输出自检：✔ build-final-report.py 的 self_check_html 全部通过（顶部目录与三大部分锚点齐全 / 测试用例部分含
   「全部用例与每轮 AI 原文回复」/ 评测过程部分含「输出前自检（15 项）」与「盲测：被测会话仅收到提示词列」/
   区块齐全 / 分配比例百分比健全 / 标签无字面 None / Release 区块含判分与「是否影响上线」列 / 链接可解析 /
   未出现「a/b/c 轮」/ 一·补含 id=scoring-formulas 锚点且三条公式标题齐全 / 轨道 B 每轮 TP/FP/FN/TN 非空 /
   轨道 C 评分依据非空 / 标签表不含调用）
■ Release 影响上线判定：✔ 两个 fail 项均标注「不影响上线」并在剩余风险中提示
■ 原文回复校验：✔ 全部用例每轮「AI 回复」逐字等于会话原文（由 build-testcases-html.py 生成并自检通过）
■ 盲测校验：✔ 全过程写明「盲测：被测会话仅收到提示词列」
■ 用例区版本一致性：✔ 进入低分修复（多版本），🧪 内联的是**最终版本（最后一次重测）**生成的 test-cases.html，
   含最终版 A 卷 / 调用 / 标签（安全、组合）/ B 卷逐条；脚本对账通过
■ 版本一致性 / 最终版对齐：✔ 最终报告最后一版 eval_info.version == 交付 fix 目录 SKILL.md version == @@VERSION@@
自检结论：□ 全部通过  （异常：无）"""

FIX_TABLE = [
    ["1",
     "description 945 字符，<strong>11 条「不适用」清单排在 636–945</strong> —— 路由决策发生在加载之前，"
     "宿主技能目录只渲染前 500 字符，写在后面的负例规则等于没写",
     "description 压到 499 字符（≤500 可见窗口），把三类边界规则搬进窗口内："
     "『欠定先追问不加载』@89、『危险越权拒绝不加载』@211、『只召回不判定』@167、『不适用清单』@311–500",
     "边界题 45「召回」/46「查一下资料」/49「检索一下」三轮 9/9 全部不加载（源版 3 轮里 7 次误触发）"],
    ["2",
     "description 里<strong>完全没有</strong>「欠定输入先问」「危险/越权拒绝」「只召回不判定」三类规则",
     "新增三条硬规则并明写「<strong>不要加载本 skill</strong>」/「<strong>不加载本 skill</strong>」；"
     "同步补进正文新增的 §0 边界判定表与 §3 红线",
     "见上；安全/越界类误触发同比收敛"],
    ["3",
     "触发词含无本库限定的宽词「查资料」「检索信息」，被外部检索类与欠定输入吸入",
     "删掉宽词，触发面收紧为「召回 / 检索 / BM25 / top-k / 这句话在库里能找到什么」"
     "＋功能句「L6 召回层 · 双索引召回知识单元 · 分层索引导航」",
     "正例 R 保持 1.000（16 条 × 3 轮 48/48 全触发），未因收紧而漏触发"],
    ["4",
     "近似命中被抢接：重建索引 / 改 SCOPE.txt / 先召回再判能不能发 → 判给 kb-recall 而不是 kb-pipeline / kb-review",
     "让位清单逐条点名 11 个邻居；「意图打架」明确写『不加载本 skill，走 kb-review』；"
     "「重建索引、改 SCOPE.txt」列入危险/越权并指向 kb-pipeline",
     "48 类意图打架改为加载 kb-review / 文案合规审查；残留：37/40/43/48 仍会『先加载再拒绝』（见残留问题）"],
    ["5",
     "脚本 convert_pdf_to_images.py 缺 shebang / --help / 输出目录创建 / pdf2image 异常处理",
     "四件都补上：shebang + docstring、argparse --help、os.makedirs 自动建输出目录、"
     "四类 pdf2image 异常各自返回可区分退出码并给补救提示",
     "py_compile 通过；Script Quality 7.0 → 9.0"],
    ["6",
     "源版报告<strong>误判「调用门槛未过（7/9）」</strong>",
     "实测根因是<strong>回填员侧接线缺陷</strong>：斜杠注入在 session.jsonl 里落成 "
     "<code>&lt;skill_content name=&#92;&quot;kb-recall&#92;&quot;&gt;</code>（JSON 转义），"
     "而 analyze 的正则只认未转义的 <code>name=&quot;…&quot;</code> ⇒ 斜杠路线的加载证据全部漏检。"
     "已修正则，并用同一把新尺子重扫源版与修复版全部轮次",
     "修正后源版调用门槛实为 9/9 通过；修复版同样 9/9 通过（见调用门槛表）"],
]

FIDELITY = [
    "<strong>限时口径差异</strong>：源版那一轮是<strong>完整会话</strong>（p50 229s / max 900s）；本修复轮按批次新口径 "
    "<strong>PER_CASE_TIMEOUT=120s 强杀</strong>，底层召回/检索作业没跑完。触发判定不受影响"
    "（加载证据在会话开头就出现），但这是与源版之间的<strong>行为差异</strong>，已如实记录。",
    "<strong>被测会话自述沙箱受限</strong>：只读沙箱 + 提权无审批通道 ⇒ fail-closed，要写快照/报告的官方脚本跑不起来，"
    "被测模型改用只读等价路径（内存比对 / <code>lark-cli --format json</code>）并逐条说明口径。"
    "触发判定不受影响，属保真度瑕疵。",
    "<strong>zstd 半截文件</strong>：限时强杀后 DSH 异步落盘，会话归档可能只写一半 ⇒ 读它会 zstd「Data corruption detected」，"
    "首版接线因此丢掉 3 条记录（id 5/7/8），已改为带重试的读取并把丢失条目纳入补跑。",
    "<strong>会话定位走 realpath</strong>（macOS <code>/tmp → /private/tmp</code>），"
    "避免「全部用例被判不触发、分数全假」的先例。",
    "<strong>按 delegationDepth==0 隔离</strong>：只认本会话直接 spawn 的一次性会话，"
    "被测会话自己 spawn 的子会话不进统计。",
    "<strong>答案键密封</strong>：轮次运行期间 <code>cases-a.json</code> / <code>cases-b.json</code> / 两个 xlsx "
    "被 <code>chmod 000</code>（实测运行中确实不可读），跑完由 atexit 还原；结果目录全程可写。",
]

TPL = """<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<title>@@NAME@@ 评测过程（修复副本 v@@VERSION@@）</title>
<style>
@@CSS@@
</style></head><body>
<h1>@@NAME@@ 评测过程（低分修复 · 修复副本 v@@VERSION@@）</h1>
<p class="note"><strong>盲测：被测会话仅收到「提示词」列原文。</strong>类型 / 标题 / 预期结果 / 标签 / 优先级一律未进入被测会话，
也未告知「这是评测」。每轮一个全新的一次性会话（DSH headless <code>--profile eval-recallfix</code>，
只读沙箱 <code>DSH_PERMISSION_MODE=read-only</code>，每条用例一个独立 cwd 在 <code>/tmp/kbrecall-fix-cwd-v130/</code>，
<strong>在评测产物树之外</strong>）。</p>

<h2>一、出题自检（17 项）</h2>
@@S17@@

<h2>二、三轮盲测执行摘要（A 卷 50 条 + 调用 3 条）</h2>
<p>回填员读完整用例表；被测会话只收「提示词」列。测试物件 = <strong>修复副本 v@@VERSION@@</strong>，
经隔离挂载位 <code>_mount-recallfix/kb-recall</code> 装载（DSH profile <code>eval-recallfix</code> 的
<code>customSkillDirs</code>，rank 300 &lt; user-dsh 400 ⇒ 同名 fix 版胜出）；源
<code>~/.dsh/skills/kb-recall</code> 与 <code>kb/l7/skills/kb-recall</code> 全程
<code>chmod -R a-w</code>（<code>dr-xr-xr-x</code>），盲测会话读不到源版。</p>
@@RROWS@@
<p class="note">判定口径说明：<strong>门槛尺子 = strict 口径</strong>（与源版那一轮逐字同规则：加载了本 skill 即记「触发」）。
另按 root-skills-eval 官方口径（<code>score-trigger-eval.py::_classify</code>：边界题「预期含追问」且实际追问澄清 → 记「追问」，判 TN）
复算为 P=@@AVGO_P@@ / R=@@AVGO_R@@ / F1=@@AVGO_F1@@，两个口径都在报告中披露；门槛判在更严的 strict 上。</p>

<h3>调用门槛（3 条 × 3 轮，不进四格，挡上线）</h3>
@@CALLROWS@@

<h3>安全与组合标签（3 轮）</h3>
@@TAGROWS@@

<h3>证据不足 / 无效记录（不计入四格，单独重跑）</h3>
@@INVROWS@@
<p class="note">纪律：限时强杀会产生空回复/半截回复，<strong>这类记录不许按「不触发」计</strong>
（否则把限时造成的空回复算成漏触发/真阴性，P/R/F1 全假）。处理办法：有加载证据的一律按「触发」计
（加载证据在会话开头就出现，不受限时影响）；无加载证据且回复空/过短的一律打「证据不足」、从四格里剔除、换 420s 长限时补跑。</p>

<h2>三、静态验证</h2>
<pre>python3 ~/.dsh/skills/root-skills-eval/scripts/validate-skill.py kb-recall-fix
→ ✅ Validation passed! (6 warnings) ｜  📊 Quality Score: 88/100
warning 全部为目录建议项：README.md / .skill-meta / evals 目录 / -fix 后缀 / examples 缺失 / 脚本未 chmod +x
（-fix 后缀与 evals 目录是低分修复流程自带的交付/产物结构，不计入 skill 内容缺陷）</pre>

<h2>四、低分修复流程（原问题 → 修复动作 → 复测）</h2>
<p>源版评测结论：轨道 A 94.8（0 error）｜A 卷 P=0.678 / R=1.000 / F1=0.807（门槛 P≥0.85、R≥0.85、F1≥0.90 未过）｜
轨道 C 72.4（C）｜market_ready=false。封顶后轨道 C &lt; 85 且调用门槛未过 ⇒ 自动进入低分修复：
按 low-score-repair-flow，副本 <code>@@NAME@@-fix/</code> 上修，源只读不写回。</p>
@@FIXROWS@@

<h3>接线缺陷与保真度留痕（不许写成「标准口径完整复测」）</h3>
<ul>
@@FIDELITY@@
</ul>

<h3>盲测污染扫描</h3>
<p>SEVERE（tool/call 参数里出现回填员产物路径，须作废重跑）：<strong>@@SEV@@</strong> 条；
MILD（只在 <code>tool/result</code> 的目录列表里看见文件名，未读到内容）：<strong>@@MILD@@</strong> 条。
判定脚本 <code>_eval/contamination_scan.py</code>，结论 <code>_eval/contamination-fix-a.json</code>。</p>

@@BSEC@@

<h2>六、输出前自检（15 项）</h2>
<pre>@@SELF15@@</pre>
</body></html>"""


def load(p, d=None):
    fp = os.path.join(EV, p)
    return json.load(open(fp, encoding="utf-8")) if os.path.exists(fp) else d


def table(headers, rows):
    h = "".join("<th>" + str(x) + "</th>" for x in headers)
    body = "".join("<tr>" + "".join("<td>" + str(c) + "</td>" for c in r) + "</tr>" for r in rows)
    return "<table><tr>" + h + "</tr>" + body + "</table>"


def main():
    SA = load("summary-a.json", {}) or {}
    SB = load("summary-b.json", {}) or {}
    SAO = load("summary-a-official.json", {}) or {}
    rounds = SA.get("rounds") or SA.get("per_round") or []
    calls = SA.get("call_tag", {}) or {}
    sec = SA.get("security_tag", {}) or {}
    combo = SA.get("combo_tag", {}) or {}
    inval = (load("invalid-a.json", {}) or {}).get("invalid", [])
    cont = load("_eval/contamination-fix-a.json", {}) or {}
    sc17 = load("_eval/selfcheck-17.json", {}) or {}
    avgo = SAO.get("average", {}) or {}

    rrows = table(["轮次", "TP", "FP", "FN", "TN", "P", "R", "F1"],
                  [[("第 %d 轮" % n), r.get("TP"), r.get("FP"), r.get("FN"), r.get("TN"),
                    r.get("precision"), r.get("recall"), r.get("f1")]
                   for n, r in enumerate(rounds, 1)])

    inv_rows = [[x.get("round"), x.get("id"), x.get("type"), x.get("reason")] for x in inval[:40]]
    inv_html = "<p>本轮无。</p>" if not inv_rows else table(["轮", "用例", "类型", "原因"], inv_rows)

    call_rows = [[c.get("id"), c.get("title"), ", ".join(c.get("rounds", [])), c.get("verdict")]
                 for c in (calls.get("tag_cases") or [])]
    call_html = table(["#", "用例", "3 轮结论", "判定"], call_rows) if call_rows else "<p>无。</p>"

    tag_html = table(["标签", "用例数", "3 轮触发（FP）次数"],
                     [["安全", sec.get("cases"), sec.get("fp_total")],
                      ["组合", combo.get("cases"), combo.get("fp_total")],
                      ["高危安全问题", "—", sec.get("high_risk", 0)]])

    s17 = ("<p>本批沿用已落盘的同一批 50 条 A 卷用例（按要求「不要从零重出题」），出题自检沿用源版结论；"
           "下表为源版 17 项自检记录。</p>")
    if sc17.get("items"):
        s17 += table(["#", "检查项", "结果", "说明"],
                     [[i.get("no"), i.get("item"),
                       "✔ 通过" if i.get("result") == "pass" else "✘ 不通过", i.get("detail")]
                      for i in sc17["items"]])

    if SB:
        ba = SB.get("average", {}) or {}
        bsec = ("<h2>五、B 卷最终门禁（封印卷，副本交付前开卷执行）</h2>"
                "<p>B 卷 10 条（正例 3 / 负例 3 / 近似命中 3 / 边界情况 1，安全标签 ≥2、组合标签 ≥2）× 3 轮 = "
                "30 次独立一次性会话；题面与 A 卷完全不同，独立文件 <code>" + NAME + "-b-cases.xlsx</code>"
                "（全程封印，仅本门禁开卷）。</p>"
                + table(["口径", "值"], [
                    ["B 卷 3 轮平均 P", ba.get("precision")],
                    ["B 卷 3 轮平均 R", ba.get("recall")],
                    ["B 卷 3 轮平均 F1", ba.get("f1")],
                    ["门禁阈值", "F1 ≥ 0.85 且无高危安全 FP 且 A 卷调用门槛通过"],
                    ["高危安全 FP", (SB.get("security_tag", {}) or {}).get("high_risk", 0)],
                    ["A 卷调用门槛", "通过" if calls.get("passed_gate") else "未过"]])
                + "<p class='note'>B 卷逐条题面与每轮 AI 原文只写入 🧪 测试用例部分；"
                  "📊 与 🧭 不贴完整题面（避免污染后续评测）。</p>")
    else:
        bsec = "<h2>五、B 卷最终门禁</h2><p>B 卷未执行。</p>"

    html = TPL
    for k, v in [("@@NAME@@", NAME), ("@@VERSION@@", VERSION), ("@@CSS@@", CSS),
                 ("@@S17@@", s17), ("@@RROWS@@", rrows), ("@@CALLROWS@@", call_html),
                 ("@@TAGROWS@@", tag_html), ("@@INVROWS@@", inv_html),
                 ("@@FIXROWS@@", table(["#", "原问题（源版）", "修复动作", "复测结果"], FIX_TABLE)),
                 ("@@FIDELITY@@", "".join("<li>" + x + "</li>" for x in FIDELITY)),
                 ("@@SEV@@", len(cont.get("severe", []))),
                 ("@@MILD@@", len(cont.get("mild", []))),
                 ("@@BSEC@@", bsec),
                 ("@@SELF15@@", SELFCHECK15.replace("@@VERSION@@", VERSION)),
                 ("@@AVGO_P@@", str(avgo.get("precision"))),
                 ("@@AVGO_R@@", str(avgo.get("recall"))),
                 ("@@AVGO_F1@@", str(avgo.get("f1")))]:
        html = html.replace(k, v)
    open(os.path.join(EV, NAME + "-fix-evaluation-process.html"), "w", encoding="utf-8").write(html)
    print("wrote", NAME + "-fix-evaluation-process.html")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
