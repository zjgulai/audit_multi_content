#!/usr/bin/env python3
"""L0 ↔ 飞书侧全表对账（只读+只报告，不改 L0）。

做什么：
  1) 对每个可达的表，用 base +record-list 全量拉一份 ndjson 快照（bot 身份，只读）；
  2) 与 kb/l0/records 下的 L0 记录文件逐条、逐字段比对；
  3) 输出四类差异：only_feishu（飞书有 L0 无）/ only_l0（L0 有飞书无）/ changed（字段值变了）/ same；
  4) 报告同时给「manifest 台账登记情况」—— L0 记录文件存在但 manifest.jsonl 里没有对应行的数量
     （这正是 20260929-1045 对账后遗留的问题）。

不做：不改 kb/l0 任何文件；不下载附件字节；不碰 l1+。
用法：python3 kb/l8/align_l0_feishu.py [RUN]
"""
# ── 解释器守卫（2026-09-29）：不合格就用 kb/.kb-python 指定的解释器重跑自己 ──
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

import collections
import json
import os
import subprocess
import sys
import time

RUN = sys.argv[1] if len(sys.argv) > 1 else time.strftime("%Y%m%d-%H%M")
ENV = dict(os.environ, PATH=os.path.expanduser("~/.dsh/bin") + ":" + os.environ.get("PATH", ""))
# 身份可切换：L8_AS=user 走用户身份（刘华丽），默认 bot
AS_ID = os.environ.get("L8_AS", "bot")
PROFILE = os.environ.get("L8_PROFILE", "dsh-kb")
STAGE = f"kb/l8/_stage/feishu-align/{RUN}"
os.makedirs(STAGE, exist_ok=True)

# 用户指令①：规则库本期不做 → 不在对账范围
TABLES = [
    ("GnRZbIuXraCzf0sGr2UcmZ62nfc", "tbld8qE92YaY38Yz", "负面样本"),
    ("GnRZbIuXraCzf0sGr2UcmZ62nfc", "tblMGtPfe8ZUsEdP", "材料收集"),
    ("GnRZbIuXraCzf0sGr2UcmZ62nfc", "tblZP8jG4tiUL98C", "知识库分类说明"),
    ("Lk3Qb8y2QaVyZns6gprcVNE9nA0", "tblcbk4XiW6471YN", "广告文案明细"),
    ("Lk3Qb8y2QaVyZns6gprcVNE9nA0", "tblD1MiUK1v5fdjD", "品线内容边界规则库"),
    ("Lk3Qb8y2QaVyZns6gprcVNE9nA0", "tblqUTAKFkWheU49", "W1卖点表达边界（品线反馈0910）"),
    ("Lk3Qb8y2QaVyZns6gprcVNE9nA0", "tblLxUfPz4Wqp2na", "风险文案改写建议库（分型号分渠道）"),
    ("N2qkb2YxuatqGLsa4U4cFQxgnCe", "tblGFyycMc45RMga", "数据表"),
    ("SKkkbdZi9aRuMzs7ob0cpSYHnQg", "tbl8AI00JZO1iZtp", "专家修订汇总表"),
    ("SKkkbdZi9aRuMzs7ob0cpSYHnQg", "tblVdl0jdK9G4ld3", "内容公式（仅供参考）"),
]


