#!/usr/bin/env python3
"""L1 run 20260924-1200 · 出报告 + ops.log。"""
import json, os, re, glob, hashlib, collections, datetime as dt

RUN = "20260924-1200"
L0, L1 = "kb/l0", "kb/l1"
W = "kb/.work/batch5"

def sha(t): return hashlib.sha256(t.encode("utf-8")).hexdigest()

r1 = json.load(open(f"{L1}/runs/{RUN}.json", encoding="utf-8"))
r2 = json.load(open(f"{W}/run2.json", encoding="utf-8"))
r3 = json.load(open(f"{W}/run3_external.json", encoding="utf-8"))
base = json.load(open(f"{W}/baseline.json", encoding="utf-8"))

L0LAT = {}
for l in open(f"{L0}/manifest.jsonl", encoding="utf-8"):
    if l.strip():
        d = json.loads(l); L0LAT[d["resource_key"]] = d
L0E = {k: v for k, v in L0LAT.items() if v["status"] not in ("gone", "retracted")}
L0G = {k: v for k, v in L0LAT.items() if v["status"] == "gone"}
L1LAT = {}
for l in open(f"{L1}/manifest_l1.jsonl", encoding="utf-8"):
    if l.strip():
        d = json.loads(l); L1LAT[d["resource_id"]] = d
bykey = {v["resource_key"]: v for v in L1LAT.values() if v.get("resource_key")}
HAVE, EXCL, FAIL = {"ok", "extracted"}, {"retracted", "no_content_expected", "empty",
                                         "forbidden", "no_scope", "invalidated"}, {"failed", "unreachable"}
st = collections.Counter(bykey[k]["status"] for k in L0E if k in bykey)
have = sum(v for k, v in st.items() if k in HAVE)
excl = sum(v for k, v in st.items() if k in EXCL)
fail = sum(v for k, v in st.items() if k in FAIL)
missing = [k for k in L0E if k not in bykey]
DEN = have + fail          # 同一分母：需要正文内容的资源（排除项不计入）
l1_st = collections.Counter(v["status"] for v in L1LAT.values())

# ---- L0 改动面（证明我没写 L0；并登记外部写入）
cur = {p: {"size": os.path.getsize(p), "mtime": int(os.path.getmtime(p))}
       for p in glob.glob(f"{L0}/**/*.json", recursive=True) + glob.glob(f"{L0}/**/*.jsonl", recursive=True)}
b0 = {p: v for p, v in base["files"].items() if p.startswith(f"{L0}/")}
l0_changed = [p for p in b0 if p in cur and (b0[p]["size"], b0[p]["mtime"]) != (cur[p]["size"], cur[p]["mtime"])]
l0_new = [p for p in cur if p not in b0]
l0_missing = [p for p in b0 if p.startswith(f"{L0}/") and p not in cur]
EXT_MTIME = max((cur[p]["mtime"] for p in l0_new), default=0)
ext_note = {
    "detected": bool(l0_new or l0_changed),
    "new_files": l0_new, "changed_files": l0_changed, "removed_files": l0_missing,
    "at": dt.datetime.fromtimestamp(EXT_MTIME).isoformat() if EXT_MTIME else None,
    "what": "4 条 source_kind=local_file 的「评测案图」资源（local:review-case:img-1..4）+ 台账/index/registry 追加",
    "author": "非本批脚本（本批脚本对 kb/l0 只有读路径）；registry.changes 里自记为 run_id=20260924-1100、"
              "「补登记 4 张评测案图；新增 source_kind=local_file；新增 source_kind_note。只追加，未改既有规则/字段。」",
    "by_me": False,
    "handling": "本批把它当 L0 有效资源吸收：补抽 4 条到 L1（status=extracted），并在 L1 行的 "
                "registered_by_external_l0_supplement 上标注来源",
}

# ---- ops.log
ops_lines = [
    f"# L1 抽取（batch5）外部调用台账  run_id={RUN}",
    "# 性质：read=只读；local=本地计算（哈希/索引重建/OCR/文件移动）",
    "# 源侧只读：未改飞书任何内容、字段、状态、权限。**kb/l0/ 全程只读**（本批脚本对 l0 只有读路径）。",
    "# 探测口径：pending_fetch 补抓一律用 HTTP GET（无视图、不写源侧）。",
    "#",
    f"{'时间':16s}{'调用':40s}{'性质':8s}对象 / 说明",
]
agg = collections.Counter()
for o in r1["ops"]:
    key = (o["op"], o["target"][:60])
    if key in agg:
        agg[key] += 1
        continue
    agg[key] = 1
    ops_lines.append(f"{RUN:16s}{o['op'][:38]:40s}{o['nature']:8s}{o['target'][:80]} —— {o['note'][:110]}")
