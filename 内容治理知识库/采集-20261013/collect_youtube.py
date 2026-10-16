#!/usr/bin/env python3
"""抓 YouTube 视频的 uploadDate（从 watch 页 JSON-LD），用于填「发布时间」。"""
import json, re, subprocess, time, os

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
HERE = os.path.dirname(__file__)


def main():
    resolved = json.load(open(os.path.join(HERE, "raw", "yt_resolved.json")))
    vids = [r for r in resolved if r.get("title")]
    out = []
    for n, r in enumerate(vids, 1):
        vid = r["videoId"]
        h = subprocess.run(["curl", "-sS", "--max-time", "25", "-A", UA,
                            f"https://www.youtube.com/watch?v={vid}"],
                           capture_output=True, text=True).stdout
        up = re.search(r'"uploadDate":"([^"]+)"', h)
        vc = re.search(r'"viewCount":"(\d+)"', h)
        rec = dict(r)
        rec["uploadDate"] = up.group(1) if up else None
        rec["viewCount"] = int(vc.group(1)) if vc else None
        rec["url"] = f"https://www.youtube.com/watch?v={vid}"
        out.append(rec)
        print(f"[{n:>2}/{len(vids)}] {vid} {rec['uploadDate']} views={rec['viewCount']} "
              f"{(rec['title'] or '')[:56]}", flush=True)
        json.dump(out, open(os.path.join(HERE, "out", "youtube.json"), "w"),
                  ensure_ascii=False, indent=1)
        time.sleep(0.6)


if __name__ == "__main__":
    main()
