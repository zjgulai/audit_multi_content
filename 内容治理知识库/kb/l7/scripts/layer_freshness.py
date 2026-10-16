#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""layer_freshness.py —— **「这层新鲜吗」的水位口径**（批次18 · 第0块 · 裁定 A 落地）。

## 为什么要它（旧口径为什么不可行）

旧口径（`daily_health.py:285-286`）只有一条：

    陈旧 ⟺ kind == "data" 的产物 mtime 距今 > 86400 秒

**它把「正确地什么都没变」判成陈旧，且永远清不掉。** 实测（2026-10-02）：

    L2 本 RUN 跑过（`kb/l2/runs/20261002-1510.json`，`applied: true`、
    `new_units: 0`、`refilled: 0`、`cov_before == cov_after`），
    但 `kb/l2/units.jsonl` 的 mtime 仍是 `Oct 1 10:45:41` ⇒ 判陈旧。

幂等层**本来就该不写盘**（L2 的 `cov_before == cov_after` 就是「无新增」的证据）。
拿 mtime 当「跑过没有」的判据，在幂等层上**结构性失效**。
更糟的是它**误导处置**：日报让它「跑 L2」，而 L2 刚跑过、结论就是「无需变更」——
人会陷入反复重跑。

## 新口径（裁定 A）

    新鲜 ⟺ 该层最近一次**成功** RUN 在 `STALE_AFTER` 内（**阈值只有这一处**，见文件中的常量）
            且（ change_state == "produced_changes"
                 或 (change_state == "no_new_input" 且 input_watermark == 上游当前水位) ）

三字段落章：

    executed_at      这一跑是什么时候（墙钟，秒）
    input_watermark  这一跑**读到**的上游水位（见 WATERMARK_SOURCES）
    change_state     produced_changes ｜ no_new_input ｜ blocked

## ★ 防假绿（硬要求，不许退化）

`no_new_input` **不许由本层自证**。本模块的 `judge()` 一律**现算**上游水位
（`current_watermark()` 直接读盘），与落章里的 `input_watermark` 比对：

    水位变了 ⇒ 判陈旧（**即使这层 1 分钟前刚跑过**）

⇒ 「只看跑过」这种退化**过不了反测 3**（见文件末 `selftest`）。
**若某层拿不到水位（无落章 / 老格式落章）⇒ 如实报「无法交叉验证」并回退到旧 mtime 判据**
（`fallback_used: True`），**不假装新鲜**。

## 水位怎么算

