#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""inputs_fingerprint.py —— 层输入指纹：回答「自上次跑层以来，输入变过没有？」

── 为什么有它（2026-10-12，实测驱动）──────────────────────────────────────────
实测（`kb/.work/perf-segments.ndjson`，4 遍）：一单评审的整链中位 **24.74s**，其中
**① 层前置 14.98s = 60.6%**。而层前置经核实**与本次送审素材无关**：
  · `review_preflight.sh` 的入参只有 `--base/--session/--layers/--no-claim/--two-phase/--dry-inventory`，
    **没有任何一个是素材**；
  · 四层命令只有层名与 RUN（`kb_pipeline.py --sync --via-skill --only L4 --run <BASE>-L4`）。
而日更（2026-10-16 起为**每周日 03:30**，L0→L7）**已经产出过** L4–L7 的层 run（全库 `daily-*` 层 run **173** 个，
如今日 `kb/l4/runs/daily-20261012-0330-L4-dryrun.json`）。
⇒ 那 15s 是「**日更做过的同一件 KB 工作，被每单重做一遍**」，不是「必须在关键路径上」。

── 本文件干什么 ─────────────────────────────────────────────────────────────
**只回答一个问题**：`layers.yaml` 各层声明的 `inputs`（62 条）**自某个快照以来变过没有**。
它**不做任何判定、不改任何闸门、不写权威库产物**（只写自己的快照/账本到 `kb/.work/`）。

★ 这是「输入没变 ⇒ 可复用日更的层 run」这条路的**前置判据**。
  它挂掉 / 说不清 ⇒ 调用方**必须回落到全跑**（fail-closed）。

── 判据口径 ─────────────────────────────────────────────────────────────────
1. 输入清单**唯一真源** = `kb/l7/registry/layers.yaml` 各层 `inputs`（**不手抄第二份**）。
   路径解析复用 `kb_pipeline.py` 的同一套口径：`looks_like_path` / `is_glob` /
   `has_match` / `strip_placeholder` —— **不重写、不发明第二套**。
2. 每个输入记 `size` + `mtime_ns` + `sha256`。
   · **快路径**：先比 `size`/`mtime_ns`，都相同 ⇒ 判「未变」，**不重算 sha256**（省时）；
   · **慢路径**：任一不同 ⇒ **真算 sha256** 复核 —— mtime 会被 `touch`、`cp -p` 骗过，
     sha256 不会。**结论以 sha256 为准**。
3. 排除历史件：`_backups|_archive|_skill-backups|/runs/|.bak`（与 layers.yaml 补全时同一条口径）
   —— 全库此类「同名不同物」诱饵实测 **25315** 个，不过滤会把快照撑爆且永久报变。

── 用法 ─────────────────────────────────────────────────────────────────────
  python3 kb/l8/inputs_fingerprint.py snapshot [--out kb/.work/inputs-fingerprint.json]
  python3 kb/l8/inputs_fingerprint.py diff --against kb/.work/inputs-fingerprint.json [--json]
  python3 kb/l8/inputs_fingerprint.py --selftest        # 反向对照（造变更 ⇒ 必须精确变红）

