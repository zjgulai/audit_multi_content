#!/usr/bin/env python3
"""L0 扫描公共库 —— scanner 0.7。

本文件补齐两处此前的链路缺口（run 20260924-1000 自查发现）：
  ① **gone 检测**：此前全台账 `status == gone` 为 0 行，且三处 `gone` 只出现在
     `downstream_invalidated` 的集合成员判断里，**没有任何代码路径会把 status 写成 gone**。
     本库提供 `detect_gone()`：取源侧全量 key 清单 × 台账有效 key 做差集 → 差集内落 gone，
     并提供 `assert_accounting()` 做「不留黑洞」的闭环断言。
  ② **规则真求值**：此前 `来源链接` 的 kb_type 是发射器硬编码的
     （build.py:293 错标 R11、build2.py:276 硬编码 R15），没走求值。
     本库提供 `eval_rule()`，`matched_rule` 一律是被求出的值。

口径约定：
  - 源侧清单一律用 **all_records** 口径（`+record-list` 不带 `--view-id`，manifest 里
    `query_context.record_scope == "all_records"`），否则视图筛选会伪造出 gone。
  - gone ≠ retracted：`retracted` 是口径排除（不该在库），`gone` 是源侧删除（曾经在库、现在没了）。
"""
import json, os, collections

SCANNER_VERSION = "0.7"

GONE_REASON_SOURCE_REMOVED = "source_record_removed"
GONE_REASON_PARENT_GONE = "parent_gone"

# ---------------------------------------------------------------- 台账

def ledger_latest(path):
    """台账按 key 取最新一行。"""
    latest = {}
    for line in open(path, encoding="utf-8"):
        if line.strip():
            r = json.loads(line)
            latest[r["resource_key"]] = r
    return latest


def ledger_keys_of_table(latest, table_id, exclude_statuses=("retracted",)):
    """某张表在台账里的全部 key（默认排除已按口径排除的 retracted）。"""
    pre = f"bitable:{table_id}:"
    return {k for k, v in latest.items()
            if k.startswith(pre) and v.get("status") not in exclude_statuses}


def split_record_and_attachment_keys(keys):
    recs, atts = set(), set()
    for k in keys:
        (atts if "/fld" in k else recs).add(k)
    return recs, atts


# ---------------------------------------------------------------- 源侧清单（all_records 口径）

def assert_all_records_scope(manifest, expect_table_id=None):
    """断言本次读取是 all_records、不带视图筛选。"""
    qc = manifest.get("query_context") or {}
    ok = qc.get("record_scope") == "all_records"
    info = {"record_scope": qc.get("record_scope"), "field_scope": qc.get("field_scope"),
            "has_more": manifest.get("has_more"), "page_count": manifest.get("page_count"),
            "records_count": manifest.get("records_count"), "rev": manifest.get("rev"),
            "view_filter_used": "--view-id" in json.dumps(manifest)}
    if not ok:
        raise AssertionError(f"源侧清单不是 all_records 口径，gone 检测不可信: {info}")
    return info


def source_key_list(table_id, records, attachment_fields):
    """源侧全量 key 清单。
    attachment_fields: {字段名: 字段id}，值为 attachment 类型的字段。
    """
    rec_keys, att_keys = set(), set()
    for r in records:
        rid = r["record_id"]
        rec_keys.add(f"bitable:{table_id}:{rid}")
        for fname, fid in attachment_fields.items():
            for a in (r.get(fname) or []):
                if isinstance(a, dict) and a.get("file_token"):
                    att_keys.add(f"bitable:{table_id}:{rid}/{fid}/{a['file_token']}")
    return rec_keys, att_keys


# ---------------------------------------------------------------- gone 检测

def detect_gone(latest, table_id, source_rec_keys, source_att_keys,
                exclude_statuses=("retracted",)):
    """台账有效 key × 源侧清单 做差集 → gone。

    返回 dict：
      gone_records / gone_attachments : 需要落 gone 的 key 列表（带 last_seen_observed_at）
      accounting                      : 闭环断言用的账目
    """
    led_keys = ledger_keys_of_table(latest, table_id, exclude_statuses)
    led_recs, led_atts = split_record_and_attachment_keys(led_keys)
    src_recs, src_atts = set(source_rec_keys), set(source_att_keys)

    gone_recs = sorted(led_recs - src_recs)
    gone_atts = sorted(led_atts - src_atts)

    # 反向差集：源侧有、台账没有 → 应登记（不能静默丢）
    missing_recs = sorted(src_recs - led_recs)
    missing_atts = sorted(src_atts - led_atts)

    keys_ever = led_keys | src_recs | src_atts
    return {
        "table_id": table_id,
        "ledger_live_keys": len(led_keys),
        "ledger_live_records": len(led_recs),
        "ledger_live_attachments": len(led_atts),
        "source_records": len(src_recs),
        "source_attachments": len(src_atts),
        "source_key_list": len(src_recs) + len(src_atts),
        "gone_records": gone_recs,
        "gone_attachments": gone_atts,
        "gone_total": len(gone_recs) + len(gone_atts),
        "source_missing_from_ledger_records": missing_recs,
        "source_missing_from_ledger_attachments": missing_atts,
        "keys_ever_in_ledger_scope": len(keys_ever),
        "last_seen": {k: latest[k].get("observed_at") for k in gone_recs + gone_atts},
    }


