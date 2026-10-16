#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 `feishu-align/<RUN>/` 的**本次真拉**快照，物化成 `reconcile_l0_feishu.py` 期待的
`feishu-compare/` 形态。

为什么需要这个脚本（批次11 · A 块，2026-10-02）：
  · `reconcile_l0_feishu.py:105` 读 `kb/l8/_stage/feishu-compare`，
    但**全库没有任何生产者写它** —— grep 全仓，只有 `reconcile_l0_feishu.py` 与
    `ocr_attachments.py` 读它，**零处写它**。它是 09-29 手工造的遗留副本。
  · 本次真拉在 `kb/l8/_stage/feishu-align/<RUN>/`（`align_l0_feishu.py` 写）。
  · 两个形态**不兼容**（这正是批次11 A 块选「加门禁」而非「硬接」的第一条依据）：
      - 字段表：compare 是 `{"data":{"fields":[{id,name,type}]}}`（`fields_of()` 读这个）；
                align 是 `{"columns":{name:{field_id,field_type,...}}}` —— **没有 `data` 键**。
      - 记录行：**key 逐字节同构**（已实测：两边的 ndjson 行 keys 序列完全一致，115 条共有
                id 的值差异为 0）⇒ 记录行可直接复制，不用转换。
  ⇒ 本脚本只做「形态翻译 + 落盘」，**不改一个字节的记录内容**。

与门禁的关系：`reconcile_l0_feishu.py` 的新鲜度闸门在暂存陈旧时拒写（退出码 4），
它给的修法①就是本脚本。跑完本脚本，那份暂存的 mtime 就是「现在」，闸门即放行。

用法：
  kb/kbpy l8/materialize_l0_compare.py <ALIGN_RUN> [--apply]
  # ALIGN_RUN = 产生 feishu-align/<RUN>/ 的那次对齐 RUN，例如 20261002-0630
  # 不带 --apply = 预演，只打印将要写什么，一个字节都不落。
