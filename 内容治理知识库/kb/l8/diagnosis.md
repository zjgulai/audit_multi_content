# L8 第二步 · 四个实验：差异在写通道还是读通道

> 现象：装载位 509 个 md「内容完整、frontmatter 规范」，但加载器读到 `meta = null`
> → **E001 × 509** → 三件套完整率 0.00 / 孤岛率 1.00 / `kb_collections` 显示
> 「`3_措辞表达库`｜0 条」+「未归库 509」/ `kb_search` 全 0 命中。
>
> 结论先说：**差异在写通道（.md 的落盘形态），并由读通道的进程身份决定谁看得见**。
> 不是文件坏了，不是 frontmatter 写错了，也不是时序竞态。下面四组实验是原始数据。
>
> 全部实验在 2026-09-23 14:5x–15:2x 于本机执行；`<DSH>` =
> `/Applications/DSH Desktop.app.pre-lute-20260907-111753/Contents/MacOS/DSH Desktop`（v24.18.1 的 Electron 运行时，
> **与被测加载器同一运行时**，用 `ELECTRON_RUN_AS_NODE=1` 以 node 模式跑）。

## E1 · 同一个文件、同一条路径，两条通道看到两份不同的字节

对象：`~/.dsh/Momcozy知识库/3_措辞表达库/L1-facts/cg-r-00277648c524fe69.md`

| 读取者 | 看到的字节数 | 首 16 字节 | 加载器 frontmatter 正则 |
|---|---|---|---|
| `stat -f %z`（bash） | 8047 | — | — |
| `ls -l` | 8047 | — | — |
| `<DSH>` node `statSync` | 8047 | — | — |
| `<DSH>` node `readFileSync` | **8047** | `88 7d 1c bb 3a 05 f6 03 be eb 3c b9 bc 6a 84 b4` | **不匹配（false）** |
| `python3` `os.stat` + `open().read()` | **3951** | `2d 2d 2d 0a`（`---\n`） | 匹配 |
| ChatGPT.app node（v24.21.0） | 3951 | `2d 2d 2d 0a` | 匹配 |

- python 与 ChatGPT-node 读到的 3951 字节**逐字节相同**（sha16 `c2f6b2cd9099f2a0`）。
- 两条通道指向**同一个 inode 65787955 / dev 16777230**；`blocks=16` 只与 4116/8047 这类
  体积自洽，与 3951 不自洽 —— 即**盘上的物理形态就是带前缀的那份**。
- 结论：**不是同一份字节被两个进程读出了不同结果，而是同一条路径下并存着两种视图**；
  加载器所在的进程读到的那份，`^---` 判不出来。

## E2 · 它不是压缩容器，是 4096 字节前缀信封

对同一批文件做 magic 判定，全部不匹配：

| 容器 | magic | 命中 |
|---|---|---|
| gzip | `1f 8b` | ✗ |
| zstd | `28 b5 2f fd` | ✗ |
| zip | `50 4b` | ✗ |
| bzip2 | `42 5a 68` | ✗ |
| xz | `fd 37 7a 58 5a 00` | ✗ |
| lz4 | `04 22 4d 18` | ✗ |

- 全库 510 个 md 逐个量体积：`physical − logical` 的取值集合 = **{4096}**（510/510）。
- 把 `dd` 取到的「原始字节」与 python 读到的明文逐字节比对：**510/510 完全相同**
  （`kb/l8/envelope_manifest.json` 的 `raw_sha16 == logical_sha16`）。
- 结论：信封 = **4096 字节前缀 + 完整原文**；原文没被改、没被截断、也没被加密成不可逆的东西。
  所以「内容完整」这个观感是对的 —— 只是有一层前缀，而且**只有部分读者看得见它**。

## E3 · 写通道矩阵（同一段内容，写到不同后缀/用不同写者）

同一段内容（20 字节 / 29 字节两种），写到 `~/.dsh/**` 与 `/tmp` 两处（结论与路径无关）：

