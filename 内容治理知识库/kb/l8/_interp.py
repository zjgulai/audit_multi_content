#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""KB 解释器约定 —— 唯一真源。

背景（2026-09-29 实测）：同一条命令在会话中途"有时成功有时崩"。
  早先 PATH 里的 python3 = /usr/bin/python3            → numpy 2.0.2 ✅
  后来 PATH 里的 python3 = 受管 external-tools python   → numpy / fastembed 全缺 ❌
而 L6 召回**必须**两者俱全（l6/retriever.py:245 `np.load(matrix.npy)`；
:249 `from fastembed import TextEmbedding` 现算 query 向量）。

本机唯一满足的解释器是 /usr/bin/python3。**受管 python 由宿主注入、会随会话变化，
所以绝不能靠 PATH** —— 解释器必须显式写进库：kb/.kb-python。

约定：
  1. 配置写在 `kb/.kb-python`（单行绝对路径）。本模块从任意深度向上查找它。
  2. 用它跑任何 KB 脚本：`kb/kbpy <相对路径> [args...]`
  3. 也可给脚本加"解释器守卫"（本库已给官方入口脚本加上）：不合格就自动 re-exec。
  4. 都不满足时 **报错退出，不静默降级** —— 静默降级会让失败点漂移。

CLI：
    python3 kb/l8/_interp.py            # 报告：配置 / 解析结果 / 当前解释器是否合格
    python3 kb/l8/_interp.py --verify   # 只校验，不合格退出 1（给闸门用）
"""

from __future__ import annotations

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

import os
import subprocess
import sys

CONFIG_NAME = ".kb-python"
# L6 召回的硬依赖；缺任一即不合格
REQUIRED = ("numpy", "fastembed")
# 候选顺序（仅在前两项都拿不到时兜底；正常走 KB_PYTHON → kb/.kb-python）
FALLBACKS = ("/usr/bin/python3", "/opt/homebrew/bin/python3", "/usr/local/bin/python3")
GUARD_ENV = "KB_INTERP_OK"


class InterpError(RuntimeError):
    pass


def find_config(start: str | None = None) -> str | None:
    """从 start（默认本文件所在目录）向上查找 kb/.kb-python。"""
    d = os.path.abspath(start or os.path.dirname(os.path.abspath(__file__)))
    while True:
        p = os.path.join(d, CONFIG_NAME)
        if os.path.isfile(p):
            return p
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent


def configured(start: str | None = None) -> str | None:
    """读配置里的解释器路径（去空行/注释）。"""
    p = find_config(start)
    if not p:
        return None
    try:
        for ln in open(p, encoding="utf-8"):
            ln = ln.split("#", 1)[0].strip()
            if ln:
                return os.path.expanduser(ln)
    except OSError:
        return None
    return None


def verify(exe: str) -> tuple[bool, str]:
    """这个解释器能满足 REQUIRED 吗？返回 (ok, 说明)。"""
    if not exe or not os.path.isfile(exe) or not os.access(exe, os.X_OK):
        return False, "不可执行或不存在"
    code = ("import importlib,sys\n"
            "miss=[]\n"
            "for m in %r:\n"
            "    try: importlib.import_module(m)\n"
            "    except Exception: miss.append(m)\n"
            "print(','.join(miss))\n" % (list(REQUIRED),))
    try:
        r = subprocess.run([exe, "-c", code], capture_output=True, text=True, timeout=120)
    except Exception as e:                       # noqa: BLE001
        return False, "探测失败：%s" % e
    miss = (r.stdout or "").strip()
    if r.returncode != 0:
        return False, "探测退出码 %d：%s" % (r.returncode, (r.stderr or "").strip()[:120])
    if miss:
        return False, "缺模块：%s" % miss
    return True, "ok（%s 齐全）" % "/".join(REQUIRED)


def candidates(start: str | None = None) -> list[str]:
    out = []
    for c in (os.environ.get("KB_PYTHON"), configured(start), *FALLBACKS, sys.executable):
        if c and c not in out:
            out.append(c)
    return out


def resolve(start: str | None = None, strict: bool = True) -> str:
    """解析出合格解释器；都不合格时：
       strict=True  → 抛 InterpError（默认，绝不静默降级）
       strict=False → 返回 None
    """
    tried = []
    for c in candidates(start):
        ok, why = verify(c)
        tried.append("  %s → %s" % (c, why))
        if ok:
            return c
    if not strict:
        return None
    raise InterpError(
        "找不到合格解释器（需 %s）。已试：\n%s\n"
        "修法：把合格解释器的绝对路径写进 kb/%s（或设 $KB_PYTHON）。"
        % (" + ".join(REQUIRED), "\n".join(tried), CONFIG_NAME))


def ensure(start: str | None = None) -> None:
    """守卫用：当前解释器不合格 → 用合格的解释器 re-exec 自己。
    用 GUARD_ENV 防循环。不合格且不可 re-exec 时抛 InterpError。"""
    if os.environ.get(GUARD_ENV):
        return
    want = resolve(start, strict=True)
    if os.path.realpath(want) == os.path.realpath(sys.executable):
        return
    script = os.path.abspath(sys.argv[0] or "")
    if not script or not os.path.isfile(script):
        raise InterpError("无法 re-exec：拿不到脚本路径（%r）" % sys.argv[0])
    env = dict(os.environ, **{GUARD_ENV: "1"})
    os.execve(want, [want, script] + sys.argv[1:], env)


def main() -> int:
    args = sys.argv[1:]
    cfg = find_config()
    print("配置文件      : %s" % (cfg or "（未找到）"))
    print("配置的解释器  : %s" % (configured() or "（空）"))
    print("$KB_PYTHON    : %s" % (os.environ.get("KB_PYTHON") or "（未设）"))
    print("当前解释器    : %s" % sys.executable)
    ok_cur, why_cur = verify(sys.executable)
    print("  是否合格    : %s — %s" % ("是" if ok_cur else "**否**", why_cur))
    print("候选清单：")
    for c in candidates():
        ok, why = verify(c)
        print("  %-58s %s — %s" % (c, "OK " if ok else "NG ", why))
    try:
        want = resolve()
        print("解析结果      : %s" % want)
        if "--verify" in args:
            return 0 if ok_cur else 1
        return 0
    except InterpError as e:
        print("解析结果      : **失败**\n%s" % e)
        return 1


if __name__ == "__main__":
    sys.exit(main())
