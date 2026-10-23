#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""配对预演：201 条失效定稿锚点（旧 record_id）→ 现存「负面样本」记录（新 id）

**只读**：不写 kb/l0…l7 任何文件；产物只有本目录下两个文件。

## 为什么（2026-10-20 实测）
飞书「负面样本」表 2026-10-14 被整体重建 ⇒ 记录 ID 全部换代；L4 定稿里 201 条
`sample_case` 的 `anchor` 仍指向旧 ID（`#正面和负面样本/<old>/原文反馈`），
今天 16:17 那批「串图修复 ③」把对应 L2 单元退役 ⇒ `l4_gate` C4 红 201，
评审链停在 L4（`layer_gate_red`，exit=4），守衡因此报「引擎 JSON 不新鲜 ⇒ 拒收」。

内容还在飞书新 ID 下（实测 `奶瓶不建议倒着放` → `recvw7XIUg72fA/具体原因/分析`），
但**字段语义换了**（旧 `原文反馈` → 新 `具体原因/分析`，还带 `【原则性错误】` 前缀），
所以逐字配对 0/201 ⇒ 必须做**归一化 + 分级**配对，并把歧义项交人裁。

## 分级（写在每一行上，不合并成一句"相似"）
  A 归一化后逐字相等
  B 一方包含另一方（归一化后，短边 ≥12 字且 ≥0.5）
  C difflib 相似度 ≥0.90
  D 无对应 ⇒ 走 `kb/l7/scripts/l4_retire.py` 退役留痕（号不回收）

## 用法
    python3 _remap-gone-anchors-dryrun.py
