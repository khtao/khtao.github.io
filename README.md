# Khtao Blog · 免 API 的极简博客

页面：`index.html`；配置：`config.json`；文章：`blog/`；静态文章索引：`blog/index.json`。

**特点：无需写文章头信息，上传 `.md` / `.html` 即能自动提取标题、文章摘要、首次提交日期、最后修订日期。网站浏览器只请求自己的 GitHub Pages 静态文件，不再访问 GitHub Contents / Commits API，也不需要 Personal Access Token。**

## 部署（重要，只需设置一次）

1. 将本压缩包 `khtao-blog/` **内部的所有文件和目录**上传到 GitHub 仓库 `khtao/khtao.github.io` 的根目录（不要将 `khtao-blog` 整个文件夹套在外层）。务必保留 `.github/workflows/blog-index.yml` 和 `scripts/build_index.py`。
2. 仓库 **Settings → Pages → Build and deployment → Source** 选择 **GitHub Actions**。这一项很重要：新的工作流会在同一次部署中生成 `blog/index.json` 并发布静态站点，彻底避免浏览器 API 限流、索引过期及文章删除后错误。
3. 在仓库 **Actions** 页面，选择 **Build and deploy blog → Run workflow** 执行首次部署，也可以修改并提交一篇文章触发。
4. 工作流显示绿色成功后，打开 `https://khtao.github.io/#/`。如果页面短时间仍是旧版，请强制刷新一次（Ctrl+Shift+R）。

工作流无需自行填写 Token，不依赖额外 Python 包，也不需要把生成索引提交回仓库。其 Git 历史由 `actions/checkout` 的 `fetch-depth: 0` 获取。

## 发布、修改或删除文章

在 `blog/` 目录直接创建、上传、编辑或删除 `.md` / `.markdown` / `.html` / `.htm` 文件，然后提交。触发的 GitHub Actions 会**先从当前文章目录重新生成索引，再连同站点文件一起部署**。即使删除最后一篇文章，索引也会变成 `"files": []`，首页正常显示空状态。

仓库目录内允许有图片等其它资源（`blog/images/`），只有 `blog/` 顶层的文章文件会列入索引。以 `_` 或 `.` 开头的文件以及写有 `draft: true` 的草稿不会公开在列表中。

### 不需要任何头信息的 Markdown

```md
# 从零开始记录

这是第一段介绍内容。系统会用它作为摘要，截取至多 160 个字符。

## 正文
更多内容……
```

文件名可以为 `从零开始记录.md`；标题优先读取首个标题，然后是文件名，摘要优先读取首个有效段落。首次提交日期和最后修订日期由工作流读取 Git 历史，而不是浏览器实时请求 GitHub API。对首次提交或修改提交的时间，使用 Git **提交日期**（不是作者手写的电脑文件创建时间）。

### 可选手动覆盖（Markdown YAML 风格头信息）

```md
---
title: 自定义标题
date: 2026-10-26
updated: 2026-10-26
tags: [随笔, 技术]
summary: 自定义摘要
cover: images/cover.svg
---

文章正文……
```

- 标题：手写 `title` → 文章标题（Markdown 标题、HTML `<h1>` / `<title>` / `og:title`）→ 文件名
- 上传日期：手写 `date/created` → Git 第一次提交日期 → 文件名日期
- 修订日期：手写 `updated/modified` → Git 最后一次提交日期（如文章无提交记录则与创建日期相同）
- 摘要：手写 `summary` → HTML 描述标签 → 正文首段 → 正文截断
- 标签：可选，未写不产生分类；草稿使用 `draft: true`

### HTML 文件也可以不写元信息

```html
<h1>我的 HTML 文章</h1>
<p>这里是正文第一段，用于自动生成文章摘要。</p>
```

兼容旧格式 `<!-- title: 自定义标题 | tags: [HTML] | summary: 摘要 -->`，也能读取 HTML 的 `<title>`、`<meta name="description">`、`og:title`、首个段落。HTML 文章使用独立 iframe 保留原始样式。

## 本地预览

在项目根目录执行：

```bash
python3 scripts/build_index.py
python3 -m http.server 8000
```

浏览器打开 `http://localhost:8000/#/`，不要直接通过 `file://` 协议打开 `index.html`。

可以运行离线回归测试（只需 Python 标准库）：

```bash
python3 -m unittest discover -s tests -v
```如果本地没有 `.git` 提交历史，无头信息文章的日期会尽量使用文件名日期，部署到 GitHub 后自动读取真实提交日期。

## 常见问题

**删掉文章后还显示？** 确认对应的 Actions 部署已经完成，并刷新网页。GitHub Pages 的 CDN 更新可能有短暂延迟；网站每 5 分钟重新请求最新索引（附时间戳且禁用浏览器缓存）。

**首页提示「文章索引尚未就绪」？** 检查 Pages Source 是否已改为 **GitHub Actions**、工作流是否运行成功、站点根目录能否访问 `blog/index.json`。`blog/index.json` 必须包含 `files` 数组，允许是空数组。

**不会再看到 GitHub API 限额错误吗？** 新版客户端不访问该 API，因此匿名配额不再影响首页加载。GitHub Pages 或用户自身网络完全不可达时，任何静态网站都不能保证在线可用，博客会尽可能展示本机上次成功同步的内容并明确标注缓存状态。

**为什么仓库里的 `blog/index.json` 有时不是最新？** 发布时的索引在 Actions 内自动生成并作为同一次部署的文件上传；该生成文件不必提交回仓库。压缩包附带的初始索引仅用于本地预览和第一次上传时的兜底。

**如何改风格/文案？** 首页文案改 `config.json`；视觉主题、文章样式改 `index.html` 的 `<style>` 区域。文章改动会自动部署；`index.html` 或 `config.json` 修改也会触发部署。
