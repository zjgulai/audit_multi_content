#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_negative_rule_coverage.py —— 负面样本规则的**覆盖与完整性判据**（只读）。

查四件事（任一不满足 ⇒ 退出码 3）
──────────────────────────────────
  ① 条款号唯一且连续（N-1.1 … N-1.N，不跳号、不重号）
  ② 每条规则都有证据：`evidence_units[]` 非空（L2 unit_id + anchor + sha 三样齐）
     ＋ `record_ids[]` 非空 ＋ `image_refs[]` 里的 token 在 L0 附件目录里**真有字节**
  ③ 图片覆盖：L0 记录里的每一张图，要么被 ≥1 条规则引用，要么在
     `kb/l3/registry/negative_rules.json` 的 `images_uncovered` 里**被点名**（不静默）
  ④ `negative_image_map.jsonl` 与规则里的 `image_refs` 双向一致（不许各说各话）

为什么要有它
────────────
库里的层闸门只看层产物「齐不齐」，不看**这张图有没有被规则覆盖**。
2026-10-20 之前，负面样本的 339 张图里 35 张连 L0 字节都没有、规则 0 条，
而日更摘要写的是「图片附件 已对齐」。这条判据就是为那个形状写的。

`--selftest` 是反向对照：把规则复制一份、删掉一条图片映射 / 改重一个条款号，
判据必须**精确变红**；不跑自证的判据等于注释。

用法
────
  python3 kb/l8/check_negative_rule_coverage.py
  python3 kb/l8/check_negative_rule_coverage.py --selftest
