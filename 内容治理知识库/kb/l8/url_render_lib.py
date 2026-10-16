#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""URL 渲染与取正文 —— **`url_text_rendered_v1` 口径的唯一实现**（共用件）。

## 为什么要有这个文件（2026-10-09，Owner 批「按口径分派核验器」）

实测病灶：L0 里 150 条活跃 url，**按 `sha256_input` 干净地分成两堆**——

    url_text_rendered_v1 103 条  ← 本文件这套管线（chrome --headless + 块级取文本）记的
    url_text_refresh_v1   40 条  ← 核验脚本那套（裸 HTTP + 去标签）记的

而 `verify_l0_urls.py` **只会裸 HTTP** ⇒ 那 103 条**结构上永远复现不出**，
对账只能写「recomputed_differ」，而它**读起来像「内容变了」**——**这是假信号**。
实测（2026-10-09 13:15）：`same 40 ／ recomputed_differ 100`，与上表分堆完全吻合。

⇒ 核验脚本必须**按台账记的口径分派管线**：`url_text_rendered_v1` 走本文件，
其余走裸 HTTP。**同一份实现只留一处**：本文件的 `render()` / `extract()` / 三个常量
是从 `kb/l8/recrawl_all_urls.py` **原样提出来的**，提出后由该脚本 import（不再各存一份）。

## 边界（照抄既有实现，不自创）

- `render()`：`stdout→文件`；文件大小连续 1.5s 不增长即认为渲染完，**立即 kill**
  （Chrome 不会自己退出）。`new` 模式失败/字数不足时由调用方降级到 `legacy`。
- `extract()`：去 script/style、块级标签转换行、去标签、**丢掉 <30 字的行**、
  丢掉代码味（`{};<>\\` 占比 > 0.04）的行、按序去重。
- **UA 可环境变量覆盖**（`L0_UA_NEW` / `L0_UA_SAFARI`）：实测**假 Chrome UA 会被
  fda.gov / CDC 整站拒**（连首页都 404）；需要时用环境变量指定，**不许在代码里再写死一份**。
