#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_record_retention.py —— PRD §12「**所有审查记录保存 ≥ 1 年**」。

## 出处（逐字）

· PRD §12 非功能需求 →「记录」行：`所有审查记录保存 ≥ 1 年`；`报告链接有效期 ≥ 30 天`。
· 任务拆解 11/23–11/27 行目标 7 逐字：
  `（PRD §12）「所有审查记录保存 ≥ 1 年」作为验收项（链接有效期 ≥30 天已单列）。
   （PRD 明确要求、此前全表无落点；Owner 2026-10-10 令自下周排期起执行，不加工时）`

## ★ 本件**不许**说"已达标"（这条最要紧）

库里最早的审查记录是 **2026-10-08**（`AD-20261008-001`）—— **没有任何一条记录活满一年**。
⇒ 「保存 ≥1 年」**现在在物理上无法被证明**。本件给的**不是**达标结论，是三样**可核的东西**：

1. **现账**：审查记录散在哪几处、各多少条、最早/最晚是哪天、跨度多少天（**现算，不抄**）；
2. **保留承诺表**：每条存放路径**由谁保证不清**、依据是什么、**哪几条根本没有保证**；
3. **可证明的那一天**：`最早记录日 + 365 天` —— 到那天之前，这条**只能是 `cannot_prove_yet`**。

⇒ 拿"机制在"冒充"事实在"是本库最忌的一类错；本件把两者分开写。

## 用法

    python3 kb/l8/check_record_retention.py            # 只读核验
    python3 kb/l8/check_record_retention.py --selftest
