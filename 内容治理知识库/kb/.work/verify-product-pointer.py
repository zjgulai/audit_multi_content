#!/usr/bin/env python3
"""独立验收：产品库条目里的「判据层对应规则」指引，是不是真的指对了。

为什么单独一个脚本（照 batch3_verify.py 的规矩）：**验收证据必须独立于生成产物的脚本**。
这里不 import 生成器、不调 judgment_pointer()，而是拿生成好的条目 + 原始源
（l3/candidates/rules.jsonl + 表格缓存）**从两头各算一遍再对**。生成器里那套连接逻辑
自己写错了，这个脚本照样能照出来。

逐条检查（任一不满足 → 退出码 1）：
  ① 指引里写的 rule_id 在判据层**存在**
  ② 指引里写的条款号与该规则的 article_no **一致**
  ③ 指引里写的 P 级/等级与该规则的 p_level·risk_level **一致**
  ④ 条目的「状态」与该规则的 risk_level **等级一致**（红色↔P0、黄色↔P1、绿色↔P2）
  ⑤ 条目的「建议表达」归一化后与规则的 suggested_replacement **同一句话**

用法：python3 kb/.work/verify-product-pointer.py
"""
from __future__ import annotations

import json
import os
import re
import sys

WORK = os.path.dirname(os.path.abspath(__file__))
KB = os.path.dirname(WORK)
RULES = os.path.join(KB, "l3", "candidates", "rules.jsonl")
SHEET = os.path.join(WORK, "sources", "w1-evidence.json")
HOSTLIB = os.path.join(WORK, "hostlib", "4_产品描述库")

POINTER = re.compile(r"\*\*判据层对应规则\*\*：([^（(]+)[（(]([^）)]*)[）)]\s*·\s*rule_id\s*`([^`]+)`")


def norm(text: str) -> str:
    s = (text or "").strip()
    s = re.sub(r"^[（(]禁用[）)]\s*", "", s)
    return s.rstrip("。；; ").strip()


def field(body: str, name: str) -> str:
    m = re.search(rf"\*\*{name}\*\*：([^\n]*)", body)
    return m.group(1).strip() if m else ""


def main() -> int:
    if not os.path.isdir(HOSTLIB):
        print(f"❌ 找不到生成结果：{HOSTLIB}")
        return 1
    rules = {}
    for line in open(RULES, encoding="utf-8"):
        if line.strip():
            r = json.loads(line)
            if r.get("rule_id"):
                rules[r["rule_id"]] = r
    print(f"判据层规则 {len(rules)} 条（按 rule_id 索引）")

    checked = 0
    bad: list[str] = []
    md_files: list[str] = []
    for dirpath, _dirs, files in os.walk(HOSTLIB):   # 条目在 L1-facts/ L2-concepts/ 子目录里，必须递归
        md_files.extend(os.path.join(dirpath, f) for f in files if f.endswith(".md"))
    md_files.sort()
    if not md_files:
        print(f"❌ 一个 .md 都没找到（{HOSTLIB}）—— 检查不了就不许报通过")
        return 1
    for path in md_files:
        name = os.path.relpath(path, HOSTLIB)
        body = open(path, encoding="utf-8").read()
        m = POINTER.search(body)
        if not m:
            continue
        checked += 1
        article, level_text, rule_id = m.group(1).strip(), m.group(2).strip(), m.group(3).strip()
        rule = rules.get(rule_id)
        if rule is None:
            bad.append(f"{name}: 指引里的 rule_id `{rule_id}` 在判据层**不存在**")
            continue
        if (rule.get("article_no") or "") != article:
            bad.append(f"{name}: 条款号对不上 —— 指引写 {article}，规则自己是 {rule.get('article_no')}")
        expect_level = "·".join(x for x in [rule.get("p_level") or "", (rule.get("risk_level") or "").strip()] if x)
        if level_text != expect_level:
            bad.append(f"{name}: 等级对不上 —— 指引写「{level_text}」，规则是「{expect_level}」")
        status = field(body, "状态")
        risk = (rule.get("risk_level") or "").strip()
        if status and risk and status.replace("-", "") not in risk.replace("-", ""):
            bad.append(f"{name}: 条目状态「{status}」与规则等级「{risk}」不一致")
        if norm(field(body, "建议表达")) != norm(rule.get("suggested_replacement")):
            bad.append(f"{name}: 建议表达与规则的 suggested_replacement 不是同一句话")

    print(f"带指引的条目 {checked} 条")
    # 覆盖对账：表格里 02_表达边界 一共几行，其中几条接了指引
    if os.path.isfile(SHEET):
        cache = json.load(open(SHEET, encoding="utf-8"))
        rows = ((cache.get("sheets") or {}).get("02_表达边界") or {}).get("rows") or []
        print(f"对账：02_表达边界 共 {max(0, len(rows) - 1)} 行，带指引 {checked} 条"
              f"（差 {max(0, len(rows) - 1) - checked} 条 = 判据层没有对应规则，属正常，不是漏）")
    # 「一条都没检查」不是通过，是没查成 —— 这个脚本第一版就栽在这里：
    # 没递归子目录 → 0 条 → 却打印 ✅。验收脚本给出假通过，比不写更糟。
    if checked == 0:
        print("\n❌ 一条指引都没读到 —— 要么生成器没产出，要么本脚本找错了地方。"
              "**这不叫通过**，先查清楚再谈结论。")
        return 1
    if bad:
        print(f"\n❌ {len(bad)} 处不通过：")
        for item in bad:
            print("  ·", item)
        return 1
    print("\n✅ 全部通过：每条指引都指得对（规则存在、条款号/等级一致、语句同源）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
