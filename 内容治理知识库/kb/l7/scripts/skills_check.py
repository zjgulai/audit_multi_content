#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""skills_check.py —— DSH 宿主 skill 登记表自检。

读 kb/l7/registry/skills.yaml（静态真源），扫 ~/.dsh/skills/（宿主唯一装载位）的现场，
输出五类问题清单 + 分组汇总，退出码 0 = 全过、非 0 = 有问题。

五类问题：
  1. 应装未装     —— 表中 scope=本项目 且 status=生产，但 ~/.dsh/skills/<id> 不存在
  2. 装了但没登记 —— ~/.dsh/skills/ 里有目录，表里没有对应 id（另含「参考项被装进装载位」）
  3. 副本不一致   —— 表中 source 非 null 的，安装副本与源逐文件 cmp；
                     ★ 装机位若是指向真源的**符号链接**，本项对其**不适用**（拿真源比真源恒等）
                       ⇒ 显式记进「备注」，不冒充通过；链接的解析由 watch_review_readiness 兜底。
                     lark-* 另按官方基准 lark-cli skills read <id> 校验是否落后于 CLI 版本
  4. 依赖缺失     —— depends_on_engine 的路径在库内不存在（另含 depends_on_skills 未登记）
  5. 自测缺失     —— selftest 路径不存在（selftest 填 null 的按「未登记」单列，不算错误）

两处口径，写死在这里，不在表里重复：
  * 「应装未装」只对 scope=本项目 有意义 —— 宿主自带 / 通用的 skill 不参与该判定。
  * 表是静态真源，安装状态一律运行时算出来，不写回表。

**不依赖第三方包**：读表有两条路径——有 PyYAML 就用 PyYAML，没有就用本文件内置的
YAML 子集解析器（见「内置 YAML 子集解析器」一节）。两条路径结果必须一致，可用
--verify-parsers 逐节点比对。这样换解释器 / 上 CI 也不会先报「缺 PyYAML」——
自检脚本自己不该成为需要被 check 的东西。

用法：
  python3 skills_check.py                 # 体检
  python3 skills_check.py --kb-root <库根> # 指定库根（含 KB-ROOT.json 的那一层）
  python3 skills_check.py --json          # 额外输出机器可读汇总
  python3 skills_check.py --quiet         # 只输出汇总与退出码
  python3 skills_check.py --no-yaml       # 强制走内置解析器（验证降级路径用）
  python3 skills_check.py --verify-parsers # 把两条解析路径的结果逐节点比对

环境变量：
  KB_ROOT              同 --kb-root
  SKILLS_CHECK_NO_YAML 置 1/true/yes/on 等价于 --no-yaml

退出码：0 全过 / 1 有问题 / 2 用法或环境错（表读不到、库根找不到）
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys

# ---------------------------------------------------------------- 常量

TABLE_REL = ("l7", "registry", "skills.yaml")
INSTALL_SLOT = "~/.dsh/skills"        # DSH 宿主唯一装载位
OTHER_SLOT = "~/.agents/skills"       # 另一套装载位（lark-cli 约定目录），本项目不装这里
LARK_CLI = "~/.dsh/bin/lark-cli"
KB_ROOT_MARKER = "KB-ROOT.json"

#: 已知落点（本机现状；换机器 / 挪库时用 --kb-root 或 KB_ROOT 覆盖）
COMMON_ROOTS = [
    "~/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理",
    "~/.dsh/Momcozy知识库",
]

#: 库根判定的最低要求：光有 marker 不够，还要这几层在（少一个说明拿到的不是这个库）
REQUIRED_LAYERS = ("l0", "l7")

STATUS_PRODUCTION = "生产"
STATUS_REFERENCE = "参考"
SCOPE_PROJECT = "本项目"

MAX_LISTED = 20   # 单个问题类别最多逐条列这么多，多的只报条数


def home(p):
    return os.path.abspath(os.path.expanduser(p))


# ---------------------------------------------------------------- 库根

def _root_ok(path):
    """这个目录算不算库根？返回 (bool, 说明)。"""
    if not path or not os.path.isdir(path):
        return False, "目录不存在"
    if os.path.isfile(os.path.join(path, KB_ROOT_MARKER)):
        missing = [d for d in REQUIRED_LAYERS if not os.path.isdir(os.path.join(path, d))]
        if missing:
            return False, "有 KB-ROOT.json 但缺目录：" + "、".join(missing)
        return True, "有 KB-ROOT.json 标记"
    # review.py 的口径：库根是含 kb/ 的那一层，标记在 kb/KB-ROOT.json
    inner = os.path.join(path, "kb")
    if os.path.isfile(os.path.join(inner, KB_ROOT_MARKER)):
        return True, "有 kb/KB-ROOT.json 标记（review.py 口径，已归一到 kb/）"
    return False, "没有 KB-ROOT.json"


def normalize_root(path):
    """把 review.py 口径的库根（含 kb/ 的那层）归一到含 KB-ROOT.json 的那层。"""
    if os.path.isfile(os.path.join(path, "kb", KB_ROOT_MARKER)):
        return os.path.join(path, "kb")
    return path


def find_root(start, explicit=None):
    """定位库根 = 含 KB-ROOT.json 的那一层目录。

    顺序：--kb-root → KB_ROOT → 从脚本位置往上找 → 已知落点。
    显式指定的路径无效直接报错，不悄悄换一个库继续跑（这是 review.py 定下的口径：
    静默换库会得到一份看起来正常、其实换了依据的报告）。
    """
    tried = []

    def try_path(label, path, fatal=False):
        p = home(path)
        ok, why = _root_ok(p)
        tried.append("%s=%s → %s" % (label, p, why))
        if ok:
            return normalize_root(p)
        if fatal:
            raise RuntimeError(
                "--kb-root 指定的目录不是知识库根：%s\n  原因：%s\n"
                "  库根要含 KB-ROOT.json（其下有 l0…l7）。" % (p, why))
        return None

    if explicit:
        got = try_path("--kb-root", explicit, fatal=True)
        if got:
            return got
    if os.environ.get("KB_ROOT"):
        got = try_path("环境变量 KB_ROOT", os.environ["KB_ROOT"])
        if got:
            return got
    d = os.path.abspath(start)
    while True:
        got = try_path("向上查找", d)
        if got:
            return got
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    for path in COMMON_ROOTS:
        got = try_path("已知落点", path)
        if got:
            return got
    raise RuntimeError(
        "找不到知识库根目录（要能找到含 KB-ROOT.json 的那一层，其下有 l0…l7）。试过：\n  "
        + "\n  ".join(tried)
        + "\n用 --kb-root <库根> 或环境变量 KB_ROOT 指定。")


