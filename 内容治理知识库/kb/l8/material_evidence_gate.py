#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""material_evidence_gate.py —— **出口闸：报告的每一条证据都要落在「本单素材」里**。

## 它治的那个病（2026-10-20 真单）

Owner 发了一张图（两个母亲在聊天场景），报告里却出现一条：

```
F-02 ｜ 未归类 ｜ P2 ｜ 有库内条款依据
位置：图片 1（#img.1）
命中描述：1.挂式衣架: 磨砂亚克力材质,搭配透明防滑条
依据：《内部正负样本库（负面样本规则）》第 N-1.65 条 ← 命中「1.挂式衣架…」
```

而这张图的 9 行图内文字里**没有「衣架」** —— 那句话来自**另一条历史审核记录**，
是「相似召回」把别人的原话搬进了这一单的报告。

**为什么现成的尺子都拦不住它**（都查过，逐条）：

| 现有判据 | 它查什么 | 对这条的结论 |
|---|---|---|
| `workflow_smoke` S4 报告溯源 | 条款号 / 指纹 / 直链**三件在不在** | ✅ 绿（三件全有） |
| `citation_integrity` | 摘录能不能**回到某条 L0 记录** | ✅ 绿（它**确实是**另一条记录的原话） |
| `prd533` 位置校验 | 位置是不是三形态 | ⚠️ 只记读数，不阻断 |

⇒ 缺的正是这一条轴：**能不能回到 L0** ≠ **是不是这一单素材里的字**。

## 四条判据（逐条给 fail 理由，不合并、不吞）

- **R1a 引用必须出现在本单素材**：`excerpt` 非空 ⇒ 必须在素材原文里逐字找到
  （NFKC + 去空白 + 小写后比对）。
- **R1b 依据行不许夹带别家原文**：`basis_line` 里 `← 命中「…」` 的引文同样必须在素材里。
  ⚠️ 这一条是关键：2026-10-20 那单的 `excerpt` 已经是空，**别家原文是从依据行漏出来的**。
- **R2 历史意见必须自报家门**：命中若来自「相似召回 / 历史审核意见」（层名含"负面样本"或带
  `history_rule_text`）⇒ 必须①`excerpt` 为空 ②理由里写明「非本单」。写不出来就是冒充逐字命中。
- **R3 位置必须三形态且与模态对得上**：图片单 `图 N 第 X 处`（N ≤ 本单图片数）、
  视频单 `视频 MM:SS`、文字单 `正文第 X 段`。`图片 1（#img.1）` 这种**不是**三形态。
- **R4 渲染后同样要过**：传了报告 md 时，把「问题总览」表的 位置/命中描述 两列再量一遍
  ——防「数据层干净、渲染层回填」。

## 反向对照（`--selftest`，缺一条本判据就不算数）

A 真实事故件（依据行带「衣架」＋位置 `图片 1（#img.1）`）⇒ **必须红**（R1b + R3）
B 把引用换成本单图上真有的一句、位置写成 `图 1 第 4 处` ⇒ **必须绿**
C 位置改回 `图片 1（#img.1）` ⇒ **必须红**（R3 不是恒绿）
D 引用在"别的记录"里、不在本单素材里 ⇒ **必须红**（R1a 不是 `citation_integrity` 的复读）
E 历史意见条目：`excerpt` 空但理由没写「非本单」 ⇒ **必须红**（R2）

## 用法

    python3 kb/l8/material_evidence_gate.py --selftest
    python3 kb/l8/material_evidence_gate.py --merged-record <守衡 merged-*.json> [--json]
    python3 kb/l8/material_evidence_gate.py --pack <pack.json> [--json]
    python3 kb/l8/material_evidence_gate.py --latest [--json]     # 取守衡最近一份逐条记录

退出码：0 全过｜3 有 fail｜2 算不出来（缺件/结构不对）
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
import unicodedata

# ── 位置三形态（与 kb/l7/registry/prd533-constraints.yaml 同源）────────────────
LOC_FIGURE = re.compile(r"^图\s*(\d+)\s*第\s*(\d+)\s*处$")
LOC_VIDEO = re.compile(r"^视频\s*(\d{1,2}):(\d{2})$")
LOC_TEXT = re.compile(r"^正文第\s*(\d+)\s*段$")