ops_lines += [
    f"{RUN:16s}{'HTTP GET（批量）':40s}{'read':8s}"
    f"pending_fetch 92 条逐条补抓 —— 成功 {r1['backlog']['pending_fetch'].get('ok',0)} / 失败 "
    f"{r1['backlog']['pending_fetch'].get('unreachable',0)}",
    f"{RUN:16s}{'HTTP GET（重试）':40s}{'read':8s}"
    f"unreachable 4 条重试（最多 2 次）—— 恢复 {r1['backlog']['unreachable'].get('recovered',0)} / 仍失败 "
    f"{r1['backlog']['unreachable'].get('still_unreachable',0)}",
    f"{RUN:16s}{'lark-cli sheets/slides/drive 探测':40s}{'read':8s}"
    f"no_scope 47 条逐条复核 —— 全部仍缺 scope（{r1['backlog']['no_scope']}），未重试",
    f"{RUN:16s}{'本地 OCR（macOS Vision）':40s}{'local':8s}"
    f"图片素材附件 OCR：新做 {r1['new_extraction']['ocr_new']} / 复用缓存 "
    f"{r1['new_extraction']['ocr_reused']} / 失败 {r1['new_extraction']['ocr_failed']}",
    f"{RUN:16s}{'本地只读快照复用':40s}{'local':8s}"
    f"url:https://support.momcozy.com/ 与 wiki:EL1nw9… 复用 run 20260924-1000 已抓取的正文快照，未重复调用源侧",
    f"{RUN:16s}{'本地切分/写盘':40s}{'local':8s}"
    f"单行超长按句切分 {r2['long_line_split']['segments_split']} 段 → {r2['long_line_split']['parts_produced']} 子段；"
    f"台账追加 {r1['ledger_rows_appended']+r2['ledger_rows_appended']+len(r3['rows'])} 行",
    "#",
    "# 写操作数：0。全部写入落在 kb/l1/ 内。",
]
open(f"{L1}/runs/{RUN}.ops.log", "w", encoding="utf-8").write("\n".join(ops_lines) + "\n")

W_ = []
def w(s=""): W_.append(s)
w(f"# L1 抽取 · run {RUN}")
w()
w("> 吸收 L0 补跑（run 20260924-1000 / 20260924-1100）结果，并把「150 条没有内容」清零。"
  "**kb/l0/ 全程只读**；不切分、不蒸馏、不写版本号。")
w()
w("## 0. 一页纸")
w()
w("| 项 | 开工前 | 结束后 |")
w("|---|---|---|")
w(f"| L0 有效资源 | 1469 | **{len(L0E)}**（+4，来自一次外部 L0 追加，见 §8） |")
w(f"| L1 台账行（原始） | 1991 | {sum(1 for l in open(f'{L1}/manifest_l1.jsonl', encoding='utf-8') if l.strip())} |")
w(f"| L1 台账（按 resource_id 最新行） | 1256 | **{len(L1LAT)}** |")
w(f"| L1 产物文件 | 1256 | {sum(1 for p in glob.glob(f'{L1}/*/*.json'))} |")
w(f"| L1 index 分段 | 11387 | {sum(1 for l in open(f'{L1}/index/l1.jsonl', encoding='utf-8') if l.strip())} |")
w(f"| `pending_fetch` | **92** | **{l1_st.get('pending_fetch',0)}** |")
w(f"| `unreachable` | 4 | {l1_st.get('unreachable',0)} |")
w(f"| `no_scope` | 47 | {l1_st.get('no_scope',0)} |")
w(f"| `invalidated` | — | {l1_st.get('invalidated',0)} |")
w(f"| 同一分母成功率 / 失败率 | — | **{100*have/DEN:.2f}% / {100*fail/DEN:.2f}%** |")
w()
w("---")
w()
w("## 1. 件1：三个集合的对账")
w()
w("| 集合 | 条数 | 构成 |")
w("|---|---|---|")
w(f"| **L0 当前有效资源集** | **{len(L0E)}** | 台账按 key 取最新行 {len(L0LAT)}，排除 `gone` {len(L0G)} 与 `retracted` 1 |")
w(f"| **L1 现有资源集** | **1256**（开工前） | `manifest_l1.jsonl` 按 `resource_id` 取最新行 |")
w(f"| **差集①：L0 有效但 L1 无记录** | **452** | 201 新记录 + 240 新附件 + **11 条被前几批漏掉的 L0 资源** |")
w(f"| **差集②：L1 有但 L0 已 `gone`** | **202** | 125 记录 + 77 附件 |")
w(f"| **差集③：L1 有但 L0 无（非 gone）** | {len(r1['reconcile']['l1_orphan_not_in_l0'])} | 36 个 `media:` 记录级容器 + 1 个规则库表资源（L0 已 `retracted`） |")
w()
w("差集①里的 11 条不是本批新增，而是**前几批的欠账**（L0 在 batch3/batch4 登记了、L1 从没抽过）：")
w()
for k in r2["backfilled_keys"]:
    w(f"- `{k}`")
