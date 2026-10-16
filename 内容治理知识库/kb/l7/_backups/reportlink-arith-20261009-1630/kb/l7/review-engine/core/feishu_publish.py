#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""feishu_publish.py —— 把评审结论**发布到飞书**（云文档正文 + 登记在案的多维表格行）。

## 它补的是哪个断点（2026-10-03 实测）

评审链能出结论（`with_kb_evidence.py`），`feishu_adapter.py` 也能把结论映射成飞书外形 ——
**但那个适配器是 `local JSON fallback`**（`transport_status: json_fallback_pending_feishu_credentials`），
**它不写飞书**。第一次真正写进飞书是 2026-10-03 手工编排的（见
`kb/l7/reports/20261003-feishu-write-probe.md`）。本脚本把那次的编排固化下来。

## 谁写、写到哪（**从登记件现读，不硬编码**）

`kb/l7/registry/conclusion-destination.yaml` → `feishu-bitable-content-review`：
`base_token` / `table_id` / `view_id` / `wiki_token`；写入人 = `dsh-kb` profile 那个 app。

## 「从最顶格第 1 行写」怎么保证（2026-10-03 实测）

* **不传 `docs +create --title`**：把报告标题写成正文的**第一行 H1**，
  飞书会把该 H1 提为**文档标题**，正文紧随其后 —— 实测：
  `# 报告标题` → `<title>报告标题</title><h1>…</h1>` 会**重复**；
  只给 H1（不给 --title）→ `<title>报告标题</title>` ＋ 正文，**不重复、无前导空行**。
* 写**已存在文档**时用 `docs +update --command overwrite`（整篇覆盖），
  **不用 `append`** —— append 就是从中间/末尾写，那是本脚本明确不做的。

## 用法

    # ① 预演（默认，不写飞书）：只渲染 + 打印将写什么
    kb/kbpy l7/review-engine/core/feishu_publish.py \
        --review-json /tmp/rev.json --content-id AMZ-0001 \
        --channel Amazon --product-line 吸奶器 --version v1.0

    # ② 真写（新建云文档 + 表行 upsert）
    ... --apply

    # ③ 写进已存在文档（整篇覆盖，从第 1 行开始）
    ... --apply --doc <docx_token>

退出码：0 = 成功（含预演）｜ 3 = 拒发（层前置没过 / 结论是 NEEDS_INPUT）｜ 2 = 用法或依赖错
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
KB = HERE.parents[2]                      # …/kb
ROOT = HERE.parents[3]                    # kb/ 的上一级
REGISTRY = KB / "l7/registry/conclusion-destination.yaml"
REPORTS = KB / "l7/reports"
NODE_HELPER = KB / ".work/write_via_node.mjs"
PROFILE = "dsh-kb"
STATUS_PASS = {"PASS", "REVIEW", "BLOCK"}

#: 「报告链接」门槛 —— **PRD §5.3.4 / §8.3 / §17** 三处同口径：
#: 「问题数量 **≥ 3** 时才生成完整报告并返回链接」（1–2 条走逐条输出，不给链接）。
#: ⇒ 本件**按 PRD 执行**，门槛 = 3（落成判据见
#:   `applied_20261003.report_output.enforced_20261003`）。
#: ── 一次改判与回退（留痕，**勿据以行事**）──────────────────────────────────
#:   2026-10-03 晚曾先被改判为「每次都填」⇒ 门槛临时置 0；
#:   同日用户裁定「**不用改 PRD 规则，后续都按照 PRD 来做**」⇒ **已回退为 3**。
#:   全过程见 `applied_20261003.report_output_link_threshold_20261003_late`（含 reverted）。
REPORT_LINK_MIN_ISSUES = 3


def _lark() -> str:
    p = shutil.which("lark-cli")
    if p:
        return p
    cand = Path.home() / ".dsh/bin/lark-cli"
    if cand.exists():
        return str(cand)
    raise SystemExit("lark-cli 找不到（PATH 与 ~/.dsh/bin 都没有）")


def _lark_run(*args: str, allow_fail: bool = False) -> dict:
    cmd = [_lark(), "--profile", PROFILE, *args, "--as", "bot"]
    p = subprocess.run(cmd, capture_output=True, text=True)
    out = (p.stdout or "").strip()
    try:
        d = json.loads(out)
    except Exception:                     # noqa: BLE001
        if allow_fail:
            return {"ok": False, "raw": out or (p.stderr or "")}
        raise SystemExit("lark-cli 输出不是 JSON：%s" % (out or p.stderr)[:300])
    if not d.get("ok") and not allow_fail:
        raise SystemExit("lark-cli 失败：%s" % json.dumps(d.get("error"), ensure_ascii=False)[:300])
    return d


def destinations() -> dict:
    """从登记件读去向（唯一真源）。PyYAML 不在就退回窄正则（只取四个 token）。"""
    txt = REGISTRY.read_text(encoding="utf-8")
    try:
        import yaml                          # noqa: PLC0415
        d = yaml.safe_load(txt)
        for x in d.get("destinations", []):
            if x.get("id") == "feishu-bitable-content-review":
                return x
    except Exception:                        # noqa: BLE001
        pass
    out = {}
    for k in ("base_token", "table_id", "view_id", "wiki_token"):
        m = re.search(r"^\s*%s:\s*([^\s#]+)" % k, txt, re.M)
        if m:
            out[k] = m.group(1)
    if not out.get("base_token") or not out.get("table_id"):
        raise SystemExit("登记件里读不到 base_token / table_id：%s" % REGISTRY)
    return out


