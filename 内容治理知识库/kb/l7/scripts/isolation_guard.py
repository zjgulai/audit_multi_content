#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""isolation_guard.py —— 副本隔离的**可证化**（批次22 · 第0块②）。

## 为什么要有它（一次真实事故换来的）

**2026-10-02 20:05，我在「副本」里跑 L2 验证，产物落进了真库。**
根因（**已定位到代码，见下**）不是路径拼接写错，而是：

    `kb/l7/registry/layers.yaml` 里**每一层**的 `cwd` 都是一个**写死的绝对路径**：
        cwd: ~/.dsh/Momcozy知识库
    编排器 `kb_pipeline.py:608` `cwd = home(x.get("cwd") or "")` 直接取它，
    `:711` `argv = [py, os.path.join(cwd, sp["script"])]`、`:724` `cwd=cwd`
    ⇒ **子进程的工作目录永远是那个写死的路径**，与「我在哪个副本里跑」**无关**。
    各层引擎又都用**相对路径** `kb/...` ⇒ 全部落在**真库**。
    而副本里那份 `kb/` 当然什么都没被写 —— **因此「副本跑」看起来一切正常**。

★ **结论：在这个库上，「用副本跑」在编排器路径下是无效的**（引擎根本不进副本）。
  ⇒ 那次之前所有「副本跑」的反测结论，**有效性都被动摇了**（见 `ledger-read-contract.yaml`
  的 `replica_isolation_silently_fails` 登记）。

## 三条措施（用户裁定：缺一不可）

  ① **运行前**：解析出的目标根 == 真库时**硬失败**（`exit≠0`，**不是警告**）
  ② **运行中**：写一份**隔离回执** —— 用了哪个根 + 该根的文件清单指纹
  ③ **运行后**：**真库清单**前后对照，差异必须为 0；有差异 ⇒ 报红

## 真库根怎么认（**不许**写死成「当前工作区」）

真库 = **`~/.dsh/Momcozy知识库`**（`layers.yaml` 各层 `cwd` 所指，实测与工作区 `kb/`
**inode 相同** —— `stat -f %i` 两边都是 `69082025`，即**同一实体**）。
本模块用**显式常量 + 可用环境变量覆盖**来认它，并在回执里记下判定依据。

## 用法

    kb/kbpy l7/scripts/isolation_guard.py check  --expect-replica <副本根>
    kb/kbpy l7/scripts/isolation_guard.py receipt --root <根> --out <回执路径>
    kb/kbpy l7/scripts/isolation_guard.py diff   --before <回执> --after <回执>
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
KB = os.path.dirname(os.path.dirname(HERE))              # …/kb

#: **真库根的权威落点** = `layers.yaml` 各层 `cwd` 所指（实测与工作区 kb/ 同一 inode）。
#: 不许推断成「脚本所在工作区」—— 工作区可能整个就是真库。
REAL_KB_PARENT = os.path.expanduser(os.environ.get("KB_REAL_ROOT") or "~/.dsh/Momcozy知识库")

#: 回执里记的关键件（相对 kb/），用于「清单指纹」
KEY_FILES = [
    "l0/manifest.jsonl",
    "l1/manifest_l1.jsonl",
    "l2/units.jsonl",
    "l3/manifest_l3.jsonl",
    "l3/candidates/rules.jsonl",
    "l4/canonical/rules.jsonl",
    "l5/p0_patterns.jsonl",
    "l7/registry/layers.yaml",
]


def real_root() -> str:
    return REAL_KB_PARENT


def _sha8(p: str):
    try:
        with open(p, "rb") as fh:
            h = hashlib.sha256()
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()[:16]
    except OSError:
        return None


