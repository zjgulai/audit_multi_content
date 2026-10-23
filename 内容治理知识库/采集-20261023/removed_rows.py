#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""**已声明移除的组合** —— 「这批行是被有意删掉的，不是意外缺失」。

## 为什么要有这个概念

2026-10-23 Owner 决定：把 `采集数据` 只有 `【说明】` 备注、**没有真实素材**的 24 行删掉
（表 135 → 111）。删完之后，一堆判据会**永久变红**，因为它们的前提是「9 × 5 × 3 = 135 全覆盖」：

- `verify_rows.py` 的 A（组合齐）/ 行数 / H（各平台 45 行）会报「期望 N 行、实际 0 行」；
- `build_collect_rows.py` 会报「表里没有这一行」；
- `fix_cells.py` 直接 KeyError（它按 `idx[key]` 取当前值）。

**逐个脚本各改一遍是错的**（本会话已经因为「同一件事两处实现」栽过 4 次）。
所以：**删哪些、为什么删** 落在声明文件 `removed_combos_20261023.json` 里，
所有脚本统一 `import removed_rows` 来认它。

## 纪律

- 声明文件是**唯一真源**：判据认它，但不许它变成「万能豁免」——
  `verify_rows.py` 仍然校验 `本批行数 == 期望行数 - 声明移除数`，
  且**声明为移除却还在表里**会精确变红（`--controls-removed-ghost` 就是这条的反向对照）。
- 删行**不可逆**（Bitable 没有撤销），所以删除脚本先把每行的完整字段快照写盘再动手。
"""
import json
import os

DECL = "removed_combos_20261023.json"

#: 组合键的列（与 verify_rows.KEY 对齐；顺序也一致）
KEY_COLS = ("产品线", "产品中文名", "内容类型", "渠道")


def load(path=DECL):
    """返回声明内容；文件不存在 ⇒ 空声明（向后兼容，老脚本照跑）。"""
    if not os.path.exists(path):
        return {"removed": [], "count": 0}
    return json.load(open(path, encoding="utf-8"))


def keys(path=DECL):
    """{(产品线, 产品中文名, 内容类型, 渠道)} —— 判据据此把这些组合当「已声明移除」。"""
    return {tuple(r["fields"].get(c) for c in KEY_COLS) for r in load(path)["removed"]}


def keys_3(path=DECL):
    """{(渠道, 产品中文名, 内容类型)} —— **写入类脚本**用的形状（build / fix 的键）。
    ⚠️ 2026-10-23 踩过：声明是 4 元组（含产品线），而 build/fix 的键是 3 元组且**顺序也不同**
    （渠道在前），直接比永远不等 ⇒ 跳过判定一次都没生效（实测 build 报 9 处「表里没有这一行」、
    fix 直接 KeyError）。换算只放这里，别在每个脚本里各拼一遍。
    """
    return {(r["fields"].get("渠道"), r["fields"].get("产品中文名"), r["fields"].get("内容类型"))
            for r in load(path)["removed"]}


def pairs_3(path=DECL):
    """{(产品中文名, 内容类型, 渠道)} —— **判据 C** 用的形状（它按 产品×平台 分组）。"""
    return {(r["fields"].get("产品中文名"), r["fields"].get("内容类型"), r["fields"].get("渠道"))
            for r in load(path)["removed"]}


def rids(path=DECL):
    """{record_id} —— 用于「声明移除却还在表里」的检查。"""
    return {r["record_id"] for r in load(path)["removed"]}


def summary(path=DECL):
    d = load(path)
    by_chan = {}
    for r in d["removed"]:
        c = r["fields"].get("渠道")
        by_chan[c] = by_chan.get(c, 0) + 1
    return len(d["removed"]), by_chan


if __name__ == "__main__":
    n, by = summary()
    print(f"已声明移除 {n} 个组合" + (f"：{by}" if by else ""))