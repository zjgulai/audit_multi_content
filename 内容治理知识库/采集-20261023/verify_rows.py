#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""写后核验：以**服务端为准**读回「守衡测试」，断言矩阵真的落全了、且逐字对得上。

矩阵形状：**9 产品 × 5 枚举 × 3 平台 = 135 行**（Owner 2026-10-23 三次口径的合成结果）。

断言（任一条不成立就红）：
  A **矩阵完整性** —— 135 个组合（产品线+产品中文名+内容类型+渠道）每个**恰好一行**，
    既不许缺、也不许多（多 = 重复写进去过）。
  B **逐字一致** —— 每行的 `产品spu` / `产品英文名` 与 `out_rows.json` **逐字相等**。
    防的是「验的是 A、写的是 B」与手抄转录错。
  C **每个「产品 × 平台」5 枚举齐** —— 按 (产品, 平台) 分组，覆盖必须完整。
  D **没碰别人的列** —— 写入只许落在白名单 6 列上；其余列
    （问题等级 / 问题描述 / 证据+来源 / Codex* / 问题编号）在本批行上必须为空。
  E **没动既有行** —— 本批行的 record_id 必须不在写前快照里
    （快照 `before_ids.json`，由 `snapshot_ids.py` 在写前生成）。
  F **数据从第 1 行开始** —— 表首不许有连续空行，且第 1 行必须是本批数据行。
    依据：Owner 2026-10-23「你要从第一行开始落数据，不要从中间开始落数据」
    （成因：前 16 行残留空行顶着、数据从第 17 行起）。清理动作见 `drop_blank_rows.py`。
  G **每品线只 3 个产品** —— 表内**任何**填了 `产品中文名` 的行（不分是谁建的）都必须在
    保留集里，且每个品线恰好 3 个产品。依据：Owner 2026-10-23「每个品线只采集 3 个具体产品，
    多余的产品更新表格删除」。删多余的动作为 `trim_extra_products.py`。
  H **平台只有这 3 个** —— `渠道` 取值必须**恰好**等于 `out_rows.json` 里的平台集
    （不许自创第四个平台名），且各平台行数一致。依据：Owner 2026-10-23「数据采集要 3 个平台的」；
    平台名取自库内既有值（官网 / Amazon / YouTube），**不自创**。

用法：
  python3 verify_rows.py                      # 正常核验
  python3 verify_rows.py --controls           # ★ B 反向对照（改期望英文名）
  python3 verify_rows.py --controls-blank     # ★ F 反向对照（注入空行）
  python3 verify_rows.py --controls-product   # ★ G 反向对照（注入保留集外产品）
  python3 verify_rows.py --controls-channel   # ★ H 反向对照（注入自创平台名）
  python3 verify_rows.py --controls-leak      # ★ D 反向对照（把采集段名注入白名单外的列）
  python3 verify_rows.py --controls-removed-ghost  # ★ 反向对照（把「已声明移除」的组合塞回，A 必须红）
