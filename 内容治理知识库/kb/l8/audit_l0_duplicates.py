#!/usr/bin/env python3
"""L0 重复项审计（只读）：同一份东西在 L0 里到底被存了几次。

回答三个不同层面的"重复"，**它们不是一回事，别混着报**：

  A. 磁盘字节重复 —— 同一份图片字节在 attachments 下存了多份（真占空间）
  B. 台账行重复 —— manifest.jsonl 里同一资源同一状态被重复登记（增长失控）
  C. 逻辑重复   —— 同一份素材被多条记录引用（**这是源侧事实，不是缺陷**）

用法：
    python3 kb/l8/audit_l0_duplicates.py <RUN>            # 只读，落 kb/l8/runs/<RUN>-l0-dup-audit.json
    python3 kb/l8/audit_l0_duplicates.py <RUN> --no-hash  # 跳过全量求 sha（快，只做行级）

设计约束（与库内其它脚本一致）：
  · **只读**：不写 L0 任何数据，不删任何文件；唯一写的是 kb/l8/runs/ 下的报告。
  · 报告落盘走 tempfile + /bin/cp（python 直接建文件会留下信封态）。
  · "重复"只报事实与可省字节数，**不自动去重** —— 合并字节是存储策略决定，要人拍板。
"""
import collections
import hashlib
import json
import os
import subprocess
import sys
import tempfile

RUN = next((a for a in sys.argv[1:] if not a.startswith("--")), None)
if not RUN:
    raise SystemExit(__doc__)
KB = os.environ.get("L8_KB_ROOT") or "kb"
NO_HASH = "--no-hash" in sys.argv
L0 = os.path.join(KB, "l0")
ATT = os.path.join(L0, "attachments")
SKIP = {"README.md", "_MANIFEST.json"}


def load_manifest():
    rows = []
    with open(os.path.join(L0, "manifest.jsonl"), encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def write_report(path, obj):
    fd, tmp = tempfile.mkstemp(dir="/tmp", prefix="dup-audit-")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=1, sort_keys=True)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.exists(path):
        subprocess.run(["/bin/cp", tmp, path], check=True)
        os.unlink(tmp)
    else:
        os.replace(tmp, path)


def bytes_audit():
    """A. 磁盘字节重复：按 sha256 分组，算"多存的那部分"。"""
    files, total = [], 0
    for root, _, fs in os.walk(ATT):
        for f in fs:
            if f in SKIP:
                continue
            p = os.path.join(root, f)
            s = os.path.getsize(p)
            files.append((p, f.rsplit(".", 1)[0], s))
            total += s
    out = {"files": len(files), "total_bytes": total}
    if NO_HASH:
        out["hashed"] = False
        return out
    by = collections.defaultdict(list)
    for p, tok, s in files:
        h = hashlib.sha256()
        with open(p, "rb") as fh:
            for b in iter(lambda: fh.read(1 << 20), b""):
                h.update(b)
        by[h.hexdigest()].append((p, tok, s))
    groups = {k: v for k, v in by.items() if len(v) > 1}
    wasteful = sum((len(v) - 1) * v[0][2] for v in groups.values())
    top = sorted(groups.items(), key=lambda x: -((len(x[1]) - 1) * x[1][0][2]))[:10]
    out.update({
        "hashed": True,
        "unique_contents": len(by),
        "dup_groups": len(groups),
        "dup_group_bytes": sum(v[0][2] for v in groups.values()),
        "wasteful_bytes": wasteful,
        "wasteful_pct": round(100.0 * wasteful / total, 1) if total else 0.0,
        "top_groups": [{"sha256": k, "copies": len(v), "bytes_each": v[0][2],
                        "wasteful_bytes": (len(v) - 1) * v[0][2],
                        "records": sorted({p.split(os.sep)[-2] for p, _, _ in v}),
                        "paths": [os.path.relpath(p, L0) for p, _, _ in v[:6]]}
                       for k, v in top],
    })
    return out


def ledger_audit(rows):
    """B. 台账行重复：同 key 同 status，且 sha/口径都没变的"空转再登记"。"""
    last, noop_by_change, noop_rows, noop_identity = {}, collections.Counter(), 0, 0
    newest = {}
    noop_att = 0
    for i, r in enumerate(rows):
        k = r.get("resource_key")
        sig = (r.get("status"), r.get("sha256"), r.get("sha256_input"), r.get("sha256_state"))
        if k in last and last[k] == sig:
            noop_rows += 1
            noop_by_change[r.get("change")] += 1
            if r.get("source_kind") == "feishu_attachment":
                noop_att += 1
            if newest.get(k) == r.get("observed_at"):
                noop_identity += 1
        last[k] = sig
        newest[k] = r.get("observed_at")
    c = collections.Counter(r.get("resource_key") for r in rows)
    return {
        "rows": len(rows),
        "unique_resource_keys": len(c),
        "keys_with_multi_rows": sum(1 for n in c.values() if n > 1),
        "noop_reappends": noop_rows,
        "noop_same_observed_at": noop_identity,
        "noop_by_change": dict(noop_by_change.most_common()),
        "attachment_rows": sum(1 for r in rows if r.get("source_kind") == "feishu_attachment"),
        "attachment_noop_reappends": noop_att,
    }


