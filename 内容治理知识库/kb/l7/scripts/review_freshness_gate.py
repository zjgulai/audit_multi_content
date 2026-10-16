#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""review_freshness_gate.py —— 评审链的 **fail-closed 前置条件**（批次19 · 第1块）。

## 它解决什么

`kb/l7/scripts/freshness.py` 早就判「关键 data 产物超期 ⇒ **应拒答（退出码 3）**」，
但那只是**一个脚本的退出码** —— **评审链照样给 PASS/BLOCK**。
⇒ 缺的不是「规则」，是 **fail-closed 的接线**：判据必须**挡住结论**，而不只是打一行字。

## 为什么单独成件（而不是在每条入口各写一遍）

两条入口都要接（用户点名）：
  · **agent/skill 入口**：`kb-content-review/scripts/review.py`（`main()` 里）
  · **API 入口**：`kb_api.py` 的 `POST /review`（`do_review`）
同一判据写两遍必然分叉 —— 本库已因「同一判据算两遍」返工多次
（`freshness.py` 顶部记的「3 vs 6 分叉」就是同一类病）。
⇒ 判据只在本文件里一份，两条入口**都调它**。

## 判据（读 daily_health 的**机读产物**，不自己重算）

    `kb/l7/reports/daily-health-latest.json → stale_layers`

非空 ⇒ **拒答**。空 ⇒ 放行。
★ **不自己重算**：`freshness.py` 已经定过这条纪律（「陈旧结论直接读它的，不自己算」），
  本文件沿用 —— 同一判据算两遍必然分叉。

## 拒答时给什么（用户要求：明写是哪件产物、超期多久、该跑哪层）

`check()` 返回的 `stale` 逐条带：层 / 产物路径 / 距今多久 / 判据原因。

## 退出码（与 `freshness.py`、`review.py` 既有约定一致）

    0 = 放行 ｜ 3 = 拒答（**与 review.py 的「拒答」退出码同一个**）｜ 2 = 判据读不到

★ **判据读不到也拒答（fail-closed）**：日报缺失 / 读不出 ⇒ **不许当成新鲜**。
  这是 fail-closed 的本义 —— 「不知道新不新鲜」不等于「新鲜」。
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
KB = os.path.dirname(os.path.dirname(HERE))          # …/kb
KBPY = os.path.join(KB, "kbpy")
DAILY = os.path.join(KB, "l7", "reports", "daily-health-latest.json")

EXIT_OK, EXIT_REFUSE, EXIT_UNREADABLE = 0, 3, 2

# ══════════════════════════════════════════════════════════════════════════════
# 批30 · 评审前置「自动跑层」—— 把「先跑 L4–L6 再出结论」落成**代码强制**
#
# 为什么必须落代码（库内先例，`kb-content-review/scripts/review.py:1326-1332` 原文）：
#   「**没有任何代码强制** ⇒ 不读正文、或读了不照做，就绕过去了。
#     ⇒ 本条把它落成**确定性阻断**……不靠 SKILL.md 文字、不靠 LLM 自觉。」
# 本块照同一先例办：陈旧 ⇒ **先跑命中层**，跑完复判；跑不动/跑挂/仍陈旧 ⇒ 照旧 fail-closed。
#
# 三条不许（批30 封顶令）：
#   · 不许加 `--apply`（真写库要单独报批）
#   · 不许带 `--write-gate`
#   · 不许放宽 fail-closed（跑层失败/超时 ⇒ **必须仍然拒答**）
# ══════════════════════════════════════════════════════════════════════════════

AUTORUN_LAYERS = ("L4", "L5", "L6")     # L0–L3 只作溯源终点；L7 是闸门不在此列
AUTORUN_TIMEOUT = 180                   # 秒
#: ★ 修复4（2026-10-03）：超时后先 SIGTERM 让 `kb_pipeline.py` 的 `finally: release_lock()` 收尾，
#: 最多等这么多秒；仍不收尾才 SIGKILL（SIGKILL 拦不住，只能接受并把残留锁记进台账）。
AUTORUN_TERM_GRACE = 20                 # 秒
AUTORUN_NDJSON = os.path.join(KB, "l7", "registry", "freshness_autorun.ndjson")
_LAYERS_YAML = os.path.join(KB, "l7", "registry", "layers.yaml")


