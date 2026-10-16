#!/usr/bin/env python3
"""L4 条款号台账修复：把被 l4_article.py 整份覆盖掉的 article-no-2 方案与已发号复原。

## 为什么需要它（2026-09-30 事故）

`kb/.work/l4_article.py` 在 --apply 时**整份重建** registry（现造 reg 字典后
write_if_changed 覆盖 `kb/l4/registry/l4.json`）。2026-09-30 16:03 有人以
RUN=20260930-1550 跑了它，后果三条：

  ① 抹掉 batch9_assign.py 定义的权威方案 `article-no-2`：numbering.scheme_version /
     block_by_library / block_by_library_authority / reserved_policy /
     order_key_per_form / scheme / scheme_defined_at_run / form_block_retired_at_run
     共 8 个键消失；
  ② `numbering.issued` 从 5 段 1242 号缩回 2 段 509 号 —— W-3(157) + S-1(201) + E-1(375)
     = **733 个已经发出去的号从「唯一台账」里消失**。而 numbering.no_reuse 写着
     「号码一经发出永久占用，不回收、不重发」—— 台账丢了号，后续批次就会把
     同一个号发给另一条规则（号码冲突且不可回溯）；
  ③ 把**已废止**的 `form_block`（entry1/revision_pair2/boundary3/saythis4）重新写成生效值。
     batch9_assign.py:44 明写它自 20260924-1320 起废止（其 boundary=3 与 W-3 冲突，
     沿用会让同一段号指两个形态）。

## 为什么这是「复原」而不是「新发号」

判据不是我说了算，是实测：损坏前的全量台账留在了
`kb/l8/_archive/fix-20260929-094703/l4-before-repromote/l4.json`
（assignments 1242 / issued 5 段 / scheme_version=article-no-2）。
本脚本把它与现库 `kb/l4/canonical/*.jsonl` 的 1242 个 article_no 逐号对账：
**1:1 完全一致、0 处不符**。所以复原的是已证事实。

## 红线（本脚本自己遵守）

- **只补缺、不改已发号**：live 里已有的号码一个不动；live 与归档对同一 id 给了
  不同号码 = 冲突 → 拒绝落盘并报错，交人裁决。
- **先验证后落盘**：逐号对账不通过就退出，不写任何字节。
- **幂等**：没有缺项时零写入（连 mtime 都不动）。
- **原子写**：tmp → json.load 验 → os.replace（本层是全库唯一做原子写的层）。
- 只写 `kb/l4/registry/l4.json` 与 `kb/l4/runs/<RUN>-ledger-repair.json`；
  kb/l0~l3、kb/l5~l7 与 canonical 全程只读。

用法：
    kb/kbpy .work/l4_ledger_repair.py <RUN>              # 干跑（默认）
    kb/kbpy .work/l4_ledger_repair.py <RUN> --apply      # 落盘
"""
# ── 解释器守卫（与 l4_article.py 同款）─────────────────────────────────────
import os as _os, sys as _sys
if not _os.environ.get("KB_INTERP_OK"):
    _d = _os.path.dirname(_os.path.abspath(__file__)); _cfg = None
    while True:
        _p = _os.path.join(_d, ".kb-python")
        if _os.path.isfile(_p):
            _cfg = _p
            break
        _q = _os.path.dirname(_d)
        if _q == _d:
            break
        _d = _q
    if _cfg:
        _want = next((l.split("#", 1)[0].strip() for l in open(_cfg, encoding="utf-8")
                      if l.split("#", 1)[0].strip()), "")
        _want = _os.path.expanduser(_want)
        if (_want and _os.access(_want, _os.X_OK)
                and _os.path.realpath(_want) != _os.path.realpath(_sys.executable)):
            _os.environ["KB_INTERP_OK"] = "1"
            _os.execve(_want, [_want, _os.path.abspath(__file__)] + _sys.argv[1:], dict(_os.environ))
# ──────────────────────────────────────────────────────────────────────────

import collections, glob, json, os, sys, time

# ── 干跑档 · 开关解析（早于 RUN 解析，避免 --apply 被当成位置参数）──────────
APPLY = "--apply" in sys.argv
if APPLY:
    sys.argv.remove("--apply")
