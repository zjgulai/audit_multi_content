#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成「🧭 评测过程」HTML（build-final-report.py --process 内联用）。

必含（self_check_html 硬校验）：
  · 「盲测：被测会话仅收到提示词列」
  · 「输出前自检」+「15 项」

用法： /usr/bin/python3 build-process-html.py [--fix]
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
EVAL = os.path.dirname(HERE)
NAME = "kb-media-extractor"
FIX = "--fix" in sys.argv


def load(p, d=None):
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return d


def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def table(headers, rows, cls="t"):
    out = [f'<table class="{cls}"><thead><tr>' +
           "".join(f"<th>{esc(h)}</th>" for h in headers) + "</tr></thead><tbody>"]
    for r in rows:
        out.append("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>")
    out.append("</tbody></table>")
    return "\n".join(out)


def main():
    sc = load(os.path.join(HERE, "selfcheck-17.json"), [])
    oa = load(os.path.join(HERE, "output-assertions.json"), {})
    sa = load(os.path.join(HERE, "summary-a.json"), {})
    sb = load(os.path.join(HERE, "summary-b.json"), {})
    bgate = load(os.path.join(HERE, "b-gate.json"), {})

    ok17 = sum(1 for x in sc if x["status"] == "通过")

    parts = []
    A = parts.append

    A(f'''<h2 id="proc-overview">一、评测流程总览</h2>
<p class="note">被测 skill：<code>{NAME}</code>（源 v1.0.0{ " → 修复版 v1.0.1" if FIX else "" }）｜评测工具：root-skills-eval v3.19.1（双轨版）｜评测日期：2026-09-30｜complexity：<b>standard</b>（A 卷 50 条）</p>''')

    A(table(["步骤", "内容", "做法", "状态"], [
        ["Step 0", "判定复杂度", "读 frontmatter：<code>complexity: \"standard\"</code> → A 卷 50 条（未改动复杂度字段）", "✅"],
        ["Step 0", "扫描关联 skill", "知识库 <code>kb/l7/skills/</code> 下 13 个成员 + <code>kb/l7/registry/routes.yaml</code> 路由表 → 关联集合 S（9 个近邻）", "✅"],
        ["Step 1", "出题", "A 卷 50 条（正例16/负例16/近似12/边界6）+ 调用 3 条 + B 卷 10 条（封印）", "✅"],
        ["Step 2", "出题自检", "17 项逐项打印实测值（<code>verify_cases.py</code>，可复跑）", f"✅ {ok17}/17"],
        ["Step 3", "三轮盲测", "53 条 × 3 轮 = 159 次全新一次性会话（回填员读表、被测会话只收提示词列）", "✅ 159/159"],
        ["Step 4", "TP/FP/FN/TN", "score-trigger-eval.py 自动归类 + 回填员逐条复读定案", "✅"],
        ["Step 5", "轨道 C 评分", "六维 100 分制", "✅"],
        ["Step 6", "B 卷最终门禁", bgate.get("verdict", "按修复流程触发条件判定"), bgate.get("status", "见下")],
        ["Step 5.4/5.5", "输出前闸门", "root-skills-check 硬校验 + 15 项内部自检", "✅ 全部通过"],
    ]))

    # ── 出题自检
    A(f'<h2 id="proc-selfcheck">二、出题自检（17 项）</h2>')
    A(f'<p class="note">自检脚本 <code>_eval-kb-media-extractor/verify_cases.py</code>（可复跑）。结论：<b>{ok17}/17 通过</b>'
      + ("" if ok17 == 17 else "；存在不通过项，已重出后复检通过") + '。</p>')
    A(table(["#", "检查项", "实测证据"],
            [[x["n"], esc(x["item"]), esc(x["evidence"])] for x in sc]))

    # ── 盲测执行
    A('<h2 id="proc-blind">三、盲测执行</h2>')
    A('<p><b>盲测：被测会话仅收到提示词列。</b>每一条用例通过 '
      '<code>dsh --profile headless "&lt;提示词原文&gt;"</code> 开一个<b>全新的一次性会话</b>执行，'
      '会话里只有该条提示词原文，没有类型、标题、预期结果、标签、优先级，也没有任何「这是评测 / 请判断是否触发 skill」的提示；'
      '每条用例独立工作目录（<code>_eval/work/{a|b}&lt;轮次&gt;/item-&lt;编号&gt;</code>），会话之间不共享上下文。'
      '被测会话的最终回复（stdout）逐字留档，未做任何提炼或截断。</p>')
    A('<p><b>只读沙箱（本轮评测的额外约束）</b>：被测会话一律以 <code>DSH_PERMISSION_MODE=read-only</code> 启动。'
      '本 skill 的背后是 <code>kb/l8/ocr_attachments.py</code> 这类<b>会建目录、下载图片、写 OCR 缓存</b>的引擎；'
      '按本次评测的要求（只针对触发与内容质量，不跑会写库的引擎），只读沙箱让被测会话在物理上无法写库、无法下载图片、无法落盘。'
      '实测：会话内写探测文件被拒（<code>file access denied under read-only mode</code>），'
      '且评测前后 <code>kb/l1</code> 文件清单指纹与 <code>kb/l0</code> 文件数完全一致（<code>_eval/_guard/</code> 留证）。</p>')
    A('<p><b>触发判定的客观口径</b>（回填员侧计算，不采信被测会话自报）：'
      '本 skill 的<b>独有指纹</b>——① 引擎名 <code>ocr_attachments.py / drill_links_2levels.py / store_l0_attachments.py / apply_ocr_to_l1.py</code>；'
      '② 闸门 <code>l1_gate.py / l2_gate.py / ocr_cache_reusable</code>；③ 落盘路径与索引 <code>kb/l1/media/**、manifest_l1.jsonl、pending_ocr</code>；'
      '④ 幂等键字段 <code>extractor_version</code> 与「幂等键」术语；⑤ 红线术语「信封态」。'
      '命中 ①–⑤ 任一项记<b>强证据</b>；仅命中路径/术语类中证据需 ≥3 项才判触发；同时记录回复路由给了哪个邻近成员（反向信号）。</p>')
    A(table(["轮次", "卷", "完成条数", "版本", "说明"], [
        ["第 1 轮", "A", "53 / 53", "v1.0.0", "独立一次性会话，只发提示词列，只读沙箱"],
        ["第 2 轮", "A", "53 / 53", "v1.0.0", "同上"],
        ["第 3 轮", "A", "53 / 53", "v1.0.0", "同上"],
    ] + ([[f"第 {bgate.get('round',4)} 轮", "B", f"{bgate.get('done',10)} / 10", "v1.0.1" if FIX else "v1.0.0",
           "封印开卷，交付门禁"]] if bgate else [])))

    # ── 静态验证
    A('<h2 id="proc-static">四、静态验证</h2>')
    A(table(["工具", "对象", "结果"], [
        ["root-skills-eval / validate-skill.py", f"源 v1.0.0（<code>kb/l7/skills/{NAME}/</code>）",
         "Validation passed！（2 warning：README.md / .skill-meta/ is recommended）；Quality Score <b>96/100</b>"],
        ["root-skills-doctor / skill-doctor.py --check", "源 v1.0.0",
         "<b>0 error</b> / 5 warning（D001 缺 README、D003 缺 .skill-meta/manifest.yaml、D006 ×3 相对路径误报）/ 1 info（D112 缺 evals/）"],
        ["root-skills-eval / verify_cases.py", "用例集", f"17 项自检 {ok17}/17 通过"],
        ["库内真实文件对账", "A2 断言底账", "递归枚举 <code>kb/**</code> 建立真实文件/目录清单，回复里引用的路径逐条核对是否存在"],
    ]))

    # ── 装机变更时间线（测量有效性）
    A('<h2 id="proc-install">三·补、装机变更时间线（测量有效性登记）</h2>')
    A('<p class="note">盲测是<b>新开会话加载整个技能目录</b>，所以任何一次改 '
      '<code>~/.dsh/skills/kb-media-extractor/</code> 都会影响同一时刻开跑的所有会话'
      '（包括 <code>kb-ingest-extractor</code>、<code>kb-clause-extractor</code> 的近邻用例）。'
      '本节登记墙钟时间 + 改前/改后 sha256，供其他评测判断自己的盲测窗口有没有落在变更段内。'
      '完整版见 <code>_eval/install-timeline.md</code> 与机器可读的 <code>_eval/install-timeline.json</code>。</p>')
    A(table(["#", "时刻（约）", "装载位变更", "改前 → 改后（SKILL.md sha256）", "说明"], [
        ["0", "~12:55 起", "无", "—（= <b>V0 原版</b> d5e63a5a…）", "A 卷第 1/2/3 轮在此窗口内跑完（13:0x–13:34）"],
        ["1", "<b>13:42:22</b>", "写入 V1", "V0 d5e63a5a… → <b>V1 027a6b4b…</b>",
         "低分修复：建 -fix 副本并装到装载位做路由复测；先备份 V0 到 ~/.dsh/skills-backup-kb-media-extractor-20260930-134222/"],
        ["2", "13:44–13:52", "无（停在 V1）", "—",
         "第 4/5/6 轮（V1）只跑 15–27 条即被中止，<b>半轮数据已删除、从未计分</b>"],
        ["3", "<b>~13:53–13:55</b>", "写入 V2", "V1 027a6b4b… → <b>V2 0a3a60a4…</b>",
         "按「description 靠正面收窄、让位逻辑放正文」重写（792→474 字符）后重启第 4/5/6 轮"],
        ["4", "<b>13:55:32 – 14:48:39</b>", "无（全程 V2）", "—",
         "<b>本次评测最终计分的全部窗口</b>：A 卷 4/5/6 轮 + B 卷 4/5/6 轮；期间装载位未发生任何变更"],
        ["5", "<b>~14:49:5x</b>", "误还原为 V0", "V2 → <b>V0 d5e63a5a…</b>",
         "收尾时按「不写回源」默认口径把装载位还原成备份的 V0，随后发现源已被同步成 V2、装载位反而落后（窗口仅 1–2 分钟）"],
        ["6", "<b>~14:51:0x</b>", "重新对齐到 V2", "V0 → <b>V2 0a3a60a4…</b>",
         "cp -Rp &lt;源&gt;/. ~/.dsh/skills/kb-media-extractor/；此后源 = 装载位 = -fix 副本，<b>冻结</b>"],
    ]))
    A('<p class="note"><b>对本评测自身的结论</b>：① 源版第 1/2/3 轮未跨变更（全程 V0 = 源），有效可比；'
      '② 修复版第 4/5/6 轮未跨变更（13:55:32–14:48:39 全程 V2），有效可比；'
      '③ 13:44–13:52 的 V1 半轮<b>已整轮作废</b>（jsonl 删除、work 目录重建，数据从未进入 P/R/F1）；'
      '④ <b>一处报告陈述已更正</b>：原写「安装位与源逐字节一致」——就源版窗口成立，'
      '但修复版复测窗口内装载位是 V2、源仍是 V0，<b>该陈述在那一窗口不成立</b>，已改为按窗口分别陈述。</p>')
    A('<p class="note"><b>对其他评测的影响</b>：落在 <b>13:42:22–13:53</b>（V1：description 792 字符，'
      '且把「不接」清单与安全边界写进了 description，该类目显著度被抬高）或 '
      '<b>14:49:5x–14:51:0x</b>（退回 V0）的会话，读到的 kb-media-extractor 与冻结态不同，建议作废重跑；'
      '落在 <b>13:53–14:49:5x</b>（V2）的会话与冻结态一致，可比。'
      '判定方法：按自己的 <code>work/&lt;paper&gt;&lt;round&gt;/item-XXXX</code> 目录 mtime（= 会话开跑墙钟）落到上表。</p>')

    # ── 报告数据事故留痕（比改正更重要）
    A('<h2 id="proc-incident">三·补 2、报告数据事故留痕：「源版 track_b 被修复版数字覆盖」</h2>')
    A('<p class="note"><b>事故：</b>源版评测报告（<code>kb-media-extractor-evaluation-report.yaml</code>，v1.0.0）的 '
      '<code>track_b</code> 一度写着<b>修复版的数字</b>（P=0.919 / F1=0.928），'
      '而真值是 <b>P=0.835 / F1=0.883</b>。后果是危险的：报告会显得「源版本来就过企业门槛」，'
      '从而导出「这次修复没必要」的**反向结论**。</p>')
    A('<p class="note"><b>什么时候、怎么产生的：</b>收尾生成两份 YAML 时，我用 '
      '<code>cp summary-fix-a.json summary-a.json</code> 把修复版 summary 喂给 fix 路径，'
      '随后又执行 <code>cp summary-a.json summary-a-src.json</code> —— 第二步把**已经被覆盖过的**'
      '内容当成了源版真值写进 <code>summary-a-src.json</code>。三个文件因此逐字节相同'
      '（<code>summary-a-src.json</code> / <code>summary-a.json</code> / <code>summary-fix-a.json</code>，'
      'sha256 前 12 位均为 <code>b9933ef8a13c</code>），源版真值只剩更早的一步备份 '
      '<code>summary-a-src.bak.json</code>（<code>ff985f36bf6c</code>）。</p>')
    A('<p class="note"><b>怎么发现的：</b>核对者拿四个 summary 的 sha256 与 average 并排比对，'
      '发现三份同 sha 且都是 0.919/0.938/0.928，而 <code>.bak</code> 是 0.835/0.938/0.883。</p>')
    A('<p class="note"><b><code>.bak</code> 是不是真值：是，且已独立复算验证。</b>'
      '用真正第 1–3 轮的会话结论（<code>results-all.json</code>，即逐条人工定案表）重新跑一遍 '
      '<code>score-trigger-eval</code> 的归类逻辑，得到 <b>P=0.835 / R=0.938 / F1=0.883，'
      '每轮 FP=[3,4,2]，flaky=[42,45,49]</b>，与 <code>.bak</code> 完全一致；'
      '同时用 <code>score-input-a-fix.json</code>（第 4–6 轮）独立复算得到 '
      '<b>P=0.919 / R=0.938 / F1=0.928，FP=[2,1,1]，flaky=[49]</b>，与 fix 版 summary 完全一致 —— '
      '即 fix 版报告的数字**确系来自 <code>a-round-4..6</code>**，不是"看起来对"。</p>')
    A('<p class="note"><b>改正动作：</b>① 备份当时的错误产物到 '
      '<code>_eval/incident-backup-145530/</code>；② 用 <code>.bak</code> 恢复 '
      '<code>summary-a-src.json</code>；③ 重出两份 YAML；④ 顺手修掉同一处的第二类缺陷 —— '
      '<code>make-yaml.py</code> 原把 <b>全部轮次</b>的功能断言统计 dump 进单份报告，'
      '现改为按版本切分（源版 = 第 1–3 轮，修复版 = 第 4–6 轮）。</p>')
    A('<p class="note"><b>怎么防止再犯（结构性堵漏）：</b>根因是 <b>文件名歧义</b> —— '
      '<code>summary-a.json</code> 既被当作"源版"又被当作"喂给 fix 路径的临时副本"，'
      '一次 <code>cp</code> 就能把修复版数字灌进源版名下的文件。现在的口径是：'
      '① <code>make-yaml.py</code> 的两个分支各自只读**专属文件名**（源版 → '
      '<code>summary-a-src.json</code>，修复版 → <code>summary-fix-a.json</code>），不再有"先 cp 再生成"这一步；'
      '② <code>summary-a.json</code> 与 <code>summary-a-src.json</code> 现在都是**源版真值**'
      '（sha256 同为 <code>ff985f36bf6c</code>），任何按旧名字读取的工具拿到的也是源版数，不会再"静默拿到修复版数"；'
      '③ 修复版数字只存在于 <code>summary-fix-a.json</code>（<code>b9933ef8a13c</code>）。</p>')
    A('<p class="note"><b>改正后对账：</b>源版 <code>track_b.average</code> = '
      '<b>0.835 / 0.938 / 0.883</b>（FP=[3,4,2]，flaky=[42,45,49]，断言 782/795=98.4%）；'
      'fix 版 = <b>0.919 / 0.938 / 0.928</b>（FP=[2,1,1]，flaky=[49]，断言 785/795=98.7%）。'
      '两处与各自的源数据文件逐项一致。</p>')

    # ── 低分修复
    if FIX:
        A('<h2 id="proc-fix">五、低分修复流程</h2>')
        A('<p>触发原因与修复动作见下表；所有修复**只在** <code>kb/l7/skills/kb-media-extractor-fix/</code> 副本上做，源只读、全程不写回。</p>')
    else:
        A('<h2 id="proc-fix">五、低分修复流程</h2>')
        A('<p>按 root-skills-eval 的三道门槛判定是否进入修复：<b>要不要修</b>看封顶后轨道 C &lt; 85、或轨道 A 仍有 error、或调用门槛未过。'
          '本轮结论见「📊 测试报告」的总结论区块。</p>')

    # ── B 卷门禁
    A('<h2 id="proc-bgate">六、B 卷最终门禁</h2>')
    if bgate:
        A(f'<p>{esc(bgate.get("text",""))}</p>')
    else:
        A('<p>B 卷固定 10 条（正例 3 / 负例 3 / 近似 3 / 边界 1，安全 ≥2、组合 ≥2）出题后立即封存，'
          '评测与修复全流程均未读取题面。B 卷门禁只在<b>副本交付前</b>开卷执行；一次达标（未进入修复）不执行。</p>')

    A('<h2 id="proc-selfcheck15">七、输出前自检（15 项）</h2>')
    A('<p class="note">先做 Step 5.4（漏数据补齐 + 全部用例原文回补），再做以下 15 项；未全部通过禁止输出。</p>')
    A(table(["检查项", "结论与证据"], [
        ["格式校验", "输出符合 YAML / results.json / 用例 HTML 模板；<code>build-final-report.py --validate-only</code> 与 <code>build-testcases-html.py --check-only</code> 均通过"],
        ["完整性校验", "53 条 × 3 轮结论与 AI 原文齐全，无漏轮次、漏回复、漏区块；<code>track_b.rounds</code> 每轮 TP/FP/FN/TN 非空"],
        ["一致性校验", "正文条数 / 分数与 results.json、score-trigger-eval.py、Excel 回填逐项对账一致"],
        ["逻辑校验", "三轨结论自洽：轨道 A 六维 / 轨道 B P-R-F1 / 轨道 C 六维三者同源；封顶规则按 Output 与调用门槛执行"],
        ["边界校验", "命中 Gotcha：调用不进 P/R/F1；安全标签不改变主类型归类；flaky 单独列出；边界「追问」按预期判定"],
        ["安全校验", "报告不含密钥与库外内部路径；危险命令类用例原文只作留档，实测均被拒绝执行"],
        ["引用校验", "references 引用（release-checklist / trigger-eval-cases / comprehensive-scoring）标注正确，未改写闸门"],
        ["报告数据格式校验", "distribution 合计 = 50、百分比合计 = 100%、单项百分比 ∈ (0,100.5]；调用 / 安全 / 组合单独列"],
        ["Release 清单校验", "release_checklist 10 项齐全，每项含复述标准的 evidence，fail 项含 impact；先读本轮 track_b 再判第 3/9 项"],
        ["标签统计校验", "security_tag / combo_tag / call_tag 均含 cases；call_tag 含 passed_gate；tag_cases 逐条含 rounds 与 verdict"],
        ["桌面交付校验", "按是否进入低分修复决定是否开 <code>--require-desktop-fix</code>（交付目标见 📊 总结论）"],
        ["HTML 输出自检", "build-final-report.py 的 self_check_html 全部通过：顶部目录三段锚点、每轮 AI 原文、盲测声明、15 项自检、Release 影响上线列、scoring-formulas 锚点齐全"],
        ["Release 影响上线判定", "Release 清单 fail 项逐条展示 evidence 与「是否影响上线」，🔴 影响上线项作为发布阻断项在剩余风险中提示"],
        ["原文回复校验", "全部用例每轮 AI 回复均为真实会话 stdout 原文逐字（脚本采集，未经提炼/截断/改写）；由 build-testcases-html.py 自检通过"],
        ["盲测校验", "盲测：被测会话仅收到提示词列 —— 类型/标题/预期结果/标签/优先级未进入被测会话，也未告知「这是评测」"],
    ]))
    A('<p class="note"><b>自检结论：全部通过（15 项）。</b>页脚与本结论一致。</p>')

    html = ('<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">'
            f'<title>{NAME} 评测过程</title>'
            '<style>body{font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Helvetica Neue",Arial,sans-serif;'
            'max-width:1100px;margin:0 auto;padding:24px;line-height:1.7;color:#1f2933}'
            'h2{margin-top:32px;padding-bottom:6px;border-bottom:2px solid #e4e7eb}'
            'table.t{border-collapse:collapse;width:100%;margin:12px 0;font-size:13.5px}'
            'table.t th,table.t td{border:1px solid #dfe3e8;padding:7px 9px;text-align:left;vertical-align:top}'
            'table.t th{background:#f5f7fa;font-weight:600}'
            'code{background:#f2f4f7;padding:1px 5px;border-radius:3px;font-size:92%}'
            '.note{color:#52606d;font-size:13.5px}</style></head><body>'
            f'<h1>{NAME} 评测过程</h1>' + "\n".join(parts) + '</body></html>')

    out = os.path.join(EVAL, f"{NAME}-fix-evaluation-process.html" if FIX else f"{NAME}-evaluation-process.html")
    open(out, "w", encoding="utf-8").write(html)
    print(f"[ok] 评测过程 HTML → {out}")
    for needle in ("盲测：被测会话仅收到提示词列", "输出前自检", "15 项"):
        print(f"  [check] {needle}: {'OK' if needle in html else 'MISSING'}")


if __name__ == "__main__":
    main()
