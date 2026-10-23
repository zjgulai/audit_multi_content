#!/usr/bin/env python3
"""P0 匹配器：对给定文本跑 P0 规则，输出命中结果。

用法：
    python3 kb/l5/matcher.py --text "some ad copy"
    python3 kb/l5/matcher.py --file path.txt
    python3 kb/l5/matcher.py --file path.txt --json
    python3 kb/l5/matcher.py --selftest

约定：
- 匹配前统一做 NFKC 归一 + 空白折叠 + casefold，抵消全角/大小写/多空格差异
- 按行匹配（换行不被折叠掉），元语境豁免（行首「禁用表达：/依据：」等）依赖行首锚点 ^ 才生效
- 先跑白名单（否定句 / 引用 / 禁用词清单 / 说明性语境），命中白名单的位置不再判 BLOCK
- keyword 用「带词边界的字面匹配」，避免 more milk 命中 more milky 之类的误报
  中日韩字符没有词边界，故对含 CJK 的 pattern 退化为子串匹配
- 退出码：0 = 无 P0 命中；1 = 有 P0 命中（便于脚本串联）
"""
import argparse, json, os, re, sys, time, unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
PATTERNS = os.path.join(HERE, "p0_patterns.jsonl")


def norm(s):
    s = unicodedata.normalize("NFKC", s or "")
    s = re.sub(r'\s+', ' ', s)
    return s.casefold()


CJK = re.compile(r'[\u3000-\u9fff\uff00-\uffef]')


def norm_rx(s):
    """正则源码的归一化：**只** NFKC + 空白折叠，**不 casefold**。

    ★ 2026-10-21 实测：原先正则源码也走 `norm()`（含 casefold），于是 `\B` → `\b`、
      `\S` → `\s`、`\W` → `\w`、`\D` → `\d` —— 转义被悄悄改了意思，那条正则**永远不命中**、
      也不报错。大小写本来就由 `re.IGNORECASE` 承担，源码不需要 casefold。
    """
    s = unicodedata.normalize("NFKC", s or "")
    return re.sub(r'\s+', ' ', s)


def compile_patterns(path=PATTERNS):
    rules = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                rules.append(json.loads(line))
    for r in rules:
        # ★ 2026-10-21：规则名/边界表述（`whitelist_exempt_terms`）—— **逐字出现即命中，白名单一律不豁免**。
        #   病灶（实测）：H03 的边界表述「未经备案的临床/科学背书」整句落在本规则否定白名单
        #   `(…|未经|…)[^。]{0,20}(…|临床|…)` 的跨度里（「未经」+「备案的」+「临床」）⇒
        #   只把词加进 `patterns` 仍 **0 命中**（加词等于白加）。它是**规则名**，不是被否定的宣称。
        #   代价（明写）：`禁用表达：<规则名>` 这类清单行也会 BLOCK —— 与 SELFTEST 里
        #   「取不豁免一侧（漏放是真红线）」同口径。
        r["_wl_exempt"] = {norm(t) for t in (r.get("whitelist_exempt_terms") or []) if norm(t)}
        kws = []
        for kw in r["patterns"]:
            k = norm(kw)
            if not k:
                continue
            _ex = k in r["_wl_exempt"]
            if CJK.search(k):
                kws.append((kw, re.compile(re.escape(k)), _ex))
            else:
                kws.append((kw, re.compile(r'(?<![A-Za-z0-9])' + re.escape(k) + r'(?![A-Za-z0-9])'), _ex))
        r["_kw"] = kws
        # ★ 2026-10-21（实测踩到）：`norm()` 会 **casefold**，而 casefold 会把**正则的大写转义
        #   一起小写** —— `\B` → `\b`、`\S` → `\s`、`\W` → `\w`、`\D` → `\d`。
        #   表现：一条 `(?<!\B#\s*1)` 之类的正则**永远不命中**（而且不报错）。
        #   正则源码只做 NFKC + 空白折叠（与待匹配文本同一套归一），大小写交给 IGNORECASE。
        #   预筛 `_pre` 用的也是这一份归一化后的源码（否则又会出现「超集不是超集」）。
        r["_rx"] = [(norm_rx(p), re.compile(norm_rx(p), re.IGNORECASE)) for p in r.get("regex_patterns") or []]
        r["_wl"] = [(norm_rx(p), re.compile(norm_rx(p), re.IGNORECASE)) for p in r.get("whitelist") or []]
        # 预筛：把该规则全部 keyword/regex 拼成一条 alternation。
        # 这是「超集」——keyword 项不带词边界，只会多匹配不会漏匹配 —— 因此预筛不过的行
        # 一定没有命中，可以整行跳过，省掉每条 pattern 各扫一遍的开销（1MB 语料上是主要成本）。
        # ★ 2026-10-21（补 H06 边界表述时实测到的**假阴性**）：这里原先是 `re.escape(k)`，
        #   而 `k` 是**原词**（未归一化）——待匹配文本却做过 NFKC/空白折叠。
        #   ⇒ 凡是词里带全角括号/全角逗号的，预筛 `search()` 恒不成立 ⇒ **整条规则在该行被跳过**。
        #   实测：H06 的边界表述 `kw at 0` 命中，而同句 `_pre.search(...) == False`。
        #   预筛的语义是「超集」，用未归一化的词连超集都不是。改成与 `_kw` 编译同一口径。
        parts = [re.escape(norm(k)) for k, _rx, _ex in r["_kw"]] + [p for p, _ in r["_rx"]]
        r["_pre"] = re.compile("|".join(parts), re.IGNORECASE) if parts else None
        r["_wl_key"] = tuple(r["whitelist"])
    return rules


