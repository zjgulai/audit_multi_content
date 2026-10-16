---
name: kb-review
description: |
  Momcozy 内容治理知识库的**评审链入口**：收到一段待判内容，走评审链给三态结论
  （PASS / REVIEW / BLOCK），并把结论分派给对应的专项成员。
  【先让位】只要能看出**专项归属**，就直接走对应专项，本 skill 不接：
    文字 / 广告用语 / listing、PDP 文案 → 文案合规审查；
    图片 / 主图 / 图上文字 / 婴幼儿画面 → 图片安全审查；
    视频 / 短视频 / 画面 / 时间码 / 口播 → 视频安全审查；
    产品宣称真伪 / SKU 事实 / 认证范围 → 产品宣称核验；
    AI 生成披露 / 肖像商标授权 / 儿童出镜隐私 → AI溯源与权利审查；
    美国本地化 / 计量单位 / 文化歧义 → 美国本地化审查；
    一批素材走发布前审查全流程 → 内容审查总控。
  本 skill 承接的是**专项归属不明 / 跨模态 / 只问"整体能不能用"**的那一类，其中**包括对象是「素材」而未指明模态**的情况（"这段素材算不算踩线""有没有禁用表述""这批东西该不该拦"）：
  当用户说「这段内容能不能发 / 审一下 / 帮我审审 / 合规检查 / 合规审查 / 内容审核 /
  会不会违规 / 能过审吗 / 有没有风险 / 踩线 / 禁用 / 敏感 / 这段能不能用 /
  帮我判一下这条内容 / 该不该拦」而不指明是哪一类专项、或对象是**不限模态的「素材」**时使用。
  触发词：内容评审入口、能不能发、审一下、帮我审、合规检查、合规审查、内容审核、
  会不会违规、能过审吗、有没有风险、踩线、禁用、敏感、这段能不能用、kb-review。
  不适用：
    · 跑知识库供给链 / 同步知识库 / L0 到 L7 → 走 **kb-pipeline**；
    · 只对账 L0 / 飞书侧改了什么 → 走 **kb-l0-feishu**；
    · 已给出结论、只追问依据 / 条款号 / 逐字摘录 → 走 **kb-content-review**；
    · 单独查某条规则的条款号 → **kb-canonical-lookup**；是不是 P0 → **kb-p0-check**；
      召回单元 / 查资料 → **kb-recall**；
    · 知识库体检 / 闸门 → **kb-check**；闸门没过的修复 → **kb-repair**；
    · 问这几个 skill 怎么分工 / 注册表 / 路由 → **kb-manage**。
version: "1.1.0"
last_updated: 2026-10-03
license: "Proprietary — Momcozy internal use only"
complexity: "standard"
compatibility:
  claude: { status: "native" }
  kimi: { status: "native" }
  cursor: { status: "native" }
  gpt: { status: "bridge", limitations: ["长依据需分段"] }
  minimax: { status: "bridge", limitations: ["需中文优化"] }
  dsh: { status: "native", notes: "kb_search/kb_read 同机可用" }
  codex: { status: "native" }
---

# kb-review —— 评审链入口

**一句话**：本 skill 是评审链的**入口**，不是审查员。
它的第一动作是**判断该谁接**，第二动作才是承接"没人认领"的那类。

## 0. 第一动作：先让位（这条写在最前面，因为它最容易做错）

```
用户送来待判内容
   │
   ├─ 能识别出专项？──是──▶ 直接走对应 brand-*，本 skill 不接
   │
   └─ 否（专项不明 / 跨模态 / 只问整体能不能用）
          └─▶ 本 skill 承接：走下面 §2 的评审链
```

**让位表**（能识别就交出去，别抢活）：

| 能识别的专项 | 交给谁 |
|---|---|
| 文字 / 广告用语 / listing、PDP / 字幕口播转写 | `文案合规审查` |
| 图片 / 主图 / 素材图 / 图上文字 / 婴幼儿画面 | `图片安全审查` |
| 视频 / 短视频 / 达人视频 / 画面 / 时间码 | `视频安全审查` |
| 产品宣称真伪 / SKU 事实 / 认证范围 / 测试报告 | `产品宣称核验` |
| AI 生成披露 / 换脸 / 肖像商标授权 / 儿童出镜隐私 | `AI溯源与权利审查` |
| 美国本地化 / 计量单位 / 文化歧义 / 直译腔 | `美国本地化审查` |
| 一批素材的发布前审查全流程（多模态 + 统一结论） | `内容审查总控` |
| 送审登记 / 哈希 / SKU / 渠道采集 | `送审登记` |
| 多条发现汇总成最终裁决 / 优先级 / 责任人 | `审查裁决` |
| 出报告 / 群发摘要 / 存档留痕 | `审查报告与记忆` |
| 审查流程本身的准确率 / 漏放评测 | `审查流程评测` |
| 证据源（法规 / 平台政策）维护登记 | `证据源维护` |
| 结果同步到飞书 / 多维表格 / 分派 | `飞书审查流转` |

