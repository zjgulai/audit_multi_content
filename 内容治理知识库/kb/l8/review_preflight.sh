#!/bin/bash
# review_preflight.sh —— 评审链四层前置（L4→L5→L6→L7）**一次执行**驱动（S2 · 2026-10-05）
#
# ── 为什么有它（实测，2026-10-05 S2）────────────────────────────────────────
# 改前：L4/L5/L6/L7 **各起一个 subagent**，让它「用 skill 工具加载本层 skill 再执行」。
#   一单实测（RT-20261005-IMG-02，会话留痕解出来的）：
#     L4 子代理 span 124.9 s（工具 4.6 s，**模型生成 120.3 s = 96.4%**）
#     L5 子代理 span 212.2 s（工具 92.7 s，生成 119.5 s）
#     L6 子代理 span 324.9 s（工具 151.1 s，生成 173.8 s）
#     L7 子代理 span 170.6 s（工具 90.5 s，生成  80.1 s，其中 `kb_check` 一次 41.9 s）
#     四个合计 **832.6 s**，其中**模型生成 493.7 s**。
#   而它们跑的命令清一色是**只读探针**（L4 那 18 条命令合计 4.6 s：ls / wc / inline python），
#   真正干活的引擎调用一条都没有 —— 因为 `kb_pipeline.py --sync --via-skill` 自己就会跑
#   本层落章引擎（`SYNC_SPEC`/`STAMP_SPEC`，kb_pipeline.py:254 起，运行时还会回表核对
#   `layers.yaml` 各层 `engine:`）。
#   ⇒ 四层前置是**机械步骤**，不需要四次 LLM 轮次。
#
# ── 本脚本做什么 ───────────────────────────────────────────────────────────
#   把四层前置压成**一次调用**：
#     ⓪ 认领（被占即退，不抢）→ ① 四层闸门 → ② 四层引擎+记账 → ③ 四道审计 → ④ 释放
#   **判据一条没动**：仍是每层一个 RUN（`<BASE>-L4…-L7`）、层侧落章带 `skill` 字段、
#   记账带 `--invoked` / `--skill-session`、四道审计必须红 0、任一红即停不往下叠。
#   顺带摘掉**与本次查询无关的全库自检**（`kb_check` / `skills_check` / `skill_conformance`
#   合计 74 s）—— 那是体检，不是审查；本脚本不跑它们。
#
# ★ 各层 skill 的**加载**仍由调用方（agent）用 `skill` 工具完成 —— 那是上下文动作，
#   脚本做不了。本脚本只负责「加载过之后该跑的东西」一次跑完。
# ★ 层 → skill 的映射**现读** `kb/l7/registry/layers.yaml` 的 `skill:` 字段（唯一真源），
#   与 `skill_invocation_audit.py` 用同一个读取口径，不手抄、不留第二份。
#
# ── 用法 ───────────────────────────────────────────────────────────────────
#   bash kb/l8/review_preflight.sh --base RT-20261005-IMG-02 --session <你的会话标识>
#   bash kb/l8/review_preflight.sh --base X --session Y --dry-inventory   # 只打印将要跑的命令
#   bash kb/l8/review_preflight.sh --base X --session Y --no-claim        # 不认领（自担并发风险）
#   bash kb/l8/review_preflight.sh --base X --session Y --two-phase      # 两段档（默认关）
#
# 退出码：0=四层全绿 ｜ 3=认领被占（别的会话在跑，本次不跑）｜ 4=某层闸门红 ｜ 5=某层审计红 ｜ 2=用法错
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
KBPY="$ROOT/kb/kbpy"
LAYERS_YAML="$ROOT/kb/l7/registry/layers.yaml"
PY="${KB_PY:-/usr/bin/python3}"