def whitelist_spans(text_n, rule):
    spans = []
    for _, rx in rule["_wl"]:
        for m in rx.finditer(text_n):
            spans.append((m.start(), m.end()))
    return spans


def inside(pos, spans):
    return any(a <= pos < b for a, b in spans)


def _line_hits(t, rules, line_no, cache):
    """在「单行归一化文本」上跑全部规则，返回 (rule, 命中项) 列表。

    按行跑而不是整篇跑，是因为白名单里的「禁用表达：/依据：」这类元语境豁免依赖行首锚点 ^；
    整篇折叠空白会把换行压成空格，^ 就只剩全文开头一个位置，豁免会失效。
    """
    out, sup = [], {}
    for r in rules:
        pre = r["_pre"]
        if pre is None or pre.search(t) is None:
            continue
        # 6 条 P0 规则共用同一份白名单，同一行内按白名单内容缓存，避免重复扫描
        key = (line_no, r["_wl_key"])
        spans = cache.get(key)
        if spans is None:
            spans = whitelist_spans(t, r)
            cache[key] = spans
        sup[r["pattern_id"]] = len(spans)
        for kind, pairs in (("keyword", r["_kw"]), ("regex", r["_rx"])):
            for item in pairs:
                label, rx = item[0], item[1]
                # `whitelist_exempt_terms`（规则名/边界表述）：forced=True ⇒ 白名单不参与判定
                forced = bool(item[2]) if kind == "keyword" else False
                for m in rx.finditer(t):
                    if forced or not inside(m.start(), spans):
                        out.append((r, {
                            "kind": kind, "pattern": label,
                            # ★ 2026-10-21：**真正被命中的那段文本**。正则命中时 `pattern` 是
                            #   正则源码（`\b\d+...`），拿它当「逐字摘录」是错的 —— 报告里
                            #   会印一整条正则，且引用契约要求的「逐字」根本不成立。
                            #   下游取摘录一律 `text or pattern`。
                            "text": m.group(0),
                            "line": line_no,
                            "span": [m.start(), m.end()],
                            "line_text": t[:300],
                        }))
    return out, sup


def match(text, rules=None):
    """返回命中列表；每处命中的 span 是「该行归一化后」的行内偏移，line 是 1 起算的行号。"""
    rules = rules if rules is not None else compile_patterns()
    agg, suppressed, cache = {}, {}, {}
    for i, raw in enumerate((text or "").split("\n"), start=1):
        t = norm(raw)
        if not t:
            continue
        line_out, line_sup = _line_hits(t, rules, i, cache)
        for pid, n in line_sup.items():
            suppressed[pid] = suppressed.get(pid, 0) + n
        for r, m in line_out:
            agg.setdefault(r["pattern_id"], {"rule": r, "matched": []})["matched"].append(m)
    hits = []
    for r in rules:
        a = agg.get(r["pattern_id"])
        if not a:
            continue
        hits.append({
            "pattern_id": r["pattern_id"], "rule_id": r["rule_id"],
            "rule_code": r.get("rule_code"), "level": r["p_level"],
            "match_note": r["match_note"],
            "matched": a["matched"][:20],
            "matched_count": len(a["matched"]),
            "lines": sorted({m["line"] for m in a["matched"]}),
            "anchor": r["anchor"], "source_sha256": r["source_sha256"],
            "suggested_replacement": r["suggested_replacement"],
            "whitelist_suppressed": suppressed.get(r["pattern_id"], 0),
        })
    return hits


