#!/usr/bin/env python3
"""负面样本表 旧 record_id → 新 record_id 重映射。

背景（2026-10-14 实测）：飞书「负面样本」表（`tbld8qE92YaY38Yz`）被**整体重建**，
174 条现行记录全部是新 ID（`recvw7XIUg…` 等），而本地 L0 的 201 件仍是旧代（`recvw2…`），
**交集为 0** ⇒ 所有引用内部正负样本库条款（S-1.x）的报告，其 L0 飞书直链全部点不开。
**内容没丢**，只是一代 ID 之差，故可重映射。

配对靠**内容指纹**，不靠 ID 顺序（表里存在同素材重复登记，顺序法必然错位）：
  1. 归一化 `原文反馈` 逐字相等
  2. 否则归一化 `具体原因/分析` 逐字相等
  3. 否则 `原文反馈` 相似度 ≥ 0.90（difflib），并列候选全部记录，交人裁

产出 `out/l0_remap_negative_samples.json`：
  { "mapping": {old: new}, "ambiguous": {...}, "unmatched": [...], "stats": {...} }
"""
import json, glob, re, os, difflib, collections

HERE = os.path.dirname(__file__)
ROOT = os.path.abspath(os.path.join(HERE, ".."))
OUT = os.path.join(HERE, "out")
TABLE = "tbld8qE92YaY38Yz"
NDJSON = os.path.join(OUT, "l0probe", f"{TABLE}.ndjson")


def norm(s):
    """归一化：去图片/附件标记、折叠空白 —— 这些 token 在重建时会变，不能参与配对。"""
    s = s or ""
    s = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", s)          # ![Image](img_v3_...)
    s = re.sub(r"<[^>]+>", "", s)
    s = re.sub(r"\s+", "", s)
    return s.strip()


def load_local():
    out = []
    for f in glob.glob(os.path.join(ROOT, "kb/l0/2_内部正负样本库",
                                    f"feishu_bitable_record__{TABLE}__*.json")):
        try:
            d = json.load(open(f))
        except Exception:
            continue
        af = (d.get("extra") or {}).get("all_fields") or {}
        out.append({
            "file": os.path.relpath(f, ROOT),
            "old": d.get("source", {}).get("record_id"),
            "entry_url": d.get("entry_url"),
            "feedback": af.get("原文反馈") or "",
            "analysis": af.get("具体原因/分析") or "",
            "n_img": len(af.get("图片素材") or []),
            "advice": af.get("建议"),
            "submitted": af.get("提交时间"),
        })
    return out


def load_new():
    out = []
    if not os.path.exists(NDJSON):
        raise SystemExit(f"缺 {NDJSON}；先跑 check_l0_backlinks.py 生成")
    for line in open(NDJSON, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        try:
            o = json.loads(line)
        except Exception:
            continue
        out.append({
            "new": o.get("record_id"),
            "feedback": o.get("原文反馈") or "",
            "analysis": o.get("具体原因/分析") or "",
            "n_img": len(o.get("图片素材") or []),
            "advice": o.get("建议"),
            "submitted": o.get("提交时间"),
        })
    return out


def main():
    old = load_local()
    new = load_new()
    print(f"本地旧记录 {len(old)} 条 / 飞书新记录 {len(new)} 条")

    by_fb = collections.defaultdict(list)
    by_an = collections.defaultdict(list)
    for n in new:
        by_fb[norm(n["feedback"])].append(n)
        by_an[norm(n["analysis"])].append(n)

    mapping, ambiguous, unmatched = {}, {}, []
    how = collections.Counter()

    for o in old:
        fb, an = norm(o["feedback"]), norm(o["analysis"])
        cands, method = [], None
        if fb and len(by_fb.get(fb, [])) >= 1:
            cands, method = by_fb[fb], "原文反馈逐字"
        elif an and len(by_an.get(an, [])) >= 1:
            cands, method = by_an[an], "具体原因/分析逐字"
        else:
            # 模糊兜底
            best, score = [], 0.0
            for n in new:
                r = difflib.SequenceMatcher(None, fb or an, norm(n["feedback"]) or norm(n["analysis"])).ratio()
                if r > score:
                    best, score = [n], r
                elif r == score:
                    best.append(n)
            if score >= 0.90:
                cands, method = best, f"模糊 {score:.3f}"

        if not cands:
            unmatched.append({"old": o["old"], "file": o["file"],
                              "feedback_head": o["feedback"][:80]})
            continue
        if len(cands) > 1:
            # 重复登记：优先有图、再有建议的那条，同时把全部候选留档交人裁
            ranked = sorted(cands, key=lambda c: (-c["n_img"], 0 if c["advice"] else 1))
            mapping[o["old"]] = ranked[0]["new"]
            ambiguous[o["old"]] = {
                "picked": ranked[0]["new"],
                "candidates": [{"new": c["new"], "n_img": c["n_img"],
                                "advice": (c["advice"] or "")[:60]} for c in cands],
                "old_file": o["file"],
            }
            how[method + " · 多候选"] += 1
        else:
            mapping[o["old"]] = cands[0]["new"]
            how[method] += 1

    stats = {
        "old_total": len(old), "new_total": len(new),
        "mapped": len(mapping), "ambiguous": len(ambiguous), "unmatched": len(unmatched),
        "by_method": dict(how),
        "new_records_covered": len({v for v in mapping.values()}),
    }
    json.dump({"mapping": mapping, "ambiguous": ambiguous,
               "unmatched": unmatched, "stats": stats},
              open(os.path.join(OUT, "l0_remap_negative_samples.json"), "w"),
              ensure_ascii=False, indent=1)

    print("\n=== 配对结果 ===")
    for k, v in stats.items():
        print(f"   {k}: {v}")
    if unmatched:
        print("\n未配上的（前 8）:")
        for u in unmatched[:8]:
            print(f"   {u['old']}  {u['feedback_head'][:70]}")
    if ambiguous:
        print(f"\n多候选（重复登记）{len(ambiguous)} 条，样例:")
        for k, v in list(ambiguous.items())[:5]:
            print(f"   {k} -> 选 {v['picked']}（候选 {len(v['candidates'])}）")
    print("\n映射已落 -> out/l0_remap_negative_samples.json")


if __name__ == "__main__":
    main()
