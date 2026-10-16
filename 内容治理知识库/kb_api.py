#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DSH 内容治理知识库 · 内网只读 API
包住现成的 l5/matcher.py（P0 确定性匹配）与 l6/retriever.py（BM25+向量召回），
以及 l4/canonical（1,242 条带永久条款号的定稿层），对外提供只读查询。

启动：
    python3 -m uvicorn kb_api:app --host 0.0.0.0 --port 8787
文档（可视化平台）：
    http://<本机IP>:8787/docs
"""
import os
import sys
import json
import glob
import time
from typing import Optional

from fastapi import FastAPI, HTTPException, Header, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# ---------------------------------------------------------------- 配置
KB = os.environ.get(
    "KB_ROOT",
    "/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理/kb",
)
TOKEN = os.environ.get("KB_API_TOKEN", "dsh-kb-dev-token")

# 必须在 import retriever/matcher **之前**置位（2026-09-30 实测踩到）：
# 这两个模块带**导入期**解释器守卫 —— 它比 realpath(sys.executable) 与 kb/.kb-python 里写的
# `/usr/bin/python3`，而本机 sys.executable 实际是
# /Library/Developer/CommandLineTools/usr/bin/python3（两者 realpath 不等），
# 于是守卫会 os.execve 成 `python3 <retriever.py> <本进程 argv>` —— uvicorn 的参数
# （kb_api:app --host … --port …）被当成 retriever 自己的参数 → argparse 报错、服务起不来。
# 本服务由 plist 固定用 /usr/bin/python3 启动（就是合格解释器），故这里直接断言，跳过守卫。
os.environ.setdefault("KB_INTERP_OK", "1")

sys.path.insert(0, os.path.join(KB, "l6"))
sys.path.insert(0, os.path.join(KB, "l5"))

import retriever  # noqa: E402
import matcher    # noqa: E402

# ---------------------------------------------------------------- 启动加载
START = time.time()

#: ★ 批次19 · 第1块：fail-closed 前置判据（**与 agent/skill 入口共用同一份**）。
#: 同一判据写两遍必然分叉 —— 本库已因「同一判据算两遍」返工多次。
_GATE_MOD = None


def _freshness_gate():
    """加载 `kb/l7/scripts/review_freshness_gate.py`（判据唯一实现处）。"""
    global _GATE_MOD
    if _GATE_MOD is None:
        import importlib.util
        p = os.path.join(KB, "l7", "scripts", "review_freshness_gate.py")
        if not os.path.exists(p):
            raise RuntimeError("前置判据不在位：%s" % p)
        spec = importlib.util.spec_from_file_location("review_freshness_gate", p)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _GATE_MOD = mod
    return _GATE_MOD


def _KBRoot():
    """判据要的是**库根**（含 kb/ 的那一层），不是 KB 本身。"""
    return os.path.dirname(os.path.abspath(KB))


def _load_canonical():
    """把 l4/canonical/*.jsonl 按 article_no 建索引。"""
    idx = {}
    counts = {}
    for path in sorted(glob.glob(os.path.join(KB, "l4", "canonical", "*.jsonl"))):
        form = os.path.splitext(os.path.basename(path))[0]
        n = 0
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                n += 1
                art = rec.get("article_no")
                if art:
                    idx[art] = rec
        counts[form] = n
    return idx, counts


CANONICAL, CANON_COUNTS = _load_canonical()
RULES = matcher.compile_patterns() if hasattr(matcher, "compile_patterns") else None

# ---------------------------------------------------------------- 应用
app = FastAPI(
    title="DSH 内容治理知识库 API",
    description=(
        "只读查询 DSH 内容治理知识库（分层库 L0–L7）。\n\n"
        "- `/match` P0 确定性匹配（词表/正则/变体，毫秒级）\n"
        "- `/search` 规则与单元检索（BM25 为主，向量可选）\n"
        "- `/rule/{article_no}` 按永久条款号取定稿记录\n"
        "- 所有返回都带引用契约四件套：**条款号 + 锚点 + source_sha256 + 逐字摘录**\n"
    ),
    version="0.1.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def auth(authorization: Optional[str] = Header(default=None)):
    if TOKEN and authorization != "Bearer " + TOKEN:
        raise HTTPException(status_code=401, detail="unauthorized: need 'Authorization: Bearer <token>'")
    return True


# ---------------------------------------------------------------- 模型
class MatchReq(BaseModel):
    text: str = Field(..., description="待审文本（逐行匹配）")
    include_rules: bool = Field(False, description="true 时额外返回每条命中的规则全文")


class SearchReq(BaseModel):
    query: str = Field(..., description="查询词")
    top: int = Field(5, ge=1, le=50, description="返回条数")
    mode: str = Field("bm25_only", description="bm25_only | hybrid | vector_only | auto")
    lang: str = Field("auto", description="auto | zh | en")
    kb_type: Optional[str] = Field(None, description="wording | internal_sample | external_standard | product_desc")


# ---------------------------------------------------------------- 端点
@app.get("/health", summary="健康检查 + 库版本（无需 token，便于连通性测试）")
def health():
    return {
        "ok": True,
        "service": "dsh-kb-api",
        "uptime_sec": round(time.time() - START, 1),
        "canonical_total": sum(CANON_COUNTS.values()),
        "canonical_by_form": CANON_COUNTS,
        "patterns_loaded": len(RULES) if RULES is not None else None,
        "search_modes": ["bm25_only", "hybrid", "vector_only", "auto"],
        "auth": "Bearer token" if TOKEN else "off",
    }


@app.post("/match", summary="P0 确定性匹配（命中即 BLOCK 候选）")
def do_match(req: MatchReq, authorization: Optional[str] = Header(default=None)):
    auth(authorization)
    hits = matcher.match(req.text, RULES) if RULES is not None else matcher.match(req.text)
    out = []
    for h in hits or []:
        item = {
            "rule_code": h.get("rule_code"),
            "rule_id": h.get("rule_id"),
            "level": h.get("level"),
            "verdict": h.get("match_note"),
            "matched": h.get("matched"),
            "matched_count": h.get("matched_count"),
            "lines": h.get("lines"),
            "anchor": h.get("anchor"),
            "source_sha256": h.get("source_sha256"),
            "suggested_replacement": h.get("suggested_replacement"),
        }
        if req.include_rules:
            item["rule"] = _find_rule_by_code(h.get("rule_code"))
        out.append(item)
    return {"ok": True, "hit_count": len(out), "hits": out}


@app.post("/search", summary="规则与单元检索（BM25 主 / 向量补）")
def do_search(req: SearchReq, authorization: Optional[str] = Header(default=None)):
    auth(authorization)
    try:
        res = retriever.search(
            req.query, top=req.top, mode=req.mode, lang=req.lang, kb_type=req.kb_type
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail="search failed: %s" % exc)
    return {"ok": True, **res}


@app.get("/rule/{article_no}", summary="按永久条款号取定稿记录")
def get_rule(article_no: str, authorization: Optional[str] = Header(default=None)):
    auth(authorization)
    rec = CANONICAL.get(article_no)
    if not rec:
        raise HTTPException(status_code=404, detail="查不到条款号 %s" % article_no)
    return {"ok": True, "article_no": article_no, "record": rec}


@app.get("/rule", summary="列条款号（按形态筛选，最多 200 条）")
def list_rules(
    form: Optional[str] = Query(None, description="wording_entry | wording_revision_pair | sample_case | scoped_clause"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    authorization: Optional[str] = Header(default=None),
):
    auth(authorization)
    items = []
    for art, rec in CANONICAL.items():
        if form and rec.get("form") != form and rec.get("kb_type") != form:
            continue
        items.append(art)
    items.sort()
    return {
        "ok": True,
        "total": len(items),
        "offset": offset,
        "limit": limit,
        "article_nos": items[offset : offset + limit],
    }


# ---------------------------------------------------------------- 评审链（2026-09-30 加）
# 守衡（飞书侧 dsh-kb 应用）原来只能"查"（/match /search /rule），没有"评"。
# 这一组路由把已经跑通的评审链暴露出来：依据（P0 + 509 条措辞表达库 + BM25）
# → 裁决（review_engine.decide()）→ 三态结论 + 逐条六要素。
# **确定性内核，不经过 agent** —— 守衡是 bot，调不了 skill，也不需要调：
# skill 是给 agent 的入口，这条 API 是给机器的入口，两者背后是同一套引擎。
import importlib.util  # noqa: E402

REVIEW_ADAPTER = os.path.join(KB, "l7", "review-engine", "core", "with_kb_evidence.py")
_ADAPTER = None


def _adapter():
    """按路径加载适配器（`review-engine` 带连字符，不能当包名 import）。"""
    global _ADAPTER
    if _ADAPTER is None:
        if not os.path.exists(REVIEW_ADAPTER):
            raise HTTPException(503, "适配器不在位：%s" % REVIEW_ADAPTER)
        spec = importlib.util.spec_from_file_location("with_kb_evidence", REVIEW_ADAPTER)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)          # 它自己会把 core/ 加进 sys.path
        _ADAPTER = mod
    return _ADAPTER


class ReviewReq(BaseModel):
    text: str = Field(..., min_length=1, max_length=20000, description="待审文字内容")
    content_id: Optional[str] = Field(default=None, description="留空则自动生成 `AUTO-<text 的 sha256 前 12 位>`（与飞书发布件同一规则；2026-10-03 统一，此前是 `text-` 前缀）")
    channel: str = Field(default="", description="Amazon / TikTok / 独立站 …（可空）")
    product_line: str = Field(default="", description="品线（可空）")
    product_line_seed: str = Field(default="", description="给 5 条种子规则扫描器的词表原样值，如「吸奶器」")
    layer_preflight_base: Optional[str] = Field(
        default=None,
        description="（2026-10-03 加）agent 侧层前置的 BASE（如 20261003-0654）。传了 ⇒ 本接口按 "
                    "`skill_invocation_audit.py` 逐层核 <BASE>-L{4,5,6,7}（2026-10-03 起含 L7），任一层红 ⇒ HTTP 409 / "
                    "NEEDS_INPUT，不出结论。不传 ⇒ 结论里记 `layer_preflight.mode=waived_by_api`"
                    "（**未经层前置**这件事必须可见）")
    sku: Optional[str] = None
    decision_owner: Optional[str] = Field(
        default=None,
        description="（2026-10-03 加，防线2）**判定主体**：本单由哪个专项 skill 下判，"
                    "**填装载目录名（中文）**，如 `文案合规审查` / `图片安全审查`"
                    "（英文 `brand-*` 是 registry 侧别名，见 routes.yaml 的 dir_name_map，别填）。"
                    "★ 本接口**核不了它有没有被真的加载**（bot 加载不了 skill）——"
                    "能做的只有两件，两件都必须可见：① 调用方申报 → 记 `mode=declared_by_api`；"
                    "② 不申报 → 记 `mode=absent_by_api`，**该结论不得当通过依据**。"
                    "★ 与 `layer_preflight_base` 必须**成对**：只见 BASE 不见判定主体 ⇒ "
                    "HTTP 409（跑完了层前置却不知道谁判，那是自相矛盾）。")
    allow_no_decision_owner: bool = Field(
        default=False,
        description="显式声明「本跑不记判定主体」—— 只有这样才允许只带 BASE 不带 decision_owner；"
                    "结论里会记 `decision_owner.mode=waived_by_api`（缺判定主体必须可见，不许静默）")


@app.post("/review", summary="评审链：依据 + 三态裁决（带条款号/锚点/source_sha256/逐字摘录）")
def do_review(req: ReviewReq, authorization: Optional[str] = Header(default=None)):
    """跑评审链，返回 PASS / REVIEW / BLOCK / NEEDS_INPUT + 逐条依据。

    - **依据**：P0 确定性匹配 + 509 条措辞表达库规则 + BM25（组件 = kb-content-review）
    - **裁决**：review_engine.decide()（决策序 NEEDS_INPUT > BLOCK > REVIEW > PASS）
    - 同一 text 的 `content_version` 稳定（= sha256），可用于幂等/去重
    - `confidence` 是**启发式**（引擎自述「未做金标标定」），不得当成法律合规概率
    """
    auth(authorization)

    # ══════════════════════════════════════════════════════════════════════════
    # ★★ 批次19 · 第1块：**fail-closed 前置（API 入口）** ────────────────────────
    # 与 agent/skill 入口（`kb-content-review/scripts/review.py main()`）调**同一份判据**
    # （`kb/l7/scripts/review_freshness_gate.py`）。
    # 判据不通过 ⇒ **HTTP 409 + state=NEEDS_INPUT，不产出 PASS/BLOCK**。
    # 为什么用 409 而不是 200：让调用方**在协议层**就知道这不是一个结论 ——
    # 200 会被上游当结论直接吞掉，那就等于没拦住。
    _fg = None
    try:
        _fg = _freshness_gate()
        _ok, _ginfo = _fg.check(_KBRoot())
    except Exception as exc:                      # noqa: BLE001
        # ★ fail-closed：判据跑不起来也算**不通过**（「不知道新不新鲜」≠「新鲜」）
        _ok, _ginfo = False, {"reason": "前置判据跑不起来：%r" % (exc,),
                              "unreadable": True, "stale": [],
                              "stale_artifacts": {}, "stale_layers": []}
    if not _ok:
        _ref = (_fg.refusal_payload(_ginfo) if _fg else
                {"state": "NEEDS_INPUT", "detail": _ginfo.get("reason"),
                 "fails_closed": True, "stale": [], "stale_layers": []})
        _ref["confidence"] = None
        _ref["items"] = []
        _ref["coverage"] = {"text": "not_evaluated", "image": "not_applicable",
                            "video": "not_applicable",
                            "why": "供给链不新鲜 ⇒ 未评审（fail-closed）"}
        _ref["gate"] = {"file": "kb/l7/scripts/review_freshness_gate.py",
                        "called_from": "kb_api.py do_review()", "verdict": "refused"}
        raise HTTPException(409, detail=_ref)

    # ══════════════════════════════════════════════════════════════════════════
    # ★ 层前置（API 入口，2026-10-03 加）：**与 agent 入口同一份判据**
    #   （`kb/l7/scripts/skill_invocation_audit.py` —— 不新造尺子）。
    # bot 加载不了 skill ⇒ 它**自己做不到**层前置；能做的只有两件，且两件都必须可见：
    #   ① 调用方把 agent 侧跑过的 BASE 传进来 → 这里**照核**；红 ⇒ 409，不出结论
    #   ② 没传 → 结论里记 `mode=waived_by_api`（**缺前置不许静默**）
    # ══════════════════════════════════════════════════════════════════════════
    _pf = None
    if req.layer_preflight_base:
        _pf = _adapter().layer_preflight(req.layer_preflight_base)
        if not _pf.get("ok"):
            _need = [L for L, r in _pf["details"].items() if not r["pass"]]
            _pref = {"state": "NEEDS_INPUT", "fails_closed": True,
                     "detail": "层前置未过：%s" % "、".join(_need),
                     "layer_preflight": _pf, "items": [], "confidence": None,
                     "coverage": {"text": "not_evaluated",
                                  "why": "层前置未过 ⇒ 未评审（fail-closed）"},
                     "gate": {"file": "kb/l7/scripts/skill_invocation_audit.py",
                              "called_from": "kb_api.py do_review()", "verdict": "refused"}}
            raise HTTPException(409, detail=_pref)
    else:
        _pf = {"base": None, "ok": True, "red_total": 0, "mode": "waived_by_api", "details": {},
               "reason": "请求未带 layer_preflight_base；bot 加载不了 skill ⇒ 本结论未经层前置"}

    # ★ 防线2（API 入口，2026-10-03 加）：**判定主体**，与层前置**同强度**、成对使用。
    #   为什么 API 侧也要有：CLI 侧已把「判定主体缺席」挡成 NEEDS_INPUT（`with_kb_evidence.py
    #   --decision-owner`），而机器入口原先**只有层前置**（实测 `grep -c decision_owner kb_api.py` = 0）
    #   ⇒ bot 那条路的结论**绕过判定主体这道防线**。
    #   三层口径（都不许静默）：
    #     ① 申报了 → `mode=declared_by_api`（**但本接口核不了它有没有真被加载** —— bot 加载不了 skill）
    #     ② 显式豁免 → `mode=waived_by_api`
    #     ③ 带了 BASE 却**没申报也没豁免** → **HTTP 409**：跑完了层前置却不知道谁判，是自相矛盾
    if req.decision_owner:
        _do = {"skill": req.decision_owner, "mode": "declared_by_api",
               "declared_by": "api_caller",
               "cannot_verify": "本接口核不了该 skill 有没有被真的加载（bot 加载不了 skill）"
                                "⇒ 这是**申报**，不是观测"}
    elif req.allow_no_decision_owner:
        _do = {"skill": None, "mode": "waived_by_api",
               "reason": "调用方显式豁免（allow_no_decision_owner=true）"}
    elif req.layer_preflight_base:
        _dref = {"state": "NEEDS_INPUT", "fails_closed": True,
                 "detail": ("判定主体缺失：带了 layer_preflight_base=%s（= 跑完了层前置）"
                            "却没给 decision_owner —— 跑完层前置却不知道谁判，是自相矛盾。"
                            "请传 decision_owner（装载目录名，如 文案合规审查），"
                            "或显式 allow_no_decision_owner=true 留痕豁免。"
                            % req.layer_preflight_base),
                 "layer_preflight": _pf,
                 "decision_owner": {"skill": None, "mode": "absent_by_api"},
                 "items": [], "confidence": None,
                 "coverage": {"text": "not_evaluated",
                              "why": "判定主体缺失 ⇒ 未评审（fail-closed）"},
                 "gate": {"file": "kb/l7/review-engine/core/with_kb_evidence.py（CLI 侧同一把尺子）",
                          "called_from": "kb_api.py do_review()", "verdict": "refused"}}
        raise HTTPException(409, detail=_dref)
    else:
        _do = {"skill": None, "mode": "absent_by_api",
               "reason": "既没传 decision_owner、也没传 layer_preflight_base ⇒ 两条防线都没走；"
                         "**本结论不得当通过依据**"}

    try:
        # write_report=True：每次 API 调用都留一份报告（审计痕迹），
        # 且报告必须走 node 明文通道（python 写 .md 会变信封态，宿主读不到）
        res, err = _adapter().run(req.text, content_id=req.content_id, channel=req.channel,
                                  product_line=req.product_line,
                                  product_line_seed=req.product_line_seed, write_report=True)
    except HTTPException:
        raise
    except Exception as exc:                   # noqa: BLE001
        raise HTTPException(500, "review failed: %s" % exc)
    if res is None:
        raise HTTPException(503, "依据组件不可用：%s" % err)

    d = res["decision"]
    meta = res.get("evidence_meta") or {}
    items = []
    for it in (d.get("risk_items") or []):
        ev = it.get("evidence") or {}
        items.append({
            "risk_type": it.get("risk_type"), "priority_tier": it.get("priority_tier"),
            "action": it.get("action"), "status": it.get("status"),
            "location": it.get("location"), "original_text": it.get("original_text"),
            "reason": it.get("reason"), "suggestion": it.get("suggestion"),
            "library": ev.get("library"), "article_no": ev.get("article_no"),
            "anchor": ev.get("anchor"), "source_sha256": ev.get("source_sha256"),
            "excerpt": ev.get("excerpt"),
            "evidence_complete": it.get("evidence_complete"),
            # ★ 2026-10-12（与 issue_count 拆分同批）：**逐条**带上「是不是非权威候选」的声明。
            #   为什么：`rule_engine.scan_text()` 的候选在源里自己写着 `authoritative: false`
            #   （已被 kb/l3 取代），但本接口原先**把它整条抹平** ⇒ 调用方拿到的候选与库内依据
            #   长得一模一样。缺这个键 = 库内依据（= `None`，不是 `false`），口径只有一处：
            #   `review_engine.is_candidate()`（判**显式 False**，不判缺键）。
            "authoritative": it.get("authoritative"),
            "superseded_by": it.get("superseded_by"),
        })
    return {
        "state": d.get("decision"),
        "confidence": d.get("confidence"),
        "confidence_note": "启发式，未做金标标定；不得当成法律合规概率",
        "issue_count": d.get("issue_count"),
        # ★ 同上：把「问题数」**拆开**给出来 —— 库内依据 / 非权威候选各几条。
        #   契约值 `issue_count` 不动（仍是总数）；这两项是**新增**，缺了 = 未测（None），不是 0。
        "candidate_count": d.get("candidate_count"),
        # ★ 2026-10-12：`issue_count` 已改成「只算库内依据」（Owner 裁定）⇒ 旧口径留出口
        "issue_count_including_candidates": d.get("issue_count_including_candidates"),
        "issue_count_basis": d.get("issue_count_basis"),
        "summary": d.get("summary"),
        "next_owners": d.get("next_owners"),
        "items": items,
        "coverage": {"text": "complete", "image": "not_applicable", "video": "not_applicable"},
        "content_version": d.get("content_version"),
        "review_id": d.get("review_id"),
        "agent_version": d.get("agent_version"),
        "evidence": {"findings": meta.get("findings"), "source": meta.get("source")},
        "report_path": meta.get("report_path"),
        # 层前置留痕（2026-10-03）：enforced（带了 BASE 且核过）/ waived_by_api（没带）
        "layer_preflight": _pf,
        # 判定主体留痕（2026-10-03，防线2）：declared_by_api / waived_by_api / absent_by_api
        # ★ bot 那条路**核不了** skill 有没有真被加载 ⇒ `declared_by_api` 是申报，不是观测。
        "decision_owner": _do,
    }


# ---------------------------------------------------------------- 内部
def _find_rule_by_code(code):
    if not code:
        return None
    for rec in CANONICAL.values():
        if rec.get("rule_code") == code:
            return rec
    return None


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8787")))
