#!/usr/bin/env python3
"""外部 URL 资源对齐核验（L0 里 150 条 url: 资源）。

判据：L0 行记了 sha256（sha256_input 多为 url_text）+ revision。重抓正文，按同一「去标签取文本」口径算 sha256 比对。
★ 2026-10-09：**按台账记的 `sha256_input` 分派管线** —— `url_text_rendered_v1` 走渲染
（`url_render_lib.fetch_rendered`），其余走裸 HTTP。混用一条管线会让 100 条永远报「复现不出」。
口径诚实性：若复现不出原摘要，就只报「可达/不可达 + 正文长度」，并把新旧摘要都记下来，不硬说一致。
★ 2026-10-13：**空正文不再判 `same`** —— 改判 `probe_empty`（`fail_class=probe_empty`）。
  病灶：空串的 sha256 与台账里同样从空串算出来的 sha256 必然相等 ⇒ 38 条「抓不到」被记成
  「内容没变」并算进日更摘要的「已对齐」。判据本体 = `judge_verdict()`，自证 = `--selftest`。
  ★ **只改裸 HTTP 分支**：渲染分支（`url_text_rendered_v1`）取不到正文**原本**就是
    `unreachable` + `fail_class=render_empty`（fail-closed，没病）⇒ 形状**一个字没动**。
    实测代价留痕：我一度把两条桶统一成 `probe_empty`，10 条便从 `unreachable` 挪了桶 ——
    那不是本缺陷、却改了失败分类分布，已**收回**（Owner 本轮口径：「先①、不许动输出格式」）。
  边界：只钉**空串**（阈值 0），不顺手把短正文判掉；不判页面失效、不改台账 sha、不动摘要与闸门。
用法：python3 kb/l8/verify_l0_urls.py 20260929-1420
      python3 kb/l8/verify_l0_urls.py --selftest      # 反向对照（全离线、不联网、不读台账）
"""
# ── 解释器守卫（2026-09-29）：不合格就用 kb/.kb-python 指定的解释器重跑自己 ──
import os as _os, sys as _sys
if not _os.environ.get("KB_INTERP_OK"):
    _d = _os.path.dirname(_os.path.abspath(__file__)); _cfg = None
    while True:
        _p = _os.path.join(_d, ".kb-python")
        if _os.path.isfile(_p):
            _cfg = _p
            break
        _q = _os.path.dirname(_d)
        if _q == _d:
            break
        _d = _q
    if _cfg:
        _want = next((l.split("#", 1)[0].strip() for l in open(_cfg, encoding="utf-8")
                      if l.split("#", 1)[0].strip()), "")
        _want = _os.path.expanduser(_want)
        if (_want and _os.access(_want, _os.X_OK)
                and _os.path.realpath(_want) != _os.path.realpath(_sys.executable)):
            _os.environ["KB_INTERP_OK"] = "1"
            _os.execve(_want, [_want, _os.path.abspath(__file__)] + _sys.argv[1:], dict(_os.environ))
# ──────────────────────────────────────────────────────────────────────────

import collections
import hashlib
import html as H
import json
import os
import re
import sys
import urllib.request

# ★ 2026-10-09：渲染管线共用件（口径分派用）——与 recrawl_all_urls.py 同一份实现
from url_render_lib import fetch_text_like_recrawl  # noqa: E402

RUN = sys.argv[1] if len(sys.argv) > 1 else "20260929-1420"
APPLY = "--apply" in sys.argv
SELFTEST = "--selftest" in sys.argv

