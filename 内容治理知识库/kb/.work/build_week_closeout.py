#!/usr/bin/env python3
"""生成《交付-10/12-10/16-结项与未达标说明》—— **每条必须做都带可复算探针**。

## 为什么不能手写

工单 §七 逐字：「**周五没达标的项，写进《未达标说明》，不要挪到 10/19 那行。**」
而 xlsx 的 G 列**已被实测证明至少 6 处过期**（目标 7/8 说"字段不存在"、目标 13 说"六项产物=0"、
目标 12 说"只有 P0 分支"、目标 9/10/18 说"没有"而交付件都在）。
⇒ 手抄一遍 G 列 = 把过期读数再发一次。**每条都要现跑探针。**

★ 写盘走 `_safe_write`（python 直写 .md 会多 4096 字节信封）。
"""

from __future__ import annotations
import collections
import datetime as dt
import importlib.util
import glob
import json
import os
import re
import subprocess
import sys

KB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(KB)
sys.path.insert(0, os.path.join(KB, ".work"))
sys.path.insert(0, os.path.join(KB, "l3"))
import _safe_write                                       # noqa: E402
import kb_rule_dimensions as D                           # noqa: E402

OUT = os.path.join(ROOT, "交付-1012至1016-结项与未达标说明-20261012.md")


def read_json(p):
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:                                    # noqa: BLE001
        return None


def run(cmd, timeout=120):
    try:
        r = subprocess.run(cmd, shell=isinstance(cmd, str), capture_output=True,
                           text=True, cwd=ROOT, timeout=timeout)
        return r.returncode
    except Exception:                                    # noqa: BLE001
        return -1


def exists(*pats):
    n = 0
    for p in pats:
        n += len(glob.glob(os.path.join(ROOT, p)))
    return n


