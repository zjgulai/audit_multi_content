#!/usr/bin/env python3
"""L0 ↔ 飞书侧全表对账（只读+只报告，不改 L0）。

做什么：
  1) 对每个可达的表，用 base +record-list 全量拉一份 ndjson 快照（默认 bot 身份、只读；
     2026-10-03 起 bot 拿不到的表按 `L8_AS_FALLBACK` 回落用户身份，回落事件写进报告不静默）；
  2) 与 kb/l0/records 下的 L0 记录文件逐条、逐字段比对；
  3) 输出四类差异：only_feishu（飞书有 L0 无）/ only_l0（L0 有飞书无）/ changed（字段值变了）/ same；
  4) 报告同时给「manifest 台账登记情况」—— L0 记录文件存在但 manifest.jsonl 里没有对应行的数量
     （这正是 20260929-1045 对账后遗留的问题）。

不做：不改 kb/l0 任何文件；不下载附件字节；不碰 l1+。
用法：python3 kb/l8/align_l0_feishu.py [RUN]
"""
# ── 解释器守卫（2026-09-29）：不合格就用 kb/.kb-python 指定的解释器重跑自己 ──
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

import collections
import json
import os
import subprocess
import sys
import time

# ── 只读档 · 开关解析（P0-3f · 2026-09-29 补）───────────────────────────────
# `--check` = 只读档：快照落 /tmp、不写报告、四类差异全 0 才退出码 0 —— 供编排器当只读闸门。
# 必须早于 RUN 解析：把开关从 argv 里剔除，避免它被当成位置参数 run_id。
CHECK = "--check" in sys.argv
if CHECK:
    sys.argv.remove("--check")
# ──────────────────────────────────────────────────────────────────────────
RUN = sys.argv[1] if len(sys.argv) > 1 else time.strftime("%Y%m%d-%H%M")
ENV = dict(os.environ, PATH=os.path.expanduser("~/.dsh/bin") + ":" + os.environ.get("PATH", ""))
# 身份可切换：L8_AS=user 走用户身份（刘华丽），默认 bot
AS_ID = os.environ.get("L8_AS", "bot")
PROFILE = os.environ.get("L8_PROFILE", "dsh-kb")
# ── 按表回落（2026-10-03 加）────────────────────────────────────────────────
# 为什么需要：wiki 上挂着那个 Base（`SKkkbdZi9aRuMzs7ob0cpSYHnQg`，节点「OGC内容生产与审核」）
#   ★ 2026-10-06 更正：**bot 现在拿得到了** —— Owner 在飞书侧把守衡加成可阅读协作者后，
#   实测 5 张 L0 源表全部 bot 直读通过（专家修订汇总表 395 行、内容公式 7 行）。
#   下面这段是**当时**的实测（整库级 131006 permission_denied），只作历史读，别再当现状引用。
#   旧记录：bot 拿不到 —— 实测是**整库级** 131006 permission_denied（连 `base +table-list` 都进不去，
#   不是表级），于是那两张表长期 `pull_failed`，L0 永远差 2 张。用户本人（刘华丽）有权限。
# 为什么不干脆全局 `L8_AS=user`：user token **没有 refresh token**（实测 device-flow 明确告警
#   `no refresh_token in response`），到期不续、而且是**静默失效** —— 把 10 张表一起吊在一个
#   会过期的令牌上，换来的正是「日更成功但 L0 全没更新」那一类事故。所以只在**必须**的表上回落。
# 纪律：回落**不许静默** —— 每张表都记 `identity`，回落另记 `identity_fallback`（含首次失败原因），
#   汇总另计一行 `身份回落`。设 `L8_AS_FALLBACK=`（空）即关闭回落。
AS_FALLBACK = os.environ.get("L8_AS_FALLBACK", "user")
# `--check`（只读档）：临时快照落 /tmp → **库内零写点**；默认档仍落 kb/l8/_stage
STAGE = (f"/tmp/kb-l0-align-check/{RUN}" if CHECK else f"kb/l8/_stage/feishu-align/{RUN}")
os.makedirs(STAGE, exist_ok=True)