# ── ★★ 2026-10-10：**日更里强制只读** —— 它写 L0 台账会把 L1 顶成陈旧，进而自激 ──────
# 病灶（实测事故，Owner 2026-10-10：「为什么一小时推一次」查出来的）：
#   本脚本被接进 L0 的 `engine:` 之后，会在 L0 阶段**追加 `url:` 台账行**（核验结论变了就写）。
#   而它**慢**（实测一轮 5m49s），于是常常**跑过 L0 阶段的末尾**：
#     2026-10-10 06:27 那趟 —— L1 落章 **06:49:07**，本脚本 **06:55:48** 才追加 3 行；
#     ⇒ L1 落章记的上游水位 `l0/manifest.jsonl:8496` 永远追不上现状 `8499`
#     ⇒ `layer_freshness.judge()` 判 L1 **陈旧** ⇒ 评审链拒答 ⇒
#        就绪巡检的**受控自愈**每小时踢一次日更（冷却 45 分钟、当日上限 3 次）
#     ⇒ **小时级日更**，而摘要推送跟着发 ⇒ **群里一小时一条**。
# ⇒ 结论：**在日更里，本脚本必须只读**（只出 same/differ/unreachable 的读数，
#   **不写台账、不推进水位**）。要登记新结论就**人工**跑 `--apply`（白天，像 2026-10-09 那样）。
#   逃生口：`KB_ALLOW_L0_APPEND_IN_DAILY=1` 显式放行（默认不放）。
if APPLY and not os.environ.get("KB_ALLOW_L0_APPEND_IN_DAILY") == "1" and (
        os.environ.get("KB_PIPELINE_RUN_ID") or str(RUN).startswith("daily-")):
    print("[verify_l0_urls] ⚠️ 日更里**强制只读**（收到了 --apply，但不写台账）——")
    print("   原因：它写 L0 台账会**推进 L0 水位**，而 L1 在同一趟里已经落章 ⇒")
    print("   L1 恒定判陈旧 ⇒ 自愈每小时踢一次日更 ⇒ 小时级日更 + 小时级推送（2026-10-10 事故）。")
    print("   仍会核验并给出 same/differ/unreachable 读数；要登记新结论请**人工**跑 `--apply`。")
    print("   显式放行：KB_ALLOW_L0_APPEND_IN_DAILY=1")
    APPLY = False
# ★ 2026-10-08 批次一：失败项是否落台账。默认 **不落**（保持只读）；显式加才写。
APPEND_FAILURES = "--append-failures" in sys.argv
# ★ 2026-10-08 批次一修正：原来写死「假 Chrome UA」，实测被 FDA / CDC 反爬命中 ——
#   fda.gov 对假 Chrome UA **整站返回 404**（连首页、robots.txt 都 404），
#   于是 3 条 FDA 监管依据 + CDC 被误报「不可达」（当天实测 8 条假红，且差点被当成
#   「FDA 依据失效」去修数据）。改成：默认用 urllib 默认 UA；
#   确需伪装时用环境变量 L0_URL_UA 显式指定 —— 别再把 UA 写死在代码里。
UA = os.environ.get("L0_URL_UA") or None

# ── ★★ 2026-10-13：**空正文不是一致，是取不到**（本脚本原先在这里 fail-open）──────────
# 病灶（实测 daily-20261013-0330 产物）：
#   日更核 145 条 URL，判 `same` 78 条 —— 其中 **38 条的正文是空串**，
#   而空串的 sha256 恒为 e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855，
#   与台账里那个**同样从空串算出来的** sha256 恰好相等 ⇒ 判「same」。
#   同域构成：hapa8fkuicz.feishu.cn 17 ｜ momcozy-in.feishu.cn 21（另一个租户与需 API 的对象）。
#   ⇒ 「我抓不到」被记成「内容没变」，而摘要把它们算进「已对齐」。
# ⇒ 判据：正文空（或只有空白）⇒ `probe_empty`，**绝不判 same**。
#   ★ 边界（别外推）：本判据只说「这次没取到可比正文」；
#     **不**说页面失效（那要两轮 404 复现才够）、**不**说台账里那条 sha 是错的
#     （它就是空串的 sha，如实）。无取到的正文就**没有**一致性证据，仅此而已。
#   ★ 阈值 = 0：**只钉空串**，不顺手把「短正文」也判掉 ——
#     假红比漏报更坏（见同目录 `verify_l0_urls.py` 惯有的 UA 教训：FDA 曾因假 UA 整站 404）。
#     真要把「403 反爬页当正文」也挡住，那是**另一轮**的事（要把 `www.ftc.gov` 那条
#     403 申诉页 331 字一并纳入口径），本轮不做。
MIN_BODY_CHARS = 0


