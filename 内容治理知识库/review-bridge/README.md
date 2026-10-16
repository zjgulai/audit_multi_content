# 审查桥（review-bridge）· 落地说明

> 目的：让飞书机器人**守衡**在群里被 @ 时，真正调用 DSH 知识库的 **skill 自动化工作流**，
> 而不是只拿到 BM25 检索片段。
>
> 建立日期：2026-09-30 ｜ 状态：**本机链路已端到端验证通过**，公网暴露待接入隧道。

---

## 一、为什么需要这道桥

> ★ **2026-10-05 更正（前版此处写错了，留此存照）**
> 前版写「守衡**跑在别的机器上**」，**这是错的**。实测（2026-10-05）：
> 守衡**就在本机** —— launchd `com.shouheng.lark`（`state = running`），
> `/usr/local/bin/node ws_daemon.mjs`，工作目录
> `/Users/lute/Project/audit_multi_content/tools/`，用飞书官方 SDK 的 WebSocket 长连接收事件。
> 它读的库也在本机：`http://127.0.0.1:4401`（工作台 `kb-serve`，db = `工作台/var/workbench.db`）。
> 前版的依据只是 `workbench-service.sh` 里一句注释，**没有独立核实**，属采信单一转述。
> ⇒ 「守衡在外机」这条理由**作废**；下面保留真正成立的那条。

**真正成立的理由只有一条：守衡加载不了 DSH 的 skill。**

| 事实 | 结果 |
|---|---|
| 守衡是**自带 LLM 循环的 Node bot**（`agent/` 下 `llm.mjs` + `tools.mjs` + 判据），**没有 skill 工具** | 它无法加载 `kb-review` / `文案合规审查` 等任何 kb-* skill |
| 它的 `run_readonly_command` 是**严格白名单**（`ls`/`cat`/`grep`/`rg`/`find`/`git log`… + 一条固定形状的 `lark_find.py`），**`dsh` 不在内**，且禁 `; & \| > < \` $` | 它也**跑不了** `dsh --profile headless` |
| 它读库走 `kb_client.mjs` → `GET /openapi/v1/kb`、`…/retrieve`，scope = **只读 `kb:search`**，日限 1000 | 只能**检索**，拿不到三态判定，也跑不了 L4–L7 层前置 |
| DSH 未暴露 HTTP 服务（`~/.dsh/settings.yaml:77 networkExposure: loopback`） | 这条**成立**，但对**同机**场景不构成障碍 |

→ 缺的不是「跨机连接」，是**「让一个没有 skill 能力的 bot 借到 DSH 的 skill 能力」**。

> ⚠️ **由此推出一条设计结论（2026-10-05）**：既然守衡本机、跑不了 `dsh` 但**能跑白名单命令**，
> 那么到达 skill 的路**不必是 HTTP 服务**——只要给它一条**固定形状的白名单命令**
> （照它现有 `python3 tools/lark_find.py search …` 的先例）去调本机
> `dsh --profile headless "<审查任务>"` 即可。本桥把「同机调用」做成了
> 「HTTP 服务 + 端口 + token + 隧道」，**多了一层**。
> 桥仍然带来的四件东西（若改内联命令需自行实现）：隔离 `DSH_HOME`（不污染真实 `~/.dsh`）、
> 超时 180s、并发信号量 2、**结果回验**（条款号须在 L4 定稿层 + 逐字回验，PASS 无 solid evidence 降 REVIEW）。


## 二、已验证的能力（2026-09-30 实测）

| 验证项 | 结果 |
|---|---|
| `dsh --profile headless "<任务>"` | ✅ 一次性任务，跑完即退 |
| headless 下加载 kb-* skill | ✅ 10 个全部加载 |
| headless 下 skill 真执行业务逻辑 | ✅ 读 `l5/p0_patterns.jsonl`、跑 matcher、引用定稿条款 |
| 桥 HTTP → headless → 三态结论 | ✅ 返回 `BLOCK` + 7 条 reasons + 5 条带锚点 evidence |
| 隔离 `DSH_HOME`（不污染真实 `~/.dsh`） | ✅ 用 `DSH_HOME` 重定向 |

## 三、启动

```bash
cd "<知识库>/内容治理/review-bridge"
TOKEN=$(cat .token 2>/dev/null || (head -c 32 /dev/urandom | base64 | tr -d '/+=' | head -c 24 | tee .token))
PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 review_bridge.py --port 8788 --token "$TOKEN"
```

常用参数：

| 参数 | 默认 | 说明 |
|---|---|---|
| `--port` | `8788` | 监听端口 |
| `--token` | 环境变量 `REVIEW_BRIDGE_TOKEN` | Bearer 鉴权；留空则不校验（**只许本机调试**） |
| `--timeout` | `180` | 单次审查超时秒数（实测一条约 82 秒） |
| `--concurrency` | `2` | 并发审查上限（headless 是冷启动，别开大） |
| `--max-chars` | `20000` | 单条素材字数上限 |
| `--home` | `./.bridge-home` | 隔离 DSH_HOME（**不写真实 `~/.dsh`**） |

