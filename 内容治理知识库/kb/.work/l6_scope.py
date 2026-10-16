#!/usr/bin/env python3
"""L6 范围确定：复算「可用单元」，再按 kb/l6/SCOPE.txt 收窄为人工核定白名单。
kb/l0~l3 只读。

★ 口径来源（批次11 · B 块，2026-10-02 改）：
  本脚本**不再自带一份 FILTER**，改为调用 `kb/.work/l6_scope_lib.py`。
  为什么必须改（批次11 复核实测）：
    · 库的 docstring 写着「本文件是唯一口径来源，`l6_scope.py` 与 `l6_build.py` 都从这里取」，
      但**本脚本此前零 import 该库**，自带一份 inline FILTER（旧 `:29-74`）。
    · 那份 inline 副本是**2026-09-29/30 四处修订之前**的形态，缺：
        oversize_gt_8000 尺寸护栏、GOOD_QUALITY_FLAGS 放行名单、
        internal_sample 收「负面样本」表、l2_unit_retired 单元级退役、l2_invalidated。
    · 后果一（假绿）：它拿旧口径与同样旧的 `kb/.work/l3_stats.json`（`kept=3540`）互证，
      打出「对账 PASS」—— 两边同源同旧，永远对得上，对不出任何东西。
    · 后果二（谁落伍，反证）：`SCOPE.txt` 4293 条对**库口径**命中 4261（仅 32 条失效），
      对旧口径只命中 3445（**848 条「未命中」**）⇒ 落伍的是旧口径，不是 SCOPE.txt。
  按边界纪律：**不动 SCOPE.txt、不动库、不动 l6_build.py**，只让本脚本改为取库口径。
"""
import collections, json, os, sys

# ── 干跑档（批次6 加，2026-10-01）────────────────────────────────────────────
# 行为变更：本脚本此前**运行即写盘**（唯一写点 = 文件末尾那一处 `kb/.work/l6_scope.json`）。
# 现在：不带 `--apply` = 预演（**不写**该证据件，只把对账结果打屏）；带 `--apply` = 真档。
# 为什么要它：本脚本已被**补登进 `layers.yaml` 的 L6 `engine`**（批次6 B 块），
# 而 engine 清单里不许有**不可预演**的引擎（同批次5 给 `l6_selftest.py` 补档的理由）。
# 闸门位次：本段早于第一个副作用（全脚本唯一的写在文件末尾），其余全是 `kb/l0~l3` 只读。
# 命名避撞：**不写** `kb/l6/runs/<RUN>-dryrun.json`（那个名字归 L6 落章引擎 `l6_report.py`）；
# 预演档**不产**任何落章件 —— 本脚本不是落章引擎（L6 的落章引擎是 `l6_report.py`）。
_AV = [a for a in sys.argv[1:]]
APPLY = "--apply" in _AV
if APPLY:
    _AV.remove("--apply")
RUN = _AV[0] if _AV and not _AV[0].startswith("--") else "20260923-1400"
# ──────────────────────────────────────────────────────────────────────────

# ── 唯一口径来源（批次11 · B 块）────────────────────────────────────────────
# 路径注入：本脚本在 `kb/.work/` 下，与库同目录；显式插入而不是靠 cwd 侥幸。
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import l6_scope_lib as LIB

L2, L6 = "kb/l2", "kb/l6"

U = LIB.load_units()
# 口径只有一份：可用集合、过滤分布、字段角色表全部由库给出。
kept, FILTER = LIB.usable_units(U)

# ---- 与 L3 台账对账（批次11 · B 块重写）------------------------------------
# 旧实现为什么是**假绿**（批次11 复核实测）：
#   `expect` 全部取自 `kb/.work/l3_stats.json`，而那个文件是 `kb/.work/l3_report.py`
#   把 **L3 自己报告里的数** 抄出来的副本（`:349-355`）。旧 `l6_scope.py` 又用**与 L3 同一份
#   旧过滤式**去复算 ⇒ 两边同源同旧，`got == expect` 恒成立。「对账 PASS」对不出任何东西。
# 现在改成三层，且把**基准同源性**单独判：
#   ① l2_total        —— 输入读数，两边都应等于 L2 行数（真对账，有意义）
#   ② kept            —— 口径对账：必须等于**库口径**的可用数
#   ③ baseline_same_source —— 基准同源性：`l3_stats["kept"]` 是否等于库口径可用数。
#      不等 = 这份基准出自**已被取代的口径**，**不许拿它当边界**（批次11 实测：3540 ≠ 4261）。
#      举证：`kb/.work/l3_distill2.py`（L3 自己的引擎，l3_stats 的出处）里
#      `MAX_UNIT_CHARS`/`GOOD_QUALITY_FLAGS`/`pdf_ocr_vision`/`负面样本`/`retired_units`
#      出现次数**均为 0**，即 2026-09-29/30 的四处修订它一条都没有。
stats = json.load(open("kb/.work/l3_stats.json", encoding="utf-8"))
expect = {f"{k[0]}|{k[1]}": v for k, v in
          {(k.split("|")[0], k.split("|")[1]): v for k, v in stats["filtered"].items()}.items()}
got = {f"{k[0]}|{k[1]}": v for k, v in FILTER.items()}

