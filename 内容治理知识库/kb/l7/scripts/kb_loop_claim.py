#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kb_loop_claim.py —— **会话级**的驱动循环认领（2026-10-03）。

## 它补的是哪个洞

`kb/.work/.kb.lock` 是**命令级**锁：`kb_pipeline.py` 每次运行持锁/释放，几秒到几分钟。
但「层前置 → 评审 → 发布」这条循环是**会话级**的，要跑好几支 subagent、几分钟到十几分钟 ——
**中间没有任何东西阻止第二个会话也在同一个 BASE 上跑**。

实测代价（2026-10-03）：
  · 两个会话同时跑 ⇒ 陈旧锁互撞，L6 记账与 L7 各被 `exit 2` 挡回一次；
  · 同一个 RUN 被两侧先后记账 ⇒ `kb/l7/runs/index.jsonl` 该 RUN 落了 **2 行**（双计）；
  · L7 的记账行被后跑的会话**覆盖**。

本脚本只做一件事：**同一时间只准一个会话在跑这条循环**。它**不是闸门**（不判内容、不判闸门红绿），
只是一张「现在谁在跑」的告示 —— 所以不违反「不造第 7 把尺子」。

★★ **2026-10-08 重大口径变更（Owner 批准 ①）：认领从「全局单槽」改成「按 RUN 分槽」。**

   **旧口径**（本文件原话）：「哪怕两个会话跑的是**不同** BASE，第二个也会被挡（exit 3）。
   这是故意的 …… **别"顺手修成"按 BASE 分槽。**」

   **为什么改**：那条旧口径把「**同一个 RUN**」与「**任何 RUN**」混成了一件事，
   代价落在守衡身上 —— 实测槽被持有**最长 1,659 秒（27.7 分钟）**、中位 34 秒，
   而守衡的评审单只要**几十秒**；于是「会话在库里干活期间，守衡一律库忙」。
   根子在于：**持有单位是「会话」，要保护的却是「一次运行的写集」** —— 锁开大了。

   **为什么「按 RUN」这个键是对的**（旧警告的三条理由逐条核过，全部不成立）：
     · 各层产物**文件名本身就是 RUN 作用域**的（`l7/runs/<RUN>.json`、
       `<layer>/runs/<RUN>-L4.json`）⇒ 不同 RUN ⇒ **不同文件**，根本不会互相覆盖；
     · `kb/.work/.kb.lock`（命令级）**另有** `kb_pipeline.py` 自己的 `O_EXCL` 锁 ——
       认领在这一项上本来就是冗余的；
     · `kb/l7/runs/index.jsonl` 两边都追加，但**全库普查零读方**，且实测
       「每次 write 传完整行」在 4 进程并发下也不穿行（见 `.work/_safe_write.py` 自证 ⑧⑨）。
     · 而 2026-10-03 事故的三条症状（同一 RUN 在 index 落 2 行、L7 记账被覆盖、
       L6/L7 被 exit 2 挡回）**全部是「两个会话跑同一个 RUN」** ⇒ 本键**一条都没放开**。
       且它**真会发生**：`daily_sync.py:78-91` 会**从盘上读最新 run_id**，两会话可能取到同一个。
   ⇒ **同一个 RUN 的互斥一个字没松；不同 RUN 不再互相挡。**

   ⚠️ 随之而来的**新前提**（分槽之后才需要，都已落地）：
     评审链要读的 `kb/l3/candidates/rules.jsonl` **必须是原子写**（原先是 `open(...,"w")`
     截断写 ⇒ 截断与写满之间读者会看到 0 字节或半份）。已改为 temp + `os.replace`
     （`kb/l8/l3_distill_run.py::_write_guarded`，判据在 `.work/_safe_write.py` 自证 ⑥⑦）。

## 用法

    kb/kbpy l7/scripts/kb_loop_claim.py status                       # 列出全部认领（按 RUN）
    kb/kbpy l7/scripts/kb_loop_claim.py claim  --base <RUN> [--session <会话id>] [--ttl 45]
    kb/kbpy l7/scripts/kb_loop_claim.py claim  --base <RUN> --take-over   # 只对**同一个 RUN 的陈旧认领**放行
    kb/kbpy l7/scripts/kb_loop_claim.py release --base <RUN> [--force]    # --force = 拆别人的那一条
    kb/kbpy l7/scripts/kb_loop_claim.py release --force                   # 无 base + --force = **只释放已陈旧的**
    kb/kbpy l7/scripts/kb_loop_claim.py history [--days 2]                # 被占了多少次、谁占的、占了多久

退出码：0 = 拿到/释放成功 ｜ 3 = **这个 RUN 被别人占着**（别抢，停下来）｜ 2 = 用法错
`claim` 遇到「持有者 pid 已死」或「已超 TTL」时**默认仍然拒**，但会告诉你它是陈旧的；
确认要接手就加 `--take-over`（会打印明确的接管告警）。
★ `--take-over` **在跨会话场景才有效**（上一会话崩了 → 新会话 session/pid 都不同）：
  认领**新鲜**时加它**照样拒**（exit 3）；只有「陈旧 + --take-over」才放行。
  另一条等效路径是 `release --base <RUN> --force` 再 `claim`。
