#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_negative_image_hitrate.py —— 「库内反面案例图，发到飞书侧必须命中库内意见」的判据。

## 为什么单独立这一件（Owner 2026-10-20）

Owner 原话：「339 张图……我这飞书侧发图片，就应该命中规则」＋「所有修复必须落库，
避免这个问题反复修复」。

在此之前，这条链上有**三道会静默吞掉命中的门**，每一道都是当天为了修另一个 bug 加的，
而且**没有任何尺子在量"改完还剩几张能命中"**：

  ① `narrow_negative_hits`：跨记录聚合的规则整条丢（实测吃掉 122/329 张图的全部命中）；
  ② 归属门：只有 `subject` 图可引用（288 张去重图里 subject 只有 15 张）；
  ③ 打分口径：带画面读数但规则无画面线索时，分数上限 0.40 < 阈值 0.45（新图必空）。

三道门的口径已经改成「**有命中就输出，但按 `evidence_class` 标清楚凭什么算**」
（figure / record / shared；unknown 仍不算）。**本条闸门量的是改完之后的结果**：
339 张库内图，逐张送真引擎，每张都必须产出 ≥1 条负面样本意见。

## 判据（三条，缺一条这一档就不算数）

  H1 **数据完整**：339 张图每一张都能在 `negative_rules.jsonl` 里找到至少一条挂它的规则
     （数据层）。这是"提炼成了规则"这句话的**可核对版本**。
  H2 **真引擎命中**：抽 `--sample` 张（默认 12，固定种子），逐张按守衡送审形状
     （图内文字 + 画面读数）过**真引擎**，每张都必须出 ≥1 条 `layer=负面样本规则` 的 finding。
  H3 **反向对照（不恒真）**：同一批取样里，把图内文字换成一段无关营销文案 ⇒
    负面样本意见必须为 0（否则说明门槛形同虚设，"命中"没意义）。

## 三种结局必须分得开

  · 供给链拒答（freshness fail-closed）⇒ **未测**（不计红、也不记绿）；
  · 引擎跑成但某张没意见 ⇒ **红**（这条正是 Owner 报的那类问题）；
  · 全过 ⇒ 绿。

用法：
  python3 kb/l8/check_negative_image_hitrate.py                 # 抽 12 张（约 2~4 分钟）
  python3 kb/l8/check_negative_image_hitrate.py --sample 0      # 全部 339 张（很慢）
  python3 kb/l8/check_negative_image_hitrate.py --selftest      # 判据自证（含反向对照）
  python3 kb/l8/check_negative_image_hitrate.py --write-artifact  # 落读数给冒烟闸门读