BASE=""; SESSION=""; LAYERS="L4,L5,L6,L7"; DO_CLAIM=1; DRY=0; TWO_PHASE=0
# ★ 用 `${SKILL_CHECK:-}`：直接写 `SKILL_CHECK=""` 会把**环境变量**覆盖成空串（实测踩过：
#   `SKILL_CHECK=图片安全审查 bash …` 传进来，脚本自己一句空赋值就把它抹了，闸门只查了层 skill 四个，
#   判定主体那个**没查**，而日志看起来一切正常）。
SKILL_CHECK="${SKILL_CHECK:-}"
while [ $# -gt 0 ]; do
  case "$1" in
    --base) BASE="${2:-}"; shift 2 ;;
    --session) SESSION="${2:-}"; shift 2 ;;
    --layers) LAYERS="${2:-}"; shift 2 ;;
    --skill-check) SKILL_CHECK="${SKILL_CHECK:+$SKILL_CHECK }${2:-}"; shift 2 ;;
    --no-claim) DO_CLAIM=0; shift ;;
    --two-phase) TWO_PHASE=1; shift ;;   # 两段档：①单独过闸门 ②记账（默认关 —— 实测纯重复，白烧 ~58 s）
    --dry-inventory) DRY=1; shift ;;
    -h|--help) sed -n '1,40p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) echo "未知参数：$1" >&2; exit 2 ;;
  esac
done
[ -n "$BASE" ] || { echo "缺 --base <BASE>（形如 RT-20261005-IMG-02）" >&2; exit 2; }
[ -n "$SESSION" ] || { echo "缺 --session <会话标识>（写进 --skill-session 留痕）" >&2; exit 2; }
cd "$ROOT" || exit 2

# ── 层 → skill：现读 layers.yaml（与审计同一口径）────────────────────────────
# 注：macOS 自带 bash 3.2，**没有 mapfile** —— 改用临时文件 + while read（内层命令的
#     stdin 一律 < /dev/null，免得把 map 的行吃掉）。
MAP_TMP="$(mktemp)"
if ! "$PY" - "$LAYERS_YAML" "$LAYERS" >"$MAP_TMP" 2>/tmp/preflight-map.err <<'PYEOF'
import sys, yaml
doc = yaml.safe_load(open(sys.argv[1], encoding="utf-8"))
want = [s.strip() for s in sys.argv[2].split(",") if s.strip()]
found = 0
for x in doc.get("layers", []):
    lid = x.get("layer")
    if lid not in want:
        continue
    sk = x.get("skill")
    sk = [sk] if isinstance(sk, str) else list(sk or [])
    if not sk:
        sys.exit("层 %s 在 layers.yaml 里没有 skill: 字段" % lid)
    print("%s %s" % (lid, sk[0])); found += 1
if not found:
    sys.exit("layers.yaml 里没找到这几层：%s" % sys.argv[2])
PYEOF
then
  echo "读 layers.yaml 失败：" >&2; tail -3 /tmp/preflight-map.err >&2
  rm -f "$MAP_TMP"; exit 2
fi
MAP="$(cat "$MAP_TMP")"; rm -f "$MAP_TMP"
[ -n "$MAP" ] || { echo "没解析出任何层（检查 --layers）" >&2; exit 2; }

say() { echo "[preflight $(date +%H:%M:%S)] $*"; }
CLAIMED=0

# ── 逐层计时（2026-10-12 加；**只记时，不碰任何判定、不改退出码**）─────────────
#   为什么加：生产单实测 ① 层前置 = 17.73s / 21.54s，而**本地**同一份代码只需 7.05s。
#   把两单的层落章时刻摊开看：**四层本身** 生产占 13s/17s，本地只约 2.5s ⇒
#   3 倍差**在「四层跑起来」这一段**，不在认领/锁/审计（那部分固定 ~4.6s）。
#   ⇒ 不逐层量就没法归因（此前已在这上面猜错过两次），故加此埋点。
#   落点：`kb/.work/preflight-segments.ndjson`（**另起一个文件**，追加式）。
#   ★ 与 `kb/.work/last_review_result.json`（守衡只认的旁挂）**物理隔离**；
#     任何异常都被吞掉（`2>/dev/null || true`），不改变 stdout / 退出码 / 任何产物。
#   关掉：`KB_PREFLIGHT_SEG_OFF=1`（关掉后与本埋点加之前**逐字相同**）。
PF_SEG="${KB_PREFLIGHT_SEG:-$ROOT/kb/.work/preflight-segments.ndjson}"
PF_ROWS=""
_now() { /usr/bin/perl -MTime::HiRes=time -e 'printf "%.3f", time' 2>/dev/null || echo 0; }
T0="$(_now)"; T_ACCT0=""; T_ACCT1=""; T_AUD0=""
finish_preflight_seg() {
  [ -n "${KB_PREFLIGHT_SEG_OFF:-}" ] && return 0
  /usr/bin/python3 - "$PF_SEG" "$BASE" "$T0" "$(_now)" "$PF_ROWS" <<'PYSEG' 2>/dev/null || true
import json, os, sys
seg, base, t0, tend, rows = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5]
def fl(x):
    try: return float(x)
    except Exception: return None
