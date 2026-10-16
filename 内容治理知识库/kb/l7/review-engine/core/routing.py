"""routing.py —— 按**问题方向**把 REVIEW 转给对应专业团队（PRD §9 / §5.3.2）。

## 这件事原先错在哪（Owner 2026-10-14 报）

PRD §5.3.2 **两处**（1-2 条与 ≥3 条）逐字都写：

    建议转 @法务 @医学顾问 复核。

§9 写「REVIEW 自动转**对应**专业团队（法务、医学、专家、北美）」。
而库里发出去的是 `建议转 @内容治理负责人 复核。` —— 一个**硬编码常量**：
收件人不在那四个团队里，且**不随问题方向变**。

## 路由从哪来

`kb/l7/review-engine/knowledge-base/routing-policy.json`（`status: confirmed_by_user`）。
本模块是它的消费者之一（另一处是守衡的 `tools/agent/routing.mjs`）——
**读它、不抄它**：词表改了，路由跟着变。

## 边界（写清楚，别让它比输入大）

- 只按方向词匹配，不判问题真假、不定三态。
- 匹配只吃 `category` / `risk_type` 这类**方向字段**，**不吃 `reason`**：
  原因句里常出现「不得宣称**医疗**功效」这种**在解释别人的违规**的措辞，
  拿它当方向会把一条广告用语问题路由成医学问题。
- 读不到路由表 ⇒ 回落 `fallback`（再读不到就 PRD §5.3.2 那一对），**不编别的**。
- **不给句柄编人名**：句柄只从 `kb/l7/registry/l7.json` 的 `approvers` 取
  （句柄的读取与渲染在 `review_engine._at`，那里是唯一口径）。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

_HERE = Path(__file__).resolve().parent          # …/kb/l7/review-engine/core
_POLICY_PATH = _HERE.parent / "knowledge-base" / "routing-policy.json"

#: 读不到路由表时的落点 —— PRD §5.3.2 示例里逐字给出的那一对。
PRD_DEFAULT_OWNERS = ["法务", "医学顾问"]

#: 方向字段的候选键（顺序即优先级；**不含 reason**，见模块头边界第 2 条）。
_DIRECTION_KEYS = ("category", "risk_type", "risk_category", "dimension")


def load_policy(path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """读路由表；任何异常都当作**没读到**（判据是「拿到的东西」，不是「文件在不在」）。"""
    try:
        raw = json.loads(Path(path or _POLICY_PATH).read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(raw, dict):
        return None
    rules = [r for r in (raw.get("rules") or [])
             if isinstance(r, dict) and isinstance(r.get("match"), list)
             and isinstance(r.get("owners"), list)]
    fallback = [x for x in (raw.get("fallback_review_owners") or [])
                if isinstance(x, str) and x.strip()]
    return {
        "version": raw.get("routing_version") if isinstance(raw.get("routing_version"), str) else None,
        "roles": raw.get("roles") if isinstance(raw.get("roles"), dict) else {},
        "rules": rules,
        "fallback": fallback,
    }


def direction_of(finding: Any) -> str:
    """一条 finding 的**方向字段**拼串（不含 reason）。"""
    if not isinstance(finding, dict):
        return ""
    return " ".join(str(finding.get(k) or "") for k in _DIRECTION_KEYS).strip()


def owners_for(findings: Iterable[Any], policy: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """按方向算出该转谁。**不抛**：拿不到路由表就回落 PRD 默认。

    命中用子串判断（路由表里的词是「医疗 / 功效 / 睡眠」这类中文词干，不是正则）。
    命中即取该条 ``owners`` 并**停止**（rules 有次序：医疗 → 产品 → 背书 → 本地）。

    返回 ``{"owners": [...], "by_rule": [...], "unmatched": N, "source": str, "version": str|None}``。
    ``owners`` 按**首次出现次序**去重（PRD §9 的并列次序要保住）。
    """
    items = [f for f in (findings or []) if isinstance(f, dict)]
    p = policy if isinstance(policy, dict) else None
    fallback = (p or {}).get("fallback") or PRD_DEFAULT_OWNERS
    rules = (p or {}).get("rules") or []

    owners: List[str] = []
    by_rule: List[int] = []
    unmatched = 0
    for f in items:
        d = direction_of(f)
        hit = -1
        if d:
            for i, r in enumerate(rules):
                if any(isinstance(w, str) and w and w in d for w in r["match"]):
                    hit = i
                    break
        by_rule.append(hit)
        if hit < 0:
            unmatched += 1
        for o in (fallback if hit < 0 else rules[hit]["owners"]):
            if isinstance(o, str) and o.strip() and o not in owners:
                owners.append(o)

    return {
        "owners": owners,
        "by_rule": by_rule,
        "unmatched": unmatched,
        "source": ("no_findings" if not items else
                   ("routing_policy" if p else "prd_default")),
        "version": (p or {}).get("version"),
    }


def review_action_line(findings: Iterable[Any], at, policy: Optional[Dict[str, Any]] = None) -> str:
    """渲染 PRD §5.3 那句收尾动作行。

    ``at`` 是**句柄渲染器**（`review_engine._at`）—— 句柄口径只有那一处，
    本函数不自己读 `l7.json`，避免出现第二份口径。

    口径三条：① 收件人 = 按方向算出来的；② 句柄由 ``at`` 决定
    （没配就「角色名（未配置）」）；③ 有未匹配到方向的条目就**如实标出**。

    ★ 空清单（**库侧覆盖缺口那一支恒为空**）⇒ 落 `fallback`，**绝不输出空的收件人**：
      `建议转  复核。` 是一句没有宾语的话，比转错人更没用。
    """
    items = [f for f in (findings or []) if isinstance(f, dict)]
    r = owners_for(items, policy if policy is not None else load_policy())
    owners = r["owners"]
    if not owners:
        # 没有任何条目可路由（含空清单）⇒ 与「读不到路由表」同一个答案：fallback
        pol = policy if policy is not None else load_policy()
        owners = (pol or {}).get("fallback") or PRD_DEFAULT_OWNERS
    who = " ".join(at(o) for o in owners)
    gap = ""
    if items and r["unmatched"] > 0:
        gap = "（其中 %d/%d 条未匹配到方向：该转谁需要人确认）" % (r["unmatched"], len(items))
    return "建议转 %s 复核。%s" % (who, gap)
