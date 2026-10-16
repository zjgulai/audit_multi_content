# L8 第一步 · 打包链路全貌（从分层新库到「读得出来」）

> 本文件只写**链路事实**：谁生成、写到哪里、谁读、读的哪一步会失败。每个结论都带
> 命令或代码位置，可直接复现。实验数据在 `kb/l8/diagnosis.md`，修复动作在
> `kb/l8/runs/20260923-1540.report.md`。
>
> 查证时间：2026-09-23 15:0x–15:4x（本机时间）。

## 一、链路一张图

```
权威库（工作区）                       打包脚本                        装载位（宿主库视图）
kb/l0 素材 / kb/l1 单元 /              kb/.work/gen-host-library.py    ~/.dsh/Momcozy知识库/
kb/l2 units / kb/l3 候选规则     ──▶   （python3，30399 字节）     ──▶  3_措辞表达库/L1-facts/*.md  (453)
kb/l4 条款号 / kb/l5 P0 匹配                                               3_措辞表达库/L2-concepts/*.md (56)
                                                                           _meta/collections.yaml
                                                                           _meta/derivation.json
                                                                           _meta/DERIVED.md
                                                                                 │
                                                                                 ▼
加载器（模块）                         工具层（插件）                    消费侧
~/.dsh/plugins/dsh-kb/lib/kb.js  ──▶  lib/index.js 暴露 kb_* 工具  ──▶  Agent（kb_search/kb_read…）
（187286 字节）                        （library/collections/search/        工作台镜像器 127.0.0.1:4317
                                        read/ingest/check/guide）          （另一条通道，见第四节）
```

## 二、打包脚本这一节：写盘动作在哪几行

| 位置 | 事实 |
|---|---|
| `kb/.work/gen-host-library.py` | 30399 字节，python3，mtime 2026-09-23 14:54，owner 是「工作台同步」那条工作流 |
| 写 .md 的调用点 | `with open(path, "w", encoding="utf-8") as handle: handle.write(text)`（433–434 行） |
| 写 `_meta` 三件 | `collections.yaml` / `DERIVED.md` / `derivation.json` 用同样的 `open(...,"w")` 写法 |
| 清目录 | 第 188 行 `shutil.rmtree(out_root)` —— 输出目录会被整体重建（不是增量写） |
| 输出位置 | `--out` 参数；被清空前指向 `~/.dsh/Momcozy知识库`，2026-09-23 15:01 起该工作流改指 `kb/.work/hostlib` |
| 生成时间线（实测 mtime） | 装载位那批 md 生成于 14:40 之后；`kb/.work/hostlib/` 生成于 15:01 |

**关键**：这个脚本的写盘方式是 **python 的 `open(...,"w")`**。在这台机器上，这就是
E001 × 509 的源头（见 `diagnosis.md` E3：python / perl 写 `.md` → 落盘成 4096 字节信封）。

## 三、装载位这一节：装进去的是什么

- 目录：`~/.dsh/Momcozy知识库/`，唯一子库 `3_措辞表达库`（登记在 `_meta/collections.yaml`，
  `entry_count: 509`，`status: derived`）。
- 条目：509 个 md = `L1-facts/` 453 + `L2-concepts/` 56。文件名 = 规则 id（`cg-r-<16 位十六进制>.md`）。
- 每个条目的 frontmatter（29 个键，实测样例 `cg-r-00277648c524fe69.md`）：
  `id / title / collection / tier / topic / kind / summary / owner / evidence_level / data_level /
  sensitivity_level / half_life_days / created_at / valid_until / asks / not_proves / forbidden /
  related / source{kind,ref,fingerprint,captured_at} / rule_id / article_no / rule_code /
  p_level / risk_level / rule_status / verification / support_count / form / kb_type / derived_from`
- 正文是给人看的规则卡：条款号 → 规则原文（照抄新库）→ 命中表达 → 判为违规的依据 →
  处理方式/合规替代 → 派生视图声明。
- 迁移前全库文件数 **512** = 509 条目 + `_meta/{collections.yaml, derivation.json, DERIVED.md}`
  （没有 `manifest.json`）。

## 四、加载器这一节：读的每一跳（`~/.dsh/plugins/dsh-kb/lib/kb.js`）

1. **库根从哪来**：不是硬编码，来自 profile 里 dsh-kb 的 `config.root`（`lib/index.js:32`
   `root: z.string().required()`；`:50` `const root = resolve(config.root)`）。
   取不到时的原话是「请检查 profile 补丁里 dsh-kb 的 config.root」（`index.js:58–59`）。
   本机实测该 root = `~/.dsh/Momcozy知识库`（修复前 `kb_check` 就是在这里数出 509 条的）。
