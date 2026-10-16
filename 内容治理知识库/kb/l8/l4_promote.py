#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""l4_promote.py —— L4 **定稿**（候选 → 抽查 → canonical）· 干跑档 + 人工抽查单。

════════════════════════════════════════════════════════════════════════
它补的是什么：**L4 从来没有过活的定稿引擎**
════════════════════════════════════════════════════════════════════════

`kb/l4/registry/l4.json → promotion_rule` 写着这条路：

    候选 → **抽查（人工）** → 定稿写 kb/l4/canonical/<形态>.jsonl（status = stable）
    gate: **抽查未过不得晋升**；晋升不是改名，是**新增定稿记录**

**但活路径上没有任何脚本写 canonical** —— 现有 1480 条 canonical 是
`kb/.work/batch9_canonical.py` / `fix_l4_repromote.py` 这些**历史一次性批次脚本**写的。
本件是第一个把这条路搬上活路径的东西。

════════════════════════════════════════════════════════════════════════
C1–C8：**照抄历史生产者，不自创**（`kb/.work/fix_l4_repromote.py:126` 逐字）
════════════════════════════════════════════════════════════════════════

    C1 唯一条款号 ｜ C2 引用三件套齐全 ｜ C3 正文非空 ｜ C4 与候选逐字一致
    C5 证据单元可在 L2 解析 ｜ C6 证据单元 rule_eligible ｜ C7 kb_version=v0
    C8 发号幂等（不新增号码）

★ **C6 与本库另一把尺子互相印证**（这是本件第一次跑就看到的）：
  干跑实测 —— 待定稿 **2780** 条，C1–C8 通过 **2733**，**被拦 47 条且全部是 C6**；
  而 `check_external_standard_supply.py` 的 **E4** 独立算出退场 **47** 条。
  **两条独立路径给出同一个数** ⇒ 排除项既进不了 E4 的「可为依据」，也过不了 C6。

★★ 而 C6 之所以今天才真能拦人：`kb/l8/l3_scope.py` 2026-10-10 加的
  `rule_eligible_false` 那道门只是**防复发**（重跑不再蒸出），
  已经蒸出来的存量得靠**定稿这道闸**拦住 —— 两者缺一不可。

════════════════════════════════════════════════════════════════════════
三条纪律
════════════════════════════════════════════════════════════════════════

1. **本件默认干跑**（`--apply` 才写）。干跑**一个字节都不落**到 L4。
2. **`--apply` 必须有 `--signoff <文件>`，且该文件必须与本件刚落盘的抽查单
   `sha256` 对得上** —— 否则拒写。这是把 `promotion_rule` 的
   「**抽查未过不得晋升**」从散文变成**代码级阻断**：没人签，就写不进去。
3. **号不回收、候选行不动**（`no_reuse`）：定稿只**追加** canonical 行。

用法：

    python3 kb/l8/l4_promote.py                          # 干跑 ＋ 抽查单（推荐先看这个）
    python3 kb/l8/l4_promote.py --sample 30              # 抽查单抽 30 条
    python3 kb/l8/l4_promote.py --apply --signoff <yaml> # 真写（需签字件）
    python3 kb/l8/l4_promote.py --selftest               # 反向对照（不碰真库）
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
from collections import Counter, OrderedDict

HERE = os.path.dirname(os.path.abspath(__file__))
KB = os.path.dirname(HERE)
L2_UNITS = os.path.join(KB, "l2", "units.jsonl")
L3_SCOPED = os.path.join(KB, "l3", "candidates", "scoped_clauses.jsonl")
L4_REG = os.path.join(KB, "l4", "registry", "l4.json")
L4_CANON = os.path.join(KB, "l4", "canonical")
RETIRED = os.path.join(KB, "l3", "registry", "retired-candidates.yaml")
REPORTS = os.path.join(KB, "l7", "reports")

#: ★ C9「切片检测」的阈值（**保守档**：两个独立信号**同时**成立才拦）。
#:   为什么不是单条：单看长度会挡 93.7%（太狠、可能误杀真条款）；单看词中间挡 68.7%；
#:   **两条同时成立 = 64.9%，是「定长窗口切片」最确定的指纹**。
#:   为什么挂在这里而不是 L3 蒸馏器：**根本不必重跑 L3** —— 定稿闸是候选变成依据的
#:   唯一一道门，C9 一加，切片就永远进不了 canonical。零写、零重跑、零撞车。
C9_WINDOW = (3700, 4100)      # `[3800,4000]` 的**宽一档**带（保守：宁可宽，不要误杀）
C9_ENABLED = True

#: ★ C10「非自然语言残渣」—— **把当年那句写死的占位符变成真判据**。
#:   2026-09-30 起，`kb/l3/rejected.jsonl` 有一个成因被写成
#:   「条款文本不可判定：**非自然语言条款（页面脚本 / base64 编码载荷）**」，
#:   而当时那段代码里**没有任何检测**（见 `诊断-外部标准库蒸馏空壳-20261010.md`）——
#:   它是占位符，**无差别盖住了所有人，包括真条款**，工单照抄过它当实测结论。
#:   ⇒ 现在把**那个现象**写成真判据：命中任一模式即判残渣。**这是当年那句话该有的样子。**
C10_PATTERNS = [
    ("HTML 标签", r"<\s*(img|link|div|span|script|style|a|p|input|meta|iframe|svg|button)\b"),
    ("CSS 规则块", r"\{\s*[a-z-]+\s*:|\.[a-zA-Z][\w-]*\s*\{|@media|data-v-[0-9a-f]+"),
    ("base64 载荷", r"base64,[A-Za-z0-9+/=]{60,}|^[A-Za-z0-9+/]{200,}={0,2}$"),
    ("内联 JS/JSON 残片", r'\\"|\bfunction\s*\(|=>\s*\{|var\s+\w+\s*=|window\.|document\.'),
    ("纯 URL/路径堆", r"^(https?://|//)[^\s]{40,}"),
]
C10_ENABLED = True


