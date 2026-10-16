#!/usr/bin/env python3
"""把 80 行挂的云文档全部拉下来解析，并与表里的结论列对账。

回答两件事：
  Q1 三态分布到底是多少（"没有一条通过"是不是真的）
  Q2 报告里所有提到「奶瓶」的发现，逐条列出并判定它是不是站得住

产出 out/reports80.json：每行 {内容ID, 表内结论, 表内问题数, 文档结论, 文档问题数, findings[...]}
"""
import json, os, re, subprocess, html, collections, sys

HERE = os.path.dirname(__file__)
OUT = os.path.join(HERE, "out")
DOCS = os.path.join(OUT, "docs80")
LARK = os.path.expanduser("~/.dsh/bin/lark-cli")
os.makedirs(DOCS, exist_ok=True)


def fetch_doc(tok):
    p = os.path.join(DOCS, f"{tok}.json")
    if os.path.exists(p) and os.path.getsize(p) > 100:
        return json.load(open(p))
    r = subprocess.run([LARK, "docs", "+fetch", "--doc", tok,
                        "--profile", "dsh-kb", "--as", "bot"],
                       capture_output=True, text=True)
    try:
        d = json.loads(r.stdout)
    except Exception:
        return None
    json.dump(d, open(p, "w"), ensure_ascii=False)
    return d


def doc_text(d):
    def walk(o):
        out = []
        if isinstance(o, dict):
            for k, v in o.items():
                if k == "content" and isinstance(v, str) and len(v) > 100:
                    out.append(v)
                else:
                    out += walk(v)
        elif isinstance(o, list):
            for v in o:
                out += walk(v)
        return out
    parts = walk(d)
    s = max(parts, key=len) if parts else ""
    s = html.unescape(re.sub(r"<br\s*/?>", "\n", s))
    s = re.sub(r"<[^>]+>", "", s)
    return s


def parse_doc(txt):
    concl = re.search(r"【审查结论[：:]\s*([A-Z_]+)】", txt)
    n = re.search(r"共发现\s*(\d+)\s*处", txt)
    # 逐条发现：N.【分类】...
    finds = []
    for m in re.finditer(r"(\d+)\.\s*【([^】]+)】([^\n]{0,120})", txt):
        finds.append({"idx": int(m.group(1)), "cat": m.group(2),
                      "head": m.group(3).strip()[:120]})
    return {"doc_concl": concl.group(1) if concl else None,
            "doc_n": int(n.group(1)) if n else None,
            "findings": finds, "len": len(txt)}


def main():
    # 表 80 行
    subprocess.run([LARK, "base", "+record-list", "--base-token",
                    "RY2UbCRjXaeeWwscUPScVN5AnQc", "--table-id", "tblavfbMDMeRsulo",
                    "--limit", "200", "--format", "ndjson", "--output",
                    os.path.join(OUT, "tbl80.ndjson"), "--profile", "dsh-kb", "--as", "bot"],
                   capture_output=True, text=True)
    rows = []
    for line in open(os.path.join(OUT, "tbl80.ndjson"), encoding="utf-8"):
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    print("表内行数:", len(rows))

    docs = set()
    for r in rows:
        for m in re.findall(r"docx/([A-Za-z0-9]{20,})", str(r.get("报告链接") or "")):
            docs.add(m)
    print("云文档数:", len(docs))

    res, fail = [], []
    for i, tok in enumerate(sorted(docs), 1):
        d = fetch_doc(tok)
        if not d or not d.get("ok"):
            fail.append(tok); continue
        info = parse_doc(doc_text(d))
        info["doc"] = tok
        res.append(info)
        print(f"[{i:>2}/{len(docs)}] {tok} 结论={info['doc_concl']} 问题数={info['doc_n']} "
              f"条目={len(info['findings'])}", flush=True)

    # 关联回表行
    for r in rows:
        toks = re.findall(r"docx/([A-Za-z0-9]{20,})", str(r.get("报告链接") or ""))
        r["_doc"] = toks[0] if toks else None
    json.dump({"docs": res, "rows": rows, "fail": fail},
              open(os.path.join(OUT, "reports80.json"), "w"), ensure_ascii=False, indent=1)

    print("\n=== 文档侧三态 ===")
    print(dict(collections.Counter(d["doc_concl"] for d in res)))
    print("=== 文档侧问题数 ===")
    print(dict(collections.Counter(d["doc_n"] for d in res)))
    print("\n取不到的文档:", fail)


if __name__ == "__main__":
    main()
