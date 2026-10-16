#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""regression_run.py —— 回归集跑手（三态与条目**同源**读法）。

════════════════════════════════════════════════════════════════════════
★ 为什么要有它（2026-10-12 诊断，逐条实测）
════════════════════════════════════════════════════════════════════════
第一版跑手是 `kb/.work/run_regression_set.py`（2026-10-12 10:45 临时补的）。
它把两样东西**读成了两个来源**：

    三态 ←  `out["decision"]["decision"]`   （= `review_engine.decide()` 的产物）
    条目 ←  `--findings-out` 缓存里的 `ev["findings"]`（= `review.py` 的产物）

而 `decide()` 的输入是
    `payload["risk_items"] = [_to_risk_item(f) for f in findings]` **＋ `scan_text(...)`**
（`with_kb_evidence.py:1199`，**无条件**并进来），并且 `decide()` 自己还有两条结构性差异：

  · **P3 只出建议、不进结论**（PRD §6.3 执行规则3）⇒ PASS 可以正当地带着 P3 条目；
  · **覆盖缺口支路**（`with_kb_evidence.py:1089`）自造一条 `risk_items`
    （带 `coverage_gap: True`）且 `issue_count=0`、`findings=0`。

⇒ 于是一批**完全正常的设计行为**，在旧读法下长得像「三态↔发现不一致」。
   2026-10-12 实测：初判为「矛盾」的 5 条，**5/5 都是读法造成的假象**
   （2 条 P3 建议、3 条覆盖缺口）。**病灶在读法，不在引擎。**

⇒ 本跑手一律**从结论对象取值**（`decision.decision` ＋ `decision.risk_items`），
  把证据侧 `findings` 降为**对照**，并把两者的差分成两类记下来：

| 字段 | 含义 | 性质 |
|---|---|---|
| `orphan_p3_n` | 证据里有、结论没采纳，且 `p_level=P3` | **合法**（§6.3 执行规则3） |
| `orphan_non_p3` | 证据里有、结论没采纳，且**不是 P3** | **异常**：有依据却不进结论 |
| `unbacked_n` | 结论里有、证据侧查无此条 | **必须看得见**：结论由别的来源驱动（如种子规则扫描器） |

════════════════════════════════════════════════════════════════════════
用法
════════════════════════════════════════════════════════════════════════
    python3 kb/l8/regression_run.py --out kb/.work/regression-<tag>.jsonl
    python3 kb/l8/regression_run.py --selftest          # 离线：读法判据的反向对照
    python3 kb/l8/regression_run.py --rebaseline --from <jsonl>   # 重采基线

★ 写盘口径：本文件是 `.py`（**不中信封**），python 直写安全（库规实测：只有 `.md`/`.sh` 中招）。
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

KB = Path(__file__).resolve().parent.parent          # …/kb
ROOT = KB.parent
SET = KB / "l7" / "registry" / "regression-set.yaml"
ENGINE = KB / "l7" / "review-engine" / "core" / "with_kb_evidence.py"
BASELINE = KB / "l7" / "registry" / "regression-baseline.json"
CACHE = KB / ".work" / "_regression_findings_cache.json"

# 跑批默认**不写评审台账**（`KB_RUN_RECORD_SKIP=1`）；`--record-runs` 显式关掉隔离。
# 口径与实测证据见 `kb/l7/scripts/run_record.py::record()` 与 `_child_env()`。
RECORD_RUNS = False


# ── 同源读法：判据本体（regression_gate.py 也 import 它，**一处口径**）──────────
def _is_candidate(item: dict) -> bool:
    """**非权威候选**的口径 —— 唯一真源是 `review_engine.is_candidate()`，本处只做转发。

    ★ 为什么不在这里写一行 `item.get("authoritative") is False`：那样就有了**第二份口径**，
      而这份口径刚刚才因为「声明存在、没人读」栽过一次（见 `review_engine.candidate_note`）。
      转发失败（引擎 import 不进来）时**不猜**：返回 False 并让调用方把 `candidate_n` 记成 None。
    """
    try:
        sys.path.insert(0, os.path.join(ROOT, "kb/l7/review-engine/core"))
        import review_engine as _re
        return bool(_re.is_candidate(item))
    except Exception:
        return False