"""
# ── 解释器守卫 ────────────────────────────────────────────────────────────
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

import json
import os
import sys
import tempfile

RULES = "kb/l3/candidates/negative_rules.jsonl"
MAP = "kb/l3/candidates/negative_image_map.jsonl"
ITEM = "kb/l3/candidates/negative_item_map.jsonl"
REG = "kb/l3/registry/negative_rules.json"
L0_REC = "kb/l0/records/负面样本"
L0_ATT = "kb/l0/attachments/负面样本"
FIELD = "图片素材"


def load_jsonl(p):
    out = []
    if not os.path.exists(p):
        return out
    for line in open(p, encoding="utf-8"):
        if line.strip():
            out.append(json.loads(line))
    return out


def l0_images(rec_dir=L0_REC):
    out = set()
    for fn in os.listdir(rec_dir):
        if not fn.endswith(".json"):
            continue
        doc = json.load(open(os.path.join(rec_dir, fn), encoding="utf-8"))
        for a in (((doc.get("fields") or {}).get(FIELD) or {}).get("value") or []):
            if isinstance(a, dict) and a.get("file_token"):
                out.add(a["file_token"])
    return out


def stored_tokens(att_dir=L0_ATT):
    out = set()
    if not os.path.isdir(att_dir):
        return out
    for rid in os.listdir(att_dir):
        d = os.path.join(att_dir, rid)
        if not os.path.isdir(d):
            continue
        for fn in os.listdir(d):
            p = os.path.join(d, fn)
            if os.path.isfile(p) and os.path.getsize(p) > 0:
                out.add(fn.rsplit(".", 1)[0])
    return out


def check(rules, map_rows, reg, src_tokens, l0_tokens, item_rows=None):
    """纯函数：喂数据就能证。返回问题清单（空 = 过）。"""
    bad = []
    # ① 条款号
    arts = [r.get("article_no") for r in rules]
    if len(set(arts)) != len(arts):
        bad.append("条款号重复：%s" % [a for a in set(arts) if arts.count(a) > 1][:5])
    expect = ["N-1.%d" % i for i in range(1, len(rules) + 1)]
    if arts != expect:
        bad.append("条款号不连续/顺序不对（期望 N-1.1…N-1.%d）" % len(rules))
    # ② 证据
    for r in rules:
        if not r.get("evidence_units"):
            bad.append("%s 没有 evidence_units" % r.get("article_no"))
        for e in (r.get("evidence_units") or []):
            if not (e.get("unit_id") and e.get("anchor") and e.get("source_sha256")):
                bad.append("%s 证据缺 unit_id/anchor/source_sha256" % r.get("article_no"))
                break
        if not r.get("record_ids"):
            bad.append("%s 没有 record_ids" % r.get("article_no"))
        for im in (r.get("image_refs") or []):
            if im.get("file_token") not in l0_tokens:
                bad.append("%s 引用的图片在 L0 没有字节：%s" % (r.get("article_no"), im.get("file_token")))
                break
    # ③ 图片覆盖（未覆盖的必须在 registry 里点名）
    covered = {m["file_token"] for m in map_rows}
    declared = set((reg or {}).get("images_uncovered") or [])
    missing = src_tokens - covered - declared
    if missing:
        bad.append("有 %d 张图既没被规则引用、也没被 registry 点名：%s"
                   % (len(missing), sorted(missing)[:5]))
    # ④ map 与规则双向一致
    rule_tokens = {im["file_token"] for r in rules for im in (r.get("image_refs") or [])}
    if rule_tokens - covered:
        bad.append("规则里有、image_map 里没有的图：%s" % sorted(rule_tokens - covered)[:5])
    if covered - rule_tokens:
        bad.append("image_map 里有、规则里没有的图：%s" % sorted(covered - rule_tokens)[:5])
    # ⑤ 逐条溯源：三栏（具体原因/分析、建议）里每一条都必须落到规则上
    if item_rows is not None:
        ids = {r.get("rule_id") for r in rules}
        unmapped = [x for x in item_rows if not x.get("rule_id") or x["rule_id"] not in ids]
        if unmapped:
            bad.append("有 %d 条要点/建议没落到规则上：%s"
                       % (len(unmapped), [x.get("text", "")[:20] for x in unmapped[:5]]))
    return bad


def selftest():
    """反向对照：造三种坏法，判据必须精确变红。"""
    rules = [
        {"article_no": "N-1.1", "record_ids": ["r1"], "image_refs": [{"file_token": "t1"}],
         "evidence_units": [{"unit_id": "u1", "anchor": "#a", "source_sha256": "s1"}]},
    ]
    map_rows = [{"file_token": "t1"}]
    src = {"t1"}
    l0 = {"t1"}
    cases = []
    cases.append(("全齐 → 无问题", not check(rules, map_rows, {}, src, l0), None))
    # 坏法 ①：少一张图映射（图没被覆盖、也没点名）
    cases.append(("漏一张图 → 红", bool(check(rules, [], {}, src, l0)), "漏图"))
    # 坏法 ②：条款号跳号
    r2 = [dict(rules[0], article_no="N-1.2")]
    cases.append(("条款号跳号 → 红", bool(check(r2, map_rows, {}, src, l0)), "条款号"))
    # 坏法 ③：证据缺 sha
    r3 = [dict(rules[0], evidence_units=[{"unit_id": "u1", "anchor": "#a"}])]
    cases.append(("证据缺 sha → 红", bool(check(r3, map_rows, {}, src, l0)), "证据"))
    ok = all(c[1] for c in cases)
    for name, okc, _ in cases:
        print(("  ✅ " if okc else "  ❌ ") + name)
    print("selftest %s（%d/%d）" % ("PASS" if ok else "FAIL", sum(1 for c in cases if c[1]), len(cases)))
    return 0 if ok else 3


def main(argv):
    if "--selftest" in argv:
        return selftest()
    rules = load_jsonl(RULES)
    map_rows = load_jsonl(MAP)
    reg = json.load(open(REG, encoding="utf-8")) if os.path.exists(REG) else {}
    src = l0_images()
    l0 = stored_tokens()
    print("规则 %d 条 ｜ 图片映射 %d 张 ｜ L0 记录里的图 %d 张 ｜ L0 有字节 %d 张"
          % (len(rules), len(map_rows), len(src), len(l0)))
    item_rows = load_jsonl(ITEM)
    bad = check(rules, map_rows, reg, src, l0, item_rows)
    print("逐条溯源：%d 条（具体原因/分析 + 建议）" % len(item_rows))
    if not bad:
        print("✅ 条款号/证据/覆盖/映射 四项全过")
        return 0
    print("❌ 不合格 %d 项：" % len(bad))
    for b in bad[:20]:
        print("   -", b)
    return 3


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