★ **存储形状**：`kb/.work/.kb-loop-claim.json` = `{"claims": {<RUN>: 记录}}`；
  旧格式（一条扁平记录）**读侧兼容**，下次写入时自动升格（无迁移脚本）。
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
KB = HERE.parents[1]                      # …/kb
CLAIM = KB / ".work/.kb-loop-claim.json"


def _alive(pid) -> bool:
    try:
        os.kill(int(pid), 0)
        return True
    except Exception:                     # noqa: BLE001
        return False


def _read_claims() -> tuple[dict, bool]:
    """读认领库 ⇒ `({base: 记录}, 读不出来吗)`。

    ★★ 2026-10-08（Owner 批准 ①）：认领从「**全局单槽**」改成「**按 RUN 分槽**」——
       「全局单槽」在运行上等价于「会话在库里干活期间，守衡一律不可用」：实测槽被持有
       **最长 1,659 秒（27.7 分钟）**、中位 34 秒，而守衡的评审单只要**几十秒**。
       持有单位本来是**会话**，要保护的却是**一次运行**的写集 —— 锁开大了。

    ★ 为什么「按 RUN」这个键是**对**的（不是"顺手"改的，逐条核过旧警告的三条理由）：
      · 各层产物**文件名本身就是 RUN 作用域**的：`l7/runs/<RUN>.json`、
        `<layer>/runs/<RUN>-L4.json` ⇒ 不同 RUN ⇒ **不同文件**；
      · `kb/.work/.kb.lock`（命令级）**另有** `kb_pipeline.py` 自己的 `O_EXCL` 锁，
        认领在这一项上本来就是冗余的；
      · `l7/runs/index.jsonl` 两边都追加 —— 但**全库普查零读方**，且实测
        「每次 write 传完整行」在 4 进程并发下也不穿行（见 `_safe_write` 自证 ⑧⑨）。
      · 而 2026-10-03 那次事故的三条症状（同一 RUN 在 index 落 2 行、L7 记账被覆盖、
        L6/L7 被 exit 2 挡回）**全部是「两个会话跑同一个 RUN」** ⇒ 本键**一条都不放开**。
        且它**真的会发生**：`daily_sync.py:78-91` 会**从盘上读最新 run_id**，
        两个会话可能取到同一个 ⇒ 那正是要被挡住的形状。
      ⇒ 旧警告「按 BASE 分槽＝把双计事故放回来」的前提，在今天**已经不成立**。

    ★ 存储形状从**一条扁平记录**变成 **`{base: 记录}` 映射**；旧文件（没有 `claims` 键）
      **照样读得出来**，下一次写入时自动升格 —— **不写一次性迁移脚本**
      （迁移脚本自己也会坏，而读侧兼容是零风险的）。
    """
    if not CLAIM.exists():
        return {}, False
    try:
        d = json.loads(CLAIM.read_text(encoding="utf-8"))
    except Exception:                     # noqa: BLE001
        return {}, True
    if isinstance(d, dict) and isinstance(d.get("claims"), dict):
        return {k: v for k, v in d["claims"].items() if isinstance(v, dict)}, False
    if isinstance(d, dict) and d.get("base"):
        return {d["base"]: d}, False      # ← 旧格式（扁平）⇒ 当成映射里的一条
    return {}, True


def _write_claims(claims: dict) -> None:
    """写回认领库。**一条都不剩时把文件删掉** —— 否则 `status` 说不出「无认领」。"""
    if not claims:
        CLAIM.unlink(missing_ok=True)
        return
    CLAIM.parent.mkdir(parents=True, exist_ok=True)
    CLAIM.write_text(json.dumps({"claims": claims}, ensure_ascii=False, indent=1),
                     encoding="utf-8")


def _mine(c: dict, session=None) -> bool:
    """这条认领是不是本会话/本进程的（释放鉴权用，与改前同一把尺子）。"""
    sess = session or os.environ.get("DSH_SESSION_ID")
    return (str(c.get("pid")) == str(os.getpid())
            or (sess and c.get("session") == sess))


def _age_min(c: dict) -> float:
    try:
        return (time.time() - float(c.get("at_ts") or 0)) / 60.0
    except Exception:                     # noqa: BLE001
        return 1e9


