#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""report_conformance.py —— **审查报告**（渲染件）是否照 Owner 2026-10-20 那五条出。

## 它治的那个病（真单：飞书 docx `X23ydZ3bwop5cIxvElZcy6Fjnu7`）

Owner 拿这份报告给了五条，逐条都能在原文里点到：

| # | Owner 原话 | 报告里的病 |
|---|---|---|
| 1 | 「未归类问题：2 个，不属于所属类别12类中的吗？图片提取规则的时候要归类」 | 汇总行 `· 未归类问题：2 个`；两条逐条 `**所属类别**：未归类` |
| 2 | 「问题描述：（本条未提供问题描述）==》不允许出现这样的回答，必须有问题描述」 | 两条逐条 `**问题描述**：（本条未提供问题描述）` |
| 3 | 「位置：图 1 ==〉你要写上尽详细具体位置，比如：图片顶部，图 1 第 3 处」 | 两条逐条 `**位置**：图 1`（无第 X 处）；另两条 `图 1 第 3 处` 的 X 不可复核 |
| 4 | 「依据文档链接中不要写【问题要点】，字数超过 prd 限制了」 | 依据格印了 `【问题要点】` ＋ 1./2./3. 三条要点，整格 181 字 |
| 5 | 「修改建议的 30 字，标点不算字数」 | 度量/截断按含标点算（`len()`），会把合规建议截成残句 |

## 五条判据（逐条给 fail 理由，不合并、不吞）

- **R1 未归类**：报告里 **不许出现** `未归类` 作为「所属类别」（汇总行 `/ 未归类问题：N 个` 与
  逐条 `所属类别：未归类` 都算）。归类口径 = `kb/l7/registry/case-taxonomy-map.json`
  （案例层）＋ `rule-taxonomy.json`（规则层）。
  ⚠️ **例外**：报告自己把「为什么归不上」写明了的，仍判红 —— 因为 Owner 要的是**归类**，
  不是**解释为什么没归类**；真归不上应当**先修库**（见 `review.py::case_taxonomy`）。
- **R2 问题描述**：`（本条未提供问题描述）` / `未提供问题描述` / `未给问题描述` 一律红。
- **R3 位置**：每条必须有位置，且落在登记件的形态里（`prd533-constraints.yaml::location`）：
  `图 N 第 X 处`｜`视频 MM:SS`｜`正文第 X 段`｜区域前缀版 `图片顶部，图 N 第 X 处`。
  裸 `图 1` **红**（它没有「第几处」）。
- **R3b 第 X 处可复核**（只在给了 `--material` 时判）：声称 `图 N 第 X 处` ⇒ 该条的
  **引文/问题描述**必须能在素材块 `【图 N 内文字｜M 行】` 的**第 X 行**里找到。
  找不到 ⇒ 红（这说明 X 是编的）。没给素材 ⇒ **未测**（不判红也不判绿，如实记）。
- **R4 依据**：不许含 `【问题要点】` / `问题要点` / `【原则性错误】`（源记录排版标记，
  不是依据）；`← 命中「…」` 的引文 ≤ `basis.max_chars`（60）。
- **R5 修改建议**：实词数 ≤30（**标点不计入**，口径 = `prd533-constraints.yaml::counting.advice_no_punct`）。

## 为什么这五条要合成一把尺

它们全都是**报告渲染件**的缺陷，而现有的尺子各量一段、都不量这份报告：
`prd_card_conformance` 量**卡面**（P0 快路 `_prd_block` 的 stdout）、`material_evidence_gate`
量**证据是不是本单素材**、`prd533_check` 只给读数不接线。⇒ Owner 报告面这一块**没人守**。

## 退出码（照非阻断闸门惯例，**只退 0 或 3**）

  0  五条全过（或 `--selftest` 全过）
  3  任一条红 ⇒ CI 记 WARN（不改 runner 退出码）
  **永不 1/2**：非阻断闸门退 1/2 会被 runner 记成 ERROR 并把 CI 打红。

## 用法

    python3 kb/l8/report_conformance.py --selftest
    python3 kb/l8/report_conformance.py --fetch-json reports.json [--material mat.txt] [--json]
    python3 kb/l8/report_conformance.py --text report.md
    lark-cli docs +fetch --doc <token> --profile dsh-kb --as bot > /tmp/r.json
    python3 kb/l8/report_conformance.py --fetch-json /tmp/r.json
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REG = os.path.join(os.path.dirname(HERE), "l7", "registry", "prd533-constraints.yaml")