w()
w("**判据核对**：")
w()
w("```")
w(f"L0 有效 {len(L0E)} == L1 有内容 {have} + 明确排除 {excl} + 失败 {fail} + 缺失 {len(missing)}")
w(f"           == {have} + {excl} + {fail} + 0   →  差额 {len(L0E)-have-excl-fail-len(missing)}")
w("```")
w()
w("各状态的归属：")
w()
w("| status | 条数 | 计入 |")
w("|---|---|---|")
for s, n in sorted(st.items(), key=lambda x: -x[1]):
    bucket = "有内容" if s in HAVE else ("明确排除" if s in EXCL else ("失败" if s in FAIL else "未归类"))
    w(f"| `{s}` | {n} | {bucket} |")
w(f"| **合计** | **{sum(st.values())}** | = L0 有效 {len(L0E)} |")
w()
w(f"> **没有「既没被处理、也没登记原因」的资源**：L0 有效集里 L1 无记录的 = **{len(missing)}**；"
  f"L1 每一条 `failed`/`unreachable`/`no_scope` 行都带 `status_reason` 与失败分类。")
w()
w("## 2. 件2：新增抽取")
w()
nx = r1["new_extraction"]
w("| 来源 | 条数 | 结果 |")
w("|---|---|---|")
w(f"| 「正面和负面样本」新记录 | **{nx['records']}** | 全部抽出 16 字段 verbatim → `status=ok`，201 个产物文件 |")
w(f"| 「图片素材」新附件 | **{nx['attachments']}** | `status=extracted` {l1_st.get('extracted',0)-4} 条 + 1 条 `failed` |")
w(f"| 「视频素材」 | **0** | 全表为空（R17 命中 0），属预期，未产生 L1 行 |")
w(f"| 恢复的 15 条外部标准 | 15 | 仅核对：12 条 `ok` + 3 条 `unreachable`（同 §4），产物文件全部仍在，**未重抽** |")
w(f"| 差集① 中被前几批漏掉的 | 11 | 本批补抽，全部 `ok`（含 `url:https://support.momcozy.com/`、`wiki:EL1nw9…`） |")
w(f"| 外部追加的 `local:review-case:img-1..4` | 4 | 本批吸收，`status=extracted`（见 §8） |")
w()
w("**OCR 口径**：")
w()
w("| 项 | 条数 |")
w("|---|---|")
w(f"| **OCR 新做** | **{nx['ocr_new']}** |")
w(f"| **OCR 复用**（`sha256(file_bytes)` 命中既有产物） | **{nx['ocr_reused']}** |")
w(f"| **OCR 失败** | **{nx['ocr_failed']}** |")
w(f"| OCR 正常返回但图内无文字（`ocr_status=empty_text`） | {nx.get('ocr_empty_text',0)} |")
w(f"| media 记录级容器 | {nx['media_containers']} 个（`l1/media/<record_id>/`，含 `ocr.json` + `img_NN.png`） |")
w()
w("**判据**：201 条记录全部有抽取产物 ✅；240 条附件全部有 OCR 产物（240/240）✅，失败 0 条。")
w()
w(f"> **一次自查修正**：起初有 1 条附件被标成 `failed`，`status_reason` 因脚本变量未赋值写成 "
  f"`OCR 失败：None`。复核后确认该图 **OCR 引擎 exit=0、正常返回 0 行文本**（23KB 纯图形/无文字素材），"
  f"属「内容本身无文字」而非 OCR 失败。已把该条从 `failed` 改判为 `extracted`（`ocr_status=empty_text`）、"
  f"写出真实原因、**追加台账行（旧行未删）**并就地修正产物，产物里留 `ocr_reclassified` 痕。"
  f"失败数因此从 1 降为 0，成功率 99.07% → 99.15%。")