| 写者 | 落盘后 python 看到 | `ls -l` 看到 | `dd` 首字节 | 判定 |
|---|---|---|---|---|
| `bash` 内建重定向 `printf > f.md` | 20 | 20 | `2d 2d` | 明文 ✓ |
| `/bin/echo > f.md` | 20 | 20 | `2d 2d` | 明文 ✓ |
| `/bin/cp src f.md` | 20 | 20 | `2d 2d` | 明文 ✓ |
| `<DSH>` node `fs.writeFileSync` | 20 | 20 | `2d 2d` | 明文 ✓ |
| ChatGPT node `fs.writeFileSync` | 20 | 20 | `2d 2d` | 明文 ✓ |
| `python3` `open(...,"w")`（buffered） | 20 | **4116** | `88 7d 1c ??` | **信封 ✗** |
| `python3` `os.write`（unbuffered） | 20 | **4116** | `88 7d 1c ??` | **信封 ✗** |
| `python3 -u`（unbuffered） | 20 | **4116** | `88 7d 1c ??` | **信封 ✗** |
| `perl -e 'print'` | 20 | **4116** | `88 7d 1c ??` | **信封 ✗** |
| `env -i python3`（清空环境变量） | 20 | **4116** | `88 7d 1c ??` | **信封 ✗** |
| `launchctl submit … /usr/bin/python3`（**脱离 DSH 进程树**） | 20 | **4116** | `88 7d 1c ??` | **信封 ✗** |
| `launchctl submit … /bin/sh -c "printf … >"` | 24 | 24 | `2d 2d` | 明文 ✓ |

**扩展名矩阵**（同一段内容，全部由 python 写）：

| 后缀 | 落盘后 `ls` 看到 | 判定 |
|---|---|---|
| `.md` | 4116 | **信封 ✗** |
| `.yaml` / `.json` / `.txt` / `.py` / `.log` | 20 | 明文 ✓ |

- `env -i` 与 launchd 两个实验排除了「环境变量注入」与「DSH 进程特有」两种解释：
  **不是 DSH 专有现象，是平台侧的、按后缀生效的写通道行为。**
- 结论：**`.md` 是被封装的唯一后缀；决定落盘形态的是写者**。python / perl 写的 `.md`
  才变信封，node / `cp` / bash 重定向写的 `.md` 是明文。

## E4 · 读侧分组、稳定性，以及「谁在注入」

**读侧分组**（对同一对文件：python 写的 `race.md` vs node 写的 `node-race.md`）：

| 组 | 读取者 |
|---|---|
| 看到**明文** | `cat` / `head -c` / `tail -c` / `od` / `xxd` / `strings` / `python3` / `shasum` / `grep` / `awk` / `cp` / ChatGPT-node / `dd`（整文件） |
| 看到**信封** | `dd bs=8 count=1` / `wc -c` / `ls -l` / `stat -f %z` / **`<DSH>` Electron 运行时 `readFileSync` + `statSync`** |

**稳定性**（排除时序竞态）：对 `race.md` 每 0.5 秒采一次、连续 12 秒共 24 次：
`stat` 恒 4125、python 恒 29、`dd` 首字节恒 `88 7d 1c c9` —— 两种视图**并存且稳定**，
不是「写入未完成」或「缓存未刷」。

**注入证据**（谁把读通道分成了两半）：

```
$ lsof -p 39297 | grep -i trld
DSH\x20De 39297 lute txt REG 1,14 220624 /usr/local/.trld/lib/libtr_monitor_hook.dylib
DSH\x20De 39297 lute txt REG 1,14 528320 /usr/local/.trld/lib/libtr_monitor_enc.dylib
DSH\x20De 39297 lute txt REG 1,14 288048 /usr/local/.trld/lib/libtr_monitor_print.dylib
DSH\x20De 39297 lute txt REG 1,14 3523552 /usr/local/.trld/lib/libtr_monitor_im.dylib
DSH\x20De 39297 lute txt REG 1,14 1184272 /usr/local/.trld/lib/libtr_inject_comm.dylib
$ vmmap 39297 | grep libtr_monitor_enc      # 同上，已映射进地址空间
$ lsof -c Python | grep -i libtr            # 无输出：python 进程未载入
```

