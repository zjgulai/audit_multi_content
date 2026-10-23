#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""补丁（承 `patch_relax_rank.py`）：把「裁定 A」落到**生成器**里，重建不再回填。

为什么必须改生成器（本项目的老病）
----------------------------------
`p0_patterns.jsonl` 是**导出物**，由 `kb/.work/l5_export.py` 从 L3 规则生成。
只改表不改生成器 ⇒ 下次 `--apply` 会把出列的词/正则**静默补回来**
（10-19 那次「最佳/最好出列」已经把这条踩明白了：必须走导出处的机制）。

本补丁加的是一张**显式裁定表**，与 10-19 的 `exclude` 同构，但管得更宽：
  · RELAXED_TERMS —— 字面词：出列
  · RELAXED_REGEX —— 正则：drop 直接出列，replace 换成收窄后的写法
  · 边界表述里写着「放开 / 不再判险」的，一律不进触发词（它是口径说明，不是规则名）
每次出列都写进 `variant_sources.relaxed_by_ruling` —— 可核、不静默。
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

CONST_BLOCK = r'''# ============================================================================
# 2026-09-21（Owner 裁定 A）：排名/最高级一族退出 P0
# ============================================================================
# Owner 原话：「虚假安全承诺（best/#1/No.1/最佳/最好等排名最高级按2026-09-09口径放开，
#   海外广告允许，不再判险）==》既然放开了，为什么还写出来问题？」
# 裁定：best / #1 / No.1 / 最佳 / 最好 / 最高级 不再判险、不进问题清单；
#   「第一 / 销量第一」这类中文事实性排名也不阻断，只留一句「需补可核验依据」的非阻断提示
#   （提示在 kb/l5/p0_fastpath.py 的 RANK_ADVISORY_RX）。
#
# 为什么需要这张表（三处来路，都实测过）：
#   1) 10-19 那次「最佳/最好出列」只过滤 literal/synonym（exclude 机制），正则没出列
#      => H05 的 (?:\bno\.?\s*1|#\s*1)\b、最(...|高|...) 照旧命中；
#   2) 10-21 把规则自己的边界表述（含「...放开，不再判险」这句）逐字灌进了 patterns
#      => 说明「已放开」的句子成了「它没放开」的证据；
#   3) V02/V03 另有 最佳/最好/第一/#1 的独立词条 => 同一条被三条规则各报一次。
#
# 代价（明写）：PRD §7.3 第 3 条把「最、第一、最佳…」列为绝对化用语 P0（10-09 据此作废过
#   09-09 的放开）。本轮 Owner 把口径收窄到排名/最高级一族；100% / 纯天然 / 最安全
#   仍在 P0，一个字没松。数量类宣称（销量 100 万台 / sold 6 million）仍在 V03。
RELAXED_RULING = "owner-2026-09-21-A（排名/最高级一族退出 P0；中文事实性排名降为非阻断提示）"
RELAXED_TERMS = {
    "H05": ["虚假安全承诺（best/#1/No.1/最佳/最好等排名最高级按2026-09-09口径放开，"
            "海外广告允许，不再判险）"],
    "V02": ["最佳", "最好", "第一"],
    "V03": ["排名第一", "销量第一", "销量领先"],
}
RELAXED_REGEX = {
    "H05": {
        "drop": [r"(?:\bno\.?\s*1|#\s*1)\b",
                 r"(排名|销量|全网|行业|品类|国内|全球|世界|亚洲)\s*第一",
                 r"第一\s*(品牌|选择|名|款|位)",
                 r"最佳", r"\bbest\b"],
        "replace": {
            r"最\s*(佳|优|强|安全|低价|便宜|有效|快|大|高|省|舒适)":
                r"最\s*(优|强|安全|低价|便宜|有效|快|大|省|舒适)",
            r"最\s*(安全|低价|便宜|有效|快|大|高|省)":
                r"最\s*(安全|低价|便宜|有效|快|大|省)",
        },
    },
    "V03": {
        "drop": [r"(?:\bno\.?\s*1\b|\B#\s*1\b|\bnumber\s*one\b)",
                 r"(?:销量|销售|出货|售出|累计|全美|全球|全国|全网|美国|北美)[^。，,；;]{0,8}(?:第一|冠军|领先|no\.?\s*1|#\s*1)",
                 r"(?:第一|冠军|榜首)[^。，,；;]{0,6}(?:销量|品牌|排名|名)",
                 r"\b(?:best[- ]?selling|top[- ]?seller|number[- ]one)\b"],
        "replace": {},
    },
}
#: 边界表述里出现这些字样 => 它是口径说明（说「这东西放开了」），不是触发词
RELAXED_BND_RE = r"放开|不再判险"


def _squash(s):
    return "".join(str(s or "").split())


def _sq_set(xs):
    return {_squash(x) for x in xs}
'''

