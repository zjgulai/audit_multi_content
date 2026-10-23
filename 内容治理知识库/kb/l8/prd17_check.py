#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""**PRD §17 结论模版字数限制** —— 知识库侧的同一把尺。

真源只有一份：`kb/l7/registry/prd17-limits.yaml`
（取自飞书 PRD §17 内嵌表 `sheet XWnpiN`，rev 96，2026-10-19 拉取）。
守衡侧读同一个文件（`tools/agent/prd17.mjs`）—— **两仓共用一张表，不许各写一份**。

为什么有这个脚本（Owner 2026-10-19）：
    「prd 中 17 写了的结论模版字数限制，你同步知识库了吗？」
在那之前，字数限制**只活在 PRD 里**，代码从不量它 —— 实测量出来：
    BLOCK ≥3 那张卡 112 字（上限 100）、REVIEW 1-2 285 字（上限 200），
**没有任何东西会红**。这就是「散文没有失败信号」的又一例。

用法
    kb/kbpy l8/prd17_check.py --selftest
    kb/kbpy l8/prd17_check.py --state BLOCK --issues 6 --text-file /tmp/card.txt
    echo '…卡面文本…' | kb/kbpy l8/prd17_check.py --state REVIEW --issues 2

口径（`counting.rule`）是**解释**不是 PRD 原文（PRD 只写「≤N 字」）：
默认 `visible_no_url` —— 去掉链接与 markdown 标记、去空白后数字符。
理由：一条 docx 链接 ≈55 字符，数进去等于让「≥3 ≤100 字」在任何实现下都不可能满足。

★ 2026-10-19 Owner 再裁一条：「**「链接那行不计入字数」，同意**」——
  只剩标签的链接行**整行不计**（`counting.exclude_link_line`，三条排除条件见真源 `counting` 段）。
  这不是「含链接就免」：依据行也含链接，但它剥掉链接后仍有 35 字 ⇒ 照旧计入。
  改口径只改 registry 一处，**守衡 `tools/agent/prd17.mjs` 同步生效**（两仓共读同一真源）。
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REGISTRY = Path(__file__).resolve().parent.parent / "l7" / "registry" / "prd17-limits.yaml"


def _load_raw() -> str:
    if not REGISTRY.is_file():
        raise SystemExit(f"[prd17] 找不到真源：{REGISTRY}")
    return REGISTRY.read_text(encoding="utf-8")


def limits() -> dict:
    """读真源。**读不到就抛**，绝不静默兜底（兜底会把「没读进来」伪装成「都合规」）。"""
    raw = _load_raw()
    try:
        import yaml  # noqa: PLC0415
        data = yaml.safe_load(raw) or {}
        rows = [r for r in (data.get("rows") or []) if r.get("limit") is not None]
        counting = data.get("counting") or {}
        revision = (data.get("meta") or {}).get("revision")
    except Exception:                                    # noqa: BLE001 —— 无 PyYAML 时走行内解析
        rows, counting, revision = [], {}, None
        for line in raw.splitlines():
            m = re.match(r"^\s*-\s*\{(.+)\}\s*$", line)
            if m:
                obj = {}
                for part in re.split(r",\s*(?=[A-Za-z_][\w-]*:)", m.group(1)):
                    kv = re.match(r"^\s*([A-Za-z_][\w-]*):\s*(.*)$", part)
                    if not kv:
                        continue
                    v = kv.group(2).strip().strip("'\"")
                    obj[kv.group(1)] = int(v) if v.isdigit() else v
                if "state" in obj and "limit" in obj:
                    rows.append(obj)
        counting = {
            "rule": "visible_no_url",
            "strip_urls": bool(re.search(r"strip_urls:\s*true", raw)),
            "strip_markdown": bool(re.search(r"strip_markdown:\s*true", raw)),
            "strip_whitespace": bool(re.search(r"strip_whitespace:\s*true", raw)),
            "exclude_link_line": bool(re.search(r"exclude_link_line:\s*true", raw)),
        }
        m = re.search(r"link_line_label_max:\s*(\d+)", raw)
        if m:
            counting["link_line_label_max"] = int(m.group(1))
        m = re.search(r"link_line_markers:\s*\[([^\]]*)\]", raw)
        if m:
            counting["link_line_markers"] = [x.strip().strip("'\"") for x in m.group(1).split(",") if x.strip()]
        m = re.search(r"^\s*revision:\s*(\d+)", raw, re.M)
        revision = int(m.group(1)) if m else None
    if not rows:
        raise SystemExit(f"[prd17] {REGISTRY} 里没有解析出任何上限行")
    return {"rows": rows, "counting": counting, "revision": revision, "path": str(REGISTRY)}