def canon(v):
    """把字段值归一成可比较的字符串。"""
    return json.dumps(v, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def rid_of_key(k):
    return k.replace(":", "__").replace("/", "_")


# ---------- L0 侧索引 ----------
l0_by_table = collections.defaultdict(dict)   # table_id -> {record_id: (path, doc)}
l0_by_name = collections.defaultdict(dict)    # source_table -> {record_id: (path, doc)}
for root, _dirs, files in os.walk("kb/l0/records"):
    for fn in files:
        if not fn.endswith(".json"):
            continue
        p = os.path.join(root, fn)
        try:
            doc = json.load(open(p, encoding="utf-8"))
        except Exception:
            continue
        rid = doc.get("record_id")
        if not rid:
            continue
        l0_by_table[doc.get("table_id")][rid] = (p, doc)
        l0_by_name[doc.get("source_table")][rid] = (p, doc)

# ---------- manifest 台账索引（最新行取胜） ----------
man_latest = {}
man_rows = 0
for line in open("kb/l0/manifest.jsonl", encoding="utf-8"):
    if not line.strip():
        continue
    man_rows += 1
    r = json.loads(line)
    man_latest[r["resource_key"]] = r
man_record_keys = {k for k, v in man_latest.items() if v.get("source_kind") == "feishu_bitable_record"}

report = {"run": RUN, "tables": {}, "manifest": {}, "summary": {}}
tot = collections.Counter()

for base, tid, name in TABLES:
    snap = f"{STAGE}/{tid}.ndjson"
    p = subprocess.run(
        ["lark-cli", "base", "+record-list", "--base-token", base, "--table-id", tid,
         "--format", "ndjson", "--output", snap, "--overwrite", "--as", AS_ID, "--profile", PROFILE],
        capture_output=True, text=True, encoding="utf-8", errors="replace", env=ENV, timeout=1800)
    ent = {"table": name, "table_id": tid, "base_token": base, "snapshot": snap}
    if not os.path.exists(snap) or os.path.getsize(snap) == 0:
        ent["status"] = "pull_failed"
        ent["error"] = (p.stdout or p.stderr or "")[:300]
        report["tables"][tid] = ent
        tot["pull_failed"] += 1
        print(f"[拉取失败] {name} {tid}: {ent['error'][:120]}")
        continue

    fs = {}
    for line in open(snap, encoding="utf-8"):
        if not line.strip():
            continue
        r = json.loads(line)
        rid = r.get("record_id") or r.get("recordId")
        if rid:
            fs[rid] = r
    l0 = l0_by_table.get(tid) or l0_by_name.get(name) or {}

    only_feishu = sorted(set(fs) - set(l0))
    only_l0 = sorted(set(l0) - set(fs))
    changed = []
    same = 0
    for rid in sorted(set(fs) & set(l0)):
        fvals = {k: v for k, v in fs[rid].items() if k not in ("record_id", "recordId")}
        lvals = {k: (fd or {}).get("value") for k, fd in (l0[rid][1].get("fields") or {}).items()}
        # 只比字段名交集 + 双方都在的字段；字段名差异单列
        diffs = {}
        for k in set(fvals) | set(lvals):
            if canon(fvals.get(k)) != canon(lvals.get(k)):
                diffs[k] = {"feishu": fvals.get(k), "l0": lvals.get(k)}
        if diffs:
            changed.append({"record_id": rid, "fields": diffs})
        else:
            same += 1

    ent.update({
        "status": "ok",
        "feishu_records": len(fs),
        "l0_records": len(l0),
        "same": same,
        "only_feishu": len(only_feishu),
        "only_feishu_ids": only_feishu[:50],
        "only_l0": len(only_l0),
        "only_l0_ids": only_l0[:50],
        "changed": len(changed),
        "changed_detail": changed[:20],
    })
    report["tables"][tid] = ent
    for k in ("same", "only_feishu", "only_l0", "changed"):
        tot[k] += ent[k]
    print(f"[{name}] 飞书={len(fs)} L0={len(l0)} 一致={same} 飞书多={len(only_feishu)} L0多={len(only_l0)} 值变={len(changed)}")

# ---------- manifest 登记对账 ----------
# 注意：resource_key 有两种形态 —— 入口 Base 的表用 bitable:<table_id>:<record_id>，
# 其它 Base 用 bitable:<base_token>:<record_id>。所以按 (table_id, record_id) 建索引比对，
# 不要按拼出来的 key 字符串匹配（否则会在非入口 Base 上误报未登记）。
rec_row = {}
for k, v in man_latest.items():
    if v.get("source_kind") == "feishu_bitable_record" and v.get("record_id"):
        rec_row[(v.get("table_id"), v["record_id"])] = v
unregistered = collections.Counter()
for tid, ent in report["tables"].items():
    if ent.get("status") != "ok":
        continue
    for rid in (l0_by_table.get(tid) or {}):
        m = rec_row.get((tid, rid))
        if m is None or m.get("status") in ("gone", "retracted"):
            unregistered[tid] += 1
report["manifest"] = {
    "manifest_rows_raw": man_rows,
    "manifest_resource_keys": len(man_latest),
    "manifest_active": sum(1 for v in man_latest.values() if v.get("status") not in ("gone", "retracted")),
    "record_files_not_registered": dict(unregistered),
    "record_files_not_registered_total": sum(unregistered.values()),
}
report["summary"] = dict(tot)
out = f"kb/l8/runs/{RUN}-l0-align.json"
json.dump(report, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("\n=== 汇总 ===")
print(f"  一致 {tot['same']} | 飞书多 {tot['only_feishu']} | L0多 {tot['only_l0']} | 值变 {tot['changed']} | 拉取失败 {tot['pull_failed']}")
print("  manifest 未登记的 L0 记录文件:", report["manifest"]["record_files_not_registered_total"],
      report["manifest"]["record_files_not_registered"])
print("  报告:", out)
