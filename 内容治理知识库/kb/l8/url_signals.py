#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""链接类「信号级对齐」：不追求整页 sha 一致，只看四个**确定性信号**变没变。

## 为什么改走信号级（Owner 2026-10-08 批准口径①）

用户口径是「有新增就补充、还下架就删除、数据一样就保留」。对**活页面**（落地页/商品页/博客）
这条规则在「整页 sha」上机械上永不成立。本轮实测三条路都不足以交付它：

| 路 | 实测 |
|---|---|
| 机械剔行（多语言正则，自证 21/0） | 102 页只剔掉 22,105 字（1.4%）；71 条「变了」只收敛 **20** 条 |
| 站点块表（跨页高频行） | 收敛 **41** 条，且是 **in-sample 上界**；**新评论永远不在表里** |
| 按 `<main>` 取正文 | 页头/导航/促销/价格排除了，但**评论就在 main 里面**（容器内 3 行／容器外 0 行） |
| ⇒ 真要做只有「按站点模板维护 DOM 排除选择器表」 | 成本高、模板改版**静默失效**、只覆盖识别得出的模板 |

⇒ 改看**信号**。这四个信号是确定性的、便宜的，且直接对应「有新增」的业务含义；
评论数、价格、配送时效、页脚推荐位轮换**天然不影响**它们：

1. `h1` —— 页面主标题（落地页文案改写会变）
2. `last_updated` —— 正文里的「最后更新」日期（博客内容更新的显式标记）
3. `products` —— 页面上的商品 handle 集合（**上下架**会变）
4. `terms` —— 正文命中的**受控词表**词条（新出现的宣称/禁用表达 = 最该看的那种「新增」）

词表来源（**不在别处抄第二份**）：`kb/l3/candidates/rules.jsonl` 的 `forbidden_expression`
＋ `kb/l5/p0_patterns.jsonl` 的 `match_terms` / `patterns`。

用法：
    python3 kb/l8/url_signals.py <RUN>                 # 采集并与基线比，只报不改
    python3 kb/l8/url_signals.py <RUN> --apply         # 同时把本次采集写成新基线
    python3 kb/l8/url_signals.py <RUN> --limit 5       # 先跑几条看形态
