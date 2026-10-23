#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_negative_rule_acceptance.py —— 负面样本图库入规这条线**能不能交付**的验收判据。

它把四件事串成一次可复跑的读数（全只读，不联网）：

  ① 覆盖闸门：`check_image_coverage.py`（源 token / L0 字节 / L1 OCR / 画面读数）
  ② 规则闸门：`check_negative_rule_coverage.py`（条款号/证据/图片挂载/映射一致）
  ③ **命中样例**：取 N 条有图有规则的记录，用它们自己的「OCR + 画面读数」去检索，
     必须命中**自己记录里的规则**（top-k 内）——这是「发了这张图能不能命中原图」的代理判据
  ④ **反向对照**：一段与负面样本无关的通用营销文案 + 干净画面读数，命中数必须为 0
     （否则说明门槛形同虚设，「命中」没意义）

用法：
  python3 kb/l8/check_negative_rule_acceptance.py            # 抽样 10 条
  python3 kb/l8/check_negative_rule_acceptance.py --sample 20 --top 3
退出码：0 = 全过 ｜ 3 = 有判据红
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
KB = os.path.dirname(HERE)
WS = os.path.dirname(KB)
sys.path.insert(0, HERE)
import negative_rule_match as M  # noqa: E402

L1_DIR = os.path.join(WS, "kb", "l1", "2_内部正负样本库")
PREFIX = "media_tbld8qE92YaY38Yz_"


def run_gate(script):
    p = subprocess.run([sys.executable, os.path.join(HERE, script)],
                       capture_output=True, text=True, timeout=300)
    tail = (p.stdout or "").strip().splitlines()[-1:] or [""]
    return p.returncode, tail[0]


def load_docs():
    docs = {}
    if not os.path.isdir(L1_DIR):
        return docs
    for fn in sorted(os.listdir(L1_DIR)):
        if fn.startswith(PREFIX) and fn.endswith(".json"):
            d = json.load(open(os.path.join(L1_DIR, fn), encoding="utf-8"))
            rid = (d.get("source") or {}).get("record_id")
            if rid:
                docs[rid] = d
    return docs


def doc_inputs(d):
    ocr = " ".join(s.get("text") or "" for s in (d.get("segments") or []) if s.get("kind") == "image_ocr")
    vis = next((s.get("scene") for s in (d.get("segments") or []) if s.get("kind") == "image_visual"), None)
    return ocr, vis


