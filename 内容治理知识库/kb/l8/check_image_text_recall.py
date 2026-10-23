#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_image_text_recall.py —— 判据：**图上文字单独再查一次**真的能把同源单元捞上来（A/B 反向对照）。

## 治的是什么（2026-10-20 实测，MOMCOZY 图 1）

`layer_units` 原先只拿**整段素材文本**查一次 BM25。图片单的素材文本一半是 4 行英文 OCR、
一半是中文画面读数，而 BM25 的**中英两个子索引分数不可比**：
  · 整段查询：中文 rank1 = 368.095（无关长文档）｜英文里真正同源的那条 = 46.367
  · 按原始分混排 ⇒ 英文那路整体掉出 top5 ⇒ `rule_cited_unit_hits=0`
  · ⇒ 覆盖判据判 `coverage_not_covered` 拒答（`REVIEW 0`），**而库其实认识这张图**
    （`#负面样本/recvw7XIUgFaLV/具体原因/分析` 正被 L4 条款 **N-1.185** 取证）

修法（B）：把 `【图 N 内文字】…【/图 N】` 那段**单独再查一次**，与主查询**按排名融合（RRF）**。

## 本件判据（三正一反）

  C1 抽块：两种外壳（守衡 `【图 1 内文字｜4 行】`、引擎 `【图内文字（本机 OCR…）】`）都能抽出来
  C2 反向对照：`KB_IMG_TEXT_RECALL=off`（**整条新路径关掉、回到老口径**）⇒ top5 **不含**同源单元
  C3 正例：开启后 top5 **含**同源单元，且它的 `raw_bm25` ≥ 覆盖门限（16.0）
  C4 不伤纯文字单：无图块时，开关前后 top5 完全一致（不许顺手改别的素材的召回）

退出码：0 = 全过 ｜ 1 = 有红 ｜ 2 = 跑不起来（夹具/依赖缺失 ⇒ 未测，不当红也不当绿）
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))       # …/kb
KBROOT = os.path.dirname(ROOT)                                           # …（工作区根）
REVIEW = os.path.join(ROOT, "l7/skills/kb-content-review/scripts/review.py")
REG = os.path.join(ROOT, "l7/registry/l7.json")

#: 本单同源单元（被 L4 条款 N-1.185 取证）。硬写是为了让这条判据**钉住这次事故**。
TARGET = "#负面样本/recvw7XIUgFaLV/具体原因/分析"

#: 夹具：一次真实送审（`kb/l7/reports/20261020-165718.json` 的 input_manifest.text）
FIXTURE_REPORT = os.path.join(ROOT, "l7/reports/20261020-165718.json")

#: 纯文字单夹具（不许被这次改动影响）
TEXT_ONLY = "这条社媒文案能不能发：奶瓶不建议倒着放，我们家的奶瓶消毒器可以彻底杀菌。"


def _load_review():
    os.environ.setdefault("KB_ENTRY", "selftest")
    spec = importlib.util.spec_from_file_location("kb_review", REVIEW)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _material_text():
    if os.path.exists(FIXTURE_REPORT):
        d = json.load(open(FIXTURE_REPORT, encoding="utf-8"))
        t = ((d.get("input_manifest") or {}).get("text") or "")
        if "Evolving for" in t:
            return t, "真实送审（%s）" % os.path.basename(FIXTURE_REPORT)
    return ("【图 1 内文字｜4 行】\nMOMCOZY\nEvolving for\nmom and cozy\nM0m222\n【/图 1】\n"
            "【图 1 画面读数】场景：影棚 人物：无 物品：黑色婴儿背带；白色湿巾盒；绿色盖奶瓶\n",
            "内联夹具（报告件不在）")


def run(mod, reg, text, top=5):
    hits = mod.layer_units(text, reg, top=top)["top_bm25"]
    return [(h["anchor"], h["raw_bm25"]) for h in hits]


