# 修复记录：canonical 注册表的 sha256 与实文件不符

- 时间：2026-09-30 16:03（本机）
- 触发：用户请求「canonical 注册表里记的 sha256 跟实际文件对不上，改成跟文件一致」
- 闸门依据：`kb-canonical-lookup` §5「canonical 注册表的 `sha256` 与实际文件不符 → 只报告，交 kb-check / kb-repair」
- 责任：L4 注册表（`kb/l4/registry/l4.json`），**未动任何数据文件、未动台账**

## 一、修的是什么

| 项 | 字段 | 修前 | 修后 |
|---|---|---|---|
| 被记录文件 | `inputs.candidates` | `kb/l3/candidates/rules.jsonl` | 未动 |
| 前缀字节数 | `inputs.base_bytes` | `1387673` | `2778734` |
| 前缀 sha256 | `inputs.base_sha256` | `416fb828fdfc790deb722ef7d3dbf286613605fc38effcb77d69e51791176de9` | `aa83d1f98bc86857254bfa4f908ebd6d1a869f868cb04970522d154f776b0dac` |

「修后」的值与 `shasum -a 256 kb/l3/candidates/rules.jsonl` 的实测值逐字符一致
（该文件共 1018 行；`inputs.base_lines` = 1018 = 全文件，故前缀哈希即整文件哈希）。

## 二、改动的边界（逐条可复算）

- 只改了 `inputs` 块两个键；顶层只有 `inputs` 变过；台账 `numbering.issued`（509 个号）与 `assignments` 与改前**逐键一致**。
- 未改数据：`kb/l3/candidates/rules.jsonl`、`kb/l4/canonical/*.jsonl` 一个字节未动。
- 回滚：`cp kb/l7/_backups/canonical-registry-sha256-20260930-160316/l4.registry.json.bak kb/l4/registry/l4.json`
  （回滚基线清单 `SHA256SUMS` 可用 `shasum -a 256 -c SHA256SUMS` 验）

## 三、修前为什么对不上（实测，不是推测）

修前那两个值**描述的是一个已经不存在的文件状态**，不是被谁篡改：

- 修前 `base_bytes` = 1387673 = 备份件
  `kb/l4/_pre-rebuild-20260930-1550/rules.candidates.jsonl.bak`（509 行）的字节数 + 1；
- 修前 `base_sha256` = 416fb828fdfc790d… 在现库任何文件里都不复现；
- 而线上文件当时已是 1018 行 / 2778734 字节（首 509 行 == 备份件，逐字节一致，
  哈希 54691908da8e8b59f4ca5e3affd6a565bc760b614258052cc0646a17c70cab1d）。

即：注册表停在了 509 行那一版的状态上。

## 四、没解决、留给人的一条

`kb/l3/candidates/rules.jsonl` 与 `kb/l4/registry/l4.json` 的 mtime **同为 2026-09-30 15:52:08**，
晚于 L4 运行记录 `run_id=20260930-1550` 的结束时刻；`kb/l4/runs/` 里**没有**对应的 run 记录。
本次只把注册表改成与文件一致，**没有**去解释这次写入是谁做的 —— 若要追责/追溯，
线索是：该时刻前后 `kb/.work/hostlib/` 也在批量写盘（同一批动作）。