def l0_locate(anchor: str, sha: str) -> dict | None:
    """把 anchor（`#表名/record_id/字段名`）反查回 **L0 源记录**，拿飞书 `entry_url` 给报告用。

    为什么（2026-10-03，用户提出）：报告里只有 `anchor` + `source_sha256` 时，人要定位得自己把
    anchor 拆成「表名／记录 id／字段名」再去飞书里搜。L0 的落盘件里本来就有 `entry_url`
    （对齐时的**飞书记录直链**）与 `observed_at`，直接带出来最省事。

    ⚠️ **只做「与 L0 文件记录值比对」，不做重算** —— L0 的 sha 输入是 `record_fields` 这个字段 blob，
    本地 L0 文件里**不含**该 blob（只记了 `sha256_input="record_fields"` 这个字面量），
    所以「重算通过」在本地结构上不可能；能声明的是「与 L0 记录值逐字一致」。要真核对得点进飞书。
    """
    m = re.match(r"#([^/]+)/(rec[A-Za-z0-9]+)/(.+)$", str(anchor or ""))
    if not m:
        return None
    table, rec, field = m.group(1), m.group(2), m.group(3)
    # ★★ 2026-10-09（第十批）：**别把 L0 的目录深度写死**。
    #   病灶（实测，Owner 问「依据溯源都会带命中逐字原文+飞书链接了吧」时查出来）：
    #   原先是 `(KB / "l0").glob("*/*%s.json" % rec)` —— **只认两层** `l0/<表名>/<rec>.json`。
    #   而库里有**两种并存布局**：
    #     · 一层 `l0/<表名>/<rec>.json`                    1536 份（旧批次）
    #     · 三层 `l0/records/<表名>/<rec>.json`            2069 份（新批次）
    #   ⇒ 新批次那 **2069 份**在这里**永远返回 None** ⇒ 报告/云文档里那一条
    #     只有 `L0 逐字核对（原文层）：kb/l0/records/….json`（**本地路径，点不开**），
    #     没有「L0 定位（源数据·飞书）」那行。
    #   ⚠️ 同一个锚点、**同一份 L0 件**，`l0_verbatim()` 找得到（所以逐字核对印得出来）、
    #      `l0_locate()` 找不到 —— 两条函数读同一份数据却结论相反，
    #      于是分裂成「**有逐字核对的没有直链，有直链的没有逐字核对**」。
    #   实测样本（图片单 `rv-20261009-102513`）：5 条依据里 **2 条**（`recvw7XJiS5DGY` /
    #      `recvw7XJiSUC86`）落在三层布局 ⇒ 没直链；另 3 条落在一层 ⇒ 有直链。
    #   改法：用 `rglob`（任意深度），但**优先非归档件** —— `_archive/` 里是
    #      superseded 的旧副本，直链可能指向已删记录，只在没有活件时才退用它。
    #   改法：用 `rglob("*%s.json" % rec)` —— **通配前缀 + 任意深度**。
    #   ⚠️ **前缀通配是必须的，别写成 `rglob("%s.json" % rec)`**：L0 件有两种**文件名形态**，
    #      两种都真实存在、且**分别对应两种目录深度**：
    #        · `l0/<分类>/feishu_bitable_record__<base>__<rec>.json`  （**带前缀**，两层，1536 份）
    #        · `l0/records/<表名>/<rec>.json`                        （**纯 rec 名**，三层，1813 份）
    #      只写纯 rec 名 ⇒ **带前缀那 1536 份全部找不到** —— 这是我自己第一版改错的地方，
    #      被 `selftest_coverage` 的 **E6** 抽样当场照出来（它报「一层 0 份抽样」）。
    #      优先**非归档**件（`_archive/` 里是 superseded 旧副本，直链可能指向已删记录），
    #      只在没有活件时才退用它。
    cands = [p for p in sorted((KB / "l0").rglob("*%s.json" % rec))
             if "_archive" not in p.parts]
    if not cands:
        cands = sorted((KB / "l0").rglob("*%s.json" % rec))
    for p in cands:
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception:                    # noqa: BLE001
            continue
        l0sha = d.get("sha256")
        return {"entry_url": d.get("entry_url"), "table": table, "record_id": rec, "field": field,
                "observed_at": d.get("observed_at"), "path": d.get("path"),
                "l0_file": str(p.relative_to(KB.parent)), "l0_sha256": l0sha,
                "sha_match": (bool(sha) and l0sha == sha)}
    return None


def l2_unit_of(article_no: str, anchor: str) -> str | None:
    """从 L4 canonical 的 `evidence_units` 里按 anchor 反查 L2 单元 id（溯源第三段的落点）。"""
    if not article_no:
        return None
    for p in (KB / "l4/canonical").glob("*.jsonl"):
        try:
            for line in p.read_text(encoding="utf-8").splitlines():
                if article_no not in line:
                    continue
                for u in (json.loads(line).get("evidence_units") or []):
                    if u.get("anchor") == anchor:
                        return u.get("unit_id")
        except Exception:                    # noqa: BLE001
            continue
    return None


