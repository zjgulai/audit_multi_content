#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""layers_check.py —— 层契约表 kb/l7/registry/layers.yaml 自检。

读 `kb/l7/registry/layers.yaml`（静态真源），校验 L0–L7 八层的层契约是否**完整且可执行**：
字段齐不齐、引擎路径在不在、cwd / 解释器约定写没写、depends_on 反映的是不是**实测 DAG**
（而不是拍脑袋的线性链）、覆盖式写入的层有没有干跑档。

判据（六类）：
  1. 层完整性   —— 恰好 8 层、id 恰为 L0…L7、无重复
  2. 必填字段   —— layer / depends_on / engine / inputs / outputs / idempotency_key /
                   gate / cwd / python / envelope / write_mode / dry_run 十二个字段齐全且非空
  3. 路径存在性 —— engine 路径按「库根相对 / ~ 展开」解析后必须存在（**本脚本做 expanduser**，
                   与 skills_check.py 第 4/5 类的已知缺陷相反，别把这里的判据误当成那条）
  4. cwd / 解释器 —— cwd 必须是 kb/ 的上一级且真实存在（**软链路径与真实路径均合法**：
                   判据为 <cwd>/kb 解析到本库；2026-09-29 口径统一）
  5. DAG 形状   —— depends_on 只引用 L0…L7、不自指、无环；并且**必须扇出**
                   （L2 → L3/L5/L6 与 L3 → L4/L5/L6 两条断言逐条核；线性链判失败）
  6. 干跑档     —— 覆盖式写入（write_mode 含 overwrite 且非 read_only）的层必须显式声明 dry_run；
                   声明 dry_run=false 的层会被列进「无干跑档清单」（**不算错误**，但必须看得见）

用法：
  kb/kbpy l7/scripts/layers_check.py                 # 体检
  kb/kbpy l7/scripts/layers_check.py --kb-root <库根> # 指定库根（含 KB-ROOT.json 的那层）
  kb/kbpy l7/scripts/layers_check.py --json          # 额外输出机器可读汇总
  kb/kbpy l7/scripts/layers_check.py --quiet         # 只输出汇总与退出码

退出码：0 全过 / 1 有问题 / 2 用法或环境错（表读不到、库根找不到、YAML 不合法）

