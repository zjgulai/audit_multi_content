#!/usr/bin/env python3
"""kb/versions/VERSIONS.md 投影器：由 versions.jsonl 生成，不手工维护。

用法：python3 kb/.work/emit_versions.py
幂等：同一份 versions.jsonl 反复运行，输出逐字节一致。
"""
import json, os

VJ = "kb/versions/versions.jsonl"
MD = "kb/versions/VERSIONS.md"

HEADER = [
    "# 版本指针流水（append-only）",
    "# 本文件只放指针，不放内容副本；每行一条 JSON，主键 version_id。",
    "# 两层版本号，不要混成一个字段：",
    "#   kb_version  —— 每类库独立，如 external_standard: v3",
    "#   release_id  —— 组合发布号，如 rel-0007",
    "# L0 原始库阶段不生成任何版本号、不做发布，本文件保持零版本行。",
]


def ensure_source():
    if not os.path.exists(VJ):
        os.makedirs(os.path.dirname(VJ), exist_ok=True)
        with open(VJ, "w", encoding="utf-8") as fh:
            fh.write("\n".join(HEADER) + "\n")


def parse():
    rows, notes = [], []
    for line in open(VJ, encoding="utf-8"):
        s = line.strip()
        if not s:
            continue
        if s.startswith("#"):
            notes.append(s.lstrip("# ").rstrip())
        else:
            rows.append(json.loads(s))
    return rows, notes


def project(rows, notes):
    out = ["# 版本清单（VERSIONS）", "",
           "> 本文件由 `versions.jsonl` 投影生成，**不许手工维护**。重建命令：",
           "> `python3 kb/.work/emit_versions.py`（重跑同一条投影逻辑，逐字节一致）。", ""]
    out += ["## 文件头部说明（来自 versions.jsonl 注释行）", ""]
    for n in notes:
        out.append(f"- {n}")
    out += ["", "## 版本行", ""]
    if not rows:
        out += ["当前 **0 条版本行**。L0 原始库阶段不生成版本号、不做发布。", ""]
    else:
        out += ["| version_id | kb_version | release_id | 时间 | 说明 |", "|---|---|---|---|---|"]
        for r in rows:
            out.append(f"| {r.get('version_id','')} | {r.get('kb_version','')} | "
                       f"{r.get('release_id','')} | {r.get('created_at','')} | {r.get('note','')} |")
        out.append("")
    out += ["## 计数器", "",
            f"- kb_version（按库）：{len({r.get('kb_version') for r in rows if r.get('kb_version')})} 个",
            f"- release_id（组合发布号）：{len({r.get('release_id') for r in rows if r.get('release_id')})} 个",
            f"- 版本行总数：{len(rows)}",
            ""]
    return "\n".join(out)


if __name__ == "__main__":
    ensure_source()
    rows, notes = parse()
    with open(MD, "w", encoding="utf-8") as fh:
        fh.write(project(rows, notes))
    print(f"VERSIONS.md 重建完成：{len(rows)} 条版本行")
