#!/usr/bin/env bash
# review_run.sh —— 评审链「一条命令跑完」（给 headless agent 的执行件）
#
# 为什么有它（2026-10-05）
# -----------------------
# 实测：评审链的 headless agent 一单做 63 次工具调用，其中八成时间不是判据、
# 而是它自己在「想怎么做 + 满库探索」。PRD §12 要的是**单条判定 ≤10/20/60 秒**，
# 而 PRD 自己写的实现路线是「正则毫秒级 → NLP 模型**秒级**」——差的是**执行形态**，不是判据。
#
# 本件把「层前置」与「出结论」两条命令**串成一条**，让 agent 从探索者变成执行者：
#   它仍然要**用 skill 工具真的加载** L4/L5/L6/L7 四层 skill 与判定主体 skill（工作流不变），
#   但跑的时候只需要执行**这一条**，不必自己拼参数、不必自己找文件。
#
# 判据一条没动
# ------------
#   ① 层前置仍走 kb/l8/review_preflight.sh（逐层 RUN、落层章带 skill、四道审计红 0、任一红即停）；
#   ② 出结论仍走 with_kb_evidence.py，--require-layer-preflight 与 --decision-owner 一个不少；
#   ③ 层 → skill 映射**现读** kb/l7/registry/layers.yaml 的 skill: 字段（唯一真源，不手抄第二份）。
#   本件只做**串联**：前置不绿就不出结论，绝不代替任何一道闸门。
#
# 用法
# ----
#   bash kb/l8/review_run.sh --base <BASE> --session <会话标识> \
#        --decision-owner <判定主体：装载目录名（中文）> \
#        --text "<素材原文，逐字>" [--question "<提问原文，逐字>"] \
#        [--content-type text|image|video] [--two-phase] [--dry-inventory] [--no-publish]
#
# 退出码（与前置一致，便于调用方分流）
#   0=已出结论（引擎 JSON 在 stdout）
#   3=认领被占（库忙 —— **不是**闸门红）｜4=某层闸门红｜5=某层审计红
#   6=前置绿但引擎拒答（NEEDS_INPUT 等，引擎 JSON 仍在 stdout）｜2=用法错
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
LAYERS_YAML="$ROOT/kb/l7/registry/layers.yaml"
PREFLIGHT="$ROOT/kb/l8/review_preflight.sh"
KBPY="$ROOT/kb/kbpy"
ENGINE="l7/review-engine/core/with_kb_evidence.py"

BASE=""; SESSION=""; OWNER=""; TEXT=""; QUESTION=""; CTYPE="text"
MATERIAL_FILE=""; REVIEW_TOKEN=""; SCENE_JSON=""
EXTRA=(); USER_LOADED=(); COVERAGE=(); IMAGES=(); POSITION=""
# ★★ 2026-10-23：**环境变量闸门** `KB_NO_PUBLISH=1` ⇒ 与 `--no-publish` 逐字等价。
#   为什么必须要它（不是"顺手加个开关"）：调优期的跑批（守衡测试表 51–100 行）由驱动件起链，
#   而链的命令行是**守衡侧模板逐字照抄**的（`tools/agent/tools.mjs::reviewCmdTemplate`）——
#   调用方**没有位置**塞 `--no-publish`。于是每一单都会往**生产结论表**落一行：
#   实测 2026-10-23 13:28–15:17 那一批落了 AD-20261023-013…032（约 20 行），
#   而委托方本次明确要求「不要改知识库任务表格」。
#   ⇒ 闸门放在**发布决策点本身**，比在模板里插一行更靠得住：模板是照抄的文本，这里是唯一判定处。
#   默认 **0**；判据 `kb/l8/no_publish_env.test.sh`（含反向对照，见该文件）。
#   ⚠️ 只有**逐字等于 `1`** 才算开 —— 不认 `true`/`yes`/`on`（避免"看着像开、其实没开"）。
#   ⚠️ 同一改动也打在了工作区那份副本（`<repo>/内容治理知识库/kb/l8/review_run.sh`）——
#      两份库同时存在是既成事实（`tools/agent/tools.mjs::KB_ROOT` 指的是本份），
#      只打一份就会出现「判据绿、真跑照样写表」那种最坏形状（2026-10-23 实测踩过一次）。
NO_PUBLISH="${KB_NO_PUBLISH:-0}"

