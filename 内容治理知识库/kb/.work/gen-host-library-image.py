#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把**图片 OCR 文本**渲染成宿主条目，落 `2_内部正负样本库/`（追加生成器）。

## 为什么要有这一步（2026-10-09 实测）

与视频那条（`gen-host-library-video.py`）**同一个病**，只是晚了几天才发现：

    hostlib（生成的 md） → 工作台镜像 → workbench.db → kb-serve :4401 → 守衡

守衡读的是 **hostlib**，不是 L6。实测（本轮，10-09）：

| 量 | 实测 |
|---|---|
| 图片 L1 产物（活跃） | **115** 条（另有 36 条在 `_archive`，**不扫**） |
| 图片 OCR 段 | **381** 段 / 0 空段 |
| **`#img.` 锚点在 hostlib** | **0 处** |
| 对照：`#t.` 视频锚点在 hostlib | **170 处**（视频那条 10-08 已补） |
| 抽查 60 段图片 OCR 文本 | hostlib 命中 **37** ／ 未命中 **23**（≈38% 读不到） |

⇒ 图片文字**有一部分**能蹭到 hostlib（当该素材恰好也成了 L4 canonical 的 sample_case），
但**锚点全丢** —— 守衡答得出来也**指不到是哪张图/哪个位置**，而工作流要求
「出报告溯源（L0 层）」，没有 `#img.N` 锚点就没法定位到图。
本脚本按库内既有惯例（**一种形态一个追加生成器**：l4 / product / video / link）补上这一路。

## 归属判据

115 份活跃产物 `kb_type=internal_sample` → `dir_by_type` 映射到 **`2_内部正负样本库`**
（与视频、sample_case 同库）。

## 条目粒度：**一条记录一条**（不是一段一条）

一条 L1 产物 = 一条飞书记录（可含多张图，实测 115 条 / 381 段，均 3.3 张/条）。
按段成条目会灌 381 条碎片、稀释检索；按记录成 **115 条**，每条自带该记录全部图的锚点列表。
**`#素材/<rec>/<field>/#img.N` 锚点逐条保留在正文里** —— 守衡答出来能定位到具体哪张图。

## 刻意**不**渲染记录上下文

`record_context` 里有「具体原因/分析 / 原文反馈 / 建议」等字段，但**本脚本不渲它们**：
① 它们已由 sample_case（`cg-sc-*`）那条路进 hostlib，重复渲染等于灌重复；
② 那里面含 `@人名`，PII 脱敏由 L4 sample_case 那条路统一做（`pii.masked`），
   本脚本再抄一份就等于**绕过脱敏**。只渲 OCR 文本 + 锚点 + 回源直链。

## 写法（照 `-video.py` 的架构，不自创）

复用主生成器的 `frontmatter / insert_kb_class / render_for_chunking / flush_md`
（`flush_md` 走 node 明文落盘 —— 宿主侧 md 有加密代理问题，python 直写会落成读不到的文件）
与 l4 的 `patch_collections / patch_manifest`。

用法（**必须排在主生成器之后**，它往同一份 manifest 里追加）：
    python3 kb/.work/gen-host-library-image.py --out kb/.work/hostlib
    python3 kb/.work/gen-host-library-image.py --out kb/.work/hostlib --dry-run
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import importlib.util
import json
import os
import sys
from datetime import date, timedelta

KB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # …/内容治理/kb
GEN_PATH = os.path.join(KB, ".work", "gen-host-library.py")
L4_PATH = os.path.join(KB, ".work", "gen-host-library-l4.py")
# ★ 只扫这 4 个具名子库 —— `_archive/` 下的 36 份**已退役**产物**不许**进来
L1_DIRS = [os.path.join(KB, "l1", d) for d in
           ("1_外部标准库", "2_内部正负样本库", "3_措辞表达库", "4_产品描述库")]

SUBDIR = "2_内部正负样本库"
COLLECTION = {
    "dir": SUBDIR,
    "name": "内容治理知识库 · 内部正负样本库",
    "display_name": "内部正负样本库",
    "source": "① kb/l1 的 `media_*` 产物里的**图片 OCR 文本**（macOS Vision，锚点 "
              "`#素材/<record>/<field>/#img.N`）；字节在 kb/l0/attachments/",
    "note": "素材**图上文字**（OCR 出的截图/海报/贴片文案）。**只含图上文字，不含画面内容判定** —— "
            "婴幼儿安全、产品用法、隐私等画面风险走「图片安全审查」，不由本条承接。"
            "OCR 可能误识别；案例只作参照，不构成规则。",
}


