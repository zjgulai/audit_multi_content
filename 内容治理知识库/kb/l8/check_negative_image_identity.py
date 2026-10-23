#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_negative_image_identity.py —— 「库内负面样本图，发到守衡必须命中」的**生产形态**判据。

## 为什么另立一条（2026-10-21）
`check_negative_image_hitrate.py`（S13）量的是「**库内 OCR** → 引擎」：它把 L1 的 OCR 原文
拼成送审文本 ⇒ 库内图当然能命中。而**生产**送进来的是另一份东西：
飞书 IM 重压缩过的图（图字节 sha 变了）、另一套 OCR（丢变音符号 / 夹水印行）。
实测 2026-10-21 的德国海报：库内 OCR 能命中，生产文本 **0 命中** ⇒ PASS。
⇒ 本判据**只认图**：把库内图重压缩后当送审图，交给真引擎的「图身份层」，
每张都必须出 ≥1 条**对应该图规则**的 finding；库外图（噪声图）必须 0 命中。

## 判据
  I1 **命中**：抽 `--sample N` 张（默认 5，固定种子），逐张把图**重压缩**（缩 80% + JPEG70，
     模拟飞书 IM），用 `review.py --image <重压缩图>` 跑真引擎 ⇒ 必须出 ≥1 条
     `layer=负面样本规则` 的 finding，且条款号 ∈ 该图 `negative_image_map` 的规则集。
  I2 **反向对照**：同一批里用一张**库外噪声图** ⇒ 图身份命中必须为 0（不恒真）。
  I3 **供给链拒答**（freshness fail-closed）⇒ **未测**（不计红、也不记绿）。

## 用法
    python3 kb/l8/check_negative_image_identity.py                 # 抽 5 张
    python3 kb/l8/check_negative_image_identity.py --sample 0      # 全部 339 张（很慢）
    python3 kb/l8/check_negative_image_identity.py --sample 20 --seed 7
    python3 kb/l8/check_negative_image_identity.py --selftest      # 反向对照：噪声图必须不命中
    python3 kb/l8/check_negative_image_identity.py --write-artifact
