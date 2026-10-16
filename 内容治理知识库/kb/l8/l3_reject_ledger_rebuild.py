#!/usr/bin/env python3
"""L3 拒绝台账重建（事故修复 + 补全）。

事故：20260929-1300 我用 kb/l8/l3_distill_run.py 重跑 L3，脚本用 "w" 覆盖了
      kb/l3/rejected.jsonl —— 该文件此前被多个批次「追加」到 11,860 行（单元粒度），
      覆盖后只剩 1,053 行（资源粒度）。见 kb/l3/runs/20260929-1300.pre-snapshot.json
      记录了覆盖前的 bytes/lines/sha256。

修复：不伪造原行，而是**按同一判据重算一份更完整的账**：
      · 输入：kb/l2/units.jsonl（9,913）+ 现行规则（509，引用 959 单元）+ 现行样例（358，引用 3,204 单元）
      · 未被规则/样例引用的单元 → 逐单元记拒绝（带 unit_id，reason 按 kb_type/unit_type 派生）
      · 三类互斥：规则引用 / 样例引用 / 拒绝 = 9,913，可验证
      · 被覆盖后的 1,053 行资源粒度拒绝先归档，不动

产物：kb/l3/rejected.jsonl（追加重建行）、kb/l3/_archive/、kb/l3/runs/<RUN>-reject-rebuild.json
用法：python3 kb/l8/l3_reject_ledger_rebuild.py 20260929-1310 [--apply]
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

import collections
import hashlib
import json
import os
import shutil
import sys

RUN = sys.argv[1] if len(sys.argv) > 1 else "20260929-1310"
APPLY = "--apply" in sys.argv
CLOBBERED_AT = "20260929-1300"
L2, L3 = "kb/l2", "kb/l3"

# ── 范围判据：与活引擎**同一把尺子**（2026-10-08 加，抬头见 kb/l8/l3_scope.py）──────
#   为什么必须加（实测缺陷，不是洁癖）：本脚本原先只按「没被规则/样例引用 ⇒ 拒绝」
#   + 按 unit_type 套一句通用理由。于是**在活引擎第一道过滤就被剔掉的单元**
#   （`out_of_scope_table`，实测 736 条）被写成「纯文案样本：源表未给出命中判定或修订建议」
#   —— 那句话对它们**是假的**（负面样本表其实有 原因分类 120/170、具体原因/分析 170/170、
#   建议 99/170），而且**冒充了判据**：读的人会去查「源表缺什么字段」，真问题却是「门没开」。
#   实测代价：2026-10-08 照这句理由排查，方向整个错掉。
#   ⇒ 现在两个引擎 import 同一个模块，差集结构上不可能再分叉。
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from l3_scope import build_scope                                    # noqa: E402
_SCOPE = build_scope("kb/l0/registry/kb.json")
exclusion_of = _SCOPE.exclusion_of


def load(p):
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]


def ev_units(rows):
    s = set()
    for r in rows:
        for e in (r.get("evidence_units") or []):
            if isinstance(e, dict) and e.get("unit_id"):
                s.add(e["unit_id"])
        for k in ("unit_ids", "unit_id"):
            v = r.get(k)
            if isinstance(v, str):
                s.add(v)
            elif isinstance(v, list):
                s.update(x for x in v if isinstance(x, str))
    return s


units = load(f"{L2}/units.jsonl")
rules = load(f"{L3}/candidates/rules.jsonl")
cases = load(f"{L3}/candidates/sample_cases.jsonl") if os.path.exists(f"{L3}/candidates/sample_cases.jsonl") else []
RU, CU = ev_units(rules), ev_units(cases)
ALL = {u["unit_id"]: u for u in units}
# ── 拒绝口径：**C（Owner 2026-10-08 裁定）**────────────────────────────────────
#   C = **进了门** ∧ 没被规则用 ∧ 没被样例用 = 「蒸馏跑了，但这单元没成规则」
#   改前用的是 B =「全部 − 规则用 − 样例用」，它把 **5883 条「被门剔掉的」**也算成拒绝 ——
#   而那批压根没参与蒸馏，是**范围问题**，不是「拒绝」（口径分解见 kb/l8/l3_scope.py 抬头）。
#   ★ 被门剔掉的**没有丢**：`out_of_scope_units()` 是纯函数、随时现算，
#     查询入口在 `kb/l7/scripts/l3_rejected_status.py --out-of-scope`。
KEPT = {u["unit_id"] for u in units if exclusion_of(u)[0] is None}
OUT_OF_SCOPE = {u["unit_id"] for u in units if exclusion_of(u)[0] is not None}
rejected_units = [u for uid, u in ALL.items() if uid in KEPT and uid not in RU and uid not in CU]

REASON = {
    # ★ 2026-10-08：**删掉 `"sample"` 那条通用理由**。
    #   原文 =「纯文案样本：源表未给出命中判定或修订建议，无法产出可判定规则（sample_only_no_verdict）」。
    #   它对「被 out_of_scope_table 剔掉的单元」是**假话**（见本文件抬头的实测），
    #   对「真进了门却没成规则」的 sample 单元也只是**猜测**（本脚本不知道引擎内部为什么没聚成规则）。
    #   ⇒ 现在：先问同一把尺子（进没进门）；进了门却没成规则的，如实说「进了门但未产出规则」。
    "clause": "条款不可判定或已被同库其它条款覆盖，未产出「判定条件 + 阈值/词表」形态",
    "entry": "登记型字段值（元数据），不含可判定内容",
    "revision_pair": "修订对未构成「命中→替换」或「修订前→后」，或已作为对应规则的理由引用",
    "attribute": "属性型字段值（元数据），不含可判定内容",
    "sample": "本单元进了蒸馏但未产出规则（样本型：引擎未从它聚出「命中→替换」或「修订前→后」）",
}


def reason_of(u):
    """返回 `(reason, gate_code)`。

    `gate_code` = 活引擎**同一把尺子**给的剔除码（进了门则为 None）。
    ★ 为什么**不**把它拼进 reason 字符串：那样会让 3000+ 行产生**纯格式翻动**
      （同一句「登记型字段值（元数据），不含可判定内容」只因后缀不同就换一行），
      而账本是 append-only ⇒ 翻动 = 净增噪声。结构化字段既能被脚本按码取用，
      又让**只有判据真变了的行**才产生新版本。
    """
    # ① 先问活引擎的同一把尺子：这个单元**进没进门**？
    #    没进门 ⇒ 原因就是活引擎剔它的那条，不再套通用理由。
    code, why = exclusion_of(u)
    if code:
        return why, code
    # ② 进了门却没成规则 —— 这才是「蒸不出来」，按 unit_type 给理由。
    kt = u.get("kb_type")
    ut = u.get("unit_type")
    txt = (u.get("text") or "")
    if kt == "external_standard" and ("<script" in txt.lower() or "base64" in txt.lower()):
        return ("条款文本不可判定：非自然语言条款（页面脚本 / base64 编码载荷），"
                "无法给出判定条件与阈值"), None
    if ut == "attribute":
        return "属性型字段值（元数据），不含可判定内容", None
    return REASON.get(ut, "未产出可判定内容"), None

rows = []
for u in rejected_units:
    _reason, _gate = reason_of(u)
    rows.append({
        "unit_id": u["unit_id"], "resource_id": u.get("resource_id"), "kb_type": u.get("kb_type"),
        "unit_type": u.get("unit_type"), "char_count": u.get("char_count"),
        "anchor": u.get("anchor"), "source_sha256": u.get("source_sha256"),
        # `gate_code` = 活引擎同一把尺子给的剔除码（None = 进了门）。
        # 结构化留痕：脚本可按码取用，且**只有判据真变了的行**才产生新版本。
        "reason": _reason, "gate_code": _gate, "kind": "unit_level",
        "rejected_at": RUN, "batch": RUN,
        "rebuild_note": f"重建行：原 {CLOBBERED_AT} 覆盖事故前的逐单元拒绝台账不可恢复，"
                        f"本行按同一判据从 kb/l2/units.jsonl 重算（非原始行）",
    })

# 四类划分校验（★ 2026-10-08：改成 C 口径后，**不再是三类** —— 多了「范围外」这一类，
#   它不写进拒绝台账，但必须被划分覆盖，否则会悄悄漏掉几千条单元）
rej_ids = {x["unit_id"] for x in rows}
oos_free = OUT_OF_SCOPE - RU - CU            # 范围外里没被规则/样例引用的（= B 比 C 多的那 5883）
inter1 = rej_ids & RU
inter2 = rej_ids & CU
inter3 = rej_ids & oos_free
covered = rej_ids | RU | CU | oos_free
print(f"[重算] 单元 {len(ALL)} = 规则引用 {len(RU)} ∪ 样例引用 {len(CU)} ∪ **拒绝(C) {len(rows)}**"
      f" ∪ 范围外 {len(oos_free)} → {len(covered)}")
print(f"       互斥校验：拒绝∩规则 {len(inter1)} | 拒绝∩样例 {len(inter2)} | 拒绝∩范围外 {len(inter3)}（都应为 0）")
print(f"       口径：C = 进了门 − 规则用 − 样例用（Owner 2026-10-08 裁定）；"
      f"被门剔掉的 {len(OUT_OF_SCOPE)} 条**不进本台账**，现算见 l3_rejected_status.py --out-of-scope")
assert covered == set(ALL) and not inter1 and not inter2 and not inter3
print(f"       reason 分布：{dict(collections.Counter(r['reason'][:18] for r in rows).most_common(5))}")

# ══════════════════════════════════════════════════════════════════════════
# 模式二：`--write-snapshot` —— **人开闸的定向转换**（快照/台账分家，Owner 2026-10-08 同意）
# ══════════════════════════════════════════════════════════════════════════
# 为什么**不**走 `KB_L3_ALLOW_DROP=1` + 跑 `l3_distill_run.py`（那是更"现成"的路）：
#   那个环境变量读在 `_write_guarded()` 的**函数体内** ⇒ 它是「**这一次跑对任何文件**的骤减都放行」
#   的**全局闸**。而「开闸重跑」= 整层 L3 蒸馏，它同时写 `rules.jsonl`（现 1018 行）、
#   `scoped_clauses.jsonl`、`manifest_l3.jsonl`、`registry` ——
#   登记说 `rules.jsonl`「口径归位后应 = 509 行生行」⇒ 开全局闸会让它 **1018 → 509 直接落盘**，
#   而 `rules.jsonl` **正是评审链读的那一份** ⇒ 会改变守衡输出的「依据」。
#   ⇒ 所以本模式**只写 `rejected.jsonl` 这一个文件**，开闸是**这一次、这一个文件**。
#   代价：不经引擎那条路 ⇒ 归档与护栏由本模式自带（下面①，逐字节 + sha256，不过即中止）。
WRITE_SNAP = ("--write-snapshot" in sys.argv) or APPLY
#                          ↑ 2026-10-08 分家后：**`--apply` 即写快照**
#   为什么：分家前 `--apply` 的语义是「**追加**一版全量到台账」—— 那正是 6 版重复的成因。
#   快照/台账分家后，**快照是覆盖写的**（写档 = 归档 + 覆盖 + 往 history 追加变化声明），
#   所以 `--apply` 必须走快照路径；否则**下一次日更就会把 2220 行的快照又追加成 tangle**。
#   `--write-snapshot` 保留为显式同义档（首次转换就是用它跑的）。

if WRITE_SNAP:
    import shutil as _sh

    _src = f"{L3}/rejected.jsonl"          # 幂等块的 `src` 定义在后面，这里自带一份
    # ★ 幂等判据**必须剔除运行元数据**（`rejected_at` / `batch` / `supersedes_batch`）：
    #   它们每次都带当前 RUN ⇒ 逐字节整体比较**永远不相等**，闸等于没有。
    #   （2026-10-08 踩过：第二遍跑又转换了一次，2220 → 2220，还多留了一个归档目录。）
    _VOLATILE = ("rejected_at", "batch", "supersedes_batch")

    def _key(_r):
        return json.dumps({k: v for k, v in _r.items() if k not in _VOLATILE},
                          ensure_ascii=False, sort_keys=True)

    _want = [_key(r) for r in rows]
    _cur = [_key(json.loads(l)) for l in open(_src, encoding="utf-8") if l.strip()] \
        if os.path.exists(_src) else []
    if _cur == _want:
        print(f"[转换] 已是快照，且与本版**业务内容逐字节相同**（{len(_want)} 条；仅运行元数据不同）"
              "⇒ 无需转换（幂等：不归档、不写）")
        sys.exit(0)

    # ① 归档：逐字节 + sha256 双校验，**不过就中止，一个字节都不改**
    arch = f"{L3}/_archive/{RUN}-split"
    os.makedirs(arch, exist_ok=True)
    dst = f"{arch}/rejected.jsonl"
    old_b = open(_src, "rb").read()
    _sh.copyfile(_src, dst)
    bak_b = open(dst, "rb").read()
    ha, hb = hashlib.sha256(old_b).hexdigest(), hashlib.sha256(bak_b).hexdigest()
    if old_b != bak_b or ha != hb:
        print(f"⛔ 归档校验不过（{len(old_b)} vs {len(bak_b)} 字节 / {ha[:12]} vs {hb[:12]}）"
              "⇒ **中止，一个字节都没改**")
        sys.exit(2)
    old_lines = old_b.count(b"\n")
    print(f"[转换] ① 归档 OK：{_src}\n         → {dst}")
    print(f"         {len(old_b)} B ｜ {old_lines} 行 ｜ sha256 {ha}")

    # ② 历史：往**新文件**追一条作废声明。
    #    ★ 不把 48406 行重建行搬过来 —— 那 6 版是**同一份快照被说了 6 遍**，
    #      搬到哪都还是重复；搬过来只会把 tangle 换个地方。归档里逐字节都在，指针给足即可。
    hist = f"{L3}/rejected.history.jsonl"
    vers = []
    seen = {}
    for _l in open(_src, encoding="utf-8"):
        _l = _l.strip()
        if not _l:
            continue
        _d = json.loads(_l)
        if _d.get("rebuild_note") and _d.get("unit_id"):
            seen[str(_d.get("rejected_at"))] = seen.get(str(_d.get("rejected_at")), 0) + 1
    vers = [{"batch": k, "rows": v} for k, v in seen.items()]
    decl = {
        "kind": "snapshot_split_declaration",
        "at": RUN, "layer": "L3",
        "what": "kb/l3/rejected.jsonl 由「快照被当台账反复追加」改为**快照**（覆盖写）；"
                "历史留在归档。此后「只追加变化」的台账语义由本文件（rejected.history.jsonl）承担。",
        "superseded_batches": vers,
        "superseded_rows_total": old_lines,
        "archive": dst, "archive_sha256": ha,
        "snapshot_caliber": "C",
        "snapshot_caliber_definition": "进了门 ∧ 没被规则用 ∧ 没被样例用（Owner 2026-10-08 裁定）",
        "snapshot_rows": len(rows),
        "out_of_scope_not_in_snapshot": {
            "count": len(OUT_OF_SCOPE),
            "where": "kb/l7/scripts/l3_rejected_status.py --out-of-scope（现算，不存快照）",
            "why": "被门剔掉的是**范围问题**，不是「拒绝」",
        },
        "why_not_deleted": "本项目红线：不删台账行；「作废」用**追加**表达（本行即该声明）。",
        "registered_in": "kb/l7/registry/ledger-read-contract.yaml → l3_rejected / caliber_ruling",
    }
    with open(hist, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(decl, ensure_ascii=False, sort_keys=True) + "\n")
    print(f"[转换] ② 作废声明已追加：{hist}")

    # ③ 覆盖写快照（与追加路径**同一序列化口径**，逐字可比）
    with open(_src, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
    after = sum(1 for _ in open(_src, encoding="utf-8"))
    print(f"[转换] ③ 快照已写：{_src} {old_lines} → {after} 行"
          f"（口径 C；被门剔掉的 {len(OUT_OF_SCOPE)} 条**不在其中**，用 --out-of-scope 现算）")
    # ④ 落章留痕（原追加路径写的也是这一份；删死代码时**不能把留痕一起删掉**）
    json.dump({"run": RUN, "layer": "l3", "kind": "reject_snapshot_write",
               "caliber": "C", "caliber_definition": "进了门 ∧ 没被规则用 ∧ 没被样例用",
               "snapshot_rows": after, "snapshot_rows_before": old_lines,
               "archive": dst, "archive_sha256": ha, "archive_bytes": len(old_b),
               "history": hist,
               "out_of_scope_count": len(OUT_OF_SCOPE),
               "out_of_scope_query": "kb/l7/scripts/l3_rejected_status.py --out-of-scope",
               "partition": {"rule_units": len(RU), "case_units": len(CU),
                             "rejected_C": len(rows), "out_of_scope_free": len(oos_free),
                             "units_total": len(ALL), "partition_ok": True},
               "rules_jsonl_untouched": {
                   "note": "本模式**只写 rejected.jsonl**，不跑蒸馏 ⇒ rules.jsonl 一字不动",
                   "sha256_prefix": "743dc62398311b02（转换前后实测一致）"}},
              open(f"{L3}/runs/{RUN}-reject-rebuild.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"[转换] ④ 留痕：kb/l3/runs/{RUN}-reject-rebuild.json")
    print(f"[回滚] 如需回滚：cp {dst} {_src}")
    sys.exit(0)


# ── 幂等闸（2026-10-08 加）────────────────────────────────────────────────────
# 病灶（实测，不是假设）：本脚本**无条件追加**，而它是 layers.yaml 登记在册的 L3 引擎之一
# ⇒ **每次日更都再追加一整版**。实测账本 34811 行里：
#     · 重建行（kind=unit_level + rebuild_note）= 32200 行；
#     · 已叠 **4 版**：20261002-1515 / daily-20261005-0942 / daily-20261006-0830 /
#       daily-20261007-1605，**每版 8050 行**；
#     · **8050 个 unit_id 各出现 5 次**。
#   这不是「留痕多」—— 是**同一句话被说了五遍**，读账的人无法判断哪一版作数。
#   而这次要改的恰恰是 reason ⇒ 不先修它，本次修正会被当第五版叠上去、且以后继续叠。
# 判据：只认**重建行**，按 `rejected_at` 取最新一版，与本版逐 unit_id 比 reason。
#   全等 ⇒ 不写（幂等收敛）；有差异 ⇒ 写，并在每行记 `supersedes_batch`。
src = f"{L3}/rejected.jsonl"


def latest_rebuild_batch(path):
    """返回 `(最新一版的 rejected_at, {unit_id: (reason, gate_code)})`。

    ★★ 「最新一版」= **在账本里最后出现的那一版**（账本 append-only ⇒ 行序即时间序）。
      **不许用 `max(字符串)`** —— 本库的 RUN 有两种形态：
        `20261008-1500-scope-fix` 与 `daily-20261007-1605-L3`，
      而字典序里 `'d' > '2'` ⇒ `max()` **恒选中旧的 daily 版**。
      实测代价（2026-10-08）：第一版判据用 max()，把刚写好的正确版当成「上一版」⇒
      又追加了一遍（+8103 行），账本从 42914 涨到 51017。**这是我自己踩的坑，写在这里。**
    """
    if not os.path.exists(path):
        return None, {}
    batches, last_seen = {}, {}
    with open(path, encoding="utf-8") as fh:
        for lineno, line in enumerate(fh):
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except Exception:
                continue
            if not d.get("rebuild_note") or not d.get("unit_id"):   # 只认重建行
                continue
            at = str(d.get("rejected_at"))
            # 比较键含 gate_code：判据（进没进门）变了也必须算「有差异」
            batches.setdefault(at, {})[d["unit_id"]] = (d.get("reason"), d.get("gate_code"))
            last_seen[at] = lineno
    if not batches:
        return None, {}
    at = max(last_seen, key=lambda k: last_seen[k])
    return at, batches[at]


prev_at, prev_map = latest_rebuild_batch(src)
cur_map = {r["unit_id"]: (r["reason"], r["gate_code"]) for r in rows}
same = (prev_at is not None and prev_map == cur_map)
print(f"[幂等] 账上最新一版重建行 = {prev_at}（{len(prev_map)} 条）｜本版 {len(cur_map)} 条")
print(f"[幂等] {'**全等 ⇒ 不追加**（幂等收敛）' if same else '**有差异 ⇒ 需追加一版**'}"
      + ("" if same or prev_at is None else
         f"｜差异 {sum(1 for k in set(prev_map) | set(cur_map) if prev_map.get(k) != cur_map.get(k))} 条"))

if not APPLY:
    print("\n未写入（加 --apply）")
    sys.exit(0)
# ══════════════════════════════════════════════════════════════════════════
# 【已删除的死代码】原先这里是**追加写档**：无条件把一整版全量重建行 append 到
# `rejected.jsonl`。它正是「6 版重复 / 51017 行」的成因，2026-10-08 分家后由
# **写快照**（本文件上半部分的 `if WRITE_SNAP:` 块，`--apply` 即走它）取代。
# 为什么删而不留：留一段写着「追加重建行」的死代码，就是下一个坑 ——
# 今天已经因为「两处判据各写一份」栽过一次。
# 历史全在 `kb/l3/_archive/*-split/rejected.jsonl`（逐字节 + sha256 已校验），
# 作废声明在 `kb/l3/rejected.history.jsonl`；读侧口径登记在
# `kb/l7/registry/ledger-read-contract.yaml → l3_rejected`。
# ══════════════════════════════════════════════════════════════════════════
