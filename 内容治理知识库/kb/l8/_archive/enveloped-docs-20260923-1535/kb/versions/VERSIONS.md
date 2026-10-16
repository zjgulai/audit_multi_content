# 版本清单（VERSIONS）

> 本文件由 `versions.jsonl` 投影生成，**不许手工维护**。重建命令：
> `python3 kb/.work/emit_versions.py`（重跑同一条投影逻辑，逐字节一致）。

## 文件头部说明（来自 versions.jsonl 注释行）

- 版本指针流水（append-only）
- 本文件只放指针，不放内容副本；每行一条 JSON，主键 version_id。
- 两层版本号，不要混成一个字段：
- kb_version  —— 每类库独立，如 external_standard: v3
- release_id  —— 组合发布号，如 rel-0007
- L0 原始库阶段不生成任何版本号、不做发布，本文件保持零版本行。

## 版本行

当前 **0 条版本行**。L0 原始库阶段不生成版本号、不做发布。

## 计数器

- kb_version（按库）：0 个
- release_id（组合发布号）：0 个
- 版本行总数：0
