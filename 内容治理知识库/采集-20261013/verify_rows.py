#!/usr/bin/env python3
"""写库前的最后一道尺子：逐条核 80 行的 URL 是否真能打开。

- 图片行：URL 必须 200 且 content-type 是 image/*
- 视频行：视频页必须 200
- 文案行：来源页必须 200
任何一条红 ⇒ 退出码 3，不许写库。
"""
import json, re, subprocess, os, sys

HERE = os.path.dirname(__file__)
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"


def probe(url, want_image=False):
    r = subprocess.run(["curl", "-sS", "-o", "/dev/null", "-w", "%{http_code} %{content_type}",
                        "-L", "--max-time", "25", "-A", UA, url], capture_output=True, text=True)
    p = r.stdout.split()
    code = p[0] if p else "000"
    ct = p[1] if len(p) > 1 else ""
    if want_image:
        return code == "200" and ct.startswith("image/"), f"{code} {ct}"
    return code == "200", f"{code} {ct}"


def target_url(row):
    """从采集数据里取出要核的那个 URL。"""
    blob = row["采集数据"]
    urls = re.findall(r"https?://[^\s]+", blob)
    return urls[0] if urls else row.get("_url", "")


def main():
    rows = json.load(open(os.path.join(HERE, "out", "rows.json")))
    fails, checked = [], 0
    for i, r in enumerate(rows, 1):
        u = target_url(r)
        t = r["内容类型"]
        ok, info = probe(u, want_image=(t == "图片"))
        checked += 1
        if not ok:
            fails.append((i, t, r["内容 ID"], u[:110], info))
            print(f"  RED  [{i:>2}] {t} {r['内容 ID']}  {info}  {u[:95]}", flush=True)
        else:
            print(f"  ok   [{i:>2}] {t} {r['内容 ID']}  {info}", flush=True)

    print(f"\nchecked={checked}  red={len(fails)}")
    if fails:
        print("!!! 有死链，不许写库")
        sys.exit(3)
    print("全部可访问 —— 可以写库")


if __name__ == "__main__":
    main()
