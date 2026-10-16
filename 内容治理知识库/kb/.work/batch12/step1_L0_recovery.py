#!/usr/bin/env python3
"""batch11/12 §5：L0 治理复位。只追加、只修引用，不删任何行、不回填被删行。"""
import json, os, hashlib, collections, time

RUN = "20260924-1512"; L0 = "kb/l0"; REG = f"{L0}/registry/kb.json"
def h(p): return hashlib.sha256(open(p, "rb").read()).hexdigest()
def atomic(p, txt):
    t = p + ".tmp"; open(t, "w", encoding="utf-8").write(txt)
    open(t, encoding="utf-8").read(); os.replace(t, p)
def savejson(p, o):
    atomic(p, json.dumps(o, ensure_ascii=False, indent=1) + "\n")

MAN = f"{L0}/manifest.jsonl"
before_rows = sum(1 for l in open(MAN, encoding="utf-8") if l.strip())
before_sha = h(MAN)
print(f"台账开工：{before_rows} 行  {before_sha[:16]}")

# ---------- §5.2.1 恢复件的重建依据来源清单 ----------
REC = "kb/.work/batch11/recovered_ledger_rows.jsonl"
rec_sha = h(REC); rec_n = sum(1 for l in open(REC, encoding="utf-8") if l.strip())
src_md = f"""# 12 行恢复件 · 重建依据来源清单

- 恢复件：`{REC}`
- 条数：**{rec_n}**（`registered` 4 + `retracted` 8）
- sha256：`{rec_sha}`
- **性质：重建件，不是原字节。** 全库检索确认 12 行无字节级副本存活。

## 来源①：两份 baseline —— 「归档曾存在」的时间证据（只含路径+尺寸，不含内容）

| baseline | 时刻 | 命中的键 | 尺寸 |
|---|---|---|---|
| `kb/.work/batch6_baseline.json` | 2026-09-24T12:03:00 | `kb/l0/9_未归类/local_file__review-case-img-{{1..4}}.json` | 802 / 808 / 800 / 803 B |
| `kb/.work/batch8_baseline.json` | 12:36 | `kb/l0/_archive/eval-material-excluded-20260924-1210/local_file__review-case-img-{{1..4}}.json` | 802 / 808 / 800 / 803 B |

→ 12:03 时文件在 `l0/9_未归类/`，12:36 时已在 `_archive/eval-material-excluded-20260924-1210/`，
**证明归档目录当时存在**；14:28–14:35 之间随写者的 pass 灭失。
两份 baseline 都**只有 `{{mtime, size}}` 骨架、不含内容** —— 所以不能靠它们做字节级恢复。

## 来源②：`kb/.work/batch5/run3_external.json` 的 `rows[].source_sha256`

给出 4 个 `local_file` 资源的文件指纹（`894c0edc…` / `353ecf9e…` / `b7dfecfa…` / `5f28249b…`），
用于填 `registered` 行的 `sha256`。

## 来源③：`kb/.work/batch6_run.py:57-70` 的建行配方

`retracted` 行的 `status` / `status_reason` / `retract_reason_detail` / `retracted_at` /
`observed_at` / `moved_to` / `downstream_invalidated` / `scanner_version` 逐字段取自这段代码。

## 来源④（补充）：`kb/l1/manifest_l1.jsonl:2963-2966`

4 条 `invalidated` 行的 `resource_key` / `source_kind` / `kb_type` / `char_count` /
`upstream_status` / `upstream_status_reason`，用于交叉核对 `registered` 行的 `kb_type=unknown`。

## 无法恢复（逐行 `_unrecoverable` 已列）

`sha256_input` / `sha256_state` / `path` / `depth` / `matched_rule` / `scanner_version` /
`revision` / `dup_of` / `last_seen_observed_at` / `moved_from`。
"""
atomic("kb/.work/batch12/recovered_ledger_rows.sources.md", src_md)
print("§5.2.1 来源清单 → kb/.work/batch12/recovered_ledger_rows.sources.md")

# ---------- §5.2.3 悬空引用：重建归档目录 ----------
ARCH = "kb/l0/_archive/eval-material-excluded-20260924-1210"
recs = [json.loads(l) for l in open(REC, encoding="utf-8") if l.strip()]
os.makedirs(ARCH, exist_ok=True)
made = []
for r in recs:
    if r["status"] != "retracted" or r.get("_pass_index") != 1:
        continue
    rid = r["resource_id"]
    body = {k: r.get(k) for k in ("resource_key", "source_kind", "kb_type", "sha256",
                                  "status", "status_reason", "retracted_at", "observed_at",
                                  "moved_to", "downstream_invalidated")}
    body["_reconstruction"] = {
        "is_original_bytes": False,
        "reconstructed_at_run": RUN,
        "why": "原归档文件于 2026-09-24 14:28–14:35 之间被 run 20260924-1115 灭失；按 batch6_run.py:57-70 的建行配方重建",
        "sources": ["kb/.work/batch11/recovered_ledger_rows.jsonl",
                    "kb/.work/batch12/recovered_ledger_rows.sources.md",
                    "kb/.work/batch8_baseline.json（证明归档曾存在：size 802/808/800/803 B）"],
        "needs_owner_confirmation": True}
    atomic(f"{ARCH}/{rid}.json", json.dumps(body, ensure_ascii=False, indent=1) + "\n")
    made.append(f"{ARCH}/{rid}.json")
