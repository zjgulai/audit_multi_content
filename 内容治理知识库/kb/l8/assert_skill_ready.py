#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""assert_skill_ready.py —— 「这个 skill 现在**能不能被 harness 读到**」的入口闸门。

## 为什么要它（2026-10-21 实测，本机真踩）

同一份 `SKILL.md`，shell 侧读得干干净净，**harness 侧读出来是二进制**：

| 读者 | 同一路径读数 |
|---|---|
| `stat` / `ls -l` | 18180 字节 |
| 顺序读到 EOF（python / `wc -c` / node `readFileSync`） | **14084** 字节，UTF-8 合法、无 NUL |
| `dd skip=14084` | 乱码（`f4ba 2d9e …`） |

差正好 **4096** —— 就是本库登记过的「信封态」（见 `tools/envelope_gate.py` 头注释：
python 写 `.py/.txt/.md` 会落成 stat 虚高 4096 的信封，宿主 Electron 侧读成乱码）。

后果不是「报错」，而是**静默降级**：`dsh-skill-filesystem` 读该文件抛
`FsError: cannot read "…": binary file`（判据在 `dsh-fs-local/lib/index.js:313/355`）⇒
该 skill 被跳过 ⇒ **不进会话 catalog** ⇒ `skill` 工具报
`skill "X" is unknown or no longer available`。实测日志（2026-10-21）：

    09:56:44 [skill-filesystem] skill file …/图片安全审查/SKILL.md ignored: … binary file
    10:03:31 / 10:09:34 / 10:12:32  同一条反复出现

⇒ 审查照跑、报告照发，**判定主体那个 skill 一次都没加载过**，而流程上没有任何东西会红。
本脚本就是把这件事变成**入口红灯**：skill 不健康 ⇒ 退出码 4 ⇒ 评审链在层闸门之前就停。

## 判据（四条，缺一红）

1. **在**：`<skills_home>/<name>/SKILL.md` 存在且是常规文件
2. **不是信封**：`os.stat().st_size == len(顺序读到 EOF 的字节)`；差 4096 时点名「信封态」
3. **是文本**：前 8192 字节无 NUL、整份 UTF-8 可解码（与 harness 的 `FS_NOT_TEXT` 同一口径）
4. **frontmatter 合法**：`---` 包裹、`name`/`description` 齐、`name` 合 harness 的
   `^[\\p{L}0-9]+(?:-[\\p{L}0-9]+)*$`；目录名 ≠ `name` 只告警不判红（harness 认 frontmatter）

## 用法

    python3 kb/l8/assert_skill_ready.py --skill 图片安全审查
    python3 kb/l8/assert_skill_ready.py --skill 图片安全审查 --skill kb-recall --json
    python3 kb/l8/assert_skill_ready.py --all            # 扫 skills_home 下全部（周期巡检用）
    python3 kb/l8/assert_skill_ready.py --selftest       # 纯夹具，含**反向对照**

退出码：0 全部就绪 ｜ 4 有不就绪 ｜ 2 用法/环境错误

**只读**：不修改任何文件。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import stat as _stat
import sys
import tempfile
from pathlib import Path

try:
    import yaml
except Exception:                                    # pragma: no cover - 环境缺件
    yaml = None

#: harness 侧同一个正则（`@deepseek-ai/dsh-skill/lib/index.js:17`）：
#:   `/^[\p{L}0-9]+(?:-[\p{L}0-9]+)*$/u`
#: Python 没有 \p{L}，用「word 字符里排除下划线」近似 —— `[^\W_]` = 字母 + 数字（含 Unicode 字母），
#: 与 harness 的「字母/数字 + 连字符分段」等价；**下划线必须判红**（harness 会拒）。
_CN_KEBAB = re.compile(r"^[^\W_]+(?:-[^\W_]+)*$")

#: harness 的二进制采样窗口（`dsh-fs-local/lib/index.js` BINARY_SAMPLE_BYTES）
SAMPLE = 8192

#: 信封态的特征差（库内口径：恒 4096）
ENVELOPE_DELTA = 4096


def default_skills_home() -> Path:
    env = os.environ.get("DSH_SKILLS_HOME")
    if env:
        return Path(env).expanduser()
    home = os.environ.get("DSH_HOME")
    if home:
        return Path(home).expanduser() / "skills"
    return Path.home() / ".dsh" / "skills"


def envelope_verdict(stat_size: int, read_size: int) -> str | None:
    """stat 与「读到 EOF」的长度不一致时的判决（纯函数，便于自证）。

    返回 None 表示一致；否则返回人话原因。差 4096 时点名信封态 —— 这正是本机的那种坏法。
    """
    if stat_size == read_size:
        return None
    delta = stat_size - read_size
    if abs(delta) == ENVELOPE_DELTA:
        return ("信封态：stat=%d 字节，读到 EOF 只有 %d 字节（差 %d = 库内登记的信封差）；"
                "宿主 Electron 侧会读成乱码 ⇒ harness 判 binary file"
                % (stat_size, read_size, delta))
    return "读数不一致：stat=%d 字节，读到 EOF 只有 %d 字节（差 %d）" % (stat_size, read_size, delta)


