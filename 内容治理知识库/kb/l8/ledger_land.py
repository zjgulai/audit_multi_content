#!/usr/bin/env python3
"""台账落账（对指定 token 一批）：把「正文已补出、台账还记着读不到」的资源一次对齐。

## 为什么单独有这个脚本（2026-10-08）

用户定的排序是「**先落 L1-L2-L3，台账最后落**」。前三层落完再单独落台账，
是为了避免一个真实风险：**L0 台账的末行会自己成为后续写入的「底本」**。
实测——本轮新下的 7 本 PDF，L0 台账末行是 `no_permission/url_text_refresh_v1`
（那是「wiki 正文直读」那一遍的结论）。若让 OCR 脚本按旧口径自动追加台账，
它会**以 `no_permission` 为底**写新行，把「已有正文」记成「读不到」。
⇒ 所以台账必须**最后单独落**，且落账时要显式给出正确状态，不能沿用末行。

## 口径（两条，都照抄库内既有模式，不自创）

**L1 台账**（`kb/l1/manifest_l1.jsonl`，append-only，45 键契约）
  为每个目标资源追加一行：`status=ok` + 正文指纹 + 字数/段数 + 本次 extractor_version。
  `source_sha256` 记的是**正文指纹**（实测既有行如此：老 OCR 本记的是 OCR 文本 sha，
  不是原件 sha）——原件 sha 另记 L0。

**L0 台账**（`kb/l0/manifest.jsonl`，append-only）
  以前一行（末行）为底，改这些字段，其余原样继承：
    `sha256` = 正文指纹、`sha256_prev` = 原 sha、`sha256_input = pdf_ocr_v1`（既有 OCR 批用的就是它）、
    `sha256_state = full`、`status = updated`、`change = l0_pdf_ocr_text`、
    `observed_at = <RUN>`、`bytes` / `local_path` = 本地原件、
    `status_reason` = 这一次到底发生了什么（含「原来的末行说了什么」）。
  ⚠️ 不改 `sha256_input` 的语义：文本层补出的用 `pdf_text_layer_v1`（本轮新口径，写明出处）。

## 安全

  · **跑前强制归档**两端台账（逐字节 + sha256 双校验，不过即中止，一个字节都不改）；
  · `--apply` 才写；不加只预演；
  · 落账后**回读复核**：逐行确认写进去的内容与预期一致，不一致就报错；
  · 只碰 `--tokens` 点名的资源，**不做全库普查式改写**。

用法：
    python3 kb/l8/ledger_land.py <RUN> --tokens t1,t2,…            # 预演
    python3 kb/l8/ledger_land.py <RUN> --tokens t1,t2,… --apply
"""
# ── 解释器守卫（与 l8 其它脚本同源）──
import os as _os, sys as _sys
if not _os.environ.get("KB_INTERP_OK"):
    _d = _os.path.dirname(_os.path.abspath(__file__)); _cfg = None
    while True:
        _p = _os.path.join(_d, ".kb-python")
        if _os.path.isfile(_p):
            _cfg = _p; break
        _q = _os.path.dirname(_d)
        if _q == _d: break
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

import glob
import hashlib
import json
import os
import shutil
import sys

RUN = next((a for a in sys.argv[1:] if not a.startswith("--")), None)
APPLY = "--apply" in sys.argv
TOKENS = [t for t in (sys.argv[sys.argv.index("--tokens") + 1].split(",") if "--tokens" in sys.argv else []) if t]
PDF_DIR = "kb/l0/attachments/外部资料库"
L1_MAN, L0_MAN = "kb/l1/manifest_l1.jsonl", "kb/l0/manifest.jsonl"

if not RUN or not TOKENS:
    print("用法：ledger_land.py <RUN> --tokens t1,t2,… [--apply]")
    sys.exit(2)


def sha_text(t):
    return hashlib.sha256(t.encode("utf-8")).hexdigest()