def l1_pointer(anchor: str) -> dict | None:
    """把 anchor 反查回 **L1 抽取件** 与对应段落（溯源第三段的上一环）。

    为什么（2026-10-03，用户要求「报告里依旧字段溯源 L0/L1/L2/L3」）：报告原先有 L4 条款号、L3 规则与命中片段、
    L2 单元 id、L0 源记录直链，**唯独缺 L1**。L1 是「按字段抽取」那一层，落点是
    `kb/l1/<子库>/bitable__<base>__<rec>.json`，段落按 `field_name` 对齐 anchor 的第三段。
    """
    m = re.match(r"#([^/]+)/(rec[A-Za-z0-9]+)/(.+)$", str(anchor or ""))
    if not m:
        return None
    table, rec, field = m.group(1), m.group(2), m.group(3)
    for p in (KB / "l1").glob("*/*%s.json" % rec):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception:                    # noqa: BLE001
            continue
        seg = None
        for s in (d.get("segments") or []):
            if s.get("anchor") == str(anchor) or s.get("field_name") == field:
                seg = s
                break
        return {"l1_file": str(p.relative_to(KB.parent)),
                "resource_key": d.get("resource_key"),
                "extractor_version": d.get("extractor_version"),
                "source_sha256": d.get("source_sha256"),
                "field": field, "table": table, "record_id": rec,
                "segment_kind": (seg or {}).get("kind"),
                "segment_text": (seg or {}).get("text"),
                "segment_anchor": (seg or {}).get("anchor") or str(anchor)}
    return None


def l0_verbatim(anchor: str, excerpt: str) -> dict | None:
    """在 `kb/l0/records/<表>/<rec>.json` 的 `fields` 里取该字段原文，与报告摘录做**逐字核对**。

    2026-10-03 补：之前只带了「L0 定位 + sha 比对」，但**原文层其实可以本地核对** ——
    `kb/l0/records/**` 的落盘件里有 `fields[<字段>].value`（`review.py:305` 回的就是它）。
    判据：摘录整串出现在 L0 字段值里 = 逐字命中；只有前缀出现 = 部分命中；都不出现 = 不一致。
    """
    m = re.match(r"#([^/]+)/(rec[A-Za-z0-9]+)/(.+)$", str(anchor or ""))
    if not m:
        return None
    table, rec, field = m.group(1), m.group(2), m.group(3)
    for p in (KB / "l0/records").glob("*/%s.json" % rec):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception:                    # noqa: BLE001
            continue
        cell = (d.get("fields") or {}).get(field) or {}
        val = cell.get("value") if isinstance(cell, dict) else cell
        if not isinstance(val, str):
            val = json.dumps(val, ensure_ascii=False)
        ex = str(excerpt or "").strip()
        if not ex or not val:
            verdict = "no_excerpt"
        elif ex in val:
            verdict = "verbatim_hit"
        elif ex[:20] and ex[:20] in val:
            verdict = "partial"
        else:
            verdict = "mismatch"
        return {"l0_file": str(p.relative_to(KB.parent)), "entry_url": d.get("entry_url"),
                "observed_at": d.get("observed_at"), "field": field, "value": val,
                "verdict": verdict}
    return None