# ---------------------------------------------------------------- 内置 YAML 子集解析器
#
# 为什么要有它：本脚本的职责是「随时能自检」。原来它硬依赖 PyYAML，换一个解释器
# （本机另一个 Python、CI、同事机器）就先报环境错 —— 自检脚本反而成了需要被 check 的东西。
# 所以：**有 PyYAML 就用 PyYAML，没有就用这份内置解析**，两条路径结果必须一致。
#
# 它只覆盖本表实际用到的 YAML 子集，不做通用 YAML：
#   · 整行注释（#）、空行
#   · 缩进嵌套的映射；块序列（含「序列项本身就是映射」的 `- key: value` 形态，
#     以及「序列与父键同缩进」这一 PyYAML safe_dump 默认写法）
#   · 标量：双引号串（支持 \n \t \r \0 \\ \" \/ \N \_ \L \P 与 \xNN / \uNNNN / \UNNNNNNNN
#           转义）、单引号串（'' → '）、裸标量、null/~、true/false、整数、浮点
#   · **跨行的 flow 标量**（这一条是为了「表被 YAML 工具重排后仍读得出来」）：
#           跨行双引号串 / 跨行单引号串 / 跨行裸标量，按 YAML 折行规则还原
#           （1 个换行折成空格，n 个连续换行折成 n-1 个换行），
#           并支持双引号串里的「行尾反斜杠续行」（不折成空格、直接接上）
#   · 行内列表 [a, b, "c"]（允许尾随逗号，不支持嵌套 [ 或 {）
#   · 块标量 >（clip）与 >-（strip）、|（literal）与 |-（strip literal）
#
# 遇到子集以外的构造一律**报错并给出行号**，绝不静默当成空值 —— 这是刻意的：
# 「读不到就当空」会让体检报告看起来正常、其实依据已经丢了。
#
# 明确不支持（会报错，不会静默）：保留模式 >+ / |+、锚点 & / 别名 * / 标签 !、
# 流式映射 {..}、裸标量的续行里出现映射键（': ' 或行尾冒号，PyYAML 也报错）、
# 裸标量里的 ' #'（YAML 会当注释截断）、跨行的行内列表、行尾注释、
# 制表符缩进、嵌套的 [ 或 {。
# 另外为了不与 YAML 语义悄悄分歧：**未加引号的标量里出现 ": " 或 " #" 会直接报错**
# （YAML 在前者会读成映射、在后者会把后面当注释），提示给该串加双引号。

class YamlSubsetError(ValueError):
    """内置解析器遇到不支持的 YAML 构造。消息里带行号。"""


#: 双引号串支持的转义（YAML 的一个常用子集）
_DQ_ESCAPES = {"0": "\0", "a": "\a", "b": "\b", "t": "\t", "n": "\n", "v": "\v",
               "f": "\f", "r": "\r", "e": "\x1b", " ": " ", '"': '"', "/": "/",
               "\\": "\\", "N": "\x85", "_": "\xa0", "L": "\u2028", "P": "\u2029"}

_INT_RE = re.compile(r"^[-+]?\d+$")
_FLOAT_RE = re.compile(r"^[-+]?(\d+\.\d*|\.\d+|\d+)([eE][-+]?\d+)?$")

#: 键名允许的形态：不含空白与 : # [ ] { }，且不以这些指示符或引号开头。
#: 本表的键全是 ASCII 标识符；放宽到「中文键也行」但仍严格挡住有歧义的形态。
_KEY_RE = re.compile(r"""^[^\s:#\[\]{}&*!|>'"][^\s:#]*$""")

#: 需要独占一行的块标量指示符（只支持这四个；+ 保留模式会报错）
_BLOCK_MARKERS = (">", ">-", ">+", "|", "|-", "|+")