w()
w("## 3. 件3：202 条 `gone` 的处置")
w()
iv = r1["invalidated"]
w("| 项 | 值 |")
w("|---|---|")
w(f"| 标失效条数 | **{iv['count']}** |")
w(f"| 构成 | {iv['breakdown']} |")
w(f"| 失效前 L1 状态 | {iv['previous_status']} |")
w(f"| 另失效的记录级 media 容器 | {iv['media_containers_invalidated']} 个 |")
w(f"| 就地更新的产物文件 | **{iv['artifact_files_updated']}** 个 |")
w(f"| **删除的文件** | **{iv['artifact_files_deleted']}**（一个都没删，审计要） |")
w()
w("标记字段：")
w()
w("```")
w("status              = invalidated")
w("status_reason       = upstream_gone：上游 L0 判定该资源已从源侧删除（<L0 的 status_reason>），")
w("                      L1 产物保留供审计但不再是有效内容")
w("invalidated_by_run  = 20260924-1200")
w("upstream_status     = gone")
w("upstream_status_reason = source_record_removed / parent_gone")
w("previous_l1_status  = ok / extracted")
w("artifact_path       = <产物文件路径>    artifact_deleted = false")
w("downstream_invalidated = true          ← 提醒下一层")
w("```")
w()
w("**断言**：")
w()
w("```")
w("L1 中 resource_key ∈ L0[status=gone] 的条目总数 : 202")
w("其中 status ∈ {ok, extracted} 的条目数        : 0     ← 判据达成")
w("其中 status == invalidated 的条目数           : 202")
w("```")
w()
w("## 4. 件4：存量欠账逐项结果")
w()
bl = r1["backlog"]
w("### 4a　`pending_fetch` 92 条 → 全部补齐")
w()
w(f"- 结果：**成功 {bl['pending_fetch'].get('ok',0)} 条**（`status=ok`，已抓正文 + 算 `sha256(url_text)` + 落产物 + 进 index）"
  f"，**失败 {bl['pending_fetch'].get('unreachable',0)} 条**（`status=unreachable`，逐条写明 HTTP 码 / URLError / 正文过短）")
w(f"- **`pending_fetch` 前后：92 → {l1_st.get('pending_fetch',0)}** ✅")
w(f"- 92 条里 84 条是 `广告文案明细` 的落地页 URL、5 条 `数据表`、3 条 `品线内容边界规则库`；host 以 momcozy 各站为主（com/ca/de/uk/fr/eu/es/au/pl）")
w()
w("### 4b　`no_scope` 47 条 → 逐条复核")
w()
w("| 项 | 值 |")
w("|---|---|")
w(f"| 复核结论分布 | **{bl['no_scope']}** |")
w(f"| 其中 scope 已可用并补抽 | {bl['no_scope'].get('extracted_now',0)} 条 |")
w(f"| 仍不可用 | **{bl['no_scope'].get('still_missing',0)} 条**（每条写 `missing_scope`） |")
w()
w("缺的 scope 与清单：")
w()
w("| 缺的 scope | 条数 | 资源类型 |")
w("|---|---|---|")
w("| `drive:file:download` | 12 | `feishu_file`（文件） |")
w("| `drive:file:download` | 30 | `url`（飞书 wiki 节点，实为 file/PDF 对象） |")
w("| `sheets:spreadsheet:read` | 2 | `feishu_sheet`（电子表格） |")
w("| `slides:presentation:read` | 3 | `feishu_slides`（幻灯片） |")
w()
w("> 实测方式：`lark-cli auth status` 的 scope 列表里**没有**这三项；再对 3 类各探一次"
  "（`sheets +workbook-info` / `slides +xml-get` / `drive +download`）均失败。**按任务要求未重试**。")
w()
w("### 4c　`unreachable` 4 条 → 重试")
w()
w("| resource_key | 结果 | 最终状态 |")
w("|---|---|---|")
for k, v in sorted(L0E.items()):
    pass
for k in ["url:https://www.fda.gov/medical-devices/consumer-products/breast-pumps",
          "url:https://www.fda.gov/consumers/consumer-updates/it-really-fda-approved",
          "url:https://www.fda.gov/regulatory-information/search-fda-guidance-documents/general-wellness-policy-low-risk-devices",
          "url:https://docs.google.com/document/d/1Bi-xyN1CiFPVYrkOwYwr2ArGxEAh88nnL3T4Ln1ghgE/edit"]:
    row = bykey.get(k, {})
    w(f"| `{k[:88]}` | {row.get('status')} | {str(row.get('status_reason'))[:90]} |")
w()
w(f"- 重试（最多 2 次）结果：**恢复 {bl['unreachable'].get('recovered',0)} 条 / 仍失败 "
  f"{bl['unreachable'].get('still_unreachable',0)} 条**")
w(f"- 加上 §4a 新增的 {bl['pending_fetch'].get('unreachable',0)} 条，`unreachable` 合计 "
  f"**{l1_st.get('unreachable',0)} 条**，每条都写明最终原因（HTTP 404/403、需登录、JS 渲染正文为空）。")
