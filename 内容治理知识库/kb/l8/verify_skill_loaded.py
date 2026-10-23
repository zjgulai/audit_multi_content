#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verify_skill_loaded.py —— 「**本会话到底有没有真的加载过**这个 skill」的**观测**判据。

## 为什么它和 `--loaded-skill` 不是一回事

引擎的 `--loaded-skill` 是**申报**（agent 自己说"我加载了"），AGENTS 明写它是
`agent_reported` 档、**不得当强证据**。2026-10-21 实测证明这个担心是真的：

    10:02  模型调 skill("图片安全审查")  → 返回 Error: … unknown or no longer available
    10:02  模型随后申报 --loaded-skill 图片安全审查   ← 申报成功，实际没加载

⇒ 申报与事实相反，而流程里没有任何东西会红。

本脚本改从**会话日志**里读事实：harness 把每次工具调用与结果都落在
`session.jsonl.zstd`（`type=tool/call` / `type=tool/result`）。判据：

* `tool/call`：`data.name == "skill"`，`data.arguments` 的 `name` 命中目标 skill；
* 对应该 `callId` 的 `tool/result`：`data.message.source.callId` 相等，
  `content[0].content[0].text` 里出现 `<skill_content` ⇒ **真的加载了**；
  出现 `unknown or no longer available` / `not available for model invocation` ⇒ **没加载**；
* 取**最后一次**调用的结果为准（先失败后修好 ⇒ 记 loaded，并把中间失败一并列出）。

## 三态（**未测不许当通过**）

| verdict | 含义 | 退出码 |
|---|---|---|
| `loaded` | 观测到成功加载 | 0 |
| `error_unknown` / `error_not_invocable` / `error_other` / `pending` / `no_call` | **没加载**（含"本会话从没调过"） | 4 |
| `untested` | 会话日志缺失 / 无 `zstandard` / 格式不认识 ⇒ **未测**（不是通过，也不是失败） | 5 |

## 用法

    python3 kb/l8/verify_skill_loaded.py --skill 图片安全审查
    python3 kb/l8/verify_skill_loaded.py --skill 图片安全审查 --session <path.jsonl.zstd> --json
    python3 kb/l8/verify_skill_loaded.py --selftest     # 用本会话**逐字**抓的两条真实记录当夹具

**只读**：不解压到盘上、不改任何文件。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

#: 成功标志：skill 工具返回的正文包装（`dsh-skill` 的 renderSkillContent）
LOADED_MARK = "<skill_content"
ERR_UNKNOWN = "unknown or no longer available"
ERR_NOT_INVOCABLE = "not available for model invocation"


def _decompress_zstd(raw_bytes: bytes) -> bytes:
    """解压会话日志。**必须走 stream_reader**。

    会话日志是**追加写**的 ⇒ 盘上可能是**多个 zstd 帧**首尾相接；
    `ZstdDecompressor().decompress()` 只解**第一帧**（实测本会话：只拿到开头几百行，
    于是把"明明调过"的 skill 判成 `no_call` —— **假红比不判更坏**）。
    """
    import io

    import zstandard                                    # noqa: PLC0415
    with zstandard.ZstdDecompressor().stream_reader(io.BytesIO(raw_bytes)) as r:
        return r.read()


