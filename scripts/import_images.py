#!/usr/bin/env python3
"""Import manually supplied blog images without overwriting existing assets.

Example:
    python3 scripts/import_images.py --article chenzhou-2026 ~/Pictures/01.jpg ~/Pictures/cover.jpg

Produces unique paths under blog/images/<article>/ and Markdown references.  Does not
modify published articles or existing files, and does not depend on Pillow.
"""
from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path

EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}


def safe_segment(value: str, *, fallback: str = 'image') -> str:
    """Use one safe filename component, with Unicode names supported."""
    if value in {'.', '..'} or '/' in value or '\\' in value:
        raise ValueError('名称必须是单个目录名，不能包含 /、\\ 或 ..')
    result = re.sub(r'[^\w-]+', '-', value, flags=re.UNICODE).strip('-_')[:64]
    if value and not result:
        return fallback
    return result or fallback


def import_one(src: Path, out_dir: Path) -> tuple[Path, bool]:
    if not src.is_file():
        raise FileNotFoundError(src)
    ext = src.suffix.lower()
    if ext not in EXTENSIONS:
        raise ValueError(f'不支持的图片类型：{src.name}（支持 JPG/PNG/GIF/WebP）')
    content = src.read_bytes()
    if not content:
        raise ValueError(f'图片为空：{src.name}')
    # Mix the extension into the digest so a JPEG and a PNG never compete for
    # the same *.webp output, even if someone gave them identical source bytes.
    digest = hashlib.sha256(ext.encode('ascii') + b'\x00' + content).hexdigest()
    stem = safe_segment(src.stem)
    for chars in (12, 16, 24, 32, 64):
        candidate = out_dir / f'{stem}-{digest[:chars]}{ext}'
        try:
            with candidate.open('xb') as f:  # atomic; existing file is NEVER truncated
                f.write(content)
            return candidate, True
        except FileExistsError:
            if candidate.read_bytes() == content:
                return candidate, False
            # Possible digest-prefix collision, or a manually modified file;
            # extend the digest rather than overwriting anything.
    raise RuntimeError(f'所有候选文件名均存在冲突：{src.name}')


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--article', required=True, help='文章标识，例如 chenzhou-2026')
    ap.add_argument('--root', type=Path, default=Path(__file__).resolve().parent.parent)
    ap.add_argument('files', type=Path, nargs='+', help='本地待上传图片')
    args = ap.parse_args(argv)
    try:
        article = safe_segment(args.article)
        output = args.root.resolve() / 'blog' / 'images' / article
        output.mkdir(parents=True, exist_ok=True)
        for src in args.files:
            imported, is_new = import_one(src, output)
            print(f'{"新增" if is_new else "复用"}: {imported.as_posix()}')
            print(f'  Markdown: ![{src.stem}](images/{article}/{imported.name})')
        return 0
    except (OSError, ValueError, RuntimeError) as exc:
        print(f'图片导入失败：{exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
