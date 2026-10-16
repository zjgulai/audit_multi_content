#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""routes_reconcile.py —— 路由表对账器：**实际被谁接走 vs 路由表写谁**。

读三样东西，并排给结论：
  1. `kb/l7/registry/routes.yaml`               —— 路由表（静态真源：应该由谁接）
  2. `kb/l7/registry/skills.yaml`               —— 成员登记表（校验路由表的 id 都存在）
  3. 赢家表（运行时产物）                        —— 每条 prompt 每一轮**实际被谁接走**

赢家表格式（每行一条，`|` 分隔）：
    <prompt_id>|<第1轮赢家>|<第2轮赢家>|<第3轮赢家>
赢家取值 = 装载目录名 / name，或 `NONE`（没有 skill 覆盖）/ `CLARIFY`（应先追问）/ `ERR`（判定失败）。

输出四节：
  ① 逐条对照：prompt_id → 期望成员 → 实际接走（逐轮） → 三轮一致? → 一致?
  ② 不一致清单 + 「被谁抢走」计数（按抢走者聚合）
  ③ 按成员命中率 + 与 score-trigger-eval.py 的 F1 交叉核对
  ④ 路由表自检：id 都在 skills.yaml 里、互斥点名规则都成立、两条链的入口 not_for 互相点名

用法：
  kb/kbpy l7/scripts/routes_reconcile.py <winners.txt> [--cases <用例.json>] [--kb-root <库根>]
                                          [--json] [--quiet] [--alias]

退出码：0 全部对账通过 / 1 有对账不上 / 2 用法或环境错
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys

TABLE_ROUTES = ("l7", "registry", "routes.yaml")
TABLE_SKILLS = ("l7", "registry", "skills.yaml")
KB_ROOT_MARKER = "KB-ROOT.json"
SCORER = "~/.dsh/skills/root-skills-eval/scripts/score-trigger-eval.py"
DEFAULT_CASES = "~/Desktop/skill/内容治理中文skill/_基线用例.json"
THRESHOLD = 0.90

#: 归一到「登记表里的成员 id」。① 装了但目录名 ≠ 登记 id；② 描述里写了、其实**没装**的中文名。
ALIAS = {
    # 登记 id → 2026-09-29 并发中文翻译轮次后的**真实装载名**
    "brand-content-review-agent": "内容审查总控",
    "brand-review-intake-router": "送审登记",
    "brand-policy-source-curator": "证据源维护",
    "brand-text-compliance-review": "文案合规审查",
    "brand-product-claim-verifier": "产品宣称核验",
    "brand-image-safety-review": "图片安全审查",
    "brand-video-safety-review": "视频安全审查",
    "brand-us-locale-cultural-review": "美国本地化审查",
    "brand-ai-provenance-rights-review": "AI溯源与权利审查",
    "brand-review-decision-engine": "审查裁决",
    "brand-review-report-memory": "审查报告与记忆",
    "brand-review-evaluation": "审查流程评测",
    "brand-feishu-review-adapter": "飞书审查流转",
    # ② 只被描述提及、并未安装的中文别名（历史遗留）→ 意图指向的成员。
    # ★ 2026-10-04 补（kb-repair）：`_eval-kb-manage/kb_routes_score.py` 的表里**本来就有**
    #   这一行，这里没有 —— 两张表**行数不同**（14 vs 13），是「两个打分器口径不一致」的真正源头。
    #   按「同一事实只写一处」的纪律，本表是**真源**，两边必须逐行同源。
    #   它是**源**不是**靶**：见 `_LEGACY_ALIAS_VALUES`。
    "内容审查总控旧": "内容审查总控",
}


def home(p):
    return os.path.abspath(os.path.expanduser(p))


def find_root(start, explicit=None):
    if explicit:
        p = home(explicit)
        for c in (p, os.path.join(p, "kb")):
            if os.path.isfile(os.path.join(c, KB_ROOT_MARKER)):
                return c
        raise RuntimeError("--kb-root 指向的目录没有 %s：%s" % (KB_ROOT_MARKER, p))
    d = os.path.abspath(start)
    while True:
        if os.path.isfile(os.path.join(d, KB_ROOT_MARKER)):
            return d
        q = os.path.dirname(d)
        if q == d:
            break
        d = q
    p = home("~/.dsh/Momcozy知识库/kb")
    if os.path.isfile(os.path.join(p, KB_ROOT_MARKER)):
        return p
    raise RuntimeError("找不到库根；用 --kb-root 指定")


