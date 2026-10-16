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
    # ★ 2026-10-13 手术副本：只动 PRD 这一份（其余 10 份是登录页 HTML / JSON 信封垃圾，
    #   一起重分块会把垃圾摊成 216 个单元）。
    if "NB55wAq8liEOdKkquL2cgtPEnmg" not in (a.get("resource_key") or ""):
        return False
    return len(s.get("text") or "") > MAX_UNIT_CHARS


# ★ 2026-10-12 改（改动单-外部标准抽取口径-20261010.md §3 方案 A）：
#   原先单行超长时**纯按字符切**（line[k*target:(k+1)*target]）⇒ 抓手是"少数几个超长行"的
#   网页正文被切成定长块，**边界落在词中间**。实测证据（该单 §1）：待定稿 2780 条 scoped_clause 里
#   char_count 落在 [3800,4000] 的占 90.0%、两端都在词中间的占 84.5%，C9 因此挡下 1774 条。
#   现在改为：**先按句末标点切句，再把整句聚合到 <= target；任何情况下不切开句子**；
#   只有**单句本身**就超 target 时才退回字符切，并在 anchor 上标记 `/hard`（可见、可统计）。
#   ★ 无损约束不变：切法只决定"在哪里断开"，**不增删任何字符** —— 重建仍逐字 == 原文。
SENT_END = ".!?。！？"
# 句末标点后可能紧跟的收尾符号（引号 / 括号 / 省略号尾巴等），它们属于**上一句**
SENT_TAIL = "\"')]}»”’＂）】》…"


def split_sentences(line):
    """把一行切成「整句」序列；逐字无损（"".join(结果) == line）。

    句界判据：句末标点 + 0..n 个收尾符号 + **空白或行尾**。
    加"必须跟空白"这一条是为了不把 `3.5` / `U.S.`（点在词中间）当句界。
    切不出句界（如压缩过的 HTML/JS）⇒ 返回 [line] 单元素，走 hard 分支。
    """
    out, start, i, n = [], 0, 0, len(line)
    while i < n:
        if line[i] in SENT_END:
            j = i + 1
            while j < n and line[j] in SENT_TAIL:
                j += 1
            if j >= n or line[j].isspace():
                out.append(line[start:j])
                start, i = j, j
                continue
        i += 1
    if start < n:
        out.append(line[start:])
    return out


def pack_sentences(sents, target):
    """把整句聚合到 <= target；单句 > target 时退回字符切并标 tag=hard。

    返回 [(chunk, hard), ...]；"".join(chunk) == "".join(sents)。
    """
    out, cur, cur_len = [], [], 0

    def flush():
        nonlocal cur, cur_len
        if cur:
            out.append(("".join(cur), False))
            cur, cur_len = [], 0

    for s in sents:
        if len(s) > target:                       # 单句本身超长 ⇒ 只能字符切
            flush()
            for k in range(0, len(s), target):
                out.append((s[k:k + target], True))
            continue
        if cur and cur_len + len(s) > target:
            flush()
        cur.append(s)
        cur_len += len(s)
    flush()
    return out


def rechunk(text, target):
    """按行分组到 <= target；单行超长时**按句边界**切（见上方 2026-10-12 说明）。

    返回 pieces = [(text, sep_after, tag), ...]；重建 = p0 + sep0 + p1 + sep1 + ...
    sep 取 "\\n"（行边界）或 ""（行内切点）。
    tag = ""（自然行/句边界，锚点不带后缀）｜ "p<k>"（同一行内第 k 块）｜ "p<k>hard"（该块是
    单句超长后退回的字符切 —— 这一块**两端仍可能在词中间**，标出来让它可见、可统计）。
    """
    lines = text.split("\n")
    pieces, cur = [], []
    for i, line in enumerate(lines):
        if len(line) > target:                      # 单行超长：先冲掉手上的，再按句切这一行
            if cur:
                pieces.append(("\n".join(cur), "\n", ""))
                cur = []
            chunks = pack_sentences(split_sentences(line), target)
            tail_sep = "\n" if i < len(lines) - 1 else ""
            for k, (chunk, hard) in enumerate(chunks):
                last = (k == len(chunks) - 1)
                tag = f"p{k + 1}" + ("hard" if hard else "")
                pieces.append((chunk, tail_sep if last else "", tag))
            continue
        if cur and sum(len(x) for x in cur) + len(line) + len(cur) > target:
            pieces.append(("\n".join(cur), "\n", ""))
            cur = []
        cur.append(line)
    if cur:
        pieces.append(("\n".join(cur), "", ""))
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
        rebuilt = "".join(t + sep for t, sep, _tag in pieces)
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
        # ★ 锚点：行内切点必须带后缀，否则同一行切出的多块会撞同一个 `#l.K`。
        #   后缀 = "p<k>"（同一行内第 k 块）＋ "hard"（该块是单句超长后退回的字符切）。
        segs, line_no, n_hard = [], 1, 0
        for t, sep, tag in pieces:
            n_lines = t.count("\n") + 1
            start, end = line_no, line_no + n_lines - 1
            a_txt = f"#l.{start}-{end}" if n_lines > 1 else f"#l.{start}"
            if tag:                        # 行内切块：标出是第几块、以及是不是硬切
                a_txt += f"/{tag}"
                if tag.endswith("hard"):
                    n_hard += 1
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
                     "hard_pieces": n_hard,
                     "verdict": "已重分块"})
        n_ok += 1
        print(f"  ✓ {os.path.basename(p)[-44:]}  {len(text):>8,} 字 → {len(segs):>3} 段"
              f"（最大段 {maxseg} 字，硬切 {n_hard} 段）")
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
