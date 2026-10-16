#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把一份 PDF 的每一页转成 PNG（kb-recall 分层索引导航用：遇 PDF 先转图再局部读/OCR）。

用法：
    python3 convert_pdf_to_images.py <input.pdf> <output_dir> [--max-dim 1000] [--dpi 200]

说明：
  - 输出目录不存在会自动创建（含多级父目录）。
  - 每页按 max_dim 等比缩放，保证宽高都不超过 max_dim。
  - pdf2image 需要系统里有 poppler（`pdftoppm`）；缺依赖 / 文件不存在 / 不是 PDF
    一律**报错退出并给出可执行的补救提示**，不静默降级、不产出空目录冒充成功。
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys

try:
    from pdf2image import convert_from_path
    from pdf2image.exceptions import PDFInfoNotInstalledError, PDFPageCountError, PDFSyntaxError
except ImportError as exc:  # pragma: no cover - 依赖缺失时的显式失败
    print(
        "错误：缺少依赖 pdf2image（%s）。\n"
        "补救：python3 -m pip install pdf2image，并确保系统已安装 poppler（提供 pdftoppm）。"
        % exc,
        file=sys.stderr,
    )
    sys.exit(2)


def convert(pdf_path: str, output_dir: str, max_dim: int = 1000, dpi: int = 200) -> int:
    """把 pdf_path 每页转成 output_dir/page_N.png；返回写出的页数。"""
    os.makedirs(output_dir, exist_ok=True)

    if not os.path.isfile(pdf_path):
        raise FileNotFoundError("输入 PDF 不存在或不是普通文件：%s" % pdf_path)
    if shutil.which("pdftoppm") is None:
        print(
            "警告：PATH 里找不到 pdftoppm（poppler）。pdf2image 通常会因此失败；"
            "macOS 可 `brew install poppler`，Debian/Ubuntu 可 `apt-get install poppler-utils`。",
            file=sys.stderr,
        )

    images = convert_from_path(pdf_path, dpi=dpi)
    if not images:
        raise ValueError("PDF 没有可转换的页面（0 页）：%s" % pdf_path)

    for i, image in enumerate(images):
        width, height = image.size
        if width > max_dim or height > max_dim:
            scale_factor = min(max_dim / width, max_dim / height)
            image = image.resize((int(width * scale_factor), int(height * scale_factor)))

        image_path = os.path.join(output_dir, "page_%d.png" % (i + 1))
        image.save(image_path)
        print("Saved page %d as %s (size: %s)" % (i + 1, image_path, image.size))

    print("Converted %d pages to PNG images" % len(images))
    return len(images)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="convert_pdf_to_images.py",
        description="把 PDF 每页转成 PNG（kb-recall 遇 PDF 时的前置步骤）。",
        epilog="示例：python3 convert_pdf_to_images.py doc.pdf ./out --max-dim 1200 --dpi 150",
    )
    p.add_argument("pdf", help="输入 PDF 路径")
    p.add_argument("output_dir", help="输出目录（不存在会自动创建）")
    p.add_argument("--max-dim", type=int, default=1000, help="单边最大像素，等比缩放（默认 1000）")
    p.add_argument("--dpi", type=int, default=200, help="渲染 DPI（默认 200）")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        convert(args.pdf, args.output_dir, max_dim=args.max_dim, dpi=args.dpi)
    except PDFInfoNotInstalledError:
        print("错误：找不到 poppler/pdftoppm。补救：brew install poppler 或 apt-get install poppler-utils。", file=sys.stderr)
        return 3
    except PDFSyntaxError as exc:
        print("错误：PDF 结构无法解析（文件损坏或不是 PDF）：%s" % exc, file=sys.stderr)
        return 4
    except PDFPageCountError as exc:
        print("错误：读不出 PDF 页数：%s" % exc, file=sys.stderr)
        return 5
    except (FileNotFoundError, ValueError) as exc:
        print("错误：%s" % exc, file=sys.stderr)
        return 6
    return 0


if __name__ == "__main__":
    sys.exit(main())
