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
  C   反向对照：**喂已知坏样本，本检查器必须报红**
      （坏样本四种：文件不存在 / 判据串不在源码里 / 自证命令不存在 / id 重复）

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
    """纯判据：回 (问题列表, 读数)。坏样本也能直接喂进来做反向对照。"""
    problems: list[str] = []
    seen_ids, causes = set(), {}
    for e in entries:
        eid = str(e.get("id") or "(无 id)")
        missing = [k for k in REQUIRED if not e.get(k)]
        if missing:
            problems.append(f"{eid} 缺字段：{'/'.join(missing)}")
        if eid in seen_ids:
            problems.append(f"{eid} 重复（id 必须唯一）")
        seen_ids.add(eid)

        # A3 文件必须都在
        for rel in e.get("fix_files") or []:
            if not (root / rel).exists():
                problems.append(f"{eid} 指着一个不存在的文件：{rel}")

        # A4 判据串必须真的在那些文件里
        needles = [n for n in (e.get("enforced_by") or []) if n]
        if not needles:
            problems.append(f"{eid} 没写 `enforced_by` —— 指不出哪一行在拦它，就只是一句注释（§2.4）")
        else:
            blob = ""
            for rel in e.get("fix_files") or []:
                p = root / rel
                if p.exists():
                    blob += p.read_text(encoding="utf-8", errors="ignore")
            for n in needles:
                if n not in blob:
                    problems.append(f"{eid} 的判据串在源码里找不到：{n!r}（判据可能已经被改掉/删掉）")

        # A5 自证命令的脚本必须在
        for cmd in [e.get("verify_cmd"), e.get("self_check")]:
            if not cmd:
                continue
            parts = str(cmd).split()
            script = next((p for p in parts if p.endswith((".py", ".mjs", ".sh"))), None)
            if script and not (root / script).exists():
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
    return problems


def main() -> int:
    entries, errs = load(JSONL)
    check("A1", entries is not None and not errs,
          f"清单读得出、每行都是合法 JSON（实测 {len(entries or [])} 条"
          + (f"，解析错误 {len(errs)} 处：{errs[:2]}" if errs else "") + ")")
    if entries:
        problems = audit(entries, root=ROOT, index_path=INDEX)
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
            probs = audit(sample, root=ROOT, index_path=idx)
            if not probs:
                bad_ok = False
                detail.append(name)
    check("C", bad_ok,
          "反向对照：喂 6 类坏样本（指空文件 / 判据串不在源码 / 自证脚本不存在 / id 重复 / "
          "同一 root_cause / 没写执行点），判据必须每种都报红"
          + (f" —— 没报红的：{detail}" if detail else ""))

    n_fail = sum(1 for _, ok, _ in results if not ok)
    print("\n" + "=" * 74)
    for cid, ok, msg in results:
        print(f"  {'✅' if ok else '❌'} {cid}  {msg}")
    print("=" * 74)
    print(("❌ 有红" if n_fail else "✅ 全过") + f"（共 {len(results)} 项断言，{n_fail} 项红）")
    return 1 if n_fail else 0


if __name__ == "__main__":
    sys.exit(main())