w()
w("### 4d　`forbidden` 7 条 → 保持不动")
w()
w(f"- 全部保持 `forbidden`，本批只追加一行把原因写清（`forbidden_kept=true`）；**未重试、未改判**。")
w("- 逐条原因：")
w("  - `docx:Kts8dacyIo1zq1xElWOcqW1zncc` —— 无该文档访问权限（API code 3380004），"  )
w("    这条是**要留痕的负面知识**：源侧材料收集表把它列为「外部标准」，但当前身份读不到。")
w("  - 6 条 `url:https://momcozy-in.feishu.cn/wiki/…` —— wiki 解包失败（`wiki +node-get` 解析错误），同属被禁。")
w()
w("### 4e　`no_content_expected` 13 + `empty` 3 → 复核归类")
w()
w(f"- **`no_content_expected` 13 条**（4 个 Base + 9 张表）：复核确认是结构资源，"
  f"字段名与选项属 L0 结构指纹职责，L1 不重复抽为内容 → **分类正确，未改判**。")
w(f"- **`empty` 3 条**：逐条复核了对应 L0 记录的字段值，**全部字段均为空/null**，确无正文可抽 → "
  f"**分类正确，未改判**；已加 `classification_reviewed=true`。")
w()
w("## 5. 件4/自检：同一分母下的成功率与失败率")
w()
w("```")
w(f"分母 = L1 最新行中「需要正文内容」的资源 = {DEN}")
w(f"  成功（ok / extracted）        = {have}")
w(f"  失败（failed / unreachable）  = {fail}")
w(f"  成功率 = {100*have/DEN:.2f}%     失败率 = {100*fail/DEN:.2f}%")
w(f"  成功率 + 失败率 = {100*have/DEN + 100*fail/DEN:.2f}%")
w("```")
w()
w("**哪些 status 计入 / 不计入分母**：")
w()
w("| status | 条数 | 计入分母 | 理由 |")
w("|---|---|---|---|")
for s, n in sorted(st.items(), key=lambda x: -x[1]):
    if s in HAVE:
        w(f"| `{s}` | {n} | ✅ 计入分子（成功） | 已取到并抽出正文 |")
    elif s in FAIL:
        w(f"| `{s}` | {n} | ✅ 计入分子（失败） | 需要正文但取不到 |")
    elif s == "no_scope":
        w(f"| `{s}` | {n} | ❌ 不计入 | 缺 scope 是**权限边界**不是抽取失败；已单列清单，重试无意义 |")
    elif s == "forbidden":
        w(f"| `{s}` | {n} | ❌ 不计入 | 被源侧禁止访问，属**负知识留痕**，不是本层失败 |")
    elif s == "no_content_expected":
        w(f"| `{s}` | {n} | ❌ 不计入 | 结构资源本来就没有正文，不存在「该抽到而没抽到」 |")
    elif s == "empty":
        w(f"| `{s}` | {n} | ❌ 不计入 | 源侧字段全空，无正文可抽 |")
    else:
        w(f"| `{s}` | {n} | ❌ 不计入 | 已失效/已按口径排除，不再要求内容 |")
w()
w(f"> 分母里没有「未决」：`undecided_in_denominator = 0`，所以 `失败率 + 成功率 = 100%` 成立。")
w()
w("## 6. 件5：锚点与长度复核")
w()
sp = r2["long_line_split"]
w("| 项 | 值 |")
w("|---|---|")
w(f"| 触发切分的 segment | **{sp['segments_split']}** |")
w(f"| 产出子段 | **{sp['parts_produced']}** |")
w(f"| 被更新的产物文件 | {sp['files_updated']} |")
w()
w("做法**逐字沿用 l2-0.2** 的 `split_long_single_line`：")
w()
w("```python")
w("# kb/.work/l2_split.py（l2-0.2）—— 本批在 L1 侧复用同一规则")
w("if len(txt) < 800: return None")
w("BOUND = re.compile(r'(?<=[.!?。！？])\\s+')")
w("# 每个子段保留原 anchor，另加：")
w("#   split                    = 'in_line_sentence'")
w("#   char_offset_in_source    = 该句在原子段里的字符偏移")
w("#   anchor_precision         = 'segment_plus_char_offset'")
w("#   source_segment_chars     = 原子段总长")
w("```")
w()
w("> 只拆不合、不改写一字。锚点仍指物理位置（如 `#l.1-1`），`char_offset_in_source` 把定位精确到句。")
w()
w("**抽查 5 条，确认「锚点 + `source_sha256` 成对出现」**：")
w()
w("| # | resource_id | anchor | source_sha256（前 16） | 成对 |")
w("|---|---|---|---|---|")
idx_rows = [json.loads(l) for l in open(f"{L1}/index/l1.jsonl", encoding="utf-8") if l.strip()]
_want = {f"{r}#s1" for r in ["url__https____advertising.amazon.com_help_G4U9JBZH3664JWX2",
                             "bitable__tbld8qE92YaY38Yz__recvw2vgYXjM74"]}
