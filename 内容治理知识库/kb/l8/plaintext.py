#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""plaintext.py —— 「发到飞书去的正文里不许有 markdown 星号」在 **KB 侧**的唯一实现。

## 它补的是哪条腿（2026-10-16）

Owner 2026-10-14 定的规矩，逐字：

> 「守衡的**所有**输出中不允许包含 `**` 星号，修复后落库。」

当天那次修复落在**守衡进程**里：`tools/agent/plain.mjs::plainify()` + 5 个执行点
（`replyMarkdown` / `sendMarkdown` 降级支 / `sendTyping` / `sendTextWithMentions` /
卡片本体与纯文本视图）。唯一的判据 `tools/verify_outbound.py` 读的是
**守衡自己的出站台账** `PMO/logs/ws_outbound.jsonl`。

⇒ **它管不到 KB 侧的两条直发腿。** 这两个脚本用**同一个守衡 bot 身份**
（`lark-cli --as bot --profile dsh-kb`）把 `--text` 直接打给飞书，**不经过守衡进程**
⇒ 既不在那 5 个执行点里，也不进那份台账，**没有任何判据看得见它们**：

  · `kb/l8/daily_digest.py::send()`   —— 日更摘要（每天一条，进「内容治理-守衡Agent-测试」群）
  · `kb/l8/watch_review_readiness.py::alert()` —— 就绪/陈旧告警（私聊）

实测（2026-10-16）：`grep -c "日更报告" PMO/logs/ws_outbound.jsonl` = **0**
—— 日更摘要推了这么多天，**一次都没进过守衡台账**。而它在群里长这样：

    **记录层**：一致 1022 ｜ **新增 13** ｜ **下架 0** ｜ …

飞书把 `--text` 载荷按**纯文本**渲染 ⇒ 星号**字面**显示。Owner 当天报：
「下面的 `*` 没有去掉，昨天修复的这个问题没有落库吗？」—— 修的是守衡进程那 5 条腿，
**规则的作用域漏了「同一个 bot 身份、但不由守衡进程发出」的那一类出口**。

## 口径（照抄 `plain.mjs`，不自创）

替换链**逐字照** `tools/agent/plain.mjs::plainify()`，顺序即语义、别调：

    ① `**粗体**` → `粗体`（成对先吃）
    ② 落单的 `**` → 删干净
    ③ `*斜体*` → `斜体`
    ④ 剩下的孤星号 → 删
    ⑤ 行首 `#` 标题号 → 删（飞书 text 里也是字面符号）

**下划线不碰** —— `_italic_` 与 `user_id` / `kb_review_chain` 长得一样，
删下划线就是把**标识符**改坏，那是**改内容**，比格式难看严重得多。

## 为什么在**发送口**摘，而不是把 `render_push()` 改成不带星号

同 `plain.mjs` 的两条理由：① 出站口是**唯一收口**，以后新增调用方自动被覆盖；
② 摘的时候**报读数**，「谁一直在写星号」这件事才不会变成不可见的因
（静默清理 = 把要治的因藏起来）。

## 两份实现怎么办（本库栽过「同一判据算两遍必然分叉」）

KB 侧是 Python、守衡侧是 Node，跨仓**不在运行时互相依赖**（守衡仓不在时 KB 也要能推）。
所以这里**必然**存在第二份实现 ⇒ 必须配一把**互校尺子**：
`--selftest` 把同一批语料同时喂给本文件与**真** `plain.mjs`（node 跑），断言逐字一致。
读不到 `plain.mjs` 时报 **未测**，**不报绿**（本库纪律：判据恒绿 = 注释）。
路径可经 `KB_PLAIN_MJS` 指定；默认找 `~/Project/audit_multi_content/tools/agent/plain.mjs`。

## 用法

    from plaintext import plainify_for_send          # 调用方在 kb/l8/ 内，直接 import
    txt, n = plainify_for_send(text, where="daily_digest.send")
    left = has_md_symbols(txt)                       # 出站前最后一道，必须 False

自证：`python3 kb/l8/plaintext.py --selftest`
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys

#: 替换链的**每一条都是有意为之**，见模块头「口径」。别调顺序、别加 `_`。
_R_BOLD = re.compile(r"\*\*([^*\n]+)\*\*")
_R_ITALIC = re.compile(r"\*([^*\n]+)\*")
_R_HEADING = re.compile(r"^[ \t]*#{1,6}[ \t]+", re.M)

#: 守衡侧唯一实现的默认落点（跨仓互校用；读不到就是**未测**，不是失败）。
PLAIN_MJS_CANDIDATES = (
    os.environ.get("KB_PLAIN_MJS") or "",
    os.path.expanduser("~/Project/audit_multi_content/tools/agent/plain.mjs"),
)


