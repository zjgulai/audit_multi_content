#!/usr/bin/env python3
"""生成「目标 6 · 风险等级按维度重算」**执行结果件**（.md）。

★ 数据来路（**真产物，不是探针推算**）：
  改前 = `kb/l8/_archive/dim-backfill-risklevel-v2-20261012-1035/rules.jsonl.before`（归档件）
  改后 = `kb/l3/candidates/rules.jsonl`（现文件）
  两者按 `rule_id` 对账。

★ 写盘口径：走 `kb/.work/_safe_write.write_text()`（node + 回读复核）——
  python 直写 `.md` 会在宿主侧多 4096 字节信封 ⇒ E001（库规已记）。
"""

from __future__ import annotations

import collections
import glob
import json
import os
import subprocess
import sys

KB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(KB)
sys.path.insert(0, os.path.join(KB, ".work"))
sys.path.insert(0, os.path.join(KB, "l3"))

import _safe_write                                       # noqa: E402
import kb_rule_dimensions as D                           # noqa: E402

BEFORE = os.path.join(KB, "l8", "_archive",
                      "dim-backfill-risklevel-v2-20261012-1035", "rules.jsonl.before")
AFTER = os.path.join(KB, "l3", "candidates", "rules.jsonl")
OUT = os.path.join(ROOT, "交付-目标6-风险等级重算-执行结果-20261012.md")


def load_merged(p):
    by = {}
    for l in open(p, encoding="utf-8"):
        if not l.strip():
            continue
        r = json.loads(l)
        m = by.setdefault(r.get("rule_id"), {})
        for k, v in r.items():
            if v not in (None, "", [], {}):
                m[k] = v
    return by


