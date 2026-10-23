#!/usr/bin/env python3
"""daily_digest.py —— **日更摘要**：出一份可核的日报，并推给守衡（飞书私聊）。

## 为什么要有它（2026-10-09 Owner 裁定「推荐 A」）

实测：**日更完什么都不推**。四个相关文件（`daily_via_skill.sh` / `daily_via_skill.md` /
`daily_health.py` / `l0_daily_sync.py`）里**零发送动作**；`daily_health.py:37` 自己写着
「**要接告警请读 `daily-health-latest.json` 的 `health` 字段**」—— 接告警这件事留给了别人，
而从来没人接。全库唯一的推送方是就绪巡检（`watch_review_readiness.py`），它推的是
「守衡**能不能用**」（认领/凭据/新鲜度/令牌寿命/漂移），**一条数据变更都不含**。

⇒ 本脚本补的正是那一条：**"这一轮日更做了什么、库现在什么样"**。

## 口径（**不自创**）

分类与四态一律照 `kb-l0-feishu` 的 `references/coverage-matrix.md`：
- **12 类资源**（该文件 §一 的表），四态 = `已对齐` ｜ `不适用（附证据）` ｜
  `读不到（原因码）` ｜ `不可核（原因码）`；
- 该文件 §三 **硬性要求**：「报告末尾必须打印这张矩阵：每类一行 = 类型 + 状态 + 条数 + 原因码」。

**两个数分开报，不许混**（这是本脚本的核心设计）：
- **库内**：台账/产物**现在**什么样 —— 走 `kb/l8/l0_ledger.py::latest_by_key()`（同一把尺子）。
- **本轮**：这一次日更**动没动**这一类 —— 判据是该类的脚本在不在日更的 engine 清单里
  （`layers.yaml` 各层 `engine:`，运行时读，不抄第二份）＋ 本轮有没有产物。

**「本轮没跑」落哪个态**：`不可核（stage_not_in_daily_engine_list）`。
不新造第五个态 —— 矩阵原文写着「任何一类都不允许静默跳过，必须落在四种状态之一」。

## 用法

    python3 kb/l8/daily_digest.py <BASE>              # 只出 md（**默认不推**）
    python3 kb/l8/daily_digest.py <BASE> --push       # 出 md 并推飞书
    python3 kb/l8/daily_digest.py <BASE> --push --chat oc_xxx
    python3 kb/l8/daily_digest.py <BASE> --print-push # 只读：打印**真要发出去**的那份正文（不写 md、不推）
    python3 kb/l8/daily_digest.py --selftest
"""
import argparse
import datetime
import glob
import io
import json
import os
import re
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(ROOT)
sys.path.insert(0, os.path.join("kb", "l8"))
sys.path.insert(0, os.path.join("kb", "l7", "scripts"))

# ★ 2026-10-16：出站正文的 markdown 星号收口（KB 侧唯一实现 —— 与守衡 `plain.mjs` 逐字互校）。
#   必须在上面两行 `sys.path` 之后导入；它摘的是**推给飞书的那份正文**，不是本文件的 md。
from plaintext import guard, has_md_symbols, plainify, plainify_for_send  # noqa: E402

LARK = os.path.expanduser("~/.dsh/bin/lark-cli")
#: 落点（Owner 2026-10-09 两次口径，以后者为准）：
#:   · 第一次：「推送给守衡，推送到私聊给我」→ p2p `oc_7775e2dacb6f2ebc9789cd6e681de5f7`
#:   · 第二次：「重新发送日更到群里『内容治理-守衡Agent-测试』」→ **日更摘要改推群**
#:     （`lark-cli im +chat-search --query 内容治理-守衡Agent-测试` 实测查到，bot 是成员）
#: ⇒ **默认推群**；要私聊副本就设 `KB_DIGEST_CHAT=<p2p id>` 或 `--chat <id>`。
#:   ⚠️ 就绪巡检（`watch_review_readiness.py`）**不动** —— 它的运维告警仍走私聊 P2P_ID。
DEFAULT_CHAT = "oc_49a7cfb2861cffa4365ca8491f398d32"   # 群：内容治理-守衡Agent-测试
P2P_CHAT = "oc_7775e2dacb6f2ebc9789cd6e681de5f7"       # 私聊（就绪巡检的落点）
PROFILE = "dsh-kb"

#: 12 类 → 台账口径 / 覆盖它的脚本（脚本名用于判「在不在日更 engine 清单里」）
#: 口径来源：`kb/l7/skills/kb-l0-feishu/references/coverage-matrix.md` §一（逐行照抄编号与名称）
CLASSES = [
    (1, "表格记录·文本字段", "feishu_bitable_record",
     # ★ 2026-10-10：`ingest_l0_new_records.py` 换成 `reconcile_l0_feishu.py` ——
     #   前者是 2026-09-30 那代的旧脚本、**不在任何 engine 清单里**；「认领新记录」
     #   这件事现在是 `reconcile_l0_feishu.py` 第 4 步在做（实测 `claim_new` 170 文件 →
     #   `kb/l0/records/负面样本`，`verdict=PASS`）。留旧名会让类① 在真引擎仍在跑时误报「不可核」。
     ["align_l0_feishu.py", "reconcile_l0_feishu.py"], "records"),
    (2, "表格字段结构", None,
     ["align_l0_schema.py"], "schema"),
    (3, "图片附件", "feishu_attachment",
     ["store_l0_attachments.py", "ocr_attachments.py", "apply_ocr_to_l1.py"], "ledger"),
    (4, "视频素材", "VIDEO",
     ["fetch_video_bytes.py", "extract_video_keyframes.py", "extract_video_asr.mjs"], "video"),
    # ★ 2026-10-09 修：这五类的台账行是 `verify_l0_nonrecord2.py`（与 `verify_l0_nonrecord.py`）
    #   写的（实测 `source_kind=feishu_file/slides/sheet/doc/bitable_*` 的写入方就是它）
    #   —— 原先 scripts=[] 是**填漏**，会把这五类误报成"没有脚本覆盖"。
    (5, "云空间文件（pdf/ppt/xlsx/docx/其他）", "feishu_file",
     ["verify_l0_nonrecord2.py", "verify_l0_nonrecord.py", "refresh_l0_drifted.py"], "ledger"),
    (6, "幻灯片 slides", "feishu_slides",
     ["verify_l0_nonrecord2.py", "verify_l0_nonrecord.py", "refresh_l0_drifted.py"], "ledger"),
    (7, "电子表格 sheets", "feishu_sheet",
     ["verify_l0_nonrecord2.py", "verify_l0_nonrecord.py", "refresh_l0_drifted.py"], "ledger"),
    (8, "文档 docx", "feishu_doc",
     ["verify_l0_nonrecord2.py", "verify_l0_nonrecord.py", "refresh_l0_drifted.py"], "ledger"),
    (9, "base / table / wiki 节点", "feishu_bitable",
     ["verify_l0_nonrecord2.py", "verify_l0_nonrecord.py"], "ledger"),
    (10, "记录里的内嵌链接（下钻两层）", "url", ["drill_links_2levels.py", "fill_drill_failures.py"], "ledger"),
    # ★ ⑪ 是 ⑩ 里**飞书域外**那一部分（coverage-matrix 原文：「URL 字段里指向飞书域外的地址」）
    #   ⇒ 它是 ⑩ 的**子集**，两行**不许相加**；台账只有 `source_kind=url` 一种，靠域名实时分。
    (11, "外部网页链接", "url_external", ["verify_l0_urls.py", "recrawl_all_urls.py"], "ledger"),
    (12, "其它附件 / 未知类型", "UNKNOWN", [], "ledger"),
]

#: Owner 点名的五类 → 12 类里的哪几行
FIVE = [
    ("文案", [1]),
    ("图片", [3]),
    ("视频", [4]),
    ("文档", [5, 6, 7, 8]),
    ("链接", [9, 10]),        # ⑪ 是 ⑩ 的子集，加进来就是双计
]

#: 各类「**本轮真跑过**」的产物证据 = `kb/l8/runs/<BASE>-*` 里的**文件名片段**。
#  ★ 2026-10-10 修（当天第二次「过度声明」）：本模块开头写的判据是
#    「该类的脚本在不在 engine 清单里 **＋ 本轮有没有产物**」，但代码**只实现了前半句**。
#    实测 2026-10-10 10:10 那趟：`verify_l0_nonrecord2.py` **完全没跑到**、
#    `verify_l0_urls.py` **跑了 33 分钟没收口**（两者都没出产物），
#    而摘要照样对**文档 / 链接**两类写「本轮已跑」—— 那句话**已经推给群了**。
#  ⇒ 这里把后半句补上：**没产物 = 本轮没跑**，如实降级，不靠清单替它作证。
#  · 判据取**产物名**、不取脚本名：产物名是本库已有的既成事实（`l0-url-verify` 这种），
#    由脚本自己写死，不随文件名漂移。
#  · ③ 图片类**故意不登记**：它的阶段产物落 `kb/l1/media/**`（`<run>.manifest.json`），
#    **不在 `kb/l8/runs/`** ⇒ 拿 l8 产物名给它做证据会**恒判未跑**（假红比漏报更坏）。
ROUND_EV = {
    1: "l0-align", 2: "l0-schema-align", 4: "video-keyframes",
    5: "l0-nonrecord-verify2", 6: "l0-nonrecord-verify2",
    7: "l0-nonrecord-verify2", 8: "l0-nonrecord-verify2",
    9: "l0-nonrecord-verify2",
    10: "l0-url-verify", 11: "l0-url-verify",
}


def _round_evidence(products, no):
    """该类本轮**有没有产物证据** → `(True/False/None, 片段)`；`None` = 本类无判据可用。"""
    ev = ROUND_EV.get(no)
    if not ev:
        return None, None
    return any(ev in p for p in products), ev


# ══════════════════════════════════════════════════════════════════════════
# 取数（全部走库内既有接口，不自己重新实现口径）
# ══════════════════════════════════════════════════════════════════════════
def _ledger_counts():
    import l0_ledger as L
    lat = L.latest_by_key("kb/l0/manifest.jsonl")
    rows = list(lat.values())
    by_kind = {}
    for r in rows:
        by_kind.setdefault(str(r.get("source_kind")), []).append(r)
    return rows, by_kind


# ── 台账行 → L0 四态（**唯一派生入口**）────────────────────────────────────
# ★ 2026-10-10 修（Owner 当场报「权限都齐了，为什么通知里还写读不到」）：
#   原先只看粗字段 `sha256_state`，凡是 no_scope／not_fetched／structure_only／未记状态
#   一律渲染成「读不到」—— 实测 19 行顶着这顶帽子，**真读不到的只有 2 行**，其余是
#   已经查清、且有字面证据的另外三种情形，被这顶帽子**误报成权限缺口**：
#     · `no_scope × gone`（8）飞书侧已不存在，用户确认 ＋ API 981003 互证 ⇒ **不适用（附证据）**
#     · `not_fetched × registered`（3）抓取器把字段「显示文本」当成 URL 主机名的解析残留
#       ⇒ 本来就不是真实链接 ⇒ **不适用（非真实链接·坏键）**
#     · `structure_only × updated`（2）base 类只核结构、`status_reason` 明写 ok
#       ⇒ **已对齐（结构核验）**
#     · `未记状态 × audit_note`（3）审计备忘行 —— **根本不是资源**，不该进任何一类的矩阵
#   判据只用**行自己的字面证据**（`status` ＋ `status_reason`），不做语义猜测。
#   `status` 是**精确**字段，`sha256_state` 是**粗**字段 —— 别把两者反过来用。
_NOT_A_RESOURCE = {"audit_note"}                 # 审计备忘：不是资源
_GONE = {"gone", "retracted"}                    # 已下线 —— **但下线有 5 种，见下**
_HARD_UNREADABLE = {"blocked_by_ua_policy", "dns_fail", "forbidden", "timeout"}
_BAD_KEY_MARKS = ("解析残留", "坏键")              # 抓取残留坏键：不是真实链接
_STRUCT_OK_MARK = "非记录类核验：ok"

