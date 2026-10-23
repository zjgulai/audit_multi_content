#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""watch_review_readiness.py —— 「@守衡 能不能出结论」的**前置就绪看门狗**。

## 为什么需要它（2026-10-05 事故驱动）

用户实测：10-04 09:05 @守衡 拿到结论，10-04 22:18 超时 30 分钟，10-05 仍然不行。
查下来是**两个互相独立的拦路虎**，但都只在「用户 @ 了一次、等 30 分钟」之后才暴露：

  ① **陈旧认领**：`kb/.work/.kb-loop-claim.json` 持有者 pid 已死，但 TTL 未到
     ⇒ `claim` 一律 exit 3 ⇒ 链子卡在门口 ⇒ 30 分钟超时。
     ★ 而 TTL 过期**不会自动放行**（`claim` 对陈旧认领默认仍拒），
       只提示"它是陈旧的" ⇒ **一次崩溃 = 此后每条 @ 都失败，直到有人 --take-over**。
  ② **数据层陈旧**：user 身份令牌丢失 ⇒ 两张表 `pull_failed` ⇒ `daily_sync` 按库规
     「L0 未对齐就跳过 L1–L6 写档」⇒ L1–L6 产物冻结 ⇒ `freshness.py` 判超期
     ⇒ 评审链 ②c 复判仍超期 ⇒ 拒答。

这两件事**都不该由用户 @ 一次才发现**。本脚本把「就绪」变成可定时巡检的谓词：
  · 能自愈的**当场自愈**（陈旧认领 → `release --force`）；
  · 不能自愈的（缺 user 令牌 / 数据陈旧）→ **主动推飞书**，并给出**可直接复制的那条命令**。

**2026-10-05 追加（③）——修掉看门狗自己的盲区：令牌寿命**：

  ③ **令牌撑不到下次日更**：user 令牌只有 **2 小时**寿命、**没有 refresh token**
     （`auth status` 的 `refreshExpiresAt` 与 `expiresAt` 同值）。
     原先只查「现在在不在」，于是 07:54 对着一枚 09:36 即死的令牌报了 ✅ ——
     而**次日那次日更必然回落失败**。即：这条故障**不是随机的，是每 2 小时必然发生一次**，
     （当年实测时日更在 08:30；2026-10-06 已挪到 03:30 —— **时刻一律从 plist 现读，别在这里写死**）
     只看「现在」的巡检查不出来。现在改成**与下次日更时刻比较**（排期从 launchd plist 读，
     不抄第二份），余量不足一个巡检周期就提前告警。

     ★ 它**非阻断**（与 AGENTS.md 漂移同类）：就绪谓词的语义是「**现在**能不能跑」，
       令牌还没死 ⇒ 现在确实能跑 ⇒ 混进 `ready` 会把这个问题答错。
       它的价值是**前瞻**：让「明天会坏」在**今天**就说出来，而不是等 @ 了一次。

## 它不做什么（刻意）

  · **不改任何闸门判据**：新鲜度结论直接读 `freshness.py`，不自己算、不放宽。
    「陈旧」是去跑供给链的理由，不是可以被豁免的状态 —— 库规写死「不许把这两张表的
    pull_failed 写进 expected 去声明掉，它是回落失效的报警」。本脚本只**报**，不改判据。
  · **不自动跑供给链**：那要持锁、要按层前置口径走，属人工/编排器决策，不在看门狗职责内。

## 用法

    python3 kb/l8/watch_review_readiness.py            # 巡检一次，就绪退出 0，被挡退出 3
    python3 kb/l8/watch_review_readiness.py --no-send  # 不推飞书（调试）
    python3 kb/l8/watch_review_readiness.py --json     # 机读

环境变量：
    KB_ALERT_CHAT   告警落到哪个会话（默认取 2026-10-05 实测的那个 p2p 会话）
    KB_ALERT_COOLDOWN_H  同一原因的告警冷却小时数（默认 6；签名变化则立刻再报）
