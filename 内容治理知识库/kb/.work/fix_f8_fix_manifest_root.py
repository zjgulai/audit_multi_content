#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""F8 回填后置 · 把 manifest 的 root / absPath 指到**真实视图路径**并复算 version。

背景：生成器把 `--out` 写进 manifest 的 `root`。历史上的取值是 `/tmp/l8-view-staging`
（一个早已不存在的 staging 路径），`absPath` 也跟着指向那里 —— 与 manifest 同一目录下的
`docs[]` 其实是对**当前视图**的描述。这属于「台账说的位置不是真位置」，一并纠正。

version 的算法与生成器逐字一致：排除 metaJson / text / content 后整体 sha256。
.json 不受 trld 信封影响，python 写安全。

用法：python3 kb/.work/fix_f8_fix_manifest_root.py [--dry-run]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os

KB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VIEW = os.path.join(KB, "view")
MAN = os.path.join(VIEW, "_meta", "manifest.json")


def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    m = json.load(open(MAN, encoding="utf-8"))
    old_root = m.get("root")
    new_root = VIEW
    if old_root == new_root:
        print(f"root 已是真实路径：{new_root}")
    else:
        print(f"root: {old_root}  →  {new_root}")
    m["root"] = new_root
    m["rootExists"] = os.path.isdir(new_root)

    changed = 0
    for d in m["docs"]:
        want = os.path.join(new_root, d["relPath"])
        if d.get("absPath") != want:
            changed += 1
        d["absPath"] = want
    print(f"absPath 修正 {changed} 条")

    old_ver = m.get("version")
    m["version"] = sha256_text(json.dumps({
        "collections": m["collections"],
        "docs": [{k: v for k, v in d.items() if k not in ("metaJson", "text", "content")}
                 for d in m["docs"]],
    }, ensure_ascii=False, sort_keys=True))
    print(f"version: {str(old_ver)[:16]}…  →  {m['version'][:16]}…")

    if a.dry_run:
        print("[dry-run] 不写盘")
        return 0
    json.dump(m, open(MAN, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("✅ 已写回 manifest.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
