#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""多维表统计与筛选导出（任务拆解 **目标 21** · PRD §8.2）。

════════════════════════════════════════════════════════════════════════
PRD §8.2 原文（逐字，`docs +fetch` 现读，2026-10-10）
════════════════════════════════════════════════════════════════════════

    ### 8.2 批量扫描与多维表
    - 批量上传入口：飞书多维表、结构化 URL、NAS 路径。
    - 多维表字段：内容 ID、产品线、渠道、内容类型、送审版本 /
      Agent 结论、置信度、问题数量、问题分类汇总、报告链接 /
      人工复核人、复核结论、sign-off 人、发布时间 /
      状态：待审 / PASS / REVIEW / BLOCK / 已修改 / 已发布
    - **支持按品线、渠道、风险类型统计。**

＋ §5.1「方式二」：**支持按 PASS / REVIEW / BLOCK 筛选、导出、统计。**

⇒ 本件要兑现的就是那两句：**三样统计**（品线 / 渠道 / 风险类型）＋ **三态筛选导出**。

════════════════════════════════════════════════════════════════════════
★ 第一条：统计走**飞书侧云端聚合**，不是本机重算
════════════════════════════════════════════════════════════════════════

「多维表支持统计」这句话的主语是**多维表**。所以品线与渠道的分布由
`lark-cli base +data-query`（LiteQuery，**服务端在完整表范围上算**）产出 ——
这就是「多维表自己支持」的那条路，§8.2 那条需求指的就是它。

**但本机同时重算一遍，并且两条路必须逐格相等（判据 J1）** —— 为什么非要这么较劲：
不重算的话，我没有任何证据证明「我报的数是飞书侧算的」而不是「我拉了明细自己数的」；
两者在本件里长得一模一样，而**只有前者是「多维表支持统计」**。

════════════════════════════════════════════════════════════════════════
★★ 第二条：风险类型**表里没有这一列** —— 这是缺口，不是可以绕过去的小事
════════════════════════════════════════════════════════════════════════

§8.2 要「按**风险类型**统计」。实测（2026-10-10，bot 身份现读）：

  · 结论表 18 列里**没有**「风险类型」列（`+field-list` 逐列核过）。
  · 唯一的风险语义落点是 **`问题分类汇总`**（text），其内容是
    `<风险类型> <条数>` 以 `；` 连起来 —— 由 `review_engine._category()`
    （= `item["risk_type"]`）汇总、`feishu_publish.py` 拼串写入。
  · ⇒ 风险类型只能**本机从那一列解析**；`+data-query` 对它无能为力
    （按整串分组 ⇒ 每个不同的散文串各成一组，没有统计意义）。

**而且那一列只有一部分行是分类汇总** —— 守衡在链返回后往同一列写的是**散文**
（「链已跑完（182s）…」「**P0 快路**（确定性匹配，24.336 ms…」）。
所以本件**必须报「可解析覆盖率」**，不许把「解析出 36 行」说成「全表统计」。
实测 2026-10-10：93 行里 **36 行可解析 / 40 行是散文 / 17 行空**。

════════════════════════════════════════════════════════════════════════
★ 第三条：判据带反向对照（把缺陷真造一遍，尺子必须精确变红）
════════════════════════════════════════════════════════════════════════

| # | 判据 | 不查会怎样 |
|---|---|---|
| **J1** | 云端聚合 与 本机复算 **逐格相等** | 拿本机数冒充飞书侧数，而没人看得出来 |
| **J2** | 出现的风险类型**必须都在受控词表里**（`l7.json → vocabulary.categories`） | 词表外类型悄悄进统计 ⇒ 分类体系名存实亡 |
| **J3** | 每个统计块**必须带覆盖率**（有值 / 未指定 / 空） | 报比例不给分母 —— 「100% 是 REVIEW」其实只有 9 行 |
| **J4** | 导出 0 行 ⇒ `empty_by_data`（**不是失败**）；非 0 行 ⇒ 必须 `has_more=false` 才算完整 | 把「表里本来没有 PASS」报成「导出失败」，或把翻页的一半当全部 |
| **J5** | 落盘 CSV 行数 **= 服务端 `records_count`** | 本机转换悄悄丢行，而摘要数字对得上 |
| **J6** | 散文行**不得**被解析成风险类型 | 一句「不得当 PASS 依据」被抠成风险类型 —— 本库已经栽过一次同款正则 |

**四条边界（照抄，别外推）**：
1. **只读**：本件只 `+data-query` / `+record-list`（lark-cli 里都是 `Risk: read`）。
   **不建仪表盘、不建视图、不写任何一行** —— 结论表是**我们自己产出的**，
   不属于「源只读」禁令范围，但改它的结构是**人的决定**，不是本件顺手做的事。
2. **`--snapshot` 不碰网络**：给一个 ndjson 就在本机算。此时 **J1 记 `skipped_offline`**
   （**看得见地跳过**，不是静默变绿）。
3. **身份按定死的口径**（AGENTS.md）：主身份 = 守衡 bot（`--profile dsh-kb --as bot`）。
4. **不编数**：任何一个格读不到就报 `null` + 原因，**不许**用 0 顶替。

════════════════════════════════════════════════════════════════════════
用法
════════════════════════════════════════════════════════════════════════

    python3 kb/l8/bitable_stats.py                     # 三样统计 ＋ 三态导出 ＋ 落产物（只读）
    python3 kb/l8/bitable_stats.py --no-export         # 只统计
    python3 kb/l8/bitable_stats.py --snapshot <x.ndjson>   # 离线（不碰飞书）
    python3 kb/l8/bitable_stats.py --selftest          # 反向对照（全离线，一台真库都不碰）
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections import Counter, OrderedDict

KB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REGISTRY = os.path.join(KB, "l7", "registry", "conclusion-destination.yaml")
L7JSON = os.path.join(KB, "l7", "registry", "l7.json")
REPORTS = os.path.join(KB, "l7", "reports")
PROFILE = "dsh-kb"

#: 目的地 id（`conclusion-destination.yaml` 里的键）
DEST_ID = "feishu-bitable-content-review"

#: 三态（PRD §5.1「支持按 PASS / REVIEW / BLOCK 筛选、导出、统计」）
TRI_STATE = ["PASS", "REVIEW", "BLOCK"]

#: ★ 能走**飞书侧云端聚合**的维度 = 结论表里真实存在的列（`+field-list` 实测 18 列）。
SERVER_DIMS = ["产品线", "渠道", "内容类型", "状态", "Agent 结论", "送审版本"]

#: ★ **表里没有这一列** ⇒ 只能本机解析（见文件头第二条）。
LOCAL_DIM = "风险类型"
RISK_TYPE_SOURCE_FIELD = "问题分类汇总"

#: 占位值：PRD 允许它出现，但统计时必须与「真实取值」分开报，否则「未指定」会变成一个品线。
PLACEHOLDER = "未指定"

#: 导出列 = PRD §8.2 逐字列的 15 个（全部真实存在）＋ 两个坐标列。
#: `record_id` 是表内稳定主键（Base 语义，不是 PRD 列的替代品）；
#: `写入时间` 是表内 created_at 自动列，用来给「导出的是哪个时点的表」留证。
EXPORT_FIELDS = [
    "内容 ID", "产品线", "渠道", "内容类型", "送审版本",
    "Agent 结论", "置信度", "问题数量", "问题分类汇总", "报告链接",
    "人工复核人", "复核结论", "sign-off 人", "发布时间", "状态",
    "写入时间",
]

#: 风控：`问题分类汇总` 里合法的 `<类型> <条数>` 段（`；` 分隔）。
#: ★ 关键在**两端都锚死**：类型里不许出现数字，条数必须是段尾整数。
#:   放宽任一端，守衡那些散文就会开始「解析出风险类型」（判据 J6 的反向对照）。
_SEG = re.compile(r"^\s*(?P<type>[^\d；;]{1,40}?)\s*[-－—]\s*(?P<sub>[^\d；;]{1,60}?)\s*(?P<n>\d{1,4})\s*$")
_SEG_PLAIN = re.compile(r"^\s*(?P<type>[^\d；;]{1,40}?)\s+(?P<n>\d{1,4})\s*$")


