#!/usr/bin/env python3
"""报告输出门槛（PRD §5.3.4 / §8.3 / §17）—— **读取的唯一实现**。

## 解决什么

任务拆解 目标 20（PRD §5.3.4 / §8.3）：

> 报告可导出飞书文档或 PDF；**问题数汇总阈值可配置（默认 3）**

改前：`feishu_publish.py:70` 写死 `REPORT_LINK_MIN_ISSUES = 3`。
PRD §5.3.4 原文是「**阈值支持配置**，后续可根据用户反馈调整（**建议保留 3 作为默认值**）」
⇒ **「可配置」这件事本身是 PRD 要求**，写死常量只做到了后半句。

现在：口径落在 `kb/l7/registry/report-threshold-policy.json`，本模块**只负责读**。
**不许在别处再写第二个常量**（与 `confidence_flow` / `content_id` 同一套做法）。

## 三条纪律

1. **读不到就用 PRD 默认值 3，并声明用的是默认值** —— 不许静默。
2. **门槛判定结果要能被下游读走**（`decision()` 返回结构），
   因为守衡侧 `dual_track.mjs` 现在也自己判一次（`REPORT_LINK_MIN_ISSUES = 3`）
   ⇒ 两侧各判一次时，改一侧不同步另一侧会造出**孤儿文档**（建了但没人看得到）。
3. **不改判定语义** —— 本模块只是把「3」从常量搬到政策文件；PRD 的口径一个字没动。

## 用法

    python3 kb/l7/review-engine/core/report_threshold.py --selftest   # 判据自证（不碰真库）
    python3 kb/l7/review-engine/core/report_threshold.py --show       # 打印当前生效口径与出处
"""

from __future__ import annotations

import argparse
import json
import os
import sys

#: PRD §5.3.4 的默认值。**它就是 3，不是别的** —— 依据见 policy 的 `prd_ref.why_3`。
PRD_DEFAULT_MIN_ISSUES = 3

#: 政策文件落点：`<kb>/l7/registry/report-threshold-policy.json`。
#: 本文件在 `<kb>/l7/review-engine/core/` ⇒ 从 `__file__` 往上退 **4** 层到 `<kb>`。
#: ⚠️ `confidence_flow` 首版就是这里退错了一层（多退/少退），导致「读政策」是假的。
#:   所以本模块**由判据 ⑨ 守着**：真政策文件必须读得到（读不到就红）。
POLICY_REL = ("l7", "registry", "report-threshold-policy.json")


def policy_path() -> str:
    kb = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))))
    return os.path.join(kb, *POLICY_REL)


def load(path: str | None = None) -> dict:
    """读政策。返回 `{min_issues, source, from_policy_file, note}`。"""
    p = path or policy_path()
    try:
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
        v = (d.get("thresholds") or {}).get("report_link_min_issues")
        if isinstance(v, int) and v >= 0:
            return {"min_issues": v, "source": p, "from_policy_file": True, "note": None}
        return {"min_issues": PRD_DEFAULT_MIN_ISSUES, "source": p, "from_policy_file": False,
                "note": "政策文件里 report_link_min_issues 不是非负整数（得到 %r）⇒ 用 PRD 默认值" % v}
    except Exception as e:                                        # noqa: BLE001
        return {"min_issues": PRD_DEFAULT_MIN_ISSUES, "source": p, "from_policy_file": False,
                "note": "政策文件读不到（%s）⇒ 用 PRD §5.3.4 默认值" % e}


def min_issues(path: str | None = None) -> int:
    """只要那个数。"""
    return int(load(path)["min_issues"])


def decision(n_issues, path: str | None = None) -> dict:
    """PRD §5.3.4 / §8.3 的分档判定。**纯函数**，不改任何东西。

    返回 `{required, n_issues, emitted, min_issues, source, from_policy_file, output_form, why}`。

    * `required` —— 是否应**生成报告并给链接**（`n_issues >= min_issues`）
    * `output_form` —— `"summary_with_link"` 或 `"itemized"`
    * `emitted` —— **实际有没有出**（本函数不知道建文档成功没，故此时等于 `required`；
      调用方建完文档后应把它改写成真实结果，别把「应出」当「已出」）
    """
    n = int(n_issues or 0)
    l = load(path)
    m = l["min_issues"]
    required = n >= m
    return {
        "required": required,
        "emitted": required,          # 见 docstring：这不是「已出」，是「应出」的初值
        "n_issues": n,
        "min_issues": m,
        "source": l["source"],
        "from_policy_file": l["from_policy_file"],
        "policy_note": l["note"],
        "output_form": "summary_with_link" if required else "itemized",
        "why": ("PRD §5.3.2/§5.3.3/§8.3/§17：问题数量 ≥ %d 时只出分类汇总 + 报告链接" % m)
               if required else
               ("PRD §5.3.2/§5.3.3：问题数量 1-%d 个时逐条输出，不给链接" % max(m - 1, 0)),
    }