#: R2 的禁止占位句（Owner 2026-10-20 点名的那一句，连同它的近亲写法）
PLACEHOLDERS = ("（本条未提供问题描述）", "未提供问题描述", "未给问题描述", "本条未提供")
#: R1 的兜底类名（12 类的第 12 个）
UNCLASSED = "未归类"
#: R4 的禁止片段（源记录排版标记 —— 见登记件 `basis.forbidden_fragments`）
BASIS_FORBIDDEN = ("【问题要点】", "问题要点", "【原则性错误】")

# 位置四形态（与 prd533-constraints.yaml::location.patterns 同一份；区域词在最前）
RE_FIGURE = re.compile(r"^图\s*\d+\s*第\s*\d+\s*处$")
RE_FIGURE_AREA = re.compile(r"^(?:图片)?(?:顶部|中部|底部|左侧|右侧)[，,]\s*图\s*\d+\s*第\s*\d+\s*处$")
RE_VIDEO = re.compile(r"^视频\s*\d{1,2}:\d{2}$")
RE_TEXT = re.compile(r"^正文第\s*\d+\s*段$")
#: 从「图 N 第 X 处」（可带区域前缀）里抠出 N / X
RE_FIG_NX = re.compile(r"图\s*(\d+)\s*第\s*(\d+)\s*处")

# 逐条块的字段行（`**所属类别**：…` 在去 markdown 后是 `所属类别：…`）
FIELD_RE = re.compile(r"^\s*(所属类别|位置|问题描述|原因|依据文档链接|修改建议)\s*[：:]\s*(.*)$")
ITEM_HEAD_RE = re.compile(r"^\s*(F-\d+)\s*｜(.+)$")
# 素材块头：`【图 1 内文字｜9 行】` … `【/图 1】`
RE_IMG_BLOCK = re.compile(r"【\s*图\s*(\d+)\s*内文字\s*[｜|]\s*\d+\s*行】\s*(.*?)【\s*/\s*图\s*\1\s*】", re.S)


# ── 文本归一化 ───────────────────────────────────────────────────────────────
def html_to_text(content):
    """飞书 `docs +fetch` 的 content（HTML 片段）⇒ 纯文本行。

    为什么必须做：这一份报告是**从飞书拉下来的**，正文是 `<p>`/`<blockquote>`/`<br/>`；
    拿正则直接在 HTML 上量字数会把标签一起数进去（`<br/>` 6 个字符），
    而 PRD 的字数是**可见字数**（去标记）。
    """
    s = str(content or "")
    s = re.sub(r"(?i)<br\s*/?>", "\n", s)
    s = re.sub(r"(?i)</(p|div|h[1-6]|blockquote|li|tr|td|th)>", "\n", s)
    s = re.sub(r"(?i)<li[^>]*>", "\n", s)
    s = re.sub(r"(?is)<[^>]+>", "", s)
    s = html.unescape(s)
    return s


def normalize(text):
    """去 markdown 标记（`**` `>` `` ` `` `#`），保留行结构。"""
    out = []
    for raw in str(text or "").split("\n"):
        t = raw.strip()
        t = re.sub(r"^>\s*", "", t)
        t = re.sub(r"^#+\s*", "", t)
        t = t.replace("**", "").replace("`", "")
        t = t.strip()
        if t:
            out.append(t)
    return "\n".join(out)


def load_report(args):
    """报告正文（已归一化成纯文本行）。"""
    if args.fetch_json:
        with open(args.fetch_json, encoding="utf-8") as fh:
            doc = json.load(fh)
        content = (((doc or {}).get("data") or {}).get("document") or {}).get("content") or ""
        if not content:
            raise SystemExit("[report_conformance] --fetch-json 里没有 data.document.content：%s"
                             % args.fetch_json)
        return normalize(html_to_text(content))
    if args.text:
        with open(args.text, encoding="utf-8") as fh:
            raw = fh.read()
        if args.text.endswith(".json"):
            return load_report(argparse.Namespace(fetch_json=args.text, text=None))
        return normalize(html_to_text(raw) if "<" in raw[:400] else raw)
    raise SystemExit("[report_conformance] 要给 --fetch-json 或 --text")


