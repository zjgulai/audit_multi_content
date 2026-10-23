#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""negative_rule_probe.py —— 「守衡收到一张图」这条路的**端到端探针**（只读）。

它按守衡收图的同一顺序做三件事，然后给出「命中哪条负面样本规则、什么问题、什么建议」：

    ① 本机 OCR（`kb/.work/ocr.jxa.js`，macOS Vision）      → 图内文字
    ② 画面读数（守衡 `agent/scene.mjs`，deepseek-flash 吃图） → 结构化读数
    ③ 规则匹配（`kb/l8/negative_rule_match.py`）             → N-1.x 命中 + 分数 + 理由

为什么要有这个探针
──────────────────
目标写的是「@守衡 发任一图片 → 命中知识库里的负面样本规则」。
那条链横跨两个仓（守衡 runtime + 本库），**没有一个能重复的读数**就只能靠"试一次"。
本探针把「图 → 文字+画面 → 规则」这一段变成一条命令，产出 JSON，可回归。

用法
────
  python3 kb/l8/negative_rule_probe.py --image <path> [--top 5] [--json]
退出码：0 = 有命中 ｜ 2 = 无命中（**这不是"没问题"，只是"没相似历史意见"**）｜ 3 = 取数失败
"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
WS = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)
import negative_rule_match as M  # noqa: E402


def ocr(path):
    out = os.path.join(tempfile.mkdtemp(prefix="probe-ocr-"), "ocr.json")
    subprocess.run(["osascript", "-l", "JavaScript", "kb/.work/ocr.jxa.js", out, path],
                   capture_output=True, text=True, timeout=300)
    if not os.path.exists(out):
        return ""
    data = json.load(open(out, encoding="utf-8"))
    return "\n".join(l.get("text", "") for l in (data[0].get("lines") or []) if l.get("text"))


def scene(path):
    """走守衡的 scene.mjs；它只收 /tmp 下的图 ⇒ 复制一份临时副本，用完即删。"""
    script = r"""
const { sceneRead } = await import('/Users/lute/Project/audit_multi_content/tools/agent/scene.mjs');
const r = await sceneRead(process.argv[1]);
console.log(JSON.stringify(r));
"""
    tmpdir = tempfile.mkdtemp(prefix="probe-scene-")
    ext = os.path.splitext(path)[1] or ".png"
    tmp = os.path.join(tmpdir, "img" + ext)
    try:
        subprocess.run(["/bin/cp", path, tmp], check=True)
        p = subprocess.run(["node", "--input-type=module", "-e", script, tmp],
                           capture_output=True, text=True, timeout=180, cwd="/tmp")
        try:
            return json.loads(p.stdout.strip().splitlines()[-1])
        except Exception:
            return {"ok": False, "error": (p.stderr or p.stdout)[-300:]}
    finally:
        try:
            os.unlink(tmp); os.rmdir(tmpdir)
        except OSError:
            pass


def main(argv):
    path = None
    top = 5
    as_json = "--json" in argv
    for i, a in enumerate(argv):
        if a == "--image" and i + 1 < len(argv):
            path = argv[i + 1]
        elif a == "--top" and i + 1 < len(argv):
            top = int(argv[i + 1])
    if not path or not os.path.exists(path):
        print("用法：negative_rule_probe.py --image <path> [--top N] [--json]")
        return 3
    text = ocr(path)
    sc = scene(path)
    scn = sc.get("scene") if isinstance(sc, dict) and sc.get("ok") else None
    hits = M.match(text, scn, top=top)
    res = {"image": path, "ocr_chars": len(text), "scene_ok": bool(scn),
           "scene": scn, "hits": hits, "count": len(hits)}
    if as_json:
        print(json.dumps(res, ensure_ascii=False, indent=1))
    else:
        print("图内文字 %d 字 ｜ 画面读数 %s" % (len(text), "ok" if scn else "失败"))
        if not hits:
            print("无命中（注意：无命中 ≠ 合规，只表示库里没有相似的历史审核意见）")
        for h in hits:
            print("─" * 60)
            print("[%s] %s ｜ 分数 %.2f（画面 %.2f / 文字 %.2f）"
                  % (h["article_no"], h["rule_code"], h["score"], h["visual_score"], h["text_score"]))
            print("  问题：%s" % h["rule_text"])
            act = h.get("action") or {}
            if act.get("kind") == "replace" and act.get("replacement"):
                print("  建议：%s" % act["replacement"])
            else:
                print("  建议：禁止 / 打回（源记录未给改法）")
            if h["reasons"]:
                print("  命中理由：%s" % "；".join(h["reasons"][:4]))
            ev = (h.get("evidence") or [{}])[0]
            if ev.get("record_id"):
                print("  回源：https://momcozy-in.feishu.cn/base/GnRZbIuXraCzf0sGr2UcmZ62nfc"
                      "?table=tbld8qE92YaY38Yz&record=%s" % ev["record_id"])
    return 0 if hits else 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