def plainify(text) -> str:
    """把会被飞书渲染成**字面符号**的 markdown 标记摘掉（纯函数，逐字对齐 plain.mjs）。"""
    t = str(text if text is not None else "")
    t = _R_BOLD.sub(r"\1", t)          # ① **粗体** → 粗体
    t = t.replace("**", "")            # ② 落单的（写歪了也要删干净）
    t = _R_ITALIC.sub(r"\1", t)        # ③ *斜体* → 斜体
    t = t.replace("*", "")             # ④ 剩下的孤星号
    t = _R_HEADING.sub("", t)          # ⑤ 行首标题号
    return t


def has_md_symbols(text) -> bool:
    """出站前的**黑体断言**：还剩 `*` 吗。

    故意写得比 `plainify()` 严 —— 只认「一个 `*` 都没有」。
    替换链再全也只是**我们写的那几条正则**；这条断言不会漏掉「还有星号」这件事。
    """
    return "*" in str(text if text is not None else "")


def plainify_for_send(text, where="未命名调用点"):
    """出站正文的**唯一收口**：返回 `(摘干净的正文, 摘掉几个星号)`。

    只在真摘了东西时打一行 —— 正常回答（没有星号）不该刷日志。
    """
    src = str(text if text is not None else "")
    out = plainify(src)
    before = src.count("*")
    if out != src and before:
        print("[plain] · %s：摘掉 %d 个 markdown 星号"
              "（飞书 text 会把它显示成字面符号）" % (where, before))
    return out, before


def guard(text, where="未命名调用点"):
    """出站前的最后一道闸：`(能不能发, 理由)`。还有星号 ⇒ **不发**。

    ★ 为什么 fail-closed：Owner 的规矩是「一个 `*` 都不许」。构造上 `plainify()`
      的第 ④ 步会删光所有星号，所以这条**只可能在有人改了 `plainify()` 时才红** ——
      那时宁可当次不推、把正文原样打出来，也不要照旧把星号推到群里（那是**破规矩**，
      而破了规矩不会有任何人告诉你）。
    """
    n = str(text if text is not None else "").count("*")
    if n:
        return False, ("%s：出站正文里仍有 %d 个星号 ⇒ 按规矩**不发**"
                       "（`plainify()` 被改动过？看 kb/l8/plaintext.py 的替换链）" % (where, n))
    return True, "ok"


# ══════════════════════════════════════════════════════════════════════════
# 跨仓互校：与守衡侧 `plainify()` 逐字比（读不到 plain.mjs ⇒ 未测，不报绿）
# ══════════════════════════════════════════════════════════════════════════

#: 语料**逐字**取自真实出站正文的形状（README 里那几行、以及本库真推过的两段）。
PARITY_CORPUS = [
    "**记录层**：一致 1022 ｜ **新增 13** ｜ **下架 0** ｜ 值变 0 ｜ 拉取失败 —",
    "1. **能查的我查完再说** —— 表、工作区文件、知识库检索这些我有路；**查不到或者\n"
    "没跑成的，我会说「没查成」**，不会替它说成「没有」。",
    "⚠️ 守衡 · 审查链**当前不可用**（就绪巡检自动告警）",
    "   = 逐层 L0–L7 比「最近一次成功 RUN 距今」≤ **24.0h**（`layer_freshness.judge`）",
    "`user_id` 与 `kb_review_chain` 是**标识符**，下划线不许动",
    "落单的 ** 星号也要删干净",
    "*斜体* 与 **粗体** 混写：**a**(*b*)",
    "## 行首标题号要摘，正文中间的 # 不许动",
    "没有星号的一行：`kb/l7/registry/layers.yaml` 各层 engine 清单",
    "a * b ／ 3 * 4 = 12 ／ select * from t",
]


def _run_plain_mjs(corpus):
    """拿**真** `plain.mjs` 跑一遍语料 → `(结果列表, 未测理由)`。

    未测理由非空 ⇒ 调用方必须报「未测」，**不许当绿**。
    """
    path = next((p for p in PLAIN_MJS_CANDIDATES if p and os.path.exists(p)), None)
    if not path:
        return None, "读不到守衡侧 plain.mjs（找过：%s）" % "、".join(
            p for p in PLAIN_MJS_CANDIDATES if p)
    js = (
        "import { plainify } from %s;\n"
        "const cases = JSON.parse(process.argv[1]);\n"
        "console.log(JSON.stringify(cases.map((c) => plainify(c))));\n"
        % json.dumps("file://" + os.path.abspath(path))
    )
    try:
        p = subprocess.run(["node", "--input-type=module", "-e", js, json.dumps(corpus)],
                           capture_output=True, text=True, timeout=60, errors="replace")
    except Exception as e:                                      # noqa: BLE001
        return None, "跑不动 node/plain.mjs：%r" % e
    if p.returncode != 0:
        return None, "node 退出码 %d：%s" % (p.returncode, (p.stderr or "").strip()[:200])
    try:
        return json.loads(p.stdout.strip().splitlines()[-1]), None
    except Exception as e:                                      # noqa: BLE001
        return None, "plain.mjs 输出不是 JSON：%r（%s）" % (e, (p.stdout or "")[:200])


