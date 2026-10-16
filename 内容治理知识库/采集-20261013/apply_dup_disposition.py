#!/usr/bin/env python3
"""①b 存量重复条款号裁决：**只销「旧代死锚点」那一侧**。

## 判定依据（全部实测，不是推断）

  1. 飞书入口 Base 只有一张 `负面样本`（`tbld8qE92YaY38Yz`，174 行），
     **没有**「正面和负面样本」——那是旧表名 ⇒ 该表被**重建**过（rev 1760）。
  2. 旧代锚点（`#正面和负面样本/recvw2…`）**201 个 distinct record，0 个还在**。
     新代锚点（`#负面样本/recvw7…`）**115 个 distinct record，115 个全在**。
     ⇒ 分离是**完全**的，不用靠 ID 前缀猜。
  3. 86 组重复的 `reason_analysis` **逐字相同**（86/86），且每组恰好「一旧一新」。
  4. `source_sha256` 是**记录派生**（473 行 / 473 个不同值 / 0 组共享）
     ⇒ **重挂锚点必须重算指纹，而指纹输入 `record_fields` 本地不存 ⇒ 手改 = 伪造指纹**。
     所以本件**只销号、不重挂**；重挂走 L0→L4 重建（另报）。

## 为什么销旧留新

  同 S-1.159/S-1.296 先例：**anchor 死了，报告里那条直链就永远点不开**。
  销的是**标记**（`status=superseded` ＋ `superseded_by`），**不删行** ⇒
  已有报告里对旧号的引用照样解析得到，并从 `superseded_by` 走到活号。

## 不裁的

  · **E 组（9 组 / 48 号）**：锚点**全活**（48/48）⇒ 「留活销死」这条规则**判不了**。
    且它们的条款正文是**字段枚举值**（「产后0-6月、产后6-12月…」），不是规则
    ⇒ 根因在 L3 蒸馏把枚举字段当条款发号，**交人裁**。
  · **115 条旧代孤儿行**（非重复、锚点死、内容仍在源表）⇒ 需重挂，**不销**。

用法：
  python3 采集-20261013/apply_dup_disposition.py            # 判定 + 出表，不落盘
  python3 采集-20261013/apply_dup_disposition.py --apply     # 真落标记
"""
import argparse, json, os, re, shutil, subprocess, sys, datetime, collections

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
OUT = os.path.join(HERE, "out")
LARK = os.path.expanduser("~/.dsh/bin/lark-cli")
CANON = os.path.join(ROOT, "kb/l4/canonical/sample_case.jsonl")
SCOPED = os.path.join(ROOT, "kb/l4/canonical/scoped_clause.jsonl")
REGISTRY = os.path.join(ROOT, "kb/l7/registry/l4-known-duplicates.yaml")
TODAY = datetime.date.today().strftime("%Y%m%d")

OLD_TABLE_MARK = "#正面和负面样本/"
NEW_TABLE_MARK = "#负面样本/"
REC = re.compile(r"/?(rec[A-Za-z0-9]{11})/")


def sh(cmd):
    return subprocess.run(cmd, capture_output=True, text=True)


def live_records(base, table):
    r = sh([LARK, "base", "+record-list", "--base-token", base, "--table-id", table,
            "--page-size", "200", "--profile", "dsh-kb", "--as", "bot"])
    if r.returncode != 0:
        print("拉表失败:", r.stderr[:400]); sys.exit(3)
    return set(re.findall(r"^\|\s*(rec[A-Za-z0-9]+)\s*\|", r.stdout, re.M))


def load_jsonl(p):
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]


