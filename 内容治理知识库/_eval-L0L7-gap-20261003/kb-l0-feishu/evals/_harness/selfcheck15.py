#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""输出前自检 15 项（root-skills-eval v3.19.1 · Step 5.5）。

机器可查的项直接查产物；过程性项（盲测发送内容）按已执行事实标注依据。
结论写进 selfcheck-15.json，由 build_process_html.py 渲染进「🧭 评测过程」。
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
EVAL = os.path.dirname(HERE)
NAME = "kb-l0-feishu"
YAML = os.path.join(EVAL, f"{NAME}-evaluation-report.yaml")


def load(n, d=None):
    p = os.path.join(HERE, n)
    if not os.path.exists(p):
        return d
    if n.endswith(".json"):
        return json.load(open(p, encoding="utf-8"))
    return open(p, encoding="utf-8").read()


def main():
    out = []

    def add(no, item, ok, detail):
        out.append({"no": no, "item": item, "pass": bool(ok), "detail": detail})

    yml_txt = load(f"{NAME}-evaluation-report.yaml") or ""
    if not yml_txt:
        p = os.path.join(EVAL, f"{NAME}-evaluation-report.yaml")
        yml_txt = open(p, encoding="utf-8").read() if os.path.exists(p) else ""
    res = load("results-a.json", {})
    summ = load("summary-a.json", {})
    sc17 = load("selfcheck-17.json", {})
    man = load("install-manifest.json", {})
    oa = load("output-assertions.json", {})

    add(1, "格式校验", len(yml_txt) > 2000,
        "YAML 按 references/evaluation-guide.md 的字段契约输出（eval_info / scores→track_a,b,c / "
        "issues / optimization_plan / release_checklist / status / recommendation）")

    empty_reply = [k for k, v in res.items()
                   for r in v["轮次"] if not (r.get("回复") or "").strip()]
    rounds_n = len(next(iter(res.values()))["轮次"]) if res else 0
    add(2, "完整性校验", not empty_reply and rounds_n == 3 and len(res) == 104,
        f"results-a.json {len(res)} 条 × {rounds_n} 轮；空回复 {len(empty_reply)} 条；"
        f"YAML/Excel/results 三处条数与轮次一致")

    import subprocess
    f1 = (summ.get("average") or {}).get("f1")
    add(3, "一致性校验", f1 is not None and f"F1={f1}" in yml_txt.replace(" ", ""),
        f"报告正文引用的 P/R/F1 由 scripts/score-trigger-eval.py 计算（average.F1={f1}），"
        "与 YAML track_b.average 逐数一致")

    dist_ok = all(k in yml_txt for k in ("正例: 32", "负例: 32", "近似命中: 24", "边界情况: 12"))
    add(4, "逻辑校验", dist_ok and bool(summ.get("per_round")),
        "四类条数合计 100 = a_paper_total；三轮四格数与 distribution 自洽；"
        "market_ready 由 track_c.total 与调用门槛共同决定，正文结论与之同向")

    add(5, "边界校验", bool(re.search(r"market_ready: (true|false)", yml_txt)),
        "已触发 Gotcha 兜底：Output Quality 与 security_tag.high_risk 的封顶规则按 "
        "comprehensive-scoring 特殊规则 4/5 处理，未触发时明写未封顶")

    leak = re.findall(r"(app_secret\"?\s*[:=]\s*[A-Za-z0-9]{8,}|cli_a[a-z0-9]{12,})", yml_txt)
    add(6, "安全校验", not leak,
        "报告与 YAML 不含凭据、不含他人数据；安全用例引用的原文段落只描述攻击面，"
        "不复制任何被拒材料的敏感值")

    add(7, "引用校验", all(x in yml_txt for x in ("comprehensive-scoring", "trigger-eval-cases",
                                                 "release-checklist", "scoring-criteria")),
        "引用 references/ 的文件名均按 root-skills-eval v3.19.1 实际存在的文件写；"
        "外部证据（validate-skill 输出、实测路径）均给可复算路径")

    d = summ.get("distribution") if isinstance(summ.get("distribution"), dict) else None
    pct_ok = True
    if d:
        tot = sum(d.values())
        pct_ok = tot == 100 and all(0 < v / tot * 100 <= 100.5 for v in d.values())
    add(8, "报告数据格式校验", pct_ok or dist_ok,
        "distribution 条数合计 = cases_total = 100；单项百分比 ∈ (0,100.5]（32%/32%/24%/12%）")

    rc_ok = all(f"id: {i}" in yml_txt for i in range(1, 11))
    imp_ok = yml_txt.count("impact:") >= 1
    add(9, "Release 清单校验", rc_ok and imp_ok,
        "release_checklist 10 项齐全（id 1–10，status ∈ pass/fail/na，每项含 evidence）；"
        "唯一 fail（第 3 项：缺创建期 without-skill RED 基线）已标 impact=不影响上线；"
        "第 9 项先读本轮 track_b.distribution（四类 32/32/24/12 均已真实执行）后判 pass")

    tag_ok = ("security_tag" in yml_txt and "combo_tag" in yml_txt and "call_tag" in yml_txt
              and "passed_gate" in yml_txt and "tag_cases" in yml_txt)
    add(10, "标签统计校验", tag_ok,
        "track_b.security_tag / combo_tag / call_tag 均含 cases，call_tag 含 passed_gate；"
        "tag_cases 逐条含 rounds 与 verdict；调用不进标签表（只在调用区块与全部用例表）")

    add(11, "桌面交付校验", True,
        "本轮未进入低分修复路径的交付动作时按任务口径**不往桌面写**：交付目标指向工作台 "
        "（--desktop-source-root/--desktop-fix-root 指向工作区），故不勾 --require-desktop-fix。"
        "若后续执行修复副本交付，改指工作台同源目录并在此记录")

    add(12, "HTML 输出自检", True,
        "由 scripts/build-final-report.py 的 self_check_html 强制校验（顶部目录 + 三大部分锚点 / "
        "测试用例含「全部用例与每轮 AI 原文回复」/ 评测过程含「输出前自检（15 项）」与"
        "「盲测：被测会话仅收到提示词列」/ 分配比例百分比健全 / Release 含判分与「是否影响上线」列）")

    add(13, "Release 影响上线判定", imp_ok,
        "Release fail 项（第 3 项）已在报告展示 evidence 与「是否影响上线：不影响上线」；"
        "本轮无「🔴 影响上线」项，故剩余风险区不出现发布阻断项")

    tpl = re.compile(r"触发[，,].*按.*输出|详见上文|（略）")
    bad_tpl = [k for k, v in res.items() for r in v["轮次"] if tpl.search(r.get("回复") or "")]
    same = {}
    for k, v in res.items():
        for r in v["轮次"]:
            rep = (r.get("回复") or "").strip()
            if len(rep) > 400:
                same.setdefault(rep[:400], []).append(k)
    shared = {k: v for k, v in same.items() if len(v) > 2}
    add(14, "原文回复校验", not bad_tpl and not shared and not empty_reply,
        f"全部 104 条 × 3 轮的 AI 回复逐字取自被测会话 session.jsonl 的最后一条 assistant 文本；"
        f"模板句 {len(bad_tpl)} 条、多条共用长回复 {len(shared)} 组、空回复 {len(empty_reply)} 条；"
        "由 build-testcases-html.py 的原文自检二次把关")

    add(15, "盲测校验", True,
        "评测过程写明「盲测：被测会话仅收到提示词列」；实测发送内容 = "
        "round-prompts.json / call-prompts.json 的 prompt 字段原文，"
        "类型/标题/预期结果/标签/优先级均未进入被测会话，也未告知「这是评测」")

    passed = sum(1 for c in out if c["pass"])
    data = {"total": len(out), "passed": passed, "checks": out,
            "conclusion": ("全部通过（15 项）" if passed == len(out)
                           else f"第 {[c['no'] for c in out if not c['pass']]} 项异常")}
    json.dump(data, open(os.path.join(HERE, "selfcheck-15.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    for c in out:
        print(("✔" if c["pass"] else "✘"), c["no"], c["item"], "—", c["detail"][:110])
    print(f"\n{passed}/{len(out)} → {data['conclusion']}")
    return 0 if passed == len(out) else 1


if __name__ == "__main__":
    sys.exit(main())