def c10_signals(text: str) -> dict:
    """C10 的五个信号 —— **只看这段文字自己**。命中任一 ⇒ 判「非自然语言残渣」。"""
    import re as _re
    t = text or ""
    hits = [name for name, pat in C10_PATTERNS if _re.search(pat, t, _re.I | _re.M)]
    return {"hits": hits, "is_residue": bool(hits)}


def c9_signals(text: str) -> dict:
    """C9 的两个信号 —— **只看这段文字自己**，不看来源、不看号。

    a 两端词中间：开头不是句首（大写字母/数字/中文/引号/括号），结尾不是句末标点。
      —— 定长窗口切下去**必然**从词中间起、到词中间止。
    b 长度贴窗口：字符数落在 `C9_WINDOW`。定长切分的 `char_count` 会挤在一个窄带里
      （实测那批 90% 落在 [3800,4000]，中位 3912）。
    """
    import re as _re
    t = (text or "").strip()
    if not t:
        return {"a_两端词中间": False, "b_长度贴窗口": False, "is_slice": False}
    a_head = not _re.match(r"^[A-Z0-9\u4e00-\u9fff\u201c\(\[\u3010]", t)
    a_tail = not _re.search(r"[.!?\u3002\uff01\uff1f\u201d\"\)\]\u3011]\s*$", t)
    a = bool(a_head and a_tail)
    b = C9_WINDOW[0] <= len(t) <= C9_WINDOW[1]
    return {"a_两端词中间": a, "b_长度贴窗口": b, "is_slice": bool(a and b)}


#: 形态 → 候选源文件（真源 `l4.json → canonical.files[*].source`）
FORM_SOURCE = {"scoped_clause": L3_SCOPED}

#: ★ C1–C8 逐字取自 `kb/.work/fix_l4_repromote.py:126`（历史生产者，**不自创**）。
PROMOTION_BASIS = ["C1 唯一条款号", "C2 引用三件套齐全", "C3 正文非空",
                   "C4 与候选逐字一致", "C5 证据单元可在 L2 解析",
                   "C6 证据单元 rule_eligible", "C7 kb_version=v0",
                   "C8 发号幂等（不新增号码）"]


def _now():
    import datetime
    return datetime.datetime.now().astimezone().replace(microsecond=0).isoformat()


def _sha256_file(p: str) -> str:
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def _last_per_key(path: str, key: str) -> dict:
    """按 key 取**最后一行** —— 本库的追加式口径（同 `l4_retire.py::read_last_per_key`）。

    ★ 候选件实测 6310 行 / 3155 唯一 id（发号后另起一行只加 `article_no`）。
      逐行读全部会把条数**读成两倍**（踩过：47 读成 94）。
    """
    last = {}
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if line:
            d = json.loads(line)
            last[d.get(key)] = d
    return last


# ══════════════════════════════════════════════════════════════════════
# 取数
# ══════════════════════════════════════════════════════════════════════

def load_world() -> dict:
    l4 = json.load(open(L4_REG, encoding="utf-8"))
    assigned = {}
    for _seg, body in ((l4.get("numbering") or {}).get("issued") or {}).items():
        assigned.update(body.get("assigned") or {})
    units = {}
    for line in open(L2_UNITS, encoding="utf-8"):
        line = line.strip()
        if line:
            u = json.loads(line)
            units[u.get("unit_id")] = u
    canon = {}
    for form in ("scoped_clause",):
        p = os.path.join(L4_CANON, form + ".jsonl")
        if os.path.exists(p):
            canon[form] = _last_per_key(p, "clause_id")
    retired = {}
    if os.path.exists(RETIRED):
        try:
            import yaml  # noqa: PLC0415
            d = yaml.safe_load(open(RETIRED, encoding="utf-8")) or {}
            retired = {r.get("clause_id"): r for r in (d.get("retired") or [])}
        except Exception:  # noqa: BLE001
            retired = {}
    return {"assigned": assigned, "units": units, "canon": canon,
            "retired": retired, "l4": l4}


# ══════════════════════════════════════════════════════════════════════
# C1–C8
# ══════════════════════════════════════════════════════════════════════