**不依赖第三方包**：有 PyYAML 就用，没有就复用同目录 skills_check.py 的内置 YAML 子集解析器
（同一套降级哲学：自检脚本自己不该成为需要被 check 的东西）。
"""
from __future__ import annotations

import argparse
import json
import os
import sys

TABLE_REL = ("l7", "registry", "layers.yaml")
KB_ROOT_MARKER = "KB-ROOT.json"
EXPECTED_LAYERS = ["L%d" % i for i in range(8)]

MANDATORY = ["layer", "depends_on", "engine", "inputs", "outputs", "idempotency_key",
             "gate", "cwd", "python", "envelope", "write_mode", "dry_run"]

#: 实测 DAG 断言：(下游层, 必须出现在其 depends_on 里的上游层)
DAG_ASSERTIONS = [
    ("L3", "L2"), ("L5", "L2"), ("L6", "L2"),      # L2 扇出到 L3/L5/L6
    ("L4", "L3"), ("L5", "L3"), ("L6", "L3"),      # L3 扇出到 L4/L5/L6
]
ENVELOPE_ENUM = ("required", "optional", "none")
EXPECTED_PYTHON = "${KB_PYTHON}"


def home(p):
    return os.path.abspath(os.path.expanduser(p))


def find_root(start, explicit=None):
    """定位库根 = 含 KB-ROOT.json 的那一层目录。显式指定无效直接报错，不静默换库。"""
    if explicit:
        p = home(explicit)
        if os.path.isfile(os.path.join(p, KB_ROOT_MARKER)):
            return p
        if os.path.isfile(os.path.join(p, "kb", KB_ROOT_MARKER)):
            return os.path.join(p, "kb")
        raise RuntimeError("--kb-root 指向的目录没有 %s：%s" % (KB_ROOT_MARKER, p))
    if os.environ.get("KB_ROOT"):
        return find_root(start, os.environ["KB_ROOT"])
    d = os.path.abspath(start)
    while True:
        if os.path.isfile(os.path.join(d, KB_ROOT_MARKER)):
            return d
        q = os.path.dirname(d)
        if q == d:
            break
        d = q
    for cand in ("~/.dsh/Momcozy知识库/kb",
                 "~/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理/kb"):
        p = home(cand)
        if os.path.isfile(os.path.join(p, KB_ROOT_MARKER)):
            return p
    raise RuntimeError("找不到库根（含 %s 的那一层）；用 --kb-root 指定" % KB_ROOT_MARKER)


def load_layers(path):
    """读层契约表，返回 (层列表, 解析器名, 说明)。顶层是 `layers:` 列表或裸列表都认。"""
    text = open(path, encoding="utf-8").read()
    doc = None
    pname = pdetail = None
    try:
        import yaml as _y
        if hasattr(_y, "safe_load"):
            try:
                doc = _y.safe_load(text)
                pname, pdetail = "PyYAML", "版本 %s" % getattr(_y, "__version__", "未知")
            except _y.YAMLError as e:
                raise RuntimeError("%s 不是合法 YAML：\n  %s" % (path, str(e).replace("\n", "\n  ")))
    except ImportError:
        pass
    if doc is None:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import skills_check as SC
        pname, pdetail = "内置降级", "未找到可用的 PyYAML，复用 skills_check 的解析器"
        try:
            doc = SC.parse_yaml_subset(text)
        except SC.YamlSubsetError as e:
            raise RuntimeError("%s 用了内置解析器覆盖不到的 YAML 构造：\n  %s" % (path, e))

    if isinstance(doc, dict):
        rows = doc.get("layers")
        if rows is None:
            raise RuntimeError("%s 顶层要有 layers: 列表（当前键：%s）"
                               % (path, "、".join(map(str, doc.keys()))))
    else:
        rows = doc
    if not isinstance(rows, list):
        raise RuntimeError("%s 顶层要是层列表（当前 %s）" % (path, type(rows).__name__))
    return rows, pname, pdetail


def resolve(root_parent, p):
    """把契约表里的路径解析成绝对路径。库根相对 / ~ / 绝对三种写法都认。"""
    if not isinstance(p, str):
        return None
    if p.startswith(("~", "/")):
        return home(p)
    return os.path.join(root_parent, p)


def nonempty(v):
    if v is None:
        return False
    if isinstance(v, str):
        return v.strip() != ""
    if isinstance(v, (list, dict)):
        return len(v) > 0
    return True


def main(argv=None):
    ap = argparse.ArgumentParser(description="layers.yaml 层契约表自检")
    ap.add_argument("--kb-root", default=None, help="库根（含 KB-ROOT.json 的那一层）")
    ap.add_argument("--table", default=None, help="layers.yaml 路径（缺省按库根推）")
    ap.add_argument("--json", action="store_true", help="额外输出机器可读汇总")
    ap.add_argument("--quiet", action="store_true", help="只输出汇总")
    args = ap.parse_args(argv)

    try:
        root = find_root(os.path.dirname(os.path.abspath(__file__)), args.kb_root)
    except RuntimeError as e:
        print("环境错：%s" % e, file=sys.stderr)
        return 2

    table_path = args.table or os.path.join(root, *TABLE_REL)
    root_parent = os.path.dirname(root)          # ★ kb/ 的上一级；l8 脚本的 cwd

    try:
        rows, pname, pdetail = load_layers(table_path)
    except (RuntimeError, OSError) as e:
        print("环境错：%s" % e, file=sys.stderr)
        return 2

    P = {"1": [], "2": [], "3": [], "4": [], "5": [], "6": []}
    I = {"无干跑档": [], "备注": []}

    by_layer = {}
    for r in rows:
        if not isinstance(r, dict):
            P["1"].append("有一条不是映射：%r" % (r,))
            continue
        lid = str(r.get("layer") or "")
        if lid in by_layer:
            P["1"].append("层 id 重复：%s" % lid)
        by_layer[lid] = r

    # ---- 1. 层完整性
    missing = [l for l in EXPECTED_LAYERS if l not in by_layer]
    extra = [l for l in by_layer if l not in EXPECTED_LAYERS]
    if missing:
        P["1"].append("缺层：%s" % "、".join(missing))
    if extra:
        P["1"].append("多出的层 id（只允许 L0…L7）：%s" % "、".join(sorted(extra)))

    # ---- 2. 必填字段
    for lid in EXPECTED_LAYERS:
        r = by_layer.get(lid)
        if r is None:
            continue
        for f in MANDATORY:
            if f not in r:
                P["2"].append("%s：缺字段 %s" % (lid, f))
            elif not nonempty(r.get(f)) and f != "depends_on":   # depends_on 允许空列表（L0）
                P["2"].append("%s：字段 %s 为空" % (lid, f))
        env = str(r.get("envelope") or "")
        if env and env not in ENVELOPE_ENUM:
            P["2"].append("%s：envelope=%r 不在 %s 里" % (lid, env, "/".join(ENVELOPE_ENUM)))
        if r.get("python") not in (None, EXPECTED_PYTHON):
            P["2"].append("%s：python=%r，应为 %s（解释器约定唯一真源 kb/.kb-python）"
                          % (lid, r.get("python"), EXPECTED_PYTHON))

    # ---- 3. 引擎路径存在性（★ 本脚本做 expanduser）
    for lid in EXPECTED_LAYERS:
        r = by_layer.get(lid)
        if r is None:
            continue
        eng = r.get("engine")
        if not isinstance(eng, list):
            P["3"].append("%s：engine 应是列表（当前 %r）" % (lid, type(eng).__name__))
            continue
        for e in eng:
            if not isinstance(e, str):
                P["3"].append("%s：engine 项不是字符串：%r" % (lid, e))
                continue
            # 契约表里引擎行尾可能带注释，解析后不含注释；这里按空白切掉防御性处理
            path = e.split()[0] if e.split() else e
            if not path.endswith(".py"):
                continue                     # 非 .py 的引擎项（如 matcher）不在存在性判定内
            ap_ = resolve(root_parent, path)
            if not os.path.exists(ap_):
                P["3"].append("%s：engine 路径不存在 %s（解析为 %s）" % (lid, path, ap_))

    # ---- 4. cwd / 解释器
    for lid in EXPECTED_LAYERS:
        r = by_layer.get(lid)
        if r is None:
            continue
        cwd = r.get("cwd")
        if not cwd:
            P["4"].append("%s：cwd 必填（29 个 l8 脚本用 \"kb/...\" 相对路径）" % lid)
            continue
        cp = home(cwd) if isinstance(cwd, str) else ""
        if not os.path.isdir(cp):
            P["4"].append("%s：cwd 不是存在的目录：%s" % (lid, cwd))
        # ★ 2026-09-29 口径统一：软链路径与真实路径**均合法**。
        #   判据 = 「cd <cwd> 后 kb/… 能到达本库」，即 <cwd>/kb 与库根解析到同一实体。
        #   批次23 起 `layers.yaml` 写占位符 `{kb_root}`；真库跑时解析到库根本身，
        #   副本跑时解析到副本根 —— **不写死任何绝对路径**（写死曾致副本隔离静默失效）。
        elif os.path.realpath(os.path.join(cp, "kb")) != os.path.realpath(root):
            P["4"].append(
                "%s：cwd=%s 不是「本次库根」（%s/kb 未解析到本库）；**合法写法**：占位符 {kb_root}（批次23 起，由编排器按本次库根替换）或 %s"
                % (lid, cwd, cp, root_parent))

    # ---- 5. DAG 形状
    deps = {}
    for lid in EXPECTED_LAYERS:
        r = by_layer.get(lid)
        if r is None:
            continue
        d = r.get("depends_on")
        if not isinstance(d, list):
            P["5"].append("%s：depends_on 应是列表（当前 %r）" % (lid, type(d).__name__))
            deps[lid] = []
            continue
        deps[lid] = [str(x) for x in d]
        for x in deps[lid]:
            if x not in EXPECTED_LAYERS:
                P["5"].append("%s：depends_on 引用了非层标识 %s" % (lid, x))
            if x == lid:
                P["5"].append("%s：depends_on 自指" % lid)
    for down, up in DAG_ASSERTIONS:
        if down in deps and up not in deps.get(down, []):
            P["5"].append("实测 DAG 断言不成立：%s.depends_on 里应有 %s（当前 %s）"
                          % (down, up, deps.get(down)))
    # 无环
    color = {}

    def visit(n, stack):
        color[n] = 1
        for m in deps.get(n, []):
            if m not in deps:
                continue
            if color.get(m) == 1:
                P["5"].append("depends_on 成环：%s" % " → ".join(stack + [n, m]))
            elif color.get(m) is None:
                visit(m, stack + [n])
        color[n] = 2

    for lid in EXPECTED_LAYERS:
        if lid in deps and color.get(lid) is None:
            visit(lid, [])
    # 必须扇出（不是线性链）
    fan = {l: [d for d in EXPECTED_LAYERS if l in deps.get(d, [])] for l in EXPECTED_LAYERS}
    if max((len(v) for v in fan.values()), default=0) < 2:
        P["5"].append("depends_on 是一条线性链（没有任何层被 ≥2 个下游依赖）——与实测 DAG 不符")

    # ---- 6. 干跑档
    for lid in EXPECTED_LAYERS:
        r = by_layer.get(lid)
        if r is None:
            continue
        wm = str(r.get("write_mode") or "")
        dr = r.get("dry_run")
        if dr not in (True, False):
            P["6"].append("%s：dry_run 应是布尔（当前 %r）" % (lid, dr))
        if "overwrite" in wm and dr is False:
            I["无干跑档"].append("%s（write_mode=%s，dry_run=false）" % (lid, wm))

    # ---------------------------------------------------------------- 输出
    counts = {k: len(v) for k, v in P.items()}
    total = sum(counts.values())

    _real = sys.stdout
    if args.json:
        sys.stdout = sys.stderr

    if not args.quiet:
        print("=" * 68)
        print("layers_check —— 层契约表 kb/l7/registry/layers.yaml 自检")
        print("=" * 68)
        print("库根      : %s" % root)
        print("契约表    : %s" % os.path.relpath(table_path, root_parent))
        print("解析器    : %s（%s）" % (pname, pdetail))
        print("层数      : %d（应为 %d）" % (len(by_layer), len(EXPECTED_LAYERS)))
        print("cwd 约定  : %s" % root_parent)
        print()
        titles = {
            "1": "1. 层完整性（恰好 L0…L7、无重复）",
            "2": "2. 必填字段（12 个字段齐全且非空；envelope 取值合法；python 为 ${KB_PYTHON}）",
            "3": "3. 引擎路径存在性（本脚本做 expanduser）",
            "4": "4. cwd / 解释器约定",
            "5": "5. DAG 形状（引用合法 / 无环 / 扇出断言）",
            "6": "6. 干跑档声明",
        }
        for k in "123456":
            print("--- %s --- %d 条" % (titles[k], counts[k]))
            for line in P[k][:20]:
                print("    · %s" % line)
            if counts[k] > 20:
                print("    … 另有 %d 条未列" % (counts[k] - 20))
            print()
        print("--- 无干跑档清单（write_mode 含 overwrite 但 dry_run=false）--- %d 条【不算错误，但必须看得见】"
              % len(I["无干跑档"]))
        for line in I["无干跑档"]:
            print("    · %s" % line)
        print()
        print("--- 备注 ---")
        for line in I["备注"]:
            print("    · %s" % line)
        print()
        print("=" * 68)
        print("汇总")
        print("=" * 68)
        print("层：%s" % "、".join(EXPECTED_LAYERS))
        for lid in EXPECTED_LAYERS:
            if lid in deps:
                print("  %s ← %s" % (lid, "、".join(deps[lid]) if deps[lid] else "（外部源，无上游层）"))
        print()
        print("六类问题：1=%d 2=%d 3=%d 4=%d 5=%d 6=%d ｜合计 %d"
              % (counts["1"], counts["2"], counts["3"], counts["4"], counts["5"], counts["6"], total))
        print("结论：%s。" % ("全过" if total == 0 else "有问题"))
        print("退出码：%d" % (0 if total == 0 else 1))

    if args.json:
        sys.stdout = _real
        out = {
            "kb_root": root,
            "table": table_path,
            "parser": pname,
            "layers": sorted(by_layer),
            "depends_on": deps,
            "problems": {k: v for k, v in P.items()},
            "counts": counts,
            "total_problems": total,
            "no_dry_run": I["无干跑档"],
            "exit_code": 0 if total == 0 else 1,
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))

    return 0 if total == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