def _stale(c: dict) -> tuple[bool, str]:
    """陈旧判定。

    ── 2026-10-06 改：`pid` 只有在「记的确实是**持有者**」时才许当信号

    **事故（这条改动的全部理由）**：那把「全局单槽」在每次长跑超过 5 分钟之后就是**名义上的**。
    实测两次，机制完全相同：

      · 2026-10-05 10:12:12 就绪巡检「自愈：释放陈旧认领」pid=41445 BASE=daily-20261005-0957 13 分钟前
      · 2026-10-06 08:35:46 同上                              pid=84706 BASE=daily-20261006-0830  6 分钟前

    两次的 worker（headless agent）**都还活着**（10-06 那次 PID 84718，父进程 84697 也活着）。
    真因：`claim` 原先记的是 **`os.getpid()`——认领进程自己**，而它写完就退出 ⇒
    `_alive(pid)` 必然为 False ⇒ 只要年龄过了宽限期，**任何正在跑的长任务都被判成崩溃**。

    所以规矩改成：**记的 pid 必须是持有者的 pid**（`claim --holder-pid`），
    否则这一格**不是证据**，只能靠 TTL。
    旧认领没有 `pid_kind` 字段 ⇒ 按 `claimer` 处理 ⇒ **pid 不参与判定**（向后兼容，且不再误报）。

    三件事分开，缺一件这条判据就还在赌：
      ① TTL 超时 ⇒ 陈旧（主判据，一直没变）；
      ② `pid_kind=holder` 且持有者已死且过了宽限期 ⇒ 陈旧（**真崩溃**才走这条）；
      ③ `pid_kind=claimer`（含所有旧认领）⇒ **pid 不参与**，只看 TTL。
    """
    raw = c.get("ttl_min")
    # ★ 别写 `raw or 45`：`ttl_min=0` 是**合法值**（立刻可接管），`or` 会把它吃成 45 分钟默认值，
    #   导致「明明写了 0、却要等 45 分钟」的静默升格。只有 None / 缺失才回落到默认。
    ttl = 45.0 if raw is None else float(raw)
    age = _age_min(c)
    if age > ttl:
        return True, "超过 TTL %s 分钟（已 %.0f 分钟）" % (ttl, age)
    # ★ 判据收在 `pid_kind` 上，**不是**「有没有 pid 字段」——
    #   旧认领也有 pid 字段，而那个 pid 是认领进程自己的，拿它判存活必然误报。
    if c.get("pid_kind") == "holder" and (not _alive(c.get("pid"))) and age > 5:
        return True, "持有者 pid 已不在且已过宽限期（%.0f 分钟）" % age
    return False, ""


def _describe(c: dict) -> str:
    kind = c.get("pid_kind") or "claimer(旧)"
    return ("会话=%s ｜ pid=%s[%s] ｜ BASE=%s ｜ %.0f 分钟前 ｜ host=%s"
            % (c.get("session") or "—", c.get("pid"), kind, c.get("base") or "—",
               _age_min(c), c.get("host") or "—"))


def cmd_status() -> int:
    """★ 输出文本有两个**下游消费者**，形状不许随意改（2026-10-08 核过）：
      · 守衡 `tools.mjs::claimStatus` —— 认 `无认领` / `陈旧` / 其余=忙；
      · `kb/l8/review_preflight.sh:106` 与 `kb/l8/watch_review_readiness.py`
        —— `grep -q '陈旧（可 --take-over）'` 决定要不要自愈/接管。
      ⇒ 因此：**全部陈旧**时才出现「陈旧（可 --take-over）」；只要还有活着的，
        整段就不得含「陈旧」二字（逐条那一列改用「已过期」），否则下游会把
        「有人正在跑」误读成「可以接手」。
    """
    claims, bad = _read_claims()
    if bad:
        print("⚠️ 认领文件读不出（%s）—— 保守起见先别跑，人工看一眼再决定" % CLAIM)
        return 3
    if not claims:
        print("无认领：现在没有会话在跑这条循环（可以 claim）")
        return 0
    rows = [(b, _stale(c), c) for b, c in sorted(claims.items(),
                                                key=lambda kv: kv[1].get("at_ts") or 0)]
    rows = [(b, st, why, c) for b, (st, why), c in rows]
    if all(r[1] for r in rows):
        for _, _, why, c in rows:
            print("陈旧（可 --take-over）：%s ｜ %s" % (why, _describe(c)))
        return 0
    print("**进行中**（%d 条认领；**按 RUN 分槽**——只挡跑同一个 RUN 的）" % len(rows))
    for base, st, why, c in rows:
        print("  %-24s %-5s %s" % (base, "已过期" if st else "进行中", _describe(c)))
    return 3


