#!/usr/bin/env python3
"""生成 kb/l7/registry/l4-known-duplicates.yaml —— 把当前已有的重复组登记为「已知·待人裁」。

为什么必须有这个清单：判据 `check_clause_no_idempotency.py` 一上线就有 95 组是红的。
**红的判据没人看** —— 要么被忽略、要么被绕过。按本库既有惯例
（`l0-expected-diffs.yaml` / `l3-known-drift.yaml` / `regression-known-drift.yaml`），
把**存量**登记成已知，判据只对**新增**变红。

★ 登记 ≠ 认可。清单头部逐字写明「这些是待裁的存量缺陷，不是通过」。
"""
import json, os, subprocess, sys, datetime, collections

HERE = os.path.dirname(__file__)
ROOT = os.path.abspath(os.path.join(HERE, ".."))
LEDGER = os.path.join(ROOT, "kb/l7/registry/l4-known-duplicates.yaml")
CHECK = os.path.join(ROOT, "kb/l8/check_clause_no_idempotency.py")


def main(apply=False):
    r = subprocess.run([sys.executable, CHECK, "--json"], capture_output=True, text=True)
    i = r.stdout.find("{")
    if i < 0:
        print("判据没输出 JSON：", r.stdout[:300], r.stderr[:300]); sys.exit(3)
    # 判据在 JSON 之后还会打一行中文提示 ⇒ 用 raw_decode 只取对象
    d, _ = json.JSONDecoder().raw_decode(r.stdout[i:])
    red = d["red"]
    print(f"当前未处理的重复组: {len(red)}")
    form = collections.Counter(x["form"] for x in red)
    print("  按形态:", dict(form))

    lines = [
        "meta:",
        "  file: kb/l7/registry/l4-known-duplicates.yaml",
        "  answers: 哪些「同内容两个条款号」是已知存量（待人裁），哪些是新增",
        "  checker: kb/l8/check_clause_no_idempotency.py",
        "  checker_selftest: python3 kb/l8/check_clause_no_idempotency.py --selftest",
        f"  registered_at: '{datetime.date.today().isoformat()}'",
        "  registered_by: DSH agent（2026-10-14 销号 S-1.159 时一并建）",
        "",
        "# ══════════════════════════════════════════════════════════════════════",
        "# ★★ 这份清单**不是通过名单** —— 它登记的是**已确认存在、尚未裁决**的重复发号。",
        "#",
        "# 为什么要它：判据上线时存量就有 95 组重复，一上线就红一片。",
        "#   **红的判据没人看** —— 于是存量登记为已知，判据只对**新增**重复变红。",
        "#   这与本库既有惯例一致（l0-expected-diffs / l3-known-drift / regression-known-drift）。",
        "#",
        "# 每一条都指向一个必须人裁的问题：**同一内容两个条款号，销哪个？**",
        "#   本件不替人裁 —— 销号会改已发号的 canonical，且两边各有取舍",
        "#   （旧号 anchor 可能已死、新号正文可能被截断，见 S-1.159/S-1.296 的先例）。",
        "#",
        "# 退场条件：某组被裁决并做了 supersede 标记（两侧齐）⇒ 从本清单删掉，",
        "#   判据会在「已销号」那一档里把它计入。**清单应当单调缩短。**",
        "# ══════════════════════════════════════════════════════════════════════",
        "",
        "known_duplicate_groups:",
    ]
    for x in sorted(red, key=lambda y: (y["form"], y["article_nos"][0])):
        nos = ", ".join(f'"{n}"' for n in x["article_nos"])
        lines.append(f"  - key: {x['key']}")
        lines.append(f"    form: {x['form']}")
        lines.append(f"    article_nos: [{nos}]")
        lines.append(f"    note: 同内容多号，待裁销哪个（{len(x['article_nos'])} 个号）")
    lines.append("")

    text = "\n".join(lines)
    if not apply:
        print(f"\n[预演] 将写 {len(red)} 组到 {os.path.relpath(LEDGER, ROOT)}，未落盘。加 --apply。")
        return
    with open(LEDGER, "w", encoding="utf-8") as fh:
        fh.write(text)
    print(f"\n已写 {os.path.relpath(LEDGER, ROOT)}（{len(red)} 组）")

    r2 = subprocess.run([sys.executable, CHECK], capture_output=True, text=True)
    print(r2.stdout[-400:])
    print("判据退出码:", r2.returncode)


if __name__ == "__main__":
    main(apply="--apply" in sys.argv)