# ── `--help` 给**真用法**（2026-10-16 加）────────────────────────────────────
# 为什么加：原先 `-h|--help` 打的是本文件**开头 40 行注释** —— 那段讲的是"为什么有它"，
#   **一个旗标都没列**。实测（2026-10-16）headless agent 跑完 `--help` 什么都没得到，
#   转而去 `grep -rn "review_run.sh"` 全仓找调用例子（单条命令 40.6 秒）。
#   ⇒ 帮助文本**骗人**，比没有帮助文本更贵：它会把人推去做更贵的探索。
# ⚠️ 这一段是**给人/给 agent 看的真源**，改旗标时**必须一起改**（判据见 `kb/l8/workflow_smoke.py` 的 S8:
#   它拿这里的旗标集合与 `case` 解析器、与执行手册、与守衡侧模板**三方对账**）。
usage() {
  cat <<'USAGE'
review_run.sh —— 评审链「一条命令跑完」：四层前置(L4→L5→L6→L7) → 自命中 → 出结论 + 默认发布飞书

用法：
  bash kb/l8/review_run.sh \
    --base "$(date +%Y%m%d-%H%M%S)" \
    --session "${DSH_SESSION_ID:-shouheng-chain-$(date +%s)}" \
    --decision-owner <判定主体：skill 装载目录名（中文，如 图片安全审查）> \
    --loaded-skill  <同一个名字：你刚刚真的加载过它> \
    --material-file <本单素材文件路径> \
    --token         <同一个路径> \
    --question "<提问原文，逐字>" \
    --content-type <text|image|video>
  # 素材是「读图 / 读视频」得来时，末尾**再加**这两行：
  #   --coverage "image:macos-vision:$(sw_vers -productVersion):$(shasum -a 256 <素材文件> | awk '{print $1}'):ok" \
  #   --coverage "ocr:macos-vision:$(sw_vers -productVersion):$(shasum -a 256 <素材文件> | awk '{print $1}'):ok"

旗标：
  必填  --base <BASE>            本单编号（形如 20261016-1003）
  必填  --session <会话标识>      写进 --skill-session 留痕；空 ⇒ 退出码 2
  素材  --material-file <路径>    素材来源**优先档**；同时是「旁挂是不是本单」的身份凭据
        --token <路径>           与 --material-file 传**同一个路径**（守衡靠它认单）
        --text "<素材原文>"       没有素材文件时的回落档；给了 --material-file 就以文件为准
  判定  --decision-owner <名字>   判定主体；按 kb-review 让位表取「装载目录名（中文）」
        --loaded-skill <名字>     你**真的加载过**的 skill（可重复；脚本不代报）
  其他  --question "<提问原文>"    提问原文，逐字
        --content-type <值>       text | image | video（默认 text）
        --coverage <模态:provider:版本:内容hash:状态>   可重复；是**申报档**，没真跑过不许填
        --image <图文件路径>      送审图（可重复）—— 走「图身份层」（pHash/像素相关），
                                  不依赖 OCR / 图字节 sha；不给 ⇒ 行为与改动前逐字相同
        --position "<区域，图 N 第 X 处>"  本单证据位置（图片单必填）。格式 = 区域词 + 图 N 第 X 处，
                                  区域词只许 顶部/中部/底部/左侧/右侧；不给 ⇒ 引擎用默认
                                  `图片 1（#img.1）`（归一化成裸「图 1」）⇒ 出口闸 R3 判红
        --two-phase | --dry-inventory | --no-publish
  -h, --help                    打印本页

退出码：0=已出结论 ｜ 3=库忙（**不是**闸门红）｜ 4=某层闸门红 ｜ 5=某层审计红 ｜ 6=前置绿但引擎拒答 ｜ 2=用法错
USAGE
}
while [ $# -gt 0 ]; do
  case "$1" in
    --base) BASE="$2"; shift 2 ;;
    --session) SESSION="$2"; shift 2 ;;
    --decision-owner) OWNER="$2"; shift 2 ;;
    --text) TEXT="$2"; shift 2 ;;
    # ★★ 2026-10-09（Owner 裁定「1 旁挂身份对齐」）：**素材文本改从文件读**。
    #   为什么必须加这一档（根因，别再走回头路）：
    #     旁挂身份原先是「把喂给链的文本哈希一遍」。而**喂进去的那段文本是谁选的**？
    #     是守衡起的那条 `dsh --profile headless` 里的**模型**自己组装的 ——
    #     playbook 只写了「逐字传入」，没有任何东西能保证它逐字。
    #     实测（2026-10-09 全天每一单）：指纹**从来没对上过**
    #     （本单=6b292a53 ／ 旁挂=eb5d8532 之类），于是身份核对**恒不成立**，
    #     只能退化成「按时间口径采纳」⇒ 就是「链接指向上一张图」的病根。
    #   ⇒ 交给**文件**：调用方（守衡）把素材写进一个文件、把**路径**递进来，
    #     两边哈希的是**同一份字节** ⇒ 指纹确定相等，与模型怎么转述无关。
    #   ⚠️ 与 `--text` 的关系：给了 `--material-file` **就以文件为准**（并覆盖 TEXT）；
    #     两个都不给 ⇒ 报错。旧调用方（只给 --text）**行为一字不变**。
    --material-file) MATERIAL_FILE="$2"; shift 2 ;;
    # ★ 调用方自报的一次性令牌：旁挂原样回写，守衡拿它做**第一把锁**
    #   （与文本构造完全无关 ⇒ 不受"模型怎么组装文本"影响）。
    --token) REVIEW_TOKEN="$2"; shift 2 ;;
    --question) QUESTION="$2"; shift 2 ;;
    # ★ 2026-10-20：画面读数透传（只影响「负面样本规则 N-1.x」那一层；不给则行为一字不变）
    --scene-json) SCENE_JSON="$2"; shift 2 ;;
    --content-type) CTYPE="$2"; shift 2 ;;
    --loaded-skill) USER_LOADED+=("--loaded-skill" "$2"); shift 2 ;;
    --coverage) COVERAGE+=("--coverage" "$2"); shift 2 ;;
    # ★ 2026-10-21：送审图文件（可重复）—— 透传给 with_kb_evidence --image，
    #   走「图身份层」（pHash/像素相关）。不给 ⇒ 命令行与改动前逐字相同。
    --image) IMAGES+=("--image" "$2"); shift 2 ;;
    # ★ 2026-10-21（P1a）：本单证据位置 —— 透传给 with_kb_evidence --position，替代依据层默认的
    #   `图片 1（#img.1）`（归一化成裸「图 1」，出口闸 R3 点名要红）。不给 ⇒ 行为与改动前逐字相同。
    --position) POSITION="$2"; shift 2 ;;
    --two-phase) EXTRA+=("--two-phase"); shift ;;
    --dry-inventory) EXTRA+=("--dry-inventory"); shift ;;
    --no-publish) NO_PUBLISH=1; shift ;;   # 透传 --no-publish-to-feishu（不写飞书；见下方 PUB 块）
    -h|--help) usage; exit 0 ;;
    *) echo "未知参数：$1" >&2; exit 2 ;;
  esac
done

# ── 素材文本的**唯一来源**（文件优先）─────────────────────────────────────────
if [ -n "$MATERIAL_FILE" ]; then
  [ -f "$MATERIAL_FILE" ] || { echo "缺 --material-file 指向的文件：$MATERIAL_FILE" >&2; exit 2; }
  TEXT="$(/bin/cat "$MATERIAL_FILE")"
fi
[ -n "$BASE" ] || { echo "缺 --base" >&2; exit 2; }
[ -n "$SESSION" ] || { echo "缺 --session" >&2; exit 2; }
[ -n "$OWNER" ] || { echo "缺 --decision-owner（判定主体，装载目录名·中文）" >&2; exit 2; }
[ -n "$TEXT" ] || { echo "缺 --text（素材原文），或给 --material-file" >&2; exit 2; }

# ★★ 2026-10-08：本单**素材文本指纹**（旁挂的身份字段，两个写入点共用）。
#   算式**必须与守衡侧逐字一致**：sha256(素材文本去掉 **ASCII 尾空白** ) 前 8 位
#   （守衡 `tools/agent/tools.mjs::readReviewSidecar` 用同一算式独立算一遍来核；
#     它另有一把锁是链自己的 `content_id`，两把任意一把对上就认）。
#   为什么要它：旁挂是**一个固定文件、每次跑整份覆盖**，而守衡原先**只看时间新鲜**——
#   链跑 2~3 分钟，期间任何并发单/补发写完旁挂，本单读到的一定是**最后写的那一份**。
#   实测（2026-10-08）：同一张图六轮，守衡的卡里引用了**另一张图**的内容 ID
#   （`AUTO-a5c77a1ef763` vs 本图的 `AUTO-11edb5e80c35`），Owner 当场报「回复是错误的」。
#   ★ 也试过「起链时生成一次性令牌、经 env 注入」——**实测穿不过去**：
#     headless agent 那一侧的 bash 不继承 env（注入 TOKPROBE-7f3a91c2 后 echo 回来是空）。
#   ★★ **只哈希文本，不掺 `--question`** —— 第一版掺了，当天就误伤：
#     同一张图被「p2p 新单」与「补发单」各跑一次，问法不同 ⇒ 指纹不符 ⇒ 把**本来可用**的
#     读数拒掉了，卡片回落成「知识库侧本次未参与」，委托方看到的就是**「库忙又复现了」**。
#     **同一内容换句话问，仍然是同一内容。**
#   ★ rstrip 只去 ASCII 尾空白（`" \t\r\n"`），**不用 `[[:space:]]`** —— 那个看 locale，
#     两端会对不齐，而对不齐的表现就是**静默拒收**。
TEXT_SHA8="$(printf '%s' "$TEXT" | /usr/bin/python3 -c 'import sys,hashlib;sys.stdout.write(hashlib.sha256(sys.stdin.read().rstrip(" \t\r\n").encode()).hexdigest()[:8])')"

