#!/usr/bin/env python3
"""10/19 重跑（PRD 字数限制更新后）回读校验 —— **只读，不写表、不写库**。

判据（每条都要能复算）：

  V1 链接齐不齐        —— 80 行「10/19 报告链接」：本轮有报告的必须有、PASS/0 的必须空
                          （判据与发布件「清空只走 PASS」同一条，不许两种口径）
  V2 旧列没被动         —— 80 行「报告链接」与**跑前快照**逐字相同（本轮一个字都不许改它）
  V3 链接打得开         —— 每个新 URL 真 fetch 一次（不是看字符串像不像）
  V4 链接与格内同源     —— 报告正文的「共发现 N 处」== 表内 `问题数量`
  V5 结论与台账一致     —— 表内 `Agent 结论` == 本轮台账 `state`
  V6 字数合规读数       —— 从本轮 `merged-reports/*.json` 读 §5.3.3（描述/原因/建议）与 §17 读数

用法：
    python3 _rerun80-20261019/verify_rerun80.py            # 全跑
    python3 _rerun80-20261019/verify_rerun80.py --no-fetch # 跳过 V3/V4（省时间）
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
BASE = "RY2UbCRjXaeeWwscUPScVN5AnQc"
TABLE = "tblavfbMDMeRsulo"
BEFORE = os.path.join(HERE, "records.ndjson")
AFTER = os.path.join(HERE, "records-after.ndjson")
LEDGER = os.path.expanduser("~/Project/audit_multi_content/PMO/shouheng-state/batch-review-1019.json")
# ★ merged 记录的落点**有两个**，别只读一个（2026-10-19 实测）：
#   `agent/merged_report.mjs:62` 解析的是 `path.join(process.cwd(), '..', 'PMO', 'shouheng-state', 'merged-reports')`
#   ⇒ 守护进程（cwd=…/audit_multi_content/tools）写在 `audit_multi_content/PMO/shouheng-state/`；
#     而批跑器（一直是从**仓根**起跑的，cwd=…/audit_multi_content）写在 `Project/PMO/shouheng-state/`。
#   历史对得上：后者 762 个文件里 **754 个是 10/13–10/16 的批跑件**。⇒ 两处都扫，按 at 筛本轮。
MERGED_DIRS = [
    os.path.expanduser("~/Project/PMO/shouheng-state/merged-reports"),
    os.path.expanduser("~/Project/audit_multi_content/PMO/shouheng-state/merged-reports"),
]


def lark(*args: str) -> dict:
    out = subprocess.run([LARK, *args], capture_output=True, text=True, timeout=180)
    try:
        return json.loads(out.stdout or "{}")
    except json.JSONDecodeError:
        return {"ok": False, "error": {"raw": (out.stdout or "")[:300], "stderr": (out.stderr or "")[:300]}}


def fetch_rows() -> list[dict]:
    # ⚠️ `--format ndjson` 打的是 **manifest**（没有 `ok` 字段）⇒ 判据不能看 `ok`，
    #    要看「落盘文件在不在、行数对不对」。第一版按 `ok` 判，第一次跑就误报「读表失败：null」。
    d = lark("base", "+record-list", "--base-token", BASE, "--table-id", TABLE,
             "--format", "ndjson", "--output", AFTER, "--overwrite",
             "--profile", "dsh-kb", "--as", "bot")
    if not os.path.exists(AFTER):
        raise SystemExit(f"读表失败（没落盘）：{json.dumps(d, ensure_ascii=False)[:300]}")
    rows = [json.loads(l) for l in open(AFTER, encoding="utf-8") if l.strip()]
    if not rows:
        raise SystemExit(f"读表失败（0 行）：{json.dumps(d, ensure_ascii=False)[:300]}")
    return rows


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
    s = plain(v)
    m = re.search(r"https?://[^\s)\]]+", s)
    return m.group(0) if m else ""


def doc_text(url: str) -> str:
    tok = url.rsplit("/", 1)[-1]
    d = lark("docs", "+fetch", "--doc", tok, "--doc-format", "markdown", "--profile", "dsh-kb", "--as", "bot")
    if not d.get("ok"):
        return ""
    return ((d.get("data") or {}).get("document") or {}).get("content") or ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-fetch", action="store_true")
    a = ap.parse_args()

    before = {r["record_id"]: r for r in (json.loads(l) for l in open(BEFORE, encoding="utf-8") if l.strip())}
    after = fetch_rows()
    ledger = json.load(open(LEDGER, encoding="utf-8")).get("items", {})

    print(f"表内 {len(after)} 行 ｜ 跑前快照 {len(before)} 行 ｜ 本轮台账 {len(ledger)} 条\n")

    problems: list[str] = []
    # V0 覆盖面：80 行都要在本轮台账里答过；表里不该有不认识的行
    ids_after = {plain(r.get("内容 ID")) for r in after}
    not_answered = sorted(cid for cid, d in ledger.items() if not d.get("answered_at") and cid in ids_after)
    not_in_ledger = sorted(ids_after - set(ledger))
    if not_answered:
        problems.append(f"V0 本轮没答完 {len(not_answered)} 行：{not_answered[:6]}")
    if not_in_ledger:
        problems.append(f"V0 台账里没有这 {len(not_in_ledger)} 行：{not_in_ledger[:6]}")
    print(f"V0 覆盖：台账已答 {len(ledger) - len(not_answered)} / {len(ids_after)} 行"
          f"（未答 {len(not_answered)}、台账缺 {len(not_in_ledger)}）\n")
    v1_ok = v1_bad = v2_bad = 0
    prd_viol: list[tuple[str, str]] = []      # 结论值域越界（非 PASS/REVIEW/BLOCK）
    per_row = []

    for r in after:
        rid = r["record_id"]
        cid = plain(r.get("内容 ID"))
        old_link = url_of(before.get(rid, {}).get("报告链接"))
        new_link = url_of(r.get("10/19 报告链接"))
        now_old = url_of(r.get("报告链接"))
        led = ledger.get(cid) or {}
        state = led.get("state")
        issues = r.get("问题数量")
        n_issue = None if issues in (None, "") else int(float(issues))

        # V2 旧列没被动
        if now_old != old_link:
            v2_bad += 1
            problems.append(f"V2 {cid}：旧「报告链接」被改了 {old_link!r} → {now_old!r}")

        # V1 链接齐不齐：有报告 ⇒ 必须有；PASS 且 0 条 ⇒ 必须空
        want = led.get("report_url") or ""
        if want and new_link != want:
            v1_bad += 1
            problems.append(f"V1 {cid}：本轮有报告但列里是 {new_link!r}（台账 {want!r}）")
        elif not want and new_link:
            v1_bad += 1
            problems.append(f"V1 {cid}：本轮没建报告，列里却写了 {new_link!r}")
        else:
            v1_ok += 1

        # V5 结论与台账一致
        if state and plain(r.get("Agent 结论")) != state:
            problems.append(f"V5 {cid}：表内结论 {plain(r.get('Agent 结论'))!r} ≠ 台账 {state!r}")

        # V7 结论值域（PRD §5.3.2 rev101 / §10.1：`decision` 只有三值，SUGGEST 是标签不是取值）
        st_now = plain(r.get("Agent 结论"))
        if st_now and st_now not in ("PASS", "REVIEW", "BLOCK"):
            prd_viol.append((cid, st_now))

        per_row.append({"record_id": rid, "content_id": cid, "type": plain(r.get("内容类型")),
                        "state_before": plain(before.get(rid, {}).get("Agent 结论")),
                        "issues_before": before.get(rid, {}).get("问题数量"),
                        "state_after": plain(r.get("Agent 结论")), "issues_after": n_issue,
                        "old_link": old_link, "new_link": new_link, "ledger_state": state,
                        "ledger_report": want})

    # V3/V4 真 fetch
    v3, v4 = [], []
    if not a.no_fetch:
        targets = [p for p in per_row if p["new_link"]]
        print(f"V3/V4：真 fetch {len(targets)} 份新报告 …")

        def one(p):
            t = doc_text(p["new_link"])
            if not t:
                return (p, "unreachable", None)
            m = re.search(r"共发现\s*\**\s*(\d+)\s*处", t)
            return (p, "ok", int(m.group(1)) if m else None)

        with ThreadPoolExecutor(max_workers=4) as ex:
            for p, st, n in ex.map(one, targets):
                if st != "ok":
                    v3.append(p["content_id"])
                    problems.append(f"V3 {p['content_id']}：新报告打不开 {p['new_link']}")
                    continue
                if n is not None and p["issues_after"] is not None and n != p["issues_after"]:
                    v4.append((p["content_id"], n, p["issues_after"]))
                    problems.append(f"V4 {p['content_id']}：报告写 {n} 处，表里 {p['issues_after']}")

    # V6 字数合规读数（本轮 merged 记录）
    since = "2026-10-19T10:40"
    files = sorted(f for d0 in MERGED_DIRS for f in glob.glob(os.path.join(d0, "merged-2026-10-19T*.json")))
    recs = []
    for f in files:
        try:
            d = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        if str(d.get("at", "")) < since:
            continue
        recs.append(d)
    trunc_advice = trunc_reason = 0
    items_total = 0
    conf_bad = 0
    loc_bad = 0
    basis_bad = 0
    for d in recs:
        if d.get("card_conformance"):
            conf_bad += 1
        for it in d.get("items") or []:
            items_total += 1
            t = it.get("truncated") or {}
            if t.get("advice"):
                trunc_advice += 1
            if t.get("reason"):
                trunc_reason += 1
            loc = str(it.get("location") or "").strip()
            if loc and not re.match(r"^(图\s*\d+\s*第\s*\d+\s*处|视频\s*\d{1,2}:\d{2}|正文第\s*\d+\s*段)$", loc):
                loc_bad += 1
            b = str(it.get("basis_card") or "")
            if b and not re.search(r"《[^》]+》\s*第\s*[0-9A-Za-z.\-]+\s*条|[A-Z]{1,3}-[0-9]|[A-Z]{1,2}[0-9]{2,3}|[rp]-[0-9a-f]{8,}", b):
                basis_bad += 1

    if prd_viol:
        problems.append("V7 结论值域越界（PRD §5.3.2 rev101：decision 只 PASS/REVIEW/BLOCK；"
                        f"SUGGEST 只是标签）{len(prd_viol)} 行：{prd_viol[:8]}")

    flipped = [p for p in per_row if p["state_before"] and p["state_after"] and p["state_before"] != p["state_after"]]
    summary = {
        "rows": len(after),
        "V1_link_complete_ok": v1_ok, "V1_link_bad": v1_bad,
        "V2_old_column_changed": v2_bad,
        "V3_unreachable": v3, "V4_count_mismatch": v4,
        "V7_verdict_out_of_prd_range": prd_viol,
        "conclusion_flips": [{"content_id": p["content_id"], "before": p["state_before"],
                              "after": p["state_after"], "issues_before": p["issues_before"],
                              "issues_after": p["issues_after"]} for p in flipped],
        "compliance": {"merged_records": len(recs), "items": items_total,
                       "advice_truncated": trunc_advice, "reason_truncated": trunc_reason,
                       "card_conformance_warn": conf_bad,
                       "location_not_in_3_patterns": loc_bad, "basis_not_prd_shape": basis_bad},
        "problems": problems,
        "per_row": per_row,
    }
    out = os.path.join(HERE, "verify-report.json")
    json.dump(summary, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    print("\n=== 结论 ===")
    print(f"V1 链接齐/不齐          ： {v1_ok} / {v1_bad}")
    print(f"V2 旧列被改动的行        ： {v2_bad}   （必须 0）")
    if not a.no_fetch:
        print(f"V3 新报告打不开          ： {len(v3)}")
        print(f"V4 报告处数≠表内问题数量 ： {len(v4)}")
    print(f"V7 结论值域越界          ： {len(prd_viol)} 行 {collections.Counter(v for _, v in prd_viol).most_common()}")
    print(f"结论翻转                 ： {len(flipped)} 行 "
          f"｜{collections.Counter((p['state_before'], p['state_after']) for p in flipped).most_common()}")
    c = summary["compliance"]
    print(f"字数读数（{c['merged_records']} 份 merged / {c['items']} 条）：建议被压 {c['advice_truncated']} 条 ｜"
          f"原因被压 {c['reason_truncated']} 条 ｜卡面不合规 {c['card_conformance_warn']} 份 ｜"
          f"位置不合 §5.3.3 {c['location_not_in_3_patterns']} 条 ｜依据不合 {c['basis_not_prd_shape']} 条")
    if problems:
        print(f"\n问题清单（{len(problems)} 条，前 12）：")
        for x in problems[:12]:
            print("  ·", x)
    print(f"\n明细 → {out}")
    return 0 if not problems else 3


if __name__ == "__main__":
    sys.exit(main())
