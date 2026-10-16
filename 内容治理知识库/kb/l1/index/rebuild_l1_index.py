#!/usr/bin/env python3
"""L1 段级投影索引的独立重建工具（F11 常驻件）。

背景
----
`kb/l1/index/l1.jsonl` 原先只作为 `kb/.work/l1_extract_v3.py` 全量抽取的**尾部副作用**写出，
没有独立入口。后果有两层：

1. **必然漂移**：资源文件在抽取之后仍会被后续批次改写，而索引不再重写 →
   实测索引 mtime 2026-09-24 16:27 早于它应覆盖的最新资源文件 2026-09-24 16:54。
2. **无状态过滤**：原写入循环只遍历目录里的 *.json，不读台账 status →
   已 `invalidated`/`retracted` 的资源，其段仍留在索引里（投影在虚报语料规模）。

本工具把索引重建从抽取流程里**切开**，并显式带上状态过滤。口径与原写入循环一致：
只投影 `segments[]` 与 `tables[].rows[]`，字段与排序键逐字保持，`seg_id` 规则不变，
从而与既有下游/历史对账兼容。

关于 `l1/media/`（OI-L1-001 的结论，别再"修"一次）
------------------------------------------------
媒体资源的正文落在 `kb/l1/media/<rec>/ocr.json`，**不在** 5 个批次目录里，
所以它以资源为单位不进索引。这**不是漏**：这批图片的 OCR 文本已经作为
**父 bitable 记录的 segments（kind=image_ocr / image_visual）** 进了索引。
实测：129 个有效 media 资源的 240 张图，240/240 在索引内。
若再按 `l1/media/` 枚举一遍，会把同一段文本**重复计数**。
因此本工具**故意不枚举** `l1/media/`，改为把该覆盖关系写成机器可查的
`media_coverage` 记录（见 --check 输出），供巡检工具核对。

用法
----
    python3 kb/l1/index/rebuild_l1_index.py --check     # 只体检，不写盘；索引陈旧/虚报则 exit 1
    python3 kb/l1/index/rebuild_l1_index.py --write     # 重建（先写 .tmp 再原子替换）
    python3 kb/l1/index/rebuild_l1_index.py --write --run 20260929-1200

`kb/l0`、`kb/l1/*` 除 `index/` 外只读。
"""
import argparse
import collections
import hashlib
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
L1 = os.path.dirname(HERE)
KB = os.path.dirname(L1)

INDEX = os.path.join(HERE, "l1.jsonl")
REPORT = os.path.join(HERE, "index-report.json")
MANIFEST = os.path.join(L1, "manifest_l1.jsonl")
MEDIA = os.path.join(L1, "media")

# 与原 l1_extract_v3.py 的 ORDER / BATCH_DIR 逐字一致
DIR_MAP = {
    "wording": "3_措辞表达库",
    "external_standard": "1_外部标准库",
    "internal_sample": "2_内部正负样本库",
    "product_desc": "4_产品描述库",
    "unknown": "9_未归类",
}
ORDER = ["wording", "external_standard", "internal_sample", "product_desc", "unknown"]

# 内容可用状态（= 允许进投影的状态）。其余一律不进，见 EXCLUDED_REASONS。
CONTENT_STATUS = {"ok", "extracted"}
# 明确"应排除且必须写明理由"的状态，防止以后有人再把它们放回来
EXCLUDED_REASONS = {
    "invalidated": "资源已作废（源记录被移除或父记录失效）",
    "retracted": "资源被撤回",
    "no_scope": "按既有口径不在抽取范围",
    "forbidden": "抓取被禁（robots/权限）",
    "unreachable": "不可达、无正文",
    "empty": "无正文",
    "no_content_expected": "结构性资源，本身不含正文",
    "pending_fetch": "仅登记地址，未抓正文",
    "pending_ocr": "OCR 未完成",
    "failed": "抽取失败",
    "audit_note": "审计备注，非内容资源",
}