# ══════════════════════════════════════════════════════════════════════════
# ★★ 2026-10-20（Owner：「同一单跑完还必须支持重新跑」）——**重跑是合法动作，且要认得出**
# ══════════════════════════════════════════════════════════════════════════
# 那条链**从来没有禁止过重跑**：换一个 `--base` 就是新 RUN。但要守住两件事，
# 而在此之前它们**一件都没有判据**（散文没有失败信号）：
#   ① **同一个 BASE 不许跑第二次** —— 那是同一个 RUN 跑两遍：层记账会被后跑的覆盖、
#      `index.jsonl` 会双计（2026-10-03 实测过：同一 RUN 落 2 行、L7 记账被覆盖）。
#      重跑**必须换新 BASE**；这里**硬拒**（退出码 2 = 用法错，不是「库忙」也不是「闸门红」）。
#   ② **第几次跑、上一轮是谁、上一轮结论是什么**要写进旁挂 ——
#      人问「这次跟上次一样吗」不该靠肉眼比两份报告。
# 判据只有一处：`kb/l8/rerun_ledger.py`（按**素材指纹**认，不按时间认 —— 补发单晚到也不能认错）。
# 台账**只追加**：`kb/.work/review_seq.ndjson`（回洗等于抹掉证据，库规明禁）。
RERUN_JSON="$(/usr/bin/python3 "$ROOT/kb/l8/rerun_ledger.py" --check-base "$BASE" --text-sha8 "$TEXT_SHA8" 2>/dev/null || true)"
if [ -z "$RERUN_JSON" ]; then RERUN_JSON='{}'; fi
_rerun_field() {   # $1=字段名；读不到就空串（**不编 0/PASS**）
  printf '%s' "$RERUN_JSON" | /usr/bin/python3 -c 'import sys,json
d=json.load(sys.stdin); v=d.get(sys.argv[1])
sys.stdout.write("" if v is None else ("true" if v is True else "false" if v is False else str(v)))' "$1" 2>/dev/null || true
}
if [ "$(_rerun_field same_base)" = "true" ]; then
  echo "[review_run] ⛔ 同一个 BASE（${BASE}）已经跑过 —— **不许在同一个 RUN 上跑第二遍**。" >&2
  echo "[review_run]    那是同一个 RUN 跑两次：层记账会被覆盖、台账会双计（2026-10-03 实测过）。" >&2
  echo "[review_run]    重跑请换一个新 BASE（同一份素材可以跑任意多次，见 kb/.work/review_seq.ndjson）。" >&2
  exit 2
fi
RERUN_SEQ="$(_rerun_field rerun_seq)"; RERUN_OF="$(_rerun_field rerun_of)"; RERUN_PREV="$(_rerun_field prev_state)"
if [ -z "$RERUN_SEQ" ]; then RERUN_SEQ=1; fi
if [ "$RERUN_SEQ" != "1" ]; then
  echo "[review_run] ↻ 这是同一份素材的**第 ${RERUN_SEQ} 次**审查（上一轮 BASE=${RERUN_OF:-（未记）}｜上一轮结论=${RERUN_PREV:-（未记）}）" >&2
  echo "[review_run]    旧 RUN 的产物（报告 / 层记账 / 表行）**一律不动** —— 重跑只新增，不覆盖。" >&2
fi