def render(rev: dict, meta: dict) -> str:
    """渲染报告正文。★ 第 1 行就是标题 H1（不传 --title，避免标题重复）。"""
    r = rev["decision"]
    pf = (rev.get("evidence_meta") or {}).get("layer_preflight") or {}
    sess = {}
    for k, v in (pf.get("details") or {}).items():
        ss = v.get("skill_sessions") or {}
        sess[k] = ss.get(k) if isinstance(ss, dict) else None
    L = ["# 内容审查报告 · %s" % r.get("review_id"), ""]
    # ★ 用户原提问**放在最前**（用户 2026-10-03：「放在内容 id 前面，方便查看」）
    if (meta.get("question") or "").strip():
        L += ["- 用户原提问：%s" % meta["question"].strip()]
    L += ["- 内容 ID：`%s` ｜ 渠道：%s ｜ 产品线：%s ｜ 送审版本：%s"
          % (meta["content_id"], meta.get("channel") or "—（本单无可核来源）",
             meta.get("product_line") or "—（本单无可核来源）", meta.get("version") or "—")]
    L += ["- 结论：**%s** ｜ 问题数量：**%s** ｜ 置信度 %s（启发式，未做金标标定）"
          % (r.get("decision"), r.get("issue_count"), r.get("confidence"))]
    L += ["- content_version：`%s`" % r.get("content_version")]
    L += ["- 层前置：BASE `%s` ｜ mode=`%s` ｜ 红合计 %s ｜ 会话 %s"
          % (pf.get("base"), pf.get("mode"), pf.get("red_total"), json.dumps(sess, ensure_ascii=False))]
    L += ["", "## 一、问题分类汇总", "", "| 分类 | 条数 |", "|---|---|"]
    for k, v in (r.get("issue_summary_by_category") or {}).items():
        L.append("| %s | %s |" % (k, v))
    L += ["", "## 二、完整清单（%s 条）" % r.get("issue_count"), ""]
    for i, it in enumerate(r.get("risk_items") or [], 1):
        ev = it.get("evidence") or {}
        L += ["### %d. 【%s】%s · %s" % (i, it.get("risk_type"), it.get("priority_tier"), it.get("action")), ""]
        L += ["- 命中：%s" % str(it.get("original_text") or "").replace("\n", " ")]
        L += ["- 条款号：**%s** ｜ 规则码：%s" % (ev.get("article_no") or "（无）", it.get("rule_code") or "—")]
        L += ["- 依据：库 %s ｜ anchor `%s` ｜ source_sha256 `%s…`"
              % (ev.get("library") or "—", ev.get("anchor") or "—", str(ev.get("source_sha256") or "")[:24])]
        L += ["- 逐字摘录：%s" % str(ev.get("excerpt") or "—").replace("\n", " ")]
        # ── L0 定位（2026-10-03 加，用户要求「方便定位」）────────────────────
        # anchor + sha 本身不可点；这里把 L0 源记录的**飞书直链**带出来，并标明 sha 是
        # 「与 L0 记录值比对」而不是「重算」（后者本地结构上不可能，见 l0_locate docstring）。
        loc = l0_locate(ev.get("anchor"), ev.get("source_sha256"))
        if loc and loc.get("entry_url"):
            L += ["- **L0 定位（源数据·飞书）**：%s" % loc["entry_url"]]
            L += ["  - 表 `%s` ／ 记录 `%s` ／ 字段 `%s` ／ 对齐时间 `%s` ／ 库内路径 `%s`"
                  % (loc["table"], loc["record_id"], loc["field"],
                     loc.get("observed_at") or "—", loc.get("l0_file") or "—")]
            L += ["  - L0 sha256 `%s`：%s"
                  % (str(loc.get("l0_sha256") or "")[:24] + "…",
                     "与报告引用值**逐字一致** ✅（注意：这是**比对**，不是重算 —— "
                     "L0 的 sha 输入是 `record_fields` blob，本地 L0 件不含该 blob）"
                     if loc.get("sha_match") else
                     "**与报告引用值不一致** ❌ —— 需人工核对（可能 L0 已重新对齐）")]
        unit = l2_unit_of(ev.get("article_no"), ev.get("anchor"))
        if unit:
            L += ["  - L2 单元 `%s`（可回 `kb/l2/units.jsonl` 查逐字）" % unit]
        # ── L0 原文层逐字核对（2026-10-03 补：原文其实可以本地核对）──────────────
        vb = l0_verbatim(ev.get("anchor"), ev.get("excerpt") or it.get("original_text"))
        if vb:
            mark = {"verbatim_hit": "**逐字命中 ✅**（摘录整串出现在 L0 字段值里）",
                    "partial": "**部分命中 ⚠️**（只有前缀出现在 L0 字段值里）",
                    "mismatch": "**不一致 ❌**（摘录在 L0 字段值里找不到 —— 需人工核对）",
                    "no_excerpt": "（本轮摘录为空，未做逐字核对）"}[vb["verdict"]]
            L += ["- **L0 逐字核对（原文层）**：`%s` ／ 字段 `%s` ／ %s"
                  % (vb["l0_file"], vb["field"], mark)]
            L += ["  - L0 原文（截断 160 字）：`%s`" % str(vb["value"])[:160].replace("\n", " ")]
        # ── L1（2026-10-03 补：四段溯源里原来缺这一环）──────────────────────────
        l1 = l1_pointer(ev.get("anchor"))
        if l1:
            L += ["- **L1 抽取**：`%s` ／ 段落 `%s`（field=`%s` ／ kind=%s ／ extractor=%s）"
                  % (l1["l1_file"], l1["segment_anchor"], l1["field"],
                     l1.get("segment_kind") or "—", l1.get("extractor_version") or "—")]
            L += ["  - 该件 `source_sha256` `%s…` —— 与 L0 同源（L1 只抽不改，sha 逐层沿用）"
                  % str(l1.get("source_sha256") or "")[:24]]
        L += ["- 修改建议：%s" % (it.get("suggestion") or "（本入口本轮未给出修改建议）"), ""]
    L += ["## 三、溯源（逐层：L4 → L3 → L2 → L1 → L0）", "",
          "1. **L4 条款号**：见上逐条「条款号」",
          "2. **L3 规则与命中片段**：见上「命中 / 逐字摘录」",
          "3. **L2 单元**：见上「L2 单元」（可回 `kb/l2/units.jsonl` 查逐字）",
          "4. **L1 抽取件**：见上「L1 抽取」—— 按字段抽取的那一层，`source_sha256` 与 L0 同源（只抽不改）",
          "5. **L0 源数据**：见上「L0 定位（源数据·飞书）」—— 直链点开就是飞书里的**原始记录**；",
          "   sha 做的是**与 L0 记录值比对**（本地无法重算：`sha256_input=record_fields`，blob 不在本地 L0 件里）", "",
          "---",
          "> 结论由引擎 `with_kb_evidence.py` 产出；条款号 / anchor / sha / L0 直链均取自引擎输出与 `kb/l0` 落盘件，未手写。"]
    return "\n".join(L) + "\n"


def _save_local(name: str, body: str) -> str:
    """把渲染稿留底。⚠️ 往库内写 `.md` 一律走 node 通道（python 直写会带 4096 字节信封）。"""
    REPORTS.mkdir(parents=True, exist_ok=True)
    dst = REPORTS / name
    if NODE_HELPER.exists():
        p = subprocess.run(["node", str(NODE_HELPER), str(dst)], input=body,
                           capture_output=True, text=True)
        if p.returncode == 0:
            return str(dst)
    dst = dst.with_suffix(".txt")             # 退路：.txt 不受信封影响
    dst.write_text(body, encoding="utf-8")
    return str(dst)


