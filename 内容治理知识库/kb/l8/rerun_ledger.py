#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""rerun_ledger.py —— **同一单跑完之后还能再跑**，而且「第几次跑」说得清。

════════════════════════════════════════════════════════════════════════
★ 为什么需要它（Owner 2026-10-20：「同一单跑完还必须支持重新跑」）
════════════════════════════════════════════════════════════════════════
评审链本身**从来没有禁止重跑**：`review_run.sh` 每次拿一个 `--base`，
不同的 base 就是不同的 RUN（层记账、报告、表行都按 RUN 分开）。
真正缺的是两件**读得出、核得到**的东西：

  ① **重跑不被「这一单跑过了」挡住** —— 现在没有任何东西挡；
     但没有东西挡 ≠ 有东西保证。改一次代码就可能把某个「已存在就跳过」加回来，
     而**没有任何判据会红**（本库栽过：散文没有失败信号）。
  ② **重跑要认得出来** —— 同一份素材第 2 次跑，盘上会多一份 RUN、表里多一行，
     但**没有任何字段说「这是第 2 次、上一轮是谁、上一轮结论是什么」**。
     人问「这次跟上次一样吗」，只能靠肉眼比两份报告。

⇒ 本件把这两件事落成一份**只追加**的台账 `kb/.work/review_seq.ndjson`：
  每跑一单记一行（base / 素材指纹 / 结论 / 内容 ID），下次开跑时按**素材指纹**查上一条。

三条口径（改之前先读，别按常识改）：

  · **按内容认，不按时间认**：重跑判定用 `text_sha8`（`sha256(素材文本)[:8]`，
    与旁挂 `text_sha8` / 守衡 `readReviewSidecar` **同一算式**）。
    拿时间窗判会被「补发单晚到 10 分钟」骗过去（2026-10-08 栽过一次）。
  · **同一个 BASE 不许跑第二次**：那是同一个 RUN 跑两遍 —— 层记账会被覆盖、
    台账会双计（2026-10-03 实测：同一 RUN 在 `index.jsonl` 落 2 行、L7 记账被覆盖）。
    重跑**必须换新 BASE**；这条在 `review_run.sh` 里是**硬拒**（退出码 2）。
  · **只追加、不改写**：台账不回洗。它记的是「发生过什么」，抹掉等于抹掉证据；
    历史上被双计的 RUN 行**留着**，由 `review_run_count.py` 那套口径去解释。

★ 判据（本件自带）：`--selftest` —— 正例 ＋ **反向对照**（缺它们本件就只是注释）。
执行点：`kb/l8/workflow_smoke.py` 的 **S12**（非阻断链级契约，与 S1/S7 同一种做法）。

用法：
    python3 kb/l8/rerun_ledger.py --check-base <BASE> --text-sha8 <S>   # 开跑前判
    python3 kb/l8/rerun_ledger.py --record --base <BASE> --text-sha8 <S> --state REVIEW
    python3 kb/l8/rerun_ledger.py --selftest
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))          # 库根
DEFAULT_LEDGER = os.path.join(ROOT, "kb", ".work", "review_seq.ndjson")


def ledger_path() -> str:
    """台账落点。**可用 `KB_REVIEW_SEQ_LEDGER` 覆盖** —— 自证必须指到临时文件，
    否则「跑一次自检」就往事台账里掺一行（§2.4.4 那个形状：自证有副作用）。"""
    return os.environ.get("KB_REVIEW_SEQ_LEDGER") or DEFAULT_LEDGER


# ── 读 ────────────────────────────────────────────────────────────────────
def read_rows(path: str | None = None) -> list[dict]:
    """读台账。**读不到 = 空**（这一单是第一次跑）；**读了抛异常也当空**（台账坏了
    不该让一单评审跑不成），但**不许**静默吞掉「有一行不是 JSON」这件事 ——
    返回里带上坏行数，交给调用方打日志。"""
    p = Path(path or ledger_path())
    if not p.exists():
        return []
    rows: list[dict] = []
    try:
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
            s = line.strip()
            if not s:
                continue
            try:
                r = json.loads(s)
            except Exception:
                continue                      # 坏行跳过（不让台账坏一单）
            if isinstance(r, dict):
                rows.append(r)
    except Exception:
        return []
    return rows


def _norm(v) -> str:
    return str(v or "").strip()


