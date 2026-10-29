#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
预先量出文章里每张图片的固有宽高，写进 blog/image-sizes.json。

为什么需要这个
--------------
原样 HTML 文章在 iframe 里渲染，父页面要把 iframe 撑到内容全高。
高度只能从 iframe 内部量出来 —— 而图片没加载时高度是 0，
浏览器要等它下载完才知道该占多高。于是一篇 50 图的文章会让
iframe 高度陆陆续续跳 50 次才稳定，读者脚下一直在动。

有了这份尺寸清单，运行时可以在图片**还没下载**时就用
`aspect-ratio` 把准确高度撑出来，高度一次算准，图片再异步慢慢加载。

用法
----
    python3 scripts/image_sizes.py [--root DIR] [--blog-dir blog]

输出 blog/image-sizes.json：

    {
      "version": 1,
      "文章名.html": {"images/pic.jpg": [1200, 800], ...},
      ...
    }

设计取舍
--------
* **只记录能确定的**：文件读不到、没有 PIL、图片是外链或 base64，
  一律跳过。宁可少一条让浏览器自然布局，也不写错尺寸把版面撑歪。
* **按文章分桶**：打开一篇文章只查它自己的那几条，不用遍历全站。
* **纯标准库 + PIL（可选）**：没有 PIL 就输出空清单，站点退化为
  当前行为（高度陆续收敛），不会报错、不会坏。
* **幂等**：重复跑结果一致，CI 里可以放心每次执行。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# 匹配 <img ...> 里的 src。HTML 属性顺序不定，所以先抓整个标签再找 src。
IMG_TAG = re.compile(r"<img\b[^>]*>", re.I)
SRC_ATTR = re.compile(r'\bsrc\s*=\s*("([^"]*)"|\'([^\']*)\'|([^\s>]+))', re.I)
# 外链 / 内联数据 / 锚点：这些量不到本地文件，跳过
SKIP_SRC = re.compile(r"^(?:https?:)?//|^data:|^#|^about:", re.I)


def image_size(path: Path):
    """返回 (w, h)；读不到或没有解码器就返回 None。"""
    try:
        from PIL import Image  # 只在真正要量的时候导入
    except Exception:
        return None
    try:
        with Image.open(path) as im:
            return int(im.width), int(im.height)
    except Exception:
        return None


def resolve(blog: Path, article: Path, src: str):
    """把文章里的 src 解析成本地文件路径。

    站点约定：文章内的相对路径以 blog/ 为根（见 index.html 的 rewriteAssets）。
    因此 "images/a.jpg" 和 "../images/a.jpg" 都指向 blog/images/a.jpg。
    """
    src = src.split("?", 1)[0].split("#", 1)[0].strip()
    if not src or SKIP_SRC.match(src):
        return None
    # 站内绝对路径（以 / 开头）：取 blog/ 之后的相对部分
    if src.startswith("/"):
        rel = src.lstrip("/")
        for prefix in ("blog/", ""):
            p = blog / (rel[len(prefix):] if prefix else rel)
            if p.is_file() and prefix:
                return p
        p = blog / rel
        return p if p.is_file() else None
    # 相对路径：先按文章所在目录找，再退到 blog/ 根。
    # 另外作者常把路径写成 "blog/images/x.jpg"（带目录名前缀），
    # 这里剥掉前缀再试一次，否则会静默漏掉整篇文章的图。
    cands = [src]
    if src.startswith("blog/"):
        cands.append(src[len("blog/"):])
    for c in cands:
        for base in (article.parent, blog):
            try:
                p = (base / c).resolve()
            except Exception:
                continue
            if p.is_file():
                return p
    return None


def scan(blog: Path):
    out: dict[str, dict[str, list[int]]] = {}
    for article in sorted(blog.glob("*.html")):
        try:
            html = article.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        sizes: dict[str, list[int]] = {}
        for tag in IMG_TAG.finditer(html):
            m = SRC_ATTR.search(tag.group(0))
            if not m:
                continue
            src = m.group(2) or m.group(3) or m.group(4) or ""
            p = resolve(blog, article, src)
            if not p:
                continue
            wh = image_size(p)
            if not wh or wh[0] <= 0 or wh[1] <= 0:
                continue
            # 用文章里书写的原始 src 作键，运行时才能原样对上
            key = src.split("?", 1)[0].split("#", 1)[0].strip()
            sizes[key] = list(wh)
        if sizes:
            out[article.name] = sizes
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    ap.add_argument("--blog-dir", default="blog")
    args = ap.parse_args()

    root = args.root.resolve()
    blog = root / args.blog_dir
    if not blog.is_dir():
        print(f"跳过：{blog} 不存在", file=sys.stderr)
        return

    data = scan(blog)
    payload = {"version": 1, "articles": data}
    out = blog / "image-sizes.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n",
                   encoding="utf-8")

    n = sum(len(v) for v in data.values())
    pil = True
    try:
        import PIL  # noqa: F401
    except Exception:
        pil = False
    note = "" if pil else "（未安装 Pillow，输出为空清单；站点会退化为加载后收敛）"
    print(f"Created {out}: {len(data)} articles, {n} image sizes{note}")


if __name__ == "__main__":
    main()
