#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""守衡「命中原文 + 飞书链接」这条通路的判据（2026-10-09 加）。

为什么单独一个判据文件：这一块今天**连栽三次**，每次的形状都一样 ——
「产出者改了／能跑了」，但**人那边什么也没看见**：

  ① `_kbFromEngineJson` 只按 `risk_type` 拆类目，而引擎的覆盖行 `risk_type` **没有连字符**
     ⇒ 覆盖行被误归进 findings ⇒ 挂在 `coverage` 上的渲染**永不执行**；
  ② 修好①后渲染进 `coverage.reasonLine` —— 而 `agent.mjs` **压根不用 `kb.coverage`**
     ⇒ 渲染进**没人读的字段**；
  ③ `kb_hits` 只写在「覆盖缺口」一条支路 ⇒ **库真命中的正常单子反而没有读数**
     （与 Owner 的「**所有**视频都要带」正好相反）。

⇒ 判据必须盯住**真实产出**与**真实数据**，不是合成样本：
  · 用真引擎跑（`_evidence_findings` + `run()`），断言**每条命中都有可点直链**；
  · 用**真实库里存在的** record_id 验 `bitable:` 那条回落（`recvuNifmKBXoP`）；
  · 反向对照：查不到就 **None**，**不许编**。

跑法：`python3 kb/l7/review-engine/tests/test_kb_hits.py`
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.join(os.path.dirname(HERE), "core")
sys.path.insert(0, CORE)

import with_kb_evidence as W  # noqa: E402

PASS, FAIL = [], []


def eq(name, got, want):
    (PASS if got == want else FAIL).append(name)
    print(("  ✅ " if got == want else "  ❌ ") + name
          + ("" if got == want else "  —— 期望 %r，实得 %r" % (want, got)))


def main():
    print("── A 组：`_clickable_of()` 的键形态（带真实形态样本）──")
    # `url:` 前缀：键里**本来就嵌着一条真 URL**。实测 2/5 条命中栽在这里。
    eq("A1 `url:https://…` ⇒ 取出那条 URL（不是 None）",
       W._clickable_of("url:https://momcozy-in.feishu.cn/wiki/Zqz7w1W9ZiP7i8kXNTGc9cBGnVb"),
       "https://momcozy-in.feishu.cn/wiki/Zqz7w1W9ZiP7i8kXNTGc9cBGnVb")
    eq("A2 `wiki:<tok>` ⇒ 拼出可点地址",
       W._clickable_of("wiki:YNnwdkTULoJLccxKnypcHwsinBZ"),
       "https://momcozy-in.feishu.cn/wiki/YNnwdkTULoJLccxKnypcHwsinBZ")
    eq("A3 裸 http ⇒ 原样返回", W._clickable_of("https://x.cn/a"), "https://x.cn/a")
    eq("A4 反向对照：空 / 认不出的键 ⇒ None（**不许编**）",
       [W._clickable_of(None), W._clickable_of("bitable:xxx"), W._clickable_of("url:不是http")],
       [None, None, None])

    print("── B 组：`_hit_link()` 三级回落（`bitable:` 那类走 L0 记录级直链）──")
    # 真实样本：L6 索引里这一行**没有** `l0_entry_url`，`resource_key` 是 `bitable:…`，
    # 而 L0 记录里有带 `&record=` 的记录级直链。
    rec = "recvuNifmKBXoP"
    rid = "bitable__Lk3Qb8y2QaVyZns6gprcVNE9nA0__" + rec
    link = W._hit_link({"anchor": "#x"}, rid, {rid: "bitable:Lk3Qb8y2QaVyZns6gprcVNE9nA0:" + rec})
    eq("B1 `bitable:` 键 ⇒ 回落到 **L0 记录级直链**（含 `&record=`）",
       bool(link) and link.startswith("https://") and ("record=" + rec) in link, True)
    eq("B2 第一级优先：命中行自带 `l0_entry_url` 时**原样用**",
       W._hit_link({"l0_entry_url": "https://a.cn/1"}, rid, {}), "https://a.cn/1")
    eq("B3 第二级：`wiki:` 键走 `_clickable_of`",
       W._hit_link({}, "url__x", {"url__x": "wiki:Tok123"}), "https://momcozy-in.feishu.cn/wiki/Tok123")
    eq("B4 反向对照：三级都取不到 ⇒ None（**卡上写「取不到直链」，不许编**）",
       W._hit_link({}, "不存在的资源__zzzzzzzz", {}), None)

    print("── C 组：`kb_hits_of()` 的字段与条数 ──")
    eq("C1 空输入 ⇒ 空列表（不是 None、不是异常）", W.kb_hits_of(None), [])
    eq("C2 没片段的命中**跳过**（不产空壳行）",
       W.kb_hits_of([{"anchor": "#a", "bm25": 1.0}]), [])
    h1 = W.kb_hits_of([{"anchor": "#a", "bm25": 2.0, "excerpt": "  原文  片段  ",
                        "kb_type": "wording", "source_sha256": "s" * 64}])
    eq("C3 有片段的命中收下来，且**只搬运不改写**（空白归一）",
       [h1[0]["anchor"], h1[0]["bm25"], h1[0]["kb_type"], h1[0]["excerpt"]],
       ["#a", 2.0, "wording", "原文 片段"])
    eq("C4 `url` 取不到时如实为 None（**不编**）", h1[0]["url"], None)

    print("── D 组：**三条支路都要带 `kb_hits`**（Owner：「所有视频都带」）──")
    # 真跑引擎（不喂 findings 缓存），三条支路的返回里都必须含这个键。
    seen = {}
    for tag, text in (("正常/命中", "这条社媒文案能不能发：美国FDA认证的吸奶器，完全无痛，模拟婴儿吸吮，宝宝睡得香。"),
                      ("覆盖缺口", "这条展会物料能不能发：M6 吸奶器附赠收纳袋与备用阀门，支持洗碗机清洗。")):
        res, err = W.run(text, decision_owner="文案合规审查", loaded_skills=["文案合规审查"],
                         content_type="text")
        if res is None:
            print("  ⚠️ 跑不起来（%s），跳过这一支" % err)
            continue
        em = res.get("evidence_meta") or {}
        seen[tag] = em.get("kb_hits")
        eq("D 支路[%s]：`evidence_meta` 里**必须有** `kb_hits` 键" % tag, "kb_hits" in em, True)
        hits = em.get("kb_hits") or []
        if hits:
            miss = [h for h in hits if not h.get("url")]
            eq("D 支路[%s]：%d 条命中**每条都要有可点直链**（缺 %d 条）" % (tag, len(hits), len(miss)),
               miss, [])
            print("     样例：%s" % (hits[0].get("url") or "(无)"))

    print("\n通过 %d / 失败 %d" % (len(PASS), len(FAIL)))
    if FAIL:
        print("失败项：")
        for f in FAIL:
            print("  - " + f)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
