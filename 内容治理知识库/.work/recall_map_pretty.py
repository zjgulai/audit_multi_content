#!/usr/bin/env python3
"""只读：把 recall-map JSON 打成一页可读的清单（条款号 + 原文摘录）。"""
import json, sys

def trunc(s, n=600):
    if s is None:
        return ""
    s = " ".join(str(s).split())
    return s if len(s) <= n else s[:n] + f" …(共{len(str(s))}字)"


def main():
    rep = json.load(open(sys.argv[1], encoding="utf-8"))
    for rec in rep["recalls"]:
        print(f"\n########## 检索：{rec['query']} ｜ mode={rec['mode']} ｜ file={rec['file']}")
        print(f"########## lists_used={rec['lists_used']}")
        for r in rec["rows"]:
            l2 = r.get("l2") or {}
            l4 = r.get("l4") or []
            print(f"\n--- rank {r['rank']}  score={r['score']}  unit_id={r['unit_id']}")
            print(f"    kb_type={r['kb_type']}  table={r.get('table')}  lang={r.get('lang')}"
                  f"  sources={r.get('sources')}")
            print(f"    anchor={r['anchor']}")
            print(f"    source_sha256={r['source_sha256']}")
            if l2:
                print(f"    L2: kb_type={l2['kb_type']} char_count={l2['char_count']}"
                      f" unit_type={l2['unit_type']} rule_eligible={l2['rule_eligible']}"
                      f" parent={l2['parent_unit_id']}")
                print(f"    L2 anchor={l2['anchor']}")
                print(f"    L2 正文：{trunc(l2['text'])}")
            else:
                print("    L2: NOT FOUND")
            if l4:
                for a in l4:
                    print(f"    ★L4 条款号={a['article_no']} form={a['form']} status={a['status']}"
                          f" rule_code={a.get('rule_code')} p_level={a.get('p_level')}"
                          f" risk_level={a.get('risk_level')}")
                    print(f"      L4 正文：{trunc(a['text'])}")
                    if a.get("reason"):
                        print(f"      L4 理由：{trunc(a['reason'], 300)}")
                    if a.get("suggested_replacement"):
                        print(f"      L4 建议表达：{trunc(a['suggested_replacement'], 300)}")
            else:
                print("    ★L4: 无对应条款号（该 unit 未进 canonical）")


if __name__ == "__main__":
    main()