#: 续行判定：`【问题要点】`/`1. …`/`原始出处：…`/`- …` 这些是**上一格的续行**
#: （飞书渲染时 `<br/>` 把一格的换行拆成了多行）。不认它们，依据格就只量到第一行
#: —— 实测那一单的 `【问题要点】` 与 1./2./3. 正是落在续行里，漏认就漏判。
RE_CONT = re.compile(r"^(【|\d{1,2}\s*[.、．]|原始出处|点开核对|- |· )")


# 引擎明细报告（`kb/l7/reports/*.review.md`）的条目形状：`### 1.【未归类】图 1` ＋ `- 依据：…`
# ⚠️ `#*` 开头是**故意**的：`normalize()` 会把行首 `###` 去掉（去 markdown 标记），
#    写死 `^###` 就永远匹配不上 ⇒ 解析 0 条 ⇒ 恒绿（第一版就这么错过了）。
ITEM_HEAD_ENGINE = re.compile(r"^#*\s*(\d+)\s*[.、]\s*【([^】]+)】\s*(.*)$")
FIELD_ENGINE = re.compile(r"^-\s*(所属类别\s*/\s*所属子类|所属类别|依据|建议同源检查|修改建议|位置|问题描述)\s*[：:]\s*(.*)$")


def parse_items_engine(report):
    """解析**引擎明细报告**（`kb/l7/reports/*.review.md`）的条目。

    为什么要认第二种形状：磁盘上真正存在的是这一种；只认渲染件的话，`--latest`
    会在「解析出 0 条」的情况下**判绿**——那正是本库最忌的「恒绿尺子」。
    认了就会真红（实测 2026-10-20 那份：3 条全是 `未归类` ＋ 位置 `图 1`）。
    """
    items, cur = [], None
    for line in report.split("\n"):
        m = ITEM_HEAD_ENGINE.match(line)
        if m:
            cur = {"id": m.group(1), "label": m.group(2).strip(),
                   "fields": {"所属类别": m.group(2).strip(), "位置": m.group(3).strip()},
                   "format": "engine"}
            items.append(cur)
            continue
        if cur is None:
            continue
        fm = FIELD_ENGINE.match(line)
        if not fm:
            continue
        key = re.sub(r"\s+", "", fm.group(1).split("/")[0])
        val = fm.group(2).strip()
        if key == "建议同源检查":
            # ⚠️ 这一行**不是**修改建议，是「这条建议的来源说明」
            #   （实测原文：「advice 取自案例记录；实测 181 条反例里只有 46% 有建议列」）。
            #   把它当 修改建议 去量 R5，等于拿来源说明当改法 —— 会凭空造出两条红。
            key = "建议说明"
        cur["fields"][key] = val
    return items


def parse_items(report):
    """把逐条块解析成 `[{id, label, fields:{位置/问题描述/…}}]`（两种形状都认）。

    形状 ① 渲染件（飞书 docx）：
        F-01 ｜ 北美本地化与标签要求 ｜ P1
        所属类别：…
        位置：…
    形状 ② 引擎明细报告：`### 1.【未归类】图 1` ＋ `- 依据：…`
    """
    items = parse_items_engine(report)
    if items:
        return items
    cur = None
    last = None                      # 上一格的字段名（续行往它身上拼）
    for line in report.split("\n"):
        m = ITEM_HEAD_RE.match(line)
        if m:
            cur = {"id": m.group(1), "head": m.group(2).strip(), "fields": {},
                   "format": "rendered"}
            items.append(cur)
            last = None
            continue
        if cur is None:
            continue
        fm = FIELD_RE.match(line)
        if fm:
            cur["fields"][fm.group(1)] = fm.group(2).strip()
            last = fm.group(1)
            continue
        if last and RE_CONT.match(line):
            cur["fields"][last] = (cur["fields"].get(last, "") + " " + line.strip()).strip()
        else:
            last = None
    return items


def count_visible(text):
    """可见字数：去链接、去空白（与登记件 `counting.rule: visible_no_url` 同口径）。"""
    t = re.sub(r"\[([^\]\n]*)\]\((?:https?:)?[^)\s]*\)", r"\1", str(text or ""))
    t = re.sub(r"https?://[^\s)）]+", "", t)
    t = re.sub(r"\s+", "", t)
    return len(t)