def assert_accounting(gone_rows, excluded_keys, retracted_keys, in_library_keys,
                      keys_ever, source_key_list):
    """闭环断言：不留黑洞。

    identity_A（本批要求的口径）：gone + 在库 + excluded == 该表历史键全集
    identity_B（源侧对账）：源侧清单 == 在库 + excluded（源侧有的都登记了，台账里没有多余的）
    """
    lhs_a = gone_rows + in_library_keys + excluded_keys + retracted_keys
    acc = {
        "identity_A_公式": "gone + 在库 + excluded + retracted == 该表历史键全集(keys_ever)",
        "identity_A_gone": gone_rows,
        "identity_A_在库": in_library_keys,
        "identity_A_excluded": excluded_keys,
        "identity_A_retracted": retracted_keys,
        "identity_A_左值": lhs_a,
        "identity_A_右值": keys_ever,
        "identity_A_差额": keys_ever - lhs_a,
        "identity_B_公式": "源侧清单数 == 在库 + excluded",
        "identity_B_源侧清单": source_key_list,
        "identity_B_左值": source_key_list,
        "identity_B_右值": in_library_keys + excluded_keys,
        "identity_B_差额": source_key_list - (in_library_keys + excluded_keys),
        "字面口径说明": ("任务写的字面式是 `gone + 在库 + excluded == 源侧清单数`。"
                         "按字面只有当「源侧清单数」读作**该表历史键全集**（源侧本轮清单 ∪ 台账历史 key）"
                         "时才成立，即 identity_A；若把「源侧清单数」读作**本轮源侧实读清单**，"
                         "成立的式子是 identity_B（源侧清单 == 在库 + excluded），"
                         "此时 gone 是「曾经在库、现已不在源侧」的部分，不参与分母。两个式子差额都为 0。"),
    }
    acc["identity_A_通过"] = acc["identity_A_差额"] == 0
    acc["identity_B_通过"] = acc["identity_B_差额"] == 0
    if not (acc["identity_A_通过"] and acc["identity_B_通过"]):
        raise AssertionError(f"对账不闭环: {json.dumps(acc, ensure_ascii=False)}")
    return acc


# ---------------------------------------------------------------- 规则真求值

def active_rules(registry):
    return [r for r in registry["rules"] if r.get("enabled", True)]


def eval_rule(registry, table, kb_type_hint=None, field_name=None,
              scope_table=None, scoped_values=None, excluded_tables=()):
    """按 registry 顺序真求值。返回 (kb_type, rule_id, kb_type_source, trace)。

    顺序：记录自带分类值 → scope_table+字段值 → 字段名 → 表名兜底。
    `excluded_tables` 里的表整体不纳入（不登记、不兜底进 unknown）。
    """
    if table in excluded_tables:
        return None, None, f"excluded_scope:{table}", {"excluded": True, "table": table}
    rules = active_rules(registry)
    trace = []
    for t in (kb_type_hint or []):
        if t == "其它":
            continue
        for r in rules:
            if (r["match_type"] == "field_value" and r.get("scope_table") == "材料收集"
                    and r.get("match_value") == t):
                trace.append(f"R?{r['id']} field_value 材料收集::{r.get('pattern')}={t}")
                return r["kb_type"], r["id"], f"记录字段值:知识库分类={t}", {"trace": trace}
    for fnam, fval in (scoped_values or {}).items():
        for r in rules:
            if (r["match_type"] == "field_value" and r.get("scope_table") == scope_table
                    and r.get("pattern") == fnam and r.get("match_value") == fval):
                trace.append(f"{r['id']} field_value {scope_table}::{fnam}={fval}")
                return r["kb_type"], r["id"], f"记录字段值:{fnam}={fval}", {"trace": trace}
    if field_name:
        for r in rules:
            if r["match_type"] == "field_name" and r["pattern"] == field_name:
                if r.get("scope_table") and scope_table and r["scope_table"] != scope_table:
                    continue
                trace.append(f"{r['id']} field_name {field_name}")
                return r["kb_type"], r["id"], f"字段名:{field_name}", {"trace": trace}
    for r in rules:
        if r["match_type"] == "table_name" and r["pattern"] == table:
            if r.get("scope_table") and r["scope_table"] != table:
                continue
            trace.append(f"{r['id']} table_name {table}")
            return r["kb_type"], r["id"], f"表名:{table}", {"trace": trace}
    trace.append("no_rule_matched")
    return "unknown", None, "no_rule_matched", {"trace": trace}


def rule_hits(entries):
    """entries: [(kb_type, rule_id, source, trace)] → Counter"""
    return collections.Counter(e[1] for e in entries if e[1])
