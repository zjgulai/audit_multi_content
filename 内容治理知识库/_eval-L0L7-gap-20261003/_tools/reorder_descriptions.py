#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""按「可见区优先」重排 L1–L7 的 description（**只搬内容，不增删语义**）。

依据（宿主代码级 + 地面真值，见 `_DISCOVERY-500char.md` 与 L0 v1.3.0 实证）：
  · `dsh-tool-skill` 的目录行 = **折叠空白后前 500 字**（`slice(0,497)+'...'`）；
  · 规范里的 1024 只管校验，**模型看到的只有 500**；
  · L0 反证：同一条「管辖看动词不看宾语」放在可见区 ⇒ 安全 FP 1；移到不可见区 ⇒ 回到 2。

实测病灶（重排前）：7 件的**边界/判归/写档约束全部落在 500 之后**，
最坏的是 kb-media-extractor —— 它的 **7 条判归句一条都不可见**（隐藏 162 字），
kb-recall 更把「查询档只读：不改索引、不写库」压到了第 501 字之后。

做法：**换取顺序，不换字**。把「不适用/判归/写档边界/安全」提到触发词表之前，
把最长的触发词表压到末尾（它被截也不影响路由判断）。**不新增、不删除任何一条规则。**

输出：`{skill}-fix/SKILL.md`（**不写回源**），并打印重排前后可见性对照。
"""
import json
import os
import re
import shutil
import sys

SRC_ROOT = os.path.expanduser("~/.dsh/skills")
OUT_ROOT = ("/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/"
            "知识库/内容治理/kb/l7/skills")
EFFECTIVE_MAX = 500

# ── 新版 description（仅为**重排后**的同一批规则；逐条可回溯到旧版原文）────────
NEW = {
"kb-media-extractor": """Momcozy 内容治理知识库 **L1（单元层）的媒体抽取入口**：把**图片 / 附件 / 落地页链接**转成**可入库的文本**（OCR 正文），落进 L1 的 media 区与单元索引。 ⚠️**这些不归本 skill**：只对账 L0 → **kb-l0-feishu**；切成单元 → **kb-ingest-extractor**；条款蒸馏 → **kb-clause-extractor**；整链同步 → **kb-pipeline**；体检 → **kb-check**。 当用户说「图片抽取 / 媒体抽取 / 这批图 OCR 一下 / 附件入库 / 链接下钻 / OCR 缓存能不能复用」时使用。 **只想查状态、不打算抽取**（有多少张图还没落文本 / 媒体抽取进度）时**也用本 skill** —— 走 §2.1 **只读查询档**，不下载、不跑 OCR。 触发词：图片抽取、媒体抽取、OCR 落库、附件入库、链接下钻、L1 媒体、kb-media-extractor。 视频字幕 / 关键帧 OCR 尚未实现，先读 references/ 再如实回报。""",

"kb-check": """Momcozy 内容治理知识库的**统一闸门**：把全库各层的 check 一次跑完并汇总成一张体检表（登记表自检 / 层契约自检 / 链路收口 / 信封闸门 / 投影一致性 / 路由表对账）。 **本 skill 只报不改、默认全只读** —— 闸门没过、要**修** → 走 **kb-repair**；要跑 L0→L7 供给链本身 → 走 **kb-pipeline**；只对账 L0 → 走 **kb-l0-feishu**；判断内容能不能发 → 走 **kb-review**；评测 / 优化某个 skill 的质量 → 走 root-skills-eval / root-skills-opt（不属本家族）。 当用户说「知识库体检 / 检查一下知识库 / 知识库有没有问题 / 跑一遍所有闸门 / 闸门过没过 / 全库自检 / 各层 check 跑一下 / 登记表对不对 / workflow_check 跑一下」时使用。 触发词：知识库体检、全库自检、统一闸门、信封闸门、登记表自检、路由对账、envelope gate、kb-check。""",

"kb-ingest-extractor": """Momcozy 内容治理知识库 **L1→L2 的抽取与切分入口**：把一批素材 / 正文 / 源记录抽成知识单元（L1），再切成可召回的单元（L2）。**只拆不合**。 用户带着一批素材 / 正文 / 源记录说「抽取单元 / 素材转条目 / L1 抽取 / L2 切分 / 重切 / 补切 / 切分规则 / 单元对不上」时使用；问为什么没动（L2 预演 / 干跑 / 将追加多少行 / +0 行 / 幂等跳过 / sha 没变）时**也用本 skill**。 **只想查状态、不打算写库**（查一下 L1 水位 / L2 切了多少 / 单元行数）时**也用本 skill** —— 走 §2.1 **只读查询档**，不跑任何写档引擎。 不适用：只对账 L0 → **kb-l0-feishu**；条款蒸馏 → **kb-clause-extractor**；发号 → **kb-pipeline**；P0 判定 → **kb-p0-check**；召回 → **kb-recall**。 触发词：抽取单元、素材转条目、L1 / L2 切分、单元对账、kb-ingest-extractor。""",

"kb-clause-extractor": """Momcozy 内容治理知识库 **L3 的条款抽取与规则蒸馏入口**：输入是一批**外部标准 / 平台政策 / 内部规则的原文**（或已切好的单元），产出**可判定的规则候选**（命中表达 + 处理方式）与逐单元拒绝台账。 用户带着这类原文或单元说「抽条款 / 条款级单元 / 规则蒸馏 / L3 蒸馏 / 规则候选 / 这条能不能成规则 / 拒绝台账 / 蒸馏漏了没」时使用。 **只想查状态、不打算蒸馏**（查一下 L3 状态 / 拒了多少条）时**也用本 skill** —— 走 §3.1 **只读查询档**（`l3_status.py`），不跑任何写档引擎。 不适用（各自点名）：发号 / 定稿 → **kb-canonical-lookup**；一条是不是 P0 → **kb-p0-check**；召回单元 → **kb-recall**；素材切成单元 → **kb-ingest-extractor**；整链 → **kb-pipeline**。 触发词：抽条款、条款级单元、规则蒸馏、条款抽取、clause extractor、kb-clause-extractor。""",

"kb-canonical-lookup": """Momcozy 内容治理知识库 **L4（定稿与发布层）的只读查询**入口：查一条规则的**条款号**、查一个条款号对应哪条规则、查这条规则**定稿了没有**（canonical 状态 / 是否已发号 / 是否 stable）。 **本 skill 只读、不写库、不发号、不晋升**：发号 / 晋升 canonical / 重建 L4 是**写操作**，编排入口是 **kb-pipeline**，本 skill 不给自己开写入口。 **不承接**：判断内容能不能发 → **kb-review**；这个是不是 P0 → **kb-p0-check**；已给结论要追问依据 → **kb-content-review**；召回单元 → **kb-recall**；跑 L0 到 L7 / 同步 → **kb-pipeline**；体检 / 闸门 → **kb-check**。 触发词：条款号是多少、条款号对应哪条规则、article_no、规则定稿了吗、进 canonical 了吗、发号了吗、L4 查询、kb-canonical-lookup。""",

"kb-p0-check": """Momcozy 内容治理知识库 **L5（P0 判定层）的只读查询**入口：回答「**这个是 P0 吗**」「这段命中哪些 P0 模式」「为什么判最高优先级」。 **本 skill 只读**：只做确定性匹配与清单查询，不写库、不改 P0 模式表；重建 / 导出 P0 层是写操作，编排入口是 **kb-pipeline**，本 skill 不给自己开写入口。 **不承接**：查条款号 / 定稿了没有 → **kb-canonical-lookup**；召回单元 / 查资料 → **kb-recall**；判断内容能不能发 → **kb-review**；已给结论要追问依据 → **kb-content-review**；跑 L0 到 L7 → **kb-pipeline**；体检 → **kb-check**。 当用户问「这个是 P0 吗 / 算不算 P0 / 命中哪些 P0 模式 / P0 模式有哪些 / 为什么是 P0 / L5 里有没有这条 / 这条触碰红线了吗（红线口径 = P0）」时使用。 触发词：是不是 P0、命中 P0、P0 模式清单、kb-p0-check。""",

"kb-recall": """Momcozy 内容治理知识库 **L6（召回层）的只读检索**入口（已并入原 `kb-retriever`）：按 **BM25 + 向量**双索引召回知识单元，也支持面向本地知识库目录的分层索引导航式检索（遇 PDF / Excel 先读 references 再检索，避免整文件加载）。 **本 skill 只读：不改索引、不写库、不重建** —— 重建 BM25 + 向量索引是写操作，编排入口是 **kb-pipeline**，本 skill 不给自己开写入口。 **不承接**：查条款号 → **kb-canonical-lookup**；是不是 P0 → **kb-p0-check**；判断内容能不能发 → **kb-review**；追问依据 → **kb-content-review**；跑 L0 到 L7 → **kb-pipeline**；体检 → **kb-check**；skill 分工 → **kb-manage**。 触发词：召回、检索单元、语义召回、BM25 / 向量召回、召回 top-k、知识库里有哪些相关单元、知识库检索、分层索引导航、kb-recall。""",
}


def parse_desc(text):
    m = re.match(r"---\r?\n(.*?)\r?\n---\r?\n", text, re.S)
    fm = m.group(1)
    start = None
    lines = fm.split("\n")
    for i, ln in enumerate(lines):
        if re.match(r"^description\s*:", ln):
            start = i
            break
    end = start + 1
    while end < len(lines) and not re.match(r"^[A-Za-z_][A-Za-z0-9_-]*\s*:", lines[end]):
        end += 1
    return m, lines, start, end, " ".join("".join(lines[start:end]).split())


def folded_len(body):
    return len(" ".join(body.split()))


def main():
    only = sys.argv[1:] or sorted(NEW)
    report = []
    for skill in only:
        if skill not in NEW:
            print(f"!! 无新版：{skill}")
            continue
        src = os.path.join(SRC_ROOT, skill, "SKILL.md")
        out_dir = os.path.join(OUT_ROOT, f"{skill}-fix")
        os.makedirs(out_dir, exist_ok=True)
        # 先整树复制（首次），再改 SKILL.md —— 源一个字节都不动
        # 源目录里有 `chmod a-w` 的文件（源只读是纪律），copytree 会中途抛错并留下半个副本
        # ⇒ 改成「尽力复制 + 逐条留痕」：失败的文件记下来，不让它挡住 SKILL.md 的落地。
        skipped = []
        for sub in ("references", "scripts", "examples", "assets", "templates", "tests"):
            s = os.path.join(SRC_ROOT, skill, sub)
            if not os.path.isdir(s):
                continue
            for root, _dirs, files in os.walk(s):
                rel = os.path.relpath(root, SRC_ROOT)
                os.makedirs(os.path.join(OUT_ROOT, f"{skill}-fix", rel), exist_ok=True)
                for fn in files:
                    try:
                        shutil.copy2(os.path.join(root, fn),
                                     os.path.join(OUT_ROOT, f"{skill}-fix", rel, fn))
                    except Exception as e:                       # noqa: BLE001
                        skipped.append(f"{rel}/{fn}: {e}")
        text = open(src, encoding="utf-8").read()
        m, lines, start, end, old = parse_desc(text)
        new = " ".join(NEW[skill].split())
        indented = "\n".join(("  " + l) if l else l for l in new.split("\n"))
        newfm = "\n".join(lines[:start] + [f"description: >-\n{indented}"] + lines[end:])
        out_text = text[:m.start(1)] + newfm + text[m.end(1):]
        open(os.path.join(out_dir, "SKILL.md"), "w", encoding="utf-8").write(out_text)

        rec = {"skill": skill, "out": out_dir, "copied_skipped": skipped,
               "old_folded": len(old), "new_folded": len(new),
               "old_hidden": max(0, len(old) - EFFECTIVE_MAX),
               "new_hidden": max(0, len(new) - EFFECTIVE_MAX)}
        report.append(rec)
        flag = "✅ 全可见" if rec["new_hidden"] == 0 else f"❌ 仍隐藏 {rec['new_hidden']} 字"
        print(f"{skill:<24} 折叠 {rec['old_folded']:>4} → {rec['new_folded']:>4}   "
              f"隐藏 {rec['old_hidden']:>4} → {rec['new_hidden']:>4}   {flag}")
    json.dump(report, open("/tmp/l1l7/reorder-report.json", "w"), ensure_ascii=False, indent=1)
    print("\n逐件报告 → /tmp/l1l7/reorder-report.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
