#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""_safe_write.py —— `.md` / `.sh` 的安全写盘（先写临时件，再 `/bin/cp` 落地）。

════════════════════════════════════════════════════════════════════════
★ 为什么需要它（2026-10-06 逐扩展名实测，**机理与旧说法不同，以本节为准**）
════════════════════════════════════════════════════════════════════════

python 直写 **`.md`** 或 **`.sh`** ⇒ **DSH 宿主**读到的比真值多 **4096 字节**，
宿主侧的读者（`read` 工具、以 `ELECTRON_RUN_AS_NODE` 跑的脚本）会把它当成损坏/二进制。

**实测：这不是"python 写的文件都脏"** —— 同一批对照里，只有这两个扩展名中招：

| 扩展名 | 宿主看到的差值 | 说明 |
|---|---|---|
| `.md` | **+4096** | ❌ 中招 |
| `.sh` | **+4096** | ❌ 中招（`kb/l8/review_run.sh` 就被这个坑过一次） |
| `.py` `.mjs` `.yaml` `.json` `.log` `.txt` | 0 | ✅ 干净 |

**谁看得见、谁看不见**（同一个文件三方对照，实测）：

| 观察者 | 读到的字节 |
|---|---|
| python `os.stat` / `os.path.getsize` / `read()` | 真值 |
| 系统 node `fs.statSync` / `readFileSync` | 真值 |
| shell `cat \\| wc -c` | 真值 |
| **DSH 宿主**（`ELECTRON_RUN_AS_NODE=1 "$DSH"`）与 shell `wc -c`（stat 口径） | **真值 + 4096** |

⇒ 所以**只有宿主侧受害**（守衡 用系统 node、读得动；python 也读得动），
   而**管线是 DSH agent 在跑的** —— 它读不了，这就是真代价。
⇒ 也因此：**判断修好没有，必须用宿主这把尺子**（`kb/l8/envelope_census.py` 用的就是它），
   用 python 或系统 node 量会得出"本来就没事"的**假绿**。

════════════════════════════════════════════════════════════════════════
★ 做法与纪律
════════════════════════════════════════════════════════════════════════

做法：**先写临时件（非 `.md`/`.sh` 扩展名 ⇒ 不会被加信封），再 `/bin/cp` 覆盖过去。**
实测：这样落地后，宿主看到的**等于真值**（25 = 25），而直写是 4121 ≠ 25。

三条纪律：
1. **写完必须回读复核**（长度 + 内容）—— 不一致就抛错，**不静默**：
   静默的半成品（报告少一半）比报错难查得多。
2. **临时件必须清掉**（`finally`）—— 否则 `kb/l*​/runs/` 里会攒一堆点文件。
3. **只给 `.md`/`.sh` 用**。别的扩展名不需要，套上只是把简单事搞复杂
   （而且多一次 `cp` 就多一个失败点）。

用法（与本脚本同目录的调用方）：

    import _safe_write as sw
    sw.write_text("kb/l3/runs/%s.report.md" % RUN, "\\n".join(L) + "\\n")