def write_jsonl(p, rows):
    """jsonl 不受信封影响，但仍走临时件 + 原子替换。"""
    tmp = p + ".swtmp"
    with open(tmp, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    os.replace(tmp, p)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    import yaml
    reg = yaml.safe_load(open(REGISTRY, encoding="utf-8"))
    groups = reg["known_duplicate_groups"]
    S = [g for g in groups if g["form"] == "sample_case"]
    E = [g for g in groups if g["form"] == "scoped_clause"]

    sc_rows = load_jsonl(CANON)
    by_no = {r["article_no"]: r for r in sc_rows}
    live = live_records("GnRZbIuXraCzf0sGr2UcmZ62nfc", "tbld8qE92YaY38Yz")
    print(f"负面样本 活记录 {len(live)} ｜ S 组 {len(S)} ｜ E 组 {len(E)}")

    # ── 前置校验：任一条不过就停，不许带着错前提落盘 ──
    bad = []
    void, keep, groups_ok = {}, [], []
    for g in S:
        # ★ 按 anchor 分类，**不按列表位置** —— 登记表里号码没按新旧排序。
        #   第一版按位置取 [0]/[1]，被下面的前置校验挡下 35 组：错的是我的前提，不是数据。
        olds = [n for n in g["article_nos"]
                if n in by_no and OLD_TABLE_MARK in (by_no[n].get("anchor") or "")]
        news = [n for n in g["article_nos"]
                if n in by_no and OLD_TABLE_MARK not in (by_no[n].get("anchor") or "")
                and NEW_TABLE_MARK in (by_no[n].get("anchor") or "")]
        if len(olds) != 1 or len(news) != 1:
            bad.append((g["key"], f"不是「一旧一新」：旧 {olds} 新 {news}")); continue
        o, n = olds[0], news[0]
        ro, rn = by_no.get(o), by_no.get(n)
        if not ro or not rn:
            bad.append((g["key"], "行不存在")); continue
        mo, mn = REC.search(ro["anchor"]), REC.search(rn["anchor"])
        if not mo or mo.group(1) in live:
            bad.append((g["key"], f"{o} 的锚点竟然还活着")); continue
        if not mn or mn.group(1) not in live:
            bad.append((g["key"], f"{n} 的锚点竟然死了")); continue
        ko = (ro.get("reason_analysis") or "").strip()
        if not ko or ko != (rn.get("reason_analysis") or "").strip():
            bad.append((g["key"], "正文不再逐字相同")); continue
        void[o] = n; keep.append(n); groups_ok.append(g)

    print(f"前置校验：通过 {len(groups_ok)} 组 ｜ 不通过 {len(bad)} 组")
    for b in bad[:10]:
        print("   ✗", b)
    if bad:
        print("\n有组不满足前提 ⇒ 停止（不带着错前提落盘）。")
        sys.exit(3)

    # ── E 组：锚点全活 ⇒ 判不了 ──
    sc = {r["article_no"]: r for r in load_jsonl(SCOPED)}
    data_live = live_records("N2qkb2YxuatqGLsa4U4cFQxgnCe", "tblGFyycMc45RMga")
    elive = 0
    for g in E:
        for n in g["article_nos"]:
            m = REC.search(sc[n]["anchor"] or "")
            if m and m.group(1) in data_live:
                elive += 1
    e_total = sum(len(g["article_nos"]) for g in E)

    # ── 旧代孤儿行（非重复、锚点死）──
    in_void = set(void)
    orphans = [r for r in sc_rows if OLD_TABLE_MARK in (r.get("anchor") or "")]
    orphan_nondup = [r["article_no"] for r in orphans if r["article_no"] not in in_void]

    disp = {
        "generated_at": TODAY,
        "rule": "留 anchor 活的、销 anchor 死的（实测：旧代 201 个记录 0 活，新代 115 个 115 活）",
        "S_groups": {"count": len(groups_ok), "void": void, "keep": keep},
        "E_groups": {"count": len(E), "clause_count": e_total, "anchors_live": elive,
                     "verdict": "需人裁 —— 锚点全活，规则判不了；且正文是字段枚举值，根因在 L3 蒸馏"},
        "orphan_dead_anchor_rows": {"count": len(orphan_nondup), "article_nos": sorted(orphan_nondup),
                                    "verdict": "需重挂锚点，不销 —— 手改会伪造 source_sha256（记录派生，本地无法重算）"},
        "stats": {"void": len(void), "keep": len(set(keep)), "need_human_groups": len(E)},
    }
    os.makedirs(OUT, exist_ok=True)
    json.dump(disp, open(os.path.join(OUT, "dup_disposition.json"), "w"),
              ensure_ascii=False, indent=1)
    print(f"\n销 {len(void)} 个旧号 ｜ 留 {len(set(keep))} 个新号 "
          f"｜ E 组待人裁 {len(E)} 组/{e_total} 号（锚点活 {elive}）"
          f"｜ 旧代孤儿待重挂 {len(orphan_nondup)} 行")
    print("-> out/dup_disposition.json")

    if not a.apply:
        print("\n（预演。加 --apply 才落标记。）")
        return

    # ── 备份 ──
    bk = os.path.join(HERE, f"backup_dup_supersede_{datetime.datetime.now():%Y%m%d-%H%M%S}")
    os.makedirs(bk)
    shutil.copy2(CANON, bk); shutil.copy2(REGISTRY, bk)
    print("已备份 ->", os.path.relpath(bk, ROOT))

    # ── 落标记（不删行）──
    reason = ("同内容多号：`reason_analysis` 与本组存活号逐字相同；本号 anchor 指向的 record "
              "在飞书源表整体重建后已不存在（实测：旧代 201 个 record **0 个**还在），"
              "留着它只会持续产出点不开的直链 ⇒ 由存活号取代。2026-10-14 销号，不删行。")
    nvoid = 0
    for r in sc_rows:
        no = r["article_no"]
        if no in void:
            r["status"] = "superseded"
            r["superseded_by"] = [void[no]]
            r["superseded_at"] = datetime.date.today().strftime("%Y-%m-%d")
            r["superseded_reason"] = reason
            nvoid += 1
    nsup = 0
    back = collections.defaultdict(list)
    for o, n in void.items():
        back[n].append(o)
    for r in sc_rows:
        no = r["article_no"]
        if no in back:
            r["supersedes"] = sorted(set((r.get("supersedes") or []) + back[no]))
            nsup += 1
    write_jsonl(CANON, sc_rows)
    print(f"落标记：superseded {nvoid} 行 ｜ supersedes {nsup} 行 ｜ 总行数仍 {len(sc_rows)}")

    # ── 登记件退场：裁决完的组从清单删掉（清单应单调缩短）──
    done = {g["key"] for g in groups_ok}
    reg["known_duplicate_groups"] = [g for g in groups if g["key"] not in done]
    reg["meta"]["adjudicated_20261014"] = {
        "judged": len(groups_ok), "voided": nvoid, "kept": len(set(keep)),
        "rule": "留 anchor 活的、销 anchor 死的",
        "evidence": "旧代 201 个 record 0 活 / 新代 115 个 record 115 活；86/86 组正文逐字相同",
        "not_voided": {
            "scoped_clause_groups": len(E),
            "why": "E 组锚点全活，规则判不了；且条款正文是字段枚举值 ⇒ 根因在 L3 蒸馏，交人裁",
        },
    }
    tmp = REGISTRY + ".swtmp"
    with open(tmp, "w", encoding="utf-8") as f:
        yaml.safe_dump(reg, f, allow_unicode=True, sort_keys=False, width=1000)
    os.replace(tmp, REGISTRY)
    print(f"登记件退场：{len(groups)} 组 -> {len(reg['known_duplicate_groups'])} 组")


if __name__ == "__main__":
    main()