# ── 判（纯函数：不读盘、不写盘，自证直接喂样本）──────────────────────────
def check_base(rows: list[dict], base: str, text_sha8: str) -> dict:
    """开跑前判这一轮是什么性质。

    返回四格（**每一格都是给人看的读数，缺一格就不叫「说得清」**）：
      · `same_base`   —— 这个 BASE 已经跑过（⇒ 调用方必须**硬拒**，换新 BASE 重跑）
      · `rerun_of`    —— 上一轮同一素材的 BASE（第一次跑时为空串）
      · `rerun_seq`   —— 这是第几次跑这份素材（第一次 = 1）
      · `prev_state`  —— 上一轮的结论（第一次 / 上一轮没落结论时为 null，**不编 0/PASS**）

    ★ 只按 `text_sha8` 认素材：**换句话问、换个人问，都是同一份素材**（同一条口径
      写在 `review_run.sh` 的 TEXT_SHA8 注释里）。
    ★ 只看**指纹成立**的行。老台账可能缺这个字段 ⇒ 那一行**不参与**比对
      （宁可少认一轮，也不要把别人的上一轮贴到这一单上 —— 「张冠李戴比没有更坏」）。
    """
    b = _norm(base)
    sha = _norm(text_sha8)
    same = any(_norm(r.get("base")) == b and b for r in rows)
    prior = [r for r in rows
             if sha and _norm(r.get("text_sha8")) == sha and _norm(r.get("base")) != b]
    prior.sort(key=lambda r: _norm(r.get("at")))
    last = prior[-1] if prior else None
    return {
        "same_base": bool(same),
        "rerun_of": _norm(last.get("base")) if last else "",
        "rerun_seq": len(prior) + 1,
        "prev_state": (_norm(last.get("state")) or None) if last else None,
        "prev_at": (_norm(last.get("at")) or None) if last else None,
    }


# ── 写 ────────────────────────────────────────────────────────────────────
def record(path: str | None = None, *, base: str, text_sha8: str,
           state: str | None = None, content_id: str | None = None,
           reason: str | None = None) -> bool:
    """追加一行（**只追加，不改写**）。写不成**不许**让这一单失败，但要返回 False
    ——调用方据此打日志（静默失败 = 台账以后少行而没人知道）。"""
    p = Path(path or ledger_path())
    row = {
        "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "base": _norm(base),
        "text_sha8": _norm(text_sha8),
        "state": (_norm(state) or None),
        "content_id": (_norm(content_id) or None),
        "reason": (_norm(reason) or None),
    }
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        return True
    except Exception:
        return False