# ★★ 2026-10-22（Owner 裁定「给面板形态开口子」）：**画面面板上的发现**没有「图内文字块阅读顺序行号」，
#   硬编一个「第 X 处」就是编造读数。真单：10:49 那张图单 3 条发现写成「图 1 上方面板 / 下方面板 / 主视觉」，
#   被 R3 判成「证据对不上本单素材」。⇒ 新增面板形态，与 `kb/l7/registry/prd533-constraints.yaml`
#   的 `figure_panel` **同一份闭集**（面板名只许这 7 个；区域词与 figure_area 同一份）。
#   两条反向边界：① 面板形态**不许**再带「第 X 处」（anchored 正则天然拒掉）；
#                 ② 面板名是闭集，`图 1 随便写` 一个都不进 —— 开放集等于把闸门关掉。
LOC_FIGURE_PANEL = re.compile(
    r"^(?:(?:图片)?(?:顶部|中部|底部|左侧|右侧)[，,]\s*)?"
    r"图\s*(\d+)\s*(?:上方面板|下方面板|左方面板|右方面板|中间面板|主视觉|整图)$")

# ★★ 2026-10-20（Owner：「位置：图 1 ==〉你要写上尽详细具体位置，比如：图片顶部，图 1 第 3 处」）：
#   位置允许**区域前缀**（`图片顶部，图 1 第 3 处`）。本闸门的 R3/R4 只判「图 N 第 X 处」这一半，
#   所以先剥掉区域词再匹配 —— 否则合规的新写法会被判红（尺子比人要严，等于假红）。
#   区域词表与 `kb/l7/registry/prd533-constraints.yaml::location.patterns[figure_area]` 同一份。
RE_AREA_PREFIX = re.compile(r"^(?:图片)?(?:顶部|中部|底部|左侧|右侧)[，,]\s*")


def strip_area_prefix(loc):
    """剥掉位置前面的区域词（`图片顶部，` / `画面底部,`），返回 `图 N 第 X 处`。"""
    return RE_AREA_PREFIX.sub("", str(loc or "").strip()).strip()


# 素材块头（链送进来的形状：`【图 1 内文字｜9 行】…【/图 1】` / `【图 1 画面读数…】…`）
RE_IMG_HEAD = re.compile(r"【\s*图\s*(\d+)\s*(?:内文字|上的字|的图内文字)")
RE_VID_HEAD = re.compile(r"【\s*视频\s*(\d+)")
# 依据行里「← 命中「…」」的引文
RE_BASIS_HIT = re.compile(r"命中\s*[「\"](.+?)[」\"]", re.S)
# 历史意见的自报家门
HIST_MARK = ("非本单", "历史审核意见", "相似召回")

DEFAULT_MERGED_DIR = os.path.expanduser(
    "~/Project/audit_multi_content/PMO/shouheng-state/merged-reports")


def _norm(s: str) -> str:
    """比对用归一化：NFKC（全半角统一）→ 去所有空白 → 小写。"""
    t = unicodedata.normalize("NFKC", str(s or ""))
    t = re.sub(r"[\s\u3000]+", "", t)
    return t.lower()


def material_text_of(record: dict) -> str:
    """从守衡逐条记录的 `question` 里取**素材本身**的文字（图内 OCR + 画面读数 + 文案）。

    为什么要挑，不整段用：`question` 里还夹着给模型看的指令句（「只能依据这一格」之类），
    整段当素材会让"引用出现在指令里"也算过 —— 那正是要防的一类假绿。
    挑不出块时**整段回落**（宁可宽一点也不静默放过）。
    """
    q = str((record or {}).get("question") or "")
    if not q:
        return ""
    parts = []
    # 图内文字块（**连块头一起留**：模态判定要靠 `【图 N 内文字】` 这个头）
    for m in re.finditer(r"【图\s*(\d+)\s*内文字[^】]*】\n.*?\n【/图\s*\1】", q, re.S):
        parts.append(m.group(0))
    # 画面读数块
    for m in re.finditer(r"【图\s*(\d+)\s*画面读数[^】]*】\n.*?\n【/图\s*\1\s*画面读数】", q, re.S):
        parts.append(m.group(0))
    # 视频块（若有）
    for m in re.finditer(r"【视频\s*(\d+)[^】]*】\n.*?(?=\n【|\Z)", q, re.S):
        parts.append(m.group(0))
    if parts:
        return "\n".join(parts)
    return q


