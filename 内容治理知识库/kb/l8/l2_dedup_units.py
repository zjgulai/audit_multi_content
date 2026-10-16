#!/usr/bin/env python3
"""压缩 kb/l2/units.jsonl 里的**重复 unit_id 行**（同一条单元被写了两次）。

## 为什么会有重复（2026-09-30 查清）

`unit_id = sha1(splitter|resource_id|source_sha256|unit_type|anchor||order)[:20]`，
由内容派生，同一条单元重写一次就会得到同一个 id。2026-09-29 那批扫描件 OCR
向 L2 回灌时**同一批单元被写了两次**，于是 `Cliyw2MG…`（9 条）与 `AD26wCxzsi…`（12 条）
各有两份行，共 21 条重复（0 条是内容冲突：sha / anchor / text 全同，只有 meta 不同）。

后果不是"内容错"，而是**账目失真**：`usable_units()` 逐行过筛，
同一条单元被数两遍（FILTER 计数、单元总数都会虚高），
将来按 unit_id 做退役/审计也要照顾两份。

## 取舍：保留**最后一次写入**的那行

两份行的 meta 不同（一份是 `{field_name, kind}`，一份带
`content_quality_flag: pdf_ocr_vision`）。保留最后一行 = 保留当前信念，
且这一份带的正是 OCR 来源标记（真实出处），不做字段合并 ——
合并会造出一行从来没被写过的记录，那不是压缩，是编造。
丢掉的行不消失：整份原文件先归档。

## 安全（吃过 L3 的教训）

写盘前先归档原文件；写盘后断言行数守恒：`归档行数 - 重复行数 = 新行数`，
且 unit_id 集合只少掉重复的那些、不新增。

用法：
    python3 kb/l8/l2_dedup_units.py <RUN>            # 干跑
    python3 kb/l8/l2_dedup_units.py <RUN> --apply    # 归档 + 压缩
    python3 kb/l8/l2_dedup_units.py <RUN> --skip-conflicts --apply
        # ★ 2026-10-09 加：**真冲突的那些 unit_id 一行都不压**，其余照压；
        #   并把「还剩哪些没裁决」写成一份台账 kb/l2/duplicate_conflicts.jsonl。

## 为什么要有 `--skip-conflicts`（2026-10-09 实测）

默认政策是「保留每个 unit_id 的**最后一次写入**」，它默认两份行只是**双写**
（除了 `meta` 之外逐字段相同）。一旦有真冲突就整批拒绝 —— 这条**没有放松**。
但整批拒绝还有第二个后果：**能安全压的那 85 行也一起压不了**，
于是 L2 的账（与下游 L6 的索引）会一直挂着 85 条重复 unit_id。

实测那 7 对冲突里，**有 6 对是「晚写的那份反而更短」**：

    unit_id            资源                        早（完整）      晚（残缺）
    513d218b…          wiki 达人稿 nikkirose…      35,102 字       61 字（只剩 title）
    e0037e03…          wiki 达人稿 tseringla5      30,915 字       4,000（截断）
    …                  （共 6 对，`source_sha256` 与锚点都相同）

⇒ 对这 6 对，**默认政策正好会毁掉正文**（13.6 万字）。所以本脚本不替人做这个选择：
`--skip-conflicts` 把它们**整条冻住**（一行不删），逐对写进台账并给出**可复核的推荐**，
由人裁决后再走默认档。
"""
import collections
import json
import os
import shutil
import sys
import time

APPLY = "--apply" in sys.argv
SKIP_CONFLICTS = "--skip-conflicts" in sys.argv
RUN = next((a for a in sys.argv[1:] if not a.startswith("--")), time.strftime("%Y%m%d-%H%M"))
SRC = "kb/l2/units.jsonl"
ARCH = "kb/l2/_archive"
CONFLICT_LEDGER = "kb/l2/duplicate_conflicts.jsonl"


def load(p):
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]


rows = load(SRC)
cnt = collections.Counter(r["unit_id"] for r in rows)
dup_ids = {k for k, v in cnt.items() if v > 1}

# 保留每个 unit_id 的最后一次写入
last_at = {}
for i, r in enumerate(rows):
    last_at[r["unit_id"]] = i
keep = [r for i, r in enumerate(rows) if last_at[r["unit_id"]] == i]
dropped = len(rows) - len(keep)

# 冲突体检：重复的两份除了 meta 之外还有没有别的不同（有就是真冲突，不该默默压掉）
conflicts = []
by = collections.defaultdict(list)
for i, r in enumerate(rows):
    by[r["unit_id"]].append((i, r))
for uid in dup_ids:
    g = [r for _, r in by[uid]]
    keys = set().union(*[set(x) for x in g])
    diff = {k for k in keys if len({json.dumps(x.get(k), sort_keys=True, ensure_ascii=False) for x in g}) > 1}
    if diff - {"meta"}:
        conflicts.append({"unit_id": uid, "fields_differing": sorted(diff)})

# ── ★ 2026-10-09：裁决档 —— 真冲突的那些 unit_id **一行都不压** ────────────────
#   默认档（不带 --skip-conflicts）行为**一个字没改**：有真冲突就整批拒绝。
conflict_ids = {c["unit_id"] for c in conflicts}
frozen_dropped = 0
if SKIP_CONFLICTS and conflict_ids:
    keep = [r for i, r in enumerate(rows)
            if last_at[r["unit_id"]] == i or r["unit_id"] in conflict_ids]
    frozen_dropped = len(rows) - dropped - len(keep)
    dropped = len(rows) - len(keep)

print(f"[{RUN}] units.jsonl 去重{'【落盘】' if APPLY else '【干跑】'}"
      f"{'（裁决档：真冲突一行不压）' if SKIP_CONFLICTS else ''}")
