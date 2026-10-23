#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""补丁（Owner 2026-09-21「审查报告中不能出现后台语言」）：

三处后台语言，全部在 `kb/l5/p0_fastpath.py`：

  ① **`quote` 印的是正则源码**（`最\\s*(安全|低价|…)`、`(?:\\bno\\.?\\s*1|#`），
     位置写「逐字命中」而印出来的是正则 —— 那不是逐字，业务侧也读不懂。
     数据里本来就有真命中文字（`matched[].text`，2026-10-21 匹配器加的），只是没被搬过来。
  ② **「原因」= L3 的 `reason`**，那一格逐字是 `H05 虚假安全承诺（best/#1/No.1/…
     按2026-09-09口径放开…不再判险）` —— 带规则码、带口径说明，还会自相矛盾。
     这里只做**去壳**：去规则码前缀、去括号里的口径说明；**判定理由一个字不改**。
  ③ **「建议」末尾挂库内路径**：`（本码共 12 组修订建议，此处按首组给出；全量见
     kb/l3/candidates/rules.jsonl#W-1.33）` —— 「本码」「kb/…jsonl#」都是内部坐标。
     改成指向「依据」那一格里的条款（那里是可点的飞书直链）。
     全量内容**一个字符没丢**（仍在条款里），只是不再把内部路径印给人看。
"""
import io
import os
import shutil

ROOTS = [
    ("repo", "/Users/lute/project/audit_multi_content/内容治理知识库"),
    ("live", os.path.expanduser(
        "~/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理")),
]
BACKUP = "/Users/lute/project/audit_multi_content/test/_fix/backup_relax"

HELPERS = '''# ══════════════════════════════════════════════════════════════════════════
# 2026-09-21（Owner：「审查报告中不能出现后台语言」）
# ══════════════════════════════════════════════════════════════════════════
# 三样东西**不许**上报告：正则源码、规则码（H05/M07…）、库内相对路径（kb/…）。
# 判断只认形状，不改判定：命中的是哪个词、理由是什么，都是原样。
_RELAX_NOTE_RE = re.compile(r"[（(][^）)]*(?:放开|不再判险|允许)[^）)]*[）)]")
_RULE_CODE_HEAD_RE = re.compile(r"^\\s*[A-Z]\\d{2}\\s*[:：]?\\s*")


def _hit_text(m, limit=40):
    """命中的**真实文字**（不是正则源码）。

    `matched[]` 里两格：`pattern` 是**规则侧写法**（正则命中时就是一整条正则），
    `text` 是**真正被命中的那段字**（匹配器的 `m.group(0)`）。
    报告写「逐字命中」⇒ 只能用 `text`；取不到才退回 `pattern`（老收据没有 `text`）。
    """
    m = m or {}
    t = str(m.get("text") or "").strip() or str(m.get("pattern") or "").strip()
    t = t.replace("`", "")
    return (t[:limit] + "…") if len(t) > limit else t


def _business_reason(text, code=None):
    """「原因」的业务版：去规则码前缀、去括号里的口径说明，**判定理由一个字不改**。

    实测那种自相矛盾的印法（2026-09-21 报告 F-02）：
        `H05 虚假安全承诺（best/#1/No.1/最佳/最好等排名最高级按2026-09-09口径放开，
         海外广告允许，不再判险）`
    —— 把「已放开」的口径原样印在一条 P0 的「原因」里，读者只能读出矛盾。
    """
    s = str(text or "").strip()
    if not s:
        return "（来源未给判定理由）"
    s = _RULE_CODE_HEAD_RE.sub("", s)
    s = _RELAX_NOTE_RE.sub("", s).strip()
    s = re.sub(r"\\s{2,}", " ", s).strip(" ；;，,、")
    return s or "（来源未给判定理由）"


'''

OLD_QUOTE = '            "quote": "、".join("`%s`" % m.get("pattern") for m in (f.get("matched") or [])[:6]) or "—",'
NEW_QUOTE = ('            # ★★ 2026-09-21（Owner：报告里不许出现后台语言）：原先印的是 `pattern`\n'
             '            #   —— 正则命中时那是一条**正则源码**，却被写成「逐字命中」。改成真命中文字。\n'
             '            "quote": "、".join(_hit_text(m) for m in (f.get("matched") or [])[:6]) or "—",')
OLD_REASON = '            "reason": rule.get("reason") or "（来源未给判定理由）",'
NEW_REASON = ('            # ★★ 2026-09-21：去规则码前缀与括号里的口径说明（见 `_business_reason`）。\n'
              '            "reason": _business_reason(rule.get("reason"), f.get("rule_code")),')
OLD_TAIL = ('    how = "按首组给出" if first else "按命中片段给出"\n'
            '    return "%s（本码共 %d 组修订建议，此处%s；全量见 kb/l3/candidates/rules.jsonl#%s）" % (\n'
            '        fix, len(pairs), how, article_no or "（无条款号）")')
NEW_TAIL = ('    # ★★ 2026-09-21（Owner：「审查报告中不能出现后台语言」）：改前这一句是\n'
            '    #   `（本码共 12 组修订建议，此处按首组给出；全量见 kb/l3/candidates/rules.jsonl#W-1.33）`\n'
            '    #   —— 「本码」「kb/l3/…jsonl#」是库内坐标，业务侧读不懂也点不开。\n'
            '    #   全量**一个字符没丢**：它就在「依据」那一格指向的条款里（可点飞书直链）。\n'
            '    return "%s（这条条款下另有 %d 组改法，本次按%s给出；全量见「依据」里的条款）" % (\n'
            '        fix, len(pairs), "首组" if first else "命中片段")')


def patch(path):
    os.makedirs(BACKUP, exist_ok=True)
    shutil.copy2(path, os.path.join(BACKUP, "p0_fastpath__" + os.path.basename(
        os.path.dirname(os.path.dirname(os.path.dirname(path)))) + ".py"))
    s = io.open(path, encoding="utf-8").read()
    assert "_hit_text" not in s, "已经打过这个补丁：%s" % path
    for old, new, what in ((OLD_QUOTE, NEW_QUOTE, "quote"), (OLD_REASON, NEW_REASON, "reason"),
                           (OLD_TAIL, NEW_TAIL, "suggestion tail")):
        assert s.count(old) == 1, "锚点不唯一（%d 处）：%s" % (s.count(old), what)
        s = s.replace(old, new)
    # 助手函数插在第一个 `def ` 之前（模块顶部常量之后），保证解析期就有
    anchor = "def _load_matcher"
    assert s.count(anchor) == 1, "锚点不唯一：_load_matcher"
    s = s.replace(anchor, HELPERS + anchor)
    # `re` 必须在助手函数之前 import（本文件已 import re，这里只断言）
    assert "\nimport" in s and "re" in s.split("\n")[0:80].__str__()
    io.open(path, "w", encoding="utf-8").write(s)
    return path


for label, root in ROOTS:
    p = os.path.join(root, "kb/l5/p0_fastpath.py")
    patch(p)
    print("[%s] 已打 p0_fastpath 补丁：%s" % (label, p))
