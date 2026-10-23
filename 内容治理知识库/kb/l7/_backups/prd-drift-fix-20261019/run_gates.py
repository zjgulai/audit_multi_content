#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""run_gates.py —— 把 kb/l7/scripts 下的闸门脚本收成一个**可被 CI / 定时任务调用**的统一入口。

## 它解决什么

八把层闸门（l0_gate.py … l7_gate.py）加上四把家族闸门（skills_check / layers_check /
skill_conformance / freshness）各说各的退出码、各打各的屏。CI 与 launchd 需要的是：
**一次调用、一张表、一个可判定的退出码、一份机读产物**。

## 退出码（CI 就照这个判）

  0  全过（所有 blocking 闸门 exit 0）
  1  有闸门判红（exit 1）
  2  有闸门「无法计算」（exit 2）—— 与红**分档**：红是数据不对，2 是判据算不出来
  3  runner 自身故障（找不到 kbpy / 超时以外的基础设施问题）

## 与库内纪律的关系（三条，没省）

1. **只读**：本 runner 只调闸门脚本，不传 `--apply`，不碰 `kb/l0…l6` 数据与台账。
   （`l5_gate` 会写它自己的 `kb/.work/l5_integrity.json` —— 那是自检器的证据件，不是层产物，
   闸门自己已在该文件头注明。）
2. **不抢锁**：本 runner **不调** `kb_loop_claim.py`、**不调** `kb_pipeline.py --apply`。
   因此它可以在 CI 上随时跑，不与每日 08:30 的写档循环抢 `kb/.work/.kb.lock`。
3. **freshness 不 blocking**：`freshness.py` 的退出码 3 是「供给链超期」，
   库内口径写明「超期是**去跑链路**的理由，不是拒答的理由」。
   → 本 runner 把它记为 PASS_WITH_WARN，**不**让 CI 变红（否则红灯会变成没人看的噪音）。

## 闸门范围（--scope，2026-10-04 第二轮加；2026-10-12 加性能两把）

  core（**默认**）  8 把层闸门 + skills/layers/conformance/freshness + p0_regression/verdict_latency
                    + perf_bench/clause_no_idem/case_thematic/recall_excl/outbound_plain/view_foreign
                    + prd_card_conformance（2026-10-19 加）
  full              core + 2 把补挂：projection（投影对账）、envelope（信封闸门）

  ★ **名单的唯一真源 = 本文件的 `CORE_GATES` / `EXTRA_GATES`** —— 本节文字只是导读，
    加/删闸门**只改那两张表**，别在这里抄第二份名单（也不要在别处写死把数）。

  ⚠️ 2026-10-12 为什么把性能两把补进 **core**（而不是 full）：
     `p0_regression` / `verdict_latency` 建好后**没有任何东西在跑它们**（launchd 跑的是默认 scope=core）
     —— 「闸门建了不接线，等于还是散文」。两把都只读、合计 < 3 s：
       · `p0_regression`（**blocking**）：11 条红线对逐字源表达的漏报率，现 126/126 ⇒ 绿。
       · `verdict_latency`（**不 blocking**，同 freshness 一档）：PRD §12「性能」三档
         按 Owner 2026-10-12 裁定口径（**守衡回复时间**）实测 —— 当前**未达标**，
         那是「去优化守衡侧」的理由，**不是红灯**（红灯会变成没人看的噪音）。
         要它硬起来：`--strict-warn`。

  ★ 2026-10-19 又补一把同类的：`prd_card_conformance`（**进 core ＋ 不 blocking**）——
    `prd17_check.py` / `prd533_check.py` 建成当天同样**没有任何东西在跑它们**。
    它拿**真产者出的真卡面**量 PRD §17 字数与 §5.3.3 硬约束，判据是**存量登记**
    （只对「比登记时更差」响）—— 因为 §17 的 C1 今天实测就超（108/100），
    超限即红会让 CI 第一天就变噪音。

  ⚠️ 为什么 full 不是默认：**它会改变 CI 的阻断范围**。
     `projection` 当前实测真坏（6 项过 3、漂移 3，退出码 1），补进来后流水线每天必红。
     这是「要你拍板」的事，所以默认留在 core，**现有 launchd / GitHub / GitLab 配置的行为
     一字未改**；要挂满就显式 `--scope full` 或设环境变量 `KB_GATES_SCOPE=full`。

  ⚠️ 没挂的两把，以及**实测**理由（不是漏了）：
     · `l8/workflow_check.py` —— 把 `L8_KB_ROOT` 指向权威库根时**实测崩溃**：
       `OSError: [Errno 7] Argument list too long`（它把 walk 出的全部 md 路径塞进单个 argv 调 DSH），
       且不落任何产物。默认（评派生视图 `kb/view`）另有 ②③ 判据过期属**已登记合法变红**。
       ⇒ 两路都不适合当 blocking 闸门；要挂得先修脚本本身（那是库内脚本，不是本 runner 能改的）。
     · `l7/scripts/routes_reconcile.py` —— `winners` 是**必填位置参数**，它是触发评测的运行时产物、
       全库无脚本自动生成；缺输入时按设计 exit 2（未判定，不许报绿）⇒ **CI 里没有这个输入**。

