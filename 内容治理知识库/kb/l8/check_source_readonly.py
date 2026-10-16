#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_source_readonly.py —— 判据：飞书侧「只读源」没被写，且这条规则没从 AGENTS.md 掉出去。

## 这条判据守的是什么

Owner 2026-10-10 定的两条规则（逐字见 `kb/l7/registry/source-readonly.yaml` 文件头）：

  ① 飞书侧**两个源只读**：入口 Base 的表「材料收集」、wiki 上的「内容审查 Agent PRD」；
  ② 飞书权限问题的**取值身份**：守衡（bot）主、用户身份回落；错误要分流报。

规则同时写进了 `~/.dsh/AGENTS.md`（每次会话注入 ⇒ 下次不用再问一遍）。

## 为什么还要一把尺子

**散文没有失败信号。** 本库栽过「判据成了注释」：规矩写在文档里、看着像守着，
可一旦有人（或下一个 agent）在活代码里加一条 `base +record-batch-update` 指向源表，
**没有任何东西会红** —— 而飞书源表是**别人的生产数据**，写错一次没有回滚。

`~/.dsh/AGENTS.md` 的漂移检查器（`check_agents_md_drift.py`）自己写着纪律：
**只检可机械验证的断言、不碰散文**。所以这两条规则各需要一个机械可核的形式：

  · **不许写** → 扫活代码里的写动词，看目标是不是只读源（本脚本 C3/C5）；
  · **别掉了** → 核 AGENTS.md 里那几句还能被命令核的话在不在（本脚本 C2）；
  · **别被写回任务单** → 扫任务拆解/工单类文档，不许出现「写飞书源表」的指令（本脚本 C6）。
    加这一条是因为 2026-10-10 那件事的**病根在文档**：任务拆解里一句
    「3 份 Brief 照 PRD §2.2 直接改（分类→其它、状态→暂不采用）」，被照着执行了 3 条写入。
    **代码闸门看不见文档**，所以文档要自己有一条。

## 判定口径（fail-closed）

对 `lark-cli base|docs|wiki` 的子命令走**只读白名单**：
**凡不在白名单里的一律按写对待**。宁可多报，不可漏报 ——
将来飞书加一个新的写子命令，**不需要改这把尺子**。

## 边界（★ 照实说，别外推）

  · **只扫活代码**（`.py/.mjs/.js/.sh`，且排除 `_`/`.` 开头的段与 `.bak`）。
    **不扫 `.md`/`.yaml`** —— 它们是散文与登记件，本来就含写命令原文。
    ⇒ 代价照实说：**人手从 runbook 里抄一条命令去打源表，这条尺子管不住。**
  · 本件**只读**：不调飞书、不写库、不认领，秒级。
  · 它证明的是「**没有已知的写路径**」，不是「飞书侧权限配得对」——
    后者是 `watch_review_readiness.py` 的活儿。

## 用法

    python3 kb/l8/check_source_readonly.py            # 人读；全绿退 0，任一红退 3
    python3 kb/l8/check_source_readonly.py --json     # 机读
    python3 kb/l8/check_source_readonly.py --selftest # 只跑反向对照（证明判据不是恒真）
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))                 # 库根
REGISTRY = os.path.join(ROOT, "kb/l7/registry/source-readonly.yaml")
AGENTS = os.path.expanduser("~/.dsh/AGENTS.md")
DEST_REGISTRY = os.path.join(ROOT, "kb/l7/registry/conclusion-destination.yaml")
ALIGNER = os.path.join(ROOT, "kb/l8/align_l0_feishu.py")

# 一个飞书令牌长什么样（表 / 记录 / 字段 / 视图 / base / wiki / docx / open_id）
TOKEN_RE = re.compile(r"\b(?:tbl|recv|fld|vew|cli_|ou_)[A-Za-z0-9]{6,}\b|\b[A-Za-z0-9]{24,}\b")

# ── 写动词的两种**真实**写法（★ 两种都要认，漏一种就等于没守）──────────────
#   A **命令行形**：`lark-cli base +record-list …`（人手敲、runbook、shell 脚本）
SUBCMD_RE = re.compile(r"\b(base|docs|wiki)\s+\+([A-Za-z0-9][-A-Za-z0-9]*)")
#   B **argv 形**：`_lark_run("base", "+record-batch-update", "--base-token", …)`
#     ★★ 这一条是**实测补的**：库里**唯一真实的写入口** `feishu_publish.py:615/620`
#     就是 argv 形，只认 A 形的第一版**扫不到它** —— 尺子看着在跑（报了 8 处"写动词"，
#     全是注释里的字面），真正的写路径一次都没进过判定。反向对照 R7 用**真文件文本**钉住这一点。
SUBCMD_ARGV_RE = re.compile(r"[\"'](base|docs|wiki)[\"']\s*,\s*[\"']\+([A-Za-z0-9][-A-Za-z0-9]*)[\"']")
WINDOW = 8                                                    # 写动词上下文行数
SELF = os.path.abspath(__file__)                              # 判据自己不参与扫描（见 find_writers）
#: **纯注释行**不可能执行 ⇒ 跳过。2026-10-10 加：本判据第一版把
#: `feishu_publish.py` 里一句**说明脚枪的注释**（那行恰好引用了 PRD 的 docx 令牌）判成了红 ——
#: 假阳性，而且正是"把正确的东西判成故障"那一类。
#: ⚠️ 只认行首 `#` / `//`；**块注释 `/* … */` 里的行认不出**（代价照实说）。
COMMENT_PREFIX = ("#", "//")


