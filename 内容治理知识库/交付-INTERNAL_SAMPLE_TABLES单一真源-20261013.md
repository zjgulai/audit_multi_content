# 交付 · `INTERNAL_SAMPLE_TABLES` 搬到单一真源

日期 2026-10-13 ｜ 承接 `quality_flags.py` 头部那条**登记**（「各写了一份 … 本次未一并合并」）

---

## 0. 一句话

`GOOD_QUALITY_FLAGS` 那类病的**第二个、也是最后一个标本**已清掉：
名单搬进唯一真源 `kb/l8/internal_sample_tables.py`，L3 与 L6 **都从它取**。
**行为与输出逐字未变**（14,649 个单元全量复核过，§3）。

---

## 1. 为什么做它

`kb/l8/quality_flags.py` 头部**当时就登记了**：

> 「`INTERNAL_SAMPLE_TABLES` 现在在 `l3_scope.py` 与 `.work/l6_scope_lib.py` 里**各写了一份**，
>   是同一类病的现成标本 —— 本次**未一并合并**，登记在案。」

那次没合并的理由是「不在本次范围内」。本单就是把它补上：**同一个常量两处定义 ⇒ 迟早分叉**，
而这正是 10/12 那次 FDA/自有站事故（1,005 条真内容被挡）的成因。

**今天两处内容其实相同**（都是那三张表），所以它**不是一个正在出血的 bug**，
是一个**结构上的隐患**——照实说，本单的价值在「把这条路堵死」，不在「修一个现象」。

---

## 2. 改了什么

| # | 文件 | 改动 |
|---|---|---|
| ① | **`kb/l8/internal_sample_tables.py`（新增）** | 唯一真源：`INTERNAL_SAMPLE_TABLES` ＋ `CONTAINER_NOT_A_SOURCE_TABLE` ＋ `--selftest`（8 例） |
| ② | `kb/l8/l3_scope.py` | 字面量 → `_load_internal_sample_tables()`（**读不到就抛**，不静默降级） |
| ③ | `kb/.work/l6_scope_lib.py` | 字面量 → 同一真源（顺带去掉一处重复的 `import importlib.util`） |

### 2.1 ★ 为什么类型必须是 **tuple**（这条最容易被"顺手改好"）

L3 的拒绝理由**把本常量逐字插进文案**：

```python
f"internal_sample 只收 {INTERNAL_SAMPLE_TABLES}，本单元来自「{_src_table_of(u)}」 …"
```

- tuple ⇒ 印 `('专家修订汇总表', '负面样本', '正面和负面样本')`（**现状**）
- frozenset ⇒ 印 `frozenset({'负面样本', …})`（**另一串**）

⇒ 改成 frozenset（哪怕更"防改")**就是改输出**。本库规矩：**输出格式不因重构而变**。
判据 ②③ 钉住它，变异 M4 证明它**真的会红**。

### 2.2 ★★ 合并的是**名单**，不是**判据** —— 这是本单必须说清的一句

两个消费端的**守卫不同**，且**今天仍会给出不同结论**：

| | L3（`l3_scope.py`） | L6（`l6_scope_lib.py`） |
|---|---|---|
| 判据 | `_src_table_of(u) not in 名单` | `_is_bitable and _tbl not in 名单` |
| 附加守卫 | **无** | **只对 `bitable__` 来源生效** |
| 实测结论（14,649 单元） | `out_of_scope_table` = **386** | = **0** |

**这一段没有被我"顺手统一"** —— 它会改 L3 蒸馏输出 ⇒ 改评审链召回。
已单独出件：`核定-internal_sample两把尺子的386条分歧-20261013.md`。**等你裁。**

---

## 3. 零行为变更的证明（这是本单的安全底线）

对 `kb/l2/units.jsonl` **全部 14,649 个单元**，改前/改后逐条比：

```
L3 全量排除分布（改前 = 改后，逐格相同）：
    None 6793 ｜ metadata 5574 ｜ quality_flag 1661 ｜ **out_of_scope_table 386**
    ｜ metadata_unknown_field 127 ｜ out_of_scope_kb 55 ｜ rule_eligible_false 53

L6 那道 internal_sample 判据：{None: 1512}      （改前 = 改后）

★ 拒绝理由**文案**：386 条逐条与「旧字面量 tuple」的渲染比对 ⇒ **不一致 0 条**
```

外加：两消费端取到的是**同一份源文件**（`A is B` 为 False 只是两次 `exec_module` 的两个模块实例，
与 `quality_flags.py` 那次同一个现象 —— **被 import 的源文件只有一份**）。

---

## 4. 判据与**反向对照**

`kb/l8/internal_sample_tables.py --selftest` **8/8**：① 名单内容 ② 类型是 tuple
③ 反向对照（证明 set 会渲染成另一串）④ 非空 ⑤ 容器表名不在名单里
**⑥[L3]/⑥[L6] 两个消费端都不许再写字面量**（只看赋值行、不看注释，避免假红）
⑦ 反向对照（证明 ⑥ 不是空转）。

**变异自证 `kb/.work/mutate_internal_sample_tables.py` —— 5/5 精确变红**：

```
M1 L3 又把名单写回字面量        ⇒ ⑥[L3]
M2 L6 又把名单写回字面量        ⇒ ⑥[L6]
M3 真源里悄悄少一张表          ⇒ ①
M4 把 tuple 改成 set           ⇒ ②、③
M5 把「材料收集」塞进名单      ⇒ ①、⑤
收尾复跑：8/8（证明还原干净）
```
原地改 ＋ `finally` 必还原 ＋ 还原后回读复算 sha（不符即退出码 4）。

---

## 5. 尺子（落盘后现跑）

| 尺子 | 结果 |
|---|---|
| `workflow_smoke.py`（六段契约） | **0** ✅ |
| `l0_gate` … `l7_gate`（八层） | 全 **0** ✅ |
| `envelope_census.py` / `check_source_readonly.py` | **0 / 0** ✅ |
| `kb/l7/review-engine/tests/` 全量 | **101 passed** ✅ |
| `internal_sample_tables.py --selftest` | **8/8** ✅ |

---

## 6. 本单**没有**做的

- **没有**统一 L3 / L6 的**守卫**（那是另一件，见 §2.2 与那份核定件）
- **没有**改名单内容（一字未改）
- **没有**改任何输出文案（§3 已证）
- **没有**碰守衡侧任何东西（本次改动对守衡可见输出**零影响**：L3 没跑、产品没变）
