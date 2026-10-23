#!/usr/bin/env python3
"""Render review results into portable Markdown and JSON report files."""

from __future__ import annotations

import json
import os
import subprocess
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict


def _write_text_safely(path: Path, text: str) -> None:
    """写 `.md`/`.sh` 必须经 `/bin/cp` 落地 —— 否则**宿主**读到的是「真内容 + 4096 字节」。

    ★ 2026-10-06 实测（机理与旧说法不同，以实测为准）：
      python 直写 `.md` / `.sh` ⇒ **DSH 宿主**（`ELECTRON_RUN_AS_NODE=1 "$DSH"`，也就是
      `read` 工具与 DSH 里跑的脚本用的那把尺子）看到的比真值多 **4096** 字节，读成 binary。
      **python 自己、系统 node、`cat` 都读得到真值** ⇒ 用它们量会得出"本来就没事"的**假绿**。
      逐扩展名对照：`.md`/`.sh` 中招；`.py`/`.mjs`/`.yaml`/`.json`/`.log`/`.txt` 干净。
      完整实测表见 `kb/.work/_safe_write.py` 的文件头。

    ★ 为什么这里又写了一份而不再 import 那个：`kb/.work/` 是工作区临时区，
      让 `kb/l7/review-engine/core/` 的核心模块依赖它，是把架构倒过来。**两份实现是已知的坏味道**
      （见 registry 的 `still_open`），等有了合适的共用位再合并。
    """
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    if p.suffix.lower() not in (".md", ".sh"):
        p.write_text(text, encoding="utf-8")
        return
    tmp = p.parent / (".%s.swtmp" % p.name)      # 非中招扩展名 ⇒ 直写它不会被加信封
    try:
        tmp.write_text(text, encoding="utf-8")
        subprocess.run(["/bin/cp", str(tmp), str(p)], check=True)
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass
    back = p.read_text(encoding="utf-8")
    if back != text:                              # 写完回读复核：**不静默**
        raise RuntimeError("报告回读不符：写入 %d 字符 / 读回 %d 字符（%s）"
                           % (len(text), len(back), p))


#: 优先级排序（高→低）；未知值排最后，**不猜**
_P_ORDER = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}


def taxonomy_groups(risk_items) -> tuple[dict, int]:
    """按 **11 类**（`taxonomy_category`）分组 —— 返回 `({类别: [条目]}, 未挂类的条数)`。

    ★ 这是什么、不是什么（写死在这里，免得后人当成源字段）：
      · 是 **2026-10-16 会话里提出、Owner 采用**的一套 11 类分类体系（真源
        `kb/l3/registry/rule-taxonomy.json`）；**不是**源表字段，也**不是** PRD 原文类目。
      · 它**不顶替** `risk_category`（PRD §5.3 四维）与 `risk_type`（库内 8 类规则词表）——
        三格并存，各说各的一件事。
    ★ 未挂类的条目（反例/案例层 `sc-…`、覆盖缺口行）**不硬塞进任何一类**，
      只计数并由调用方在报告里写明 —— 蒙一个类比留空更坏。
    """
    groups: dict = defaultdict(list)
    unnamed = 0
    for it in risk_items or []:
        cat = str(it.get("taxonomy_category") or "").strip()
        if cat:
            groups[cat].append(it)
        else:
            unnamed += 1
    return groups, unnamed


