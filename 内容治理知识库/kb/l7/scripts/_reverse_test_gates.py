#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""l7/scripts/_reverse_test_gates.py —— P1-3 的反测台（**只给测试用，不在链路里**）。

做什么：为每道层闸门造一份**夹具库**（kb/ 的镜像：目录是真的、文件是指向真库的软链），
然后把**判据弄坏一处**，跑闸门，确认它**真的会红**；再跑原样夹具，确认它会绿。

为什么这么做：闸门最容易的失败方式不是「漏判」，是**永远红**或**永远绿**。
夹具镜像 + 单点破坏 = 一次只动一个变量，红了才知道是哪条判据在起作用。
**全程不碰真库**：改的永远是夹具里那个「被换成真副本」的文件。

用法：
    kb/kbpy l7/scripts/_reverse_test_gates.py            # 跑全部反测
    kb/kbpy l7/scripts/_reverse_test_gates.py --keep     # 保留夹具目录，便于手工复看
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
KB = os.path.dirname(os.path.dirname(HERE))
ROOT = os.path.dirname(KB)
KBPY = os.path.join(KB, "kbpy")


def mirror(dst, subdirs):
    """把 kb/<subdir> 镜像成夹具：**夹具根下必须有一层 kb/**，真目录 + 文件软链。

    为什么必须有 kb/ 这一层：闸门里有 `kb/...` 这种相对路径（如 l6_scope_lib 读
    kb/l0/registry/kb.json），相对路径是按 cwd 解析的。夹具若不造 kb/ 这一层，
    这些读取会**穿透到真库** —— 反测就会「假绿」（L6 第一版就是这么失败的）。
    """
    for sub in subdirs:
        src_root = os.path.join(KB, sub)
        if not os.path.exists(src_root):
            continue
        for dirpath, dirnames, filenames in os.walk(src_root):
            rel = os.path.join("kb", os.path.relpath(dirpath, KB))
            os.makedirs(os.path.join(dst, rel), exist_ok=True)
            for fn in filenames:
                src = os.path.join(dirpath, fn)
                link = os.path.join(dst, rel, fn)
                if not os.path.lexists(link):
                    os.symlink(src, link)
    # 闸门脚本自己也要在夹具里（相对于 KB 解析）
    rel = os.path.join("kb", os.path.relpath(HERE, KB))
    os.makedirs(os.path.join(dst, rel), exist_ok=True)
    for fn in os.listdir(HERE):
        src = os.path.join(HERE, fn)
        link = os.path.join(dst, rel, fn)
        if not os.path.lexists(link):
            os.symlink(src, link)


def realize(fix, rel):
    """把夹具里某个软链文件换成**真副本**（之后随便改，伤不到真库）。"""
    p = os.path.join(fix, "kb", rel)
    if os.path.islink(p):
        src = os.path.realpath(p)
        os.unlink(p)
        shutil.copyfile(src, p)
    return p


def run(gate, fix, env_extra=None):
    env = dict(os.environ, KB_GATE_KB=os.path.join(fix, "kb"), KB_INTERP_OK="1")
    env.pop("KB_GATE_L7", None)
    if env_extra:
        env.update(env_extra)
    r = subprocess.run([KBPY, "l7/scripts/%s_gate.py" % gate, "--quiet"],
                       cwd=fix, capture_output=True, text=True, env=env)
    out = (r.stdout or "") + (r.stderr or "")
    verdict = "过" if r.returncode == 0 else ("红" if r.returncode == 1 else "无法计算")
    return r.returncode, verdict, out.strip().splitlines()[-2:] 


CASES = []


def case(gate, name, mutate, expect_rc, subdirs):
    CASES.append((gate, name, mutate, expect_rc, subdirs))


# ── L1：把一条缓存的 ocr_version 改成坏引擎版本 ────────────────────────────────
def l1_break(fix):
    import glob
    p = sorted(glob.glob(os.path.join(fix, "kb/l1/media/_cache/*.json")))
    p = [x for x in p if "_batch" not in os.path.basename(x)][0]
    real = realize(fix, os.path.relpath(p, os.path.join(fix, "kb")))
    d = json.load(open(real, encoding="utf-8"))
    d["ocr_version"] = "vision-jxa-1.0"
    json.dump(d, open(real, "w", encoding="utf-8"), ensure_ascii=False)


case("l1", "缓存 ocr_version=坏引擎 vision-jxa-1.0", l1_break, 1, ["l1", ".work"])


# ── L5：把「判据过期登记」抽掉 → 基线项 FAIL 且未登记，必须变红 ─────────────────
# L5 闸门包的是一个自带冻结基线的检查器：造夹具反而会因为缺输入把原样基线也弄红
# （第一版就是这样，反测不成立）。所以 L5 用**真库 + 只换登记文件所在目录**来反测：
#   * 基线跑：KB_GATE_L7 = 真 kb/l7/registry（登记在那儿）→ 应过；
#   * 破坏跑：KB_GATE_L7 = 一个空目录（登记文件不存在）→ 未登记 → 应红。
# 真库全程只读；检查器本来就会写它自己的 .work/l5_integrity.json。
L5_SHADOW = None


def l5_prepare(fix):
    pass                                            # 基线跑必须用**真** registry（否则基线也红）