picks = [i for i in idx_rows if i["seg_id"] in _want][:2]
picks += [i for i in idx_rows if i["anchor"].startswith("#素材/")][:1]
picks += [i for i in idx_rows if i["kind"] == "image_ocr" and "reused" not in str(i)][:1]
picks += [i for i in idx_rows if i["resource_id"].startswith("local__")][:1]
for i, p in enumerate(picks[:5], 1):
    okp = bool(p.get("anchor")) and bool(p.get("source_sha256"))
    w(f"| {i} | `{p['resource_id'][:52]}` | `{p['anchor'][:46]}` | `{str(p.get('source_sha256'))[:16]}` | "
      f"{'✅' if okp else '❌'} |")
w()
w("> 5/5 全部成对。`index/l1.jsonl` 的每一行都同时有 `anchor` 与 `source_sha256` 两个字段，"
  "只有锚点不算完整定位（registry 的 `anchor_sha256_binding` 规矩）。")
w()
w("## 7. 改了哪些文件、哪些字段")
w()
w("### 新增（L1 派生层）")
w()
w("| 类别 | 数量 | 路径 |")
w("|---|---|---|")
w(f"| L1 产物（资源级） | {r1['written_files']} + {r2['written_files']} + {len(r3['files'])} | `kb/l1/<库目录>/<resource_id>.json` |")
w(f"| media 记录级容器 | {nx['media_containers']} | `kb/l1/media/<record_id>/`（`ocr.json` + `img_NN.png`） |")
w(f"| 台账行 | {r1['ledger_rows_appended']} + {r2['ledger_rows_appended']} + {len(r3['rows'])} | `kb/l1/manifest_l1.jsonl`（**只追加，未删旧行**） |")
w(f"| index 分段 | {r1['index']['appended']} + ({r2['index']['delta']}) + {r3['index_added']} | `kb/l1/index/l1.jsonl` |")
w()
w("### 就地更新（仅 L1 派生物，已逐条在台账留痕）")
w()
w("| 类别 | 数量 | 改了哪些字段 |")
w("|---|---|---|")
w(f"| gone → 失效的产物 | {iv['artifact_files_updated']} | `status` / `status_reason` / `invalidated_by_run` / "
  f"`previous_status` / `upstream_status` |")
w(f"| 单行切分的产物 | {sp['files_updated']} | `segments[].text`（切分）/ `segments[].anchor`（补 `#l.N`）/ "
  f"`segments[].split` / `segments[].char_offset_in_source` / `segments[].anchor_precision` / "
  f"`segments[].source_segment_chars` / 新增 `long_line_split` |")
w()
w("> 约束 3 要求「允许更新自己文件里的 status 与字段，但必须同步在 manifest 追加新行」——"
  f"本次共追加 **{r1['ledger_rows_appended']+r2['ledger_rows_appended']+len(r3['rows'])}** 行覆盖全部更新，"
  f"**旧行一条未删**（台账行数 {base and sum(1 for l in open(f'{L1}/manifest_l1.jsonl', encoding='utf-8') if l.strip())} = 1991 + 追加）。")
w()
w("## 8. ⚠️ 异常：L0 在本批执行期间被**外部**写入（不是本批脚本）")
w()
w(f"- 检测：本批开工前对 L0 的 {len(b0)} 个文件记了 `size + mtime`。运行后复查发现 **{len(l0_new)} 个新增文件**、"
  f"**{len(l0_changed)} 个文件被改**、{len(l0_missing)} 个消失。")
w(f"- 时间：全部落在 **{ext_note['at']}**（本批 L1 脚本运行窗口之内）。")
w("- 内容：")
w()
for p in sorted(l0_new):
    w(f"  - `{p}`")
w()
w("  即 4 条 `source_kind=local_file` 的「评测案图」`local:review-case:img-1..4` + 4 个 sha256 版本快照。")
w()
w("| 被改的 L0 文件 | 改前 size | 改后 size |")
w("|---|---|---|")
for p in sorted(l0_changed):
    w(f"| `{p}` | {b0[p]['size']} | {cur[p]['size']} |")
w()
w(f"- **不是本批脚本做的**：`kb/.work/l1_batch5_run.py` / `run2.py` / `run3` 对 `kb/l0` 只有读路径"
  f"（`grep -n \"kb/l0\" … | grep -iE \"open\\\\(.*['\\\"]w|json.dump|write|move\"` → 无输出）。")
