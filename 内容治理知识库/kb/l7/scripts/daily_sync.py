#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""daily_sync.py —— L0–L7 **日更总入口**（launchd 08:30 调它）。

    ① L0 与飞书对齐（可写：新增入库；删除立碑后真删）
    ② 逐层写档 L1 → L6（`--sync --only Lx --apply`，编排器自带「先闸门后引擎、遇红即停」）
    ③ L0–L7 全链只读体检（daily_health.py）—— 无论②走到哪层都要跑，日报是停因的唯一出口

为什么要有这一层（2026-10-02 用户裁定）：
  原先 08:30 只跑 `daily_health.py` —— **只读体检，一个字节源数据都不动**；
  于是"日更"名不副实：L0 与飞书的对齐一直是人想起来才跑。
  用户口径原文：「每层自动更新，不要人手动触发」+「每天 8:30 全跑一遍，其他时间不用跑」。
  ⇒ 本脚本把「L0 对齐 → 逐层写档 → 体检」串成一条。

为什么现在敢让每层自动写（防护没减）：
  · 编排器：每层「先闸门、后引擎」，闸门红即停，后续层不跑（kb_pipeline.py:811-819）
  · 编排器：ARCHIVE_BEFORE_WRITE 归档红线（写 L3 前先归档 rejected.jsonl）+ 持锁互斥
  · 引擎侧（同日加）：内容对等则不写 / 写前强制归档 + sha 校验 / **行数骤减护栏**
    —— L3 的护栏当日实测拦下一次 10,661 → 2,611（降 76%）的骤减
  · 白名单：SYNC_ALLOWED 已放开 L1–L6（机制保留，要收紧改一个列表）

