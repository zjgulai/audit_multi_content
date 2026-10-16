#!/usr/bin/env python3
"""写库后读回核验：不信任写入返回，以服务端读到的为准。"""
import json, subprocess, os, collections, sys

HERE = os.path.dirname(__file__)
BASE = "RY2UbCRjXaeeWwscUPScVN5AnQc"
TABLE = "tblavfbMDMeRsulo"
LARK = os.path.expanduser("~/.dsh/bin/lark-cli")
VOCAB = {"吸奶器", "喂养电器", "婴幼儿", "家居", "其他"}


def main():
    p = subprocess.run([LARK, "base", "+record-list", "--base-token", BASE, "--table-id", TABLE,
                        "--page-size", "200", "--profile", "dsh-kb", "--as", "bot",
                        "--format", "json"],
                       capture_output=True, text=True)
    d = json.loads(p.stdout)
    if not d.get("ok"):
        print("读回失败:", json.dumps(d.get("error"), ensure_ascii=False)); sys.exit(3)
    # 服务端返回的是「列名 + 位置数组」，不是 [{fields:{...}}]
    payload = d["data"]
    cols = payload.get("fields") or []
    raw = payload.get("data") or []
    recs = [dict(zip(cols, row)) for row in raw]
    print("服务端读回记录数:", len(recs))
    print("列名:", cols)

    mine = [r for r in recs if r.get("内容 ID")]
    print("本次采集行数:", len(mine))

    def fv(r, k):
        v = r.get(k)
        if isinstance(v, list):
            return "".join(x.get("text", "") if isinstance(x, dict) else str(x) for x in v)
        if isinstance(v, dict):
            return v.get("text") or v.get("name") or ""
        return v if v is not None else ""

    print("\n内容类型:", dict(collections.Counter(fv(r, "内容类型") for r in mine)))
    print("渠道:", dict(collections.Counter(fv(r, "渠道") for r in mine)))
    print("产品线:", dict(collections.Counter(fv(r, "产品线") for r in mine)))
    print("状态:", dict(collections.Counter(fv(r, "状态") for r in mine)))

    errs = []
    want = {"文案": 35, "图片": 35, "视频": 10}
    got = collections.Counter(fv(r, "内容类型") for r in mine)
    for k, v in want.items():
        if got.get(k, 0) != v:
            errs.append(f"{k} 数量 {got.get(k,0)} != {v}")
    bad_line = {fv(r, "产品线") for r in mine} - VOCAB
    if bad_line:
        errs.append(f"产品线越出受控词表: {bad_line}")
    empty = [fv(r, "内容 ID") for r in mine if not str(fv(r, "采集数据")).strip()]
    if empty:
        errs.append(f"采集数据为空: {empty[:5]}")
    ids = [fv(r, "内容 ID") for r in mine]
    if len(ids) != len(set(ids)):
        dup = [k for k, c in collections.Counter(ids).items() if c > 1]
        errs.append(f"内容 ID 重复: {dup[:5]}")

    print("\n--- 抽样（各类型第一条）---")
    for t in ("文案", "图片", "视频"):
        for r in mine:
            if fv(r, "内容类型") == t:
                print(f"[{t}] {fv(r,'内容 ID')} | {fv(r,'渠道')} | {fv(r,'产品线')} | 状态={fv(r,'状态')}")
                print("   ", str(fv(r, "采集数据"))[:150].replace("\n", " / "))
                break

    print("\n结论:", "全部通过" if not errs else "有问题 —— " + "; ".join(errs))
    sys.exit(0 if not errs else 3)


if __name__ == "__main__":
    main()