# ★★ `status=gone` **不是**「飞书侧已不存在」的代理指标（2026-10-10 实测纠正）——
#   661 条 gone 的真实构成里只有 **8 条**是资源本体没了，其余 653 条是**本地留档**，
#   且台账自己把原因写清楚了。把 653 条报成「飞书侧已不存在」＝把自己的归档动作
#   说成飞书侧的事故。判据只能取**行自己的字面互证措辞**，不许按 status 一把抓。
_GONE_RESOURCE_MARKS = ("已不存在", "互证，标 gone")   # ⇒ 真·不适用（附证据）
_GONE_ARCHIVE_KINDS = (                                # ⇒ 已对齐（下架留档），**正常态**
    ("parent_gone", ("parent_gone",)),
    ("superseded_batch", ("整批替换", "Record not found")),
    ("rule_excluded", ("不入 L0", "审核状态非")),
)


def _gone_kind(rs):
    """`status=gone` 的行：返回 `None` 表示「资源本体在飞书侧已不存在」，否则回留档原因码。"""
    if any(m in rs for m in _GONE_RESOURCE_MARKS):
        return None
    for code, marks in _GONE_ARCHIVE_KINDS:
        if any(m in rs for m in marks):
            return code
    return "archived"


def _row_state(r):
    """台账一行 → `(四态, 原因码)`；返回 `(None, code)` 表示「按原逻辑继续判」。

    四态照 `kb-l0-feishu/references/coverage-matrix.md`：
    `已对齐` / `不适用（附证据）` / `读不到（原因码）` / `不可核（原因码）`。
    """
    st = str(r.get("status") or "")
    rs = str(r.get("status_reason") or "")
    sha = r.get("sha256_state")
    sha = "未记状态" if sha in (None, "None") else str(sha)

    if st in _NOT_A_RESOURCE:
        return None, "audit_note"                                  # 不是资源，不进矩阵
    if st in _GONE:
        # ★ `gone` 有五种，**只有一种**是「资源本体在飞书侧已不存在」（2026-10-10 实测：
        #   661 条 gone 里只有 8 条是这一种）。另四种是**我们自己的留档/排除动作**：
        #   `parent_gone`（父记录下架）／`superseded_batch`（飞书侧整批替换，本地留档）／
        #   `rule_excluded`（审核非通过、按 Owner 指令③不入 L0，文件**仍在飞书表中**）。
        #   把它们报成「不适用（飞书侧已不存在）」＝把自己的归档说成飞书侧的事故。
        gk = _gone_kind(rs)
        if gk is None:
            return "不适用（飞书侧已不存在，附证据）", "gone"
        return "已对齐（下架留档）", gk
    if any(m in rs for m in _BAD_KEY_MARKS):
        return "不适用（非真实链接·抓取残留坏键）", "bad_key"
    # ★ `非记录类核验：ok` 只对**非 full** 的行才有判读价值 —— 2026-10-10 修：
    #   原先不看 `sha`，把 23 条 `sha=full` 的**正常行**（doc 10／table 8／sheet 3／base 2）
    #   也判成「标签不符」，凭空造出三类「不可核」。
    if sha == "structure_only":
        return "已对齐（结构核验）", "structure_only"
    if sha in ("no_scope", "not_fetched") and _STRUCT_OK_MARK in rs:
        # base 类不核字节、`status_reason` 明写 ok ⇒ 结构核验通过；标签差异留原因码，可见、不静默。
        return "已对齐（结构核验）", "structure_only_via_reason"
    if st in _HARD_UNREADABLE:
        return "读不到（%s）" % st, st
    if sha in ("no_scope", "not_fetched"):
        return "读不到（%s）" % sha, sha
    if sha == "未记状态":
        return "不可核（未记状态）", "未记状态"
    return None, None


def _classify(sel):
    """一批台账行 → `(sha 分布, 四态计数, 真读不到, 不适用, 不可核, 审计备忘)`。

    ★ 归口只认**前缀**，且 `已对齐（…）`（结构核验／父记录下架留档）**是正常态** ——
      2026-10-10 踩过两次：第一版写 `else: unk`，把「已对齐（结构核验）」和
      「已对齐（父记录已下架，字节留档）」全扫进了「不可核」，凭空造出两处告警。
    """
    memos = [r for r in sel if str(r.get("status") or "") == "audit_note"]
    sel = [r for r in sel if str(r.get("status") or "") != "audit_note"]
    st, verdicts, hard, soft, unk = {}, {}, {}, {}, {}
    for r in sel:
        k = r.get("sha256_state")
        k = "未记状态" if k in (None, "None") else str(k)
        st[k] = st.get(k, 0) + 1
        v, code = _row_state(r)
        if v is None:
            v = "已对齐"
        verdicts[v] = verdicts.get(v, 0) + 1
        if v.startswith("读不到"):
            hard[code] = hard.get(code, 0) + 1
        elif v.startswith("不适用"):
            soft[code] = soft.get(code, 0) + 1
        elif v.startswith("不可核"):
            unk[code] = unk.get(code, 0) + 1
        # else：「已对齐（…）」⇒ 正常态，只进 `verdicts`，**绝不当问题报**
    return st, verdicts, hard, soft, unk, memos


def _video_stats():
    """视频不在 L0 台账里 —— 它落在 L1。

    ★ 结构（2026-10-09 实测，别按名字猜）：`video_ocr_segments` **每条 = 一个视频**，
      内层的 `segments[]` 才是**时间窗段**（带 `anchor`/`t_start`/`t_end`/`text`）。
      `video_asr_segments` 同样是**每条 = 一个视频**的口播转写。
      ⇒ 直接 `len(video_ocr_segments)` 得到的是**视频个数**，不是段数 —— 原先就标错了。
    """
    n_vid = n_seg = n_frame = n_chars = 0
    n_asr_text = n_asr_nospeech = 0
    for f in glob.glob("kb/l1/2_内部正负样本库/*.json"):
        try:
            d = json.load(io.open(f, encoding="utf-8"))
        except Exception:                                     # noqa: BLE001
            continue
        if not isinstance(d, dict):
            continue
        for e in (d.get("video_ocr_segments") or []):
            n_vid += 1
            inner = e.get("segments") or []
            n_seg += len(inner)
            n_frame += (e.get("frames_extracted") or 0)
            n_chars += sum(len(x.get("text") or "") for x in inner)
        for s in (d.get("video_asr_segments") or []):
            if (s.get("text") or "").strip():
                n_asr_text += 1
            elif (s.get("kind") or "") == "no_speech":
                n_asr_nospeech += 1
    d = "kb/l0/attachments/视频"
    n_bytes = 0
    if os.path.isdir(d):
        n_bytes = sum(1 for dp, _, fs in os.walk(d) for f in fs
                      if not f.startswith(".") and f != "_MANIFEST.json")
    return {"videos": n_vid, "ocr_segments": n_seg, "frames": n_frame, "ocr_chars": n_chars,
            "asr_text": n_asr_text, "asr_no_speech": n_asr_nospeech, "files": n_bytes}


# ★ 2026-10-10 晚：`_user_token_ok()` 已删除 —— 它的用途是「无 user 令牌时把文档类降级为未核验」，
#   而 Owner 把 5 个对象授权给「守衡」bot 之后，**文档类走 bot、根本不看 user 令牌** ⇒ 判断前提消失；
#   留着只会把「会跑」误报成「未跑」。若将来又出现 bot 读不到的对象，判据应读**脚本那一轮的 run 产物**
#   （它自己会写 `user_token_missing`），**不靠猜令牌状态**。

def _is_feishu_link(row):
    """该 URL 行是不是**飞书域**（`*.feishu.cn` / `*.larksuite.com`）。

    为什么要分：coverage-matrix 的 ⑩ 是「记录里的内嵌链接」（全部），
    ⑪ 是「**飞书域外**的地址」⇒ ⑪ 是 ⑩ 的**子集**，两行相加就是双计。
    """
    s = "%s %s" % (row.get("resource_key") or "", row.get("entry_url") or "")
    m = re.search(r"https?://([^/\s\"]+)", s)
    host = (m.group(1) if m else "").lower()
    return host.endswith(".feishu.cn") or host == "feishu.cn" or host.endswith(".larksuite.com")


def _daily_engines():
    """日更**实际会跑**的引擎集合 = `layers.yaml` 各层 `engine:` 的 basename。

    ★ 这是本脚本与「按类型出数」之间最关键的一条：**日更跑的是这张清单，不是 skill 的阶段清单**。
      实测 2026-10-09：L0 的清单只有 4 个脚本（阶段 1–4），
      阶段 5–8（非记录/图片字节/视频/链接）**不在里面** ⇒ 那几类日更根本不跑。
    """
    import yaml
    doc = yaml.safe_load(io.open("kb/l7/registry/layers.yaml", encoding="utf-8")) or {}
    out = set()
    for x in (doc.get("layers") or []):
        for e in (x.get("engine") or []):
            out.add(os.path.basename(str(e).split("（")[0].strip()))
    return out


def _run_products(base):
    return sorted(os.path.basename(p) for p in glob.glob("kb/l8/runs/%s-*.json" % base))


def _load(base, suffix):
    for p in sorted(glob.glob("kb/l8/runs/%s*%s" % (base, suffix)), key=os.path.getmtime):
        try:
            return json.load(io.open(p, encoding="utf-8"))
        except Exception:                                     # noqa: BLE001
            continue
    return None


#: 预演/自述的判据词。⚠️ 这里判的是「**这份读数强不强**」（报告要不要报黄），
#: **不是** `layer_freshness._preview_marks` 那把「算不算一次层运行」的尺子 —— 两件事，
#: 别把两把尺子合成一把（2026-10-19：同一个 verdict 在两处各有各的用途）。
_PREVIEW_MARKS = ("预演", "未落盘", "非执行证据", "干跑", "dryrun", "dry_run")


def _split_layers(stamps):
    """把落章切成 `done` / `preview` / `bad` / `missing` —— **纯函数**，自证直接喂夹具。

    ★ 2026-10-19：`done` 只收**真执行**的层；退出码 0 但落章是预演/自述的进 `preview`
      （报黄，不判红 —— 见 `_layer_stamps` 的说明）。
    """
    done = [L for L, v in stamps.items() if v and v["exit"] == 0 and not v.get("preview")]
    preview = [L for L, v in stamps.items() if v and v["exit"] == 0 and v.get("preview")]
    bad = ["%s(exit=%s)" % (L, v["exit"]) for L, v in stamps.items() if v and v["exit"] != 0]
    missing = [L for L, v in stamps.items() if not v]
    return {"done": done, "bad": bad, "missing": missing, "preview": preview}


def _layer_stamps(base):
    """复刻 `observe_layers.py` 的落章发现（**不抄第二份**）。

    ★ 2026-10-19：**除了退出码，还要判这份落章是「真执行」还是「预演／自述」**。
      实测：10-19 的 L7 落章 `daily-…-L7.json` 退出码 0，verdict 却是
      「全走完（预演 · 未落盘 · 非执行证据）」、skill 证据退回注册表声明 ⇒ 卡片照打 `L7✅`。
      库规是「**预演/自述 ⇒ 报黄，不判红**」：绿是绿、黄是黄，混成一片绿
      等于把「没真跑」说成「跑了」。
    """
    import observe_layers as OL
    out = {}
    for L in ("L0", "L1", "L2", "L3", "L4", "L5", "L6", "L7"):
        p = OL.find_stamp(base, L)
        if not p:
            out[L] = None
            continue
        rc, verdict, ev = 0, "", ""
        try:
            d = json.load(io.open(p, encoding="utf-8"))
            for k in ("exit_code", "exit", "rc"):
                if isinstance(d.get(k), int):
                    rc = d[k]
                    break
            verdict = str(d.get("verdict") or "")
            ev = str(((d.get("extra") or {}).get("skill_evidence")) or "")
        except Exception:                                     # noqa: BLE001
            pass
        out[L] = {"stamp": os.path.basename(p), "exit": rc, "verdict": verdict,
                  "skill_evidence": ev,
                  "preview": any(m in verdict for m in _PREVIEW_MARKS)}
    return out


