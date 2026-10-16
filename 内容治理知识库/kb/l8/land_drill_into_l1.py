#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""land_drill_into_l1.py —— 把**下钻产物**接进 L1（产物 + 台账），使它能被 L2 切分。

## 为什么需要它（2026-10-10 实测）

`kb/l8/drill_links_2levels.py` 的下钻产物落在 `kb/l1/sources/<run>.{md,jsonl,report.json}`，
而 **L2 的唯一输入口是 `kb/l1/manifest_l1.jsonl` + `kb/l1/<数字目录>/<rid>.json`**：

    l2_split_run.py:67   ART[<rid>] = json.load(kb/l1/<d>/*.json)   # 只扫**数字开头**的目录
    l2_split_run.py:69   E = [rid for rid,o in ART.items() if o.get("segments") and 台账 status 非 dead]

⇒ `kb/l1/sources/` 既不在数字目录里、也不是那份 `.json` 形状 ⇒ **下钻产物从来没进过 L1 台账**
（历史 20260929-1100 那 74 条边同样没进）。**它是侧信道**：只喂派生视图（`kb/.work/gen-host-library.py`），
不进供给链 —— 所以「取它索引的真资料」拿到了资料，却**蒸不成规则**。

本引擎补的就是这一段接线：**下钻产物 → L1 产物 + L1 台账行**，此后 L2 自然能切。

## 纪律

1. **只追加**：台账是 append-only，本引擎**只追加** manifest 行，绝不改写历史行。
2. **不碰 L0**：与下钻引擎同一条口径（`l0_untouched`）。
3. **幂等**：同一 `resource_id` 已在台账里 ⇒ 跳过（`--apply` 重跑不重复追加）。
4. **只落 `status=="ok"` 的 level-1 边** —— 失败件里装的是报错正文（见下钻引擎的说明），
   **不许**把报错当正文落库。
5. `--apply` 才落盘；不带则只打印将追加多少。

用法：
    python3 kb/l8/land_drill_into_l1.py <drill_run_id> [--apply]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
L1 = os.path.join(ROOT, "kb/l1")
SRC = os.path.join(L1, "sources")
SUBLIB = "1_外部标准库"          # 外部标准库：外部 URL 落这里（与既有 url__ 产物一致）
EXTRACTOR_VERSION = "drill-land-0.1"
KB_TYPE = "external_standard"


def sanitize(url: str) -> str:
    """URL → `resource_id`。确定性、可复算、不含路径分隔符。"""
    body = re.sub(r"^https?://", "", url.strip())
    return "url__" + re.sub(r"[^A-Za-z0-9.]+", "_", body).strip("_")


def strip_front(text: str) -> str:
    """去掉下钻产物头部的 YAML front-matter（`---\\n…\\n---\\n\\n`），只留正文。"""
    if text.startswith("---\n"):
        i = text.find("\n---\n", 4)
        if i != -1:
            return text[i + 5:].lstrip("\n")
    return text


def sha(t: str) -> str:
    return hashlib.sha256(t.encode("utf-8")).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(description="把下钻产物接进 L1（产物 + 台账）")
    ap.add_argument("run")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    edges_p = os.path.join(SRC, f"{a.run}.jsonl")
    if not os.path.exists(edges_p):
        print("找不到边表：%s" % edges_p)
        return 2
    edges = [json.loads(l) for l in open(edges_p, encoding="utf-8") if l.strip()]
    lvl1 = [e for e in edges if e.get("depth") == 1]
    ok = [e for e in lvl1 if e.get("status") == "ok"]
    print(f"[落地] 边 {len(edges)}｜level-1 {len(lvl1)}｜可落（status=ok）{len(ok)}")

    man_p = os.path.join(L1, "manifest_l1.jsonl")
    have = set()
    if os.path.exists(man_p):
        for l in open(man_p, encoding="utf-8"):
            if l.strip():
                try:
                    have.add(json.loads(l)["resource_id"])
                except Exception:                       # noqa: BLE001
                    pass

    outdir = os.path.join(L1, SUBLIB)
    todo, skipped = [], []
    for e in ok:
        rid = sanitize(e["url"])
        if rid in have:
            skipped.append((rid, "台账已有"))
            continue
        ap_ = e.get("artifact")
        p = os.path.join(ROOT, ap_) if ap_ and not os.path.isabs(ap_) else ap_
        if not p or not os.path.exists(p):
            skipped.append((rid, "产物缺失"))
            continue
        text = strip_front(open(p, encoding="utf-8", errors="replace").read()).strip()
        if len(text) < 200:
            skipped.append((rid, f"正文仅 {len(text)} 字节"))
            continue
        todo.append((e, rid, text))

    print(f"  将落 {len(todo)} 条｜跳过 {len(skipped)} 条")
    for rid, why in skipped[:8]:
        print(f"    跳过 {rid[:56]} —— {why}")
    if not a.apply:
        for e, rid, text in todo[:5]:
            print(f"    · {rid[:60]}  {len(text):>9} 字节  ← {e['url'][:60]}")
        print("\n  [干跑] 未落盘（kb/l1 一字未动）。加 --apply 才写。")
        return 0

    os.makedirs(outdir, exist_ok=True)
    n_art = n_man = 0
    with open(man_p, "a", encoding="utf-8") as mfh:
        for e, rid, text in todo:
            h = sha(text)
            doc = {
                "resource_id": rid,
                "resource_key": rid,
                "kb_type": KB_TYPE,
                "anchor_kind": "text",
                "anchor_spec": "#正文",
                "extractor_version": EXTRACTOR_VERSION,
                "source_kind": "drill_link",
                "source": {"url": e["url"], "from_record": e.get("from_id"),
                           "from_table": e.get("from_table"), "field": e.get("label"),
                           "drill_run": a.run},
                # 溯源：一路回到记录与下钻边（不编）
                "l0_path": None,
                "l0_depth": None,
                "l0_matched_rule": None,
                "observed_at": e.get("observed_at") or a.run,
                "status": "ok",
                "status_reason": "由 drill_links_2levels 下钻取得正文后落地",
                "source_sha256": h,
                "char_count": len(text),
                "segment_count": 1,
                "segments": [{"anchor": "#正文", "kind": "paragraph", "text": text}],
                "media_count": 0, "media_refs": [], "table_count": 0, "tables": [],
                "pdf_local_path": None, "pdf_pages": None, "untruncated_from": None,
            }
            with open(os.path.join(outdir, f"{rid}.json"), "w", encoding="utf-8") as fh:
                json.dump(doc, fh, ensure_ascii=False, indent=1)
            n_art += 1
            mfh.write(json.dumps({
                "resource_id": rid, "resource_key": rid, "kb_type": KB_TYPE,
                "source_kind": "drill_link", "extractor_version": EXTRACTOR_VERSION,
                "observed_at": e.get("observed_at") or a.run,
                "status": "ok", "status_reason": "下钻落地（land_drill_into_l1）",
                "source_sha256": h, "char_count": len(text),
                "segment_count": 1, "media_count": 0, "table_count": 0,
            }, ensure_ascii=False) + "\n")
            n_man += 1
    print(f"  ✅ 产物 {n_art} 件 → {os.path.relpath(outdir, ROOT)}｜台账追加 {n_man} 行")
    print(f"  （{time.strftime('%Y-%m-%d %H:%M:%S')}｜L0 未改动）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
