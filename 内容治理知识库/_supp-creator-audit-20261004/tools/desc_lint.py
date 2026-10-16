#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""description 格式合规 lint —— 只读，不改任何 skill。

检查两项**互不相同**的规范，二者不可互相替代：

  A. 宿主生效面（机制硬约束）
     宿主 @deepseek-ai/dsh-tool-skill/lib/index.js
       :18  DEFAULT_CATALOG_DESCRIPTION_MAX_LENGTH = 500
       :338 value.replaceAll(/\\s+/g, " ").trim()
       :339 normalized.slice(0, maxLength - 3) + "..."
     ⇒ 折叠空白后的**前 500 字**才是路由器看得见的；**`**` 加粗标记计入长度**（每对 4 字符）。

  B. 家族格式（root-skills-creator，只参照、不改其本体）
     references/cso-optimization.md「description 公式」：
       [功能描述]。当用户[触发条件1/2/3]时使用。触发词：[关键词…]。
     检查清单 5 条：第三人称 / 只写 WHEN / 含具体触发词 / 覆盖 3+ 种表达 / 写明不适用场景
     references/pre-launch-checklist.md 第 4 项：
       第一句描述**触发时机**（中文等效「当用户…时使用」），而非功能列表；关键触发词前置

  ★ 本器**只报不改**，也不给分——分数归 root-skills-eval 的 track_a，本器只提供可核事实。
"""
import argparse
import os
import re
import sys

MAXLEN = 500
TRIGGER_HEAD = re.compile(r"^\s*当用户|^\s*当\s*你|^\s*Use when|^\s*Load when")
FUNC_HEAD = re.compile(r"^\s*(把|对|用于|本 skill|Momcozy|知识库|L\d|[A-Za-z])")
XMLTAG = re.compile(r"</?[a-zA-Z][\w:-]*\s*/?>")
SECOND_PERSON = re.compile(r"你可以|你能|你需要|your |you can", re.I)


def extract_desc(path):
    """取 frontmatter 里的 description 块（含 `|` 块标量）。"""
    txt = open(path, encoding="utf-8").read()
    m = re.match(r"^---\n(.*?)\n---\n", txt, re.S)
    if not m:
        return None
    lines = m.group(1).split("\n")
    out, on = [], False
    for ln in lines:
        if re.match(r"^description:", ln):
            rest = ln.split(":", 1)[1].strip()
            on = True
            if rest and rest not in ("|", ">", "|-", ">-"):
                out.append(rest)
            continue
        if on:
            if re.match(r"^[A-Za-z_][\w-]*:", ln):
                break
            out.append(ln)
    return "\n".join(out) if out else None


def norm(d):
    return " ".join(d.split())


def lint(path, label=None):
    d = extract_desc(path)
    name = label or os.path.basename(os.path.dirname(os.path.abspath(path)))
    if d is None:
        return {"skill": name, "error": "取不到 description"}
    flat = norm(d)
    r = {"skill": name, "folded": len(flat), "visible": min(len(flat), MAXLEN - 3) if len(flat) > MAXLEN else len(flat)}
    r["over_window"] = len(flat) > MAXLEN

    # 规则单元可见性：按 、；。 切句，首现位置 ≥ 可见区即不可见
    cut = r["visible"]
    units, pos, seen = [], 0, set()
    for u in re.split(r"[、；。]", flat):
        if not u.strip():
            continue
        i = flat.find(u, pos)
        if i < 0:
            i = flat.find(u)
        pos = max(pos, i + len(u))
        if u not in seen:
            seen.add(u)
            if i >= cut:
                units.append(u.strip()[:40])
    r["invisible_units"] = units

    # 家族格式检查
    first = re.split(r"[。；]", flat)[0] if flat else ""
    r["first_sentence"] = first[:50]
    r["first_is_trigger"] = bool(TRIGGER_HEAD.match(first))
    r["has_trigger_kw_block"] = "触发词：" in flat or "触发词:" in flat
    r["has_when"] = bool(re.search(r"当用户|时使用", flat))
    r["third_person"] = not bool(SECOND_PERSON.search(flat))
    r["has_xml_tag"] = bool(XMLTAG.search(flat))
    # ★ 边界要求可由两种写法之一满足，二者**等效**（creator skill-design-boundaries「Description 边界」
    #   与 cso-optimization 的「正确示范」都接受）：
    #   ① 场景式「不适用：<场景>」；② **正向判归句**「某类请求归 kb-xxx」。
    #   ⇒ 只写判归句**不算**缺项，不得据此报缺陷（避免制造伪缺陷）。
    r["has_not_applicable"] = bool(re.search(r"不适用|不处理|不负责", flat))
    r["has_route"] = bool(re.search(r"归\s*kb-|→\s*kb-|走\s*kb-", flat))
    r["has_boundary"] = r["has_not_applicable"] or r["has_route"]
    r["has_undefined_rule"] = bool(re.search(r"追问|欠定|别加载|不加载", flat))
    r["has_safety_rule"] = bool(re.search(r"rm -rf|破坏|越权|--apply|清空", flat))
    r["has_no_handle_x"] = bool(re.search(r"本 skill 不处理|本 skill 不负责", flat))
    # 覆盖 3+ 种表达：数「」内或 / 分隔的候选说法
    quoted = re.findall(r"[「『][^」』]{1,40}[」』]", flat)
    slashed = [x for x in re.split(r"[/／]", flat) if 2 <= len(x.strip()) <= 24]
    r["n_phrasings"] = max(len(quoted), len(slashed))
    return r


def verdict(r):
    """只输出「符合/不符合」，不打分。"""
    bad = []
    if r.get("error"):
        return ["取不到 description"]
    if not r["first_is_trigger"]:
        bad.append("首句非触发句式（creator 清单④）")
    if not r["has_trigger_kw_block"]:
        bad.append("无「触发词：」块（creator 公式）")
    if not r["has_boundary"]:
        bad.append("未写边界（既无场景式「不适用」，也无正向判归句）")
    if not r["third_person"]:
        bad.append("非第三人称")
    if r["has_xml_tag"]:
        bad.append("含 XML 标签")
    if r["n_phrasings"] < 3:
        bad.append(f"表达方式不足 3 种（实测 {r['n_phrasings']}）")
    if r["over_window"]:
        bad.append(f"折叠后 {r['folded']} > 500，路由器只看得到前 497 字")
    return bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    rows = []
    for p in a.paths:
        f = p if p.endswith("SKILL.md") else os.path.join(p, "SKILL.md")
        rows.append(lint(f))
    if a.json:
        import json
        print(json.dumps(rows, ensure_ascii=False, indent=1))
        return 0
    print(f"{'skill':<24}{'折叠':>5}{'超窗':>5} {'首句触发':<9}{'触发词块':<9}{'边界':<7}{'说法数':>6} {'不可见单元':>10}")
    for r in rows:
        if r.get("error"):
            print(f"{r['skill']:<24}  {r['error']}")
            continue
        print(f"{r['skill']:<24}{r['folded']:>5}{('是' if r['over_window'] else '否'):>5} "
              f"{('是' if r['first_is_trigger'] else '★否'):<9}"
              f"{('是' if r['has_trigger_kw_block'] else '★否'):<9}"
              f"{('是' if r['has_boundary'] else '★否'):<7}"
              f"{r['n_phrasings']:>6} {len(r['invisible_units']):>10}")
    print()
    for r in rows:
        bad = verdict(r)
        if bad:
            print(f"[{r['skill']}] 不符合：")
            for b in bad:
                print(f"    · {b}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
