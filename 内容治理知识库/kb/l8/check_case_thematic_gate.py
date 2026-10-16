#!/usr/bin/env python3
"""案例层「题材一致性」闸门的判据自证 —— 用**两份真素材**做反向对照。

## 为什么必须有这一件

闸门加在 `kb/l7/skills/kb-content-review/scripts/review.py` 的案例层依据出口上。
**光写不验，就是注释** —— 本库栽过「判据恒绿、看着像守着、其实什么都没守」。

## 三组样本（全部来自实测）

  A 反例 · BM04 **婴儿监控器**视频（`MC-US-YT-iAVRpPXgAeU`）
    ⇒ 素材原文只有品牌拼写/监控器参数/移动侦测提示，**无一个「水槽/奶瓶/配件/堆满」**
    ⇒ 闸门**必须挡**
  B 反例 · D8 **奶瓶清洗机**视频（`MC-US-YT-9-vZmvgIrRA`）
    ⇒ 素材原文是「M0m207 / Washer / 2850mL / Self-Clean / spray arm」，**同样零命中**
    ⇒ 闸门**必须挡**（它的真发现是品牌/型号写法，与「堆得过满」无关）
  C 正例 · 一条**真的**在讲同类场景的中文素材
    ⇒ 闸门**必须放行**（否则就是把闸门焊死了 —— 那和恒绿一样坏）
  D 反例 · 条款没有主题词
    ⇒ 保守拒（不许默认放行）
  E 组 · **接线**反向对照（2026-10-14 第二轮加）
    E1 取得到 S-1.296 的**真单元文本**（`kb/l2/units.jsonl` 的 `text_excerpt`）
    E2 条款主题词在**它自己的单元文本**里高命中 —— 这就是第一版恒过的机理
    E3 旧接法（素材＋单元文本）放行、新接法（只传素材）挡住，**两者必须不同**
    E4 静态钉住 `review.py` 调用点的**实参个数 = 2**（加回第三个 ⇒ 精确变红）

  ★★ 为什么非有 E 组：**第一版的闸门是空转的**。调用点给函数传了第三个参数
     `row["text_excerpt"]`，而那是 BM25 **库内单元**的文本 —— 对案例条款就是**条款自己的话**
     ⇒ 主题词必然命中 ⇒ 恒过。A–D 四组测的全是**纯函数**（2 参，写法正确），
     **没有一组碰接线**，所以全绿而闸门无效。E 组专治这一层。

用法：`python3 kb/l8/check_case_thematic_gate.py --selftest`
"""
import importlib.util
import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
THEME_PY = os.path.join(ROOT, "kb/l7/review-engine/core/case_theme.py")
CANON = os.path.join(ROOT, "kb/l4/canonical/sample_case.jsonl")

# ── 真素材原文（逐字取自两份已发报告，见交付件的「证据链」一节）──────────────
MAT_BM04 = ("【视频 1｜MC-US-YT-iAVRpPXgAeU.mp4｜82.8s｜640×360｜关键帧 8/8 帧读成功】"
            "画面上的字（按时间码）：[00:05] momCoZY / 5-Inch Dual-mode / Smart Baby Monitor "
            "[00:25] pan 350° / Tilt 110° [00:56] Real-Time Motion Alerts / BM04 detected the "
            "baby is moving. [01:17] momcozY / 5-Inch Dual-mode / Smart Baby Monitor / "
            "Home or Away, Keep Baby in Sight 音轨转写（本机识别）：With me")
MAT_D8 = ("【视频 1｜MC-US-YT-9-vZmvgIrRA.mp4｜226.1s｜640×360｜关键帧 8/8 帧读成功】"
          "画面上的字（按时间码）：[00:14] M0m207 / 兴 [00:42] Max / Washer / 2850mL / "
          "Fill the water tank with purified or distilled water [02:07] M9 Pump Parts / "
          "Loading Guide [02:35] 22 modes / Cleaning / Press the button to choose and switch "
          "modes [03:03] Select Self-Clean mode 音轨转写：Central water column upper rack "
          "upper spray arm")
# 正例：一条**真的**在讲「水槽前清洗奶瓶、配件别堆太满」的中文素材
MAT_POS = ("【设计需求】厨房场景实拍：妈妈站在水槽前清洗奶瓶与吸奶器配件，"
           "整体氛围自然明亮；但水槽、奶瓶、配件不要堆得过满，避免画面杂乱。")


