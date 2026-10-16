#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""修复计划 F6 · 把 56 条从 L2-concepts 迁到 L1-facts 的变更同步进两份 JSON 台账。

要同步的两份：
  · `kb/view/_meta/derivation.json` —— 逐条溯源台账（path / tier / bytes / counts）
  · `kb/view/_meta/manifest.json`   —— 工作台 HTTP 取数载荷（relPath / absPath / tier /
    kind / sha256 / bytes / text / content / metaJson / counts / version）

`content` 字段必须**重算**：它是 `render_for_chunking(meta, body)` 的产物，
里面写着「档位 L2 · 判断」，不重算就会与新 frontmatter 说的「档位 L1 · 事实」自相矛盾。
重算直接用生成器自己的 `render_for_chunking` —— 保证与工作台 `frontmatter.ts` 逐字对齐的口径。

**内置自检**：先用**旧** meta + 旧正文重算一遍旧 content，必须与 manifest 里的原值逐字节一致。
不一致就中止 —— 那说明正文切法理解错了，重算出来的 content 是错的。

用法：python3 kb/.work/fix_f6_sync_json.py [--dry-run]
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import importlib.util
import json
import os
import sys

KB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VIEW = os.path.join(KB, "view")
META = os.path.join(VIEW, "_meta")
OLD_TIER = "L2-concepts"
NEW_TIER = "L1-facts"
OLD_KIND = "judgment"
NEW_KIND = "fact"


def load_generator():
    spec = importlib.util.spec_from_file_location(
        "ghl", os.path.join(KB, ".work", "gen-host-library.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)          # 有 __main__ 守卫，import 安全
    return mod


def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def split_body(text: str) -> str:
    """从落盘文本里取出 `body_text`。

    落盘形态是 `frontmatter(meta) + "\\n" + body_text + "\\n"`，而 frontmatter 以 `---\\n` 收尾，
    所以第二段之后先有一个空行、再是正文、最后还有一个换行。原样剥掉这两端的换行。
    """
    parts = text.split("---\n", 2)
    if len(parts) < 3:
        raise ValueError("取不到正文：frontmatter 分隔符不足 2 个")
    raw = parts[2]
    if raw.startswith("\n"):
        raw = raw[1:]
    if raw.endswith("\n"):
        raw = raw[:-1]
    return raw


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    ghl = load_generator()

    man_path = os.path.join(META, "manifest.json")
    der_path = os.path.join(META, "derivation.json")
    man = json.load(open(man_path, encoding="utf-8"))
    der = json.load(open(der_path, encoding="utf-8"))
    root = man.get("root")

    targets = [d for d in man["docs"] if d.get("tier") == OLD_TIER]
    print(f"manifest.docs 共 {len(man['docs'])}，其中 {OLD_TIER} 有 {len(targets)} 条")
    if not targets:
        print("没有需要迁移的条目 —— 可能已经同步过。")
        return 0

    # ── 自检：用旧 meta + 旧正文重算旧 content，必须与原值一致 ──────────────
    checked = 0
    for d in targets:
        old_meta = json.loads(d["metaJson"])
        old_body = split_body(d["text"])
        recomputed = ghl.render_for_chunking(old_meta, "\n" + old_body + "\n")
        if recomputed != d["content"]:
            print(f"❌ 自检失败：{d['relPath']}")
            print(f"   原值前 120：{d['content'][:120]!r}")
            print(f"   重算前 120：{recomputed[:120]!r}")
            print("   正文切法或渲染口径与原生成器不一致，**中止**（重算出的 content 不可信）。")
            return 2
        checked += 1
    print(f"✅ 自检通过：{checked}/{len(targets)} 条的旧 content 能逐字节复现")

    # ── 更新 manifest ──────────────────────────────────────────────────────
    for d in man["docs"]:
        if d.get("tier") != OLD_TIER:
            continue
        new_rel = d["relPath"].replace(f"/{OLD_TIER}/", f"/{NEW_TIER}/")
        abs_path = os.path.join(root, new_rel) if root else new_rel
        disk = os.path.join(VIEW, new_rel)
        if not os.path.isfile(disk):
            print(f"❌ 目标文件不存在：{disk}")
            return 3
        raw = open(disk, "rb").read()
        text = raw.decode("utf-8")
        meta = json.loads(d["metaJson"])
        meta["tier"] = "L1"
        meta["kind"] = NEW_KIND

        d["relPath"] = new_rel
        d["absPath"] = abs_path
        d["tier"] = NEW_TIER
        d["kind"] = NEW_KIND
        d["sha256"] = hashlib.sha256(raw).hexdigest()
        d["bytes"] = len(raw)
        d["text"] = text
        d["metaJson"] = json.dumps(meta, ensure_ascii=False)
        d["content"] = ghl.render_for_chunking(meta, "\n" + split_body(text) + "\n")

    man["counts"] = dict(collections.Counter(
        f"{d['collectionId']}/{d['tier']}" for d in man["docs"]))
    # version 的算法与生成器逐字一致：排除 metaJson / text / content 再整体 sha256
    man["version"] = sha256_text(json.dumps({
        "collections": man["collections"],
        "docs": [{k: v for k, v in d.items() if k not in ("metaJson", "text", "content")}
                 for d in man["docs"]],
    }, ensure_ascii=False, sort_keys=True))

    # ── 更新 derivation ────────────────────────────────────────────────────
    for e in der["entries"]:
        if e.get("tier") != OLD_TIER:
            continue
        new_rel = e["path"].replace(f"/{OLD_TIER}/", f"/{NEW_TIER}/")
        e["path"] = new_rel
        e["tier"] = NEW_TIER
        fp = os.path.join(VIEW, new_rel)
        if os.path.isfile(fp):
            e["bytes"] = os.path.getsize(fp)
    der["counts"] = dict(collections.Counter(
        f"{e['collection']}/{e['tier']}" for e in der["entries"]))

    if a.dry_run:
        print("[dry-run] 不写盘")
        print("  manifest.counts →", json.dumps(man["counts"], ensure_ascii=False))
        print("  derivation.counts →", json.dumps(der["counts"], ensure_ascii=False))
        return 0

    # 备份原件后写回（.json 不受 trld 信封影响）
    for p in (man_path, der_path):
        bak = p + ".bak-f6"
        if not os.path.exists(bak):
            open(bak, "w", encoding="utf-8").write(open(p, encoding="utf-8").read())
    json.dump(man, open(man_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump(der, open(der_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("✅ 已写回 manifest.json（备份 .bak-f6）")
    print("   counts →", json.dumps(man["counts"], ensure_ascii=False))
    print("✅ 已写回 derivation.json（备份 .bak-f6）")
    print("   counts →", json.dumps(der["counts"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
