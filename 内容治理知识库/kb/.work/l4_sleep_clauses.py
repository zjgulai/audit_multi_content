#!/usr/bin/env python3
"""只读：L4 canonical **五个形态文件**里抽「婴幼儿睡眠安全」相关条款（条款号 + 逐字正文）。

输出 JSONL 到 stdout，一行一条：
  {article_no, form, status, kb_type, anchor, p_level, risk_level, rule_code,
   text, reason, suggested_replacement, unit_ids}
"""
import json, os, re, sys

KB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
L4 = os.path.join(KB, "l4", "canonical")
FILES = ["wording_entry.jsonl", "wording_revision_pair.jsonl", "sample_case.jsonl", "scoped_clause.jsonl"]

PAT = re.compile(
    r"睡眠|睡姿|仰卧|仰睡|俯卧|趴睡|侧躺|侧睡|窒息|猝死|SIDS|SUID|safe\s*sleep|bed\s*shar|"
    r"co-?sleep|婴儿床|宝宝睡眠|婴幼儿睡眠|床围|防撞|枕头|sleep\s*sack|swaddle|襁褓|"
    r"同床|分床|夜灯|夜间|睡眠空间|睡眠环境|睡整觉",
    re.I,
)


def main():
    out = []
    for fn in FILES:
        p = os.path.join(L4, fn)
        if not os.path.exists(p):
            continue
        for line in open(p, encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            try:
                o = json.loads(line)
            except Exception:
                continue
            blob = json.dumps(o, ensure_ascii=False)
            if not PAT.search(blob):
                continue
            text = ""
            for tf in ("rule_text", "sample_body", "clause_text", "forbidden_expression"):
                if o.get(tf):
                    text = o[tf]
                    break
            uids = []
            if o.get("unit_id"):
                uids.append(o["unit_id"])
            uids += list(o.get("unit_ids") or [])
            uids += [e.get("unit_id") for e in (o.get("evidence_units") or [])
                     if isinstance(e, dict) and e.get("unit_id")]
            rec = {
                "article_no": o.get("article_no"),
                "form": o.get("form"),
                "status": o.get("status"),
                "kb_type": o.get("kb_type"),
                "anchor": o.get("anchor"),
                "source_sha256": o.get("source_sha256"),
                "p_level": o.get("p_level"),
                "risk_level": o.get("risk_level"),
                "rule_code": o.get("rule_code"),
                "text": text,
                "reason": o.get("reason") or o.get("reason_analysis") or o.get("p_level_basis"),
                "suggested_replacement": o.get("suggested_replacement"),
                "unit_ids": sorted(set(uids)),
                "matched_form": fn.replace(".jsonl", ""),
            }
            out.append(rec)
    for r in out:
        print(json.dumps(r, ensure_ascii=False))


if __name__ == "__main__":
    main()