RUN = sys.argv[1] if len(sys.argv) > 1 else time.strftime("%Y%m%d-%H%M")
# ──────────────────────────────────────────────────────────────────────────

REG = "kb/l4/registry/l4.json"
ARCH = "kb/l8/_archive/fix-20260929-094703/l4-before-repromote/l4.json"
RUNS = "kb/l4/runs"
SCHEME_KEYS = ("scheme_version", "block_by_library", "block_by_library_authority",
               "order_key_per_form", "order_key_note_per_form", "reserved_policy",
               "scheme_defined_at_run", "form_block_retired_at_run", "scheme")
t0 = time.time()

# ── 干跑档 · 落盘闸门（必须早于本脚本第一个副作用）────────────────────────
if not APPLY:
    print("[dry-run] %s 未落盘。" % os.path.basename(os.path.abspath(__file__)))
    print("[dry-run] 本脚本会写入：kb/l4/registry/l4.json（补回 article-no-2 方案键与缺的已发号段）、"
          "kb/l4/runs/%s-ledger-repair.json" % RUN)
    print("[dry-run] 加 --apply 才落盘。只补缺、不改已发号；逐号对账不过则拒绝写。")
# ──────────────────────────────────────────────────────────────────────────


def load_json(p):
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


def save_atomic(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=1)
    json.load(open(tmp, encoding="utf-8"))          # 先验后换（本层事故教训）
    os.replace(tmp, path)


# ---------------- 一、读三份事实 ----------------
live = load_json(REG)
arch = load_json(ARCH)
canon = []                                        # 现库 canonical 的 (id, article_no, 文件)
for p in sorted(glob.glob("kb/l4/canonical/*.jsonl")):
    for l in open(p, encoding="utf-8"):
        if l.strip():
            r = json.loads(l)
            idk = "rule_id" if "rule_id" in r else ("case_id" if "case_id" in r else "clause_id")
            canon.append((idk, r[idk], r.get("article_no"), os.path.basename(p)))
print(f"现库台账 run_id={live.get('run_id')}｜issued 段 {sorted(live['numbering'].get('issued', {}))}")
print(f"归档台账 scheme_version={arch['numbering'].get('scheme_version')}｜"
      f"issued 段 {sorted(arch['numbering']['issued'])}｜assignments {len(arch['assignments'])}")
print(f"现库 canonical：{len(canon)} 行")

# ---------------- 二、逐号对账（先验证，后落盘）----------------
arch_an = {}                                      # 归档：id → 号
for seg, info in arch["numbering"]["issued"].items():
    for k, v in (info.get("assigned") or {}).items():
        if k in arch_an and arch_an[k] != v:
            print(f"★归档自相矛盾：{k} 既是 {arch_an[k]} 又是 {v}")
            sys.exit(2)
        arch_an[k] = v
assert arch_an == arch["assignments"], "归档 issued 与 assignments 不一致，拒绝据此修复"

mismatch, unknown = [], []
for idk, rid, ano, f in canon:
    want = arch_an.get(rid)
    if want is None:
        unknown.append((f, rid, ano))
    elif want != ano:
        mismatch.append((f, rid, want, ano))
print(f"逐号对账：一致 {len(canon) - len(mismatch) - len(unknown)}｜"
      f"不符 {len(mismatch)}｜归档查不到 {len(unknown)}")
if mismatch or unknown:
    print("★逐号对账不通过 → 拒绝落盘（归档不是现库的正确台账，不得用它修复）")
    for x in (mismatch + unknown)[:10]:
        print("   ", x)
    sys.exit(3)

# ---------------- 三、算差异：缺哪些段、缺哪些键 ----------------
live_issued = live["numbering"].get("issued", {})
# 快照「修复前」状态：必须深拷贝 —— live_issued 是 live 内部的引用，就地改段会把 before 也改掉
_before = {"segments": sorted(live_issued), "assigned": len(live.get("assignments", {}))}
missing_segs = [s for s in arch["numbering"]["issued"] if s not in live_issued]
missing_keys = [k for k in SCHEME_KEYS if k not in live["numbering"]]
live_assign = live.get("assignments", {})
add_assign = {k: v for k, v in arch["assignments"].items() if k not in live_assign}
# 已有号的 id 若与归档冲突 → 拒绝（只补缺、不改已发号）
conflict = {k: (live_assign[k], arch["assignments"][k])
            for k in live_assign if k in arch["assignments"] and live_assign[k] != arch["assignments"][k]}