# ══════════════════════════════════════════════════════════════════════════
# 认领留痕（2026-10-08 加，Owner 同意 ①）
# ══════════════════════════════════════════════════════════════════════════
# 为什么必须有：**在此之前，这条循环被占了多少、被谁占、占多久 —— 一个数都查不到。**
#   认领文件是**单文件、每次覆盖**，没有历史；于是「守衡被库忙挡住了多少次」只能靠
#   在守衡日志里 grep `claim_busy` 反推，而那只看到**被挡的那一侧**，
#   看不到「谁占着、占了多久、释放没有」。
#   实测代价（2026-10-08）：Owner 问「怎么彻底解决库忙」，我查完只能说
#   「今天 2 次、样本太小」—— 因为**没有第二份数据**。**不量就改**是这次会话反复踩的坑。
#
# ★ **只记状态变更，不记 `status` 轮询**：守衡每次送审都会先 `status` 一次
#   （`claimStatus()`），记它会把这本账淹掉，真正要看的行反而找不到。
# ★ 留痕失败**不许**影响认领本身（它是可观测性，不是安全闸）。
#
# ── 同批次一起查清的三件事（2026-10-08，Owner 同意 ③④）────────────────────────
#
# ③ **「排程避让」的对象不是排程作业 —— 是人会话。** 实测 launchd：
#     · `com.kb.pipeline-daily` / `-daily-skill` = **每周日 03:30**（2026-10-16 日更改周更；
#       此前是每天 03:30，更早是 08:30 —— 时刻一律从 plist 现读，别在这儿抄第二份）；
#     · `com.kb.publish` 每 5 分钟、`com.kb.review-readiness` 每 30 分钟 —— **都不占这条槽**。
#     占槽的是**人会话里跑的库维护**（当天持有者是 `session-11298093…`，BASE `20261008-1500`）。
#   ⇒ 所以本脚本在**被拒时给下一步**（等多久／怎么查历史／别撬），而不是只报「别抢」。
#
# ④ **分离锁（评审链 vs 供给链）的可行性：真交集只有一个文件。**
#     写集对比（实测到行）：
#       · 评审链   → `kb/.work/last_review_result.json`、`kb/l7/reports/*.review.md`、
#                    `kb/l7/runs/<RUN>.json` 与 `index.jsonl`、各层 `runs/<RUN>-L{4,5,6,7}.json`
#                    （`kb/l8/review_preflight.sh:174` 明写「记账完成 → kb/l7/runs/$RUN.json」）
#       · 供给链   → `SYNC_ALLOWED = L1..L6`（`kb_pipeline.py:294`），层引擎写
#                    `kb/<layer>/runs/<RUN>*.json`（`:573` 明写）
#     ⇒ **同文件冲突只有 `kb/l7/runs/index.jsonl`**（append-only，两边都写）；
#       其余是**同目录、不同文件名**（`<RUN>-L4.json` vs `<RUN>.json`）⇒ 不冲突。
#     ⇒ 三个选项：④-1 维持单槽（现状，零风险但用户会撞库忙）／
#                ④-2 分锁 + 用文件锁串行化写 index.jsonl／
#                ④-3 **分锁 + 索引分区**（评审链写 `index.review.jsonl`）← **推荐**
#       选 ④-3 的理由：它把「唯一真交集」变成「两个文件」，**不需要引入锁原语**；
#       代价＝读索引的消费点要合并两个文件（**先普查有几个**，未做）。
#     ⚠️ **不建议现在做**：当天只有 **2 次** `claim_busy`，样本太小。
#       先用本文件这本留痕账把量做出来（跑 `history` 看 `held_sec` 与 `refused_busy` 分布），
#       观察一两周再定。**不量就改**是这条循环上反复踩过的坑。
LEDGER = KB / ".work" / "claim-ledger.ndjson"


def _ledger(op, result, **extra) -> None:
    try:
        LEDGER.parent.mkdir(parents=True, exist_ok=True)
        rec = {"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "at_ts": time.time(),
               "op": op, "result": result,
               "session": os.environ.get("DSH_SESSION_ID") or "unknown",
               "host": socket.gethostname()}
        rec.update(extra)
        with LEDGER.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False, sort_keys=True) + "\n")
    except Exception as e:                                  # noqa: BLE001
        print("⚠️ 认领留痕写失败（**不影响认领本身**）：%s" % e)


def _holder_of(c: dict) -> dict:
    """把「占着的那个人」抽成留痕字段 —— 这正是「谁占的」要回答的。"""
    return {"holder_session": c.get("session"), "holder_base": c.get("base"),
            "holder_pid_kind": c.get("pid_kind"),
            "holder_age_min": round(_age_min(c), 2),
            "holder_since": c.get("at")}



