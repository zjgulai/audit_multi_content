#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_view_foreign_survival.py —— 「视图重建之后，**外来条目**还在不在」的读数

★★ 2026-10-16 新写。由来（Owner：「同意你的推进，不要影响现有的工作流」）：

  宿主库视图 `kb/view/` 里有两类条目，**它们由两条完全不同的路径进来**：

    · **派生条目**（文件名 `cg-*`）—— 由 `kb/l8/build_view.py` 从
      `kb/l3/candidates/rules.jsonl` ＋ `kb/l5/p0_patterns.jsonl` 生成；
    · **外来条目**（文件名 `ref-*`）—— 由**人**走 `kb_ingest` 直接写进视图
      （`kb_class: []` 显式声明「判断过、不属四类素材」；见 `_meta/GUIDE.md` §一）。

  `build_view.py` 报告里的 `ok` **只比派生那一半**：

      rep["ok"] = (not missing_entries and not installed_enveloped
                   and E001 == 0 and E046 == 0
                   and loader.entries == expected_entries)

  ⇒ **`ok=True` 一个字都没说外来条目**。而它删文件的那一处是
  `stale_removed`（「上一轮是派生的、这一轮不是了」就 `os.remove`）——
  `preserved_foreign` 只是**事后把盘上剩下的记一笔**，不是断言。
  ⇒ 「外来条目不会丢」当时**只是一句散文**（我 2026-10-16 把它写进了 GUIDE，
     所以这一条是**给那句话配的判据** —— 散文没有失败信号，判据才有）。

## 判据（**不跑重建**，只读盘上与留档的报告 —— 见「为什么不自己跑一次重建」）

  F1  当下盘上的外来条目 **⊇** 最近一次构建报告里的 `foreign_entry_md`
      —— 重建之后，报告认过的外来条目一个都不许少；
  F2  相邻两次构建报告之间，`foreign_entry_md` **只增不减**（`prev ⊆ next`）
      —— 少一条就是「重建把它删了」，那是本条要抓的形状；
  F3  **看得见**：把当下盘上的外来条目逐条列出来（不是只报一个数）。

  ⚠️ **未测**（不判红，但要说出来）：`kb/l8/view_build_*.json` 一份都没有 ⇒ F1/F2 都无从谈起。
     「本机没跑过重建」不是「坏了」（同 FIX-035 的三态纪律）。

## 为什么不自己跑一次重建（**这条是给「不许影响工作流」配的**）

  `build_view.py` **没有非破坏模式** —— 它的 `--out` 默认就是线上视图 `kb/view`。
  为了核一条「重建后还在不在」而**真去重建一次线上视图**，代价与风险都远大于这条读数：
  重建会重写整个 `kb/view/`，而那儿正被别人用着（`kb_guide` / `kb_search` / 就绪巡检）。
  ⇒ 本条**只读**：构建报告是 `build_view.py` 自己落的 `kb/l8/view_build_<run>.json`，
    盘上的条目就在 `kb/view/` 里，两样都不需要动。

## 退出码（**照 `ci/run_gates.py` 的口径来，不是随手定的**）

  `run_gates.py` 对**非阻断**闸门分档：`rc == 3` ⇒ WARN（**不改 runner 退出码**）；
  `rc in (1, 2)` ⇒ ERROR ⇒ **会把 runner 打到退出码 3**。
  ⇒ 本脚本**只退 0 或 3**，异常也自己兜成 3 —— **绝不用 1/2**，
    免得一条本意是「读数」的东西把 CI 变红。

用法：
  python3 kb/l8/check_view_foreign_survival.py            # 读数（0 通过 / 3 需人看）
  python3 kb/l8/check_view_foreign_survival.py --json     # 机读
  python3 kb/l8/check_view_foreign_survival.py --selftest # 反向对照（真造一遍）
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent          # kb/l8
KB = HERE.parent                                # kb
VIEW = KB / "view"

#   「外来条目」的判定：**看文件名前缀 `ref-`**。
#   ⚠️ 为什么不读报告的 `foreign_entry_md` 当唯一真源：那个集合是**构建那一刻**算出来的，
#     而 `kb_ingest` 之后新入的条目报告里根本没有（实测：最近一次构建 2026-10-10 记 foreign=1，
#     而盘上现在有 10 条）。⇒ 盘上那一份必须**自己数**，报告那一份只作历史留档。
FOREIGN_PREFIX = "ref-"
DERIVED_PREFIX = "cg-"


def foreign_on_disk(view: Path) -> list[str]:
    """当下盘上的外来条目（相对视图根的路径，排序）。"""
    if not view.is_dir():
        return []
    out = []
    for r, _d, fs in os.walk(view):
        for f in fs:
            if f.endswith(".md") and f.startswith(FOREIGN_PREFIX):
                out.append(os.path.relpath(os.path.join(r, f), view))
    return sorted(out)