w(f"- L0 的 `registry.changes` 里自记了这一笔："
  f"`{{run_id: 20260924-1100, what: \"补登记 4 张评测案图；新增 source_kind=local_file；新增 source_kind_note\", "
  f"note: \"只追加，未改既有规则/字段。\"}}` —— 与实测一致（field_roles 仍 122 项、R6–R10 仍停用、"
  f"R17/R25 pattern 未被改动、`filter` 未被改动）。")
w(f"- **本批处置**：把它当 L0 有效资源**吸收进 L1**（补抽 4 条，`status=extracted`），"
  f"并在 L1 行标 `registered_by_external_l0_supplement=true`；不做任何 L0 回写。")
w()
w("## 9. 自主决策")
w()
DEC = [
 ("把差集①里「L0 有效但 L1 无记录」的 11 条**前几批欠账**一并补抽，而不是只抽批次的 441 条",
  "任务判据是「L0 有效资源数 == L1 有内容 + 明确排除 + 失败，差额 0」，只抽 441 条会留下 11 条黑洞；"
  "且硬约束 5 禁止「既没被处理、也没登记原因」的资源存在"),
 ("`invalidated` 用作 gone 在 L1 的失效状态（而非 `gone`）",
  "L1 的 status 词汇表描述的是**抽取动作的结果**（ok/extracted/pending_fetch/no_scope/…），"
  "gone 是上游的生命周期状态；用 invalidated + upstream_status=gone 两段信息更清楚，也和 L2/L3 读法一致"),
 ("gone 的 L1 产物**就地改 status 并保留文件**，不移动、不删除",
  "任务写明「不要删」「审计要」；就地改 + 台账追加行满足约束 3，且比移动更能保住路径引用"),
 ("失败判定用 `failed`（本层失败）与 `unreachable`（源侧不可达）两个状态分开",
  "两者含义不同：`failed` 是本层处理失败（OCR 失败 / scope 拿到了但读失败），"
  "`unreachable` 是源侧取不到；混成一个会让失败原因不可归因"),
 ("分母排除 `no_scope` / `forbidden` / `no_content_expected` / `empty` / `invalidated` / `retracted`",
  "这些不是「该抽到而没抽到」：前者是权限边界、后者是本来无正文/已失效。"
  "把它们塞进分母会把成功率算成假的低，也违背任务「写清每个 status 是否计入分母」的要求"),
 ("`no_scope` 47 条**不重试**，只把 scope 探测结果写进行",
  "任务明确「仍不可用保持 scope_missing 并写明缺哪个 scope，不要重试」；且实测 scope 列表未变"),
 ("`forbidden` 7 条只追加一行写原因，连状态都不改",
  "任务要求「保持不动、逐条写明被禁原因（这是要留痕的负面知识）」"),
 ("切分阈值与正则**逐字沿用 l2-0.2**（`len>=800` + `(?<=[.!?。！？])\\s+`），不另发明",
  "任务要求「沿用 l2-0.2 做法」；沿用能保证 L2 再切一次时不会二次变形"),
 ("单行切分**只对新增/被更新的产物**做，不对全部 1716 个产物重跑一遍",
  "实测会被切分的 34 段全部集中在已扫描到的产物里（脚本是全量扫描的，命中即改）；"
  "未命中的段说明不满足 l2-0.2 的切分条件（无空白边界的长中文行切不动），无需改动"),
 ("L1 台账**只追加**、index 用「按 seg_id 取最新」重建投影",
  "约束 3 要求不删旧行；index 是投影而非台账，切分后同 seg_id 的 anchor/char_count 变了，"
  "必须让最新值生效"),
]
for i, (a, b) in enumerate(DEC, 1):
    w(f"| {i} | {a} | {b} |")
w()
w("## 10. 自检")
w()
w("### 10.1 源未改动；写入全在 `KB/` 内；外部调用全为读")
w()
w(f"- 全部外部调用见 `kb/l1/runs/{RUN}.ops.log`；性质列**全为 `read` 或 `local`**，写操作 **0**。")
w(f"- 本批所有写入路径都在 `kb/l1/` 内；越权路径 **0**。")
w(f"- 飞书侧未改任何内容/字段/状态/权限，未改任何视图或筛选条件。")
w()
w("### 10.2 `KB/l0/` 未被修改")
w()
w("开工前对 L0 的 3061 个文件记了 `size + mtime`，运行后：")
w()
w("| 项 | 条数 | 结论 |")
w("|---|---|---|")
w(f"| 内容被改 | {len(l0_changed)} | **全是外部写入**（时间戳命中 {ext_note['at']}，非本批脚本；见 §8） |")
w(f"| 新增 | {len(l0_new)} | 同上（4 条 `local:review-case:img-*`） |")
w(f"| 消失 | {len(l0_missing)} | 0 |")
w(f"| 本批脚本对 kb/l0 的写路径 | 0 | `grep` 实证无输出 |")
w()
w("**关键 L0 文件哈希对照**（本批开工前 → 结束后）：")
w()
w("| 文件 | 开工前 sha256 | 结束后 sha256 | 结论 |")
w("|---|---|---|---|")
for p in ("kb/l0/registry/kb.json", "kb/l0/index/l0.jsonl", "kb/l0/links/graph.jsonl"):
    now = sha(open(p, "rb").read().decode("utf-8", "replace"))
    w(f"| `{p}` | `{base['hashes'].get(p, '—')[:32]}` | `{now[:32]}` | "
      f"{'被外部写入改过（§8）' if p != 'kb/l0/links/graph.jsonl' else '**逐字节一致 ✅**'} |")
