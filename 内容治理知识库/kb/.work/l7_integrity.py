#!/usr/bin/env python3
"""L7 自检：7 项，产出 kb/.work/l7_integrity.json。
1) kb/l0~l6 未被修改（对 L4/L5/L6 留痕里记录的产物哈希 + L5 的 tree_sha256 逐字节核对）
2) 每条结论可追到 anchor + source_sha256，无裸 URL
3) 引用的库名都来自四类库
4) 无命中确实拒答，文案与 no_hit_semantics 一致
5) 检索轨迹完整
6) 三态输出符合模板（自验里各至少出现一次）
7) kb/l4/canonical/rules.jsonl 仍空；kb_version 仍 v0；versions.jsonl 版本行 0
"""
import collections, hashlib, json, os, re, subprocess, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(ROOT)
L7, RUN = "kb/l7", "20260923-1500"
ev = {"run_id": RUN, "checked_at": time.strftime("%Y-%m-%d %H:%M:%S"), "checks": {}}


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def tree_fp(d):
    rows = []
    for dp, _, fns in os.walk(d):
        for fn in sorted(fns):
            p = os.path.join(dp, fn)
            rows.append(f"{os.path.relpath(p, ROOT)}\0{os.path.getsize(p)}\0{sha(p)}")
    rows.sort()
    return hashlib.sha256("\n".join(rows).encode()).hexdigest()


# ---- 1) 冻结层：拿各层留痕里记的产物哈希当基线
base_hashes = {}
for f in ("kb/l4/runs/20260923-1445.json", "kb/l5/runs/20260923-1430.json", "kb/l6/runs/20260923-1440.json"):
    if os.path.exists(f):
        for a in json.load(open(f, encoding="utf-8"))["artifacts"]:
            base_hashes.setdefault(a["path"], a["sha256"])
l5layers = json.load(open("kb/.work/l5_integrity.json", encoding="utf-8"))["checks"]["frozen_layers"]["layers"]
rows, bad = [], []
for p, want in sorted(base_hashes.items()):
    if not os.path.exists(p):
        bad.append({"path": p, "why": "留痕里记过但现在不存在"})
        continue
    got = sha(p)
    rows.append({"path": p, "sha256_16": got[:16], "same_as_recorded": got == want})
    if got != want:
        bad.append({"path": p, "why": "哈希与留痕记录不一致", "now": got[:16], "recorded": want[:16]})
tree_same = {}
for d in ("l0", "l1", "l2"):
    tree_same[d] = tree_fp(f"kb/{d}") == l5layers[d]["tree_sha256"]
# l3：前 1018 行必须等于 L6 记录值；前 1527 行必须等于 L4 记录值
l3 = open("kb/l3/candidates/rules.jsonl", "rb").read()
l3_lines = l3.split(b"\n")
if l3_lines and l3_lines[-1] == b"":
    l3_lines.pop()
base1018 = hashlib.sha256(b"".join(l + b"\n" for l in l3_lines[:1018])).hexdigest()
base1527 = hashlib.sha256(b"".join(l + b"\n" for l in l3_lines[:1527])).hexdigest()
l6rec = json.load(open("kb/.work/l6_integrity.json", encoding="utf-8"))["checks"]["frozen_layers"]["l3_candidates"]
l4rec = json.load(open("kb/l4/runs/20260923-1445.json", encoding="utf-8"))
l4_l3_sha = next(a["sha256"] for a in l4rec["artifacts"] if a["path"].endswith("candidates/rules.jsonl"))
ev["checks"]["frozen_layers"] = {
    "artifact_hash_check": {"checked": len(rows), "mismatch": bad,
                            "layers_covered": sorted({p.split("/")[1] for p in base_hashes})},
    "l0_l2_tree_sha256_same_as_L5": tree_same,
    "l3_candidates": {"lines": len(l3_lines), "base1018_matches_L6": base1018 == l6rec["sha256"],
                      "whole1527_matches_L4": base1527 == l4_l3_sha, "bytes": len(l3)},
    "verdict": "PASS" if (not bad and all(tree_same.values()) and base1018 == l6rec["sha256"]
                          and base1527 == l4_l3_sha) else "FAIL",
}

# ---- 2/3) 引用契约：锚点、sha、裸 URL、库名
texts = {}
for f in ("selftest_a_block.md", "selftest_b_refusal.md", "selftest_d_paraphrase.md", "selftest_e_trigger.md"):
    texts[f] = open(f"{L7}/{f}", encoding="utf-8").read()
for f in sorted(os.listdir(f"{L7}/reports")):
    texts[f"reports/{f}"] = open(f"{L7}/reports/{f}", encoding="utf-8").read()
