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
        if item.get("risk_category"):
            key = item["risk_category"]
        elif item.get("risk_category_basis"):
            key = "未标注维度"
        else:
            key = item.get("risk_type") or item.get("category") or "未分类"
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
                f"{index}. **{item.get('risk_id', '')}**【{item.get('risk_type') or item.get('category') or '未分类'}】（{item.get('priority_tier', '')} / {item.get('severity', '')}）",
                f"   - 位置：{item.get('location', '未定位')}",
                f"   - 原文/观察：{item.get('original_text') or item.get('observation') or '未提供'}",
                f"   - 原因：{item.get('reason', '')}",
                f"   - 建议：{item.get('suggestion', '')}",
                f"   - 证据：{item.get('evidence_url') or item.get('evidence_id') or '缺失'}",
                "",
            ])
    lines.extend([
        "## 决策轨迹",
        "",
        f"- 下一步：{result.get('next_action', '')}",
        f"- 责任角色：{', '.join(result.get('next_owners') or [])}",
        f"- SLA：{json.dumps(result.get('sla', {}), ensure_ascii=False)}",
        f"- 版本门禁：{json.dumps(result.get('version_gate', {}), ensure_ascii=False)}",
        f"- 覆盖状态：{json.dumps(result.get('coverage', {}), ensure_ascii=False)}",
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