def same_source_report(items, ev_findings):
    """把「结论条目」与「证据 findings」的差分成三类。**缺的不编**，一律如实计数。"""
    ik = [str(i.get("risk_id")) for i in (items or [])]
    ek = [str(f.get("rule_id") or f.get("case_id")) for f in (ev_findings or [])]
    ik_set, ek_set = set(ik), set(ek)
    orphan = [f for f in (ev_findings or [])
              if str(f.get("rule_id") or f.get("case_id")) not in ik_set]
    unbacked = [i for i in (items or []) if str(i.get("risk_id")) not in ek_set]
    orphan_p3 = [f for f in orphan if str(f.get("p_level") or "").upper() == "P3"]
    orphan_non_p3 = [f for f in orphan if f not in orphan_p3]
    try:
        sys.path.insert(0, os.path.join(ROOT, "kb/l7/review-engine/core"))
        import review_engine as _re2
        _cand = [i for i in (items or []) if _re2.is_candidate(i)]
    except Exception:
        _cand = None                      # 引擎读不进来 ⇒ 记 None（未测），**不记 0**
    return {
        "items_n": len(items or []),
        "candidate_n": (len(_cand) if _cand is not None else None),
        "authoritative_n": (len(items or []) - len(_cand) if _cand is not None else None),
        "evidence_n": len(ev_findings or []),
        "orphan_p3_n": len(orphan_p3),
        "orphan_non_p3": [
            {"rule_id": f.get("rule_id"), "p_level": f.get("p_level"),
             "severity": f.get("severity"), "category": f.get("category")}
            for f in orphan_non_p3],
        "unbacked_n": len(unbacked),
        "unbacked_ids": [i.get("risk_id") for i in unbacked][:8],
        "unbacked_sources": sorted({str(i.get("source") or "?") for i in unbacked}),
    }


def _decode(raw: str):
    d, dec = None, json.JSONDecoder()
    for cand in (raw,) + tuple(raw[k:] for k in range(len(raw)) if raw[k] == "{"):
        try:
            d, _ = dec.raw_decode(cand.lstrip())
            break
        except Exception:                                     # noqa: BLE001
            continue
    return d


def _child_env() -> dict:
    """跑批用的子进程环境：**默认把「只读测量不许进评审台账」打开**。

    ★ 为什么（2026-10-12 实测）：引擎每跑一单都会 `run_record.record(source="review_machine")`，
      而本跑手**每跑一次 = 100 单** ⇒ 跑一次回归就往 `kb/l7/runs/index.jsonl` 灌 100 行。
      实测该台账 `review_machine` 1102 行里 **316 行**的 trigger 与回归集素材**逐字相同**
      （今天 268 行）—— 那不是新评审单，是同一条素材被重跑。
      而 xlsx 的 G 列与多份交付件里的「**累计评审单数 562/580**」正是从这份台账算的
      ⇒ **度量被测量行为本身抬高。**
      开关与口径写在 `kb/l7/scripts/run_record.py::record()`；`--record-runs` 可显式关掉隔离。
    """
    env = dict(os.environ)
    if RECORD_RUNS:
        env.pop("KB_RUN_RECORD_SKIP", None)
    else:
        env["KB_RUN_RECORD_SKIP"] = "1"
    return env