class _YamlSubsetParser:
    """缩进驱动的递归下降解析器。任何超出子集的构造都 raise YamlSubsetError。"""

    def __init__(self, text):
        self.lines = text.split("\n")

    # ---- 基础工具

    def err(self, lineno, msg):
        raise YamlSubsetError("第 %d 行：%s" % (lineno, msg))

    def _is_blank(self, i):
        s = self.lines[i].strip()
        return (not s) or s.startswith("#")

    def _next_content(self, i):
        while i < len(self.lines) and self._is_blank(i):
            i += 1
        return i

    def _indent(self, i):
        n = 0
        for ch in self.lines[i]:
            if ch == " ":
                n += 1
            elif ch == "\t":
                self.err(i + 1, "缩进里用了制表符（YAML 只允许空格）")
            else:
                break
        return n

    # ---- 入口

    def parse(self):
        v, i = self._node(0)
        i = self._next_content(i)
        if i < len(self.lines):
            self.err(i + 1, "顶层还有解析不到的内容：%r" % self.lines[i].strip()[:60])
        return v

    def _is_seq_line(self, i):
        s = self.lines[i].strip()
        return s == "-" or s.startswith("- ")

    def _node(self, i):
        """从第 i 行开始解析一个块（映射或序列），返回 (值, 下一行号)。"""
        i = self._next_content(i)
        if i >= len(self.lines):
            return None, i
        ind = self._indent(i)
        s = self.lines[i].strip()
        if s == "-" or s.startswith("- "):
            return self._seq(i, ind)
        return self._map(i, ind)

    # ---- 序列

    def _seq(self, i, ind):
        items = []
        while True:
            i = self._next_content(i)
            if i >= len(self.lines):
                break
            cur = self._indent(i)
            if cur < ind:
                break
            if cur > ind:
                self.err(i + 1, "序列项缩进不一致（本层 %d 个空格，这行 %d 个）" % (ind, cur))
            s = self.lines[i].strip()
            if not (s == "-" or s.startswith("- ")):
                break
            rest = s[1:].strip()
            if rest == "":
                j = self._next_content(i + 1)
                if j < len(self.lines) and self._indent(j) > ind:
                    val, i = self._node(j)
                else:
                    val, i = None, i + 1
                items.append(val)
            elif self._is_map_start(rest):
                # 映射项的「同级键必须对齐」：键列 = 破折号后第一个非空格字符所在的列。
                # 必须按这一列去解析后续键，**不能**改成「下一行缩进多少就用多少」——
                # 那样会把「键没对齐」的坏表默默读成合法表（PyYAML 在这里是报错的），
                # 正是本解析器最不该犯的错：静默地把依据读歪。
                m = re.match(r"^-( +)", self.lines[i][ind:])
                keycol = ind + 1 + len(m.group(1)) if m else ind + 2
                val, i = self._map(i, keycol, first=rest, first_lineno=i + 1)
                items.append(val)
            else:
                val, i = self._read_scalar(rest, i, ind)
                items.append(val)
        return items, i

    def _is_map_start(self, rest):
        """序列项 `- xxx` 里的 xxx 是「映射的首键」还是「一个标量」？"""
        if rest[:1] in ('"', "'", "[", "{", "&", "*", "!", "|", ">"):
            return False
        m = re.match(r"^([^:]*?):(?:[ \t]|$)", rest)
        return bool(m) and bool(_KEY_RE.match(m.group(1).strip()))

    # ---- 映射

    def _map(self, i, ind, first=None, first_lineno=None):
        out = {}
        pending, plineno = first, first_lineno
        while True:
            if pending is not None:
                text, lineno = pending, plineno
                li = i                      # 这一行就是 '  - id: xxx'
                pending = None
                i += 1                      # 消费掉 '  - id: xxx' 这一行
            else:
                i = self._next_content(i)
                if i >= len(self.lines):
                    break
                cur = self._indent(i)
                if cur < ind:
                    break
                if cur > ind:
                    self.err(i + 1, "缩进跳级（本层 %d 个空格，这行 %d 个）" % (ind, cur))
                text, lineno = self.lines[i].strip(), i + 1
                li = i
                i += 1
            key, rest = self._split_key(text, lineno)
            if rest == "":
                j = self._next_content(i)
                if j < len(self.lines) and self._indent(j) > ind:
                    val, i = self._node(j)
                elif j < len(self.lines) and self._indent(j) == ind and self._is_seq_line(j):
                    # YAML 允许「块的序列与父键同缩进」，而且这是 PyYAML safe_dump 的默认写法：
                    #   skills:
                    #   - id: x
                    # 不支持它的话，表被任何 YAML 工具重排一次就会读不出来。
                    val, i = self._seq(j, ind)
                else:
                    val = None
                out[key] = val
            elif rest in _BLOCK_MARKERS:
                if rest not in (">", ">-", "|", "|-"):
                    self.err(lineno, "内置解析器只支持 >、>-、|、|- 四种块标量写法，不支持 %r"
                             % rest)
                val, i = self._block_scalar(i, ind, literal=rest.startswith("|"),
                                            strip=rest.endswith("-"))
                out[key] = val
            elif rest.startswith("["):
                out[key] = self._flow_seq(rest, lineno)
            else:
                # 用 _read_scalar：它可能吃掉后续行（跨行引号串）
                val, i = self._read_scalar(rest, li, ind)
                out[key] = val
        return out, i

    def _split_key(self, text, lineno):
        if text[:1] == "{":
            self.err(lineno, "内置解析器不支持流式映射 {..}（这份表被 dump 成了 flow 风格）；"
                             "请用默认的块风格 dump：%r" % text[:50])
        m = re.match(r"^([^:]*):(?:[ \t](.*))?$", text)
        if not m:
            self.err(lineno, "既不是 key: value，也不是序列项：%r" % text[:60])
        key, rest = m.group(1).strip(), (m.group(2) or "").strip()
        if not _KEY_RE.match(key):
            self.err(lineno, "键名形态不认识（含空白或特殊字符）：%r" % key[:40])
        return key, rest

    # ---- 折叠块标量（仅 > 与 >-）

    def _block_scalar(self, i, key_indent, literal=False, strip=False):
        raw, j = [], i
        while j < len(self.lines):
            l = self.lines[j]
            if l.strip() == "":
                raw.append("")              # 可能是块内空行，也可能是块已结束；先收着
                j += 1
                continue
            if self._indent(j) <= key_indent:
                break
            raw.append(l.strip())
            j += 1
        while raw and raw[-1] == "":        # 尾部空行不算内容
            raw.pop()
        if not raw:
            return "", j
        if literal:                         # | ：换行原样保留
            return "\n".join(raw) + ("" if strip else "\n"), j
        out = []                            # > ：折行之间折成空格，空行折成换行
        for l in raw:
            if l == "":
                out.append("\n")
            else:
                if out and out[-1] != "\n":
                    out.append(" ")
                out.append(l)
        return "".join(out) + ("" if strip else "\n"), j

    # ---- 行内列表

    def _flow_seq(self, s, lineno):
        if not s.endswith("]"):
            self.err(lineno, "行内列表没有正常闭合（不支持跨行的行内列表）：%r" % s[:60])
        body = s[1:-1].strip()
        if body == "":
            return []
        parts, buf, k, quote = [], [], 0, None
        while k < len(body):
            ch = body[k]
            if quote:
                buf.append(ch)
                if ch == "\\" and quote == '"' and k + 1 < len(body):
                    buf.append(body[k + 1])
                    k += 2
                    continue
                if ch == quote:
                    quote = None
                k += 1
                continue
            if ch in ('"', "'"):
                quote = ch
                buf.append(ch)
                k += 1
                continue
            if ch in "[{":
                self.err(lineno, "行内列表里不支持嵌套的 [ 或 {：%r" % s[:60])
            if ch == ",":
                parts.append("".join(buf))
                buf = []
                k += 1
                continue
            buf.append(ch)
            k += 1
        if quote:
            self.err(lineno, "行内列表里有没闭合的引号：%r" % s[:60])
        parts.append("".join(buf))
        if len(parts) > 1 and parts[-1].strip() == "":   # 允许尾随逗号
            parts.pop()
        out = []
        for p in parts:
            p = p.strip()
            if p == "":
                self.err(lineno, "行内列表里有空项（连续逗号）：%r" % s[:60])
            out.append(self._scalar(p, lineno))
        return out

    # ---- 标量：入口（支持跨行引号串）

    def _read_scalar(self, rest, li, ind):
        """读一个标量值。li = 值所在行的行下标，ind = 本层块的缩进。返回 (值, 下一行下标)。

        与 _scalar 的区别：这个版本**会吃掉后续行**，用来支持两种跨行写法：
          · 跨行引号串（PyYAML safe_dump 对含换行的长串、以及按宽度折行的串会这么写）
          · 跨行裸标量（safe_dump 会把过长的裸标量折到下一行）
        两种都用同一套 YAML flow 折行规则，见 _fold_flow。
        """
        s = rest.strip()
        if s[:1] in ('"', "'"):
            return self._quoted_any_line(s, li)
        if s == "" or s[:1] in ("{", "&", "*", "!", "[", "|", ">"):
            return self._scalar(s, li + 1), li + 1
        # —— 裸标量：可能跨行。续行必须比本层更缩进；比本层浅就是标量结束。
        raw, j, blanks = [s], li + 1, 0
        while j < len(self.lines):
            line = self.lines[j]
            if line.strip() == "":
                blanks += 1
                j += 1
                continue
            if line.strip().startswith("#") or self._indent(j) <= ind:
                break
            cont = line.strip()
            # 这几条是刻意报错而不是吸收：YAML 在这里会报错（映射键不允许出现在
            # 裸标量的续行里），静默吸收会把一张坏表读成一张好表。
            # 实测过的边界（2026-09-29 逐条问过 PyYAML）：
            #   · 续行含 ': ' 或行尾是 ':'  → PyYAML 报错   → 这里也报错
            #   · 续行含 '15:11'（冒号后无空白）→ PyYAML 当正文 → 这里也当正文
            #   · 续行以 - [ { ] 开头       → PyYAML 当正文 → 这里**不能**拦
            # 所以只认 ': ' 与行尾冒号，不要按「有没有冒号」或首字符一刀切。
            if ": " in cont or cont.endswith(":"):
                self.err(j + 1, "裸标量的续行里出现了映射键（': ' 或行尾冒号），"
                                "YAML 在这里会报错，内置解析器也不吸收它：%r" % cont[:50])
            raw.extend([""] * blanks)
            blanks = 0
            raw.append(cont)
            j += 1
        if len(raw) == 1:
            return self._scalar(s, li + 1), li + 1
        return self._fold_flow(raw, ""), j      # 裸标量没有引号，不涉及反斜杠续行

    def _find_close(self, s, start, quote, lineno):
        """在本行里找闭合引号的位置；本行没有就返回 None。会跳过转义。"""
        k = start
        while k < len(s):
            ch = s[k]
            if quote == '"' and ch == "\\":
                k += 2
                continue
            if ch == quote:
                if quote == "'" and k + 1 < len(s) and s[k + 1] == "'":
                    k += 2                      # '' 是转义的单引号，不是闭合
                    continue
                return k
            k += 1
        return None

    def _quoted_any_line(self, s, li):
        quote = s[0]
        end = self._find_close(s, 1, quote, li + 1)
        if end is not None:
            if s[end + 1:].strip() != "":
                self.err(li + 1, "引号串后面还有多余内容：%r" % s[:60])
            return self._unescape(s[1:end], quote, li + 1), li + 1
        # —— 跨行：把后续物理行收进来，按 YAML flow 标量的折行规则拼回一个字符串
        raw = [s[1:]]
        j = li + 1
        while j < len(self.lines):
            line = self.lines[j]
            end = self._find_close(line, 0, quote, j + 1)
            seg = line if end is None else line[:end]
            raw.append(seg)
            if end is not None:
                if line[end + 1:].strip() != "":
                    self.err(j + 1, "引号串后面还有多余内容：%r" % line.strip()[:60])
                return self._unescape(self._fold_flow(raw, quote), quote, li + 1), j + 1
            j += 1
        self.err(li + 1, "%s引号串一直到文件末尾都没有闭合"
                 % ("双" if quote == '"' else "单"))

    def _fold_flow(self, segs, quote):
        """flow 标量的折行规则：1 个换行折成空格，n 个连续换行折成 n-1 个换行。

        首行只去尾部空白（紧跟引号的内容是正文，前导空格要留）；后续行的首尾空白都去掉
        （那是缩进，不是内容）。结尾那一段空白行正是 safe_dump 用来表达尾部换行的。

        双引号串还要先处理「行尾反斜杠续行」：`\\` 在行尾 = 转义掉这个换行，
        两段直接拼上、不留空格（allow_unicode=False 的长串折行就是这个形式）。
        """
        if quote == '"':
            merged, i = [], 0
            while i < len(segs):
                rst = segs[i].rstrip()
                if (len(rst) - len(rst.rstrip("\\"))) % 2 == 1 and i + 1 < len(segs):
                    segs[i] = rst[:-1] + segs[i + 1].strip()   # 接上，不留空格
                    del segs[i + 1]
                    continue                                    # 合并后的这段再看一次
                merged.append(segs[i])
                i += 1
            segs = merged
        norm = [segs[0].rstrip()] + [x.strip() for x in segs[1:]]
        out, started, breaks = [], False, 0
        for seg in norm:
            if not started:
                started = True
                if seg == "":
                    breaks += 1
                    continue
                out.append(seg)
                continue
            breaks += 1
            if seg == "":
                continue
            out.append(" " if breaks == 1 else "\n" * (breaks - 1))
            out.append(seg)
            breaks = 0
        if breaks >= 2:
            out.append("\n" * (breaks - 1))
        return "".join(out)

    def _unescape(self, body, quote, lineno):
        """解引号串里的转义。单引号只有 '' → '；双引号按 YAML 转义表。"""
        if quote == "'":
            return body.replace("''", "'")
        out, k = [], 0
        while k < len(body):
            ch = body[k]
            if ch != "\\":
                out.append(ch)
                k += 1
                continue
            k += 1
            if k >= len(body):
                self.err(lineno, "双引号串以单个反斜杠结尾")
            e = body[k]
            k += 1
            if e in _DQ_ESCAPES:
                out.append(_DQ_ESCAPES[e])
            elif e in ("x", "u", "U"):
                # \xNN（2 位）/ \uNNNN（4 位）/ \UNNNNNNNN（8 位）
                # allow_unicode=False 的 dump 会用 \x 表示 Latin-1 范围的字符
                width = {"x": 2, "u": 4, "U": 8}[e]
                hexs = body[k:k + width]
                if len(hexs) < width or not re.match(r"^[0-9a-fA-F]{%d}$" % width, hexs):
                    self.err(lineno, "\\%s 转义后面不是 %d 位十六进制" % (e, width))
                out.append(chr(int(hexs, 16)))
                k += width
            else:
                self.err(lineno, "内置解析器不认识的转义 \\%s" % e)
        return "".join(out)

    # ---- 标量：单行

    def _scalar(self, s, lineno):
        s = s.strip()
        if s == "":
            self.err(lineno, "空标量（只有冒号没有值，也不是嵌套块）")
        if s.startswith('"'):
            return self._dquoted(s, lineno)
        if s.startswith("'"):
            return self._squoted(s, lineno)
        if s[:1] in ("{", "&", "*", "!"):
            self.err(lineno, "内置解析器不支持这个构造：%r" % s[:40])
        if s[:1] in ("[",):
            self.err(lineno, "内置解析器不支持作为标量出现的 [（行内列表只允许写在 '键: [...]' 位置）：%r"
                     % s[:40])
        if s in ("null", "Null", "NULL", "~"):
            return None
        if s in ("true", "True", "TRUE"):
            return True
        if s in ("false", "False", "FALSE"):
            return False
        # 这两条是刻意报错而不是猜：YAML 在这里的语义和「看上去」不一样，
        # 静默按其中一种读都会让体检依据悄悄变味。
        if ": " in s or s.endswith(":"):
            self.err(lineno, "未加引号的标量里出现 ': '，YAML 会读成映射键值对，"
                             "语义有歧义 —— 请给这个串加双引号：%r" % s[:60])
        if " #" in s:
            self.err(lineno, "未加引号的标量里出现 ' #'，YAML 会把后面当注释截掉 —— "
                             "请给这个串加双引号：%r" % s[:60])
        if _INT_RE.match(s):
            return int(s)
        if _FLOAT_RE.match(s):
            return float(s)
        return s

    def _dquoted(self, s, lineno):
        k = self._find_close(s, 1, '"', lineno)
        if k is None:
            self.err(lineno, "双引号串在本行没有闭合，而这里（行内列表内 / 行内位置）"
                             "不允许跨行引号串：%r" % s[:60])
        if s[k + 1:].strip() != "":
            self.err(lineno, "双引号串后面还有多余内容：%r" % s[:60])
        return self._unescape(s[1:k], '"', lineno)

    def _squoted(self, s, lineno):
        k = self._find_close(s, 1, "'", lineno)
        if k is None:
            self.err(lineno, "单引号串在本行没有闭合，而这里（行内列表内 / 行内位置）"
                             "不允许跨行引号串：%r" % s[:60])
        if s[k + 1:].strip() != "":
            self.err(lineno, "单引号串后面还有多余内容：%r" % s[:60])
        return self._unescape(s[1:k], "'", lineno)


