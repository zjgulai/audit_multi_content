#!/usr/bin/env python3
"""② 抽 10 条做小样本验证：备份账本 → 存改前快照 → 清 `answered_at`。

## 为什么这么选这 10 条

判据是「**能不能验到题材闸门**」，不是「随便抽 10 条」。所以覆盖三件事：

  ① **两个已知误引**（必须包含）—— `MC-US-YT-9-vZmvgIrRA`（清洗机视频）与
     `MC-US-YT-iAVRpPXgAeU`（婴儿监控器视频）的报告里都引了
     「【品牌一致性】视频 ③ 场景要体现真实日常清洁，但水槽、奶瓶、配件不要堆得过满」，
     而那条条款的原件是**图片·展会海报**，与这两条**题材不符** ⇒ 这正是题材闸门要挡的。
  ② **三种三态都盖到**（BLOCK 2 / NEEDS_INPUT 4 / REVIEW 4）—— 闸门只影响 case 条款那一档，
     三态都得看一眼有没有被带偏。
  ③ **三种模态、三个渠道都盖到**（视频 4 / 文案 5 / 图片 1；官网 5 / YouTube 4 / Amazon 1）。

用法：
  python3 采集-20261013/pick10.py            # 预演
  python3 采集-20261013/pick10.py --apply    # 备份 + 存快照 + 清 answered_at
"""
import argparse, datetime, json, os, shutil, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
OUT = os.path.join(HERE, "out")
LEDGER = "/Users/lute/Project/audit_multi_content/PMO/shouheng-state/batch-review.json"

# 10 条：改前状态取自表（`parse_table80.py` 的解析结果）
PICK = [
    ("MC-US-YT-9-vZmvgIrRA",                "清洗机",   "YouTube", "视频", "REVIEW",      "已知误引奶瓶条款 #1"),
    ("MC-US-YT-iAVRpPXgAeU",                "婴儿监控器", "YouTube", "视频", "REVIEW",      "已知误引奶瓶条款 #2"),
    ("MC-US-YT-cFMhzoIYjI0",                "吸奶器",   "YouTube", "视频", "BLOCK",       "真 BLOCK（唯一？）"),
    ("MC-US-WEB-COL-baby-monitor-black-friday", "婴儿监控器", "官网", "文案", "BLOCK",    "BLOCK＋依据写「未给条款号」"),
    ("MC-US-WEB-COL-electric-breast-pump",  "吸奶器",   "官网",    "文案", "NEEDS_INPUT", "覆盖缺口"),
    ("MC-US-WEB-COL-hospital-grade-breast-pump", "吸奶器", "官网",  "文案", "NEEDS_INPUT", "覆盖缺口"),
    ("MC-US-AMZ-B0FHQJWPTN",                "吸奶器",   "Amazon",  "文案", "NEEDS_INPUT", "覆盖缺口"),
    ("MC-US-YT-88uvcSNxMdk",                "吸奶器",   "YouTube", "视频", "NEEDS_INPUT", "覆盖缺口"),
    ("MC-US-WEB-COL-baby-bottle-sterilizers", "清洗机", "官网",    "文案", "REVIEW",       "对照：真·奶瓶题材"),
    ("MC-US-WEB-IMG-8855218782406",         "清洗机",   "官网",    "图片", "REVIEW",       "图片模态"),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    st = json.load(open(LEDGER, encoding="utf-8"))
    items = st["items"]
    ids = [p[0] for p in PICK]

    missing = [i for i in ids if i not in items]
    if missing:
        print("账本里找不到:", missing); sys.exit(3)
    already = [i for i in ids if not items[i].get("answered_at")]
    print(f"10 条都在账本里 ｜ 其中已经是「未答」状态的: {len(already)} {already}")

    for i, (cid, pl, ch, mod, state, why) in enumerate(PICK, 1):
        cur = items[cid]
        ok = (cur.get("state") == state)
        print(f"  {i:2d}. {cid:<42} {pl:<6}{ch:<8}{mod:<4} 三态={str(cur.get('state') or '—'):<12}"
              f" 报告={str(cur.get('report_url') or '—')[-12:]}  {why}"
              + ("" if ok else f"  ⚠ 表里记的是 {state}"))

    if not a.apply:
        print("\n（预演。加 --apply 才动账本。）")
        return

    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    bk = os.path.join(HERE, f"backup_ledger_{ts}")
    os.makedirs(bk)
    shutil.copy2(LEDGER, os.path.join(bk, "batch-review.json"))
    print("\n已备份账本 ->", os.path.relpath(bk, ROOT))

    before = {cid: items[cid] for cid in ids}
    json.dump(before, open(os.path.join(OUT, "before_10.json"), "w"),
              ensure_ascii=False, indent=1)
    print("改前快照 -> out/before_10.json")
    for cid, _, _, _, _, _ in PICK:
        print(f"   {cid:<42} {str(before[cid].get('state') or '—'):<12} 问题数={before[cid].get('issue_total')} "
              f"{str(before[cid].get('report_url') or '')[-12:]}")

    for cid in ids:
        items[cid]["answered_at"] = False
        items[cid]["requeued_at"] = datetime.datetime.now().isoformat(timespec="seconds")
        items[cid]["requeue_reason"] = "② 小样本验证：库侧已修（销 86 重复号 ＋ 题材闸门上线）后复跑"
    tmp = LEDGER + ".swtmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, indent=1)
    os.replace(tmp, LEDGER)
    print(f"\n已清 answered_at：{len(ids)} 条（其余 {len(items)-len(ids)} 条不动）")


if __name__ == "__main__":
    main()