def _punct_re():
    """推荐信登记件里的标点类；取不到就用 prd533_check 的实现（唯一真源）。"""
    try:
        import importlib.util as _ilu
        spec = _ilu.spec_from_file_location("kb_prd533_check",
                                            os.path.join(HERE, "prd533_check.py"))
        mod = _ilu.module_from_spec(spec)
        spec.loader.exec_module(mod)
        if hasattr(mod, "ADVICE_PUNCT_RE"):
            return mod.ADVICE_PUNCT_RE
    except Exception as e:                                        # noqa: BLE001
        print("[report_conformance] ⚠ 标点类取不到，按最小类算：%s" % e, file=sys.stderr)
    return re.compile(r"[，。、；：！？…—～·「」『』（）【】《》〈〉“”‘’,.!?;:()\[\]{}<>]")


def advice_chars(text):
    """修改建议的实词字数：**标点不计入**（Owner 2026-10-20 / §5.3.3 口径）。"""
    t = re.sub(r"\s+", "", str(text or ""))
    return len(_punct_re().sub("", t))


def load_registry_limits():
    """从登记件读 `basis.max_chars` / `fields[advice].limit`（读不到给默认并说一声）。"""
    limits = {"basis_max_chars": 60, "advice_limit": 30}
    try:
        raw = open(REG, encoding="utf-8").read()
        m = re.search(r"^\s*max_chars:\s*(\d+)\s*$", raw, re.M)
        if m:
            limits["basis_max_chars"] = int(m.group(1))
        m2 = re.search(r"-\s*\{key:\s*advice,[^}]*limit:\s*(\d+)", raw)
        if m2:
            limits["advice_limit"] = int(m2.group(1))
    except OSError as e:                                          # noqa: F841
        print("[report_conformance] ⚠ 登记件读不到 ⇒ 用默认 60/30：%s" % e, file=sys.stderr)
    return limits


def material_lines(material_text):
    """素材块 ⇒ `{图 N: [第1行文字, 第2行文字, …]}`（阅读顺序，从 1 数）。

    口径与 `kb/l7/registry/prd533-constraints.yaml::location.figure_index_basis` 一致：
    **第 X 处 = 该图内文字块的阅读顺序行号**。
    """
    out = {}
    for m in RE_IMG_BLOCK.finditer(str(material_text or "")):
        n = int(m.group(1))
        body = m.group(2)
        lines = [re.sub(r"\s+", "", x) for x in body.split("\n")]
        out[n] = [x for x in lines if x]
    return out


