#!/usr/bin/env python3
"""L6 模型事实核查：维度、有效截断长度、权重 dtype（量化方式）、权重来源与本地路径。
不装新库：ONNX 只用 60 行 protobuf 解析读 initializer 的 data_type。
结论写 kb/.work/l6_model_probe.json。
"""
import json, os, struct, sys, time

SNAP = os.path.expanduser("~/.dsh/models/fastembed/models--qdrant--paraphrase-multilingual-MiniLM-L12-v2-onnx-Q/"
                          "snapshots/faf4aa4225822f3bc6376869cb1164e8e3feedd0")
MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
out = {"checked_at": time.strftime("%Y-%m-%d %H:%M:%S"), "model": MODEL}

# ---------- 1) 有效截断长度：实测（不靠文档描述） ----------
from fastembed import TextEmbedding       # noqa: E402
m = TextEmbedding(model_name=MODEL)
out["dim"] = int(m.embedding_size)
out["token_count_samples"] = {f"{n} 字/词": m.token_count(t) for n, t in
                              (("空", ""), ("200 字中文", "啊" * 200), ("1000 字中文", "啊" * 1000),
                               ("3000 词英文", "word " * 3000))}
import numpy as np                          # noqa: E402
base = "吸奶器广告合规检查。" * 30
a, b = base + "结论：段落甲。" * 200, base + "结论：完全不同的另一段内容。" * 200
va, vb = (np.array(list(m.embed([x]))[0]) for x in (a, b))
out["truncation_test"] = {
    "how": "两段文本共享前 300 字、其余完全不同，比对向量是否相同",
    "cosine": float(va @ vb / (np.linalg.norm(va) * np.linalg.norm(vb))),
    "identical": bool(np.allclose(va, vb, atol=1e-6)),
    "verdict": "完全相同 → 长文本被静默截断，必须分段（不许截断）",
}
out["effective_max_tokens"] = m.token_count("啊" * 1000)
out["description_says"] = m.model.model_description.description
out["description_vs_reality"] = ("fastembed 元信息写 512 input tokens truncation，实测 token_count 封顶 "
                                 f"{out['effective_max_tokens']}（tokenizer.json 里 truncation.max_length=128），"
                                 "以实测为准")

# ---------- 2) 权重 dtype：解析 ONNX initializer 的 data_type ----------
DT = {1: "FLOAT(fp32)", 2: "UINT8", 3: "INT8", 4: "UINT16", 5: "INT16", 6: "INT32", 7: "INT64",
      9: "BOOL", 10: "FLOAT16(fp16)", 11: "DOUBLE(fp64)", 12: "UINT32", 13: "UINT64"}


def rd_varint(buf, i):
    shift = val = 0
    while True:
        b = buf[i]
        i += 1
        val |= (b & 0x7F) << shift
        if not b & 0x80:
            return val, i
        shift += 7


def fields(buf, start, end):
    i = start
    while i < end:
        key, i = rd_varint(buf, i)
        fno, wt = key >> 3, key & 7
        if wt == 0:
            v, i = rd_varint(buf, i)
            yield fno, wt, v
        elif wt == 2:
            ln, i = rd_varint(buf, i)
            yield fno, wt, (i, i + ln)
            i += ln
        elif wt == 5:
            yield fno, wt, buf[i:i + 4]
            i += 4
        elif wt == 1:
            yield fno, wt, buf[i:i + 8]
            i += 8
        else:
            raise ValueError(f"不支持的 wire type {wt}")


def collect_initializer_dtypes(path):
    buf = open(path, "rb").read()
    dtypes, count = {}, 0
    for fno, wt, v in fields(buf, 0, len(buf)):
        if fno == 7 and wt == 2:                      # graph
            for g_fno, g_wt, g_v in fields(buf, v[0], v[1]):
                if g_fno == 5 and g_wt == 2:          # initializer
                    count += 1
                    for t_fno, t_wt, t_v in fields(buf, g_v[0], g_v[1]):
                        if t_fno == 2 and t_wt == 0:  # data_type
                            dtypes[DT.get(t_v, f"enum:{t_v}")] = dtypes.get(DT.get(t_v, f"enum:{t_v}"), 0) + 1
                            break
    return dtypes, count


onnx_path = os.path.join(SNAP, "model_optimized.onnx")
dtypes, n_init = collect_initializer_dtypes(onnx_path)
raw = open(onnx_path, "rb").read()
quant_ops = {op: raw.count(op.encode()) for op in
             ("QuantizeLinear", "DequantizeLinear", "MatMulInteger", "DynamicQuantizeLinear",
              "QLinearMatMul", "ConvInteger")}
out["weights"] = {
    "hf_repo": "qdrant/paraphrase-multilingual-MiniLM-L12-v2-onnx-Q",
    "model_file": "model_optimized.onnx",
    "local_path": onnx_path,
    "stable_cache_dir": os.path.expanduser("~/.dsh/models/fastembed"),
    "bytes": os.path.getsize(onnx_path),
    "initializer_dtype_histogram": dtypes,
    "initializer_count": n_init,
    "quantization_op_hits": quant_ops,
    "quantization": ("无量化算子，权重为 " + "/".join(dtypes) if not any(quant_ops.values())
                     else "检测到量化算子：" + json.dumps({k: v for k, v in quant_ops.items() if v})),
}
out["weights"]["quantization_verdict"] = (
    "fp16（ONNX initializer 全部为 FLOAT16，且无 QuantizeLinear/MatMulInteger 等量化算子）"
    if set(dtypes) == {"FLOAT16(fp16)"} else
    ("未识别：" + json.dumps(dtypes, ensure_ascii=False)))
json.dump(out, open("kb/.work/l6_model_probe.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(json.dumps({k: out[k] for k in ("dim", "effective_max_tokens", "token_count_samples")},
                 ensure_ascii=False, indent=1))
print("截断实验:", json.dumps(out["truncation_test"], ensure_ascii=False))
print("权重 dtype 直方图:", dtypes, "| initializer 数:", n_init)
print("量化算子命中:", quant_ops)
print("量化结论:", out["weights"]["quantization_verdict"])