## 四、接口

### `GET /health`（免 token）

```json
{"ok": true, "checks": {"kb_root_marker": true, "kb_symlink": true, "dsh_node": true,
 "dsh_bin": true, "isolated_home": true, "skills_linked": true, "credentials": true}}
```
任一为 false 时返回 503 —— 这是桥的"能不能干活"自检。

### `POST /openapi/v1/review`（需 Bearer）

请求：
```bash
curl -s -X POST http://127.0.0.1:8788/openapi/v1/review \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"text":"Momcozy 吸奶器，全网最好用，绝对安全，100% 无副作用，医疗级品质，FDA 认证，能治好涨奶。"}'
```

响应（实测截选）：
```json
{
  "status": "BLOCK",
  "summary": "命中 P0 红线（「FDA 认证」＝L5 模式 H06／定稿条款 W-1.8）…打回提交人",
  "reasons": [{"code": "P0_H06_FDA", "detail": "确定性 P0 命中：p0_patterns.jsonl 第 4 行逐字命中，basis=verbatim_source"}],
  "evidence": [{"article_no": "W-1.8", "anchor": "#…/检测关键词",
                "source_sha256": "2e8bb36d6edf…", "quote": "FDA approved, FDA certified, FDA 认证…"}],
  "evidence_solid": 5,
  "contract_notes": [],
  "elapsed_s": 82.6
}
```

错误码：`400 missing_text` / `401 unauthorized` / `413 text_too_long` / `502 headless_failed` / `504 review_timeout`。

## 五、三条硬闸门（写在代码里，不是建议）

1. **引用契约**：`PASS` 且无任何可回源依据（缺 `article_no` 或 `anchor`/`quote`）→ **强制降级 `REVIEW`**。
   依据 `kb-content-review` 的 hard_gate：引用不到锚点的结论一律不输出。
2. **不给放行承诺**：`3_措辞表达库` 是派生视图，口径写明「未命中 ≠ 合规」「`p_level`/`risk_level` 不是放行结论」。
   桥只回三态**分流**结论，不生成「能过 / 保证合规」。
3. **不猜结论**：模型输出不符合 JSON 契约时，回 `NEEDS_INPUT` + 原始输出，**不替它编一个三态**。

## 六、给守衡侧的接入（待做）

### 6.1 公网暴露

现有隧道 `KB_TUNNEL_TARGET` 默认指向 `http://127.0.0.1:4401`。两种做法：

| 做法 | 说明 |
|---|---|
| **同域加路径**（推荐） | 让承载进程把 `/openapi/v1/review` 反代到 `:8788`，守衡只加一个工具，**不用改隧道、不用新 Key** |
| 第二条隧道 | `KB_TUNNEL_TARGET=http://127.0.0.1:8788` 另起一条；但 ngrok 免费版静态域名只有 1 个，需评估额度 |

### 6.2 守衡侧要加的工具

```
名称：审查内容治理素材
方法：POST  <BASE>/openapi/v1/review
鉴权：Authorization: Bearer <KEY>
额外头：ngrok-skip-browser-warning: true
入参：{"text": "<待审素材原文>"}
```

### 6.3 守衡指令（建议直接采用）

> 回答内容治理、合规、文案审核相关问题时：
> 1. 先抽 2~4 个关键词，用**检索**工具拿规则片段（不要把整句问题当检索词）；
> 2. 只要用户问的是「**能不能发 / 能过吗 / 审一下**」，**必须再调「审查内容治理素材」工具**，
>    把素材原文传进去，拿到 `status`；
> 3. 按 `status` 回话：`BLOCK` → 明确说不能发，列出命中的条款号与原因；`REVIEW` → 说需要人工复核，
>    列出待确认点；`NEEDS_INPUT` → 说缺什么信息；
> 4. **禁止**把 `PASS` 说成「保证合规」；**禁止**在无 evidence 时下结论；
> 5. 所有检索都 0 命中且审查无依据时，回答「知识库查不到」。

## 七、已知边界与维护

- **冷启动成本**：每次调用起一个 headless agent 进程，实测单条约 82 秒。高频 @ 要排队（`--concurrency`），别裸奔。
- **模型**：走 `~/.dsh/settings.yaml` 的 `agent-default-model`（当前 `deepseek-flash`）。改模型改那里，不用改桥。
- **凭据**：桥软链复用真实 `~/.dsh/.credentials.yaml`（只读），**不复制明文**。
- **隔离 HOME**：`.bridge-home/` 只复制 `profiles/headless`（16K）。
  ⚠ 早前版本复制整个 `profiles/`（desktop 全家桶 487MB + DSH 正在写的 `.desktop.incomplete-*`）→ `copytree` 崩溃。
  **教训：最少必要。**
- **cwd 纪律**：headless 子进程 cwd 必须含 `kb/`（29 个 kb 脚本用 `kb/...` 相对路径）。桥默认设为 `内容治理/`。
- **.token**：600 权限，别提交、别贴群。