all_text = "\n".join(texts.values())
bib_blocks = re.findall(r"- 条款号[^\n]*\n((?:\|.*\n)+)", texts["selftest_a_block.md"])
cites = re.findall(r"第 (W-[\d.]+) 条", all_text)
anchors = re.findall(r"锚点[：:]\s*`?([#][^\s`|]+)", all_text)
shas = re.findall(r"source_sha256[：:]\s*`?([0-9a-f]{16,64})", all_text)
bare_urls = re.findall(r"https?://[^\s)｜|]+", all_text)
libs = set(re.findall(r"《([^》]+?)\s*v0", all_text))
real_libs = {"外部标准库", "内部正负样本库", "措辞表达库", "产品描述库"}
ghost = [l for l in libs if l not in real_libs]
ev["checks"]["citation_contract"] = {
    "citations": len(cites), "anchors": len(anchors), "source_sha256": len(shas),
    "bare_urls": bare_urls, "library_names_used": sorted(libs), "library_names_not_in_kb": ghost,
    "verdict": "PASS" if (cites and anchors and shas and not bare_urls and not ghost) else "FAIL",
    "note": "结论里的条款号/锚点/source_sha256 三类都在；输出里没有裸 URL；库名只有知识库真实存在的四类库",
}

# ---- 4) 拒答
cap = json.load(open("kb/l6/registry/l6.json", encoding="utf-8"))["retrieval_capability"]
b = texts["selftest_b_refusal.md"]
nhs_hit = any(v in b for v in cap["no_hit_semantics"].values())
ev["checks"]["refusal"] = {
    "refuses": "无法给出结论（拒答）" in b,
    "no_hit_semantics_verbatim": nhs_hit,
    "semantics_source": cap["no_hit_semantics"],
    "verdict": "PASS" if ("无法给出结论（拒答）" in b and nhs_hit) else "FAIL",
}

# ---- 5) 检索轨迹
tr = {"P0": "P0 确定性匹配" in all_text or "P0 0 命中" in all_text,
      "规则层": "规则层" in all_text, "单元层分数与门限": re.search(r"BM25 最高[^\n]*门限|最高原始分[^\n]*门限", all_text) is not None,
      "采用舍弃": "采用" in all_text or "低于门限" in all_text or "未触发向量补召" in all_text,
      "向量启用与否": "向量补召" in all_text}
ev["checks"]["retrieval_trace"] = {"elements": tr, "verdict": "PASS" if all(tr.values()) else "FAIL"}

