#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_negative_rule_reverse_images.py —— **真图反向对照**（P1，2026-10-20）。

## 为什么单独立这一件

`check_negative_rule_acceptance.py` 的 ④ 反向对照用的是**一段通用营销文案**
（`Summer sale. Shop now...`）。它能抓住「阈值形同虚设」，但**抓不住**真实事故的形状：

    2026-10-20 真单：图片单的报告里出现「1.挂式衣架: 磨砂亚克力材质…」——
    图里根本没有衣架。命中读数是「仅文字 0.50 / 画面 0.00」，而报告把它印成
    「这张图命中了某某条款」。

那种命中，通用文案一条都构造不出来 —— 它需要**真实素材之间**的字符二元组重合
（同一个品牌名 `momcozy`、同一套外文营销句式就够）。所以反向对照的夹具必须换成
**库内别的真图**：拿 A 条记录的图内文字去检索，命中若**不是 A 自己那条**，就是误引用。

## 本条闸门量什么（两条，缺一不可）

  R1 **不许跨记录误引用**：样本里每个素材，引擎返回的负样本命中必须**全部**属于它自己
     （`why=同图` 或 `visual_score>=0.30`）。任何一条「仅文字相近」的命中都算红 ——
     因为它会被印成"这张图命中了某某条款"，而画面/图片根本不是那一张。
  R2 **反向对照（不恒真）**：改成一条**别的记录**的图内文字去检索，**不许**命中样本这条的规则。
     （只写 R1 而不写 R2 的话，判据可能因为"引擎什么都不返回"而恒绿。）

## 为什么走**真引擎**而不是直接调 matcher

`require_visual` 这个过滤住在 `kb/l7/skills/kb-content-review/scripts/review.py::layer_negative_rules`
里，**matcher 里没有它**。直接调 `negative_rule_match.match()` 测出来的数与线上看到的
**不是同一件事**（本人在 11:46 就这么量错过一次：离线报"18 条满额误命中"，引擎实际是 0 条）。
⇒ 判据必须打在**引擎产物**上：读 `trace.negative_rules.hits[]` 的 `why` / `visual_score`。

用法：
  python3 kb/l8/check_negative_rule_reverse_images.py [--sample 12]
