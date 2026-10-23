#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""apply_vision_to_l1.py —— 把「每图一次画面读数」写回 L1 媒体文档（append-only 语义）。

输入：`kb/.work/scene_batch.mjs` 产出的 ndjson（每行一张图：file_token + sha256 + 读数）
输出：`kb/l1/2_内部正负样本库/media_<table>_<rid>.json` 里追加 `kind=image_visual` 段
      ＋ `media_refs[].visual` 结构化读数 ＋ 运行清单 `kb/l1/media/vision_<RUN>.manifest.json`

口径（照 `scene.mjs` 的边界）
──────────────────────────────
· 读数**只陈述可见事实**（场景/人物/产品/可见标识/文字脚本/风险线索/看不清），
  不含判定、不含建议 —— 判定归规则层，本层只提供"这张图上有什么"。
· 每段带 `source_sha256`（= 图片字节 sha）⇒ 可回源复算；换模型重跑时同 sha 覆盖、不同 sha 追加。
· 幂等：同一 (anchor, kind, source_sha256) 已存在 ⇒ 不重复写；只补差异。
· 不写 L0、不改 OCR 段。

用法：
  kb/kbpy l8/apply_vision_to_l1.py kb/l1/media/scene_<RUN>.jsonl --run <RUN> [--apply]
"""
import json
import os
import sys
import time

APPLY = "--apply" in sys.argv
if APPLY:
    sys.argv.remove("--apply")
pos = [a for a in sys.argv[1:] if not a.startswith("--")]
SRC = pos[0] if pos else ""
RUN = time.strftime("%Y%m%d-%H%M")
for i, a in enumerate(sys.argv):
    if a == "--run" and i + 1 < len(sys.argv):
        RUN = sys.argv[i + 1]

TABLE_ID = "tbld8qE92YaY38Yz"
L1_DIR = "kb/l1/2_内部正负样本库"
PREFIX = "media_%s_" % TABLE_ID
OUT_MANIFEST = "kb/l1/media/vision_%s.manifest.json" % RUN


def render(scene):
    """读数 → 一段可检索文本（顺序固定，便于 diff 与复核）。"""
    if not scene:
        return ""
    parts = []
    if scene.get("setting"):
        parts.append("场景：%s" % scene["setting"])
    ppl = scene.get("people") or []
    if ppl:
        parts.append("人物：" + "；".join(
            "%s（%s）" % (p.get("kind", ""), p.get("doing", "")) if p.get("doing") else p.get("kind", "")
            for p in ppl))
    prods = scene.get("products") or []
    if prods:
        parts.append("产品：" + "；".join(
            ("%s%s" % (p.get("what", ""), "（在用）" if p.get("in_use") else "")) for p in prods))
    marks = scene.get("visible_marks") or []
    if marks:
        parts.append("可见标识：" + "；".join(marks))
    if scene.get("text_script"):
        parts.append("文字脚本：%s" % scene["text_script"])
    cues = scene.get("risk_cues") or []
    if cues:
        parts.append("风险线索：" + "；".join(cues))
    unclear = scene.get("unclear") or []
    if unclear:
        parts.append("看不清：" + "；".join(unclear))
    return "；".join(parts)


def main():
    if not SRC or not os.path.exists(SRC):
        print("用法：apply_vision_to_l1.py <scene.ndjson> [--run RUN] [--apply]")
        return 2
    rows = []
    for line in open(SRC, encoding="utf-8"):
        if line.strip():
            rows.append(json.loads(line))
    good = [r for r in rows if r.get("ok") and r.get("scene")]
    print("画面读数：%d 行 ｜ 成功 %d ｜ 失败 %d" % (len(rows), len(good), len(rows) - len(good)))

    by_rec = {}
    for r in good:
        by_rec.setdefault(r["record_id"], []).append(r)

    stats = {"docs": 0, "segments_added": 0, "segments_replaced": 0, "images": 0, "skipped": 0}
    docs = {}
    for rid, rs in by_rec.items():
        p = os.path.join(L1_DIR, PREFIX + rid + ".json")
        if not os.path.exists(p):
            print("  ⚠️ 没有 L1 媒体文档：%s（跳过）" % rid)
            stats["skipped"] += len(rs)
            continue
        doc = json.load(open(p, encoding="utf-8"))
        segs = doc.get("segments") or []
        refs = doc.get("media_refs") or []
        for r in rs:
            tok = r["file_token"]
            ref = next((m for m in refs if m.get("file_token") == tok), None)
            if ref is None:
                stats["skipped"] += 1
                continue
            anchor = ref.get("anchor")
            text = render(r["scene"])
            if not text:
                stats["skipped"] += 1
                continue
            sha = r.get("sha256") or ref.get("sha256")
            old = next((s for s in segs if s.get("anchor") == anchor
                        and s.get("kind") == "image_visual"), None)
            seg = {"seg_id": (old or {}).get("seg_id") or ("media_%s_%s#v%s" % (TABLE_ID, rid, ref.get("seq"))),
                   "anchor": anchor, "source_sha256": sha, "kind": "image_visual",
                   "text": text, "char_count": len(text),
                   "model": r.get("model") or "deepseek-flash/scene.mjs",
                   "scene": r["scene"]}
            if old is None:
                segs.append(seg)
                stats["segments_added"] += 1
            elif old.get("source_sha256") != sha or old.get("text") != text:
                old.update(seg)
                stats["segments_replaced"] += 1
            else:
                stats["skipped"] += 1
            ref["visual"] = r["scene"]
            ref["visual_text"] = text
            stats["images"] += 1
        doc["segments"] = segs
        doc["media_refs"] = refs
        doc["segment_count"] = len(segs)
        doc["char_count"] = sum(len(s.get("text") or "") for s in segs)
        doc["vision_version"] = "scene.mjs/deepseek-flash"
        doc["vision_observed_at"] = RUN
        docs[rid] = doc
        stats["docs"] += 1

    print("待写文档 %d ｜ 段 +%d / 覆盖 %d / 替换 %d / 跳过 %d"
          % (stats["docs"], stats["segments_added"], stats["images"],
             stats["segments_replaced"], stats["skipped"]))
    if not APPLY:
        print("[dry-run] 加 --apply 才写回 L1")
        return 0
    for rid, doc in docs.items():
        p = os.path.join(L1_DIR, PREFIX + rid + ".json")
        json.dump(doc, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump({"run": RUN, "at": time.strftime("%Y-%m-%d %H:%M:%S"), "source": SRC,
               "rows": len(rows), "ok": len(good), "failed": len(rows) - len(good),
               "stats": stats, "model": "deepseek-flash/scene.mjs",
               "policy": "画面读数只陈述可见事实；不判合规、不给建议；锚点+图片 sha 可回源"},
              open(OUT_MANIFEST, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("已写 %d 份媒体文档 + %s" % (len(docs), OUT_MANIFEST))
    return 0


if __name__ == "__main__":
    sys.exit(main())