# ── 层 → skill：现读 layers.yaml（与 review_preflight.sh / 审计同一口径）──────
LOADED=()
if [ ${#EXTRA[@]} -eq 0 ] || [ "${EXTRA[0]}" != "--dry-inventory" ]; then
  while IFS= read -r s; do [ -n "$s" ] && LOADED+=("--loaded-skill" "$s"); done < <(
    /usr/bin/python3 - "$LAYERS_YAML" <<'PY'
import sys, yaml
d = yaml.safe_load(open(sys.argv[1], encoding='utf-8'))
for L in d.get('layers', []):
    if L.get('layer') in ('L4', 'L5', 'L6', 'L7'):
        for s in (L.get('skill') or []):
            print(s)
PY
  )
fi
# ★ 判定主体必须由**调用方显式申报**，脚本不代报 —— 代报等于把「填了≠加载了」那道防线
#   静默降级（实测过一次：脚本只报层 skill 时，引擎留 warning「判定主体不在申报里」）。
for e in ${USER_LOADED[@]+"${USER_LOADED[@]}"}; do LOADED+=("$e"); done
if [ ${#LOADED[@]} -eq 0 ]; then :; else
  echo "[review_run] --loaded-skill 申报：$(printf '%s ' "${LOADED[@]}" | sed 's/--loaded-skill //g')" >&2
fi
case "$(printf '%s ' "${USER_LOADED[@]+"${USER_LOADED[@]}"}")" in
  *"$OWNER"*) : ;;
  *) echo "[review_run] ⚠ 判定主体「${OWNER}」**不在 --loaded-skill 申报里** —— 结论会留 warning、不得当强证据。" >&2
     echo "[review_run]   你（调用方）必须显式加：--loaded-skill \"${OWNER}\"（在你真的用 skill 工具加载它之后）" >&2 ;;
esac

# ── ⑦ 库侧**没跑成**时，也要落一份「结构化拒答」旁挂（2026-10-07，Owner 同意）───────
#
# 为什么（实测缺陷，不是假设）：旁挂原先**只在 ④（引擎跑完之后）**写。于是
# `exit 3/4/5`（库忙 / 某层闸门红 / 某层审计红）这三条路上**盘上什么都没有** ⇒
# 守衡侧 `readReviewSidecar()` 读不到 ⇒ 卡片与表行的「知识库侧」是**含糊的 0 条**，
# 而不是明确的「未判」。实测：素材「这条社媒文案能不能发：这批婴幼儿用品的文案里写了医用级」
# （表行 `recvxlAvpEWMIX`）就是这样在**库侧零读数**的情况下落了 `Agent 结论=PASS`。
#
# ⇒ 现在这几种情况**照实写成拒答**（`state=NEEDS_INPUT` + 原因码）：
#   **守衡侧一行都不用改** —— 它本来就认 NEEDS_INPUT（卡里写「库侧未判」、表里落「待审」），
#   于是「库忙/闸门红」从**「读不到」**变成**「明确拒答」**，含糊就此消失。
#   ★ 判据一个字没动：这里不改结论、不放宽任何闸门，只是**把已经发生的事写成结构化读数**。
#   ★ 与 ④ 的旁挂**同一路径同一形状**（守衡只认这一个文件、且只认 `at` 新鲜的）。
SIDECAR="$ROOT/kb/.work/last_review_result.json"

# ── ★ 2026-10-22（同群并行 · 第 1 批）：**旁挂按单另存一份副本** ──────────────────
# 为什么（这两份是**固定单文件**，每条链跑完整份覆盖）：
#   `last_review_result.json` 与 `last_engine_out.json` 每次 `>` 重写。两条链并行时，
#   后写的那条盖掉先写的 ⇒ 守衡侧「四把锁」判据拒收 ⇒ **本单降级**
#   （图片单强制 NEEDS_INPUT、文字单逐条依据退回从回答里抠）。
# 这里**不动原文件**（守衡旧读法一字不变），只把同一份内容**多存一份**到
#   `kb/.work/sidecars/<标签>-<BASE>-<pid>.json`
# 守衡并行时按「四把锁」从这堆副本里挑本单那份（`tools.mjs` 的 `pickOwnSidecar`）；
# **单条跑时只是多一份副本，行为不变** —— 这条是本次改动的硬约束。
# 判据：守衡侧 `tools/agent/sidecar_pick.test.mjs`（挑本单 / 只有他单必须拒收 / 回退固定文件）。
# 清理：只留最近 `SIDECAR_KEEP` 份（按 mtime），不设上限会把 `.work` 撑大。
SIDECAR_DIR="$ROOT/kb/.work/sidecars"
SIDECAR_KEEP=200
mirror_sidecar() {   # $1=源文件  $2=标签（review / engine）
  [ -f "${1:-}" ] || return 0
  mkdir -p "$SIDECAR_DIR" 2>/dev/null || return 0
  cp "$1" "$SIDECAR_DIR/${2:-x}-${BASE:-nobase}-$$.json" 2>/dev/null || true
  # 只留最近 N 份：macOS 的 tail 没有 `-n -N`，用 `tail -n +N` 从第 N 条起删
  ls -t "$SIDECAR_DIR" 2>/dev/null | tail -n +$((SIDECAR_KEEP + 1)) | while IFS= read -r _f; do
    rm -f "$SIDECAR_DIR/$_f" 2>/dev/null || true
  done
}
write_refusal_sidecar() {   # $1=原因码  $2=人话原因
  /usr/bin/python3 - "$SIDECAR" "$BASE" "$OWNER" "$1" "$2" "$TEXT_SHA8" "$REVIEW_TOKEN" "$RERUN_JSON" <<'PY' > "$SIDECAR" 2>/dev/null || true
import sys, json, time
# ★★ 2026-10-20：拒答这一轮**也记进重跑台账** —— 否则「库忙/闸门红」那几次不算数，
#   下一次重跑会被说成「第 1 次」，而人明明已经送过 N 次了（这就是「说不清」）。
try:
    _rr = json.loads(sys.argv[8]) if len(sys.argv) > 8 and sys.argv[8].strip() else {}
    _rr = _rr if isinstance(_rr, dict) else {}
except Exception:
    _rr = {}
sys.stdout.write(json.dumps({
    "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    "base": sys.argv[2],
    # ★★ 2026-10-08：**本单文本指纹**（身份）—— 与 ④ 那个字段同一算法（见脚本 61 行附近的说明）。
    #    守衡只采纳**指纹相符**的旁挂 ⇒ 并发/补发时不会再拿别人的结论。
    "text_sha8": sys.argv[6],
    # ★★ 2026-10-09：调用方自报的一次性令牌 —— **原样回写、原样读回**。
    #    它是身份的第一把锁：与"模型怎么组装文本"完全无关（这正是原判据失效的地方）。
    "review_token": sys.argv[7],
    "state": "NEEDS_INPUT",
    "issue_count": 0,
    "confidence": None,
    "content_id": None,
    "review_id": None,
    "report_path": None,
    "report_url": None,
    "publish": None,
    "decision_owner": sys.argv[3],
    "refusal": {
        "state": "NEEDS_INPUT",
        "reason_code": sys.argv[4],
        "reason": sys.argv[5],
        "human": ("本单**没有跑到引擎** ⇒ 知识库侧**没有读数**。"
                  "这不是「库说没问题」，也不是「素材有问题」—— 是**这一次没判**。"
                  "补素材无用：请先确认库侧为什么没跑成，再重审这一单。"),
    },
    "facets": {},
    # ★★ 2026-10-20（同一单重跑留痕，与 ④ 那条旁挂同一组字段）
    "rerun_seq": _rr.get("rerun_seq"),
    "rerun_of": _rr.get("rerun_of") or None,
    "rerun_prev_state": _rr.get("prev_state") or None,
    "source": "kb/l8/review_run.sh",
}, ensure_ascii=False))
PY
  # 台账：拒答这一轮同样算「跑过一次」（state=NEEDS_INPUT，原因码进 reason）
  /usr/bin/python3 "$ROOT/kb/l8/rerun_ledger.py" --record --base "$BASE" \
      --text-sha8 "$TEXT_SHA8" --state NEEDS_INPUT --reason "$1" >/dev/null 2>&1 || true
  echo "[review_run] 已落**结构化拒答**旁挂（${1}）：$SIDECAR" >&2
  mirror_sidecar "$SIDECAR" review     # 按单副本（并行时守衡按四把锁挑本单那份）
}

# ── 计时埋点（2026-10-12 加；**只记时，不碰任何判定、不改任何退出码**）────────────
#   为什么加：PRD §12「单条文字 ≤10s」按字面 = 单条送审→出结论。整链实测 35.8s 里，
#   层前置 ~15s 与证据层 ~4.2s 都有出处，**剩下 ~16s（引擎装配+发布飞书+旁挂）是黑箱**
#   （`perf-latest.json` 原话「属估算」）。不拆开它，任何优化都是盲猜。
#   怎么拆而**不必碰引擎**：引擎 JSON 本来就带 `trace.perf`
#   （`p0_match_ms`/`rule_layer_ms`/`unit_layer_ms`/`assemble_ms`，由 `review.py` 产出、
#    `with_kb_evidence.py:1250` 原样透传）⇒ 本脚本只在**段边界**打点，再算
#   「③ 引擎(含发布) − Σ(trace.perf)」= **发布飞书 + wrapper 其余**。
#   落点：`kb/.work/perf-segments.ndjson`（**另起一个文件，追加式**）。
#   ★★ 绝不动 `kb/.work/last_review_result.json` —— 那是守衡侧只认的旁挂（S1 契约），
#      碰它 = 断链。本埋点与它**物理隔离**；任何异常都被吞掉（`2>/dev/null || true`），
#      不改变 stdout / 退出码 / 任何产物。
#   关掉：`KB_PERF_SEG_OFF=1`（反向对照用 —— 关掉后与本埋点加之前**逐字相同**）。
PERF_SEG="${KB_PERF_SEG:-$ROOT/kb/.work/perf-segments.ndjson}"
_now() { /usr/bin/perl -MTime::HiRes=time -e 'printf "%.3f", time' 2>/dev/null || echo 0; }
T0="$(_now)"; T_PREFLIGHT=""; T_SELFHIT=""; T_ENGINE=""; T_SIDECAR=""
finish_perf_seg() {
  [ -n "${KB_PERF_SEG_OFF:-}" ] && return 0
  /usr/bin/python3 - "$PERF_SEG" "$BASE" "$T0" "$T_PREFLIGHT" "$T_SELFHIT" \
      "$T_ENGINE" "$T_SIDECAR" "$(_now)" "${ENGINE_RAW:-}" <<'PYSEG' 2>/dev/null || true
import json, sys
def fl(x):
    try: return float(x)
    except Exception: return None
a = (sys.argv[1:10] + [""] * 9)[:9]
p, base, t0, tp, ts, te, tsc, tend, eng = a
t0, tp, ts, te, tsc, tend = [fl(x) for x in (t0, tp, ts, te, tsc, tend)]
if not t0 or not tend:
    sys.exit(0)
def d(x, y):
    return None if (x is None or y is None) else round(y - x, 3)
perf = {}
try:
    raw = open(eng, encoding="utf-8", errors="replace").read()
    i = raw.find("{")
    obj = json.loads(raw[i:]) if i >= 0 else {}
    em = obj.get("evidence_meta") if isinstance(obj.get("evidence_meta"), dict) else {}
    tr = obj.get("trace") or em.get("trace") or {}
    if not isinstance(tr, dict):
        tr = {}
    pr = tr.get("perf") if isinstance(tr.get("perf"), dict) else {}
    perf = pr or {}
except Exception:
    perf = {}
# ★ 只认 `_ms` 结尾的键 —— `trace.perf` 里还混着 `text_bytes` / `threshold_s`
#   这类**非计时**字段，早先版用 `isinstance(v,(int,float))` 一律相加，把证据段多算了 0.13s。
_ms = {k: v for k, v in perf.items() if k.endswith("_ms") and isinstance(v, (int, float))}
ev = round(sum(_ms.values()) / 1000.0, 3) if _ms else None
eng_s = d(ts, te)
rec = {"base": base, "total_s": d(t0, tend),
       "seg_s": {"① 层前置": d(t0, tp), "② 自命中": d(tp, ts),
                 "③ 引擎(含发布)": eng_s, "④ 旁挂": d(te, tsc)},
       "engine_trace_perf_ms": perf or None,
       "engine_evidence_s": ev,
       "③内_非证据装配_s": None if (eng_s is None or ev is None) else round(eng_s - ev, 3)}
with open(p, "a", encoding="utf-8") as fh:
    fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
PYSEG
}
trap finish_perf_seg EXIT

# ── ① 层前置（判据不动；不绿就不往下走）──────────────────────────────────────
echo "[review_run] ① 四层前置 L4→L5→L6→L7 …" >&2
bash "$PREFLIGHT" --base "$BASE" --session "$SESSION" "${EXTRA[@]+"${EXTRA[@]}"}"
RC=$?
T_PREFLIGHT="$(_now)"
case "$RC" in
  0) : ;;
  3) echo "[review_run] 库忙（认领被占）—— 未跑结论。这是**库忙**，不是闸门红。" >&2
     write_refusal_sidecar claim_busy "库忙（认领被占）：同一时间只准一个会话跑这条循环，本次没抢"; exit 3 ;;
  4) echo "[review_run] 某层闸门红 —— 未跑结论（如实报是哪一层）。" >&2
     write_refusal_sidecar layer_gate_red "某层闸门红（L4→L5→L6→L7 逐层闸门）—— 详见 ① 的输出"; exit 4 ;;
  5) echo "[review_run] 某层审计红 —— 未跑结论（如实报是哪一层）。" >&2
     write_refusal_sidecar layer_audit_red "某层审计红（skill 调用审计）—— 详见 ① 的输出"; exit 5 ;;
  *) echo "[review_run] 前置异常退出码 $RC —— 未跑结论。" >&2
     write_refusal_sidecar preflight_aborted "四层前置异常退出码 ${RC}"; exit "$RC" ;;
