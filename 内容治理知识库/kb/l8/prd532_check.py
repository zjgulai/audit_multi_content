#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""prd532_check.py —— **PRD §5.3.2（rev 107）**的接线判据：三值 ＋ 一个标签 ＋ 四个桶

## 它解决什么（2026-10-19 一天两轮 ＋ 2026-10-22 一轮）

Owner 10-19 先问「卡片态必须是 4 态，这个同步知识库了吗」，随后把 PRD §5.3.2 **原文**贴来：
**SUGGEST 是「PASS 的附属标签」**。拉 PRD 内嵌表核对：sheet `xcdTpv` 当天从 **rev 96 → rev 101**，
四行定义全改（PASS 定义新增「可包含 SUGGEST 建议」、列头改「系统流转动作」）。

10-22 再核一次，发现**远端已经走到 rev 107**，而本判据当时只比两个本地文件
（真源 `meta.revision` vs `_prd-20261019/…rev101.json`）——**两个一起陈旧就互相印证，恒绿**：

    实测（2026-10-22 16:3x）：远端 revision=107，`prd532_check` 仍报
    「PASS（三值＋标签＋四桶 六处一致）」、退出码 0 ⇒ **那句绿证明的是库内一致，
    不是「跟今天的 PRD 一致」**。

rev 107 把形状又降了一档：表头改「**主状态 / 定义 / 附属信息 / 动作**」，
**只剩 PASS／REVIEW／BLOCK 三行**，SUGGEST 连「一行」都不是了 —— 它只活在 PASS 的
「附属信息」列（「可附带 SUGGEST（如措辞优化建议）」）与 §5.3.2 正文的「SUGGEST 规则」段。

⇒ PRD 自己的口径仍是 **三值 ＋ 一个标签 ＋ 四个统计桶**：
    `decision` = PASS / REVIEW / BLOCK（＋ 拒答 NEEDS_INPUT，非 PRD 态）
    `SUGGEST`  = PASS 的附属标签（`decision=PASS ∧ suggestions≠∅`），**不占主状态行**
    统计四桶  = PASS ／ **PASS＋建议** ／ REVIEW ／ BLOCK（§10.2「汇总四态结论」）

## 判据面（A–G）

    A    源侧   真源**三个主状态**齐；`blocks_flow` 与 PRD 一致；**SUGGEST 不许出现在 states 里**；
                `attached`（附属信息列）非空；**标签语义段在案**（`label_semantics`）
    A2   出处   与 PRD 内嵌表**逐字**核对：`定义 / 附属信息 / 动作` 三列 ＋ revision 三比对；
                PASS 的附属信息里必须出现 SUGGEST。读不到 ⇒ **未测**（不判红）
    A2L  远端   `--live`：把**远端**表喂进同一套 A2（这是 10-22 补的那条 —— 本地两文件互证会恒绿）
    B    决策集 `DECISIONS` **不得**含 SUGGEST；三态齐；多出来的只能是 `NEEDS_INPUT`
    C    落表   `STATUS_PASS` **不得**含 SUGGEST；三态齐（否则对应结论发不进飞书）
    D    分级   `decide_effect`：P0→block、P1/P2→review、**P3→none**（不改结论）
    E    标签/渲染 ①P3-only ⇒ `decision=PASS` ＋ `suggest_count≥1` ＋ `suggest_label=True`；
                ②PASS 卡面带「建议（不阻断，随 PASS 流转」附段；③`render_summary("SUGGEST")` **必须抛**
    F    跨仓   守衡 `STATES`：**缺三态中的任一个 ⇒ 红**；仍含 SUGGEST ⇒ **报「跨仓待同步」不判红**
    G    读数   生产侧 `decision=SUGGEST` 的单量（应恒 0）—— **读数，永不判红**

## 退出码（照 `prd_card_conformance` 的惯例：**只退 0 或 3**）

    0  A–E 全过（A2／A2L／F 读不到的那部分记「未测」，不判红）
    3  任一条红 / 判据自证失败 / 真源读不到
    **永不 1/2**：非阻断闸门退 1/2 会被 `ci/run_gates.py` 记成 ERROR 并把 CI 打红。

用法
    sh kb/kbpy l8/prd532_check.py [--json]
    sh kb/kbpy l8/prd532_check.py --live         # ★ 拉**远端**表比对（无网/无凭据 ⇒ 未测退 0）
    sh kb/kbpy l8/prd532_check.py --selftest     # 反向对照：每一条都真造一遍坏形状
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections import Counter
from pathlib import Path

KB = Path(__file__).resolve().parent.parent          # …/kb
REGISTRY = KB / "l7" / "registry" / "prd532-states.yaml"
CORE = KB / "l7" / "review-engine" / "core"
SAMPLES = KB / "l7" / "review-engine" / "samples"
# 当天的 PRD 内嵌表快照（**出处核对**用；不在了就报「未测」，不判红）
SHEET_SNAPSHOT = Path(os.environ.get("KB_PRD532_SHEET")
                      or (KB.parent / "_prd-20261022" / "sheet-xcdTpv-rev107.json"))
# 守衡那把尺子（跨仓件；本库不复制它的词表，只读它的导出）
SHOUHENG_ROOT = Path(os.environ.get("KB_SHOUHENG_ROOT")
                     or os.path.expanduser("~/project/audit_multi_content"))