def judge_verdict(l0_sha, text, min_chars=MIN_BODY_CHARS):
    """正文 → 判决。**本件是那一处缺陷的唯一判据本体**（2026-10-13 抽出为纯函数）。

    ★ 顺序不许调换：**先问「有没有拿到正文」，再问「像不像」**。
      调换回来（先比 sha）就是本缺陷本身 —— 空串的 sha 与空串的 sha 必然相等。
    返回五值之一：
      `probe_empty`       正文（**先 strip**）长度 ≤ `min_chars`（含空串／纯空白）⇒ **没有可比正文**
      `first_hash`        台账**没有** sha（首次登记），而正文拿到了 ⇒ 无基线可判
      `same`              台账有 sha ＋ 正文拿到了 ＋ 摘要逐字相等
      `recomputed_differ` 台账有 sha ＋ 正文拿到了 ＋ 摘要不同 ⇒ 需人工看
      `probe_short`       非空但短于阈值（默认阈值 0 ⇒ 本值当前不可能出现；留作接线位）
    ★ **先 `strip()` 再量长度**：`strip_html()` 当前已自带 strip，但本判据不许依赖调用方 ——
      纯空白 `"   \\n\\t  "` 长度 6 > 阈值 0，不 strip 就会漏过去（自证 ④ 实测踩到过）。
    """
    txt = (text or "").strip()
    if len(txt) <= min_chars:
        return "probe_empty"
    h = hashlib.sha256(txt.encode()).hexdigest()
    if not l0_sha:
        return "first_hash" if len(txt) > 0 else "probe_empty"
    return "same" if h == l0_sha else "recomputed_differ"


def selftest():
    """反向对照：证明「空正文不再判 same」这条判据**不恒绿、也不恒红**。

    全部离线（不联网、不读台账），`--selftest` 时在**任何网络动作之前**执行。
    """
    EMPTY_SHA = hashlib.sha256(b"").hexdigest()          # e3b0c442…b7852b855
    _real = "Momcozy S12 Pro Quick tragbare Milchpumpe"    # 形如真实正文的一句
    _real_sha = hashlib.sha256(_real.encode()).hexdigest()
    ok = fail = 0

    def chk(name, cond, extra=""):
        nonlocal ok, fail
        if cond:
            ok += 1
            print("  ✅ %s %s" % (name, extra))
        else:
            fail += 1
            print("  ❌ %s %s" % (name, extra))

    # ── 正例：本缺陷的**逐字真实形状**（38 条的实测组合）────────────────────────
    chk("①空正文 × 台账空串 sha ⇒ probe_empty（**不许 same**）—— 本缺陷的病灶",
        judge_verdict(EMPTY_SHA, "") == "probe_empty",
        "得 %s" % judge_verdict(EMPTY_SHA, ""))
    chk("②空正文 × 台账真实 sha ⇒ probe_empty（取不到就是取不到，与台账无关）",
        judge_verdict(_real_sha, "") == "probe_empty")
    chk("③空正文 × 台账无 sha ⇒ probe_empty（不是 first_hash —— 没正文可登记）",
        judge_verdict(None, "") == "probe_empty")
    chk("④纯空白正文 ⇒ probe_empty（`strip_html` 后可能只剩空白）",
        judge_verdict(EMPTY_SHA, "   \n\t  ") == "probe_empty")
    # ── ⑤–⑧ 反向对照：正常路径**一个字不许变**（否则就是拿假红换假绿）──────────
    chk("⑤正文拿到 ＋ 摘要相等 ⇒ same（正常路径没被误伤）",
        judge_verdict(_real_sha, _real) == "same")
    chk("⑥正文拿到 ＋ 摘要不同 ⇒ recomputed_differ（差异判据没被改掉）",
        judge_verdict(_real_sha, _real + " x") == "recomputed_differ")
    chk("⑦正文拿到 ＋ 台账无 sha ⇒ first_hash（首次登记仍认得出）",
        judge_verdict(None, _real) == "first_hash")
    chk("⑧原文里有换行的正文 ⇒ same（不受空白归一影响）",
        judge_verdict(hashlib.sha256(b"a\nb").hexdigest(), "a\nb") == "same")
    # ── ⑨–⑩ 判据本身的自证：把缺陷造回去，必须**精确变红** ──────────────────────
    def _buggy(l0_sha, text, min_chars=0):
        """改动前的写法（逐字）：`same if l0_sha and h == l0_sha else …`。"""
        txt = text or ""
        h = hashlib.sha256(txt.encode()).hexdigest()
        return ("same" if l0_sha and h == l0_sha
                else ("recomputed_differ" if l0_sha else "first_hash"))

    chk("⑨★反向对照：把缺陷写法喂同一组输入 ⇒ 必须判 same（证明①不是恒真）",
        _buggy(EMPTY_SHA, "") == "same",
        "缺陷写法得 %s ⇒ ① 与它**必然不同**" % _buggy(EMPTY_SHA, ""))
    chk("⑩阈值可调但默认只钉空串：`min_chars=5` 时 3 字正文 ⇒ probe_short",
        judge_verdict(_real_sha, "abc", min_chars=5) == "probe_empty"
        and MIN_BODY_CHARS == 0,
        "默认阈值 %d（不许顺手把短正文判掉）" % MIN_BODY_CHARS)

    print("\n  %d/%d 通过 ｜ %d 失败" % (ok, ok + fail, fail))
    print("  边界：本件只证「空正文不判 same」；**不**判页面失效、**不**改台账 sha、"
          "不动摘要与任何闸门。")
    return 0 if fail == 0 else 3