esac

# ── 空跑档到此为止（不跑结论）──────────────────────────────────────────────
for e in ${EXTRA[@]+"${EXTRA[@]}"}; do
  if [ "$e" = "--dry-inventory" ]; then
    echo "[review_run] --dry-inventory：只列命令，未出结论。" >&2
    exit 0
  fi
done

# ── ② 自命中检查（确定性，只报事实；不判三态）────────────────────────────────
echo "[review_run] ② 自命中检查（素材 vs 库内 181 条反例/禁区）…" >&2
echo "===== ② 自命中检查（确定性；它只报事实，不判三态）====="
sh "$KBPY" "l7/review-engine/core/selfhit_check.py" --text "$TEXT"
T_SELFHIT="$(_now)"
echo "[review_run] 若上面是 status=error，那是「没查成」，**不是**「没命中」。" >&2

# ── ③ 出结论（唯一有权产出结论的命令；发布是默认动作）──────────────────────
echo "[review_run] ③ 出结论（含默认发布到飞书）…" >&2
echo "===== ③ 引擎结论（唯一有权产出三态的地方）====="
# ★ stderr 必须单独走文件：引擎会把「飞书发布：…」这类日志打到 stderr，
#   早先写成 2>&1 后这些日志排在 JSON 后面 ⇒ 模板 json.loads 吃到尾随文本而**渲染失败**
#   （实测：链接那单的 agent 只能自己绕过模板去转述，并回头报「工具缺陷」）。
ERRTMP="$(mktemp -t review_run_err.XXXXXX)"
# ── 发布开关（2026-10-12 加；**默认仍发布，默认行为一个字不改**）──────────────────
#   为什么加：`--no-publish` 走的才是 PRD §12「单条文字 ≤10s」的**正确量具** ——
#   PRD 把「报告生成：问题 ≥3 时，报告链接生成 ≤30s」**单列一项** ⇒ 写云文档那一段
#   **不该**重复计入 ≤10s（否则同一段耗时被两条指标双计）。
#   顺带：调优期的真跑不再往**生产结论表**落测试行。
#   ★ 不传此开关 ⇒ PUB 为空数组 ⇒ 命令行与加它之前**逐字相同**。
PUB=()
[ "$NO_PUBLISH" = "1" ] && PUB=(--no-publish-to-feishu)
# 画面读数（2026-10-20）：给了才追加，不给 ⇒ 命令行与加它之前**逐字相同**
SCENE=()
[ -n "$SCENE_JSON" ] && SCENE=(--scene-json "$SCENE_JSON")
# 本单证据位置（2026-10-21 P1a）：给了才追加，不给 ⇒ 引擎走自己的默认位置（行为与改动前逐字相同）
POS=()
[ -n "$POSITION" ] && POS=(--position "$POSITION")

ENGINE_RAW="$(mktemp -t review_run_out.XXXXXX)"
if [ -n "$QUESTION" ]; then
  sh "$KBPY" "$ENGINE" --text "$TEXT" --content-type "$CTYPE" --question "$QUESTION" \
    --require-layer-preflight "$BASE" --decision-owner "$OWNER" \
    "${LOADED[@]+"${LOADED[@]}"}" "${COVERAGE[@]+"${COVERAGE[@]}"}" "${PUB[@]+"${PUB[@]}"}" "${SCENE[@]+"${SCENE[@]}"}" "${IMAGES[@]+"${IMAGES[@]}"}" "${POS[@]+"${POS[@]}"}" --write-report --json >"$ENGINE_RAW" 2>"$ERRTMP"
else
  sh "$KBPY" "$ENGINE" --text "$TEXT" --content-type "$CTYPE" \
    --require-layer-preflight "$BASE" --decision-owner "$OWNER" \
    "${LOADED[@]+"${LOADED[@]}"}" "${COVERAGE[@]+"${COVERAGE[@]}"}" "${PUB[@]+"${PUB[@]}"}" "${SCENE[@]+"${SCENE[@]}"}" "${IMAGES[@]+"${IMAGES[@]}"}" "${POS[@]+"${POS[@]}"}" --write-report --json >"$ENGINE_RAW" 2>"$ERRTMP"
fi
RC=$?
ENGINE_OUT="$(cat "$ENGINE_RAW")"
T_ENGINE="$(_now)"
# ★★ 2026-10-08（第七批）：**引擎 JSON 另落一份机读件**。
#   为什么：守衡侧要「逐条的条款号 / 锚点 / 命中片段 / L0 飞书直链」，
#   而那些东西**只存在于这份 JSON 的 `risk_items[].evidence` 里**。
#   原先守衡只能从**链的回答（headless agent 自己组织的文本）**里正则抠中文 ⇒
#     · 模型改写过措辞 ⇒ 抠不到 ⇒ 卡片退回「《知识库》（未给条款号）（锚点：—）」；
#     · 库侧判到 ≥3 条（PRD §5.3.3 只出汇总）⇒ 根本没有逐条行可抠。
#   ⇒ 与「机读旁挂」同一个套路：**结构化的东西走文件，不走散文**。
#   落点与旁挂同目录（`kb/.work/`），守衡侧按 `at` 新鲜度采纳。
cp "$ENGINE_RAW" "$ROOT/kb/.work/last_engine_out.json" 2>/dev/null || true
mirror_sidecar "$ROOT/kb/.work/last_engine_out.json" engine   # 按单副本（同上，并行时防串）
[ -s "$ERRTMP" ] && cat "$ERRTMP" >&2
rm -f "$ERRTMP"
printf '%s\n' "$ENGINE_OUT"
echo
echo "===== ③b 转述模板（照抄这一段即可，不必再跑任何命令）====="
# ★ 2026-10-05 修（**这是本脚本最容易踩的一处**）：
#   原先写的是 `printf '%s' "$ENGINE_OUT" | /usr/bin/python3 - <<'PYEOF'` ——
#   `python3 -` 是**从 stdin 读程序**，而 `<<'PYEOF'` **覆盖了前面的管道** ⇒
#   python 的 stdin 就是这段程序本身，`sys.stdin.read()` 读到空 ⇒
#   **永远走「不可解析」分支**（实测：round8 链接单、round9、20:38 文案单全中）。
#   现在改成：**引擎 stdout 先落文件**，python 用 `sys.argv[1]` 读文件 —— 不经过管道。
/usr/bin/python3 - "$ENGINE_RAW" <<'PYEOF'
import sys, json
raw = open(sys.argv[1], encoding="utf-8", errors="replace").read() if len(sys.argv) > 1 else ""
d = None
_dec = json.JSONDecoder()
# 三重兜底：引擎可能在 JSON 前/后打了日志行，也可能 stdout 就是纯 JSON
for _cand in (raw, ) + tuple(raw[i:] for i, ch in enumerate(raw) if ch == '{'):
    try:
        d, _ = _dec.raw_decode(_cand.lstrip())
        break
    except Exception:
        continue