**为什么不自己全干**：专项成员各有判据、证据要求与 not_for。入口全干 =
专项成员永远拿不到自己的活（这正是 `文案合规审查` F1 掉到 0.111 的机制）。

## 1. 第二动作：承接

只有下面三种情况由本 skill 接：

1. **专项归属不明** —— 用户只说"这段能不能用""有没有风险"，看不出是哪一类。
2. **跨模态** —— 一段内容同时含文字 + 图片 + 视频，且用户要**一个**结论。
   （若用户要的是"发布前审查全流程 + 版本留痕"，改走 `内容审查总控`。）
3. **只要一个整体判定** —— 用户不要分项报告，只要"能不能过"。

## 1.5 层前置（驱动循环）—— 承接后、取依据前，必跑

**为什么单列一节**：`kb_pipeline.py --via-skill` **不负责调用层 skill** —— 它只跑闸门 + 记账 +
`--skill` 透传，并把 `layers.yaml` 的声明值**复述**进 `kb/l7/runs/<RUN>.json` 的 `skills` 字段；
该字段**无论 agent 到底加载了几个 skill 都长一样**（出处：`kb-pipeline/SKILL.md` §驱动循环 的
2026-10-01 更正 + `l7/scripts/skill_invocation_audit.py` 开头）。所以这一节不能只写"跑链路"，
必须写**"用 skill 工具把层 skill 加载进上下文再执行"** —— 打印一句"该调谁"不算调过。

**它与 §0 让位表的关系（别混）**：

- **层前置 = 证据准备 + 链路留证**，与专项归属**无关**，**恒定执行**（L4 → L5 → L6 → L7）；
- **让位表 = 判定主体**，只决定"这一单由哪个专项判"。
- 让位**不豁免**层前置；层前置也**不替专项下判**。

**逐层 RUN 约定**（`<RUN>` = `YYYYMMDD-HHMM`）：四层各用自己的 run id —— `<RUN>-L4` / `<RUN>-L5` /
`<RUN>-L6` / `<RUN>-L7`。理由：`kb/l7/runs/<RUN>.json` 是**单文件**，多层共用一个 id 会被最后一层覆盖，
`skill_invocation_audit.py` 的 E2/E3 就只能核到最后一层（该缺陷已登记在 `kb-pipeline/SKILL.md`
§驱动循环 第 5 步的事实更正里）。

**逐层执行体**：照 `kb-pipeline/SKILL.md` §驱动循环 的六件事跑（**引用，不复制** —— 契约 #4：
同一事实写两处，第二处必然过期）。本层要跑哪几个脚本，现读 `layers.yaml` 本层 `engine`（**不许抄**）；
本层该调哪个 skill，现读 `layers.yaml` 本层 `skill:`（**不许抄**）。

```bash
BASE=$(date +%Y%m%d-%H%M)
cd <库根>                                   # kb/ 的上一级
for L in L4 L5 L6; do
  RUN=$BASE-$L
  # ① 先过闸门（本步不跑层引擎、不记账）
  sh kb/kbpy l7/scripts/kb_pipeline.py --sync --via-skill --only $L --gate-only --run $RUN
  # ②③④⑤ 切 subagent：照下面「每层必须做的四件事」做，做完拿到 <子 agent 会话标识> 再往下
  # ⑥ 记账（本层唯一一次；带 --invoked 才让 skill_evidence 从 registry_echo 变成 agent_reported）
  sh kb/kbpy l7/scripts/kb_pipeline.py --sync --via-skill --only $L --run $RUN \
      --invoked <skill-id> --skill-session $L=<subagent 会话标识>
done
# L7 = 跨层闸门、不是层主（skill_write=false），单独跑；
#   ★ 2026-10-03 起 **L7 也在出报告闸门内** ⇒ 必须同样带凭据记账，
#   否则 L7 审计红 1（「本 run 声称的『逐层调了』，证据不成立」）⇒ 引擎直接拒答
sh kb/kbpy l7/scripts/kb_pipeline.py --sync --via-skill --only L7 --run $BASE-L7 \
    --invoked <L7 的 skill-id，从 layers.yaml 取> --skill-session L7=<subagent 会话标识>
```