"""
from __future__ import annotations

import argparse
import datetime
import inspect
import json
import os
import plistlib
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))          # …/知识库/内容治理
sys.path.insert(0, HERE)                               # 同目录共用件（plaintext）
sys.path.insert(0, os.path.join(ROOT, "kb", "l7", "scripts"))   # layer_freshness（唯一新鲜度判据）
# ★ 2026-10-16：出站正文的 markdown 星号收口（KB 侧唯一实现 —— 与守衡 `plain.mjs` 逐字互校）。
#   本脚本的告警是 KB 侧**另一条**直发腿（`lark-cli --text`，不经过守衡进程）。
from plaintext import guard, has_md_symbols, plainify, plainify_for_send  # noqa: E402
# ★ 2026-10-16：周更兜底要问「这一轮跑成了没有」—— 用的还是 `layer_freshness.judge()`
#   那把尺子（`change_state`），**不新造第二把**。阈值仍归它，这里只问「跑没跑」。
from layer_freshness import judge as _lf_judge          # noqa: E402
KBPY = os.path.join(ROOT, "kb", "kbpy")
LARK = os.path.expanduser("~/.dsh/bin/lark-cli")
STATE = os.path.join(ROOT, "kb", ".work", ".review-readiness-alert.json")
DEFAULT_CHAT = "oc_7775e2dacb6f2ebc9789cd6e681de5f7"

# 日更排期的**唯一真源**是 launchd 的 plist —— 不在这里抄第二份（AGENTS.md 的纪律：
# 抄出去的第二份必然过期）。读不到就返回 None，由调用方按「判断不了」处理。
DAILY_PLIST = os.path.expanduser("~/Library/LaunchAgents/com.kb.pipeline-daily.plist")
HORIZON_MARGIN_MIN = 30          # 巡检周期；留一个周期当缓冲

COOLDOWN_H = float(os.environ.get("KB_ALERT_COOLDOWN_H") or 6)

# ── ★★ 受控自愈（2026-10-07，Owner 批准「先修复新鲜度问题」）──────────────────────────
#  为什么必须有它（2026-10-07 事故实测，全链条三处叠在一起）：
#    ① **零余量**（**当时的形状**）：陈旧阈值 24h（`daily_health.py`），日更每 24h 一次（03:30）
#       ★★ 2026-10-16 Owner 裁定①：日更改**周更（每周日 03:30）**，阈值同时 24h → **8 天**。
#          **放宽阈值 = 同时放宽了保护** ⇒ 兜这个缺口的是下面新增的 `check_weekly_run_ran()`
#          （排期时刻过 12h 还没跑成 ⇒ 当天报、阻断级冷却），**不是**靠把阈值调小。
#       ⇒ 日更失败一次，次日同一时刻起**必然**全量降级；
#    ② **自愈路径不可能自愈**：引擎发现陈旧会「自动跑层」，但那是 **dry-run**（不带 --apply）
#       ⇒ 推不动水位。实测那句原话：`跑层后仍超期 ⇒ 拒答（fail-closed）`；
#    ③ **告警只告警**：本巡检每 30 分钟巡到红、推一条飞书，然后**什么都不做**；
#       而「同因 6h 冷却」还会把一个**全量拒答级**的问题压成沉默（2026-10-07 15:35/16:05 两条
#       都是 `冷却中（0.5h < 6.0h）`）。
#  ⇒ 本段只做一件事：**前端全部满足时，踢一次那条本来就该跑的日更作业**
#     （`launchctl kickstart -k`，launchd 里那条日常作业自己会认领、自己会释放 —— 不是我临时拼的写库命令）。
HEAL_COOLDOWN_MIN = float(os.environ.get("KB_HEAL_COOLDOWN_MIN") or 45)
HEAL_MAX_PER_DAY = int(os.environ.get("KB_HEAL_MAX_PER_DAY") or 3)
HEAL_STATE = os.path.join(ROOT, "kb", ".work", ".review-readiness-heal.json")
HEAL_LEDGER = os.path.join(ROOT, "kb", ".work", "freshness-heal.ndjson")
DAILY_SKILL_LABEL = "com.kb.pipeline-daily-skill"
#: 「阻断级」问题的重报间隔 —— 比 6h 短得多：一个让**整条评审链拒答**的问题，
#: 沉默 6 小时等于让人在黑暗里等（2026-10-07 就是这么发生的：警报响过，然后没声了）。
# ★ 2026-10-10（Owner 定）：阻断级重复告警从 **1h 改成 24h** ——「一天最多一条」。
#   为什么改：当天实测**同一条陈旧推了 6 次**（04:25/05:26/06:27/07:29/08:30/11:03），
#   后 5 条没有携带任何新信息（同一个 `stale_items`、同一个原因码）⇒ 那是噪声，不是提醒。
#   这与日更自己的口径对齐：日更摘要推送早就做了「**今天已推过，不再推**」的门
#   （见 `~/Library/Logs/kb-pipeline-skill/launchd-out.log` 的 `[digest] ⏭` 那行），
#   而告警这条腿一直是 1h ⇒ **两条腿的门不一致**。
#   代价（如实写）：一轮真陈旧拖过一天，中间不会再响 —— 靠 `signature()` 兜住：
#   **层集合变了 / 原因变了 ⇒ 立刻再报**（`should_alert` 的「原因变化」分支），所以
#   「换了层的陈旧」不会被 24h 沉默掉，被沉默的只有「同一个层集合反复响」。
#   为什么当初是 1h（2026-10-07）：那天 6h 冷却把一条全量拒答级问题压成一声沉默 ⇒ 调到 1h。
#   现在的问题是它的反面（太吵）—— **两个方向都要防**：一天一条 + 原因变化即报。
#   ⇒ 这条的历史要在两处文件里保持对称：本注释、`should_alert()` 的 docstring、以及
#     `~/.dsh/AGENTS.md` 的巡检那一节（**三处写的是同一件事，改一处就要改三处**）。
BLOCKING_COOLDOWN_H = float(os.environ.get("KB_ALERT_COOLDOWN_BLOCKING_H") or 24)


def run(argv, timeout=180):
    """跑一条命令，返回 (exit, stdout, stderr)。**不抛** —— 巡检不许因为一条命令挂掉而中断。"""
    try:
        p = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True,
                           timeout=timeout, errors="replace")
        return p.returncode, p.stdout, p.stderr
    except subprocess.TimeoutExpired:
        return 124, "", f"timeout after {timeout}s"
    except Exception as exc:                                    # noqa: BLE001
        return 125, "", repr(exc)


# ────────────────────────────────────────────── 三项阻断检查（认领 / 凭据 / 新鲜度）

def check_claim():
    """陈旧认领 → **当场自愈**（release --force）。返回 (ok, detail)。"""
    rc, out, err = run(["sh", KBPY, "l7/scripts/kb_loop_claim.py", "status"], timeout=60)
    text = (out or "") + (err or "")
    if "无认领" in text:
        return True, "空闲（无认领）"
    if "陈旧" in text:
        rc2, out2, err2 = run(["sh", KBPY, "l7/scripts/kb_loop_claim.py",
                               "release", "--force"], timeout=60)
        ok = (rc2 == 0)
        return ok, {
            "action": "自愈：释放陈旧认领",
            "before": text.strip()[:300],
            "release_exit": rc2,
            "release_out": (out2 or err2).strip()[:200],
        }
    # 新鲜认领：别人正在跑，这是**正常状态**，不算故障
    return True, {"note": "有新鲜认领（别的会话在跑），非故障", "status": text.strip()[:300]}


def _lark_env():
    return dict(os.environ, PATH=os.path.expanduser("~/.dsh/bin") + ":" + os.environ.get("PATH", ""))


# 两张「曾经只有 user 身份才读得到」的表 —— 日更的 L0 pull 必须能拿到它们。
PROBLEM_TABLES = (
    ("SKkkbdZi9aRuMzs7ob0cpSYHnQg", "tbl8AI00JZO1iZtp", "专家修订汇总表"),
    ("SKkkbdZi9aRuMzs7ob0cpSYHnQg", "tblVdl0jdK9G4ld3", "内容公式（仅供参考）"),
)


def _interpret_bot_probe(rc, stdout, stderr):
    """把一次探针的**原始读数**翻译成三态。**纯函数**，不联网 —— 自证直接喂样本进来。

    ★ 为什么把这一步单独拆出来（2026-10-06）：判据必须**能被调用**才有判据可言。
      事故里那句话之所以能发出去，是因为「探针的原始输出」与「结论」之间隔着一个 subprocess，
      没有任何用例走得进去。`AGENTS.md` §2.4.7 的方法教训写的就是这一条：
      **判据没盖住的那一跳，就是事故所在的那一跳。**
    """
    raw = (stdout or "").strip()
    i = raw.find("{")
    if i < 0:
        # ★ 08:19:59 那一格的形状，逐字复刻在这里：stdout 里没有 JSON。
        #   旧代码把它读成 `ok=False`（「bot 读不到」），而它真正说的是「这一次什么都没测到」。
        err = (stderr or "").strip()[:120]
        return None, (f"未测：探针 stdout 里没有 JSON（rc={rc}｜stdout {len(raw)} 字｜"
                      f"stderr：{err or '空'}）—— 这**不是**「bot 读不到」")
    try:
        d = json.loads(raw[i:])
    except json.JSONDecodeError as exc:
        return None, f"未测：探针输出不是合法 JSON（{exc}）"
    if not isinstance(d, dict) or "ok" not in d:
        keys = sorted(d)[:8] if isinstance(d, dict) else type(d).__name__
        return None, f"未测：返回里没有 `ok` 字段（形状不认识：{keys}）"

    if d.get("ok"):
        return True, None
    e = d.get("error") or {}
    if not e:
        # `ok:false` 却连 error 都没有 ⇒ 判不出是不是权限问题。落未测，**不许**当成被拒。
        return None, "未测：`ok=false` 但 error 为空 —— 判不出是权限还是别的原因"
    return False, f"{e.get('type')}/{e.get('subtype')}｜{str(e.get('message'))[:160]}"


def _bot_can_read(base, table):
    """用 **bot 身份**直读一张表（只取 1 条，不写库）。返回**三态** `True | False | None`。

    **事故（这条改动的全部理由）**：08:19:59 那次巡检报了「审查链**当前不可用**」并推了飞书，
    而同一张表在 **30 分钟前（07:49）** 与 **3 分钟后（08:23）** 都是通的 ——
    直读 5/5、连打 20/20 全通。它留下的错误串是 `None/None｜None`：**字段全空**。
    飞书真拒绝会带 type/subtype/message；全空只说明**探针的 stdout 里没有可解析的 JSON**。

    三态的含义见 `_interpret_bot_probe`；这一层只负责跑进程与把超时/异常归进「未测」。
    """
    try:
        p = subprocess.run(
            [LARK, "base", "+record-list", "--base-token", base, "--table-id", table,
             "--page-size", "1", "--as", "bot", "--profile", "dsh-kb", "--json"],
            capture_output=True, text=True, timeout=60, env=_lark_env(), errors="replace")
    except subprocess.TimeoutExpired:
        # 超时 ≠ 读不到：它连一句话都还没说。旧代码把它归进「bot 直读失败」。
        return None, "未测：探针 60s 超时（CLI/网络卡住，**不是**「bot 读不到」）"
    except Exception as exc:                                    # noqa: BLE001
        return None, f"未测：探针跑不起来 {exc!r}"
    return _interpret_bot_probe(p.returncode, p.stdout, p.stderr)


def _user_identity():
    """回落身份（user 令牌）现在还能不能用。返回 `(available_or_None, info)`。

    `None` 表示**未测**（auth status 跑不起来）—— 与「明确不可用」分开，
    否则「问不到」会被当成「没有」。
    """
    try:
        p = subprocess.run([LARK, "auth", "status", "--profile", "dsh-kb", "--json"],
                           capture_output=True, text=True, timeout=60, env=_lark_env(), errors="replace")
        d = json.loads(p.stdout or "{}")
    except Exception as exc:                                    # noqa: BLE001
        return None, {"reason": f"未测：auth status 跑不起来：{exc!r}"}
    user = ((d.get("identities") or {}).get("user") or {})
    return bool(user.get("available")), user


def check_credential():
    """日更的凭据够不够 —— **按 pull 的真实主身份（bot）判，不按 user 判**。

    ★ 2026-10-06 改（旧判据会天天误报）。旧版问的是「user 身份可用吗」，并断言
      「缺了 ⇒ 两张表必然 pull_failed」。**该断言已失效**：Owner 在飞书侧把守衡 bot
      加成可阅读协作者后，**bot 直读两张表都成功**；而
      `kb/l8/align_l0_feishu.py` 的 `AS_ID = os.environ.get("L8_AS", "bot")` 说明
      **pull 的主身份本来就是 bot**，user 只是回落（`L8_AS_FALLBACK`）。
      ⇒ 旧判据会在 bot 完全够用的情况下报红、并推飞书告警（冷却 6h）。

    ★ 同日再改（**未测不是红**）：08:19:59 那次报红的真身是**探针没输出**，不是权限被拒。
      现在三态各自分开：两张都读到 ⇒ 绿；飞书明确拒绝且无回落 ⇒ 红；
      **探针没跑起来 ⇒ 未测（`None`）**，且这一格**决定不了一句话**说「链坏了」。
    """
    if not os.path.exists(LARK):
        # 找不到 CLI 是**确定的**坏（日更的 `align_l0_feishu.py` 也走它）⇒ 红，不是未测。
        return False, {"reason": f"找不到 lark-cli：{LARK}"}

    # ① 主身份：bot 直读两张表（这正是日更 pull 走的那条路）
    bad = {}                     # name -> (state, detail)，state ∈ {False, None}
    for base, table, name in PROBLEM_TABLES:
        st, detail = _bot_can_read(base, table)
        if st is not True:
            bad[name] = (st, detail)
    if not bad:
        return True, {
            "identity": "bot",
            "bot_direct_read": "两张表都通（专家修订汇总表 / 内容公式）",
            "note": "日更 pull 的主身份就是 bot（`L8_AS` 默认 bot）⇒ **user 令牌不再是它的前置条件**。",
        }

    denied = {n: d for n, (s, d) in bad.items() if s is False}      # 飞书明确拒绝
    untested = {n: d for n, (s, d) in bad.items() if s is None}     # 探针没跑起来

    # ② 回落身份：user 令牌还能不能用（这道回落与「凭据寿命」非阻断项是同一件事的两面）
    user_ok, user = _user_identity()
    if user_ok:
        return True, {"identity": "user(回落)", "bot_fail": {**denied, **untested},
                      "user": user.get("userName"),
                      "note": "bot 读不到/没测成，靠 user 令牌回落 —— 能跑，但令牌只活 2 小时。"}

    if denied:
        return False, {
            "reason": "**飞书明确拒绝 bot 直读**，且 user 令牌也不可用 ⇒ 这两张表 pull_failed，"
                      "→ 日更会跳过 L1–L6 写档 → 数据停更 → 评审链拒答",
            "bot_fail": denied,
            **({"bot_untested": untested} if untested else {}),
            "detail": user.get("message"),
            "fix": "【先核这一句】bot 直读在 2026-10-06 实测**已经通了**（两张表都读得到）⇒ "
                   "先按上面 `bot_fail` 里的 error 类型判断是**资源权限**还是 **scope**"
                   "（两者修的地方不同，别混），并确认是不是**回退了**"
                   "（协作者被移除 / Base 或表被换掉）—— 别把已经加好的协作者再加一遍。"
                   "  【应急】~/.dsh/bin/lark-cli auth login --profile dsh-kb（需本人扫码；令牌只活 2 小时）",
        }

    # ③ 只有「未测」：探针没跑起来 + 没有回落 ⇒ **判不出此刻能不能跑**。
    #    这一格以前会被说成「审查链当前不可用」—— 那句话说出去的时候没有依据。
    return None, {
        "reason": "**未测**：bot 探针没跑起来，且 user 令牌不可用 ⇒ "
                  "**判不出**此刻能不能跑（这既不是「读不到」，也不是「链坏了」）。"
                  "→ 处置：隔几分钟再巡一次；同一张表连着两次未测才值得动手查。",
        "bot_untested": untested,
        "detail": user.get("message"),
    }


def _read_plist_tolerant(path):
    """读 launchd plist，**先严格、后宽松**。

    为什么要两档（2026-10-05 实测）：本机 `com.kb.pipeline-daily.plist` **不是 well-formed XML** ——
    它的注释里写了 `kb_pipeline.py --check`，而 **XML 注释内禁止出现 `--`**。
    `plutil -lint` 与 launchd 都宽容（照跑不误），python 的 expat 不宽容（直接抛 ExpatError）。
    ⇒ 巡检**不能把「能不能读到排期」押在解析器的宽容度上**，否则它会静默降级成「判断不了」。
    严格档读不到时退回正则只取 Hour/Minute（够本用途；排期不是这份文件的安全边界）。
    """
    try:
        with open(path, "rb") as fh:
            raw = fh.read()
    except Exception as exc:                                    # noqa: BLE001
        return None, f"读不到文件（{exc!r}）"
    try:
        d = plistlib.loads(raw)
        return (d if isinstance(d, dict) else {}), "plistlib"
    except Exception:                                           # noqa: BLE001
        pass
    try:
        txt = raw.decode("utf-8", "replace")
        blk = re.search(r"<key>StartCalendarInterval</key>\s*<dict>(.*?)</dict>",
                        txt, re.S)
        if not blk:
            return None, "宽松档：找不到 StartCalendarInterval 段"
        seg = blk.group(1)
        out = {}
        for fld in ("Hour", "Minute"):
            m = re.search(r"<key>%s</key>\s*<integer>(\d+)</integer>" % fld, seg)
            if m:
                out[fld] = int(m.group(1))
        if not out:
            return None, "宽松档：段里没有 Hour/Minute"
        return {"StartCalendarInterval": out}, "regex（原文非 well-formed XML）"
    except Exception as exc:                                    # noqa: BLE001
        return None, f"宽松档也失败（{exc!r}）"


def _read_schedule(path=None):
    """读 launchd 排期 → `({"hour","minute","weekdays","period_days"}, how)`；读不到回 `(None, why)`。

    ★★ 2026-10-16：日更改**周更**（每周日 03:30）⇒ 排期里多了 `Weekday`。
      而原先只有 `next_daily_run()` 一个读法、**只取 Hour/Minute** ⇒ 会把「每周日 03:30」
      当成「每天 03:30」：
        · 令牌前瞻算出一个**不存在的下次日更时刻**；
        · 它那句 `interval_h = nxt - (nxt - 1 天)` 更是个**恒等式**（恒等于 24h），
          从来就没读过排期 —— 日更一变成周更，那句话当场变成假话。
      ⇒ 排期解析**只留这一处**：`next_daily_run()` / `last_due()` / 凭据前瞻 / 周更兜底
        全调它（抄出去的第二份必然过期）。

    launchd 口径：`Weekday` **0 与 7 都是周日**，1=周一 … 6=周六；没有 `Weekday` = 每天。
    多档排期（list）取第一档；多天（如 `[0, 3]`）按天数推周期。
    """
    path = path or DAILY_PLIST
    d, how = _read_plist_tolerant(path)
    if d is None:
        return None, how
    cal = d.get("StartCalendarInterval") or {}
    if isinstance(cal, list):                       # 多档排期：取最早的一档
        cal = cal[0] if cal else {}
    try:
        hh, mm = int(cal.get("Hour", 8)), int(cal.get("Minute", 30))
    except Exception as exc:                                    # noqa: BLE001
        return None, f"排期字段读不出（{exc!r}）"
    wd = cal.get("Weekday")
    raw = wd if isinstance(wd, (list, tuple)) else ([wd] if wd is not None else [])
    try:
        wds = sorted({int(x) % 7 for x in raw})     # 0 与 7 都归 0（周日）
    except Exception as exc:                                    # noqa: BLE001
        return None, f"Weekday 读不出（{exc!r}）"
    return {"hour": hh, "minute": mm, "weekdays": wds,
            "period_days": (1.0 if not wds else 7.0 / len(wds))}, how


def _next_after(spec, now):
    """排期里**严格晚于 now** 的第一个时刻（认 Weekday；没有 Weekday 就是每天）。"""
    cand = now.replace(hour=spec["hour"], minute=spec["minute"], second=0, microsecond=0)
    if not spec["weekdays"]:
        return cand + datetime.timedelta(days=1) if cand <= now else cand
    for i in range(0, 8):
        c = cand + datetime.timedelta(days=i)
        # `datetime.weekday()`：周一=0 … 周日=6 ⇒ +1 取模换成 launchd 的「周日=0」口径。
        if ((c.weekday() + 1) % 7) in spec["weekdays"] and c > now:
            return c
    return None


def next_daily_run(now=None, path=None):
    """下次**日更／周更**的时刻。**从 launchd 的 plist 读**，读不到返回 None。

    返回 None 表示「判断不了」—— 调用方**不许**把它当「没问题」。
    """
    now = now or datetime.datetime.now().astimezone()
    spec, how = _read_schedule(path)
    if spec is None:
        return None, how
    nxt = _next_after(spec, now)
    if nxt is None:
        return None, "排期算不出下次时刻（Weekday=%r）" % (spec.get("weekdays"),)
    return nxt, how


def last_due(now=None, path=None):
    """**已经过去**的最近一个排期时刻 → `(时刻, how)`（周更兜底判据用它）。

    读不到排期 ⇒ `(None, why)`；调用方必须按**未测**处置（缺件 ≠ 坏件）。
    """
    now = now or datetime.datetime.now().astimezone()
    spec, how = _read_schedule(path)
    if spec is None:
        return None, how
    cand = now.replace(hour=spec["hour"], minute=spec["minute"], second=0, microsecond=0)
    if not spec["weekdays"]:
        return (cand if cand <= now else cand - datetime.timedelta(days=1)), how
    for i in range(0, 8):
        c = cand - datetime.timedelta(days=i)
        if ((c.weekday() + 1) % 7) in spec["weekdays"] and c <= now:
            return c, how
    return None, "排期算不出「最近一次该跑的时刻」"


def check_credential_horizon():
    """user 令牌**撑得到下次日更吗** —— 撑不到就提前报，别等日更那天才发现。

    为什么必须单列这一条（2026-10-05 实测出来的**看门狗自身盲区**）：
      守衡的 L0 回落靠 user 令牌，而这枚令牌**只有 2 小时寿命、且没有 refresh token**
      （`auth status` 的 `refreshExpiresAt` 与 `expiresAt` **同值**；登录时输出
      `[WARN] no refresh_token in response`）。
      ⇒ 「现在可用」**根本不等于**「日更那天可用」。
      只看「现在在不在」的就绪巡检，会对着一枚 2 小时后即死的令牌报 ✅（实测 07:54 就报了），
      然后在**次日那次日更**让 L0 回落失败 → 跳过 L1–L6 → 数据停更 → 评审链拒答。
      那正是用户抱怨的「每次 @ 一次就要重新解决」的**复发路径**：
      故障不是随机发生的，是**每 2 小时必然发生一次**，只是以前要等 @ 了一次才知道。

    ★ **非阻断**：此刻评审链确实能用（令牌还没死），把它混进 `ready` 会让就绪谓词失真 ——
      就绪谓词的语义是「现在能不能跑」，不是「明天能不能跑」。所以它与 AGENTS.md 漂移同类：
      **要告警，但不改 ready、不改退出码**。
    """
    if not os.path.exists(LARK):
        return True, {"note": "lark-cli 不在，凭据项已单独报"}
    env = dict(os.environ, PATH=os.path.expanduser("~/.dsh/bin") + ":" + os.environ.get("PATH", ""))
    try:
        p = subprocess.run([LARK, "auth", "status", "--profile", "dsh-kb", "--json"],
                           capture_output=True, text=True, timeout=60, env=env, errors="replace")
        d = json.loads(p.stdout or "{}")
    except Exception as exc:                                    # noqa: BLE001
        return False, {"reason": f"取令牌寿命失败：auth status 跑不起来（{exc!r}）"}
    user = ((d.get("identities") or {}).get("user") or {})
    if not user.get("available"):
        return True, {"note": "user 身份当前不可用 —— 由「凭据」项报，本项不重复报"}

    exp_raw = user.get("expiresAt") or user.get("refreshExpiresAt")
    try:
        exp = datetime.datetime.fromisoformat(exp_raw)
        if exp.tzinfo is None:
            exp = exp.astimezone()
    except Exception:                                           # noqa: BLE001
        return False, {"reason": f"拿不到可解析的令牌到期时间（expiresAt={exp_raw!r}）"
                                 " ⇒ **判断不了**它能不能撑到下次日更，按不通过报（读不到 ≠ 没问题）"}

    nxt, how = next_daily_run()
    if nxt is None:
        return False, {"reason": "读不到日更排期（" + DAILY_PLIST + f"，原因：{how}）"
                                 " ⇒ **判断不了**令牌能不能撑到下次日更（读不到 ≠ 没问题）",
                       "expires_at": exp.isoformat()}

    # ★ 结构性事实（2026-10-05 实测，三个数都能重算）：
    #   令牌寿命 2.0h ＜ 日更间隔 24h ⇒ **一次扫码最多只能覆盖一次日更**，
    #   想让它天天有效，就得**在每天那次日更之前重扫一次**（旧写法把「06:30–08:30」写死在这里，
    #   日更一挪就成假话；此刻**从 plist 现读**，不抄第二份）—— 那不是一个可接受的运维动作。
    #   ⇒ 「扫码」治不了这个病，根治只有两条：拿到 refresh token，或给守衡 bot 授该 Base 阅读权。
    #   这条事实**每次都报**（进输出与 JSON），但**不单独告警** —— 它是常驻状态，
    #   每 30 分钟推一次会把告警淹掉（库规：无人值守的日报如果每天报同一个假红，第三天就没人看）。
    structural = None
    life_h = None
    interval_h = None
    try:
        g = datetime.datetime.fromisoformat(user.get("grantedAt") or "")
        if g.tzinfo is None:
            g = g.astimezone()
        life_h = (exp - g).total_seconds() / 3600.0
        # ★★ 2026-10-16 修（周更暴露出来的**恒等式**）：原先是
        #   `interval_h = (nxt - (nxt - 1 天))` —— 它**恒等于 24h**，从来没读过排期。
        #   日更时它"碰巧对"，周更后它当场变成假话（周期是 7 天）。现在从排期现算。
        _spec, _ = _read_schedule()
        interval_h = ((_spec or {}).get("period_days") or 1.0) * 24.0
        if life_h < interval_h:
            structural = (f"令牌寿命仅 {life_h:.1f}h ＜ 更新周期 {interval_h:.0f}h ⇒ "
                          "**一次扫码最多只覆盖一次更新**；想让它每次都有效就得**在每次更新之前重扫**，"
                          "那不是可接受的运维动作。⇒ 扫码治不了这个病，根治只有两条："
                          "① 在飞书侧把「守衡」bot 加成 Base SKkkbdZi9aRuMzs7ob0cpSYHnQg 的可阅读协作者"
                          "（bot 直读成功，回落与令牌整条链路不再需要）；"
                          "② 拿到带 refresh token 的授权方式。")
    except Exception:                                           # noqa: BLE001
        pass

    margin = datetime.timedelta(minutes=HORIZON_MARGIN_MIN)
    covers = exp > nxt + margin
    base = {"expires_at": exp.isoformat(), "next_daily_run": nxt.isoformat(),
            "schedule_period_h": interval_h,
            "lifetime_h": round(life_h, 2) if life_h is not None else None,
            "covers_next_run": covers, "structural_recurs": bool(structural),
            "structural_note": structural}
    if covers:
        return True, {**base, "note": "令牌撑得过下次日更"}
    # ★★ 2026-10-16：**周期长过一天 ⇒ 这条前瞻退化成常驻事实，只进输出、不单独告警。**
    #   理由不是"嫌吵"：本文件自己的纪律写着「常驻状态每次都报，但**不单独告警**」，
    #   而 `covers_next_run` 在周更（168h 周期 / 2h 令牌）下**永远是 False** ——
    #   每 6h 推一条，正是"假红挤掉真问题"。
    #   取「一天」当界线是因为：一天以内，"下次更新前重扫一次"还是个**可行动作**；
    #   超过一天（周更 7 天），要重扫 84 次，那个 fix 已经不是修法了。
    #   而且 pull 的**主身份是 bot**（「凭据」项每次实测两张表都通），令牌只是回落 ——
    #   把回落说成"会导致评审链拒答"在今天就说过头了。
    if interval_h is not None and interval_h > 24.0:
        return True, {**base,
                      "note": "更新周期 %g 天 ＞ user 令牌寿命 %s ⇒ 本条是**常驻事实**，不是新故障"
                              "（回落身份才用它；主身份是 bot，见「凭据」项）"
                              % (interval_h / 24.0,
                                 ("%.1fh" % life_h) if life_h is not None else "未知")}

    remain_h = (exp - datetime.datetime.now().astimezone()).total_seconds() / 3600.0
    return False, {
        **base,
        "reason": f"user 令牌**撑不到下次日更**：它到期时，下一次日更（{nxt.strftime('%H:%M')}）还没开始。"
                  "届时 L0 的两张表会回落失败 ⇒ 日更跳过 L1–L6 ⇒ 数据停更 ⇒ 评审链拒答。"
                  "**这不是随机故障，是每 2 小时必然发生一次**，现在提前报，别等它发作。",
        "remaining_h": round(remain_h, 2),
        "now_usable": "此刻评审链**仍可用**（令牌还没死）—— 本条是前瞻预警，不是当前阻断",
        "fix": "在下次日更前重扫一次： ~/.dsh/bin/lark-cli auth login --profile dsh-kb"
               "   （device flow，需本人手机确认，链接 10 分钟内有效）"
               "   ▶ **一次性根治**：在飞书侧把「守衡」bot 加成 Base "
               "SKkkbdZi9aRuMzs7ob0cpSYHnQg 的可阅读协作者 ⇒ bot 直读成功，"
               "回落链路整条不再触发，从此不再依赖这枚 2 小时令牌。",
    }


def check_skill_links():
    """装机位的**符号链接**是否都还解析得开（2026-10-05 加，symlink 试点配套护栏）。

    为什么必须有一条（试点工具自己写明的代价）：
      `dsh-skill-filesystem` 的 `nodeEntryKind()` 在 `isSymbolicLink()` 之后用 `stat()` 跟随链接；
      **链接断裂时它只打一条 warning 就 `return void 0`** ⇒ 该 skill 会**从技能目录里静默消失**。
      实测过的形态：`kb-l0-feishu` 曾因文件表示层损坏而不进目录，症状同样是"skill 不见了"，
      但**没有任何闸门报红** —— 直到有人 @ 一次、链路断在第 1 层才发现。
    ⇒ 既然我们把装机位从"实体镜像"改成"指向真源的符号链接"（kb-p0-check / kb-l0-feishu 已改），
      就必须有人替那条链接**定期解析一次**，否则是我们自己引入了一个静默失效点。

    ★ **阻断项**：某层 skill 消失 ⇒ 评审链那一层的"逐层调 skill"必然做不到 ⇒ 确实不该说"就绪"。
    """
    root = os.path.expanduser("~/.dsh/skills")
    if not os.path.isdir(root):
        return False, {"reason": f"找不到技能根 {root}"}
    try:
        names = sorted(os.listdir(root))
    except Exception as exc:                                    # noqa: BLE001
        return False, {"reason": f"列不出技能根（{exc!r}）"}
    links, broken, dirs = [], [], []
    for n in names:
        p = os.path.join(root, n)
        if os.path.islink(p):
            links.append(n)
            if not os.path.exists(p):            # exists() 跟随链接 ⇒ False 即断链
                broken.append({"skill": n, "target": os.readlink(p)})
        elif os.path.isdir(p):
            dirs.append(n)
    if broken:
        return False, {
            "reason": "装机位有**断链的符号链接** ⇒ 这些 skill 会**从技能目录里静默消失**，"
                      "评审链那一层的『逐层调 skill』会直接做不到（且不会有别的闸门报红）",
            "broken": broken,
            "fix": "重建链接或在真源在位时直接指回真源："
                   " ln -sfn \"<库内真源路径>\" ~/.dsh/skills/<skill>"
                   "   ▶ 复核：git -C ... 无需；直接 `python3 _eval-*/tools/extract_catalog.py "
                   "--skill <skill> <新会话文件>` 看它是否回到目录里",
        }
    return True, {"symlink_装载位": len(links), "实体目录": len(dirs), "断链": 0,
                  "已链接": links[:12]}


def check_freshness():
    """直接读 freshness.py 的结论（**不自己算、不放宽**）。

    ★ 自证专用闸门（2026-10-07）：`KB_FRESHNESS_FORCE_STALE=1` ⇒ **强制判陈旧**，
      只为让「陈旧 ⇒ 自愈」这条分支能被人**真的跑一遍**（否则它只能等下次真事故才首验）。
      与 `SHOUHENG_REVIEW_TABLE=off` 同一种做法：**只认环境变量、默认关**，
      launchd 不会设它 ⇒ 定时跑永远走真判据；且命中时在读数里**写明是强制**（不许冒充真读数）。
    """
    if os.environ.get("KB_FRESHNESS_FORCE_STALE") == "1":
        return False, {
            "reason": "**自证用闸门 `KB_FRESHNESS_FORCE_STALE=1`：本次是强制判陈旧**"
                      "（不是真读数；只为验证自愈分支）",
            "exit": 3, "forced": True,
            "stale_items": ["（强制）L0 的 manifest.jsonl 落后 N 天",
                            "（强制）最近一次成功 RUN 距今 > 24 小时 ⇒ 陈旧"],
            "fix": "这条是自证用的强制读数；真实修法见下面的自愈动作。",
        }
    rc, out, err = run(["sh", KBPY, "l7/scripts/freshness.py"], timeout=300)
    text = (out or "") + (err or "")
    stale = (rc == 3) or ("拒答" in text) or ("超期" in text and "❌" in text)
    if not stale:
        return True, {"exit": rc, "tail": text.strip()[-300:]}
    lines = [ln.strip() for ln in text.splitlines() if ln.strip().startswith("·")]
    return False, {
        "reason": "数据层超期 ⇒ 评审链 ②c 复判仍会超期 ⇒ 拒答",
        "exit": rc,
        "stale_items": lines[:6],
        "fix": "**陈旧不再自动踢整链**（2026-10-20 Owner 定 ①，实测依据见 heal_decision() 开头）："
               "周更模式下踢整链补不回某一层的红，反而会在排期前抢跑、占认领、"
               "把行的运行时间戳刷成「像跑过了」。"
               "**下一步**：`sh kb/kbpy l7/scripts/freshness.py` 看是哪一层落后，"
               "再看该层 `runs/` 里那份记录的 `verdict`（`run_verdict_gate_red=true` 就是"
               "「跑到了底但闸门判红」）⇒ 红在哪一层就修哪一层。"
               "**只有**「周更这一轮没跑成」（`check_weekly_run_ran`）才会受控自愈补跑，"
               "动作与结果进 `kb/.work/freshness-heal.ndjson`。",
    }


#: 「这一轮没跑」的宽限：排期时刻过了这么久还没跑成，就报。
#  ★ 为什么给到 12 小时而不是 1 小时：`StartCalendarInterval` 到点时机器若在睡觉，
#    launchd 会在**唤醒后补跑**（本机是笔记本）。宽限太短会把「睡过去了、醒来补跑」
#    误报成「没跑」—— 假红挤掉真问题，是本库最忌讳的那种检查器。
#: `layer_freshness.judge()` 的 `kb_root` 口径是 **`<库根>/kb`**（它的水位来源表按 `kb/` 相对写），
#: 不是库根 —— 传库根过去会**静默全 None**（`change_state=None` ⇒ 被判成「没跑」）。实测踩过。
KB_DIR = os.path.join(ROOT, "kb")
WEEKLY_GRACE_H = 12.0
#: 排期时刻**之前**这么久内跑过，也算这一轮已经跑过（有人手动提前跑过 ⇒ 不报假红）。
WEEKLY_COVER_H = 24.0


def check_weekly_run_ran(now=None, path=None, kb_root=None):
    """**这一轮该跑的那趟，跑了没有**（2026-10-16 加；阈值放宽到 8 天之后的兜底）。

    ★ 2026-10-19 收紧（改动单 C）：② 从「任意一层跑过」改为 **L1–L7 每一层都要有
      一次跑成的 RUN**。原先把 L0 单独跑过也算「整轮跑成」—— 10-18 停在 L0 的实测形状
      因此一直绿。`kb_root` 可注入，供自证用临时 KB（不碰真库）。

    为什么必须有它：Owner 2026-10-16 裁定① 把日更改**周更**（每周日 03:30），
    同时把陈旧阈值 24h → 8 天（`layer_freshness.STALE_AFTER`）。**放宽阈值 = 同时放宽了保护**：
    原先「跑挂了 24 小时内就知道」，现在 freshness 要 **8 天**才红。
    而周更**一周只有一次机会**，错过就是**一整周没人知道**。
    ⇒ 这条检查把「错过」在**当天**就说出来，**不等阈值**。

    ★ 三件事同时成立才报红，缺一件都必须是 True／None（不许当红）：
      ① 最近一个排期时刻已过 + 宽限 `WEEKLY_GRACE_H`；
      ② 从该时刻**往前 `WEEKLY_COVER_H` 起**，**L1–L7 每一层**都必须有一次跑成的 RUN；
      ③ 排期读得到（读不到 ⇒ **未测**）。
    ★ 「跑成了」用的是**同一把尺子** `layer_freshness.judge()` 的 `change_state`
      （`produced_changes` / `no_new_input`）—— 本件**不新造第二个陈旧判据**；
      阈值那件事仍归 freshness，这里只问「跑没跑」，不问「够不够新」。

    ★ **非阻断**：报的时候评审链**照常出结论**（数据还没到 8 天）。把它说成「审查链不可用」
      正是本文件反复修的同一个错误（把未测／前瞻说成不可用）。
    """
    now = now or datetime.datetime.now().astimezone()
    due, how = last_due(now, path)
    if due is None:
        return None, {"note": "读不到日更排期（%s：%s）⇒ **未测**" % (path or DAILY_PLIST, how)}

    if now < due + datetime.timedelta(hours=WEEKLY_GRACE_H):
        return True, {"note": "最近一个排期时刻 %s 才过 %.1fh（宽限 %gh）⇒ 还没到该判的时候"
                              % (due.strftime("%m-%d %H:%M"), (now - due).total_seconds() / 3600.0,
                                 WEEKLY_GRACE_H),
                      "last_due": due.isoformat()}

    kb_root = KB_DIR if kb_root is None else kb_root
    per_layer = {}
    for L in ("L0", "L1", "L2", "L3", "L4", "L5", "L6", "L7"):
        try:
            j = _lf_judge(kb_root, L)
        except Exception:                                       # noqa: BLE001
            continue
        ra = j.get("run_at")
        if ra and j.get("change_state") in ("produced_changes", "no_new_input"):
            per_layer[L] = ra
    cover_from = (due - datetime.timedelta(hours=WEEKLY_COVER_H)).timestamp()
    # ★ 2026-10-19：**必跑集 = L1–L7**（数据层；L0 可因令牌/流程跳过，不进必跑集）。
    #   原先只要**任意一层**跑成就算 —— L0 在 10-18 单独跑过，于是「停在 L0」被当成
    #   「整轮跑成」，周更兜底一直绿。缺哪层就点名哪层。
    required = ("L1", "L2", "L3", "L4", "L5", "L6", "L7")
    missing = [L for L in required if L not in per_layer or per_layer[L] < cover_from]
    if not missing:
        newest = max(per_layer[L] for L in required)
        return True, {"note": "这一轮跑过了（L1–L7 最近一次跑成最晚 %s）"
                              % time.strftime("%m-%d %H:%M", time.localtime(newest)),
                      "last_due": due.isoformat(), "newest_success_at": newest}
    newest = max(per_layer.values()) if per_layer else None
    return False, {
        "reason": "**%s 那一轮没跑成** —— 排期时刻已过 %.1f 小时，而自那之前 %gh 起，"
                  "L1–L7 里**有层没有跑成的 RUN**：缺 %s。"
                  % (due.strftime("%m-%d %H:%M"), (now - due).total_seconds() / 3600.0,
                     WEEKLY_COVER_H, "、".join(missing)),
        "last_due": due.isoformat(),
        "newest_success_at": newest,
        "missing_layers": missing,
        "detail": "各层最近一次跑成的时刻："
                  + ("、".join("%s %s" % (k, time.strftime("%m-%d %H:%M", time.localtime(v)))
                               for k, v in sorted(per_layer.items())) or "（一层都没有）"),
        "fix": ("手动跑那一趟： `launchctl kickstart -k gui/%d/%s`"
                "（就是那条周更作业，它自己认领、自己释放；跑完 ~15 分钟）" % (os.getuid(), DAILY_SKILL_LABEL)),
    }


# ────────────────────────────────────────────── 层闸门：工作流的前置还成立吗（**阻断项**）

#: 评审链的层前置，按链上顺序。**只读档**（不加 `--apply`），与链自己跑的是同一条命令。
LAYER_GATES = [("L4", "l7/scripts/l4_gate.py"), ("L5", "l7/scripts/l5_gate.py"),
               ("L6", "l7/scripts/l6_gate.py"), ("L7", "l7/scripts/l7_gate.py")]


def _gate_verdict(rc):
    """一次闸门运行的退出码 → 三态。**只认契约里写死的三个码**，其余一律「未测」。

    契约（见各 `kb/l7/scripts/*_gate.py` 头部）：`0` = 过 ｜ `1` = 红 ｜ `2` = 未测。
    为什么其余码不许归成红或绿：`124`（本巡检查超时自己发的）／`125`（子进程起不来）／
    `137`（被 kill）／`127`（命令不存在）都**不是闸门的判断结果** ——
    说成「红」会让人去修一个不存在的红项，说成「绿」则是把一个没跑起来的东西声明成通过。
    """
    if rc == 0:
        return True
    if rc == 1:
        return False
    return None


def check_layer_gates(_runner=None):
    """评审链的**层前置**（L4→L5→L6→L7 只读闸门）此刻过不过。返回 (ok, detail)。

    ★ 为什么必须有这一条（2026-10-09 实测事故，本巡检建成以来第三次同形状）：

      13:10 一次 L2 重切把 338 条**在册**单元作废（那次运行自己的报告里就写着
      `retired_in_scope_file: 338`），L6 索引随之过期 ⇒ `l6_gate.py` 红 ⇒
      评审链按「遇红即停」停在 L6、库侧拒答（`layer_gate_red`，退出码 4）。
      **而本巡检查了 7 条、一条都不看层闸门** ⇒ 13:10 断的，直到 14:12 有人
      在群里发了一张图才发现（62 分钟里没有任何东西会响）。
      这与 10-04（陈旧认领／凭据）、10-05（装机位符号链接）那两次是**同一个形状**，
      那两次的修法都是「给本巡检加一条判据」—— 这次也一样。

    ★ **阻断项**：层闸门红 ⇒ 评审链**必然**停在那一层并拒答。它不是"文档过期"那类
      非阻断项，混进 ready 会把「此刻能不能出结论」答错。

    ★ 代价与档位：四条闸门都是只读的，L6 那条要复算可用集（实测 ~55s），
      四条合计约 1~2 分钟，每 30 分钟一次 ⇒ 可接受。
      自证／离线档用 `KB_READINESS_GATES_FIXTURE`（如 `L6=1,L4=2`）注入读数，一条命令都不跑。
    """
    fixture = os.environ.get("KB_READINESS_GATES_FIXTURE")
    rows, bad, untested = [], [], []
    for layer, rel in LAYER_GATES:
        if fixture is not None and _runner is None:
            want = {kv.split("=")[0].strip(): kv.split("=")[1].strip()
                    for kv in fixture.split(",") if "=" in kv}
            rc = int(want.get(layer, "0"))
            out = f"[夹具] {layer} 退出码 {rc}"
        elif _runner is not None:
            rc, out = _runner(layer, rel)
        else:
            rc, out, err = run(["sh", KBPY, rel], timeout=600)
            out = (out or "") + (err or "")
        ok = _gate_verdict(rc)
        tail = [l.strip() for l in (out or "").strip().splitlines() if l.strip()]
        rows.append({"layer": layer, "exit": rc, "ok": ok,
                     "tail": (tail[-1][:140] if tail else "")})
        if ok is False:
            bad.append(layer)
        elif ok is None:
            untested.append(layer)

    detail = {"gates": rows}
    if bad:
        # 复开的判据 = 闸门自己那一行；命令逐层给出，可原样复制。
        detail |= {
            "reason": f"层闸门**红**：{'、'.join(bad)} ⇒ 评审链会停在那一层并拒答（`layer_gate_red`）",
            "fix": " cd \"" + ROOT + "\" && " + " ; ".join(
                f"sh kb/kbpy l7/scripts/l{ly[1]}_gate.py" for ly in bad)
                   + "   # 逐条看红项；L6 红时按它的「处置」块走（数据档见 kb/.work/l6_integrity.py）",
        }
        return False, detail
    if untested:
        detail |= {
            "reason": f"层闸门**未测**：{'、'.join(untested)}（退出码不在契约的 0/1/2 里 —— "
                      "多半是超时或被拒，不是「过」）",
            "fix": " 手动跑一次看现场： cd \"" + ROOT + "\" && sh kb/kbpy l7/scripts/"
                   + f"l{untested[0][1]}_gate.py",
        }
        return None, detail
    return True, detail


def check_agents_drift():
    """AGENTS.md 是否已过期（读 `check_agents_md_drift.py` 的结论）。

    ★ 这是**非阻断**项：AGENTS.md 漂移不必然让评审链跑不起来，
      但会让 agent **按错的口径干活** —— 2026-10-05 就因「守衡在外机」那句错话误判过一轮。
      ⇒ 它**要告警**（否则又是「等踩到才发现」），但不改 `ready`，也不改退出码。
    """
    script = os.path.join(ROOT, "kb", "l8", "check_agents_md_drift.py")
    if not os.path.exists(script):
        return False, {"reason": f"找不到 {script}"}
    rc, out, err = run(["python3", script, "--json"], timeout=120)
    try:
        d = json.loads(out or "{}")
    except Exception:                                           # noqa: BLE001
        return False, {"reason": f"漂移自检跑不起来：{(err or out)[:200]}"}
    if d.get("drift", 1) == 0:
        return True, {"claims": d.get("claims"), "drift": 0}
    bad = [r for r in (d.get("rows") or []) if not r.get("ok")]
    return False, {
        "reason": f"AGENTS.md 有 {len(bad)} 条断言与真值不符（agent 会按错的口径干活）",
        "rows": [{"id": r.get("id"), "claim": r.get("claim"),
                  "truth": str(r.get("truth"))[:160], "fix": r.get("fix")} for r in bad],
        "fix": " cd \"" + ROOT + "\" && python3 kb/l8/check_agents_md_drift.py"
               "   # 看逐条真值与修法；改完 AGENTS.md 后重跑确认无漂移",
    }


# ────────────────────────────────────────────── 回归基线漂移（2026-10-12 加；**非阻断**）

def check_regression_drift():
    """回归集基线漂移（读 `kb/l8/regression_gate.py --json` 的结论）。

    ★ 这是**非阻断**项（与 AGENTS.md 漂移同类）：它说的是
      「**改了上游、同一批素材的三态变了**」，**不是**「此刻评审链跑不起来」。
      而且产物是**周期性跑批**（100 条 ≈ 9 分钟）的结果 ——
      几天没跑叫**未测**，不叫坏了。
      ⇒ 红了**只告警**，不改 `ready` / 退出码；未测只记一条说明。

    ★ 为什么值得报（2026-10-12 实测）：这套回归集自 2026-10-10 建起就**没有任何东西在跑它**，
      第一次跑出来就是 **solid 80 条里 13 条与基线不同、从未归因**。
      按库规「散文没有失败信号；判据才有」——闸门建了没接线，等于还是散文。

    ★ 三态（照 `check_layer_gates` 的档位口径）：
      `green` ⇒ True ｜ `red` ⇒ False（告警）｜ `yellow`（基线未建/没跑过/旧读法）⇒ True ＋ 说明。
    """
    script = os.path.join(ROOT, "kb", "l8", "regression_gate.py")
    if not os.path.exists(script):
        return True, {"note": f"找不到 {os.path.relpath(script, ROOT)} ⇒ 未测（不算问题）"}
    # ★ 三态用**退出码**读，不读 JSON 里的判定字段名 —— 两处理由：
    #   ① 自证 ⑯i 禁止本件出现「读那个字段名」的写法（该名字在本库被 L5 落章台账用脏了：
    #      它的值混着三条既有红灯，一读就恒红）；
    #   ② 退出码是**给出的契约**（0=绿 / 4=未测 / 3=红），比耦合 JSON 键名稳。
    rc, out, err = run(["python3", script, "--json", "--strict"], timeout=120)
    try:
        d = json.loads(out or "{}")
    except Exception:                                           # noqa: BLE001
        d = {}
    if not d:
        return True, {"note": f"回归闸门跑不起来（rc={rc}）：{(err or out)[:200]} ⇒ 未测（不算问题）"}
    if rc == 3:
        return False, {
            "reason": ("回归基线漂移：**同一批素材的三态变了**（先核**引擎版本**再判是不是回归 —— "
                       "`review.py` / `tiering.py` 一改，同一素材的结论就可能变）"),
            "drift": d.get("drift"), "missing": d.get("missing"),
            "orphan_non_p3": d.get("orphan_non_p3"),
            "artifact": d.get("artifact"),
            "fix": (" cd \"" + ROOT + "\" && python3 kb/l8/regression_gate.py"
                    "   # 逐条看漂移；**确属预期**的登记 kb/l7/registry/regression-known-drift.yaml"
                    "（登记后降为黄）；确属改进的重采基线："
                    "python3 kb/l8/regression_run.py --out kb/.work/regression-<tag>.jsonl"
                    " && python3 kb/l8/regression_run.py --rebaseline --from kb/.work/regression-<tag>.jsonl"),
            "not_proves": "漂移 ≠ 变坏（可能是修好了，也可能是引擎换版）；本项只说明**变了**。",
        }
    return True, {"rc": rc, "note": "；".join(d.get("reasons") or [])[:200]}


# ────────────────────────────────────────────── AGENTS.md 漂移判据的**自证**（2026-10-12 加；非阻断）

def check_drift_checker_selftest():
    """跑 `check_agents_md_drift.py --selftest`，看**那把尺子自己**还准不准。

    ★ 为什么要读它（2026-10-12 假红体检的直接产物）：那条判据集里**5 条曾把正确改动判成故障**
      （手抄的脚本清单、写死的绝对路径、只认行内列表的正则、要求加粗的文档断言…）。
      体检把它们修好，并给每条配了「**合法变体不许红 ＋ 真坏必须红**」的 20 例自证 ——
      但**没有任何东西在定期跑这 20 例**：判据哪天被改回那种写法，只有真出漂移时才可能被发现。
      ⇒ 让巡检每天替人跑一遍，**红了只告警**（它是「尺子准不准」，不是「此刻能不能跑」）。

    ★ 三态：退出码 0 ⇒ 过 ｜ 3 ⇒ 自证有例不符（告警）｜ 其它 ⇒ **未测**（脚本跑不起来，只记一条）。
    """
    script = os.path.join(ROOT, "kb", "l8", "check_agents_md_drift.py")
    if not os.path.exists(script):
        return True, {"note": f"找不到 {os.path.relpath(script, ROOT)} ⇒ 未测（不算问题）"}
    rc, out, err = run(["python3", script, "--selftest"], timeout=180)
    if rc == 0:
        tail = [l for l in (out or "").strip().split("\n") if l.strip()][-1:]
        return True, {"rc": rc, "note": (tail[0] if tail else "自证通过")[:160]}
    if rc == 3:
        bad = [l.strip() for l in (out or "").split("\n") if l.strip().startswith("❌")]
        return False, {
            "reason": ("**判据自己的自证没过**：那把尺子可能又会把「正确的改动」判成故障 —— "
                       "而它每轮都在推告警，一条假红会挤掉真问题"),
            "failing": bad[:8],
            "raw_tail": (out or err or "")[-300:],
            "fix": (" cd \"" + ROOT + "\" && python3 kb/l8/check_agents_md_drift.py --selftest"
                    "   # 逐例看：**合法变体不许红 + 真坏必须红** 两个方向都要对"),
            "not_proves": "自证没过 ≠ 一定误报；它说明**这把尺子失去了这个保证**，得有人看一眼。",
        }
    return True, {"rc": rc, "note": f"自证跑不起来（rc={rc}）：{(err or out)[:160]} ⇒ 未测（不算问题）"}


# ────────────────────────────────────────────── 日更收尾之后的供给链写入（2026-10-13 加；**非阻断**）

def _post_daily_verdict(writes, stale_layers):
    """纯函数：`(写入清单, 本轮陈旧层)` ⇒ `(ok, detail)`。**喂样本就能判，不碰盘**（自证靠它）。

    ★ 判定要**两件同时成立**才告警：
      ① 日更收尾之后有**真写档**（归因来自 `kb/l8/post_daily_writes.py`，本件不重算）；
      ② **同一轮 freshness 里确实有落后层**（`_stale_layers` 取的那个层集合）。
      只有① ⇒ 只记读数、**不吵** —— 有人白天写库但下游没落后，那不是事。
    """
    if not writes:
        return True, {"note": "日更收尾之后没有真写档"}
    layers = sorted({str(w.get("layer") or "?") for w in writes})
    if not stale_layers:
        return True, {"note": ("日更收尾之后有 %d 笔真写档（层：%s），但**本轮没有落后层** ⇒ 不告警"
                               % (len(writes), "、".join(layers))), "writes": writes[:5]}
    return False, {
        "reason": ("日更收尾之后有人写了供给链 ⇒ **下游已经落后**（这就是「超期」的来路，"
                   "**不是**「超过 24 小时」）："
                   + "；".join("%s：RUN=%s @ %s（%s）" % (w.get("layer") or "?", w.get("run_id") or "?",
                                                        w.get("at") or "?", w.get("via") or "?")
                              for w in writes[:3])),
        "writes": writes[:5],
        "stale_layers": list(stale_layers),
        "cost": ("代价：`freshness.py` 退出码 3 ⇒ 评审链 **fail-closed 拒答** ⇒ 卡上是 `NEEDS_INPUT`；"
                 "而库对这一状态只有一味药 —— **重跑日更**（约 28 分钟，期间送审全量拒答）。"),
        "fix": ("两条路：① **写完立刻补一轮收尾**（重跑受影响层／整轮日更）；"
                "② 下次把这类写**排到日更之后**跑 —— 白天的供给链写入本身就是这条告警的来路。"),
        "not_proves": "本件只做**归因**（谁在日更之后写了库）；陈旧与否由 `daily_health`/`freshness` 判，"
                      "本件**不新造第二把尺子**。",
    }


def check_post_daily_writes(stale_layers=None):
    """日更收尾之后，还有谁往供给链写了（读 `kb/l8/post_daily_writes.py --json`）。

    ★ 为什么有它（2026-10-13 事故；Owner 同意「推荐 ①+③」）：
      那天 03:30 的日更**跑得好好的**（八层退 0、03:57 的日报无 `stale.*`），
      **15:29:48** 又有人跑了一次 L4 发号写（`kb/kbpy .work/l4_article.py 20261013-prd --apply`），
      而 L5 还是 03:41 那份 ⇒ `daily_health` 判 `stale.L5` ⇒ 评审链 fail-closed 拒答。
      **那一刻看告警的人只知道「L5 陈旧」，不知道是谁写新的、该找谁、要不要等。**
      ⇒ 这条读数把那句话补上：**点名 culprit（层／RUN／时刻／命令）**。

    ★ **非阻断**：它说的是「**再往后会出问题**」（白天的写会让下游落后 ⇒ 送审被拒），
      不是「此刻跑不起来」—— 混进 `ready` 会把就绪谓词答错。
      真正阻断的那一格是**新鲜度**（同一轮里它照旧红、照旧触发自愈）。

    ★ 三态：无写入 ⇒ True ｜ 有写入 ＋ 本轮有落后层 ⇒ **False（告警）** ｜ 读数采不到 ⇒ True ＋ 未测说明。
    """
    script = os.path.join(ROOT, "kb", "l8", "post_daily_writes.py")
    if not os.path.exists(script):
        return True, {"note": f"找不到 {os.path.relpath(script, ROOT)} ⇒ 未测（不算问题）"}
    rc, out, err = run(["python3", script, "--json"], timeout=60)
    if rc == 4:
        _tail = [l for l in (out or err or "").strip().split("\n") if l.strip()][-1:]
        return True, {"note": "**未测**（不判绿）：" + (_tail[0] if _tail else "")[:160]}
    try:
        d = json.loads(out or "{}")
    except Exception:                                           # noqa: BLE001
        return True, {"note": f"读数跑不起来（rc={rc}）：{(err or out)[:160]} ⇒ 未测（不算问题）"}
    return _post_daily_verdict(d.get("writes") or [], stale_layers)


# ───────────────────────────────── 报告链接的可见范围（2026-10-16 加；**非阻断**）

# 抽样条数（可注入，供自证/手工诊断；launchd 不设它 ⇒ 默认 8）
REPORT_PERM_SAMPLE = int(os.environ.get("KB_REPORT_PERM_SAMPLE") or 8)


def _perm_verdict(rc, out, err=""):
    """子脚本回包 → `(ok, detail)`。**三态必须分得开**（与 ⑳/㉓ 同一套写法）。

    ★ 为什么这一格非有不可（Owner 2026-10-16 原话两句）：
      「所有上审查报告，有飞书云文档阅读权限的，都必须可以打开」＋
      「第16行的图片，点击『审查报告』提示 Access Denied X-TT-System-Error: 3 Oncall ID: 783」。
      实测根因：报告文档建完**从不设权限** ⇒ `link_share_entity=closed`（当时全量 76/76），
      于是群里那张卡、表里那一格给出的链接，**业务侧点开就是 Access Denied**。
      当天补过 319 份、代码也补了（`review_publish.ensureTenantReadable`：建完立刻 patch →
      回读确认 → 回读不过就不给链接）；**但"补过一次"不等于"以后不会再出现"** ——
      同一天就复发了 43 份（跑批进程是 `import` 进自己进程跑评审的，**代码改了没重启它**）。

    ★ **非阻断**：它不拦评审链（业务侧照样能送审、能出结论），
      但它说的是**已经发给业务的链接打不开** —— 所以照报，且按阻断级冷却那一档进告警正文。

    ★ 三态：全 `tenant_readable` ⇒ True ｜ 有 `closed`/非目标口径 ⇒ **False（点名 token 与来路）**
      ｜ 读数跑不起来 / 一份都没抽到 / `permission_public` 读不到 ⇒ **None（未测）**。
      「量不到」不许说成「没问题」，也不许说成「坏了」—— 本库两边都栽过。
    """
    try:
        d = json.loads(out or "{}")
    except Exception:                                            # noqa: BLE001
        return None, {"note": f"**未测**（读数跑不起来 rc={rc}）：{(err or out or '')[:160]}"}
    ok = d.get("ok")
    n = d.get("n")
    if ok is False:
        bad = d.get("bad") or []
        who = "、".join(f"{b.get('tok')}（{b.get('src') or '?'}）" for b in bad[:5])
        return False, {"reason": f"{d.get('note') or '有报告打不开'}（抽 {n} 份）",
                       "who": who or "（未给 token）",
                       "fix": "python3 kb/l8/report_link_permissions.py --apply"}
    if ok is None:
        return None, {"note": d.get("note") or "**未测**：可见范围读不到"}
    return True, {"note": d.get("note") or f"抽样 {n} 份都是 {d.get('want')}"}


def check_report_link_permissions():
    """抽样回读报告云文档的可见范围（读 `kb/l8/report_link_permissions.py --json`）。"""
    script = os.path.join(ROOT, "kb", "l8", "report_link_permissions.py")
    if not os.path.exists(script):
        return None, {"note": f"找不到 {os.path.relpath(script, ROOT)} ⇒ 未测（不算问题）"}
    rc, out, err = run(["python3", script, "--json", "--sample", str(REPORT_PERM_SAMPLE)],
                       timeout=180)
    return _perm_verdict(rc, out, err)


# ────────────────────────────────────────────── L1 索引：重建有没有被执行（非阻断）

L1_INDEX_STALE_H = float(os.environ.get("KB_L1_INDEX_STALE_H") or 8 * 24)  # 8 天：一个周更周期 + 1 天（2026-10-19 对齐周更；原 25h 按日更写）
L1_INDEX = os.path.join(ROOT, "kb", "l1", "index", "l1.jsonl")
# ★ 2026-10-10 加：L5 落章存在性（可注入，供自证用临时目录，**不碰真库**）。
#   路径可注入：`KB_L5_STAMP_DIR` / `KB_L5_RUN_RECORDS` —— 只为**离线复现与自证**，
#   默认值一个字不改（launchd 不会设这两个变量）。
L5_STAMP_DIR = os.environ.get("KB_L5_STAMP_DIR") or os.path.join(ROOT, "kb", "l5", "runs")
L5_RUN_RECORDS = os.environ.get("KB_L5_RUN_RECORDS") or os.path.join(ROOT, "kb", "l7", "runs")
L5_STAMP_GRACE_MIN = float(os.environ.get("KB_L5_STAMP_GRACE_MIN") or 30)


def _l1_index_verdict(mtime, now, threshold_h=None):
    """纯函数：索引 mtime + 现在 ⇒ `(ok, age_h)`。**喂样本就能判，不碰盘**（自证靠它）。

    `mtime is None` ⇒ `(None, None)` = **未测**，既不是「刚重建」也不是「没重建」。
    """
    th = L1_INDEX_STALE_H if threshold_h is None else threshold_h
    if mtime is None:
        return None, None
    age_h = (now - mtime) / 3600.0
    return (age_h <= th), age_h


def check_l1_index_rebuilt(now=None):
    """`kb/l1/index/l1.jsonl` 有没有被**重建**过（阈值 8 天 = 一个周更周期 + 1 天）。

    ★ 为什么要它（2026-10-08）：这本索引是**全量重建**产物（`layers.yaml` L1 的 `write_mode`
      原话：「manifest_l1.jsonl append-only；资源 json 就地覆盖；**index/l1.jsonl 全量重建**」），
      但它在编排器里**只被登记成只读闸门**（`kb_pipeline.py:91` 的 `GATE_WHITELIST` 是 `["--check"]`）
      ⇒ launchd 与全库**没有任何自动流程**调 `--write` ⇒ **源一变它就漂**，
      `--check` 天天红、没人修。实测（2026-10-08）：mtime 停在 10-02 12:51 而源已到 15:33；
      多余 3 段僵尸；重建 14707 → 15114。
      ⇒ 治法是把重建**接进周更驱动**（`kb/l8/daily_via_skill.sh`；2026-10-19 起由驱动在 agent 结束后**确定性执行**，不再依赖 agent 记得）。
      **本条就是那条接线的防线**：驱动那一步失败 / 被跳过时，
      这条巡检是「漏做了会有人知道」的那一环。

    ★ 阈值为什么是 8 天而不是 25h（2026-10-19 改）：排期 2026-10-16 已由日更改**周更**
      （每周日 03:30），`layer_freshness.STALE_AFTER` 同步 24h → 8 天。重建在周更收尾做，
      一周一次 ⇒ 阈值必须是「一个周更周期 + 1 天余量」。原先 25h 是按日更写的，
      周更后会**天天误报**（即使重建成功）。
      ⇒ 所以本判据**只看 mtime、不跑 `--check`** —— 跑内容检查会整天误报；
         `--check` 的内容结论以 `rebuild_l1_index.py --check` 自身为准。

    ★ **非阻断**：`kb/l6/` 里引用 `l1/index` 的处数 = **0**（实测）⇒ 它**不在检索路径上**，
      是审计投影。它坏不坏不影响此刻能不能评审，只影响「拿索引当分母的对账数字」。
      ⇒ 只进告警，不改 `ready`、不改退出码。
    """
    now = time.time() if now is None else now
    if not os.path.exists(L1_INDEX):
        return None, {"reason": f"找不到 {L1_INDEX} —— **未测**（不是「没重建」）"}
    mtime = os.path.getmtime(L1_INDEX)
    ok, age_h = _l1_index_verdict(mtime, now)
    stamp = time.strftime("%Y-%m-%d %H:%M", time.localtime(mtime))
    if ok:
        return True, {"age_h": round(age_h, 2), "threshold_h": L1_INDEX_STALE_H, "mtime": stamp}
    _age_txt = ("%.1f 天" % (age_h / 24.0)) if age_h >= 48 else ("%.1f 小时" % age_h)
    _th_txt = ("%g 天" % (L1_INDEX_STALE_H / 24.0)) if L1_INDEX_STALE_H >= 48 else ("%gh" % L1_INDEX_STALE_H)
    return False, {
        "reason": f"L1 索引已有 **{_age_txt}**没重建（阈值 {_th_txt}）"
                  "—— 周更任务书步骤 ③c 没有被执行（或驱动那一步没跑成）",
        "before": stamp,
        "detail": "它是**审计投影**（实测 `kb/l6/` 引用 `l1/index` 0 处，**不在检索路径上**），"
                  "**不影响此刻能不能评审**；若源变过而索引没跟上，`--check` 会红"
                  "（本判据只看 mtime，不代替内容检查）；拿它当分母的对账数字会偏。",
        "fix": " ① 立刻补一次："
               "`python3 kb/l1/index/rebuild_l1_index.py --write --run manual-$(date +%Y%m%d-%H%M)`"
               "\n        ② 立刻确认：`python3 kb/l1/index/rebuild_l1_index.py --check` —— **必须 `[OK]`**"
               "\n        ③ 若连着**两轮周更**都是这条 ⇒ 驱动里的 `L1_INDEX` 那一步没跑成："
               "先查 `kb/l8/daily_via_skill.sh` 的日志 `L1_INDEX=` 行；驱动已确定性执行，"
               "别再依赖 agent 记得。",
    }


# ──────────────────────────── 受控自愈（**周更这一轮没跑成** ⇒ 踢一次补跑）

def _pid_alive(pid):
    """pid 还在不在。判据与 `kb_pipeline.lock_state()` 同款（那里是锁口径的真源）。"""
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:                        # 活着但不属于我
        return True
    except OSError:
        return False


def kb_lock_alive():
    """`kb/.work/.kb.lock` 的持有者进程是否还活着（活锁 ⇒ 有人在写库 ⇒ 不抢）。"""
    path = os.path.join(ROOT, "kb", ".work", ".kb.lock")
    if not os.path.exists(path):
        return False, "无锁"
    try:
        rec = json.load(open(path, encoding="utf-8"))
    except Exception:                               # noqa: BLE001
        return True, "锁文件读不出（当活锁处理，宁可不抢）"
    if _pid_alive(rec.get("pid")):
        return True, f"持有者 pid={rec.get('pid')} 还活着"
    return False, f"锁在但 pid={rec.get('pid')} 已不在（陈旧锁，交给 kb_pipeline 自己判）"


def job_running(label):
    """launchd 里这个作业此刻有没有在跑（有 PID 就是在跑）。"""
    rc, out, err = run(["launchctl", "list"], timeout=30)
    for ln in (out or "").splitlines():
        parts = ln.split()
        if len(parts) >= 3 and parts[2] == label:
            return parts[0].isdigit(), parts[0]
    return None, "没有这个作业（launchd 里查不到）"


def heal_decision(*, freshness_stale, claim_free, job_running_pid, lock_alive,
                  last_heal_ts=0.0, attempts_today=0, now_ts=None,
                  kick_sig=(), last_kick_sig=(), weekly_missed=False, ):
    """**纯函数**：这一次要不要踢日更（自证里正反两面逐条喂样本）。

    六道前置缺一不可 —— 每一道拦的都是一种真实碰撞：
      · 新鲜度没问题 **且** 这一轮跑成了 ⇒ 根本不该有动作；
      · 认领槽被占 ⇒ 有会话在跑这条循环，**不许抢**（库规）；
      · 日更已在跑 ⇒ 不重复踢；
      · `kb/.work/.kb.lock` 持有者活着 ⇒ 有人在写库，不抢；
      · 当日次数上限 ⇒ 防抖动（自愈不是重试风暴）；
      · ★ **同一轮陈旧已经踢过 ⇒ 不再踢**（2026-10-10 加，Owner 定）。
        为什么非有这一道：**周更是一周一次的作业**（摘要推送自己就做了「今天已推过，不再推」的门），
        而同一轮陈旧里**踢第二次不可能改变结果** —— 实测 2026-10-10：04:25/05:26/06:27 连踢
        三次、陈旧一次没解，最后是那轮日更**自己跑完**（10:55）才转绿的。
        代价：真换了层的陈旧会**立刻**放行（签名变了 ⇒ 允许再踢），所以这一道只压"原地重踢"。
      · 冷却 ⇒ 距上次动作太近时不重复。
    冷却**放最后**：它是"时间还不够"，与"这一轮已经踢过"是两件事，报出来的话不一样。

    ★★ 2026-10-19（Owner：「我需要的是你解决问题」）—— **周更这一轮没跑成**也进自愈。
      原先唯一触发条件是「新鲜度红」，而新鲜度阈值是 **8 天** ⇒ 周更失败后最长约 **2 天**没人兜；
      实测 10-19：10:00:11 推了「周更：这一轮没跑成」，10:03:57 才**有人**手敲
      `launchctl kickstart` 补跑（自愈台账 `kb/.work/freshness-heal.ndjson` 最后一条停在
      2026-10-13 —— **那天没有自愈**）。⇒ 加 `weekly_missed` 这个触发因，**五道前置一道不减**；
      「同一轮」签名由主循环给（`weekly-missed@<排期时刻>`）⇒ 同一轮只踢一次，不会重试风暴。
    """
    now_ts = time.time() if now_ts is None else now_ts
    # ★★ 2026-10-20（Owner 定 ①，实测依据见下）：**陈旧不再单独触发整链重跑**。
    #   只认「周更这一轮没跑成」——那一轮是排期漏跑，补跑能真正补上；
    #   而「层陈旧」在周更模式下**踢整链补不回来**：
    #     · 陈旧阈值 8 天 > 周更周期 7 天 ⇒ 一旦判陈旧，下一次排期必在 7 天以内；
    #     · 实测 2026-10-20：12:16 因「陈旧（L7）」踢了整链，13:45 那条链**停在 L6**
    #       （`integrity` 崩 + `scope` 基线落伍），白跑 12–24 分钟、占掉认领，
    #       还把 L6/L7 的运行时间戳刷新成「像跑过了」。
    #   ⇒ 陈旧的正确处置是**告警 + 人看红在哪一层**，不是抢在排期前重跑一遍整链。
    if not weekly_missed:
        if freshness_stale:
            return False, ("陈旧只告警、**不踢整链**（周更模式）：周更周期 7 天 < 陈旧阈值 8 天 "
                           "⇒ 陈旧出现时下一次排期必在 7 天内；此时重跑整链会在排期前抢跑，"
                           "而且它解决不了「某一层红」（2026-10-20 实测那轮停在 L6）。"
                           "要看红在哪一层：`sh kb/kbpy l7/scripts/freshness.py` ＋ 该层 run 记录")
        return False, "新鲜度没问题、这一轮也跑成了 ⇒ 不自愈"
    if not claim_free:
        return False, "认领槽被占（有会话在跑这条循环）⇒ 不抢"
    if job_running_pid is True:
        return False, "日更作业已在跑 ⇒ 不重复踢"
    if job_running_pid is None:
        return False, f"launchd 里查不到日更作业 ⇒ 不自愈（要人看一眼）"
    if lock_alive:
        return False, "kb/.work/.kb.lock 的持有者进程还活着（有人在写库）⇒ 不抢"
    if attempts_today >= HEAL_MAX_PER_DAY:
        return False, f"今天已自愈 {attempts_today} 次（上限 {HEAL_MAX_PER_DAY}）⇒ 停手交人"
    # ★ 按**集合**比较，不是按元组：签名是「哪些层陈旧」，与报告顺序无关
    #   （首版写成 `tuple(a) == tuple(b)` ⇒ 顺序不同就判成"换了一轮"，⑰c 精确抓到）。
    if kick_sig and set(kick_sig) == set(last_kick_sig):
        return False, (f"这一轮（{'、'.join(kick_sig)}）**已经踢过一次** ⇒ 不再重踢"
                       f"（同一轮里踢第二次不会换结果）⇒ 等它跑完；"
                       f"若踢过仍没解决，人看 `~/Library/Logs/kb-pipeline-skill/out.log`")
    if last_heal_ts and (now_ts - last_heal_ts) < HEAL_COOLDOWN_MIN * 60:
        mins = (now_ts - last_heal_ts) / 60.0
        return False, f"距上次自愈 {mins:.0f} 分钟（< {HEAL_COOLDOWN_MIN:.0f}）⇒ 等它跑完"
    if weekly_missed:
        _cause = (("陈旧（%s）＋" % ("、".join(kick_sig) if kick_sig else "层集合未解析"))
                  if freshness_stale else "")
        return True, ("%s**周更这一轮没跑成** ＋ 认领空闲 ＋ 作业未在跑 ＋ 无活锁 "
                      "⇒ **踢一次补跑**（一周才一次机会，不能等到下周）" % _cause)
    # ★ 2026-10-20：这一行**不可达**（`not weekly_missed` 已在函数开头早退）。
    #   留着按 **fail-closed** 写：万一有人把上面那条早退删掉，这里也**不许**静默变成「允许踢」。
    return False, "未命中任何自愈触发因（陈旧不再触发整链重跑）⇒ 只告警，不踢"


def heal_causes(fresh_ok, wk_ok):
    """**纯函数**：这一轮的自愈触发因（主循环与自证**共用同一份逻辑**）。

    ★ 2026-10-19：把触发条件从 `main()` 里**抽出来**。为什么非抽不可 —— 原先这段是内联的，
      自证只能 grep 源码；而 grep 的那串字面量**就写在自证自己的正文里** ⇒ 判据自满。
      实测：把 `main()` 的触发退回「只认新鲜度」，⑰q **照样绿**（那是我第一版，当场抓到）。
      ⇒ 现在主循环真调这个函数，自证喂的也是它，改坏任一处都会精确变红。
    ★★ 2026-10-20（Owner 定 ①）：**触发因只剩 `weekly_missed`**。
      `freshness_stale` 仍如实返回（告警正文要用它），但它**不再是触发因** ——
      陈旧只告警、不踢整链。理由写死在 `heal_decision()` 开头那段（含 10-20 实测）。
      判据形状没变：这条仍是一个纯函数，主循环与自证喂**同一份**逻辑（⑰q 钉着）。
    """
    return {"freshness_stale": fresh_ok is False,
            "weekly_missed": wk_ok is False,
            #: 陈旧但周更没漏 ⇒ **只告警**（不是触发；显式给个名字，免得下一个人再猜）
            "stale_only": (fresh_ok is False) and (wk_ok is not False),
            "triggered": (wk_ok is False)}


def heal_sig(fresh_ok, fs_detail, wk_ok, wk_detail):
    """**纯函数**：「这一轮」的自愈签名 —— 同一轮只踢一次就靠它。

    · 陈旧因 ⇒ 陈旧的层集合（`_stale_layers`，只取层号，不含会变的字节数）；
    · 周更因 ⇒ `weekly-missed@<排期时刻>`：**同一槽只算一轮**，下一个周末自动换了签名。
    两者同时命中 ⇒ 两个签名都在（任一变化都算新的一轮）。
    """
    sig = tuple(_stale_layers(fs_detail)) if fresh_ok is False else ()
    if wk_ok is False:
        _due = (wk_detail or {}).get("last_due") if isinstance(wk_detail, dict) else None
        sig = tuple(sig) + ("weekly-missed@%s" % (_due or "?"),)
    return sig


def _stale_layers(detail):
    """从新鲜度读数里取**陈旧的层集合** —— 自愈的「同一轮」签名就用它。

    ★ 为什么不用 `stale_items` 原文：那串里带**字节数**（`l6/registry/l6.json:945:26178`），
      上游文件每写一次它就变 ⇒ 会被误判成"新的一轮"（2026-10-10 那条 L7 假红正是字节差 26178≠26180）。
      层集合是稳定的：同一轮陈旧里它不变，层换了才变。
    """
    if not isinstance(detail, dict):
        return ()
    layers = set()
    for it in detail.get("stale_items") or []:
        m = re.search(r"\*\*(L[0-7])\b", str(it)) or re.search(r"\b(L[0-7])\b", str(it))
        if m:
            layers.add(m.group(1))
    return tuple(sorted(layers))


def _heal_sig_state(now=None):
    """读「上一轮踢过的陈旧签名 + 那是什么时候」——`_heal_state` 的补充读侧（同一次读盘）。"""
    try:
        d = json.load(open(HEAL_STATE, encoding="utf-8"))
    except Exception:                               # noqa: BLE001
        return (), 0.0
    sig = d.get("kicked_sig")
    return (tuple(sig) if isinstance(sig, list) else ()), float(d.get("kicked_sig_at") or 0)


def _heal_state(now=None):
    """读自愈台账（`.review-readiness-heal.json`）：返回 (上次 ts, 当日次数)。"""
    try:
        d = json.load(open(HEAL_STATE, encoding="utf-8"))
    except Exception:                               # noqa: BLE001
        return 0.0, 0
    today = time.strftime("%Y-%m-%d", time.localtime(now or time.time()))
    n = int(d.get("attempts") or 0) if d.get("day") == today else 0
    return float(d.get("at_ts") or 0), n


def _remember_heal(now=None, sig=None):
    now = now or time.time()
    last, n = _heal_state(now)
    os.makedirs(os.path.dirname(HEAL_STATE), exist_ok=True)
    tmp = HEAL_STATE + ".tmp"
    rec = {"at_ts": now, "at": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(now)),
           "day": time.strftime("%Y-%m-%d", time.localtime(now)),
           "attempts": n + 1}
    # ★ 2026-10-10：连**这一轮踢的是哪个陈旧集合**一起记住 —— 下一次同集合就不再踢（见 heal_decision）。
    if sig:
        rec |= {"kicked_sig": list(sig), "kicked_sig_at": now}
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(rec, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, HEAL_STATE)


def attempt_heal(reason):
    """真踢一次日更；**留痕**（ndjson，一行一次，含前后读数）。返回 detail dict。"""
    uid = os.getuid()
    rec = {"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "why": reason,
           "label": DAILY_SKILL_LABEL}
    rc, out, err = run(["launchctl", "kickstart", "-k",
                        f"gui/{uid}/{DAILY_SKILL_LABEL}"], timeout=60)
    rec["returncode"] = rc
    rec["stdout"] = (out or "").strip()[:300]
    rec["stderr"] = (err or "").strip()[:300]
    rec["ok"] = (rc == 0)
    try:
        os.makedirs(os.path.dirname(HEAL_LEDGER), exist_ok=True)
        with open(HEAL_LEDGER, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except OSError as exc:                          # 台账写不进去也要把动作结果带出去
        rec["ledger_error"] = repr(exc)
    return rec


# ────────────────────────────────────────────── 告警（带冷却去重）

def signature(problems):
    """同一原因只报一次；原因变了立刻再报。"""
    return "|".join(sorted(problems))


def should_alert(sig, cooldown_h=None):
    """同一原因只报一次；原因变了立刻再报。

    ★ 冷却按严重度分档，**两侧的都踩过，所以两段历史都写在这儿**：
      · 2026-10-07：阻断级原是 6h ⇒ 当天 15:35/16:05 两条都 `冷却中（0.5h < 6.0h）`，
        **一个让评审链全量拒答的问题，响两声就沉默了** ⇒ 改成 **1h**（治"沉默"）。
      · 2026-10-10（Owner 定）：1h 的代价是**太吵** —— 当天同一条陈旧推了 **6 次**
        （04:25/05:26/06:27/07:29/08:30/11:03），后 5 条零新信息 ⇒ 改成 **24h（一天最多一条）**，
        与日更摘要自己的「今天已推过，不再推」对齐（两条腿的门原本不一致）。
      · **"不许被永久沉默"一个字没松**：`sig` 变了（层集合变 / 原因变）⇒ **立刻再报**，
        见下面 `if d.get("sig") != sig: return True, "原因变化"`。⑧g2/⑧g3 两条判据钉着这一点。
    """
    cooldown_h = COOLDOWN_H if cooldown_h is None else cooldown_h
    try:
        d = json.load(open(STATE, encoding="utf-8"))
    except Exception:                                           # noqa: BLE001
        return True, "首次"
    if d.get("sig") != sig:
        return True, "原因变化"
    age_h = (time.time() - float(d.get("at_ts") or 0)) / 3600.0
    if age_h >= cooldown_h:
        return True, f"冷却已过 {age_h:.1f}h"
    return False, f"冷却中（{age_h:.1f}h < {cooldown_h}h）"


def remember(sig):
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    tmp = STATE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump({"sig": sig, "at_ts": time.time(),
                   "at": time.strftime("%Y-%m-%dT%H:%M:%S")}, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, STATE)


def alert(text, chat):
    """用**守衡自己的 bot 身份**推飞书。bot 令牌与 user 令牌是两套 ⇒ user 丢了也能报。

    ★ 2026-10-16：**出站前必须摘掉 markdown 星号**。本函数是 KB 侧两条直发腿之一
      （另一条是 `daily_digest.py::send()`）：走 `lark-cli im +messages-send --text`，
      飞书按**纯文本**渲染 ⇒ `**阻断级**` 里的星号**字面**进私聊。
      Owner 2026-10-14 的规矩是「守衡的**所有**输出中不允许包含 `**` 星号」，
      但当天修复落在**守衡进程**的 5 个出口、判据只看守衡台账 `ws_outbound.jsonl`
      —— 这两条腿**不在那 5 个出口里、也不进那份台账**，所以一直是漏的。
      摘法 = `kb/l8/plaintext.py`（与守衡 `plain.mjs` 逐字互校）。

    ★ 自证用闸门：`KB_ALERT_FORCE_SEND=1` 时**不真发**，只回报"本该发什么"（离线验告警正文）。
    """
    text, _n_star = plainify_for_send(text, where="watch_review_readiness.alert")
    _sendable, _why = guard(text, where="watch_review_readiness.alert")
    if not _sendable:
        return False, _why
    if os.environ.get("KB_ALERT_FORCE_SEND") == "1":
        return True, "[自证] 未真发；正文长度 %d（已摘星号）" % len(text or "")
    if not os.path.exists(LARK):
        return False, "找不到 lark-cli"
    env = dict(os.environ, PATH=os.path.expanduser("~/.dsh/bin") + ":" + os.environ.get("PATH", ""))
    try:
        p = subprocess.run([LARK, "im", "+messages-send", "--as", "bot", "--profile", "dsh-kb",
                            "--chat-id", chat, "--text", text],
                           capture_output=True, text=True, timeout=90, env=env, errors="replace")
        ok = (p.returncode == 0)
        return ok, (p.stdout or p.stderr or "").strip()[:300]
    except Exception as exc:                                    # noqa: BLE001
        return False, repr(exc)


def compose(problems=(), untested=(), warnings=(), heal=()):
    """拼告警正文。三段分开、各有各的首行 —— **不许把未测说成不可用**。

    ★ 2026-10-06：首行原先恒为「审查链**当前不可用**」。而 08:19:59 那次唯一的依据是
      **一个探针没输出**；那句话在说出去的时候没有依据（§2.4.3：说出去的话比手上的依据大）。
      同一个函数里还要把「非阻断」项（令牌寿命 / AGENTS.md 漂移）与「被挡」分清 ——
      两者的严重性差一个量级，混进同一句话里，读的人只能全按最坏的那个理解。
    """
    if problems:
        head = "⚠️ 守衡 · 审查链**当前不可用**（就绪巡检自动告警）"
    elif untested:
        head = "⚠️ 守衡 · 审查链**就绪未测** —— 读数没采到，**不代表链坏了**"
    else:
        head = "ℹ️ 守衡 · 就绪巡检（**非阻断**提醒：此刻能跑）"
    L = [head, ""]
    for i, p in enumerate([*problems, *untested, *heal, *warnings], 1):
        L.append(f"{i}. {p['title']}")
        for k in ("reason", "before", "detail"):
            if p.get(k):
                L.append(f"   {k}：{str(p[k])[:400]}")
        if p.get("fix"):
            L.append(f"   ▶ 修法：{p['fix']}")
        L.append("")
    if untested and not problems:
        L.append("★ **这一条不是「链坏了」**：它说的是「这一次没读到」。"
                 "同一次巡检里其余各项若是绿的，链此刻多半能跑 —— "
                 "隔几分钟的下一轮会自己给出答案。"
                 "（**例外**：L5 落章缺失是「读不到层侧证据」，不是抖动 —— "
                 "它会让图片/视频送审按 `layer_audit_red` 拒答，要按它的修法处置。）")
        L.append("")
    # ★ 2026-10-10 修：原先条件是 `not problems and not untested` ——
    #   只要同一次里**有未测项**，非阻断组的说明就被整段吞掉（读了等于没读）。
    #   未测说的是「这一次没读到」，与「这些非阻断项不影响此刻能不能跑」并不冲突。
    if warnings and not problems:
        L.append("★ 上面这些**不影响此刻能不能跑**（非阻断）：它们说的是「再往后会出问题」。")
        L.append("")
    L.append("（本告警由 kb/l8/watch_review_readiness.py 自动发出；同一原因不重复 —— "
             f"**阻断级 {BLOCKING_COOLDOWN_H:g}h ／ 非阻断 {COOLDOWN_H:g}h**："
             "拒答级的问题不许被沉默 6 小时。）")
    return "\n".join(L)


def selftest():
    """判据自证：**三态必须分得开**，且这次事故的形状不许再被判成「红」。

    全部离线（喂样本给纯函数 `_interpret_bot_probe`，一次网络都不发）。
    每一项都能红 —— 红了就是这条判据坏了，不是环境坏了。
    """
    P, F = [], []
    def chk(name, cond, extra=""):
        (P if cond else F).append(name)
        print(f"  {'✅' if cond else '❌'} {name}{('  ' + extra) if extra else ''}")

    OK = json.dumps({"ok": True, "data": {"items": [{"record_id": "rec1"}]}})
    DENIED = json.dumps({"ok": False, "error": {"type": "forbidden", "subtype": "resource_permission",
                                                "message": "you do not have permission"}})
    NOERR = json.dumps({"ok": False})
    SHAPE = json.dumps({"data": {"items": []}})          # 没有 ok 字段
    WARN = "[warn] profile token refreshed\n" + OK       # CLI 常会先打一行噪声

    # ① 读到 ⇒ True
    st, _ = _interpret_bot_probe(0, OK, "")
    chk("① ok:true ⇒ True（读到）", st is True)

    # ② 飞书明确拒绝（带 error）⇒ False，且 detail 里要能读出 type/subtype
    st, d = _interpret_bot_probe(1, DENIED, "")
    chk("② ok:false + error ⇒ False（真拒绝）", st is False, f"detail={d!r}")
    chk("② detail 里带得出 type/subtype（否则修的人不知道修哪儿）",
        "forbidden" in d and "resource_permission" in d)

    # ③ ★ 这次事故的形状：stdout 空 / 非 JSON / 没 ok / ok:false 却没 error
    #    —— 四个**全都必须是 None（未测）**，一个都不许是 False。
    #    第一版把 ③ 读成 False，于是「探针没跑起来」被说成了「审查链当前不可用」。
    for name, (rc, out, err) in {
        "③a stdout 空（08:19:59 的形状）": (1, "", "dial tcp: lookup open.feishu.cn: no such host"),
        "③b stdout 完全不是 JSON": (0, "not json at all", ""),
        "③c 有 JSON 但没有 ok 字段": (0, SHAPE, ""),
        "③d ok:false 但 error 为空": (1, NOERR, ""),
    }.items():
        st, d = _interpret_bot_probe(rc, out, err)
        chk(f"{name} ⇒ None（未测，**不许**判成 red）", st is None, f"detail={str(d)[:60]!r}")

    # ③e 反向对照：未测的 detail 里必须**说得出它是未测**，不许长得像权限被拒
    st, d = _interpret_bot_probe(1, "", "")
    chk("③e 未测的文案里写着「未测」且说明不是「读不到」", "未测" in d and "不是" in d, f"detail={d[:70]!r}")

    # ④ CLI 前面有噪声行时仍要读到（别把「有噪声」当成「读不到」）
    st, _ = _interpret_bot_probe(0, WARN, "")
    chk("④ stdout 前面有警告行 ⇒ 仍判 True", st is True)

    # ⑤ 三态互不相同 —— 否则「分得开」是假的
    trio = {_interpret_bot_probe(0, OK, "")[0], _interpret_bot_probe(1, DENIED, "")[0],
            _interpret_bot_probe(1, "", "")[0]}
    chk("⑤ 三种读数给出三个互不相同的结论", len(trio) == 3, f"got={trio}")

    # ⑥ ★ 告警首行：只有未测时**不许**出现「当前不可用」
    u = [{"title": "凭据：**未测**（读数没采到）"}]
    p = [{"title": "凭据：不满足"}]
    chk("⑥ 只有未测时，告警首行不许写「当前不可用」",
        "当前不可用" not in compose([], u).splitlines()[0])
    chk("⑥ 有红时，告警首行必须写「当前不可用」", "当前不可用" in compose(p, u).splitlines()[0])
    chk("⑥ 未测的告警正文里必须明说「不是链坏了」", "不代表链坏了" in compose([], u))

    # ⑦ 非阻断项（令牌寿命 / AGENTS.md 漂移）单独一段，不许被说成被挡
    w = [{"title": "凭据寿命：撑不到下次日更"}]
    chk("⑦ 只有非阻断项时，首行不许写「当前不可用」也不许写「未测」",
        "当前不可用" not in compose([], [], w).splitlines()[0]
        and "未测" not in compose([], [], w).splitlines()[0])

    # ══ ⑧ **受控自愈的判据**（2026-10-07；五道前置，正例一条 + 反向对照五条）══════════
    #   为什么每道都要单独喂样本：这五条拦的是**五种不同的碰撞**（抢认领 / 重复踢 /
    #   抢正在写库的锁 / 抖动 / 停不下来），任何一条写反了都会变成"该自愈时不自愈"
    #   或"不该动时乱动" —— 后者会在别人跑评审时抢库。
    NOW = 1_800_000_000.0          # 固定时刻，判据里不许出现"现在几点"
    # ★ 2026-10-20（Owner 定 ①）：触发因只剩「周更这一轮没跑成」⇒ 正例喂 `weekly_missed=True`。
    #   `freshness_stale=True` 单独**不再**触发（见 ⑧a2），所以这些前置用例都带 weekly_missed。
    base = dict(freshness_stale=True, weekly_missed=True, claim_free=True, job_running_pid=False,
                lock_alive=False, last_heal_ts=0.0, attempts_today=0, now_ts=NOW)
    go, why = heal_decision(**base)
    chk("⑧ 正例：周更这一轮没跑成＋认领空闲＋日更没在跑＋无活锁 ⇒ 踢一次补跑", go is True, why)

    # ⑧a 既没陈旧、周更也跑成了 ⇒ 不许动（否则"每天踢一次"变成常态）
    g, w2 = heal_decision(**{**base, "freshness_stale": False, "weekly_missed": False})
    chk("⑧a 反向对照：新鲜度没问题、这一轮也跑成了 ⇒ 不自愈", g is False, w2)
    # ⑧a2 ★★ 2026-10-20：**陈旧单独不许触发整链重跑**（今天实测它会把链停在 L6）。
    #   反向对照在 ⑧a3：把 weekly_missed 打开 ⇒ 必须放行 —— 证明 ⑧a2 的拒绝来自
    #   "陈旧不算触发因"，不是"这道闸总拒"。
    _g_a2, _w_a2 = heal_decision(**{**base, "weekly_missed": False})
    chk("⑧a2 ★ 只有陈旧、周更没漏 ⇒ **不踢整链**，理由点明「陈旧只告警」",
        _g_a2 is False and "不踢整链" in _w_a2, _w_a2)
    _g_a3, _w_a3 = heal_decision(**{**base, "weekly_missed": True})
    chk("⑧a3 反向对照：同一条件把「周更没跑成」打开 ⇒ 必须踢（拒绝来自触发因，不是总拒）",
        _g_a3 is True, _w_a3)
    # ⑧b 认领被占 ⇒ 不许抢（库规：同一时间只准一个会话跑这条循环）
    g, w2 = heal_decision(**{**base, "claim_free": False})
    chk("⑧b 反向对照：认领槽被占 ⇒ 不抢", g is False, w2)
    # ⑧c 日更已在跑 ⇒ 不重复踢
    g, w2 = heal_decision(**{**base, "job_running_pid": True})
    chk("⑧c 反向对照：日更已在跑 ⇒ 不重复踢", g is False, w2)
    # ⑧c2 查不到这个作业 ⇒ 也不许自作主张（要人看一眼）
    g, w2 = heal_decision(**{**base, "job_running_pid": None})
    chk("⑧c2 反向对照：launchd 里查不到作业 ⇒ 不自愈", g is False, w2)
    # ⑧d 有人正在写库（活锁）⇒ 不抢
    g, w2 = heal_decision(**{**base, "lock_alive": True})
    chk("⑧d 反向对照：kb.lock 持有者活着 ⇒ 不抢", g is False, w2)
    # ⑧e 抖动：刚踢过 ⇒ 等它跑完；当日次数到顶 ⇒ 停手交人
    g, w2 = heal_decision(**{**base, "last_heal_ts": NOW - 10 * 60})
    chk("⑧e 反向对照：10 分钟前刚踢过 ⇒ 等它跑完（不自愈）", g is False, w2)
    g, w2 = heal_decision(**{**base, "last_heal_ts": NOW - (HEAL_COOLDOWN_MIN + 5) * 60})
    chk("⑧e2 冷却已过 ⇒ 允许再踢一次（不是一次就永久停手）", g is True, w2)
    g, w2 = heal_decision(**{**base, "attempts_today": HEAL_MAX_PER_DAY})
    chk(f"⑧f 反向对照：当日已达上限（{HEAL_MAX_PER_DAY} 次）⇒ 停手交人", g is False, w2)

    # ⑧g 冷却分档（**2026-10-10 政策变更后重写**）：
    #   旧判据是「阻断级必须**短于**非阻断」—— 它治的是"沉默"（2026-10-07：6h 把全量拒答级问题
    #   压成一声不响）。当天实测反面代价：同一条陈旧 **1h 一条、推了 6 次**（04:25→11:03），
    #   后 5 条零新信息 ⇒ Owner 2026-10-10 定「**一天最多一条**」（阻断级＝24h）。
    #   ⇒ 旧的"必须更短"**不再成立**，但"不许被永久沉默"这条**一个字没松**，改由两条钉住：
    #     ① `should_alert` 的「**原因变化** ⇒ 立刻再报」分支必须在（层集合变了/原因变了即刻响）；
    #     ② 冷却值必须是个**有限数**（写成无穷/负数 ⇒ 永久沉默 ⇒ 本条红）。
    _sa = open(__file__, encoding="utf-8").read()
    chk("⑧g 阻断级 =「一天最多一条」（24h）—— 改回 1h 或其它值 ⇒ ⑰j/本条精确变红",
        abs(BLOCKING_COOLDOWN_H - 24.0) < 1e-9, f"BLOCKING_COOLDOWN_H={BLOCKING_COOLDOWN_H}h")
    chk("⑧g2 ★「不许被永久沉默」不放松：`原因变化 ⇒ 立刻再报` 这条分支必须在"
        "（拆掉它 ⇒ 本条红：换了层的陈旧会被 24h 静默）",
        'return True, "原因变化"' in _sa)
    chk("⑧g3 反向对照：冷却值必须有限且为正（把它写成 inf/0/-1 ⇒ 本条红）",
        0 < BLOCKING_COOLDOWN_H < 24 * 365 and 0 < COOLDOWN_H < 24 * 365,
        f"{BLOCKING_COOLDOWN_H}h / {COOLDOWN_H}h")

    # ⑧h **动作层**：它会执行什么、留什么痕 —— 用假 runner 抓 argv，
    #     台账指到临时路径（**不许往真台账里塞自证行**：那是污染，比没测更坏）。
    import tempfile
    global run, HEAL_LEDGER
    captured = {}
    real_run, real_ledger = run, HEAL_LEDGER
    tmpd = tempfile.mkdtemp(prefix="heal-selftest-")
    try:
        def fake_run(argv, timeout=180):
            captured["argv"] = list(argv)
            return 0, "ok", ""
        run = fake_run
        HEAL_LEDGER = os.path.join(tmpd, "heal.ndjson")
        rec = attempt_heal("自证：不许真的踢")
        chk("⑧h 自愈动作 = `launchctl kickstart -k gui/<uid>/com.kb.pipeline-daily-skill`"
            "（不是 kill、也不是临时拼的写库命令）",
            captured.get("argv") == ["launchctl", "kickstart", "-k",
                                     f"gui/{os.getuid()}/{DAILY_SKILL_LABEL}"],
            json.dumps(captured.get("argv"), ensure_ascii=False))
        lines = open(HEAL_LEDGER, encoding="utf-8").read().strip().splitlines() if os.path.exists(HEAL_LEDGER) else []
        one = json.loads(lines[0]) if lines else {}
        chk("⑧i 动作必留痕：台账一行含 why / returncode / ok",
            bool(lines) and one.get("why") == "自证：不许真的踢" and one.get("ok") is True,
            f"行数={len(lines)}")
    finally:
        run, HEAL_LEDGER = real_run, real_ledger
        import shutil
        shutil.rmtree(tmpd, ignore_errors=True)

    # ⑭ L1 索引重建判据（2026-10-08 加；2026-10-19 随周更把阈值改 8 天）：
    #    只认「**超过**一个周更周期」，且「文件不在」必须与「没重建」分得开 ——
    #    两者混了，修的人会去修错的东西。先喂纯函数（离线、不碰盘）：
    T = 1780000000.0                                     # 任取一个固定时刻
    chk("⑭a 1 小时前重建过 ⇒ True", _l1_index_verdict(T - 3600, T)[0] is True)
    chk("⑭b 恰 192h（8 天，等于阈值）⇒ True —— 判据是「**超过**」才红，不是「达到」",
        _l1_index_verdict(T - 192 * 3600, T)[0] is True)
    chk("⑭c 193h（8 天 + 1h，刚过一个周更周期没重建）⇒ False",
        _l1_index_verdict(T - 193 * 3600, T)[0] is False)
    chk("⑭d 反向对照：9 天没重建 ⇒ False", _l1_index_verdict(T - 9 * 24 * 3600, T)[0] is False)
    chk("⑭e mtime 为 None（文件不在）⇒ None（**未测**），不许判成「没重建」",
        _l1_index_verdict(None, T)[0] is None)
    chk("⑭f 阈值可传（自证口不依赖 env）", _l1_index_verdict(T - 30 * 3600, T, threshold_h=40)[0] is True)

    # ⑭g–⑭i 真函数：拿**临时文件**当索引，**不碰真库**（与 ⑧i 同一套做法）。
    #    要证明两件纯函数证不了的事：① 红里带得出修法；② 「文件不在」走的是 None 而不是 False。
    import tempfile
    global L1_INDEX
    _real_idx = L1_INDEX
    try:
        _fd, _tmp_idx = tempfile.mkstemp(suffix=".jsonl")
        os.close(_fd)
        _now = time.time()
        os.utime(_tmp_idx, (_now - 200 * 3600, _now - 200 * 3600))
        L1_INDEX = _tmp_idx
        _ro, _rd = check_l1_index_rebuilt(now=_now)
        chk("⑭g 真函数：200h 前重建过 ⇒ False，且 reason 与 **fix** 都在"
            "（带不出修法的红等于没红）",
            _ro is False and isinstance(_rd, dict) and bool(_rd.get("reason")) and bool(_rd.get("fix")),
            f"ok={_ro}")
        os.utime(_tmp_idx, (_now - 3600, _now - 3600))
        _rn, _dn = check_l1_index_rebuilt(now=_now)
        chk("⑭h 反向对照：同一个真函数、mtime 改成 1h 前 ⇒ True（⑭g 的红确实来自 mtime）",
            _rn is True and isinstance(_dn, dict) and _dn.get("age_h") is not None, f"ok={_rn}")
        os.remove(_tmp_idx)
        L1_INDEX = os.path.join(ROOT, "kb", "l1", "index", "__自证__不存在__.jsonl")
        _rz, _ = check_l1_index_rebuilt(now=_now)
        chk("⑭i 文件不在 ⇒ None（**未测**），**不许**判成 False（否则修的人会去修错的东西）",
            _rz is None, f"ok={_rz}")
    finally:
        L1_INDEX = _real_idx

    # ⑮ 层闸门（2026-10-09 加）：三态必须分得开，且**认不出来的退出码不许当红／当绿**。
    #    这是 2026-10-09 那次事故的形状：闸门红了，而本巡检查了 7 条却一条都不看层闸门。
    chk("⑮a 退出码 0 ⇒ True（过）", _gate_verdict(0) is True)
    chk("⑮b 退出码 1 ⇒ False（红）", _gate_verdict(1) is False)
    chk("⑮c 退出码 2 ⇒ None（**未测**，不是红）", _gate_verdict(2) is None)
    for code in (124, 125, 127, 137, 3):
        chk(f"⑮d 反向对照：退出码 {code} ⇒ 未测（说成红会让人去修不存在的项）",
            _gate_verdict(code) is None, f"got {_gate_verdict(code)}")
    _g_all_ok = check_layer_gates(_runner=lambda ly, rel: (0, f"{ly} 过"))
    chk("⑮e 四层全绿 ⇒ True，且四层读数都在", _g_all_ok[0] is True
        and len(_g_all_ok[1]["gates"]) == 4, f"ok={_g_all_ok[0]}")
    _g_red = check_layer_gates(_runner=lambda ly, rel: (1 if ly == "L6" else 0, "L6 复算 5717 ≠ 5979"))
    chk("⑮f L6 红 ⇒ False，且 reason 点名到层、fix 给出可复制的命令",
        _g_red[0] is False and "L6" in _g_red[1].get("reason", "")
        and "l6_gate.py" in _g_red[1].get("fix", ""), f"ok={_g_red[0]}")
    _g_untested = check_layer_gates(_runner=lambda ly, rel: (2 if ly == "L4" else 0, ""))
    chk("⑮g 某层未测（码 2）⇒ None，**不许**等于 False（两件事的处置不同）",
        _g_untested[0] is None, f"ok={_g_untested[0]}")
    chk("⑮h 反向对照：夹具全 0 ⇒ 不许报红（红必须来自读数，不来自「这条检查总会红」）",
        check_layer_gates(_runner=lambda ly, rel: (0, ""))[0] is True)
    chk("⑮i 阻断性：层闸门挂在 `checks`（阻断项）里，不在非阻断那几段",
        '("层闸门", check_layer_gates())' in open(__file__, encoding="utf-8").read())

    # ⑯ L5 落章存在性（2026-10-10 加）：三态必须分得开，且**落章不在**与**测不了**不许混。
    #    这是 2026-10-10 那次事故的形状：`l5_report.py` 崩了 ⇒ 落章一个字节没写 ⇒
    #    图片/视频送审全挂，而本巡检查了 8 条、一条都不看"落章有没有写出来"。
    #    用**临时目录**当 D 与 R（不碰真库，与 ⑧i / ⑭g 同一套做法）。
    _l5_tmp = tempfile.mkdtemp(prefix="l5stamp-selftest-")
    try:
        _l5_D = os.path.join(_l5_tmp, "runs_stamp"); os.makedirs(_l5_D)
        _l5_R = os.path.join(_l5_tmp, "runs_rec"); os.makedirs(_l5_R)
        _l5_now = 1780000000.0                                   # 固定时刻，不吃当前时间
        _l5_rec = os.path.join(_l5_R, "RUNX-L5.json")
        with open(_l5_rec, "w", encoding="utf-8") as _fh:
            json.dump({"run_id": "RUNX-L5", "at": "2026-05-28T00:00:00"}, _fh)
        os.utime(_l5_rec, (_l5_now - 3600, _l5_now - 3600))       # 1 小时前

        # ⑯a 落章在 ⇒ True（反向对照：证明 ⑯b 的红来自"落章不在"，不是"这条检查总会红"）
        with open(os.path.join(_l5_D, "RUNX-L5-dryrun.json"), "w", encoding="utf-8") as _fh:
            json.dump({"run_id": "RUNX-L5"}, _fh)
        _a = check_l5_stamp(now=_l5_now, stamp_dir=_l5_D, records_dir=_l5_R)
        chk("⑯a 落章在 ⇒ True（且报出的是最近一次的 run_id）",
            _a[0] is True and _a[1].get("newest_run_id") == "RUNX-L5", f"ok={_a[0]}")

        # ⑯b 落章不在 + 过了宽限 ⇒ False，**且 reason / how_to_confirm / fix 三样都得在**
        os.remove(os.path.join(_l5_D, "RUNX-L5-dryrun.json"))
        _b = check_l5_stamp(now=_l5_now, stamp_dir=_l5_D, records_dir=_l5_R)
        chk("⑯b 落章不在（1h 前，过宽限）⇒ False，且 reason＋how_to_confirm＋fix 都在"
            "（带不出复核与修法的红等于没红）",
            _b[0] is False and bool(_b[1].get("reason")) and bool(_b[1].get("how_to_confirm"))
            and bool(_b[1].get("fix")), f"ok={_b[0]}")
        chk("⑯b2 reason 点明后果（`E2 逐层无落章` ⇒ 前置 exit=5），不是一句「没落章」",
            "E2" in _b[1].get("reason", "") and "exit=5" in _b[1].get("reason", ""))
        chk("⑯b3 fix 明确禁止续用已停死的 RUN（否则人会去重跑一个不会好的 RUN）",
            _b[1].get("newest_run_id") in _b[1].get("fix", "")
            and "不要" in _b[1].get("fix", ""))

        # ⑯c 在飞（记账刚写成 5 分钟）⇒ True：宽限内不许误报。
        #     ★ `at` 与 mtime **一起推进** —— 只动 mtime 是本自证第一版写错的地方：
        #       判据优先读记账里的 `at`，mtime 根本不参与 ⇒ 那样测的是空气。
        def _l5_age(minutes):
            _t = _l5_now - minutes * 60
            with open(_l5_rec, "w", encoding="utf-8") as _fh:
                json.dump({"run_id": "RUNX-L5",
                           "at": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(_t))}, _fh)
            os.utime(_l5_rec, (_t, _t))

        _l5_age(5)
        _c = check_l5_stamp(now=_l5_now, stamp_dir=_l5_D, records_dir=_l5_R)
        chk("⑯c 反向对照：记账写成仅 5 分钟（宽限 30 分钟内）⇒ True，不许误报在飞的运行",
            _c[0] is True and "宽限" in (_c[1].get("note") or ""), f"ok={_c[0]}")
        # …而 35 分钟（刚过宽限）⇒ False：证明 ⑯c 的绿确实来自宽限，不是"这条检查不看时间"
        _l5_age(35)
        _c2 = check_l5_stamp(now=_l5_now, stamp_dir=_l5_D, records_dir=_l5_R)
        chk("⑯c2 反向对照：同一条记录改成 35 分钟前（刚过宽限）⇒ False"
            "（拆掉宽限判据 ⇒ ⑯c 精确变红；把宽限写成「永不报」⇒ 本条变红）",
            _c2[0] is False, f"ok={_c2[0]}")
        _l5_age(60)

        # ⑯d 一份记账都没有 ⇒ None（**未测**）：不许判成 False，否则人去修不存在的落章
        _l5_R2 = os.path.join(_l5_tmp, "runs_rec_empty"); os.makedirs(_l5_R2)
        _d = check_l5_stamp(now=_l5_now, stamp_dir=_l5_D, records_dir=_l5_R2)
        chk("⑯d 一份 L5 记账都没有 ⇒ None（**未测**），不许判成 False", _d[0] is None, f"ok={_d[0]}")

        # ⑯e 记账目录不存在 ⇒ None（未测），不是红
        _e = check_l5_stamp(now=_l5_now, stamp_dir=_l5_D,
                            records_dir=os.path.join(_l5_tmp, "__不存在__"))
        chk("⑯e 记账目录列不出来 ⇒ None（**未测**），不许判成 False", _e[0] is None, f"ok={_e[0]}")

        # ⑯f 只认**非预演**记账：`*-dryrun.json` 不算记账（层侧落章才是留痕）
        _l5_R3 = os.path.join(_l5_tmp, "runs_rec_dry"); os.makedirs(_l5_R3)
        with open(os.path.join(_l5_R3, "DRY-L5-dryrun.json"), "w", encoding="utf-8") as _fh:
            json.dump({"run_id": "DRY-L5"}, _fh)
        _f = check_l5_stamp(now=_l5_now, stamp_dir=_l5_D, records_dir=_l5_R3)
        chk("⑯f 反向对照：目录里只有 `*-dryrun.json` ⇒ **未测**（记账本来就该是非预演档）",
            _f[0] is None, f"ok={_f[0]}")
    finally:
        import shutil as _sh2
        _sh2.rmtree(_l5_tmp, ignore_errors=True)

    # ⑯g–⑯i 接线与档位：改坏了要精确变红，而不是"看起来还行"。
    _src = open(__file__, encoding="utf-8").read()
    chk("⑯g 接线：L5落章 挂在 `checks` 里（读数进结果），且落进 `l5stamp` 那一组",
        '("L5落章", check_l5_stamp())' in _src and '"l5_stamp_missing"' in _src)
    chk("⑯h 冷却档：L5 落章存在时走**阻断级**冷却（拆掉 `or l5stamp` ⇒ 本条精确变红）",
        "BLOCKING_COOLDOWN_H if (problems or l5stamp) else COOLDOWN_H" in _src)
    chk("⑯i 判据不看 verdict（本件任何地方都不得**读**该字段：它混着三条既有红灯 ⇒ 一读就恒红）",
        not re.search(r'\[[\'"]verdict[\'"]\]|\.get\([\'"]verdict[\'"]', _src))
    chk("⑯j 退出码：L5 落章缺失 ⇒ **未测(2)**，不是被挡(3) —— 文案走快路此刻确实能跑，"
        "说成「链坏了」是夸大（拆掉 `or l5stamp` ⇒ 本条精确变红）",
        "return 2 if (untested or l5stamp) else 0" in _src)
    # ⑯k 真跑 compose 验**首行说了什么** —— 源码字符串证不了行为（⑯k 第一版就栽在这上面）。
    _l5w = {"title": "L5 落章：最近一次运行没有落章", "reason": "x"}
    _hd_ok = compose(untested=[_l5w])                     # L5 走「未测」那一格
    _hd_bad = compose(warnings=[_l5w])                    # 若留在纯 warnings 会是什么首行
    chk("⑯k L5 落章走「未测」⇒ 首行是**未测**语义，不是「此刻能跑」",
        "未测" in _hd_ok.splitlines()[0] and "此刻能跑" not in _hd_ok.splitlines()[0],
        f"首行={_hd_ok.splitlines()[0][:40]}")
    chk("⑯k2 反向对照：同一个告警项放进 warnings ⇒ 首行确实会说「此刻能跑」"
        "（证明 ⑯k 的红来自归类，不是来自这句话本来就不出现）",
        "此刻能跑" in _hd_bad.splitlines()[0], f"首行={_hd_bad.splitlines()[0][:40]}")
    chk("⑯k3 未测与「链坏了」分开说：首行**不含**「当前不可用」",
        "当前不可用" not in _hd_ok.splitlines()[0])
    # ⑯l/⑯m 钉死 2026-10-10 实测踩到的那个形状：L5 落章**同时**进了 problems 与 untested
    #   ⇒ 退出码变 3、告警正文列两遍。（第一版把特判写在通用分支**后面**，就是这个后果。）
    _l5c = [("认领", (True, {})), ("层闸门", (True, {})), ("L5落章", (False, {"reason": "r"}))]
    _g = _alert_groups(_l5c)
    chk("⑯l L5 落章缺失 ⇒ **只**进 untested，**不许**同时进 problems（重复归类会让退出码变 3）",
        [x["title"] for x in _g["problems"]] == []
        and len([x for x in _g["untested"] if x["title"].startswith("L5 落章")]) == 1,
        f"problems={[x['title'] for x in _g['problems']]}")
    chk("⑯m 退出码契约：L5 缺失 ⇒ 2；有真阻断项 ⇒ 3；L5 在宽限内(ok=True)→不报",
        exit_code_for([], [], [{"t": 1}]) == 2
        and exit_code_for([{"t": 1}], [], []) == 3
        and exit_code_for([], [{"t": 1}], []) == 2
        and exit_code_for([], [], []) == 0)
    _gn = _alert_groups([("L5落章", (True, {"note": "该运行写成仅 5 分钟，在 30 分钟宽限内 ⇒ 本次不报"}))])
    chk("⑯m2 宽限内 ⇒ 进 nonblocking（**看得见**，但不算问题、不改退出码）",
        exit_code_for([], [], []) == 0 and len(_gn["nonblocking"]) == 1
        and "宽限" in _gn["nonblocking"][0]["title"])
    chk("⑯k4 有未测项时，非阻断组的说明**不许被吞掉**（原先 `not untested` 会吞掉它）",
        "不影响此刻能不能跑" in compose(untested=[_l5w], warnings=[{"title": "w", "reason": "y"}]))

    # ⑰ 「同一轮陈旧不重踢」＋ 阻断级冷却＝一天一条（2026-10-10，Owner 定）。
    #    形状：当天实测同一条陈旧被踢 3 次、报警 6 次 —— 这两条判据就是压它的。
    #    ★ 2026-10-20（Owner 定 ①）：**陈旧单独已不是触发因**，所以这里的正例必须
    #      带 `weekly_missed=True` 才可能放行 —— 这一组判据量的是「同一轮/冷却」那几道闸，
    #      不是「什么算触发」（那条归 ⑧a2/⑧a3/⑰q 管）。
    _HK = dict(freshness_stale=True, weekly_missed=True, claim_free=True,
               job_running_pid=False, lock_alive=False)
    chk("⑰a 首次（没有历史签名）⇒ 允许踢",
        heal_decision(**_HK, kick_sig=("L1",), last_kick_sig=())[0] is True)
    chk("⑰b ★ 同一轮（层集合一样）⇒ **拒绝重踢**，且理由点明「已经踢过一次」",
        heal_decision(**_HK, kick_sig=("L1",), last_kick_sig=("L1",))[0] is False
        and "已经踢过一次" in heal_decision(**_HK, kick_sig=("L1",), last_kick_sig=("L1",))[1])
    chk("⑰c 顺序不同不算换轮（集合比较，不是字符串比较）",
        heal_decision(**_HK, kick_sig=("L1", "L6"), last_kick_sig=("L6", "L1"))[0] is False)
    chk("⑰d 反向对照：**换了层** ⇒ 立刻放行（证明 ⑰b 的红来自集合相同，不是「这道闸总拒」）",
        heal_decision(**_HK, kick_sig=("L1", "L7"), last_kick_sig=("L1",))[0] is True)
    chk("⑰e 层集合解析不出来（签名空）⇒ 不许把它当「同一轮」永久拒踢",
        heal_decision(**_HK, kick_sig=(), last_kick_sig=("L1",))[0] is True)
    chk("⑰f 当日配额优先于同轮判定：两个都命中时，报的是配额（更有信息量）",
        "上限" in heal_decision(**_HK, kick_sig=("L1",), last_kick_sig=("L1",),
                                attempts_today=HEAL_MAX_PER_DAY)[1])
    # 签名本身：只认层号，不认那些会变的字节数
    _sig = _stale_layers({"stale_items": [
        "· **L7 的 (该层无 data 产物) 落后 0.1 小时前** → 水位差（l6/registry/l6.json:945:26178 ≠ l6/registry/l6.json:945:26180）",
        "· **L1 的 manifest_l1.jsonl 落后 18.7 小时前** → 24h 内跑过"]})
    chk("⑰g 签名只取层号、按字典序、去重（字节数 26178/26180 不参与 ⇒ 上游写一次不会误判成新的一轮）",
        _sig == ("L1", "L7"), f"got {_sig}")
    chk("⑰h 反向对照：**同一批层、只改字节数** ⇒ 签名一模一样",
        _stale_layers({"stale_items": ["· **L7 … （l6/registry/l6.json:945:99999 ≠ …:945:1）"]})
        == _stale_layers({"stale_items": ["· **L7 … （l6/registry/l6.json:945:1 ≠ …:945:2）"]}))
    chk("⑰i 非 dict / 无 stale_items ⇒ 空签名（不许抛错、也不许凭空造签名）",
        _stale_layers(None) == () and _stale_layers({}) == () and _stale_layers("x") == ())
    # 冷却分档：阻断级＝一天一条
    chk("⑰j 阻断级冷却 = 24h（一天最多一条）—— 改回 1h ⇒ 本条精确变红",
        abs(BLOCKING_COOLDOWN_H - 24.0) < 1e-9, f"BLOCKING_COOLDOWN_H={BLOCKING_COOLDOWN_H}")
    chk("⑰k 非阻断冷却仍是 6h（两类不许被一起改掉）", abs(COOLDOWN_H - 6.0) < 1e-9, f"COOLDOWN_H={COOLDOWN_H}")
    _src2 = open(__file__, encoding="utf-8").read()
    # ★★★ ⑰l/⑰q/⑰r（2026-10-19 改写）：**接线判据不许自己满足自己**。
    #   原先 ⑰l 写的是 `"kick_sig=_kick_sig, last_kick_sig=_last_sig" in _src2`，
    #   而那串字面量**就写在这条判据自己的正文里** ⇒ 恒真。⑰q 初版也是同一形状，
    #   实测：把 `main()` 的触发退回「只认新鲜度」，⑰q 照样绿。
    #   ⇒ 改写两件：① 触发与签名抽成纯函数（`heal_causes`/`heal_sig`），自证**功能性地**喂；
    #     ② 源码接线判据只扫 `main()` 的正文（`inspect.getsource`），扫不到自证自己。
    _main_src = inspect.getsource(main)
    chk("⑰l 接线：`main()` 正文里把签名传给 heal_decision，且成功后记住它（拆任一处 ⇒ 本条红）",
        "kick_sig=_kick_sig, last_kick_sig=_last_sig" in _main_src
        and "_remember_heal(sig=_kick_sig)" in _main_src)
    chk("⑰m 正例：**只有**周更没跑成（新鲜度还是绿的）也要踢"
        "（改回「只认新鲜度」⇒ 本条与 ⑰q 精确变红）",
        heal_decision(**{**base, "freshness_stale": False},
                      kick_sig=("weekly-missed@x",))[0] is True)
    chk("⑰n 反向对照：周更没跑成但**认领被占** ⇒ 不抢（五道前置一道不减）",
        heal_decision(**{**base, "freshness_stale": False, "claim_free": False},
                      kick_sig=("weekly-missed@x",))[0] is False)
    _o1 = heal_decision(**{**base, "freshness_stale": False},
                        kick_sig=("weekly-missed@x",), last_kick_sig=("weekly-missed@x",))
    chk("⑰o 同一轮只踢一次：排期时刻相同 ⇒ 拒绝重踢，且理由点明「已经踢过一次」",
        _o1[0] is False and "已经踢过一次" in _o1[1], _o1[1])
    chk("⑰p 反向对照：**换了排期槽**（下一个周末）⇒ 立刻放行"
        "（证明 ⑰o 的红来自「同一轮」，不是这道闸总拒）",
        heal_decision(**{**base, "freshness_stale": False},
                      kick_sig=("weekly-missed@y",), last_kick_sig=("weekly-missed@x",))[0] is True)
    # 10-19 的真实形状逐条喂 **纯函数**：新鲜度绿、周更没跑成 ⇒ 必须 triggered，且只报周更因。
    # ★ 2026-10-20（Owner 定 ①）改写：**触发因只剩周更**。原来 `heal_causes(False, False)`
    #   断言「陈旧也触发」⇒ 现在必须是 False，并由 `stale_only` 如实标出来（告警要用，但不踢）。
    chk("⑰q **功能**接线：触发因由 `heal_causes()` 算 —— 10-19 形状（周更没跑成）⇒ triggered；"
        "10-20 形状（只有陈旧）⇒ **不 triggered 但 `stale_only`**"
        "（改回「陈旧也触发」或「只看新鲜度」⇒ 本条精确变红）",
        heal_causes(True, False) == {"freshness_stale": False, "weekly_missed": True,
                                     "stale_only": False, "triggered": True}
        and heal_causes(True, True)["triggered"] is False
        and heal_causes(False, True)["freshness_stale"] is True
        and heal_causes(False, True)["triggered"] is False
        and heal_causes(False, True)["stale_only"] is True
        and heal_causes(False, False)["triggered"] is True)
    chk("⑰r 签名由 `heal_sig()` 算：周更因带排期时刻，换槽 ⇒ 签名变"
        "（这是「同一轮只踢一次」的凭据）",
        heal_sig(True, None, False, {"last_due": "2026-10-18T03:30:00+08:00"})
        == ("weekly-missed@2026-10-18T03:30:00+08:00",)
        and heal_sig(True, None, False, {"last_due": "2026-10-25T03:30:00+08:00"})
        != heal_sig(True, None, False, {"last_due": "2026-10-18T03:30:00+08:00"})
        and heal_sig(True, None, False, None) == ("weekly-missed@?",)
        and heal_sig(False, {"stale_items": ["· **L7 …"]}, True, None) == ("L7",))
    chk("⑰s 源码接线：`main()` 正文里真的用 `heal_causes()` 的结论当触发、并用 `heal_sig()` 算签名"
        "（把 `if _hc[\"triggered\"]:` 退回 `if fresh_ok is False:` ⇒ 本条精确变红；"
        "扫的是 `main()`，扫不到自证自己）",
        "heal_causes(" in _main_src and "heal_sig(" in _main_src
        and '_hc["triggered"]' in _main_src)

    # ⑱ 回归基线漂移（2026-10-12 加）：**非阻断**项 —— 三态分得开，且判据有反向对照。
    #    为什么它是非阻断：它说的是「改了上游、三态变了」，不是「此刻跑不跑得起来」；
    #    产物是周期性跑批（100 条 ≈ 9 分钟），几天没跑叫**未测**。
    #    ★ 反向对照走**真 CLI + 临时文件**（不是直接读内部字典）：
    #      既验到接线，又避开 ⑯i 禁用的那个字段名。
    try:
        import shutil as _sh2
        _rt = tempfile.mkdtemp(prefix="reggate-selftest-")
        _bp = os.path.join(_rt, "baseline.json")
        _ap = os.path.join(_rt, "artifact.jsonl")
        with open(_bp, "w", encoding="utf-8") as _fh:
            json.dump({"schema": "kb-regression-baseline/1",
                       "cases": {"x": {"state": "BLOCK"}, "y": {"state": "PASS"}}}, _fh)
        _rows = [{"case_id": "x", "layer": "solid", "got": "BLOCK", "got_source": "decision.decision"},
                 {"case_id": "y", "layer": "solid", "got": "PASS", "got_source": "decision.decision"}]

        def _rc_of(rows, baseline=_bp):
            with open(_ap, "w", encoding="utf-8") as _fh:
                for _r in rows:
                    _fh.write(json.dumps(_r, ensure_ascii=False) + "\n")
            _rc, _o, _e = run(["python3", os.path.join(ROOT, "kb", "l8", "regression_gate.py"),
                               "--baseline", baseline, "--artifact", _ap, "--json", "--strict"],
                              timeout=60)
            return _rc
        chk("⑱a 反向对照：篡改一条三态 ⇒ **红（rc=3）**（红必须来自读数，不来自「永远红」）",
            _rc_of(_rows) == 0 and _rc_of([dict(_rows[0]), dict(_rows[1], got="BLOCK")]) == 3,
            f"绿rc={_rc_of(_rows)}")
        _nob = os.path.join(_rt, "nobase.json")
        chk("⑱b 未测（基线不存在）⇒ rc=4，**不许**判红（未测 ≠ 坏了）",
            _rc_of(_rows, baseline=_nob) == 4)
        chk("⑱c 旧读法产物 ⇒ rc=4（不许判绿：旧读法会产出假警报）",
            _rc_of([{**r, "got_source": ""} for r in _rows]) == 4)
        _sh2.rmtree(_rt, ignore_errors=True)
    except Exception as _e2:                                    # noqa: BLE001
        chk("⑱a 反向对照：篡改一条三态 ⇒ **红（rc=3）**（红必须来自读数，不来自「永远红」）",
            False, repr(_e2))
        chk("⑱b 未测（基线不存在）⇒ rc=4，**不许**判红（未测 ≠ 坏了）", False, "见 ⑱a")
        chk("⑱c 旧读法产物 ⇒ rc=4（不许判绿：旧读法会产出假警报）", False, "见 ⑱a")
    _src3 = open(__file__, encoding="utf-8").read()
    # ★ 判据写法要避开自指：断言串本身也在这份源码里 ⇒ 不能直接 `"...X..." not in src`。
    #   改成只看 `checks`（阻断项）那一段里有没有它。
    _checks_block = _src3.split("checks = [", 1)[1].split("]", 1)[0] if "checks = [" in _src3 else ""
    chk("⑱d 非阻断性：回归漂移**不进** `checks`（阻断项），且确实接进了告警组",
        "check_regression_drift" not in _checks_block
        and "reg_ok, reg_detail = check_regression_drift()" in _src3
        and "horizon + drift + reg + l1idx + l5_note" in _src3,
        f"checks 段命中={'check_regression_drift' in _checks_block}")
    chk("⑱e 接线：`regression_drift` 与 `regression` 都进结果（拆任一处 ⇒ 本条红）",
        '"regression_drift": bool(reg)' in _src3 and '"regression": reg,' in _src3)

    # ⑲（2026-10-12 加）：**判据自己的自证**这条读数 —— 接线 + 非阻断 + 真能告警。
    #   为什么单列：它守的是「那把尺子还准不准」（上一批的假红体检全在它的 20 例里），
    #   而**没有任何东西在定期跑那 20 例**之前，等于没接。
    chk("⑲a 接线：`check_drift_checker_selftest` 进了主流程，且**不在** `checks`（阻断项）里",
        "dsc_ok, dsc_detail = check_drift_checker_selftest()" in _src3
        and "check_drift_checker_selftest" not in _checks_block
        and "horizon + drift + reg + l1idx + dsc + l5_note" in _src3,
        f"checks 段命中={'check_drift_checker_selftest' in _checks_block}")
    chk("⑲b 结果里带得出来（`--json` 读得到），拆掉就红",
        '"drift_checker_selftest": {"ok": dsc_ok' in _src3)
    try:
        # 真喂一次：拿真脚本跑（它现在应该是 0）；再用一个**不存在的脚本路径**造「未测」。
        _ok_real, _d_real = check_drift_checker_selftest()
        chk("⑲c 真跑：自证通过 ⇒ 读数 ok 且**不告警**", _ok_real is True, str(_d_real)[:90])
    except Exception as _e3:                                    # noqa: BLE001
        chk("⑲c 真跑：自证通过 ⇒ 读数 ok 且**不告警**", False, repr(_e3))
    try:
        # 反向对照：把脚本路径指到不存在的文件 ⇒ 必须**未测（True）**，而不是判红（缺件 ≠ 坏件）
        _saved = globals().get("ROOT")
        import tempfile as _tf3
        _empty = _tf3.mkdtemp()
        globals()["ROOT"] = _empty
        _ok_missing, _d_missing = check_drift_checker_selftest()
        globals()["ROOT"] = _saved
        chk("⑲d 反向对照：脚本不在 ⇒ **未测（不判红）**（缺件 ≠ 坏件）",
            _ok_missing is True and "未测" in json.dumps(_d_missing, ensure_ascii=False),
            json.dumps(_d_missing, ensure_ascii=False)[:90])
    except Exception as _e4:                                    # noqa: BLE001
        chk("⑲d 反向对照：脚本不在 ⇒ **未测（不判红）**（缺件 ≠ 坏件）", False, repr(_e4))

    # ⑳（2026-10-13 加）：**日更收尾之后的供给链写入**这条读数 —— 接线 ＋ 非阻断 ＋ 判定要看两件。
    #   为什么单列：它守的是「**谁**在日更之后写了库」这个**归因**。指错人比不报更坏
    #   （人会去问错的人、或以为要等，而真正该做的是「谁写的谁补一轮收尾」）
    #   ⇒ 判定必须是**纯函数**、可喂样本；读数本身不许把「有几笔」写死（那会随库变化假红）。
    chk("⑳a 接线：`check_post_daily_writes` 进了主流程，且**不在** `checks`（阻断项）里",
        "pdw_ok, pdw_detail = check_post_daily_writes(" in _src3
        and "check_post_daily_writes" not in _checks_block
        and "l5_note + postdaily" in _src3,
        f"checks 段命中={'check_post_daily_writes' in _checks_block}")
    chk("⑳b 结果里带得出来（`--json` 读得到），拆掉就红",
        '"post_daily_writes": bool(postdaily)' in _src3 and '"post_daily": postdaily,' in _src3)
    _w1 = [{"layer": "L4", "run_id": "20261013-prd", "at": "2026-10-13 15:29:48",
            "via": "命令带 `--apply`"}]
    _ok0, _d0 = _post_daily_verdict([], ("L5",))
    _ok1, _d1 = _post_daily_verdict(_w1, ())
    _ok2, _d2 = _post_daily_verdict(_w1, ("L5",))
    chk("⑳c 反向对照（**两件同时成立才告警**）：无写入 ⇒ 不告警 ｜ 有写入但本轮无落后层 ⇒ 不告警 "
        "｜ 有写入＋有落后层 ⇒ **告警**",
        _ok0 is True and _ok1 is True and _ok2 is False, f"{_ok0}/{_ok1}/{_ok2}")
    _dj = json.dumps(_d2, ensure_ascii=False)
    chk("⑳d 告警里必须**点名 culprit**（层／RUN／时刻）—— 只报「有人写了」等于把排查退回给人",
        "L4" in _dj and "20261013-prd" in _dj and "15:29:48" in _dj)
    try:
        _saved4 = globals().get("ROOT")
        _empty4 = _tf3.mkdtemp()
        globals()["ROOT"] = _empty4
        _okm, _dm = check_post_daily_writes(stale_layers=("L5",))
        globals()["ROOT"] = _saved4
        chk("⑳e 反向对照：脚本不在 ⇒ **未测（不判红）**（缺件 ≠ 坏件）",
            _okm is True and "未测" in json.dumps(_dm, ensure_ascii=False),
            json.dumps(_dm, ensure_ascii=False)[:90])
    except Exception as _e7:                                    # noqa: BLE001
        chk("⑳e 反向对照：脚本不在 ⇒ **未测（不判红）**（缺件 ≠ 坏件）", False, repr(_e7))
    try:
        # 真跑一次真库读数：只断言「跑得起来 ＋ 三态合法」，**不断言有几笔**
        #   （写死了就会随库变化而假红 —— 一条假红挤掉一个真问题）。
        _okr, _dr = check_post_daily_writes(stale_layers=())
        chk("⑳f 真跑：真库上读数跑得起来，三态合法（不写死笔数）",
            _okr in (True, False) and isinstance(_dr, dict), str(_dr)[:90])
    except Exception as _e8:                                    # noqa: BLE001
        chk("⑳f 真跑：真库上读数跑得起来，三态合法（不写死笔数）", False, repr(_e8))

    # ㉑（2026-10-13 加）：告警里的**「修法」命令必须真能跑**。
    #   实测缺陷（当天自己按告警照做时撞上）：三条修法/复核命令都在 `kbpy` 后面
    #   **又写了一遍 `kb/` 前缀**，而 `kbpy` 自己就会补这个前缀
    #   ⇒ 实跑得到「找不到脚本 …/kb/kb/l7/scripts/l7_gate.py」exit 2。
    #   人照着告警做却得到「找不到脚本」，比不给修法更坏（会以为是自己环境不对）。
    #   ★ 自指陷阱（本条自己踩过一次，见下 `_needle`）：断言串**和注释里的同一串**
    #     都会出现在这份源码里 ⇒ 断言必须**运行时拼**，注释也**不许**写全那一段字面量。
    _needle = "kb/kbpy" + " kb/"
    chk("㉑a 修法命令不许带重复前缀（`kbpy` 自己补 `kb/`）—— 源码级",
        _needle not in _src3 and "sh kb/kbpy l7/scripts/l" in _src3,
        f"命中={'是' if _needle in _src3 else '否'}")
    _saved5 = os.environ.get("KB_READINESS_GATES_FIXTURE")
    try:
        os.environ["KB_READINESS_GATES_FIXTURE"] = "L7=1"
        _g_ok, _g_d = check_layer_gates()
        _fix = str((_g_d or {}).get("fix") or "")
        chk("㉑b 反向对照（真造一次红）：夹具 `L7=1` ⇒ 修法里给的是**能跑的那条**",
            _g_ok is False and _needle not in _fix and "sh kb/kbpy l7/scripts/l7_gate.py" in _fix,
            _fix[:130])
    except Exception as _e9:                                    # noqa: BLE001
        chk("㉑b 反向对照（真造一次红）：夹具 `L7=1` ⇒ 修法里给的是**能跑的那条**", False, repr(_e9))
    finally:
        if _saved5 is None:
            os.environ.pop("KB_READINESS_GATES_FIXTURE", None)
        else:
            os.environ["KB_READINESS_GATES_FIXTURE"] = _saved5

    # ㉒ 出站正文的 markdown 星号（2026-10-16 加；Owner 当天报「下面的 `*` 没有去掉」）。
    #    本脚本的告警走 `lark-cli --text`（飞书按**纯文本**渲染）⇒ 星号**字面**进私聊，
    #    而守衡那次修复的 5 个出口与唯一判据（只看 `ws_outbound.jsonl`）**都够不着它**。
    _p1 = {"title": "**L5 落章缺失**", "reason": "没有 `kb/l5/runs/<RUN>-L5.json`",
           "fix": "sh kb/kbpy l7/scripts/l5_gate.py", "detail": "**读不到层侧证据**"}
    _c_txt = compose(problems=[_p1])
    chk("㉒a 告警正文**本来确实带** markdown 星号（否则下面两条是恒真的）",
        has_md_symbols(_c_txt), f"星号 {_c_txt.count('*')} 个")
    chk("㉒b 过收口后**一个星号都没有**（三种首行都要过 —— 阻断／未测／非阻断）",
        all(not has_md_symbols(plainify(compose(**k)))
            for k in ({"problems": [_p1]},
                      {"untested": [{"title": "**未测**：L5 落章", "reason": "读不到"}]},
                      {"warnings": [{"title": "**非阻断**：AGENTS.md 漂移"}]})),
        f"阻断支 星号 {plainify(compose(problems=[_p1])).count('*')} 个")
    chk("㉒c **反向对照**：没过收口的正文会被出站闸门拦下（拆收口 ⇒ 精确变红）",
        guard(_c_txt, where="自证")[0] is False
        and guard(plainify(_c_txt), where="自证")[0] is True)
    chk("㉒d 摘的是标记不是字：修法命令与原因摘完仍读得出来",
        "sh kb/kbpy l7/scripts/l5_gate.py" in plainify(_c_txt)
        and "L5 落章缺失" in plainify(_c_txt))
    # ㉒e **预览不许说谎**：`--alert-preview` 打印的必须是**摘过的**那份（与真发同一个收口）。
    #     源码级断言（同 ㉑a 的做法）：预览那一支若回去 print 原始 compose ⇒ 精确变红。
    #     ⚠️ 两个针**必须拼出来** —— 直接写字面量的话，断言那一行自己就把针带进 `_src4`，
    #        正向恒真、负向恒假（第一版就这么写，㉒e 当场红）。
    _src4 = open(os.path.join(HERE, "watch_review_readiness.py"), encoding="utf-8").read()
    _wrapped = "print(plainify_for_send(" + 'compose(_g["'
    _raw = "print(" + 'compose(_g["problems"]'
    chk("㉒e **预览与真发同一个收口**（预览打原始 compose ⇒ 精确变红）",
        _wrapped in _src4 and _raw not in _src4, "预览支走的是 plainify_for_send")
    # ㉒f ★ **接线**：光证明 `plainify()` 好用不算 —— 要证明 `alert()` 那条路**真调了它**。
    #     做法同守衡侧「真发一次（网络打桩）」：换掉 `subprocess.run`，看它**准备发什么**。
    #     删掉 `alert()` 里那行收口 ⇒ 本条**精确变红**（㉒a–㉒d 都拦不住：它们只测纯函数）。
    _seen2 = {}

    class _Fake2:
        returncode, stdout, stderr = 0, "{}", ""

    _real_run2 = subprocess.run
    _saved_force2 = os.environ.pop("KB_ALERT_FORCE_SEND", None)
    try:
        subprocess.run = lambda argv, **kw: (_seen2.setdefault("argv", argv), _Fake2())[1]
        _ok_alert, _ = alert("⚠️ **阻断级**：审查链**当前不可用**", "oc_自证")
    finally:
        subprocess.run = _real_run2
        if _saved_force2 is not None:
            os.environ["KB_ALERT_FORCE_SEND"] = _saved_force2
    _sent2 = (_seen2.get("argv") or [""])[-1]
    chk("㉒f **接线**：`alert()` 真发的那份正文里一个星号都没有（删掉收口 ⇒ 本条精确变红）",
        _ok_alert and "*" not in _sent2 and "阻断级" in _sent2, "实发：%r" % _sent2[:50])

    # ㉓ 周更（2026-10-16，Owner 裁定①）：排期解析必须认 `Weekday`；
    #    阈值放宽到 8 天之后，「这一轮没跑」要有**快信道**兜底。
    #    ⚠️ 全部喂**临时 plist 与固定时刻**，不碰真库写口、也不看今天是星期几。
    import datetime as _dt
    import tempfile as _tf

    def _mk_plist(hh, mm, weekday=None):
        els = ["<key>Hour</key><integer>%d</integer>" % hh,
               "<key>Minute</key><integer>%d</integer>" % mm]
        if weekday is not None:
            els.insert(0, "<key>Weekday</key><integer>%d</integer>" % weekday)
        xml = ('<?xml version="1.0" encoding="UTF-8"?><plist version="1.0"><dict>'
               '<key>StartCalendarInterval</key><dict>' + "".join(els)
               + '</dict></dict></plist>')
        f = _tf.NamedTemporaryFile("w", suffix=".plist", delete=False, encoding="utf-8")
        f.write(xml)
        f.close()
        return f.name

    _p_week = _mk_plist(3, 30, weekday=0)          # 每周日 03:30（周更）
    _p_daily = _mk_plist(3, 30)                    # 每天 03:30（向后兼容）
    _tz = _dt.timezone(_dt.timedelta(hours=8))
    _fri = _dt.datetime(2026, 10, 16, 9, 0, tzinfo=_tz)          # 周五 09:00
    _spec_w, _ = _read_schedule(_p_week)
    _spec_d, _ = _read_schedule(_p_daily)
    chk("㉓a 排期解析**认 `Weekday`**：周日 03:30 ⇒ weekdays=[0]／周期 7 天",
        _spec_w == {"hour": 3, "minute": 30, "weekdays": [0], "period_days": 7.0},
        f"{_spec_w}")
    chk("㉓b **反向对照**：没有 `Weekday` 的排期仍是「每天」（不许把每天当周更）",
        _spec_d == {"hour": 3, "minute": 30, "weekdays": [], "period_days": 1.0},
        f"{_spec_d}")
    _nxt_w, _ = next_daily_run(_fri, _p_week)
    _nxt_d, _ = next_daily_run(_fri, _p_daily)
    chk("㉓c 周五 09:00 看下次：周更 ⇒ **周日 03:30**（原先只读 Hour/Minute 会错报「周六 03:30」）；"
        "日更 ⇒ 周六 03:30",
        _nxt_w == _dt.datetime(2026, 10, 18, 3, 30, tzinfo=_tz)
        and _nxt_d == _dt.datetime(2026, 10, 17, 3, 30, tzinfo=_tz),
        f"周更={_nxt_w} ｜ 日更={_nxt_d}")
    _due_w, _ = last_due(_fri, _p_week)
    chk("㉓d `last_due()`：周五 09:00 ⇒ 最近一个排期时刻是**上周日 10-11**（不是「今天 03:30」）",
        _due_w == _dt.datetime(2026, 10, 11, 3, 30, tzinfo=_tz), f"{_due_w}")
    # 三态都要真造一遍（不造假样本、也不改真库）
    _n_ok, _n_d = check_weekly_run_ran(_fri, os.path.join(ROOT, "kb", "**不存在**.plist"))
    chk("㉓e 排期读不到 ⇒ **None（未测）**；**不许**判成「没跑」（缺件 ≠ 坏件）",
        _n_ok is None, str(_n_d)[:90])
    _w_ok, _w_d = check_weekly_run_ran(_dt.datetime(2026, 10, 11, 6, 0, tzinfo=_tz), _p_week)
    chk("㉓f 排期时刻才过 2.5h（宽限 %gh 内）⇒ True（**机器睡过去、醒来补跑**不许误报）"
        % WEEKLY_GRACE_H, _w_ok is True, str((_w_d or {}).get("note"))[:70])
    # ㉓g–㉓k 夹具：**不再拿真库当输入**（真库会被 daily_health 记录/未来周更改变，
    # 旧写法 ㉓h 的「真库最近跑成在 10-16」是个时间炸弹）。临时 KB 只造判据要的落章。
    import tempfile as _tf3, json as _json3, shutil as _sh3
    def _mk_week_kb(runs):
        _root = _tf3.mkdtemp(prefix="kb-week-")
        for _L, _spec in runs.items():
            _d = os.path.join(_root, _L.lower(), "runs")
            os.makedirs(_d, exist_ok=True)
            with open(os.path.join(_d, _spec["run_id"] + ".json"), "w", encoding="utf-8") as _fh:
                _json3.dump(_spec, _fh)
        return _root

    _full = {L: {"run_id": "daily-20261016-0330-%s" % L,
                 "at": "2026-10-16T04:18:00",
                 "source": "pipeline_sync",
                 "change_state": "produced_changes",
                 "input_watermark": "x"} for L in ("L1", "L2", "L3", "L4", "L5", "L6", "L7")}
    _kb_full = _mk_week_kb(_full)
    try:
        _r_ok, _r_d = check_weekly_run_ran(_fri, _p_week, kb_root=_kb_full)
        chk("㉓g 整轮 L1–L7 都跑成 ⇒ True（夹具 KB，不再拿真库当输入）",
            _r_ok is True, str((_r_d or {}).get("note"))[:70])
    finally:
        _sh3.rmtree(_kb_full, ignore_errors=True)

    _kb_l0 = _mk_week_kb({"L0": {"run_id": "daily-20261016-0330-L0",
                                 "at": "2026-10-16T03:35:00",
                                 "source": "pipeline_sync",
                                 "change_state": "produced_changes",
                                 "input_watermark": "x"}})
    try:
        _j_ok, _j_d = check_weekly_run_ran(_fri, _p_week, kb_root=_kb_l0)
        chk("㉓j 只 L0 跑成（10-18 停在 L0 的真实形状）⇒ False，且 missing_layers 点名 L1–L7",
            _j_ok is False
            and set((_j_d or {}).get("missing_layers") or []) == {"L1", "L2", "L3", "L4", "L5", "L6", "L7"},
            str((_j_d or {}).get("reason"))[:90])
    finally:
        _sh3.rmtree(_kb_l0, ignore_errors=True)

    _kb_empty = _tf3.mkdtemp(prefix="kb-week-empty-")
    try:
        _m_ok, _m_d = check_weekly_run_ran(_dt.datetime(2026, 10, 26, 12, 0, tzinfo=_tz),
                                           _p_week, kb_root=_kb_empty)
        chk("㉓h **真造一次「没跑」**（夹具 KB 里没有任何 L1–L7 落章）⇒ False，"
            "且 reason 点名排期时刻、fix 给得出能跑的命令",
            _m_ok is False and "10-25 03:30" in str((_m_d or {}).get("reason"))
            and "kickstart" in str((_m_d or {}).get("fix")),
            str((_m_d or {}).get("reason"))[:90])
    finally:
        _sh3.rmtree(_kb_empty, ignore_errors=True)

    # ㉓k C1 反测：`_latest_run_record` 必须跳过**不是层运行**的记录
    #    （`daily_health` 只读体检 / `l0_daily` 只读门 / 预演档 / **别的层的记账**）。
    #    真库里 L7 的 run_at 就是被这些记录顶新的；删掉过滤器 ⇒ 本条精确变红。
    import layer_freshness as _lf_mod
    _kb_rec = _tf3.mkdtemp(prefix="kb-rec-")
    try:
        _d = os.path.join(_kb_rec, "l7", "runs")
        os.makedirs(_d)
        with open(os.path.join(_d, "20261019-0950.json"), "w", encoding="utf-8") as _fh:
            _json3.dump({"run_id": "20261019-0950", "at": "2026-10-19T09:50:27",
                         "source": "l0_daily"}, _fh)
        with open(os.path.join(_d, "20261019-0946-L7.json"), "w", encoding="utf-8") as _fh:
            _json3.dump({"run_id": "20261019-0946-L7", "at": "2026-10-19T09:46:58",
                         "source": "pipeline_sync",
                         "verdict": "全走完（预演 · 未落盘 · 非执行证据）"}, _fh)
        with open(os.path.join(_d, "20261019-0935.json"), "w", encoding="utf-8") as _fh:
            _json3.dump({"run_id": "20261019-0935", "at": "2026-10-19T09:35:00",
                         "source": "daily_health"}, _fh)
        with open(os.path.join(_d, "daily-20261018-0330-L0.json"), "w", encoding="utf-8") as _fh:
            _json3.dump({"run_id": "daily-20261018-0330-L0", "at": "2026-10-18T03:35:41",
                         "source": "pipeline_sync",
                         "verdict": "停在 L0 闸门红：exit=1 ｜ 退出码：1"}, _fh)
        with open(os.path.join(_d, "daily-20261016-0330-L7.json"), "w", encoding="utf-8") as _fh:
            _json3.dump({"run_id": "daily-20261016-0330-L7", "at": "2026-10-16T04:18:00",
                         "source": "pipeline_sync", "change_state": "produced_changes",
                         "input_watermark": "x"}, _fh)
        _now2 = time.time()
        os.utime(os.path.join(_d, "daily-20261016-0330-L7.json"), (_now2 - 300, _now2 - 300))
        os.utime(os.path.join(_d, "20261019-0946-L7.json"), (_now2 - 200, _now2 - 200))
        os.utime(os.path.join(_d, "20261019-0950.json"), (_now2 - 100, _now2 - 100))
        os.utime(os.path.join(_d, "daily-20261018-0330-L0.json"), (_now2 - 50, _now2 - 50))
        os.utime(os.path.join(_d, "20261019-0935.json"), (_now2, _now2))
        _m, _rec, _p, _rej = _lf_mod._latest_run_record(_kb_rec, "L7")
        chk("㉓k `_latest_run_record` 跳过只读体检 / L0 门 / 预演档 / 别的层的记账（只认真运行）",
            os.path.basename(_p or "") == "daily-20261016-0330-L7.json"
            and (_rec or {}).get("change_state") == "produced_changes",
            f"picked={os.path.basename(_p or '')}")
    finally:
        _sh3.rmtree(_kb_rec, ignore_errors=True)

    # ㉓l L7 例外：周更/日更驱动的 L7 预演记录**就是**它的真运行（只读闸门）；
    #    放过它，否则 judge 会回退到很久以前的记录、把 run_lower_bound 拉到过去 ⇒ 误判陈旧。
    _kb_l7prev = _tf3.mkdtemp(prefix="kb-l7prev-")
    try:
        _d = os.path.join(_kb_l7prev, "l7", "runs")
        os.makedirs(_d)
        with open(os.path.join(_d, "20261019-0946-L7.json"), "w", encoding="utf-8") as _fh:
            _json3.dump({"run_id": "20261019-0946-L7", "at": "2026-10-19T09:46:58",
                         "source": "pipeline_sync",
                         "verdict": "全走完（预演 · 未落盘 · 非执行证据）"}, _fh)
        with open(os.path.join(_d, "daily-20261019-1003-L7.json"), "w", encoding="utf-8") as _fh:
            _json3.dump({"run_id": "daily-20261019-1003-L7", "at": "2026-10-19T10:45:26",
                         "source": "pipeline_sync",
                         "verdict": "全走完（预演 · 未落盘 · 非执行证据）",
                         "extra": {"layers": ["L7"]}}, _fh)
        _now3 = time.time()
        os.utime(os.path.join(_d, "20261019-0946-L7.json"), (_now3 - 100, _now3 - 100))
        os.utime(os.path.join(_d, "daily-20261019-1003-L7.json"), (_now3, _now3))
        _m, _rec, _p, _rej = _lf_mod._latest_run_record(_kb_l7prev, "L7")
        chk("㉓l L7 例外：`daily-` 开头的 L7 预演记录算真运行（不放行 ⇒ 回退旧记录、误判陈旧）",
            os.path.basename(_p or "") == "daily-20261019-1003-L7.json",
            f"picked={os.path.basename(_p or '')}")
    finally:
        _sh3.rmtree(_kb_l7prev, ignore_errors=True)
    _ident = "nxt - (nxt - " + "datetime.timedelta(days=1))"
    chk("㉓i **恒等式回归**：凭据前瞻的「更新周期」不许再写成 `nxt - (nxt - 1 天)`"
        "（它恒等于 24h，从来没读过排期 —— 周更当场把这句话变成假话）",
        _ident not in _src4 and "_read_schedule()" in _src4)

    # ── ㉔ 报告链接的可见范围（2026-10-16 加；Owner 当天问的第二件事）──────────────
    #   为什么值得占一格：报告是**发给业务侧点开的那一份**，而它此前**建完从不设权限**
    #   （实测 76/76 `closed` ⇒ 群里/表里点开就是 Access Denied）。当天补过 319 份、
    #   代码也补了，**同一天又复发 43 份**（跑批进程没重启）—— 这种事只能靠有东西定期量。
    _perm_script = os.path.join(ROOT, "kb", "l8", "report_link_permissions.py")
    _src5 = open(__file__, encoding="utf-8").read()
    _pv_ok, _pv_d = _perm_verdict(0, json.dumps(
        {"ok": True, "n": 8, "bad": [], "want": "tenant_readable",
         "note": "每一份都是 tenant_readable"}))
    chk("㉔a 全 tenant_readable ⇒ True（这一格不许把正常路判红）", _pv_ok is True)

    _pv_ok, _pv_d = _perm_verdict(3, json.dumps(
        {"ok": False, "n": 8, "bad": [{"tok": "R8rbdYaxColioIxhiZycqITQnrb", "got": "closed",
                                       "src": "表:MC-US-WEB-IMG-cleaning-bundl"}]}))
    chk("㉔b ★ 有 closed ⇒ False，且**点名 token 与来路**、fix 给得出能跑的命令",
        _pv_ok is False and "R8rbdYaxColioIxhiZycqITQnrb" in str(_pv_d.get("who"))
        and "report_link_permissions.py --apply" in str(_pv_d.get("fix")),
        str(_pv_d.get("reason"))[:80])

    _pv_ok, _pv_d = _perm_verdict(4, json.dumps({"ok": None, "n": 0, "bad": [],
                                                 "note": "**未测**：三条来路一份报告都没抽到"}))
    chk("㉔c 读数采不到 ⇒ **None（未测）**，不许说成通过、也不许说成坏", _pv_ok is None)

    _pv_ok, _pv_d = _perm_verdict(1, "Traceback... boom", "")
    chk("㉔d 子脚本自己炸了 ⇒ None（**读不到 ≠ 坏件**，与 ③ 同一把尺子）", _pv_ok is None)

    chk("㉔e ★ **接线**：main 与 `--alert-preview` **两条路**都必须调它"
        "（只接一条 ⇒ 预览说谎 / 真发漏报，两个方向都栽过）",
        _src5.count("check_report_link_permissions()") >= 3
        and _perm_script  # 文件存在性由下一条真跑证明
        and os.path.exists(_perm_script))

    _rc6, _o6, _e6 = run(["python3", _perm_script, "--selftest"], timeout=120)
    chk("㉔f 子脚本的判据自证**真跑得通**（离线，一次网络都不发）",
        _rc6 == 0 and "14/14" in (_o6 or ""), f"rc={_rc6} tail={( _o6 or _e6 or '').strip()[-40:]}")

    print(f"\n自证：通过 {len(P)} / 失败 {len(F)}")
    for x in F:
        print(f"  · 失败：{x}")
    return 1 if F else 0


def check_l5_stamp(now=None, stamp_dir=None, records_dir=None):
    """L5 那次运行，**留痕到底写出来了没有**。返回 (ok, detail)。

    ★ 为什么必须有这一条（2026-10-10 事故；本巡检第四次补同形状的洞）：
        `kb/.work/l5_report.py:108` 直取 `r["rule_kind"]`，而 `kb/l3/candidates/rules.jsonl`
        自 2026-10-09 20:01 起被归一化成**只有生行**（无 rule_kind/authority）⇒ `KeyError`
        ⇒ **L5 落章一个字节都没写**。而编排器把这一层标成「全走完（预演）」照常记账、
        日更四层也照常"跑完" ⇒ **03:30/04:25/05:26/06:52 四次都坏着，零告警**。
        代价落在评审链上：四层前置的 L5 审计红 `E2 逐层无落章` ⇒ 前置 exit=5 ⇒
        守衡侧只能回「我这侧出故障了、这一次没判」——**图片/视频送审全挂**，
        直到 09:30 有人真送了一单才发现。

    ★ 判据（**只看落章在不在，不看它写的是 PASS 还是 FAIL**）：
        取 `kb/l7/runs/*-L5.json` 里 **mtime 最新**的一份记账（= 最近一次 L5 运行），
        读它的 `run_id`，再看 `kb/l5/runs/` 里有没有 `<run_id>*.json`。
        记账在 ⟺ 「这一层跑过」；落章不在 ⟺ 「这次运行没留下任何层侧证据」。
      · **不看 `verdict`**：`verdict` 里混着既有红灯（自测 / L3 只追加 / 冻结层），
        把它们算进来会让这条判据**恒红**、立刻失去分辨力（同 `check_layer_gates` 的纪律）。
      · 记账文件写成（`at`）后 **宽限 `L5_STAMP_GRACE_MIN`（默认 30 分钟）**，防误报在飞的运行。
      · 认定不了新旧 ⇒ **`None`（未测）**，不许当红：判成红会让人去修不存在的东西。

    ★ **非阻断项**（对齐 `check_layer_gates` 的档位理由）：落章不在 ⇒
      **图片/视频送审必然 `layer_audit_red` / 前置 exit=5 拒答**，而**文案类走 P0 快路不受影响**
      （`p0_fastpath.py` 自述「未跑四层前置/评审链」）。
      ⇒ 它不是「此刻能不能跑」这个谓词的一部分（那会因为一条模态通道坏了就把整库答成不可用），
        但它自己**要按阻断级冷却报**（见 `main` 里的 `l5stamp`），
        不许被「同因 6 小时」压成一声沉默 —— 这正是当天白等 6 小时的那个形状。
    """
    sd = stamp_dir or L5_STAMP_DIR
    rd_ = records_dir or L5_RUN_RECORDS
    now = now or time.time()
    detail: dict = {}

    try:
        names = [n for n in os.listdir(rd_)
                 if n.endswith("-L5.json") and not n.endswith("-dryrun.json")]
        recs = [(n, os.path.join(rd_, n)) for n in names]
    except OSError as exc:
        return None, {"reason": f"列不出记账目录（{exc!r}）⇒ **未测**，不是「落章丢了」"}

    if not recs:
        return None, {"reason": f"`{os.path.relpath(rd_, ROOT)}` 里一份 `*-L5.json` 记账都没有 "
                                f"⇒ **未测**（不是「落章丢了」）"}

    def _mt(item):
        try:
            return os.path.getmtime(item[1])
        except OSError:
            return 0.0

    fname, fpath = max(recs, key=_mt)
    mtime = _mt((fname, fpath))
    run_id, at_raw = None, None
    try:
        with open(fpath, encoding="utf-8") as fh:
            rec = json.load(fh)
        run_id = rec.get("run_id")
        at_raw = rec.get("at")
    except Exception as exc:                                       # noqa: BLE001
        detail["record_error"] = f"读记账失败（{exc!r}）"

    run_id = run_id or fname[:-len("-L5.json")]
    if at_raw:
        try:
            _dt = datetime.datetime.fromisoformat(at_raw)
            age_h = (datetime.datetime.fromtimestamp(now) - _dt).total_seconds() / 3600.0
        except ValueError:
            age_h = (now - mtime) / 3600.0
    else:
        age_h = (now - mtime) / 3600.0

    try:
        stamps = sorted(n for n in os.listdir(sd)
                        if n.startswith(run_id) and n.endswith(".json"))
    except OSError as exc:
        return None, {"reason": f"列不出落章目录（{exc!r}）⇒ **未测**"}

    detail |= {"newest_run_record": fname, "newest_run_id": run_id, "age_h": round(age_h, 2),
               "stamps_found": stamps, "stamp_dir": os.path.relpath(sd, ROOT)}

    if stamps:
        return True, detail
    if age_h * 60.0 < L5_STAMP_GRACE_MIN:
        return True, detail | {"note": f"该运行写成仅 {age_h * 60:.0f} 分钟，"
                                       f"在 {L5_STAMP_GRACE_MIN:g} 分钟宽限内 ⇒ 本次不报"}
    detail |= {
        "reason": f"最近一次 L5 运行（`{run_id}`，{age_h:.1f} 小时前）**没有落章**："
                  f"`{os.path.relpath(sd, ROOT)}/` 里找不到以它开头的 `.json` "
                  f"⇒ 这一层「跑了但没留下任何层侧证据」。"
                  "演示链的后果是确定的：`skill_invocation_audit` 判 **E2 逐层无落章** ⇒ "
                  "四层前置 exit=5 ⇒ **图片/视频送审拒答**（文案走 P0 快路，不受影响）。",
        "how_to_confirm": f" cd \"{ROOT}\" && sh kb/kbpy l7/scripts/skill_invocation_audit.py "
                          f"--run {run_id}   # 看它是否报 E2",
        "fix": f" ① 先看编排器日志里这一层引擎的 exit：`grep -A4 '{run_id}' /tmp/preflight-L5.acct.out`"
               f"（历史同类：`l5_report.py` KeyError ⇒ 引擎 exit=1、产物变化 0 个）；"
               f" ② 修好后**换一个新 RUN** 重跑入口："
               f"`bash kb/l8/review_run.sh --base <新BASE> --session <会话> "
               f"--decision-owner <判定主体> --content-type image|video --text \"<素材原文>\"`；"
               f" ③ **不要**续用 `{run_id}` 这个已停死的 RUN。",
        "not_proves": "落章在 ≠ 这一层判得对（`verdict` 里另有三条既有红灯，本判据不看它）；"
                      "落章不在也 ≠ 素材有问题 —— 它只说明这一次没判。",
    }
    return False, detail


def exit_code_for(problems, untested, l5stamp=()):
    """完成一次巡检该退什么码。**纯函数** —— 好让自证能离线喂样本。

    契约（2026-10-06 定，2026-10-10 扩到 L5）：0=就绪 ｜ 3=被挡（红） ｜ **2=未测**。
    ★ L5 落章缺失走 **2（未测）**，不走 3：
      文案类走 P0 快路此刻确实能跑（`p0_fastpath.py` 自述「未跑四层前置/评审链」），
      把它说成「审查链当前不可用」是**说法比依据大**；
      而它又确实不是「能跑」⇒ 也不能进 0。
    """
    if problems:
        return 3
    return 2 if (untested or l5stamp) else 0


def _alert_groups(checks):
    """把 `checks` 分成告警用的三组：`problems` / `untested`（含 L5 落章）/ 其余非阻断名。

    ★ 为什么要有它（2026-10-10）：`--alert-preview` 第一版**自己又拼了一遍**分组，
      结果 L5 那一条被列了两遍（`checks` 里出现一次、preview 又补一次）。
      两份实现必然漂移 ⇒ 分组只留这一份，preview 与 main 都调它。
    """
    groups = {"problems": [], "untested": [], "nonblocking": []}
    for name, (ok, detail) in checks:
        d = detail if isinstance(detail, dict) else {"reason": str(detail)}
        # ★ L5 落章**先特判**：它的 `False` 归「未测」那一格，**不许**落进通用的
        #   `ok is False ⇒ problems`（2026-10-10 实测：那会让它同时进 problems 与 untested，
        #   于是退出码变 3、告警正文里还列两遍 —— 两处自相矛盾）。
        if name == "L5落章":
            continue
        if ok is False:
            groups["problems"].append({"title": f"{name}：不满足", **d})
        elif ok is None:
            groups["untested"].append({"title": f"{name}：**未测**（读数没采到）", **d})

    # ★ L5 落章缺失 ⇒ 进 `untested` 这一格（不是 problems，也不是纯 warnings）：
    #   文案走 P0 快路此刻确实能跑 ⇒ 说「链坏了」是夸大；
    #   但图片/视频送审会 `layer_audit_red` 拒答 ⇒ 也不能说「此刻能跑」。
    l5_ok, l5_detail = next(((ok, d) for n, (ok, d) in checks if n == "L5落章"), (True, {}))
    l5_d = l5_detail if isinstance(l5_detail, dict) else {"reason": str(l5_detail)}
    if l5_ok is False:
        groups["untested"].append({"title": "L5 落章：最近一次运行没有落章", **l5_d})
    elif l5_ok is None:
        groups["untested"].append({"title": "L5 落章：**未测**（读数没采到）", **l5_d})
    elif l5_d.get("note"):
        # `ok=True` 且带 `note` = **在宽限内**先不报。这一档必须看得见：
        # 否则「刚判过、还没到报的时候」会被读成「没这条检查」。
        groups["nonblocking"].append({"title": f"L5 落章：{l5_d['note']}", **l5_d})
    return groups


# ────────────────────────────────────────────── main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--no-send", action="store_true")
    ap.add_argument("--no-heal", action="store_true",
                    help="只算「该不该自愈」并打印，**不真踢日更**（手工诊断用；"
                         "判据与自动跑时同一套）")
    ap.add_argument("--selftest", action="store_true",
                    help="只跑判据自证（离线，不联网、不推飞书）：三态必须分得开")
    ap.add_argument("--alert-preview", action="store_true",
                    help="只打印**会发出去的告警正文**（不推飞书、不写冷却状态）")
    ap.add_argument("--chat", default=os.environ.get("KB_ALERT_CHAT") or DEFAULT_CHAT)
    a = ap.parse_args()

    if a.selftest:
        print("就绪巡检 · 判据自证（离线；喂样本给纯函数，一次网络都不发）")
        return selftest()
    if a.alert_preview:
        # 只把**会发出去的那段正文**打出来，不推飞书、不写冷却状态。
        # 为什么要有它：告警正文本身是判据的一部分（「不许把未测说成不可用」），
        # 而它此前只能靠真发一次才看得见 —— 那等于拿群消息当测试环境。
        _c = [("认领", check_claim()), ("凭据", check_credential()),
              ("新鲜度", check_freshness()), ("技能链接", check_skill_links()),
              ("层闸门", check_layer_gates()), ("L5落章", check_l5_stamp())]
        _g = _alert_groups(_c)                          # 与 main **同一把尺子**
        # ★ 2026-10-12：非阻断那几段也要进预览 —— 原先只喂 `_g["nonblocking"]`，
        #   于是 AGENTS.md 漂移 / 回归漂移**在预览里根本不出现**，
        #   而预览的用途正是「告警正文本身是判据的一部分」。与 main 的 compose 调用对齐。
        _extra_nb = list(_g["nonblocking"])
        _d_ok, _d_detail = check_agents_drift()
        if not _d_ok:
            _extra_nb.append({"title": "AGENTS.md：已过期",
                              **(_d_detail if isinstance(_d_detail, dict)
                                 else {"reason": str(_d_detail)})})
        _w_ok, _w_detail = check_weekly_run_ran()
        if _w_ok is not True:
            _extra_nb.append({"title": ("周更：**这一轮没跑成**" if _w_ok is False
                                        else "周更：**未测**（读数没采到，不代表没跑）"),
                              **(_w_detail if isinstance(_w_detail, dict)
                                 else {"reason": str(_w_detail)})})
        _r_ok, _r_detail = check_regression_drift()
        if not _r_ok:
            _extra_nb.append({"title": "回归集：**三态漂移**（对基线）",
                              **(_r_detail if isinstance(_r_detail, dict)
                                 else {"reason": str(_r_detail)})})
        # ★ 2026-10-13：日更之后的供给链写入也要进预览（同 2026-10-12 那条教训 ——
        #   「告警正文本身是判据的一部分」，预览里不出现就等于没接）。
        # ★ 2026-10-16：报告权限那一格也要进预览（同 2026-10-12 那条教训）。
        _pm_ok, _pm_detail = check_report_link_permissions()
        if _pm_ok is not True:
            _extra_nb.append({"title": ("报告权限：**有报告打不开**（业务侧点开是 Access Denied）"
                                        if _pm_ok is False else
                                        "报告权限：**未测**（可见范围读数没采到）"),
                              **(_pm_detail if isinstance(_pm_detail, dict)
                                 else {"reason": str(_pm_detail)})})
        _p_ok, _p_detail = check_post_daily_writes(
            stale_layers=_stale_layers(dict(_c).get("新鲜度", (True, {}))[1]))
        if not _p_ok:
            _extra_nb.append({"title": "日更之后：**有人写了供给链，下游已落后**",
                              **(_p_detail if isinstance(_p_detail, dict)
                                 else {"reason": str(_p_detail)})})
        # ★ 2026-10-16：预览必须与**真发**走同一个收口 —— 否则预览会打出一份
        #   带 `**` 的正文，而真发那条路是摘过的 ⇒ **预览说谎**（这正是本文件
        #   `_alert_groups` 那条 2026-10-10 教训的同一形状：两份实现必然漂移）。
        print(plainify_for_send(compose(_g["problems"], _g["untested"], _extra_nb, []),
                                where="--alert-preview")[0])
        return 0

    checks = [("认领", check_claim()), ("凭据", check_credential()),
              ("新鲜度", check_freshness()), ("技能链接", check_skill_links()),
              # ★ 2026-10-09 加（**阻断项**）：层闸门就是评审链的前置本身。
              #   放在这里而不是"非阻断"那几段：闸门红 ⇒ 链必然拒答。
              ("层闸门", check_layer_gates()),
              # ★ 2026-10-10 加：L5 落章存在性。**非阻断**（文案走快路不受影响），
              #   但按阻断级冷却报 —— 理由见 check_l5_stamp 的 docstring。
              ("L5落章", check_l5_stamp())]
    # ★ 三态分流（2026-10-06）：`ok is None` 是**未测**，既不是通过也不是红。
    #   混进 problems 会把它说成「不可用」（08:19:59 那条告警就是这么发出去的）；
    #   混进「没它就算过」则会让一次读数失败静默通过 —— 两个方向都错。
    _groups = _alert_groups(checks)
    problems, untested = _groups["problems"], _groups["untested"]

    # ★ AGENTS.md 漂移：**非阻断** —— 单独收集，只进告警，不改 ready / 退出码。
    #   理由见 check_agents_drift 的 docstring：它会让 agent 按错的口径干活，值得报，
    #   但「文档过期」不等于「评审链跑不起来」，混进 ready 会让就绪谓词失真。
    # ★ L5 落章（2026-10-10）：分组由 `_alert_groups` 统一负责 —— 缺失时它落在
    #   `untested` 里，宽限内落在 `nonblocking` 里（看得见，但不算问题）。
    l5stamp = [w for w in untested if w["title"].startswith("L5 落章")]
    l5_note = _groups["nonblocking"]

    drift_ok, drift_detail = check_agents_drift()
    drift = []
    if not drift_ok:
        d = drift_detail if isinstance(drift_detail, dict) else {"reason": str(drift_detail)}
        drift.append({"title": "AGENTS.md：已过期", **d})

    # ★ 回归基线漂移：同样**非阻断**（2026-10-12 加）—— 它说的是「改了上游、三态变了」，
    #   不是「此刻跑不跑得起来」；且产物是周期性跑批，几天没跑叫**未测**。
    #   理由见 check_regression_drift 的 docstring。
    reg_ok, reg_detail = check_regression_drift()
    reg = []
    if not reg_ok:
        d = reg_detail if isinstance(reg_detail, dict) else {"reason": str(reg_detail)}
        reg.append({"title": "回归集：**三态漂移**（对基线）", **d})

    # ★ AGENTS.md 漂移判据的**自证**：同样**非阻断**（2026-10-12 加）。
    #   它说的是「那把尺子自己还准不准」—— 不是「此刻能不能跑」。
    #   理由见 check_drift_checker_selftest 的 docstring。
    dsc_ok, dsc_detail = check_drift_checker_selftest()
    dsc = []
    if not dsc_ok:
        d = dsc_detail if isinstance(dsc_detail, dict) else {"reason": str(dsc_detail)}
        dsc.append({"title": "判据自证：**AGENTS.md 漂移尺子**（合法变体/真坏 20 例）", **d})

    # ★ L1 索引重建：同样**非阻断**（2026-10-08 加）—— 它是**审计投影**，
    #   实测 `kb/l6/` 引用 `l1/index` 0 处 ⇒ **不在检索路径上**，坏不坏不影响此刻能不能评审。
    #   理由见 check_l1_index_rebuilt 的 docstring：它守的是「日更任务书 ③c 有没有被执行」。
    idx_ok, idx_detail = check_l1_index_rebuilt()
    l1idx = []
    if idx_ok is not True:
        d = idx_detail if isinstance(idx_detail, dict) else {"reason": str(idx_detail)}
        l1idx.append({"title": ("L1 索引：**周更的 ③c 没被执行**" if idx_ok is False
                                else "L1 索引：**未测**（索引文件不在）"), **d})

    # ★ 令牌寿命：同样**非阻断** —— 此刻能跑，但撑不到下次日更就会复发。
    #   理由见 check_credential_horizon 的 docstring：这是「每 2 小时必然发生一次」的
    #   复发路径，提前报才有意义；混进 ready 则会把「现在能不能跑」答错。
    hz_ok, hz_detail = check_credential_horizon()
    horizon = []
    if not hz_ok:
        d = hz_detail if isinstance(hz_detail, dict) else {"reason": str(hz_detail)}
        horizon.append({"title": "凭据寿命：撑不到下次日更", **d})

    # ★★ 周更兜底（2026-10-16 加）：**这一轮该跑的跑了吗**。
    #   为什么非有它：Owner 裁定① 把日更改周更、同时把陈旧阈值 24h → 8 天 ——
    #   **放宽阈值 = 同时放宽了保护**：周更一周只有一次机会，错过就是**一周没人知道**。
    #   同样**非阻断**（报的时候链照常出结论：数据还没到 8 天），但按**阻断级冷却**报
    #   —— 与 L5 落章同类：一天最多响一次，别让 6h 档把它压成沉默。
    wk_ok, wk_detail = check_weekly_run_ran()
    weekly = []
    if wk_ok is False:
        d = wk_detail if isinstance(wk_detail, dict) else {"reason": str(wk_detail)}
        weekly.append({"title": "周更：**这一轮没跑成**", **d})
    elif wk_ok is None:
        d = wk_detail if isinstance(wk_detail, dict) else {"reason": str(wk_detail)}
        weekly.append({"title": "周更：**未测**（读数没采到，不代表没跑）", **d})

    # ★ 日更收尾之后的供给链写入：同样**非阻断**（2026-10-13 加；Owner 同意「推荐 ①+③」）。
    #   它把「谁在日更之后写了库」点名出来 —— 那一刻人只知道「L5 陈旧」，不知道是谁写的、要不要等。
    #   判定要用**同一轮**的 freshness 落后层：本件不重算陈旧、不新造第二把尺子。
    _stale_now = _stale_layers(dict(checks).get("新鲜度", (True, {}))[1])
    pdw_ok, pdw_detail = check_post_daily_writes(stale_layers=_stale_now)
    postdaily = []
    if not pdw_ok:
        d = pdw_detail if isinstance(pdw_detail, dict) else {"reason": str(pdw_detail)}
        postdaily.append({"title": "日更之后：**有人写了供给链，下游已落后**", **d})

    # ★ 报告链接的可见范围（2026-10-16 加）：**非阻断**，但报的是「已经发出去的链接打不开」。
    perm_ok, perm_detail = check_report_link_permissions()
    perm = []
    if perm_ok is not True:
        dd = perm_detail if isinstance(perm_detail, dict) else {"reason": str(perm_detail)}
        perm.append({"title": ("报告权限：**有报告打不开**（业务侧点开是 Access Denied）"
                               if perm_ok is False else
                               "报告权限：**未测**（可见范围读数没采到）"), **dd})

    result = {
        # ★ `ready` 的语义是「**此刻**能不能跑」。未测 ⇒ 答不出这个问题 ⇒ 不是 ready。
        #   但它也**不是** problem —— 两个字段分开，让读的人分得清「坏了」与「没测到」。
        "ready": not problems and not untested,
        "agents_md_drift": bool(drift),
        "regression_drift": bool(reg),
        "credential_horizon": bool(horizon),
        "l1_index_stale": bool(l1idx),
        "post_daily_writes": bool(postdaily),
        # ★ 2026-10-16：周更兜底（阈值 8 天之后的唯一快信道）。
        # ★ 2026-10-16：报告链接的可见范围（**非阻断**，但它说的是"发给业务的链接打不开"）。
        "report_link_permissions": bool(perm),
        "report_permission": perm,
        "weekly_run_missed": bool(wk_ok is False),
        "weekly_run_untested": bool(wk_ok is None),
        "weekly_run": weekly,
        "post_daily": postdaily,
        "l5_stamp_missing": bool(l5stamp),
        "l5_stamp_note": [w["title"] for w in l5_note],
        "checked_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "checks": {n: (ok, d if not isinstance(d, str) else d) for n, (ok, d) in checks},
        "problems": problems,
        "untested": untested,
        "drift": drift,
        "regression": reg,
        "horizon": horizon,
        # ★ 结构性事实**始终**进结果（含"通过"时）—— 它是常驻状态，不是事件：
        #   就算令牌此刻撑得过下次日更，2h 寿命也撑不过再下一次。放在这里才不会被"✅ 就绪"盖掉。
        "credential_horizon_note": (hz_detail or {}).get("structural_note")
        if isinstance(hz_detail, dict) else None,
    }

    # ★★ 受控自愈（2026-10-07；**2026-10-20 Owner 定 ① 改触发面**）：
    #   **只认「周更这一轮没跑成」**，在五道前置全过时踢一次补跑。
    #   陈旧（`fresh_ok=False`）**不再触发**：周更周期 7 天 < 陈旧阈值 8 天 ⇒
    #   陈旧出现时下一次排期必在 7 天内；此时踢整链是抢跑，且补不回某一层的红
    #   （2026-10-20 实测：12:16 因「陈旧（L7）」踢的那轮 13:45 **停在 L6**）。
    #   陈旧仍进告警正文（`check_freshness` 的 fix 写清下一步），但不自动动手。
    #   放在告警**之前**：这样同一条告警里就能写清「我做了什么、成了没成」，
    #   而不是等下一次巡检才说 —— 人看到的是一句话，不是两半。
    heal_items, heal_rec = [], None
    cd = dict(checks)
    fresh_ok = cd.get("新鲜度", (True, {}))[0]
    claim_ok = cd.get("认领", (True, {}))[0]
    _hc = heal_causes(fresh_ok, wk_ok)
    if _hc["triggered"]:
        jr_pid, jr_why = job_running(DAILY_SKILL_LABEL)
        lock_on, lock_why = kb_lock_alive()
        last_ts, n_today = _heal_state()
        # ★ 2026-10-10：算「本轮陈旧的层集合」当签名，并读回「上一轮踢的是哪个集合」。
        # ★★ 2026-10-19（Owner：「我需要的是你解决问题」）：**周更这一轮没跑成**也触发自愈。
        #   原先是「新鲜度红」才动，而新鲜度阈值 8 天 ⇒ 周更失败后要等约 2 天才有人兜；
        #   10-19 实测就是**人**在 10:03 手敲 kickstart 补的（自愈台账最后一条停在 10-13）。
        #   触发条件与签名都走**纯函数**（`heal_causes` / `heal_sig`），自证喂同一份逻辑。
        _kick_sig = heal_sig(fresh_ok, cd.get("新鲜度", (True, {}))[1], wk_ok, wk_detail)
        _last_sig, _last_sig_at = _heal_sig_state()
        go, why = heal_decision(freshness_stale=_hc["freshness_stale"],
                                weekly_missed=_hc["weekly_missed"],
                                claim_free=(claim_ok is not False),
                                job_running_pid=jr_pid, lock_alive=lock_on,
                                last_heal_ts=last_ts, attempts_today=n_today,
                                kick_sig=_kick_sig, last_kick_sig=_last_sig)
        heal_rec = {"decided": go, "why": why, "job": jr_why, "lock": lock_why,
                    "attempts_today": n_today}
        if go and a.no_heal:
            r = {"ok": False, "returncode": None, "dry_run": True,
                 "would_run": f"launchctl kickstart -k gui/{os.getuid()}/{DAILY_SKILL_LABEL}"}
        elif go:
            r = attempt_heal(why)
        else:
            r = None
        if go:
            heal_rec["attempt"] = r
            if r.get("ok"):
                _remember_heal(sig=_kick_sig)
            heal_items.append({
                "title": ("**该自愈，但本次是 --no-heal（只算不做）**"
                          if (r or {}).get("dry_run") else
                          "**已自动处置：踢了一次日更**（受控自愈）"),
                "reason": why,
                "detail": ("已执行 `launchctl kickstart -k "
                           f"gui/{os.getuid()}/{DAILY_SKILL_LABEL}`（rc={r.get('returncode')}）。"
                           "它会自己认领、自己释放；跑完（~15 分钟）新鲜度应恢复。"
                           "台账：`kb/.work/freshness-heal.ndjson`"),
            })
        else:
            heal_items.append({
                "title": "**没有自动处置**（有一道前置不满足）",
                "reason": why,
                "detail": f"作业：{jr_why} ｜ 锁：{lock_why} ｜ 今日已自愈 {n_today} 次",
            })
    result["heal"] = heal_rec
    result["drift_checker_selftest"] = {"ok": dsc_ok, "detail": dsc_detail}

    sent = None
    to_alert = (problems + untested + horizon + drift + reg + l1idx + dsc + l5_note
                + postdaily + weekly)
    # ★ 自愈动作本身**必须发得出去** —— 绕过冷却：它是「我替你动了手」，不是重复提醒。
    force_alert = bool(heal_rec and (heal_rec.get("attempt") or {}).get("ok"))
    if to_alert and not a.no_send:
        sig = signature(p["title"] for p in to_alert)
        # ★ 2026-10-10：L5 落章也在**阻断级**冷却里 —— 它让图片/视频送审全量拒答，
        #   与「整条链拒答」同档；落进 6h 档就会重演当天「响两声就沉默」的形状。
        # ★ 2026-10-16：周更没跑也走**阻断级**冷却（与 L5 落章同档）—— 一周才一次机会，
        #   落进 6h 档会重演「响两声就沉默」的形状。
        go, why = should_alert(sig, BLOCKING_COOLDOWN_H
                               if (problems or l5stamp or wk_ok is False) else COOLDOWN_H)
        if force_alert and not go:
            go, why = True, f"{why} ⇒ **但本次有自愈动作，强制报一次**"
        if go:
            ok, info = alert(compose(problems, untested,
                                     horizon + drift + reg + l1idx + dsc + l5_note + postdaily
                                     + weekly + perm,
                                     heal_items), a.chat)
            sent = {"sent": ok, "why": why, "info": info}
            if ok:
                remember(sig)
        else:
            sent = {"sent": False, "why": why}
    result["alert"] = sent

    if a.json:
        print(json.dumps(result, ensure_ascii=False, indent=1))
    else:
        # ★ 2026-10-10：`untested`/`l5stamp` 都算「未测」，判定要与退出码**同一把尺子**
        #   （原先只看 `problems`：L5 落章丢了会打印「被挡」却退 2，两处自相矛盾）。
        _untested_any = bool(untested or l5stamp)
        verdict = ("✅ 就绪" if result["ready"]
                   else ("❌ 被挡" if problems else "⚠️ 未测（读数没采到，不代表链坏了）"))
        print(f"就绪巡检 @ {result['checked_at']}  ⇒  {verdict}"
              + ("（★ 令牌撑不到下次日更，见下）" if horizon else "")
              + ("（另有 AGENTS.md 漂移，见下）" if drift else "")
              + ("（★ L1 索引没重建，见下）" if l1idx else "")
              + ("（★ L5 落章丢了：图片/视频送审会拒答，见下）" if l5stamp else "")
              + ("（★ 日更之后有人写库、下游已落后，见下）" if postdaily else ""))
        for n, (ok, d) in checks:
            mark = "✅" if ok is True else ("❌" if ok is False else "⚠️")
            print(f"  {mark} {n}: "
                  f"{json.dumps(d, ensure_ascii=False)[:220] if isinstance(d, (dict, list)) else d}")
        for w in horizon:
            print(f"  ⚠️ {w['title']}: 到期 {w.get('expires_at')} ｜ 下次日更 {w.get('next_daily_run')}"
                  f" ｜ 余 {w.get('remaining_h')}h")
            print(f"     {str(w.get('reason'))[:200]}")
        # ★ L1 索引（非阻断）：只在该红时印 —— 绿时留白，免得把常驻状态说成事件。
        for w in l1idx:
            print(f"  ⚠️ {w['title']}: {str(w.get('reason'))[:200]}")
            if w.get("before"):
                print(f"     上次重建 {w['before']} ｜ 阈值 {L1_INDEX_STALE_H:g}h")
            if w.get("fix"):
                print(f"     ▶ 修法：{str(w['fix'])[:300]}")
        for w in l5_note:
            print(f"  ℹ️ {w['title']}")
        # ★ 日更之后的供给链写入（非阻断）：只在该红时印 —— 绿时留白，免得把常驻读数说成事件。
        for w in postdaily:
            print(f"  ⚠️ {w['title']}: {str(w.get('reason'))[:300]}")
            if w.get("stale_layers"):
                print(f"     本轮落后层：{'、'.join(str(x) for x in w['stale_layers'])}")
            if w.get("cost"):
                print(f"     {str(w['cost'])[:240]}")
            if w.get("fix"):
                print(f"     ▶ 修法：{str(w['fix'])[:300]}")
        # ★ L5 落章（非阻断）：只在该红时印。
        for w in l5stamp:
            print(f"  ⚠️ {w['title']}: {str(w.get('reason'))[:240]}")
            print(f"     最近一次记账 {w.get('newest_run_record')} ｜ {w.get('age_h')}h 前 "
                  f"｜ 落章 {w.get('stamps_found')}")
            if w.get("how_to_confirm"):
                print(f"     ▶ 复核：{str(w['how_to_confirm'])[:300]}")
            if w.get("fix"):
                print(f"     ▶ 修法：{str(w['fix'])[:400]}")
        if result.get("credential_horizon_note"):
            print(f"  ⏳ 凭据寿命: {result['credential_horizon_note']}")
        if result.get("heal"):
            h = result["heal"]
            at = h.get("attempt") or {}
            tail = (" ｜ **--no-heal：只算不做**" if at.get("dry_run")
                    else (f" ｜ 已执行 rc={at.get('returncode')}" if at else ""))
            print(f"  🩺 自愈: 决定={h.get('decided')} ｜ {str(h.get('why'))[:90]}{tail}")
        if sent:
            print(f"  告警: {json.dumps(sent, ensure_ascii=False)[:200]}")

    # ★ 三个退出码必须各不相同（2026-10-06）：0=就绪 / 3=被挡（红） / **2=未测**。
    #   原先只有 0 与 3，于是「读数没采到」只能挤进「被挡」那一格 ——
    #   而它们要人说出口的话完全不同（一个是「链坏了」，一个是「没测到」）。
    #   同口径见 AGENTS.md §2.4.2 的 L3（未测退 2，不是 0）与 §2.7 的 E1/E4。
    # ★ L5 落章（2026-10-10）：**进"未测"这一格，但不进"被挡"**。
    #   为什么不进 problems：文案类走 P0 快路，此刻确实能跑 ⇒ 说成「链坏了」是夸大。
    #   为什么不留在纯 warnings：`compose()` 在**没有阻断项**时首行是
    #     「ℹ️ 就绪巡检（非阻断提醒：**此刻能跑**）」—— 而 L5 落章丢了的时候
    #     图片/视频送审**跑不了**（前置 exit=5）。那句话在说出去的时候就没有依据，
    #     正是本库反复记过的「说出去的话比手上的依据大」。
    #   放进 untested 后首行是「就绪**未测** —— 读数没采到，不代表链坏了」：
    #     「这次没拿到这一层的证据」是准确描述，且两个方向都不夸。
    return exit_code_for(problems, untested, l5stamp)


if __name__ == "__main__":
    sys.exit(main())