# 用户指令①：规则库本期不做 → 不在对账范围
TABLES = [
    ("GnRZbIuXraCzf0sGr2UcmZ62nfc", "tbld8qE92YaY38Yz", "负面样本"),
    ("GnRZbIuXraCzf0sGr2UcmZ62nfc", "tblMGtPfe8ZUsEdP", "材料收集"),
    ("GnRZbIuXraCzf0sGr2UcmZ62nfc", "tblZP8jG4tiUL98C", "知识库分类说明"),
    ("Lk3Qb8y2QaVyZns6gprcVNE9nA0", "tblcbk4XiW6471YN", "广告文案明细"),
    ("Lk3Qb8y2QaVyZns6gprcVNE9nA0", "tblD1MiUK1v5fdjD", "品线内容边界规则库"),
    ("Lk3Qb8y2QaVyZns6gprcVNE9nA0", "tblqUTAKFkWheU49", "W1卖点表达边界（品线反馈0910）"),
    ("Lk3Qb8y2QaVyZns6gprcVNE9nA0", "tblLxUfPz4Wqp2na", "风险文案改写建议库（分型号分渠道）"),
    ("N2qkb2YxuatqGLsa4U4cFQxgnCe", "tblGFyycMc45RMga", "数据表"),
    ("SKkkbdZi9aRuMzs7ob0cpSYHnQg", "tbl8AI00JZO1iZtp", "专家修订汇总表"),
    ("SKkkbdZi9aRuMzs7ob0cpSYHnQg", "tblVdl0jdK9G4ld3", "内容公式（仅供参考）"),
]