def main(argv):
    sample = 10
    top = 3
    for i, a in enumerate(argv):
        if a == "--sample" and i + 1 < len(argv):
            sample = int(argv[i + 1])
        elif a == "--top" and i + 1 < len(argv):
            top = int(argv[i + 1])

    fails = []

    # ① 覆盖
    rc, line = run_gate("check_image_coverage.py")
    print("① 覆盖闸门：%s（%s）" % ("✅" if rc == 0 else "❌", line))
    if rc != 0:
        fails.append("覆盖闸门红")

    # ② 规则
    rc, line = run_gate("check_negative_rule_coverage.py")
    print("② 规则闸门：%s（%s）" % ("✅" if rc == 0 else "❌", line))
    if rc != 0:
        fails.append("规则闸门红")

    # ③ 命中样例（**图片级**自检索）：拿每张图自己的 OCR + 画面读数去检索，
    #    必须命中最少一条**引用了这张图的**规则 —— 这才是「发这张图能不能命中它自己」。
    rules = M.load_rules()
    tok2rules = {}
    for r in rules:
        for im in (r.get("image_refs") or []):
            tok2rules.setdefault(im.get("file_token"), set()).add(r.get("rule_id"))
    docs = load_docs()
    by_id = {r["rule_id"]: r for r in rules}

    def same_image_hit(hits, ocr):
        n = M._norm(ocr)
        for h in hits:
            r = by_id.get(h["rule_id"]) or {}
            if any(M._norm(im.get("ocr_text") or "") == n for im in (r.get("image_refs") or [])):
                return True
        return False

    total = hit = 0
    for rid, doc in docs.items():
        segs = doc.get("segments") or []
        for m in (doc.get("media_refs") or []):
            tok = m.get("file_token")
            if tok not in tok2rules:
                continue
            anchor = m.get("anchor")
            ocr = next((x.get("text") or "" for x in segs
                        if x.get("anchor") == anchor and x.get("kind") == "image_ocr"), "")
            vis = next((x.get("scene") for x in segs
                        if x.get("anchor") == anchor and x.get("kind") == "image_visual"), None)
            hits = M.match(ocr, vis, top=top, rules=rules)
            total += 1
            if same_image_hit(hits, ocr):
                hit += 1
    rate = (hit / total) if total else 0
    # ★ 2026-10-20（Owner 硬要求）：**库内图必须 100% 命中**，不是 80%。
    ok3 = total > 0 and rate >= 1.0
    print("③ 图片级自检索 top%d：%d/%d（%.0f%%）%s"
          % (top, hit, total, rate * 100, "✅" if ok3 else "❌"))
    if not ok3:
        fails.append("图片级自检索命中率 <100%%")

    # ③b 守衡现成形状：**正文里嵌画面读数**（【/图 N 画面读数】+ sceneBlock）
    #     —— 这条路的命中率必须与结构化 scene 相当，否则「守衡已经把画面读出来了」
    #     在规则匹配里等于白费（实测：不剥块时 74%，剥块后 83%）。
    def _block(sc):
        if not sc:
            return ""
        L = []
        if sc.get("setting"):
            L.append("- 场景：%s" % sc["setting"])
        if sc.get("people"):
            L.append("- 人物：%s" % "；".join("%s · %s" % (p.get("kind", ""), p.get("doing", ""))
                                             for p in sc["people"]))
        if sc.get("products"):
            L.append("- 物品：%s" % "；".join(str(p.get("what", "")) for p in sc["products"]))
        if sc.get("risk_cues"):
            L.append("- 画面线索：%s" % "；".join(sc["risk_cues"]))
        return "\n".join(L)

    emb_total = emb_hit = 0
    for rid, doc in docs.items():
        segs = doc.get("segments") or []
        for m in (doc.get("media_refs") or []):
            tok = m.get("file_token")
            if tok not in tok2rules:
                continue
            anchor = m.get("anchor")
            ocr = next((x.get("text") or "" for x in segs
                        if x.get("anchor") == anchor and x.get("kind") == "image_ocr"), "")
            vis = next((x.get("scene") for x in segs
                        if x.get("anchor") == anchor and x.get("kind") == "image_visual"), None)
            text = ("【图 1 图内文字（本机 OCR，逐字）】\n" + ocr + "\n【/图 1】\n"
                    + "【图 1 画面读数（视觉模型的读数，**不是原图**）】\n" + _block(vis)
                    + "\n【/图 1 画面读数】")
            hits = M.match(text, None, top=top, rules=rules)
            emb_total += 1
            if same_image_hit(hits, ocr):
                emb_hit += 1
    emb_rate = (emb_hit / emb_total) if emb_total else 0
    ok3b = emb_total > 0 and emb_rate >= 1.0
    print("③b 正文内嵌画面读数自检索 top%d：%d/%d（%.0f%%）%s"
          % (top, emb_hit, emb_total, emb_rate * 100, "✅" if ok3b else "❌"))
    if not ok3b:
        fails.append("内嵌画面读数命中率 <100%")

    # ④ 反向对照
    neg_text = "Summer sale. Shop now. Free shipping on orders over 50 dollars. New arrivals available."
    neg_scene = {"setting": "影棚", "people": [], "products": [{"what": "白色背景板", "in_use": False}],
                 "visible_marks": ["有文字，认不清"], "text_script": "英文", "risk_cues": []}
    neg_hits = M.match(neg_text, neg_scene, top=top, rules=rules)
    ok4 = not neg_hits
    print("④ 反向对照：无关文案命中 %d 条 %s" % (len(neg_hits), "✅" if ok4 else "❌"))
    if not ok4:
        fails.append("无关文案被误命中")

    if fails:
        print("\n❌ 验收未过：" + "；".join(fails))
        return 3
    print("\n✅ 验收通过：覆盖齐、规则齐、库内图 100% 命中、无关文案 0 命中")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