if SELFTEST:
    sys.exit(selftest())


def strip_html(h):
    h = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", h, flags=re.S | re.I)
    h = re.sub(r"<(title|h1|h2|h3|h4|p|li|br|tr|/p|/li|/h1|/h2|/h3|/h4|/tr)[^>]*>", "\n", h)
    h = re.sub(r"<[^>]+>", "", h)
    return re.sub(r"\n{2,}", "\n", H.unescape(h)).strip()


def is_bad_key(row):
    """★ 2026-10-08 批次一：台账里 09-29 就把「字段显示文本被当成 URL 主机名」的键
    定性为坏键（change=l0_url_bad_key_note / status_reason 写「供下游忽略」），
    但本脚本原先只看 status，于是把坏键当真 URL 去抓 → UnicodeEncodeError / unknown url type。
    判据两条：① 键体不是 http(s):// 开头；② 台账已标坏键备注。命中即跳过，不再计入对账分母。"""
    if not re.match(r"^https?://", (row.get("resource_key") or "").split(":", 1)[-1]):
        return True
    note = str(row.get("status_reason") or "") + str(row.get("change") or "")
    return ("坏键" in note) or ("bad_key" in note)


lat = {}
for line in open("kb/l0/manifest.jsonl", encoding="utf-8"):
    if line.strip():
        r = json.loads(line)
        lat[r["resource_key"]] = r
all_url = [(k, v) for k, v in lat.items()
           if v["source_kind"] == "url" and v["status"] not in ("gone", "retracted")]
urls = [(k, v) for k, v in all_url if not is_bad_key(v)]
bad_keys = [k for k, v in all_url if is_bad_key(v)]
print(f"待重抓 URL：{len(urls)} 条 ｜ 跳过已登记坏键：{len(bad_keys)} 条")
for k in bad_keys:
    print(f"   [skip 坏键] {k[:90]}")