2. **扫哪些文件**：`walk()` 递归遍历目录，跳过 `NON_ENTRY_DIRS`
   （`intake-log / candidates / pending / tests / baseline / _meta`，第 57 行），
   并且按文件名排除 `INDEX.md / SKILL.md / README.md`；只收 `.md`。
   → 所以 `_meta/GUIDE.md`、`_meta/DERIVED.md`、根目录 `README.md` **都不是条目**，
   不会报 E001（本次六项验收里 E001=0 就是在这些文件都在盘上的情况下测到的）。
3. **读一个条目**：`loadEntry()` = `readFileSync(absPath, "utf8")` → `splitFrontmatter(raw)`。
   **失败就发生在这两行之间**。
4. **切 frontmatter 的判据**（`splitFrontmatter`，kb.js:768）：
   `/^---\r?\n([\s\S]*?)\r?\n---\r?\n?([\s\S]*)$/`。
   切不出来 → `{ meta: null, body: text }` → `check()` 里判 `E001 缺 frontmatter`。
5. **校验链**：`meta=null` 之后，三件套 `TRIPLET = ["data_level","valid_until","owner"]`（第 63 行）
   非空率直接掉到 0.00（E014），`kb_class`（T4）走 W040 汇总，孤岛率变 1.00，
   `collections()` 里 509 条全落到「未归库」，`search()` 一条也匹配不到。
6. **工具层**（`lib/index.js`）把上面这些包成 `kb_guide / kb_collections / kb_search / kb_read /
   kb_ingest / kb_check` 六个工具。消费侧（Agent、工作台）只跟这六个打交道。

## 五、故障现象 → 机制（一句话版）

`gen-host-library.py` 用 python 通道写 `.md` → 落盘成 **4096 字节信封**
（首字节 `88 7d 1c ?? 3a 05 f6 03`）→ 加载器（Electron 运行时，载入了
`/usr/local/.trld/lib/libtr_monitor_enc.dylib`）`readFileSync` 读到的是**信封**而不是明文
→ `^---` 不匹配 → `meta = null` → **E001 × 509** → 三件套 0.00 / 孤岛率 1.00 /
`kb_collections` 显示「0 条 + 未归库 509」/ `kb_search` 全 0 命中。

而 `cat`、`python3`、`head` 这些通道读到的是**明文**，所以从文件本身看「内容完整、
frontmatter 规范」——两边看的是同一 inode 的两种视图（E1/E4 原始数据见 `diagnosis.md`）。

## 六、本批改了链路的哪一节、哪几节没动

| 环节 | 本批动作 |
|---|---|
| 装载位 `.md` 的**写通道** | **改了**：改由加载器同一运行时（Electron/node）的 `fs.writeFileSync` 明文写盘，写完逐文件读回断言，失败 `/bin/cp` 兜底（`kb/l8/repack_write.mjs`） |
| 打包脚本 `gen-host-library.py` | **未改**（他人正在跑的在产脚本；本批改用「等价于脚本输出的载荷 + 明文写通道」达成同一效果，脚本侧改造列入遗留问题 1） |
| 加载器代码 | **未改**（未走 R3；因此没有 `portable:false` / `requires_runtime_decode:true` 标记） |
| profile 的 `config.root` | **未改**（仍指 `~/.dsh/Momcozy知识库`） |
| `kb/l0`…`kb/l6` | **未改**（自检 1 逐项核对过） |
| `_meta/` 补充件 | **新增**：`kb-classes.yaml`、`GUIDE.md`、`acceptance.yaml`（前两个非 md 内容、第三个非 md；`DERIVED.md` 按迁出前原文逐字写回） |

## 七、复现命令（按顺序）

```bash
cd <工作区>/知识库/内容治理
DSH="/Applications/DSH Desktop.app.pre-lute-20260907-111753/Contents/MacOS/DSH Desktop"

# 1 读装载位：逻辑内容 + dd 原始字节存档（不改任何文件）
python3 kb/l8/repack_read.py 20260923-1520
# 2 明文重写：node 通道 + 逐文件读回断言（失败自动 cp 兜底）
ELECTRON_RUN_AS_NODE=1 "$DSH" kb/l8/repack_write.mjs \
  --payload kb/l8/repack_payload.json --root ~/.dsh/Momcozy知识库 \
  --out kb/l8/repack_write_report.json --add-class 措辞表达库
# 3 _meta 补充件（含 kb-classes.yaml / GUIDE.md / acceptance.yaml）
ELECTRON_RUN_AS_NODE=1 "$DSH" kb/l8/repack_write.mjs --payload kb/l8/meta_payload.json \
  --root ~/.dsh/Momcozy知识库 --out kb/l8/repack_write_meta_report.json
# 4 六项回环验收（读侧一律走加载器本体）
python3 kb/l8/roundtrip_check.py 20260923-1540
```