SELFTEST = [
    ("positives", [
        "Experience pain-free pumping with our hospital grade pump.",
        "This pump helps you get more milk in less time.",
        # ★ 2026-10-12 补（H02 物主代词缺口）：同一句话**换个人称**就不拦了 —— 改前实测 MISS。
        #   回归集里就有第 2 条（RC-b2390ccfe4f8 逐字）。它同时钉住物主代词族，
        #   只补 `her` 一个会在这里变红。
        "She said the warm massage has been so relaxing and it actually increased her milk supply.",
        "It increased my milk supply within a week.",
        "Recommended by 100+ experts and trusted worldwide.",
        "The safest, most perfect pump — 100% safe.",
        "Designed to mimic baby's natural nursing rhythm.",
        # ★ 2026-10-12 补（H09 英文变形）：素材里真实出现过的写法，改前**实测 MISS**
        #   （回归集 solid 层 RC-11b8f1e6a2c7 逐字含这一句 ⇒ 整段 P0 快路 hit=False ⇒ 漏放）。
        #   它同时钉住「`suckling` ↔ `sucking`」这一对变形 —— 只补一半会在这里变红。
        "Designed to follow a baby-like natural sucking rhythm.",
        "Follows a baby-like sucking motion.",
        "Say goodbye to painful pumping forever.",
        # ★ 2026-10-21（Owner 验收：把「未经备案的临床/科学背书」送审，守衡回了 PASS）：
        #   H03 的**边界表述**逐字送审必须命中。改前实测 MISS；补词后**仍 MISS**（被否定白名单吞），
        #   故与 `whitelist_exempt_terms` 一并钉在这里 —— 少一半这条就变红。
        "未经备案的临床/科学背书",
        # ★ 2026-10-21（Owner：「这是未标注来源的效果数据声明吗？」→「补」）：
        #   效果百分比的**形态**（不是字面词）—— 改前实测 MISS（词表只有 28% faster / trusted by 6 million）。
        "95% of users saw results in 2 weeks",
        # ★ 2026-10-21（Owner：「这条『无依据的销量/排名宣称』预期命中 P0，却没有」）：
        #   销量/排名宣称的**形态**（V03）—— 改前实测 MISS（V03 只有 4 个字面词）。
        "吸奶器m5.pro 是全美国销量no.1 的吸奶器，销量1万台",
        "98% 的用户反馈有效",   # 中文同族：百分比 + 人群

        # ★★ 2026-10-21（Owner 裁定 A 的**正向对照**）：放开的是**排名/最高级一族**，
        #   不是「整族绝对化用语」。这三条钉住「没被一起放开」那一侧 ——
        #   把 `100%` / `最安全` / `纯天然` 误伤成 PASS，这条立刻变红。
        "100% safe and 完全安全。",
        "成分 100% 天然。",        # ★ 2026-10-22：裸 100% 出列后，带限定词的这一侧必须仍 P0（H05）
        "这款是最安全的吸奶器。",
        "成分纯天然。",

        # ★ 2026-10-21（同上，Owner 选定「一并补」）：H06 的边界表述。
        #   它同时钉住**预筛归一化**那条 bug —— 句里有全角括号，`_pre` 不归一化就整行跳过。
        "FDA 表述错误（吸奶器为 cleared/registered，非 approved/certified）",
        # 同批：H08 / H09 的边界表述
        "无数据支撑的违法对比 / 贬低竞品",
        "智能闭环/仿生虚假宣称（自动识别节奏、模拟/复制宝宝、饱腹反馈、降低奶量焦虑）；"
        "W1当前为用户主动调节+保存程序，非闭环生理识别",
        "采用无痛设计，缓解疼痛，帮助催奶增产。",
        "医生推荐的专业选择，专家推荐品牌。",
        # 豁免只到句末：清单句之后的正文仍要判 BLOCK
        "禁用表达：pain-free。但我们这款提供无痛体验，还能帮助催奶。",
        # ★ 2026-10-12 补（否定守卫扩面后的**反向对照**）：这几条都带否定外壳（`Don't` / `won't` /
        #   `Not only`），但都是**真声明** —— 补守卫**不许**把它们一起吞掉。
        #   它们同时在钉窗口：`Don't`→`milk` 分别隔 30 / 26 字 ⇒ 窗口放到 30 就会在这里变红。
        "Don't miss out - it increases your milk supply.",
        "Don't wait - it increases your milk supply.",
        "Not only does it increase milk supply, but it also helps you pump faster.",
        "You won't believe how much more milk you'll get.",
        # ★ 这条钉住**分开写**那条（`did/will/can/… + not`）的窗口上限：`not`→`milk` 隔 **23** 字，
        #   是真声明 ⇒ 窗口一放宽到 23 以上，它就从 HIT 变 MISS、精确变红。
        "You will not believe how much more milk you'll get.",
        # ⚠️ **故意不放在这里**：`Do not wait - it boosts your milk supply!`（真声明，`not`→`milk` 隔 23 字）
        #   —— 实测**改前就 MISS**：压它的是 **2026-10-09 那条老守卫的 40 字窗口**
        #   （`do\s+not` 这一支），**不是本轮新增的三条**。⇒ 属**既有漏放**，单独记在交付件里；
        #   放进 positives ⇒ 本自证恒红。要修得**收紧那条 40 字的老守卫**，是另一次改动、得单独裁。
    ]),
    ("negatives_should_be_empty", [
        "Our device is not intended to treat, cure or prevent any disease.",
        "本产品不能治疗乳腺炎，也不可以预防疾病。",
        "禁用表达：pain-free、more milk。",
        "DO NOT SAY: pain-free; SAY THIS INSTEAD: comfortable.",
        "依据原文：「more milk」属于禁用表述。",
        # ★ 2026-10-12 反向对照（H09 变形）：含 `sucking` 但**没有** `baby-like`
        #   ⇒ 新正则**不许**把它拦下（否则就是「补词补过头」）。
        "The one-way valve prevents milk from flowing back while sucking.",
        # ★ 2026-10-12 反向对照（H02 物主代词放宽）：放宽**只加人称**，不加"拦别的东西"的能力 ——
        #   含物主代词与 `milk`、但**没有增产动词**的句子，必须**仍然 MISS**。
        "Her milk supply is fine and the bottle keeps it warm.",
        # ★★ 2026-10-12 补（**否定守卫扩面**）—— 本块原先写着「`It did not increase her milk supply.`
        #   故意不放这里（既有缺陷）」，那个缺口**本轮已修** ⇒ 它必须进 negatives，
        #   否则这把尺子对本次改动是瞎的（改前实测：`It did not increase her milk supply.` → **HIT H02**；
        #   同伴 `Our pump won't increase milk supply.` → **HIT H02**）。
        #   病灶：negation 的交替列只写到 `do/does`，**没有 `did/will/can/…`** ⇒ 同一件事换个时态就不豁免。
        #   修法见 `kb/.work/l5_export.py::WHITELIST_COMMON["negation_patterns"]`（**只补否定词形**）。
        "It did not increase her milk supply.",
        "It did not increase your milk supply.",   # 同族、换个物主代词，也必须豁免
        "Our pump won't increase milk supply.",
        "It doesn't boost your milk supply.",
        "Our pump cannot cure any disease.",
        "The pump cannot treat mastitis.",
        # ★ 反向对照（同上）：这次改动**不许**把否定句豁免带走 ——
        #   「未经临床证明」是**被否定的宣称**（否定白名单该豁免它），不是规则名。
        "这款产品未经临床证明，也没有科学依据。",
        # ★ 反向对照（效果百分比）——**折扣不是效果宣称**（PRD 处理口径原文「折扣百分比不在此列」）；
        #   成分占比、纯时长同理。这三条钉住白名单：拆掉 EFFECT_DATA_WHITELIST 立刻变红。
        "Save 20% off with code MOM20.",
        "95% cotton, 5% spandex.",
        # ★ 反向对照（销量/排名形态）：只是产品参数，没有任何排名/销量宣称 ⇒ 必须 MISS
        "M5 Pro 双泵吸奶器，主机重 260 克，配件可拆洗，支持洗碗机清洁",
        "The discount is 15% and delivery in 2 weeks.",

        # ══════════════════════════════════════════════════════════════════════
        # ★★ 2026-10-21（Owner 裁定 A）：**排名/最高级一族不再判险** —— 六条反向对照。
        #   起因（真单，`merged-2026-10-21T08_37_38.json`）：一句写着「best/#1/No.1/最佳/最好
        #   按 2026-09-09 口径放开」的**口径说明**被判成 4 处 P0/P1 ——
        #   三处来路：H05 的正则没跟着出列、10-21 又把边界表述灌进了词表、V02/V03 各有同族词条。
        #   下面六条就是那三处来路的形状；任何一处回填 ⇒ 这一组精确变红。
        # ══════════════════════════════════════════════════════════════════════
        "虚假安全承诺（best/#1/No.1/最佳/最好等排名最高级按2026-09-09口径放开，"
        "海外广告允许，不再判险）",          # 口径说明本身：它不是宣称，更不是规则名
        "The #1 best seller on Amazon.",     # 英文排名/最高级
        "Our pump is the No.1 choice for moms.",
        "销量第一的吸奶器。",                  # 中文事实性排名 → 非阻断提示（`RANK_ADVISORY_RX`）
        "全美销量第一。",
        "这款是最好用的吸奶器。",              # 主观最高级

        # ★★ 2026-10-22（Owner 裁定 B）：**裸「100%」不再判 P0** —— 四条反向对照。
        #   病灶：一张秋促组合图，OCR 在 Nipple Cream 管身上只读到一行「100%」⇒ V02 裸词命中 ⇒ 整单 BLOCK。
        #   Owner：「医学安全类的绝对词才报 P0」。带限定词的（100% safe/100% 天然）仍由 H05 判 P0。
        "Nipple Cream 100%",
        "100% cotton",
        "100% BPA-free",
        "Made with 100% recycled packaging",

        # ⚠️ **故意不放在这里**（**两条已知残留：都是取舍的结果，不是没修到**）：
        #   ① `It has not been shown to increase milk supply.`（免责声明）—— `not`→`milk` 隔 **24** 字，
        #      而真声明 `Do not wait - it boosts your milk supply!` 只隔 **22** 字
        #      ⇒ **没有窗口能把两者分开**；取「不豁免」一侧（漏放是真红线）⇒ 它**仍 HIT**。
        #      （钉它的是 positives 里那条 22 字的真声明；窗口一放宽，那条先红。）
        #   ② `This pump is not a treatment for clogged ducts.` —— 尾组是 `\btreat\b`，
        #      `treatment` 不匹配（**既有口径限制**，与本轮改动无关）。
        #   放进 negatives ⇒ 本自证**恒红**，尺子就废了。两条按「已知残留」单独记在交付件里。
    ]),
]


