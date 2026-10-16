#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""凭据泄漏只读扫描器（快版：字面量预筛 -> 正则命中）
不读任何系统凭据文件；命中值掩码化输出。
"""
import hashlib, os, re, sys, time

ROOT = sys.argv[1] if len(sys.argv) > 1 else "kb"
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".pytest_cache", ".mypy_cache"}
MAXBYTES = 2 * 1024 * 1024

# 字面量预筛：文件里一个都不含 -> 直接跳过（快几个数量级）
NEEDLES = [b"-----BEGIN", b"AKIA", b"ASIA", b"ghp_", b"gho_", b"ghs_", b"ghr_",
           b"glpat-", b"xox", b"sk-", b"sk_", b"rk_live", b"sk_live", b"AIza",
           b"eyJ", b"hooks.slack.com", b"open-apis/bot/v2/hook", b"SG.",
           b"npm_", b"PuTTY-User-Key", b"password", b"passwd", b"pwd", b"api_key",
           b"apikey", b"secret", b"token", b"Bearer", b"bearer", b"credential",
           b"id_rsa", b"id_ed25519", b"id_ecdsa", b".ssh", b"/etc/passwd",
           b"/etc/shadow", b"://", b"AKID", b"SECRET", b"TOKEN"]

STRUCT = [
    ("PRIVATE_KEY_BLOCK", re.compile(r"-----BEGIN[A-Z ]*PRIVATE KEY-----")),
    ("OPENSSH_PRIVATE", re.compile(r"-----BEGIN OPENSSH PRIVATE KEY-----")),
    ("PUTTY_PRIVATE", re.compile(r"PuTTY-User-Key-File-\d")),
    ("AWS_AKID", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("AWS_SECRET", re.compile(r"(?i)aws_secret_access_key\s*[=:]\s*['\"]?([A-Za-z0-9/+=]{40})")),
    ("GITHUB_TOKEN", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b")),
    ("GITLAB_TOKEN", re.compile(r"\bglpat-[A-Za-z0-9_\-]{20,}\b")),
    ("SLACK_TOKEN", re.compile(r"\bxox[abprs]-[A-Za-z0-9\-]{10,}\b")),
    ("OPENAI_KEY", re.compile(r"\bsk-[A-Za-z0-9]{20,}\b")),
    ("ANTHROPIC_KEY", re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{20,}\b")),
    ("STRIPE_KEY", re.compile(r"\b[sr]k_(?:live|test)_[A-Za-z0-9]{16,}\b")),
    ("GOOGLE_API_KEY", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b")),
    ("LARK_WEBHOOK", re.compile(r"open\.feishu\.cn/open-apis/bot/v2/hook/[0-9a-f\-]{30,}")),
    ("JWT", re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\b")),
    ("SLACK_HOOK", re.compile(r"hooks\.slack\.com/services/[A-Za-z0-9/]{20,}")),
    ("NPM_TOKEN", re.compile(r"\bnpm_[A-Za-z0-9]{36}\b")),
    ("SENDGRID", re.compile(r"\bSG\.[A-Za-z0-9_\-]{22}\.[A-Za-z0-9_\-]{43}\b")),
]
ASSIGN = [
    ("PASSWORD_ASSIGN", re.compile(r"(?i)\b(?:password|passwd|pwd)\s*[=:]\s*['\"]([^'\"\s]{6,})['\"]")),
    ("TOKEN_ASSIGN", re.compile(r"(?i)\b(?:api[_-]?key|access[_-]?token|secret[_-]?key|auth[_-]?token|app[_-]?secret)\s*[=:]\s*['\"]([A-Za-z0-9_\-/+=]{12,})['\"]")),
    ("BEARER", re.compile(r"(?i)\bBearer\s+([A-Za-z0-9_\-\.=]{20,})")),
    ("URI_WITH_CRED", re.compile(r"\b[a-z][a-z0-9+.\-]{2,}://([^/\s:@]{2,}):([^/\s@]{3,})@")),
    ("SSH_PRIV_PATH", re.compile(r"(?:^|[\s'\"`])(~|\$HOME|/Users/[A-Za-z0-9._\-]+)/\.ssh/id_(?:rsa|ed25519|ecdsa)\b")),
    ("CRED_FILE_PATH", re.compile(r"(?:^|[\s'\"`])(?:~|/Users/[A-Za-z0-9._\-]+)/\.dsh/credentials\b")),
    ("SYS_PASSWD_PATH", re.compile(r"(?:^|[\s'\"`])/etc/(?:passwd|shadow)\b")),
    ("ENV_SECRET", re.compile(r"\b([A-Z][A-Z0-9_]*(?:SECRET|TOKEN|PASSWORD|APIKEY|API_KEY|CREDENTIAL)[A-Z0-9_]*)=")),
]

def mask(v):
    v = v.strip()
    if len(v) <= 8:
        return "*" * min(len(v), 12)
    return f"{v[:4]}…{v[-4:]} (len={len(v)}, fp={hashlib.sha256(v.encode('utf-8','replace')).hexdigest()[:10]})"

def main():
    t0 = time.time()
    hits, nfiles, nskipped, nscanned = [], 0, 0, 0
    for dp, dns, fns in os.walk(ROOT):
        dns[:] = [d for d in dns if d not in SKIP_DIRS]
        for fn in fns:
            p = os.path.join(dp, fn)
            try:
                sz = os.path.getsize(p)
            except OSError:
                continue
            nfiles += 1
            if sz > MAXBYTES:
                nskipped += 1
                continue
            try:
                with open(p, "rb") as fh:
                    raw = fh.read()
            except OSError:
                continue
            if not any(n in raw for n in NEEDLES):
                continue
            nscanned += 1
            text = raw.decode("utf-8", "replace")
            for i, line in enumerate(text.splitlines(), 1):
                lc = line[:4000]
                for code, rx in STRUCT:
                    for m in rx.finditer(lc):
                        hits.append(("A", code, p, i, mask(m.group(1) if m.groups() else m.group(0))))
                for code, rx in ASSIGN:
                    for m in rx.finditer(lc):
                        g = m.group(1) if m.groups() else m.group(0)
                        if len(m.groups()) >= 2 and m.group(2):
                            g = m.group(2)
                        hits.append(("B", code, p, i, mask(g)))
    print(f"# ROOT={ROOT}  文件总数={nfiles}  超 {MAXBYTES} 字节跳过={nskipped}  实际细扫={nscanned}")
    print(f"# 耗时 {time.time()-t0:.1f}s")
    for cls, label in (("A", "结构性凭据(高置信)"), ("B", "赋值/路径型(疑似)")):
        sub = [h for h in hits if h[0] == cls]
        print(f"# {cls} 类 {label}: {len(sub)} 处")
    print()
    from collections import Counter
    for cls in ("A", "B"):
        sub = [h for h in hits if h[0] == cls]
        if not sub:
            continue
        print(f"===== {cls} 类明细 =====")
        for code, cnt in Counter(h[1] for h in sub).most_common():
            print(f"\n-- {code}  共 {cnt} 处")
            for h in [x for x in sub if x[1] == code][:30]:
                print(f"   {h[2]}:{h[3]}  ->  {h[4]}")
            if cnt > 30:
                print(f"   … 其余 {cnt-30} 处省略")

main()
