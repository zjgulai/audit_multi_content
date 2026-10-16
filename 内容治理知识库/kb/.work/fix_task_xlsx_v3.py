#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""修 G6 内两处自相矛盾 + 依据改成可核的。"""
import zipfile, os, re, html, shutil, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

P = os.path.expanduser("~/Desktop/内容治理知识库搭建任务详情.xlsx")
TMP = P + ".new"; SHEET = "xl/worksheets/sheet1.xml"

NEW_BLOCK = """【10/10 14:20 本轮实测（独立复核，只读库）】
结果：**必须做 2 项（⑭ 9 场景覆盖表 / 全文回验）**｜**不做 3 项**｜**另 1 项是记账缺陷（可直接修，不是"做不做"问题）**。

必须做
⑭ **9 场景覆盖表** —— 依据：PRD §7.3 七项一票否决，**4 项在 L3(1018 行)+L5(11 条) 里 0 命中**（车内安全座椅·副驾·独留 / 危险行为示范 / 未成年人出镜 / AI 标识）；PRD §7.1 把「车内场景」标为极高·一票否决域；`l7.json` 词表「婴幼儿安全与场景」挂 7 个场景域、**规则码列表为空**。
　影响：主图/视频出现"安全座椅装副驾""趴睡"，**库给不出依据**，评审链只能靠模型自己。
　⚠ 更正一句：**不是"库里没有素材"** —— L0 里这四类只有零散噪声命中（"安全座椅"落在设计审核群聊天记录、"可以用AI生成"是一条建议），**没被抽成规则**。真源候选：`母婴设计常识清单 V2.0`（设计审核群 2026-07 起反馈汇总，L1 有）。
　⚠ **待 Owner 拍**：规则来源走法规原文还是内部红线 —— 没定来源不写 L5。
　⚠ 与本行末尾【是否要做】块里"不做 ⑭"冲突：**以本块为准**（那条写于 14:20 之前，当时按"引擎有 coverage_gap 标记 ⇒ 人手清单不改变输出"判的；本轮量化后判定改变）。
**全文回验** —— 依据：实测**回验覆盖 1/510 = 0.2%**，32 个字面量里 6 个未在来源中找到（1,365 / 1,018 等）；低于 30% 门槛 ⇒ 幻觉率**不进健康分分母**。
　影响：**"库里的数字准不准"到今天还没被量过**；对外报的每个数都是未经回验的。

不做
⑰ **基线表**（已建成，只做不引）—— 依据：没有它也不影响判断（一条命令现算）；它只解决"对外文件里的数字能不能对账"。
⑮ **蒸馏工单** —— 依据：上游没货（同期多条素材停在 🟡）；库内明文警告**未裁决素材进 L3 = 把噪声固化成条款**。替代：改记「阻塞」+ 写明阻塞条件。
⑯ **W-4 编号段** —— 依据：段位定义早已存在（`l4.json`：`wording_boundary` / `reserved_unused`），缺的是**实体规则**，属"等内容"不属"要做事"。

记账缺陷（可直接修、不依赖任何前置）
· `l4.json` 的 `reserved_unused_segments` 把**已在用的 E-2**（`clause.jsonl` 123 条）列成了"未用" —— 同一份注册表自相矛盾，一行可改。
· 号段现状：E-1 375 / E-2 123 / S-1 316 / W-1 56 / W-2 453 / W-3 157 = 1480 条，全部有号、无重复。

【10/10 14:20 口径落定】
· 「一单」= **一次评审运行**（`source=review_machine` 行数，现 562），**不是素材数**（同一段文案送审三次算三单）。
· 旧值不再引用：112（按任何日期切法都不等于 112：≤10/1=45｜≤10/2=142｜10/3 起=205）｜183 / 155（index.jsonl 里无对应字段，distinct trigger 文本 = 199）。
· 基线表现读数（**连采样时点一起引**）：健康分 **79.3**（不通过，因错误项 451 条非空）｜孤岛率 **0.9412**｜检索命中 **433/557=77.7%**｜评审单 **562**。
　同日 12:04 采样 76.7、12:15 采样 79.3，**两次都真**（kb/view 持续重建）⇒ 不连时点引 = 没法对账。
　「口径 A 健康分」与日更「GREEN / 闸门红 0」**不是同一把尺子**：`daily-health-latest.json` 里 健康分/孤岛/覆盖率/利用率 **各 0 次命中**。
※ 本块的**依据**已内联在每条（不再是"依据见 playbook"）—— `failure-playbook.yaml` 只覆盖 ⑩⑫ 两条（id: finding.l3_p_level_vs_l5_p0_mismatch / finding.w014_uses_created_at_as_basis），其余各条的依据是本轮逐词实测。"""

G6_LINE_OLD = "【是否要做｜10/10 查证】**本条无遗留必做项 ⇒ 能力面已达成**"
G6_LINE_NEW = "【是否要做｜10/10 查证】**本条能力面无遗留必做项**（跑通 562 run 超额；三个写死的默认值已改成真读库；「谁负责/何时生效」10/10 补完 1018/1018）"

z = zipfile.ZipFile(P); items = z.infolist(); xml = z.read(SHEET).decode("utf-8")
i = xml.index('<c r="G6"'); j = xml.index("</c>", i) + 4
cell = xml[i:j]
t = html.unescape(re.search(r"<t[^>]*>(.*?)</t>", cell, re.S).group(1))

s0 = t.index("【10/10 14:20 本轮实测（独立复核，只读库）】")
s1 = t.index("〔备注〕本条 ⑤⑥ 项")
tn = t[:s0] + NEW_BLOCK + "\n" + t[s1:]
assert G6_LINE_OLD in tn
tn = tn.replace(G6_LINE_OLD, G6_LINE_NEW, 1)

new_cell = cell.replace(re.search(r"<t[^>]*>.*?</t>", cell, re.S).group(0),
                        f'<t xml:space="preserve">{html.escape(tn, quote=False)}</t>', 1)
new_xml = xml.replace(cell, new_cell, 1)
assert "ns0" not in new_xml
assert new_xml.count("<row ") == xml.count("<row ")
assert new_xml.count('customHeight="1"') == xml.count('customHeight="1"')
ET_ok = __import__("xml.etree.ElementTree", fromlist=["x"]); ET_ok.fromstring(new_xml)
print(f"G6 {len(t)} → {len(tn)} 字")

with zipfile.ZipFile(TMP, "w", zipfile.ZIP_DEFLATED) as out:
    for it in items:
        out.writestr(it, new_xml.encode("utf-8") if it.filename == SHEET else z.read(it.filename))
z.close()
shutil.move(TMP, P)
print("已写回", P, os.path.getsize(P), "字节")
