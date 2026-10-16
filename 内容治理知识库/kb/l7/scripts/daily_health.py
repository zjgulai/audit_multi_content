#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""daily_health.py —— L0–L7 每日只读体检日报（P0）

## 它是什么 / 不是什么

**是**：驱动 `kb/l7/scripts/kb_pipeline.py --check`（只读、自带零写自证），
把它给不出的**「落后量」**补上，然后出两份产物：
  * `kb/l7/reports/<YYYY-MM-DD>-daily-health.md`   —— 给人看的日报
  * `kb/l7/reports/daily-health-latest.json`       —— 机器可读（给后续 --sync / 通知用）

**不是**：不是新的编排器。编排器只有 `kb_pipeline.py` 一个（本脚本只是它的调度外壳）。

## 为什么需要它（实测依据）

1. `kb_pipeline.py --check` 只报**闸门过没过**，不报**落后多少**。实测：L3 台账里记的
   L2 输入是 10,021 行，而 L2 现在 12,144 行 —— 差 2,123 个单元，`--check` 里看不见。
2. 各层「最后一次运行」各不相干：L2 18:41 / L3 14:46 / L4 11:00 / L5 昨天 —— 需要一张
   新鲜度表把它们摆在一起，否则"每层都能跑"会掩盖"没人串"。
3. 只报红没人管：日报必须回答「**要人做什么**」，否则第三天就没人看。

## 写通道（本库硬规定）

python 写 `.md` 会落成「stat 虚高 4096」的信封态（宿主读成乱码）。
→ 一律「python 生成内容 → 写**无扩展名**临时件 → `/bin/cp` 落到目标」。
本脚本对 `.md` 与 `.json` 都走这条通道（`.json` 其实安全，统一起来少一个例外）。

## 零写边界

**只写 `kb/l7/reports/`**；不碰 `kb/l0…l6` 的任何数据文件与台账。
`--check` 自身另有零写自证（跑前跑后对 4,000+ 个层产物取 mtime 快照，变化即报错）。

## 退出码

  0 = **本次体检跑成功**（报告已落盘）。**健康与否看报告内容，不看退出码** ——
      定时任务每天非 0 退出只会污染日志，不会有人因此被通知；
      要接告警请读 `daily-health-latest.json` 的 `health` 字段。

用法：
    kb/kbpy l7/scripts/daily_health.py                 # 出日报
    kb/kbpy l7/scripts/daily_health.py --no-gates      # 跳过闸门，只出新鲜度/落后量表
    kb/kbpy l7/scripts/daily_health.py --outdir <dir>  # 换输出目录（默认 kb/l7/reports）
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
KB = os.path.dirname(os.path.dirname(HERE))        # …/kb
ROOT = os.path.dirname(KB)                          # kb/ 的上一级（cwd 约定）
KBPY = os.path.join(KB, "kbpy")

# ── 新鲜度判据（批次18 · 第0块 · 裁定 A）────────────────────────────────────────
# **实现在 `layer_freshness.py`，本文件不重算第二遍** —— 同一判据算两遍必然分叉，
# 本库已因此返工多次（见 `freshness.py` 顶部那段「3 vs 6 分叉」的自述）。
sys.path.insert(0, HERE)
import layer_freshness as _lf                        # noqa: E402
#: `--kb-root` 覆盖：**只给反测夹具用**（默认 None = 用真实 KB）。
#: 反测一律用副本/夹具，不许拿真实库试（纪律 6）。
_KB_ROOT_OVERRIDE = None

#: 每层的「关键产物」——新鲜度只看这些，不看整目录 mtime（目录 mtime 会被无关写入带偏）
#: (库根相对路径, 类别)。类别只有两种：
#:   data     = 这一层的**产物**（"这层最近干过活没有"只看它）
#:   registry = 注册表/契约（**被别人改一下不代表这层跑过** —— 2026-09-30 实测踩过：
#:              只因为我更新了 layers.yaml，L7 那行就显示成"2 分钟前刚跑过"，是假新鲜）
KEY_OUTPUTS = {
    "L0": [("l0/manifest.jsonl", "data"), ("l0/registry/kb.json", "registry")],
    "L1": [("l1/manifest_l1.jsonl", "data"), ("l1/index/l1.jsonl", "data")],
    "L2": [("l2/units.jsonl", "data"), ("l2/manifest_l2.jsonl", "data")],
    "L3": [("l3/candidates/rules.jsonl", "data"), ("l3/rejected.jsonl", "data"),
           ("l3/manifest_l3.jsonl", "data")],
    "L4": [("l4/canonical/wording_entry.jsonl", "data"), ("l4/registry/l4.json", "registry")],
    "L5": [("l5/p0_patterns.jsonl", "data"), ("l5/registry/l5.json", "registry")],
    "L6": [("l6/registry/l6.json", "registry"), ("l6/selftest.json", "data")],
    "L7": [("l7/registry/skills.yaml", "registry"), ("l7/registry/layers.yaml", "registry"),
           ("l7/registry/routes.yaml", "registry")],
}