用法：
    python3 ci/run_gates.py                 # 跑全部，人看表
    python3 ci/run_gates.py --json          # 额外打印机读汇总
    python3 ci/run_gates.py --outdir ci/out # 落盘 JSON + Markdown 报告
    python3 ci/run_gates.py --only l0 l4 l7 # 只跑指定几把
    python3 ci/run_gates.py --scope full    # 连补挂的 projection / envelope 一起跑
    python3 ci/run_gates.py --strict-warn   # 把 WARN 也算失败（用于发布前门禁）
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
KB_ROOT = os.path.dirname(HERE)          # 含 KB-ROOT.json 的那一层（权威库根）
KB_DIR = os.path.join(KB_ROOT, "kb")     # kb/ 本体：kbpy 的脚本路径基准
KBPY = os.path.join(KB_DIR, "kbpy")


def write_text_plain(path: str, text: str) -> None:
    """写 `.md` / `.py` / `.txt` **只走「无扩展名临时件 → cp」通道**（2026-10-03 kb-repair 修）。

    为什么必须这样写：本机上用 python 直写 `.md`（`open(p, "w")`）会落成
    「stat 虚高 4096」的**信封态** —— python 自己 `getsize`/`read` 看到的是明文，
    而**消费方运行时（宿主 Electron 的 `readFileSync` = agent 的 read 工具、装配位加载器）**
    读到的是 4096 字节二进制垃圾 + 原文。

    实测（本 runner 落的盘，2026-10-03 23:33 `ci/out/gates-latest.md`）：

        python getsize = 1282 ｜ 消费方读者 = 5378 = 1282 + 4096 ｜ 首字节 `\x88}\x1cn:`

    后果不是"读起来难看"，而是**闸门判红**：`kb/l8/workflow_check.py` 腿⑥「文档可见性」
    按「`其他` 桶必须为空」判 ⇒ 本文件让整把闸门红，且同一份报告 agent 自己读不到。

    `.json` / `.yaml` **不受此影响**（python 直写安全，实测 `ci/out/gates-latest.json`
    两读者同为 36472），故 `gates-latest.json` 仍走 `json.dump`，只把 `.md` 换成此通道。
    """
    tmp = path + ".tmp-plain"            # 无 .md/.py/.txt 扩展名 ⇒ 不落信封
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(text)
    subprocess.run(["cp", tmp, path], check=True)
    os.remove(tmp)

# 每把闸门：id、脚本路径、是否 blocking、说明
#
# ⚠️ 路径口径（实测踩过，2026-10-03）：`kb/kbpy` 内部 `cd` 到自己的目录（即 `kb/`），
#    所以它接收的脚本路径是**相对 `kb/`** 的 —— 传 `kb/l7/scripts/l0_gate.py` 会被拼成
#    `kb/kb/l7/scripts/l0_gate.py` 并报「找不到脚本」。
#    → 此处存**相对 `kb/`** 的路径（`KBPY_REL`）；要拼库根绝对路径时走 `os.path.join(KB_DIR, …)`。
#
# ⚠️ 参数**不统一**（实测踩过，2026-10-03）：八把层闸门支持 `--json --quiet`，
#    但 `freshness.py` **没有 `--quiet`** —— 传了会 argparse 报错、退出码 2（看起来像"判据算不出来"）。
#    → 每把闸门自带 flags，别假设「大家都一样」。
DEFAULT_FLAGS = ["--json", "--quiet"]