`(行数, 字节数)` 二元组 —— **确定性、可现算、不吃 IO**（不 sha256 28 MB 的 `units.jsonl`）。
选它是因为它足以察觉「上游改了」；真要逐字节比对是另一件事，不在本判据范围内。
"""
from __future__ import annotations

import json
import os
import time

#: 新鲜阈值（秒）—— **全库唯一一处**（`daily_health.py` / `freshness.py` / 日报都读它，别抄第二份）。
#:
#: ★★ 2026-10-16 Owner 裁定①：日更改**周更**（每周日 03:30）⇒ 阈值**必须 ≥ 一个周期**。
#:    否则一周里有 6 天各层全判「陈旧」⇒ 评审链 ②c 复判仍超期 ⇒ **全周拒答**；
#:    而且就绪巡检的受控自愈会**每天**把日更踢回来（冷却 45 分钟／当日 ≤3 次）⇒ 周更名存实亡。
#:    取值 = **7 天周期 + 1 天余量**：余量留给「周日那趟跑到一半失败、当天补跑」。
#: ⚠️ **放宽阈值 = 同时放宽了保护**：原先「跑挂了 24h 内就知道」，现在最长 **8 天**。
#:    兜这个缺口的是 `kb/l8/watch_review_readiness.py::check_weekly_run_ran()`（带受控自愈）
#:    —— **不是**靠把阈值调小，也不是靠人记得看日报。
#: ⚠️ 改这个数会同时影响两件事，改前先看这两处：`daily_digest.py` 的「新鲜度」段（读它）、
#:    `watch_review_readiness.py::check_freshness()`（陈旧 ⇒ 拒答级告警 + 自愈）。
STALE_AFTER = 8 * 86400

#: 给人看的写法 —— 判据文案里**只引用它**，别在别处再抄一遍「24h／8 天」（抄出去的第二份必然过期）。
STALE_AFTER_HUMAN = ("%g 天" % (STALE_AFTER / 86400.0) if STALE_AFTER >= 2 * 86400
                     else "%g 小时" % (STALE_AFTER / 3600.0))

#: 每层的**上游**水位来源（库根相对路径）。
#: ★ 只列**上游**，不列本层自己的产物 —— 列自己的产物就等于自证。
#: ★★ 只用**台账（manifest）**，**不用派生索引**（`index/*.jsonl`）：
#:    派生索引会被**内容未变的重算**整份重写（L1 的 OCR 回填就是），
#:    把它算进水位 ⇒ 水位**无故翻动** ⇒ 上游明明没变却判本层陈旧（假陈旧）。
#:    台账行数才是「上游有多少东西」的语义量。
WATERMARK_SOURCES = {
    "L0": ["l0/manifest.jsonl"],
    "L1": ["l0/manifest.jsonl"],
    "L2": ["l1/manifest_l1.jsonl"],
    "L3": ["l2/manifest_l2.jsonl"],
    "L4": ["l3/manifest_l3.jsonl"],
    "L5": ["l4/registry/l4.json"],
    "L6": ["l5/registry/l5.json"],
    "L7": ["l6/registry/l6.json"],
}

#: 三字段的合法取值
CHANGE_STATES = ("produced_changes", "no_new_input", "blocked")

#: 每层的**自身产物**（判「这一跑有没有产出变化」只看这些；上游不在其内）。
OUTPUT_SOURCES = {
    "L0": ["l0/manifest.jsonl"],
    "L1": ["l1/manifest_l1.jsonl", "l1/index/l1.jsonl"],
    "L2": ["l2/units.jsonl", "l2/manifest_l2.jsonl"],
    "L3": ["l3/candidates/rules.jsonl", "l3/rejected.jsonl", "l3/manifest_l3.jsonl"],
    "L4": ["l4/canonical/wording_entry.jsonl"],
    "L5": ["l5/p0_patterns.jsonl"],
    "L6": ["l6/selftest.json"],
    "L7": [],
}

RUNS_DIRNAME = os.path.join("l7", "registry")
SIDECAR_NAME = "layer_run_freshness.json"


def _stat_sig(path: str):
    """单个文件的水位签名：`{"lines": int|None, "bytes": int|None, "exists": bool}`。"""
    if not os.path.isfile(path):
        return {"lines": None, "bytes": None, "exists": False}
    n = 0
    try:
        with open(path, "rb") as fh:
            for _ in fh:
                n += 1
    except OSError:
        return {"lines": None, "bytes": None, "exists": True}
    return {"lines": n, "bytes": os.path.getsize(path), "exists": True}


def current_watermark(kb_root: str, layer: str):
    """**现算**该层的上游水位（读盘，不采信任何落章）。"""
    srcs = WATERMARK_SOURCES.get(layer or "")
    if srcs is None:
        return None
    return {rel: _stat_sig(os.path.join(kb_root, rel)) for rel in srcs}


def watermark_digest(wm) -> str:
    """把水位压成一个可比较的字符串（落章里存这个，便于人读与比对）。"""
    if not wm:
        return ""
    return "|".join("%s:%s:%s" % (k, v.get("lines"), v.get("bytes"))
                    for k, v in sorted(wm.items()))


def upstream_mtime(kb_root: str, layer: str):
    """本层上游**最新的改动时刻**（取 `WATERMARK_SOURCES` 各源的最大 mtime）。

    ★ 2026-10-10 加（Owner 同意「推荐 ①」）—— 专治**假陈旧**：
      `input_watermark` 记的是**驱动开跑那一刻**的水位（`measure()` 明写「测前的水位，避免自证」），
      而一趟日更要跑 ~45 分钟 ⇒ **上游在 run 中途变了**是常态，不是异常。
      实测 L7：快照 10:10 记 `l6.json`=26178，而它是 **L6 自己在 10:42:34** 写的（26180），
      L7 到 **10:50** 才跑 —— **本层处理的就是最新输入**，却被判陈旧 ⇒ 评审链拒答。
      ⇒ 判据需要的是**时间**（上游改动在本层运行**之前**还是**之后**），不是「快照 == 现状」。

    ⚠️ **拿不到就回 `None`**（文件缺失 / 权限）——**绝不回 0**：0 会让
      `mtime <= run_at` 恒真 ⇒ 把「无法证明」变成「证明新鲜」，是 fail-open。
      调用方见到 `None` 必须**保持陈旧**。
    """
    mtimes = []
    for rel in (WATERMARK_SOURCES.get(layer or "") or []):
        try:
            mtimes.append(os.path.getmtime(os.path.join(kb_root, rel)))
        except OSError:
            continue                      # 缺失/不可读 ⇒ 这一源不参与，且**不当作 0**
    return max(mtimes) if mtimes else None


def _fmt_ts(ts):
    """时间戳 → `HH:MM:SS`（判词里要给人看，`None` 原样写出来）。"""
    if not isinstance(ts, (int, float)):
        return str(ts)
    return time.strftime("%H:%M:%S", time.localtime(ts))


def make_fields(kb_root: str, layer: str, *, change_state: str,
                executed_at: float | None = None) -> dict:
    """给层引擎用的**落章三字段**生成器。

    用法（在层引擎写 `kb/<层>/runs/<RUN>.json` 之前合并进去）：

        from layer_freshness import make_fields
        rec.update(make_fields(KB_ROOT, "L2", change_state="no_new_input"))
    """
    if change_state not in CHANGE_STATES:
        raise ValueError("change_state 必须是 %s 之一，收到 %r" % (CHANGE_STATES, change_state))
    wm = current_watermark(kb_root, layer)
    return {
        "executed_at": float(executed_at if executed_at is not None else time.time()),
        "input_watermark": watermark_digest(wm),
        "input_watermark_sources": sorted((WATERMARK_SOURCES.get(layer) or [])),
        "change_state": change_state,
    }


def _latest_run_record(kb_root: str, layer: str):
    """该层 `runs/` 里**最新**的一份落章（按 mtime）：返回 `(mtime, dict|None, path)`。"""
    d = os.path.join(kb_root, layer.lower(), "runs")
    if not os.path.isdir(d):
        return None, None, None
    best = None
    for fn in os.listdir(d):
        if not fn.endswith(".json"):
            continue
        # ★ 干跑档不算「跑过」：`<RUN>-dryrun.json` 不落盘、不改变产物 ⇒ 不是一次成功 RUN。
        if "dryrun" in fn or "dry-run" in fn:
            continue
        p = os.path.join(d, fn)
        try:
            m = os.path.getmtime(p)
        except OSError:
            continue
        if best is None or m > best[0]:
            best = (m, p)
    if best is None:
        return None, None, None
    m, p = best
    try:
        with open(p, encoding="utf-8") as fh:
            return m, json.load(fh), p
    except Exception:                                    # noqa: BLE001
        return m, None, p


# ── 测量与落章（批次18 · 第0块）────────────────────────────────────────────────
def output_fingerprint(kb_root: str, layer: str):
    """该层**自身产物**的指纹（判「这一跑有没有产出变化」）。"""
    srcs = OUTPUT_SOURCES.get(layer or "")
    if srcs is None:
        return None
    return {rel: _stat_sig(os.path.join(kb_root, rel)) for rel in srcs}


def sidecar_path(kb_root: str) -> str:
    return os.path.join(kb_root, RUNS_DIRNAME, SIDECAR_NAME)


def load_sidecar(kb_root: str) -> dict:
    p = sidecar_path(kb_root)
    if not os.path.isfile(p):
        return {}
    try:
        with open(p, encoding="utf-8") as fh:
            return json.load(fh) or {}
    except Exception:                                    # noqa: BLE001
        return {}


def measure(kb_root: str, layer: str, *, change_state: str,
            out_before=None, wm_before: str | None = None,
            exit_code: int | None = None,
            run_id: str | None = None, note: str = "") -> dict:
    """测量一次运行并落章三字段（写 sidecar，**不碰层数据**）。

    **现算复核（两条，都是保守方向）**：
      · 给了 `out_before` 而产物指纹没变 ⇒ 把 `produced_changes` **降级**为 `no_new_input`
        （宁可保守，也不许把「没产出」报成「有产出」）。
      · 给了 `wm_before` ⇒ 落章 `input_watermark` = **测前**取的上游水位，
        并记录 `input_unchanged`（测前 == 测后）。
    """
    out_after = output_fingerprint(kb_root, layer)
    wm_after = watermark_digest(current_watermark(kb_root, layer))
    derived = change_state
    if out_before is not None:
        changed = (watermark_digest(out_before) != watermark_digest(out_after))
        if not changed and change_state == "produced_changes":
            derived = "no_new_input"
            note = (note + " ｜**现算降级**：产物指纹未变，"
                           "调用方声称 produced_changes 不成立 ⇒ no_new_input").strip(" ｜")
        elif changed and change_state == "no_new_input":
            derived = "produced_changes"
            note = (note + " ｜**现算升级**：产物指纹已变 ⇒ produced_changes").strip(" ｜")
    if exit_code not in (None, 0):
        derived = "blocked"
        note = (note + " ｜退出码 %s ⇒ blocked" % exit_code).strip(" ｜")

    wm_used = wm_before if wm_before is not None else wm_after
    fields = make_fields(kb_root, layer, change_state=derived)
    fields["input_watermark"] = wm_used          # ★ 落**测前**的水位（不是测后，避免自证）
    fields.update({
        "run_id": run_id,
        "measured_at": fields["executed_at"],
        "output_watermark": watermark_digest(out_after),
        "output_changed": None if out_before is None
        else (watermark_digest(out_before) != watermark_digest(out_after)),
        "input_watermark_after_run": wm_after,
        "input_unchanged": (wm_used == wm_after) if wm_before is not None else None,
        "exit_code": exit_code,
        "note": note,
        # ★ 观测 vs 补记：`measured` = 本函数包住一次真运行测出来的（**强**）；
        #   `seeded_from_disk` = `seed_freshness_sidecar.py` 事后补的（**弱**，见该脚本自述）。
        #   `judge()` 两处都认；但读者能分辨，且补记**不许覆盖**观测。
        "provenance": "measured",
    })
    sc = load_sidecar(kb_root)
    sc[layer] = fields
    p = sidecar_path(kb_root)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(sc, fh, ensure_ascii=False, indent=1, sort_keys=True)
    return fields


def _trace_exists(kb_root: str, layer: str, rid) -> bool:
    """sidecar 观测的 `run_id` 是否**能核对到一次真运行**（2026-10-03 加，收紧项）。

    **为什么加**：`judge()` 采信 `provenance=measured` 的 sidecar 时间，而 sidecar 是普通文件 ——
    实测（同 20:38）有**库外代码**把 L1/L4/L5/L6 补写成 `provenance=measured`（note 里自述是「补观测」），
    **把事后补记伪装成强档观测**，从而让 8 层瞬间「变新鲜」、绕过整道新鲜度闸门。
    本函数就是那条收紧：**观测必须指向一次真运行**。

    **判据为什么写成「精确匹配」而不是通配**（实测踩过，别改成通配）：
    那条伪造用的 rid 是 `REV-202610031826-momcozy-pump`，它的产物**只有**
    `kb/l7/runs/<rid>-L4.json` 这类**带后缀的记账件**与 `<layer>/runs/<rid>-L4-dryrun.json`
    **干跑件** —— 而库规明写**「干跑档不算跑过」**（见 `_latest_run_record` 的 dryrun 过滤）。
    ⇒ 若用 `<rid>*` 通配，那条伪造**照样过**；只有**精确匹配**才抓得住它。

    认三种**精确**形态（都出现才算「真跑过」）：
      · `kb/l7/runs/<rid>.json`        —— 编排器每层的记账件（长这样，不带后缀）
      · `kb/<layer>/runs/<rid>.json`   —— 该层自己的落章（精确同名，不含 dryrun）
      · `kb/l8/runs/<rid>-l0-align.json` —— L0 每日对齐的回执

    ★ **不许加"兜底通配"**（本函数第一版加过 `<rid>-*.json`，实测**把洞又打开了**）：
      那条伪造的 `<rid>` 正好有 `kb/l7/runs/<rid>-L4.json` 这类层记账件 ⇒ 通配一匹配就放行。
      **三种精确形态已经够用**（日更 L0–L6 命中第一种、L7 用 `_newest_l7_run()` 取真产物名命中第一种）。
    """
    if not rid:
        return False
    pats = [
        os.path.join(kb_root, "l7", "runs", "%s.json" % rid),
        os.path.join(kb_root, layer.lower(), "runs", "%s.json" % rid),
        os.path.join(kb_root, "l8", "runs", "%s-l0-align.json" % rid),
    ]
    return any(os.path.exists(p) for p in pats)


def judge(kb_root: str, layer: str, now: float | None = None):
    """判断单层新鲜度。返回 dict（含 `fresh` / `reason` / `fallback_used`）。

    **本函数只报事实与判据，不写任何东西。**
    """
    now = time.time() if now is None else now
    out = {
        "layer": layer,
        "fresh": False,
        "reason": "",
        "fallback_used": False,
        "run_path": None,
        "run_at": None,
        "run_age": None,
        "change_state": None,
        "input_watermark": None,
        "current_watermark": None,
        "watermark_match": None,
    }

    run_m, rec, run_p = _latest_run_record(kb_root, layer)
    out["run_path"] = os.path.relpath(run_p, kb_root) if run_p else None

    # 落章里声明的执行时间优先（引擎写的 executed_at）；没有就退回落章文件 mtime
    exec_at = None
    _src = "落章"
    if isinstance(rec, dict):
        for k in ("executed_at",):
            v = rec.get(k)
            if isinstance(v, (int, float)) and v > 0:
                exec_at = float(v)
        if exec_at is None:
            for k in ("at",):
                v = rec.get(k)
                if isinstance(v, str) and len(v) >= 19:
                    try:
                        exec_at = time.mktime(time.strptime(v[:19], "%Y-%m-%dT%H:%M:%S"))
                    except ValueError:
                        exec_at = None
    if exec_at is None and run_m is not None:
        exec_at = run_m
        _src = "落章文件 mtime"

    out["run_at"] = exec_at
    # ★ 修复4（2026-10-03）：**时间来源必须可见**。原实现只有 `run_at` / `run_age` 两个数，
    #   没人知道这个时间是落章里写的、还是文件 mtime、还是（见下）sidecar 的 —— 排查时会被带偏。
    out["run_at_source"] = _src
    if exec_at is not None:
        out["run_age"] = now - exec_at

    cs = (rec or {}).get("change_state")
    wm = (rec or {}).get("input_watermark")
    # ★ 2026-10-10：**先留一份落章时间** —— 下面 sidecar 分支会把 `exec_at` 更新成「两边取较新」，
    #   而判「上游改动是在本层运行之前还是之后」要的是**保守下界**（宁可判陈旧）。
    #   不先留，落章时间就被较新的 sidecar 时间盖掉 ⇒ 判据会偏松（fail-open 方向）。
    _rec_at = exec_at
    #: 本层运行时刻的**保守下界**（落章 vs sidecar 观测，取小）。全程只增不减之外的唯一例外。
    _run_lo = None
    exec_at = exec_at if (cs in CHANGE_STATES and wm) else exec_at

    # 落章里没有三字段 ⇒ 找 **sidecar**（`measure()` 写的测量档）。
    # 为什么两处都要看：层引擎自己的落章格式五花八门（L2 有 applied/new_units，
    # L3 只有 counters），**逐个改引擎既慢又易漏**；`measure()` 是**中心化测量**，
    # 它落三字段到 sidecar，本函数优先用落章、落章没有再取 sidecar。
    sidecar_used = False
    if cs not in CHANGE_STATES or not wm:
        _sc = (load_sidecar(kb_root) or {}).get(layer) or {}
        if _sc.get("change_state") in CHANGE_STATES and _sc.get("input_watermark"):
            cs, wm = _sc["change_state"], _sc["input_watermark"]
            sidecar_used = True
            # ★ 修复2（2026-10-03）：**落章时间与 sidecar 观测时间，取较新者**。
            #   为什么不是"落章无条件优先"（第一版改法，实测不够）：幂等层跑完**不留新落章**
            #   —— 实测 L1/L3/L5/L6 的落章 mtime 停在 10-02 21:02（23.6h），24 分钟后照样翻红；
            #   而它们当天 08:31 **确实跑过**，只是没有产物能证明。所以两边都要认，谁新用谁。
            #   为什么认 sidecar 的时间要加 `provenance == "measured"` 条件：
            #   `seeded_from_disk` 是 `seed_freshness_sidecar.py` **事后补记**的（该脚本自述
            #   「补记，非观测……不构成该次运行当时上游是什么的证明」）⇒ 它的 `executed_at`
            #   不构成"跑过"的证据，**不认**。
            _ea = _sc.get("executed_at")
            _rid = _sc.get("run_id")
            _traced = _trace_exists(kb_root, layer, _rid)
            # ★★ 2026-10-10：**运行时刻的保守下界** —— 只要 sidecar 这次观测可信，
            #   就把它与落章时间**取小**，**不管哪个更新**。
            #   为什么非这样不可（自查发现的偏松）：`exec_at` 会被「谁新用谁」顶大，
            #   而 `_latest_run_record` 认的是**该层目录里最新的 run 记录** ——
            #   实测 L7 的 `exec_at` 被 `kb/l7/runs/20261010-1056.json`（`daily_health` 的记账，
            #   L7 实际是 **10:50** 跑的）顶到 11:03 ⇒ 判「上游早于运行」的窗口被白白放宽 13 分钟。
            #   判据方向必须**保守**（宁可判陈旧），所以这里不能跟着「谁新用谁」走。
            if (_sc.get("provenance") == "measured" and _traced
                    and isinstance(_ea, (int, float)) and _ea > 0):
                _cand = [x for x in (_rec_at, float(_ea)) if isinstance(x, (int, float))]
                _run_lo = min(_cand) if _cand else None
            if (_sc.get("provenance") == "measured" and _traced
                    and isinstance(_ea, (int, float)) and _ea > 0
                    and (exec_at is None or float(_ea) > exec_at)):
                exec_at = float(_ea)
                _src = "sidecar 观测（provenance=measured＋run_id 已核对）"
            elif _sc.get("provenance") == "measured" and not _traced:
                # ★ 收紧项（2026-10-03）：measured 但找不到对应真运行 ⇒ **不采信它的时间**，
                #   退回落章时间；并把拒绝原因如实写出来（不静默）。
                out["sidecar_time_rejected"] = (
                    "sidecar 声称 provenance=measured，但 run_id=%r 核对不到对应真运行"
                    "（认 kb/l7/runs/<rid>.json ／ <layer>/runs/<rid>.json ／ "
                    "kb/l8/runs/<rid>-l0-align.json）⇒ **不采信它的时间**，退回落章时间" % _rid)
            # ★ 修复4（同日）：`run_at` 与 `run_age` **同源更新**。
            #   原实现只更新 `run_age` 不更新 `run_at` ⇒ 同一份输出里
            #   `run_at=当天08:31` 与 `run_age=31.2h` **自相矛盾**，把排查带偏（本次实测踩到）。
            out["run_at"] = exec_at
            out["run_at_source"] = _src
            out["run_age"] = (now - exec_at) if exec_at is not None else None
    out["sidecar_used"] = sidecar_used

    out["change_state"] = cs
    out["input_watermark"] = wm

    # ① 两处都没有三字段 ⇒ 回退旧 mtime 口径，如实标注（**不假装新鲜**）
    if cs not in CHANGE_STATES or not wm:
        out["fallback_used"] = True
        out["reason"] = ("该层落章与 sidecar 都没有 `change_state`/`input_watermark`"
                         "⇒ **无法做水位交叉验证**，回退到旧 mtime 口径")
        return out

    # ② 在 STALE_AFTER 内跑过没有
    if exec_at is None or (now - exec_at) > STALE_AFTER:
        out["reason"] = ("最近一次成功 RUN 距今 %s 小时（> %s）⇒ 陈旧"
                         % (round((now - (exec_at or 0)) / 3600.0, 1), STALE_AFTER_HUMAN))
        return out

    if cs == "blocked":
        out["reason"] = "最近一次 RUN 的 `change_state=blocked` ⇒ 不算跑过 ⇒ 陈旧"
        return out

    if cs == "produced_changes":
        out["fresh"] = True
        out["reason"] = ("%s 内跑过且 `change_state=produced_changes` ⇒ 新鲜"
                         % STALE_AFTER_HUMAN)
        return out

    # ③ ★ 防假绿的核心：`no_new_input` **必须**用现算水位交叉验证
    cur = current_watermark(kb_root, layer)
    out["current_watermark"] = watermark_digest(cur)
    match = (out["current_watermark"] == out["input_watermark"])
    out["watermark_match"] = match
    # 测前后水位一致（measure 现算）也算交叉验证通过 —— 两条证据任一成立即可，
    # 但**都不成立就判陈旧**，绝不放行。
    _sc_rec = (load_sidecar(kb_root) or {}).get(layer) or {}
    _iu = _sc_rec.get("input_unchanged")
    out["input_unchanged_at_run"] = _iu
    if match or _iu is True:
        out["fresh"] = True
        out["reason"] = ("%s 内跑过；`change_state=no_new_input` 且" % STALE_AFTER_HUMAN +
                         "**上游水位交叉验证通过**（%s）⇒ 新鲜（无可处理的输入）"
                         % ("现算水位与落章一致" if match else "该次运行测前测后水位一致"))
    else:
        # ★★ 2026-10-10（Owner 同意「推荐 ①」）：**先问时间，再判陈旧**。
        #   病灶：`input_watermark` 是**驱动开跑那一刻**的快照，而一趟日更要跑 ~45 分钟
        #   ⇒ 上游在 run **中途**变了是常态。实测 L7：快照 10:10 记 `l6.json`=26178，
        #   而它是 **L6 自己在 10:42:34** 写的（26180），L7 到 **10:50** 才跑 ——
        #   本层处理的就是最新输入，却被判陈旧 ⇒ 评审链拒答。
        #   ⚠️ 下面这条**只把「本来要判陈旧」翻成新鲜**，且**必须有 mtime 正证据**：
        #      `upstream_mtime()` 回 `None`（上游缺失/不可读）⇒ **保持陈旧**（fail-closed，不许猜）；
        #      上游改动**晚于**本层运行 ⇒ **保持陈旧** —— 那正是真陈旧的形状
        #      （实测事故：L1 落章 06:49:07，`l0/manifest.jsonl` 06:55:48 才被追加 ⇒ 自测反测3 守着）。
        _up = upstream_mtime(kb_root, layer)
        _lo = _run_lo if _run_lo is not None else exec_at
        out["upstream_mtime"] = _up
        out["run_lower_bound"] = _lo
        out["upstream_settled_before_run"] = bool(
            _up is not None and _lo is not None and _up <= _lo)
        if out["upstream_settled_before_run"]:
            out["fresh"] = True
            out["reason"] = (
                "%s 内跑过；`change_state=no_new_input`，水位差（%s ≠ %s）**不是本层之后的变化** —— "
                "上游最新改动 %s **早于**本层这次运行 %s ⇒ 本层处理的就是最新输入 ⇒ 新鲜"
                % (STALE_AFTER_HUMAN, out["input_watermark"], out["current_watermark"],
                   _fmt_ts(_up), _fmt_ts(_lo)))
        else:
            out["reason"] = ("%s 内跑过，但 `change_state=no_new_input` 而" % STALE_AFTER_HUMAN +
                             "**上游水位已变**（落章 %s ≠ 现状 %s）⇒ **判陈旧**"
                             "（防假绿：不许自证）%s"
                             % (out["input_watermark"], out["current_watermark"],
                                "；上游最新改动 %s **晚于**本层运行 %s"
                                % (_fmt_ts(_up), _fmt_ts(_lo)) if _up is not None and _lo is not None
                                else "；上游 mtime 取不到 ⇒ **无证据可翻绿，保持陈旧**"))
    return out


def judge_all(kb_root: str, now: float | None = None):
    """八层全判（L0–L7）。"""
    return [judge(kb_root, "L%d" % i, now=now) for i in range(8)]


# ── 自测（反测 1/2/3 的夹具都走这里）────────────────────────────────────────────
def _selftest():
    import tempfile
    ok = True

    def mk(root, layer, *, age_s, cs, wm):
        d = os.path.join(root, layer.lower(), "runs")
        os.makedirs(d, exist_ok=True)
        rec = {"run_id": "fixture", "executed_at": time.time() - age_s,
               "change_state": cs, "input_watermark": wm}
        p = os.path.join(d, "fixture.json")
        with open(p, "w", encoding="utf-8") as fh:
            json.dump(rec, fh)
        os.utime(p, (time.time() - age_s, time.time() - age_s))
        return p

    with tempfile.TemporaryDirectory() as t:
        # 造 L2 的上游（l1/manifest_l1.jsonl, l1/index/l1.jsonl）
        os.makedirs(os.path.join(t, "l1", "index"), exist_ok=True)
        for rel in ("l1/manifest_l1.jsonl", "l1/index/l1.jsonl"):
            with open(os.path.join(t, rel), "w", encoding="utf-8") as fh:
                fh.write("a\nb\nc\n")
        wm = watermark_digest(current_watermark(t, "L2"))

        # 反测1：5 分钟前跑过、水位一致、no_new_input ⇒ 新鲜
        mk(t, "L2", age_s=300, cs="no_new_input", wm=wm)
        r = judge(t, "L2")
        print("  反测1 5分钟前+水位一致 →", "新鲜 ✅" if r["fresh"] else "陈旧 ❌（%s）" % r["reason"])
        ok &= r["fresh"]

        # 反测2：超过阈值没跑 ⇒ 陈旧
        # ★ 2026-10-16：夹具**相对常量取值**，不再写死「30 小时」。阈值从 24h 改成 8 天
        #   （周更，Owner 裁定①）时，写死的那条会**把正确改动判成故障** —— 本库最忌讳的检查器。
        mk(t, "L2", age_s=STALE_AFTER + 2 * 3600, cs="no_new_input", wm=wm)
        r = judge(t, "L2")
        print("  反测2 超阈值(%s+)没跑  →" % STALE_AFTER_HUMAN,
              "陈旧 ✅" if not r["fresh"] else "新鲜 ❌")
        ok &= (not r["fresh"])

        # ★ 反测2b（**反向对照**）：刚在阈值**以内** ⇒ 新鲜。
        #   没有它的话，「把阈值改成 0（谁都判陈旧）」反测2 照样绿 ⇒ 尺子恒真。
        mk(t, "L2", age_s=STALE_AFTER - 2 * 3600, cs="no_new_input", wm=wm)
        r = judge(t, "L2")
        print("  反测2b 阈值以内(%s-)   →" % STALE_AFTER_HUMAN,
              "新鲜 ✅" if r["fresh"] else "陈旧 ❌（%s）" % r["reason"])
        ok &= r["fresh"]

        # 反测3：刚跑过、但上游水位变了 ⇒ 陈旧（防假绿）
        mk(t, "L2", age_s=60, cs="no_new_input", wm=wm)
        with open(os.path.join(t, "l1", "manifest_l1.jsonl"), "a", encoding="utf-8") as fh:
            fh.write("d\n")                                   # 上游变了
        r = judge(t, "L2")
        print("  反测3 刚跑过+水位变了  →", "陈旧 ✅" if not r["fresh"] else "新鲜 ❌（退化成只看跑过！）")
        ok &= (not r["fresh"])

        # 反测4（补充）：刚跑过 + produced_changes ⇒ 新鲜（不看水位）
        mk(t, "L2", age_s=60, cs="produced_changes", wm="STALE-WM")
        r = judge(t, "L2")
        print("  反测4 刚跑过+有产出    →", "新鲜 ✅" if r["fresh"] else "陈旧 ❌")
        ok &= r["fresh"]

        # 反测5（补充）：老格式落章（无三字段）⇒ 回退旧口径并标注
        d = os.path.join(t, "l3", "runs")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "old.json"), "w", encoding="utf-8") as fh:
            json.dump({"run_id": "old"}, fh)
        r = judge(t, "L3")
        print("  反测5 老格式落章        →", "回退旧口径 ✅" if r["fallback_used"] else "❌")
        ok &= r["fallback_used"]

        # ★ 反测6（2026-10-10 加，Owner 同意「推荐 ①」）：**上游改动在本层运行之前** ⇒ 新鲜。
        #   这是当天实测的 L7 形状：水位差是真的（驱动开跑快照 ≠ 现状），但那次变化发生在
        #   **本层运行之前**（L6 在 10:42:34 写 l6.json，L7 到 10:50 才跑）⇒ 本层处理的就是最新输入。
        #   夹具：水位仍写旧值（制造 mismatch），再把上游 mtime **往回拨到运行时刻之前**。
        mk(t, "L2", age_s=600, cs="no_new_input", wm="OLD-WM")        # 10 分钟前跑过
        _p = os.path.join(t, "l1", "manifest_l1.jsonl")
        _now = time.time()
        os.utime(_p, (_now - 900, _now - 900))                        # 上游 15 分钟前就定稿了
        r = judge(t, "L2")
        print("  反测6 上游早于本次运行 →",
              "新鲜 ✅" if r["fresh"] else "陈旧 ❌（假陈旧没修掉：%s）" % r["reason"])
        ok &= r["fresh"]

        # ★ 反测7（fail-closed，本次改动的**反向对照**）：上游**取不到 mtime** ⇒ **保持陈旧**。
        #   防止有人把 `upstream_mtime()` 写成「拿不到就当 0/当新鲜」——
        #   **无法证明 ≠ 证明新鲜**，这一条守住就把 fail-open 方向堵死。
        mk(t, "L6", age_s=600, cs="no_new_input", wm="OLD-WM")        # L6 上游 l5/registry/l5.json 不存在
        r = judge(t, "L6")
        print("  反测7 上游缺失         →",
              "陈旧 ✅" if not r["fresh"] else "新鲜 ❌（fail-open：无法证明被当成了新鲜！）")
        ok &= (not r["fresh"])

        # ★ 反测8（2026-10-10，钉**保守方向**）：`exec_at` 会被「谁新用谁」顶大 ——
        #   `_latest_run_record` 认的是该层目录里**最新**的 run 记录，而那可能是**与本层无关**的
        #   别的 run（实测 L7 被 `kb/l7/runs/20261010-1056.json`＝`daily_health` 的记账，
        #   从真实的 10:50 顶到 11:03）⇒ 判「上游早于本次运行」的窗口被白白放宽 13 分钟。
        #   ⇒ 下界必须取 sidecar 与落章的**较小者**，**不跟「谁新用谁」走**。
        #   夹具：落章**很新**（1 分钟前）、sidecar 观测**较旧**（20 分钟前），
        #        上游 mtime 卡在两者**之间**（10 分钟前）⇒ **必须判陈旧**。
        #        （把下界改成 `exec_at` ⇒ 这条**精确变红**。）
        mk(t, "L2", age_s=60, cs=None, wm=None)          # 最新的落章：1 分钟前（无三字段 ⇒ 走 sidecar）
        with open(os.path.join(t, "l2", "runs", "fixture-obs.json"), "w", encoding="utf-8") as fh:
            json.dump({"run_id": "fixture-obs"}, fh)
        _scp = sidecar_path(t)
        os.makedirs(os.path.dirname(_scp), exist_ok=True)
        with open(_scp, "w", encoding="utf-8") as fh:
            json.dump({"L2": {"change_state": "no_new_input", "input_watermark": "OLD-WM",
                              "provenance": "measured", "run_id": "fixture-obs",
                              "executed_at": _now - 1200, "input_unchanged": False,
                              "note": "自测夹具"}}, fh)
        os.utime(_p, (_now - 600, _now - 600))           # 上游 10 分钟前改动（夹在 20 与 1 之间）
        r = judge(t, "L2")
        print("  反测8 下界不被无关run顶大 →",
              "陈旧 ✅" if not r["fresh"] else "新鲜 ❌（下界被更晚的无关 run 顶大了！）")
        ok &= (not r["fresh"])

    print("\n自测：", "全部通过 ✅" if ok else "**有失败 ❌**")
    return 0 if ok else 1


if __name__ == "__main__":
    import subprocess
    import sys as _s

    # ── ① 自测 ──────────────────────────────────────────────────────────────
    if len(_s.argv) > 1 and _s.argv[1] == "selftest":
        _s.exit(_selftest())

    # 用法（**子命令在 argv[1:3]，其余原样透传** —— 不用 argparse 的 REMAINDER，
    # 它会把 `--flag value` 拆错，实测踩到过）：
    #   kb/kbpy l7/scripts/layer_freshness.py judge  L2
    #   kb/kbpy l7/scripts/layer_freshness.py measure L2 --change-state no_new_input -- <命令…>
    if len(_s.argv) < 3 or _s.argv[1] not in ("judge", "measure"):
        print(__doc__.split("## 水位怎么算")[0])
        print("用法：")
        print("  kb/kbpy l7/scripts/layer_freshness.py judge   <L0..L7>")
        print("  kb/kbpy l7/scripts/layer_freshness.py measure <L0..L7> "
              "[--change-state X] [--run-id R] [--note N] [--kb-root P] -- <命令…>")
        print("  kb/kbpy l7/scripts/layer_freshness.py selftest")
        _s.exit(2)

    MODE, LAYER = _s.argv[1], _s.argv[2]
    tail = _s.argv[3:]
    KBROOT = None
    for i, tok in enumerate(tail):
        if tok == "--kb-root" and i + 1 < len(tail):
            KBROOT = tail[i + 1]
    _KB = os.path.abspath(KBROOT) if KBROOT else os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    if MODE == "judge":
        _j = judge(_KB, LAYER)
        print(json.dumps(_j, ensure_ascii=False, indent=1))
        _s.exit(0 if _j["fresh"] else 1)

    # ── measure ─────────────────────────────────────────────────────────────
    cs, rid, note = "produced_changes", None, ""
    cmd = []
    it = iter(range(len(tail)))
    i = 0
    while i < len(tail):
        tok = tail[i]
        if tok == "--":
            cmd = tail[i + 1:]
            break
        if tok in ("--change-state", "--run-id", "--note", "--kb-root") and i + 1 < len(tail):
            v = tail[i + 1]
            if tok == "--change-state":
                cs = v
            elif tok == "--run-id":
                rid = v
            elif tok == "--note":
                note = v
            i += 2
            continue
        cmd.append(tok)
        i += 1
    del it
    if cs not in CHANGE_STATES:
        print("--change-state 必须是 %s" % (CHANGE_STATES,), file=_s.stderr)
        _s.exit(2)
    if not cmd:
        print("measure 需要命令：… measure L2 --change-state no_new_input -- kb/kbpy <引擎> …",
              file=_s.stderr)
        _s.exit(2)

    before = output_fingerprint(_KB, LAYER)
    wm_before = watermark_digest(current_watermark(_KB, LAYER))
    print("── measure %s ── 测前上游水位 %s" % (LAYER, wm_before or "(无)"))
    rc = subprocess.call(cmd)
    f = measure(_KB, LAYER, change_state=cs, out_before=before,
                wm_before=wm_before, exit_code=rc, run_id=rid, note=note)
    print("   落章：executed_at=%s change_state=%s" % (round(f["executed_at"]), f["change_state"]))
    print("         input_watermark(测前)=%s" % (f["input_watermark"] or "(无)"))
    print("         input_unchanged=%s  output_changed=%s"
          % (f["input_unchanged"], f["output_changed"]))
    print("   → %s" % sidecar_path(_KB))
    _s.exit(rc)
