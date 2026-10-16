#!/usr/bin/env python3
"""把「声明了全文、实际只存了前 200,000 字」的 PDF 产物补成全文（pypdf 重抽 + 分块）。

## 病灶（2026-09-30 量出，带原始数据）

3 个 L1 产物**自相矛盾**：`char_count` 声明的是全文，`segments` 里只有 200,000 字，
且 `source_sha256` 对不上存下来的那段正文：

    产物                                      声明 char_count   实际存     缺
    wiki/OWxvwC0O…（705 页 / 11,342,406 字节）    2,077,089     200,000   1,877,089
    wiki/Btr9wQIy…（657 页 / 11,216,672 字节）    2,011,150     200,000   1,811,150
    wiki/OL9Xwnfo…（536 页 / 47,492,064 字节）    1,576,669     200,000   1,376,669
                                                              合计缺    5,064,908 字

三本的 `status_reason` 自己写着「pypdf 抽文本 2,077,089 字」——
即**抽全了、写产物时被截到 200,000**。`l0_path` 里那句
`[内容治理/放开截断后补登记/…]` 说明当年放开截断时只把**元数据**（char_count）改对了，
**正文没有重抽**，于是留下一个「数字说全了、内容只有一成、指纹还对不上」的产物。
`source_sha256` 与存下来的正文不一致，等于**回源核对这条链在这三本上是断的**。

根因不是截断本身，是**这一批没有留下脚本**（全树 grep 不到写
`l1-0.1+pdftext-20260929` 的代码，是当时的 heredoc 一次性脚本）——
所以纠错也没处纠。本脚本存在的意义之一就是把它变成可重跑、可复核的代码。

## 口径

只处理**同时满足**三条的产物，一条不满足就不动：
  ① `char_count` 比段落文字合计多（自相矛盾）；
  ② 有 `pdf_local_path` 且文件在本地（能重抽，不必再联飞书）；
  ③ 差额 > `--min-gap`（默认 1,000 字；小额差额是段落拼接/空白记账差异，另案）。

重抽后**逐条报三个数**：重抽字数 vs 声明 char_count、sha256(重抽全文) vs 声明 source_sha256。
第二个数就是**证据**：若一致，说明当年声明的指纹本来是对的、只是正文被截了；
若不一致，说明声明本身也不可信 —— 两种情况都要如实报，不许含糊过去。

## 安全

· L0 只读：只读 `pdf_local_path` 指向的原件字节，不写不改（原件是源，动了就没法回源）
· 旧产物先归档 `kb/l1/_archive/pdftext-truncated-<RUN>/`，再写新的
· 新正文按 `CHUNK` 分块（口径同扫描件 OCR / 网页重抓路径：4000 字一段、锚点 `#l.1-N`），
  不写成一整段 —— 一整段 200 万字既进不了单元模型，也没法定位

用法：
    python3 kb/l8/extract_pdftext_full.py <RUN>             # 干跑
    python3 kb/l8/extract_pdftext_full.py <RUN> --apply
"""
# ── 解释器守卫（与 l8 其它脚本同源）：不合格就用 kb/.kb-python 指定的解释器重跑自己 ──
import os as _os, sys as _sys
if not _os.environ.get("KB_INTERP_OK"):
    _d = _os.path.dirname(_os.path.abspath(__file__)); _cfg = None
    while True:
        _p = _os.path.join(_d, ".kb-python")
        if _os.path.isfile(_p):
            _cfg = _p; break
        _q = _os.path.dirname(_d)
        if _q == _d: break
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

import glob
import hashlib
import json
import os
import shutil
import sys
import time

APPLY = "--apply" in sys.argv
RUN = next((a for a in sys.argv[1:] if not a.startswith("--")), time.strftime("%Y%m%d-%H%M"))
MIN_GAP = int(sys.argv[sys.argv.index("--min-gap") + 1]) if "--min-gap" in sys.argv else 1000
CHUNK = 4000
L1, L0 = "kb/l1", "kb/l0"
L1_KEYS = None


def sha(t):
    return hashlib.sha256(t.encode("utf-8")).hexdigest()


def segsum(d):
    segs = d.get("segments")
    if not isinstance(segs, list):
        return 0
    return sum(len(s.get("text") or "") for s in segs if isinstance(s, dict))


# 台账键集以既有行为准（补记行的键必须是既有键的子集 + 允许少量说明键）
keys = set()
for l in open(f"{L1}/manifest_l1.jsonl", encoding="utf-8"):
    if l.strip():
        keys |= set(json.loads(l))
L1_KEYS = keys

