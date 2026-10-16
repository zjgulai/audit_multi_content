#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""l0_daily_sync.py —— L0 与飞书侧的**每日自动对齐**（P0-b / P1）。

## 它补的是什么

本库原先的 08:30 日更（`com.kb.pipeline-daily`）**只跑 `daily_health.py` 体检**：
只读、只出报告，**一个字节的源数据都不动**。于是 L0 与飞书的对齐
实际上一直是"人想起来才跑"——`layers.yaml` 里 L0 至今登记为「无写档引擎，
该层写档一律人工」，而理由是「飞书 token 只有 ~2h 有效期」。

★ 2026-10-02 实测：**那个理由不成立**。
  `align_l0_feishu.py` 的 `AS_ID` 默认就是 **`bot`**（另有 `AS_FALLBACK` 默认 `user`，bot 拿不到的表才回落）；`lark-cli auth status`
  报 bot 身份 `ready`；直接 `--as bot` 拉表返回真数据、**零授权交互**。
  bot 走 `tenant_access_token`：**2 小时过期但用 app_id/app_secret 自动刷新**。
  —— "有效期 2h" 与 "必须人工" 是两件事，混为一谈了。
  ⇒ 无人值守可做。

## 两个脚本的分工（都不是本脚本发明的，是既有的）

    align_l0_feishu.py <RUN>         对账：飞书 vs L0，产出 kb/l8/runs/<RUN>-l0-align.json
                                     分类：一致 / 飞书多 / L0多 / 值变 / 拉取失败
    ingest_l0_new_records.py <RUN>   入库：只处理「飞书有、L0 完全没有」的**新增**
                                     （默认干跑，`--apply` 才落盘）

本脚本 = 串起来 + 落回执 + 给下游一个「该不该继续」的判据。

## 三部曲与删除缺口（如实说）

    ① 对账 → 拿到四类差异
    ② 新增 → 入库（--apply）
    ③ 删除 → **立碑后真删**（P1，2026-10-02 接上）

★ **「飞书删了、L0 还有」这一类，原先无人处理** ——
  `ingest_l0_new_records.py` 只管新增（它的 docstring 原文：
  「只处理『飞书有、L0 没有』的记录」）。
  现由本脚本接管：对账给出 `only_l0_ids` → **先立碑（原子写+读回校验）→ 再删原件**。
  · 立碑失败 ⇒ 该条**不删**（宁可不删，也不留无碑的空洞）
  · 默认关闭：需 `l0-sync.yaml` 的 `auto_delete: true` 或命令行 `--allow-delete`
  · 墓碑落 `kb/l0/tombstones/<表>/<record_id>.json`，记删前原文的 sha256 ——
    下游据此把「依据查不到」解释成「源已下架」，而不是数据丢失

## 用法

    kb/kbpy l7/scripts/l0_daily_sync.py                 # 干跑（默认，不落盘）
    kb/kbpy l7/scripts/l0_daily_sync.py --apply         # 真正入库新增
    kb/kbpy l7/scripts/l0_daily_sync.py --apply --allow-delete   # 另允许立碑后真删
    kb/kbpy l7/scripts/l0_daily_sync.py --apply --run 20261003-0830

退出码：0 = 跑完（健康与否看回执 health 字段）｜ 2 = 跑不起来（前置不满足）
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))      # …/kb/l7/scripts
KB = os.path.dirname(os.path.dirname(HERE))            # …/kb（两层！
#   ★ 2026-10-02 实测踩坑：本脚本放在 l7/scripts/ 下，只取一层 dirname 会得到
#   `…/kb/l7`，于是 KBPY 拼成 `…/kb/l7/kbpy` → FileNotFoundError。
#   口径与同目录 kb_pipeline.py 逐字一致（它也是 dirname(dirname(HERE))）。
ROOT = os.path.dirname(KB)                     # kb/ 的上一级（cwd 约定）
KBPY = os.path.join(KB, "kbpy")
LOCK = os.path.join(KB, ".work", ".kb.lock")
OUT = os.path.join(KB, "l7", "reports")