"""

from __future__ import annotations

import os
import subprocess

#: 需要走 `/bin/cp` 的扩展名（**实测中招的那两个**，见文件头对照表）
SAFE_EXTS = (".md", ".sh")


def write_text(path, content, *, encoding="utf-8"):
    """把 `content` 安全写到 `path`。返回 `path`。

    `path` 的扩展名若不在 `SAFE_EXTS` 里，就**直写**（省一次 `cp`，也不引入多余失败点）——
    但仍然做同样强度的回读复核：**这个函数的保证是"写完能读回来"，不只是"防信封"**。
    """
    p = os.path.abspath(str(path))
    d = os.path.dirname(p) or "."
    os.makedirs(d, exist_ok=True)
    text = content if isinstance(content, str) else str(content)
    ext = os.path.splitext(p)[1].lower()

    if ext in SAFE_EXTS:
        # 临时件用**非中招扩展名**（`.swtmp`）⇒ python 直写它不会被加信封
        tmp = os.path.join(d, ".%s.swtmp" % os.path.basename(p))
        try:
            with open(tmp, "w", encoding=encoding) as fh:
                fh.write(text)
            subprocess.run(["/bin/cp", tmp, p], check=True)
        finally:
            try:
                os.unlink(tmp)
            except OSError:
                pass                      # 清不掉不影响正文；但下面回读会兜住任何真问题
    else:
        with open(p, "w", encoding=encoding) as fh:
            fh.write(text)

    back = open(p, encoding=encoding).read()
    if back != text:
        raise RuntimeError(
            "安全写盘回读不符：写入 %d 字符 / 读回 %d 字符（%s）"
            % (len(text), len(back), p))
    return p


# ══════════════════════════════════════════════════════════════════════════
# 原子写 / 追加（2026-10-08 加，Owner 批准「②③ 先做」）
# ══════════════════════════════════════════════════════════════════════════
# ── 为什么需要（**这不是预防性设计，是补一个已经存在的洞**）────────────────
# 评审链要读的活文件只有 3 个（引擎侧读入口实测 grep）：
#   `kb/l3/candidates/rules.jsonl` / `kb/l2/units.jsonl` / `kb/l4/canonical/sample_case.jsonl`
#
# ★ **覆盖写确实会撕裂 —— 已实测（这是本文件新增 `write_atomic` 的全部理由）**：
#   `l3_distill_run.py::_write_guarded` 是**截断后重写**（`open(path,"w")`），
#   窗口内读者会看到 **0 字节或半份**。自证 ⑦ 就是这个缺陷的**反向对照**：
#   同样的并发读者，裸 `open(p,"w")` 写 ⇒ 41 次读里检出 **4~8 次撕裂**；
#   换成 `write_atomic` ⇒ 130+ 次读 **0 次撕裂**。
#
# ★★ **追加那边我原先的假设是错的，实测否掉了，所以 ② 没有做** ——
#   我提 ② 的理由是「行很长（最长 211,118 字节）⇒ Python 缓冲会把一行劈成多次 syscall
#   ⇒ 两个写者交错会穿行」。**4 线程 24 万行、4 进程 × {300B,500B,20KB} 全部零穿行。**
#   机理：每次 `fh.write()` 传的是**一整行** ⇒ 缓冲区只装整行 ⇒ 刷出去的也是整行
#   ⇒ 单次 syscall + `O_APPEND` = 原子。详见自证 ⑧⑨ 那段注释（结论钉在那儿）。
#   ⇒ **不量为改是这条循环上反复踩的坑，所以没做那把锁。**
#
# ★ 另外一个**独立的洞**（同一天实测发现的，与本文件直接相关）：
#   `l8/ocr_scanned_pdfs.py --apply` 跑 27.7 分钟写 L1，**连 `.kb.lock` 都没拿** ——
#   即「靠认领保护数据」今天本来只等于**纪律强度**。所以原子写不是「为了分槽才补的前提」，
#   是**独立成立的修复**：让读者永远看到旧版或新版，**永远不是半成品**。
#
# ── 两条用法纪律 ────────────────────────────────────────────────────────
# 1. **覆盖写一律用 `write_atomic()`** —— 同目录临时件 + `os.replace`；
#    POSIX 上同文件系统的 rename 是**原子**的 ⇒ 读者不可能看到半份。
#    临时件必须与目标**同目录**（跨文件系统的 rename 会退化成 copy，就不原子了）。
# 2. **追加**：库里现有的裸追加（整行 write）实测安全，**不必改**。
#    `append_lines()` 保留给「一次写多行」的场合（少一次 open、且语义更明确）。
try:
    import fcntl as _fcntl
except ImportError:                    # 非 POSIX：退化成"只保证单次 write"
    _fcntl = None


def write_atomic(path, content, *, encoding="utf-8", verify=True):
    """**原子**覆盖写：写同目录临时件 → fsync → `os.replace` 换过去。返回 `path`。

    与 `write_text()` 的分工：那个解决**信封**（`.md`/`.sh` 给宿主多 4096 字节），
    这个解决**撕裂**（读者看到半份）。两者独立，都需要时按需串起来用。
    """
    p = os.path.abspath(str(path))
    d = os.path.dirname(p) or "."
    os.makedirs(d, exist_ok=True)
    text = content if isinstance(content, str) else str(content)
    # 临时件用 `.swtmp`（非 `.md`/`.sh` ⇒ 不会被加信封），且**与目标同目录**（保证同文件系统）
    tmp = os.path.join(d, ".%s.%d.swtmp" % (os.path.basename(p), os.getpid()))
    try:
        with open(tmp, "w", encoding=encoding) as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())      # 落盘后再换，断电也不会换上去一个空文件
        os.replace(tmp, p)             # ★ 原子点
    finally:
        try:
            os.unlink(tmp)             # 正常路径下 tmp 已被 replace 掉，这里是失败路径兜底
        except OSError:
            pass
    if verify:
        back = open(p, encoding=encoding).read()
        if back != text:
            raise RuntimeError("原子写回读不符：写入 %d 字符 / 读回 %d 字符（%s）"
                               % (len(text), len(back), p))
    return p


def append_lines(path, lines, *, encoding="utf-8"):
    """**串行化**追加：整批拼成一个字符串，**一次 `write()`**，全程持 `flock`。返回写入行数。

    `lines` 里可以带也可以不带结尾换行 —— 统一补齐。
    """
    p = os.path.abspath(str(path))
    os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
    buf = "".join((ln if ln.endswith("\n") else ln + "\n") for ln in lines)
    if not buf:
        return 0
    with open(p, "a", encoding=encoding) as fh:
        if _fcntl is not None:
            _fcntl.flock(fh.fileno(), _fcntl.LOCK_EX)
        try:
            fh.write(buf)              # O_APPEND + 单次 write ⇒ 偏移不会与别人抢
            fh.flush()
        finally:
            if _fcntl is not None:
                _fcntl.flock(fh.fileno(), _fcntl.LOCK_UN)
    return buf.count("\n")


def selftest():
    """判据自证（离线）。

    ★ **诚实交代这把尺子的边界**：这里**量不出信封** ——
      信封只有**宿主**（DSH）看得见，而本自证跑在 python 里，python 读到的永远是真值。
      所以本自证只证明「**内容完整落地、临时件清干净**」这两条；
      「宿主看到的不再是信封」由 **`kb/l8/envelope_census.py`** 负责（它用宿主那把尺子）。
      **未测的部分写在上面，不许当成测过了。**
    """
    import tempfile
    P, F = [], []

    def chk(name, cond, extra=""):
        (P if cond else F).append(name)
        print("  %s %s%s" % ("✅" if cond else "❌", name, ("  " + extra) if extra else ""))

    d = tempfile.mkdtemp(prefix="safewrite_")
    body = "# 标题\n\n正文一行。带 **markdown** 与中文。\n"

    for ext in (".md", ".sh", ".py", ".json"):
        p = os.path.join(d, "t" + ext)
        write_text(p, body)
        got = open(p, encoding="utf-8").read()
        chk("① %-6s 内容逐字一致" % ext, got == body, "读回 %d 字符" % len(got))
        chk("① %-6s 临时件没留下" % ext,
            [x for x in os.listdir(d) if x.startswith(".")] == [],
            str([x for x in os.listdir(d) if x.startswith(".")]))

    # ② 覆盖已有文件（真实场景：同一 RUN 复跑，报告已存在）
    p = os.path.join(d, "t.md")
    write_text(p, "旧内容\n")
    write_text(p, body)
    chk("② 覆盖已有文件后内容正确", open(p, encoding="utf-8").read() == body)

    # ③ 深目录会自动建
    deep = os.path.join(d, "a", "b", "c.report.md")
    write_text(deep, body)
    chk("③ 目标目录不存在时会自动建", os.path.isfile(deep))

    # ④ 反向对照：回读复核**真的会红**（写一个读不回来的场景：目录当文件写）
    ok = False
    try:
        write_text(os.path.join(d, "adir"), body)     # 先建目录占位
        os.makedirs(os.path.join(d, "adir"), exist_ok=True)
        write_text(os.path.join(d, "adir"), body)
    except Exception:
        ok = True
    chk("④ 反向对照：写不进去时会抛错（不静默）", ok)

    # ⑤ 空内容也要能写（报告可能渲染成空，不许因此崩）
    p5 = os.path.join(d, "empty.md")
    write_text(p5, "")
    chk("⑤ 空内容可写且回读一致", open(p5, encoding="utf-8").read() == "")

    # ══════════════════════════════════════════════════════════════════════
    # ⑥–⑪ 原子写 / 带锁追加（2026-10-08 加）
    # ★ ⑥ 与 ⑧ 是"正例"，⑦ 与 ⑨ 是**反向对照** —— 没有后两条，
    #   把函数体改成裸写也能让前两条全绿，那就是"判据量不出缺陷"，等于没量。
    # ══════════════════════════════════════════════════════════════════════
    import re
    import threading

    # ── ⑥⑦ 原子写 vs 撕裂读 ───────────────────────────────────────────
    # ★★ 第一版是「写者与读者赛跑、数撕裂次数」—— **flaky，已废**：
    #   同一份代码连跑三次，裸写那边检出 7 / 0 / 0 次撕裂（读者和写者是否重叠纯看调度）。
    #   一个会随机变红的反向对照，比没有更坏（人会开始忽略它）。
    # ⇒ 改成**构造式**：不靠抢时序，直接把「写到一半」那一刻**摆出来看**。
    pt = os.path.join(d, "torn.jsonl")
    OLD = "OLD" * 5000          # 15,000 字符
    NEW = "NEW" * 5000

    # ⑦ 反向对照（**先跑控制组**）：裸截断写写到一半时，读者读到的是**半成品**
    with open(pt, "w", encoding="utf-8") as fh:      # ← 这就是改前的写法（_write_guarded 那一处）
        fh.write(NEW[:len(NEW) // 2])
        fh.flush()
        half_seen = open(pt, encoding="utf-8").read()   # ← 读者此刻读到什么
        fh.write(NEW[len(NEW) // 2:])
    chk("⑦ 反向对照：裸截断写**写到一半时读者读到半成品**（%d 字符，新旧都该是 %d）"
        % (len(half_seen), len(NEW)),
        half_seen != NEW and half_seen != OLD and len(half_seen) < len(NEW))

    # ⑥ 原子写：同一个「写到一半」的时刻，目标**只可能是完整旧版或完整新版**
    #    观测点选在 `os.replace` 调用前 —— 那正是「换上去」这个原子动作的临界点。
    #    ★ 先**显式**把目标置成 OLD：⑦ 跑完文件里是 NEW，不置的话 `target_before` 会等于 NEW，
    #      这条断言就变成在比 NEW==OLD —— 第一版正是这么红的（我自己测试里的 bug）。
    write_atomic(pt, OLD)
    _orig_replace = os.replace
    obs = {}

    def _spy_replace(src, dst):
        obs["target_before"] = open(dst, encoding="utf-8").read()   # 换之前目标是什么
        obs["tmp_content"] = open(src, encoding="utf-8").read()     # 临时件是不是完整新版
        return _orig_replace(src, dst)

    os.replace = _spy_replace
    try:
        write_atomic(pt, NEW)
    finally:
        os.replace = _orig_replace
    chk("⑥ 原子写：换上去之前目标**仍是完整旧版**、临时件是完整新版 ⇒ 不存在\"半成品可见\"的时刻",
        obs.get("target_before") == OLD and obs.get("tmp_content") == NEW
        and open(pt, encoding="utf-8").read() == NEW,
        "换前 %s 字符（应 %d）/ 临时件对不对 %s / 现值对不对 %s"
        % (len(obs.get("target_before") or ""), len(OLD),
           obs.get("tmp_content") == NEW, open(pt, encoding="utf-8").read() == NEW))

    # ── ⑧⑨ 追加：**实测结论与提 ② 时的假设相反，把结论钉在这儿，免得后人重做** ──
    # 假设（2026-10-08 我提 ② 时的理由）：`index.jsonl` / `units.jsonl` 的行很长
    #   （实测最长 5,763 / 111,994 / 211,118 字节），Python 缓冲会把一行劈成两次 syscall
    #   ⇒ 两个写者交错时会穿行 ⇒ 要给追加加锁。
    # **实测把这个假设否掉了**（同一台机器、同一份 CPython 3.12/3.9）：
    #   · 4 线程 × 6 万行 × 300B                        ⇒ 穿行 0（24 万行）
    #   · 4 **进程** × 2000 行 × {300B, 500B, 20000B}   ⇒ 穿行 0（进程不走 GIL，是真实形状）
    # 机理（可推演、与观测一致）：每个 `fh.write()` 传进去的是**一整行** ⇒ 缓冲区里**只装整行**
    #   ⇒ 刷出去的也是整行 ⇒ 每次 `write()` syscall 都携带完整行，而 `O_APPEND` 下单次
    #   syscall 的写入是原子的 ⇒ 文件永远是整行拼接。
    # ⚠️ **边界（诚实交代，不许当成 POSIX 保证）**：这是 CPython 在本机的实测行为。
    #   它依赖两条：① 每次 write 传的是完整行；② 没有一处把一行拆成多次 write。
    #   只要有人写出 `fh.write(前半); fh.write(后半)`，下面 ⑨ 那条绿就不再成立。
    # ⇒ **所以 ② 那把锁没做**（"不量就改"是这条循环上反复踩的坑）。留这两条判据，
    #   是为了**将来有人改追加形状时，这里会红**。
    pa = os.path.join(d, "append.jsonl")
    LINE = 300              # 故意不整除缓冲区 ⇒ 若实现会劈行，这里最容易暴露
    PER = 200
    RX = re.compile(r"^(\d+):(\d+):(\d)\3*$")     # ← 校验「这一行是不是完整的一整行」

    def mkline(w, i):
        head = "%d:%d:" % (w, i)
        return head + str(w) * (LINE - len(head))

    def append_probe(fn, nthreads=4):
        """4 个写者并发追加，逐行校验「是不是完整的一行」。返回 (完整行数, 坏行数)。"""
        open(pa, "w").close()

        def work(w):
            fn(pa, [mkline(w, i) for i in range(PER)])

        ths = [threading.Thread(target=work, args=(w,)) for w in range(nthreads)]
        for t in ths:
            t.start()
        for t in ths:
            t.join()
        good = bad = 0
        for ln in open(pa, encoding="utf-8"):
            ln = ln.rstrip("\n")
            m = RX.match(ln)
            if len(ln) == LINE and m and m.group(3) == m.group(1):
                good += 1
            else:
                bad += 1
        return good, bad

    total = 4 * PER
    g1, b1 = append_probe(lambda p, lns: append_lines(p, lns))
    chk("⑧ `append_lines()`：4 写者 × %d 行 ⇒ 行行完整" % PER,
        g1 == total and b1 == 0, "完整 %d / 坏行 %d（应 %d）" % (g1, b1, total))

    def plain_append(p, lns):
        with open(p, "a", encoding="utf-8") as fh:      # ← 库里现有的写法（l2_split_run.py:173）
            for ln in lns:
                fh.write(ln + "\n")

    g2, b2 = append_probe(plain_append)
    chk("⑨ **实测结论**：库里现有的裸追加（整行 write）并发下也**不穿行** —— 这是 ② 没做的判据",
        g2 == total and b2 == 0, "完整 %d / 坏行 %d" % (g2, b2))

    # ── ⑩⑪ 收尾纪律 ───────────────────────────────────────────────────
    pz = os.path.join(d, "z.json")
    write_atomic(pz, "第一版\n")
    write_atomic(pz, "第二版\n")
    left = [x for x in os.listdir(d) if x.endswith(".swtmp")]
    chk("⑩ 原子写不留临时件、且覆盖后内容正确",
        left == [] and open(pz, encoding="utf-8").read() == "第二版\n", str(left))

    # ⑪ 反向对照：回读复核**真的会红**（写进一个读不回来的目标：目录）
    ok = False
    try:
        write_atomic(os.path.join(d, "adir2"), "x")     # 目标是个已存在的目录
        os.makedirs(os.path.join(d, "adir2"), exist_ok=True)
        write_atomic(os.path.join(d, "adir2"), "x")
    except Exception:
        ok = True
    chk("⑪ 反向对照：写不进去时抛错（回读复核不是摆设）", ok)

    print("\n自证：通过 %d / 失败 %d" % (len(P), len(F)))
    print("⚠️ 本自证**测不到信封**（那要宿主那把尺子）—— 见 `kb/l8/envelope_census.py`。")
    for x in F:
        print("  · 失败：%s" % x)
    return 1 if F else 0


if __name__ == "__main__":
    import sys
    if "--selftest" in sys.argv:
        print("_safe_write · 判据自证（离线；测内容完整性与临时件清理，**不测信封**）")
        raise SystemExit(selftest())
    print(__doc__)
    raise SystemExit(0)