# ══════════════════════════════════════════════════════════════════════
# 纯函数：判定逻辑与取数分开，反向对照才好喂合成样本
# ══════════════════════════════════════════════════════════════════════

def resolve_readonly(doc):
    """从登记件取出**只读令牌集合**（含 base / table / wiki / docx / view）。

    ★ 为什么把 view 也算进来：只读的价值在于「这张表/这份文档不许动」，
      指向它的 view_id 出现在写命令旁边，同样是可疑信号，不该漏。
    ★ 为什么 `readonly_bases` 也要进集合（2026-10-10 Owner 裁定后加）：
      Owner 的口径是「**整个**入口 Base 都只读」，而**按表枚举会漏** ——
      实测该 Base 实拉 4 张表，`align_l0_schema.py` 里只写了 3 张（少「规则库」）。
      ⇒ 只读按 **base 令牌**判定：指向该 Base 里**任何一张表**的写，窗口里必有 base 令牌 ⇒ 照红。
        Base 以后新增的表**自动**覆盖，不需要回来改本件。
    """
    toks, ids = set(), []
    for r in doc.get("resources") or []:
        if not r.get("read_only"):
            continue
        ids.append(str(r.get("id")))
        for k in ("base_token", "table_id", "view_id", "wiki_token", "docx_token"):
            v = r.get(k)
            if v:
                toks.add(str(v).strip())
    for b in doc.get("readonly_bases") or []:
        bt = str(b.get("base_token") or "").strip()
        if bt:
            toks.add(bt)
            ids.append("base:%s" % (b.get("label") or bt))
        for t in b.get("tables_observed_20261010") or []:
            if t.get("id"):
                toks.add(str(t["id"]).strip())
    return toks, ids


def subcmds_in(text):
    """一段代码里出现的 `(家族, +子命令, 行号)` —— **两种写法都认**（见文件头的 A/B）。"""
    out, seen = [], set()
    for pat in (SUBCMD_RE, SUBCMD_ARGV_RE):
        for m in pat.finditer(text):
            line = text.count("\n", 0, m.start()) + 1
            key = (line, m.group(1), "+" + m.group(2))
            if key in seen:
                continue
            seen.add(key)
            out.append(key)
    return sorted(out)


def find_writers(text, readonly_toks, known_targets):
    """扫一段代码文本，返回 (red, yellow, seen) 三个列表。

    red    = 写动词命中只读令牌（同窗口）⇒ **必须红**
    yellow = 写动词窗口里有令牌，但既不是只读源也不是已登记的写目标 ⇒ 未登记，需人看
    seen   = 扫到的写动词总数（判据**判了几条**的证据；为 0 说明尺子可能空转）
    """
    lines = text.splitlines()
    red, yellow, seen = [], [], 0
    for line_no, family, sub in subcmds_in(text):
        if sub in READONLY_SUBCMDS.get(family, ()):            # 只读白名单：放行
            continue
        raw = lines[line_no - 1].strip()
        if raw.startswith(COMMENT_PREFIX):                     # 纯注释行：不可能执行，跳过
            continue
        seen += 1
        i = line_no - 1
        lo, hi = max(0, i - WINDOW), min(len(lines), i + WINDOW + 1)
        window = "\n".join(lines[lo:hi])
        hit_ro = sorted(t for t in readonly_toks if t in window)
        if hit_ro:
            red.append({"line": line_no, "verb": "%s %s" % (family, sub), "tokens": hit_ro,
                        "src": lines[i].strip()[:120]})
            continue
        other = sorted(set(TOKEN_RE.findall(window)) - set(known_targets))
        if other:
            yellow.append({"line": line_no, "verb": "%s %s" % (family, sub),
                           "tokens": other[:4], "src": lines[i].strip()[:120]})
    return red, yellow, seen


def missing_in_agents(agents_text, must):
    """AGENTS.md 里**该在而没在**的断言（空列表 = 声明在位）。"""
    return [k for k in must if k not in agents_text]


def as_id_default(src_text):
    """读 `align_l0_feishu.py` 真值：`AS_ID` 的默认身份是什么（不抄文档）。"""
    m = re.search(r"AS_ID\s*=\s*os\.environ\.get\(\s*[\"']L8_AS[\"']\s*,\s*[\"']([^\"']+)[\"']\s*\)",
                  src_text)
    return m.group(1) if m else None


def _iter_live_code(policy):
    """活代码文件清单（排除 `_`/`.` 开头段、tests、.bak —— 口径在登记件里，这里只执行）。"""
    roots = policy.get("roots") or ["kb", "tools"]
    suffixes = tuple(policy.get("suffixes") or [".py", ".mjs", ".js", ".sh"])
    ex_seg = tuple(policy.get("exclude_segments_prefix") or ["_", "."])
    ex_name = set(policy.get("exclude_segment_names") or ["tests"])
    ex_file = tuple(policy.get("exclude_filename_contains") or [".bak"])
    out = []
    for root in roots:
        base = os.path.join(ROOT, root)
        for dirpath, dirnames, filenames in os.walk(base):
            parts = os.path.relpath(dirpath, ROOT).split(os.sep)
            if any(p.startswith(ex_seg) or p in ex_name for p in parts if p not in (".",)):
                dirnames[:] = []
                continue
            dirnames[:] = [d for d in dirnames
                           if not d.startswith(ex_seg) and d not in ex_name]
            for fn in filenames:
                if not fn.endswith(suffixes) or any(x in fn for x in ex_file):
                    continue
                out.append(os.path.join(dirpath, fn))
    return sorted(out)