def _frontmatter_reasons(raw_text: str) -> list[str]:
    """frontmatter 四条：包裹 / 可解析 / 有 name+description / name 合 harness 语法。"""
    reasons: list[str] = []
    if not raw_text.startswith("---"):
        return ["frontmatter：文件不以 `---` 开头（harness 视为缺失 frontmatter）"]
    nl = raw_text.find("\n")
    if nl < 0:
        return ["frontmatter：只有一行，找不到闭合 `---`"]
    body = raw_text[nl + 1:]
    close = None
    pos = 0
    for line in body.splitlines(keepends=True):
        if line.rstrip("\r\n") == "---":
            close = pos
            break
        pos += len(line)
    if close is None:
        return ["frontmatter：找不到闭合 `---`"]
    if yaml is None:
        reasons.append("frontmatter：环境缺 PyYAML，未解析（不算通过，也不算失败）")
        return reasons
    try:
        data = yaml.safe_load(body[:close])
    except Exception as e:                            # noqa: BLE001
        return ["frontmatter：YAML 解析失败：%s" % e]
    if not isinstance(data, dict):
        return ["frontmatter：解析结果不是对象"]
    name = data.get("name")
    desc = data.get("description")
    if not isinstance(name, str) or not name.strip():
        reasons.append("frontmatter：缺 name")
    elif not _CN_KEBAB.match(name.strip()):
        reasons.append("frontmatter：name=%r 不合 harness 的 skill 名语法" % name)
    if not isinstance(desc, str) or not desc.strip():
        reasons.append("frontmatter：缺 description")
    return reasons


def diagnose(skill_dir: Path) -> dict:
    """对单个 skill 目录跑四条判据，返回结构化的诊断结果（**不抛异常**）。"""
    out = {"name": skill_dir.name, "path": str(skill_dir), "ok": False,
           "reasons": [], "warnings": [], "bytes": None}
    f = skill_dir / "SKILL.md"
    try:
        st = os.stat(f)
    except OSError:
        out["reasons"].append("找不到 %s（skill 目录存在，但没有 SKILL.md）" % f)
        return out
    if not _stat.S_ISREG(st.st_mode):
        out["reasons"].append("%s 不是常规文件" % f)
        return out
    try:
        content = f.read_bytes()
    except OSError as e:
        out["reasons"].append("读不了 %s：%s" % (f, e))
        return out
    out["bytes"] = len(content)

    verdict = envelope_verdict(st.st_size, len(content))
    if verdict:
        out["reasons"].append(verdict)
    if b"\x00" in content[:SAMPLE]:
        out["reasons"].append("前 %d 字节里出现 NUL ⇒ harness 判 binary file（FS_NOT_TEXT）" % SAMPLE)
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as e:
        out["reasons"].append("不是合法 UTF-8（第 %d 字节：%s）⇒ harness 判 binary file"
                              % (e.start, e.reason))
        return out

    out["reasons"].extend(_frontmatter_reasons(text))

    if yaml is not None:
        try:
            _front = text.split("\n---", 1)[0]
            name = yaml.safe_load(_front.split("\n", 1)[1]).get("name")
        except Exception:                             # noqa: BLE001
            name = None
        if isinstance(name, str) and name.strip() and name.strip() != skill_dir.name:
            out["warnings"].append("目录名 %r ≠ frontmatter name %r（harness 认 name，不认目录名）"
                                   % (skill_dir.name, name.strip()))

    out["ok"] = not out["reasons"]
    return out


