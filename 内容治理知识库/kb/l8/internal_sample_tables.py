#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""`INTERNAL_SAMPLE_TABLES` —— **唯一真源**（`internal_sample` 只收哪几张表）。

为什么要单独一个文件
────────────────────────────────────────────────────────────────
本库因「**同一个常量两份定义**」栽过不止一次。最近一次是 `GOOD_QUALITY_FLAGS`：
L6 有放行白名单、L3 没有 ⇒ 同一个 flag 两层读成相反的意思 ⇒ **1,005 条真内容被挡在 L3 之外**
（含 10/19–10/23 行 #1 要的 FDA 8/8、自有站 714/934）。那次把它搬到了 `kb/l8/quality_flags.py`，
两个消费者都 import **同一份**。

当时就登记了**同一类病的第二个标本**（`quality_flags.py` 头部逐字）：
    「`INTERNAL_SAMPLE_TABLES` 现在在 `l3_scope.py` 与 `.work/l6_scope_lib.py` 里**各写了一份**，
      是同一类病的现成标本 —— 本次**未一并合并**，登记在案。」
**本文件就是那次登记的落地。**

消费端（两个，都必须 import 本文件，不许再写第二份）
────────────────────────────────────────────────────────────────
| 消费者 | 路径 | 判据形状 |
|---|---|---|
| L3 蒸馏范围 | `kb/l8/l3_scope.py` | `_src_table_of(u) not in INTERNAL_SAMPLE_TABLES`（**无附加守卫**） |
| L6 召回范围 | `kb/.work/l6_scope_lib.py` | `_is_bitable and _tbl not in INTERNAL_SAMPLE_TABLES`（**只对 bitable 来源生效**） |

★★ **合并的是「名单」，不是「判据」—— 两者今天仍会给出不同结论，这是已知且未裁的**
────────────────────────────────────────────────────────────────
2026-10-13 实测（`kb/l2/units.jsonl` 全 14,649 个单元，`internal_sample` 1,512 个）：

    L3 判 out_of_scope_table = **386**    ← `_src_table_of()` 取到「材料收集」等容器名
    L6 判 out_of_scope_table = **0**      ← 那 386 条 resource_id 是 wiki__ / url__ / base__，
                                            不满足 `_is_bitable` ⇒ L6 不做这道判

两者**都是有意的**：L6 的守卫是 2026-10-08 为修一个**假阳性**加的
（`_is_bitable` 那处注释逐字：「只有 bitable 资源才有『表』可判；其他来源不做这道判」，
当时实测被误挡的真内容含 `Meta近期在投文案`（2,114 字）共 341 条）。
而 L3 那侧**没有跟改** ⇒ **同一份名单、两种结论**。

⇒ **本文件只统一名单，不擅自统一判据。** 要不要让 L3 也加那道守卫，
**会改变 L3 蒸馏输出 ⇒ 改变评审链召回**，属需要单独裁定的变更
（登记见 `核定-internal_sample两把尺子的386条分歧-20261013.md`）。**别顺手改。**

边界
────────────────────────────────────────────────────────────────
· 本模块**只有常量**，不读文件、不写文件、无副作用。
· ★ 类型必须是 **tuple**，**不许**改成 set / frozenset：L3 的拒绝理由里把本常量
  **逐字插进文案**（`f"internal_sample 只收 {INTERNAL_SAMPLE_TABLES}，…"`），
  换类型会**改掉那句输出**（tuple 印 `('a', 'b')`，frozenset 印 `frozenset({'a', …})`）。
  本库规矩：**输出格式不因重构而变**。

用法
────────────────────────────────────────────────────────────────
    python3 kb/l8/internal_sample_tables.py --selftest