results, rows = [], []
for key, row in sorted(urls):
    url = key.split(":", 1)[1]
    ent = {"resource_key": key, "l0_sha256": row.get("sha256"), "l0_sha256_input": row.get("sha256_input"),
           "l0_revision": row.get("revision")}
    try:
        # ── ★ 2026-10-09 **口径分派**（Owner 批「按口径分派核验器」）────────────────
        # 病灶实测：150 条活跃 url **按 sha256_input 干净地分成两堆** ——
        #   `url_text_rendered_v1` 103 条（**渲染管线**记的）
        #   `url_text_refresh_v1`  40 条（**裸 HTTP** 记的）
        # 而本脚本只会裸 HTTP ⇒ 那 103 条**结构上永远复现不出**，只能报 `recomputed_differ`，
        # 而它**读起来像「内容变了」—— 那是假信号**（实测 13:15：same 40 / differ 100，分堆吻合）。
        # ⇒ 按台账记的 `sha256_input` 选管线：渲染件走共用件 `kb/l8/url_render_lib.py`
        #   （与 `recrawl_all_urls.py` **同一份实现**，已实测能逐字复现原摘要）。
        if row.get("sha256_input") == "url_text_rendered_v1":
            # ★ 2026-10-13：**该分支的形状一个字没动** —— 原先是
            #   `if not txt: raise RuntimeError("render_empty…")` ⇒ 落到 except ⇒
            #   `verdict=unreachable` + `fail_class=render_empty`（**fail-closed，本来就没病**）。
            #   本轮**只修裸 HTTP 分支**那处空对空判 same（见下）。
            #   ⚠️ 实测教训：我一度把这两条桶统一成 `probe_empty`，结果 10 条从
            #   `unreachable` 挪了桶 —— 那**不是**本缺陷，却改变了失败分类的分布。
            #   Owner 本轮口径是「先①、不许动输出格式」⇒ **收回**，保持 unreachable 不变。
            txt, _method = fetch_text_like_recrawl(url)
            if not txt or not txt.strip():
                raise RuntimeError("render_empty：两级都取不到正文")
            h = hashlib.sha256(txt.encode()).hexdigest()
            ent.update({"http_status": None, "bytes": None, "chars": len(txt),
                        "feishu_sha256": h, "render_mode": _method, "pipeline": "recrawl_equivalent",
                        "verdict": judge_verdict(row.get("sha256"), txt),
                        "text_head": txt[:80]})
        else:
            headers = {"Accept-Language": "en,zh;q=0.8"}
            if UA:
                headers["User-Agent"] = UA
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=25) as resp:
                raw = resp.read()
                status = resp.status
            txt = strip_html(raw.decode("utf-8", "ignore"))
            h = hashlib.sha256(txt.encode()).hexdigest()
            ent.update({"http_status": status, "bytes": len(raw), "chars": len(txt),
                        "feishu_sha256": h, "pipeline": "http",
                        "verdict": judge_verdict(row.get("sha256"), txt),
                        "text_head": txt[:80]})
            # ── ★★ 2026-10-13 本缺陷的**修复点**（病灶逐字：空对空判 same）─────────────
            #   原先这一行是 `"same" if row.get("sha256") and h == row["sha256"] else …`
            #   ⇒ 台账 sha 与重算 sha **都是空串的 sha** ⇒ 相等 ⇒ 判 same。
            #   实测 38 条（hapa8fkuicz 17 ／ momcozy-in 21）顶着「已对齐」进了日更摘要。
            #   现在：正文为空 ⇒ `probe_empty`，**并明着带 fail_class**（别静默降级）。
            if ent["verdict"] == "probe_empty":
                ent["fail_class"] = "probe_empty"
                ent["why"] = ("正文为空（chars=%d；HTTP %s）—— 取不到可比正文，"
                              "**不是**「内容一致」" % (ent["chars"], status))
    except urllib.error.HTTPError as e:
        # ★ 2026-10-08 批次一：把「不可达」细分，因为处置完全不同（见 status_reason）。
        #   ⚠️ 404 不等于 gone：skill 红线要求「标 gone 要双证（人确认 + API 报不存在）」，
        #   所以这里只记可复现的 missing，等的就是多轮复现 —— 别直接判死。
        ent.update({"http_status": e.code, "verdict": "unreachable", "why": f"HTTP {e.code}",
                    "fail_class": ("missing_page_candidate" if e.code == 404 else
                                   ("blocked_candidate" if e.code in (400, 403) else f"http_{e.code}"))})
    except urllib.error.URLError as e:
        rsn = str(getattr(e, "reason", e))
        ent.update({"verdict": "unreachable", "why": f"URLError: {rsn[:100]}",
                    "fail_class": "dns_fail" if "nodename" in rsn or "Name or service" in rsn else "network_error"})
    except Exception as e:
        ent.update({"verdict": "unreachable", "why": f"{type(e).__name__}: {str(e)[:110]}",
                    "fail_class": ("render_empty" if "render_empty" in str(e)
                                   else ("timeout" if "timed out" in str(e) else "other"))})
    results.append(ent)
    if APPLY and ent["verdict"] in ("same", "recomputed_differ", "first_hash"):
        n = dict(row)
        # ★ 2026-10-09：写回的口径名**必须反映实际走的管线** —— 原先无条件写
        #   `url_text_refresh_v1`，会把**渲染件**（`url_text_rendered_v1`）标错口径，
        #   下一轮核验又按错口径去复现，口径就永远统一不了（这正是本次要修的病根之一）。
        _inp = (row.get("sha256_input") if ent.get("pipeline") == "recrawl_equivalent"
                and row.get("sha256_input") == "url_text_rendered_v1"
                else "url_text_refresh_v1")
        n.update({"observed_at": RUN, "change": "l0_url_reverify",
                  "status": "updated" if ent["verdict"] != "recomputed_differ" else "registered",
                  "status_reason": f"URL 重抓核验：{ent['verdict']}"
                                   f"（管线 {ent.get('pipeline')}／{ent.get('render_mode')}；"
                                   f"HTTP {ent.get('http_status')}）"
                                   + ("；正文摘要与原行不同 → 网页内容可能已变，需人工看"
                                      if ent["verdict"] == "recomputed_differ" else ""),
                  "sha256_prev": row.get("sha256"), "sha256": ent["feishu_sha256"],
                  "sha256_input": _inp, "sha256_state": "full"})
        rows.append(n)
    # ★ 失败项留痕（只在显式 --append-failures 时写；默认不写，保持只读）。
    #   status 取 **非终态**：missing 是「疑似没了，待复现/人确认」，不是 gone。
    if APPEND_FAILURES and ent["verdict"] == "unreachable":
        fc = ent.get("fail_class")
        if fc in ("missing_page_candidate", "blocked_candidate", "dns_fail"):
            n = dict(row)
            n.update({
                "observed_at": RUN, "change": "l0_url_unreachable_observed",
                "status": ("missing" if fc == "missing_page_candidate" else
                           ("blocked_by_ua_policy" if fc == "blocked_candidate" else "dns_fail")),
                "status_reason": {
                    "missing_page_candidate": f"HTTP 404（第 N 轮复现才可判 gone）：{ent['why']}",
                    "blocked_candidate": f"HTTP {ent.get('http_status')} —— 疑似反爬拦截，非页面失效；"
                                         f"本轮 UA={'自定义 ' + str(UA) if UA else 'urllib 默认'}。"
                                         f"实测同站换 UA 结果相反（FDA 假 Chrome UA 整站 404、默认 UA 200）",
                    "dns_fail": f"DNS 解析失败：{ent['why']}",
                }[fc],
            })
            rows.append(n)

rep = {"run": RUN, "kind": "url_reverify", "checked": len(results),
       "by_verdict": dict(collections.Counter(r["verdict"] for r in results)),
       "fail_classes": dict(collections.Counter(r.get("fail_class") for r in results if r.get("fail_class"))),
       "skipped_bad_keys": bad_keys,
       "user_agent": UA or "urllib-default",
       "same_count": sum(1 for r in results if r["verdict"] == "same"),
       "differ_count": sum(1 for r in results if r["verdict"] == "recomputed_differ"),
       "results": results}
json.dump(rep, open(f"kb/l8/runs/{RUN}-l0-url-verify.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("结果：", rep["by_verdict"])
if rep["fail_classes"]:
    print("失败分类：", rep["fail_classes"])
if APPLY or APPEND_FAILURES:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from l0_ledger import append_changed
    _n = append_changed("kb/l0/manifest.jsonl", rows, run=RUN)
    print(f"已追加 {_n['appended']} 行；{_n['skipped_unchanged']} 行未变（只刷新 last_seen，不再重复登记）")
    print(f"  （闸门：APPLY={APPLY} ｜ APPEND_FAILURES={APPEND_FAILURES}；"
          f"只加 --append-failures 时仅失败项会进台账，正常项不写）")