def parse_yaml_subset(text):
    """内置解析器入口：只覆盖本表用到的子集，超出即报错（不静默当空）。"""
    return _YamlSubsetParser(text).parse()


def _load_pyyaml():
    """尝试拿到可用的 PyYAML；没装或装坏了都返回 None（不报错，交给降级路径）。"""
    try:
        import yaml as _y
        if not hasattr(_y, "safe_load"):
            return None
        return _y
    except Exception:
        return None


def _no_yaml_forced(cli_flag):
    """--no-yaml 或环境变量 SKILLS_CHECK_NO_YAML 是否要求强制走内置解析器。"""
    if cli_flag:
        return True
    v = (os.environ.get("SKILLS_CHECK_NO_YAML") or "").strip().lower()
    return v not in ("", "0", "false", "no", "off")


# ---------------------------------------------------------------- 读取

def load_table(path, force_builtin=False):
    """读登记表。返回 (skills 行列表, 解析器名, 解析器说明)。

    两条路径：有 PyYAML 用 PyYAML，没有（或强制）用内置子集解析器。
    两条路径的**解析结果必须一致**（可用 --verify-parsers 逐节点比对），
    下游校验（顶层 skills 列表、id 唯一）对两条路径一视同仁。
    """
    yaml_mod = None if force_builtin else _load_pyyaml()
    with open(path, encoding="utf-8") as f:
        text = f.read()

    if yaml_mod is not None:
        pname, pdetail = "PyYAML", "版本 %s" % getattr(yaml_mod, "__version__", "未知")
        try:
            doc = yaml_mod.safe_load(text)
        except yaml_mod.YAMLError as e:
            # 表本身写坏了要报成「环境错」并给出行号，不许抛裸 traceback
            raise RuntimeError("%s 不是合法 YAML：\n  %s" % (path, str(e).replace("\n", "\n  ")))
    else:
        pname = "内置降级"
        pdetail = "--no-yaml 强制" if force_builtin else "未找到可用的 PyYAML，已自动降级"
        try:
            doc = parse_yaml_subset(text)
        except YamlSubsetError as e:
            raise RuntimeError(
                "%s 用了内置解析器覆盖不到的 YAML 构造（**没有**静默当成空值）：\n  %s\n"
                "  支持的子集见本文件「内置 YAML 子集解析器」一节；"
                "也可以装上 PyYAML 或改回表里的写法。" % (path, str(e).replace("\n", "\n  ")))

    if not isinstance(doc, dict) or not isinstance(doc.get("skills"), list):
        raise RuntimeError("%s 顶层要有 skills: 列表（当前读到 %r，解析器 %s）"
                           % (path, type(doc).__name__, pname))
    rows = doc["skills"]
    ids = [r.get("id") for r in rows]
    dup = sorted({i for i in ids if i and ids.count(i) > 1})
    if dup:
        raise RuntimeError("%s 有重复 id：%s" % (path, "、".join(dup)))
    return rows, pname, pdetail