"""
import sys

# ── 名单本体（唯一一份）────────────────────────────────────────────────
INTERNAL_SAMPLE_TABLES = ("专家修订汇总表", "负面样本", "正面和负面样本")

#: ★ 明确**不属于**来源表的名字（写出来，免得下次有人「顺手补一条」）。
#: 「材料收集」是**容器表**（wiki/url 那批的 `heading_path` / `field_name` 落到它身上），
#: 不是本单元的来源表 —— 把它加进名单，等于**悄悄放弃** L3 那 386 条的判别。
CONTAINER_NOT_A_SOURCE_TABLE = ("材料收集",)

__all__ = ["INTERNAL_SAMPLE_TABLES", "CONTAINER_NOT_A_SOURCE_TABLE", "load_single_source"]


def load_single_source():
    """给**别的目录**下的消费者（如 `kb/.work/l6_scope_lib.py`）用的自证入口。

    返回本模块的 `INTERNAL_SAMPLE_TABLES`。调用方拿到后**不许再定义自己的副本** ——
    这正是本文件存在的理由。
    """
    return INTERNAL_SAMPLE_TABLES


def _selftest():
    """自证 + 反向对照（①–⑤）。**判据自己必须能红**，否则它就是注释。"""
    ok = fail = 0
    fails = []

    def ck(name, cond, detail=""):
        nonlocal ok, fail
        if cond:
            ok += 1
        else:
            fail += 1
            fails.append("%s %s" % (name, detail))

    # ① 名单内容 = 登记的那三张表（改名单必须同时改这里，否则本条红）
    ck("① 名单 = 登记的三张表",
       set(INTERNAL_SAMPLE_TABLES) == {"专家修订汇总表", "负面样本", "正面和负面样本"},
       "得到 %r" % (INTERNAL_SAMPLE_TABLES,))

    # ② 类型必须是 tuple —— L3 的拒绝理由逐字插值它，换类型 = 改输出
    ck("② 类型是 tuple（L3 报错文案依赖它的渲染）",
       isinstance(INTERNAL_SAMPLE_TABLES, tuple),
       "得到 %s" % type(INTERNAL_SAMPLE_TABLES).__name__)

    # ③ 反向对照：**证明②不是恒真** —— 换成 set 时，渲染出来的文案确实不同
    as_tuple = "%s" % (INTERNAL_SAMPLE_TABLES,)
    as_set = "%s" % (set(INTERNAL_SAMPLE_TABLES),)
    ck("③ 反向对照：set 会渲染成另一串（证明②在守真东西）",
       as_tuple != as_set, "两者相同 ⇒ ② 是空转")

    # ④ 不许为空 —— 空了就是「internal_sample 一条都不收」，静默把整库挡掉
    ck("④ 名单非空", len(INTERNAL_SAMPLE_TABLES) > 0, "")

    # ⑤ ★ 容器表名不许进名单（「材料收集」实测 357 条落在它上面；加进来=悄悄放弃判别）
    ck("⑤ 容器表名不在名单里",
       not (set(CONTAINER_NOT_A_SOURCE_TABLE) & set(INTERNAL_SAMPLE_TABLES)),
       "交叠 %r" % (set(CONTAINER_NOT_A_SOURCE_TABLE) & set(INTERNAL_SAMPLE_TABLES),))

    # ⑥ ★★ **防止再分叉**：两个消费端都**不许**再把名单写成字面量。
    #    判据只看「赋值给本常量的那一行是不是一个字面量集合」，**不看注释**——
    #    两边注释里都保留着「原字面量是什么」的留痕，扫全文会假红。
    import os as _os
    import re as _re
    _root = _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
    _pat = _re.compile(r'^\s*INTERNAL_SAMPLE_TABLES\s*=\s*[\(\[\{]', _re.M)
    _consumers = [("L3", _os.path.join(_root, "kb", "l8", "l3_scope.py")),
                  ("L6", _os.path.join(_root, "kb", ".work", "l6_scope_lib.py"))]
    for _tag, _p in _consumers:
        _src = open(_p, encoding="utf-8").read() if _os.path.exists(_p) else ""
        ck("⑥[%s] 不再自写字面量（只 import 本文件）" % _tag,
           bool(_src) and not _pat.search(_src),
           "在 %s 里仍看到 `INTERNAL_SAMPLE_TABLES = <字面量>`" % _p)

    # ⑦ ★ 反向对照：证明 ⑥ 的判据**不是恒真** —— 喂一段真会造成分叉的源码，必须命中
    _fake = 'INTERNAL_SAMPLE_TABLES = {"专家修订汇总表", "负面样本", "正面和负面样本"}'
    ck("⑦ 反向对照：⑥ 的判据能认出真分叉", bool(_pat.search(_fake)),
       "判据对 %r 没反应 ⇒ ⑥ 是空转" % _fake)

    print("internal_sample_tables --selftest：%d/%d" % (ok, ok + fail))
    for x in fails:
        print("  ✗", x)
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    print(__doc__)
    raise SystemExit(0)
