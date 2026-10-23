#!/usr/bin/env python3
"""内容 ID（PRD §5.4 业务编号 `AD-YYYYMMDD-NNN`）—— **发号的唯一实现**。

## 为什么要有这个模块

2026-10-03 那次裁定把**发布侧**改成了业务编号（`applied_20261003.content_id_business_number`），
但它自己就登记了遗留项：

> `residual`: 引擎侧 `_auto_content_id()` 未动 ⇒ 同一次审查存在两个 ID
> （`AUTO-…` 引擎/本地报告 ／ `AD-…` 表行/云文档）。

实际情况（2026-10-10 逐处核 + 只读真表实测）：

| 位置 | 原形态 |
|---|---|
| `review.py:1568` | `text-<sha12>` |
| `with_kb_evidence.py` 的 `_auto_content_id` | `AUTO-<sha12>`（内容哈希） |
| `feishu_publish.py` | `AD-YYYYMMDD-NNN`，但写在 `if not a.content_id:` 里 |

⚠️ **我最初的推断被实测否掉了**：曾以为「引擎每次都传 content_id ⇒ 发布件那段是死代码
⇒ 表里全是哈希」。**只读真表：89 行里 68 个 `AD-` 业务号、21 个 `AUTO-` 哈希**
（最早 `AD-20261008-001`）⇒ 那段**一直在跑**，说明有入口没带 content_id。

⇒ 准确的病灶是：**同一件事的形态取决于「谁调、带没带 content_id」**，
**不存在**一个统一的口径。本模块把发号收成一份，让三条路都指向它。

所以把**发号**收成一个模块，三处共用 —— **不许在别处再写第二份**。

## 裁定口径（逐字取自 `report-output-contract.yaml::applied_20261003.content_id_business_number`）

| 项 | 口径 | 来源 |
|---|---|---|
| 形态 | `AD-<YYYYMMDD>-<NNN>`，NNN 三位零填充 | PRD §5.4 示例 `AD-20260922-001` |
| 序号 | 按天自增，**表内已有行**同日前缀最大序号 + 1（无需额外台账） | 同上 |
| 复用 | **永不复用** | 同上 |
| 历史行 | **不改、不重编号** —— `AUTO-…` / `text-…` 原样保留 | 同上 `history_untouched` |
| 原提问词 | **不进 ID**（ID 是表主键与统计维度，按 PRD §5.4 是纯编号） | 同上 `not_inside_id` |

### ⚠️ 已知边界（照抄，别当没看见）

`+record-list` **有分页上限**：表行数极大时序号推导可能偏小（届时改为台账发号）。
⇒ 本模块对「推导不出序号」**不编一个号**，返回 `None` + 原因，由调用方决定怎么办。

## 「不编」这条怎么落

- 发号要读飞书表。**读不到**（没权限 / 没网 / `lark-cli` 不在）⇒ **不编号**，返回 `None` + 原因。
- **不发飞书**的场合（`--no-publish-to-feishu`）⇒ 不去发表、也就不需要号；
  此时报告里用**内容指纹形态**（`AUTO-<sha12>`）并在 `content_id_basis` 里写明
  「本单不发飞书，故不发业务号」—— 让人看得出这不是漏发。

## 用法

    python3 kb/l7/review-engine/core/content_id.py --selftest     # 判据自证（不碰真表）
    python3 kb/l7/review-engine/core/content_id.py --peek         # 只读：看下一个号会是什么
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time

#: 形态真源（PRD §5.4）。**别在别处再写一条正则。**
FORM_RE = re.compile(r"^AD-(\d{8})-(\d{3})$")

#: 发不出去时用的指纹形态。**它不是内容 ID**，是「本单没有业务号」的可见标记。
FALLBACK_PREFIX = "AUTO-"

#: 读表分页（2026-10-20 加）。`lark-cli base +record-list` 默认只回 **100 行**，
#: json 格式上限 200；不翻页 ⇒ 只看得见最早那 100 行 ⇒ 当天的新号一个都看不见 ⇒ 恒发 001。
_PAGE_LIMIT = 200

#: 翻页保险：服务端 `has_more` 抽风时不把发号拖死。
_MAX_PAGES = 200


def is_business_id(v) -> bool:
    """是不是 PRD §5.4 的业务编号形态。"""
    return bool(FORM_RE.match(str(v or "").strip()))


def format_id(day: str, seq: int) -> str:
    """按 PRD §5.4 拼号。`day` = `YYYYMMDD`。"""
    return "AD-%s-%03d" % (str(day), int(seq))


def next_seq(existing_ids, day: str) -> int:
    """**纯函数**：从已有 ID 列表推出当天下一个序号（同日最大 + 1）。

    抽成纯函数是为了能**不碰真表**地自证 —— 发号逻辑算错会直接撞号。
    """
    day = str(day)
    mx = 0
    for v in existing_ids or []:
        m = FORM_RE.match(str(v or "").strip())
        if m and m.group(1) == day:
            mx = max(mx, int(m.group(2)))
    return mx + 1


def list_table_content_ids(destinations=None, lark_runner=None) -> tuple[list | None, str]:
    """只读飞书表，取「内容 ID」列全部值。返回 (ids, 原因)。

    **读不到就返回 (None, 原因)** —— 不返回空列表（那会被下游当成「表里一行都没有」）。
    """
    try:
        dest = (destinations or _default_destinations)()
        runner = lark_runner or _default_lark_run
        got = runner("base", "+record-list", "--base-token", dest["base_token"],
                     "--table-id", dest["table_id"], "--format", "json",
                     "--limit", str(_PAGE_LIMIT), "--offset", "0")
        # ★★ 2026-10-20：**「没读到」有两种形状，一种都不许被当成「表里一行都没有」**。
        #   ① `feishu_publish._lark_run` 在 `allow_fail` 关闭时 **抛 `SystemExit`** ——
        #      **它不是 `Exception` 的子类** ⇒ 原先下面那个 `except Exception` 接不住
        #      ⇒ 直接穿出 `resolve()`、穿出引擎的 `except Exception` ⇒ **整个引擎 exit=1、
        #      stdout 0 字节、结论与旁挂全丢**。实测复现（假 lark-cli 逐字吐 keychain 报错）：
        #      `rc=1 ｜ stdout 0 字节 ｜ stderr 只剩 lark-cli 输出不是 JSON`。
        #   ② `allow_fail=True` 时它**不抛**，返回 `{"ok": false, "raw": …}` ——
        #      原先 `d = {}` ⇒ `out=[]` ⇒ `next_seq([])=1` ⇒ 发出 `AD-…-001`
        #      **与表里已有的号撞车**（历史行不改不重编号）。这条更阴：不报错、直接错号。
        #   ⇒ 两条一律按"读不到"返回 `(None, 原因)`，由 `resolve()` 退指纹、**不编号**。
        if isinstance(got, dict) and got.get("ok") is False:
            return None, "读表失败（lark-cli 报错）：%s" % (
                str(got.get("error") or got.get("raw") or "")[:300])
        # ★★ 2026-10-20（第三处，也是当天最贵的一处）：**必须翻页**。
        #   病灶：lark-cli `+record-list` 默认只回**一页 100 行**，而这张表已有 ~190 行 ——
        #   于是「内容 ID」永远只看见**最早那 100 行**，今天新写的行全在第 2 页 ⇒ 永远看不见
        #   ⇒ `next_seq([])=1` ⇒ **每一单都发 `AD-…-001`**。
        #   实测代价（2026-10-20 15:1x 核表）：当天 **5 条记录共用 `AD-20261020-001`**；
        #   而按内容 ID 幂等 upsert 的那条路会**命中同一行** ⇒ 后一单覆盖前一单。
        #   判据：④f/④f2（两页才看得到今天的号 ⇒ 必须取到 max+1；页尾不满也必须翻完）。
        out: list[str] = []
        seen_rows = 0
        offset = 0
        pages = 0
        while True:
            pages += 1
            if pages > _MAX_PAGES:      # 保险：不许无限翻（服务端 has_more 抽风时不挂死）
                return None, "读表超过 %d 页仍未结束 ⇒ 不编号（宁可退指纹，也不发重号）" % _MAX_PAGES
            d = (got or {}).get("data") or {}
            names = d.get("fields") or []
            try:
                ci = names.index("内容 ID")
            except ValueError:
                ci = 0
            rows = d.get("data") or []
            for row in rows:
                if ci < len(row):
                    v = str(row[ci] or "").strip()
                    if v:
                        out.append(v)
            seen_rows += len(rows)
            if not rows or not d.get("has_more"):
                break
            offset += len(rows)
            got = runner("base", "+record-list", "--base-token", dest["base_token"],
                         "--table-id", dest["table_id"], "--format", "json",
                         "--limit", str(_PAGE_LIMIT), "--offset", str(offset))
            if isinstance(got, dict) and got.get("ok") is False:
                return None, "读表失败（第 %d 页 lark-cli 报错）：%s" % (
                    pages + 1, str(got.get("error") or got.get("raw") or "")[:300])
        return out, "读到 %d 个内容 ID（表内 %d 行、翻了 %d 页）" % (len(out), seen_rows, pages)
    except SystemExit as e:                                        # ★ 2026-10-20 补
        # `SystemExit` 是 `BaseException`，上面那个 `except Exception` 抓不到它 ——
        # 这正是「引擎整单被一个读表失败打死」的真凶，别改回 `except Exception` 一条。
        return None, "读表失败（lark-cli 退出）：%s" % (
            e.code if isinstance(e.code, str) else (e.code,))
    except Exception as e:                                        # noqa: BLE001
        return None, "读表失败：%s" % e


def resolve(day: str | None = None, *, want_business_id: bool = True,
            destinations=None, lark_runner=None) -> dict:
    """发一个号。**唯一入口。**

    返回 `{content_id, basis, ok, reason, next_seq}`。

    * `want_business_id=False` ⇒ **不去读表**（不发飞书就不需要号），返回指纹形态占位 + 说明。
    * 读表失败 ⇒ `ok=False`、`content_id=None`、`reason` 写明 —— **不编号**。
    """
    day = day or time.strftime("%Y%m%d")
    if not want_business_id:
        return {"content_id": None, "ok": False, "next_seq": None,
                "basis": "not_publishing",
                "reason": ("本单不发飞书 ⇒ 不发业务号（也就不去读表）。"
                           "报告侧用内容指纹形态，由调用方补 `content_id_basis`。")}
    ids, why = list_table_content_ids(destinations, lark_runner)
    if ids is None:
        return {"content_id": None, "ok": False, "next_seq": None,
                "basis": "table_unreadable", "reason": why}
    seq = next_seq(ids, day)
    return {"content_id": format_id(day, seq), "ok": True, "next_seq": seq,
            "basis": "business_number_from_table",
            "reason": "PRD §5.4 `AD-YYYYMMDD-NNN`；序号=%s（表内同日前缀最大 +1）；%s"
                      % (seq, why)}


def fallback_of(content_version) -> str:
    """没有业务号时用的**指纹形态**。调用方必须同时写 `content_id_basis` 说明原因。"""
    return FALLBACK_PREFIX + str(content_version or "unknown")[:12]


# ── 默认依赖（可注入，便于自证不碰真表/真网）──────────────────────────────
def _default_lark_run(*args, **kw):
    from feishu_publish import _lark_run as _run          # 同目录，延迟导入
    return _run(*args, **kw)


def _default_destinations():
    from feishu_publish import destinations as _dest
    return _dest()


# ══════════════════════════════════════════════════════════════════
# 判据自证（不碰真表：`lark_runner` 全注入）
# ══════════════════════════════════════════════════════════════════

def _selftest() -> int:
    ok = fail = 0
    fails: list[str] = []

    def ck(name, cond, detail=""):
        nonlocal ok, fail
        if cond:
            ok += 1
        else:
            fail += 1
            fails.append("%s %s" % (name, detail))

    # ①a–e 形态
    ck("①a 正例", is_business_id("AD-20260922-001"))
    ck("①b 三位固定", is_business_id("AD-20260922-999"))
    ck("①c 拒哈希", not is_business_id("AUTO-48cac901ac43"))
    ck("①d 拒 text-", not is_business_id("text-e2678dd00abe"))
    ck("①e 拒缺零填充", not is_business_id("AD-20260922-1"))

    # ②a–d 序号推导（纯函数）
    ck("②a 空表→1", next_seq([], "20260922") == 1, next_seq([], "20260922"))
    ck("②b 取最大+1", next_seq(["AD-20260922-001", "AD-20260922-007", "AD-20260922-003"],
                               "20260922") == 8)
    ck("②c 只数当天", next_seq(["AD-20260921-099"], "20260922") == 1)
    ck("②d 忽略非本形态", next_seq(["AUTO-abc", "text-xyz", ""], "20260922") == 1)
    # ②e 乱序也要取最大（不能"数条数"—— 历史行不改不重编号 ⇒ 中间可能有洞）
    ck("②e 有洞也取最大", next_seq(["AD-20260922-005", "AD-20260922-002"], "20260922") == 6)

    # ③a 拼接
    ck("③a 三位零填充", format_id("20260922", 1) == "AD-20260922-001", format_id("20260922", 1))
    ck("③b 三位上限", format_id("20260922", 999) == "AD-20260922-999")

    # ④a ★ 读表失败 ⇒ **不编号**
    def boom(*a, **k):
        raise RuntimeError("表读不到")
    r = resolve("20260922", destinations=lambda: {"base_token": "b", "table_id": "t"},
                lark_runner=boom)
    ck("④a 读不到就不编", r["ok"] is False and r["content_id"] is None
       and r["basis"] == "table_unreadable", "得到 %r" % r)
    ck("④a2 原因写明", "表读不到" in r["reason"], r["reason"])

    # ④b 正常读到 ⇒ 发号
    def fake(*a, **k):
        return {"data": {"fields": ["内容 ID", "状态"],
                         "data": [["AD-20260922-001", "x"], ["AD-20260922-004", "y"],
                                  ["AUTO-old", "z"]]}}
    r = resolve("20260922", destinations=lambda: {"base_token": "b", "table_id": "t"},
                lark_runner=fake)
    ck("④b 读到就发", r["ok"] is True and r["content_id"] == "AD-20260922-005",
       "得到 %r" % r["content_id"])
    ck("④b2 出处写明", "PRD §5.4" in r["reason"], r["reason"])

    # ④c 不发飞书 ⇒ 不去读表（runner 一被调用就报错，证明真没调）
    def must_not_call(*a, **k):
        raise AssertionError("不发飞书却去读了表")
    r = resolve("20260922", want_business_id=False, lark_runner=must_not_call)
    ck("④c 不发就不读表", r["ok"] is False and r["basis"] == "not_publishing"
       and r["content_id"] is None, "得到 %r" % r)

    # ④d ★★ 2026-10-20：runner 抛 `SystemExit` ⇒ **必须退成「不编号」，不许把引擎打死**
    #   （真凶是 `feishu_publish._lark_run` 抛 SystemExit，而 SystemExit 不是 Exception）
    def exits(*a, **k):
        raise SystemExit('lark-cli 输出不是 JSON：{"error":{"message":"keychain access blocked"}}')
    r = resolve("20260922", destinations=lambda: {"base_token": "b", "table_id": "t"},
                lark_runner=exits)
    ck("④d SystemExit 不吃掉整单", r["ok"] is False and r["content_id"] is None
       and r["basis"] == "table_unreadable", "得到 %r" % r)
    ck("④d2 原因写明 keychain", "keychain" in r["reason"], r["reason"])

    # ④e ★★ 2026-10-20：runner 返回 `{"ok": false}`（allow_fail 档）⇒ **不许当成空表**
    #   当成空表 ⇒ next_seq([])=1 ⇒ 发 AD-…-001 ⇒ 与表里已有号撞车
    def fails_soft(*a, **k):
        return {"ok": False, "error": {"message": "keychain Get failed"}}
    r = resolve("20260922", destinations=lambda: {"base_token": "b", "table_id": "t"},
                lark_runner=fails_soft)
    ck("④e ok:false 不发 001", r["ok"] is False and r["content_id"] is None,
       "得到 %r（空表会让 next_seq 得 1 ⇒ 撞号）" % (r["content_id"],))

    # ④f ★★ 2026-10-20：**今天的号在第 2 页** ⇒ 必须翻页才发得出 max+1，不许恒发 001
    #   （实测代价：当天 5 条记录共用 AD-20261020-001；按内容 ID 幂等 upsert 会命中同一行）
    def paged(*a, **k):
        args = list(a)
        off = int(args[args.index("--offset") + 1]) if "--offset" in args else 0
        if off == 0:
            return {"ok": True, "data": {
                "fields": ["内容 ID"],
                "data": [["AD-20261019-018"], ["AD-20261019-019"]],
                "has_more": True}}
        return {"ok": True, "data": {
            "fields": ["内容 ID"],
            "data": [["AD-20261020-001"], ["AD-20261020-003"]],
            "has_more": False}}
    ids, why = list_table_content_ids(
        destinations=lambda: {"base_token": "b", "table_id": "t"}, lark_runner=paged)
    ck("④f 翻页读全表", ids == ["AD-20261019-018", "AD-20261019-019",
                                "AD-20261020-001", "AD-20261020-003"], "得到 %r" % (ids,))
    r = resolve("20261020", destinations=lambda: {"base_token": "b", "table_id": "t"},
                lark_runner=paged)
    ck("④f2 不许恒发 001", r["ok"] is True and r["content_id"] == "AD-20261020-004",
       "得到 %r（不翻页会得 001 ⇒ 撞号）" % (r["content_id"],))

    # ⑤ 指纹兜底形态 + 它**不是**业务号
    fb = fallback_of("e2678dd00abea802")
    ck("⑤a 指纹形态", fb == "AUTO-e2678dd00abe", fb)
    ck("⑤b 指纹不是业务号", not is_business_id(fb), fb)

    # ⑥ ★ 反向对照：把「有洞取最大」改成「数条数」⇒ ②e 必须红
    ck("⑥ 洞不会被填错", next_seq(["AD-20260922-005", "AD-20260922-002"], "20260922") == 6,
       "改成数条数会得 3 ⇒ 撞号（历史行不改不重编号，中间一定有洞）")

    print("content_id --selftest：%d/%d" % (ok, ok + fail))
    for f in fails:
        print("  ✗", f)
    return 0 if fail == 0 else 1


def _peek() -> int:
    r = resolve()
    print(("下一个号：%s" % r["content_id"]) if r["ok"] else ("推不出号：%s" % r["reason"]))
    print("  出处：%s" % r["basis"])
    return 0 if r["ok"] else 3


def main() -> int:
    ap = argparse.ArgumentParser(description="内容 ID 发号（PRD §5.4，唯一实现）")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--peek", action="store_true", help="只读：看下一个号会是什么")
    a = ap.parse_args()
    if a.selftest:
        return _selftest()
    if a.peek:
        return _peek()
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
