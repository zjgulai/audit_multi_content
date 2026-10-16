#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""观察件（`observations[]`）的形态判据 —— **画面语义通道的入口闸**。

## 它守的是什么（2026-10-13 B1 实测，不是预防性设计）

`kb/l7/review-engine/core/media_adapter.py::text_segments()` 把 `observations[]` 的
**`text`/`observation`/`description`/`claim` 任一键**当**文本**读进去，送进**同一个**
`rule_engine.scan_text()` 做**字面子串**匹配。B1 实测（夹具 A）证明这条路**真的通**：

    observation「…标注 'safe for baby'」→ 命中 US-CLAIM-HEALTH-001
    location = `00:00:05 (observation[0]) text characters 26-38`

⇒ **观察件的 `text` 就是"会被判定的素材内容"**，因此它的**写法**直接决定误报率。

## ★ 为什么必须禁「否定式表述」（这是本判据存在的唯一理由）

B1 反向对照里实测到的那条陷阱：

    干净读数：「无车辆、**无安全座椅**、无危险动作」
    规则模式：「**没有安全座椅**」

两者字面上极像，而匹配是**字面子串**。一旦**规则收宽**（这几乎是必然的，
B1 里 `危险动作示范` 就因为少一个语序而漏掉），干净读数就会被判成红线。

⇒ **本判据的口径**：`text` **只写「画面里有什么」**；
  要记「没看到什么」，写进**另一个字段 `absent`** —— 它**不会被扫**，只作覆盖说明。

## 四条硬规则（`text`）

1. **不许是否定式**（见 `NEG_MARKERS`）—— 否定式只许进 `absent`。
2. **必须带 `timecode`** —— 否则这一条**定位不到**（B1 的命中位置正是取自它）。
3. **必须标 `fact_or_inference`** —— 「观察」与「推断」不能混（库规：不把推断写成观测事实）。
4. **必须标 `reader`** —— 谁产出的（人眼过帧 / 某模型），否则无法追溯与复核。

另：`text` 不许把**素材自己的字**搬进来 —— 那是 `ocr[]` / `transcript[]` 的活；
两者混一起会**骗过"这是画面观察"的性质标注**。

## 用法

    python3 kb/l8/check_observations.py --selftest            # 自证（含反向对照）
    python3 kb/l8/check_observations.py <file.json> [--json]  # 校验一个观察件