退出码：0 = 绿/未测 ｜ 3 = 红
"""
import argparse
import glob
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
KB = os.path.dirname(HERE)
WS = os.path.dirname(KB)
PREFIX = "media_tbld8qE92YaY38Yz_"
L1 = os.path.join(KB, "l1", "2_内部正负样本库")
L2 = os.path.join(KB, "l2", "units.jsonl")
RULES = os.path.join(KB, "l3", "candidates", "negative_rules.jsonl")
REVIEW = os.path.join(KB, "l7", "skills", "kb-content-review", "scripts", "review.py")
ARTIFACT = os.path.join(KB, ".work", "negative_image_hitrate.json")
NEG_LAYER = "负面样本规则"


def jlines(p):
    with open(p, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                yield json.loads(line)


# ── H1：数据完整（每张图都挂得上规则）──────────────────────────────────────
def load_fixtures():
    """339 张图 → {record_id, seq, ocr, visual}。"""
    visuals = {}
    for u in jlines(L2):
        rid = (u.get("resource_id") or "")
        if not rid.startswith(PREFIX):
            continue
        t = u.get("text") or ""
        if "[image_visual]" not in t:
            continue
        visuals.setdefault(rid[len(PREFIX):], []).extend(
            [s.strip() for s in t.split("[image_visual]")[1:] if s.strip()])
    items = []
    for fn in sorted(os.listdir(L1)):
        if not (fn.startswith(PREFIX) and fn.endswith(".json")):
            continue
        rid = fn[len(PREFIX):-5]
        d = json.load(open(os.path.join(L1, fn), encoding="utf-8"))
        seg = {s.get("anchor"): (s.get("text") or "") for s in (d.get("segments") or [])
               if s.get("kind") == "image_ocr"}
        vs = visuals.get(rid) or []
        for k, m in enumerate(d.get("media_refs") or []):
            items.append({"record_id": rid, "seq": m.get("seq"), "sha256": m.get("sha256"),
                          "file_token": m.get("file_token"),
                          "ocr": seg.get(m.get("anchor")) or "",
                          "visual": (vs[k] if k < len(vs) else "")})
    return items


URL_RE = __import__("re").compile(r"https?://|www\.", __import__("re").I)


def is_substantive_rule(r):
    """这条规则正文是不是**可引用的审核意见**（2026-10-20 第五轮）。

    背景：476 条 N-1.x 里只有 132 条（28%）带规范内容，其余是 observation(245) /
    brief(35) / non_substantive(39)。真单里出现的「Figma 链接」「项目背景：亚马逊多语言修改」
    「麻烦看看呀」就是这一类 —— 引擎现在会丢掉它们（`negative_rules.not_substantive`），
    本判据在闸门侧再验一次：**finding 里不许出现这种正文**。
    """
    t = str(r.get("rule_text") or "").strip()
    if str(r.get("rule_kind") or "") not in ("point", "advice"):
        return False
    if len(t) < 10 or URL_RE.search(t) or t.startswith("@") or t.count("@") >= 2:
        return False
    return True


def h1_coverage(items):
    """每张图是否都有挂它的规则（按 sha 与 file_token 双口径）。"""
    by_sha, by_tok = set(), set()
    for r in jlines(RULES):
        for im in r.get("image_refs") or []:
            if im.get("sha256"):
                by_sha.add(im["sha256"])
            if im.get("file_token"):
                by_tok.add(im["file_token"])
    miss = [i for i in items if (i["sha256"] not in by_sha) and (i["file_token"] not in by_tok)]
    return len(miss), miss


# ── 送审形状（与守衡一致）─────────────────────────────────────────────────
def scene_block(vtext):
    out = []
    for part in [p for p in str(vtext or "").split("；") if p.strip()]:
        k, _, val = part.partition("：")
        k, val = k.strip(), val.strip()
        if not k or not val:
            continue
        key = {"场景": "场景", "人物": "人物", "产品": "物品", "可见标识": "可见标识",
               "文字脚本": "图上文字用的是什么文字", "风险线索": "画面线索"}.get(k)
        if key:
            out.append("- %s：%s" % (key, val))
    return "\n".join(out)


def build_text(it, ocr_override=None):
    ocr = it["ocr"] if ocr_override is None else ocr_override
    seq = int(it.get("seq") or 1)
    body = "【图 %d 内文字｜%d 行】\n%s\n【/图 %d】" % (
        seq, len([l for l in ocr.splitlines() if l.strip()]), ocr, seq)
    sb = scene_block(it.get("visual"))
    if sb:
        body += ("\n【图 %d 画面读数（视觉模型的读数，**不是原图**；涉及画面的结论只能依据这一格）】\n"
                 "%s\n【/图 %d 画面读数】" % (seq, sb, seq))
    return body


class Unmeasured(Exception):
    pass


def run_engine(text):
    tmp = tempfile.mkdtemp(prefix="neghit-")
    tf = os.path.join(tmp, "m.txt")
    with open(tf, "w", encoding="utf-8") as fh:
        fh.write(text)
    env = dict(os.environ, KB_INTERP_OK="1", KB_ENTRY="with_kb_evidence")
    try:
        p = subprocess.run([sys.executable, REVIEW, "--kb-root", WS, "--file", tf,
                            "--content-type", "image", "--json", "--dry-run"],
                           cwd=WS, capture_output=True, text=True, env=env, timeout=600)
    finally:
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
        # 供给链 fail-closed ⇒ 层根本没跑 —— 未测，不是红
        ref = ((doc.get("evidence_meta") or {}).get("refusal") or {})
        raise Unmeasured(ref.get("reason") or "引擎拒答（fresness fail-closed）")
    return doc


def neg_findings(doc):
    return [f for f in (doc.get("findings") or [])
            if NEG_LAYER in str(f.get("layer") or "")]


# ── 主判据 ────────────────────────────────────────────────────────────────
UNRELATED = ("Summer sale. Shop now and save 20% on selected items.\n"
             "Free shipping over $49. Limited time offer.\n"
             "Join our loyalty program today.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=12, help="抽多少张（0 = 全部）")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--write-artifact", action="store_true")
    a = ap.parse_args()

    items = load_fixtures()
    if not items:
        print("✗ 没有图内文字夹具（L1 媒体区为空？）")
        return 3

    n_miss, miss = h1_coverage(items)
    # 可引用（有 substantive 规则挂着）的图
    citable_sha = set()
    for r in jlines(RULES):
        if not is_substantive_rule(r):
            continue
        for im in r.get("image_refs") or []:
            if im.get("sha256"):
                citable_sha.add(im["sha256"])
    citable = [i for i in items if i["sha256"] in citable_sha]
    gap = [i for i in items if i["sha256"] not in citable_sha]
    res = {"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "images": len(items),
           "h1_missing": n_miss, "h1_missing_examples": [(x["record_id"], x["seq"]) for x in miss[:5]],
           "citable_images": len(citable), "no_citable_rule_images": len(gap),
           "no_citable_rule_examples": [(x["record_id"], x["seq"]) for x in gap[:5]],
           "sample": a.sample, "checked": 0, "hit": 0, "miss": [], "controls": {}, "verdict": None}

    if a.selftest:
        # 反向对照 ⑴：把图内文字清空、只留画面读数 ⇒ **不许**判命中
        #   （证明这条判据不是「只要有画面读数就算」）
        it = items[len(items) // 2]
        try:
            doc = run_engine(build_text(it, ocr_override="（无文字）"))
        except Unmeasured as e:
            print("未测：%s" % e)
            return 0
        got = neg_findings(doc)
        ok1 = len(got) == 0
        # 反向对照 ⑵：同一张图**原样**送 ⇒ 必须判命中（否则整条判据恒红）
        try:
            doc2 = run_engine(build_text(it))
        except Unmeasured as e:
            print("未测：%s" % e)
            return 0
        ok2 = len(neg_findings(doc2)) >= 1
        print("  ⑴ 清空图内文字 ⇒ 不命中：%s（实得 %d 条）" % ("✅" if ok1 else "❌", len(got)))
        print("  ⑵ 同图原样送 ⇒ 命中：%s（实得 %d 条）" % ("✅" if ok2 else "❌", len(neg_findings(doc2))))
        print("selftest %s（%d/2）" % ("PASS" if (ok1 and ok2) else "FAIL", int(ok1) + int(ok2)))
        return 0 if (ok1 and ok2) else 3

    pool = citable if citable else items
    picked = pool if a.sample == 0 else random.Random(a.seed).sample(pool, min(a.sample, len(pool)))
    print("=" * 78)
    print("负面样本图 · 飞书侧命中率判据（真引擎）")
    print("=" * 78)
    print("  图片总数 %d ｜ H1 无规则挂载 %d ｜ 有可引用意见的图 %d（%.0f%%）｜ 无可引用意见 %d"
          % (len(items), n_miss, len(citable), 100.0 * len(citable) / max(1, len(items)), len(gap)))
    for it in picked:
        tag = "%s/图%s" % (it["record_id"], it["seq"])
        try:
            doc = run_engine(build_text(it))
        except Unmeasured as e:
            print("  ⚠ %s **未测**：%s" % (tag, e))
            res["verdict"] = "未测"
            if a.write_artifact:
                os.makedirs(os.path.dirname(ARTIFACT), exist_ok=True)
                json.dump(res, open(ARTIFACT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
            return 0
        got = neg_findings(doc)
        junk = [f for f in got if not is_substantive_rule({"rule_kind": "point",
                                                           "rule_text": f.get("history_rule_text")})]
        if junk:
            res.setdefault("junk_findings", []).extend(
                [{"article_no": f.get("article_no"), "text": (f.get("history_rule_text") or "")[:40]}
                 for f in junk])
        res["checked"] += 1
        if got:
            res["hit"] += 1
            classes = {f.get("evidence_class") for f in got}
            print("  ✓ %-28s 意见 %d 条｜证据类 %s" % (tag, len(got), "/".join(sorted(x for x in classes if x))))
        else:
            res["miss"].append({"record_id": it["record_id"], "seq": it["seq"], "ocr_chars": len(it["ocr"])})
            print("  ✗ %-28s **没命中**（图内文字 %d 字）" % (tag, len(it["ocr"])))

    # H3 反向对照：同一批里取一张，把文字换成无关营销文案 ⇒ 意见必须为 0
    if picked:
        ctl = picked[0]
        try:
            doc = run_engine(build_text(ctl, ocr_override=UNRELATED))
            bad = neg_findings(doc)
            res["controls"]["unrelated_text"] = len(bad)
            print("  %s H3 反向对照：无关文案 ⇒ 意见 %d 条（必须 0）"
                  % ("✓" if not bad else "✗", len(bad)))
        except Unmeasured as e:
            print("  ⚠ H3 未测：%s" % e)

    ok = (n_miss == 0 and res["checked"] > 0 and res["hit"] == res["checked"]
          and res["controls"].get("unrelated_text", 0) == 0
          and not res.get("junk_findings"))
    res["verdict"] = "PASS" if ok else "FAIL"
    print("-" * 78)
    print("  读数：抽 %d 张｜命中 %d｜漏 %d｜H1 缺规则 %d｜H3 无关文案误命中 %s｜垃圾正文却进意见 %d"
          % (res["checked"], res["hit"], len(res["miss"]), n_miss,
             res["controls"].get("unrelated_text", "—"), len(res.get("junk_findings") or [])))
    if gap:
        print("  ⚠ 数据缺口：%d 张图**没有可引用的历史意见**（规则只有 observation/brief/@提醒）"
              "—— 这不是引擎漏了，是语料里没有可引用的内容；补法 = 重蒸馏（见 registry）" % len(gap))
    print("%s %s" % ("✅ 通过" if ok else "❌ 未过",
                     "：库内反面案例图发到飞书侧，每张都能命中库内意见" if ok
                     else "：有图发出去拿不到意见（正是 Owner 报的那类问题）"))
    if a.write_artifact:
        os.makedirs(os.path.dirname(ARTIFACT), exist_ok=True)
        json.dump(res, open(ARTIFACT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    if a.json:
        print(json.dumps(res, ensure_ascii=False, indent=1))
    return 0 if ok else 3


if __name__ == "__main__":
    sys.exit(main())