def taxonomy_section_lines(risk_items, heading: str = "## 按所属类别汇总（12 类，附加视图）") -> list:
    """渲染「**按所属类别（12 类）**分组」那一段（表格：类别 / 条数 / 最高优先级 / 条款号）。

    没有一条挂上 11 类时**返回空列表**（整段不出现，不输出空表当结论）。
    """
    groups, unnamed = taxonomy_groups(risk_items)
    if not groups:
        return []
    rows = []
    for cat, items in groups.items():
        # findings（review.py 的旧报告路径）用 `p_level`，risk_items 用 `priority_tier` —— 两者都认
        tiers = [str(i.get("priority_tier") or i.get("p_level") or "").upper() for i in items]
        tiers = [t for t in tiers if t]
        top = min(tiers, key=lambda t: _P_ORDER.get(t, 9)) if tiers else "—"
        # `article_no` 可能在顶层（findings）或 `evidence.article_no`（risk_items）—— 两处都认
        arts = [str(i.get("article_no") or ((i.get("evidence") or {}).get("article_no")) or "").strip()
                for i in items]
        arts = [a for a in arts if a]
        rows.append((cat, len(items), top, "、".join(arts) if arts else "—"))
    rows.sort(key=lambda r: (_P_ORDER.get(r[2], 9), -r[1], r[0]))
    lines = [heading, "",
             "| 所属类别（11 类） | 条数 | 最高优先级 | 条款号 |",
             "|---|---:|---|---|"]
    for cat, n, top, arts in rows:
        lines.append(f"| {cat} | {n} | {top} | {arts} |")
    lines.append("")
    total = sum(r[1] for r in rows)
    note = f"（本单 {total} 条挂上 11 类"
    note += f"；另有 {unnamed} 条无 11 类 —— 反例/案例层或覆盖缺口，**不编**）" if unnamed else "）"
    lines.append(note)
    lines.append("")
    return lines