"""
from __future__ import annotations

import argparse
import json
import re
import sys

#: 必填字段
REQUIRED = ("text", "timecode", "fact_or_inference", "reader")

#: ★ 否定式标记 —— 出现在 `text` 里就**拒**。
#: 为什么宁可拒：漏放（干净读数被判成红线）代价高于多要人改一次写法。
#: 中英都收；英文按词边界，避免 `no` 撞进 `note`/`nothing`。
NEG_MARKERS_CN = ("无", "未见", "没有", "未使用", "未坐", "未系", "未安装", "未取得", "未获",
                  "不在", "不含", "未出现", "未发现")
NEG_MARKERS_EN = ("no ", "not ", "without", "none", "absent", "missing")

#: `fact_or_inference` 的闭集（与库内口径一致）
FACT_VALUES = ("观察", "事实", "推断", "inference", "observation")

#: timecode 形状：`HH:MM:SS` 或 `HH:MM:SS-HH:MM:SS`
TC_RE = re.compile(r"^\d{2}:\d{2}:\d{2}(-\d{2}:\d{2}:\d{2})?$")


def _neg_hits(text: str) -> list[str]:
    s = str(text or "")
    low = " " + s.lower() + " "
    hits = [m for m in NEG_MARKERS_CN if m in s]
    hits += [m.strip() for m in NEG_MARKERS_EN if m in low]
    return sorted(set(hits))


def check_one(obs: dict, index: int = 0) -> list[str]:
    """校验一条 observation，返回问题列表（空 = 通过）。**只报，不改。**"""
    bad: list[str] = []
    where = "observation[%d]" % index
    if not isinstance(obs, dict):
        return ["%s 不是对象（%s）" % (where, type(obs).__name__)]

    for f in REQUIRED:
        if not str(obs.get(f) or "").strip():
            bad.append("%s 缺必填字段 `%s`" % (where, f))

    txt = str(obs.get("text") or "")
    if txt.strip():
        hits = _neg_hits(txt)
        if hits:
            bad.append("%s 的 `text` 含否定式表述 %s ⇒ 干净读数会被规则误判成红线；"
                       "请改写为「画面里有什么」，把「没看到什么」移到 `absent`"
                       % (where, hits))

    tc = str(obs.get("timecode") or "")
    if tc and not TC_RE.match(tc):
        bad.append("%s 的 `timecode=%r` 不是 HH:MM:SS 或 HH:MM:SS-HH:MM:SS 形状" % (where, tc))

    fi = str(obs.get("fact_or_inference") or "")
    if fi and fi not in FACT_VALUES:
        bad.append("%s 的 `fact_or_inference=%r` 不在闭集 %s 里" % (where, fi, list(FACT_VALUES)))
    return bad


def check_payload(observations) -> list[str]:
    """校验一份观察件（list 或契约对象里的 `observations`）。"""
    if isinstance(observations, dict):
        observations = observations.get("observations") or []
    if not isinstance(observations, list):
        return ["observations 不是数组（%s）" % type(observations).__name__]
    out: list[str] = []
    for i, o in enumerate(observations):
        out.extend(check_one(o, i))
    return out


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

    GOOD = {"text": "成年女性手持粉色吸奶器展示，室内家居场景，画面内仅成人。",
            "timecode": "00:00:00-00:00:23", "fact_or_inference": "观察", "reader": "人眼过帧"}
    ck("① 合规观察件通过", check_one(GOOD) == [], str(check_one(GOOD)))

    # ② ★ 反向对照：B1 实测的那条陷阱**必须被拒**
    TRAP = dict(GOOD, text="无车辆、无安全座椅、无危险动作")
    ck("② 反向对照：「无安全座椅」这类否定式必须被拒",
       check_one(TRAP) != [], "竟然通过了 ⇒ 判据没在守东西")

    # ③ 每一类必填缺失都要红
    for f in REQUIRED:
        bad = dict(GOOD)
        bad.pop(f)
        ck("③ 缺 `%s` 必须红" % f, check_one(bad) != [], "通过了")

    # ④ timecode 形状
    ck("④ 坏 timecode 必须红",
       check_one(dict(GOOD, timecode="12秒")) != [], "通过了")
    ck("④b 合法单点 timecode 通过",
       check_one(dict(GOOD, timecode="00:00:05")) == [], "")

    # ⑤ fact_or_inference 闭集
    ck("⑤ 闭集外的取值必须红",
       check_one(dict(GOOD, fact_or_inference="大概吧")) != [], "通过了")

    # ⑥ ★ 反向对照：英文否定式也要拒（并按词边界，不误伤 note）
    ck("⑥ 英文否定式必须红",
       check_one(dict(GOOD, text="child on adult lap, no car seat")) != [], "通过了")
    ck("⑥b 「note」不许被当成 `no ` 误伤（反向对照）",
       check_one(dict(GOOD, text="画面右下角有一行 note 文字")) == [],
       str(check_one(dict(GOOD, text="画面右下角有一行 note 文字"))))

    # ⑦ 整份 payload：一条坏就报，且指数对得上
    res = check_payload([GOOD, TRAP])
    ck("⑦ 整份校验报出且指名第 1 条",
       len(res) == 1 and res[0].startswith("observation[1]"), str(res))

    # ⑧ 契约对象形态也认
    ck("⑧ 认契约对象（{observations:[...]}）",
       check_payload({"observations": [GOOD]}) == [], "")
    ck("⑧b 空 observations 通过（不是错误）", check_payload([]) == [], "")

    print("check_observations --selftest：%d/%d" % (ok, ok + fail))
    for x in fails:
        print("  ✗", x)
    return 0 if fail == 0 else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="观察件形态判据（只读）")
    ap.add_argument("path", nargs="?", help="观察件 JSON（或含 observations 的契约对象）")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return _selftest()
    if not a.path:
        ap.print_help()
        return 0
    try:
        data = json.load(open(a.path, encoding="utf-8"))
    except Exception as e:                                        # noqa: BLE001
        print("读不到 / 解不开：%r" % (e,), file=sys.stderr)
        return 2
    problems = check_payload(data)
    if a.json:
        print(json.dumps({"ok": not problems, "problems": problems}, ensure_ascii=False, indent=2))
    else:
        if problems:
            print("❌ 观察件不合规（%d 条）：" % len(problems))
            for p in problems:
                print("   -", p)
        else:
            print("✅ 观察件合规")
    return 0 if not problems else 3


if __name__ == "__main__":
    raise SystemExit(main())
