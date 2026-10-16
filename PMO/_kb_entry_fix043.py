#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
入库载荷：`ref-shouheng-p0-fastpath-prd53-block-20261016`（FIX-043 的参考实现条）

**为什么写成文件而不是直接在会话里敲**：正文与元数据都很长（十几条 `asks` / `not_proves` /
`forbidden` + 六节正文），而 `kb_ingest` 每次尝试都会落一行账本 —— 手工拼一长串 JSON
出一次语法错就白记一笔。放这儿之后，调用点只剩一次 `kb_ingest(meta=..., body=...)`。

字段口径来源（逐条核过，不是猜的）：
  · `source.fingerprint` = 该留底文件的 **sha256 全长**（对照 `ref-shouheng-pass-card-one-line-20261016`
    的 frontmatter 与 `sha256sum`，逐字相同）；
  · `valid_until` = `created_at + half_life_days`（90 天）；
  · `kb_class: []` —— 显式声明「判断过，不属四类素材」（同 `ref-*` 家族其余各条）；
  · `evidence_group: coordinate` / `tier: L1` —— 同家族各条。

★ 入库闸门的现状：`kb_ingest` 回 **E040**（`canonical_write=false`）——
  「本库约定入库是人的动作，机器直写权威树被拒」，要带 `{human: true, actor: '<具名人>'}`。
  所以这个载荷**不是**绕过闸门的脚本，它只是把要写的东西准备好，等 Owner 点头。
