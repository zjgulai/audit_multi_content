#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_agents_md_drift.py —— 检 `~/.dsh/AGENTS.md` 里**可机械验证的断言**是否已过期。

## 为什么需要它

AGENTS.md 是每次会话注入 agent 上下文的全局规则。它的**结构决定了它会过期**：
它复述的事实住在别处（`layers.yaml` / `routes.yaml` / 代码本身），
事实一变而没人回头改文档，它就变成**误导源**。

2026-10-05 实际踩到两次（都是「文档说 A、代码是 B」，而 agent 采信了文档）：

  ① AGENTS.md 写「API 侧没有判定主体闸门（`grep decision_owner kb_api.py` = 0 命中）」，
     实测 **15 命中、缺口已修** ⇒ 我据此误判了机制状态。
  ② AGENTS.md **压根没写「守衡在哪台机器」**，我只能去读别处注释，
     采信了 `workbench-service.sh` 里一句「跑在别的机器上的守衡」⇒ 误判成外机。

⇒ **文档不可能永不过期。能做到的是「过期被自动发现」。**
   本脚本只做一件事：把 AGENTS.md 里那些**能用命令核**的断言，逐条拿真值对一遍。

## 设计纪律

  · **只检可机械验证的断言** —— 不碰散文、不做语义判断、不猜文档"想说什么"。
  · **不改 AGENTS.md** —— 只报漂移。改文档要人（或另开一次明确授权的动作）。
  · **每条都指出修法** —— 报告里给「哪一句、真值是什么、该改成什么」。
  · 断言清单写在 `CLAIMS` 里，**新增/删除断言在这里改**，别把判据散到别处。

## 用法

    python3 kb/l8/check_agents_md_drift.py           # 人读；无漂移退出 0，有漂移退出 3
    python3 kb/l8/check_agents_md_drift.py --json
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
AGENTS = os.path.expanduser("~/.dsh/AGENTS.md")
KBPY = os.path.join(ROOT, "kb", "kbpy")
BRIDGE = os.path.join(ROOT, "review-bridge")


def sh(argv, timeout=60):
    try:
        p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, errors="replace")
        return p.returncode, p.stdout, p.stderr
    except Exception as exc:                                    # noqa: BLE001
        return 125, "", repr(exc)


def grep_count(path, pattern):
    if not os.path.exists(path):
        return None
    try:
        return len(re.findall(pattern, open(path, encoding="utf-8", errors="replace").read(), re.M))
    except Exception:                                           # noqa: BLE001
        return None


# ─────────────────────────────────────────── 断言清单
# 每条： (id, 断言的中文说明, 验证函数 -> (ok, 真值描述, 修法 or None))

def c_agents_exists():
    if not os.path.exists(AGENTS):
        return False, f"找不到 {AGENTS}", None
    n = len(open(AGENTS, encoding="utf-8", errors="replace").read())
    return True, f"{AGENTS} 存在，{n} 字符", None


def c_shouheng_section(agents_text=None):
    """AGENTS.md 必须写明「守衡在本机」，且给出 launchd 标签与工作目录。

    ★ 2026-10-12 假红体检：原先三个 needle 都是**字面子串**，其中「本机」是**措辞**——
      改成「本地」「这台机器」这种**同义且更自然**的写法会当场判红。
      ⇒ 标识符（launchd 标签 / 工作目录）**必须逐字**（它们是可核事实），
        而**定性措辞**放宽成 `本机|本地`（同一条事实的两种说法）。
    """
    txt = agents_text if agents_text is not None else (
        open(AGENTS, encoding="utf-8", errors="replace").read() if os.path.exists(AGENTS) else "")
    must = [k for k in ("com.shouheng.lark", "audit_multi_content") if k not in txt]
    if must:
        return False, f"AGENTS.md 缺「守衡」事实块的硬要素：{must}", \
            "补一节「守衡（飞书机器人）在哪 —— 就在本机」，写明 launchd 标签 / 进程 / 工作目录 / 它读的库"
    if not re.search(r"本机|本地", txt):
        return False, "AGENTS.md 的「守衡」那节没有「本机/本地」定性", \
            "写上它跑在本机（这是 2026-10-05 实测纠正过的关键事实）"
    return True, "含 launchd 标签 + 工作目录 + 「本机/本地」定性", None


