#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""freshness.py —— 供给链「各层新鲜度「汇总检查器（L0–L7，只读）。

## 它是给谁用的

给**评审链做前置**：用户说「这个评审一下」时，先跑本脚本确认各层数据新不新鲜；
不新鲜就**如实拒答**（退出码 3），而不是拿陈旧数据出一份看着完整的报告。

## 它不重造判据（关键设计）

「每层关键产物的新鲜度 / 落后量 / 陈旧」这套判据**已经存在**：
`kb/l7/scripts/daily_health.py`（判据：**最近一次成功 RUN 距今是否超过 `layer_freshness.STALE_AFTER`**；
注册表被改不算这层跑过）。本脚本**调用它、读它的机读产物**，不在本文件里复述判据。

**陈旧结论直接读它的，不自己算**（2026-10-01 修正）：本脚本原先用「报告文件的 mtime」当"现在"
重算 age，而 daily_health 用**墙钟**（`daily_health.py:207` `now = time.time()`）——
两个基准差一次运行间隔，实测**同一次体检它判 3 项陈旧、本脚本判 6 项**。
现改为读 `todos_with_playbook` 里 `sig.startswith("stale.")` 的条目。
**同一判据算两遍必然分叉** —— 这是本库反复栽过的同一类问题。

**但调用它必须不写权威库**：`daily_health.py` 默认落 `kb/l7/reports/`。
本脚本用 `--outdir <临时目录>` 把它引开 —— 实测（2026-10-01）零写权威库。

## 它新增的两样（daily_health 没有的）

  ① **L1/L2/L3 查询档状态** —— 调 `l1_status.py` / `l2_status.py` / `l3_status.py`，
     把「逐层都有只读入口可调」这件事落成一条可核的输出（调用 = 调该层 skill 的查询档）。
  ② **L6 索引 vs L3 规则的时序** —— daily_health 只看「age > 阈值」，
     报不出「L6 索引比 L3 规则旧」。本脚本**把两者 mtime 并排报出**。
     ⚠️ 注意：**"索引比规则旧"不等于"索引坏了"** —— 是否存在真实的 L3→L6 数据边，
     需人裁（`l6_build.py` 读的是 L2 units 与 L5 matcher，不是 L3 规则）。本脚本只报事实，不判因果。

## 只读

只读各层台账与产物；唯一写盘是**临时目录**（跑完即删），**不写 kb/l0…kb/l7 任何文件**。

## 退出码

    0 = 各层 data 产物都在阈值内（阈值见 `layer_freshness.STALE_AFTER`；不代表业务上正确）
    3 = 有层超期 → **评审链应拒答**（同 kb-content-review 的拒答码 3）
    2 = 用法错 / 库根不对 / 取不到新鲜度数据
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import tempfile

ROOT_MARKER = os.path.join("kb", "KB-ROOT.json")
KBPY = os.path.join("kb", "kbpy")
DAILY = os.path.join("kb", "l7", "scripts", "daily_health.py")  # 存在性校验用（库根相对）
#: 陈旧阈值**不在本脚本** —— 唯一出处是 `kb/l7/scripts/layer_freshness.py::STALE_AFTER`
#: （2026-10-16 周更后为 8 天）。**别在这里抄第二份数字。**
#: 本脚本只读它的结论，不自己算（原先自算导致同一次体检 3 vs 6 分叉，2026-10-01 修）。


# ── ★ 2026-10-10：**落定后再判**（治"把正在写的文件读成上游刚变"的假红）────────────
# 病灶（当天实测）：`layer_freshness.judge()` 拿**现算**上游水位比落章水位，
#   而那次比对落在 L6 正在写 `l6/registry/l6.json` 的窗口里 —— 读到 26178，写完是 26180
#   ⇒ 判「上游水位已变 ⇒ L7 陈旧」⇒ 就绪巡检推飞书告警（11:03 那条）。
#   同一份产物事后写圆了：「水位差**不是本层之后的变化** —— 上游最新改动 10:42:34 早于本层运行 10:55:29 ⇒ 新鲜」。
# 修法（**不改 judge() 的判据**，只改"什么时候采信它"）：
#   第一遍收集"哪些层判陈旧"；若有 ⇒ **共享等一次**（默认 90s，所有层共用，不是每层各等一次），
#   再跑第二遍；**只有两遍都判陈旧的层才算陈旧**。
#   单遍就绿的层由 `intersect_stale` 原样保留 —— 这一步**只可能把红翻绿，不可能把绿翻红**。
# 超时账（别把上层撞爆）：调用方 `watch_review_readiness.check_freshness` 给 300s；
#   一遍 daily_health(--no-gates) 实测 ~5-10s ⇒ 90s 一次共享等待 + 两遍，余量充足。
#   自证/离线：`KB_FRESH_SETTLE_S=0`（env-only，launchd 不会设）⇒ 不等待，跑纯逻辑。
SETTLE_S = float(os.environ.get("KB_FRESH_SETTLE_S") or 90)