- 失败的那一侧（加载器所在进程）**确实载入了** `libtr_monitor_enc.dylib`；
  能看到明文的那一侧（python）**没有载入**。
- **事实与推断分开写**：
  - **事实**（可复现）：`.md` 的物理形态带 4096 字节前缀；读取结果按进程分成两组；
    Electron 运行时进程载入了上述注入库；写者决定 `.md` 是否带前缀。
  - **推断**（无法在本机取得厂商内部实现，只能标推断）：前缀由 `/usr/local/.trld`
    这套监控/加密代理施加，Electron 族进程被排除在「透明还原」之外。
    （另一条工作流的 `kb/.work/README-同步到工作台.md` 独立得出同一归因：
    它实测同一路径 `fs.statSync` 13084 而 python 8988，并点了 `com.trld.tr_daemon`
    与 `libtr_monitor_enc.dylib`。本批此前一度把嫌疑放在在装的卡巴斯基 sysext 上，
    现按证据更正为 trld —— 卡巴斯基 sysext 也在装，但没有证据链把它连到这个行为上。）
- 另外实测：**DSH 的 `write` 工具写 `.md` 是明文的**（92 字节，两条通道一致）——
  所以「DSH 写的就一定是信封」不成立，**写者身份要逐个测，不能按 App 猜**。
- `codesign` 标志全为 `0x0(none)`、无 `DYLD_*` 环境变量、无 FUSE 挂载 ——
  这几条排除了「加固运行时」「DYLD 注入」「用户态文件系统」三种常见解释。

## 五、四个实验合起来的结论

1. **写通道**决定落盘形态：python / perl 写 `.md` → 4096 字节信封；node / `cp` / bash 重定向 → 明文。
   本库的 509 条正是由 `kb/.work/gen-host-library.py` 的 `open(...,"w")` 写的，所以全部是信封。
2. **读通道**决定谁能看穿信封：加载器（Electron 运行时）看不到，于是
   `splitFrontmatter` 的 `^---` 失配 → `meta = null` → E001 × 509。
3. 两个通道看到的是**同一 inode 的两种视图**，各自稳定：所以「文件是好的」和
   「加载器读不到」可以同时为真，不矛盾。
4. 因此修复点在 **kb 侧的写通道**（本批采用 R1：用加载器同一运行时明文写盘，并保留
   R2 的写后读回断言），**不需要改加载器**，也就没有把 `portable:false` /
   `requires_runtime_decode:true` 这套技术债引进来。

## 六、查实过程中发现的、必须一起报告的外部变化

修复窗口内（15:01–15:02）**另一个工作流把装载位清空了**，只留一份 `README.md`（mtime
2026-09-23 15:02:15），并把派生视图搬到 `kb/.work/hostlib/` + python HTTP 服务
（`kb/.work/kb-hostlib-serve.py`，launchd 作业 `com.kb-hostlib`，`127.0.0.1:4508`）。
证据与影响：

```
$ ls -la ~/.dsh/Momcozy知识库          # 15:02 之后：只有 README.md
$ stat -f %z ~/.dsh/Momcozy知识库/README.md   → 5478（ls 侧）
$ python3 -c 'import os;print(os.stat("…/README.md").st_size)'  → 1382（python 侧，差 4096）
$ grep -n "已清空" kb/.work/README-同步到工作台.md
96:4. 旧位置 `~/.dsh/Momcozy知识库/` 已清空，只留一份 README 说明来龙去脉。
$ ls kb/.work/hostlib/3_措辞表达库/L1-facts/ | wc -l   → 453
$ <DSH> node -e 'fs.readFileSync("kb/.work/hostlib/…/cg-r-00277648c524fe69.md").length' → 8047（信封）
$ python3 -c 'open("kb/.work/hostlib/…/cg-r-00277648c524fe69.md").read()' → 3951（明文）
```