def range_of(n: int) -> str:
    return "≥3" if int(n) >= 3 else "1-2条"


def scope_of(state: str, issues: int):
    """这一档量什么：`format` 含「逐条」⇒ per_item（每条各自判）；否则 ⇒ message（整条消息）。

    Owner 2026-10-19：「最后的字数限制是针对每一条问题」＋「下面两个写了逐条，没写的就是整张卡」。
    """
    st = str(state or "").upper()
    rng = range_of(issues)
    for r in limits()["rows"]:
        if str(r.get("state", "")).upper() != st:
            continue
        if r.get("issue_range") in ("任意", "—", rng):
            return "per_item" if "逐条" in str(r.get("format", "")) else "message"
    return None


def limit_of(state: str, issues: int):
    st = str(state or "").upper()
    rng = range_of(issues)
    for r in limits()["rows"]:
        if str(r.get("state", "")).upper() != st:
            continue
        if r.get("issue_range") in ("任意", "—", rng):
            return int(r["limit"])
    return None


def _visible(s: str, c: dict) -> str:
    """按口径算「可见字」：剥链接 → 剥 markdown 标记 → 去空白。

    ★ 全脚本**只有这一处**能定义「什么算一个字」；`count_chars` 与「链接行排除」的
      门槛判定都调它 —— 两处各写一套是这条尺子最容易分叉的地方。
    """
    t = str(s or "")
    if c.get("strip_urls", True):
        t = re.sub(r"\[([^\]\n]*)\]\((?:https?:)?[^)\s]*\)", r"\1", t)   # markdown 链接只留可见文字
        t = re.sub(r"https?://[^\s)）]+", "", t)
    if c.get("strip_markdown", True):
        t = re.sub(r"[*`>|【】→#]", "", t)
    if c.get("strip_whitespace", True):
        t = re.sub(r"\s+", "", t)
    return t


LINK_LINE_DEFAULT_MAX = 20
LINK_LINE_DEFAULT_MARKERS = ("【", "结论")


def split_link_lines(text: str, counting: dict | None = None) -> dict:
    """把卡面拆成「计入的行」与「整行排除的链接行」，并挑出 hazard。

    排除条件**三条同时成立**（真源 `prd17-limits.yaml::counting`，理由写在那里，别在代码里另说一套）：
      ① 该行含 `http(s)://`；
      ② 剥掉链接后可见字数 **≤ `link_line_label_max`**（默认 20）—— 这一行只剩标签；
      ③ 该行不含 `link_line_markers`（默认 `['【', '结论']`）里的结论标记。

    ★ ②③ 是故意收紧的，两条都别删：
      · F1 的**依据行**也含链接，剥后仍剩 35 字 ⇒ 不排除。改成「含链接就整行免」会把
        一条 30+ 字的依据凭空抹掉 —— 那是放宽「依据必须给出」，不是放宽字数。
      · 结论行带内联链接（`【审查结论：BLOCK】… 详见 https://…`）⇒ ③ 命中 ⇒ **不排除**，
        并记进 `hazards`（fail-closed：宁可多数，不可漏数）。
    """
    c = counting or limits()["counting"]
    if not c.get("exclude_link_line", False):
        return {"kept": str(text or ""), "excluded": [], "hazards": [], "enabled": False}
    try:
        mx = int(c.get("link_line_label_max") or LINK_LINE_DEFAULT_MAX)
    except (TypeError, ValueError):
        mx = LINK_LINE_DEFAULT_MAX
    marks = tuple(c.get("link_line_markers") or LINK_LINE_DEFAULT_MARKERS)
    kept: list[str] = []
    excluded: list[str] = []
    hazards: list[str] = []
    for ln in str(text or "").splitlines():
        if re.search(r"https?://", ln) and len(_visible(ln, c)) <= mx:
            if any(k in ln for k in marks):
                hazards.append(ln.strip())
                kept.append(ln)
            else:
                excluded.append(ln.strip())
            continue
        kept.append(ln)
    return {"kept": "\n".join(kept), "excluded": excluded, "hazards": hazards, "enabled": True}