def modality_of(material_text: str) -> tuple[str, int]:
    """素材形态：('image', 图片数) / ('video', n) / ('text', 0)。"""
    imgs = [int(x) for x in RE_IMG_HEAD.findall(material_text or "")]
    if imgs:
        return "image", max(imgs)
    if RE_VID_HEAD.search(material_text or ""):
        return "video", 1
    return "text", 0


def _in_material(quote: str, material_norm: str) -> bool:
    q = _norm(quote)
    if not q:
        return False
    return q in material_norm


def check_item(item: dict, material_norm: str, modality: str, img_n: int) -> list:
    fails = []
    iid = str(item.get("f_id") or item.get("id") or item.get("index") or "?")
    loc = str(item.get("location") or "").strip()
    exc = str(item.get("excerpt") or "").strip()
    kb = item.get("kb") if isinstance(item.get("kb"), dict) else {}
    basis = str(kb.get("basis_line") or item.get("basis") or item.get("basis_line") or "")
    layer = str(item.get("layer") or kb.get("layer") or "")
    hist_txt = str(item.get("history_rule_text") or kb.get("history_rule_text") or "")
    reason = str(item.get("reason") or "")
    gap = str(item.get("evidence_gap") or "")

    # R1a
    if exc and not _in_material(exc, material_norm):
        fails.append({"item": iid, "rule": "R1a",
                      "msg": "excerpt 不在本单素材里：%r" % exc[:40]})
    # R1b
    for m in RE_BASIS_HIT.finditer(basis):
        quote = m.group(1).strip(" `「」\"'")
        if quote and not _in_material(quote, material_norm):
            fails.append({"item": iid, "rule": "R1b",
                          "msg": "依据行的命中文案不在本单素材里：%r" % quote[:40]})
            break
    # R2
    is_hist = ("负面样本" in layer) or bool(hist_txt.strip()) or ("相似召回" in layer)
    if is_hist:
        if exc:
            fails.append({"item": iid, "rule": "R2",
                          "msg": "历史审核意见条目不许带 excerpt（会把历史原文当逐字命中）"})
        blob = reason + gap
        if not any(k in blob for k in HIST_MARK):
            fails.append({"item": iid, "rule": "R2",
                          "msg": "历史审核意见条目没写「非本单/历史审核意见」——读者会当成逐字命中"})
    # R3
    if modality == "image":
        # 区域前缀（`图片顶部，图 1 第 3 处`）先剥掉再判形态 —— 见 `strip_area_prefix`。
        _core = strip_area_prefix(loc)
        mm = LOC_FIGURE.match(_core)
        mm_panel = LOC_FIGURE_PANEL.match(_core)      # 2026-10-22：面板类发现
        if not (mm or mm_panel):
            fails.append({"item": iid, "rule": "R3",
                          "msg": "图片单的位置必须是「图 N 第 X 处」或「图 N <面板名>」"
                                 "（面板名闭集：上方面板/下方面板/左方面板/右方面板/中间面板/主视觉/整图），"
                                 "实得 %r" % loc})
        elif int((mm or mm_panel).group(1)) > max(img_n, 1):
            fails.append({"item": iid, "rule": "R3",
                          "msg": "位置指向 图 %s，但本单只有 %d 张图"
                                 % ((mm or mm_panel).group(1), img_n)})
    elif modality == "video":
        if not LOC_VIDEO.match(loc):
            fails.append({"item": iid, "rule": "R3",
                          "msg": "视频单的位置必须是「视频 MM:SS」，实得 %r" % loc})
    else:
        if not LOC_TEXT.match(loc):
            fails.append({"item": iid, "rule": "R3",
                          "msg": "文字单的位置必须是「正文第 X 段」，实得 %r" % loc})
    return fails


