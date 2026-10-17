#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_prd12_acceptance.py —— PRD §12 非功能需求**逐行落点核验**。

## 为什么要有它

PRD §12 有 9 行要求，散落在全表各处。实测有两条**此前全表无落点**（Owner 2026-10-10 令执行）：

    6.（PRD §12）「P0 层响应 ≤ 1 秒」作为验收项
    7.（PRD §12）「所有审查记录保存 ≥ 1 年」作为验收项

问题不是"某一条没做"，而是**没有一把尺子能回答「§12 一共几条、哪几条有落点、落点还活着吗」**——
所以补一条漏一条，而且**落点被改坏也没人知道**。本件就是那把尺子。

## 它核什么（三问，缺一不可）

1. **有没有落点** —— 每条要求必须点名一个**判据 / 产物**（文件路径）。
2. **落点还活着吗** —— 那个文件**真的存在**（不存在 ⇒ 判红：落点被删/改名，而**没人会知道**）。
3. **读数是不是现读的** —— ★ 2026-10-12 补。

## ★ 第三问是怎么来的（一个真事故，不是洁癖）

第一版把每条实测结论**硬编码**在 `measured` 字符串里。于是出现账实不符：
`group_response` 那行写着「观测数 **0**」，而同一天它的判据
（`kb/l8/measure_group_response.py`）已经给出 **6 次观测、中位 1063 ms**。
**硬编码的结论不会随判据更新** —— 表还是那张表，事实已经变了。

⇒ 现在：凡有判据的条目，读数一律**现读**（`_probe_*`），现读不到才回落静态快照，
   并**在表里标明「静态快照」**（不静默）；判据判 FAIL 时，再看
   `kb/l7/registry/perf-known-drift.yaml` **登记没有**：
   · 已登记 ⇒ `registered_fail`（分类出来，不当新事故重报 —— 与 l5-known-drift 同一套纪律）
   · 没登记 ⇒ `unregistered_fail`（**判红**，这才是新事件）

## ★ 2026-10-17：PRD 升到 v1.3，§12 从「9 行 / 12 条落点」变「6 行 / 10 条在册」

回源：`lark-cli docs +fetch --doc PXfBdjTwFokEQixtmTscqm7knNh --profile dsh-kb --as bot`
→ **v1.3，revision 223**（旧登记 v1.2 / rev 36）。

**§12 的正文现在不在文档正文里，在内嵌飞书表格里**（`<sheet sheet-id="nvWbMk"
token="B1aUs2Vuah8YwjtwWO6cr5MFnUd">`）—— `docs +fetch` 只给占位符，
必须 `lark-cli sheets +csv-get` 按 sheet-id 另拉。本件照 v1.3 的 6 行为准：

    性能（文字≤10s / 图片≤20s / 视频≤60s / brief 按文字）
    响应（飞书群 @Agent ≤5s；P0 命中 ≤1s）
    批量（100-500 条）
    记录（≥1 年；报告链接 ≥30 天）
    权限 / 安全

**v1.3 删掉了两条**（v1.2 有、v1.3 没有），本件的处置（2026-10-17 定，见
`kb/l7/registry/prd-v1.3-alignment.yaml`）：

- `report_gen`「报告生成 ≤30s」 —— **保留落点与读数，从 §12 达标口径移出**。
  理由：它量得出来（中位 0.141 s），删判据=丢掉现成观测。
- `extensible`「可扩展」 —— 同样移出；它本来就没有落点。

⇒ 移出的两条**照旧跑、照旧打印**（标 `⬜ v1.3 已删除`），但**不再让结论判红**。
**这不是静默豁免**：它们在输出里单列一段，且 `--selftest` ⑥/⑦ 钉着这条。

## 用法

    python3 kb/l8/check_prd12_acceptance.py             # 只读核验
    python3 kb/l8/check_prd12_acceptance.py --selftest   # 自证（含反向对照与变异测试）