def resolve_facets(a, rev):
    """素材属性（渠道 / 产品线）取值：**命令行 > review JSON 的 `evidence_meta.material_facets` > 空**。

    ★ 为什么发布件也要读 JSON（2026-10-06，Owner 报「文案类送审，文档里两格都是空的」）：
      原先这两格**只认命令行参数**（`--channel` / `--product-line`，缺省 `""`）——
      上游没传就恒空：云文档渲染成 `渠道：— ｜ 产品线：—`，表行按 PRD 兜成「未指定」。
      而引擎其实**已经把推好的值落在 JSON 里**（`with_kb_evidence.py::_derive_material_facets`）。
      ⇒ 改为一并认 JSON：**空必须是"确实没有可核来源"，不能是"没人给我传"**。
    返回 `{channel, product_line, source:{…}}`；取不到就是空串 —— **不编**。
    """
    mf = (rev.get("evidence_meta") or {}).get("material_facets") or {}
    src_from = mf.get("from") or {}
    out = {"channel": "", "product_line": "", "source": {}}
    for key, cli in (("channel", a.channel), ("product_line", a.product_line)):
        v = (cli or "").strip()
        if v:
            out[key] = v
            out["source"][key] = "命令行 --%s" % key.replace("_", "-")
            continue
        v = str(mf.get(key) or "").strip()
        if v:
            out[key] = v
            out["source"][key] = "引擎 JSON material_facets（%s）" % (src_from.get(key) or "来源未标")
        else:
            out["source"][key] = "本单无可核来源（未编）"
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--review-json", required=True, help="with_kb_evidence.py --json 的输出")
    ap.add_argument("--content-id", default=None,
                    help="不填则自动发号 `AD-YYYYMMDD-NNN`（PRD §5.4 业务编号；按天自增、永不复用；"
                         "序号由表内已有行推导 —— 用户只说素材时不该被追问元数据）")
    ap.add_argument("--channel", default="")
    ap.add_argument("--product-line", default="")
    ap.add_argument("--version", default="v1.0")
    ap.add_argument("--content-type", default="")
    ap.add_argument("--question", default="", help="送审时**用户的原提问**：写入表「送审问题」列 ＋ 报告正文一行"
                                                   "（2026-10-03 用户裁定 (a)+(b)）；不给则不写该列")
    ap.add_argument("--doc", default=None, help="写进已存在文档（整篇覆盖，从第 1 行开始）")
    ap.add_argument("--apply", action="store_true", help="不加 = 预演（不写飞书）")
    ap.add_argument("--allow-waived-preflight", action="store_true",
                    help="层前置是 waived/absent 时也允许发布（默认拒发）")
    ap.add_argument("--allow-no-decision-owner", action="store_true",
                    help="判定主体缺失时也允许发布（默认拒发）—— 防线2 的兜底，缺了就该发不出去")
    a = ap.parse_args()

    rev = json.loads(Path(a.review_json).read_text(encoding="utf-8"))
    r = rev.get("decision") or {}
    # ── 形状守卫（2026-10-03）：`decision` 必须是**对象** ─────────────────────
    # 实测：把「无闸门那扇门」（`review.py` 直调 = kb-content-review 自己的报告）产出的 JSON
    #   喂进来时，`decision` 是**字符串**（"PASS"）⇒ 下面 `r.get(...)` 抛 AttributeError、
    #   进程带栈退出（exit 1），看起来像脚本坏了。**其实这是入口用错了**，要明说而不是崩。
    #   与防线1 合起来：后门产物既跑不出带闸门的报告，也发不进飞书 —— 缺哪一环都看得见。
    if not isinstance(r, dict):
        print("拒发：这份结论不是 `with_kb_evidence.py` 的形状（`decision` = %s，应为对象）。"
              % type(r).__name__)
        print("      多半是**直调内部引擎**（kb-content-review/scripts/review.py）产出的裸报告 ——")
        print("      它没有层前置、没有判定主体、没有发布字段（防线1 自 2026-10-03 起已拒直调）。")
        print("      请重跑：with_kb_evidence.py … --require-layer-preflight <BASE> --decision-owner <skill-id>")
        return 2
    pf = (rev.get("evidence_meta") or {}).get("layer_preflight") or {}
    do = (rev.get("evidence_meta") or {}).get("decision_owner") or {}

    # 元数据自动化（2026-10-03）：用户只丢素材时**不许回头追问**内容 ID/渠道/版本。
    # ★ 内容 ID 形态改为 **PRD §5.4 的业务编号**（2026-10-03 用户裁定「内容 ID 按照你的建议」）：
    #   `AD-YYYYMMDD-NNN` —— 按天自增、**永不复用**。序号从**表内已有行**推导（`内容 ID` 列里
    #   同日前缀的最大序号 + 1），所以**不需要额外台账文件**；同一内容重发也拿新号
    #   （口径 = 「每次审查一行」，见 registry `applied_20261003.row_per_review`）。
    #   原实现 `AUTO-<content_version 前 12 位>`：内容哈希 ⇒ 同文恒同号，与 PRD §5.4 相反
    #   （登记在 registry 的 `GAP-RO-6` ②），故本条替换它。
    #   ⚠️ 已知边界：`+record-list` 有分页上限；行数极大时序号推导可能偏小（届时改台账发号）。
    if not a.content_id:
        _day = time.strftime("%Y%m%d")
        _prefix = "AD-%s-" % _day
        _d0 = destinations()
        _got = _lark_run("base", "+record-list", "--base-token", _d0["base_token"],
                         "--table-id", _d0["table_id"], "--format", "json", allow_fail=True)
        _d = _got.get("data") or {}
        _names = _d.get("fields") or []
        try:
            _ci = _names.index("内容 ID")
        except ValueError:                       # noqa: PERF203
            _ci = 0
        _mx = 0
        for _row in (_d.get("data") or []):
            _v = str(_row[_ci] or "") if _ci < len(_row) else ""
            if _v.startswith(_prefix):
                try:
                    _mx = max(_mx, int(_v.rsplit("-", 1)[1]))
                except Exception:                # noqa: BLE001
                    pass
        a.content_id = "%s%03d" % (_prefix, _mx + 1)
        print("元数据：内容 ID 自动发号 = %s（PRD §5.4 业务编号形态；按天自增、永不复用；"
              "序号由表内已有行推导）" % a.content_id)

    # ── 前置：层前置必须真过；结论必须是三态之一 ──────────────────────────
    if not (pf.get("mode") == "enforced" and pf.get("ok") and not pf.get("red_total")):
        if not a.allow_waived_preflight:
            print("拒发：层前置不是 enforced+ok（当前 mode=%s ok=%s 红=%s）。"
                  % (pf.get("mode"), pf.get("ok"), pf.get("red_total")))
            print("      要带 BASE 重跑：with_kb_evidence.py … --require-layer-preflight <BASE>")
            return 3
        print("[warn] 层前置是 %s，按 --allow-waived-preflight 继续（**该结论不构成走过 L4–L7 的证据**）"
              % pf.get("mode"))
    # ── 防线2（2026-10-03）：判定主体必须有 —— 否则发不出去 ────────────────
    # 为什么放在这一层：引擎侧已 fail-closed，这里是**兜底**（引擎被显式豁免时仍会走到这）。
    # 更要紧的是——「发不出去」是用户**当天就能看见**的信号，不必等人去翻 evidence_meta。
    if not do.get("skill"):
        if not a.allow_no_decision_owner:
            print("拒发：**判定主体缺失**（evidence_meta.decision_owner.mode=%s）。" % do.get("mode"))
            print("      层前置只证明「证据管道通了」，不证明「有人按专项规程判过」。")
            print("      要带判定主体重跑：with_kb_evidence.py … --decision-owner <skill-id>"
                  "（按 kb-review 让位表，如 图片安全审查）")
            return 3
        print("[warn] 判定主体缺失（mode=%s），按 --allow-no-decision-owner 继续"
              "（**该结论不构成「专项判过」的证据**）" % do.get("mode"))
    if r.get("decision") not in STATUS_PASS:
        print("拒发：结论是 %s（NEEDS_INPUT = 没有结论可发）" % r.get("decision"))
        return 3

    fac = resolve_facets(a, rev)
    print("①·素材属性：渠道=%r（%s）｜ 产品线=%r（%s）"
          % (fac["channel"], fac["source"]["channel"],
             fac["product_line"], fac["source"]["product_line"]))
    meta = {"content_id": a.content_id, "channel": fac["channel"],
            "product_line": fac["product_line"], "version": a.version,
            # 用户原提问（(b) 报告正文用）：命令行给的优先，其次取 review JSON 里的 submit_question
            "question": (a.question or "").strip() or (r.get("submit_question") or "")}
    body = render(rev, meta)
    assert body.startswith("# "), "正文第一行必须是标题 H1（保证从最顶格第 1 行写）"
    local = _save_local("%s.feishu.md" % (rev.get("decision", {}).get("review_id") or "report"), body)
    print("① 渲染完成：%d 字节 ｜ 本地留底 %s ｜ 第一行 = %r"
          % (len(body.encode()), local, body.splitlines()[0]))

    # ── 报告链接门槛（**现行 = 0：每次都填**；历史与依据见常量处注释 ＋ registry）────
    # 历史（2026-10-03 早先，门槛 3）：把「建文档」也一起挡，理由是云文档在这条流程里只有一个用途
    #   —— 被「报告链接」指向；只挡列不挡文档，会让每条 <3 的单留下**没人能点到的孤儿文档**
    #   （下次同内容重发时 prev_doc 查不到、再建一份）。
    # 现行（2026-10-03 晚，用户改判「每次都填」）：门槛 0 ⇒ link_ok 恒真，
    #   链接列与云文档**恒同现**，孤儿文档的成因不复存在，故该顾虑随门槛一起失效。
    n_issues = int(r.get("issue_count") or 0)
    link_ok = n_issues >= REPORT_LINK_MIN_ISSUES

    dest = destinations()
    print("② 去向（读登记件）：table=%s ｜ base=%s" % (dest.get("table_id"), dest.get("base_token")))
    if not a.apply:
        print("③ 预演结束（未写飞书）。要真写：加 --apply")
        return 0

    tmp = Path("/tmp/kb-feishu-publish.md")
    tmp.write_text(body, encoding="utf-8")          # 给 lark-cli 读的临时稿（/tmp，不入库）

    # ── ③ 先查同 内容 ID 的既有行（拿到 record_id 与既有报告链接 ⇒ 文档维度也幂等）──
    # ⚠️ 2026-10-03 实测坑：`+record-search` 默认输出是 **markdown 表格**（json.loads 会失败），
    #    必须显式 `--format json`；记录 id 在 `data.record_id_list`（不是 data.records）。
    found = _lark_run("base", "+record-search", "--base-token", dest["base_token"],
                      "--table-id", dest["table_id"], "--keyword", a.content_id,
                      "--search-field", "内容 ID", "--format", "json", allow_fail=True)
    fdata = found.get("data") or {}
    rids = fdata.get("record_id_list") or []
    # ── ★★ 用户 2026-10-03 裁定：**每次审查新增一行**（不再按「内容 ID」upsert 更新既有行）──
    #   依据：PRD §5.4「用于系统记录、流转、统计。**每条审查生成一份 JSON**」＋
    #   §10「审核记录绑定内容版本」。PRD 全文**没有**要求按「内容 ID」去重 ——
    #   原 upsert 是**实现选择**，其后果（复审在表里看不见、且会覆盖行内真实值）已由用户裁定改掉。
    #   ⚠️ 已知代价：同一内容会有**多行、且「内容 ID」相同**（根因：内容 ID 仍用内容哈希，
    #   而 PRD §5.4 要的是业务编号 `AD-YYYYMMDD-NNN`）—— 登记在 registry 的 `GAP-RO-6`；
    #   本次**未改 ID 算法**（该件 `do_not`：判定前不得改）。历史行一律不动。
    rid = None
    prev_doc = None
    print("③ 既有同「内容 ID」行 %d 条（本单**新增一行**，不更新它们）" % len(rids))

    # ── ④ 云文档：--doc 指定 > 新建（**不再复用上一单的文档**）──────────────────
    #     每单一行 ⇒ 每单报告各归本行；复用会把**上一单的报告整篇覆盖**，毁掉留痕。
    #     门槛仍按 PRD：问题数 ≥ 3 才建文档（常量 REPORT_LINK_MIN_ISSUES，见其注释）。
    url = ""
    if link_ok or a.doc:
        target = a.doc
        if target:
            _lark_run("docs", "+update", "--doc", target, "--command", "overwrite",
                      "--content", "@%s" % tmp, "--doc-format", "markdown")
            url = "https://momcozy-in.feishu.cn/docx/%s" % target
            print("④ 云文档：整篇覆盖（--doc 指定）→ %s" % url)
            if a.doc and not link_ok:
                print("   ⚠️ 问题数 %d < %d，但调用方**显式点名** --doc ⇒ 按人令覆盖该文档"
                      "（人的显式动作，不是自动行为）；「报告链接」列**仍按 PRD 留空**。"
                      % (n_issues, REPORT_LINK_MIN_ISSUES))
        else:
            d = _lark_run("docs", "+create", "--content", "@%s" % tmp, "--doc-format", "markdown")
            doc = (d.get("data") or {}).get("document") or {}
            url = doc.get("url")
            print("④ 云文档：新建 → %s" % url)
    else:
        print("④ 云文档：跳过（问题数 %d < %d ⇒ 按 PRD 不生成报告；报告正文见本地 %s）"
              % (n_issues, REPORT_LINK_MIN_ISSUES, local))

    # ── ⑤ 表行 upsert（同 内容 ID 已存在就更新，不新增重复行）───────────────
    fields = {
        "内容 ID": a.content_id,
        "Agent 结论": r.get("decision"),
        "问题数量": r.get("issue_count"),
        "问题分类汇总": "；".join("%s %s" % (k, v) for k, v in (r.get("issue_summary_by_category") or {}).items()),
        "置信度": r.get("confidence"),
        # ★ 门槛位：< 3 时**显式写空串**（不是省略键）—— 更新既有行时省略键 = 保留旧值，
        #   那就又把上一次写进去的链接留下了（2026-10-02 清空那 6 行要的正是「清空」语义）。
        #
        # ★★ 2026-10-09（Owner：「这 3 个要改成一致的」）：**库侧不再往这一格写链接** ──────
        #   病灶（实测 16:24 那单，逐字可核）：
        #     卡上链接 = `docx/M7DbdQUvbopAkmxGdsRccGstnTg`（守衡那份**合并报告**）
        #     表里链接 = `docx/Y2Gxd8BAbonVKrxgPWQcKkwRneb`（**库侧这份**）
        #     ⇒ 同一单两份文档、两个链接。成因：库侧只在**它自己** ≥3 时建文档
        #       （本单库侧 5 条 ⇒ 建了），而它建完把 URL **upsert 进同一行**、
        #       且跑在守衡落表**之后** ⇒ 守衡写的合并链接被**覆盖**。
        #   ⇒ 现在这一格**只由守衡写**（它按「卡里那个数」建合并报告，与卡同源）。
        #     库侧这份仍会建（要留档就留），只是**不抢卡上/表上那一格**。
        #     判据：这一格的值必须与**卡上那个链接**相同 —— 卡上没有时留空。
        #   ⚠️ 库侧自己的那份文档**仍然生成**（`link_ok` 逻辑一字未动）——
        #     这里改的只是"写不写进表里那一格"，不是"建不建文档"。
        "报告链接": "",
        "状态": [r.get("decision")],
    }
    # ★★ 元数据（内容类型 / 渠道 / 产品线 / 送审版本）**不许用占位值覆盖既有真实值** ──────
    #   缺陷实测两次（2026-10-03）：11:05 rev71 产品线「吸奶器」→「未指定」（非本单）；
    #   21:26 rev77 内容类型「广告语」→「未指定」（本单）。两次均已人工恢复原值。
    #   现行规则：**更新既有行**⇒ 只写调用方真给了值的键（省略键 = 行内旧值保留，省略就是「不动」）；
    #            **新建行**⇒ 没有旧值可保留，缺的补 PRD 默认（「未指定」/「v1.0」）。
    _meta = {"内容类型": a.content_type, "渠道": fac["channel"],
             "产品线": fac["product_line"], "送审版本": a.version}
    for _k, _v in _meta.items():
        _s = (_v or "").strip()
        if _s in ("—",):
            _s = ""
        if rid:
            if _s and _s != "未指定":
                fields[_k] = _s
        else:
            fields[_k] = _s or ("v1.0" if _k == "送审版本" else "未指定")
    # 「送审问题」列（用户 2026-10-03 裁定 (a) 项）：**只在调用方真给了原提问时才写** ——
    #   没给就保持空（不写「未指定」这类占位值，理由同上面的 B 修复）。
    if (a.question or "").strip():
        fields["送审问题"] = a.question.strip()
    if rid:
        _lark_run("base", "+record-batch-update", "--base-token", dest["base_token"],
                  "--table-id", dest["table_id"],
                  "--json", json.dumps({"update_records": {rid: fields}}, ensure_ascii=False))
        print("⑤ 表行：更新既有行 %s（未新增重复行）" % rid)
    else:
        d2 = _lark_run("base", "+record-batch-create", "--base-token", dest["base_token"],
                       "--table-id", dest["table_id"],
                       "--json", json.dumps({"create_records": [fields]}, ensure_ascii=False))
        rid = ((d2.get("data") or {}).get("record_id_list") or [None])[0]
        print("⑤ 表行：新建 %s" % rid)

    # ── ⑥ 读回校验 ────────────────────────────────────────────────────────
    got = _lark_run("base", "+record-get", "--base-token", dest["base_token"],
                    "--table-id", dest["table_id"], "--record-id", rid, allow_fail=True)
    txt = json.dumps(got, ensure_ascii=False)
    ok_row = a.content_id in txt and (r.get("decision") in txt)
    print("⑥ 读回：表行 %s ｜ 内容 ID 与结论%s" % (rid, "一致 ✅" if ok_row else "**对不上** ❌"))
    # ══════════════════════════════════════════════════════════════════════════
    # ★★ 2026-10-09：**未生成文档时，`docx=` 这一格必须是空的** ────────────────
    #
    #   病灶（实测三单全中：图片 / 视频 / 文案）：
    #   原先这里印的是 `docx=（未生成·问题数<3）` —— 一句**中文说明霸占了链接那一格**。
    #   而下游 `with_kb_evidence.py:1162` 是拿**正则**解析这一行的：
    #       re.search(r"docx=(\S+)\s*｜\s*record=(\S+)", out)
    #   `（未生成·问题数<3）` 里**没有空白** ⇒ `\S+` 照吃 ⇒ 解析出一个"链接"，
    #   于是 `publish.docx` 非空、`published=true`、`report_url_kind=feishu_docx`（**谎报**）。
    #   后果（每一环都可核）：
    #     · `kbSide.reportUrl` 变成真值 ⇒ 守衡侧 `agent.mjs:824`
    #       `if (total >= 3 && !kbSide?.reportUrl)` **被挡掉** ⇒ **合并报告根本不建**；
    #     · 卡片把它当本地路径渲染 ⇒ 群里出现
    #       `→ 查看完整问题清单与修改建议：（未生成·问题数<3）` ＋「**你点不开**」；
    #     · 而按 PRD §5.3.4 / Owner 2026-10-09 的口径（并集去重后 ≥3 必须给报告链接），
    #       这一格本该由守衡侧建出**真的** docx 链接。
    #   ⇒ 修法：**这一格只许放 URL 或空**。说明文字挪到下一行的 `未生成报告：…`（人看得见，
    #     但**不占链接格**）。空 ⇒ 正则应匹配不上 ⇒ `docx=None` ⇒ `report_url=None`
    #     ⇒ 守衡侧建报告那一跳的条件成立。**不许**在消费者侧加"什么算链接"的补丁：
    #     真值是这一格给的，补丁会把它固化（库规：同一个事实写两处，第二处必然过期）。
    _docx_out = url or ""
    print("完成：docx=%s ｜ record=%s" % (_docx_out, rid))
    if not _docx_out:
        print("未生成报告：%d 条 < PRD §5.3.4 门槛 %d ⇒ 库侧按 PRD 不建云文档；"
              "报告链接由守衡侧按「并集去重后的总数」口径补建。" % (n_issues, REPORT_LINK_MIN_ISSUES))
    return 0 if ok_row else 1


if __name__ == "__main__":
    sys.exit(main())
