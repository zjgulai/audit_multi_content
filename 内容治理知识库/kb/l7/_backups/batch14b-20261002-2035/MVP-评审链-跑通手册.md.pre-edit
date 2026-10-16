# 评审链 skills 工作流 · 最小可复跑手册（MVP）

> 目标：用户说一句「**这个评审一下**」（带待审文字内容）→ 由已装 skills 自动走完 → 输出带依据的三态结论。
> 状态：**2026-09-30 端到端跑通一次并留证**（见文末证据）。无人值守（定时触发 agent）**未做**。

## 一、五跳链路（这就是 skills 工作流）

```
① 触发    用户一句话
            └─ 盲测实测：新开 agent 只拿到「这个评审一下」+ 文案 → 自己选中 `文案合规审查`
② 入口    kb-review（让位表：能识别专项就交出去，不抢活）
            └─ 文字 / listing / 字幕口播 → 让它位给 文案合规审查
③ 专项    文案合规审查（brand-text-compliance-review）
            ├─ 第 1 源：候选扫描 rule_engine.py（**只有 5 条** US 种子规则，产出的是候选不是结论）
            └─ 第 2 源：依据检索（**必跑**，见 ④）
④ 依据    kb-content-review（链内组件）
            └─ P0 匹配（l5/matcher.py）→ 509 条措辞表达库（l3/candidates/rules.jsonl）
               → BM25（l6/retriever.py）→ 条款号 + anchor + source_sha256 + 逐字摘录
⑤ 裁决    审查裁决 → review_engine.decide()（决策序：NEEDS_INPUT > BLOCK > REVIEW > PASS）
            └─ 契约交接由适配器完成：l7/review-engine/core/with_kb_evidence.py
```

## 二、可复跑命令（三条，按顺序）

```bash
cd ~/.dsh/Momcozy知识库            # 库根 = kb/ 的上一级

# ③ 专项第 1 源：候选扫描（可选，0 候选很正常，别据此判 PASS）
kb/kbpy l7/review-engine/core/rule_engine.py "<待审文案>" --product-line 吸奶器 --channel Amazon
#   ⚠️ --product-line/--channel 必须用 seed-rules.json 的词表原样（吸奶器 / Baby Monitor /
#      Bottle Washer ｜ Amazon / Google / Instagram / TikTok / YouTube / 独立站），写错会全被过滤掉

# ④+⑤ 依据 + 裁决（一条命令跑完，这是 MVP 主入口）
kb/kbpy l7/review-engine/core/with_kb_evidence.py --text "<待审文案>" [--json]

# ④ 只要依据、不要裁决（想看完整问题清单落盘时用）
python3 ~/.dsh/skills/kb-content-review/scripts/review.py --kb-root "$PWD" --text "<待审文案>"
```

## 三、验收判据（四条，缺一条不算跑通）

| # | 判据 | 怎么核 |
|---|---|---|
| A1 | **触发对** | 新开 agent，只给「这个评审一下」+ 内容 → 它选中 `文案合规审查`（不是供给链、不是 kb-review 兜底） |
| A2 | **依据可核** | 每条结论带齐六要素：库名 + 版本 + 条款号 + anchor + source_sha256 + 逐字摘录（缺一即不合格） |
| A3 | **裁决有出处** | 结论由 `review_engine.decide()` 产出（不是 agent 自己说的），且 `issue_count` 与依据条数一致 |
| A4 | **落盘可读** | 报告写在 `kb/l7/reports/<run>.review.md`，且 **python getsize == node statSync().size**（差 0；±4096 = 信封态，宿主读不到） |

**反判据（必须避免）**：候选扫描 0 条 → 直接给 PASS。实测同一段文案「候选 0 条 / 依据 10 处 BLOCK」，
只跑候选就判 PASS = **漏放**。

## 四、2026-09-30 那次跑通的留证

输入：`FDA approved breast pump. Hospital grade. 100% safe and pain-free. Mimics baby natural nursing to boost supply.`

| 环节 | 结果 |
|---|---|
| ① 触发（盲测） | 新 agent 选中 `文案合规审查`，理由「纯文字命中让位规则」 |
| ③ 候选扫描 | **0 候选**（该文案不含那 10 个种子词）—— 正确的"没候选"，不是"没问题" |
| ④ 依据 | **10 处**，条款号 W-1.6 / W-1.8 / W-1.11 / W-1.18 / W-1.19 / W-1.22 / W-1.31 / W-1.33 / W-1.35 / W-1.53；引用契约六要素齐 |
| ⑤ 裁决 | `review_engine.decide()` → **BLOCK**，confidence **0.97**，issue_count 10 |
| 落盘 | `kb/l7/reports/20260930-115756.review.md`（后续几次同形态），python=node 差 0 |

**这次修掉的三个断点**（都记在对应文件里）：
1. `kb-content-review/scripts/review.py`：node 解析器的 DSH glob 写错（`DSH Desktop*.app/…` 匹配不上本机
   `DSH Desktop.app.pre-lute-…`）→ 掉到被 SIGKILL 的 ChatGPT node → 降级 python → 报告变**信封态**；
   已修 glob + 候选逐个试。