def _diff_docs(a, b, path, out, limit=40):
    """逐节点比对两棵树，差异写进 out。"""
    if len(out) >= limit:
        return
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b), key=str):
            if k not in a:
                out.append("%s.%s 只有内置有" % (path, k))
            elif k not in b:
                out.append("%s.%s 只有 PyYAML 有" % (path, k))
            else:
                _diff_docs(a[k], b[k], "%s.%s" % (path, k), out, limit)
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            out.append("%s 长度不同：PyYAML %d / 内置 %d" % (path, len(a), len(b)))
        for i, (x, y) in enumerate(zip(a, b)):
            _diff_docs(x, y, "%s[%d]" % (path, i), out, limit)
    elif a != b or type(a) is not type(b):
        out.append("%s 不同：PyYAML %r(%s) / 内置 %r(%s)"
                   % (path, a, type(a).__name__, b, type(b).__name__))


def verify_parsers(path):
    """把两条解析路径的结果逐节点比对（需要 PyYAML 在场才有意义）。"""
    yaml_mod = _load_pyyaml()
    if yaml_mod is None:
        print("--verify-parsers 需要 PyYAML 在场才能比对两条路径；当前只有内置解析器。",
              file=sys.stderr)
        return 2
    with open(path, encoding="utf-8") as f:
        text = f.read()
    a = yaml_mod.safe_load(text)
    b = parse_yaml_subset(text)
    diffs = []
    _diff_docs(a, b, "$", diffs)
    print("两条解析路径比对：%s" % path)
    print("  A 路径 : PyYAML %s" % getattr(yaml_mod, "__version__", "?"))
    print("  B 路径 : 内置子集解析器")
    if not diffs:
        print("  结果   : 完全一致（逐节点相等，类型也一致）")
        return 0
    print("  结果   : %d 处不一致" % len(diffs))
    for d in diffs:
        print("    · %s" % d)
    return 1