def _shouheng_paths(plist_path=None):
    """从**守衡自己的 plist** 派生「它到底跑哪个脚本、在哪个目录」——**不在这里抄第二份路径**。

    ★ 2026-10-12 假红体检的产物：原先本判据把 `run_shouheng.sh` / `ws_daemon.mjs` 两条
      绝对路径写死在这里 ⇒ **仓一搬家就红**，哪怕 plist 与 AGENTS.md 都已同步改好
      —— 那是「判据自己抄了第二份真源」，本库明令禁止的做法。
    plist 里本来就有 `ProgramArguments[1]`（启动脚本）与 `WorkingDirectory`（工作目录），
    守护进程 `ws_daemon.mjs` 就住在那个工作目录下 ⇒ 全部可派生。
    """
    pl = plist_path or os.path.expanduser("~/Library/LaunchAgents/com.shouheng.lark.plist")
    if not os.path.exists(pl):
        return None, {"plist": False}
    try:
        import plistlib
        d = plistlib.loads(open(pl, "rb").read())
    except Exception:                                           # noqa: BLE001
        return pl, {"plist": True, "readable": False}
    args = d.get("ProgramArguments") or []
    wd = str(d.get("WorkingDirectory") or "")
    sub = str(args[1]) if len(args) > 1 else ""
    return pl, {"plist": True, "readable": True,
                "run_shouheng.sh": sub, "工作目录": wd,
                "ws_daemon.mjs": os.path.join(wd, "ws_daemon.mjs") if wd else ""}


def c_shouheng_actually_local(plist_path=None, probe=None):
    """真值侧：守衡确实在本机跑（launchd 已装 + **plist 派生出的**脚本在位）。

    `plist_path` / `probe` 只在 `--selftest` 里注入（喂样本）。
    """
    pl, info = _shouheng_paths(plist_path)
    if pl is None:
        return False, json.dumps(info, ensure_ascii=False), \
            "守衡的 launchd plist 不在 ⇒ 「在本机跑」这条事实失效"
    host_ok = probe if probe is not None else (
        sh(["launchctl", "print", f"gui/{os.getuid()}/com.shouheng.lark"], timeout=30)[0] == 0)
    sub, daemon = info.get("run_shouheng.sh", ""), info.get("ws_daemon.mjs", "")
    detail = dict(info, launchctl_loaded=host_ok,
                  run_shouheng_sh_exists=bool(sub) and os.path.exists(sub),
                  ws_daemon_exists=bool(daemon) and os.path.exists(daemon))
    ok = bool(sub) and bool(daemon) and detail["run_shouheng_sh_exists"] \
        and detail["ws_daemon_exists"] and host_ok
    if ok:
        return True, json.dumps(detail, ensure_ascii=False), None
    return False, json.dumps(detail, ensure_ascii=False), \
        ("守衡运行时不在 plist 说的位置、或未装载 —— "
         "**路径取自 plist 自己**，所以红=真要人看一眼（迁走了就同步 plist 与 AGENTS.md 的守衡事实块）")


def c_kbapi_decision_owner():
    """AGENTS.md 2026-10-05 更正为「已修」。核真值：kb_api.py 里 decision_owner 命中数 > 0。"""
    n = grep_count(os.path.join(ROOT, "kb_api.py"), r"decision_owner")
    if n is None:
        return False, "读不到 kb_api.py", None
    if n > 0:
        return True, f"kb_api.py 中 decision_owner 命中 {n} 处（与「已修」一致）", None
    return False, f"kb_api.py 中 decision_owner 命中 0 处", \
        "AGENTS.md 现称「该缺口已修」，但代码里已无 decision_owner ⇒ 文档与代码反向漂移，需重核"


def c_bridge_gates():
    """AGENTS.md 称「review-bridge 仍两样都缺（0 命中）」。核真值。"""
    f = os.path.join(BRIDGE, "review_bridge.py")
    if not os.path.exists(f):
        return False, "找不到 review-bridge/review_bridge.py", \
            "若桥已删除/迁走，请更新 AGENTS.md 里关于桥的那段"
    n_do = grep_count(f, r"decision_owner") or 0
    n_pf = grep_count(f, r"layer_preflight") or 0
    if n_do == 0 and n_pf == 0:
        return True, "桥仍缺两道闸门（decision_owner=0, layer_preflight=0），与文档一致", None
    return False, f"桥已出现闸门（decision_owner={n_do}, layer_preflight={n_pf}）", \
        "AGENTS.md 称「桥仍两样都缺」⇒ 已过期，改成实际命中数"


def _skills_of(layers_obj):
    """从 layers.yaml 的 YAML 对象里取 {L4..L7: [skill, …]} —— **三种写法都要认**。

    为什么要三种：`skill:` 可以写成行内列表 `[a, b]`、单值 `kb-x`、或块序列
    （`skill:` 换行 + `  - kb-x`）。**2026-10-12 实测**：只认行内写法的那种正则，
    在该文件被改成块序列后当场报「没找全：{}」—— 而文件一个字没丢（S2 真解析照样认得出）。
    """
    out = {}
    for entry in (layers_obj or []):
        if not isinstance(entry, dict):
            continue
        lid = str(entry.get("layer") or entry.get("id") or "").strip()
        if lid not in ("L4", "L5", "L6", "L7"):
            continue
        sk = entry.get("skill")
        if isinstance(sk, str):
            sk = [sk]
        if isinstance(sk, list):
            out[lid] = [str(x) for x in sk if str(x).strip()]
    return out