def run_case(case: dict, findings_out: Path | None = None) -> dict:
    """跑一条 case。`findings_out` 不传时**每条 case 用自己的临时缓存**。

    ★★ 2026-10-12 修（这一个是**本跑手自己的缺陷**，实测踩到）：
      原先默认写/读**同一份** `kb/.work/_regression_findings_cache.json`，且读的时候是
      `json.loads(...)` **裸读**、不验 `text_sha256`。后果：两个跑批同时跑时（实测 13:05–13:15
      另一会话的 `regression-SCOPE-BEFORE-20261012.jsonl` 与我的同时进行），
      缓存里躺着**另一条文案**的依据，而本跑手照单全收 ⇒ 100 条里 10 条报出
      `orphan_non_p3`/`unbacked` 的**假差异**（三态与条目数一个没错，只有证据侧被污染）。
      ⇒ 这是「把另一条文案的依据算到这条上」——与 `evidence_cache.read_cache()` 里
        那句注释警告**逐字同因**，而引擎早就防住了（它校验 sha），**是本跑手绕过了那把锁**。
    修法两层：
      ① **每条 case 一个临时缓存路径** ⇒ 并发跑批、同 RUN 内前后条目**都不可能互相踩**；
      ② 读的时候改走引擎的 `evidence_cache.read_cache()`（**同一把尺子**，带 `text_sha256` 校验）；
         校验不过 ⇒ 记 `evidence_probe="mismatch"`、证据侧计 **None（未测）**，
         **不许**拿别的文案的依据去算 orphan/unbacked。
    """
    t0 = time.time()
    _tmp = None
    if findings_out is None:
        _fd, _tmp = tempfile.mkstemp(prefix="_regr_findings_", suffix=".json", dir=str(KB / ".work"))
        os.close(_fd)
        os.unlink(_tmp)                      # 让引擎自己创建；我们只要一个**独占**路径
        cache = Path(_tmp)
    else:
        cache = findings_out
    cmd = [sys.executable, str(ENGINE), "--text", case["text"], "--json",
           "--no-publish-to-feishu",
           "--allow-no-layer-preflight", "--allow-no-decision-owner",
           "--findings-out", str(cache)]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=180,
                           cwd=str(ROOT), env=_child_env())
        out = _decode(r.stdout or "")
    except Exception as e:                                    # noqa: BLE001
        return {"case_id": case["case_id"], "expected": case.get("expected"),
                "got": None, "error": "%s: %s" % (type(e).__name__, e),
                "elapsed_s": round(time.time() - t0, 1), "layer": case.get("_layer")}

    # ★★ 同源：三态与条目都从**同一个 decision 对象**取（这是本跑手存在的理由）
    dec = (out or {}).get("decision") or {}
    state = dec.get("decision") or dec.get("state")
    items = dec.get("risk_items") or []
    dtr = dec.get("decision_trace") or {}
    cov_gap = any(bool(i.get("coverage_gap")) for i in items)

    # 证据侧（降为**对照**，不再是三态的依据）—— ★ 必须过 `text_sha256` 校验（见 run_case 的 docstring）
    ev_findings = []
    ev_probe = "unavailable"
    try:
        sys.path.insert(0, str(ROOT / "kb/l7/review-engine/core"))
        from evidence_cache import read_cache as _read_cache      # noqa: PLC0415
        _payload, _err = _read_cache(str(cache), case["text"])
        if _payload is not None:
            ev_findings = _payload.get("findings") or []
            ev_probe = "match"
        else:
            ev_probe = "rejected"        # 缓存不是这一条的 ⇒ 未测，**不是 0 条**
    except Exception as _e:                                       # noqa: BLE001
        ev_probe = "error:%s" % type(_e).__name__
    finally:
        if _tmp:
            try:
                os.unlink(_tmp)
            except OSError:
                pass

    rec = {
        "case_id": case["case_id"], "layer": case.get("_layer"),
        "expected": case.get("expected"),
        "got": state, "got_source": "decision.decision" if dec.get("decision") else "decision.state",
        "issue_count": dec.get("issue_count"),
        # ★ 2026-10-12：**PRD §5.4 的结构等式**（`issue_count` == 分类汇总合计）也记进每条，
        #   跑批时 100 条一起看 —— 它是我这一批按 PRD 修过的东西，得有人在真实数据上盯着。
        "category_total_n": sum((dec.get("issue_summary_by_category") or {}).values()),
        "prd54_ok": (dec.get("issue_count") == sum(
            (dec.get("issue_summary_by_category") or {}).values())),
        # ★ 证据侧这次**测到没有**：match = 缓存是这一条的；其余（rejected/unavailable/error）
        #   = **未测** —— 此时 orphan/unbacked 一律记 None，免得把「没测到」读成「对不上」。
        "evidence_probe": ev_probe,
        "decision_before_confidence_flow": dtr.get("decision_before_confidence_flow"),
        "reasons": dtr.get("reasons"),
        "coverage_gap": cov_gap,
        "refusal_reason": (dec.get("refusal") or {}).get("reason_code") if isinstance(
            dec.get("refusal"), dict) else None,
        "confidence": dec.get("confidence"),
        "elapsed_s": round(time.time() - t0, 1),
        # 保留旧字段名，免得既有下游读不到（**证据侧**，不是结论清单）
        "findings": [{"rule_id": f.get("rule_id"), "rule_code": f.get("rule_code"),
                      "p_level": f.get("p_level"), "severity": f.get("severity"),
                      "category": f.get("category"), "article_no": f.get("article_no")}
                     for f in ev_findings],
        "conclusion_items": [{"risk_id": i.get("risk_id"), "priority_tier": i.get("priority_tier"),
                              "action": i.get("action"), "risk_type": i.get("risk_type"),
                              "article_no": (i.get("evidence") or {}).get("article_no")}
                             for i in items],
    }
    _ss = same_source_report(items, ev_findings)
    if ev_probe != "match":
        # 未测：只保留条数，把三个「差异」判据置 None（**fail-closed**，不 fail-open）
        _ss.update({"orphan_p3_n": None, "orphan_non_p3": None,
                    "unbacked_n": None, "unbacked_ids": None, "unbacked_sources": None,
                    "evidence_n": None, "unmeasured_reason": ev_probe})
    rec.update(_ss)
    return rec