print(f"§5.2.3 归档目录已重建：{len(made)} 个文件")
for m in made: print("   ", m, os.path.getsize(m), "B")

# ---------- §5.2.2 台账追加一行留痕 ----------
audit_row = {
  "change": "ledger_rows_unauthorizedly_deleted",
  "resource_key": "audit:l0-ledger-integrity:20260924-1512",
  "source_kind": None, "status": "audit_note", "depth": 0,
  "table_name": None, "table_id": None, "record_id": None, "field_name": None, "field_id": None,
  "entry_url": None, "path": None, "kb_type": "unknown", "matched_rule": None,
  "sha256": None, "sha256_input": None, "sha256_state": None, "revision": None,
  "dup_of": None, "moved_from": None, "downstream_invalidated": True,
  "observed_at": RUN, "scanner_version": "0.7",
  "status_reason": ("L0 台账 append-only 被破：run 20260924-1115 于 2026-09-24T14:35:46 把 "
                    "l0/manifest.jsonl 从 3663 行删到 3651 行（−12 行）。被删的是 4 张评测案图"
                    "（local:review-case:img-1..4）的 registered 4 行 + retracted 8 行，"
                    "即「补登记 → 按用户裁决撤回」这段审计痕迹。本行只做留痕，**不回填原行**"
                    "（回填会让台账的时间线说谎）。"),
  "audit": {
    "defect": "ledger_append_only_broken",
    "rows_before": 3663, "rows_after": 3651, "rows_deleted": 12,
    "deleted_at": "2026-09-24T14:35:46", "actor_run_id": "20260924-1115",
    "deleted_rows_composition": {"registered": 4, "retracted": 8},
    "affected_resources": [r["resource_key"] for r in recs if r["status"] == "registered"],
    "recovery_artifact": REC, "recovery_artifact_rows": rec_n,
    "recovery_artifact_sha256": rec_sha,
    "recovery_is_reconstruction_not_original_bytes": True,
    "recovery_evidence_list": "kb/.work/batch12/recovered_ledger_rows.sources.md",
    "backfill_policy": "原行不得回填",
    "backfill_reason": "回填会让台账的时间线说谎：这 12 行的 observed_at 是 20260924-1115/1210，"
                       "若在 20260924-1512 之后插回原位，后续任何按 observed_at 排序的审计都会误判",
    "detected_by_run": "20260924-1432（首次发现 index 被写）→ 20260924-1443（确认删行）→ 本批处置"
  }
}
with open(MAN, "a", encoding="utf-8") as fh:
    fh.write(json.dumps(audit_row, ensure_ascii=False, sort_keys=True) + "\n")
after_rows = sum(1 for l in open(MAN, encoding="utf-8") if l.strip())
print(f"§5.2.2 台账追加 1 行：{before_rows} → {after_rows} 行（只增不减：{after_rows == before_rows+1}）")

# ---------- §5.2.3 registry：archived_to 注解 ----------
reg = json.load(open(REG, encoding="utf-8"))
sk = reg["source_kind_retired"][0]
sk["archived_to_reconstructed"] = True
sk["archived_to_note"] = ("该目录连同其中 4 个归档 json 于 2026-09-24 14:28–14:35 之间被 "
                          "run 20260924-1115 灭失（batch8_baseline 12:36 时仍列有这 4 个文件，"
                          "size 802/808/800/803 B）。run 20260924-1512 按 batch6_run.py:57-70 的配方"
                          "**重建**目录与文件，使 archived_to 可解析。**重建件不是原字节。**")
sk["archive_lost_window"] = {"from": "2026-09-24T12:36:00", "to": "2026-09-24T14:35:46",
                             "actor_run_id": "20260924-1115",
                             "evidence": "kb/.work/batch8_baseline.json 的键里列有这 4 个文件"}
sk["archive_reconstructed_from"] = ["kb/.work/batch11/recovered_ledger_rows.jsonl",
                                    "kb/.work/batch12/recovered_ledger_rows.sources.md"]
sk["needs_owner_confirmation"] = True