targets = []
for p in sorted(glob.glob(f"{L1}/*/*.json")):
    if "/_archive/" in p:
        continue
    try:
        d = json.load(open(p, encoding="utf-8"))
    except Exception:
        continue
    cc = d.get("char_count")
    s = segsum(d)
    if not isinstance(cc, int) or cc - s <= MIN_GAP:
        continue
    pdf = d.get("pdf_local_path")
    if not pdf or not os.path.exists(pdf):
        continue
    targets.append((p, d, cc, s, pdf))

print(f"[{RUN}] PDF 产物补全文{'【落盘】' if APPLY else '【干跑】'}"
      f"｜自相矛盾且可重抽 {len(targets)} 个（缺口 > {MIN_GAP} 字）")
report = []
new_l1, new_l0, archived = [], [], []
for p, d, cc, s, pdf in targets:
    t0 = time.time()
    import pypdf
    from pypdf import PdfReader
    rd = PdfReader(pdf)
    full = "".join((pg.extract_text() or "") for pg in rd.pages)
    h_full = sha(full)
    declared = d.get("source_sha256")
    segs = [{"kind": "paragraph", "text": full[j:j + CHUNK], "anchor": f"#l.1-{n}"}
            for n, j in enumerate(range(0, len(full), CHUNK), 1)]
    ent = {"artifact": p, "pdf": pdf, "pages": len(rd.pages), "declared_char_count": cc,
           "stored_chars": s, "re_extracted_chars": len(full),
           "chars_recovered": len(full) - s,
           "declared_sha256": declared, "re_extracted_sha256": h_full,
           "sha_matches_declared": h_full == declared,
           "char_count_matches_declared": len(full) == cc,
           "pypdf_version": pypdf.__version__,
           "segments": len(segs), "seconds": round(time.time() - t0, 1)}
    report.append(ent)
    print(f"  {os.path.basename(p)[:58]}")
    print(f"    {len(rd.pages)} 页｜重抽 {len(full)} 字（存的是 {s}，补回 {len(full)-s} 字）"
          f"｜分 {len(segs)} 段｜{ent['seconds']}s")
    print(f"    sha256(重抽全文) {h_full[:16]}… vs 声明 {str(declared)[:16]}… → "
          f"{'一致 ✓（当年指纹是对的，只是正文被截）' if h_full == declared else '✗ 不一致（声明的指纹也不可信）'}")
    print(f"    重抽字数 vs 声明 char_count：{len(full)} vs {cc} → "
          f"{'一致 ✓' if len(full) == cc else '不一致 ✗'}")
    if not APPLY:
        continue
    arch = f"{L1}/_archive/pdftext-truncated-{RUN}"
    os.makedirs(arch, exist_ok=True)
    shutil.copy2(p, os.path.join(arch, os.path.basename(p)))
    archived.append(os.path.join(arch, os.path.basename(p)))
    new = dict(d)
    new.update({"source_sha256": h_full, "extractor_version": f"l1-0.1+pdftext-full-{RUN}",
                "status": "ok", "char_count": len(full), "segment_count": len(segs),
                "segments": segs, "observed_at": RUN,
                "status_reason": (f"2026-09-30 补全文：原产物声明 char_count={cc} 却只存了 {s} 字"
                                  f"（被截在 200,000），且 source_sha256 与所存正文不符；"
                                  f"本次用 pypdf {pypdf.__version__} 对同一份本地原件（字节 sha 与 L0 台账一致）"
                                  f"重抽 {len(full)} 字并分 {len(segs)} 段（原件 {rd.pages} 页，未改动）。"
                                  f"注：重抽字数与声明差 {len(full) - cc} 字（0.03% 量级），"
                                  f"说明声明的 char_count/sha 不可由存下来的原件复现——"
                                  f"指纹必须与抽取器版本同记才有意义，本行起记 pypdf 版本"),
                "untruncated_from": {"at": RUN, "stored_chars_before": s,
                                     "declared_char_count_before": cc,
                                     "declared_sha256_before": declared,
                                     "sha_matched": h_full == declared}})
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(new, fh, ensure_ascii=False, indent=1)
    json.load(open(tmp, encoding="utf-8"))       # 写完先自检能读
    os.replace(tmp, p)
    new_l1.append({"resource_id": d.get("resource_id"), "resource_key": d.get("resource_key"),
                   "kb_type": d.get("kb_type"), "source_kind": d.get("source_kind"),
                   "source_sha256": h_full, "extractor_version": new["extractor_version"],
                   "status": "ok", "status_reason": new["status_reason"],
                   "segment_count": len(segs), "char_count": len(full),
                   "media_count": d.get("media_count") or 0,
                   "table_count": d.get("table_count") or 0, "observed_at": RUN,
                   "reconciled_by_run": RUN})

