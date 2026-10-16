#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把**链接类正文**（飞书内链取原件 PDF / 扫描件 OCR 抽出来的 L1 正文）渲染成宿主条目，
落 `1_外部标准库/`（追加生成器）。

## 为什么要有这一步（2026-10-08，Owner 批准「写链接专用的 hostlib 生成器」）

链路断层（实测）：链接类 36 条飞书内链的正文**合计 10,730,271 字**早已在 L1/L2，
本轮又把其中 20 条补进了 **L6 索引**（4,891 → 5,979 行）。但 **守衡读不到**：

    hostlib（生成的 md） → 工作台镜像 → workbench.db → kb-serve :4401 → 守衡

实测：工作台 `kb_docs` = **1,372**（正是 hostlib 四库之和），这 36 条**一条都不在**。
原因：四个生成器分别读 `l3/candidates/rules.jsonl`（509）、
`l4/canonical/{scoped_clause,sample_case}.jsonl`（375+358）、`l2/units.jsonl`（**仅 product_desc 9 行**）、
以及视频专用 `kb/l1` 的 `video_ocr_segments`（11）—— **没有任何一个读 L1/L2 的「链接正文」**。

## 归属判据

这 36 条的 `kb_type` 实测是 `external_standard`（WHO / PubMed / 术语表 / 监管材料）
⇒ 按主生成器 `dir_by_type` 的口径落 **`1_外部标准库`**。

## ★ 粒度：**按体量切片成多条**，不是「一资源一条」

校准（实测现有 hostlib）：**1,372 条 / 3,863,007 字，中位 2,556，p90 3,859，最大 23,138**。
而本批单资源最大 **2,076,385 字**（是现有最大条目的 90 倍）⇒ 「一资源一条」会把一条巨条目
灌进守衡的索引。因此**按 `--max-chars` 切片**（默认 20,000，贴着现有最大 23,138），
每片自带它的 `#l.a-b` 锚点区间，正文**逐字不截断**（切片边界按行对齐）。

**预期体量（实跑前先报数，不写盘）**：约 535 条 ⇒ hostlib 1,372 → ~1,907 条（+39%）、
3.86M → ~14.6M 字（**3.8 倍**）。⇒ **稀释风险是真的**，所以本脚本**默认干跑**，
且支持 `--only <子串>` 收窄范围；是否全量入守衡由 Owner 定。

用法：
    python3 kb/.work/gen-host-library-link.py --out kb/.work/hostlib            # 干跑报数
    python3 kb/.work/gen-host-library-link.py --out kb/.work/hostlib --apply    # 真写