"""
import collections
import difflib
import glob
import json
import os
import re

ROOT = os.path.dirname(os.path.abspath(__file__))
KB = os.path.join(ROOT, "kb")
OUT_MD = os.path.join(ROOT, "配对预演-201条失效锚点-20261020.md")
OUT_JSONL = os.path.join(ROOT, "配对预演-201条失效锚点-20261020.jsonl")

BRACKET = re.compile(r"【[^】]*】")
WS = re.compile(r"\s+")
PUNCT = re.compile(r"[\s\u3000，。、；：！？…·—\-—_~\"'“”‘’（）()\[\]【】<>《》/\\|,.;:!?]+")


def norm_hard(s: str) -> str:
    """硬归一：去标签块 + 去空白标点。用于 A 档（逐字）。"""
    s = BRACKET.sub("", s or "")
    return PUNCT.sub("", WS.sub("", s))


def norm_soft(s: str) -> str:
    """软归一：只去空白与不可见字符，标点保留。用于 B/C 档（不易把不同长文判成相等）。"""
    s = BRACKET.sub("", s or "")
    return WS.sub("", s)


def load_old():
    """失效定稿：anchor 以 `#正面和负面样本/` 开头的 sample_case。"""
    rows = []
    for p in sorted(glob.glob(os.path.join(KB, "l4/canonical/*.jsonl"))):
        for line in open(p, encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            anc = d.get("anchor") or ""
            if not anc.startswith("#正面和负面样本/"):
                continue
            parts = anc.split("/")
            cc = d.get("cite_check") if isinstance(d.get("cite_check"), dict) else {}
            rows.append({
                "article_no": d.get("article_no"),
                "old_rec": parts[1] if len(parts) > 1 else "",
                "old_field": "/".join(parts[2:]) if len(parts) > 2 else "",
                "old_anchor": anc,
                "old_sha": cc.get("source_sha256"),
                "text": d.get("sample_body") or d.get("rule_text") or d.get("body") or "",
                "file": os.path.basename(p),
            })
    return rows


def load_new():
    """现存负面样本的 L2 单元：(记录, 字段) → 文本 / unit_id / source_sha256。"""
    rows = []
    for line in open(os.path.join(KB, "l2/units.jsonl"), encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        d = json.loads(line)
        anc = d.get("anchor") or ""
        if not anc.startswith("#负面样本/"):
            continue
        parts = anc.split("/")
        if len(parts) < 3:
            continue
        txt = d.get("text") or ""
        # 切分器会把 "字段名:" 贴在正文前（实测：`原文反馈: …` / `具体原因/分析: …`）
        txt = re.sub(r"^[^\n:：]{1,20}[:：]\s*", "", txt, count=1)
        rows.append({
            "new_rec": parts[1], "new_field": "/".join(parts[2:]),
            "new_anchor": anc, "new_unit_id": d.get("unit_id"),
            "new_sha": d.get("source_sha256"), "text": txt,
        })
    return rows


def shingles(s: str, k: int = 6) -> set:
    if len(s) < k:
        return {s} if s else set()
    return {s[i:i + k] for i in range(len(s) - k + 1)}


def best_for(new, osf_hard, osf_soft, o_sh):
    """返回按分数排序的候选（score, tier, unit）。

    ★ 为什么不用 difflib 当主判据（第一版实测踩过）：旧正文与新单元文本的**前缀不同**
      （旧 `@饶雨诗…`、新 `文案…`，且新单元末尾被截断），逐字包含与 0.90 相似度都会漏掉
      ——实测把 `S-1.2`（被引 46 次、内容明明还在 `recvw7XIUg72fA/具体原因/分析`）判成 D。
      改用 **6-gram 覆盖率**（分母取短边）当主判据：前缀/截断不影响，语义重复才命中。
    """
    out = []
    for n in new:
        cov = 0.0
        if o_sh and n["_sh"]:
            inter = len(o_sh & n["_sh"])
            cov = inter / max(1, min(len(o_sh), len(n["_sh"])))
        if osf_hard and osf_hard == norm_hard(n["text"]):
            out.append((100, "A 逐字", n, 1.0))
        elif cov >= 0.60:
            out.append((60 + int(40 * cov), "B 重合%.2f" % cov, n, cov))
        else:
            # 弱档：difflib 只用来**兜底**（覆盖率不到 0.60 时才看）
            r = difflib.SequenceMatcher(None, osf_soft[:400], n["_soft"][:400]).ratio()
            if r >= 0.80:
                out.append((30 + int(30 * (r - 0.80) / 0.20), "C 相似%.3f" % r, n, cov))
    out.sort(key=lambda x: -x[0])
    seen, uniq = set(), []
    for item in out:
        if item[2]["new_anchor"] in seen:
            continue
        seen.add(item[2]["new_anchor"])
        uniq.append(item)
    return uniq


def main():
    old = load_old()
    new = load_new()
    by_rec = collections.defaultdict(list)
    for n in new:
        by_rec[n["new_rec"]].append(n)

    # 预建索引
    hard_index = collections.defaultdict(list)
    for n in new:
        h = norm_hard(n["text"])
        if h:
            hard_index[h].append(n)
        n["_sh"] = shingles(norm_hard(n["text"]))
        n["_soft"] = norm_soft(n["text"])

        out, stats = [], collections.Counter()
    for o in old:
        oh, osf = norm_hard(o["text"]), norm_soft(o["text"])
        cands = []
        for n in hard_index.get(oh, []):
            cands.append((100, "A 逐字", n, 1.0))
        if not cands and oh:
            cands = best_for(new, oh, osf, shingles(oh))
        # 去重 + 取最高档
        seen, uniq = set(), []
        for score, tier, n, cov in sorted(cands, key=lambda x: -x[0]):
            if n["new_anchor"] in seen:
                continue
            seen.add(n["new_anchor"])
            uniq.append((score, tier, n, cov))
        top = [u for u in uniq if u[0] == uniq[0][0]] if uniq else []
        row = {
            "article_no": o["article_no"], "old_rec": o["old_rec"],
            "old_anchor": o["old_anchor"], "old_sha": o["old_sha"],
            "text_head": (o["text"] or "")[:110],
            "candidates": [{"score": s, "tier": t, "overlap": round(cov, 3),
                            "new_rec": n["new_rec"],
                            "new_field": n["new_field"], "new_anchor": n["new_anchor"],
                            "new_unit_id": n["new_unit_id"], "new_sha": n["new_sha"],
                            "text_head": (n["text"] or "")[:110]} for s, t, n, cov in uniq[:3]],
            "n_candidates": len(uniq),
        }
        if not uniq:
            row["tier"] = "D 无对应"
            stats["D"] += 1
        elif len(top) > 1:
            # ★ 并列要再分两种（实测 44 条并列里 26 条是**同内容重复登记**、18 条是**相近但不同**）：
            #   前者两个候选互为同一段内容（6-gram 重合 ≥0.95）⇒ 取哪个 L0 记录都是真出处，
            #   可按「重合最高 → 记录 id 字典序」规则收敛并留痕；后者必须人看。
            ta, tb = shingles(norm_hard(top[0][2]["text"])), shingles(norm_hard(top[1][2]["text"]))
            dup = len(ta & tb) / max(1, min(len(ta), len(tb))) if (ta and tb) else 0.0
            if dup >= 0.95:
                row["tier"] = "并列·同内容（可规则收敛）"
                stats["并列·同内容"] += 1
            else:
                row["tier"] = "并列·相近但不同（人裁）"
                stats["并列·人裁"] += 1
            row["tie_dup_overlap"] = round(dup, 3)
        else:
            row["tier"] = top[0][1]
            stats[top[0][1].split()[0]] += 1
        out.append(row)

    # 覆盖与冲突
    mapped = [r for r in out if r["candidates"]]
    target_rec = collections.Counter(r["candidates"][0]["new_rec"] for r in mapped)
    collide = {k: v for k, v in target_rec.items() if v > 1}
    covered_recs = len({r["candidates"][0]["new_rec"] for r in mapped})
    # 引用面影响（报告里 S-1.x 被引次数）
    cites = collections.Counter()
    for p in glob.glob(os.path.join(KB, "l7/reports/*.review.md")):
        try:
            t = open(p, encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        for m in re.findall(r"S-1\.\d+", t):
            cites[m] += 1
    total_cites = sum(cites.values())
    saved = sum(v for k, v in cites.items() if k in {r["article_no"] for r in mapped})
    dead_cites = sum(v for k, v in cites.items() if k in {r["article_no"] for r in out})

    with open(OUT_JSONL, "w", encoding="utf-8") as fh:
        for r in out:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    amb = [r for r in out if r["tier"].startswith("并列")]
    none = [r for r in out if r["tier"] == "D 无对应"]
    ok = [r for r in out if r["candidates"] and not r["tier"].startswith("并列")]

    L = []
    L.append("# 配对预演：201 条失效锚点 → 现存「负面样本」记录（只读，未写库）\n")
    L.append("- 生成时刻：`python3 _remap-gone-anchors-dryrun.py`（本文件由脚本产出）")
    L.append("- 旧侧：`kb/l4/canonical/sample_case.jsonl` 里 anchor 以 `#正面和负面样本/` 开头的定稿 **%d** 条" % len(old))
    L.append("- 新侧：`kb/l2/units.jsonl` 里 `#负面样本/` 单元 **%d** 个（覆盖 **%d** 个记录）" % (len(new), len(by_rec)))
    L.append("- 明细：`配对预演-201条失效锚点-20261020.jsonl`（每行含候选 1–3 个）\n")
    L.append("## 一、分级结论\n")
    L.append("| 档 | 条数 | 含义 | 落盘动作 |")
    L.append("|---|---|---|---|")
    L.append("| A 逐字 | %d | 归一化后完全相等 | 可直接重指 |" % stats["A"])
    L.append("| B 重合 | %d | 6-gram 覆盖率（分母取短边）≥0.60 | 重指 + 抽检弱档 |" % stats["B"])
    L.append("| C 相似 | %d | difflib ≥0.80（兜底档，覆盖不到 0.60 才用） | 重指 + **逐条人看** |" % stats["C"])
    L.append("| 并列·同内容 | %d | 并列但两候选互为同内容（重合≥0.95） | 规则收敛（重合最高 → 记录 id 升序）＋留痕 |" % stats["并列·同内容"])
    L.append("| 并列·相近但不同 | %d | 并列且两候选内容不同（0.87–0.95） | **人裁** |" % stats["并列·人裁"])
    L.append("| D 无对应 | %d | 什么都没配上 | 走 `l4_retire.py` 退役留痕 |" % stats["D"])
    L.append("")
    auto_n = stats["A"] + stats["B"] + stats["C"] + stats["并列·同内容"]
    human_n = stats["并列·人裁"]
    L.append("⇒ **可重指 %d / %d**（其中**零人裁自动** %d、需人裁 %d），**必须退役 %d**；"
             "重指覆盖 **%d** 个现存记录。" % (len(mapped), len(old), auto_n, human_n, len(none), covered_recs))
    L.append("")
    L.append("## 二、引用面影响（报告 `kb/l7/reports/*.review.md` 实测）\n")
    L.append("| 量 | 值 |")
    L.append("|---|---|")
    L.append("| S-1.x 被引总次数 | %d |" % total_cites)
    L.append("| 落在**能重指**的条款上 | **%d**（%.0f%%） |" % (saved, 100.0 * saved / max(total_cites, 1)))
    L.append("| 落在 201 条里、但**配不上**（要退役） | %d |" % (dead_cites - saved))
    L.append("")
    L.append("## 三、一对多（同一条新记录被多条旧条款指向）\n")
    if collide:
        L.append("共 **%d** 个新记录被 ≥2 条旧条款指向（重建时的重复登记/同素材多次反馈）：\n" % len(collide))
        L.append("| 新记录 | 被几条旧条款指向 | 旧条款 |")
        L.append("|---|---|---|")
        for rec, n in sorted(collide.items(), key=lambda x: -x[1])[:12]:
            arts = [r["article_no"] for r in mapped if r["candidates"][0]["new_rec"] == rec]
            L.append("| `%s` | %d | %s |" % (rec, n, "、".join(arts)))
        L.append("\n⚠️ 这是**正常**的：旧表把同一条反馈按素材类型存过多份（`图片/视频/文案`），重建后并成一条。"
                 "重映射允许一对多，但**报告引用时会撞号**（同一段依据挂两个条款号）⇒ 人裁时要么合并、要么保留两条都指同一记录。")
    else:
        L.append("无。")
    L.append("")
    L.append("## 四、明细（前 40 行）\n")
    L.append("| 条款 | 档 | 新记录 | 新字段 | 旧正文（截） | 新正文（截） |")
    L.append("|---|---|---|---|---|---|")
    for r in sorted(out, key=lambda x: (0 if x["candidates"] else 1,
                                        x["tier"].startswith("歧义"),
                                        x["article_no"] or ""))[:40]:
        c = (r["candidates"] or [{}])[0]
        L.append("| %s | %s | `%s` | `%s` | %s | %s |" % (
            r["article_no"], r["tier"], c.get("new_rec") or "—", c.get("new_field") or "—",
            (r["text_head"] or "").replace("|", "\\|")[:48],
            (c.get("text_head") or "—").replace("|", "\\|")[:48]))
    L.append("")
    L.append("## 五、边界（别当结论用）\n")
    L.append("1. 本件**只配对、不判断**「是不是同一张图/同一条反馈」—— B/C 档只是文本像，"
             "同素材不同反馈会被配上，**必须人看**。")
    L.append("2. 配上的新锚点**改指向字段**（旧 `原文反馈` → 新 `具体原因/分析` 等），"
             "`cite_check.source_sha256` 必须换成**目标单元的 `source_sha256`**，脚本已给出该值。")
    L.append("3. 本件没动 `kb/l3/rejected.jsonl` 那 240 行（同源失效）—— 它们可按同一张"
             "「旧记录→新记录」映射表改写，但要另做，且属写库动作。")
    L.append("4. 本件没做任何 `--apply`；落盘要另行报批。")
    open(OUT_MD, "w", encoding="utf-8").write("\n".join(L) + "\n")

    print("旧侧 %d 条 ｜ 新侧 %d 单元 / %d 记录" % (len(old), len(new), len(by_rec)))
    for k in ("A", "B", "C", "并列·同内容", "并列·人裁", "D"):
        print("  %-4s %d" % (k, stats[k]))
    print("可重指 %d/%d ｜ 必须退役 %d ｜ 覆盖记录 %d ｜ 一对多 %d 个记录"
          % (len(mapped), len(old), len(none), covered_recs, len(collide)))
    print("引用面：S-1.x 共 %d 次，可恢复 %d 次（%.0f%%）" % (total_cites, saved, 100.0 * saved / max(total_cites, 1)))
    print("产物：%s\n     %s" % (os.path.basename(OUT_MD), os.path.basename(OUT_JSONL)))


if __name__ == "__main__":
    main()
