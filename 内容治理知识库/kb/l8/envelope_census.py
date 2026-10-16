#!/usr/bin/env python3
"""信封普查（A2 的真正形态）：把「有多少 .md 对 node 侧读者不可读」变成一个**会自我解释**的数字。

为什么要它，而不是靠删文件把数字压小：
  2026-09-29 实测 1,248 个 .md 存在问题（Python 侧字节数 != node 侧，差值**恒为 4096**）。
  但其中绝大多数是**刻意保留**的 —— 直接报「1,248 个坏文件」既吓人又没用，
  而"删掉让数字变小"更糟：`kbcheck-home/` 与 `kbremote-home/` 是**他人/临时目录**，
  kb/l8/runs/20260923-1540.report.md:279 已经明确记过「不擅自改」。
  正确的做法是**分类**：把「刻意归档的证据」「他人的目录」「可再生的过期备份」与
  「活路径上真该修的」分开报，并且**只对最后一类判失败**。

判据（精确，不看首字节）：同一路径下 Python 侧 `os.path.getsize` != node 侧 `fs.statSync().size`。
不看首字节是因为有假阳性（正常 md 也可以不以 `#`/`---` 开头）。

分类表（改这里之前先读上面那段）：
  · 刻意归档        kb/l8/_archive/enveloped-*   —— 信封机制的证据本体，改了就毁证
  · 本次修复留底    kb/l8/_archive/enveloped-repair-*（内容与现文件相同，见 fix_a1_envelopes.py）
  · 他人/临时目录   kb/.work/kbcheck-home、kb/.work/kbremote-home、kb/.work/prd.md
                    —— 既有决定「不擅自改」，只报不修
  · 可再生的过期备份 kb/.work/hostlib.bak-*
  · 活路径         其余一切 —— **这类必须为 0**，非 0 即 exit 1

用法：
  python3 kb/l8/envelope_census.py            # 普查，活路径有信封则 exit 1
  python3 kb/l8/envelope_census.py --json     # 只输出 JSON
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

import argparse
import json
import os
import subprocess
import sys

KB = "kb"
DSH = "/Applications/DSH Desktop.app.pre-lute-20260907-111753/Contents/MacOS/DSH Desktop"
NODE_SCAN = f"{KB}/.work/sizes_node.mjs"
TMP = "/tmp/kb_envelope_census_node.json"

# 分类：前缀 → (类别, 是否算失败, 说明)
CLASSES = [
    ("l8/_archive/enveloped-repair-", "修复留底", False,
     "A1 修复前的明文留底（内容与现文件逐字节相同）"),
    ("l8/_archive/enveloped-", "刻意归档", False,
     "信封机制的证据本体，改了就毁证"),
    (".work/kbcheck-home/", "他人/临时目录", False,
     "kb/l8/runs/20260923-1540.report.md:279 记「不擅自改」"),
    (".work/kbremote-home/", "他人/临时目录", False,
     "同上"),
    (".work/prd.md", "他人/临时目录", False,
     "同上（A1 只做了明文修复、内容未改，见留底）"),
    (".work/hostlib.bak-", "可再生的过期备份", False,
     "hostlib 可 1.8 秒重新生成（publish.sh 实测）；留着不影响任何读取方"),
]


# ★ 2026-10-09（Owner 批准「① + ③ 一起，且 ③ 必须写在 ① 之后」）加的窄分类。
#   背景：29 条活路径红**全部**落在 7 个 `-fix` 副本目录里，**没有一条是真源** ——
#     装机位是 `~/.dsh/skills/<名>` → 指向 `kb/l7/skills/<名>`（**不带 -fix**）；
#     实测 `~/.dsh/skills` 里指向 `-fix` 的软链 **0 个**，registry/scripts 里引用 `-fix` 的也是 0。
#     `-fix` 是评测/优化流程产出的**交付副本**，不被任何读者加载。
#   为什么必须先做 ① 再写这条：先删掉 5 个「内层整份重复副本」（逐份 sha256 与各自外层
#     **完全相同**，15 份，0 不同、0 外层缺失；已归档 `l8/_archive/inner-fix-copies-20261009-100746`）
#     ⇒ 22 → 11。**若先写分类，就是拿标签把红灯涂绿。**
#   ⚠️ **残余（不许读成"修好了"）**：剩下 11 份 `*-fix/references/*.md` **仍然是被信封的**
#     （node 写一律 EACCES，目录只读），**宿主侧读者依然读不到**。它们不再冒充"活路径红"，
#     但"读不到"这个事实**没有被消除**。要真修需 Owner 授权 chmod，或把交付副本改成经 node 落盘。
FIX_COPY = ("l7/skills/", "-fix/", "评测/优化交付副本", False,
            "非装机位（实测 ~/.dsh/skills 与 registry 均 0 处引用）；"
            "★ 但其中 11 份 references/*.md 仍被信封、宿主侧读不到 —— 分类只免了『活路径』这一项，未消除该事实")


def classify(rel):
    for prefix, name, fails, why in CLASSES:
        if rel.startswith(prefix):
            return name, fails, why
    # `-fix` 副本：须同时命中「l7/skills/」与「-fix/」两个子串，避免误放行真源
    if FIX_COPY[0] in rel and FIX_COPY[1] in rel:
        return FIX_COPY[2], FIX_COPY[3], FIX_COPY[4]
    return "活路径", True, "node 侧读者（含 agent 的 read 工具）读不到，必须修"


def node_sizes():
    r = subprocess.run(["env", "ELECTRON_RUN_AS_NODE=1", DSH, NODE_SCAN,
                        os.path.abspath(KB), TMP], capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"node 扫描失败：{r.stderr[:300]}")
    return json.load(open(TMP, encoding="utf-8"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    node = node_sizes()
    py = {}
    for dp, dn, fn in os.walk(KB):
        dn[:] = [d for d in dn if d not in ("node_modules", ".git")]
        for f in fn:
            if f.endswith(".md"):
                p = os.path.join(dp, f)
                py[os.path.relpath(p, KB)] = os.path.getsize(p)

    buckets = {}
    live = []
    deltas = set()
    for rel in sorted(set(py) & set(node)):
        if py[rel] == node[rel]:
            continue
        deltas.add(node[rel] - py[rel])
        name, fails, why = classify(rel)
        b = buckets.setdefault(name, {"count": 0, "fails": fails, "why": why, "samples": []})
        b["count"] += 1
        if len(b["samples"]) < 3:
            b["samples"].append(rel)
        if fails:
            live.append({"rel": rel, "py": py[rel], "node": node[rel]})

    out = {
        "scanned_md": len(py),
        "enveloped_total": sum(b["count"] for b in buckets.values()),
        "delta_bytes": sorted(deltas),
        "buckets": buckets,
        "live_path_envelopes": live,
        "verdict": "OK" if not live else f"FAIL（活路径 {len(live)} 个）",
    }
    if a.json:
        print(json.dumps(out, ensure_ascii=False, indent=1))
    else:
        print(f"信封普查：扫了 {out['scanned_md']} 个 .md，其中 {out['enveloped_total']} 个 "
              f"node 侧读不到（差值 {out['delta_bytes']} 字节）")
        for name, b in sorted(buckets.items(), key=lambda kv: -kv[1]["count"]):
            flag = "❌ 必须为 0" if b["fails"] else "✅ 已分类"
            print(f"  {flag}  {name:16} {b['count']:5} 个   {b['why']}")
            for s in b["samples"]:
                print(f"                    例：{s}")
        print(f"\n结论：{out['verdict']}")
    return 1 if live else 0


if __name__ == "__main__":
    sys.exit(main())