def load_cases() -> list:
    import yaml
    d = yaml.safe_load(SET.read_text(encoding="utf-8"))
    cases = [dict(c, _layer="solid") for c in (d.get("solid") or [])]
    cases += [dict(c, _layer="fragile") for c in (d.get("fragile") or [])]
    return cases


# 首采缘起（**保留**，别删）：它是这套基线为什么长这样的原因。
_BASE_WHY = ("2026-10-12 首采：旧 `expected` 是从**历史 `*.review.md` 里刮出来的当时的结论**"
             "（`kb/l8/build_regression_set.py`，按同一素材留最早一份去重），"
             "**不是改动前引擎的结论** ⇒ 拿它当断言，等于把「引擎这一年的演进」全报成回归。"
             "实测 13/80 条漂移里 12 条属此类。")


def rebaseline(src: Path, out: Path = BASELINE, why: str | None = None) -> int:
    """以**一次真跑完的产物**重采基线。只收 solid（fragile 会合法变，不作断言）。

    `why` = **本次**重采的原因（`--why`）。为什么要有它：基线里存着每条 case 的
    `issue_count`，而口径一变（例：2026-10-12 `issue_count` 改成只算库内依据），
    存量的数就与现行口径不一致 —— 重采时**必须把这个原因写在基线自己身上**，
    否则下一个人只会看到「基线被谁重采过」，看不出为什么。
    """
    rows = [json.loads(l) for l in src.read_text(encoding="utf-8").splitlines() if l.strip()]
    solid = [r for r in rows if r.get("layer") == "solid"]
    bad = [r for r in solid if not r.get("got") or r.get("error")]
    if bad:
        print("拒收：有 %d 条没拿到三态（%s…）—— 基线不许带空洞"
              % (len(bad), ",".join(r["case_id"] for r in bad[:3])))
        return 3
    obj = {
        "schema": "kb-regression-baseline/1",
        "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "captured_from": str(src),
        "why": ((why + " ｜ 首采缘起：" + _BASE_WHY) if why else _BASE_WHY),
        "reading": ("同源读法：三态 = `decision.decision`；条目 = `decision.risk_items`"
                    "（见 `kb/l8/regression_run.py` 文件头）。"),
        "n_solid": len(solid),
        "cases": {r["case_id"]: {"state": r["got"], "issue_count": r.get("issue_count")}
                  for r in solid},
    }
    out.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")
    print("基线已重采：%s ｜ solid %d 条 ｜ 来源 %s" % (out, len(solid), src))
    return 0


