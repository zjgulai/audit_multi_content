#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""「四类知识库各自有没有一条通往依据的路」—— 供给路径判据（任务拆解 目标 5 的收口前置）。

════════════════════════════════════════════════════════════════════════
它回答的那一个问题
════════════════════════════════════════════════════════════════════════

    PRD §7.1 的四类知识库，**哪几类真的能变成评审依据**？

「库里有一类东西」**不等于**「这一类能变成依据」—— 中间隔着一条供给路径：

    源 → L0 → L1 → L2 单元 ─┬─→ ① **规则层命中**（`kb/l3/candidates/rules.jsonl`）
                            └─→ ② **定稿件被活代码读作内容**（`kb/l4/canonical/<形态>.jsonl`）

两条都没有 ⇒ 这一类**永远进不了结论**，而报告里看起来「库里有这一类」。

**实测（2026-10-10，本判据第一次跑）**：

| 知识库 | L2 单元 | 规则层 | 定稿消费者 | 能依据？ |
|---|---|---|---|---|
| 措辞表达库 `wording` | 7661 | **1018 条** | — | ✅ |
| 内部正负样本库 `internal_sample` | 1510 | 0 条 | `review.py` / `selfhit_check.py` 读 `sample_case` | ✅ |
| **外部标准库 `external_standard`** | **5421** | **0 条** | **无** | ❌ |
| **产品描述库 `product_desc`** | **54** | **0 条** | **无** | ❌ |

⇒ **PRD §7.1 的四类里，两类不可依据。** 而「外部标准库」正是 P0+P1 那一类。

════════════════════════════════════════════════════════════════════════
判据（三条，每条都带反向对照）
════════════════════════════════════════════════════════════════════════

| # | 判据 | 不查会怎样 |
|---|---|---|
| **E1** | L2 里**有单元**的每个 `kb_type`，必须至少有一条 `to_evidence` 路径，**且该路径被机械复核通过** | 「四类知识库」名不副实，而没有东西会红 |
| **E1b** | `rules` 路径核 `kb/l3/candidates/rules.jsonl` 里**真有**该 `kb_type` 的行；`canonical_consumer` 路径核该文件**真的存在、在活路径、且 AST 非 docstring 字符串里含该形态名** | 声明可以撒谎 —— 写一句「有消费者」就变绿 |
| **E3** | `numbering.issued` 与 `canonical` 行数的差额，必须登记，**且登记里的两个数要与现算一致** | 读台账的人以为「发了 3155 个号 = 有 3155 条可引条款」；声明还会悄悄过期 |

**三条边界（照抄，别外推）**：
1. **只读**：只读 `kb/l2/units.jsonl`、`kb/l3/candidates/rules.jsonl`、`kb/l4/registry/l4.json`、
   `kb/l4/canonical/*.jsonl`、`kb/l7/registry/{library-supply.yaml,l7.json}` 与活代码源码。
   **不碰飞书、不写任何库内数据。**
2. **`canonical_consumer` 只认活代码**（`kb/l7/**`、`kb/l8/**`）+ `.py/.mjs/.js/.sh`。
   人手从 `.md` runbook 里抄命令读某个 canonical 文件，**本判据管不住**。
3. **「路径存在」≠「路径好用」** —— 本件只证明**有一条被机械复核过的读路径**，
   不证明命中率 / 准确率 / 性能。

════════════════════════════════════════════════════════════════════════
用法
════════════════════════════════════════════════════════════════════════

    python3 kb/l8/check_external_standard_supply.py            # 红 ⇒ 退出码 3
    python3 kb/l8/check_external_standard_supply.py --selftest # 反向对照（全离线）
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import sys

KB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
L2_UNITS = os.path.join(KB, "l2", "units.jsonl")
L3_RULES = os.path.join(KB, "l3", "candidates", "rules.jsonl")
L4_REG = os.path.join(KB, "l4", "registry", "l4.json")
L4_CANON = os.path.join(KB, "l4", "canonical")
L7_REG = os.path.join(KB, "l7", "registry", "l7.json")
SUPPLY = os.path.join(KB, "l7", "registry", "library-supply.yaml")

#: 「活路径」= 真正参与评审/供给的代码根。**别把 `kb/.work/` 算进来** ——
#: 那里是早期一次性批次脚本，本库已多次因为它误判成「有读者」。
LIVE_ROOTS = [os.path.join(KB, "l7"), os.path.join(KB, "l8")]
LIVE_EXTS = (".py", ".mjs", ".js", ".sh")
#: 在这些路径下出现的不算「活读者」（备份 / 归档 / 评测副本 / 反向测试）。
DEAD_PARTS = ("_backups", "_archive", "_skill-backups", "-fix/", "_reverse_test", ".pytest_cache")


# ══════════════════════════════════════════════════════════════════════
# 取数
# ══════════════════════════════════════════════════════════════════════

def _load_yaml(p):
    try:
        import yaml
    except ImportError:  # pragma: no cover
        print("需要 pyyaml", file=sys.stderr)
        raise SystemExit(2)
    with open(p, encoding="utf-8") as f:
        return yaml.safe_load(f)


def library_vocab() -> dict:
    """类目真源：`l7.json → citation_contract.libraries`。**不在这里抄第二份。**"""
    d = json.load(open(L7_REG, encoding="utf-8"))
    return (d.get("citation_contract") or {}).get("libraries") or {}


