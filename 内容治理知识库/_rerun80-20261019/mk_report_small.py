#!/usr/bin/env python3
"""⑥ 给「问题数 <3」的 38 行补建报告 —— **不落库**（一个表字段都不写）。

## 为什么是「档案式归档」而不是「重跑一遍让它出报告」

Owner 要求「<3 个的也输出报告链接」，同时第 3 条要求「表内五字段与报告正文一致」。
这两条**只有一条路能同时满足**：

  · **重跑一遍**（`SH_FORCE_REPORT=1`）→ 报告是管线原生模版，但**读数会漂**。
    实测：`MC-US-WEB-IMG-baby-sleep-bundle-baby-sleep-sack-baby-monitor-bm04`
    10/19 表内 **2 处**，21:00 重跑只得 **1 处** ⇒ 报告与表内**必然**对不上。
  · **按 10/19 本轮已有产物归档**（本脚本）→ 内容**逐字复制自报告同源的那几处**
    （表内「问题分类汇总」那一格 ＋ 本轮 `merged-*.json` 逐条记录），
    **零漂移**，可逐字校验（脚本自带断言：表格那一格必须整段出现在报告正文里）。

⇒ 取后者。代价照实说：这份报告的**版式**与那 42 份（管线原生）不完全一样，
   它多一节「本文件是补建的」说明；**内容一个字没改**。

## 判据

  · 只对 `问题数量 < 3` 且 `10/19 报告链接` 为空的行补；
  · 每份报告的正文必须**逐字包含**表内「问题分类汇总」那一格（否则抛错，不出版式可疑件）；
  · 发布走**管线同一个发布器**（`review_publish.publishReportDoc`）：
    同一条 `lark-cli docs +create`、同一个身份、建完**立刻设成组织内可阅读并回读**；
  · **不写任何表**：本脚本只建云文档，采集表/结论表一个字段都不碰。

用法：
    python3 _rerun80-20261019/mk_report_small.py            # 干跑：只生成 md 与清单
    python3 _rerun80-20261019/mk_report_small.py --publish  # 真建云文档
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
LARK = os.path.expanduser("~/.dsh/bin/lark-cli")
SIDE = os.path.expanduser("~/Project/audit_multi_content/PMO/shouheng-state")
LEDGER = os.path.join(SIDE, "batch-review-1019.json")
TABLE_ROWS = os.path.join(HERE, "records-final.ndjson")
MERGED_DIRS = [os.path.expanduser("~/Project/PMO/shouheng-state/merged-reports"), SIDE + "/merged-reports"]
OUTDIR = os.path.join(HERE, "reports-small")
MANIFEST = os.path.join(HERE, "reports-small-manifest.json")
RESULT = os.path.join(HERE, "reports-small-supplement.json")
START = "2026-10-19T10:40"
NODE_PUBLISH = os.path.join(HERE, "mk_report_small_publish.mjs")


def plain(v) -> str:
    if v is None:
        return ""
    if isinstance(v, str):
        return v
    if isinstance(v, list):
        return "".join(plain(x) for x in v)
    if isinstance(v, dict):
        return str(v.get("link") or v.get("text") or "")
    return str(v)


def url_of(v) -> str:
    m = re.search(r"https?://[^\s)\]]+", plain(v))
    return m.group(0) if m else ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--publish", action="store_true")
    a = ap.parse_args()

    rows = [json.loads(l) for l in open(TABLE_ROWS, encoding="utf-8") if l.strip()]
    led = json.load(open(LEDGER, encoding="utf-8")).get("items", {})
    merged = []
    for f in sorted(x for d0 in MERGED_DIRS for x in glob.glob(os.path.join(d0, "merged-2026-10-19T*.json"))):
        try:
            d = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        if str(d.get("at", "")) >= START:
            merged.append((f, d))

    os.makedirs(OUTDIR, exist_ok=True)
    todo, used = [], set()
    for r in rows:
        cid = plain(r.get("内容 ID"))
        if url_of(r.get("10/19 报告链接")):
            continue                                     # 已有本轮报告 ⇒ 不动
        n = r.get("问题数量")
        try:
            n = int(float(n)) if n not in (None, "") else 0
        except (TypeError, ValueError):
            n = 0
        if n >= 3:
            continue                                     # 不该出现（≥3 必有报告），留着提醒
        d = led.get(cid) or {}
        win = (str(d.get("ran_from") or ""), str(d.get("sent_at") or ""))
        rec = None
        for i, (f, m) in enumerate(merged):
            if i in used:
                continue
            if win[0] and win[0] <= str(m.get("at", "")) <= win[1]:
                rec, _ = (f, m), used.add(i)
                break
        todo.append({"cid": cid, "rid": r["record_id"], "n": n,
                     "state": plain(r.get("Agent 结论")), "type": plain(r.get("内容类型")),
                     "material": plain(r.get("采集数据")), "cell": plain(r.get("问题分类汇总")),
                     "status": plain(r.get("状态")), "merged": rec[1] if rec else None,
                     "merged_file": rec[0] if rec else None})

    print(f"待补报告：{len(todo)} 行（1–2 处 {sum(1 for t in todo if t['n'] > 0)} 行 ／ "
          f"0 处 PASS {sum(1 for t in todo if t['n'] == 0)} 行）｜配上本轮逐条记录 "
          f"{sum(1 for t in todo if t['merged'])} 行")

    manifest = []
    for t in todo:
        L = []
        L.append('# 内容审查报告\n')
        head = t["cell"].split("\n")[0].strip() or f"【审查结论：{t['state']}】"
        L.append(head + "\n")
        L.append('> 本条问题数 **%d** ＜ 3 ⇒ 按 PRD §5.3.4 不另生成「完整清单报告」'
                 '（明细本就在结论里逐条平铺）。本文件是 **2026-10-19 本轮**的结论与逐条记录的'
                 '**原样归档**，用于让这一行也有可点开的报告；**未改动任何结论**。\n' % t["n"])
        L.append('## 审查对象\n')
        mat = t["material"].strip()
        L.append('> **内容类型**：%s ｜ **内容 ID**：%s\n' % (t["type"] or "—", t["cid"]))
        # 素材里的 URL **一个都不许丢**（图片行是本体、视频行是正片＋缩略图、文案行可能只有来源页）：
        #   ① 图 / 缩略图 ⇒ 一律列成可点链接（图片行的素材就是它）；
        #   ② 其余链接（YouTube / 来源页）⇒ 单列「素材链接」，**不许**被当成正文吞掉。
        all_urls = list(dict.fromkeys(re.findall(r"https?://[^\s)\]>'\"]+", mat)))
        imgs = [u for u in all_urls if re.search(r"\.(?:jpe?g|png|webp|gif|bmp)(?:$|\?)", u, re.I)]
        others = [u for u in all_urls if u not in imgs]
        body = re.sub(r"\[([^\]]*)\]\((https?://[^)]+)\)", r"\1", mat)   # markdown 链接 → 留文字
        body = re.sub(r"https?://\S+", "", body)                          # 裸 URL 从正文里摘掉（下面单列）
        # 摘掉 URL 后会留下「缩略图：」「来源（美国站）：」这种**空标签行** —— 留着是丑排列，删掉不丢信息
        # （对应的链接已在下面单列成可点链接）。
        body = "\n".join(x.rstrip() for x in body.split("\n")
                         if x.strip() and not re.match(r'^[^：:]{1,12}[：:]\s*$', x.strip()))
        if body:
            L.append('> **素材原文**：\n>\n> ' + body.replace("\n", "\n> ") + "\n")
        else:
            L.append('> **素材原文**：（本条只有链接/图片，正文见下）\n')
        for i, u in enumerate(imgs, 1):
            label = "视频缩略图" if t["type"] == "视频" else "图片 %d" % i
            L.append('> **%s**：[点开查看](%s)\n' % (label, u))
        for u in others:
            L.append('> **素材链接**：[点开](%s)\n' % u)
        L.append('\n## 一、结论与逐条明细（表内同一格的逐字副本）\n')
        L.append(t["cell"].strip() + "\n")
        rec = t["merged"]
        if rec and (rec.get("items") or []):
            L.append('\n## 二、逐条结构化记录（本轮 `merged-*.json`，未按版式截断）\n')
            for it in rec["items"]:
                L.append("**%s ｜ %s ｜ %s**\n" % (it.get("id") or "", it.get("tax_label") or "—",
                                                  str(it.get("severity") or "—")))
                L.append("· 来源侧：%s ｜ 回源能力：%s" % (it.get("side") or "—", it.get("basis_kind") or "—"))
                if it.get("location"):
                    L.append("· 位置：%s" % it["location"])
                if it.get("description"):
                    L.append("· 问题描述：%s" % it["description"])
                if it.get("reason"):
                    L.append("· 原因（全文）：%s" % it["reason"])
                if it.get("advice"):
                    L.append("· 修改建议（全文）：%s" % it["advice"])
                if it.get("basis_card"):
                    L.append("· 依据：%s" % it["basis_card"])
                kb = it.get("kb") or {}
                if kb.get("entry_url"):
                    L.append("· 源记录直链：[点开核对](%s)" % kb["entry_url"])
                L.append("")
        L.append("\n---\n")
        L.append('本文件由「10/19 重跑」的补建通道生成：结论与明细**逐字复制自本轮同一单的**'
                 '「问题分类汇总」与逐条记录（`merged-*.json`），不重跑、不改判、不写表。')
        L.append('问题数 ≥3 的另有管线原生版式的报告（「10/19 报告链接」列那份）。')

        md = "\n".join(x for x in L if x is not None)
        assert t["cell"].strip() and t["cell"].strip() in md, f"断言失败：{t['cid']} 的结论格没进正文"
        p = os.path.join(OUTDIR, re.sub(r"[^\w.-]", "_", t["cid"]) + ".md")
        open(p, "w", encoding="utf-8").write(md)
        manifest.append({"content_id": t["cid"], "record_id": t["rid"], "issues": t["n"],
                         "state": t["state"], "md": p, "chars": len(md)})

    json.dump(manifest, open(MANIFEST, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"已生成 {len(manifest)} 份 md → {OUTDIR}")
    for m in manifest[:5]:
        print("  ·", m["content_id"], m["issues"], "处", m["chars"], "字")

    if not a.publish:
        print("\n（干跑：没建云文档。加 --publish 真建）")
        return 0

    print("\n开始建云文档（走管线同一个发布器）…")
    out = subprocess.run(["node", NODE_PUBLISH, MANIFEST], capture_output=True, text=True,
                         cwd=os.path.expanduser("~/Project/audit_multi_content"), timeout=3600)
    print(out.stdout[-3000:])
    if out.returncode != 0:
        print(out.stderr[-2000:], file=sys.stderr)
        return 3
    if os.path.exists(RESULT):
        res = json.load(open(RESULT, encoding="utf-8"))
        ok = [k for k, v in res.items() if v.get("ok")]
        bad = [k for k, v in res.items() if not v.get("ok")]
        print(f"建成 {len(ok)} ｜失败 {len(bad)}")
        for k in bad[:8]:
            print("  ✗", k, res[k].get("detail"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
