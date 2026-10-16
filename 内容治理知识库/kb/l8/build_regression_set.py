#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_regression_set.py —— 建**固定回归集**（只读采集，落一件声明）。

════════════════════════════════════════════════════════════════════════
为什么必须有它（这是「修 L1 抽取口径」改动单的**第一件前提**）
════════════════════════════════════════════════════════════════════════

改动单 `改动单-外部标准抽取口径-20261010.md` 要动 **L1 重分块 ⇒ L2 ⇒ L6 索引**，
而 **L6 索引是评审链「单元层」召回的底座** ⇒ **评审结论可能变**。
按 Owner 硬约束「不要影响工作流」，放行前必须证明**同一批素材的三态不变**。

**但库里没有金标件** —— 所以那句话今天**无法证明**。本件就是那把尺子。

⚠️ 本件与「目标 14 每周人工抽检 100 条」**不是一回事**（Owner 已把那条推迟到开发完成 90%）：
  · **本件**＝从**既有**评审里采一批**已知答案**的素材，做**回归对照**（改前/改后同一批）；
  · 目标 14＝**人**每周抽检**新**记录、评估**准确率**。**对象、目的、执行者都不同。**

════════════════════════════════════════════════════════════════════════
★★ 一条关键设计：**「拒答」必须单独分层**，不能混进回归断言
════════════════════════════════════════════════════════════════════════

实测三态分布里有 **23 条是「拒答」**（`NEEDS_INPUT`，多为 `coverage_not_covered` ——
「库对该题材没有可依据的条款」）。它们的**答案本身依赖库的覆盖度**：
一旦外部标准库真的接上（正是改动单要干的事），这 23 条**理应变成能判** ——
**改了是进步，不是回归。**
⇒ 它们必须**单独成层并标 `fragile: true`**，否则日后一比对就会把「变好了」误报成「回归了」。
本库栽过同类：拿一个会随覆盖度动的数当固定基线。

**反过来**：`BLOCK` / `REVIEW` / `PASS` 三态是**判定**，不该随上游切分而变
（除非判定依据真的变了）—— 那才是回归断言该盯的。

用法：

    python3 kb/l8/build_regression_set.py               # 预演（默认，零写入）
    python3 kb/l8/build_regression_set.py --apply       # 写 kb/l7/registry/regression-set.yaml
    python3 kb/l8/build_regression_set.py --selftest    # 反向对照（不碰真库）
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
KB = os.path.dirname(HERE)
REPORTS = os.path.join(KB, "l7", "reports")
DECL = os.path.join(KB, "l7", "registry", "regression-set.yaml")

#: **必须排除**的报告名特征。
#: `PERF-*` 是 2026-10-10 性能测量时**手敲的 31 条测试单**（已登记为污染事件）——
#: 把自造单当金标，等于自己考自己。
EXCLUDE_PAT = (re.compile(r"^PERF-"), re.compile(r"^TEST"), re.compile(r"selftest", re.I))

#: 三态里**会随库覆盖度合法变化**的那一档 ⇒ 单独分层 + 标 fragile。
FRAGILE_STATES = {"拒答", "NEEDS_INPUT"}


def _now():
    import datetime
    return datetime.datetime.now().astimezone().replace(microsecond=0).isoformat()


def parse_report(path: str) -> dict | None:
    """从一份 `<run>.review.md` 里取：素材原文 + 三态 + 问题数 + 版本绑定。

    ★ 取不到就返回 `None`（**不编**）。解析不了的那 18 份会进 `unparsed` 名单，**看得见**。
    """
    t = open(path, encoding="utf-8").read()
    m = re.search(r"结论：\*\*([^*]+)\*\*", t)
    if not m:
        return None
    dec = m.group(1).strip()
    mm = re.search(r"##\s*送审内容\s*\n+```[^\n]*\n(.*?)\n```", t, re.S)
    if not mm or not mm.group(1).strip():
        return None
    text = mm.group(1)
    n = re.search(r"问题数：\**\s*(\d+)", t)
    rid = re.search(r"run_id\s+([A-Za-z0-9._\-]+)", t)
    rv = re.search(r"rule version：`?([^`\n]+)`?", t)
    cid = re.search(r"content hash[^`]*`([0-9a-f]{16,})`", t)
    return {"text": text, "decision": dec,
            "issue_count": int(n.group(1)) if n else None,
            "run_id": (rid.group(1) if rid else os.path.basename(path).split(".")[0]),
            "rule_version": (rv.group(1).strip() if rv else None),
            "content_hash": (cid.group(1)[:16] if cid else None),
            "source_report": os.path.basename(path)}


