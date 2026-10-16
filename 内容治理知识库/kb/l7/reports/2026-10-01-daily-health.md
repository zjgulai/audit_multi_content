# 知识库 L0–L7 每日体检 · 2026-10-01

- **体检时间**：2026-10-01 22:35:10（墙钟）
- **run_id**：`20261001-2235`（约定 = 墙钟；见 ⑥）
- **健康**：**YELLOW**
- **本次是否零写**：✅ 是（编排器 mtime 快照自证：4,000+ 个层产物无变化）
- **解释器**：`/usr/bin/python3` ✅

> 本报告只读：不写 `kb/l0…l6` 的任何数据与台账；产物只落 `kb/l7/reports/`。
> 退出码 0 = **体检跑成功**；健康与否看上面的 **健康** 一行。

## 1. 逐层闸门

| 层 | 闸门 | 明细 | 干跑档 | 写模式 |
|---|---|---|---|---|
| L0 | 只读闸门 通过 | exit=0 ｜ 退出码：0 | 有 | append_then_archive |
| L1 | 只读闸门 通过 | exit=0 ｜ 退出码：0 | 有 | append_then_archive |
| L2 | 只读闸门 通过 | exit=0 ｜ 退出码：0 | 有 | append_only |
| L3 | 只读闸门 通过 | exit=0 ｜ 退出码：0 | 有 | overwrite_in_place_no_archive |
| L4 | 只读闸门 通过 | exit=0 ｜ 退出码：0 | 有 | overwrite_in_place_atomic |
| L5 | 只读闸门 通过 | exit=0 ｜ 退出码：0 | 有 | overwrite_with_archive |
| L6 | 只读闸门 通过 | exit=0 ｜ 退出码：0 | 有 | overwrite_in_place_with_guard |
| L7 | 只读闸门 通过 | exit=0 ｜ 退出码：0 | 有 | append_new_files_by_run |

**小结**：过 8 ｜ 红 0 ｜ 未判（未执行/声明式）0 ｜ 层数 8

**四方对账（skill 文本 ↔ 注册表 ↔ 层契约 ↔ 磁盘）**：过 ｜ 红 0 ｜ 黄（需人裁）85 ｜ 待裁清单 kb/l7/reports/20260930-1240-对账待裁清单.md

## 2. 新鲜度（各层关键产物）

| 层 | 关键产物 | 类别 | 最后写入 | 距今 | 行数 |
|---|---|---|---|---|---|
| L0 | `kb/l0/manifest.jsonl` | data | 10-01 10:40 | 11.9 小时前 | 5418 |
| L0 | `kb/l0/registry/kb.json` | registry | 09-30 09:56 | 1.5 天前 | 2396 |
| L1 | `kb/l1/manifest_l1.jsonl` | data | 10-01 15:54 | 6.7 小时前 | 5512 |
| L1 | `kb/l1/index/l1.jsonl` | data | 10-01 10:45 | 11.8 小时前 | 14707 |
| L2 | `kb/l2/units.jsonl` | data | 10-01 10:45 | 11.8 小时前 | 12213 |
| L2 | `kb/l2/manifest_l2.jsonl` | data | 10-01 10:45 | 11.8 小时前 | 2543 |
| L3 | `kb/l3/candidates/rules.jsonl` | data | 10-01 22:29 | 5 分钟前 | 2036 |
| L3 | `kb/l3/rejected.jsonl` | data | 10-01 22:28 | 6 分钟前 | 10661 |
| L3 | `kb/l3/manifest_l3.jsonl` | data | 10-01 22:29 | 5 分钟前 | 8416 |
| L4 | `kb/l4/canonical/wording_entry.jsonl` | data | 09-29 10:32 | 2.5 天前 | 56 |
| L4 | `kb/l4/registry/l4.json` | registry | 10-01 22:28 | 6 分钟前 | 3430 |
| L5 | `kb/l5/p0_patterns.jsonl` | data | 10-01 22:29 | 5 分钟前 | 7 |
| L5 | `kb/l5/registry/l5.json` | registry | 10-01 22:29 | 5 分钟前 | 173 |
| L6 | `kb/l6/registry/l6.json` | registry | 10-01 22:31 | 3 分钟前 | 541 |
| L6 | `kb/l6/selftest.json` | data | 10-01 22:33 | 1 分钟前 | 2735 |
| L7 | `kb/l7/registry/skills.yaml` | registry | 10-01 11:59 | 10.6 小时前 | 1205 |
| L7 | `kb/l7/registry/layers.yaml` | registry | 10-01 22:22 | 12 分钟前 | 571 |
| L7 | `kb/l7/registry/routes.yaml` | registry | 09-30 14:37 | 1.3 天前 | 226 |

> **类别**：`data` = 该层产物（判「这层跑过没有」只看 data）；`registry` = 注册表/契约 —— **被别人改一下不代表这层跑过**。下面的「落后」判定只用 `data` 行。