# ══════════════════════════════════════════════════════════════════════════
# 排期事实：**这趟是不是排期那一趟**，以及**上一次排期趟跑到哪了**
# ══════════════════════════════════════════════════════════════════════════
# ★ 2026-10-19（Owner 同意「推荐 ①」）：报告标题原先**写死「日更」**，而排期早在 2026-10-16
#   就改成**周更（每周日 03:30）**；更糟的是 10-19 10:03 这一趟**根本不在排期时刻**
#   （周日 03:30 那趟 10-18 停在 L0 闸门红），报告却把它印成一条正常的「日更报告」。
#   ⇒ 周期词与「本趟 vs 排期」一律**从 launchd plist 现读**（排期的唯一真源），
#   解析仍只留 `watch_review_readiness._read_schedule()` 那一处 —— 本段只**解读**，不重写解析。
WEEKDAY_CN = ("周日", "周一", "周二", "周三", "周四", "周五", "周六")   # launchd：0/7=周日
#: 排期时刻与本趟 BASE 的比对容差（分钟）：launchd 会因休眠唤醒抖动几分钟，
#: 那不足以把「排期那一趟」说成「补跑」；超过它才叫补跑。
SLOT_TOLERANCE_MIN = 20


def _base_dt(base):
    """`daily-20261019-1003` → `datetime(2026,10,19,10,3)`；解析不出回 `None`。"""
    m = re.match(r"^daily-(\d{8})-(\d{4})", str(base or ""))
    if not m:
        return None
    try:
        return datetime.datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M")
    except ValueError:
        return None


def _prev_slot_line(base_dt, spec):
    """**上一次排期趟**跑到哪了 —— 读 `kb/l7/runs/daily-<日期>-<时刻>-L0.json` 的 verdict。

    为什么只看 L0 那一份：L0 是每一轮的第一层，它停在哪就代表整轮停在哪
    （2026-10-18 实测就是「停在 L0 闸门红：exit=1」⇒ L1–L7 全无落章）。
    找不到落章就写「未见落章」—— **没落章 ≠ 没跑，也 ≠ 跑成**，不许猜。
    """
    hh, mm = spec["hour"], spec["minute"]
    wds = spec.get("weekdays") or []
    for i in range(1, 9):
        d = base_dt - datetime.timedelta(days=i)
        if wds and ((d.weekday() + 1) % 7) not in wds:
            continue
        if not wds and i > 1:
            break                                   # 每天：只看前一天
        stamp = "%s-%02d%02d" % (d.strftime("%Y%m%d"), hh, mm)
        p = os.path.join("kb", "l7", "runs", "daily-%s-L0.json" % stamp)
        if not os.path.exists(p):
            return "`daily-%s` → **未见落章**（没跑成，或落章不在 `kb/l7/runs/`）" % stamp
        verdict = ""
        try:
            with io.open(p, encoding="utf-8") as fh:
                verdict = str((json.load(fh) or {}).get("verdict") or "")
        except Exception:                                     # noqa: BLE001
            verdict = ""
        return "`daily-%s` → **%s**" % (stamp, verdict or "落章里没有 verdict")
    return None


def _schedule_fact(base):
    """本驱动**实际排期** vs 本趟 BASE → 一份事实（读不到就如实写读不到）。

    返回 `{"kind","human","is_slot","base_at","plist","prev_slot","spec","why"}`；
    `kind` ∈ {`周更`,`日更`,`周期`,None}；`is_slot` ∈ {True,False,None}。
    **任何一步失败都不许让摘要挂掉** —— 调用方按「读不到」渲染，不按「正常」。
    """
    out = {"kind": None, "human": None, "is_slot": None, "base_at": None,
           "plist": None, "prev_slot": None, "spec": None, "why": ""}
    try:
        from watch_review_readiness import DAILY_PLIST, _read_schedule
        spec, how = _read_schedule()
        out["plist"] = os.path.basename(DAILY_PLIST)
    except Exception as e:                                    # noqa: BLE001
        out["why"] = "读不到排期（%r）" % e
        return out
    if not spec:
        out["why"] = "读不到排期（%s）" % how
        return out
    wds = spec.get("weekdays") or []
    if not wds:
        out["kind"] = "日更"
        out["human"] = "每天 %02d:%02d" % (spec["hour"], spec["minute"])
    elif len(wds) == 1:
        out["kind"] = "周更"
        out["human"] = "每%s %02d:%02d" % (WEEKDAY_CN[wds[0] % 7], spec["hour"], spec["minute"])
    else:
        out["kind"] = "周期"
        out["human"] = "%s %02d:%02d" % ("、".join(WEEKDAY_CN[w % 7] for w in wds),
                                        spec["hour"], spec["minute"])
    out["spec"] = spec
    d = _base_dt(base)
    if d is None:
        out["why"] = "BASE 解析不出时刻（%r）" % (base,)
        return out
    out["base_at"] = d.strftime("%Y-%m-%d %H:%M")
    same_wd = (not wds) or (((d.weekday() + 1) % 7) in wds)
    delta = abs((d.hour * 60 + d.minute) - (spec["hour"] * 60 + spec["minute"]))
    out["is_slot"] = bool(same_wd and delta <= SLOT_TOLERANCE_MIN)
    out["prev_slot"] = _prev_slot_line(d, spec)
    return out


def _kind_word(D):
    """报告的**周期口径词**（`周更`／`日更`／`周期`）；排期读不到回 `None`（标题不写周期）。"""
    return (D.get("schedule") or {}).get("kind")


def _slot_words(sched):
    """本趟与排期的关系，一句话。`is_slot` 三态：True=排期那一趟／False=补跑／None=比不了。"""
    v = (sched or {}).get("is_slot")
    if v is True:
        return "= **排期那一趟**"
    if v is False:
        return "**不在排期时刻 ⇒ 补跑／手动跑**"
    return "**与排期比对不了**"


def _freshness_summary():
    """**判据要一起报出来** —— 只说"不陈旧"，读者不知道它按什么尺子量的。

    Owner 2026-10-09 反馈：「新鲜度这次没写明是什么意思？什么时间范围的新鲜度」
    ⇒ 报三样：① 判据（`layer_freshness.judge`）② 阈值（`STALE_AFTER`，实测 24h）
       ③ **本次实测最旧的那一层与它的年龄**。
    """
    try:
        import layer_freshness as lf
        bad, ages = [], {}
        for L in ("L0", "L1", "L2", "L3", "L4", "L5", "L6", "L7"):
            j = lf.judge("kb", L)
            a = j.get("run_age")
            if isinstance(a, (int, float)):
                ages[L] = round(a / 3600.0, 1)
            if not j.get("fresh"):
                bad.append((L, str(j.get("reason") or "")))
        oldest = max(ages.items(), key=lambda kv: kv[1]) if ages else (None, None)
        # ★ 2026-10-19：判词**不再截断**。原先是 `[:40]` —— 实测把 127 字的判词切成
        #   「…`change_state=no_new_input` 而*」，**真正的原因（谁变了、哪个时间晚于哪个
        #   时间）全被切掉**，读者只看到一句断在半截的话；而同一段「本次实测」又写着 0.0h
        #   ⇒ 「陈旧」与「刚跑过」并列，谁都判断不了。判词长度是**信息**，不是噪声。
        return {"ok": not bad,
                "stale": ["%s(%s)" % (L, r) for (L, r) in bad],
                "stale_pairs": [{"layer": L, "reason": r} for (L, r) in bad],
                "ages": ages,
                "oldest_layer": oldest[0], "oldest_h": oldest[1],
                "threshold_h": round(getattr(lf, "STALE_AFTER", 86400) / 3600.0, 1),
                # ★ 2026-10-16：给人看的写法**从常量取**（周更后 24h → 8 天，
                #   抄在文案里的「24 小时」会当场说谎）。
                "threshold_human": getattr(lf, "STALE_AFTER_HUMAN", "24 小时")}
    except Exception as e:                                    # noqa: BLE001
        return {"ok": None, "error": repr(e)[:120]}