# ══════════════════════════════════════════════════════════════════════
# 取数：登记件 + 判据口径（**唯一真源，不在这里抄第二份**）
# ══════════════════════════════════════════════════════════════════════

def _load():
    import yaml
    with open(REGISTRY, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _read(path):
    try:
        return open(path, encoding="utf-8", errors="replace").read()
    except Exception:                                          # noqa: BLE001
        return ""


DOC = _load()
READONLY_TOKS, READONLY_IDS = resolve_readonly(DOC)
SCAN_POLICY = DOC.get("scan_policy") or {}
READONLY_SUBCMDS = {k: set(v or []) for k, v in (SCAN_POLICY.get("readonly_subcommands") or {}).items()}
KNOW_AGENTS_MUST = ((DOC.get("agents_md") or {}).get("must_contain")) or []


def _known_write_targets():
    """已登记的写目标（不是只读源的那些）—— 用来把「动态目标」与「未登记目标」分开。"""
    out = set()
    for w in DOC.get("write_targets_not_affected") or []:
        for k in ("base_token", "table_id"):
            if w.get(k):
                out.add(str(w[k]))
    return out


# ══════════════════════════════════════════════════════════════════════
# 五条判据
# ══════════════════════════════════════════════════════════════════════

def c1_registry():
    """① 登记件自洽：两条只读源都在、都带令牌，按 base 的只读清单不为空，判据口径不为空。"""
    bad = []
    res = DOC.get("resources") or []
    if len(res) < 2:
        bad.append("只登记了 %d 条只读源（Owner 给的是 2 条）" % len(res))
    for r in res:
        if not r.get("read_only"):
            bad.append("%s: read_only 不为 true" % r.get("id"))
        if not r.get("url"):
            bad.append("%s: 缺 url" % r.get("id"))
        if not any(r.get(k) for k in ("base_token", "wiki_token", "docx_token")):
            bad.append("%s: 缺任何令牌" % r.get("id"))
    bases = DOC.get("readonly_bases") or []
    if not bases:
        bad.append("readonly_bases 为空 —— Owner 裁的「整个 Base 只读」没有被执行")
    for b in bases:
        if not b.get("base_token"):
            bad.append("readonly_bases 里有一条缺 base_token：%r" % (b.get("label"),))
        if not b.get("provenance"):
            bad.append("readonly_bases 的 %r 没标 provenance（分不清哪些是 Owner 裁定、哪些是扩展）"
                       % (b.get("label"),))
    if not KNOW_AGENTS_MUST:
        bad.append("agents_md.must_contain 为空 —— 判据会空转")
    if not READONLY_SUBCMDS:
        bad.append("scan_policy.readonly_subcommands 为空 —— fail-closed 白名单空了")
    prov = {}
    for b in bases:
        prov[str(b.get("provenance"))] = prov.get(str(b.get("provenance")), 0) + 1
    return (not bad), {"只读源(resources)": len(res), "只读 Base": len(bases),
                       "按来源": prov, "只读令牌总数": len(READONLY_TOKS),
                       "AGENTS 必含项": len(KNOW_AGENTS_MUST),
                       "只读白名单族": sorted(READONLY_SUBCMDS),
                       "问题": bad}


def c2_agents_declares():
    """② 规则还在 AGENTS.md 里（掉了 ⇒ 下次又会从头问一遍）。"""
    txt = _read(AGENTS)
    miss = missing_in_agents(txt, KNOW_AGENTS_MUST)
    return (not miss), {"核了": len(KNOW_AGENTS_MUST), "缺": miss,
                        "文件": AGENTS, "字节": len(txt.encode())}


def c3_live_code_no_writer():
    """③ 活代码里**没有**写只读源的路径（fail-closed：非白名单子命令一律按写算）。

    ★ **判据自己不参与扫描**：本文件里既有 `+xxx` 这种注释，也有自证用的合成字符串，
      扫进来只会把「写动词命中数」灌水（实测第一版 8 处里 4 处是它自己）。
      代价照实说：**判据自身被改坏，这条尺子看不见** —— 那要靠 git 与 code review。
    """
    files = [f for f in _iter_live_code(SCAN_POLICY) if os.path.abspath(f) != SELF]
    known = _known_write_targets()
    red, yellow, seen, scanned, sites = [], [], 0, 0, []
    for f in files:
        txt = _read(f)
        if "+" not in txt:
            continue
        scanned += 1
        r, y, s = find_writers(txt, READONLY_TOKS, known)
        for x in r:
            x["file"] = os.path.relpath(f, ROOT)
        for x in y:
            x["file"] = os.path.relpath(f, ROOT)
        if s:
            rel = os.path.relpath(f, ROOT)
            sites += ["%s:%d %s %s" % (rel, ln, fam, sub)
                      for ln, fam, sub in subcmds_in(txt)
                      if sub not in READONLY_SUBCMDS.get(fam, ())]
        red += r
        yellow += y
        seen += s
    detail = {"扫了活代码": "%d 个文件（其中含 `+` 的 %d 个）" % (len(files), scanned),
              "写动词命中": "%d 处（含注释/文档串）" % seen,
              "写动词位置": sites[:12] or "无",
              "只读源被写": red or "无"}
    if yellow:
        detail["未登记目标(黄)"] = yellow[:5]
    return (not red), detail


def c4_identity():
    """④ 身份口径的真值：`align_l0_feishu.py` 的 AS_ID 默认**确实是 bot**（读代码，不抄文档）。"""
    src = _read(ALIGNER)
    dflt = as_id_default(src)
    order = ((DOC.get("identity_policy") or {}).get("order")) or []
    bad = []
    if dflt != "bot":
        bad.append("align_l0_feishu.py 的 AS_ID 默认 = %r（应是 bot）" % dflt)
    if not order or order[0] != "bot":
        bad.append("登记件 identity_policy.order 首位 = %r（应是 bot）" % (order[:1] or None))
    return (not bad), {"AS_ID 默认(代码真值)": dflt, "登记件顺序": order, "问题": bad}


def c5_write_target_not_readonly():
    """⑤ 唯一的飞书写入口没被误伤：它声明的写目标**不在**只读集合里。"""
    txt = _read(DEST_REGISTRY)
    tgts = sorted(set(TOKEN_RE.findall(txt)))
    clash = sorted(set(tgts) & READONLY_TOKS)
    # 结论去向必须真的指向一张表；指不到 ⇒ 这条判据在空转
    has_table = bool(re.search(r"\btbl[A-Za-z0-9]{6,}\b", txt))
    bad = (["写目标与只读源**重叠**：%s" % clash] if clash else []) + \
          ([] if has_table else ["conclusion-destination.yaml 里解析不出表 id —— 判据在空转"])
    return (not bad), {"写目标登记件": os.path.relpath(DEST_REGISTRY, ROOT),
                       "解析到的令牌": len(tgts), "与只读源重叠": clash or "无",
                       "问题": bad}


# ── C6「文档口径闸门」的判据（Owner 2026-10-10：「检查整个任务拆解，不允许出现改源表」）──
# ★ 为什么单列一条：C3 只扫**活代码**，而这次的病根在**文档**——
#   任务拆解里一句「3 份 Brief 照 PRD §2.2 直接改（分类→其它、状态→暂不采用）」，
#   被照着执行了 3 条写入。**代码闸门看不见文档**，所以文档要自己有一条。
DOC_GATE = {
    # ── ① **执行单**：必须带只读口径（作者得把约束写进去）────────────────────
    #   ★ 刻意**收窄到执行单**：像 `任务详情-与建设方案v2-一致性对照.md`（9/28 的历史对照件）
    #     比这条规则早两周，硬要它带锚 = **把正确的东西判成故障** ——
    #     正是本库最忌讳的那种检查器。它只进下面的黑名单扫描，不进这一条。
    "anchor_globs": ["工单-*.md", "*任务拆解*.md"],
    # ── ② 黑名单扫描的**全体**文档（执行单 + 同族文档 + 正本 xlsx）──────────
    "scan_globs": ["工单-*.md", "*任务拆解*.md", "*任务详情*.md"],
    # 正本 xlsx（在则一并扫它的 C/D/G 三列）
    "xlsx": os.path.expanduser("~/Desktop/内容治理知识库搭建任务详情.xlsx"),
    # 执行单必须命中的口径锚（任一即可）
    "must_contain_any": ["禁止修改飞书侧源", "source-readonly.yaml"],
    # **不许**出现的「写源表」指令写法。刻意只收**具体到能执行的措辞**，
    # 不收「改」「飞书」这类泛词 —— 否则「禁止修改飞书侧源」自己就会被判红。
    "deny": [
        r"→\s*「(其它|暂不采用)」",
        r"(改成|改为|直接改)[^。\n]{0,14}「(其它|暂不采用)」",
        r"(修改|改|回写|写回)(飞书)?源(表|数据)",
        r"照\s*PRD[^。\n]{0,12}直接改",
    ],
    # 否定感知：同一行里有这些词 ⇒ 那是在**讲规则**，不是在**下指令**
    "negation": r"(禁止|不许|不得|不要|不可|严禁|不允许|已删除|已于|作废|只读|不改|不动|一个字没改)",
}


def scan_doc(text, must_any, deny, negation):
    """扫一段文档文本：返回 (missing_anchor, hits)。

    missing_anchor = 该文档没带只读口径（①没做到）
    hits           = 命中的「写源表」指令（②破了）
    """
    miss = [] if any(k in text for k in must_any) else list(must_any)
    hits = []
    for ln in text.splitlines():
        if re.search(negation, ln):          # 讲规则的句子，放行
            continue
        for pat in deny:
            if re.search(pat, ln):
                hits.append({"line": ln.strip()[:140], "pattern": pat})
                break
    return miss, hits


def _doc_targets():
    """要扫的文档清单 → [(名字, 文本, 是否必须带口径锚)]（存在才扫；xlsx 把 C/D/G 拼成文本）。"""
    import glob as _g
    out = []
    anchor_set = set()
    for pat in DOC_GATE["anchor_globs"]:
        for f in _g.glob(os.path.join(ROOT, pat)):
            anchor_set.add(os.path.abspath(f))
    for pat in DOC_GATE["scan_globs"]:
        for f in sorted(_g.glob(os.path.join(ROOT, pat))):
            if os.path.abspath(f) == SELF or "_archive" in f:
                continue
            out.append((os.path.relpath(f, ROOT), _read(f), os.path.abspath(f) in anchor_set))
    xp = DOC_GATE["xlsx"]
    if os.path.exists(xp):
        try:
            import openpyxl
            wb = openpyxl.load_workbook(xp)
            ws = wb[wb.sheetnames[0]]
            txt = "\n".join(str(ws.cell(r, c).value) for r in range(1, ws.max_row + 1)
                            for c in (3, 4, 7) if ws.cell(r, c).value)
            out.append((os.path.relpath(xp, os.path.expanduser("~")), txt, True))
        except Exception as e:                                     # noqa: BLE001
            out.append((os.path.relpath(xp, os.path.expanduser("~")),
                        "【读不出：%r】" % e, False))
    return out


def c6_task_docs():
    """⑥ 任务拆解/工单类文档：**不许出现「写飞书源表」的指令**；执行单还必须带上只读口径。

    ★ 边界：这是**措辞黑名单**，只能挡住「具体到能执行」的那几类写法
      （`→「其它」` / `改成「暂不采用」` / `照 PRD 直接改` / `改飞书源表`）。
      **换个说法就挡不住** —— 挡不住的部分只能靠人读（AGENTS.md 的规则）。
      写清楚这条，是为了别让人以为"绿了就万事大吉"。
    """
    rows = _doc_targets()
    if not rows:
        return False, {"扫到的文档": "0 份 —— 闸门在空转（文件名模式可能已过期）"}
    bad, det = [], []
    for name, txt, need_anchor in rows:
        miss, hits = scan_doc(txt, DOC_GATE["must_contain_any"] if need_anchor else [],
                              DOC_GATE["deny"], DOC_GATE["negation"])
        det.append("%s%s：%s" % (name, "（执行单）" if need_anchor else "",
                                "✅" if (not miss and not hits) else "❌"))
        for m in miss:
            bad.append("%s 是执行单但缺只读口径锚「%s」" % (name, m))
        for h in hits:
            bad.append("%s 出现写源表指令：%s" % (name, h["line"]))
    return (not bad), {"扫到的文档": det, "问题": bad}


PUBLISHER = os.path.join(ROOT, "kb/l7/review-engine/core/feishu_publish.py")
_WIRE_RE = re.compile(r"if\s+a\.doc\s*:\s*\n\s*refuse_if_source_readonly\(a\.doc\)")


def _publish_mod():
    """import 发布件只为验闸门（它模块级只有常量与 import，`main()` 在 `__main__` 守卫里）。"""
    import importlib.util
    spec = importlib.util.spec_from_file_location("_fp_guard", PUBLISHER)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def c7_publish_doc_guard():
    """⑦ 发布件的 `--doc` 只读源闸门**在位且真的会拒**（Owner 2026-10-10：「--doc 脚枪封」）。

    ★ 为什么这条必须**真调一次**而不是只看有没有那个函数：
      本库栽过「判据恒绿」。一个叫 `refuse_if_source_readonly` 的函数**存在**、
      但没人调、或者判据写反（把只读令牌放行、把普通令牌拒掉），静态看全都是"在"。
      ⇒ 所以两半都验：**接线**（`main()` 里真的调了）＋ **行为**（只读令牌抛、普通令牌不抛）。
    """
    if not os.path.exists(PUBLISHER):
        return False, {"问题": ["发布件不在：%s" % PUBLISHER]}
    src = _read(PUBLISHER)
    wired = bool(_WIRE_RE.search(src))
    bad = []
    if not wired:
        bad.append("闸门没接线：`feishu_publish.py::main()` 里找不到 "
                   "`if a.doc: refuse_if_source_readonly(a.doc)` ⇒ 函数在但不会被执行")
    refused, passed = [], []
    try:
        m = _publish_mod()
    except Exception as e:                                     # noqa: BLE001
        return False, {"接线": wired, "问题": ["发布件 import 不起来：%r" % e]}
    # 应当拒：登记件里**每一条**只读令牌里的 docx/wiki 那类（这里全量试一遍）
    for t in sorted(READONLY_TOKS):
        try:
            m.refuse_if_source_readonly("https://momcozy-in.feishu.cn/docx/%s" % t)
            passed.append(t)          # 没抛 ⇒ 漏了
        except SystemExit:
            refused.append(t)
    # 应当放：正常报告文档令牌
    try:
        m.refuse_if_source_readonly("YOjkd5ItEoBybHx7BGAc25r6nXb")
        ok_benign = True
    except SystemExit:
        ok_benign = False
    if passed:
        bad.append("这些只读令牌**没被拒**（闸门漏了）：%s" % passed[:6])
    if not ok_benign:
        bad.append("普通报告文档令牌被**误拒** ⇒ 正常发布会被挡死")
    return (not bad), {"接线": "✅ main() 里调了" if wired else "❌ 没接线",
                       "应当拒（只读令牌）": "%d/%d 拒了" % (len(refused), len(READONLY_TOKS)),
                       "应当放（普通文档）": "✅" if ok_benign else "❌ 被误拒",
                       "问题": bad}


def c8_prd_scope_exclusions():
    """⑧ PRD §2.2 排除项**真的不作依据了吗** —— 现算残留（Owner 2026-10-10「按 prd 走」）。

    ★ 为什么要有这条：口径写在登记件里**不等于**生效。库内真正的开关是 L2 单元的
      `rule_eligible`（L1 manifest 承载 → `l2_split_run.py` 读）；登记件改一个字，
      **已经产出的单元不会自己变**。⇒ 必须**现算残留**，红了就是还没做完，
      绿了（残留 0）才算落地。这就是「术据而非散文」在**口径类**改动上的用法。
    """
    ex = ((DOC.get("prd_scope_exclusions") or {}).get("records")) or []
    if not ex:
        return False, {"问题": ["登记件里没有 `prd_scope_exclusions.records` —— 判据空转"]}
    rids = {str(r.get("record_id")) for r in ex if r.get("record_id")}
    units_path = os.path.join(ROOT, "kb/l2/units.jsonl")
    if not os.path.exists(units_path):
        return False, {"问题": ["读不到 %s —— 判不出残留" % os.path.relpath(units_path, ROOT)]}
    total, hit, eligible = 0, 0, 0
    with open(units_path, encoding="utf-8") as fh:
        for ln in fh:
            if not ln.strip():
                continue
            total += 1
            try:
                u = json.loads(ln)
            except Exception:                                  # noqa: BLE001
                continue
            rid = str(u.get("resource_id") or "")
            if any(r in rid for r in rids):
                hit += 1
                if u.get("rule_eligible") is not False:
                    eligible += 1
    ok = (eligible == 0)
    return ok, {"排除记录": len(rids), "L2 单元总数": total,
                "命中排除记录的单元": hit,
                "其中仍 rule_eligible≠false": eligible,
                "结论": "✅ 已不作依据" if ok else
                        "❌ 仍未落地：%d 个单元仍可作依据 ⇒ 见登记件 `prd_scope_exclusions.implementation_status`"
                        % eligible}


CHECKS = [
    ("C1 登记件自洽（两条只读源齐、口径不为空）", c1_registry),
    ("C2 规则仍在 AGENTS.md（没被删掉）", c2_agents_declares),
    ("C3 活代码里没有写只读源的路径", c3_live_code_no_writer),
    ("C4 身份口径真值（AS_ID 默认 = bot）", c4_identity),
    ("C5 写入口没被误伤（结论去向 ≠ 只读源）", c5_write_target_not_readonly),
    ("C6 任务拆解/工单里没有「写飞书源表」的指令", c6_task_docs),
    ("C7 发布件 --doc 闸门在位且真的会拒", c7_publish_doc_guard),
    ("C8 PRD §2.2 排除项已不作依据（现算残留）", c8_prd_scope_exclusions),
]


# ══════════════════════════════════════════════════════════════════════
# 反向对照：证明上面五条**不是恒真**
# ══════════════════════════════════════════════════════════════════════

def reverse_controls():
    """把每条判据喂一个"坏样本"，它**必须**红。红了才说明这条判据在判。

    ★ 为什么非做不可：本库栽过「判据恒绿、看着像守着、其实什么都没守」。
      反向对照是唯一能证伪它的东西。
    ★ 这里的坏样本**在内存里造**，不往盘上写任何东西 —— 判据是只读件，自证也一样。
    """
    P, F = [], []

    def chk(name, cond, extra=""):
        (P if cond else F).append(name)
        print("  %s %s%s" % ("✅" if cond else "❌", name, ("  " + extra) if extra else ""))

    ro = READONLY_TOKS or {"__no_readonly_token__"}
    tok = sorted(ro)[0]
    known = _known_write_targets()

    # R1 真造一遍：写动词 + 只读令牌同窗口 ⇒ 必须红
    bad1 = "lark-cli base +record-batch-update --base-token %s\n  --json '{}'\n" % tok
    r1, _y1, _s1 = find_writers(bad1, ro, known)
    chk("R1 C3 反向对照：写只读源必须判红", len(r1) == 1, "命中 %d 处（令牌 %s）" % (len(r1), tok))

    # R2 对照的反面：写动词指向**别处** ⇒ 必须**不**红（证明不是"见写动词就红"的恒红尺）
    bad2 = "lark-cli base +record-batch-update --base-token %s\n" % ("ZZZZnotarealsource99")
    r2, _y2, s2 = find_writers(bad2, ro, known)
    chk("R2 反向对照的反面：写别处不许红（否则是恒红尺）",
        len(r2) == 0 and s2 == 1, "写动词命中 %d / 红 %d" % (s2, len(r2)))

    # R3 只读子命令**不许**被当成写（否则白名单失效、天天误报）
    ok3 = "lark-cli base +record-list --base-token %s --as bot\n" % tok
    _r3, _y3, s3 = find_writers(ok3, ro, known)
    chk("R3 fail-closed 白名单：只读子命令不被算作写", s3 == 0, "写动词命中 %d" % s3)

    # R4 把 AGENTS.md 里的令牌抠掉 ⇒ C2 必须红
    atxt = _read(AGENTS)
    stripped = atxt.replace(tok, "（已剔除）") if tok in atxt else atxt
    chk("R4 C2 反向对照：抠掉令牌后 AGENTS.md 声明必须判缺",
        bool(atxt) and (not missing_in_agents(atxt, KNOW_AGENTS_MUST))
        and bool(missing_in_agents(stripped, KNOW_AGENTS_MUST)),
        "必含 %d 项" % len(KNOW_AGENTS_MUST))

    # R5 把 AS_ID 默认改成 user ⇒ C4 必须红
    src = _read(ALIGNER)
    tweaked = re.sub(r'(AS_ID\s*=\s*os\.environ\.get\(\s*["\']L8_AS["\']\s*,\s*["\'])bot(["\'])',
                     r"\1user\2", src)
    chk("R5 C4 反向对照：AS_ID 默认改成 user 必须判红",
        as_id_default(src) == "bot" and tweaked != src and as_id_default(tweaked) == "user",
        "真值 %r → 改后 %r" % (as_id_default(src), as_id_default(tweaked)))

    # R6 五条判据都有 return False 的路径（不是恒绿）
    me = open(os.path.abspath(__file__), encoding="utf-8").read()
    chk("R6 五条判据都有失败路径（不是恒绿）", me.count("return (not bad), ") >= 4)

    # R7 ★★ **真造一遍缺陷，而且用真文件的文本**（第一版栽在这上面）──────────────
    #   库里唯一真实的写入口是 argv 形：`_lark_run("base", "+record-batch-update", …)`。
    #   只认 `base +xxx` 的检测器**扫不到它**，而它当时照样报"扫到 8 处写动词、全绿"
    #   —— 典型的「尺子看着在跑、真正的路径从没进过判定」。
    #   这条对照两半都要过：① 真文件原样 ⇒ **不许红**（不是恒红）；② 把只读令牌塞进那次调用 ⇒ **必须红**。
    pub = os.path.join(ROOT, "kb/l7/review-engine/core/feishu_publish.py")
    ptxt = _read(pub)
    # 要挑一个**真的是写**的调用点来注入 —— 挑到白名单里的读子命令（`+record-search`）
    # 注入后照样不红，那条对照就成了假绿（第一版就挑错了）。
    hits = [m for m in SUBCMD_ARGV_RE.finditer(ptxt)
            if "+" + m.group(2) not in READONLY_SUBCMDS.get(m.group(1), ())]
    m = hits[0] if hits else None
    if ptxt and m:
        injected = ptxt[:m.start()] + '\n    _x = "%s"\n' % tok + ptxt[m.start():]
        r7a, _y7a, _s7a = find_writers(ptxt, ro, known)
        r7b, _y7b, _s7b = find_writers(injected, ro, known)
        chk("R7 真文件反向对照：真 argv 写入口被认出来，且塞入只读令牌后精确变红",
            len(r7a) == 0 and len(r7b) >= 1,
            "真文件红 %d → 注入后红 %d（拿 %s %s 做的注入）"
            % (len(r7a), len(r7b), m.group(1), "+" + m.group(2)))
    else:
        chk("R7 真文件反向对照：真 argv 写入口被认出来，且塞入只读令牌后精确变红", False,
            "在 %s 里找不到 argv 形写调用 —— 检测口径可能又漏了" % os.path.relpath(pub, ROOT))

    # R8 ★「整个 Base 只读」必须是**真的按 Base 判**（2026-10-10 Owner 裁定后加）─────
    #   口径：写这个 Base 里**另一张表**（不是 Owner 给的 URL 点的那张）**同样算违规**。
    #   若哪天有人把判定退回「只认 resources 里那几张表的 id」⇒ **本条精确变红**
    #   （因为下面那张表的 id 不在 resources 里，只由 readonly_bases 兜着）。
    bases = DOC.get("readonly_bases") or []
    # 取「**只被 readonly_bases 的表清单兜住、不在 resources 里**」的那张表当靶子 ——
    # 命中它就等于命中「按 Base 判」这条口径本身。
    res_toks = set()
    for r in DOC.get("resources") or []:
        for k in ("base_token", "table_id", "view_id", "wiki_token", "docx_token"):
            if r.get(k):
                res_toks.add(str(r[k]))
    victim = None
    for b in bases:
        for t in b.get("tables_observed_20261010") or []:
            if t.get("id") and str(t["id"]) not in res_toks:
                victim = (str(b.get("base_token")), str(t["id"]), t.get("name"))
                break
        if victim:
            break
    if victim:
        bt, tid, tname = victim
        bad8 = 'lark-cli base +record-delete --base-token %s --table-id %s --yes\n' % (bt, tid)
        r8, _y8, _s8 = find_writers(bad8, ro, known)
        # ★ 判据要看的是「**表 id 在命中令牌里**」——窗口里同时还有 base 令牌，
        #   所以不能拿 `tokens[0]` 比（第一版就这么比的，把好好的检测器判成了失败）。
        chk("R8 写同 Base 的另一张表（%s）也必须红 —— 证明是按 Base 判、不是按表枚举" % tname,
            len(r8) == 1 and tid in r8[0]["tokens"],
            "该表 %s 不在 resources 里，靠 readonly_bases 兜住；命中令牌 %s"
            % (tid, r8[0]["tokens"] if r8 else None))
    else:
        chk("R8 写同 Base 的另一张表也必须红", False,
            "readonly_bases 里找不到「不在 resources 里」的表 ⇒ 这条对照没在判")

    # R9 ★ C6 文档口径闸门：写源表的**指令写法**必须命中（2026-10-10 那件事的原始措辞）
    synth_bad = ("23. 【补·PRD §2.2】按飞书表既有选项裁定 3 份红人 Brief："
                 "知识库分类「外部标准」→「其它」，材料审核状态→「暂不采用」，备注写明依据。")
    m9, h9 = scan_doc(synth_bad, DOC_GATE["must_contain_any"], DOC_GATE["deny"], DOC_GATE["negation"])
    chk("R9 C6 反向对照：那句原始措辞（→「其它」/→「暂不采用」）必须被判红",
        len(h9) >= 1, "命中 %d 处" % len(h9))

    # R10 反面：**讲规则**的句子不许被判红（否定感知），否则「禁止修改飞书侧源表」自己会红
    synth_ok = ("★ 口径：禁止修改飞书侧源任何数据；凡→「其它」这类写法一律不许出现在本件。\n"
                "参照 kb/l7/registry/source-readonly.yaml。")
    m10, h10 = scan_doc(synth_ok, DOC_GATE["must_contain_any"], DOC_GATE["deny"], DOC_GATE["negation"])
    chk("R10 否定感知：讲规则的句子（含禁止/不许）不许被判红", not m10 and not h10,
        "缺锚 %d / 命中 %d" % (len(m10), len(h10)))

    # R11 真文档当前必须干净（不是恒红）
    rows11 = _doc_targets()
    allhits = [h for n, t, _a in rows11
               for h in scan_doc(t, [], DOC_GATE["deny"], DOC_GATE["negation"])[1]]
    chk("R11 真文档当前无写源表指令（证明这条不是恒红）", not allhits,
        "扫了 %d 份，命中 %d" % (len(rows11), len(allhits)))

    # R12 ★ C7：把「接线」那两行从发布件里抠掉 ⇒ 静态检查必须判红
    src12 = _read(PUBLISHER)
    stripped12 = _WIRE_RE.sub("# （已抠掉接线，反向对照用）", src12)
    chk("R12 C7 反向对照：抠掉 `if a.doc: refuse_if_source_readonly(a.doc)` 必须判红",
        bool(_WIRE_RE.search(src12)) and not _WIRE_RE.search(stripped12),
        "原文命中接线 %d 处" % len(_WIRE_RE.findall(src12)))

    # R13 ★ 注释行必须被跳过（2026-10-10 的假阳性就是这个）；但**非注释**的同内容必须照红
    ro_tok = tok
    synth_cmt = '# 说明：有人 `--doc %s` 就会整篇覆盖\n' % ro_tok
    synth_code = 'x = "--doc %s"\nlark-cli base +record-delete --base-token %s --yes\n' % (ro_tok, ro_tok)
    _r13a, _y13a, s13a = find_writers(synth_cmt, ro, known)
    r13b, _y13b, s13b = find_writers(synth_code, ro, known)
    chk("R13 注释行跳过：注释里的写动词不算；非注释的照红",
        s13a == 0 and len(r13b) >= 1,
        "注释 写动词%d/红%d ｜ 代码 红%d" % (s13a, len(_r13a), len(r13b)))

    print("\n反向对照：通过 %d / 失败 %d" % (len(P), len(F)))
    for x in F:
        print("  · 失败：%s" % x)
    return 1 if F else 0


def main():
    ap = argparse.ArgumentParser(description="判据：飞书只读源没被写 + 规则没从 AGENTS.md 掉出去")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--selftest", action="store_true", help="只跑反向对照")
    a = ap.parse_args()

    if a.selftest:
        print("check_source_readonly · 反向对照（证明判据不是恒真）")
        return reverse_controls()

    results, fails = [], []
    for name, fn in CHECKS:
        try:
            ok, detail = fn()
        except Exception as e:                                 # noqa: BLE001
            ok, detail = False, {"判据自己崩了": repr(e)}
        results.append({"check": name, "ok": ok, "detail": detail})
        if not ok:
            fails.append("%s → %s" % (name, detail.get("问题") or detail))

    if a.json:
        print(json.dumps({"ok": not fails, "results": results}, ensure_ascii=False, indent=1))
    else:
        print("飞书只读源判据（只读；不调飞书 / 不写库）")
        print("登记件：%s" % os.path.relpath(REGISTRY, ROOT))
        print("-" * 74)
        for r in results:
            print("  %s %s" % ("✅" if r["ok"] else "❌", r["check"]))
            for k, v in (r["detail"] or {}).items():
                print("       %s：%s" % (k, v))
        print("-" * 74)
        print("结论：%s" % ("✅ 只读源没被写、规则在位、PRD §2.2 排除项已落地" if not fails
                          else "❌ %d 条红 —— %s" % (len(fails), "；".join(fails))))
        print("★ 边界：C3 只扫**活代码**（.py/.mjs/.js/.sh）；C6 只扫**任务拆解/工单类文档**且是"
              "**措辞黑名单**（换个说法就挡不住）。人手从 .md runbook 里抄命令去打源表，"
              "这两条都管不住 —— 那部分只能靠 AGENTS.md 的规则 + 人。")
    return 3 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