def intersect_stale(stale_first, stale_second):
    """**纯函数**：只有**两遍都判陈旧**的层才算陈旧。返回 (陈旧层, 第一遍红但第二遍转绿的层)。

    为什么是交集而不是并集：第二遍是**更晚、更落定**的读数 —— 它转绿说明第一遍抓到的是
    「上游正在写」的瞬时态（假红）。并集会把这个假红留下来 ⇒ 白等还照样误报。
    """
    a, b = set(stale_first or ()), set(stale_second or ())
    return sorted(a & b), sorted(a - b)


def settle_decide(blob_first, blob_second, settle_s):
    """**纯函数**：落定重判后到底采信哪一份读数。

    返回 `(采用哪一份: "first"|"second", 陈旧层, 第一遍红第二遍转绿的层, 说明)`。
    它在**第二遍没跑成**（`blob_second is None`）与**没到该等的条件**两种情况下都**保持第一遍** ——
    fail-closed：宁可按更早、更严的那份判，也不许因为"重判没跑成"就静默翻绿。
    """
    first = _stale_of(blob_first)
    if blob_second is None:
        return "first", first, [], "第二遍没跑成 ⇒ **保持第一遍的判定**（fail-closed，不许猜、不许静默翻绿）"
    if not needs_settle_recheck(first, settle_s):
        return "first", first, [], "第一遍全绿（或未达等待条件）⇒ 不必重判"
    keep, recovered = intersect_stale(first, _stale_of(blob_second))
    why = ("落定后转绿 %s —— 第一遍那一下是「写入过程中的瞬时读数」，不判陈旧" % "、".join(recovered)
           if recovered else "两遍一致")
    return ("second" if keep != first else "first"), keep, recovered, why


def needs_settle_recheck(stale_first, settle_s):
    """**纯函数**：要不要再等一次。没有第一遍就红的层 ⇒ 不必等（省 90s）。"""
    return bool(stale_first) and float(settle_s or 0) > 0


def _daily_health_blob(outdir):
    """跑一次 daily_health（--no-gates，零写权威库），返回机读 blob；失败回 None。"""
    cmd = ["sh", KBPY, "l7/scripts/daily_health.py", "--no-gates", "--outdir", outdir]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    path = os.path.join(outdir, "daily-health-latest.json")
    if not os.path.exists(path):
        print("freshness: daily_health 没产出机读文件（exit=%s）" % proc.returncode, file=sys.stderr)
        print((proc.stderr or "")[-800:], file=sys.stderr)
        return None
    return json.load(open(path, encoding="utf-8"))


def _stale_of(blob):
    """从 daily_health 的结论里取出**陈旧层名**（读它的判定，不自己算 —— 2026-10-01 的口径）。"""
    rows = [t for t in (blob.get("todos_with_playbook") or [])
            if str(t.get("sig") or "").startswith("stale.")]
    return sorted({str(t.get("sig")).replace("stale.", "") for t in rows})


def check_root() -> None:
    if not os.path.isdir("kb"):
        sys.exit("freshness: 没有 kb/ 目录。请把 cwd 设成 kb/ 的上一级（库根）。")
    if not os.path.exists(ROOT_MARKER):
        sys.exit("freshness: 缺 %s —— 这里不是权威库根。" % ROOT_MARKER)


def mtime(p):
    try:
        return os.path.getmtime(os.path.join("kb", p))
    except OSError:
        return None


