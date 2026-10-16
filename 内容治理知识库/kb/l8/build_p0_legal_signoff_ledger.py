#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_p0_legal_signoff_ledger.py —— 目标 18：**P0 红线法务逐条确认台账**（留签署记录）。

## 出处（逐字）

· 任务拆解 10/12–10/16 行 · **目标 18**：`【补·PRD §16】P0 红线上线前由法务逐条确认（留签署记录）。`
· 同表交付物 18：`P0 红线法务逐条确认记录`
· PRD §16 风险与依赖原文：风险「**P0 规则误配**」→ 影响「红线漏放或误伤」→
  应对「**P0 规则上线前由法务逐条确认**；P0 层定期回归测试」
· 同表 G 列现状自记：「目标 18 P0 红线法务逐条确认 —— 现状 **无签署记录**」
  并写明它对知识库的作用：「**红线的判定有法务背书**，不是库侧自己拍的。」

## 本件做什么 / 不做什么（**这条最要紧**）

**做**：把「逐条确认」这件事**落成一张可签、可核、可溯源的台账** —— 11 条 P0 模式逐条一行，
每条带齐**四段溯源**（条款号 / 规则与命中表达 / anchor + source_sha256 / 源直链），
外加**空的签署区**（`status=pending`）。

**不做**：**不替法务签**。`signer` / `signed_at` / `basis` 一律 `null`，
  `status` 一律 `pending` —— **没签就是没签**。
  ★ 本库在「不许编」上栽过：**空值人会去补，错值人不会再回头看。**

⇒ 本件的产出是「**夹具就绪 + 待签 11 条**」，**不是**「已确认」。
   `--verify` 会如实打印 `已签 N/11`；N=11 且 0 例外，才算 PRD §16 那条应对真落地。

## 用法

    python3 kb/l8/build_p0_legal_signoff_ledger.py            # 预演（零写入）
    python3 kb/l8/build_p0_legal_signoff_ledger.py --apply    # 落盘
    python3 kb/l8/build_p0_legal_signoff_ledger.py --verify    # 只读：已签几条
    python3 kb/l8/build_p0_legal_signoff_ledger.py --selftest  # 自证（含反向对照）
