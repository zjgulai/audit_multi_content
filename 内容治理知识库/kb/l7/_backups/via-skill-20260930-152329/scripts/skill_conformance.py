#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""skill_conformance.py —— **四方对账闸门**：skill 文本 ↔ 注册表 ↔ 层契约 ↔ 磁盘。

## 它补的是哪个洞（2026-09-30 实测，一天内撞到两次）

「skills 自动化工作流」跑不动的根因不是引擎不好，是**声明与实现会漂移，而且没人查**：

* `文案合规审查`（brand-text-compliance-review）的注册表只登记了
  `l7/review-engine/core/rule_engine.py`（**5 条** US 种子规则），
  而它的 SKILL.md 声称覆盖「医疗/健康暗示、安全承诺、绝对化用语、无依据数据、背书、披露、产品准确性、渠道限制」——
  实测同一段文案它给 **0 候选**，而真正的判据在 509 条措辞表达库里。
* `kb-pipeline` 的工具**支持** `--check/--sync --only L2`，SKILL.md 里**一字未提** `--only`
  → agent 不可能知道能只跑一层。

这两类都属于「**skill 说的 ≠ 实际做的**」。靠人读是查不过来的（71 行注册表 × 每份 SKILL.md），
所以要机器逐条核。**本闸门只报不改**（修 skill 文本要人点头）。

## 判据（红 = 必须修；黄 = 需人裁）

  C1 引擎路径存在     注册表 `depends_on_engine` 的每个路径必须在库里存在（相对库根）。
  C2 引擎被层契约承认 **黄**：`depends_on_engine` 里的路径若不在 `layers.yaml` 的 engine 里，
                      正文又没提它的文件名 —— 这多半是**间接依赖**（skill 委托给另一个 skill 去跑），
                      不是坏，是**登记与正文的分工没说清**，交人裁。
  C3 说的 = 做的      **红**：注册表登记了引擎，正文却一个文件名都没提（agent 照正文走不到那些引擎）。
                      **黄**：正文提到的 `kb/...` 路径没登记进 `depends_on_engine`（登记不完整）。
  C4 触发词可生效     注册表 `trigger_keywords` 里的每条，必须出现在 SKILL.md 的 description（frontmatter）里
                      —— 登记了却没写进 description 的触发词，**触发面上等于不存在**。
  C5 装机位一致        **红**：`install_target` 下必须有该目录与 SKILL.md，且 frontmatter `name` 与 id/dir_name 对得上。
                      **红（2026-09-30 补）**：SKILL.md 的 frontmatter **必须读得出来**（起始 `---` 围栏在场），
                      且 `name` **必须合宿主的字符集规则** `^[\p{L}0-9]+(?:-[\p{L}0-9]+)*$`。
                      这两条**彼此独立、各自都足以**让成员在任何会话里**选不到**：宿主 `parseSkillFile`
                      对前者记 `missing YAML frontmatter`、对后者记 `invalid skill name`，**都是整份忽略**。
                      实测 `brand-ai-provenance-rights-review` 就这么在生产态隐形了 —— 两个缺陷叠在同一个
                      文件上，而本闸门当时**没报**（`_frontmatter()` 返回空串 → `name=None` →
                      `if name and …` 直接跳过），只剩 C4 一条黄条喊"触发词没写进 description"，
                      没人会从那条读出"这个成员根本不存在于任何会话里"。

## 只读

