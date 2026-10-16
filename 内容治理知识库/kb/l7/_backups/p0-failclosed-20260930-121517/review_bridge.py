#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""review_bridge.py —— 审查桥：把「飞书侧守衡」的 HTTP 调用桥到本机 DSH 的 skill 工作流。

## 它解决什么

守衡跑在**别的机器**上（见 工作台/scripts/workbench-service.sh 注释），没有本机 shell，
够不到 `dsh --profile headless "<任务>"`。本服务是那道桥：

    守衡（外网） --HTTP--> 本桥 --subprocess--> dsh --profile headless <审查任务>
                                                 └─ 加载 kb-review / 文案合规审查 / P0 匹配 …

## 三条硬纪律（都不是本服务的发明，是库自己的口径）

1. **引用契约**：出结论必须带「条款号 + anchor + source_sha256 + 逐字摘录」。
   服务端**逐条核**：没有依据支撑的 PASS，一律降级为 REVIEW ——
   宁可回「需要人看」，也不回一个无锚点的放行结论（kb-content-review 的 hard_gate）。
2. **不给放行承诺**：`3_措辞表达库` 是派生视图，口径写明「未命中 ≠ 合规」、
   「p_level/risk_level 不是放行结论」。所以本服务只回三态**分流**结论，
   不生成「能过 / 保证合规」这类措辞。
3. **cwd 必须是含 kb 软链的那一层**：29 个 kb 脚本用 `kb/...` 相对路径。
   cwd 写错 = 工程错，不是数据错。

## 零污染

子进程用**隔离的 DSH_HOME**（默认 `内容治理/review-bridge/.bridge-home`），
不写真实的 `~/.dsh`。skills / plugins 走软链复用，profiles 走真实副本
（软链会被写操作 ESYMLINK 穿透失败，实测）。

## 用法

    python3 review_bridge.py --port 8788 --token <KEY>
    curl -s -X POST http://127.0.0.1:8788/openapi/v1/review \
      -H "Authorization: Bearer <KEY>" -H "Content-Type: application/json" \
      -d '{"text":"全网最好用的吸奶器，绝对安全"}'

接口：
    GET  /health                      —— 连通性与依赖自检（免 token）
    POST /openapi/v1/review           —— 单条素材审查（主接口）
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# ──────────────────────────────────────────────────────────── 路径常量

HERE = os.path.dirname(os.path.abspath(__file__))
KB_LAYER_ROOT = os.path.join(os.path.dirname(HERE), "kb")   # …/内容治理/kb
WORK_CWD = os.path.dirname(KB_LAYER_ROOT)                    # …/内容治理（含 kb/ 软链的那一层）

DEFAULT_HOME = os.path.join(HERE, ".bridge-home")

#: DSH 运行时（DSH Desktop 自带 node，PATH 里没有 node）
DSH_NODE_CANDIDATES = [
    os.path.expanduser(
        "~/Library/Application Support/DSH Desktop/runtime-commands/private/node-bin/node"
    ),
    "/usr/local/bin/node",
    "/opt/homebrew/bin/node",
]
DSH_BIN_CANDIDATES = [
    "/Applications/DSH Desktop.app.pre-lute-20260907-111753/Contents/Resources/"
    "app.asar.unpacked/node_modules/@deepseek-ai/dsh/lib/bin.js",
]

#: 审查结论三态 + 需人补料
VALID_STATUS = {"PASS", "REVIEW", "BLOCK", "NEEDS_INPUT"}

# ──────────────────────────────────────────────────────────── 隔离 HOME 准备


def log(msg: str) -> None:
    print(f"[bridge {time.strftime('%H:%M:%S')}] {msg}", flush=True)


def find_first(paths: list[str], kind: str) -> str:
    for p in paths:
        if os.path.exists(p):
            return p
    raise SystemExit(f"找不到{kind}：试过 {paths}")