t0, tend = fl(t0), fl(tend)
if not t0 or not tend:
    sys.exit(0)
out = []
for line in (rows or "").split("\n"):
    f = line.split("|")
    if len(f) != 4:
        continue
    a, b, c = fl(f[1]), fl(f[2]), fl(f[3])
    out.append({"layer": f[0],
                "acct_s": None if (a is None or b is None) else round(b - a, 3),
                "audit_s": None if (b is None or c is None) else round(c - b, 3)})
rec = {"base": base, "total_s": round(tend - t0, 3), "layers": out,
       "layers_total_s": round(sum((x["acct_s"] or 0) + (x["audit_s"] or 0) for x in out), 3)}
os.makedirs(os.path.dirname(seg), exist_ok=True)
with open(seg, "a", encoding="utf-8") as fh:
    fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
PYSEG
}

cleanup() {
  if [ "$CLAIMED" = "1" ]; then
    sh "$KBPY" l7/scripts/kb_loop_claim.py release --base "$BASE" >/dev/null 2>&1 \
      && say "已释放认领 ${BASE}" || say "⚠️ 释放认领失败（请人工 release --base ${BASE}）"
  finish_preflight_seg
  fi
}
trap cleanup EXIT

# ── ⓪ 认领（全局单槽：不同 BASE 也互斥，这是有意的）────────────────────────
if [ "$DO_CLAIM" = "1" ] && [ "$DRY" = "0" ]; then
  CLAIM_ARGS=(claim --base "$BASE")
  # 上一会话崩了会留下**陈旧**认领（pid 已亡）。它是「可以接手」的，但必须显式 --take-over；
  # 认领**新鲜**时这个 flag 照样被拒（工具自己会再判一次），所以这里先探一次状态再决定。
  if sh "$KBPY" l7/scripts/kb_loop_claim.py status 2>/dev/null | grep -q '陈旧（可 --take-over）'; then
    CLAIM_ARGS+=(--take-over)
    say "检测到陈旧认领（pid 已不在）→ 以 --take-over 接手"
  fi
  if sh "$KBPY" l7/scripts/kb_loop_claim.py "${CLAIM_ARGS[@]}" >/tmp/preflight-claim.out 2>&1; then
    CLAIMED=1; say "认领成功：${BASE}"
  else
    rc=$?
    say "⛔ 认领未成功（exit=${rc}）—— 别的会话在跑这条循环，本次不跑。原文："
    tail -3 /tmp/preflight-claim.out
    exit 3
  fi
fi

# ── ⓪b skill 就绪（2026-10-21 加）：防「skill **静默消失**」──────────────────────
#   病灶（本机实测）：某 skill 的 SKILL.md 落成「信封态」（stat 比内容多 4096），
#   harness 的 dsh-fs-local 读它抛 `FS_NOT_TEXT: binary file` ⇒ 该 skill 被跳过、
#   **不进会话 catalog** ⇒ `skill` 工具报 `unknown or no longer available`。
#   后果不是报错，是**静默降级**：评审照跑、报告照发，判定主体一次都没加载过。
#   实测日志（2026-10-21 09:56/10:03/10:09/10:12 同一条）见 kb/l8/assert_skill_ready.py 头注释。
#   判据：本层声明的 skill（现读 layers.yaml，不抄第二份）+ 调用方用 `--skill-check` 点名的
#   （典型是**判定主体**，如 `--skill-check 图片安全审查`）。红 ⇒ exit 4，停在层闸门之前。
if [ "$DRY" = "0" ] && [ "${KB_SKILL_READY_OFF:-}" != "1" ]; then
  SK_ARGS=()
  while IFS=' ' read -r _L _S; do
    [ -n "${_S:-}" ] && SK_ARGS+=(--skill "$_S")
  done <<EOF