FILTER_BLOCK = (
    "    # 2026-09-21 裁定 A：出列排名/最高级一族（见文件上方 RELAXED_* 常量）\n"
    "    _rel_t = {norm(x) for x in RELAXED_TERMS.get(code) or []}\n"
    "    _rel_dropped = {\"terms\": [], \"regex\": []}\n"
    "    _bnd_relaxed = {b for b in bnd if re.search(RELAXED_BND_RE, b)}\n"
    "    _drop_terms = set(_rel_t) | _bnd_relaxed\n"
    "    if _drop_terms:\n"
    "        _hit_t = [t for t in (list(lit) + list(syn)\n"
    "                              + [m[\"term\"] for m in match_terms] + list(bnd))\n"
    "                  if t in _drop_terms]\n"
    "        _rel_dropped[\"terms\"] = sorted(set(_hit_t))\n"
    "        lit = [x for x in lit if x not in _drop_terms]\n"
    "        syn = [x for x in syn if x not in _drop_terms]\n"
    "        match_terms = [m for m in match_terms if m[\"term\"] not in _drop_terms]\n"
    "        bnd = [x for x in bnd if x not in _drop_terms]\n"
)

REGEX_FILTER_BLOCK = (
    "    # 2026-09-21 裁定 A：正则出列 / 收窄（同上 RELAXED_REGEX）\n"
    "    _rr = RELAXED_REGEX.get(code) or {}\n"
    "    _drop_rx = _sq_set(_rr.get(\"drop\") or [])\n"
    "    _rep_rx = {_squash(k): v for k, v in (_rr.get(\"replace\") or {}).items()}\n"
    "    _rx_new = []\n"
    "    for _x in rx:\n"
    "        _k = _squash(_x)\n"
    "        if _k in _drop_rx:\n"
    "            _rel_dropped[\"regex\"].append(_x)\n"
    "            continue\n"
    "        if _k in _rep_rx:\n"
    "            _rel_dropped[\"regex\"].append(_x)\n"
    "            _x = _rep_rx[_k]\n"
    "        _rx_new.append(_x)\n"
    "    rx = _rx_new\n"
    "    _relax_note = {\"ruling\": RELAXED_RULING,\n"
    "                   \"removed_terms\": sorted(set(_rel_dropped[\"terms\"])),\n"
    "                   \"removed_regex\": sorted(set(_rel_dropped[\"regex\"]))}\n"
)

VARIANT_ANCHOR = '"dropped_by_ruling": sorted(_excl)},'
VARIANT_NEW = ('"dropped_by_ruling": sorted(_excl),\n'
               '                         # 2026-09-21 裁定 A：出列的排名/最高级一族（可核、不静默）\n'
               '                         "relaxed_by_ruling": _relax_note},')


def patch_export(path):
    os.makedirs(BACKUP, exist_ok=True)
    shutil.copy2(path, os.path.join(
        BACKUP, os.path.basename(os.path.dirname(os.path.dirname(path))) + "__l5_export.py"))
    s = io.open(path, encoding="utf-8").read()
    assert "RELAXED_RULING" not in s, "已经打过这个补丁：%s" % path
    a1 = "# ---------- 生成模式"
    assert s.count(a1) == 1, "锚点不唯一：生成模式"
    s = s.replace(a1, CONST_BLOCK + "\n" + a1)
    a2 = '    plist = [m["term"] for m in match_terms]'
    assert s.count(a2) == 1, "锚点不唯一：plist"
    s = s.replace(a2, FILTER_BLOCK + a2)
    a3 = ('    if code == "V03":\n'
          '        rx = list(rx) + [x for x in SALES_RANK_REGEX if x not in rx]')
    assert s.count(a3) == 1, "锚点不唯一：V03 regex 扩展"
    s = s.replace(a3, a3 + "\n" + REGEX_FILTER_BLOCK)
    if s.count(VARIANT_ANCHOR) == 1:
        s = s.replace(VARIANT_ANCHOR, VARIANT_NEW)
    else:
        # repo 那份没有 10-19 的 `_excl` 机制 —— 挂在 boundary_from_source 后面
        a4 = '                         "dropped_ungrounded": dropped, "boundary_from_source": bnd},'
        assert s.count(a4) == 1, "锚点不唯一：repo 版 variant_sources"
        s = s.replace(a4,
                      '                         "dropped_ungrounded": dropped, "boundary_from_source": bnd,\n'
                      '                         # 2026-09-21 裁定 A：出列的排名/最高级一族（可核、不静默）\n'
                      '                         "relaxed_by_ruling": _relax_note},')
    io.open(path, "w", encoding="utf-8").write(s)
    return path


for label, root in ROOTS:
    p = os.path.join(root, "kb/.work/l5_export.py")
    patch_export(p)
    print("[%s] 已打生成器补丁：%s" % (label, p))