"""
from __future__ import annotations

import argparse
import io
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
KB = os.path.dirname(HERE)
ROOT = os.path.dirname(KB)
PATTERNS = os.path.join(KB, "l5/p0_patterns.jsonl")
OUT_JSONL = os.path.join(KB, "l5/registry/p0-legal-signoff-ledger.jsonl")
OUT_JSON = os.path.join(KB, "l5/registry/p0-legal-signoff-ledger.json")

#: 四段溯源里本层能核的三段（第四段「逐字原文」靠 source_sha256 + 直链回 L0，本地不复算）
REQUIRED_TRACE = ("article_no", "anchor", "source_sha256")


def entry_url(rid):
    """L0 源记录直链 —— 第四段要可点（本库口径：anchor/sha 不可点，不给直链等于没法定回去）。"""
    return ("https://momcozy-in.feishu.cn/base/GnRZbIuXraCzf0sGr2UcmZ62nfc"
            "?table=tblXsrMVkDNZ3oW8&record=" + str(rid))


def build(patterns_path=PATTERNS):
    """读 P0 模式 ⇒ (台账行, 未决明细)。**四段溯源缺一不进台账**。"""
    rows, unresolved = [], []
    with io.open(patterns_path, encoding="utf-8") as fh:
        pats = [json.loads(l) for l in fh if l.strip()]
    for p in pats:
        pid = p.get("pattern_id") or p.get("rule_code")
        lack = [k for k in REQUIRED_TRACE if not p.get(k)]
        if lack:
            unresolved.append({"pattern_id": pid, "missing": lack,
                               "why": "四段溯源缺段 ⇒ 不进台账（不许拿缺依据的条目去让人签）"})
            continue
        rows.append({
            "pattern_id": pid,
            "rule_code": p.get("rule_code"),
            "rule_id": p.get("rule_id"),                    # L4 唯一主键
            "p_level": p.get("p_level") or "P0",
            "article_no": p.get("article_no"),              # 第一段：条款号
            "article_no_source": p.get("article_no_source"),
            "match_terms": p.get("match_terms"),            # 第二段：规则与命中表达
            "patterns": p.get("patterns"),
            "regex_patterns": p.get("regex_patterns"),
            "match_note": p.get("match_note"),
            "type": p.get("type"),
            "authority": p.get("authority"),
            "suggested_replacement": p.get("suggested_replacement"),
            "anchor": p.get("anchor"),                      # 第三段：坐标
            "source_sha256": p.get("source_sha256"),        # 第三段：指纹
            "evidence_units": p.get("evidence_units"),
            "entry_url": entry_url(p.get("rule_id")),       # 第四段：可点回源
            "whitelist_allowed_expressions": p.get("whitelist_allowed_expressions"),
            # ── 签署区：**一律留空**，人签了才填 ──────────────────────────
            "legal_signoff": {
                "status": "pending",        # pending / confirmed / rejected —— 只许人改
                "signer": None,             # 具名（不许写「法务团队」）
                "signed_at": None,          # YYYY-MM-DD
                "basis": None,              # 依据（法条 / 内部口径 / 会议纪要）
                "note": None,               # 例外、附条件通过、要改的地方
            },
            "round": 1,                     # 复核轮次；P0 层定期回归测试后 ++
        })
    return rows, unresolved


def verify(jsonl=OUT_JSONL):
    """只读：已签几条。**pending 不许被算成已签。**"""
    if not os.path.exists(jsonl):
        print("台账不存在：%s（先 --apply）" % os.path.relpath(jsonl, ROOT))
        return 2
    rows = [json.loads(l) for l in io.open(jsonl, encoding="utf-8") if l.strip()]
    def st(r):
        return ((r.get("legal_signoff") or {}).get("status") or "pending")
    confirmed = [r for r in rows if st(r) == "confirmed"]
    rejected = [r for r in rows if st(r) == "rejected"]
    pending = [r for r in rows if st(r) == "pending"]
    # ★ 判据：confirmed 必须**有具名签署人**；只有 status 不算
    _lab = lambda r: (r.get("rule_code") or r.get("pattern_id"))
    nameless = [_lab(r) for r in confirmed if not (r["legal_signoff"].get("signer") or "").strip()]
    print("P0 红线法务逐条确认台账：共 %d 条" % len(rows))
    print("  已确认 %d（其中无具名签署人 %d ← 必须是 0）" % (len(confirmed), len(nameless)))
    print("  已驳回 %d ｜ 待签 %d" % (len(rejected), len(pending)))
    print("  待签：%s" % ", ".join(_lab(r) for r in pending) if pending else "  待签：无")
    ok = (len(rows) == 11 and not nameless and not pending)
    print("结论：%s" % ("✅ PRD §16「P0 规则上线前由法务逐条确认」已落地"
                       if ok else
                       "⛔ 未落地 —— 待签 %d 条（夹具已就绪，**签署是人动作，不许代签**）" % len(pending)))
    return 0 if ok else 3


def selftest():
    res = []

    def ck(n, c, ex=""):
        res.append((n, bool(c), ex))

    rows, unres = build()
    ck("① 11 条 P0 模式一条不少", len(rows) + len(unres) == 11, "台账 %d + 未决 %d" % (len(rows), len(unres)))
    ck("①b 全部进台账（四段溯源齐）", len(rows) == 11 and not unres, "未决 %d" % len(unres))
    ck("② 四段溯源：条款号 / anchor / source_sha256 无一为空",
       all(all(r[k] for k in REQUIRED_TRACE) for r in rows), "")
    ck("②b 第四段可点（entry_url 非空）", all(r["entry_url"].startswith("https://") for r in rows), "")
    ck("②c rule_id 唯一（L4 主键，不许靠 rule_code）",
       len({r["rule_id"] for r in rows}) == len(rows), "唯一 %d/%d" % (len({r["rule_id"] for r in rows}), len(rows)))
    # ★ 反向对照 A：**不许代签** —— 初始必须 11 条全 pending 且签署区全空
    ck("③ 反向对照：初始 11 条全 pending、签署区全空（不许代签）",
       all(r["legal_signoff"]["status"] == "pending" and not r["legal_signoff"]["signer"]
           and not r["legal_signoff"]["signed_at"] and not r["legal_signoff"]["basis"] for r in rows), "")
    # ★ 反向对照 B：缺一段溯源 ⇒ 不进台账（真造一条）
    import tempfile
    bad = dict(rows[0]); bad.pop("source_sha256")
    tmp = tempfile.mkdtemp(prefix="t18sign-")
    fp = os.path.join(tmp, "p.jsonl")
    io.open(fp, "w", encoding="utf-8").write("\n".join(
        [json.dumps({k: v for k, v in bad.items() if k != "legal_signoff"}, ensure_ascii=False)] +
        [json.dumps({"pattern_id": "X1", "article_no": "W-1.99", "anchor": "#a",
                     "source_sha256": "deadbeef", "rule_id": "r-x"}, ensure_ascii=False)]) + "\n")
    r2, u2 = build(fp)
    ck("④ 反向对照：缺 source_sha256 ⇒ 不进台账（进未决）",
       len(r2) == 1 and len(u2) == 1 and "source_sha256" in u2[0]["missing"], "进 %d / 未决 %d" % (len(r2), len(u2)))
    # ★ 变异测试：把 status 改 confirmed 但不写 signer ⇒ verify 的判据必须精确变红
    tdir = os.path.join(tmp, "led")
    os.makedirs(tdir, exist_ok=True)
    led = os.path.join(tdir, "l.jsonl")
    fake = []
    for i, r in enumerate(rows):
        r = json.loads(json.dumps(r))
        if i == 0:
            r["legal_signoff"]["status"] = "confirmed"      # ← 造假：签了但没签名
        fake.append(r)
    io.open(led, "w", encoding="utf-8").write("\n".join(json.dumps(r, ensure_ascii=False) for r in fake) + "\n")
    import contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = verify(led)
    out = buf.getvalue()
    ck("⑤ 变异测试：confirmed 但无具名签署人 ⇒ verify 判「无具名 1」且不通过",
       "无具名签署人 1" in out and rc == 3, "rc=%d" % rc)
    # ★ 反向对照 C：全 pending ⇒ 必须判「未落地」（不许把待签当已落地）
    io.open(led, "w", encoding="utf-8").write("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n")
    buf2 = io.StringIO()
    with contextlib.redirect_stdout(buf2):
        rc2 = verify(led)
    ck("⑥ 反向对照：全 pending ⇒ 判「未落地」（不许当已落地）",
       rc2 == 3 and "待签 11" in buf2.getvalue(), "rc=%d" % rc2)
    import shutil
    shutil.rmtree(tmp, ignore_errors=True)
    print("build_p0_legal_signoff_ledger --selftest（目标 18 · P0 法务逐条确认台账）")
    for n, c, ex in res:
        print("  %s %s%s" % ("✅" if c else "❌", n, ("　｜ " + ex) if ex else ""))
    bad_n = sum(1 for _, c, _e in res if not c)
    print("结果：%d/%d%s" % (len(res) - bad_n, len(res), "" if not bad_n else "  ← 有失败"))
    return 1 if bad_n else 0


def _signed_rows(jsonl=OUT_JSONL):
    """已签（非 pending）的行。**读不到就返回空** —— 首次生成时台账还不存在。"""
    try:
        rows = [json.loads(l) for l in io.open(jsonl, encoding="utf-8") if l.strip()]
    except (OSError, ValueError):
        return []
    return [(r.get("rule_code") or r.get("pattern_id"),
             (r.get("legal_signoff") or {}).get("status"),
             (r.get("legal_signoff") or {}).get("signer"))
            for r in rows
            if (r.get("legal_signoff") or {}).get("status") not in (None, "pending")]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--force", action="store_true",
                    help="已有人签过也照重建（**签署区会被清空**，须显式写出来）")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    if a.verify:
        return verify()
    rows, unres = build()
    print("P0 红线法务逐条确认台账 —— 目标 18（PRD §16）")
    print("  待签对象：%d 条 P0 模式" % len(rows))
    for r in rows:
        print("    %-6s %-9s %s" % (r["rule_code"] or r["pattern_id"], r["article_no"],
                                     str(r["match_terms"])[:60]))
    if unres:
        print("  ⚠️ 未决 %d 条（四段溯源缺段，不进台账）：%s"
              % (len(unres), [(u["pattern_id"], u["missing"]) for u in unres]))
    if not a.apply:
        print("\n预演（零写入）。要落盘加 --apply。")
        return 0
    # ★★ 2026-10-12 加：**覆盖写不许静默抹掉人的签字** ────────────────────────────
    #   病灶：`build()` 把 `legal_signoff` **无条件**写成 pending（见它上面那行注释
    #   「签署区：一律留空」）⇒ 一旦法务签过，任何一次重建（补词、改词、换引擎）
    #   都会**静默**把 confirmed 抹回 pending —— 而台账是**签署凭据**，抹掉就是丢证据。
    #   实测此刻 11 条全是 pending ⇒ 这条守卫现在不触发；它守的是"签完之后"。
    #   口径：**默认拒写**；确实要重建得显式 `--force`，并会被打印出来（不静默）。
    _signed = _signed_rows()
    if _signed and not a.force:
        print("\n❌ 拒写：台账里已有 **%d 条非 pending（人签过）**：" % len(_signed))
        for code, status, signer in _signed[:11]:
            print("     %-6s %-10s signer=%s" % (code, status, signer))
        print("   本脚本会把 `legal_signoff` **整体重置为 pending** ⇒ 重建即抹掉签字。")
        print("   要么先备份、要么显式 `--force`（并随后人工补回签署区）。")
        return 3
    if _signed and a.force:
        print("\n⚠️ --force：台账里有 %d 条已签，**签署区将被清空**（本条已打印，不静默）"
              % len(_signed))
    os.makedirs(os.path.dirname(OUT_JSONL), exist_ok=True)
    with io.open(OUT_JSONL, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
    summary = {
        "run_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "target": "18 P0 红线法务逐条确认台账",
        "prd": "§16 风险与依赖 —— 风险「P0 规则误配」→ 应对「P0 规则上线前由法务逐条确认」",
        "entries": len(rows), "unresolved": len(unres), "unresolved_detail": unres,
        "signoff_status": {"pending": len(rows), "confirmed": 0, "rejected": 0},
        "note": "★ 签署区一律留空 —— **本件不替法务签**。待签 %d 条；夹具就绪 ≠ 已确认。" % len(rows),
        "verify_cmd": "python3 kb/l8/build_p0_legal_signoff_ledger.py --verify",
        "how_to_sign": ("逐条把 legal_signoff.status 改成 confirmed/rejected，并填 signer（**具名**，不许写"
                        "「法务团队」）、signed_at、basis（依据法条/内部口径）；例外写 note。"
                        "改完跑 --verify，11/11 且无具名缺失才算落地。"),
    }
    json.dump(summary, io.open(OUT_JSON, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n✅ 台账已落盘：%s（%d 条）" % (os.path.relpath(OUT_JSONL, ROOT), len(rows)))
    print("   摘要：%s" % os.path.relpath(OUT_JSON, ROOT))
    print("   现状：**待签 %d / 已签 0** —— 夹具就绪，签署是人动作" % len(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