def c_layers_skills(layers_path=None):
    """AGENTS.md 把「到某层调哪个 skill」指向 layers.yaml（唯一真源）。核该文件可读且 L4–L7 有 skill。

    `layers_path` 只在 `--selftest` 里传（喂样本）；默认就是真库那份。
    """
    y = layers_path or os.path.join(ROOT, "kb", "l7", "registry", "layers.yaml")
    if not os.path.exists(y):
        return False, f"找不到 {y}", None
    txt = open(y, encoding="utf-8", errors="replace").read()
    found = {}
    # ★ 首选 YAML 真解析（那份文件本来就是 YAML；正则只作回落）
    try:
        import yaml as _yaml
        found = _skills_of((_yaml.safe_load(txt) or {}).get("layers"))
    except Exception:                                           # noqa: BLE001
        found = {}
    if not all(found.get(L) for L in ("L4", "L5", "L6", "L7")):
        # 回落：老的行内写法（保留原逻辑，免得真解析失败时判据整个失效）
        _re_found = {}
        for L in ("L4", "L5", "L6", "L7"):
            for seg in re.split(r"(?m)^(?=\s*-\s)", txt):
                if re.search(rf"\b{L}\b", seg[:200]):
                    mm = re.search(r"skill:\s*(\[[^\]]*\])", seg)
                    if mm:
                        _re_found[L] = mm.group(1)
                        break
        for L, v in _re_found.items():
            found.setdefault(L, v)
    have = all(found.get(L) for L in ("L4", "L5", "L6", "L7"))
    if have:
        return True, json.dumps({k: found[k] for k in ("L4", "L5", "L6", "L7")},
                                ensure_ascii=False), None
    return False, f"layers.yaml 里 L4–L7 的 skill 字段没找全：{found}", \
        ("AGENTS.md 指向 layers.yaml 是对的，但这个文件本身可能改版了 —— 需人工看它的新形状"
         "（★ 2026-10-12：本判据已改用 YAML 真解析，行内列表 / 单值 / 块序列三种写法都认；"
         "再报这条，说明 L4–L7 里真有一层的 skill 没了）")


def c_key_scripts(agents_text=None, min_paths=5):
    """AGENTS.md 里点名的**库内脚本路径**必须都在位。

    ★ 2026-10-12 假红体检的产物：原先这里是**手抄的 6 条清单**——
      那是把 AGENTS.md 的内容又抄了一份（**第二份真源**）：
      脚本合法改名、AGENTS.md 同步改好之后，**这条判据仍然红**（它在核旧名字）。
      ⇒ 现在**从 AGENTS.md 抽**：凡文中出现的 `kb/…\.(py|sh|mjs)` 都要在位。
      抽不出任何路径（<min_paths）也判红 —— 否则「文档被清空」会静默变绿。
    """
    txt = agents_text if agents_text is not None else (
        open(AGENTS, encoding="utf-8", errors="replace").read() if os.path.exists(AGENTS) else "")
    paths = sorted(set(re.findall(r"\bkb/[\w./\-]+\.(?:py|sh|mjs)\b", txt)))
    if len(paths) < min_paths:
        return False, f"从 AGENTS.md 只抽出 {len(paths)} 个库内脚本路径（<{min_paths}）", \
            "AGENTS.md 可能被清空/改版了 —— 抽不出东西时不许静默判绿"
    miss = [k for k in paths if not os.path.exists(os.path.join(ROOT, k))]
    if miss:
        return False, f"AGENTS.md 点名但不在位：{miss}", \
            "要么脚本改名/搬家了（**同时**更新 AGENTS.md 与引用），要么库结构变了"
    return True, f"AGENTS.md 点名的 {len(paths)} 个库内脚本全部在位", None


def c_watchdog_installed():
    """本优化包装的巡线任务应仍在位（否则告警机制静默失效）。"""
    w = os.path.join(ROOT, "kb", "l8", "watch_review_readiness.py")
    plist = os.path.expanduser("~/Library/LaunchAgents/com.kb.review-readiness.plist")
    rc, out, err = sh(["launchctl", "print", f"gui/{os.getuid()}/com.kb.review-readiness"], timeout=30)
    ok = os.path.exists(w) and os.path.exists(plist) and (rc == 0)
    d = {"watch_script": os.path.exists(w), "plist": os.path.exists(plist), "loaded": rc == 0}
    if ok:
        return True, json.dumps(d, ensure_ascii=False), None
    return False, json.dumps(d, ensure_ascii=False), \
        "就绪巡检没在位 ⇒ 「出问题提前告知」会静默失效：重新 load com.kb.review-readiness.plist"


