#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""L1 重分块：把「单个 `#正文` 巨段」拆成按行的多段，锚点改成 `anchor_spec` 规定的 `#l.a-b`。

为什么做（2026-10-08 实测）：
  飞书链接类的 L1 产物里有 13 份是**整篇塞进 1 个 paragraph 段**（锚点 `#正文`，最长 188,828 字）。
  L2 的 `external_standard` 语义是「逐段 → clause 单元」，于是 1 段 ⇒ **1 个巨单元** ⇒
  被 L6 的尺寸护栏 `oversize_gt_8000` 整份挡在索引外 ⇒ **守衡检索不到这 1,754,363 字**。
  （同批另外 7 条是另一回事：过了判据但没进 SCOPE 白名单。）

**本脚本只改「分段与锚点」，正文一个字符都不动**：
  · 按 `\n` 切行后重新分组，重建时逐字比对 `== 原文`，不等就抛错、不落盘；
  · `source_sha256` 必须与重建文本的 sha256 一致，不一致即拒绝（说明我动到了正文）；
  · 锚点由 `#正文`（非 anchor_spec 口径）改为 `#l.<起始行>-<结束行>`（1 起，spec 的 url 口径）。

**窄判据**（只碰这一类，不做全库扫描 —— 2026-10-08 有过「判据放宽导致 822 个资源被误选」的教训）：
  产物只有 1 个内容段 且 kind=paragraph 且 anchor=="#正文" 且 len(text) > MAX_UNIT_CHARS。

用法：
  python3 kb/l8/rechunk_l1_segments.py <RUN> [--apply] [--target 4000]
"""
import os
import sys
import json
import glob
import shutil
import hashlib

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MAX_UNIT_CHARS = 8000          # 与 kb/.work/l6_scope_lib.py / l2_split_run.py 同值
RUN = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else "no-run"
APPLY = "--apply" in sys.argv
TARGET = int(sys.argv[sys.argv.index("--target") + 1]) if "--target" in sys.argv else 4000
BACKUP = os.path.join(ROOT, "kb/l1/_archive", f"rechunk-{RUN}")


def is_candidate(a):
    """窄判据：单内容段 + paragraph + #正文 + 超尺寸。"""
    segs = a.get("segments") or []
    if len(segs) != 1:
        return False
    s = segs[0]
    if (s.get("kind") or "") != "paragraph":
        return False
    if (s.get("anchor") or "") != "#正文":
        return False
    return len(s.get("text") or "") > MAX_UNIT_CHARS


def rechunk(text, target):
    """按行分组到 <= target；单行本身就超 target 时再按字符切，并记录「切点不是行边界」。

    返回 pieces = [(text, sep_after), ...]；重建 = p0 + sep0 + p1 + sep1 + ...
    sep 取 "\\n"（行边界）或 ""（行内切点）。
    """
    lines = text.split("\n")
    pieces, cur = [], []
    for i, line in enumerate(lines):
        if len(line) > target:                      # 单行超长：先冲掉手上的，再切这一行
            if cur:
                pieces.append(("\n".join(cur), "\n", 0))
                cur = []
            n_split = (len(line) + target - 1) // target
            for k in range(n_split):
                chunk = line[k * target:(k + 1) * target]
                last = (k == n_split - 1)
                pieces.append((chunk,
                               ("\n" if i < len(lines) - 1 else "") if last else "",
                               k + 1))          # 行内第 k+1 块（锚点要带这个序号）
            continue
        if cur and sum(len(x) for x in cur) + len(line) + len(cur) > target:
            pieces.append(("\n".join(cur), "\n", 0))
            cur = []
        cur.append(line)
    if cur:
        pieces.append(("\n".join(cur), "", 0))
    return pieces