"""
# ── 解释器守卫（与库内其余脚本同构）────────────────────────────────────────
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

import hashlib
import json
import os
import shutil
import sys
import time

WS = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
os.chdir(WS)

APPLY = "--apply" in sys.argv
_argv = [a for a in sys.argv[1:] if not a.startswith("--")]
RUN = _argv[0] if _argv else None
if not RUN:
    print("用法：kb/kbpy l8/materialize_l0_compare.py <ALIGN_RUN> [--apply]")
    sys.exit(2)

SRC = f"kb/l8/_stage/feishu-align/{RUN}"
# 目标目录可覆盖：让反测/回归能造隔离夹具，不必动真暂存（也与 reconcile 的
# L0_RECONCILE_STAGE 成对，两边可指同一夹具做端到端反测）。
DST = os.environ.get("L0_COMPARE_OUT") or "kb/l8/_stage/feishu-compare"

# 只物化 reconcile_l0_feishu.py 真正读的两张表（规则库本期不做，见该脚本用户指令①）。
# (table_id, compare 侧文件名, 中文表名)
TABLES = [
    ("tblMGtPfe8ZUsEdP", "材料收集", "材料收集"),
    ("tbld8qE92YaY38Yz", "负面样本", "负面样本"),
]

if not os.path.isdir(SRC):
    print(f"❌ 源快照目录不存在：{SRC}")
    print(f"   先跑对齐产生它： kb/kbpy l8/align_l0_feishu.py {RUN}")
    sys.exit(3)

sha = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()
plan, prov = [], {}
for tid, fname, cn in TABLES:
    rec_p = os.path.join(SRC, tid + ".ndjson")
    man_p = os.path.join(SRC, tid + ".manifest.json")
    if not os.path.isfile(rec_p):
        print(f"❌ 缺记录文件：{rec_p}")
        sys.exit(3)
    rows = [json.loads(l) for l in open(rec_p, encoding="utf-8") if l.strip()]
    # 形态翻译：columns{name:{field_id,field_type,...}} → data.fields[{id,name,type}]
    # 这是 `fields_of()`（reconcile_l0_feishu.py:120-128）唯一认的形态。
    fields = []
    man = {}
    if os.path.isfile(man_p):
        man = json.load(open(man_p, encoding="utf-8"))
        for nm, meta in (man.get("columns") or {}).items():
            fields.append({"id": meta.get("field_id"), "name": nm, "type": meta.get("field_type")})
    if not fields:
        print(f"❌ 无法从 manifest 取字段表（缺 {man_p} 或没有 columns）→ 拒绝物化")
        print("   理由：`fields_of()` 要的是 data.fields；没有它就只能编一个假字段表 —— 不许编。")
        sys.exit(3)
    # 一致性自检（只报，不改）：ndjson 行的 key 集合应被字段表覆盖
    row_keys = set()
    for r in rows:
        row_keys |= {k for k in r if not k.startswith("_")}
    fs_names = {f["name"] for f in fields}
    rec = {"table_id": tid, "table": cn, "src_record_file": rec_p,
           "records_count": len(rows), "records_count_manifest": man.get("records_count"),
           "rev": man.get("rev"), "fields_count": len(fields),
           "row_keys_not_in_fields": sorted(row_keys - fs_names),
           "fields_not_in_rows": sorted(fs_names - row_keys),
           "record_file_sha256": sha(rec_p),
           "records_ids_sha16": hashlib.sha256(
               "|".join(sorted(r["record_id"] for r in rows)).encode()).hexdigest()[:16]}
    prov[tid] = rec
    plan.append((rec_p, os.path.join(DST, f"feishu-{fname}.ndjson"), rows, fields, man_p, man))

print(f"源 : {SRC}")
print(f"目标: {DST}")
print()
for rec_p, dst, rows, fields, man_p, man in plan:
    print(f"  {rec_p}")
    print(f"    → {dst}   {len(rows)} 行 / {len(fields)} 字段 / rev={man.get('rev')}")
prov_path = os.path.join(DST, "PROVENANCE.json")
print(f"    → {prov_path}   （来源留痕）")

if not APPLY:
    print()
    print("[dry-run] 未落盘。加 --apply 才写。")
    print("[dry-run] 本脚本会写：kb/l8/_stage/feishu-compare/ 下的 "
          "feishu-<表>.ndjson、fields-<表>.json、PROVENANCE.json")
    sys.exit(0)

os.makedirs(DST, exist_ok=True)
# 物化前把旧目录整份留档（移动不删除）—— 旧件是「09-29 手工版」，动了它就该留证。
if any(os.path.isfile(os.path.join(DST, f)) for f in os.listdir(DST)):
    tag = time.strftime("%Y%m%d-%H%M%S")
    arch = os.path.join(DST, "_archive", f"pre-materialize-{RUN}-{tag}")
    os.makedirs(arch, exist_ok=True)
    for fn in os.listdir(DST):
        p = os.path.join(DST, fn)
        if os.path.isfile(p):
            shutil.copy2(p, os.path.join(arch, fn))
    print(f"✓ 旧件留档 → {arch}")

written = []
for rec_p, dst, rows, fields, man_p, man in plan:
    # 记录行**逐字节复制**源 ndjson（两边形态本就同构，不做任何转换）。
    # 用 copyfile 而非 copy2：**必须让物化件带"现在"的 mtime**。快照被拉到 align 目录
    # 时是 06:27，物化发生在 07:13；若用 copy2 保留 06:27，新鲜度闸门会把这个刚物化出来
    # 的目录判成陈旧（早于本 RUN）—— 门禁就永远放不了行（本块自测踩到过一次）。
    # 语义上也该如此：物化 = "这份内容现在是当前有效的暂存"。
    shutil.copyfile(rec_p, dst)
    # 字段表写成 `fields_of()` 认的形态，**字段顺序与源 manifest 的 columns 一致**。
    fp = os.path.join(DST, "fields-" + os.path.basename(dst).replace("feishu-", "").replace(".ndjson", "") + ".json")
    json.dump({"ok": True, "identity": "materialized",
               "data": {"fields": fields, "total": len(fields)},
               "_materialized_from": os.path.relpath(rec_p, WS)},
              open(fp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    written += [os.path.relpath(dst, WS), os.path.relpath(fp, WS)]
    print(f"✓ {os.path.relpath(dst, WS)}  ({len(rows)} 行)")
    # manifest 也要一起物化：新鲜度闸门看的是**目录内所有文件**的最早 mtime，
    # 只换 ndjson 的话旧 manifest 会把整个目录判成陈旧 —— 那样门禁就永远放不了行。
    if man_p and os.path.isfile(man_p):
        dm = os.path.join(DST, "feishu-" + fname + ".manifest.json")
        shutil.copyfile(man_p, dm)   # 同上：要新 mtime，不要保留源时间戳
        written.append(os.path.relpath(dm, WS))
        print(f"✓ {os.path.relpath(dm, WS)}")

json.dump({"materialized_at": time.strftime("%Y-%m-%d %H:%M:%S"),
           "align_run": RUN, "source_dir": SRC, "target_dir": DST,
           "note": ("由 kb/l8/materialize_l0_compare.py 从本次真拉的 feishu-align 快照物化；"
                    "记录行逐字节复制，字段表由 manifest.columns 翻译成 data.fields。"
                    "**不是**手工编辑件。"),
           "tables": prov},
          open(prov_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
written.append(os.path.relpath(prov_path, WS))
print(f"✓ {os.path.relpath(prov_path, WS)}")
print()
print("物化完成。现在 reconcile 的新鲜度闸门应放行：")
print(f"  kb/kbpy l8/reconcile_l0_feishu.py <RUN> --apply")
print("写入清单：")
for w in written:
    print("  ", w)