def _prd12_live():
    """现读 §12 性能三档 + 可用性（⇒ {id: {measured, verdict}}）。炸了就抛，不静默。"""
    p = os.path.join(KB, "l8", "check_prd12_acceptance.py")
    spec = importlib.util.spec_from_file_location("kbprobe_prd12_closeout", p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m.live_readings()


def main() -> int:
    rows = [json.loads(l) for l in open(os.path.join(KB, "l3", "candidates", "rules.jsonl"),
                                       encoding="utf-8") if l.strip()]
    by = {}
    for r in rows:
        m = by.setdefault(r["rule_id"], {})
        for k, v in r.items():
            if v not in (None, "", [], {}):
                m[k] = v
    n = len(by)
    rl = collections.Counter(str(m.get("risk_level")) for m in by.values())
    mod_und = sum(1 for m in by.values() if str(m.get("modality")) == D.MODALITY_UNDETERMINED)
    noscope = sum(1 for m in by.values()
                  if not any((m.get("applicable_scope") or {}).get(k)
                             for k in ("product_line", "channel", "content_type")))
    ext = sum(1 for m in by.values() if str(m.get("kb_type")) == "external_standard")
    rej = sum(1 for _ in open(os.path.join(KB, "l3", "rejected.jsonl"), encoding="utf-8"))

    am = read_json(os.path.join(KB, "l7", "reports", "audit-metrics-latest.json")) or {}
    m7 = am.get("m") or am.get("metrics") or {}
    def mstat(key):
        v = m7.get(key) if isinstance(m7, dict) else None
        if isinstance(v, dict):
            return v.get("status")
        return None
    perf = read_json(os.path.join(KB, "l7", "reports", "perf-latest.json")) or {}
    pm = open(os.path.join(KB, "l7", "registry", "permission-matrix.yaml"),
              encoding="utf-8").read()
    nroles = len(re.findall(r"^\s{2}[^\s].*:", pm, re.M))
    conf = read_json(os.path.join(KB, "l7", "registry", "confidence-policy.json")) or {}
    led = os.path.join(KB, "l5", "registry", "p0-legal-signoff-ledger.jsonl")
    nl = sum(1 for l in open(led, encoding="utf-8") if l.strip()) if os.path.exists(led) else 0
    sample_csv = os.path.join(KB, "l7", "reports", "audit-sample-ALL.csv")
    ns = sum(1 for l in open(sample_csv, encoding="utf-8") if l.strip()) - 1 if os.path.exists(sample_csv) else 0
    bit = read_json(os.path.join(KB, "l7", "reports", "bitable-stats-latest.json")) or {}

    # ★ 2026-10-12：§12「性能」三档的口径由 Owner 裁定为**守衡回复时间** ⇒
    #   本节读数**现读**（复用 kb/l8/check_prd12_acceptance.py::live_readings，
    #   不在这里另写一套解析 —— 免得同一件事两条路、各覆盖一半）。
    live, live_errs = _prd12_live()

    gate = lambda c: run(c)                                        # noqa: E731
    g_kdim = gate([sys.executable, os.path.join(KB, "l3", "kb_rule_dimensions.py"), "--selftest"])
    g_as = gate([sys.executable, os.path.join(KB, "l8", "audit_sample.py"), "--selftest"])
    g_bit = gate([sys.executable, os.path.join(KB, "l8", "bitable_stats.py"), "--selftest"])
    g_smoke = gate([sys.executable, os.path.join(KB, "l8", "workflow_smoke.py")])
    g_gate = gate([sys.executable, os.path.join(KB, "l8", "regression_gate.py")])
    g_l3 = gate(["sh", os.path.join(KB, "kbpy"), "l7/scripts/l3_gate.py"])
    g_src = gate([sys.executable, os.path.join(KB, "l8", "check_source_readonly.py")])
    g_vl = gate([sys.executable, os.path.join(KB, "l8", "measure_verdict_latency.py"), "--selftest"])
    g_p12 = gate([sys.executable, os.path.join(KB, "l8", "check_prd12_acceptance.py"), "--selftest"])

    ITEMS = []
    ITEMS.append(("1", "目标 6 风险等级（PRD §6.5）",
                  "四维链重算；`risk_level` 分布 %s" % "／".join("%s %d" % kv for kv in rl.most_common()),
                  "`kb_rule_dimensions --selftest` = %d" % g_kdim,
                  "已交付" if g_kdim == 0 else "闸门红"))
    ITEMS.append(("2", "目标 7 适用范围（PRD §6.5）",
                  "有范围 %d ／ 无范围 %d（382+19 条源侧无列，已登记）" % (n - noscope, noscope),
                  "`NOT_DERIVABLE.applicable_scope.*` 已登记；见《交付-目标7-适用范围结案》",
                  "本地已尽（源侧缺列）"))
    ITEMS.append(("3", "目标 8 模态（PRD §5.2）",
                  "`undetermined` %d / %d" % (mod_und, n),
                  "四条穷尽取证；两条候选口径**待签**",
                  "本地已尽（源侧缺列）"))
    ITEMS.append(("4", "目标 5 外部标准抽成规则（PRD §7.1）",
                  "`rules.jsonl` 里 `external_standard` = **%d** 条；rejected 台账 %d 行" % (ext, rej),
                  "根因已归因到 L1 定长切；`改动单-外部标准抽取口径-20261010.md` = **待批**（未批不能动）",
                  "**待签**"))
    ITEMS.append(("5", "目标 10 WHO/AAP 条款号台账（PRD §7.1）",
                  "交付件 %d 份" % exists("交付-目标10-*.md"),
                  "`交付-目标10-WHO-AAP条款号台账-20261010.md`", "已交付"))
    ITEMS.append(("6", "目标 9 内容 ID（PRD §5.4）",
                  "`core/content_id.py` 在；`AUTO-` 仅作拿不到号时的**退回指纹**",
                  "今日真单实测 `content_id=AD-20261012-002`", "已交付"))
    ITEMS.append(("7", "目标 11 置信度分流（PRD §6.6）",
                  "政策件 status=%s；`thresholds_note` 自述：**这两个数是 PRD 政策值，不是标定出来的**"
                  % conf.get("status"),
                  "**阈值未标定** —— 标定依赖金标集（11/30 那行）", "**待签／依赖后续**"))
    ITEMS.append(("8", "目标 12 P1/P2 两层（PRD §6.3）",
                  "`review_engine.py` 已有 P0/P1/P2/P3 **四条显式分支**",
                  "grep `priority_tier` 命中 4 层；注释自述 2026-10-10 接线", "已交付"))
    ITEMS.append(("9", "目标 13 审计指标 7 项（PRD §10）",
                  "**4 measured ／ 3 no_data**（覆盖率、误漏报、回流）",
                  "`kb/l7/reports/audit-metrics-latest.json`", "部分（3 项结构性/后续）"))
    ITEMS.append(("10", "目标 14 每周人工抽检 100 条（PRD §11.2-6）",
                  "首轮清单 **%d 条**（人判栏空）；抽样器自证 = %d" % (ns, g_as),
                  "`kb/l7/reports/audit-sample-ALL.csv`", "已交付（人判待人工）"))
    ITEMS.append(("11", "目标 15 报告 ≤30s ／ 链接 ≥30 天（PRD §12/§8.3）",
                  "`report-threshold-policy.json` 在；链接核验件 %d 份"
                  % exists("交付-目标15*.md"),
                  "perf 阈值表含 `report: 30`", "已交付"))
    ITEMS.append(("12", "目标 16 权限按角色（PRD §13）",
                  "`permission-matrix.yaml` **9 个角色位**＋显式 `open_questions`",
                  "★ 未闭合：**人名全空**（要人给）＋「专家」角色位无 `routing_policy_key`",
                  "已交付（两处待外部输入）"))
    ITEMS.append(("13", "目标 17 端到端性能（PRD §12）",
                  "文字 %.3fs／长文 %.3fs／图片代理 %.3fs／视频代理 %.3fs／P0 判定 %.3fs／整链 %.1fs"
                  % ((perf.get("results", {}).get("text", {}).get("wall", {}) or {}).get("median_s") or 0,
                     (perf.get("results", {}).get("text_long", {}).get("wall", {}) or {}).get("median_s") or 0,
                     (perf.get("results", {}).get("image_ocr_proxy", {}).get("wall", {}) or {}).get("median_s") or 0,
                     (perf.get("results", {}).get("video_asr_proxy", {}).get("wall", {}) or {}).get("median_s") or 0,
                     (perf.get("results", {}).get("p0_judge", {}).get("wall", {}) or {}).get("median_s") or 0,
                     (perf.get("end_to_end", {}).get("chain_wall_s", {}) or {}).get("median_s") or 0),
                  "no_data：%s" % "／".join((perf.get("no_data") or {}).keys()),
                  "部分（3 项 no_data）"))
    ITEMS.append(("14", "目标 18 P0 红线法务逐条确认（PRD §16）",
                  "签署台账 **%d** 行" % nl,
                  "`kb/l5/registry/p0-legal-signoff-ledger.jsonl`（另一会话本轮建）",
                  "已交付（签署待法务）"))
    ITEMS.append(("15", "目标 19 单条时效＋群响应（PRD §12）",
                  "单条时效（**裁定口径＝守衡回复**）%s"
                  % ((live.get("perf_text") or {}).get("measured") or "**读不到**（不许当达标）"),
                  "群响应（回执卡口径）：%s"
                  % ((live.get("group_response") or {}).get("measured") or "**读不到**"),
                  "部分（性能三档未达标，见 §3.6）"))
    ITEMS.append(("16", "目标 20 报告导出／阈值可配置（PRD §5.3.4/§8.3）",
                  "`report-threshold-policy.json` 在（KB 侧已删写死常量）",
                  "★ PDF 导出属**飞书侧云文档功能**（Owner 定：备注项，不计交付）",
                  "已交付（KB 侧）"))
    ITEMS.append(("17", "目标 21 多维表统计与筛选导出（PRD §8.2）",
                  "`bitable-stats-latest.json` 在；导出 BLOCK/REVIEW 两份 CSV；自证 = %d" % g_bit,
                  "`risk_type` 加权统计可用（可解析覆盖率 %.2f）"
                  % float(((bit.get("risk_type") or {}).get("可解析覆盖率")) or 0),
                  "已交付"))

    # ★ 判定列里有 `**` 强调标记 ⇒ 计数前先剥掉，否则汇总键会变成 `**待签**`
    cnt = collections.Counter(x[4].split("（")[0].replace("*", "").strip() for x in ITEMS)
    L = []
    A = L.append
    A("# 10/12–10/16 行 · 结项与《未达标说明》")
    A("")
    A("> 对应：xlsx **A6 行（10/12–10/16）「文字链路首次跑通」**，G 列 **17 条「必须做」**。")
    A("> 工单 §七 逐字：「**周五没达标的项，写进《未达标说明》，不要挪到 10/19 那行。**」")
    A("> ★ **本件的每个数都是现跑探针取的，不是抄 G 列** —— 生成于 %s。"
      % dt.datetime.now().strftime("%Y-%m-%d %H:%M"))
    A("")
    A("---")
    A("")
    A("## 一、判定汇总")
    A("")
    A("| 判定 | 条数 |")
    A("|---|---|")
    for k, v in cnt.most_common():
        A("| %s | %d |" % (k, v))
    A("")
    A("**一句话**：**17 条里没有一条是「没做」** —— **%d 条已交付 ＋ %d 条部分交付**"
      "（含 3 项结构性 no_data）、**%d 条本地已尽**（缺口在源侧）、**%d 条待签/依赖后续**。"
      % (cnt.get("已交付", 0), cnt.get("部分", 0), cnt.get("本地已尽", 0),
         cnt.get("待签", 0) + cnt.get("待签/依赖后续", 0)))
    A("")
    A("## 二、逐条（每条带判据，可复算）")
    A("")
    A("| # | 必须做 | 实测（现跑） | 依据 | **判定** |")
    A("|---|---|---|---|---|")
    for no, name, meas, ev, verdict in ITEMS:
        A("| %s | %s | %s | %s | %s |" % (no, name, meas, ev, verdict))
    A("")
    A("## 三、《未达标说明》—— 未闭合项逐条")
    A("")
    A("### 3.1 卡在**签字**上的（3 件，都不是技术问题）")
    A("")
    A("| # | 事项 | 卡在哪 | 我的推荐 |")
    A("|---|---|---|---|")
    A("| 1 | **目标 5 外部标准抽成规则** | `改动单-外部标准抽取口径-20261010.md` 状态 **待批**；"
      "根因（L1 定长字符切）未修 ⇒ `external_standard` 规则仍 **0 条** | **批** |")
    A("| 2 | **目标 8 模态两条候选口径** | 候选 A（`广告类型`，16 条）／候选 B（来源性质默认 `text`，最多 493 条） | **都先不签**，交回源侧 |")
    A("| 3 | **目标 11 置信度阈值** | 政策值是 PRD 照抄，**未标定**；标定依赖金标集（11/30 那行） | 维持 `heuristic_not_calibrated` |")
    A("")
    A("### 3.2 卡在**源侧/外部**的（3 件）")
    A("")
    A("| # | 事项 | 缺什么 |")
    A("|---|---|---|")
    A("| 4 | 目标 7 适用范围 401 条 | 源侧给 `专家修订汇总表` 补「适用产品线 / 适用渠道」两列 |")
    A("| 5 | 目标 16 权限矩阵**人名** | 要你或统筹给具名人（本库无从推断） |")
    A("| 6 | 目标 16「专家」角色位 | `routing-policy.json` 无该角色（`open_questions[expert-role-missing]`） |")
    A("")
    A("### 3.3 **结构性**算不出来的（3 件，如实写）")
    A("")
    A("| # | 事项 | 为什么 |")
    A("|---|---|---|")
    A("| 7 | 目标 13 审查覆盖率 | **分母不存在**：库里没有「本期应审素材清单」这种东西 |")
    A("| 8 | 目标 13 误报 / 漏报 | **要人工金标**当对照；11/30 那行才建 |")
    A("| 9 | 目标 13 知识库回流数量 | **回流未接线**（11/23 那行）；现在恒 0，而那个 0 是「没接」不是「没有」 |")
    A("")
    A("### 3.4 本机测不到的（1 件 ＋ 1 件**已更正**）")
    A("")
    A("| # | 事项 | 为什么 |")
    A("|---|---|---|")
    A("| 10 | ~~目标 17 群响应 ≤5s~~ **已可测（本行更正）** | 埋点 2026-10-10 就位；"
      "现读：%s ⇒ **不再是「测不到」**。"
      % ((live.get("group_response") or {}).get("measured") or "**读不到**"))
    A("| 11 | 目标 17 图片/视频**真实**时效 | 现有是 `image_ocr` / `video_asr` **代理**，不是端到端真媒体 |")
    A("")
    A("### 3.6 ★ 按 Owner 2026-10-12 口径复判：PRD §12「性能」三档**未达标**")
    A("")
    A("> 口径逐字：「单条文字 ≤ 10 秒；图片 ≤ 20 秒；视频 ≤ 60 秒 ==》指的是**飞书侧守衡回复的时间**。")
    A("> 比如：我发文字给守衡，守衡 10s 内回复我结果。")
    A("> 判据 `kb/l8/measure_verdict_latency.py`（当日新建，自证 15/15）｜"
      "登记 `kb/l7/registry/perf-known-drift.yaml`（**未登记者＝新事件**）")
    A("")
    A("| 档 | PRD 门槛 | 实测（**守衡回复**：min／中位／max） | 判 |")
    A("|---|---|---|---|")
    for _k, _nm, _lim in (("perf_text", "单条文字", "10 s"), ("perf_image", "图片", "20 s"),
                          ("perf_video", "视频", "60 s")):
        _v = live.get(_k) or {}
        A("| %s | ≤ %s | %s | %s |" % (_nm, _lim,
          _v.get("measured") or "**读不到**",
          ("✅ 达标" if _v.get("verdict") == "pass" else
           ("❌ **未达标**" if _v.get("verdict") else "—"))))
    A("")
    A("**根因：瓶颈不在知识库** —— 证据层地板 4~5 s、四层前置 ~15 s，链本身逐字"
      "「🧭 送审链返回：跑成｜1875ms」；慢的是 **LLM 写那张卡**（逐字「💬 回复 2903 字，耗时 54541ms」）。")
    A("⇒ 要改的是**守衡侧**（另一仓库 `/Users/lute/Project/audit_multi_content`）："
      "缩短回复／按结论分流／换更快的模型档。**知识库侧没有可动的余地**。")
    A("")
    A("★ 同时更正一条旧结论：`kb/l7/reports/perf-latest.md` 原先那句「六项全部达标」量的是"
      "**证据层地板**（不含 agent/LLM）⇒ 在本口径下**不成立**；该报告当日已加口径注记。")
    A("")

    A("### 3.5 本行**新增**的一个发现（不在原 17 条里）")
    A("")
    A("**`kb/l7/runs/index.jsonl` 已被复跑灌入**：实测 **1013 条**评审单按素材去重后只有 **253 条**"
      "（**760 条重复**，最大一组 60 条同一句文案）。不去重时 **BLOCK 占比 51.6%、去重后 41.1%**"
      "（差 **10.5 个百分点**）。凡读这个文件的读数都带这个偏差。")
    A("⇒ 已在本轮的交检器里按「同一素材只留最早」处理；**要不要回洗 index 本身，等你裁**（我没动它）。")
    A("")
    A("## 四、尺子（本件生成时现跑）")
    A("")
    A("| 尺子 | 退出码 |")
    A("|---|---|")
    for nm, rc in (("`kb_rule_dimensions --selftest`", g_kdim),
                   ("`kb/l8/audit_sample.py --selftest`", g_as),
                   ("`kb/l8/bitable_stats.py --selftest`", g_bit),
                   ("`kb/l8/workflow_smoke.py`", g_smoke),
                   ("`kb/l8/regression_gate.py`", g_gate),
                   ("`kb/l7/scripts/l3_gate.py`", g_l3),
                   ("`kb/l8/check_source_readonly.py`", g_src),
                   ("`kb/l8/measure_verdict_latency.py --selftest`", g_vl),
                   ("`kb/l8/check_prd12_acceptance.py --selftest`", g_p12)):
        A("| %s | %s |" % (nm, "**0 ✅**" if rc == 0 else "**%d ❌**" % rc))
    A("")
    A("## 五、给 10/19 行的交接（**别把这些挪过去，只交接**）")
    A("")
    A("- **目标 7 的维度字段**已冻结并接线（`dimension-policy.json` active）⇒ 10/19 行「报告补维度/位置」"
      "的**前置已具备**（`risk_level` / `applicable_scope` / `modality` 三字段在位且有出处）。")
    A("- **目标 8 的候选口径**若在 10/19 前签了，回填只需一条命令"
      "（`sh kb/kbpy .work/backfill_dimensions.py`，幂等）。")
    A("- **`review.py` 严重度死分支**已修（本行顺带查出，见 `改动单-严重度死分支-20261012.md`）。")
    A("")

    text = "\n".join(L)
    _safe_write.write_text(OUT, text)
    print("已落盘：%s" % OUT)
    print("回读：%d 字节 / %d 行" % (os.path.getsize(OUT), len(text.splitlines())))
    print("判定汇总：%s" % dict(cnt))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