SHOUHENG_MJS = Path(os.environ.get("KB_PRD53")
                    or str(SHOUHENG_ROOT / "tools" / "agent" / "prd53.mjs"))
# PRD 内嵌表的身份（远端比对用）
PRD_SHEET_TOKEN = "B1aUs2Vuah8YwjtwWO6cr5MFnUd"
PRD_SHEET_ID = "xcdTpv"
PRD_SHEET_RANGE = "A1:D4"

#: §5.3.2 rev107 的**主状态**（表里那三行）。**SUGGEST 不在内** —— 它已降成 PASS 的一格。
PRD_STATES = ["PASS", "REVIEW", "BLOCK"]
#: 曾经占过一行的那个标签（rev96 四态 → rev101 附属标签 → rev107 只剩一格）
FORMER_STATE = "SUGGEST"
#: `decision` 的合法取值（PRD 态）。**SUGGEST 不在内** —— 它是 PASS 的标签。
PRD_DECISIONS = {"PASS", "REVIEW", "BLOCK"}
#: 唯一允许的额外 token —— 拒答态（fail-closed），**不是 PRD 的态**
NON_PRD_DECISIONS = {"NEEDS_INPUT"}
#: 谁阻断流程（SUGGEST 永不阻断：它只是标签）
PRD_BLOCKS = {"PASS": False, "REVIEW": True, "BLOCK": True}
#: 统计四桶（§10.2「汇总四态结论」）—— 只作读数，不是 decision 取值
PRD_BUCKETS = ["PASS", "PASS+SUGGEST", "REVIEW", "BLOCK"]
#: 表列名（rev107：状态→主状态，动作→附属信息，另加一列动作）
COL_ID, COL_DEF, COL_ATT, COL_ACT = "主状态", "定义", "附属信息", "动作"
_HEADER_CELLS = {"状态", "主状态", "状态 ", ""}

_REAL = object()


# ══════════════════════════════════════════════════════════════════════
# 读取真源 / 快照 / 远端 / 跨仓件
# ══════════════════════════════════════════════════════════════════════
def load_registry(path: Path | None = None) -> dict:
    p = Path(path) if path else REGISTRY
    if not p.is_file():
        raise FileNotFoundError(f"真源不存在：{p}")
    import yaml                                      # noqa: PLC0415
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"真源不是映射：{p}")
    data["__path__"] = str(p)
    return data


def _rows_from_values(values) -> list[dict]:
    """把 `sheets/v2/...values` 的二维数组转成 `[{主状态,定义,附属信息,动作}]`（跳过表头与空行）。"""
    rows = []
    for row in values or []:
        cells = ["" if c is None else str(c).strip() for c in row]
        if not cells or cells[0] in _HEADER_CELLS:
            continue
        if len(cells) < 2 or not cells[0]:
            continue
        cells += [""] * (4 - len(cells))
        rows.append({COL_ID: cells[0], COL_DEF: cells[1], COL_ATT: cells[2], COL_ACT: cells[3]})
    return rows


def _rows_from_csv(csv: str) -> list[dict]:
    """从 `annotated_csv`（`[row=N] a,b,c`）还原 —— 旧快照只有这一种形态。"""
    rows = []
    for line in str(csv or "").splitlines():
        line = line.strip()
        if not line.startswith("[row="):
            continue
        cells = [c.strip() for c in line.split("]", 1)[-1].strip().split(",")]
        if not cells or cells[0] in _HEADER_CELLS:
            continue
        cells += [""] * (4 - len(cells))
        rows.append({COL_ID: cells[0], COL_DEF: cells[1], COL_ATT: cells[2], COL_ACT: cells[3]})
    return rows


def load_sheet_snapshot(path: Path | None = None):
    """返回 `(rows, revision)`；文件不在 / 读不出版本 ⇒ `(None, None)`（调用方记未测）。"""
    p = Path(path) if path else SHEET_SNAPSHOT
    if not p.is_file():
        return None, None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:                                # noqa: BLE001
        return None, None
    d = data.get("data") or {}
    d = d.get("data") if isinstance(d.get("data"), dict) else d
    rev = d.get("revision")
    rows = _rows_from_values(d.get("values"))
    if not rows:
        rows = _rows_from_csv(d.get("annotated_csv") or "")
    return (rows or None), rev


def fetch_live_sheet(url_range: str = PRD_SHEET_RANGE):
    """**远端**读 PRD 内嵌表（只读 values 接口；红线内的「读」，不碰 download/medias）。

    返回 `(rows, revision, err)`；任何一步失败 ⇒ `(None, None, 原因)`（调用方记**未测**）。

    取 token 复用守衡仓那把既有的 `tools/lark_find.py`（凭据只在那里被解一次），
    本文件不另造一份凭据读取 —— 见 AGENTS.md §2.6 第 3 条。
    """
    try:
        tools = str(SHOUHENG_ROOT / "tools")
        if tools not in sys.path:
            sys.path.insert(0, tools)
        import lark_find as LF                       # noqa: PLC0415
        tok = LF.token()
        url = (f"{LF.BASE}/sheets/v2/spreadsheets/{PRD_SHEET_TOKEN}"
               f"/values/{PRD_SHEET_ID}!{url_range}?valueRenderOption=ToString")
        r = LF._req(url, tok)
    except Exception as e:                           # noqa: BLE001
        return None, None, f"远端取数抛异常：{type(e).__name__}: {e}"
    if r.get("code") != 0:
        return None, None, f"远端返回 code={r.get('code')}（{json.dumps(r, ensure_ascii=False)[:160]}）"
    vr = (r.get("data") or {}).get("valueRange") or {}
    rows = _rows_from_values(vr.get("values"))
    rev = (r.get("data") or {}).get("revision")
    if not rows:
        return None, None, "远端读到了空表"
    return rows, rev, ""