def judge(c: dict, world: dict, seen_art: dict) -> tuple:
    """对一条候选跑 C1–C8。返回 `(passed: bool, failed: [码], detail: {})`。"""
    cid = c.get("clause_id")
    art = world["assigned"].get(cid) or c.get("article_no")
    units = world["units"]
    canon_arts = world["canon_arts"]
    bad = []
    d = {}

    if not art:
        bad.append("C1")
    elif art in canon_arts:
        bad.append("C1")
        d["C1"] = "号 %s 已被已定稿行占用" % art
    elif art in seen_art and seen_art[art] != cid:
        bad.append("C1")
        d["C1"] = "本批重号：%s 与 %s" % (cid, seen_art[art])
    seen_art.setdefault(art, cid)

    if not (c.get("anchor") and c.get("source_sha256") and c.get("unit_id")):
        bad.append("C2")
        d["C2"] = {"anchor": bool(c.get("anchor")),
                   "source_sha256": bool(c.get("source_sha256")),
                   "unit_id": bool(c.get("unit_id"))}

    if not str(c.get("clause_text") or "").strip():
        bad.append("C3")

    if c.get("form") != "scoped_clause":
        bad.append("C4")
        d["C4"] = "form=%r ≠ scoped_clause" % c.get("form")

    uid = c.get("unit_id")
    u = units.get(uid)
    if u is None:
        bad.append("C5")
        d["C5"] = "unit %s 不在 kb/l2/units.jsonl 里" % uid
    elif u.get("rule_eligible") is False:
        bad.append("C6")
        d["C6"] = "unit %s 的 rule_eligible=false（%s）" % (
            uid, world["retired"].get(cid, {}).get("reason_code") or "已声明排除")

    if c.get("kb_version") != "v0":
        bad.append("C7")
        d["C7"] = "kb_version=%r" % c.get("kb_version")

    if cid not in world["assigned"]:
        bad.append("C8")
        d["C8"] = "该候选没有号（发号幂等要求号已在台账里）"

    # ── C9 切片检测（**不是** promotion_basis 里的历史 C1–C8，是本件新加的）──────
    #   ★ 为什么必须加：C1–C8 只核**结构完整性**，对「这段文字是不是一条款」**一句话都没问**。
    #     实测那批 2733 条里 64.9% 是网页定长切片（`ant seat Seborrheic dermatitis, 253, 281`），
    #     **C1–C8 全过** —— 这正是 `promotion_rule` 要人工抽查的原因；C9 是把人能一眼看出的
    #     那个特征**机器化**，替人挡掉最典型的那一批。
    if C9_ENABLED:
        sig = c9_signals(c.get("clause_text"))
        d["C9"] = sig
        if sig["is_slice"]:
            bad.append("C9")

    # ── C10 非自然语言残渣（HTML / CSS / base64 / 内联 JS / 纯 URL 堆）──────────
    if C10_ENABLED:
        sig10 = c10_signals(c.get("clause_text"))
        d["C10"] = sig10
        if sig10["is_residue"]:
            bad.append("C10")

    return (not bad), sorted(set(bad)), d


def plan(world: dict, form: str = "scoped_clause") -> dict:
    """算出「会写哪些行」——**只算不写**。"""
    cand = _last_per_key(FORM_SOURCE[form], "clause_id")
    canon = world["canon"].get(form, {})
    world = dict(world)
    world["canon_arts"] = {d.get("article_no") for d in canon.values()}
    pending = [c for cid, c in cand.items()
               if cid in world["assigned"] and cid not in canon]
    pending.sort(key=lambda c: world["assigned"].get(c["clause_id"]) or "")
    seen_art, ok, blocked = {}, [], []
    for c in pending:
        good, bad, det = judge(c, world, seen_art)
        (ok if good else blocked).append({"clause_id": c["clause_id"],
                                          "article_no": world["assigned"].get(c["clause_id"]),
                                          "unit_id": c.get("unit_id"),
                                          "resource_id": c.get("resource_id"),
                                          "failed": bad, "detail": det,
                                          "row": c})
    reasons = Counter(x for b in blocked for x in b["failed"])
    by_c9 = [b for b in blocked if "C9" in b["failed"]]
    only_c9 = [b for b in blocked if b["failed"] == ["C9"]]
    by_c10 = [b for b in blocked if "C10" in b["failed"]]
    return {"form": form, "n_candidates": len(cand), "n_canonical": len(canon),
            "n_pending": len(pending), "n_ok": len(ok), "n_blocked": len(blocked),
            "n_blocked_by_c9": len(by_c9), "n_blocked_only_by_c9": len(only_c9),
            "n_blocked_by_c10": len(by_c10),
            "c9_window": list(C9_WINDOW), "c9_enabled": C9_ENABLED,
            "blocked_by": dict(reasons), "ok": ok, "blocked": blocked,
            "canonical_lines_after": len(canon) + len(ok),
            "basis_sha256_12": {
                "kb/l3/candidates/scoped_clauses.jsonl": _sha256_file(L3_SCOPED)[:12],
                "kb/l2/units.jsonl": _sha256_file(L2_UNITS)[:12],
                "kb/l4/registry/l4.json": _sha256_file(L4_REG)[:12]}}


# ══════════════════════════════════════════════════════════════════════
# 人工抽查单（分层抽样）
# ══════════════════════════════════════════════════════════════════════

def sample_fingerprint(pl: dict, rows: list) -> str:
    """抽查单的指纹 —— **对结构化内容算，不对渲染文本算**。

    为什么不对 md 文本算：那会把排版/措辞改动也算成「数据变了」，
    于是改一个字就让人重签一次；而签字要绑的是**「你看的是哪一批条目」**。
    绑的字段：形态 / 待定稿数 / 通过数 / 每条 (条款号, clause_id, unit_id, 来源, 指纹)。
    """
    payload = {"form": pl["form"], "n_pending": pl["n_pending"], "n_ok": pl["n_ok"],
               "rows": [[r.get("article_no"), r.get("clause_id"), r.get("unit_id"),
                         r.get("resource_id"), r.get("row", {}).get("source_sha256")]
                        for r in rows]}
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False,
                                     sort_keys=True).encode("utf-8")).hexdigest()