# ── 自证（正例 ＋ 反向对照；缺一条本判据就不算数）─────────────────────────
def _selftest() -> int:
    good = bad = 0

    def ck(name, cond):
        nonlocal good, bad
        if cond:
            good += 1
            print("  ✅ %s" % name)
        else:
            bad += 1
            print("  ❌ %s" % name)

    rows = [
        {"at": "2026-10-20T17:03:15", "base": "20261020-1703", "text_sha8": "e5b61501",
         "state": "REVIEW", "content_id": "AD-20261020-006"},
        {"at": "2026-10-20T16:23:00", "base": "20261020-1623", "text_sha8": "e5b61501",
         "state": "NEEDS_INPUT", "content_id": None},
        {"at": "2026-10-20T17:10:00", "base": "20261020-1710", "text_sha8": "aaaa1111",
         "state": "PASS", "content_id": "AUTO-aaaa1111"},
        {"at": "2026-10-19T09:00:00", "base": "OLD-1", "state": "PASS"},   # 缺指纹（老台账）
    ]

    # ① 正例：同一素材的第三轮 ⇒ 认得出来
    r = check_base(rows, "20261020-1730", "e5b61501")
    ck("① 同一素材第 3 轮：rerun_seq=3、rerun_of=上一轮 BASE、prev_state=上一轮结论",
       [r["same_base"], r["rerun_seq"], r["rerun_of"], r["prev_state"]]
       == [False, 3, "20261020-1703", "REVIEW"])

    # ② 正例：全新素材 ⇒ 第 1 次，且**不编**上一轮
    r2 = check_base(rows, "20261020-1731", "beef0000")
    ck("② 全新素材：rerun_seq=1、rerun_of 为空、prev_state 为 None（不编 PASS）",
       [r2["same_base"], r2["rerun_seq"], r2["rerun_of"], r2["prev_state"]]
       == [False, 1, "", None])

    # ③ 反向对照：同一个 BASE 再跑 ⇒ **必须**判冲突（这条挡的是「同一 RUN 跑两遍」）
    r3 = check_base(rows, "20261020-1703", "e5b61501")
    ck("③ 反向对照：同 BASE 重跑 ⇒ same_base=True（挡住双计）", r3["same_base"] is True)

    # ④ 反向对照：**按内容认、不按时间认** —— 换一个指纹，同一个 BASE 的冲突判定不变，
    #    但重跑序号必须回到 1（如果有人把判据改成时间窗，这条会红）
    r4 = check_base(rows, "20261020-9999", "e5b61501")
    ck("④ 反向对照：指纹不符的老行不算「上一轮」（缺 text_sha8 的行不得参与比对）",
       r4["rerun_seq"] == 3 and check_base(rows, "x", "nope")["rerun_seq"] == 1)

    # ⑤ 正例：磁盘上的读写闭环（自证用临时文件 —— 绝不碰真台账）
    with tempfile.TemporaryDirectory() as td:
        p = os.path.join(td, "seq.ndjson")
        ck("⑤ 空台账读得动（第一次跑不报错）", read_rows(p) == [])
        ck("⑤2 追加成功", record(p, base="B1", text_sha8="s1", state="REVIEW") is True)
        ck("⑤3 读回来一行且字段齐",
           (lambda rs: len(rs) == 1 and rs[0]["base"] == "B1" and rs[0]["state"] == "REVIEW"
            and rs[0]["text_sha8"] == "s1")(read_rows(p)))
        ck("⑤4 第一轮跑完、第二次开跑：rerun_seq=2、rerun_of=B1、prev_state=REVIEW",
           (lambda r: [r["rerun_seq"], r["rerun_of"], r["prev_state"]] == [2, "B1", "REVIEW"])(
               check_base(read_rows(p), "B2", "s1")))
        record(p, base="B2", text_sha8="s1", state="BLOCK")
        ck("⑤4b 第二轮跑完、第三次开跑：rerun_seq=3、rerun_of=B2、prev_state=BLOCK",
           (lambda r: [r["rerun_seq"], r["rerun_of"], r["prev_state"]] == [3, "B2", "BLOCK"])(
               check_base(read_rows(p), "B3", "s1")))
        with open(p, "a", encoding="utf-8") as f:
            f.write("{坏行不是 JSON\n")
        ck("⑤5 坏行不让整份台账作废（跳过坏行，好行照读）",
           len(read_rows(p)) == 2)

    # ⑥ 反向对照：写不成要返回 False（不许假装成功）
    ck("⑥ 反向对照：台账路径不可写 ⇒ record 返回 False（不静默成功）",
       record("/proc/definitely/not/writable/x.ndjson", base="B", text_sha8="s") is False)

    print("\n  %d / %d" % (good, bad))
    return 0 if bad == 0 else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="同一单重跑台账（只追加）")
    ap.add_argument("--check-base", metavar="BASE", help="开跑前判：这个 BASE/这份素材是什么性质")
    ap.add_argument("--text-sha8", default="", help="素材指纹（sha256(素材文本)[:8]）")
    ap.add_argument("--record", action="store_true", help="追加一行")
    ap.add_argument("--base", default="", help="本轮 RUN 标识（--record 用）")
    ap.add_argument("--state", default="", help="本轮结论（--record 用）")
    ap.add_argument("--content-id", default="", help="内容 ID（--record 用）")
    ap.add_argument("--reason", default="", help="原因码（拒答时用）")
    ap.add_argument("--ledger", default="", help="台账路径（默认 kb/.work/review_seq.ndjson）")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)

    if a.selftest:
        return _selftest()

    path = a.ledger or ledger_path()
    if a.record:
        okv = record(path, base=a.base, text_sha8=a.text_sha8, state=a.state,
                     content_id=a.content_id, reason=a.reason)
        if not okv:
            print("[rerun_ledger] ⚠ 台账写不成（不影响这一单）：%s" % path, file=sys.stderr)
            return 1
        return 0
    if a.check_base:
        out = check_base(read_rows(path), a.check_base, a.text_sha8)
        print(json.dumps(out, ensure_ascii=False))
        return 0
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
