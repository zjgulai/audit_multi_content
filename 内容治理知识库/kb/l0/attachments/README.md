# kb/l0/attachments —— 飞书附件字节副本

- 来源：飞书 Base `GnRZbIuXraCzf0sGr2UcmZ62nfc` 表 `负面样本`（tbld8qE92YaY38Yz）字段 `图片素材`（fldnvxjaSr）
- 结构：`<表名>/<record_id>/<file_token>.png`（文件名=file_token，天然去重且可回源核对）
- 台账：`_MANIFEST.json`；`kb/l0/manifest.jsonl` 里对应行已升级为 `sha256_input=file_bytes`
- 用途：**留档与复算**（OCR 引擎/参数升级时可重跑，无需回源、不受权限变动影响）；审计时看原图
- 边界：**L1 及以上一律读 OCR 文本**，不要读这里的图片；本目录不是知识条目，不参与加载器扫描
- 落盘批：20261009-1240（304 张 / 888.3 MB）
