#!/usr/bin/env python3
"""L0 台账（`kb/l0/manifest.jsonl`）的写入助手：**只写变化，不写空转**。

## 为什么有这个东西（2026-09-30 实测）

`kb/l8/` 下 13 个脚本都会往 `manifest.jsonl` 追加行，**没有一个检查"这次和上次一样吗"**。
后果（`kb/l8/runs/20260930-1045-l0-dup-audit.json` 实测）：

    5,361 行 / 唯一资源 2,112 → 台账膨胀 2.5 倍；其中 **1,621 行是空转再登记**
    （同 key、同 status、同 sha、同口径，什么都没变却又登记了一遍）

一次全量同步（哪怕源侧一个字没改）会再追加约 700 行 —— 台账会长成一个"每轮都记一遍"的流水账，
而它本来的语义是**资源状态台账**（谁在、什么状态、什么指纹）。

## 语义边界（重要，别越界）

- **状态变了 → 照写**：status / sha256 / sha256_input / sha256_state / revision 任一不同，行照旧追加。
- **什么都没变 → 不写整行**，改为在 sidecar `kb/l0/registry/last_seen.json` 里刷新"这轮还看见它"。
  这样既止住了膨胀，又**没有丢掉"它还活着"这个信息**（丢掉它会让"失踪"和"没查"分不清）。
- **不改历史行**：本模块只 append 或建 sidecar，从不重写、从不删除 `manifest.jsonl` 已有行。

## 用法

    from l0_ledger import append_changed
    n = append_changed("kb/l0/manifest.jsonl", rows, run=RUN, change_default="l0_xxx")
    print(n["appended"], "行有变化；", n["skipped_unchanged"], "行未变（记入 last_seen）")

落盘走 `tempfile` + 子进程 `/bin/cp`：python 直接建/截断文件会留下**信封态**
（bash `stat` 虚高 4096，harness 的 read 工具判成 binary file）。见 `references/gotchas.md` §二。
"""
import json
import os
import subprocess
import tempfile

SIG_FIELDS = ("status", "sha256", "sha256_input", "sha256_state", "revision")
LAST_SEEN = "kb/l0/registry/last_seen.json"


def latest_by_key(path):
    """每个 resource_key 的最后一行 —— 与各脚本里 `lat[...]` 的口径一致。"""
    lat = {}
    if not os.path.exists(path):
        return lat
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                r = json.loads(line)
                lat[r.get("resource_key")] = r
    return lat


def signature(row):
    return tuple(row.get(f) for f in SIG_FIELDS)


def cp_write(path, data: bytes):
    """tempfile → /bin/cp：避免 python 直接建文件带来的信封态。"""
    fd, tmp = tempfile.mkstemp(dir="/tmp", prefix="l0ledger-")
    with os.fdopen(fd, "wb") as fh:
        fh.write(data)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    if os.path.exists(path):
        subprocess.run(["/bin/cp", tmp, path], check=True)
        os.unlink(tmp)
    else:
        os.replace(tmp, path)


def append_changed(manifest_path, rows, run=None, last_seen_path=None, verbose=True):
    """把 rows 里**真正有变化的**追加进台账；未变的只刷新 last_seen。

    返回 {"appended": n, "skipped_unchanged": n, "seen_refreshed": n}
    """
    last_seen_path = last_seen_path or LAST_SEEN
    lat = latest_by_key(manifest_path)
    keep, unchanged = [], []
    for r in rows:
        prev = lat.get(r.get("resource_key"))
        if prev is not None and signature(prev) == signature(r):
            unchanged.append(r)
        else:
            keep.append(r)

    payload = b""
    if keep:
        payload = "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in keep).encode("utf-8")
        old = b""
        if os.path.exists(manifest_path):
            with open(manifest_path, "rb") as fh:
                old = fh.read()
            if old and not old.endswith(b"\n"):
                old += b"\n"
        cp_write(manifest_path, old + payload)

    if unchanged:
        seen = {}
        if os.path.exists(last_seen_path):
            try:
                seen = json.load(open(last_seen_path, encoding="utf-8"))
            except Exception:
                seen = {}
        for r in unchanged:
            seen[r["resource_key"]] = {"run": run, "status": r.get("status"),
                                       "sha256": r.get("sha256"),
                                       "sha256_input": r.get("sha256_input")}
        seen["_note"] = ("未变化的资源只在这里刷新『这轮还看见它』，不再往 manifest.jsonl 追加整行"
                         "（2026-09-30 起）。台账只记状态变化，避免每轮无脑膨胀。")
        cp_write(last_seen_path, json.dumps(seen, ensure_ascii=False, indent=1, sort_keys=True).encode("utf-8"))

    if verbose:
        print(f"  [l0_ledger] 追加 {len(keep)} 行（有变化）；跳过 {len(unchanged)} 行（未变，已记 last_seen）")
    return {"appended": len(keep), "skipped_unchanged": len(unchanged), "seen_refreshed": len(unchanged)}