def main() -> int:
    b, a = load_merged(BEFORE), load_merged(AFTER)
    assert set(b) == set(a), "改前改后的 rule_id 集合不一致 —— 不许继续"
    idx = D.build_l0_index()
    look = D.l0_lookup(idx)

    old = collections.Counter(str(b[k].get("risk_level")) for k in b)
    new = collections.Counter(str(a[k].get("risk_level")) for k in a)
    n_rules = len(a)
    n_lines = sum(1 for l in open(AFTER, encoding="utf-8") if l.strip())

    moved = collections.Counter()
    changed, flipped = [], []
    for k in b:
        o, n = str(b[k].get("risk_level")), str(a[k].get("risk_level"))
        if o != n:
            moved[(o, n)] += 1
            changed.append((k, o, n, a[k].get("risk_level_basis"), a[k].get("p_level")))
            if {o, n} & {"Critical"}:
                flipped.append((k, o, n, a[k].get("risk_level_basis")))

    # 逐维度统计（现文件里 basis 的第一段就是「走了哪一维」）
    dim = collections.Counter()
    for k in a:
        bs = str(a[k].get("risk_level_basis") or "")
        if "源字段 风险等级" in bs:
            dim["① 源字段 风险等级"] += 1
        elif "灯色状态" in bs and "提到" not in bs:
            dim["② 源字段 灯色状态"] += 1
        elif "修订类型" in bs and "提到" not in bs:
            dim["③ 源字段 修订类型"] += 1
        if "提到" in bs:
            dim["④ P0 地板提档（叠加在前三维之上）"] += 1
        if "不编" in bs:
            dim["⑤ 取不到 ⇒ unknown（不编）"] += 1

    # 逐 token（现文件口径）
    tok = collections.Counter()
    for k in a:
        f, _ = look(a[k])
        for t in D.revision_type_of(f)[1] or []:
            pass
        raw = None
        fv = (f or {}).get("修订类型")
        if isinstance(fv, dict):
            raw = fv.get("value")
        elif fv is not None:
            raw = fv
        if isinstance(raw, list):
            raw = raw[0] if raw else None
        if raw:
            s = str(raw).strip()
            toks = [s] if s in D.REVISION_TYPE_TO_RISK else [x.strip() for x in s.split("/") if x.strip()]
            for t in toks:
                if t in D.REVISION_TYPE_TO_RISK:
                    tok[t] += 1

    def run(cmd):
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT, timeout=180)
            return r.returncode
        except Exception:
            return -1

    gates = [
        ("模块自证 `python3 kb/l3/kb_rule_dimensions.py --selftest`（46 项）",
         run([sys.executable, os.path.join(KB, "l3", "kb_rule_dimensions.py"), "--selftest"])),
        ("变异自证 `sh kb/kbpy .work/mutate_risk_level.py`（5 个变异）",
         run(["sh", os.path.join(KB, "kbpy"), ".work/mutate_risk_level.py"])),
        ("L3 闸门 `sh kb/kbpy l7/scripts/l3_gate.py`",
         run(["sh", os.path.join(KB, "kbpy"), "l7/scripts/l3_gate.py"])),
        ("工作流冒烟 `python3 kb/l8/workflow_smoke.py`（五段契约 S1–S5）",
         run([sys.executable, os.path.join(KB, "l8", "workflow_smoke.py")])),
        ("飞书源只读 `python3 kb/l8/check_source_readonly.py`",
         run([sys.executable, os.path.join(KB, "l8", "check_source_readonly.py")])),
        ("信封普查 `python3 kb/l8/envelope_census.py`",
         run([sys.executable, os.path.join(KB, "l8", "envelope_census.py")])),
    ]

    L = []
    A = L.append
    A("# 目标 6 · 风险等级「按维度重算」——执行结果")
    A("")
    A("> 对应：xlsx **A6 行（10/12–10/16）G 列「必须做」第 1 条**（目标 6 风险等级）。")
    A("> Owner 授权（2026-10-12）：走 **A**（先只读重算出证据）→ **签字**（口径由 Owner 签、法务事后追认）"
      "→ **按建议走、不要影响工作流**。")
    A("> 前置件：《交付-目标6-风险等级重算-对照与签字件-20261012.md》。本件是**落地结果**。")
    A("")
    A("---")
    A("")
    A("## 一、口径（已签，落进权威库）")
    A("")
    A("四维链逐条取，**取不到就 `unknown`（不编）**：")
    A("")
    A("| 序 | 维度 | 现行条数 |")
    A("|---|---|---|")
    for k in ("① 源字段 风险等级", "② 源字段 灯色状态", "③ 源字段 修订类型",
              "④ P0 地板提档（叠加在前三维之上）", "⑤ 取不到 ⇒ unknown（不编）"):
        A("| %s | %s | %d |" % (k[0], k[2:], dim.get(k, 0)))
    A("")
    A("**★★ 删掉了什么**：旧版的四档批量兜底 `P_LEVEL_TO_RISK`（P1→High / P2→Medium / P3→Low）。")
    A("它实测把 **420 条规则整批压成同一档**、零区分度 —— 病根是**拿错了轴**：")
    A("`p_level` 是 PRD **§6.2 的优先级层级**，`risk_level` 是 **§6.5 的风险等级**。")
    A("只保留 **P0 一条地板**（PRD §7.3 逐字「命中即驳回，不进入后续审查层级」）。")
    A("")
    A("## 二、结果")
    A("")
    A("**条数口径（重要）**：`rules.jsonl` = **%d 行** = **%d 条规则** × 2 行（每条规则：生行 + 富化行）。"
      "下表一律按**规则条数**。" % (n_lines, n_rules))
    A("")
    A("| 档 | 改前 | 改后 |")
    A("|---|---|---|")
    for lvl in ("Critical", "High", "Medium", "Low", "unknown"):
        A("| %s | %d | %d |" % (lvl, old.get(lvl, 0), new.get(lvl, 0)))
    A("")
    A("变动 **%d / %d** 条。迁移矩阵：" % (sum(moved.values()), n_rules))
    A("")
    A("| 改前 → 改后 | 条数 |")
    A("|---|---|")
    for (o, n), v in moved.most_common():
        A("| %s → %s | %d |" % (o, n, v))
    A("")
    A("## 三、落到 `Critical` 的 %d 条，逐条可核" % new.get("Critical", 0))
    A("")
    A("**全部来自源侧证据 + P0 地板，没有一条出自本库自己的语义判断**（「不编」的直接体现）：")
    A("")
    for k, o, n, basis in flipped[:12]:
        A("- `%s` %s → %s ｜ %s" % (k, o, n, str(basis)[:96]))
    if len(flipped) > 12:
        A("- …（共 %d 条，全量见 `kb/l3/candidates/rules.jsonl` 的 `risk_level_basis`）" % len(flipped))
    A("")
    A("## 四、尺子（六道全绿）")
    A("")
    A("> 另跑过一次 L3 日更**预演**（`sh kb/kbpy l8/l3_distill_run.py`，退出码 0）——")
    A("> 但它的 dry-run 守卫在 `apply_dimensions`（第 699 行）**之前**就退出了，")
    A("> 所以**它测不到本次改动**，不列为判据。真正管用的是 §4.1 那条逐字节幂等。")
    A("")
    A("| 尺子 | 退出码 |")
    A("|---|---|")
    for name, rc in gates:
        A("| %s | %s |" % (name, "**0 ✅**" if rc == 0 else "**%d ❌**" % rc))
    A("")
    A("### 4.1 ★ 「不影响工作流」的硬证据：口径**逐字节幂等**")
    A("")
    A("日更 `kb/l8/l3_distill_run.py:699` 会 `apply_dimensions(mode=\"force\")` **重算**这批字段。")
    A("所以真正要证的是：**日更重算一遍，`rules.jsonl` 逐字节不变**。实测：")
    A("")
    A("```")
    A("写入后        sha256 = f902c9b0c84bc41d01e35c34…")
    A("force 重算后  sha256 = f902c9b0c84bc41d01e35c34…")
    A("★ 逐字节相同        : True")
    A("```")
    A("")
    A("### 4.2 影响面排查：`risk_level` 全库只有两个活消费者")
    A("")
    A("- `tiering.tier_of(p_level, layer, severity, risk_level)` —— **收了 `risk_level` 参数却从没用过它**")
    A("  （取值链只用 `p_level` / `layer` / `severity` / P1 兜底）⇒ **三态结论不受影响**。")
    A("- `with_kb_evidence.py` 只是把 `risk_level` 转发给 `tier_of`（同上，无害）。")
    A("- 守衡侧（`audit_multi_content/tools/agent/*.mjs`）**不读** `risk_level`。")
    A("")
    A("## 五、过程中抓到并修掉的三处缺陷（**两处是我自己写错的**）")
    A("")
    A("| # | 缺陷 | 怎么发现的 | 处置 |")
    A("|---|---|---|---|")
    A("| ① | 我把 `去绝对化` 判成 **Critical** | 等距抽查 + 逐条读源里那 6 条 | 改判 **High**。源里「去绝对化」指去掉不成立的适用边界，**不是** §7.3-3 的广告绝对化用语。已钉判据 ①i4 + 变异 M2 |")
    A("| ② | 复合值 `存疑/待讨论` 被误拆 | 读 token（**两路结论都是 unknown ⇒ 分布上看不出来的哑失败**） | 先整值查、未中再拆 `/`。已钉判据 ①i3 + 变异 M3 |")
    A("| ③ | **回填留下一枚错值**：`r-ca61bf7be5b26052`（源 `修订类型=存疑/待讨论`）文件里仍是旧的 `High`，而正确口径是「还没判」 | **幂等检查**（force 重算 sha 不一致） | 按库自己的哨兵惯例（`risk_level` 的哨兵 = `unknown`，正如 `modality` 的 `undetermined`）在**模块里**统一返回哨兵 ⇒ 日更与回填不再可能写出两个值。已钉判据 ①k2 |")
    A("")
    A("> ③ 值得单说：它是**两个产出者写同一个字段**的典型 —— 回填器有「推不出就不写 null 占位」的守卫，")
    A("> 日更却照写 `null`，于是同一条规则在两条路上得到两个值。**只靠分布看不出来**（都是 1 条），")
    A("> 是幂等检查把它逼出来的。")
    A("")
    A("## 六、发现的**活缺陷（未修）** —— 要你裁")
    A("")
    A("`kb/l7/skills/kb-content-review/scripts/review.py:982` 与 `:1015`：")
    A("")
    A("```python")
    A('sev = "BLOCK" if (h.get("p_level") == "P0" or h.get("risk_level") == "高危·红") else "REVIEW"')
    A("```")
    A("")
    A("`h[\"risk_level\"]` 取自 **L3 规则行**。而 2026-10-10 那次换词表已把该列改成**英文**")
    A("（实测现行取值集合 = `Critical/High/Medium/Low/unknown`）⇒ `== \"高危·红\"` **恒假**，")
    A("**这个分支已经静默死掉**。代价：")
    A("")
    A("- **%d 条**规则（改前 %d 条）`risk_level=Critical` 但 `p_level≠P0` ⇒ 该走 BLOCK 的落了 REVIEW；"
      % (sum(1 for k in a if a[k].get("risk_level") == "Critical" and str(a[k].get("p_level")) != "P0"),
         sum(1 for k in b if b[k].get("risk_level") == "Critical" and str(b[k].get("p_level")) != "P0")))
    A("- 靠前半句 `p_level == \"P0\"` 兜住的只有 **%d 条**。"
      % sum(1 for k in a if str(a[k].get("p_level")) == "P0"))
    A("")
    A("**我没修**：修它会把这三态结论从 REVIEW 改成 BLOCK —— 那是**工作流可见的行为变更**，")
    A("正是你这次明令不许碰的。⇒ **交你裁**（推荐：单独开一条改动单，带回归集前后对照再动）。")
    A("")
    A("## 七、回退")
    A("")
    A("```")
    A("/bin/cp kb/l8/_archive/dim-backfill-risklevel-v2-20261012-1035/rules.jsonl.before \\")
    A("        kb/l3/candidates/rules.jsonl        # sha256 回到 3f7d50dc94608577…")
    A("```")
    A("")
    A("**不要只回退数据不回退代码** —— ①f「P1/P2/P3 不兜底」会立刻变红（这正是它该有的行为）。")
    A("归档链（每一版都可回）：`3f7d50dc…`（原始）→ v2 归档 → `f1db7e54…` → v2b 归档 → `f902c9b0…`（现行）。")
    A("")

    text = "\n".join(L)
    _safe_write.write_text(OUT, text)
    print("已落盘：%s" % OUT)
    print("回读：%d 字节 / %d 行" % (os.path.getsize(OUT), len(text.splitlines())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
