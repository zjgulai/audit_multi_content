# 知识库 L0–L7 每日体检 · 2026-10-20

- **体检时间**：2026-10-20 13:47:55（墙钟）
- **run_id**：`20261020-1347`（约定 = 墙钟；见 ⑥）
- **健康**：**RED**
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
| L6 | 只读闸门 **未过** | exit=1 ｜ 退出码：1 | 有 | overwrite_in_place_with_guard |
| L7 | 只读闸门 通过 | exit=0 ｜ 退出码：0 | 有 | append_new_files_by_run |

**小结**：过 7 ｜ 红 1 ｜ 未判（未执行/声明式）0 ｜ 层数 8

**四方对账（skill 文本 ↔ 注册表 ↔ 层契约 ↔ 磁盘）**：过 ｜ 红 0 ｜ 黄（需人裁）85 ｜ 待裁清单 kb/l7/reports/20260930-1240-对账待裁清单.md

## 2. 新鲜度（各层关键产物）

| 层 | 关键产物 | 类别 | 最后写入 | 距今 | 行数 |
|---|---|---|---|---|---|
| L0 | `kb/l0/manifest.jsonl` | data | 10-20 10:46 | 3.0 小时前 | 8586 |
| L0 | `kb/l0/registry/kb.json` | registry | 10-20 13:01 | 46 分钟前 | 3474 |
| L1 | `kb/l1/manifest_l1.jsonl` | data | 10-20 13:41 | 6 分钟前 | 6682 |
| L1 | `kb/l1/index/l1.jsonl` | data | 10-20 12:50 | 57 分钟前 | 16513 |
| L2 | `kb/l2/units.jsonl` | data | 10-20 13:41 | 6 分钟前 | 14978 |
| L2 | `kb/l2/manifest_l2.jsonl` | data | 10-20 13:41 | 6 分钟前 | 3162 |
| L3 | `kb/l3/candidates/rules.jsonl` | data | 10-17 17:15 | 2.9 天前 | 1018 |
| L3 | `kb/l3/rejected.jsonl` | data | 10-20 13:42 | 5 分钟前 | 5485 |
| L3 | `kb/l3/manifest_l3.jsonl` | data | 10-13 16:28 | 6.9 天前 | 13512 |
| L4 | `kb/l4/canonical/wording_entry.jsonl` | data | 10-08 18:46 | 11.8 天前 | 56 |
| L4 | `kb/l4/registry/l4.json` | registry | 10-20 13:42 | 5 分钟前 | 9957 |
| L5 | `kb/l5/p0_patterns.jsonl` | data | 10-20 13:43 | 4 分钟前 | 17 |
| L5 | `kb/l5/registry/l5.json` | registry | 10-20 13:43 | 4 分钟前 | 623 |
| L6 | `kb/l6/registry/l6.json` | registry | 10-20 11:57 | 1.8 小时前 | 1062 |
| L6 | `kb/l6/selftest.json` | data | 10-20 13:45 | 2 分钟前 | 2737 |
| L7 | `kb/l7/registry/skills.yaml` | registry | 10-13 16:54 | 6.9 天前 | 1209 |
| L7 | `kb/l7/registry/layers.yaml` | registry | 10-20 12:00 | 1.8 小时前 | 350 |
| L7 | `kb/l7/registry/routes.yaml` | registry | 10-05 11:04 | 15.1 天前 | 235 |

> **类别**：`data` = 该层产物（判「这层跑过没有」只看 data）；`registry` = 注册表/契约 —— **被别人改一下不代表这层跑过**。下面的「落后」判定只用 `data` 行。

### 2.5 逐层新鲜度（**水位口径**，不是 mtime 口径）

| 层 | 新鲜 | change_state | 落章水位 == 现算水位 | 判据 | 回退旧口径 |
|---|---|---|---|---|---|
| L0 | ❌ | blocked | — | 最近一次 RUN 的 `change_state=blocked` ⇒ 不算跑过 ⇒ 陈旧 | 否 |
| L1 | ✅ | produced_changes | — | 8 天 内跑过且 `change_state=produced_changes` ⇒ 新鲜 | 否 |
| L2 | ✅ | produced_changes | — | 8 天 内跑过且 `change_state=produced_changes` ⇒ 新鲜 | 否 |
| L3 | ✅ | produced_changes | — | 8 天 内跑过且 `change_state=produced_changes` ⇒ 新鲜 | 否 |
| L4 | ✅ | no_new_input | **一致** | 8 天 内跑过；`change_state=no_new_input` 且**上游水位交叉验证通过**（现算水位与落章一致）⇒ 新鲜（无可处理的输入） | 否 |
| L5 | ✅ | no_new_input | **不一致 ⇒ 判陈旧** | 8 天 内跑过；`change_state=no_new_input` 且**上游水位交叉验证通过**（该次运行测前测后水位一致）⇒ 新鲜（无可处理的输入） | 否 |
| L6 | ✅ | produced_changes | — | 8 天 内跑过且 `change_state=produced_changes` ⇒ 新鲜 | 否 |
| L7 | ✅ | no_new_input | **一致** | 8 天 内跑过；`change_state=no_new_input` 且**上游水位交叉验证通过**（现算水位与落章一致）⇒ 新鲜（无可处理的输入） | 否 |

