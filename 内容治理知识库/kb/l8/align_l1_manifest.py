#!/usr/bin/env python3
"""把 kb/l1/manifest_l1.jsonl 对齐到它自己的产物：补记「台账说没有、产物里其实有」的正文。

## 病灶（2026-09-30 量出来的）

L1 台账是**层账**，它声称的 `char_count / status / source_sha256` 必须描述
`kb/l1/*/…json` 产物的真实内容。实测有 105 个资源是反的：

    · 77 个 `status=invalidated` —— 故意作废、产物留档，**这是对的，不动**
    · 28 个 `status=no_scope`   —— 台账说「这条 URL 不在采集范围、没抽到东西」，
      而产物里躺着 51,558 ~ 200,000 字正文（其中 3 条正好 200,000 字，像是被截断）
      → 这是**静默失真的溯源声明**：谁按台账统计 L1 覆盖，就会把这 250 万字算作不存在

28 条里就包含本次 OCR 的扫描书（如 `…wiki_XhrkwZQZ…` 51,558 字）。
根因是后续几批「重抓 / OCR」只改了产物、没有往层账补记一行 —— 和 L0 侧
`kb/l8/emit_l0_manifest_reconcile.py` 修的是同一类病，只是这次在 L1。

## 只补记，不改写

台账是 append-only：本脚本**只追加**一行新记录（带 `previous_l1_status` 交代旧状态），
不修改也不删除任何历史行 —— 历史仍可回放「什么时候被谁补记的」。

## 红线：绝不复活故意作废的资源

`status in (invalidated, retracted)` 一律不碰。给它们补一行 `status=ok`
会让下游（`kb/l8/l2_split_run.py` 的 E 过滤、审计）把这批作废资源当活的用，
那是把一个记账问题升级成一次数据事故。

用法：
    python3 kb/l8/align_l1_manifest.py <RUN>            # 干跑，列清单
    python3 kb/l8/align_l1_manifest.py <RUN> --apply    # 追加补记行
"""
import collections
import json
import os
import sys
import time

APPLY = "--apply" in sys.argv
# ── 落章档（2026-10-01 加，批次4）：`--skill <id>` = 本层**真正执行**的 skill id ──
#   真源 = `kb/l7/registry/layers.yaml` 本层 `skill:`，**由调用者读表后传入**；本脚本不硬编码。
#   落章由**执行本层的进程**（本脚本）写，编排器不得代写（代写即 registry_echo、不能当证据）。
#   ★ 批次4b：**L1 声明两个 skill**（`skill: [kb-ingest-extractor, kb-media-extractor]`），
#   故 `--skill` 支持**重复给出**，按给定顺序收成列表写进落章 —— 只有一个时仍写单值（形状不变）。
#   必须**早于 RUN 解析**摘掉，否则 skill id 会被当成位置参数 run_id。
SKILLS = []
_i = 0
while _i < len(sys.argv):
    _a = sys.argv[_i]
    if _a == "--skill" and _i + 1 < len(sys.argv):
        SKILLS.append(sys.argv[_i + 1]); del sys.argv[_i:_i + 2]; continue
    if _a.startswith("--skill="):
        SKILLS.append(_a.split("=", 1)[1]); del sys.argv[_i]; continue
    _i += 1
SKILL = SKILLS[0] if len(SKILLS) == 1 else None       # 单值形态（其它层沿用）
RUN = next((a for a in sys.argv[1:] if not a.startswith("--")), time.strftime("%Y%m%d-%H%M"))
L1 = "kb/l1"
MAN = f"{L1}/manifest_l1.jsonl"
DEAD = ("invalidated", "retracted")
BASE_KEYS = {"char_count", "extractor_version", "kb_type", "media_count", "observed_at",
             "resource_id", "resource_key", "segment_count", "source_kind", "source_sha256",
             "status", "status_reason", "table_count"}

man_all = [json.loads(l) for l in open(MAN, encoding="utf-8") if l.strip()]
latest = {}
for r in man_all:
    latest[r["resource_id"]] = r

ART = {}
for d in sorted(os.listdir(L1)):
    dp = os.path.join(L1, d)
    if not (os.path.isdir(dp) and d[0].isdigit()):
        continue
    for f in os.listdir(dp):
        if f.endswith(".json"):
            try:
                o = json.load(open(os.path.join(dp, f), encoding="utf-8"))
            except Exception:
                continue
            ART[o.get("resource_id") or f[:-5]] = (os.path.join(dp, f), o)

fix, dead_kept, classes = [], [], collections.Counter()
for rid, (path, art) in sorted(ART.items()):
    m = latest.get(rid)
    if m is None:
        classes["无台账行"] += 1
        continue
    segs = art.get("segments") or []
    segsum = sum(len(s.get("text") or "") for s in segs)
    mchars = m.get("char_count") or 0
    st = m.get("status")
    if segsum <= mchars:
        classes["一致"] += 1
        continue
    if st in DEAD:
        classes["故意作废(不动)"] += 1
        dead_kept.append({"resource_id": rid, "status": st, "ledger_chars": mchars,
                          "artifact_chars": segsum})
        continue
    if m.get("artifact_deleted"):
        classes["台账说产物已删、产物却在(存疑不自动补)"] += 1
        continue
    classes["要补记"] += 1
    fix.append({"resource_id": rid, "resource_key": art.get("resource_key"),
                "kb_type": art.get("kb_type"), "source_kind": art.get("source_kind"),
                "source_sha256": art.get("source_sha256"),
                "extractor_version": art.get("extractor_version"),
                "status": "ok", "observed_at": RUN,
                "status_reason": (f"2026-09-30 L1 层账补记：产物里有 {segsum} 字正文，"
                                  f"而台账记 char_count={mchars} / status={st}"
                                  f"（上一次台账写入 {m.get('observed_at')}）；"
                                  f"本行只补记事实，不改写产物。产物 {path}"),
                "segment_count": len(segs), "char_count": segsum,
                "media_count": art.get("media_count") or 0,
                "table_count": art.get("table_count") or 0,
                "previous_l1_status": st, "previous_char_count": mchars,
                "reconciled_by_run": RUN, "artifact_path": path})