def _load(mod_name: str, path: str):
    spec = importlib.util.spec_from_file_location(mod_name, path)
    assert spec and spec.loader, f"加载失败：{path}"
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


gen = _load("gen_hostlib", GEN_PATH)
l4 = _load("gen_hostlib_l4", L4_PATH)


def _clickable(ref: str) -> str:
    """把内部 resource_key 变成**能点开的直链**（依据要能定位，用户 2026-10-03 要求）。"""
    if ref.startswith(("http://", "https://")):
        return ref
    tok = ref.split(":", 1)[1] if ":" in ref else ""
    if ref.startswith("wiki:") and tok:
        return f"https://momcozy-in.feishu.cn/wiki/{tok}"
    if ref.startswith("docx:") and tok:
        return f"https://momcozy-in.feishu.cn/docx/{tok}"
    if ref.startswith("sheets:") and tok:
        return f"https://momcozy-in.feishu.cn/sheets/{tok}"
    if ref.startswith("url:"):
        return ref[4:]
    return ref


def collect_images() -> tuple[list[dict], int]:
    """扫 4 个具名 L1 子库的 `media_*` 产物。返回 (有条目的, 被判空跳过的)。"""
    items, blank = [], 0
    for d in L1_DIRS:
        if not os.path.isdir(d):
            continue
        for name in sorted(os.listdir(d)):
            if not (name.startswith("media_") and name.endswith(".json")):
                continue
            p = os.path.join(d, name)
            try:
                rec = json.load(open(p, encoding="utf-8"))
            except Exception:
                continue
            if not isinstance(rec, dict):
                continue
            segs = [s for s in (rec.get("segments") or []) if (s.get("text") or "").strip()]
            if not segs:
                blank += 1          # 认不出来就跳过（不造空条目、不许编文本）
                continue
            items.append({"artifact": rec, "segments": segs})
    return items, blank


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, help="宿主库根目录（主生成器的 --out）")
    ap.add_argument("--today", default=date.today().isoformat())
    ap.add_argument("--half-life-days", type=int, default=180)
    ap.add_argument("--dry-run", action="store_true", help="只报体量，不写任何文件")
    args = ap.parse_args()
    out_root = os.path.abspath(args.out)
    if not os.path.isdir(out_root):
        print(f"[image] 输出根不存在：{out_root}（必须先跑主生成器）")
        return 2

    items, blank = collect_images()
    n_seg = sum(len(i["segments"]) for i in items)
    n_chr = sum(sum(len(s["text"]) for s in i["segments"]) for i in items)
    print(f"[image] 源：活跃 media_* 产物 {len(items)} 条 / OCR 段 {n_seg} 段 / {n_chr} 字"
          f"（空文本跳过 {blank} 条）")
    if args.dry_run:
        print(f"[image] 【干跑】将产出 {len(items)} 条 → {SUBDIR}/L1-facts，不写盘")
        return 0

    payload: list[dict] = []
    manifest_docs: list[dict] = []
    counts: dict[str, int] = collections.Counter()
    per_collection: dict[str, int] = collections.Counter()

    for item in items:
        rec, segs = item["artifact"], item["segments"]
        rk = rec.get("resource_key") or rec.get("resource_id") or ""
        src = rec.get("source") or {}
        rid = src.get("record_id") or rec.get("resource_id") or ""
        table_name = src.get("table_name") or "（未登记表名）"
        field_name = src.get("field_name") or "（未登记字段）"
        entry_url = src.get("entry_url") or _clickable(str(rec.get("l0_parent_resource_key") or ""))
        chars = sum(len(s["text"]) for s in segs)

        # id 确定性：同一 resource_key 永远同一个 id
        img_id = "cg-img-" + hashlib.sha256(str(rk).encode()).hexdigest()[:16]

        lines = [f"# 图片文字：{table_name} · {field_name}", "",
                 f"- 所属记录：{rid}",
                 f"- L0 记录直链（点开核对逐字原文）：{entry_url}",
                 f"- 表 / 字段：`{table_name}` / `{field_name}`",
                 f"- 图片数 {len(segs)} ｜ 图上文字 {chars} 字 ｜ OCR `{rec.get('ocr_version')}`",
                 f"- 观察时间：`{rec.get('observed_at')}`",
                 "",
                 "## 图上文字（逐图，锚点可回源）", ""]
        for s in segs:
            t = " ".join((s.get("text") or "").split())
            lines.append(f"- `{s.get('anchor')}`　{t}")
        lines += ["", "> 以上是**图上文字（OCR）**。OCR 可能误识别（中英混排/艺术字尤甚）；",
                  "> **本条不含画面内容判定** —— 婴幼儿安全、产品用法、隐私等画面风险走「图片安全审查」。",
                  "> 案例只作参照，不构成规则。"]
        body = "\n".join(lines)

        meta = {
            "id": img_id,
            "title": f"[IMG-{rid[-8:] or img_id[-8:]}] 图片文字：{table_name}·{field_name}",
            "collection": SUBDIR,
            "tier": "L1",
            "topic": rid[-12:] or str(rk)[-12:],
            "kind": "fact",
            "summary": (f"{table_name} 记录 {rid} 的「{field_name}」{len(segs)} 张图 / 图上文字 "
                        f"{chars} 字。用于按 `#img.N` 锚点定位某张图上写了什么。"),
            "owner": "刘华丽",
            "evidence_level": "L1",
            "data_level": "L2",
            "sensitivity_level": "L2",
            "half_life_days": args.half_life_days,
            "created_at": args.today,
            "valid_until": (date.fromisoformat(args.today) + timedelta(days=args.half_life_days)).isoformat(),
            "asks": [
                f"这条素材（{table_name} {rid}）图里写了什么文字",
                "某张图上的文字是什么（按 #img.N 定位）",
                "图上文字与文案 / 口播是否一致",
            ],
            "not_proves": ("只有**图上文字（OCR）** —— **不含画面内容判定**（婴幼儿安全、产品用法、"
                           "隐私等画面风险走「图片安全审查」）；OCR 可能误识别，不能当逐字原文引用；"
                           "不能证明图上文字的时效（素材可能已改版）；不能证明该条已过正式验收；"
                           "不能替代合规/法务意见"),
            "forbidden": ("不许把 OCR 文本当成画面合规结论（未命中≠合规）；不许据本条直接判 BLOCK/PASS；"
                          "不许把派生视图的字段改动当成新库改动（视图不写回）"),
        }
        meta = gen.insert_kb_class(meta, SUBDIR)
        rel = os.path.join(SUBDIR, "L1-facts", f"{meta['id']}.md")
        text = gen.frontmatter(meta) + "\n" + body
        payload.append({"rel": rel, "text": text})
        counts[SUBDIR] += 1
        per_collection[f"{SUBDIR}/L1-facts"] += 1
        raw = text.encode("utf-8")
        manifest_docs.append({
            "id": meta["id"], "collectionId": SUBDIR, "relPath": rel,
            "absPath": os.path.join(out_root, rel), "record": False,
            "title": meta["title"], "sha256": hashlib.sha256(raw).hexdigest(),
            "text": text, "content": gen.render_for_chunking(meta, "\n" + body + "\n"),
            "bytes": len(raw), "entryId": meta["id"], "tier": meta["tier"],
            "kind": meta["kind"], "validUntil": meta["valid_until"],
            "evidenceLevel": meta["evidence_level"], "owner": meta["owner"],
            "metaJson": json.dumps(meta, ensure_ascii=False),
        })

    if not payload:
        print("[image] 没有可渲染的图片 OCR（L1 里没有 media_* 段）⇒ 不写")
        return 0

    gen.flush_md(payload, out_root)
    l4.patch_collections(out_root, [COLLECTION], counts)
    l4.patch_manifest(out_root, [COLLECTION], counts, manifest_docs, per_collection, args.today)
    print(f"[image] 产出：{sum(counts.values())} 条 → {SUBDIR}/L1-facts"
          f"（记录 {len(items)} 条 / 图 {n_seg} 张 / {n_chr} 字）")
    print(f"[image] 输出根：{out_root}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