"""
from __future__ import annotations

import argparse
import datetime as _dt
import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
KB = os.path.dirname(HERE)
ROOT = os.path.dirname(KB)

#: 审查记录的存放路径 → 保留承诺。`guarantee` 为空 = **没有保证**（必须明写，不许留白）。
PLACES = [
    {"id": "local_runs", "path": "kb/l7/runs", "what": "评审链逐单运行记录（含四段溯源）",
     "guarantee": "本库自持；**无自动清理**（`_archive` 只增不删），随工作区备份",
     "owner": "本库"},
    {"id": "local_reports", "path": "kb/l7/reports", "what": "评审报告（本地 md ＋ 发布回执 json）",
     "guarantee": "本库自持；**无自动清理**", "owner": "本库"},
    {"id": "feishu_table", "path": None, "what": "飞书结论去向表 `tblCXPQVzfFWWCon` 的审查行",
     "guarantee": "**取决于飞书侧租户保留策略 —— 本库读得到、改不了**（要人去飞书核）",
     "owner": "飞书侧（人的动作）"},
    {"id": "feishu_doc", "path": None, "what": "飞书报告云文档（链接有效期见另一判据）",
     "guarantee": "文档不自动过期；**删除权在文档所有者** —— 未见清理动作",
     "owner": "飞书侧"},
]

#: ★ 日期抽取必须**带边界**：`(?<!\d)…(?!\d)` 挡住"嵌在长数字里"的假日期。
#:   我第一版没加，实测把报告正文里一串数字抠成 `2058-03-10`，
#:   于是「跨度 11505 天」——**判据自己被脏输入喂出了假账**。宁可取不到，不许取错。
DAY_RE = re.compile(r"(?<!\d)(20\d{2})[-_/]?(\d{2})[-_/]?(\d{2})(?!\d)")
TODAY_CAP = None   #: 晚于"今天"的日期一律丢弃（报告里出现的未来年份是文本，不是记录日期）


def _dates_in(text, cap=None):
    """从文本里取**合法的、不晚于 cap** 的日期。取不到就返回空 —— **不许猜**。"""
    cap = cap or _dt.date.today()
    out = []
    for m in DAY_RE.finditer(text or ""):
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if not (1 <= mo <= 12 and 1 <= d <= 31):
            continue
        try:
            dt = _dt.date(y, mo, d)
        except ValueError:
            continue
        if dt > cap:                      # 未来日期 = 文本里的数字，不是记录日期
            continue
        out.append(dt)
    return out


def scan(kb=KB):
    """现算各存放处的条数与日期跨度。**日期只从文件名/内容里真取到才算**，取不到就不算。"""
    rows = []
    for pl in PLACES:
        if not pl["path"]:
            rows.append({**pl, "count": None, "earliest": None, "latest": None, "span_days": None})
            continue
        d = os.path.join(kb, pl["path"].split("kb/", 1)[1])
        ds, n = [], 0
        if os.path.isdir(d):
            for fn in os.listdir(d):
                p = os.path.join(d, fn)
                if not os.path.isfile(p):
                    continue
                n += 1
                got = _dates_in(fn)          # ★ 优先且**只信文件名**（约定 `rv-YYYYMMDD-HHMMSS`）
                if not got:
                    continue                 # 文件名没有日期 ⇒ **不计入账**，不去正文里抠
                ds.extend(got)
        ds = sorted(set(ds))
        rows.append({**pl, "count": n,
                     "earliest": ds[0].isoformat() if ds else None,
                     "latest": ds[-1].isoformat() if ds else None,
                     "span_days": (ds[-1] - ds[0]).days if len(ds) > 1 else (0 if ds else None)})
    return rows


def verdict(rows, today=None):
    """纯函数：给现账 ⇒ 结论。**过不了一年就绝不说达标。**"""
    today = today or _dt.date.today()
    e = [r["earliest"] for r in rows if r.get("earliest")]
    if not e:
        return {"state": "no_reading", "why": "一处都没取到日期 ⇒ **判不了**（不许当达标）"}
    earliest = min(e)
    d0 = _dt.date.fromisoformat(earliest)
    age = (today - d0).days
    provable_on = (d0 + _dt.timedelta(days=365)).isoformat()
    unguaranteed = [r["id"] for r in rows if r.get("guarantee") and "改不了" in r["guarantee"]]
    if age >= 365:
        return {"state": "pass", "why": "最早记录 %s，已满 %d 天 ⇒ 事实可证" % (earliest, age),
                "earliest": earliest, "age_days": age, "provable_on": provable_on,
                "unguaranteed": unguaranteed}
    return {"state": "cannot_prove_yet",
            "why": ("最早记录 %s，距今仅 **%d 天** ⇒ **物理上不可能证明「≥1 年」**。"
                    "到 **%s** 才可能证明。" % (earliest, age, provable_on)),
            "earliest": earliest, "age_days": age, "provable_on": provable_on,
            "unguaranteed": unguaranteed}


def run():
    print("PRD §12「所有审查记录保存 ≥ 1 年」—— 落点核验")
    print("★ 本件给的是**现账 + 保留承诺 + 可证明的那一天**，**不是**达标结论。\n")
    rows = scan()
    for r in rows:
        print("  · %-14s %s" % (r["id"], r["what"]))
        print("      条数 %s ｜ 最早 %s ｜ 最晚 %s ｜ 跨度 %s 天"
              % (r["count"], r["earliest"] or "—", r["latest"] or "—", r["span_days"]))
        print("      保留承诺：%s" % r["guarantee"])
    v = verdict(rows)
    print("\n结论：**%s**" % v["state"])
    print("  %s" % v["why"])
    if v.get("unguaranteed"):
        print("  ⚠️ **本库改不了保留策略的存放处**：%s ⇒ 要人去飞书核（本库只能读）"
              % ", ".join(v["unguaranteed"]))
    print("\n★ 边界：本判据在最早记录满 365 天之前**恒为 `cannot_prove_yet`**，"
          "这是**如实**，不是缺陷。")
    return 0 if v["state"] == "pass" else 3


def selftest():
    res = []

    def ck(n, c, ex=""):
        res.append((n, bool(c), ex))

    import tempfile
    import shutil
    tmp = tempfile.mkdtemp(prefix="ret-")
    os.makedirs(os.path.join(tmp, "l7/runs"), exist_ok=True)
    for d in ("2025-01-01", "2026-10-08"):
        io.open(os.path.join(tmp, "l7/runs", "rv-%s.json" % d), "w").write("{}")
    rows = scan(kb=tmp)
    ck("① 现算：取到 2 条、最早 2025-01-01", rows[0]["count"] == 2 and rows[0]["earliest"] == "2025-01-01",
       "%s / %s" % (rows[0]["count"], rows[0]["earliest"]))
    v = verdict(rows, today=_dt.date(2026, 10, 10))
    ck("② 跨过 365 天 ⇒ 判 pass（判据不是恒 cannot_prove_yet）", v["state"] == "pass", v["state"])
    # ★ 反向对照：**只有几天 ⇒ 绝不许说达标**
    tmp2 = tempfile.mkdtemp(prefix="ret2-")
    os.makedirs(os.path.join(tmp2, "l7/runs"), exist_ok=True)
    io.open(os.path.join(tmp2, "l7/runs", "rv-2026-10-08.json"), "w").write("{}")
    v2 = verdict(scan(kb=tmp2), today=_dt.date(2026, 10, 10))
    ck("③ 反向对照：只有 2 天 ⇒ `cannot_prove_yet`（**不许拿机制冒充事实**）",
       v2["state"] == "cannot_prove_yet", v2["state"])
    ck("③b 且给出可证明的那一天 = 最早+365", v2["provable_on"] == "2027-10-08", v2.get("provable_on"))
    # ★ 反向对照：一处日期都没有 ⇒ no_reading，不许当达标
    tmp3 = tempfile.mkdtemp(prefix="ret3-")
    os.makedirs(os.path.join(tmp3, "l7/runs"), exist_ok=True)
    io.open(os.path.join(tmp3, "l7/runs", "no-date-here.json"), "w").write("{}")
    v3 = verdict(scan(kb=tmp3), today=_dt.date(2026, 10, 10))
    ck("④ 反向对照：取不到日期 ⇒ no_reading（不许当达标）", v3["state"] == "no_reading", v3["state"])
    for t in (tmp, tmp2, tmp3):
        shutil.rmtree(t, ignore_errors=True)
    print("check_record_retention --selftest（PRD §12 记录行）")
    for n, c, ex in res:
        print("  %s %s%s" % ("✅" if c else "❌", n, ("　｜ " + str(ex)) if ex else ""))
    bad = sum(1 for _, c, _e in res if not c)
    print("结果：%d/%d%s" % (len(res) - bad, len(res), "" if not bad else "  ← 有失败"))
    return 1 if bad else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    sys.exit(selftest() if a.selftest else run())