def record_audit():
    """C. 记录层：record_id 唯一性与记录内容重复。"""
    seen, content = collections.Counter(), collections.defaultdict(list)
    n = 0
    for root, _, fs in os.walk(os.path.join(L0, "records")):
        for f in fs:
            if not f.endswith(".json"):
                continue
            n += 1
            p = os.path.join(root, f)
            seen[f[:-5]] += 1
            content[hashlib.sha256(open(p, "rb").read()).hexdigest()].append(os.path.relpath(p, L0))
    return {"files": n,
            "duplicate_record_ids": [k for k, v in seen.items() if v > 1],
            "identical_record_files": [v for v in content.values() if len(v) > 1]}


def orphan_audit(rows):
    """磁盘 token 与台账 token 的双向差集（两边都可能有多出来的）。

    注意（2026-09-30 踩过）：台账里的键不止一种形态 —— 附件是
    `bitable:<tbl>:<rec>/<fld>/<token>`，而云文件是 `file:<token>`。
    只取 `resource_key` 的最后一段会把 `file:<token>` 误判成"台账里没有"。
    """
    keys = [r.get("resource_key") or "" for r in rows]
    latest = {}
    for r in rows:
        latest[r.get("resource_key")] = r          # 末行 = 当前状态
    disk = set()
    for root, _, fs in os.walk(ATT):
        for f in fs:
            if f not in SKIP:
                disk.add(f.rsplit(".", 1)[0])
    on_disk_not_in_ledger = sorted(t for t in disk if not any(t in k for k in keys))
    # 台账里"声称本地有字节"却没有文件的，才是真缺口
    claimed_missing, status_of_missing = [], collections.Counter()
    for k, r in latest.items():
        tok = k.rsplit("/", 1)[-1].split(":", 1)[-1]
        if tok in disk or r.get("status") in ("gone", "retracted"):
            continue
        if r.get("sha256_input") == "file_bytes" or r.get("local_path"):
            claimed_missing.append(k)
            status_of_missing[r.get("status")] += 1
    return {"on_disk_not_in_ledger": on_disk_not_in_ledger,
            "in_ledger_not_on_disk": sum(1 for r in latest.values()
                                         if r.get("status") not in ("gone", "retracted")
                                         and r.get("sha256_input") != "file_bytes"),
            "bytes_claimed_but_missing_on_disk": sorted(claimed_missing),
            "bytes_claimed_but_missing_by_status": dict(status_of_missing)}


rows = load_manifest()
rep = {"run": RUN, "audit": "l0-duplicates", "readonly": True,
       "A_disk_bytes": bytes_audit(),
       "B_ledger_rows": ledger_audit(rows),
       "C_records": record_audit(),
       "D_orphans": orphan_audit(rows),
       "note": "A=真占空间；B=台账膨胀；C/D=完整性。C 里『同一素材被多条记录引用』是源侧事实，"
               "本报告不把它记为缺陷；去重是存储策略决定，需人拍板（脚本不自动合并）。"}
out = os.path.join(KB, "l8", "runs", f"{RUN}-l0-dup-audit.json")
write_report(out, rep)

A, B, Cr = rep["A_disk_bytes"], rep["B_ledger_rows"], rep["C_records"]
print(f"[{RUN}] L0 重复项审计（只读）")
if A.get("hashed"):
    print(f"  A 磁盘: {A['files']} 个文件 / {A['total_bytes']:,} B｜唯一内容 {A['unique_contents']}"
          f"｜重复组 {A['dup_groups']}｜**多存 {A['wasteful_bytes']:,} B（{A['wasteful_pct']}%）**")
    for g in A["top_groups"][:3]:
        print(f"     同一份 ×{g['copies']}（{g['bytes_each']:,} B/份）跨记录 {g['records']}，"
              f"多占 {g['wasteful_bytes']:,} B")
else:
    print(f"  A 磁盘: {A['files']} 个文件 / {A['total_bytes']:,} B（--no-hash，未求 sha）")
print(f"  B 台账: {B['rows']} 行 / 唯一资源 {B['unique_resource_keys']}"
      f"｜空转再登记 {B['noop_reappends']} 行（其中连观测时间都相同 {B['noop_same_observed_at']} 行）")
print(f"     空转最多的写入者: {list(B['noop_by_change'].items())[:4]}")
print(f"  C 记录: {Cr['files']} 个文件｜重复 record_id {len(Cr['duplicate_record_ids'])}"
      f"｜内容相同的记录 {len(Cr['identical_record_files'])} 组")
print(f"  D 差集: 磁盘有台账无 {len(rep['D_orphans']['on_disk_not_in_ledger'])}"
      f"｜台账有磁盘无 {rep['D_orphans']['in_ledger_not_on_disk']}"
      f"｜**声称有字节却没文件（真缺口） {len(rep['D_orphans']['bytes_claimed_but_missing_on_disk'])}**")
print(f"  报告: {out}")
