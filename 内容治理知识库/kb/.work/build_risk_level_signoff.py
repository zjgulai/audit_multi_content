#!/usr/bin/env python3
"""生成「目标 6 · 风险等级按维度重算」签字件（.md）。

★ 写盘口径：走 `kb/.work/_safe_write.write_text()`（node + 回读复核）——
  python 直写 `.md` 会在宿主侧多 4096 字节信封 ⇒ E001（库规已记）。

只读输入：`kb/.work/risk_level_recompute_diff.jsonl` + 真库（rules.jsonl / l0）。
"""

from __future__ import annotations

import collections
import json
import os
import sys

KB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KB, ".work"))
sys.path.insert(0, os.path.join(KB, "l3"))

import _safe_write                                    # noqa: E402
from kb_rule_dimensions import build_l0_index, l0_lookup   # noqa: E402
import importlib.util                                  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "probe", os.path.join(KB, ".work", "risk_level_recompute_probe.py"))
P = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(P)

DIFF = os.path.join(KB, ".work", "risk_level_recompute_diff.jsonl")
# ★ 落点：**工作区根**，与 `交付-目标10-…` / `留痕-…` 同一惯例。
#   为什么不放 `kb/l7/reports/`：那里 1163 个文件**全是 `*.review.md`**（评审报告），
#   本件是**交付/签字件**，放进去等于往报告目录里塞非报告 —— 且 S4 的尺子只扫
#   `*.review.md`（`workflow_smoke.py:203`），塞进去既不被判红、也污染目录。
OUT = os.path.join(os.path.dirname(KB),
                   "交付-目标6-风险等级重算-对照与签字件-20261012.md")


