#!/usr/bin/env python3
"""OCR 缓存复用门槛（件0.5 修复点）。任何「按 sha256 命中缓存就复用」的路径都必须先过这里。"""
OCR_OK_VERSION = "vision-jxa-2.0"

def ocr_cache_reusable(entry, img_bytes=None):
    """返回 (ok, reason)。ok=False 时必须重跑 OCR，不得复用。"""
    if not entry:
        return False, "缓存条目不存在"
    if entry.get("sha256_state") not in (None, "full"):
        return False, f"缓存 sha256_state 非 full: {entry.get('sha256_state')}"
    ver = entry.get("ocr_version")
    if ver != OCR_OK_VERSION:
        return False, f"ocr_version != {OCR_OK_VERSION}（坏引擎产物）：{ver}"
    text = entry.get("ocr_text") or ""
    if "\uffff" in text:
        return False, "ocr_text 含 U+FFFF（坏引擎中文丢失标志）"
    if not text.strip() and (img_bytes or 0) > 4096:
        return False, f"ocr_text 为空但图片 {img_bytes} 字节 > 4096（疑似整图丢失）"
    return True, ""
