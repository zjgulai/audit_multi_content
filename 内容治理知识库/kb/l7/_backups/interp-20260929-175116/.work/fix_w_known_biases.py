#!/usr/bin/env python3
"""W 批收尾：登记已知偏差、口径错配与写通道纪律。

本轮（W019/W023/W035/W036）已修并验证；剩下三类**不是缺陷**或**不该由 agent 修**的
项必须显式登记，否则它们会以「没修的告警」形式长期挂着，让人分不清
「已知并接受」与「漏了」。
"""
import json
import os
import shutil
import subprocess
import sys

KB = "kb"
L8 = f"{KB}/l8/registry/l8.json"
ARCHIVE = f"{KB}/l8/_archive/fix-20260929-094703"
RUN = "20260929-1200"


def main():
    subprocess.run(["cp", L8, f"{ARCHIVE}/l8.json.before-Wbatch"], check=True)
    r = json.load(open(L8, encoding="utf-8"))
    have = {t.get("id") for t in r["technical_debt"]}

    add = []

    # ── 写通道：本轮踩到并用一轮 509 条 E001 换来 ──────────────
    if "TD8" not in have:
        add.append({
            "id": "TD8",
            "item": "写通道纪律：Python 写 kb/view 会落成信封，且 Python 自己看不见",
            "impact": (
                "本轮实测：`shutil.copy2` 把同一份 4,532 字节的 md 落盘后，"
                "**node 读到 8,628 字节**（= 4,532 + 4,096 前缀，即「4096 字节前缀 + 原文」的信封），"
                "加载器据此报 **E001 × 509「缺 frontmatter」**，并因 loadAll 拿不到条目把"
                "条目基线刷成了 0 条（removed 509）。而 **Python 的 stat / sha256 / head 报的仍是"
                "4,532 字节、sha256 与源文件一致** —— 所以当时那个「明文自检」"
                "（用 Python 读首 3 字节）**结构上不可能发现这个缺陷**，它给了假绿灯。"
                "同一份文件走 shell `cp` → node 读到 4,532 字节、首 3 字节 `---`，明文。"
            ),
            "priority": "P0",
            "status": "已定纪律（纪律比修复更重要：这类缺陷只能靠消费方运行时发现）",
            "fix": (
                "(1) 落进 kb/view 的文件只用 shell `cp` 或 node 写，**不要用 Python 写**"
                "（含 shutil.copy2 / open(...,'w') / sed / perl）；追加账本行也用 shell。"
                "(2) 校验必须用**消费方运行时**：`kb/.work/which_enveloped.mjs`（node 看首字节）与"
                "`kb/l8/scan_envelope.mjs`（全库扫描），不要用 Python 自证。"
                "(3) 留底也要用 `cp` —— 信封版的留底在回滚时会把信封带回来。"
                "证据与复现：kb/l8/runs/20260929-1200.report.md（W 批一节）。"
            ),
            "owner": "l8 批次",
        })

    # ── 已知偏差 / 不该由 agent 修的项 ────────────────────────
    r.setdefault("known_biases", {})
    r["known_biases"] = {
        "E026": {
            "count_at_run": 454,
            "level": "error",
            "verdict": "**不是缺陷，是口径错配** —— 散文质量闸门套在结构化规则库上。",
            "why_not_fixed_by_agent": (
                "闸门口径（kb.js QUALITY / quality()）：正文 ≥200 字符且总分 ≥60，"
                "总分 = 长度(≤20, n/500 封顶) + 密度(30) + 去重(20) + 语言(30)。"
                "这四维是为**手写散文条目**设计的。本库 509 条的正文是**规则行的忠实渲染**"
                "（规则原文 / 命中表达 / 判为违规的依据 / 处理方式 / 适用范围 / 证据单元明细），"
                "样例 1,305 字符 —— 不是写得薄，是规则本身就短。"
                "实测 454 条全部落在「分数 <60」分支（短正文分支 0 条），"
                "现有总分 52.5 / 55.8 / 59.9（min/中位/max）。"
            ),
            "rejected_fix": (
                "**不采用「往正文灌水凑长度」**：按 lengthScore=min(20, n/500) 反推，"
                "分别需要新增约 801 / 3,151 / 7,000 字符即可过线 —— 也就是给每条规则"
                "补 0.8k–7k 字的**非知识内容**。那正是本库明令禁止的「为指标造数据」"
                "（同类判例：related 为压孤岛率而造的合成边，见 W025 一条）。"
                "灌水还会同时改变 density（去重比被拉低）与 language（重复句 `(.)\\1{5,}` 直接扣分），"
                "属于用一个假绿换另一个假绿。"
            ),
            "two_honest_paths": [
                "① 给 QUALITY 闸门加**按库分档**的口径（结构化规则库 vs 散文库），由插件侧改、需留痕；",
                "② 若权威库里这些规则确实还有未渲染的正文（rule_text/reason 之外的长文本），"
                "则把它渲染出来 —— 那是**暴露已有内容**，不是灌水。本轮核对：正文已渲染"
                "规则原文/依据/处理方式/证据明细，未见明显可渲染的长字段，故 ② 预计收益有限。",
            ],
            "note": "health 分不把 errors 计入维度，但熔断看 errors；本库 errors 全为 E026 时 health 仍 98.4，"
                    "而 kb_check 的 ok=false 由 errors.length>0 决定 —— 这一条决定了「本库算不算通过」。",
        },
        "W020": {
            "count_at_run": 2218,
            "level": "warning",
            "verdict": "**机器只报疑似，判归人** —— 需人工决定合并或补写分工。",
            "why_not_fixed_by_agent": (
                "加载器自己的措辞：「要么合并（新建 + supersedes 留痕，不许原地改写），"
                "要么把两者的分工写进 summary。**机器只报疑似，判归人**」。"
                "合并会改知识口径并触发 AP14（改主意 = 新建 + supersedes，不许原地改），"
                "那是业务判断，不是工程修复。样例：元字段 Jaccard 0.61、正文 Jaccard 0.59 —— "
                "相似度只说明「同源同族」，不说明「该合并」。"
            ),
            "action_needed": "业务方按疑似清单逐条判定（清单可由 kb_check 导出）。",
        },
        "W021": {
            "count_at_run": 10,
            "level": "warning",
            "verdict": "**疑似数值矛盾，且经查为解析伪影** —— 键名是截断串。",
            "evidence": (
                "样例消息：「同一个键「recvunn」+ 同一个单位「(无)」 取值不相交 —— 本条 6，对端 4」。"
                "键名 `recvunn` 是记录 id 前缀被截断的产物，不是知识里的键；"
                "另一类「同一个键「命中表达」+ 单位「条」，本条 1、对端 3」比较的是"
                "**各条目自己的命中表达条数**（每条规则天然不同），不是对同一量的两个断言。"
            ),
            "why_not_fixed_by_agent": (
                "加载器已声明「**疑似项不是判决**：可能是不同对象、不同口径、或其一已过期。"
                "属数值冲突的走 governance.yaml，**不许自动裁决**」。"
                "本轮判定为伪影，但按该口径也不应自动改数据 —— 记此判定供人复核。"
            ),
            "action_needed": "人工确认 10 条均为伪影后，可在 governance.yaml 记「已复核为伪影」。",
        },
        "W025": {
            "count_at_run": 1,
            "affected_entries": 509,
            "level": "warning",
            "verdict": "**待决策** —— 修它会把一个假绿维度换成真的红。",
            "background": (
                "生成器「补丁 E」的注释自己写明：related 是「给每条规则挂几个 related 邻居"
                "（**用来把孤岛率从 1.00 打下来**）」。两个依据："
                "①同 rule_code —— 真的规则族关系（37 条规则、22 个码）；"
                "②同主来源表 —— 文档原话是「每条指向稳定序上紧随其后的 N 条，**使全组都有入边**」，"
                "即**为过门槛而制造的合成边**，不是关系。"
            ),
            "consequence_if_migrated": (
                "加载器只认「related 为空/不存在」才消警（把内容搬进 typed keys 不算）。"
                "故修它必须删/清空 related。而孤岛率 = 没被任何条目引用的占比，"
                "清掉合成边后只剩 37 条有真边 → 孤岛率约 0.93，**超过 ≤0.2 阈值，该维度转红**，"
                "健康分随之下行（当前 98.4，熔断线 60）。"
            ),
            "options": {
                "A": "只让生成器**不再新写** related（合规字面要求），存量不动 → W025 仍报 1 条，孤岛率仍是假绿。",
                "B": "删掉合成边、只保留同 rule_code 的真边并迁到 complements → W025 归零，孤岛率转真红（约 0.93），健康分下行。",
                "C": "把合成边也迁成 complements → W025 归零且孤岛率保持绿，但**类型是编造的**，违反本库「不许为指标造数据」，已排除。",
            },
            "recommendation": "B（与 F10「健康分从 100 掉到 98.4 是假绿被拆掉」同一处置逻辑），但需人确认，因为它改的是一个已公开的健康数字。",
            "note": "真孤岛率约 0.93 本身是有价值的业务结论：472/509 条规则与其他条目**没有任何真实引用关系**。"
                    "要真正降下来，需要来源表提供真实的关联列（当前没有）→ 属业务动作。",
        },
    }

    r["technical_debt"].extend(add)
    with open(L8, "w", encoding="utf-8") as fh:
        json.dump(r, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    print(f"l8.json 已更新：technical_debt {len(r['technical_debt'])} 项（新增 {len(add)}），"
          f"known_biases {len(r['known_biases'])} 类")


if __name__ == "__main__":
    sys.exit(main())