#: 本桥只跑 `--profile headless`，所以只复制这一个 profile。
#: ⚠ 教训：早前版本复制整个 profiles/ —— 那里有 desktop 全家桶（node_modules 数百 MB）
#: 且 DSH 会同时写入 `.desktop.incomplete-*` 临时目录，copytree 直接崩。
#: 最少必要 = 只复制要用的那一个。
NEEDED_PROFILE = "headless"


def prepare_home(home: str, real_home: str) -> dict:
    """建隔离 DSH_HOME：skills/plugins 软链复用，只复制 headless profile，凭据软链。"""
    os.makedirs(home, exist_ok=True)
    info: dict[str, str] = {}

    for name in ("skills", "plugins"):
        src = os.path.join(real_home, name)
        dst = os.path.join(home, name)
        if not os.path.exists(src):
            continue
        if not os.path.exists(dst):
            os.symlink(src, dst)
        info[name] = f"软链 → {src}"

    # profiles：软链会被写操作穿透失败（实测 EPERM）→ 用真实副本，且只复制 headless 一个
    prof_dst = os.path.join(home, "profiles")
    os.makedirs(prof_dst, exist_ok=True)
    src_prof = os.path.join(real_home, "profiles", NEEDED_PROFILE)
    dst_prof = os.path.join(prof_dst, NEEDED_PROFILE)
    if os.path.exists(src_prof) and not os.path.exists(os.path.join(dst_prof, "package.json")):
        if os.path.exists(dst_prof):
            shutil.rmtree(dst_prof)
        shutil.copytree(src_prof, dst_prof)
        info["profiles"] = f"仅复制 {NEEDED_PROFILE} ← {src_prof}"
    else:
        info["profiles"] = f"复用已有 {dst_prof}"

    cred_src = os.path.join(real_home, ".credentials.yaml")
    cred_dst = os.path.join(home, ".credentials.yaml")
    if os.path.exists(cred_src) and not os.path.exists(cred_dst):
        os.symlink(cred_src, cred_dst)
        info["credentials"] = "软链 → 真实凭据（只读复用，不复制明文）"
    return info


# ──────────────────────────────────────────────────────────── 审查任务与解析

PROMPT = """你是内容治理审查执行器。按知识库的评审链判定下面这条素材。

【必须调用 skill】用 kb-review 作为入口；它能看出专项归属时会分派给对应专项成员
（文字走 文案合规审查、产品宣称走 产品宣称核验 等）。用 P0 匹配（kb-p0-check）做红线检查。

【判定口径 —— 不许违反】
1. 只回三态**分流**结论，不许给「能过 / 保证合规」这类放行承诺。
2. 未命中 ≠ 合规。没命中任何规则时，结论只能是 REVIEW 或 NEEDS_INPUT，不能是 PASS。
3. `3_措辞表达库` 是派生视图，「p_level / risk_level 不是放行结论」。
4. 每条依据必须能回源：给条款号 + anchor + source_sha256 + 逐字摘录。
   拿不到锚点的判定，不要写进依据里。
5. 查不到就说查不到，不许用常识补。

【输出格式】最后**只输出一个 JSON 代码块**，不要有别的内容：

```json
{
  "status": "PASS | REVIEW | BLOCK | NEEDS_INPUT",
  "summary": "一句话结论",
  "reasons": [{"code": "原因码或规则类", "detail": "说明"}],
  "evidence": [
    {"article_no": "W-2.1", "anchor": "锚点", "source_sha256": "…", "quote": "逐字摘录"}
  ],
  "skills_used": ["kb-review", "文案合规审查"],
  "model_note": "判定时用到的口径或不确定性"
}
```

待判素材：
---
%s
---
"""


def extract_json(text: str) -> dict | None:
    """从模型输出里取最后一个 JSON 代码块（模型常在前后带解释）。"""
    blocks = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    for raw in reversed(blocks):
        try:
            obj = json.loads(raw)
            if isinstance(obj, dict) and "status" in obj:
                return obj
        except json.JSONDecodeError:
            continue
    # 退路：直接找最外层花括号
    m = re.search(r"\{.*\}", text, re.S)
    if m:
        try:
            obj = json.loads(m.group(0))
            if isinstance(obj, dict) and "status" in obj:
                return obj
        except json.JSONDecodeError:
            pass
    return None