# ══════════════════════════════════════════════════════════════════════
# 取数：去处 / 词表 / lark-cli
# ══════════════════════════════════════════════════════════════════════

def destinations() -> dict:
    """从登记件读去向（**唯一真源**，不硬编码 token）。

    与 `feishu_publish.py::destinations()` 同口径：PyYAML 在就用它，不在就退回窄正则
    （只取四个 token）—— 目的是「本件与发布件永远指向同一张表」。
    """
    txt = open(REGISTRY, encoding="utf-8").read()
    try:
        import yaml  # noqa: PLC0415
        d = yaml.safe_load(txt)
        for x in (d.get("destinations") or []):
            if x.get("id") == DEST_ID:
                return {"base_token": x["base_token"], "table_id": x["table_id"],
                        "name": x.get("name"), "source": "yaml"}
    except Exception:  # noqa: BLE001
        pass
    blk = txt.split("id: %s" % DEST_ID, 1)[-1][:1200]
    def g(k):
        m = re.search(r"%s:\s*\"?([A-Za-z0-9_]+)\"?" % k, blk)
        return m.group(1) if m else None
    return {"base_token": g("base_token"), "table_id": g("table_id"),
            "name": None, "source": "regex-fallback"}


#: 哨兵值：词表里表示「没分类」的占位，**不是**一个真实类型（统计时必须排除）。
SENTINELS = {"未分类", "unknown", ""}

#: 反例/禁区样本的类目字段（L4 canonical）。**词表来源有两处，见 `controlled_risk_types()`**。
SAMPLE_CASE = os.path.join(KB, "l4", "canonical", "sample_case.jsonl")


