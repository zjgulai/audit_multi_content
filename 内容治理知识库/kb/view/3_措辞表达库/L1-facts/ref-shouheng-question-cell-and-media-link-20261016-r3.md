---
asks:
  - 守衡里「写到哪」的路径为什么不能用 process.cwd()
  - 启动横幅里「媒材链接(云空间)」那条读数是什么意思、什么时候会红
  - 媒材链接那两处修复现在生效了吗（哪次重启让它生效的）
  - 改了东西之后怎么知道该不该落库（有没有读数）
  - verify_ingest_coverage.py 退什么码、要不要当闸门用
collection: 3_措辞表达库
corroborated_by:
  - 盘上实测：tools/PMO/shouheng-state/media-folders.json 被误建（daemon cwd=tools/）与 CLI 那一份不共用；修后路径回到 PMO/shouheng-state/
  - 启动横幅逐字读数：媒材链接(云空间) = ✅ 就绪（云空间可达（月夹子 2026-10：已存在，复用））
  - 重启留痕 PMO/logs/restart-ledger.jsonl 两行 ok:true（18335→53806、53806→64874）；留底件 sha256[:16] ea821101715ba78e
created_at: 2026-10-16
data_level: L2
evidence_group: coordinate
evidence_level: L2
forbidden: 不许据本条判断某条素材能不能发；不许把 `process.cwd()` 当作「仓库根」的代名词（daemon 的 cwd 是 tools/）；不许把 verify_ingest_coverage.py 当成硬闸门用（它默认恒退 0，是读数）；不许据本条声称 cwd 那处修复已经生效（要等下一次重启）。
half_life_days: 90
id: ref-shouheng-question-cell-and-media-link-20261016-r3
kb_class: []
kind: fact
not_proves: 不能证明任何一条具体内容能不能发 —— 它讲的是路径口径与重启收口；不能替代 3_措辞表达库 的任何条款；不能证明 cwd 那处修复已生效（要等下一次重启）；不能证明「落库覆盖率」已经满了 —— 首次读数里就有 1 个留底件没被任何条目指向，而那可能本来就不需要入库；不能证明这条规矩以后不会被忘 —— 它靠 AGENTS.md 那句话与这个读数，不靠记忆。
owner: 刘华丽
pii:
  detected: false
  masked: false
  strategy: 未检出自然人信息：正文为实现说明与命令，不含姓名、联系方式等个人数据；文中「Owner」为角色指称；如后续来源变化需重新判定
provenance:
  anchor: PMO/守衡-媒材链接-补2-cwd与重启-20261016.md#一/#二/#三/#四
  confidence: 确定
sensitivity_level: L2
source:
  captured_at: 2026-10-16
  fingerprint: ea821101715ba78e
  kind: file
  ref: /Users/lute/project/audit_multi_content/PMO/守衡-媒材链接-补2-cwd与重启-20261016.md
summary: 当天第三个缺陷与收口（2026-10-16）：`MEDIA_LINK.cacheFile` 用了 `process.cwd()`，而守护进程的 cwd 是 `tools/` ⇒ 缓存被写进源码树（`tools/PMO/shouheng-state/`）、与 CLI 那份互不相认；修法是走本仓唯一真源 `stateDir()`。教训：daemon 里任何「写到哪」的路径都不许用 cwd。另记：媒材链接接线与两处修复已分别由两次重启生效（PID 18335→53806→64874），启动横幅多了一条 `媒材链接(云空间) = ✅ 就绪` 的读数。同批还落了 Owner 那条「修完要落库、不要每次提醒」的两半：AGENTS.md §2.1 的规矩 + `tools/verify_ingest_coverage.py` 这个读数（首次跑：入库 6 条 / 动过 6 个留底件 / 未覆盖 1 个）。
tier: L1
title: "[参考实现] 守衡里「写到哪」的路径不许用 process.cwd()（2026-10-16 实测）+ 媒材链接两次重启的收口 + 「落库覆盖率」读数"
topic: 知识
valid_until: 2027-01-14
---

# 补 2：状态路径不许用 `process.cwd()`（2026-10-16 实测）+ 两次重启的收口

> **本条是 `ref-shouheng-question-cell-and-media-link-20261016` 的 r3**（supersedes r2）。
> 留底件：`PMO/守衡-媒材链接-补2-cwd与重启-20261016.md`（3,580 字节，sha256 前 16 位 `ea821101715ba78e`）。

---

## 一、第三个缺陷：缓存路径用了 `process.cwd()`

**现象**（盘上看到的，不是推测）：daemon 起来之后，`tools/PMO/shouheng-state/media-folders.json`
凭空出现 —— **源码树里多了一个目录**。

**根因**：`MEDIA_LINK.cacheFile` 第一版写 `path.join(process.cwd(), 'PMO', …)`，
而**守护进程的工作目录是 `tools/`**。于是两份缓存互不相认：

| 谁在跑 | cwd | 缓存写到哪 |
|---|---|---|
| 守护进程 | `tools/` | `tools/PMO/shouheng-state/…` ← **误建** |
| 命令行实测 | 仓库根 | `PMO/shouheng-state/…` |

**修法**：走本仓唯一真源 `stateDir()`（`config.mjs`，带 `SHOUHENG_STATE_DIR` 覆盖语义）。
修后实测路径回到 `PMO/shouheng-state/media-folders.json`；误建的 `tools/PMO/` 已删。

> ★ 教训独立成句：**daemon 里任何「写到哪」的路径都不许用 `process.cwd()`** ——
> 它只在 cwd 恰好等于仓库根时才「看起来对」，而守护进程不是那个 cwd。

## 二、两次重启的收口

| # | PID | 让什么生效 |
|---|---|---|
| ① | 18335 → 53806 | 媒材链接接线（`agent.mjs` / `media_link.mjs` / `review_publish.mjs`） |
| ② | 53806 → 64874 | 修回的两处（链接标签被吃、探针标记过宽）＋ 启动横幅那条读数 |

②之后第一屏逐字：`媒材链接(云空间) = ✅ 就绪（云空间可达（月夹子 2026-10：已存在，复用））`
⇒ r2 里「修完还没重启」那句**已作废**。

## 三、这条规矩自己的读数

Owner 当天：「你的修复验证后要落库，不要我每次提醒」⇒ 按本仓纪律（散文没有失败信号）落了两半：
① `AGENTS.md` §2.1 写着它；② `python3 tools/verify_ingest_coverage.py` 是**它的读数** ——
把「今天动过的 PMO 留底件」对「今天入库的条目」，摆出**没有条目指向的那些**。
首次运行：入库 6 条 / 动过 6 个 / 未覆盖 1 个。默认恒退 0（读数不是判决），`--strict` 才当闸门 ——
理由是「留底件被动过 ≠ 必须入库」（索引/规程/台账那几类不该逼人入库）。

## 四、还欠着的

cwd 那处修复**要等下一次重启**才生效（进程里仍是旧路径）；影响仅是下次启动
还会在 `tools/PMO/` 重建一次那个缓存目录，功能无损失，不为它单独重启。