# ---------- §5.2.4 修 changes[6] 的悬空键引用 ----------
fixed = None
for i, c in enumerate(reg["changes"]):
    ks = c.get("keys") or []
    if "source_kind_note" in ks:
        c["keys"] = [k for k in ks if k != "source_kind_note"]
        c["keys_note"] = ("原 keys 含 source_kind_note。该键由 run 20260924-1115 于 14:28 写入、"
                          "又于 14:35:46 由其自行删除，键已不存在。run 20260924-1512 把该键从本条 keys 中"
                          "**移出**（而不是补回那个来路不明的键），并在此留痕。")
        fixed = i
print(f"§5.2.4 changes[{fixed}] 的 source_kind_note 引用已移出（未补回该键）")

# ---------- §5.2.5 L0↔L1 分叉结论 ----------
reg["ledger_divergence_conclusion"] = {
  "defined_at": RUN, "long_lived": True,
  "subject": "local:review-case:img-1..4（4 张评测对照报告案图）的 L0 台账 vs L1 台账",
  "observed": {"l0_manifest_rows_for_these_keys": 0, "l1_manifest_rows_for_these_keys": 8,
               "l1_composition": "extracted 4（run 20260924-1200）+ invalidated 4（run 20260924-1210）"},
  "verdict": "**L0 无这些行是对的；L1 保留的 8 行是历史留痕，也是对的。两边不是矛盾，是「权威口径」与「审计留痕」的分工。**",
  "basis": [
    "口径一（源侧投影）：L0 的定义是「L0 == 源侧投影」（见 source_kind_retired[0].reason）。"
    "local_file 不是源侧入口，4 张案图已按用户裁决（user_decision_20260924）移出知识库，"
    "所以 L0 台账里**不应该有这 4 个 key 的有效行**。写者删掉它们，在「该不该在库里」这个方向上是对的。",
    "口径二（append-only）：台账是 append-only 的审计面。撤回决定的痕迹必须留。"
    "正确做法是「保留 12 行不动 + 追加行说明已撤出索引」，而不是「删行」。"
    "写者用删达成目的，破坏了审计面 —— 这一点是错的，已由本批的 ledger_rows_unauthorizedly_deleted 行留痕。",
    "L1 侧：kb/l1/README.md 未声明「L1 == 源侧投影」；L1 台账的主键是"
    "(resource_id, extractor_version, source_sha256)，它的 invalidated 行写明"
    "「L1 产物保留供审计但不再是有效内容」—— 这正是审计面该有的样子，无需改动。"
  ],
  "action": "只登记结论，不改数据：L0 不回填 12 行；L1 8 行保留原样。",
  "residual": "l1/index/l1.jsonl 里这 4 个 key 的单元行已在 run 20260924-1115 的 14:35:46 pass 中移除"
              "（index 回到 14782），与「L1 台账保留、索引不含」的处理一致，无残留。"
}
reg["ledger_audit"] = {
  "defined_at": RUN,
  "why": "本批往 l0/manifest.jsonl 追加了一行非资源行（change=ledger_rows_unauthorizedly_deleted）。"
         "为免它变成一个来路不明的枚举，在此登记。",
  "row_resource_key_prefix": "audit:",
  "row_status_enum_added": ["audit_note"],
  "row_schema": "与资源行同 schema，但 source_kind/sha256/path/table_* 等资源字段为 null；"
                "审计细节放 audit{} 子对象。",
  "consumer_note": "按 (resource_key, observed_at) 取最新行的消费者不受影响：audit 行的 key 前缀是 audit:，"
                   "不在任何 bitable:/url:/wiki: 资源命名空间内；kb_l0_scan_lib.ledger_keys_of_table "
                   "按 `bitable:<table_id>:` 前缀过滤，天然排除本行。",
  "pointer_resolution_policy": "「路径型引用可解析」分两类判："
    "①**live 指针**（registry 里指向当前仍在用的位置，如 archived_to / excluded_scope.archived_to）—— 必须存在；"
    "②**历史指针**（台账行里的 moved_to / path，只描述「当时的去向」）—— 若该 key 的**最新行**状态不是"
    "gone/retracted，则该历史指针视为**已被后续行取代**，不算悬空。"
    "实测：gone 202/202 解析成功；restored 15/15 解析成功；retracted 16 行中 15 行的 moved_to 指向"
    "rulelib 归档，而这 15 个 key 的最新行均为 restored（文件已回到 kb/l0/1_外部标准库/）→ 属类②，非悬空；"
    "剩下 1 行解析成功。"
}
savejson(REG, reg)
print("§5.2.3/4/5 registry 已更新")
print("  source_kind_retired[0].archived_to 可解析:", os.path.exists(sk["archived_to"]))
print("  顶层键数:", len(reg))
