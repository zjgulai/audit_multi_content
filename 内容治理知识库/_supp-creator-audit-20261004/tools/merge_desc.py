#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把主线的**现役** description 机械改写成 creator 公式形态 —— **逐字保留它的每一句**。

背景（为什么不能拿旧稿覆盖）：
  主线在 2026-10-04 21:31 改过 description 内容（新增「导出手机号身份证 / 只翻译已抽正文 /
  只审字幕」等负例类别，并加「★以下优先于上面的触发词」优先标记）。我 17:20 的旧稿**没有**这些，
  直接覆盖 = 把它的工作回退掉。⇒ 本工具以**主线现役文本为唯一底本**，只做结构重排。

只做三件事（其余一字不动）：
  ① 把含「时使用」的那一句**提到最前**（creator 清单④：第一句描述触发时机，而非功能列表）；
     若该句不以「当用户」开头，则补「当用户」前缀使其成为触发句式。
  ② 在末尾补一行字面 `触发词：…`（creator 公式三大件之一）；关键词**从它自己的「」列表里取**，
     不新增、不改写。
  ③ 「★以下优先于上面的触发词，一律不加载」块与「判归：」块 **逐字保留**，位置不动。

用法：python3 merge_desc.py [--write]
"""
import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SUPP = os.path.dirname(HERE)
WS = os.path.dirname(SUPP)
FIX = os.path.join(WS, "_eval-L1L7-gap-20261004", "fix")

SKILLS = ["kb-ingest-extractor", "kb-media-extractor", "kb-clause-extractor",
          "kb-canonical-lookup", "kb-p0-check", "kb-recall", "kb-check"]

MAXLEN = 500


def front_and_body(txt):
    m = re.match(r"^---\n(.*?)\n---\n", txt, re.S)
    if not m:
        raise SystemExit("!! 没有 frontmatter")
    return m.group(1), txt[m.end():]


def get_desc(fm):
    lines = fm.split("\n")
    out, on = [], False
    for ln in lines:
        if re.match(r"^description:", ln):
            on = True
            rest = ln.split(":", 1)[1].strip()
            if rest and rest not in ("|", ">", "|-", ">-"):
                out.append(rest)
            continue
        if on:
            if re.match(r"^[A-Za-z_][\w-]*:", ln):
                break
            out.append(ln)
    return "\n".join(out)


def norm(d):
    return " ".join(d.split())


def split_parts(d):
    """→ (func, trig, neg, route)  四段；neg / route 逐字保留。"""
    i_star = d.find("★")
    i_route = d.find("判归：")
    head = d[:i_star].strip() if i_star >= 0 else d.strip()
    neg = ""
    route = ""
    if i_star >= 0:
        end = i_route if i_route > i_star else len(d)
        neg = d[i_star:end].strip()
    if i_route >= 0:
        route = d[i_route:].strip()
    # head 里切出含「时使用」的那一句及其后续（读取条件常跟在它后面）
    sents = re.findall(r"[^。]*。|[^。]+$", head)
    sents = [s for s in sents if s.strip()]
    ti = None
    for i, s in enumerate(sents):
        if "时使用" in s and "「" in s:
            ti = i
            break
    if ti is None:                      # 找不到就原样返回，fail-visible
        return head, "", neg, route
    func = "".join(sents[:ti]).strip()
    trig = "".join(sents[ti:]).strip()
    return func, trig, neg, route


def split_trigger_list(trig, keep=3):
    """把触发句里那份「A/B/C/…」列表**一分为二**：前 keep 个留在句子里，其余搬进 `触发词：` 行。

    为什么这么做（而不是另起一份触发词）：主线描述已 482–494，没有余量再塞一整行；
    硬塞只能塞进 1 个词 → 「有名无实」；而**删触发词**会重演 L0 v1.2.5 的教训（删词把正例变 FN）。
    ⇒ 只是**把同一批词在两个公式件之间挪位**，一个词都不丢，净增仅 `触发词：` 4 个字符。
    """
    quoted = re.findall(r"「([^」]+)」", trig)
    if not quoted:
        return trig, ""
    first = quoted[0]
    items = [x.strip() for x in first.split("/") if x.strip()]
    if len(items) <= keep:
        return trig, ""
    head, tail = items[:keep], items[keep:]
    new_sent = trig.replace("「" + first + "」", "「" + "/".join(head) + "」", 1)
    line = "触发词：" + "、".join(tail) + "。"
    return new_sent, line


def merge(d, skill):
    d = norm(d)
    func, trig, neg, route = split_parts(d)
    if not trig:
        return None, "找不到触发句"
    if not trig.startswith("当用户"):
        trig = "当用户" + trig
    rest = ([func] if func else []) + ([neg] if neg else []) + ([route] if route else [])
    # 逐档试 keep：先少留（触发词行更长），不行再多留，直到放得下为止。
    # 目的是**尽量补上 `触发词：` 这一件**，但绝不为了它删词。
    for keep in (3, 4, 5, 6, 8, 10):
        t2, tl = split_trigger_list(trig, keep=keep)
        if not tl:
            continue
        body = " ".join([t2] + rest + [tl])
        if len(body) <= MAXLEN:
            return body, "ok"
    # 一档都放不下 ⇒ 退回原句子形态（一个词都不删），并**如实标注未补**
    body = " ".join([trig] + rest)
    return body, ("ok·未补触发词行" if len(body) <= MAXLEN else "超窗")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--out", default=os.path.join(SUPP, "out", "merged-desc.json"))
    a = ap.parse_args()
    res, report = {}, []
    for s in SKILLS:
        p = os.path.join(FIX, s, "SKILL.md")
        fm, _b = front_and_body(open(p, encoding="utf-8").read())
        old = norm(get_desc(fm))
        new, status = merge(old, s)
        if new is None:
            report.append((s, len(old), 0, "★" + status, 0, 0))
            continue
        # 保真核对：新串必须包含旧串的 ★块与判归块（逐字）
        _, _, neg, route = split_parts(old)
        ok_neg = (neg in new) if neg else True
        ok_route = (route in new) if route else True
        res[s] = new
        report.append((s, len(old), len(new), status, int(ok_neg), int(ok_route)))
    print(f"{'skill':<22}{'原折叠':>6}{'新折叠':>6}  {'状态':<8}{'★块保留':<9}{'判归保留':<9}")
    for s, a_, b_, st, n1, n2 in report:
        print(f"{s:<22}{a_:>6}{b_:>6}  {st:<8}{'是' if n1 else '★否':<9}{'是' if n2 else '★否':<9}")
    if a.write:
        json.dump(res, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"\n写出 → {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