"""
from __future__ import annotations

import argparse
import collections
import glob
import hashlib
import importlib.util
import json
import os
import sys
from datetime import date, timedelta

KB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GEN_PATH = os.path.join(KB, ".work", "gen-host-library.py")
L4_PATH = os.path.join(KB, ".work", "gen-host-library-l4.py")
L1_DIRS = [os.path.join(KB, "l1", d) for d in
           ("1_外部标准库", "2_内部正负样本库", "3_措辞表达库", "4_产品描述库")]
DEFAULT_SUBDIR = "1_外部标准库"
SUBDIRS = ["1_外部标准库", "2_内部正负样本库", "3_措辞表达库", "4_产品描述库"]
COLLECTION_TMPL = {
    "dir": DEFAULT_SUBDIR,
    "name": "内容治理知识库 · 外部标准库",
    "display_name": "外部标准库",
    "source": "① kb/l1 链接类正文（飞书内链 `wiki +node-get` → `drive +preview --type source_file` "
              "取原件 PDF / 扫描件 OCR；锚点 `#l.起-止`）",
    "note": "外部监管/研究/术语材料的正文。**只作参照与溯源，不构成规则**；"
            "判定仍以 L3 规则 + L4 条款为准。",
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
    if ref.startswith(("http://", "https://")):
        return ref
    tok = ref.split(":", 1)[1] if ":" in ref else ""
    for pre, path in (("wiki:", "wiki"), ("docx:", "docx"), ("sheets:", "sheets")):
        if ref.startswith(pre) and tok:
            return f"https://momcozy-in.feishu.cn/{path}/{tok}"
    if ref.startswith("url:"):
        return ref[4:]
    return ref


TITLES_PATH = os.path.join(KB, "l8", "runs", "20261008-link-titles.json")


def load_titles() -> dict:
    """飞书节点标题（`wiki +node-get` 取回，见 kb/l8/runs/20261008-link-titles.json）。

    为什么必须取：实测这 36 条 L1 产物**全都没有 title**，直接渲染出来守衡只会看到
    `链接正文：(无标题)` —— 等于没入。取不到的（5 个 131006 缺权限节点 + 分享视图）
    回落到 token 尾段，并在正文里标明「标题未取到」。
    """
    try:
        return json.load(open(TITLES_PATH, encoding="utf-8"))
    except Exception:
        return {}


def collect_links(only: str | None, max_source: int | None = None) -> list[dict]:
    """取「链接类且 L1 有正文」的产物。判据窄：source_kind=url + 飞书站内 + char_count>0。"""
    out = []
    for d in L1_DIRS:
        if not os.path.isdir(d):
            continue
        for name in sorted(os.listdir(d)):
            if not (name.startswith("url__") and name.endswith(".json")):
                continue
            p = os.path.join(d, name)
            try:
                rec = json.load(open(p, encoding="utf-8"))
            except Exception:
                continue
            rk = str(rec.get("resource_key") or "")
            if "feishu.cn" not in rk or (rec.get("char_count") or 0) <= 0:
                continue
            if only and only not in rk:
                continue
            if max_source and (rec.get("char_count") or 0) > max_source:
                continue
            rec["_l1_dir"] = os.path.basename(d)
            out.append(rec)
    return out


def slices(segs: list[dict], max_chars: int) -> list[list[dict]]:
    """把段按**行对齐**切成每片 ≤ max_chars（不截断任何一行）。"""
    out, cur, n = [], [], 0
    for s in segs:
        t = s.get("text") or ""
        if cur and n + len(t) > max_chars:
            out.append(cur)
            cur, n = [], 0
        cur.append(s)
        n += len(t)
    if cur:
        out.append(cur)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--apply", action="store_true", help="不给我就只报数、不写盘")
    ap.add_argument("--max-chars", type=int, default=20000,
                    help="单条宿主条目正文上限（默认 20000，贴着现有最大条目 23138 校准）")
    ap.add_argument("--only", default=None, help="按 resource_key 子串收窄范围")
    ap.add_argument("--max-source-chars", type=int, default=None,
                    help="只入「L1 正文字数 ≤ 此值」的资源（Owner 2026-10-08 定：先入 <10 万字的，"
                         "观察守衡检索质量再决大件；不传则不限）")
    ap.add_argument("--today", default=date.today().isoformat())
    ap.add_argument("--half-life-days", type=int, default=180)
    args = ap.parse_args()
    out_root = os.path.abspath(args.out)
    if not os.path.isdir(out_root):
        print(f"[link] 输出根不存在：{out_root}（必须先跑主生成器）")
        return 2

    recs = collect_links(args.only, args.max_source_chars)
    titles = load_titles()
    payload, manifest_docs = [], []
    counts: dict[str, int] = collections.Counter()
    per_collection: dict[str, int] = collections.Counter()
    n_slices = n_chars = 0
    biggest = 0
    for rec in recs:
        rid = rec.get("resource_id") or ""
        rk = str(rec.get("resource_key") or "")
        ref = _clickable(rk)
        _t = titles.get(rk) or {}
        title = str(_t.get("title") or "").strip()
        if not title:
            title = f"（标题未取到）{rk.rsplit('/', 1)[-1][:16]}"
        segs = [s for s in (rec.get("segments") or []) if (s.get("text") or "").strip()]
        if not segs:
            continue
        parts = slices(segs, args.max_chars)
        for i, part in enumerate(parts, 1):
            a0 = part[0].get("anchor") or "?"
            a1 = part[-1].get("anchor") or "?"
            body_text = "\n".join((s.get("text") or "") for s in part)
            n_slices += 1
            n_chars += len(body_text)
            biggest = max(biggest, len(body_text))
            lid = "cg-lnk-" + hashlib.sha256(f"{rid}|{i}".encode()).hexdigest()[:16]
            head = [f"# 链接正文：{title}", "",
                    f"- 来源地址：{ref}",
                    f"- 锚点区间：`{a0}` ~ `{a1}`",
                    f"- 本片 {len(part)} 段 / {len(body_text)} 字；全篇 {len(parts)} 片 / "
                    f"{rec.get('char_count') or 0} 字",
                    f"- 抽取方式：`{rec.get('extractor_version')}`",
                    "",
                    "## 正文（逐字，锚点可回源）", ""]
            body = "\n".join(head) + "\n" + body_text
            meta = {
                "id": lid,
                "title": f"[LNK-{rid[-8:]}-{i:03d}] 链接正文：{title}"[:180],
                "collection": rec.get("_l1_dir") or DEFAULT_SUBDIR, "tier": "L1",
                "topic": rid[-12:] or "link", "kind": "fact",
                "summary": (f"外部链接《{title}》正文第 {i}/{len(parts)} 片，{len(body_text)} 字"
                            f"（锚点 {a0} ~ {a1}）。用于按锚点定位外部材料原文。"),
                "owner": "刘华丽", "evidence_level": "L1", "data_level": "L2",
                "sensitivity_level": "L2", "half_life_days": args.half_life_days,
                "created_at": args.today,
                "valid_until": (date.fromisoformat(args.today)
                                + timedelta(days=args.half_life_days)).isoformat(),
                "asks": [f"《{title}》里关于某个主题是怎么写的",
                         "这条外部材料的原文与出处是什么",
                         "某个锚点区间（如 #l.120-140）对应哪段原文"],
                "not_proves": ("只是**外部材料的原文**，不能证明 Momcozy 的文案合规；"
                               "不能替代 L3 规则 / L4 条款的判定；不能证明该材料仍然现行有效"
                               "（外部页面可能已改版）；不能证明本片之外的上下文（切片有边界）"),
                "forbidden": ("不许把外部材料原文当成自家规则引用；不许据本条直接判 BLOCK；"
                              "不许跨片拼接当作完整原文（本片有锚点区间，回源请按锚点取）；"
                              "不许把派生视图的字段改动当成新库改动（视图不写回）"),
            }
            subdir = rec.get("_l1_dir") or DEFAULT_SUBDIR
            meta = gen.insert_kb_class(meta, subdir)
            rel = os.path.join(subdir, "L1-facts", f"{meta['id']}.md")
            text = gen.frontmatter(meta) + "\n" + body
            payload.append({"rel": rel, "text": text})
            counts[subdir] += 1
            per_collection[f"{subdir}/L1-facts"] += 1
            raw = text.encode("utf-8")
            manifest_docs.append({
                "id": meta["id"], "collectionId": subdir, "relPath": rel,
                "absPath": os.path.join(out_root, rel), "record": False,
                "title": meta["title"], "sha256": hashlib.sha256(raw).hexdigest(),
                "text": text, "content": gen.render_for_chunking(meta, "\n" + body + "\n"),
                "bytes": len(raw), "entryId": meta["id"], "tier": meta["tier"],
                "kind": meta["kind"], "validUntil": meta["valid_until"],
                "evidenceLevel": meta["evidence_level"], "owner": meta["owner"],
                "metaJson": json.dumps(meta, ensure_ascii=False),
            })

    # 现有体量（校准口径：manifest.json 的 docs）
    mp = os.path.join(out_root, "_meta", "manifest.json")
    try:
        prev = json.load(open(mp, encoding="utf-8")).get("docs") or []
    except Exception:
        prev = []
    prev_chars = sum(len(x.get("text") or "") for x in prev)
    _f = []
    if args.only:
        _f.append("--only " + args.only)
    if args.max_source_chars:
        _f.append(f"正文字数 ≤ {args.max_source_chars:,}")
    print(f"[link] 源：链接类且 L1 有正文的产物 {len(recs)} 条"
          f"{'（' + '；'.join(_f) + '）' if _f else ''}")
    print(f"[link] 切片：{n_slices} 条宿主条目 / {n_chars:,} 字"
          f"（单条上限 {args.max_chars:,}；实测最大条 {biggest:,} 字）")
    print(f"[link] 体量对照：hostlib 现有 {len(prev)} 条 / {prev_chars:,} 字"
          f" ⇒ 追加后 {len(prev)+n_slices} 条 / {prev_chars+n_chars:,} 字"
          f"（字数 ×{(prev_chars+n_chars)/max(1,prev_chars):.2f}）")
    if not args.apply:
        print("[link] 【干跑】未写盘。加 --apply 才落 hostlib（再跑 publish.sh 才会到守衡）")
        return 0
    if not payload:
        print("[link] 无可渲染内容 ⇒ 不写")
        return 0
    gen.flush_md(payload, out_root)
    colls = [dict(COLLECTION_TMPL, dir=sd, display_name=sd,
                  name=f"内容治理知识库 · {sd.split('_', 1)[-1]}") for sd in SUBDIRS]
    l4.patch_collections(out_root, colls, counts)
    l4.patch_manifest(out_root, colls, counts, manifest_docs, per_collection, args.today)
    print(f"[link] 已写入 {sum(counts.values())} 条 → 落位 {dict(counts)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