**②③④⑤ 谁来做：那六件事＋三条实测补丁**

上面 bash 循环里 ②③④⑤ 是一句注释 —— 它是**行为要求**，库里没有实现体，**由读到本节的你执行**。
执行内容照 `kb-pipeline/SKILL.md` §驱动循环 的**契约表（六件事）**与**驱动循环第 3 步的六件事清单**
（**引用，不复制** —— 契约 #4：同一事实写两处，第二处必然过期）。本节**只写那两处没有的三件实测事实**：

**补丁 1 · 第 ⑥ 步的 `<subagent 会话标识>` 怎么取真值（2026-10-03 实测）**
子 agent 的运行环境里**有** `DSH_SESSION_ID`，格式就是 `--skill-session` 要的裸 UUID：

```bash
echo "$DSH_SESSION_ID"        # 子 agent 侧执行 → 如 73e3f421-530c-40b4-b8c1-e017ab605603
```
还可用 `$DSH_SESSION_JSONL` 交叉验证（路径末段目录名与它同值）。**取不到就报"本层未完成"，
不许拿占位串（如 `L4-verify`）充数。**

> ⚠️ **补丁 2 · 已实测的风险：`--skill-session` 没有任何机器校验，别以为审计能替你挡**
> 实测填占位串 `LBV4-verify-L4` → 审计照样**红 0、退出码 0**；子 agent 只传 `--invoked`
> 不传 `--skill-session`（`extra.skill_sessions` 为空）→ **也照样绿**。
> 所以第 ⑥ 步的绿**只说明"闸门过了 + 落章在 + 记账与声明一致"**，说明不了"子 agent 真跑了"。
> 要证明后者，只能人核那两个子会话产物里**确有加载该 skill / 读 SKILL.md 的动作**。

**补丁 3 · 落章"文件在"≠"本次写的"**：第 ① 步的 `--gate-only` 就会用**同一个 RUN 名**写一份同样
skill 的预演落章（实测：`kb/l4/runs/<RUN>-dryrun.json`），所以只看文件存在与 `skill` 值分不出执行者。
能区分的只有 `extra.skill_sessions` 与本层的 `applied` / `dry_run` —— 见下面首跑实测第 3 条。

**2026-10-03 首跑实测的三条硬约束（照做，别重新踩）**：

1. **不许用 `--help` 探参数** —— 本库有脚本不做 argv 解析（`kb/.work/l5_bench.py` / `l5_report.py`），
   `--help` 会被当成普通参数**照常执行并写盘**（首跑实测：多写出 `kb/l5/benchmark.json` 与一个
   **陈旧 RUN 名**的预演落章 `kb/l5/runs/20260923-1430-dryrun.json`）。**参数以 `layers.yaml` 该条注释里
   声明的用法为准**（如 `l6_selftest.py` 只认 `--run=<RUN>`，位置参数会被静默忽略并**回落到默认 RUN**，
   产出错名的落章）。
2. **先 `grep -n "APPLY\|--apply" <脚本>` 再决定跑不跑** —— 无干跑档、不加 `--apply` 也会写盘的
   （`l4_integrity.py` / `l5_bench.py` / `l6_bench.py`）**一律跳过并登记**，**不许用 `--apply` 绕**。
   跳过的连带后果要写进报告：L4 的 `l4_report.py` 吃 `kb/.work/l4_integrity.json` 当输入，跳过它 ⇒
   落章 `verdict=FAIL` 属**继承的旧红**，不是本轮新坏。
3. **落章「文件在 + skill 对」不算数** —— `--gate-only` 那一步就会用**同一个 RUN 名**写一份同样 skill 的
   预演落章，单看文件**分不出执行者**。能区分的只有 `extra.skill_sessions` 与本层的 `applied`/`dry_run`。