def collect(reports_dir: str = REPORTS) -> dict:
    cases, unparsed, excluded = [], [], []
    for p in sorted(glob.glob(os.path.join(reports_dir, "*.review.md"))):
        base = os.path.basename(p)
        if any(rx.search(base) for rx in EXCLUDE_PAT):
            excluded.append(base)
            continue
        got = parse_report(p)
        if got is None:
            unparsed.append(base)
            continue
        got["case_id"] = "RC-%s" % hashlib.sha1(
            ("%s|%s" % (got["run_id"], hashlib.sha256(got["text"].encode()).hexdigest()[:12])
             ).encode()).hexdigest()[:12]
        got["text_sha256_12"] = hashlib.sha256(got["text"].encode("utf-8")).hexdigest()[:12]
        got["fragile"] = got["decision"] in FRAGILE_STATES
        # ★ 质量标注（**不删条，只标**）：短素材里混着**非业务探针**
        #   （实测：`test` / `hello world` / `量子纠缠配色调参` / `我们公司去年营收多少？`）
        #   也有**合法的极短红线短语**（`治疗堵奶` / `预防乳腺炎` / `less pain`）。
        #   两者**机器分不开** ⇒ 标 `needs_human_label` 交人，**不许自己判**。
        got["flags"] = []
        if len(got["text"].strip()) < 12:
            got["flags"].append("short")
            got["needs_human_label"] = True
        cases.append(got)
    # 去重：同一素材（text sha 相同）只留**最早**那份（首判；复判会带前一次的上下文）
    seen, dedup = {}, []
    for c in sorted(cases, key=lambda x: x["source_report"]):
        k = c["text_sha256_12"]
        if k in seen:
            seen[k]["duplicates"].append(c["source_report"])
            continue
        c["duplicates"] = []
        seen[k] = c
        dedup.append(c)
    return {"cases": dedup, "unparsed": unparsed, "excluded": excluded,
            "n_raw": len(cases)}


