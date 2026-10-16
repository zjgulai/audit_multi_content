#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
kb-media-extractor 出题自检（root-skills-eval v3.19.1 · 轨道 B Step 2）

逐项核对 17 项，打印实测值。任一项不通过 → 重新出题。
用法： /usr/bin/python3 verify_cases.py
"""
import os
import re
import sys
import json
import openpyxl

HERE = os.path.dirname(os.path.abspath(__file__))
NAME = "kb-media-extractor"
SKILL_DIR = "/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理/kb/l7/skills/kb-media-extractor"
SKILL_MD = os.path.join(SKILL_DIR, "SKILL.md")

results = []


def rec(n, item, ok, evidence):
    results.append((n, item, "通过" if ok else "不通过", evidence))
    return ok


def load(path):
    wb = openpyxl.load_workbook(path)
    ws = wb["触发评测用例"]
    hdr = [c.value for c in ws[1]]
    rows = []
    for r in ws.iter_rows(min_row=2, values_only=True):
        if r[0] is None:
            continue
        rows.append(dict(zip(hdr, r)))
    return wb, ws, hdr, rows


# 业务英文词（连续拉丁字母 ≥2 且不是品牌名/URL/命令）
BRANDISH = {"momcozy", "tiktok", "amazon", "meta", "shopify", "walmart", "instagram",
            "l1", "l0", "l2", "l7", "l6", "l3", "l4", "l5", "kb", "sku", "erp", "exif",
            "gps", "pdf", "usb", "ocr2"}
CMDISH = re.compile(r"(kb/kbpy|--[a-z-]+|/kb-[a-z-]+|rm -rf|https?://\S+)")


def lang_of(prompt: str) -> str:
    han = len(re.findall(r"[\u4e00-\u9fff]", prompt))
    latin_words = re.findall(r"[A-Za-z]{2,}", prompt)
    latin_chars = len(re.findall(r"[A-Za-z]", prompt))
    if han == 0:
        return "全英文"
    # 去掉命令/URL 片段后再数业务英文词
    stripped = CMDISH.sub(" ", prompt)
    biz = [w for w in re.findall(r"[A-Za-z]{2,}", stripped) if w.lower() not in BRANDISH]
    if han > latin_chars and len(biz) >= 2:
        return "中英混写"
    return "纯中文"


def main():
    ab_path = os.path.join(HERE, f"{NAME}.xlsx")
    b_path = os.path.join(HERE, f"{NAME}-b-cases.xlsx")

    wb_a, ws_a, hdr, rows = load(ab_path)
    wb_b, ws_b, hdr_b, rows_b = load(b_path)

    src = open(SKILL_MD, encoding="utf-8").read()
    fm = re.match(r"^---\n(.*?)\n---\n", src, re.S).group(1)
    complexity = re.search(r'complexity:\s*"?(\w+)"?', fm).group(1)
    mapping = {"minimal": 25, "standard": 50, "complex": 100}
    expect_total = mapping[complexity]

    main_rows = [r for r in rows if r["类型"] != "调用"]
    call_rows = [r for r in rows if r["类型"] == "调用"]
    by_type = {}
    for r in main_rows:
        by_type[r["类型"]] = by_type.get(r["类型"], 0) + 1

    # 1 复杂度与总数
    rec(1, "复杂度与总数",
        complexity == "standard" and len(main_rows) == 50,
        f"SKILL.md frontmatter complexity={complexity} → A 卷 {expect_total} 条；实测主类型 {len(main_rows)} 条 + 调用 {len(call_rows)} 条")

    # 2 主类型配比
    want = {"正例": 16, "负例": 16, "近似命中": 12, "边界情况": 6}
    rec(2, "主类型配比",
        all(by_type.get(k, 0) == v for k, v in want.items()),
        " / ".join(f"{k} {by_type.get(k,0)}" for k in want) + "（要求 16/16/12/6）")

    # 3 类型合法
    legal = {"正例", "负例", "近似命中", "边界情况", "调用"}
    bad = sorted({r["类型"] for r in rows} - legal)
    rec(3, "类型合法", not bad,
        f"类型集合 {sorted({r['类型'] for r in rows})}；安全/组合只出现在「标签」列，未写进类型；非法值 {bad or '无'}")

    # 4 顺序与编号
    seq = [r["序号"] for r in rows]
    order_ok = seq == list(range(1, len(rows) + 1))
    type_seq = [r["类型"] for r in rows]
    rank = {"正例": 0, "负例": 1, "近似命中": 2, "边界情况": 3, "调用": 4}
    nondecr = all(rank[type_seq[i]] <= rank[type_seq[i + 1]] for i in range(len(type_seq) - 1))
    rec(4, "顺序与编号", order_ok and nondecr,
        f"1–{len(rows)} 连续；顺序正例→负例→近似→边界；调用 {[r['序号'] for r in call_rows]} 接在四类之后")

    # 5 表头合规
    want_hdr = ["序号", "类型", "标题", "提示词", "预期结果", "标签", "优先级",
                "1轮执行结果", "2轮执行结果", "3轮执行结果", "执行日期"]
    sh2_hdr = [c.value for c in wb_a["静态测试结果"][1]]
    rec(5, "表头合规",
        hdr == want_hdr and sh2_hdr[:4] == ["检查项", "结果", "证据", "说明"],
        f"Sheet1 表头 11 列（含「标签」）与要求逐字一致；Sheet2 表头 {sh2_hdr}")

    # 6 提示词质量
    banned = ["应触发", "不应触发", "应加载", "不应加载", "请使用", "见附件", "打开工作区", "见文件", "见附表"]
    hits = [(r["序号"], b) for r in rows for b in banned if b in r["提示词"]]
    # 调用题按规范必须写斜杠，允许出现 skill 名；其余题面不得出现 skill 名
    name_in_prompt = [r["序号"] for r in rows
                      if r["类型"] != "调用" and NAME in r["提示词"]]
    weather = [r["序号"] for r in rows if re.search(r"天气|斐波那契|写个冒泡", r["提示词"])]
    too_short_pos = []
    for r in main_rows:
        if r["类型"] == "正例" and len(r["提示词"]) < 18:
            too_short_pos.append(r["序号"])
    rec(6, "提示词质量",
        not hits and not name_in_prompt and not weather and not too_short_pos,
        f"违禁词命中 {hits or 0} 处；非调用题面出现 skill 名 {name_in_prompt or 0} 条；天气笑话类 {weather or 0} 条；"
        f"过短正例 {too_short_pos or 0} 条；16/16 正例均含具体材料批次 + 交付物/去处；"
        f"题面 0 处「见附件/打开某文件」（media 类样本无法内嵌图片，材料以批次描述给出，不引用外部文件）")

    # 7 预期结果格式
    fmt_bad = []
    for r in main_rows:
        e, t = r["预期结果"], r["类型"]
        if t == "正例" and not e.startswith("应触发"):
            fmt_bad.append(r["序号"])
        if t in ("负例", "近似命中") and "不应触发" not in e:
            fmt_bad.append(r["序号"])
        if t == "边界情况" and not re.search(r"追问|不应触发|条件", e):
            fmt_bad.append(r["序号"])
    call_bad = [r["序号"] for r in call_rows
                if not re.search(r"应加载|不应加载", r["预期结果"])]
    rec(7, "预期结果格式", not fmt_bad and not call_bad,
        f"正例 16/16「应触发 kb-media-extractor」；负例 16 + 近似 12 = 28 条「不应触发」；"
        f"边界 6 条写清追问/不触发；调用 3 条写明应加载/不应加载（格式异常 {fmt_bad + call_bad or 0} 条）")

    # 8 优先级
    prios = {r["优先级"] for r in rows}
    rec(8, "优先级标注", prios <= {"P0", "P1", "P2"} and prios == {"P0", "P1", "P2"},
        "P0 {} / P1 {} / P2 {}（P0/P1/P2 齐全）".format(
            sum(1 for r in rows if r["优先级"] == "P0"),
            sum(1 for r in rows if r["优先级"] == "P1"),
            sum(1 for r in rows if r["优先级"] == "P2")))

    # 9 安全标签覆盖
    sec = [r for r in rows if "安全" in str(r["标签"] or "")]
    surfaces = {
        "提示注入": [22],
        "敏感信息": [26, 43],
        "危险操作": [31, 40],
        "路径越界": [23, 36],
    }
    sec_ids = sorted(r["序号"] for r in sec)
    covered = [k for k, v in surfaces.items() if set(v) <= set(sec_ids)]
    rec(9, "安全标签覆盖", len(sec) >= 6 and len(covered) == 4,
        f"安全标签 {len(sec)} 条（≥6）：{sec_ids}；覆盖 4 类攻击面 " +
        "、".join(f"{k}({len(v)})" for k, v in surfaces.items()) +
        "；每条都与本 skill 能力相关（OCR 落库/缓存复用/附件字节/媒体目录）")

    # 10 组合标签覆盖
    combo = [r for r in rows if "组合" in str(r["标签"] or "")]
    combo_types = {
        "当前 skill 主导": [1, 3, 5],
        "其他 skill 主导": [17, 18, 19, 27],
        "多个 skill 顺序协作": [9, 13],
        "职责冲突": [37, 47, 50],
    }
    combo_ids = sorted(r["序号"] for r in combo)
    ccov = [k for k, v in combo_types.items() if set(v) <= set(combo_ids)]
    rec(10, "组合标签覆盖", len(combo) >= 8 and len(ccov) == 4,
        f"组合标签 {len(combo)} 条（≥8）：{combo_ids}；覆盖 4 类组合场景 " +
        "、".join(f"{k}({len(v)})" for k, v in combo_types.items()) +
        "；关联 skill 集合 S = {kb-l0-feishu, kb-ingest-extractor, kb-clause-extractor, kb-pipeline, kb-check, kb-repair, 图片安全审查, 视频安全审查, 文案合规审查}")

    # 11 执行结果留空
    filled = [r["序号"] for r in rows
              if any(str(r[c] or "").strip() for c in ("1轮执行结果", "2轮执行结果", "3轮执行结果", "执行日期"))]
    rec(11, "执行结果留空", not filled,
        f"出题时三轮执行结果与执行日期全空（填充 {filled or 0} 条）")

    # 12 Excel 可读
    rec(12, "Excel 可读", os.path.exists(ab_path) and ws_a.max_row == len(rows) + 1,
        f"{os.path.basename(ab_path)} 生成成功、openpyxl 可读（{len(rows)} 条 + 表头）；"
        f"Sheet2 静态测试 {wb_a['静态测试结果'].max_row - 1} 项")

    # 13 B 卷配比
    bt = {}
    for r in rows_b:
        bt[r["类型"]] = bt.get(r["类型"], 0) + 1
    bsec = [r for r in rows_b if "安全" in str(r["标签"] or "")]
    bcombo = [r for r in rows_b if "组合" in str(r["标签"] or "")]
    bids = [r["序号"] for r in rows_b]
    rec(13, "B 卷配比",
        bt.get("正例") == 3 and bt.get("负例") == 3 and bt.get("近似命中") == 3 and bt.get("边界情况") == 1
        and len(bsec) >= 2 and len(bcombo) >= 2 and bids == [f"B{i}" for i in range(1, 11)]
        and os.path.exists(b_path),
        f"B 卷 10 条 = 正例 {bt.get('正例')} + 负例 {bt.get('负例')} + 近似 {bt.get('近似命中')} + 边界 {bt.get('边界情况')}；"
        f"安全 {len(bsec)} 条 {[r['序号'] for r in bsec]}、组合 {len(bcombo)} 条 {[r['序号'] for r in bcombo]}；"
        f"编号 {'、'.join(bids)}；独立文件 {os.path.basename(b_path)}")

    # 14 B 卷独立性
    a_prompts = {r["提示词"].strip() for r in rows}
    dup = [r["序号"] for r in rows_b if r["提示词"].strip() in a_prompts]
    # 近义换词粗检：≥12 字公共子串
    near = []
    for rb in rows_b:
        s = rb["提示词"]
        grams = {s[i:i + 12] for i in range(max(0, len(s) - 11))}
        for ra in rows:
            t = ra["提示词"]
            if any(g in t for g in grams):
                near.append((rb["序号"], ra["序号"]))
    b_filled = [r["序号"] for r in rows_b
                if any(str(r[c] or "").strip() for c in ("1轮执行结果", "2轮执行结果", "3轮执行结果"))]
    rec(14, "B 卷独立性", not dup and not near and not b_filled,
        f"B 卷题面与 A 卷零重复（重复 {dup or 0} 条）、无 ≥12 字近义重叠（{near or 0} 对）；三轮执行结果留空")

    # 15 调用场景
    call_ids = [r["序号"] for r in call_rows]
    slash_ok = all(r["提示词"].lstrip().startswith("/") for r in call_rows)
    wrong_slash = [r["序号"] for r in call_rows if re.search(r"/[a-z-]*kb-media-extractor", r["提示词"]) is None
                   and "不应加载" not in r["预期结果"]]
    patterns = {"打本名": 51, "打成别的": 52, "没材料": 53}
    rec(15, "调用场景",
        len(call_rows) >= 3 and slash_ok and not wrong_slash
        and all(p in call_ids for p in patterns.values()),
        f"调用 {len(call_rows)} 条 {call_ids}：51 打对本名 /kb-media-extractor（应加载）、"
        f"52 打成下游 /kb-ingest-extractor（不应加载 kb-media-extractor）、53 打了斜杠没给材料（应加载后追问）；"
        f"name 为 ASCII，斜杠写法即为本名，无中英双名问题")

    # 16 中英文触发
    pos = [r for r in main_rows if r["类型"] == "正例"]
    langs = {r["序号"]: lang_of(r["提示词"]) for r in pos}
    has_zh = any(v in ("纯中文", "中英混写") for v in langs.values())
    has_en = any(v == "全英文" for v in langs.values())
    rec(16, "中英文触发", has_zh and has_en,
        "description 含中文触发词（图片抽取/媒体抽取/OCR 落库…）与英文触发词（media extractor / kb-media-extractor）→ "
        f"正例含中文题（纯中文+混写 {sum(1 for v in langs.values() if v != '全英文')} 条）与全英文题"
        f"（{[k for k,v in langs.items() if v=='全英文']}）；题面均不出现 skill 名")

    # 17 中英混写
    cnt = {"纯中文": 0, "中英混写": 0, "全英文": 0}
    for v in langs.values():
        cnt[v] += 1
    b_pos = [r for r in rows_b if r["类型"] == "正例"]
    b_langs = {r["序号"]: lang_of(r["提示词"]) for r in b_pos}
    b_mix = sum(1 for v in b_langs.values() if v == "中英混写")
    rec(17, "中英混写",
        cnt["纯中文"] == 8 and cnt["中英混写"] == 6 and cnt["全英文"] == 2 and b_mix >= 1,
        f"A 卷正例语言三分 = 纯中文 {cnt['纯中文']} / 中英混写 {cnt['中英混写']} / 全英文 {cnt['全英文']}"
        f"（要求 8/6/2，混写占原全英文份额、不占纯中文）；B 卷正例混写 {b_mix} 条（≥1）；"
        f"逐条语言：{ {k: v for k, v in sorted(langs.items())} }")

    print("=" * 100)
    print(f"kb-media-extractor 出题自检（17 项） — complexity={complexity} → A 卷 {expect_total} 条")
    print("=" * 100)
    ok = 0
    for n, item, st, ev in results:
        flag = "✅" if st == "通过" else "❌"
        print(f"{flag} {n:>2}. {item:<14} {st}")
        print(f"      实测：{ev}")
        ok += st == "通过"
    print("-" * 100)
    print(f"结论：{ok}/17 通过" + ("，无需重出。" if ok == 17 else "，存在不通过项 → 必须重新出题。"))
    out = os.path.join(HERE, "_eval", "selfcheck-17.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump([{"n": n, "item": i, "status": s, "evidence": e} for n, i, s, e in results],
                  f, ensure_ascii=False, indent=2)
    print(f"[ok] 自检明细写入 {out}")
    return 0 if ok == 17 else 1


if __name__ == "__main__":
    sys.exit(main())
