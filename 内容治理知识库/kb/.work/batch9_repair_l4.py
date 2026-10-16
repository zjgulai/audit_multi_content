#!/usr/bin/env python3
"""修复被非原子写截断的 kb/l4/registry/l4.json。
- 未被触碰的 JSON 前缀逐字节保留（kb_version…numbering.no_reuse）
- issued/assignments 用 kb/.work/l4_article.json 的 mapping 重建（509 条，逐号一致）
- 失败教训：目标文件必须 temp + os.replace 原子替换；json.dump 中途抛错会留下半成品。
"""
import json, os
ART = json.load(open("kb/.work/l4_article.json", encoding="utf-8"))
M = ART["mapping"]
assert len(M) == 509 and len(set(M.values())) == 509, "mapping 不是 509 条唯一"
by_seq = lambda p: sorted((k for k in M if M[k].startswith(p)), key=lambda k: int(M[k].split(".")[1]))
w1, w2 = by_seq("W-1."), by_seq("W-2.")
assert [M[k] for k in w1] == [f"W-1.{i}" for i in range(1, 57)]
assert [M[k] for k in w2] == [f"W-2.{i}" for i in range(1, 454)]

prefix = open("kb/.work/batch9/l4.json.corrupt", encoding="utf-8").read()
prefix = prefix[:prefix.index('  "issued": {')]
assert prefix.rstrip().endswith('",'), prefix[-40:]

numbering_tail = {
 "issued": {
   "W-1": {"library": "wording", "library_label": "3_措辞表达库", "block": 1, "form": "entry",
           "assigned": {k: M[k] for k in w1}, "count": 56, "range": ["W-1.1", "W-1.56"], "next_seq": 57,
           "block_label": "entry（词条/命中片段型）", "change": "unchanged_existing"},
   "W-2": {"library": "wording", "library_label": "3_措辞表达库", "block": 2, "form": "revision_pair",
           "assigned": {k: M[k] for k in w2}, "count": 453, "range": ["W-2.1", "W-2.453"], "next_seq": 454,
           "block_label": "revision_pair（修订对型）", "change": "unchanged_existing"}},
 "totals": {"assigned": 509, "newly_assigned": 0, "reused_from_ledger": 509, "segments": 2,
            "libraries_used": ["wording"],
            "libraries_empty": ["external_standard", "internal_sample", "product_desc", "unknown"],
            "note": "本键是 20260923-1445 首跑的当时事实，按 append-only 留痕不改写；本批（20260924-1320）的全量口径见顶层 totals_20260924-1320"},
}
rest = {
 "reproduce": {"how": "python3 kb/.work/l4_article.py 20260923-1445",
   "expect": "同一份 kb/l3 候选重跑：映射完全一致、追加 0 行、kb/l3/candidates/rules.jsonl 逐字节不变",
   "ledger": "kb/l4/registry/l4.json 的 numbering.issued 是唯一台账；后续批次只能在其上追加，不得改写已发号码"},
 "promotion_rule": {"status": "待抽查（本批不做）",
   "candidate_state": "kb/l3/candidates/rules.jsonl 的 status = provisional",
   "path": "候选 → 抽查（人工）→ 定稿写 kb/l4/canonical/rules.jsonl（status = stable）→ 才允许冻结版本",
   "what_changes_on_promotion": "写 canonical 时新增定稿记录（含条款号），不动候选行",
   "gate": "抽查未过不得晋升；晋升不是改名，是新增定稿记录"},
 "version_rule": {"article_no": "规则的稳定标识 → 本批分配，永不复用",
   "kb_version": "发布语义 → 仍为 v0", "this_batch": "不冻结、不发版本；versions.jsonl 不追加版本行",
   "release_id": "跨库发布号，本批不产生（与 kb_version 不混用）"},
 "assignments": M,
 "inputs": {"candidates": "kb/l3/candidates/rules.jsonl", "rules": 509, "base_lines": 1018,
   "base_bytes": 2877760,
   "base_sha256": "d9a28e25f6fee706f5d96b2d21973eef6b362f16a40a67caa6762bace8de20b5",
   "lines_after": 1527, "appended_this_run": 0, "prefix_unchanged": True,
   "l3_distiller_version": "l3-0.2"},
}
inner = json.dumps(numbering_tail, ensure_ascii=False, indent=1)[2:-2]
body = prefix + inner + "\n  },\n"
for k, v in rest.items():
    body += '  %s: %s,\n' % (json.dumps(k, ensure_ascii=False),
                             json.dumps(v, ensure_ascii=False, indent=1).replace("\n", "\n  "))
body = body.rstrip().rstrip(",") + "\n}\n"

tmp = "kb/l4/registry/.l4.json.tmp"
open(tmp, "w", encoding="utf-8").write(body)
json.load(open(tmp, encoding="utf-8"))            # 先验后换
os.replace(tmp, "kb/l4/registry/l4.json")
d = json.load(open("kb/l4/registry/l4.json", encoding="utf-8"))
print("修复完成。顶层键:", list(d.keys()))
print("numbering 键:", list(d["numbering"].keys()))
print("assignments:", len(d["assignments"]), "| issued:", list(d["numbering"]["issued"].keys()))
print("509 号码与 mapping 完全一致:", d["assignments"] == M)
print("W-1.1/W-2.1:", d["assignments"]["r-006445396c95aa10"], d["numbering"]["issued"]["W-2"]["range"])