def render(res: dict) -> str:
    cases = res["cases"]
    by = Counter(c["decision"] for c in cases)
    solid = [c for c in cases if not c["fragile"]]
    frag = [c for c in cases if c["fragile"]]
    L = []
    L.append("# regression-set.yaml —— **固定回归集**（上游改动的三态对照尺子）")
    L.append("#")
    L.append("# 谁写它：`kb/l8/build_regression_set.py --apply`（**脚本生成，人手别改**）")
    L.append("# 谁读它：**人**（改上游前后各跑一遍、逐条比对三态）。**没有自动消费者**。")
    L.append("#")
    L.append("# ★ 它回答的那个问题：**改了 L1/L2/L6 之后，同一批素材的三态变没变。**")
    L.append("#   这是 `改动单-外部标准抽取口径-20261010.md` 的**第一件前提** ——")
    L.append("#   那一单动 L1 重分块 ⇒ L2 ⇒ **L6 索引** ⇒ 评审链单元层召回，")
    L.append("#   而前几单能靠「输入文件 sha 未变」证明无影响，**那一单做不到**。")
    L.append("#")
    L.append("# ★★ **分层读法（别把两层混着比）**：")
    L.append("#   · `solid`（**三态断言**）—— BLOCK / REVIEW / PASS。**改了就不该变**，变了就是回归。")
    L.append("#   · `fragile`（**会合法变**）—— 「拒答」（NEEDS_INPUT，多为 coverage_not_covered：")
    L.append("#     「库对该题材没有可依据的条款」）。它们的答案**依赖库的覆盖度** ⇒")
    L.append("#     外部标准库一接上，这批**理应变成能判** —— **改了是进步，不是回归**。")
    L.append("#     混着比就会把「变好了」误报成「回归了」。")
    L.append("")
    L.append("meta:")
    L.append("  generated_by: kb/l8/build_regression_set.py")
    L.append("  generated_at: \"%s\"" % _now())
    L.append("  source: kb/l7/reports/*.review.md（**只读采集**）")
    L.append("  excluded_patterns: [\"PERF-*（2026-10-10 性能测量自造单，已登记为污染事件）\", \"TEST*/selftest\"]")
    L.append("  n_cases: %d" % len(cases))
    L.append("  n_solid: %d" % len(solid))
    L.append("  n_fragile: %d" % len(frag))
    L.append("  n_needs_human_label: %d   # 短素材（<12 字）—— 里面既有「极短红线短语」"
             "（治疗堵奶 / 预防乳腺炎 / less pain，**该留**）也有「非业务探针」"
             "（test / hello world / 量子纠缠配色调参 / 我们公司去年营收多少？，**未必要留**）；"
             "**机器分不开，标出来交人**。" % sum(1 for c in cases if c.get("needs_human_label")))
    L.append("  decision_distribution: %s" % json.dumps(dict(by), ensure_ascii=False))
    L.append("  dedup_rule: 同一素材（text sha256 前 12 位相同）只留**最早**那份（首判；复判带前一次上下文）")
    L.append("  how_to_use: |")
    L.append("    改上游前后，各跑一遍这批素材（走 `with_kb_evidence.py`），逐条比对：")
    L.append("      · solid 层：三态**必须逐条相同**；不同 ⇒ **回归**，不许放行。")
    L.append("      · fragile 层：允许从「拒答」变成三态中任一；**但必须逐条说明为什么**（是覆盖度提升？还是别的）。")
    L.append("      · 还有一条硬要求：**`kb/l3/candidates/rules.jsonl` 的 sha256 必须逐字不变**")
    L.append("        （它 1018 条 `kb_type` 全是 `wording`，本单只碰 `external_standard`）。")
    L.append("")
    L.append("# ── solid：三态断言（改了就不该变）─────────────────────────────")
    L.append("solid:")
    for c in solid:
        L.append("  - case_id: %s" % c["case_id"])
        L.append("    expected: %s" % c["decision"])
        L.append("    issue_count: %s" % (c["issue_count"] if c["issue_count"] is not None else "null"))
        L.append("    run_id: %s" % c["run_id"])
        L.append("    source_report: %s" % c["source_report"])
        L.append("    rule_version: %s" % json.dumps(c["rule_version"], ensure_ascii=False))
        L.append("    text_sha256_12: %s" % c["text_sha256_12"])
        if c.get("flags"):
            L.append("    flags: %s" % json.dumps(c["flags"], ensure_ascii=False))
            L.append("    needs_human_label: true    # 机器分不开「极短红线短语」与「非业务探针」⇒ 交人"
                     "（删条也要人点头，本件只标不删）")
        if c["duplicates"]:
            L.append("    duplicates: %s" % json.dumps(c["duplicates"], ensure_ascii=False))
        L.append("    text: %s" % json.dumps(c["text"], ensure_ascii=False))
    L.append("")
    L.append("# ── fragile：会随库覆盖度**合法**变化（改了要逐条解释，不算回归）──────")
    L.append("fragile:")
    for c in frag:
        L.append("  - case_id: %s" % c["case_id"])
        L.append("    expected: %s          # ← 只作「当时的答案」读，**不是**断言" % c["decision"])
        L.append("    issue_count: %s" % (c["issue_count"] if c["issue_count"] is not None else "null"))
        L.append("    run_id: %s" % c["run_id"])
        L.append("    source_report: %s" % c["source_report"])
        L.append("    text_sha256_12: %s" % c["text_sha256_12"])
        if c.get("flags"):
            L.append("    flags: %s" % json.dumps(c["flags"], ensure_ascii=False))
            L.append("    needs_human_label: true")
        L.append("    text: %s" % json.dumps(c["text"], ensure_ascii=False))
    L.append("")
    L.append("# ── 采集时**取不到**的（如实列，不藏）────────────────────────────")
    L.append("unparsed_reports:")
    for u in res["unparsed"]:
        L.append("  - %s" % u)
    L.append("excluded_reports:")
    for e in res["excluded"]:
        L.append("  - %s" % e)
    L.append("")
    return "\n".join(L) + "\n"