def shouheng_states():
    """读守衡 `prd53.mjs` 导出的 `STATES`（只读，不复制、不改）。读不到 ⇒ None。"""
    if not SHOUHENG_MJS.is_file():
        return None
    script = ("import(%s).then(m=>console.log(JSON.stringify(m.STATES||[])))"
              ".catch(e=>{console.error(String(e&&e.message||e));process.exit(4)})"
              % json.dumps(SHOUHENG_MJS.as_uri()))
    try:
        pr = subprocess.run(["node", "--input-type=module", "-e", script],
                            capture_output=True, text=True, timeout=60)
    except Exception:                                # noqa: BLE001
        return None
    if pr.returncode != 0:
        return None
    try:
        arr = json.loads(pr.stdout.strip() or "[]")
    except Exception:                                # noqa: BLE001
        return None
    return [str(x) for x in arr] if isinstance(arr, list) and arr else None


def engine():
    if str(CORE) not in sys.path:
        sys.path.insert(0, str(CORE))
    import feishu_publish as FP                # noqa: PLC0415
    import review_engine as RE                 # noqa: PLC0415
    import tiering as TI                       # noqa: PLC0415
    return RE, TI, FP


def _p3_payload():
    """从真夹具 `samples/pass.json` 造一单「只有 P3」的载荷（不手搓整个 payload）。"""
    base = json.loads((SAMPLES / "pass.json").read_text(encoding="utf-8"))
    base = json.loads(json.dumps(base))
    base["risk_items"] = [{
        "risk_id": "P3-SMOKE",
        "risk_type": "措辞表达-口语化",
        "priority_tier": "P3",
        "status": "confirmed",
        "action": "advice",
        "location": "正文第 2 段",
        "evidence_id": "《内部样本库 v0》第 W-2.1 条",
        "reason": "措辞偏口语",
        "suggestion": "改为「高效便捷」",
        "original_text": "超级好用",
        "severity": "SUGGEST",
        "taxonomy_category": "措辞表达",
        "taxonomy_subcategory": "口语化",
    }]
    return base