# ══════════════════════════════════════════════════════════════════════════
# 拼摘要
# ══════════════════════════════════════════════════════════════════════════
def build(base):
    align = _load(base, "-L0-l0-align.json") or _load(base, "-l0-align.json")
    ingest = _load(base, "-L0-l0-ingest.json") or _load(base, "-l0-ingest.json")
    emit = _load(base, "-L0-l0-manifest-emit.json")
    schema = _load(base, "-L0-l0-schema-align.json") or _load(base, "-l0-schema-align.json")
    rows, by_kind = _ledger_counts()
    vid = _video_stats()
    engines = _daily_engines()
    stamps = _layer_stamps(base)
    fresh = _freshness_summary()
    products = _run_products(base)

    D = {"base": base, "at": time.strftime("%Y-%m-%d %H:%M:%S"),
         "align": (align or {}).get("summary") or {},
         "align_tables": (align or {}).get("tables") or {},
         "ingest": {**{k: len((ingest or {}).get(k) or []) for k in ("written", "skipped", "archived")},
                    # ★ 2026-10-19：「跳过 11」要说清**为什么**、以及是不是**声明内**
                    "skip_reasons": _skip_reasons(ingest),
                    "declared_only_feishu": _declared_only_feishu()},
         "emit": {"appended": (emit or {}).get("appended"),
                  "before": (emit or {}).get("rows_before"),
                  "after": (emit or {}).get("rows_after")},
         "schema": schema, "video": vid, "stamps": stamps, "fresh": fresh,
         "products": products, "engines": sorted(engines)}
    # ★ 2026-10-19：本趟是不是**排期那一趟**、**上一次排期趟**跑到哪了 —— 现读一次，
    #   两个渲染器（md／推文）共用，别各读一遍（读两遍就会有两次真相）。
    D["schedule"] = _schedule_fact(base)

    # ── 12 类矩阵 ─────────────────────────────────────────────────────
    matrix = []
    for no, name, kind, scripts, how in CLASSES:
        in_daily = any(s in engines for s in scripts)
        cnt, note, state = None, "", None
        if how == "schema":
            n = len((schema or {}).get("tables") or {}) if isinstance(schema, dict) else 0
            cnt = n
            note = "schema_snapshots %d 表" % n
            state = "已对齐" if (in_daily and n) else ("不可核（no_product_this_run）" if in_daily
                                                     else "不可核（stage_not_in_daily_engine_list）")
        elif how == "records":
            s = D["align"] or {}
            # ★ 条数一律用**台账条数**（与其余 11 行同口径）；对账的四个数进 note ——
            #   原先拿 `same`（1014）当条数，与别的行「库内条数」不是一个意思，会看错。
            cnt = len(by_kind.get("feishu_bitable_record") or [])
            note = "台账 %d 条 ｜ 本轮：一致 %s ｜ **飞书多 %s** ｜ **L0多 %s** ｜ 值变 %s ｜ 拉取失败 %s" % (
                cnt, s.get("same"), s.get("only_feishu"), s.get("only_l0"),
                s.get("changed"), _v(s.get("pull_failed")))
            if not s:
                state = "不可核（no_product_this_run）"
            elif s.get("pull_failed"):
                state = "读不到（pull_failed=%s）" % s["pull_failed"]
            elif s.get("only_l0") or s.get("changed"):
                state = "不可核（L0多=%s／值变=%s 需逐条查）" % (s.get("only_l0"), s.get("changed"))
            else:
                state = "已对齐"
        elif how == "video":
            cnt = vid["files"]
            note = "有字节 %d ｜ 画面文字 %d 段 / %d 帧 / %d 字 ｜ 口播 %d 条（no_speech %d）" % (
                vid["files"], vid["ocr_segments"], vid["frames"], vid["ocr_chars"],
                vid["asr_text"], vid["asr_no_speech"])
            state = ("不适用（飞书侧视频素材 0 条）" if cnt == 0
                     else ("已对齐" if in_daily else "不可核（stage_not_in_daily_engine_list）"))
        else:                                                  # 台账口径
            if kind == "feishu_bitable":
                sel = [r for r in rows if str(r.get("source_kind") or "").startswith("feishu_bitable_")
                       and r.get("source_kind") != "feishu_bitable_record"]
            elif kind == "url":
                sel = by_kind.get("url") or []
            elif kind == "url_external":
                sel = [r for r in (by_kind.get("url") or []) if not _is_feishu_link(r)]
                _all = len(by_kind.get("url") or [])
                note_extra = "**⑩ 的子集，不与 ⑩ 相加**（⑩ %d ／ 飞书域 %d ／ 域外 %d）" % (
                    _all, _all - len(sel), len(sel))
            elif kind == "UNKNOWN":
                sel = [r for r in rows if not r.get("source_kind")]
            else:
                sel = by_kind.get(kind) or []
            # ★ 2026-10-10：归口走 `_classify()`（唯一入口，含自检）——
            #   审计备忘行在这里被剔掉（不是资源），四态也不再看粗字段 `sha256_state`。
            st, verdicts, hard, soft, unk, memos = _classify(sel)
            sel = [r for r in sel if str(r.get("status") or "") != "audit_note"]
            cnt = len(sel)
            note = "／".join("%s %d" % (k, v) for k, v in sorted(st.items())) or "—"
            if verdicts:
                note += " ｜ 四态：" + "／".join(
                    "%s %d" % (k, v) for k, v in sorted(verdicts.items()))
            if memos:
                note += " ｜ 另剔审计备忘 %d 行（非资源）" % len(memos)
            if kind == "url_external":
                note = note_extra
            elif kind == "url":
                _ex = sum(1 for r in sel if not _is_feishu_link(r))
                note = "%s ｜ 飞书域 %d ／ 域外 %d（⑪ 是其中域外那部分，**别相加**）" % (
                    note, len(sel) - _ex, _ex)
            if cnt == 0:
                state = "不适用（飞书侧该类 0 条）"
            elif kind == "url_external":
                # ⑪ 是 ⑩ 的**子集** ⇒ 不单独下判决，否则同一批行被两个类各判一次（双计）。
                state = "（⑩ 的子集，判决见 ⑩）"
            elif not in_daily and not scripts:
                state = "不可核（stage_not_in_daily_engine_list）"
            elif hard:
                state = "读不到（%s）" % "／".join("%s=%d" % (k, v) for k, v in sorted(hard.items()))
            elif unk:
                state = "不可核（%s）" % "／".join("%s=%d" % (k, v) for k, v in sorted(unk.items()))
            elif soft:
                # 「不适用（附证据）」是**合法四态**，不是缺陷 —— 写进状态里，别混进「读不到」。
                state = "不适用（%s）" % "／".join("%s=%d" % (k, v) for k, v in sorted(soft.items()))
            else:
                state = "已对齐"
        # ★ 2026-10-10：「在清单里」**不等于「本轮跑过」** —— 补产物证据（见 `ROUND_EV`）。
        ev_ok, ev_frag = _round_evidence(products, no)
        if in_daily and ev_ok is False:
            state = "不可核（no_round_product：%s）" % ev_frag
        matrix.append({"no": no, "name": name, "state": state, "count": cnt,
                       "note": note, "in_daily": in_daily, "ev_ok": ev_ok,
                       "scripts": scripts, "kind": kind})
    D["matrix"] = matrix
    # ★ 2026-10-10 晚：**删掉**「无 user 令牌 ⇒ 文档类未核验」的降级。它昨天加的时候是对的
    #   （那时文档类必须走 user，而 user 令牌只活 2h、日更在 03:30 ⇒ 必然跳过）；
    #   但 **Owner 当日把那 5 个对象授权给「守衡」bot、bot 实测 `{'ok': 10}` 全通**，
    #   于是文档类改成**默认 bot** ⇒ **不再看 user 令牌**。
    #   留着它会把"会跑"误报成"未跑" —— 与它当初要防的过度声明**方向相反、性质相同**。
    #   残余：若将来又出现"bot 读不到"的对象，脚本自己的守卫会把 `user_token_missing`
    #   写进它那一轮的 run 产物；到时摘要再读那个产物即可（不靠本函数猜令牌状态）。

    # ── 五类速览 ──────────────────────────────────────────────────────
    five = []
    for label, nos in FIVE:
        picked = [m for m in matrix if m["no"] in nos]
        total = sum(m["count"] or 0 for m in picked)
        # ★ 「本轮已跑」必须**有产物作证**（`ev_ok is True`）或**本类无判据**（`None`，如 ③ 图片）；
        #   `False` = 清单里有、但这轮没出产物 ⇒ **不许说已跑**。
        ran = any(m["in_daily"] and m.get("ev_ok") is not False for m in picked)
        why = None if ran else next(
            ("本轮的阶段产物未见（%s）" % ev for m in picked
             for ev in [_round_evidence(products, m["no"])[1]] if m.get("ev_ok") is False
             and ev), "不在日更 engine 清单")
        states = sorted({str(m["state"]).split("（")[0] for m in picked})
        five.append({"label": label, "count": total, "ran": ran, "why": why,
                     "states": states, "detail": "；".join(
                         "%s %s%s" % (m["name"].split("（")[0], m["count"],
                                      "" if m["state"] == "已对齐" else "·" + str(m["state"]))
                         for m in picked)})
    D["five"] = five

    # ★ 2026-10-19：`done` 只收**真执行**的层；退出码 0 但落章是预演/自述的进 `preview`
    #   （报黄，不判红 —— 见 `_layer_stamps` 的说明）。切分逻辑抽成 `_split_layers()` 纯函数，
    #   好让自证能直接喂夹具（否则只能靠真库，改坏了也未必看得见）。
    D["layers"] = _split_layers(stamps)
    return D


def _skip_reasons(ingest):
    """入库回执里 `skipped` **按原因分组**（同因合并，多的在前）。

    ★ 2026-10-19：卡片原先只写「跳过 11」，**不说为什么** —— 读起来像「11 条数据被丢了」。
      原因就在入库回执里（每条 `why` 一句），不展示等于让读者自己猜。
    """
    cnt = {}
    for x in (ingest or {}).get("skipped") or []:
        why = str((x or {}).get("why") or "").strip() or "（回执里没写原因）"
        cnt[why] = cnt.get(why, 0) + 1
    return sorted(({"why": k, "n": v} for k, v in cnt.items()), key=lambda d: -d["n"])


def _declared_only_feishu():
    """`kb/l7/registry/l0-expected-diffs.yaml` 里 **`only_feishu` 的声明合计**。

    **走 `l0_gate.py` 的同一个读取器**（`load_yaml` ＋ `EXPECT`）—— 不抄第二份解析，
    也不在这里复算「预期内/真差异」（那是闸门的事）。读不到就回 `None`：**不猜**。
    """
    try:
        sys.path.insert(0, os.path.join("kb", "l7", "scripts"))
        import l0_gate as _g
        doc = _g.load_yaml(_g.EXPECT) or {}
        items = []
        for e in (doc.get("expected") or []):
            if isinstance(e, dict) and e.get("kind") == "only_feishu":
                try:
                    n = int(e.get("expected"))
                except (TypeError, ValueError):
                    continue
                items.append({"id": str(e.get("id") or "?"),
                              "table": str(e.get("table") or "?"), "expected": n})
        if not items:
            return None
        return {"total": sum(i["expected"] for i in items), "items": items}
    except Exception:                                         # noqa: BLE001
        return None


def _v(x):
    """缺键（None）写 `—`，**不写 0** —— 0 是在断言"没有失败"，缺键没有这个证据。"""
    return "—" if x is None else x


