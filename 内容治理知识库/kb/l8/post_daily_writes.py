#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""post_daily_writes.py —— 日更收尾之后，还有谁往供给链写了？（只读）

## 为什么有它（2026-10-13 事故驱动；Owner 同意「推荐 ①+③」）

那天 03:30 的日更**跑得好好的**：八层退出码 0、03:57:38 的日报里没有任何 `stale.*`。
然后 **15:29:48** 又有人跑了一次 L4 发号写：

    kb/l4/runs/20261013-prd-article.json
      command  = kb/kbpy .work/l4_article.py 20261013-prd --apply
      products = [kb/l4/registry/l4.json, kb/l3/candidates/rules.jsonl, …]

而 L5 的关键产物还是 **03:41** 那份 ⇒ `daily_health` 判 `stale.L5` ——
**它不是"超过 24 小时"**（L5 才 12.1 小时），红在另一半判据：**「上游变了、本层没跟上」**。
⇒ `freshness.py` 退出码 3 ⇒ 评审链 fail-closed 拒答 ⇒ 守衡侧那张卡是 `NEEDS_INPUT`。

库对这一状态**只有一味药**：重跑日更（15:44 那轮就是受控自愈按这条口径踢的，
跑完约 28 分钟，期间送审全量拒答）。

⇒ 所以要有一条读数回答：**「日更收尾之后，还有谁写了供给链？」**
把「谁写的、哪一层、什么时候、什么命令」点名出来，人才有得选：
**① 写完立刻补一轮收尾；② 下次把这类写排到日更之后跑。**

## 本件**只归因、不下判定**（这条是纪律，不是省事）

「陈旧 / 落后」的尺子**只有一把**：`daily_health.py`（`freshness.py` 读它的结论）。
本件**不新造第二把** —— 它只列出日更收尾之后的**真写档**。
是否告警由调用方（`watch_review_readiness.py`）把本件与**同一轮的 freshness 读数**合起来判：
**写了 ＋ 下游确实落后** ⇒ 告警；**写了但下游没落后** ⇒ 只记读数，不吵。

## 什么算「真写档」（本件唯一需要判的地方 ⇒ 所以它配了反向对照）

扫 `kb/l0/runs` … `kb/l6/runs` 的落章，**先排除**：

  · `run_id`（或文件名）以 `daily-` 开头 —— **那是日更自己**。
    不排除的话**每一轮日更都会把自己报成 culprit**（它的层落章也带 `--apply`、时刻也最新）。
  · 预演件：`dry_run is True` ／ `applied is False` ／ `apply is False`。
    （评审链每天落几十份 `*-dryrun.json` 前置记账 —— 不排除的话这条读数天天在响。）
  · 发生时刻 ≤ 日更收尾时刻。

**算写入**（四条任一）：`command` 里有 `--apply` ／ `applied is True` ／ `apply is True` ／
有非空 `products` 清单。**四条都不落地** ⇒ 记进 `skipped`（**不静默**，但**不算写入** ——
宁可漏报也不误报：误报会把"谁写的"指错人）。

## 用法

    python3 kb/l8/post_daily_writes.py             # 人读
    python3 kb/l8/post_daily_writes.py --json      # 机器读（调用方用这个）
    python3 kb/l8/post_daily_writes.py --selftest  # 反向对照：真实样本 ＋ 变异

退出码：`0` = 读数采到（**无论有没有写入**）｜ `4` = **未测**（读不到日更收尾时刻，不猜、不判绿）
｜ `2` = 用法错。
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
import tempfile
import time
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))          # …/知识库/内容治理

#: 扫哪些目录（层落章）。**不收** `kb/l7/runs`（跨层闸门，`skill_write=false`）与
#: `kb/l8/runs`（驱动自己的记录）—— 它们的记录不都是「层写档」，收进来会指错人。
LAYER_RUN_DIRS = ["kb/l%d/runs" % i for i in range(0, 7)]

#: 日更收尾时刻的来源：`kb/l8/observe_layers.py --land` 落的八层观测 sidecar。
FRESHNESS_SIDECAR = os.path.join("kb", "l7", "registry", "layer_run_freshness.json")

DAILY_PREFIX = "daily-"

#: 时刻字段的读取顺序（先 ISO `at`，再当地格式 `finished_at`，再 epoch）。
TS_KEYS = ("at", "finished_at", "ended_at", "ts", "time",
           "executed_at", "measured_at", "started_at")


def _fmt(t):
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(t)) if t else None


