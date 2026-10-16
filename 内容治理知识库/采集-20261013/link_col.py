#!/usr/bin/env python3
"""链接列的名字**不许写死** —— 按 `/报告链接/` 认列（Owner 2026-10-16 的改名同步）。

背景（Owner 原话）：「我会把云文档中 **10/14重跑报告链接**，字段替换成 **报告链接**，
这是同一个字段，同步下你」。

⇒ 本项目里凡是按列名取链接的脚本，都从这儿取候选名，两个名字**都认**：
  · 改名**之后**：`报告链接` 命中；
  · 改名**之前**：`10/14重跑报告链接` 命中（正则也匹配 `报告链接`，所以顺序反过来也行）。

为什么值得单独一个文件：这一列的名字**已经坑过两次** ——
  ① 批跑器里把判据写成 `name === '报告链接'`（写死），而表里叫 `10/14重跑报告链接`
     ⇒ 那个"转成超链接"的分支**从来没执行**，写进去的是黑字纯文本（Owner 2026-10-16 报的那 7 格）；
  ② 回填字段名同样写死 ⇒ 那一列**从来没人写**，80 行的链接全靠人手补。
两次都是"同一个东西、两个名字、各写一份判据" ⇒ 现在**只有这一份**。

用法：
    from link_col import LINK_COL_CANDIDATES, pick_link, resolve_from_fields
    link = pick_link(row)                       # row = 一行记录（dict）
    name = resolve_from_fields(fields)          # fields = lark-cli +field-list 的字段名列表
"""
import re

#: 顺序即优先级：新名字在前，旧名字兜底。
LINK_COL_CANDIDATES = ('报告链接', '10/14重跑报告链接')

#: 认列的**判据**（唯一）：名字里含「报告链接」。改名/加前缀都不怕。
LINK_COL_RE = re.compile(r'报告链接')


def _plain(v):
    if v is None:
        return ''
    if isinstance(v, str):
        return v
    if isinstance(v, list):
        return ''.join(_plain(x) for x in v)
    if isinstance(v, dict):
        return str(v.get('link') or v.get('text') or '')
    return str(v)


def pick_link(row):
    """从一行记录里取链接格的文本（两个名字都试；都没有 → 空串）。"""
    for k in LINK_COL_CANDIDATES:
        v = _plain((row or {}).get(k))
        if v:
            return v
    # 兜底：按正则在这一行里找列名（改名成「报告链接(新)」这类也能认出来）
    for k, v in (row or {}).items():
        if LINK_COL_RE.search(str(k)) and _plain(v):
            return _plain(v)
    return ''


def resolve_from_fields(field_names):
    """从**表里真实存在的字段名清单**里认列名；认不出返回 None（不许猜一个写下去）。"""
    names = [str(x) for x in (field_names or [])]
    for k in LINK_COL_CANDIDATES:
        if k in names:
            return k
    for n in names:
        if LINK_COL_RE.search(n):
            return n
    return None


def selftest():
    """反向对照：改名前后都要认得出；认不出时**必须返回 None/空串**，不许猜。"""
    cases = [
        ('改名后（报告链接）', {'报告链接': 'https://x/docx/A'}, 'https://x/docx/A'),
        ('改名前的旧名', {'10/14重跑报告链接': 'https://x/docx/B'}, 'https://x/docx/B'),
        ('两个都在 ⇒ 取新的', {'报告链接': 'NEW', '10/14重跑报告链接': 'OLD'}, 'NEW'),
        ('都没有 ⇒ 空串（不许猜）', {'Agent 结论': 'PASS'}, ''),
    ]
    bad = 0
    for name, row, want in cases:
        got = pick_link(row)
        good = (got == want)
        bad += 0 if good else 1
        print(f"  {'✅' if good else '✗'} {name} ⇒ {got!r}")
    for name, names, want in [
        ('字段清单里只有新名', ['内容 ID', '报告链接'], '报告链接'),
        ('字段清单里只有旧名', ['内容 ID', '10/14重跑报告链接'], '10/14重跑报告链接'),
        ('字段清单里带后缀', ['内容 ID', '报告链接(重跑)'], '报告链接(重跑)'),
        ('字段清单里没有 ⇒ None', ['内容 ID', '状态'], None),
    ]:
        got = resolve_from_fields(names)
        good = (got == want)
        bad += 0 if good else 1
        print(f"  {'✅' if good else '✗'} {name} ⇒ {got!r}")
    print('selftest ' + ('全绿' if bad == 0 else f'{bad} 项红'))
    return 0 if bad == 0 else 1


if __name__ == '__main__':
    import sys
    raise SystemExit(selftest() if '--selftest' in sys.argv else selftest())