if d is None:
    try:
        d = json.loads(raw)
    except Exception:
        d = None

if not isinstance(d, dict) or not d:
    print("【引擎输出不可解析】—— 这是**没查成**，不是「没问题」。")
    print("如实回「未能得出结论 · 引擎输出无法解析」，**不许**自己判三态、**不许**自己写飞书表。")
    print()
    print("---- 便于定位：引擎 stdout 的头 300 字（原文，未加工）----")
    print(raw.strip()[:300])
    raise SystemExit(0)

# ★ 引擎 JSON 里 `decision` 是一个**嵌套对象**（{state, review_id, …}），不是字符串 ——
#   早先这里写成 `d.get("decision") or d.get("state")`，于是「状态」打出一整坨 dict、
#   「问题数」取到 None。两者都改成**先看里层、再看外层**。
_dec_obj = d.get("decision")
_dec_obj = _dec_obj if isinstance(_dec_obj, dict) else {}
# ★★ 2026-10-08（第四批）：`evidence_meta` 也必须在搜索范围内。
#   病灶（Owner 报「私聊有依据、群里没有」）：`report_url` 是**发布之后**才补进
#   `evidence_meta.publish` 旁边的（`with_kb_evidence.py` 末尾），而本函数原先只找
#   `decision` 与顶层 `d` ⇒ **`evidence_meta.report_url` 永远读不到** ⇒
#   旁挂 `report_url=null` ⇒ 卡片只能写「（本次库侧未回报告链接）」，
#   而同一轮里**飞书云文档链接其实是有的**（`publish.docx`）。
_em_obj = d.get("evidence_meta")
_em_obj = _em_obj if isinstance(_em_obj, dict) else {}


def pick(*keys):
    #   顺序：里层 decision（判定本体）→ **evidence_meta（留痕/发布读数）** → 顶层 d。
    #   把 evidence_meta 放在顶层之前：它的键更具体（report_url / report_path / state），
    #   顶层只有 decision / evidence_meta 两个键，放它在前不会抢走别的东西。
    for k in keys:
        for src in (_dec_obj, _em_obj, d):
            v = src.get(k) if isinstance(src, dict) else None
            if v is not None:
                return v
    return None


def verdict_state():
    """「状态」那一格的取值 —— **必须取裁决本体，不许被依据侧的状态顶掉**。

    ★★ 2026-10-14 修（实测 MC-US-YT-88uvcSNxMdk，Owner 报「卡片首行印状态：PASS」）：

    病灶在 `pick()` 的**查找次序**：它先按 key 再换 src，而
      · 裁决本体的键是 `decision`（字符串），**没有 `state` 键**
        （`review_engine._result()` 的 result 里根本没有 `state`）；
      · `evidence_meta` **有** `state`（= `ev.get("state")`，**依据侧**的状态）。
    ⇒ 取 key `"state"` 时：`_dec_obj` 未命中 → **`_em_obj` 命中并直接返回**
      ⇒ **永远走不到 `"decision"` 这个 key**，抬头印的是依据侧的状态。

    后果不是一个措辞问题：**依据侧 PASS ＋ 裁决侧 NEEDS_INPUT（模态覆盖不足而 fail-closed）
    会被印成「状态：PASS」** —— 一句把**拒答**说成**通过**的话。

    ⇒ 现在显式定序：裁决 `decision` → 裁决 `state` → 顶层 `state` / `decision`
      → **最后**才是 `evidence_meta.state`（只在真拿不到裁决时兜底）。
      非字符串（例如顶层 `decision` 是个 dict）**跳过**，不许把一坨 dict 印进抬头。
    """
    for src, k in ((_dec_obj, "decision"), (_dec_obj, "state"),
                   (d, "state"), (d, "decision"), (_em_obj, "state")):
        v = src.get(k) if isinstance(src, dict) else None
        if isinstance(v, str) and v.strip():
            return v
    return None


state = verdict_state()
state = str(state).strip().upper() if isinstance(state, str) else "(无)"
em = d.get("evidence_meta") or {}
lp = d.get("layer_preflight") or {}
do = em.get("decision_owner") or d.get("decision_owner") or {}
pub = em.get("publish") or d.get("publish") or {}

print("状态：%s ｜ 问题数：%s ｜ 置信度：%s"
      % (state, pick("issue_count"), pick("confidence")))
if pick("summary"):
    print("摘要：%s" % pick("summary"))
print("层前置：ok=%s mode=%s" % (lp.get("ok"), lp.get("mode")))
if do:
    print("判定主体：%s ｜ mode=%s%s" % (do.get("skill"), do.get("mode"),
          (" ｜ ⚠ " + str(do.get("warning"))) if do.get("warning") else ""))
# ★ 2026-10-06 修：引擎 `--json` 顶层的字段是 **`risk_items`**（`findings` 在 `evidence_meta` 里）——
#   原先这里取 `d.get("findings")` ⇒ 该段**从来没打印过**（四段溯源是死代码）。
#   实测回复里那四段其实来自**上面完整打印的引擎 JSON**，不是这一段。两处都认，缺一不可。
#
# ★★ 2026-10-14 修（实测复发，Owner 报「卡片首行印状态：PASS」那一单）：
#   `pick("findings")` 取到的是 **`evidence_meta.findings`，一个整数**（`= len(findings)`，见
#   `with_kb_evidence.py` 的 evidence_meta 组装）—— 不是列表。
#   而 `risk_items` 为空时（**所有 NEEDS_INPUT / PASS 的单子**都是空）那个 `or` 就会落到它
#   ⇒ `6[:20]` 抛 TypeError ⇒ **这一段之后的输出全部丢失**，链返回是断的。
#   ⇒ 先取出来、**确认是 list 才用**；不是就当没有（**不猜**，也不把整数当条目循环）。
_ri = pick("risk_items")
if not isinstance(_ri, list):
    _fi = pick("findings")
    _ri = _fi if isinstance(_fi, list) else []
for f in _ri[:20]:
    if not isinstance(f, dict):
        continue
    print("  ● 条款号 %s ｜ %s" % (f.get("article_no") or f.get("clause") or "?",
          str(f.get("rule") or f.get("matched") or f.get("reason") or "")[:120]))
    for k in ("anchor", "source_sha256", "entry_url", "unit_id"):
        if f.get(k):
            print("     %s: %s" % (k, f[k]))

print()
if pub.get("published"):
    print("【飞书那一步已经做完了】published=true ｜ 记录 %s" % (pub.get("record_id") or "?"))
    print("⇒ **你不要再写一次飞书表**（实测：有单子自己又跑 28~29 次 bash 去补写，"
          "把时间从 50 秒拖到 160 秒，还可能造出重复行）。照抄本段即可收工。")