def load_gate():
    """只导入**独立模块** `case_theme.py`。

    ★ 为什么不去 import `review.py`：**它在 import 时就会把整条评审引擎跑起来**
      （模块级解析 `sys.argv` 并执行）—— 实测直接触发了一次空素材评审、还落了一份报告。
      所以闸门逻辑抽在 `case_theme.py` 里，`review.py` 与本源都调它（一份实现）。
    """
    spec = importlib.util.spec_from_file_location("case_theme", THEME_PY)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def clause(article_no="S-1.296"):
    for line in open(CANON, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        o = json.loads(line)
        if o.get("article_no") == article_no:
            return o
    return None


def real_unit_text(article_no="S-1.296"):
    """取该条款**在 L2 单元里的真文本** —— 就是第一版误当成"命中片段"传进去的那个东西。

    来源与引擎一致：`kb/l6/retriever.py:397` 的 `d["text_excerpt"]`，doc 来自 `kb/l2/units.jsonl`。
    """
    c = clause(article_no)
    uids = set((c or {}).get("unit_ids") or [])
    if not uids:
        return ""
    p = os.path.join(ROOT, "kb/l2/units.jsonl")
    if not os.path.exists(p):
        return ""
    for line in open(p, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
        except Exception:
            continue
        if d.get("unit_id") in uids:
            return str(d.get("text_excerpt") or d.get("text") or "")
    return ""


def callsite_arity():
    """静态读 `review.py` 里 `case_thematic_ok(...)` 的**实参个数**。

    ★ 为什么要静态读：那是**接线**，不是纯函数。A–D 组测的是函数本身（写法正确），
      接线写错了它们一个都不会红（2026-10-14 第一版实测如此）。
    """
    import ast
    p = os.path.join(ROOT, "kb/l7/skills/kb-content-review/scripts/review.py")
    try:
        tree = ast.parse(open(p, encoding="utf-8").read())
    except Exception as e:
        return -1, f"（解析失败：{e}）"
    hits = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "case_thematic_ok":
            hits.append((node.lineno, len(node.args) + len(node.keywords)))
    if not hits:
        return -1, "（review.py 里找不到 case_thematic_ok 调用）"
    if len(hits) > 1:
        return -2, f"（调用点不止一处：{hits}）"
    return hits[0][1], f"（行 {hits[0][0]}）"


def pool_stats():
    """依据池（`load_case_clauses` 的口径）里还有没有 superseded；被销号的孪生号在不在池里。

    ★ 为什么在**判据侧**重算一遍池子：`load_case_clauses()` 在 `review.py` 里，
      而那件**import 就会跑整条引擎**（不能 import）。所以这里按**同一口径**从
      canonical 重算 —— 口径写死在同一处（下面四个条件），两边必须一致。
    """
    import json as _json
    rows = []
    for line in open(CANON, encoding="utf-8"):
        line = line.strip()
        if line:
            rows.append(_json.loads(line))

    def in_pool(d):
        rc = str(d.get("reason_category") or "").strip()
        return (d.get("polarity") == "反例" and rc and rc.lower() != "unknown"
                and d.get("anchor")
                and str(d.get("status") or "").strip().lower() != "superseded")

    by = {d.get("article_no"): d for d in rows}
    pool = [d for d in rows if in_pool(d)]
    sup = [d for d in pool if str(d.get("status") or "").lower() == "superseded"]
    twins = 0
    for d in rows:
        if str(d.get("status") or "").lower() != "superseded":
            continue
        for t in (d.get("superseded_by") or []):
            if t in by and in_pool(by[t]):
                twins += 1
                break
    return len(pool), len(sup), twins


def sources_missing_status_filter():
    """扫活代码：读 `canonical/sample_case` 当依据的地方，有没有 `superseded` 过滤。

    返回**缺过滤的文件名列表**（空 = 都带了）。
    """
    import re as _re
    targets = [
        "kb/l7/skills/kb-content-review/scripts/review.py",
        "kb/l7/review-engine/core/selfhit_check.py",
    ]
    missing = []
    for rel in targets:
        p = os.path.join(ROOT, rel)
        if not os.path.exists(p):
            continue
        src = open(p, encoding="utf-8").read()
        if not _re.search(r"[\"']superseded[\"']", src):
            missing.append(os.path.basename(rel))
    return missing


def main():
    R = load_gate()
    c = clause()
    ok = True
    checks = []

    def ck(name, cond, extra=""):
        nonlocal ok
        checks.append((name, cond, extra))
        if not cond:
            ok = False

    ck("前置：S-1.296 在 canonical 里且带主题词",
       bool(c) and bool(R.case_subject_terms(c)),
       f"主题词数={len(R.case_subject_terms(c)) if c else 0}")

    if c:
        terms = sorted(R.case_subject_terms(c))
        ck("主题词确实抓到了病灶词（水槽/奶瓶/配件/堆得过满 之类）",
           any(t in terms for t in ("水槽", "奶瓶", "配件")),
           "、".join(terms[:10]))

        # A：BM04 监控器视频 ⇒ 必须挡
        ga, wa = R.case_thematic_ok(c, MAT_BM04)
        ck("A 反例 · BM04 婴儿监控器视频 ⇒ 必须挡", not ga, wa)

        # B：D8 清洗机视频 ⇒ 必须挡
        gb, wb = R.case_thematic_ok(c, MAT_D8)
        ck("B 反例 · D8 奶瓶清洗机视频 ⇒ 必须挡", not gb, wb)

        # C：真的同题材中文素材 ⇒ 必须放行
        gc, wc = R.case_thematic_ok(c, MAT_POS)
        ck("C 正例 · 同题材中文素材 ⇒ 必须放行", gc, wc)

        # D：条款没主题词时保守拒（不许默认放行）
        gd, wd = R.case_thematic_ok({"reason_analysis": "", "sample_body": ""}, MAT_POS)
        ck("D 条款无主题词 ⇒ 保守拒（不默认放行）", not gd, wd)

        # ── ★★ E 组：**接线**反向对照（2026-10-14 第二轮加）────────────────────
        #   为什么加：第一版的闸门**是空转的** —— 调用点给 `case_thematic_ok` 传了第三个参数
        #   `row["text_excerpt"]`，而那是 **BM25 库内单元**的文本（对案例条款就是**条款自己的话**）
        #   ⇒ 主题词必然命中 ⇒ 恒过。
        #   A–D 四组测的都是**纯函数**（2 参，写法正确），**没有一组碰接线** ⇒ 全绿而闸门无效。
        #   E 组专治这个：它用**真单元文本**把病灶钉死，并直接检查调用点的实参个数。
        unit_txt = real_unit_text()
        ck("E1 能取到 S-1.296 的真单元文本（否则 E2/E3 是空跑）",
           bool(unit_txt), f"长度={len(unit_txt)}")
        if unit_txt:
            # E2：条款主题词在**它自己的单元文本**里几乎全中 ⇒ 这正是第一版恒过的机理。
            #     这一条**必须为真** —— 它为假说明素材/单元取错了，E3 就成了假绿。
            self_hit = [t for t in R.case_subject_terms(c) if t in unit_txt]
            ratio = len(self_hit) / max(1, len(R.case_subject_terms(c)))
            ck("E2 条款主题词在**自己的单元文本**里高命中（第一版恒过的机理）",
               ratio >= 0.9, f"{len(self_hit)}/{len(R.case_subject_terms(c))} = {ratio:.0%}")
            # E3：**接线**必须只传素材。把「素材 ＋ 单元文本」当 hay 就是第一版的错误接法，
            #     它必须**放行**（说明这条素材确实过不了题材关，是单元文本在替它作证）；
            #     而**只传素材**必须**挡住**。
            fake_hay = MAT_D8 + " " + unit_txt
            old_style_pass = bool([t for t in R.case_subject_terms(c) if t in fake_hay])
            new_style = R.case_thematic_ok(c, MAT_D8)[0]
            ck("E3 旧接法（素材＋单元文本）会放行、新接法（只传素材）会挡住 —— 两者必须不同",
               old_style_pass and not new_style,
               f"旧接法放行={old_style_pass} 新接法放行={new_style}")

        # E4：**静态**钉住调用点实参个数 —— 有人把第三个参数加回来 ⇒ 精确变红。
        nargs, why = callsite_arity()
        ck("E4 review.py 调用点恰好传 2 个实参（加回第三个 ⇒ 变红）",
           nargs == 2, f"实参个数={nargs} {why}")

        # ── F 组：**已销号的条款不许再进依据池**（2026-10-14 加）────────────────
        #   为什么：销号原先只写标记，而 `load_case_clauses()` 与 `selfhit_check` 的
        #   `load_clauses()` **都不读 `status`** ⇒ 被销号照样进池、照样被引用 ——
        #   而**被销那一侧的 anchor 是死的** ⇒ 引擎继续产出点不开的直链。
        #   **不加这条，销号在引擎侧等于没生效。**
        n_pool, n_sup, n_twin = pool_stats()
        ck("F1 依据池里**不再有** superseded 条款", n_sup == 0, f"池内 superseded={n_sup}")
        ck("F2 被销号的**孪生号**仍在池子里（覆盖不受损）", n_twin > 0, f"孪生号在池={n_twin}")
        dead = sources_missing_status_filter()
        ck("F3 读 canonical/sample_case 的活代码都带 superseded 过滤",
           not dead, ("缺过滤：" + "、".join(dead)) if dead else "review.py ＋ selfhit_check.py 都有")

    for name, cond, extra in checks:
        print(f"  {'✅' if cond else '❌'} {name}" + (f"  —— {extra}" if extra else ""))
    print(f"\n自证：{sum(1 for _, c2, _ in checks if c2)}/{len(checks)} "
          f"{'通过' if ok else '**未通过**'}")
    sys.exit(0 if ok else 3)


if __name__ == "__main__":
    main()
