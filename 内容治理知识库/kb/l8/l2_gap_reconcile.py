#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""l2_gap_reconcile.py —— 「L1 有正文、L2 找不到单元」逐条对账（只读）

背景：kb/l7/scripts/l2_gate.py 只在说明项里报一句「滞后 N 个资源未切分」，
      不说是谁、为什么。而 L2 层主引擎 l8/l2_split_run.py 的干跑会把这些
      资源判成「元数据闭合」并报「将追加 0 行」—— 于是缺口在两层工具里
      互相看不见，人要一条条翻台账才能定位。本脚本把这条对账做成可复跑的一条命令。

判据（三段，全部只读）：
  M1 门控滞后  ：l2_gate 的 N2 口径 —— 当前输入集里没有 split/skipped 结论的资源
  M2 引擎缺口  ：l2_split_run 的 gap 口径 —— 正文 sha 不在任何既有单元里
  M3 未读子资源：容器记录的正文落在子资源上，而该子资源 L1 就没读到正文

输出：每条缺口 → 资源 id / 表 / 正文字符数 / 归属原因 / 证据（字段名、子资源、sha）

用法：
  kbpy l8/l2_gap_reconcile.py            # 人读报告
  kbpy l8/l2_gap_reconcile.py --json     # 机器读（stdout 一个 JSON）