else:
    print("【飞书那一步没有做】published=false ｜ 原因 %s" % (pub.get("reason") or "未说明"))
    print("⇒ 这**由守衡侧负责**，不是你的活。**不许**自己调 lark-cli 去补写表。")

if state in ("NEEDS_INPUT", "(无)", ""):
    print()
    print("★ 本次没有拿到可用的三态结论（%s）—— 如实回「未能得出结论 + 下面的原因」，" % state)
    # ★ 2026-10-05（Owner 裁定「建议1」）：把**真原因**打出来，别再只说"拒答"。
    #   分两类说清：**该用户补的** vs **不该用户补的**（库/系统侧的缺口）——
    #   这样"要不要请对方补充"就从猜变成可判定。
    _ref = pick("refusal") or {}
    if _ref.get("reason_code"):
        print("  原因码：`%s`" % _ref["reason_code"])
    if _ref.get("human"):
        print("  原因（引擎原话）：%s" % _ref["human"])
    _cov = _ref.get("coverage") or {}
    if _cov.get("bm25_max") is not None:
        print("  读数：最高 BM25 %s ｜ 覆盖门限 %s ｜ 被规则引用的达门限单元 %s 条 ｜ Top 命中 %s"
              % (_cov.get("bm25_max"), _cov.get("coverage_bm25_min"),
                 _cov.get("rule_cited_unit_hits"), _cov.get("top_hit_anchor")))
    print("  **这不是「请你补充信息」**：上面若是 `coverage_not_covered` / `evidence_side_refused`，"
          "缺的是**知识库或系统接线**，补素材也没用。")
    print("  **不许**自己判三态、**不许**自己写飞书表（实测有单子就是这么把时间烧掉的）。")
PYEOF

# ── ④ 机读旁挂：把结论的**结构化字段**落成一份小文件，供守衡侧落表读回 ─────────────
#
# 为什么必须有它（Owner 2026-10-05 指出）：
#   `kb_review_chain` 只拿得到 agent 的**最终文本**，拿不到结构化字段 ⇒
#   表里「问题数量/置信度」一直是空的 —— 于是出现「BLOCK 却问题数量空」「拒答却问题数量 0」
#   这种自相矛盾的行。
#
# 纪律：**判据仍在引擎**。这里只是把引擎 JSON 里已有的字段**原样搬**到一份机读文件，
#       不新造任何值、不做任何换算；引擎没给的就留 null（**不许编**）。
# 写法：python 只负责**打印**，落盘由 shell 重定向完成 ——
#       本机 python 直接 open() 写盘会带上 4096 字节信封，宿主读不了（库规已记）。
SIDECAR="$ROOT/kb/.work/last_review_result.json"   # 同上（⑦ 的拒答旁挂也写它，同一个文件、同一个形状）
# ★ 同上：**不许**用 `printf | python3 - <<EOF`（管道会被 heredoc 覆盖 ⇒ stdin 为空）。
#   这里让 python 直接读引擎落下的那份 stdout 文件。
/usr/bin/python3 - "$ENGINE_RAW" "$BASE" "$ROOT" "$TEXT" "$TEXT_SHA8" "$REVIEW_TOKEN" "$RERUN_JSON" <<'PYEOF' > "$SIDECAR"
import os, sys, json, time
# ★★ 2026-10-20：重跑读数（由 `kb/l8/rerun_ledger.py --check-base` 在开跑前算出，
#   经 argv[7] 递进来）—— 读不到就是空 dict：第一次跑时它本来就是空的，**不算错**。
try:
    _rr = json.loads(sys.argv[7]) if len(sys.argv) > 7 and sys.argv[7].strip() else {}
    _rr = _rr if isinstance(_rr, dict) else {}
except Exception:                                          # noqa: BLE001
    _rr = {}
raw = open(sys.argv[1], encoding="utf-8", errors="replace").read() if len(sys.argv) > 1 else ""
base = sys.argv[2] if len(sys.argv) > 2 else ""
d = None
_dec = json.JSONDecoder()
for cand in (raw,) + tuple(raw[k:] for k, ch in enumerate(raw) if ch == '{'):
    try:
        d, _ = _dec.raw_decode(cand.lstrip())
        break
    except Exception:
        continue
if not isinstance(d, dict):
    d = {}
dec = d.get("decision")
dec = dec if isinstance(dec, dict) else {}
em = d.get("evidence_meta") or {}


def pick(*keys):
    """同一字段在两种形状里位置不同（正常路径在顶层，拒答路径在 decision 里）—— 两处都找。"""
    for k in keys:
        for src in (d, dec):
            v = src.get(k) if isinstance(src, dict) else None
            if v is not None:
                return v
    return None


state = dec.get("state") or dec.get("decision") or d.get("state") or d.get("decision")
if not isinstance(state, str):
    state = None

# ── 产品线 / 渠道：**从命中的 L0 记录里取**（Owner 2026-10-06）────────────────────
#   现场原话：「里面的产品线和渠道都是空或者未指定，运行任务的时候从知识库命中产品线和
#   渠道的都填写进去」。⇒ 值只从 `kb/l5/l0_facets.py` 出 —— 与 **P0 快路同一个取数点**
#   （两处各写一套 ⇒ 迟早一个取 `品线`、一个取 `适用产品`，同一条素材两个答案）。
#   ★ 取不到就**空**（`l0_facets.py` 的纪律：只认登记过的字段名 + 只认「本素材自己的记录」，
#     不许从素材正文猜、也不许拿规则样本的投放属性充数）；
#   ★ `--text` 必须传（2026-10-06）：`l0_facets` 加了「这条记录是不是本素材本人」的准入闸 ——
#     **不给素材原文 ⇒ 一律不采信记录**（fail-closed）。先前这里没传 ⇒ 旁挂的 facets 会恒空。
#     这一步失败也**不阻断**旁挂 —— 其余读数照写。
facets = {}
try:
    import subprocess as _sp
    _fx_cmd = ["/usr/bin/python3", os.path.join(sys.argv[3], "kb", "l5", "l0_facets.py"),
               "--engine-json", sys.argv[1]]
    if len(sys.argv) > 4 and sys.argv[4].strip():
        _fx_cmd += ["--text", sys.argv[4]]
    _fx = _sp.run(_fx_cmd, capture_output=True, text=True, timeout=20)
    facets = json.loads(_fx.stdout) if _fx.stdout.strip() else {}
except Exception as _e:                                    # noqa: BLE001
    facets = {"error": "%s: %s" % (type(_e).__name__, _e)}

# ── ★ 2026-10-09（Owner 批准）：把**检索命中**原样搬进旁挂 ─────────────────────
#   为什么在这一层做（而不是只在引擎的 `summary` 里）：**守衡不读 `summary`**。
#   实测：旁挂 `kb/.work/last_review_result.json` 顶层**根本没有 summary 字段**
#   （只有 at/base/text_sha8/state/issue_count/confidence/content_id/review_id/
#     report_path/report_url/publish/decision_owner/refusal/facets/source），
#   守衡侧 `readReviewSidecar()` 是**整份透传**（`return j`）⇒
#   **只要这里写进去，守衡就一定拿得到**；缺的只是它那张卡的渲染那一句。
#   ★ 引擎的 `summary` 里仍保留同一份（报告走那条）—— 两处都留，各服务一个读者。
#   ★ 纪律：**只搬运，不新造**；取不到就是空列表，不编。
_RID2KEY, _U2RID = {}, {}
try:
    import glob as _g
    for _p in _g.glob(os.path.join(sys.argv[3], "kb", "l1", "*", "*.json")):
        try:
            _a = json.load(open(_p, encoding="utf-8"))
        except Exception:
            continue
        if isinstance(_a, dict) and _a.get("resource_id") and _a.get("resource_key"):
            _RID2KEY[_a["resource_id"]] = _a["resource_key"]
    for _line in open(os.path.join(sys.argv[3], "kb", "l2", "units.jsonl"), encoding="utf-8"):
        if _line.strip():
            _u = json.loads(_line)
            if _u.get("unit_id"):
                _U2RID[_u["unit_id"]] = _u.get("resource_id")