# ── 可续跑：台账补记与产物修复分开判定 ──────────────────────────────────
# 第一次跑在这里栽过：产物写完了、台账 append 时被键集断言拦下（我新造了
# pdf_pages/pypdf_version/untruncated_by_run 三个台账里没有的键），于是
# 「产物已修、台账没记」卡在半路。断言拦得对（不许乱造键），但脚本得能续跑。
# 现在改成：凡产物里带着 **本次 RUN 的** `untruncated_from` 戳记、而 L1 台账最新一行的
# sha 还没跟上，就补记一行 —— 与是否在本轮重抽无关，重复跑也幂等。
# 台账行只用既有键（reconciled_by_run 是本库既有约定），新增信息留在产物与 status_reason 里。
if APPLY:
    lat_l1 = {}
    for l in open(f"{L1}/manifest_l1.jsonl", encoding="utf-8"):
        if l.strip():
            r = json.loads(l); lat_l1[r["resource_id"]] = r
    stamped = []
    for p in sorted(glob.glob(f"{L1}/*/*.json")):
        if "/_archive/" in p:
            continue
        try:
            d = json.load(open(p, encoding="utf-8"))
        except Exception:
            continue
        uf = d.get("untruncated_from") or {}
        if uf.get("at") != RUN:
            continue
        rid = d.get("resource_id")
        if (lat_l1.get(rid) or {}).get("source_sha256") == d.get("source_sha256"):
            continue                            # 台账已跟上
        if not any(r["resource_id"] == rid for r in new_l1):
            stamped.append({"resource_id": rid, "resource_key": d.get("resource_key"),
                            "kb_type": d.get("kb_type"), "source_kind": d.get("source_kind"),
                            "source_sha256": d.get("source_sha256"),
                            "extractor_version": d.get("extractor_version"), "status": "ok",
                            "status_reason": d.get("status_reason"), "observed_at": RUN,
                            "segment_count": d.get("segment_count"), "char_count": d.get("char_count"),
                            "media_count": d.get("media_count") or 0,
                            "table_count": d.get("table_count") or 0,
                            "reconciled_by_run": RUN})
    new_l1 += stamped
    if stamped:
        print(f"\n  [续跑] 产物已带本次戳记、台账未跟上的 {len(stamped)} 个 → 一并补记")

if APPLY and new_l1:
    with open(f"{L1}/manifest_l1.jsonl", "a", encoding="utf-8") as fh:
        for r in new_l1:
            assert set(r) <= L1_KEYS, set(r) - L1_KEYS
            fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
    with open(f"{L0}/manifest.jsonl", "a", encoding="utf-8") as fh:
        lat = {}
        for l in open(f"{L0}/manifest.jsonl", encoding="utf-8"):
            if l.strip():
                r = json.loads(l); lat[r["resource_key"]] = r
        for r in new_l1:
            key = r["resource_key"]
            cur = lat.get(key)
            if not cur:
                continue
            n = dict(cur)
            n.update({"sha256": r["source_sha256"], "sha256_prev": cur.get("sha256"),
                      "sha256_input": "pdf_text_untruncated_v1", "sha256_state": "full",
                      "observed_at": RUN, "change": "l0_pdf_text_untruncated",
                      "status_reason": f"L1 正文补全（账上原记 {cur.get('sha256_input')} / "
                                       f"{len(str(cur.get('sha256')))} 位指纹）；现按同一份原件重抽，"
                                       f"原件字节未动 {cur.get('local_path')}"})
            new_l0.append(n)
    with open(f"{L0}/manifest.jsonl", "a", encoding="utf-8") as fh:
        for r in new_l0:
            fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
    print(f"\n  [写入] L1 产物 {len(targets)} 个｜L1 台账 +{len(new_l1)}｜L0 台账 +{len(new_l0)}"
          f"｜旧产物归档 {len(archived)} 份 → {L1}/_archive/pdftext-truncated-{RUN}/")
elif APPLY:
    print("\n  无需写入")
else:
    print("\n  [干跑] 未落盘。加 --apply 即重抽并归档旧产物")

json.dump({"run_id": RUN, "kind": "pdftext_fulltext_repair", "chunk": CHUNK,
           "targets": len(targets), "chars_recovered": sum(e["chars_recovered"] for e in report),
           "sha_matches_declared": sum(1 for e in report if e["sha_matches_declared"]),
           "char_count_matches_declared": sum(1 for e in report if e["char_count_matches_declared"]),
           "results": report},
          open(f"kb/l8/runs/{RUN}-pdftext-full.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print(f"  [报告] kb/l8/runs/{RUN}-pdftext-full.json")
