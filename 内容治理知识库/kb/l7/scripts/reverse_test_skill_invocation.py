#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""反测：E1「记账即复述」判据（批次18 · 第1块）。

## 要证的两件事（互相咬合，缺一不可）

  A. **证它认观测值**：`skills` 与声明逐项相同，但 `skill_evidence=layer_stamps_observed`
     且**层落章确实存在**（真观测） ⇒ E1 **应为 0**。
  B. **证它没有退化成「换个标签就绿」**：同样的 `skills`、同样的层落章，
     只把 `skill_evidence` 换成一个**不在白名单里的名字** ⇒ E1 **必须判红**。
  C. **漏调一层反测**（用户点名要的）：`skills` 照旧声明齐全，但**少写一层的落章**
     ⇒ E1 **必须判红**（观测不到 ⇒ 不能算调过）。

## 做法

夹具根用 `KB_GATE_KB` 指过去（该闸门自己的环境变量口子），**不碰真实库**。
夹具里**复制真实 `layers.yaml`**，这样「声明侧」是真表，不是我编的。

用法：kb/kbpy l7/scripts/reverse_test_skill_invocation.py
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
KB = HERE.parents[1]                       # …/kb
ROOT = KB.parent
REAL_LAYERS = KB / "l7/registry/layers.yaml"


def _declared():
    sys.path.insert(0, str(HERE))
    import skill_invocation_audit as sia
    layers = sia._yaml(REAL_LAYERS)["layers"]
    return sia.declared(layers)


def build(t: Path, *, observed: bool, evidence: str, stamps_for: list, declared: list):
    """造夹具：layers.yaml（真表）+ 一条 run 记账 + 若干层落章。

    ★ `declared` = 本跑**声称**走到哪几层（写进 `extra.layers`）；
      `stamps_for` = **实际**写了落章的层。
      「漏调一层」= `declared` 有它、`stamps_for` 没有它 —— 这正是要抓的形态。
    """
    (t / "l7/registry").mkdir(parents=True, exist_ok=True)
    (t / "l7/runs").mkdir(parents=True, exist_ok=True)
    shutil.copy2(REAL_LAYERS, t / "l7/registry/layers.yaml")

    dec = _declared()
    layers = sorted(set(declared))
    # 声明侧：kb-pipeline + 本跑各层声明（去重保序）
    skills = ["kb-pipeline"]
    for lid in layers:
        for s in (dec.get(lid) or []):
            if s not in skills:
                skills.append(s)

    rid = "20990101-0000"                    # 假 RUN，绝不会与真账撞
    rec = {
        "run_id": rid,
        "at": "2099-01-01T00:00:00",
        "source": "pipeline_sync",
        "trigger": "反测夹具",
        "skills": skills,
        "commands": [],
        "products": [],
        "verdict": "反测",
        "human_involved": True,
        "extra": {
            "via_skill": True,
            "skill_evidence": evidence,
            "layers": layers,
            "layer_skills": [s for s in skills if s != "kb-pipeline"],
            "declared_layer_skills": {lid: (dec.get(lid) or []) for lid in layers},
            "layer_skills_uniq": [s for s in skills if s != "kb-pipeline"],
            "observed_skills": ([s for s in skills if s != "kb-pipeline"] if observed else []),
            "skill_evidence_note": "反测夹具：观测=%s" % observed,
        },
    }
    (t / "l7/runs" / (rid + ".json")).write_text(
        json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")

    # 层落章：**只有 stamps_for 里的层**才有（漏调的层刻意不写）
    for lid in sorted(set(stamps_for)):
        d = t / lid.lower() / "runs"
        d.mkdir(parents=True, exist_ok=True)
        for s in (dec.get(lid) or []):
            (d / (rid + ".json")).write_text(json.dumps(
                {"run_id": rid, "layer": lid, "skill": s,
                 "skill_source": "反测夹具", "applied": True, "dry_run": False},
                ensure_ascii=False), encoding="utf-8")
    return rid


def run_audit(t: Path, rid: str):
    env = dict(os.environ, KB_GATE_KB=str(t))
    p = subprocess.run([str(KB / "kbpy"), "l7/scripts/skill_invocation_audit.py",
                        "--run", rid, "--json"],
                       capture_output=True, text=True, cwd=str(ROOT), env=env)
    raw = p.stdout + p.stderr
    try:
        j = json.loads(p.stdout[p.stdout.find("{"):p.stdout.rfind("}") + 1])
        return j, raw
    except Exception:                                     # noqa: BLE001
        return None, raw


def main():
    dec = _declared()
    # 取两层做被测层（真表里挑两个有 skill 声明的）
    lids = [lid for lid, ss in dec.items() if ss][:2]
    print("=" * 74)
    print("反测：E1 判据（夹具在 /tmp，KB_GATE_KB 指过去，**不碰真实库**）")
    print("被测层（取自真 layers.yaml）：%s" % "、".join(lids))
    print("=" * 74)

    cases = [
        ("A 观测值 + 层落章齐（期望 E1=0）",
         dict(observed=True, evidence="layer_stamps_observed", stamps_for=lids, declared=lids), 0),
        ("B 同 skills 但标签不在白名单（期望 E1>0）",
         dict(observed=False, evidence="observed", stamps_for=lids, declared=lids), 1),
        ("C 漏调一层：声明有它、落章没有（期望 E1>0）",
         dict(observed=True, evidence="layer_stamps_observed",
              stamps_for=lids[:1], declared=lids), 1),
    ]
    allok = True
    for name, kw, want_e1 in cases:
        with tempfile.TemporaryDirectory(prefix="kb-e1-rt-") as td:
            t = Path(td)
            rid = build(t, **kw)
            j, raw = run_audit(t, rid)
            if j is None:
                print("  %-46s **跑不出机读结论** ✗" % name)
                print(raw[-500:])
                allok = False
                continue
            n = j.get("E1_n")
            ok = (n == want_e1) if want_e1 == 0 else (n and n > 0)
            allok &= bool(ok)
            print("  %-46s E1_n=%s（期望 %s）%s"
                  % (name, n, "0" if want_e1 == 0 else ">0", "✅" if ok else "❌"))
            for row in (j.get("E1_registry_echo") or [])[:1]:
                print("        理由：%s" % str(row[-1])[:130])
    print()
    print("E1 反测：%s" % ("**全部通过 ✅**" if allok else "**有失败 ❌**"))
    if not allok:
        print("⚠️ B 不红 = 判据退化成「换个标签就绿」；C 不红 = 观测不到也算调过。都要修。")
    return 0 if allok else 1


if __name__ == "__main__":
    sys.exit(main())
