#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_report_link_validity.py —— 目标 15 后半：报告链接到底**能不能打开**。

## 出处（逐字）

· 任务拆解 10/12–10/16 行 **目标 15**：`【补·PRD §8.3】报告生成 ≤30 秒、链接有效期 ≥30 天。`
· 同表交付物 15：`报告生成时延与链接有效期实测`
· PRD §12「记录」行逐字：`所有审查记录保存 ≥ 1 年；报告链接有效期 ≥ 30 天。`
· PRD §15 验收：三态结论须「附维度标注、原因和**文档链接**」；
  §9 要求报告链接送达 法务／医学／专家／北美／sign-off／内容提交方。

## 实测到的真相（2026-10-10，只读）

**前半 ≤30 秒已达标**：`kb/l7/reports/perf-latest.md` 实测 **0.164 s**（P0 判定＋生成报告）。

**后半卡在更前面一层** —— 不是"能活多久"，是"**能不能打开**"：

| 实测项 | 结果 |
|---|---|
| `drive permission.public get` 读报告云文档 | `link_share_entity = **closed**`（3/4 份实测；第 4 份取不到，另计） |
| 发布件加不加协作者 | **不加**（`feishu_publish.py` 里 `member-add`/`collaborator` **0 命中**） |
| 权限模型里有没有"有效期"字段 | **没有**（`permission_public` 的键里无 expire 类字段） |

⇒ **「有效期 ≥30 天」这句话在本库现有链路上无法直接核**：有效期是对"一个能打开的链接"说的；
  而 `link_share_entity=closed` ＋ 不加协作者 ⇒ **非协作者点开即无权访问** ⇒ **前提不成立**。

## 本判据怎么处置这条（**不曲解 PRD，也不假装达标**）

把「链接有效期 ≥30 天」**拆成它真正可核的两问**，逐问给结论：

1. **链接可打开吗**（`link_share_entity != closed`）—— 这一问**机器可核**，本件就是它；
2. **≥30 天** —— 平台侧**无字段可核** ⇒ 本件**不给数字**，如实标 `not_measurable`，
   **不许用"飞书文档默认不过期"当证明**（那是常识推断，不是实测）。

## 用法

    python3 kb/l8/check_report_link_validity.py             # 只读：核最近几份报告的真实链接设置
    python3 kb/l8/check_report_link_validity.py --selftest  # 自证（纯夹具，不联网）
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
KB = os.path.dirname(HERE)
ROOT = os.path.dirname(KB)
RECEIPTS = os.path.join(KB, "l7/reports")
LARK = os.environ.get("LARK_BIN", "lark-cli")
PROFILE = os.environ.get("L8_PROFILE", "dsh-kb")

#: `link_share_entity` 取值 → 链接能不能被非协作者打开。
#: ★ 只登记**闭合不可用**的那一个：其余取值即便名称各异，也是"链接分享已开"这一侧。
CLOSED = "closed"


def judge_link(perm):
    """纯函数：拿 `permission_public` 字典判「报告链接能不能打开」。

    返回 (ok, verdict, why)。**这是本件唯一的判据，`--selftest` 直接喂夹具验它。**
    """
    if not isinstance(perm, dict) or not perm:
        return False, "no_reading", "读不到权限设置 ⇒ **判不了**（不许当成合格）"
    ent = perm.get("link_share_entity")
    if ent is None:
        return False, "no_field", "权限设置里**没有** link_share_entity ⇒ 判不了，不许推定"
    if str(ent).strip().lower() == CLOSED:
        return False, "closed", ("link_share_entity=%s ⇒ **仅协作者可访问**；"
                                 "而发布件不加协作者 ⇒ 非协作者点开即无权访问" % ent)
    return True, "open", "link_share_entity=%s ⇒ 链接分享已开" % ent


def doc_tokens(limit=6):
    """从发布回执里取报告云文档 token（**不猜、不编**：只取真出现过的）。"""
    toks = []
    if not os.path.isdir(RECEIPTS):
        return toks
    for fn in sorted(os.listdir(RECEIPTS), reverse=True):
        p = os.path.join(RECEIPTS, fn)
        if not os.path.isfile(p) or os.path.getsize(p) > 4_000_000:
            continue
        try:
            txt = io.open(p, encoding="utf-8", errors="ignore").read()
        except Exception:                                    # noqa: BLE001
            continue
        for m in re.findall(r"https://momcozy-in\.feishu\.cn/docx/([A-Za-z0-9]+)", txt):
            if m not in toks:
                toks.append(m)
        if len(toks) >= limit:
            break
    return toks[:limit]