def count_chars(text: str, counting: dict | None = None) -> int:
    c = counting or limits()["counting"]
    return len(_visible(split_link_lines(text, c)["kept"], c))


def check(state: str, issues: int, text: str) -> dict:
    lim = limit_of(state, issues)
    c = limits()["counting"]
    sp = split_link_lines(text, c)
    chars = len(_visible(sp["kept"], c))
    out = {
        "state": str(state or "").upper(),
        "issue_range": range_of(issues),
        "limit": lim,
        "chars": chars,
        "over": max(0, chars - lim) if lim is not None else 0,
        "ok": (chars <= lim) if lim is not None else None,
        "rule": limits()["counting"].get("rule"),
        "revision": limits()["revision"],
        # ★ 口径可见：免得「字数忽然变小了」变成没法解释的读数（不静默）
        "link_lines_excluded": len(sp["excluded"]),
        "link_chars_excluded": sum(len(_visible(x, c)) for x in sp["excluded"]),
        "link_line_hazards": list(sp["hazards"]),
    }
    return out


def check_items(state: str, issues: int, item_texts) -> dict:
    """**逐条量**（与守衡 `checkItems` 同一口径）。

    Owner 2026-10-19：「字数限制是针对**每一条问题**」＋「写了逐条的就按条」。
    覆盖三行：`SUGGEST 任意`（≤150/条）、`REVIEW 1-2条`、`BLOCK 1-2条`（各 ≤200/条）。
    """
    lst = list(item_texts or [])
    per = [dict(index=i + 1, **check(state, issues, t)) for i, t in enumerate(lst)]
    lim = per[0]["limit"] if per else limit_of(state, issues)
    over = sum(1 for r in per if r["ok"] is False)
    return {
        "per_item": per,
        "max": max((r["chars"] for r in per), default=0),
        "over_count": over,
        "limit": lim,
        "ok": None if lim is None else (over == 0),
        "scope": "item",
        "rule": limits()["counting"].get("rule"),
        "revision": limits()["revision"],
    }


def reading(state: str, issues: int, text: str) -> str:
    r = check(state, issues, text)
    if r["limit"] is None:
        return f"PRD §17：{r['state']} 无此档（不判）"
    tail = "（✅ 合规）" if r["ok"] else f"（❌ 超 **{r['over']}** 字）"
    extra = ""
    if r["link_lines_excluded"]:
        extra = f"｜已排除链接行 {r['link_lines_excluded']} 行（−{r['link_chars_excluded']} 字）"
    if r["link_line_hazards"]:
        extra += f"｜⚠️ hazard {len(r['link_line_hazards'])} 行（链接与结论同行，**未排除**）"
    return (f"PRD §17：{r['state']} {r['issue_range']} 实测 **{r['chars']}** 字 / "
            f"上限 **{r['limit']}**{tail}｜口径 {r['rule']}"
            f"（sheet XWnpiN rev {r['revision']}）{extra}")


