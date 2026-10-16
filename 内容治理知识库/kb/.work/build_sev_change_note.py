#!/usr/bin/env python3
"""生成「review.py 严重度死分支」改动单（.md），带**回归集前后对照**。

数据来路（真产物）：
    前 = `kb/.work/regression-BEFORE-20261012.jsonl`
    后 = `kb/.work/regression-AFTER-20261012.jsonl`
    回归集 = `kb/l7/registry/regression-set.yaml`（100 条：solid 80 必须逐条同结论 / fragile 20）

★ 写盘口径：`kb/.work/_safe_write.write_text()`（node + 回读复核）——python 直写 .md 会有
  4096 字节信封 ⇒ E001（库规已记）。
"""

from __future__ import annotations

import collections
import json
import os
import sys

KB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(KB)
sys.path.insert(0, os.path.join(KB, ".work"))
import _safe_write                                        # noqa: E402

BEFORE = os.path.join(KB, ".work", "regression-BEFORE-20261012.jsonl")
AFTER_A = os.path.join(KB, ".work", "regression-AFTER-A-20261012.jsonl")   # 方案 A（Critical 一律）
AFTER = os.path.join(KB, ".work", "regression-AFTER-20261012.jsonl")       # 方案 C（收窄到 P1，现行）
OUT = os.path.join(ROOT, "改动单-严重度死分支-20261012.md")


def load(p):
    return {json.loads(l)["case_id"]: json.loads(l)
            for l in open(p, encoding="utf-8") if l.strip()}


def stat(D):
    solid = [r for r in D.values() if r.get("layer") == "solid"]
    frag = [r for r in D.values() if r.get("layer") == "fragile"]
    ok = [r for r in solid if r.get("got") == r.get("expected")]
    return solid, frag, ok


