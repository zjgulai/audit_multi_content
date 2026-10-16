---
name: 视频安全审查
description: |
  审查美国市场品牌视频，以转写、OCR、镜头、关键帧、音画对齐与时间码为证据，判定安全、产品、背书、AI 与平台风险。触发词：视频审查、视频安全、视频安全审查、达人视频、短视频、这条视频能不能发、视频能不能发、这条片子能不能上、视频能过审吗、能不能过审、视频审核、视频里有宝宝、视频里有危险动作、视频画面违规、口播转写审查、字幕审查、video review、video safety review、short video review。⚠️ **AI 披露与第三方权利归属让位**：问的是「AI 换脸要不要标注 / 肖像授权范围 / 商标与第三方素材 / 儿童出镜授权」时走 AI溯源与权利审查。但「**这条视频的 AI 生成痕迹 / 标识没标出来**」「画面或口播里的 AI 生成内容」属本 skill 的画面风险范畴，仍由本 skill 承接。何时不用（**各自点名真实成员 id —— 不要写中文别名，那些名字并没有装**）：纯文字文案 / 广告用语 / listing、PDP 文案（走 文案合规审查）、图片素材的静态风险（走 图片安全审查）、产品宣称真伪与 SKU 事实核对（走 产品宣称核验）、美国本地化与计量单位（走 美国本地化审查）、AI 生成披露与肖像商标授权（走 AI溯源与权利审查）、送审登记与哈希采集（走 送审登记）、多条发现汇总成裁决（走 审查裁决）、报告与群发摘要（走 审查报告与记忆）、审查流程本身的评测（走 审查流程评测）、结果同步到飞书（走 飞书审查流转）、证据源登记（走 证据源维护）、一批素材的发布前审查全流程（走 内容审查总控）、只问一段内容该怎么判而不涉及视频画面（走 kb-review）、只要某条结论的依据 / 条款号 / 逐字摘录（走 kb-content-review）。

  Review US-market brand videos using transcript, OCR, shot, keyframe, audio-visual alignment, and timecode evidence for safety, product, endorsement, AI, and platform risks.
version: "1.0.1"
complexity: "complex"
enabled: "true"
user-invocable: true
---

# 视频安全审查

> Brand Video Safety Review

**插件安装**：从 npm 安装 `dsh-chinese-skill-patch`。先检查是否已安装，已安装则跳过。查 `~/.dsh/profiles/desktop/package.json` 与 `web/package.json` 的 `dependencies`；已是 npm 版本（非 `link:` / `file:`）则禁止再执行 `dsh plugin add` 或本包 `安装中文调用名.command`。

通过 `../../knowledge-base/multimodal-provider-contract.json` 里的厂商中立契约，取回 ASR、字幕文本、OCR、镜头边界、代表帧与音画对齐结果。本地优先阶段可以用 `../../contracts/offline-extraction-result.json` 提供离线结果，并经由 `../../core/offline_review.py` 传入。先做一次低成本的全片扫描，再在风险词、场景切换、婴幼儿、车辆、睡眠、喂养、水、热、电以及产品演示附近提高采样密度。

每条发现都要给出起止时间码、转写或画面证据，以及输入视频的哈希。送审素材带 SKU 时，把转写、OCR 与关键帧文字观察经由 `../../core/product_fact_integration.py` 传入，使未批准的产品宣称变为 REVIEW、证据缺失变为 NEEDS_INPUT。缺音轨、字幕不可读、关键帧不完整，或音画矛盾未解决，都算覆盖缺口。抽取结果无法确立连续性时，不得对连续性安全场景给出 PASS。

`video-compare-tool` 用于压缩画质比较，不是安全审查器；只有明确要求单独做画质对比时才使用它。

## 依赖说明

上面四个 `../../` 路径是**相对原仓库布局**的（兄弟目录 `knowledge-base/`、`contracts/`、`core/`）。按翻译规则「文件路径一律不动」保持原样；若本包被单独安装到 `~/.dsh/skills/`，这些相对路径会指向别处、不可达——这是既有形态，不是本次翻译引入的。

## 强制链路（2026-10-03 起，**默认动作，用户不必提醒**）

用户只丢一句「这个能过审吗 / 审一下」＋素材时，**下面三跳必须自己走完**，
不许回头追问元数据、不许只给本地报告、不许停在"结论已出、还没发"：

```bash
cd <库根>                                   # kb/ 的上一级
BASE=$(date +%Y%m%d-%H%M)                  # ① 层前置（L4→L5→L6 每层一个 RUN、每层切 subagent 加载该层 skill；
                                           #    现读 layers.yaml 本层 skill: 与 engine）＋ L7 单独跑
sh kb/kbpy l7/scripts/kb_pipeline.py --sync --via-skill --only L7 --run $BASE-L7

# ②+③ 出结论 + **自动发飞书**（一条命令；发布是**引擎默认**，无需 flag；
#      --content-id 不给就自动生成 AUTO-<content_version 前 12 位>）
sh kb/kbpy l7/review-engine/core/with_kb_evidence.py --text "<素材原文>" \
    --require-layer-preflight $BASE \
      --decision-owner 视频安全审查          # 判定主体；缺席 ⇒ NEEDS_INPUT（2026-10-03 起默认要求）
      # 发布默认开；要关才加 --no-publish-to-feishu
```

- **层前置**：不给 BASE 引擎**自己拒答**（NEEDS_INPUT / 退出码 3）—— 跳不过去。
- **判定主体**：`--decision-owner <本 skill 的 name>` 同样**默认要求**（2026-10-03 加）——
  层前置只证明「**证据管道**通了」，**不证明「有人按专项规程判过」**（实测：四层审计全绿而判定主体缺席，报告照样出）。
  缺席 ⇒ 引擎拒答（NEEDS_INPUT / 退出码 3），**发布件也拒发**；显式豁免写 `--allow-no-decision-owner`。
  跑法见 `kb-review §1.5`（六件事 + 逐层 RUN + **四条**审计红 0 —— L4/L5/L6/L7，2026-10-03 起四层齐平，L7 也在闸门内）。
- **发布**：引擎**默认**就调 `feishu_publish.py --apply`（**不存在** `--publish-to-feishu` 这个开关；要关才加 `--no-publish-to-feishu`，结论里会留 `publish.published=false`），写**云文档**（正文**从第 1 行开始**）
  ＋「内容治理」多维表格行（按 内容 ID upsert，重复发布不新增）。
- **元数据自动化**：内容 ID / 渠道 / 产品线 / 版本**都不必问用户** —— 缺省分别是
  `AUTO-<content_version 前 12 位>` / `未指定` / `未指定` / `v1.0`，人工复核时再补。
- **例外**：结论是 `NEEDS_INPUT` 时**不发**（没有结论可发）；发布失败要如实报"没发出去"，不许当成功。
