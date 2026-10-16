#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
verify_fixed.py —— 「**同一个问题不许修第二遍**」这条承诺的判据

Owner 2026-10-14：「你修复完的问题记得落库，避免后面重复修。」

「落库」在这里是什么（说清楚，免得读的人以为在说那本措辞表达库）：
  · 本项目的**知识库**（Momcozy 内容治理库）是**内容侧**的库（条款号 / 禁用表达），
    没有系统与工程类条目 —— 把工程教训塞进去是**污染**，所以**不入那本库**；
  · 工程侧的「落库」= 一份**可查的已修问题索引** + **一个判据**：
    `PMO/已修问题.jsonl`（机器读）+ `PMO/已修问题索引.md`（人读）+ 本检查器。

`AGENTS.md` §2.4：写进文档的每条约束，必须指得出**哪一行在拦它**。
「已修问题索引」如果没有判据，它就会**腐烂成一张过期的白名单** ——
指着一堆早就不存在的文件说「这个问题已经修好了」。所以本文件逐条断：

  A1  JSONL 读得出、字段齐全（`id/title/symptom/root_cause/fix_files/self_check/verify_cmd`）
  A2  `id` 唯一
  A3  **每一个 `fix_files` 路径都存在**（清单不许指空）
  A4  **每一个 `enforced_by` 的判据串都真的在 `fix_files` 里找得到**
      —— 这条是「名字出现过 ≠ 拦得住」的**反面**：它至少要求那行代码还在原处
  A5  `verify_cmd` 的脚本存在（不许指向一个不存在的自证命令）
  A6  没有两条记录在**同一条 `root_cause`** 上重复（同一形状修两遍 = 这份清单没起作用）
  B1  人读的那份 md 里，**每一条 id 都出现**
  B2  md 里的条数 == jsonl 的条数（数字型说法必须算出来，不许写死；§2.2 第 1 条）
  B3  判据在本仓之外的记录**看得见**（未测几条，单列一行 —— 未测不是通过，也不是坏）
  C   反向对照：**喂已知坏样本，本检查器必须报红**
      （坏样本六类：文件不存在 / 判据串不在源码里 / 自证命令不存在 / id 重复 /
        同一 root_cause / 没写执行点）
  C2  反向对照（成对）：记录级 `repo_root` 的**三半**都要咬得住 ——
      指不到 ⇒ 记未测不判红；**不写** ⇒ 照旧报红；它是**后备根**（本仓优先，混合记录两半都找得到）

★ 2026-10-16（FIX-035）：A3/A4/A5 的根从「本仓一个」变成「本仓 ＋ 可选后备根」。
  起因：有 5 条记录（FIX-026/027/028/029/031）的判据**不在本仓**，而在**知识库工作区**
  （`…/知识库/内容治理/采集-20261013/`，2026-10-13 那批一次性采集／修复脚本）——
  它们**既没废弃也没写错**（路径相对于那个工作区是对的），本检查器只是**只有一个根**，
  于是那 5 条**永远红着 3 项**。而**一条假红会挤掉一个真问题**。
  现在：记录可写可选字段 `repo_root`（后备根）；**本仓优先**，本仓找不到才到它下面找；
  它指不到时记**未测**（不判红，但必须看得见）。缺省不写 ⇒ 行为与改动前**逐字相同**。

用法：
  python3 tools/verify_fixed.py            # 全跑（零网络）
  python3 tools/verify_fixed.py --verbose
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JSONL = ROOT / "PMO" / "已修问题.jsonl"
INDEX = ROOT / "PMO" / "已修问题索引.md"

REQUIRED = ("id", "title", "symptom", "root_cause", "fix_files", "self_check", "verify_cmd")

results: list[tuple[str, bool, str]] = []


def check(cid: str, ok: bool, msg: str) -> None:
    results.append((cid, bool(ok), msg))


def load(path: Path):
    out, errs = [], []
    if not path.exists():
        return None, [f"清单不存在：{path.relative_to(ROOT)}"]
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError as e:
            errs.append(f"第 {i} 行不是合法 JSON：{e.msg}")
    return out, errs


