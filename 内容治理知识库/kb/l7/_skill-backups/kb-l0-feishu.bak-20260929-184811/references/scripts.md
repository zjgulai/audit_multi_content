---
title: Scripts（脚本清单与用法）
doc_type: reference
module: kb-l0-feishu
topic: scripts
status: stable
created: 2026-09-29
updated: 2026-09-29
owner: self
source: human+ai
---

# 脚本清单与用法

**读取条件**：执行具体阶段前读对应小节。脚本全部位于库内 `kb/l8/`（`<KB>` = 库根）。

## 约定

- 统一 run_id：`RUN=<YYYYMMDD-HHMM>`；产物落 `kb/l8/runs/<RUN>-*.json`。
- 带 `--apply` 的脚本**先不带参数跑一遍**（预演），拿到差异再决定。
- 全部从库根执行，避免相对路径错位。

## 阶段 1 · 记录层核对

```bash
python3 kb/l8/align_l0_feishu.py $RUN          # 只读全表逐字段对账
```

- 身份：默认 bot；`L8_AS=user` 可切用户身份。
- 产物：`kb/l8/runs/$RUN-l0-align.json`，看 `summary`：
  `same / only_feishu / only_l0 / changed` + `record_files_not_registered_total`。

## 阶段 2 · 结构层核对

```bash
python3 kb/l8/align_l0_schema.py $RUN [--apply]
```

- 比 `field_id ↔ 名 ↔ 类型`，刷新 `kb/l0/registry/kb.json` 的 `schema_snapshots`。

## 阶段 3 · 认领与归档

```bash
python3 kb/l8/reconcile_l0_feishu.py $RUN
```

- 处理"表整批替换"（新记录认领 + 旧记录归档）与 `材料收集` 只留「审核状态 = 通过」。

## 阶段 4 · 台账补齐

```bash
python3 kb/l8/emit_l0_manifest_reconcile.py $RUN [--apply]
```

- **反向复现校验**：先用一条既有 `manifest.jsonl` 行跑一遍 sha256 计算，确认口径一致再批量写。

## 阶段 5 · 非记录资源核验

```bash
python3 kb/l8/verify_l0_nonrecord.py  $RUN [--apply]
python3 kb/l8/verify_l0_nonrecord2.py $RUN [--apply]
python3 kb/l8/refresh_l0_drifted.py   $RUN [--apply]
python3 kb/l8/store_l0_attachments.py $RUN [--apply]
python3 kb/l8/sync_l0_changed_records.py        # 变更记录同步
```

## 阶段 6 · 图片 OCR

```bash
python3 kb/l8/ocr_attachments.py $RUN
python3 kb/l8/apply_ocr_to_l1.py <OCR_RUN> <L1_RUN> [--apply]
python3 kb/l8/verify_l0_nonrecord2.py $RUN [--apply]   # 复核归档 docx 与 OCR 覆盖
```

- 缓存闸门：`vision-jxa-2.0`；新旧图 `file_token` 交集为 0 → 缓存作废。

## 阶段 7 · 视频

```bash
# 字段级非空筛选（留证）→ 有则下载字节 → 提字幕 + 抽关键帧 → 关键帧走 OCR → 文本落 L1
```

## 阶段 8 · 链接

```bash
python3 kb/l8/drill_links_2levels.py  $RUN
python3 kb/l8/fill_drill_failures.py  $RUN [--apply]
python3 kb/l8/verify_l0_urls.py       $RUN
python3 kb/l8/verify_urls_headless.py $RUN
python3 kb/l8/verify_urls_shingles.py $RUN                       # 词 8-gram 双向重叠
python3 kb/l8/recrawl_all_urls.py     $RUN [--apply] [--limit N]
python3 kb/l8/recrawl_jsnoise_urls.py $RUN [--apply]
```

## 阶段 9 · 下游重跑（不动 L0）

```bash
python3 kb/l8/extract_l1_new_resources.py $RUN [--apply]
python3 kb/l8/l2_split_run.py             $RUN
python3 kb/l8/l3_distill_run.py           <L3_RUN>
python3 kb/l8/l3_reject_ledger_rebuild.py <L3_RUN> [--apply]
python3 kb/l1/index/rebuild_l1_index.py
```

> `l3_distill_run.py` 以 `w` 模式覆盖 `rejected.jsonl`——跑前归档现状，跑后重建逐单元台账。

## 阶段 10 · 收口核验

```bash
python3 kb/l8/workflow_check.py $RUN
python3 kb/l8/roundtrip_check.py $RUN
python3 kb/l8/projection_reconcile.py
python3 kb/l8/envelope_census.py
python3 kb/l8/build_view.py --run $RUN
```

## 辅助脚本

| 脚本 | 用途 |
|---|---|
| `kb/l8/projection_reconcile.py` | `kb/view` 投影 vs 权威库漂移 |
| `kb/l8/envelope_census.py` | 活路径信封普查 |
| `kb/l8/workflow_check.py` | 流程一致性检查 |
| `kb/l8/roundtrip_check.py` | 往返一致性检查 |

## lark-cli 常用命令

```bash
export PATH="$HOME/.dsh/bin:$PATH"
lark-cli auth status --profile dsh-kb
lark-cli base +url-resolve --url '<URL>' --as bot --profile dsh-kb
lark-cli base +record-list --base-token <T> --table-id <tbl> --page-size 1 --as bot --profile dsh-kb
lark-cli base +field-list  --base-token <T> --table-id <tbl> --as bot --profile dsh-kb
lark-cli drive +preview --type source_file --file-token <ft> --profile dsh-kb
lark-cli slides +xml-get  --file-token <ft> --profile dsh-kb
lark-cli sheets +workbook-* --file-token <ft> --profile dsh-kb
```