CORE_GATES = [
    ("l0", "l7/scripts/l0_gate.py", True, DEFAULT_FLAGS, "L0 判定档：原始差异 − 预期 = 真差异"),
    ("l1", "l7/scripts/l1_gate.py", True, DEFAULT_FLAGS, "L1 独立复算：OCR 缓存复用门槛逐条核"),
    ("l2", "l7/scripts/l2_gate.py", True, DEFAULT_FLAGS, "L2 独立复算：unit_count 口径逐条点名"),
    ("l3", "l7/scripts/l3_gate.py", True, DEFAULT_FLAGS, "L3 独立复算：证据可回指 L2 单元"),
    ("l4", "l7/scripts/l4_gate.py", True, DEFAULT_FLAGS, "L4 独立复算：promotion_rule C1–C6"),
    ("l5", "l7/scripts/l5_gate.py", True, DEFAULT_FLAGS, "L5 包装分类：实质 4 项 + 基线项登记"),
    ("l6", "l7/scripts/l6_gate.py", True, DEFAULT_FLAGS, "L6 只读档：可用单元/向量/倒排/版本纪律"),
    ("l7", "l7/scripts/l7_gate.py", True, DEFAULT_FLAGS, "L7 引用契约前置条件"),
    ("skills", "l7/scripts/skills_check.py", True, DEFAULT_FLAGS, "登记表自检：应装未装 / 副本不一致"),
    ("layers", "l7/scripts/layers_check.py", True, DEFAULT_FLAGS, "layers.yaml 层契约表自检"),
    ("conformance", "l7/scripts/skill_conformance.py", True, DEFAULT_FLAGS,
     "四方对账：文本↔注册表↔层契约↔磁盘"),
    ("freshness", "l7/scripts/freshness.py", False, ["--json"],
     "供给链新鲜度（超期=去跑链路的理由，不是红灯）"),
    # ── 性能两把（2026-10-12 加；**进 core**，否则默认 scope 根本不跑它们）────────────
    # 为什么进 core：`p0_regression` 建好当天就写明「定期那半尚未接线」，
    # 而 launchd `com.kb.gates` 跑的是默认 scope ⇒ 挂在 full 里 = 等于没挂。
    ("p0_regression", "l8/p0_regression.py", True, [],
     "P0 层定期回归（PRD §16）：11 条红线 × 逐字源表达的漏报率（现 126/126、漏报率 0）"),
    ("verdict_latency", "l8/measure_verdict_latency.py", False, [],
     "PRD §12 性能三档（Owner 2026-10-12 口径=守衡回复时间）：未达标=去优化守衡侧的理由，不是红灯"),
    ("perf_bench", "l8/check_perf_bench.py", True, [],
     "L5 性能验收**复算**（PRD §12 P0≤1s）：真实形态 <1s 硬门槛 ＋ 1MB 余量用例每模式 ≤120ms"),
    # ── PRD 卡面读数（2026-10-19 加；**进 core ＋ 非阻断 = 读数档**）────────────────
    # 为什么必须接进来：`prd17_check.py`（§17 结论模板字数）与 `prd533_check.py`（§5.3.3
    #   字数/位置/依据/语言）建成当天，**20 道闸门里 0 道 PRD、就绪巡检 0 命中**
    #   ⇒ 「判据不接线 = 注释」（本文件上方 2026-10-12 那条写的是同一件事）。
    # 为什么**非阻断**（这是关键，别顺手改成 True）：§17 的 **C1**（BLOCK/REVIEW ≥3 档
    #   ≤100 字）**今天实测就超**（夹具 F2：整卡 108 字 / 上限 100）。
    #   按「超限即红」接线，CI 第一天必红 ⇒ 红灯变噪音 ⇒ 又回到「没人看」
    #   （`perf-known-drift.yaml` 头部记着同一个教训）。
    #   ⇒ 判据改用**存量登记**（`kb/l7/registry/prd-card-known-drift.yaml`）：
    #      **只对「比登记时更差」响**；存量超限登记在案（C1/C2），不天天响。
    # 为什么量**真卡面**：手搓样张只证明「尺子会算」，不证明「我们出得对不对」；
    #   本闸门跑**真产者** `l5/p0_fastpath.py`，量它出的那条卡（守衡卡片供字的同一条路）。
    # 实测成本：2 个夹具、2 次真渲染，合计 ≈4 s（只读，不碰库、不抢锁）。
    ("prd_card_conformance", "l8/prd_card_conformance.py", False, ["--json"],
     "PRD §17/§5.3.3 真实卡面读数（字数/位置/依据/四格）：**只对变差响**（退 3=WARN）"),
    # ── PRD §5.3.2 四态接线（2026-10-19 加；**进 core ＋ 非阻断**）──────────────────
    # 为什么非有它（这一条是 Owner 当天问到的那半）：四态定义落了真源
    #   `kb/l7/registry/prd532-states.yaml`、决策集也加了 `SUGGEST`，可**三处各写一份**：
    #   真源**0 个读方**（只有 `review_engine.py:51` 一句注释）、跨仓 S7 只有
    #   PASS/REVIEW/BLOCK 三条正则、统计侧还是 `TRI_STATE`。
    #   ⇒ 谁把 `SUGGEST` 从任一侧删掉，**今天不会红**。本闸门把「真源 ↔ 决策集 ↔ 落表 ↔
    #   分级 ↔ 渲染 ↔ 守衡词表」六处钉在一起，六种坏形状各有一条反向对照（12/0 自证）。
    # 为什么**非阻断**：它量的是「接线在不在」，不是「库里数据对不对」；
    #   跨仓件（守衡 `prd53.mjs`）或 PRD 内嵌表快照读不到时，本闸门报**未测**，不判红
    #   —— 缺件 ≠ 坏件（同 S7 的口径）。真要它挡发布，等四态统计侧补齐后再提 blocking。
    # 实测成本：≈0.3 s（读一个 yaml ＋ import 三个模块 ＋ 一次 node 取 STATES）。
    ("prd532", "l8/prd532_check.py", False, ["--json"],
     "PRD §5.3.2 四态接线：真源↔决策集↔落表↔分级↔渲染↔守衡词表（六处一致，退 3=WARN）"),
    # ── 发号幂等（2026-10-14 加；**进 core**，同 p0_regression 的理由）──────────────
    # 为什么非有它：`l4_promote.py` 的 `promotion_basis` 写着「C8 发号幂等（不新增号码）」，
    # 而 C8 的实现只核「这条候选在台账里有没有号」—— **从没核过同内容会不会拿第二个号**。
    # 源表整体重建（record_id 换代）后，同一条反例被重新蒸馏、重新发号，C8 一路绿灯。
    # 实测：96 个重复组 / 222 个条款号（S-1.159 vs S-1.296 是其中一组）。
    # 存量 95 组已登记在 `kb/l7/registry/l4-known-duplicates.yaml`（待人裁）⇒ 当前绿；
    # 只对**新增**重复变红。清单缺失时 fail-closed（会红），不静默放行。
    ("clause_no_idem", "l8/check_clause_no_idempotency.py", True, [],
     "发号幂等：同内容不许拿两个条款号（存量 95 组已登记；新增即红）"),
    # ── 案例层题材一致性闸门（2026-10-14 加；**非阻断 = 自证档**）──────────────────
    # 为什么非阻断：这是**判据自证**（拿两份真素材证明闸门有牙），不是对库内数据的检查。
    # 本库惯例：判据自证走非阻断（同 `verdict_latency`、就绪巡检里的「判据自证」那一格）
    # —— 它坏了要人看，但不该让 CI 变红、免得红灯变噪音。
    ("case_thematic", "l8/check_case_thematic_gate.py", False, ["--selftest"],
     "案例层题材一致性闸门自证：BM04 监控器视频 / D8 清洗机视频必须被挡、同题材正例必须放行"),
    # ── 召回面排除闸门（2026-10-15 加；**blocking**）────────────────────────────────
    # 为什么非有它：`rule_eligible=false` 把「这 3 份红人 Brief 不许成为依据」落在了 L1/L2 上，
    # 而**它在 L6 那一层没有任何读方**（`kb/l6/*.py` grep 0 命中）——
    # 今天生效靠的是"没进规则面⇒没进索引"这条**间接**路径，**没有任何判据盯着召回面**。
    # ⇒ 本闸门把它变成直接可核的一条（按记录 id grep 召回索引必须为 0），含反向对照。
    # 依据：Owner 2026-10-15 裁定 B（继续排除；`reason_code=content_artifact_not_a_standard`）。
    ("recall_excl", "l8/check_recall_exclusion.py", True, [],
     "被排除出依据库的记录不许出现在**召回面**（真源=source-readonly.yaml，含反向对照）"),
    # ── KB 侧出站正文的星号收口（2026-10-16 加；**blocking**）────────────────────
    # 为什么非有它：Owner 2026-10-14 定了「守衡的**所有**输出中不允许包含 `**` 星号」，
    # 但当天那次修复落在**守衡进程**的 5 个出口，而唯一的判据
    # `tools/verify_outbound.py` 只看守衡台账 `PMO/logs/ws_outbound.jsonl`。
    # KB 侧有**两条直发腿**用**同一个守衡 bot 身份**把 `lark-cli … --text` 直接打给飞书
    # （`kb/l8/daily_digest.py::send()` 日更摘要 ／ `kb/l8/watch_review_readiness.py::alert()` 告警）
    # —— 它们既不经过守衡进程、也不进那份台账（实测 `grep -c 日更报告 ws_outbound.jsonl` = **0**）
    # ⇒ **这条腿没有任何东西在量**；Owner 2026-10-16 报「下面的 `*` 没有去掉」正是它。
    # 本闸门把这条腿接上：收口自证 ＋ 与守衡 `plain.mjs` 的逐字互校（读不到即**未测**，不报绿）。
    ("outbound_plain", "l8/plaintext.py", True, ["--selftest"],
     "KB 侧出站正文：一个 `*` 都不许有（含与守衡 plain.mjs 逐字互校；读不到即**未测**）"),
    # ── 视图外来条目存活（2026-10-16 加；**非阻断 = 读数档**）──────────────────────
    # 为什么非阻断（**这就是「不许影响现有工作流」的落点**）：
    #   `run_gates.py` 对非阻断闸门分档 —— **rc==3 ⇒ WARN（不改 runner 退出码）**；
    #   rc∈(1,2) ⇒ ERROR ⇒ **会把 runner 打到退出码 3**。
    #   本脚本**只退 0 或 3**（见它文件头「退出码」那节），所以它最多显示成 WARN，
    #   **永远不会把一条本意是「读数」的东西变成红灯**。
    # 为什么值得占一格：`build_view.py` 的 `rep["ok"]` **一个字都没说外来条目**
    #   （它只比派生载荷 `expected_entries`），而它删文件的那一跳是 `stale_removed`。
    #   ⇒ 「视图重建之后外来条目还在」当时**只是一句散文**（GUIDE §一 2026-10-16 记的），
    #     这一格就是给那句话配的判据 —— **只读，不跑重建**（理由见该脚本文件头）。
    ("view_foreign", "l8/check_view_foreign_survival.py", False, [],
     "视图外来条目（`ref-*`）只增不减：重建报告认过的，盘上不许少（只读；退 3=WARN）"),
]

