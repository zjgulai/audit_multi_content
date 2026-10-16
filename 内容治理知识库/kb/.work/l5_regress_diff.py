# -*- coding: utf-8 -*-
"""L5 P0 表变更的**影响面差分跑台**（不是自测抽样，是全语料逐条比对）。

为什么要有它（2026-10-10 建）：
  每次往 P0 表里加/改模式，都必须回答两个问题 ——
    · **有没有把原来拦得住的变成拦不住？**（漏放回归，最坏的一类）
    · **有没有在真实素材上多拦？多拦的是不是误伤？**
  只跑 `matcher.py --selftest` 答不了：自测只有十几条构造句，覆盖不到真实语料
  （实测教训：2026-10-10 中文否定式里的裸 `无` 造成 H02/H07 漏放，自测能抓到，
   但「影响面有多大」必须靠本跑台）。

跑法：
    python3 kb/.work/l5_regress_diff.py                 # 全语料 · 三张表差分
    python3 kb/.work/l5_regress_diff.py --corpus prod   # 只看生产送审单

三张表（把「谁改的」分离开，不混成一句「表变了」）：
    T0  = 变更前快照  默认 kb/l5/runs/<RUN>.p0_patterns.superseded.jsonl（--base 指定）
    T0' = 现表去掉指定码（默认 M03）—— 用来把「本次加的那个码」单独摘出去
    T1  = 现表 kb/l5/p0_patterns.jsonl
  于是：T0→T0' 量的是「除该码以外的改动」，T0'→T1 量的是「该码本身」。

四套语料：
    gold  = 金标评测集文字题（桌面 xlsx 的 A 表）
    ads   = kb/l2/units.jsonl 里 #广告文案明细/ 的**真实投放文案**（去重）
    prod  = kb/l7/reports/*.review.md 里「## 送审内容」代码块 = **生产上真正审过的素材**
    all   = 以上合并

判据：只认「有没有命中」这一层（命中即 BLOCK），与引擎三态无关 —— 这是 P0 层这一把尺子。
      **丢命中必须为 0**；新增命中要逐条看是不是误伤。
"""
import argparse, glob, importlib.util, json, os, re, sys, tempfile

KB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))          # …/kb
ROOT = os.path.dirname(KB)                                                # 库根
CUR = os.path.join(KB, "l5/p0_patterns.jsonl")

spec = importlib.util.spec_from_file_location("l5_matcher", os.path.join(KB, "l5/matcher.py"))
M = importlib.util.module_from_spec(spec); spec.loader.exec_module(M)


def _by_code(rows, code):
    return [r for r in rows if (r.get("rule_code") or "") != code]


def _write(rows, name):
    p = os.path.join(tempfile.gettempdir(), name)
    with open(p, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
    return p


def corpus_gold():
    try:
        import openpyxl
    except Exception:
        return []
    p = os.path.expanduser("~/Desktop/内容治理知识库-金标评测集-20261009.xlsx")
    if not os.path.exists(p):
        return []
    ws = openpyxl.load_workbook(p)["A-文字题-预期答案（40）"]
    return [(str(ws.cell(r, 1).value), ws.cell(r, 3).value)
            for r in range(2, ws.max_row + 1) if ws.cell(r, 3).value]


def corpus_ads():
    out, seen = [], set()
    fp = os.path.join(KB, "l2/units.jsonl")
    if not os.path.exists(fp):
        return []
    for line in open(fp, encoding="utf-8"):
        if not line.strip():
            continue
        u = json.loads(line)
        if not (u.get("anchor") or "").startswith("#广告文案明细"):
            continue
        t = (u.get("text") or "").strip()
        if len(t) < 8 or t in seen:
            continue
        seen.add(t)
        out.append((u.get("unit_id"), t))
    return out


def corpus_prod():
    out = []
    for f in sorted(glob.glob(os.path.join(KB, "l7/reports/*.review.md"))):
        try:
            txt = open(f, encoding="utf-8", errors="replace").read()
        except Exception:
            continue
        m = re.search(r"##\s*送审内容\s*\n+```[^\n]*\n(.*?)\n```", txt, re.S)
        if m and len(m.group(1).strip()) >= 4:
            out.append((os.path.basename(f), m.group(1).strip()))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=None, help="变更前的 P0 表快照（T0）")
    ap.add_argument("--code", default="M03", help="本次新增/改动的 rule_code（T0' 会把它摘掉）")
    ap.add_argument("--corpus", default="all", choices=("all", "gold", "ads", "prod"))
    ap.add_argument("--show", type=int, default=25, help="每条新增命中最多打印几例")
    a = ap.parse_args()

    if not a.base:
        cand = sorted(glob.glob(os.path.join(KB, "l5/runs/*.p0_patterns.superseded.jsonl")),
                      key=os.path.getmtime, reverse=True)
        if not cand:
            print("✗ 找不到变更前快照（kb/l5/runs/*.p0_patterns.superseded.jsonl），请用 --base 指定")
            return 2
        a.base = cand[0]
    cur = [json.loads(l) for l in open(CUR, encoding="utf-8") if l.strip()]
    T0 = M.compile_patterns(a.base)
    T0p = M.compile_patterns(_write(_by_code(cur, a.code), "l5_regress_nocode.jsonl"))
    T1 = M.compile_patterns(CUR)
    print("T0  = %s（%d 条模式）" % (os.path.relpath(a.base, ROOT), len(T0)))
    print("T0' = 现表摘掉 %s（%d 条）" % (a.code, len(T0p)))
    print("T1  = 现表（%d 条）\n" % len(T1))

    sets = {"gold": corpus_gold(), "ads": corpus_ads(), "prod": corpus_prod()}
    if a.corpus != "all":
        sets = {a.corpus: sets[a.corpus]}
    else:
        sets["ALL"] = [x for v in sets.values() for x in v]

    rc = 0
    for name, corpus in sets.items():
        if not corpus:
            print("【%s】语料为空，跳过\n" % name)
            continue
        lost, add_fix, add_code = [], [], []
        for key, text in corpus:
            c0 = bool(M.match(text, T0)); c0p = bool(M.match(text, T0p)); c1 = bool(M.match(text, T1))
            if c0 and not c0p:
                lost.append((key, text))
            if not c0 and c0p:
                add_fix.append((key, text))
            if not c0p and c1:
                hits = [h for h in M.match(text, T1) if h.get("rule_code") == a.code]
                terms = sorted({mm["pattern"] for h in hits for mm in h["matched"]})
                add_code.append((key, text, terms))
        print("=" * 92)
        print("【%s】%d 条 | 现表命中 %d" % (name, len(corpus),
              sum(1 for _, t in corpus if M.match(t, T1))))
        print("  ❗丢命中（T0 命中 → 现表不命中）：%d  %s" % (len(lost), "✅" if not lost else "❌ 必须修"))
        for k, t in lost[:a.show]:
            print("      %s | %r" % (k, t[:70]))
        print("  ▲除 %s 外的改动带来的新增拦截：%d" % (a.code, len(add_fix)))
        for k, t in add_fix[:a.show]:
            print("      %s | %r" % (k, t[:70]))
        print("  ▲%s 带来的新增拦截：%d" % (a.code, len(add_code)))
        for k, t, terms in add_code[:a.show]:
            print("      %s | %-28s | %r" % (k, ",".join(terms), t[:60]))
        if lost:
            rc = 1
        print()
    print("结论：%s" % ("❌ 存在丢命中（漏放回归）" if rc else "✅ 丢命中 0；新增拦截数见上，需逐条判是否误伤"))
    return rc


if __name__ == "__main__":
    sys.exit(main())