基线文件：`kb/l8/url_signals.json`（**不写 L0** —— L0 是与飞书对齐的源层，观测件不混进去）
"""
import json
import os
import re
import sys
import html as H
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "kb/l8"))
import probe_main_content as PMC  # noqa: E402  复用同一套 chrome 抓取与 extract

BASELINE = os.path.join(ROOT, "kb/l8/url_signals.json")
RUN = next((a for a in sys.argv[1:] if not a.startswith("--")), "no-run")
APPLY = "--apply" in sys.argv
LIMIT = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None

H1 = re.compile(r"<h1[^>]*>(.*?)</h1>", re.S | re.I)
PROD = re.compile(r'href=["\'](?:https?://[^"\']*)?/products/([A-Za-z0-9_\-\.%]{2,80})', re.I)
UPD = re.compile(r"(Last updated|Updated on|Last modified|Dernière mise à jour|Zuletzt aktualisiert|"
                 r"Actualizado el|Ultima modifica|最終更新|更新时间)\s*[::]?\s*([^\n]{4,40})", re.I)


def load_vocabulary():
    """受控词表：{词: 出处}。词长 ≥3，避免单字噪声。"""
    voc = {}
    p = os.path.join(ROOT, "kb/l3/candidates/rules.jsonl")
    if os.path.exists(p):
        for line in open(p, encoding="utf-8"):
            if not line.strip():
                continue
            r = json.loads(line)
            fe = r.get("forbidden_expression")
            for x in (fe if isinstance(fe, list) else [fe]):
                if isinstance(x, str) and len(x.strip()) >= 3:
                    voc.setdefault(x.strip(), f"L3:{r.get('rule_code') or r.get('rule_id')}")
    p = os.path.join(ROOT, "kb/l5/p0_patterns.jsonl")
    if os.path.exists(p):
        for line in open(p, encoding="utf-8"):
            if not line.strip():
                continue
            r = json.loads(line)
            for key in ("match_terms", "patterns"):
                v = r.get(key)
                if isinstance(v, str):
                    v = [v]
                for x in (v or []):
                    if isinstance(x, str) and 3 <= len(x.strip()) <= 60:
                        voc.setdefault(x.strip(), f"L5:{r.get('pattern_id') or r.get('rule_id')}")
    return voc


def signals_for(dom, text, voc):
    h1 = ""
    m = H1.search(dom or "")
    if m:
        h1 = " ".join(H.unescape(re.sub(r"<[^>]+>", " ", m.group(1))).split())[:200]
    prods = sorted({x.lower().rstrip("/") for x in PROD.findall(dom or "")})
    mu = UPD.search(text or "")
    upd = " ".join(mu.group(0).split())[:80] if mu else ""
    low = (text or "").lower()
    terms = sorted({w for w in voc if w.lower() in low})
    return {"h1": h1, "last_updated": upd, "products": prods, "terms": terms}


def main():
    voc = load_vocabulary()
    print(f"[{RUN}] 受控词表 {len(voc)} 条（L3 forbidden_expression + L5 match_terms/patterns）")
    try:
        base = json.load(open(BASELINE, encoding="utf-8"))
    except Exception:
        base = {}
    print(f"  基线：{len(base)} 条（{'有' if base else '**没有** —— 本次是首轮建基线'}）")

    # 目标：台账里非飞书站内的活跃 url（飞书站内走 API 通道，不由本工具管）
    cur = {}
    for line in open(os.path.join(ROOT, "kb/l0/manifest.jsonl"), encoding="utf-8"):
        if line.strip():
            r = json.loads(line)
            if r.get("source_kind") == "url":
                cur[r["resource_key"]] = r
    def _bad_key(r):
        """与 recrawl_all_urls.py 同口径：显示文本被当成主机名的坏键不抓（台账 09-29 已定性）。"""
        note = str(r.get("status_reason") or "") + str(r.get("change") or "")
        return ("坏键" in note) or ("bad_key" in note)

    targets, n_bad = [], 0
    for k, r in sorted(cur.items()):
        u = k.split(":", 1)[-1]
        if not u.startswith(("http://", "https://")) or "feishu.cn" in u:
            continue
        if r.get("status") in ("gone", "retracted"):
            continue
        if _bad_key(r):
            n_bad += 1
            continue
        targets.append((k, u))
    if n_bad:
        print(f"  跳过台账已登记坏键 {n_bad} 条")
    if LIMIT:
        targets = targets[:LIMIT]
    print(f"  待采集 {len(targets)} 条")

    out, changes, newly, n_fail = {}, [], [], 0
    for i, (k, u) in enumerate(targets, 1):
        dom = PMC.fetch(u)
        if not dom:
            out[k] = {"error": "渲染失败", "at": RUN}
            n_fail += 1
            print(f"  [{i}/{len(targets)}] ✗ 渲染失败 {u[:60]}", flush=True)
            continue
        sig = signals_for(dom, PMC.extract(dom), voc)
        out[k] = dict(sig, at=RUN)
        b = base.get(k)
        # ★★ 比较的三条排除（2026-10-08 实测踩到）：首轮 107 条里 **27 条渲染失败**（25%），
        #   而原比较逻辑**没排除失败条目** —— 基线里那 27 条是 `{"error": …}`，
        #   `b.get('h1')` 是 None，与本轮的真值一比就「变了」⇒ 下一轮会凭空多出 27 条假变化。
        #   ⇒ ① 基线侧是失败条目 ⇒ 记「本轮才补上」，**不算变化**；
        #     ② 本轮失败 ⇒ 记未测，不算变化；
        #     ③ 两侧都是「没有这个信号」（如 h1 本来就取不到）也不算变化。
        if b is not None and b.get("error"):
            newly.append({"key": k, "url": u, "why": f"上一轮渲染失败（{b.get('error')}），本轮才测到"})
        elif b is not None:
            d = {}
            for f in ("h1", "last_updated"):
                if (b.get(f) or "") != (sig[f] or ""):
                    d[f] = {"before": b.get(f), "after": sig[f]}
            for f in ("products", "terms"):
                add = sorted(set(sig[f]) - set(b.get(f) or []))
                rm = sorted(set(b.get(f) or []) - set(sig[f]))
                if add or rm:
                    d[f] = {"added": add, "removed": rm}
            if d:
                changes.append({"key": k, "url": u, "diff": d})
        print(f"  [{i}/{len(targets)}] "
              f"{'★' if any(c['key'] == k for c in changes) else ' '} "
              f"h1={sig['h1'][:40]!r} upd={sig['last_updated'][:24]!r} "
              f"products={len(sig['products'])} terms={len(sig['terms'])} {u[:52]}", flush=True)
        time.sleep(0.3)

    print("\n" + "=" * 78)
    if not base:
        print("首轮建基线：没有可比对象，**不报变化**（下一轮起才有意义）。")
    else:
        print(f"信号有变的：{len(changes)} / {len(targets)} 条（对比基线 {len(base)} 条）｜"
              f"未测（本轮渲染失败）：{n_fail} 条｜上轮失败本轮补上：{len(newly)} 条")
        print("★ 「未测」与「补上」都不算变化 —— 把它们算成变化就是拿读数当结论。")
        for c in changes:
            print(f"\n  ★ {c['url'][:76]}")
            for f, v in c["diff"].items():
                if f in ("h1", "last_updated"):
                    print(f"     {f}: {str(v['before'])[:56]!r} → {str(v['after'])[:56]!r}")
                else:
                    print(f"     {f}: +{v['added'][:6]} -{v['removed'][:6]}")
    rep = os.path.join(ROOT, "kb/l8/runs", f"{RUN}-url-signals.json")
    tmp = rep + ".swtmp"
    json.dump({"run": RUN, "vocabulary": len(voc), "targets": len(targets),
               "baseline_n": len(base), "changes": changes, "newly_measured": newly,
               "failed_this_run": n_fail, "signals": out},
              open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    os.replace(tmp, rep)
    print(f"\n报告 {rep}")
    if APPLY:
        tmp = BASELINE + ".swtmp"
        json.dump(out, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        os.replace(tmp, BASELINE)
        print(f"基线已更新 → {BASELINE}（{len(out)} 条）")
    else:
        print("（未加 --apply ⇒ 基线未改）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
