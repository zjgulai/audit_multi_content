#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""sweep_desktop_xlsx_backups.py —— 桌面「任务详情」散落备份的**清扫闸门**。

## 为什么要有它（这不是洁癖，是三次复发后的处置）

`~/Desktop/内容治理知识库-历史版本/版本规矩.md`（Owner 自定，2026-10-10）逐字：

> **正本 = 桌面上的这两个文件，就地改，不另存新名字**
> **改之前**：把「当前状态」复制进**本文件夹**一份，命名 `<表名>_bak-<真实时间 YYYYMMDD-HHMM>.xlsx`
> **保留多少**：每张表**最多留最近 5 份**，更旧的删
> **不要做**：**不要为每次提问新建一个文件名**

实测复发**三次**：
· 2026-10-12 14:48 清掉 11 个（`-备份<ts>[-写前].xlsx`）；
· 同日 14:54–16:33 又长出 **8 个**，且后缀变成语义化的（`头部订正前`/`重建落地前`/`裁定前`…）；
· 成因是**并行会话逐个写一次性改表脚本**，每个脚本写前留一份备份 —— **没有人负责清**。

⇒ 「再删一次」治不了，因为**下一次编辑必然再长一个**。本件把「清扫」变成**可重复执行的判据**。

## ★ 安全闸（缺一不可，红了就不扫）

清扫是**移动文件**，动错了就是丢数据。所以扫之前必须先证明**正本最全**：
① 正本在；② 每个散落件的 (行数, G列字符数) **都不超过正本**。
任一不满足 ⇒ **拒扫**并列出可疑件（也许某个散落件才是最新的，那时该做的是**人工判断**，不是自动移走）。

## 去处

`~/.Trash/`（**移动，不是删除** —— 与 `版本规矩.md` 里「10/8 的两份在回收站，未动」同一口径）。
每扫一次记一行账：`kb/.work/desktop-xlsx-sweep.ndjson`。

## 用法

    python3 kb/l8/sweep_desktop_xlsx_backups.py             # 预演（零移动）
    python3 kb/l8/sweep_desktop_xlsx_backups.py --apply
    python3 kb/l8/sweep_desktop_xlsx_backups.py --selftest
