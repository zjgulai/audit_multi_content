#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""l4_retire.py —— L4 条款**退役**（P3）：源下架时标记 retired，**绝不删号**。

## 为什么是"追加退役行"而不是"删掉那条"

`kb/l4/registry/l4.json` 的 `numbering.no_reuse` 写着：
**「号码一经发出永久占用，不回收、不重发」**。
更硬的理由是证据链：定稿层有 **632 条 evidence** 的 `anchor` 指向 L0-L3，
一旦删掉某条定稿，那些引用就**指空**，而且**事后无法解释**它为什么没了。

所以退役 = **另起一行**，把 `status` 从 `stable` 改成 `retired`，
并记下为什么退役。条款号保留、原文保留、可被继续引用（只是引用时要标注已退役）。

## 模式照抄现有实现（不自创）

`kb/.work/l4_article.py:398-419` 的追加口径：
    原行**逐字节不动**，另起一行，**只加差异字段**；
    已赋过同一状态的行 → `continue`（**重跑零写入**）。
本脚本沿用同一套：同一 `article_no` 已有一条 `status: retired` 的行 ⇒ 不再追加。

## 用法

    kb/kbpy l7/scripts/l4_retire.py --article-no W-1.8 --why "飞书侧源记录已下架（见墓碑 …）"
    kb/kbpy l7/scripts/l4_retire.py --article-no W-1.8 --why "…" --apply
    kb/kbpy l7/scripts/l4_retire.py --list-retired          # 看现有哪些退役

退出码：0 = 成功（含"已是退役态、无需追加"）｜ 2 = 参数/前置错｜ 3 = 找不到该条款号
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))       # …/kb/l7/scripts
KB = os.path.dirname(os.path.dirname(HERE))             # …/kb
CANON = os.path.join(KB, "l4", "canonical")
RUNS = os.path.join(KB, "l4", "runs")

#: 定稿有五个形态文件（见 kb/l4/registry/l4.json 的 form 计数）
FORMS = ("wording_entry", "wording_revision_pair", "sample_case",
         "scoped_clause", "clause")


def log(m: str) -> None:
    print("[l4-retire] %s" % m, flush=True)


def read_last_per_key(path: str, key: str = "article_no") -> dict:
    """按 `article_no` 取**最后一行**（与 kb_ledger.read_last_per_key 同口径）。

    下游若用"逐行读全部"会看到退役行与定稿行并存 —— 那是**设计的可见性**：
    退役是事实，不该被藏起来。判定「当前态」一律取最后一行的 status。
    """
    latest = {}
    if not os.path.exists(path):
        return latest
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            k = r.get(key)
            if k:
                latest[k] = r
    return latest


def find_article(art: str) -> tuple[str, dict] | tuple[None, None]:
    """在五个形态文件里找这条定稿；返回 (文件路径, 该号最后一行)。"""
    for form in FORMS:
        p = os.path.join(CANON, form + ".jsonl")
        if not os.path.exists(p):
            continue
        last = read_last_per_key(p).get(art)
        if last:
            return p, last
    return None, None


def list_retired() -> int:
    n = 0
    for form in FORMS:
        p = os.path.join(CANON, form + ".jsonl")
        if not os.path.exists(p):
            continue
        for k, r in read_last_per_key(p).items():
            if str(r.get("status")) == "retired":
                n += 1
                print("  %-10s %s ｜ %s" % (form, k, r.get("retired_reason") or ""))
    print("  退役合计：%d 条" % n)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="L4 条款退役（标记 retired，不删号）")
    ap.add_argument("--article-no", help="条款号，如 W-1.8")
    ap.add_argument("--why", default="", help="退役原因（必填，写进 retired_reason）")
    ap.add_argument("--tombstone", default="", help="关联的 L0 墓碑路径（可选，留证据链）")
    ap.add_argument("--apply", action="store_true", help="真正追加（默认干跑）")
    ap.add_argument("--list-retired", action="store_true", help="只列已退役的")
    a = ap.parse_args()

    if a.list_retired:
        return list_retired()
    if not a.article_no:
        log("❌ 必须给 --article-no（或用 --list-retired）")
        return 2
    if not a.why.strip():
        log("❌ 必须给 --why：退役原因要进证据链，不许空着")
        return 2

    path, cur = find_article(a.article_no)
    if path is None:
        log("❌ 找不到条款号 %s（五个形态文件都查过了）" % a.article_no)
        return 3

    if str(cur.get("status")) == "retired":
        log("✅ %s 已是退役态（%s）→ 重跑零写入"
            % (a.article_no, cur.get("retired_at") or "无时间戳"))
        return 0

    row = dict(cur)                       # 原行逐字节不动；这里只造**新行**
    row["status"] = "retired"
    row["retired_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    row["retired_reason"] = a.why.strip()
    row["retired_by"] = "l4_retire.py"
    row["numbering_note"] = "号码保留、不回收、不重发（numbering.no_reuse）"
    if a.tombstone:
        row["retired_tombstone"] = a.tombstone

    if not a.apply:
        log("[干跑] 将向 %s **追加**一行（原行不动）：" % os.path.relpath(path, KB))
        log("   article_no=%s status=stable → retired" % a.article_no)
        log("   retired_reason=%s" % row["retired_reason"])
        log("   加 --apply 才落盘")
        return 0

    os.makedirs(RUNS, exist_ok=True)
    rec_path = os.path.join(RUNS, "%s-l4-retire.json" % time.strftime("%Y%m%d-%H%M%S"))
    try:
        with open(path, "a", encoding="utf-8") as fh:      # ★ 追加，不覆盖
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        with open(rec_path, "w", encoding="utf-8") as fh:
            json.dump({"article_no": a.article_no, "why": row["retired_reason"],
                       "at": row["retired_at"], "file": os.path.relpath(path, KB)},
                      fh, ensure_ascii=False, indent=1)
    except Exception as e:                                  # noqa: BLE001
        log("❌ 追加失败：%s" % e)
        return 2

    back = read_last_per_key(path).get(a.article_no)
    ok = back and str(back.get("status")) == "retired"
    log("%s %s → retired ｜ 读回校验=%s ｜ 记录 %s"
        % ("✅" if ok else "❌", a.article_no, "通过" if ok else "**不通过**",
           os.path.relpath(rec_path, KB)))
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