def _autorun_enabled() -> bool:
    """开关：`KB_FRESHNESS_AUTORUN`（默认开）。仿 `--skip-freshness-gate` 那套。"""
    return os.environ.get("KB_FRESHNESS_AUTORUN", "1").strip().lower() not in (
        "0", "false", "off", "no", "")


def layer_skills(kb_root: str, layers=AUTORUN_LAYERS) -> dict:
    """**从 `layers.yaml` 各层 `skill:` 字段派生** 层→skill 列表。

    ★ 不许硬编码、不许手抄 —— `layers.yaml` 自己警告过「复制出去的第二份必然过期」。
      这也是批30 §2.3 明写的硬要求（`--invoked` 必须派生）。
    """
    try:
        import yaml                                # PyYAML 6.0.3（实测可用）
    except Exception:                              # noqa: BLE001
        return {L: [] for L in layers}             # 取不到 ⇒ 空 ⇒ 上层记为「跑不成」并拒答
    # ★ 批30 修：两条入口传的 `kb_root` 约定**不一致**，实测：
    #   · `review.py` 的 `_find_root()` 返回 **workspace 根**（`…/内容治理`）
    #   · `kb_api.py` 的 `_KBRoot()` = `dirname(KB)` 也是 **workspace 根**
    #   而 `layers.yaml` 在 `<库根>/kb/l7/registry/`。原写法只认「kb_root 就是 kb 目录」，
    #   于是两条入口**都取不到**、自动跑层静默不触发。⇒ 三种落点依次试，最后回退到本模块自己的 KB。
    cands = [os.path.join(kb_root, "l7", "registry", "layers.yaml"),
             os.path.join(kb_root, "kb", "l7", "registry", "layers.yaml"),
             _LAYERS_YAML]
    p = next((c for c in cands if os.path.isfile(c)), None)
    if p is None:
        return {L: [] for L in layers}
    try:
        with open(p, encoding="utf-8") as fh:
            doc = yaml.safe_load(fh)
    except Exception:                                  # noqa: BLE001
        return {L: [] for L in layers}
    found = {}

    def walk(o):
        if isinstance(o, dict):
            if "layer" in o and "skill" in o:
                found[str(o["layer"])] = [str(s) for s in (o.get("skill") or [])]
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(doc)
    return {L: found.get(L, []) for L in layers}