def enforce_contract(obj: dict) -> tuple[dict, list[str]]:
    """逐条核引用契约。没有依据支撑的 PASS → 降级 REVIEW（硬闸门）。"""
    notes: list[str] = []
    status = str(obj.get("status") or "").strip().upper()
    if status not in VALID_STATUS:
        notes.append(f"status 非法（{status!r}）→ 降为 NEEDS_INPUT")
        status = "NEEDS_INPUT"

    evidence = obj.get("evidence") or []
    if not isinstance(evidence, list):
        evidence = []
    solid = [
        e for e in evidence
        if isinstance(e, dict) and e.get("article_no") and (e.get("anchor") or e.get("quote"))
    ]
    if len(solid) != len(evidence):
        notes.append(f"{len(evidence) - len(solid)} 条依据缺条款号或锚点，已标注为不可回源")

    if status == "PASS" and not solid:
        notes.append("PASS 但无任何可回源依据 → 按 hard_gate 降级为 REVIEW")
        status = "REVIEW"

    obj["status"] = status
    obj["evidence"] = evidence
    obj["evidence_solid"] = len(solid)
    obj["contract_notes"] = notes
    return obj, notes


# ──────────────────────────────────────────────────────────── 调用 headless

_sem: threading.Semaphore | None = None


def run_headless(task: str, cfg: argparse.Namespace) -> tuple[int, str, str, float]:
    """跑一次 headless 审查；返回 (exit, stdout, stderr, 秒)。"""
    assert _sem is not None
    env = dict(os.environ)
    env["DSH_HOME"] = cfg.home
    env.pop("KB_INTERP_OK", None)  # 不继承本进程的 KB 解释器标记
    cmd = [cfg.node, cfg.dsh_bin, "--profile", "headless", task]
    t0 = time.time()
    with _sem:
        proc = subprocess.run(
            cmd, cwd=cfg.cwd, env=env, capture_output=True, text=True,
            timeout=cfg.timeout, errors="replace",
        )
    return proc.returncode, proc.stdout, proc.stderr, time.time() - t0


# ──────────────────────────────────────────────────────────── HTTP 服务