"""
from __future__ import annotations

import argparse
import importlib.util
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
KB = os.path.dirname(HERE)
ROOT = os.path.dirname(KB)

REGISTRY = "kb/l7/registry/perf-known-drift.yaml"
LOG_PATH = os.path.expanduser("~/Project/audit_multi_content/PMO/logs/ws_daemon.log")

#: PRD §12 逐行要求 → 落点。
#: `landing` = 认领它的判据/产物（**相对工作区根**）；
#: `measured` = **静态快照，只在现读不到时展示**（会过期，不许当现状引用）；
#: `live` = 现读探针名（见 `_probe_*`），有它就以现读为准；
#: `v13` = 这条在 **PRD v1.3 §12** 里的位置：`in` = 仍在册（`row` 就是 v1.3 的那一行）；
#:         `removed` = **v1.3 已删除**（照旧跑、照旧打印，但不再让结论判红）。
#: ⚠️ `row` 一律用 **v1.3 的 6 行原词**（性能/响应/批量/记录/权限/安全），
#:    不许再写 v1.2 的「并发」「可用性」「P0 层响应」—— 那两个名字 v1.3 已经没有了。
V13_ROWS = ["性能", "响应", "批量", "记录", "权限", "安全"]
V13_SHEET = "nvWbMk"                    # §12 正文所在的内嵌表格 sheet
V13_DOCX = "PXfBdjTwFokEQixtmTscqm7knNh"
V13_REVISION = 223

REQ = [
    {"id": "perf_text", "row": "性能", "v13": "in",
     "req": "单条文字 ≤ 10 秒（brief 按文字处理）",
     "landing": "kb/l8/measure_verdict_latency.py", "live": "verdict_latency",
     "measured": "中位 5.145 s（n=3，**证据层地板**，不含 agent/LLM）", "verdict": "pass"},
    {"id": "perf_image", "row": "性能", "v13": "in", "req": "图片 ≤ 20 秒",
     "landing": "kb/l8/measure_verdict_latency.py", "live": "verdict_latency",
     "measured": "中位 4.132 s（**OCR 文本代输入·近似**）", "verdict": "approximate"},
    {"id": "perf_video", "row": "性能", "v13": "in", "req": "视频 ≤ 60 秒",
     "landing": "kb/l8/measure_verdict_latency.py", "live": "verdict_latency",
     "measured": "中位 5.786 s（**ASR 文本代输入·近似**）", "verdict": "approximate"},
    {"id": "concurrency", "row": "批量", "v13": "in", "req": "支持 100-500 条批量扫描",
     "landing": "kb/l8/batch_scan.py",
     "measured": "入口已建：真读结论去向表 → 一批一次层前置 → 有界并发逐条出结论。"
                 "实测 **1/1 成功**（层前置四层全绿、四道审计红 0，用时 7.8s）。"
                 "★ 并发**上限**尚未压测到 100-500 条（见该脚本边界）",
     "verdict": "landing_partial"},
    {"id": "group_response", "row": "响应", "v13": "in", "req": "飞书群 @Agent ≤ 5 秒",
     "landing": "kb/l8/measure_group_response.py", "live": "group_response",
     "measured": "埋点已就位，**观测数 0**（待一次真实送审）", "verdict": "no_reading"},
    {"id": "p0_response", "row": "响应", "v13": "in", "req": "P0 命中 ≤ 1 秒（关键词/正则匹配）",
     "landing": "kb/l8/p0_regression.py", "live": "l5_bench",
     "measured": "P0 判定中位 **0.15 s**；11 条红线回归 **126/126**", "verdict": "pass"},
    {"id": "report_gen", "row": "报告生成", "v13": "removed",
     "req": "问题 ≥ 3 时，报告链接生成 ≤ 30 秒",
     "landing": "kb/l7/reports/perf-latest.json", "live": "perf_ledger",
     "measured": "**0.164 s**（★ 该数原无出处，2026-10-12 已补真量法与 provenance）",
     "verdict": "pass"},
    {"id": "retention_1y", "row": "记录", "v13": "in", "req": "审查记录保存 ≥ 1 年",
     "landing": "kb/l8/check_record_retention.py", "measured": "见该判据（保留承诺 + 现账）",
     "verdict": "see_landing"},
    {"id": "link_30d", "row": "记录", "v13": "in", "req": "报告链接有效期 ≥ 30 天",
     "landing": "kb/l8/check_report_link_validity.py",
     "measured": "链接可打开 **6/6**（原 6/6 `closed`）；「≥30 天」平台无字段 ⇒ `not_measurable`",
     "verdict": "pass_with_caveat"},
    {"id": "rbac", "row": "权限", "v13": "in", "req": "按角色控制查看、复核、sign-off",
     "landing": "kb/l7/registry/permission-matrix.yaml", "measured": "9 个角色位；**执行面在飞书侧（人的动作）**",
     "verdict": "declared"},
    {"id": "security", "row": "安全", "v13": "in",
     "req": "默认权限控制；导出、报告分享、模型训练样本按需脱敏",
     "landing": "kb/l7/registry/source-readonly.yaml", "measured": "源只读闸门 C1–C8 全绿",
     "verdict": "pass"},
    {"id": "extensible", "row": "可扩展", "v13": "removed",
     "req": "支持后续接入图片、视频深度识别、平台界面",
     "landing": "", "measured": "**无落点**（前瞻性要求，无可核产物）", "verdict": "no_landing"},
]


def v13_gap(rows):
    """v1.3 §12 的 6 行里，哪几行**没有任何在册落点**覆盖。⇒ [行名]。

    ★ 为什么要有它：v1.3 删了 2 条、并在册条目重新归到 6 行 —— 万一哪天有人把
      某行的条目全标成 `removed`（或漏标一行），**覆盖率会静默掉一块**，
      而总数/红绿都看不出来。这条把它变成可判定的缺口。
    """
    covered = {r["row"] for r in rows if r.get("v13") != "removed"}
    return [x for x in V13_ROWS if x not in covered]


# ══════════════════════════════════════════════════════════════════
# 登记处（**不是豁免**：只说"这条已知、成因已定、处置派给人了"）
# ══════════════════════════════════════════════════════════════════

def load_registry(root=ROOT):
    """⇒ ({id: 记录}, 状态)。读不到/读坏了 ⇒ 空表（于是 FAIL 会落成 `unregistered_fail`）。"""
    p = os.path.join(root, REGISTRY)
    if not os.path.exists(p):
        return {}, "missing"
    try:
        import yaml
        d = yaml.safe_load(io.open(p, encoding="utf-8").read()) or {}
        items = {r["id"]: r for r in (d.get("registered") or []) if r.get("id")}
        return items, "ok"
    except Exception as e:                                     # noqa: BLE001
        return {}, "unreadable: %r" % (e,)


# ══════════════════════════════════════════════════════════════════
# 现读探针（**只读**；现读不到 ⇒ 返回 None，由调用方回落静态快照并标出来）
# ══════════════════════════════════════════════════════════════════

def _load_mod(name):
    """按**文件路径**加载同目录判据（不污染 sys.path、不重名踩踏）。"""
    path = os.path.join(HERE, name + ".py")
    if not os.path.exists(path):
        return None
    spec = importlib.util.spec_from_file_location("kbprobe_" + name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _probe_verdict_latency():
    """§12「性能」三档 —— Owner 2026-10-12 裁定口径（守衡回复时间）。⇒ {REQ id: {...}}"""
    mod = _load_mod("measure_verdict_latency")
    if not mod or not os.path.exists(LOG_PATH):
        return None
    text = io.open(LOG_PATH, encoding="utf-8", errors="ignore").read()
    units, _c = mod.parse(text)
    s = mod.summarize(units)
    names = {"text": "文字", "image": "图片", "video": "视频"}
    out = {}
    for k in ("text", "image", "video"):
        r = s[k]
        if r["verdict"] == "no_reading":
            out["perf_" + k] = {"measured": "%s：**无观测**（n=0）" % names[k],
                                "verdict": "no_reading"}
        else:
            out["perf_" + k] = {
                "measured": "%s n=%d ｜ min %.1f s ｜ **中位 %.1f s** ｜ max %.1f s ｜ %s"
                            % (names[k], r["n"], r["min_ms"] / 1000.0, r["median_ms"] / 1000.0,
                               r["max_ms"] / 1000.0, r["why"]),
                "verdict": r["verdict"]}
    return out


def _probe_group_response():
    """§12「可用性 ≤5s」—— ingress → **回执卡**（另一条指标，别与性能档混）。"""
    mod = _load_mod("measure_group_response")
    if not mod or not os.path.exists(LOG_PATH):
        return None
    text = io.open(LOG_PATH, encoding="utf-8", errors="ignore").read()
    rows, _bad = mod.parse(text)
    s = mod.summarize(rows)
    if s["verdict"] == "no_reading":
        return {"group_response": {"measured": "**观测数 0**（埋点已就位，等真实送审）",
                                   "verdict": "no_reading"}}
    return {"group_response": {
        "measured": "观测 **%d** 次 ｜ min %d ms ｜ **中位 %d ms** ｜ max %d ms（门槛 %d ms）"
                    % (s["n"], s["min"], s["median"], s["max"], s["limit_ms"]),
        "verdict": s["verdict"]}}


def _probe_l5_bench():
    """§12「P0 层响应 ≤1s」—— 读 L5 bench 现值（真送审形态 vs 1MB 余量用例分开说）。"""
    p = os.path.join(KB, "l5", "benchmark.json")
    if not os.path.exists(p):
        return None
    d = json.load(io.open(p, encoding="utf-8"))
    cases = {c["case"]: c for c in (d.get("cases") or [])}
    pc = max(1, int(d.get("pattern_count") or 1))
    crit = d.get("criterion") or {}
    small = [cases[k]["elapsed_ms"]["median"] for k in
             (crit.get("real_cases") or
              ["single_primary_text", "single_with_hit", "batch_ad_copy"]) if k in cases]
    big = cases.get("large_doc_1mb", {}).get("elapsed_ms", {}).get("median")
    s = ("真实送审形态 %s ms（<1s 硬门槛 ✅）" % " / ".join("%.1f" % x for x in small)) if small else "真实形态读数缺"
    if big is not None:
        s += "；1MB 余量用例 %.0f ms ÷ %d 模式 = **%.1f ms/模式**（门槛 %s ms）" % (
            big, pc, big / pc, crit.get("per_pattern_limit_ms", "?"))
    return {"p0_response": {
        "measured": s + " ⇒ bench verdict=**%s**（分级口径：%s；复算闸门 kb/l8/check_perf_bench.py）"
                        % (d.get("verdict"), crit.get("ruling") or "分级口径"),
        "verdict": "fail" if d.get("verdict") == "FAIL" else "pass"}}


def _probe_perf_ledger():
    """§12「报告生成 ≤30s」—— 现读台账 `perf-latest.json`（该数此前**无出处**，见 provenance）。"""
    p = os.path.join(KB, "l7", "reports", "perf-latest.json")
    if not os.path.exists(p):
        return None
    d = json.load(io.open(p, encoding="utf-8"))
    r = ((d.get("results") or {}).get("p0_with_report") or {})
    w = r.get("wall") or {}
    if not w:
        return None
    prov = (r.get("provenance") or {}).get("measured_by") or "**无出处**"
    return {"report_gen": {
        "measured": "中位 **%.3f s**（n=%s，门槛 %s s；出处 %s）—— 量的是「同一夹具 + `--report-out` 写全量报告」的墙钟，"
                    "**不含**云文档创建与飞书落表（那两段属发布）"
                    % (w.get("median_s") or 0, w.get("n"), r.get("threshold_s"), prov),
        "verdict": r.get("verdict") or "pass"}}


PROBES = {"verdict_latency": _probe_verdict_latency,
          "group_response": _probe_group_response,
          "l5_bench": _probe_l5_bench,
          "perf_ledger": _probe_perf_ledger}


def live_readings():
    """跑一遍探针 ⇒ {REQ id: {"measured", "verdict"}}。**探针炸了不许静默**：记进 errors。"""
    cache, errors = {}, []
    for name, fn in PROBES.items():
        try:
            cache[name] = fn() or {}
        except Exception as e:                                 # noqa: BLE001
            cache[name] = {}
            errors.append("%s：%r" % (name, e))
    out = {}
    for r in REQ:
        name = r.get("live")
        if not name:
            continue
        got = cache.get(name, {}).get(r["id"])
        if got:
            out[r["id"]] = got
    return out, errors


def check(root=ROOT, live=None, registry=None):
    if live is None:
        live, _err = live_readings()
    if registry is None:
        registry, _rs = load_registry(root)
    rows = []
    for r in REQ:
        p = os.path.join(root, r["landing"]) if r["landing"] else ""
        alive = bool(p) and os.path.exists(p)
        lv = (live or {}).get(r["id"])
        # ★ 只有「有判据却现读不到」才标静态快照 —— 没有判据的条目（权限/安全/记录）本来就没探针
        measured = (lv or {}).get("measured") or (
            r["measured"] + ("　⚠️（**静态快照**：判据现读不到）" if r.get("live") else ""))
        verdict = (lv or {}).get("verdict") or r["verdict"]
        # ★ 大小写归一：判据自己用的是 "FAIL"（见 measure_verdict_latency.summarize）
        vlow = str(verdict).lower()
        if r.get("v13") == "removed":
            # ★ v1.3 已删除：落点丢了照样报（`landing_gone` 比「已删除」更该让人看见），
            #   否则标「已删除」但**不再参与**达标口径（既不判红、也不进分母）。
            state = "landing_gone" if (r["landing"] and not alive) else "prd13_removed"
        elif r["verdict"] == "no_landing" or not r["landing"]:
            state = "no_landing"
        elif not alive:
            state = "landing_gone"          # ★ 最坏：声明有落点，落点没了且没人知道
        elif vlow == "fail":
            state = "registered_fail" if r["id"] in registry else "unregistered_fail"
        else:
            state = verdict
        rows.append({**r, "measured_text": measured, "live": bool(lv),
                     "file_exists": alive, "state": state})
    return rows


ICON = {"pass": "✅", "pass_with_caveat": "🟡", "declared": "🟡", "see_landing": "🟡",
        "landing_partial": "🟡", "approximate": "🟡", "no_reading": "⛔",
        "registered_fail": "⚠️", "unregistered_fail": "❌",
        "no_landing": "❌", "landing_gone": "❌", "prd13_removed": "⬜"}
ORDER = {"landing_gone": 0, "no_landing": 1, "unregistered_fail": 2, "no_reading": 3,
         "registered_fail": 4, "landing_partial": 5, "approximate": 5, "declared": 6,
         "see_landing": 7, "pass_with_caveat": 8, "pass": 9, "prd13_removed": 10}


def run():
    reg, reg_state = load_registry()
    live, errors = live_readings()
    rows = check(live=live, registry=reg)
    inscope = [r for r in rows if r.get("v13") != "removed"]
    removed = [r for r in rows if r.get("v13") == "removed"]
    gap = v13_gap(rows)
    print("PRD §12 非功能需求 —— 逐行落点核验")
    print("★ 口径：PRD **v1.3 / revision %d**（docx `%s`；§12 正文在内嵌表格 sheet `%s`，"
          "`docs +fetch` 只给占位符，须 `sheets +csv-get` 另拉）"
          % (V13_REVISION, V13_DOCX, V13_SHEET))
    print("★ 三问：① 有没有落点 ② 落点文件还在不在 ③ **读数是不是现读的**")
    print("★ 登记处：%s（%s，%d 条）—— 判 FAIL 且**已登记** ⇒ 分类出来；**没登记** ⇒ 判红"
          % (REGISTRY, reg_state, len(reg)))
    if errors:
        print("⚠️ 探针报错（已回落静态快照，**那些结论可能是过期的**）：%s" % "；".join(errors))
    print()
    for r in sorted(inscope, key=lambda x: ORDER.get(x["state"], 9)):
        print("  %s [%-7s] %-15s %s" % (ICON.get(r["state"], "?"), r["row"], r["id"], r["req"]))
        print("        落点：%s" % (r["landing"] or "**（无）**"))
        print("        实测：%s%s" % (r["measured_text"], "" if r["live"] else ""))
        if r["state"] == "registered_fail":
            print("        ⇒ **已登记**：%s（status=%s）"
                  % (REGISTRY, (reg.get(r["id"]) or {}).get("status", "?")))
    n_no = [r for r in inscope if r["state"] == "no_landing"]
    n_gone = [r for r in inscope if r["state"] == "landing_gone"]
    n_unreg = [r for r in inscope if r["state"] == "unregistered_fail"]
    n_reg = [r for r in inscope if r["state"] == "registered_fail"]
    n_pending = [r for r in inscope if r["state"] in ("no_reading", "approximate", "declared",
                                                      "see_landing", "landing_partial")]
    print("\n共 %d 条 ｜ **v1.3 在册 %d 条**（覆盖 6 行：%s）｜ ⬜ v1.3 已删除 %d 条（照旧跑，不进结论）"
          % (len(rows), len(inscope), "、".join(V13_ROWS), len(removed)))
    print("在册口径：✅ 达标 %d ｜ 🟡 有保留 %d ｜ ⚠️ **已登记未达标 %d** ｜ "
          "❌ **未登记 FAIL %d** ｜ ❌ 无落点 %d ｜ ❌ 落点丢失 %d"
          % (sum(1 for r in inscope if r["state"] in ("pass", "pass_with_caveat")),
             len(n_pending), len(n_reg), len(n_unreg), len(n_no), len(n_gone)))
    if gap:
        print("\n❌ **v1.3 的 §12 有 %d 行没有任何在册落点**：%s —— 覆盖率掉了一块"
              % (len(gap), "、".join(gap)))
    for label, group in (("**无落点的（真缺口）**", n_no),
                         ("**未登记的 FAIL（新事件，判红）**", n_unreg)):
        if group:
            print("\n%s：" % label)
            for r in group:
                print("   · %s —— %s" % (r["req"], r["measured_text"]))
    if removed:
        print("\n⬜ **v1.3 已删除、本地仍保留的 %d 条**（不判红，但也不许当没看见）：" % len(removed))
        for r in removed:
            print("   · [%s] %s —— 落点 %s ｜ 现读数：%s"
                  % (r["row"], r["req"], r["landing"] or "**（无）**", r["measured_text"]))
        print("   ⇒ 处置登记：kb/l7/registry/prd-v1.3-alignment.yaml（D4）")
    ok = not n_no and not n_gone and not n_unreg and not gap
    if ok:
        print("\n结论：✅ §12（v1.3 六行）每行都有活着的落点，且没有未登记的 FAIL")
    else:
        print("\n结论：❌ **§12 有 %d 行覆盖缺口、%d 条无落点、%d 条落点丢失、%d 条未登记 FAIL** —— 见上"
              % (len(gap), len(n_no), len(n_gone), len(n_unreg)))
    return 0 if ok else 3


def selftest():
    global REQ                                              # noqa: PLW0603
    res = []

    def ck(n, c, ex=""):
        res.append((n, bool(c), ex))

    live, _e = live_readings()
    reg, reg_state = load_registry()
    rows = check(live=live, registry=reg)
    inscope = [r for r in rows if r.get("v13") != "removed"]
    removed = [r for r in rows if r.get("v13") == "removed"]
    ck("① 要求条数 == v1.2 铺开的 12 条落点（v1.3 后仍是 12 条，其中 2 条已移出在册）",
       len(rows) == 12, "n=%d" % len(rows))
    ck("①b 每条都有 row / req / verdict / v13（没有半条）",
       all(r.get("row") and r.get("req") and r.get("verdict") and r.get("v13")
           for r in rows), "")
    # ★ 现读真的生效了：至少 4 条走的是现读（三档 + 响应），不是硬编码
    n_live = len([r for r in rows if r["live"]])
    ck("①c 读数**现读**生效（≥4 条走探针，不是硬编码）", n_live >= 4, "live=%d" % n_live)
    ck("①c2 登记处读到了且非空", reg_state == "ok" and len(reg) >= 1, "%s n=%d" % (reg_state, len(reg)))
    # ★ 2026-10-17 v1.3：须与 §12 的 6 行**逐行对得上**，且两条已删除的**不许悄悄消失**
    ck("①d v1.3 在册 10 条 / 已删除 2 条（report_gen、extensible）",
       len(inscope) == 10 and len(removed) == 2
       and sorted(r["id"] for r in removed) == ["extensible", "report_gen"],
       "在册=%d 已删=%d" % (len(inscope), len(removed)))
    ck("①e v1.3 §12 的 6 行**每行都有在册落点**（覆盖率没有缺口）",
       v13_gap(rows) == [], "缺口=%s" % (v13_gap(rows) or "无"))
    ck("①f 已删除的两条**仍在输出里**（标记为 prd13_removed，不是静默丢掉）",
       all(r["state"] == "prd13_removed" for r in removed)
       and len(removed) == 2, "states=%s" % [r["state"] for r in removed])

    # ★ 反向对照：**声明了落点但文件不存在 ⇒ 必须判 landing_gone**（真造一条）
    import tempfile
    tmp = tempfile.mkdtemp(prefix="prd12-")
    # 取两条**真落点**逐个造出来（造哪条，哪条就不许判 gone —— 否则判据可能是恒假）
    made = [r for r in REQ if r["landing"]][:2]
    for r in made:
        fp = os.path.join(tmp, r["landing"])
        os.makedirs(os.path.dirname(fp), exist_ok=True)
        io.open(fp, "w").write("x")
    rows2 = check(root=tmp, live=live, registry=reg)
    gone = [r for r in rows2 if r["state"] == "landing_gone"]
    ck("② 反向对照：声明有落点、文件不存在 ⇒ 判 landing_gone（不是静默通过）",
       len(gone) >= 3, "gone=%d" % len(gone))
    ck("②b 反向对照：**造了的那两条**落点不算 gone（判据不是恒假）",
       not any(r["id"] in [m["id"] for m in made] for r in gone),
       "made=%s" % [m["id"] for m in made])

    # ★ 反向对照：**登记处被喂空 ⇒ 已登记的那些 FAIL 必须精确变成未登记 FAIL**（判红）
    #   ⚠️ 2026-10-17 修口径（**这不是我改出来的，是它自己烂掉的**）：原断言写
    #   `len(unreg) == n_fail_live`，隐含假设「所有 FAIL 都已被登记」。一旦有**本就未登记**
    #   的 FAIL 出现（实测 `group_response` 在真拿到 57 次观测后由 no_reading 变 FAIL），
    #   喂空后 unreg = 已登记 4 + 本就未登记 1 = 5，而 n_fail_live 仍是 4 ⇒ **恒假**。
    #   ⇒ 正确口径：喂空后 unreg 必须**等于「已登记 + 本就未登记」之和**，且 regd 必须清零。
    rows3 = check(live=live, registry={})
    unreg = [r for r in rows3 if r["state"] == "unregistered_fail"]
    regd = [r for r in rows3 if r["state"] == "registered_fail"]
    n_fail_live = len([r for r in rows if r["state"] == "registered_fail"])
    n_unreg_had = len([r for r in rows if r["state"] == "unregistered_fail"])
    ck("③ 反向对照：登记处喂空 ⇒ 已登记 FAIL 精确转成 unregistered_fail（判据不是恒绿）",
       n_fail_live >= 3 and not regd and len(unreg) == n_fail_live + n_unreg_had,
       "reg=%d unreg=%d（原已登记 %d ＋ 原本就未登记 %d，**前者 ≥3 才不是空跑**）"
       % (len(regd), len(unreg), n_fail_live, n_unreg_had))

    # ★ 反向对照：登记处**文件不存在** ⇒ 状态必须是 missing（不许静默当"没问题"）
    _r4, rs4 = load_registry(root=tmp)
    ck("④ 反向对照：登记处缺失 ⇒ 状态 missing（不许静默）", rs4 == "missing", rs4)

    # ★ 变异测试：**先真造一条在册条目「无落点」，再给它补真落点 ⇒ 必须精确归零**
    #   ⚠️ 2026-10-17 重造：v1.3 把唯一那条 `no_landing`（extensible）移出了在册范围，
    #   旧版「给 no_landing 塞落点」于是变成**恒绿的空跑**（原样跑也一条 no_landing 都没有）。
    #   ⇒ 改成**从在册条目里造**：先把 `security` 的落点抽空、判 no_landing（必须数出 1），
    #   再补上一个真文件（必须归零）。两边都成立，才说明这条判据真在读落地。
    _orig = REQ
    fake = [dict(r) for r in REQ]
    tgt = next(r for r in fake if r["id"] == "security")
    tgt["landing"] = ""
    tgt["verdict"] = "no_landing"
    REQ = fake
    r5 = check(live=live, registry=reg)
    n5 = len([x for x in r5 if x["state"] == "no_landing"])
    ck("⑤ 变异测试：从在册条目真造一条「无落点」⇒ 无落点数**精确 = 1**（不是恒绿）",
       n5 == 1, "no_landing=%d" % n5)
    tgt["landing"] = "kb/l7/registry/source-readonly.yaml"   # 真存在的文件
    tgt["verdict"] = "pass"
    r5b = check(live=live, registry=reg)
    ck("⑤b 补上真落点 ⇒ 无落点数**精确归零**",
       not [x for x in r5b if x["state"] == "no_landing"], "")
    REQ = _orig
    r6 = check(live=live, registry=reg)
    ck("⑥ 还原后无落点数回到真值", len([x for x in r6 if x["state"] == "no_landing"]) ==
       len([x for x in rows if x["state"] == "no_landing"]), "")

    # ★ 反向对照：**把「响应」那一行的条目全标成 v1.3 已删除 ⇒ 覆盖率缺口必须精确报「响应」**
    #   （证明 `v13_gap()` 不是恒空：真有行没人覆盖时，它能点名）
    fake2 = [dict(r) for r in REQ]
    for r in fake2:
        if r["row"] == "响应":
            r["v13"] = "removed"
    ck("⑧ 反向对照：某行条目全标记已删除 ⇒ v13_gap 精确点名该行（判据不是恒空）",
       v13_gap(fake2) == ["响应"], "gap=%s" % v13_gap(fake2))
    ck("⑧b 而真值的覆盖缺口是空（两条一起看才说明它不是恒真也不是恒假）",
       v13_gap(rows) == [], "")

    # ★ 跨文件一致：**对齐登记件的六行口径必须与这里的 V13_ROWS 一致**
    #   （谁改了一边忘了另一边 ⇒ 精确变红；这是"两份事实写两处"的唯一解药）
    align_p = os.path.join(ROOT, "kb/l7/registry/prd-v1.3-alignment.yaml")
    if not os.path.exists(align_p):
        ck("⑨ 对齐登记件在位（kb/l7/registry/prd-v1.3-alignment.yaml）", False, "缺件")
    else:
        try:
            import yaml
            ad = yaml.safe_load(io.open(align_p, encoding="utf-8").read()) or {}
            rows_a = ((ad.get("section_12") or {}).get("rows_v13") or [])
            ck("⑨ 登记件的 §12 六行口径 == 本件 V13_ROWS（防止两处各写各的）",
               rows_a == V13_ROWS, "登记件=%s" % (rows_a or "读不到"))
        except Exception as e:                                 # noqa: BLE001
            ck("⑨ 登记件可解析", False, "%r" % (e,))

    # ★ 变异测试：**把现读关掉**（喂空 live）⇒ 那些行必须回落并**标出「静态快照」**
    r7 = check(live={}, registry=reg)
    snap = [x for x in r7 if "静态快照" in x["measured_text"]]
    ck("⑦ 变异测试：现读关掉 ⇒ 回落静态快照并**标明**（不许冒充现读）",
       len(snap) >= 4, "snap=%d" % len(snap))
    import shutil
    shutil.rmtree(tmp, ignore_errors=True)
    print("check_prd12_acceptance --selftest")
    for n, c, ex in res:
        print("  %s %s%s" % ("✅" if c else "❌", n, ("　｜ " + ex) if ex else ""))
    bad_n = sum(1 for _, c, _e in res if not c)
    print("结果：%d/%d%s" % (len(res) - bad_n, len(res), "" if not bad_n else "  ← 有失败"))
    return 1 if bad_n else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    sys.exit(selftest() if a.selftest else run())
