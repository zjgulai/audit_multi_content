#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_negative_rule_trigger.py —— 「负面样本规则层该不该跑」的判据（含反向对照）。

## 为什么单独立这一把尺子（2026-10-20）

`layer_negative_rules` 只在三个条件之一成立时才跑：

    (content_type == "image") or (scene is not None) or _looks_image

而 `--content-type` 是 **headless 里的模型自己选的**（模板只写「三选一」）。
实测（2026-10-20 10:06 / 11:10 两次，同一份图 OCR）：

    10:06:48  content_type=text   → PASS / 0 条   ← 这一层根本没跑
    11:10:00  content_type=image  → REVIEW / 5 条

⇒ 「同一张图，选错一个词就整层失效」。守衡实际送进 `--text` 的正文恒以
`【图片 1 的图内文字（本机 OCR）】` 开头 —— **这就是现成的、不依赖上游选对的信号**。

本尺子量两件事，缺一不可（只有 A 组会把判据做成「恒真」）：

  A 组 图必须触发 —— 图内文字（本机 OCR）/ 画面读数 / content_type=image 三条路各自成立
  B 组 文字单不许被误触发 —— 普通文案里出现「图片」「图」「素材」等字样**不算图**

## 判据形状

只读引擎 JSON 的 `trace.negative_rules.engine`：
  · 有 engine 字段 ⇒ 这一层**跑过**
  · 无 ⇒ **没跑**（不是"跑了没命中"，两者必须分得开）

退出码：0 = 全过 ｜ 3 = 有判据红

用法：python3 kb/l8/check_negative_rule_trigger.py [--selftest]
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
KB = os.path.dirname(HERE)
WS = os.path.dirname(KB)
REVIEW = os.path.join(KB, "l7", "skills", "kb-content-review", "scripts", "review.py")

# ── 夹具：**逐字取自真实单子**（2026-10-20 10:07 那单的 input_manifest）────────
OCR_ONLY = (
    "【图片 1 的图内文字（本机 OCR）】\n"
    "Breastfeeding Month\n"
    "Share What Helped. Find Real Support.\n"
    "Help Another Mom.\n"
    "Share real breastfeeding and pumping experiences，\n"
    "help build the Support List, and get a chance to win prizes worth\n"
    "up to $199.99.\n"
    "Join Breastfeeding Month\n"
    "MOmCOZY\n"
    "MOmCOZY"
)
# 守衡把画面读数拼进正文时的形状（`agent.mjs` 的 `【图 N 画面读数 …】/【/图 N 画面读数】`）
SCENE_BLOCK = (
    "【图 1 画面读数（视觉模型的读数，**不是原图**；涉及画面的结论只能依据这一格）】\n"
    "- 场景：客厅\n- 人物：成人 · 坐在沙发上拿笔写字\n"
    "【/图 1 画面读数】"
)
# B 组：纯文字单（**不许**触发负样本层）
TEXT_CN = "这条社媒文案能不能发：我们的吸奶器支持洗碗机清洗，附赠收纳袋与备用阀门。"
TEXT_EN = "Momcozy M5 wearable breast pump. Quiet, hands-free pumping for busy moms."
# B3：正文里有「图片」字样，但没有任何读数标记 —— 最容易被写宽的误伤形状
TEXT_MENTIONS_IMAGE = "这条图片素材能不能发：图 1 是我们的主图，图里产品支持洗碗机清洗。"


class Unmeasured(Exception):
    """跑是跑了，但引擎拒答、层根本没执行 ⇒ 本判据**未测**（不许读成不跑）。"""


def _has_layer(doc):
    nr = ((doc.get("trace") or {}).get("negative_rules")) or {}
    return bool(nr.get("engine")), nr


