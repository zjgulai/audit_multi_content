#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把两个目录的文件清单 + 原文落到一份 md 里，供人工对照。
用法: /usr/bin/python3 _dump_dirs.py
"""
import os, sys, hashlib, subprocess, datetime

WS = "/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理"
UP2 = "/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试"
OUT = os.path.join(WS, "_dump-20260930")

TEXT_EXT = {".md", ".txt", ".py", ".js", ".mjs", ".cjs", ".json", ".jsonl", ".yaml", ".yml",
            ".csv", ".sh", ".pl", ".rb", ".sql", ".mmd", ".bak", ".html", ".svg", ".toml",
            ".ini", ".cfg", ".log", ""}
SKIP_NAME = {"profile-boot-BTzzdrGY.js.bak"}  # 单独判断（其实是 js 备份，仍算文本）


def is_text(p):
    ext = os.path.splitext(p)[1].lower()
    if ext in (".png", ".jpg", ".jpeg", ".webp", ".gif", ".zip", ".xlsx", ".xls", ".pdf",
               ".docx", ".npy", ".bin", ".pyc"):
        return False
    if ext in TEXT_EXT:
        return True
    # 形如 xxx.py.bak-20260923-180844 的备份：按去掉 .bak-<时间戳> 后的真实扩展名判
    import re as _re
    m = _re.match(r"^(.*)\.bak-\d{8}-\d{6}$", p)
    if m:
        return os.path.splitext(m.group(1))[1].lower() in TEXT_EXT
    return False


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for b in iter(lambda: fh.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def size(p):
    return os.path.getsize(p)


def mtime(p):
    return datetime.datetime.fromtimestamp(os.path.getmtime(p)).strftime("%Y-%m-%d %H:%M")


def read_text(p):
    try:
        return open(p, encoding="utf-8").read()
    except UnicodeDecodeError:
        return open(p, encoding="latin-1").read()


def lang_of(p):
    ext = os.path.splitext(p)[1].lower().lstrip(".")
    return {"md": "md", "py": "python", "js": "javascript", "mjs": "javascript",
            "json": "json", "jsonl": "json", "yaml": "yaml", "yml": "yaml",
            "sh": "bash", "pl": "perl", "rb": "ruby", "sql": "sql",
            "html": "html", "svg": "xml", "csv": "csv", "mmd": "mermaid",
            "txt": "", "": ""}.get(ext, ext)


# ── 目录 A：root-skills-eval 全量
A = os.path.expanduser("~/.dsh/skills/root-skills-eval")

# ── 目录 B：../../ 顶层直系文件（不含递归）
B = UP2
B_SKIP_DIRS = {"知识库"}   # 知识库/ 就是 cwd 自身，不重复 dump


def walk_full(root):
    rows = []
    for dp, dns, fns in os.walk(root):
        dns.sort()
        for fn in sorted(fns):
            rows.append(os.path.join(dp, fn))
    return rows


def top_level_files(root):
    rows = []
    for name in sorted(os.listdir(root)):
        p = os.path.join(root, name)
        if os.path.isfile(p):
            rows.append(p)
    return rows


def top_level_dirs(root):
    return sorted(n for n in os.listdir(root) if os.path.isdir(os.path.join(root, n)))


def emit_section(out, title, files, root, preview_over=None):
    out.append(f"\n---\n\n## {title}\n")
    out.append(f"根目录：`{root}`　文件数：**{len(files)}**\n")
    out.append("| # | 相对路径 | 字节 | 修改时间 | sha256(前16) | 类型 |")
    out.append("|---|---|---|---|---|---|")
    for i, p in enumerate(files, 1):
        rel = os.path.relpath(p, root)
        kind = "文本" if is_text(p) else "二进制"
        out.append(f"| {i} | `{rel}` | {size(p)} | {mtime(p)} | `{sha(p)[:16]}` | {kind} |")
    out.append("")
    for i, p in enumerate(files, 1):
        rel = os.path.relpath(p, root)
        sz = size(p)
        out.append(f"\n### {title.split('·')[-1].strip()} [{i}/{len(files)}] `{rel}`\n")
        out.append(f"- 字节：{sz}　修改：{mtime(p)}　sha256：`{sha(p)}`")
        if not is_text(p):
            out.append(f"- **二进制/非文本，不贴原文**（{os.path.splitext(p)[1] or '无扩展名'}）\n")
            continue
        txt, notes = mask(rel, read_text(p))
        for n in notes:
            out.append(f"- 🔒 **脱敏**：{n}")
        if preview_over and sz > preview_over:
            head = txt[:preview_over]
            out.append(f"- **文件 {sz} 字节，超过 {preview_over} 字节阈值 → 只贴前 {preview_over} 字节**"
                       f"（完整文件在磁盘原位，路径见上）\n")
            out.append("```" + lang_of(p))
            out.append(head)
            out.append("```")
            out.append(f"\n…（后略 {sz - preview_over} 字节）\n")
            continue
        out.append("```" + lang_of(p))
        out.append(txt)
        out.append("```")


# ── 凭据脱敏（只影响本 dump 副本，磁盘原文一个字节都不动）──────────────
def mask(rel, txt):
    """返回 (可能被打码的文本, 打码说明列表)。"""
    notes = []
    if rel == ".lark-device-code.txt":
        notes.append("整个文件内容是一枚**飞书设备授权码**（活凭据），本 dump 不贴原值")
        return "<REDACTED 飞书设备授权码：完整值见磁盘原位 .lark-device-code.txt>\n", notes
    if rel == "exec_probe.py":
        old = txt
        txt = txt.replace('"password": "Vicky"', '"password": "<REDACTED:测试夹具口令>"')
        txt = txt.replace('"password": "WRONG"', '"password": "<REDACTED:测试夹具口令>"')
        txt = txt.replace('"password": "pass', '"password": "<REDACTED:测试夹具口令>')
        if txt != old:
            notes.append("硬编码的**测试夹具口令**已打码（其余逐字保留）")
    return txt, notes


def emit_inventory(out, title, files, root):
    out.append(f"\n---\n\n## {title}\n")
    out.append(f"根目录：`{root}`　文件数：**{len(files)}**\n")
    out.append("| # | 相对路径 | 字节 | 修改时间 | sha256(前16) | 类型 |")
    out.append("|---|---|---|---|---|---|")
    for i, p in enumerate(files, 1):
        rel = os.path.relpath(p, root)
        kind = "文本" if is_text(p) else "二进制"
        out.append(f"| {i} | `{rel}` | {size(p)} | {mtime(p)} | `{sha(p)[:16]}` | {kind} |")
    out.append("")


def main(mode="both", preview_over=None, only=None):
    os.makedirs(OUT, exist_ok=True)
    A_files = walk_full(A)
    B_files = top_level_files(B)

    header = []
    header.append("# 两目录清单与原文（对照用）\n")
    header.append(f"生成时间：{datetime.datetime.now():%Y-%m-%d %H:%M:%S}\n")
    header.append("工作目录（= `../../知识库/内容治理`）：\n")
    header.append(f"`{WS}`\n")
    header.append("\n口径声明（先说清楚，避免误读）：\n")
    header.append(f"1. **目录 A** = `~/.dsh/skills/root-skills-eval/`，**递归全量**，"
                  f"共 {len(A_files)} 个文件。")
    header.append(f"2. **目录 B** = `../../` = `{B}`，**只列顶层直系文件**，共 {len(B_files)} 个、"
                  f"{len(top_level_dirs(B))} 个子目录；子目录**不递归**"
                  f"（该目录递归下去有 77,789 个文件，且 `知识库/` 就是本次工作目录本身）。")
    header.append("3. 二进制（.png/.zip/.xlsx 等）只登记元数据，不贴原文。")
    header.append("4. 脱敏只动本 dump 副本；**磁盘原文一个字节未改**。仅 2 处："
                  "`.lark-device-code.txt`（活凭据，整文件不贴值）、`exec_probe.py`（硬编码测试夹具口令）。")
    out = []

    if only == "A":
        out += header
        emit_section(out, "目录 A · `~/.dsh/skills/root-skills-eval/` 全量递归", A_files, A)
        p = os.path.join(OUT, "A-root-skills-eval-全量原文.md")
    elif only == "B":
        out += header
        emit_section(out, "目录 B · `../../` 顶层直系文件", B_files, B, preview_over=preview_over)
        out.append("\n---\n\n## 目录 B 的子目录（只列名，未递归）\n")
        out.append("| 子目录 |")
        out.append("|---|")
        for d in top_level_dirs(B):
            out.append(f"| `{d}/` |")
        p = os.path.join(OUT, "B-上层目录-顶层文件原文.md")
    else:
        out += header
        out.append("\n---\n\n# 第一部分：清单（两个目录）\n")
        emit_inventory(out, "目录 A · `~/.dsh/skills/root-skills-eval/` 清单", A_files, A)
        emit_inventory(out, "目录 B · `../../` 顶层直系文件清单", B_files, B)
        out.append("\n---\n\n## 目录 B 的子目录（只列名，未递归）\n")
        out.append("| 子目录 |")
        out.append("|---|")
        for d in top_level_dirs(B):
            out.append(f"| `{d}/` |")
        out.append("\n---\n\n# 第二部分：目录 A 原文（全量）\n")
        emit_section(out, "目录 A · `~/.dsh/skills/root-skills-eval/` 全量递归", A_files, A)
        out.append("\n---\n\n# 第三部分：目录 B 原文（顶层）\n")
        emit_section(out, "目录 B · `../../` 顶层直系文件", B_files, B, preview_over=preview_over)
        p = os.path.join(OUT, "两目录清单与原文-20260930.md")

    open(p, "w", encoding="utf-8").write("\n".join(out))
    print("写出:", p, size(p), "字节")
    print("A:", len(A_files), "文件 | B 顶层:", len(B_files), "文件")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "both"
    prev = int(sys.argv[2]) if len(sys.argv) > 2 else None
    main(mode=mode, preview_over=prev, only=mode if mode in ("A", "B") else None)