def sample_rows(pl: dict, n: int = 20, seed: int = 20261010) -> list:
    """**分层抽样**：按 `resource_id` 分层（来源是"这到底是不是真条款"的关键），
    每层按条款号升序取前若干，保证**每层都能被看到**、且**可复现**（固定种子 + 确定性顺序）。

    为什么不用 `random.sample`：抽查单是要**给人签字**的，必须**同日同数据出同一份**，
    否则签过的那份和后来跑出来的对不上（本件用 sha 把签字绑到抽查单上，更输不起这个）。
    """
    import hashlib as _h
    by_res: dict = {}
    for r in pl["ok"]:
        by_res.setdefault(r.get("resource_id"), []).append(r)
    res_list = sorted(by_res, key=lambda k: (-len(by_res[k]), str(k)))
    out, i = [], 0
    # 轮转取样：每层轮流取一条 ⇒ 层数多时也不会被最大的一层吃满
    while len(out) < n and any(by_res[r] for r in res_list):
        r = res_list[i % len(res_list)]
        if by_res[r]:
            row = by_res[r].pop(0)
            row = dict(row)
            row["_res_size"] = None
            out.append(row)
        i += 1
        if i > n * len(res_list) + 10:
            break
    out.sort(key=lambda x: str(x.get("article_no") or ""))
    return out


def render_sample(pl: dict, rows: list, n_total: int) -> str:
    L = []
    L.append("# L4 定稿 · 人工抽查单（任务拆解 目标 5 收口 · PRD §7.1 外部标准库）")
    L.append("")
    L.append("生成时间：%s" % _now())
    L.append("")
    L.append("## 这是什么、要你做什么")
    L.append("")
    L.append("`kb/l4/registry/l4.json → promotion_rule` 明写 **「候选 → 抽查（人工）→ 定稿」**"
             "且 **「抽查未过不得晋升」**。本单就是那道抽查。")
    L.append("")
    L.append("**要你判的只有一件事**：下面这些条款，**是不是真条款**（能不能当审查依据）。")
    L.append("机器闸门 C1–C8 已经过了（本单里的每一条都是过的），**机器过不了的那 47 条不在单上**。")
    L.append("")
    L.append("## 本批规模")
    L.append("")
    L.append("| 项 | 值 |")
    L.append("|---|---|")
    L.append("| 形态 | `%s`（E-1 段 · 外部标准库） |" % pl["form"])
    L.append("| 候选总数 | %d |" % pl["n_candidates"])
    L.append("| 已定稿 | %d |" % pl["n_canonical"])
    L.append("| **待定稿** | **%d** |" % pl["n_pending"])
    L.append("| **C1–C8 通过** | **%d** |" % pl["n_ok"])
    L.append("| 被机器拦下 | %d（%s） |"
             % (pl["n_blocked"],
                "、".join("%s×%d" % (k, v) for k, v in sorted(pl["blocked_by"].items())) or "—"))
    L.append("| 定稿后 canonical 行数 | %d → **%d** |"
             % (pl["n_canonical"], pl["canonical_lines_after"]))
    L.append("")
    L.append("★ **抽样口径**：按来源资源**分层轮转**取样（来源是判断「是不是真条款」的关键），"
             "本单 %d 条 / 全批 %d 条。**确定性**（同日同数据出同一份），"
             "签字时会把本单的 sha256 绑进去。" % (len(rows), pl["n_ok"]))
    L.append("")
    L.append("## 抽查条目")
    L.append("")
    for i, r in enumerate(rows, 1):
        txt = str(r.get("row", {}).get("clause_text") or "")
        L.append("### %d. `%s`" % (i, r.get("article_no")))
        L.append("")
        L.append("| 项 | 值 |")
        L.append("|---|---|")
        L.append("| 条款号 | **%s** |" % r.get("article_no"))
        L.append("| clause_id | `%s` |" % r.get("clause_id"))
        L.append("| 来源资源 | `%s` |" % r.get("resource_id"))
        L.append("| L2 单元 | `%s` |" % r.get("unit_id"))
        L.append("| 锚点 anchor | `%s` |" % r.get("row", {}).get("anchor"))
        L.append("| 指纹 source_sha256 | `%s` |" % r.get("row", {}).get("source_sha256"))
        L.append("| 证据级 | %s |" % r.get("row", {}).get("evidence_strength"))
        L.append("| 字符数 | %s |" % r.get("row", {}).get("char_count"))
        L.append("")
        L.append("**正文（前 500 字，逐字）**：")
        L.append("")
        L.append("```")
        L.append(txt[:500] + ("…" if len(txt) > 500 else ""))
        L.append("```")
        L.append("")
        L.append("**判断**：☐ 是真条款，可作依据　☐ 不是（说明：＿＿＿＿）")
        L.append("")
    L.append("## 签法")
    L.append("")
    L.append("看完后写一份签字件（YAML），`--apply` 时传进来：")
    L.append("")
    L.append("```yaml")
    L.append("decision: approved          # approved / rejected")
    L.append("by: <你的名字>")
    L.append("at: <YYYY-MM-DDTHH:MM:SS+08:00>")
    L.append("sample_sha256: <本单的 sha256，见下>")
    L.append("notes: <可留空；rejected 时请写清理由>")
    L.append("```")
    L.append("")
    L.append("```")
    L.append("本抽查单 sha256：%s" % pl.get("_sample_sha256", "（未计算）"))
    L.append("```")
    L.append("")
    L.append("★ **这个 sha 把签字绑在本单上** —— 数据一变、单子一变，旧签字立刻失效（代码级阻断）。")
    L.append("")
    return "\n".join(L) + "\n"