def render_md(D):
    A = D["align"]
    # ★ 2026-10-19：标题的周期词与「本趟 vs 排期」**从 plist 现读**（原写死「日更」，
    #   而排期 2026-10-16 起是周更；10-19 那趟更不在排期时刻）。
    _sched = D.get("schedule") or {}
    L = ["# DSH 知识库 L0 ↔ 飞书侧（内容治理源数据）· %s对齐摘要"
         % (_kind_word(D) or "周期"), "",
         "**BASE** `%s` ｜ 生成于 %s" % (D["base"], D["at"]), ""]
    if _sched.get("human"):
        L.append("**排期**：%s（launchd `%s`） ｜ 本趟 **%s** %s"
                 % (_sched["human"], _sched.get("plist") or "plist",
                    _sched.get("base_at") or D["base"], _slot_words(_sched)))
        if _sched.get("prev_slot"):
            L.append("**上一次排期趟**：%s" % _sched["prev_slot"])
        L.append("")
    elif _sched.get("why"):
        L += ["**排期**：读不到（%s）—— 本报告不写周期口径" % _sched["why"], ""]
    L += [
         "> 由 `kb/l8/daily_digest.py` 出。口径照 `kb-l0-feishu` 的 "
         "`references/coverage-matrix.md`：**12 类 × 四态**"
         "（`已对齐`／`不适用（附证据）`／`读不到（原因码）`／`不可核（原因码）`）。", "",
         "## 0. 一句话", ""]
    n_run = sum(1 for m in D["matrix"] if m["in_daily"])
    L.append("- 记录层：一致 %s ｜ **新增 %s** ｜ **下架 %s** ｜ 值变 %s ｜ 拉取失败 %s"
             % (A.get("same"), A.get("only_feishu"), A.get("only_l0"),
                A.get("changed"), _v(A.get("pull_failed"))))
    L.append("- 覆盖率：12 类里 **%d 类在日更 engine 清单内**，其余落 "
             "`不可核（stage_not_in_daily_engine_list）`" % n_run)
    L.append("- 各层：完成 %s%s%s%s" % (
        ",".join(D["layers"]["done"]) or "无",
        "｜失败 " + ",".join(D["layers"]["bad"]) if D["layers"]["bad"] else "",
        "｜无落章 " + ",".join(D["layers"]["missing"]) if D["layers"]["missing"] else "",
        "｜**预演/自述（不判红，但不算真执行）** " + ",".join(D["layers"].get("preview") or [])
        if D["layers"].get("preview") else ""))
    L += ["", "## 1. 记录层（① 表格记录·文本字段）", "",
          "| 量 | 值 |", "|---|---|",
          "| 一致 | %s |" % A.get("same"), "| **新增（飞书多）** | **%s** |" % A.get("only_feishu"),
          "| **下架（L0 多）** | **%s** |" % A.get("only_l0"), "| 值变 | %s |" % A.get("changed"),
          "| 拉取失败 | %s |" % _v(A.get("pull_failed")), ""]
    if D["align_tables"]:
        L += ["逐表：", "", "| 表 | 飞书 | L0 | 一致 | 飞书多 | L0多 | 值变 |", "|---|---|---|---|---|---|---|"]
        for t in D["align_tables"].values():
            if isinstance(t, dict):
                L.append("| %s | %s | %s | %s | %s | %s | %s |" % (
                    t.get("table"), t.get("feishu_records"), t.get("l0_records"), t.get("same"),
                    t.get("only_feishu"), t.get("only_l0"), t.get("changed")))
        L.append("")
    _ing = D["ingest"]
    L += ["## 2. 入库与台账", "",
          "- 入库：写入 **%s** ｜ 跳过 %s ｜ 归档 %s" % (
              _ing["written"], _ing["skipped"], _ing["archived"])]
    # ★ 2026-10-19：「跳过 11」必须说清**为什么**、以及是不是**声明内**（原先只有个数）。
    for _r in (_ing.get("skip_reasons") or [])[:5]:
        L.append("  - 跳过 **%d** 条：%s" % (_r["n"], _r["why"]))
    if len(_ing.get("skip_reasons") or []) > 5:
        L.append("  - 另有 %d 种原因，见 `kb/l8/runs/%s-L0-l0-ingest.json`"
                 % (len(_ing["skip_reasons"]) - 5, D["base"]))
    _dec = _ing.get("declared_only_feishu") or {}
    if _dec.get("total") and _dec["total"] == _ing.get("skipped"):
        L.append("  - **跳过数 = 声明数**（%d）：`kb/l7/registry/l0-expected-diffs.yaml` "
                 "%s ⇒ **这 %d 条是声明内的预期排除，不是漏抓**"
                 % (_ing["skipped"],
                    "、".join("%s(%s) expected %s"
                              % (i["id"], i["table"], i["expected"]) for i in _dec.get("items") or []),
                    _ing["skipped"]))
    L.append("- 补登记（台账）：%s 行（%s → %s）—— ⚠️ 这是 **reconcile 的追加行**，"
             "**不是入库条数**（两本账，别相加）" % (
                 D["emit"]["appended"], D["emit"]["before"], D["emit"]["after"]))
    L.append("")
    L += ["## 3. 覆盖率矩阵（**12 类 × 四态** —— 该文件 §三 硬性要求的那张表）", "",
          "| # | 类型 | 状态 | 条数 | 依据 / 原因码 | 在日更清单 |", "|---|---|---|---|---|---|"]
    for m in D["matrix"]:
        L.append("| %d | %s | %s | %s | %s | %s |" % (
            m["no"], m["name"], m["state"], m["count"], m["note"],
            "✅" if m["in_daily"] else "❌"))
    _nr = sorted({s for m in D["matrix"] if not m["in_daily"] for s in m["scripts"]})
    # ★ 2026-10-10：`_nr` 为空时**不许留个空壳**（原先会渲染出一个空的 ``` 块 + 一段
    #   「这几类日更不更新」的解释，而实际上 11 类都在清单里、剩下那类飞书侧 0 条）。
    if _nr:
        L += ["", "> **两个数分开看**：「条数」是**库内现在**的实况（走 `l0_ledger.latest_by_key`）；",
              "> 「在日更清单」是**这一轮会不会动它**（`layers.yaml` 各层 `engine:`，运行时读）。",
              "> 「❌」不等于数据有问题 —— 它说的是**日更不跑这一类**，历史数据仍在库里、仍可检索。", "",
              "### 为什么这些类「不在日更清单」", "",
              "日更执行的是 `kb/l7/registry/layers.yaml` **各层 `engine:` 清单**（唯一真源），",
              "而覆盖下面这些类的脚本**没有被登记进那张清单** ⇒ **从来没被接进日更**：", "",
              "```"] + ["  " + s for s in _nr] + ["```", "",
              "- 后果：这几类**日更不更新**（不是数据丢了 —— 数据在库里、仍可检索）。",
              "- 要它们每天出数，得改 `layers.yaml` 的 `engine:` 清单 ＝ 改「日更写什么」",
              "  ＝ **规则层动作，需 Owner 批**（见 `kb/l8/CHANGELOG.md` 2026-10-09「推荐 B」）。", ""]
    else:
        L += ["", "> **两个数分开看**：「条数」是**库内现在**的实况（走 `l0_ledger.latest_by_key`）；",
              "> 「在日更清单」是**这一轮会不会动它**（`layers.yaml` 各层 `engine:`，运行时读）。",
              "> 「❌」不等于数据有问题 —— 它说的是**日更不跑这一类**，历史数据仍在库里、仍可检索。", "",
              "### 「不在日更清单」的类",
              "",
              "- **没有**「有脚本却没接进日更」的类 —— 12 类里 **11 类在清单内**。",
              "- 唯一标 ❌ 的第 ⑫ 类「其它附件 / 未知类型」**飞书侧 0 条**且**没有专属脚本**",
              "  （它本来就不是一类资源，是兜底格）。", ""]
    L += ["## 4. 五类速览", "", "| 类 | 库内条数 | 本轮跑了 | 说明 |", "|---|---|---|---|"]
    for f in D["five"]:
        L.append("| **%s** | %s | %s | %s |" % (
            f["label"], f["count"],
            "✅ 已跑" if f["ran"] else ("❌ 未跑（%s）" % (f.get("why") or "不在日更清单")),
            f["detail"]))
    L += ["", "## 5. 各层写档 / 新鲜度", "",
          "| 层 | 落章 | 退出码 | 这份落章强不强 |", "|---|---|---|---|"]
    for k in ("L0", "L1", "L2", "L3", "L4", "L5", "L6", "L7"):
        v = D["stamps"].get(k)
        # ★ 2026-10-19：退出码 0 **不等于**真执行 —— 预演/自述档要在这里看得见（报黄，不判红）。
        _rd = "—"
        if v:
            _rd = ("⚠️ **预演/自述 · 不判红但不算真执行**（`%s`）" % (v.get("verdict") or "")
                   if v.get("preview") else "真执行")
        L.append("| %s | %s | %s | %s |" % (k, (v or {}).get("stamp") or "**无**",
                                           (v or {}).get("exit") if v else "—", _rd))
    fr = D["fresh"]
    L += ["", "### 新鲜度是怎么判的", "",
          "- **判据**：`kb/l7/scripts/layer_freshness.py::judge()` 逐层（L0–L7）看"
          "「**最近一次成功 RUN 距今**」，超过阈值即判陈旧。",
          "- **阈值**：`STALE_AFTER = %sh`（%s 内跑过算新鲜；唯一出处 "
          "`kb/l7/scripts/layer_freshness.py`）。"
          % (fr.get("threshold_h"), fr.get("threshold_human") or "24 小时")]
    # ★ 2026-10-19：陈旧判词按层分行给**全文**（原先截 40 字，切在句中）。
    if fr.get("ok") is False:
        L.append("- **结论**：⚠️ 陈旧 %d 层（判词逐条给全文，不截断）："
                 % len(fr.get("stale") or []))
        for _p in (fr.get("stale_pairs") or []):
            L.append("  - **%s**：%s" % (_p.get("layer"), _p.get("reason")))
    else:
        L.append("- **结论**：%s"
                 % ("✅ 各层不陈旧" if fr.get("ok")
                    else "（测不到：%s）" % fr.get("error")))
    L += ["- **本次实测**：%s" % ("；".join("%s %sh" % (k, v) for k, v in (fr.get("ages") or {}).items())
                              or "—"),
          "- 最旧：**%s %sh**" % (fr.get("oldest_layer"), fr.get("oldest_h")), ""]
    L += ["## 6. 本轮产物", ""] + ["- `kb/l8/runs/%s`" % p for p in D["products"]] + [""]
    return "\n".join(L) + "\n"


def render_push(D):
    """推文（飞书消息）：**短**，但把 Owner 点名的那几项放在最前。"""
    A = D["align"]
    # ★ Owner 2026-10-09 反馈①：「没有写明是 DSH 知识库 L0 与飞书侧内容治理源侧数据对齐」
    # ★★ 2026-10-19：周期词**不许写死**（原写「（日更报告）」）。排期 2026-10-16 起是**周更**，
    #   而 10-19 10:03 这一趟**根本不在排期时刻**（周日 03:30 那趟 10-18 停在 L0 闸门红）——
    #   卡上却是一条不带任何提示的「日更报告」⇒ 读者无法判断「周更到底跑成没有」。
    _kind = _kind_word(D)
    _sched = D.get("schedule") or {}
    head = ("📊 **DSH 知识库 · L0 ↔ 飞书侧（内容治理源数据）对齐**（%s报告）" % _kind
            if _kind else "📊 **DSH 知识库 · L0 ↔ 飞书侧（内容治理源数据）对齐**（报告）")
    L = [head, "BASE `%s` ｜ 起跑见日志 ｜ 生成 %s" % (D["base"], D["at"])]
    if _sched.get("human"):
        L.append("**排期**：%s ｜ 本趟 **%s** %s"
                 % (_sched["human"], _sched.get("base_at") or D["base"], _slot_words(_sched)))
        if _sched.get("prev_slot"):
            L.append("**上一次排期趟**：%s" % _sched["prev_slot"])
    elif _sched.get("why"):
        L.append("**排期**：读不到（%s）—— 本条不写「日更／周更」" % _sched["why"])
    L.append("")
    L.append("**记录层**：一致 %s ｜ **新增 %s** ｜ **下架 %s** ｜ 值变 %s ｜ 拉取失败 %s"
             % (A.get("same"), A.get("only_feishu"), A.get("only_l0"),
                A.get("changed"), _v(A.get("pull_failed"))))
    _ing = D["ingest"]
    L.append("**入库**：写入 %s ｜ 跳过 %s ｜ 归档 %s ｜ 台账 +%s（%s → %s）"
             % (_ing["written"], _ing["skipped"], _ing["archived"],
                D["emit"]["appended"], D["emit"]["before"], D["emit"]["after"]))
    # ★ 2026-10-19：**跳过要说为什么**（原先只有个数，读起来像"11 条数据丢了"），
    #   并点明「台账 +N 是另一本账」—— 这两个数并排时读者最容易把它们相加。
    for _r in (_ing.get("skip_reasons") or [])[:3]:
        L.append("   · 跳过 %d 条：%s" % (_r["n"], _r["why"]))
    if len(_ing.get("skip_reasons") or []) > 3:
        L.append("   · 另有 %d 种原因（见 `kb/l8/runs/%s-L0-l0-ingest.json`）"
                 % (len(_ing["skip_reasons"]) - 3, D["base"]))
    _dec = _ing.get("declared_only_feishu") or {}
    if _dec.get("total") and _dec["total"] == _ing.get("skipped"):
        L.append("   · **%d = 声明数**（`l0-expected-diffs.yaml` %s）"
                 "⇒ **声明内的预期排除，不是漏抓**"
                 % (_ing["skipped"],
                    "、".join("%s expected %s" % (i["id"], i["expected"])
                              for i in _dec.get("items") or [])))
    L.append("   · 台账是 **reconcile 追加行**，与入库条数是**两本账**，别相加")
    L.append("")
    L.append("**分类覆盖**（库内 ｜ 本轮）")
    for f in D["five"]:
        # ★ 2026-10-09：理由**不能写死** —— "不在清单"只是其中一种；缺令牌是另一种。
        L.append("· **%s** %s 条 ｜ %s" % (
            f["label"], f["count"],
            "本轮已跑" if f["ran"] else ("⛔ 本轮未跑（%s）" % (f.get("why") or "不在日更 engine 清单"))))
    L.append("")
    ly = D["layers"]
    L.append("**各层**：%s%s%s%s" % (
        "、".join("%s✅" % x for x in ly["done"]) or "无",
        " ｜ 失败 %s" % "、".join(ly["bad"]) if ly["bad"] else "",
        " ｜ **无落章 %s**" % "、".join(ly["missing"]) if ly["missing"] else "",
        " ｜ ⚠️ **预演/自述 %s**（不判红，但**不算真执行**）" % "、".join(ly.get("preview") or [])
        if ly.get("preview") else ""))
    fr = D["fresh"]
    # ★ 2026-10-19：陈旧判词**逐条给全文**（原先截 40 字 ⇒「…而*」，原因全丢）。
    if fr.get("ok") is False:
        _pairs = fr.get("stale_pairs") or [{"layer": "-", "reason": s} for s in (fr.get("stale") or [])]
        L.append("**新鲜度**：⚠️ 陈旧 %d 层（判词**全文**逐条给）" % len(_pairs))
        for _p in _pairs:
            L.append("   · **%s**：%s" % (_p.get("layer"), _p.get("reason")))
    elif fr.get("ok"):
        L.append("**新鲜度**：✅ 不陈旧")
    else:
        L.append("**新鲜度**：（测不到：%s）" % (fr.get("error") or ""))
    if fr.get("threshold_h"):
        L.append("   = 逐层 L0–L7 比「最近一次成功 RUN 距今」≤ **%sh**（`layer_freshness.judge`）"
                 % fr["threshold_h"])
    if fr.get("oldest_layer"):
        L.append("   本次最旧：**%s %sh**" % (fr["oldest_layer"], fr["oldest_h"]))
    norun = [m for m in D["matrix"] if not m["in_daily"]]
    if norun:
        L.append("")
        L.append("⛔ **%s不跑这些类**（%d 类）：%s"
                 % (_kind or "本驱动", len(norun), "、".join(m["name"] for m in norun)))
        # ★ Owner 反馈②：「视频/文档/链接为什么不跑？」—— 原来只写"不在 engine 清单"，
        #   那是**机制名**，不是原因。这里把链条讲完：谁定的 → 缺了哪些脚本 → 后果是什么。
        # ★★ 2026-10-19：**`miss` 为空时不许再说「脚本没登记」**。第 ⑫ 类在 `CLASSES` 里
        #   就是 `scripts=[]`（兜底格，不是一类资源），原先这里照样打印「覆盖这几类的脚本
        #   没有被登记进那张清单」⇒ 与**同一份 md 摘要的结论相反**（md 写「没有『有脚本却
        #   没接进日更』的类」），而且连一个脚本名都列不出来 —— 读者被指向一个不存在的缺陷。
        _cnt = sum(m["count"] or 0 for m in norun)
        miss = sorted({s for m in norun for s in m["scripts"]})
        if miss:
            L.append("   原因：%s按 `kb/l7/registry/layers.yaml` 各层 `engine:` 清单执行；"
                     "覆盖这几类的脚本**没有被登记进那张清单** ⇒ **从来没被接进日更**。"
                     % (_kind or "本驱动"))
            L.append("   缺登记的脚本（%d 个）：%s" % (len(miss), "、".join(miss)))
        else:
            L.append("   原因：这几类**没有专属引擎脚本**，它本身不是一类资源（兜底格）⇒ "
                     "%s没有可跑的动作；**不是**「有脚本却没登记进清单」。" % (_kind or "本驱动"))
            L.append("   本轮这类在库内 **%d 条**%s。" % (
                _cnt, "（飞书侧也没有）⇒ 不跑它不影响任何数据" if _cnt == 0
                else "—— 仍在库里、仍可检索，只是日更不更新"))
        if _cnt > 0:
            L.append("   ⚠️ **数据没丢**：它们仍在库里、仍可检索；只是**%s不更新这几类**。"
                     "要更新得人工跑（或按下面「能不能接」的结论重新接线）。"
                     % (_kind or "本驱动"))
    L.append("")
    L.append("完整摘要：`kb/l8/runs/%s-digest.md`" % D["base"])
    return "\n".join(L)


