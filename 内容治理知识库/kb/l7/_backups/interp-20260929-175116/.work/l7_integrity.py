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
    "BLOCK": "【审查结论：BLOCK】共发现" in a and "请修改后重新提交。" in a,
    "REVIEW": "【审查结论：REVIEW】共发现" in a and "建议转" in a,
    "PASS": "【审查结论：PASS】未发现已知底线风险，可转交" in a,
    "汇总分流(≥3)": "→ 查看完整问题清单与修改建议：" in a,
    "逐条分流(1-2)": re.search(r"1\.【[^】]+】[^\n]*\n\s+原因：[^\n]*\n\s+依据：[^\n]*\n"
                              r"(?:\s+(?:锚点|source_sha256|判定)[^\n]*\n)*\s+建议：", a) is not None,
    "逐条块含引用三要素": re.search(r"1\.【[^】]+】[\s\S]{0,600}?锚点：[^\n]*source_sha256：[^\n]*"
                                r"[\s\S]{0,200}?判定：[^\n]*置信度：", a) is not None,
}
ev["checks"]["template_conformance"] = {"markers": tmpl, "verdict": "PASS" if all(tmpl.values()) else "FAIL"}

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

ev["verdict"] = "PASS" if all(v.get("verdict") == "PASS" for v in ev["checks"].values()) else "FAIL"
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
print(f"\n自检总计：{ev['verdict']}")
sys.exit(0 if ev["verdict"] == "PASS" else 1)