# ══════════════════════════════════════════════════════════════════
# 判据自证（不碰真库；政策路径可注入）
# ══════════════════════════════════════════════════════════════════

def _selftest() -> int:
    ok = fail = 0
    fails: list[str] = []

    def ck(name, cond, detail=""):
        nonlocal ok, fail
        if cond:
            ok += 1
        else:
            fail += 1
            fails.append("%s %s" % (name, detail))

    import tempfile, os as _os

    def write_policy(v):
        fd, p = tempfile.mkstemp(suffix=".json")
        _os.close(fd)
        with open(p, "w", encoding="utf-8") as f:
            json.dump({"thresholds": {"report_link_min_issues": v}}, f)
        return p

    # ①a–c 边界（**边界值本身要判对**：n == min ⇒ 出链接）
    p3 = write_policy(3)
    ck("①a 3>=3 出链接", decision(3, p3)["required"] is True)
    ck("①b 2<3 不出", decision(2, p3)["required"] is False)
    ck("①c 0<3 不出", decision(0, p3)["required"] is False)
    ck("①d 99>=3 出", decision(99, p3)["required"] is True)

    # ②a–b ★ 阈值**真能改**（PRD §5.3.4「阈值支持配置」）——本条的判据
    p1 = write_policy(1)
    ck("②a 改成 1 后 1 条就出", decision(1, p1)["required"] is True
       and decision(0, p1)["required"] is False, "得到 %r" % decision(1, p1))
    p5 = write_policy(5)
    ck("②b 改成 5 后 4 条不出", decision(4, p5)["required"] is False
       and decision(5, p5)["required"] is True)
    # ②c 变异对照：把阈值硬编码回 3 ⇒ ②a/②b 必须红（下面断言 ②a 已覆盖；此处自证"改得动"）
    ck("②c 阈值随政策变", decision(1, p1)["min_issues"] == 1
       and decision(5, p3)["min_issues"] == 3, "阈值没跟着政策走")
    for p in (p3, p1, p5):
        _os.unlink(p)

    # ③ 输出形态与依据文案
    d3 = decision(3, p3 if _os.path.exists(p3) else write_policy(3))
    ck("③a 形态=汇总+链接", d3["output_form"] == "summary_with_link", d3["output_form"])
    ck("③b 依据引 PRD", "PRD" in d3["why"], d3["why"])
    p3b = write_policy(3)
    d2 = decision(2, p3b)
    ck("③c 1-2 条=逐条", d2["output_form"] == "itemized", d2["output_form"])
    ck("③d 逐条依据引 PRD", "PRD" in d2["why"], d2["why"])
    _os.unlink(p3b)

    # ④ ★ 读不到政策 ⇒ 用 PRD 默认值**并声明**
    lp = load("/nonexistent/report-threshold-policy.json")
    ck("④a 兜底=3", lp["min_issues"] == 3, lp["min_issues"])
    ck("④b 兜底可辨认", lp["from_policy_file"] is False and lp["note"], "得到 %r" % lp)

    # ⑤ ★ **真政策文件必须读得到** —— 守「可配置」不是空话（同 confidence_flow ⑨）
    lr = load()
    ck("⑤a 真政策读到了", lr["from_policy_file"] is True, "读不到：%s" % lr["note"])
    ck("⑤b 路径指向 kb/l7/registry",
       policy_path().endswith("kb/l7/registry/report-threshold-policy.json"), policy_path())
    ck("⑤c 默认值 = PRD §5.3.4 的 3", lr["min_issues"] == PRD_DEFAULT_MIN_ISSUES,
       "得到 %r" % lr["min_issues"])

    # ⑥ ★ `emitted` 不许被当成「已出」的既成事实 —— 它是「应出」的初值
    dd = decision(5)
    ck("⑥ emitted 初值=required", dd["emitted"] == dd["required"], "得到 %r" % dd["emitted"])
    ck("⑥b 调用方须改写（字段在位）", "emitted" in dd and "required" in dd, list(dd))

    print("report_threshold --selftest：%d/%d" % (ok, ok + fail))
    for f in fails:
        print("  ✗", f)
    return 0 if fail == 0 else 1


def _show() -> int:
    l = load()
    print("报告链接门槛 = %d" % l["min_issues"])
    print("  出处：%s" % l["source"])
    print("  来自政策文件：%s" % l["from_policy_file"])
    if l["note"]:
        print("  ⚠ %s" % l["note"])
    print("  依据：PRD §5.3.4「阈值支持配置…建议保留 3 作为默认值」/ §8.3 / §17")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="报告输出门槛（PRD §5.3.4 / §8.3）")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--show", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return _selftest()
    if a.show:
        return _show()
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
