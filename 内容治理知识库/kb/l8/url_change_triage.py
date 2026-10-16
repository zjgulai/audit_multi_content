#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""链接类对账分诊：把 recrawl_all_urls.py 的抓取 spool 与 L0 台账逐条比对，
按「摘要口径可不可比」分层出结论，而不是拿一把尺子量到底。

为什么必须分层（2026-10-08 踩过的坑）：
  L0 的 url 摘要混了 8 种口径（url_text / url_text_rendered_v1 / url_text_refresh_v1 /
  pdf_ocr_v1 / pdf_text_layer_v1 / pdf_text_untruncated_v1 / file_bytes / feishu_content_v1）。
  `recrawl_all_urls.py` 内部用的是 `url_text_rendered_v1`（sha256(块级取文本)）。
  ⇒ 只有台账口径**也是** rendered_v1 的行，摘要不等才等于「正文真变了」；
     其余行摘要不等是**口径差异**，不是变化 —— 早先那 72 条 "recomputed_differ" 就是这么来的假警报。

分诊桶：
  A_一致            正文抓到 + 摘要逐字相同          ⇒ 保留（规则：数据一样就保留）
  B_真变            正文抓到 + 口径同为 rendered_v1 且摘要不同 ⇒ 有新增/diff（规则：有新增就补充）
  C_口径不可比      正文抓到 + 台账口径非 rendered_v1 且摘要不同 ⇒ 不能判为变化，需回源裁
  D_取不到          未抓到 / 正文 < 300 字            ⇒ 不下结论
  E_未覆盖          spool 里没有这个 key
  F_无指纹          台账口径名义可比但 sha 为 null（not_fetched）⇒ 无基线可判

用法：
  python3 kb/l8/url_change_triage.py <spool.jsonl> [--out <report.json>]