退出码：0 = 绿/未测 ｜ 3 = 红
"""
import argparse
import json
import os
import random
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
KB = os.path.dirname(HERE)
WS = os.path.dirname(KB)
IDX = os.path.join(KB, "l3", "candidates", "negative_image_fp.jsonl")
L1 = os.path.join(KB, "l1", "2_内部正负样本库")
REVIEW = os.path.join(KB, "l7", "skills", "kb-content-review", "scripts", "review.py")
ARTIFACT = os.path.join(KB, ".work", "negative_image_identity.json")
NEG_LAYER = "负面样本规则"


class Unmeasured(Exception):
    pass


def jlines(p):
    with open(p, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                yield json.loads(line)


def load_index():
    return list(jlines(IDX)) if os.path.exists(IDX) else []


def _image_ocr(record_id):
    """该记录 L1 的图内文字（没有就回空串——图身份层不依赖它）。"""
    p = os.path.join(L1, "bitable__tbld8qE92YaY38Yz__%s.json" % record_id)
    if not os.path.exists(p):
        return ""
    try:
        d = json.load(open(p, encoding="utf-8"))
    except Exception:
        return ""
    for s in d.get("segments") or []:
        if s.get("kind") == "image_ocr" and s.get("text"):
            return s["text"]
    return ""


def _compress(src, dst, q=70, scale=0.8):
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = None
    im = Image.open(src).convert("RGB")
    w, h = im.size
    im = im.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.LANCZOS)
    im.save(dst, format="JPEG", quality=q)
    return dst


def _noise_image(path, seed=7):
    """库外图：确定性噪声（与任何库内图都不可能同图）。"""
    from PIL import Image
    rnd = random.Random(seed)
    w, h = 320, 320
    px = [(rnd.randrange(256), rnd.randrange(256), rnd.randrange(256)) for _ in range(w * h)]
    im = Image.new("RGB", (w, h))
    im.putdata(px)
    im.save(path, format="PNG")
    return path


def run_engine(image_path, text):
    tmp = tempfile.mkdtemp(prefix="negid-")
    tf = os.path.join(tmp, "m.txt")
    with open(tf, "w", encoding="utf-8") as fh:
        fh.write(text or "（图内文字未读出）")
    env = dict(os.environ, KB_INTERP_OK="1", KB_ENTRY="with_kb_evidence")
    try:
        p = subprocess.run([sys.executable, REVIEW, "--kb-root", WS, "--file", tf,
                            "--content-type", "image", "--image", image_path,
                            "--json", "--dry-run"],
                           cwd=WS, capture_output=True, text=True, env=env, timeout=600)
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)
    out = p.stdout or ""
    i = out.find("{")
    while i != -1:
        try:
            doc = json.loads(out[i:])
            break
        except json.JSONDecodeError:
            i = out.find("{", i + 1)
    else:
        raise RuntimeError("引擎没吐 JSON（rc=%s）：%s" % (p.returncode, (p.stderr or "")[-300:]))
    if p.returncode == 3 and not (doc.get("trace") or {}):
        ref = ((doc.get("evidence_meta") or {}).get("refusal") or {})
        raise Unmeasured(ref.get("reason") or "引擎拒答（freshness fail-closed）")
    return doc


def neg_findings(doc):
    return [f for f in (doc.get("findings") or [])
            if NEG_LAYER in str(f.get("layer") or "")]


def check_one(entry, workdir):
    """重压缩该库内图 → 跑引擎 → 断言命中它自己的规则。"""
    src = os.path.join(KB, entry["path"])
    dst = os.path.join(workdir, "src-%s-%s.jpg" % (entry["record_id"], entry.get("seq")))
    _compress(src, dst)
    text = _image_ocr(entry["record_id"])
    doc = run_engine(dst, text)
    fs = neg_findings(doc)
    want = set(entry.get("want_article_nos") or [])
    got = {f.get("article_no") for f in fs}
    ok = bool(fs) and (not want or bool(got & want))
    return {"record_id": entry["record_id"], "seq": entry.get("seq"),
            "want": sorted(want), "got": sorted(x for x in got if x),
            "hit": ok, "n": len(fs),
            "identity": ((doc.get("trace") or {}).get("image_identity") or {}).get("checked")}


def reverse_control(workdir):
    p = _noise_image(os.path.join(workdir, "noise.png"))
    doc = run_engine(p, "Summer sale. Shop now and save 20%.")
    return len(neg_findings(doc))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=5)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--write-artifact", action="store_true")
    a = ap.parse_args()
    idx = load_index()
    if not idx:
        print("❌ 图身份索引缺件：跑 python3 kb/l8/build_negative_image_fp.py")
        return 3
    workdir = tempfile.mkdtemp(prefix="negid-w-")
    try:
        # 只量「有**可引用**规则（point/advice，且正文够长、不是链接/@）」的图：
        # 其余图（observation/brief/non_substantive 占 151/339）引擎按口径不出 findings，
        # 那是数据缺口，不是命中判据能解的——单独计数，不算红。
        rules = {}
        for line in open(os.path.join(KB, "l3", "candidates", "negative_rules.jsonl"), encoding="utf-8"):
            r = json.loads(line)
            rules[r.get("rule_id")] = r

        def _substantive(rid):
            r = rules.get(rid) or {}
            txt = str(r.get("rule_text") or "").strip()
            if str(r.get("rule_kind") or "") not in ("point", "advice"):
                return False
            if len(txt) < 10:
                return False
            if "http://" in txt or "https://" in txt or "www." in txt:
                return False
            if txt.startswith("@") or txt.count("@") >= 2:
                return False
            return True

        for e in idx:
            e["want_article_nos"] = [rules.get(x, {}).get("article_no")
                                     for x in (e.get("rule_ids") or []) if _substantive(x)]
        pool = [e for e in idx if e.get("want_article_nos")]
        if a.selftest:
            # 反向对照：噪声图必须 0 命中；再拿一张库内图（重压缩）必须命中
            rev = reverse_control(workdir)
            one = check_one(pool[0], workdir)
            print("selftest：噪声图命中 %d（要求 0）｜库内图命中 %s（要求 True）" % (rev, one["hit"]))
            return 0 if (rev == 0 and one["hit"]) else 3
        picked = pool if a.sample == 0 else random.Random(a.seed).sample(pool, min(a.sample, len(pool)))
        rows = []
        for e in picked:
            rows.append(check_one(e, workdir))
        rev = reverse_control(workdir)
        hit = sum(1 for r in rows if r["hit"])
        out = {"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "images": len(idx),
               "citable_images": len(pool),
               "noncitable_images": len(idx) - len(pool),
               "sample": a.sample, "checked": len(rows), "hit": hit,
               "miss": [r for r in rows if not r["hit"]],
               "controls": {"unrelated_image_hits": rev},
               "verdict": "PASS" if (hit == len(rows) and rev == 0) else "FAIL"}
        if a.write_artifact:
            os.makedirs(os.path.dirname(ARTIFACT), exist_ok=True)
            with open(ARTIFACT, "w", encoding="utf-8") as fh:
                json.dump(out, fh, ensure_ascii=False, indent=1)
        print(json.dumps(out, ensure_ascii=False, indent=1))
        return 0 if out["verdict"] == "PASS" else 3
    except Unmeasured as e:
        print(json.dumps({"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "verdict": "UNTESTED",
                          "why": str(e)}, ensure_ascii=False, indent=1))
        return 0
    finally:
        import shutil
        shutil.rmtree(workdir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