def cmd_claim(a) -> int:
    """认领**一个 RUN**（★ 2026-10-08 起按 RUN 分槽，见 `_read_claims()` 头注）。

    ★ 判定只看 `claims[a.base]` 这一条 —— **别的 RUN 的认领不参与判定**。
      这就是「你改库 / 日更时守衡不再库忙」的全部机制：两者的 RUN 永远不同名
      （评审 = `YYYYMMDD-HHMM`，供给 = `daily-YYYYMMDD-HHMM`），所以谁也挡不住谁。
      而**同一个 RUN** 的互斥**一个字没松** —— 那才是 2026-10-03 双计事故的形状。
    """
    claims, bad = _read_claims()
    if bad:
        print("🚫 认领文件读不出（%s）—— 先人工看一眼再决定" % CLAIM)
        return 3
    cur = claims.get(a.base)
    if cur:
        stale, why = _stale(cur)
        mine = _mine(cur, a.session)
        if not mine:
            # ★ `--take-over` 必须**在这里**生效：跨会话接手才是它的唯一用途
            #   （上一个会话崩了 → 新会话的 session/pid 必然都不同 ⇒ 走不进 mine 分支）。
            #   默认仍然拒（别抢）；只有「陈旧」+ 显式 --take-over 才放行，并打印接管告警。
            if not (stale and a.take_over):
                print("🚫 **这个 RUN 已被占用** —— 别抢：" + _describe(cur))
                if stale:
                    print("   它是**陈旧**的（%s）。确认没有别人的活还在跑，再加 --take-over 接手。" % why)
                else:
                    # ★ 2026-10-08（Owner 同意 ③）：**被拒时要给下一步，不能只报「别抢」。**
                    #   ★ 同日晚些时候（① 落地后）这条分支的**触发面已经很小**：只有
                    #     「**正好跑同一个 RUN**」才会走到这儿（此前是"任何别的 RUN"）。
                    left = max(0.0, float(cur.get("ttl_min") or 45) - _age_min(cur))
                    print("   → **建议**：这是**同一个 RUN**，同一时间只准一个会话跑它。")
                    print("     · 等它跑完（它自己会 release）；")
                    print("     · 或等到陈旧阈值（还有约 %.0f 分钟；届时 `--take-over` 或由就绪巡检自愈）" % left)
                    print("     · 想看「今天被占了几次、谁占的、占了多久」：`kb_loop_claim.py history`")
                    print("     · **不要**为此撬槽 —— 同一 RUN 两会话同跑会双计（项目有实测事故记录）")
                _ledger("claim", "refused_busy", base=a.base, stale=bool(stale),
                        stale_why=why, **_holder_of(cur))
                return 3
            print("⚠️ **接管**别人的陈旧认领：" + _describe(cur))
            print("   陈旧原因：%s —— 确认过没有别人的活还在跑才走到这里。" % why)
            _ledger("claim", "take_over", base=a.base, stale_why=why, **_holder_of(cur))
        if stale and not a.take_over:
            print("⚠️ 你自己的认领已陈旧；继续请加 --take-over（或先 release）")
            _ledger("claim", "refused_own_stale", base=a.base, stale_why=why, **_holder_of(cur))
            return 3
    # ★ `pid` 记的必须是**持有者**的 pid（2026-10-06）。
    #   默认仍是 `os.getpid()`（认领进程自己），但那样记下来的 pid **写完就死**，
    #   拿它判存活必然把「正在跑」读成「崩了」—— 见 `_stale()` 的头注。
    #   所以同时记 `pid_kind`：`holder` 才参与存活判定，`claimer` 只当追溯线索。
    holder = getattr(a, "holder_pid", None)
    rec = {"session": a.session or os.environ.get("DSH_SESSION_ID") or "unknown",
           "pid": int(holder) if holder else os.getpid(),
           "pid_kind": "holder" if holder else "claimer",
           "base": a.base, "ttl_min": a.ttl,
           "at": time.strftime("%Y-%m-%dT%H:%M:%S"), "at_ts": time.time(),
           "host": socket.gethostname()}
    others = [b for b in claims if b != a.base]
    claims[a.base] = rec
    _write_claims(claims)
    _ledger("claim", "ok", base=a.base, pid_kind=rec["pid_kind"], ttl_min=a.ttl,
            holder_pid=(int(holder) if holder else None), concurrent_bases=len(others))
    print("✅ 已认领：" + _describe(rec))
    if others:
        # 可见性：按 RUN 分槽之后，**并存**是正常的，但要说出来（免得读日志的人以为串了）
        print("   ℹ️ 同时还有 %d 个别的 RUN 在跑（按 RUN 分槽 ⇒ 互不阻塞）：%s"
              % (len(others), ", ".join(sorted(others)[:4])))
    if not holder:
        print("   ⚠️ 没给 `--holder-pid` ⇒ 记的是**认领进程自己的 pid**（写完即退）⇒ "
              "陈旧判定**不会**用 pid，只看 TTL。长任务请让持有者传 `--holder-pid $$`。")
    print("   跑完请 `release --base %s`；中途被别人看到会读到这条记录。" % a.base)
    return 0


def cmd_release(a) -> int:
    """释放认领。★ 2026-10-08 起是**按 RUN** 的，三种调用形态各有明确语义：

      · `--base X`            ⇒ 释放 X 这一条（鉴权：是你的，或带 `--force`）；
      · 不给 `--base`、不给 `--force` ⇒ 释放**你自己的全部**认领；
      · 不给 `--base`、给 `--force`   ⇒ **只释放已陈旧的**（就绪巡检与守衡自愈走这条）。

    ★ 最后一条是**故意收窄**的：`--force` 在全局单槽时代等价于「把唯一那条拆掉」，
      映射化之后「全拆」会顺手拆掉**别人正在跑的活** ⇒ 无 base 的 `--force`
      **不碰活着的认领**（要拆活的必须点名 `--base`）。
    """
    claims, bad = _read_claims()
    if bad:
        print("⚠️ 认领文件读不出，没法安全释放")
        return 3
    if not claims:
        print("无认领可释放")
        return 0

    sess = a.session or os.environ.get("DSH_SESSION_ID")
    if a.base:
        if a.base not in claims:
            print("无认领可释放（`%s` 名下没有认领）" % a.base)
            return 0
        targets = [a.base]
    elif a.force:
        targets = [b for b, c in claims.items() if _stale(c)[0]]
        if not targets:
            print("🚫 **拒绝**：`--force` 但不给 `--base` 只释放**已陈旧**的，"
                  "而现在 %d 条认领**全都还活着** —— 要拆活的必须点名 `--base <RUN>`。"
                  % len(claims))
            for b, c in sorted(claims.items()):
                print("     %-24s %s" % (b, _describe(c)))
            return 3
    else:
        targets = [b for b, c in claims.items() if _mine(c, sess)]

    if not targets:
        one = next(iter(claims.values()))
        print("🚫 这条认领不是你的（%s）—— 要强拆加 `--base <RUN> --force`" % _describe(one))
        _ledger("release", "refused_not_mine", base=None, **_holder_of(one))
        return 3

    for b in sorted(targets):
        c = claims.pop(b)
        mine = _mine(c, sess)
        held = round(time.time() - float(c.get("at_ts") or time.time()), 1)
        _ledger("release", "force" if (a.force and not mine) else "ok",
                base=b, held_sec=held, **_holder_of(c))
        print("✅ 已释放（%s）｜这次持有了 %.1f 秒" % (b, held))
    _write_claims(claims)
    if claims:
        print("   ℹ️ 还剩 %d 条别的 RUN 的认领（不动它们）：%s"
              % (len(claims), ", ".join(sorted(claims))))
    return 0