def run_review(text, ctype, tag):
    """跑一次引擎（只读 dry-run，报告落临时目录），返回 (state, 层跑没跑, 命中数)。"""
    tmp = tempfile.mkdtemp(prefix="negtrig-")
    tf = os.path.join(tmp, "m.txt")
    with open(tf, "w", encoding="utf-8") as fh:
        fh.write(text)
    try:
        p = subprocess.run(
            [sys.executable, REVIEW, "--i-am-the-entry", "--file", tf,
             "--content-type", ctype, "--json", "--dry-run",
             "--report-dir", tmp, "--run-id", "trig-" + tag],
            cwd=WS, capture_output=True, text=True, timeout=300)
        if p.returncode not in (0, 3) or not (p.stdout or "").strip():
            raise RuntimeError("引擎退出码 %s：%s" % (p.returncode, (p.stderr or "")[-400:]))
        doc = json.loads(p.stdout)
        # ★★ 未测 ≠ 不跑：供给链拒答（fail-closed）时引擎**根本不跑层**，trace 是空的。
        #   把它读成「层没跑」会对**新鲜度**判红、而不是对**触发条件**判红 —— 两件事必须分开报。
        #   （实测 2026-10-20 11:55：上游 L6 重建 ⇒ L7 判陈旧 ⇒ 6/6 全被读成「红」。）
        if p.returncode == 3 and not (doc.get("trace") or {}):
            raise Unmeasured("供给链拒答（fail-closed）⇒ 引擎没跑层，本判据**未测**"
                             "（不是绿、也不是触发条件红）")
        ran, nr = _has_layer(doc)
        return doc.get("state"), ran, len(nr.get("hits") or [])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true",
                    help="辨别力对照：证明这把尺子对「跑」和「不跑」两种结果都有样本"
                         "（否则它对两种情形给同一个答案 ⇒ 恒真或恒假）")
    a = ap.parse_args()

    # (标签, 文本, content_type, 期望「层跑了吗」)
    cases = [
        ("A1 图内文字OCR + content-type=text（守衡实际口径）", OCR_ONLY, "text", True),
        ("A2 图内文字OCR + content-type=image", OCR_ONLY, "image", True),
        ("A3 画面读数块 + content-type=text", SCENE_BLOCK, "text", True),
        ("B1 中文纯文案 + text", TEXT_CN, "text", False),
        ("B2 英文纯文案 + text", TEXT_EN, "text", False),
        ("B3 正文提到「图片」但无读数标记 + text", TEXT_MENTIONS_IMAGE, "text", False),
    ]
    bad = 0
    unm = 0
    seen_ran = set()
    print("=" * 78)
    print("负面样本规则层 · 触发判据" + ("（反向对照）" if a.selftest else ""))
    print("=" * 78)
    for lab, txt, ct, want in cases:
        try:
            state, ran, hits = run_review(txt, ct, lab[:2].strip())
        except Unmeasured as e:                      # 未测：既不绿也不红，单独报
            print(f"  ⚠ {lab}\n      **未测**：{e}")
            unm += 1
            continue
        except Exception as e:                       # noqa: BLE001
            print(f"  ✗ {lab}\n      没跑成：{e}")
            bad += 1
            continue
        seen_ran.add(ran)
        ok = (ran == want)
        mark = "✓" if ok else "✗"
        print(f"  {mark} {lab}\n      期望层{'跑' if want else '不跑'}｜实际{'跑' if ran else '不跑'}"
              f"｜state={state}｜命中 {hits}")
        if not ok:
            bad += 1
    print("-" * 78)
    if a.selftest:
        # ★ 辨别力对照：这把尺子要么**看见过「跑了」**、要么**看见过「没跑」**，
        #   否则它对两种情形给同一个答案 —— 那就不是判据，是常量。
        #   （当前红的是 A1；这条不影响辨别力成立：A2/A3 为真，B 组为假。）
        okd = (True in seen_ran) and (False in seen_ran)
        print(f"辨别力对照：本组样本里「跑了」={True in seen_ran}｜「没跑」={False in seen_ran}"
              f" ⇒ {'成立' if okd else '**不成立：恒真/恒假**'}")
        return 0 if okd else 3
    print(f"合计 {len(cases)} 条｜红 {bad} 条｜未测 {unm} 条")
    if unm:
        print("⚠ 有未测项 ⇒ **不得判通过**（未测不是绿；先把供给链跑回新鲜再复跑本判据）")
        return 3
    return 0 if bad == 0 else 3


if __name__ == "__main__":
    sys.exit(main())
