#!/usr/bin/env python3
"""80 份报告核对（Owner 2026-10-19 的 6 项）—— **只读**，不写任何表/库。

六项对应：
  ① 两侧都跑了吗        —— 库侧（机读旁挂/链）＋ 模型侧，逐行看本轮 merged 记录的 `kb` / `model`
  ② 置信度是不是两侧合成一个数 —— 读 `confidence-merged.ndjson` 本轮 80 行；`merged_value=null` 的
                              在表里被写成 0（那**不是一个置信度**，是"没有这个数"）
  ③ 表内五字段与报告正文一致 —— Agent 结论 / 问题数量 / 问题分类汇总（＋置信度、状态的适用性说明）
  ④ 链接打得开          —— 真 fetch
  ⑤ 三态计数            —— PASS / REVIEW / BLOCK / PASS+SUGGEST
  ⑥ <3 条的补报告        —— 由 `mk_report_small.py` 另做，本脚本只读口径不改它

用法：
    python3 _rerun80-20261019/audit_reports80.py                 # 全跑（含 fetch）
    python3 _rerun80-20261019/audit_reports80.py --no-fetch      # 只做本地读数
"""
from __future__ import annotations

import argparse
import collections
import glob
import json
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
LARK = os.path.expanduser("~/.dsh/bin/lark-cli")
SIDE = os.path.expanduser("~/Project/audit_multi_content/PMO/shouheng-state")
LEDGER = os.path.join(SIDE, "batch-review-1019.json")
CONF = os.path.join(SIDE, "confidence-merged.ndjson")
# merged 记录两个落点（见 改动单：批跑器从仓根起跑 ⇒ 落在 Project/PMO/…）
MERGED_DIRS = [os.path.expanduser("~/Project/PMO/shouheng-state/merged-reports"), SIDE + "/merged-reports"]
TABLE_ROWS = os.path.join(HERE, "records-final.ndjson")
SUPPLEMENT = os.path.join(HERE, "reports-small-supplement.json")   # ⑥ 补建的报告（若已跑）
START = "2026-10-19T10:40"


def lark(*a):
    o = subprocess.run([LARK, *a], capture_output=True, text=True, timeout=180)
    try:
        return json.loads(o.stdout or "{}")
    except json.JSONDecodeError:
        return {}


def plain(v) -> str:
    if v is None:
        return ""
    if isinstance(v, str):
        return v
    if isinstance(v, list):
        return "".join(plain(x) for x in v)
    if isinstance(v, dict):
        return str(v.get("link") or v.get("text") or "")
    return str(v)


def url_of(v) -> str:
    m = re.search(r"https?://[^\s)\]]+", plain(v))
    return m.group(0) if m else ""


