# 12 行恢复件 · 重建依据来源清单

- 恢复件：`kb/.work/batch11/recovered_ledger_rows.jsonl`
- 条数：**12**（`registered` 4 + `retracted` 8）
- sha256：`bafe907bb9db9fbccc6d8a9130b3b423beb085ef4780863ac41558522820fdb4`
- **性质：重建件，不是原字节。** 全库检索确认 12 行无字节级副本存活。

## 来源①：两份 baseline —— 「归档曾存在」的时间证据（只含路径+尺寸，不含内容）

| baseline | 时刻 | 命中的键 | 尺寸 |
|---|---|---|---|
| `kb/.work/batch6_baseline.json` | 2026-09-24T12:03:00 | `kb/l0/9_未归类/local_file__review-case-img-{1..4}.json` | 802 / 808 / 800 / 803 B |
| `kb/.work/batch8_baseline.json` | 12:36 | `kb/l0/_archive/eval-material-excluded-20260924-1210/local_file__review-case-img-{1..4}.json` | 802 / 808 / 800 / 803 B |

→ 12:03 时文件在 `l0/9_未归类/`，12:36 时已在 `_archive/eval-material-excluded-20260924-1210/`，
**证明归档目录当时存在**；14:28–14:35 之间随写者的 pass 灭失。
两份 baseline 都**只有 `{mtime, size}` 骨架、不含内容** —— 所以不能靠它们做字节级恢复。

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