"""
import json
import sys
import os
import collections

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MIN_CHARS = 300                      # 与 recrawl_all_urls.py 同判据
RENDERED = "url_text_rendered_v1"    # 本脚本重算用的口径


def load_current_url_rows():
    """每个 url key 的当前态 = manifest 里该 key 的最后一行（已核实该语义）。"""
    cur, bad = {}, []
    p = os.path.join(ROOT, "kb/l0/manifest.jsonl")
    for line in open(p, encoding="utf-8"):
        if not line.strip():
            continue
        r = json.loads(line)
        if r.get("source_kind") != "url":
            continue
        cur[r["resource_key"]] = r          # 后行覆盖前行 ⇒ 末行即当前态
    # 坏键：resource_key 冒号后不是 http 起头（显示文本被当成主机名），或台账已标坏键
    out = {}
    for k, r in cur.items():
        if not k.split(":", 1)[-1].startswith(("http://", "https://")):
            bad.append(k)
            continue
        note = str(r.get("status_reason") or "") + str(r.get("change") or "")
        if "坏键" in note or "bad_key" in note:
            bad.append(k)
            continue
        if r.get("status") in ("gone", "retracted"):
            continue
        out[k] = r
    return out, bad


def load_l1_chars():
    """L1 归档里每条 url 的正文字数（用于看「变长还是变短」）。"""
    d = {}
    base = os.path.join(ROOT, "kb/l1")
    for sub in os.listdir(base):
        pd = os.path.join(base, sub)
        if not os.path.isdir(pd) or sub in ("registry", "index", "_archive", "media"):
            continue
        for f in os.listdir(pd):
            if not f.startswith("url__") or not f.endswith(".json"):
                continue
            try:
                a = json.load(open(os.path.join(pd, f), encoding="utf-8"))
            except Exception:
                continue
            rk = a.get("resource_key")
            if rk:
                d[rk] = a.get("char_count")
    return d


def load_l1_note():
    """L1 归档里每条 url 的 status / status_reason（判「0 字是为什么」）。"""
    d = {}
    base = os.path.join(ROOT, "kb/l1")
    for sub in os.listdir(base):
        pd = os.path.join(base, sub)
        if not os.path.isdir(pd) or sub in ("registry", "index", "_archive", "media"):
            continue
        for f in os.listdir(pd):
            if not f.startswith("url__") or not f.endswith(".json"):
                continue
            try:
                a = json.load(open(os.path.join(pd, f), encoding="utf-8"))
            except Exception:
                continue
            rk = a.get("resource_key")
            if rk:
                d[rk] = (a.get("status"), a.get("status_reason"))
    return d


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    spool = sys.argv[1]
    out_p = None
    if "--out" in sys.argv:
        out_p = sys.argv[sys.argv.index("--out") + 1]

    cur, bad = load_current_url_rows()
    l1c = load_l1_chars()
    l1n = load_l1_note()
    got = {}
    for line in open(spool, encoding="utf-8"):
        if line.strip():
            r = json.loads(line)
            got[r["key"]] = r

    buckets = collections.defaultdict(list)
    for k in sorted(cur):
        r = cur[k]
        old_sha = r.get("sha256")
        cal = r.get("sha256_input")
        g = got.get(k)
        ent = {"key": k, "url": k.split(":", 1)[1],
               "caliber": cal, "old_sha": (old_sha or "")[:12],
               "l1_chars_before": l1c.get(k),
               "status": r.get("status"), "observed_at": r.get("observed_at")}
        if g is None:
            ent["why"] = "spool 未覆盖"
            buckets["E_未覆盖"].append(ent)
            continue
        chars = int(g.get("chars") or 0)
        ent["chars_after"] = chars
        ent["method"] = g.get("method")
        if chars < MIN_CHARS:
            ent["why"] = f"正文 {chars} 字 < {MIN_CHARS}"
            # ★★ 2026-10-08 关键修正：HTTP/渲染通道取不到 **≠** 这条没有内容。
            #   飞书站内对象（*.feishu.cn/wiki|file|drive|share）走 HTTP 结构上读不到，
            #   但走飞书 API（取原件 PDF + 扫描件 OCR）早就抽到了正文。实测 42 条
            #   「取不到」里 36 条 L1 有正文、合计 10,730,271 字（最长 207 万字）。
            #   不分这一刀就会把它们误报成缺口 —— 这正是本脚本第一版犯的错。
            _n = l1c.get(k)
            ent["l1_chars"] = _n
            ent["l1_status"], ent["l1_reason"] = l1n.get(k, (None, None))
            if (_n or 0) > 0:
                ent["why"] = (f"HTTP/渲染通道取不到，但 **L1 已有正文 {_n:,} 字**"
                              f"（走飞书 API 通道，status={ent['l1_status']}）⇒ 不是缺口")
                buckets["D1_已有内容_通道不同"].append(ent)
            else:
                ent["why"] = (f"HTTP 取不到且 L1 也无正文（status={ent['l1_status']}）"
                              f"：{str(ent['l1_reason'])[:60]}")
                buckets["D2_真缺口"].append(ent)
            continue
        import hashlib
        new_sha = hashlib.sha256(g["text"].encode("utf-8")).hexdigest()
        ent["new_sha"] = new_sha[:12]
        if old_sha == new_sha:
            buckets["A_一致"].append(ent)
        elif old_sha is None:
            ent["why"] = f"台账无指纹（口径 {cal} 但 sha=null，not_fetched）"
            buckets["F_无指纹"].append(ent)
        elif cal == RENDERED:
            ent["why"] = "口径同为 rendered_v1 且摘要不同 ⇒ 真变"
            ent["delta_chars"] = (chars - l1c[k]) if l1c.get(k) is not None else None
            buckets["B_真变"].append(ent)
        else:
            ent["why"] = f"台账口径 {cal} ≠ {RENDERED} ⇒ 摘要不可比，不是变化"
            buckets["C_口径不可比"].append(ent)
        ent["delta_chars"] = (chars - l1c[k]) if l1c.get(k) is not None else None

    print("=" * 78)
    print(f"链接类对账分诊  |  台账 url（去坏键/去 gone）{len(cur)} 条  |  spool {len(got)} 条")
    print(f"排除坏键 {len(bad)} 条：{[b[:54] for b in bad]}")
    print("=" * 78)
    order = ["A_一致", "B_真变", "C_口径不可比", "D1_已有内容_通道不同",
             "D2_真缺口", "F_无指纹", "E_未覆盖"]
    for b in order:
        rows = buckets[b]
        print(f"\n【{b}】{len(rows)} 条")
        if b == "A_一致":
            print("   ⇒ 规则「数据一样就保留」：不动。")
        elif b == "B_真变":
            print("   ⇒ 规则「有新增就补充」：需补 L1/L2（口径一致，diff 可判）。")
            for e in sorted(rows, key=lambda x: -(x.get("delta_chars") or 0)):
                print(f"     +{e.get('delta_chars')} 字  {e['url'][:70]}")
        elif b == "C_口径不可比":
            cc = collections.Counter(e["caliber"] for e in rows)
            print(f"   ⇒ 口径分布 {dict(cc)}；**不可据此判变化**，需回源裁。")
            for e in rows:
                print(f"     [{e['caliber']}] {e['url'][:64]}")
        elif b == "D1_已有内容_通道不同":
            tot = sum(e.get("l1_chars") or 0 for e in rows)
            print(f"   ⇒ 合计 L1 正文 {tot:,} 字。**不是缺口**：内容在，只是不走 HTTP。")
            for e in sorted(rows, key=lambda x: -(x.get("l1_chars") or 0)):
                print(f"     L1 {e.get('l1_chars'):>9,} 字 | {e['url'][:66]}")
        elif b == "D2_真缺口":
            print(f"   ⇒ 真没正文，需人/需权限。原因逐条列出：")
            for e in rows:
                print(f"     [{str(e.get('l1_status')):12s}] {str(e.get('l1_reason'))[:52]:52s} | {e['url'][:56]}")
        elif b == "F_无指纹":
            for e in rows:
                print(f"     {e['url'][:70]}")
        else:
            for e in rows:
                print(f"     {e['url'][:70]}")

    if out_p:
        tmp = out_p + ".swtmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump({b: buckets[b] for b in order}, fh, ensure_ascii=False, indent=1)
        os.replace(tmp, out_p)
        print(f"\n报告已落盘：{out_p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
