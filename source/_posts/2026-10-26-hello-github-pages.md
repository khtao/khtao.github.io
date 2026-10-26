---
title: 你好，自动化的 GitHub Pages 博客
categories: 教程
tags:
  - Hexo
  - GitHub Pages
  - 自动化
description: 这套博客从写文章到上线完全不用碰命令行：在线写完点保存，GitHub Actions 自动构建发布。
abbrlink: dcd67292
date: 2026-10-26 00:00:00
updated: 2026-10-26 00:00:00
---

## 这套博客是怎么工作的

```text
浏览器里的编辑器  →  写入 .md 文件（一次 Git 提交）
                 →  GitHub Actions 自动触发
                 →  Hexo 重新生成整站
                 →  发布到 https://xxx.github.io
```

你唯一要做的事，就是**打开 `/admin/` 写文章，然后点保存**。剩下的构建、发布、刷新 sitemap 全部自动完成。

## 三步开始写第一篇

1. 打开 `https://你的域名/admin/`，填入仓库信息和 Token 连接仓库
2. 点「新建文章」，填写标题、分类、标签，写正文（图片可直接粘贴）
3. 点「保存并发布」，等 30～90 秒刷新博客首页即可看到

## 写 Markdown 的小提示

- 图片直接 **Ctrl+V 粘贴** 或拖进来，会自动上传到仓库并生成 CDN 链接
- `Ctrl / ⌘ + S` 是保存快捷键
- 标签用英文逗号分隔；摘要留空则自动截取正文开头

> 这是一篇示例文章，登录编辑器后可以直接删掉它。