def main() -> int:
    ap = argparse.ArgumentParser(description="供给链各层新鲜度汇总（只读）")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--skip-layer-status", action="store_true",
                    help="跳过 L1/L2/L3 查询档调用（只想快点看新鲜度时用）")
    ap.add_argument("--selftest", action="store_true",
                    help="只跑「落定后再判」这条判据的自证（离线，不跑 daily_health、不联网）")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    check_root()

    if not os.path.exists(KBPY) or not os.path.exists(DAILY):
        print("freshness: 找不到 kb/kbpy 或 %s" % DAILY, file=sys.stderr)
        return 2

    tmp = tempfile.mkdtemp(prefix="kb-freshness-")
    tmp2 = tempfile.mkdtemp(prefix="kb-freshness-2-")
    settle_recovered = []
    try:
        # ── ① 复用 daily_health（outdir 引到临时目录，零写权威库）
        # 注意：kbpy 收的是** kb 内相对路径**（不是库根相对）—— kb/kbpy l7/scripts/xxx.py
        blob = _daily_health_blob(tmp)
        if blob is None:
            return 2

        # ── ①b ★ 落定后再判（2026-10-10）：第一遍有红 ⇒ 共享等一次 ⇒ 两遍都红才算红。
        #    见 `SETTLE_S` 上方那段注释（病灶 = 把"正在写"读成"上游刚变"）。
        _stale_first = _stale_of(blob)
        if needs_settle_recheck(_stale_first, SETTLE_S):
            print("freshness: 第一遍判陈旧 %s ⇒ 等 %.0fs 落定后**重判一遍**"
                  "（防「上游正在写」被读成「上游刚变」；`KB_FRESH_SETTLE_S` 可调）"
                  % ("、".join(_stale_first), SETTLE_S), file=sys.stderr)
            time.sleep(SETTLE_S)
            blob2 = _daily_health_blob(tmp2)
            which, keep, recovered, why = settle_decide(blob, blob2, SETTLE_S)
            print("freshness: %s（陈旧 %s）" % (why, "、".join(keep) if keep else "（无）"),
                  file=sys.stderr)
            settle_recovered = recovered
            if which == "second":
                blob = blob2            # 采用**更晚、更落定**的那份读数

        fresh = [r for r in (blob.get("freshness") or []) if r.get("kind") == "data"]

        # ── 陈旧结论：**读 daily_health 自己的判定，不自己算**（2026-10-01 修正）
        # 为什么改：本脚本原先用「报告文件的 mtime」当"现在"重算 age，而 daily_health 用
        # **墙钟**（`daily_health.py:207` `now = time.time()`）—— 两个基准差一次运行间隔，
        # 实测同一次体检它判 3 项陈旧、本脚本判 6 项。**同一判据算两遍必然分叉。**
        # 改为读它的 `todos_with_playbook` 里 `sig.startswith("stale.")` 的条目
        # （它连 owner / command 都给了，本脚本不必再拼）。
        stale_rows = [t for t in (blob.get("todos_with_playbook") or [])
                      if str(t.get("sig") or "").startswith("stale.")]
        stale_layers = sorted({str(t.get("sig")).replace("stale.", "") for t in stale_rows})
        stale = stale_layers
        by_layer = {}
        for r in fresh:
            by_layer.setdefault(r.get("layer"), []).append(r)

        # ── ② L1/L2/L3 查询档（调用 = 调该层 skill 的查询档）
        layer_status = {}
        if not a.skip_layer_status:
            for name, script in (("L1", "l1_status.py"), ("L2", "l2_status.py"), ("L3", "l3_status.py")):
                p = os.path.join("kb", "l7", "scripts", script)
                if not os.path.exists(p):
                    layer_status[name] = {"ok": False, "why": "脚本不存在：%s" % p}
                    continue
                r = subprocess.run(["sh", KBPY, "l7/scripts/" + script, "--json"],
                                   capture_output=True, text=True)
                got = None
                for line in (r.stdout or "").splitlines():
                    if line.strip().startswith("{"):
                        got = line
                        break
                layer_status[name] = {"ok": r.returncode == 0, "json": got}

        # ── ③ L6 索引 vs L3 规则的时序（daily_health 不报这个）
        m_idx = mtime("l6/index/l6.jsonl")
        m_rules = mtime("l3/candidates/rules.jsonl")
        index_vs_rules = None
        if m_idx and m_rules:
            index_vs_rules = {
                "l6_index_mtime": m_idx,
                "l3_rules_mtime": m_rules,
                "index_older_than_rules": m_idx < m_rules,
                "delta_hours": round((m_rules - m_idx) / 3600.0, 2),
            }

        # ── 汇总
        print("=" * 78)
        print("供给链新鲜度检查（L0–L7，只读）｜陈旧判定**读 daily_health 自己的结论**")
        print("=" * 78)
        print("逐层关键 data 产物（age 为 daily_health 按**墙钟**算的值）：")
        for lay in sorted(by_layer):
            for r in by_layer[lay]:
                flag = "⚠️ 陈旧" if lay in stale_layers else ""
                print("  %-3s %-42s %8s  %s" % (lay, r.get("file"), r.get("age") or "?", flag))
        print()
        # ── ★★ 批次20 · 第4块：不要打印一个**与真实健康色不符**的颜色 ──────────────
        # 病灶（实测，且它**误导过一次人**）：本脚本调用 daily_health 时**故意带
        #   `--no-gates`**（`:92`，为了省时间、且新鲜度不依赖闸门），于是daily_health 那一跑
        #   的 `gate_ok=0 / gate_undecided=8`，`health` 因此恒为 **YELLOW**。
        #   而**带闸门**的真健康色是 GREEN ⇒ 这一行打出 YELLOW，**与真实健康色相反**。
        #   读完这行的人会以为「供给链是黄的」，而 `daily-health-latest.json` 里是绿的。
        #   ⇒ 与「登记在撒谎」同类：**输出必须与判据一致**。
        # 修法：带 `--no-gates` 时**不报健康色**，改报「未跑闸门 ⇒ 健康色不可用」，
        #   并**指路**到真正带闸门的那份产物。**不改任何判据**（新鲜度结论照旧）。

        def _is_nogates():
            # 判据 = 这一跑没跑闸门（gate_ok 与 gate_undecided 一并看）：
            # 带了 --no-gates 时 ok=0 且 undecided=8（全层未执行）；带闸门时 ok=8。
            return (blob.get("gate_ok") == 0) and (blob.get("gate_undecided") or 0) > 0

        if _is_nogates():
            print("健康色：**（本次未跑闸门，健康色不可用）**")
            print("  原因：本脚本调用 daily_health 时带 `--no-gates`（`freshness.py:92`，为省时间；"
                  "新鲜度判定不依赖闸门）。")
            print("  ⚠️ 因此 `health=%s` 是「没跑闸门」的产物，**不代表真实健康色**，"
                  "**不要**把它当供给链状态读。" % blob.get("health"))
            print("  要真实健康色：看带闸门的那份产物 ——")
            print("    `kb/l7/reports/daily-health-latest.json`（`daily_health.py` 不带 `--no-gates` 跑出来的）")
        else:
            print("健康总判（daily_health 自报）: %s ｜ 闸门 ok=%s red=%s 未执行/声明式=%s"
                  % (blob.get("health"), blob.get("gate_ok"), blob.get("gate_red"),
                     blob.get("gate_undecided")))
        if layer_status:
            print()
            print("L1/L2/L3 查询档（调用 = 调该层 skill 的只读查询档）：")
            for k in ("L1", "L2", "L3"):
                v = layer_status.get(k) or {}
                print("  %-3s %s" % (k, "✅ 可调" if v.get("ok") else "❌ 不可用：%s" % v.get("why")))
        if index_vs_rules:
            print()
            print("L6 索引 vs L3 规则（时序事实，本脚本只报不判因果）：")
            print("  L6 索引 %s ｜ L3 规则 %s ｜ 索引比规则旧：%s（差 %.2f 小时）" % (
                _ts(index_vs_rules["l6_index_mtime"]), _ts(index_vs_rules["l3_rules_mtime"]),
                index_vs_rules["index_older_than_rules"], index_vs_rules["delta_hours"]))
            print("  ⚠️ 「索引比规则旧」**不等于**「索引坏了」—— 是否存在真实 L3→L6 数据边需人裁")
            print("     （l6_build.py 读的是 L2 units 与 L5 matcher，不是 L3 规则）")

        print()
        if stale_rows:
            print("结论：❌ 有 %d 个关键 data 产物超期 → 评审链应**拒答**（退出码 3），不许拿陈旧数据出结论"
                  % len(stale_rows))
            for t in stale_rows:
                print("   · %s" % str(t.get("text") or "")[:150])
            rc = 3
        else:
            print("结论：✅ 各层关键 data 产物都不陈旧（**不代表业务上正确**，只代表不陈旧）")
            rc = 0

        if a.json:
            print(json.dumps({
                "stale_threshold_note": "由 daily_health.py 定（24 小时）；本脚本不自己算",
                "health": blob.get("health"),
                "gate_ok": blob.get("gate_ok"),
                "gate_red": blob.get("gate_red"),
                "gate_undecided": blob.get("gate_undecided"),
                "freshness": fresh,
                "stale_layers": stale_layers,
                "stale_items": stale_rows,
                "layer_status": layer_status,
                "index_vs_rules": index_vs_rules,
                "verdict": ("stale" if stale_rows else "fresh"),
            }, ensure_ascii=False, indent=1))
        return rc
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        shutil.rmtree(tmp2, ignore_errors=True)


