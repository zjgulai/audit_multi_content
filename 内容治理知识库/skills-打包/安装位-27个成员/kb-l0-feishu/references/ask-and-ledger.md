---
title: Ask & Ledger（问人格式、落盘留痕、自成长台账）
doc_type: reference
module: kb-l0-feishu
topic: ask-and-ledger
status: stable
created: 2026-10-04
updated: 2026-10-04
owner: self
source: human+ai（由 SKILL.md §6.1 / §8.3 下沉，正文只留判据）
---

# 问人格式 · 落盘留痕 · 自成长台账

**读取条件**：要写「待确认清单」时（§一）；要改任何 skill 文件时（§二）；跑 `retro.py` 或审计重复项时（§三）。

## 一、问人的格式：每条待确认事项必须自带建议

把选择权交出去、却不给判断，等于把活推回给人（用户 2026-09-30 明确要求）。**四项俱全**：

| 要素 | 要求 |
|---|---|
| ① 事实 | 实测数字 + 证据路径（`kb/l8/runs/<RUN>-*.json`），不写"大概""可能" |
| ② **我的建议** | **必须明确选一个**（"我建议做 X"），不许只罗列选项让人挑 |
| ③ 理由 | 为什么是它：代价 / 风险 / 可逆性 / 与已有口径是否冲突 |
| ④ 取舍 | 其他选项各差在哪；默认（不做）会怎样 |

- 排序：把**我建议的那个放第一条**。
- 允许说"这条我没有建议，因为缺 X 信息" —— 但要写明**缺什么信息才能形成建议**。
- 收尾时用一句"**按你的建议做**"就能整体放行的写法组织清单；需要拆开决策的逐条标注依赖关系。

**反例（不许这样写）**：

```text
待确认：这些记录要不要补登？（等你决定）
```

**正例**：

```text
① 事实：record_files_not_registered_total = 37（kb/l8/runs/20261004-0756-l0-align.json）
② 我的建议：本轮回填阶段 4（append-only，只加行、不改历史行），不做删除
③ 理由：不补 → 下游算「L0 活跃集 ⊖ L1」得 0，这 37 条永远抽不出来；可逆（台账 append-only）
④ 取舍：本轮回填 = 本轮就能进下游；等下轮 = 今天这 37 条在报告里只能是"缺口"，下游继续缺
```

> 与红线 4 同源：**要么给人可执行的判断，要么明说判断不了**，
> 不要把"没想清楚"伪装成"等你决定"。

## 二、落盘留痕（改 skill 文件时的硬要求）

任何 skill 文件被改，**同一次改动里五步齐全**：

```bash
# ① 备份：改的是哪一侧就备哪一侧，但**库内源必留一份**（它是唯一可写位置）
cp -Rp kb/l7/skills/kb-l0-feishu ~/.dsh/backups/kb-l0-feishu-<YYYYMMDD-HHMM>/

# ② 追加 references/CHANGELOG.md：日期 / 改了什么 / 依据哪个 RUN 的证据 / 谁确认

# ③ SKILL.md 与 .skill-meta/manifest.yaml 同步 bump version / last_updated
#    （别让两份版本号各说各话）

# ④ 验一次明文（这个仓库踩过信封坑：python 直接 open(w) 会留 4096 字节信封）
f=SKILL.md; [ "$(stat -f %z "$f")" = "$(python3 -c "import os;print(os.path.getsize('$f'))")" ] \
  && echo OK || echo 信封态

# ⑤ 回灌 + 自证（两个方向都要收口）
rsync -a --delete kb/l7/skills/kb-l0-feishu/ ~/.dsh/skills/kb-l0-feishu/   # 源 → 装载位
kb/kbpy l7/scripts/skills_check.py                                          # 第 3 类必须为 0、exit=0
```

**为什么第 ⑤ 步是硬要求**：只改源不回灌装位、或只改装位不回灌源，都会当场变成一条
`skills_check` 第 3 类红 —— 这正是 2026-09-30 那次连红四次的形态
（13:10 / 13:38 / 13:46 / 14:50），每次都要人手工回灌才收口。
口径真源：`kb/l7/registry/skills.yaml` :: `meta.single_writer_rule`。

## 三、自成长台账（`retro.py` 写什么 / 不写什么）

| 项 | 值 |
|---|---|
| 跑法 | `python3 kb/l7/skills/kb-l0-feishu/scripts/retro.py <RUN> [--align-run <RUN>] [--kb <库根>]`（`--help` 可查参数） |
| 写 | `kb/l8/retro/ledger.ndjson`（append-only，一行一轮）；`<库根>/l7/skills/kb-l0-feishu/references/gotchas.proposals.md`（升级候选） |
| **不写** | `SKILL.md` / `gotchas.md` 正文 / 任何闸门 / **装载位 `~/.dsh/skills`** |
| 护栏 | 候选落点命中装载位即拒跑；写完当场把**这一个文件**镜像到装载位（两个方向都不红） |
| 落盘方式 | `mkstemp` 到 `/tmp` → 子进程 `/bin/cp` 覆盖；**不要用** `open(w)`（信封态）或 `os.replace()`（下一轮 stat 又变信封） |

**候选与已确认坑分开放**：`gotchas.proposals.md` 是"候选区"，`gotchas.md` 是"人工确认区"。
`retro.py` 只往候选区追加；把候选升成确认坑、或把候选升成红线，都要人拍板（§8.2）。

`--help` 与参数自校验（2026-10-04 加）：缺 `--kb` 的值会当场停，不吞成静默默认。