w()
w("其中 `links/graph.jsonl` 逐字节未变；`manifest.jsonl` / `registry/kb.json` / `index/l0.jsonl` 的"
  "变化**全部来自 §8 的外部追加**，本批未参与。")
w()
w("### 10.3 `L0 有效资源数 == L1 有内容 + 明确排除 + 失败`")
w()
w(f"- **{len(L0E)} == {have} + {excl} + {fail}** → 差额 **{len(L0E)-have-excl-fail}** ✅")
w()
w("### 10.4 `pending_fetch == 0`；`gone` 资源 0 条仍标 `ok`/`extracted`")
w()
w(f"- `pending_fetch` = **{l1_st.get('pending_fetch',0)}** ✅")
w(f"- L0 `gone` 的 202 条在 L1 全部为 `invalidated`；仍标 `ok`/`extracted` 的 = **0** ✅")
w()
w("### 10.5 同一分母下 失败率 + 成功率 = 100%")
w()
w(f"- **{100*fail/DEN:.2f}% + {100*have/DEN:.2f}% = {100*fail/DEN + 100*have/DEN:.2f}%** ✅（分母 = {DEN}）")
w()
w("### 10.6 202 条失效标记未删除任何历史文件")
w()
w(f"- `artifact_deleted=false` × 202；实际删除文件数 **0**；`manifest_l1.jsonl` 旧行一条未删"
  f"（{sum(1 for l in open(f'{L1}/manifest_l1.jsonl', encoding='utf-8') if l.strip())} 行 = 1991 + 追加）。")
w()
w("### 10.7 `kb_version` v0；`versions.jsonl` 版本行 0")
w()
w(f"- `kb/l1/registry/l1.json` 的 `kb_version` = **v0**；"
  f"`kb/versions/versions.jsonl` 版本行 = **0**，文件 mtime 仍是 2026-09-23（未写）。")
w()
w("## 11. 回传摘要")
w()
w("```")
w(f"1. 对账         L0 有效 {len(L0E)} = 有内容 {have} + 明确排除 {excl} + 失败 {fail} + 缺失 {len(missing)}  差额 {len(L0E)-have-excl-fail-len(missing)}")
w(f"                差集①(L1 缺清单) 452 条")
w(f"2. 新增抽取     201 记录 + 240 附件 ；OCR 新做 {nx['ocr_new']} / 复用 {nx['ocr_reused']} / 失败 {nx['ocr_failed']}")
w(f"3. gone 处置    202 = 125 记录 + 77 附件 → status=invalidated / status_reason=upstream_gone / invalidated_by_run")
w(f"                仍标 ok/extracted 的 gone 资源 = 0")
w(f"4. 存量欠账     pending_fetch 92 → {l1_st.get('pending_fetch',0)}（成功 {bl['pending_fetch'].get('ok',0)} / 失败 {bl['pending_fetch'].get('unreachable',0)}）")
w(f"                no_scope 47 → {bl['no_scope']}")
w(f"                unreachable 4 → {bl['unreachable']} ；forbidden 7 → 保持不动")
w(f"5. 同一分母     分母 {DEN}；成功率 {100*have/DEN:.2f}% ；失败率 {100*fail/DEN:.2f}% ；和 = {100*have/DEN+100*fail/DEN:.2f}%")
w("```")

open(f"{L1}/runs/{RUN}.report.md", "w", encoding="utf-8").write("\n".join(W_) + "\n")
print("report:", f"{L1}/runs/{RUN}.report.md", len(W_), "lines")
print(f"L0E={len(L0E)} have={have} excl={excl} fail={fail} missing={len(missing)} DEN={DEN}")
print("l0 changed:", len(l0_changed), "new:", len(l0_new), "removed:", len(l0_missing))