def selftest():
    rules = compile_patterns()
    print(f"载入 P0 模式 {len(rules)} 条\n")
    ok = True
    for group, texts in SELFTEST:
        print(f"--- {group}")
        for s in texts:
            h = match(s, rules)
            status = "HIT " if h else "MISS"
            want_hit = group == "positives"
            mark = "✅" if bool(h) == want_hit else "❌"
            if bool(h) != want_hit:
                ok = False
            codes = ",".join(sorted({x["rule_code"] for x in h}))
            print(f"  {mark} {status} [{codes:22s}] {s[:56]}")
            if h:
                print(f"        建议改法: {h[0]['suggested_replacement'][:70]}")
    print(f"\n自测结论：{'✅ 正例全命中、负例零误报' if ok else '❌ 存在偏差'}")
    return 0 if ok else 2


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--text")
    ap.add_argument("--file")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        sys.exit(selftest())
    if a.file:
        text = open(a.file, encoding="utf-8").read()
    elif a.text is not None:
        text = a.text
    else:
        text = sys.stdin.read()
    t0 = time.perf_counter()
    hits = match(text)
    dt = (time.perf_counter() - t0) * 1000
    if a.json:
        print(json.dumps({"elapsed_ms": round(dt, 3), "hits": hits}, ensure_ascii=False, indent=2))
    else:
        verdict = "BLOCK" if hits else "PASS"
        print(f"结论: {verdict}　|　耗时 {dt:.2f} ms　|　文本 {len(text)} 字符")
        for h in hits:
            print(f"  [{h['match_note']}] {h['rule_code']} ({h['pattern_id']}) 命中 {h['matched_count']} 处")
            print(f"    命中的表达: {', '.join(m['pattern'] for m in h['matched'][:6])}")
            print(f"    依据: {h['anchor'][:70]}  sha256={str(h['source_sha256'])[:16]}")
            print(f"    建议改法: {h['suggested_replacement'][:120]}")
    sys.exit(1 if hits else 0)


if __name__ == "__main__":
    main()