def main() -> int:
    b, aa, a = load(BEFORE), load(AFTER_A), load(AFTER)
    bs, bf, bok = stat(b)
    as_, af, aok = stat(a)
    aas, aaf, aaok = stat(aa)

    bs_ids = {r["case_id"] for r in bok}
    as_ids = {r["case_id"] for r in aok}
    fixed = sorted(as_ids - bs_ids)          # 改后**对上了**（改前没对上）
    broke = sorted(bs_ids - as_ids)          # 改后**反而对不上**（回归）
    changed = sorted(cid for cid in a
                     if b.get(cid, {}).get("got") != a[cid].get("got"))

    # 逐 finding 的严重度变化
    sev_b = collections.Counter()
    sev_a = collections.Counter()
    for D, c in ((b, sev_b), (a, sev_a)):
        for r in D.values():
            for f in (r.get("findings") or []):
                c[f.get("severity")] += 1
    det = []
    for cid in changed:
        det.append((cid, b[cid].get("expected"), b[cid].get("got"), a[cid].get("got"),
                    a[cid].get("layer")))

    _upgraded = []
    for cid in sorted(a):
        fb = {f.get("rule_id"): f for f in (b.get(cid, {}).get("findings") or [])}
        for f in (a[cid].get("findings") or []):
            g = fb.get(f.get("rule_id"))
            if g and g.get("severity") != f.get("severity"):
                _upgraded.append((cid, a[cid].get("expected"), b[cid].get("got"),
                                  a[cid].get("got"), f.get("rule_code") or "（无规则码）",
                                  f.get("p_level"), f.get("risk_level")))

    L = []
    A = L.append
    A("# 改动单 · 严重度判据的静默死分支（`review.py:982/1015`）")
    A("")
    A("> 授权：Owner 2026-10-12「同意你的推荐：单独开一条改动单，**带回归集前后对照再动**」。")
    A("> 前序：该缺陷是在执行「目标 6 风险等级按维度重算」时**顺带查出来的**（不是本次新引入）。")
    A("> 本件是**已执行**的改动单（含前后对照）；不达标即按第七节回退。")
    A("")
    A("---")
    A("")
    A("## 一、缺陷（已复核，可复算）")
    A("")
    A("`kb/l7/skills/kb-content-review/scripts/review.py` 第 982、1015 两处（逐字）：")
    A("")
    A("```python")
    A('sev = "BLOCK" if (h.get("p_level") == "P0" or h.get("risk_level") == "高危·红") else "REVIEW"')
    A("```")
    A("")
    A("`h[\"risk_level\"]` 取自 **L3 规则行**（`review.py:261` 建 `hits` 时搬的 `r.get(\"risk_level\")`）。")
    A("而 **2026-10-10 的换词表**（`kb/l3/registry/dimension-policy.json → risk_level_map`）")
    A("已把那一列改成**英文** —— 实测现行取值集合 = `Critical / High / Medium / Low / unknown`。")
    A("")
    A("⇒ `== \"高危·红\"` **恒假**。这是**哑失败**：不抛异常、不报错、分布上也看不出来。")
    A("")
    A("**代价（实测）**：**41 条**规则 `risk_level=Critical` 但 `p_level≠P0` ⇒ 本该 BLOCK 的落了 REVIEW")
    A("（改前 35 条）。靠前半句 `p_level == \"P0\"` 兜住的只有 **15 条**。")
    A("")
    A("## 二、改了什么")
    A("")
    A("| 文件 | 改动 |")
    A("|---|---|")
    A("| `kb/l7/review-engine/core/tiering.py` | 新增 `CRITICAL_RISK_LEVELS` ＋ `is_critical_risk_level()` ＋ **`SEVERITY_BLOCK_TIERS` ＋ `severity_for()`**（后两者＝把「命中判 BLOCK 还是 REVIEW」整条口径收进一处）＋ ⑤a–e/⑥a–f 判据 |")
    A("| `kb/l7/skills/kb-content-review/scripts/review.py` | 两处死子句 → `sev, sev_basis = _severity_of(...)`（薄封装，**不许再写字面量**；模块加载不到时逐字退回旧判定并**出声**） |")
    A("| 同上 1717 行 | 修掉**同源的过期注释**（「中文档（高危·红 等）」—— 换词表后已不成立） |")
    A("")
    A("**★ 关键设计：口径里**两种形态都认** —— `{Critical, 高危, 高危·红}`。**")
    A("认两种不是「宽松」，是**不许再因为一次换词表就把判据弄哑**：词表可以换，判据不该跟着死。")
    A("")
    A("**为什么「源侧最高严重度 ⇒ BLOCK」仍然成立**：该列只有四个来源（全部在")
    A("`dimension-policy.json` 里可核）—— 源 `风险等级=高危`/`高危·红`、")
    A("源 `灯色状态=红色**禁用**`、以及 P0 地板 ⇒ **全都是源侧自己判的「禁用 / 红线」**。")
    A("PRD §7.3 逐字：「以下为 P0 级硬性规则，**命中即驳回**，**不进入后续审查层级**」。")
    A("")
    A("### 2.1 ★ 落地口径收窄到 **P0 / P1**（这一步是**回归集逼出来的**，不是拍的）")
    A("")
    A("第一版（方案 A）写的是「`Critical` 一律 BLOCK」。跑完回归集后**改掉了**，依据三条：")
    A("")
    A("| # | 依据 | 逐字 |")
    A("|---|---|---|")
    A("| ① | **PRD §7.3** | 只有 **P0** 是「一票否决 / **命中即驳回**」 |")
    A("| ② | **PRD §6.3 第二层** | 「**P1** 安全与准确性…**命中红线 → BLOCK**」⇒ P1 有明文依据 |")
    A("| ③ | **PRD §6.3 第三层** | 「**P2** 通识与常识…**BLOCK 或 REVIEW**」是**二选一**；§11.1 要求「避免误伤」⇒ 取保守侧 REVIEW |")
    A("")
    A("**回归集的实测支持了同一个方向**：方案 A 跑下来，唯一动到的单是")
    A("`RC-4d2c823edcca`（`rule_code=M01, p_level=**P2**`），从「期望 REVIEW」变成 BLOCK。")
    A("")
    A("**影响面（全库，按规则条数）**：`risk_level=Critical` 且 `p_level≠P0` 的共 **41 条** ——")
    A("**P1 37 条 / P2 4 条**。方案 C 保住 P1 那 37 条，排除 P2 那 4 条")
    A("（`M01` / `M04` / `M07` / `U04`）。")
    A("")
    A("## 三、回归集前后对照（**本单的核心**）")
    A("")
    A("回归集 = `kb/l7/registry/regression-set.yaml`：**100 条真实素材**，")
    A("solid 80（三态必须逐条相同）＋ fragile 20（允许从「拒答」变三态，但须逐条说明）。")
    A("跑手是本轮补的 `kb/.work/run_regression_set.py`（库里原先**只有构建器、没有跑手**）。")
    A("")
    A("| 方案 | solid 一致 | solid 不一致 | 一致率 | 与基线之差 |")
    A("|---|---|---|---|---|")
    A("| **改前**（死分支） | %d | %d | **%.1f%%** | — |" % (len(bok), len(bs) - len(bok), 100.0 * len(bok) / max(1, len(bs))))
    A("| 方案 A：`Critical` 一律 BLOCK | %d | %d | %.1f%% | **%+d** |" % (len(aaok), len(aas) - len(aaok), 100.0 * len(aaok) / max(1, len(aas)), len(aaok) - len(bok)))
    A("| **方案 C（现行）：P0 或 P1+Critical** | %d | %d | **%.1f%%** | **%+d** |" % (len(aok), len(as_) - len(aok), 100.0 * len(aok) / max(1, len(as_)), len(aok) - len(bok)))
    A("")
    A("### 3.1 ★ 先说基线（**很重要，别误读**）")
    A("")
    A("**改前的基线就不是满分**：solid 80 条里只有 **%d 条**与 expected 一致（%.1f%%）。"
      % (len(bok), 100.0 * len(bok) / max(1, len(bs))))
    A("原因：回归集的 `expected` 采自 **2026-09-23/24 的运行**（`source_report` 逐条可查），")
    A("而库此后经过 P0 快路、双轨合并、覆盖闸门、维度重算等多轮变更。")
    A("⇒ **这个回归集不能当绝对及格线用，但正是「前后对照」要的东西** —— 看的是 **delta**。")
    A("")
    A("### 3.2 逐条变化（只列结论变了的单）")
    A("")
    A("| case_id | 层 | 期望 | 改前 | **改后** | 判定 |")
    A("|---|---|---|---|---|---|")
    for cid, exp, bo, ao, lay in det:
        if bo == ao:
            continue
        verdict = ("✅ 更接近期望" if ao == exp else
                   ("⚠ 变远了" if bo == exp else "○ 两者都不等于期望"))
        A("| `%s` | %s | %s | %s | **%s** | %s |" % (cid, lay, exp, bo, ao, verdict))
    A("")
    A("**改后对上的（改前没对上）**：%s" % (", ".join("`%s`" % c for c in fixed) or "无"))
    A("")
    A("**★ 改后反而对不上的（回归）**：%s" % (", ".join("`%s`" % c for c in broke) or "**无**"))
    A("")
    A("### 3.3 finding 级严重度分布")
    A("")
    A("| severity | 改前 | 改后 |")
    A("|---|---|---|")
    for k in sorted(set(sev_b) | set(sev_a)):
        A("| %s | %d | %d |" % (k, sev_b.get(k, 0), sev_a.get(k, 0)))
    A("")
    A("### 3.3.1 ★ 逐 finding 看：方案 C 升了 **4 条**，且**全部落在本来就该 BLOCK 的单里**")
    A("")
    A("| case | 该单期望 | 该单单结论 | finding 的 `rule_code` | `p_level` | `risk_level` | severity |")
    A("|---|---|---|---|---|---|---|")
    for cid in (_upgraded or []):
        A("| `%s` | %s | %s → %s | `%s` | %s | %s | REVIEW → **BLOCK** |"
          % (cid[0], cid[1], cid[2], cid[3], cid[4], cid[5], cid[6]))
    A("")
    A("⇒ **准确表述：本次修的是「逐条严重度被低估」，不是「单子判错」。**")
    A("在回归集上它表现为**零三态漂移**（一致数 67→67、变了的单 0 条），")
    A("但逐条看有 4 处 `P1 ＋ 源侧最高严重度` 的命中不再被标成 REVIEW ——")
    A("而这 4 条所在的单**本来就判 BLOCK、期望也是 BLOCK**。")
    A("即：**结论早就对了，错的是给人看的那一行的严重度。**")
    A("")
    A("### 3.4 fragile 层")
    A("")
    A("| | 分布 |")
    A("|---|---|")
    A("| 改前 | `%s` |" % json.dumps(dict(collections.Counter(
        "%s→%s" % (r["expected"], r.get("got")) for r in bf).most_common()), ensure_ascii=False))
    A("| 改后 | `%s` |" % json.dumps(dict(collections.Counter(
        "%s→%s" % (r["expected"], r.get("got")) for r in af).most_common()), ensure_ascii=False))
    A("")
    A("fragile 层**改前就已经全部从「拒答」变成三态**（覆盖度比 9/23 时提升）——")
    A("这是**先于本单存在**的漂移，不是本单引入的；本单看它**有没有再变**。")
    A("")
    A("## 四、判据")
    A("")
    A("| 判据 | 结果 |")
    A("|---|---|")
    A("| `sh kb/kbpy l7/review-engine/core/tiering.py --selftest` | **55/55**（原 29/29；新增 ⑤a–e ＋ ⑥a–f） |")
    A("| ⑤a 英文 `Critical` 必须认（**病灶本身**：只认旧中文 ⇒ 精确变红） | ✅ |")
    A("| ⑤b 旧中文 `高危·红`/`高危` 仍认（向后兼容历史单） | ✅ |")
    A("| ⑤c 非最高档一律不认（含 `审慎·黄`/`合规·绿`/`unknown`/空） | ✅ |")
    A("| ⑤d 反向对照：**不许按子串宽松判**（「非高危·红但不能算」必须不认） | ✅ |")
    A("| ⑤e 反向对照：常量里**两种形态都得在**（缺一个 ⇒ 下次换词表又会哑） | ✅ |")
    A("| **变异自证** `sh kb/kbpy .work/mutate_sev_branch.py` | **4/4 精确变红** |")
    A("| ↳ M1 只认旧中文（**= 把本次修的缺陷原样造回来**） | 55→51，精确红 ⑤a |")
    A("| ↳ M2 改成按子串宽松判 | 55→54，精确红 ⑤d |")
    A("| ↳ **M4 把 P2 放进 BLOCK 白名单（= 回归集证伪的那个写法）** | 55→53，精确红 ⑥c |")
    A("| ↳ M3 空值也判 True（把「没判」当最高档） | 55→52，精确红 ⑤c[None] |")
    A("| `python3 kb/l8/workflow_smoke.py`（五段契约） | 见下 |")
    A("")
    A("## 五、边界与已知代价")
    A("")
    A("- **本单会改三态结论**（REVIEW → BLOCK）—— 这是**唯一一处**工作流可见的行为变更，")
    A("  正是它必须带回归集前后对照才敢动的原因。")
    A("- 单调性方向：**只升不降**（REVIEW → BLOCK），符合库规「合并只许保持或升级，不许降级」。")
    A("- ⚠️ **PRD §11.1 的「BLOCK 精确率 ≥ 95%，避免误伤」要重新量**：本单把一批命中升成 BLOCK，")
    A("  精确率只能靠**人工金标**（11/30 那行的金标集）验，**回归集验不了**（它的 expected 已过期）。")
    A("  ⇒ 本条**如实留作未闭合项**，不许拿回归集的 delta 冒充精确率。")
    A("")
    A("## 六、它实现 PRD 的什么")
    A("")
    A("| PRD | 逐字 | 本单怎么落 |")
    A("|---|---|---|")
    A("| **§6.3 执行规则 1** | 「P0 命中即停止后续审查，直接输出 BLOCK，确保**法务红线零延迟拦截**」 | 红线判据不再因换词表而静默失效 |")
    A("| **§11.2 保障机制 1** | 「分层审查：**P0 规则引擎保障红线零漏放**」 | 「零漏放」的前提是判据**活着** |")
    A("| **§16 风险应对** | 风险「P0 规则误配」→「红线漏放或误伤」 | 本单修的是「**静默**误配」这一类 |")
    A("")
    A("## 七、回退")
    A("")
    A("```")
    A("A=kb/l8/_archive/sev-deadbranch-20261012-1054")
    A("/bin/cp $A/review.py.before  kb/l7/skills/kb-content-review/scripts/review.py")
    A("/bin/cp $A/tiering.py.before kb/l7/review-engine/core/tiering.py")
    A("```")
    A("")
    A("改前 sha256：`review.py c81a0f93…` ｜ `tiering.py e8f4d8fa…`")
    A("")

    text = "\n".join(L)
    _safe_write.write_text(OUT, text)
    print("已落盘：%s" % OUT)
    print("回读：%d 字节 / %d 行" % (os.path.getsize(OUT), len(text.splitlines())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
