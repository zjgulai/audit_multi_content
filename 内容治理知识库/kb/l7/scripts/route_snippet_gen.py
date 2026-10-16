#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""route_snippet_gen.py —— 从注册表**生成**「层→skill→引擎」调度片段（单一真源，不许手抄）。

为什么需要它
------------
DSH 侧的会话目录只给模型 `name` + 截断后的 `description`（默认 497 字符可见），
**`layers.yaml` 的 `skill:` 字段从不出现在目录里**。所以「到某一层调哪个 skill」
这件事，模型看不见；写进 AGENTS.md 的那份一旦手工维护就必然过期。

本脚本把三份静态真源编译成**一段可直接贴进 AGENTS.md 的片段**，并给每个片段带
`generated_at` + 三个源文件的 sha256 —— 于是 AGENTS.md 里那段不再是人抄的第二份事实，
而是**可复算的产物**：`--check` 能判它漂没漂。

真源（全部相对库根）
--------------------
  1. `l7/registry/layers.yaml`  —— 层→skill→引擎（唯一真源）、skill_write、depends_on
  2. `l7/registry/routes.yaml`  —— 两条链的入口 e `not_for`
  3. `l7/registry/skills.yaml`  —— 成员登记表（校验层声明里的 id 都登记过）

用法
----
  kb/kbpy l7/scripts/route_snippet_gen.py                 # 打到 stdout
  kb/kbpy l7/scripts/route_snippet_gen.py --out <文件>     # 落盘
  kb/kbpy l7/scripts/route_snippet_gen.py --check <文件>   # 漂移校验（红=片段已过期）
  kb/kbpy l7/scripts/route_snippet_gen.py --json          # 机器可读

退出码
------
  0 成功 / `--check` 未漂移
  1 `--check` 发现漂移（片段与真源不一致）
  2 用法或环境错、真源缺失、层声明里的 skill 未登记
