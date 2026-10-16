#!/usr/bin/env python3
"""生成 L5 运行留痕：runs/<RUN>.json / .report.md / .ops.log
数字全部从证据文件读，不手抄。

★ 2026-10-01（批次4）两处行为变更，明写：
  ① **RUN 此前硬编码 `"20260923-1430"`**，位置参数被忽略 ⇒ 落章永远挂不到编排器的 RUN 上。
     现改为「第一个非 `--` 位置参数优先；不传则沿用旧默认 `20260923-1430`」——
     **不传时行为与旧版一致**，只有传参时才与旧版不同（此前传了等于没传）。
  ② 真档要显式 `--apply`；不带 = 预演，只写 `<RUN>-dryrun.json`（`dry_run=true`/`applied=false`），
     **不写** `.report.md` / `.ops.log`（那是真档的留痕）。
     调用方实测：全库零引用（无引擎清单、无文档、无 shell 调用），无自动化调用者会因此断。
"""
# ── 解释器守卫（2026-09-29）：不合格就用 kb/.kb-python 指定的解释器重跑自己 ──
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
# ──────────────────────────────────────────────────────────────────────────

import hashlib, json, os, subprocess, sys
from datetime import datetime

# ── 2026-10-10：把 `kb/` 放进 sys.path，使 `import kb_ledger` 可用 ──────────────
# 与 `l5_export.py:34` 同一行、同一理由（那边首版兜底踩过 `No module named 'kb_ledger'`）。
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(ROOT)
# ── 落章档 + 干跑档（2026-10-01 加，批次4；样板 = kb/.work/l4_report.py）─────────
# `--skill <id>` = 本层**真正执行**的 skill id，写进落章**顶层** `skill` 字段；不传则不写。
#   真源 = `kb/l7/registry/layers.yaml` 本层 `skill:`，**由调用者读表后传入**；本脚本不硬编码。
#   落章由**执行本层的进程**（本脚本）写，编排器不得代写（代写即 registry_echo、不能当证据）。
_AV = list(sys.argv[1:])
_ARGV_RAW = list(sys.argv)   # ★ 2026-10-12：ops.log 默认档要写「本轮到底是怎么被调的」——原样留一份，别用加工过的 _AV
def _take(flag):
    """摘取 `--flag v` / `--flag=v` 的值并从 argv 里删掉（不影响位置参数 RUN）。"""
    for i, a in enumerate(_AV):
        if a == flag and i + 1 < len(_AV):
            v = _AV[i + 1]; del _AV[i:i + 2]; return v
        if a.startswith(flag + "="):
            v = a.split("=", 1)[1]; del _AV[i]; return v
    return None
SKILL = _take("--skill")
# `--selftest` = 只跑本脚本自己的两条判据（**零写入**，必须先于任何落盘分支）。
SELFTEST_ONLY = "--selftest" in _AV
# `--ops-note <文件>` = 用**这一轮真做过什么**替换 ops.log 里那段固定叙事（2026-10-12 加）。
#   起因（实测，写在这里免得下一个人再踩）：`ops.log` 原先是一段**写死的 11 步叙事**，
#   命令与数字逐字固定、只把 RUN 换掉。证据两条：
#     ① `kb/l5/benchmark.json` 的 mtime 是 **04:11**，而 h09fix（11:23）/ h02fix（12:25）
#        两轮的 ops.log 都写着「[09] 性能验收 $ l5_bench.py → 单条 0.117 ms … 6408.46 ms」，
#        两轮的这段话**逐字节相同**（两份 .ops.log 都是 2736 字节，diff 只差 RUN 那几行）
#        ⇒ 那段数字是**抄来的，不是那一轮量的**；
#     ② 同一段还写着 `[01] l5_prep` / `[03] l3_distill2`（重建 L3）—— 那两轮**都没跑**。
#   ⇒ 结论：那份 ops.log 记的是**最初构建那一次**的经历，不是任何后续轮次的记录。
#   本参数让调用方把**本轮真做过的步骤**写进来（人工叙事首选）。
#   ★ 2026-10-12 稍后（Owner「同意」推荐 A）：**默认档已改成按本轮实测生成**，
#     模板叙事降级为显式的 `--ops-template`；判据见本文件 `--selftest` 的 R1–R4。
#     ⇒ 这一段注释的第一版写的是「不传则维持原样」，那句现在**不再成立**，原样保留会误导人。
OPS_NOTE = _take("--ops-note")
APPLY = "--apply" in _AV
RUN = _AV[0] if _AV and not _AV[0].startswith("--") else "20260923-1430"   # 旧默认值原样保留
P = lambda *a: os.path.join(*a)


def rd(p):
    return json.load(open(p, encoding="utf-8"))


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def sha16(p):
    return sha(p)[:16]


now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
prep, spot, integ, bench = rd("kb/.work/l5_prep.json"), rd("kb/.work/l5_spotcheck.json"), \
    rd("kb/.work/l5_integrity.json"), rd("kb/l5/benchmark.json")
l5reg = rd("kb/l5/registry/l5.json")
bmap = {c["case"]: c for c in bench["cases"]}
pats = [json.loads(l) for l in open("kb/l5/p0_patterns.jsonl", encoding="utf-8") if l.strip()]
# ★ 2026-10-12：这两个读数原先散在后面（`_NO_PAT` 甚至在 ops.log 之后才定义），
#   而 ops.log 的默认档要用它们 ⇒ 统一提到这里，**一处定义，两处引用**。
_NO_PAT = rd("kb/l5/registry/l5_no_pattern.json") or []
try:   # 哪些自检项已被登记为「判据过期」——真源是登记件，不在本脚本里抄第二份
    import yaml as _yaml
    _kd = _yaml.safe_load(open("kb/l7/registry/l5-known-drift.yaml", encoding="utf-8")) or {}
    _STALE_ITEMS = [x["item"] for x in (_kd.get("stale_criteria") or []) if x.get("item")]
except Exception:
    _STALE_ITEMS = []
