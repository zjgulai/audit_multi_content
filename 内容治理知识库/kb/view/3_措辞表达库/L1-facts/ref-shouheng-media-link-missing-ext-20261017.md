---
asks:
  - 报告里「图片 1：点开查看」点开后无法查看，真因是什么
  - 为什么权限读数是 tenant_readable、文件字节也是好的，链接却仍然是死链
  - 只改名（不重传）为什么能修好旧链接、重传为什么不行
  - 上传到云空间的文件名该怎么起（为什么要从魔数认类型）
  - 取图那一跳为什么把字节存成 .img，扩展名又从哪来
  - 「能打开」这件事由几个条件合成、各自该怎么量
  - 改名前后的三条旧素材最后是什么状态（能否预览、权限多少）
  - 1060007 与 1060006 分别意味着什么
collection: 3_措辞表达库
corroborated_by:
  - /Users/lute/Project/audit_multi_content/PMO/守衡-媒材链接点不开-扩展名-20261017.md（三步追因、三条旧文件修复回读）
  - /Users/lute/Project/audit_multi_content/tools/agent/media_link.mjs（magicExt / withMagicExt 与上传那一跳的接线）
  - /Users/lute/Project/audit_multi_content/tools/agent/media_link.test.mjs（M6a–M6d 四条，含反向对照）
  - https://momcozy-in.feishu.cn/file/VOcQboBNIoU6HyxAygzcT3cQnGe（改名后 preview ok、tenant_readable）
created_at: 2026-10-17
data_level: L2
evidence_group: evidence
evidence_level: L2
forbidden: 不许据本条判断某张图能不能过审；不许拿「权限对」当「链接能点开」（本条就是在纠这个）；不许为了修旧链接而重传媒材（会换 token，旧链接更死）；不许把扩展名硬写成固定值（必须从字节魔数认，认不出就不加）。
half_life_days: 90
id: ref-shouheng-media-link-missing-ext-20261017
kb_class: []
kind: fact
not_proves: 不能证明所有历史媒材链接都修好了（只修了台账里出现过的三条）；不能证明飞书以后不会按别的规则判类型（它描述的是 2026-10-17 这一版行为）；不能证明视频那一档也一定能预览（只补了扩展名，没做截帧）；不能证明「名字对了就一定打得开」—— 飞书不认识的格式仍可能只能下载不能预览，目前没有实例；不能替代 3_措辞表达库 的任何条款。
owner: 刘华丽
pii:
  detected: false
  masked: false
  strategy: 未检出自然人信息：正文为文件类型与权限读数；含云空间文件 token（非个人数据）
provenance:
  anchor: PMO/守衡-媒材链接点不开-扩展名-20261017.md#一、真因（三步追到底，不是猜）
  confidence: 确定
sensitivity_level: L2
source:
  captured_at: 2026-10-17
  fingerprint: 2a6f42d6ed8219a1
  kind: file
  ref: /Users/lute/Project/audit_multi_content/PMO/守衡-媒材链接点不开-扩展名-20261017.md
summary: Owner 报「图片 1：点开查看 —— 点击后无法查看」。三步追因：文件本身完好（下回来 83,421 字节、魔数 ff d8 ff e0 … JFIF 的好 JPEG）；权限也对了（link_share_entity = tenant_readable）；但 drive +preview 回 1060006 file type does not support preview —— 真因是上传到云空间的文件叫「守衡送审素材-image-1」、没扩展名，飞书把它当未知二进制。决定性验证：同一个 token 只改名加 .jpg（不动字节、不换 token）预览立刻通过，所以已发出的卡片、报告、表里的旧链接全都照样可用。根因链：取图那一跳故意把字节存成 .img（不让它在临时目录里伪装成图片），组装文件名时又没带扩展名，中间没有一步是错的，错在没人负责给名字加扩展名。修法：新增 magicExt（只读前 16 字节魔数认 jpg/png/gif/webp/bmp/heic/mp4，认不出返回空）+ withMagicExt（没扩展名就补、已有扩展名一字不动），上传那一跳改成 --name withMagicExt(name, f)；文件名标签改中文；已存在的三条旧文件只改名不重传（重传会换 token，旧链接更死），修好后三条全部 preview ok 且 tenant_readable。判据 M6a–M6d（43/43 通过），其中 M6d 钉「真传到 CLI 的 --name 必须带扩展名」。最该记住的一条：能打开 = 权限对 加 类型认得出，两条都要有判据；上一版 fail-closed 只量了「谁能看」，没量「看得见吗」，所以读数恒绿而链接恒死。同形先例：守衡的重启闸门原来只量「进程在不在」不量「它在不在做事」，因此掐断过一条真单。
tier: L1
title: "[反例] 媒材链接「点开无法查看」（2026-10-17）：文件没扩展名 —— 权限读数全绿、字节也是好图；能打开 = 权限对 ＋ 类型认得出"
topic: 知识
valid_until: 2027-01-15
---