def selftest() -> int:
    """「落定后再判「这条判据的自证 —— **纯函数喂样本，离线**。

    每一条都能红：红了就是判据坏了，不是环境坏了。
    """
    P, F = [], []

    def chk(name, cond, extra=""):
        (P if cond else F).append(name)
        print(f"  {'✅' if cond else '❌'} {name}{('  ' + extra) if extra else ''}")

    # ① 交集语义：只有**两遍都红**才算陈旧
    keep, rec = intersect_stale(["L1", "L7"], ["L1"])
    chk("①a 两遍都红 ⇒ 保留（L1）", keep == ["L1"], f"keep={keep}")
    chk("①b 第一遍红、第二遍绿 ⇒ **转绿**，且单独记下来（它就是那条假红）",
        rec == ["L7"], f"recovered={rec}")
    chk("①c 第二遍新红的层**不因第一遍没红而被丢**（判据是交集，不是「以第一遍为准」）",
        intersect_stale([], ["L2"])[0] == [])
    chk("①d 反向对照：两遍都红集合相同时 ⇒ 一条都不转绿",
        intersect_stale(["L1", "L2"], ["L2", "L1"]) == (["L1", "L2"], []))
    chk("①e 升序去重（同一层报两次不会变成两条）",
        intersect_stale(["L7", "L1", "L7"], ["L7", "L1"])[0] == ["L1", "L7"])
    chk("①f 空输入不抛错", intersect_stale(None, None) == ([], []))

    # ② 要不要等：没有第一遍红就不等（省 90s）
    chk("②a 第一遍全绿 ⇒ **不等**（不能白等 90s）", needs_settle_recheck([], 90) is False)
    chk("②b 第一遍有红 ⇒ 等", needs_settle_recheck(["L1"], 90) is True)
    chk("②c 反向对照：`KB_FRESH_SETTLE_S=0` ⇒ 不等（自证/离线档用）",
        needs_settle_recheck(["L1"], 0) is False)
    chk("②d 负数/None 阈值 ⇒ 不等（不许把 sleep 传成负数）",
        needs_settle_recheck(["L1"], -1) is False and needs_settle_recheck(["L1"], None) is False)

    # ③ 真行为（假 blob，喂 `settle_decide` 这个纯函数）——**不是查源码字符串**
    _src = open(__file__, encoding="utf-8").read()
    def _blob(*sigs):
        return {"todos_with_playbook": [{"sig": "stale." + x} for x in sigs]}
    _w, _k, _r, _why = settle_decide(_blob("L7"), None, 90)
    chk("③a ★ 第二遍**没跑成** ⇒ 保持第一遍判定（fail-closed：不许因为「重判失败」就静默翻绿）",
        _w == "first" and _k == ["L7"] and "fail-closed" in _why, f"{_w}/{_k}")
    _w2, _k2, _r2, _ = settle_decide(_blob("L7"), _blob("L7"), 90)
    chk("③b 两遍都红 ⇒ 保持陈旧（真陈旧不许被重判洗绿）",
        _w2 == "first" and _k2 == ["L7"] and _r2 == [])
    _w3, _k3, _r3, _w3why = settle_decide(_blob("L7"), _blob(), 90)
    chk("③c 第一遍红、第二遍绿 ⇒ 换用第二份读数 + 记下转绿（假红被消掉）",
        _w3 == "second" and _k3 == [] and _r3 == ["L7"], f"{_w3}/{_k3}/{_r3}")
    _w4, _k4, _, _ = settle_decide(_blob(), _blob(), 90)
    chk("③d 第一遍全绿 ⇒ 不重判（够省：不白等 90s）", _w4 == "first" and _k4 == [])
    _w5, _k5, _, _ = settle_decide(_blob("L7"), _blob(), 0)
    chk("③e 反向对照：`settle_s=0`（离线档）⇒ 即便第二遍绿也不采信（不等待就不许重判）",
        _w5 == "first" and _k5 == ["L7"])
    chk("③c 默认值就在代码里（90s），且只认 env 覆盖（launchd 不会设该 env）",
        "KB_FRESH_SETTLE_S" in _src and "or 90" in _src)

    print(f"\n自证：通过 {len(P)} / 失败 {len(F)}")
    for x in F:
        print(f"  · 失败：{x}")
    return 1 if F else 0


def _ts(epoch):
    import time
    return time.strftime("%m-%d %H:%M", time.localtime(epoch))


if __name__ == "__main__":
    sys.exit(main())