$MAP
EOF
  for extra in ${SKILL_CHECK:-}; do
    case " ${SK_ARGS[*]:-} " in
      *" $extra "*) : ;;
      *) SK_ARGS+=(--skill "$extra") ;;
    esac
  done
  if [ ${#SK_ARGS[@]} -gt 0 ]; then
    if "$PY" kb/l8/assert_skill_ready.py "${SK_ARGS[@]}" --quiet >/tmp/preflight-skill.out 2>&1; then
      say "⓪b skill 就绪 ✅（$(( ${#SK_ARGS[@]} / 2 )) 个：本层 skill + 点名的判定主体）"
    else
      say "⛔ skill 就绪闸门红（exit=4）—— 有 skill 在 harness 侧**读不到**，不许往下跑："
      "$PY" kb/l8/assert_skill_ready.py "${SK_ARGS[@]}" || true
      say "   这不是数据缺陷，是文件落盘成了信封态/坏 frontmatter；修法见 kb/l8/assert_skill_ready.py 头注释。"
      exit 4
    fi
  fi
fi

RC=0

# ── 锁序检查（2026-10-05 实测补；2026-10-08 改成**有界等待**）────────────────
#    认领是**会话级**、kb/.work/.kb.lock 是**命令级**，两者不是一回事。
#    实测踩过：认领拿得到（上一会话已死 → --take-over），但**锁**被另一个活着的进程持着，
#    于是 L4 闸门立刻红 → 报告写成"闸门红"，把「库忙」说成了「库坏」。
#    库内纪律：工具态与数据缺陷必须分开报。所以这里先判锁：
#      · 锁在 & 持有者 pid 活着 → **库忙**（退出码 3），**不删锁**；
#      · 锁在 & pid 已死 → 是 lock.held_dead，交给 kb_pipeline 自己按它的口径处置（本脚本不碰）。
#
# ★★ 2026-10-08（Owner 批准 ④）：**判到「库忙」不再立刻退出，先等一会儿。**
#    为什么：这把锁是**命令级**的 —— `kb_pipeline.py` 每跑一层就持几秒到一分钟，
#    为了它把整单评审弹回去（用户看到的是一张库忙卡）代价完全不对等。
#    认领已经改成**按 RUN 分槽**（①），于是**这把锁成了最后一个会立刻弹库忙的地方**。
#    · 等多久：`KB_LOCK_WAIT_S`（默认 120 秒），每 5 秒复看一次；
#    · **只等「持有者还活着」那一种**：pid 已死的不等（那是要人判断的 lock.held_dead，
#      等它等于把「崩在中途」当成「马上就好」）；
#    · 等的时候**什么都不写**（不删锁、不 --break-lock、不碰认证）——**等 ≠ 撬**；
#    · 等到超时 ⇒ 与改前**逐字同一条路**：报库忙（exit 3）并把锁记录打出来。
LOCK_WAIT_S="${KB_LOCK_WAIT_S:-120}"
#: 复看粒度（2026-10-12 改 5→1）。为什么：旧版每 **5 秒**才复看一次，
#   锁哪怕早 0.1 秒放开，也要白等近 5 秒才继续 —— 而这一等**整段落在关键路径上**
#   （生产 ① 实测比本地多 4.3–4.4s，量级吻合）。改成 1 秒只影响**多久发现锁没了**，
#   **保护语义一个字不动**：仍是「只等持有者还活着的那种」、仍不删锁、不撬锁、
#   上限仍 `KB_LOCK_WAIT_S`。可用 `KB_LOCK_POLL_S` 覆盖（自证用）。
LOCK_POLL_S="${KB_LOCK_POLL_S:-1}"
if [ "$DRY" = "0" ] && [ -f kb/.work/.kb.lock ]; then
  WAITED=0
  while :; do
    LPID=$("$PY" -c "import json;print(json.load(open('kb/.work/.kb.lock')).get('pid',''))" 2>/dev/null)
    if [ -z "$LPID" ] || ! kill -0 "$LPID" 2>/dev/null; then
      # 锁没了、或持有者已死（后者不归本脚本管，交给 kb_pipeline 的口径）
      [ "$WAITED" -gt 0 ] && say "✅ 命令级锁已让开（等了 ${WAITED}s）—— 继续"
      break
    fi
    if [ "$WAITED" -ge "$LOCK_WAIT_S" ]; then
      say "⛔ 库忙：kb/.work/.kb.lock 被**活着的**进程持有（pid=${LPID}）—— 这不是闸门红，是并发互斥。"
      say "   已经等了 ${WAITED}s（上限 KB_LOCK_WAIT_S=${LOCK_WAIT_S}）仍没让开；**不要删锁、不要 --break-lock**。锁记录："
      head -c 300 kb/.work/.kb.lock; echo
      exit 3
    fi
    [ "$WAITED" = "0" ] && say "⏳ 命令级锁被活着的 pid=${LPID} 持着 —— 它有界等待中（上限 ${LOCK_WAIT_S}s，每 ${LOCK_POLL_S}s 复看；不删锁、不撬锁）"
    # ★ 最后一步只睡**剩下的那点**：写死 `sleep 5` 会让上限形同虚设
    #   （实测 `KB_LOCK_WAIT_S=6` 实际等了 10s —— 多睡了一整个周期）。
    LEFT=$((LOCK_WAIT_S - WAITED))
    [ "$LEFT" -gt "$LOCK_POLL_S" ] && LEFT="$LOCK_POLL_S"
    sleep "$LEFT"
    WAITED=$((WAITED + LEFT))
  done
fi
while IFS= read -r pair; do
  [ -n "$pair" ] || continue
  set -- $pair; LID="$1"; SKID="$2"
  RUN="$BASE-$LID"

  # ① 单独过闸门：**默认不跑**（2026-10-05 实测：这是纯重复，白烧 ~58 s/单）
  #    依据：`kb_pipeline.py` 的 ② 那一步**自己就带闸门且红即停** ——
  #      `kb_pipeline.py:830` 红线③「写之前先跑本层闸门；红 → 立即停（不写这一层，更不往下走）」，
  #      `break` 在任何引擎/落章之前。所以 ① 与 ② 的闸门**同源同判据**，跑两次只多花一次的钱
  #      （实测 L6 闸门 54.7 s；一次前置里被跑了两次）。
  #    保留开关给"想看两段分明"的场合：`--two-phase`。
  G=(sh "$KBPY" l7/scripts/kb_pipeline.py --sync --via-skill --only "$LID" --gate-only --run "$RUN")
  # ② 闸门 + 引擎（预演，不带 --apply）+ 记账（本层唯一一次）
  A=(sh "$KBPY" l7/scripts/kb_pipeline.py --sync --via-skill --only "$LID" --run "$RUN" \
        --invoked "$SKID" --skill-session "$LID=$SESSION")
  # ③ 审计
  U=(sh "$KBPY" l7/scripts/skill_invocation_audit.py --run "$RUN")

  if [ "$DRY" = "1" ]; then
    [ "$TWO_PHASE" = "1" ] && printf '  %s\n' "${G[*]}"
    printf '  %s\n' "${A[*]}"; printf '  %s\n' "${U[*]}"
    continue
  fi

  if [ "$TWO_PHASE" = "1" ]; then
    say "① $LID 闸门（两段档）…"
    if ! "${G[@]}" </dev/null >/tmp/preflight-$LID.gate.out 2>&1; then
      say "⛔ $LID 闸门红 —— 停下，不往下叠。尾部："; tail -12 /tmp/preflight-$LID.gate.out; RC=4; break
    fi
    say "① $LID 闸门绿"
  fi

  T_ACCT0="$(_now)"
  say "② $LID 闸门(自带)+引擎(预演)+记账 … invoked=$SKID session=$SESSION"
  if ! "${A[@]}" </dev/null >/tmp/preflight-$LID.acct.out 2>&1; then
    say "⛔ $LID 闸门红/记账非零退出 —— 停下，不往下叠。尾部："; tail -14 /tmp/preflight-$LID.acct.out; RC=4; break
  fi
  say "② $LID 记账完成 → kb/l7/runs/$RUN.json"

  T_ACCT1="$(_now)"; T_AUD0="$T_ACCT1"
  say "③ $LID 审计 …"
  if "${U[@]}" </dev/null >/tmp/preflight-$LID.audit.out 2>&1; then
    say "③ $LID 审计 exit=0（红 0）"
  else
    say "⛔ $LID 审计非零 —— **该层「调了」不算数**，停下。尾部："
    tail -14 /tmp/preflight-$LID.audit.out; RC=5; break
  fi
  PF_ROWS="${PF_ROWS}${LID}|${T_ACCT0:-}|${T_ACCT1:-}|$(_now)"$'\n'
done <<< "$MAP"

if [ "$DRY" = "1" ]; then echo "[dry-inventory] 以上命令未执行"; exit 0; fi

if [ "$RC" = "0" ]; then
  say "✅ 四层前置全绿（L4–L7 各一 RUN，四道审计红 0）｜BASE=$BASE"
  say "   下一步：出结论 —— with_kb_evidence.py --require-layer-preflight $BASE --decision-owner <判定主体>"
else
  say "❌ 四层前置未全绿（exit=${RC}）"
fi
exit $RC
