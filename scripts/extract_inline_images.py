#!/usr/bin/env python3
"""Pull base64 images out of article sources and turn them into lazy-loadable files.

The problem this solves
-----------------------
An article can embed photos as `data:image/jpeg;base64,...`. It looks convenient
— the file is self-contained — but on the web it is the most expensive way to
ship an image:

  * base64 inflates bytes by ~33%, and the JPEG inside is already compressed,
    so gzip barely helps (measured: 2.69 MB source -> 2.03 MB gzipped).
  * the bytes sit inside the *HTML*, so they must all arrive before the page
    can render — no lazy loading, no WebP, no caching, no progressive display.
  * the same payload gets re-downloaded on every visit and re-stored in the
    visitor-side cache.

This script rewrites those inline images into ordinary files under
`blog/images/inline/`, named by content hash. After that the normal pipeline
applies: WebP twins get generated, the front end lazy-loads them, and the
article HTML shrinks by ~99%.

Idempotent & non-destructive
----------------------------
* File names use a SHA-256 prefix; an existing matching file is reused only
  after comparing the actual bytes. A prefix collision extends the digest.
* The rewrite is content-addressed: running it twice is a no-op because the
  second run finds no `data:` URI left.
* Sources are only rewritten when something actually changed, so a plain
  `git status` stays clean on repeat runs.
"""
from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import re
from pathlib import Path

# src="data:image/png;base64,...."  |  url(data:image/jpeg;base64,....)
# Also covers Markdown:  ![alt](data:image/png;base64,....)
DATA_URI = re.compile(
    r'(?P<prefix>(?:src|href)\s*=\s*["\']|\]\(\s*|url\(\s*["\']?)'
    r'data:image/(?P<fmt>png|jpeg|jpg|gif|webp)\s*;\s*base64\s*,'
    r'(?P<data>[A-Za-z0-9+/=]+)'
    r'(?P<suffix>["\']?\s*\)|["\'])?',
    re.IGNORECASE,
)
ARTICLE_EXT = {'.md', '.markdown', '.html', '.htm'}
EXT_BY_FMT = {'png': '.png', 'jpeg': '.jpg', 'jpg': '.jpg', 'gif': '.gif', 'webp': '.webp'}
# Below this size inlining is genuinely cheaper than a second request.
MIN_BYTES = 2048


def decode(chunk: str) -> bytes | None:
    """Tolerant base64 decode: tolerates missing padding and whitespace."""
    s = re.sub(r'\s+', '', chunk)
    pad = -len(s) % 4
    if pad:
        s += '=' * pad
    try:
        return base64.b64decode(s, validate=False)
    except (binascii.Error, ValueError):
        return None


def sniff_ext(raw: bytes, declared: str) -> str:
    """Trust the magic bytes over the declared MIME type."""
    if raw[:8] == b'\x89PNG\r\n\x1a\n':
        return '.png'
    if raw[:3] == b'\xff\xd8\xff':
        return '.jpg'
    if raw[:6] in (b'GIF87a', b'GIF89a'):
        return '.gif'
    if raw[:4] == b'RIFF' and raw[8:12] == b'WEBP':
        return '.webp'
    return EXT_BY_FMT.get(declared.lower(), '.jpg')


def process_file(path: Path, out_dir: Path, base: Path) -> tuple[int, int]:
    """Returns (number_of_images_extracted, bytes_removed_from_source)."""
    try:
        text = path.read_text(encoding='utf-8')
    except (OSError, UnicodeDecodeError):
        return 0, 0

    # 相对「文章目录」的路径：文章在 blog/ 根，图片在 blog/images/inline/，
    # 所以引用必须是 images/inline/xxx.jpg，而不是 inline/xxx.jpg。
    rel_dir = out_dir.relative_to(base).as_posix()
    removed = 0
    seen: dict[str, str] = {}

    def repl(m: re.Match) -> str:
        nonlocal removed
        raw = decode(m.group('data'))
        if raw is None or len(raw) < MIN_BYTES:
            return m.group(0)          # 不认识或太小，原样保留
        digest = hashlib.sha256(raw).hexdigest()
        ext = sniff_ext(raw, m.group('fmt'))
        out_dir.mkdir(parents=True, exist_ok=True)
        for chars in (12, 16, 24, 32, 64):
            basename = f'{digest[:chars]}{ext}'
            target = out_dir / basename
            try:
                # Atomic create: NEVER overwrite an existing (possibly edited)
                # image even if its truncated hash happens to match.
                with target.open('xb') as f:
                    f.write(raw)
                break
            except FileExistsError:
                if target.read_bytes() == raw:
                    break  # the identical photo has already been extracted
        else:
            raise RuntimeError(f'Cannot find collision-free filename for {path}')
        rel = f'{rel_dir}/{basename}'
        seen[basename] = ext
        removed += len(m.group('data'))
        return f'{m.group("prefix")}{rel}{m.group("suffix") or ""}'

    new_text = DATA_URI.sub(repl, text)
    if new_text != text:
        path.write_text(new_text, encoding='utf-8')
    return len(seen), removed


def scan(root: Path, blogdir: str, out_name: str = 'inline') -> dict:
    folder = root / blogdir
    if not folder.is_dir():
        print(f'No blog directory at {folder} - nothing to extract.')
        return {'files': 0, 'images': 0, 'bytesRemoved': 0}

    out_dir = folder / 'images' / out_name
    stats = {'files': 0, 'images': 0, 'bytesRemoved': 0}
    for path in sorted(folder.iterdir()):
        if not path.is_file() or path.suffix.lower() not in ARTICLE_EXT:
            continue
        if path.name.startswith(('_', '.')):
            continue
        n, removed = process_file(path, out_dir, folder)
        stats['files'] += 1
        if n:
            stats['images'] += n
            stats['bytesRemoved'] += removed
            print(f'  - {path.name}: 抽出 {n} 张内联图，'
                  f'源码减少 {removed/1024/1024:.2f}MB')

    # 空目录不留痕
    if out_dir.is_dir() and not any(out_dir.iterdir()):
        try:
            out_dir.rmdir()
        except OSError:
            pass
    return stats


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--root', type=Path,
                    default=Path(__file__).resolve().parent.parent)
    ap.add_argument('--blog-dir', default='blog')
    ap.add_argument('--out-name', default='inline')
    args = ap.parse_args()
    stats = scan(args.root.resolve(), args.blog_dir, args.out_name)
    if stats['images']:
        print(f'extract_inline_images: {stats["files"]} 篇文章扫描，'
              f'抽出 {stats["images"]} 张内联图，'
              f'源码总计减少 {stats["bytesRemoved"]/1024/1024:.2f}MB')
    else:
        print('extract_inline_images: 未发现内联图片（或已处理过）')


if __name__ == '__main__':
    main()
