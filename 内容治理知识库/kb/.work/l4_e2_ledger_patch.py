#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""L4 台账补 E-2 段：把已经发出去、但没进唯一台账的 123 个 E-2 号补登记。

## 为什么需要它（2026-10-01 实测）

三份记录互相打架，实测四方对账：

| 来源 | 说 E-2 是什么 |
|---|---|
| `kb/l4/registry/l4.json → numbering.block_by_library` | `reserved_unused`（预留、**不预发不占位**） |
| `kb/l4/registry/l4.json → numbering.issued` | **没有 E-2 段** |
| `kb/l4/runs/20260930-1740.json → totals.segments_used` | **含 E-2** |
| `kb/l3/candidates/external_standard.jsonl`（数据） | **123 条，E-2.1 ~ E-2.123** |

时间线：`l4_article.py --apply` 在 **09-30 17:31** 给该文件写入 E-2 号；
`l4_ledger_repair.py` 在 **17:21** 用事故前归档复原 —— **E-2 晚于它的事实源，结构上补不到**。

**后果（不是评审链）**：`numbering.no_reuse` 写着「号码一经发出永久占用，不回收、不重发」。
E-2 的号不在唯一台账里 → **后续批次可能把同一个号发给另一条规则**。
这与 09-30 那次「733 个号从台账消失」是**同一类缺陷**，只是这次漏了 E-2。

## 为什么这不是「新发号」而是「补登记」

`block_by_library` **已经登记了 `E-2 / form=clause`** —— 方案早已承认该形态存在，
只是 `state` 仍写着 `reserved_unused`。本脚本改的是**它的状态**，不是发明一个段。

## 红线（照 `l4_ledger_repair.py`，一条不改）

- **只补缺、不改已发号**：live 里已有的号码一个不动；同 id 不同号 = 冲突 → 拒绝落盘交人裁决。
- **先验证后落盘**：与 live 已发集合逐个对账不通过就退出，不写任何字节。
- **幂等**：没有缺项时零写入（连 mtime 都不动）。
- **原子写**：tmp → json.load 验 → os.replace。
- 只写 `kb/l4/registry/l4.json` 与 `kb/l4/runs/<RUN>-e2-ledger-patch.json`；
  `kb/l0~l3`、`kb/l5~l7` 与 canonical **全程只读**。

用法：
    kb/kbpy .work/l4_e2_ledger_patch.py <RUN>              # 干跑（默认）
    kb/kbpy .work/l4_e2_ledger_patch.py <RUN> --apply      # 落盘