本脚本不写任何文件、不改台账。修复动作走 kb-repair，不在这里。
"""
import collections
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
L0, L1, L2 = (os.path.join(ROOT, x) for x in ("kb/l0", "kb/l1", "kb/l2"))
AS_JSON = "--json" in sys.argv
L1_HAS_CONTENT = ("ok", "extracted")          # 与 l2_gate.py 同口径
# 附件子资源：OCR 文本已并入父记录的 sample 单元，不再单独发单元
ATTACH_OK = "merged_into_parent_sample"


def iter_jsonl(path):
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            try:
                yield json.loads(line)
            except Exception:
                continue


def load_artifacts():
    """与 l2_split_run.py 同口径：只收「数字开头子目录」下的 <resource_id>.json。"""
    art = {}
    for d in sorted(os.listdir(L1)):
        dp = os.path.join(L1, d)
        if not (os.path.isdir(dp) and d[:1].isdigit()):
            continue
        for f in sorted(os.listdir(dp)):
            if not f.endswith(".json"):
                continue
            try:
                with open(os.path.join(dp, f), encoding="utf-8") as fh:
                    art[f[:-5]] = json.load(fh)
            except Exception:
                continue
    return art


def table_of(artifact, rid):
    src = artifact.get("source") or {}
    if src.get("table_name"):
        return src["table_name"]
    return rid.split("__")[1] if rid.count("__") >= 2 else None


def link_target(url):
    """飞书链接 → 子资源 id。表内 Base 链接（/base/）与站外链接（Google 等）不算可读子资源。"""
    url = url or ""
    m = re.search(r"/(slides|wiki|docx|sheets|file)/([A-Za-z0-9]+)", url)
    if m:
        return f"{m.group(1)}__{m.group(2)}"
    if "/drive/folder/" in url or "/base/" in url:
        return None                      # 文件夹/表内链接，不是可读内容资源
    if re.search(r"https?://[^\s)]+", url) and "feishu" not in url:
        return "EXTERNAL"                # 站外（Google Drive/Docs 等），本库无读取通道
    return None


def main():
    reg = json.load(open(os.path.join(L0, "registry/kb.json"), encoding="utf-8"))
    field_roles = reg.get("field_roles") or {}
    overrides = reg.get("field_role_table_overrides") or {}

    l1_rows = list(iter_jsonl(os.path.join(L1, "manifest_l1.jsonl")))
    l2_rows = [d for d in iter_jsonl(os.path.join(L2, "manifest_l2.jsonl")) if d]
    units = list(iter_jsonl(os.path.join(L2, "units.jsonl")))
    art = load_artifacts()

    # 与 L2 引擎一致：同一 resource_id 取文件顺序最后一行
    lat = {}
    for r in l1_rows:
        lat[r.get("resource_id")] = r
    unit_sha = collections.defaultdict(set)
    for u in units:
        unit_sha[u.get("resource_id")].add(u.get("source_sha256"))
    l2_latest = {}
    for d in l2_rows:
        l2_latest[d.get("resource_id")] = d

    out = {"counts": {}, "by_cause": {}, "items": []}

    # ---------- M1：门控滞后（l2_gate N2 口径） ----------
    l0_valid = {d.get("resource_key") for d in iter_jsonl(os.path.join(L0, "manifest.jsonl"))
                if d.get("status") not in ("gone", "retracted")}
    l1_by_key = {d["resource_key"]: d for d in l1_rows if d.get("resource_key")}
    in_scope = [k for k in l0_valid
                if k in l1_by_key and l1_by_key[k].get("status") in L1_HAS_CONTENT]
    lag = [l1_by_key[k] for k in in_scope
           if (l2_latest.get(l1_by_key[k].get("resource_id")) or {}).get("result")
           not in ("split", "skipped")]

    # ---------- M2：引擎缺口（l2_split_run gap 口径） ----------
    engine_gap = [rid for rid, o in art.items()
                  if o.get("segments")
                  and lat.get(rid, {}).get("status") not in ("invalidated", "retracted")
                  and o.get("source_sha256") not in unit_sha.get(rid, set())]

    # ---------- M3：容器记录 → 子资源未读到正文 ----------
    def classify(rid):
        o = art.get(rid) or {}
        led = lat.get(rid) or {}
        segs = o.get("segments") or []
        fields = []
        for s in segs:
            if s.get("kind") == "field_value":
                fn = s.get("field_name")
                fields.append({"field": fn,
                               "role": overrides.get(f"{table_of(o, rid)}::{fn}",
                                                     field_roles.get(fn))})
        # ① 附件子资源：OCR 已并入父记录
        if "_fld" in rid:
            return "attachment_merged_into_parent", None
        # ② 容器记录：正文落在子资源上
        link = next((s.get("text") for s in segs if s.get("field_name") == "材料链接"), None)
        tgt = link_target(link)
        if tgt == "EXTERNAL":
            return "external_link_unreadable", {"link": (link or "")[:200],
                                                "why": "站外链接（Google Drive/Docs 等），本库没有读取通道"}
        if tgt:
            to = art.get(tgt) or {}
            if not to.get("segments"):
                return "container_child_unreadable", {
                    "child": tgt,
                    "child_l1_status": (lat.get(tgt) or {}).get("status"),
                    "child_reason": ((lat.get(tgt) or {}).get("status_reason") or "")[:160]}
        # ③ 全字段无内容角色 → 被切分器整体丢弃
        if fields and all(f["role"] != "content" for f in fields):
            return ("field_role_unknown" if any(f["role"] is None for f in fields)
                    else "field_role_non_content"), {"fields": fields}
        return "unknown", {"fields": fields,
                           "l2_result": (l2_latest.get(rid) or {}).get("result"),
                           "l2_reason": ((l2_latest.get(rid) or {}).get("status_reason") or "")[:160],
                           "ledger_obs": led.get("observed_at")}

    seen = set()
    for rid in sorted(set(engine_gap) | {r["resource_id"] for r in lag}):
        o = art.get(rid) or {}
        led = lat.get(rid) or {}
        cause, ev = classify(rid)
        if cause == "attachment_merged_into_parent" and rid not in engine_gap:
            seen.add(rid)
            out["by_cause"][cause] = out["by_cause"].get(cause, 0) + 1
            continue                                    # 设计如此，不进明细
        seen.add(rid)
        out["by_cause"][cause] = out["by_cause"].get(cause, 0) + 1
        out["items"].append({
            "resource_id": rid, "cause": cause,
            "table": table_of(o, rid), "kb_type": o.get("kb_type") or led.get("kb_type"),
            "char_count": led.get("char_count") or o.get("char_count"),
            "segments": len(o.get("segments") or []),
            "source_sha256": o.get("source_sha256"),
            "in_engine_gap": rid in engine_gap,
            "in_gate_lag": any(r["resource_id"] == rid for r in lag),
            "seen_by_l2": bool(l2_latest.get(rid)),
            "evidence": ev})

    out["counts"] = {"l1_registered": len(lat), "l1_artifacts": len(art),
                     "units": len(units), "resources_with_units": len(unit_sha),
                     "in_scope": len(in_scope), "gate_lag": len(lag),
                     "engine_gap": len(engine_gap),
                     "gap_union": len(set(engine_gap) | {r["resource_id"] for r in lag})}

    if AS_JSON:
        print(json.dumps(out, ensure_ascii=False, indent=1, sort_keys=True))
        return

    c = out["counts"]
    print("=" * 74)
    print("L1→L2 缺口对账（只读；判据与 l2_gate / l2_split_run 同口径）")
    print(f"  L1 登记 {c['l1_registered']} ｜ 产物 {c['l1_artifacts']} ｜ 单元 {c['units']} 条 / "
          f"{c['resources_with_units']} 资源")
    print(f"  当前输入集 {c['in_scope']} ｜ 门控滞后 {c['gate_lag']} ｜ 引擎缺口 "
          f"{c['engine_gap']} ｜ 合计 {c['gap_union']}")
    print("-" * 74)
    print("归属原因：")
    for k, v in sorted(out["by_cause"].items(), key=lambda x: -x[1]):
        print(f"   {v:5}  {k}")
    print("-" * 74)
    real = [i for i in out["items"]
            if i["cause"] in ("field_role_unknown", "field_role_non_content",
                              "container_child_unreadable", "unknown")]
    print(f"需要人看的 {len(real)} 条（附件子资源已按设计并入父记录，不列）：")
    for i in real:
        print(f"\n  [{i['cause']}] {i['resource_id']}")
        print(f"      表={i['table']} 类型={i['kb_type']} 正文={i['char_count']}字 "
              f"段={i['segments']} 引擎缺口={i['in_engine_gap']} 门控滞后={i['in_gate_lag']} "
              f"L2见过={i['seen_by_l2']}")
        ev = i["evidence"] or {}
        if ev.get("fields"):
            for f in ev["fields"]:
                print(f"      字段 {f['field']!r} → 角色 {f['role']!r}")
        if ev.get("child"):
            print(f"      子资源 {ev['child']} L1状态={ev['child_l1_status']}")
            print(f"        原因 {ev['child_reason']}")
        if ev.get("link"):
            print(f"      链接 {ev['link']}")
            print(f"        {ev['why']}")
        if ev.get("l2_reason"):
            print(f"      L2 台账结论 {ev.get('l2_result')}：{ev['l2_reason']}")
    print("=" * 74)


if __name__ == "__main__":
    main()