**并发纪律（同日实测，两层都要看）**：
① **会话级**——跑之前先认领：`sh kb/kbpy l7/scripts/kb_loop_claim.py claim --base <BASE>`，
   **exit 3 = 已被占用 ⇒ 停下来**；跑完 `release --base <BASE>`。
   认领是**全局单槽**：`--base` 只作标识、**不分槽**（跑**不同** BASE 的第二个会话照样 exit 3 ——
   要保护的是全库唯一的 lock / index / 各层 `runs/`）。
   陈旧认领（超 TTL 45 分钟，或 pid 已不在且过 5 分钟宽限）才 `--take-over`，且**认领新鲜时加它也照样拒**；
   `--take-over` 就是为**跨会话接手**设的（上一会话崩了 ⇒ session/pid 必然都不同）。
   实测代价：两会话同跑 ⇒ 同一个 RUN 在 index 里落 **2 行**、L7 记账被覆盖。
② **命令级**——看 `kb/.work/.kb.lock`。陈旧锁（pid 已死、未宣布释放）按
`lock.held_dead` 口径处置 —— **先 `kb_pipeline.py --check` 判有没有写坏，再删锁**，顺序反了就等于把
「崩在中途」当「跑完了」；**同一把锁别两个 agent 同时恢复**（首跑时两个会话撞过，L6 记账与 L7 各被
`exit 2` 挡回一次）。

**出报告前置闸门（硬：不过不许出结论、不许写报告）**：

```bash
for R in $BASE-L4 $BASE-L5 $BASE-L6 $BASE-L7; do
  sh kb/kbpy l7/scripts/skill_invocation_audit.py --run $R     # 期望：红 0，退出码 0
done
python3 -c "import json;print(json.load(open('kb/l7/runs/$BASE-L4.json'))['extra']['skill_sessions'])"
```

- **红（E1 记账即复述 / E2 逐层无落章）⇒ 本单不许出结论**：该做的不是补一句"我调过了"，
  而是回去把该层的 subagent 起起来。
- **黄（E5 落章来自预演）⇒ 可以出结论，但报告里必须写明"本单未落盘、出的是机制证据"**；
  要落盘证据得带 `--apply`，而 `--apply` 属写库、**要单独报批**（`l7/registry/write-gate.yaml`）。
- **逐层人核**（**不许为它新建闸门脚本** —— 库规：不造第 7 把尺子）：读 `kb/l{4,5,6}/runs/<RUN>*.json`，
  核顶层 `skill` == `layers.yaml` 本层 `skill:`，并核 `applied` 真伪。

- **接线已落地（2026-10-03）：CLI 侧已「默认要求」层前置** —— 跑 ③ **必须**带
  `--require-layer-preflight <BASE>`：`with_kb_evidence.py` 自己逐层调 `skill_invocation_audit.py`，
  **任一层红、或压根没给 BASE，都直接回 `NEEDS_INPUT`（退出码 3）、不出三态结论**。
  这样 ②d 就从"人记得跑"变成"引擎自己挡"。判据仍是审计那一把尺子（**没有新造第 7 把**）。
  确实不做层前置的场合（回归用例等）要**显式**写 `--allow-no-layer-preflight`，
  结论里会记 `layer_preflight.mode=waived_by_caller` —— **缺前置必须可见，不许静默**。

**机器入口（必须显式标注，不许当 PASS 依据）**：守衡 / 飞书走 `kb_api.py`（`:8787/review`），
**bot 加载不了 skill** —— 但它能把 agent 侧跑过的 BASE 用 `layer_preflight_base` 字段传进来，
本接口**照核**（红 ⇒ HTTP 409）；不传时响应里记 `layer_preflight.mode=waived_by_api`。

## 2. 评审链（承接后照这个顺序走）