- 该迁移的**新位置对 node 仍然是信封**（8047 vs 3951）：那条 HTTP 通道救的是工作台
  （它派 python 服务取数），**救不了加载器**（加载器是 Electron 运行时，自己读盘）。
- 迁移前那 509 条的原文与本批归档完全一致（本批在清空前已把 510 个文件的逻辑内容与
  原始字节存档到 `kb/l8/repack_payload.json` 与 `kb/l8/_archive/enveloped-20260923-1520/`），
  因此恢复没有丢内容，且 509/509 正文逐字可比对。
- 两边对同一个目录做了相反的决定：该工作流认为这目录「不再走这条路」，本批按加载器
  `config.root` 的要求把它恢复成**加载器专用装载位**（工作台继续走 HTTP，互不干扰）。
  这条冲突连同它的处理方式记在 `runs/20260923-1540.report.md` 第八节遗留问题 6。

## 七、续修：R1「打包脚本改明文写盘」的收口实验（E5–E10）

第一轮的修复只做到「用 node 把装载位重写一遍」，**没有改打包脚本本身**（R1 的原意是改脚本）。
补做时先做了四组隔离实验，因为「怎么在 python 里写出明文」这件事有一个反直觉的坑。

### E5 · 「写 `.md.tmp` 再改名」看起来能绕过

同一份内容，三种写法（`/tmp/e5`，后又在新工作区目录复测，结论一致）：

| 写法 | node 侧 | python 侧 | 判定 |
|---|---|---|---|
| python 直接写 `.md` | 4191 | 95 | **信封 ✗** |
| python 写 `.md.tmp` 再 `os.replace` 成 `.md` | 95 | 95 | 明文 ✓ |
| python 写 `.txt` 再 `/bin/cp` 成 `.md` | 95 | 95 | 明文 ✓ |

→ 单看这一步，封装像是「按写入时的路径后缀」生效的，改名就能躲开。

### E6/E7 · 排除「目录」与「批量」两种解释

- 工作区 `kb/l8/_stage/e6/` 四种写法（python 直写 / tmp+改名 / cp / node）：
  **只有 python 直写是信封，其余三种明文** —— 与 `/tmp` 结论一致，**不是目录差异**。
- `kb/l8/_stage/e7/`：node 批量写 20 个 `.md` + python tmp+改名 + cp，**10 秒后 21/21 明文**
  —— **不是写入量差异**。

### E8 · 关键反证：把生成器的写调用全部 trace 一遍

给 `builtins.open` 与 `os.replace` 装 trace 后跑打补丁的生成器：

```
open w 次数 513：
  直接写 .md        0 次
  写 .md.tmp       510 次
os.replace         510 次
```

—— 我补的明文路径**确实生效**（一次都没直写 `.md`），但产出**仍然是信封**
（node 8077 / python 3981）；而同一趟里最后写的 `DERIVED.md` 当场是明文（2069/2069）、
**3 秒后变成信封**（6165/2069）。同目录再放 30 个 node 写的 md + 2.4 MB `manifest.json`，
12 秒后仍 30/30 明文 → 排除「manifest/内容触发」。

### E9 · 结论性对照

同一类目录（`kb/l8/_stage/e9-node509/`，含 3 个非 md 元数据件），**用 node 写** 509 条 + `DERIVED.md`：

```
node 写的 510 个 md（20 秒后）：信封 0 / 明文 510
写入器自带的读回断言：510/510 通过、cp 兜底 0 次
```

### E10 · 补丁端到端验证（R1 + R2）

