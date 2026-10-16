# -*- coding: utf-8 -*-
"""生成评测 YAML 报告。源版本与修复版本共用本生成器，参数化分项分与结论。"""
import json, os, sys
import yaml

OUT = os.path.dirname(os.path.abspath(__file__))
SKILL = "kb-ingest-extractor"

# ---- 轨道 A 静态六维（分项 0-100，权重 20/25/30/15/10/5，总分 = Σ(分项×权重)/105）----
TRACK_A_DIMS = {
    "schema_compliance": (85, "name=kb-ingest-extractor 与目录一致（ASCII kebab-case，5/5）；description 含 what+when+触发词（5/5）、无 XML 标签且第三人称（4/4）；complexity: standard 已声明且有效（3/3）；未声明 compatibility 核心联盟（0/3）。合计 17/20。"),
    "frontmatter_quality": (92, "description 471 字符落在 200-1024（5/5）；触发短语 3+ 种且具体：当用户说「抽取单元 / 素材转条目 / L1 抽取 / L2 切分 / 补切 / 重切 / 切分规则 / 单元对账」时使用（8/8）；触发词覆盖同义词+变体+中英（7/7）；防过度触发写了不适用场景，但实测 3 轮 FP 8/8/11 条，边界声明未阻止近邻误触发（3/5）。合计 23/25。"),
    "body_quality": (76.7, "全篇祈使语态（6/6）；核心工作流给了 L1/L2 引擎命令与预演/落盘两档，但无编号步骤，L2 缺口口径靠一段说明（6/8）；适用性只在 §5 用表格给上下游关系，正文无 When to Use / When Not to Use 章节（4/6）；无独立 Error Handling 章节，错误分支散在红线里（2/5）；正文 1721 字符远低于 standard 上限（5/5）。合计 23/30。"),
    "methodology_audit": (100, "同质化 0 命中：内容全部绑在本库特有对象上（幂等键三元组、units.jsonl append-only、unit_count 三种口径实测 1520/1624/1320、l1_gate/l2_gate 判据）；壁垒 2+ 项：私有数据（本库台账/闸门/实测计数）+ 失败案例（口径歧义不猜公式、信封态、删行毁出处）。合计 15/15。"),
    "quality_gate": (90, "单一职责（素材→知识单元，合并在 L3）2/2；差异化 2/2；触发准确——有明确触发词与 When to Use，但实测 P=0.627 未达门槛，扣 1（1/2）；可测试（§4 验收 A1–A4 可执行）2/2；可打包（单 SKILL.md 无冗余文件）2/2。合计 9/10。"),
    "directory_structure": (40, "SKILL.md 存在 2/2；无 references/、examples/、scripts/（各 0）。合计 2/5。"),
}
TRACK_A_TOTAL = round(sum(s * w for s, w in
                          zip([v[0] for v in TRACK_A_DIMS.values()], [20, 25, 30, 15, 10, 5])) / 105, 1)

# ---- 轨道 B ----
DISTRIBUTION = {"正例": 16, "负例": 16, "近似命中": 12, "边界情况": 6}


def track_b_from(summary_path, cases_total=50, combo_cases=19, pass_gate=True):
    sm = json.load(open(summary_path, encoding="utf-8"))
    rounds = []
    for i, r in enumerate(sm["per_round"], 1):
        rounds.append({"round": i, "TP": r["TP"], "FP": r["FP"], "FN": r["FN"], "TN": r["TN"],
                       "precision": r["precision"], "recall": r["recall"], "f1": r["f1"]})
    flaky = [{"id": i, "title": f"用例 {i}", "conclusions": []} for i in sm.get("flaky", [])]
    sec = dict(sm["security_tag"]); sec.setdefault("high_risk", 0)
    combo = dict(sm["combo_tag"])
    return {
        "cases_total": cases_total, "cases_main": cases_total, "cases_combo": combo_cases,
        "distribution": DISTRIBUTION,
        "rounds": rounds,
        "average": sm["average"],
        "flaky": flaky,
        "pass_enterprise_gate": bool(sm["average"]["precision"] >= 0.85 and sm["average"]["recall"] >= 0.85
                                     and sm["average"]["f1"] >= 0.90),
        "pass_call_gate": bool(sm.get("pass_call_gate")),
        "security_tag": sec, "combo_tag": combo, "call_tag": sm["call_tag"],
        "tag_cases": sm["tag_cases"],
    }


def build(version, tag_a_total, track_a_dims, track_b, track_c_dims, track_c_total, grade,
          market_ready, issues, release_checklist, optimization_plan, status, recommendation, extra=None):
    doc = {
        "eval_info": {
            "skill_name": SKILL,
            "version": version,
            "skill_path": "kb/l7/skills/kb-ingest-extractor/",
            "install_path": "~/.dsh/skills/kb-ingest-extractor/",
            "eval_date": "2026-09-30",
            "evaluator": "root-skills-eval v3.19.1（一键全自主模式）",
            "complexity": "standard",
            "cases_total": 50,
            "rounds": 3,
        },
        "track_a": {"total": tag_a_total,
                    "dimensions": {k: {"score": v[0], "weight": w, "basis": v[1]}
                                   for (k, v), w in zip(track_a_dims.items(), [20, 25, 30, 15, 10, 5])}},
        "track_b": track_b,
        "track_c": {"total": track_c_total, "grade": grade, "market_ready": market_ready,
                    "dimensions": {k: v for k, v in track_c_dims.items()}},
        "issues": issues,
        "release_checklist": release_checklist,
        "optimization_plan": optimization_plan,
        "status": status,
        "recommendation": recommendation,
    }
    if extra:
        doc.update(extra)
    return doc


if __name__ == "__main__":
    print("TRACK_A_TOTAL =", TRACK_A_TOTAL)