print(f"[{RUN}] L1 层账对齐{'【落盘】' if APPLY else '【干跑】'}")
for k, v in sorted(classes.items(), key=lambda kv: -kv[1]):
    print(f"  {k:<34} {v}")
print(f"  要补记 {len(fix)} 条 / 补记 {sum(r['char_count'] for r in fix)} 字")
if dead_kept:
    print(f"  故意作废、产物留档 {len(dead_kept)} 条（共 {sum(r['artifact_chars'] for r in dead_kept)} 字）——"
          f"状态即事实，不补 status=ok，否则会把这批资源复活成「可用」")
by_st = collections.Counter(r["previous_l1_status"] for r in fix)
print("  待补记的旧状态分布:", dict(by_st))
for r in sorted(fix, key=lambda r: -r["char_count"])[:8]:
    print(f"    {r['char_count']:>8} 字（旧记 {r['previous_char_count']} / {r['previous_l1_status']}）  {r['resource_id'][:64]}")
if APPLY:
    with open(MAN, "a", encoding="utf-8") as fh:
        for r in fix:
            assert BASE_KEYS <= set(r), BASE_KEYS - set(r)
            fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
    print(f"\n  [写入] {MAN} +{len(fix)} 行（行数 {len(man_all)} → {len(man_all) + len(fix)}）")
else:
    print("\n  [干跑] 权威库未落盘（kb/l1/manifest_l1.jsonl 一字未动）。加 --apply 才追加补记行")
# ── 落章 / 台账（2026-10-01 加，批次4；样板 = kb/.work/l4_report.py）────────────
# 两档**都写**台账，只是落点与字段不同：真档 `<RUN>-manifest-reconcile.json`（dry_run=false），
# 预演 `<RUN>-dryrun.json`（dry_run=true / applied=false）。
# 为什么预演也要写：本脚本的干跑档原先在**写任何台账之前**就 sys.exit(0)（旧 :114-116），
# 于是预演在磁盘上零痕迹 ⇒ `skill_invocation_audit.py` 的 E2（逐层落章）对 L1 预演恒红。
# `skill` 只在被 `--skill` 告知时才写 —— 真源是 layers.yaml 本层 `skill:`，由调用者读表传入。
_rec = {"run_id": RUN, "kind": "l1_manifest_reconcile", "classes": dict(classes),
        "reconciled": len(fix), "reconciled_chars": sum(r["char_count"] for r in fix),
        "left_deliberately_retired": len(dead_kept), "rows": fix,
        "retired_kept": dead_kept,
        "dry_run": not APPLY, "applied": bool(APPLY)}
if SKILLS:
    # 单值 → 字符串（形状与其它层一致）；多值（L1 声明两个 skill）→ 按传入顺序的列表。
    _rec["skill"] = SKILLS[0] if len(SKILLS) == 1 else SKILLS
    _rec["skill_source"] = ("--skill 参数（调用者读 layers.yaml 本层 skill: 后传入；"
                            "本脚本不硬编码）"
                            + ("；L1 声明两个 skill，本次按序传入 %d 个" % len(SKILLS)
                               if len(SKILLS) > 1 else ""))
# ── 批次21 · 第1块：落章写 `pipeline_run_id`（编排归属）──────────────────────
# 为什么不改判据而是写这个字段：落章契约（skill_invocation_audit.py:56-61）**早就支持**
# `pipeline_run_id == <编排RUN>` 这一支，`stamp_of()` 也早就实现读它（`:186`），
# 只是**从来没人写** ⇒ E2 在编排 RUN 名下恒查不到落章。
try:
    import sys as _sm_sys, os as _sm_os
    _sm_sys.path.insert(0, _sm_os.path.join(_sm_os.path.dirname(_sm_os.path.dirname(
        _sm_os.path.dirname(_sm_os.path.abspath(__file__)))), "kb", "l7", "scripts"))
    from stamp_meta import stamp_fields as _stamp_fields
    _rec.update(_stamp_fields())
except Exception as _sm_e:
    print("[warn] pipeline_run_id 未写入：%r" % (_sm_e,))
_STAMP = (f"kb/l1/runs/{RUN}-manifest-reconcile.json" if APPLY
          else f"kb/l1/runs/{RUN}-dryrun.json")
os.makedirs("kb/l1/runs", exist_ok=True)
json.dump(_rec, open(_STAMP, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"  [{'apply' if APPLY else 'dry-run'}] 台账 → {_STAMP}"
      + (f"（顶层 skill={_rec['skill']}）" if SKILLS else "（**未传 --skill，无落章**）"))
# ★ 2026-10-01（批次4）修既有措辞缺陷：本行原先**无条件**打印
#   `[报告] kb/l1/runs/<RUN>-manifest-reconcile.json`，而预演档的真实落点是 `-dryrun.json`
#   ⇒ 干跑时 stdout 里出现一个**从不存在的路径**（实测被 subagent 抓到）。
#   改法：打印**实际落点** `_STAMP`，让 stdout 可作证据。
print(f"  [报告] {_STAMP}")