"""
from __future__ import annotations

import argparse
import glob
import io
import json
import os
import shutil
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
KB = os.path.dirname(HERE)
ROOT = os.path.dirname(KB)
DESK = os.path.expanduser("~/Desktop")
TRASH = os.path.expanduser("~/.Trash")
LEDGER = os.path.join(KB, ".work/desktop-xlsx-sweep.ndjson")
MASTER = "内容治理知识库搭建任务详情.xlsx"
PATTERN = "内容治理知识库搭建任务详情-*.xlsx"     # 正本**不匹配**本模式（没有 `-`）


def _shape(path):
    """(行数, G列字符数)。读不了 ⇒ None（**读不了就不许扫** —— 见安全闸）。"""
    try:
        import openpyxl
        wb = openpyxl.load_workbook(path, read_only=True)
        ws = wb[wb.sheetnames[0]]
        rows = ws.max_row or 0
        g = 0
        for r in ws.iter_rows(min_col=7, max_col=7, values_only=True):
            g += len(str(r[0])) if r and r[0] is not None else 0
        wb.close()
        return rows, g
    except Exception:                                        # noqa: BLE001
        return None


def judge(master_path, strays):
    """纯函数：给正本与散落件 ⇒ (可否清扫, 原因, 明细)。**判据只有一条：正本必须最全。**"""
    if not os.path.exists(master_path):
        return False, "**正本不在**（%s）⇒ 拒扫：不知道拿什么当基准" % os.path.basename(master_path), []
    m = _shape(master_path)
    if m is None:
        return False, "**正本读不了** ⇒ 拒扫（读不了就不许动文件）", []
    detail, suspicious = [], []
    for p in strays:
        s = _shape(p)
        if s is None:
            suspicious.append(os.path.basename(p))
            detail.append({"file": os.path.basename(p), "shape": None, "over": None})
            continue
        over = (s[0] > m[0]) or (s[1] > m[1])
        if over:
            suspicious.append(os.path.basename(p))
        detail.append({"file": os.path.basename(p), "rows": s[0], "gchars": s[1], "over": over})
    if suspicious:
        return False, ("**有 %d 个散落件比正本更全（或读不了）⇒ 拒扫** —— "
                       "那时该做的是人工判断哪个才是最新的，**不是自动移走**：%s"
                       % (len(suspicious), suspicious)), detail
    return True, "正本最全（行 %d ｜ G列 %d 字符）⇒ 可扫" % (m[0], m[1]), detail


def scan(desk=DESK, master=MASTER):
    return sorted(glob.glob(os.path.join(desk, PATTERN)))


def run(apply_now=False, desk=DESK, master=MASTER, trash=TRASH, ledger=LEDGER):
    mp = os.path.join(desk, master)
    strays = scan(desk, master)
    print("桌面「任务详情」散落备份清扫 —— 依据 `版本规矩.md`（备份进归档位、每表≤5 份）\n")
    print("正本：%s" % master)
    print("散落件：**%d 个**" % len(strays))
    for p in strays:
        print("   · %s" % os.path.basename(p))
    if not strays:
        print("\n✅ 没有散落件（幂等）—— 无需动作")
        return 0
    ok, why, detail = judge(mp, strays)
    print("\n安全闸：%s" % why)
    if not ok:
        print("⛔ **拒扫** —— 一个文件都没动。")
        return 3
    if not apply_now:
        print("\n预演（零移动）。要真扫加 --apply —— 去处 `~/.Trash/`（可恢复）。")
        return 0
    os.makedirs(trash, exist_ok=True)
    moved = []
    for p in strays:
        dst = os.path.join(trash, os.path.basename(p))
        if os.path.exists(dst):
            dst = dst + ".swept-" + time.strftime("%H%M%S")
        shutil.move(p, dst)
        moved.append(os.path.basename(p))
    rec = {"at": time.strftime("%Y-%m-%d %H:%M:%S"), "what": "desktop task-xlsx stray backups swept",
           "moved_to": "~/.Trash", "count": len(moved), "files": moved, "judge": why,
           "authority": "版本规矩.md（备份进归档位、不另存新名字）"}
    # ★★ 自证**不许污染生产留痕**（我这一版栽过）：`--selftest` 在临时夹具上跑真逻辑，
    #   若共用同一个账本文件，夹具记录会混进真账 —— 实测账本里出现两条
    #   「移走 2 个（1526-写前、1633-裁定前）」，那是 selftest 的**夹具文件名**，不是真事。
    #   ⇒ 账本落点由调用方给：真跑用真账，自证用临时账（下面 selftest 传 tempfile）。
    if ledger:
        os.makedirs(os.path.dirname(ledger), exist_ok=True)
        with io.open(ledger, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print("\n✅ 已移入回收站 **%d 个**（可恢复）｜ 账：%s"
          % (len(moved), os.path.relpath(ledger, ROOT) if ledger else "（自证：不写生产账本）"))
    return 0


def selftest():
    import tempfile
    import openpyxl
    res = []

    def ck(n, c, ex=""):
        res.append((n, bool(c), ex))

    def mk(path, gchars):
        wb = openpyxl.Workbook(); ws = wb.active
        ws.cell(1, 1, "日期"); ws.cell(2, 7, "x" * gchars)
        wb.save(path)

    d = tempfile.mkdtemp(prefix="sweep-")
    m = os.path.join(d, MASTER)
    a = os.path.join(d, "内容治理知识库搭建任务详情-备份20261012-1633-裁定前.xlsx")
    b = os.path.join(d, "内容治理知识库搭建任务详情-备份20261012-1526-写前.xlsx")
    mk(m, 500); mk(a, 100); mk(b, 200)
    st = scan(d, MASTER)
    ck("① 模式只抓散落件、**不抓正本**", len(st) == 2 and all("备份" in os.path.basename(x) for x in st),
       "抓到 %d 个" % len(st))
    ok, why, _ = judge(m, st)
    ck("② 正例：散落件都比正本小 ⇒ 可扫", ok, why[:60])
    # ★ 反向对照：**有一个比正本更全 ⇒ 必须拒扫**（否则把最新数据扫走）
    mk(a, 900)
    ok2, why2, det = judge(m, scan(d, MASTER))
    ck("③ 反向对照：有一个比正本更全 ⇒ **拒扫**", (not ok2) and "更全" in why2, why2[:70])
    mk(a, 100)
    # ★ 反向对照：**正本不在 ⇒ 拒扫**
    m2 = os.path.join(d, "没有正本.xlsx")
    ok3, why3, _ = judge(m2, scan(d, MASTER))
    ck("④ 反向对照：正本不在 ⇒ 拒扫", (not ok3) and "正本不在" in why3, why3[:50])
    # ★ 反向对照：**读不了 ⇒ 拒扫**（不许把读不了的当"小件"扫掉）
    bad = os.path.join(d, "内容治理知识库搭建任务详情-坏件.xlsx")
    io.open(bad, "w", encoding="utf-8").write("not an xlsx")
    ok4, why4, _ = judge(m, scan(d, MASTER))
    ck("⑤ 反向对照：散落件读不了 ⇒ 拒扫", (not ok4) and "更全" in why4, why4[:70])
    os.remove(bad)
    # ⑥ 真扫：移到 temp 回收站 + 幂等
    t = os.path.join(d, "trash"); os.makedirs(t, exist_ok=True)
    n_before = len(scan(d, MASTER))
    run(True, desk=d, master=MASTER, trash=t, ledger=os.path.join(d, "led.ndjson"))
    n_after = len(scan(d, MASTER))
    ck("⑥ 真扫：散落件清零、正本还在", n_after == 0 and os.path.exists(m) and n_before == 2,
       "扫前 %d → 扫后 %d" % (n_before, n_after))
    ck("⑦ 幂等：再扫 0 个，退出 0", run(True, desk=d, master=MASTER, trash=t, ledger=os.path.join(d, "led.ndjson")) == 0, "")
    ck("⑧ 移的是**副本**不是删除：回收站里确有文件", len(os.listdir(t)) == 2,
       "回收站 %d 个" % len(os.listdir(t)))
    shutil.rmtree(d, ignore_errors=True)
    print("sweep_desktop_xlsx_backups --selftest")
    for n, c, ex in res:
        print("  %s %s%s" % ("✅" if c else "❌", n, ("　｜ " + str(ex)) if ex else ""))
    bad_n = sum(1 for _, c, _e in res if not c)
    print("结果：%d/%d%s" % (len(res) - bad_n, len(res), "" if not bad_n else "  ← 有失败"))
    return 1 if bad_n else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    sys.exit(selftest() if a.selftest else run(a.apply))