l2_total_ok = (len(U) == stats["accounting"]["l2_total"])
kept_ok = (len(kept) == stats["kept"])
baseline_same_source = kept_ok          # 基准与库口径同源 ⟺ 可用数一致
dist_ok = (got == expect)
checks = {
    "l2_total": {"got": len(U), "baseline": stats["accounting"]["l2_total"], "ok": l2_total_ok},
    "kept": {"got": len(kept), "baseline": stats["kept"], "ok": kept_ok,
             "baseline_note": ("同源" if baseline_same_source else
                               "**基准落伍**：l3_stats.json 出自已被取代的口径"
                               "（kb/.work/l3_distill2.py），不许当边界")},
    "baseline_same_source": baseline_same_source,
    "filter_distribution": {"got": got, "baseline": expect, "ok": dist_ok},
}
ok = bool(l2_total_ok and kept_ok and baseline_same_source and dist_ok)

# ---- SCOPE.txt 子集（批次11 · B 块：改调库，收窄逻辑也只有一份）----------
# 旧实现在这里又抄了一遍「读白名单 + 取子集」；库的 `apply_scope_file()`（F11 补）才是
# `l6_build.py` 真正走的那份。不调库 = 报告器与建索引器可能再一次不同源。
# 顺带修掉字段误标：旧 `usable_total` 是在**收窄之后**才取的 `len(kept)` ⇒ 一个名字两义。
# 现在拆成两个字段，谁都不许再一义两名：
#   usable_before_scope = 库口径可用数（收窄前）
#   usable_after_scope  = SCOPE.txt 收窄后的条数（真正建索引的那批）
usable_before_scope = len(kept)
FILTER_BEFORE_SCOPE = collections.Counter(FILTER)      # 收窄前的分布，供对账（收窄会往 FILTER 里加项）
kept, removed, scope_info = LIB.apply_scope_file(kept, FILTER)
usable_after_scope = len(kept)
if scope_info is None:
    scope_note = "无 kb/l6/SCOPE.txt → 对全部可用单元建索引"
else:
    scope_note = (f"按 kb/l6/SCOPE.txt 取子集：{scope_info['specified']} 条指定，"
                  f"命中可用单元 {scope_info['hits']} 条，"
                  f"未命中 {len(scope_info['specified_but_not_usable'])}")

# ---- 语言构成（供分语言索引预估）
def cjk(ch):
    o = ord(ch)
    return 0x3400 <= o <= 0x9FFF or 0x3040 <= o <= 0x30FF or 0xF900 <= o <= 0xFAFF


LANG = collections.Counter()
for u in kept:
    t = u.get("text") or ""
    has_cjk = any(cjk(c) for c in t)
    has_lat = any(c.isascii() and c.isalpha() for c in t)
    LANG["中英混排" if has_cjk and has_lat else ("中文" if has_cjk else
          ("英文/拉丁" if has_lat else "无字母"))] += 1

out = {
    "run_id": RUN, "scope_note": scope_note,
    # ── 批次11 · B 块：一个名字只许一义（旧版 `usable_total` = 收窄后的 len(kept)，误标）──
    "usable_before_scope": usable_before_scope,
    "usable_after_scope": usable_after_scope,
    "usable_total": usable_after_scope,     # 兼容旧读者：明确等于 after，不再两义
    "usable_total_note": ("`usable_total` 是历史字段名，**等于 usable_after_scope**；"
                          "收窄前的数看 usable_before_scope"),
    "scope_file_applied": bool(scope_info), "scope_info": scope_info,
    "usable_source": "kb/.work/l6_scope_lib.py（唯一口径来源；本脚本不再自带 FILTER）",
    "reconcile_ok": ok, "baseline_same_source": baseline_same_source,
    "checks": checks,
    # 分布取**收窄前**的（收窄会给 FILTER 加 `*|outside_scope_file`，那是另一件事）
    "filter_distribution_got": {f"{k[0]}|{k[1]}": v for k, v in FILTER_BEFORE_SCOPE.items()},
    "filter_distribution_expected": expect,
    "filter_distribution_after_scope_extra": {
        f"{k[0]}|{k[1]}": v for k, v in FILTER.items() if v != FILTER_BEFORE_SCOPE.get(k)},
    "lang_composition": dict(LANG),
    "by_kb_type": dict(collections.Counter(u["kb_type"] for u in kept)),
    "unit_ids": [u["unit_id"] for u in kept],
}
if APPLY:
    json.dump(out, open("kb/.work/l6_scope.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"[apply] 证据件已写 → kb/.work/l6_scope.json（reconcile_ok={ok}, run_id={RUN}）")
else:
    print(f"[dry-run] **未写** kb/.work/l6_scope.json（reconcile_ok 本会是 {ok}, run_id={RUN}）"
          f" —— 加 --apply 才落盘")

print(f"L2 单元 {len(U)} → 库口径可用 {usable_before_scope} → SCOPE.txt 收窄后 {usable_after_scope}"
      f"（对账 {'PASS' if ok else 'FAIL'}）")
print(f"对账 l2_total   : got={len(U)} baseline={stats['accounting']['l2_total']} ok={l2_total_ok}")
print(f"对账 kept       : got={usable_before_scope} "
      f"baseline={stats['kept']} ok={kept_ok}")
if not baseline_same_source:
    print(f"  ❌ **基准落伍**：l3_stats.json 的 kept={stats['kept']} 不等于库口径可用数 "
          f"{usable_before_scope}；该基准出自 kb/.work/l3_distill2.py（2026-09-29/30 四处修订一条都没有）")
    print(f"     ⇒ 拿它当边界就是拿旧口径自证旧口径。**本对账判 FAIL，不判 PASS。**")
print(f"过滤分布 got={got}")
print(f"过滤分布 exp={expect}（同源于落伍基准 ⇒ 不等是预期的，见上）")
print(f"语言构成：{dict(LANG)}")
print(f"kb_type：{out['by_kb_type']}")
print(f"范围：{scope_note}")
sys.exit(0 if ok else 1)
