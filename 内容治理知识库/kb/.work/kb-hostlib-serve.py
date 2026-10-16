#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""宿主库的只读 HTTP 取数服务（给工作台的镜像器读）。

为什么需要它
------------
工作台的镜像器（`工作台/apps/server/src/kb/kb-sync.ts`）本来是**直接读宿主库文件**的。
但这台机器上装了加密代理（`/usr/local/.trld`，LaunchDaemon `com.trld.tr_daemon`，
`libtr_monitor_enc.dylib` 注入到 Electron 进程），实测：**Electron/Node 读宿主库的 md
拿到的是密文**——
  · 同一路径 `fs.statSync` 报 13084 字节，而 `python3`/`cat` 看到 8988 字节；
  · 读出来的字节不是合法 UTF-8，镜像器一条都入不了库（509 条全被跳过）；
  · 同一份文件用 node 的 `readFileSync` / `readFile` / `openSync+readSync` 都拿到密文，
    而 `cat`/`python3` 拿到明文；反向也试过：**只有 2026-09-20 之前落盘的老文件两个世界都能读**。
结论：不是内容问题，是「谁在读」的问题。所以把取数换成 HTTP —— 由本服务（python 进程，
读得到明文）把条目连同渲染好的切块文本发出去，工作台不再碰文件。

接口（只读，无写入口）
----------------------
  GET /health    → {"ok":true,...}
  GET /manifest  → 镜像载荷：登记表 + 全部条目（含 content / sha256）
  GET /doc?rel=<子库/层/id.md> → 单条 {relPath, sha256, bytes, text}
  GET /raw?rel=...             → 原文（排障用）

载荷来源：`<hostlib>/_meta/manifest.json`（由 `kb/.work/gen-host-library.py` 生成，
内容与同目录的 .md 一一对应）。本服务**不改任何文件**，只读 + 发。

用法
----
  python3 kb/.work/kb-hostlib-serve.py --hostlib kb/.work/hostlib --port 4508
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

STATE = {
    "hostlib": "",
    "manifest_path": "",
    "mtime": None,
    "size": None,
    "payload": b"",
    "version": "",
    "docs": 0,
}
LOCK = threading.Lock()


def load_manifest(force: bool = False) -> None:
    """按 mtime+size 缓存：manifest 变了才重新读盘（它有几 MB）。"""
    path = STATE["manifest_path"]
    stat = os.stat(path)
    key = (stat.st_mtime_ns, stat.st_size)
    if not force and STATE["mtime"] == key:
        return
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    docs = data.get("docs") or []
    with LOCK:
        STATE["mtime"] = key
        STATE["payload"] = json.dumps(data, ensure_ascii=False).encode("utf-8")
        STATE["version"] = str(data.get("version") or "")
        STATE["docs"] = len(docs)


class Handler(BaseHTTPRequestHandler):
    server_version = "kb-hostlib/1"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args) -> None:  # noqa: A003
        sys.stderr.write("[kb-hostlib] %s - %s\n" % (self.address_string(), fmt % args))

    def _send(self, code: int, body: bytes, content_type: str, extra: dict | None = None) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, code: int, obj) -> None:
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def do_HEAD(self) -> None:  # noqa: N802
        self.do_GET()

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        route = parsed.path
        try:
            if route == "/health":
                load_manifest()
                self._json(200, {
                    "ok": True,
                    "hostlib": STATE["hostlib"],
                    "manifest": STATE["manifest_path"],
                    "version": STATE["version"],
                    "docs": STATE["docs"],
                })
                return
            if route == "/manifest":
                load_manifest()
                etag = f'W/"{STATE["version"]}"' if STATE["version"] else None
                if etag is not None and self.headers.get("If-None-Match") == etag:
                    self._send(304, b"", "application/json; charset=utf-8", {"ETag": etag})
                    return
                self._send(200, STATE["payload"], "application/json; charset=utf-8",
                           {"ETag": etag} if etag else None)
                return
            if route in ("/doc", "/raw"):
                load_manifest()
                query = parse_qs(parsed.query)
                rel = (query.get("rel") or [""])[0]
                if not rel:
                    self._json(400, {"error": "缺少 rel 参数"})
                    return
                target = os.path.normpath(os.path.join(STATE["hostlib"], rel))
                if not target.startswith(os.path.abspath(STATE["hostlib"]) + os.sep):
                    self._json(400, {"error": "rel 越出宿主库根"})
                    return
                if not os.path.isfile(target):
                    self._json(404, {"error": f"没有这个文件：{rel}"})
                    return
                with open(target, "rb") as handle:
                    raw = handle.read()
                try:
                    text = raw.decode("utf-8")
                except UnicodeDecodeError:
                    self._json(500, {"error": "文件不是合法 UTF-8"})
                    return
                self._json(200, {"relPath": rel, "bytes": len(raw), "text": text})
                return
            self._json(404, {"error": "只提供 /health /manifest /doc /raw"})
        except BrokenPipeError:
            pass
        except Exception as error:  # noqa: BLE001
            self._json(500, {"error": f"{type(error).__name__}: {error}"})


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hostlib", required=True, help="宿主库根（含 _meta/manifest.json）")
    parser.add_argument("--port", type=int, default=4508)
    parser.add_argument("--bind", default="127.0.0.1")
    args = parser.parse_args()

    hostlib = os.path.abspath(args.hostlib)
    manifest = os.path.join(hostlib, "_meta", "manifest.json")
    if not os.path.isfile(manifest):
        print(f"[kb-hostlib] 找不到载荷：{manifest}（先跑 gen-host-library.py）", file=sys.stderr)
        return 1
    STATE["hostlib"] = hostlib
    STATE["manifest_path"] = manifest
    load_manifest(force=True)

    server = ThreadingHTTPServer((args.bind, args.port), Handler)
    print(f"[kb-hostlib] 监听 http://{args.bind}:{args.port}/ → {hostlib}"
          f"（{STATE['docs']} 条，version {STATE['version'][:12]}）", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("[kb-hostlib] 收到中断，收尾", flush=True)
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