def _parse_ts(v):
    """把落章里各式时刻解析成 epoch。**认不出来就返回 None**（不猜、不默认成"现在"）。"""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    if not s:
        return None
    try:
        return float(s)                                    # epoch 写法
    except ValueError:
        pass
    for cand in (s.replace("Z", "+00:00"), s.replace(" ", "T", 1)):
        try:
            dt = datetime.fromisoformat(cand)
        except ValueError:
            continue
        if dt.tzinfo is None:                              # 库里落的是**本机时刻**（实测：
            return time.mktime(dt.timetuple()) + dt.microsecond / 1e6   # 15:29:48 与 mtime 同）
        return dt.timestamp()
    return None


def record_ts(rec):
    """`(epoch, 字段名)` —— 认不出来返回 `(None, None)`。"""
    for k in TS_KEYS:
        if k in rec:
            t = _parse_ts(rec.get(k))
            if t is not None:
                return t, k
    return None, None


def record_id(rec):
    for k in ("run_id", "run", "pipeline_run_id"):
        v = rec.get(k)
        if v:
            return str(v)
    return ""


def is_daily(rec, path=""):
    """这条落章是不是**日更自己**的（前缀 `daily-`，run_id 或文件名任一看得出就算）。"""
    return (record_id(rec).startswith(DAILY_PREFIX)
            or os.path.basename(path or "").startswith(DAILY_PREFIX))


def _layer_of(rec, path=""):
    lay = rec.get("layer")
    if isinstance(lay, str) and re.fullmatch(r"L[0-7]", lay.strip()):
        return lay.strip()
    m = re.search(r"kb[/\\](l[0-7])[/\\]runs", path or "")
    return m.group(1).upper() if m else None


def classify(rec, path="", finish=None):
    """纯函数：一条落章 ⇒ `(kind, detail)`，kind ∈ {`"write"`, `"skip"`}。

    **喂样本就能判，不碰盘** —— 自证靠它（同 `watch_review_readiness._l1_index_verdict` 的做法）。

    ★ 顺序即口径：**先排日更自己 → 再排预演 → 再看时刻 → 最后才判"是不是写档"**。
      任何一步认不出来 ⇒ `skip` **并写明原因**（不静默），**绝不默认成写入**。
    """
    rid = record_id(rec)
    if is_daily(rec, path):
        return "skip", {"why": "日更自己的落章（`daily-` 前缀）", "run_id": rid}
    if rec.get("dry_run") is True:
        return "skip", {"why": "预演（`dry_run=true`）", "run_id": rid}
    for k in ("applied", "apply"):
        if rec.get(k) is False:
            return "skip", {"why": "预演（`%s=false`）" % k, "run_id": rid}
    t, tkey = record_ts(rec)
    if t is None:
        return "skip", {"why": "读不到发生时刻（不猜）", "run_id": rid}
    if finish is not None and t <= float(finish):
        return "skip", {"why": "发生在日更收尾（含）之前", "run_id": rid, "at": _fmt(t)}
    cmd = str(rec.get("command") or rec.get("cmd") or "")
    prods = rec.get("products") or []
    if "--apply" in cmd:
        via = "命令带 `--apply`"
    elif rec.get("applied") is True or rec.get("apply") is True:
        via = "落章声明 `applied/apply=true`"
    elif prods:
        via = "落章带非空 `products` 清单"
    else:
        return "skip", {"why": "未声明写档（无 `--apply` / 无 `applied` / 无 `products`）",
                        "run_id": rid, "at": _fmt(t), "ts_key": tkey}
    return "write", {"run_id": rid, "layer": _layer_of(rec, path), "at": _fmt(t), "ts": t,
                     "ts_key": tkey, "action": rec.get("action"), "command": cmd,
                     "products": [str(x) for x in prods][:8], "via": via}


def daily_finish(root, sidecar=None):
    """日更收尾时刻 ⇒ `(epoch, 说明)`。读不到 ⇒ `(None, 原因)` = **未测**（不猜、不判绿）。"""
    path = sidecar or os.path.join(root, FRESHNESS_SIDECAR)
    rel = os.path.relpath(path, root) if path.startswith(root) else path
    if not os.path.exists(path):
        return None, "找不到 %s" % rel
    try:
        with open(path, encoding="utf-8") as fh:
            d = json.load(fh)
    except Exception as e:                                  # noqa: BLE001
        return None, "读不了 %s：%r" % (rel, e)
    best, best_rid = None, ""
    for _lay, rec in (d.items() if isinstance(d, dict) else []):
        if not isinstance(rec, dict) or not record_id(rec).startswith(DAILY_PREFIX):
            continue
        t, _k = record_ts(rec)
        if t is not None and (best is None or t > best):
            best, best_rid = t, record_id(rec)
    if best is None:
        return None, "%s 里没有 `daily-` 开头的层观测 ⇒ 认不出日更收尾时刻" % rel
    return best, "%s ｜ run_id=%s" % (rel, best_rid)