def audit(entries, *, root: Path, index_path: Path):
    """
    纯判据：回 `(problems, untested)`。坏样本也能直接喂进来做反向对照。

    ★★ 2026-10-16（FIX-035）—— 记录级可选字段 `repo_root` ＋ **第三态「未测」**：

    有几条记录的判据（脚本与判据串）**不在本仓**，而在知识库工作区
    （`…/知识库/内容治理/采集-20261013/`，那批 2026-10-13 的一次性采集/修复脚本）。
    本检查器原先只有**一个根**（本仓 `ROOT`），于是那 5 条**永远红着 3 项**（A3/A4/A5）——
    而它们红的原因是「跨工作区」，不是「判据没了」。**一条假红会挤掉一个真问题。**

      · 记录给了 `repo_root` 且**指得到** ⇒ A3/A4/A5 照旧**逐条真核**（不放松一个字）；
      · 记录给了 `repo_root` 但**指不到**（那个工作区不在本机了）⇒ 这三项记 **未测**、**不判红**，
        但**必须看得见**（`main` 里单列一行）—— 「未测 ≠ 坏了」，也**不等于核过了**；
      · 记录**没给** `repo_root` ⇒ 缺省就是本仓，行为与改动前**逐字相同**。
    """
    problems: list[str] = []
    untested: list[str] = []
    seen_ids, causes = set(), {}
    for e in entries:
        eid = str(e.get("id") or "(无 id)")
        missing = [k for k in REQUIRED if not e.get(k)]
        if missing:
            problems.append(f"{eid} 缺字段：{'/'.join(missing)}")
        if eid in seen_ids:
            problems.append(f"{eid} 重复（id 必须唯一）")
        seen_ids.add(eid)

        # ★ FIX-035：这条记录的判据在哪些根下解析 —— `repo_root` 是**后备根**，不是替换根。
        #   为什么必须是后备：有的记录是**混合**的（例 FIX-028 的 `fix_files` 同时列着
        #   本仓的 `tools/agent/review_publish.mjs` 与跨仓的 `采集-20261013/backfill_confidence_notes.py`）
        #   —— 拿 `repo_root` 顶替本仓，本仓那一半立刻找不到了（实测：改替换根当场多一条红）。
        #   解析顺序：**本仓优先**，本仓找不到再到 `repo_root` 找；两边都没有 ⇒ 照旧报红。
        base, base_ok = root, True
        roots = [root]
        rr = str(e.get("repo_root") or "").strip()
        if rr:
            base = Path(rr).expanduser()
            if not base.is_dir():
                base_ok = False
                untested.append(
                    f"{eid} 的判据在本仓之外（`repo_root`={rr}）—— 该目录现在**指不到**，"
                    f"这条的 A3/A4/A5 **未测**（不是通过，也不是坏）")
            else:
                roots.append(base)

        if base_ok:
            # A3 文件必须都在（本仓或后备根，任一处找得到即可）
            for rel in e.get("fix_files") or []:
                if not any((b / rel).exists() for b in roots):
                    problems.append(f"{eid} 指着一个不存在的文件：{rel}（本仓与 `repo_root` 下都没有）")

            # A4 判据串必须真的在那些文件里
            needles = [n for n in (e.get("enforced_by") or []) if n]
            if not needles:
                problems.append(f"{eid} 没写 `enforced_by` —— 指不出哪一行在拦它，就只是一句注释（§2.4）")
            else:
                blob = ""
                for rel in e.get("fix_files") or []:
                    for b in roots:
                        p = b / rel
                        if p.exists():
                            blob += p.read_text(encoding="utf-8", errors="ignore")
                            break
                for n in needles:
                    if n not in blob:
                        problems.append(f"{eid} 的判据串在源码里找不到：{n!r}（判据可能已经被改掉/删掉）")

            # A5 自证命令的脚本必须在（同上，两个根任一处）
            for cmd in [e.get("verify_cmd"), e.get("self_check")]:
                if not cmd:
                    continue
                parts = str(cmd).split()
                script = next((p for p in parts if p.endswith((".py", ".mjs", ".sh"))), None)
                if script and not any((b / script).exists() for b in roots):
                    problems.append(f"{eid} 的自证命令指向不存在的脚本：{script}")

        # A6 同一 root_cause 不许两条
        rc = str(e.get("root_cause") or "").strip()
        if rc:
            if rc in causes:
                problems.append(f"{eid} 与 {causes[rc]} 的 `root_cause` 逐字相同 —— 同一个形状记两遍等于没记")
            causes[rc] = eid

    # B1/B2 人读的那份
    if not index_path.exists():
        problems.append(f"人读的那份不存在：{index_path.relative_to(root)}")
    else:
        md = index_path.read_text(encoding="utf-8")
        for e in entries:
            if str(e.get("id")) not in md:
                problems.append(f"{e.get('id')} 没出现在 {index_path.name} 里（人查不到 = 没落库）")
        for m in __import__("re").finditer(r"共\s*(\d+)\s*条", md):
            if int(m.group(1)) != len(entries):
                problems.append(f"{index_path.name} 写着「共 {m.group(1)} 条」，实际 {len(entries)} 条")
    return problems, untested


