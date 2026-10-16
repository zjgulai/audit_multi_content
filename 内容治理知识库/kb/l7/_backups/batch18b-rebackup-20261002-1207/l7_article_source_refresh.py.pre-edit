#!/usr/bin/env python3
"""L7 登记表 · `article_no_source` 快照刷新（**不是发号，是订正一张过期的读取快照**）。

## 为什么

`kb/l7/registry/l7.json → article_no_source` 是 L7 对 L4 发号状态的**读取快照**
（字段 `read_at` 就是它的语义：某时刻读到的样子）。它上次刷新是 **2026-09-24 15:20**，
之后发生了两件事：

  ① `kb/l3/candidates/external_standard.jsonl` 的 123 条外部标准条款级规则入库
     （L3 run 20260930-1400，distiller_version l3-clause-0.1）—— 快照完全不知道有这 123 条；
  ② 2026-09-30 RUN=20260930-1721 给它们发了 E-2.1…E-2.123。

于是快照现在**与台账互相矛盾**：它把 E-2 列在 `reserved_unused_segments`（预留未用），
而 E-2.1…E-2.123 已经发出去了。这不是措辞问题 —— L7 是引用契约层，
`kb/l7/skills/kb-content-review` 按这张表判断「这个条款号存不存在」；
留着一张说 E-2 未启用的表，引用 E-2.x 会被判成无效号。

## 边界（本脚本只做这些）

- **只改 `l7.json` 的 `article_no_source` 一个块**；citation_contract / vocabulary /
  decision_rules / approvers 等一概不动。
- **不分配号码**（发号是 L4 的动作，已由 RUN=20260930-1721 完成）；本脚本只读取台账并如实记录。
- 数值全部**从台账与候选件现算**，不写死 —— 写死就是下一次过期。
- 幂等：算出来与现值一致就零写入。
- 原子写（tmp → json.load 验 → os.replace）。

用法：
    kb/kbpy .work/l7_article_source_refresh.py <RUN>            # 干跑
    kb/kbpy .work/l7_article_source_refresh.py <RUN> --apply    # 落盘
"""
import os as _os, sys as _sys
if not _os.environ.get("KB_INTERP_OK"):
    _d = _os.path.dirname(_os.path.abspath(__file__)); _cfg = None
    while True:
        _p = _os.path.join(_d, ".kb-python")
        if _os.path.isfile(_p):
            _cfg = _p
            break
        _q = _os.path.dirname(_d)
        if _q == _d:
            break
        _d = _q
    if _cfg:
        _want = next((l.split("#", 1)[0].strip() for l in open(_cfg, encoding="utf-8")
                      if l.split("#", 1)[0].strip()), "")
        _want = _os.path.expanduser(_want)
        if (_want and _os.access(_want, _os.X_OK)
                and _os.path.realpath(_want) != _os.path.realpath(_sys.executable)):
            _os.environ["KB_INTERP_OK"] = "1"
            _os.execve(_want, [_want, _os.path.abspath(__file__)] + _sys.argv[1:], dict(_os.environ))

import collections, glob, json, os, sys, time

APPLY = "--apply" in sys.argv
if APPLY:
    sys.argv.remove("--apply")
RUN = sys.argv[1] if len(sys.argv) > 1 else time.strftime("%Y%m%d-%H%M")
L7 = "kb/l7/registry/l7.json"
REG = "kb/l4/registry/l4.json"
t0 = time.time()

if not APPLY:
    print("[dry-run] %s 未落盘。" % os.path.basename(os.path.abspath(__file__)))
    print("[dry-run] 会写入：%s（只改 article_no_source 一个块）" % L7)


def rows(p):
    with open(p, encoding="utf-8") as fh:
        return [json.loads(l) for l in fh if l.strip()]


def save_atomic(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=1)
    json.load(open(tmp, encoding="utf-8"))
    os.replace(tmp, path)