写档边界：
  · 只写：kb/l0…l6（按各层引擎与幂等键）、kb/l8/runs/**、kb/l7/reports/**
  · 有活跃写锁时：L0 同步跳过（体检照跑）；逐层写档由编排器自己判锁

退出码：0 = 跑完（健康看回执与日报）｜ 2 = 连体检都没跑成
"""
from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))       # …/kb/l7/scripts
KB = os.path.dirname(os.path.dirname(HERE))             # …/kb
ROOT = os.path.dirname(KB)                              # kb/ 的上一级
KBPY = os.path.join(KB, "kbpy")


def log(m: str) -> None:
    print("[daily %s] %s" % (time.strftime("%H:%M:%S"), m), flush=True)


def step(name: str, argv: list[str], timeout: int = 3600) -> int:
    t0 = time.time()
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    try:
        p = subprocess.run(argv, cwd=ROOT, env=env, capture_output=True,
                           text=True, errors="replace", timeout=timeout)
        code, out = p.returncode, (p.stdout or "") + (p.stderr or "")
    except subprocess.TimeoutExpired:
        code, out = -1, "超时 %ds" % timeout
    log("%s → exit=%s（%.1fs）" % (name, code, time.time() - t0))
    for ln in out.strip().splitlines()[-8:]:
        log("    " + ln)
    return code


#: 逐层写档顺序（拓扑序；L0 由 l0_daily_sync 走飞书对齐，L7 只出报告不写库）
WRITE_LAYERS = ["L1", "L2", "L3", "L4", "L5", "L6"]


def _freshness():
    """惰性拿 `layer_freshness` 模块；拿不到返回 None —— 新鲜度记账**不该拖垮日更**。"""
    try:
        sys.path.insert(0, os.path.join(KB, "l7", "scripts"))
        import layer_freshness as lf
        return lf
    except Exception as e:                                  # noqa: BLE001
        log("⚠️ 新鲜度测量档不可用（%r）⇒ 本次不落观测，日更照跑" % (e,))
        return None


def _newest_l7_run() -> str:
    """取 `kb/l7/runs/` 里**最新**那件记账件的 run_id（体检刚写的那件）。

    为什么不用墙钟：`layer_freshness.judge()` 的收紧项会拿 sidecar 的 `run_id` 去核对**真运行**，
    而墙钟算出来的 rid 与体检实际写的 run_id 常常差一分钟（实测 20261003-2059 无产物）
    ⇒ 观测会被判「不可采信」、白落一次。取真产物名才核得上。
    """
    try:
        cand = [f for f in os.listdir(os.path.join(KB, "l7", "runs")) if f.endswith(".json")]
        if not cand:
            return time.strftime("%Y%m%d-%H%M")
        newest = max(cand, key=lambda f: os.path.getmtime(os.path.join(KB, "l7", "runs", f)))
        return os.path.splitext(newest)[0]
    except Exception:                                       # noqa: BLE001
        return time.strftime("%Y%m%d-%H%M")


def observe(lf, lid: str, *, rid: str, rc: int, out_before, wm_before) -> None:
    """★ 修复1（2026-10-03）：每层写档**跑完就落一次真实观测**（写 sidecar，不碰层数据）。

    为什么必须有这一步（实测根因，不是理论）：
      `layer_freshness.judge()` 要 `change_state` + `input_watermark` 做**水位交叉验证**，
      而这些字段层引擎的落章里大多没有 ⇒ 它转读 sidecar `kb/l7/registry/layer_run_freshness.json`。
      而 `measure()` —— **sidecar 的唯一写入者** —— **全库没有任何生产调用点**
      （只有 `layer_freshness.py` 自己的 CLI 与 `seed_freshness_sidecar.py` 的注释）。
      后果：L4/L5/L6 的 sidecar 停在 10-02 13:22，而当天 08:31 日更**明明跑过每层**
      （`--apply` 成功、体检 GREEN），`judge()` 仍拿那个旧时间判「距今 31.2 小时 ⇒ 陈旧」
      ⇒ **评审链永久拒答，再跑日更也没用**。
      `seed_freshness_sidecar.py` 的注释早就承诺「之后每一跑都走 `measure()`，seeded 会被真观测覆盖」
      —— **本函数就是兑现那句承诺。**

    参数取法与 `layer_freshness.py` 自己的 `measure` 子命令一致（`:521-526`）：
      `out_before = output_fingerprint(KB, lid)`、`wm_before = watermark_digest(current_watermark(KB, lid))`。
    """
    if lf is None:
        return
    try:
        f = lf.measure(KB, lid, change_state="produced_changes",
                       out_before=out_before, wm_before=wm_before,
                       exit_code=rc, run_id=rid,
                       note="daily_sync.py 写档后落的真实观测（修复1，2026-10-03）")
        log("    ↳ 新鲜度观测已落：%s change_state=%s provenance=%s 水位未变=%s"
            % (lid, f.get("change_state"), f.get("provenance"), f.get("input_unchanged")))
    except Exception as e:                                  # noqa: BLE001
        log("    ⚠️ 新鲜度观测没落成（%r）—— 不影响本次写档，但新鲜度会少一条证据" % (e,))


def l0_write_guard() -> tuple[bool, str]:
    """★ 用户裁定（2026-10-03）：「**先把 L0 跟飞书侧对齐，再执行其他层的**」。

    读 `kb/l7/reports/l0-daily-sync-latest.json`（`l0_daily_sync.py` 的回执），按**库里已有的
    `not_exemptable` 教义**判「能不能往下写 l1–l6」：

      · `only_l0  > 0` ⇒ **拦**（库里有、飞书无：可能是飞书侧删除或整批替换 —— 该教义原文「必须逐条查，不许豁免」）
      · `changed  > 0` ⇒ **拦**（值变了就是值变了 —— 同上，不许豁免）
      · `pull_failed` **超出已登记豁免** ⇒ **拦**（未登记的表拉不到，不许把"没对齐"往下带）
      · `only_feishu > 0` ⇒ **不拦** —— 这正是**准入规则正常工作**：实测那 10 条逐条原因全同
        `准入未过：材料审核状态=[] != ["通过"]`（未审核通过的材料本来就不该入库）。
        ★ **若拿它拦，只要有一批待审材料，整条日更就永远跑不动** —— 那是把"正常"当"故障"。
      · **已登记**的 `pull_failed`（`l0-expected-diffs.yaml` 的 EX-2/EX-3）⇒ **不拦**，
        但由 `daily_health` 第 5 节暴露其 L0 副本年龄（修复2），不静默。

    读不到回执 ⇒ **拦**（fail-closed：L0 对齐结果不明，就别拿它当输入往下写）。
    返回 `(能否继续, 原因)`。**只读**，不写任何东西。
    """
    p = os.path.join(KB, "l7", "reports", "l0-daily-sync-latest.json")
    try:
        rec = json.load(open(p, encoding="utf-8"))
    except Exception as e:                                  # noqa: BLE001
        return False, "读不到 L0 对齐回执（%s：%r）⇒ fail-closed 不往下写" % (p, e)
    al = (rec.get("align_summary") or {})
    only_l0 = int(al.get("only_l0") or 0)
    changed = int(al.get("changed") or 0)
    pf = int(al.get("pull_failed") or 0)
    only_fs = int(al.get("only_feishu") or 0)
    # 已登记的豁免（按表名计数）
    exempt_pf = 0
    try:
        import yaml as _y
        doc = _y.safe_load(io.open(os.path.join(KB, "l7/registry/l0-expected-diffs.yaml"),
                                   encoding="utf-8")) or {}
        exempt_pf = sum(int(e.get("expected") or 1)
                        for e in (doc.get("expected") or []) if e.get("kind") == "pull_failed")
    except Exception:                                       # noqa: BLE001
        exempt_pf = 0
    bad = []
    if only_l0:
        bad.append("only_l0=%d（库里有、飞书无 —— 不许豁免，必须逐条查）" % only_l0)
    if changed:
        bad.append("changed=%d（字段值变了 —— 不许豁免，必须逐条查）" % changed)
    if pf > exempt_pf:
        bad.append("pull_failed=%d > 已登记豁免 %d（有**未登记**的表拉不到）" % (pf, exempt_pf))
    if bad:
        return False, "；".join(bad)
    return True, ("only_feishu=%d 属**准入规则正常工作**（未审核通过 ⇒ 故意不入库）、"
                  "pull_failed=%d 已在 expected 登记 ⇒ 均不拦" % (only_fs, pf))


def main() -> int:
    log("日更开始 ｜ 库根 %s" % ROOT)

    # ① L0 对齐（写档范围仅 L0；是否落盘由 kb/l7/registry/l0-sync.yaml 决定）
    #    ★ 修复1b（2026-10-03，同日追加）：**L0 也必须落观测**。实测：L0 今天跑了对齐（exit=0）、
    #    `kb/l8/_stage/feishu-align/20261003-2043/*` 也产出了，但 `kb/l0/runs/` 里**今天零落章**
    #    ⇒ 新鲜度只能靠 10-02 21:02 那份旧落章撑 ⇒ 24 小时一到就翻红、**拒答回来**。
    #    这与 L1–L6 是同一个洞，只是 L0 走 `l0_daily_sync.py` 这条路、没被 修复1 覆盖到。
    lf = _freshness()
    _b0 = _w0 = None
    if lf is not None:
        try:
            _b0 = lf.output_fingerprint(KB, "L0")
            _w0 = lf.watermark_digest(lf.current_watermark(KB, "L0"))
        except Exception as e:                              # noqa: BLE001
            log("    ⚠️ L0 测前指纹/水位取不到（%r）⇒ 该层观测降级" % (e,))
    c1 = step("L0 对齐", [KBPY, "l7/scripts/l0_daily_sync.py"])
    observe(lf, "L0", rid=time.strftime("%Y%m%d-%H%M"), rc=c1,
            out_before=_b0, wm_before=_w0)

    # ② 逐层写档 L1→L6（用户裁定 2026-10-02：每层自动更新，不要人手动触发）
    #    编排器**自带「先闸门、后引擎、遇红即停」**（kb_pipeline.py:811-819 →
    #    `stopped` → :1156 后面的层不跑），所以这里逐层调即可，不必自己实现停止逻辑。
    #    每层是独立子进程：一层失败不影响已完成的层，失败状态进回执。
    #    ★ 修复1（2026-10-03）：每层**测前取指纹/水位 → 写完落真实观测**，否则幂等层
    #      跑完不留任何"跑过"的证据，新鲜度判据会拿旧时间判陈旧 ⇒ 评审链永久拒答。
    lf = _freshness()
    # ★ 闸门（用户裁定 2026-10-03）：**L0 先对齐，再跑其他层**。判据见 `l0_write_guard()`。
    _ok, _why = l0_write_guard()
    layer_results = []
    if not _ok:
        log("⛔ **L0 未对齐到「可继续」的程度 ⇒ 跳过 L1–L6 写档**（用户裁定：先对齐 L0 再跑其他层）")
        log("   原因：%s" % _why)
        log("   处置：查 kb/l7/reports/l0-daily-sync-latest.json 与日报第 5 节；"
            "only_l0/changed 必须逐条查清（库规：**不许豁免**），pull_failed 未登记的要先登记或解锁。")
        log("   （体检仍会跑 —— 否则人看不到停在哪、为什么停。）")
    else:
        log("L0 对齐闸门：✅ 放行 → %s" % _why)
    for lid in (WRITE_LAYERS if _ok else []):
        rid = time.strftime("%Y%m%d-%H%M")
        out_before = wm_before = None
        if lf is not None:
            try:
                out_before = lf.output_fingerprint(KB, lid)       # 测前产物指纹
                wm_before = lf.watermark_digest(lf.current_watermark(KB, lid))   # 测前上游水位
            except Exception as e:                            # noqa: BLE001
                log("    ⚠️ %s 测前指纹/水位取不到（%r）⇒ 该层观测降级" % (lid, e))
        rc = step("%s 写档" % lid,
                  [KBPY, "l7/scripts/kb_pipeline.py", "--sync", "--only", lid, "--apply"])
        observe(lf, lid, rid=rid, rc=rc, out_before=out_before, wm_before=wm_before)
        layer_results.append({"layer": lid, "exit": rc})
        if rc != 0:
            # 遇红即停：闸门红/引擎失败都不该让后面的层带着坏输入往下走。
            # 但**体检仍要跑**（否则人看不到"停在哪、为什么停"）。
            log("⚠️ %s 未通过（exit=%s）→ 按「遇红即停」不再往下跑写档" % (lid, rc))
            break

    # ③ 全链只读体检（无论上面走到哪一层都要跑 —— 日报是停因的唯一出口）
    c2 = step("L0–L7 体检", [KBPY, "l7/scripts/daily_health.py"])

    # ③b ★ 修复1b（2026-10-03）：L7 也要落观测。它是**跨层闸门**、不写库、也没有 data 产物，
    #     但新鲜度判据照样判它（判的是 `kb/l7/runs/` 的落章）—— 体检刚写完新的，这里接着落一次观测，
    #     免得它跟 L0 一样退化成"靠旧落章 mtime 撑"。
    #     ★ run_id 取**体检刚写的那一件**（不是墙钟）：`judge()` 的收紧项会拿 run_id 去核对真运行，
    #       墙钟算出来的 rid 常常核对不到（实测 20261003-2059 无产物）⇒ 观测会被判"不可采信"。
    observe(lf, "L7", rid=_newest_l7_run(), rc=c2, out_before=None, wm_before=None)

    done = [x["layer"] for x in layer_results if x["exit"] == 0]
    bad = [x for x in layer_results if x["exit"] != 0]
    log("日更结束 ｜ L0对齐 exit=%s ｜ 写档完成 %s ｜ 失败 %s ｜ 体检 exit=%s"
        % (c1, ",".join(done) or "无",
           ",".join("%s(exit=%s)" % (x["layer"], x["exit"]) for x in bad) or "无", c2))
    # 体检跑不成才算失败；写档失败已由体检报出来
    return 0 if c2 == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