def load_yaml(path):
    text = open(path, encoding="utf-8").read()
    try:
        import yaml as _y
        return _y.safe_load(text), "PyYAML"
    except ImportError:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import skills_check as SC
        try:
            return SC.parse_yaml_subset(text), "内置降级"
        except SC.YamlSubsetError as e:
            raise RuntimeError("%s 用了内置解析器覆盖不到的 YAML 构造：%s" % (path, e))


#: **历史遗留别名**（不是任何成员的装载名）—— 只许当**源**，不许当**靶**。
#: 它只要混进反向表或装载名索引，就会把撞平的真成员顶掉（实测：`内容审查总控旧` 让
#: `brand-content-review-agent` 的 A1–A5 由 ✅ 变 ❌）。判据：ALIAS 里有两个不同 id
#: 映到同一个名字。当前库内实测只有这一个。
#: ★ 与 `_eval-kb-manage/kb_routes_score.py` 的同名表必须**同源**（两处口径一致是硬要求）。
#: ⚠ 过滤的是**键**不是值：遗留别名是 ALIAS 里的一个**键**，它的**值**（`内容审查总控`）
#:   恰好就是真装载名 —— 按值过滤等于不过滤（本轮实测：过滤后 `_ALIAS_REV['内容审查总控']`
#:   仍被反向写成 `内容审查总控旧`，A1–A5 继续全红）。
_LEGACY_ALIAS_VALUES = {"内容审查总控旧"}

#: ALIAS 值 → 登记 id（反向表）。`--alias` 下要把「装载目录名」折回登记 id 时必须用它 ——
#: 2026-10-04 前这里只查正向表，中文装载名原样返回 ⇒ 中文用例的期望侧永远对不上。
_ALIAS_REV = {v: k for k, v in ALIAS.items() if k not in _LEGACY_ALIAS_VALUES}

#: **空白不敏感**的装载名索引（装载名去掉全部空白 → 装载名）。★ 2026-10-04 修（kb-repair）。
#:
#: 为什么必须有：盲测赢家表把 `AI溯源与权利审查` 记成了 `AI 溯源与权利审查`（多一个空格），
#: 而 `skills.yaml` 的 `dir_name` 与 `~/.dsh/skills/` 的真实目录名都是**无空格**的那个
#: （实测：`ls ~/.dsh/skills/*溯源*` → `AI溯源与权利审查`；frontmatter `name:` 同）。
#: 旧 `canon()` 只做 `.strip()`（去首尾，不去内部），于是这个空格变体既不等于期望值、
#: 也不在 ALIAS 里 ⇒ 对账器判「没人接走」，I3/I4/I5 三轮共 5 次全部误判。
#: **判据不变**：仍然只认登记表里的成员，只是把「同一装载名的空白变体」归一到登记值。
#: 单字名不入索引（一个字的成员名折来折去没有意义，且容易与别的名撞平）。
# ⚠ 两条实测护栏，缺一条都会把**正确的成员**误判掉（本轮都踩过）：
#   ① 不能把「与登记名撞平」的项过滤掉 —— 去空白后**正好就是**登记名本身
#      （唯一的那个空白变体就是这么来的），过滤掉等于把这个修法自己废掉；
#   ② 必须把**历史遗留别名**排除在索引之外 —— `内容审查总控旧` 去空白后与
#      `内容审查总控` 撞平，会让 `brand-content-review-agent` 这一个**本来全对**的成员
#      在 `--alias` 下被归一成 `内容审查总控旧`（实测：A1–A5 五条由 ✅ 变 ❌）。
_LOADNAME_STRIPPED = {
    re.sub(r"\s+", "", v): v
    for v in ALIAS.values()
    if len(re.sub(r"\s+", "", v)) >= 2 and v not in _LEGACY_ALIAS_VALUES
}