def manifest(root: str) -> dict:
    """根的文件清单指纹：文件数 + 关键件 sha256 + 总字节。"""
    kbdir = root if os.path.basename(root.rstrip("/")) == "kb" else os.path.join(root, "kb")
    n = 0
    total = 0
    for dirpath, _dirs, files in os.walk(kbdir):
        for f in files:
            n += 1
            try:
                total += os.path.getsize(os.path.join(dirpath, f))
            except OSError:
                pass
    key = {}
    for rel in KEY_FILES:
        p = os.path.join(kbdir, rel)
        key[rel] = {"sha256_16": _sha8(p), "exists": os.path.isfile(p)}
    return {
        "kb_dir": kbdir,
        "file_count": n,
        "total_bytes": total,
        "key_files": key,
        "taken_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }


def check(expect_replica: str | None):
    """措施①：目标根 == 真库 ⇒ **硬失败**。返回 `(ok, info)`。"""
    root = expect_replica
    info = {"real_root": real_root(), "expect_replica": root,
            "resolved_real_root_kb": os.path.join(real_root(), "kb")}
    if not root:
        # 没声明副本根 ⇒ 按「本次不是副本跑」处理，只在回执里记明
        info["verdict"] = "no_replica_declared"
        return True, info
    rp = os.path.abspath(os.path.expanduser(root))
    real_kb = os.path.join(real_root(), "kb")
    # 判据用 **realpath**：软链/挂载点会让「看起来不同的路径」指向同一实体
    same = os.path.realpath(rp) == os.path.realpath(real_root()) or \
        os.path.realpath(rp) == os.path.realpath(real_kb)
    info["replica_realpath"] = os.path.realpath(rp)
    info["real_root_realpath"] = os.path.realpath(real_root())
    info["is_real_root"] = same
    if same:
        info["verdict"] = "REFUSED_IS_REAL"
        return False, info
    # 追加判据：inode 相同也判同实体（软链/硬链都躲不过）
    try:
        kbdir = rp if os.path.basename(rp.rstrip("/")) == "kb" else os.path.join(rp, "kb")
        a = os.stat(os.path.join(kbdir, "l0", "registry", "kb.json")).st_ino
        b = os.stat(os.path.join(real_kb, "l0", "registry", "kb.json")).st_ino
        info["inode_replica"] = a
        info["inode_real"] = b
        if a == b:
            info["verdict"] = "REFUSED_SAME_INODE"
            return False, info
    except OSError as e:
        info["inode_check"] = "跳过：%r" % (e,)
    info["verdict"] = "ok_is_distinct"
    return True, info


def cmd_receipt(args):
    m = manifest(args.root)
    m["receipt_version"] = 1
    m["note"] = ("隔离回执：**只记事实**（用了哪个根 + 该根清单指纹）。"
                 "拿它与运行后的回执做 `diff` 才能证明「真库没被动过」。")
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(m, fh, ensure_ascii=False, indent=1)
    print("回执 → %s（文件 %d 个 / %d 字节 / 关键件 %d 项）"
          % (args.out, m["file_count"], m["total_bytes"], len(m["key_files"])))
    return 0


def cmd_diff(args):
    try:
        b = json.load(open(args.before, encoding="utf-8"))
        a = json.load(open(args.after, encoding="utf-8"))
    except Exception as e:                                  # noqa: BLE001
        print("回执读不出：%r" % (e,))
        return 2
    diffs = []
    if b.get("file_count") != a.get("file_count"):
        diffs.append("文件数 %s → %s" % (b.get("file_count"), a.get("file_count")))
    if b.get("total_bytes") != a.get("total_bytes"):
        diffs.append("总字节 %s → %s" % (b.get("total_bytes"), a.get("total_bytes")))
    for rel, bv in (b.get("key_files") or {}).items():
        av = (a.get("key_files") or {}).get(rel) or {}
        if bv.get("sha256_16") != av.get("sha256_16"):
            diffs.append("关键件 %s：%s → %s" % (rel, bv.get("sha256_16"), av.get("sha256_16")))
    print("措施③ 真库前后对照：%s" % ("**差异 0 ✅**" if not diffs else "**有差异 ❌**"))
    for d in diffs:
        print("   · %s" % d)
    return 0 if not diffs else 3


def main():
    ap = argparse.ArgumentParser(description="副本隔离可证化（三措施）")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check"); c.add_argument("--expect-replica", default=None)
    r = sub.add_parser("receipt"); r.add_argument("--root", required=True); r.add_argument("--out", required=True)
    d = sub.add_parser("diff"); d.add_argument("--before", required=True); d.add_argument("--after", required=True)
    a = ap.parse_args()
    if a.cmd == "check":
        ok, info = check(a.expect_replica)
        print(json.dumps(info, ensure_ascii=False, indent=1))
        if not ok:
            print("\n⛔ **硬失败**：声明要跑副本，但目标根就是真库 ⇒ **拒绝继续**。", file=sys.stderr)
            print("   真库根（权威落点）：%s" % info["real_root"], file=sys.stderr)
            print("   ★ 根因：`layers.yaml` 各层 `cwd` 写死为该绝对路径，"
                  "编排器直接用它当子进程 cwd ⇒ 引擎永远不在副本里跑。", file=sys.stderr)
            return 2
        print("\n✅ 通过：目标根与真库不是同一实体。")
        return 0
    if a.cmd == "receipt":
        return cmd_receipt(a)
    return cmd_diff(a)


if __name__ == "__main__":
    sys.exit(main())