def check(report, material_text=None):
    """跑五条判据 ⇒ `{ok, fails, stats, untested}`。"""
    limits = load_registry_limits()
    fails = []
    items = parse_items(report)
    fmt = (items[0].get("format") if items else "unknown")
    untested = []

    # ── R0 **量不到不许判绿**（本库最忌「恒绿尺子」）────────────────────────────
    #   真踩过：第一版只认渲染件形状，`--latest` 拿到引擎明细报告 ⇒ 解析出 0 条 ⇒ ok=True。
    #   那不是「报告没问题」，那是「尺子没量到」。⇒ 0 条一律红，除非报告自己说没事。
    if not items:
        if re.search(r"结论[：:]\s*\**\s*(PASS)\b", report) or "问题数：0" in report:
            untested.append("R0：报告说 0 个问题 ⇒ 没有逐条块可量（不算缺陷）")
        else:
            fails.append({"rule": "R0", "msg": "解析出 0 条逐条块 ⇒ **量不到**，不许判绿"
                                               "（不是渲染件 / 结构变了）"})

    # ── R1 未归类 ────────────────────────────────────────────────────────────
    #   两处都要看：① 汇总行 `· 未归类问题：N 个`；② 逐条 `所属类别：未归类`
    #   （逐条那一行归 `unclassed_items` 统，不重复计进汇总 —— 否则一个条目被数两遍）
    unclassed_lines = [ln for ln in report.split("\n")
                       if (UNCLASSED + "问题：") in ln
                       and not re.search(r"所属类别\s*[：:]\s*" + UNCLASSED, ln)]
    unclassed_items = [it["id"] for it in items
                       if UNCLASSED in str(it["fields"].get("所属类别", ""))]
    if unclassed_lines or unclassed_items:
        fails.append({"rule": "R1", "msg": "报告里有「未归类」：汇总行 %d 处、逐条 %s"
                      % (len(unclassed_lines), unclassed_items or "—")})

    # ── R2 问题描述不许占位 ──────────────────────────────────────────────────
    #   引擎明细报告**本来就没有「问题描述」这一格**（它是「原因 + 依据 + 锚点」的明细形状）
    #   ⇒ 那一侧记「未测」，不拿另一侧的格式去判它红（缺件 ≠ 坏件）。
    if fmt == "engine":
        untested.append("R2/R5：引擎明细报告没有「问题描述」「修改建议」两格 ⇒ 这两条未测")
    else:
        ph = [it["id"] for it in items
              if any(p in it["fields"].get("问题描述", "") for p in PLACEHOLDERS)]
        no_desc = [it["id"] for it in items if not it["fields"].get("问题描述", "").strip()]
        if ph:
            fails.append({"rule": "R2", "msg": "问题描述是占位句：%s" % ph})
        if no_desc:
            fails.append({"rule": "R2", "msg": "问题描述整格缺失：%s" % no_desc})

    # ── R3 位置形态 ──────────────────────────────────────────────────────────
    bad_loc = []
    for it in items:
        loc = it["fields"].get("位置", "").strip()
        if not loc:
            bad_loc.append((it["id"], "（缺）"))
            continue
        if not (RE_FIGURE.match(loc) or RE_FIGURE_AREA.match(loc)
                or RE_VIDEO.match(loc) or RE_TEXT.match(loc)):
            bad_loc.append((it["id"], loc))
    if bad_loc:
        fails.append({"rule": "R3", "msg": "位置不落在四形态里：%s" % bad_loc})

    # ── R3b 第 X 处可复核（只在给了素材时判）────────────────────────────────
    if material_text:
        lines_by_img = material_lines(material_text)
        if not lines_by_img:
            untested.append("R3b：素材里没有 `【图 N 内文字｜M 行】` 块 ⇒ 判不了")
        else:
            for it in items:
                loc = it["fields"].get("位置", "").strip()
                m = RE_FIG_NX.search(loc)
                if not m:
                    continue
                n, x = int(m.group(1)), int(m.group(2))
                lines = lines_by_img.get(n) or []
                if not lines:
                    fails.append({"rule": "R3b", "item": it["id"],
                                  "msg": "位置指向 图 %d，但素材里没有这一图的图内文字" % n})
                    continue
                if x > len(lines):
                    fails.append({"rule": "R3b", "item": it["id"],
                                  "msg": "位置说 图 %d 第 %d 处，但该图只有 %d 行文字"
                                      % (n, x, len(lines))})
                    continue
                claim = (it["fields"].get("问题描述", "") + " " + it["fields"].get("依据文档链接", ""))
                claim_n = re.sub(r"\s+", "", claim)
                if lines[x - 1] and lines[x - 1] not in claim_n:
                    fails.append({"rule": "R3b", "item": it["id"],
                                  "msg": "图 %d 第 %d 行是 %r，这一条没引到它 ⇒ 「第 %d 处」不可复核"
                                      % (n, x, lines[x - 1][:24], x)})
    else:
        untested.append("R3b：没给 --material ⇒ 「第 X 处」是否对得上**未测**（不判红也不判绿）")

    # ── R4 依据 ──────────────────────────────────────────────────────────────
    for it in items:
        basis = (it["fields"].get("依据文档链接")
                 or it["fields"].get("依据") or "")
        hit = [w for w in BASIS_FORBIDDEN if w in basis]
        if hit:
            fails.append({"rule": "R4", "item": it["id"],
                          "msg": "依据格里出现源记录排版标记 %s" % hit})
        q = re.search(r"命中\s*[「\"](.+?)[」\"]", basis)
        if q:
            n = count_visible(q.group(1))
            if n > limits["basis_max_chars"]:
                fails.append({"rule": "R4", "item": it["id"],
                              "msg": "依据引文 %d 字 > 上限 %d" % (n, limits["basis_max_chars"])})

    # ── R5 修改建议 ≤30 实词 ────────────────────────────────────────────────
    for it in items:
        sug = it["fields"].get("修改建议", "")
        if not sug.strip():
            continue
        n = advice_chars(sug)
        if n > limits["advice_limit"]:
            fails.append({"rule": "R5", "item": it["id"],
                          "msg": "修改建议 %d 实词 > 上限 %d" % (n, limits["advice_limit"])})

    return {"ok": not fails, "fails": fails,
            "items": len(items), "untested": untested,
            "limits": limits}