#: 各层台账里「记的输入规模」→ 与上游现状比，得到落后量。
#: 只做**能由台账直接读出**的比对，不做任何推测（推不出的层如实写「推不出」）。
BACKLOG_FROM_LEDGER = [
    # (下游层, 台账文件, 台账里表示上游规模的键路径, 上游文件, 上游一行=一单元)
    ("L3", "l3/registry/l3.json", ("accounting", "l2_total"), "l2/units.jsonl"),
]

#: 差异 → 「要人做什么」。按 key 前缀匹配，命中即附上。
#: （P3 起，每条待办都会再挂上 kb/l7/registry/failure-playbook.yaml 的处置条目：
#:   谁 / 做什么 / 命令 / 不许做什么 / 复开条件 —— 处置办法不在本文件里现编。）
TODO_MAP = [
    ("91403", "把「守衡」加成**可阅读协作者**（资源级 ACL，重试/换身份都无效，只能等所有者共享）"),
    ("拉取失败", "同上：先看是不是 91403；不是再按 kb-l0-feishu §3.2 的判定顺序走（token expired → 发设备码）"),
    ("飞书多", "跑 L0 同步：人开窗口执行 `kb/kbpy l8/reconcile_l0_feishu.py <RUN> --apply`（**需人工**：飞书 token 实测有效期 2 小时）；按声明应排除的记录见 kb/l7/registry/l0-expected-diffs.yaml"),
    # 闸门红 / 掉线**不在这里**：下面按层遍历 gate_state，逐层点名（带层号，处置条目也更具体）。
    # 放在这里只会生成一条「某层闸门红了」的泛泛待办，把逐层那条盖住。
]


def _playbook():
    """读失败处置表（P3）。取不到就当空表——日报要能出，不能因为处置表缺失而整个不出。"""
    try:
        import yaml
        d = yaml.safe_load(open(os.path.join(KB, "l7/registry/failure-playbook.yaml"),
                                encoding="utf-8")) or {}
        return {e.get("id"): e for e in (d.get("entries") or [])}
    except Exception:                                # noqa: BLE001
        return {}


def _pb(pb, sig):
    """取处置条目：精确 id → 同前缀 `*` → None（取不到就如实说没有，不现编）。"""
    if not pb:
        return None
    return pb.get(sig) or pb.get(str(sig).split(".")[0] + ".*")


def _pb_line(pb, sig):
    e = _pb(pb, sig)
    if not e:
        return "→ ⚠️ 没有登记的处置办法（%s）：补进 kb/l7/registry/failure-playbook.yaml" % sig
    return ("→ **谁**：%s ｜ **命令**：%s\n"
            "      **做什么**：%s\n"
            "      **不许**：%s ｜ **复开**：%s"
            % (e.get("owner"), e.get("command"), e.get("do"),
               e.get("forbidden"), e.get("reopen_when")))


sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from run_record import record as _run_record
except Exception:                     # noqa: BLE001
    _run_record = None


def sh(cmd, cwd=ROOT, timeout=1800):
    """跑一条命令，返回 (rc, stdout, stderr)。"""
    try:
        p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout, p.stderr
    except subprocess.TimeoutExpired:
        return 124, "", "超时（%ss）" % timeout


def mtime(p):
    """p 是**库根相对**路径（写作 l0/...），所以与 KB 拼，不是与 ROOT 拼。"""
    try:
        return os.path.getmtime(os.path.join(KB, p))
    except OSError:
        return None


def fmt_ts(t):
    return time.strftime("%m-%d %H:%M", time.localtime(t)) if t else "缺失"


