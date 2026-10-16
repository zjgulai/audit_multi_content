#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kb_pipeline.py —— 知识库 L0–L7 的**执行编排器**（P0-1）

读 kb/l7/registry/layers.yaml（静态真源）→ 拓扑排序 → 逐层校验 → 逐层跑闸门 → 汇总。
两种模式：
  · `--check`（零写档）：不执行任何会写盘的层引擎，只做静态校验 + 跑已确认只读的闸门；
  · `--sync`（写档编排，2026-09-30 加）：按拓扑序逐层「先闸门、后引擎」，**默认预演**，
    加 `--apply` 才落盘；越出 `SYNC_ALLOWED` 白名单必须显式 `--allow-beyond-policy`。
    （旧文写「本版只有 --check」，已过期 —— --sync 已实现，见 run_sync。）
  · `--sync --via-skill`（逐层调 skill，2026-09-30 加）：**编排器不跑层引擎** ——
    到达 Lx 就按 layers.yaml 该层 `skill:` 字段报出该调哪个 skill，引擎归那个 skill 跑；
    编排器只保留闸门 + 归档红线 + 锁 + 记账（run 记录的 skills 写逐层真调用到的 skill）。
    **默认关**：不带 `--via-skill` 时行为与旧版逐字节一致。

为什么需要它：`layers.yaml` 已把每层的 engine / inputs / outputs / gate / cwd / python /
envelope / write_mode / dry_run / skill 全部声明齐全，但**没有任何脚本按它去执行** —— 于是"自动化"
实际是"agent 照文档做"。本脚本是那个缺失的执行者；而"每一层由谁执行"的答案是
**该层的 skill**（`skill:` 字段），本脚本负责编排、闸门与记账。

零写保证（三层，适用于 `--check` 与 `--sync` 的预演路径）：
  1. 预演路径**没有任何写操作**（无 open(...,"w")、无 shutil 落地）；
  2. 只跑**只读白名单**里的闸门，其余闸门逐条说明为何未执行（不静默跳过）；
  3. 跑前跑后对"各层已存在的产出文件"取 mtime 快照，**变化即报错**（自证零写）。

用法（库内相对路径，cwd 必须是 kb/ 的上一级；推荐走 kb/kbpy）：
    kb/kbpy l7/scripts/kb_pipeline.py --check                 # 全链零写体检
    kb/kbpy l7/scripts/kb_pipeline.py --check --no-gates      # 只做静态校验，不跑闸门
    kb/kbpy l7/scripts/kb_pipeline.py --check --only L3       # 只看/只跑某层
    kb/kbpy l7/scripts/kb_pipeline.py --check --from L2       # 从某层起
    kb/kbpy l7/scripts/kb_pipeline.py --check --json
    kb/kbpy l7/scripts/kb_pipeline.py --sync --only L2        # 写档编排（预演）
    kb/kbpy l7/scripts/kb_pipeline.py --sync --all            # 整链预演