# ---- 6) 三态模板
a = texts["selftest_a_block.md"]
tmpl = {
    # ★ 2026-10-06 改：原先这三条**只查到「共发现」为止** ——
    #   `"【审查结论：BLOCK】共发现" in a`，后半句（「必须修改」/「需人工确认」）压根没查。
    #   于是引擎把 REVIEW 与 BLOCK 写成**同一句话**「共发现 N 处需处理问题」，
    #   一路绿灯跑了半个月，直到 Owner 在群里看见格式不对。
    #   判据存在、但没盖住出事的那一跳 —— AGENTS.md §2.4 点名的正是这个形状。
    #   现在措辞逐字断言（PRD §5.3.2 / §5.3.3 / §5.3.1）。
    "BLOCK": re.search(r"【审查结论：BLOCK】共发现 \d+ 处必须修改。", a) is not None
             and "请修改后重新提交。" in a,
    "REVIEW": re.search(r"【审查结论：REVIEW】共发现 \d+ 处需人工确认。", a) is not None
              and "建议转" in a,
    # ★ 这一条第一版写的是 `可转交 @\S+ 进行 sign-off` —— 当场把**正确的夹具**判红：
    #   夹具写的是 `@sign-off 责任人（未配置） 进行 sign-off`（角色位，不是句柄），
    #   而 `\S+ ` 要求 @ 后面紧跟一个不含空格的词再加空格。会误报的判据比没有判据更糟。
    #   判据收宽到「@ 开头 + 同一条线里出现『进行 sign-off』」—— PRD §5.3.1 要的是那个**动作**，
    #   不是「@ 后面必须恰好是一个 handle」（句柄未配置时本来就不该编一个）。
    "PASS": re.search(r"【审查结论：PASS】未发现已知底线风险，可转交 @\S[^\n]*进行 sign-off", a) is not None,
    "汇总分流(≥3)": "→ 查看完整问题清单与修改建议：" in a,
    # ★ 2026-10-06：夹具（`selftest_a_block.md`）是**历史样本**，标签加不加粗都认；
    #   而**引擎真实产出**那条（下面的 template_from_engine）**必须加粗** —— 严格的一侧在那里。
    # ★★ 2026-10-14（Owner 裁定）：逐条块**不再有 `**判定**` 行**（PRD §5.3 逐条模板里没有它，
    #   三态只在结论行一处）⇒ 下面两条判据同步收窄：
    #     ① 夹在「依据」与「建议」之间的补充行只认 `锚点` / `source_sha256`；
    #     ② 原「逐条块含引用三要素」把 `判定：…置信度：` 当成了三要素之一 —— 它**不是**
    #        引用契约的一部分（引用契约要的是 锚点 + source_sha256）。改钉真正的引用锚。
    "逐条分流(1-2)": re.search(r"1\.【[^】]+】[^\n]*\n\s+\*{0,2}原因\*{0,2}：[^\n]*\n\s+\*{0,2}依据\*{0,2}：[^\n]*\n"
                              r"(?:\s+\*{0,2}(?:锚点|source_sha256)\*{0,2}[^\n]*\n)*\s+\*{0,2}建议\*{0,2}：", a) is not None,
    # ★★ 2026-10-19 改名（原「逐条块含引用两要素」）：这一条量的是**历史夹具**
    #   （`selftest_a_block.md` 是 2026-09-23 那一轮的真实产出记录），它里面**还带着锚点行** ——
    #   那是当时的卡，**不改写历史**。所以这里改称「历史夹具仍留着引用锚」，
    #   而**当前卡片契约**（不许有锚点行、建议不许是占位符）由下面 `template_from_engine` 的
    #   `BLOCK 逐条块无 锚点 行` / `BLOCK 建议非占位符` **钉在真生产者上** ——
    #   「历史样本」与「现行契约」分开，才不会一改格式就把记录判成故障。
    "历史夹具仍留着引用锚（记录 2026-09-23 当时的卡）":
        re.search(r"1\.【[^】]+】[\s\S]{0,600}?\*{0,2}锚点\*{0,2}：[^\n]*source_sha256：[^\n]*", a) is not None,
    # ★★ 反向对照（2026-10-14 加）：谁把 `**判定**` 行加回夹具，这里**精确变红** ——
    #   否则「删掉判定行」这件事没有任何失败信号（旧判据本来就容得下它，删没删都绿）。
    "夹具里不再有 判定 行": not re.search(r"^\s+\*{0,2}判定\*{0,2}：", a, re.M),
}
ev["checks"]["template_conformance"] = {"markers": tmpl, "verdict": "PASS" if all(tmpl.values()) else "FAIL"}