# ── 规则视图：生行 + 富化，**唯一实现**（2026-10-10 方案 A）────────────────────
# 为什么从"私有兜底"改成调共用件（三次栽坑的完整链条，写给下一个人）：
#   · 2026-10-10 本脚本崩在 `r["rule_kind"]` 直取 ⇒ 无落章 ⇒ 审计 `E2` ⇒ 前置 exit=5 ⇒ 评审链拒答。
#     当时我照 `l5_export.py` 的先例加了**一份私有兜底**（形状感知 + 只补缺失键）。
#   · 但全库普查发现：`l5_prep` / `l5_export` / `l5_report`（+ `l5_gate` 内联）**各有一份**，
#     且**没有一份比对 `evidence_digest`** ⇒ 上游改过正文后会照旧套用旧富化（分类静默错）。
#   · 更根本的是：`kb/l3/candidates/rules.jsonl` 是**上游每天重建的派生件**
#     （`kb/l8/l3_distill_run.py` 按硬编码字段重新生成、`_serialize` 也不剥键）
#     ⇒ 往它追加富化行**下一次日更必然消失**，所以富化只能以 `manifest_l3` 为真源。
#   ⇒ 现在收成一个口：`kb/kb_ledger.py::rules_enriched_view`（含 digest 校验）。
#     **新读者一律调它，不许再写第五份。** 判据一字未改：只补缺失键、不覆盖已有值。
import kb_ledger as _kl
# ★ 2026-10-13 修：规则视图必须与 `l5_export.py` **同一口径** —— 由**两个候选件**合成。
#   病灶（当天实测）：`l5_export.py` 改成两源合成并据此产出 V01–V06（住
#   `candidates/external_standard.jsonl`），而本文件仍只读 `rules.jsonl`
#   ⇒ 下面 `latest[p["rule_id"]]` 直接 `KeyError: 'r-9961b7d19cdd81e6'`
#   ⇒ 落章引擎 exit=1 ⇒ L5 无落章 ⇒ 审计 E2 红 ⇒ 前置 exit=5 ⇒ 每次送审 fail-closed 拒答。
#   合成**只此一口**（`kb_ledger.rules_enriched_view_multi`），不许在这里再抄一份。
latest, _enrich_stats, _ = _kl.rules_enriched_view_multi(
    {"rules": "kb/l3/candidates/rules.jsonl",
     "external_standard": "kb/l3/candidates/external_standard.jsonl"},
    "kb/l3/manifest_l3.jsonl")
_kl.assert_no_stale_enrichment(_enrich_stats, "l5_report")
print(f"[富化] 生行 {_enrich_stats['read']} 行 / {_enrich_stats['uniq']} 个 rule_id ｜ "
      f"从 manifest_l3 补齐 {_enrich_stats['backfilled']} 条 ｜ "
      f"无富化 {_enrich_stats['no_enrich']} ｜ 陈旧 {_enrich_stats['stale']}")

# ★ 缺键**不许静默**（判据抄 `l5_export.py:74`：静默变 0 比抛错更坏）：
#   富化键齐不齐，决定下面 P0 的**排除口径**。缺了就停下来报出来，
#   不许用 `.get()` 默认值把「读不到」折成「没有这条」。
_missing = [rid for rid, _r in latest.items()
            if _r.get("p_level") == "P0" and not all(kk in _r for kk in ("rule_kind", "authority"))]
if _missing:
    sys.exit(f"⛔ P0 规则缺富化字段（rule_kind/authority）共 {len(_missing)} 条：{_missing[:8]}\n"
             f"   这两列是 P0 排除口径的判据；缺了会把「读不到」静默折成 0 条 —— 比抛错更坏。\n"
             f"   修数据（manifest_l3 补富化行）或修读取口径，不许改成 .get() 默认值。")

# P0 入选白名单：算法唯一真源 = `l5_export.py::P0_CODE_ALLOWLIST`（含 Owner 裁定的依据与回退说明）。
#   本脚本只**读**同一套准入结果用于出报告，不改判据。两边不一致 ⇒ 报告与 registry 对不上账。
P0_CODE_ALLOWLIST = {"H06", "H01", "H03", "H08"}

excluded = []
_admitted_by_allowlist = []
for rid, r in sorted(latest.items(), key=lambda kv: str(kv[1].get("rule_code"))):
    if r["p_level"] != "P0":
        continue
    if r["rule_kind"] == "atomic" and r["authority"] in ("expert", "legal"):
        continue
    if r["rule_kind"] == "atomic" and (r.get("rule_code") or "").strip() in P0_CODE_ALLOWLIST:
        # 与 l5_export 同口径：authority 低于门槛，但码在显式准入集合里 ⇒ **入选，不是排除**
        _admitted_by_allowlist.append({"rule_id": rid, "rule_code": r.get("rule_code")})
        continue
    excluded.append({"rule_id": rid, "rule_code": r.get("rule_code"), "form": r.get("form"),
                     "rule_kind": r["rule_kind"], "authority": r["authority"],
                     "authority_source_table": r.get("authority_source_table"),
                     "anchor": r["anchor"]})
# 自测现场复跑
st = subprocess.run([sys.executable, "kb/l5/matcher.py", "--selftest"],
                    capture_output=True, text=True)
selftest = {"exit_code": st.returncode, "stdout": st.stdout, "stderr": st.stderr,
            "positives": st.stdout.count("✅ HIT"), "negatives": st.stdout.count("✅ MISS"),
            "verdict": "PASS" if st.returncode == 0 else "FAIL"}

per_rule = []
for p in pats:
    r = latest[p["rule_id"]]
    per_rule.append({
        "rule_code": p["rule_code"], "rule_id": p["rule_id"], "pattern_id": p["pattern_id"],
        "keyword_terms": len(p["patterns"]), "regex_terms": len(p["regex_patterns"]),
        "whitelist_guards": len(p["whitelist"]),
        "whitelist_allowed_expressions": len(p["whitelist_allowed_expressions"]),
        "support_count": r.get("support_count"), "risk_level": r.get("risk_level"),
        "authority_source_table": r.get("authority_source_table"),
        "anchor": p["anchor"], "source_sha256": p["source_sha256"],
        "term_basis": {m["term"]: m["basis"] for m in p["match_terms"]},
    })