2. 同文件：`article_no` 从候选文件读（空）→ 依据印「第　条」；已改为从 `kb/l4/canonical/*.jsonl` join 补齐（509/509）。
3. **`l7/review-engine/core/with_kb_evidence.py`（新增）**：依据侧与裁决侧**原本不相通**
   （裁决侧只吃 `rule_engine.py` 的 5 条种子规则）→ 新增适配器把 509 条依据按契约送进
   `review_engine.decide()`。这是「工作流」与「一堆 skill」的分界。

## 五、还没做的（别当成已完成）

1. **报告与记忆这一跳**（`审查报告与记忆`）没接：结论目前落在 review.py 的报告里，没走它的模板/存档契约。
2. **无人值守**：定时触发 agent 的无头入口未确认（只找到 `~/.dsh/bin/lark-cli`）；现在是人在环。
3. **图片 / 视频模态**：本手册只覆盖文字；图片走 `图片安全审查`、视频走 `视频安全审查`，各自的证据链未按本手册验证。
4. **`审查裁决` 的置信度**：引擎自己声明「confidence 是启发式，未做金标标定」，不得当成法律合规概率。

---

## 六、机器入口：`POST /review`（2026-09-30 加，给守衡 / 飞书侧调用）

skill 是给 **agent** 的入口；守衡是 **bot**，调不了 skill —— 所以给机器开了同一条链的 API，
**两者背后是同一套引擎**（P0 + 509 条措辞表达库 + BM25 + `decide()`），且**确定性、不经过 agent**。

```bash
curl -s -X POST http://127.0.0.1:8787/review \
  -H "Authorization: Bearer $KB_API_TOKEN" -H 'Content-Type: application/json' \
  --data-binary @body.json      # {"text":"<待审文案>","content_id":"可选","channel":"Amazon"}
```

服务：`com.dsh.kbapi`（uvicorn，`kb_api.py`，`0.0.0.0:8787`，与 `/match` `/search` `/rule` 同一个服务、同一个 token、同一套引用契约）。

**实测验收（2026-09-30，4/4 通过）**

| # | 判据 | 结果 |
|---|---|---|
| 1 | 调得通、结论对 | `state=BLOCK`、`confidence=0.97`、`issue_count=10`、`evidence_complete 10/10`，每条带 条款号 W-1.18 / 库 / anchor / source_sha256 |
| 2 | 幂等 | 同文本两次：`state` 相同、`content_version` 相同（= sha256）、`review_id` 不同 |
| 3 | 鉴权 | 无 token → **HTTP 401** |
| 4 | 不伤老路由 | `/match` 仍正常返回（H05 / P0 / BLOCK） |

另外：**每次调用都落报告**（`report_path` 随响应返回），且报告 python getsize == node statSync（差 0，宿主读得到）。

### 踩到并修掉的两个坑（都写进代码注释了）

1. **服务起不来**：`kb/l6/retriever.py`（`matcher.py` 同）带**导入期**解释器守卫，它比
   `realpath(sys.executable)` 与 `.kb-python` 写的 `/usr/bin/python3` —— 本机 `sys.executable` 实际是
   CommandLineTools 那个，两者 realpath 不等 → 守卫 `execve` 成 `python3 retriever.py <uvicorn 的参数>` → argparse 报错、服务退出。
   修：`kb_api.py` 在 import 前 `os.environ.setdefault("KB_INTERP_OK","1")`（plist 已固定用合格解释器）。
   **注**：这说明该服务此前若经 launchd 冷启动也会失败 —— 现在修好了。
2. **API 调用不落盘**：适配器默认走 `--dry-run`（冒烟用）→ 加 `write_report=True`，API 路径改为每次留痕。

### 守衡怎么调（两条路，前置条件不同）

| 路 | 机制 | 前置 | 现状 |
|---|---|---|---|
| **(a) 长连接事件**（推荐，不需要公网） | 本机 `lark-cli event consume im.message.receive_v1` 收指令 → 调 `/review` → 用 `lark-im` 回帖 | 守衡应用 `cli_aa2243de0438dcd7` 要开**事件订阅**并启总线 | ⚠️ 实测 `event status` 显示的是**另一个应用** `cli_aa2e11d952f85be9` 且 `Bus: not running` → **需飞书侧配置** |
| **(b) 公网直调** | 守衡（云端）HTTPS 调我们的 `/review` | 需要把 8787 挂上公网 | ⚠️ 现有 ngrok 隧道 `scrambled-collision-exception.ngrok-free.dev` **目标是 4401（工作台）**，不是 8787 → 要另开隧道；且**默认 token `dsh-kb-dev-token` 必须先换掉**（0.0.0.0 监听 + 公开默认值 = 同网段谁都能查库） |

**还没验证的（如实说）**：**没有从飞书侧真实调用过一次** —— 本机侧就绪（curl 4/4 通过），
但守衡侧的事件订阅/隧道都还没配，所以「守衡可调用」目前是**通路就绪、端到端未验**。