def cmd_history(a) -> int:
    """把留痕账读成**能回答「这条循环被占了多少」**的几个数。

    为什么单开一个子命令：留痕是 ndjson（给机器），而问「今天库忙几次、谁占的、
    占了多久」的是**人**。让人去 grep ndjson 等于没做 ①。
    """
    import collections
    if not LEDGER.exists():
        print("留痕账还不存在：%s" % LEDGER)
        print("  （认领留痕 2026-10-08 才加；此前的认领没有历史，查不到不代表没发生）")
        return 0
    since = time.time() - float(a.days) * 86400
    rows = []
    for line in LEDGER.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
        except Exception:                                    # noqa: BLE001
            continue
        if float(d.get("at_ts") or 0) >= since:
            rows.append(d)
    print("认领留痕（最近 %s 天）｜%s" % (a.days, LEDGER))
    if not rows:
        print("  这段时间**没有**认领状态变更。")
        print("  ⚠️ 注意：『没有记录』≠『没被占过』 —— 留痕从 2026-10-08 才开始。")
        return 0
    c = collections.Counter((r.get("op"), r.get("result")) for r in rows)
    for (op, res), n in sorted(c.items()):
        print(f"  {op:<10} {res:<20} {n}")
    held = [float(r["held_sec"]) for r in rows if r.get("held_sec") is not None]
    if held:
        held_sorted = sorted(held)
        print(f"  ── 持有时长：{len(held)} 次 ｜ 合计 {sum(held):.0f}s ｜ "
              f"最长 {max(held):.0f}s ｜ 中位 {held_sorted[len(held_sorted)//2]:.0f}s")
    busy = [r for r in rows if r.get("result") == "refused_busy"]
    if busy:
        print(f"  ── 被挡（refused_busy）{len(busy)} 次，占用者分布：")
        for k, n in collections.Counter(
                (r.get("holder_session"), r.get("holder_base")) for r in busy).most_common(5):
            print(f"       {n:>3} 次  {k[0]} ｜ BASE {k[1]}")
    tail = rows[-int(a.tail):]
    print(f"  ── 最近 {len(tail)} 条：")
    for r in tail:
        print(f"     {r.get('at')}  {r.get('op')}/{r.get('result')}"
              + (f"  持有 {r['held_sec']}s" if r.get("held_sec") is not None else "")
              + (f"  BASE={r.get('base')}" if r.get("base") else ""))
    return 0