# ---------------- 一、现算：台账 + 候选件 ----------------
reg = json.load(open(REG, encoding="utf-8"))
n = reg["numbering"]
iss = n["issued"]
assigned = reg["assignments"]
segments_used = sorted(iss)
reserved = sorted(
    f"{lib_short}-{info.get('block')}"
    for lib_short, segs in (n.get("block_by_library") or {}).items()
    for seg, info in (segs or {}).items()
    if info.get("state") == "reserved_unused"
)
# reserved 的短名直接用段键更可靠（block 号在跨库时不唯一）
reserved = sorted(seg for _lib, segs in (n.get("block_by_library") or {}).items()
                  for seg, info in (segs or {}).items() if info.get("state") == "reserved_unused")

cand_files = sorted(glob.glob("kb/l3/candidates/*.jsonl"))
cand_ids, cand_lines, file_nums = set(), 0, {}
for p in cand_files:
    rs = rows(p)
    if not rs:
        continue
    idk = "rule_id" if "rule_id" in rs[0] else ("case_id" if "case_id" in rs[0] else "clause_id")
    ids = {r[idk] for r in rs}
    cand_ids |= ids
    cand_lines += len(rs)
    file_nums[os.path.basename(p)] = sum(1 for r in rs if r.get("article_no"))
missing = sorted(cand_ids - set(assigned))

canon_rows, canon_nums = 0, set()
for p in glob.glob("kb/l4/canonical/*.jsonl"):
    for r in rows(p):
        canon_rows += 1
        if r.get("article_no"):
            canon_nums.add(r["article_no"])

ranges = {}
for seg in segments_used:
    nums = sorted(int(v.rsplit(".", 1)[1]) for v in iss[seg]["assigned"].values())
    ranges[seg] = [nums[0], nums[-1]]
by_form = collections.Counter()
for seg in segments_used:
    by_form[iss[seg].get("form") or seg] = iss[seg].get("count", len(iss[seg]["assigned"]))
# ★ 保持旧键语义不变：老表把 W-3 与 S-1 合并记作 `sample_case`（157+201=358）。
#   改成按段名分别列会**悄悄改掉消费方的键名**，所以合并回来；E-2 用新键单列并说明构成。
by_form.pop("sample_case_wording_sample", None)
by_form.pop("sample_case_polarity", None)
by_form["sample_case"] = (iss.get("W-3", {}).get("count", 0) + iss.get("S-1", {}).get("count", 0))
if "E-2" in iss:
    by_form.pop("clause", None)
    by_form["external_standard_clause"] = iss["E-2"].get("count", 0)
    by_form_note = ("`sample_case` = W-3(157) + S-1(201)，沿用旧键口径不变；"
                    "`external_standard_clause` = E-2(123)，2026-09-30 新增，"
                    "由 form ∈ {recommendation, substantiation, disclosure, prohibition, scope, mandate} "
                    "六类条款级规则构成（见 ledger block_by_library['external_standard']['E-2'].forms）。")
else:
    by_form_note = "`sample_case` = W-3 + S-1，沿用旧键口径不变。"

print(f"台账：{len(assigned)} 号｜段 {segments_used}｜预留未用 {reserved}")
print(f"候选件：{cand_lines} 行｜唯一 id {len(cand_ids)}｜其中在台账里 {len(cand_ids) - len(missing)}｜缺号 {len(missing)}")
print(f"canonical：{canon_rows} 行 / {len(canon_nums)} 个号，全部在台账：{canon_nums <= set(assigned.values())}")

