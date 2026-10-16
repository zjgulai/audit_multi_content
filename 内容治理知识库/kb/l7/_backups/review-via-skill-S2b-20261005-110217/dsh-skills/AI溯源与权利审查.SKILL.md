---
name: AI溯源与权利审查
description: |
  **本 skill 负责且只负责这三类问题**（问题的**性质**决定归属，**载体**不决定归属）：
    ① **AI 生成披露**：AI 生成标识缺失、AI 换脸/深度伪造要不要标注、要不要标 AI；
    ② **肖像与人物授权**：肖像授权范围是否覆盖本次投放、授权到不到期、授权证据齐不齐；
    ③ **第三方权利与出镜隐私**：商标与第三方素材侵权、儿童出镜授权与隐私。
  这三类问题的**唯一承接者就是本 skill** —— 句子里的「这条视频」「这张图」「画面里」只是素材描述，
  不改变归属（图片安全审查 / 视频安全审查 只管**画面本身**的安全，不管**权利归属**）。
  审查 **AI 生成披露**与**第三方权利**：AI 生成标识缺失、AI 换脸/深度伪造要不要标注、
  肖像与人物授权范围是否覆盖本次投放、商标与第三方素材侵权、儿童出镜的授权证据与隐私。
  ⚠️ **本 skill 按「问题」路由，不按「载体」路由**：只要问题本身是「AI 披露」或「第三方权利归属」，
  **无论载体是视频、图片还是文字，都由本 skill 承接** —— 不要因为句子里出现「视频」就走视频安全审查、
  出现「图片」就走图片安全审查（它们只管画面/文字**本身**的安全与合规，不管权利归属）。
  当用户说「这个达人视频是 AI 生成的但没有标识，有风险吗 / 这条素材用了 AI 换脸，需要标注吗 /
  这张图里的人物肖像授权范围覆盖到这次投放吗 / 画面里出现的第三方素材和商标有没有侵权风险 /
  儿童出镜的授权证据齐全吗，隐私上有问题吗 / AI 生成痕迹没标 / 要不要标 AI / 肖像授权到不到期 /
  商标授权 / 素材授权」时使用。
  触发词：AI 溯源与权利审查、AI 生成、AI 生成的但没有标识、AI 生成标识、AI 换脸、深度伪造、
  需要标注吗、要不要标 AI、肖像授权、肖像授权范围、授权范围覆盖、第三方素材、商标、商标侵权、
  儿童出镜授权、授权证据齐全、隐私、溯源、provenance、rights review。
  不适用（各自点名）：视频**画面本身**的安全 / 背书 / 违规画面（走 视频安全审查）、
  图片**画面本身**的安全与内容风险（走 图片安全审查）、文字**措辞**合规（走 文案合规审查）、
  产品宣称真伪与 SKU 事实（走 产品宣称核验）、把发现汇总裁决（走 审查裁决）、
  一批素材走发布前全流程（走 内容审查总控）。
version: "1.0.0"
complexity: "complex"
enabled: "true"
user-invocable: true
---

# Brand Ai Provenance Rights Review

Check declared AI generation or deep-synthesis status, required labels, realistic people or children, recognizable likenesses, logos and trademarks, stock or creator assets, music, and influencer/endorsement permissions.

`missing_authorization` or `missing_disclosure` defaults to REVIEW because the evidence may exist outside the asset. Explicitly unauthorized use, a confirmed prohibited synthetic representation, or a confirmed privacy violation can be BLOCK when the applicable rule and evidence are present.

Do not infer a person’s identity or age from appearance alone. Record only observable facts and supplied authorization metadata.

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
      --decision-owner AI溯源与权利审查          # 判定主体；缺席 ⇒ NEEDS_INPUT（2026-10-03 起默认要求）
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
