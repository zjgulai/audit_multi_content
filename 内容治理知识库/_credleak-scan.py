#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""凭据泄漏只读扫描器（不写库、不读系统凭据文件）

判据两类：
  A 结构性凭据 —— 有固定格式的 secret（私钥块、AKIA、ghp_、sk-、JWT…），
    基本不存在"文档里本来就是这么写的"这种正当情形。
  B 赋值型凭据 —— password= / api_key: / secret_token 之类，
    文档里可能是在讲这个字段名，所以**只作疑似**，须人裁。

输出：命中位置 + 掩码值 + 指纹（前4后4 + 长度），不输出完整 secret。
"""
import hashlib
import os
import re
import sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else "kb"

# ---------- A 类：结构性凭据（高置信） ----------
STRUCT = [
    ("PRIVATE_KEY_BLOCK", re.compile(r"-----BEGIN[A-Z ]*PRIVATE KEY-----")),
    ("OPENSSH_PRIVATE", re.compile(r"-----BEGIN OPENSSH PRIVATE KEY-----")),
    ("PUTTY_PRIVATE", re.compile(r"PuTTY-User-Key-File-\d")),
    ("AWS_AKID", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("AWS_SECRET_CTX", re.compile(r"(?i)aws_secret_access_key\s*[=:]\s*['\"]?([A-Za-z0-9/+=]{40})")),
    ("GITHUB_TOKEN", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b")),
    ("GITLAB_TOKEN", re.compile(r"\bglpat-[A-Za-z0-9_\-]{20,}\b")),
    ("SLACK_TOKEN", re.compile(r"\bxox[abprs]-[A-Za-z0-9\-]{10,}\b")),
    ("OPENAI_KEY", re.compile(r"\bsk-[A-Za-z0-9]{20,}\b")),
    ("ANTHROPIC_KEY", re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{20,}\b")),
    ("STRIPE_KEY", re.compile(r"\b[sr]k_(?:live|test)_[A-Za-z0-9]{16,}\b")),
    ("GOOGLE_API_KEY", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b")),
    ("FEISHU_APP_TOKENish", re.compile(r"\b(?:u-|t-|cli_)[A-Za-z0-9]{16,}\b")),
    ("LARK_WEBHOOK", re.compile(r"open\.feishu\.cn/open-apis/bot/v2/hook/[0-9a-f\-]{30,}")),
    ("JWT", re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\b")),
    ("PEM_PUBKEY_BODY", re.compile(r"-----BEGIN (?:RSA |EC )?PUBLIC KEY-----")),
    ("SLACK_HOOK", re.compile(r"hooks\.slack\.com/services/[A-Za-z0-9/]{20,}")),
    ("NPM_TOKEN", re.compile(r"\bnpm_[A-Za-z0-9]{36}\b")),
    ("SENDGRID", re.compile(r"\bSG\.[A-Za-z0-9_\-]{22}\.[A-Za-z0-9_\-]{43}\b")),
]

# ---------- B 类：赋值型（疑似，须人裁） ----------
ASSIGN = [
    ("PASSWORD_ASSIGN", re.compile(r"(?i)\b(?:password|passwd|pwd)\s*[=:]\s*['\"]([^'\"\s]{6,})['\"]")),
    ("TOKEN_ASSIGN", re.compile(r"(?i)\b(?:api[_-]?key|access[_-]?token|secret[_-]?key|auth[_-]?token|app[_-]?secret)\s*[=:]\s*['\"]([A-Za-z0-9_\-/+=]{12,})['\"]")),
    ("BEARER", re.compile(r"(?i)\bBearer\s+([A-Za-z0-9_\-\.=]{20,})")),
    ("URI_WITH_CRED", re.compile(r"\b[a-z][a-z0-9+.\-]{2,}://([^/\s:@]{2,}):([^/\s@]{3,})@")),
    ("SSH_PRIV_PATH", re.compile(r"(?:^|[\s'\"`])(~|\$HOME|/Users/[A-Za-z0-9._\-]+)/\.ssh/id_(?:rsa|ed25519|ecdsa)\b")),
    ("CRED_FILE_PATH", re.compile(r"(?:^|[\s'\"`])(?:~|/Users/[A-Za-z0-9._\-]+)/\.dsh/credentials\b")),
    ("ENV_SECRET", re.compile(r"(?i)\b([A-Z0-9_]*(?:SECRET|TOKEN|PASSWORD|APIKEY|API_KEY|CREDENTIAL)[A-Z0-9_]*)=([^\s'\"]{6,})")),
]

TEXT_EXT = {".md", ".json", ".ndjson", ".jsonl", ".yaml", ".yml", ".txt",
            ".py", ".sh", ".csv", ".tsv", ".log", ".html", ".js", ".mjs",
            ".path", ".before", ".pre-edit", ".enveloped", ".err", ".bak",
            ".toml", ".ini", ".cfg", ".conf", ".mmd", ".gitkeep"}
MAXBYTES = 8 * 1024 * 1024


def mask(v):
    v = v.strip()
    if len(v) <= 8:
        return "*" * len(v)
    fp = hashlib.sha256(v.encode("utf-8", "replace")).hexdigest()[:10]
    return f"{v[:4]}…{v[-4:]} (len={len(v)}, fp={fp})"


def scan_file(path):
    try:
        if os.path.getsize(path) > MAXBYTES:
            return []
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            lines = fh.read().splitlines()
    except OSError:
        return []

    hits = []
    for i, line in enumerate(lines, 1):
        if len(line) > 4000:
            line_c = line[:4000]
        else:
            line_c = line
        for code, rx in STRUCT:
            for m in rx.finditer(line_c):
                hits.append(("A", code, path, i, mask(m.group(1) if m.groups() else m.group(0))))
        for code, rx in ASSIGN:
            for m in rx.finditer(line_c):
                g = m.group(1) if m.groups() else m.group(0)
                if len(m.groups()) >= 2 and m.group(2):
                    g = m.group(2)
                hits.append(("B", code, path, i, mask(g)))
    return hits


def main():
    all_hits = []
    nfiles = 0
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in (".git", "node_modules")]
        for fn in filenames:
            ext = os.path.splitext(fn)[1].lower()
            if ext not in TEXT_EXT:
                continue
            nfiles += 1
            all_hits.extend(scan_file(os.path.join(dirpath, fn)))

    print(f"# 扫描目录: {ROOT}")
    print(f"# 扫描文本文件数: {nfiles}")
    print(f"# A 类（结构性凭据）命中: {sum(1 for h in all_hits if h[0]=='A')}")
    print(f"# B 类（赋值型/路径类，疑似）命中: {sum(1 for h in all_hits if h[0]=='B')}")
    print()
    for cls in ("A", "B"):
        sub = [h for h in all_hits if h[0] == cls]
        if not sub:
            continue
        print(f"===== {cls} 类明细 =====")
        from collections import Counter
        for code, cnt in Counter(h[1] for h in sub).most_common():
            print(f"\n-- {code}  共 {cnt} 处")
            for h in [x for x in sub if x[1] == code][:25]:
                print(f"   {h[2]}:{h[3]}  ->  {h[4]}")
            if cnt > 25:
                print(f"   … 其余 {cnt-25} 处省略")


if __name__ == "__main__":
    main()