# ── 补挂闸门（2026-10-04 第二轮）──────────────────────────────────────────────
# 6 元组：(id, 相对路径, 路径基准, 是否 blocking, flags, 说明)
#   base="kb"   → 脚本在 kb/ 下；喂给 kbpy 的是**相对 kb/** 的路径（kbpy 内部会 cd 到 kb/）
#   base="root" → 脚本在**库根**下（如 tools/）；两边都用绝对路径（实测 kbpy 接受绝对路径）
#
# 依据：`闸门体检-CI-20261004-0156.md` §4「库内另 4 道（不在 CI 12 道里，必须一起看）」。
# ⚠️ 接线手札 §3 那段补丁片段把 envelope 写成 `l7/scripts/envelope_gate.py` —— **实测该路径不存在**，
#    真身在**库根** `tools/envelope_gate.py`。照抄那段会得到 MISSING_SCRIPT（已在本文件按实测修正）。
EXTRA_GATES = [
    ("projection", "l8/projection_reconcile.py", "kb", True, ["--json"],
     "投影对账：派生视图 kb/view ↔ 权威库漂移（R1–R6）—— 实测真坏 3/6"),
    ("envelope", "tools/envelope_gate.py", "root", True, ["--json", "--quiet"],
     "信封闸门：python getsize vs 读端 statSync().size（活路径）"),
]

