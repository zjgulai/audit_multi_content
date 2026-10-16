#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""run_record.py —— **每一次运行的留痕**（谁触发、选了哪个 skill、跑了什么、产物在哪、有没有人在环）。

## 为什么必须有它（2026-09-30）

「skills 自动化工作流跑通」这句话，没有 run 记录就**无法验收**：
  * 说不清这一次到底调用了哪些 skill（用户已经问过三次）；
  * 分不清「人在环」和「无人值守」—— 本机**没有无头 agent 入口**
    （PATH 无 `dsh`、app bundle 无 dsh 的 bin 声明），所以当前只有两级自动化：
      · 一级 无人值守：跑的是 **skill 文档里写的那条命令**（脚本执行，没有 agent 读 skill）
      · 二级 人在环：人说一句 → agent 按 skill 走（判断权在这一级）
    这两级在产物上长得一样，**只有 run 记录的 `human_involved` 字段能分开**。

## 记录字段（克制，只留能核的）

    run_id        墙钟 YYYYMMDD-HHMMSS
    at             ISO 时间
    source         哪个入口写的：daily_health / review_machine / pipeline_sync / manual
    trigger        触发语或触发源（如「同步一下知识库」/「定时 08:30」）
    skills         本次**被用到**的 skill（列表；机器路径只写它真用到的那几个，不吹）
    commands       实际跑的命令（列表）
    products       产物（路径列表）
    verdict        结论/健康度（如 BLOCK / 过8-红0-未判0）
    human_involved 有没有人在环（True/False）—— **这一格是这套记录存在的理由**
    content_id     素材身份（评审单：业务号 `AD-…` 或指纹兜底 `AUTO-<sha12>`；2026-10-12 加）
    confidence     引擎置信度（0–1；评审单专用；2026-10-12 加，派生量）
    extra          兜底字典（别塞大对象）

落盘：`kb/l7/runs/<run_id>.json`（每条一份）+ `kb/l7/runs/index.jsonl`（一行一条，便于统计）。

## 约定（2026-09-30 起）：**谁走完 skill，谁写一条**

* agent 侧（我按 skill 的正文走过一遍）→ `--agent`，`human_involved=True`，`skills` 写**真正加载过的**那几个，
  机器路径（`daily_health` / `review_machine` / `pipeline_sync`）→ `--unattended`。
* 这条约定没有强制器（本机没有无头 agent 入口，没法在入口处拦）。**所以它靠纪律**：
  不写，就等于这次运行没有证据 —— 下次有人问「这一跑用了哪些 skill」，只能靠嘴说。

## 用法

    # 库里调用
    from run_record import record
    record(source="daily_health", trigger="定时 08:30", skills=["kb-check"],
           commands=["kb/kbpy l7/scripts/kb_pipeline.py --check"],
           products=["kb/l7/reports/2026-09-30-daily-health.md"],
           verdict="过8/红0/未判0", human_involved=False)

    # 命令行（给 shell / launchd 兜底用）
    kb/kbpy l7/scripts/run_record.py --source manual --trigger "人肉跑一次" \
        --skill kb-pipeline --command "kb/kbpy l7/scripts/kb_pipeline.py --check" \
        --verdict "全过" --unattended
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
KB = os.path.dirname(os.path.dirname(HERE))          # …/kb
RUNS = os.path.join(KB, "l7", "runs")
INDEX = os.path.join(RUNS, "index.jsonl")


# ★ 只读测量的隔离开关（口径与实测证据见 `record()` 的 docstring）：
#   `KB_RUN_RECORD_SKIP=1` ⇒ 不写台账（往 stderr 说明）；`KB_RUN_RECORD_FORCE=1` ⇒ 压过它。
#   两个都**只有显式设置才生效** ⇒ 既有调用方（日更 / 守衡 / API）行为一字未变。
_SKIP_ENV = "KB_RUN_RECORD_SKIP"
_FORCE_ENV = "KB_RUN_RECORD_FORCE"
_TRUTHY = ("1", "true", "yes", "on")


def _truthy(name):
    return str(os.environ.get(name) or "").strip().lower() in _TRUTHY


def _skip_verdict():
    """返回 (是否跳过, 原因)。**纯函数** —— 自证靠它，好喂样本。"""
    if _truthy(_FORCE_ENV):
        return False, "KB_RUN_RECORD_FORCE 显式覆盖"
    if _truthy(_SKIP_ENV):
        return True, "%s=%s" % (_SKIP_ENV, os.environ.get(_SKIP_ENV))
    return False, ""


def _norm_list(v):
    if v is None:
        return []
    if isinstance(v, str):
        return [v]
    return [str(x) for x in v]


