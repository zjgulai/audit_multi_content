#!/usr/bin/env python3
"""
serve-lan.py - 在局域网提供评测交付物 HTTP 访问

启动一个绑定 0.0.0.0 的静态文件服务器，使同一局域网内的设备
（手机/平板/其他电脑）都能通过 http://<局域网IP>:<端口>/ 打开
评测 HTML 报告、过程文档、Excel 等交付物。

用法:
    python3 scripts/serve-lan.py --dir <交付目录> --port 8000

输出:
    - 本机可访问链接: http://127.0.0.1:8000/
    - 局域网链接:     http://192.168.x.x:8000/{skill-name}-evaluation-report.html

说明:
    - 绑定 0.0.0.0（所有网卡），自动探测局域网 IP（优先 en0/en1 的 IPv4）。
    - 按 Ctrl+C 停止；也可加 --daemon 转后台运行并把 PID 写入 pid 文件。
    - 安全提示：仅建议在可信局域网内使用；默认只读静态服务，不执行脚本。
"""

from __future__ import annotations

import argparse
import os
import signal
import socket
import subprocess
import sys
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


def get_lan_ips() -> list[str]:
    """探测本机局域网 IPv4 地址（macOS/Linux/WSL 通用）。"""
    ips: list[str] = []

    # 方式 1: ipconfig / ip addr / hostname -I
    candidates = [
        (["ipconfig", "getifaddr", "en0"], "darwin"),
        (["ipconfig", "getifaddr", "en1"], "darwin"),
        (["hostname", "-I"], "linux"),
        (["ip", "-4", "addr", "show", "scope", "global"], "linux"),
    ]
    for cmd, _os in candidates:
        if sys.platform != _os and not (_os == "linux" and "linux" in sys.platform):
            continue
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=3).stdout
            for tok in out.split():
                if tok.count(".") == 3 and not tok.startswith("127."):
                    ip = tok.split("/")[0]
                    if ip not in ips:
                        ips.append(ip)
        except Exception:
            pass

    # 方式 2: UDP socket 探测（不需要真实发包）
    if not ips:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("10.255.255.255", 1))  # 不实际发送
            ip = s.getsockname()[0]
            s.close()
            if ip and not ip.startswith("127."):
                ips.append(ip)
        except Exception:
            pass

    return ips


def run_server(directory: Path, port: int, daemon: bool = False, pidfile: Path | None = None) -> None:
    if daemon:
        # 转后台运行：fork 子进程并退出父进程
        pid = os.fork()
        if pid > 0:
            print(f"[ok] 服务已在后台启动（PID {pid}），日志: {pidfile}.log")
            if pidfile:
                pidfile.write_text(str(pid), encoding="utf-8")
            return
        if pidfile:
            pidfile.write_text(str(os.getpid()), encoding="utf-8")

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(directory), **kwargs)

        def log_message(self, fmt, *msg):
            sys.stderr.write(f"[{self.log_date_time_string()}] {fmt % msg}\n")

    os.chdir(directory)
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    lan_ips = get_lan_ips()
    print("=" * 64)
    print("✅ 评测交付 HTTP 服务已启动（绑定 0.0.0.0，局域网可访问）")
    print(f"   目录: {directory}")
    print(f"   本机: http://127.0.0.1:{port}/")
    for ip in lan_ips:
        print(f"   局域网: http://{ip}:{port}/")
    print("   交付物示例:")
    for f in sorted(directory.glob("*.html"))[:10]:
        print(f"     http://{lan_ips[0] if lan_ips else '127.0.0.1'}:{port}/{f.name}")
    print("   Ctrl+C 停止服务")
    print("=" * 64)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[info] 服务已停止")
    finally:
        server.server_close()


def main() -> None:
    parser = argparse.ArgumentParser(description="局域网评测交付 HTTP 服务")
    parser.add_argument("--dir", type=Path, default=Path.cwd(), help="交付目录（默认当前目录）")
    parser.add_argument("--port", type=int, default=8000, help="端口（默认 8000）")
    parser.add_argument("--daemon", action="store_true", help="后台运行")
    parser.add_argument("--pidfile", type=Path, help="PID 文件路径（配合 --daemon）")
    args = parser.parse_args()

    if not args.dir.exists():
        print(f"[error] 目录不存在: {args.dir}")
        sys.exit(1)
    run_server(args.dir, args.port, daemon=args.daemon, pidfile=args.pidfile)


if __name__ == "__main__":
    main()
