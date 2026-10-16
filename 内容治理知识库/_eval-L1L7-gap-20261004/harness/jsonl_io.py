# -*- coding: utf-8 -*-
"""容错读取：兼容「单个 JSON 数组」与「JSONL」混写的中间文件。"""
import json


def read_records(path):
    if not path:
        return []
    try:
        text = open(path, encoding="utf-8").read()
    except FileNotFoundError:
        return []
    dec = json.JSONDecoder()
    out, i, n = [], 0, len(text)
    while i < n:
        while i < n and text[i] in " \t\r\n":
            i += 1
        if i >= n:
            break
        try:
            obj, j = dec.raw_decode(text, i)
        except ValueError:
            k = text.find("\n", i)
            if k < 0:
                break
            i = k + 1
            continue
        out.extend(obj if isinstance(obj, list) else [obj])
        i = j
    return out