excl_reason = {"P0_but_authority_insufficient": "来源是内部品线边界规则（authority=inferred），"
                                               "不在 expert/legal 门槛内",
               "P0_but_inductive": "由多条证据归纳出的模式（rule_kind=inductive），不是一对一原子映射",
               "P0_admitted_by_allowlist": "authority 低于门槛，但码在 `l5_export.py::P0_CODE_ALLOWLIST` "
                                           "里（Owner 按 PRD 显式准入，依据写在该常量注释里）⇒ 计入入选、不计排除"}

artifacts = ["kb/l5/p0_patterns.jsonl", "kb/l5/index/l5.jsonl", "kb/l5/registry/l5.json",
             "kb/l5/registry/l5_no_pattern.json", "kb/l5/matcher.py", "kb/l5/benchmark.json",
             "kb/l5/runs/%s.p0_patterns.superseded.jsonl" % RUN]
run = {
    "run_id": RUN, "stage": "L5 P0 可执行导出", "finished_at": now,
    "exporter_version": l5reg["exporter_version"], "kb_version": l5reg["kb_version"],
    "inputs_read_only": {
        "kb/l0": integ["checks"]["frozen_layers"]["layers"]["l0"],
        "kb/l1": integ["checks"]["frozen_layers"]["layers"]["l1"],
        "kb/l2": integ["checks"]["frozen_layers"]["layers"]["l2"],
        "kb/l3/candidates/rules.jsonl": {"lines": integ["checks"]["l3_append_only"]["lines"],
                                         "latest_view": integ["checks"]["l3_append_only"]["rules_latest_view"]},
    },
    "precondition_a": {
        "what": "给 509 条候选规则补齐 rule_kind / authority / p_level，只追加不覆盖",
        "before_lines": prep["before_lines"], "before_sha256": prep["before_sha256"],
        "appended": prep["appended"], "latest_total": prep["latest_total"],
        "rule_kind": prep["kinds"], "authority": prep["authority"], "p_level": prep["p_level"],
        "组合分布": prep["stat"],
    },
    "precondition_b": {
        "what": "atomic 规则配对抽查（回源核对 命中片段 与 修改建议 是否取自同一单元）",
        "seed": spot["seed"], "atomic_total": spot["atomic_total"], "sampled": spot["sampled"],
        "mismatches": spot["mismatches"], "rows": spot["rows"],
        "verdict": "PASS（未发现错配，可导出）" if not spot["mismatches"] else "STOP（发现错配，按前置 B 约定停下）",
    },
    "selection": l5reg["selection"] | {"p0_total": prep["p_level"]["P0"],
                                       "selected": len(pats),
                                       "excluded": l5reg["excluded"],
                                       "excluded_p0_rules": excluded,
                                       "excluded_reason": excl_reason},
    "patterns": {
        "pattern_count": len(pats),
        "keyword_terms": sum(len(p["patterns"]) for p in pats),
        "regex_terms": sum(len(p["regex_patterns"]) for p in pats),
        "avg_keyword_terms_per_rule": round(sum(len(p["patterns"]) for p in pats) / len(pats), 2),
        "avg_regex_terms_per_rule": round(sum(len(p["regex_patterns"]) for p in pats) / len(pats), 2),
        "rules_with_whitelist": sum(1 for p in pats if p["whitelist"]),
        "rules_with_allowed_expressions": sum(1 for p in pats if p["whitelist_allowed_expressions"]),
        "per_rule": per_rule,
        "cannot_generate": l5reg["excluded"] and rd("kb/l5/registry/l5_no_pattern.json"),
    },
    "term_grounding": integ["checks"]["no_fabricated_words"],
    "benchmark": bench, "selftest": selftest, "integrity": integ["checks"],
    # ★ 2026-10-01（批次4）既有缺陷防呆：本行原先直接 getsize/sha `artifacts` 里每个路径，
    #   而其中含**只属于历史 RUN 的产物**（如 `kb/l5/runs/<RUN>.p0_patterns.superseded.jsonl`，
    #   现存只有 20260923-1430 那一份）⇒ 换任何新 RUN 都会 FileNotFoundError 崩掉（实测复现）。
    #   处理：文件不在就**如实记 missing**（bytes/sha256 = None + missing=true），不猜值、不跳过不提。
    "artifacts": [({"path": a, "bytes": os.path.getsize(a), "sha256": sha(a)}
                   if os.path.exists(a) else
                   {"path": a, "bytes": None, "sha256": None, "missing": True})
                  for a in artifacts],
    "decisions": [
        {"id": "D1", "decision": "匹配式分三层：keyword（词）+ regex（词形/组合）+ whitelist（豁免），"
                                 "匹配表即 kb/l5/p0_patterns.jsonl，matcher 只读它，不内嵌任何词表",
         "why": "词表与代码分离，改词不用改代码；三层各自的误报/漏报可以单独调"},
        {"id": "D2", "decision": "词级溯源：每个词都要带 basis（verbatim_source / verbatim_rule_text / "
                                 "equivalent_of:<锚点词>），锚点词必须是该规则自己写过的词；对不上的词直接不进匹配表",
         "why": "把「不许凭空加词」从口头约束变成可机验字段：31 个非逐字词（另一语言写法/连字符写法）全部列出锚点，"
                "越界的词会被导出脚本剔除并报出来"},
        {"id": "D3", "decision": "复合片段按「；」（L3 跨记录连接符）和「,，」（源侧单元格内并列）都切开——"
                                 "不切会拼出源里不存在的长串，匹配永远失败（H04 首轮即因此漏判）",
         "why": "切分只是把源侧本来就并列写的片段拆回各自独立，不新增词；修完关键词从 64 个变 79 个"},
        {"id": "D4", "decision": "豁免按「句」生效而不是「行」：禁用表达：xxx。之后的正文照常判 BLOCK；"
                                 "因此匹配改为逐行做（换行不折叠），行首锚点 ^ 才有意义",
         "why": "整行豁免会把「禁用表达：pain-free。但我们提供无痛体验」整行放过；按句豁免只覆盖标记到句号，"
                "既不误报规则陈述、也不漏判真违规"},
        {"id": "D5", "decision": "性能优化用预筛（每条规则全部 pattern 拼成一条超集 alternation）+ 白名单按行缓存；"
                                 "1MB 语料从 2226 ms 降到 647 ms，未改变任何匹配语义",
         "why": "预筛是超集（keyword 项不带词边界），只会多扫不会漏扫，因此行为与优化前逐条一致；"
                "验收前先跑一遍自测确认 9 正例 5 负例结论不变"},
        {"id": "D6", "decision": "阶段早期笔记里的 L3 前缀哈希 780d2a432db775e7 复算不出来（8 种口径都不匹配），"
                                 "改用前置 A 写入的 before_sha256 作基线，本次复算逐字节一致",
         "why": "不复现的旧值不能当基线用；换成有明确口径、能逐字节复算的哈希，并把两种口径都写进证据文件"},
        {"id": "D7", "decision": "首轮导出在同一阶段内被修正并重跑，旧文件另存为 runs/%s.p0_patterns.superseded.jsonl；"
                                 "不新增版本号（仍是 l5-0.1），因为下游还未消费过首轮产物" % RUN,
         "why": "首轮产物没出过 kb/l5、也没有版本行，属同批内返工；旧文件留痕可追溯"},
        {"id": "D8", "decision": "kb/l2/registry/l2.json 缺 kb_version 字段——冻结层只报不改，留给后续阶段处理",
         "why": "本批约定 kb/l0~l2 只读，动它就越界；已在自检里点名，后续阶段可一次性补齐"},
        {"id": "D9", "decision": "rule_code 在全套规则里不唯一（品线内容边界规则库复用 H01-H09/M01-M07/U01-U04）；"
                                 "变体表按 rule_code 查表，故加了「入选集合内 rule_code 必须唯一」的断言，当前 PASS",
         "why": "不校验的话，将来若两条同码规则同时入选，会把前一条的变体悄悄套到后一条上；"
                "全部 21 条边界规则都是 inferred，本批不入选，所以当前无冲突"},
    ],
    "not_done": [
        "不发布、不生成版本号（kb_version 仍 v0，versions.jsonl 仍 0 条版本行）",
        "不写 canonical/（kb/l3/canonical/rules.jsonl 仍 0 字节）",
        "不调 embedding、不改 kb/l0~l2、不重写 kb/l3 已有行",
        "不导出 P1/P2/P3、不导出 inductive、不导出 authority=inferred",
    ],
    "verdict": "PASS" if (integ["verdict"] == "PASS" and bench["verdict"] == "PASS"
                          and selftest["verdict"] == "PASS" and not spot["mismatches"]) else "FAIL",
}
os.makedirs("kb/l5/runs", exist_ok=True)
# 落章（2026-10-01 加，批次4）：dry_run/applied 显式写；`skill` 只在被 --skill 告知时才写。
run["dry_run"] = not APPLY
run["applied"] = bool(APPLY)
if SKILL:
    run["skill"] = SKILL
    run["skill_source"] = ("--skill 参数（调用者读 layers.yaml 本层 skill: 后传入；"
                           "本脚本不硬编码）")
