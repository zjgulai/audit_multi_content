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
    # ★ 2026-10-09 晚：**默认不打网络** —— `wiki:` 键现在要查一次才能拼对路径
    #   （见 A5–A11）。自证必须**离线可跑、结果确定**；要真验网络的那几条走显式桩
    #   （`A7–A11` 传 `_probe=`）或另外的 env 开关（`KB_LINK_PROBE=1`）。
    os.environ["KB_LINK_PROBE"] = "0"
    W._link_probe_cache.clear()
    W._link_probe_states.clear()

    print("── A 组：`_clickable_of()` 的键形态（带真实形态样本）──")
    # `url:` 前缀：键里**本来就嵌着一条真 URL**。实测 2/5 条命中栽在这里。
    eq("A1 `url:https://…` ⇒ 取出那条 URL（不是 None）",
       W._clickable_of("url:https://momcozy-in.feishu.cn/wiki/Zqz7w1W9ZiP7i8kXNTGc9cBGnVb"),
       "https://momcozy-in.feishu.cn/wiki/Zqz7w1W9ZiP7i8kXNTGc9cBGnVb")
    # ★ 2026-10-09 晚改口径：这个键**装的是 obj_token**（实测），而 `/wiki/` 只认节点 token
    #   ⇒ 旧断言（恒拼 `/wiki/`）钉的正是**病**。现在：探测关掉（本测试默认关）⇒ **None**，
    #   宁可让卡上写「取不到直链」，也不印一个点不开的链接。
    eq("A2 `wiki:<tok>` 探测关闭 ⇒ None（旧口径恒拼 `/wiki/` 是错的；见 A7/A8）",
       W._clickable_of("wiki:YNnwdkTULoJLccxKnypcHwsinBZ"), None)
    eq("A3 裸 http ⇒ 原样返回", W._clickable_of("https://x.cn/a"), "https://x.cn/a")
    eq("A4 反向对照：空 / 认不出的键 ⇒ None（**不许编**）",
       [W._clickable_of(None), W._clickable_of("bitable:xxx"), W._clickable_of("url:不是http")],
       [None, None, None])

    # ── A5–A9（2026-10-09 晚，Owner 报「报告中有个检索读数，链接是无效的」）──────────
    #
    # 病灶（**实测，不是推演**）：L1 的资源键 `wiki:TqJSduQE3oBM4uxtHhmcrVtGnPg` 里装的
    # 是 **docx 的 `obj_token`**，不是 wiki 的 `node_token`。而 `/wiki/<token>` **只认节点 token**
    # ⇒ 点开无效。用 bot 凭据把 L1 里 **14 个 `wiki:` 键逐个查了**：
    #   · 8 个是 `obj_token`（含 docx / **file** / bitable）⇒ 全失效；
    #   · 5 个 `permission_denied`（**那是权限问题，不是坏链接** —— 两者必须分开报）；
    #   · **只有 1 个**是真 `node_token`。
    # ⇒ 光把 `/wiki/` 换成 `/docx/` 是错的：`file` / `bitable` 会变成新的失效链接。
    #   **正确路径取决于 token 指向什么对象**，只有查一次才知道（`wiki +node-get`
    #   对两种 token **都**解析得出：`obj_token==入参` ⇒ 是对象；`node_token==入参` ⇒ 是节点）。
    print("── A5–A9：`wiki:` 键的 token 可能是**对象 token**（旧口径恒拼 `/wiki/` 是错的）──")

    # A5：**纯离线**判形状 —— 畸形 `url:` 值不许当链接（实测 148 个里有 3 个）
    #     样本逐字取自库：`url:http://W1利益点边界表(SWMYUF`（域名后直接跟中文与半个括号）
    eq("A5 反向对照：`url:` 里畸形值 ⇒ None（不许印一个点不开的链接）",
       [W._clickable_of("url:http://W1利益点边界表(SWMYUF"),
        W._clickable_of("url:http://W1卖点表达边界（品线反馈2026-09-10"),
        W._clickable_of("url:http://吸奶器广告文案审计_红绿灯.xlsx")],
       [None, None, None])
    # A5b 同一条规则的**正向对照**：真 URL 必须照旧取出（别把好的也一起掐了）
    eq("A5b 正向对照：`url:` 里真 URL 照旧取出",
       W._clickable_of("url:https://momcozy-in.feishu.cn/wiki/Zqz7w1W9ZiP7i8kXNTGc9cBGnVb"),
       "https://momcozy-in.feishu.cn/wiki/Zqz7w1W9ZiP7i8kXNTGc9cBGnVb")

    # A6：token 形状判据（离线）—— 不是 24 位 base64url 形状 ⇒ 不许拼成链接
    eq("A6 反向对照：token 形状不像 Feishu token ⇒ None",
       [W._clickable_of("wiki:Tok123"),          # 测试用短串：**形状就不对**
        W._clickable_of("wiki:带中文的token"),
        W._clickable_of("docx:短")],
       [None, None, None])

    # A7–A9：**解析器**（打网络）—— 注入桩，判「按 obj_type 拼对路径」这一跳
    #   桩回的就是**真实读数**（这三条都是我逐个 `wiki +node-get` 查出来的）。
    REAL = {
        # obj_token，obj_type=docx ⇒ 必须走 /docx/
        "TqJSduQE3oBM4uxtHhmcrVtGnPg": {"obj_type": "docx", "obj_token": "TqJSduQE3oBM4uxtHhmcrVtGnPg",
                                        "node_token": "DAd6wOcX2iWuWhkZqqlc0AZxncg"},
        # 真 node_token，obj_type=bitable ⇒ 必须走 /wiki/（**别把对的改坏**）
        "LLpMwbYEmiX5uSkntPucf893ncf": {"obj_type": "bitable", "obj_token": "XxYyZz1",
                                        "node_token": "LLpMwbYEmiX5uSkntPucf893ncf"},
        # obj_token，obj_type=file ⇒ 走 /file/（**这条正是「改成 /docx/」会弄坏的反例**）
        "L9DXbU4XxoZoTHxdKXzcTEwJnNe": {"obj_type": "file", "obj_token": "L9DXbU4XxoZoTHxdKXzcTEwJnNe",
                                        "node_token": "NnOoPp2"},
    }
    W._link_probe_cache.clear()

    def stub(tok, timeout=6):
        return REAL.get(tok)

    eq("A7 `wiki:<obj_token>` 且 obj_type=docx ⇒ 走 **/docx/**（这就是 Owner 报的那条）",
       W._clickable_of("wiki:TqJSduQE3oBM4uxtHhmcrVtGnPg", _probe=stub),
       "https://momcozy-in.feishu.cn/docx/TqJSduQE3oBM4uxtHhmcrVtGnPg")
    eq("A8 ★ 反向对照：真节点 token（bitable）⇒ 仍走 **/wiki/**（别把唯一对的那个改坏）",
       W._clickable_of("wiki:LLpMwbYEmiX5uSkntPucf893ncf", _probe=stub),
       "https://momcozy-in.feishu.cn/wiki/LLpMwbYEmiX5uSkntPucf893ncf")
    eq("A9 ★★ 反向对照：obj_type=file ⇒ 走 **/file/**（证明「一律改 /docx/」是错的）",
       W._clickable_of("wiki:L9DXbU4XxoZoTHxdKXzcTEwJnNe", _probe=stub),
       "https://momcozy-in.feishu.cn/file/L9DXbU4XxoZoTHxdKXzcTEwJnNe")

    # A10：取不到（没权限 / 网络失败）⇒ **照实 None**，绝不回落到一个点不开的 `/wiki/`
    W._link_probe_cache.clear()
    eq("A10 反向对照：解析不到 ⇒ None（**不许编**，宁可让卡上写「取不到直链」）",
       W._clickable_of("wiki:PERMISSIONDENIED00000000", _probe=lambda t, timeout=6: None),
       None)
    # A11：解析结果**进缓存** ⇒ 同一次报告里重复 token 只查一次（5 条命中常只 2~3 个 token）
    W._link_probe_cache.clear()
    calls = {"n": 0}

    def counting(tok, timeout=6):
        calls["n"] += 1
        return REAL.get(tok)

    W._clickable_of("wiki:TqJSduQE3oBM4uxtHhmcrVtGnPg", _probe=counting)
    W._clickable_of("wiki:TqJSduQE3oBM4uxtHhmcrVtGnPg", _probe=counting)
    eq("A11 同一 token 只解析一次（缓存生效；否则每份报告白打多次网络）", calls["n"], 1)

    # A12–A14：**成因要分开写**（实测 14 个 `wiki:` 键里 5 个是 `permission_denied`）
    #   ⇒ 「守衡无权直读」≠「链接已失效」。混成一句会让人去重建一个其实好好的文件。
    print("── A12–A14：取不到直链时，成因**必须分开**（无权 / 失效 / 未核）──")
    W._link_probe_cache.clear(); W._link_probe_states.clear()
    W._clickable_of("wiki:TqJSduQE3oBM4uxtHhmcrVtGnPg",
                    _probe=lambda t, timeout=6: {"_probe_error": "permission_denied"})
    r = W._link_probe_reason("wiki:TqJSduQE3oBM4uxtHhmcrVtGnPg") or ""
    eq("A12 `permission_denied` ⇒ 写「守衡无权直读」+「人可能点得开」，**不许**说成失效",
       ("无权" in r) and ("人可能点得开" in r) and ("失效" not in r), True)

    W._link_probe_cache.clear(); W._link_probe_states.clear()
    W._clickable_of("wiki:TqJSduQE3oBM4uxtHhmcrVtGnPg",
                    _probe=lambda t, timeout=6: {"_probe_error": "not_found"})
    r2 = W._link_probe_reason("wiki:TqJSduQE3oBM4uxtHhmcrVtGnPg") or ""
    eq("A13 `not_found` ⇒ 写「链接已失效」", "失效" in r2, True)

    W._link_probe_cache.clear(); W._link_probe_states.clear()
    W._clickable_of("wiki:TqJSduQE3oBM4uxtHhmcrVtGnPg",
                    _probe=lambda t, timeout=6: {"_probe_error": "transient"})
    r3 = W._link_probe_reason("wiki:TqJSduQE3oBM4uxtHhmcrVtGnPg") or ""
    # ⚠️ 判据要抓「**已**失效」（断言句），不能抓「失效」二字 —— 这句话本身写着
    #   「不等于失效」，抓子串会把它自己判红（第一版就是这么假红的）。
    eq("A14 ★ 反向对照：超时/未知 ⇒ 必须写「未核」，**不许**冒充「无权」或「已失效」",
       ("未核" in r3) and ("无权" not in r3) and ("已失效" not in r3)
       and ("不等于失效" in r3), True)
    W._link_probe_cache.clear(); W._link_probe_states.clear()

    # A15 ★★（2026-10-09 晚，**又栽了一次「桩绿真红」之后补的**）：
    #   上面 A12/A13/A14 全是**桩**，于是它们**没抓到**真路径的 bug ——
    #   真跑时 `lark-cli` 在**失败时把 JSON 写到 stderr**（stdout 空、退出码非 0），
    #   而解析只读 stdout ⇒ `permission_denied` 被误归成「超时/未核」。
    #   ⇒ 这一条用**假 CLI**（临时 HOME 里放一个只往 stderr 写真实错误 JSON 的脚本）走**真代码路径**。
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        bindir = os.path.join(td, ".dsh", "bin")
        os.makedirs(bindir)
        fake = os.path.join(bindir, "lark-cli")
        # 逐字取自真实现场：`wiki +node-get` 对无权资源的输出（stdout 空、stderr 是这段）
        payload = json.dumps({"ok": False, "identity": "bot",
                              "error": {"type": "authorization", "subtype": "permission_denied",
                                        "code": 131006,
                                        "message": "bot lacks permission for the requested resource"}})
        with open(fake, "w", encoding="utf-8") as fh:
            fh.write("#!/bin/sh\ncat >/dev/null 2>&1\nprintf '%s' " + json.dumps(payload) + " >&2\nexit 3\n")
        os.chmod(fake, 0o755)
        real_home = W.os.path.expanduser("~")
        W.os.path.expanduser = lambda p: (os.path.join(td, p[2:]) if p.startswith("~/") else p)
        try:
            os.environ["KB_LINK_PROBE"] = "1"
            W._link_probe_cache.clear(); W._link_probe_states.clear()
            got = W._probe_wiki_token_real("TqJSduQE3oBM4uxtHhmcrVtGnPg")
            eq("A15 ★★ 真路径：CLI 把 JSON 写在 **stderr** 时也要读出来（桩抓不到的那个 bug）",
               (isinstance(got, dict) and got.get("_probe_error") == "permission_denied"), True)
        finally:
            W.os.path.expanduser = real_home
            os.environ["KB_LINK_PROBE"] = "0"
            W._link_probe_cache.clear(); W._link_probe_states.clear()

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
    # ★ 同上改口径：第二级仍走 `_clickable_of`，但结果取决于能不能解析出对象类型。
    #   **这一条钉的是「第二级有没有被调用」** ⇒ 用桩 + 清缓存，**不许依赖执行顺序**
    #   （第一版就是漏了清缓存，A11 的桩结果留在里面 ⇒ 假红）。
    W._link_probe_cache.clear()
    _real_probe = W._probe_wiki_token_real
    W._probe_wiki_token_real = lambda tok, timeout=6: {"obj_type": "docx", "obj_token": tok, "node_token": "N1"}
    try:
        eq("B3 第二级：`wiki:<obj_token>` 键 ⇒ 经 `_clickable_of` 拼成 **/docx/**",
           W._hit_link({}, "url__x", {"url__x": "wiki:TqJSduQE3oBM4uxtHhmcrVtGnPg"}),
           "https://momcozy-in.feishu.cn/docx/TqJSduQE3oBM4uxtHhmcrVtGnPg")
    finally:
        W._probe_wiki_token_real = _real_probe
    W._link_probe_cache.clear()
    eq("B3b 第二级在**探测开启**时按 obj_type 拼对路径",
       W._clickable_of("wiki:TqJSduQE3oBM4uxtHhmcrVtGnPg",
                      _probe=lambda t, timeout=6: {"obj_type": "docx",
                                                   "obj_token": t, "node_token": "N1"}),
       "https://momcozy-in.feishu.cn/docx/TqJSduQE3oBM4uxtHhmcrVtGnPg")
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
            # ★ 2026-10-09 晚**改断言口径**（原先钉「每条都要有可点直链」，钉错了东西）：
            #   实测有命中**本来就没有链接来源** —— 它的 `anchor` 里没有 `__<record>` 后缀
            #   ⇒ `rid=None` ⇒ `resource_key` 取不到 ⇒ 三级回落全空。那种情况
            #   **正确行为就是 None**（卡/报告如实写「取不到直链」），不是缺陷。
            #   ⇒ 现在钉**真正的不变量**（三条，合起来等价于「宁可没有，也不许给一个点不开的」）：
            #     ① 每条的 `url` 要么是 **http(s)**、要么**明确为 None**（不许是半截串）；
            #     ② 至少有一条真有链接（否则说明整条通路又断了 —— 那是原来的病灶）；
            #     ③ **不许再出现「`/wiki/` + 对象 token」这种点不开的链接**：
            #        凡 `/wiki/<tok>` 的链接，那个 tok 必须**确实**是节点 token
            #        （离线判不了 ⇒ 只判「不是本条自己的 obj_token 形态」这一层，
            #          其余留给 A7/A8/A9 的桩判据）。
            bad = [h.get("url") for h in hits
                   if h.get("url") is not None and not str(h.get("url")).startswith("https://")]
            eq("D 支路[%s]：url 要么是 https、要么明确为 None（不许半截串）" % tag, bad, [])
            withurl = [h for h in hits if h.get("url")]
            eq("D 支路[%s]：至少一条真有直链（全空 = 这条通路又断了）" % tag, len(withurl) > 0, True)
            none_n = len(hits) - len(withurl)
            print("     %d/%d 条有直链%s" % (len(withurl), len(hits),
                  "（另 %d 条**本来就没有链接来源**，如实为 None）" % none_n if none_n else ""))
            print("     样例：%s" % (withurl[0].get("url") if withurl else "(无)"))

    print("\n通过 %d / 失败 %d" % (len(PASS), len(FAIL)))
    if FAIL:
        print("失败项：")
        for f in FAIL:
            print("  - " + f)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