退出码：0 = 全过 ｜ 3 = 有判据红
"""
import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
KB = os.path.dirname(HERE)
WS = os.path.dirname(KB)
REVIEW = os.path.join(KB, "l7", "skills", "kb-content-review", "scripts", "review.py")
L0_LIVE = os.path.join(KB, "l0", "records", "负面样本")     # 日更真身（换代后的记录只在这里）
L2_UNITS = os.path.join(KB, "l2", "units.jsonl")
L4_CASES = os.path.join(KB, "l4", "canonical", "sample_case.jsonl")
RULES = os.path.join(KB, "l3", "candidates", "negative_rules.jsonl")


def jlines(p):
    out = []
    with open(p, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def clean_ocr(text):
    """剥掉 L2 的 `[image_ocr]` 标记并按段去重 —— 还原守衡真实收到的图内文字。

    ⚠️ 不剥会**系统性低估**：标记自带中文二元组，会把英文素材的命中分往下拉
    （实测：带标记自命中 43%，剥掉后 49%），而且 `[image_ocr]` 这段字在规则侧的
    `image_refs[].ocr_text` 里并不存在 ⇒ 同图指纹永远对不上。
    """
    parts = [p.strip() for p in str(text or "").split("[image_ocr]")]
    seen = []
    for p in parts:
        if p and p not in seen:
            seen.append(p)
    return "\n".join(seen)


def build_fixtures():
    """记录号 → 图内文字（只取**日更真身**里的记录）。"""
    live = {os.path.basename(p)[:-5] for p in glob.glob(os.path.join(L0_LIVE, "*.json"))}
    ocr = {}
    for u in jlines(L2_UNITS):
        t = str(u.get("text") or "")
        if "[image_ocr]" not in t:
            continue
        m = re.search(r"#素材/([^/]+)/", str(u.get("anchor") or ""))
        if not m or m.group(1) not in live:
            continue
        ocr.setdefault(m.group(1), []).append(t)
    # 记录 → 自己那条规则的条款号（判「这条命中是不是它自己的」）
    own = {}
    for r in jlines(RULES):
        for rid in (r.get("record_ids") or []):
            own.setdefault(rid, set()).add(r.get("article_no"))
    fixtures = []
    for rid, txts in ocr.items():
        if rid not in own:
            continue                        # 没有规则 ⇒ 命不命中都是 0，测不出东西
        txt = clean_ocr("\n".join(txts))
        if len(txt.strip()) < 12:
            continue
        fixtures.append({"record": rid, "ocr": txt, "own": own[rid]})
    return sorted(fixtures, key=lambda x: x["record"])


class Unmeasured(Exception):
    """引擎拒答、层没执行 ⇒ 本判据**未测**（既不绿也不红）。"""


def run_engine(ocr_text, tag):
    """把图内文字按**守衡真实送审格式**送进真引擎，返回 trace.negative_rules。"""
    tmp = tempfile.mkdtemp(prefix="negrev-")
    tf = os.path.join(tmp, "m.txt")
    # 守衡送图单时正文恒以这一行开头（见 `agent.mjs`）；库侧的图单判据认的就是它。
    with open(tf, "w", encoding="utf-8") as fh:
        fh.write("【图片 1 的图内文字（本机 OCR）】\n" + ocr_text)
    try:
        p = subprocess.run([sys.executable, REVIEW, "--i-am-the-entry", "--file", tf,
                            "--content-type", "text", "--json", "--dry-run",
                            "--report-dir", tmp, "--run-id", "rev-" + tag],
                           cwd=WS, capture_output=True, text=True, timeout=300)
        # ★ 退出码 3 = 引擎给了**拒答**（NEEDS_INPUT），stdout 仍是完整 JSON —— 那是合法结果，
        #   不是"没跑成"。把它当失败会让本闸门在覆盖缺口素材上误红（实测 1/12 条）。
        if p.returncode not in (0, 3) or not (p.stdout or "").strip():
            raise RuntimeError("引擎退出码 %s：%s" % (p.returncode, (p.stderr or "")[-300:]))
        doc = json.loads(p.stdout)
        # ★★ 供给链拒答（fail-closed）时引擎**根本不跑层**，trace 是空的 ⇒ 本判据**未测**。
        #   不许读成「没跑 = 红」，也不许读成绿（未测不是通过）。
        if p.returncode == 3 and not (doc.get("trace") or {}):
            raise Unmeasured("供给链拒答（fail-closed）⇒ 引擎没跑层，本判据**未测**")
        nr = ((doc.get("trace") or {}).get("negative_rules")) or {}
        if nr.get("error"):
            raise RuntimeError("负样本层报错：%s" % nr["error"])
        if not nr.get("engine"):
            raise RuntimeError("负样本层没跑（触发判据红了？）")
        return doc.get("state"), nr
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def is_itself(hit):
    """这条命中算不算「真的对上了这张图」—— 与引擎 `require_visual` 同口径。"""
    return hit.get("why") == "同图" or float(hit.get("visual_score") or 0) >= 0.30


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=12, help="抽多少条记录（默认 12）")
    ap.add_argument("--selftest", action="store_true",
                    help="证明这条判据不是恒绿：绕过引擎的 require_visual 过滤、直接调 matcher，"
                         "必须能看见跨记录误引用（否则说明样本选得没打到要害）")
    a = ap.parse_args()

    fx = build_fixtures()
    if not fx:
        print("✗ 没有可用夹具（真身记录 ∩ 有规则 ∩ 有图内文字 为空）")
        return 3
    step = max(1, len(fx) // max(1, a.sample))
    picked = fx[::step][:a.sample]

    print("=" * 78)
    print("负面样本规则 · **真图反向对照**（引擎口径）")
    print("=" * 78)
    # ── ★ 不是恒绿的证明：同一批样本，**绕过引擎过滤**（直接调 matcher）应当看见误引用 ──
    #   只写「引擎返回 0 条跨记录」是不够的 —— 引擎如果整层没跑、或阈值高到什么都不返回，
    #   这条判据照样是绿的。所以必须先证明**同样的输入在不过滤时确实会出错**。
    if a.selftest:
        sys.path.insert(0, HERE)
        import negative_rule_match as _M
        rules = _M.load_rules(RULES)
        raw_foreign = 0
        for i, f in enumerate(picked):
            txt = "【图片 1 的图内文字（本机 OCR）】\n" + f["ocr"]
            hits = _M.match(txt, None, top=5, min_score=0.45, rules=rules)
            raw_foreign += sum(1 for h in hits if h.get("article_no") not in f["own"])
        ok = raw_foreign > 0
        print(f"\n辨别力对照（绕过引擎过滤）：样本 {len(picked)} 条共出现跨记录误引用 "
              f"{raw_foreign} 条 ⇒ {'成立（判据能红）' if ok else '**不成立：这批样本打不到要害**'}")
        if not ok:
            print("✗ 这批样本在「不过滤」时也不出错 ⇒ 用它当反向对照等于恒绿")
            return 3
        print("✅ 辨别力成立：不过滤会误引用，引擎的 require_visual 把它挡住了")
        return 0

    bad = 0
    unm = 0
    tot_hits = tot_self = tot_dropped = tot_sib = 0
    for i, f in enumerate(picked):
        try:
            state, nr = run_engine(f["ocr"], "%02d" % i)
        except Unmeasured as e:
            print(f"  ⚠ {f['record']} **未测**：{e}")
            unm += 1
            continue
        except Exception as e:                      # noqa: BLE001
            print(f"  ✗ {f['record']} 没跑成：{e}")
            bad += 1
            continue
        hits = nr.get("hits") or []
        dropped = nr.get("dropped_text_only") or []
        # ★★ 口径（与 `require_visual` 一致，2026-10-20 修正）：
        #   「跨记录」**本身不是罪** —— 库内一张图会挂在多条记录上（实测 154 张图跨 ≥2 条，
        #   单图最多 12 条记录），同一张图命中兄弟记录的规则是**对的**（那确实是这张图的历史意见）。
        #   真正要禁的是「**不是这张图**却被引成本单命中」：`why!=同图` 且 `visual_score<0.30`。
        illegal = [h for h in hits if not is_itself(h)]
        sibling = [h for h in hits if is_itself(h) and h.get("article_no") not in f["own"]]
        tot_hits += len(hits); tot_self += len(hits) - len(illegal) - len(sibling)
        tot_sib += len(sibling)
        tot_dropped += len(dropped)
        ok = not illegal
        print(f"  {'✓' if ok else '✗'} {f['record']:<18} state={str(state):<7} "
              f"命中 {len(hits)}（本记录 {len(hits)-len(illegal)-len(sibling)}｜"
              f"同图兄弟 {len(sibling)}）｜滤掉 {len(dropped)}"
              f"{'' if ok else '｜★ 不是这张图：' + ','.join(h.get('article_no') for h in illegal)}")
        if not ok:
            bad += 1
            for h in illegal:
                print(f"       ★ 误引用 {h.get('article_no')} score={h.get('score')} "
                      f"why={h.get('why')} visual={h.get('visual_score')}")

    # ── R2 反向对照：拿**别的记录**的图内文字去检索，不许命中这一条的规则 ──────────
    print("-" * 78)
    if len(picked) >= 2:
        src, other = picked[0], picked[1]
        try:
            _st, nr2 = run_engine(src["ocr"], "reverse")
            leak = [h for h in (nr2.get("hits") or []) if h.get("article_no") in other["own"]]
            ok2 = not leak
            print(f"  {'✓' if ok2 else '✗'} R2 反向对照：把 {src['record']} 的图内文字送进去，"
                  f"不许命中 {other['record']} 的规则（{len(other['own'])} 条）"
                  f"｜实际 {len(leak)} 条")
        except Unmeasured as e:
            ok2 = True
            print(f"  ⚠ R2 反向对照**未测**：{e}")
        except Exception as e:                      # noqa: BLE001
            ok2 = False
            print(f"  ✗ R2 反向对照没跑成：{e}")
        if not ok2:
            bad += 1
    else:
        print("  ✗ R2 反向对照缺夹具（至少要 2 条记录）")
        bad += 1

    print("-" * 78)
    print(f"读数：样本 {len(picked)} 条｜命中合计 {tot_hits}"
          f"（本记录 {tot_self}｜同图兄弟记录 {tot_sib}｜**不是这张图 0 条**）"
          f"｜被 require_visual 滤掉 {tot_dropped} 条")
    if unm:
        print(f"⚠ 未测 {unm} 条 ⇒ **不得判通过**（供给链拒答时层根本没跑；先把链跑回新鲜再复跑）")
        return 3
    if bad:
        print(f"❌ 未过：红 {bad} 处 —— 出现了「不是这张图」却被引成本单判断的命中")
        return 3
    print("✅ 通过：库内真图自送，每一条负样本命中都真对得上这张图（同图或画面对上）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