"""
from __future__ import annotations

import hashlib
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "PMO/守衡-P0单上不了PRD逐条块-20261016.md"

ENTRY_ID = "ref-shouheng-p0-fastpath-prd53-block-20261016"

META = {
    "id": ENTRY_ID,
    "title": "P0 快路单的 PRD §5.3 逐条块上不了卡 —— 判据写好了、没人接（同形第三次）",
    "collection": "3_措辞表达库",
    "tier": "L1",
    "topic": "守衡系统 · 产物形态的启用条件与接线判据",
    "summary": (
        "真单 om_x100b622a8e762cbcce3b9bfa8402ccb（群里问「m5 pro是最好的吸奶器，这句话能过审吗？」）"
        "回了一张 180 字卡：只有一行结论 + 四组折叠摘要，PRD §5.3.3 的逐条块"
        "（原因/依据/建议/动作行）一个字都没有 —— 而链其实给了完整那一份。根因两层："
        "① 那一单送审闸门判「不是送审」⇒ g.verdict53 = null（链是模型自己调的）；"
        "② 内核兜底那一支只喂 replyText ⇒ 结论行取决于「模型有没有把链那一行抄进回复」。"
        "而 prd53.deriveVerdictLine 第 ② 支早就会按 p0Fastpath.matched_patterns 派生 §5.3.3 那一行、"
        "W1 一直在喂它，全仓却没有一个调用点给它传过 p0Fastpath。修法：把链返回里那几格"
        "（answer / p0_fastpath / p0_findings）按「每轮清空、只装跑成的」留下来，"
        "兜底那一支有载荷才展开地喂进去；并给工具循环加一个注入点，让这条接线能端到端跑。"
    ),
    "owner": "刘华丽",
    "evidence_level": "L2",
    "data_level": "L2",
    "half_life_days": 90,
    "created_at": "2026-10-16",
    "valid_until": "2027-01-14",
    "asks": [
        "守衡回的那张卡为什么没有 PRD §5.3 的逐条块（原因/依据/建议/动作行）",
        "为什么「闸门判不是送审、链是模型自己调的」这一条路会把结论行寄在模型的措辞上",
        "deriveVerdictLine 的 P0 快路那一支早就写好了，为什么线上还是不出块",
        "同一形状（判据被验过 ≠ 它被接上了）在本仓还栽过哪几次",
        "P0 快路读数为什么要每轮清空、为什么只装跑成的",
        "为什么给工具循环加注入点，而不是只写一条源码文本断言",
        "怎么判断一条卡面缺陷是「产物层」还是「启用条件」层（前者自证能拦住，后者拦不住）",
    ],
    "not_proves": (
        "不能证明任何一条具体内容能不能发（它讲的是卡面形态与接线，不是条款判定）；"
        "不能替代 3_措辞表达库 的任何条款（条款号/命中表达/锚点以权威库 kb/l3、kb/l4 为准）；"
        "不能证明这一修已经生效 —— tools.mjs / agent.mjs / prd53.mjs 都是 ws_daemon 进程 import "
        "得到的模块，**必须重启守衡才生效**（重启闸门见 AGENTS.md §2.7，要先问、要留痕），"
        "本条写作时尚未重启；不能证明 handleMessage 内部那一跳"
        "（p0MemoRead() → deriveVerdictLine）已被端到端验过（Y7 走不到那一跳，LLM 没有注入点）；"
        "不能证明「P0 快路是唯一会走这条路的形态」（同类接缝可能还在别处）。"
    ),
    "kb_class": [],
    "evidence_group": "coordinate",
    "source": {
        "kind": "file",
        "ref": "PMO/守衡-P0单上不了PRD逐条块-20261016.md",
        "captured_at": "2026-10-16",
    },
    "corroborated_by": [
        "真单对照：台账 PMO/logs/ws_outbound.jsonl 第 1400 行（180 字卡面，四组折叠摘要）"
        "+ 守护进程日志 ws_daemon.log 第 20499–20508 行（闸门不起链 / P0 命中 63.121 ms / "
        "全程没有 📋 PRD §5.3 结论行那一行）",
        "链侧实跑复核：kb/kbpy l5/p0_fastpath.py --file <那一句> --json 的 rendered 字段，"
        "与真单会话第 147 条逐字相同（同一份结论行 + 四要素 + 动作行）",
        "离线复现件：修前 verdict53=null ⇒ reviewShape=false ⇒ 模型自拟的卡照用"
        "（与线上 180 字卡逐字同形）；修后卡面 ✅原因 ✅依据 ✅建议 ✅「请修改后重新提交。」",
        "判据读数：test_agent 251/3（改动前 246/3，那 3 条红是本机语音识别没授权，改前改后逐字相同）"
        "｜verify_cards 347/0｜prd53_format 19/0",
        "反向对照四条各自精确变红：兜底去掉 answer/p0Fastpath ⇒ Y4①+Y7 红；删掉 beginP0Turn() "
        "⇒ Y6① 红；p0PayloadOf 去掉「只装跑成的」⇒ Y5② 红；arm 后不清空 ⇒ Y5b 第三步红",
    ],
    "pii": {
        "detected": False,
        "masked": False,
        "strategy": "未检出自然人信息：正文为代码位置、判据名与台账行号，不含姓名、联系方式等个人数据；"
                    "文中「Owner」为角色指称；如后续来源变化需重新判定",
    },
    "provenance": {
        "anchor": "PMO/守衡-P0单上不了PRD逐条块-20261016.md#一/#二/#三/#四/#五/#六",
        "confidence": "确定",
    },
    "sensitivity_level": "L2",
    "forbidden": (
        "不许据本条判断某条素材能不能发；不许把「读 P0 读数派生结论行」扩到**没跑快路**的送审单"
        "（那会给走链的单子编一条不是它算出来的 §5.3 行）；不许把 P0 读数缓存读成可以跨轮复用"
        "（必须每轮清空，否则会把上一单的结论搬到这一张卡上）；不许把本条当成「重启已经做过」的凭据。"
    ),
}


def main() -> int:
    if not SRC.exists():
        print(f"留底件不在：{SRC}")
        return 1
    fp = hashlib.sha256(SRC.read_bytes()).hexdigest()
    meta = dict(META)
    meta["source"] = dict(meta["source"], fingerprint=fp)
    print(json.dumps({"id": ENTRY_ID, "fingerprint": fp, "meta": meta}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
