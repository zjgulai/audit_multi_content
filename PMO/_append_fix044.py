#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 FIX-044 追加进 PMO/已修问题.jsonl（id 先查过没被占）。"""
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
JSONL = ROOT / "PMO/已修问题.jsonl"

rec = {
    "id": "FIX-044",
    "title": "P0 判据不许取决于「模型肯不肯调工具」—— 同一句话问两遍，两遍形状不同；"
             "FIX-043 修的「链跑了但结论行寄在措辞上」之外，还有「链压根没跑」这一种",
    "found_at": "2026-10-16",
    "class": "接线缺失（判据的上游是模型的自选项）＋ 自证副作用（建了一份真云文档）",
    "symptom": (
        "Owner 贴了第二张卡之后原话：「**没有修复呀**」。真单 "
        "`om_x100b6214a146d0a0cd13079897c6483`（群 oc_49a7…，**同一句话第二次问**），"
        "台账 `PMO/logs/ws_outbound.jsonl` 第 1404 行、**163 字**卡面逐字："
        "`【m5 pro 是最好的吸奶器 —— BLOCK（同上轮，未重跑）】` ␤ "
        "`BLOCK：命中「最好」，E-2.124（P0 一票否决项）` ␤ "
        "`上一轮已跑链得此结论，同一句话判定不变；重跑会往飞书再加一行，故未重跑。…` ␤ "
        "`（已收起 1 条证据：证据 · 1 条）` —— 同样**没有 PRD §5.3.3 的逐条块**。"
        "守护进程日志逐字（ws_daemon.log 第 20661–20675 行）：闸门「不起链 —— 在问「审查这件事本身"
        "怎么运作」（过审）」，而**整段里没有 `🔧 工具: kb_review_chain`** ⇒ 链一次都没跑。"
    ),
    "root_cause": (
        "FIX-043 修的是「**链跑了，但结论行与逐条块寄在模型的措辞上**」；"
        "而这一单是第二种走法：**链压根没跑**。原因是 **P0 判据（确定性匹配、只读、毫秒级）"
        "此前唯一的上游是「模型愿不愿意调 `kb_review_chain`」** —— 模型这一轮不肯调，"
        "理由还很正当（会话记忆逐字：「重跑一遍要走完整个 P0 快路流程，**并且往飞书再写一行**……"
        "**我不想因为一句话又问一遍，再多留一行。**」）。于是 `p0Memo` 没有货、"
        "`verdict53Final` 两个来源全空 ⇒ 信封层 `reviewShape=false` ⇒ 卡仍是模型自拟的。"
        "★ 两遍的对照：同一个群、同一句话、**闸门判词逐字相同** —— 17:19 那遍模型自己调了链"
        "（卡 180 字），19:4x 那遍没调（卡 163 字）。**同一个输入、两种产物，差别只在模型的临时决定。**"
        "PRD §6.3 第一层说的是「命中即停止后续审查，直接输出 BLOCK」—— 它是**判据**，不是自选项。"
    ),
    "fix_files": [
        "tools/agent/tools.mjs",
        "tools/agent/agent.mjs",
        "tools/test_agent.mjs",
        "PMO/守衡-P0不许取决于模型肯不肯调工具-20261016.md",
    ],
    "fix_what": (
        "① `tools.mjs`：把 `kb_review_chain` 注册体里 P0 那一整块（报告复用/生成 → 回执重渲染 → "
        "两端对齐核对 → 组装返回体）抽成 **`export async function runP0Preflight()`** ＋ 内层 "
        "`p0HitPayload()`（一个产出者，两处不许各写一份）。工具那一支改成一个转发，"
        "`allowPublish: true` ⇒ 行为逐字不变。"
        "② 同一个函数的**默认参数是纯只读**：`reportOut=''`、`allowPublish=false` ⇒ "
        "不落报告文件、不建云文档、一行都不往飞书写。"
        "③ `agent.mjs`：`if (!gate?.yes) p0Preflight = await runP0Preflight({ text, question })` "
        "—— 排在闸门之后、模型之前；异常一律按未命中算（一个字都不许因此拦住回话）。"
        "④ `verdict53Final` 改成先判载荷再选支：`g.verdict53` → `p0Payload`（工具来的 / "
        "内核前置来的）→ `toolTrace` 那一支。"
        "⑤ `reportLink: g.dual?.reportUrl ?? (p0Preflight?.report || null)`（拿不到就是 null，不编）。"
        "⑥ 判据 `Y8 / Y9 / Y10`（第 22c 组）。"
    ),
    "enforced_by": [
        "runP0Preflight",
        "p0HitPayload",
        "Y8",
        "Y9",
        "Y10",
    ],
    "self_check": "node tools/test_agent.mjs",
    "verify_cmd": "node tools/test_agent.mjs",
    "ingest_ref": {"not_needed": (
        "本条与 FIX-043 是同一条方法论的两跳（「判据的上游不许是模型的自选项」/「判据被验过 ≠ "
        "它被接上了」），**FIX-043 的那条 `ref-shouheng-*` 条目已经覆盖了方法本身**；"
        "本条只多一组现场读数与一个只读前置的实现细节，入库会与前一条近乎重复。"
        "★ 这条表态是 Owner 说「你的优化不要影响现有的工作流」之后写的："
        "入库闸门当时回 E040（要 `human=true`），**我没有绕闸门**，改为如实表态不入。"
        "★ 若 Owner 后面要求入库，改成给条目 id 即可。"
    )},
    "readings": [
        "`node tools/test_agent.mjs` **254 / 3**（改动前 **251 / 3**；那 3 条红是「真跑一次本机转写」"
        "那一组，本机语音识别没授权，**改动前后逐字相同**）",
        "`node tools/verify_cards.mjs` **347 / 0**｜`node tools/agent/prd53_format.test.mjs` **19 / 0**",
        "**行为级复现**（真跑那条只读前置）：命中 1 条 V02 ｜ 29.404 ms ｜ "
        "`report_path` 空、`report === ''`（只读）→ 派生 `【审查结论：BLOCK】共发现 1 处必须修改。`"
        "（合规 true）→ 卡类型 evidence、第一组「逐条问题」、卡面 ✅原因 ✅依据 ✅建议 "
        "✅「请修改后重新提交。」（夹具 = 模型**没调链也没抄结论行**的那一轮）",
        "**反向对照**：`你的能力图谱有哪些？` / `谢谢，我明白了` / `PRD §5.3 里 PASS 长什么样？` / "
        "空串 ⇒ 前置一律回 null（不误报）；`Y10` 另两条：调用点恰好 1 个、那一跳不许带 "
        "`allowPublish`",
        "⚠️ **自证副作用（§2.4.4 那个病，我自己踩的）**：第一版验证时给 `reportOut` 传了临时路径，"
        "于是**真建了一份云文档** `FGhGd87rkoaiM6xXRP3cJoOVnEf`（与真单那份内容相同）。它促成了"
        "「默认只读」这一版设计；那份文档撤不回，且没有被任何表行指着"
        "（`previousReportLink('AUTO-ab2b0b733528')` 实测回 **null** —— 那一单从未落过表行）",
        "★ **尚未生效**：`tools.mjs` / `agent.mjs` 都是 `ws_daemon.mjs` import 得到的模块，"
        "**要重启守衡**（AGENTS.md §2.7 闸门，须 Owner 同意）；本条写作时未重启",
    ],
    "docs": ["PMO/守衡-P0不许取决于模型肯不肯调工具-20261016.md"],
    "note": (
        "★ 与 FIX-043 的分工：043 修「链跑了、结论行寄在措辞上」（`p0Memo` 那一格）；"
        "044 修「链压根没跑」（内核自己跑一遍）。**两次都要重启才都生效。**"
        "★ 最该被后人读到的一句：**一个确定性判据，它的上游不许是模型的自选项** —— "
        "同一句话问两遍会长出两种产物，而两次自证都是绿的。"
        "★ 只读那条边界是 Owner「不要影响现有的工作流」直接逼出来的："
        "「闸门判不是送审」那条路以前从不建云文档，前置若照抄工具那一支就会开始建。"
        "代价（这条路上报告链接可能为空）与 PRD §5.3.3 不冲突：1–2 条本来就不要求报告链接。"
    ),
}


def main() -> int:
    ids = [json.loads(l)["id"] for l in JSONL.read_text(encoding="utf-8").splitlines() if l.strip()]
    if rec["id"] in ids:
        print(f"{rec['id']} 已被占 —— 不追加")
        return 1
    with JSONL.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"appended {rec['id']}；现在共 {len(ids) + 1} 条")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
