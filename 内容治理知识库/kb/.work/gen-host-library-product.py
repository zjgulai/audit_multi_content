#!/usr/bin/env python3
"""
4_产品描述库：把 l2 单元层里的产品事实素材产出成宿主条目。

为什么单独一个生成器（2026-09-28）：
    PRD §7.1 规定 4 个子库，第 4 个是「产品描述库」（覆盖 P1+P2）。但它一直是空的，
    而且**不是生成器漏了映射** —— 主生成器的 `dir_by_type` 里早就有
    `product_desc → 4_产品描述库`，问题是**没有输入喂给它**：
      · 主生成器只读 l3/candidates/rules.jsonl（509 条 wording）
      · l4 生成器只读 l4/canonical/{scoped_clause,sample_case}.jsonl
      · 而 `product_desc` 在这三处一条都没有；它只出现在 `l2/units.jsonl`（9 行）
      · 主生成器虽然也读 l2/units.jsonl，但**只用来数数**（写进 manifest 的 provenance），
        不参与产出 —— 所以这 9 行一直躺在单元层，从没变成条目。
    这个生成器就是把这条断链接上：**从 l2 单元直接产出产品描述库条目**。

它产出什么、不产出什么（写清楚，避免被误用）：
    产出：产品事实素材（品线构成、型号、类目、卖点、边界、认证口径的原文摘录）。
    不产出：合规规则。这些条目是**素材层**，不是判据层 —— 每条的 `not_proves` 与
    `forbidden` 里写明「不能据它判 BLOCK」「参数与认证以产品/法务正式发布为准」。

为什么按 100 字过滤：
    l2 里 9 行 product_desc，逐行量过长度：24 / 5 / 37 / 45 / 25 字的是**提纲与字段清单**
    （「产品线、型号、卖点、边界、禁止表述、认证、FAQ」「产品描述库」
    「吸奶器 Misty/银舒涵、喂养 William、品牌 Daisy/张丽敏、专家 Emma」——最后这条是人名）；
    而 10525 / 2309 / 1814 / 179 字的是**真内容**（官网文本 + 三份品线产品信息汇总）。
    100 字这条线在实测数据上把两者干净分开，而且判据可复算，不是拍脑袋。
    179 字那条虽然短，但它是「喂养品线产品信息内容汇总」的开头（真内容、只是被截断），
    所以保留 —— 宁可在条目里如实写明它是节选，也不要手工丢内容。

用法（必须排在主生成器与 l4 生成器之后，因为它往同一份 manifest 里追加）：
    python3 kb/.work/gen-host-library.py         --out kb/.work/hostlib
    python3 kb/.work/gen-host-library-l4.py      --out kb/.work/hostlib
    python3 kb/.work/gen-host-library-product.py --out kb/.work/hostlib
（publish.sh 已经把这三步串成一条命令，平时不用手跑。）
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import importlib.util
import json
import os
import re
import sys
from datetime import date, timedelta

KB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # …/内容治理/kb
L4_PATH = os.path.join(KB, ".work", "gen-host-library-l4.py")

SRC_UNITS = os.path.join(KB, "l2", "units.jsonl")
# 第二条源：飞书表格「W1卖点匹配证据库」（由 fetch-w1-evidence.py 抓成本地缓存）
SRC_SHEET = os.path.join(KB, ".work", "sources", "w1-evidence.json")
# 判据层规则（3_措辞表达库 的来源）。用来给产品库条目补「判据层对应规则」指引，见 judgment_pointer()。
SRC_RULES = os.path.join(KB, "l3", "candidates", "rules.jsonl")

SUBDIR = "4_产品描述库"
# 分档约定（与 3_措辞表达库 一致）：目录名 = tier
#   事实素材（卖点/文献证据/转译卡/缺口/术语/说明书） → L1-facts   / tier L1 / kind fact
#   判定口径（表达边界三态、术语口径）               → L2-concepts / tier L2 / kind judgment
# 目录跟着 kind 走，tier 跟着目录走 —— 两者必须一致，否则守衡按 tier 过滤时会漏条。
COLLECTION = {
    "dir": SUBDIR,
    "name": "内容治理知识库 · 产品描述库",
    "display_name": "产品描述库",
    "source": "① kb/l2/units.jsonl（kb_type=product_desc 的单元；源自飞书产品信息汇总与官网）"
              " ② 飞书表格《W1卖点匹配证据库》（wiki EsCdw2A7tiz67Rk8LgMce2TAnEh，7 个工作表 / 100 条）",
    "note": "产品线构成、型号、类目、卖点与边界口径的原文素材（PRD §7.1，覆盖 P1+P2）。"
            "两个来源：产品基本事实（来源①）与 W1 卖点匹配证据库（来源②，含 01_卖点护照、"
            "02_表达边界三态、03_文献研究证据库 56 条、04_内容转译卡、05_验证缺口、06_术语与口径）。"
            "**这是产品事实与口径素材，不是合规规则** —— 「绿色-可用」不等于任何渠道都能发，"
            "不能据它判 BLOCK；参数与认证的最终口径以产品/法务正式发布为准。",
    "form": "product_desc",
}

# 短于这个长度的是提纲/字段清单/人名，不是内容（判据见模块 docstring）。
MIN_CONTENT_CHARS = 100

# 产品信息比规则变得快（新品、改版、认证状态），半衰期取规则的 180 天的一半。
PRODUCT_HALF_LIFE_DAYS = 90

_SPEC = importlib.util.spec_from_file_location("_genl4", L4_PATH)
l4 = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(l4)
gen = l4.gen  # 主生成器（l4 已经把它加载好了）


def load_l1_titles() -> dict:
    """resource_id → (标题, 网址)。产品素材的来源信息在 l1 层，l2 单元里没有。

    为什么要去 l1 找：条目的 `source.ref` 得是**能点回去的地址**，而 l2 单元里只有
    resource_id（形如 `wiki__CUMOwJyo9iWNB7kfQMpc2LOSnAe`）。拿不出真地址就退化成
    resource_id 本身，那样引用链就断了。
    """
    out: dict[str, tuple[str, str]] = {}
    d = os.path.join(KB, "l1", SUBDIR)
    if not os.path.isdir(d):
        return out
    for name in os.listdir(d):
        if not name.endswith(".json"):
            continue
        try:
            with open(os.path.join(d, name), encoding="utf-8") as handle:
                rec = json.load(handle)
        except Exception:
            continue
        rid = rec.get("resource_id")
        if not rid:
            continue
        src = rec.get("source") or {}
        title = (src.get("title") or "").strip()
        url = (src.get("url") or "").strip()
        if not url:
            # resource_id 形如 wiki__<token> / doc__<token>，能还原成飞书地址
            kind, _, token = rid.partition("__")
            if token:
                path = {"wiki": "wiki", "doc": "docx", "sheet": "sheets", "slides": "slides"}.get(kind)
                if path:
                    url = f"https://momcozy-in.feishu.cn/{path}/{token}"
        out[rid] = (title, url)
    return out


def first_line(text: str) -> str:
    for line in text.splitlines():
        line = line.strip()
        if line:
            return line
    return ""


def build_product_meta(rec: dict, today: str, valid_until: str, l1: dict) -> tuple[dict, str]:
    """l2 单元 → meta + body"""
    unit_id = str(rec.get("unit_id") or "")
    raw = (rec.get("text") or "").strip()
    body_text, pii_hit = l4.mask_pii(raw)

    rid = str(rec.get("resource_id") or "")
    l1_title, l1_url = l1.get(rid, ("", ""))
    headline = l1_title or first_line(raw)[:60] or "产品信息素材"
    is_excerpt = len(raw) < 400

    meta: dict = {
        "id": f"cg-pd-{unit_id}",
        "title": f"产品描述库：{headline}",
        "collection": SUBDIR,
        "tier": "L1",
        "topic": "产品信息",
        "kind": "fact",
        "summary": (
            f"产品事实素材（{len(raw)} 字）：{headline}。"
            f"{'**这是节选**，原文更长。' if is_excerpt else ''}"
            "来源为品线产品信息汇总/官网，属单元层素材，未过正式验收。"
        ),
        "owner": gen.LIBRARY_OWNER,
        "evidence_level": "L1",
        "data_level": gen.DATA_LEVEL,
        "sensitivity_level": gen.SENSITIVITY,
        "half_life_days": PRODUCT_HALF_LIFE_DAYS,
        "created_at": today,
        "valid_until": valid_until,
        "asks": [
            f"{headline} 里有哪些品线/类目/型号",
            "这个品线的卖点与描述边界是什么",
            "文案里写的型号/参数能不能和产品事实对上",
            "这份产品信息的来源是哪份材料（锚点 + 指纹）",
        ],
        "not_proves": (
            "**不能证明文案合规**：这是产品事实素材，不是合规规则 —— 和它一致不等于内容合规，"
            "和它不一致也不由它单独判违规。"
            "不能证明该条已过正式验收（单元层素材，未走晋升）。"
            "不能替代产品/法务对参数与认证的正式口径。"
            "不能证明本条目之外的品线情况（未覆盖 ≠ 不存在）。"
        ),
        "forbidden": (
            "不许把它当判据层用：**不许据它下 BLOCK 或放行结论**，判定的依据只能来自措辞表达库的规则条目。"
            "不许把分片当成完整产品手册（原文可能更长，本条可能是节选）。"
            "引用时必须注明来源是产品事实素材层，并给出本条 id。"
        ),
        "related": [],
        "source": {
            "kind": "feishu-wiki" if rid.startswith(("wiki__", "doc__")) else "feishu",
            "ref": l1_url or rid or "kb/l2/units.jsonl",
            "fingerprint": str(rec.get("source_sha256") or f"l2-units/{unit_id}"),
            "captured_at": today,
        },
        "provenance": {
            "anchor": f"kb/l2/units.jsonl#{unit_id}",
            "confidence": "确定",
        },
        "pii": {
            "detected": pii_hit,
            "masked": pii_hit,
            "strategy": "按条目内出现的 @人名 做不可逆脱敏；产品信息本身不含自然人信息则原样保留",
        },
        "unit_id": unit_id,
        "resource_id": rid,
        "unit_type": rec.get("unit_type") or "",
        "char_count": len(raw),
        "excerpt": is_excerpt,
    }
    body = body_text + "\n"
    return meta, body


# ── 第二条源：飞书表格「W1卖点匹配证据库」 ──────────────────────────────────
#
# 为什么值得单独接：这张表是 W1 产品"能不能这么说"的判据底座 ——
#   01_卖点护照   每个卖点的推荐表达 / 不能说·谨慎说 / 证据强度
#   02_表达边界   **三态判定**（绿色-可用 / 黄色-需限定 / 红色-禁用）+ 使用条件 + 理由
#   03_文献研究证据库  56 条文献证据（来源/页码/研究结果/引用段落）
# 有了它，产品描述库才不只是"产品简介"，而是能回答"这个卖点的这句话越界没有"。
#
# 分档约定（与既有子库一致）：事实类 → L1-facts / tier L1；判定口径 → L2-concepts / tier L2。
SHEET_SPECS = {
    "00_使用说明": {"id": "cg-w1-manual", "kind": "fact", "label": "W1 证据库使用说明",
                    "one_per": "sheet"},
    "01_卖点护照": {"id": "cg-w1-sp", "kind": "fact", "label": "W1 卖点护照",
                    "one_per": "row", "key": "卖点ID"},
    "02_表达边界": {"id": "cg-w1-bd", "kind": "judgment", "label": "W1 表达边界",
                    "one_per": "row", "key": "卖点ID"},
    "03_文献研究证据库": {"id": "cg-w1-ev", "kind": "fact", "label": "W1 文献证据",
                          "one_per": "row", "key": "证据ID"},
    "04_内容转译卡": {"id": "cg-w1-tr", "kind": "fact", "label": "W1 内容转译卡",
                      "one_per": "row", "key": "卖点ID"},
    "05_验证缺口": {"id": "cg-w1-gap", "kind": "fact", "label": "W1 验证缺口",
                    "one_per": "row", "key": "卖点ID"},
    "06_术语与口径": {"id": "cg-w1-term", "kind": "judgment", "label": "W1 术语与口径",
                      "one_per": "row", "key": "术语"},
}


def safe_key(value: str) -> str:
    """把 key 变成能进 id 的 ASCII 段；中文/空值退回行号。"""
    keep = re.sub(r"[^A-Za-z0-9-]", "", value or "")
    return keep or "x"


# ── 把产品库条目接回判据层（2026-09-28 加）────────────────────────────────────
#
# 为什么需要（实测踩到，是个**入口缺失**）：
#   判据层 3_措辞表达库 的规则条目里，**没有一个字**是卖点号或表达类型
#   —— `rules.jsonl` 的 `scope.sellpoint` 509 条全部为 null，规则正文只抄了
#   `建议表达 / 限定要求 / 判定理由` 三个字段。实测：
#       3_措辞表达库 含「操作负担」→ 0 条
#       3_措辞表达库 含「W1-04」  → 0 条
#   后果：按卖点名/表达类型查判据层会得到**假「没有相关规则」**。
#   W-1.42 明明就是「操作负担（W1-04）」这条卖点的判定规则（P1·黄），却查不到。
#   守衡那次能引到它，是先在产品库查到 W1 表达边界，再顺着建议表达的措辞「绕」进去的
#   —— 推理链完整，但入口本身是缺的。
#
# 本次只做**方向①**：在产品库的表达边界条目里写清它对应判据层的哪一条。
# 不动判据层（改规则条目要重写 509 篇，代价大且会动到权威侧）。
def norm_expression(text: str) -> str:
    """归一化「同一句话」的两种转录写法，归一后才能当连接键。

    两处系统性差异（实测）：
      ① 红线条款的处理方式**带「（禁用）」前缀**：`（禁用）自动识别最佳节奏、降低奶量焦虑…`
      ② 句尾标点/空白可能不同
    不归一化的话 18 条里只能连上 8 条；归一化后连上 13 条。
    """
    s = (text or "").strip()
    s = re.sub(r"^[（(]禁用[）)]\s*", "", s)
    return s.rstrip("。；; ").strip()


def load_rule_index() -> dict:
    """判据层索引：归一化后的 `suggested_replacement` → 规则条目列表。"""
    if not os.path.isfile(SRC_RULES):
        return {}
    index: dict = {}
    for rule in l4.load_jsonl(SRC_RULES):
        key = norm_expression(rule.get("suggested_replacement"))
        if key:
            index.setdefault(key, []).append(rule)
    return index


def judgment_pointer(sheet_name: str, row: dict, header: list, index: dict) -> tuple:
    """给一条表达边界找它在判据层的对应规则，返回 (正文指引行 or None, 结果标签)。

    连接键是**建议表达**：两边的字符串本来就是同一句话的两次转录
    （实测 18 条里 13 条逐字相同，另 5 条判据层确实没有对应规则）。

    发射条件**两个都要满足**（宁缺勿错：错了会把使用者导向无关条款）：
      · 在判据层**唯一命中** —— 命中多条说明这个键不足以定身份，不发射
      · 规则的 P 级/风险等级与表里的**状态一致** —— 红色↔P0、黄色↔P1、绿色↔P2
    实测：13 条唯一命中，13 条等级全部一致，0 条歧义、0 条冲突。
    """
    if sheet_name != "02_表达边界":
        return None, "na"
    try:
        i_sug = header.index("建议表达")
        i_st = header.index("状态")
    except ValueError:
        return None, "na"
    cells = row["cells"]
    expression = cells[i_sug] if i_sug < len(cells) else ""
    status = (cells[i_st] if i_st < len(cells) else "").strip()
    key = norm_expression(expression)
    if key == "":
        return None, "empty"
    hits = index.get(key, [])
    if len(hits) == 0:
        return None, "no_rule"
    if len(hits) > 1:
        return None, "ambiguous"
    rule = hits[0]
    risk = (rule.get("risk_level") or "").strip()
    # 等级一致：表里写「红色-禁用」，规则里写「P0·红色-禁用」—— 比「颜色词」是否出现
    if status != "" and risk != "" and status.replace("-", "") not in risk.replace("-", ""):
        return None, "disagree"
    article = rule.get("article_no") or "(无条款号)"
    level = "·".join(x for x in [rule.get("p_level") or "", risk] if x)
    rule_id = rule.get("rule_id") or ""
    line = (
        f"**判据层对应规则**：{article}（{level or '等级未登记'}）"
        f" · rule_id `{rule_id}` · 在 3_措辞表达库 · 判定口径以该条为准"
    )
    return line, "ok"


def build_sheet_meta(sheet_name: str, row: dict, header: list, spec: dict,
                     today: str, valid_until: str, fingerprint: str, seq: int,
                     pointer_line: str | None = None) -> tuple[dict, str]:
    cells = row["cells"]

    def col(name: str) -> str:
        try:
            i = header.index(name)
        except ValueError:
            return ""
        return cells[i] if i < len(cells) else ""

    key_value = col(spec.get("key", "")) if spec.get("key") else ""
    ident = spec["id"] if spec["one_per"] == "sheet" else f"{spec['id']}-{safe_key(key_value)}"
    if spec["one_per"] == "row" and not key_value:
        ident = f"{spec['id']}-r{row['row']}"
    if spec["one_per"] == "row":
        # 同键可能有多行（表达边界就是一个卖点好几条），加行号保证 id 唯一
        ident = f"{ident}-r{row['row']}"

    status = col("状态")
    headline = key_value or col(header[0] if header else "") or f"第 {row['row']} 行"
    if sheet_name == "02_表达边界" and status:
        headline = f"{key_value} {status} · {col('表达类型')}"

    fields = []
    for i, name in enumerate(header):
        if not name:
            continue
        value = cells[i] if i < len(cells) else ""
        if value:
            fields.append((name, value))
    body_lines = [f"# {spec['label']}：{headline}", ""]
    for name, value in fields:
        body_lines.append(f"**{name}**：{value}")
        body_lines.append("")
    if pointer_line:
        # 判据层指引放在字段之后：它必须进**可检索正文**，
        # 这样按卖点号/表达类型查到这里时，能顺着条款号走到判据层。
        body_lines.append(pointer_line)
        body_lines.append("")
    body = "\n".join(body_lines).rstrip() + "\n"
    body, pii_hit = l4.mask_pii(body)

    tier = "L2" if spec["kind"] == "judgment" else "L1"
    not_proves = (
        "**不能替代合规判定**：这条是 W1 产品侧的口径素材，不是已过验收的合规规则。"
        "表格里的「绿色-可用」**不等于任何渠道都能发** —— 仍需遵守品牌、法务与当地合规要求。"
        "不能证明该条已过正式验收（直接取自飞书表格，未走分层晋升链）。"
        "不能外推到其他型号/品线（本表专指 W1）。"
    )
    forbidden = (
        "不许把「绿色-可用」当全渠道通行证；不许把「不能说」清单当成全部禁用项"
        "（通用禁用规则以措辞表达库的条目为准）。"
        "不许把本条当判据层的最终结论，判定的依据仍须落到措辞表达库的规则条目上。"
        "引用时必须给出本条 id 与所在工作表。"
    )
    meta: dict = {
        "id": ident,
        "title": f"产品描述库：{spec['label']} · {headline}"[:110],
        "collection": SUBDIR,
        "tier": tier,
        "topic": key_value or sheet_name,
        "kind": spec["kind"],
        "summary": f"{spec['label']}第 {row['row']} 行。" + (
            f"三态：{status}。" if status else ""
        ) + (f"{fields[0][1][:60]}。" if fields else ""),
        "owner": gen.LIBRARY_OWNER,
        "evidence_level": "L1",
        "data_level": gen.DATA_LEVEL,
        "sensitivity_level": gen.SENSITIVITY,
        "half_life_days": PRODUCT_HALF_LIFE_DAYS,
        "created_at": today,
        "valid_until": valid_until,
        "asks": [f"{spec['label']}里 {headline} 的内容是什么",
                 f"{headline} 这个卖点/术语的口径与边界是什么",
                 "这条素材来自哪张表、哪一行"],
        "not_proves": not_proves,
        "forbidden": forbidden,
        "related": [],
        "source": {
            "kind": "feishu-sheet",
            "ref": f"https://momcozy-in.feishu.cn/wiki/EsCdw2A7tiz67Rk8LgMce2TAnEh?sheet={row['sheet_id']}",
            "fingerprint": f"{fingerprint[:16]}#{sheet_name}#row={row['row']}",
            "captured_at": today,
        },
        "provenance": {
            "anchor": f"kb/.work/sources/w1-evidence.json#{sheet_name}/row={row['row']}",
            "confidence": "确定",
        },
        "pii": {"detected": pii_hit, "masked": pii_hit,
                "strategy": "按条目内出现的 @人名 做不可逆脱敏"},
        "sheet": sheet_name,
        "sheet_row": row["row"],
        "spreadsheet_revision": row.get("revision") or "",
    }
    if status:
        meta["status_tristate"] = status
    return meta, body


def build_sheet_docs(today: str, valid_until: str) -> list[dict]:
    """读表格缓存 → 条目列表。缓存不存在时返回空（不报错）。"""
    if not os.path.isfile(SRC_SHEET):
        print(f"[product] 表格缓存不存在（{SRC_SHEET}），跳过第二条源。"
              f"要抓：python3 kb/.work/fetch-w1-evidence.py")
        return []
    cache = json.load(open(SRC_SHEET, encoding="utf-8"))
    fingerprint = str(cache.get("fingerprint") or "")
    rule_index = load_rule_index()
    pointer_stats: dict = collections.Counter()
    out: list[dict] = []
    for sheet_name, spec in SHEET_SPECS.items():
        sheet = (cache.get("sheets") or {}).get(sheet_name)
        if not sheet or not sheet.get("rows"):
            continue
        rows = sheet["rows"]
        header = [c.strip() for c in rows[0]["cells"]]
        data_rows = rows[1:]
        if spec["one_per"] == "sheet":
            merged = {"row": rows[0]["row"], "cells": [], "sheet_id": sheet["sheet_id"],
                      "revision": sheet.get("revision")}
            # 整表合成一条：把所有行按「第一列：其余列」拼起来
            lines = []
            for r in data_rows:
                cells = r["cells"]
                lines.append("：".join(c for c in cells[:2] if c) + (f"（{cells[2]}）" if len(cells) > 2 and cells[2] else ""))
            merged["cells"] = ["说明全文", "\n".join(lines)]
            meta, body = build_sheet_meta(sheet_name, {**merged, "sheet_id": sheet["sheet_id"]},
                                          ["条目", "内容"], spec, today, valid_until, fingerprint, 0)
            out.append({"id": meta["id"], "meta": meta, "body": body})
            continue
        for r in data_rows:
            row = {"row": r["row"], "cells": r["cells"], "sheet_id": sheet["sheet_id"],
                   "revision": sheet.get("revision")}
            pointer_line, verdict = judgment_pointer(sheet_name, row, header, rule_index)
            if verdict != "na":
                pointer_stats[verdict] += 1
            meta, body = build_sheet_meta(sheet_name, row, header, spec, today, valid_until,
                                          fingerprint, r["row"], pointer_line)
            out.append({"id": meta["id"], "meta": meta, "body": body})
    if pointer_stats:
        ok = pointer_stats.get("ok", 0)
        total = sum(pointer_stats.values())
        print(f"[product] 判据层指引：{ok}/{total} 条接上了 3_措辞表达库的规则"
              f"（其余：{ {k: v for k, v in pointer_stats.items() if k != 'ok'} }）")
        if pointer_stats.get("ambiguous") or pointer_stats.get("disagree"):
            print("[product]   ⚠️ 有歧义或等级冲突 —— 这些条目**故意没发**指引（宁缺勿错）")
        # 防「静默退化」：有表达边界行、却一条都没接上，说明连接键失效了
        #（rules.jsonl 改了字段名、两边措辞被改写…）。这种情况不能悄悄过去 ——
        # 指引一旦消失，按卖点名查判据层的入口就又断了，而表面上一切正常。
        if ok == 0 and total > 0:
            print("[product]   ⚠️⚠️ 一条都没接上判据层 —— 连接键可能失效了"
                  "（检查 rules.jsonl 的 suggested_replacement 是否还在、写法是否变了）")
    return out


def patch_generator_name(out_root: str) -> None:
    """l4 的 patch_manifest 会把 generator 字段写成「主 + l4」，这里补上本生成器。"""
    path = os.path.join(out_root, "_meta", "manifest.json")
    if not os.path.isfile(path):
        return
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    data["generator"] = "kb/.work/gen-host-library.py + gen-host-library-l4.py + gen-host-library-product.py"
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=1)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True, help="宿主库根目录（主生成器的 --out）")
    parser.add_argument("--today", default=date.today().isoformat())
    args = parser.parse_args()

    out_root = os.path.abspath(args.out)
    if not os.path.isdir(out_root):
        print(f"[product] 错误：{out_root} 不存在，请先跑主生成器与 l4 生成器")
        return 2

    today = args.today
    valid_until = (date.fromisoformat(today) + timedelta(days=PRODUCT_HALF_LIFE_DAYS)).isoformat()

    all_units = l4.load_jsonl(SRC_UNITS)
    product = [r for r in all_units if r.get("kb_type") == "product_desc"]
    keep = [r for r in product if len((r.get("text") or "").strip()) >= MIN_CONTENT_CHARS]
    dropped = [r for r in product if r not in keep]

    l1_index = load_l1_titles()

    docs_meta: list[dict] = []
    id_seen: set[str] = set()
    for rec in keep:
        meta, body = build_product_meta(rec, today, valid_until, l1_index)
        if meta["id"] in id_seen:
            meta["id"] = f"{meta['id']}-dup"
        id_seen.add(meta["id"])
        docs_meta.append({"id": meta["id"], "meta": meta, "body": body})

    # 第二条源：飞书表格「W1卖点匹配证据库」
    sheet_docs = build_sheet_docs(today, valid_until)
    sheet_seen = collections.Counter()
    for d in sheet_docs:
        if d["id"] in id_seen or sheet_seen[d["id"]]:
            d["id"] = f"{d['id']}-b{sheet_seen[d['id']]}"
            d["meta"]["id"] = d["id"]
        sheet_seen[d["id"]] += 1
        id_seen.add(d["id"])
        docs_meta.append(d)

    l4.link_neighbors(docs_meta)

    payload: list[dict] = []
    manifest_docs: list[dict] = []
    counts: dict[str, int] = collections.Counter()
    per_collection: dict[str, int] = collections.Counter()

    for doc in docs_meta:
        meta = gen.insert_kb_class(doc["meta"], SUBDIR)
        body = doc["body"]
        tier_dir = "L2-concepts" if meta["kind"] == "judgment" else "L1-facts"
        rel = os.path.join(SUBDIR, tier_dir, f"{meta['id']}.md")
        text = gen.frontmatter(meta) + "\n" + body
        payload.append({"rel": rel, "text": text})
        counts[SUBDIR] += 1
        per_collection[f"{SUBDIR}/{tier_dir}"] += 1
        raw_bytes = text.encode("utf-8")
        manifest_docs.append({
            "id": meta["id"],
            "collectionId": SUBDIR,
            "relPath": rel,
            "absPath": os.path.join(out_root, rel),
            "record": False,
            "title": meta["title"],
            "sha256": hashlib.sha256(raw_bytes).hexdigest(),
            "text": text,
            "content": gen.render_for_chunking(meta, "\n" + body + "\n"),
            "bytes": len(raw_bytes),
            "entryId": meta["id"],
            "tier": meta["tier"],
            "kind": meta["kind"],
            "validUntil": meta["valid_until"],
            "evidenceLevel": meta["evidence_level"],
            "owner": meta["owner"],
            "metaJson": json.dumps(meta, ensure_ascii=False),
        })

    gen.flush_md(payload, out_root)
    # 下面两行日志带 `[l4]` 前缀 —— 那是复用的 l4 助手函数（登记表 / manifest 的追加逻辑），
    # 不是 l4 生成器在跑。写清楚，免得排障时被前缀误导。
    print("[product] 说明：下面两行由复用的 l4 助手函数打印（追加登记表与 manifest）")
    l4.patch_collections(out_root, [COLLECTION], counts)
    l4.patch_manifest(out_root, [COLLECTION], counts, manifest_docs, per_collection, today)
    patch_generator_name(out_root)

    print(f"[product] 源：l2/units.jsonl 里 product_desc {len(product)} 行；"
          f"其中 ≥{MIN_CONTENT_CHARS} 字的 {len(keep)} 行入条目，"
          f"短于阈值丢弃 {len(dropped)} 行（提纲/字段清单/人名）")
    for rec in dropped:
        t = (rec.get("text") or "").strip().replace("\n", " ")
        print(f"[product]   丢弃（{len(t)} 字）：{t[:46]}")
    by_dir = collections.Counter(d["rel"].split("/")[1] for d in payload)
    by_kind = collections.Counter(d["meta"]["kind"] for d in docs_meta)
    print(f"[product] 第二条源（飞书表格 W1卖点匹配证据库）：{len(sheet_docs)} 条")
    print(f"[product] 产出：{sum(counts.values())} 条 → {SUBDIR}/"
          f"（{dict(by_dir)}；kind={dict(by_kind)}）")
    print(f"[product] 输出根：{out_root}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
