---
id: cg-vid-b3b320f236dc86f3
title: "[VID-OTHmbtOK] 视频画面文字与口播：WhatsApp Video 2026-09-15 at 22.34.44.mp4"
collection: 2_内部正负样本库
kb_class: [内部正负样本库]
tier: L1
topic: OTHmbtOKVo8n
kind: fact
summary: "https://momcozy-in.feishu.cn/wiki/YNnwdkTULoJLccxKnypcHwsinBZ 内嵌视频「WhatsApp Video 2026-09-15 at 22.34.44.mp4」：画面文字 7 段 / 188 字（带 `#t.` 时间码，时长 81.78s）；**尚无口播转写**（原因见正文）"
owner: 刘华丽
evidence_level: L1
data_level: L2
sensitivity_level: L2
half_life_days: 180
created_at: 2026-10-16
valid_until: 2027-04-14
asks:
  - 这条视频（WhatsApp Video 2026-09-15 at 22.34.44.mp4）画面里出现了哪些文字
  - 某个时间点画面上写的是什么
  - 这条视频（WhatsApp Video 2026-09-15 at 22.34.44.mp4）口播说了什么
  - 画面文字与口播是否一致
not_proves: "画面文字只覆盖**画面上出现的字**，口播转写只覆盖**音轨里说的话** —— 两者都**不含画面内容判定**（婴幼儿安全、产品用法、隐私等画面风险走「视频安全审查」）；**口播转写没有逐句时间码**，不能按时间定位，且 ASR 可能误识别、不能当逐字原文引用；不能证明时效（视频可能已改版）；不能证明该条已过正式验收；不能替代合规/法务意见"
forbidden: "不许把画面文字当口播转写用（反之亦然）；不许把口播转写当逐字原文引用（ASR 有误识别，`script_mismatch` 时尤其）；不许据本条直接判 BLOCK/PASS；不许把派生视图的字段改动当成新库改动（视图不写回）"
---

# 视频画面文字与口播转写：WhatsApp Video 2026-09-15 at 22.34.44.mp4

- 所属材料：wiki:YNnwdkTULoJLccxKnypcHwsinBZ
- 材料地址：https://momcozy-in.feishu.cn/wiki/YNnwdkTULoJLccxKnypcHwsinBZ
- 视频文件：kb/l0/attachments/视频/OTHmbtOKVo8nRSxD__WhatsApp_Video_2026-09-15_at_22.34.44.mp4
- 时长 81.78s ｜ 464×832 ｜ h264
- 抽取方式：`ffmpeg(scene)+macOS Vision`（21 帧 → 7 段画面文字）

## 画面文字（按时间窗，锚点可回源）

- `#t.00:00:25-00:00:33`　5-Zone Suction-Synced Massage
- `#t.00:00:39-00:00:48`　Double-Layer Flange
- `#t.00:00:48-00:00:51`　- 180 - 120 / 6 oz vs. 5 oz Capacity
- `#t.00:00:51-00:00:53`　6 oz vs. 5 oz Capacity
- `#t.00:00:53-00:00:54`　Bak 6 oz vs. 5 oz Capacity
- `#t.00:00:54-00:00:55`　6 ozas. 5 or Capacity
- `#t.00:01:11-00:01:17`　ORT' Up to 10 Pumping-Only Sessions

## 口播转写（本机 ASR）

- 本视频**尚无口播转写**：音轨里没有人说话（**读数**，不是失败）

> **口播转写**由 `macOS Speech.framework` **本机**完成（on-device、不出机器），
> **没有逐句时间码** —— 不能按时间定位；ASR 可能误识别，不能当逐字原文引用。
> **画面文字**那半**有** `#t.` 时间码，可定位到秒。案例只作参照，不构成规则。