def scan(root, finish, dirs=None):
    """⇒ `(writes, skipped, seen)`。`skipped` **不静默**：每条都带 `why`。"""
    writes, skipped, seen = [], [], 0
    for rel in (dirs or LAYER_RUN_DIRS):
        d = os.path.join(root, rel)
        if not os.path.isdir(d):
            skipped.append({"path": rel, "why": "目录不在（跳过，不静默）"})
            continue
        for p in sorted(glob.glob(os.path.join(d, "*.json"))):
            rp = os.path.relpath(p, root)
            try:
                with open(p, encoding="utf-8") as fh:
                    rec = json.load(fh)
            except Exception as e:                          # noqa: BLE001
                skipped.append({"path": rp, "why": "落章读不了：%r" % e})
                continue
            if not isinstance(rec, dict):
                skipped.append({"path": rp, "why": "落章不是对象"})
                continue
            seen += 1
            kind, detail = classify(rec, p, finish)
            detail["path"] = rp
            (writes if kind == "write" else skipped).append(detail)
    writes.sort(key=lambda w: w.get("ts") or 0)
    return writes, skipped, seen


def _why_hist(skipped):
    hist = {}
    for s in skipped:
        k = re.split(r"[（(]", str(s.get("why") or "?"))[0].strip()
        hist[k] = hist.get(k, 0) + 1
    return hist


def main(argv=None):
    ap = argparse.ArgumentParser(description="日更收尾之后的供给链写入（只读；只归因不下判定）")
    ap.add_argument("--root", default=ROOT)
    ap.add_argument("--json", action="store_true", help="机器读（调用方用这个）")
    ap.add_argument("--limit", type=int, default=10, help="人读时最多列几条写入")
    ap.add_argument("--selftest", action="store_true", help="反向对照：真实样本 ＋ 变异")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()

    finish, src = daily_finish(a.root)
    if finish is None:
        out = {"tested": False, "note": "未测：%s" % src, "writes": [], "skipped_n": 0}
        print(json.dumps(out, ensure_ascii=False, indent=1) if a.json
              else "供给链写入读数（日更之后）｜**未测**：%s" % src)
        return 4
    writes, skipped, seen = scan(a.root, finish)
    out = {"tested": True, "daily_finish": _fmt(finish), "daily_finish_epoch": finish,
           "daily_finish_src": src, "n": len(writes), "writes": writes,
           "skipped_n": len(skipped), "skipped_hist": _why_hist(skipped),
           "skipped": skipped[:50], "seen": seen}
    if a.json:
        print(json.dumps(out, ensure_ascii=False, indent=1))
        return 0

    print("=" * 78)
    print("供给链写入读数（**日更收尾之后**）｜只读 ｜ 本件只归因，不判陈旧")
    print("=" * 78)
    print("  日更收尾   %s ｜ %s" % (_fmt(finish), src))
    print("  真写档     %d 笔" % len(writes))
    for w in writes[:max(0, a.limit)]:
        print("    · %s ｜ RUN=%s ｜ %s ｜ %s" % (w.get("layer") or "?", w.get("run_id") or "?",
                                                  w.get("at") or "?", w.get("via")))
        if w.get("command"):
            print("        %s" % str(w["command"])[:160])
        if w.get("products"):
            print("        产物：%s" % " ｜ ".join(w["products"][:5]))
    if len(writes) > a.limit:
        print("    …（另有 %d 笔，见 --json）" % (len(writes) - a.limit))
    print("  不计入     %d 笔：%s" % (len(skipped),
                                     " ｜ ".join("%s×%d" % (k, v) for k, v in
                                                sorted(_why_hist(skipped).items(),
                                                       key=lambda kv: -kv[1])) or "—"))
    print("-" * 78)
    if not writes:
        print("结论：日更收尾之后**没有**新的供给链写入 ⇒ 下游的落后不是「白天写库」造成的。")
    else:
        print("结论：日更收尾之后**有 %d 笔真写档**（上面点名了层/RUN/命令）⇒ "
              "写过的那些层的下游，存在「上游变了、本层没跟上」的落后。" % len(writes))
        print("      陈旧与否**不由本件判**（同一把尺子：`freshness.py` / `daily_health.py`）；")
        print("      两条路：① 写完立刻补一轮收尾；② 下次把这类写**排到日更之后**跑。")
    return 0