def _safe_write_md(path: str, text: str) -> None:
    """`.md` 走 `/bin/cp` 通道（python 直写 `.md` ⇒ **宿主**读到的比真值多 4096 字节）。"""
    d = os.path.dirname(path) or "."
    os.makedirs(d, exist_ok=True)
    tmp = os.path.join(d, ".%s.swtmp" % os.path.basename(path))
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(text)
        import subprocess
        subprocess.run(["/bin/cp", tmp, path], check=True)
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass
    if open(path, encoding="utf-8").read() != text:
        raise RuntimeError("安全写盘回读不符：%s" % path)


# ══════════════════════════════════════════════════════════════════════
# 签字闸门
# ══════════════════════════════════════════════════════════════════════

def check_signoff(path: str, sample_sha: str) -> tuple:
    """核签字件。返回 `(ok, why)`。**任何一项不符 ⇒ 拒写。**

    这是 `promotion_rule` 的「**抽查未过不得晋升**」从散文变代码的那一处。
    """
    if not path:
        return False, "没有 --signoff ⇒ 拒写（`promotion_rule`：抽查未过不得晋升）"
    if not os.path.exists(path):
        return False, "签字件不存在：%s" % path
    try:
        import yaml  # noqa: PLC0415
        d = yaml.safe_load(open(path, encoding="utf-8")) or {}
    except Exception as e:  # noqa: BLE001
        return False, "签字件读不了（%r）" % e
    if d.get("decision") != "approved":
        return False, "签字件 decision=%r ≠ approved" % d.get("decision")
    if not str(d.get("by") or "").strip():
        return False, "签字件没有 by（**不许匿名签字**）"
    if not str(d.get("at") or "").strip():
        return False, "签字件没有 at（签于何时）"
    if d.get("sample_sha256") != sample_sha:
        return False, ("签字件绑的抽查单 sha 与当前不符：件里 %r ／ 当前 %s"
                       "（数据或单子变了 ⇒ 旧签字失效，必须重看）"
                       % (d.get("sample_sha256"), sample_sha))
    return True, ""


# ══════════════════════════════════════════════════════════════════════
# 主流程
# ══════════════════════════════════════════════════════════════════════

def run(apply_now: bool, sample_n: int, signoff: str | None,
        out_dir: str = REPORTS, world: dict | None = None,
        canon_path: str | None = None) -> int:
    world = world or load_world()
    pl = plan(world)
    rows = sample_rows(pl, sample_n)
    sha = sample_fingerprint(pl, rows)
    pl["_sample_sha256"] = sha
    sample_md = render_sample(pl, rows, sample_n)

    print("L4 定稿 · 干跑（形态 %s · 外部标准库 · E-1 段）" % pl["form"])
    print("-" * 74)
    print("  候选 %d ｜ 已定稿 %d ｜ **待定稿 %d**" % (pl["n_candidates"], pl["n_canonical"],
                                                     pl["n_pending"]))
    print("  C1–C8 **通过 %d** ｜ 被拦 %d %s"
          % (pl["n_ok"], pl["n_blocked"],
             ("（%s）" % "、".join("%s×%d" % (k, v) for k, v in sorted(pl["blocked_by"].items())))
             if pl["blocked_by"] else ""))
    print("  其中 C9 切片检测挡下 **%d** 条（阈值 a两端词中间 ∧ b长度∈%s）"
          % (pl.get("n_blocked_by_c9", 0), list(C9_WINDOW)))
    print("  定稿后 canonical 行数：%d → **%d**" % (pl["n_canonical"], pl["canonical_lines_after"]))
    print("  抽查单：%d 条（分层轮转；确定性）" % len(rows))
    print("-" * 74)

    os.makedirs(out_dir, exist_ok=True)
    sp = os.path.join(out_dir, "l4-promote-sample-latest.md")
    _safe_write_md(sp, sample_md)
    jp = os.path.join(out_dir, "l4-promote-dryrun-latest.json")
    slim = {k: v for k, v in pl.items() if k not in ("ok", "blocked")}
    slim["blocked_sample"] = pl["blocked"][:20]
    slim["sample_sha256"] = sha
    with open(jp, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(slim, ensure_ascii=False, indent=2) + "\n")
    # ★「留痕不删」：被 C9 挡下的逐条落一份名单（含两个信号的读数）——
    #   它们**仍在候选件里**（本件不改候选件），只是**永远进不了 canonical**。
    #   判据是**自足可复算**的（只看文字自己），所以**不另立 registry 声明件** ——
    #   加了反而是第二份真源。名单带阈值与数据指纹，日后改阈值时看得出当时的判断依据。
    bp = os.path.join(out_dir, "l4-promote-blocked-slice-latest.json")
    blocked_c9 = [{"clause_id": b["clause_id"], "article_no": b["article_no"],
                   "resource_id": b["resource_id"], "unit_id": b["unit_id"],
                   "signals": b["detail"].get("C9"),
                   "len": len(str(b["row"].get("clause_text") or "")),
                   "head": str(b["row"].get("clause_text") or "")[:60],
                   "failed": b["failed"]}
                  for b in pl["blocked"] if "C9" in b["failed"]]
    with open(bp, "w", encoding="utf-8") as fh:
        fh.write(json.dumps({"generated_at": _now(), "threshold": {"c9_window": list(C9_WINDOW)},
                             "n_blocked_by_c9": len(blocked_c9),
                             "basis_sha256_12": pl["basis_sha256_12"],
                             "note": "候选件**未动**；这些条仍在 kb/l3/candidates/scoped_clauses.jsonl 里，"
                                     "只是**永远进不了 canonical**（定稿闸 C9 挡）。",
                             "blocked": blocked_c9}, ensure_ascii=False, indent=2) + "\n")
    print("  产物：%s ｜ %s ｜ %s" % (sp, jp, bp))
    print("  抽查单 sha256：%s" % sha)

    if not apply_now:
        print("-" * 74)
        print("[干跑] **一个字节都没写**。加 `--apply --signoff <签字件>` 才落盘。")
        return 0

    ok, why = check_signoff(signoff, sha)
    if not ok:
        print("-" * 74)
        print("[拒写] %s" % why)
        return 3

    target = canon_path or os.path.join(L4_CANON, pl["form"] + ".jsonl")
    rows_out = []
    for r in pl["ok"]:
        c = dict(r["row"])
        c.update({"status": "stable", "promoted_from": "provisional",
                  "promoted_at_run": "PROMOTE-%s" % _now()[:10].replace("-", ""),
                  "promotion_basis": PROMOTION_BASIS})
        rows_out.append(c)
    before = _sha256_file(target) if os.path.exists(target) else None
    bak = None
    if before:
        bak = target + ".bak-pre-promote-" + _now().replace(":", "").replace("-", "")[:15]
        shutil.copy2(target, bak)
    with open(target, "a", encoding="utf-8") as fh:
        for c in rows_out:
            fh.write(json.dumps(c, ensure_ascii=False) + "\n")
    after_lines = sum(1 for l in open(target, encoding="utf-8") if l.strip())
    print("-" * 74)
    print("[落盘] 追加 %d 行 → %s（现 %d 行）" % (len(rows_out), target, after_lines))
    if bak:
        print("       备份：%s" % bak)
    print("       ★ 候选件与号**一个字没动**（no_reuse）")
    return 0


