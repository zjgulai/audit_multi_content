#!/usr/bin/env python3
"""L8 第一步：把宿主库视图的 509 条 + DERIVED.md 读出来、存档旧字节、产出待重写的载荷。

为什么要分两步（本脚本 python 读，repack_write.mjs 用 node 写）：
- 本机存在一层按扩展名生效的文件封装：**`.md` 经解释器/工具通道写盘后会变成 4096 字节的信封**，
  只有部分读取者能看到解密视图（python / cat / od / xxd 可以，加载器所在的 DSH 运行时不行）。
- 详见 kb/l8/diagnosis.md 的 E1–E4 原始数据。
- 所以：读取用能解密的通道（python），落盘用**加载器同一运行时**的 node，并在写完后立刻读回断言。

旧文件不删：原始信封字节用 dd（唯一能看到信封的读取者）存到 kb/l8/_archive/enveloped-<run>/。
"""
# ── 解释器守卫（2026-09-29）：不合格就用 kb/.kb-python 指定的解释器重跑自己 ──
import os as _os, sys as _sys
if not _os.environ.get("KB_INTERP_OK"):
    _d = _os.path.dirname(_os.path.abspath(__file__)); _cfg = None
    while True:
        _p = _os.path.join(_d, ".kb-python")
        if _os.path.isfile(_p):
            _cfg = _p
            break
        _q = _os.path.dirname(_d)
        if _q == _d:
            break
        _d = _q
    if _cfg:
        _want = next((l.split("#", 1)[0].strip() for l in open(_cfg, encoding="utf-8")
                      if l.split("#", 1)[0].strip()), "")
        _want = _os.path.expanduser(_want)
        if (_want and _os.access(_want, _os.X_OK)
                and _os.path.realpath(_want) != _os.path.realpath(_sys.executable)):
            _os.environ["KB_INTERP_OK"] = "1"
            _os.execve(_want, [_want, _os.path.abspath(__file__)] + _sys.argv[1:], dict(_os.environ))
# ──────────────────────────────────────────────────────────────────────────

import hashlib, json, os, re, shutil, subprocess, sys, time

ROOT_WS = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # …/内容治理
KB = os.path.expanduser("~/.dsh/Momcozy知识库")
RUN = sys.argv[1] if len(sys.argv) > 1 else "20260923-1520"
L8 = os.path.join(ROOT_WS, "kb", "l8")
ARCH = os.path.join(L8, "_archive", f"enveloped-{RUN}")
for d in (L8, os.path.join(L8, "runs"), os.path.join(L8, "registry"), ARCH):
    os.makedirs(d, exist_ok=True)


def sha(b):
    return hashlib.sha256(b).hexdigest()


def raw_via_dd(path):
    """用 dd 读原始字节（本机唯一稳定看到信封的读取者）。"""
    p = subprocess.run(["/bin/dd", f"if={path}", "bs=65536"], capture_output=True)
    return p.stdout


def raw_size(path):
    """物理大小：用 stat 命令（它看得到信封长度）。"""
    p = subprocess.run(["/usr/bin/stat", "-f", "%z", path], capture_output=True, text=True)
    return int(p.stdout.strip())


TARGETS = ["_meta/DERIVED.md"]
for sub in ("3_措辞表达库/L1-facts", "3_措辞表达库/L2-concepts"):
    d = os.path.join(KB, sub)
    TARGETS += [f"{sub}/{n}" for n in sorted(os.listdir(d)) if n.endswith(".md")]

payload, manifest = [], []
for rel in TARGETS:
    live = os.path.join(KB, rel)
    if not os.path.exists(live):
        print(f"  跳过（不存在）：{rel}")
        continue
    logical = open(live, encoding="utf-8").read()          # python 通道：解密视图
    logical_bytes = logical.encode("utf-8")
    raw = raw_via_dd(live)                                  # 信封原始字节
    phys = raw_size(live)
    arch = os.path.join(ARCH, rel)
    os.makedirs(os.path.dirname(arch), exist_ok=True)
    with open(arch, "wb") as fh:
        fh.write(raw)
    manifest.append({"rel": rel, "logical_bytes": len(logical_bytes), "physical_bytes": phys,
                     "enveloped": phys != len(logical_bytes), "delta": phys - len(logical_bytes),
                     "logical_sha16": sha(logical_bytes)[:16], "raw_sha16": sha(raw)[:16],
                     "archived_raw": os.path.relpath(arch, ROOT_WS),
                     "archived_raw_bytes": os.path.getsize(arch)})
    payload.append({"rel": rel, "text": logical, "logical_sha256": sha(logical_bytes),
                    "logical_bytes": len(logical_bytes), "physical_bytes": phys})

env = [m for m in manifest if m["enveloped"]]
with open(os.path.join(L8, "repack_payload.json"), "w", encoding="utf-8") as fh:
    json.dump({"run_id": RUN, "kb_root": KB, "files": payload}, fh, ensure_ascii=False)
with open(os.path.join(L8, "envelope_manifest.json"), "w", encoding="utf-8") as fh:
    json.dump({"run_id": RUN, "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
               "kb_root": KB, "total": len(manifest), "enveloped": len(env),
               "files": manifest}, fh, ensure_ascii=False, indent=1)
print(f"读取 {len(manifest)} 个文件：信封态 {len(env)} 个 / 明文 {len(manifest)-len(env)} 个")
if env:
    d0 = {m["delta"] for m in env}
    print(f"  信封态的体积差集合：{sorted(d0)}（应为 {{4096}}）")
print(f"载荷 → kb/l8/repack_payload.json（{os.path.getsize(os.path.join(L8,'repack_payload.json'))} 字节）")
print(f"旧字节存档 → kb/l8/_archive/enveloped-{RUN}/（{sum(m['archived_raw_bytes'] for m in manifest)} 字节，不删除任何原文件）")