# ══════════════════════════════════════════════════════════════════════
# 判据主体（纯函数；一切来源可注入 ⇒ 自证能做**真变异**）
# ══════════════════════════════════════════════════════════════════════
def evaluate(reg=_REAL, sheet=_REAL, decisions=_REAL, status_pass=_REAL,
             decide_effect=_REAL, render_summary=_REAL, decide=_REAL,
             sh_states=_REAL, runs_index=_REAL, live: bool = False) -> dict:
    red: list[str] = []
    untested: list[str] = []
    d: dict = {}

    # ── A 源侧（rev107：三个主状态）────────────────────────────────────
    if reg is _REAL:
        try:
            reg = load_registry()
        except Exception as e:                       # noqa: BLE001
            return {"ok": False, "red": ["A 真源读不到（fail-closed，不当「未测」）：%r" % (e,)],
                    "untested": [], "detail": {"registry": str(REGISTRY)}}
    states = reg.get("states") or []
    ids = [str(s.get("id")) for s in states if isinstance(s, dict)]
    by_id = {str(s.get("id")): s for s in states if isinstance(s, dict)}
    d["states"] = ids
    d["buckets"] = PRD_BUCKETS
    d["registry"] = reg.get("__path__")
    if set(ids) != set(PRD_STATES):
        red.append("A1 真源主状态与 PRD §5.3.2 rev107 不同集：%s（PRD：%s）" % (ids, PRD_STATES))
    if FORMER_STATE in ids:
        red.append("A1b 真源把 %s 写成了**主状态** —— rev 107 起它连「一行」都不是，"
                   "只是 PASS 的「附属信息」（写回 states 就是把旧口径复线）" % FORMER_STATE)
    for sid in PRD_STATES:
        s = by_id.get(sid) or {}
        if not str(s.get("definition") or "").strip():
            red.append("A2 %s 缺 definition" % sid)
        if not str(s.get("action") or "").strip():
            red.append("A3 %s 缺 action（PRD 的「动作」列）" % sid)
        if not str(s.get("attached") or "").strip():
            red.append("A3b %s 缺 attached（PRD rev107 新增的「附属信息」列）" % sid)
        if "blocks_flow" not in s:
            red.append("A4 %s 缺 blocks_flow" % sid)
        elif bool(s.get("blocks_flow")) != PRD_BLOCKS[sid]:
            red.append("A5 %s 的 blocks_flow=%r，PRD 是 %r"
                       % (sid, s.get("blocks_flow"), PRD_BLOCKS[sid]))
    # 标签语义段：三版合一的**判据锚** —— 它证明「SUGGEST 是标签、decision 只有三值」
    lab = reg.get("label_semantics") or {}
    d["label_semantics"] = bool(lab)
    if not lab:
        red.append("A6 真源缺 `label_semantics` 段 —— 没有它，「SUGGEST 是标签」只是散文；"
                   "四态/三值两种读法又会被混着用（同日已踩过一次）")
    else:
        if set(map(str, lab.get("decision_values") or [])) != PRD_DECISIONS:
            red.append("A7 `label_semantics.decision_values` 必须是 %s，实得 %s"
                       % (sorted(PRD_DECISIONS), lab.get("decision_values")))
        if int(lab.get("buckets") or 0) != 4:
            red.append("A8 `label_semantics.buckets` 必须是 4（PASS／PASS＋建议／REVIEW／BLOCK），实得 %r"
                       % (lab.get("buckets"),))
        if str(lab.get("label_state") or "").upper() != FORMER_STATE:
            red.append("A9 `label_semantics.label_state` 必须是 SUGGEST，实得 %r"
                       % (lab.get("label_state"),))
        if lab.get("label_not_a_row") is not True:
            red.append("A9b `label_semantics.label_not_a_row` 必须是 true —— rev107 的 SUGGEST"
                       "不占主状态行，这一格就是那条口径的落点")
    conf = reg.get("conflict_decision") or {}
    if not str(conf.get("owner_ruling_20261019") or "").strip():
        red.append("A10 冲突 K 的**历史裁定**不在案（它已被 rev 101／107 覆盖，但必须留痕）")
    if not (conf.get("superseded_by") or conf.get("superseded_at")):
        red.append("A11 冲突 K 的历史裁定没有 `superseded_by` 留痕 —— "
                   "改主意必须可追溯到「谁在什么时候按什么覆盖了它」（AP14）")

    # ── A2 出处：逐字（三列）＋ revision 三比对；--live 时换成**远端** ──
    if sheet is _REAL:
        if live:
            rows, rev, err = fetch_live_sheet()
            d["sheet_source"] = "live" if rows else "live-unavailable"
            if rows is None:
                untested.append("A2L 远端核对未测：%s —— **未测不是通过**" % (err or "未知原因"))
        else:
            rows, rev = load_sheet_snapshot()
            d["sheet_source"] = "snapshot"
            if rows is None:
                untested.append("A2 出处核对未测：PRD 内嵌表快照不在（%s）" % SHEET_SNAPSHOT)
    elif isinstance(sheet, tuple):
        rows, rev = sheet
        d["sheet_source"] = d.get("sheet_source") or "injected"
    else:
        rows, rev = sheet, None
        d["sheet_source"] = "injected"
        if rows is None:
            untested.append("A2 出处核对未测：没有可核对的表（注入为空 / 快照读不到）"
                            "—— **未测不是通过**")
    meta_rev = (reg.get("meta") or {}).get("revision")
    d["revision"] = {"registry": meta_rev, "sheet": rev, "source": d.get("sheet_source")}
    if rows is not None:
        snap = {str(r.get(COL_ID)): r for r in rows}
        if set(snap) != set(PRD_STATES):
            red.append("A2a 表里的主状态与 PRD 三态不同集：%s（rev107：%s）" % (list(snap), PRD_STATES))
        if FORMER_STATE in snap:
            red.append("A2a2 表里 %s 又占了**一行** —— rev107 已把它降成 PASS 的「附属信息」" % FORMER_STATE)
        for sid in PRD_STATES:
            r = snap.get(sid) or {}
            for key, field in ((COL_DEF, "definition"), (COL_ATT, "attached"), (COL_ACT, "action")):
                want = str(r.get(key) or "").strip()
                got = str((by_id.get(sid) or {}).get(field) or "").strip()
                if want and got and want != got:
                    red.append("A2b %s 的 %s 与 PRD 内嵌表**不逐字一致**：\n      PRD：%s\n      真源：%s"
                               % (sid, field, want, got))
        pass_att = str((snap.get("PASS") or {}).get(COL_ATT) or "")
        if "SUGGEST" not in pass_att.upper():
            red.append("A2d PASS 的「附属信息」列里没有 SUGGEST —— rev107 的 SUGGEST 就活在这一格里，"
                       "它要是没了，「标签」这件事在 PRD 里就没有落点了")
    if meta_rev is not None and rev is not None and int(meta_rev) != int(rev):
        red.append("A2c revision 对不上：真源记的是 %s，表拿到的是 %s —— "
                   "**真源与快照一起陈旧时这条判据会恒绿**，所以必须比这一格" % (meta_rev, rev))

    # ── B 决策集 ─────────────────────────────────────────────────────
    if decisions is _REAL:
        try:
            decisions = engine()[0].DECISIONS
        except Exception as e:                       # noqa: BLE001
            red.append("B 取不到 `review_engine.DECISIONS`：%r" % (e,))
            decisions = None
    if decisions is not None:
        ds = set(map(str, decisions))
        d["decisions"] = sorted(ds)
        if "SUGGEST" in ds:
            red.append("B1 `DECISIONS` 含 SUGGEST —— rev 101／107 里它是 **PASS 的附属标签**，"
                       "进了决策集就又是第四态（同日踩过一次，这是那条的回归判据）")
        miss = PRD_DECISIONS - ds
        if miss:
            red.append("B2 决策集缺态：%s" % sorted(miss))
        extra = ds - PRD_DECISIONS
        if extra - NON_PRD_DECISIONS:
            red.append("B3 决策集多出非 PRD、也非拒答态的取值：%s" % sorted(extra - NON_PRD_DECISIONS))
        if extra & NON_PRD_DECISIONS:
            d["non_prd"] = sorted(extra & NON_PRD_DECISIONS)

    # ── C 落表放行集 ─────────────────────────────────────────────────
    if status_pass is _REAL:
        try:
            status_pass = engine()[2].STATUS_PASS
        except Exception as e:                       # noqa: BLE001
            red.append("C 取不到 `feishu_publish.STATUS_PASS`：%r" % (e,))
            status_pass = None
    if status_pass is not None:
        sp = set(map(str, status_pass))
        d["status_pass"] = sorted(sp)
        if "SUGGEST" in sp:
            red.append("C1 `STATUS_PASS` 含 SUGGEST —— 它不该作为 `decision` 出现在表行里")
        lack = PRD_DECISIONS - sp
        if lack:
            red.append("C2 STATUS_PASS 不收这些态：%s（该结论**发不进飞书**）" % sorted(lack))

    # ── D 分级路径 ───────────────────────────────────────────────────
    if decide_effect is _REAL:
        try:
            decide_effect = engine()[1].decide_effect
        except Exception as e:                       # noqa: BLE001
            red.append("D 取不到 `tiering.decide_effect`：%r" % (e,))
            decide_effect = None
    if decide_effect is not None:
        want = [("P0", "block"), ("P1", "review"), ("P2", "review"), ("P3", "none")]
        got = {}
        for tier, expect in want:
            try:
                eff = decide_effect([tier])[0]
            except Exception as e:                   # noqa: BLE001
                red.append("D1 decide_effect([%r]) 抛异常：%r" % (tier, e))
                continue
            got[tier] = eff
            if eff != expect:
                red.append("D2 %s 的 effect 是 %r，PRD §5.3.2 rev107/§6.3 规则4 要求 %r"
                           % (tier, eff, expect))
        d["decide_effect"] = got
        if got.get("P3") not in (None, "none"):
            red.append("D3 **P3 改了结论**（effect=%r）—— rev 107 里 P3 只出建议、结论仍是 PASS。"
                       "反向的一条同样致命：P3 若是「没有产者」，PASS＋建议那个桶就永远恒 0"
                       % (got.get("P3"),))

    # ── E 标签与渲染（rev107 的核心：标签必须看得见，第四态必须不存在）──
    if render_summary is _REAL or decide is _REAL:
        try:
            REs = engine()[0]
        except Exception as e:                       # noqa: BLE001
            red.append("E 取不到 `review_engine`：%r" % (e,))
            REs = None
        if REs is not None:
            if render_summary is _REAL:
                render_summary = REs.render_summary
            if decide is _REAL:
                decide = REs.decide
    if callable(decide):
        try:
            res = decide(_p3_payload())
        except Exception as e:                       # noqa: BLE001
            res = None
            red.append("E1 只有 P3 的载荷 `decide()` 抛异常：%r" % (e,))
        if isinstance(res, dict):
            d["p3_only"] = {"decision": res.get("decision"),
                            "suggest_count": res.get("suggest_count"),
                            "suggest_label": res.get("suggest_label")}
            if res.get("decision") != "PASS":
                red.append("E2 只有 P3 ⇒ `decision` 必须是 PASS（rev 107），实得 %r"
                           % (res.get("decision"),))
            if not int(res.get("suggest_count") or 0):
                red.append("E3 只有 P3 却 `suggest_count=0` —— 建议集丢了，"
                           "「PASS 附建议」在数据上退化成 PASS（四态第二个桶永远恒 0）")
            if not res.get("suggest_label"):
                red.append("E4 只有 P3 但 `suggest_label` 不为 True")
    if callable(render_summary):
        p3_item = _p3_payload()["risk_items"]
        try:
            txt = str(render_summary("PASS", p3_item, Counter(), None))
        except Exception as e:                       # noqa: BLE001
            txt = ""
            red.append("E5 PASS＋P3 渲染抛异常：%r" % (e,))
        d["pass_with_suggest_head"] = txt.split("\n")[0][:80] if txt else ""
        if txt:
            if not txt.startswith("【审查结论：PASS】"):
                red.append("E6 PASS＋建议的结论行不是 PASS：%r" % txt.split("\n")[0][:60])
            if "建议（不阻断，随 PASS 流转" not in txt:
                red.append("E7 PASS＋建议缺附段抬头「建议（不阻断，随 PASS 流转…」")
        try:
            render_summary("SUGGEST", p3_item, Counter(), None)
            red.append("E8 `render_summary('SUGGEST', …)` **没有抛** —— 第四态还能从渲染这条路长回来")
        except ValueError:
            pass
        except Exception as e:                       # noqa: BLE001
            red.append("E9 `render_summary('SUGGEST', …)` 抛了非 ValueError：%r（要的是明确拒绝）" % (e,))

    # ── F 跨仓词表（缺三态⇒红；仍含 SUGGEST⇒只报待同步）─────────────
    if sh_states is _REAL:
        sh_states = shouheng_states()
    if sh_states is None:
        untested.append("F 跨仓未测：守衡 `prd53.mjs` 读不到（%s）—— 缺件 ≠ 坏件" % SHOUHENG_MJS)
    else:
        sh = list(map(str, sh_states))
        d["shouheng_states"] = sh
        lack = PRD_DECISIONS - set(sh)
        if lack:
            red.append("F1 守衡 `STATES` 缺 %s —— 那会让它**读不出**这类结论行（跨仓断链）" % sorted(lack))
        if "SUGGEST" in sh:
            untested.append("F2 跨仓待同步：守衡 `STATES` 仍含 SUGGEST（%s）—— 那是另一会话工作区里的改动，"
                            "改单见 `交付-PRD532-标签口径-与守衡改单-20261019.md`；KB 侧已不再产出 SUGGEST 行，"
                            "**该分歧当前无害**（多认一个不会出现的词），但必须同步" % ",".join(sh))

    # ── G 生产读数（**永不判红**）─────────────────────────────────────
    if runs_index is _REAL:
        runs_index = KB / "l7" / "runs" / "index.jsonl"
    cnt = None
    try:
        p = Path(runs_index)
        if p.is_file():
            cnt = sum(1 for ln in p.read_text(encoding="utf-8").splitlines()
                      if '"decision": "SUGGEST"' in ln or '"decision":"SUGGEST"' in ln)
    except Exception:                                # noqa: BLE001
        cnt = None
    d["productions_decision_suggest"] = cnt
    if cnt is not None and cnt:
        d["reading_note"] = "生产侧有 %d 单落过 decision=SUGGEST（rev 96 时期的产物）—— 读数，不判红" % cnt

    return {"ok": not red, "red": red, "untested": untested, "detail": d}