def _union(a, b):
    """保序去重合并（a 在前）。"""
    out = [str(x) for x in (a or [])]
    for x in (b or []):
        if str(x) not in out:
            out.append(str(x))
    return out


def _merge_prev(rec, prev):
    """同一个 run_id 被写第二次时**合并**，不覆盖（2026-10-03 加）。

    为什么：`kb/l7/runs/<RUN>.json` 是**单文件**。驱动循环对每层各记一次账，
    共用一个 RUN 时后一层会把前一层**覆盖**掉（`skill_sessions` 只剩最后一层，
    `skill_invocation_audit.py` 的 E2/E3 因此核不到前几层）。
    合并是**加性**的：列表取并集、`extra` 逐键合并（dict 再并一层），标量取**新值**，
    绝不删键；`extra.write_merges` 记次数，让「这一份是合并来的」可见。
    （根治口径仍是「逐层一个 RUN」；本合并只是让旧写法不再丢证据。）
    """
    rec["skills"] = _union(prev.get("skills"), rec.get("skills"))
    rec["commands"] = _union(prev.get("commands"), rec.get("commands"))
    rec["products"] = _union(prev.get("products"), rec.get("products"))
    pe, ne = prev.get("extra") or {}, rec.get("extra") or {}
    merged = dict(pe)
    for k, v in ne.items():
        old = merged.get(k)
        if isinstance(v, list) or isinstance(old, list):
            merged[k] = _union(old if isinstance(old, list) else [old] if old is not None else [],
                               v if isinstance(v, list) else [v])
        elif isinstance(v, dict) and isinstance(old, dict):
            d = dict(old)
            for k2, v2 in v.items():
                if isinstance(v2, list) or isinstance(d.get(k2), list):
                    d[k2] = _union(d.get(k2), v2)
                else:
                    d[k2] = v2
            merged[k] = d
        else:
            merged[k] = v
    merged["write_merges"] = int(pe.get("write_merges") or 0) + 1
    merged["previous_at"] = prev.get("at")
    rec["extra"] = merged
    return rec