def human_age(t, now):
    if not t:
        return "缺失"
    d = now - t
    if d < 3600:
        return "%d 分钟前" % (d // 60)
    if d < 86400:
        return "%.1f 小时前" % (d / 3600)
    return "%.1f 天前" % (d / 86400)


def count_lines(relpath):
    p = os.path.join(KB, relpath)
    if not os.path.isfile(p):
        return None
    try:
        with io.open(p, encoding="utf-8") as fh:
            return sum(1 for l in fh if l.strip())
    except OSError:
        return None


def write_via_cp(text, dst, tmpdir="/tmp"):
    """写通道：python 生成 → 无扩展名临时件 → /bin/cp。避免 .md 信封态。"""
    tmp = os.path.join(tmpdir, "kb_daily_health.tmp")
    io.open(tmp, "w", encoding="utf-8").write(text)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    subprocess.run(["/bin/cp", tmp, dst], check=True)


def load_json_rel(rel):
    try:
        return json.load(io.open(os.path.join(KB, rel), encoding="utf-8"))
    except Exception:
        return None


def l0_copy_age(kb_root: str, table_name: str):
    """该表在 L0 的副本：`(记录数, 最新 mtime, 距今天数)`；目录不存在返回 `(None, None, None)`。

    ★ 修复2（2026-10-03）：给「**已登记阻断项**」暴露**副本年龄**。
    为什么加（实测）：`l0-expected-diffs.yaml` 把两张拉不到的表登记成了 `pull_failed`（EX-2/EX-3）
    ⇒ 健康色判 GREEN **是对的**（不冤枉管线）。**但登记 ≠ 无害** ——
    `专家修订汇总表` 的 L0 副本停在 **09-23**（395 条）、`内容公式（仅供参考）` 停在 **09-24**（7 条），
    即 **10 天 / 9 天前的快照**，而**评审链照样能引用它们当溯源终点**。
    本函数让"因此已经多旧"**可见**，而不是只报"拉不到"。**只读**：不修任何东西。
    """
    d = os.path.join(kb_root, "l0", "records", table_name or "")
    if not table_name or not os.path.isdir(d):
        return None, None, None
    files = [os.path.join(d, f) for f in os.listdir(d) if f.endswith(".json")]
    if not files:
        return 0, None, None
    newest = max(os.path.getmtime(f) for f in files)
    return len(files), newest, (time.time() - newest) / 86400.0


def dig(d, path):
    x = d
    for k in path:
        if isinstance(x, dict) and k in x:
            x = x[k]
        else:
            return None
    return x


def main():
    global KB
    ap = argparse.ArgumentParser(description="L0–L7 每日只读体检日报")
    ap.add_argument("--no-gates", action="store_true", help="跳过闸门（只出新鲜度/落后量）")
    ap.add_argument("--outdir", default=os.path.join("kb", "l7", "reports"))
    ap.add_argument("--kb-root", default=None,
                    help="**只给反测夹具用**：替换 KB 根（默认用真实库）。不许拿真实库做反测。")
    args = ap.parse_args()
    if args.kb_root:
        KB = os.path.abspath(args.kb_root)
        print("⚠️ --kb-root 覆盖生效：KB=%s（**反测夹具模式**，不读真实库）" % KB)

    now = time.time()
    run_id = time.strftime("%Y%m%d-%H%M")          # ★ 墙钟（⑥ run_id 与墙钟对齐）
    today = time.strftime("%Y-%m-%d")

    # ---- 1. 驱动编排器（只读）
    cmd = [KBPY, "l7/scripts/kb_pipeline.py", "--check", "--json"]
    if args.no_gates:
        cmd.append("--no-gates")
    rc, out, err = sh(cmd)
    pipe = None
    if out.strip():
        try:
            pipe = json.loads(out)
        except json.JSONDecodeError:
            pipe = None
    # 人读输出再来一次（--json 模式把人读版打到 stderr）
    rc2, out2, err2 = sh([KBPY, "l7/scripts/kb_pipeline.py", "--check"] +
                         (["--no-gates"] if args.no_gates else []))
    pipe_human = (out2 or "") + (err2 or "")

    # ---- 2. 新鲜度表
    # 一个文件一行 —— 不再把「文件名」和「另一文件的 mtime」拼在同一行（那会指错人）
    rows = []
    for lay, outs in KEY_OUTPUTS.items():
        for rel, kind in outs:
            ts = mtime(rel)
            rows.append({"layer": lay, "file": rel, "kind": kind, "mtime": ts,
                         "age": human_age(ts, now), "lines": count_lines(rel)})

    # ---- 3. 落后量（只做台账能直读的）
    backlog = []
    for down, ledger, keypath, up, in BACKLOG_FROM_LEDGER:
        d = load_json_rel(ledger)
        v = dig(d, keypath) if d else None
        cur = count_lines(up)
        if isinstance(v, int) and isinstance(cur, int):
            backlog.append({"downstream": down, "ledger": ledger, "ledger_says": v,
                            "upstream_now": cur, "gap": cur - v, "upstream": up})
        else:
            backlog.append({"downstream": down, "ledger": ledger, "ledger_says": v,
                            "upstream_now": cur, "gap": None, "upstream": up,
                            "note": "台账读不出输入规模 → 推不出落后量"})

    # ---- 4. 已知阻断项（P1-2 的声明文件；未建立时如实写「未登记」，不假装为空）
    # 声明文件就是 P1-2 的产物：kb/l7/registry/l0-expected-diffs.yaml（**不另立第二个文件** ——
    # 同一件事写两处，早晚不一致）。它的 expected[] 里 kind=pull_failed 的就是"已知阻断项"。
    blockers, blockers_note = [], ""
    kb_blk = os.path.join(KB, "l7/registry/l0-expected-diffs.yaml")
    if os.path.isfile(kb_blk):
        try:
            import yaml as _y
            doc = _y.safe_load(io.open(kb_blk, encoding="utf-8")) or {}
            blockers = [e for e in (doc.get("expected") or [])
                        if e.get("kind") == "pull_failed"]
        except Exception as e:
            blockers_note = "l0-expected-diffs.yaml 读不出来：%s" % e
    else:
        blockers_note = "`kb/l7/registry/l0-expected-diffs.yaml` 不存在（P1-2 未落地）"

    # ---- 5. 汇总
    layers = (pipe or {}).get("layers") or []
    hard = (pipe or {}).get("hard") or []
    # 闸门状态判定（**不要用 startswith("通过")**：实际文案是「只读闸门 通过」，
    # 而「只读闸门 未过」里也含「过」—— 必须显式排掉「未过」，否则会把红算成过。
    def _gate_kind(l):
        st = str(l.get("gate_state", ""))
        su = str(l.get("gate_summary", ""))
        if st.startswith(("未执行", "声明式")):
            return "undecided"
        if "未过" in st or "❌" in su or "**未过**" in st:
            return "red"
        if "通过" in st:
            return "ok"
        return "undecided"
    gate_ok = [l for l in layers if _gate_kind(l) == "ok"]
    gate_red = [l for l in layers if _gate_kind(l) == "red"]
    gate_skip = [l for l in layers if _gate_kind(l) == "undecided"]
    # ── 陈旧判定（批次18 · 第0块 · 裁定 A 落地）────────────────────────────────
    # 旧口径：`kind=="data" 且 mtime > 24h` ⇒ **幂等层结构性失效**：
    #   L2 跑过、`new_units: 0`、`cov_before == cov_after`（正确地什么都没变），
    #   但 units.jsonl 的 mtime 不动 ⇒ 被判陈旧，且**永远清不掉**、误导人反复重跑。
    # 新口径（`kb/l7/scripts/layer_freshness.py` 是唯一实现处，此处不重算第二遍）：
    #   新鲜 ⟺ 最近一次**成功** RUN 在 `layer_freshness.STALE_AFTER` 内（唯一出处，别抄数字）
    #          且（change_state==produced_changes
    #              或 (change_state==no_new_input 且 input_watermark == 现算上游水位)）
    # ★ 防假绿：`no_new_input` **不许自证** —— `layer_freshness.judge()` 一律**现算**上游
    #   水位与落章比对，水位变了就判陈旧（反测 3）。拿不到水位 ⇒ 回退旧 mtime 口径并标注。
    layer_fresh = []
    stale = []
    for _lay in KEY_OUTPUTS:
        try:
            _j = _lf.judge(KB, _lay, now=now)
        except Exception as _e:                        # noqa: BLE001
            _j = {"layer": _lay, "fresh": False, "fallback_used": True,
                  "reason": "layer_freshness 判不了：%s" % str(_e)[:120],
                  "run_path": None, "change_state": None,
                  "input_watermark": None, "current_watermark": None}
        _j["data_rows"] = [r for r in rows
                           if r["layer"] == _lay and r["kind"] == "data"]
        layer_fresh.append(_j)
        if _j["fresh"]:
            continue
        # 判陈旧：逐条 data 产物各给一条待办（人要知道点哪件产物）。
        # ★ L7 是**跨层闸门**、`KEY_OUTPUTS` 里全是 `registry`（没有 data 产物）——
        #   旧代码在这种情况下会生成一条「(该层无 data 产物登记) 落后 —」的**无意义待办**。
        #   现改为：无 data 产物 ⇒ 只出一条**层级**待办，点位指向该层落章，
        #   不当成「某件产物落后」（它没有产物可落后）。
        _dr = _j["data_rows"]
        if _dr:
            for _r in _dr:
                stale.append({"layer": _lay, "file": _r["file"], "age": _r["age"],
                              "mtime": _r.get("mtime"),
                              "reason": _j["reason"],
                              "fallback_used": _j["fallback_used"],
                              "change_state": _j["change_state"],
                              "watermark_match": _j.get("watermark_match")})
        else:
            stale.append({"layer": _lay, "file": "(该层无 data 产物 —— 跨层闸门层)",
                          "age": _j.get("run_age") and "%.1f 小时前" % (_j["run_age"] / 3600.0)
                          or "—",
                          "mtime": None, "reason": _j["reason"],
                          "fallback_used": _j["fallback_used"],
                          "change_state": _j["change_state"],
                          "watermark_match": _j.get("watermark_match")})
    health = "RED" if (hard or gate_red) else ("YELLOW" if (gate_skip or stale or
                                                           any(b["gap"] for b in backlog if b["gap"])) else "GREEN")

    # ── 2.6 注册表陈旧（**信息项，不进健康判据**）──────────────────────────────
    # 为什么单列：`registry` 类是**契约**，「被别人改一下不代表这层跑过」（见 KEY_OUTPUTS 注释）。
    # 但契约**长期不更新**本身是信号（如 L7 的 routes.yaml 停在 09-30）。
    # ⇒ 用**更宽的阈值**（30 天）单列出来，**不参与 health 判定**，也不生成待办。
    #   混进健康判据就会把「契约没改」误报成「这层没跑」—— 正是本块要治的那类假红。
    REGISTRY_STALE_AFTER = 30 * 86400
    registry_stale = [r for r in rows if r["kind"] == "registry" and r["mtime"]
                      and (now - r["mtime"]) > REGISTRY_STALE_AFTER]

    # ---- 6. 「要人做什么」
    todos, seen = [], set()

    def add(text, sig):
        if text not in seen:
            seen.add(text)
            todos.append((text, sig))

    blob = json.dumps({"hard": hard, "layers": layers}, ensure_ascii=False)
    for key, action in TODO_MAP:
        if key in blob:
            add(action, "gate_missing.*" if key in ("未执行", "声明式") else
                ("gate_red.*" if key == "未过" else ""))
    # 闸门逐层：红了按层给处置；掉线了也单独点出来
    for l in layers:
        kind = _gate_kind(l)
        if kind == "red":
            add("**%s 闸门红**：%s" % (l.get("layer"), (l.get("gate_summary") or "")[:110]),
                "gate_red.%s" % l.get("layer"))
        elif kind == "undecided":
            add("**%s 闸门回到「未执行/声明式」**：%s" % (l.get("layer"),
                                                    (l.get("gate_summary") or "")[:110]),
                "gate_missing.%s" % l.get("layer"))
    for b in backlog:
        if b["gap"]:
            add("**%s 落后 %s 个单元**（台账记 %s / 上游现有 %s）→ 跑 %s 的层引擎"
                % (b["downstream"], b["gap"], b["ledger_says"], b["upstream_now"], b["downstream"]),
                "backlog.%s" % b["downstream"])
    for r in stale:
        add("**%s 的 %s 落后 %s** → %s"
            % (r["layer"], r["file"].split("/")[-1], r["age"],
               r.get("reason") or "（无原因，异常）"),
            "stale.%s" % r["layer"])
    # ★ 2026-10-02 修：`_changed` 原先在下面第 7 节（日报）才赋值，此处先用 ⇒
    #   Python 判它是本函数局部变量 ⇒ UnboundLocalError（实测：2026-10-02 08:36 定时作业
    #   退出码 1 就是这个）。同一个值在日报里还要用，所以**只提前赋值，不复制表达式**。
    _changed = (pipe or {}).get("changed") or []
    if not (pipe or {}).get("zero_write"):
        add("**体检窗口内检测到外部写入者**（%d 个层产物变化）→ 跑写档前先确认没有别的批次在跑"
            "（本库已有先例：units.jsonl 被并发写到 12,144 行）" % len(_changed), "external_writer")

    PB = _playbook()

    # ---- 6.5 四方对账（skill 文本 ↔ 注册表 ↔ 层契约 ↔ 磁盘）
    # 为什么放日报：P1-3 把**引擎**闸门做齐了，但「skill 说的 ≠ 实际做的」没人查 ——
    # 2026-09-30 一天内撞到两次（文案合规审查只指向 5 条种子规则、kb-pipeline 正文没写 --only）。
    conf, conf_err = None, None
    try:
        rc_c, out_c, _ = sh([KBPY, "l7/scripts/skill_conformance.py", "--json"])
        conf = json.loads(out_c[out_c.find("{"):])
    except Exception as exc:                     # noqa: BLE001
        conf_err = str(exc)[:120]
    if conf and not conf.get("ok"):
        add("**四方对账没过**：红 %d（skill 文本与注册表/层契约/磁盘不一致）→ 跑 "
            "`kb/kbpy l7/scripts/skill_conformance.py` 看明细"
            % conf.get("red_total", 0), "conformance.red")

    # ---- 7. 日报
    L = []
    L.append("# 知识库 L0–L7 每日体检 · %s" % today)
    L.append("")
    L.append("- **体检时间**：%s（墙钟）" % time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now)))
    L.append("- **run_id**：`%s`（约定 = 墙钟；见 ⑥）" % run_id)
    L.append("- **健康**：**%s**" % health)
    _zw = (pipe or {}).get("zero_write")
    # `_changed` 已在第 5 节（外部写入者判定）提前赋值 —— 那里先用，此处复用同一个值。
    if _zw:
        _zw_text = "✅ 是（编排器 mtime 快照自证：4,000+ 个层产物无变化）"
    else:
        _zw_text = ("⚠️ **窗口内有层产物发生变化，但不是本次体检所致** —— 本次全程只读，"
                    "唯一的写盘是 `kb/l7/reports/` 下的日报本身，且发生在体检**之后**。"
                    "→ 判读为**存在外部写入者**（并发进程）；这本身是重要信息（见 G5 并发写入风险）。"
                    "变化文件 %d 个：%s" % (len(_changed), "、".join(_changed[:6]) or "（编排器未列清单）"))
    L.append("- **本次是否零写**：%s" % _zw_text)
    L.append("- **解释器**：`/usr/bin/python3` %s" % ("✅" if (pipe or {}).get("py_ok") else "⚠️"))
    L.append("")
    L.append("> 本报告只读：不写 `kb/l0…l6` 的任何数据与台账；产物只落 `kb/l7/reports/`。")
    L.append("> 退出码 0 = **体检跑成功**；健康与否看上面的 **健康** 一行。")
    L.append("")

    L.append("## 1. 逐层闸门")
    L.append("")
    L.append("| 层 | 闸门 | 明细 | 干跑档 | 写模式 |")
    L.append("|---|---|---|---|---|")
    for l in layers:
        L.append("| %s | %s | %s | %s | %s |" % (
            l.get("layer"), l.get("gate_state", "?"),
            (l.get("gate_summary") or "").replace("\n", " ")[:150] or "—",
            "有" if l.get("dry_run") else "**无**", l.get("write_mode", "")))
    L.append("")
    L.append("**小结**：过 %d ｜ 红 %d ｜ 未判（未执行/声明式）%d ｜ 层数 %d"
             % (len(gate_ok), len(gate_red), len(gate_skip), len(layers)))
    if conf:
        L.append("")
        L.append("**四方对账（skill 文本 ↔ 注册表 ↔ 层契约 ↔ 磁盘）**：%s ｜ 红 %d ｜ 黄（需人裁）%d"
                 " ｜ 待裁清单 kb/l7/reports/20260930-1240-对账待裁清单.md"
                 % ("过" if conf.get("ok") else "**未过**", conf.get("red_total", 0),
                    conf.get("warn_total", 0)))
    elif conf_err:
        L.append("")
        L.append("**四方对账**：跑不起来（%s）—— 这本身要修" % conf_err)
    L.append("")

    L.append("## 2. 新鲜度（各层关键产物）")
    L.append("")
    L.append("| 层 | 关键产物 | 类别 | 最后写入 | 距今 | 行数 |")
    L.append("|---|---|---|---|---|---|")
    for r in rows:
        L.append("| %s | `kb/%s` | %s | %s | %s | %s |" % (
            r["layer"], r["file"], r["kind"], fmt_ts(r["mtime"]), r["age"],
            r["lines"] if r["lines"] is not None else "—"))
    L.append("")
    L.append("> **类别**：`data` = 该层产物（判「这层跑过没有」只看 data）；"
             "`registry` = 注册表/契约 —— **被别人改一下不代表这层跑过**。"
             "下面的「落后」判定只用 `data` 行。")
    L.append("")

    # ── 2.5 逐层新鲜度判定（批次18 · 第0块 · 裁定 A 的水位口径）──────────────────
    L.append("### 2.5 逐层新鲜度（**水位口径**，不是 mtime 口径）")
    L.append("")
    L.append("| 层 | 新鲜 | change_state | 落章水位 == 现算水位 | 判据 | 回退旧口径 |")
    L.append("|---|---|---|---|---|---|")
    for j in layer_fresh:
        m = j.get("watermark_match")
        mtxt = "—" if m is None else ("**一致**" if m else "**不一致 ⇒ 判陈旧**")
        L.append("| %s | %s | %s | %s | %s | %s |" % (
            j["layer"], "✅" if j["fresh"] else "❌",
            j.get("change_state") or "—", mtxt,
            (j.get("reason") or "")[:150],
            "⚠️ 是" if j.get("fallback_used") else "否"))
    L.append("")
    L.append("> **口径（裁定 A）**：新鲜 ⟺ 该层最近一次成功 RUN 在 %s 内，**且**"
             % getattr(_lf, "STALE_AFTER_HUMAN", "24 小时") +
             "（`change_state=produced_changes` 或（`change_state=no_new_input` 且"
             "**现算**上游水位 == 落章水位））。")
    L.append("> ★ **防假绿**：`no_new_input` **不许自证** —— 水位由 `layer_freshness.judge()`"
             " 现算读盘，**上游变了就判陈旧**（哪怕 1 分钟前刚跑过）。")
    L.append("> ⚠️ 「回退旧口径 = 是」表示该层落章没有三字段（老格式）⇒ 退回 mtime 判据，"
             "**不是**判它新鲜。")
    L.append("")

    L.append("## 3. 落后量（下游 vs 上游现状）")
    L.append("")
    if backlog:
        L.append("| 下游层 | 台账记的上游规模 | 上游现有 | 差 | 判读 |")
        L.append("|---|---|---|---|---|")
        for b in backlog:
            gap = b["gap"]
            verdict = ("**落后 %d 个单元**" % gap) if gap and gap > 0 else (
                "同步" if gap == 0 else (b.get("note") or "推不出"))
            L.append("| %s | %s | %s | %s | %s |" % (
                b["downstream"], b["ledger_says"], b["upstream_now"],
                gap if gap is not None else "—", verdict))
    else:
        L.append("（无可用比对）")
    L.append("")
    L.append("> 口径：只做**台账能直读**的比对，不做推测。L0 的缺口看第 1 节的闸门明细；"
             "L1/L4/L5/L6 的台账目前没有「记的上游输入规模」字段 → 后期待补（P1-3）。")
    L.append("")

    L.append("## 4. 要人做什么")
    L.append("")
    if todos:
        for i, (t, sig) in enumerate(todos, 1):
            L.append("%d. %s" % (i, t))
            if sig:
                L.append("   %s" % _pb_line(PB, sig))
    else:
        L.append("（无）")
    L.append("")
    L.append("## 5. 已知阻断项（需人工解锁，重试无效）")
    L.append("")
    if blockers:
        L.append("| 对象 | 原因码 | 要谁做 | 复开条件 | L0 副本（★ 2026-10-03 加） |")
        L.append("|---|---|---|---|---|")
        stale_copies = []
        for b in blockers:
            # ★ 修复2：登记 ≠ 无害 —— 把「副本已经多旧」摆出来（详见 `l0_copy_age` 的注释）。
            n, _newest, age_d = l0_copy_age(KB, b.get("table") or "")
            if n is None:
                cell = "（无 L0 副本目录）"
            elif n == 0:
                cell = "0 条"
            elif age_d is None:
                cell = "%d 条 ｜ 时间读不出" % n
            else:
                cell = "%d 条 ｜ 最新 %.1f 天前" % (n, age_d)
                if age_d >= 3.0:
                    cell = "⚠️ " + cell
                    stale_copies.append((b.get("table") or "?", n, age_d))
            L.append("| %s（%s） | %s | %s | %s | %s |" % (
                b.get("table", "?"), b.get("table_id", "—"), b.get("code", "?"),
                b.get("owner_action", "?"), b.get("reopen_when", "?"), cell))
        if stale_copies:
            L.append("")
            L.append("> ⚠️ **已登记阻断项的副本正在变陈旧**（登记只说明「拉不到是有原因的」，"
                     "**不说明「旧副本还能当依据」**）——"
                     "它们仍是评审链的**溯源终点**，引用的可能是下面这些天前的快照：")
            for t, n, a in stale_copies:
                L.append("> · `%s`：%d 条，最新 **%.1f 天前**" % (t, n, a))
            L.append("> ⇒ 二选一：**在飞书侧解锁**（把守衡加为该表协作者），"
                     "或**在报告里标明这一层溯源是旧快照**。")
    else:
        L.append("（未登记：%s）" % blockers_note)
        L.append("")
        L.append("> 本轮实测到的两条（等 P1-2 正式登记）：")
        L.append("> `专家修订汇总表` tbl8AI00JZO1iZtp 与 `内容公式（仅供参考）` tblVdl0jdK9G4ld3 "
                 "—— 都是 **91403 资源级 ACL**；要人在飞书侧把「守衡」加成**可阅读协作者**。")
    L.append("")
    L.append("## 6. 编排器原始输出（存证，不转述）")
    L.append("")
    L.append("```text")
    L.append(pipe_human.strip()[-3000:] or "（无输出）")
    L.append("```")
    L.append("")

    md = "\n".join(L) + "\n"
    out_md = os.path.join(args.outdir, "%s-daily-health.md" % today)
    write_via_cp(md, os.path.join(ROOT, out_md))

    summary = {
        "run_id": run_id, "at": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(now)),
        "health": health, "zero_write": (pipe or {}).get("zero_write"),
        "gate_ok": len(gate_ok), "gate_red": len(gate_red), "gate_undecided": len(gate_skip),
        "hard": hard,
        "layers": [{"layer": l.get("layer"), "gate_state": l.get("gate_state"),
                    "gate_summary": l.get("gate_summary")} for l in layers],
        "freshness": rows, "backlog": backlog,
        # 批次18 · 第0块：逐层水位判定（判据的唯一机读出口；`freshness` 只是 mtime 表）
        "freshness_by_layer": [
            {"layer": j["layer"], "fresh": j["fresh"], "reason": j["reason"],
             "fallback_used": j["fallback_used"], "run_path": j["run_path"],
             "change_state": j["change_state"], "input_watermark": j["input_watermark"],
             "current_watermark": j.get("current_watermark"),
             "watermark_match": j.get("watermark_match")}
            for j in layer_fresh],
        "stale_layers": sorted({r["layer"] for r in stale}),
        "todos": [t for t, _s in todos],
        "todos_with_playbook": [{"text": t, "sig": s,
                                 "owner": (_pb(PB, s) or {}).get("owner") if s else None,
                                 "command": (_pb(PB, s) or {}).get("command") if s else None}
                                for t, s in todos],
        "skill_conformance": ({"ok": conf.get("ok"), "red": conf.get("red_total"),
                               "warn": conf.get("warn_total")} if conf else None),
        "external_write_suspected": (not (pipe or {}).get("zero_write")),
        "changed_files": _changed,
        "report": out_md,
    }
    write_via_cp(json.dumps(summary, ensure_ascii=False, indent=1),
                 os.path.join(ROOT, args.outdir, "daily-health-latest.json"))

    print("=" * 72)
    print("L0–L7 每日体检 · %s · run_id=%s" % (today, run_id))
    print("=" * 72)
    print("健康: %s ｜ 闸门 过%d/红%d/未判%d ｜ 零写: %s"
          % (health, len(gate_ok), len(gate_red), len(gate_skip), summary["zero_write"]))
    for b in backlog:
        if b["gap"]:
            print("落后: %s 差 %d（台账 %s / 上游 %s）"
                  % (b["downstream"], b["gap"], b["ledger_says"], b["upstream_now"]))
    print("要人做什么: %d 条" % len(todos))
    for i, (t, sig) in enumerate(todos, 1):
        print("  %d. %s" % (i, re.sub(r"\*\*|`", "", t)[:110]))
        e = _pb(PB, sig) if sig else None
        if e:
            print("     谁：%s ｜ 命令：%s" % (e.get("owner"), e.get("command")))
        elif sig:
            print("     ⚠️ 没有登记的处置办法（%s）：补 kb/l7/registry/failure-playbook.yaml" % sig)
    print("日报: %s" % out_md)
    print("机读: %s" % os.path.join(args.outdir, "daily-health-latest.json"))

    # run 记录（P3）：这一档是**无人值守**的只读体检
    if _run_record:
        try:
            _run_record(source="daily_health", trigger="定时/手动 每日体检",
                        skills=["kb-check"], commands=["kb/kbpy l7/scripts/kb_pipeline.py --check"],
                        products=[out_md, os.path.join(args.outdir, "daily-health-latest.json")],
                        verdict="过%d/红%d/未判%d ｜ 零写=%s" % (len(gate_ok), len(gate_red),
                                                              len(gate_skip), summary["zero_write"]),
                        human_involved=False, run_id=run_id)
        except Exception:                 # noqa: BLE001
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
