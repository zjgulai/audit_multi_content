#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""变异自证：`p0_rule_config`（PRD §6.5「适用内容类型」「生效版本」）这条判据**真的守得住**。

库规（`~/.dsh/AGENTS.md`）逐字：
    **新增任何判据，必须同时给反向对照** —— 否则它就是注释。
    **自证方式**：把缺陷**真造一遍**（例：抹掉模式表的 `article_no`），尺子必须**精确变红**、退出码 3。

## 为什么**原地**变异（不是副本）

被测件 `kb/.work/l5_integrity.py` 开头就 `os.chdir(ROOT)`，并且**按固定路径**读
`kb/l5/p0_patterns.jsonl` ⇒ 副本没法被它读到。与 `mutate_dimension_wiring.py` 同一处境，
所以照它那套硬安全措施，三条缺一不可：
  ① 先存 `sha256`；② `finally` **必定**还原（哪怕中途抛异常）；③ 还原后**回读复算 sha**，不符即非零退出。

## 「精确变红」判的是**差分集合相等**

基线时本闸门本来就有 2 项 FAIL（`frozen_layers` / `l3_append_only`，属已登记基线漂移）
⇒ 不能断言「FAIL 集合 == {p0_rule_config}」。判据是 **变异后的 FAIL 集合 − 基线 FAIL 集合**：
  · 少一个 ⇒ 报「**漏**」（这条判据没钉住）；· 多一个 ⇒ 报「**脆**」（判据连坐别的项）。

## 用法

    python3 kb/.work/mutate_rule_config.py        # 0 = 全部精确命中；3 = 有漏/有脆 或 还原失败

配套：本判据由 `kb/l7/scripts/l5_gate.py` 的 `SUBSTANTIVE` 列为**实质判据**（未出现也判红）。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TARGET = os.path.join(ROOT, "kb/l5/p0_patterns.jsonl")
CHECKER = os.path.join(ROOT, "kb/.work/l5_integrity.py")
EVIDENCE = os.path.join(ROOT, "kb/.work/l5_integrity.json")
ITEM = re.compile(r"^\[(PASS|FAIL)\]\s+(\S+)\s*$")
NEW_CHECK = "p0_rule_config"


def sha() -> str:
    return hashlib.sha256(open(TARGET, "rb").read()).hexdigest()


def run_checker() -> tuple[set, dict]:
    """跑自检器 ⇒ (FAIL 集合, 证据 dict)。"""
    r = subprocess.run([sys.executable, CHECKER], capture_output=True, text=True, cwd=ROOT)
    fails = set()
    for line in (r.stdout or "").splitlines():
        m = ITEM.match(line.strip())
        if m and m.group(1) == "FAIL":
            fails.add(m.group(2))
    ev = json.load(open(EVIDENCE, encoding="utf-8")) if os.path.exists(EVIDENCE) else {}
    return fails, ev


def mutate(lines: list, which: int) -> list:
    """在**内存里**造缺陷，返回新的行列表。每条变异只动**一行**（精确性靠这个）。"""
    rows = [json.loads(l) for l in lines if l.strip()]
    victim = next(r for r in rows if r.get("rule_code") == "H01")   # 固定挑 H01，可复现
    if which == 1:
        victim.pop("content_type", None)
    elif which == 2:
        victim.pop("rule_version", None)
    elif which == 3:
        victim["content_type"] = []          # 空数组 ⇒ 与 None 同判「空」
    elif which == 4:
        victim["rule_version"] = ""          # 空串
    return [json.dumps(r, ensure_ascii=False, sort_keys=True) for r in rows]


MUTATIONS = [
    (1, "M1 删掉 H01 的 content_type 键"),
    (2, "M2 删掉 H01 的 rule_version 键"),
    (3, "M3 把 H01 的 content_type 改成空数组 []"),
    (4, "M4 把 H01 的 rule_version 改成空串 \"\""),
]


def main() -> int:
    before = sha()
    original = open(TARGET, encoding="utf-8").read()
    lines = original.splitlines()

    print("被测件：kb/l5/p0_patterns.jsonl ｜ 变异前 sha256=%s" % before[:16])
    print("判据：kb/.work/l5_integrity.py::%s（l5_gate 已列为实质判据）" % NEW_CHECK)

    base_fails, base_ev = run_checker()
    base_new = base_ev.get("checks", {}).get(NEW_CHECK, {})
    print("\n基线：FAIL 项 %s ｜ %s = %s（模式 %s 条）"
          % (sorted(base_fails) or "无", NEW_CHECK, base_new.get("verdict"),
             base_new.get("patterns")))
    if base_new.get("verdict") != "PASS":
        print("❌ 基线就没过 —— 先修基线，变异自证无意义")
        return 2

    passed = failed = 0
    try:
        for which, name in MUTATIONS:
            payload = "\n".join(mutate(lines, which)) + "\n"
            with open(TARGET, "w", encoding="utf-8") as fh:
                fh.write(payload)
            fails, ev = run_checker()
            delta = fails - base_fails
            chk = ev.get("checks", {}).get(NEW_CHECK, {})
            missing = (chk.get("missing_content_type") or []) + (chk.get("missing_rule_version") or [])
            # ★ 精确性：差分必须**正好**是 {NEW_CHECK}，且缺项**只有 H01 一条**
            if delta == {NEW_CHECK} and missing == ["H01"]:
                passed += 1
                print("✅ %-34s ⇒ 变红，差分={'%s'}，缺项=%s（精确）" % (name, NEW_CHECK, missing))
            else:
                failed += 1
                extra = delta - {NEW_CHECK}
                print("❌ %-34s ⇒ 不精确" % name)
                print("      差分=%s %s" % (sorted(delta),
                      ("← **漏**：判据没红" if NEW_CHECK not in delta else "← **脆**：连坐了 %s" % sorted(extra))))
                print("      缺项=%s（期望 ['H01']）" % missing)
    finally:
        # ② 无论成败，必定还原
        with open(TARGET, "w", encoding="utf-8") as fh:
            fh.write(original)

    after = sha()
    run_checker()          # ③ 让证据文件回到未变异状态
    print("\n还原：sha256 %s → %s ｜ %s" % (before[:16], after[:16],
          "✅ 逐字节一致" if before == after else "❌ **不一致，必须人工处理**"))
    if before != after:
        return 3
    print("变异自证：%d 通过 / %d 失败" % (passed, failed))
    print("※ 源文件已还原；判据 %s 在基线上 PASS、在缺陷上精确变红。" % NEW_CHECK)
    return 0 if failed == 0 else 3


if __name__ == "__main__":
    raise SystemExit(main())