GATE_SETS = {
    "core": CORE_GATES,
    "full": CORE_GATES + EXTRA_GATES,
}


def _gate_tuple(g):
    """把 CORE_GATES 的 5 元组补成统一的 6 元组（默认 base='kb'），免得改一处要动 12 行。"""
    if len(g) == 5:
        gid, rel, blocking, flags, desc = g
        return (gid, rel, "kb", blocking, flags, desc)
    return g

STATE_BY_EXIT = {0: "PASS", 1: "RED", 2: "BLOCKED", 124: "TIMEOUT", 127: "NO_RUNNER"}


def _parse_json_tail(text: str):
    """闸门用 --json 时把 JSON 混在人类可读屏里；取最后一个平衡的 {...} 块。"""
    start = text.find("{")
    while start != -1:
        depth = 0
        in_str = False
        esc = False
        for i in range(start, len(text)):
            ch = text[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start:i + 1])
                    except Exception:
                        break
        start = text.find("{", start + 1)
    return None


def run_one(gate_id, rel_path, base, blocking, flags, desc, timeout):
    # 路径口径两档（见 GATE 注释）：
    #   base="kb"   → 存在性检查拼 kb/；喂给 kbpy 的是相对 kb/ 的路径（kbpy 自己 cd 到 kb/）
    #   base="root" → 库根下的脚本（如 tools/）：存在性检查与实参都用**绝对路径**
    if base == "root":
        script_abs = os.path.join(KB_ROOT, rel_path)
        target_arg = script_abs
    else:
        script_abs = os.path.join(KB_DIR, rel_path)
        target_arg = rel_path
    started = time.time()
    rec = {
        "gate": gate_id,
        "script": rel_path,
        "base": base,
        "blocking": blocking,
        "desc": desc,
        "exit": None,
        "state": None,
        "red_total": None,
        "ok_field": None,
        "seconds": 0.0,
        "stderr": "",
        "json": None,
        "tail": "",
    }

    if not os.path.exists(KBPY):
        rec.update(state="NO_RUNNER", exit=127,
                   stderr="找不到 %s（kbpy 是库内约定的解释器入口）" % KBPY)
        return rec
    if not os.path.exists(script_abs):
        rec.update(state="MISSING_SCRIPT", exit=127,
                   stderr="脚本不存在：%s" % script_abs)
        return rec

    cmd = [KBPY, target_arg] + list(flags)
    try:
        p = subprocess.run(cmd, cwd=KB_ROOT, capture_output=True,
                           text=True, timeout=timeout)
        out, err, rc = p.stdout or "", p.stderr or "", p.returncode
    except subprocess.TimeoutExpired as e:
        out = (e.stdout or b"").decode("utf-8", "replace") if isinstance(e.stdout, bytes) else (e.stdout or "")
        err = "超时 %ss" % timeout
        rc = 124
    except Exception as e:                                    # noqa: BLE001
        out, err, rc = "", "runner 调用失败：%r" % (e,), 127

    rec["exit"] = rc
    rec["seconds"] = round(time.time() - started, 1)
    rec["stderr"] = err.strip()[-400:]
    rec["tail"] = "\n".join(out.strip().splitlines()[-8:])[-1200:]

    if rc not in STATE_BY_EXIT:
        rec["state"] = "FAILED"
    else:
        rec["state"] = STATE_BY_EXIT[rc]

    parsed = _parse_json_tail(out)
    if parsed:
        rec["json"] = parsed
        rec["ok_field"] = parsed.get("ok")
        for key in ("red_total", "real_diff_total", "C1_n"):
            if key in parsed and isinstance(parsed[key], int):
                rec["red_total"] = parsed[key]
                break
        if rc == 0 and rec["ok_field"] is False:
            rec["state"] = "RED"
            rec["note"] = "退出码 0 但 JSON ok=false —— 以 ok 为准，判红"
    elif rc == 0:
        rec["state"] = "PASS"

    # 非 blocking 闸门的分档（**不许静默**）：
    #   · 退出码 3 = 业务意义上的"超期/注意"（freshness 的口径）→ WARN
    #   · 退出码 1/2 = 该闸门自己就没跑成（数据红或判据算不出来）→ ERROR
    #   两者都进汇总，只是不单独把 CI 打红（除非 --strict-warn）。
    if not blocking:
        if rc == 3:
            rec["state"] = "WARN"
        elif rc in (1, 2):
            rec["state"] = "ERROR"
            rec["note"] = rec.get("note") or "非 blocking 闸门自己报错（退出码 %s），需人看" % rc
    return rec