# ---------------- 二、组装新快照 ----------------
l7 = json.load(open(L7, encoding="utf-8"))
old = l7.get("article_no_source") or {}
new = dict(old)
new.update({
    # ★ 格式约束：l7_gate.py 的 C4 会按 "+" 拆开、剥掉「（…）」说明、再把每段当**字面路径**验存在性
    #   （见 kb/l7/scripts/l7_gate.py:141-165）。所以这里必须一段一个真实路径，
    #   不能写 {a,b}.jsonl 这种花括号展开 —— 那不是路径，C4 会判红（实测踩过一次）。
    "field_lives_in": "kb/l4/canonical/*.jsonl（定稿；**五个形态文件** — wording_entry/wording_revision_pair/sample_case/scoped_clause/clause；rules.jsonl 为空迁移留痕不计）"
                      "+ kb/l3/candidates/rules.jsonl（L4 追加写的带号行）"
                      "+ kb/l3/candidates/external_standard.jsonl（L4 追加写的带号行）"
                      "+ kb/l4/registry/l4.json 的 numbering.issued",
    "scheme_version": n.get("scheme_version", old.get("scheme_version")),
    "total_rules": sum(v["count"] for k, v in iss.items() if k in ("W-1", "W-2", "E-2")),
    "total_rules_note": "规则类形态（wording_entry + wording_revision_pair + external_standard 条款型）的条数。"
                        "★ 2026-09-30 从 509 变 632：新增 kb/l3/candidates/external_standard.jsonl 的 123 条"
                        "外部标准条款级规则（L3 run 20260930-1400），本批落 E-2 段。",
    "total_outputs": len(assigned),
    "total_outputs_note": f"全部带条款号的记录数 = {len(assigned)}（台账 numbering.issued 逐段相加）。"
                          f"其中 canonical 落盘 {canon_rows} 条；E-2 的 123 条仍是**候选**，未晋升定稿"
                          f"（晋升要过人工抽查，不在本批）。",
    "candidate_rows": cand_lines,
    "candidate_rows_note": f"{cand_lines} 行 = 唯一 id {len(cand_ids)} 条，其中 rules/external_standard 两个文件"
                           f"按 L4 的追加约定各存两份（原行 + 带号行），差异只有 article_no 一个字段。"
                           f"各文件自带 article_no 的行数：{file_nums}",
    "by_form": dict(by_form),
    "by_form_note": by_form_note,
    "ranges": ranges,
    "segments_used": segments_used,
    "reserved_unused_segments": reserved,
    "missing_article_no": missing,
    "missing_check": f"逐条核过：候选件 {len(cand_ids)} 个唯一 id 全部能取到条款号，取不到的 {len(missing)} 条。"
                     f"（口径：按**台账 assignments** 核，不按文件自带字段核 —— "
                     f"sample_cases/scoped_clauses 的条目不回写号，号只在台账与 canonical 里。）",
    "read_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    "read_at_previous": old.get("read_at"),
    "refreshed_by": f"kb/.work/l7_article_source_refresh.py {RUN}",
    "refresh_note": "★ 为什么刷新：本块是**读取快照**（见 read_at），上次是 2026-09-24 15:20。"
                    "之后 123 条外部标准条款级规则入库并发号，快照却仍把 E-2 列为 reserved_unused —— "
                    "而 E-2.1…E-2.123 已发出。L7 是引用契约层，留着一张说 E-2 未启用的表会让 E-2.x 被判成无效号。",
})
changed = {k: (old.get(k), v) for k, v in new.items() if old.get(k) != v}
print("\n差异（旧 → 新）：")
for k, (a, b) in changed.items():
    sa, sb = json.dumps(a, ensure_ascii=False), json.dumps(b, ensure_ascii=False)
    print(f"  {k}:\n     {sa[:150]}\n  →  {sb[:150]}")
# 幂等判据 = **实质字段**没变就零写入。read_at / read_at_previous / refreshed_by 每次都会变
# （它们回答「本次读于何时」），拿它们当差异会让本脚本永远「有变化、永远落盘」—— 那不是幂等。
VOLATILE = ("read_at", "read_at_previous", "refreshed_by")
substantive = {k: v for k, v in changed.items() if k not in VOLATILE}
if not substantive:
    print("\n实质字段无差异（只有 read_at/refreshed_by 这类时间戳在动）→ 零写入")
    sys.exit(0)
if not APPLY:
    print("\n[dry-run] 未落盘。加 --apply 才写。")
    sys.exit(0)

backup = f"kb/l7/_backups/l7json-{time.strftime('%Y%m%d-%H%M%S')}"
os.makedirs(backup, exist_ok=True)
import shutil
shutil.copy2(L7, f"{backup}/l7.json.bak")
l7["article_no_source"] = new
save_atomic(L7, l7)
print(f"\n★ 已落盘：{L7}（备份 {backup}/l7.json.bak）｜耗时 {time.time()-t0:.1f}s")