def selftest() -> int:
    """陈旧判据自证：**「正在跑」与「崩了」必须分得开**。全部离线。

    ★ 样本不是编的：前两条**逐字取自两次真实事故**（就绪巡检日志里那两行原文）。
      后两条是一对**相反**的构造样本 —— 缺了它们，把判据改成「永远不陈旧」也会全绿。
    """
    P, F = [], []

    def chk(name, cond, extra=""):
        (P if cond else F).append(name)
        print(f"  {'✅' if cond else '❌'} {name}{('  ' + extra) if extra else ''}")

    def mk(pid, age_min, kind=None, ttl=45):
        c = {"session": "unknown", "pid": pid, "base": "daily-x",
             "ttl_min": ttl, "at_ts": time.time() - age_min * 60}
        if kind:
            c["pid_kind"] = kind
        return c

    DEAD = 999999           # 一个几乎不可能存在的 pid
    LIVE = os.getpid()      # 本进程，必然活着

    # ① 真实事故 1：2026-10-05 10:12:12 —— 巡检把 daily-20261005-0957 的认领判成陈旧
    #    原文：陈旧（可 --take-over）：pid 已不在且已过宽限期（13 分钟）｜pid=41445
    st, why = _stale(mk(41445, 13))
    chk("① 真事故 2026-10-05（pid 已死 13 分钟，旧认领）⇒ **不陈旧**", st is False, f"why={why!r}")

    # ② 真实事故 2：2026-10-06 08:35:46 —— 同一天同一形状（pid=84706，6 分钟）
    st, why = _stale(mk(84706, 5.7))
    chk("② 真事故 2026-10-06（pid 已死 5.7 分钟，旧认领）⇒ **不陈旧**", st is False, f"why={why!r}")

    # ③ 新式认领 + 持有者**活着** ⇒ 不陈旧（即使跑了半小时）
    st, why = _stale(mk(LIVE, 30, kind="holder"))
    chk("③ pid_kind=holder 且持有者活着（30 分钟）⇒ **不陈旧**", st is False, f"why={why!r}")

    # ④ ★ 反向对照：新式认领 + 持有者**真的死了** ⇒ 必须陈旧。
    #    没有这一条，把 pid 判定整个删掉也能让 ①②③ 全绿 —— 那就是把判据放宽，不是修好。
    st, why = _stale(mk(DEAD, 6, kind="holder"))
    chk("④ 反向对照：pid_kind=holder 且持有者真死（6 分钟）⇒ **必须陈旧**", st is True, f"why={why!r}")

    # ⑤ TTL 仍是主判据：持有者活着但超了 TTL ⇒ 陈旧
    st, why = _stale(mk(LIVE, 46, kind="holder"))
    chk("⑤ 持有者活着但超 TTL（46 > 45）⇒ **必须陈旧**", st is True, f"why={why!r}")

    # ⑥ ③ 与 ④ 必须给出**相反**的结论 —— 否则「分得开」是假的
    chk("⑥ 「持有者活着」与「持有者真死」结论必须相反",
        _stale(mk(LIVE, 30, kind="holder"))[0] != _stale(mk(DEAD, 30, kind="holder"))[0])

    # ⑦ `ttl_min=0` 是合法值（立刻可接管），不许被 `or 45` 吃掉
    st, why = _stale(mk(LIVE, 0.5, kind="holder", ttl=0))
    chk("⑦ ttl_min=0 ⇒ 立刻陈旧（不许被默认值 45 吃掉）", st is True, f"why={why!r}")

    # ══════════════════════════════════════════════════════════════════════
    # ⑧–⑬ **按 RUN 分槽**（2026-10-08 ①；Owner：「这是个bug」）
    # ★ 全部落在临时目录：`CLAIM` / `LEDGER` 在下面被改指走 ⇒ **不碰真库的认领文件**。
    # ★ ⑩ 是 ① 的核心，它必须配 ⑨ 这个反向对照 —— 只测「不同 RUN 放行」的话，
    #   把整个互斥删掉也能全绿，那就是把事故形状丢了。
    # ══════════════════════════════════════════════════════════════════════
    import contextlib
    import io
    import shutil
    import tempfile
    import types

    global CLAIM, LEDGER          # ← 不写这句，下面那两行赋值会把它们变成局部变量
    _d = tempfile.mkdtemp(prefix="claims_")
    _old_claim, _old_ledger = CLAIM, LEDGER
    _old_sess = os.environ.get("DSH_SESSION_ID")
    CLAIM = Path(_d) / ".kb-loop-claim.json"
    LEDGER = Path(_d) / "ledger.ndjson"
    os.environ["DSH_SESSION_ID"] = "session-SELFTEST-A"

    def call(fn, **kw):
        """跑一个子命令并把它的 stdout 收起来（自证输出才不会被命令输出淹掉）。"""
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = fn(types.SimpleNamespace(**kw)) if kw else fn()
        return rc, buf.getvalue()

    def claim(base, session=None, ttl=45, take_over=False, holder_pid=None):
        return call(cmd_claim, base=base, session=session, ttl=ttl,
                    take_over=take_over, holder_pid=holder_pid)

    def release(base=None, session=None, force=False):
        return call(cmd_release, base=base, session=session, force=force)

    try:
        # ⑧ 向后兼容：旧格式（一条扁平记录）必须读得出来
        CLAIM.write_text(json.dumps({"session": "s-old", "pid": 1, "pid_kind": "claimer",
                                     "base": "OLD-RUN", "ttl_min": 45, "at_ts": time.time(),
                                     "at": "x", "host": "h"}), encoding="utf-8")
        cl, bad = _read_claims()
        chk("⑧ 旧格式（扁平单条）读侧兼容", (not bad) and list(cl) == ["OLD-RUN"], str(cl))

        # ⑨ **同一个 RUN** 被别人占 ⇒ 必须拒（= 2026-10-03 双计事故的形状，一条没松）
        #   ★ 这里必须给 `holder_pid`：自证跑在**一个进程**里，而 `_mine()` 会拿
        #     `pid == os.getpid()` 认「是我的」—— 真实现场是两个进程，pid 天然不同。
        #     不给的话第二条会被误判成「自己的认领」⇒ 测不出互斥（第一版就是这么假绿的）。
        CLAIM.unlink(missing_ok=True)
        rc1, _ = claim("RUN-A", session="session-1", holder_pid=999999)
        rc2, out2 = claim("RUN-A", session="session-2", holder_pid=888888)
        chk("⑨ 同一个 RUN 被别的会话占 ⇒ **拒（exit 3）**（事故形状保住）",
            rc1 == 0 and rc2 == 3 and "这个 RUN 已被占用" in out2,
            f"第一次={rc1} 第二次={rc2}")

        # ⑩ ★ ① 的核心：**不同 RUN** 必须放行（改前这一步是 exit 3 = 守衡库忙）
        rc3, _ = claim("RUN-B", session="session-2", holder_pid=888888)
        cl, _ = _read_claims()
        chk("⑩ 不同 RUN ⇒ **放行**，且两条同时存在（★ 这就是「守衡不再库忙」的机制）",
            rc3 == 0 and set(cl) == {"RUN-A", "RUN-B"}, f"rc={rc3} claims={sorted(cl)}")

        # ⑪ 释放**只动点名的那一条**，不许顺手拆别人的
        rc4, _ = release(base="RUN-B", session="session-2")
        cl, _ = _read_claims()
        chk("⑪ release --base 只拆点名那条，别人的留着",
            rc4 == 0 and set(cl) == {"RUN-A"}, f"rc={rc4} claims={sorted(cl)}")

        # ⑫ status 文本契约：**有活着的时整段不许出现「陈旧」**
        #    （下游 `review_preflight.sh:106` 与就绪巡检都 grep「陈旧（可 --take-over）」）
        rc5, out5 = call(cmd_status)
        chk("⑫ 有活认领时 status **不含「陈旧」**（否则下游会把「有人跑」读成「可接手」）",
            rc5 == 3 and "陈旧" not in out5, out5.strip().splitlines()[0][:60])

        # ⑫b 全部陈旧 ⇒ **必须**出现「陈旧（可 --take-over）」（下游靠这句自愈）
        cl, _ = _read_claims()
        for b in cl:
            cl[b]["at_ts"] = time.time() - 46 * 60
        _write_claims(cl)
        rc6, out6 = call(cmd_status)
        chk("⑫b 全部陈旧 ⇒ status 含「陈旧（可 --take-over）」且 exit 0",
            rc6 == 0 and "陈旧（可 --take-over）" in out6, f"rc={rc6}")

        # ⑬ 反向对照：**无 base 的 `--force` 不许拆活着的**（映射化之后「全拆」会误伤别人）
        #    此刻 RUN-A 已陈旧（⑫b 把它改老了）、RUN-C 是活的。
        claim("RUN-C", session="session-3", holder_pid=777777)
        rc7, out7 = release(force=True)
        cl, _ = _read_claims()
        chk("⑬ `release --force`（无 base）**只拆陈旧的**，活着的 RUN-C 一个字不动",
            rc7 == 0 and set(cl) == {"RUN-C"}, f"rc={rc7} claims={sorted(cl)}")

        # ⑬b 反向对照的第二半：**没有陈旧的可拆时，必须拒**（否则它会顺手拆掉活着的）
        rc8, out8 = release(force=True)
        cl, _ = _read_claims()
        chk("⑬b 反向对照：没有陈旧的 ⇒ `--force` **拒绝**，RUN-C 仍在",
            rc8 == 3 and set(cl) == {"RUN-C"} and "拒绝" in out8, f"rc={rc8} claims={sorted(cl)}")
    finally:
        CLAIM, LEDGER = _old_claim, _old_ledger
        if _old_sess is None:
            os.environ.pop("DSH_SESSION_ID", None)
        else:
            os.environ["DSH_SESSION_ID"] = _old_sess
        shutil.rmtree(_d, ignore_errors=True)

    print(f"\n自证：通过 {len(P)} / 失败 {len(F)}")
    for x in F:
        print(f"  · 失败：{x}")
    return 1 if F else 0