# ══════════════════════════════════════════════════════════════════════
def selftest() -> int:
    bad: list[str] = []
    n = [0]

    def ck(name: str, ok: bool, extra: str = "") -> None:
        n[0] += 1
        if ok:
            print(f"  ✅ {name}")
        else:
            bad.append(name)
            print(f"  ❌ {name} {extra}")

    print("=== prd532_check 自证（rev 107：三值 ＋ 一个标签 ＋ 四个桶）===")

    base = evaluate()
    ck("① 基线：真源＋代码＋跨仓一致（红 0）", base["ok"], str(base["red"])[:200])
    ck("①b 真源主状态就是三行（PASS/REVIEW/BLOCK），且标签语义段在案",
       set(base["detail"].get("states") or []) == set(PRD_STATES)
       and base["detail"].get("label_semantics") is True,
       str(base["detail"].get("states")))
    ck("①c 统计仍是四个桶（PASS／PASS+建议／REVIEW／BLOCK）",
       base["detail"].get("buckets") == PRD_BUCKETS, str(base["detail"].get("buckets")))

    try:
        reg = load_registry()
    except Exception as e:                            # noqa: BLE001
        print(f"  ❌ ② 真源读不到，后面的变异没法造：{e!r}")
        return 1
    plain = {k: v for k, v in reg.items() if not k.startswith("__")}

    # ② 真源删掉 REVIEW ⇒ 红
    mut = json.loads(json.dumps(plain))
    mut["states"] = [s for s in mut.get("states") or [] if s.get("id") != "REVIEW"]
    r = evaluate(reg=mut)
    ck("② 变异：真源删掉 REVIEW ⇒ 必须红", not r["ok"] and any("不同集" in x for x in r["red"]), str(r["red"])[:120])

    # ②b SUGGEST 又写成主状态 ⇒ 红（rev107 的回归）
    mut1b = json.loads(json.dumps(plain))
    mut1b.setdefault("states", []).append(
        {"id": "SUGGEST", "definition": "非强制性问题", "attached": "—",
         "action": "随 PASS 流转", "blocks_flow": False})
    r = evaluate(reg=mut1b)
    ck("②b 变异：把 SUGGEST 又写回主状态行 ⇒ 必须红",
       not r["ok"] and any("A1b" in x for x in r["red"]), str(r["red"])[:120])

    # ③ PASS 改成阻断 ⇒ 红
    mut2 = json.loads(json.dumps(plain))
    for s in mut2.get("states") or []:
        if s.get("id") == "PASS":
            s["blocks_flow"] = True
    r = evaluate(reg=mut2)
    ck("③ 变异：PASS 改成 blocks_flow=true ⇒ 必须红",
       not r["ok"] and any("blocks_flow" in x for x in r["red"]), str(r["red"])[:120])

    # ④ 去掉标签语义段 ⇒ 红（这就是「三值/四态混着用」那一半的判据）
    mut3 = json.loads(json.dumps(plain))
    mut3.pop("label_semantics", None)
    r = evaluate(reg=mut3)
    ck("④ 变异：真源删掉 label_semantics ⇒ 必须红",
       not r["ok"] and any("label_semantics" in x for x in r["red"]), str(r["red"])[:120])

    # ④b label_not_a_row 被拿掉 ⇒ 红（rev107 新增的那一格）
    mut3b = json.loads(json.dumps(plain))
    (mut3b.get("label_semantics") or {}).pop("label_not_a_row", None)
    r = evaluate(reg=mut3b)
    ck("④b 变异：label_semantics 去掉 label_not_a_row ⇒ 必须红",
       not r["ok"] and any("A9b" in x for x in r["red"]), str(r["red"])[:120])

    # ⑤ 去掉 superseded_by 留痕 ⇒ 红
    mut4 = json.loads(json.dumps(plain))
    (mut4.get("conflict_decision") or {}).pop("superseded_by", None)
    (mut4.get("conflict_decision") or {}).pop("superseded_at", None)
    r = evaluate(reg=mut4)
    ck("⑤ 变异：历史裁定去掉 superseded 留痕 ⇒ 必须红",
       not r["ok"] and any("superseded" in x for x in r["red"]), str(r["red"])[:120])

    # ⑥ DECISIONS 又收进 SUGGEST ⇒ 红（rev 96 的回归）
    ds = set(base["detail"].get("decisions") or []) | {"SUGGEST"}
    r = evaluate(decisions=ds)
    ck("⑥ 变异：DECISIONS 又含 SUGGEST ⇒ 必须红",
       not r["ok"] and any("B1" in x for x in r["red"]), str(r["red"])[:120])

    # ⑦ STATUS_PASS 含 SUGGEST ⇒ 红
    sp = set(base["detail"].get("status_pass") or []) | {"SUGGEST"}
    r = evaluate(status_pass=sp)
    ck("⑦ 变异：STATUS_PASS 含 SUGGEST ⇒ 必须红",
       not r["ok"] and any("C1" in x for x in r["red"]), str(r["red"])[:120])

    # ⑧ P3 回退成 suggest（第四态那版）⇒ 红
    def _p3_state(tiers):
        t = list(tiers)
        if t and all(x == "P3" for x in t):
            return ("suggest", "回退成 rev 96 那版")
        return ("block" if "P0" in t else "review", "变异桩")
    r = evaluate(decide_effect=_p3_state)
    ck("⑧ 变异：P3 又改结论（effect=suggest）⇒ 必须红",
       not r["ok"] and any("D2" in x or "D3" in x for x in r["red"]), str(r["red"])[:140])

    # ⑨ 渲染能出 SUGGEST 结论行 ⇒ 红
    def _render_ok(state, items, cats, url):
        return "【审查结论：%s】x" % state
    r = evaluate(render_summary=_render_ok)
    ck("⑨ 变异：`render_summary('SUGGEST')` 不抛 ⇒ 必须红",
       not r["ok"] and any("E8" in x for x in r["red"]), str(r["red"])[:140])

    # ⑩ PASS＋P3 却渲染不出建议段 ⇒ 红
    def _render_pass_only(state, items, cats, url):
        return "【审查结论：PASS】未发现已知底线风险，可转交 @某 进行 sign-off。"
    r = evaluate(render_summary=_render_pass_only, decide=lambda p: {
        "decision": "PASS", "suggest_count": 1, "suggest_label": True})
    ck("⑩ 变异：PASS＋P3 渲染不出建议段 ⇒ 必须红",
       not r["ok"] and any("E7" in x for x in r["red"]), str(r["red"])[:140])

    # ⑪ decide 把 P3 单落成 SUGGEST ⇒ 红
    r = evaluate(decide=lambda p: {"decision": "SUGGEST", "suggest_count": 1, "suggest_label": True})
    ck("⑪ 变异：只有 P3 时 decision=SUGGEST ⇒ 必须红",
       not r["ok"] and any("E2" in x for x in r["red"]), str(r["red"])[:140])

    # ⑫ 守衡缺 BLOCK ⇒ 红（跨仓断链那一半）
    r = evaluate(sh_states=["PASS", "REVIEW", "SUGGEST"])
    ck("⑫ 变异：守衡 STATES 缺 BLOCK ⇒ 必须红",
       not r["ok"] and any("F1" in x for x in r["red"]), str(r["red"])[:120])

    # ⑬ 守衡仍含 SUGGEST ⇒ **不判红**，但要报「跨仓待同步」
    r = evaluate(sh_states=["PASS", "SUGGEST", "REVIEW", "BLOCK"])
    ck("⑬ 守衡仍含 SUGGEST ⇒ 不判红、但必须报「跨仓待同步」",
       r["ok"] and any("跨仓待同步" in x for x in r["untested"]), str(r["untested"])[:140])

    # ⑭ 真源不存在 ⇒ 红（fail-closed）
    saved = globals()["REGISTRY"]
    try:
        globals()["REGISTRY"] = Path("/nonexistent/prd532-states.yaml")
        r = evaluate()
        ck("⑭ 真源不存在 ⇒ 红且明说 fail-closed",
           not r["ok"] and any("真源读不到" in x for x in r["red"]), str(r["red"])[:120])
    finally:
        globals()["REGISTRY"] = saved

    # ⑮ 快照不在 ⇒ 未测不红
    r = evaluate(sheet=None)
    ck("⑮ PRD 快照不在 ⇒ 报未测且不判红",
       r["ok"] and any("未测" in x for x in r["untested"]), str(r["untested"])[:120])

    # ⑯ 快照定义改一个字 ⇒ 红（逐字核对有牙）
    rows, rev = load_sheet_snapshot()
    if rows:
        mut5 = [dict(x) for x in rows]
        for x in mut5:
            if x[COL_ID] == "PASS":
                x[COL_DEF] = "未发现已知底线风险。"
        r = evaluate(sheet=(mut5, rev))
        ck("⑯ 变异：快照里 PASS 的定义改一个字 ⇒ 必须红（逐字核对有牙）",
           not r["ok"] and any("A2b" in x for x in r["red"]), str(r["red"])[:140])

        # ⑯b 快照 PASS 的「附属信息」里去掉 SUGGEST ⇒ 红（rev107 的新落点）
        mut5b = [dict(x) for x in rows]
        for x in mut5b:
            if x[COL_ID] == "PASS":
                x[COL_ATT] = "可附带修改建议"
        r = evaluate(sheet=(mut5b, rev))
        ck("⑯b 变异：快照 PASS 的附属信息去掉 SUGGEST ⇒ 必须红",
           not r["ok"] and any("A2d" in x for x in r["red"]), str(r["red"])[:140])

        # ⑯c 快照里 SUGGEST 又占一行 ⇒ 红
        mut5c = [dict(x) for x in rows] + [{COL_ID: "SUGGEST", COL_DEF: "非强制性问题",
                                            COL_ATT: "—", COL_ACT: "提示内容方"}]
        r = evaluate(sheet=(mut5c, rev))
        ck("⑯c 变异：快照里 SUGGEST 又占一行 ⇒ 必须红",
           not r["ok"] and any("A2a" in x for x in r["red"]), str(r["red"])[:140])

        # ⑰ revision 对不上 ⇒ 红（真源与快照一起陈旧时，这条是唯一的报警器）
        r = evaluate(sheet=(rows, int(rev) + 1))
        ck("⑰ 变异：快照 revision 比真源新 ⇒ 必须红（防「一起陈旧、互相印证」）",
           not r["ok"] and any("A2c" in x for x in r["red"]), str(r["red"])[:140])
    else:
        ck("⑯ 快照不在 ⇒ 逐字与 revision 两条记为未测（不算失败）", True)
        ck("⑰ 同上", True)

    # ⑱ 远端拉不到 ⇒ **未测、不判红**（`--live` 的 fail-open 那一半）
    saved_fetch = globals()["fetch_live_sheet"]
    try:
        globals()["fetch_live_sheet"] = lambda *a, **k: (None, None, "桩：无网")
        r = evaluate(live=True)
        ck("⑱ 变异：远端拉不到 ⇒ 未测且不判红（未测 ≠ 通过 ≠ 红）",
           r["ok"] and any("A2L" in x for x in r["untested"]), str(r["untested"])[:140])
    finally:
        globals()["fetch_live_sheet"] = saved_fetch

    # ⑲ 远端拉到更新的版本 ⇒ 红（这就是 rev107 是**怎么被发现的**那条路）
    if rows:
        r = evaluate(sheet=(rows, int(rev) + 4), live=True)
        ck("⑲ 变异：远端比真源新（模拟 101→107 那种漂移）⇒ 必须红",
           not r["ok"] and any("A2c" in x for x in r["red"]), str(r["red"])[:140])

    print("\n" + "═" * 60)
    print(f"自证：通过 {n[0] - len(bad)} / 失败 {len(bad)}")
    if bad:
        print("失败项：" + "；".join(bad))
        return 1
    print("✅ 三值＋标签＋四桶 的每一条都被咬住：删标签、退四态、缺桶、revision 漂移、"
          "远端读不到，全都精确区分「红」与「未测」。")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="PRD §5.3.2 rev107 接线判据（三值＋标签＋四桶）")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--live", action="store_true",
                    help="拉**远端** PRD 内嵌表比对（无网/无凭据 ⇒ 记「未测」，退出码仍 0）")
    a = ap.parse_args()
    if a.selftest:
        return 0 if selftest() == 0 else 3

    res = evaluate(live=a.live)
    if a.json:
        print(json.dumps(res, ensure_ascii=False))
    else:
        d = res["detail"]
        print("=== PRD §5.3.2（rev 107）三值 ＋ 一个标签 ＋ 四个桶 ===")
        print("真源：%s ｜ 版本：%s" % (d.get("registry"), d.get("revision")))
        print("主状态（表里那三行）：%s" % d.get("states"))
        print("统计四桶：%s" % d.get("buckets"))
        print("标签语义段：%s" % ("在案" if d.get("label_semantics") else "**缺**"))
        print("决策集：%s（其中非 PRD：%s）" % (d.get("decisions"), d.get("non_prd")))
        print("落表放行：%s" % d.get("status_pass"))
        print("分级路径：%s" % d.get("decide_effect"))
        print("P3 单：%s" % d.get("p3_only"))
        print("PASS＋建议结论行：%s" % d.get("pass_with_suggest_head"))
        print("跨仓词表：%s" % (d.get("shouheng_states", "（未测）")))
        print("生产侧 decision=SUGGEST 单量：%s" % d.get("productions_decision_suggest"))
        for line in res["untested"]:
            print("⚠ %s" % line)
        for line in res["red"]:
            print("❌ %s" % line)
        print("结论：%s" % ("PASS（三值＋标签＋四桶 六处一致）" if res["ok"] else "WARN（有红项）"))
    return 0 if res["ok"] else 3


if __name__ == "__main__":
    sys.exit(main())