1. **冻结输入**：记下内容原文、来源、版本、渠道、SKU（有就给）。**改一个字就是新版本。**
2. **定专项**：按 §0 让位表逐类过一遍。**认领不了任何专项**才继续第 3 步。
3. **取依据**（**前置：§1.5 层前置已跑完，且三条 `skill_invocation_audit` 全红 0**）：
   调 `kb-content-review` 的检索协议（L3 规则 → L5 P0 → L6 召回），
   拿条款号 + 锚点 + `source_sha256` + 逐字摘录。
   **具体跑哪几个引擎（点名，别让下一个人猜）**：`l5/matcher.py`（P0 确定性匹配）
   → `l3/candidates/rules.jsonl`（509 条措辞表达库规则）→ `l6/retriever.py`（BM25 主、向量辅）；
   门限/词表/责任人从 `l7/registry/l7.json` 读；输出格式照 `l7/output_template.md`。
   —— 这五个文件就是注册表 `depends_on_engine` 登记的那五个，两边必须一致
   （一致性由 `kb/l7/scripts/skill_conformance.py` 每日常规核）。
   - 只查条款号 → `kb-canonical-lookup`；只问是不是 P0 → `kb-p0-check`；
     只要召回候选 → `kb-recall`。
   - **一次算、两处读（2026-10-01 起）**：同一次评审里「取依据」和「出裁决」用的是**同一份依据** ——
     别把同一段文本算两遍（第二遍不会更准，只会更慢）。依据侧第一次跑就落缓存，裁决侧复用：

     ```bash
     RUN=$(date +%Y%m%d-%H%M)
     # ① 依据侧：跑一次，顺手把依据落成 run 内缓存
     kb/kbpy l7/skills/kb-content-review/scripts/review.py --kb-root <库根> \
         --text "…" --json --dry-run --findings-out "kb/.work/$RUN-findings.json"
     # ② 裁决侧：复用①的依据（不再跑 review.py）
     kb/kbpy l7/review-engine/core/with_kb_evidence.py --text "…" \
         --findings-from "kb/.work/$RUN-findings.json" \
          --require-layer-preflight <BASE> --decision-owner <中文装载目录名>
     ```

     缓存自带 `text_sha256`：**文本对不上会被拒**（防止"把 A 文案的依据算到 B 文案上"）。
     只跑一次也合法 —— 那就走 ② 去掉 `--findings-from`，由 ② 内部现跑依据。
4. **给三态结论**：`PASS` / `REVIEW` / `BLOCK`，逐条附依据。
   **依据不足就按 `no_hit_semantics` 拒答，不许拿常识补。**
5. **分派**：BLOCK 退回提交人；REVIEW 交对应专项；PASS 交签核。
6. **发飞书（**引擎默认**，2026-10-03 起 —— 用户不必提醒）**：出结论那条命令**不用加任何 flag**，
   引擎**默认就发**（要关才写 `--no-publish-to-feishu`）：
   ```bash
   sh kb/kbpy l7/review-engine/core/with_kb_evidence.py --text "<素材>" \
       --require-layer-preflight <BASE> \
       --decision-owner <判定主体：装载目录名（中文），如 文案合规审查> \
       --loaded-skill <判定主体> --loaded-skill <本会话加载过的层 skill…>
   # 判定主体：2026-10-03 起**同样默认要求** —— 缺 ⇒ NEEDS_INPUT / 退出码 3，**发布件也拒发**
   #   ★ 取值 = 装载目录名（中文）；英文 brand-* 是 registry 侧别名（routes.yaml 的 dir_name_map），
   #     填错**不报错**、只会让留痕对不上人
   #   ★ **光填不算**：必须真的用 skill 工具加载该专项正文，再用 --loaded-skill 申报
   # 发布默认开，无需 flag
   ```
   引擎会自己调 `feishu_publish.py --apply`，写**云文档**（正文**从第 1 行开始**、第一行就是报告标题）
   ＋「内容治理」多维表格行（按 `内容 ID` upsert，重复发布不新增）。
   **元数据不必问用户**：内容 ID 缺省自动生成 `AUTO-<content_version 前 12 位>`；
   渠道 / 产品线 / 版本缺省写「未指定」/「未指定」/「v1.0」，人工复核时再补。
   结论是 `NEEDS_INPUT` 时**不发**；发布失败要**如实报「没发出去」**，不许当成功。

## 3. 三条不许

- **不许不检索就答**：没有条款号 + 逐字摘录的结论，算幻觉。
- **不许替专项下判**：认出专项就交出去；替它判 = 它的 F1 归零。
- **不许把"没查到"说成"没问题"**：查不到要明说"知识库查不到"。

## 4. 与其他成员的关系

| 关系 | 成员 | 说明 |
|---|---|---|
| 上游（供给） | `kb-pipeline` | 规则/索引过期时先跑链路，再评审 |
| 链内组件（出依据） | `kb-content-review` | 结论 → 条款号 / 锚点 / 逐字摘录 |
| 只读查询 | `kb-canonical-lookup` / `kb-p0-check` / `kb-recall` | 不写库 |
| 专项成员 | 13 个 `brand-*` | 见 §0 让位表 |
| 家族管理 | `kb-manage` | 路由表变更、成员启停 |

## 5. 何时停下来问人

- 内容里有**看不见的模态**（用户说"还有几张图"但没给）：先要素材，不要凭描述判。
- 结论会是 BLOCK 但依据只有一条 L6 召回（证据级不够）：标 REVIEW + 列出缺什么证据。
- 用户要"改到能过"：那是改写，不是评审，先确认范围再动。