# 「点开无法查看」的真因是文件名没有扩展名

## 一、三步追到底

Owner 说「图片 1：点开查看 —— 点击后无法查看」。三步读数：

- 文件本身是完好的：drive 下回来 83,421 字节，魔数 ff d8 ff e0 … JFIF，是一条好 JPEG；
- 权限也设对了：permission_public.link_share_entity = tenant_readable，协作者里有 bot 与两个 openid；
- 但 drive +preview 回 1060006 file type does not support preview —— 飞书按**文件名扩展名**判类型，
  而这个文件叫 `守衡送审素材-image-1`，**没有扩展名**，被当成未知二进制，点开就是死页。

决定性验证：同一个 token **只改名**加 `.jpg`（不动任何字节、换不了 token），预览立刻通过 ——
已经发出去的卡片、报告、表里的旧链接全都照样可用。

根因链：取图那一跳故意把字节存成 `.img`（不让它在临时目录里伪装成图片，是那条窄豁免的边界）⇒
组装文件名时只写了 `守衡送审素材-{kind}-{index}`，没有扩展名 ⇒ 上传后飞书不认识类型。
中间没有一步是「错」的，错在没人负责给名字加扩展名。

## 二、修法

1. `magicExt(path)`：只读前 16 字节魔数认 jpg / png / gif / webp / bmp / heic / mp4，认不出返回空；
2. `withMagicExt(name, path)`：没扩展名就按魔数补，已有扩展名一个字不动；
3. 上传那一跳改成 `--name withMagicExt(name, f)`（一个入口，所有调用方受益）；
4. 文件标签改中文：`守衡送审素材-图片-1.jpg`、`守衡送审素材-视频-1.mp4`（这串名字用户在云空间里看得到）；
5. 已存在的三条一起修好：只改名、不重传（重传会换 token，已发出的旧链接照样死链）。

修好后的回读：三条文件全部 title 带 `.jpg`、preview ok、link_share_entity = tenant_readable。

## 三、最该记住的一条

**「能打开」= 权限对 ＋ 类型认得出，两条都要有判据。**

上一版把 fail-closed 全押在「回读 link_share_entity === tenant_readable」上 ——
那个读数一直是绿的，而链接一直是死链。这不是「判据写错了」，是**判据只量了其中一半**：
只量「谁能看」，没量「看得见吗」。

同一天的另一条同形：守衡的重启闸门原来只量「进程在不在」，不量「它在不在做事」，于是掐断过一条真单。
⇒ 凡是要判「这个东西可用吗」，先问它由几个条件合成，再每个条件各给一条判据。

## 四、判据与边界

media_link.test.mjs 新增 M6a–M6d（43/43）：魔数认得出；认不出**不加**（不编假后缀）；
已有扩展名**一个字不动**（反向对照）；真传到 CLI 的 --name **必须带扩展名**（拆掉修法即精确变红）。

边界：视频那一档只补 .mp4 或源文件名带的扩展名，没做截帧预览；旧文件只改名不重传；
若素材是飞书不认识的格式，名字对了也可能预览不了 —— 那种只能照实说「可下载、不可预览」，目前没有实例。
中间有一条文件第一次回读报 1060007，再查就 ok —— 那是「预览还在生成」的瞬时态，不是第二种故障。
