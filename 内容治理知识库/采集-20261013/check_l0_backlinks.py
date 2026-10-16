#!/usr/bin/env python3
"""L0 回链体检（修正版）：本地 L0 件记的 record_id，在飞书源表里还存不存在。

★ 第一版有个 bug 已修：`+record-list` 默认单页 200（`--page-size` 上限也是 200），
  两张超过 200 条的表因此被读成「飞书现有 200 / 失效 195+91」——
  那个数**是把「不在第一页」误当成「已失效」**。
  改用 `--format ndjson --limit 2000` 取全量。
"""
import json, glob, re, os, subprocess, collections

HERE = os.path.dirname(__file__)
ROOT = os.path.abspath(os.path.join(HERE, ".."))
LARK = os.path.expanduser("~/.dsh/bin/lark-cli")

BASE_OF = {
    "tblMGtPfe8ZUsEdP": "GnRZbIuXraCzf0sGr2UcmZ62nfc",
    "tbld8qE92YaY38Yz": "GnRZbIuXraCzf0sGr2UcmZ62nfc",
    "tblZP8jG4tiUL98C": "GnRZbIuXraCzf0sGr2UcmZ62nfc",
    "tblcbk4XiW6471YN": "Lk3Qb8y2QaVyZns6gprcVNE9nA0",
    "tblD1MiUK1v5fdjD": "Lk3Qb8y2QaVyZns6gprcVNE9nA0",
    "tblqUTAKFkWheU49": "Lk3Qb8y2QaVyZns6gprcVNE9nA0",
    "tblLxUfPz4Wqp2na": "Lk3Qb8y2QaVyZns6gprcVNE9nA0",
    "tblGFyycMc45RMga": "N2qkb2YxuatqGLsa4U4cFQxgnCe",
    "tbl8AI00JZO1iZtp": "SKkkbdZi9aRuMzs7ob0cpSYHnQg",
    "tblVdl0jdK9G4ld3": "SKkkbdZi9aRuMzs7ob0cpSYHnQg",
}
NAME_OF = {
    "tblMGtPfe8ZUsEdP": "材料收集", "tbld8qE92YaY38Yz": "负面样本",
    "tblZP8jG4tiUL98C": "知识库分类说明", "tblcbk4XiW6471YN": "广告文案明细",
    "tblD1MiUK1v5fdjD": "品线内容边界规则库", "tblqUTAKFkWheU49": "W1卖点表达边界",
    "tblLxUfPz4Wqp2na": "风险文案改写建议库", "tblGFyycMc45RMga": "外部资料库·数据表",
    "tbl8AI00JZO1iZtp": "专家修订汇总表", "tblVdl0jdK9G4ld3": "内容公式",
}


def feishu_ids(base, table):
    """ndjson 会把记录写到**独立文件**（stdout 只有 manifest）⇒ 读 manifest 的 record_file。

    ★ 踩过的坑：`--page-size` 上限 200，两张超过 200 条的表会被读成「飞书只有 200 条」；
      而直接解析 ndjson 的 stdout 又会得到 0 条。两次都得出过错误结论，故此处写死用法。
    """
    outp = os.path.join(HERE, "out", "l0probe", f"{table}.ndjson")
    os.makedirs(os.path.dirname(outp), exist_ok=True)
    p = subprocess.run([LARK, "base", "+record-list", "--base-token", base, "--table-id", table,
                        "--limit", "2000", "--format", "ndjson", "--output", outp,
                        "--profile", "dsh-kb", "--as", "bot"],
                       capture_output=True, text=True)
    raw = p.stdout
    i = raw.find("{")
    if i < 0:
        return None, False, f"无 manifest 输出: {raw[:120]}"
    man = json.loads(raw[i:])
    rec_file = man.get("record_file") or outp
    ids = []
    if os.path.exists(rec_file):
        for line in open(rec_file, encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            try:
                o = json.loads(line)
            except Exception:
                continue
            rid = o.get("record_id") or (o.get("fields") or {}).get("record_id")
            if rid:
                ids.append(rid)
    # 兜底：manifest 自己报了条数
    declared = man.get("records_count")
    if not ids and declared:
        return None, False, f"record_file 里没读到 id（manifest 报 {declared} 条）"
    return ids, bool(man.get("has_more")), None


def main():
    rows = []
    for f in glob.glob(os.path.join(ROOT, "kb/l0/*/feishu_bitable_record__*.json")):
        try:
            d = json.load(open(f))
        except Exception:
            continue
        s = d.get("source", {}) or {}
        rows.append({"table": s.get("table_id"), "rec": s.get("record_id"),
                     "obs": d.get("observed_at"), "url": d.get("entry_url")})
    by_t = collections.defaultdict(list)
    for r in rows:
        if r["table"]:
            by_t[r["table"]].append(r)

    print(f"{'源表':<20}{'本地件':>7}{'飞书现有':>9}{'命中':>7}{'失效':>7}  对齐时刻")
    print("-" * 80)
    tot = dead_tot = 0
    dead_tables = {}
    for t, rs in sorted(by_t.items(), key=lambda x: -len(x[1])):
        local = {r["rec"] for r in rs if r["rec"]}
        base = BASE_OF.get(t)
        if not base:
            print(f"{NAME_OF.get(t,t):<20}{len(local):>7}{'—':>9}   未登记 base"); continue
        fs, trunc, err = feishu_ids(base, t)
        if fs is None:
            print(f"{NAME_OF.get(t,t):<20}{len(local):>7}{'ERR':>9}   {err}"); continue
        hit = len(local & set(fs))
        dead = len(local) - hit
        tot += len(local); dead_tot += dead
        obs = ",".join(sorted({r["obs"] for r in rs if r["obs"]}))
        warn = "  ⚠分页未取全" if trunc else ""
        flag = "  <<< 有失效" if dead else ""
        print(f"{NAME_OF.get(t,t):<20}{len(local):>7}{len(fs):>9}{hit:>7}{dead:>7}  {obs}{flag}{warn}")
        if dead:
            dead_tables[NAME_OF.get(t, t)] = (dead, len(local))
    print("-" * 80)
    print(f"合计：本地 {tot} 件，其中 {dead_tot} 件指向的记录在飞书已不存在")
    if dead_tables:
        print("\n失效集中在：")
        for k, (d, n) in dead_tables.items():
            print(f"   · {k}：{d}/{n} 失效")


if __name__ == "__main__":
    main()