def log(m: str) -> None:
    print("[l0-daily %s] %s" % (time.strftime("%H:%M:%S"), m), flush=True)


CONF = None       # 延迟到 main 里按库内相对路径定位


def read_auto_apply(conf_path: str) -> tuple[bool, str]:
    """读调度配置：`kb/l7/registry/l0-sync.yaml`。

    为什么要有这个开关（2026-10-02）：日更是**无人值守**的，硬编码 `--apply`
    等于关机也写；而没有开关又得每次改 plist。开关放库内，改行为不用动系统配置。

    极简解析（不引第三方）：只认 `auto_apply: true|false`，其余行忽略。
    读不到文件 ⇒ 返回 (False, 原因)，**默认不写** —— fail-closed。
    """
    if not os.path.exists(conf_path):
        return False, "配置不存在：%s（按不写处理）" % conf_path
    try:
        for ln in open(conf_path, encoding="utf-8"):
            ln = ln.split("#", 1)[0].strip()
            if ln.lower().startswith("auto_apply:"):
                v = ln.split(":", 1)[1].strip().strip('"').strip("'").lower()
                return v in ("true", "yes", "1", "on"), "配置 auto_apply=%s" % v
    except Exception as e:                              # noqa: BLE001
        return False, "配置读失败：%s（按不写处理）" % e
    return False, "配置里没有 auto_apply（按不写处理）"


def read_flag(conf_path: str, key: str) -> bool:
    """读配置里某个布尔开关；读不到一律 False（fail-closed）。"""
    try:
        for ln in open(conf_path, encoding="utf-8"):
            ln = ln.split("#", 1)[0].strip()
            if ln.lower().startswith(key.lower() + ":"):
                v = ln.split(":", 1)[1].strip().strip('"').strip("'").lower()
                return v in ("true", "yes", "1", "on")
    except Exception:                                   # noqa: BLE001
        return False
    return False


def tombstone_and_delete(cands: list[dict], run: str, apply_now: bool) -> dict:
    """P1：飞书已下架 → **真删 L0 记录，但先立碑**。

    为什么必须立碑（用户裁定 (a)：真删+碑）：
      定稿层有 632 条 evidence 指向 L0-L3 的 (anchor, source_sha256)。
      直接删掉 L0 记录，那些 anchor 会**静默指空** —— 将来没人能解释
      「这条规则的依据为什么查不到了」。墓碑把「源已下架」变成**可解释的事实**，
      而不是一次数据丢失。

    墓碑形状（落 kb/l0/tombstones/<表>/<record_id>.json）：
      {record_id, table, deleted_at, run, deleted_by,
       source_sha256_deleted,   ← 删前那份原文的指纹（回源时用来解释"它确实存在过"）
       reason}

    顺序：**先立碑（原子写 + 读回校验），再删文件**。
      立碑失败 ⇒ 不删（宁可不删，也不留无碑的空洞）。
    """
    out = {"deleted": [], "tombstoned": [], "failed": []}
    if not cands:
        return out
    for c in cands:
        tbl, rid = c.get("table") or "", c.get("record_id") or ""
        if not tbl or not rid:
            out["failed"].append({"cand": c, "why": "缺 table 或 record_id"})
            continue
        rec = os.path.join(KB, "l0", "records", tbl, rid + ".json")
        if not os.path.exists(rec):
            out["failed"].append({"table": tbl, "record_id": rid,
                                  "why": "L0 记录文件不存在（可能已被删）"})
            continue
        try:
            raw = open(rec, "rb").read()
            import hashlib
            sha = hashlib.sha256(raw).hexdigest()
        except Exception as e:                          # noqa: BLE001
            out["failed"].append({"table": tbl, "record_id": rid,
                                  "why": "读原记录失败：%s" % e})
            continue
        tomb = {
            "record_id": rid, "table": tbl,
            "deleted_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "run": run,
            "deleted_by": "l0_daily_sync.py（飞书侧已无此记录）",
            "source_sha256_deleted": sha,
            "reason": "飞书侧已下架/删除：对账判为 only_l0（飞书无、L0 有）",
            "schema": "l0-tombstone/v1",
        }
        dst = os.path.join(KB, "l0", "tombstones", tbl, rid + ".json")
        if not apply_now:
            out["tombstoned"].append({"table": tbl, "record_id": rid,
                                      "sha256": sha, "would_write": dst})
            continue
        try:
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            tmp = dst + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(tomb, fh, ensure_ascii=False, indent=1)
            # 读回校验：碑必须能读回且 sha 对得上，才允许删原件
            back = json.load(open(tmp, encoding="utf-8"))
            assert back.get("source_sha256_deleted") == sha, "碑读回 sha 不一致"
            os.replace(tmp, dst)
        except Exception as e:                          # noqa: BLE001
            out["failed"].append({"table": tbl, "record_id": rid,
                                  "why": "立碑失败，**故不删**：%s" % e})
            continue
        try:
            os.remove(rec)
            out["deleted"].append({"table": tbl, "record_id": rid,
                                   "sha256_deleted": sha, "tombstone": dst})
        except Exception as e:                          # noqa: BLE001
            out["failed"].append({"table": tbl, "record_id": rid,
                                  "why": "碑已立但删文件失败：%s" % e})
    return out