def _audit(kb_root: str, rec: dict) -> None:
    """每次自动跑层**必写审计**（一行一跑），供事后核「跑了没 / 跑哪层 / 多久 / 前后」。"""
    try:
        os.makedirs(os.path.dirname(AUTORUN_NDJSON), exist_ok=True)
        with open(AUTORUN_NDJSON, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:                                  # noqa: BLE001
        pass                                           # 审计写不动**不许**影响判定


def autorun_stale_layers(kb_root: str, info: dict) -> dict:
    """陈旧层（过滤成 L4–L6）⇒ 先跑它们。返回本次跑的记录（同时落审计）。"""
    all_stale = list(info.get("stale_layers") or [])
    stale = [L for L in all_stale if L in AUTORUN_LAYERS]
    rec = {
        "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "enabled": _autorun_enabled(),
        "before_stale_layers": all_stale,
        "stale_in_scope": stale,
        "stale_out_of_scope": [L for L in all_stale if L not in AUTORUN_LAYERS],
        "attempted": False, "layers": stale, "skills": {},
        "elapsed_sec": None, "returncode": None, "ok": False, "why": "",
    }
    if not rec["enabled"]:
        rec["why"] = "KB_FRESHNESS_AUTORUN 关闭 ⇒ 不跑层，按原判据拒答"
        _audit(kb_root, rec)
        return rec
    if not stale:
        rec["why"] = ("超期层不含 L4–L6（%s）⇒ 不跑层；L0–L3 只作溯源终点、L7 是闸门"
                      % (",".join(all_stale) or "无"))
        _audit(kb_root, rec)
        return rec

    skills = layer_skills(kb_root, tuple(stale))
    rec["skills"] = skills
    missing = [L for L in stale if not skills.get(L)]
    if missing:
        # `--invoked` 派生不出来 ⇒ **不猜**、也不硬编；如实记为跑不成
        rec["why"] = ("layers.yaml 取不到 %s 的 skill: 字段 ⇒ 不跑（不许手抄兜底）"
                      % ",".join(missing))
        _audit(kb_root, rec)
        return rec

    run_id = time.strftime("%Y%m%d-%H%M%S") + "-autorun"
    cmd = ["sh", KBPY, "l7/scripts/kb_pipeline.py", "--sync", "--via-skill",
           "--only", ",".join(stale), "--run", run_id]
    for L in stale:
        for s in skills[L]:
            cmd += ["--invoked", s]
    # ★ 不带 --apply、不带 --write-gate（批30 封顶令）
    rec["cmd"] = " ".join(cmd[2:])
    rec["run_id"] = run_id
    rec["attempted"] = True
    t0 = time.time()
    # ★ 修复4（2026-10-03）：**别再用 `subprocess.run(timeout=)`** —— 它超时直接 SIGKILL，
    #   而 `kb_pipeline.py` 的锁是在 `finally: release_lock()` 里放的（:958），
    #   进程被 SIGKILL ⇒ finally 跑不到 ⇒ **锁留在 kb/.work/.kb.lock**。
    #   实测代价：2026-10-03 18:53:13 漏下 `run_id=20261003-185311-autorun` 那把锁，
    #   **挡停了随后的一次日更**（`L1 写档 → exit=2`，日更「遇红即停」）。
    #   改法：先 SIGTERM（`kb_pipeline` 已把 SIGTERM 转成 SystemExit ⇒ finally 会跑 ⇒ 锁释放），
    #   给 `AUTORUN_TERM_GRACE` 秒收尾；仍不收尾才 SIGKILL。收尾后再核一次锁，如实记录。
    try:
        pr = subprocess.Popen(cmd, cwd=os.path.dirname(kb_root), stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, text=True)
        try:
            out, err = pr.communicate(timeout=AUTORUN_TIMEOUT)
            rec["returncode"] = pr.returncode
            rec["stdout_tail"] = (out or "")[-1200:]
            rec["stderr_tail"] = (err or "")[-600:]
            rec["ok"] = (pr.returncode == 0)
            if not rec["ok"]:
                rec["why"] = "跑层退出码 %s ⇒ 不认为已刷新" % pr.returncode
        except subprocess.TimeoutExpired:
            rec["timeout_sec"] = AUTORUN_TIMEOUT
            pr.terminate()                          # SIGTERM：让 finally 放锁
            try:
                out, err = pr.communicate(timeout=AUTORUN_TERM_GRACE)
                rec["killed"] = "sigterm"
                rec["why"] = ("跑层超时（%ss）⇒ 已 SIGTERM 收尾（锁应由 finally 释放）"
                              % AUTORUN_TIMEOUT)
            except subprocess.TimeoutExpired:
                pr.kill()                           # SIGKILL：拦不住，只能接受
                out, err = pr.communicate()
                rec["killed"] = "sigkill"
                rec["why"] = ("跑层超时（%ss）且 SIGTERM 在 %ss 宽限内未收尾 ⇒ SIGKILL"
                              "（**锁可能残留**，按 lock.held_dead 口径人工处置）"
                              % (AUTORUN_TIMEOUT, AUTORUN_TERM_GRACE))
            rec["stdout_tail"] = (out or "")[-1200:]
            rec["stderr_tail"] = (err or "")[-600:]
            rec["ok"] = False
    except Exception as e:                             # noqa: BLE001
        rec["why"] = "跑层抛错：%r" % (e,)
    finally:
        # 收尾后核一次锁：**是不是我们留下的**，如实写进台账。
        # ★ **不自动撬锁** —— 库规要求「先 `--check` 判有没有写坏，再删锁」，那一步该由人做；
        #   这里只负责让它**不可能被忽略**。
        try:
            _lk = os.path.join(kb_root, ".work", ".kb.lock")
            if os.path.exists(_lk):
                _ld = json.load(open(_lk, encoding="utf-8"))
                if str(_ld.get("run_id")) == run_id:
                    rec["lock_left"] = True
                    rec["lock_note"] = (
                        "⚠️ 本次 autorun（run_id=%s）**留下了锁** —— 它会让下一个写档者 `exit=2`。"
                        "按库规处置：**先 `kb_pipeline.py --check` 判有没有写坏，再删锁**；"
                        "顺序反了就等于把「崩在中途」当成「跑完了」。" % run_id)
        except Exception:                              # noqa: BLE001
            pass
    rec["elapsed_sec"] = round(time.time() - t0, 1)
    # ★ 审计**不在这里写** —— 由 `check()` 在拿到复判结果后**一次写完**（一跑一行，
    #   行里才有完整的「前后 stale_layers / 是否放行」）。这里写过一次会导致每跑两行。
    return rec


def _load_report(kb_root: str, force_live: bool = False):
    """读日报机读档；**优先现跑一次**（避免拿陈旧日报判新鲜）。

    ★ 为什么要现跑：日报是**别的进程写的**，可能停在几小时前。
      拿一份 6 小时前的日报判「现在新鲜吗」，就是**用陈旧数据判新鲜** —— 同一类病。
      现跑一次 `daily_health.py --no-gates --outdir <临时目录>`（**零写权威库**，
      与 `freshness.py:88-92` 同款做法），跑不动才退回盘上那份。

    ★ **反测口**：环境变量 `KB_GATE_DAILY_JSON` 指向一份**夹具日报**时，直接用它、
      不现跑。存在的唯一理由是：陈旧场景**没法在真实库上安全复现**（要先把真库弄陈旧），
      而「拒答路径没测过」= 本批最不能接受的缺口。与 `skill_invocation_audit.py`
      的 `KB_GATE_KB` 是同一类测试缝。**默认不设 ⇒ 行为不变。**
    """
    _fx = os.environ.get("KB_GATE_DAILY_JSON")
    if _fx and os.path.isfile(_fx):
        try:
            with open(_fx, encoding="utf-8") as fh:
                d = json.load(fh)
            d["_source"] = {"mode": "fixture", "path": _fx,
                            "note": "**反测夹具**（KB_GATE_DAILY_JSON），非真实日报"}
            return d, None
        except Exception as e:                           # noqa: BLE001
            return None, "夹具日报读不出：%r" % (e,)

    # ── ★ TTL 复用：盘上日报只要够新就**直接用它**，不每次现跑 ──────────────────
    # 为什么需要：现跑一次 `daily_health --no-gates` 实测 **P50 ≈ 9.4 s**（它要把
    #   kb_pipeline --check 跑两遍）。评审链每次都付这 9 秒，warm 从 1.2 s 涨到 13 s ——
    #   仍在 60 s 内，但**没必要**：日报本身就是同一判据的产物。
    # 为什么**不构成放松判据**：复用有**上界**（默认 10 分钟）。日报判的是「层是否新鲜
    #   （24h 窗口）」，10 分钟前的日报与此刻的结论**在 24h 尺度上等价**；
    #   而且判定所需的**上游水位**是现算的（`daily_health` 每次都现读盘）。
    #   要绝对实时：`KB_GATE_MAX_AGE=0` 强制现跑。
    try:
        _max_age = float(os.environ.get("KB_GATE_MAX_AGE", "600"))
    except ValueError:
        _max_age = 600.0
    if (not force_live) and _max_age > 0 and os.path.isfile(DAILY):
        try:
            _age = time.time() - os.path.getmtime(DAILY)
            if _age <= _max_age:
                with open(DAILY, encoding="utf-8") as fh:
                    d = json.load(fh)
                d["_source"] = {"mode": "recent_on_disk", "path": DAILY,
                                "age_sec": round(_age, 1), "max_age_sec": _max_age,
                                "note": "日报在 TTL 内 ⇒ 直接复用，未现跑"
                                        "（判据同一份；要强制现跑设 KB_GATE_MAX_AGE=0）"}
                return d, None
        except Exception:                                # noqa: BLE001
            pass                                         # 读不动就往下走现跑

    tmp = tempfile.mkdtemp(prefix="kb-gate-")
    cmd = ["sh", KBPY, "l7/scripts/daily_health.py", "--no-gates", "--outdir", tmp]
    try:
        subprocess.run(cmd, cwd=os.path.dirname(kb_root), capture_output=True,
                       text=True, timeout=600)
        p = os.path.join(tmp, "daily-health-latest.json")
        if os.path.isfile(p):
            with open(p, encoding="utf-8") as fh:
                d = json.load(fh)
            d["_source"] = {"mode": "live", "path": p}
            return d, None
    except Exception as e:                               # noqa: BLE001
        _err = str(e)
    else:
        _err = "现跑日报没出机读档（服务可能在忙）"
    # 退回盘上那份（**如实标注是陈旧的**，不假装现跑）
    if os.path.isfile(DAILY):
        try:
            with open(DAILY, encoding="utf-8") as fh:
                d = json.load(fh)
            d["_source"] = {"mode": "on_disk", "path": DAILY,
                            "note": "现跑失败 ⇒ 退回盘上日报：%s" % _err}
            return d, None
        except Exception as e:                           # noqa: BLE001
            return None, "日报读不出：%r" % (e,)
    return None, "日报不存在（%s）；现跑也失败：%s" % (DAILY, _err)


def _info_from_report(d: dict) -> dict:
    """把日报机读档折成 `check()` 的 `info`（批30 抽出成函数，供**跑层后复判**复用）。"""
    stale_layers = d.get("stale_layers") or []
    # 逐条把「哪件产物 / 多久 / 原因」取出来（用户要求拒答时必须明写这三样）
    by_layer = {j.get("layer"): j for j in (d.get("freshness_by_layer") or [])}
    stale = []
    for r in (d.get("todos_with_playbook") or []):
        sig = str(r.get("sig") or "")
        if sig.startswith("stale."):
            stale.append({"layer": sig.split(".", 1)[1], "text": r.get("text"),
                          "owner": r.get("owner"), "command": r.get("command")})
    # 补上产物级细节（日报的 freshness 表里有 file/age）
    files = {}
    for row in (d.get("freshness") or []):
        if row.get("layer") in stale_layers and row.get("kind") == "data":
            files.setdefault(row["layer"], []).append(
                {"file": "kb/" + row["file"], "age": row.get("age"),
                 "mtime": row.get("mtime")})

    return {
        "ok": not stale_layers,
        "reason": ("" if not stale_layers else
                   "**供给链超期 ⇒ 拒答**：超期层 %s" % "、".join(stale_layers)),
        "stale_layers": stale_layers,
        "stale": stale,
        "stale_artifacts": files,
        "layer_detail": [
            {"layer": L, "change_state": (by_layer.get(L) or {}).get("change_state"),
             "watermark_match": (by_layer.get(L) or {}).get("watermark_match"),
             "reason": (by_layer.get(L) or {}).get("reason")}
            for L in stale_layers],
        "health": d.get("health"),
        "gate_ok": d.get("gate_ok"), "gate_red": d.get("gate_red"),
        "run_id": d.get("run_id"), "at": d.get("at"),
        "source": d.get("_source"),
    }


def check(kb_root: str | None = None):
    """返回 `(ok: bool, info: dict)`。

    `info` 里带 `stale`（逐条：层/产物/多久/原因）、`health`、`gate_red`、`source`。
    """
    kb_root = kb_root or KB
    d, err = _load_report(kb_root)
    if d is None:
        return False, {
            "ok": False, "reason": "**判据读不到 ⇒ 拒答（fail-closed）**：%s" % err,
            "stale": [], "unreadable": True,
            "source": {"mode": "missing"},
        }

    info = _info_from_report(d)
    if info["ok"]:
        info["autorun"] = {"attempted": False, "why": "全部新鲜，未跑层"}
        return True, info

    # ── ★★ 批30：陈旧 ⇒ **先跑命中层（L4–L6）**，再复判 ────────────────────────
    # 「超期」是**去跑层的理由**，不是拒答的理由；只有跑完仍超期才拒答（fail-closed 保住）。
    run = autorun_stale_layers(kb_root, info)
    info["autorun"] = run
    if not run.get("ok"):
        info["reason"] = ("**供给链超期，且自动跑层未成功 ⇒ 拒答（fail-closed）**：%s；"
                          "原超期层 %s"
                          % (run.get("why") or "（无原因）",
                             "、".join(info.get("stale_layers") or []) or "无"))
        run["final_ok"] = False
        _audit(kb_root, run)                            # 一跑一行（失败路径）
        return False, info

    d2, err2 = _load_report(kb_root, force_live=True)   # ★ 复判必须现跑，不得复用 TTL 内旧日报
    if d2 is None:
        info["reason"] = "**跑层后复判读不到日报 ⇒ 拒答（fail-closed）**：%s" % err2
        run["final_ok"] = False
        _audit(kb_root, run)
        return False, info
    info2 = _info_from_report(d2)
    run["after_stale_layers"] = info2.get("stale_layers") or []
    run["final_ok"] = bool(info2["ok"])
    info2["autorun"] = run
    if not info2["ok"]:
        info2["reason"] = ("**跑层后仍超期 ⇒ 拒答（fail-closed）**：超期层 %s"
                           % "、".join(info2.get("stale_layers") or []))
    _audit(kb_root, run)                                # 一跑一行（含前后 + 是否放行）
    return info2["ok"], info2


def refusal_payload(info: dict) -> dict:
    """拒答结论的标准形状（两条入口共用，保证同输入同结论）。"""
    return {
        "state": "NEEDS_INPUT",
        "reason": "供给链不新鲜",
        "detail": info.get("reason"),
        "stale_layers": info.get("stale_layers") or [],
        "stale": info.get("stale") or [],
        "stale_artifacts": info.get("stale_artifacts") or {},
        "layer_detail": info.get("layer_detail") or [],
        "health": info.get("health"),
        "fails_closed": True,
        "note": ("供给链有超期产物 ⇒ **不产出 PASS/BLOCK**（fail-closed）。"
                 "按上面 `stale` 逐条处置后重跑。"
                 "判据来源 = kb/l7/scripts/review_freshness_gate.py（两条入口共用同一份）。"),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="评审链 fail-closed 前置：供给链新鲜度")
    ap.add_argument("--kb-root", default=None)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    ok, info = check(a.kb_root)
    if a.json:
        print(json.dumps({"ok": ok, "info": info}, ensure_ascii=False, indent=1))
    else:
        print("评审链前置（fail-closed）：%s" % ("✅ 放行" if ok else "⛔ 拒答"))
        print("  判据来源：%s" % json.dumps(info.get("source"), ensure_ascii=False))
        print("  health=%s ｜ gate 过%s/红%s ｜ 超期层 %s"
              % (info.get("health"), info.get("gate_ok"), info.get("gate_red"),
                 info.get("stale_layers") or "无"))
        for s in (info.get("stale") or []):
            print("   · %s" % s.get("text"))
    if not ok:
        return EXIT_UNREADABLE if info.get("unreadable") else EXIT_REFUSE
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