def _print_red_hints(results, red_ids):
    """红了以后，把**已声明的成因与处置办法**印出来（纯提示，不参与判红）。

    只处理一种实测过的情形：L0 的 `拉取失败`。
    库内 `kb/l7/registry/l0-expected-diffs.yaml` 的 `resolved → reopen_when` 已经把
    这条路径写死了口径：**先看该表的 `identity` / `identity_fallback`**，再决定查哪条路。
    实测（2026-10-04）回落字段**不在**，而 user 身份报 `token_missing` ⇒ 令牌失效，
    与 `owner_action` ② 一致（`lark-cli auth login …`）。
    """
    hints = []
    for rec in results:
        if rec["gate"] not in red_ids:
            continue
        payload = rec.get("json") or {}
        uncovered = payload.get("uncovered") or []
        pull_failed = [u for u in uncovered if "拉取失败" in str(u)]
        if pull_failed:
            hints.append((rec["gate"], pull_failed))

    if not hints:
        return

    print("-" * 74)
    print("★ 成因提示（**不改判据**，判红仍以上面各闸门为准）：")
    for gate, items in hints:
        print("  · %s 报「拉取失败」%d 条 —— 这**不是数据错**，是取数身份的问题：" % (gate, len(items)))
        for it in items:
            print("      - %s" % str(it)[:120])
        print("    先按 `kb/l7/registry/l0-expected-diffs.yaml → resolved → reopen_when` 分路：")
        print("      · 该表 `identity`/`identity_fallback` 字段**在** → 用户令牌失效或权限被收回")
        print("      · 字段**不在**且 user 身份报 `token_missing` → 同样是令牌失效（实测 2026-10-04 即此路）")
        print("    处置（registry 的 `owner_action` 原文两条）：")
        print("      ① 根治：在飞书侧把 bot「守衡」加成该 Base 的**可阅读协作者**（不用改代码）")
        print("      ② 令牌到期时重跑：lark-cli auth login --profile dsh-kb --domain base --domain wiki")
        print("    ⚠️ 这两条都是**要人做**的动作，CI 修不了 —— 别改成豁免声明把闸门调绿。")