"""
import argparse
import hashlib
import json
import os
import re
import sys

BEGIN = "<!-- BEGIN route_snippet_gen (自动生成 · 勿手改) -->"
END = "<!-- END route_snippet_gen -->"


def kb_root(explicit=None):
    if explicit:
        return os.path.abspath(explicit)
    here = os.path.dirname(os.path.abspath(__file__))          # kb/l7/scripts
    root = os.path.dirname(os.path.dirname(here))              # kb
    if not os.path.isfile(os.path.join(root, "KB-ROOT.json")):
        sys.stderr.write("route_snippet_gen: 找不到 KB-ROOT.json，用 --kb-root 指定库根\n")
        return None
    return root


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# ── 真源 1：layers.yaml ────────────────────────────────────────────────
def parse_layers(text):
    """解析 `- layer: Lx` 块。只取生成片段需要的字段，不做完整 YAML 解析。"""
    layers = []
    cur = None
    in_engine = False
    for raw in text.split("\n"):
        line = raw.rstrip()
        m = re.match(r"^- layer:\s*(L\d+)\s*$", line)
        if m:
            cur = {"layer": m.group(1), "skill": [], "skill_write": None,
                   "depends_on": [], "engine": []}
            layers.append(cur)
            in_engine = False
            continue
        if cur is None:
            continue
        # 下一个顶层列表项结束本块（layers: 下只有 layer 块）
        if re.match(r"^-\s+\S", line):
            cur = None
            in_engine = False
            continue
        m = re.match(r"^  skill:\s*\[(.*?)\]", line)
        if m:
            cur["skill"] = [s.strip() for s in m.group(1).split(",") if s.strip()]
            in_engine = False
            continue
        m = re.match(r"^  skill_write:\s*(true|false)", line)
        if m:
            cur["skill_write"] = (m.group(1) == "true")
            in_engine = False
            continue
        m = re.match(r"^  depends_on:\s*\[(.*?)\]", line)
        if m:
            cur["depends_on"] = [s.strip() for s in m.group(1).split(",") if s.strip()]
            in_engine = False
            continue
        if re.match(r"^  engine:\s*$", line):
            in_engine = True
            continue
        if in_engine:
            m = re.match(r"^\s{4}-\s+(\S+\.py)", line)
            if m:
                cur["engine"].append(m.group(1))
                continue
            # engine 块内的续行/注释不结束块；其它一级键结束块
            if re.match(r"^  [a-z_]+:", line):
                in_engine = False
            continue
        if re.match(r"^  [a-z_]+:", line):
            in_engine = False
    return layers


# ── 真源 2：routes.yaml ────────────────────────────────────────────────
def parse_chains(text):
    chains = []
    cur = None
    for raw in text.split("\n"):
        line = raw.rstrip()
        m = re.match(r"^  - id:\s*(\S+)\s*$", line)
        if m:
            cur = {"id": m.group(1), "name": "", "entry": None, "members": []}
            chains.append(cur)
            continue
        if cur is None:
            continue
        m = re.match(r"^    name:\s*(.+)$", line)
        if m:
            cur["name"] = m.group(1).strip()
            continue
        m = re.match(r"^    entry:\s*(\S+)", line)
        if m:
            cur["entry"] = m.group(1)
            continue
        m = re.match(r"^    members:\s*\[(.*?)\]", line)
        if m:
            cur["members"] = [s.strip() for s in m.group(1).split(",") if s.strip()]
            continue
        if re.match(r"^[a-z_]+:", line):            # 离开 chains 段
            cur = None
    return chains


# ── 真源 3：skills.yaml ────────────────────────────────────────────────
def parse_registered_ids(text):
    ids = set()
    for m in re.finditer(r"^\s*-\s*id:\s*(\S+)\s*$", text, re.M):
        ids.add(m.group(1))
    return ids


def build(root):
    paths = {
        "layers": os.path.join(root, "l7/registry/layers.yaml"),
        "routes": os.path.join(root, "l7/registry/routes.yaml"),
        "skills": os.path.join(root, "l7/registry/skills.yaml"),
    }
    for k, p in paths.items():
        if not os.path.isfile(p):
            return None, "真源缺失：%s（%s）" % (k, p)

    layers = parse_layers(open(paths["layers"], encoding="utf-8").read())
    chains = parse_chains(open(paths["routes"], encoding="utf-8").read())
    registered = parse_registered_ids(open(paths["skills"], encoding="utf-8").read())

    if not layers:
        return None, "layers.yaml 里没解析到任何 `- layer:` 块"

    # 交叉校验：层声明里的 skill 必须在 skills.yaml 登记过
    unregistered = []
    for L in layers:
        for s in L["skill"]:
            if s not in registered:
                unregistered.append("%s → %s" % (L["layer"], s))

    fps = {k: sha256(p) for k, p in paths.items()}
    return {"layers": layers, "chains": chains, "fingerprints": fps,
            "unregistered": unregistered, "root": root}, None


def render(data):
    fps = data["fingerprints"]
    out = []
    out.append(BEGIN)
    out.append("### 层 → skill → 引擎（**本段自动生成，勿手改**）")
    out.append("")
    out.append("真源 = 三份注册表，本段是**产物**。改路由请改真源，然后重跑：")
    out.append("")
    out.append("```bash")
    out.append("sh kb/kbpy l7/scripts/route_snippet_gen.py --out <本段所在文件>   # 重生成")
    out.append("sh kb/kbpy l7/scripts/route_snippet_gen.py --check <本段所在文件> # 漂移校验")
    out.append("```")
    out.append("")
    out.append("| 源 | sha256（前 16） |")
    out.append("|---|---|")
    for k in ("layers", "routes", "skills"):
        out.append("| `l7/registry/%s.yaml` | `%s` |" % (k, fps[k][:16]))
    out.append("")
    out.append("**逐层绑定**（`--invoked` 的取值就是本表 `skill` 列）：")
    out.append("")
    out.append("| 层 | skill（按序调） | skill_write | depends_on | 层内引擎 |")
    out.append("|---|---|---|---|---|")
    for L in data["layers"]:
        sk = "、".join("`%s`" % s for s in L["skill"]) or "（空）"
        eng = "<br>".join(L["engine"]) if L["engine"] else "—"
        out.append("| **%s** | %s | %s | %s | %s |" % (
            L["layer"], sk,
            "`true`" if L["skill_write"] else "`false`",
            ", ".join(L["depends_on"]) or "—",
            eng))
    out.append("")
    if data["chains"]:
        out.append("**两条链的入口**（互不抢活）：")
        out.append("")
        for c in data["chains"]:
            out.append("- **%s**（`%s`）入口 = `%s`｜成员 %s" % (
                c["name"] or c["id"], c["id"], c["entry"],
                "、".join("`%s`" % m for m in c["members"]) or "—"))
        out.append("")
    out.append("> `skill_write: false` 的层（L7）**不给自己开写入口**，"
               "塞进 `--only` 只在带 `--write-gate` 时才被硬拒。")
    if data["unregistered"]:
        out.append("")
        out.append("⚠️ **未登记项**（层声明了但 `skills.yaml` 查不到）：")
        for u in data["unregistered"]:
            out.append("- %s" % u)
    out.append(END)
    return "\n".join(out) + "\n"


def extract_block(text):
    i = text.find(BEGIN)
    j = text.find(END)
    if i < 0 or j < 0:
        return None
    return text[i:j + len(END)] + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--emit", action="store_true",
                    help="打到 stdout（贴 .md 时的**唯一推荐**通道）")
    ap.add_argument("--out", default=None,
                    help="写入该文件。**`.md` 目标会被拒**（写通道纪律），非 .md 可直接写")
    ap.add_argument("--allow-md-direct-write", action="store_true",
                    help="覆盖 .md 写通道闸门（风险自负：Node/Electron 写的 .md 宿主可能读不懂）")
    ap.add_argument("--check", default=None, help="漂移校验：该文件里的片段与真源是否一致")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--kb-root", default=None)
    a = ap.parse_args()

    root = kb_root(a.kb_root)
    if root is None:
        return 2
    data, err = build(root)
    if err:
        sys.stderr.write("❌ %s\n" % err)
        return 2
    snippet = render(data)

    if a.json:
        print(json.dumps({"fingerprints": data["fingerprints"],
                          "layers": data["layers"], "chains": data["chains"],
                          "unregistered": data["unregistered"],
                          "snippet": snippet}, ensure_ascii=False, indent=1))
        return 0 if not data["unregistered"] else 2

    if a.check:
        if not os.path.isfile(a.check):
            sys.stderr.write("❌ 待校验文件不存在：%s\n" % a.check)
            return 2
        cur = extract_block(open(a.check, encoding="utf-8").read())
        if cur is None:
            sys.stderr.write("❌ %s 里找不到生成标记（%s）—— 说明它还是**手抄版**，不是产物\n"
                             % (a.check, BEGIN))
            return 1
        if cur.strip() != snippet.strip():
            sys.stderr.write("❌ 片段已漂移：与真源不一致，请重跑 --out 重生成\n")
            sys.stderr.write("   源指纹：%s\n" % json.dumps(
                {k: v[:16] for k, v in data["fingerprints"].items()}, ensure_ascii=False))
            return 1
        print("✅ 片段未漂移（与三份真源一致）｜源指纹 %s" %
              json.dumps({k: v[:16] for k, v in data["fingerprints"].items()},
                         ensure_ascii=False))
        return 0

    if a.out:
        target = a.out
        # ★ 写通道纪律（kb/view/_meta/GUIDE.md §八 + kb/l7/install-skill.sh 实测）：
        # 本机 trld 监控层会给**经由 Node/Electron 写出的 .md** 落宿主读不懂的加密信封
        # （首字节 88 7d 1c ??），宿主 frontmatter 解析失败 → skill 不进目录。
        # **shell（cat / 重定向 / cp）写出的才是明文** —— 技能安装通道就是 `cat > 文件`。
        # 而 python 自己的 stat/sha256 对信封免疫 → 自检给假绿灯。
        # 所以本脚本**两条都拒绝**：不自己写 .md、也不让 node 写 .md。
        if target.lower().endswith(".md") and not a.allow_md_direct_write:
            sys.stderr.write(
                "❌ 拒绝本脚本直接写 `.md`（写通道纪律 —— 见 kb/view/_meta/GUIDE.md §八 与\n"
                "   kb/l7/install-skill.sh：Node/Electron 写的 .md 会带宿主读不懂的信封，\n"
                "   shell `cat` 写的才是明文；而 python 的 stat/sha256 查不出信封）。\n\n"
                "   正确做法（shell 通道 + node 回读校验）：\n"
                "     sh kb/kbpy l7/scripts/route_snippet_gen.py --emit > /tmp/snippet.md\n"
                "     cat /tmp/snippet.md >> <目标.md>          # 或按标记就地替换\n"
                "     # 再校验宿主可读：Node 读该文件首 3 字节（示例见 install-skill.sh --check）\n\n"
                "   ⚠️ 不要用 write_via_node.mjs 写 .md —— 它同样是 Node 写，同样带信封。\n"
                "   非 .md 目标（.txt/.json 等）不受影响，可直接 --out。\n"
                "   确有需要覆盖本闸门：加 --allow-md-direct-write（风险自负）。\n")
            return 2
        old = open(target, encoding="utf-8").read() if os.path.isfile(target) else ""
        if BEGIN in old and END in old:
            new = old[:old.find(BEGIN)] + snippet + old[old.find(END) + len(END) + 1:]
        elif old and not old.endswith("\n"):
            new = old + "\n\n" + snippet
        else:
            new = old + ("\n" if old else "") + snippet
        with open(target, "w", encoding="utf-8") as f:
            f.write(new)
        print("✅ 已写入 %s（%d 字节）" % (target, len(new.encode("utf-8"))))
        return 0

    sys.stdout.write(snippet)
    return 0 if not data["unregistered"] else 2


if __name__ == "__main__":
    sys.exit(main())