print(f"  行数 {len(rows)} → {len(keep)}（丢重复 {dropped} 行 / {len(dup_ids)} 个 unit_id）")
print(f"  unit_id distinct: {len({r['unit_id'] for r in rows})} → {len({r['unit_id'] for r in keep})}")
print(f"  除 meta 外还有字段冲突的重复：{len(conflicts)} 个"
      f"{'（' + str([c['unit_id'] for c in conflicts[:3]]) + '…）' if conflicts else '（无：纯双写，不是内容冲突）'}")
byres = collections.Counter(r["resource_id"] for r in rows if cnt[r["unit_id"]] > 1)
for rid, n in byres.most_common():
    print(f"    {n:>3} 行重复  {rid[:80]}")
if conflicts and not SKIP_CONFLICTS:
    print("\n  ✗ 存在真冲突，拒绝压缩：先人工判哪一份是对的。")
    print("    只想压掉那批**逐字段相同**的重复行、把冲突原样冻住：加 --skip-conflicts")
    sys.exit(2)


def _conflict_entry(uid):
    """一对冲突的完整证据 + **可复核的推荐**（人裁决前先看这一条）。"""
    g = by[uid]
    texts = [(i, r, r.get("text") or "") for i, r in g]
    uniq = {t for _, _, t in texts}
    detail = [{"line": i + 1, "text_chars": len(t), "char_count": r.get("char_count"),
               "anchor": r.get("anchor"), "rule_eligible_run": r.get("rule_eligible_run"),
               "splitter_version": r.get("splitter_version"),
               "source_sha256": r.get("source_sha256"), "resource_id": r.get("resource_id"),
               "text_head": t[:120]} for i, r, t in texts]
    if len(uniq) == 1:
        rec = {"rule": "keep-last-write", "keep_line": texts[-1][0] + 1,
               "why": "各份正文**逐字相同**（只有规则可用性/元信息不同）⇒ 保留最后一次写入，零内容风险"}
    else:
        longest = max(texts, key=lambda x: len(x[2]))
        last = texts[-1]
        rec = {"rule": "keep-longest-text", "keep_line": longest[0] + 1,
               "keep_text_chars": len(longest[2]),
               "why": f"同一 source_sha256 与锚点下正文长度差 "
                      f"{len(longest[2]) - min(len(t) for _, _, t in texts)} 字 ⇒ 保留最长的一份",
               # ★ 这个读数就是「重切把正文写短了」的信号：晚写的那份不是最长的那份
               "late_write_is_shorter": last[0] != longest[0],
               "late_write_text_chars": len(last[2])}
    return {"unit_id": uid, "resource_id": texts[0][1].get("resource_id"),
            "kb_type": texts[0][1].get("kb_type"), "rows": detail,
            "verdict": "待人工裁决", "recommendation": rec}


if conflicts:
    led = [{**_conflict_entry(c["unit_id"]), "generated_by": "kb/l8/l2_dedup_units.py",
            "run_id": RUN, "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "note": "本文件是**状态**（现在还挂着哪些未裁决的冲突）—— 每次扫描整份重写；"
                    "历史动作记在 kb/l2/runs/<RUN>-dedup.json 里"}
           for c in conflicts]
    if APPLY:
        os.makedirs(os.path.dirname(CONFLICT_LEDGER), exist_ok=True)
        with open(CONFLICT_LEDGER, "w", encoding="utf-8") as fh:
            for e in led:
                fh.write(json.dumps(e, ensure_ascii=False, sort_keys=True) + "\n")
    shrink = [e["unit_id"] for e in led if e["recommendation"].get("late_write_is_shorter")]
    print(f"\n  ⚠ 真冲突 {len(conflicts)} 对{'（已冻住，一行未压）' if SKIP_CONFLICTS else ''}"
          f"｜其中「**晚写的那份更短**」{len(shrink)} 对 —— 这 6 类若按默认政策压，会毁掉正文。")
    for e in led[:8]:
        r = e["recommendation"]
        print(f"     {e['unit_id']}  {str(e['resource_id'])[:46]:<46} "
              f"{[x['text_chars'] for x in e['rows']]} → 推荐 {r['rule']}（行 {r['keep_line']}）")
    if APPLY:
        print(f"  [台账{'写入' if APPLY else '（干跑未写）'}] {CONFLICT_LEDGER}（{len(led)} 条）")

if not APPLY:
    print("\n  [干跑] 未落盘。加 --apply 即归档并压缩")
    sys.exit(0)

os.makedirs(ARCH, exist_ok=True)
bak = f"{ARCH}/units.jsonl.before-dedup-{RUN}"
shutil.copy2(SRC, bak)
tmp = SRC + ".tmp"
with open(tmp, "w", encoding="utf-8") as fh:
    for r in keep:
        fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
after = load(tmp)
assert len(after) == len(rows) - dropped, (len(after), len(rows), dropped)
assert {r["unit_id"] for r in after} == {r["unit_id"] for r in rows}, "unit_id 集合不该变"
assert len(after) == len(keep)
os.replace(tmp, SRC)
print(f"\n  [归档] {bak}（{len(rows)} 行）")
print(f"  [写入] {SRC} → {len(after)} 行")
json.dump({"run_id": RUN, "kind": "l2_units_dedup", "before": len(rows), "after": len(after),
           "dropped_rows": dropped, "dup_unit_ids": len(dup_ids),
           "conflicts": conflicts, "archive": bak,
           "kept": "每个 unit_id 的最后一次写入"},
          open(f"kb/l2/runs/{RUN}-dedup.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"  [报告] kb/l2/runs/{RUN}-dedup.json")