print(f"\n缺的段：{missing_segs or '无'}")
print(f"缺的方案键：{missing_keys or '无'}")
print(f"缺的逐号登记：{len(add_assign)} 条")
print(f"与已发号冲突：{len(conflict)} 条")
if conflict:
    print("★已发号与归档冲突 → 拒绝落盘（交人裁决）")
    for k, v in list(conflict.items())[:10]:
        print("   ", k, "live=", v[0], "arch=", v[1])
    sys.exit(4)

for s in missing_segs:
    info = arch["numbering"]["issued"][s]
    print(f"   {s}: {info.get('count')} 号 {info.get('range')} form={info.get('form')}")

changed = bool(missing_segs or missing_keys or add_assign)
if not changed:
    print("\n台账已完整：无缺项 → 零写入（连 mtime 都不动）")
    json.dump({"run_id": RUN, "action": "ledger_repair", "changed": False,
               "checked_canonical_rows": len(canon), "elapsed_s": round(time.time() - t0, 1)},
              open("/tmp/kbp/ledger-repair-dryrun.json", "w"), ensure_ascii=False, indent=1)
    sys.exit(0)

# ── 干跑在此收口：差异已算完、落盘未开始（闸门位次 = 第一个副作用之前）──
if not APPLY:
    print("\n[dry-run] 以上是差异，未落盘。加 --apply 才写 kb/l4/registry/l4.json。")
    sys.exit(0)

# ---------------- 四、落盘（只补缺）----------------
for k in missing_keys:
    live["numbering"][k] = arch["numbering"][k]
for s in missing_segs:
    live["numbering"]["issued"][s] = arch["numbering"]["issued"][s]
live["assignments"] = {**arch["assignments"], **live_assign}      # live 优先，绝不改已发号
live["numbering"]["ledger_repair"] = {
    "repaired_at_run": RUN, "repaired_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    "by": os.path.basename(os.path.abspath(__file__)),
    "why": "20260930-1550 的 l4_article.py --apply 整份重建 registry，抹掉 article-no-2 方案键并"
           "丢掉了 W-3/S-1/E-1 三段共 733 个已发号；本脚本按损坏前全量台账复原",
    "source_of_truth": ARCH,
    "restored_segments": missing_segs,
    "restored_segment_counts": {s: arch["numbering"]["issued"][s].get("count") for s in missing_segs},
    "restored_assignments": len(add_assign),
    "restored_scheme_keys": missing_keys,
    "verification": "归档台账与现库 kb/l4/canonical/*.jsonl 的 %d 个 article_no 逐号 1:1 完全一致，"
                    "不符 0 / 查不到 0" % len(canon),
    "no_reuse_honored": "live 里已有的号码一个未改；与归档冲突 %d 条" % len(conflict),
}
live["numbering"]["totals"] = {**live["numbering"].get("totals", {}),
                               "assigned": len(live["assignments"]),
                               "segments_used": sorted(live["numbering"]["issued"]),
                               "note": "totals 由 l4_ledger_repair.py 按修复后台账重算"}
save_atomic(REG, live)

os.makedirs(RUNS, exist_ok=True)
save_atomic(f"{RUNS}/{RUN}-ledger-repair.json", {
    "run_id": RUN, "layer": "L4", "action": "ledger_repair", "changed": True,
    "restored_segments": missing_segs,
    "restored_assignments": len(add_assign),
    "restored_scheme_keys": missing_keys,
    "conflict": len(conflict), "checked_canonical_rows": len(canon),
    "before": _before,
    "after": {"segments": sorted(live["numbering"]["issued"]), "assigned": len(live["assignments"])},
    "elapsed_s": round(time.time() - t0, 1)})
print(f"\n★ 已落盘：segment {_before['segments']} → {sorted(live['numbering']['issued'])}｜"
      f"assignments {_before['assigned']} → {len(live['assignments'])}")
print(f"   补回方案键 {len(missing_keys)} 个｜补回已发号 {len(add_assign)} 条｜耗时 {time.time()-t0:.1f}s")
