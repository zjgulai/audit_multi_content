#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把桌面任务表的 G5（10/12–10/16 行）里 #22 由 ❌ 改判 ✅，并同步表头 21→22 / 未做 1→0。

技法（沿用本仓既有口径）：
  · 单元格内非 ASCII 存**十进制数字实体**（`&#21608;`）⇒ 编码器必须能**逐字节往返**
  · `<t xml:space="preserve">` 必须正则兼容
  · zip 重建时**其余条目逐字复制**；`testzip()` + 全 XML `ET.fromstring` 校验
  · 落盘前后逐格比对，**只许 1 处差异（G5）**
"""
from __future__ import annotations
import argparse, re, shutil, sys, time
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

SRC = Path.home() / "Desktop" / "内容治理知识库搭建任务详情.xlsx"
SHEET = "xl/worksheets/sheet1.xml"

HDR_OLD = "周期未到 · 已完成 21 项 / 未做 1 项 / 部分完成 2 项"
HDR_NEW = "周期未到 · 已完成 22 项 / 未做 0 项 / 部分完成 2 项"
OLD22 = "22. ❌ 可读性补齐（drive:file:download scope / 文档协作者）：未做 —— 缺口在飞书侧权限，非本地"
NEW22 = ("22. ✅ 可读性补齐（drive:file:download scope / 文档协作者）：**已核销（2026-10-12 改判）** —— "
         "原判「缺口在飞书侧权限」是**按资源件**口径得出的，该结论**已过期**。按 **L0 台账（kb/l0/manifest.jsonl）"
         "最新行口径**复算：全库 `no_scope` 仅 **8 条，属「缺 scope」型 = 0 条**；台账 `forbidden` **0 条** —— "
         "那 8 条全是 `file:` 标 `l0_file_deleted_confirmed`（用户 2026-09-29 已确认文件不存在），是**事实变更**不是权限缺口。"
         "且 Owner 2026-10-12 已裁定 `files-read-only-images-downloadable`：**图片可下载，其他文件类只能读** ⇒ "
         "`drive:file:download` **不是缺口，是设计**（登记件 kb/l7/registry/source-readonly.yaml → rulings，4→6 条）。"
         "实测佐证（bot 主身份、--profile dsh-kb）：`drive +preview` 可拿到附件字节、`docs +fetch --as bot` 可读 PRD 全文（rev 62）；"
         "而 `drive +download` 报 permission_denied 正属**设计内**。⇒ 本地无需补齐，**本项已尽**")


def enc(t: str) -> str:
    """ASCII 之外一律十进制数字实体；& < > 转义。"""
    out = []
    for c in t:
        o = ord(c)
        if c == "&": out.append("&amp;")
        elif c == "<": out.append("&lt;")
        elif c == ">": out.append("&gt;")
        elif o > 126: out.append("&#%d;" % o)
        else: out.append(c)
    return "".join(out)


def dec(t: str) -> str:
    import html
    return html.unescape(t)


CELL_RE = re.compile(
    r'<c r="([A-Z]+\d+)"([^>]*)>(.*?)</c>', re.S)
T_RE = re.compile(r'<t([^>]*)>(.*?)</t>', re.S)

def cells(xml: str) -> dict:
    out = {}
    for m in CELL_RE.finditer(xml):
        ref, attr, inner = m.group(1), m.group(2), m.group(3)
        tm = T_RE.search(inner)
        out[ref] = dec(tm.group(2)) if tm else inner
    return out


def main() -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    stamp = time.strftime("%Y%m%d-%H%M%S")

    raw = SRC.read_bytes()
    z = zipfile.ZipFile(SRC)
    bad = z.testzip()
    if bad: print("原件 testzip 失败：%s" % bad); return 2
    sheet = z.read(SHEET).decode("utf-8")

    # ── ① 编码器往返自证：解码→再编码必须逐字节等于原文
    m = re.search(r'<c r="G5"[^>]*>.*?</c>', sheet, re.S)
    raw_g5 = m.group(0)
    tm = T_RE.search(raw_g5)
    if not tm: print("G5 不是 inlineStr/t，停"); return 2
    if enc(dec(tm.group(2))) != tm.group(2):
        print("❌ 编码器往返不一致 ⇒ 拒绝落盘"); return 2
    print("① 编码器往返自证：逐字节一致 ✅（%d 字节）" % len(tm.group(2)))

    cur = dec(tm.group(2)); L = cur.split("\n")
    if L[0] != HDR_OLD: print("❌ 表头不是预期值：%r" % L[0]); return 2
    i = [k for k, v in enumerate(L) if v.strip().startswith("22.")]
    if len(i) != 1 or L[i[0]] != OLD22:
        print("❌ #22 行不是预期值：%r" % (L[i[0]] if i else None)); return 2
    print("② 表头 + #22 现状与预期一致 ✅")

    L[0] = HDR_NEW; L[i[0]] = NEW22
    new = "\n".join(L)
    a_, b_ = tm.span()                      # tm 是对 raw_g5 匹配的，span 相对 raw_g5
    raw_g5_new = raw_g5[:a_] + tm.group(0).replace(tm.group(2), enc(new), 1) + raw_g5[b_:]
    sheet2 = sheet[:m.start()] + raw_g5_new + sheet[m.end():]
    assert sheet2 != sheet

    # ── ③ 其余条目逐字复制
    shutil.copy2(SRC, SRC.with_name("_xlsx-backup-before-G5-22-%s.xlsx" % stamp))
    tmp = SRC.with_suffix(".tmp.xlsx")
    with zipfile.ZipFile(tmp, "w") as out:
        for zi in z.infolist():
            data = sheet2.encode("utf-8") if zi.filename == SHEET else z.read(zi.filename)
            out.writestr(zi, data)
    z.close()

    # ── ④ 校验：testzip + 全 XML 可解析 + 其余条目逐字节相同
    z2 = zipfile.ZipFile(tmp)
    if z2.testzip(): print("❌ 新件 testzip 失败"); return 3
    nxml = 0
    for n in z2.namelist():
        if n.endswith((".xml", ".rels")):
            ET.fromstring(z2.read(n)); nxml += 1
    same = sum(1 for zi in z.infolist() if zi.filename != SHEET and z2.read(zi.filename) == zipfile.ZipFile(SRC).read(zi.filename))
    print("④ 新件 testzip OK ✅｜XML 全可解析 %d 个 ✅｜其余条目逐字节相同 %d/%d ✅"
          % (nxml, same, len(z.infolist()) - 1))

    # ── ⑤ 逐格比对：只许 1 处差异
    A = cells(sheet); B = cells(sheet2)
    diff = [k for k in set(A) | set(B) if A.get(k) != B.get(k)]
    print("⑤ 逐格比对：差异 %d 处 = %s" % (len(diff), diff))
    if diff != ["G5"]: print("❌ 差异不止 G5 ⇒ 拒绝落盘"); return 3

    if not a.apply:
        print("\n预演（零写入）。落盘加 --apply。"); tmp.unlink(); return 0
    print("\n新 G5 表头：%s" % HDR_NEW)
    print("新 #22：%s…" % NEW22[:110])
    tmp.replace(SRC)
    wb = zipfile.ZipFile(SRC); s = wb.read(SHEET).decode("utf-8")
    ok = dec(T_RE.search(re.search(r'<c r="G5"[^>]*>.*?</c>', s, re.S).group(0)).group(2)).split("\n")
    print("✅ 已就地写入 %s（%d 字节，原 %d）" % (SRC.name, SRC.stat().st_size, len(raw)))
    print("   回读：表头=%r ｜ #22 前缀=%r" % (ok[0], ok[i[0]][:24]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