def main():
    rows = []
    if not os.path.exists(REVIEW) or not os.path.exists(REG):
        print("未测：缺 %s 或 %s" % (REVIEW, REG))
        return 2
    try:
        mod = _load_review()
        reg = json.load(open(REG, encoding="utf-8"))
        text, src = _material_text()
    except Exception as e:                                   # noqa: BLE001
        print("未测：装不起来（%s: %s）" % (type(e).__name__, e))
        return 2

    cov_thr = float(reg["retrieval"]["gate"].get("coverage_bm25_min", 16.0))

    # C1 抽块（两种外壳）
    b1 = mod.image_text_blocks("【图 1 内文字｜4 行】\nAAA\nBBB\n【/图 1】\n【图 1 画面读数】x")
    b2 = mod.image_text_blocks("【图内文字（本机 OCR，逐字，可能误识、也可能读不全）】\nCCC DDD\n\n【画面读数】y")
    ok1 = (b1 and "AAA" in b1[0]) and (b2 and "CCC DDD" in b2[0])
    rows.append(("C1 抽块：两种外壳都抽得出来", ok1, "守衡壳=%r 引擎壳=%r" % (b1[:1], b2[:1])))

    # C2 反向对照：关掉 ⇒ 同源单元不在 top5
    os.environ["KB_IMG_TEXT_RECALL"] = "off"
    off = run(mod, reg, text)
    off_has = any(a == TARGET for a, _ in off)
    rows.append(("C2 反向对照：KB_IMG_TEXT_RECALL=off ⇒ top5 不含同源单元",
                 not off_has, "off top5=%d 条；含目标=%s" % (len(off), off_has)))

    # C3 正例：开启 ⇒ 含同源单元且过覆盖门限
    os.environ.pop("KB_IMG_TEXT_RECALL", None)
    on = run(mod, reg, text)
    hit = [(a, s) for a, s in on if a == TARGET]
    ok3 = bool(hit) and hit[0][1] >= cov_thr
    rows.append(("C3 开启后 top5 含同源单元，且 raw_bm25 ≥ 覆盖门限 %.1f" % cov_thr,
                 ok3, "on top5=%s" % [(a[:34], s) for a, s in on][:5]))

    # C3b 读数（不判红）：只关「图上文字单独再查」、仍保留 RRF ⇒ 同源单元还捞得到吗
    os.environ["KB_IMG_TEXT_EXTRA"] = "off"
    rrf_only = run(mod, reg, text)
    os.environ.pop("KB_IMG_TEXT_EXTRA", None)
    rows.append(("C3b 读数：只关补查、仍用 RRF ⇒ 同源单元在 top5 %s"
                 % ("里（说明主修是 RRF）" if any(a == TARGET for a, _ in rrf_only) else "外（说明补查在做功）"),
                 True, "top5=%s" % [(a[:30], s) for a, s in rrf_only][:5]))

    # C4 纯文字单不受影响（开关前后一致）
    os.environ["KB_IMG_TEXT_RECALL"] = "off"
    t_off = run(mod, reg, TEXT_ONLY)
    os.environ.pop("KB_IMG_TEXT_RECALL", None)
    t_on = run(mod, reg, TEXT_ONLY)
    rows.append(("C4 纯文字单：开关前后 top5 一致（不顺手改别的素材的召回）",
                 t_off == t_on, "off=%d 条｜on=%d 条｜一致=%s" % (len(t_off), len(t_on), t_off == t_on)))

    print("=" * 78)
    print("check_image_text_recall —— 图上文字单独再查一次（A/B 反向对照）")
    print("  素材来源：%s" % src)
    print("-" * 78)
    bad = 0
    for name, ok, detail in rows:
        print("  %s %s" % ("✅" if ok else "❌", name))
        print("       %s" % detail)
        if not ok:
            bad += 1
    print("=" * 78)
    print("结论：%s（%d/%d）" % ("✅ 全过" if not bad else "❌ 红 %d" % bad,
                                len(rows) - bad, len(rows)))
    print("退出码：%d" % (0 if not bad else 1))
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