def check_pack(pack: dict) -> dict:
    """pack = {"material": {"text": ...}, "items": [...], "report_md": str?}"""
    material = str(((pack.get("material") or {}).get("text")) or "")
    material_norm = _norm(material)
    modality, img_n = modality_of(material)
    items = pack.get("items") or []
    fails, checked = [], 0
    for it in items:
        checked += 1
        fails.extend(check_item(it, material_norm, modality, img_n))
    # R4：渲染后的报告（表格两列）
    md = str(pack.get("report_md") or "")
    if md:
        for line in md.split("\n"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) < 5 or not re.match(r"^\d+$", cells[0] or ""):
                continue
            loc, hit = cells[3], cells[4]
            checked += 1
            # 同样先剥区域词（新写法 `图片顶部，图 1 第 3 处` 必须照旧绿，否则是尺子比人严）
            _loc = strip_area_prefix(loc)
            if _loc and _loc not in ("—", "-") and not (
                LOC_FIGURE.match(_loc) or LOC_FIGURE_PANEL.match(_loc)
                or LOC_VIDEO.match(_loc) or LOC_TEXT.match(_loc)):
                fails.append({"item": "md#%s" % cells[0], "rule": "R4",
                              "msg": "报告表里的位置不是三形态：%r" % loc})
            q = hit.strip("`").rstrip("…").strip()
            if q and q not in ("—", "-") and not _in_material(q, material_norm):
                fails.append({"item": "md#%s" % cells[0], "rule": "R4",
                              "msg": "报告表的命中描述不在素材里：%r" % q[:40]})
    return {"ok": not fails, "fails": fails, "checked_items": checked,
            "modality": modality, "images": img_n,
            "material_chars": len(material)}


def pack_from_merged_record(record: dict) -> dict:
    """守衡逐条记录（`PMO/shouheng-state/merged-reports/merged-*.json`）⇒ pack。"""
    rd = record or {}
    mat = {"text": material_text_of(rd)}
    items = []
    for it in (rd.get("items") or []):
        kb = it.get("kb") if isinstance(it.get("kb"), dict) else {}
        items.append({
            "f_id": it.get("f_id") or it.get("id"),
            "index": it.get("index"),
            "location": it.get("location"),
            "excerpt": it.get("excerpt"),
            "reason": it.get("reason"),
            "basis_line": kb.get("basis_line"),
            "kb": kb,
            "layer": it.get("layer") or "",
            "history_rule_text": it.get("history_rule_text") or kb.get("history_rule_text") or "",
            "evidence_gap": it.get("evidence_gap") or "",
            "source": it.get("source"),
        })
    return {"material": mat, "items": items}