# ── 反向对照（离线桩）─────────────────────────────────────────────────────────
def selftest() -> int:
    ok = True

    def chk(name, cond, extra=""):
        nonlocal ok
        print(("  ✅ " if cond else "  ❌ ") + name + (("  " + extra) if extra and not cond else ""))
        ok = ok and bool(cond)

    print("regression_run 自证（同源读法判据的反向对照）")
    items = [{"risk_id": "r-1", "priority_tier": "P1"},
             {"risk_id": "r-2", "priority_tier": "P3"}]
    finds = [{"rule_id": "r-1", "p_level": "P1"},
             {"rule_id": "r-2", "p_level": "P3"}]
    rep = same_source_report(items, finds)
    chk("① 完全对齐 ⇒ 零 orphan / 零 unbacked",
        rep["orphan_p3_n"] == 0 and rep["unbacked_n"] == 0 and not rep["orphan_non_p3"])

    # 反向：证据有、结论没有，且**不是 P3** ⇒ 必须落进 orphan_non_p3（异常那一类）
    rep2 = same_source_report([items[0]], [finds[0], {"rule_id": "r-9", "p_level": "P1"}])
    chk("② 证据有、结论没采纳的 **非 P3** ⇒ 精确落进 orphan_non_p3",
        len(rep2["orphan_non_p3"]) == 1
        and rep2["orphan_non_p3"][0]["rule_id"] == "r-9",
        repr(rep2["orphan_non_p3"]))

    # 反向：同上但 p_level=P3 ⇒ 必须归到合法那一档，**不许**混进 orphan_non_p3
    rep3 = same_source_report([items[0]], [{"rule_id": "r-2", "p_level": "P3"}])
    chk("③ 未采纳的是 P3（§6.3 执行规则3）⇒ 归 orphan_p3、**不许**判异常",
        rep3["orphan_p3_n"] == 1 and not rep3["orphan_non_p3"])

    # 反向：结论有、证据没有（种子规则扫描器那条路）⇒ 必须被看见
    rep4 = same_source_report([{"risk_id": "seed-9"}, {"risk_id": "r-1"}],
                              [{"rule_id": "r-1", "p_level": "P1"}])
    chk("④ 结论有、证据侧查无此条 ⇒ unbacked 必须计数且点名",
        rep4["unbacked_n"] == 1 and "seed-9" in rep4["unbacked_ids"])

    # 反向：p_level 缺失 ⇒ 不当 P3 放行（宁可报异常，不许默认合法）
    rep5 = same_source_report([], [{"rule_id": "x"}])
    chk("⑤ p_level 缺失 ⇒ **不**按 P3 放行（算异常）",
        len(rep5["orphan_non_p3"]) == 1)

    # ⑥ 台账隔离（2026-10-12 加）：跑批默认**不许**写 kb/l7/runs/index.jsonl。
    #    为什么：引擎每跑一单都会 `run_record.record(source="review_machine")`，
    #    而本跑手一次 100 单 ⇒ 跑一次回归灌 100 行；而「累计评审单数」正是从那份台账算的
    #    ⇒ **度量被测量行为抬高**。喂样本：默认 / --record-runs 两种取值都要对。
    global RECORD_RUNS
    _saved = RECORD_RUNS
    try:
        RECORD_RUNS = False
        _e1 = _child_env()
        chk("⑥a 默认（隔离开）⇒ 子进程环境带 KB_RUN_RECORD_SKIP=1",
            _e1.get("KB_RUN_RECORD_SKIP") == "1")
        RECORD_RUNS = True
        _e2 = _child_env()
        chk("⑥b --record-runs ⇒ 隔离被显式摘掉（写要写出来）",
            "KB_RUN_RECORD_SKIP" not in _e2)
    finally:
        RECORD_RUNS = _saved

    # ⑦ 非权威候选的**拆解读数**（2026-10-12 加，与引擎 `issue_count` 拆分同批）。
    #    为什么要有：`issue_count` 里混着「库内依据」与「非权威候选」，而后者源里自己写着
    #    「已被取代」。跑批是唯一能一眼看到**真实占比**的地方 ⇒ 不测就只是个没人读的字段。
    _rep7 = same_source_report([{"risk_id": "a"}, {"risk_id": "b", "authoritative": False}], [])
    chk("⑦a 候选按声明计数（1 库内 + 1 候选）",
        _rep7.get("candidate_n") == 1 and _rep7.get("authoritative_n") == 1,
        "candidate_n=%s authoritative_n=%s" % (_rep7.get("candidate_n"), _rep7.get("authoritative_n")))
    _rep7b = same_source_report([{"risk_id": "a"}, {"risk_id": "b", "authoritative": True}], [])
    chk("⑦b **反向对照**：声明改成权威 ⇒ 候选归零（判据不是恒等于 items_n）",
        _rep7b.get("candidate_n") == 0 and _rep7b.get("authoritative_n") == 2,
        "candidate_n=%s" % _rep7b.get("candidate_n"))
    chk("⑦c 缺 `authoritative` 键**不算**候选（否则会把全部库内依据打成候选）",
        same_source_report([{"risk_id": "a"}, {"risk_id": "b"}, {"risk_id": "c"}], []).get("candidate_n") == 0)

    # ⑧ 证据缓存的**归属校验**（2026-10-12 加；本跑手自己的缺陷，见 run_case 的 docstring）。
    #    为什么要测：两个跑批同跑时，缓存里会躺着**另一条文案**的依据；裸读就会把
    #    「别人的依据」算成本条的 orphan/unbacked —— 实测 100 条里 10 条假差异。
    #    判据本体是引擎的 `evidence_cache.read_cache()`（带 text_sha256 校验），本处直接喂样本。
    try:
        sys.path.insert(0, str(ROOT / "kb/l7/review-engine/core"))
        from evidence_cache import envelope as _env, read_cache as _rc      # noqa: PLC0415
        import tempfile as _tf2
        _mine, _other = "这一条文案 A", "另一条文案 B"
        _f1 = _tf2.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
        _f1.write(json.dumps(_env(_mine, {"findings": [{"rule_id": "r-1"}]}, "selftest"),
                             ensure_ascii=False))     # envelope() 返回 dict（与 write_cache 同一用法）
        _f1.close()
        _ok, _err = _rc(_f1.name, _mine)
        chk("⑧a 缓存**是这一条**的 ⇒ 正常读到", isinstance(_ok, dict) and _ok.get("findings"),
            "err=%s" % _err)
        _bad, _err2 = _rc(_f1.name, _other)
        chk("⑧b **反向对照**：缓存属于**另一条**文案 ⇒ 必须拒绝（不许把别人的依据算到这条上）",
            _bad is None and "不符" in str(_err2), "err=%s" % _err2)
        os.unlink(_f1.name)
        _src = Path(__file__).read_text(encoding="utf-8")
        chk("⑧c run_case 的证据侧**确实走**那把带校验的读法（不是裸 json.loads）",
            "read_cache as _read_cache" in _src and "evidence_probe" in _src)
    except Exception as e:                              # noqa: BLE001
        chk("⑧ 证据缓存归属校验（反向对照）", False, repr(e))

    print("结论：%s" % ("✅ 判据有反向对照，不是恒真" if ok else "❌ 有反向对照没红 —— 判据是注释"))
    return 0 if ok else 3


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", help="逐条结果 jsonl 落点")
    ap.add_argument("--limit", type=int, default=0, help="只跑前 N 条（0=全跑）")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--record-runs", action="store_true",
                    help="让跑批也写 kb/l7/runs/index.jsonl（**默认不写**：只读测量不进评审台账）")
    ap.add_argument("--rebaseline", action="store_true", help="以 --from 的产物重采基线")
    ap.add_argument("--from", dest="src", help="重采基线时的来源 jsonl")
    ap.add_argument("--why", help="本次重采的原因（写进基线自身的 why 字段，**必填**才可追溯）")
    a = ap.parse_args()

    global RECORD_RUNS
    RECORD_RUNS = bool(a.record_runs)

    if a.selftest:
        return selftest()
    if a.rebaseline:
        if not a.src:
            print("--rebaseline 必须带 --from <jsonl>")
            return 2
        if not (a.why or "").strip():
            print("--rebaseline 必须带 --why <本次重采的原因>："
                  "基线里存着每条 case 的 issue_count，口径变更后重采必须留下原因，"
                  "否则下一个人只看到「被重采过」，看不出为什么。")
            return 3
        return rebaseline(Path(a.src), why=a.why.strip())
    if not a.out:
        print("要么 --out，要么 --selftest / --rebaseline")
        return 2

    cases = load_cases()
    if a.limit:
        cases = cases[:a.limit]
    print("回归集：%d 条（solid %d / fragile %d）｜ 读法：同源（decision.decision + decision.risk_items）"
          % (len(cases), sum(1 for c in cases if c["_layer"] == "solid"),
             sum(1 for c in cases if c["_layer"] == "fragile")), flush=True)

    res, t0 = [], time.time()
    out = Path(a.out)
    for i, c in enumerate(cases, 1):
        r = run_case(c)
        res.append(r)
        out.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in res),
                       encoding="utf-8")
        flag = "✅" if r.get("got") == r.get("expected") else "❌"
        extra = ""
        if r.get("orphan_non_p3"):
            extra += " ⚠️orphan_non_p3=%d" % len(r["orphan_non_p3"])
        if r.get("unbacked_n"):
            extra += " ⚠️unbacked=%d" % r["unbacked_n"]
        print("[%3d/%3d] %-7s %-16s 期望 %-5s 实得 %-5s %s (%.1fs)%s"
              % (i, len(cases), r.get("layer"), r["case_id"], r["expected"],
                 r.get("got") or "ERR", flag, r["elapsed_s"], extra), flush=True)

    solid = [r for r in res if r.get("layer") == "solid"]
    frag = [r for r in res if r.get("layer") == "fragile"]
    sm = [r for r in solid if r.get("got") != r.get("expected")]
    print("\n" + "=" * 72)
    print("solid %d 条：与**历史 expected** 一致 %d ／ 不一致 %d"
          % (len(solid), len(solid) - len(sm), len(sm)))
    print("  ⚠️ 历史 expected 是「报告当时的结论」，**不是改动前引擎的结论** ⇒")
    print("     这一行只作**线索**；真断言看 `kb/l8/regression_gate.py`（比基线）。")
    for r in sm:
        print("   · %s 期望 %s 实得 %s" % (r["case_id"], r["expected"], r.get("got")))
    print("fragile %d 条：%s" % (len(frag), dict(collections.Counter(
        "%s→%s" % (r["expected"], r.get("got")) for r in frag).most_common())))
    orph = [r for r in res if r.get("orphan_non_p3")]
    unb = [r for r in res if r.get("unbacked_n")]
    print("同源判据：orphan_non_p3 命中 %d 条 ｜ unbacked 命中 %d 条" % (len(orph), len(unb)))
    _bad54 = [r["case_id"] for r in res if r.get("prd54_ok") is False]
    if _bad54:
        print("⚠️ PRD §5.4 等式不成立：%d 条 %s（issue_count 必须 == 分类汇总合计）"
              % (len(_bad54), _bad54[:5]))
    else:
        print("PRD §5.4 等式：issue_count == 分类汇总合计 —— 100 条全部成立")
    _cn = [r.get("candidate_n") for r in res]
    if any(v is None for v in _cn):
        print("非权威候选：**未测**（引擎口径没 import 进来）—— 不写 0，免得读成「没有候选」")
    else:
        print("非权威候选：%d 条命中落在 %d 条 case 里（'问题数'里有多少不是库内依据，这里直接可见）"
              % (sum(_cn), sum(1 for v in _cn if v)))
    print("总耗时 %.1f 分钟 ｜ 逐条结果 %s" % ((time.time() - t0) / 60, a.out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
