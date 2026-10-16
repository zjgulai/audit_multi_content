#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kb-repair 2026-10-03：修「活路径上的 4096 字节信封」.md（内容逐字不变）。

判据（与 `l8/envelope_census.py` 同一把尺子，不另造第二把）：
    同一路径上 Python `getsize` != node（**消费方** DSH Electron）`statSync().size`，差值恒 4096。

为什么必须由消费方读者判：同一文件三读者实测
    python getsize=14005（明文）｜PATH node statSync=14005｜宿主 Electron=18101（乱码）
⇒ PATH node 与 python 一起"看不见"信封，只有宿主 Electron（= agent read 工具的真实读者）
   看得见。本修法以此为准。

修法（沿用 2026-09-29 A1 的既定通道，**内容一个字不改**）：
  ① python 读到的是明文（信封对 python 免疫）—— 那就是"逻辑内容"；
  ② 先把**旧物理字节**用 `cp` 归档（cp 是 shell 命令，不经 python 写封装，落盘即原始字节）；
  ③ 逻辑内容经 **stdin** 交给 `kb/.work/write_via_node.mjs`，由 **Electron 的 fs.writeFileSync** 写盘；
  ④ 双向断言：逻辑内容 sha256 前后一致（内容守恒）＋ Electron 侧字节数 == python 侧字节数（信封没了）。

用法：
  python3 kb/.work/repair_envelopes_20261003.py <census.json> [--apply]
  不给 --apply 只预演（不写盘、不归档）。
"""
import hashlib
import json
import os
import subprocess
import sys
import time

DSH = "/Applications/DSH Desktop.app.pre-lute-20260907-111753/Contents/MacOS/DSH Desktop"
WS = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
WRITER = "kb/.work/write_via_node.mjs"


def sha(b):
    return hashlib.sha256(b).hexdigest()


def node_size(path):
    code = ('const fs=require("fs");console.log(fs.statSync(process.argv[1]).size)')
    r = subprocess.run([DSH, "-e", code, os.path.abspath(path)],
                       capture_output=True, text=True,
                       env=dict(os.environ, ELECTRON_RUN_AS_NODE="1"))
    return int(r.stdout.strip())


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    apply_ = "--apply" in sys.argv
    if not args:
        print(__doc__)
        return 2
    data = json.load(open(args[0], encoding="utf-8"))
    # 两种输入形态：
    #   ① `l8/envelope_census.py --json` 的普查结果 —— `rel` 是**相对 kb/** 的
    #   ② 纯列表 `["a/b.md", …]` —— **相对本次库根**（工作区根），用于普查范围之外的件
    #      （工作区根 / `_dump-*` 等，这些在 `workflow_check.py` 第⑥腿里落「其他」桶）
    if isinstance(data, dict):
        targets = [os.path.join("kb", x["rel"]) for x in data["live_path_envelopes"]]
    else:
        targets = list(data)
    run = time.strftime("%Y%m%d-%H%M%S")
    arch = os.path.join(WS, "kb/l8/_archive", "enveloped-repair-%s" % run)
    print("库根        : %s" % WS)
    print("待修（活路径）: %d 个" % len(targets))
    print("归档        : %s" % os.path.relpath(arch, WS) if apply_ else "（预演，不归档）")
    print("写通道      : %s（Electron fs.writeFileSync，内容走 stdin）" % WRITER)

    rows, ok, fail = [], 0, 0
    for rel in targets:
        # rel 一律**相对本次库根**（形态①由上面的 "kb/" 前缀归一）
        p = os.path.join(WS, rel)
        if not os.path.isfile(p):
            fail += 1
            rows.append({"rel": rel, "verdict": "FAIL", "why": "文件不存在"})
            continue
        before_py = os.path.getsize(p)
        before_node = node_size(p)
        if abs(before_py - before_node) != 4096:
            ok += 1
            rows.append({"rel": rel, "verdict": "SKIP", "why": "已不是信封态（%d/%d）" % (before_py, before_node)})
            continue
        try:
            logical = open(p, "rb").read().decode("utf-8")
        except UnicodeDecodeError as e:
            fail += 1
            rows.append({"rel": rel, "verdict": "FAIL", "why": "python 侧不是 UTF-8：%s" % e})
            continue
        lb = logical.encode("utf-8")
        sha_before = sha(open(p, "rb").read())
        rec = {"rel": rel, "py_before": before_py, "node_before": before_node,
               "logical_bytes": len(lb), "logical_sha256": sha_before,
               "archived_raw": None}
        if not apply_:
            rec["verdict"] = "DRY"
            rows.append(rec)
            continue
        # ① 归档旧物理字节（cp 通道）
        dst = os.path.join(arch, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if subprocess.run(["cp", p, dst]).returncode != 0:
            fail += 1
            rec.update({"verdict": "FAIL", "why": "归档 cp 失败"})
            rows.append(rec)
            continue
        rec["archived_raw"] = os.path.relpath(dst, WS)
        # ② 逻辑内容经 stdin 交给 Electron 写盘
        r = subprocess.run([DSH, WRITER, os.path.abspath(p)], input=lb,
                           capture_output=True, env=dict(os.environ, ELECTRON_RUN_AS_NODE="1"))
        try:
            info = json.loads(r.stdout.decode("utf-8"))
        except Exception as e:
            fail += 1
            rec.update({"verdict": "FAIL", "why": "读不到 writer JSON：%s / rc=%d %r"
                        % (e, r.returncode, (r.stderr or b"")[:160])})
            rows.append(rec)
            continue
        # ③ 双向断言
        after_py = os.path.getsize(p)
        after_node = node_size(p)
        sha_after = sha(open(p, "rb").read())
        rec.update({"py_after": after_py, "node_after": after_node,
                    "writer_bytes_after": info.get("bytes_after"),
                    "logical_sha256_after": sha_after})
        if sha_after != sha_before:
            fail += 1
            rec["verdict"] = "FAIL"
            rec["why"] = "内容变了（sha256 前后不一致）—— 已归档，可回滚"
        elif after_node != after_py or abs(after_py - after_node) == 4096:
            fail += 1
            rec["verdict"] = "FAIL"
            rec["why"] = "仍是信封态（py=%d node=%d）" % (after_py, after_node)
        else:
            ok += 1
            rec["verdict"] = "FIXED"
        rows.append(rec)

    rep = {"run": run, "kb_root": WS, "targets": len(targets),
           "fixed": ok, "failed": fail, "apply": apply_,
           "archive": os.path.relpath(arch, WS) if apply_ else None, "files": rows}
    out = os.path.join(WS, "kb/l8", "envelope_repair_%s.json" % run)
    json.dump(rep, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n修好 %d 个 ｜ 失败 %d 个 ｜ 预演 %s" % (ok, fail, "是" if not apply_ else "否"))
    for r_ in rows:
        if r_["verdict"] == "FAIL":
            print("  FAIL %s ← %s" % (r_["rel"], r_.get("why")))
    print("报告：%s" % os.path.relpath(out, WS))
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