def doc_text(u: str) -> str:
    d = lark("docs", "+fetch", "--doc", u.rsplit("/", 1)[-1], "--doc-format", "markdown",
             "--profile", "dsh-kb", "--as", "bot")
    return ((d.get("data") or {}).get("document") or {}).get("content") or ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-fetch", action="store_true")
    a = ap.parse_args()

    rows = [json.loads(l) for l in open(TABLE_ROWS, encoding="utf-8") if l.strip()]
    led = json.load(open(LEDGER, encoding="utf-8")).get("items", {})
    conf = [r for r in (json.loads(l) for l in open(CONF, encoding="utf-8") if l.strip())
            if str(r.get("at", "")) >= START]
    # 置信度台账按**素材哈希**记，不按内容 ID ⇒ 只能按「本轮各自的时间窗」配到行
    merged = []
    for f in sorted(x for d0 in MERGED_DIRS for x in glob.glob(os.path.join(d0, "merged-2026-10-19T*.json"))):
        try:
            d = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        if str(d.get("at", "")) >= START:
            merged.append(d)
    supp = {}
    if os.path.exists(SUPPLEMENT):
        supp = json.load(open(SUPPLEMENT, encoding="utf-8"))

    def near(at, items):
        """在台账时间窗内取唯一一条（窗口 = ran_from .. sent_at）。"""
        hit = [x for x in items if at and str(x.get("at", "")) >= at[0] and str(x.get("at", "")) <= at[1]]
        return hit[-1] if hit else None

    per = []
    used_c, used_m = set(), set()
    for r in rows:
        cid = plain(r.get("内容 ID"))
        d = led.get(cid) or {}
        win = (str(d.get("ran_from") or ""), str(d.get("sent_at") or ""))
        mk = lambda x: id(x)
        mc = None
        for x in conf:
            if id(x) in used_c:
                continue
            if win[0] and win[0] <= str(x.get("at", "")) <= win[1]:
                mc, _ = x, used_c.add(id(x))
                break
        mm = None
        for x in merged:
            if id(x) in used_m:
                continue
            if win[0] and win[0] <= str(x.get("at", "")) <= win[1]:
                mm, _ = x, used_m.add(id(x))
                break
        per.append({
            "content_id": cid, "record_id": r["record_id"], "type": plain(r.get("内容类型")),
            "table": {"结论": plain(r.get("Agent 结论")), "问题数": r.get("问题数量"),
                      "置信度": r.get("置信度"), "状态": plain(r.get("状态")),
                      "报告": plain(r.get("问题分类汇总")), "链接1019": url_of(r.get("10/19 报告链接")),
                      "链接旧": url_of(r.get("报告链接"))},
            "ledger": {"state": d.get("state"), "report": d.get("report_url"), "reason": d.get("reply_reason"),
                       "secs": d.get("secs")},
            "merged": None if not mm else {"at": mm.get("at"), "state": mm.get("state"),
                                           "sides": mm.get("sides"), "kb": mm.get("kb"), "model": mm.get("model"),
                                           "items": len(mm.get("items") or [])},
            "conf": None if not mc else {"merged": mc.get("merged_value"), "band": mc.get("band"),
                                         "kb": mc.get("kb_value"), "model_band": mc.get("model_band"),
                                         "basis": mc.get("basis")},
            "supp": supp.get(cid),
        })

    # ── ① 两侧都跑 ─────────────────────────────────────────────────────────
    both, kb_missing, model_missing = [], [], []
    for p in per:
        m = p["merged"]
        kbok = bool(m and (m["kb"] or {}).get("state"))
        mok = bool(m and (m["model"] or {}).get("ok"))
        if not kbok:
            kb_missing.append((p["content_id"], None if not m else (m["kb"] or {}).get("state")))
        if not mok:
            model_missing.append((p["content_id"], None if not m else (m["model"] or {}).get("error")))
        if kbok and mok:
            both.append(p["content_id"])

    # ── ② 置信度 ───────────────────────────────────────────────────────────
    conf_ok = [p for p in per if (p["conf"] or {}).get("merged") is not None]
    conf_none = [p for p in per if (p["conf"] or {}).get("merged") is None]
    conf_zero_in_table = [p for p in per if str(p["table"]["置信度"]) in ("0", "0.0", "0.00")]
    conf_mismatch = []
    for p in per:
        c, t = p["conf"], p["table"]["置信度"]
        if not c:
            continue
        try:
            tn = float(t) if t not in (None, "") else None
        except (TypeError, ValueError):
            tn = None
        cv = c.get("merged")
        if cv is None:
            if tn not in (None, 0.0):
                conf_mismatch.append((p["content_id"], "台账无该数", f"表内 {t}"))
        elif tn is None or abs(float(cv) - tn) > 1e-9:
            conf_mismatch.append((p["content_id"], cv, f"表内 {t}"))

    # ── ③ 与报告正文一致（只看本轮有报告的；<3 条的补报告另算）───────────────
    def norm(t):
        return re.sub(r"[\s*_`>·•]+", "", str(t or ""))

    checks = []
    targets = [p for p in per if p["table"]["链接1019"]]
    sup_targets = [p for p in per if (p.get("supp") or {}).get("url")]
    if not a.no_fetch and (targets or sup_targets):
        def one(p):
            u = p["table"]["链接1019"] or ((p.get("supp") or {}).get("url") or "")
            return p, (doc_text(u) if u else "")
        pool = targets + [p for p in sup_targets if not p["table"]["链接1019"]]
        with ThreadPoolExecutor(max_workers=4) as ex:
            for p, md in ex.map(one, pool):
                if not md:
                    checks.append({"id": p["content_id"], "opened": False, "why": "打不开/空文档"})
                    continue
                m = re.search(r"(?:共)?发现\s*\**\s*(\d+)\s*处", md)
                n_rep = int(m.group(1)) if m else None
                st_rep = (re.search(r"【审查结论[：:]\s*([A-Z_]+)", md) or [None, None])[1]
                # 分类汇总：报告开头那几行「· 类别问题：N 个」＋结论句
                cats = re.findall(r"[·•]\s*([^\n：:]{2,40})问题[：:]\s*(\d+)\s*个", md)
                tcats = re.findall(r"[·•]\s*([^\n：:]{2,40})问题[：:]\s*(\d+)\s*个", p["table"]["报告"])
                # ★ 汇总格有两种版式：≥3 条是「· 类别问题：N 个」，<3 条是「1.【类别-子类】…」。
                #   判据取**能跨两种版式都成立**的那条：表格那格点到的每个类别标签，报告里都得在。
                cell = p["table"]["报告"]
                labels = [x for x in re.findall(r"【([^】]{4,60})】", cell) if "审查结论" not in x]
                labels = list(dict.fromkeys(labels))
                # ★ 分隔符归一：表格那格写「类别-子类」，报告逐条头写「类别·子类」，
                #   同一件事两种分隔符 ⇒ 不归一会**误报**（2026-10-19 实测 1 条假红）。
                def _k(t):
                    return re.sub(r"[\s*_`>·•｜|/\-－—]+", "", str(t))
                nmd = _k(md)
                miss = [x for x in labels if _k(x) not in nmd]
                t_issues = p["table"]["问题数"]
                ok_state = (st_rep == p["table"]["结论"]) if st_rep else None
                try:
                    tn = int(float(t_issues)) if t_issues not in (None, "") else None
                except (TypeError, ValueError):
                    tn = None
                if tn == 0 and st_rep == "PASS":
                    # PASS/0：报告里**不该**出现「发现 N 处」（N>0）；出现了才是坏
                    ok_n = (n_rep is None) or (n_rep == 0)
                else:
                    ok_n = (n_rep is not None and tn is not None and tn == n_rep)
                ok_cat = (not miss) if labels else None
                checks.append({"id": p["content_id"], "opened": True, "rep_state": st_rep,
                               "table_state": p["table"]["结论"], "rep_n": n_rep,
                               "table_n": t_issues, "ok_state": ok_state, "ok_n": ok_n,
                               "ok_cat": ok_cat, "rep_cats": cats, "table_cats": tcats,
                               "labels_missing": miss,
                               "source": "1019列" if p["table"]["链接1019"] else "补建"})
    c_bad = [c for c in checks if not c.get("opened")]
    c_state = [c for c in checks if c.get("ok_state") is False]
    c_n = [c for c in checks if c.get("ok_n") is False]
    c_cat = [c for c in checks if c.get("ok_cat") is False]

    # ── ⑤ 三态计数 ─────────────────────────────────────────────────────────
    cnt = collections.Counter(p["table"]["结论"] or "(空)" for p in per)
    pass_suggest = [p for p in per if p["table"]["结论"] == "SUGGEST"]

    out = {
        "rows": len(per),
        "check1_both_sides": {"both": len(both), "kb_missing": kb_missing, "model_missing": model_missing},
        "check2_confidence": {
            "has_merged_number": len(conf_ok),
            "no_merged_number": [p["content_id"] for p in conf_none],
            "table_wrote_zero": [p["content_id"] for p in conf_zero_in_table],
            "mismatch": conf_mismatch,
            "distribution": collections.Counter(
                "null" if (p["conf"] or {}).get("merged") is None else str((p["conf"] or {}).get("merged"))
                for p in per).most_common(),
        },
        "check3_report_consistency": {
            "checked": len(checks), "unopenable": c_bad,
            "state_mismatch": c_state, "count_mismatch": c_n, "category_mismatch": c_cat,
            "note": "报告正文不印『置信度』、也不印『状态』⇒ 这两项无法与报告互核（见交付说明）",
        },
        "check4_links": {"with_1019_link": len(targets), "with_supplement": len(sup_targets),
                         "unopenable": [c["id"] for c in c_bad]},
        "check5_states": {"counts": cnt.most_common(), "pass_suggest_rows": len(pass_suggest),
                          "pass_suggest_ids": [p["content_id"] for p in pass_suggest]},
        "per_row": per,
    }
    json.dump(out, open(os.path.join(HERE, "audit-report.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    print(f"行数 {len(per)}")
    print(f"\n① 两侧都跑：都跑 {len(both)} ｜缺库侧 {len(kb_missing)} ｜缺模型侧 {len(model_missing)}")
    if kb_missing:
        print("   缺库侧样本:", kb_missing[:5])
    if model_missing:
        print("   缺模型侧样本:", model_missing[:5])
    print(f"\n② 置信度：有合成数 {len(conf_ok)} ｜**没有这个数** {len(conf_none)} ｜表里写成 0 {len(conf_zero_in_table)} ｜"
          f"与台账不符 {len(conf_mismatch)}")
    print("   分布:", out["check2_confidence"]["distribution"])
    print(f"\n③ 与报告正文：核了 {len(checks)} 份 ｜打不开 {len(c_bad)} ｜结论不符 {len(c_state)} ｜"
          f"问题数不符 {len(c_n)} ｜分类汇总不符 {len(c_cat)}")
    for x in (c_state + c_n + c_cat)[:6]:
        print("   ·", json.dumps(x, ensure_ascii=False)[:200])
    print(f"\n④ 链接：10/19 列 {len(targets)} 份 ｜补建 {len(sup_targets)} 份 ｜打不开 {len(c_bad)}")
    print(f"\n⑤ 三态计数: {cnt.most_common()} ｜PASS+SUGGEST(=结论写 SUGGEST) {len(pass_suggest)} 行")
    print(f"\n明细 → {os.path.join(HERE, 'audit-report.json')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
