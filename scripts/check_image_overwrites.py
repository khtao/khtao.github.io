#!/usr/bin/env python3
"""Prevent tracked blog images from being replaced under their old URLs.

Run against the base commit *before* the build modifies source JPEG files:
    python3 scripts/check_image_overwrites.py --base <base-sha>

The check notices same-path binary changes. To replace an image intentionally,
upload it under a NEW name and update only the relevant article's reference.
"""
from __future__ import annotations

import argparse
import subprocess
import sys

ASSET_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.gif', '.webp', '.avif', '.svg')


def changes(base: str, head: str = 'HEAD') -> list[str]:
    if not base or set(base) == {'0'}:
        return []  # first push / no parent commit
    subprocess.run(['git', 'cat-file', '-e', f'{base}^{{commit}}'],
                   check=True, stdout=subprocess.DEVNULL)
    diff = subprocess.check_output([
        'git', 'diff', '--no-renames', '--name-only', '-z', '--diff-filter=M',
        base, head, '--', 'blog/images/'
    ])
    return [x.decode('utf-8', 'surrogateescape') for x in diff.split(b'\x00')
            if x and x.decode('utf-8', 'surrogateescape').lower().endswith(ASSET_EXTENSIONS)]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--base', required=True, help='PR base SHA or push event.before SHA')
    ap.add_argument('--head', default='HEAD')
    args = ap.parse_args(argv)
    try:
        conflicts = changes(args.base, args.head)
    except (subprocess.CalledProcessError, OSError) as exc:
        print(f'无法检查图片变更，请确认已检出完整 Git 历史：{exc}', file=sys.stderr)
        return 2
    if conflicts:
        print('发现已有图片被同路径替换：', file=sys.stderr)
        for path in conflicts:
            print(f'  - {path}', file=sys.stderr)
        print('为保护旧文章，请改用新的图片路径，更新目标文章引用。'
              '推荐执行：python3 scripts/import_images.py --article <文章标识> <新图片>', file=sys.stderr)
        return 1
    print('图片保护检查通过：没有同路径覆盖已有图片。')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
