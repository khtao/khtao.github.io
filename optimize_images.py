#!/usr/bin/env python3
"""Compress blog images and emit WebP twins, without touching article sources.

Why this exists
---------------
The blog ships full-size camera JPEGs (a 50-photo travel post alone was ~11 MB).
Visitors pay that cost on every open because GitHub Pages serves each file as-is.
This script is the build-time half of the fix:

  * downscale oversized images (long edge capped at MAX_EDGE)
  * re-encode JPEG/PNG with sane quality + progressive encoding
  * write a `.webp` twin next to every raster image
  * record a manifest so the front end can swap in WebP with an automatic
    fallback, and so repeat builds stay idempotent (never re-compress twice)

The originals are kept as the fallback source: if a WebP is missing or a browser
cannot decode it, the page simply loads the JPEG it always loaded.

Safety
------
* Never edits article HTML/Markdown: the swap happens at runtime only.
* Skips anything already processed with the same settings (manifest keyed by
  content sha256), so image quality never degrades across repeated builds.
* Missing Pillow is not fatal: the build continues with the original images.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

try:
    from PIL import Image, ImageOps
except ImportError:  # Pillow absent -> degrade gracefully, do not break CI
    Image = None

MANIFEST = '.optimized.json'
# Current settings fingerprint: bump when defaults change so old entries expire.
SETTINGS_ID = 'v2'
# Photos in this blog are 1200x800; the layout never renders wider than ~760px,
# so capping at 1600 leaves real photos untouched and only tames future 4K uploads.
MAX_EDGE = 1600
JPEG_QUALITY = 80
# 76 is the knee of the curve: below it travel photos start to smear, above it
# the bytes grow fast with no visible gain.
WEBP_QUALITY = 76
MIN_SAVING = 0.02        # skip rewrite if it saves < 2% (already well encoded)
RASTER = {'.jpg', '.jpeg', '.png'}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def load_manifest(root: Path) -> dict:
    path = root / MANIFEST
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def save_manifest(root: Path, data: dict) -> None:
    (root / MANIFEST).write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + '\n',
        encoding='utf-8',
    )


def open_image(path: Path):
    img = Image.open(path)
    # Honour EXIF orientation so rotated photos do not come out sideways.
    try:
        img = ImageOps.exif_transpose(img)
    except Exception:
        pass
    return img


def needs_downscale(img) -> bool:
    return max(img.size) > MAX_EDGE


def process(path: Path, entry: dict) -> tuple[int, int]:
    """Return (bytes_before, bytes_after) for the JPEG/PNG itself."""
    before = path.stat().st_size
    with open_image(path) as img:
        if needs_downscale(img):
            img.thumbnail((MAX_EDGE, MAX_EDGE), Image.LANCZOS)
        target = img.convert('RGB') if path.suffix.lower() in {'.jpg', '.jpeg'} else img
        suffix = path.suffix.lower()

        if suffix in {'.jpg', '.jpeg'}:
            target.save(path, 'JPEG', quality=JPEG_QUALITY, optimize=True,
                        progressive=True, subsampling='4:2:0')
        else:
            target.save(path, optimize=True)

        # WebP twin: this is what modern browsers actually download.
        webp_path = path.with_suffix('.webp')
        target.save(webp_path, 'WEBP', quality=WEBP_QUALITY, method=5)

    after = path.stat().st_size
    entry['webp'] = webp_path.name
    try:
        entry['webpBytes'] = webp_path.stat().st_size
    except OSError:
        entry['webpBytes'] = 0
    return before, after


def scan(root: Path, blogdir: str, images_subdir: str = 'images') -> dict:
    folder = root / blogdir / images_subdir
    if Image is None:
        print('Pillow not installed - skipping image optimization (originals kept).')
        return {'skipped': 'pillow-missing', 'files': 0}
    if not folder.is_dir():
        print(f'No image directory at {folder} - nothing to optimize.')
        return {'skipped': 'no-directory', 'files': 0}

    manifest = load_manifest(folder)
    stats = {'files': 0, 'compressed': 0, 'webp': 0, 'bytesBefore': 0,
             'bytesAfter': 0, 'webpBytes': 0, 'skipped': 0}

    for path in sorted(folder.rglob('*')):
        if not path.is_file() or path.suffix.lower() not in RASTER:
            continue
        digest = sha256(path)
        rel = path.relative_to(folder).as_posix()
        prev = manifest.get(rel)
        # 只在「内容没变」且「WebP 孪生文件确实还在」时才跳过。
        # 少了后半个条件，一旦 .webp 被误删或被 .gitignore 排除，
        # 脚本会永远认为已处理过，WebP 就再也补不回来了。
        webp_ok = (path.with_suffix('.webp')).is_file()
        if isinstance(prev, dict) and prev.get('sha') == digest \
                and prev.get('settings') == SETTINGS_ID and webp_ok:
            stats['skipped'] += 1
            stats['webp'] += 1
            stats['bytesBefore'] += int(prev.get('bytes', 0))
            stats['bytesAfter'] += int(prev.get('bytes', 0))
            stats['webpBytes'] += int(prev.get('webpBytes', 0))
            stats['files'] += 1
            continue

        stats['files'] += 1
        before = path.stat().st_size
        entry = {'sha': digest, 'settings': SETTINGS_ID}
        try:
            b, a = process(path, entry)
        except Exception as exc:  # a single bad file must not fail the build
            print(f'  ! {rel}: {exc}')
            stats['skipped'] += 1
            continue

        # 记下的是**落盘后**文件的 sha：下次运行读到同一个 sha 就跳过，
        # 避免重复压缩导致画质一代代劣化。
        entry['bytes'] = path.stat().st_size
        entry['originalBytes'] = before
        entry['sha'] = sha256(path)
        manifest[rel] = entry
        stats['bytesBefore'] += b
        stats['bytesAfter'] += entry['bytes']
        stats['webpBytes'] += int(entry.get('webpBytes', 0))
        stats['compressed'] += 1
        stats['webp'] += 1
        saved = (1 - entry['bytes'] / b) * 100 if b else 0
        print(f'  - {rel}: {b/1024:.0f}KB -> {entry["bytes"]/1024:.0f}KB '
              f'({saved:.0f}% off), webp {entry.get("webpBytes", 0)/1024:.0f}KB')

    save_manifest(folder, manifest)
    return stats


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--root', type=Path,
                    default=Path(__file__).resolve().parent.parent)
    ap.add_argument('--blog-dir', default='blog')
    ap.add_argument('--images-dir', default='images')
    args = ap.parse_args()
    root = args.root.resolve()
    stats = scan(root, args.blog_dir, args.images_dir)

    if stats.get('skipped') in {'pillow-missing', 'no-directory'}:
        print(f'optimize_images: {stats["skipped"]}')
        return
    before = stats['bytesBefore'] / (1024 * 1024)
    after = stats['bytesAfter'] / (1024 * 1024)
    webp = stats['webpBytes'] / (1024 * 1024)
    print(f'optimize_images: {stats["files"]} images, {stats["compressed"]} re-encoded, '
          f'{stats["skipped"]} unchanged')
    print(f'  raster payload {before:.2f}MB -> {after:.2f}MB; '
          f'webp set {webp:.2f}MB (what browsers actually download)')


if __name__ == '__main__':
    main()
