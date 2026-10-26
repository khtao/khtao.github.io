# khtao.github.io — 上传即发布的极简博客

一套零构建的 GitHub Pages 博客：**往 `blog/` 文件夹丢一个文件，博客就更新了。**
不用 git、不用本地环境、不用重新部署。

## 一、首次部署（只需做一次）

1. 打开仓库 https://github.com/khtao/khtao.github.io
2. 把本目录下的 `index.html` 和 `config.json` 上传到仓库**根目录**
   （Add file → Upload files，直接拖拽即可）
3. 新建 `blog/` 文件夹，把示例文章 `你好世界.md`、`html文章示例.html` 放进去
4. 确认 Settings → Pages → Source 为分支根目录（默认 `main` / `/root`）
5. 访问 https://khtao.github.io/ —— 完成

> 仓库名 `khtao.github.io` 固定对应域名 `https://khtao.github.io/`，无需额外配置 CNAME。

## 二、日常发文章（这才是重点）

1. 进入仓库的 `blog/` 目录
2. 点 **Add file → Upload files**，把你电脑上写好的 `.md` 或 `.html` 拖进去
3. 页面底部填一句 Commit message，点 **Commit changes**
4. 打开 https://khtao.github.io/ ，新文章已经在首页了，目录、标签、搜索自动更新

也可以直接在 GitHub 网页上点 `blog/` → **Create new file** 在线写完提交，连本地文件都不用。

## 三、文章格式

### Markdown（推荐）

文件名就是 URL 的一部分，建议用中文或英文标题命名，后缀 `.md`。

在文章**开头**写一段 frontmatter 来声明标题、日期、标签、摘要：

```markdown
---
title: 文章的标题
date: 2026-10-26
tags: [技术, 随笔]
summary: 显示在首页列表的一句话摘要
cover: https://…/cover.jpg   # 可选，文章顶部大图
---

正文从这开始，支持全部标准 Markdown 语法。
```

- `title`、`date`、`tags`、`summary` 都可以省略：标题退化为文件名的第一个 `#` 标题或文件名，摘要自动截取正文前 140 字
- 不想发布的草稿：文件名以 `_` 开头（如 `_草稿.md`），或在 frontmatter 写 `draft: true`
- 排序按 `date` 倒序

### HTML

后缀 `.html`，只写正文片段（不需要 `<html>`/`<body>`）。元信息写在第一行注释里：

```html
<!-- title: 文章标题 | date: 2026-10-25 | tags: [教程, HTML] | summary: 一句话摘要 -->
<h2>正文</h2>
<p>可以用任意 HTML 标签，样式与 Markdown 文章一致。</p>
```

## 四、功能

| 功能 | 说明 |
| --- | --- |
| 自动目录 | 每次访问实时读取 `blog/` 目录，新文章立刻出现在首页 |
| 标签筛选 | 由 frontmatter 的 `tags` 自动生成顶部标签栏 |
| 全文搜索 | 顶栏搜索框，标题 + 正文 + 标签即时过滤；按 `/` 快速聚焦 |
| 亮/暗主题 | 右上角一键切换，记忆选择，首次访问跟随系统 |
| 阅读进度条 | 页面顶部随滚动推进 |
| 文章大纲 | 文章右侧自动生成 h2/h3 目录，滚动高亮当前章节 |
| 代码高亮 | 代码块自动高亮 + 一键复制 |
| 图片灯箱 | 点击正文图片放大查看 |

## 五、配置（可选）

根目录 `config.json`：

```json
{
  "title": "Khtao",
  "subtitle": "记录技术、产品与生活",
  "description": "一个用文字对抗遗忘的地方。",
  "owner": "khtao",
  "repo": "khtao.github.io",
  "branch": "main",
  "blogDir": "blog",
  "footer": "© 2026 khtao · Built with GitHub Pages"
}
```

改完 Commit 即可生效。若分支是 `master`，把 `branch` 改成 `master`（不写也会自动探测）。

## 六、可能遇到的问题

**Q：新文章没出现？**
A：GitHub API 有缓存/CDN 延迟，通常几十秒内可见。点右下角 ↻ 按钮强制刷新；若仍没有，确认文件确实在 `blog/` 目录下且后缀是 `.md`/`.html`。

**Q：提示「暂时无法连接 GitHub」？**
A：GitHub 未认证 API 限制 60 次/小时（同一出口 IP）。稍等一会儿或点 ↻ 重试即可，已读过的文章会走本地缓存，不影响浏览。

**Q：中文文件名乱码/打不开？**
A：已做 URL 编码处理，正常可用；如仍不确定，改用英文文件名（如 `hello-world.md`）。

**Q：想本地预览？**
A：在这个目录执行 `python3 -m http.server 8000`，浏览器打开 http://localhost:8000 即可（联网状态下能读到仓库里的真实文章）。