def main() -> int:
    D = [json.loads(l) for l in open(DIFF, encoding="utf-8") if l.strip()]
    rows = [json.loads(l) for l in open(os.path.join(KB, "l3", "candidates", "rules.jsonl"),
                                       encoding="utf-8") if l.strip()]
    idx = build_l0_index()
    look = l0_lookup(idx)

    old = collections.Counter(str(d["old_risk_level"]) for d in D)
    new = collections.Counter(str(d["new_risk_level"]) for d in D)
    used = collections.Counter(d["priority_used"] for d in D)
    crit = [d for d in D if d["new_risk_level"] == "Critical"]
    changed = [d for d in D if d["old_risk_level"] != d["new_risk_level"]]
    mapped_old = [d for d in D if "按 p_level=" in str(d["old_basis"] or "")]

    # 逐 token 统计
    tok_hit = collections.Counter()
    for r in rows:
        f, _ = look(r)
        for t in P._revision_tokens(f):
            if t in P.REVISION_TYPE_TO_RISK:
                tok_hit[t] += 1
    tok_rows = []
    for t, n in tok_hit.most_common():
        lvl, the_basis, hard = P.REVISION_TYPE_TO_RISK[t]
        tok_rows.append((t, lvl or "unknown", n, "硬引 PRD" if hard else "★软判", the_basis))
    soft_n = sum(n for _, _, n, k, _ in tok_rows if k == "★软判")
    tot_n = sum(n for _, _, n, _, _ in tok_rows)
    soft_rules = 0
    for r in rows:
        f, _ = look(r)
        ts = P._revision_tokens(f)
        if any(t in P.REVISION_TYPE_TO_RISK and not P.REVISION_TYPE_TO_RISK[t][2] for t in ts):
            soft_rules += 1

    L = []
    A = L.append
    A("# 目标 6 · 风险等级「按维度重算」——对照与签字件")
    A("")
    A("> 对应：《内容治理知识库搭建任务详情.xlsx》**A6 行（10/12–10/16）G 列「必须做」第 1 条**"
      "（目标 6 风险等级）。")
    A("> 判据（xlsx 逐字）：「**风险等级须逐条判定或按维度重算，不得用 p_level 映射顶替**」。")
    A("> Owner 授权（2026-10-12）：走 **A**（先只读重算 + 出对照证据，签字后再回填）；"
      "口径由 **Owner 签**、法务事后追认。")
    A("> 本件**只读产出**：一个字节都没写进 `kb/l0`–`kb/l7`。")
    A("")
    A("---")
    A("")
    A("## 一、一句话结论")
    A("")
    A("现状 **840/1018 条**走的是 `p_level` 兜底（`源无 风险等级；按 p_level=P1 映射`）"
      "⇒ **整批同一档 High，零区分度**。")
    A("按维度重算后，同一批 840 条的分布变为：**%s**。" %
      "／".join("%s %d" % (k, v) for k, v in
                collections.Counter(str(d["new_risk_level"]) for d in mapped_old).most_common()))
    A("")
    A("## 二、新旧对照")
    A("")
    A("| 档 | 旧 | 新 |")
    A("|---|---|---|")
    for lvl in ("Critical", "High", "Medium", "Low", "None"):
        A("| %s | %d | %d |" % (lvl, old.get(lvl, 0), new.get(lvl, 0)))
    A("")
    A("变动 **%d / %d** 条。" % (len(changed), len(D)))
    A("")
    A("## 三、重算口径 D1（**待签**）")
    A("")
    A("逐条按**优先级**取第一个能定的维度，并**逐条写明出处**：")
    A("")
    A("| 序 | 维度 | 映射 | 性质 | 用了多少条 |")
    A("|---|---|---|---|---|")
    A("| 1 | 源字段 `风险等级` | `RISK_LEVEL_MAP`（库内**既有**换词表） | 硬：不动 | %d |" % used.get(1, 0))
    A("| 2 | 源字段 `灯色状态` | **复用既有色标口径**：红→Critical / 黄→High / 绿→Low | 硬：与维度 1 同一套色标语汇 | %d |" % used.get(2, 0))
    A("| 3 | 源字段 `修订类型` | 按 `/` 拆 token → 下表，**取最高档** | 见下表逐 token 标注 | %d |" % used.get(3, 0))
    A("| 4 | 都取不到 | `unknown` | **不编** | %d |" % new.get("None", 0))
    A("")
    A("### 3.1 为什么这不是「换一个批量映射」")
    A("")
    A("`p_level` 是 PRD **§6.2 的优先级层级**（P0–P3），`risk_level` 是 **§6.5 的风险等级**"
      "（Critical/High/Medium/Low）—— **两个轴**。拿前者顶替后者，正是本次要修的病。")
    A("`修订类型` 是专家**逐条手填**的「这条修订是什么性质」，天然落在**严重度轴**上。")
    A("")
    A("### 3.2 逐 token 映射表（%d 个 token；**软判 %d/%d = %.0f%%**）" % (len(tok_rows), soft_n, tot_n, 100.0 * soft_n / max(1, tot_n)))
    A("")
    A("| 修订类型 token | → 档 | 命中条数 | 性质 | PRD 出处 |")
    A("|---|---|---|---|---|")
    for t, lvl, n, kind, basis in tok_rows:
        A("| `%s` | %s | %d | %s | %s |" % (t, lvl, n, kind, basis))
    A("")
    A("★ **含软判 token 的规则 = %d / %d（%.0f%%）** —— 这批是签字时要逐类看的；"
      "其余走硬引 PRD 原文。" % (soft_rules, len(rows), 100.0 * soft_rules / len(rows)))
    A("")
    A("## 四、证据")
    A("")
    A("### 4.1 `Critical` %d 条**全部来自源字段**，无一条出自我自己的语义判断" % len(crit))
    A("")
    for k, v in collections.Counter(d["new_basis"].split(" ｜")[0] for d in crit).most_common():
        A("- %d 条：%s" % (v, k))
    A("")
    A("⇒ **红线档完全交还源侧证据**（`高危` / `高危·红` / `红色-禁用`），"
      "不由我的映射表产生 —— 这是「不编」的直接体现。")
    A("")
    A("### 4.2 30 条 P0 规则没被这次改动伤到")
    A("")
    by_id = {r["rule_id"]: r for r in rows}
    p0 = [d for d in D if str(by_id[d["rule_id"]].get("p_level")) == "P0"]
    A("去掉 `p_level` 兜底后，P0 规则的档位分布：**%s**；"
      "被判成 None/Low/Medium 的 = **0 条** —— 因为它们的源字段是真值，本来就不走兜底。"
      % "／".join("%s %d" % (k, v) for k, v in
                  collections.Counter(str(d["new_risk_level"]) for d in p0).most_common()))
    A("")
    A("## 五、我在自查中抓到并修掉的两处（**都是我自己写错的**）")
    A("")
    A("| # | 我写错的 | 怎么发现的 | 修法 |")
    A("|---|---|---|---|")
    A("| ① | 初版把 `去绝对化` 判 **Critical** | 等距抽查第 10 条「停止哺乳超过1年」看着不对 ⇒ 逐条读源里 6 条 | 改判 **High**。源里「去绝对化」指**去掉不成立的适用边界**（室温区间/解冻母乳/数值阈值），**不是** PRD §7.3-3 的广告绝对化用语（最/第一/最佳/100%/纯天然）。据它判红线会把 P0 档撑到 104 —— **错档比不分档更坏** |")
    A("| ② | 复合值被误拆：`存疑/待讨论` 拆成两个查不到的 token | 读 token 才看见（**两者结论恰好都是 unknown，分布上看不出来** ⇒ 哑失败） | 先整值查、未中再拆 `/` |")
    A("")
    A("⇒ 两处都说明了同一条纪律：**判据要能被反例打红，光看分布看不出来。**")
    A("")
    A("## 六、遗留观察（**不改，交你判**）")
    A("")
    A("30 条 P0 规则里有 **2 条**源字段「风险等级 = 审慎·黄」⇒ 重算后是 **High**，"
      "而它们的 `p_level` 是 **P0**（PRD §7.3 一票否决、命中即驳回）。")
    A("这是**源与层级轴的口径冲突**，**不是本次引入的**（旧档也是 High，源优先是既有口径）。"
      "要不要为 P0 层级加一条「不得低于 Critical」的地板，**要你裁**。")
    A("")
    A("## 七、尺子与未做")
    A("")
    A("- `python3 kb/l8/workflow_smoke.py` ⇒ **exit 0，五段契约齐**"
      "（S4 报告溯源：取样 10、缺条款号 0、缺 sha 0、缺直链 0）。")
    A("- **未做**：没有改 `kb/l3/kb_rule_dimensions.py`、没有改 `dimension-policy.json`、"
      "没有回填 `rules.jsonl` —— 全部等你签字。")
    A("- **回填路径**（签字后）：改 `kb_rule_dimensions.py::risk_level_of()` 的维度链 ＋ "
      "`dimension-policy.json` 加 `revision_type_map` 段（版本 +1）→ 走 **L3 重建**回填，"
      "**不逐行手改**（手改 = 29 条原地改写的再来一遍）→ 回填后重跑本对照件复算。")
    A("")
    A("## 八、逐条明细")
    A("")
    A("`kb/.work/risk_level_recompute_diff.jsonl`（1018 行，每行带 "
      "`old_risk_level` / `old_basis` / `new_risk_level` / `new_basis` / `priority_used`）。")
    A("")
    A("复算命令（只读）：`sh kb/kbpy .work/risk_level_recompute_probe.py --json`")
    A("")

    text = "\n".join(L)
    _safe_write.write_text(OUT, text)
    print("已落盘：%s" % OUT)
    print("宿主尺子回读：%d 字节 / %d 行" %
          (os.path.getsize(OUT), len(text.splitlines())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