def fetch_perm(tok, as_id="bot"):
    p = subprocess.run([LARK, "drive", "permission.public", "get", "--token", tok,
                        "--type", "docx", "--as", as_id, "--profile", PROFILE, "--json"],
                       capture_output=True, text=True)
    if p.returncode != 0:
        return None, (p.stderr or p.stdout or "").strip()[:160]
    try:
        d = json.loads(p.stdout[p.stdout.find("{"):])
    except Exception as e:                                   # noqa: BLE001
        return None, "解析失败 %r" % (e,)
    return ((d.get("data") or {}).get("permission_public")), None


def run():
    toks = doc_tokens()
    print("报告链接可打开性核验 —— 目标 15 后半（PRD §12「报告链接有效期 ≥ 30 天」）")
    print("★ 本判据只核**可核的那一半**（链接能不能打开）；「≥30 天」平台无字段 ⇒ 标 not_measurable，不给数字。\n")
    if not toks:
        print("没找到报告云文档 token（发布回执里没有）⇒ 判不了，不许推定。")
        return 2
    rows, bad = [], []
    for t in toks:
        perm, err = fetch_perm(t)
        ok, verdict, why = judge_link(perm)
        rows.append({"token": t, "ok": ok, "verdict": verdict, "why": why,
                     "link_share_entity": (perm or {}).get("link_share_entity"), "error": err})
        print("  %s docx/%s ｜ %-10s ｜ %s" % ("✅" if ok else "❌", t, verdict,
                                              why if not err else (why + "（错误：%s）" % err)))
        if not ok:
            bad.append(t)
    print("\n可见性：可打开 %d / 共 %d" % (len(rows) - len(bad), len(rows)))
    print("≥30 天：**not_measurable** —— 飞书 `permission_public` 无有效期字段；"
          "不许拿「文档默认不过期」当证明（那是常识推断）")
    print("结论：%s" % ("✅ 报告链接对非协作者可打开" if not bad else
                       "❌ %d/%d 份报告链接 **link_share_entity=closed** ⇒ 非协作者打不开；"
                       "PRD §9/§15 要求链接送达法务/医学/sign-off/提交方 ⇒ **不成立**"
                       % (len(bad), len(rows))))
    return 0 if not bad else 3


def selftest():
    res = []

    def ck(n, c, ex=""):
        res.append((n, bool(c), ex))

    ok, v, _ = judge_link({"link_share_entity": "closed"})
    ck("① 正向：link_share_entity=closed ⇒ 判不可用", (not ok) and v == "closed", v)
    ok2, v2, _ = judge_link({"link_share_entity": "tenant_readable"})
    ck("② 反向对照：非 closed ⇒ 判可用（判据不是恒假）", ok2 and v2 == "open", v2)
    ok3, v3, _ = judge_link({})
    ck("③ 反向对照：空设置 ⇒ 判「读不到」而不是「合格」", (not ok3) and v3 == "no_reading", v3)
    ok4, v4, _ = judge_link({"security_entity": "anyone_can_edit"})
    ck("④ 反向对照：**没有该字段** ⇒ 判不了，不许推定可用", (not ok4) and v4 == "no_field", v4)
    ok5, v5, e5 = judge_link(None)
    ck("⑤ 反向对照：None ⇒ 判不了（不许抛异常也不许算过）", (not ok5) and v5 == "no_reading", v5)
    # ⑥ 变异测试：把真实现的「closed ⇒ 不可用」拆掉（当作可用）⇒ ① 必须精确变红
    _orig = CLOSED
    globals()["CLOSED"] = "__never_matches__"
    ok6, v6, _ = judge_link({"link_share_entity": "closed"})
    ck("⑥ 变异测试：拆掉 closed 判据 ⇒ ① 精确变红（判成 open）", ok6 and v6 == "open", v6)
    globals()["CLOSED"] = _orig
    ok7, v7, _ = judge_link({"link_share_entity": "closed"})
    ck("⑦ 还原后 ① 恢复", (not ok7) and v7 == "closed", v7)
    print("check_report_link_validity --selftest（目标 15 后半）")
    for n, c, ex in res:
        print("  %s %s%s" % ("✅" if c else "❌", n, ("　｜ " + ex) if ex else ""))
    bad = sum(1 for _, c, _e in res if not c)
    print("结果：%d/%d%s" % (len(res) - bad, len(res), "" if not bad else "  ← 有失败"))
    return 1 if bad else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    sys.exit(selftest() if a.selftest else run())