# ---- 6b) ★ 判据要盖住**真生产者**，不能只盖自验夹具（2026-10-06 加）
#
# 上面那六条查的是 `kb/l7/selftest_a_block.md` —— 一份**手写的夹具**。
# 真实回话里的那一行是 `kb/l7/review-engine/core/review_engine.py` 的 `render_summary()` 生成的，
# 而**没有任何东西查过它**。这就是「守衡在群里发的格式」与「自验里写的格式」可以是两回事的原因。
# 现在把引擎真的调起来，三态各断言一次 —— 与夹具那六条**成对**：只查一边，另一边恒真。
import importlib.util as _ilu
_eng_path = os.path.join(ROOT, "kb/l7/review-engine/core/review_engine.py")
_producer = {"engine_found": os.path.exists(_eng_path), "states": {}, "verdict": "FAIL"}
if _producer["engine_found"]:
    try:
        # ★ 引擎是用 `from .sla import …` / 兜底 `from sla import …` 写的 ⇒ 以文件路径加载时
        #   它的同目录必须临时进 `sys.path`，否则 `ModuleNotFoundError: No module named 'sla'`。
        #   第一版就是漏了这一步，于是本项落成 **UNTESTED** —— 而那是**对的行为**：
        #   「引擎没跑起来」与「引擎写错了」必须长得不一样，不许当成通过（§2.4.4）。
        _core = os.path.dirname(_eng_path)
        if _core not in sys.path:
            sys.path.insert(0, _core)
        _spec = _ilu.spec_from_file_location("_l7_review_engine", _eng_path)
        _mod = _ilu.module_from_spec(_spec)
        _spec.loader.exec_module(_mod)
        _one = {"risk_type": "功效宣称-催乳与通乳宣称", "location": "全文", "original_text": "increase milk supply",
                "reason": "H02 催乳/增产/奶量产出承诺", "suggestion": "删除 more milk 等承诺",
                "fact_or_inference": "事实", "confidence": "高",
                "evidence": {"library": "措辞表达库", "article_no": "W-1.18",
                             "anchor": "#广告文案明细/recvuJYdOb1Rm1/命中片段", "source_sha256": "c" * 64},
                "evidence_url": "kb/l3/candidates/rules.jsonl#W-1.18",
                "evidence_id": "《措辞表达库 v0》第 W-1.18 条"}
        _cases = {
            "BLOCK": _mod.render_summary("BLOCK", [_one, _one], __import__("collections").Counter(), None),
            "REVIEW": _mod.render_summary("REVIEW", [_one], __import__("collections").Counter(), None),
            "PASS": _mod.render_summary("PASS", [], __import__("collections").Counter(), None),
        }
        _producer["states"] = {
            "BLOCK 逐字": re.search(r"【审查结论：BLOCK】共发现 2 处必须修改。", _cases["BLOCK"]) is not None,
            "BLOCK 收尾": "请修改后重新提交。" in _cases["BLOCK"],
            # ★ 这一条查的是**引擎真实产出**（`render_summary`），所以**要求加粗**：
            #   Owner 2026-10-06 明确要「原因/依据/建议」加粗，方便业务同事扫读；
            #   钉在这里，格式退回非加粗时会红。
            # ★★ 2026-10-14（Owner 裁定）：**`**判定**` 那一行已从逐条块删除**
            #   （PRD §5.3 逐条模板只有 原因 / 依据 /（BLOCK 才有）建议；三态只在结论行一处）。
            # ★★ 2026-10-19（Owner 逐字：「**去掉锚点**」）：**`**锚点**` 那一行也从卡上删了**
            #   —— 它是库内坐标 + sha，PRD §5.3.3/§5.3.4 的逐条字段里没有它
            #   （溯源仍在 findings / 报告 / 入口 JSON 里）。
            #   ⇒ 本条由「四要素」收窄为 **三要素**：原因 / 依据 / 建议。加粗要求一个字没松。
            "BLOCK 逐条三要素": re.search(r"1\.【[^】]+】[^\n]*\n\s+\*\*原因\*\*：[^\n]*\n\s+\*\*依据\*\*：[^\n]*\n"
                                      r"\s+\*\*建议\*\*：", _cases["BLOCK"]) is not None,
            # ★★ 反向对照（2026-10-14 加）：引擎产出里**不许再出现 `**判定**` 行**。
            #   谁把它加回来（或在别处又渲染一次），这一条精确变红。
            "BLOCK 逐条块无 判定 行": re.search(r"^\s+\*\*判定\*\*：", _cases["BLOCK"], re.M) is None,
            # ★★ 反向对照（2026-10-19 加）：引擎产出里**不许再出现 `**锚点**` 行**。
            #   谁把它加回卡上（或两处产者只改了一处），这一条精确变红。
            "BLOCK 逐条块无 锚点 行": re.search(r"^\s+\*\*锚点\*\*：", _cases["BLOCK"], re.M) is None,
            # ★★ 2026-10-19（Owner：「**必须给建议**」）：`_one` 这条夹具**没有** `suggestion`
            #   （正是库内无原话那一档）⇒ 必须被兜底表补上，且**不许**印占位符。
            "BLOCK 建议非占位符": (re.search(r"^\s+\*\*建议\*\*：（来源未给", _cases["BLOCK"], re.M) is None
                              and re.search(r"^\s+\*\*建议\*\*：\S", _cases["BLOCK"], re.M) is not None),
            "REVIEW 逐字": re.search(r"【审查结论：REVIEW】共发现 1 处需人工确认。", _cases["REVIEW"]) is not None,
            "REVIEW 收尾": "建议转" in _cases["REVIEW"],
            "REVIEW 与 BLOCK 措辞**必须不同**": ("需处理问题" not in _cases["REVIEW"]
                                          and "需处理问题" not in _cases["BLOCK"]),
            "PASS 逐字": re.search(r"【审查结论：PASS】未发现已知底线风险，可转交 @\S[^\n]*进行 sign-off",
                                _cases["PASS"]) is not None,
        }
        _producer["verdict"] = "PASS" if all(_producer["states"].values()) else "FAIL"
    except Exception as _e:  # 引擎读不起来 ⇒ **未测**，不许当成通过（也不许当成红）
        _producer["error"] = f"{type(_e).__name__}: {_e}"
        _producer["verdict"] = "UNTESTED"
else:
    _producer["verdict"] = "UNTESTED"
ev["checks"]["template_from_engine"] = _producer