def load_ledger():
    """读 append-only 台账取每个资源的最新状态。

    台账可能对同一 resource_id 有多行（重抽/改状态），最后一行即最新。
    """
    latest, rows = {}, 0
    with open(MANIFEST, encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            r = json.loads(line)
            rows += 1
            latest[r["resource_id"]] = r
    return latest, rows


def scan_resources():
    """枚举 5 个批次目录里的资源文件。返回 {resource_id: (path, kb_type)}。"""
    found = {}
    for kb_type in ORDER:
        d = os.path.join(L1, DIR_MAP[kb_type])
        if not os.path.isdir(d):
            continue
        for fn in sorted(os.listdir(d)):
            if not fn.endswith(".json"):
                continue
            p = os.path.join(d, fn)
            try:
                with open(p, encoding="utf-8") as fh:
                    rid = json.load(fh)["resource_id"]
            except Exception as e:  # 坏文件必须暴露，不能静默跳过
                raise SystemExit(f"[E] 资源文件无法解析：{p} :: {e}")
            found[rid] = (p, kb_type)
    return found


def build_rows(latest, files):
    """产出索引行 + 统计。返回 (rows, stats)。"""
    rows = []
    stats = {
        "included_resources": 0,
        "excluded_resources": collections.Counter(),
        "excluded_reasons": {},
        "kinds": collections.Counter(),
        "empty_included": 0,
        "not_on_disk": [],
    }
    for rid, (path, kb_type) in sorted(files.items(), key=lambda kv: (ORDER.index(kv[1][1]), kv[0])):
        rec = latest.get(rid)
        status = rec["status"] if rec else None
        if status not in CONTENT_STATUS:
            key = status or "不在台账"
            stats["excluded_resources"][key] += 1
            if status in EXCLUDED_REASONS:
                stats["excluded_reasons"].setdefault(status, EXCLUDED_REASONS[status])
            continue
        with open(path, encoding="utf-8") as fh:
            o = json.load(fh)
        segs = o.get("segments") or []
        tables = o.get("tables") or []
        if not segs and not tables:
            # 状态说"有内容"但文件里没有 → 记账，不静默丢
            stats["empty_included"] += 1
            continue
        stats["included_resources"] += 1
        si = 0
        for s in segs:
            si += 1
            stats["kinds"][s["kind"]] += 1
            rows.append({
                "seg_id": f"{o['resource_id']}#s{si}",
                "resource_id": o["resource_id"],
                "kb_type": o["kb_type"],
                "kind": s["kind"],
                "anchor": s["anchor"],
                "char_count": len(s["text"]),
            })
        for t in tables:
            for rw in t["rows"]:
                si += 1
                stats["kinds"]["table_row"] += 1
                rows.append({
                    "seg_id": f"{o['resource_id']}#t{t['table_index']}r{rw['row_index']}",
                    "resource_id": o["resource_id"],
                    "kb_type": o["kb_type"],
                    "kind": "table_row",
                    "anchor": rw["anchor"],
                    "char_count": len(rw["text"]),
                })
    # 台账里有、磁盘上没有的资源（只登记，不进索引）
    for rid, rec in latest.items():
        if rid not in files and rec["status"] in CONTENT_STATUS:
            stats["not_on_disk"].append(rid)
    return rows, stats


def media_coverage(latest, index_anchors):
    """核对「媒体资源的图片 OCR 是否已经经父记录进了索引」。

    OI-L1-001 的误报就出在这里：媒体资源以资源为单位不在索引内，但**文本在**。
    本函数把这件事做成可核对的数字，供巡检工具长期盯住。
    """
    valid_media = [
        r for r in latest.values()
        if r["resource_id"].startswith("media_") and r["status"] in CONTENT_STATUS
    ]
    total = hit = absent_files = 0
    for r in valid_media:
        # 媒体目录有两种历史落盘形态，都要认（2026-09-30 实测：只认其中一种会假报 0/0）：
        #   ① 全 id 形态  media/l1/media_<table>_<rec>/ocr.json  —— 2026-09-30 批次（115 个）
        #   ② 裸 rec 形态 kb/l1/media/<rec>/ocr.json             —— 更早批次（165 个，已 invalidated/retracted）
        # 只探测①时：任务①②都不存在 → ocr_json_missing=有效媒体数、images_total=0，
        # 于是图片 OCR 掉出索引 304 条也照样报「images_missing_from_index: 0」的假绿。
        p = next((c for c in (os.path.join(MEDIA, r["resource_id"], "ocr.json"),
                              os.path.join(MEDIA, r["resource_id"].split("_")[-1], "ocr.json"))
                  if os.path.isfile(c)), None)
        if p is None:
            absent_files += 1
            continue
        with open(p, encoding="utf-8") as fh:
            d = json.load(fh)
        for im in d.get("images") or []:
            total += 1
            if im.get("anchor") in index_anchors:
                hit += 1
    return {
        "valid_media_resources": len(valid_media),
        "media_resources_by_design_not_indexed_as_resource": len(valid_media),
        "images_total": total,
        "images_present_in_index_via_parent": hit,
        "images_missing_from_index": total - hit,
        "ocr_json_missing": absent_files,
        "conclusion": (
            "媒体资源以资源为单位不进索引是设计口径（正文经父记录的 segments 进索引）；"
            "只要 images_missing_from_index == 0，就没有图片 OCR 掉出检索链路。"
        ),
    }


def source_fingerprint(files):
    """资源文件的 (最晚 mtime, 条数, path:mtime 摘要) —— 供 --check 判陈旧。"""
    newest, h = 0.0, hashlib.sha256()
    for rid, (path, _) in sorted(files.items()):
        mt = os.path.getmtime(path)
        newest = max(newest, mt)
        h.update(f"{rid}:{int(mt)}\n".encode())
    return newest, len(files), h.hexdigest()


def read_index(path):
    rows = []
    if not os.path.isfile(path):
        return rows
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--check", action="store_true", help="只体检，不写盘")
    g.add_argument("--write", action="store_true", help="重建索引")
    ap.add_argument("--run", default="", help="run id，写进报告")
    args = ap.parse_args()

    latest, ledger_rows = load_ledger()
    files = scan_resources()
    rows, stats = build_rows(latest, files)
    anchors = {r["anchor"] for r in rows}
    # 陈旧只看**在台账里且状态为内容可用**的源文件。
    # 为什么：实测 2026-09-29 11:03 有 8 个 `media_*` 文件同时落盘（source_kind=feishu_attachment、
    # status=empty、0 段）但**不在台账里** —— 是别的写入方留下的无内容占位。若把它们算进
    # "源文件最晚 mtime"，索引会永远显示「陈旧」，而这个 DRIFT 是假的（内容一条没差）。
    # 故：陈旧判据收窄到受管文件；未受管文件单列 untracked_files_on_disk 报出来 —— 仍可见，
    # 但不与「索引陈旧」混为一谈。
    content_files = {rid: v for rid, v in files.items()
                     if latest.get(rid, {}).get("status") in CONTENT_STATUS}
    newest_src, n_src, src_fp = source_fingerprint(content_files)
    untracked = sorted(rid for rid in files if rid not in latest)
    noncontent_on_disk = sorted(rid for rid in files
                                if rid in latest and latest[rid]["status"] not in CONTENT_STATUS)

    cur = read_index(INDEX)
    cur_anchors = {r["anchor"] for r in cur}
    cur_by_res = collections.Counter(r["resource_id"] for r in cur)

    # 覆盖必须量**盘上落着的那份索引**，不能量「重建后会长成什么样」。
    # 为什么：--check 是巡检入口，若拿重建结果当被检物，索引里一条 image_ocr 都没有
    # 时也会报 304/304 —— 又一个假绿（2026-09-30 实测踩到）。--write 时改量写后的索引。
    cov = media_coverage(latest, cur_anchors)

    # 当前索引里的"僵尸行"：资源已不在内容状态，段却还在
    zombie_rows = [r for r in cur if latest.get(r["resource_id"], {}).get("status") not in CONTENT_STATUS]
    zombie_res = {r["resource_id"] for r in zombie_rows}

    idx_mtime = os.path.getmtime(INDEX) if os.path.isfile(INDEX) else 0
    stale = idx_mtime < newest_src

    report = {
        "tool": "kb/l1/index/rebuild_l1_index.py",
        "version": "l1-index-1.0",
        "run": args.run,
        "ledger": {"rows": ledger_rows, "resources": len(latest)},
        "status_filter": {"include": sorted(CONTENT_STATUS), "excluded_reasons": EXCLUDED_REASONS},
        "on_disk_files": n_src,
        "managed_source_files": n_src,
        "untracked_files_on_disk": {"count": len(untracked), "samples": untracked[:20],
                                    "note": "批次目录里有文件、但台账里没有这个资源 —— 别的写入方留下的，"
                                            "不参与陈旧判据；数量持续增长说明有未登记的写入方"},
        "noncontent_files_on_disk": {"count": len(noncontent_on_disk), "samples": noncontent_on_disk[:20],
                                     "note": "台账状态不是内容可用（如 empty/unreachable/no_scope），已在磁盘上但按口径不进索引"},
        "newest_source_mtime": newest_src,
        "index_mtime": idx_mtime,
        "stale": stale,
        "rebuilt_rows": len(rows),
        "rebuilt_resources": stats["included_resources"],
        "excluded_resources": dict(stats["excluded_resources"]),
        "included_but_empty_files": stats["empty_included"],
        "ledger_content_resources_not_on_disk": sorted(stats["not_on_disk"]),
        "kind_distribution": dict(stats["kinds"]),
        "current_index_rows": len(cur),
        "current_index_resources": len(cur_by_res),
        "zombie_rows": len(zombie_rows),
        "zombie_resources": len(zombie_res),
        "zombie_resource_ids": sorted(zombie_res),
        "rows_added_if_rebuilt": len(rows) - len(cur),
        "delta_anchors_missing_from_index": len(anchors - cur_anchors),
        "source_fingerprint": src_fp,
        "media_coverage": cov,
    }

    drift = bool(zombie_rows) or stale or len(anchors - cur_anchors) or len(cur_anchors - anchors)
    report["verdict"] = "DRIFT" if drift else "OK"

    if args.write:
        tmp = INDEX + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
        os.replace(tmp, INDEX)
        report["index_mtime"] = os.path.getmtime(INDEX)
        report["stale"] = report["index_mtime"] < newest_src
        # verdict 必须反映「这一跑干了什么」。先前写档沿用 check 口径 → 刚重建成功的
        # 报告仍留 verdict=DRIFT + current_index_rows=旧值，读档的人会以为漂移没修掉。
        report["verdict"] = "OK" if not report["stale"] else "DRIFT"
        report["pre_rebuild_index_rows"] = report["current_index_rows"]
        report["current_index_rows"] = len(rows)
        cov = media_coverage(latest, anchors)          # 写完之后，被检物就是新索引
        report["media_coverage"] = cov
        with open(REPORT, "w", encoding="utf-8") as fh:
            json.dump(report, fh, ensure_ascii=False, indent=1)
            fh.write("\n")
        print(f"已重建 {INDEX}")
        print(f"  行 {len(cur)} → {len(rows)}   资源 {len(cur_by_res)} → {stats['included_resources']}")
        print(f"  剔除僵尸行 {len(zombie_rows)}（{len(zombie_res)} 个已失效资源）")
        print(f"  图片 OCR 覆盖 {cov['images_present_in_index_via_parent']}/{cov['images_total']}"
              f"（缺 {cov['images_missing_from_index']}）")
        return 0

    print(f"索引体检 [{report['verdict']}]")
    if stale:
        print(f"  陈旧：索引 mtime {idx_mtime:.0f} < 源文件最晚 {newest_src:.0f}")
    if zombie_rows:
        print(f"  虚报：{len(zombie_rows)} 行 / {len(zombie_res)} 个资源已失效却仍在索引内")
    if anchors - cur_anchors:
        print(f"  缺段：{len(anchors - cur_anchors)} 段当前语料有、索引没有")
    if cur_anchors - anchors:
        print(f"  多余：{len(cur_anchors - anchors)} 段索引有、当前语料没有")
    print(f"  图片 OCR 覆盖 {cov['images_present_in_index_via_parent']}/{cov['images_total']}"
          f"（缺 {cov['images_missing_from_index']}）")
    if untracked:
        print(f"  未入台账的文件 {len(untracked)} 个（不判陈旧，仅提示有未登记写入方）：{untracked[:3]}")
    print(f"  重建后行数 {len(cur)} → {len(rows)}")
    return 1 if drift else 0


if __name__ == "__main__":
    sys.exit(main())
