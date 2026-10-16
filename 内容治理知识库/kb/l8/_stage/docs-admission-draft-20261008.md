# 文档准入判据 · 修订稿（待 Owner 批准后生效）

> 建立：2026-10-08（批次二现场）
> 状态：**草稿，未生效** —— 判据属"判定标准"，按纪律不许由 agent 自行改判据（同 `kb-l0-feishu` §8.2：自动化的应该是"发现"，不是"裁决"）。
> 触发它的实测：拉取前盘点发现，**待拉的 23 份飞书云文档里没有一份是合规依据**，全是达人横测草稿、活动反馈、任务表。

---

## 一、判据（四类，每份文档必须落一类）

| 类 | 名称 | 判据（可操作） | 处理 |
|---|---|---|---|
| **A** | **依据类** | 是**监管/平台政策**的原文，或是**医学/育儿权威出版物**——即：**合规判定可以直接引用它**来支撑或否决一句话 | ✅ **拉全文**（字节 + 正文），进 L1 |
| **B** | **业务素材** | 达人横测/草稿、活动物料与反馈、内部排期/任务表、他组对外资料 | ❌ **不拉**（**不进知识库**） |
| **C** | **源 Base 自身** | 就是 L0 的入口 Base / 源表 | ❌ 不拉（它已经在 L0 台账里） |
| **D** | **待权** | API 返 `131006`（资源级 ACL），bot 读不到 | ⏸ **挂牌**，等所有者在飞书加「守衡」为可阅读协作者 |

## 二、判据背后的理由（写清楚，供复核）

1. **本库用途是「给合规判定提供可引用依据」**，不是"飞书工作区镜像"。
2. **B 类拉进来是负资产**：达人草稿里恰恰塞满 `more milk` 这类待判词，会把 H02 这类精确规则**挤下召回榜**。
3. **这个库已为同类错误返工过一次** —— `kb/l6/SCOPE.txt` 原话：
   「被排除 83 条…**这不是"少收了知识"，是拒绝把网页全文当知识**」。
   ⇒「飞书里有什么就拉什么」与「把网页全文当知识」是同一类错误，只是换了源。

## 三、按此判据，当前 58 份飞书云文档的归类

### B 类（**不拉**）—— 12 份可读，全部落此

| 文档 | 类型 |
|---|---|
| Momcozy 横测 - tseringla5 - Draft V3 待审核 | docx |
| Momcozy横测 - emaza - Draft V2 | docx |
| Momcozy - mamajodieee - Draft V3 待审核 | docx |
| Momcozy 横测 - nikkirosecapulong31 - Draft V3待审核 | docx |
| Momcozy - julieandcorey - Draft V4待审核 | docx |
| 20260827_Babylist NY Event Rendering_Feedback | slides |
| 9.28 BBL NY Event Feedback | sheet ×2 |
| 【创意】需求排期与任务管理 | bitable |
| 喂养电器组对外资料汇总.xlsx | file |
| 【IMC跟进】W1再营销整合营销方案 | sheet |
| 婴幼儿品线_产品基础信息汇总 | sheet ← **待议**：产品基础信息可能属依据侧，需人判 |

### C 类（**不拉**）

| 文档 | 理由 |
|---|---|
| OGC内容生产与审核（bitable） | 就是 L0 入口 Base 本身 |
| 2 份无标题 docx（`Kts8dacy…` / `W2KodnZP…`） | 取不到标题即取不到内容，**不定性就不拉** |

### D 类（**挂牌待权**，7 份）

| 文档 | 错误 |
|---|---|
| `wiki/CUMOwJyo9iWNB7kfQMpc2LOSnAe` | `131006` 资源级 ACL |
| `wiki/EL1nw9zdyinX2iklXfLco216niM` | 同上 |
| `wiki/EsCdw2A7tiz67Rk8LgMce2TAnEh` | 同上 |
| `wiki/F44LwhbAqiD0TVkaNqYcXeF2n5P` | 同上 |
| `wiki/FerwwSi9WidD1SkqW7kcNXxnnEb` | 同上 |
| `wiki/KISzwvc8OifWk8kI5cBcTtU6n9g` | 同上 |
| `wiki/NtMrwG7m2iDNdik5wDKcwajSnJh` | 同上 |

**要人做什么**：找这 7 份的所有者，在飞书侧把「守衡」加成**可阅读协作者**。
**复开条件**：加完后重跑 `L8_AS=bot kb/kbpy l8/verify_l0_nonrecord.py <RUN>`，`forbidden/unreachable` 归零即可纳入。

### A 类（**拉全文**）

- 本地**已有正文**的 35 份（育儿/医学出版物，如 WHAT TO EXPECT、DK 科学育儿小百科、协和孕产大百科、澳洲政府 healthy growth）
- **政策/监管依据 32 条**（FDA / FTC / CDC / Meta / Google / Amazon 政策 / TikTok / MSD / dxy）→ 见 `verify_l0_urls.py` 的 URL 清单

## 四、未决口径（**要 Owner 拍板，agent 不代决**）

1. **版权**：A 类里那批是**正式出版物**（WHAT TO EXPECT、DK、协和…），把正文抽进库内并用于检索——
   属于什么性质？**这条比技术问题更要紧，未定之前我不批量拉。**
2. **`婴幼儿品线_产品基础信息汇总`** 归 A 还是 B？需要业务判。