def iter_events(path: Path):
    """逐行吐事件（dict）。.zst/.zstd 用 zstandard 流式解压；其余按纯文本。"""
    raw_bytes = path.read_bytes()
    if path.suffix.lower() in (".zst", ".zstd") or raw_bytes[:4] == b"\x28\xb5\x2f\xfd":
        try:
            import zstandard                              # noqa: PLC0415
        except Exception:
            raise RuntimeError("缺 zstandard 模块，无法读会话日志（未测，不是未加载）")
        raw = _decompress_zstd(raw_bytes)
    else:
        raw = raw_bytes
    for line in raw.decode("utf-8", "replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            yield json.loads(line)
        except Exception:                                 # noqa: BLE001 —— 单行坏不毁整份
            continue


def collect(events) -> tuple[dict, dict]:
    """收齐 skill 工具调用与它们的返回。返回 (calls, results)，键均为 callId。"""
    calls, results = {}, {}
    for d in events:
        t = d.get("type")
        data = d.get("data") or {}
        if t == "tool/call" and data.get("name") == "skill":
            try:
                args = json.loads(data.get("arguments") or "{}")
            except Exception:                             # noqa: BLE001
                continue
            calls[data.get("callId")] = {"skill": args.get("name"),
                                         "seq": d.get("seq"), "time": d.get("time")}
        elif t == "tool/result":
            msg = data.get("message") or {}
            cid = (msg.get("source") or {}).get("callId")
            if cid:
                results[cid] = msg
    return calls, results


def result_text(msg: dict) -> tuple[str, bool]:
    """从 tool/result 的 message 里取出 (正文, 是否报错)。"""
    texts, is_err = [], False
    for block in (msg.get("content") or []):
        if block.get("type") != "tool-result":
            continue
        is_err = is_err or bool(block.get("isError"))
        for c in (block.get("content") or []):
            if c.get("type") == "text":
                texts.append(c.get("text") or "")
    return "\n".join(texts), is_err


def classify(text: str, is_error: bool) -> str:
    if LOADED_MARK in text:
        return "loaded"
    if ERR_UNKNOWN in text:
        return "error_unknown"
    if ERR_NOT_INVOCABLE in text:
        return "error_not_invocable"
    if is_error or text.lstrip().startswith("Error:"):
        return "error_other"
    return "pending"


def verify(skill: str, session: Path | None) -> dict:
    out = {"skill": skill, "session": str(session) if session else None,
           "verdict": "untested", "reason": "", "calls": []}
    if session is None or not Path(session).exists():
        out["reason"] = "没有会话日志（---session 未给、$DSH_SESSION_JSONL 也没有）⇒ 未测"
        return out
    try:
        calls, results = collect(iter_events(Path(session)))
    except RuntimeError as e:
        out["reason"] = str(e) + " ⇒ 未测"
        return out
    except Exception as e:                                # noqa: BLE001
        out["reason"] = "会话日志读不了：%s ⇒ 未测" % e
        return out

    mine = [(cid, meta) for cid, meta in calls.items() if meta["skill"] == skill]
    mine.sort(key=lambda x: x[1].get("seq") or 0)
    if not mine:
        out["verdict"] = "no_call"
        out["reason"] = "本会话日志里**没有** skill(%r) 的调用记录 ⇒ 没加载过" % skill
        return out

    for cid, meta in mine:
        msg = results.get(cid)
        if msg is None:
            out["calls"].append({"callId": cid, "seq": meta.get("seq"), "verdict": "pending"})
            continue
        text, is_err = result_text(msg)
        out["calls"].append({"callId": cid, "seq": meta.get("seq"),
                             "verdict": classify(text, is_err),
                             "excerpt": text[:120]})
    last = out["calls"][-1]["verdict"]
    out["verdict"] = last
    if last != "loaded":
        out["reason"] = "本会话对 %r 的**最后一次** skill 调用没有加载成功（%s）" % (skill, last)
    elif any(c["verdict"] != "loaded" for c in out["calls"]):
        out["reason"] = ("最后一次加载成功；但本会话中**有过失败调用**（见 calls）——"
                         "失败发生在修复之前，属如实留痕，不是当前的错")
    return out


def selftest() -> int:
    """纯夹具自证：**两条都是本会话逐字抓的真实记录**（2026-10-21 session-2aa04e21）。"""
    passed = failed = 0

    def expect(label: str, cond: bool, detail: str = "") -> None:
        nonlocal passed, failed
        if cond:
            passed += 1
        else:
            failed += 1
            print("  ❌ %s %s" % (label, detail))

    # ① 失败样本：10:02 那次（skill 文件坏着，catalog 里没有）
    fail_lines = [
        '{"type": "tool/call", "seq": 4835, "time": 1792548139673, "data": '
        '{"turn": 1, "step": 5, "callId": "call_01_2i9UTrHBn5rgXcRZQjzY9176", "name": "skill", '
        '"arguments": "{\\"name\\": \\"图片安全审查\\"}"}}',
        '{"type": "tool/result", "seq": 4836, "time": 1792548139678, "data": {"turn": 1, "step": 5, '
        '"message": {"source": {"kind": "tool", "callId": "call_01_2i9UTrHBn5rgXcRZQjzY9176"}, '
        '"content": [{"type": "tool-result", "toolCallId": "call_01_2i9UTrHBn5rgXcRZQjzY9176", '
        '"content": [{"type": "text", "text": "Error: skill \\"图片安全审查\\" is unknown or no longer available"}], '
        '"isError": true}], "role": "tool", "id": "x"}}}',
    ]
    # ② 成功样本：修好文件之后那次（同一会话、逐字）
    ok_lines = [
        '{"type": "tool/call", "seq": 77637, "time": 1792548879925, "data": '
        '{"turn": 2, "step": 55, "callId": "call_00_GahsVTpLV4AC4Rpjxoto7047", "name": "skill", '
        '"arguments": "{\\"name\\": \\"图片安全审查\\"}"}}',
        '{"type": "tool/result", "seq": 77638, "time": 1792548879932, "data": {"turn": 2, "step": 55, '
        '"message": {"source": {"kind": "tool", "callId": "call_00_GahsVTpLV4AC4Rpjxoto7047"}, '
        '"content": [{"type": "tool-result", "toolCallId": "call_00_GahsVTpLV4AC4Rpjxoto7047", '
        '"content": [{"type": "text", "text": "<skill_content name=\\"图片安全审查\\">\\n正文…\\n</skill_content>"}], '
        '"isError": false}], "role": "tool", "id": "y"}}}',
    ]
    import tempfile
    tmp = Path(tempfile.mkdtemp(prefix="verify-skill-selftest-"))
    p_fail, p_ok = tmp / "fail.jsonl", tmp / "ok.jsonl"
    p_fail.write_text("\n".join(fail_lines) + "\n", encoding="utf-8")
    p_ok.write_text("\n".join(ok_lines) + "\n", encoding="utf-8")

    # 反面：失败样本必须判「没加载」（判成 loaded 就是恒绿，这条钉死它）
    r = verify("图片安全审查", p_fail)
    expect("① 失败样本 ⇒ error_unknown", r["verdict"] == "error_unknown", r["verdict"])
    # 正面：成功后必须判 loaded
    r = verify("图片安全审查", p_ok)
    expect("② 成功样本 ⇒ loaded", r["verdict"] == "loaded", r["verdict"])
    # 未测：会话缺失不是"通过"也不是"失败"
    r = verify("图片安全审查", tmp / "nope.jsonl")
    expect("③ 无会话日志 ⇒ untested", r["verdict"] == "untested", r["verdict"])
    # 没调过：日志在、但没这个 skill 的调用
    r = verify("根本没装这个skill", p_ok)
    expect("④ 没调用过 ⇒ no_call", r["verdict"] == "no_call", r["verdict"])
    # 先失败后成功：最终判 loaded，但中间失败要留痕（不许被抹平）
    both = tmp / "both.jsonl"
    both.write_text("\n".join(fail_lines + ok_lines) + "\n", encoding="utf-8")
    r = verify("图片安全审查", both)
    expect("⑤ 先失败后成功 ⇒ loaded 且留痕失败",
           r["verdict"] == "loaded" and len(r["calls"]) == 2
           and r["calls"][0]["verdict"] == "error_unknown",
           json.dumps(r["calls"], ensure_ascii=False))
    # 坏行不毁整份
    p_bad = tmp / "badline.jsonl"
    p_bad.write_text("{not json}\n" + "\n".join(ok_lines) + "\n", encoding="utf-8")
    r = verify("图片安全审查", p_bad)
    expect("⑥ 坏行容错 ⇒ 仍判 loaded", r["verdict"] == "loaded", r["verdict"])
    # 其他 skill 的调用不算数（不许串台）
    r = verify("文案合规审查", p_ok)
    expect("⑦ 不串台 ⇒ no_call", r["verdict"] == "no_call", r["verdict"])

    print("verify_skill_loaded selftest：通过 %d ／ 失败 %d（夹具目录 %s）" % (passed, failed, tmp))
    return 0 if failed == 0 else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="观测本会话是否真的加载过某个 skill（读会话日志）")
    ap.add_argument("--skill", default=None, help="skill 名")
    ap.add_argument("--session", default=None, help="会话日志（默认 $DSH_SESSION_JSONL）")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)

    if a.selftest:
        return selftest()
    if not a.skill:
        print("给 --skill <名字>（或 --selftest）", file=sys.stderr)
        return 2

    session = a.session or os.environ.get("DSH_SESSION_JSONL")
    r = verify(a.skill, Path(session) if session else None)
    if a.json:
        print(json.dumps(r, ensure_ascii=False, indent=1))
    elif not a.quiet:
        mark = {"loaded": "✅", "untested": "⚠️"}.get(r["verdict"], "❌")
        print("%s %s ｜ verdict=%s" % (mark, r["skill"], r["verdict"]))
        if r["reason"]:
            print("   %s" % r["reason"])
        for c in r["calls"]:
            print("   · call %s（seq=%s）→ %s%s"
                  % (c["callId"], c.get("seq"), c["verdict"],
                     ("：" + c["excerpt"]) if c.get("excerpt") else ""))

    if r["verdict"] == "loaded":
        return 0
    if r["verdict"] == "untested":
        return 5
    return 4


if __name__ == "__main__":
    sys.exit(main())