"""
from __future__ import annotations

import html as H
import os
import re
import shutil
import subprocess
import time

# ★★ 2026-10-09 修正（Owner：「又开始不停的弹 chrome了」）——**本行原先指向完整 Google Chrome.app**。
#
# 病灶（实测）：macOS 上启动 `Google Chrome.app` 这个 **GUI app bundle** 必然在 Dock 出现
# Chrome 图标，而 `--headless=new` **消不掉**它（那不是"窗口"，是 app 的激活状态）。
# 本库的取数形态是「起一个 → 渲染完 kill → 再起一个」的循环（`fetch_rendered` 还要
# new→legacy 各跑一次）⇒ **Dock 图标不停闪**。实测 2026-10-08 一天建了 187 个临时 profile，
# 8 并发时任意时刻 45~47 个 Chrome 进程；2026-10-09 换 `verify_l0_urls.py` 走本文件后
# **同一个毛病立刻重现**（14:09 起跑，3 分钟内 37 个临时目录）。
#
# 改用 `chrome-headless-shell`：Chrome 官方专供无头的**独立二进制（不是 .app）**，
# 没有 GUI、**不进 Dock**。装法（机器上已装）：
#   https://googlechromelabs.github.io/chrome-for-testing/ → chrome-headless-shell-mac-arm64.zip
CHROME = os.environ.get(
    "KB_CHROME_BIN",
    "/Users/lute/.dsh/vendor/chrome-headless-shell-mac-arm64/chrome-headless-shell")
# 不许回落到 /Applications/Google Chrome.app —— 那正是本 bug。缺失时**报错，不静默降级**
# （缺证据必须可见）；换机器用环境变量 `KB_CHROME_BIN` 指定，**不要在代码里再写死第二份**。
UA_NEW = os.environ.get("L0_UA_NEW", ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/122 Safari/537.36"))
UA_SAFARI = os.environ.get("L0_UA_SAFARI", ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
             "(KHTML, like Gecko) Version/17.0 Safari/605.1.15"))


def render(url, mode):
    """stdout→文件；文件大小连续 1.5s 不增长即认为渲染完成，立即 kill（Chrome 不会自己退出）。

    ★ 2026-10-09 两处修正（与本文件头部的 CHROME 注释同批）：
      ① 去掉 `--headless=new` / `--headless` —— 现在用的是 `chrome-headless-shell`，
         **它本身就是无头二进制**，那几个 flag 是给完整 Chrome 用的（且正是弹 Dock 的来源）。
      ② 本次的临时 profile 与临时 html **在 finally 里删掉** —— 原先**从不清理**，
         实测积到 187 个目录 / 4.4 GB。（只清本函数自己建的那两个，不碰别人的 /tmp。）
    """
    if not os.path.exists(CHROME):
        raise RuntimeError(
            f"找不到无头 Chrome：{CHROME}\n"
            "  ★ 不许回落到 /Applications/Google Chrome.app —— 那是 GUI app bundle，"
            "每次启动都会在 macOS Dock 弹图标（2026-10-08/09 实测）。\n"
            "  装法见本文件顶部注释；或用环境变量 KB_CHROME_BIN 指定。")
    tag = abs(hash(url)) % 10**8
    tmp = f"/tmp/_chp_{os.getpid()}_{tag}.html"
    profile = f"/tmp/chp-{mode}-{tag}"
    if mode == "new":
        args = [CHROME, "--disable-gpu", "--no-sandbox",
                f"--user-data-dir={profile}", "--lang=en-US",
                "--virtual-time-budget=8000", f"--user-agent={UA_NEW}", "--dump-dom", url]
    else:
        args = [CHROME, "--disable-gpu", "--no-sandbox",
                f"--user-data-dir={profile}", "--lang=en-US", "--window-size=1440,900",
                "--virtual-time-budget=12000", f"--user-agent={UA_SAFARI}", "--dump-dom", url]
    cap, quiet = (30, 1.5) if mode == "new" else (40, 2.0)
    h = ""
    try:
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
                p.wait(timeout=5)
            except Exception:
                pass
        try:
            h = open(tmp, "rb").read().decode("utf-8", "ignore")
        except Exception:
            h = ""
    finally:
        try:
            os.remove(tmp)
        except Exception:
            pass
        shutil.rmtree(profile, ignore_errors=True)
    return h


def extract(h):
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


def http_get(url):
    """HTTP 直取（多数站点服务端渲染，1-2 秒即可）；失败返回空串。**与 recrawl 逐字相同。**"""
    import urllib.request
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA_NEW, "Accept-Language": "en,zh;q=0.8"})
        with urllib.request.urlopen(req, timeout=25) as r:
            raw = r.read()
        enc = "utf-8"
        m = re.search(rb'charset=["\']?([\w-]+)', raw[:4000], re.I)
        if m:
            enc = m.group(1).decode("ascii", "ignore")
        return extract(raw.decode(enc, "ignore"))
    except Exception:
        return ""


def fetch_text_like_recrawl(url, log=None):
    """**逐字复刻 `recrawl_all_urls.py::fetch_one()` 的取正文规则**，返回 `(text, method)`。

    ## 我第一版写错了，把教训留在这里（2026-10-09，实测打回）

    第一版叫 `fetch_rendered`，我凭「名字里有 rendered」就写成「**直接渲染**」，
    抽样复现只有 **same 1 / differ 3**。回去读 `fetch_one()` 才发现**真规则是两级**：

        ① 先 `http_get(url)`（裸 HTTP，1-2 秒）
        ② **只有** `len(text) < 500` 才上无头浏览器：`new` → 仍不足 500 再 `legacy`，取更长的那个

    ⇒ 被标成 `url_text_rendered_v1` 的行里，**很大一部分正文其实来自裸 HTTP**
    （HTTP 够 500 字就不上浏览器了，可口径名照旧写 rendered）。
    **跳过 HTTP 直接渲染 ⇒ 必然对不上**，而那会被读成「网页内容变了」——又是假信号。

    ★ **教训（比 bug 本身值钱）**：复用别人的口径，要复刻**它的判定规则**，
      不是复刻**它的名字**。名字是标签，规则才是口径。

    `log` 传一个可调用对象可拿到每步读数（`(step, chars)`）。
    """
    text, method = http_get(url), "http"
    if log:
        log("http", len(text))
    if len(text) < 500:
        for mode in ("new", "legacy"):
            if len(text) >= 500:
                break
            try:
                t = extract(render(url, mode))
            except Exception:
                t = ""
            if log:
                log(mode, len(t))
            if len(t) > len(text):
                text, method = t, mode
    return text, method
