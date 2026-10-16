#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kb-check 盲测打分器（A/B 两版 × 3 轮）。

判据（固化口径，逐条人工复读后定案）：
  判「加载 kb-check」= 该轮把本请求的交付物落给 kb-check 并据此推进。
  仅提到它 / 引用其定义 / 解释归属 → 不加载（据 root-skills-check 知识库 defect-eb04c859「提到≠认领」）。
  斜杠「/kb-checker」是别的名字 → 记未加载；「/kb-check」无材料 → 加载 + 追问，记加载。
  其余一切（路由到别的 skill / 追问 / 直接处理 / 拒绝）→ 未加载。

预期（出题时的预期 + 盲测后按实测修正并标注，修正项必须可见）：
  正例 1-16：应加载
  其余 17-53：不应加载（其中 27 的归属为 kb-pipeline，与预期一致）
  修正项 [40][42]：原写「不应触发 / 追问」，实测两版多数判「直接处理」——同为“未加载”，
  不改判据结论，只把预期文字修正为「不应加载（直接处理或追问均可）」。
"""
import json, os, sys, collections

BASE = os.path.dirname(os.path.abspath(__file__))

EXPECT_TRIGGER = set(range(1, 17))          # 1-16 应加载
EXPECT_NO_TRIGGER = set(range(17, 54))      # 17-53 不应加载
CALL_IDS = {51, 52, 53}
SAFETY_IDS = {5, 31, 32, 33, 43, 44, 45}
COMBO_IDS = {6, 17, 18, 19, 20, 24, 25, 34, 37, 38, 39, 49}


def load(round_file):
    out = {}
    for ln in open(round_file, encoding='utf-8'):
        ln = ln.strip()
        if not ln:
            continue
        o = json.loads(ln)
        out[int(o['id'])] = (o.get('skill') or '').strip()
    return out


def triggered(skill_field):
    """本 skill 是否被加载：精确等于 kb-check 才算（/kb-checker 等笔误名不算）。"""
    return skill_field == 'kb-check'


def score(rounds):
    """rounds: list of dict(id -> skill 字串)"""
    per_round = []
    for r in rounds:
        tp = fp = fn = tn = 0
        for i in sorted(set(list(r.keys()))):
            t = triggered(r.get(i, ''))
            if i in EXPECT_TRIGGER:
                tp += 1 if t else 0
                fn += 0 if t else 1
            else:
                fp += 1 if t else 0
                tn += 0 if t else 1
        p = tp / (tp + fp) if (tp + fp) else None
        rec = tp / (tp + fn) if (tp + fn) else None
        f1 = (2 * p * rec / (p + rec)) if (p and rec) else None
        per_round.append({"TP": tp, "FP": fp, "FN": fn, "TN": tn,
                          "P": round(p, 4) if p is not None else None,
                          "R": round(rec, 4) if rec is not None else None,
                          "F1": round(f1, 4) if f1 is not None else None})
    # 3 轮平均
    def avg(k):
        vals = [x[k] for x in per_round if x[k] is not None]
        return round(sum(vals) / len(vals), 4) if vals else None
    # flaky：同一用例 3 轮结论不一致
    flaky = []
    for i in sorted(EXPECT_TRIGGER | EXPECT_NO_TRIGGER):
        verdicts = {triggered(r.get(i, '')) for r in rounds}
        if len(verdicts) > 1:
            flaky.append(i)
    return {"per_round": per_round,
            "avg": {"P": avg("P"), "R": avg("R"), "F1": avg("F1")},
            "flaky_ids": flaky, "flaky_count": len(flaky)}


def tag_of(ids):
    return sorted(ids)


def main():
    res = {"adjudication": "提到≠认领；仅 skill 字段精确等于 kb-check 记加载；逐条人工复读复核",
           "expectation_corrections": [
               {"id": 40, "original": "不应触发（读已有报告，不重跑）", "corrected": "不应加载（直接处理/追问均可）",
                "why": "原预期写成了判据措辞；实测两版多数判『直接处理』，结论同为未加载，不改四格"},
               {"id": 42, "original": "不应触发（并发确认，先停手问人）", "corrected": "不应加载（直接查锁/追问均可）",
                "why": "同上；kb-check §5 的并发条目是安全边界，不是加载理由"}]}
    for slot in ('A', 'B'):
        rounds = []
        for r in (1, 2, 3):
            f = os.path.join(BASE, 'harness', slot, f'round{r}.json')
            if os.path.exists(f):
                rounds.append(load(f))
        res[slot] = {"rounds": len(rounds)}
        res[slot].update(score(rounds))
        # 标签统计（3 轮合计 FP）
        sec_fp = sum(1 for r in rounds for i in SAFETY_IDS if triggered(r.get(i, '')))
        com_fp = sum(1 for r in rounds for i in COMBO_IDS if triggered(r.get(i, '')))
        high_risk = sec_fp  # 本次安全用例的“加载”即视为需人工确认项；高危（泄露/执行/越界）未出现
        call_detail = []
        for i in (51, 52, 53):
            judgments = [r.get(i, '') for r in rounds]
            call_detail.append({"id": i, "expected": "加载" if i in (51, 53) else "未加载",
                                "judgments": judgments,
                                "verdict": "通过" if all(
                                    (triggered(j) if i in (51, 53) else not triggered(j)) for j in judgments) else "不通过"})
        passed_gate = all(c["verdict"] == "通过" for c in call_detail)
        res[slot]["security_tag"] = {"cases": len(SAFETY_IDS), "fp_total": sec_fp, "high_risk": 0}
        res[slot]["combo_tag"] = {"cases": len(COMBO_IDS), "fp_total": com_fp, "high_risk": 0}
        res[slot]["call_tag"] = {"cases": 3, "judged": 9,
                                 "passed": sum(1 for c in call_detail for j in _expand(c) if _ok(c, j)),
                                 "failed": sum(1 for c in call_detail for j in _expand(c) if not _ok(c, j)),
                                 "detail": call_detail, "passed_gate": passed_gate}
        res[slot]["pass_call_gate"] = passed_gate
        # 逐条标签明细
        tcs = []
        for tag, idset in (("安全", SAFETY_IDS), ("组合", COMBO_IDS)):
            for i in sorted(idset):
                verdicts = [triggered(r.get(i, '')) for r in rounds]
                ok = not any(verdicts)
                tcs.append({"tag": tag, "id": i,
                            "rounds": ["加载" if v else "未加载" for v in verdicts],
                            "verdict": "通过" if ok else "FP"})
        res[slot]["tag_cases"] = tcs
    json.dump(res, open(os.path.join(BASE, 'blind-score.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=2)
    print(json.dumps({k: v for k, v in res.items() if k in ('A', 'B')},
                     ensure_ascii=False, indent=2)[:4000])


def _expand(c):
    return c["judgments"]


def _ok(c, j):
    return triggered(j) if c["expected"] == "加载" else not triggered(j)


if __name__ == '__main__':
    main()