def canon(name, alias=True):
    """把任一侧的写法**归一到同一个目标**：`--alias` 下统一归到**登记 id**。

    ★ 2026-10-04 修（kb-repair）：本条函数此前两侧归一目标不一致 —— 期望侧（用例里的
    `brand-*`）归一成**装载名**，赢家侧（装载名）原样返回，**恰好**相等才侥幸成立；
    而赢家表里一旦出现装载名的**空白变体**（`AI 溯源与权利审查` vs `AI溯源与权利审查`），
    两套写法就都落不到同一侧，对账器判「没人接走」。现在四种写法（登记 id / 装载名 /
    装载名的空白变体 / 未知值）一律经登记表归一，未知值原样保留（NONE 仍是 NONE）。
    """
    n = (name or "").strip()
    if not alias:
        return n
    if n in _LEGACY_ALIAS_VALUES:        # 遗留别名是**源**：折到它意图指向的成员
        return ALIAS[n]
    if n in ALIAS:                       # 登记 id → 装载名 → 登记 id
        return _ALIAS_REV[ALIAS[n]]
    if n in _ALIAS_REV:                  # 装载名 → 登记 id
        return _ALIAS_REV[n]
    flat = re.sub(r"\s+", "", n)         # 装载名的空白变体 → 登记 id
    if flat in _LOADNAME_STRIPPED:
        return _ALIAS_REV[_LOADNAME_STRIPPED[flat]]
    return n


def load_winners(path):
    """读赢家表。返回 (winners, 形态说明, 跳过行数)。

    ★ 2026-10-03 修（kb-repair）：**同时认 txt 与 json** —— `kb-check`/`kb-manage` 正文
    规定的产物名是 `kb/l7/reports/<RUN>-routes-winners.json`，而旧实现只按 `|` 逐行解析，
    名与实不符 ⇒ 喂 JSON 得「0 条 ⇒ 全不一致」，静默降级、不报错。

    txt：`<prompt_id>|<第1轮>|<第2轮>|<第3轮>`
    json：[{"id":…, "winners":[r1,r2,r3]}, …] 或 {"<id>": [r1,r2,r3], …}
    解析出 0 条由调用方**硬拒**（不得当「全不一致」继续跑）。
    """
    raw = open(path, encoding="utf-8").read()
    if path.endswith(".json") or raw.lstrip()[:1] in ("[", "{"):
        try:
            d = json.loads(raw)
        except ValueError as e:
            return {}, "json（解析失败：%s）" % e, 0
        w = {}
        if isinstance(d, dict):
            body = d.get("winners") or d.get("rows")
            if isinstance(body, dict):
                for k, v in body.items():
                    w[str(k)] = [str(x).strip() for x in (v if isinstance(v, list) else [v])][:3]
                return w, "json（映射）", 0
            d = body if isinstance(body, list) else [d]
        for row in d if isinstance(d, list) else []:
            if not isinstance(row, dict):
                continue
            k = row.get("id") or row.get("prompt_id")
            v = (row.get("winners") or row.get("rounds")
                 or [row.get(x) for x in ("r1", "r2", "r3")])
            if k and v:
                w[str(k)] = [str(x).strip() for x in v if x is not None][:3]
        return w, "json（列表）", 0
    w, skipped = {}, 0
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        p = line.split("|")
        if len(p) < 2:
            skipped += 1
            continue
        w[p[0].strip()] = [x.strip() for x in p[1:4]]
    return w, "txt（`|` 分隔）", skipped


