#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""workflow_impact_gate.py —— 写**上游面**之前的「工作流影响面」闸门。

## 为什么要有它（2026-10-09 实测事故，不是推演）

一次 L2 重切（`l2_align_current`，run 20261009-1300）把 **338 条在册单元**作废，于是：

    L6 白名单（`kb/l6/SCOPE.txt`，按 unit id 记）里 418 条**指空**
      ⇒ L6 索引与口径脱节（复算 5,717 vs 索引 5,979）
      ⇒ `l6_gate.py` 红
      ⇒ 评审链「遇红即停」停在 L6，用户拿到的是**拒答**（`layer_gate_red`，退出码 4）

而**那次运行自己的报告里就写着这个数**：

    kb/l2/runs/20261009-1300.json → "retired_in_scope_file": 338

⇒ 这不是"没人算"，是**读数有了、没有执行点**（`AGENTS.md` §2.4 那个病）。
本脚本把那个读数变成执行点，规则三条（缺一条都不算修好）：

1. **算影响面**：这次写会让多少**在册**（在 SCOPE.txt 里）的单元失效，涉及哪些资源。
2. **能补偿就补偿**：受影响的资源**本来就在白名单里**（= 已被人核定过），
   把它的**现行**单元按同一套校验补回白名单 —— 调 `kb/l8/l6_scope_append.py`（**唯一写点**，
   它自己有 5 条硬校验 + 批次说明头 + 运行报告；本脚本不自己写 SCOPE.txt）。
   ★ 只补**已在册资源**的现行单元 ⇒ 这条规则**不会把新资源放进白名单**：
     它不是"自动扩范围"，是"重切之后把 id 对回去"。
     实测依据：2026-10-09 那次 88 个资源的现行单元 397 条 / 1,405,308 字，
     与被作废的 418 条 / 1,490,968 字几乎等量（−6%）—— 内容没变，只是换了 id。
3. **补不了就拒**：补偿之后仍有资源**一条都命中不了**（现行单元全不合格）⇒ exit 3，
   打印人该跑的那条命令。**不做半批**。

## 边界（刻意不做的事）

  · **不重建 L6 索引**：那是分钟级的写档（要 --apply、要人看着跑），不属写前闸门的职责。
    补偿完打印重建命令；就算没人跑，`kb/l8/watch_review_readiness.py` 的层闸门检查
    也会在 30 分钟内把红项推给当班人。
  · **不动 L0–L3 的任何数据**：只读退役账 + SCOPE.txt + L2 单元。
  · **不自己判定"该不该退役"**：那是 L2 层主的判断，本闸门只回答"这次退役会不会
    把工作流打断、打断了能不能自动补回来"。

用法：
    python3 kb/l8/workflow_impact_gate.py <RUN> --pending=<要退役的那些行的 jsonl>   # 写前（调用方用）
    python3 kb/l8/workflow_impact_gate.py <RUN> --pending=<…> --compensate           # 补偿
    python3 kb/l8/workflow_impact_gate.py <RUN> --pending=<…> --allow-workflow-impact="<理由>"  # 签字硬写
    python3 kb/l8/workflow_impact_gate.py <RUN>                                      # 诊断：读退役账（累计口径）
    python3 kb/l8/workflow_impact_gate.py --selftest                                 # 判据自证（离线）