def sha_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for b in iter(lambda: fh.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


# ── L1 台账键契约（只许用既有键，不许乱造）──
L1_KEYS = set()
for _l in open(L1_MAN, encoding="utf-8"):
    if _l.strip():
        L1_KEYS |= set(json.loads(_l))

# ── L0 末行（后写覆盖前写）──
lat0 = {}
for _l in open(L0_MAN, encoding="utf-8"):
    if _l.strip():
        _r = json.loads(_l); lat0[_r["resource_key"]] = _r

# ── 找产物 & 组装两行 ──
plan = []
for tok in TOKENS:
    # 匹配口径（2026-10-08 扩）：token 可以出现在**文件名**里（PDF 那批：url__…_<token>.json），
    # 也可以只出现在 **resource_key** 里（单文档那批：key 形如 `docx:<token>` / `wiki:<token>`，
    # 文件名不含 token）。两条都试，避免「产物明明在、却报找不到」。
    art = [f for f in glob.glob("kb/l1/*/*.json") if tok in f and "/_archive/" not in f]
    if not art:
        for f in glob.glob("kb/l1/*/*.json"):
            if "/_archive/" in f:
                continue
            try:
                if tok in (json.load(open(f, encoding="utf-8")).get("resource_key") or ""):
                    art = [f]; break
            except Exception:
                continue
    if not art:
        print(f"  ✗ {tok}：无 L1 产物，跳过"); continue
    d = json.load(open(art[0], encoding="utf-8"))
    text = "".join(s.get("text") or "" for s in (d.get("segments") or []))
    if not text:
        print(f"  ✗ {tok}：产物仍无正文，跳过"); continue
    key = d["resource_key"]
    prev = lat0.get(key)
    if prev is None:
        print(f"  ✗ {tok}：L0 台账无此资源，跳过"); continue
    pdf = None
    for cand in (f"{PDF_DIR}/{tok}.pdf",):
        if os.path.exists(cand):
            pdf = cand
    if pdf is None:
        # 文件名 token 可能截断，退化为前缀匹配
        g = glob.glob(f"{PDF_DIR}/{tok[:24]}*.pdf")
        pdf = g[0] if g else None
    h_text = sha_text(text)
    plan.append({"token": tok, "artifact": art[0], "key": key, "prev": prev,
                 "text_sha": h_text, "chars": len(text), "segs": d.get("segment_count"),
                 "ev": d.get("extractor_version"), "pdf": pdf,
                 "pdf_bytes": os.path.getsize(pdf) if pdf else None,
                 "pdf_sha": sha_file(pdf) if pdf else None,
                 "src": d.get("ocr_pages_source") or d.get("extracted_from") or "unknown",
                 "prev_status": prev.get("status"), "prev_sha_input": prev.get("sha256_input")})

print(f"[{RUN}] 台账落账{'【落盘】' if APPLY else '【干跑】'}｜目标 {len(plan)} 个")
for e in plan:
    print(f"   {e['token'][:30]}")
    print(f"     L1: +1 行 status=ok {e['chars']} 字 / {e['segs']} 段 ev={str(e['ev'])[:34]}")
    print(f"     L0: 末行 {e['prev_status']}/{e['prev_sha_input']} → updated/pdf_*_v1"
          f"｜正文 sha {e['text_sha'][:16]}…｜原件 {e['pdf_bytes']} 字节")

if not APPLY:
    print("\n  [干跑] 未写入。加 --apply 才落账")
    json.dump({"run": RUN, "kind": "ledger_land", "apply": False, "targets": plan},
              open(f"kb/l8/runs/{RUN}-ledger-land.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    sys.exit(0)

# ── ① 归档两端台账（逐字节 + sha256 双校验，不过即中止）──
arch = f"kb/l8/_archive/ledger-land-{RUN}"
os.makedirs(arch, exist_ok=True)
archived = {}
for src in (L1_MAN, L0_MAN):
    dst = os.path.join(arch, os.path.basename(src))
    a = open(src, "rb").read()
    shutil.copyfile(src, dst)
    b = open(dst, "rb").read()
    if a != b or hashlib.sha256(a).hexdigest() != hashlib.sha256(b).hexdigest():
        print(f"⛔ 归档校验不过（{src}）⇒ 中止，一个字节都没改"); sys.exit(2)
    archived[src] = {"archive": dst, "bytes": len(a), "lines": a.count(b"\n"),
                     "sha256": hashlib.sha256(a).hexdigest()}
    print(f"  ① 归档 OK {src} → {dst}（{len(a)} B / {a.count(chr(10).encode())} 行）")

# ── ② 组装两批行 ──
l1_rows, l0_rows = [], []
for e in plan:
    ev = str(e["ev"])
    is_pdf_text = ev.startswith("l1-0.1+pdftext-fill")
    is_api_text = ev.startswith("l1-0.1+feishu-api")
    # 办公文档/在线表格那批：没有本地 PDF ⇒ 走 else 分支（见下面 status_reason 与原件字段）
    is_api_like = ("office" in ev) or ("feishu-api" in ev) or ("feishu_sheets" in str(e.get("src")))
    l1_rows.append({
        "resource_id": e["prev"].get("resource_key"), "resource_key": e["key"],
        "kb_type": e["prev"].get("kb_type"), "source_kind": e["prev"].get("source_kind"),
        "source_sha256": e["text_sha"], "extractor_version": e["ev"], "status": "ok",
        "status_reason": (f"台账补记（{RUN}）：正文由本地 PDF 补出 —— "
                          f"{'文本层抽取' if is_pdf_text else '扫描件 Vision OCR'}，"
                          f"{e['chars']} 字 / {e['segs']} 段；原件 {e['pdf']}（{e['pdf_bytes']} 字节）"
                          if e["pdf"] else
                          f"台账补记（{RUN}）：正文由{'飞书在线表格/文档 API 直读' if is_api_like else '本地办公文档抽取'}读入，"
                          f"{e['chars']} 字 / {e['segs']} 段；资源 {e['key']}"),
        "segment_count": e["segs"], "char_count": e["chars"],
        "media_count": 0, "table_count": 0, "observed_at": RUN, "reconciled_by_run": RUN,
    })
    n = dict(e["prev"])
    n.update({
        "sha256": e["text_sha"], "sha256_prev": e["prev"].get("sha256"),
        "sha256_input": ("pdf_text_layer_v1" if is_pdf_text
                         else ("feishu_api_text_v1" if is_api_text else "pdf_ocr_v1")),
        "sha256_state": "full", "status": "updated", "observed_at": RUN,
        "change": ("l0_pdf_text_layer" if is_pdf_text
                   else ("l0_feishu_api_text" if is_api_text else "l0_pdf_ocr_text")),
        # 原件字段：只有真从本地 PDF 抽的才覆盖；API 直读那批没有本地 PDF，
        # 写成 None 会把上一行有用的值抹掉 ⇒ 保持原值不动。
        **({"bytes": e["pdf_bytes"], "local_path": e["pdf"]} if e["pdf"] else {}),
        "status_reason": (
            f"台账补记（{RUN}）：正文由{'飞书 API 直读（docs +fetch）' if is_api_text else '本地 PDF 补出'}（{'文本层抽取' if is_pdf_text else ('API 正文' if is_api_text else 'Vision OCR 内嵌页图')}，"
            f"{e['chars']} 字 / {e['segs']} 段）。此前末行记的是 "
            f"{e['prev_status']}/{e['prev_sha_input']} —— 那是「wiki 正文直读」那一遍的结论"
            f"（bot 读不到该节点正文），**并不代表取不到内容**：原件一直在本地。"
            f"原件 {e['pdf']}（{e['pdf_bytes']} 字节，sha256 {str(e['pdf_sha'])[:16]}…）未改动。"),
    })
    l0_rows.append(n)

# ── ②b 收窄：L0 末行若**已经**等于本次的正文指纹，就**一个字都不写** ──
#   2026-10-08 改（差点写坏）：单文档那 4 个的 L0 末行是当天补的 `updated/feishu_content_v1`，
#   `sha256` 已等于产物 sha —— 也就是 **L0 侧本来就是对的，缺的只是 L1 台账行**。
#   无条件重写 L0 会：①把准确的 `feishu_content_v1` 降级成我猜的 `feishu_api_text_v1`；
#   ②多出 4 行没有信息量的账。⇒ 只在 L0 与事实不符时才写它。
l0_rows = [n for n in l0_rows if (lat0.get(n["resource_key"], {}).get("sha256") != n["sha256"]
                                   or lat0.get(n["resource_key"], {}).get("status") != n["status"])]
skipped_l0 = len(plan) - len(l0_rows)
if skipped_l0:
    print(f"  [收窄] {skipped_l0} 个资源的 L0 末行已与正文指纹一致 ⇒ **不动 L0**（只补 L1 行）")

# ── ③ 键契约校验 + 写 ──
for r in l1_rows:
    extra = set(r) - L1_KEYS
    assert not extra, f"L1 台账出现新键 {extra}（不许乱造键）"
with open(L1_MAN, "a", encoding="utf-8") as fh:
    for r in l1_rows:
        fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
if l0_rows:
    with open(L0_MAN, "a", encoding="utf-8") as fh:
        for r in l0_rows:
            fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
print(f"  ② 已写：L1 +{len(l1_rows)} 行 ｜ L0 +{len(l0_rows)} 行")

# ── ④ 回读复核 ──
back_l0, back_l1 = {}, {}
for l in open(L0_MAN, encoding="utf-8"):
    if l.strip():
        r = json.loads(l); back_l0[r["resource_key"]] = r
for l in open(L1_MAN, encoding="utf-8"):
    if l.strip():
        r = json.loads(l); back_l1[r["resource_key"]] = r
bad = []
for e in plan:
    r0, r1 = back_l0.get(e["key"]), back_l1.get(e["key"])
    if not r1 or r1.get("source_sha256") != e["text_sha"] or r1.get("status") != "ok":
        bad.append((e["token"], "L1 回读不符"))
    if not r0 or r0.get("sha256") != e["text_sha"] or r0.get("status") != "updated":
        bad.append((e["token"], "L0 回读不符"))
print(f"  ③ 回读复核：{len(plan)*2 - len(bad)}/{len(plan)*2} 项一致"
      + ("" if not bad else f" ｜ ✗ {bad}"))
if bad:
    print("⛔ 回读不一致 ⇒ 请查归档并回滚：cp <archive>/manifest_*.jsonl <原位>"); sys.exit(3)

json.dump({"run": RUN, "kind": "ledger_land", "apply": True, "archived": archived,
           "l1_rows": len(l1_rows), "l0_rows": len(l0_rows), "plan": plan},
          open(f"kb/l8/runs/{RUN}-ledger-land.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print(f"  [报告] kb/l8/runs/{RUN}-ledger-land.json")
print(f"  [回滚] cp {arch}/manifest_l1.jsonl {L1_MAN} && cp {arch}/manifest.jsonl {L0_MAN}")