## 3. 落后量（下游 vs 上游现状）

| 下游层 | 台账记的上游规模 | 上游现有 | 差 | 判读 |
|---|---|---|---|---|
| L3 | 12213 | 12213 | 0 | 同步 |

> 口径：只做**台账能直读**的比对，不做推测。L0 的缺口看第 1 节的闸门明细；L1/L4/L5/L6 的台账目前没有「记的上游输入规模」字段 → 后期待补（P1-3）。

## 4. 要人做什么

1. **L4 的 wording_entry.jsonl 落后 2.5 天前**（只看 data 产物）→ 确认它是否该跑（或它的上游还没更新）
   → **谁**：该层层主 ｜ **命令**：先 kb/kbpy l7/scripts/kb_pipeline.py --check 看该层闸门与输入是否齐 → 再 kb/kbpy l7/scripts/kb_pipeline.py --sync --only <层>（预演）
      **做什么**：分两种：① 「该跑没跑」→ 按该层写档引擎跑一次；② 「上游没更新」→ 先去上游层找原因，别在本层空转
      **不许**：不许只改文件时间戳让它「看着新鲜」（新不新鲜看内容）；不许跳过该层闸门直接写 ｜ **复开**：日报「落后 / 陈旧」不再报该层

## 5. 已知阻断项（需人工解锁，重试无效）

| 对象 | 原因码 | 要谁做 | 复开条件 |
|---|---|---|---|
| 专家修订汇总表（tbl8AI00JZO1iZtp） | 91403 | 在飞书侧把「守衡」加成这张表的**可阅读协作者**。加完把本条从 expected 移除（闸门会自动失去豁免）。 | 所有者共享后，`align_l0_feishu.py --check` 该表不再报拉取失败 |
| 内容公式（仅供参考）（tblVdl0jdK9G4ld3） | 91403 | 同 EX-2：把「守衡」加成可阅读协作者。 | 所有者共享后自动失去豁免 |

## 6. 编排器原始输出（存证，不转述）

```text
====================================================================================
知识库 L0–L7 执行编排器 · --check（零写档）
====================================================================================
库根      : /Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理/kb
解释器    : /usr/bin/python3 ✅
层数      : 8（拓扑序：L0 → L1 → L2 → L3 → L4 → L5 → L6 → L7）
闸门执行  : 只读白名单 12 个

层    cwd   engine inputs    outputs  干跑档      闸门
------------------------------------------------------------------------------------
L0   ✅     ✅4     ✅         ✅        有        只读闸门 通过 ｜ exit=0 ｜ 退出码：0
L1   ✅     ✅4     ✅         ✅        有        只读闸门 通过 ｜ exit=0 ｜ 退出码：0
L2   ✅     ✅1     ✅         ✅        有        只读闸门 通过 ｜ exit=0 ｜ 退出码：0
L3   ✅     ✅3     ✅         ✅        有        只读闸门 通过 ｜ exit=0 ｜ 退出码：0
L4   ✅     ✅5     ✅         ✅        有        只读闸门 通过 ｜ exit=0 ｜ 退出码：0
L5   ✅     ✅4     ✅         ✅        有        只读闸门 通过 ｜ exit=0 ｜ 退出码：0
L6   ✅     ✅6     ✅         ✅        有        只读闸门 通过 ｜ exit=0 ｜ 退出码：0
L7   ✅     ✅3     ✅         ✅        有        只读闸门 通过 ｜ exit=0 ｜ 退出码：0
------------------------------------------------------------------------------------
逐层 skill（`layers.yaml` → `skill:` 字段；唯一真源）
  L0  → kb-l0-feishu                               ✅ 写档
  L1  → kb-ingest-extractor → kb-media-extractor   ✅ 写档
  L2  → kb-ingest-extractor                        ✅ 写档
  L3  → kb-clause-extractor                        ✅ 写档
  L4  → kb-canonical-lookup                        ✅ 写档
  L5  → kb-p0-check                                ✅ 写档
  L6  → kb-recall                                  ✅ 写档
  L7  → kb-check                                   ⚠️ 只读/闸门（写档是显式登记的缺口）
  `--sync --via-skill` 时按此逐层调用；引擎不在这里跑（归该层 skill）。

零写自证  : ✅ 未写任何文件（产出文件 mtime 快照 4001 个，变化 0 个）

硬问题：无 ✅
结论：全过
说明：本次是 `--check`（零写体检）。写档走 `--sync`，仍需人工开闸：它按层序逐层调 `--apply`，而**干跑档已于 P0-3/P0-3d（2026-09-29）补齐** —— 8 个会改库数据的脚本（reconcile_l0_feishu / ocr_attachments / l3_distill_run / drill_links_2levels / l4_article / l5_prep / l5_export / l6_build）均支持 --apply，闸门位次在各自第一个副作用之前。
```