def main():
    ap = argparse.ArgumentParser(description="KB 闸门统一入口（只读；供 CI / 定时任务调用）")
    ap.add_argument("--json", action="store_true", help="额外打印机读汇总")
    ap.add_argument("--outdir", default=None, help="落盘 JSON + Markdown 报告到这个目录")
    ap.add_argument("--only", nargs="*", default=None, help="只跑这些 gate id")
    ap.add_argument("--timeout", type=int, default=600, help="单把闸门超时秒数（默认 600）")
    ap.add_argument("--scope", choices=sorted(GATE_SETS), default=None,
                    help="闸门范围：core=%d 把（默认）｜full=core+projection+envelope。"
                         "缺省读环境变量 KB_GATES_SCOPE，也没有就 core" % len(GATE_SETS["core"]))
    ap.add_argument("--strict-warn", action="store_true",
                    help="把 PASS_WITH_WARN（如 freshness 超期）也当失败")
    args = ap.parse_args()

    scope = args.scope or os.environ.get("KB_GATES_SCOPE") or "core"
    if scope not in GATE_SETS:
        print("未知 scope：%s（可选 %s）" % (scope, "／".join(sorted(GATE_SETS))), file=sys.stderr)
        return 3

    pool = [_gate_tuple(g) for g in GATE_SETS[scope]]
    selected = [g for g in pool if not args.only or g[0] in args.only]
    if not selected:
        print("没有匹配的闸门：%s" % args.only, file=sys.stderr)
        return 3

    print("=" * 74)
    print("KB 闸门统一入口  ｜ 库根 %s" % KB_ROOT)
    print("共 %d 把 ｜ scope=%s ｜ 单把超时 %ss ｜ 本 runner 只读、不抢锁、不传 --apply"
          % (len(selected), scope, args.timeout))
    if scope == "full":
        print("⚠️ scope=full：已挂 projection / envelope —— projection 实测真坏，红了是**真的**")
    print("=" * 74)

    results = []
    for gate_id, rel, base, blocking, flags, desc in selected:
        rec = run_one(gate_id, rel, base, blocking, flags, desc, args.timeout)
        results.append(rec)
        mark = {"PASS": "✅", "WARN": "⚠️", "ERROR": "🔶", "RED": "❌",
                "BLOCKED": "⛔", "TIMEOUT": "⏱️", "FAILED": "💥",
                "MISSING_SCRIPT": "💥", "NO_RUNNER": "💥"}.get(rec["state"], "?")
        extra = ""
        if rec["red_total"] is not None:
            extra = " ｜ 红 %s" % rec["red_total"]
        if rec["state"] == "BLOCKED":
            extra += " ｜ 判据算不出来（不是数据错）"
        print("%s %-12s %-16s %5.1fs%s" % (mark, gate_id, rec["state"], rec["seconds"], extra))
        if rec["state"] in ("RED", "BLOCKED", "FAILED", "TIMEOUT", "MISSING_SCRIPT", "NO_RUNNER"):
            if rec["tail"]:
                for line in rec["tail"].splitlines()[-4:]:
                    print("      │ %s" % line[:150])
        if rec["stderr"] and rec["state"] != "PASS":
            print("      │ stderr: %s" % rec["stderr"][:150])

    blocking_results = [r for r in results if r["blocking"]]
    red = [r["gate"] for r in blocking_results if r["state"] == "RED"]
    blocked = [r["gate"] for r in blocking_results if r["state"] == "BLOCKED"]
    infra = [r["gate"] for r in blocking_results
             if r["state"] in ("FAILED", "TIMEOUT", "MISSING_SCRIPT", "NO_RUNNER")]
    warn = [r["gate"] for r in results if r["state"] == "WARN"]
    errored = [r["gate"] for r in results if r["state"] == "ERROR"]
    passed = [r["gate"] for r in results if r["state"] == "PASS"]

    if red:
        code = 1
    elif blocked:
        code = 2
    elif infra or errored:
        code = 3
    elif warn and args.strict_warn:
        code = 1
    else:
        code = 0

    # ── 红的**成因提示**（2026-10-04 加；纯提示，**不改判据、不改退出码**）──────────
    # 为什么需要：L0 的「拉取失败」在报告里只显示 `拉取失败（没有声明）`，看不出根因。
    #   实测（2026-10-04 00:2x）l0 红 2 条，根因是**用户身份令牌失效**
    #   （`lark-cli` user identity `token_missing`），不是数据错、也不是有人改了库。
    #   值班的人若照着「红=数据不对」去查数据，会白跑一趟。
    #   ⇒ 这里只把**已声明的处置办法**（kb/l7/registry/l0-expected-diffs.yaml → owner_action）
    #     捞出来印在表下面。判红与否仍由闸门自己决定。
    _print_red_hints(results, red)

    print("-" * 74)
    print("汇总：过 %d/%d ｜ 红 %s ｜ 无法计算 %s ｜ 非 blocking 报错 %s ｜ 基础设施 %s ｜ 告警 %s"
          % (len(passed), len(results), red or "无", blocked or "无",
             errored or "无", infra or "无", warn or "无"))
    print("退出码 %d ｜ %s" % (code, {
        0: "全过（告警不算失败；要严格加 --strict-warn）",
        1: "有红", 2: "有『无法计算』（判据算不出来，不是数据错）", 3: "runner 故障 / 非 blocking 闸门自身报错",
    }[code]))
    print("=" * 74)

    payload = {
        "runner": "kb-ci-run-gates",
        "kb_root": KB_ROOT,
        "scope": scope,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "exit_code": code,
        "summary": {"passed": passed, "red": red, "blocked": blocked,
                    "errored": errored, "infra": infra,
                    "warn": warn, "total": len(results)},
        "gates": results,
    }

    if args.outdir:
        os.makedirs(args.outdir, exist_ok=True)
        jp = os.path.join(args.outdir, "gates-latest.json")
        with open(jp, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=1)
        mp = os.path.join(args.outdir, "gates-latest.md")
        lines = [
            "# KB 闸门体检 ｜ %s" % payload["generated_at"],
            "",
            "库根：`%s`" % KB_ROOT,
            "",
            "范围：`scope=%s`（core=%d 把 ｜ full=core+projection+envelope）"
            % (scope, len(GATE_SETS["core"])),
            "",
            "| 闸门 | 状态 | 退出码 | 红数 | 耗时 | 说明 |",
            "|---|---|---|---|---|---|",
        ]
        for r in results:
            lines.append("| %s | %s | %s | %s | %ss | %s |" % (
                r["gate"], r["state"], r["exit"],
                "-" if r["red_total"] is None else r["red_total"],
                r["seconds"], r["desc"]))
        lines += ["", "**退出码 %d** ｜ 红：%s ｜ 无法计算：%s ｜ 告警：%s" % (
            code, red or "无", blocked or "无", warn or "无")]
        # ⚠️ 不许用 `open(mp, "w")` 直写 .md —— 会落成 4096 字节信封（见 write_text_plain 的说明）
        write_text_plain(mp, "\n".join(lines) + "\n")
        print("报告已落盘：\n  %s\n  %s" % (jp, mp))

    if args.json:
        print(json.dumps({k: v for k, v in payload.items() if k != "gates"},
                         ensure_ascii=False, indent=1))

    return code


if __name__ == "__main__":
    sys.exit(main())