# ══════════════════════════════════════════════════════════════════════════
#: 「一天只推一次」的落点（Owner 2026-10-10：「日更是一天一次…为什么一小时推一次」）
PUSH_STATE = "kb/.work/digest-pushed.json"


def _pushed_today(today):
    """今天已经**成功推过**没有 —— 返回 (是否推过, 记录)。

    ★ 为什么必须有这道守卫（2026-10-10 实测事故）：
      日更**不止 03:30 跑一次** —— `watch_review_readiness.py` 的**受控自愈**在新鲜度红时
      会 `launchctl kickstart -k` 再踢一次日更（冷却 45 分钟、**当日上限 3 次**）。
      实测 2026-10-10：`04:25 / 05:26 / 06:27` 各被踢一次 ⇒ 连同 03:30 那趟，
      **日更跑了 4 次**。而我把摘要推送接在驱动收尾、**没加去重** ⇒ **群里收到 4 条**。
      日更（对齐数据）**可以**重跑，但**推送必须一天只有一条**。
      ⇒ 按**日期**记「今天已推」；推**失败**不记账（后面那趟可以补推）。
    """
    try:
        d = json.load(io.open(PUSH_STATE, encoding="utf-8"))
    except Exception:                                         # noqa: BLE001
        return False, None
    return (d.get("date") == today), d


def _remember_push(today, base, chat):
    try:
        os.makedirs(os.path.dirname(PUSH_STATE), exist_ok=True)
        tmp = PUSH_STATE + ".tmp"
        with io.open(tmp, "w", encoding="utf-8") as fh:
            json.dump({"date": today, "base": base, "chat": chat,
                       "at": time.strftime("%Y-%m-%d %H:%M:%S")},
                      fh, ensure_ascii=False, indent=1)
        os.replace(tmp, PUSH_STATE)
    except Exception as e:                                    # noqa: BLE001
        print("[digest] ⚠️ 推送状态没落成（%r）—— 下一次可能重复推" % e)


def send(text, chat):
    """用**守衡自己的 bot 身份**推（与就绪巡检同一条通道、同一个落点）。

    bot 令牌与 user 令牌是两套 ⇒ user 掉了日更摘要照发。
    `KB_DIGEST_FORCE_SEND=1` 时**不真发**，只回报"本该发什么"（离线验正文）。

    ★★ 2026-10-16：**出站前必须摘掉 markdown 星号** —— 本函数是 KB 侧两条直发腿之一。
      它走 `lark-cli im +messages-send --text`，而飞书把 text 载荷按**纯文本**渲染
      ⇒ `**新增 13**` 里的星号**字面**进群。Owner 2026-10-14 定的规矩是
      「守衡的**所有**输出中不允许包含 `**` 星号」，当天的修复落在**守衡进程**的 5 个出口，
      判据 `tools/verify_outbound.py` 只看守衡台账 `PMO/logs/ws_outbound.jsonl`
      —— 本条腿**不在那 5 个出口里、也不进那份台账**（实测 `grep -c 日更报告` = 0），
      于是它一直是漏的。摘法 = `kb/l8/plaintext.py`（与守衡 `plain.mjs` 逐字互校）。
    """
    text, _n_star = plainify_for_send(text, where="daily_digest.send")
    _sendable, _why = guard(text, where="daily_digest.send")
    if not _sendable:
        return False, _why
    if os.environ.get("KB_DIGEST_FORCE_SEND") == "1":
        return True, "[自证] 未真发；正文 %d 字（已摘星号）" % len(text or "")
    if not os.path.exists(LARK):
        return False, "找不到 lark-cli（%s）" % LARK
    env = dict(os.environ, PATH=os.path.expanduser("~/.dsh/bin") + ":" + os.environ.get("PATH", ""))
    try:
        p = subprocess.run([LARK, "im", "+messages-send", "--as", "bot", "--profile", PROFILE,
                            "--chat-id", chat, "--text", text],
                           capture_output=True, text=True, timeout=90, env=env, errors="replace")
        return p.returncode == 0, (p.stdout or p.stderr or "").strip()[:300]
    except Exception as e:                                    # noqa: BLE001
        return False, repr(e)[:200]