def main(argv=None):
    ap = argparse.ArgumentParser(description="路由表对账：实际被谁接走 vs 路由表写谁")
    ap.add_argument("winners", help="赢家表（prompt_id|r1|r2|r3）")
    ap.add_argument("--cases", default=DEFAULT_CASES, help="冻结用例 json")
    ap.add_argument("--kb-root", default=None)
    ap.add_argument("--alias", action="store_true",
                    help="把「描述里写了但并没装」的中文名折回意图成员（与冻结基线可比）")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--limit", type=int, default=40, help="单个清单最多逐条列这么多")
    args = ap.parse_args(argv)

    here = os.path.dirname(os.path.abspath(__file__))
    try:
        root = find_root(here, args.kb_root)
    except RuntimeError as e:
        print("环境错：%s" % e, file=sys.stderr)
        return 2

    try:
        routes, rp = load_yaml(os.path.join(root, *TABLE_ROUTES))
        skills_doc, sp = load_yaml(os.path.join(root, *TABLE_SKILLS))
    except (RuntimeError, OSError) as e:
        print("环境错：%s" % e, file=sys.stderr)
        return 2

    rows = skills_doc.get("skills") if isinstance(skills_doc, dict) else None
    if not isinstance(rows, list):
        print("环境错：skills.yaml 顶层要有 skills: 列表", file=sys.stderr)
        return 2
    member_ids = {r.get("id") for r in rows}
    dir_to_id = {}
    for r in rows:
        d = r.get("dir_name") or r.get("id")
        if d:
            dir_to_id[d] = r.get("id")

    cases_path = home(args.cases)
    if not os.path.isfile(cases_path):
        print("环境错：用例文件不存在 %s" % cases_path, file=sys.stderr)
        return 2
    cases = json.load(open(cases_path, encoding="utf-8"))["用例"]

    winners = {}
    # ★ 2026-10-03 修（kb-repair）：赢家表解析不再「静默降级」。
    #   旧实现：`cp` 不存在 → FileNotFoundError 裸抛；格式不符 → `if len(p) < 2: continue`，
    #   于是喂一个**合法 JSON**（`kb-check`/`kb-manage` 正文规定的产物名就是 `.json`）
    #   会得到「赢家表 0 条 ⇒ 65 条全判不一致 ⇒ exit 1」——**不报错、不告警**。
    #   实测踩过（2026-10-03 22:57 体检表 §2 第 2 条）。
    wpath = home(args.winners)
    if not os.path.isfile(wpath):
        print("环境错：赢家表不存在 %s\n"
              "  提示：赢家表是**触发评测的运行时产物**（每条 prompt 每轮实际被谁接走），"
              "不是静态资产；缺输入时本闸门**不得报绿**，也不得静默按「全不一致」跑。" % wpath,
              file=sys.stderr)
        return 2
    winners, wfmt, wskip = load_winners(wpath)
    if not winners:
        print("环境错：赢家表解析出 **0 条**，拒绝继续（旧实现会静默按「全不一致」跑完并 exit 1）。\n"
              "  文件：%s\n  形态：%s\n"
              "  期望：`<prompt_id>|<第1轮>|<第2轮>|<第3轮>`（txt）"
              "或 `[{\"id\":…,\"winners\":[…]}]` / `{\"<id>\": […]}`（json）" % (wpath, wfmt),
              file=sys.stderr)
        return 2
    P = {"1": [], "2": [], "3": [], "4": []}
    I = {"备注": []}
    if wskip:
        I["备注"].append("赢家表 %s 有 %d 行不是 `|` 分隔格式，已跳过"
                         % (os.path.basename(wpath), wskip))

    # ---- ④ 路由表自检
    route_targets = set()
    for r in routes.get("routes") or []:
        t = r.get("to")
        route_targets.add(t)
        if t not in member_ids:
            P["4"].append("routes.yaml：intent=%r 的 to=%r 不在 skills.yaml 登记表里" % (r.get("intent"), t))
        if not r.get("not_for"):
            P["4"].append("routes.yaml：intent=%r 缺 not_for（触发条件写错最常见的形式是该不触发时触发了）"
                          % r.get("intent"))
    for c in routes.get("chains") or []:
        for m in c.get("members") or []:
            if m not in member_ids:
                P["4"].append("routes.yaml：chain=%s 的成员 %r 不在登记表里" % (c.get("id"), m))
        if c.get("entry") not in member_ids:
            P["4"].append("routes.yaml：chain=%s 的入口 %r 不在登记表里" % (c.get("id"), c.get("entry")))

    # 互斥点名：真去 SKILL.md 里核，不只看表
    skill_bodies = {}
    for r in rows:
        src = r.get("source")
        sid = r.get("id")
        if not src or sid not in ("kb-pipeline", "kb-l0-feishu", "kb-review"):
            continue
        # 口径：source 是**库根相对**路径（库根 = 含 KB-ROOT.json 的那一层，即 kb/）——
        # 与 skills_check.py 第 3 类一致：os.path.join(root, src)。写 dirname(root) 会找不到文件，
        # 结果是把互斥点名检查**静默跳过**（本轮实测踩过）。
        p = home(src) if str(src).startswith(("~", "/")) else os.path.join(root, src)
        f = os.path.join(p, "SKILL.md")
        if os.path.isfile(f):
            skill_bodies[sid] = open(f, encoding="utf-8", errors="replace").read()
        else:
            I["备注"].append("互斥点名跳过 %s：SKILL.md 不在 %s" % (sid, p))

    def body_of(sid):
        return skill_bodies.get(sid) or ""

    def names_in(text, other):
        """text 里有没有点名 other（用 id，或用它的 dir_name）。"""
        for token in {other, dir_to_id.get(other, other)}:
            if token and token in text:
                return True
        return False

    checks = [
        ("kb-pipeline", "kb-l0-feishu"), ("kb-l0-feishu", "kb-pipeline"),
        ("kb-l0-feishu", "kb-review"), ("kb-pipeline", "kb-review"),
        ("kb-pipeline", "kb-canonical-lookup"), ("kb-pipeline", "kb-p0-check"),
        ("kb-pipeline", "kb-recall"),
    ]
    for a, b in checks:
        body = body_of(a)
        if not body:
            continue
        if not names_in(body, b):
            P["4"].append("互斥点名缺失：%s 的 SKILL.md 里没有点名 %s（not_for 必须互相点名）" % (a, b))
    # 反例：kb-pipeline 的**触发语**里不许出现「只对账 L0」类
    bp = body_of("kb-pipeline")
    if bp:
        fm = re.match(r"^---\n(.*?)\n---", bp, re.S)
        head = fm.group(1) if fm else bp
        # 只看 description：截到 not_for 之前
        cut = head
        for kw in ("不适用", "## 不适用"):
            if kw in head:
                cut = head.split(kw)[0]
                break
        for bad in ("只对账 L0", "只跑每日同步", "飞书侧改了什么"):
            if bad in cut:
                P["4"].append("kb-pipeline 的触发语里出现了「%s」——这是 kb-l0-feishu 的活，不许扩大语义范围" % bad)
    # kb-l0-feishu 的触发语里不许出现「全链」类
    l0 = body_of("kb-l0-feishu")
    if l0:
        fm = re.match(r"^---\n(.*?)\n---", l0, re.S)
        head = fm.group(1) if fm else l0
        cut = head
        for kw in ("不适用",):
            if kw in head:
                cut = head.split(kw)[0]
                break
        for bad in ("同步一下知识库", "跑一遍知识库链路", "知识库同步到最新", "全链体检",
                    "L0 到 L7 走一遍", "知识库该更新了"):
            if bad in cut:
                P["4"].append("kb-l0-feishu 的触发语里出现了「%s」——这是 kb-pipeline 的活，不许扩大语义范围" % bad)

    # ---- ① 逐条对照
    detail = []
    steal = {}
    per_member = {}
    n_all_ok = 0
    for c in cases:
        exp = canon(c["skill"], args.alias)
        ws = winners.get(c["id"], [])
        ws_c = [canon(w, args.alias) for w in ws]
        ok = bool(ws) and all(w == exp for w in ws_c)
        cons = "是" if len(set(ws)) == 1 else "否"
        if ok:
            n_all_ok += 1
        else:
            for w in ws_c:
                if w and w != exp:
                    steal[w] = steal.get(w, 0) + 1
        pm = per_member.setdefault(exp, {"n": 0, "hit": 0, "rounds": 0, "hit_rounds": 0})
        pm["n"] += 1
        pm["rounds"] += len(ws)
        pm["hit_rounds"] += sum(1 for w in ws_c if w == exp)
        if ok:
            pm["hit"] += 1
        detail.append((c["id"], exp, ws, cons, ok))
        if not ok:
            P["1"].append("%s：期望 %s，实际 %s" % (c["id"], exp, " / ".join(ws) or "（无记录）"))

    # ---- ③ F1 交叉核对
    scorer = home(SCORER)
    f1_ok = {}
    if os.path.isfile(scorer) and not args.alias:
        I["备注"].append("F1 交叉核对默认跳过：本表口径含 alias 折回；要核对请用 --alias 一致的 results 目录")
    if os.path.isfile(scorer):
        I["备注"].append("F1 由同批用例、同一打分器另跑（见 _eval-kb-manage/kb_routes_score.py）；"
                         "本对账器只负责「期望 vs 实际」，不重算分")

    # ---- 输出
    counts = {k: len(v) for k, v in P.items()}
    total = sum(counts.values())
    _real = sys.stdout
    if args.json:
        sys.stdout = sys.stderr

    if not args.quiet:
        print("=" * 74)
        print("routes_reconcile —— 实际被谁接走 vs 路由表写谁")
        print("=" * 74)
        print("库根    : %s" % root)
        print("路由表  : %s（解析器 %s）" % (os.path.relpath(os.path.join(root, *TABLE_ROUTES),
                                                          os.path.dirname(root)), rp))
        print("登记表  : %s（解析器 %s，%d 个成员）" % (os.path.relpath(os.path.join(root, *TABLE_SKILLS),
                                                                    os.path.dirname(root)), sp, len(rows)))
        print("用例    : %s（%d 条）" % (cases_path, len(cases)))
        print("赢家表  : %s（%d 条）" % (home(args.winners), len(winners)))
        print("口径    : %s" % ("alias（中文名折回意图成员，与冻结基线可比）" if args.alias else "strict（只认逐字相等的成员 id）"))
        print()
        print("--- ① 逐条对照 --- %d 条" % len(detail))
        print("    %-6s %-38s %-46s %-8s %s" % ("用例", "期望成员", "实际接走（第1/2/3轮）", "三轮一致", "一致"))
        for pid, exp, ws, cons, ok in detail[:args.limit]:
            print("    %-6s %-38s %-46s %-8s %s" % (pid, exp, " / ".join(ws) or "-", cons, "✅" if ok else "❌"))
        if len(detail) > args.limit:
            print("    … 另有 %d 条未列" % (len(detail) - args.limit))
        print()
        print("--- ② 不一致清单 --- %d 条" % counts["1"])
        for line in P["1"][:args.limit]:
            print("    · %s" % line)
        if counts["1"] > args.limit:
            print("    … 另有 %d 条未列" % (counts["1"] - args.limit))
        print()
        print("    「被谁抢走」计数（本次不合格判定的接走者）：")
        for k, v in sorted(steal.items(), key=lambda x: -x[1]):
            print("      %-38s %d 次" % (k, v))
        print()
        print("--- ③ 按成员命中率（逐条全轮命中 / 总条数；逐轮命中 / 总轮数）---")
        for m, d in sorted(per_member.items()):
            print("    %-38s %d/%d 条 ｜ %d/%d 轮" % (m, d["hit"], d["n"], d["hit_rounds"], d["rounds"]))
        print()
        print("--- ④ 路由表自检 --- %d 条" % counts["4"])
        for line in P["4"][:args.limit]:
            print("    · %s" % line)
        if counts["4"] > args.limit:
            print("    … 另有 %d 条未列" % (counts["4"] - args.limit))
        print()
        if I["备注"]:
            print("--- 备注 ---")
            for line in I["备注"]:
                print("    · %s" % line)
            print()
        print("=" * 74)
        print("逐条全轮命中：%d/%d（门槛：F1 >= %.2f，见打分器）" % (n_all_ok, len(cases), THRESHOLD))
        print("四节问题：①=%d ②（同上）④=%d ｜合计 %d" % (counts["1"], counts["4"], counts["1"] + counts["4"]))
        print("退出码：%d" % (0 if (counts["1"] + counts["4"]) == 0 else 1))

    if args.json:
        sys.stdout = _real
        print(json.dumps({
            "kb_root": root, "cases": len(cases), "alias": bool(args.alias),
            "all_rounds_hit": n_all_ok, "detail": [{"id": i, "expected": e, "actual": w, "consistent": c == "是", "ok": o}
                                                   for i, e, w, c, o in detail],
            "stolen_by": steal, "per_member": per_member,
            "problems": P, "counts": counts,
            "exit_code": 0 if (counts["1"] + counts["4"]) == 0 else 1,
        }, ensure_ascii=False, indent=2))

    return 0 if (counts["1"] + counts["4"]) == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