# ══════════════════════════════════════════════════════════════════════════

def selftest() -> int:
    ok = fail = untested = 0
    print("plaintext.py 自证（KB 侧出站正文：一个星号都不许有）")

    def chk(name, cond, extra=""):
        nonlocal ok, fail
        if cond:
            ok += 1
            print("  ✅ %s%s" % (name, ("  " + extra) if extra else ""))
        else:
            fail += 1
            print("  ❌ %s%s" % (name, ("  " + extra) if extra else ""))

    # ① 替换链：三种写法都要摘干净（照 test_agent.mjs 第 3 组「plainify」的形状）
    chk("① 成对 `**粗体**` → `粗体`", plainify("**粗体**") == "粗体")
    chk("①b 落单 `**` 也删干净（模型写歪了）", plainify("落单的 ** 星号") == "落单的  星号")
    chk("①c `*斜体*` → `斜体`", plainify("*斜体*") == "斜体")
    chk("①d 三个星号残留的写法都不许出现（`粗体**` / `**粗体` / `*粗体*`）",
        plainify("**a**(*b*)") == "a(b)" and not has_md_symbols(plainify("**a**(*b*)")))
    chk("①e 行首标题号摘掉", plainify("## 标题") == "标题")

    # ② ★ 反向对照：**下划线不许动**（`user_id` 是标识符 —— 摘它就是改内容）
    _u = "`user_id` 与 `kb_review_chain` 是标识符"
    chk("② **反向对照**：下划线一个字都不许动", plainify(_u) == _u,
        "把 `_` 也纳入替换链 ⇒ 本条精确变红")

    # ③ ★ 反向对照：**没有星号的正文必须原样**（尺子不许顺手改别的）
    _plain = "记录层：一致 1022 ｜ 新增 13 ｜ 拉取失败 —"
    chk("③ **反向对照**：本来没星号的正文逐字不变", plainify(_plain) == _plain)

    # ④ 断言本体：`has_md_symbols()` 认的是「一个 `*` 都没有」
    chk("④ `has_md_symbols()`：摘过的必须 False、没摘的必须 True",
        (not has_md_symbols(plainify("**x**"))) and has_md_symbols("**x**"))

    # ⑤ ★ 出站闸门**不是恒真**：真造一个「没摘干净」的输入，它必须精确拦下
    g_ok, _ = guard(plainify("**x**"), where="自证")
    g_bad, why = guard("**x**", where="自证")
    chk("⑤ 出站闸门：摘过的放行 ／ **没摘的必须拦下**（拆掉守卫 ⇒ 本条变红）",
        g_ok is True and g_bad is False and "星号" in why, why[:60])

    # ⑥ 真语料：把 README 里那句**逐字**的实例喂进去，出站必须一个星号都没有
    _real = ("1. **能查的我查完再说** —— 表、工作区文件、知识库检索这些我有路；"
             "**查不到或者没跑成的，我会说「没查成」**，不会替它说成「没有」。")
    chk("⑥ 逐字真实样本：摘完 0 星号，且内容一个字没丢",
        not has_md_symbols(plainify(_real)) and "没查成" in plainify(_real))

    # ⑦ 跨仓互校：与守衡侧 `plainify()` 逐字一致（读不到 ⇒ **未测**，不报绿）
    theirs, why = _run_plain_mjs(PARITY_CORPUS)
    if theirs is None:
        untested += 1
        print("  ⚠️ 未测 ⑦ 与守衡侧 `plain.mjs` 逐字互校 —— %s" % why)
        print("        （**未测不是绿**：这条腿今天没有被量过。）")
    else:
        mine = [plainify(c) for c in PARITY_CORPUS]
        diff = [(i, c, a, b) for i, (c, a, b) in enumerate(zip(PARITY_CORPUS, mine, theirs))
                if a != b]
        chk("⑦ 与守衡侧 `plain.mjs` 在 %d 条语料上**逐字一致**" % len(PARITY_CORPUS),
            not diff, ("分歧：%s" % diff[:2]) if diff else "")

    print("\n自证：通过 %d / 失败 %d%s"
          % (ok, fail, ("／**未测 %d**" % untested) if untested else ""))
    return 0 if fail == 0 else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="KB 侧出站正文的 markdown 星号收口")
    ap.add_argument("--selftest", action="store_true", help="判据自证（含与守衡 plain.mjs 的互校）")
    ap.add_argument("--plainify", metavar="TEXT", help="就地看一眼摘完长什么样（只读）")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    if a.plainify is not None:
        out, n = plainify_for_send(a.plainify, where="--plainify")
        print(json.dumps({"in": a.plainify, "out": out, "stripped": n,
                          "still_has_md": has_md_symbols(out)}, ensure_ascii=False, indent=1))
        return 0
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