def run(apply_now: bool, decl_path: str = DECL, reports_dir: str = REPORTS) -> int:
    res = collect(reports_dir)
    text = render(res)
    by = Counter(c["decision"] for c in res["cases"])
    print("固定回归集 · 采集（**只读** —— 除本件外不写任何库内数据）")
    print("-" * 70)
    print("  扫描报告：%d 份" % (len(glob.glob(os.path.join(reports_dir, '*.review.md')))))
    print("  排除（自造/测试）：%d 份" % len(res["excluded"]))
    print("  取不到三态或正文：%d 份（**已列进声明件，看得见**）" % len(res["unparsed"]))
    print("  去重后可用：**%d 条** ｜ 三态分布 %s"
          % (len(res["cases"]), json.dumps(dict(by), ensure_ascii=False)))
    solid = [c for c in res["cases"] if not c["fragile"]]
    frag = [c for c in res["cases"] if c["fragile"]]
    print("  ★ solid（三态断言）：**%d 条** ｜ fragile（会合法变）：**%d 条**"
          % (len(solid), len(frag)))
    print("-" * 70)
    if not apply_now:
        print("[预演] 将写入 %s（%d 字符 / %d 字节）—— 加 --apply 才落盘"
              % (decl_path, len(text), len(text.encode("utf-8"))))
        return 0
    old = open(decl_path, encoding="utf-8").read() if os.path.exists(decl_path) else None

    def _body(t):
        return "\n".join(x for x in t.splitlines() if not x.strip().startswith("generated_at:"))
    if old is not None and _body(old) == _body(text):
        print("[零写入] %s 内容未变（保留原 generated_at）" % decl_path)
        return 0
    if old is not None:
        bak = decl_path + ".bak-" + _now().replace(":", "").replace("-", "")[:15]
        shutil.copy2(decl_path, bak)
        print("[备份] %s" % bak)
    os.makedirs(os.path.dirname(decl_path), exist_ok=True)
    with open(decl_path, "w", encoding="utf-8") as fh:      # `.yaml` 不中信封（逐扩展名实测）
        fh.write(text)
    if open(decl_path, encoding="utf-8").read() != text:
        raise SystemExit("回读不符")
    print("[落盘] %s（%d 字符 / %d 字节，回读一致）"
          % (decl_path, len(text), len(text.encode("utf-8"))))
    return 0


# ══════════════════════════════════════════════════════════════════════
# 反向对照
# ══════════════════════════════════════════════════════════════════════