退出码：0 全过；1 有硬问题；2 用法/环境错。
"""
# ── ★ 修复4（2026-10-03）：让 SIGTERM 也能走到 `finally: release_lock()` ──────────
#   为什么加：`review_freshness_gate.py` 的**自动跑层**超时时用 `subprocess.run(timeout=)`，
#   那会直接 **SIGKILL** 子进程 —— `finally` 不跑、锁就留在 `kb/.work/.kb.lock`。
#   实测代价：2026-10-03 18:53:13 那把 `run_id=20261003-185311-autorun` 的锁就是这样漏的，
#   随后 **挡停了第二天的一次日更**（`L1 写档 → exit=2`，日更「遇红即停」）。
#   把 SIGTERM 转成 SystemExit 后，`finally: release_lock()` 就能正常释放锁。
#   注：**SIGKILL 仍然拦不住**（设计如此，无法捕获）⇒ 对端也必须配合：
#   先 SIGTERM 收尾、给宽限期，仍不收尾才 SIGKILL（见 review_freshness_gate.py）。
def _sigterm_to_exit(signum, frame):                    # noqa: ARG001
    raise SystemExit(128 + signum)


try:
    import signal as _signal
    _signal.signal(_signal.SIGTERM, _sigterm_to_exit)
except Exception:                                       # noqa: BLE001
    pass                                                # 装不上就算了，不拖垮主流程
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

import argparse
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
KB = os.path.dirname(os.path.dirname(HERE))          # …/kb
CONFIG_NAME = ".kb-python"

# 只读闸门白名单：**只在逐条确认"0 写盘点"或自带 --check 档后**才可加入
GATE_WHITELIST = {
    "kb/l7/scripts/layers_check.py": [],
    "kb/l7/scripts/skills_check.py": [],
    "kb/l1/index/rebuild_l1_index.py": ["--check"],
    # L0 的闸门：纯对账器（不改 kb/l0）。--check 只读档 = 快照落 /tmp、不写报告 + 差异判退出码
    "kb/l8/align_l0_feishu.py": ["--check"],
    # L0 的**判定档**（2026-09-30 加）：跑 align --check + 读 l7/registry/l0-expected-diffs.yaml，
    # 把「按声明就该存在的差异」分类出来，只有真差异才判红 —— 否则材料收集那 10 条
    # 按声明排除的记录会让 L0 闸门**永远红**。零写：只读 yaml、不写 kb/l0。
    "kb/l7/scripts/l0_gate.py": [],
    # ── P1-3（2026-09-30）：L1–L7 七道层闸门落地，目标「过 8 / 未判 0」 ─────────────
    # 全部只读（不写 kb/l0…l6 的任何数据与台账）；每道都做过反测（把判据弄坏必须变红）。
    # L1：把 .work/kb_ocr_gate.py::ocr_cache_reusable 落到 169 条真实 OCR 缓存上逐条判。
    "kb/l7/scripts/l1_gate.py": [],
    # L2：独立复算 manifest_l2 × units × manifest_l1，不读 l2.json 的自报计数。
    "kb/l7/scripts/l2_gate.py": [],
    # L3：1729 条 evidence_units 逐条回指 + rejected 台账回指 + 自报键逐键声明。
    "kb/l7/scripts/l3_gate.py": [],
    # L4：从定稿 × 候选 × L2 单元重算 C1–C6（2462 条证据引用逐条回指）。
    "kb/l7/scripts/l4_gate.py": [],
    # L5：包装 .work/l5_integrity.py 的 6 项，实质项判红、基线项须登记（它会写自己的证据 json）。
    "kb/l7/scripts/l5_gate.py": [],
    # L6：只读档 4 项；③重跑幂等会带 --apply 重跑建索引 → 不进日报，闸门里明写「没跑哪几项」。
    "kb/l7/scripts/l6_gate.py": [],
    # L7：引用契约的前置条件（库名不得自造 / 六要素 100% 可物化 / 条款号出处可解析）。
    "kb/l7/scripts/l7_gate.py": [],
}
# 已知需参数/未验证只读 → 不执行，但必须出现在报告里
GATE_NOT_RUN_REASON = {
    "kb/.work/l5_integrity.py": "未纳入只读白名单（其写行为未逐条验证）",
    "kb/.work/l6_integrity.py": "需要位置参数（run_id）",
    "kb/.work/kb_ocr_gate.py": "函数引用（path::func），非独立可执行",
}
PLACEHOLDER = re.compile(r"<[^>]+>|\*\*")
GLOBCH = re.compile(r"[*?{\[]")        # glob 模式（非字面路径）：按「至少匹配到一个」判
import glob as _glob


def home(p: str) -> str:
    return os.path.expanduser(str(p))


def read_config() -> str:
    for base in (os.path.dirname(KB), KB):
        p = os.path.join(base, CONFIG_NAME)
        if os.path.isfile(p):
            for ln in open(p, encoding="utf-8"):
                ln = ln.split("#", 1)[0].strip()
                if ln:
                    return home(ln)
    return os.environ.get("KB_PYTHON") or ""


def looks_like_path(s: str) -> bool:
    s = s.strip()
    return bool(re.match(r"^(kb/|~/|/)", s))


def is_glob(s: str) -> bool:
    return bool(GLOBCH.search(s))


def brace_expand(s: str) -> list[str]:
    """bash 花括号展开：{1..4,9} → 1 2 3 4 9；{a,b} → a b。glob 本身不支持花括号。"""
    m = re.search(r"\{([^{}]*)\}", s)
    if not m:
        return [s]
    alts = []
    for part in m.group(1).split(","):
        if ".." in part:
            a, b = part.split("..", 1)
            try:
                lo, hi = int(a), int(b)
                alts += [str(i) for i in range(min(lo, hi), max(lo, hi) + 1)]
            except ValueError:
                alts.append(part)
        else:
            alts.append(part)
    out = []
    for a in alts:
        out += brace_expand(s[:m.start()] + a + s[m.end():])
    return out


def has_match(pat: str, cwd: str) -> bool:
    for exp in brace_expand(pat):
        p = exp if os.path.isabs(home(exp)) else os.path.join(cwd, exp)
        if _glob.glob(home(p), recursive=True):
            return True
    return False


def strip_placeholder(p: str) -> str:
    s = PLACEHOLDER.split(p)[0]
    m = GLOBCH.search(s)                       # 截到第一个 glob 字符，取其目录做父目录判定
    if m:
        s = s[:m.start()]
    return s.rstrip("/") or p


def topo_sort(layers: list[dict]) -> list[dict]:
    ids = [x.get("layer") for x in layers]
    indeg = {}
    for x in layers:
        d = [y for y in (x.get("depends_on") or []) if y in ids and y != x.get("layer")]
        indeg[x["layer"]] = len(d)
    out, seen = [], set()
    while len(out) < len(layers):
        ready = [x for x in layers if x["layer"] not in seen and indeg[x["layer"]] == 0]
        if not ready:                      # 有环 → 按声明顺序兜底，并如实标注
            ready = [x for x in layers if x["layer"] not in seen][:1]
            ready[0]["_cycle"] = True
        for x in ready:
            out.append(x); seen.add(x["layer"])
            for y in layers:
                if x["layer"] in (y.get("depends_on") or []):
                    indeg[y["layer"]] -= 1
    return out


def snapshot_mtimes(layers: list[dict]) -> dict:
    """对每层已存在的产出文件取 mtime 快照（零写自证用）。"""
    snap = {}
    for x in layers:
        for o in (x.get("outputs") or []):
            if not looks_like_path(o):
                continue
            base = strip_placeholder(o)
            p = base if os.path.isabs(home(base)) else os.path.join(os.path.dirname(KB), base)
            p = home(p)
            if os.path.isfile(p):
                try: snap[p] = os.path.getmtime(p)
                except OSError: pass
            elif os.path.isdir(p):
                for r, d, f in os.walk(p):
                    d[:] = [z for z in d if z != "__pycache__"]
                    for z in f:
                        q = os.path.join(r, z)
                        try: snap[q] = os.path.getmtime(q)
                        except OSError: pass
                        if len(snap) > 4000: return snap
    return snap


def run_gate(script: str, extra: list[str], cwd: str, py: str):
    """跑一个白名单闸门，返回 (ok, 摘要)。"""
    target = os.path.join(cwd, script)
    if not os.path.isfile(target):
        return False, "闸门脚本不存在: %s" % script
    env = dict(os.environ, KB_INTERP_OK="1", PYTHONDONTWRITEBYTECODE="1")
    try:
        r = subprocess.run([py, target] + extra, cwd=cwd, env=env,
                           capture_output=True, text=True, timeout=600)
    except subprocess.TimeoutExpired:
        return False, "超时"
    tail = [l for l in (r.stdout or "").strip().split("\n") if l.strip()]
    summ = tail[-1][:110] if tail else "(无输出)"
    return r.returncode == 0, "exit=%d ｜ %s" % (r.returncode, summ)


# ══════════════════════════════════════════════════════════════════════════
# --sync：写档编排（2026-09-30 加）。三条红线逐条落在代码里，不靠人记。
# ══════════════════════════════════════════════════════════════════════════

LOCK = os.path.join(KB, ".work", ".kb.lock")

# 各层的写档引擎（**只在这里登记**；每条都要能在该层 layers.yaml 的 engine 列表里找到）。
#   args      ：位置参数（RUN 会被替换成本次 run_id）
#   apply     ：该脚本的落盘开关（`--apply`；None = 该脚本本就无落盘开关，如只读对账器）
#
# ★ 本表**不再登记「本层能不能预演」** —— 干跑档的真源是
#   `kb/l7/registry/layers.yaml` 各层的 `dry_run` 字段（唯一真源，改口径先改表）。
#   2026-09-30 修正：原先本表把 L3 写死 `apply=None / dry_ok=False`，注释称「L3 蒸馏器没有干跑档」，
#   与同时期的 layers.yaml（L3 行 `dry_run: true`，notes 已写明「干跑档已补 P0-3」）
#   以及脚本实测（`kb/l8/l3_distill_run.py:32` 解析 APPLY、`:42–46` 不带 --apply 即预演并 exit 0）
#   三方打架 —— 后果是 `--sync --all` 停在 L3，整链永远走不到 L4–L7。
#   同一事实写两处，第二处必然过期；故改为**只读 layers.yaml**，本表只声明「怎么调」。
SYNC_SPEC = {
    "L1": [{"script": "kb/l8/ocr_attachments.py", "args": ["RUN"], "apply": "--apply"}],
    "L2": [{"script": "kb/l8/l2_split_run.py", "args": ["RUN"], "apply": "--apply"}],
    # L3：l3_distill_run.py 已于 P0-3 补 --apply 干跑档（闸门早于 RUN 解析与任何写盘）——
    # 判据见 layers.yaml 的 L3 行 `dry_run: true`，不再在本表重复声明。
    "L3": [{"script": "kb/l8/l3_distill_run.py", "args": ["RUN"], "apply": "--apply"}],
    "L4": [{"script": "kb/.work/l4_article.py", "args": ["RUN"], "apply": "--apply"}],
    "L5": [{"script": "kb/.work/l5_prep.py", "args": ["RUN"], "apply": "--apply"},
           {"script": "kb/.work/l5_export.py", "args": ["RUN"], "apply": "--apply"}],
    "L6": [{"script": "kb/.work/l6_build.py", "args": ["RUN"], "apply": "--apply"}],
    # L7 没有写库数据的引擎（它就是索引/注册表/报告层）→ 只跑闸门。
    "L7": [],
}

# 红线①：写这些层之前，必须先把**会被改写/重建**的台账归档一份（实测依据：
# kb/l3/rejected.jsonl 2026-09-29 被重建过，历史只能从 kb/l3/_archive/ 捞回来）。
ARCHIVE_BEFORE_WRITE = {
    "L3": ["kb/l3/rejected.jsonl"],
}

# 写档白名单：越界必须显式说一声（--allow-beyond-policy），而不是顺手就能跑。
# ★ 2026-10-02 改（用户裁定）：**放开 L1–L6 全层**。
#   口径原文：「每层自动更新，不要人手动触发」+「每天 8:30 全跑一遍，其他时间不用跑」。
#   原先只开 ["L2"]（两周只读观察期），导致日更只能更新 L0，L1–L7 全靠人点名。
#   为什么敢放开：放开的**不是防护**——每层仍有自己的闸门与写前保护：
#     · 编排器：每层「先闸门、后引擎」，闸门红即停（run_sync 里逐层判定）
#     · 编排器：ARCHIVE_BEFORE_WRITE 的归档红线（L3 等）+ 持锁互斥
#     · 引擎侧（今天加的）：内容对等则不写 / 写前强制归档+sha 校验 / 行数骤减护栏
#   白名单机制**保留**（不是删掉）：将来要收紧，改这一个列表即可。
SYNC_ALLOWED = ["L1", "L2", "L3", "L4", "L5", "L6"]


def _run_id_now() -> str:
    import time as _t
    return _t.strftime("%Y%m%d-%H%M")


def _pid_alive(pid) -> bool:
    try:
        os.kill(int(pid), 0)
        return True
    except Exception:                                # noqa: BLE001
        return False


def lock_state():
    """返回 (状态, 记录)。状态 ∈ absent / held-alive / stale-declared / held-dead。

    为什么要分这么细（实测 2026-09-30）：库上躺着一个 **2026-09-24 的旧锁**
    `kb/.work/.kb.lock`，它的 JSON 里 `status=finished_partial`、`released_at=2026-09-24T17:45:00`
    —— 也就是**上一个持有者自己宣布结束了**，只是没删文件。这种锁要是当成「有人在跑」，
    写档编排就**永远起不来**（`.work/batch*.py` 撞到同一个文件也是直接退出）。
    反过来，把「pid 死了」一律当陈旧自动删，又会在真崩在中途时偷偷放行第二次写。
    所以：**宣布释放过 + pid 不在** = 陈旧（dry-run 可绕过并告警，写档仍要人拍板）；
    其余一律当真锁拒绝。
    """
    if not os.path.exists(LOCK):
        return "absent", None
    try:
        rec = json.load(open(LOCK, encoding="utf-8"))
    except Exception:                                # noqa: BLE001
        return "held-dead", {"raw": "(无法解析为 JSON)"}
    alive = _pid_alive(rec.get("pid"))
    if alive:
        return "held-alive", rec
    if rec.get("released_at") or str(rec.get("status") or "").startswith("finished"):
        return "stale-declared", rec
    return "held-dead", rec


def acquire_lock(run_id: str, break_lock: bool = False, dry: bool = False):
    """红线②：编排器自己持 kb/.work/.kb.lock。返回 (ok, 说明)。"""
    os.makedirs(os.path.dirname(LOCK), exist_ok=True)
    st, rec = lock_state()
    if st != "absent":
        rel = os.path.relpath(LOCK, os.path.dirname(KB))
        if st == "stale-declared" and dry:
            return True, ("⚠️ 陈旧锁（上一个持有者已宣布释放）：%s —— 本次是**预演**，不写盘，"
                          "故不抢锁继续跑；写档模式会被拒绝，除非人删掉它或 --break-lock" % rel)
        if break_lock:
            try:
                os.remove(LOCK)
            except OSError as e:
                return False, "撬锁失败：%s" % e
        else:
            why = {"held-alive": "持有者进程还活着（pid=%s）" % rec.get("pid"),
                   "stale-declared": "上一个持有者已宣布释放（released_at=%s）但文件还在 → "
                                     "写档前要人拍板：删掉它，或 --break-lock" % rec.get("released_at"),
                   "held-dead": "pid=%s 已不在，但**没有宣布释放** → 可能是崩在中途，"
                                "要人先判断有没有写坏" % rec.get("pid")}.get(st, "状态未知")
            return False, ("已有锁 %s ｜ %s ｜ 记录：%s —— 本编排器不自动撬锁（写档互斥靠它）"
                           % (rel, why, json.dumps(rec, ensure_ascii=False)[:220]))
    try:
        fd = os.open(LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return False, "抢锁失败：另一个写入者刚刚抢先（并发）"
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump({"run_id": run_id, "pid": os.getpid(),
                   "at": __import__("time").strftime("%Y-%m-%dT%H:%M:%S"),
                   "by": "kb_pipeline.py --sync"}, fh, ensure_ascii=False)
    return True, "已持锁 pid=%d run_id=%s" % (os.getpid(), run_id)


def release_lock():
    try:
        if os.path.exists(LOCK):
            os.remove(LOCK)
    except OSError:
        pass


def archive_before_write(layer: str, run_id: str):
    """红线①：归档台账。返回 (ok, 说明列表)。归档是**逐字节复制 + 校验**，不是改文件。"""
    msgs, ok = [], True
    for rel in ARCHIVE_BEFORE_WRITE.get(layer, []):
        src = os.path.join(os.path.dirname(KB), rel)
        if not os.path.isfile(src):
            msgs.append("⚠️ %s 不存在，跳过归档" % rel)
            continue
        d = os.path.dirname(src)
        arch = os.path.join(d, "_archive")
        base = os.path.basename(src)
        dst = os.path.join(arch, base.replace(".jsonl", "-pre-%s.jsonl" % run_id))
        try:
            os.makedirs(arch, exist_ok=True)
            import shutil as _sh
            _sh.copyfile(src, dst)                 # .jsonl 不受信封影响（见 l8.json 的 extension_matrix）
            a = os.path.getsize(src); b = os.path.getsize(dst)
            import hashlib as _h
            ha = _h.sha256(open(src, "rb").read()).hexdigest()
            hb = _h.sha256(open(dst, "rb").read()).hexdigest()
            if a != b or ha != hb:
                ok = False
                msgs.append("❌ 归档校验不过：%s（%d/%d 字节，sha %s/%s）" % (dst, a, b, ha[:12], hb[:12]))
            else:
                msgs.append("✅ 已归档 %s → %s（%d 字节，sha %s）"
                            % (rel, os.path.relpath(dst, os.path.dirname(KB)), b, hb[:12]))
        except OSError as e:
            ok = False
            msgs.append("❌ 归档失败：%s（%s）—— **红线①要求先归档再写，故停在这里，不写**" % (dst, e))
    return ok, msgs


PLAYBOOK = os.path.join(KB, "l7", "registry", "failure-playbook.yaml")


def playbook_get(sig: str):
    """按 id 取处置条目；取不到退到同前缀的 `*`；再取不到返回 None（**绝不现编**）。"""
    try:
        import yaml
        doc = yaml.safe_load(open(PLAYBOOK, encoding="utf-8")) or {}
        entries = {e.get("id"): e for e in (doc.get("entries") or [])}
    except Exception:                                # noqa: BLE001
        return None
    if sig in entries:
        return entries[sig]
    return entries.get(sig.split(".")[0] + ".*")


def print_playbook(sig: str, indent: str = "  "):
    """P3：失败清单 —— 把「谁、做什么、跑哪条命令、不许做什么」直接打出来。"""
    e = playbook_get(sig)
    if not e:
        print("%s⚠️ 没有登记的处置办法（%s）—— 补进 kb/l7/registry/failure-playbook.yaml，**不许现编**" % (indent, sig))
        return
    print("%s┌ 处置 %s" % (indent, e.get("id")))
    print("%s│ 症状    ：%s" % (indent, e.get("symptom")))
    print("%s│ 谁      ：%s" % (indent, e.get("owner")))
    print("%s│ 做什么  ：%s" % (indent, e.get("do")))
    print("%s│ 命令    ：%s" % (indent, e.get("command")))
    print("%s│ **不许**：%s" % (indent, e.get("forbidden")))
    print("%s└ 复开条件：%s" % (indent, e.get("reopen_when")))


def _layer_skills(x: dict) -> list:
    """本层该调哪个 skill —— **只读 layers.yaml 的 `skill:` 字段**（唯一真源，2026-09-30 加）。

    本函数存在的理由：编排形态从「逐层跑脚本」改成「逐层调该层 skill」之后，
    "到 Lx 调谁"必须是**表里读出来的**，不能在这个脚本里再写一份。
    """
    v = x.get("skill")
    if v is None:
        return []
    if isinstance(v, str):
        return [v]
    return [str(s) for s in v]


def _layer_engines(x: dict) -> list:
    eng = x.get("engine") or []
    return [eng] if isinstance(eng, str) else [str(e) for e in eng]


# ══════════════════════════════════════════════════════════════════════════════
# ★★ 批次27 · 第0块：`--skill` **透传** —— 编排器按 layers.yaml 的 `skill:` 唯一真源
#    给各层落章引擎传 `--skill`。
#
# 补哪个洞（实测，非推测）：
#   各层落章引擎（见下表）**早就支持** `--skill <id>`（各脚本 docstring 原文：「真源 =
#   kb/l7/registry/layers.yaml 本层 skill:，**由调用者读表后传入**；本脚本不硬编码」），
#   但**全库没有一个调用者传它** —— 这条契约的「调用者」一侧是空的：
#     · 只有人工手敲时才带上（实测：kb/l0..l6/runs/ 里带 skill 的落章全是手工跑出来的）；
#     · 编排器跑一遍，落章里**没有** `skill` ⇒ `skill_invocation_audit.py` 的 E2
#       （逐层无落章）恒红 —— 它要的正是「本 RUN + 带 skill」的落章。
#   ⇒ 这不是判据问题，是**缺一个调用者**。本块把那个调用者补上。
#
# 与 `pipeline_run_id` 的关系（两个字段各管一半，缺一不可）：
#   · `KB_PIPELINE_RUN_ID` 环境变量（批次21）= 让落章**归属到编排 RUN**（E2 的
#     `pipeline_run_id == <RUN>` 那一支）；
#   · `--skill` 参数（本块）= 让落章**带上该层真源 skill**（E2 的 `skill` 必需字段）。
#   两者由**同一次子进程调用**写入（同一 stamp 引擎、同一次 env+argv）。
#
# ★ 本表与 layers.yaml 的分工（不许混）：layers.yaml 是**唯一真源**，
#   它把「本层落章引擎」写在各层 `engine:` 条目的注释里（L0 `:117`、L1 `:165`、
#   L3 `:247`、L5 `:420`、L6 `:487`）。本表只把那份声明**变成可执行的一行**。
#   为防止本表腐烂成「第二份会过期的登记」，`_stamp_spec_selfcheck()` 会**逐条回表核对**
#   「这个脚本确实在本层 `engine:` 里」，对不上就**显著告警**（不静默通过）。
#
# ★ L7 不在此表：kb-check 是**跨层闸门**不是 L7 的层主，且 kb/l7/runs/<RUN>.json 就是
#   编排器自己的记账文件 —— 结构上不能自证（与 skill_invocation_audit.py 的
#   EXEMPT_LAYERS 同款豁免，理由同一份）。
STAMP_SPEC = {
    "L0": "kb/l8/reconcile_l0_feishu.py",     # layers.yaml:117「**L0 落章引擎**」
    "L1": "kb/l8/align_l1_manifest.py",       # layers.yaml:165「**L1 落章引擎**」
    "L2": "kb/l8/l2_split_run.py",            # 本层写档引擎**就是**落章引擎
    "L3": "kb/.work/l3_report.py",            # layers.yaml:247「**L3 落章引擎**」
    "L4": "kb/.work/l4_report.py",            # L4 落章引擎（批次4 补登的样板）
    "L5": "kb/.work/l5_report.py",            # layers.yaml:420「**L5 落章引擎**」
    "L6": "kb/.work/l6_report.py",            # layers.yaml:487「**L6 落章引擎**」
}

#: 各落章引擎 `--skill` 的**解析形态**（实测源码，写在这里免得下次再翻一遍）：
#:   · 单值 `_take("--skill")` —— L2/L3/L4/L5/L6（`--skill v` / `--skill=v`，**首个**生效）
#:   · 可重复收集 —— L1 `align_l1_manifest.py:50-55`（多个按序收成 list）
#:   · 单值 while-摘除 —— L0 `reconcile_l0_feishu.py:66-72`
#: ★ **全库没有任何落章引擎按逗号切分** ⇒ 多 skill 的层必须写**重复 flag**，不能写 `a,b`。
STAMP_MULTI_SKILL_REPEAT = ("L1",)


def _skill_args(lid: str, x: dict) -> list:
    """本层该传给落章引擎的 `--skill` 参数 —— **唯一真源 = layers.yaml 本层 `skill:`**。

    形态由 `layers.yaml` 的**声明**决定，不由调用者猜：
      · 声明一个 → `["--skill", "<id>"]`（落章写**单值**）；
      · 声明两个（实测只有 L1）→ `["--skill", "<a>", "--skill", "<b>"]`
        —— `align_l1_manifest.py` 按序收成 **list** 写进落章 `skill` 字段。
    """
    return [a for s in _layer_skills(x) for a in ("--skill", s)]


def _stamp_spec_selfcheck(layers):
    """回表核对 `STAMP_SPEC`：每个脚本必须出现在该层 layers.yaml 的 `engine:` 里。

    为什么要有它：`STAMP_SPEC` 是**代码里的第二份登记**，而本库反复栽在
    「同一事实写两处 ⇒ 必有一处过期」。核对不通过 ⇒ 打印告警并返回明细，
    由调用方决定停还是继续（**不静默**）。
    """
    bad = []
    by = {str(x.get("layer")): x for x in layers}
    for lid, script in STAMP_SPEC.items():
        x = by.get(lid)
        if x is None:
            bad.append("%s：layers.yaml 里没有这一层" % lid)
            continue
        if script not in _layer_engines(x):
            bad.append("%s：%s 不在本层 engine: 列表里" % (lid, script))
    return bad


ROOT = os.path.dirname(KB)                            # kb/ 的上一级（cwd 约定）


WRITE_GATE_FILE = os.path.join(KB, "l7", "registry", "write-gate.yaml")


def load_write_gate(gate_id):
    """读**驱动层人开闸凭据**（批次8 加）。返回 (ok, layers|None, msg)。

    ok=True 且 layers 是集合 → 该凭据覆盖这些层（**L7 一律剔除**，永不开写档）。
    gate_id 为 None → ok=False，msg 说明「未带凭据 ⇒ 各层只许只读档」。
    """
    if not gate_id:
        return False, None, ("**未带 --write-gate 凭据** → 本次按「各层只许只读档」对待；"
                             "层引擎不得带 --apply。凭据表见 kb/l7/registry/write-gate.yaml")
    if not os.path.exists(WRITE_GATE_FILE):
        return False, None, "凭据表不存在：%s" % WRITE_GATE_FILE
    try:
        import yaml
        doc = yaml.safe_load(open(WRITE_GATE_FILE, encoding="utf-8")) or {}
    except Exception as exc:                          # noqa: BLE001
        return False, None, "凭据表读不动：%r" % (exc,)
    for g in (doc.get("gates") or []):
        if str(g.get("id")) == str(gate_id):
            layers = {str(x) for x in (g.get("layers") or [])} - {"L7"}
            return True, layers, ("凭据命中 id=%s（authorized_by=%s, at=%s），覆盖层=%s"
                                  % (gate_id, g.get("authorized_by"), g.get("authorized_at"),
                                     sorted(layers, key=lambda s: int(s[1:]))))
    return False, None, ("凭据表里没有 id=%s 这一条 → 视为未开闸 ⇒ 各层只许只读档" % gate_id)


def _layer_stamps(lid: str, run_id: str) -> dict:
    """读**层侧落章**（实测），供 `--via-skill` 的记账据实填写（2026-10-01 加，A 块）。

    为什么必须有它：`--via-skill` 模式下编排器**永远不带 `--apply`**
    （`--gate-only` 与它互斥，第 5 步也不带）⇒ 旧写法
    `human_involved=bool(a.apply)` **结构性恒为 False**、`verdict` 恒为「预演·未落盘」、
    `products` 恒为 `[]`。而 `run_record.py` 的 docstring 写明
    「只有 run 记录的 `human_involved` 字段能分开（有人/无人在环）——**这一格是这套记录存在的理由**」。
    层级的事实就在磁盘上（层引擎自己写的 `kb/<layer>/runs/<RUN>*.json`），
    编排器**读它**即可 —— 注意：读≠写，**落章永远由执行该层的进程写**，编排器不代写。

    返回 {"applied": [(相对路径, 记录)], "dry": [...], "unknown": [...], "errors": [...]}
      · applied = 落章显式声明 `applied is True` → 该层**真落盘**
      · dry     = `dry_run is True` 或 `applied is False` → **预演台账**（按 L2 样板写的都落这里）
      · unknown = 两个字段都没有的老式落章 → **不算落盘证据**，单列，不并进 applied
      · errors  = 读不出的（坏 JSON / 顶层不是对象）→ 不静默吞，由调用方写进 extra
    """
    d = os.path.join(KB, str(lid).lower(), "runs")
    out = {"applied": [], "dry": [], "unknown": [], "errors": []}
    if not os.path.isdir(d):
        return out
    for name in sorted(os.listdir(d)):
        if not name.endswith(".json") or not name.startswith(run_id):
            continue
        p = os.path.join(d, name)
        rel = os.path.relpath(p, ROOT)
        try:
            with open(p, encoding="utf-8") as fh:
                rec = json.load(fh)
            if not isinstance(rec, dict):
                raise ValueError("顶层不是 JSON 对象")
        except Exception as exc:                      # noqa: BLE001
            out["errors"].append([rel, "%r" % (exc,)])
            continue
        if rec.get("applied") is True:
            out["applied"].append((rel, rec))
        elif rec.get("dry_run") is True or rec.get("applied") is False:
            out["dry"].append((rel, rec))
        else:
            out["unknown"].append((rel, rec))
    return out


def _stamp_products(rel: str, rec: dict) -> list:
    """从层侧落章里取产物清单；**层侧给不出就填层侧台账路径本身** —— 不许留空数组。

    空数组会复现老毛病：读记录的人从 `products: []` 得出「什么产物都没有」，
    而实际上层侧台账就在那儿。宁可填一个自己承认是什么的路径（如 `kb/l2/runs/<RUN>.json`）。

    兼容两种形态（2026-10-01 实测）：纯路径列表（L2 那种），
    以及**字典列表**（L4 `l4_report.py` 的 `artifacts: [{path, bytes, sha256}, …]`）——
    后者取其中的 `path`，**不要把 dict 字符串化**塞进 products（那样读的人拿到的是「{…}」）。
    """
    for k in ("products", "outputs", "artifacts"):
        v = rec.get(k)
        if not isinstance(v, list) or not v:
            continue
        out = []
        for x in v:
            if isinstance(x, dict):
                p = x.get("path") or x.get("file") or x.get("product")
                if p:
                    out.append(str(p))
            elif isinstance(x, str) and x:
                out.append(x)
        if out:
            return out
    return [rel]


def run_stamp_engine(lid, x, cwd, py, run_id, apply_ok, authorized):
    """★ 批次27 · 第0块：跑**本层落章引擎**，并把 layers.yaml 的 `skill:` 当面传给 `--skill`。

    这就是「`--skill` 透传」的落点：**参数由编排器从唯一真源读出来、交给层引擎**，
    落章仍由**层引擎自己写**（编排器不代写、不拼记录 —— 代写即 registry_echo，不能当证据）。

    返回 (ok: bool, summary: str)。

    三个 fail-closed 的地方（都不许静默跳过）：
      · 本层没有落章引擎登记（L7 / 或表腐烂）→ ok=False、说明写清楚；
      · `--apply` 但本层**不在人开闸凭据的授权层里** → 降级为**预演落章**
        （`<RUN>-dryrun.json`，`applied=false`）—— 落章会如实写「预演」，
        于是 E5 判黄、E1 观测不到 —— **这正是它该有的样子**，不是 bug；
      · 层引擎退出码非 0 → ok=False，由调用方决定停不停。
    """
    script = STAMP_SPEC.get(lid)
    sk = _layer_skills(x)
    skargs = _skill_args(lid, x)
    if not script:
        print("[%s] ⚠️ --skill 透传：**本层没有落章引擎登记**（STAMP_SPEC 无此层）"
              "→ 落章只能由该层 skill 自己写；本编排器不代写。" % lid)
        return False, "no_stamp_engine"
    if not sk:
        # ★ 这正是反测要的形态：声明为空 ⇒ **不传 --skill** ⇒ 落章不带 skill
        #   ⇒ skill_invocation_audit 的 E2 判红。**如实打印，不补值。**
        print("[%s] ⚠️ --skill 透传：**layers.yaml 本层 `skill:` 为空** → 不传 --skill。"
              "落章将不带 skill 字段 ⇒ 该层「调了谁」无证据（E2 会判红，这是对的）。" % lid)
    use_apply = bool(apply_ok) and bool(authorized)
    argv = [py, os.path.join(cwd, script), run_id] + skargs + (["--apply"] if use_apply else [])
    print("[%s] --skill 透传：%s %s %s%s"
          % (lid, os.path.basename(script), run_id,
             " ".join(skargs) if skargs else "**（无 --skill）**",
             " --apply" if use_apply else " ［预演档：未获本层写档凭据］"))
    before = snapshot_mtimes(layers_of_scope())
    try:
        r = subprocess.run(argv, cwd=cwd, capture_output=True, text=True,
                           env=dict(os.environ, KB_INTERP_OK="1",
                                    PYTHONDONTWRITEBYTECODE="1",
                                    KB_PIPELINE_RUN_ID=run_id),
                           timeout=600)
    except subprocess.TimeoutExpired:
        print("[%s] ❌ 落章引擎超时（600s）" % lid)
        return False, "stamp_timeout"
    tail = [l for l in (r.stdout or "").strip().split("\n") if l.strip()][-2:]
    after = snapshot_mtimes(layers_of_scope())
    changed = sorted(p for p in after if before.get(p) != after[p])
    print("[%s] 落章引擎 exit=%d ｜ 产物变化 %d 个" % (lid, r.returncode, len(changed)))
    for t in tail:
        print("        %s" % t[:170])
    if r.returncode != 0:
        for ln in (r.stderr or "").strip().split("\n")[-3:]:
            if ln.strip():
                print("        stderr: %s" % ln.strip()[:170])
        return False, "stamp_exit_%d" % r.returncode
    return True, "ok"


def layers_of_scope():
    """`snapshot_mtimes` 需要一个 layers 列表；这里给**本次编排的层表**（模块级缓存）。"""
    return _SCOPE_LAYERS


_SCOPE_LAYERS = []


def run_sync(a) -> int:
    """--sync 主流程：先闸门后写档，遇红即停。"""
    reg = os.path.join(KB, "l7", "registry", "layers.yaml")
    import yaml
    doc = yaml.safe_load(open(reg, encoding="utf-8"))
    layers = doc.get("layers") if isinstance(doc, dict) else doc
    ordered = topo_sort(layers)
    # 批次27 第0块：落章引擎的产物快照要用同一份层表（否则 snapshot_mtimes 看不到变化）
    global _SCOPE_LAYERS
    _SCOPE_LAYERS = layers
    # ★ 批次27 第0块：`STAMP_SPEC` 是代码里的第二份登记 → 回表核对，对不上就显著告警
    _sc_bad = _stamp_spec_selfcheck(layers)
    if _sc_bad:
        print("⚠️ STAMP_SPEC 与 layers.yaml 不一致（%d 条）—— 落章引擎表可能已过期：" % len(_sc_bad))
        for _b in _sc_bad:
            print("    · %s" % _b)
    else:
        print("[层表核对] STAMP_SPEC %d 条全部能在 layers.yaml 本层 engine: 里找到 ✅"
              % len(STAMP_SPEC))
    if not a.only and not a.all_layers:
        print("--sync 必须点名层：`--sync --only L2`（或 --all 明确表示整链，风险自负）", file=sys.stderr)
        return 2
    if a.only:
        ids = [z.strip() for z in a.only.split(",") if z.strip()]
        bad = [i for i in ids if i not in [x["layer"] for x in ordered]]
        if bad:
            print("未知层：%s" % bad, file=sys.stderr); return 2
        ordered = [x for x in ordered if x["layer"] in ids]
    py = read_config() or sys.executable
    run_id = a.run or _run_id_now()
    mode = "写档（--apply）" if a.apply else "预演（不带 --apply）"

    print("=" * 84)
    print("知识库 L0–L7 执行编排器 · --sync ｜ %s ｜ run_id=%s" % (mode, run_id))
    print("=" * 84)

    # 逐层调 skill 的**会话留痕**（2026-10-01 加）：Lx → 执行该层的 subagent 会话标识。
    # 它记的是「编排器起了哪个会话去跑 Lx」。★ 它不是落章 —— 落章（kb/<layer>/runs/ 的
    # skill 字段）必须由执行该层的进程自己写；编排器代写即 registry_echo、不能当证据
    # （判据见 kb/l7/scripts/skill_invocation_audit.py 的落章契约）。
    skill_sessions = {}
    for _it in (a.skill_session or []):
        _k, _v = _it.split("=", 1)                    # 格式已在 main() 里校验过
        skill_sessions[_k.strip()] = _v.strip()

    beyond = [x["layer"] for x in ordered if x["layer"] not in SYNC_ALLOWED
              and x["layer"] not in ("L7",)]
    if a.apply and beyond and not a.allow_beyond_policy:
        print("本编排器的写档白名单目前只有 %s。" % SYNC_ALLOWED)
        print("要点名跑 %s 的写档，必须显式加 --allow-beyond-policy。" % beyond)
        print_playbook("policy.beyond_whitelist")
        return 2

    if a.check_archive:                       # 只验红线①，不跑任何引擎
        ok_all = True
        for x in ordered:
            ok, msgs = archive_before_write(x["layer"], run_id)
            ok_all = ok_all and ok
            for m in msgs:
                print("[%s] %s" % (x["layer"], m))
        print("结论：%s" % ("✅ 归档红线可执行" if ok_all else "❌ 归档红线不通过 → 不许进入写档"))
        return 0 if ok_all else 1

    ok, msg = acquire_lock(run_id, break_lock=a.break_lock, dry=not a.apply)
    print("锁：%s" % msg)
    if not ok:
        print_playbook("lock.%s" % lock_state()[0].replace("-", "_"))
        return 2

    stopped = None
    called_skills = []          # via-skill 模式：本跑**该调**的层 skill（读 layers.yaml，声明侧）
    called_layers = []          # via-skill 模式：本跑真正走到的层（拓扑序）→ extra.layers
    declared_by_layer = {}      # 层 → [skill id]（声明侧；供 skill_invocation_audit 逐层对账）
    # ★ 批次27 第0块：落章引擎没跑成 / 没落章的层 —— **如实记缺口**，不静默（供记账见 extra）
    stamp_gaps = []
    # ── 驱动层写档闸门（批次8 加）：先解析凭据，再进循环 ────────────────────────
    gate_ok, gate_layers, gate_msg = load_write_gate(a.write_gate)
    unauthorized_layers = []
    readonly_declared = {str(x) for x in (a.readonly_layer or [])} - {"L7"}
    if a.via_skill:
        print("[写档闸门] %s" % gate_msg)
        if gate_ok:
            print("[写档闸门] 本跑授权层：%s（其余层一律只许只读档）"
                  % "、".join(sorted(gate_layers, key=lambda s: int(s[1:]))))
    try:
        for x in ordered:
            lid = x["layer"]
            # ── ★★ 批次23 · 第0块「甲1」：`cwd` 由**库根派生**，不再写死 ────────────
            # 病灶（批22 定位到代码并复现）：`layers.yaml` 每层 `cwd` 写死
            #   `~/.dsh/Momcozy知识库` ⇒ 子进程工作目录**永远**是它，与「在哪个副本里跑」无关；
            #   各层引擎又都用相对路径 `kb/...` ⇒ **全部落在真库**，副本里那份一个字没写
            #   ⇒ **「副本跑」静默失效**（本工程全部反测都依赖副本）。
            # 修法（甲1）：`layers.yaml` 的 cwd 改成**占位符** `{kb_root}`，此处替换为
            #   **本次库根**（= 本编排器所在 kb/ 的上一级，由脚本自身位置推，不读环境、不写死）。
            #   ⇒ 真库跑时**指向同一实体**（判据 = `kb/l0/registry/kb.json` 的
            #     **inode 两边均 `69082025`**、**sha256 两边均 `05de4939c370a9ac`**）；
            #     ★ **路径串是不同的**（改后指向库根本身，改前是 `~/.dsh/Momcozy知识库`）——
            #     本行初稿曾写「逐位相同」，**那是假话**，与批次23 第1块(a)的实测结论相反，已改。
            #     副本跑时**真的进副本**（实测：落章只进副本、真库该 RUN 0 件）。
            # ★ registry 里不再存假信息：`{kb_root}` 明说「这是从库根派生的」，而不是一个
            #   看似具体、实则与本次运行无关的绝对路径（与「登记在撒谎」同类，故不选甲2）。
            #   库根来源优先级：`KB_ROOT`（显式，供批次/副本用）→ 否则按**脚本自身位置**推。
            _kbr = os.path.abspath(os.path.expanduser(
                os.environ.get("KB_ROOT") or ROOT))
            cwd = home((x.get("cwd") or "{kb_root}").replace("{kb_root}", _kbr))
            # ── 驱动层写档闸门（批次8 加）：本层有没有「人开闸」凭据？────────────────
            # 只看 `--via-skill`（老路 `--apply` 由上面 SYNC_ALLOWED 那段管，不动它）。
            # ① 未带凭据 / 凭据查不到 → 本层**只许只读档**：显著告警，并把本层记入
            #    `unauthorized_layers`（记账时写进 extra，供审计与人核）。
            # ② 带了凭据、但本层**不在**凭据的 layers 里 → **直接拒（return 2）**，
            #    不与「顺手就跑」妥协 —— 这正是白名单当初的意图。
            if a.via_skill:
                if lid in readonly_declared:
                    print("[%s] 写档闸门：**本跑显式声明只读档**（--readonly-layer %s）→ "
                          "层引擎不得带 --apply，落章应为 applied=false。" % (lid, lid))
                    unauthorized_layers.append(lid)
                elif not gate_ok:
                    print("[%s] ⚠️ 写档闸门：%s" % (lid, gate_msg))
                    unauthorized_layers.append(lid)
                elif lid not in gate_layers:
                    print("=" * 84)
                    print("❌ 驱动层写档闸门**拒绝**：本层 %s 不在凭据 %s 的授权层里。"
                          % (lid, a.write_gate))
                    print("   %s" % gate_msg)
                    print("   授权范围外**不许真写**。要么换一份含 %s 的凭据，要么本层只跑只读档"
                          "（把 L%s 从 --only 里去掉）。" % (lid, lid[1:]))
                    print("=" * 84)
                    return 2
            # 红线③：写之前先跑本层闸门；红 → 立即停（不写这一层，更不往下走）
            gate = str(x.get("gate") or "")
            gm = re.match(r"\s*(kb/[A-Za-z0-9_./\-]+\.py)", gate)
            gscript = gm.group(1) if gm else None
            if gscript in GATE_WHITELIST:
                gok, gsumm = run_gate(gscript, GATE_WHITELIST[gscript], cwd, py)
                print("[%s] 闸门：%s ｜ %s" % (lid, "过" if gok else "**红**", gsumm))
                if not gok:
                    stopped = "%s 闸门红：%s" % (lid, gsumm)
                    print_playbook("gate_red.%s" % lid)
                    break
            else:
                print("[%s] 闸门：未纳入只读白名单 → 写档前无法自证，**停**" % lid)
                print_playbook("gate_missing.%s" % lid)
                stopped = "%s 没有可跑的白名单闸门" % lid
                break

            skills_here = _layer_skills(x)
            engines_here = _layer_engines(x)
            if a.via_skill:
                # ── 逐层调 skill（2026-09-30）：编排器**不跑层引擎**，引擎归该层 skill ──
                print("[%s] via-skill：本层该调的 skill ＝ %s"
                      % (lid, " → ".join(skills_here) if skills_here else "**layers.yaml 未声明 skill**"))
                for e in engines_here:
                    print("        ↳ 该 skill 内部照 layers.yaml 跑：%s" % e)
                if x.get("skill_write") is False:
                    print("        ↳ ⚠️ 本层 skill_write=false —— 该 skill 不写档（写档是显式登记的缺口，"
                          "不是漏填）：%s" % re.sub(r"\s+", " ", str(x.get("skill_note") or ""))[:80])
                called_skills.extend(skills_here)
                called_layers.append(lid)
                declared_by_layer[lid] = list(skills_here)

            specs = SYNC_SPEC.get(lid)
            if specs is None:
                if a.via_skill:
                    print("[%s] via-skill：编排器对本层无**写数据**引擎登记（旧口径：写档一律人工）——"
                          "本层写数据归 %s（skill_write=%s）"
                          % (lid, " → ".join(skills_here) or "**未声明 skill**", x.get("skill_write")))
                    # ★ 批次27 第0块：**写数据**没登记 ≠ **落章**没登记。落章引擎照传 --skill。
                    _sok, _ssum = run_stamp_engine(lid, x, cwd, py, run_id,
                                                   apply_ok=a.apply,
                                                   authorized=(gate_ok and lid in gate_layers))
                    if not _sok:
                        stamp_gaps.append("%s:%s" % (lid, _ssum))
                else:
                    print("[%s] 无写档引擎登记（该层写档一律人工，如 L0 的飞书 token 只有 ~2h 有效期）→ 只跑了闸门" % lid)
                continue
            if not specs:
                if a.via_skill and lid in STAMP_SPEC:
                    # L7 不在此表（跨层闸门 + 记账文件不能自证）→ 走到这里只有显式登记过的层
                    _sok, _ssum = run_stamp_engine(lid, x, cwd, py, run_id,
                                                   apply_ok=a.apply,
                                                   authorized=(gate_ok and lid in gate_layers))
                    if not _sok:
                        stamp_gaps.append("%s:%s" % (lid, _ssum))
                else:
                    print("[%s] 无写库引擎（索引/注册表/报告层）→ 只跑了闸门" % lid)
                continue

            # 红线①：写之前归档。**只在真落盘（--apply）时执行** ——
            # 归档是"写"动作，预演不写盘却留下 4.2MB/次的归档，会让"零写自证"变成空话
            # （2026-09-30 实测：两次预演各生成一份 kb/l3/_archive/rejected-pre-*.jsonl）。
            # 只想单独验证归档红线本身，用 `--check-archive`（不跑任何引擎）。
            if a.apply:
                aok, msgs = archive_before_write(lid, run_id)
                for m in msgs:
                    print("[%s] %s" % (lid, m))
                if not aok:
                    print_playbook("archive_failed.%s" % lid)
                    stopped = "%s 归档红线不通过" % lid
                    break
            elif ARCHIVE_BEFORE_WRITE.get(lid):
                print("[%s] 预演：跳过归档（归档只在 --apply 落盘前执行；"
                      "单验归档红线用 --check-archive）" % lid)

            if a.via_skill:
                # 逐层调 skill（2026-09-30）：编排器到此为止 —— **写数据的引擎**归该层 skill。
                # 红线①的归档**已经在本分支之前执行**（防御纵深：即使写的是 skill，归档也不省）。
                print("[%s] via-skill：引擎交给 %s（本编排器不跑；它只跑闸门 + 记账 + "
                      "**--skill 透传**）"
                      % (lid, " → ".join(skills_here) or "**未声明 skill**"))
                # ── ★★ 批次27 · 第0块：`--skill` 透传（关键路径）────────────────────
                # 本块只碰**落章引擎**这一支，写数据的引擎仍归该层 skill（上面那句不变）。
                # 判据：层落章同时带 `pipeline_run_id`（批次21 的 env）与 `skill`（本块 argv）。
                # ★ 批29 修：操作数顺序必须与 852/863 一致 —— `gate_ok and lid in gate_layers`。
                #   原写法 `lid in gate_layers and gate_ok` **先算 `in`**，而 `load_write_gate(None)`
                #   返回的 `gate_layers` 是 **None** ⇒ 不带 `--write-gate` 时必抛
                #   `TypeError: argument of type 'NoneType' is not iterable`，
                #   把 799-801 那条正当的「无凭据 → 只许只读档」分支整个打穿：
                #   `--sync --via-skill --only L4,L5,L6`（不带凭据）**必然崩**，走不到落章。
                #   只调顺序、**判定语义不变**（803/852/863 本就是这个写法）。
                _sok, _ssum = run_stamp_engine(lid, x, cwd, py, run_id,
                                               apply_ok=a.apply,
                                               authorized=(gate_ok and lid in gate_layers))
                if not _sok:
                    # 落章拿不到 ⇒ 这一层的「调了」没证据。**不让它静默过去**：
                    # 记进 stopped 由人看见，但**不阻断**（其余层照走，账如实留缺口）。
                    stamp_gaps.append("%s:%s" % (lid, _ssum))
                continue

            for sp in specs:
                # 干跑档真源 = layers.yaml 本层 dry_run（本表不再重复声明，见 SYNC_SPEC 上方注释）。
                # 取不到或不为 True → fail-closed：预演模式下拒绝执行（不猜、不默认放行）。
                dry_ok = x.get("dry_run")
                if not a.apply and dry_ok is not True:
                    print("[%s] %s **没有干跑档**（layers.yaml 的 %s.dry_run = %r，不是 true）"
                          "→ 预演模式下拒绝执行" % (lid, sp["script"], lid, dry_ok))
                    print_playbook("engine_failed.%s" % lid)
                    stopped = ("%s 的 %s 没有干跑档（layers.yaml dry_run 不是 true），预演跑不了"
                               % (lid, sp["script"]))
                    break
                argv = [py, os.path.join(cwd, sp["script"])]
                argv += [run_id if q == "RUN" else q for q in sp["args"]]
                if sp["apply"] and a.apply:
                    argv.append(sp["apply"])
                before = snapshot_mtimes(layers)
                # ── ★★ 批次21 · 第1块：把**编排器的 RUN 号**透传给层引擎 ──────────────
                # 为什么：落章契约（skill_invocation_audit.py:56-61）**早就支持**
                #   `pipeline_run_id == <编排RUN>` 这一支，`stamp_of()` 也早就实现读它（`:186`），
                #   但**全库没有写入者** ⇒ 各层引擎用自己的 RUN 写落章 ⇒ 审计在编排 RUN
                #   名下**查不到任何落章** ⇒ **E2 恒红**（声称层数越多红越多，实测 1→7）。
                # 本条只**注入一个环境变量**（不占层引擎的位置参数、不动其 argv 契约），
                #   层引擎在写落章前由 `kb/l7/scripts/stamp_meta.py` 读它并写 `pipeline_run_id`。
                # ★ **不改记账算法**：本行只影响子进程环境，`extra`/`record()` 一字未动。
                r = subprocess.run(argv, cwd=cwd, capture_output=True, text=True,
                                   env=dict(os.environ, KB_INTERP_OK="1",
                                            PYTHONDONTWRITEBYTECODE="1",
                                            KB_PIPELINE_RUN_ID=run_id),
                                   timeout=a.timeout)
                tail = [l for l in (r.stdout or "").strip().split("\n") if l.strip()][-2:]
                after = snapshot_mtimes(layers)
                changed = sorted(p for p in after if before.get(p) != after[p])
                print("[%s] %s exit=%d ｜ 产物变化 %d 个" % (lid, os.path.basename(sp["script"]),
                                                            r.returncode, len(changed)))
                for t in tail:
                    print("        %s" % t[:160])
                if r.returncode != 0:
                    for ln in (r.stderr or "").strip().split("\n")[-3:]:
                        if ln.strip():
                            print("        stderr: %s" % ln.strip()[:160])
                    print_playbook("engine_failed.%s" % lid)
                    stopped = "%s 的 %s 退出码 %d" % (lid, sp["script"], r.returncode)
                    break
                if a.apply and not changed:
                    print("        ↳ **幂等**：本次没有改动任何产物文件")
            if stopped:
                break
    finally:
        release_lock()

    # run 记录（P3）：写档档 = 人在环（--apply 必须人开闸）
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from run_record import record as _rr
        # ── --gate-only（2026-10-01 加）：只过闸门，**不记账** ──────────────────
        # 病灶（实测）：驱动循环每个 RUN 调本编排器两次（第 1 步过闸门 + 第 5 步带上报），
        #   两次都走 run_record → `kb/l7/runs/index.jsonl` 一个 RUN 落 2 行
        #   （实测 RUN=20261001-1121：11:20:45 registry_echo / 11:21:29 agent_reported），
        #   于是「跑了几层 / 几次」系统性双计；且 `<RUN>.json` 被后者覆盖，前者只剩 index 一行。
        # 改法：第 1 步用 `--gate-only`，本函数变成空操作；最终态由第 5 步那一次记账落。
        _rr_impl = _rr
        def _rr(**kw):                      # noqa: F811  （有意遮蔽，见上）
            if a.gate_only:
                return None
            return _rr_impl(**kw)
        if a.gate_only:
            print("[记账] --gate-only：本次**不写** kb/l7/runs/（只过闸门 + 持锁/释放）—— "
                  "最终态由带 --invoked 的那次记账落，一个 RUN 在 index.jsonl 里只留 1 行")
        # ★ 2026-10-01：`全走完` **不再对预演说**。
        #   病灶：原写法 `"全走完" if not stopped else (...)` 只反映「层有没有被触达」，
        #   不反映「有没有真落盘」—— 于是 `--sync`（预演、零写入）也写「全走完」。
        #   实测旧账 `kb/l7/runs/20260930-1740.json`：`verdict="全走完"` 却 `products: []`、
        #   `human_involved=false` —— 读记录的人会以为库被推进了，其实一个字节都没写。
        #   改法：预演写「全走完（预演 · 未落盘 · 非执行证据）」，**保留"全走完"四字在前**，
        #   不破坏按前缀读这个字段的既有消费者；真 `--apply` 才写「全走完」。
        if stopped:
            mode_txt = "停在 " + stopped
        elif a.apply:
            mode_txt = "全走完"
        else:
            mode_txt = "全走完（预演 · 未落盘 · 非执行证据）"
        if a.via_skill:
            # 逐层调 skill 模式（2026-09-30）：
            # ★ `skills` 必须写**实际调用的**，不许复述注册表 —— 否则该字段结构上不可能为假，
            #   就不能当证据（对照本库旧账：kb/l2/runs/20260929-1754-l2-unscheduled-run.json）。
            #   给了 `--invoked` → 写 agent 上报值，标 skill_evidence=agent_reported；
            #   没给 → 照旧写声明值，但**明确标 registry_echo**，让证据闸门判得出来它不算数。
            #   判据：kb/l7/scripts/skill_invocation_audit.py 的 E1（记账即复述）。
            #   去重保序（kb-ingest-extractor 在 L1/L2 各出现一次）；逐层明细留在 extra。
            declared_uniq = list(dict.fromkeys(called_skills))
            if a.invoked:
                reported = list(dict.fromkeys(a.invoked))
                skills_out = ["kb-pipeline"] + [s for s in reported if s != "kb-pipeline"]
                evidence = "agent_reported"
            else:
                skills_out = ["kb-pipeline"] + declared_uniq
                evidence = "registry_echo"

            # ── ★★ 批次18 · 第1块：把 `skills` 从**复述**改成**观测** ──────────────
            # 病灶（实测）：`skill_evidence=registry_echo` —— 该字段由**编排器复述注册表**生成，
            #   **无论真调没调都长这样**，所以 E1 判红「记账即复述、证据不成立」。
            #   ⇒ D1 要的是「**调用** L0-L7 逐层的 skills」，而复述**结构上不可能为假**，
            #     等于没有证据。
            # 修法：**观测** = 读各层引擎**自己写**的落章里的 `skill` 字段
            #   （`kb/<层>/runs/<RUN>*.json`）。编排器**只读不写**（落章永远由执行该层的进程写），
            #   且**只认非预演落章**（`applied is True` / `dry_run` 非真）——
            #   预演台账**不构成执行证据**（同一批已为 E5 定过这条口径）。
            # 观测不到 ⇒ **照旧标 registry_echo**（诚实：不假装有观测），E1 该红就红。
            _obs, _obs_src = [], []
            for _lid in called_layers:
                _st_obs = _layer_stamps(_lid, run_id)
                for _k in ("applied", "unknown"):
                    for _r, _rec in _st_obs[_k]:
                        # `unknown` = 老式落章（没有 applied/dry_run 字段）：**不计入观测**，
                        # 与 E5 同口径（老落章不算落盘证据）。只有 `applied` 才算。
                        if _k != "applied":
                            continue
                        _sv = _rec.get("skill")
                        # ★★ 批次27 · 第0块：落章的 `skill` **可以是列表** —— L1 声明两个 skill
                        #   （`skill: [kb-ingest-extractor, kb-media-extractor]`），
                        #   `align_l1_manifest.py:50-55` 按序收成 **list** 写进落章。
                        #   判据侧本来就认列表（`skill_invocation_audit.py` 的 `SKILL_KEYS`
                        #   一律走 `_as_list`），而这里原先按**标量**用 ⇒ 下游 `set(_obs)`
                        #   抛 `TypeError: unhashable type: 'list'`，**把整段记账打崩**
                        #   （实测 20261002-2056：`[warn] run_record 没写成`，run 账一个字没落）。
                        #   本行把它摊平成字符串列表 —— 与判据侧**同一口径**，写进去的仍是
                        #   「观测到的 skill 集合」，**不改记账算法**。
                        _sl = ([str(_x) for _x in _sv] if isinstance(_sv, list)
                               else ([str(_sv)] if _sv else []))
                        for _s in _sl:
                            if _s and _s not in _obs:
                                _obs.append(_s)
                        # ★★ 批次27 · 第0块（实测逼出来的第二处）：**层来源要按「落章」记，
                        #   不能按「skill 是不是新的」记**。原先 `_obs_src.append` 写在
                        #   `if _s not in _obs` **里面** ⇒ 一个 skill 被两层共用时（实测：
                        #   L1 与 L2 **都**声明 `kb-ingest-extractor`，L2 的 skill 与 L1 相同
                        #   ⇒ 不新 ⇒ 不记来源）⇒ 下面 `called_layers = {来源里的层}`
                        #   **把 L2 静默丢掉**（run 20261002-2057 实测：落章 7 份、`layers`
                        #   只写 6 层）。后果是**审计范围自己缩小**：少的那层不再被 E2 要求
                        #   落章 ⇒ 绿得比事实宽。
                        #   ⇒ 本行把它提到去重之外：**每份带 skill 的落章都记来源**。
                        #   只改「观测到哪些层」这一项，且**只让范围变大、不变小**（更难过）。
                        if _sl:
                            _obs_src.append("%s:%s" % (_lid, _r))
            if _obs:
                # ★ 观测优先：`skills` 写**观测到的**（不是声明的）。
                skills_out = ["kb-pipeline"] + [s for s in _obs if s != "kb-pipeline"]
                evidence = "layer_stamps_observed"
                _obs_note = "观测来源＝层落章（非预演）：%s" % "、".join(_obs_src)
                # ★★ 批次18 · 第1块（漏调一层的反测逼出来的）：**`layers` 也必须改成观测集**。
                #   原先 `layers` 写的是 `called_layers`（= **声明**该走哪几层）。
                #   于是「落章齐不齐」这个检查**结构上不可能失败** —— 闸门只遍历 `layers`，
                #   而 `layers` 本来就是声明，漏调的那层**根本不在遍历范围里**。
                #   实测：夹具里 L1 无落章，E1 仍为 0（假阴），是**自证循环**。
                #   ⇒ `layers` 改为**实际观测到非预演落章的层**；只有真落了章的层才算走到。
                called_layers = sorted({_src.split(":")[0] for _src in _obs_src})
                if set(_obs) != set(declared_uniq):
                    # 观测与声明不一致 ⇒ **如实留痕**，不抹平（这正是要看见的东西）
                    print("⚠️ [记账] 观测到的 skill 与声明不一致：观测=%s ｜ 声明=%s"
                          % (_obs, declared_uniq))
                _declared_not_observed = [s for s in declared_uniq if s not in _obs]
                if _declared_not_observed:
                    print("⚠️ [记账] 声明要走、但**观测不到落章**的 skill：%s（漏调？）"
                          % _declared_not_observed)
            else:
                _obs_note = ("该 RUN 在 kb/<层>/runs/ 里**读不到任何非预演落章**"
                             "⇒ 无观测值，退回注册表声明（skill_evidence=registry_echo）")

            # ── 记账实测化（2026-10-01 加，A 块）：三格贴事实，不再结构性恒假 ────────
            # ① human_involved：本模式下 a.apply **恒 False** ⇒ 旧写法恒假。
            #    这一格是 run_record.py 说的「这套记录存在的理由」，必须贴事实：
            #    传了 `--invoked` = agent 按层 skill 正文走过一遍 = **人在环**。
            # ② verdict / ③ products：读**层侧落章实测**（层引擎自己写的），不猜、不代写。
            #    有真落盘层（applied 显式 true）→ 纯「全走完」（四字保留在前，既有消费者按前缀读）；
            #    只有预演台账 → 保留「（预演 · 未落盘 · 非执行证据）」；
            #    层还没落章 / 中途停下 → 退回现状文案（边界：不许崩，也不许把停下写成全走完）。
            human_out = bool(a.invoked)
            st_all = {"applied": [], "dry": [], "unknown": [], "errors": []}
            prods = []
            for _lid in called_layers:
                _st = _layer_stamps(_lid, run_id)
                for _k in ("applied", "dry", "unknown"):
                    st_all[_k].extend(["%s:%s" % (_lid, r) for r, _rec in _st[_k]])
                    for _r, _rec in _st[_k]:
                        for _p in _stamp_products(_r, _rec):
                            if _p not in prods:
                                prods.append(_p)
                st_all["errors"].extend(["%s:%s" % (_lid, e[0]) for e in _st["errors"]])
            if stopped or not (st_all["applied"] or st_all["dry"] or st_all["unknown"]):
                verdict_out = mode_txt
                basis = "层侧无落章或中途停下 → 退回现状文案"
            elif st_all["applied"]:
                verdict_out = "全走完"
                basis = "层侧落章 applied=true → 真落盘"
            else:
                verdict_out = "全走完（预演 · 未落盘 · 非执行证据）"
                basis = "层侧落章全是预演台账 → 未落盘"
            print("[记账] 层侧落章实测：applied %d ｜ dry %d ｜ unknown %d ｜ 读错 %d"
                  " → human_involved=%s ｜ verdict=%s"
                  % (len(st_all["applied"]), len(st_all["dry"]), len(st_all["unknown"]),
                     len(st_all["errors"]), human_out, verdict_out))
            extra_out = {"via_skill": True, "skill_invoked_by": "agent",
                         "skill_evidence": evidence,
                         # ★ 批次18 · 第1块：`skills` 是**观测值还是复述值**，及其来源。
                         # 这是 E1 的判据口：`skill_evidence=layer_stamps_observed` 才算观测。
                         "skill_evidence_note": _obs_note,
                         "observed_skills": _obs,
                         "observed_skills_sources": _obs_src,
                         "layers": called_layers,
                         "layer_skills": called_skills,
                         "declared_layer_skills": declared_by_layer,
                         "layer_skills_uniq": declared_uniq,
                         "invoked_reported": list(a.invoked or []),
                         "skill_sessions": skill_sessions,
                         "human_involved_basis": ("--invoked 已上报（agent 按层 skill 走过）"
                                                  if a.invoked else "无 --invoked 上报"),
                         "verdict_basis": basis,
                         "layer_stamps_applied": st_all["applied"],
                         "layer_stamps_dry": st_all["dry"],
                         "layer_stamps_unknown": st_all["unknown"],
                         # 驱动层写档凭据留痕（批次8 加）：谁开的闸、覆盖哪些层、哪些层没被覆盖
                         "write_gate": {"id": a.write_gate, "resolved": gate_ok,
                                        "layers_authorized": (sorted(gate_layers,
                                                                     key=lambda s: int(s[1:]))
                                                              if gate_layers else None),
                                        "unauthorized_layers": unauthorized_layers,
                                        "readonly_declared": sorted(readonly_declared),
                                        "msg": gate_msg}}
            if st_all["errors"]:
                extra_out["stamp_read_error"] = st_all["errors"]
            _rr(source="pipeline_sync",
                trigger="--sync --via-skill " + (a.only or ("all" if a.all_layers else "")),
                skills=skills_out,
                commands=["kb/kbpy l7/scripts/kb_pipeline.py --sync --via-skill %s%s --run %s%s%s"
                          % (("--only " + a.only) if a.only else "--all",
                             " --apply" if a.apply else "", run_id,
                             "".join(" --invoked " + s for s in (a.invoked or [])),
                             "".join(" --skill-session " + s for s in (a.skill_session or [])))],
                products=prods, verdict=verdict_out, human_involved=human_out,
                run_id=run_id, extra=extra_out)
        else:
            _rr(source="pipeline_sync", trigger="--sync " + (a.only or ("all" if a.all_layers else "")),
                skills=["kb-pipeline"],
                commands=["kb/kbpy l7/scripts/kb_pipeline.py --sync %s%s"
                          % (("--only " + a.only) if a.only else "--all", " --apply" if a.apply else "")],
                products=[], verdict=mode_txt,
                human_involved=bool(a.apply), run_id=run_id)
    except Exception as exc:              # noqa: BLE001
        print("[warn] run_record 没写成：%r" % (exc,))

    print("-" * 84)
    if stopped:
        print("**已在 %s 停下**（红线：遇红即停，后面的层不跑）" % stopped)
        print("要人做什么：看上面那一层的闸门/引擎输出；修好之后重跑同一条命令。")
        return 1
    print("结论：%s 全部走完（%s）" % ("、".join(x["layer"] for x in ordered), mode))
    if not a.apply:
        print("提示：这是预演。真正落盘要加 --apply，且当前白名单只开 %s。" % SYNC_ALLOWED)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="知识库 L0–L7 执行编排器（--check 零写体检 / --sync 写档编排）")
    ap.add_argument("--check", action="store_true", help="零写体检（不执行任何会写盘的层引擎）")
    ap.add_argument("--no-gates", action="store_true", help="只做静态校验，不跑闸门")
    ap.add_argument("--only", default=None, help="只看/只跑某一层，如 L3")
    ap.add_argument("--from", dest="from_layer", default=None, help="从某层起（拓扑序）")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--sync", action="store_true", help="写档编排（默认预演；加 --apply 才落盘）")
    ap.add_argument("--via-skill", action="store_true",
                    help="逐层调该层 skill（2026-09-30 加）：编排器不跑层引擎，只跑闸门 + 归档 + 锁 + 记账；"
                         "该调哪个 skill 读 layers.yaml 各层 skill: 字段。默认关（不带时行为与旧版一致）")
    ap.add_argument("--invoked", action="append", default=None, metavar="SKILL_ID",
                    help="--sync --via-skill 时，agent **实际加载过**的层 skill id（可重复）。"
                         "如 --invoked kb-l0-feishu --invoked kb-ingest-extractor。"
                         "不传 = skills 记声明值并标 skill_evidence=registry_echo"
                         "（证据闸门 skill_invocation_audit.py 会判它不算证据）")
    ap.add_argument("--skill-session", action="append", default=None, metavar="Lx=SESSION_ID",
                    help="--sync --via-skill 时，执行某层的 subagent 会话标识（可重复），"
                         "如 --skill-session L2=<session-id> → 写进 run 记录 extra.skill_sessions"
                         "（形如 {\"L2\": \"<session-id>\"}），记「本层由哪个会话执行」。"
                         "★ 它**不是落章**：落章（kb/<layer>/runs/ 里的 skill 字段）必须由执行该层的"
                         "进程自己写；编排器代写即 registry_echo、不能当证据（见 skill_invocation_audit.py E1/E2）")
    ap.add_argument("--gate-only", action="store_true",
                    help="驱动循环第 1 步专用：只过闸门 + 持锁/释放，**不写 kb/l7/runs/**。"
                         "为什么：驱动循环每个 RUN 会调本编排器两次（第 1 步过闸门、第 5 步带上报），"
                         "两次都记账会让 kb/l7/runs/index.jsonl 一个 RUN 落 2 行"
                         "（registry_echo + agent_reported）→ 统计层数/次数系统性双计。"
                         "用了本开关，一个 RUN 只剩 1 行、且是最终态。"
                         "与 --apply / --invoked / --skill-session 互斥（传了会被丢掉，故 fail-closed）")
    ap.add_argument("--apply", action="store_true", help="--sync 时真正落盘")
    ap.add_argument("--all", dest="all_layers", action="store_true", help="--sync 时点名整链（风险自负）")
    ap.add_argument("--run", default=None, help="run_id（默认取墙钟 YYYYMMDD-HHMM）")
    ap.add_argument("--timeout", type=int, default=3600, help="单个引擎超时秒数")
    ap.add_argument("--break-lock", action="store_true", help="撬掉 .kb.lock（只准人用）")
    ap.add_argument("--allow-beyond-policy", action="store_true",
                    help="越过写档白名单 %s（只准人用）" % SYNC_ALLOWED)
    ap.add_argument("--check-archive", action="store_true",
                    help="只验红线①的归档动作，不跑任何引擎（给反测用）")
    # ── 驱动层（--via-skill）的人开闸凭据（批次8 加，2026-10-01）────────────────
    # 病灶：`--via-skill` 路径上编排器**永远不带 `--apply`**（本文件 :440 原文），
    #   于是 :540 那段 `if a.apply and beyond ...` 白名单检查**从不触发**；
    #   写动作实际发生在**层引擎**（subagent 带 --apply 跑），编排器看不见
    #   ⇒ 契约 #7 第三条「人开闸」在这条路上**只有口头约定、没有代码凭据**。
    # 本开关把它变成可查凭据：命中 `kb/l7/registry/write-gate.yaml` 的某条 `id` 才算开闸。
    ap.add_argument("--write-gate", default=None, metavar="GATE_ID",
                    help="驱动层人开闸凭据（= kb/l7/registry/write-gate.yaml 的某条 id）；"
                         "不带 → 各层按「只许只读档」对待")
    # 显式「本层本跑按只读对待」的声明（批次8 加）。为什么要有它：没有它，一份**不含** Lx 的
    # 凭据会让 Lx 连第 1 步（只过闸门）与第 5 步（记账）都进不来 —— 那两步**不写层数据**，
    # 拒它们是过度拦截。显式声明把「L0 本批按只读跑」从**遗漏**变成**留痕的决定**。
    ap.add_argument("--readonly-layer", action="append", default=None, metavar="Lx",
                    help="声明本层本跑只跑只读档（可重复）；无需写档凭据，但会记进 extra.write_gate")
    a = ap.parse_args()
    if a.via_skill and not a.sync:
        print("--via-skill 只在 --sync 下有意义（逐层调 skill 的编排模式）。"
              "要零写体检请用 --check。", file=sys.stderr)
        return 2
    if a.invoked and not a.via_skill:
        print("--invoked 只在 --sync --via-skill 下有意义（它是「这一跑真加载了哪些层 skill」的上报）。",
              file=sys.stderr)
        return 2
    if a.skill_session and not a.via_skill:
        print("--skill-session 只在 --sync --via-skill 下有意义（它是「本层由哪个 subagent 会话执行」的留痕）。",
              file=sys.stderr)
        return 2
    if a.skill_session and any("=" not in s for s in a.skill_session):
        print("--skill-session 要写成 Lx=<会话标识>，如 --skill-session L2=kb-layer-L2-kb-ingest-extractor；"
              "收到 %s" % [s for s in a.skill_session if "=" not in s], file=sys.stderr)
        return 2
    if a.gate_only and not (a.sync and a.via_skill):
        print("--gate-only 只在 --sync --via-skill 下有意义（它是驱动循环第 1 步的「只过闸门、不记账」挡）。",
              file=sys.stderr)
        return 2
    if a.gate_only and a.apply:
        print("--gate-only 与 --apply 互斥：前者只过闸门、不落记账，后者要执行写档编排"
              "（含归档红线①）。要单验归档用 --check-archive。", file=sys.stderr)
        return 2
    if a.gate_only and (a.invoked or a.skill_session):
        print("--gate-only 与 --invoked / --skill-session 互斥：后两者是「带上报的那次记账」才有的东西，"
              "--gate-only 不写记录，传了会被静默丢掉 —— 故在这里拒收，不静默。", file=sys.stderr)
        return 2
    if a.sync:
        import yaml  # noqa: F401  （run_sync 里要用）
        return run_sync(a)
    if not a.check:
        print("要写档请用 --sync（默认预演）；只做零写体检请用 --check。", file=sys.stderr)
        return 2

    reg = os.path.join(KB, "l7", "registry", "layers.yaml")
    if not os.path.isfile(reg):
        print("找不到 %s" % reg, file=sys.stderr); return 2
    try:
        import yaml
    except ImportError:
        print("需要 PyYAML（请用 kb/kbpy 或 /usr/bin/python3 运行）", file=sys.stderr); return 2
    doc = yaml.safe_load(open(reg, encoding="utf-8"))
    layers = doc.get("layers") if isinstance(doc, dict) else doc
    ordered = topo_sort(layers)

    if a.only:
        ordered = [x for x in ordered if x["layer"] == a.only]
    elif a.from_layer:
        ids = [x["layer"] for x in ordered]
        if a.from_layer in ids:
            ordered = ordered[ids.index(a.from_layer):]

    py = read_config()
    py_ok = bool(py) and os.access(py, os.X_OK)
    before = snapshot_mtimes(layers)          # 零写自证：跑前快照

    rows, hard = [], []
    # ★ 2026-10-02 修（P0-a）：`layers.yaml` 各层 cwd 已改成占位符 `{kb_root}`
    #   （批次23「甲1」：让副本跑真的进副本）。但那次只改了 `--sync` 那条路径（本文件
    #   `cwd = home(...).replace("{kb_root}", _kbr)`），**`--check` 这条漏了** ——
    #   于是这里拿到字面量 `"{kb_root}"` 去 isdir ⇒ 8 层 cwd/engine/inputs/outputs 全红。
    #   实测：2026-10-02 `--check` 报「闸门脚本不存在: kb/l7/scripts/l0_gate.py」（文件其实在）。
    #   口径与 `--sync` 那条**逐字一致**（同一个 _kbr 推导式），避免两条路径再次分叉。
    _kbr = os.path.abspath(os.path.expanduser(
        os.environ.get("KB_ROOT") or ROOT))
    for x in ordered:
        lid = x["layer"]
        cwd = home((x.get("cwd") or "{kb_root}").replace("{kb_root}", _kbr))
        eng = x.get("engine") or []
        if isinstance(eng, str): eng = [eng]
        # 1) cwd
        cwd_ok = bool(cwd) and os.path.isdir(cwd) and \
            os.path.realpath(os.path.join(cwd, "kb")) == os.path.realpath(KB)
        # 2) engine 在位
        miss_eng = [e for e in eng if not os.path.exists(home(e) if os.path.isabs(home(e))
                    else os.path.join(cwd, str(e)))]
        # 3) inputs 里像路径的
        miss_in = []
        for i in (x.get("inputs") or []):
            if not looks_like_path(i):
                continue
            if is_glob(i):
                if not has_match(i, cwd):
                    miss_in.append(i + "（glob 无匹配）")
            else:
                q = home(strip_placeholder(i))
                q = q if os.path.isabs(q) else os.path.join(cwd, strip_placeholder(i))
                if not os.path.exists(q):
                    miss_in.append(i)
        # 4) outputs 父目录
        miss_out = []
        for o in (x.get("outputs") or []):
            if not looks_like_path(o):
                continue
            base = strip_placeholder(o)
            par = os.path.dirname(base)
            p = par if os.path.isabs(home(par)) else os.path.join(cwd, par)
            if not os.path.isdir(home(p)):
                miss_out.append(par)
        # 5) gate 分类与执行
        gate = str(x.get("gate") or "")
        gm = re.match(r"\s*(kb/[A-Za-z0-9_./\-]+\.py)", gate)
        gscript = gm.group(1) if gm else None
        gstate, gsumm = "声明式（表达式/契约，无独立脚本）", ""
        if gscript and gscript in GATE_WHITELIST:
            if a.no_gates:
                gstate, gsumm = "只读闸门（--no-gates 已跳过）", ""
            else:
                ok, gsumm = run_gate(gscript, GATE_WHITELIST[gscript], cwd, py or sys.executable)
                gstate = "只读闸门 通过" if ok else "只读闸门 **未过**"
                if not ok:
                    hard.append("%s 闸门未过：%s" % (lid, gsumm))
        elif gscript and gscript in GATE_NOT_RUN_REASON:
            gstate, gsumm = "未执行", GATE_NOT_RUN_REASON[gscript]
        elif gscript:
            gstate, gsumm = "未执行", "有序脚本但未纳入只读白名单（需参数或写行为未验证）"

        rows.append(dict(layer=lid, cwd_ok=cwd_ok, n_eng=len(eng), miss_eng=miss_eng,
                         miss_in=miss_in, miss_out=miss_out, gate_state=gstate,
                         gate_summary=gsumm, envelope=x.get("envelope"),
                         dry_run=x.get("dry_run"), write_mode=x.get("write_mode"),
                         skills=_layer_skills(x), skill_write=x.get("skill_write")))
        if not cwd_ok: hard.append("%s cwd 不合格：%s" % (lid, x.get("cwd")))
        if miss_eng:   hard.append("%s 引擎悬空 %d 个：%s" % (lid, len(miss_eng), miss_eng[:2]))
        if miss_in:    hard.append("%s 输入缺失 %d 个：%s" % (lid, len(miss_in), miss_in[:2]))
        if miss_out:   hard.append("%s 产出父目录不存在 %d 个：%s" % (lid, len(miss_out), miss_out[:2]))
        if x.get("envelope") == "required" and x.get("dry_run") is False:
            rows[-1]["note"] = "该层声明 dry_run=false（写档不可预演）"

    after = snapshot_mtimes(layers)            # 零写自证：跑后快照
    changed = [p for p in before if after.get(p) != before[p]]

    if a.json:
        print(json.dumps(dict(zero_write=not changed, changed=changed, layers=rows,
                              hard=hard, py=py, py_ok=py_ok), ensure_ascii=False, indent=1))
        return 0 if not hard and not changed else 1

    print("=" * 84)
    print("知识库 L0–L7 执行编排器 · --check（零写档）")
    print("=" * 84)
    print("库根      : %s" % KB)
    print("解释器    : %s %s" % (py or "(未配置)", "✅" if py_ok else "**不合格**"))
    print("层数      : %d（拓扑序：%s）" % (len(rows), " → ".join(r["layer"] for r in rows)))
    print("闸门执行  : %s" % ("已跳过（--no-gates）" if a.no_gates else ("只读白名单 %d 个" % len(GATE_WHITELIST))))
    print()
    hdr = "%-4s %-5s %-6s %-9s %-8s %-8s %s" % ("层", "cwd", "engine", "inputs", "outputs", "干跑档", "闸门")
    print(hdr); print("-" * 84)
    for r in rows:
        print("%-4s %-5s %-6s %-9s %-8s %-8s %s" % (
            r["layer"], "✅" if r["cwd_ok"] else "❌",
            "✅%d" % r["n_eng"] if not r["miss_eng"] else "❌%d/%d" % (len(r["miss_eng"]), r["n_eng"]),
            "✅" if not r["miss_in"] else "❌%d" % len(r["miss_in"]),
            "✅" if not r["miss_out"] else "❌%d" % len(r["miss_out"]),
            "有" if r["dry_run"] else "**无**",
            r["gate_state"] + (" ｜ " + r["gate_summary"] if r["gate_summary"] else "")))
    print("-" * 84)
    print("逐层 skill（`layers.yaml` → `skill:` 字段；唯一真源）")
    for r in rows:
        tag = "✅ 写档" if r.get("skill_write") else "⚠️ 只读/闸门（写档是显式登记的缺口）"
        print("  %-3s → %-42s %s" % (r["layer"],
                                     " → ".join(r.get("skills") or []) or "**未声明 skill**", tag))
    print("  `--sync --via-skill` 时按此逐层调用；引擎不在这里跑（归该层 skill）。")
    print()
    print("零写自证  : %s（产出文件 mtime 快照 %d 个，变化 %d 个）"
          % ("✅ 未写任何文件" if not changed else "❌ 有文件被改动", len(before), len(changed)))
    for c in changed[:5]:
        print("    X %s" % c)
    print()
    if hard:
        print("硬问题 %d 条：" % len(hard))
        for h in hard:
            print("   - %s" % h)
    else:
        print("硬问题：无 ✅")
    skipped = [r["layer"] for r in rows if r["gate_state"].startswith("未执行")]
    if skipped:
        print("闸门未执行的层：%s（各自原因见上表；**不是静默跳过**）" % "、".join(skipped))
    print("结论：%s" % ("全过" if not hard and not changed else "有问题"))
    print("说明：本次是 `--check`（零写体检）。写档走 `--sync`，仍需人工开闸：它按层序逐层调 `--apply`，"
          "而**干跑档已于 P0-3/P0-3d（2026-09-29）补齐** —— 8 个会改库数据的脚本"
          "（reconcile_l0_feishu / ocr_attachments / l3_distill_run / drill_links_2levels / "
          "l4_article / l5_prep / "
          "l5_export / l6_build）均支持 --apply，闸门位次在各自第一个副作用之前。")
    return 0 if not hard and not changed else 1


if __name__ == "__main__":
    sys.exit(main())