def controlled_risk_types() -> dict:
    """受控风险类型 → **出处**。★ 这里曾经错过一次，留档说明为什么是「两处」而不是「一处」。

    ── 出错经过（2026-10-10，**本件自己的判据抓到的**）─────────────────────
    第一版只认 `kb/l7/registry/l7.json → vocabulary.categories`（`review.py::classify()`
    实际会产出的那 8 类）。跑真表立刻 J2 红：`品牌一致性 29 / 措辞表达 10 / 原则性错误 6 /
    合规红线 2` 四类「不在词表里」。

    **但那个红是尺子错了，不是数据错了** —— 逐条追下去：
      · `品牌一致性 / 原则性错误 / 措辞表达 / 合规红线` **全都在**
        `kb/l4/canonical/sample_case.jsonl` 的 **`reason_category`** 字段里
        （实测 473 行：unknown 214 / 品牌一致性 119 / 原则性错误 49 / 措辞表达 47 /
         审核问题 31 / 文化禁忌 10 / 合规红线 3）。
      · 它们是**反例/禁区（sample_case）那套类目**，由「自命中已定稿反例/禁区」这条判定路径
        产出（口径见 Owner 2026-10-05 规则①）；而 `l7.json` 那套是**规则命中**的类目。
    ⇒ **同一列里并存着两套类目体系**，用其中一套去量另一套，必然全红。
      ⇒ 判据改成「**两套的并集**」—— 每套都从它自己的唯一真源读，**不在这里抄第二份**。

    ── 边界（不许外推）─────────────────────────────────────────────────
    · 反例侧那份是**实测**出来的（`grep` L4 canonical），**没有** registry 声明件
      —— 这件事记在 `warnings` 里，并在 `open_questions` 里等 Owner 一句话。
    · **不做任何"归一"**：`措辞表达` 与 `表述与术语准确性` 看着像同一件事的两种叫法，
      但在没有人裁之前，**不许**把它们合并 —— 合错了就是把两类风险并成一类。
    """
    out: dict = {}
    try:
        d = json.load(open(L7JSON, encoding="utf-8"))
        for k in ((d.get("vocabulary") or {}).get("categories") or {}):
            if k not in SENTINELS:
                out[k] = "规则词表（kb/l7/registry/l7.json·声明）"
    except Exception:  # noqa: BLE001
        pass
    try:
        seen = set()
        for line in open(SAMPLE_CASE, encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            c = json.loads(line).get("reason_category")
            if c and c not in SENTINELS:
                seen.add(c)
        for c in sorted(seen):
            out[c] = (out[c] + " ＋ 反例词表（kb/l4/canonical/sample_case.jsonl·实测）"
                      if c in out else "反例词表（kb/l4/canonical/sample_case.jsonl·实测）")
    except Exception:  # noqa: BLE001
        pass
    return out


def _lark() -> str:
    p = shutil.which("lark-cli")
    if p:
        return p
    cand = os.path.expanduser("~/.dsh/bin/lark-cli")
    if os.path.exists(cand):
        return cand
    raise SystemExit("lark-cli 找不到（PATH 与 ~/.dsh/bin 都没有）")


def _lark_json(*args: str, allow_fail: bool = False) -> dict:
    cmd = [_lark(), "--profile", PROFILE, *args, "--as", "bot"]
    p = subprocess.run(cmd, capture_output=True, text=True)
    out = (p.stdout or "").strip()
    try:
        d = json.loads(out)
    except Exception:  # noqa: BLE001
        if allow_fail:
            return {"ok": False, "raw": (out or p.stderr or "")[:400]}
        raise SystemExit("lark-cli 输出不是 JSON：%s" % (out or p.stderr)[:300])
    if "manifest_version" in d:
        # ★ `+record-list --output` 回的是**产物 manifest**（`{"manifest_version": "v1", …}`），
        #   **没有 `ok` 键**。实测坑：拿「有没有 ok」当成败判据，会把一次成功的导出
        #   读成 `lark-cli 失败：null`（error 也是 null）—— 看着像权限问题，其实是形状不同。
        return d
    if not d.get("ok") and not allow_fail:
        raise SystemExit("lark-cli 失败：%s" % json.dumps(d.get("error"), ensure_ascii=False)[:300])
    return d


# ══════════════════════════════════════════════════════════════════════
# 统计
# ══════════════════════════════════════════════════════════════════════

def server_groupby(dim: str, dest: dict) -> list:
    """**飞书侧云端聚合**（LiteQuery）—— 「多维表支持统计」的那条路。

    空值归一：`+data-query` 对空单元格回的是 `{"value": null}`；本机复算那边是 `None`。
    两边都归一成 `None`，**并且单独成一组**（不当 0、不当「未指定」）。
    """
    dsl = {
        "datasource": {"type": "table", "table": {"tableId": dest["table_id"]}},
        "dimensions": [{"field_name": dim, "alias": "d"}],
        # ★★ 必须用 `count_all`，**不能用 `count`** —— 这是本件实测出来的分母陷阱：
        #   `count` 数的是「该字段非空的取值个数」，空单元格那一组恒为 **0**；
        #   `count_all` 数的是**行数**。实测同一张表、同一个维度（2026-10-10）：
        #       count     → 未指定 62 ／ 吸奶器 14 ／ 空 **0**     （合计 76，少了 17）
        #       count_all → 未指定 62 ／ 吸奶器 14 ／ 空 **17**    （合计 93 = 全表）
        #   ⇒ 用 `count` 的话，「按品线统计」的分母**静默少 17 行**，而报表看不出来。
        #     判据 J1（云端 vs 本机逐格相等）就是钉这个的：本机复算数的是行，
        #     两边不等 ⇒ 立刻红（这也是 J1 第一次跑就抓到的真缺陷，不是假想）。
        "measures": [{"field_name": dim, "aggregation": "count_all", "alias": "n"}],
        "shaper": {"format": "flat"},
    }
    # lark-cli 的 `@file` 只认「工作目录之下」或 /tmp 之下（AGENTS.md 实测）。
    # 小 DSL 直接进 argv，不落文件 —— 少一个失败点。
    d = _lark_json("base", "+data-query", "--base-token", dest["base_token"],
                   "--dsl", json.dumps(dsl, ensure_ascii=False))
    out = []
    for r in ((d.get("data") or {}).get("main_data") or []):
        v = r.get("d")
        v = v.get("value") if isinstance(v, dict) else v
        n = r.get("n")
        n = n.get("value") if isinstance(n, dict) else n
        out.append([v, int(n or 0)])
    return out


def local_groupby(rows: list, dim: str) -> list:
    """本机在**同一份明细**上复算同一个维度（供 J1 对账；风险类型也只有这条能走）。"""
    c = Counter()
    for r in rows:
        c[_cell(r, dim)] += 1
    return [[k, v] for k, v in c.items()]


def _cell(row: dict, field: str):
    """取单元格 → 归一成「标量或 None」。

    select / user / link 等数组列在本机读回时是 list；统计要的是「哪个选项」。
    多选在 `问题分类汇总` 这种场景不存在，但 `状态` 是 select ⇒ 取第一个元素并**记多值**。
    """
    v = row.get(field)
    if isinstance(v, list):
        if not v:
            return None
        if len(v) > 1:
            return " + ".join(_scalar(x) for x in v)
        return _scalar(v[0])
    if isinstance(v, dict):
        return _scalar(v)
    return v if v != "" else None


def _scalar(x):
    if x is None:
        return None
    if isinstance(x, dict):
        return x.get("name") or x.get("value") or x.get("text") or json.dumps(x, ensure_ascii=False)
    return x


def coverage_of(rows: list, dim: str) -> dict:
    """★ 判据 J3：每个统计块**必须带分母**。

    三档分开报，**不许合并**：
      · `有值`      —— 非空、且不是 `未指定`
      · `未指定`    —— PRD 允许的占位值（发布件按 PRD 兜的），它**不是**一个真实品线
      · `空`        —— 单元格真的没有值（发布件「只补空、不覆盖既有真实值」的必然结果）
    """
    real = Counter()
    ph = empty = 0
    for r in rows:
        v = _cell(r, dim)
        if v is None:
            empty += 1
        elif str(v).strip() == PLACEHOLDER:
            ph += 1
        else:
            real[str(v)] += 1
    return {"dim": dim, "total": len(rows), "有值": sum(real.values()),
            "未指定": ph, "空": empty, "取值": dict(real.most_common())}


def _row_segments(s: str):
    """把一行 `问题分类汇总` 拆成 `[(类型, n)]`；**任一段解析不了 ⇒ 整行返回 None**。

    ★ 判据 J6 的全部要点就在这个「整行返回 None」上：一行里混着散文时，
    半解析会把「链已跑完（182s）」这类串撕出假类型，而且**损失看不见**
    （分母悄悄少几行，报表照出）。宁可整行算不可解析 —— 损失可见，人才知道要修数据。

    实测真数据里这种**混行确实存在**（2026-10-10）：
    「绝对化与安全承诺-虚假安全承诺 1；功效宣称-疾病治疗宣称 1；平台与促销-静音绝对化表述 1；
      背书与资质-医疗场景宣称」—— 最后一段缺条数（被截断了）。
    """
    segs = [x for x in re.split(r"[；;]", s) if x.strip()]
    out = []
    for seg in segs:
        m = _SEG.match(seg) or _SEG_PLAIN.match(seg)
        if not m:
            return None
        out.append((m.group("type").strip(), int(m.group("n"))))
    return out


def parse_risk_types(rows: list, vocab: dict) -> dict:
    """★ 从 `问题分类汇总` 解析风险类型（**表里没有风险类型列**，见文件头第二条）。

    返回里**必须能看出分母**：可解析几行 / 散文几行 / 空几行。
    产出的类型若两套词表里都没有 ⇒ 落进 `词表外类型`（判据 J2 的输入）。
    """
    weighted = Counter()      # 按「类型被引用的条数」加权（段尾那个 n）
    rows_ok = 0
    prose = []
    empty = 0
    drift = Counter()
    for r in rows:
        s = (r.get(RISK_TYPE_SOURCE_FIELD) or "").strip()
        if not s:
            empty += 1
            continue
        segs = _row_segments(s)
        if segs is None:
            prose.append(s[:70])
            continue
        rows_ok += 1
        for t, n in segs:
            weighted[t] += n
            if t not in vocab:
                drift[t] += n
    return {"可用": rows_ok > 0,
            "分母_总行": len(rows),
            "分母_可解析行": rows_ok,
            "不可解析_散文行": len(prose),
            "空行": empty,
            "可解析覆盖率": (round(rows_ok / len(rows), 4) if rows else None),
            "风险类型_按条数加权": dict(weighted.most_common()),
            "受控词表": sorted(vocab),
            "词表出处": {k: vocab[k] for k in sorted(vocab)},
            "词表外类型": dict(drift.most_common()),
            "不可解析样本": prose[:5]}


# ══════════════════════════════════════════════════════════════════════
# 筛选导出（PRD §5.1「按 PASS / REVIEW / BLOCK 筛选、导出」）
# ══════════════════════════════════════════════════════════════════════

def fetch_rows(dest: dict, states=None, snapshot: str | None = None):
    """拉明细：给了 `snapshot` 就在本机读，否则走服务端**谓词下推**。

    返回 `(rows, meta)`；`meta` 必须带 `records_count` / `has_more` / `rev` ——
    判据 J4 靠 `has_more` 判断「这份导出是不是完整的」，不许拿半页当全部。
    """
    if snapshot:
        rows = [json.loads(l) for l in open(snapshot, encoding="utf-8") if l.strip()]
        if states:
            # ★ 缺陷实测（本件自证 ⑫ 抓到）：离线支路原先**忽略 states**
            #   ⇒ `--snapshot x.ndjson` 导出的「BLOCK 筛选」其实是全表。
            #   这是本件最不该犯的错（导出物标着 BLOCK、内容却是全部），必须在本机补筛。
            want = {str(s) for s in states}
            rows = [r for r in rows if str(_cell(r, "状态") or "") in want]
        return rows, {"source": "snapshot", "path": snapshot,
                      "records_count": len(rows), "has_more": False, "rev": None}
    args = ["base", "+record-list", "--base-token", dest["base_token"],
            "--table-id", dest["table_id"]]
    for f in EXPORT_FIELDS:
        args += ["--field-id", f]
    if states:
        cond = [["状态", "intersects", list(states)]]
        args += ["--filter-json", json.dumps({"logic": "and", "conditions": cond},
                                             ensure_ascii=False)]
    # ★ lark-cli 的 `--output` 有**路径白名单**：只认「工作目录之下」或 `/tmp` 之下。
    #   实测坑（本件第一次跑就撞上）：`tempfile.mkstemp()` 在 macOS 上给的是
    #   `/var/folders/...`（那就是 /tmp 的真身）—— **但白名单是按字面判的**，
    #   于是报 `unsafe output path ... outside the built-in allowlist`，
    #   看着像权限问题，其实是路径写法问题。⇒ 显式 `dir="/tmp"`。
    #   另：`mkstemp` **会先把文件建出来**，而 lark-cli 拒绝覆盖既有文件
    #   （`failed_precondition: output file already exists ... Pass --overwrite`）
    #   ⇒ 用 `mkdtemp` + 自己给文件名：目录建好、文件**不存在**。
    tdir = tempfile.mkdtemp(prefix="bitable-stats-", dir="/tmp")
    tmp = os.path.join(tdir, "rows.ndjson")
    try:
        args += ["--format", "ndjson", "--output", tmp]
        d = _lark_json(*args)
        rows = [json.loads(l) for l in open(tmp, encoding="utf-8") if l.strip()]
        m = d if "records_count" in d else (d.get("data") or {})
        return rows, {"source": "feishu", "path": None,
                      "records_count": m.get("records_count", len(rows)),
                      "has_more": m.get("has_more"), "rev": m.get("rev")}
    finally:
        shutil.rmtree(tdir, ignore_errors=True)


def write_csv(rows: list, path: str) -> int:
    """落 CSV。**UTF-8 BOM** —— 不然 Excel 打开中文是乱码（项目统筹就是这么看表的）。"""
    cols = ["record_id"] + EXPORT_FIELDS
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(cols)
    n = 0
    for r in rows:
        out = []
        for c in cols:
            if c == "record_id":
                out.append(r.get("record_id"))
                continue
            v = _cell(r, c)
            if isinstance(v, list):
                v = json.dumps(v, ensure_ascii=False)
            out.append("" if v is None else v)
        w.writerow(out)
        n += 1
    # .csv **不在** `.md`/`.sh` 那两个中招扩展名里 ⇒ 直写安全（AGENTS.md 逐扩展名实测）。
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        fh.write(buf.getvalue())
    back = sum(1 for _ in open(path, encoding="utf-8-sig")) - 1
    if back != n:
        raise RuntimeError("CSV 回读行数不符：写 %d / 读 %d（%s）" % (n, back, path))
    return n


# ══════════════════════════════════════════════════════════════════════
# 判据（★ 每一条都有反向对照，见 _selftest）
# ══════════════════════════════════════════════════════════════════════

def _prose_recount(rows: list) -> dict:
    """判据 J6 的**独立重扫** —— 本函数里的匹配规则与 `_row_segments` **各写一份，故意不共享**。

    为什么故意重复（这不是手滑，是本库栽过的坑）：共享同一个实现的话，
    **把共享那份改坏，两边一起坏，判据恒绿** —— 尺子和被量的东西是同一根。
    本库已有两处栽在这上面（`p0_fastpath.py` ⑩c2、`workflow_smoke.py` R1–R4）。

    口径与生产侧**必须一致**：整行要么全解析、要么算散文（见 `_row_segments` 的 docstring）。
    """
    ok = prose = empty = 0
    for r in rows:
        s = str(r.get(RISK_TYPE_SOURCE_FIELD) or "").strip()
        if not s:
            empty += 1
            continue
        good = True
        for seg in [x for x in re.split(r"[；;]", s) if x.strip()]:
            if not re.match(r"^\s*[^\d；;]{1,40}?\s*[-－—]\s*[^\d；;]{1,60}?\s*\d{1,4}\s*$", seg) \
               and not re.match(r"^\s*[^\d；;]{1,40}?\s+\d{1,4}\s*$", seg):
                good = False
                break
        if good:
            ok += 1
        else:
            prose += 1
    return {"可解析行": ok, "散文行": prose, "空行": empty}


def _notes(result: dict):
    """**报黄**（不判红）+ **留给 Owner 的问题**。

    按本库惯例（`workflow_smoke.py` 的「判红 / 报黄要分开」）：已知的、口径性的、
    需要人裁的事**报黄**；只有「尺子说得清对错」的才判红。黄项**必须出现在产物里**，
    否则等于没报。
    """
    w, q = [], []
    cov = result.get("coverage") or {}
    rt = result.get("risk_type") or {}

    # ① 分母被占位值吃掉 —— 品线/渠道的「有值」占比极低，统计的可用性受限
    for dim in ("产品线", "渠道"):
        c = cov.get(dim) or {}
        if c.get("total") and (c.get("有值", 0) / c["total"]) < 0.5:
            w.append("「%s」有值只占 %s（%d/%d）—— 未指定 %d ／ 空 %d。"
                     "按 %s 统计的**分布本身是可信的**，但它描述的是**少数行**，"
                     "不能当成全表画像。根因：送审时该字段常缺，发布件按 PRD 兜「未指定」。"
                     % (dim, _pct(c.get("有值"), c.get("total")), c.get("有值"), c["total"],
                        c.get("未指定"), c.get("空"), dim))

    # ② 内容类型的写法没收敛 —— 「按内容类型统计」会给出同义多组
    c = cov.get("内容类型") or {}
    vals = list((c.get("取值") or {}).keys())
    zh = [v for v in vals if re.search(r"[\u4e00-\u9fff]", v)]
    en = [v for v in vals if v not in zh]
    if zh and en:
        w.append("「内容类型」**中英两套写法并存**：中文侧 %s ／ 英文侧 %s（共 %d 种写法）—— "
                 "调用方传什么就写什么（`feishu_publish.py` 的 `a.content_type`），没有受控词表。"
                 "⇒ 按内容类型统计会把同一类拆成几组。**本件不替它归一**（归一要定受控词表，是人的决定）。"
                 % ("、".join(zh), "、".join(en), len(vals)))

    # ③ 风险类型列缺失
    w.append("§8.2 要「按**风险类型**统计」，而结论表 18 列里**没有这一列** —— "
             "本件是从 `%s` 反解出来的，**可解析覆盖率只有 %s**。"
             "要真兑现这条，需要给表加一个「风险类型」列并回填（**写操作，等一句话**）。"
             % (RISK_TYPE_SOURCE_FIELD, _pct(rt.get("分母_可解析行"), rt.get("分母_总行"))))

    # ④ 两套类目体系并存
    prov = rt.get("词表出处") or {}
    only_sample = [k for k, s in prov.items() if "反例词表" in s and "规则词表" not in s]
    if only_sample:
        w.append("风险类型**两套类目体系并存**：规则词表（`l7.json`·声明）与 "
                 "反例/禁区词表（`sample_case.jsonl`·**实测、无声明件**）。"
                 "只在反例侧出现的：%s。" % "、".join(only_sample))
        q.append("AQ-1 反例/禁区类目（`sample_case.reason_category`：品牌一致性 / 原则性错误 / "
                 "措辞表达 / 审核问题 / 文化禁忌 / 合规红线）**没有声明件**，只在 L4 canonical 里实测得到；"
                 "它和规则词表（`l7.json → vocabulary.categories`）是**两套还是应归一**？"
                 "本件按「并集」处理、不做任何改名或合并。")

    # ⑤ 表行没有 PASS —— 三态筛选的第三腿当前是空的
    ex = result.get("exports") or {}
    if ex.get("PASS", {}).get("rows") == 0:
        w.append("**PASS 导出 0 行**：不是筛不出来，是表里确实没有一行 `状态=PASS`。"
                 "根因方向（本件未判）：引擎在「库内没有可依据条款」时按 fail-closed **拒答**，"
                 "而且「未命中 ≠ 合规」⇒ 不产出 PASS。⇒ PRD §5.1 的「按 PASS 筛选」"
                 "这条路**通着、但当前无数据可筛**。")

    # ⑥ NEEDS_INPUT 与「待审」共用一个 select 值
    j1 = (result.get("j1_cloud_vs_local") or {}).get("dims") or {}
    st = {k: v for k, v in (j1.get("状态", {}).get("server") or [])}
    ag = {k: v for k, v in (j1.get("Agent 结论", {}).get("server") or [])}
    if ag.get("NEEDS_INPUT") and "NEEDS_INPUT" not in st:
        w.append("`状态`（select，6 个选项）里**没有 `NEEDS_INPUT`** —— 实测 %d 行 `Agent 结论=NEEDS_INPUT`"
                 "在 `状态` 上落的是「待审」（由守衡写，记录历史可核：`after=\"待审\"` / `operator=守衡`）。"
                 "⇒ 按 `状态` 筛选时**分不出「真待审」与「引擎拒答/未判」**；要分开就得按 `Agent 结论`。"
                 % ag["NEEDS_INPUT"])
    return w, q


def verify(result: dict, rows: list | None = None) -> list:
    """J1–J6。**返回问题列表，空 = 过。**"""
    probs = []

    # J1 云端 vs 本机（离线时**看得见地跳过**，不是静默变绿）
    j1 = result.get("j1_cloud_vs_local") or {}
    if j1.get("status") == "checked":
        for dim, d in (j1.get("dims") or {}).items():
            if not d.get("equal"):
                probs.append("J1 %s 云端与本机不等：云端=%s 本机=%s"
                             % (dim, d.get("server"), d.get("local")))
    elif j1.get("status") != "skipped_offline":
        probs.append("J1 状态未知：%r" % (j1.get("status"),))

    # J2 风险类型必须在**两套词表的并集**里（见 controlled_risk_types 的出错留档）
    rt = result.get("risk_type") or {}
    if not rt.get("受控词表"):
        probs.append("J2 受控词表读不到（%s 与 %s 都空）⇒ 无法判定类型合法性"
                     % (L7JSON, SAMPLE_CASE))
    if rt.get("词表外类型"):
        probs.append("J2 出现两套词表都没有的风险类型：%s"
                     % json.dumps(rt["词表外类型"], ensure_ascii=False))
    # J2b 每一个报出来的类型都必须**指得出出处**（哪个词表、哪个文件）
    for t in (rt.get("风险类型_按条数加权") or {}):
        if t not in (rt.get("词表出处") or {}):
            probs.append("J2b 风险类型 %r 没有可追溯的词表出处" % t)

    # J3 每个统计块必须带覆盖率
    for dim, c in (result.get("coverage") or {}).items():
        if not {"有值", "未指定", "空", "total"} <= set(c):
            probs.append("J3 %s 的覆盖率块缺字段：%s" % (dim, sorted(c)))
        elif c["有值"] + c["未指定"] + c["空"] != c["total"]:
            probs.append("J3 %s 覆盖率三档之和 ≠ 总数（%d+%d+%d ≠ %d）"
                         % (dim, c["有值"], c["未指定"], c["空"], c["total"]))

    # J4 导出的「完整性」与「空」分开报
    for st, e in (result.get("exports") or {}).items():
        if e.get("rows") == 0 and e.get("state") != "empty_by_data":
            probs.append("J4 %s 导出 0 行，却被标成 %r（应为 empty_by_data）" % (st, e.get("state")))
        if e.get("rows", 0) > 0 and e.get("has_more") is not False and e.get("source") == "feishu":
            probs.append("J4 %s 导出 has_more=%r ⇒ 不是完整结果，不许当全部"
                         % (st, e.get("has_more")))
        if e.get("csv_rows") is not None and e["csv_rows"] != e.get("rows"):
            probs.append("J5 %s 落盘 CSV 行数 %s ≠ 服务端 %s"
                         % (st, e["csv_rows"], e.get("rows")))

    # J6 散文行不得被解析成风险类型 —— **独立重扫对账**（两套实现，见 _prose_recount）
    if rows is not None:
        rc = _prose_recount(rows)
        if rc["可解析行"] != rt.get("分母_可解析行"):
            probs.append("J6 可解析行数对不上独立重扫：报 %s ／ 重扫 %s"
                         % (rt.get("分母_可解析行"), rc["可解析行"]))
        if rc["散文行"] != rt.get("不可解析_散文行"):
            probs.append("J6 散文行数对不上独立重扫：报 %s ／ 重扫 %s"
                         % (rt.get("不可解析_散文行"), rc["散文行"]))
        if rc["空行"] != rt.get("空行"):
            probs.append("J6 空行数对不上独立重扫：报 %s ／ 重扫 %s"
                         % (rt.get("空行"), rc["空行"]))
        if (rt.get("分母_可解析行", 0) + rt.get("不可解析_散文行", 0)
                + rt.get("空行", 0)) != rt.get("分母_总行"):
            probs.append("J6 风险类型三档之和 ≠ 总行：%s+%s+%s ≠ %s"
                         % (rt.get("分母_可解析行"), rt.get("不可解析_散文行"),
                            rt.get("空行"), rt.get("分母_总行")))
    for sample in (rt.get("不可解析样本") or []):
        if _SEG.match(sample) or _SEG_PLAIN.match(sample):
            probs.append("J6 散文样本被判成可解析：%r" % sample[:40])
    return probs


# ══════════════════════════════════════════════════════════════════════
# 渲染
# ══════════════════════════════════════════════════════════════════════

def render_md(result: dict) -> str:
    L = []
    L.append("# 多维表统计与筛选导出（任务拆解 目标 21 · PRD §8.2）")
    L.append("")
    L.append("生成时间：%s ｜ 取样表：%s / %s ｜ 明细来源：**%s** ｜ rev：%s"
             % (result.get("generated_at"), result.get("dest", {}).get("base_token"),
                result.get("dest", {}).get("table_id"),
                (result.get("detail") or {}).get("source"),
                (result.get("detail") or {}).get("rev")))
    L.append("")
    L.append("> **统计口径**：品线 / 渠道等维度由 **飞书侧云端聚合**（`base +data-query`，"
             "服务端在完整表范围上算）产出 —— 这就是 PRD §8.2「多维表支持统计」指的那条路；"
             "本机同时复算一遍，两者必须逐格相等（判据 J1）。")
    L.append("")

    j1 = result.get("j1_cloud_vs_local") or {}
    L.append("## 〇、云端 vs 本机（判据 J1）")
    L.append("")
    if j1.get("status") == "checked":
        L.append("| 维度 | 云端聚合 | 本机复算 | 一致 |")
        L.append("|---|---|---|---|")
        for dim, d in (j1.get("dims") or {}).items():
            L.append("| %s | %s | %s | %s |" % (dim, _fmt(d.get("server")), _fmt(d.get("local")),
                                                "✅" if d.get("equal") else "❌"))
    else:
        L.append("**`skipped_offline`** —— 本次跑的是 `--snapshot`，不碰飞书 ⇒ "
                 "**J1 未执行**（看得见地跳过，不是静默变绿）。")
    L.append("")

    L.append("## 一、按品线 / 渠道统计（§8.2 前两样）")
    L.append("")
    for dim in ("产品线", "渠道"):
        c = (result.get("coverage") or {}).get(dim) or {}
        L.append("### %s" % dim)
        L.append("")
        L.append("分母：总 **%s** 行 ＝ 有值 %s ／ 未指定 %s ／ 空 %s"
                 % (c.get("total"), c.get("有值"), c.get("未指定"), c.get("空")))
        L.append("")
        L.append("| %s | 行数 | 占有值比 | 占全表比 |" % dim)
        L.append("|---|---|---|---|")
        for k, v in (c.get("取值") or {}).items():
            L.append("| %s | %d | %s | %s |"
                     % (k, v, _pct(v, c.get("有值")), _pct(v, c.get("total"))))
        L.append("")

    L.append("## 二、按风险类型统计（§8.2 第三样）")
    L.append("")
    rt = result.get("risk_type") or {}
    L.append("⚠️ **结论表里没有「风险类型」这一列**（`+field-list` 实测 18 列）。"
             "唯一的风险语义落点是 **`%s`**（text），且那一列只有一部分行是分类汇总 —— "
             "另一部分是守衡写回的散文。⇒ 下面是**在该列可解析范围内**的统计，"
             "**不是全表统计**。"
             % RISK_TYPE_SOURCE_FIELD)
    L.append("")
    L.append("分母：总 **%s** 行 ＝ 可解析 **%s** 行 ／ 散文（不可解析）**%s** 行 ／ 空 **%s** 行 "
             "⇒ **可解析覆盖率 %s**"
             % (rt.get("分母_总行"), rt.get("分母_可解析行"), rt.get("不可解析_散文行"),
                rt.get("空行"), _pct(rt.get("分母_可解析行"), rt.get("分母_总行"))))
    L.append("")
    tot = sum((rt.get("风险类型_按条数加权") or {}).values())
    prov = rt.get("词表出处") or {}
    L.append("| 风险类型 | 条数（按汇总里的 n 加权） | 占可解析条数比 | 词表出处 |")
    L.append("|---|---|---|---|")
    for k, v in (rt.get("风险类型_按条数加权") or {}).items():
        L.append("| %s | %d | %s | %s |" % (k, v, _pct(v, tot), prov.get(k, "❌ 无出处")))
    L.append("")
    if rt.get("词表外类型"):
        L.append("❌ **两套词表都没有的类型**：%s"
                 % json.dumps(rt["词表外类型"], ensure_ascii=False))
        L.append("")
    only_sample = [k for k, s in prov.items() if "反例词表" in s and "规则词表" not in s]
    L.append("★ **注意：这一列里并存着两套类目体系**（不是一套）：")
    L.append("")
    L.append("| 词表 | 出自 | 类目 |")
    L.append("|---|---|---|")
    L.append("| 规则词表 | `kb/l7/registry/l7.json → vocabulary.categories`（**声明件**） | %s |"
             % "、".join(k for k, s in prov.items() if "规则词表" in s))
    L.append("| 反例/禁区词表 | `kb/l4/canonical/sample_case.jsonl → reason_category`（**实测，无声明件**） | %s |"
             % "、".join(only_sample))
    L.append("")
    if only_sample:
        L.append("⇒ **只在反例侧出现的类型**：%s —— 它们由「自命中已定稿反例/禁区」那条判定路径产出"
                 "（Owner 2026-10-05 规则①），`l7.json` 那套是「规则命中」的类目。"
                 "**本件不做归一**（把 `措辞表达` 并进 `表述与术语准确性` 看着合理，"
                 "但没人裁之前合并 = 把两类风险并成一类）。等 Owner 一句话。"
                 % "、".join(only_sample))
        L.append("")
    L.append("受控词表合计（两套并集，哨兵 `未分类`/`unknown` 已剔除）：%d 类"
             % len(rt.get("受控词表") or []))
    L.append("")

    L.append("## 三、按 PASS / REVIEW / BLOCK 筛选导出（§5.1）")
    L.append("")
    L.append("| 状态 | 行数 | 完整性 | CSV |")
    L.append("|---|---|---|---|")
    for st in TRI_STATE:
        e = (result.get("exports") or {}).get(st) or {}
        L.append("| %s | %s | has_more=%s | %s |"
                 % (st, e.get("rows"), e.get("has_more"),
                    ("`%s`" % os.path.basename(e["csv"])) if e.get("csv") else "—"))
    L.append("")
    zero = [s for s in TRI_STATE if ((result.get("exports") or {}).get(s) or {}).get("rows") == 0]
    if zero:
        L.append("⚠️ **%s 导出 0 行 —— 这不是「导出失败」，是表里本来就没有该状态的行**"
                 "（`empty_by_data`）。筛子通着、只是没东西可筛。" % "、".join(zero))
        L.append("")
    L.append("状态分布（云端聚合，全表）：%s"
             % json.dumps((result.get("j1_cloud_vs_local") or {}).get("dims", {})
                          .get("状态", {}).get("server"), ensure_ascii=False))
    L.append("")

    L.append("## 四、判据")
    L.append("")
    probs = result.get("problems") or []
    if probs:
        for x in probs:
            L.append("- ❌ %s" % x)
    else:
        L.append("- ✅ J1 云端聚合 与 本机复算 **逐格相等**（或离线时可见跳过）")
        L.append("- ✅ J2 风险类型全在**两套词表的并集**内")
        L.append("- ✅ J2b 每个类型都指得出词表出处")
        L.append("- ✅ J3 每个统计块都带分母（有值 / 未指定 / 空）")
        L.append("- ✅ J4 0 行标 `empty_by_data`；非 0 行 `has_more=false`")
        L.append("- ✅ J5 落盘 CSV 行数 = 服务端 `records_count`")
        L.append("- ✅ J6 散文行未被解析成风险类型（独立重扫对账）")
    L.append("")

    warns = result.get("warnings") or []
    if warns:
        L.append("## 四·黄 —— 报黄不判红（已知 / 需人裁，**必须看得见**）")
        L.append("")
        for i, x in enumerate(warns, 1):
            L.append("%d. %s" % (i, x))
            L.append("")
    qs = result.get("open_questions") or []
    if qs:
        L.append("## 四·待裁 —— 留给 Owner 的问题（本件不代人裁）")
        L.append("")
        for x in qs:
            L.append("- %s" % x)
        L.append("")
    L.append("## 五、边界（照抄，别外推）")
    L.append("")
    L.append("1. **只读**：只 `+data-query` / `+record-list`（lark-cli 里都是 `Risk: read`）。"
             "**不建仪表盘、不建视图、不写任何一行。**")
    L.append("2. 结论表里有个**空仪表盘**（`blkBTSiCT1crpikn`，0 个组件）—— "
             "要不要往里放三张图，是**人的决定**，本件不代劳。")
    L.append("3. **风险类型列缺失**是**已测出的缺口**（不是本件的实现选择）："
             "§8.2 要按风险类型统计，而表里没有这一列。")
    L.append("")
    return "\n".join(L) + "\n"


def _fmt(x):
    if x is None:
        return "—"
    return json.dumps(x, ensure_ascii=False)


def _pct(a, b):
    if not b:
        return "—"
    return "%.1f%%" % (100.0 * (a or 0) / b)


def _safe_write_md(path: str, text: str) -> None:
    """`.md` 走 `/bin/cp` 通道（python 直写 `.md` ⇒ **宿主**看到的比真值多 4096 字节）。"""
    d = os.path.dirname(path) or "."
    os.makedirs(d, exist_ok=True)
    tmp = os.path.join(d, ".%s.swtmp" % os.path.basename(path))
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(text)
        subprocess.run(["/bin/cp", tmp, path], check=True)
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass
    if open(path, encoding="utf-8").read() != text:
        raise RuntimeError("安全写盘回读不符：%s" % path)


# ══════════════════════════════════════════════════════════════════════
# 主流程
# ══════════════════════════════════════════════════════════════════════

def run(snapshot: str | None = None, do_export: bool = True,
        out_dir: str = REPORTS, dest: dict | None = None) -> dict:
    dest = dest or destinations()
    if not dest.get("base_token") or not dest.get("table_id"):
        raise SystemExit("去向登记件里取不到 base/table：%s" % REGISTRY)
    vocab = controlled_risk_types()

    rows, meta = fetch_rows(dest, snapshot=snapshot)

    # ── 逐维度：云端算一次、本机复算一次 ───────────────────────────────
    j1 = {"status": "skipped_offline" if snapshot else "checked", "dims": {}}
    coverage = {}
    if not snapshot:
        for dim in SERVER_DIMS:
            try:
                srv = server_groupby(dim, dest)
            except SystemExit as e:
                j1["dims"][dim] = {"server": None, "local": None, "equal": False,
                                   "error": str(e)[:200]}
                continue
            loc = local_groupby(rows, dim)
            j1["dims"][dim] = {"server": _sorted_pairs(srv), "local": _sorted_pairs(loc),
                               "equal": _sorted_pairs(srv) == _sorted_pairs(loc)}
    for dim in ("产品线", "渠道", "内容类型", "状态", "Agent 结论", "送审版本"):
        coverage[dim] = coverage_of(rows, dim)

    risk = parse_risk_types(rows, vocab)

    # ── 三态筛选导出 ────────────────────────────────────────────────────
    exports = {}
    if do_export:
        for st in TRI_STATE:
            sub, smeta = fetch_rows(dest, states=[st], snapshot=snapshot)
            e = {"rows": len(sub), "has_more": smeta.get("has_more"),
                 "source": smeta.get("source"), "rev": smeta.get("rev"), "csv": None,
                 "csv_rows": None}
            if not sub:
                e["state"] = "empty_by_data"      # ★ 判据 J4：0 行不是失败
            else:
                e["state"] = ("complete" if smeta.get("has_more") is False else "partial")
                p = os.path.join(out_dir, "bitable-export-%s-latest.csv" % st)
                e["csv"] = p
                e["csv_rows"] = write_csv(sub, p)
            exports[st] = e

    result = OrderedDict()
    result["generated_at"] = _now()
    result["dest"] = {"base_token": dest["base_token"], "table_id": dest["table_id"],
                      "name": dest.get("name"), "source": dest.get("source")}
    result["detail"] = meta
    result["j1_cloud_vs_local"] = j1
    result["coverage"] = coverage
    result["risk_type"] = risk
    result["exports"] = exports
    result["warnings"], result["open_questions"] = _notes(result)
    result["problems"] = verify(result, rows)
    result["judges"] = {
        "J1": "云端聚合 vs 本机复算逐格相等",
        "J2": "风险类型必须在受控词表内",
        "J3": "每个统计块都带分母",
        "J4": "0 行 = empty_by_data；非 0 行须 has_more=false",
        "J5": "CSV 行数 = 服务端 records_count",
        "J6": "散文行不得被解析成风险类型（独立重扫对账）",
    }
    return result


def _sorted_pairs(pairs):
    """排序后比较 —— `+data-query` 不保证组顺序，逐格比的是**内容**不是行序。"""
    return sorted([[("" if k is None else str(k)), int(v)] for k, v in pairs],
                  key=lambda x: (-x[1], x[0]))


def _now():
    import datetime
    return datetime.datetime.now().astimezone().replace(microsecond=0).isoformat()


def write_artifacts(result: dict, out_dir: str = REPORTS) -> dict:
    os.makedirs(out_dir, exist_ok=True)
    jp = os.path.join(out_dir, "bitable-stats-latest.json")
    mp = os.path.join(out_dir, "bitable-stats-latest.md")
    txt = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    # `.json` 不在中招扩展名里 ⇒ 直写安全（AGENTS.md 逐扩展名实测）
    with open(jp, "w", encoding="utf-8") as fh:
        fh.write(txt)
    _safe_write_md(mp, render_md(result))
    import hashlib
    h = hashlib.sha256(txt.encode("utf-8")).hexdigest()
    with open(jp + ".sha256", "w", encoding="utf-8") as fh:
        fh.write("%s  %s\n" % (h, os.path.basename(jp)))
    return {"json": jp, "md": mp, "sha256": jp + ".sha256", "sha256_value": h}


# ══════════════════════════════════════════════════════════════════════
# 反向对照（把缺陷真造一遍）—— **全离线，一台真库都不碰**
# ══════════════════════════════════════════════════════════════════════

_FIXTURE = [
    # 8 行：状态分布 REVIEW 4 / BLOCK 2 / PASS 2；品线 吸奶器 3 / 监视器 2 / 未指定 2 / 空 1
    {"record_id": "rec1", "内容 ID": "AD-1", "产品线": "吸奶器", "渠道": "Meta",
     "内容类型": "image", "送审版本": "v1.0", "Agent 结论": "REVIEW", "置信度": 0.8,
     "问题数量": 2, "状态": ["REVIEW"],
     "问题分类汇总": "功效宣称-催乳与通乳宣称 1；背书与资质-监管认证宣称 1"},
    {"record_id": "rec2", "内容 ID": "AD-2", "产品线": "吸奶器", "渠道": "Meta",
     "内容类型": "text", "送审版本": "v1.0", "Agent 结论": "BLOCK", "置信度": 1.0,
     "问题数量": 1, "状态": ["BLOCK"], "问题分类汇总": "平台与促销-静音绝对化表述 2"},
    {"record_id": "rec3", "内容 ID": "AD-3", "产品线": "监视器", "渠道": "Google",
     "内容类型": "video", "送审版本": "v1.0", "Agent 结论": "PASS", "置信度": 0.95,
     "问题数量": 0, "状态": ["PASS"], "问题分类汇总": ""},
    {"record_id": "rec4", "内容 ID": "AD-4", "产品线": "监视器", "渠道": "",
     "内容类型": "video", "送审版本": "v1.0", "Agent 结论": "PASS", "置信度": 0.9,
     "问题数量": 0, "状态": ["PASS"], "问题分类汇总": ""},
    {"record_id": "rec5", "内容 ID": "AD-5", "产品线": "未指定", "渠道": "未指定",
     "内容类型": "text", "送审版本": "v1.0", "Agent 结论": "REVIEW", "置信度": 0.5,
     "问题数量": 3, "状态": ["REVIEW"],
     # ★ 散文行：**必须**整行判为不可解析（判据 J6 的正例）
     "问题分类汇总": "链已跑完（182s）。结论原文见对话与报告；本行由守衡在链返回后核对落表。"},
    {"record_id": "rec6", "内容 ID": "AD-6", "产品线": "未指定", "渠道": "社媒",
     "内容类型": "video", "送审版本": "v1.0", "Agent 结论": "REVIEW", "置信度": 0.3,
     "问题数量": 4, "状态": ["REVIEW"], "问题分类汇总": None},
    {"record_id": "rec7", "内容 ID": "AD-7", "产品线": "吸奶器", "渠道": "社媒",
     "内容类型": "image", "送审版本": "v1.0", "Agent 结论": "REVIEW", "置信度": 0.7,
     "问题数量": 1, "状态": ["REVIEW"],
     "问题分类汇总": "婴幼儿安全与场景-乘车安全 1"},
    {"record_id": "rec8", "内容 ID": "AD-8", "产品线": None, "渠道": "Meta",
     "内容类型": "image", "送审版本": "v1.0", "Agent 结论": "BLOCK", "置信度": 1.0,
     "问题数量": 2, "状态": ["BLOCK"],
     "问题分类汇总": "绝对化与安全承诺-虚假安全承诺 3"},
    # ★ **混行**（真实数据里就有）：前两段是好段，第三段被截断没有条数。
    #   严格口径 ⇒ **整行算散文**（损失可见）；放宽成"能解析几段算几段" ⇒
    #   这行的两个类型会被计入，而分母上看不出少了什么 —— 判据 J6 就是钉这个。
    {"record_id": "rec9", "内容 ID": "AD-9", "产品线": "吸奶器", "渠道": "Meta",
     "内容类型": "text", "送审版本": "v1.0", "Agent 结论": "REVIEW", "置信度": 0.6,
     "问题数量": 2, "状态": ["REVIEW"],
     "问题分类汇总": "功效宣称-疾病治疗宣称 1；平台与促销-促销紧迫感表述 1；背书与资质-专业头衔与合作"},
]


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

    import copy
    d = tempfile.mkdtemp(prefix="bitable-stats-selftest-")
    snap = os.path.join(d, "fx.ndjson")
    with open(snap, "w", encoding="utf-8") as fh:
        for r in _FIXTURE:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    base = run(snapshot=snap, do_export=True, out_dir=d,
               dest={"base_token": "FAKE", "table_id": "FAKE", "name": "fixture"})

    # ① 基座：真 fixture 必须过，且**离线时 J1 可见跳过**
    ck("①基座过", not base["problems"], base["problems"][:3])
    ck("①b J1 离线可见跳过", base["j1_cloud_vs_local"]["status"] == "skipped_offline",
       base["j1_cloud_vs_local"]["status"])

    # ② 统计数对得上（手工数：总 9 行；REVIEW 5 / BLOCK 2 / PASS 2）
    ck("②状态分母", base["coverage"]["状态"]["total"] == 9, base["coverage"]["状态"]["total"])
    ck("②b 品线覆盖率", base["coverage"]["产品线"]["有值"] == 6
       and base["coverage"]["产品线"]["未指定"] == 2
       and base["coverage"]["产品线"]["空"] == 1, base["coverage"]["产品线"])

    # ③ J4 反向：把 0 行导出的 state 从 empty_by_data 改成 failed ⇒ 必须红
    r = copy.deepcopy(base)
    r["exports"]["PASS"] = {"rows": 0, "state": "failed", "has_more": False, "csv": None}
    ck("③J4 0行误判为失败变红", any("J4 PASS" in x for x in verify(r)), verify(r)[:3])

    # ④ J4 反向：非 0 行却 has_more=true ⇒ 必须红（半页不许当全部）
    r = copy.deepcopy(base)
    r["exports"]["REVIEW"]["has_more"] = True
    r["exports"]["REVIEW"]["source"] = "feishu"
    ck("④J4 半页当全部变红", any("J4 REVIEW" in x and "has_more" in x for x in verify(r)),
       verify(r)[:3])

    # ⑤ J5 反向：CSV 行数与服务端不等 ⇒ 必须红
    r = copy.deepcopy(base)
    r["exports"]["BLOCK"]["csv_rows"] = r["exports"]["BLOCK"]["rows"] - 1
    ck("⑤J5 掉行变红", any("J5 BLOCK" in x for x in verify(r)), verify(r)[:3])

    # ⑥ J2 反向：塞一个受控词表外的风险类型 ⇒ 必须红
    r = copy.deepcopy(base)
    r["risk_type"]["风险类型_按条数加权"]["品牌一致性"] = 3
    r["risk_type"]["词表外类型"]["品牌一致性"] = 3
    ck("⑥J2 词表外类型变红", any("J2" in x and "品牌一致性" in x for x in verify(r)),
       verify(r)[:3])

    # ⑦ J2 反向：受控词表读不到 ⇒ 必须红（不许悄悄放行）
    r = copy.deepcopy(base)
    r["risk_type"]["受控词表"] = []
    ck("⑦J2 词表缺失变红", any("J2 受控词表读不到" in x for x in verify(r)), verify(r)[:3])

    # ⑦b J2b 反向：抹掉一个类型的词表出处 ⇒ 必须红（类型必须指得出来源）
    r = copy.deepcopy(base)
    r["risk_type"]["词表出处"].pop("功效宣称", None)
    ck("⑦b J2b 无出处变红", any("J2b" in x and "功效宣称" in x for x in verify(r)), verify(r)[:3])

    # ⑦c ★ 两套词表的**并集**必须真的生效 —— 拿只存在于反例侧的「品牌一致性」验：
    #     它在并集里（不该红），但**不能**被算成规则词表那一套。
    vocab = controlled_risk_types()
    ck("⑦c 反例侧类型在并集内", "品牌一致性" in vocab, list(vocab)[:3])
    ck("⑦c2 它的出处只指反例词表",
       "反例词表" in vocab.get("品牌一致性", "") and "规则词表" not in vocab.get("品牌一致性", ""),
       vocab.get("品牌一致性"))
    ck("⑦c3 规则侧类型不被误标成反例侧",
       "规则词表" in vocab.get("功效宣称", ""), vocab.get("功效宣称"))
    ck("⑦c4 哨兵不进词表", "unknown" not in vocab and "未分类" not in vocab, list(vocab))

    # ⑧ J3 反向：抹掉覆盖率字段 ⇒ 必须红
    r = copy.deepcopy(base)
    r["coverage"]["渠道"].pop("空", None)
    ck("⑧J3 缺分母变红", any("J3 渠道" in x for x in verify(r)), verify(r)[:3])

    # ⑨ J3 反向：三档之和对不上总数 ⇒ 必须红
    r = copy.deepcopy(base)
    r["coverage"]["产品线"]["有值"] += 5
    ck("⑨J3 分母不自洽变红", any("J3 产品线" in x and "≠" in x for x in verify(r)), verify(r)[:3])

    # ⑩ J6 反向：**把「整行全解析」放宽成「能解析几段算几段」** ⇒
    #    混行 rec9 的两个类型会被计入、散文样本变少 ⇒ 独立重扫必须抓到。
    global _row_segments
    keep = _row_segments

    def _partial(s):
        out = []
        for seg in [x for x in re.split(r"[；;]", s) if x.strip()]:
            m = _SEG.match(seg) or _SEG_PLAIN.match(seg)
            if m:
                out.append((m.group("type").strip(), int(m.group("n"))))
        return out or None

    try:
        _row_segments = _partial
        vocab = controlled_risk_types()
        wide = parse_risk_types(_FIXTURE, vocab)
        ck("⑩J6 放宽后混行被误计入", wide["分母_可解析行"] > base["risk_type"]["分母_可解析行"],
           (wide["分母_可解析行"], base["risk_type"]["分母_可解析行"]))
        ck("⑩b J6 独立重扫抓到它",
           any("J6 可解析行数对不上独立重扫" in x
               for x in verify(dict(base, risk_type=wide), _FIXTURE)),
           verify(dict(base, risk_type=wide), _FIXTURE)[:3])
    finally:
        _row_segments = keep

    # ⑪ 严口径下：混行与散文行**都**算不可解析（损失可见）
    ck("⑪散文/混行判为不可解析", base["risk_type"]["不可解析_散文行"] == 2,
       base["risk_type"]["不可解析_散文行"])
    ck("⑪b 风险类型条数加权", base["risk_type"]["风险类型_按条数加权"] == {
        "功效宣称": 1, "背书与资质": 1, "平台与促销": 2, "婴幼儿安全与场景": 1,
        "绝对化与安全承诺": 3}, base["risk_type"]["风险类型_按条数加权"])
    ck("⑪c 混行的类型**不许**进统计",
       "背书与资质-专业头衔与合作" not in json.dumps(base["risk_type"], ensure_ascii=False)
       or base["risk_type"]["风险类型_按条数加权"].get("功效宣称") == 1,
       base["risk_type"]["风险类型_按条数加权"])

    # ⑫ 三态导出：PASS 2 / REVIEW 5 / BLOCK 2，且 CSV 行数逐一对上
    ck("⑫导出三态行数", {k: base["exports"][k]["rows"] for k in TRI_STATE}
       == {"PASS": 2, "REVIEW": 5, "BLOCK": 2},
       {k: base["exports"][k]["rows"] for k in TRI_STATE})
    ck("⑫b CSV 行数=服务端", all(base["exports"][k]["csv_rows"] == base["exports"][k]["rows"]
                                for k in TRI_STATE), base["exports"])

    # ⑬ 产物：.md 走安全写盘、回读一致、json.sha256 在
    art = write_artifacts(base, d)
    ck("⑬产物齐", os.path.exists(art["json"]) and os.path.exists(art["md"])
       and os.path.exists(art["sha256"]), art)
    md = open(art["md"], encoding="utf-8").read()
    ck("⑬b md 含三样统计", "按风险类型统计" in md and "按品线 / 渠道统计" in md, len(md))
    ck("⑬c md 明写风险类型列缺失", "结论表里没有「风险类型」这一列" in md, len(md))
    import hashlib
    ck("⑬d sha256 对得上",
       hashlib.sha256(open(art["json"], encoding="utf-8").read().encode("utf-8")).hexdigest()
       == art["sha256_value"], art["sha256_value"])

    # ⑭ verify() 空结果不许恒绿：给一个空 dict 必须红
    ck("⑭空结果不恒绿", bool(verify({})), verify({}))

    shutil.rmtree(d, ignore_errors=True)
    print("bitable_stats --selftest：%d/%d" % (ok, ok + fail))
    for f in fails:
        print("  ✗", f)
    return 0 if fail == 0 else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="多维表统计与筛选导出（目标 21 · PRD §8.2）")
    ap.add_argument("--snapshot", help="离线：直接读这个 ndjson，不碰飞书（J1 记 skipped_offline）")
    ap.add_argument("--no-export", action="store_true", help="只统计，不导出三态 CSV")
    ap.add_argument("--out-dir", default=REPORTS)
    ap.add_argument("--no-artifacts", action="store_true", help="不落 kb/l7/reports 产物")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return _selftest()

    r = run(snapshot=a.snapshot, do_export=not a.no_export, out_dir=a.out_dir)
    print(render_md(r))
    if not a.no_artifacts:
        art = write_artifacts(r, a.out_dir)
        print("产物：%s ｜ %s ｜ %s" % (art["md"], art["json"], art["sha256"]))
        print("sha256：%s" % art["sha256_value"])
    return 3 if r["problems"] else 0


if __name__ == "__main__":
    sys.exit(main())