def selftest() -> int:
    ok = fail = 0

    def chk(name, cond, extra=""):
        nonlocal ok, fail
        if cond:
            ok += 1
            print("  ✅ %s %s" % (name, extra))
        else:
            fail += 1
            print("  ❌ %s %s" % (name, extra))

    eng = _daily_engines()
    chk("① 能读到日更 engine 清单", isinstance(eng, set) and len(eng) > 0, "n=%d" % len(eng))
    # ★ 2026-10-09 晚：这条断言**反转**了 —— 原先它钉的是"阶段 5–8 不在清单里"（旧根因），
    #   而那几类当晚就接进去了。现在钉**新不变量**：该在的都在、该在外的都有明确理由。
    chk("①b 该接进清单的四类脚本**都在**（视频④ / 链接⑩⑪ / 文档核验⑤–⑨）",
        all(s in eng for s in ("fetch_video_bytes.py", "extract_video_keyframes.py",
                              "drill_links_2levels.py", "verify_l0_urls.py",
                              "verify_l0_nonrecord2.py")))
    chk("①b2 **故意仍在清单外**的仍在外（⑫ 无脚本 / 图片字节仅在新增时需要 / 重抓会连带动 L1-L2）",
        all(s not in eng for s in ("store_l0_attachments.py", "recrawl_all_urls.py",
                                   "refresh_l0_drifted.py")))
    chk("①c 清单里的脚本能认出来（对照片区）", "align_l0_feishu.py" in eng)
    chk("② 12 类编号连续 1..12", [c[0] for c in CLASSES] == list(range(1, 13)))
    # ★ ②b：这一节（「为什么这些类不在日更清单」）**只在真有孤儿脚本时才渲染** ——
    #   类⑫ 的 `scripts` 是空的，若还无条件渲染就会留个空 ``` 块 + 一段自相矛盾的解释。
    _orphan = [c[1] for c in CLASSES if c[3] and not any(s in eng for s in c[3])]
    chk("②b 「不在清单但仍有脚本」的孤儿类 = 0（有的话那一节才有内容）",
        not _orphan, "孤儿: %s" % (_orphan or "无"))
    # ★ ②c：`ROUND_EV` 是**硬编码产物名片段** —— 产物一改名就会恒判「未跑」（假红比漏报更坏）。
    #   所以逐条回**历史产物**核：每个片段必须至少在某一次真实运行的产物里出现过。
    _hist = sorted(os.path.basename(p) for p in glob.glob("kb/l8/runs/*.json"))
    _rot = sorted({f for f in ROUND_EV.values() if not any(f in p for p in _hist)})
    chk("②c `ROUND_EV` 的每个产物片段都能在历史产物里找到（产物改名即精确变红）",
        not _rot, "认不出的片段: %s ｜ 历史产物 %d 件" % (_rot or "无", len(_hist)))
    # ★ ②d：产物证据三态 —— 这是「清单在 ≠ 本轮跑过」的判据本体。
    chk("②d 产物证据三态：有产物=True／无产物=False／本类无判据=None（③ 图片故意无判据）",
        _round_evidence(["daily-X-L0-l0-url-verify.json"], 10) == (True, "l0-url-verify")
        and _round_evidence(["daily-X-digest.md"], 10) == (False, "l0-url-verify")
        and _round_evidence([], 3) == (None, None),
        "10→%s ／ 空→%s ／ 3→%s" % (_round_evidence(["x-l0-url-verify.json"], 10),
                                    _round_evidence([], 10), _round_evidence([], 3)))
    chk("③ 五类映射不重不漏（⑪ 是 ⑩ 的子集，**故意不含**；第 12 类「其它」不属五类）",
        sorted(n for _, ns in FIVE for n in ns) == [1, 3, 4, 5, 6, 7, 8, 9, 10])
    vs = _video_stats()
    chk("③c 视频口径分得开（个数 ≠ 段数）：段 ≥ 个数、帧 > 0",
        vs["videos"] > 0 and vs["ocr_segments"] >= vs["videos"] and vs["frames"] > 0,
        "视频 %d ／ 段 %d ／ 帧 %d ／ %d 字" % (vs["videos"], vs["ocr_segments"],
                                              vs["frames"], vs["ocr_chars"]))
    chk("③d 缺键写 `—` 不写 0", _v(None) == "—" and _v(0) == 0)
    chk("③b ⑪ 必须与 ⑩ 共用 url 台账但**单独一行**，否则双计",
        [c[2] for c in CLASSES if c[0] == 11] == ["url_external"])
    # ── ③e–③h：四态派生（2026-10-10 修「读不到」误报）────────────────────
    #   每条都用**逐字真实的台账字段形状**喂，不造假样本；③h 是反向对照。
    _gone = {"status": "gone", "sha256_state": "no_scope",
             "status_reason": "用户 2026-09-29 确认：该文件在飞书已不存在；API 侧 981003 互证，标 gone"}
    _badkey = {"status": "registered", "sha256_state": "not_fetched",
               "status_reason": "L0 资源键是当年抓取器的解析残留：把「材料链接」字段里的显示文本当成了 URL 主机名，并非真实链接。不重抓；标为坏键。"}
    _struct = {"status": "updated", "sha256_state": "structure_only",
               "status_reason": "非记录类核验：ok"}
    _memo = {"status": "audit_note", "sha256_state": None,
             "status_reason": "L0 台账 append-only 被破"}
    _ua = {"status": "blocked_by_ua_policy", "sha256_state": "not_fetched",
           "status_reason": "HTTP 403 —— 疑似反爬拦截，非页面失效"}
    _dns = {"status": "dns_fail", "sha256_state": "not_fetched",
            "status_reason": "DNS 解析失败"}
    _full = {"status": "registered", "sha256_state": "full"}
    chk("③e `gone`／坏键／结构核验**都不许落「读不到」**（否则误报成权限缺口）",
        not any(_row_state(r)[0].startswith("读不到")
                for r in (_gone, _badkey, _struct)),
        "｜".join(str(_row_state(r)) for r in (_gone, _badkey, _struct)))
    chk("③e2 三种情形各落**正确的四态**",
        _row_state(_gone)[0].startswith("不适用")
        and _row_state(_badkey)[0].startswith("不适用")
        and _row_state(_struct)[0] == "已对齐（结构核验）")
    chk("③f 审计备忘行**不进矩阵**（返回 None ⇒ 调用方剔除）",
        _row_state(_memo) == (None, "audit_note"))
    chk("③g **反向对照**：真读不到（反爬 403／DNS 失败）仍必须落「读不到」",
        _row_state(_ua)[0] == "读不到（blocked_by_ua_policy）"
        and _row_state(_dns)[0] == "读不到（dns_fail）",
        "把闸门拆成「什么都不报」会精确变红")
    chk("③g2 正常行（full）交给原逻辑 ⇒ `(None, None)`",
        _row_state(_full) == (None, None))
    # ★ 这两条是**被自己咬过之后**补的（2026-10-10 第一版判据过宽，实测咬出两类误标）：
    _parent_gone = {"status": "gone", "sha256_state": "full", "status_reason": "parent_gone"}
    # 逐字真实的两条（`_ledger_counts()` 上实测 326 ／ 10 条）：
    _superseded = {"status": "gone", "sha256_state": "full",
                   "status_reason": "飞书侧整批替换（原 record_id 在飞书返回 Record not found）；本地留档 kb/l0/_archive/正面和负面样本-superseded-2026092"}
    _rule_excluded = {"status": "gone", "sha256_state": "full",
                      "status_reason": "材料收集审核状态非「通过」：按用户指令③（只抓审核通过）不入 L0；文件已归档 kb/l0/_archive/材料收集-未通过-20260929-1045，仍在飞书表中"}
    _full_ok = {"status": "updated", "sha256_state": "full",
                "status_reason": "非记录类核验：ok"}
    chk("③i `gone` 的五种必须分开：只有「互证已不存在」⇒ 不适用；其余四种是**留档**⇒ 已对齐",
        _row_state(_parent_gone)[0].startswith("已对齐")
        and _row_state(_superseded)[0].startswith("已对齐")
        and _row_state(_rule_excluded)[0].startswith("已对齐")
        and _row_state(_gone)[0].startswith("不适用"),
        "｜".join("%s→%s" % (t, _row_state(r)[1])
                  for t, r in (("parent_gone", _parent_gone), ("整批替换", _superseded),
                               ("规则排除", _rule_excluded), ("互证", _gone))))
    chk("③j **反向对照**：`sha=full` 且 reason 含「非记录类核验：ok」的是正常行，"
        "不许判成结构核验/不可核",
        _row_state(_full_ok) == (None, None),
        "第一版不看 sha ⇒ 把 23 条正常行判成「标签不符」，会精确变红")
    # ★ ③k：**归口**也要有判据 —— ③e–③j 只测单行，第一版归口写 `else: unk` 时它们全绿，
    #   而摘要上却凭空多出「不可核（结构核验=2）」和「不可核（parent_gone=77）」两处告警。
    _st, _vd, _hd, _sf, _uk, _mm = _classify(
        [_full, _parent_gone, _struct, _badkey, _gone, _ua, _memo, _full_ok])
    _okv = sum(v for k, v in _vd.items() if k.startswith("已对齐"))
    chk("③k 归口：`已对齐（…）` 变体**绝不许**进「不可核」（写 `else: unk` 会精确变红）",
        _hd == {"blocked_by_ua_policy": 1} and not _uk and _okv == 4,
        "读不到=%s ／ 不可核=%s ／ 已对齐系=%d" % (_hd, _uk, _okv))
    chk("③k2 审计备忘被剔出计数（不进任何四态，单独回传）",
        len(_mm) == 1 and sum(_vd.values()) == 7,
        "备忘 %d ／ 计入四态 %d" % (len(_mm), sum(_vd.values())))
    # 与**活台账**对账：真读不到的行数必须**小**，且这四类一条都不许算进去
    _lat = _ledger_counts()[0]
    _hard = sum(1 for r in _lat if _row_state(r)[0] and _row_state(r)[0].startswith("读不到"))
    _gap = sum(1 for r in _lat if _row_state(r)[1] == "gone")
    chk("③h 活台账上「真读不到」只有个位数（当前实测 2 条）",
        _hard <= 9, "真读不到 %d 条 ／ 已不存在 %d 条" % (_hard, _gap))
    # ★ ③h2：**这条是本轮最该钉的** —— `status=gone` 一把抓会把 653 条留档行
    #   报成「飞书侧已不存在」（＝把自己的归档说成飞书侧事故）。留档 ≫ 真不存在。
    _allgone = sum(1 for r in _lat if str(r.get("status") or "") in _GONE)
    chk("③h2 留档**不许**被报成「飞书侧已不存在」：判成已存在的必须 ≪ status=gone 总数",
        _allgone > 100 and _gap <= 20 and _gap < _allgone / 10,
        "gone 总数 %d ／ 判成真·已不存在 %d ／ 留档 %d" % (_allgone, _gap, _allgone - _gap))
    # 正文必须带 Owner 点名的四个词，否则等于没答他的问题
    def _mkD(**over):
        """推文夹具（**逐字真实形状**）：只造 `render_push` 真正读的字段。"""
        d = {"base": "T", "at": "2026-01-01 00:00:00",
             "align": {"same": 1, "only_feishu": 2, "only_l0": 3,
                       "changed": 4, "pull_failed": 0},
             "ingest": {"written": 0, "skipped": 0, "archived": 0},
             "emit": {"appended": 0, "before": 0, "after": 0},
             "five": [{"label": x, "count": 0, "ran": False, "detail": ""}
                      for x in ("文案", "图片", "视频", "文档", "链接")],
             "matrix": [{"no": 1, "name": "n", "in_daily": False, "state": "x",
                         "count": 0, "note": "", "scripts": [], "kind": None}],
             "layers": {"done": [], "bad": [], "missing": []},
             "fresh": {"ok": True, "threshold_h": 24.0,
                       "oldest_layer": "L3", "oldest_h": 1.3}}
        d.update(over)
        return d

    txt = render_push(_mkD())
    for w in ("新增", "下架", "文案", "图片", "视频", "文档", "链接"):
        chk("④ 推文含「%s」" % w, w in txt)
    chk("④b 落点是**群**而不是私聊（Owner 2026-10-09 第二次口径）",
        DEFAULT_CHAT != P2P_CHAT and DEFAULT_CHAT == "oc_49a7cfb2861cffa4365ca8491f398d32",
        "群=%s" % DEFAULT_CHAT)
    # ── ④c–④f：出站正文的 markdown 星号（2026-10-16，Owner 当天报「下面的 `*` 没有去掉」）──
    #   两件事一起断：**收口真摘干净** ＋ **尺子不是恒真**（原文确实带星号）。
    #   为什么钉在这里：本脚本的两条直发腿走 `lark-cli --text`（纯文本渲染 ⇒ 星号字面显示），
    #   而守衡那次修复的 5 个出口与唯一判据（只看 `ws_outbound.jsonl`）**都够不着它**。
    chk("④c 推文正文**本来确实带** markdown 星号（否则下面那条就是恒真的）",
        has_md_symbols(txt), "星号 %d 个" % txt.count("*"))
    chk("④d 过收口之后**一个星号都没有**（`plainify()` 的四种写法都摘干净）",
        not has_md_symbols(plainify(txt)))
    chk("④e **反向对照**：没过收口的原文会被出站闸门拦下（拆掉收口 ⇒ 本条精确变红）",
        guard(txt, where="自证")[0] is False and guard(plainify(txt), where="自证")[0] is True)
    chk("④f 摘完版面没塌：内容仍在（摘的是标记，不是字）",
        all(w in plainify(txt) for w in ("记录层", "新增", "新鲜度")))
    # ④g ★ **接线**：光证明 `plainify()` 好用不算 —— 要证明 `send()` 那条路**真调了它**。
    #   做法同守衡侧「真发一次（网络打桩）」：把 `subprocess.run` 换掉，看它**准备发什么**。
    #   删掉 `send()` 里那行收口 ⇒ 本条**精确变红**（前四条都拦不住 —— 它们只测纯函数）。
    _seen = {}

    class _Fake:
        returncode, stdout, stderr = 0, "{}", ""

    _real_run = subprocess.run
    _saved_force = os.environ.pop("KB_DIGEST_FORCE_SEND", None)
    try:
        subprocess.run = lambda argv, **kw: (_seen.setdefault("argv", argv), _Fake())[1]
        _ok_send, _ = send("**新增 13** ｜ **下架 0**", "oc_自证")
    finally:
        subprocess.run = _real_run
        if _saved_force is not None:
            os.environ["KB_DIGEST_FORCE_SEND"] = _saved_force
    _sent = (_seen.get("argv") or [""])[-1]
    chk("④g **接线**：`send()` 真发的那份正文里一个星号都没有（删掉收口 ⇒ 本条精确变红）",
        _ok_send and "*" not in _sent and "新增 13" in _sent, "实发：%r" % _sent[:50])
    chk("⑤ 自证档不真发", send("x", "c")[1].startswith("[自证]")
        if os.environ.get("KB_DIGEST_FORCE_SEND") == "1" else True, "(需 KB_DIGEST_FORCE_SEND=1 才验)")
    # ── ⑥ 展示层三条（2026-10-19 修；每条都配反向对照）──────────────────────────
    #  为什么钉这三条：10-19 那张周报上 —— ① 陈旧判词被切成「…而*」（真原因全丢）；
    #  ② 把一个 `scripts=[]` 的兜底格说成「脚本没登记进清单」（与同一份 md 摘要**结论相反**）；
    #  ③ 标题写死「日更」而排期是周更，且没写这一趟是补跑。三条都是**读者直接看到的话**。
    _long = ("8 天 内跑过，但 `change_state=no_new_input` 而**上游水位已变**"
             "（落章 l6/registry/l6.json:945:26178 ≠ 现状 l6/registry/l6.json:945:26182）"
             "⇒ **判陈旧**（防假绿：不许自证）；上游最新改动 10:42:25 **晚于**本层运行 17:39:28")
    # ★ ⑥a 必须走**真链**：截断在 `_freshness_summary()` 里（`[:40]`），**不在** `render_push()`。
    #   夹具直接塞 `stale_pairs` 只能证到渲染层 —— 实测过：那样把 `[:40]` 加回去**照样全绿**。
    #   ⇒ 这里把 `layer_freshness.judge` 打桩成「L7 陈旧 + 一条完整判词」，整条链一起验。
    try:
        import layer_freshness as _lf
        _real_judge = _lf.judge

        def _fake_judge(kb_root, layer, now=None):
            if layer == "L7":
                return {"fresh": False, "reason": _long, "run_age": 300.0}
            return {"fresh": True, "reason": "ok", "run_age": 300.0}

        try:
            _lf.judge = _fake_judge
            _fr_stale = _freshness_summary()
            _stale_txt = render_push(_mkD(fresh=_fr_stale))
        finally:
            _lf.judge = _real_judge
        _got = ((_fr_stale.get("stale_pairs") or [{}])[0] or {}).get("reason") or ""
        chk("⑥a 陈旧判词**原样进正文**（`_freshness_summary` 里把判词截成 40 字 ⇒ 本条精确变红）",
            "上游水位已变" in _stale_txt and "17:39:28" in _stale_txt and _got == _long,
            "判词 %d 字 → 摘要里 %d 字" % (len(_long), len(_got)))
    except Exception as _e:                                   # noqa: BLE001
        chk("⑥a 陈旧判词原样进正文", False, "打桩失败：%r" % (_e,))
    _norun_empty = render_push(_mkD(matrix=[
        {"no": 12, "name": "其它附件 / 未知类型", "in_daily": False, "state": "x",
         "count": 0, "note": "", "scripts": [], "kind": None}]))
    _norun_orphan = render_push(_mkD(matrix=[
        {"no": 10, "name": "某类", "in_daily": False, "state": "x",
         "count": 5, "note": "", "scripts": ["orphan.py"], "kind": None}]))
    chk("⑥b 兜底格（`scripts=[]`）**不许**被说成「脚本没登记进清单」"
        "（它与同一份 md 摘要的结论相反）",
        "没有被登记进那张清单" not in _norun_empty and "兜底格" in _norun_empty,
        "该段：%r" % _norun_empty.split("⛔")[-1][:48].replace("\n", " "))
    chk("⑥b2 **反向对照**：真有孤儿脚本时，仍必须说「没登记」并把脚本名列出",
        "没有被登记进那张清单" in _norun_orphan and "orphan.py" in _norun_orphan)
    _sched_w = {"kind": "周更", "human": "每周日 03:30", "is_slot": False,
                "base_at": "2026-10-19 10:03", "plist": "x.plist",
                "prev_slot": "`daily-20261018-0330` → **停在 L0 闸门红：exit=1**", "why": ""}
    _t_week = render_push(_mkD(schedule=_sched_w))
    _t_slot = render_push(_mkD(schedule=dict(_sched_w, is_slot=True)))
    _t_daily = render_push(_mkD(schedule=dict(_sched_w, kind="日更", human="每天 03:30")))
    chk("⑥c 标题周期词**跟排期走**（写死「日更」⇒ 本条精确变红）",
        "（周更报告）" in _t_week and "（日更报告）" not in _t_week
        and "（日更报告）" in _t_daily)
    chk("⑥d 不在排期时刻写「补跑」／在排期时刻写「排期那一趟」，并带上一次排期趟的结果",
        "补跑" in _t_week and "排期那一趟" in _t_slot
        and "上一次排期趟" in _t_week and "停在 L0 闸门红" in _t_week)
    _t_unknown = render_push(_mkD(schedule={"why": "读不到排期（x）"}))
    chk("⑥e 排期读不到时**不写周期词**、也不假装比对过（不许 fail-open）",
        "（报告）" in _t_unknown and "读不到" in _t_unknown
        and "周更报告" not in _t_unknown)
    # ★ ⑥f 接**真库**：排期解析必须与 plist 的 `Weekday` 一致，且比对得出**三态之一**。
    #   不写死「必须有 Weekday」—— 排期从周更改回每天是合法改动，硬断言会把正确改动判成故障。
    _sf = _schedule_fact("daily-20261019-1003")
    _spec = (_sf or {}).get("spec") or {}
    chk("⑥f 真库：排期读得到、周期词与 plist 一致、本趟与排期的比对落三态之一",
        bool(_spec) and _sf.get("kind") is not None and _sf.get("is_slot") in (True, False),
        "kind=%r ｜ %r ｜ is_slot=%r ｜ weekdays=%r"
        % (_sf.get("kind"), _sf.get("human"), _sf.get("is_slot"), _spec.get("weekdays")))
    # ── ⑦ 入库说清「为什么跳过」＋ 预演档**报黄**（2026-10-19 第二批，Owner 同意做 C1/C2/D1）──
    #   钉的是两件「读者会读错」的事：① 退出码 0 的预演档被并进 `✅`；
    #   ② 「跳过 11」只有一个数，读者以为是数据丢了。
    _lc_prev = render_push(_mkD(layers={"done": ["L0", "L6"], "bad": [], "missing": [],
                                        "preview": ["L7"]}))
    chk("⑦a 预演/自述的层**报黄**，不许并进 ✅（把它放回 done ⇒ 本条精确变红）",
        "预演/自述 L7" in _lc_prev and "L7✅" not in _lc_prev,
        next((x for x in _lc_prev.splitlines() if "各层" in x), ""))
    _ing_fx = {"written": 0, "skipped": 3, "archived": 0,
               "skip_reasons": [{"why": "准入未过：材料审核状态=[] != [\"通过\"]", "n": 3}],
               "declared_only_feishu": {"total": 3, "items": [{"id": "EX-1",
                                       "table": "材料收集", "expected": 3}]}}
    _t_ing = render_push(_mkD(ingest=_ing_fx))
    chk("⑦b 跳过**说得出原因**，且「跳过数 = 声明数」时说「不是漏抓」、并点明两本账",
        "材料审核状态" in _t_ing and "不是漏抓" in _t_ing and "两本账" in _t_ing)
    chk("⑦b2 **反向对照**：跳过数 ≠ 声明数时**不许**说「声明内的预期排除」",
        "不是漏抓" not in render_push(_mkD(ingest=dict(
            _ing_fx, skipped=2,
            declared_only_feishu={"total": 3, "items": [{"id": "EX-1", "expected": 3}]}))))
    chk("⑦c 回执缺 `skipped` 明细／缺声明 ⇒ 不崩、也不贴「声明内」",
        "不是漏抓" not in render_push(_mkD()))
    chk("⑦d `_skip_reasons()` 分组正确；缺件回空表（**缺回执 ≠ 有 0 条跳过**）",
        _skip_reasons(None) == [] and _skip_reasons(
            {"skipped": [{"why": "a"}, {"why": "a"}, {"why": "b"}]}) == [
            {"why": "a", "n": 2}, {"why": "b", "n": 1}])
    _dec_real = _declared_only_feishu()
    chk("⑦e 真库：EX 声明读得到（走 `l0_gate.load_yaml` 的同一个读取器，不抄第二份解析）",
        isinstance(_dec_real, dict) and (_dec_real.get("total") or 0) > 0,
        "only_feishu 声明合计=%s" % ((_dec_real or {}).get("total"),))
    # ★ ⑦a2/⑦a3/⑦f 走**真链**：⑦a 只证渲染层，改坏 `_split_layers()` 或
    #   `_layer_stamps()` 的 verdict 解析它照样绿 —— 这三条把它们接上。
    _spl = _split_layers({"L0": {"exit": 0, "preview": False},
                          "L7": {"exit": 0, "preview": True, "verdict": "全走完（预演 · 未落盘 · 非执行证据）"},
                          "L6": None,
                          "L5": {"exit": 2, "preview": False}})
    chk("⑦a2 切分：预演档进 `preview` 不进 `done`；缺落章进 missing、非零退出进 bad",
        _spl["preview"] == ["L7"] and "L7" not in _spl["done"]
        and _spl["missing"] == ["L6"] and _spl["bad"] == ["L5(exit=2)"],
        "done=%s preview=%s missing=%s bad=%s"
        % (_spl["done"], _spl["preview"], _spl["missing"], _spl["bad"]))
    _Db = build("daily-20261019-1003")          # 真库一次，供 ⑦a3 与 ⑦f 共用
    _v7 = (_Db["stamps"] or {}).get("L7") or {}
    chk("⑦a3 真库：L7 落章被认成**预演/自述**（拆掉 verdict 解析 ⇒ 本条精确变红）",
        _v7.get("preview") is True and "预演" in (_v7.get("verdict") or ""),
        "verdict=%r" % ((_v7 or {}).get("verdict"),))
    _sr = _Db["ingest"].get("skip_reasons") or []
    chk("⑦f 真库：跳过的原因**确实从入库回执并进了摘要**（拆掉那步接线 ⇒ 本条变红）",
        bool(_sr) and sum(r["n"] for r in _sr) == _Db["ingest"]["skipped"],
        "原因组 %d ｜ 合计 %s ｜ 跳过 %s"
        % (len(_sr), sum(r["n"] for r in _sr), _Db["ingest"]["skipped"]))
    print("\n自证：通过 %d / 失败 %d" % (ok, fail))
    return 0 if fail == 0 else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="日更摘要：出 md + 推飞书私聊")
    ap.add_argument("base", nargs="?")
    ap.add_argument("--push", action="store_true", help="推飞书（**默认不推**）")
    ap.add_argument("--chat", default=os.environ.get("KB_DIGEST_CHAT") or DEFAULT_CHAT)
    ap.add_argument("--force", action="store_true",
                    help="今天已推过也再推一次（**调试用**；正式日更不要加）")
    ap.add_argument("--print-push", dest="print_push", action="store_true",
                    help="只读：打印真会发出去的正文（已摘星号），**不写 md、不推送**")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    if not a.base:
        print("用法：daily_digest.py <BASE> [--push] [--chat <id>]")
        return 2

    # ★ 只读档：给人（与判据）看「这一轮真要发出去的那份正文」，**不写 md、不真发**。
    if a.print_push:
        txt, n = plainify_for_send(render_push(build(a.base)), where="--print-push")
        print(txt)
        print("\n[digest] 摘掉 %d 个星号 ｜ 出站正文仍有星号：%s"
              % (n, has_md_symbols(txt)))
        return 0 if not has_md_symbols(txt) else 1

    D = build(a.base)
    md = render_md(D)
    out = "kb/l8/runs/%s-digest.md" % a.base
    sys.path.insert(0, os.path.join("kb", ".work"))
    import _safe_write as sw
    sw.write_text(out, md)                                    # .md 只许走安全写盘通道
    print("[digest] 已出 %s（%d 字）" % (out, len(md)))

    A = D["align"]
    print("[digest] 记录层：一致 %s ｜ 新增 %s ｜ 下架 %s ｜ 值变 %s"
          % (A.get("same"), A.get("only_feishu"), A.get("only_l0"), A.get("changed")))
    for f in D["five"]:
        # ★ 2026-10-10：理由**不许写死**（推文/md 早改了，这句漏了）—— 与它们同源。
        print("   %s %s 条 ｜ %s" % (
            f["label"], f["count"],
            "本轮已跑" if f["ran"] else ("本轮未跑（%s）" % (f.get("why") or "不在日更清单"))))
    if not a.push:
        print("[digest] **未推送**（加 --push 才推）")
        return 0

    # ★ 一天只成功推一次（日更会被受控自愈反复踢，但推送不许跟着反复发）
    today = time.strftime("%Y-%m-%d")
    already, rec = _pushed_today(today)
    if already and not a.force:
        print("[digest] ⏭ **今天已推过，不再推**（%s ｜ BASE=%s ｜ %s）"
              % (today, (rec or {}).get("base"), (rec or {}).get("at")))
        print("        日更可以被自愈反复踢，但**推送一天只发一条**；")
        print("        要强制再推：`--force`（调试用，别在正式日更里加）。")
        return 0

    txt = render_push(D)
    ok, why = send(txt, a.chat)
    print("[digest] 推送 %s → %s ｜ %s" % ("✅" if ok else "❌", a.chat, why[:160]))
    if ok:
        _remember_push(today, a.base, a.chat)
    return 0 if ok else 4


if __name__ == "__main__":
    sys.exit(main())