def dir_of(row):
    """这条登记在装载位里的**实际目录名**：`dir_name` 优先，没有就回落 `id`。

    为什么要有它：中文触发补丁把 skill 目录改成了中文名（`视频安全审查`），
    但 `id` 要保持英文稳定键（被 depends_on_skills 等引用）。于是「目录名」与
    「登记 id」不再恒等 —— 所有按目录定位的地方都必须走这个函数，
    否则会把中文目录误报成「装了但没登记」，副本比对也会找错源。
    """
    return row.get("dir_name") or row.get("id")


def scan_slot(slot):
    """扫装载位，返回 {目录名: 绝对路径}（只认目录，跳过隐藏项与文件）。"""
    d = home(slot)
    out = {}
    if not os.path.isdir(d):
        return out
    for name in sorted(os.listdir(d)):
        if name.startswith("."):
            continue
        p = os.path.join(d, name)
        if os.path.isdir(p):
            out[name] = p
    return out


def walk_files(root):
    """递归列出相对路径（不含目录），跳过 .DS_Store 之类噪声。"""
    out = set()
    for base, dirs, files in os.walk(root):
        dirs[:] = [x for x in dirs if not x.startswith(".")]
        for fn in files:
            if fn in (".DS_Store",):
                continue
            out.add(os.path.relpath(os.path.join(base, fn), root))
    return out


def cmp_bytes(a, b):
    try:
        with open(a, "rb") as fa, open(b, "rb") as fb:
            return fa.read() == fb.read()
    except OSError:
        return False


def fm_field(text, key):
    """从 SKILL.md 的 frontmatter 里取一个标量字段（够用就好，不引 yaml）。"""
    m = re.match(r"^---\s*\n(.*?)\n---\s*(?:\n|$)", text, re.S)
    if not m:
        return None
    fm = m.group(1)
    mm = re.search(r"^%s\s*:\s*(.+?)\s*$" % re.escape(key), fm, re.M)
    if not mm:
        return None
    return mm.group(1).strip().strip('"').strip("'")


def ver_tuple(s):
    if not s:
        return None
    nums = re.findall(r"\d+", str(s))
    return tuple(int(x) for x in nums[:4]) if nums else None


# ---------------------------------------------------------------- lark 官方基准

