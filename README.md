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
- `cover` 是文章顶部大图，同样支持相对路径（如 `images/cover.svg`）
- HTML 文章内的 `<script>` 会正常执行（独立 iframe 内），不需要额外声明
- 不想发布的草稿：文件名以 `_` 开头（如 `_草稿.md`），或在 frontmatter 写 `draft: true`
- 排序按 `date` 倒序

### HTML

后缀 `.html`，只写正文片段（不需要 `<html>`/`<body>`）。元信息写在第一行注释里：

```html
<!-- title: 文章标题 | date: 2026-10-25 | tags: [教程, HTML] | summary: 一句话摘要 -->
<h2>正文</h2>
<p>可以用任意 HTML 标签，样式与 Markdown 文章一致。</p>
```

## 四、不写头信息也能用：标题 / 日期 / 摘要自动提取

**不写任何 frontmatter 也能正常发布。** 站点会自动从内容和 Git 记录里补全：

| 信息 | 取值优先级 |
| --- | --- |
| 标题 | frontmatter `title` → HTML `<h1>` / `<title>` / `og:title` → Markdown 首个 `#` 标题 → 文件名（自动去掉日期前缀、`-` `_` 转空格） |
| 上传日期 | frontmatter `date` → **该文件第一次提交的日期** → 文件名里的日期（`2026-10-26-xxx.md`） |
| 修订日期 | frontmatter `updated` → **该文件最后一次提交的日期** |
| 摘要 | frontmatter `summary` → `og:description` / `<meta description>` → 正文第一段 → 正文前 140 字 |
| 标签 | frontmatter `tags`；没写就是无标签 |

- 上传 / 修订日期直接读仓库提交记录，**改一次文件就自动更新修订日期**
- 这些日期按文件指纹缓存，不会重复消耗 API；只有文件内容变了才重新取
- 想自己指定就写 frontmatter，写了就以你写的为准（`date` / `updated` / `summary` / `tags`）

## 五、相对路径：一律以 `blog/` 为根目录

文章里引用图片、附件时**不用写完整网址**，相对路径会按 `blog/` 为根自动解析。

| 你写的 | 实际解析为 |
| --- | --- |
| `images/cover.svg` | `…/main/blog/images/cover.svg` |
| `./images/cover.svg` | 同上（`./` 可省略） |
| `files/报告.pdf` | `…/main/blog/files/报告.pdf` |
| `https://…/a.png` | 原样使用，不改写 |

- 中文文件名、空格会自动做 URL 编码
- 主源取不到时自动回退镜像与 jsDelivr，图片不会裂
- 相对路径**指向另一篇文章**（如 `[链接](你好世界.md)`）会自动转成站内跳转，无需刷新页面
- 目录建议：`blog/images/` 放图片、`blog/files/` 放附件

## 六、HTML 文章：100% 原样渲染

上传 `.html` 后，整篇文章会在一个独立的 iframe 里**按你写的样子完整渲染**：

- 自带 `<style>`、`<link rel=stylesheet>`、`<script>` **全部生效**（轮播、灯箱、滚动动画、sticky 导航照常工作）
- 有自己的 `<head>`、`:root` 变量、`body` 背景、`vh` 布局 —— 全都按原文件走，不受站点主题影响
- 文章内的滚动、锚点导航都在文章自己的视口里进行，与单独打开这个 HTML 文件完全一致
- 也完全不会污染首页和其他文章

右上角提供 **↗ 独立页面打开**，直接访问 `https://khtao.github.io/blog/你的文件名.html`，
由 GitHub Pages 原生托管，是最原汁原味的打开方式（这个地址也能直接分享给别人）。

> 注意：文章里的 `vh` 单位会按 iframe 高度计算（约等于窗口高度减顶部导航），这是正常的。

## 七、链接容错：文件名不完全一致也能打开

如果链接里的文件名和仓库里的不一样（例如上传时被改短、少了后缀），
站点会做模糊匹配：忽略标点空格大小写后，若只有一篇文章匹配，就直接打开它；
匹配不到时，404 页面会列出「你可能要找的是」候选文章，不会白屏。

建议做法：把 `blog/` 里的文件名作为唯一标识，尽量不要在文件名里用 `·` `？` 等特殊符号。

## 八、功能

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

## 九、配置（可选）

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

`token` 一般留空；只有频繁遇到「连不上 GitHub」时才需要，见下一节。

## 十、【推荐】开启静态索引，彻底告别 API 限额

在仓库里加一个 GitHub Actions 文件，它会在每次发文时自动生成 `blog/index.json`，
把**目录、标题、上传日期、修订日期、摘要、标签**全部预先算好。
访问博客时只读这一个静态文件，**一次 GitHub API 都不用调用**，
国内访问也走 Pages CDN，速度更快、永远不会限额。

**添加方法（网页端，不用 git）**：仓库 → Add file → Create new file，
文件名填 `.github/workflows/blog-index.yml`，内容用交付包里的同名文件粘贴进去，Commit 即可。
之后想手动触发：Actions → Build blog index → Run workflow。

效果对比：

| | 不开索引 | 开了索引 |
| --- | --- | --- |
| 目录 + 日期 | 需调用 GitHub API（匿名 60 次/小时） | 读静态 JSON，0 次 |
| 国内访问 | 依赖 raw / 镜像 | Pages CDN，最快 |
| 断网/限额时 | 显示缓存 | 一切照常 |

不开也能用（会自动回退到 API + CDN 多源），只是没那么稳。

## 十一、可能遇到的问题

**Q：上传 / 修订日期是怎么来的？**
A：读该文件的 Git 提交记录——第一次提交是「上传日期」，最后一次提交是「修订日期」。
改一次文件，修订日期就自动更新。开了静态索引后，这些日期由 Actions 在服务端算好，不消耗 API。

**Q：新文章没出现？**
A：GitHub API 有缓存/CDN 延迟，通常几十秒内可见。点右下角 ↻ 按钮强制刷新；若仍没有，确认文件确实在 `blog/` 目录下且后缀是 `.md`/`.html`。

**Q：提示「暂时连不上 GitHub」？**

站点已经做了四层兜底，**正常情况下不会再出现这个提示**：

1. 目录读取：GitHub API → 3 个公开镜像 → jsDelivr 文件清单 → ungh.cc（后两者完全不受 API 限额影响）
2. 正文读取：raw → gitmirror → 2 个代理 → jsDelivr ×2 → githack，共 7 个源
3. 有本地缓存时：**先秒开缓存**，后台继续同步，只在顶部显示一行淡淡的「正在展示本地缓存」，不再弹错误
4. 完全没有缓存且全源失败：才显示提示，并提供「填写 Token」入口

如果还是长期遇到（公司/校园网共享出口 IP，60 次/小时很容易打满），
在页面提示里点「填写 Token」，或在 `config.json` 里填 `token`：
GitHub → Settings → Developer settings → Fine-grained tokens → 生成时**权限全部留空**即可（公开仓库读内容不需要任何 scope），
配额立刻从 60 次/小时 提升到 **5000 次/小时**。

**Q：删掉的文章还在列表里？**
A：刷新一次即可消失。目录以仓库实际内容为准，删除的文章不会残留；
只有在完全连不上 GitHub 时才显示缓存（此时顶部会明确标注「正在展示本地缓存」）。

**Q：中文文件名乱码/打不开？**
A：已做 URL 编码处理，正常可用；如仍不确定，改用英文文件名（如 `hello-world.md`）。

**Q：想本地预览？**
A：在这个目录执行 `python3 -m http.server 8000`，浏览器打开 http://localhost:8000 即可（联网状态下能读到仓库里的真实文章）。