def render_markdown(result: Dict[str, Any]) -> str:
    groups = defaultdict(list)
    for item in result.get("risk_items", []):
        # ── ★★ 2026-10-12（改动单《risk_type对齐PRD5.4》方案 B，Owner 批准）──────────────
        #   PRD §8.3 逐字要的是「**按维度分组展示**」—— 「维度」= 四维 = `risk_category`
        #   （PRD §5.3：合规 / 消费者安全 / 产品描述 / 措辞表达）。
        #   改前按 `risk_type`（**库内细分类别**）分组 ⇒ 那是「细分」不是「维度」。
        #
        #   ★ 为什么不干脆把 `risk_type` 改成「维度-子类」（那样只改一行）：
        #     `review_engine.py::route_owners()` **拿 `risk_type` 做关键词匹配定责任人**，
        #     改成四维度会**静默降级路由**（实测 6 条里 3 条变：`功效宣称-…` 丢了「功效」⇒
        #     医学顾问不再被转；另两条丢了「渠道负责人」）。详见那份改动单 §1.1。
        #
        #   三档回落，**每一档都可区分**：
        #     ① 有 `risk_category` ⇒ 用它（维度）
        #     ② 无、但有 `risk_category_basis` ⇒ 落 **「未标注维度」**
        #        （走过标注但类别未映射/待裁：原则性错误 / 文化禁忌 / 未分类 / unknown）
        #        —— **显式成桶，不许悄悄并进别的桶，也不许丢掉**
        #     ③ 连 basis 都没有（老形状：`rule_engine` 的「产品事实审批」、
        #        `with_kb_evidence` 的「覆盖缺口」）⇒ **逐字退回** `risk_type`
        #        （与守衡 `dual_track` 那条「引擎给了就照搬、没给才回落」同一条纪律）
        # ★★ 2026-10-19（Owner：「**报告要同步 卡上 12 类呀，整个知识库都要同步**」）——
        #   分组轴从 **A2 四维**（`risk_category`）换成 **A3 12 类**（`taxonomy_category`）。
        #   为什么：卡面逐条首行、卡面分类汇总、守衡那份报告**早就是 A3**，
        #   只有库侧这份报告还在按四维分组 ⇒ 一份报告两种分类，读者只能怀疑哪个对。
        #   盖不到 A3 的条目落 **`未归类`**（12 类的兜底类，**不编一个类**）。
        key = str(item.get("taxonomy_category") or "").strip() or "未归类"
        groups[key].append(item)
    lines = [
        f"# 内容审核报告 {result.get('review_id', '')}",
        "",
        f"- 内容 ID：{result.get('content_id', '')}",
        f"- 内容版本：{result.get('content_version', '')}",
        f"- 结论：{result.get('decision', '')}",
        f"- 置信度（未校准启发式）：{result.get('confidence', '')}",
        f"- Agent 版本：{result.get('agent_version', '')}",
        f"- 规则版本：{result.get('rule_version', '')}",
        f"- 知识库版本：{result.get('knowledge_version', '')}",
        "",
        "## 问题清单",
        "",
    ]
    if not groups:
        lines.append("未发现风险项。")
    for category, items in groups.items():
        lines.append(f"### {category}")
        lines.append("")
        for index, item in enumerate(items, start=1):
            lines.extend([
                # ★★ 2026-10-12（同一条改动单）：分组键换成「维度」后，**每条必须补回「细分」**
                #   否则细分信息就真丢了 —— 改前它是分组标题，改后那个位置变成了维度。
                #   PRD §5.3 的展示形态本就是 `【维度-细分】`：分组给维度、这条给细分，两格各就各位。
                f"{index}. **{item.get('risk_id', '')}**【{item.get('risk_type') or item.get('category') or '未分类'}】（{item.get('priority_tier', '')} / {item.get('severity', '')}）"
                # ★ 2026-10-19：分组标题已经是**所属类别**（12 类）⇒ 这一格只补**所属子类**，
                #   不再重复印一遍类别（同一件事说两遍）。子类没有就不印这一格。
                + (f"｜所属子类：{item.get('taxonomy_subcategory')}"
                   if (item.get("taxonomy_subcategory") and item.get("taxonomy_category")) else ""),
                f"   - 位置：{item.get('location', '未定位')}",
                f"   - 原文/观察：{item.get('original_text') or item.get('observation') or '未提供'}",
                *([f"   - 历史规则意见（非本素材原文；{item.get('history_attribution') or '归属见溯源'}）：{item.get('history_rule_text')}\n"
                   f"     源记录：{(item.get('evidence') or {}).get('l0_entry_url') or item.get('evidence_url') or '未提供'}"]
                  if item.get("history_rule_text") else []),
                *([f"   - 历史审核完整分析（来源记录 {item.get('history_record_id') or '未知'}；{item.get('history_scope') or '历史意见'}，非本素材原文）：\n{item.get('history_analysis')}\n"
                   f"     源记录：{(item.get('evidence') or {}).get('l0_entry_url') or item.get('evidence_url') or '未提供'}"]
                  if item.get("history_analysis") else []),
                *([f"   - 历史源建议（来源记录 {item.get('history_record_id') or '未知'}；非本素材原文）：{item.get('history_advice')}\n"
                   f"     源记录：{(item.get('evidence') or {}).get('l0_entry_url') or item.get('evidence_url') or '未提供'}"]
                  if item.get("history_advice") else []),
                f"   - 原因：{item.get('reason', '')}",
                f"   - 建议：{item.get('suggestion', '')}",
                f"   - 证据：{item.get('evidence_url') or item.get('evidence_id') or '缺失'}",
                "",
            ])
    # ★ 2026-10-19：分组的轴已是 12 类 ⇒ 这一段（按 12 类汇总）与上面的分组**同一套口径**，不是附加视图了
    lines.extend(taxonomy_section_lines(result.get("risk_items") or []))
    lines.extend([
        "## 决策轨迹",
        "",
        f"- 下一步：{result.get('next_action', '')}",
        f"- 责任角色：{', '.join(result.get('next_owners') or [])}",
        f"- SLA：{json.dumps(result.get('sla', {}), ensure_ascii=False)}",
        f"- 版本门禁：{json.dumps(result.get('version_gate', {}), ensure_ascii=False)}",
        f"- 覆盖状态：{json.dumps(result.get('coverage', {}), ensure_ascii=False)}",
    ])
    _image_audit = ((result.get("decision_trace") or {}).get("image_identity")
                    if isinstance(result.get("decision_trace"), dict) else None)
    if isinstance(_image_audit, dict):
        lines.extend([
            "- 图片身份层：%s；检测 %s 条，新增 %s 条，升级 %s 条" % (
                "已检查" if _image_audit.get("checked") else "未测",
                _image_audit.get("detected", 0), _image_audit.get("added", 0),
                _image_audit.get("upgraded", 0)),
            "- 图片规则命中：%s" % json.dumps(_image_audit.get("hits") or [], ensure_ascii=False),
        ])
    return "\n".join(lines) + "\n"


def write_report(result: Dict[str, Any], output_dir: str | Path) -> Dict[str, str]:
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    review_id = result.get("review_id", "review")
    json_path = directory / f"{review_id}.json"
    markdown_path = directory / f"{review_id}.md"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    # ★ `.md` 走安全写盘（`.json` 不受信封影响，实测干净，直写即可）
    _write_text_safely(markdown_path, render_markdown(result))
    return {"json_path": str(json_path), "markdown_path": str(markdown_path)}
