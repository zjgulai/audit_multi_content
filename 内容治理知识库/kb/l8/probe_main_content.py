#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""实测：按「正文容器」取文本，能不能把评论组件与页脚推荐位排除在外。

为什么试这条（2026-10-08 实测结论）：
  「整页渲染取全部文本 + 事后按规则剔行」压不住 —— 机械规则只把 71 条变更里的 20 条抹平，
  再叠一张**从同一批 diff 反推**的站点块表也只到 41 条（且那是 in-sample 上界），
  剩下的全是**每天轮换的顾客评论正文**（新评论文本永远不在表里）。
  ⇒ 要让「数据一样就保留」机械成立，只能**一开始就不把评论组件抽进来**，
    也就是按正文容器取文本，而不是整页。

本脚本只做**对照实验**，不写任何库：同一 URL 分别按
  ① 现有 extract()（整页）② 正文容器（main/article/role=main，取不到再回落 body）
取文本，逐行比，看评论/页脚是否落在 ① 有而 ② 没有的那部分。

用法：python3 kb/l8/probe_main_content.py <url> [<url> ...]
"""
import os
import re
import sys
import html as H
import shutil
import subprocess
import time
from html.parser import HTMLParser

# ★ 2026-10-09 修正：原先指向完整 Google Chrome.app —— macOS 上启动 app bundle
# 必然在 Dock 弹图标，而本库是「起一个→kill→再起一个」的循环 ⇒ 图标不停闪。
# 改用 chrome-headless-shell（官方无头专用二进制，不是 .app，不进 Dock）。
# 它对本文件既有的 --headless=new/--headless 参数一律容忍，故只换路径、不动 flag。
CHROME = os.environ.get("KB_CHROME_BIN",
    "/Users/lute/.dsh/vendor/chrome-headless-shell-mac-arm64/chrome-headless-shell")
UA_NEW = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")


_SEQ = [0]


def fetch(url, mode="new", cap=30, quiet=1.5, _retry=True):
    """渲染整页 DOM。

    ★ 2026-10-08 修脆弱点：`user-data-dir` 原先按 `hash(url)` 命名 —— 同一 URL 跨进程会落到
      **同一个 profile 目录**，撞上上一次被 kill 但未回收的 Chrome 时，新进程起不来 ⇒
      `--dump-dom` 一个字节都不落，**表现为「渲染失败」而看不出原因**（实测同一 URL 单独跑
      成功、连着跑偶发 0 字节）。改成 `pid + 自增序号` 唯一目录，用完删掉；空结果再重试一次。
    """
    _SEQ[0] += 1
    tag = f"{os.getpid()}_{_SEQ[0]}"
    tmp = f"/tmp/_pmc_{tag}.html"
    prof_dir = f"/tmp/pmc-prof-{tag}"
    if mode == "new":
        args = [CHROME, "--headless=new", "--disable-gpu", "--no-sandbox",
                f"--user-data-dir={prof_dir}", "--lang=en-US",
                "--virtual-time-budget=8000", f"--user-agent={UA_NEW}", "--dump-dom", url]
    else:
        args = [CHROME, "--headless", "--disable-gpu", "--no-sandbox",
                f"--user-data-dir={prof_dir}", "--lang=en-US",
                "--window-size=1440,900", "--virtual-time-budget=12000",
                "--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
                "--dump-dom", url]
    with open(tmp, "wb") as fh:
        p = subprocess.Popen(args, stdout=fh, stderr=subprocess.DEVNULL)
        last, stable, t0 = -1, 0.0, time.time()
        while time.time() - t0 < cap:
            time.sleep(0.4)
            try:
                sz = os.path.getsize(tmp)
            except OSError:
                sz = 0
            if sz > 0 and sz == last:
                stable += 0.4
                if stable >= quiet and b"</html>" in open(tmp, "rb").read()[-400000:]:
                    break
            else:
                stable = 0.0
            last = sz
        try:
            p.kill()
        except Exception:
            pass
    try:
        h = open(tmp, "rb").read().decode("utf-8", "ignore")
    except Exception:
        h = ""
    for _d in (tmp,):
        try:
            os.remove(_d)
        except OSError:
            pass
    shutil.rmtree(prof_dir, ignore_errors=True)
    if not h and _retry:
        time.sleep(1.5)
        return fetch(url, mode=mode, cap=cap, quiet=quiet, _retry=False)
    return h


def extract(h):
    """与 recrawl_all_urls.py::extract 逐字相同（对照组）。"""
    h = re.sub(r"<(script|style|noscript)[^>]*>.*?</\1>", " ", h, flags=re.S | re.I)
    h = re.sub(r"</(p|li|div|h[1-6]|tr|section|article|ul|ol|td|th|table)>", "\n", h, flags=re.I)
    h = re.sub(r"<br\s*/?>", "\n", h, flags=re.I)
    h = re.sub(r"<[^>]+>", " ", h)
    txt = H.unescape(h)
    out, seen = [], set()
    for line in txt.split("\n"):
        s = re.sub(r"\s+", " ", line).strip()
        if len(s) < 30:
            continue
        codey = sum(s.count(c) for c in "{};<>\\") / max(1, len(s))
        if codey > 0.04:
            continue
        if s not in seen:
            seen.add(s)
            out.append(s)
    return "\n".join(out).strip()


class MainFinder(HTMLParser):
    """找出第一个 main / [role=main] / article 的字符区间；找不到返回 None。

    只用字符偏移，不建树 —— 目的是**挑区间**，不是解析语义。
    """

    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.offsets = []          # (start_offset, tag, attrs)
        self.depth = 0
        self.spans = []
        self._open = None

    def _off(self):
        return self.getpos()

    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        if tag in ("main", "article") or (d.get("role") == "main"):
            if self._open is None:
                self._open = (tag, self._linecol_to_off())
        self.depth += 1

    def handle_endtag(self, tag):
        self.depth -= 1
        if self._open and self._open[0] == tag:
            self.spans.append((self._open[1], self._linecol_to_off()))
            self._open = None

    def _linecol_to_off(self):
        return None      # 占位：真实偏移由外部按行累计（见 find_main_span）


def find_main_span(h):
    """用正则粗定位 <main…>…</main>（或 article / role=main）区间。

    为什么用正则而不是建树：`--dump-dom` 的产出是**浏览器修过的** HTML，
    真实站点里有大量畸形嵌套；建树反而容易被吞掉整段。这里只求区间够用，
    且**取不到就回落整页**（不会因为找不到 main 而丢正文）。
    """
    for pat in (r"<main[\s>]", r"<article[\s>]", r"<[a-z]+[^>]*\brole=[\"']main[\"']"):
        m = re.search(pat, h, re.I)
        if not m:
            continue
        tag = re.match(r"<([a-z]+)", h[m.start():], re.I).group(1)
        # 从开标签起做括号配平
        depth, i = 0, m.start()
        for mm in re.finditer(rf"<(/?){tag}\b[^>]*>", h[i:], re.I):
            if mm.group(1) == "/":
                depth -= 1
                if depth == 0:
                    return h[m.start():i + mm.end()], tag
            else:
                depth += 1
    return None, None


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    for url in sys.argv[1:]:
        h = fetch(url)
        if not h:
            print(f"── {url}\n   渲染失败（0 字节）")
            continue
        full = extract(h)
        span, tag = find_main_span(h)
        main_txt = extract(span) if span else ""
        fl, ml = set(full.split("\n")), set(main_txt.split("\n"))
        only_full = [x for x in full.split("\n") if x not in ml]
        print(f"── {url}")
        print(f"   容器: {tag or '未找到（回落整页）'}｜整页 {len(full):,} 字 / 容器 {len(main_txt):,} 字"
              f"｜容器外 {len(full)-len(main_txt):,} 字（{len(only_full)} 行）")
        # 容器外那部分里，有没有评论/页脚特征
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "bo", os.path.join(os.path.dirname(os.path.abspath(__file__)), "body_only.py"))
        bo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(bo)
        noise = [x for x in only_full if bo.classify(x)]
        print(f"   容器外且命中噪声规则的行：{len(noise)}")
        for x in noise[:6]:
            print(f"      - [{bo.classify(x)}] {x[:96]}")
        print(f"   容器外**未**命中规则的行（看是不是评论正文/推荐位）：{len(only_full)-len(noise)}")
        for x in [y for y in only_full if not bo.classify(y)][:6]:
            print(f"      ? {x[:96]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