def selftest() -> int:
    """纯夹具自证：**每条判据都要有一个能把它判红的样本**（反向对照）。"""
    passed = failed = 0
    tmp = Path(tempfile.mkdtemp(prefix="skill-ready-selftest-"))

    def expect(label: str, cond: bool, detail: str = "") -> None:
        nonlocal passed, failed
        if cond:
            passed += 1
        else:
            failed += 1
            print("  ❌ %s %s" % (label, detail))

    good_fm = ("---\nname: %s\ndescription: |\n  演示用 skill。\n---\n\n# Demo\n\n正文。\n")

    def mk(name: str, text: str) -> Path:
        d = tmp / name
        d.mkdir(parents=True, exist_ok=True)
        (d / "SKILL.md").write_text(text, encoding="utf-8")
        return d

    # ① 正例：合法文件必须判「就绪」（否则后面全部反向对照都没有意义）
    ok = diagnose(mk("demo-ok", good_fm % "demo-ok"))
    expect("① 合法 skill 判就绪", ok["ok"], json.dumps(ok["reasons"], ensure_ascii=False))

    # ② 反向对照：文件里带 NUL ⇒ 必须判红（harness 的 NUL 采样分支）
    b = diagnose(mk("demo-nul", (good_fm % "demo-nul") + "\x00\x00\x00"))
    expect("② NUL ⇒ 判红", not b["ok"] and any("NUL" in r for r in b["reasons"]),
           json.dumps(b["reasons"], ensure_ascii=False))

    # ③ 反向对照：信封态（stat 比内容多 4096）⇒ 纯函数必须点名信封
    v = envelope_verdict(18180, 14084)
    expect("③ 差 4096 ⇒ 判信封态", v is not None and "信封态" in v, str(v))
    expect("③b 一致 ⇒ 不报", envelope_verdict(14084, 14084) is None)
    expect("③c 差 4096（负向）也判信封", (envelope_verdict(14084, 18180) or "").find("信封态") >= 0)

    # ④ 反向对照：缺 description ⇒ 判红
    d = diagnose(mk("demo-nodesc", "---\nname: demo-nodesc\n---\n\n正文\n"))
    expect("④ 缺 description ⇒ 判红",
           not d["ok"] and any("description" in r for r in d["reasons"]),
           json.dumps(d["reasons"], ensure_ascii=False))

    # ⑤ 反向对照：name 带空格 ⇒ 判红
    e = diagnose(mk("demo-badname", "---\nname: demo bad\ndescription: x\n---\n\n正文\n"))
    expect("⑤ name 不合语法 ⇒ 判红",
           not e["ok"] and any("name=" in r for r in e["reasons"]),
           json.dumps(e["reasons"], ensure_ascii=False))

    # ⑥ 反向对照：没有 SKILL.md ⇒ 判红
    empty = tmp / "demo-empty"
    empty.mkdir(parents=True, exist_ok=True)
    f = diagnose(empty)
    expect("⑥ 缺 SKILL.md ⇒ 判红", not f["ok"] and any("SKILL.md" in r for r in f["reasons"]),
           json.dumps(f["reasons"], ensure_ascii=False))

    # ⑦ 反向对照：非法 UTF-8 ⇒ 判红（harness 的 decodeUtf8 fatal 分支）
    g = tmp / "demo-badutf8"
    g.mkdir(parents=True, exist_ok=True)
    (g / "SKILL.md").write_bytes(b"---\nname: demo-badutf8\ndescription: x\n---\n\xff\xfe\x80\n")
    h = diagnose(g)
    expect("⑦ 非法 UTF-8 ⇒ 判红", not h["ok"] and any("UTF-8" in r for r in h["reasons"]),
           json.dumps(h["reasons"], ensure_ascii=False))

    # ⑧ 目录名 ≠ name ⇒ 只告警、不判红（harness 认 frontmatter）
    i = diagnose(mk("demo-dirname", good_fm % "demo-other"))
    expect("⑧ 目录名不一致只告警", i["ok"] and bool(i["warnings"]),
           json.dumps({"reasons": i["reasons"], "warnings": i["warnings"]}, ensure_ascii=False))

    print("assert_skill_ready selftest：通过 %d ／ 失败 %d（夹具目录 %s）" % (passed, failed, tmp))
    return 0 if failed == 0 else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="skill 就绪闸门：harness 读不读得到、是不是真货")
    ap.add_argument("--skill", action="append", default=None,
                    help="skill 名（**可重复**：--skill A --skill B）。"
                         "别写成一个 flag 带多个值 —— argparse 的 nargs='+' 遇到重复 flag 会"
                         "**后者覆盖前者**（实测因此漏检过四个 skill 里的三个）")
    ap.add_argument("--all", action="store_true", help="扫 skills_home 下的全部 skill 目录")
    ap.add_argument("--skills-home", default=None, help="默认 $DSH_HOME/skills（本机 ~/.dsh/skills）")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)

    if a.selftest:
        return selftest()

    home = Path(a.skills_home).expanduser() if a.skills_home else default_skills_home()
    if not home.is_dir():
        print("skills 目录不存在：%s（用 --skills-home 指定）" % home, file=sys.stderr)
        return 2

    if a.all:
        targets = sorted(p for p in home.iterdir() if p.is_dir() and not p.name.startswith("."))
    elif a.skill:
        targets = [home / s for s in a.skill]
    else:
        print("给 --skill <名字…> 或 --all（或 --selftest）", file=sys.stderr)
        return 2

    results = [diagnose(p) for p in targets]
    bad = [r for r in results if not r["ok"]]
    payload = {"skills_home": str(home), "ok": not bad,
               "checked": len(results), "not_ready": len(bad), "skills": results}

    if a.json:
        print(json.dumps(payload, ensure_ascii=False, indent=1))
    elif not a.quiet:
        for r in results:
            mark = "✅" if r["ok"] else "❌"
            print("%s %-24s %s" % (mark, r["name"], ("%d 字节" % r["bytes"]) if r["bytes"] is not None else ""))
            for why in r["reasons"]:
                print("     · %s" % why)
            for w in r["warnings"]:
                print("     ⚠️ %s" % w)
        print("—— 就绪 %d ／ 不就绪 %d（skills_home=%s）"
              % (len(results) - len(bad), len(bad), home))

    return 0 if not bad else 4


if __name__ == "__main__":
    sys.exit(main())