def lock_holder() -> dict | None:
    """本库的写档互斥靠 kb/.work/.kb.lock；有活跃持有者就不许写。"""
    if not os.path.exists(LOCK):
        return None
    try:
        rec = json.load(open(LOCK, encoding="utf-8"))
    except Exception:                                   # noqa: BLE001
        return {"raw": "锁文件读不出", "alive": None}
    pid = rec.get("pid")
    alive = None
    if isinstance(pid, int):
        try:
            os.kill(pid, 0)
            alive = True
        except OSError:
            alive = False
    rec["alive"] = alive
    return rec


def run_step(name: str, argv: list[str], timeout: int = 3600) -> dict:
    """跑一个既有脚本，回 (exit, tail)。不捕获成异常 —— 失败要如实进回执。"""
    t0 = time.time()
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    # ★ 2026-10-02 实测（本文件 22:18 那次 exit=1 的根因）：
    #   两个依赖飞书的脚本**身份默认值不一致** ——
    #     align_l0_feishu.py:55        AS_ID = os.environ.get("L8_AS", "bot")
    #     ingest_l0_new_records.py:76  AS_ID = os.environ.get("L8_AS", "user")   ←
    #   而 user 身份的 token 在 keychain 里是 missing 的（`lark-cli auth status`
    #   报 `User identity: missing`），于是 ingest 那步必失败：
    #     --as user → exit=3 stdout=0B  error=need_user_authorization
    #     --as bot  → exit=0 stdout=3562B 有效 JSON
    #   这里**统一钉成 bot**：bot 走 tenant_access_token，自动刷新、无需人工授权，
    #   这正是"L0 可以无人值守日更"的依据。要临时切 user 调试：
    #   在外部设 L8_AS=user 即可（本行用 setdefault，不覆盖外部显式值）。
    env.setdefault("L8_AS", "bot")
    try:
        p = subprocess.run(argv, cwd=ROOT, env=env, capture_output=True,
                           text=True, errors="replace", timeout=timeout)
        code, out = p.returncode, (p.stdout or "") + (p.stderr or "")
    except subprocess.TimeoutExpired:
        code, out = -1, "超时 %ds" % timeout
    tail = "\n".join(out.strip().splitlines()[-6:])
    log("%s → exit=%s（%.1fs）" % (name, code, time.time() - t0))
    for ln in tail.splitlines():
        log("    " + ln)
    return {"step": name, "argv": argv, "exit": code, "tail": tail,
            "elapsed_s": round(time.time() - t0, 1)}