按 E8/E9 的结论改脚本：`.md` **不再由 python 落盘**（连 `.md.tmp` 都不写），
改为收集载荷 → 交给 node 写盘 + 逐文件读回断言。沙箱重生成（不动装载位）：

```
$ python3 kb/.work/gen-host-library.py --out kb/l8/_stage/gen-verify-v3
[gen] 明文落盘：509 个 md（node 读回断言全部通过）
[gen] 明文落盘：1 个 md（node 读回断言全部通过）
→ 产出 510 个 md：信封 0 / 明文 510（15 秒后复测一致）

$ # 让加载器本体直接读生成器的产出
entries 509 / entries_fm_ok 509 / entries_id_ok 509 / entries_kb_class_ok 509
E001 0 / 三件套 1.00 / 健康分 75 / collections 3_措辞表达库 509
与装载位对账：正文一致 509/509；frontmatter 493 条完全一致、16 条漂移（summary 15、title 3）
```

**结论（R1 的准确表述）**：明文写盘这件事**不能靠「换个临时后缀再改名」在 python 里实现**
—— 异步的封装层随后会按路径把 `.md` 变成信封，实测 trace 证明了这一点。
可靠的做法只有一条：**`.md` 由非 python 的写者落盘**（node 实测最稳，`/bin/cp` 与 bash 重定向短窗口
内也成立），并且**读回断言必须由 node 做**（python 的读通道永远看得到明文，验不出这个问题）。
生成器现已按此实现，原文归档在 `kb/l8/_archive/gen-host-library.py.orig-294b16a0f404c977`。

### E11 · 并发工作流在同一文件上加了「第三轮补丁」之后，重新验证

写补丁期间，另一条工作流**在同一个脚本上**加了「l8 补丁（第三轮）：把派生字段对齐到加载器的 schema」
（`tier` 目录名与值拆开、`kind` 归属对齐、`source.kind` 落进枚举、指纹换形态、`related` 邻居生成、
补 `provenance`/`pii`/`corroborated_by`）。这正好是我列的遗留问题 3/4。核实结果：

| 项 | 我补丁的版本（38–39 KB） | 并发第三轮之后（53 KB，含我的补丁） |
|---|---|---|
| `.md` 落盘形态 | 510/510 明文 ✓ | **510/510 明文 ✓**（我的补丁未被覆盖） |
| 加载器直读产出：E001 | 0 | **0** |
| 健康分 / 孤岛率 | 75 / 1.00 | **100 / 0.00**（`related` 生效） |
| 字段级错误 | E002 1018、E005 509、E006 509、E021 509… | E002/E005/E006 归零，剩 E026 452、E021 56 |

**我自己补丁留下的一个洞（已补）**：写了 `kb_class` 却没产出枚举文件 `_meta/kb-classes.yaml`
—— 换个 `--out` 落新位置时，加载器枚举为空集，509 条全判 **E046**（实测）。
现在生成器会一并产出该文件（内容与 `KB_CLASS_BY_DIR` 同源，含四类枚举 + ranking + 三个开关）：

```
$ python3 kb/.work/gen-host-library.py --out kb/l8/_stage/gen-verify-v5
[gen] 明文落盘：509 个 md（node 读回断言全部通过）
[gen] 明文落盘：1 个 md（node 读回断言全部通过）
$ ls <out>/_meta → DERIVED.md collections.yaml derivation.json kb-classes.yaml manifest.json
$ 加载器直读产出：entries 509 / fm_ok 509 / kb_class_ok 509 / **E001 0** / **E046 0**
                 / 健康分 100 / 孤岛率 0.00 / collections 3_措辞表达库 509
```

**装载位没有被这一轮改动碰过**：它仍是本批逐字对账过的那份（六项回环复验见
`kb/l8/roundtrip_20260923-1522.json`）。装载位要不要跟随生成器的新形态（并发补丁改了
`tier`/`kind`/`derived_from` 等字段并连带影响正文），属于遗留问题 7 的决策，不在本批范围内。