def main():
    rows, n_ok, n_bad = [], 0, 0
    for p in sorted(glob.glob(os.path.join(ROOT, "kb/l1/*/url__*.json"))):
        try:
            a = json.load(open(p, encoding="utf-8"))
        except Exception:
            continue
        if "feishu.cn" not in str(a.get("resource_key")) or not is_candidate(a):
            continue
        text = a["segments"][0]["text"]
        sha_before = hashlib.sha256(text.encode("utf-8")).hexdigest()
        declared = a.get("source_sha256")
        pieces = rechunk(text, TARGET)
        rebuilt = "".join(t + sep for t, sep, _ord in pieces)
        # ---- 两道自证：正文逐字不变 + sha 不变。任一不过就跳过，不落盘 ----
        if rebuilt != text:
            n_bad += 1
            rows.append({"file": os.path.basename(p), "verdict": "拒绝：重建文本 != 原文"})
            print(f"  ✗ {os.path.basename(p)[-46:]}  重建文本与原文不一致，拒绝")
            continue
        if declared and sha_before != declared:
            n_bad += 1
            rows.append({"file": os.path.basename(p), "verdict": "拒绝：sha256 与台账不符",
                         "sha_now": sha_before, "sha_declared": declared})
            print(f"  ✗ {os.path.basename(p)[-46:]}  sha 不符（现 {sha_before[:12]} vs 台账 {str(declared)[:12]}），拒绝")
            continue
        # 逐段锚点：记录该段首行/末行（1 起）
        # ★ 锚点：行内切点必须带序号，否则同一行切出的两块会撞同一个 `#l.K-K`。
        segs, line_no = [], 1
        for t, sep, ordn in pieces:
            n_lines = t.count("\n") + 1
            start, end = line_no, line_no + n_lines - 1
            a_txt = f"#l.{start}-{end}" if n_lines > 1 else f"#l.{start}"
            if ordn:                       # 该行被按字符切开，标出是第几块
                a_txt += f"/p{ordn}"
            # ★ 段间 `\n` 必须**写进段文本**，否则 `"".join(段)` 拼不回原文
            #   （第一版就漏了这一步，被回读断言当场拦住，0 份落盘）。
            segs.append({"kind": "paragraph", "text": t + sep, "anchor": a_txt})
            line_no = end + 1 if sep == "\n" else end
        # 最后一段若以 "" 结尾且是行内切点，行号不推进 —— 上面的推进已按 sep 处理
        maxseg = max(len(s["text"].rstrip("\n")) for s in segs)
        new = dict(a)
        new.update({"segments": segs, "segment_count": len(segs),
                    "rechunk": {"at": RUN, "from_anchor": "#正文", "to_anchor": "#l.a-b",
                                "pieces": len(segs), "target_chars": TARGET,
                                "max_piece_chars": maxseg,
                                "text_sha256_before": sha_before,
                                "text_sha256_after": hashlib.sha256(rebuilt.encode("utf-8")).hexdigest(),
                                "note": "只改分段与锚点，正文逐字未变（脚本内已比对）"}})
        rows.append({"file": os.path.basename(p), "resource_key": a["resource_key"],
                     "chars": len(text), "pieces": len(segs), "max_piece_chars": maxseg,
                     "verdict": "已重分块"})
        n_ok += 1
        print(f"  ✓ {os.path.basename(p)[-44:]}  {len(text):>8,} 字 → {len(segs):>3} 段"
              f"（最大段 {maxseg} 字）")
        if APPLY:
            os.makedirs(BACKUP, exist_ok=True)
            shutil.copy2(p, os.path.join(BACKUP, os.path.basename(p)))
            tmp = p + ".swtmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(new, fh, ensure_ascii=False, indent=1)
            # 回读复核：段落数、最大段、正文重建
            rb = json.load(open(tmp, encoding="utf-8"))
            assert rb["segment_count"] == len(segs), "回读段数不符"
            assert "".join(s["text"] for s in rb["segments"]) == text, "回读正文不符"
            os.replace(tmp, p)
    print(f"\n[{RUN}] 重分块 {n_ok} 份 / 拒绝 {n_bad} 份（应用写入：{APPLY}）")
    rep = os.path.join(ROOT, "kb/l8/runs", f"{RUN}-l1-rechunk.json")
    tmp = rep + ".swtmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump({"run": RUN, "apply": APPLY, "target": TARGET,
                   "ok": n_ok, "rejected": n_bad, "items": rows}, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, rep)
    print(f"报告 {rep}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