# ---- 7) 版本纪律
canon = os.path.getsize("kb/l4/canonical/rules.jsonl")
vrows = [l for l in open("kb/versions/versions.jsonl", encoding="utf-8")
         if l.strip() and not l.lstrip().startswith("#")]
kbvs = {p: json.load(open(f"kb/{p}", encoding="utf-8")).get("kb_version") for p in
        ("l0/registry/kb.json", "l1/registry/l1.json", "l2/registry/l2.json", "l3/registry/l3.json",
         "l4/registry/l4.json", "l5/registry/l5.json", "l6/registry/l6.json", "l7/registry/l7.json")}
ev["checks"]["version_discipline"] = {
    "l4_canonical_bytes": canon, "versions_jsonl_rows": len(vrows), "kb_version_by_registry": kbvs,
    "verdict": "PASS" if canon == 0 and not vrows and {v for v in kbvs.values() if v} == {"v0"} else "FAIL",
}

# ---- 附加）条款号读取
latest = {}
for l in open("kb/l3/candidates/rules.jsonl", encoding="utf-8"):
    if l.strip():
        r = json.loads(l)
        latest[r["rule_id"]] = r
missing = [rid for rid, r in latest.items() if not (r.get("article_no") or "").strip()]
segs = collections.defaultdict(list)
for r in latest.values():
    if (r.get("article_no") or "").strip():
        segs[r["article_no"].rsplit(".", 1)[0]].append(int(r["article_no"].rsplit(".", 1)[1]))
ev["checks"]["article_no_read"] = {
    "rules": len(latest), "missing": missing,
    "ranges": {k: [min(v), max(v), len(v)] for k, v in sorted(segs.items())},
    "verdict": "PASS" if len(latest) == 509 and not missing else "FAIL",
    "note": "本步只读 L4 分配的条款号，不重新分配、不改 kb/l3",
}

ev["verdict"] = ("PASS" if all(v.get("verdict") == "PASS" for v in ev["checks"].values())
                 else ("UNTESTED" if any(v.get("verdict") == "UNTESTED" for v in ev["checks"].values())
                       else "FAIL"))
json.dump(ev, open("kb/.work/l7_integrity.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

for k, v in ev["checks"].items():
    print(f"[{v['verdict']}] {k}")
    if k == "frozen_layers":
        h = v["artifact_hash_check"]
        print(f"        核对 {h['checked']} 个留痕产物（层：{h['layers_covered']}），不一致 {len(h['mismatch'])}")
        print(f"        l0/l1/l2 tree_sha256 与 L5 基线一致：{v['l0_l2_tree_sha256_same_as_L5']}")
        print(f"        l3/candidates：{v['l3_candidates']['lines']} 行｜前1018行={v['l3_candidates']['base1018_matches_L6']}"
              f"｜前1527行={v['l3_candidates']['whole1527_matches_L4']}")
    if k == "citation_contract":
        print(f"        条款号 {v['citations']}｜锚点 {v['anchors']}｜sha {v['source_sha256']}｜"
              f"裸 URL {len(v['bare_urls'])}｜库名 {v['library_names_used']}｜不存在的库名 {v['library_names_not_in_kb']}")
    if k == "refusal":
        print(f"        拒答={v['refuses']}｜no_hit_semantics 逐字={v['no_hit_semantics_verbatim']}")
    if k == "retrieval_trace":
        print(f"        {v['elements']}")
    if k == "template_conformance":
        print(f"        {v['markers']}")
    if k == "version_discipline":
        print(f"        canonical {v['l4_canonical_bytes']} 字节｜versions 行 {v['versions_jsonl_rows']}｜"
              f"kb_version 取值 {sorted({x for x in v['kb_version_by_registry'].values() if x})}")
    if k == "article_no_read":
        print(f"        {v['rules']} 条，缺 article_no {len(v['missing'])}｜区间 {v['ranges']}")
    if k == "template_from_engine":
        # ★ 三态读数必须**逐项打出来**：只打一个 PASS/FAIL，
        #   看的人分不出「引擎三态都对」与「这条检查根本没跑起来」（§2.4.4）。
        print(f"        引擎在盘上：{v.get('engine_found')}"
              + (f"｜读不起来：{v['error']}" if v.get("error") else ""))
        for name, hit in (v.get("states") or {}).items():
            print(f"        {'✅' if hit else '❌'} {name}")
print(f"\n自检总计：{ev['verdict']}")
# ★ 未测与红必须长得不一样：退出码 2 ≠ 1 ≠ 0（§2.4.2 的 L3 同口径）。
sys.exit({"PASS": 0, "FAIL": 1, "UNTESTED": 2}[ev["verdict"]])