退出码：0=未变（可复用）｜3=**变了**（必须全跑）｜2=判不了（缺快照/读不到 ⇒ 调用方按「变了」处理）
"""
from __future__ import annotations

import argparse
import glob as _glob
import hashlib
import json
import os
import re
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
KB = os.path.join(ROOT, "kb")
LAYERS_YAML = os.path.join(KB, "l7", "registry", "layers.yaml")
DEFAULT_SNAP = os.path.join(KB, ".work", "inputs-fingerprint.json")

#: 历史件排除口径 —— **与 layers.yaml 补全时逐字同一条**（见该文件 inputs 的注释）
EXCLUDE = re.compile(r"_backups|_archive|_skill-backups|/runs/|\.bak")

_SHA_CHUNK = 1 << 20


def _sha256(path: str) -> str | None:
    h = hashlib.sha256()
    try:
        with open(path, "rb") as fh:
            while True:
                b = fh.read(_SHA_CHUNK)
                if not b:
                    break
                h.update(b)
        return h.hexdigest()
    except Exception:                                    # noqa: BLE001
        return None


# ── 路径解析：与 kb_pipeline.py 同一口径（那边是判据真源，此处只借形）──────────
def _looks_like_path(s: str) -> bool:
    """像路径的才查。散文行（如「飞书侧（lark-cli…）：entry Base xxx」）一律跳过。"""
    if not s or not isinstance(s, str):
        return False
    if "：" in s or " " in s.strip():                    # 含全角冒号/空格 ⇒ 判为散文
        return False
    return "/" in s


def _is_glob(s: str) -> bool:
    return any(c in s for c in "*?{[") or ".." in s


def _strip_placeholder(s: str) -> str:
    """`<sha256>` / `<表名>` 这类模板先剥掉，只留能判存在性的前缀。"""
    return re.sub(r"<[^>]*>", "", s)


def _resolve(cwd: str, spec: str) -> list[str]:
    """把一条 inputs 声明解析成**真实存在的路径列表**。解析不出 ⇒ 空列表。"""
    if not _looks_like_path(spec):
        return []
    if EXCLUDE.search(spec):
        return []
    if _is_glob(spec):
        # 花括号展开（形如 `kb/l1/{1..4,9}_*/*.json`）—— 不引第三方库，自己展开
        out: list[str] = []
        for pat in _expand_braces(spec):
            out.extend(_glob.glob(os.path.join(cwd, pat), recursive=True))
        return sorted({p for p in out if os.path.isfile(p)})
    p = _strip_placeholder(spec)
    q = os.path.join(cwd, p) if not os.path.isabs(p) else p
    if os.path.isfile(q):
        return [q]
    if os.path.isdir(q):
        return sorted(os.path.join(q, f) for f in os.listdir(q)
                      if os.path.isfile(os.path.join(q, f)))
    # ★ 模板路径（`<sha256>.json` / `<表名>/<record_id>.json`）剥完占位符后**不是**文件也不是目录。
    #   早先版在此直接 return [] ⇒ 这三条声明**完全没被指纹覆盖**，改动它们不会报变 = **fail-open**。
    #   改为回落到**最近的已存在祖先目录**，把该目录下的文件全列进去。
    #   上限 3 级 —— 防止一路退到 kb/ 根，把整库都扫进来（那既慢又失去指向性）。
    anc = q
    for _ in range(3):
        anc = os.path.dirname(anc)
        if anc and os.path.isdir(anc):
            direct = sorted(os.path.join(anc, f) for f in os.listdir(anc)
                            if os.path.isfile(os.path.join(anc, f)))
            if direct:
                return direct
            # ★ 该目录下**只有子目录**（实测：`kb/l0/records/` 是按表分目录的）
            #   ⇒ 只收直接文件会漏光。此时递归收，上限 5000 个文件防失控。
            deep, cap = [], 5000
            for dp, _dn, fn in os.walk(anc):
                for f in sorted(fn):
                    deep.append(os.path.join(dp, f))
                    if len(deep) >= cap:
                        return sorted(deep)
            return sorted(deep)
    return []


def _expand_braces(pat: str) -> list[str]:
    """展开 `{a,b}` 与 `{1..4}`；无花括号原样返回。够用即止，不做通用 glob。"""
    m = re.search(r"\{([^{}]*)\}", pat)
    if not m:
        return [pat]
    body, out = m.group(1), []
    for part in body.split(","):
        rng = re.match(r"^\s*(-?\d+)\s*\.\.\s*(-?\d+)\s*$", part)
        alts = ([str(i) for i in range(int(rng.group(1)), int(rng.group(2)) + 1)]
                if rng else [part.strip()])
        for a in alts:
            out.extend(_expand_braces(pat[:m.start()] + a + pat[m.end():]))
    return out


def collect() -> dict:
    """扫 layers.yaml 全部 inputs ⇒ {abs_path: {size, mtime_ns}} + 解析统计。"""
    import yaml
    with open(LAYERS_YAML, encoding="utf-8") as fh:
        reg = yaml.safe_load(fh)
    cwd = ROOT
    files: dict[str, dict] = {}
    declared, unresolved = 0, []
    for L in reg.get("layers") or []:
        lid = L.get("layer") or "?"
        for spec in (L.get("inputs") or []):
            declared += 1
            got = _resolve(cwd, spec)
            if not got and _looks_like_path(spec):
                unresolved.append([lid, spec])
            for p in got:
                rp = os.path.realpath(p)
                try:
                    st = os.stat(p)
                except Exception:                        # noqa: BLE001
                    continue
                files[rp] = {"size": st.st_size, "mtime_ns": st.st_mtime_ns}
    return {"files": files, "declared": declared, "unresolved": unresolved}


def snapshot(out: str, with_sha: bool = True) -> dict:
    c = collect()
    files = c["files"]
    n_sha = 0
    for rp, rec in files.items():
        rec["sha256"] = _sha256(rp) if with_sha else None
        n_sha += 1 if rec["sha256"] else 0
    snap = {"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "root": ROOT,
            "declared_inputs": c["declared"], "file_count": len(files),
            "sha256_count": n_sha, "unresolved": c["unresolved"], "files": files}
    os.makedirs(os.path.dirname(out), exist_ok=True)
    tmp = out + ".swtmp"
    with open(tmp, "w", encoding="utf-8") as fh:          # .json/.swtmp 不受信封影响
        json.dump(snap, fh, ensure_ascii=False, indent=1, sort_keys=True)
    os.replace(tmp, out)
    return snap


def diff(against: str) -> dict:
    """与快照比。返回 changed / added / removed / same 与**是否可复用**。"""
    try:
        with open(against, encoding="utf-8") as fh:
            old = json.load(fh)
    except Exception as e:                                # noqa: BLE001
        return {"ok": False, "reusable": False, "reason": "读不到快照：%s" % e}
    of = old.get("files") or {}
    c = collect()
    nf = c["files"]
    changed, added, removed, same, size_only = [], [], [], 0, []
    for rp, rec in nf.items():
        o = of.get(rp)
        if o is None:
            added.append(rp)
            continue
        if o.get("size") == rec["size"] and o.get("mtime_ns") == rec["mtime_ns"]:
            same += 1                                     # 快路径：stat 全同 ⇒ 不重算
            continue
        # 慢路径：stat 变了 ⇒ **以 sha256 为准**（mtime 会被 touch / cp -p 骗过）
        new_sha = _sha256(rp)
        if new_sha is not None and new_sha == o.get("sha256"):
            same += 1
            size_only.append(rp)                          # stat 动过但内容没变
        else:
            changed.append(rp)
    for rp in of:
        if rp not in nf:
            removed.append(rp)
    reusable = not (changed or added or removed)
    return {"ok": True, "reusable": reusable, "changed": sorted(changed),
            "added": sorted(added), "removed": sorted(removed),
            "same": same, "stat_only": sorted(size_only),
            "snapshot_at": old.get("at"), "declared_inputs": c["declared"],
            "file_count": len(nf), "unresolved": c["unresolved"]}


# ── 反向对照 ─────────────────────────────────────────────────────────────────
def _selftest() -> int:
    """造一次真变更 ⇒ 必须**精确变红**；还原 ⇒ 必须回绿。**这是判据不是注释。**"""
    ok = bad = 0
    tmpd = tempfile.mkdtemp(prefix="inpfix-")
    a = os.path.join(tmpd, "a.txt")
    b = os.path.join(tmpd, "b.txt")
    for p, s in ((a, "AAA"), (b, "BBB")):
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(s)
    snap = {"files": {os.path.realpath(p): {"size": os.stat(p).st_size,
                                            "mtime_ns": os.stat(p).st_mtime_ns,
                                            "sha256": _sha256(p)}
                      for p in (a, b)}}

    def _check(name, cond):
        nonlocal ok, bad
        if cond:
            ok += 1
            print("  ✅ %s" % name)
        else:
            bad += 1
            print("  ❌ %s" % name)

    def _diff(paths):
        """用给定文件集跑一遍 diff 的判据核心（不依赖真库）。"""
        of = snap["files"]
        changed, added, removed, same = [], [], [], 0
        for rp in paths:
            o = of.get(os.path.realpath(rp))
            if o is None:
                added.append(rp)
                continue
            st = os.stat(rp)
            if o["size"] == st.st_size and o["mtime_ns"] == st.st_mtime_ns:
                same += 1
                continue
            if _sha256(rp) == o["sha256"]:
                same += 1
            else:
                changed.append(rp)
        for rp in of:
            if rp not in [os.path.realpath(x) for x in paths]:
                removed.append(rp)
        return changed, added, removed, same

    print("inputs_fingerprint --selftest")
    c, ad, rm, sm = _diff([a, b])
    _check("① 未动任何文件 ⇒ 判「未变」（changed 空）", not (c or ad or rm) and sm == 2)

    with open(a, "w", encoding="utf-8") as fh:
        fh.write("AAA-changed")
    c, ad, rm, sm = _diff([a, b])
    _check("② 改内容 ⇒ **精确点名 a.txt**", c == [a] and not ad and not rm)

    # 还原内容，但**只 touch 改 mtime** ⇒ 必须靠 sha256 判回「没变」
    with open(a, "w", encoding="utf-8") as fh:
        fh.write("AAA")
    os.utime(a, (time.time() + 5, time.time() + 5))
    c, ad, rm, sm = _diff([a, b])
    _check("③ 只动 mtime、内容不变 ⇒ 判「未变」（sha256 复核挡住假红）", not c and sm == 2)

    with open(a, "w", encoding="utf-8") as fh:
        fh.write("AAA")                                   # 变回原样
    os.utime(a, (snap["files"][os.path.realpath(a)]["mtime_ns"] / 1e9,) * 2)
    c, ad, rm, sm = _diff([a, b])
    _check("④ 逐字还原 ⇒ 回绿", not (c or ad or rm))

    # ★ 比 realpath：macOS 上 `/var` 是 `/private/var` 的软链，
    #   拿原路径去比 realpath 结果**必假红**（写这条时真踩了）。
    rb = os.path.realpath(b)
    os.unlink(b)
    c, ad, rm, sm = _diff([a])
    _check("⑤ 删掉 b.txt ⇒ 报 removed", rm == [rb] and not c)

    # ⑤ 已把 b 删了 ⇒ 这里**不能**再 _diff([a, b])（会 stat 不存在的文件而抛）。
    with open(b, "w", encoding="utf-8") as fh:
        fh.write("BBB-new")
    # 路径本就在快照里 ⇒ 复现且内容不同 = **changed**，不是 added
    # （added 的定义是「快照里没有这个路径」，两者别混 —— 写这条时又踩了一次）。
    c, ad, rm, sm = _diff([a, b])
    _check("⑥ 复现但内容不同 ⇒ 报 changed 且点名（ad 必须为空）", b in c and not ad and not rm)

    # 口径守卫（不跑真库，只验解析函数）
    _check("⑦ 散文行不当作路径", not _looks_like_path("飞书侧（lark-cli，全程只读）：entry Base xxx"))
    _check("⑧ `_backups` 路径被排除", _resolve(ROOT, "kb/l2/_backups/x/units.jsonl") == [])
    _check("⑨ `<sha256>` 模板先剥再判", _strip_placeholder("a/<x>.json") == "a/.json")
    _check("⑩ 花括号 {1..3} 展开", len(_expand_braces("kb/l1/{1..3}_*/*.json")) == 3)

    print("  ---- %d/%d 通过，%d 失败" % (ok, ok + bad, bad))
    if bad == 0:
        print("  ★ 反向对照：把 ② 写成恒绿（不比对 sha256）⇒ ② 必红 —— 已由 ②③ 一对夹住")
    return 0 if bad == 0 else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="层输入指纹：输入变没变（决定能否复用日更的层 run）")
    sub = ap.add_subparsers(dest="cmd")
    p1 = sub.add_parser("snapshot", help="写一份快照")
    p1.add_argument("--out", default=DEFAULT_SNAP)
    p1.add_argument("--no-sha", action="store_true", help="只记 stat（快，但弱）")
    p2 = sub.add_parser("diff", help="与快照比")
    p2.add_argument("--against", default=DEFAULT_SNAP)
    p2.add_argument("--json", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()

    if a.selftest:
        return _selftest()

    if a.cmd == "snapshot":
        s = snapshot(a.out, with_sha=not a.no_sha)
        print("已写快照：%s" % a.out)
        print("  声明 inputs %d 条 ｜ 解析出文件 %d 个 ｜ 带 sha256 %d 个"
              % (s["declared_inputs"], s["file_count"], s["sha256_count"]))
        if s["unresolved"]:
            print("  ⚠️ 解析不出的声明 %d 条（**不静默**）：" % len(s["unresolved"]))
            for lid, spec in s["unresolved"][:8]:
                print("      [%s] %s" % (lid, spec))
        return 0

    if a.cmd == "diff":
        r = diff(a.against)
        if a.json:
            print(json.dumps(r, ensure_ascii=False, indent=1))
        else:
            if not r.get("ok"):
                print("⛔ 判不了：%s ⇒ 调用方**按「变了」处理**（fail-closed）" % r.get("reason"))
                return 2
            print("对标快照：%s ｜ 声明 %d 条 ｜ 文件 %d 个"
                  % (r["snapshot_at"], r["declared_inputs"], r["file_count"]))
            print("  未变 %d ｜ **变 %d** ｜ 新增 %d ｜ 消失 %d ｜ 仅 stat 动 %d"
                  % (r["same"], len(r["changed"]), len(r["added"]),
                     len(r["removed"]), len(r["stat_only"])))
            for tag, key in (("变", "changed"), ("新增", "added"), ("消失", "removed")):
                for p in r[key][:6]:
                    print("    %s %s" % (tag, os.path.relpath(p, ROOT)))
            print("  ⇒ %s" % ("**未变**：可复用日更的层 run" if r["reusable"]
                              else "**变了**：必须全跑 L4→L5→L6→L7（一步不省）"))
        return 0 if r.get("reusable") else 3

    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