def l5_break(fix):
    global L5_SHADOW
    L5_SHADOW = tempfile.mkdtemp(prefix="kb-l5-shadow-")   # 破坏 = 登记文件从视野里消失


def l5_run(gate, fix):
    env = dict(os.environ, KB_INTERP_OK="1")
    env.pop("KB_GATE_KB", None)
    env["KB_GATE_L7"] = (os.path.join(KB, "l7/registry") if L5_SHADOW is None else L5_SHADOW)
    r = subprocess.run([KBPY, "l7/scripts/l5_gate.py", "--quiet"], cwd=ROOT,
                       capture_output=True, text=True, env=env)
    out = (r.stdout or "") + (r.stderr or "")
    return r.returncode, ("过" if r.returncode == 0 else "红"), out.strip().splitlines()[-2:]


case("l5", "抽掉 l5-known-drift.yaml（基线项 2 条变成未登记）", l5_break, 1, [])


# ── L2：三条判据（已在本轮早先做过，这里留一条回归）────────────────────────────
def l2_break(fix):
    p = realize(fix, "l2/manifest_l2.jsonl")
    rows = [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]
    for r in rows:
        if r.get("result") == "split":
            r["unit_count"] = "999999"
            break
    with open(p, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")


case("l2", "某 split 行的 unit_count 改成 999999（下界破）", l2_break, 1,
     ["l2", "l1", "l0"])


# ── L3：把一条证据引用的 unit_id 改成不存在的 ──────────────────────────────────
def l3_break(fix):
    p = realize(fix, "l3/candidates/rules.jsonl")
    rows = [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]
    rows[0]["evidence_units"][0]["unit_id"] = "deadbeefdeadbeefdead"
    with open(p, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")


case("l3", "一条 evidence_units.unit_id 改成不存在（C1 回指）", l3_break, 1,
     ["l3", "l2", "l0", "l7/registry", "l7/scripts"])


# ── L4：把两条定稿的 article_no 改成同一个（C1 唯一性）────────────────────────
def l4_break(fix):
    p = realize(fix, "l4/canonical/wording_entry.jsonl")
    rows = [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]
    rows[1]["article_no"] = rows[0]["article_no"]
    with open(p, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")


case("l4", "两条定稿共用一个条款号（C1 唯一性）", l4_break, 1,
     ["l4", "l3", "l2"])


# ── L6：把索引里一条 unit_id 改成不存在（C3 编号同源）─────────────────────────
def l6_break(fix):
    p = realize(fix, "l6/index/l6.jsonl")
    rows = [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]
    rows[0]["unit_id"] = "deadbeefdeadbeefdead"
    with open(p, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")


case("l6", "索引里一条 unit_id 改成不存在（C3 倒排缺编号）", l6_break, 1,
     ["l6", "l2", "l3", "l0", "l1", "l4", "versions", ".work"])


# ── L7：把契约里一个库名改掉（C1 不得自造库名）────────────────────────────────
def l7_break(fix):
    p = realize(fix, "l7/registry/l7.json")
    d = json.load(open(p, encoding="utf-8"))
    d["citation_contract"]["libraries"]["wording"]["dir"] = "3_措辞表达库（自造）"
    json.dump(d, open(p, "w", encoding="utf-8"), ensure_ascii=False)


case("l7", "契约里库名目录自造成「3_措辞表达库（自造）」", l7_break, 1,
     ["l7/registry", "l0/registry", "l3/candidates", "l4/canonical", "l2"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--only", default=None, help="只跑某一层（如 l5）")
    a = ap.parse_args()

    tmp = tempfile.mkdtemp(prefix="kb-gate-fixture-")
    rows, bad = [], 0
    for gate, name, mutate, expect, subdirs in CASES:
        if a.only and gate != a.only:
            continue
        fix = os.path.join(tmp, gate)
        os.makedirs(fix, exist_ok=True)
        mirror(fix, subdirs)
        if gate == "l5":
            l5_prepare(fix)
        runner = l5_run if gate == "l5" else run
        rc0, v0, _ = runner(gate, fix)
        mutate(fix)
        rc1, v1, tail = runner(gate, fix)
        ok = (rc1 == expect)
        baseline_ok = (rc0 == 0)
        if not ok or not baseline_ok:
            bad += 1
        rows.append((gate, name, rc0, v0, rc1, v1, ok and baseline_ok, tail))

    print("=" * 100)
    print("P1-3 反测台：夹具镜像 + 单点破坏。真库只被读，**一个字节都没动**。")
    print("=" * 100)
    print("%-4s %-42s %-10s %-10s %s" % ("层", "破坏点", "原样夹具", "破坏后", "判定"))
    print("-" * 100)
    for gate, name, rc0, v0, rc1, v1, ok, tail in rows:
        print("%-4s %-42s %-10s %-10s %s" % (gate.upper(), name, "%s(%d)" % (v0, rc0),
                                             "%s(%d)" % (v1, rc1), "✅ 反测成立" if ok else "❌ 反测不成立"))
        if not ok:
            for t in tail:
                print("        %s" % t)
    print("-" * 100)
    print("合计 %d 例，反测成立 %d 例，不成立 %d 例" % (len(rows), len(rows) - bad, bad))
    print("夹具目录：%s%s" % (tmp, "（--keep 保留）" if a.keep else "（用完即删）"))
    if not a.keep:
        shutil.rmtree(tmp, ignore_errors=True)
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
