# kept / removed / moved 清单 · 8 件（2026-10-04）

> 对应 `root-skills-creator/references/pre-launch-checklist.md` 交付要求与
> `_执行留痕` 清单⑤：「**kept / removed / moved 的说明**（哪句保留、哪句删、哪句移到哪）」。
>
> 分两段：**A 段** = 主线已做的改动（基线真源 → fix 副本）；
> **B 段** = 本补充优化包做的改动（fix 副本 → `optimized/`）。
> 全部由脚本机械比对得出（`re` 切小节 + 逐文件 sha256），可复跑。

---

## 0. 总表

| skill | 版本 | 正文 基线→fix | 正文 fix→优化 | 行数 | references 基线→fix | 家族校验器(fix) |
|---|---|---|---|---|---:|---|
| kb-l0-feishu | 1.2.4 → 1.3.0 → **1.4.0** | 13442 → 7979 | 7979 → 7979 | 369→185 | 6 → 7 | ✅ |
| kb-ingest-extractor | 1.2.0 → 1.3.0 → **1.4.0** | 4003 → 3527 | 3527 → 3574 | 114→98 | **0 → 1** | ✅ |
| kb-media-extractor | 1.1.0 → 1.2.0 → **1.3.0** | 4312 → 3945 | 3945 → 3992 | 132→111 | 1 → 2 | ✅ |
| kb-clause-extractor | 2.1.0 → 2.2.0 → **2.3.0** | 4947 → 3897 | 3897 → 3944 | 144→99 | 4 → 4 | ✅ |
| kb-canonical-lookup | 1.3.0 → 1.4.0 → **1.5.0** | 2154 → 1951 | 1951 → 1998 | 60→57 | 1 → 1 | ✅ |
| kb-p0-check | 1.2.0 → 1.3.0 → **1.4.0** | 1541 → 1541 | 1541 → 1588 | 43→43 | 1 → 1 | ✅ |
| kb-recall | 1.2.0 → 1.3.0 → **1.4.0** | 2155 → 2155 | 2155 → 2202 | 56→56 | 4 → 4 | ✅ |
| kb-check | 1.1.0 → 1.2.0 → **1.3.0** | 3073 → 3073 | 3073 → 3120 | 82→82 | **0 → 0** | ✅ |

（「正文 fix→优化」的增量是本包在正文插入的一行 gotchas 指针，约 47 字符。
`kb-l0-feishu` 正文**未增一字**——它正文本就点名了 `references/gotchas.md`，无需指针。）

---

## A 段 · 主线已做（基线真源 → fix 副本）

### A1 · 三件正文**逐字未变** —— 只改 description

| skill | kept | removed | moved |
|---|---|---|---|
| kb-p0-check | 全部 4 小节（§1 数据在哪 / §2 红线 / §3 何时停下来问人 / §4 写档档位） | 无 | 无 |
| kb-recall | 全部 5 小节 | 无 | 无 |
| kb-check | 全部 6 小节 | 无 | 无 |

> 实测：三件正文 `1541 / 2155 / 3073` 字符**一字不差**。改动仅在 frontmatter 的 description。
> ⇒ 主线对这三件采取的是「**只动路由层、不动行为层**」的最小改动策略。

### A2 · `kb-l0-feishu` —— 最大一次重组（13442 → 7979，砍 41%）

| 类别 | 内容 |
|---|---|
| **kept（13 小节原样保留）** | §0 一句话 · §1 红线 · §2 核对范围 · §3 库根与凭据 · §3.1 阶段 0 前置自检 · §4 执行序列 · §5 交付物 · §6 何时停下来问人 · §7 每次结束前 · §8 自成长 + §8.1/§8.2/§8.3 |
| **moved（13 个「阶段 N」小节合并进 §4）** | 阶段 1 记录层 / 阶段 2 结构层 / 阶段 3 认领与归档 / 阶段 4 台账补齐 / 阶段 5 非记录资源 / 阶段 6 图片 OCR / 阶段 7 视频 / 阶段 8 链接下钻 / 阶段 9 下游重跑 / 阶段 9.5 索引层 / 阶段 10 收口核验 —— **由 11 个独立小节压成 §4 的一张执行序列表** |
| **moved（1 处）** | §3.2 权限问题判定顺序 → 细节并入 `references/auth-and-permissions.md`（该文件基线即存在，正文 §3.1 已点名它 §二/§三） |
| **removed** | 无独立删除；上述内容均可从 §4 表 + references 到达 |
| **added（正文）** | §6.1「问人的格式：每条待确认事项必须自带建议」 |
| **added（references）** | `references/ask-and-ledger.md`（6 → 7 份） |

### A3 · 三件「正文超限」件 —— 命令细节下沉 references

三件原本被家族校验器判 **ERROR [body]**（正文超 complexity 上限），
按 `scoring-criteria.md:314` + `comprehensive-scoring.md` 特殊规则 1 会**封顶轨道 C ≤79、`market_ready=false`**。
主线的处置是「把命令细节下沉 references、正文留指针」：