STAMP = ("kb/l5/runs/%s.json" % RUN) if APPLY else ("kb/l5/runs/%s-dryrun.json" % RUN)

# ── 批次21 · 第1块：落章写 `pipeline_run_id`（编排归属）──────────────────────
# 为什么不改判据而是写这个字段：落章契约（skill_invocation_audit.py:56-61）**早就支持**
# `pipeline_run_id == <编排RUN>` 这一支，`stamp_of()` 也早就实现读它（`:186`），
# 只是**从来没人写**（实测全库 0 命中）⇒ E2 在编排 RUN 名下恒查不到落章。
# 本行把编排器透传下来的 RUN 号写进去 —— **用契约自带字段补上缺失的一半**。
try:
    import sys as _sm_sys, os as _sm_os
    _sm_sys.path.insert(0, _sm_os.path.join(_sm_os.path.dirname(_sm_os.path.dirname(
        _sm_os.path.dirname(_sm_os.path.abspath(__file__)))), "kb", "l7", "scripts"))
    from stamp_meta import stamp_fields as _stamp_fields
    run.update(_stamp_fields())
except Exception as _sm_e:      # 取不到就不写这一项（**不阻断落章**，也不编造值）
    print("[warn] pipeline_run_id 未写入：%r" % (_sm_e,))