> **口径（裁定 A）**：新鲜 ⟺ 该层最近一次成功 RUN 在 8 天 内，**且**（`change_state=produced_changes` 或（`change_state=no_new_input` 且**现算**上游水位 == 落章水位））。
> ★ **防假绿**：`no_new_input` **不许自证** —— 水位由 `layer_freshness.judge()` 现算读盘，**上游变了就判陈旧**（哪怕 1 分钟前刚跑过）。
> ⚠️ 「回退旧口径 = 是」表示该层落章没有三字段（老格式）⇒ 退回 mtime 判据，**不是**判它新鲜。

## 3. 落后量（下游 vs 上游现状）

| 下游层 | 台账记的上游规模 | 上游现有 | 差 | 判读 |
|---|---|---|---|---|
| L3 | 14978 | 14978 | 0 | 同步 |

> 口径：只做**台账能直读**的比对，不做推测。L0 的缺口看第 1 节的闸门明细；L1/L4/L5/L6 的台账目前没有「记的上游输入规模」字段 → 后期待补（P1-3）。

## 4. 要人做什么

1. **L6 闸门红**：exit=1 ｜ 退出码：1
   → **谁**：L6 层主 ｜ **命令**：kb/kbpy l7/scripts/l6_gate.py ；需要完整档时人跑 kb/kbpy .work/l6_integrity.py <RUN>
      **做什么**：只读档红了先查数据；④重跑幂等要写索引，必须人看着跑完整档（kb/.work/l6_integrity.py）
      **不许**：不许在无人值守的日报里跑完整档（它会 --apply 重建索引） ｜ **复开**：l6_gate.py 退出 0
2. **L0 的 manifest.jsonl 落后 3.0 小时前** → 最近一次 RUN 的 `change_state=blocked` ⇒ 不算跑过 ⇒ 陈旧
   → **谁**：该层层主 ｜ **命令**：先 kb/kbpy l7/scripts/kb_pipeline.py --check 看该层闸门与输入是否齐 → 再 kb/kbpy l7/scripts/kb_pipeline.py --sync --only <层>（预演）
      **做什么**：分两种：① 「该跑没跑」→ 按该层写档引擎跑一次；② 「上游没更新」→ 先去上游层找原因，别在本层空转
      **不许**：不许只改文件时间戳让它「看着新鲜」（新不新鲜看内容）；不许跳过该层闸门直接写 ｜ **复开**：日报「落后 / 陈旧」不再报该层

## 5. 已知阻断项（需人工解锁，重试无效）

（未登记：）

> 本轮实测到的两条（等 P1-2 正式登记）：
> `专家修订汇总表` tbl8AI00JZO1iZtp 与 `内容公式（仅供参考）` tblVdl0jdK9G4ld3 —— 都是 **91403 资源级 ACL**；要人在飞书侧把「守衡」加成**可阅读协作者**。

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
L0   ✅     ✅10    ✅         ✅        有        只读闸门 通过 ｜ exit=0 ｜ 退出码：0
L1   ✅     ✅4     ✅         ✅        有        只读闸门 通过 ｜ exit=0 ｜ 退出码：0
L2   ✅     ✅2     ✅         ✅        有        只读闸门 通过 ｜ exit=0 ｜ 退出码：0
L3   ✅     ✅4     ✅         ✅        有        只读闸门 通过 ｜ exit=0 ｜ 退出码：0
L4   ✅     ✅6     ✅         ✅        有        只读闸门 通过 ｜ exit=0 ｜ 退出码：0
L5   ✅     ✅4     ✅         ✅        有        只读闸门 通过 ｜ exit=0 ｜ 退出码：0
L6   ✅     ✅6     ✅         ✅        有        只读闸门 **未过** ｜ exit=1 ｜ 退出码：1
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

硬问题 1 条：
   - L6 闸门未过：exit=1 ｜ 退出码：1
结论：有问题
说明：本次是 `--check`（零写体检）。写档走 `--sync`，仍需人工开闸：它按层序逐层调 `--apply`，而**干跑档已于 P0-3/P0-3d（2026-09-29）补齐** —— 8 个会改库数据的脚本（reconcile_l0_feishu / ocr_attachments / l3_distill_run / drill_links_2levels / l4_article / l5_prep / l5_export / l6_build）均支持 --apply，闸门位次在各自第一个副作用之前。
```

