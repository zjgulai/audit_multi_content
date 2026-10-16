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
#        [--content-type text|image|video] [--two-phase] [--dry-inventory]
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
EXTRA=(); USER_LOADED=()
while [ $# -gt 0 ]; do
  case "$1" in
    --base) BASE="$2"; shift 2 ;;
    --session) SESSION="$2"; shift 2 ;;
    --decision-owner) OWNER="$2"; shift 2 ;;
    --text) TEXT="$2"; shift 2 ;;
    --question) QUESTION="$2"; shift 2 ;;
    --content-type) CTYPE="$2"; shift 2 ;;
    --loaded-skill) USER_LOADED+=("--loaded-skill" "$2"); shift 2 ;;
    --two-phase) EXTRA+=("--two-phase"); shift ;;
    --dry-inventory) EXTRA+=("--dry-inventory"); shift ;;
    -h|--help) sed -n '1,40p' "$0"; exit 0 ;;
    *) echo "未知参数：$1" >&2; exit 2 ;;
  esac
done
[ -n "$BASE" ] || { echo "缺 --base" >&2; exit 2; }
[ -n "$SESSION" ] || { echo "缺 --session" >&2; exit 2; }
[ -n "$OWNER" ] || { echo "缺 --decision-owner（判定主体，装载目录名·中文）" >&2; exit 2; }
[ -n "$TEXT" ] || { echo "缺 --text（素材原文）" >&2; exit 2; }

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
  *) echo "[review_run] ⚠ 判定主体「$OWNER」**不在 --loaded-skill 申报里** —— 结论会留 warning、不得当强证据。" >&2
     echo "[review_run]   你（调用方）必须显式加：--loaded-skill \"$OWNER\"（在你真的用 skill 工具加载它之后）" >&2 ;;
esac

# ── ① 层前置（判据不动；不绿就不往下走）──────────────────────────────────────
echo "[review_run] ① 四层前置 L4→L5→L6→L7 …" >&2
bash "$PREFLIGHT" --base "$BASE" --session "$SESSION" "${EXTRA[@]+"${EXTRA[@]}"}"
RC=$?
case "$RC" in
  0) : ;;
  3) echo "[review_run] 库忙（认领被占）—— 未跑结论。这是**库忙**，不是闸门红。" >&2; exit 3 ;;
  4) echo "[review_run] 某层闸门红 —— 未跑结论（如实报是哪一层）。" >&2; exit 4 ;;
  5) echo "[review_run] 某层审计红 —— 未跑结论（如实报是哪一层）。" >&2; exit 5 ;;
  *) echo "[review_run] 前置异常退出码 $RC —— 未跑结论。" >&2; exit "$RC" ;;
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
echo "[review_run] 若上面是 status=error，那是「没查成」，**不是**「没命中」。" >&2

# ── ③ 出结论（唯一有权产出结论的命令；发布是默认动作）──────────────────────
echo "[review_run] ③ 出结论（含默认发布到飞书）…" >&2
echo "===== ③ 引擎结论（唯一有权产出三态的地方）====="
# ★ stderr 必须单独走文件：引擎会把「飞书发布：…」这类日志打到 stderr，
#   早先写成 2>&1 后这些日志排在 JSON 后面 ⇒ 模板 json.loads 吃到尾随文本而**渲染失败**
#   （实测：链接那单的 agent 只能自己绕过模板去转述，并回头报「工具缺陷」）。
ERRTMP="$(mktemp -t review_run_err.XXXXXX)"
if [ -n "$QUESTION" ]; then
  ENGINE_OUT="$(sh "$KBPY" "$ENGINE" --text "$TEXT" --content-type "$CTYPE" --question "$QUESTION" \
    --require-layer-preflight "$BASE" --decision-owner "$OWNER" \
    "${LOADED[@]+"${LOADED[@]}"}" --json 2>"$ERRTMP")"
else
  ENGINE_OUT="$(sh "$KBPY" "$ENGINE" --text "$TEXT" --content-type "$CTYPE" \
    --require-layer-preflight "$BASE" --decision-owner "$OWNER" \
    "${LOADED[@]+"${LOADED[@]}"}" --json 2>"$ERRTMP")"
fi
RC=$?
[ -s "$ERRTMP" ] && cat "$ERRTMP" >&2
rm -f "$ERRTMP"
printf '%s\n' "$ENGINE_OUT"
echo
echo "===== ③b 转述模板（照抄这一段即可，不必再跑任何命令）====="
printf '%s' "$ENGINE_OUT" | /usr/bin/python3 - <<'PYEOF'
import sys, json
raw = sys.stdin.read()
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

state = str(d.get("decision") or d.get("state") or "").strip().upper() or "(无)"
em = d.get("evidence_meta") or {}
lp = d.get("layer_preflight") or {}
do = em.get("decision_owner") or d.get("decision_owner") or {}
pub = em.get("publish") or d.get("publish") or {}

print("状态：%s ｜ 问题数：%s" % (state, d.get("issue_count")))
if d.get("summary"):
    print("摘要：%s" % d["summary"])
print("层前置：ok=%s mode=%s" % (lp.get("ok"), lp.get("mode")))
if do:
    print("判定主体：%s ｜ mode=%s%s" % (do.get("skill"), do.get("mode"),
          (" ｜ ⚠ " + str(do.get("warning"))) if do.get("warning") else ""))
for f in (d.get("findings") or [])[:20]:
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
    print("★ 本次没有拿到可用的三态结论（%s）—— 如实回「未能得出结论 + 上面的原因」，" % state)
    print("  **不许**自己判三态、**不许**自己写飞书表（实测有单子就是这么把时间烧掉的）。")
PYEOF
# 引擎拒答（NEEDS_INPUT / 退出码 3）时 JSON 仍在 stdout —— 如实转述为「结论未知」
case "$RC" in
  0) exit 0 ;;
  3) echo "[review_run] 引擎拒答（NEEDS_INPUT 一类）—— 如实报「结论未知」，不许说成通过。" >&2; exit 6 ;;
  *) echo "[review_run] 引擎退出码 $RC —— 如实报。" >&2; exit "$RC" ;;
esac
