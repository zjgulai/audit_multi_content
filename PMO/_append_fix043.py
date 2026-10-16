#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 FIX-043 追加进 PMO/已修问题.jsonl（id 先查过没被占）。"""
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
JSONL = ROOT / "PMO/已修问题.jsonl"

rec = {
    "id": "FIX-043",
    "title": "P0 快路单的卡上没有 PRD §5.3 逐条块 —— 判据早就写好了（W1 一直在喂它），全仓没有一个调用点给它传过 p0Fastpath",
    "found_at": "2026-10-16",
    "class": "产物形态（启用条件）＋ 接线缺失（判据被验过 ≠ 它被接上了）",
    "symptom": (
        "Owner 原话（2026-10-16 17:23 群里）：「我在群里@守衡的，守衡输出的格式跟 prd 不符，"
        "**这个问题修复多次了，怎么还出现了**」。真单 `om_x100b622a8e762cbcce3b9bfa8402ccb`"
        "（群 oc_49a7…，问「m5 pro是最好的吸奶器，这句话能过审吗？」），台账 "
        "`PMO/logs/ws_outbound.jsonl` 第 1400 行、**180 字**卡面逐字：`【证据】` ␤ "
        "`BLOCK —— 「最好」命中 P0 一票否决项 E-2.124；红线拦截，非专项审查结论` ␤ "
        "`（已收起 1 条证据：判定 · 1）` ␤ `（已收起 1 条证据：四段溯源只两段可用 · 2）` ␤ …"
        "（四组折叠摘要）—— **PRD §5.3.3 的逐条块（原因/依据/建议/动作行）一个字都没有**。"
        "而链其实给了完整的那一份：现场实跑 `kb/kbpy l5/p0_fastpath.py --file …--json`，"
        "`rendered` 与真单会话第 147 条逐字相同。"
    ),
    "root_cause": (
        "两个各自都对的部件，接缝断了。① 那一单**闸门判「不是送审」**（守护进程日志逐字："
        "`🧭 送审闸门：不起链 —— 在问「审查这件事本身怎么运作」（过审）`）⇒ `runSubmissionGate` "
        "直接 `return { verdict53: null }`；链是**模型自己**调的（`🔧 工具: kb_review_chain(9465ms)`）。"
        "② 内核兜底那一支 `deriveVerdictLine({ replyText, reviewedByTool: true })` **只喂 `replyText`** "
        "⇒ 结论行取决于「**模型有没有把链那一行抄进回复**」，而这一单模型没抄（它写 "
        "`**结论：BLOCK —— 共 1 处必须修改。**`）⇒ `verdict53Final = null` ⇒ 信封层 "
        "`reviewShape = !!(verdict53 && verdict53.line && verdict53.block)` 为 false ⇒ "
        "**模型自拟的卡原样发出去**。★ `toolTrace` 那一跳**结构上补不上**：它的元素是 "
        "`{tool, ok, ms, args, error}`，**不记返回体**。★ 而 `prd53.deriveVerdictLine` 第 ② 支"
        "**早就**会按 `p0Fastpath.matched_patterns` 派生 §5.3.3 那一行，`test_agent.mjs` 的 W1 "
        "**一直在喂它**、自证一直绿 —— 但全仓**没有一个调用点给它传过 `p0Fastpath`**"
        "（与 FIX-021 同一个形状，换了个接缝）。★ 顺带撞出第二处：`prd53.verdictLineFor` 的 PASS 支"
        "返回 `conform: conforms(line).ok`（**布尔**，其余各支都是 `{ok,state,why}`）⇒ 发送层 "
        "`⚠️ 措辞不合 §5.3：${c.why}` 打出 `undefined`（实测 ws_daemon.log："
        "`PASS（来自 dual-track-merged）… ⚠️ 措辞不合 §5.3：undefined`）—— 回退本来最该看得见，"
        "配一个空原因等于没写。"
    ),
    "fix_files": [
        "tools/agent/tools.mjs",
        "tools/agent/agent.mjs",
        "tools/agent/prd53.mjs",
        "tools/test_agent.mjs",
        "PMO/守衡-P0单上不了PRD逐条块-20261016.md",
    ],
    "fix_what": (
        "① `tools.mjs`：新增**纯函数** `p0PayloadOf(result)`（只装跑成的、只认对象形状的 "
        "`p0_fastpath`）＋ 每轮边界 `beginP0Turn()` ＋ 读取口 `p0MemoRead()` ＋ 只给自证用的 "
        "`_resetP0MemoForTest` / `_armP0MemoForTest`；`executeTool` 里 `kb_review_chain` 命中快路时"
        "把 `{p0Fastpath, answer, p0Findings}` 留下来 —— 与链缓存**同一个漏斗、同一条纪律**"
        "（每轮清空、只装跑成的）。② `agent.mjs`：`beginP0Turn()` 紧跟 `beginChainTurn()`"
        "（闸门之前）；兜底那一支改成 `const p0Payload = p0MemoRead()`，**有载荷才展开**地把 "
        "`answer` 与 `p0Fastpath` 喂进 `deriveVerdictLine`，并打一行读数"
        "（`🧭 闸门没判送审、但这一轮 P0 快路命中了…`）。③ `agent.mjs` 工具循环留一个**注入点** "
        "`deps?.executeTool ?? executeTool`（默认值就是原来那一行，生产一个字不用改）—— "
        "这一条缺陷的判据只在接线上，此前**没有任何缝**能喂桩。④ `prd53.mjs`：PASS 支的 `conform` "
        "改成 `conforms(line)`（对象），与其余各支同形。⑤ 判据 `Y4–Y7`（第 22b 组，含三条反向对照）"
        "＋ Z12 补 conform 形状两半。"
    ),
    "enforced_by": [
        "p0PayloadOf",
        "p0MemoRead",
        "beginP0Turn",
        "Y4",
        "Y5",
        "Y5b",
        "Y6",
        "Y7",
    ],
    "self_check": "node tools/test_agent.mjs",
    "verify_cmd": "node tools/test_agent.mjs",
    "ingest_ref": "ref-shouheng-p0-fastpath-prd53-block-20261016",
    "readings": [
        "`node tools/test_agent.mjs` **251 / 3**（改动前 **246 / 3**）；那 3 条红与本条无关 —— "
        "「真跑一次本机转写」那一组（本机语音识别没授权），**改前改后逐字相同**",
        "`node tools/verify_cards.mjs` **347 / 0**｜`node tools/agent/prd53_format.test.mjs` **19 / 0**",
        "**离线复现件**（真单逐字夹具）：修前 `verdict53 = null ⇒ reviewShape=false ⇒ 模型自拟的卡照用`"
        "（**与线上那张 180 字卡逐字同形**）；修后结论行 `【审查结论：BLOCK】共发现 1 处必须修改。`"
        "＋逐条块 10 行，卡面 ✅原因 ✅依据 ✅建议 ✅「请修改后重新提交。」",
        "**反向对照**（逐条跑过）：兜底去掉 `answer`／`p0Fastpath` ⇒ Y4① 与 Y7 变红；"
        "`beginP0Turn()` 从 `handleMessage` 删掉 ⇒ Y6① 变红；`p0PayloadOf` 去掉「只装跑成的」那半 "
        "⇒ Y5 反向对照② 变红；arm 之后不调 `beginP0Turn()` ⇒ Y5b 第三步变红",
        "★ **未测的那一格如实记下**：`handleMessage` 内部那一跳（`p0MemoRead()` → "
        "`deriveVerdictLine`）**不在 Y7 里** —— 它要有一次真的模型往返才跑得到，而 LLM 那一跳"
        "**没有注入点**（真跑会真起链、真写飞书）。守着它的是 Y6 那两条**源码级**断言 ＋ 新加的 "
        "`deps.executeTool` 注入点",
    ],
    "docs": ["PMO/守衡-P0单上不了PRD逐条块-20261016.md"],
    "note": (
        "★ 这一条回答 Owner「**修复多次了，怎么还出现了**」：前几次修的是**产物层**"
        "（FIX-020/023/025/037 都在治「卡面上出现了不该出现的字」），而这一条是**启用条件**层 —— "
        "产物层再干净，「那一段压根没被启用」时也看不出来；每次修完自证都是绿的，绿的是**判据**、"
        "不是**接线**。★ 同一形状本仓已栽三次：FIX-021（`machineAnswer`）、本条（`p0Fastpath`）、"
        "以及 `Y1` 那条夹具里**假设模型会把结论行抄进回复**（实测不成立 —— "
        "**夹具里的假设就是判据的边界**）。★ 生效要重启守衡：`tools.mjs` / `agent.mjs` / `prd53.mjs` "
        "都是 `ws_daemon.mjs` import 得到的模块（重启闸门见 AGENTS.md §2.7，**必须先问、必须留痕**）。"
    ),
}


def main():
    ids = [json.loads(l)["id"] for l in JSONL.read_text(encoding="utf-8").splitlines() if l.strip()]
    if rec["id"] in ids:
        print(f"{rec['id']} 已被占 —— 不追加（先看一眼是不是别的会话写的）")
        return 1
    with JSONL.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"appended {rec['id']}；现在共 {len(ids) + 1} 条")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