def lark_cli_versions(cli):
    """lark-cli skills list → {name: version}；拿不到就返回 None（不算错误，只标注跳过）。"""
    if not os.path.exists(cli):
        return None
    try:
        p = subprocess.run([cli, "skills", "list"], capture_output=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    if p.returncode != 0:
        return None
    try:
        doc = json.loads(p.stdout.decode("utf-8", "replace"))
    except ValueError:
        return None
    if not doc.get("ok"):
        return None
    return {s.get("name"): s.get("version") for s in doc.get("skills", []) if s.get("name")}


def lark_cli_read(cli, name):
    """lark-cli skills read <name> → SKILL.md 原文；失败返回 None。"""
    try:
        p = subprocess.run([cli, "skills", "read", name], capture_output=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    return p.stdout if p.returncode == 0 and p.stdout else None


# ---------------------------------------------------------------- 主流程

def main(argv=None):
    ap = argparse.ArgumentParser(
        description="skills.yaml 自检：应装未装 / 装了没登记 / 副本不一致 / 依赖缺失 / 自测缺失")
    ap.add_argument("--kb-root", default=None, help="库根（含 KB-ROOT.json 的那一层）")
    ap.add_argument("--table", default=None, help="skills.yaml 路径（缺省按库根推）")
    ap.add_argument("--slot", default=INSTALL_SLOT, help="装载位，缺省 %s" % INSTALL_SLOT)
    ap.add_argument("--no-yaml", action="store_true",
                    help="强制走内置 YAML 子集解析器（不 import PyYAML），用于验证降级路径")
    ap.add_argument("--verify-parsers", action="store_true",
                    help="把 PyYAML 与内置解析器的解析结果逐节点比对（需要 PyYAML 在场）")
    ap.add_argument("--json", action="store_true", help="额外输出机器可读汇总")
    ap.add_argument("--quiet", action="store_true", help="只输出汇总")
    args = ap.parse_args(argv)

    try:
        root = find_root(os.path.dirname(os.path.abspath(__file__)), args.kb_root)
    except RuntimeError as e:
        print("环境错：%s" % e, file=sys.stderr)
        return 2

    table_path = args.table or os.path.join(root, *TABLE_REL)

    if args.verify_parsers:
        try:
            return verify_parsers(table_path)
        except OSError as e:
            print("环境错：%s" % e, file=sys.stderr)
            return 2

    try:
        rows, parser_name, parser_detail = load_table(
            table_path, force_builtin=_no_yaml_forced(args.no_yaml))
    except (RuntimeError, OSError) as e:
        print("环境错：%s" % e, file=sys.stderr)
        return 2

    installed = scan_slot(args.slot)
    slot_disp = home(args.slot)
    cli = home(LARK_CLI)

    P = {"1": [], "2": [], "3": [], "4": [], "5": []}   # 问题（计入退出码）
    I = {"selftest_未登记": [], "备注": [], "预期未装": []}   # 信息（不计入退出码）

    by_id = {r.get("id"): r for r in rows}
    by_dir = {dir_of(r): r for r in rows}     # 目录名 → 行（dir_name 优先）

    # ---- 1. 应装未装：scope=本项目 且 status=生产
    # 只有「已登记为生产」却没装才算问题；候选 / 规划 本阶段只登记不安装，
    # 单列为「预期未装」（要看得见下一步该装什么，但不能算错误、不能把退出码顶成非 0）。
    for r in rows:
        if r.get("scope") != SCOPE_PROJECT:
            continue
        if r.get("status") == STATUS_PRODUCTION:
            if dir_of(r) not in installed:
                P["1"].append("%s（层 %s）" % (r["id"], r.get("layer")))
        elif r.get("status") in ("候选", "规划") and dir_of(r) not in installed:
            I["预期未装"].append("%s（%s · 层 %s）" % (r["id"], r.get("status"), r.get("layer")))

    # ---- 2. 装了但没登记
    for name in sorted(installed):
        if name not in by_dir:
            P["2"].append("%s（装了但表里没有这一行）" % name)
    for name in sorted(installed):
        r = by_dir.get(name)
        if r and r.get("status") == STATUS_REFERENCE:
            P["2"].append("%s（status=参考 却被装进装载位，违反「参考项一律不安装」）" % name)

    # ---- 3. 副本不一致
    skipped = []   # 登记了 source 但尚未安装 → 只能跳过，不算问题（应装未装由第 1 类管）
    linked = []    # 装机位是**指向真源的符号链接** → 本项对其**不适用**（2026-10-05 加）
    lark_versions = lark_cli_versions(cli) if os.path.exists(cli) else None
    if lark_versions is None:
        I["备注"].append("lark 官方基准不可用（%s 调不到 skills list）——lark 副本只做逐文件 cmp，"
                         "未做「是否落后于 CLI 版本」校验" % LARK_CLI)
    for r in rows:
        src = r.get("source")
        if not src:
            continue
        sid = r["id"]
        src_abs = home(src) if src.startswith(("~", "/")) else os.path.join(root, src)
        dst = installed.get(dir_of(r))
        if dst is None:
            skipped.append("%s（%s）" % (sid, r.get("status")))
            continue
        if not os.path.isdir(src_abs):
            P["3"].append("%s：源目录不存在 %s" % (sid, src_abs))
            continue
        # ★ 2026-10-05：装机位改成指向真源的**符号链接**后，下面这段逐文件比对
        #   变成「拿真源比真源」—— 恒等，且**结构上不可能不一致**。
        #   ⇒ 它不是"通过"，是**不适用**。不许让它冒充"副本一致"：
        #     那会让这道闸门在最该有判别力的地方保持沉默（假绿的一种）。
        #   改为**显式记账**——列出来，由人一眼看见"这几件已经不靠比对兜底了"。
        #   （配套护栏在 kb/l8/watch_review_readiness.py 的 check_skill_links：
        #     链接**断裂**时加载器会静默跳过该 skill，那才是新的失效点。）
        if os.path.islink(dst):
            linked.append("%s → %s" % (sid, os.readlink(dst)))
            continue
        sf, df = walk_files(src_abs), walk_files(dst)
        diffs = []
        for rel in sorted(sf):
            d = os.path.join(dst, rel)
            if rel not in df:
                diffs.append("缺 %s" % rel)
            elif not cmp_bytes(os.path.join(src_abs, rel), d):
                diffs.append("异 %s" % rel)
        for rel in sorted(df - sf):
            diffs.append("多 %s" % rel)
        if diffs:
            head = diffs[:MAX_LISTED]
            more = "" if len(diffs) <= MAX_LISTED else "（另有 %d 项未列）" % (len(diffs) - MAX_LISTED)
            P["3"].append("%s：与源 %s 不一致，%d 个文件：%s%s"
                          % (sid, src, len(diffs), "；".join(head), more))
    if linked:
        I["备注"].append(
            "本项对 %d 件**不适用**：装机位是**指向真源的符号链接**（逐文件比对会变成「拿真源比真源」，"
            "恒等、结构上不可能不一致）⇒ 这几件不靠本项兜底，改由链接解析来保证：%s"
            % (len(linked), "、".join(x.split(" → ")[0] for x in linked)))
        I.setdefault("链接装载位", []).extend(linked)

    # ---- 3b. lark：官方基准（落后于 CLI 版本）
    for r in rows:
        sid = r["id"]
        if not sid.startswith("lark-") or dir_of(r) not in installed:
            continue
        if lark_versions is None:
            continue
        if sid not in lark_versions:
            P["3"].append("%s：已装但 lark-cli 里没有这个 skill（CLI 侧已移除或改名）" % sid)
            continue
        skill_md = os.path.join(installed[dir_of(r)], "SKILL.md")
        if not os.path.isfile(skill_md):
            P["3"].append("%s：装了但没有 SKILL.md" % sid)
            continue
        with open(skill_md, encoding="utf-8", errors="replace") as f:
            local_text = f.read()
        local_v = ver_tuple(fm_field(local_text, "version"))
        cli_v = ver_tuple(lark_versions.get(sid))
        cli_bytes = lark_cli_read(cli, sid)
        content_diff = cli_bytes is not None and cli_bytes != local_text.encode("utf-8")
        if cli_v and local_v and local_v < cli_v:
            P["3"].append("%s：副本落后于 CLI 版本（本地 %s < CLI %s）——按 lark-cli skills read %s 同步"
                          % (sid, ".".join(map(str, local_v)), ".".join(map(str, cli_v)), sid))
        elif content_diff and not (local_v and cli_v and local_v > cli_v):
            P["3"].append("%s：SKILL.md 与 lark-cli skills read 的输出不一致（版本号未体现差异）" % sid)
        elif content_diff:
            I["备注"].append("3 备注：%s 与 CLI 输出不一致，但本地版本 %s 高于 CLI %s（属超前，不告警）"
                             % (sid, ".".join(map(str, local_v)), ".".join(map(str, cli_v))))

    if skipped:
        head = "、".join(skipped[:8])
        tail = "" if len(skipped) <= 8 else "…（共 %d 个）" % len(skipped)
        I["备注"].append(
            "3 跳过：%d 个登记了 source 的条目尚未安装，未做副本比对：%s%s"
            % (len(skipped), head, tail))

    # ---- 4. 依赖缺失
    for r in rows:
        deps = r.get("depends_on_engine")
        if isinstance(deps, list):
            for dep in deps:
                p = dep if dep.startswith(("~", "/")) else os.path.join(root, dep)
                if not os.path.exists(p):
                    P["4"].append("%s：depends_on_engine 缺 %s" % (r["id"], dep))
        elif deps not in (None, []):
            P["4"].append("%s：depends_on_engine 应是列表或 null，当前是 %r" % (r["id"], deps))
        sdeps = r.get("depends_on_skills")
        if isinstance(sdeps, list):
            for dep in sdeps:
                if dep not in by_id:
                    P["4"].append("%s：depends_on_skills 里的 %s 不在登记表中" % (r["id"], dep))

    # ---- 5. 自测缺失
    for r in rows:
        st = r.get("selftest")
        if st in (None, ""):
            I["selftest_未登记"].append(r["id"])
            continue
        p = st if st.startswith(("~", "/")) else os.path.join(root, st)
        if not os.path.exists(p):
            P["5"].append("%s：selftest 路径不存在 %s" % (r["id"], st))

    # ---------------------------------------------------------------- 输出
    total_problems = sum(len(v) for v in P.values())
    counts = {k: len(v) for k, v in P.items()}

    # --json 时人读汇总改走 stderr，stdout 只留纯 JSON（便于 jq / 程序消费）
    _real_stdout = sys.stdout
    if args.json:
        sys.stdout = sys.stderr

    if not args.quiet:
        print("=" * 68)
        print("skills_check —— DSH 宿主 skill 登记表自检")
        print("=" * 68)
        print("库根    : %s" % root)
        print("登记表  : %s" % os.path.relpath(table_path, root))
        print("解析器  : %s（%s）" % (parser_name, parser_detail))
        print("  行数  : %d（本项目 %d / 宿主通用 %d）"
              % (len(rows),
                 sum(1 for r in rows if r.get("scope") == SCOPE_PROJECT),
                 sum(1 for r in rows if r.get("scope") != SCOPE_PROJECT)))
        print("装载位  : %s" % slot_disp)
        print("  扫到  : %d 个目录" % len(installed))
        print("另一装载位: %s（本项目不装这里，仅作对照）" % home(OTHER_SLOT))
        print("lark 基准: %s%s"
              % (LARK_CLI, "" if lark_versions is not None else "（不可用，跳过版本比对）"))
        print()

        titles = {
            "1": "1. 应装未装（scope=本项目 且 status=生产，但装载位里没有）",
            "2": "2. 装了但没登记（装载位里有目录，表里没有对应 id）",
            "3": "3. 副本不一致（source 非 null 的逐文件 cmp；lark-* 另比官方基准；符号链接装载位不适用，见备注）",
            "4": "4. 依赖缺失（depends_on_engine 路径在库内不存在）",
            "5": "5. 自测缺失（selftest 路径不存在）",
        }
        for k in "12345":
            items = P[k]
            print("--- %s --- %d 条" % (titles[k], len(items)))
            for line in items[:MAX_LISTED]:
                print("    · %s" % line)
            if len(items) > MAX_LISTED:
                print("    … 另有 %d 条未列" % (len(items) - MAX_LISTED))
            if k == "1":
                # 1b 单列：候选 / 规划 未装是**预期结果**，不计入问题与退出码，
                # 但必须列出来 —— 「下一步该装什么」的答案就在这里。
                exp = I["预期未装"]
                print("--- 1b. 预期未装（scope=本项目 且 status=候选/规划，本阶段只登记不安装）"
                      "--- %d 条【不算错误】" % len(exp))
                for line in exp[:MAX_LISTED]:
                    print("    · %s" % line)
                if len(exp) > MAX_LISTED:
                    print("    … 另有 %d 条未列" % (len(exp) - MAX_LISTED))
            print()

        print("--- 未登记 selftest（单独归类，不算错误）--- %d 条" % len(I["selftest_未登记"]))
        if I["selftest_未登记"]:
            print("    " + "、".join(I["selftest_未登记"][:MAX_LISTED]))
        print()
        if I["备注"]:
            print("--- 备注 ---")
            for line in I["备注"][:MAX_LISTED]:
                print("    · %s" % line)
            if len(I["备注"]) > MAX_LISTED:
                print("    … 另有 %d 条未列" % (len(I["备注"]) - MAX_LISTED))
            print()

    # ---- 汇总：本项目一共要用多少、已装几个、还差几个、差在哪一层
    proj = [r for r in rows if r.get("scope") == SCOPE_PROJECT]
    use = [r for r in proj if r.get("status") in (STATUS_PRODUCTION, "候选", "规划")]
    cat = [r for r in proj if r.get("status") == "候选"]
    plan = [r for r in proj if r.get("status") == "规划"]
    ref = [r for r in proj if r.get("status") == STATUS_REFERENCE]
    prod = [r for r in proj if r.get("status") == STATUS_PRODUCTION]
    installed_prod = [r for r in prod if dir_of(r) in installed]
    missing = [r for r in use if dir_of(r) not in installed]

    def layer_hist(rs):
        h = {}
        for r in rs:
            h[r.get("layer")] = h.get(r.get("layer"), 0) + 1
        return "、".join("%s %d 个" % (k, v) for k, v in sorted(h.items(), key=lambda x: str(x[0])))

    print("=" * 68)
    print("汇总")
    print("=" * 68)
    print("本项目要用：%d 个（生产 %d + 候选 %d + 规划 %d）"
          % (len(use), len(prod), len(cat), len(plan)))
    print("  已装    ：%d 个" % len(installed_prod))
    print("  还差    ：%d 个（候选 %d + 规划 %d）"
          % (len(missing), len([r for r in missing if r.get("status") == "候选"]),
             len([r for r in missing if r.get("status") == "规划"])))
    if missing:
        print("  差在哪层：%s" % layer_hist(missing))
    print("另：status=参考 %d 个（只参考 / 只收编，一律不安装、不复制）" % len(ref))
    print("    宿主通用 %d 个（登记归属，不参与「应装未装」判定）"
          % sum(1 for r in rows if r.get("scope") != SCOPE_PROJECT))
    print()
    print("五类问题：1=%d 2=%d 3=%d 4=%d 5=%d ｜合计 %d"
          % (counts["1"], counts["2"], counts["3"], counts["4"], counts["5"], total_problems))
    if not total_problems:
        print("结论：全过。")
    else:
        print("结论：有问题，退出码 1。第 1 类若列出「已登记为生产但未装」的项，"
              "下一步就是把这些装到 %s。" % INSTALL_SLOT)
    print("退出码：%d" % (1 if total_problems else 0))

    if args.json:
        sys.stdout = _real_stdout
        print(json.dumps({
            "kb_root": root,
            "table": os.path.relpath(table_path, root),
            "parser": parser_name,
            "parser_detail": parser_detail,
            "rows": len(rows),
            "scan_count": len(installed),
            "problems": {k: v for k, v in P.items()},
            "problem_counts": counts,
            "expected_missing_1b": I["预期未装"],
            "selftest_unregistered": I["selftest_未登记"],
            "notes": I["备注"],
            "use_total": len(use), "installed": len(installed_prod),
            "missing_total": len(missing),
            "missing_by_layer": {k: sum(1 for r in missing if r.get("layer") == k)
                                 for k in sorted({r.get("layer") for r in missing}, key=str)},
            "exit_code": 1 if total_problems else 0,
        }, ensure_ascii=False, indent=1))

    return 1 if total_problems else 0


if __name__ == "__main__":
    sys.exit(main())