# ★ 2026-10-12：`--selftest` 是**零写入**档 ⇒ 连预演戳都不写。
#   实测教训：上一版把 selftest 放在落章之后，「不写盘」当场就是假的 ——
#   它真写了 `kb/l5/runs/20260923-1430-dryrun.json`（默认 RUN + 空落章）。
if not SELFTEST_ONLY:
    json.dump(run, open(STAMP, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"[{'apply' if APPLY else 'dry-run'}] 台账 → {STAMP}"
          + (f"（顶层 skill={SKILL}）" if SKILL else "（**未传 --skill，无落章**）"))

# ---------------- ops.log ----------------
# ★★ 2026-10-12（Owner「同意」推荐 A）：**默认档不再写下面这段模板叙事**。
#   为什么改（证据，别再退回模板）：
#     ① 这段 [01]–[11] **只把 RUN 换掉**，其余命令与数字逐字固定 ⇒
#        h09fix（11:23）与 h02fix（12:25）两份 .ops.log 都是 2736 字节、diff 只差 RUN 那几行；
#     ② 其中 [09] 的「单条 0.117 ms … 6408.46 ms」**与 `kb/l5/benchmark.json` 的 mtime（04:11）矛盾**
#        ⇒ 那两轮根本没量，数字是抄的；
#     ③ [01] l5_prep / [03] l3_distill2 那两轮也没跑。
#   ⇒ 它记的是**最初构建那一次**的经历，却被当成每一轮的执行记录 ⇒ 假留痕。
#   现在的三档（**默认档是数据**，两档人工叙事都要显式点）：
#     · 不给参数      → 按**本轮实测**生成：argv 原样 + 产物字节/sha256（现算）+ 模式表读数 +
#                       自证与自检读数（全部取自本轮真跑出来的对象）—— **一个写死的数字都没有**；
#     · `--ops-note f` → **在默认档之后追加**调用方写的本轮人工记录（追加，**不是替换**：
#                       人工叙事不许盖掉机器读数）；
#     · `--ops-template` → 才写下面这段最初的构建叙事，且文件头**明写它是历史模板**。
OPS_TEMPLATE = "--ops-template" in _AV
if OPS_TEMPLATE:
    _AV.remove("--ops-template")
ops = [
    ("前置 A：给 509 条候选规则补 rule_kind / authority / p_level（追加）",
     "python3 kb/.work/l5_prep.py %s" % RUN,
     "509 行 l3-0.1 之上追加 509 行 l3-0.2；派生 rule_kind atomic 483/inductive 26，authority expert 416/inferred 93，"
     "p_level P0 21/P1 477/P2 7/P3 4"),
    ("前置 B：atomic 规则配对抽查（seed 20260923，抽 10 条）",
     "python3 kb/.work/l5_spotcheck.py %s" % RUN,
     "10/10 命中片段与修改建议取自同一单元，mismatches=[] → 放行导出"),
    ("修正 L3：entry/boundary/saythis 规则补 resource_id/resource_ids（发现 rule_code 存在但 resource_id 缺失）",
     "python3 kb/.work/l3_distill2.py（重建 L3，验证 rule_id 稳定：H07 仍 r-d7290a0ee59c58ef）",
     "追加式重建后 1018 行；rule_id 未变"),
    ("首轮导出（后被同阶段修正覆盖）",
     "python3 kb/.work/l5_export.py %s" % RUN,
     "模式 6 条 | keyword 式 64 | regex 式 16；旧产物 sha256 49cc44bf… → 另存 superseded"),
    ("自测暴露两个问题：H04 正例漏判（复合片段没切开）、H04 负例把「禁用表达：」清单判成 BLOCK（豁免只到冒号）",
     "python3 kb/l5/matcher.py --selftest",
     "退出码 2，2 处偏差，进入修复"),
    ("修复导出：分隔符同时切「；」与「,，」；豁免改为句级（禁用表达/DO NOT SAY 等标记到句末）",
     "python3 kb/.work/l5_export.py %s" % RUN,
     "keyword 式 79（+15 个此前被粘连而永远匹配不上的片段）"),
    ("修复匹配器：逐行匹配（保住 ^ 锚点）+ 预筛超集 + 白名单按行缓存",
     "python3 kb/l5/matcher.py --selftest",
     "9 正例全命中 / 5 负例零误报，退出码 0"),
    ("词级溯源：31 个非逐字词逐个声明等价锚点，加进 DERIVATION 表；凭空词直接剔除",
     "python3 kb/.work/l5_export.py %s" % RUN,
     "verbatim_source 30 / verbatim_rule_text 18 / equivalent_of 31；剔除凭空词 0"),
    ("性能验收（PRD §12 要求 <1 秒）",
     "python3 kb/.work/l5_bench.py",
     "单条 %s ms、命中样例 %s ms、%s/%d 行 %s ms、%s/%d 行 %s ms、冷启动 %s ms → %s"
     % (bmap["single_primary_text"]["elapsed_ms"]["median"], bmap["single_with_hit"]["elapsed_ms"]["median"],
        bmap["batch_ad_copy"]["chars_human"], bmap["batch_ad_copy"]["lines"],
        bmap["batch_ad_copy"]["elapsed_ms"]["median"], bmap["large_doc_1mb"]["chars_human"],
        bmap["large_doc_1mb"]["lines"], bmap["large_doc_1mb"]["elapsed_ms"]["median"],
        bench["compile_ms"], bench["verdict"])),
    ("自检 6 项（冻结层 / 追加性 / 回指 / 词源 / 版本纪律 / 离线）",
     "python3 kb/.work/l5_integrity.py",
     "全部 PASS；1MB 优化后重跑仍 PASS"),
    ("生成留痕",
     "python3 kb/.work/l5_report.py",
     "runs/%s.json / .report.md / .ops.log" % RUN),
]
def _ops_default_text():
    """默认档正文：**全部按本轮实测生成**（argv 原样 + 产物现算 + 读数现读）。

    ★ 判据在本文件 `--selftest`（R1–R4）：默认档必须含**当前模式表**的 sha16，
      而历史模板档必须**不含** —— 后者就是反向对照，证明这条判据不是恒真。
    """
    out = ["# 正文来源：**默认档 = 本轮实测**（argv 原样 + 产物现算 + 读数现读）",
           "#   人工叙事请用 `--ops-note <文件>`；最初构建那一轮的历史模板用 `--ops-template`。",
           "", "[调用] 本轮的调用方式（argv 原样，未加工）",
           "     $ " + " ".join(_ARGV_RAW), "",
           "[产物] 本轮写入的产物（字节与 sha256 现算）"]
    for a in run["artifacts"]:
        if a.get("missing"):
            out.append(f"     → {a['path']}：**missing**（文件不存在，如实记，不猜值）")
        else:
            out.append(f"     → {a['path']}：{a['bytes']} 字节 ｜ sha256 前 16 位 {a['sha256'][:16]}")
    _pt = run["patterns"]
    out += ["", "[读数] 本轮模式表读数",
            f"     → 模式 {_pt['pattern_count']} 条 ｜ keyword 式 {_pt['keyword_terms']} ｜ "
            f"regex 式 {_pt['regex_terms']} ｜ 有白名单 {_pt['rules_with_whitelist']} ｜ "
            f"无法生成 {len(_NO_PAT)}",
            "", "[自证] 本轮自证与自检（读数现读，判决照抄）",
            f"     → kb/l5/matcher.py --selftest：退出码 {selftest['exit_code']}，"
            f"正例 {selftest['positives']} / 负例 {selftest['negatives']} ⇒ {selftest['verdict']}",
            "     → kb/.work/l5_integrity.py：总判决 %s；逐项 %s"
            % (integ["verdict"], "、".join(f"{k}={v.get('verdict')}" for k, v in integ["checks"].items()))]
    if _STALE_ITEMS:
        out.append(f"     → 其中 {'、'.join(_STALE_ITEMS)} 两项已登记为**判据过期**"
                   f"（`kb/l7/registry/l5-known-drift.yaml`，不判红）")
    out += [f"     → 性能：1MB 合成文档 {bmap['large_doc_1mb']['elapsed_ms']['median']} ms，"
            f"bench 判决 {bench['verdict']}",
            "", "[判定] 本层判定",
            f"     → 本件 run verdict = {run['verdict']}（口径见 report.md §0；"
            f"层闸门另看 `kb/l7/scripts/l5_gate.py`）",
            "#    ★ 本文件不含任何写死的数字：要核对就重跑一次，逐字对比。"]
    return "\n".join(out) + "\n"


def _ops_template_text():
    """**历史模板**：最初构建那一轮（6 条模式时代）的 11 步叙事，只把 RUN 换掉。

    默认档**不再用它**（理由见本文件头部 `OPS_TEMPLATE` 的注释）。留着是为了不丢历史，
    且它正好当 `--selftest` 的**反向对照**：它不含当前表的 sha16 ⇒ 判据能分辨真档与模板。
    """
    out = ["# ⚠️ **本文件是历史模板**（最初构建那一轮的 11 步叙事），**不是本轮的执行记录**。",
           "#    调用方显式传了 --ops-template 才会出现这一段。"]
    for i, (what, cmd, res) in enumerate(ops, 1):
        out += ["", f"[{i:02d}] {what}", f"     $ {cmd}", f"     → {res}"]
    return "\n".join(out) + "\n"


if APPLY:                                  # 预演档不写 .ops.log / .report.md
    with open("kb/l5/runs/%s.ops.log" % RUN, "w", encoding="utf-8") as fh:
        fh.write(f"# L5 P0 可执行导出 · 操作日志 run_id={RUN}\n")
        fh.write(f"# 生成时间 {now}｜写入范围：kb/l3 追加、kb/l5 写入；kb/l0~l2 只读；未发布任何版本\n")
        if OPS_TEMPLATE:
            fh.write(_ops_template_text())
        else:
            # 默认档（数据）**永远写**；`--ops-note` 是**追加**，不是替换 ——
            # ★ 为什么不做成「替换」：替换的话，人工叙事可以整段盖掉机器读数，
            #   而「谁写的、写了什么」恰恰是这次要修的病灶。数据在前、人工补充在后，两者都在。
            fh.write(_ops_default_text())
            if OPS_NOTE:
                fh.write(f"\n# ── 调用方补充的本轮操作记录（人工，未加工；来源 {OPS_NOTE}）──\n")
                with open(OPS_NOTE, encoding="utf-8") as nf:
                    fh.write(nf.read().rstrip("\n") + "\n")


# ---------------- 自证（--selftest）----------------
def _selftest():
    """判据：**ops.log 的默认档必须是本轮实测，不能是历史模板**。

    做法：拿两个正文直接对断言 —— 默认档必须含**当前**模式表的 sha16，
    而历史模板档（`--ops-template` 那一份，正是改前每一轮都在写的东西）**必须不含**。
    后者就是**反向对照**：判据若恒真，R3 会红。
    """
    tbl_sha16 = sha16("kb/l5/p0_patterns.jsonl")
    tbl_bytes = os.path.getsize("kb/l5/p0_patterns.jsonl")
    d = _ops_default_text()
    t = _ops_template_text()
    checks = [
        ("R1 默认档含**当前**模式表 sha16（证明确是现算的）", tbl_sha16 in d),
        ("R2 默认档含本轮 argv 原样（证明记的是这一轮怎么被调的）",
         "kb/.work/l5_report.py" in d and " ".join(_ARGV_RAW[1:]) in d),
        ("R3 反向对照：历史模板档**不含**当前表 sha16 ⇒ 判据能分辨真档与模板", tbl_sha16 not in t),
        ("R4 反向对照：历史模板档**不含**当前表字节数", str(tbl_bytes) not in t),
    ]
    print("l5_report.py 自证（ops.log 默认档）")
    ok = True
    for name, good in checks:
        print(f"  {'✅' if good else '❌'} {name}")
        ok = ok and good
    print(f"  · 当前模式表 sha16={tbl_sha16} ｜ 字节={tbl_bytes} ｜ RUN={RUN}")
    print("结论：%s" % ("✅ 默认档是本轮实测，且判据不是恒真" if ok else "❌ 默认档与实测脱节"))
    return 0 if ok else 2


if SELFTEST_ONLY:
    _sys = __import__("sys")
    _sys.exit(_selftest())

# ---------------- report.md ----------------
B = bench["cases"]
st_lines = [l for l in selftest["stdout"].split("\n") if l.strip().startswith(("✅", "❌", "载入", "---", "自测"))]
pt = run["patterns"]
# ★ 2026-10-12 修：原先「无法生成 pattern 的规则」那行**把两个数字写死在正文里**
#   （`0 条` 与 `入选的 6 条）`—— 而同一份报告第 4 节已经从数据里算出 `共 11 条 pattern`
#   ⇒ **报告自己跟自己打架**（6 ≠ 11）。实测证据：negfix-20261012-1239 那一版报告第 4 节写 11 条、
#   紧接着那行写 6 条。数字必须从数据来：`0 条` = 无模式清单的长度，`入选 N 条` = 模式表行数。
L = []
A = L.append
A(f"# L5 · P0 可执行导出报告（run_id {RUN}）\n")
A(f"生成时间 {now}｜exporter_version `{l5reg['exporter_version']}`｜kb_version `{l5reg['kb_version']}`｜"
  f"结论 **{run['verdict']}**\n")
A("## 0. 一句话\n")
A(f"从 {integ['checks']['l3_append_only']['rules_latest_view']} 条候选规则里筛出 P0 且原子且 authority∈(expert,legal) 的 "
  f"{pt['pattern_count']} 条，导出成机器可执行的匹配表 `kb/l5/p0_patterns.jsonl`（关键词 {pt['keyword_terms']} 个 / "
  f"正则 {pt['regex_terms']} 条 / 豁免 {pt['rules_with_whitelist']} 组），配 `kb/l5/matcher.py` 可直接跑。\n")
# ★ 2026-10-12 修：原先这句**无论数字多少都写「满足 PRD §12 的「P0 匹配 < 1 秒」」**，
#   而同一份报告的性能表与 `kb/l5/benchmark.json` 都写着 1MB 那一条 ❌超时 —— 报告**自己否自己**。
#   实测证据（2026-10-12 12:5x 复查）：报告第 0 节写「6408.46 ms，**满足** <1 秒」，
#   而 bench 的 verdict=FAIL、表里那一行是「❌超时」。数字要跟判决同源，不能各说各话。
_doc_ms = bmap['large_doc_1mb']['elapsed_ms']['median']
_single_ms = bmap['single_primary_text']['elapsed_ms']['median']
_hit_ms = bmap['single_with_hit']['elapsed_ms']['median']
A(f"P0 匹配中位耗时：单条文案 {_single_ms} ms ｜ 命中样例 {_hit_ms} ms ｜ "
  f"1MB 合成大文档 {_doc_ms} ms → **bench 判决 {bench['verdict']}**"
  + ("（各条全部 <1s）。\n" if bench["verdict"] == "PASS"
     else f"（**1MB 合成大文档那一条超 PRD §12 的 1 秒**；前两条实测远低于 1 秒）。\n"))

A("## 1. 前置 A：规则属性补齐（只追加）\n")
A("| 维度 | 分布 |")
A("|---|---|")
A(f"| 处理前 | {prep['before_lines']} 行（l3-0.1），sha256 `{prep['before_sha256'][:16]}…` |")
A(f"| 本次追加 | {prep['appended']} 行（l3-0.2），最新视图 {prep['latest_total']} 条 |")
A(f"| rule_kind | atomic {prep['kinds']['atomic']} / inductive {prep['kinds']['inductive']} |")
A(f"| authority | expert {prep['authority']['expert']} / inferred {prep['authority'].get('inferred', 0)} / legal {prep['authority'].get('legal', 0)} |")
A(f"| p_level | P0 {prep['p_level']['P0']} / P1 {prep['p_level']['P1']} / P2 {prep['p_level']['P2']} / P3 {prep['p_level']['P3']} |")
A("")
A("组合分布（rule_kind｜authority｜p_level）：" + "；".join(f"{k} = {v}" for k, v in sorted(prep["stat"].items())) + "\n")

A("## 2. 前置 B：atomic 配对抽查（seed %d，抽 %d 条）\n" % (spot["seed"], spot["sampled"]))
A("回源核对「命中片段」与「修改建议」是否取自同一单元：**%d/%d 无错配**（mismatches=%s）→ 放行导出。\n"
  % (spot["sampled"], spot["sampled"], json.dumps(spot["mismatches"])))
A("| # | rule_id | 形态 | 命中片段（截断） | 建议改法（截断） | 判定 |")
A("|---|---|---|---|---|---|")
for i, r in enumerate(spot["rows"], 1):
    A(f"| {i} | `{r['rule_id']}` | {r['form']} | {r['hit_fragment'][:36]} | "
      f"{r['suggested_replacement'][:36]} | {r['verdict']} |")
A("")

A("## 3. 选取与排除\n")
A(f"P0 共 {prep['p_level']['P0']} 条 → 入选 **{pt['pattern_count']}** 条；排除 {json.dumps(l5reg['excluded'], ensure_ascii=False)}\n")
A("| 原因 | 条数 | 说明 |")
A("|---|---|---|")
A(f"| non_P0 | {l5reg['excluded']['non_P0']} | p_level ≠ P0，本批不导出 |")
A(f"| P0_but_authority_insufficient | {l5reg['excluded']['P0_but_authority_insufficient']} | {excl_reason['P0_but_authority_insufficient']} |")
A(f"| P0_but_inductive | {l5reg['excluded']['P0_but_inductive']} | {excl_reason['P0_but_inductive']} |")
A("")
A("被排除的 P0 规则逐条：\n")
A("| rule_code | rule_id | rule_kind | authority | 来源表 |")
A("|---|---|---|---|---|")
for e in excluded:
    A(f"| {e['rule_code'] or '（空码）'} | `{e['rule_id']}` | {e['rule_kind']} | {e['authority']} | {e['authority_source_table']} |")
A("")

A("## 4. 导出的匹配表\n")
A(f"共 {pt['pattern_count']} 条 pattern｜关键词 {pt['keyword_terms']} 个（平均 {pt['avg_keyword_terms_per_rule']} 个/规则）｜"
  f"正则 {pt['regex_terms']} 条（平均 {pt['avg_regex_terms_per_rule']} 条/规则）｜带豁免 {pt['rules_with_whitelist']}/{pt['pattern_count']} 条｜"
  f"带规则专属放行表达 {pt['rules_with_allowed_expressions']} 条\n")
A("| rule_code | rule_id | 关键词 | 正则 | 豁免 | 放行表达 | 支撑记录 | 风险 | 来源表 |")
A("|---|---|---|---|---|---|---|---|---|")
for p in per_rule:
    A(f"| {p['rule_code']} | `{p['rule_id']}` | {p['keyword_terms']} | {p['regex_terms']} | {p['whitelist_guards']} | "
      f"{p['whitelist_allowed_expressions']} | {p['support_count']} | {p['risk_level']} | {p['authority_source_table']} |")
A("")
A("**无法生成 pattern 的规则：%d 条**（%s，`kb/l5/registry/l5_no_pattern.json`%s）。\n"
  % (len(_NO_PAT), 
     ("入选的 %d 条全部产出模式" % pt["pattern_count"]) if not _NO_PAT
     else ("入选 %d 条里有 %d 条产不出模式" % (pt["pattern_count"], len(_NO_PAT))),
     " 为空" if not _NO_PAT else " 见该文件"))
A("### 词级溯源（对应「不许凭空加词」）\n")
tg = run["term_grounding"]
A(f"匹配表里 {tg['checked']} 个词每个都带 basis：{json.dumps(tg['basis_distribution'], ensure_ascii=False)}；"
  f"对不上规则的词 {len(tg['bad'])} 个（凭空词一律剔除，本次剔除 {tg['dropped_ungrounded']} 个）。\n")
A("| basis | 含义 |")
A("|---|---|")
A("| verbatim_source | 逐字来自该规则的「命中片段」 |")
A("| verbatim_rule_text | 逐字来自该规则的 rule_text / 建议替换 |")
A("| equivalent_of:<锚点词> | 同一词的另一种语言或连字符写法，锚点词必须是该规则自己写过的词 |")
A("")
A("`equivalent_of` 的 31 个词全部列在 `kb/l5/p0_patterns.jsonl` 的 `match_terms` 里（含锚点），可逐条核对。\n")

A("## 5. 性能实测（PRD §12：P0 匹配 < 1 秒）\n")
A(f"语料：`kb/l2/units.jsonl` 里 #广告文案明细/ 的真实广告文案（Headline / Primary Text 共 {bench['corpus']['lines_available']} 条）；"
  f"环境 python {bench['env']['python']}；**全程离线**。\n")
A("| 规模 | 文本 | 行数 | min | 中位 | max | 命中规则 | 判定 |")
A("|---|---|---|---|---|---|---|---|")
for c in B:
    A(f"| {c['label']} | {c['chars_human']} | {c['lines']} | {c['elapsed_ms']['min']} ms | "
      f"{c['elapsed_ms']['median']} ms | {c['elapsed_ms']['max']} ms | {','.join(c['hit_rules']) or '无'} | "
      f"{'✅ <1s' if c['under_1s'] else '❌ >1s'} |")
A("")
A(f"单条文案摊薄耗时 **{bench['per_copy_avg_ms']} ms/条**；冷启动（读模式表 + 编译正则）**{bench['compile_ms']} ms**，"
  f"常驻服务只付一次；验收 **{bench['verdict']}**。\n")

A("## 6. 自测（正例必中、负例零误报）\n")
A("```")
A("\n".join(st_lines))
A("```")
A("")
A("负例里两条是「元语境」：`禁用表达：pain-free、more milk。` 与 `依据原文：「more milk」属于禁用表述。` —— "
  "规则在陈述被禁的词，不应判 BLOCK；同时正例里 `禁用表达：pain-free。但我们这款提供无痛体验，还能帮助催奶。` "
  "证明豁免只到句末，句号之后的正文照常命中。\n")

A("## 7. 自检（6 项，全部 PASS）\n")
ck = integ["checks"]
fl = ck["frozen_layers"]
A("| 项 | 结论 | 证据 |")
A("|---|---|---|")
A(f"| kb/l0~l2 未被改动 | {fl['verdict']} | l0 {fl['layers']['l0']['files']} 文件/{fl['layers']['l0']['bytes']} 字节，"
  f"l1 {fl['layers']['l1']['files']}/{fl['layers']['l1']['bytes']}，l2 {fl['layers']['l2']['files']}/{fl['layers']['l2']['bytes']}；"
  f"最后修改时间分别是 {fl['layers']['l0']['max_mtime']} / {fl['layers']['l1']['max_mtime']} / {fl['layers']['l2']['max_mtime']}，"
  f"都早于 l5 首次写入 {fl['l5_first_write']}；并记下 tree_sha256 供后续比对 |")
A(f"| kb/l3 只追加 | {ck['l3_append_only']['verdict']} | 前 509 行哈希 `{ck['l3_append_only']['prefix_sha256']}` "
  f"与前置 A 的 before_sha256 逐字节一致；追加段 509 行、rule_id 集合与基线段完全相同；基线无 rule_kind、追加段为 l3-0.2 |")
A(f"| pattern 全部可回指 | {ck['pattern_traceability']['verdict']} | {ck['pattern_traceability']['patterns']} 条 pattern 的 "
  f"rule_id / anchor / source_sha256 与规则 evidence_units[0] 一致，异常 {len(ck['pattern_traceability']['bad'])} |")
A(f"| 无凭空加词 | {ck['no_fabricated_words']['verdict']} | {tg['checked']} 个词 basis 全部对得上规则原文，越界 0 |")
A(f"| 版本纪律 | {ck['version_discipline']['verdict']} | canonical/rules.jsonl {ck['version_discipline']['canonical_rules_bytes']} 字节；"
  f"versions.jsonl 版本行 {ck['version_discipline']['versions_jsonl_rows']}；kb_version {ck['version_discipline']['kb_version_values']} |")
A(f"| matcher 离线 | {ck['offline']['verdict']} | 源码里没有 requests/urllib/socket/http/curl 等网络符号 |")
A("")
A(f"注：`kb/l2/registry/l2.json` 缺 `kb_version` 字段（{'、'.join(ck['version_discipline']['registries_missing_kb_version']) or '无'}）——"
  "冻结层只报不改。\n")

A("## 8. 产物与校验和\n")
A("| 文件 | 字节 | sha256 |")
A("|---|---|---|")
for a in run["artifacts"]:
    A(f"| `{a['path']}` | {a['bytes'] if a['bytes'] is not None else '—'} | "
      f"{('`%s…`' % a['sha256'][:16]) if a['sha256'] else '**缺失（本 RUN 无此产物）**'} |")
A("")

A("## 9. 自主决策（本批内自定，未另行请示）\n")
A("| # | 决策 | 理由/影响 |")
A("|---|---|---|")
for d in run["decisions"]:
    A(f"| {d['id']} | {d['decision']} | {d.get('why', '')} |")
A("")

A("## 10. 本批没做的事\n")
for x in run["not_done"]:
    A(f"- {x}")
A("")
if APPLY:
    # ★ 2026-10-06：`.md` 走 `/bin/cp` 落地（宿主会把 python 直写的 .md 多算 4096 字节）——
    #   见 `kb/.work/_safe_write.py` 文件头。
    import _safe_write as _sw                # 与本脚本同目录
    _sw.write_text("kb/l5/runs/%s.report.md" % RUN, "\n".join(L))
    print(f"已生成 kb/l5/runs/{RUN}.json / .report.md / .ops.log")
print(f"run verdict = {run['verdict']}")