# ── 自证（2 正 + 7 反；缺一条本判据就不算数）──────────────────────────────────
_CLEAN = """内容审查报告
【审查结论：REVIEW】共发现 2 处需人工确认。
· 平台与渠道政策类问题：1 个
· 北美本地化与标签要求类问题：1 个
F-01 ｜ 北美本地化与标签要求 ｜ P1
所属类别：北美本地化与标签要求
位置：图片顶部，图 1 第 2 处
问题描述：主文案整段为德语，画面无英文版本
原因：投放美国站，英语消费者读不懂
依据文档链接：独立语义复核（非条款依据，需人工核对）
修改建议：将整段德语主文案改写为英文版本
F-02 ｜ 平台与渠道政策 ｜ P3
所属类别：平台与渠道政策
位置：图 1 第 1 处
问题描述：首行文字只剩残字，不成词
原因：文字被裁切
依据文档链接：《内部正负样本库》第 N-1.337 条 ← 命中「首行文字被裁切」
修改建议：补全或删去被裁切的这个单词
"""

_MATERIAL = """【图 1 内文字｜3 行】
首行文字只剩残字，不成词
主文案整段为德语，画面无英文版本
rowth
【/图 1】
"""


def _bad(**over):
    """把 CLEAN 的 F-01 改成各种坏形状（只改一处，其它保持干净）。"""
    out = []
    for line in _CLEAN.split("\n"):
        for k, v in over.items():
            if line.startswith("所属类别：" if k == "cat" else
                               "位置：" if k == "loc" else
                               "问题描述：" if k == "desc" else
                               "依据文档链接：" if k == "basis" else
                               "修改建议：" if k == "sug" else "\0"):
                line = line.split("：")[0] + "：" + v
        out.append(line)
    return "\n".join(out)


