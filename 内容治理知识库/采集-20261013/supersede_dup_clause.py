#!/usr/bin/env python3
"""① 销重复条款号：S-1.159（旧）→ 由 S-1.296（新）取代。

## 判据（为什么留 S-1.296、销 S-1.159）

| | S-1.159 | S-1.296 |
|---|---|---|
| `anchor` | `#正面和负面样本/recvw2wE9M0tak/原文反馈` —— **该 record 在飞书已 `Record not found`** | `#负面样本/recvw7XIUgkQRI/具体原因/分析` —— **实读命中** |
| `observed_at` | 20260924-1230 | 20261008-ALIGN（更新） |
| `material_type` | 视频（**错**：原件是「社群9月Melissa直播**海报**×4张」） | 图片（对） |
| `reason_analysis` | 逐字相同 | 逐字相同 |
| `sample_body` | 1136 字（全） | 353 字（**是前者的严格前缀，截断了**） |

⇒ 留**锚点活着**的那条（S-1.296）；S-1.159 **不删、只标**（保留可追溯）。

## 两条纪律

1. **不删行**：销号是加标记，不是删数据 —— 删了就再也查不到「它曾经发过这个号」。
2. **必须有入边**：被取代方标 `superseded_by`，取代方标 `supersedes`，两边都写、且不成环
   （kb_check 的「超集完整性」要这个形状）。

★ 已知未修（另单）：S-1.296 的 `sample_body` 被截断成 353 字，
   完整值在 S-1.159 的 `sample_body` 里（1136 字）。**本件不动正文**，只销号。
"""
import json, os, shutil, sys, datetime

HERE = os.path.dirname(__file__)
ROOT = os.path.abspath(os.path.join(HERE, ".."))
STAMP = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
BACKUP = os.path.join(HERE, f"backup_l4_l3_{STAMP}")
OLD, NEW = "S-1.159", "S-1.296"
TARGETS = ["kb/l4/canonical/sample_case.jsonl", "kb/l3/candidates/sample_cases.jsonl"]


def main(apply=False):
    plan = []
    for rel in TARGETS:
        p = os.path.join(ROOT, rel)
        if not os.path.exists(p):
            print("缺文件:", rel); continue
        lines = open(p, encoding="utf-8").read().splitlines()
        n_old = n_new = 0
        for i, ln in enumerate(lines):
            if not ln.strip():
                continue
            o = json.loads(ln)
            if o.get("article_no") == OLD:
                n_old += 1
            elif o.get("article_no") == NEW:
                n_new += 1
        plan.append((rel, n_old, n_new, len(lines)))
        print(f"  {rel}: {OLD} ×{n_old} ｜ {NEW} ×{n_new} ｜ 共 {len(lines)} 行")

    if not apply:
        print("\n[预演] 未写盘。加 --apply 才落盘。")
        return

    os.makedirs(BACKUP, exist_ok=True)
    for rel, n_old, n_new, _ in plan:
        p = os.path.join(ROOT, rel)
        bp = os.path.join(BACKUP, rel)
        os.makedirs(os.path.dirname(bp), exist_ok=True)
        shutil.copy2(p, bp)

        out = []
        for ln in open(p, encoding="utf-8").read().splitlines():
            if not ln.strip():
                out.append(ln); continue
            o = json.loads(ln)
            if o.get("article_no") == OLD:
                o["status"] = "superseded"
                o["superseded_by"] = [NEW]
                o["superseded_at"] = datetime.date.today().isoformat()
                o["superseded_reason"] = (
                    "与 S-1.296 是**同一条反例**：`reason_analysis` 逐字相同、原件同为"
                    "「【9.21】社群9月Melissa直播海报*4张」。本号 anchor 指向的 record "
                    "`recvw2wE9M0tak` 在飞书源表整体重建后已不存在（`Record not found`），"
                    "且 `material_type` 标成「视频」与原件（海报/图片）相悖 ⇒ 由 S-1.296 取代。"
                    "2026-10-14 销号，不删行。")
            elif o.get("article_no") == NEW:
                o["supersedes"] = sorted(set(list(o.get("supersedes") or []) + [OLD]))
            out.append(json.dumps(o, ensure_ascii=False))

        tmp = p + ".swtmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write("\n".join(out) + "\n")
        os.replace(tmp, p)

        # 回读复核
        back = [json.loads(x) for x in open(p, encoding="utf-8") if x.strip()]
        so = [x for x in back if x.get("article_no") == OLD]
        sn = [x for x in back if x.get("article_no") == NEW]
        assert so and so[0].get("status") == "superseded", "被取代方没标上"
        assert so[0].get("superseded_by") == [NEW], "被取代方缺入边"
        assert OLD in (sn[0].get("supersedes") or []), "取代方没有 supersedes 入边"
        print(f"  ✅ {rel}: 行数 {len(back)}（原 {len([x for x in open(bp,encoding='utf-8') if x.strip()])}）")

    print(f"\n备份在 {os.path.relpath(BACKUP, ROOT)}")
    print(f"销号完成：{OLD} → superseded_by {NEW}")


if __name__ == "__main__":
    main(apply="--apply" in sys.argv)
