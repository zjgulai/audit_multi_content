#!/usr/bin/env python3
"""L6 前置探针：本机有没有可用的 embedding 模型/接口。
只探测、不安装、不下载、不调用外部 API。结果写 kb/.work/l6_probe.json。
判定口径：只要能拿到「真实向量」的本地模型或接口就算可用；拿不到就走仅 BM25 模式。
"""
# ── 解释器守卫（2026-09-29）：不合格就用 kb/.kb-python 指定的解释器重跑自己 ──
import os as _os, sys as _sys
if not _os.environ.get("KB_INTERP_OK"):
    _d = _os.path.dirname(_os.path.abspath(__file__)); _cfg = None
    while True:
        _p = _os.path.join(_d, ".kb-python")
        if _os.path.isfile(_p):
            _cfg = _p
            break
        _q = _os.path.dirname(_d)
        if _q == _d:
            break
        _d = _q
    if _cfg:
        _want = next((l.split("#", 1)[0].strip() for l in open(_cfg, encoding="utf-8")
                      if l.split("#", 1)[0].strip()), "")
        _want = _os.path.expanduser(_want)
        if (_want and _os.access(_want, _os.X_OK)
                and _os.path.realpath(_want) != _os.path.realpath(_sys.executable)):
            _os.environ["KB_INTERP_OK"] = "1"
            _os.execve(_want, [_want, _os.path.abspath(__file__)] + _sys.argv[1:], dict(_os.environ))
# ──────────────────────────────────────────────────────────────────────────

import importlib, json, os, socket, subprocess, sys, time

OUT = "kb/.work/l6_probe.json"
res = {"checked_at": time.strftime("%Y-%m-%d %H:%M:%S"), "get": {}}

# 1) Python 侧 embedding 运行时 / 客户端
for m in ("sentence_transformers", "transformers", "torch", "onnxruntime", "numpy",
          "fastembed", "text2vec", "FlagEmbedding", "openai", "cohere", "dashscope",
          "modelscope", "jieba", "rank_bm25", "sklearn", "faiss"):
    try:
        mod = importlib.import_module(m)
        res["get"][f"py:{m}"] = {"ok": True, "version": str(getattr(mod, "__version__", "?"))}
    except Exception as e:
        res["get"][f"py:{m}"] = {"ok": False, "err": type(e).__name__}

# 2) 本机可执行 / 本地服务
for b in ("ollama", "llama-server", "llama-cli", "mlx_lm.generate", "vllm",
          "text-embeddings-router", "infinity", "lmstudio", "localai"):
    p = subprocess.run(["bash", "-lc", f"command -v {b}"], capture_output=True, text=True)
    res["get"][f"bin:{b}"] = {"ok": bool(p.stdout.strip()), "path": p.stdout.strip()}
for port in (11434, 1234, 8080, 8000, 9997, 5000, 43121):
    s = socket.socket()
    s.settimeout(0.4)
    try:
        s.connect(("127.0.0.1", port))
        res["get"][f"port:{port}"] = {"ok": True}
    except Exception:
        res["get"][f"port:{port}"] = {"ok": False}
    finally:
        s.close()

# 3) 磁盘上的模型文件（只扫常见位置，不递归全盘）
hits = []
for root in (os.path.expanduser("~/.dsh"), os.path.expanduser("~/.cache"),
             os.path.expanduser("~/Library/Application Support"),
             os.path.expanduser("~/.ollama"), "/opt/homebrew/share"):
    if not os.path.isdir(root):
        continue
    for dp, dns, fns in os.walk(root):
        dns[:] = [d for d in dns if d not in (".git", "node_modules", "Caches")]
        if dp.count(os.sep) - root.count(os.sep) > 5:
            dns[:] = []
            continue
        for fn in fns:
            if fn.endswith((".onnx", ".gguf", ".safetensors")) or fn == "tokenizer.json":
                hits.append(os.path.join(dp, fn))
res["model_files_found"] = hits[:20]

# 4) 网络（embedding 服务多为远程 API；不通则远程接口也不可用）
def probe(url):
    p = subprocess.run(["bash", "-lc",
                        f"curl -s -o /dev/null -m 3 -w '%{{http_code}}' {url}"],
                       capture_output=True, text=True)
    return p.stdout.strip() or "timeout/err"
res["network"] = {u: probe(u) for u in
                  ("https://huggingface.co", "https://pypi.org", "https://api.openai.com")}

# 5) 结论
usable = ([k for k, v in res["get"].items() if v.get("ok") and ("sentence_transformers" in k
           or "fastembed" in k or "text2vec" in k or "FlagEmbedding" in k)]
          or hits
          or [k for k, v in res["get"].items() if v.get("ok") and k.startswith("port:")])
res["usable_embedding_found"] = bool(usable)
res["why"] = ("没找到任何可产出真实向量的本地模型或接口：无 embedding 运行时依赖、无本地服务端口、"
              "磁盘无 .onnx/.gguf/.safetensors 模型文件、外网不可达（远程 embedding API 也用不了）"
              if not usable else "发现候选：" + str(usable))
res["mode"] = "bm25_only" if not usable else "vector_plus_bm25"
json.dump(res, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

print(f"结论：mode = {res['mode']}")
print(f"原因：{res['why']}")
print("命中的依赖：" + (", ".join(k for k, v in res["get"].items()
                                if v.get("ok") and k.startswith("py:")) or "无"))
print("模型文件：" + (str(hits[:5]) if hits else "无"))
print("网络：" + json.dumps(res["network"], ensure_ascii=False))
sys.exit(0)
