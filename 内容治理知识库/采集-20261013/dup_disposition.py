#!/usr/bin/env python3
"""①b 存量 95 组重复条款号：出**机器判定表**。

## 裁决规则（取自 S-1.159 / S-1.296 的先例）

  1. **anchor 活着的那条留；anchor 指向的记录在飞书已不存在的，销。**
     依据：anchor 死了，报告里那条「可点直链」就永远点不开 ⇒ 留着它只会持续产出死链。
  2. **两条都活** ⇒ 机器**判不了**，标 `需人裁`（可能两条都该留，是近重复不是真重复）。
  3. **两条都死** ⇒ 也判不了，标 `需人裁`（得先做 L0 重对齐才知道该指哪）。

## 产出

  `out/dup_disposition.json`：
    { "void": {旧号: 保留号}, "keep": [...], "need_human": [...], "stats": {...} }
  本件**只判定、不落盘** —— 销号由 `apply_dup_disposition.py --apply` 执行。
"""
import json, os, re, subprocess, collections, sys

HERE = os.path.dirname(__file__)
ROOT = os.path.abspath(os.path.join(HERE, ".."))
OUT = os.path.join(HERE, "out")
LARK = os.path.expanduser("~/.dsh/bin/lark-cli")

# 表的 `#<表名>/<record_id>/...` → (base_token, table_id)
ANCHOR_TABLE = {
    "正面和负面样本": ("GnRZbIuXraCzf0sGr2UcmZ62nfc", "tbld8qE92YaY38Yz"),
    "负面样本": ("GnRZbIuXraCzf0sGr2UcmZ62nfc", "tbld8qE92YaY38Yz"),
    "广告文案明细": ("Lk3Qb8y2QaVyZns6gprcVNE9nA0", "tblcbk4XiW6471YN"),
    "品线内容边界规则库": ("Lk3Qb8y2QaVyZns6gprcVNE9nA0", "tblD1MiUK1v5fdjD"),
    "W1卖点表达边界（品线反馈0910）": ("Lk3Qb8y2QaVyZns6gprcVNE9nA0", "tblqUTAKFkWheU49"),
    "风险文案改写建议库（分型号分渠道）": ("Lk3Qb8y2QaVyZns6gprcVNE9nA0", "tblLxUfPz4Wqp2na"),
    "数据表": ("N2qkb2YxuatqGLsa4U4cFQxgnCe", "tblGFyycMc45RMga"),
    "专家修订汇总表": ("SKkkbdZi9aRuMzs7ob0cpSYHnQg", "tbl8AI00JZO1iZtp"),
    "内容公式（仅供参考）": ("SKkkbdZi9aRuMzs7ob0cpSYHnQg", "tblVdl0jdK9G4ld3"),
    "材料收集": ("GnRZbIuXraCzf0sGr2UcmZ62nfc", "tblMGtPfe8ZUsEdP"),
}
ANCHOR_RE = re.compile(r"^#([^/]+)/(rec[A-Za-z0-9]{11})/")


def load_canon():
    rows = []
    for form in ("sample_case", "scoped_clause"):
        p = os.path.join(ROOT, "kb/l4/canonical", f"{form}.jsonl")
        if not os.path.exists(p):
            continue
        for line in open(p, encoding="utf-8"):
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def liveness(anchor):
    """返回 ('live'|'dead'|'unknown', 说明)。"""
    m = ANCHOR_RE.match(str(anchor or ""))
    if not m:
        return "unknown", "anchor 形态不认"
    tname, rid = m.group(1), m.group(2)
    bt = ANCHOR_TABLE.get(tname)
    if not bt:
        return "unknown", f"未登记的表名 {tname}"
    r = subprocess.run([LARK, "base", "+record-get", "--base-token", bt[0],
                        "--table-id", bt[1], "--record-id", rid,
                        "--profile", "dsh-kb", "--as", "bot"],
                       capture_output=True, text=True)
    out = r.stdout or ""
    if "record_not_found=1" in out or "Record not found" in out:
        return "dead", f"{tname}/{rid} 不存在"
    if '"ok": true' in out or "count=" in out:
        return "live", f"{tname}/{rid} 存在"
    return "unknown", f"{tname}/{rid} 读取异常"


def main():
    ledger = os.path.join(ROOT, "kb/l7/registry/l4-known-duplicates.yaml")
    try:
        import yaml
        d = yaml.safe_load(open(ledger, encoding="utf-8")) or {}
        groups = d.get("known_duplicate_groups") or []
    except Exception as e:
        print("读已知清单失败:", e); sys.exit(3)
    print(f"已知重复组 {len(groups)} 组")

    by_no = {}
    for r in load_canon():
        by_no.setdefault(r.get("article_no"), r)

    cache, void, need_human, keep = {}, {}, [], []
    for g in groups:
        nos = g.get("article_nos") or []
        info = []
        for n in nos:
            r = by_no.get(n)
            if not r:
                info.append({"no": n, "live": "unknown", "why": "canonical 里找不到"}); continue
            a = r.get("anchor")
            if a not in cache:
                cache[a] = liveness(a)
            info.append({"no": n, "live": cache[a][0], "why": cache[a][1], "anchor": a})
        live = [x for x in info if x["live"] == "live"]
        dead = [x for x in info if x["live"] == "dead"]
        if len(live) >= 1 and len(dead) >= 1:
            keeper = live[0]["no"]
            for x in dead:
                void[x["no"]] = keeper
            keep.append(keeper)
        else:
            need_human.append({"key": g.get("key"), "form": g.get("form"),
                               "members": info,
                               "why": "全活" if live and not dead else ("全死" if dead and not live else "含未判定")})
        print(f"  [{g.get('form')}] {nos[:3]}… live={len(live)} dead={len(dead)}", flush=True)

    stats = {"groups": len(groups), "void": len(void), "keep": len(set(keep)),
             "need_human": len(need_human)}
    json.dump({"void": void, "keep": sorted(set(keep)), "need_human": need_human,
               "stats": stats},
              open(os.path.join(OUT, "dup_disposition.json"), "w"),
              ensure_ascii=False, indent=1)
    print("\n=== 判定结果 ===")
    for k, v in stats.items():
        print(f"   {k}: {v}")
    print("\n-> out/dup_disposition.json")


if __name__ == "__main__":
    main()