except Exception:
    pass


def _clickable(_rk):
    """resource_key → 可点地址（与 hostlib 生成器同一套映射）。"""
    if not _rk:
        return None
    _rk = str(_rk)
    if _rk.startswith(("http://", "https://")):
        return _rk
    _tok = _rk.split(":", 1)[1] if ":" in _rk else ""
    for _pre, _path in (("wiki:", "wiki"), ("docx:", "docx"), ("sheets:", "sheets"),
                        ("base:", "base"), ("file:", "file")):
        if _rk.startswith(_pre) and _tok:
            return "https://momcozy-in.feishu.cn/%s/%s" % (_path, _tok)
    return None


kb_hits = []
try:
    # ★ 取自**引擎已经写进最终 JSON** 的 `evidence_meta.kb_hits` —— 不是 trace
    #   （实测 trace/top_bm25 在最终 JSON 里不存在，取它恒为空，本段会静默产出 0 条）。
    _tb = em.get("kb_hits") or []
    for _h in _tb[:8]:
        if not isinstance(_h, dict):
            continue
        _t = (_h.get("excerpt") or _h.get("text_excerpt") or _h.get("text") or "").strip()
        if not _t:
            continue
        kb_hits.append({
            "anchor": _h.get("anchor"),
            "bm25": _h.get("bm25"),
            "kb_type": _h.get("kb_type"),
            "source_sha256": _h.get("source_sha256"),
            "excerpt": " ".join(_t.split())[:200],
            "url": _h.get("url"),
        })
except Exception:
    kb_hits = []

out = {
    "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    "base": base,
    # ★★ 2026-10-08：**本单文本指纹**（身份，与 ⑦ 的拒答旁挂同一字段、同一算法）。
    #    守衡只采纳**指纹相符**的那一份旁挂 ⇒ 并发/补发时不会再拿别人的结论
    #    （实测：同一张图六轮，守衡的卡引用了另一张图的内容 ID。算法见本脚本 61 行附近）。
    "text_sha8": sys.argv[5],
    # ★★ 2026-10-09：调用方自报的一次性令牌 —— 原样回写（身份第一把锁，与文本构造无关）。
    "review_token": sys.argv[6] if len(sys.argv) > 6 else "",
    "state": state,
    "issue_count": pick("issue_count"),
    # ★★ 2026-10-12（Owner 签字 · 与引擎 `issue_count` 拆分同批）：把**拆分**也放进旁挂。
    #   为什么必须放：`issue_count` 是「问题数」的**唯一出口**（卡 / 表行 / 报告都读它），
    #   而它里面混着「库内依据」与**非权威候选**（源里自己写着 `authoritative:false`、
    #   已被 kb/l3 取代）⇒ 不放这两个数，守衡侧就只能看到一个偏大的总数。
    #   ★ 取值靠 `pick()`：引擎没给（老 JSON / 拒答支路）就是 None —— **记 None 不记 0**，
    #     因为「0 条候选」和「这次没测」是两件事，写 0 会被读成「核过了，没有候选」。
    #   ★ 本库**不代改守衡的卡**：它要显示这一行，得改它自己；本库只保证取值可达。
    "candidate_count": pick("candidate_count"),
    # ★★ 2026-10-12（Owner 裁定：`issue_count` 只算库内依据）—— **旧口径也留一个出口**。
    #   为什么必须留：守衡 `dual_track.mjs` 用 `issue_count` 算「另有 N 条未并进本卡」
    #   （`kbGap = kbN − txtN`）。口径一改，若不给旧数，那张卡会**静默地少算**；
    #   给了旧数，任何一处觉得新口径不合用都能**显式**读回来，而不是回头改引擎。
    "issue_count_including_candidates": pick("issue_count_including_candidates"),
    "confidence": pick("confidence"),
    "content_id": pick("content_id"),
    "review_id": pick("review_id"),
    "report_path": em.get("report_path"),
    "report_url": pick("report_url"),
    "publish": em.get("publish") or d.get("publish"),
    "decision_owner": em.get("decision_owner") or d.get("decision_owner"),
    # ★ 2026-10-05（Owner 裁定「建议1」）：拒答要带**原因码**，不再只给一个词。
    "refusal": pick("refusal"),
    # ★ 产品线 / 渠道（取自命中 L0 记录；取不到为空串 —— 不编）
    "facets": facets,
    # ★ 检索命中（原文 + 锚点 + sha + 可点直链）—— 守衡那张卡逐条列它（见上面的说明）
    "kb_hits": kb_hits,
    # ★★ 2026-10-20（Owner：「同一单跑完还必须支持重新跑」）：**重跑留痕**。
    #   为什么放在旁挂里：守衡侧 `readReviewSidecar()` 是**整份透传** ⇒
    #   只要这里写了，人被问「这次跟上次一样吗」时守衡答得出来；
    #   而**卡面一个字都不加**（Owner 2026-10-13：口径读数不上卡）。
    #   `rerun_seq` 第一次跑就是 1（不是 0）；`rerun_of` 第一次为空（None，不编）。
    "rerun_seq": _rr.get("rerun_seq"),
    "rerun_of": _rr.get("rerun_of") or None,
    "rerun_prev_state": _rr.get("prev_state") or None,
    "source": "kb/l8/review_run.sh",
}
# ── 台账记账（只追加）：这一轮跑过了，下一轮才认得出「第几次」──
#   ⚠️ 写不成**不许**让这一单失败（评审结论比台账重要），但**要出声**到 stderr
#      （stdout 是旁挂本体，一个字都不能掺）。
try:
    _lp = os.path.join(sys.argv[3], "kb", ".work", "review_seq.ndjson")
    _lp = os.environ.get("KB_REVIEW_SEQ_LEDGER") or _lp
    _row = {"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "base": base,
            "text_sha8": sys.argv[5], "state": state,
            "content_id": pick("content_id"), "reason": None}
    with open(_lp, "a", encoding="utf-8") as _f:
        _f.write(json.dumps(_row, ensure_ascii=False) + "\n")
except Exception as _e:                                    # noqa: BLE001
    import sys as _sys
    _sys.stderr.write("[review_run] ⚠ 重跑台账没写成（不影响本单）：%s\n" % _e)
print(json.dumps(out, ensure_ascii=False))
PYEOF
echo "[review_run] 机读旁挂已写：$SIDECAR" >&2
mirror_sidecar "$SIDECAR" review     # 按单副本（并行时守衡按四把锁挑本单那份）
T_SIDECAR="$(_now)"
# 引擎拒答（NEEDS_INPUT / 退出码 3）时 JSON 仍在 stdout —— 如实转述为「结论未知」
case "$RC" in
  0) exit 0 ;;
  3) echo "[review_run] 引擎拒答（NEEDS_INPUT 一类）—— 如实报「结论未知」，不许说成通过。" >&2; exit 6 ;;
  *) echo "[review_run] 引擎退出码 $RC —— 如实报。" >&2; exit "$RC" ;;
esac