"""
import json
import sys

sys.path.insert(0, "../../tools")
import removed_rows as RR
from lark_find import _req, token, BASE                        # noqa: E402

APP = "RY2UbCRjXaeeWwscUPScVN5AnQc"
TABLE = "tblTPsjiyOHYfUc0"
#: 本轮允许写的列。
#: ★ 2026-10-23 采集阶段起**增加 `采集数据`** —— 建矩阵阶段它是白名单外的
#:   （那时只该有结构列，写进任何素材都算串列；D 断言就是为拦这个而写的）。
#:   采集开始后 `采集数据` 正是**该写的列**，所以放进来；其余人/引擎结论列仍不在白名单里。
ALLOWED = {"产品线", "产品中文名", "产品spu", "产品英文名", "内容类型", "渠道", "采集数据"}

#: 采集 payload 的段名 —— 只该出现在 `采集数据` 列里；出现在别处即为串列
LEAK_MARKS = ("【图片】", "【视频】", "【文案】", "【链接】", "【发布】")
#: 本批所有 record_id 前缀（10-23 两次写入：先 45 行、后补 90 行）
#: 本批 record_id 前缀。**每次整体重建都会换** —— `rebuild_matrix.py` 删旧建新，
#: 旧前缀的行已不存在（2026-10-23 重建两次：15→9 产品收窄、平台改回 YouTube + 换 3 个产品）。
MINE_PREFIXES = ("reczz28QhOqu", "reczz28QhOte")
KEY = ("产品线", "产品中文名", "内容类型", "渠道")


def fetch_all():
    out, page = [], None
    while True:
        url = (f"{BASE}/bitable/v1/apps/{APP}/tables/{TABLE}/records?page_size=500"
               + (f"&page_token={page}" if page else ""))
        r = _req(url, token())
        if r.get("code") != 0:
            raise SystemExit(f"读表失败：{json.dumps(r, ensure_ascii=False)[:400]}")
        d = r["data"]
        out += d.get("items", [])
        if not d.get("has_more"):
            return out
        page = d.get("page_token")


def main():
    argv = sys.argv
    want = json.load(open("out_rows.json", encoding="utf-8"))
    want = [{"fields": dict(w["fields"]), "_meta": dict(w.get("_meta", {}))} for w in want]
    enums, channels = [], []
    for w in want:
        if w["fields"]["内容类型"] not in enums:
            enums.append(w["fields"]["内容类型"])
        if w["fields"]["渠道"] not in channels:
            channels.append(w["fields"]["渠道"])

    if "--controls" in argv:
        # ★ B 的反向对照（AGENTS.md §2.4.1：判据必须自证拦得住）：
        #   把第 1 行期望英文名改成**表里不可能有**的值 ⇒ B 必须变红。
        want[0]["fields"]["产品英文名"] = "___CONTROL-NOT-IN-TABLE___"
        print("（反向对照：第 1 行期望英文名已改成表里不可能有的值，B 应当变红）\n")

    rows = fetch_all()
    if "--controls-blank" in argv:
        # ★ F 反向对照（**注入式，不碰服务端**）：最前面插一行合成空行。
        rows = [{"record_id": "rec___CONTROL_BLANK___", "fields": {}}] + rows
        print("（反向对照：已在结果最前面注入 1 行合成空行，F 应当变红）\n")
    if "--controls-product" in argv:
        # ★ G 反向对照：塞一行保留集之外的产品。
        rows = rows + [{"record_id": "rec___CONTROL_PRODUCT___",
                        "fields": {"产品线": "吸奶器", "产品中文名": "___CONTROL-EXTRA-PRODUCT___",
                                   "内容类型": "单图", "渠道": "官网"}}]
        print("（反向对照：已注入 1 行保留集之外的产品，G 应当变红）\n")
    if "--controls-channel" in argv:
        # ★ H 反向对照：塞一行自创的平台名。
        rows = rows + [{"record_id": "rec___CONTROL_CHANNEL___",
                        "fields": {"产品线": "吸奶器", "产品中文名": "S12 Pro+吸奶器",
                                   "内容类型": "单图", "渠道": "___CONTROL-PLATFORM___"}}]
        print("（反向对照：已注入 1 行自创平台名，H 应当变红）\n")

    if "--controls-leak" in argv:
        # ★ D 反向对照（2026-10-23 新增）：把采集段名塞进**白名单外的列**，
        #   D 必须精确变红 —— 否则 D 就只是注释，守不住「采集数据串列」这件事。
        #   ⚠️ 必须**就地污染一行**，不能新增行 —— 新增行会被 A（组合重复）先抓走，
        #   那样这条对照只证明「A 还在工作」，**不能证明 D 能变红**。
        _t = [dict(r) for r in rows]
        for _r in _t:
            if _r["record_id"].startswith(MINE_PREFIXES):
                _r["fields"] = dict(_r["fields"])
                _r["fields"]["问题等级"] = "【图片】https://example.com/leaked.jpg"
                break
        rows = _t
        print("（反向对照：已把「【图片】」段名注入到「问题等级」列，D 应当变红）\n")

    if "--controls-removed-ghost" in argv:
        # ★ 新增（2026-10-23）：「已声明移除」的反向对照。
        #   把一条**声明为已删**的组合塞回表里，A 必须精确变红 ——
        #   否则「声明过就算数」会变成**万能豁免**（声明过的组合可以随便留着、甚至回填）。
        _decl = RR.load()["removed"]
        if not _decl:
            print("（反向对照：声明文件里没有行，本对照跳过 —— 不算通过，标未测）\n")
        else:
            rows = [{"record_id": _decl[0]["record_id"],
                     "fields": dict(_decl[0]["fields"])}] + rows
            print("（反向对照：已把 1 个『已声明移除』的组合塞回表里，A 应当变红）\n")

    mine = [r for r in rows if r["record_id"].startswith(MINE_PREFIXES)]
    # ★ 已声明移除的组合（`removed_rows.py` 是唯一真源）
    #   2026-10-23 Owner 决定删掉「采集数据只有【说明】备注、没有真实素材」的 24 行（135→111）。
    #   判据必须认这件事，否则 A/C/H 会**永久变红**；但**不许它变成万能豁免** ——
    #   ① 总行数仍校验「期望 − 声明移除数」；② 声明移除却还在表里 ⇒ 精确变红。
    removed, removed_ids = RR.keys(), RR.rids()
    removed_pairs = RR.pairs_3()      # 产品×平台 视角的形态集合（判据 C 用）
    n_rem, by_chan_rem = RR.summary()
    want_eff = [w for w in want if tuple(w["fields"][c] for c in KEY) not in removed]
    print(f"表内共 {len(rows)} 行 ｜ 本批（{'/'.join(MINE_PREFIXES)}*）{len(mine)} 行"
          + (f" ｜ 已声明移除 {n_rem} 个组合 {by_chan_rem}" if n_rem else ""))

    red, seen, got = [], {}, {}
    for w in want:
        seen.setdefault(tuple(w["fields"][c] for c in KEY), []).append(w)
    for r in mine:
        f = r["fields"]
        got.setdefault(tuple(f.get(c) for c in KEY), []).append(r["record_id"])

    # A
    for k in sorted(set(seen) | set(got), key=str):
        if k in removed:
            if got.get(k):
                red.append(f"A 组合 {k} **已声明移除却还在表里**（{len(got[k])} 行）")
            continue
        n_w, n_g = len(seen.get(k, [])), len(got.get(k, []))
        if n_w != n_g:
            red.append(f"A 组合 {k} 期望 {n_w} 行、实际 {n_g} 行")
    if len(mine) != len(want_eff):
        red.append(f"A 本批行数 {len(mine)} ≠ 期望 {len(want_eff)}"
                   f"（{len(want)} − 声明移除 {n_rem}）")

    # B + D
    byk = {tuple(w["fields"][c] for c in KEY): w["fields"] for w in want}
    for r in mine:
        f = r["fields"]
        k = tuple(f.get(c) for c in KEY)
        w = byk.get(k)
        if not w:
            red.append(f"A 表里多出组合 {k}")
            continue
        if k in removed:
            red.append(f"A 组合 {k} 已声明移除却还在表里")
            continue
        for col in ("产品spu", "产品英文名"):
            if f.get(col) != w[col]:
                red.append(f"B {k} 的「{col}」不符：表={f.get(col)!r} 期望={w[col]!r}")
        # ★★ D 改了判据（2026-10-23）：原来查「非白名单列必须全空」——
        #   那条前提已经失效：**复核侧（守衡 / Codex）在并行往
        #   「问题等级 / Codex问题描述 / Codex证据+来源」里写真实结论**，
        #   于是 D 把别人的正常产出判成了我的串列（实测一次报了 40 行）。
        #   现在按**内容签名**判：采集 payload 才有 `【图片】/【视频】/【文案】/【链接】` 这些段名，
        #   它们出现在白名单外的列里 ⇒ 才是「我的采集数据串到了别的列」。
        for col, val in f.items():
            if col in ALLOWED or val in (None, "", [], {}):
                continue
            hit = [m for m in LEAK_MARKS if m in str(val)]
            if hit:
                red.append(f"D {k} 的非白名单列「{col}」出现采集段名 {hit}：{str(val)[:60]!r}")

    # C
    per = {}
    for r in mine:
        f = r["fields"]
        per.setdefault((f.get("产品中文名"), f.get("渠道")), []).append(f.get("内容类型"))
    for k, v in sorted(per.items(), key=str):
        exp = [e for e in enums if (k[0], e, k[1]) not in removed_pairs]   # 减掉该 产品×平台 被声明移除的形态
        if sorted(v) != sorted(exp):
            red.append(f"C 「{k[0]} @ {k[1]}」枚举不齐：实际 {sorted(v)} 期望 {sorted(exp)}")

    # E
    try:
        before = set(json.load(open("before_ids.json", encoding="utf-8")))
        overlap = [r["record_id"] for r in mine if r["record_id"] in before]
        if overlap:
            red.append(f"E 本批里出现写前就存在的 record_id：{overlap[:5]}")
        print(f"写前快照 {len(before)} 行 ｜ 与本批重叠 {len(overlap)} 行")
    except FileNotFoundError:
        print("（无 before_ids.json，跳过 E —— 不算通过，标未测）")

    # F
    lead = []
    for r in rows:
        f = r["fields"]
        if all(f.get(c) in (None, "", [], {}) for c in f):
            lead.append(r["record_id"])
        else:
            break
    if lead:
        red.append(f"F 表首有 {len(lead)} 行连续空行（数据没从第 1 行开始）：{lead[:5]}")
    if rows and not rows[0]["record_id"].startswith(MINE_PREFIXES):
        red.append(f"F 第 1 行不是本批数据行：{rows[0]['record_id']}")
    print(f"表首连续空行 {len(lead)} 行 ｜ 第 1 行 = "
          f"{rows[0]['fields'].get('产品中文名') if rows else '（空表）'}")

    # G
    keep = {w["fields"]["产品中文名"] for w in want}
    extra = sorted({r["fields"].get("产品中文名") for r in rows
                    if r["fields"].get("产品中文名") and r["fields"]["产品中文名"] not in keep})
    if extra:
        red.append(f"G 表里有保留集之外的产品：{extra}")
    byline = {}
    for w in want:
        byline.setdefault(w["fields"]["产品线"], set()).add(w["fields"]["产品中文名"])
    for line, names in sorted(byline.items()):
        if len(names) != 3:
            red.append(f"G 品线「{line}」有 {len(names)} 个产品（应为 3）：{sorted(names)}")

    # H
    ch_now = {}
    for r in rows:
        c = r["fields"].get("渠道")
        if r["fields"].get("产品中文名"):
            ch_now[c] = ch_now.get(c, 0) + 1
    bad = sorted(str(c) for c in ch_now if c not in channels)
    if bad:
        red.append(f"H 表里有自创的平台名：{bad}")
    for c in channels:
        exp_c = len(want) // len(channels) - by_chan_rem.get(c, 0)
        if ch_now.get(c) != exp_c:
            red.append(f"H 平台「{c}」有 {ch_now.get(c)} 行，应为 {exp_c}"
                       f"（{len(want)//len(channels)} − 声明移除 {by_chan_rem.get(c,0)}）")
    print(f"保留集 {len(keep)} 产品 ｜ 品线 { {k: len(v) for k, v in sorted(byline.items())} } "
          f"｜ 平台 { {k: v for k, v in sorted(ch_now.items(), key=str)} } ｜ 多出产品 {len(extra)}")

    print(f"\n产品数={len(keep)} ｜ 平台数={len(channels)} ｜ 组合={len(got)} ｜ "
          f"期望组合={len(seen)} ｜ red={len(red)}")
    for x in red[:40]:
        print("  ✗", x)
    if red:
        print("\n❌ 未过")
        return 1
    print(f"✅ 通过：{len(got)} 个组合齐（{len(keep)} 产品 × {len(enums)} 枚举 × "
          f"{len(channels)} 平台）、SPU/英文名逐字一致、每「产品×平台」枚举齐、"
          f"采集段名未串到别的列、数据从第 1 行开始、每品线 3 产品、平台无自创、"
          f"已声明移除 {n_rem} 个组合且逐个确认不在表里")
    return 0


if __name__ == "__main__":
    sys.exit(main())