def l2_unit_counts() -> tuple:
    """每个 `kb_type` 在 L2 里有多少单元 —— 「这一类有没有料」。

    返回 `(raw, eligible)`：`raw` 是全部单元；`eligible` 剔掉**已被声明不作依据**的
    （`rule_eligible=False`，即 PRD §2.2 排除项 —— 2026-10-10 起真有这一档）。
    ★ 两个数都要报：只报 raw 会把「已排除的材料」也算成供给面；只报 eligible
    会把「这一类其实有 5421 个单元」这件事说小。
    """
    raw: dict = {}
    elig: dict = {}
    with open(L2_UNITS, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            d = json.loads(line)
            t = d.get("kb_type") or "unknown"
            raw[t] = raw.get(t, 0) + 1
            if d.get("rule_eligible") is not False:
                elig[t] = elig.get(t, 0) + 1
    return raw, elig


def rule_counts_by_type() -> dict:
    """`rules.jsonl` 里每个 `kb_type` 有多少条规则 —— ① 号路径的数据面。"""
    out: dict = {}
    with open(L3_RULES, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            t = json.loads(line).get("kb_type") or "unknown"
            out[t] = out.get(t, 0) + 1
    return out


def canonical_line_counts() -> dict:
    """每个定稿形态的行数（`kb/l4/canonical/<形态>.jsonl`）。"""
    out = {}
    if not os.path.isdir(L4_CANON):
        return out
    for fn in sorted(os.listdir(L4_CANON)):
        if not fn.endswith(".jsonl"):
            continue
        form = fn[: -len(".jsonl")]
        n = 0
        with open(os.path.join(L4_CANON, fn), encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    n += 1
        out[form] = n
    return out


def canonical_form_types() -> dict:
    """每个定稿形态里**实际装着哪些 `kb_type`** 的行 —— 判据 E1c 的数据面。

    ★ 这一条是本件自证 ③ 逼出来的：首版只核「这个文件读那个形态」，
    于是**指着一个不装本类内容的形态**（拿内部样本库的 `sample_case` 冒充外部标准库）
    照样能变绿 —— 那不是「接上了路」，那是**换了个库**。
    """
    out: dict = {}
    if not os.path.isdir(L4_CANON):
        return out
    for fn in sorted(os.listdir(L4_CANON)):
        if not fn.endswith(".jsonl"):
            continue
        form = fn[: -len(".jsonl")]
        c: dict = {}
        with open(os.path.join(L4_CANON, fn), encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                t = json.loads(line).get("kb_type") or "unknown"
                c[t] = c.get(t, 0) + 1
        out[form] = c
    return out


SOURCE_READONLY = os.path.join(KB, "l7", "registry", "source-readonly.yaml")


def excluded_records() -> tuple:
    """PRD §2.2 **已声明排除**的记录 ⇒ `(rids, verdict, source)`。**fail-closed**。

    真源 = `kb/l7/registry/source-readonly.yaml → prd_scope_exclusions`
    （`kb/l0/registry/kb.json → rule_eligible_overrides` 与它同口径；本件读前者，
    因为它是**权威登记件**）。读不到 / 空清单 ⇒ **抛错** ——
    静默当成「没有排除项」，正好会把下面 E4 变成一把**恒绿**的尺子（本库栽过那一类）。
    """
    try:
        supply = _load_yaml(SOURCE_READONLY)
    except Exception as e:  # noqa: BLE001
        raise SystemExit("[拒判] 读不到 %s（%r）—— fail-closed" % (SOURCE_READONLY, e))
    blk = supply.get("prd_scope_exclusions") or {}
    recs = blk.get("records") or []
    rids = {r.get("record_id") for r in recs if r.get("record_id")}
    if not rids:
        raise SystemExit("[拒判] %s 里没有 prd_scope_exclusions.records —— "
                         "空清单会让 E4 恒绿" % SOURCE_READONLY)
    return rids, (blk.get("implementation_status") or {}).get("verdict", ""), SOURCE_READONLY


def _unit_rid(unit: dict) -> str:
    """从 L2/L3 行的 `resource_id` 里取出记录 id（形如 `bitable__<tbl>__<rec>`）。"""
    rid = str(unit.get("resource_id") or "")
    return rid.split("__")[-1] if "__" in rid else rid


def check_exclusions(rids: set) -> dict:
    """E4 的数据面：被排除的记录，其单元在 **L2 / L3 两层**各有多少、几条已发号。

    ★ 为什么量到 L3：C8（`check_source_readonly.py`）**只量 L2** —— 那是它声明的范围。
    而「不许成为规则或依据」这句话的**上游**是 **L3 候选**，不是 L2：
    候选 → 定稿 → 被消费者读 ⇒ 才成为依据。
    """
    out = {"l2_units": 0, "l2_units_still_eligible": 0,
           "l3_candidates": 0, "l3_candidates_with_article_no": 0,
           "l3_units": 0, "l3_sample": [],
           "l3_candidate_ids_all": [], "l3_all_ids": [], "issued_articles": set()}
    excl_units = set()
    with open(L2_UNITS, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            d = json.loads(line)
            if _unit_rid(d) in rids:
                out["l2_units"] += 1
                if d.get("rule_eligible") is not False:
                    out["l2_units_still_eligible"] += 1
                excl_units.add(d.get("unit_id"))

    assigned = {}
    try:
        l4 = json.load(open(L4_REG, encoding="utf-8"))
        for _seg, body in ((l4.get("numbering") or {}).get("issued") or {}).items():
            assigned.update(body.get("assigned") or {})
    except Exception:  # noqa: BLE001
        pass

    out["issued_articles"] = set(assigned.values())
    scoped = os.path.join(KB, "l3", "candidates", "scoped_clauses.jsonl")
    if os.path.exists(scoped):
        # ★★ **按 `clause_id` 取最后一行**（追加式文件：发号后另起一行只加 `article_no`）。
        #   实测：6310 行 ⇒ 3155 个唯一 `clause_id`。**逐行读全部会把条数读成两倍** ——
        #   本件第一版就栽在这（把 47 读成 94）。口径同 `l4_retire.py::read_last_per_key`。
        last, n_rows = {}, 0
        with open(scoped, encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                n_rows += 1
                d = json.loads(line)
                last[d.get("clause_id")] = d
        out["l3_rows_in_file"] = n_rows
        out["l3_candidates_all"] = len(last)
        out["l3_all_ids"] = list(last.keys())
        units = set()
        for d in last.values():
            if d.get("unit_id") in excl_units or _unit_rid(d) in rids:
                out["l3_candidates"] += 1
                out["l3_candidate_ids_all"].append(d.get("clause_id"))
                units.add(d.get("unit_id"))
                cid = d.get("clause_id")
                if cid in assigned:
                    out["l3_candidates_with_article_no"] += 1
                    if len(out["l3_sample"]) < 5:
                        out["l3_sample"].append({"clause_id": cid,
                                                 "article_no": assigned[cid],
                                                 "text": str(d.get("clause_text") or "")[:60]})
        out["l3_units"] = len(units)
    return out


RETIRED_DECL = os.path.join(KB, "l3", "registry", "retired-candidates.yaml")


def retired_declaration(path: str = RETIRED_DECL) -> dict:
    """读**候选层退场名单**（由 `kb/l8/retire_excluded_candidates.py --apply` 生成）。

    返回 `{"present", "by_clause", "counts", "reason_code", "path"}`。
    ★ 名单**缺席不算「没有退场项」** —— 缺席时 E4a 会因为「命中未被覆盖」判红，
    不会静默放行（与 fail-closed 同一方向的纪律）。
    """
    if not os.path.exists(path):
        return {"present": False, "by_clause": {}, "counts": {}, "reason_code": None,
                "path": path}
    d = _load_yaml(path) or {}
    rows = d.get("retired") or []
    return {"present": True, "by_clause": {r.get("clause_id"): r for r in rows},
            "counts": d.get("counts") or {},
            "reason_code": (d.get("meta") or {}).get("reason_code"),
            "path": path}


def issued_counts() -> dict:
    """`l4.json → numbering.issued` 每个段已发多少号。"""
    d = json.load(open(L4_REG, encoding="utf-8"))
    out = {}
    for seg, body in ((d.get("numbering") or {}).get("issued") or {}).items():
        out[seg] = {"form": body.get("form"),
                    "issued": len(body.get("assigned") or {}),
                    "next_seq": body.get("next_seq")}
    return out


# ══════════════════════════════════════════════════════════════════════
# 「这个文件真的读那个形态吗」—— AST / 源码级复核
# ══════════════════════════════════════════════════════════════════════

def _py_string_literals_excluding_docstrings(src: str) -> list:
    """`.py`：取出**非 docstring** 的字符串常量字面量（值），丢了行号的一维表。

    为什么用 AST 而不是 grep：**grep 会把注释和 docstring 算进去**，于是
    `l4_gate.py` 抬头那句「`scoped_clause → clause_text`」会被当成"有读者"。
    实测踩过：按文件名 grep，`scoped_clause` 在 9 个活文件里"出现"
    —— 全是 gate / distiller（**生产者与检查者，不是消费者**）。
    """
    tree = ast.parse(src)
    doc_nodes = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = getattr(node, "body", None) or []
            if body and isinstance(body[0], ast.Expr) \
                    and isinstance(body[0].value, ast.Constant) \
                    and isinstance(body[0].value.value, str):
                doc_nodes.add(id(body[0].value))
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) \
                and id(node) not in doc_nodes:
            out.append(node.value)
    return out


def _noncomment_lines(src: str) -> list:
    """`.mjs`/`.js`/`.sh`：去掉整行注释后的行（够用，且**明说只到这个精度**）。"""
    out = []
    for line in src.splitlines():
        s = line.strip()
        if s.startswith("//") or s.startswith("#") or s.startswith("*") or s.startswith("/*"):
            continue
        out.append(line)
    return out


def file_reads_form(path: str, form: str) -> tuple:
    """这个文件**读** `form.jsonl` 吗？返回 `(bool, 证据)`。

    判据只有一条：`"<form>.jsonl"` 必须作为一个**非 docstring 的字符串字面量**出现。
    为什么这样就够：本库所有真实读取都是 `os.path.join(..., "canonical", "<form>.jsonl")`
    或 `"<form>.jsonl"` 直接拼路径 —— 文件名一旦进代码，就说明它在**被拼成路径用**；
    而注解 / docstring / 注释里提到它，**一律不算**（那正是首版误判的来源）。
    """
    if not os.path.exists(path):
        return False, "文件不存在"
    ext = os.path.splitext(path)[1].lower()
    try:
        src = open(path, encoding="utf-8").read()
    except Exception as e:  # noqa: BLE001
        return False, "读不到：%s" % e
    needle = "%s.jsonl" % form
    if ext == ".py":
        try:
            lits = _py_string_literals_excluding_docstrings(src)
        except SyntaxError as e:
            return False, "AST 解析失败：%s" % e
        if any(needle in s for s in lits):
            return True, "非 docstring 字符串字面量里含 %r" % needle
        return False, "只在 docstring / 注释里出现（**不算读者**）"
    lines = _noncomment_lines(src)
    if any(needle in ln for ln in lines):
        return True, "非注释行里含 %r" % needle
    return False, "只在注释里出现（不算读者）"


def is_live(path: str) -> bool:
    ap = os.path.abspath(path)
    if not any(ap.startswith(r + os.sep) or ap == r for r in LIVE_ROOTS):
        return False
    if any(part in ap for part in DEAD_PARTS):
        return False
    return ap.endswith(LIVE_EXTS)


# ══════════════════════════════════════════════════════════════════════
# 判据
# ══════════════════════════════════════════════════════════════════════

def check(supply: dict | None = None, ctx: dict | None = None) -> tuple:
    """E1 / E1b / E1c / E3。返回 `(problems, report)`。

    `ctx` 可注入数据面（自证用它做**全离线**的正例，证明判据不是恒红）。
    不给就现读真库。
    """
    supply = supply if supply is not None else _load_yaml(SUPPLY)
    if ctx is None:
        _raw, _elig = l2_unit_counts()
        ctx = {"units": _raw, "units_eligible": _elig, "rules": rule_counts_by_type(),
               "canon": canonical_line_counts(), "form_types": canonical_form_types(),
               "issued": issued_counts(), "reader": file_reads_form,
               "rules_file": L3_RULES,
               "excl_rids": excluded_records()[0]}
    vocab = library_vocab()
    units, rules = ctx["units"], ctx["rules"]
    elig = ctx.get("units_eligible", units)      # 缺省视作全部合格（注入档用）
    canon, form_types = ctx["canon"], ctx["form_types"]
    issued, reader = ctx["issued"], ctx["reader"]
    rules_file = ctx.get("rules_file", L3_RULES)

    problems: list = []
    report = {"vocab": vocab, "l2_units": units, "l2_units_eligible": elig,
              "rules_by_type": rules,
              "canonical": canon, "form_types": form_types, "issued": issued,
              "libraries": {}, "numbering_gap": []}

    declared = supply.get("libraries") or {}

    # ── E1 + E1b：有料的每一类都必须有一条**被复核通过**的路径 ──────────
    for kb_type in vocab:
        if kb_type == "unknown":
            continue
        n_units = units.get(kb_type, 0)
        lib = declared.get(kb_type)
        entry = {"label": (vocab.get(kb_type) or {}).get("label"),
                 "l2_units": n_units,
                 "l2_units_eligible": elig.get(kb_type, 0),
                 "l2_units_excluded": n_units - elig.get(kb_type, 0),
                 "rules_in_rules_jsonl": rules.get(kb_type, 0),
                 "declared_paths": [], "verified_paths": [], "ok": False,
                 "declared": lib is not None}
        if n_units == 0:
            entry["ok"] = True
            entry["note"] = "L2 无单元 ⇒ 不适用（本判据只管**有料**的类）"
            report["libraries"][kb_type] = entry
            continue
        if lib is None:
            problems.append("E1 %s（%s）在 L2 里有 %d 个单元，但**声明件里没有这一类**"
                            % (kb_type, entry["label"], n_units))
            report["libraries"][kb_type] = entry
            continue

        for p in (lib.get("to_evidence") or []):
            entry["declared_paths"].append(p)
            kind = p.get("kind")
            if kind == "rules":
                f = p.get("file") or ""
                full = f if os.path.isabs(f) else os.path.join(os.path.dirname(KB), f)
                if not os.path.exists(full):
                    entry["declared_paths"][-1] = dict(p, verified=False, why="文件不存在")
                    continue
                real = rules if os.path.abspath(full) == os.path.abspath(rules_file) else {}
                cnt = real.get(kb_type, 0)
                ok = cnt > 0
                entry["declared_paths"][-1] = dict(
                    p, verified=ok,
                    why=("该文件里 %s 有 %d 条" % (kb_type, cnt)) if ok
                        else "该文件里 %s **0 条** ⇒ 声明与实际不符" % kb_type)
                if ok:
                    entry["verified_paths"].append(p)
            elif kind == "canonical_consumer":
                f = p.get("file") or ""
                form = p.get("form") or ""
                full = f if os.path.isabs(f) else os.path.join(os.path.dirname(KB), f)
                if not is_live(full):
                    entry["declared_paths"][-1] = dict(
                        p, verified=False, why="不在活路径（kb/l7|kb/l8 之外，或在 _backups/_archive/-fix 下）")
                    continue
                if form not in canon:
                    entry["declared_paths"][-1] = dict(
                        p, verified=False,
                        why="`kb/l4/canonical/%s.jsonl` 不存在 ⇒ 声明的形态是空的" % form)
                    continue
                # ★ E1c：该形态里必须**真的装着本类的定稿行** ——
                #   否则就是"换了个库"（拿别类的形态冒充），不是接上了路。
                n_this = (form_types.get(form) or {}).get(kb_type, 0)
                if n_this == 0:
                    entry["declared_paths"][-1] = dict(
                        p, verified=False,
                        why="`%s.jsonl` 里**没有 %s 的行**（装的是 %s）⇒ 换了个库，不是接上了路"
                            % (form, kb_type,
                               "/".join("%s=%d" % (k, v)
                                        for k, v in sorted((form_types.get(form) or {}).items()))))
                    continue
                got, why = reader(full, form)
                entry["declared_paths"][-1] = dict(
                    p, verified=got, why=("%s；且该形态里有 %s 定稿行 %d 条" % (why, kb_type, n_this))
                    if got else why)
                if got:
                    entry["verified_paths"].append(p)
            else:
                entry["declared_paths"][-1] = dict(p, verified=False, why="未知 kind=%r" % kind)

        entry["ok"] = len(entry["verified_paths"]) > 0
        if not entry["ok"]:
            problems.append(
                "E1 %s（%s）在 L2 里有 %d 个单元，但**没有一条被复核通过的供给路径**"
                "（声明 %d 条 / 通过 %d 条；规则层 %d 条）—— 这一类**不可依据**"
                % (kb_type, entry["label"], n_units,
                   len(entry["declared_paths"]), len(entry["verified_paths"]),
                   rules.get(kb_type, 0)))
        report["libraries"][kb_type] = entry

    # ── E4：**已声明排除的记录，不得在任何一层成为依据** ────────────────
    #
    # 「不许成为规则或依据」这句话的上游是 **L3 候选**（候选 → 定稿 → 被消费 ⇒ 依据）。
    # C8 只量 L2 ⇒ 本判据把 L2 与 L3 一起量。
    excl = ctx.get("excl") if ctx else None
    if excl is None:
        excl = check_exclusions(ctx.get("excl_rids") or set())
    decl = ctx.get("retired") if ctx else None
    if decl is None:
        decl = retired_declaration()
    report["exclusions"] = excl
    report["retired"] = {k: v for k, v in decl.items() if k != "by_clause"}
    report["retired"]["n_listed"] = len(decl.get("by_clause") or {})
    report["retired"]["ids"] = sorted((decl.get("by_clause") or {}).keys())

    if excl["l2_units_still_eligible"] > 0:
        problems.append("E4 L2 里仍有 %d 个已排除记录的单元 rule_eligible≠false"
                        % excl["l2_units_still_eligible"])

    # ★ 退场声明**要能被复核**，不能是一张纸：五条
    by_clause = decl.get("by_clause") or {}
    hit_ids = set(excl.get("l3_candidate_ids_all") or [])
    if excl["l3_candidates"] > 0:
        n_cov = len(hit_ids & set(by_clause))
        if n_cov < excl["l3_candidates"]:
            problems.append(
                "E4 L3 候选里仍有 **%d 条**出自已声明排除的记录**未被退场覆盖**"
                "（命中 %d ／ 已退场覆盖 %d）—— 它们一旦定稿并被消费者读，就会变成"
                "**可引用依据**，而这正是 PRD §2.2「不审 brief」要避免的"
                % (excl["l3_candidates"] - n_cov, excl["l3_candidates"], n_cov))
    if by_clause:
        for cid, row in by_clause.items():
            if cid not in (excl.get("l3_all_ids") or hit_ids):
                problems.append("E4b 退场名单里的 %s **不在候选件里** ⇒ 凭空退场" % cid)
            art = row.get("article_no")
            if not art:
                problems.append("E4c 退场名单里的 %s **没写条款号** ⇒ 号不回收，退场必须留号" % cid)
            elif art not in (excl.get("issued_articles") or set()):
                problems.append("E4c 退场名单里的 %s 号 %r **不在 `numbering.issued` 里**" % (cid, art))
            if decl.get("reason_code") and row.get("reason_code") != decl.get("reason_code"):
                problems.append("E4d 退场名单里的 %s 理由码 %r ≠ 声明的 %r"
                                % (cid, row.get("reason_code"), decl.get("reason_code")))
        cnt = (decl.get("counts") or {}).get("retired")
        if cnt != len(by_clause):
            problems.append("E4e 退场名单自报 retired=%r，实际列了 %d 条 ⇒ 少报就是部分退场"
                            % (cnt, len(by_clause)))

    # ── E3：发号总数 ↔ 定稿总数 的差额必须登记，且**登记的数要与现算逐字一致** ──
    #
    # ★ 为什么用「总数」而不是「逐段」——第一版**按段比，当场被自证 ①e 判红**，
    #   而那个红是**我的尺子错了**，不是数据错了：
    #   段的 `form`（`numbering.issued[*].form`）**不是** canonical 文件名 ——
    #   实测 S-1 的 form 是 `sample_case_polarity`、W-3 是 `sample_case_wording_sample`，
    #   而这两个段**共同**落在 `kb/l4/canonical/sample_case.jsonl`（316 + 157 = 473 ✓）。
    #   `l4.json` 里**没有任何一处**声明「段 → canonical 文件」的映射
    #   （`canonical.files` 给的是「文件 → L3 源文件」，方向不同）。
    #   ⇒ 我**没有依据**按段算定稿数，就不能装作有。改成算**总数**（零歧义、可复算）。
    issued_total = sum(v.get("issued", 0) for v in issued.values())
    canonical_total = sum(canon.values())
    diff_total = issued_total - canonical_total
    report["numbering_gap"] = {"issued_total": issued_total,
                               "canonical_total": canonical_total,
                               "gap": diff_total,
                               "per_segment": issued,
                               "per_file": canon}
    ng = supply.get("numbering_gap") or {}
    if diff_total > 0:
        if not ng:
            problems.append("E3 已发 %d 个号、canonical 合计 %d 行（差 %d），**没有登记** ⇒ "
                            "读台账的人会以为有 %d 条可引条款"
                            % (issued_total, canonical_total, diff_total, issued_total))
        else:
            if ng.get("issued_total_measured") != issued_total:
                problems.append("E3 登记的发号总数 %r ≠ 现算 %d ⇒ 登记已过期"
                                % (ng.get("issued_total_measured"), issued_total))
            if ng.get("canonical_total_measured") != canonical_total:
                problems.append("E3 登记的定稿总数 %r ≠ 现算 %d ⇒ 登记已过期"
                                % (ng.get("canonical_total_measured"), canonical_total))
            if not str(ng.get("reason") or "").strip():
                problems.append("E3 登记了差额却没写 reason")
            report["numbering_gap"]["declared"] = True

    return problems, report


# ══════════════════════════════════════════════════════════════════════
# 反向对照（把缺陷真造一遍）—— **全离线，一台真库都不碰**
# ══════════════════════════════════════════════════════════════════════

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

    import copy
    import tempfile

    real = _load_yaml(SUPPLY)
    real_ctx = None  # 不给 = 现读真库

    # ① 基座（**真库**）：必须指出两类不可依据，且 E3 的登记**不能过期**
    probs, rep = check(real, real_ctx)
    ck("①基座 external_standard 判红",
       any("E1 external_standard" in x for x in probs), probs[:4])
    ck("①b 基座 product_desc 判红",
       any("E1 product_desc" in x for x in probs), probs[:4])
    ck("①c 措辞表达库不误伤", rep["libraries"]["wording"]["ok"],
       rep["libraries"].get("wording"))
    ck("①d 内部正负样本库不误伤", rep["libraries"]["internal_sample"]["ok"],
       rep["libraries"].get("internal_sample"))
    ck("①e E3 登记未过期（真件里没有 E3 红）",
       not [x for x in probs if x.startswith("E3")], [x for x in probs if x.startswith("E3")])

    # ② E1b 反向 A：**谎报一条路径**（指向一个不读该形态的活文件）⇒ 必须仍红
    s = copy.deepcopy(real)
    s["libraries"]["external_standard"]["to_evidence"] = [
        {"kind": "canonical_consumer", "form": "scoped_clause",
         "file": "kb/l8/bitable_stats.py"}]
    p2, _ = check(s, real_ctx)
    ck("②谎报消费者仍红", any("E1 external_standard" in x for x in p2), p2[:3])
    ck("②b 且写明理由（docstring / 不算读者 / 0 条）",
       any(("docstring" in x or "不算读者" in x or "0 条" in x) for x in p2), p2[:3])

    # ③ ★ E1c 反向：指着一个**真被读、但不装本类内容**的形态 ⇒ 必须仍红
    #    （拿内部样本库的 sample_case 冒充外部标准库 —— 那不是接上了路，是换了个库）
    s = copy.deepcopy(real)
    s["libraries"]["external_standard"]["to_evidence"] = [
        {"kind": "canonical_consumer", "form": "sample_case",
         "file": "kb/l7/skills/kb-content-review/scripts/review.py"}]
    p3, r3 = check(s, real_ctx)
    ck("③换个库冒充仍红", any("E1 external_standard" in x for x in p3), p3[:3])
    _why3 = [d.get("why", "") for d in r3["libraries"]["external_standard"]["declared_paths"]]
    ck("③b 且写明「没有 external_standard 的行（装的是 …）」",
       any("没有 external_standard 的行" in w for w in _why3), _why3)

    # ④ ★ 判据**不是恒红**：注入一份「外部标准库真的有路」的数据面 ⇒ 必须变绿
    green_ctx = {
        "units": {"external_standard": 5421, "internal_sample": 1510,
                  "wording": 7661, "product_desc": 54},
        "units_eligible": {"external_standard": 5368, "internal_sample": 1510,
                           "wording": 7661, "product_desc": 53},
        "rules": {"wording": 1018, "external_standard": 526, "product_desc": 12},
        "canon": {"scoped_clause": 526, "sample_case": 473,
                  "wording_entry": 56, "wording_revision_pair": 453, "clause": 123},
        "form_types": {"scoped_clause": {"external_standard": 526},
                       "sample_case": {"internal_sample": 316, "wording": 157},
                       "wording_entry": {"wording": 56},
                       "wording_revision_pair": {"wording": 453},
                       "clause": {"external_standard": 123}},
        "issued": {"W-1": {"form": "wording_entry", "issued": 56},
                   "W-2": {"form": "wording_revision_pair", "issued": 453},
                   "W-3": {"form": "sample_case_wording_sample", "issued": 157},
                   "S-1": {"form": "sample_case_polarity", "issued": 316},
                   "E-1": {"form": "scoped_clause", "issued": 526},
                   "E-2": {"form": "clause", "issued": 123}},
        "reader": lambda path, form: (True, "（注入：假定真读）"),
        "rules_file": L3_RULES,
        # ★ 自证里给一份**空退场声明**：否则控件会去读**真件**，
        #   于是「注入的 excl」与「真的 47 条退场」对不上 ⇒ 假红（踩过）。
        "retired": {"present": False, "by_clause": {}, "counts": {},
                    "reason_code": None, "path": "（自证夹具）"},
    }
    s = copy.deepcopy(real)
    s["libraries"]["external_standard"]["to_evidence"] = [
        {"kind": "rules", "file": "kb/l3/candidates/rules.jsonl"}]
    s["libraries"]["product_desc"]["to_evidence"] = [
        {"kind": "rules", "file": "kb/l3/candidates/rules.jsonl"}]
    s["numbering_gap"]["issued_total_measured"] = 1631
    s["numbering_gap"]["canonical_total_measured"] = 1631
    p4, r4 = check(s, green_ctx)
    ck("④有真路 ⇒ 外部标准库变绿（判据不恒红）",
       r4["libraries"]["external_standard"]["ok"]
       and not any("E1 external_standard" in x for x in p4),
       (r4["libraries"]["external_standard"], p4[:3]))
    ck("④b 四类全接上 ⇒ 整体转绿、退出码 0",
       not p4, p4[:3])

    # ⑤ E1b 反向 C：`rules` 路径声明一个**该文件里没有的 kb_type** ⇒ 必须仍红
    s = copy.deepcopy(real)
    s["libraries"]["product_desc"]["to_evidence"] = [
        {"kind": "rules", "file": "kb/l3/candidates/rules.jsonl"}]
    p5, _ = check(s, real_ctx)
    ck("⑤假 rules 路径仍红", any("E1 product_desc" in x for x in p5), p5[:3])

    # ⑥ E1 反向 D：**把声明整段删掉** ⇒ 必须红（缺声明 ≠ 放行）
    s = copy.deepcopy(real)
    del s["libraries"]["external_standard"]
    p6, _ = check(s, real_ctx)
    ck("⑥缺声明变红", any("声明件里没有这一类" in x for x in p6), p6[:3])

    # ⑦ E1b 反向 E：**AST 剔除 docstring 那条真的在起作用**
    d = tempfile.mkdtemp(prefix="libsupply-", dir="/tmp")
    fake = os.path.join(KB, "l8", "_selftest_fake_consumer.py")
    try:
        open(fake, "w", encoding="utf-8").write(
            '"""本文件只提到 scoped_clause.jsonl，并不读它。"""\nX = 1\n')
        got, why = file_reads_form(fake, "scoped_clause")
        ck("⑦docstring 里的形态名不算读者", got is False and "docstring" in why, (got, why))
        open(fake, "w", encoding="utf-8").write(
            '"""抬头仍提到 scoped_clause.jsonl。"""\nimport os\n'
            'P = os.path.join("kb", "l4", "canonical", "scoped_clause.jsonl")\n')
        got2, why2 = file_reads_form(fake, "scoped_clause")
        ck("⑦b 真进了路径拼接就算读者", got2 is True, (got2, why2))
    finally:
        if os.path.exists(fake):
            os.unlink(fake)
        import shutil
        shutil.rmtree(d, ignore_errors=True)

    # ⑧ E3 反向：登记的数改错 ⇒ 必须红（声明不许过期）
    s = copy.deepcopy(real)
    s["numbering_gap"]["issued_total_measured"] += 1
    p8, _ = check(s, real_ctx)
    ck("⑧E3 发号总数登记过期变红", any("E3 登记的发号总数" in x for x in p8), p8[:3])
    s = copy.deepcopy(real)
    s["numbering_gap"]["canonical_total_measured"] = 0
    p8b, _ = check(s, real_ctx)
    ck("⑧b E3 定稿总数登记过期变红", any("E3 登记的定稿总数" in x for x in p8b), p8b[:3])

    # ⑨ E3 反向：**把登记整段删掉** ⇒ 必须红
    s = copy.deepcopy(real)
    s["numbering_gap"] = {}
    p9, _ = check(s, real_ctx)
    ck("⑨E3 无登记变红", any("没有登记" in x for x in p9), p9[:3])

    # ⑩ ★ 段 form ≠ canonical 文件名这件事**必须被如实反映**（第一版就是栽在这）
    ck("⑩汇总数可复算",
       rep["numbering_gap"]["issued_total"]
       == sum(v["issued"] for v in rep["numbering_gap"]["per_segment"].values()),
       rep["numbering_gap"]["issued_total"])
    ck("⑩b S-1 的 form 不是 canonical 文件名（防有人改回按段比）",
       rep["numbering_gap"]["per_segment"]["S-1"]["form"] not in rep["numbering_gap"]["per_file"],
       (rep["numbering_gap"]["per_segment"]["S-1"]["form"],
        list(rep["numbering_gap"]["per_file"])))

    # ⑫ ★ E4：排除项下游回潮 —— 注入档里 L3 候选为 0 ⇒ 绿；造 1 条 ⇒ 红
    s = copy.deepcopy(real)
    s["libraries"]["external_standard"]["to_evidence"] = [
        {"kind": "rules", "file": "kb/l3/candidates/rules.jsonl"}]
    s["libraries"]["product_desc"]["to_evidence"] = [
        {"kind": "rules", "file": "kb/l3/candidates/rules.jsonl"}]
    s["numbering_gap"]["issued_total_measured"] = 1631
    s["numbering_gap"]["canonical_total_measured"] = 1631
    dirty = dict(green_ctx, excl={"l2_units": 53, "l2_units_still_eligible": 0,
                                  "l3_candidates": 1, "l3_units": 1,
                                  "l3_candidates_with_article_no": 1,
                                  "l3_sample": [{"clause_id": "x", "article_no": "E-1.1", "text": "t"}]})
    p12, _ = check(s, dirty)
    ck("⑫E4 下游回潮变红", any(x.startswith("E4") for x in p12), p12[:3])
    clean = dict(green_ctx, excl={"l2_units": 53, "l2_units_still_eligible": 0,
                                  "l3_candidates": 0, "l3_units": 0,
                                  "l3_candidates_with_article_no": 0, "l3_sample": []})
    p12b, _ = check(s, clean)
    ck("⑫b E4 干净 ⇒ 不误伤", not any(x.startswith("E4") for x in p12b), p12b[:3])
    # ⑫c L2 侧仍未落 ⇒ 也必须红（C8 那一半）
    dirty2 = dict(green_ctx, excl=dict(clean["excl"], l2_units_still_eligible=3))
    p12c, _ = check(s, dirty2)
    ck("⑫c E4 L2 未落变红",
       any(x.startswith("E4") and "L2 里仍有" in x for x in p12c), p12c[:3])

    # ⑫d ★ 退场声明**要能被复核**，不是一张纸
    import copy as _cp
    _base_decl = {"present": True, "by_clause": {}, "counts": {}, "reason_code": "prd_scope_exclusion",
                  "path": "x"}
    _hit = {"l2_units": 53, "l2_units_still_eligible": 0, "l3_candidates": 1, "l3_units": 1,
            "l3_candidates_with_article_no": 1, "l3_candidate_ids_all": ["cA"],
            "l3_all_ids": ["cA", "cZ"], "issued_articles": {"E-1.1", "E-1.2"},
            "l3_sample": [{"clause_id": "cA", "article_no": "E-1.1", "text": "t"}]}
    _good = dict(_base_decl, by_clause={"cA": {"clause_id": "cA", "article_no": "E-1.1",
                                               "reason_code": "prd_scope_exclusion"}},
                 counts={"retired": 1})
    p13, _ = check(s, dict(green_ctx, excl=_hit, retired=_good))
    ck("⑫d 退场覆盖 ⇒ E4 不红", not any(x.startswith("E4") for x in p13), p13[:3])
    # ⑫e 退场缺席 ⇒ 必须红（不许静默放行）
    p13b, _ = check(s, dict(green_ctx, excl=_hit, retired=_base_decl))
    ck("⑫e 退场缺席 ⇒ 红", any("未被退场覆盖" in x for x in p13b), p13b[:3])
    # ⑫f 凭空退场（clause_id 不在候选件里）⇒ 红
    _ghost = dict(_good, by_clause=dict(_good["by_clause"],
                                        cZZZ={"clause_id": "cZZZ", "article_no": "E-1.2",
                                              "reason_code": "prd_scope_exclusion"}),
                  counts={"retired": 2})
    p13c, _ = check(s, dict(green_ctx, excl=_hit, retired=_ghost))
    ck("⑫f 凭空退场 ⇒ 红", any("凭空退场" in x for x in p13c), p13c[:3])
    # ⑫g 退场不带号 ⇒ 红（号不回收，退场必须留号）
    _noart = dict(_good, by_clause={"cA": {"clause_id": "cA", "reason_code": "prd_scope_exclusion"}})
    p13d, _ = check(s, dict(green_ctx, excl=_hit, retired=_noart))
    ck("⑫g 退场不带号 ⇒ 红", any("没写条款号" in x for x in p13d), p13d[:3])
    # ⑫h 号不在 issued 里 ⇒ 红
    _badart = dict(_good, by_clause={"cA": {"clause_id": "cA", "article_no": "E-9.999",
                                            "reason_code": "prd_scope_exclusion"}})
    p13e, _ = check(s, dict(green_ctx, excl=_hit, retired=_badart))
    ck("⑫h 号不在台账里 ⇒ 红", any("不在 `numbering.issued` 里" in x for x in p13e), p13e[:3])
    # ⑫i 理由码对不上 ⇒ 红
    _badwhy = dict(_good, by_clause={"cA": {"clause_id": "cA", "article_no": "E-1.1",
                                            "reason_code": "别的理由"}})
    p13f, _ = check(s, dict(green_ctx, excl=_hit, retired=_badwhy))
    ck("⑫i 理由码对不上 ⇒ 红", any("理由码" in x for x in p13f), p13f[:3])
    # ⑫j 少报（counts.retired ≠ 实际条数）⇒ 红
    _short = dict(_good, counts={"retired": 0})
    p13g, _ = check(s, dict(green_ctx, excl=_hit, retired=_short))
    ck("⑫j 少报条数 ⇒ 红", any("少报就是部分退场" in x for x in p13g), p13g[:3])

    # ⑬ ★ 直接测**那把新门**本身：`l3_scope.exclusion_of` 对 rule_eligible=False 必须拦
    sys.path.insert(0, os.path.join(KB, "l8"))
    import l3_scope  # noqa: PLC0415
    _sc = l3_scope.build_scope()
    _u_false = {"kb_type": "external_standard", "unit_type": "clause",
                "heading_path": "#正文", "rule_eligible": False, "meta": {}}
    _code, _why = _sc.exclusion_of(_u_false)
    ck("⑬rule_eligible=False 被 L3 挡住", _code == "rule_eligible_false", (_code, _why))
    ck("⑬b 该原因码已登记进 CODES", "rule_eligible_false" in _sc.CODES, _sc.CODES)
    _u_true = dict(_u_false, rule_eligible=True)
    ck("⑬c rule_eligible=True 不受这道门影响",
       _sc.exclusion_of(_u_true)[0] != "rule_eligible_false", _sc.exclusion_of(_u_true))
    _u_missing = {k: v for k, v in _u_false.items() if k != "rule_eligible"}
    ck("⑬d 缺字段不受这道门影响（不误伤老数据）",
       _sc.exclusion_of(_u_missing)[0] != "rule_eligible_false",
       _sc.exclusion_of(_u_missing))
    ck("⑬e 原理由码一个字没动（out_of_scope_kb）",
       _sc.exclusion_of({"kb_type": "product_desc", "unit_type": "clause",
                         "heading_path": "#正文", "meta": {}})[0] == "out_of_scope_kb",
       _sc.exclusion_of({"kb_type": "product_desc", "unit_type": "clause",
                         "heading_path": "#正文", "meta": {}}))

    # ⑪ 空输入不恒绿
    p11, _ = check({"libraries": {}, "numbering_gap": {}},
                   {"units": {"wording": 1}, "rules": {}, "canon": {},
                    "form_types": {}, "issued": {},
                    "reader": lambda p, f: (False, "无"), "rules_file": L3_RULES})
    ck("⑪空声明不恒绿", len(p11) >= 1, p11[:3])

    # ⑨ 空输入不恒绿
    p9, _ = check({"libraries": {}, "numbering_gap": []})
    ck("⑨空声明不恒绿", len(p9) >= 4, p9[:4])

    print("check_external_standard_supply --selftest：%d/%d" % (ok, ok + fail))
    for f in fails:
        print("  ✗", f)
    return 0 if fail == 0 else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="四类知识库的供给路径判据（PRD §7.1 · 目标 5 收口前置）")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return _selftest()

    probs, rep = check()
    print("四类知识库供给路径核验（只读；不碰飞书）")
    print("-" * 78)
    print("  %-22s %8s %8s %8s %8s  %s"
          % ("知识库（kb_type）", "L2单元", "合格", "规则条数", "路径", "能依据？"))
    for t, e in rep["libraries"].items():
        print("  %-22s %8d %8d %8d %8d  %s"
              % ("%s/%s" % (t, e["label"]), e["l2_units"], e["l2_units_eligible"],
                 e["rules_in_rules_jsonl"], len(e["verified_paths"]),
                 "✅" if e["ok"] else "❌"))
    print("  ★ 「合格」= 剔掉 `rule_eligible=False`（PRD §2.2 已声明不作依据的单元）；两个数都报，别只看一个。")
    ex = rep.get("exclusions") or {}
    print("  排除项下游回潮（判据 E4 · 真源 %s）：" % os.path.basename(SOURCE_READONLY))
    print("    L2 单元 %d（其中仍合格 %d） ｜ L3 候选 **%d 条**（涉 %d 单元；**已发号 %d 条**）"
          % (ex.get("l2_units", 0), ex.get("l2_units_still_eligible", 0),
             ex.get("l3_candidates", 0), ex.get("l3_units", 0),
             ex.get("l3_candidates_with_article_no", 0)))
    _rt = rep.get("retired") or {}
    print("    退场声明：%s ｜ 列了 %d 条 ｜ 覆盖命中 %d/%d %s"
          % (os.path.basename(_rt.get("path") or RETIRED_DECL) if _rt.get("present") else "**缺席**",
             _rt.get("n_listed", 0),
             len(set(ex.get("l3_candidate_ids_all") or []) & set(_rt.get("ids") or [])),
             ex.get("l3_candidates", 0),
             "" if not _rt.get("present") else "（号保留、候选件未动）"))
    for x in (ex.get("l3_sample") or [])[:3]:
        print("      %s = %s ｜ %r" % (x["clause_id"], x["article_no"], x["text"]))
    print("-" * 78)
    ng = rep["numbering_gap"]
    print("  发号 ↔ 定稿（判据 E3）：已发号合计 %d ｜ canonical 合计 %d ｜ 差 %d%s"
          % (ng["issued_total"], ng["canonical_total"], ng["gap"],
             "（已登记）" if ng.get("declared") else ""))
    if ng.get("gap", 0) <= 0:
        print("    （无差额，无需登记）")
    else:
        print("    ★ 逐段（注意：段的 `form` **不是** canonical 文件名，S-1/W-3 共用 sample_case.jsonl）：")
        for seg, b in ng["per_segment"].items():
            print("      %-5s form=%-28s 已发 %4d" % (seg, b.get("form"), b["issued"]))
        print("    ★ 逐文件：%s"
              % " ｜ ".join("%s=%d" % (k, v) for k, v in sorted(ng["per_file"].items())))
    print("-" * 78)
    if probs:
        for x in probs:
            print("  ✗ %s" % x)
        kinds = []
        if any(x.startswith("E1 ") for x in probs):
            kinds.append("有知识库**不可依据**")
        if any(x.startswith("E4") for x in probs):
            kinds.append("**已声明排除的内容下游回潮**")
        if any(x.startswith("E3") for x in probs):
            kinds.append("发号↔定稿差额未登记")
        print("结论：❌ 不过（%d 条）—— %s" % (len(probs), "；".join(kinds)))
        return 3
    print("结论：✅ 过（E1 每类有料者皆有路 / E1b 路径经机械复核 / E3 差额已登记且未过期）")
    print("★ 边界：只证明**有一条被复核过的读路径**，不证明命中率 / 准确率 / 性能。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