# ══════════════════════════════════════════════════════════════════════
# 反向对照
# ══════════════════════════════════════════════════════════════════════

def _selftest() -> int:
    ok = fail = 0
    fails: list[str] = []

    def ck(n, c, ex=""):
        nonlocal ok, fail
        if c:
            ok += 1
        else:
            fail += 1
            fails.append("%s %s" % (n, ex))

    d = tempfile.mkdtemp(prefix="l4promote-", dir="/tmp")
    try:
        units = os.path.join(d, "units.jsonl")
        scoped = os.path.join(d, "scoped.jsonl")
        l4 = os.path.join(d, "l4.json")
        canon = os.path.join(d, "canonical")
        os.makedirs(canon)
        with open(units, "w", encoding="utf-8") as f:
            f.write(json.dumps({"unit_id": "u1", "rule_eligible": True}) + "\n")
            f.write(json.dumps({"unit_id": "u2", "rule_eligible": False}) + "\n")
        with open(scoped, "w", encoding="utf-8") as f:
            base = {"form": "scoped_clause", "kb_version": "v0", "kb_type": "external_standard",
                    "anchor": "#a", "source_sha256": "s" * 8, "clause_text": "正文",
                    "resource_id": "url__x", "status": "provisional"}
            f.write(json.dumps(dict(base, clause_id="c1", unit_id="u1")) + "\n")   # 应过
            f.write(json.dumps(dict(base, clause_id="c1", unit_id="u1",
                                    article_no="E-1.1")) + "\n")                    # 追加行
            f.write(json.dumps(dict(base, clause_id="c2", unit_id="u2")) + "\n")   # C6 应拦
            f.write(json.dumps(dict(base, clause_id="c3", unit_id="u1",
                                    clause_text="")) + "\n")                        # C3 应拦
            f.write(json.dumps(dict(base, clause_id="c4", unit_id="u9")) + "\n")   # C5 应拦
            f.write(json.dumps(dict(base, clause_id="c5", unit_id="u1",
                                    kb_version="v9")) + "\n")                       # C7 应拦
            f.write(json.dumps(dict(base, clause_id="c6", unit_id="u1",
                                    anchor="")) + "\n")                             # C2 应拦
        json.dump({"numbering": {"issued": {"E-1": {"assigned": {
            "c1": "E-1.1", "c2": "E-1.2", "c3": "E-1.3", "c4": "E-1.4",
            "c5": "E-1.5", "c6": "E-1.6"}}}}}, open(l4, "w", encoding="utf-8"))
        open(os.path.join(canon, "scoped_clause.jsonl"), "w").close()

        w = {"assigned": {}, "units": {}, "canon": {"scoped_clause": {}},
             "retired": {}, "l4": {}}
        # 手工装配 world（路径已固定常量，这里直接喂内存数据）
        w["assigned"] = json.load(open(l4, encoding="utf-8"))["numbering"]["issued"]["E-1"]["assigned"]
        w["units"] = {"u1": {"unit_id": "u1", "rule_eligible": True},
                      "u2": {"unit_id": "u2", "rule_eligible": False}}
        w["canon"] = {"scoped_clause": {}}
        w["canon_arts"] = set()

        cand = _last_per_key(scoped, "clause_id")
        ck("①追加式去重：7 行 ⇒ 6 个候选", len(cand) == 6, len(cand))
        seen, res = {}, []
        for c in cand.values():
            g, b, _ = judge(c, w, seen)
            res.append((c["clause_id"], g, b))
        by = {k: (g, b) for k, g, b in res}
        ck("②c1 应通过", by["c1"][0], by["c1"])
        ck("③C6 拦 rule_eligible=false", not by["c2"][0] and "C6" in by["c2"][1], by["c2"])
        ck("④C3 拦空正文", not by["c3"][0] and "C3" in by["c3"][1], by["c3"])
        ck("⑤C5 拦 L2 找不到的单元", not by["c4"][0] and "C5" in by["c4"][1], by["c4"])
        ck("⑥C7 拦 kb_version≠v0", not by["c5"][0] and "C7" in by["c5"][1], by["c5"])
        ck("⑦C2 拦缺引用三件套", not by["c6"][0] and "C2" in by["c6"][1], by["c6"])

        # ⑧ C1 反向：号撞已定稿行 ⇒ 拦
        w2 = dict(w, canon_arts={"E-1.1"})
        seen2 = {}
        g8, b8, _ = judge(cand["c1"], w2, seen2)
        ck("⑧C1 拦撞号", not g8 and "C1" in b8, b8)
        # ⑨ C1 反向：**本批重号** ⇒ 拦（两条不同 clause_id 拿到同一个号）
        import copy as _copy
        w3 = _copy.deepcopy(w)
        w3["canon_arts"] = set()
        w3["assigned"] = dict(w["assigned"], cX="E-1.1")     # cX 与 c1 同号
        seen3 = {}
        _g, _b, _ = judge(cand["c1"], w3, seen3)             # 先占住 E-1.1
        c_dup = dict(cand["c1"], clause_id="cX")
        g9, b9, _ = judge(c_dup, w3, seen3)
        ck("⑨C1 拦本批重号", not g9 and "C1" in b9, b9)
        # ⑩ C8 反向：候选没有号 ⇒ 拦
        w4 = dict(w, assigned={k: v for k, v in w["assigned"].items() if k != "c1"})
        g10, b10, _ = judge(cand["c1"], w4, {})
        ck("⑩C8 拦无号候选", not g10 and "C8" in b10, b10)

        # ⑪ ★ 签字闸门：没有签字件 ⇒ 拒写
        o, why = check_signoff(None, "abc")
        ck("⑪无签字件 ⇒ 拒写", (not o) and "拒写" in why, why)
        # ⑫ decision≠approved ⇒ 拒
        sp = os.path.join(d, "so.yaml")
        import yaml as _y
        _y.safe_dump({"decision": "rejected", "by": "张三", "at": "x", "sample_sha256": "abc"},
                     open(sp, "w", encoding="utf-8"), allow_unicode=True)
        o, why = check_signoff(sp, "abc")
        ck("⑫decision≠approved ⇒ 拒写", not o and "approved" in why, why)
        # ⑬ 匿名签字 ⇒ 拒
        _y.safe_dump({"decision": "approved", "by": "", "at": "x", "sample_sha256": "abc"},
                     open(sp, "w", encoding="utf-8"), allow_unicode=True)
        o, why = check_signoff(sp, "abc")
        ck("⑬匿名签字 ⇒ 拒写", not o and "匿名" in why, why)
        # ⑭ ★ sha 对不上 ⇒ 拒（数据变了旧签字失效）
        _y.safe_dump({"decision": "approved", "by": "张三", "at": "x", "sample_sha256": "别的"},
                     open(sp, "w", encoding="utf-8"), allow_unicode=True)
        o, why = check_signoff(sp, "abc")
        ck("⑭抽查单 sha 对不上 ⇒ 拒写", not o and "旧签字失效" in why, why)
        # ⑮ 全对 ⇒ 放行
        _y.safe_dump({"decision": "approved", "by": "张三", "at": "x", "sample_sha256": "abc"},
                     open(sp, "w", encoding="utf-8"), allow_unicode=True)
        o, why = check_signoff(sp, "abc")
        ck("⑮签字齐全 ⇒ 放行", o, why)

        # ⑯ C9 切片检测：反向对照 ×4
        _slice = "ant seat Seborrheic dermatitis, 253, 281" + "x" * 3900
        _clause = "Section 4.2 车内场景：不得呈现未使用安全座椅的画面。" + "正文" * 1900
        ck("⑯a 定长切片被 C9 判为切片", c9_signals(_slice)["is_slice"], c9_signals(_slice))
        ck("⑯b 正常条款行文**不**被判切片", not c9_signals(_clause)["is_slice"], c9_signals(_clause))
        ck("⑯c 短句不判切片（长度不贴窗口）",
           not c9_signals("不得使用最安全。")["is_slice"], c9_signals("不得使用最安全。"))
        ck("⑯d 两端完整但长度贴窗口 ⇒ **不**判切片（须两个信号同时成立）",
           not c9_signals("A" + "x" * 3900 + ".")["is_slice"],
           c9_signals("A" + "x" * 3900 + "."))
        ck("⑯e 词中间但长度不贴窗口 ⇒ **不**判切片",
           not c9_signals("artial sentence with no ending")["is_slice"],
           c9_signals("artial sentence with no ending"))
        # ⑯f 关掉 C9 ⇒ 那条切片必须放行（证明这道门真的在起作用）
        global C9_ENABLED
        _k = C9_ENABLED
        try:
            C9_ENABLED = False
            _w = {"assigned": {"cS": "E-1.99"}, "units": {"uS": {"unit_id": "uS"}},
                  "canon": {"scoped_clause": {}}, "canon_arts": set(), "retired": {}}
            _c = {"clause_id": "cS", "kb_version": "v0", "form": "scoped_clause",
                  "anchor": "#a", "source_sha256": "s", "unit_id": "uS", "clause_text": _slice}
            _g_off, _b_off, _ = judge(_c, _w, {})
            C9_ENABLED = True
            _g_on, _b_on, _ = judge(_c, _w, {})
            ck("⑯f 关掉 C9 ⇒ 放行；打开 ⇒ 拦（这道门真在起作用）",
               _g_off and (not _g_on) and "C9" in _b_on, (_g_off, _g_on, _b_on))
        finally:
            C9_ENABLED = _k

        # ⑯g–k C10 非自然语言残渣：反向对照 ×5（**当年那句占位符该有的样子**）
        ck("⑯g HTML 残渣被 C10 判残渣",
           c10_signals('<img src="//x/a.png?v=17">正文')["is_residue"],
           c10_signals('<img src="//x/a.png?v=17">正文'))
        ck("⑯h CSS 规则块被 C10 判残渣",
           c10_signals('.card-media--vertical[data-v-b3e04aaa]{justify-content:center}')["is_residue"],
           c10_signals('.card-media--vertical[data-v-b3e04aaa]{justify-content:center}'))
        ck("⑯i base64 载荷被 C10 判残渣",
           c10_signals("data:image/png;base64," + "iVBORw0KGgoA" * 12)["is_residue"],
           c10_signals("data:image/png;base64," + "iVBORw0KGgoA" * 12))
        ck("⑯j 正常条款行文**不**判残渣",
           not c10_signals("Section 4.2 车内场景：不得呈现未使用安全座椅的画面。"
                           "本条款适用于所有面向美国市场的视频与图片素材。")["is_residue"],
           c10_signals("Section 4.2 车内场景：不得呈现未使用安全座椅的画面。"))
        ck("⑯k 中文条款（含书名号/冒号/数字）不误判",
           not c10_signals("婴儿睡姿为仰卧，不可趴睡（不到1岁绝对不可趴睡）；"
                           "婴儿床内无玩偶/被子/枕头。")["is_residue"],
           c10_signals("婴儿睡姿为仰卧，不可趴睡（不到1岁绝对不可趴睡）；"))
        # ⑯l 关掉 C10 ⇒ 放行；打开 ⇒ 拦
        global C10_ENABLED
        _k10 = C10_ENABLED
        try:
            _w10 = {"assigned": {"cR": "E-1.98"}, "units": {"uR": {"unit_id": "uR"}},
                    "canon": {"scoped_clause": {}}, "canon_arts": set(), "retired": {}}
            _c10 = {"clause_id": "cR", "kb_version": "v0", "form": "scoped_clause",
                    "anchor": "#a", "source_sha256": "s", "unit_id": "uR",
                    "clause_text": '<link rel="shortcut icon" href="data:image/png;base64,'
                                   + "iVBORw0KGgoA" * 12 + '">'}
            C10_ENABLED = False
            _go, _bo, _ = judge(_c10, _w10, {})
            C10_ENABLED = True
            _gn, _bn, _ = judge(_c10, _w10, {})
            ck("⑯l 关掉 C10 ⇒ 放行；打开 ⇒ 拦（这道门真在起作用）",
               _go and (not _gn) and "C10" in _bn, (_go, _gn, _bn))
        finally:
            C10_ENABLED = _k10

        # ⑯ C1–C8 清单必须与历史生产者**逐字一致**（防有人改口径）
        ck("⑯C1–C8 清单逐字", PROMOTION_BASIS == [
            "C1 唯一条款号", "C2 引用三件套齐全", "C3 正文非空", "C4 与候选逐字一致",
            "C5 证据单元可在 L2 解析", "C6 证据单元 rule_eligible", "C7 kb_version=v0",
            "C8 发号幂等（不新增号码）"], PROMOTION_BASIS)

        # ⑰ 抽样确定性：同日同数据出同一份
        plx = {"ok": [{"clause_id": "x%d" % i, "article_no": "E-1.%d" % i,
                       "resource_id": "r%d" % (i % 3)} for i in range(30)]}
        s1 = [r["clause_id"] for r in sample_rows(plx, 9)]
        s2 = [r["clause_id"] for r in sample_rows(plx, 9)]
        ck("⑰抽样确定性", s1 == s2, (s1, s2))
        ck("⑰b 分层：抽到的来源 ≥2 种", len({r["resource_id"] for r in sample_rows(plx, 9)}) >= 2,
           {r["resource_id"] for r in sample_rows(plx, 9)})
    finally:
        shutil.rmtree(d, ignore_errors=True)

    print("l4_promote --selftest：%d/%d" % (ok, ok + fail))
    for f in fails:
        print("  ✗", f)
    return 0 if fail == 0 else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="L4 定稿（候选→抽查→canonical）· 默认干跑")
    ap.add_argument("--apply", action="store_true", help="真写 canonical（需 --signoff）")
    ap.add_argument("--signoff", help="人工抽查签字件（YAML）")
    ap.add_argument("--sample", type=int, default=20, help="抽查单条数（默认 20）")
    ap.add_argument("--out-dir", default=REPORTS)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return _selftest()
    return run(a.apply, a.sample, a.signoff, out_dir=a.out_dir)


if __name__ == "__main__":
    sys.exit(main())