def main() -> int:
    ap = argparse.ArgumentParser(description="L0 与飞书侧每日自动对齐")
    ap.add_argument("--run", default=time.strftime("%Y%m%d-%H%M"))
    ap.add_argument("--apply", action="store_true", help="真正入库新增（覆盖配置）")
    ap.add_argument("--dry-run", action="store_true", help="强制干跑（覆盖配置）")
    ap.add_argument("--allow-delete", action="store_true",
                    help="允许「立碑后真删」（覆盖配置 auto_delete；默认关）")
    ap.add_argument("--conf", default=os.path.join("kb", "l7", "registry", "l0-sync.yaml"))
    ap.add_argument("--timeout", type=int, default=1800, help="每步超时秒数")
    ap.add_argument("--outdir", default=OUT)
    a = ap.parse_args()

    # 落盘口径：显式 --apply/--dry-run 优先；否则读库内配置（fail-closed → 不写）
    conf_path = a.conf if os.path.isabs(a.conf) else os.path.join(ROOT, a.conf)
    conf_on, conf_why = read_auto_apply(conf_path)
    if a.dry_run:
        a.apply, why = False, "命令行 --dry-run"
    elif a.apply:
        why = "命令行 --apply"
    else:
        a.apply, why = conf_on, conf_why

    run = a.run
    mode = "落盘" if a.apply else "干跑"

    log("L0 每日对齐 ｜ run=%s ｜ %s（%s）" % (run, mode, why))
    log("库根 %s" % ROOT)

    # ── 写档互斥：--apply 才需要（干跑不写，允许与别人并行）──────────────
    hold = lock_holder()
    if hold and a.apply and hold.get("alive"):
        log("❌ 已有活跃写档者（pid=%s run=%s）→ 不写，退出"
            % (hold.get("pid"), hold.get("run_id")))
        return 2
    if hold and not hold.get("alive"):
        log("⚠️ 存在**陈旧锁**（pid=%s 已死，run=%s）—— 本脚本不撬锁，交由人处置"
            % (hold.get("pid"), hold.get("run_id")))

    steps: list[dict] = []

    # ── ① 对账 ────────────────────────────────────────────────────────
    steps.append(run_step("align_l0_feishu", [KBPY, "l8/align_l0_feishu.py", run], a.timeout))
    align_path = os.path.join(KB, "l8", "runs", "%s-l0-align.json" % run)
    align = None
    if os.path.exists(align_path):
        try:
            align = json.load(open(align_path, encoding="utf-8"))
        except Exception as e:                          # noqa: BLE001
            log("⚠️ 对账报告读不出：%s" % e)

    # ── ② 新增入库 ────────────────────────────────────────────────────
    if align is None:
        log("⚠️ 没有对账报告 → 跳过入库（入库脚本依赖它）")
        steps.append({"step": "ingest_l0_new_records", "exit": None,
                      "tail": "跳过：前置对账报告缺失"})
    else:
        argv = [KBPY, "l8/ingest_l0_new_records.py", run]
        if a.apply:
            argv.append("--apply")
        steps.append(run_step("ingest_l0_new_records", argv, a.timeout))

    # ── ③ 删除：立碑后真删（P1；用户裁定 (a) 真删+碑）──────────────────
    # ★ 2026-10-02 修（我自己的 bug，与 daily_health 那次同类）：
    #   `removed` 原先在下面才定义，这里先用 ⇒ UnboundLocalError。
    #   两份报告的字段名都是**英文键**（原版按中文键读 → 全 None）：
    #     对齐报告 summary = {same, only_feishu, only_l0, changed, pull_failed}
    #     每条表里删除候选的键是 `only_l0_ids`（only_l0 是计数）
    smy = {}
    removed = []
    if align:
        s = align.get("summary") or {}
        smy = {"same": s.get("same"), "only_feishu": s.get("only_feishu"),
               "only_l0": s.get("only_l0"), "changed": s.get("changed"),
               "pull_failed": s.get("pull_failed")}
        # 「L0 多」= 飞书没有、L0 有 → 删除候选
        for t in (align.get("tables") or {}).values():
            if isinstance(t, dict):
                for rid in (t.get("only_l0_ids") or []):
                    removed.append({"table": t.get("table") or t.get("table_id"),
                                    "record_id": rid})

    # 默认**不动**：要真删需配置 auto_delete: true（或命令行 --allow-delete）。
    # 立碑失败 ⇒ 该条不删（tombstone_and_delete 里保证）。
    del_on = a.allow_delete or read_flag(conf_path, "auto_delete")
    del_res = {"deleted": [], "tombstoned": [], "failed": [], "skipped_reason": None}
    if removed and not (a.apply and del_on):
        del_res["skipped_reason"] = (
            "删除候选 %d 条，但未开启真删（需 kb/l7/registry/l0-sync.yaml 的 "
            "auto_delete: true，或命令行 --allow-delete）→ 本轮只报不删" % len(removed))
    elif removed:
        del_res = tombstone_and_delete(removed, run, apply_now=a.apply)
        del_res.setdefault("skipped_reason", None)
    # （③ 的字段解析已上移到删除段之前 —— 那里先用，故先算）
    ingest_report = os.path.join(KB, "l8", "runs", "%s-l0-ingest.json" % run)
    ing = None
    if os.path.exists(ingest_report):
        try:
            ing = json.load(open(ingest_report, encoding="utf-8"))
        except Exception:                               # noqa: BLE001
            pass
    ing_smy = None
    if isinstance(ing, dict):
        ing_smy = {"written": len(ing.get("written") or []),
                   "skipped": len(ing.get("skipped") or []),
                   "archived": len(ing.get("archived") or [])}

    hard_fail = [s for s in steps if s.get("exit") not in (0, None)]
    health = "GREEN" if not hard_fail else "RED"
    receipt = {
        "run_id": run, "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "mode": mode, "applied": bool(a.apply), "health": health,
        "root": ROOT,
        "align_summary": smy,
        "align_report": align_path if os.path.exists(align_path) else None,
        "ingest_report": ingest_report if os.path.exists(ingest_report) else None,
        "ingest_summary": ing_smy,
        "removed_candidates": removed,
        "removed_count": len(removed),
        "delete_result": del_res,
        "steps": steps,
        "lock": hold,
    }

    os.makedirs(a.outdir, exist_ok=True)
    dst = os.path.join(a.outdir, "l0-daily-sync-latest.json")
    with open(dst, "w", encoding="utf-8") as fh:
        json.dump(receipt, fh, ensure_ascii=False, indent=1)

    print()
    print("=" * 72)
    print("L0 每日对齐 ｜ %s ｜ %s ｜ run=%s" % (health, mode, run))
    if smy:
        print("  对账：一致 %s ｜ 飞书多 %s ｜ L0多 %s ｜ 值变 %s ｜ 拉取失败 %s"
              % (smy.get("same"), smy.get("only_feishu"), smy.get("only_l0"),
                 smy.get("changed"), smy.get("pull_failed")))
    if ing_smy:
        print("  入库：入库 %s ｜ 跳过 %s ｜ 归档 %s"
              % (ing_smy.get("written"), ing_smy.get("skipped"), ing_smy.get("archived")))
    if removed:
        _d = len(del_res.get("deleted") or [])
        _t = len(del_res.get("tombstoned") or [])
        _f = len(del_res.get("failed") or [])
        print("  ⚠️ 删除候选 %d 条（飞书已无、L0 仍有）→ 真删 %d ｜ 待立碑 %d ｜ 失败 %d"
              % (len(removed), _d, _t, _f))
        if del_res.get("skipped_reason"):
            print("     %s" % del_res["skipped_reason"])
        for x in (del_res.get("failed") or [])[:5]:
            print("     ❌ %s" % x.get("why"))
    else:
        print("  删除候选：0 条（飞书侧与 L0 无删除差异）")
    print("  回执：kb/l7/reports/l0-daily-sync-latest.json")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    sys.exit(main())
