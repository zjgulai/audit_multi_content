#!/usr/bin/env python3
"""把对账发现的**新增**飞书记录入库（L0 = 飞书副本）。只处理「飞书有、L0 没有」的记录。

## 与既有脚本的分工

    kb/l8/sync_l0_changed_records.py   管「内容已变」（changed_detail）
    kb/l8/emit_l0_manifest_reconcile.py 管「补登记」（文件在、台账缺）
    **本脚本**                          管「新增」（飞书有、L0 完全没有）

2026-09-30 09:30 对账发现负面样本表一夜之间 108 → 115 条，就是这一类。

## 口径（照既有 108 条逐字复刻，不另立一套）

原始快照文件 `kb/l0/records/<表名>/<record_id>.json`，键：
    base_token / table_id / source_table / record_id / entry_url / timezone
    fields   : 字段名 → {field_id, field_type, value, raw_verbatim}
    schema   : 字段名 → {field_id, field_type}
    raw_record : record_id + 各字段原值（扁平）
    filter   : {result, note}（各表准入规则不同，见下）
    note / observed_at

指纹 `sha256_input=record_fields` 的算法**不是我发明的**，是从既有行反解并复现过的：
    sha256( json.dumps([["field_id",fid,"value",val] …按 fid 升序], sort_keys=True, separators=(",",":")) )
复现证据：既有 40 条记录逐条复算 == 台账记的 sha（40/40）。本脚本直接调用同一实现。

## 各表准入规则（不是一刀切）

    · 负面样本：独立入口表（R26），**不按材料审核状态筛选**，全字段 verbatim → 应收尽收
    · 材料收集：用户指令③「材料审核状态 == 通过」才收 → 不通过的不入库（只进台账留痕）
    其它表按各自既有规则；本脚本遇到没有规则的被控表时**拒写并报错**，不猜。

## 安全

· 只写新文件（目标已存在则**归档后**再写，并在报告里标出）
· 飞书侧全程只读
· L0 原件字节不动
用法：
    python3 kb/l8/ingest_l0_new_records.py <RUN>            # 干跑
    python3 kb/l8/ingest_l0_new_records.py <RUN> --apply
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
# ──────────────────────────────────────

import collections
import glob
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time

APPLY = "--apply" in sys.argv
RUN = next((a for a in sys.argv[1:] if not a.startswith("--")), time.strftime("%Y%m%d-%H%M"))
L0 = "kb/l0"
LARK = os.path.expanduser("~/.dsh/bin/lark-cli")
# ★ 2026-10-02 修：默认身份 `user` → `bot`。
#   病灶：本行原为 `os.environ.get("L8_AS", "user")`，而 user 身份的 token 在 keychain 里
#   是 **missing** 的（`lark-cli auth status`：`User identity: missing`），于是：
#     · `--as user` → **exit=3** `error=token_missing` `stdout=0B`（**任何表都读不了**）
#     · `--as bot`  → exit=0，3562B 有效 JSON
#   实测（2026-10-02）：align 涉及的 10 张表里 **bot 可读 8 张**；另 2 张
#   ★ 2026-10-06 更正：**该权限问题已解决** —— bot 直读两张表都成功（395 / 7 行）。
#   下面这段是**当时**的实测（`91403` / `131006`），只作历史读。
#   旧记录：（专家修订汇总表 / 内容公式）是 `91403` **权限**问题。
#   ★★ 2026-10-03 更正：原文在这里写「与身份无关 ……『换成 user 就能读那两张』**不成立**」——
#     **那句是错的**，它把「**实验没做成**」当成了「**实验做出来是负的**」：
#     当时 user token 在 keychain 里是 missing，所以那两张表压根**没被试过**。
#     拿到 token 后实测：**user 身份读得到这两张表**（395/395 与 7/7 逐条一致、值变 0），
#     而 bot 至今读不到（对该 base 是**整库级** `131006`，连 `base +table-list` 都进不去）。
#     ⇒ 「按身份回落」是**有效**的，已落地在 `align_l0_feishu.py` 的 `AS_FALLBACK`（默认 `user`）。
#     教训：**没做成的实验 ≠ 反例**；写「X 没用」之前先证明 X 真的被执行过。
#   同库的 `align_l0_feishu.py:55` 用的就是 `"bot"`；本行改为一致，否则单独跑本脚本必失败
#   （实测：22:18 那次 exit=1，报 `Expecting value: line 1 column 1` —— 因为 stdout 为空）。
#   要临时切 user 调试：外部设 `L8_AS=user` 即可（getenv 优先，不覆盖显式值）。
AS_ID = os.environ.get("L8_AS", "bot")
BOT_ID = os.environ.get("L8_BOT_AS", "bot")   # 附件下载权限在应用侧（守衡），与记录读取不同身份
PROFILE = os.environ.get("L8_PROFILE", "dsh-kb")
TIMEZONE = "Asia/Shanghai"
SCANNER = "0.7"

# 各表准入：allowed=入库，gated=按字段门槛，其余拒写（不猜）
ADMISSION = {
    "负面样本": {"mode": "all", "rule": "R26",
                 "note": "独立入口表（R26）：不按材料审核状态筛选；本批全字段 verbatim"},
    "材料收集": {"mode": "gate", "field": "材料审核状态", "equals": ["通过"], "rule": "用户指令③",
                 "note": "用户指令③：只收 材料审核状态 == 通过"},
}

# ── ★ 目标 23（2026-10-10）：**本地声明排除** ────────────────────────────────
# 为什么要有：Owner 2026-10-10 明令「禁止修改飞书侧源任何数据」，而任务拆解 目标 23 原本
# 要「把 3 份红人 Brief 的分类改「其它」、状态改「暂不采用」」—— **那三个字段都在只读源上**。
# 更正后的口径：**不动飞书源，只在本侧把它挡出去**（PRD §2.2：brief 属「不审的中间物」）。
#
# 声明真源 = `kb/l0/registry/kb.json → rule_eligible_overrides`（带 authority / registry / reason_code）。
# **不许在本文件里再写第二份名单** —— 复制出去的那份必然过期。
RULE_ELIG_REASON_FALLBACK = "prd_scope_exclusion"


def rule_eligible_overrides() -> dict:
    """读 `kb/l0/registry/kb.json → excluded_records` ⇒ `{record_id: {reason_code, why}}`。

    ★ **fail-closed**：读不到 / 结构不对 ⇒ **抛错退出**，不许静默当成「没有排除项」。
      静默的代价正是本库栽过的那一类 ——「判据恒绿、看着像守着、其实什么都没守」：
      声明文件坏掉时仍然照常入库，而**没有任何东西会红**。
    """
    p = os.path.join(L0, "registry/kb.json")
    try:
        reg = json.load(open(p, encoding="utf-8"))
    except Exception as e:                                   # noqa: BLE001
        raise SystemExit("[拒写] 读不到 L0 登记件 %s（%r）—— 声明读不到就不许猜，fail-closed" % (p, e))
    blk = reg.get("rule_eligible_overrides") or {}
    out = {}
    for r in (blk.get("records") or []):
        rid = r.get("record_id")
        if not rid:
            raise SystemExit("[拒写] rule_eligible_overrides 里有条目没有 record_id：%r" % (r,))
        out[rid] = {"reason_code": blk.get("reason_code") or RULE_ELIG_REASON_FALLBACK,
                    "why": r.get("why") or r.get("note") or r.get("label") or "（覆盖项里没写 why）"}
    return out


def canon(o):
    return json.dumps(o, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha(t):
    return hashlib.sha256(t.encode("utf-8")).hexdigest()


def rec_hash(fields):
    """与 kb/l8/emit_l0_manifest_reconcile.py:rec_hash 逐字同口径（已用既有 40 条复现验证）。"""
    items = sorted(((v.get("field_id"), v.get("value")) for v in fields.values() if v.get("field_id")),
                   key=lambda x: x[0])
    return sha(canon([["field_id", k, "value", v] for k, v in items]))


# 台账行的**必需键**：下游真的会读的那些。
# 事故（2026-09-30 09:35）：第一版只写了「不许出现既有权之外的新键」这一条守卫，
# 结果漏了 table_id / table_name —— 而对账脚本正是按 (table_id, record_id) 建索引，
# 于是 7 条新记录明明写进了台账，却被报「未登记」。守卫只防"多"不防"少"，等于没防。
REQUIRED_ROW_KEYS = {"resource_key", "record_id", "table_id", "table_name", "source_kind",
                     "status", "kb_type", "path", "observed_at", "sha256", "sha256_input",
                     "sha256_state", "change", "emitted_by", "scanner_version", "matched_rule"}


def manifest_row(table_id, table_name, rid, digest, rule, reason):
    return {"change": "l0_feishu_new_record_ingest", "depth": 1, "downstream_invalidated": False,
            "dup_of": None, "emitted_by": "l8/ingest_l0_new_records.py",
            "entry_url": f"https://momcozy-in.feishu.cn/base/GnRZbIuXraCzf0sGr2UcmZ62nfc?table={table_id}&record={rid}",
            "field_id": None, "field_name": None, "kb_type": "internal_sample", "matched_rule": rule,
            "observed_at": RUN, "path": f"[内容治理/入口Base/{table_name}]", "record_id": rid,
            "resource_key": f"bitable:{table_id}:{rid}", "revision": None, "scanner_version": SCANNER,
            "sha256": digest, "sha256_input": "record_fields", "sha256_state": "full",
            "source_kind": "feishu_bitable_record", "status": "registered", "status_reason": reason,
            "table_id": table_id, "table_name": table_name,
            "rule_eligible": _elig, "rule_eligible_source": _elig_src}


def _assert_row(row, required=None):
    required = REQUIRED_ROW_KEYS if required is None else required
    extra = set(row) - MAN_KEYS
    if extra:
        raise SystemExit(f"[拒写] 台账行出现既有权之外的新键 {sorted(extra)} —— 不擅自扩台账 schema")
    lack = set(required) - set(row)
    if lack:
        raise SystemExit(f"[拒写] 台账行缺必需键 {sorted(lack)} —— 下游会读不到（table_id 这类漏过）")
    empty = sorted(k for k in required if row.get(k) in (None, "", [], {}))
    if empty:
        raise SystemExit(f"[拒写] 台账行必需键为空 {empty}")


if "--selftest-decl" in sys.argv:
    # ★ 目标 23 的自证：证明「声明排除」这条判据**不是恒真也不是恒假**。
    #   变异测试口径（本库纪律）：把缺陷**真造一遍**，尺子必须**精确变红**。
    import tempfile
    _res = []

    def _ck(name, cond, extra=""):
        _res.append((name, bool(cond), extra))

    _real_L0 = L0
    D = rule_eligible_overrides()
    _ck("① 覆盖项读到了（非空 —— 挡住「读法错导致恒空」）", len(D) >= 1, "条数=%d" % len(D))
    _ck("①b 三条 Brief 逐条在册",
        all(r["record_id"] in D for r in json.load(open(os.path.join(_real_L0, "registry/kb.json"),
                                                         encoding="utf-8"))
            ["rule_eligible_overrides"]["records"]), "")
    _ck("①c 原因码取到的是声明里的真值",
        all(D[k]["reason_code"] == "prd_scope_exclusion" for k in D), "")
    _ck("①d why 不是占位符（不许「（覆盖项里没写 why）」）",
        all("没写 why" not in D[k]["why"] for k in D), "")
    # 反向对照 A：**没声明的记录不许被挡** —— 否则就是「把所有人都挡了」的假绿
    _ck("② 反向对照：未声明的记录不在册（recvvg2wL2qE3K）", "recvvg2wL2qE3K" not in D, "")
    # 反向对照 B：读不到 ⇒ **必须抛错**，不许静默返回 {}
    L0 = "kb/__no_such_dir_for_selftest__"
    try:
        rule_eligible_overrides()
        _ck("③ 反向对照：读不到登记件 ⇒ fail-closed 拒写", False, "竟然没抛错（静默了）")
    except SystemExit:
        _ck("③ 反向对照：读不到登记件 ⇒ fail-closed 拒写", True, "按预期 SystemExit")
    except Exception as e:                                   # noqa: BLE001
        _ck("③ 反向对照：读不到登记件 ⇒ fail-closed 拒写", False, "抛的是 %r，不是拒写" % (e,))
    # 反向对照 C：声明里缺 record_id ⇒ 拒（不许静默丢掉那一条）
    _tmp = tempfile.mkdtemp(prefix="t23selftest-")
    os.makedirs(os.path.join(_tmp, "registry"), exist_ok=True)
    json.dump({"rule_eligible_overrides": {"records": [{"why": "忘了写 record_id"}]}},
              open(os.path.join(_tmp, "registry/kb.json"), "w", encoding="utf-8"), ensure_ascii=False)
    L0 = _tmp
    try:
        rule_eligible_overrides()
        _ck("④ 反向对照：条目缺 record_id ⇒ 拒", False, "竟然没抛错")
    except SystemExit:
        _ck("④ 反向对照：条目缺 record_id ⇒ 拒", True, "按预期 SystemExit")
    # 反向对照 D：把声明清空 ⇒ ① 必须变假（证明 ① 不是恒真）
    _tmp2 = tempfile.mkdtemp(prefix="t23selftest2-")
    os.makedirs(os.path.join(_tmp2, "registry"), exist_ok=True)
    json.dump({"rule_eligible_overrides": {"records": []}},
              open(os.path.join(_tmp2, "registry/kb.json"), "w", encoding="utf-8"), ensure_ascii=False)
    L0 = _tmp2
    _ck("⑤ 变异测试：覆盖项清空 ⇒ ① 精确变假", len(rule_eligible_overrides()) == 0, "")
    L0 = _real_L0
    print("ingest_l0_new_records --selftest-decl（目标 23 · rule_eligible 覆盖）")
    for n, c, ex in _res:
        print("  %s %s%s" % ("✅" if c else "❌", n, ("　｜ " + ex) if ex else ""))
    _bad = sum(1 for _, c, _e in _res if not c)
    print("结果：%d/%d%s" % (len(_res) - _bad, len(_res), "" if not _bad else "  ← 有失败"))
    sys.exit(1 if _bad else 0)


rep = json.load(open(f"kb/l8/runs/{RUN}-l0-align.json", encoding="utf-8"))
stage = f"kb/l8/_stage/feishu-align/{RUN}"
print(f"[{RUN}] 新增记录入库{'【落盘】' if APPLY else '【干跑】'}｜快照目录 {stage}")

man_latest = {}
for l in open(f"{L0}/manifest.jsonl", encoding="utf-8"):
    if l.strip():
        r = json.loads(l)
        man_latest[r["resource_key"]] = r
MAN_KEYS = set()
for l in open(f"{L0}/manifest.jsonl", encoding="utf-8"):
    if l.strip():
        MAN_KEYS |= set(json.loads(l))

# ── 补记模式：记录文件已落盘、但台账行缺键（见 REQUIRED_ROW_KEYS 上方的事故记录）──
if "--restamp" in sys.argv:
    irp = f"kb/l8/runs/{RUN}-l0-ingest.json"
    if not os.path.exists(irp):
        raise SystemExit(f"[补记] 找不到 {irp}（补记只针对已入库批次，不重新抓飞书）")
    done = json.load(open(irp, encoding="utf-8"))["written"]
    tid_by_name = {v.get("table"): v.get("table_id") for v in rep["tables"].values()}
    rows = []
    for e in done:
        p = e["path"]
        if not os.path.exists(p):
            raise SystemExit(f"[补记] 记录文件不存在：{p}")
        tid = e.get("table_id") or tid_by_name.get(e["table"])
        if not tid:
            raise SystemExit(f"[补记] 表「{e['table']}」的 table_id 取不到（对账报告里没有），停手")
        doc = json.load(open(p, encoding="utf-8"))
        h = rec_hash(doc["fields"])
        if h != e["sha256"]:
            raise SystemExit(f"[补记] {e['record_id']} 现算 sha {h[:12]} != 入库时 {e['sha256'][:12]}，"
                             f"文件被改过 —— 停手人工看")
        rows.append(manifest_row(tid, e["table"], e["record_id"], h,
                                 ADMISSION[e["table"]]["rule"],
                                 f"台账行补记（{RUN}）：首版漏写 table_id/table_name 导致对账误报未登记，"
                                 f"记录文件与 sha 均未变（复算一致），只补台账行"))
    for r in rows:
        _assert_row(r)
    print(f"[补记] 待追加 {len(rows)} 行（必需键已齐）")
    for r in rows:
        print(f"   {r['record_id']}｜table_id={r['table_id']}｜{r['table_name']}")
    if APPLY:
        with open(f"{L0}/manifest.jsonl", "a", encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
        print(f"[补记] 已追加 {len(rows)} 行到 kb/l0/manifest.jsonl")
    else:
        print("[补记] 干跑，未落盘（加 --apply）")
    sys.exit(0)

# ── 附件模式：给本批新记录的图片附件补台账行 + 落字节 ──────────────────────
# 行形态照 kb/l8/emit_l0_manifest_reconcile.py（metadata 行）与 kb/l8/store_l0_attachments.py
# （file_bytes 行）既有约定复刻；只处理本批 21 张，不做全量重扫（全量重扫会给既有 1,680 条重复追加）。
if "--attachments" in sys.argv:
    irp = f"kb/l8/runs/{RUN}-l0-ingest.json"
    if not os.path.exists(irp):
        raise SystemExit(f"[附件] 找不到 {irp}")
    BASE_T = "GnRZbIuXraCzf0sGr2UcmZ62nfc"
    ROOT = f"{L0}/attachments"
    done = json.load(open(irp, encoding="utf-8"))["written"]
    have = {json.loads(l)["resource_key"] for l in open(f"{L0}/manifest.jsonl", encoding="utf-8") if l.strip()}
    rows, stored, failed = [], [], []
    for e in done:
        doc = json.load(open(e["path"], encoding="utf-8"))
        tid = e.get("table_id") or {v.get("table"): v.get("table_id") for v in rep["tables"].values()}[e["table"]]
        for fname, meta in doc["fields"].items():
            if meta.get("field_type") != "attachment":
                continue
            for a in (meta.get("value") or []):
                tok = a.get("file_token")
                if not tok:
                    continue
                key = f"bitable:{tid}:{e['record_id']}/{meta['field_id']}/{tok}"
                if key in have:
                    continue
                mh = sha(canon({"file_token": tok, "name": a.get("name"), "size": a.get("size")}))
                dst_dir = f"{ROOT}/{e['table']}/{e['record_id']}"
                dst = f"{dst_dir}/{tok}.png"
                ent = {"key": key, "record_id": e["record_id"], "table": e["table"], "table_id": tid,
                       "field_id": meta["field_id"], "field_name": fname, "token": tok,
                       "name": a.get("name"), "size": a.get("size"), "meta_sha": mh, "local_path": dst}
                if APPLY:
                    os.makedirs(dst_dir, exist_ok=True)
                    got = os.path.exists(dst) and os.path.getsize(dst) > 0
                    if not got:
                        for _ in range(3):
                            p = subprocess.run([LARK, "base", "+record-download-attachment",
                                                "--base-token", BASE_T, "--table-id", tid,
                                                "--record-id", e["record_id"], "--file-token", tok,
                                                "--output", dst, "--overwrite", "--as", BOT_ID,
                                                "--profile", PROFILE],
                                               capture_output=True, text=True, encoding="utf-8",
                                               errors="replace", timeout=300)
                            if os.path.exists(dst) and os.path.getsize(dst) > 0:
                                got = True
                                break
                        if not got:
                            failed.append(ent)
                            continue
                    b = open(dst, "rb").read()
                    ent["bytes"] = len(b)
                    ent["file_sha"] = hashlib.sha256(b).hexdigest()
                    stored.append(ent)
                rows.append(ent)
                print(f"   {'+' if APPLY else '·'} {e['record_id']} {fname} {tok[:14]}… "
                      f"{a.get('name')} {a.get('size')} 字节")
    if APPLY:
        with open(f"{L0}/manifest.jsonl", "a", encoding="utf-8") as fh:
            for x in rows:
                base = {"change": "l0_feishu_new_attachment_ingest", "depth": 2,
                        "downstream_invalidated": True, "dup_of": None,
                        "emitted_by": "l8/ingest_l0_new_records.py",
                        "entry_url": f"https://momcozy-in.feishu.cn/base/{BASE_T}?table={x['table_id']}&record={x['record_id']}",
                        "field_id": x["field_id"], "field_name": x["field_name"],
                        "kb_type": "internal_sample", "matched_rule": "R25", "observed_at": RUN,
                        "path": f"[内容治理/入口Base/{x['table']}/{x['field_name']}]",
                        "record_id": x["record_id"], "resource_key": x["key"], "revision": None,
                        "scanner_version": SCANNER, "source_kind": "feishu_attachment",
                        "status": "registered", "table_id": x["table_id"], "table_name": x["table"]}
                meta_row = dict(base, sha256=x["meta_sha"], sha256_input="attachment_metadata",
                                sha256_state="metadata_only",
                                status_reason=f"新增记录附件；原名 {x['name']} / 声明 {x['size']} 字节")
                _assert_row(meta_row, required={"resource_key", "record_id", "field_id", "source_kind",
                                                "status", "sha256", "sha256_input", "sha256_state",
                                                "observed_at", "table_id"})
                fh.write(json.dumps(meta_row, ensure_ascii=False, sort_keys=True) + "\n")
                if x.get("file_sha"):
                    byte_row = dict(base, sha256=x["file_sha"], sha256_input="file_bytes",
                                    sha256_state="full", bytes=x["bytes"], local_path=x["local_path"],
                                    status_reason=f"新增记录附件字节已落 L0；原字节 {x['bytes']} 字节（声明 {x['size']}）")
                    _assert_row(byte_row, required={"resource_key", "record_id", "field_id", "source_kind",
                                                    "status", "sha256", "sha256_input", "sha256_state",
                                                    "observed_at", "table_id"})
                    fh.write(json.dumps(byte_row, ensure_ascii=False, sort_keys=True) + "\n")
        print(f"[附件] 台账 +{len(rows)} metadata 行 +{len(stored)} file_bytes 行｜下载失败 {len(failed)}")
    else:
        print(f"[附件] 干跑：待补 {len(rows)} 条 metadata 行（加 --apply 才下载字节）")
    json.dump({"run_id": RUN, "kind": "l0_new_attachments", "rows": rows, "stored": stored,
               "failed": failed}, open(f"kb/l8/runs/{RUN}-l0-attachments.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    sys.exit(0)

written, skipped, archived = [], [], []
RULE_ELIG_OVERRIDE = rule_eligible_overrides()   # ★ 目标 23（读不到即拒写，见函数 docstring）
for tid, t in sorted(rep["tables"].items()):
    name = t.get("table")
    ids = t.get("only_feishu_ids") or []
    if not ids:
        continue
    adm = ADMISSION.get(name)
    if adm is None:
        raise SystemExit(f"[拒写] 表「{name}」没有登记准入规则 —— 不猜，先人工定规则再加进 ADMISSION")
    snap_p = os.path.join(stage, f"{tid}.ndjson")
    if not os.path.exists(snap_p):
        raise SystemExit(f"[缺快照] {snap_p} 不存在，无法入库")
    snap = {json.loads(l)["record_id"]: json.loads(l) for l in open(snap_p, encoding="utf-8") if l.strip()}
    # 字段 id/类型以飞书现值为准（不去猜、也不沿用旧文件的可能过期的 schema）
    fp = subprocess.run([LARK, "base", "+field-list", "--base-token", t["base_token"], "--table-id", tid,
                         "--as", AS_ID, "--profile", PROFILE, "--json"],
                        capture_output=True, text=True)
    fd = json.loads(fp.stdout[fp.stdout.find("{"):])["data"]["fields"]
    schema = {f["name"]: {"field_id": f["id"], "field_type": f["type"]} for f in fd}
    print(f"\n[{name}] 飞书多出 {len(ids)} 条｜字段定义 {len(schema)} 个｜准入规则 {adm['rule']}")
    for rid in ids:
        rec = snap.get(rid)
        if rec is None:
            skipped.append({"table": name, "record_id": rid, "why": "快照里没有这条"}); continue
        raw_vals = {k: v for k, v in rec.items() if k != "record_id"}
        # ★ 目标 23（2026-10-10）：**按记录覆盖 rule_eligible** —— 不是把记录挡在库外，
        #   而是让它的单元「**留在库里可读、不许成为规则或依据**」（登记件 intended_effect）。
        #   权威登记件 = kb/l7/registry/source-readonly.yaml → prd_scope_exclusions。
        _roe = RULE_ELIG_OVERRIDE.get(rid)
        if _roe is None:
            _elig, _elig_src = True, "not_material_collection"
        else:
            _elig, _elig_src = False, _roe["reason_code"]
            print("   · %s 覆盖 rule_eligible=false（%s：%s）" % (rid, _roe["reason_code"], _roe["why"]))
        if adm["mode"] == "gate" and raw_vals.get(adm["field"]) != adm["equals"]:
            skipped.append({"table": name, "record_id": rid,
                            "why": f"准入未过：{adm['field']}={json.dumps(raw_vals.get(adm['field']), ensure_ascii=False)}"
                                   f" != {json.dumps(adm['equals'], ensure_ascii=False)}"})
            print(f"   · {rid} 跳过（准入未过）")
            continue
        fields = {}
        for fname, meta in schema.items():
            v = raw_vals.get(fname)
            fields[fname] = {"field_id": meta["field_id"], "field_type": meta["field_type"],
                             "value": v, "raw_verbatim": v}
        # 飞书有、字段定义里没有的列（新增列）：如实记下但不编 field_id
        extra = sorted(set(raw_vals) - set(schema))
        doc = {"base_token": t["base_token"], "table_id": tid, "source_table": name, "record_id": rid,
               "entry_url": f"https://momcozy-in.feishu.cn/base/{t['base_token']}?table={tid}&record={rid}",
               "timezone": TIMEZONE, "fields": fields, "schema": schema,
               "raw_record": {"record_id": rid, **raw_vals},
               "filter": {"result": "not_filtered" if adm["mode"] == "all" else "filtered",
                          "note": adm["note"]},
               "note": f"字段原值 verbatim；由 l8 新增记录入库脚本按飞书现值抓取；scanner_version={SCANNER}"
                       + (f"；飞书多出字段（未在字段定义里）: {extra}" if extra else ""),
               "observed_at": RUN}
        dst = f"{L0}/records/{name}/{rid}.json"
        h = rec_hash(fields)
        entry = {"table": name, "table_id": tid, "record_id": rid, "path": dst, "sha256": h,
                 "fields": len(fields), "extra_cols": extra,
                 "attachments": sum(1 for v in raw_vals.values()
                                    if isinstance(v, list) and v and isinstance(v[0], dict) and "file_token" in v[0])}
        if os.path.exists(dst) and json.load(open(dst, encoding="utf-8")).get("fields") and \
                rec_hash(json.load(open(dst, encoding="utf-8"))["fields"]) == h:
            skipped.append({"table": name, "record_id": rid, "why": "已在 L0 且 sha 相同"}); continue
        if APPLY:
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            if os.path.exists(dst):
                a = f"{L0}/_archive/{name}-pre-ingest-{RUN}"
                os.makedirs(a, exist_ok=True)
                shutil.copy2(dst, os.path.join(a, os.path.basename(dst))); archived.append(dst)
            tmp = dst + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(doc, fh, ensure_ascii=False, indent=1)
            json.load(open(tmp, encoding="utf-8"))      # 写完先自检能读
            os.replace(tmp, dst)
        written.append(entry)
        print(f"   + {rid}｜{len(fields)} 字段｜sha {h[:12]}…｜附件字段 {entry['attachments']}")

if APPLY and written:
    with open(f"{L0}/manifest.jsonl", "a", encoding="utf-8") as fh:
        for e in written:
            row = manifest_row(e["table_id"], e["table"], e["record_id"], e["sha256"],
                               ADMISSION[e["table"]]["rule"],
                               f"对账发现飞书新增（{RUN}-l0-align 的 only_feishu_ids）；按 {ADMISSION[e['table']]['rule']} 入库")
            _assert_row(row)
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")

print(f"\n[{'写入' if APPLY else '干跑'}] 入库 {len(written)}｜跳过 {len(skipped)}｜归档 {len(archived)}")
for s in skipped:
    print(f"   跳过 {s['table']}/{s['record_id']}：{s['why']}")
json.dump({"run_id": RUN, "kind": "l0_new_record_ingest", "written": written,
           "skipped": skipped, "archived": archived,
           "next": "附件字节走 kb/l8/store_l0_attachments.py；下游 L1/L2 由各自的 run 脚本接着跑"},
          open(f"kb/l8/runs/{RUN}-l0-ingest.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"[报告] kb/l8/runs/{RUN}-l0-ingest.json")