# ── 自证 ────────────────────────────────────────────────────────────────────────
def selftest() -> int:
    bad: list[str] = []

    def eq(name: str, got, want) -> None:
        if got != want:
            bad.append(f"{name} —— 期望 {want!r}，实得 {got!r}")
            print(f"  ❌ {name}")
        else:
            print(f"  ✅ {name}")

    print("=== PRD §17 字数限制（知识库侧）自证 ===")
    L = limits()
    eq("① 上限表 6 行，取值与 PRD §17 逐字一致",
       sorted(f"{r['state']}/{r['issue_range']}={r['limit']}" for r in L["rows"]),
       sorted(["PASS/—=50", "SUGGEST/任意=150", "REVIEW/1-2条=200",
               "REVIEW/≥3=100", "BLOCK/1-2条=200", "BLOCK/≥3=100"]))
    eq("①b 真源带版本（可回溯到 sheet rev）", isinstance(L["revision"], int), True)
    eq("② 3 条走 ≥3 档（BLOCK 100）", limit_of("BLOCK", 3), 100)
    eq("②b 2 条走 1-2 档（BLOCK 200）", limit_of("BLOCK", 2), 200)
    eq("②c PRD 有但本库未启用的 SUGGEST 也能取（150）", limit_of("SUGGEST", 1), 150)
    # ★ 口径改名说明（2026-10-19）：本行原写 `count_chars("完整清单：https://x.y/z") == count_chars("完整清单：")`
    #   —— 在「链接那行整行不计入」生效后，整行被排除（两边变成 0 vs 5），那条断言自然会红。
    #   它要守的是**「URL 字符本身不占字数」**，与「整行免」是两件事 ⇒ 改用一条不会触发整行排除的长行来量。
    eq("③ URL 字符本身不计入字数（剥链接，不是靠整行免）",
       count_chars("甲" * 30 + "https://x.y/z"), count_chars("甲" * 30))
    eq("③b markdown 标记不计入", count_chars("**原因**：甲"), count_chars("原因：甲"))
    eq("③c 空白与换行不计入", count_chars("甲\n\n乙"), 2)
    # ── 链接那一行整行不计入（Owner 2026-10-19：「「链接那行不计入字数」，同意」；C1 的处置）──
    CARD = "【审查结论：BLOCK】共发现 5 处必须修改。\n· 甲类：2 个\n· 乙类：1 个\n" \
           "→ 完整清单：https://x.y/z\n请修改后重新提交。"
    eq("③d 纯链接行整行不计入（连行首标签一起不数）",
       count_chars(CARD),
       count_chars("【审查结论：BLOCK】共发现 5 处必须修改。\n· 甲类：2 个\n· 乙类：1 个\n请修改后重新提交。"))
    eq("③d2 且读数报出「排除了几行、少了几个字」（不静默）",
       [check("BLOCK", 5, CARD)["link_lines_excluded"], check("BLOCK", 5, CARD)["link_chars_excluded"]],
       [1, 5])                                    # `完整清单：` = 5 个可见字（`→` 已被 markdown 口径剥掉）
    # ★ 反向对照：同一行标签加长到超 link_line_label_max ⇒ **重新计入**
    LONG_LABEL = "→ " + "完整问题清单与修改建议请点这里查看" * 2 + "：https://x.y/z"
    eq("③e 反向对照：标签超 20 字 ⇒ 该行**重新计入**（门槛是 label_max，不是「含链接就免」）",
       count_chars(LONG_LABEL) > 20, True)
    # ★★ 关键反向对照：依据行含链接、剥后仍 >20 字 ⇒ 照旧计入（不许把「依据」免掉）
    BASIS = "**依据**：《外部标准库 v0（试用版，未发布）》第 E-2.124 条（链接：https://x.y/z）"
    eq("③f 依据行含链接但剥后 >20 字 ⇒ **照旧计入**（放宽的是链接标签行，不是「依据必须给出」）",
       count_chars(BASIS) > 20, True)
    # ★★ fail-closed：结论行带内联链接 ⇒ 不排除，且报 hazard
    INLINE = "【审查结论：BLOCK】详见 https://x.y/z"
    r_in = check("BLOCK", 5, INLINE)
    eq("③g 结论行带内联链接 ⇒ **不排除** ＋ 报 hazard（宁可多数，不可漏数）",
       [r_in["link_lines_excluded"], r_in["link_line_hazards"] != [],
        r_in["chars"] == count_chars("【审查结论：BLOCK】详见")], [0, True, True])
    # ★ 开关真起作用：关掉 ⇒ 链接行重新计入（证明上面几条不是恒真）
    c_off = dict(limits()["counting"])
    c_off["exclude_link_line"] = False
    eq("③h 关掉开关 ⇒ 链接行重新计入", count_chars(CARD, c_off) > count_chars(CARD), True)
    # ★ 门槛就是真源那个数：把 label_max 压到 4 ⇒ 5 字的标签行**不再**被排除
    c_tight = dict(limits()["counting"])
    c_tight["link_line_label_max"] = 4
    eq("③i 把 label_max 压到 4 ⇒ 5 字标签行不再排除（读的是真源，不是写死的 20）",
       count_chars(CARD, c_tight) > count_chars(CARD), True)
    lim = limit_of("BLOCK", 3)
    eq("④ 恰好等于上限 ⇒ 合规", check("BLOCK", 3, "字" * lim)["ok"], True)
    eq("④b 上限 +1 ⇒ 超 1 字", check("BLOCK", 3, "字" * (lim + 1))["over"], 1)
    # ★ 反向对照：同一段字换成 1-2 档（200）⇒ 不再超（证明它读的是**档位**，不是常数）
    eq("④c 反向对照：同一段字在 1-2 档（200）⇒ 不超", check("BLOCK", 2, "字" * (lim + 1))["ok"], True)
    # ★ 反向对照：51 字在 PASS(50) 超、在 SUGGEST(150) 不超
    eq("④d 反向对照：51 字 PASS 超、SUGGEST 不超",
       [check("PASS", 1, "字" * 51)["ok"], check("SUGGEST", 1, "字" * 51)["ok"]], [False, True])
    # ★★ Owner 2026-10-19 的规则：「输出格式里写了逐条 ⇒ 按条量；没写的 ⇒ 整张卡」
    eq("⑥ 档位：逐条的两行按条量、其余按整卡量",
       [scope_of("BLOCK", 2), scope_of("REVIEW", 1), scope_of("BLOCK", 3),
        scope_of("REVIEW", 6), scope_of("PASS", 0), scope_of("SUGGEST", 2)],
       ["per_item", "per_item", "message", "message", "message", "per_item"])
    # ★ Owner 补充：「逐条的还有 SUGGEST（≤150 字/条）」
    sug = check_items("SUGGEST", 2, ["建议把「最好」改为具体表述。" * 3, "建议补上数据来源与统计口径。"])
    eq("⑦ SUGGEST 也按条量、上限 150", [sug["scope"], sug["limit"], sug["over_count"]], ["item", 150, 0])
    # 反向对照：其中一条加长到超 150 ⇒ 必须翻红，且只报那一条
    sug2 = check_items("SUGGEST", 2, ["建议把「最好」改为具体表述。" * 12, "建议补上数据来源与统计口径。"])
    eq("⑦b 反向对照：把第 1 条加长 ⇒ 只报那一条超",
       [sug2["over_count"], sug2["ok"], sug2["per_item"][1]["ok"]], [1, False, True])
    eq("⑤ 不存在的状态 ⇒ 不判（limit/ok 都为 None）",
       [check("NEEDS_INPUT", 1, "字")["limit"], check("NEEDS_INPUT", 1, "字")["ok"]], [None, None])
    print(f"\n自证：通过 {len(bad) == 0 and 'all' or '—'} / 失败 {len(bad)}")
    for b in bad:
        print(f"   ❌ {b}")
    return 1 if bad else 0


def main() -> int:
    ap = argparse.ArgumentParser(description="PRD §17 结论模版字数限制（知识库侧同一把尺）")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--state", help="PASS / SUGGEST / REVIEW / BLOCK")
    ap.add_argument("--issues", type=int, help="问题数（决定 1-2条 / ≥3 档）")
    ap.add_argument("--text-file", help="卡面文本文件；不给就读 stdin")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    if not a.state or a.issues is None:
        ap.error("--state 与 --issues 必填（或用 --selftest）")
    text = Path(a.text_file).read_text(encoding="utf-8") if a.text_file else sys.stdin.read()
    r = check(a.state, a.issues, text)
    print(reading(a.state, a.issues, text))
    return 0 if (r["ok"] is not False) else 3


if __name__ == "__main__":
    sys.exit(main())