def _selftest() -> int:
    ok = fail = 0
    fails: list[str] = []

    def ck(n, c, ex=""):
        nonlocal ok, fail
        if c:
            ok += 1
        else:
            fail += 1
            fails.append("%s %s" % (n, ex))

    d = tempfile.mkdtemp(prefix="regset-", dir="/tmp")
    try:
        def w(name, body):
            open(os.path.join(d, name), "w", encoding="utf-8").write(body)

        w("a.review.md", "结论：**BLOCK**｜问题数：2\n\n## 送审内容\n\n```\n素材甲\n```\n")
        w("b.review.md", "结论：**PASS**｜问题数：0\n\n## 送审内容\n\n```\n素材乙\n```\n")
        w("c.review.md", "结论：**拒答**｜问题数：0\n\n## 送审内容\n\n```\n素材丙\n```\n")
        w("d.review.md", "结论：**REVIEW**｜问题数：1\n\n## 送审内容\n\n```\n素材甲\n```\n")  # 与 a 同素材
        w("PERF-123.review.md", "结论：**BLOCK**｜问题数：9\n\n## 送审内容\n\n```\n自造单\n```\n")
        w("e.review.md", "这份没有结论行，取不到。\n")
        w("f.review.md", "结论：**BLOCK**｜问题数：1\n\n（没有送审内容段）\n")

        res = collect(d)
        ids = {c["source_report"] for c in res["cases"]}
        ck("①采到 3 条（a/b/c）", len(res["cases"]) == 3, sorted(ids))
        ck("②★ PERF-* 被排除", "PERF-123.review.md" in res["excluded"], res["excluded"])
        ck("③★ 同素材去重：d 与 a 同 text ⇒ 只留最早那份（a）",
           "a.review.md" in ids and "d.review.md" not in ids, sorted(ids))
        ck("③b 被去重的落进 duplicates（看得见）",
           any("d.review.md" in (c.get("duplicates") or []) for c in res["cases"]),
           [c.get("duplicates") for c in res["cases"]])
        ck("④取不到的（e/f）如实进 unparsed",
           set(res["unparsed"]) == {"e.review.md", "f.review.md"}, res["unparsed"])
        ck("⑤★ 「拒答」被标 fragile（**不许混进 solid**）",
           [c["fragile"] for c in res["cases"] if c["source_report"] == "c.review.md"] == [True],
           [(c["source_report"], c["fragile"]) for c in res["cases"]])
        ck("⑤b BLOCK/PASS 不标 fragile",
           all(not c["fragile"] for c in res["cases"]
               if c["source_report"] in ("a.review.md", "b.review.md")),
           [(c["source_report"], c["fragile"]) for c in res["cases"]])
        t = render(res)
        ck("⑥声明件两个层都在", "solid:" in t and "fragile:" in t)
        # ★ 按**段落标题**切，不按裸 `fragile:` —— meta 里有 `n_fragile:`，裸切会切错段（踩过）
        _sec = "\nfragile:\n"
        ck("⑥b solid 段里**没有**拒答",
           "expected: 拒答" not in t.split(_sec)[0], t[:200])
        ck("⑥c fragile 段里**有**拒答",
           "expected: 拒答" in t.split(_sec)[1], t.split(_sec)[1][:120])
        ck("⑥d unparsed/excluded 都写进声明件",
           "e.review.md" in t and "PERF-123.review.md" in t)
        ck("⑦case_id 稳定（同输入同 id）", collect(d)["cases"][0]["case_id"]
           == res["cases"][0]["case_id"])
        # ⑧ 幂等：同数据第二次零写入
        dp = os.path.join(d, "reg.yaml")
        run(True, decl_path=dp, reports_dir=d)
        r = run(True, decl_path=dp, reports_dir=d)
        ck("⑧重跑零写入（幂等）", r == 0)
        ck("⑧b 未产生多余 .bak",
           not [x for x in os.listdir(d) if ".bak-" in x], os.listdir(d))
        # ⑨ 空报告目录不恒绿
        empty = os.path.join(d, "empty")
        os.makedirs(empty, exist_ok=True)
        ck("⑨空目录采到 0 条（不编）", collect(empty)["cases"] == [])
    finally:
        shutil.rmtree(d, ignore_errors=True)

    print("build_regression_set --selftest：%d/%d" % (ok, ok + fail))
    for f in fails:
        print("  ✗", f)
    return 0 if fail == 0 else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="建固定回归集（只读采集）")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--decl", default=DECL)
    ap.add_argument("--reports-dir", default=REPORTS)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return _selftest()
    return run(a.apply, decl_path=a.decl, reports_dir=a.reports_dir)


if __name__ == "__main__":
    sys.exit(main())