def check_merged_record(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        rec = json.load(f)
    out = check_pack(pack_from_merged_record(rec))
    out["record"] = path
    out["record_mtime"] = os.path.getmtime(path)
    return out


def latest_merged_record(directory: str = DEFAULT_MERGED_DIR) -> str | None:
    files = glob.glob(os.path.join(directory, "merged-*.json"))
    if not files:
        return None
    return max(files, key=os.path.getmtime)


# ── 自证（1 正 + 5 反，缺一条本判据就不算数）─────────────────────────────────
MATERIAL = """【图 1 内文字｜9 行】
Breastfeeding Month
Share What Helped. Find Real Support.
Help Another Mom.
Share real breastfeeding and pumping experiences，
help build the Support List, and get a chance to win prizes worth
up to $199.99.
Join Breastfeeding Month
MOmCOZY
MOmCOZY
【/图 1】
【图 1 画面读数（视觉模型的读数，**不是原图**；涉及画面的结论只能依据这一格）】
- 场景：客厅
- 人物：成人 · 坐在沙发上拿笔写字；成人 · 抱着婴儿坐在沙发上；婴幼儿 · 被成人抱在怀里
【/图 1 画面读数】"""


def _item(**kw):
    base = {"f_id": "F-01", "location": "图 1 第 4 处", "excerpt": None,
            "kb": {}, "reason": "x", "layer": "", "history_rule_text": "", "evidence_gap": ""}
    base.update(kw)
    return base


def selftest() -> int:
    bad = []

    def chk(name, got, want):
        if got == want:
            print("  ✅ %s" % name)
        else:
            print("  ❌ %s —— 期望 %r，实得 %r" % (name, want, got))
            bad.append(name)

    # A 真实事故件：依据行夹带「衣架」＋ 位置 `图片 1（#img.1）` ⇒ 必须红
    a = check_pack({"material": {"text": MATERIAL}, "items": [_item(
        location="图片 1（#img.1）",
        kb={"basis_line": "《内部正负样本库（负面样本规则）》第 N-1.65 条 ← 命中「1.挂式衣架: 磨砂亚克力材质,搭配透明防滑条」"},
    )]})
    chk("A 真实事故件 ⇒ 红（R1b 依据行夹带别家原文）",
        [f["rule"] for f in a["fails"]], ["R1b", "R3"])
    # B 换成本单图上真有的一句 + 三形态位置 ⇒ 必须绿
    b = check_pack({"material": {"text": MATERIAL}, "items": [_item(
        location="图 1 第 4 处",
        kb={"basis_line": "《库》第 W-1.18 条 ← 命中「Share What Helped. Find Real Support.」"},
    )]})
    chk("B 引用落在本单素材 + 位置三形态 ⇒ 绿", b["ok"], True)
    # C 位置改回 `图片 1（#img.1）` ⇒ 必须红（R3 不是恒绿）
    c = check_pack({"material": {"text": MATERIAL}, "items": [_item(
        location="图片 1（#img.1）",
        kb={"basis_line": "《库》第 W-1.18 条 ← 命中「Help Another Mom.」"},
    )]})
    chk("C 位置不是三形态 ⇒ 红（R3）", [f["rule"] for f in c["fails"]], ["R3"])
    # D 引用只存在于"别的记录"（不在本单素材）⇒ 必须红（R1a 不是 citation_integrity 的复读）
    d = check_pack({"material": {"text": MATERIAL}, "items": [_item(
        excerpt="1.挂式衣架: 磨砂亚克力材质,搭配透明防滑条",
        kb={"basis_line": "《库》第 N-1.65 条"},
    )]})
    chk("D 引用不在本单素材 ⇒ 红（R1a）", [f["rule"] for f in d["fails"]], ["R1a"])
    # E 历史意见条目：excerpt 空但理由没写「非本单」⇒ 必须红（R2）
    e = check_pack({"material": {"text": MATERIAL}, "items": [_item(
        layer="负面样本规则（N-1.x）", history_rule_text="1.挂式衣架…",
        reason="匹配分 1.00（画面 1.00 / 文字 0.73）",   # ← 故意不写「非本单/历史审核意见」
    )]})
    chk("E 历史意见没自报家门 ⇒ 红（R2）", [f["rule"] for f in e["fails"]], ["R2"])
    # F 反向对照的对照：素材为空时**不许**恒绿
    f = check_pack({"material": {"text": ""}, "items": [_item(
        excerpt="随便一句", location="图 1 第 1 处")]})
    chk("F 素材为空 ⇒ 红（R1a 不恒绿；R3 也跟着响：没素材就判不了模态）",
        [x["rule"] for x in f["fails"]], ["R1a", "R3"])

    # ★★ 2026-10-22：面板形态（`图 1 上方面板`）—— 三条，成对
    #   G 面板形态**必须绿**（这是这次开口子的原因；不给它一条正例，等于既没开也没验）
    g = check_pack({"material": {"text": MATERIAL}, "items": [_item(
        location="图 1 上方面板",
        kb={"basis_line": "《库》第 W-1.18 条 ← 命中「Share What Helped. Find Real Support.」"},
    )]})
    chk("G 面板形态（图 1 上方面板）⇒ 绿", g["ok"], True)
    #   H 面板形态带「第 X 处」⇒ 必须红（面板上没有可复核的文字行号，那个 X 是编的）
    h = check_pack({"material": {"text": MATERIAL}, "items": [_item(
        location="图 1 上方面板 第 3 处",
        kb={"basis_line": "《库》第 W-1.18 条 ← 命中「Share What Helped. Find Real Support.」"},
    )]})
    chk("H 面板形态再带「第 X 处」⇒ 红（拒绝编造行号）", [x["rule"] for x in h["fails"]], ["R3"])
    #   I 面板名不在闭集里 ⇒ 必须红（`图 1 随便写` 不许进，否则闸门等于关掉）
    i = check_pack({"material": {"text": MATERIAL}, "items": [_item(
        location="图 1 随便写",
        kb={"basis_line": "《库》第 W-1.18 条 ← 命中「Share What Helped. Find Real Support.」"},
    )]})
    chk("I 面板名不在闭集 ⇒ 红（开口子不等于开大门）", [x["rule"] for x in i["fails"]], ["R3"])

    total = 6 + 3
    print("\n自证：通过 %d / 失败 %d" % (total - len(bad), len(bad)))
    return 0 if not bad else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="出口闸：报告证据是否落在本单素材")
    ap.add_argument("--merged-record", help="守衡逐条记录 merged-*.json")
    ap.add_argument("--latest", action="store_true", help="取守衡最近一份逐条记录")
    ap.add_argument("--pack", help="pack.json（material/items/report_md）")
    ap.add_argument("--dir", default=DEFAULT_MERGED_DIR, help="merged-reports 目录")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--strict", action="store_true",
                    help="连「判据建之前的存量记录」也判红（默认：存量只报不改红）")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    if a.pack:
        with open(a.pack, encoding="utf-8") as f:
            res = check_pack(json.load(f))
    else:
        path = a.merged_record or (latest_merged_record(a.dir) if a.latest else None)
        if not path:
            print("未测：没有逐条记录（%s）—— 不计红" % a.dir)
            return 0
        if not os.path.exists(path):
            print("算不出来：记录不存在 %s" % path, file=sys.stderr)
            return 2
        res = check_merged_record(path)
    # ★ 存量口径（2026-10-20）：本判据**建之前**产出的记录只**报**、不判红 ——
    #   同 `prd_card_conformance` 的「存量登记、只对变差响」。新记录（mtime ≥ 判据文件）
    #   一律照判；要看历史记录的真红，用 `--strict`。
    legacy = bool(res.get("record_mtime")) and res["record_mtime"] < os.path.getmtime(__file__)
    res["legacy_record"] = legacy
    # ★★ 2026-10-20：**存量口径要进 JSON 的 `ok`**，不能只体现在退出码上 ——
    #   `ci/run_gates.py` 有一条 fail-closed 规则：「退出码 0 但 JSON 里 ok=false ⇒ 判红」。
    #   ⇒ 存量记录（判据建之前的）把红项挪进 `known_drift`，`ok=true`；`--strict` 照旧 ok=false。
    if legacy and not a.strict and res.get("fails"):
        res["known_drift"] = res["fails"]
        res["fails"] = []
        res["ok"] = True
    if a.json:
        print(json.dumps(res, ensure_ascii=False, indent=1))
    else:
        print("形态=%s｜图片=%d｜素材 %d 字｜核了 %d 条"
              % (res["modality"], res["images"], res["material_chars"], res["checked_items"]))
        for f in res["fails"]:
            print("  ✗ [%s] %s：%s" % (f["rule"], f["item"], f["msg"]))
        print("结论：%s" % ("✅ 每条证据都落在本单素材里" if res["ok"] else "❌ 有条目对不上本单素材"))
    if res["ok"]:
        return 0
    if legacy and not a.strict:
        # ⚠️ 这行**只打到 stderr**：`--json` 的调用方（workflow_smoke S10 / CI）要解析 stdout
        print("（存量：这份记录产出于本判据建立之前 ⇒ 只报不改红；要看真红用 --strict）",
              file=sys.stderr)
        return 0
    return 3


if __name__ == "__main__":
    sys.exit(main())