def main() -> int:
    ap = argparse.ArgumentParser()
    # ★ `required=False`：`--selftest` 是**不带子命令**跑的。
    #   写成 required=True 时，`--selftest` 会被「缺少 cmd」挡在 argparse 层（exit 2）——
    #   而那种红**看起来像自证失败**，其实自证一次都没跑（§2.4.4 的形状）。
    sub = ap.add_subparsers(dest="cmd", required=False)
    sub.add_parser("status")
    c = sub.add_parser("claim")
    c.add_argument("--base", required=True)
    c.add_argument("--session", default=None)
    c.add_argument("--ttl", type=float, default=45, help="认领有效期（分钟），默认 45")
    c.add_argument("--take-over", action="store_true")
    # ★ 2026-10-06 加：**持有者**的 pid（长任务请传 `$$`）。
    #   不传 ⇒ 记认领进程自己的 pid ⇒ 那一格不参与陈旧判定（见 `_stale()` 头注）。
    c.add_argument("--holder-pid", type=int, default=None,
                   help="真正持有这次运行的进程 pid（shell 里写 $$）；不传则记认领进程自己的 pid")
    r = sub.add_parser("release")
    r.add_argument("--base", required=False)
    r.add_argument("--session", default=None)
    r.add_argument("--force", action="store_true")
    h = sub.add_parser("history", help="读认领留痕：被占多少次、谁占的、占了多久")
    h.add_argument("--days", type=float, default=2, help="回看天数（默认 2）")
    h.add_argument("--tail", type=int, default=10, help="明细打印条数（默认 10）")
    ap.add_argument("--selftest", action="store_true",
                    help="只跑陈旧判据自证（离线；喂真实认领样本，一次网络都不发）")
    a = ap.parse_args()
    if a.selftest:
        print("kb_loop_claim · 陈旧判据自证（离线）")
        return selftest()
    if not a.cmd:
        ap.print_help()
        return 2
    return {"status": lambda: cmd_status(), "claim": lambda: cmd_claim(a),
            "release": lambda: cmd_release(a), "history": lambda: cmd_history(a)}[a.cmd]()


if __name__ == "__main__":
    sys.exit(main())
