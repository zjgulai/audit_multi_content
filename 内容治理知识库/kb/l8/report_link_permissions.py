#!/usr/bin/env python3
"""报告链接的**可见范围**抽样回读 —— 「有报告打不开」这件事要有东西在跑它。

Owner 2026-10-16 逐字指令（两句，第二句是判据）：
  「所有上审查报告，有飞书云文档阅读权限的，都必须可以打开，**权限跟随飞书云文档**」

── 它守的是哪一次事故

  报告云文档由 `tools/agent/review_publish.mjs` 的 `docs +create` 建，**建完从来不碰权限**
  ⇒ `link_share_entity = closed`（2026-10-16 全量抽查：76/76 全是 closed）
  ⇒ 群里那张卡、表里那一格给出的链接，**业务侧点开就是 Access Denied**
  （当天实测原话：`Access Denied X-TT-System-Error: 3 Oncall ID: 783`）。
  11:38 挨个 patch 了 319 份、11:49 又把复跑期间新建的 43 份补齐；
  **代码也补了**（建完立刻 patch → 回读确认 → 回读不过就不给链接）。

  ⚠️ 但「补过一次」不等于「以后不会再出现」—— 当天就是活例子：代码改完 **跑批进程没重启**
  （`batch_review_runner.mjs` 是 `import { handleMessage }` 在**自己进程内**跑评审的）
  ⇒ 那一批新建的 43 份**照样是 closed**。**这类事只能靠有东西定期量。**

── 量什么（抽样，不是全量；三处来路合并去重，按「最近写进去的」优先）

  ① 采集表 `tblavfbMDMeRsulo` 的链接列 —— 业务侧真正点的那一列；
  ② 结论表 `tblCXPQVzfFWWCon` 的 `报告链接`（按 `写入时间` 最新几行）；
  ③ 守衡台账 `PMO/shouheng-state/batch-review.json` 的 `report_url`（按 `sent_at` 最新几条）
     —— 这一路是**刚跑完、还没进表**的那一批，最容易漏。

── 三态（与就绪巡检其余各格同一套）

  · `ok=True`  —— 抽到的每一份都是 `tenant_readable`；
  · `ok=False` —— 抽到 `closed`/`anyone_*`/其它：**有报告打不开**（给出去路与 token）；
  · `ok=None`  —— **未测**（lark-cli 不在 / 调用失败 / 一份都没抽到）——
     「量不到」不许说成「没问题」，这是本库反复栽过的那条（§2.4.1）。

用法：
  python3 kb/l8/report_link_permissions.py --json          # 只读抽样（就绪巡检调的就是它）
  python3 kb/l8/report_link_permissions.py --sample 20     # 抽样条数（默认 8）
  python3 kb/l8/report_link_permissions.py --all           # 全量（表 ∪ 台账 ∪ 结论表）
  python3 kb/l8/report_link_permissions.py --apply         # 把不是 tenant_readable 的补齐（Owner 已授权）
  python3 kb/l8/report_link_permissions.py --selftest      # 判据自证（喂桩，一次网络都不发）
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LARK = os.path.expanduser("~/.dsh/bin/lark-cli")
PROFILE = "dsh-kb"
WANT = "tenant_readable"          # 「组织内获得链接的人可阅读」；**不是**公网公开（anyone_*）
BASE, TABLE = "RY2UbCRjXaeeWwscUPScVN5AnQc", "tblavfbMDMeRsulo"
CONCL_TABLE = "tblCXPQVzfFWWCon"
LINK_COLS = ("10/14重跑报告链接", "报告链接")
LEDGER = os.path.expanduser(
    "~/Project/audit_multi_content/PMO/shouheng-state/batch-review.json")
TIMEOUT_S = 60


# ─────────────────────────────────── 纯函数（判据都在这一层，喂样本就能证）

def tok_of(s):
    """从任意形状里取 `/docx/<token>` 的 token（取不到回空串，**不许编**）。"""
    m = re.search(r"/docx/([A-Za-z0-9]+)", str(s or ""))
    return m.group(1) if m else ""


def plain(v):
    """飞书字段 → 字符串（纯文本 / 富文本 / URL 字段三种形状都要认）。"""
    if v is None:
        return ""
    if isinstance(v, str):
        return v
    if isinstance(v, list):
        return "".join(plain(x) for x in v)
    if isinstance(v, dict):
        if v.get("link"):
            return str(v.get("link"))
        if v.get("text"):
            return str(v.get("text"))
        return "".join(plain(x) for x in v.values())
    return str(v)


def pick(tokens, sample=None, order=None):
    """去重 →（可选）按 `order`（token 序列，最新的在前）排 → 截断。

    ★ 为什么要有 `order`：抽样要抽**最可能坏的那几份** —— 也就是**刚写进去的**。
      随机抽只会抽到一周前那批（它们早就被 patch 过）⇒ 永远绿，等于没量。
    """
    seq = [t for t in dict.fromkeys(tokens) if t]
    if order:
        rank = {t: i for i, t in enumerate(order) if t}
        seq.sort(key=lambda t: rank.get(t, len(rank)))
    return seq[:sample] if sample else seq


def verdict(settings):
    """`{token: 设置值}` → (ok, bad)。

    ★ 三态分开：`None`（读不到）**不算** `closed`，也**不算**通过 —— 由调用方汇总成「未测」。
    """
    bad = [(t, v) for t, v in settings.items() if v is not None and v != WANT]
    if any(v is None for v in settings.values()):
        return (None if not bad else False), bad
    return (not bad), bad


# ─────────────────────────────────── 读飞书（三条来路）

def lark(args, timeout=TIMEOUT_S):
    return subprocess.run([LARK, *args], capture_output=True, text=True,
                          cwd="/tmp", timeout=timeout)


def read_table(base, table, out_path):
    q = lark(["base", "+record-list", "--base-token", base, "--table-id", table,
              "--limit", "2000", "--format", "ndjson", "--output", out_path, "--overwrite",
              "--profile", PROFILE, "--as", "bot"])
    if q.returncode != 0 or not os.path.exists(out_path):
        return None
    try:
        return [json.loads(l) for l in open(out_path, encoding="utf-8") if l.strip()]
    except Exception:                                            # noqa: BLE001
        return None


def read_link_col(rows):
    """采集表的链接列 ⇒ [(token, 内容ID)]，按表内顺序。"""
    out = []
    for r in rows or []:
        cid = plain(r.get("内容 ID"))[:40]
        for col in LINK_COLS:
            t = tok_of(plain(r.get(col)))
            if t:
                out.append((t, f"表:{cid}"))
                break
    return out


def read_concl_links(rows, newest=12):
    """结论表 ⇒ 按 `写入时间` 最新的若干行。"""
    if not rows:
        return []
    def key(r):
        v = plain(r.get("写入时间"))
        try:
            return float(v) if re.fullmatch(r"\d+", v or "") else 0.0
        except Exception:                                        # noqa: BLE001
            return 0.0
    seq = sorted(rows, key=key)
    out = []
    for r in seq[-newest:][::-1]:
        t = tok_of(plain(r.get("报告链接")))
        if t:
            out.append((t, "结论表"))
    return out


def read_ledger_links(path=LEDGER, newest=12):
    """守衡台账 ⇒ 按 `sent_at` 最新的若干条（刚跑完、还没进表的那一批）。"""
    try:
        d = json.load(open(path, encoding="utf-8"))
    except Exception:                                            # noqa: BLE001
        return []
    items = d.get("items") or {}
    seq = sorted(((v.get("sent_at") or "", k, v) for k, v in items.items()), reverse=True)
    out = []
    for _, k, v in seq[:newest]:
        t = tok_of(v.get("report_url"))
        if t:
            out.append((t, f"台账:{k[:28]}"))
    return out


def get_setting(token, runner=None):
    """回读一份文档的可见范围。

    ★ 读不到回 `None`（**未测**），**不是** `closed` —— 两者混起来会把「没量到」报成故障。
      ⚠️ `permission_public` 缺失（有些文档没有这一节）也走 `None`：
        那是「这个读数对这种文档不适用」，同样不是「closed」。
    """
    run = runner or lark
    q = run(["drive", "+permission-get-setting", "--token", token, "--type", "docx",
             "--profile", PROFILE, "--as", "bot"])
    if getattr(q, "returncode", 1) != 0:
        return None
    try:
        return json.loads(q.stdout)["data"]["permission_public"]["link_share_entity"]
    except Exception:                                            # noqa: BLE001
        return None


def patch_setting(token, runner=None):
    run = runner or lark
    q = run(["drive", "permission.public", "patch", "--token", token, "--type", "docx",
             "--data", json.dumps({"link_share_entity": WANT}),
             "--profile", PROFILE, "--as", "bot", "--yes"])
    return getattr(q, "returncode", 1) == 0


# ─────────────────────────────────── 自证

class _Stub:
    def __init__(self, out, rc=0):
        self.stdout, self.stderr, self.returncode = out, "", rc


def selftest():
    """喂样本给纯函数 + 桩给读回；**一次网络都不发**。"""
    res = []

    def eq(cid, got, want):
        res.append((cid, got == want, got, want))

    eq("P1 取 token：markdown / 裸 URL / URL 字段三种形状都要认",
       [tok_of("[审查报告](https://momcozy-in.feishu.cn/docx/Abc123Def)"),
        tok_of("https://momcozy-in.feishu.cn/docx/XyZ9"),
        tok_of({"link": "https://momcozy-in.feishu.cn/docx/Qq11", "text": "审查报告"})],
       ["Abc123Def", "XyZ9", "Qq11"])
    eq("P2 取不到 ⇒ 空串（不许编一个 token 出来）", tok_of("（无）"), "")

    eq("P3 抽样：去重 + 保留顺序",
       pick(["a", "b", "a", "c"]), ["a", "b", "c"])
    eq("P4 ★ 抽样要抽**最新写进去的**（order 说谁新）",
       pick(["old1", "new1", "old2"], sample=2, order=["new1", "old2", "old1"]),
       ["new1", "old2"])

    ok, bad = verdict({"a": WANT, "b": WANT})
    eq("P5 全是 tenant_readable ⇒ 通过", (ok, bad), (True, []))
    ok, bad = verdict({"a": WANT, "b": "closed"})
    eq("P6 ★ 有一份 closed ⇒ **不通过**，且点名是哪一份", (ok, [b[0] for b in bad]), (False, ["b"]))
    ok, bad = verdict({"a": WANT, "b": None})
    eq("P7 ★ 读不到 ⇒ **未测**（None），不许说成通过、也不许说成 closed", (ok, bad), (None, []))
    ok, bad = verdict({"a": "closed", "b": None})
    eq("P8 既有 closed 又有读不到 ⇒ 先报 closed（故障优先于未测）", (ok, len(bad)), (False, 1))
    ok, _ = verdict({"a": "anyone_readable"})
    eq("P9 ★ 「公网公开」不等于目标口径（Owner 定的是**组织内**可读）", ok, False)

    # ★ 桩：读回那一跳的三种结局必须分得开（真实现只差一个 runner 注入）
    def stub(out, rc=0):
        return lambda argv, timeout=TIMEOUT_S: _Stub(out, rc)
    good = json.dumps({"data": {"permission_public": {"link_share_entity": WANT}}})
    closed = json.dumps({"data": {"permission_public": {"link_share_entity": "closed"}}})
    eq("P10 桩：tenant_readable ⇒ 认出来", get_setting("t", stub(good)), WANT)
    eq("P11 桩：closed ⇒ 认出来", get_setting("t", stub(closed)), "closed")
    eq("P12 桩：命令失败 ⇒ None（未测，不是 closed）", get_setting("t", stub("", 1)), None)
    eq("P13 桩：回包没有 permission_public ⇒ None（不适用，不是 closed）",
       get_setting("t", stub(json.dumps({"data": {}}))), None)

    # ★ 变异对照：把判据改宽（把 None 也算通过）⇒ P7 必须精确变红
    def loose(settings):
        return not [v for v in settings.values() if v not in (None, WANT)], []
    eq("P14 ★ 变异对照：判据改宽（None 算通过）⇒ P7 那条样本必须变红",
       loose({"a": WANT, "b": None})[0], True)

    bad_n = 0
    for cid, okk, got, want in res:
        if not okk:
            bad_n += 1
        print(f"  {'✅' if okk else '❌'} {cid}"
              + ("" if okk else f"\n       got={got!r}\n       want={want!r}"))
    print(f"\n{'❌' if bad_n else '✅'} 报告权限读数 {len(res) - bad_n}/{len(res)} 项通过")
    return 1 if bad_n else 0


# ─────────────────────────────────── main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--sample", type=int, default=8)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--apply", action="store_true",
                    help="把不是 tenant_readable 的补齐（Owner 2026-10-16 已授权这句）")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()

    if a.selftest:
        return selftest()

    if not os.path.exists(LARK):
        out = {"ok": None, "n": 0, "bad": [],
               "note": f"**未测**：找不到 {LARK}（lark-cli 不在）—— 量不到不等于没问题"}
        print(json.dumps(out, ensure_ascii=False))
        return 0 if a.json else 2

    led = read_ledger_links()
    tbl = read_link_col(read_table(BASE, TABLE, "/tmp/perm_watch_tbl.ndjson"))
    con = read_concl_links(read_table(BASE, CONCL_TABLE, "/tmp/perm_watch_concl.ndjson"))
    # 最新的排前面：台账（刚跑完）→ 结论表 → 采集表链接列
    order = [t for t, _ in led] + [t for t, _ in con] + [t for t, _ in tbl]
    want = pick([t for t, _ in led] + [t for t, _ in tbl] + [t for t, _ in con],
                sample=None if a.all else a.sample, order=order)
    src = {}
    for t, s in (led + tbl + con):
        src.setdefault(t, s)

    if not want:
        out = {"ok": None, "n": 0, "bad": [],
               "note": "**未测**：三条来路一份报告都没抽到（表/结论表/台账都读不到？）"}
        print(json.dumps(out, ensure_ascii=False))
        return 0 if a.json else 2

    settings = {t: get_setting(t) for t in want}
    ok, bad = verdict(settings)
    if a.apply and bad:
        for t, _v in bad:
            patch_setting(t)
            settings[t] = get_setting(t)
        ok, bad = verdict(settings)

    untested = [t for t, v in settings.items() if v is None]
    out = {
        "ok": ok, "n": len(settings), "want": WANT,
        "bad": [{"tok": t, "got": v, "src": src.get(t, "")} for t, v in bad],
        "untested_tokens": untested,
        "note": ("每一份都是 tenant_readable" if ok is True else
                 (f"**有报告打不开**：{len(bad)}/{len(settings)} 不是 {WANT}" if ok is False else
                  f"**未测**：{len(untested)}/{len(settings)} 份读不到可见范围 —— 量不到不是没问题")),
        "checked_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    print(json.dumps(out, ensure_ascii=False))
    # 退出码按**三态**给（与就绪巡检其余各格同一套；`--json` 只决定打印形状，不改判据）：
    #   0 = 通过 ｜ 3 = 有报告打不开 ｜ 4 = 未测（量不到）
    return 0 if ok is True else (3 if ok is False else 4)


if __name__ == "__main__":
    sys.exit(main())