# ────────────────────────────────────────────── 反向对照（自证）

P, F = [], []


def chk(name, ok, extra=""):
    (P if ok else F).append(name if ok else "%s ｜ %s" % (name, str(extra)[:220]))


def _real_sample(root, pattern, pred=None):
    """取一份**逐字真实样本**（只读）。找不到就是不找得到 —— 不许现场编一份顶替。"""
    for p in sorted(glob.glob(os.path.join(root, pattern)), reverse=True):
        try:
            with open(p, encoding="utf-8") as fh:
                rec = json.load(fh)
        except Exception:                                   # noqa: BLE001
            continue
        if isinstance(rec, dict) and (pred is None or pred(rec, p)):
            return rec, p
    return None, None


def selftest():
    print("post_daily_writes · 反向对照（离线；喂样本给纯函数，不动真库一个字节）")
    finish = time.mktime(time.strptime("2026-10-13 03:58:06", "%Y-%m-%d %H:%M:%S"))

    wr, wrp = _real_sample(ROOT, "kb/l[0-6]/runs/*.json",
                           lambda r, p: "--apply" in str(r.get("command") or "")
                           and not is_daily(r, p))
    dr, drp = _real_sample(ROOT, "kb/l[0-6]/runs/*dryrun*.json", lambda r, p: True)
    ar, arp = _real_sample(ROOT, "kb/l8/runs/*.json",
                           lambda r, p: r.get("apply") is False or r.get("applied") is False)

    if wr is None:
        chk("①a 真实正例：仓里有一份带 `--apply` 的层落章（缺了这条自证就没了依据）", False, "找不到")
    else:
        k, d = classify(wr, wrp, None)                      # finish=None：只验形状，时刻闸门归 ④
        chk("①a 真实正例：真实 `--apply` 落章 ⇒ **write**（层/时刻都读得出来）",
            k == "write" and d.get("layer") and d.get("at"), "%s %s %s" % (k, d.get("via"), d.get("at")))
        # ★ 事件那一笔（2026-10-13 15:29:48 的 L4 发号写）必须被这条判据认出来。
        #   `finish` 由**样本自己的时刻往前推 60 秒**得出 —— 不写死日期，换哪一天都成立。
        k2, d2 = classify(wr, wrp, (d.get("ts") or 0) - 60)
        chk("①a2 时刻闸门：同一份真写档放在「日更收尾之后」⇒ **write**（放在之前 ⇒ 见 ④）",
            k2 == "write", "%s %s" % (k2, d2.get("why")))

    if dr is None:
        chk("①b 真实反例：仓里有一份预演件（评审链每天落几十份，不许被算成写入）", False, "找不到")
    else:
        k, d = classify(dr, drp, None)
        chk("①b 真实反例：真实预演件 ⇒ **skip**，原因写「预演」",
            k == "skip" and "预演" in str(d.get("why")), "%s %s" % (k, d.get("why")))
        mut = {k2: v for k2, v in dr.items() if k2 not in ("dry_run", "applied", "apply")}
        mut["dry_run"], mut["applied"] = False, True
        mut["command"] = "kb/kbpy .work/l4_article.py x --apply"
        k2, _d2 = classify(mut, drp, None)                  # finish=None：只验形状
        chk("②b 变异（判据不许恒假）：把真实预演件改成真写档 ⇒ **必须变成 write**",
            k2 == "write", k2)

    if ar is None:
        chk("①c 真实反例：仓里有 `apply=false` 的落章（另一种预演写法）", False, "找不到")
    else:
        k, d = classify(ar, arp, finish)
        chk("①c 真实反例：真实 `apply=false` 落章 ⇒ **skip**（不许当成写档）",
            k == "skip", "%s %s" % (k, d.get("why")))

    if wr is not None:
        mut = {k2: v for k2, v in wr.items()
               if k2 not in ("command", "cmd", "products", "applied", "apply", "dry_run")}
        k, d = classify(mut, wrp, finish)
        chk("②a 变异（判据不许恒真）：抹掉 `--apply` 与 `products` ⇒ **必须变成 skip**",
            k == "skip", "%s %s" % (k, d.get("why")))
    k, d = classify({"run_id": "daily-20261013-1544-L5", "layer": "L5", "at": "2026-10-13T15:44:10",
                     "command": "kb/kbpy l7/scripts/kb_pipeline.py --sync --apply"}, "x.json", finish)
    chk("③ 日更自己**不算 culprit**（否则每轮日更都会把自己报出来）",
        k == "skip" and "日更自己" in str(d.get("why")), "%s %s" % (k, d.get("why")))

    base = {"run_id": "x", "layer": "L5", "command": "kb/kbpy y --apply"}
    k1, _ = classify({**base, "at": time.strftime("%Y-%m-%dT%H:%M:%S",
                                                  time.localtime(finish - 1))}, "x.json", finish)
    k2, _ = classify({**base, "at": time.strftime("%Y-%m-%dT%H:%M:%S",
                                                  time.localtime(finish + 1))}, "x.json", finish)
    chk("④ 时刻边界：收尾前 1 秒 ⇒ skip ｜ 收尾后 1 秒 ⇒ write",
        k1 == "skip" and k2 == "write", "%s/%s" % (k1, k2))

    k, d = classify({"run_id": "y", "layer": "L4", "finished_at": "2026-10-13 15:29:48",
                     "command": "kb/kbpy z --apply"}, "x.json", finish)
    chk("⑤ 只带当地格式 `finished_at` 也认（库里两种写法都有）",
        k == "write" and d.get("at") == "2026-10-13 15:29:48", "%s %s" % (k, d.get("at")))

    k, d = classify({"run_id": "z", "layer": "L4", "note": "no ts", "command": "kb/kbpy z --apply"},
                    "x.json", finish)
    chk("⑥ 读不到时刻 ⇒ **skip 且写明原因**（不猜成「刚发生」）",
        k == "skip" and "读不到发生时刻" in str(d.get("why")), "%s %s" % (k, d.get("why")))

    try:
        with tempfile.TemporaryDirectory() as td:
            for sub in LAYER_RUN_DIRS:
                os.makedirs(os.path.join(td, sub), exist_ok=True)
            samples = {
                "kb/l4/runs/w.json": {"run_id": "w", "layer": "L4", "at": "2026-10-13T15:29:48",
                                      "command": "kb/kbpy w --apply"},
                "kb/l4/runs/d.json": {"run_id": "d", "layer": "L4", "at": "2026-10-13T15:29:48",
                                      "dry_run": True, "applied": False},
                "kb/l5/runs/daily-20261013-1544-L5.json": {"run_id": "daily-20261013-1544-L5",
                                                           "layer": "L5", "executed_at": finish + 60},
                "kb/l6/runs/n.json": {"run_id": "n", "layer": "L6", "at": "2026-10-13T15:29:48"},
            }
            for rel, rec in samples.items():
                with open(os.path.join(td, rel), "w", encoding="utf-8") as fh:
                    json.dump(rec, fh, ensure_ascii=False)
            ws, sk, seen = scan(td, finish)
            chk("⑦ 端到端 `scan()`：4 份样本 ⇒ **恰好 1 笔写入**（其余进 skipped，不静默）",
                len(ws) == 1 and ws[0]["run_id"] == "w" and len(sk) == 3 and seen == 4,
                "writes=%d skipped=%d seen=%d" % (len(ws), len(sk), seen))
            f2, src2 = daily_finish(td)
            chk("⑧ 未测：认不出日更收尾时刻 ⇒ **不判绿**（返回 None ＋ 原因）",
                f2 is None and "找不到" in str(src2), str(src2)[:80])
    except Exception as e:                                  # noqa: BLE001
        chk("⑦ 端到端 `scan()`：4 份样本 ⇒ **恰好 1 笔写入**（其余进 skipped，不静默）", False, repr(e))
        chk("⑧ 未测：认不出日更收尾时刻 ⇒ **不判绿**（返回 None ＋ 原因）", False, "见 ⑦")

    f3, src3 = daily_finish(ROOT)
    chk("⑨ 真库：日更收尾时刻读得出来（sidecar 里 `daily-` 观测的最大 `executed_at`）",
        f3 is not None, str(src3)[:100])

    print("反向对照：通过 %d / 失败 %d" % (len(P), len(F)))
    for x in F:
        print("  · 失败：%s" % x)
    return 1 if F else 0


if __name__ == "__main__":
    sys.exit(main())
