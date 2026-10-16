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
    content_id: Optional[str] = Field(default=None, description="留空则自动用 text 的 sha256 前 12 位")
    channel: str = Field(default="", description="Amazon / TikTok / 独立站 …（可空）")
    product_line: str = Field(default="", description="品线（可空）")
    product_line_seed: str = Field(default="", description="给 5 条种子规则扫描器的词表原样值，如「吸奶器」")
    sku: Optional[str] = None


@app.post("/review", summary="评审链：依据 + 三态裁决（带条款号/锚点/source_sha256/逐字摘录）")
def do_review(req: ReviewReq, authorization: Optional[str] = Header(default=None)):
    """跑评审链，返回 PASS / REVIEW / BLOCK / NEEDS_INPUT + 逐条依据。

    - **依据**：P0 确定性匹配 + 509 条措辞表达库规则 + BM25（组件 = kb-content-review）
    - **裁决**：review_engine.decide()（决策序 NEEDS_INPUT > BLOCK > REVIEW > PASS）
    - 同一 text 的 `content_version` 稳定（= sha256），可用于幂等/去重
    - `confidence` 是**启发式**（引擎自述「未做金标标定」），不得当成法律合规概率
    """
    auth(authorization)
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
        })
    return {
        "state": d.get("decision"),
        "confidence": d.get("confidence"),
        "confidence_note": "启发式，未做金标标定；不得当成法律合规概率",
        "issue_count": d.get("issue_count"),
        "summary": d.get("summary"),
        "next_owners": d.get("next_owners"),
        "items": items,
        "coverage": {"text": "complete", "image": "not_applicable", "video": "not_applicable"},
        "content_version": d.get("content_version"),
        "review_id": d.get("review_id"),
        "agent_version": d.get("agent_version"),
        "evidence": {"findings": meta.get("findings"), "source": meta.get("source")},
        "report_path": meta.get("report_path"),
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