def c_verified_stamp(agents_text=None, now=None):
    """AGENTS.md 的事实块应带「已核于 <日期>」；超过 30 天提醒重核。

    ★ 2026-10-12 假红体检：原正则只认「已核于 + 空白 + YYYY-MM-DD」——
      写成 `已核于：2026-10-12`（全角冒号）或 `已核于 2026/10/12` 都**合法**，却会判红。
      ⇒ 分隔符放宽到 `[：:\s]*`，年月日分隔符放宽到 `[-/]`。
    """
    txt = agents_text if agents_text is not None else (
        open(AGENTS, encoding="utf-8", errors="replace").read() if os.path.exists(AGENTS) else "")
    m = [x.replace("/", "-") for x in
         re.findall(r"已核于[：:\s]*(\d{4}[-/]\d{2}[-/]\d{2})", txt)]
    if not m:
        return False, "AGENTS.md 里没有「已核于 <日期>」标记", \
            "给可机械验证的事实块加一行「> 已核于 YYYY-MM-DD（核验命令见 kb/l8/check_agents_md_drift.py）」"
    newest = max(m)
    d0 = time.mktime(time.strptime(newest, "%Y-%m-%d"))
    age = ((now if now is not None else time.time()) - d0) / 86400.0
    if age > 30:
        return False, f"最近一次核验是 {newest}（{age:.0f} 天前）", \
            "过期已久，请重跑 check_agents_md_drift.py 并更新「已核于」日期"
    return True, f"最近核验 {newest}（{age:.0f} 天前）", None