| skill | kept | moved | removed | added（references） | 结果 |
|---|---|---|---|---|---|
| kb-ingest-extractor | 9 小节全保留 | §2 干活的引擎的命令块 → `references/engine-commands.md` | 无 | **`references/engine-commands.md`（从 0 起建）** | 4003→3527，✅ 通过 |
| kb-media-extractor | 10 小节全保留 | §2 命令块 + §2.1 查询档细节 → `references/engine-commands.md` | 无 | `references/engine-commands.md` | 4312→3945，✅ 通过 |
| kb-clause-extractor | 10 小节全保留 | §5 让位表 → `references/routing.md`；§3.1/§2 元信息表/§7 验收表/§4 缺料表 → `references/rejection-ledger.md`、`references/acceptance.md`；原 `compatibility` 自由文本 → `references/l3-redlines.md` | 无（就地压缩约 300 字符） | —（4 份 references 就地扩充） | 4947→3897，**且校验器由「崩溃」转为 ✅ 通过** |
| kb-canonical-lookup | 6 小节全保留 | §2 逐文件口径 → `references/layer-playbook.md`（该文件基线即存在） | 「六个形态文件」的错误说法改为「五个形态文件」（口径更正，非删内容） | — | 2154→1951，✅ 通过 |

**配套修**：`kb-clause-extractor` 的 `compatibility` 基线是**自由文本字符串**，
schema 要求映射 ⇒ 家族校验器在它上面**直接崩溃**（`AttributeError: 'str' object has no attribute 'items'`）。
主线已修为合法映射（`dsh: native` / `claude: bridge` / `codex: bridge`）。

### A4 · description 压缩（8 件，主线做）

| skill | 折叠后 | 不可见规则单元 |
|---|---:|---:|
| kb-recall | 932 → 492 | 15 → 0 |
| kb-canonical-lookup | 846 → 475 | 12 → 0 |
| kb-p0-check | 744 → 475 | 11 → 0 |
| kb-media-extractor | 660 → 496 | 6 → 0 |
| kb-check | 648 → 478 | 6 → 0 |
| kb-clause-extractor | 636 → 492 | 4 → 0 |
| kb-ingest-extractor | 573 → 491 | 2 → 0 |
| kb-l0-feishu | （L0 线）→ 499 | 0 |

**手法**：把 `当用户说「…」` 与 `触发词：` 两块（**重复约 90%**）合并成一份，
逐项删掉的都是**语义重复项**，并**移除了 `**` 加粗标记**（每对 4 字符，计入渲染长度）。
⚠️ 注意与教训对照：L0 v1.2.5 曾因**删触发词**把正例变成 FN ⇒ 压长度**只能删重复，不能删触发词**。

---

## B 段 · 本补充优化包所做（fix 副本 → `optimized/`）

**B 段的每一件都只动两处**，由 `build_optimized.py` 内建的保真自证保证
（其余文件逐文件 sha256 必须与源全等，不等即拒跑）。

### B1 · kept（一字未动的部分）

| 范围 | 说明 |
|---|---|
| 8 件正文的**全部既有小节** | 见 A 段；本包只在正文**末尾追加一行指针**（L0 除外），既有文字零改动 |
| `references/` 全部既有文件 | 逐字保留（含 `kb-l0-feishu/references/gotchas.md` 的 79 行人工台账） |
| `scripts/` | 逐字保留，**权限位照抄**（未擅自给 `kb-recall/scripts/convert_pdf_to_images.py` 加 +x —— 它在源里本就不可执行） |
| `tests/` `examples/` `.skill-meta/` `README.md` `evals.json`（L0） | 逐字保留 |

### B2 · removed

| 项 | 说明 |
|---|---|
| **无** | 本包**没有删除任何一行**。description 是**整块替换**（旧块内容全部在保留的触发词里重现，见 B3）；gotchas 是**新增文件**。 |

### B3 · moved / 改写

| skill | 位置 | 动作 | 说明 |
|---|---|---|---|
| 8/8 | `SKILL.md` frontmatter `description` | **重排 + 补块** | ① 触发条件提到**第一句**；② 补字面 `触发词：` 块；③ 功能句保留但退到第二句。**原有触发词一个没删**（kb-ingest-extractor 触发词由 19 种变为 24 种，其余持平或增加） |
| 8/8 | `references/gotchas.md` | **新增**（L0 为**追加**） | 44 条 `错误 / 修正` 成对条目，含 8/8「本 skill 不处理 X，即使措辞看起来相似」句 |
| 7/8 | `SKILL.md` 正文末尾 | **追加 1 行指针** | `**Gotchas（错误 → 修正）→ \`references/gotchas.md\`**`（47 字符）。`kb-l0-feishu` **未加**——它正文已点名该文件 |
| `kb-check` | `references/` | **从 0 起建** | 新建 `references/gotchas.md`；正文同时点名（原先正文 0 处点名 references） |
| 8/8 | `version` / `last_updated` | 升 minor + 置 2026-10-04 | 例：1.3.0 → 1.4.0 |
| 8/8 | 目录名 | `kb-l0-feishu-fix` → `kb-l0-feishu` | 消掉家族校验器的 `Name doesn't match directory name` warning（L0 由 3 warning 降到 2） |

### B4 · 本包**没有**动的

- 测试用例 / 阈值 / 打分器 / `root-skills-*` 任何工具与脚本；
- `_eval-*/fix/`、`mounts/`、`kb/l7/skills/`、`~/.dsh/skills/`、桌面；
- **没有跑任何盲测** ⇒ 本包不含分数，也不构成任何「通过」依据。

---

## 复核

```bash
cd <内容治理>/_supp-creator-audit-20261004
# 副本与源只应差 SKILL.md 与 references/gotchas.md
for s in kb-check kb-recall kb-p0-check kb-canonical-lookup kb-clause-extractor kb-media-extractor kb-ingest-extractor; do
  diff -rq ../_eval-L1L7-gap-20261004/fix/$s optimized/$s
done
diff -rq ../_eval-L0L7-gap-20261003/kb-l0-feishu-fix optimized/kb-l0-feishu
```