def main() -> int:
    entries, errs = load(JSONL)
    check("A1", entries is not None and not errs,
          f"清单读得出、每行都是合法 JSON（实测 {len(entries or [])} 条"
          + (f"，解析错误 {len(errs)} 处：{errs[:2]}" if errs else "") + ")")
    if entries:
        problems, untested = audit(entries, root=ROOT, index_path=INDEX)
        by_id = {}
        for p in problems:
            by_id.setdefault(p.split()[0], []).append(p)
        check("A2", not any("重复" in p for p in problems), "id 唯一")
        check("A3", not any("不存在的文件" in p for p in problems),
              "每条 `fix_files` 指的文件都真的在盘上（清单不许指空）")
        check("A4", not any("判据串" in p or "enforced_by" in p for p in problems),
              "每条都写得出执行点，且那个判据串**真的在源码里找得到**"
              "（指不出哪一行在拦它 = 只是一句注释）")
        check("A5", not any("自证命令" in p for p in problems), "自证命令指向的脚本都存在")
        check("A6", not any("root_cause" in p for p in problems),
              "没有两条记录共用同一条 `root_cause`（同一形状记两遍 = 这份清单没起作用）")
        check("B1", not any("没出现在" in p for p in problems), "人读的那份索引里每条 id 都在")
        check("B2", not any("实际" in p and "条" in p for p in problems),
              "索引里的条数**算出来**等于实际条数（不写死）")
        # ★ FIX-035：第三态必须**看得见** —— 判据在本仓之外时，既不许判绿、也不许静默
        check("B3", True,
              f"判据在本仓之外的记录**看得见**（未测 {len(untested)} 条 —— "
              f"未测既不是通过，也不是坏；要真核得让那个工作区在本机）")
        if untested:
            print("未测明细（判据不在本仓，本次**核不了** —— 这不是通过）：")
            for u in untested:
                print("  ·", u)
        if any(p for p in problems):
            print("不通过明细：")
            for p in problems:
                print("  ·", p)
    else:
        for cid in ("A2", "A3", "A4", "A5", "A6", "B1", "B2"):
            check(cid, False, "清单读不出 ⇒ 这些判据都无从谈起")

    # ── C 反向对照：喂坏样本，判据必须报红（否则上面全是恒真）──────────────────
    good = [{
        "id": "FIX-T", "title": "t", "symptom": "s", "root_cause": "rc-1",
        "fix_files": ["tools/verify_fixed.py"], "enforced_by": ["def audit("],
        "self_check": "python3 tools/verify_fixed.py", "verify_cmd": "python3 tools/verify_fixed.py",
    }]
    bad_cases = {
        "指着一个不存在的文件": [{**good[0], "fix_files": ["tools/__nope__.mjs"]}],
        "判据串不在源码里": [{**good[0], "enforced_by": ["这道判据根本不存在("]}],
        "自证命令指向不存在的脚本": [{**good[0], "verify_cmd": "python3 tools/__nope__.py"}],
        "id 重复": [good[0], dict(good[0])],
        "root_cause 逐字相同": [good[0], {**good[0], "id": "FIX-T2"}],
        "没写 enforced_by": [{**good[0], "enforced_by": []}],
    }
    import tempfile
    bad_ok = True
    detail = []
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        idx = tdp / "idx.md"
        for name, sample in bad_cases.items():
            idx.write_text("共 999 条\n" + " ".join(e["id"] for e in sample), encoding="utf-8")
            probs, _ = audit(sample, root=ROOT, index_path=idx)
            if not probs:
                bad_ok = False
                detail.append(name)
    check("C", bad_ok,
          "反向对照：喂 6 类坏样本（指空文件 / 判据串不在源码 / 自证脚本不存在 / id 重复 / "
          "同一 root_cause / 没写执行点），判据必须每种都报红"
          + (f" —— 没报红的：{detail}" if detail else ""))

    # ── C2 ★ FIX-035：`repo_root` 的**成对**反向对照 ────────────────────────────────
    #   要证明的是「未测」**不是**把 A3/A4/A5 变成恒绿的后门。两条必须成对，缺一条就证明不了：
    #     ① 同一条坏记录（`fix_files` 指空）**不给** `repo_root` ⇒ 必须照旧报红（缺省=本仓，一个字没松）；
    #     ② 同一条坏记录**给**一个指不到的 `repo_root` ⇒ 不判红，但必须**记进 untested**（看得见）。
    #   少了 ① ⇒ 「只要写上 repo_root 什么都过」；少了 ② ⇒ 变回静默放过。
    c2_ok, c2_detail = True, []
    with tempfile.TemporaryDirectory() as td:
        idx = Path(td) / "idx.md"
        idx.write_text("共 1 条 FIX-T", encoding="utf-8")
        bad_row = {**good[0], "fix_files": ["tools/__nope__.mjs"]}
        p1, _u1 = audit([bad_row], root=ROOT, index_path=idx)
        if not p1:
            c2_ok = False
            c2_detail.append("① 不给 repo_root 时竟然没报红")
        p2, u2 = audit([{**bad_row, "repo_root": "/__没有这个目录__"}], root=ROOT, index_path=idx)
        if p2:
            c2_ok = False
            c2_detail.append(f"② 给了指不到的 repo_root 仍报红：{p2[:1]}")
        if not u2:
            c2_ok = False
            c2_detail.append("② 未测没有被记下来（等于静默放过）")
        # ③ **后备根**语义：本仓那一半照旧找得到，**只在 repo_root 下**的那一半也找得到。
        #    钉住这条，是因为「拿 repo_root 顶替本仓」这个错法实测真的会多出一条红
        #    （FIX-028 是混合记录：本仓 2 个文件 + 跨仓 1 个文件）。
        with tempfile.TemporaryDirectory() as td3:
            (Path(td3) / "kb_only.py").write_text("NEEDLE_KB_ONLY(\n", encoding="utf-8")
            row3 = {**good[0], "fix_files": ["tools/verify_fixed.py", "kb_only.py"],
                    "enforced_by": ["def audit(", "NEEDLE_KB_ONLY("], "repo_root": td3}
            p3, u3 = audit([row3], root=ROOT, index_path=idx)
            if p3 or u3:
                c2_ok = False
                c2_detail.append(f"③ 后备根没生效：{p3[:1] or u3[:1]}")
    check("C2", c2_ok,
          "反向对照（成对）：`repo_root` 指不到 ⇒ 记**未测**、不判红；**不写** `repo_root` ⇒ 照旧报红；"
          "`repo_root` 是**后备根**（本仓优先，混合记录两半都找得到）"
          + (f" —— {c2_detail}" if c2_detail else ""))

    n_fail = sum(1 for _, ok, _ in results if not ok)
    print("\n" + "=" * 74)
    for cid, ok, msg in results:
        print(f"  {'✅' if ok else '❌'} {cid}  {msg}")
    print("=" * 74)
    print(("❌ 有红" if n_fail else "✅ 全过") + f"（共 {len(results)} 项断言，{n_fail} 项红）")
    return 1 if n_fail else 0


if __name__ == "__main__":
    sys.exit(main())