#: 中文星期 → launchd 的 `Weekday`（**0 与 7 都是周日**）。
_WD_CN = {"日": 0, "天": 0, "一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6}


def sched_key(sched):
    """排期指纹 `(HH:MM, (星期…))` —— **周期与时刻一起**；读不出回 `None`。

    ★★ 2026-10-16：原先只比 `HH:MM` ⇒ 「每周日 03:30」与「每天 03:30」会被判成**一致**
      （两份 plist 一份写周日、一份写每天，尺子照样绿）。周期必须进指纹。
    """
    if not isinstance(sched, dict) or sched.get("Hour") is None or sched.get("Minute") is None:
        return None
    wd = sched.get("Weekday")
    raw = wd if isinstance(wd, (list, tuple)) else ([wd] if wd is not None else [])
    try:
        return ("%02d:%02d" % (int(sched["Hour"]), int(sched["Minute"])),
                tuple(sorted({int(x) % 7 for x in raw})))
    except Exception:                                           # noqa: BLE001
        return None


def doc_sched_key(txt):
    """从 AGENTS.md 正文里读排期：`每天 HH:MM` 或 `每周X HH:MM` → 与 `sched_key()` 同形状。

    读不出回 `None`（调用方必须判**不一致**，而不是"没写就算过"）。
    """
    m = re.search(r"每(周([一二三四五六日天])|天)\s*(\d{1,2}:\d{2})", txt or "")
    if not m:
        return None
    return ("%02d:%02d" % tuple(int(x) for x in m.group(3).split(":")),
            ((_WD_CN[m.group(2)],) if m.group(2) else ()))


def c_credential_horizon():
    """令牌寿命陷阱：**脚本里真有这条判断** + **AGENTS.md 真写了这条结论**（2026-10-05 加）。

    为什么值得单列一条断言：这道检查修的是「**看门狗自己的盲区**」——
    它一度只查「令牌现在在不在」，于是对着一枚 2 小时后即死的令牌报 ✅，
    然后在**次日 08:30** 让日更的 L0 回落失败 → L1–L6 冻结 → 评审链拒答。
    ★ 盲区的要命之处是**它不报错**：删掉这段代码，就悄无声息地退回去了，
      而症状要等第二天 08:30 才发作。⇒ 必须机械可核，不能靠"读起来还在"。
    """
    w = os.path.join(ROOT, "kb", "l8", "watch_review_readiness.py")
    code = {}
    if os.path.exists(w):
        t = open(w, encoding="utf-8", errors="replace").read()
        code = {"函数存在": "def check_credential_horizon" in t,
                "已接线": "check_credential_horizon()" in t,
                "读排期不抄第二份": "StartCalendarInterval" in t}
    else:
        code = {"脚本存在": False}

    txt = open(AGENTS, encoding="utf-8", errors="replace").read() if os.path.exists(AGENTS) else ""
    # ★ 2026-10-12 假红体检：原先断言的是**加粗**写法（`**2.0 小时**`）—— 去掉加粗是合法排版改动，
    #   却会判红。⇒ 比对前把 `**` 剥掉，只核**事实文本**。
    _flat = txt.replace("**", "")
    # ★ 2026-10-16：日更改**周更**（Owner 裁定①）⇒ 这里断的「间隔」跟着改。
    #   它断的是**文档里那个事实还在不在**（不是「数字必须是 24」）——
    #   所以改排期时必须**同时**改这里与 AGENTS.md，两边都不许单飞。
    doc = {"2.0 小时寿命": "2.0 小时" in _flat,
           "7 天更新间隔": "7 天" in _flat,
           "排期写的是每周日": "每周日" in _flat,
           "根治指向 bot 授权": "可阅读协作者" in _flat}

    # 交叉核对：AGENTS.md 说的「24 小时 / 每天 08:30」与 launchd 排期是否还一致。
    # plist 可能不是 well-formed XML（注释里禁止 `--`），所以**先严格后宽松**。
    sched, how = None, "未读"
    p = os.path.expanduser("~/Library/LaunchAgents/com.kb.pipeline-daily.plist")
    try:
        raw = open(p, "rb").read()
        try:
            import plistlib
            sched = plistlib.loads(raw).get("StartCalendarInterval")
            how = "plistlib"
        except Exception:                                       # noqa: BLE001
            m = re.search(rb"<key>StartCalendarInterval</key>\s*<dict>(.*?)</dict>", raw, re.S)
            if m:
                seg = m.group(1)
                g = lambda k: (int(re.search(rb"<key>%s</key>\s*<integer>(\d+)</integer>" % k, seg).group(1))
                               if re.search(rb"<key>%s</key>\s*<integer>(\d+)</integer>" % k, seg) else None)
                sched = {"Hour": g(b"Hour"), "Minute": g(b"Minute"),
                         "Weekday": g(b"Weekday")}          # ★ 2026-10-16：周期也要读
                how = "regex（plist 非 well-formed XML）"
    except Exception as exc:                                    # noqa: BLE001
        how = f"读不到（{exc!r}）"

    # ★ 2026-10-06 改：**两份 plist 互校 + 与 ~/.dsh/AGENTS.md 写的那一刻互校**。
    #
    #   原先这一行是 `sched.get("Hour") == 8 and sched.get("Minute") == 30` ——
    #   把「日更几点」又抄了**第三份**，而且抄在一个检查器里。实测后果：
    #   Owner 把日更从 08:30 挪到 03:30（理由：日更持全局单槽 12~24 分钟，08:30 正好挡住
    #   人白天用守衡），**这条断言当场变红 —— 而它红的原因是「排期变了」，不是「防护坏了」**。
    #   一个把正确改动判成故障的断言，就是这个仓库最忌讳的那种检查器。
    #
    #   而原先真正该断的那件事**没有任何东西在断**：`com.kb.pipeline-daily-skill.plist`
    #   的注释里写着「改时刻要同时改两份」，两份一不一致**从来没被检查过** ——
    #   注释里的警告不是约束（AGENTS.md §2.4）。现在两份不一致会红，文档与 plist 不一致也会红。
    def _read_sched(path):
        try:
            raw = open(path, "rb").read()
        except Exception as exc:                                # noqa: BLE001
            return None, f"读不到（{exc!r}）"
        try:
            import plistlib
            return plistlib.loads(raw).get("StartCalendarInterval"), "plistlib"
        except Exception:                                       # noqa: BLE001
            m = re.search(rb"<key>StartCalendarInterval</key>\s*<dict>(.*?)</dict>", raw, re.S)
            if not m:
                return None, "解析不出 StartCalendarInterval"
            seg = m.group(1)

            def g(k):
                mm = re.search(rb"<key>%s</key>\s*<integer>(\d+)</integer>" % k, seg)
                return int(mm.group(1)) if mm else None
            return {"Hour": g(b"Hour"), "Minute": g(b"Minute")}, "regex（非 well-formed XML）"

    LA = os.path.expanduser("~/Library/LaunchAgents")
    sched_skill, how_skill = _read_sched(os.path.join(LA, "com.kb.pipeline-daily-skill.plist"))

    plist_key = sched_key(sched)
    skill_key = sched_key(sched_skill)
    # ★★ 2026-10-16：**周期也要互校**。原先只比 `HH:MM` ⇒ 「每周日 03:30」与「每天 03:30」
    #   会被判成一致 —— 两份 plist 里一份写周日、一份写每天，尺子照样绿。
    #   AGENTS.md 那边同理：从「每天 HH:MM」改成「每周日 HH:MM」（周期与时刻一起读）。
    doc_key = doc_sched_key(txt)

    sched_ok = (plist_key[0] is not None and plist_key == skill_key   # ★ 两份必须一致（含周期）
                and doc_key == plist_key)                             # ★ 文档必须与排期一致
    ok = all(code.values()) and all(doc.values()) and sched_ok
    d = {"code": code, "doc": doc,
         "plist_schedule": sched, "plist_read_via": how,
         "skill_plist_schedule": sched_skill, "skill_plist_read_via": how_skill,
         "两份一致": plist_key == skill_key,
         "两个排期": [list(plist_key or ()), list(skill_key or ())],
         "AGENTS.md 写的排期": list(doc_key or ()),
         "排期与文档一致": doc_key == plist_key}
    if ok:
        return True, json.dumps(d, ensure_ascii=False), None
    return False, json.dumps(d, ensure_ascii=False), (
        "令牌寿命陷阱的防护缺了一角 ⇒ 会退回「对 2 小时后即死的令牌报 ✅」的盲区，"
        "症状要到次日日更失败才发作。逐项看上面的 code / doc / 两份一致 / 时刻与排期一致："
        "code 缺 → kb/l8/watch_review_readiness.py 的 check_credential_horizon 被删或没接线；"
        "doc 缺 → ~/.dsh/AGENTS.md 的「令牌寿命陷阱」段被删；"
        "两份 plist 不一致 → 挪日更时刻时只改了一份（这正是 skill plist 注释里警告过、"
        "却一直没有执行点的那一条）；"
        "AGENTS.md 与排期不一致 → 挪了时刻／周期但文档没跟着改"
        "（文档写法：`每天 HH:MM` 或 `每周X HH:MM` —— 周期与时刻**一起**核）")


def c_source_readonly():
    """飞书只读源 + 身份口径 在位（2026-10-10 加）。

    为什么单列一条：Owner 这两条规则的全部价值在于「**下次不用再问一遍**」，
    而「又得问一遍」的触发条件恰好是**任一件掉了** ——
    判据脚本被删（没人拦）、登记件被删（没真源）、AGENTS.md 那几句被改没（下个会话看不到）。
    三件缺一，规则事实上失效，而**在此之前没有任何东西会红**。

    ★ **委托，不抄第二份**：直接跑 `kb/l8/check_source_readonly.py --json` 取它的结论。
      在这边重写一遍「哪些令牌该在 AGENTS.md 里」＝ 同一件事两份真源，必然有一天对不上。
      ⇒ 本条的职责只有一句：**让每日巡检能发现那把尺子红了**。
    """
    checker = os.path.join(ROOT, "kb", "l8", "check_source_readonly.py")
    registry = os.path.join(ROOT, "kb", "l7", "registry", "source-readonly.yaml")
    if not os.path.exists(checker):
        return False, f"判据脚本不在：{checker}", \
            "飞书只读源没人拦了 ⇒ 恢复 kb/l8/check_source_readonly.py（或明确废弃这条规则）"
    if not os.path.exists(registry):
        return False, f"登记件不在：{registry}", \
            "判据读不到真源会直接崩 ⇒ 恢复 kb/l7/registry/source-readonly.yaml"
    rc, out, err = sh([sys.executable, checker, "--json"], timeout=90)
    try:
        j = json.loads(out)
    except Exception:                                           # noqa: BLE001
        return False, f"判据跑不通（rc={rc}）：{(err or out)[:200]}", \
            "跑 python3 kb/l8/check_source_readonly.py 看它为什么起不来"
    rows = {r["check"]: r for r in (j.get("results") or [])}
    # ★ 本条**只核漂移该管的那件事**：AGENTS.md 那两句声明还在不在（= C2）＋ 判据/登记件在位。
    #   其余各条（C3 活代码、C6 文档、C7 --doc 闸门、C8 实现缺口…）是**判据自己的业务**，
    #   由人跑判据看；在这里一并判红会把「AGENTS.md 漂移」这个标签贴在别的事上 —— 语义错配。
    #   （2026-10-10 实测就踩了：C8 报「PRD §2.2 排除项还没落地」的缺口，把本条带红了。）
    c2 = next((r for k, r in rows.items() if k.startswith("C2")), None)
    red_others = [k for k, r in rows.items() if not r.get("ok") and not k.startswith("C2")]
    d = {"判据可跑": True, "检查项": len(rows),
         "C2 声明在位": bool(c2 and c2.get("ok")),
         "判据侧其它红项（不归本条管）": red_others or "无"}
    if c2 is None:
        return False, json.dumps(d, ensure_ascii=False), \
            "判据里找不到 C2（AGENTS.md 声明核验）—— 判据可能被改坏了，去跑一遍看"
    if c2.get("ok"):
        return True, json.dumps(d, ensure_ascii=False), None
    return False, json.dumps(d, ensure_ascii=False), (
        "AGENTS.md 里「飞书只读源 / 身份口径」那几句声明掉了 ⇒ 下个会话又会从头问一遍。\n"
        "        跑 `python3 kb/l8/check_source_readonly.py` 看 C2 缺哪几个锚，补回 ~/.dsh/AGENTS.md。\n"
        "        ⚠️ 判据侧的其它红项（活代码写源 C3 / 任务拆解写源 C6 / --doc 闸门 C7 / 实现缺口 C8）\n"
        "        **不由本条负责**，但值得单独跑一次判据看。")


CLAIMS = [
    ("agents_exists", "AGENTS.md 存在且可读", c_agents_exists),
    ("shouheng_section", "AGENTS.md 写明「守衡在本机」的关键要素", c_shouheng_section),
    ("shouheng_local", "真值：守衡运行时确实在本机且已装载", c_shouheng_actually_local),
    ("kbapi_decision_owner", "AGENTS.md「API 已补判定主体」与代码一致", c_kbapi_decision_owner),
    ("bridge_gates", "AGENTS.md「桥仍两样都缺」与代码一致", c_bridge_gates),
    ("layers_skills", "AGENTS.md 指向的 layers.yaml 仍是可用真源", c_layers_skills),
    ("key_scripts", "AGENTS.md「执行纪律」点名的脚本全部在位", c_key_scripts),
    ("watchdog", "就绪巡检任务在位（告警机制没静默失效）", c_watchdog_installed),
    ("credential_horizon", "令牌寿命陷阱的防护在位（脚本判断 + AGENTS.md 结论 + 排期一致）",
     c_credential_horizon),
    ("verified_stamp", "AGENTS.md 有「已核于」日期戳且未超 30 天", c_verified_stamp),
    ("source_readonly", "飞书只读源 + 身份口径在位（判据/登记件/AGENTS.md 三件齐）",
     c_source_readonly),
]


def selftest():
    """假红体检的自证：**合法变体不许红 ＋ 真坏必须红**。

    这一批（2026-10-12）修的全是**假红**——「把正确改动判成故障」。
    所以每条判据都要喂两个方向：
      · **合法变体**：措辞/排版/位置的**等价改写**，事实没变 ⇒ **不许红**；
      · **真坏**：事实真没了 ⇒ **必须红**。
    只喂后者的自证，用一个恒红的判据就能骗过去。
    """
    import tempfile
    import time as _t

    def _tmp(text, suffix=".md"):
        fh = tempfile.NamedTemporaryFile("w", suffix=suffix, delete=False, encoding="utf-8")
        fh.write(text)
        fh.close()
        return fh.name

    today = _t.strftime("%Y-%m-%d")
    cases = []   # (名字, 判据返回值的第一位, 期望)

    # ── 6 layers_skills（上一批修的假红：只认行内列表）──────────────────────
    _L = ("layers:\n- layer: L4\n  skill: [kb-a]\n- layer: L5\n  skill: [kb-b]\n"
          "- layer: L6\n  skill: [kb-c]\n- layer: L7\n  skill: [kb-d]\n")
    _LBLOCK = ("layers:\n- layer: L4\n  skill:\n  - kb-a\n- layer: L5\n  skill:\n  - kb-b\n"
               "- layer: L6\n  skill:\n  - kb-c\n- layer: L7\n  skill:\n  - kb-d\n")
    _LSINGLE = ("layers:\n- layer: L4\n  skill: kb-a\n- layer: L5\n  skill: kb-b\n"
                "- layer: L6\n  skill: kb-c\n- layer: L7\n  skill: kb-d\n")
    for nm, body, want in (("行内列表（合法）", _L, True),
                           ("块序列（合法·2026-10-12 改成的形状）", _LBLOCK, True),
                           ("单值（合法）", _LSINGLE, True),
                           ("真缺一层 L7（必红）",
                            "layers:\n- layer: L4\n  skill: [kb-a]\n- layer: L5\n  skill: [kb-b]\n"
                            "- layer: L6\n  skill: [kb-c]\n- layer: L7\n  engine: [x]\n", False)):
        f = _tmp(body, ".yaml")
        cases.append(("layers_skills / " + nm, c_layers_skills(f)[0], want))
        os.unlink(f)

    # ── 2 shouheng_section：措辞等价改写不许红 ───────────────────────────────
    _base = "守衡 com.shouheng.lark 跑在 audit_multi_content 的 tools 下"
    for nm, body, want in (
            ("「本机」写法（合法）", _base + "，就在本机。", True),
            ("「本地」写法（合法·同义）", _base + "，就在本地。", True),
            ("真缺 launchd 标签（必红）", "守衡跑在 audit_multi_content，就在本机。", False),
            ("真缺工作目录（必红）", "守衡 com.shouheng.lark 跑在本机。", False),
            ("真缺定性（必红）", "守衡 com.shouheng.lark 在 audit_multi_content 的 tools 下。", False)):
        cases.append(("shouheng_section / " + nm, c_shouheng_section(body)[0], want))

    # ── 7 key_scripts：从文档派生（改名＋同步文档不许红）──────────────────────
    _real = "见 kb/l8/workflow_smoke.py 与 kb/l5/matcher.py 与 kb/l8/regression_gate.py " \
            "与 kb/l8/regression_run.py 与 kb/l8/check_source_readonly.py"
    for nm, body, want in (
            ("真路径 ×5（合法）", _real, True),
            ("文档被清空 / 抽不出（必红）", "本库没有任何脚本。", False),
            ("名字打错（必红）", _real + " 与 kb/l8/does_not_exist_at_all.py", False)):
        cases.append(("key_scripts / " + nm, c_key_scripts(body)[0], want))

    # ── 9 verified_stamp：分隔符等价写法不许红；超期必须红 ───────────────────
    _now = _t.mktime(_t.strptime(today, "%Y-%m-%d")) + 3600
    for nm, body, now, want in (
            ("半角空格（合法）", f"> 已核于 {today}", _now, True),
            ("全角冒号（合法·等价）", f"> 已核于：{today}", _now, True),
            ("斜杠日期（合法·等价）", "> 已核于 " + today.replace("-", "/"), _now, True),
            ("45 天前（必红）", "> 已核于 2026-08-20", _now, False),
            ("没有标记（必红）", "本文件没有日期戳", _now, False)):
        cases.append(("verified_stamp / " + nm, c_verified_stamp(body, now=now)[0], want))

    # ── 3 shouheng_actually_local：路径**从 plist 派生**（搬家＋同步 plist 不许红）──
    _bad_plist = _tmp('<?xml version="1.0"?><plist version="1.0"><dict>'
                      "<key>ProgramArguments</key><array><string>/bin/bash</string>"
                      "<string>/nonexistent/run_shouheng.sh</string></array>"
                      "<key>WorkingDirectory</key><string>/nonexistent</string>"
                      "</dict></plist>", ".plist")
    cases.append(("shouheng_local / plist 指向不存在的脚本（必红）",
                  c_shouheng_actually_local(plist_path=_bad_plist, probe=True)[0], False))
    cases.append(("shouheng_local / 真 plist ＋ 已装载（合法）",
                  c_shouheng_actually_local(probe=True)[0], True))
    cases.append(("shouheng_local / 真 plist ＋ **未装载**（必红）",
                  c_shouheng_actually_local(probe=False)[0], False))
    os.unlink(_bad_plist)

    # ── credential_horizon 的**排期指纹**（2026-10-16 加：日更改周更时补的判据）──────
    #   为什么单独自证：那一条改成了「周期与时刻一起比」，而**周期写错时原先照样绿**
    #   （只比 HH:MM ⇒ 「每周日 03:30」==  「每天 03:30」）。下面最后两例就是它的反向对照。
    _sched_daily = {"Hour": 3, "Minute": 30}
    _sched_sun = {"Weekday": 0, "Hour": 3, "Minute": 30}
    cases += [
        ("sched_key / 每天 03:30（合法）", sched_key(_sched_daily), ("03:30", ())),
        ("sched_key / 每周日 03:30（合法）", sched_key(_sched_sun), ("03:30", (0,))),
        ("sched_key / `Weekday=7` 也是周日（合法变体，不许红）",
         sched_key({"Weekday": 7, "Hour": 3, "Minute": 30}), ("03:30", (0,))),
        ("sched_key / 读不出（缺 Hour）⇒ None", sched_key({"Minute": 30}), None),
        ("doc_sched_key / `**每天 03:30**`（合法）",
         doc_sched_key("| 更新间隔 | **7 天**（每天 03:30） |"), ("03:30", ())),
        ("doc_sched_key / `**每周日 03:30**`（合法）",
         doc_sched_key("| 更新间隔 | **7 天**（**每周日 03:30**） |"), ("03:30", (0,))),
        ("doc_sched_key / 文档没写排期 ⇒ None（**不许**当成「没写就算过」）",
         doc_sched_key("守衡跑在本机"), None),
        # ★★ 反向对照：**周期不同 ⇒ 指纹必须不同**。
        #   （拆掉周期比对、退回只比 HH:MM ⇒ 这一例精确变红。）
        ("★ 反向对照：一份写「每周日」、一份写「每天」⇒ **指纹不许相等**",
         sched_key(_sched_sun) == sched_key(_sched_daily), False),
        ("★ 反向对照：文档写「每天」而排期是「每周日」⇒ **不许相等**",
         doc_sched_key("每隔一天 03:30 与每天 03:30") == sched_key(_sched_sun), False),
    ]

    ok = True
    for name, got, want in cases:
        good = (got == want)
        ok = ok and good
        print(f"  {'✅' if good else '❌'} {name}：判 {'过' if got else '红'}"
              f"（期望 {'过' if want else '红'}）")
    print(f"\n结论：{'✅ 合法变体不红、真坏必红（%d 例）' % len(cases) if ok else '❌ 有例不符'}")
    return 0 if ok else 3


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--selftest", action="store_true", help="只跑本条判据的反向对照")
    a = ap.parse_args()
    if getattr(a, "selftest", False):
        return selftest()

    rows = []
    for cid, desc, fn in CLAIMS:
        try:
            ok, detail, fix = fn()
        except Exception as exc:                                # noqa: BLE001
            ok, detail, fix = False, f"检查本身出错：{exc!r}", None
        rows.append({"id": cid, "claim": desc, "ok": bool(ok),
                     "truth": detail, "fix": fix})

    drift = [r for r in rows if not r["ok"]]
    out = {"agents_md": AGENTS, "checked_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
           "claims": len(rows), "drift": len(drift), "rows": rows}

    if a.json:
        print(json.dumps(out, ensure_ascii=False, indent=1))
    else:
        print(f"AGENTS.md 漂移自检 @ {out['checked_at']}  ⇒  "
              f"{'✅ 无漂移' if not drift else f'❌ {len(drift)} 条漂移'}")
        for r in rows:
            print(f"  {'✅' if r['ok'] else '❌'} [{r['id']}] {r['claim']}")
            if not r["ok"]:
                print(f"        真值：{str(r['truth'])[:300]}")
                if r["fix"]:
                    print(f"        修法：{r['fix']}")
    return 0 if not drift else 3


if __name__ == "__main__":
    sys.exit(main())