def selftest():
    P, F = [], []

    def chk(name, cond, extra=""):
        (P if cond else F).append(name)
        print("  %s %s%s" % ("✅" if cond else "❌", name, ("  " + extra) if extra else ""))

    # A 干净件 ⇒ 全绿（否则尺子恒红，等于噪音）
    a = check(_CLEAN, _MATERIAL)
    chk("A 干净件 ⇒ 五条全过", a["ok"], str(a["fails"])[:160])

    # B 未归类 ⇒ R1 红
    b = check(_bad(cat=UNCLASSED))
    chk("B 所属类别=未归类 ⇒ R1 红", any(x["rule"] == "R1" for x in b["fails"]))

    # C 占位句 ⇒ R2 红
    c = check(_bad(desc="（本条未提供问题描述）"))
    chk("C 问题描述=占位句 ⇒ R2 红", any(x["rule"] == "R2" for x in c["fails"]))

    # D 裸「图 1」⇒ R3 红（这一条是 Owner 原话里的形状）
    d = check(_bad(loc="图 1"))
    chk("D 位置=图 1（无第 X 处）⇒ R3 红", any(x["rule"] == "R3" for x in d["fails"]))

    # D2 **反向对照**：区域前缀版必须**不判 R3**（2026-10-20 Owner 要的新写法）
    #    ⚠️ 不给素材：这一条只钉「形态」那一半，R3b 另有 G 组管
    d2 = check(_bad(loc="图片底部，图 1 第 1 处"))
    chk("D2 位置=图片底部，图 1 第 1 处 ⇒ 不判 R3（新写法不许被旧尺子误杀）",
        not [x for x in d2["fails"] if x["rule"] == "R3"],
        str([x for x in d2["fails"] if x["rule"] == "R3"])[:160])

    # E 依据含【问题要点】⇒ R4 红
    e = check(_bad(basis="《内部正负样本库》第 S-1.195 条 ← 命中「【问题要点】1. 图1: …」"))
    chk("E 依据含【问题要点】⇒ R4 红", any(x["rule"] == "R4" for x in e["fails"]))

    # E2 依据引文超 60 字 ⇒ R4 红（长度这一半不是恒绿）
    long_quote = "《内部正负样本库》第 S-1.195 条 ← 命中「" + ("原" * 61) + "」"
    e2 = check(_bad(basis=long_quote))
    chk("E2 依据引文 61 字 ⇒ R4 红（长度那一半）", any(x["rule"] == "R4" for x in e2["fails"]))

    # F 修改建议 30 实词 + 标点 ⇒ 绿；31 实词 ⇒ 红（**标点不算字数**这条本身）
    f_ok = check(_bad(sug=("改" * 30) + "，。！？；：、"))
    f_bad = check(_bad(sug=("改" * 31) + "，。！？；：、"))
    chk("F 建议 30 实词＋标点 ⇒ 绿；31 实词 ⇒ R5 红",
        f_ok["ok"] and any(x["rule"] == "R5" for x in f_bad["fails"]),
        "ok=%r / %s" % (f_ok["ok"], [x["rule"] for x in f_bad["fails"]]))

    # G **R3b 反向对照**：位置说「第 2 处」，第 2 行却对不上 ⇒ 红；对上 ⇒ 不红
    mat_wrong = _MATERIAL.replace("主文案整段为德语，画面无英文版本", "这一行跟那条没关系")
    g_bad = check(_CLEAN, mat_wrong)
    g_bad_out = [x for x in g_bad["fails"] if x["rule"] == "R3b"]
    chk("G R3b：声称「图 1 第 2 处」而第 2 行对不上 ⇒ 红", bool(g_bad_out),
        str(g_bad_out)[:120])
    g_ok = check(_CLEAN, _MATERIAL)
    chk("G2 R3b 反向对照：第 2 行就是该条的描述 ⇒ 不红",
        not [x for x in g_ok["fails"] if x["rule"] == "R3b"],
        str([x for x in g_ok["fails"] if x["rule"] == "R3b"])[:120])

    # H 没给素材 ⇒ R3b 记「未测」，不判红（缺件 ≠ 坏件）
    h = check(_CLEAN)
    chk("H 没给素材 ⇒ R3b 未测且不因它判红",
        h["ok"] and any("未测" in u for u in h["untested"]), str(h["untested"])[:120])

    print("\n自证：通过 %d / 失败 %d" % (len(P), len(F)))
    for x in F:
        print("  · 失败：%s" % x)
    return 0 if not F else 3


def latest_report():
    """最近一份**本地报告**（`kb/l7/reports/*.review.md`）；没有 ⇒ None（缺件 ≠ 坏件）。"""
    import glob
    files = glob.glob(os.path.join(os.path.dirname(HERE), "l7", "reports", "*.review.md"))
    if not files:
        return None
    return max(files, key=os.path.getmtime)


def main():
    ap = argparse.ArgumentParser(description="审查报告渲染件一致性（五条 Owner 裁定）")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--fetch-json", help="lark-cli docs +fetch 的 JSON 输出")
    ap.add_argument("--text", help="报告 markdown / 文本文件")
    ap.add_argument("--latest", action="store_true", help="量 kb/l7/reports 里最近一份报告")
    ap.add_argument("--material", help="本单素材（含 `【图 N 内文字｜M 行】` 块）；给了才判 R3b")
    ap.add_argument("--json", action="store_true", help="机读输出")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    if a.latest:
        p = latest_report()
        if not p:
            print("⚠ 未测：`kb/l7/reports/*.review.md` 一份都没有 ⇒ 没有报告可量（缺件 ≠ 坏件）")
            return 0
        a.text = p
        print("量的是：%s" % p)
    report = load_report(a)
    material = None
    if a.material:
        material = open(a.material, encoding="utf-8").read()
    res = check(report, material)
    if a.json:
        print(json.dumps(res, ensure_ascii=False, indent=1))
    else:
        print("报告逐条：%d 条 ｜ 判据：R1 未归类 / R2 问题描述 / R3 位置 / R3b 第X处 / R4 依据 / R5 建议"
              % res["items"])
        for u in res["untested"]:
            print("  ⚠ 未测：%s" % u)
        if res["ok"]:
            print("  ✅ 五条全过")
        for f in res["fails"]:
            print("  ❌ [%s]%s %s" % (f["rule"], (" " + f.get("item", "")) if f.get("item") else "",
                                     f["msg"]))
    return 0 if res["ok"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