def canon(v):
    """把字段值归一成可比较的字符串。"""
    return json.dumps(v, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def rid_of_key(k):
    return k.replace(":", "__").replace("/", "_")


# ---------- L0 侧索引 ----------
l0_by_table = collections.defaultdict(dict)   # table_id -> {record_id: (path, doc)}
l0_by_name = collections.defaultdict(dict)    # source_table -> {record_id: (path, doc)}
for root, _dirs, files in os.walk("kb/l0/records"):
    for fn in files:
        if not fn.endswith(".json"):
            continue
        p = os.path.join(root, fn)
        try:
            doc = json.load(open(p, encoding="utf-8"))
        except Exception:
            continue
        rid = doc.get("record_id")
        if not rid:
            continue
        l0_by_table[doc.get("table_id")][rid] = (p, doc)
        l0_by_name[doc.get("source_table")][rid] = (p, doc)

# ---------- manifest 台账索引（最新行取胜） ----------
man_latest = {}
man_rows = 0
for line in open("kb/l0/manifest.jsonl", encoding="utf-8"):
    if not line.strip():
        continue
    man_rows += 1
    r = json.loads(line)
    man_latest[r["resource_key"]] = r
man_record_keys = {k for k, v in man_latest.items() if v.get("source_kind") == "feishu_bitable_record"}

report = {"run": RUN, "tables": {}, "manifest": {}, "summary": {}}
tot = collections.Counter()

def pull(base, tid, snap, as_id):
    """按指定身份拉一份 ndjson 快照。返回 (是否成功, 错误文本)。"""
    p = subprocess.run(
        ["lark-cli", "base", "+record-list", "--base-token", base, "--table-id", tid,
         "--format", "ndjson", "--output", snap, "--overwrite", "--as", as_id, "--profile", PROFILE],
        capture_output=True, text=True, encoding="utf-8", errors="replace", env=ENV, timeout=1800)
    if os.path.exists(snap) and os.path.getsize(snap) > 0:
        return True, ""
    return False, (p.stdout or p.stderr or "")[:300]


for base, tid, name in TABLES:
    snap = f"{STAGE}/{tid}.ndjson"
    ok, err = pull(base, tid, snap, AS_ID)
    ent = {"table": name, "table_id": tid, "base_token": base, "snapshot": snap,
           "identity": AS_ID}

    # ★ 按表回落（2026-10-03 加）：首拉拿不到才换身份，且**把这件事写进报告**。
    #   先删掉可能写了一半的快照再重拉 —— 否则残件非 0 字节，会被下面当成成功。
    if not ok and AS_FALLBACK and AS_FALLBACK != AS_ID:
        try:
            if os.path.exists(snap):
                os.unlink(snap)
        except OSError:
            pass
        ok2, err2 = pull(base, tid, snap, AS_FALLBACK)
        if ok2:
            ok = True
            ent["identity"] = AS_FALLBACK
            ent["identity_fallback"] = {"from": AS_ID, "to": AS_FALLBACK, "first_error": err}
            tot["identity_fallback"] += 1
            print(f"[身份回落] {name} {tid}: {AS_ID} 拿不到 → {AS_FALLBACK} 成功"
                  f"（首次失败：{err[:80]}）")
        else:
            err = f"{AS_ID}: {err} ｜ {AS_FALLBACK}: {err2}"

    if not ok:
        ent["status"] = "pull_failed"
        ent["error"] = err
        report["tables"][tid] = ent
        tot["pull_failed"] += 1
        print(f"[拉取失败] {name} {tid}: {ent['error'][:120]}")
        continue

    fs = {}
    for line in open(snap, encoding="utf-8"):
        if not line.strip():
            continue
        r = json.loads(line)
        rid = r.get("record_id") or r.get("recordId")
        if rid:
            fs[rid] = r
    l0 = l0_by_table.get(tid) or l0_by_name.get(name) or {}

    only_feishu = sorted(set(fs) - set(l0))
    only_l0 = sorted(set(l0) - set(fs))
    changed = []
    same = 0
    for rid in sorted(set(fs) & set(l0)):
        fvals = {k: v for k, v in fs[rid].items() if k not in ("record_id", "recordId")}
        # ── 批次13 修正（CD-1）：**两侧用同一套键归一**，不许只剥一边 ──────────────
        # 原缺陷（批次13 实测，L0 闸门长期红的直接原因）：
        #   上一行把飞书快照的 `record_id` **剥掉**，而 L0 记录文件的 `fields` 字典**含 `record_id`**
        #   （`write_record` 用 `fields_of()` 的字段表建 `fields`，其中含 `record_id`，值 = 该记录 id）。
        #   下面 `set(fvals) | set(lvals)` 比并集 ⇒ `canon(None) != canon("recvw…")`
        #   ⇒ **每条记录恒判「值变」**。实测：负面样本 170 条 + 材料收集 22 条，
        #   业务字段差异 **0**，却报出 `值变 192`，把 L0 闸门顶成「真差异 2 / exit=1」。
        # 修法：L0 侧同样排除 record_id/recordId（它是身份键不是字段值；
        #   真正的身份比对由上面的 `set(fs) & set(l0)` 负责，那里已经比过了）。
        # 影响面：只影响**共有记录**的值比较；only_feishu / only_l0 / pull_failed 一律不变。
        lvals = {k: (fd or {}).get("value")
                 for k, fd in (l0[rid][1].get("fields") or {}).items()
                 if k not in ("record_id", "recordId")}
        # 只比字段名交集 + 双方都在的字段；字段名差异单列
        diffs = {}
        for k in set(fvals) | set(lvals):
            if canon(fvals.get(k)) != canon(lvals.get(k)):
                diffs[k] = {"feishu": fvals.get(k), "l0": lvals.get(k)}
        if diffs:
            changed.append({"record_id": rid, "fields": diffs})
        else:
            same += 1

    ent.update({
        "status": "ok",
        "feishu_records": len(fs),
        "l0_records": len(l0),
        "same": same,
        # ★ 2026-10-01 改：原先写 `only_feishu[:50]` / `only_l0[:50]` / `changed[:20]` ——
        #   **静默截断**：计数报真值（如 55）而列表只给 50，且没有任何标记说明截断了。
        #   实测后果：`kb/l8/ingest_l0_new_records.py` 消费 `only_feishu_ids` →
        #   **静默漏掉第 51 条以后的记录**（本次实测漏 5 条，无一报错、无一告警）。
        #   这与本库反复栽的「静默降级」同类 —— **看不见的丢失比看得见的失败更危险**。
        #   改法：**不截断**（本次最大表 170 条，无体量顾虑），并把清单策略显式声明出来，
        #   再加 `ids_truncated` 布尔供闸门判 —— 将来若恢复上限，至少它是可见的。
        "only_feishu": len(only_feishu),
        "only_feishu_ids": only_feishu,
        "only_l0": len(only_l0),
        "only_l0_ids": only_l0,
        "changed": len(changed),
        "changed_detail": changed,
        "list_policy": {"note": "2026-10-01 起不截断；如需恢复上限，必须同步写 ids_truncated 与上限值"},
        "ids_truncated": False,
    })
    report["tables"][tid] = ent
    for k in ("same", "only_feishu", "only_l0", "changed"):
        tot[k] += ent[k]
    print(f"[{name}] 飞书={len(fs)} L0={len(l0)} 一致={same} 飞书多={len(only_feishu)} L0多={len(only_l0)} 值变={len(changed)}")
    # ★ 2026-10-19：把「只有飞书有」的**记录 id 与快照路径**也交出去（零写，只走 stdout）。
    #   为什么：`l0_gate.py` 要判的是「这几条是不是**都被 filter 排除**」，不是「一共几条」——
    #   条数只是那个判据的**影子**；源侧多一条未审核材料，影子就变，闸门就假红
    #   （2026-10-18 周更正是这么停在 L0 的）。一行 JSON + `ensure_ascii` ⇒ 表名带空格也不会被拆错。
    print("[only-feishu-ids] " + json.dumps(
        {"table": name, "tid": tid, "snap": snap, "ids": list(only_feishu)}, ensure_ascii=True))

# ---------- manifest 登记对账 ----------
# 注意：resource_key 有两种形态 —— 入口 Base 的表用 bitable:<table_id>:<record_id>，
# 其它 Base 用 bitable:<base_token>:<record_id>。所以按 (table_id, record_id) 建索引比对，
# 不要按拼出来的 key 字符串匹配（否则会在非入口 Base 上误报未登记）。
rec_row = {}
for k, v in man_latest.items():
    if v.get("source_kind") == "feishu_bitable_record" and v.get("record_id"):
        rec_row[(v.get("table_id"), v["record_id"])] = v
unregistered = collections.Counter()
for tid, ent in report["tables"].items():
    if ent.get("status") != "ok":
        continue
    for rid in (l0_by_table.get(tid) or {}):
        m = rec_row.get((tid, rid))
        if m is None or m.get("status") in ("gone", "retracted"):
            unregistered[tid] += 1
report["manifest"] = {
    "manifest_rows_raw": man_rows,
    "manifest_resource_keys": len(man_latest),
    "manifest_active": sum(1 for v in man_latest.values() if v.get("status") not in ("gone", "retracted")),
    "record_files_not_registered": dict(unregistered),
    "record_files_not_registered_total": sum(unregistered.values()),
}
report["summary"] = dict(tot)
out = None if CHECK else f"kb/l8/runs/{RUN}-l0-align.json"
if out:
    json.dump(report, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("\n=== 汇总 ===")
print(f"  一致 {tot['same']} | 飞书多 {tot['only_feishu']} | L0多 {tot['only_l0']} | 值变 {tot['changed']} | 拉取失败 {tot['pull_failed']} | 身份回落 {tot['identity_fallback']}")
print("  manifest 未登记的 L0 记录文件:", report["manifest"]["record_files_not_registered_total"],
      report["manifest"]["record_files_not_registered"])
print("  报告:", out if out else "（--check 只读档：不写报告，库内零写点）")
if CHECK:
    # 只读档判据：四类差异（含拉取失败）全 0 → 0；否则 1（编排器据此判「只读闸门 未过」）
    diff_total = (tot["only_feishu"] + tot["only_l0"] + tot["changed"] + tot["pull_failed"])
    if diff_total:
        print("  ❌ 只读闸门未过：四类差异合计 %d（飞书多 %d / L0多 %d / 值变 %d / 拉取失败 %d）"
              % (diff_total, tot["only_feishu"], tot["only_l0"], tot["changed"], tot["pull_failed"]))
        _sys.exit(1)
    print("  ✅ 只读闸门通过：四类差异全 0（一致 %d）" % tot["same"])