只读 kb/l7/registry/*.yaml、kb/l7/skills/**、~/.dsh/skills/**、kb/l7/registry/layers.yaml。
**不写任何文件**。

用法：
    kb/kbpy l7/scripts/skill_conformance.py [--json] [--quiet] [--only <skill-id>]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
KB = Path(os.environ.get("KB_GATE_KB") or HERE.parents[1])       # …/kb
ROOT = KB.parent
REG = KB / "l7/registry"
SKILLS_YAML = REG / "skills.yaml"
LAYERS_YAML = REG / "layers.yaml"
HOME_SKILLS = Path(os.environ.get("KB_GATE_INSTALL") or (Path.home() / ".dsh/skills"))

# 注册表文件、契约文件这类「不是层引擎」的依赖，允许不进 layers.yaml
NON_ENGINE_PREFIXES = ("l7/registry/", "l7/output_template.md", "l7/selftest", "l7/review-engine/contracts/")
PATH_RE = re.compile(r"\bkb/[A-Za-z0-9_./\-]+\.(?:py|jsonl|json|yaml|md)")
CAP = 6


def _yaml(p):
    import yaml
    return yaml.safe_load(open(p, encoding="utf-8"))


def _frontmatter(text):
    m = re.match(r"^---\r?\n([\s\S]*?)\r?\n---", text)
    return m.group(1) if m else ""


def _host_name_ok(name):
    """宿主 `isSkillName` 的等价判据：`^[\\p{L}0-9]+(?:-[\\p{L}0-9]+)*$`。

    逐段判：段内每个字符必须是**字母**（`str.isalpha()` == Unicode 类别 L*，与 `\\p{L}` 对齐）
    或 **ASCII 数字**（用 `isascii()` 卡掉上标数字那类 `isdigit()` 也为真的怪字符）。
    空格、下划线、点、斜杠都会在这里被挡掉 —— 宿主对它们一律判 `invalid skill name`。
    """
    if not name:
        return False
    for part in name.split("-"):
        if not part:
            return False
        if not all(c.isalpha() or (c.isascii() and c.isdigit()) for c in part):
            return False
    return True


def compute():
    for p in (SKILLS_YAML, LAYERS_YAML):
        if not p.exists():
            return None, "输入缺失：%s" % p
    reg_rows = _yaml(SKILLS_YAML)
    reg_rows = reg_rows["skills"] if isinstance(reg_rows, dict) and "skills" in reg_rows else reg_rows
    layers = _yaml(LAYERS_YAML)["layers"]
    layer_engines = set()
    for l in layers:
        for e in (l.get("engine") or []):
            layer_engines.add(str(e).split()[0].replace("kb/", "", 1))

    c1, c2, c3_hard, c3_soft, c4, c5 = [], [], [], [], [], []
    checked = 0
    for r in reg_rows:
        sid = r.get("id")
        if not sid:
            continue
        engines = [str(e) for e in (r.get("depends_on_engine") or [])]
        if not engines and r.get("status") != "生产":
            continue
        inst_dir = HOME_SKILLS / (r.get("dir_name") or sid)
        md = inst_dir / "SKILL.md"
        if not md.exists():
            if r.get("status") == "生产":
                c5.append([sid, "装机位没有 %s/SKILL.md" % inst_dir.name])
            continue
        checked += 1
        text = md.read_text(encoding="utf-8", errors="replace")
        fm = _frontmatter(text)

        # C5① frontmatter 必须**读得出来**（缺起始围栏 → 宿主整份忽略，成员不可选）
        if not fm.strip():
            c5.append([sid, "SKILL.md 读不出 frontmatter（缺起始 `---` 围栏）→ 宿主按 "
                            "missing YAML frontmatter 整份忽略，成员在任何会话里都选不到"])
        else:
            # C5② frontmatter name
            m = re.search(r"(?m)^name:\s*(.+?)\s*$", fm)
            name = m.group(1).strip().strip('"\'') if m else None   # 剥引号：实测 frontmatter 里是 "tdd"
            if name and name not in (sid, r.get("dir_name")):
                c5.append([sid, "frontmatter name=%s 与 id/dir_name 不一致" % name])
            # C5③ name 必须合宿主的字符集规则（空格/下划线/点 → invalid skill name，成员不可选）
            if name and not _host_name_ok(name):
                c5.append([sid, "frontmatter name=%s 含宿主不接受的字符（空格/下划线/点等）→ "
                                "宿主判 invalid skill name 并整份忽略，成员在任何会话里都选不到" % name])

        # C4 触发词必须出现在 description
        kw = r.get("trigger_keywords") or []
        fm_body = fm
        missing_kw = [k for k in kw if k not in fm_body]
        if missing_kw:
            c4.append([sid, "%d 条触发词没写进 description" % len(missing_kw), missing_kw[:CAP]])

        # C1/C2/C3①
        for e in engines:
            rel = e.replace("kb/", "", 1)
            if not (ROOT / "kb" / rel).exists() and not (ROOT / rel).exists():
                c1.append([sid, rel, "路径不存在"])
                continue
            if rel in layer_engines:
                continue
            if any(rel.startswith(p) for p in NON_ENGINE_PREFIXES):
                continue
            if Path(rel).name not in text:
                c2.append([sid, rel, "不在 layers.yaml 的 engine 里，且正文没有它的文件名"])

        # C3①（红）登记了引擎 → 正文至少要提到一个文件名
        if engines and not any(Path(e.replace("kb/", "", 1)).name in text for e in engines):
            c3_hard.append([sid, "注册表登记了 %d 个引擎，正文一个文件名都没提" % len(engines)])

        # C3② 正文里的 kb/ 路径必须在 depends_on_engine 或白名单里
        allowed = {e.replace("kb/", "", 1) for e in engines}
        for hit in set(PATH_RE.findall(text)):
            rel = hit.replace("kb/", "", 1)
            if rel in allowed or any(rel.startswith(p) for p in NON_ENGINE_PREFIXES):
                continue
            if rel.startswith(("l7/scripts/", "l1/index/")):     # 闸门/检查器脚本：常见且已在别处登记
                continue
            c3_soft.append([sid, rel, "正文提到但注册表没登记"])

    # 明细**存全量**、截断只发生在打印时（main 里的 [:6]/[:4]）。
    # 为什么必须这样：`--only` 是**在这份明细上**过滤、再按过滤后的列表重算 `_n` 的。
    # 2026-09-30 实测过一个假阴性：明细先截到 40 条，目标成员的第 41 条起被切掉 →
    # `--only <该成员>` 报 `C5_n = 0 / red 0 / 结论过`，而全量 compute() 里它是红的。
    # **闸门自己静默说谎**比闸门漏检更危险，所以这里存全量、把截断推到输出层。
    rep = {
        "counts": {"registered": len(reg_rows), "installed_checked": checked},
        "C1_missing_engine": c1, "C1_n": len(c1),
        "C2_engine_not_in_layers": c2, "C2_n": len(c2),
        "C3_hard": c3_hard, "C3_hard_n": len(c3_hard),
        "C3_soft": c3_soft, "C3_soft_n": len(c3_soft),
        "C4_keyword_not_in_description": c4, "C4_n": len(c4),
        "C5_install_mismatch": c5, "C5_n": len(c5),
    }
    # 红 = 会让工作流真出错的三类；黄 = 登记/文本漂移，需人裁（分开计数，别混成一个数）
    rep["red_total"] = rep["C1_n"] + rep["C3_hard_n"] + rep["C5_n"]
    rep["warn_total"] = rep["C2_n"] + rep["C3_soft_n"] + rep["C4_n"]
    return rep, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--only", default=None, help="只看某个 skill id")
    a = ap.parse_args()

    rep, err = compute()
    if rep is None:
        print("❌ 无法计算：%s" % err)
        print("退出码：2")
        return 2

    if a.only:
        for k in ("C1_missing_engine", "C2_engine_not_in_layers", "C3_hard", "C3_soft",
                  "C4_keyword_not_in_description", "C5_install_mismatch"):
            rep[k] = [x for x in rep[k] if x and x[0] == a.only]
        rep["C1_n"] = len(rep["C1_missing_engine"]); rep["C2_n"] = len(rep["C2_engine_not_in_layers"])
        rep["C3_hard_n"] = len(rep["C3_hard"]); rep["C3_soft_n"] = len(rep["C3_soft"])
        rep["C4_n"] = len(rep["C4_keyword_not_in_description"]); rep["C5_n"] = len(rep["C5_install_mismatch"])
        rep["red_total"] = rep["C1_n"] + rep["C3_hard_n"] + rep["C5_n"]
        rep["warn_total"] = rep["C2_n"] + rep["C3_soft_n"] + rep["C4_n"]

    ok = rep["red_total"] == 0
    if a.json:
        print(json.dumps({"gate": "skill_conformance", "ok": ok, **rep}, ensure_ascii=False, indent=1))
        return 0 if ok else 1

    c = rep["counts"]
    print("=" * 78)
    print("skill_conformance —— 四方对账：skill 文本 ↔ 注册表 ↔ 层契约 ↔ 磁盘")
    print("  注册表 %d 行 ｜ 实际逐条核过的已装成员 %d 个" % (c["registered"], c["installed_checked"]))
    print("-" * 78)
    if not a.quiet:
        for key, nkey, label in (("C1_missing_engine", "C1_n", "🔴 C1 引擎路径不存在"),
                                 ("C3_hard", "C3_hard_n", "🔴 C3 登记了引擎但正文一个都没提"),
                                 ("C5_install_mismatch", "C5_n", "🔴 C5 装机位/名字不一致")):
            if rep[nkey]:
                print("%s（%d）：" % (label, rep[nkey]))
                for row in rep[key][:6]:
                    print("   · %s" % " ｜ ".join(str(x)[:60] for x in row))
        for key, nkey, label in (("C2_engine_not_in_layers", "C2_n", "🟡 C2 间接依赖（正文没提文件名）"),
                                 ("C3_soft", "C3_soft_n", "🟡 C3 正文提到但注册表没登记"),
                                 ("C4_keyword_not_in_description", "C4_n", "🟡 C4 触发词没写进 description")):
            if rep[nkey]:
                print("%s：%d 处（抽样）" % (label, rep[nkey]))
                for row in rep[key][:4]:
                    print("   · %s" % " ｜ ".join(str(x)[:56] for x in row[:3]))
    print("-" * 78)
    print("结论：%s ｜ 红 %d ｜ 黄（触发词）%d"
          % ("✅ 过（四方一致）" if ok else "❌ 未过", rep["red_total"], rep["warn_total"]))
    print("退出码：%d" % (0 if ok else 1))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
