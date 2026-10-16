#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""l3_status.py —— L3（规则蒸馏层）的**只读状态查询档**。

## 补的是哪个洞（2026-10-01）

`kb-clause-extractor` 是 L3 的层 skill，但它**只有写档** ——
入口是 `l3_distill_run.py <RUN>`、`l3_reject_ledger_rebuild.py <RUN> [--apply]`，
没有只读入口。查「抽了多少条 / 拒了多少条 / 对得上吗」时无档可调。本脚本就是那个入口。

## 它会报一处**已知的口径不一致**（不替人抹平）

实测（2026-10-01）：

    kb/l3/candidates/rules.jsonl       1018 行
    kb/l3/index/l3.jsonl                509 行
    l3/registry/l3.json → convergence   keep=509 / move=1018 / same_id_set=true

`rules.jsonl` 已长到 1018 行，而 `index/l3.jsonl` 仍是 509 行、`accounting.kept` 也是 3540。
本脚本**照实把三个数并排打出来**，并标 `counts_disagree=true` ——
哪个是权威口径是**人的判断**，不由查询档替人决定（同 `l2_status` 不替人合并 status）。

## 只读

只读 `kb/l3/candidates/*.jsonl`、`kb/l3/rejected*.jsonl`、`kb/l3/index/l3.jsonl`、
`kb/l3/registry/l3.json`。**不写任何文件。**

## 退出码

    0 = 读成功（不代表"没问题"）
    2 = 用法错 / 库根不对 / 注册表读不到
"""

from __future__ import annotations

import argparse
import json
import os
import sys

CAND = {"wording 规则": os.path.join("kb", "l3", "candidates", "rules.jsonl"),
        "外部标准条款": os.path.join("kb", "l3", "candidates", "external_standard.jsonl")}
REJ = {"拒收（内部）": os.path.join("kb", "l3", "rejected.jsonl"),
       "拒收（外部标准）": os.path.join("kb", "l3", "rejected_external_standard.jsonl")}
INDEX = os.path.join("kb", "l3", "index", "l3.jsonl")
L3REG = os.path.join("kb", "l3", "registry", "l3.json")
ROOT_MARKER = os.path.join("kb", "KB-ROOT.json")


def check_root() -> None:
    if not os.path.isdir("kb"):
        sys.exit("l3_status: 没有 kb/ 目录。请把 cwd 设成 kb/ 的上一级（库根）。")
    if not os.path.exists(ROOT_MARKER):
        sys.exit("l3_status: 缺 %s —— 这里不是权威库根。" % ROOT_MARKER)


def count_lines(p):
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as f:
        return sum(1 for line in f if line.strip())


def main() -> int:
    ap = argparse.ArgumentParser(description="L3 只读状态查询档")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    check_root()

    if not os.path.exists(L3REG):
        print("l3_status: 注册表不存在：%s" % L3REG, file=sys.stderr)
        return 2

    cand = {k: count_lines(p) for k, p in CAND.items()}
    rej = {k: count_lines(p) for k, p in REJ.items()}
    index_n = count_lines(INDEX)

    reg = json.load(open(L3REG, encoding="utf-8"))
    conv = reg.get("convergence") or {}
    acct = reg.get("accounting") or {}

    rules_n = cand.get("wording 规则")
    counts_disagree = (
        rules_n is not None and index_n is not None and rules_n != index_n
    )

    print("L3 状态（只读查询档）｜注册表 %s" % L3REG)
    print("  候选规则文件：")
    for k, v in cand.items():
        print("    %-14s %s 行" % (k, v if v is not None else "缺失"))
    print("  索引 index/l3.jsonl: %s 行" % (index_n if index_n is not None else "缺失"))
    print("  拒收台账：")
    for k, v in rej.items():
        print("    %-14s %s 行" % (k, v if v is not None else "缺失"))
    if conv:
        print("  registry convergence: keep=%s ｜ move=%s ｜ same_id_set=%s" % (
            conv.get("unique_rule_ids"), conv.get("move"), conv.get("same_id_set")))
        print("    l4_assignments=%s ｜ keep_equals_l4=%s" % (
            conv.get("l4_assignments"), conv.get("keep_equals_l4")))
    if acct:
        print("  registry accounting: l2_total=%s ｜ kept=%s ｜ used_in_rules=%s ｜ "
              "explicitly_rejected=%s ｜ unaccounted=%s" % (
                  acct.get("l2_total"), acct.get("kept"), acct.get("used_in_rules"),
                  acct.get("explicitly_rejected"), acct.get("unaccounted")))
    if counts_disagree:
        print("  ⚠️ 口径不一致：candidates/rules.jsonl=%s 行，但 index/l3.jsonl=%s 行、"
              "convergence.keep=%s —— 哪个是权威口径需**人裁**，查询档不替人决定。"
              % (rules_n, index_n, conv.get("unique_rule_ids")))
        print("     （对照：l7/registry/l7.json → article_no_source 记 09-30 已从 509 变 632）")

    if a.json:
        print(json.dumps({
            "layer": "L3",
            "candidates": cand,
            "index_lines": index_n,
            "rejected": rej,
            "convergence": conv,
            "accounting": acct,
            "counts_disagree": counts_disagree,
        }, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
