#!/usr/bin/env python3
"""把 OCR 结果回写 L1 台账（append-only）。

前置：kb/l8/ocr_attachments.py <OCR_RUN> --purge-images 已跑完，产出
  · kb/l1/2_内部正负样本库/media_<table>_<rid>.json     （每条记录一份，含 image_ocr segments）
  · kb/l1/media/media_<table>_<rid>/ocr.json            （每图一份 OCR 明细）
  · kb/l1/media/<OCR_RUN>.manifest.json                 （运行统计）

本脚本追加两类 L1 行（覆盖此前的 pending_ocr / forbidden）：
  ① 附件级：bitable:<tid>:<rid>/<fid>/<token> → status ok，char_count=该图 OCR 字数
  ② 媒体容器级：media:<tid>:<rid> → status ok，segment_count/char_count/media_count
并写 kb/l1/runs/<RUN>.json 运行记录 + 与 OCR manifest 对账（数字必须自洽）。
用法：python3 kb/l8/apply_ocr_to_l1.py <OCR_RUN> <L1_RUN> [--apply]
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
import sys

# ── 批次11 · C-2：台账去重实现只有一份（kb/kb_ledger.py），这里只取用 ──────────
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import kb_ledger as _ledger_mod

# ★ 2026-10-01（批次4 · D-1 真缺陷）：落章契约要求落章记录的 `run_id` 以**编排器的 <RUN>** 开头，
#   而本脚本落章用的是 `L1_RUN`（**第二位置参数**，见 :123 的 `{L1_RUN}.json`），
#   与编排器 RUN 可能不同名 ⇒ 落章挂不上本 RUN。
#   改法：接受 `--run <RUN>` / `--run=<RUN>`，**优先级最高**（与编排器同源）；
#   **不传时行为与旧版完全一致**（仍取第二个位置参数，仍回落到 20260929-1630）。
_argv = list(sys.argv[1:])
_run_ov = None
for _i, _a in enumerate(list(_argv)):
    if _a == "--run" and _i + 1 < len(_argv):
        _run_ov = _argv[_i + 1]; del _argv[_i:_i + 2]; break
    if _a.startswith("--run="):
        _run_ov = _a.split("=", 1)[1]; del _argv[_i]; break
_pos = [a for a in _argv if not a.startswith("--")]
OCR_RUN = _pos[0] if len(_pos) > 0 else "20260929-1620"
L1_RUN = _pos[1] if len(_pos) > 1 else "20260929-1630"
if _run_ov:
    L1_RUN = _run_ov                     # 与编排器同源（落章 run_id 因此对得上 <RUN>）
APPLY = "--apply" in sys.argv
L1 = "kb/l1"
TABLE = "tbld8qE92YaY38Yz"

ocr_man = json.load(open(f"{L1}/media/{OCR_RUN}.manifest.json", encoding="utf-8"))
stats = ocr_man.get("stats") or {}
print("OCR 运行统计:", json.dumps(stats, ensure_ascii=False))
print("OCR 出文本段落:", ocr_man.get("segments_total"), "| 字符:", ocr_man.get("chars_total"))

rows = [json.loads(l) for l in open(f"{L1}/manifest_l1.jsonl", encoding="utf-8") if l.strip()]
MAN_KEYS = set(rows[0].keys())
latest = {}
for r in rows:
    latest[r["resource_key"]] = r

# 收 OCR 结果：按 (rid, file_token) → 文本
per_file, per_rec = {}, {}
media_files = []
for fn in os.listdir(f"{L1}/2_内部正负样本库"):
    if not (fn.startswith(f"media_{TABLE}_") and fn.endswith(".json")):
        continue
    d = json.load(open(f"{L1}/2_内部正负样本库/{fn}", encoding="utf-8"))
    # OCR 产物按 L1 artifact schema 写，record_id 编码在 resource_key = media:<tid>:<rid> 里
    rid = d.get("record_id") or d["resource_key"].split(":")[-1]
    per_rec[rid] = d
    media_files.append(fn)
    for img in d.get("media_refs") or []:
        per_file[(rid, img.get("file_token"))] = img
print(f"读到媒体产物 {len(media_files)} 条（记录级），附件明细 {len(per_file)} 条")

new_rows = []
# ① 附件级
for (rid, tok), img in sorted(per_file.items(), key=lambda x: (x[0][0], x[0][1])):
    key = f"bitable:{TABLE}:{rid}/fldnvxjaSr/{tok}"
    old = latest.get(key)
    if old is None:
        continue
    row = dict(old)
    row.update({"status": "ok" if (img.get("status") == "ok") else "empty",
                "status_reason": "" if img.get("status") == "ok" else "已下载并 OCR，但未识别出文本",
                "char_count": img.get("chars") or 0, "segment_count": 1 if img.get("chars") else 0,
                "source_sha256": img.get("sha256"), "observed_at": L1_RUN})
    new_rows.append(row)
# ② 媒体容器级
for rid, d in sorted(per_rec.items()):
    key = f"media:{TABLE}:{rid}"
    old = latest.get(key) or {"resource_id": f"media_{TABLE}_{rid}", "resource_key": key,
                              "kb_type": "internal_sample", "source_kind": "feishu_attachment",
                              "source_sha256": None, "extractor_version": "l1-0.1",
                              "status": "pending_ocr", "status_reason": "", "segment_count": 0,
                              "char_count": 0, "media_count": 0, "table_count": 0, "observed_at": L1_RUN}
    row = dict(old)
    row.update({"status": d.get("status") or "ok", "status_reason": d.get("status_reason") or "",
                "segment_count": d.get("segment_count") or 0, "char_count": d.get("char_count") or 0,
                "media_count": d.get("media_count") or 0, "observed_at": L1_RUN,
                "source_sha256": None})
    assert not (set(row) - MAN_KEYS), set(row) - MAN_KEYS
    new_rows.append(row)

seg = sum(1 for r in new_rows if r["resource_key"].startswith("media:") for _ in range(r["segment_count"] or 0))
chars = sum(r["char_count"] or 0 for r in new_rows if r["resource_key"].startswith("media:"))
print(f"将追加 {len(new_rows)} 行（附件级 {sum(1 for r in new_rows if '/' in r['resource_key'])}，"
      f"媒体容器 {sum(1 for r in new_rows if '/' not in r['resource_key'])}）")
print(f"对账：容器级 segments={seg} chars={chars} | OCR manifest segments={ocr_man.get('segments_total')} chars={ocr_man.get('chars_total')}")
ok_self = (seg == (ocr_man.get("segments_total") or 0))
print("自洽:", "✓" if ok_self else "✗（数字不一致，需看）")

if APPLY:
    # ── 批次11 · C-2 写入点①：改走**去重追加**（原为无条件 `"a"` 追加）──────────
    # 去重判定与读侧「同键取行序最后一行」严格对应：同键且除运行元数据外全等
    # ⇒ 读侧结果不变 ⇒ 不追加。实现只有一份：kb/kb_ledger.py。
    _dedup = _ledger_mod.dedup_append(
        f"{L1}/manifest_l1.jsonl", new_rows, "resource_key", label="@apply_ocr_to_l1.py",
        last_seen_path="kb/l1/registry/last_seen.json", run=L1_RUN)
    rep = {"run": L1_RUN, "layer": "l1", "kind": "ocr_backfill", "ocr_run": OCR_RUN,
           "attachments_ok": sum(1 for r in new_rows if "/" in r["resource_key"] and r["status"] == "ok"),
           "attachments_empty": sum(1 for r in new_rows if "/" in r["resource_key"] and r["status"] == "empty"),
           "media_containers": sum(1 for r in new_rows if "/" not in r["resource_key"]),
           "segments": seg, "chars": chars, "self_consistent": ok_self,
           "manifest_dedup": _dedup,
           "ocr_stats": stats, "purge": ocr_man.get("purge"),
           "note": "此前 283 条为 forbidden（库级禁止下载）；守衡取得下载权后重跑 OCR 并回写"}
    json.dump(rep, open(f"{L1}/runs/{L1_RUN}.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"已写入 L1 manifest +{_dedup['appended']} 行"
          f"（去重跳过同内容重复 {_dedup['dup_skipped']}）；运行记录 kb/l1/runs/{L1_RUN}.json")
else:
    print("未写入（加 --apply）")