退出码：0 = 影响面为 0 **或**已补偿干净（**或**已签字）；3 = 有影响且没补干净（**拒写**）；2 = 读不到账（未测）
"""
import collections
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))          # …/知识库/内容治理
RETIRED = os.path.join(ROOT, "kb/l2/retired_units.jsonl")
SCOPE = os.path.join(ROOT, "kb/l6/SCOPE.txt")
APPEND = os.path.join(ROOT, "kb/l8/l6_scope_append.py")

RUN = next((a for a in sys.argv[1:] if not a.startswith("--")), None)
COMPENSATE = "--compensate" in sys.argv


def _scope_ids(path=SCOPE):
    if not os.path.exists(path):
        return None
    return {l.strip() for l in open(path, encoding="utf-8")
            if l.strip() and not l.startswith("#")}


def _retired_rows(path=RETIRED):
    if not os.path.exists(path):
        return None
    return [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]


def impact(rows, scope, run=None):
    """返回 (条数, 资源 → 被作废的条数)。纯函数，喂样本即可自证。

    ★ `run` 的口径很关键（2026-10-09 第一版就在这里错了）：
      退役账 `retired_units.jsonl` 是**只追加**的 —— 补偿之后旧 id 仍留在账里、
      也仍留在 SCOPE.txt 里（历史，按设计不删）。所以「**累计**在册作废数」永远不降，
      拿它当闸门会把**下一刀也永远拒掉**（实测：补完之后仍报 418）。
      ⇒ 闸门要判的是**这一次写**的影响面：给了 `run` 就只数这一次的，
        没给就数全部（诊断档，读数里会写明是累计口径）。
    """
    rows = [r for r in rows if run is None or r.get("retired_at") == run]
    hit = [r for r in rows if r.get("unit_id") in scope]
    by = collections.Counter(r.get("resource_id") for r in hit)
    return len(hit), dict(by)


def _pending_rows(path):
    """本次**将要**退役的那些行（调用方写个临时 JSONL 递进来）。

    为什么不让闸门自己去猜"将要退役什么"：那只有调用方知道（它的 `RET`）。
    闸门只回答"你递给我的这批，会不会把工作流打断" —— 一个输入、一个答案。
    """
    if not path or not os.path.exists(path):
        return None
    return [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]


def main():
    if "--selftest" in sys.argv:
        return selftest()
    pending = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--pending=")), None)
    rows, scope = _pending_rows(pending), _scope_ids()
    if rows is None:
        rows = _retired_rows()
    if rows is None or scope is None:
        print("✗ 读不到退役账或白名单 ⇒ **未测**（不当作 0 影响）")
        print(f"    {RETIRED} exists={os.path.exists(RETIRED)} ｜ {SCOPE} exists={os.path.exists(SCOPE)}")
        return 2
    scope_by = "本次待写的那批" if pending else "退役账全量（诊断口径）"
    n, by = impact(rows, scope, run=None if pending else RUN)
    print(f"[{RUN or '（未给 RUN）'}] 工作流影响面：输入={scope_by} {len(rows)} 条 ｜ 在册（SCOPE）{len(scope)} 条")
    if not n:
        print("  ✓ 影响面 0：这批作废的单元**一条都不在册** ⇒ 不会打断评审链。")
        return 0
    print(f"  ⚠ 影响面：**{n} 条在册单元会被作废**，涉及 {len(by)} 个资源：")
    for rid, c in sorted(by.items(), key=lambda kv: -kv[1])[:12]:
        print(f"      {c:>4} 条  {str(rid)[:78]}")
    if len(by) > 12:
        print(f"      …另有 {len(by) - 12} 个资源")
    print("  ⇒ 不处理的话：白名单指空 ⇒ L6 索引过期 ⇒ 闸门红 ⇒ 评审链停在 L6 拒答")
    print("     （2026-10-09 实测过一次，见本文件头部）")

    why = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--allow-workflow-impact=")), None)
    if why and not COMPENSATE:
        print(f"\n  ✓ 已签字：`--allow-workflow-impact=\"{why[:70]}\"` ⇒ 明知会影响工作流，按签字继续。")
        print("     ★ 本闸门**不代写**别人的报告：请把这句话连同上面那行影响面读数写进本次 run 报告。")
        print("     ⇒ 签字之后仍欠两件事（补不补由人定，但**别当作已经不会断**）：")
        print(f"        ① 补偿白名单：python3 kb/l8/workflow_impact_gate.py {RUN or '<RUN>'} --compensate")
        print(f"        ② 重建 L6 索引：cd \"{ROOT}\" && sh kb/kbpy .work/l6_build.py {RUN or '<RUN>'} --apply")
        return 0
    if not COMPENSATE:
        print("\n  接下来二选一：")
        print("    ① 补偿（推荐，只补已在册资源的现行单元）：")
        print(f"        python3 kb/l8/workflow_impact_gate.py {RUN or '<RUN>'} --compensate")
        print("    ② 明知会影响工作流也要作废：加 --allow-workflow-impact=\"<理由>\"（会记账）")
        return 3
    if not RUN:
        print("\n  ✗ --compensate 必须带 RUN（写进批次说明头与报告）")
        return 2

    print(f"\n  [补偿] 调唯一写点 kb/l8/l6_scope_append.py（{len(by)} 个资源）…")
    cmd = [sys.executable, APPEND, f"{RUN}-remap",
           "--resources", ",".join(sorted(by)), "--note",
           f"{RUN} 的 L2 重切作废了 {n} 条在册单元；按「已在册资源的现行单元」把它们对回白名单"
           f"（workflow_impact_gate 自动补偿）", "--apply"]
    p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, errors="replace")
    tail = [l for l in (p.stdout or "").strip().splitlines() if l.strip()][-6:]
    print("    " + "\n    ".join(tail) if tail else "    （无输出）")
    if p.returncode != 0:
        print(f"  ✗ 补偿失败（退出码 {p.returncode}）：{(p.stderr or '')[:200]}")
        print("     ⇒ **拒写**：先人工处理白名单，再重跑上游那一步。")
        return 3

    # ★ 补偿之后必须**回读复核**：每个受影响资源在白名单里至少还要命中一条可用单元。
    #   否则"我补过了"就是一句没有判据的话（§2.4.2）。
    sys.path.insert(0, os.path.join(ROOT, "kb/.work"))
    import l6_scope_lib as SL                                            # noqa: E402
    scope2 = _scope_ids()
    kept, _ = SL.usable_units()
    usable = {u["unit_id"] for u in kept}
    rid_of = {}
    for u in kept:
        rid_of[u["unit_id"]] = u["resource_id"]
    alive = collections.Counter(rid_of[i] for i in (scope2 & usable))
    dead = [r for r in by if not alive.get(r)]
    print(f"\n  [复核] 白名单 {len(scope)} → {len(scope2)} 条；在册且可用 {len(scope2 & usable)} 条")
    if dead:
        print(f"  ✗ 仍有 {len(dead)} 个资源**一条都命中不了**（现行单元全不合格）：")
        for r in dead[:8]:
            print(f"      {str(r)[:80]}")
        print("     ⇒ **拒写**：这不是能自动补的，要人看那些资源现在还剩什么。")
        return 3
    print(f"  ✓ 全部 {len(by)} 个受影响资源都还有在册且可用的单元 ⇒ 工作流不断。")
    print(f"  ⇒ 还差一步（本闸门刻意不做）：重建 L6 索引")
    print(f"     cd \"{ROOT}\" && sh kb/kbpy .work/l6_build.py {RUN} --apply"
          f"        # 可用集变了要加 L6_ACCEPT_SCOPE_DELTA=1")
    return 0


def selftest():
    """离线自证：三态必须分得开，且**影响面 0 时不许报红**（反向对照）。"""
    P, F = [], []

    def chk(name, cond, extra=""):
        (P if cond else F).append(name)
        print(f"  {'✅' if cond else '❌'} {name}{('  ' + extra) if extra else ''}")

    S = {"a1", "a2", "b1"}
    rows = [{"unit_id": "a1", "resource_id": "R1"}, {"unit_id": "a2", "resource_id": "R1"},
            {"unit_id": "c9", "resource_id": "R2"}]
    n, by = impact(rows, S)
    chk("① 只数**在册**的那些（不在册的不进影响面）", n == 2, f"n={n}")
    chk("② 资源要归并（同资源两条 → 1 个资源）", by == {"R1": 2}, f"by={by}")
    n0, by0 = impact([{"unit_id": "zz", "resource_id": "R9"}], S)
    chk("③ 反向对照：影响面 0 ⇒ 不许报红（0 与 >0 必须分得开）", n0 == 0 and by0 == {})
    chk("④ 反向对照：白名单是空集 ⇒ 影响面 0（不是「全都要报警」）",
        impact(rows, set()) == (0, {}))
    chk("⑤ 退役账读不到 ⇒ 走未测（不当作 0 影响）", _retired_rows("/nonexistent") is None)
    chk("⑥ 白名单读不到 ⇒ 走未测", _scope_ids("/nonexistent") is None)
    # ★ ⑦ 这一条第一版**自己把自己判红了**：探针字符串里就含要找的那五个字符，
    #   于是恒真（`AGENTS.md` §2.4.4 记的正是这个形状 —— 判据自己的正则里也有一次）。
    #   修法：把针拼出来，别让探针文本进入被扫的文本。
    _needle = "open(" + "SCOPE"
    chk("⑦ 唯一写点：本脚本自己**不写** SCOPE.txt（只 shell 出 l6_scope_append.py）",
        _needle not in open(__file__, encoding="utf-8").read())
    # ★ ⑧ 口径：只追加的退役账 ⇒ 不给 run 就是累计口径，**不能**拿它当"这一刀的影响面"
    _r = [{"unit_id": "a1", "resource_id": "R1", "retired_at": "20260101-0000"},
          {"unit_id": "a2", "resource_id": "R1", "retired_at": "20260202-0000"}]
    chk("⑧ 给了 run 就只数这一次（否则补完之后下一刀会被永久拒掉）",
        impact(_r, S, run="20260202-0000") == (1, {"R1": 1})
        and impact(_r, S) == (2, {"R1": 2}))
    chk("⑨ 反向对照：run 在本批里一次都没出现 ⇒ 影响面 0（不是拿全量凑数）",
        impact(_r, S, run="20990101-0000") == (0, {}))
    print(f"\n自证：通过 {len(P)} / 失败 {len(F)}")
    for x in F:
        print(f"  · 失败：{x}")
    return 1 if F else 0


if __name__ == "__main__":
    sys.exit(main())
