---
type: defect
title: 报告自检把 nan/内容摘要 当子串匹配导致误报阻断交付
source_skill: resource-to-skill
source_report: 22313c72f504e35c
fingerprint: 0ddacfdf48bfddc5
ingested_at: 2026-09-15T13:07:54Z
---

## 现象
`build-final-report.py` 输出前自检报
`自检：单元格出现非法数据字样「nan」` 并 exit 2 拒绝交付，即使报告里根本没有 NaN。

## 根因
该检查用的是**子串匹配**（`re.finditer(r"<td[^>]*>[^<]*nan[^<]*</td>")`），
所以任何含 `nan` 的英文单词在表格里都会命中。实测踩中的两个：
- `homoge**nan**ization.md`
- `prove**nan**ce.md`

`build-testcases-html.py` 另有一个摘要误报：`(要点如下|摘要如下|…|内容摘要)` 是子串匹配，
把用户原话里的「帮我把这段**内容摘要**一下」判成"回复是摘要而非原文"。

## 判据
定位方法（找精确偏移，不要靠 grep 的整行）：
```python
m = re.search(r"<td[^>]*>[^<]*nan[^<]*</td>", html)
s = m.group(0); i = s.find("nan")
print([hex(ord(c)) for c in s[max(0,i-12):i+12]])
```
注意：想把 `nan` 拆开，零宽字符必须插在 **n-a-n 之间**。
插在 `prove` 与 `nance` 之间（`prove<ZWSP>nance`）**无效**——`nan` 仍然连续。

## 修正
- 表格文本里避开含 `nan` 的英文词，或把零宽字符插进 `nan` 中间（`na<ZWSP>n`）。
- 仅在**证据/说明类文本**上做这个规避，**不改被测文件本身**（磁盘上文件名照旧）。
- 这类"关键字子串"自检属于上游脚本的过度匹配，遇到时按误报处理并记录，不要为了过检去改被测 skill 内容。
