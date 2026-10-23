---
id: cg-vid-720e0d64d92fdd40
title: "[VID-H36pbQup] 视频画面文字与口播：Video.mov"
collection: 2_内部正负样本库
kb_class: [内部正负样本库]
tier: L1
topic: H36pbQupBop2
kind: fact
summary: "https://momcozy-in.feishu.cn/wiki/NPKldCDgZomiyjxF6OMcVnDxnBQ 内嵌视频「Video.mov」：画面文字 10 段 / 142 字（带 `#t.` 时间码，时长 38.13s）＋口播转写 307 字（本机 ASR，**无时间码**）"
owner: 刘华丽
evidence_level: L1
data_level: L2
sensitivity_level: L2
half_life_days: 180
created_at: 2026-10-22
valid_until: 2027-04-20
asks:
  - 这条视频（Video.mov）画面里出现了哪些文字
  - 某个时间点画面上写的是什么
  - 这条视频（Video.mov）口播说了什么
  - 画面文字与口播是否一致
not_proves: "画面文字只覆盖**画面上出现的字**，口播转写只覆盖**音轨里说的话** —— 两者都**不含画面内容判定**（婴幼儿安全、产品用法、隐私等画面风险走「视频安全审查」）；**口播转写没有逐句时间码**，不能按时间定位，且 ASR 可能误识别、不能当逐字原文引用；不能证明时效（视频可能已改版）；不能证明该条已过正式验收；不能替代合规/法务意见"
forbidden: "不许把画面文字当口播转写用（反之亦然）；不许把口播转写当逐字原文引用（ASR 有误识别，`script_mismatch` 时尤其）；不许据本条直接判 BLOCK/PASS；不许把派生视图的字段改动当成新库改动（视图不写回）"
---

# 视频画面文字与口播转写：Video.mov

- 所属材料：wiki:NPKldCDgZomiyjxF6OMcVnDxnBQ
- 材料地址：https://momcozy-in.feishu.cn/wiki/NPKldCDgZomiyjxF6OMcVnDxnBQ
- 视频文件：kb/l0/attachments/视频/H36pbQupBop2mcxD__Video.mov
- 时长 38.13s ｜ 220×480 ｜ h264
- 抽取方式：`ffmpeg(scene)+macOS Vision`（16 帧 → 10 段画面文字）

## 画面文字（按时间窗，锚点可回源）

- `#t.00:00:03-00:00:33`　10:394
- `#t.00:00:05-00:00:08`　10:394 41888 00:04
- `#t.00:00:08-00:00:11`　10:394 41888 00:08
- `#t.00:00:21-00:00:21`　10:394 COSI
- `#t.00:00:23-00:00:31`　10:394 41588
- `#t.00:00:25-00:00:26`　€ 00 10:394
- `#t.00:00:26-00:00:29`　10:394 11 88
- `#t.00:00:33-00:00:34`　10:394 00%
- `#t.00:00:34-00:00:36`　10:394 00:34
- `#t.00:00:36-00:00:37`　10:394 •1/-88 momcozy Wellness 1

## 口播转写（本机 ASR）

- 语种 `zh-CN` ｜ 307 字 ｜ `macOS Speech.framework（本机、on-device）`
- 语种判读：样本里可判字符只有 19 个（< 20）⇒ **语种未定**，按默认语序试 zh-CN → en-US

没买we postcard Max beans is westwan my big paradise safe second baby the away change paint for someone price who look can sometimes eat people dont want than control her pot action for and five parts foot one and five once啥子中的磅礴色的八年才33栋熟肉Lex in Christ Max splay so you luckin fire panda be there that the one

> **口播转写**由 `macOS Speech.framework` **本机**完成（on-device、不出机器），
> **没有逐句时间码** —— 不能按时间定位；ASR 可能误识别，不能当逐字原文引用。
> **画面文字**那半**有** `#t.` 时间码，可定位到秒。案例只作参照，不构成规则。