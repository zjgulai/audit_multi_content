#!/usr/bin/env python3
"""Owner 硬规矩② · 表行独立回读与逐字段核对（RT-20261005-YOGA-03）。"""
import json, pathlib

here = pathlib.Path(__file__).resolve().parent
root = here.parent
raw = json.load(open(root / "_rt-yoga-03-readback-raw.json", encoding="utf-8"))
d = raw["data"]
names, vals = d["fields"], d["data"][0]
row = dict(zip(names, vals))

PRD = ["内容 ID", "产品线", "渠道", "内容类型", "送审版本", "Agent 结论", "置信度",
       "问题数量", "问题分类汇总", "报告链接", "人工复核人", "复核结论", "sign-off 人",
       "发布时间", "状态"]

out = {
    "record_id": d["record_id_list"][0],
    "rev": d["rev"],
    "identity": raw.get("identity"),
    "prd_fields_present_in_table": {k: (k in names) for k in PRD},
    "row": {k: row.get(k) for k in names},
}
missing = [k for k in PRD if k not in names]
out["missing_prd_columns"] = missing

eng = json.load(open(here / "engine.stdout.json", encoding="utf-8"))
dec = eng["decision"]
pub = eng["evidence_meta"]["publish"]
checks = {
    "内容 ID 非空且为 AD 编号": isinstance(row.get("内容 ID"), str) and row["内容 ID"].startswith("AD-"),
    "Agent 结论 == 引擎 decision": row.get("Agent 结论") == dec.get("decision"),
    "问题数量 == 引擎 issue_count": row.get("问题数量") == dec.get("issue_count"),
    "置信度 == 引擎 confidence": row.get("置信度") == dec.get("confidence"),
    "报告链接含云文档 id": isinstance(row.get("报告链接"), str) and pub.get("docx", "").split("/")[-1] in row.get("报告链接", ""),
    "状态 == [decision]": row.get("状态") == [dec.get("decision")],
    "送审问题 == 用户原提问": row.get("送审问题") == dec.get("submit_question"),
}
out["field_checks"] = checks
out["row_record_id_matches_publish"] = (d["record_id_list"][0] == pub.get("record_id"))
out["all_checks_pass"] = all(checks.values()) and not missing and out["row_record_id_matches_publish"]
print(json.dumps(out, ensure_ascii=False, indent=2))
(here / "readback-verified.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