## 6. 最小可复跑路径与验收判据（2026-09-30 端到端跑通后补）

完整手册：`kb/l7/MVP-评审链-跑通手册.md`。这里是**验收那四条**，跑完必须逐条核：

| # | 判据 | 怎么核 |
|---|---|---|
| **A0** | 层前置过闸门（2026-10-03 加；同日扩到四层） | `skill_invocation_audit.py --run <BASE>-L{4,5,6,7}` **四条都红 0 / exit 0**；黄里若有 E5，报告必须标"本单未落盘" |
| **A1** | 触发对 | 新开 agent 只给「这个评审一下」+ 内容 → 选中对应**专项**（文字类 = `文案合规审查`），不是本 skill 兜底、更不是供给链 |
| **A2** | 依据可核 | 每条结论六要素齐：库名 + 版本 + 条款号 + `anchor` + `source_sha256` + 逐字摘录 |
| **A3** | 裁决有出处 | 三态结论由 `l7/review-engine/core/review_engine.py → decide()` 产出，`issue_count` 与依据条数一致 |
| **A4** | 落盘可读 | 报告在 `kb/l7/reports/<run>.review.md`，且 python `getsize` == node `statSync().size`（差 0；±4096 = 信封态，宿主读不到） |

**一条反判据（踩过，必须避免）**：专项的候选扫描器 `rule_engine.py` **只有 5 条** US 种子规则，
它报 0 候选**不等于合规** —— 实测同一段文案「候选 0 条 / 依据 10 处 BLOCK」。
**没有 `kb-content-review` 的依据，不得输出 PASS。**

**两个交接件**（缺了链路就是断的）：

- 依据 → 裁决 的契约适配器：`kb/l7/review-engine/core/with_kb_evidence.py`
  （一条命令跑完依据 + 裁决：`kb/kbpy l7/review-engine/core/with_kb_evidence.py --text "…" `
  `--require-layer-preflight <BASE> --decision-owner <中文装载目录名>`；
  2026-10-03 起**不给 BASE、或不给 `--decision-owner`，都会拒答** —— 两道闸门同强度）。
  它存在的理由：裁决侧原先只吃 `rule_engine.py` 的 5 条种子规则，
  与依据侧的 509 条措辞表达库**不相通**，同一段文案两条路会给出相反结论。
  **依据缓存的两端**：写方 `--findings-out`（依据侧，`review.py` 或本适配器都行）／
  读方 `--findings-from`（裁决侧）；格式与三道校验的唯一真源是
  `kb/l7/review-engine/core/evidence_cache.py`。见 §2 第 3 步的命令。
- 结论 → 飞书的**发布件**：`kb/l7/review-engine/core/feishu_publish.py`（**默认预演，`--apply` 才写**）。
  它从 `l7/registry/conclusion-destination.yaml` **现读去向**，写**云文档**（**必须从第 1 行写**：
  markdown 第一行就是报告标题 H1、**不传 `--title`**、**不用 `append`**；写已有文档用
  `docs +update --command overwrite`）＋ **表行 upsert**（按 `内容 ID` 幂等），写完两端读回校验。
  ⚠️ 层前置不是 `enforced`、或结论是 `NEEDS_INPUT` 时**拒发**；它也**不是 KB 写库动作**（不碰 kb/l0–l7 数据）。
- 三态结论的落盘：由 `kb-content-review/scripts/review.py` 的 node 明文通道写 `kb/l7/reports/`，
  **不许**用 python 直接写 `.md`（会落成信封态）。

**机器入口（守衡 / 飞书侧调用走这里，不走 skill）**：

```bash
curl -s -X POST http://127.0.0.1:8787/review -H "Authorization: Bearer $KB_API_TOKEN" \
  -H 'Content-Type: application/json' --data-binary '{"text":"<待审文案>"}'
```

服务 `com.dsh.kbapi`（`kb_api.py`，0.0.0.0:8787），与 `/match` `/search` `/rule` 同一服务、同一 token。
**守衡是 bot，加载不了 skill** —— 它调的是这条 API；两者背后是同一套引擎（P0 + 509 条 + BM25 + `decide()`），
所以"机器入口的结论"与"agent 走 skill 的结论"应当一致（不一致就是缺陷，按 A3 判据查）。
实测：`state=BLOCK` / `evidence_complete 10/10` / 无 token → 401 / 每次调用落 `report_path`。