def build_reports(l8: Path) -> list[tuple[str, dict]]:
    """
    按**时间**排序的构建报告（`view_build_<run>.json`；`view_write_report_*` 不算）。

    ⚠️⚠️ **不许按 run 名排序** —— 这是本判据第一次真跑就踩到的假阳性（实测 2026-10-16）：
      run 名有三种形状（`20261010-1233`、`CHK-20261004-0152`、`20260923-1656`），
      而 ASCII 里数字 < 字母 ⇒ 字符串排序把 `CHK-20261004-0152`（**10-04**）排到了
      `20261010-1233`（**10-10**）**后面** ⇒ F2 判成「后一轮少了一条」，
      而少的正是 10-05 才入库的 `ref-content-review-kb-plan-v2-5` —— **一条纯粹的假红**。
      （本仓记过同一句话：**一条假红会挤掉一个真问题**。）
    ⇒ 排序键取报告自己的 `at`（`build_view.py` 落的 `%Y-%m-%d %H:%M:%S`），
      没有 `at` 才退回 run 名 —— 而且**退回时也只在同形状内可比**，
      所以 `at` 缺失的排在最后（宁可少比一对，也不许比错一对）。
    """
    if not l8.is_dir():
        return []
    rows = []
    for p in sorted(l8.glob("view_build_*.json")):
        m = re.fullmatch(r"view_build_(.+)\.json", p.name)
        if not m:
            continue
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception:                                     # noqa: BLE001
            continue
        at = str(d.get("at") or "").strip()
        rows.append(((at, m.group(1)) if at else ("~", m.group(1)), m.group(1), d))
    rows.sort(key=lambda x: x[0])
    return [(run, d) for _key, run, d in rows]


def audit(view: Path, l8: Path) -> tuple[list[str], list[str]]:
    """
    纯判据：回 `(problems, untested)`。坏样本也能直接喂进来做反向对照。

    `problems` 非空 ⇒ 脚本退 3（WARN，不改 runner 退出码）；`untested` 只打印、不改退出码。
    """
    problems: list[str] = []
    untested: list[str] = []

    on_disk = foreign_on_disk(view)
    reports = build_reports(l8)

    if not reports:
        untested.append("`kb/l8/view_build_*.json` 一份都没有 ⇒ 「重建之后还在不在」**未测**"
                        "（不是通过，也不是坏；本机没跑过重建而已）")
    else:
        run, latest = reports[-1]
        reported = sorted(latest.get("foreign_entry_md") or [])
        # F1 当下盘上 ⊇ 最近一次报告认过的
        missing = [r for r in reported if r not in on_disk]
        if missing:
            problems.append(
                f"最近一次构建（run={run}）报告认过的外来条目，现在盘上**少了 {len(missing)} 条**："
                + "、".join(missing[:6]) + ("…" if len(missing) > 6 else "")
                + " —— 要么重建把它们删了（`build_view.py` 的 `stale_removed` 那一跳），"
                  "要么有人手动删了（那也得说清楚）")
        # F2 相邻两次报告之间只增不减
        for (r_prev, prev), (r_next, nxt) in zip(reports, reports[1:]):
            a = set(prev.get("foreign_entry_md") or [])
            b = set(nxt.get("foreign_entry_md") or [])
            lost = sorted(a - b)
            if lost:
                problems.append(
                    f"构建报告 {r_prev} → {r_next}：外来条目**少了 {len(lost)} 条**"
                    + "、".join(lost[:6]) + ("…" if len(lost) > 6 else "")
                    + " —— 外来条目是人工入库的，**只许增不许减**")

    # F3 **看得见** —— 只报一个数，人没法核
    if on_disk:
        derived_n = sum(1 for r, _d, fs in os.walk(view) for f in fs
                        if f.endswith(".md") and f.startswith(DERIVED_PREFIX)) if view.is_dir() else 0
        untested.append(f"盘上外来条目（`{FOREIGN_PREFIX}*`）**{len(on_disk)} 条**、"
                        f"派生条目（`{DERIVED_PREFIX}*`）**{derived_n} 条**；逐条："
                        + "、".join(on_disk))
    return problems, untested