"""
import collections
import glob
import json
import os
import sys
import time

APPLY = "--apply" in sys.argv
if APPLY:
    sys.argv.remove("--apply")
RUN = sys.argv[1] if len(sys.argv) > 1 else time.strftime("%Y%m%d-%H%M")
REG = "kb/l4/registry/l4.json"
SRC = "kb/l3/candidates/external_standard.jsonl"
RUNS = "kb/l4/runs"
SEG = "E-2"
t0 = time.time()

if not APPLY:
    print("[dry-run] %s 未落盘。" % os.path.basename(os.path.abspath(__file__)))
    print("[dry-run] 本脚本会写入：kb/l4/registry/l4.json（补 %s 段登记与已发号）、"
          "kb/l4/runs/%s-e2-ledger-patch.json" % (SEG, RUN))
    print("[dry-run] 加 --apply 才落盘。只补缺、不改已发号；对账不过则拒绝写。")


def save_atomic(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=1)
    json.load(open(tmp, encoding="utf-8"))          # 先验后换（本层事故教训）
    os.replace(tmp, path)


# ---------------- 一、读事实 ----------------
live = json.load(open(REG, encoding="utf-8"))
live_issued = live["numbering"].get("issued", {})
live_assign = live.get("assignments", {}) or {}
live_an = {}
for _s, _i in live_issued.items():
    live_an.update(_i.get("assigned") or {})

# 事实源：数据文件里**确实带号**的行（不猜、不外推）
src_rows, per_seg = [], collections.Counter()
for line in open(SRC, encoding="utf-8"):
    line = line.strip()
    if not line:
        continue
    r = json.loads(line)
    a = str(r.get("article_no") or "")
    if a.startswith(SEG + "."):
        src_rows.append((r["rule_id"], a))
        per_seg[a.split(".")[0]] += 1
src_an = dict(src_rows)

print("现库台账 run_id=%s ｜ issued 段 %s ｜ 已发号 %d 个"
      % (live.get("run_id"), sorted(live_issued), len(live_an)))
print("事实源 %s ｜ %s 带号 %d 条 ｜ 段 %s"
      % (SRC, SEG, len(src_an), dict(per_seg)))

if not src_an:
    print("\n事实源里没有 %s 带号行 → 无事可做，零写入。" % SEG)
    sys.exit(0)

# ---------------- 二、对账（先验证，后落盘）----------------
nums = sorted(int(v.split(".")[1]) for v in src_an.values())
seq_ok = nums == list(range(1, len(nums) + 1))
conflict = {k: (live_an[k], src_an[k]) for k in live_an if k in src_an and live_an[k] != src_an[k]}
dup_no = set(src_an.values()) & set(live_an.values())
print("\n对账：")
print("  序号连续 1..%d ：%s" % (len(nums), seq_ok))
print("  与 live 已发号同 id 不同号（冲突）：%d 条" % len(conflict))
print("  号与本库其他段重复：%d 个" % len(dup_no))
if not seq_ok:
    print("★序号不连续 → 拒绝落盘（数据本身可疑，交人裁决）")
    sys.exit(3)
if conflict:
    print("★已发号冲突 → 拒绝落盘（交人裁决）")
    for k, v in list(conflict.items())[:10]:
        print("   ", k, "live=", v[0], "src=", v[1])
    sys.exit(4)
if dup_no:
    print("★号码跨段重复 → 拒绝落盘（交人裁决）：%s" % sorted(dup_no)[:10])
    sys.exit(5)

# ---------------- 三、算差异（只补缺）----------------
add_assign = {k: v for k, v in src_an.items() if k not in live_an}
already = len(src_an) - len(add_assign)
blk = live["numbering"].get("block_by_library", {}).get("external_standard", {}).get(SEG)
seg_missing = SEG not in live_issued
blk_state = (blk or {}).get("state")
print("\n缺的段登记：%s" % (SEG if seg_missing else "无（已在 issued 里）"))
print("  block_by_library[%s].state = %r（将改为 issued）" % (SEG, blk_state))
print("缺的逐号登记：%d 条（已在册 %d 条）" % (len(add_assign), already))

changed = bool(seg_missing or add_assign or (blk_state and blk_state != "issued"))
if not changed:
    print("\n台账已完整：无缺项 → 零写入（连 mtime 都不动）")
    sys.exit(0)

if not APPLY:
    print("\n[dry-run] 以上是差异，未落盘。加 --apply 才写 %s。" % REG)
    sys.exit(0)

# ---------------- 四、落盘（live 优先，绝不改已发号）----------------
_before = {"segments": sorted(live_issued), "assigned": len(live_an)}
if seg_missing:
    live["numbering"]["issued"][SEG] = {
        "library": "external_standard",
        "library_label": "1_外部标准库",
        "block": 2,
        "form": (blk or {}).get("form") or "clause",
        "block_label": "clause（法条型）",
        "change": "assign_article_no",
        "assigned": dict(src_an),
        "count": len(src_an),
        "range": ["%s.%d" % (SEG, nums[0]), "%s.%d" % (SEG, nums[-1])],
        "next_seq": nums[-1] + 1,
        "assigned_at_run": "20260930-1740",
        "newly_assigned": 0,
        "reused_from_ledger": len(src_an),
        "note": ("2026-10-01 补登记：号由 l4_article.py --apply（run 20260930-1740，17:31）发出，"
                 "但未写回本台账；事实源 = %s 的带号行，非新发号。" % SRC),
        "patched_by": "l4_e2_ledger_patch.py",
        "patched_at_run": RUN,
    }
if blk_state and blk_state != "issued":
    blk["state"] = "issued"
    blk["state_patched_at_run"] = RUN
live["assignments"] = {**src_an, **live_assign}          # live 优先，绝不改已发号
live["numbering"]["e2_ledger_patch"] = {
    "run": RUN, "segment": SEG, "added": len(add_assign),
    "already": already, "source": SRC, "before": _before,
}
save_atomic(REG, live)

os.makedirs(RUNS, exist_ok=True)
rec = {"run_id": RUN, "layer": "L4", "action": "e2_ledger_patch", "changed": True,
       "segment": SEG, "added_assignments": len(add_assign), "already_present": already,
       "source": SRC, "before": _before,
       "after": {"segments": sorted(live["numbering"]["issued"]),
                 "assigned": len(live.get("assignments", {}))},
       "conflict": 0, "elapsed_s": round(time.time() - t0, 1)}
with open(os.path.join(RUNS, "%s-e2-ledger-patch.json" % RUN), "w", encoding="utf-8") as fh:
    json.dump(rec, fh, ensure_ascii=False, indent=1)
print("\n✅ 已落盘：补 %s 段 %d 号 ｜ issued 段 %s ｜ 已发号 %d"
      % (SEG, len(add_assign), sorted(live["numbering"]["issued"]),
         len(live.get("assignments", {}))))