def record(*, source, trigger, skills=None, commands=None, products=None,
           verdict="", human_involved=True, extra=None, run_id=None, content_id=None,
           confidence=None):
    """写一条 run 记录，返回 run_id。**只写 kb/l7/runs/**（不碰层数据）。

    ★★ 2026-10-12：**只读测量不许进评审台账**（观测者不得改变被观测对象）──────────
      病灶：本函数**无条件**追加 `kb/l7/runs/index.jsonl`，而**回归跑批**
      （`kb/l8/regression_run.py`）每跑一次就 subprocess 调一次引擎 ⇒
      `with_kb_evidence.py` 里的 `run_record.record(source="review_machine")` 就落一行
      ⇒ **跑一次回归 = 往评审台账灌 100 行**。

      实测代价（2026-10-12 11:52 读数）：
        · `index.jsonl` 共 **5161** 行，其中 `source=review_machine` **1102** 行；
        · 这 1102 行里 **316 行**的 `trigger` 与 `regression-set.yaml` 的素材**逐字相同**
          （**今天 268 行**）—— 那**不是新的评审单**，是**同一条素材被重跑**；
        · 而 xlsx 的 G 列与多份交付件里的「**累计评审单数 562 / 580**」
          **正是从这份台账算出来的**（`.work/task_xlsx_g_values*.py` 逐字写着
          `kb/l7/runs/index.jsonl 的 source=review_machine`）
        ⇒ **度量被测量行为本身抬高。**

      口径：**只读测量（回归跑批 / 自证 / 离线探针）一律不进评审台账。**
        开关 `KB_RUN_RECORD_SKIP=1` ⇒ 跳过写盘，**但往 stderr 打一行**（不许静默）；
        真要让测量也记账，得显式 `KB_RUN_RECORD_FORCE=1`（**写要写出来**）。
        两个变量都**只有显式设置才生效** ⇒ 日更 / 守衡 / API 那些既有调用方**行为一字未变**。
    """
    skip, why = _skip_verdict()
    if skip:
        rid = run_id or time.strftime("%Y%m%d-%H%M%S")
        sys.stderr.write("[run_record] 已跳过记账（%s）：source=%s ｜ trigger=%r\n"
                         "              口径：只读测量不进评审台账；要记账加 KB_RUN_RECORD_FORCE=1\n"
                         % (why, source, str(trigger)[:60]))
        return rid
    os.makedirs(RUNS, exist_ok=True)
    rid = run_id or time.strftime("%Y%m%d-%H%M%S")
    rec = {
        "run_id": rid,
        "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "source": source,
        "trigger": trigger,
        "skills": _norm_list(skills),
        "commands": _norm_list(commands),
        "products": _norm_list(products),
        "verdict": verdict,
        "human_involved": bool(human_involved),
    }
    # ── ★ 2026-10-12：素材 ID 落成**顶层字段**（缺省不写，**不编**）──────────────────
    #   为什么必须有它（实测口径缺陷）：本台账的「一单」原先**只能用 `trigger`（text[:60]）
    #   当身份** ⇒ 同一素材重跑 = 多单，读数被重跑抬高（实测 1305 行 → 按素材只 **258** 条）。
    #   `kb/l8/baseline_table.mjs:207` 自己写着：「换成「一素材 = 一单」需要**先给 index.jsonl
    #   补素材 ID 字段**，否则复现不出来」—— 本行就是补那个字段。
    #   值 = 业务号（`AD-YYYYMMDD-NNN`，见 `core/content_id.py`）或指纹兜底 `AUTO-<sha12>`
    #   —— **由调用方给**，本函数不自己造号（造号要去读飞书表，记账不该干那件事）。
    #   ★ 缺省 `None` ⇒ **键不出现**（而不是写 null）：这样"没给"与"给了空"分得开，
    #     且既有调用方（日更 / 守衡 / API）的记录**一个字节不变**。
    if content_id:
        rec["content_id"] = str(content_id)
    # ── ★ 2026-10-12（#11 第②步前置）：引擎**置信度**落成顶层字段（缺省不写，**不编**）──
    #   为什么必须有它：**自标定与两侧一致性都要「按单取置信度」**，而实测台账
    #   `source=review_machine` **1306 行里带置信度的 0 行** —— `verdict` 只有
    #   「STATE ｜ issue_count=N」，置信度**只在跑批那一刻的 JSON 里**，事后回捞不到
    #   （`grep -c '"confidence"' kb/l7/runs/index.jsonl` = 0）。
    #   值 = 引擎 `decide()` 输出的 `confidence`（2026-10-12 起是**派生量**，
    #   见 `review_engine.py::_result(conf_derivation=…)`）—— **由调用方给**，
    #   本函数不自己算（记账不该去跑引擎）。
    #   口径与 `content_id` 一致：缺省 `None` ⇒ **键不出现**（"没给"与"给了空"分得开），
    #   既有调用方（日更 / 守衡 / API）的记录**一个字节不变**。
    #   ★ 非数字一律**报错**，不静默写 null —— 一个写不进去的数比没有数更坏。
    if confidence is not None:
        try:
            rec["confidence"] = round(float(confidence), 4)
        except (TypeError, ValueError):
            raise ValueError("confidence 必须是 0–1 的数字或 None，收到 %r" % (confidence,))
    if extra:
        rec["extra"] = extra
    p = os.path.join(RUNS, rid + ".json")
    if os.path.exists(p):                                # ★ 同一个 RUN 再记一次 ⇒ 合并，不覆盖
        try:
            with open(p, encoding="utf-8") as fh:
                prev = json.load(fh)
            if prev.get("run_id") == rid:
                rec = _merge_prev(rec, prev)
        except Exception:                                # noqa: BLE001
            pass                                         # 读不动就照旧覆盖，不因记账崩掉
    with open(p, "w", encoding="utf-8") as fh:          # .json/.jsonl 不受信封影响
        json.dump(rec, fh, ensure_ascii=False, indent=1)
    with open(INDEX, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False, sort_keys=True) + "\n")
    return rid


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True)
    ap.add_argument("--trigger", required=True)
    ap.add_argument("--skill", action="append", default=[])
    ap.add_argument("--command", action="append", default=[])
    ap.add_argument("--product", action="append", default=[])
    ap.add_argument("--verdict", default="")
    ap.add_argument("--unattended", action="store_true", help="无人在环")
    ap.add_argument("--agent", action="store_true",
                    help="agent 侧走的 skill（=人在环）；source 缺省会补成 agent_manual")
    ap.add_argument("--human", action="store_true", help="人在环（默认）")
    a = ap.parse_args()
    rid = record(source=(a.source if a.source != "manual" else
                         ("agent_manual" if a.agent else "manual")),
                 trigger=a.trigger, skills=a.skill, commands=a.command,
                 products=a.product, verdict=a.verdict,
                 human_involved=(a.agent or a.human or not a.unattended))
    print("已记录 run_id=%s → kb/l7/runs/%s.json" % (rid, rid))
    return 0


if __name__ == "__main__":
    sys.exit(main())