def selftest() -> int:
    """
    反向对照：**真造一遍**缺陷，判据必须精确变红（§2.4：新增判据必须同时给反向对照）。

    三半，缺一条都证明不了：
      ① 正常（盘上 ⊇ 报告、报告只增）⇒ **不许**报红；
      ② 报告认过、盘上没了 ⇒ **必须**报红（F1）；
      ③ 后一份报告比前一份少 ⇒ **必须**报红（F2）；
      ④ 一份报告都没有 ⇒ 记**未测**、**不许**报红（别把「没跑过重建」判成坏）。
    """
    import tempfile
    fails = []
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        view, l8 = root / "view", root / "l8"
        (view / "3_措辞表达库" / "L1-facts").mkdir(parents=True)
        l8.mkdir()
        d = view / "3_措辞表达库" / "L1-facts"
        (d / "ref-a.md").write_text("---\nid: a\n---\n", encoding="utf-8")
        (d / "cg-x.md").write_text("---\nid: x\n---\n", encoding="utf-8")
        rel = "3_措辞表达库/L1-facts/ref-a.md"
        (l8 / "view_build_20260101-0000.json").write_text(
            json.dumps({"foreign_entry_md": [rel]}), encoding="utf-8")

        # ① 正常 ⇒ 不许红
        p, u = audit(view, l8)
        if p:
            fails.append(f"① 正常情形竟然报红：{p[:1]}")
        if not u:
            fails.append("① 正常情形什么都没打印（F3「看得见」没生效）")

        # ② 报告认过、盘上没了 ⇒ 必须红
        (d / "ref-a.md").unlink()
        p2, _ = audit(view, l8)
        if not p2:
            fails.append("② 报告认过而盘上没了，竟然没报红（F1 恒绿）")

        # ③ 后一份比前一份少 ⇒ 必须红
        (d / "ref-a.md").write_text("---\nid: a\n---\n", encoding="utf-8")
        (l8 / "view_build_20260102-0000.json").write_text(
            json.dumps({"foreign_entry_md": []}), encoding="utf-8")
        p3, _ = audit(view, l8)
        if not p3:
            fails.append("③ 后一份报告少了条目，竟然没报红（F2 恒绿）")

        # ④ 一份报告都没有 ⇒ 记未测、不许红
        for f in l8.glob("view_build_*.json"):
            f.unlink()
        p4, u4 = audit(view, l8)
        if p4:
            fails.append(f"④ 没有构建报告时被判红了：{p4[:1]}（那会把「没跑过重建」当成坏）")
        if not any("未测" in x for x in u4):
            fails.append("④ 没有构建报告时没记「未测」（等于静默放过）")

        # ⑤ ★ **本条判据自己踩过的假阳性**（实测 2026-10-16）：run 名有三种形状，
        #    而 ASCII 里数字 < 字母 ⇒ **按名排序会把 `CHK-20261004-…` 排到 `20261010-…` 后面**，
        #    于是「后一轮少了一条」被报出来，少的却是一条**当时还没入库**的条目。
        #    这一半钉的是：**排序必须认 `at`，不认名字**。
        #    —— 少了它，上面那四半全绿也照样会在真库上吐假红。
        for f in l8.glob("view_build_*.json"):
            f.unlink()
        (d / "ref-a.md").write_text("---\nid: a\n---\n", encoding="utf-8")
        #   名字顺序与时间顺序**故意相反**：`CHK-*`（晚）在 ASCII 上排在 `2026*`（早）之后
        (l8 / "view_build_20261010-1233.json").write_text(
            json.dumps({"at": "2026-10-10 12:33:00", "foreign_entry_md": [rel]}), encoding="utf-8")
        (l8 / "view_build_CHK-20261004-0152.json").write_text(
            json.dumps({"at": "2026-10-04 01:52:00", "foreign_entry_md": []}), encoding="utf-8")
        p5, _ = audit(view, l8)
        if p5:
            fails.append("⑤ 按名排序的假阳性又回来了（run 名与时间顺序相反时误报「少了一条」）："
                         + str(p5[:1]))

    print("反向对照 --selftest：")
    if fails:
        for f in fails:
            print(f"  ❌ {f}")
        print("❌ 判据不是恒绿的反面 —— 它有问题")
        return 1                      # ⚠️ selftest 由人/CI 手动跑，退 1 是「判据自己坏了」
    print("  ✅ ① 正常不报红 ｜ ② 报告认过而盘上没了 ⇒ 红 ｜ ③ 报告间只增不减 ⇒ 违反即红 "
          "｜ ④ 没有报告 ⇒ 未测不判红 ｜ ⑤ 排序认 `at` 不认 run 名（假阳性钉死）")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--view", default=str(VIEW))
    ap.add_argument("--l8", default=str(HERE))
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()

    if a.selftest:
        return selftest()

    try:
        problems, untested = audit(Path(a.view), Path(a.l8))
    except Exception as e:                                    # noqa: BLE001
        # ★ 兜成 3（WARN），**绝不退 1/2** —— 退 1/2 会被 run_gates 记成 ERROR
        #   并把 runner 打到退出码 3，那就「影响工作流」了。
        print(f"⚠️ 本判据自己没跑成：{e}")
        return 3

    payload = {"ok": not problems, "problems": problems, "untested": untested,
               "foreign_on_disk": foreign_on_disk(Path(a.view)),
               "reports": [r for r, _ in build_reports(Path(a.l8))]}
    if a.json:
        print(json.dumps(payload, ensure_ascii=False, indent=1))
    else:
        print("视图外来条目存活读数（`kb/view` 的 `ref-*`；只读，不跑重建）")
        print("-" * 74)
        for u in untested:
            print("  ·", u)
        for p in problems:
            print("  ❌", p)
        print("-" * 74)
        print("结论：" + ("✅ 外来条目一条没少" if not problems else
                          f"⚠️ 有 {len(problems)} 处需人看（**WARN，不改 CI 退出码**）"))

    #   ⚠️ 退出码只有 0 与 3：3 = WARN（run_gates 对非阻断闸门的分档），
    #     1/2 会被记成 ERROR 并**改变 runner 的退出码** —— 本条不许那样。
    return 0 if not problems else 3


if __name__ == "__main__":
    sys.exit(main())
