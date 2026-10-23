#!/usr/bin/env python3
"""只读归因探针：把「③ 引擎(含发布) 里那 20–40 s 非证据装配」拆成可指的几段。

做法：**不改知识库一个字节**——用 importlib 把 `with_kb_evidence.py` 当模块载进来，
在**本进程内**给它的模块级函数套一层计时（`run()` 里的名字都是运行时查 globals，
所以打桩生效），然后调一次 `run()`：

  · `write_report=False` ⇒ 依据层走 `--dry-run`（不落报告文件）
  · `_PUBLISHING=False`  ⇒ 不发飞书、不发业务号（content_id 退回指纹）
  · 画面读数直接拼进正文（与守衡真实送来的材料同形），负样本层照常启得起来

不复用 `review_run.sh`：那条路会重写 `kb/.work/last_review_result.json`
（守衡只认的旁挂，AGENTS.md 写死不许动）。

用法：
  python3 test/_lat/engine_seg_probe.py [--image PATH] [--repeat N]
"""
import argparse
import importlib.util
import json
import os
import sys
import time

KB_ROOT = os.environ.get("SHOUHENG_KB_ROOT") or (
    "/Users/lute/Documents/skill-test/执行skills/执行skills/skills-回归测试/知识库/内容治理")
ENGINE = os.path.join(KB_ROOT, "kb/l7/review-engine/core/with_kb_evidence.py")

# 这一单的材料取自 2026-10-22 03:26 那次真实图片送审（5 分 42 秒那单）的
# 报告附录「机读素材读数」——OCR 逐行碎片 + 画面读数，逐字照抄，没有改写。
OCR_BLOCK = """Mistake 03
Sharing
your bed
The baby can be trapped，
covered by bedding, or
accidentally rolled onto by
parents.
AAP Recommendation
Share Your Room，
not your bed
Keep baby in their own
crib or bassinet nearby
parents' bed for at least
thefirst 6months."""

SCENE_BLOCK = """- 场景：卧室
- 人物：右上 · 成人 · 侧躺闭眼睡觉，手臂放在被子上；右上 · 婴幼儿 · 穿连体衣戴帽子躺着，旁边有奶嘴 · 睡眠场景：是；睡姿：仰卧 · 姿势依据：脸朝上，躯干正面朝上，四肢摊开；右下 · 成人 · 侧躺闭眼睡觉，手放在头旁；右下 · 婴幼儿 · 躺在婴儿床里，四肢抬起 · 睡眠场景：是；睡姿：仰卧 · 姿势依据：脸朝上，躯干正面朝上，四肢朝上
- 物品：婴儿床（正在被使用）（朝向：正放）；奶嘴（朝向：看不清）；小盆栽（朝向：正放）
- 可见标识：有文字，认不清
- 图上文字用的是什么文字：英文
- 画面线索：右上画面中婴幼儿与成人同床躺着；右下画面中婴幼儿躺在婴儿床内；画面多处有半透明水印文字
- 读数自报看不清的：水印文字内容认不清；奶嘴的具体朝向看不清"""

MARKS = []
CHILDREN = []


def load_engine():
    spec = importlib.util.spec_from_file_location("kb_with_evidence_probe", ENGINE)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["kb_with_evidence_probe"] = mod
    spec.loader.exec_module(mod)
    return mod


def wrap(mod, name):
    orig = getattr(mod, name, None)
    if orig is None:
        return

    def timed(*a, **kw):
        t0 = time.time()
        try:
            return orig(*a, **kw)
        finally:
            MARKS.append((name, round((time.time() - t0) * 1000, 1)))
    setattr(mod, name, timed)


def wrap_subprocess(mod):
    orig = mod.subprocess.run

    def timed(cmd, *a, **kw):
        t0 = time.time()
        try:
            return orig(cmd, *a, **kw)
        finally:
            label = os.path.basename(str(cmd[0]) if not isinstance(cmd, str) else cmd.split()[0])
            tail = [x for x in (cmd[1:] if isinstance(cmd, list) else str(cmd).split()[1:])
                    if x.startswith("--")]
            CHILDREN.append({"child": label, "flags": tail[:6],
                             "ms": round((time.time() - t0) * 1000, 1)})
    mod.subprocess.run = timed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", default=os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "work", "A_baby_face.png"))
    ap.add_argument("--repeat", type=int, default=1)
    args = ap.parse_args()

    if not os.path.exists(ENGINE):
        print("找不到引擎：%s" % ENGINE)
        return 2
    img = os.path.abspath(args.image)
    if not os.path.exists(img):
        print("找不到图片：%s" % img)
        return 2

    text = SCENE_BLOCK + "\n\n" + OCR_BLOCK
    for i in range(args.repeat):
        mod = load_engine()
        mod._PUBLISHING = False                  # 不发飞书、不发业务号
        wrap_subprocess(mod)
        for fn in ("_evidence_findings", "decide", "scan_text", "kb_hits_of",
                   "_to_risk_item", "_auto_content_id"):
            wrap(mod, fn)
        MARKS.clear()
        CHILDREN.clear()
        t0 = time.time()
        res, err = mod.run(text, content_type="image", images=[img], write_report=False)
        total = round((time.time() - t0) * 1000, 1)
        print("=" * 78)
        print("第 %d 次｜run() 总 %s ms｜err=%r" % (i + 1, total, err))
        if res is None:
            return 2
        d = res.get("decision") or {}
        em = res.get("evidence_meta") or {}
        print("结论 %s｜findings %s｜risk_items %d" % (
            d.get("state"), em.get("findings"), len(d.get("risk_items") or [])))
        print("engine trace.perf：", json.dumps((em.get("trace") or {}).get("perf") or {}, ensure_ascii=False))
        print("-- 段（本进程计时）--")
        agg = {}
        for name, ms in MARKS:
            agg[name] = agg.get(name, 0) + ms
        covered = 0.0
        for name, ms in sorted(agg.items(), key=lambda x: -x[1]):
            print("  %-20s %9.1f ms" % (name, ms))
            covered += ms
        print("  %-20s %9.1f ms  ← 上面几段合计（子段可能是嵌套的）" % ("Σ", covered))
        print("-- 子进程 --")
        for c in sorted(CHILDREN, key=lambda x: -x["ms"]):
            print("  %-24s %9.1f ms  %s" % (c["child"], c["ms"], " ".join(c["flags"])))
        print("  子进程合计 %.1f ms" % sum(c["ms"] for c in CHILDREN))
    return 0


if __name__ == "__main__":
    sys.exit(main())