class Handler(BaseHTTPRequestHandler):
    cfg: argparse.Namespace
    server_version = "review-bridge/0.1"

    def log_message(self, fmt: str, *args) -> None:  # 收敛日志
        log(f"{self.address_string()} {fmt % args}")

    # ── 工具
    def _send(self, code: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _auth_ok(self) -> bool:
        if not self.cfg.token:
            return True
        got = (self.headers.get("Authorization") or "").removeprefix("Bearer ").strip()
        return got == self.cfg.token

    # ── GET /health
    def do_GET(self) -> None:
        if self.path.split("?")[0] not in ("/health", "/openapi/v1/health"):
            self._send(404, {"error": "not_found", "path": self.path})
            return
        checks = {
            "kb_root_marker": os.path.exists(os.path.join(KB_LAYER_ROOT, "KB-ROOT.json")),
            "kb_symlink": os.path.exists(os.path.join(WORK_CWD, "kb")),
            "dsh_node": os.path.exists(self.cfg.node),
            "dsh_bin": os.path.exists(self.cfg.dsh_bin),
            "isolated_home": os.path.isdir(self.cfg.home),
            "skills_linked": os.path.exists(os.path.join(self.cfg.home, "skills")),
            "credentials": os.path.exists(
                os.path.join(self.cfg.home, ".credentials.yaml")
            ),
        }
        self._send(200 if all(checks.values()) else 503, {
            "ok": all(checks.values()),
            "service": "review-bridge",
            "cwd": self.cfg.cwd,
            "dsh_home": self.cfg.home,
            "timeout_s": self.cfg.timeout,
            "checks": checks,
        })

    # ── POST /openapi/v1/review
    def do_POST(self) -> None:
        if self.path.split("?")[0] != "/openapi/v1/review":
            self._send(404, {"error": "not_found", "path": self.path})
            return
        if not self._auth_ok():
            self._send(401, {"error": "unauthorized"})
            return
        try:
            n = int(self.headers.get("Content-Length") or 0)
            req = json.loads(self.rfile.read(n) or b"{}")
        except (ValueError, json.JSONDecodeError):
            self._send(400, {"error": "bad_json"})
            return

        text = str(req.get("text") or "").strip()
        if not text:
            self._send(400, {"error": "missing_text", "hint": "字段 text 必填"})
            return
        if len(text) > self.cfg.max_chars:
            self._send(413, {
                "error": "text_too_long",
                "limit": self.cfg.max_chars,
                "got": len(text),
            })
            return

        try:
            code, out, err, secs = run_headless(PROMPT % text, self.cfg)
        except subprocess.TimeoutExpired:
            self._send(504, {
                "error": "review_timeout",
                "timeout_s": self.cfg.timeout,
                "hint": "审查超时；可提高 --timeout 或拆分素材",
            })
            return

        if code != 0:
            self._send(502, {
                "error": "headless_failed",
                "exit": code,
                "stderr_tail": err[-1500:],
            })
            return

        obj = extract_json(out)
        if obj is None:
            # 没按契约输出 JSON：如实回原始文本，判 NEEDS_INPUT，不猜结论
            self._send(200, {
                "status": "NEEDS_INPUT",
                "summary": "审查执行器未按引用契约输出 JSON，需人工阅读原始输出",
                "reasons": [{"code": "CONTRACT_NOT_MET", "detail": "输出里找不到合法 JSON 结论"}],
                "evidence": [],
                "evidence_solid": 0,
                "contract_notes": ["输出未遵循 JSON 契约 → 不生成三态结论"],
                "raw_output": out[-4000:],
                "elapsed_s": round(secs, 1),
            })
            return

        obj, notes = enforce_contract(obj)
        obj["elapsed_s"] = round(secs, 1)
        obj["_contract_enforced"] = True
        if notes:
            log(f"契约修正：{notes}")
        self._send(200, obj)


# ──────────────────────────────────────────────────────────── 入口


def main() -> None:
    global _sem
    ap = argparse.ArgumentParser(description="审查桥：守衡 HTTP → 本机 DSH skill 工作流")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8788)
    ap.add_argument("--token", default=os.environ.get("REVIEW_BRIDGE_TOKEN", ""),
                    help="Bearer 鉴权；留空则不校验（仅本机调试用）")
    ap.add_argument("--home", default=DEFAULT_HOME, help="隔离的 DSH_HOME")
    ap.add_argument("--real-home", default=os.path.expanduser("~/.dsh"))
    ap.add_argument("--cwd", default=WORK_CWD, help="headless 子进程 cwd（须含 kb/ 软链）")
    ap.add_argument("--timeout", type=int, default=180, help="单次审查超时秒数")
    ap.add_argument("--concurrency", type=int, default=2, help="并发审查上限")
    ap.add_argument("--max-chars", type=int, default=20000, help="单条素材字数上限")
    cfg = ap.parse_args()

    cfg.node = find_first(DSH_NODE_CANDIDATES, "DSH 运行时 node")
    cfg.dsh_bin = find_first(DSH_BIN_CANDIDATES, "dsh CLI")
    _sem = threading.Semaphore(cfg.concurrency)

    info = prepare_home(cfg.home, cfg.real_home)
    log(f"库根 cwd : {cfg.cwd}")
    log(f"DSH_HOME : {cfg.home}")
    for k, v in info.items():
        log(f"  {k}: {v}")

    srv = ThreadingHTTPServer((cfg.host, cfg.port), Handler)
    Handler.cfg = cfg
    log(f"审查桥就绪 → http://{cfg.host}:{cfg.port}")
    log(f"  GET  /health")
    log(f"  POST /openapi/v1/review   （Bearer {'已启用' if cfg.token else '未启用'}）")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        log("收到中断，退出")
        srv.shutdown()


if __name__ == "__main__":
    main()
