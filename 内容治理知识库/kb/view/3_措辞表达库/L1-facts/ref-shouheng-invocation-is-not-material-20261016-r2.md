---
asks:
  - 已发出的评审报告要改时能不能新建文档
  - 作废一条发现该怎么处理（删还是留痕）
  - 改完之后要核什么
  - 改报告会不会把「报告链接」那一列搞断
collection: 3_措辞表达库
corroborated_by:
  - 飞书文档实测：revision 3 → 8、URL 不变（docs +update 的 str_replace×3 / block_delete×1 / append×1，每次回 document.revision_id）
  - 回读核对：docs +fetch 得 7 块（标题 / 结论行 2 处 / 1.【消费者安全】 / 2.【隐私】 / 更正说明三块）
  - 留底件 sha256[:16] 0305f3dbc257c2c9；上一条（本条取代的）ref-shouheng-invocation-is-not-material-20261016
created_at: 2026-10-16
data_level: L2
evidence_group: coordinate
evidence_level: L2
forbidden: 不许据本条判断某条素材能不能发；不许把「原地改」理解成可以随便改别人的文档 —— 只限我们自己投出去的评审件；不许用新建文档的方式“更正”投递件（会让已发链接成孤儿）；不许删除条目而不留更正说明；不许据本条声称飞书侧源可改（源仍然只读）。
half_life_days: 90
id: ref-shouheng-invocation-is-not-material-20261016-r2
kb_class: []
kind: fact
not_proves: 不能证明任何一条具体内容能不能发；不能替代 3_措辞表达库 的任何条款；不能证明所有投递件都能原地改（docx 可以；卡片、表行另说，没验过）；不能证明读过那份报告的人都看到了更正（他们可能只看了旧版本）。
owner: 刘华丽
pii:
  detected: false
  masked: false
  strategy: 未检出自然人信息：正文为文档操作与纪律，不含姓名、联系方式等个人数据；文中「Owner」为角色指称；如后续来源变化需重新判定
provenance:
  anchor: PMO/守衡-投递件的更正纪律-20261016.md#一/#二/#三
  confidence: 确定
sensitivity_level: L2
source:
  captured_at: 2026-10-16
  fingerprint: 0305f3dbc257c2c9
  kind: file
  ref: /Users/lute/project/audit_multi_content/PMO/守衡-投递件的更正纪律-20261016.md
summary: 投递件的更正纪律（2026-10-16 实操）：Owner 说「直接更新文档，链接不变」⇒ 对那份已发出的评审报告做原地修改 —— revision 3→8、URL 不变，步骤是 str_replace 改结论数 3→2、str_replace 顺延编号、block_delete 删作废项、append 补更正说明；四条纪律：原地改不新建（新建会让已发链接成孤儿、与表行「报告链接」不一致）、作废要留痕不静默删、数要跟着清单走、改完必须回读核对。本条取代上一条（那条写着「改不了、没动它」，已不成立）。
tier: L1
title: "[参考实现] 投递件的更正纪律（2026-10-16）：原地改、链接不变、作废留痕、数与清单一致、改完回读"
topic: 知识
valid_until: 2027-01-14
---

# 投递件的更正纪律（2026-10-16 实操一次）

> **本条是 `ref-shouheng-invocation-is-not-material-20261016` 的 r2**（supersedes）：
> 那份条目 §六.1 写着「已发出的报告改不了（投递件）—— **没动它**」，
> 而 Owner 当天说「**你直接更新文档，链接不变**」⇒ 那句话已不成立，原地改了。
> 留底件：`PMO/守衡-投递件的更正纪律-20261016.md`（2,792 字节，sha256 前 16 位 `0305f3dbc257c2c9`）。

---

## 一、同一条链接，原地改

报告 `https://momcozy-in.feishu.cn/docx/NKmbdpRrbooHFAxSNb2cIdlsnGe` ——
**revision 3 → 8，URL 一个字符没变**。

| # | 命令 | 改了什么 |
|---|---|---|
| ① | `str_replace` 共发现 **3** 处 → **2** 处 | 结论行必须与清单一致 |
| ②③ | `str_replace` 编号 `2.`→`1.`、`3.`→`2.` | 顺延 |
| ④ | `block_delete` 那条作废项 | 删掉「正文只带了中文账号名 @守衡」那一整块 |
| ⑤ | `append`（markdown） | 文末补**更正说明**：作废了哪条、为什么 |

回读成品（`docs +fetch`，7 块）：标题｜`【审查结论：REVIEW】共发现 2 处需人工确认。`｜
`1.【消费者安全】`｜`2.【隐私】`｜`附：更正说明（2026-10-16）`＋两段。

## 二、纪律（实操出来的四条）

1. **原地改，不许新建**：投递件的链接已经发出去了（群、表行「报告链接」列都指着它）；
   新建 = 旧链接成孤儿、表行与文档不一致（本仓有先例：复跑建新文档 ⇒ 新报告成孤儿）。
2. **作废要留痕、不许静默删**：删条让清单干净，但**必须**留更正说明 ——
   否则读到「2 处」的人不知道原来说过 3 处、也不知道为什么少了一条。
3. **数要跟着清单走**：删条那一刻就改结论行那个数（①与④是同一次改动，缺一个就自相矛盾）。
4. **改完必须回读**：逐块核（本次核了块数与文末三段）—— 与「判据不许只看接口 ok」同一条纪律。

## 三、没碰的

另两条一个字没动（含那条 FDA 外部依据与直链）；没改任何**飞书侧源**
（这是我们自己投出去的评审报告）；没动结论表那一行（「报告链接」仍指向同一份文档 ——
这正是「链接不变」带来的好处）。
