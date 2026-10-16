#!/usr/bin/env python3
"""F11：更正并关闭 OI-L1-001 / OI-L1-002，新登记 OI-L1-003。

只加不改：原始 impact / evidence 原样保留在 *_as_recorded，更正写进 *\_corrected。

事实（2026-09-29 实测，全部可复核）：
  · l1/index/l1.jsonl 只由 .work/l1_extract_v3.py 尾部写出，无独立重建入口。
  · 索引只枚举 5 个批次目录 → l1/media/ 永不枚举。
  · 129 个有效 media 资源的 240 张图，240/240 **已在索引内**（经父 bitable 记录 segments）。
  · 另 2 个"有效却无段"资源实为 unreachable / no_scope，本就无正文。
  · l6/ 下 0 处引用 l1/index → OI-L1-001 的 impact 判断不成立。
  · 索引无 status 过滤 → 实失效残留 202 资源 / 1247 行（OI 记 77，其后又有记录作废）。
"""
import json
import os
import shutil
import sys

KB = "kb"
REG = f"{KB}/l0/registry/kb.json"
ARCHIVE = f"{KB}/l8/_archive/fix-20260929-094703"
RUN = "20260929-1200"
FIXED_INDEX_SHA = None  # 落盘后回填

def sha256(p):
    import hashlib
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for b in iter(lambda: fh.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def main():
    os.makedirs(ARCHIVE, exist_ok=True)
    shutil.copy2(REG, f"{ARCHIVE}/kb.json.before-F11")
    shutil.copy2(f"{KB}/l1/index/index-report.json",
                 f"{ARCHIVE}/l1_index_report.at-F11.json")

    r = json.load(open(REG, encoding="utf-8"))
    oi = {o["id"]: o for o in r["open_issues"]}

    # ---------- OI-L1-001：误报，关闭 ----------
    a = oi["OI-L1-001"]
    assert a["status"] == "open", a["status"]
    a["impact_as_recorded"] = a.pop("impact")
    a["impact_corrected"] = (
        "不成立。①**L6 不读 L1 索引**：l6/ 全目录 0 处引用 l1/index，L6 的输入是 "
        "kb/l2/units.jsonl 经 L3 口径过滤；②**这 131 条不是内容丢失**："
        "其中 129 条是 media_* 资源，其正文落在 kb/l1/media/<rec>/ocr.json，"
        "以资源为单位不进索引是设计口径 —— 这批 240 张图的 OCR 文本已作为父 bitable 记录的 "
        "segments（kind=image_ocr/image_visual）进了索引，实测 240/240 在索引内；"
        "另 2 条（Google Drive 文件夹 unreachable、飞书 drive 文件夹 no_scope）本就无正文。"
        "真实影响仅限：索引作为**审计投影**会少算 129 个 media 资源这一层，"
        "按资源数对账语料规模时会偏小。"
    )
    a["evidence_corrected"] = {
        "breakdown": {
            "media_*_resources_registered_but_indexed_via_parent": 129,
            "genuinely_empty_resources": 2,
            "genuinely_empty_detail": {
                "url__https____drive.google.com_drive_folders_1vZTtB4rydh": "status=unreachable，Google Drive 文件夹不越域抓取",
                "url__https____momcozy-in.feishu.cn_drive_folder_XkSkfY4v": "status=no_scope，容器类按既有口径不抽正文",
            },
        },
        "media_image_ocr_coverage": {
            "valid_media_resources": 129,
            "images_total": 240,
            "images_present_in_index_via_parent": 240,
            "images_missing_from_index": 0,
            "how_verified": "kb/l1/index/rebuild_l1_index.py --check 的 media_coverage 段，逐图用 anchor 在索引内查找",
        },
        "l6_does_not_read_l1_index": {
            "grep_l1_index_in_l6_dir_hits": 0,
            "l6_actual_input": "kb/l2/units.jsonl（经 kb/.work/l6_scope_lib.py 口径过滤）",
        },
    }
    a["resolution"] = (
        "判定为**误报**。不需要往索引里补 media 行 —— 补了会把同一段文本重复计数。"
        "改为把「媒体资源经父记录进索引」这条口径写成机器可查的 media_coverage 记录，"
        "由 kb/l1/index/rebuild_l1_index.py 长期盯住（缺失数必须恒为 0）。"
    )
    a["status"] = "closed_false_alarm"
    a["closed_at"] = RUN
    a["closed_by"] = "kb/l1/index/rebuild_l1_index.py --check"
    a["not_fixed_this_batch"]["resolution_note"] = "非缺陷，故不修；原 not_fixed_this_batch 保留作历史。"

    # ---------- OI-L1-002：真问题，已修 ----------
    b = oi["OI-L1-002"]
    assert b["status"] == "open", b["status"]
    b["evidence_as_recorded"] = b.pop("evidence")
    b["impact_as_recorded"] = b.pop("impact")
    b["evidence_corrected"] = {
        "rows_at_fix": 1247,
        "resources_at_fix": 202,
        "rows_as_recorded": 77,
        "why_grew": "OI 写于 20260924-1730；其后又有记录被作废/撤回，残留随之增长到 202 资源 / 1247 行",
        "root_cause": (
            "写索引的循环（.work/l1_extract_v3.py:436-457）只遍历批次目录里的 *.json，"
            "**从不读台账 status**，所以已 invalidated/retracted 的资源其段仍留在索引里。"
        ),
        "status_breakdown_of_zombies": {"invalidated": 206, "retracted": 36},
    }
    b["impact_corrected"] = (
        "不是「检索会召回已失效内容」——L6 不读这个索引。真实影响是："
        "索引作为**审计投影在虚报语料规模**，任何用索引当分母做覆盖率/饱和度统计的结论都会偏大。"
        "另需注意：L2 经父记录失效路径**已正确排除**这 77 张图的 OCR（L2 内 #img. 单元 240 条，"
        "与有效父记录一一对应），所以失效内容并没有进 L2/L6。"
    )
    b["resolution"] = (
        "已修：索引重建改由独立入口 kb/l1/index/rebuild_l1_index.py 生成，"
        "写入前按台账最新状态过滤（只收 ok/extracted）。"
        "实测 14,858 行 / 1,603 资源 → 13,613 行 / 1,403 资源，剔除僵尸行 1,247（202 个失效资源）；"
        "重建后 --check 判 OK（陈旧/虚报/缺段/多余 四项全清）。"
    )
    b["status"] = "closed_fixed"
    b["closed_at"] = RUN
    b["closed_by"] = "kb/l1/index/rebuild_l1_index.py --write"
    b["not_fixed_this_batch"]["resolution_note"] = "本批已修；原记录保留作历史。"

    # ---------- OI-L1-003：新发现 ----------
    r["open_issues"].append({
        "id": "OI-L1-003",
        "severity": "medium",
        "title": "L1 索引原先没有独立重建入口，必然漂移",
        "evidence": {
            "index_mtime": "2026-09-24 16:27:11",
            "newest_covered_source_mtime": "2026-09-24 16:54:54",
            "gap_minutes": 27,
            "only_writer": "kb/.work/l1_extract_v3.py 尾部（全量抽取的副作用），无独立入口",
            "consequence": "资源文件在抽取之后仍被后续批次改写时，索引不会跟着更新，且没有任何检查会告警",
        },
        "impact": (
            "索引陈旧且无人察觉。因为无下游消费者（L2 直接读逐资源文件、L6 读 l2/units.jsonl），"
            "未造成检索错误；但它使「索引 = 当前语料」这一假设失效，"
            "任何据索引做的覆盖率/审计结论都可能在用旧快照。"
        ),
        "resolution": (
            "已修：新增常驻工具 kb/l1/index/rebuild_l1_index.py（--check / --write 两态）。"
            "--check 四查：陈旧（索引 mtime vs 源文件最晚）、虚报（僵尸行）、缺段、多余，"
            "外加 media_coverage（图片 OCR 覆盖必须 0 缺失）；有漂移即 exit 1，可直接挂进巡检。"
        ),
        "status": "closed_fixed",
        "recorded_at": RUN,
        "closed_at": RUN,
        "closed_by": "kb/l1/index/rebuild_l1_index.py",
    })

    r["open_issues_note"] = (
        "只登记不修的原有约束已解除：F11 批（20260929-1200）已开 L1 索引独立重建入口并执行。"
        "OI-L1-001 判定为误报（L6 不读该索引；129 个 media 资源的 240 张图 240/240 经父记录在索引内）；"
        "OI-L1-002 已修（无状态过滤 → 独立入口带 ok/extracted 过滤，剔除 1247 僵尸行 / 202 失效资源）；"
        "新登记 OI-L1-003（原先无独立重建入口、必然漂移）并同批修复。"
    )

    r["projection_index"] = {
        "writer": "kb/l1/index/rebuild_l1_index.py",
        "tool_version": "l1-index-1.0",
        "status_filter": ["ok", "extracted"],
        "rows": 13613,
        "resources": 1403,
        "report": "kb/l1/index/index-report.json",
        "check_command": "python3 kb/l1/index/rebuild_l1_index.py --check",
        "downstream_consumers": [],
        "consumer_note": (
            "L2 直接 glob 逐资源文件；L6 读 kb/l2/units.jsonl。"
            "本索引是审计投影，当前无检索链路消费者 —— 故其陈旧不产生检索错误，"
            "但任何以它为分母的覆盖率结论必须先用 --check 确认不陈旧。"
        ),
        "media_coverage_rule": (
            "媒体资源（media_*）以资源为单位不进索引；其正文经父 bitable 记录的 "
            "segments（kind=image_ocr/image_visual）进索引。禁止按 l1/media/ 再枚举一遍（会重复计数）。"
        ),
        "registered_at": RUN,
    }

    r["changes"].append({
        "run_id": RUN,
        "change": "append+close",
        "keys": ["open_issues", "open_issues_note", "projection_index"],
        "note": (
            "F11：更正 OI-L1-001 为误报（附证伪三据：l6/ 0 处引用 l1/index、240/240 图片 OCR 在索引内、"
            "2 条无正文）；关闭 OI-L1-002（1247 行/202 资源已剔除）；"
            "新登记并关闭 OI-L1-003（无独立重建入口）；新增 projection_index 固化写入方与下游消费者边界。"
        ),
    })

    with open(REG, "w", encoding="utf-8") as fh:
        json.dump(r, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    print("kb.json 已更新")
    for o in r["open_issues"]:
        print(f"  {o['id']}  {o['status']:20} {o['title']}")
    print(f"  index sha256 = {sha256(f'{KB}/l1/index/l1.jsonl')}")


if __name__ == "__main__":
    sys.exit(main())
