<p align="center"><img src="blog/images/guide/hero.svg" width="100%" alt="Khtao Blog — 写作，就从这里开始"/></p>

<h1 align="center">Khtao Blog</h1>

<p align="center"><strong>你只是想写点东西，结果却在装 Node、配主题、修 npm 报错。</strong></p>

<p align="center"><strong>这个模板把博客变回它该有的样子：新建 <code>.md</code>，写完，提交。没了。</strong></p>

<p align="center">
  <a href="https://khtao.github.io/#/">✨ 看真实效果</a> ·
  <a href="blog/%E4%BB%8E%E9%9B%B6%E9%83%A8%E7%BD%B2GitHub%E5%8D%9A%E5%AE%A2.md">📖 图文部署教程</a> ·
  <a href="#-现在开始给自己搭一座博客">🚀 10 分钟上线</a>
</p>

<p align="center">
  <code>零构建</code> <code>不需要 Node.js</code> <code>单个 HTML 文件</code> <code>GitHub Pages 原生部署</code> <code>WebP + 图片懒加载</code>
</p>

---

## 🤔 先说清楚，它和别的博客差在哪

| | 常见的博客方案 | 这里 |
| --- | --- | --- |
| 准备环境 | 装 Node.js、npm，拉几百 MB 依赖 | **什么都不用装**，有 GitHub 账号就行 |
| 发一篇文章 | `hexo new` → 写 → `hexo g` → `hexo d`，等本地构建 | 丢一个 `.md` 进 `blog/`，提交 |
| 改标题和署名 | 翻几百行 YAML 主题配置 | 改一个 `config.json`，**真正必改的只有 4 个字段** |
| 半年后再来 | 依赖过期、版本冲突、构建失败 | **没有依赖，也就没有冲突** |
| 手机想写点东西 | 不可能 | 浏览器里新建文件就能写 |

它不是一个"功能更多的 Hexo"，而是**把整条构建链拿掉之后剩下的东西**：一个 `index.html`、一个 `config.json`、一个用 Python 标准库写的索引脚本。

代价也很实在，不想骗你：文章用 `#/` 哈希路由，**每篇文章没有独立的 SEO 页面**（站点地图只含主页）。如果你靠搜索引擎流量吃饭，这是要考虑的；如果你主要是写给自己和老读者，它无所谓。

---

## 👀 30 秒，看看它长什么样

<table>
  <tr>
    <td width="73%" align="center"><img src="blog/images/guide/desktop.webp" alt="桌面端浅色模式真实截图"/><br/><b>桌面端 · 编辑式双栏</b></td>
    <td width="27%" align="center"><img src="blog/images/guide/mobile.webp" alt="手机端真实截图"/><br/><b>移动端 · 自适应</b></td>
  </tr>
</table>

<details>
<summary>🌙 展开看深色模式</summary>

![深色模式真实截图](blog/images/guide/dark.webp)

</details>

---

## ✨ 为什么值得一试

**写的时候，什么都不用管**

- 丢进 `.md` 就能发 —— 标题、摘要、发布日期、修订日期**全部自动提取**，不用手写一行元信息
- 想加分类标签才需要写 front-matter，不写也照常发布
- 原样 HTML 文章也没问题：走 iframe 隔离渲染，你自带的 CSS / JS 100% 生效，不污染整站

**读的时候，体验是认真做过的**

- 全文搜索（`Ctrl/⌘ + K` 或直接按 `/`）、标签、分类、按年归档
- 文章目录、代码高亮与一键复制、字号调节、阅读进度条
- 浅色 / 深色双主题，桌面平板手机三端自适应

**上线之后，真的不用维护**

- Push 即构建，Actions 自动刷新索引、RSS、站点地图
- 访客读的是本站的 `blog/index.json`，**不碰 GitHub API**，所以不限流、不卡顿、也不需要任何 Token
- 删文章索引会同步，哪怕删到一篇不剩，也是正常的空状态而不是报错

---

## ⚡ 顺带一提：它很快

一篇 50 图的游记，原本要在首屏拉 **11MB** 原图。现在：

| 瓶颈 | 怎么处理的 | 结果 |
| --- | --- | --- |
| 50 张原图挤在首屏 | 构建期生成 WebP 孪生文件并重新压缩；前端补 `loading="lazy"`，只留首屏 2 张立即加载 | WebP 全量 **10.8MB → 5.9MB**，首屏降到几百 KB |
| 每页苦等境外 CDN 的两个脚本，最坏 6 秒超时 | marked / highlight.js 已本地化到 `assets/vendor/`；122KB 的高亮库推迟到浏览器空闲再取 | 首屏不再受境外网络抖动影响，少 122KB |
| 所有请求都是 `no-store`，回访也重下全文 | 正文 URL 带 `sha`，内容不变就复用 HTTP 缓存；索引仍 `no-store` 保证新鲜 | 二次访问基本秒开，又不会读到旧文章 |

图片优化是**幂等**的：按内容 sha256 记录已处理文件，重复构建不会反复压缩、画质不累积劣化。没装 Pillow 时脚本自动跳过，构建照常通过。

---

## ©️ 还有件别人不太管的事：你的版权

文字是你写的，被整篇搬走还抹掉署名，很窝火。这里默认就帮你挡了一层：

1. **页脚常驻** —— 许可协议 + 「未经许可不得转载」
2. **每篇文末声明框** —— 作者 / 标题 / 原文链接 / 许可，四项齐全
3. **复制自动溯源** —— 复制超过 40 字会自动带上标题和原文链接，短摘引不受影响

`robots.txt` 由构建脚本生成：Google、Bing、百度正常收录，同时**拒绝 26 个未授权的 AI 训练与 SEO 抓取**（`GPTBot`、`CCBot`、`Bytespider`、`SemrushBot` 等，可在 `config.json → blockedBots` 追加）。

> 说句实话：robots.txt 是声明，挡不住执意的抓取者。真要强拦，请配合 Cloudflare 的 Bot 规则。

---

## 🚀 现在开始，给自己搭一座博客

![从写文章到自动上线的流程图](blog/images/guide/deploy-flow.svg)

### 方式 A：用模板一键复制（最快）

1. 进 [本仓库](https://github.com/khtao/khtao.github.io)，点 **Use this template → Create a new repository**
2. 仓库名填 **`你的用户名.github.io`**，选 Public
3. 打开 `config.json`，把 `owner`、`repo`、`author`、`title` 改成你自己的
4. 进 **Settings → Pages → Build and deployment → Source**，选 **GitHub Actions**
5. 到 **Actions** 里等 `Build and deploy blog` 跑完（没自动跑就点 **Run workflow**）
6. 打开 `https://你的用户名.github.io/#/`

> 没看到「Use this template」按钮？说明模板模式没开，直接用方式 B，效果一样。

### 方式 B：下载源码上传（始终可用）

1. 仓库页 **Code → Download ZIP**，解压
2. 新建一个公开的 `你的用户名.github.io` 仓库
3. **把解压后根目录里的文件和文件夹整个传上去** —— 特别当心 `.github/workflows/blog-index.yml`、`scripts/`、`blog/` 这三样，漏了就跑不起来
4. 改 `config.json`，按上面第 4 步开 Pages

> ⚠️ 用 Git 或 GitHub Desktop 提交整个目录最稳妥。GitHub 网页上传容易漏掉 `.nojekyll` 这类隐藏文件（构建时会补一份，但别赌）。

---

## 📝 发第一篇文章

在 `blog/我的第一篇文章.md` 新建文件：

```md
# 我的第一篇文章

今天，我终于有了一个真正属于自己的博客。

## 从这里开始

以后把学到的、做过的、想明白的，都慢慢写下来。
```

提交到 `main`，然后**什么都不用做**。工作流会自动提取标题、摘要、日期，生成索引和 RSS，一起发布。

想加分类标签，就在开头**可选**地写：

```yaml
---
category: 技术
tags: [GitHub Pages, 博客]
---
```

> 不写也照常发布。写的话，注意 `category`、`tags` 要顶格对齐。

图片放进 `blog/images/`，正文写 `![说明](images/文件名.png)`，路径会自动指向博客目录。

---

## 🗂 项目结构

```text
你的用户名.github.io/
├── index.html                  # 页面、样式、阅读器全在这里
├── config.json                 # 博客名、简介、作者、版权设置
├── blog/
│   ├── 我的第一篇文章.md        # 你的内容
│   ├── images/                 # 图片
│   └── index.json              # 自动生成的索引
├── assets/vendor/              # 本地化的 marked / highlight.js
├── scripts/
│   ├── build_index.py          # 提取元数据、生成 RSS / sitemap / robots
│   ├── optimize_images.py      # 图片压缩 + 生成 WebP
│   └── build_projects.py       # 项目页快照（可选）
├── .github/workflows/
│   └── blog-index.yml          # 自动部署到 Pages
└── .nojekyll                   # 静态站点兼容文件
```

**个性化入口就一个**：`config.json` 里的 `title`、`subtitle`、`description`、`author`、`owner`、`repo`、`notice`、`about`。想改配色或布局，编辑 `index.html` 里的 CSS。

> 记得把 `owner` 和 `repo` 改成你自己的账号和仓库名，否则页脚的 GitHub 链接会指向这里。

---

## 🧩 它到底是怎么跑起来的

```text
你在 blog/ 里新建、修改或删除文章
              ↓
        Push 到 main
              ↓
    GitHub Actions 拉取完整 Git 历史
              ↓
  Python 扫描文章 → 生成 index.json + feed.xml + sitemap.xml + robots.txt
  （同时压缩图片、生成 WebP）
              ↓
      与 index.html 一起部署到 Pages
              ↓
          读者打开你的网站
```

几个值得知道的实现细节：

- **日期从 Git 历史里来**，不需要你手写 —— 首次提交即发布日，最后一次即修订日
- **先渲染本地缓存再静默同步**，所以回访是秒开的，新文章在后台补上
- `#/` 是哈希路由，**站点地图只含主页**，文章没有独立 SEO 页面
- Markdown 渲染用本地 `marked`，内置降级解析器兜底；都不行也能看

---

## 🔧 本地预览

```bash
python3 scripts/build_index.py
python3 -m http.server 8000
```

打开 `http://localhost:8000/#/`。有 `tests/` 的话可以跑 `python3 -m unittest discover -s tests -v`。

> 一定要通过 HTTP 访问，**别双击用 `file://` 打开** —— 浏览器会拦本地文件的 `fetch`，页面会是空的。

---

## 💬 最后

喜欢这种**低维护、重内容**的博客方式，欢迎点个 ⭐，或者在 [Issues](https://github.com/khtao/khtao.github.io/issues) 留下你的作品和建议 —— 我很想看看你用它写了什么。

也可以直接读 [图文部署教程](blog/%E4%BB%8E%E9%9B%B6%E9%83%A8%E7%BD%B2GitHub%E5%8D%9A%E5%AE%A2.md)，从第一篇文章开始记录。

> **关于授权**：仓库公开不等于自动授予再分发权。使用前请以仓库实际许可为准；如果你是维护者，建议补一份明确的 `LICENSE`（如 MIT），让想用的人安心。

<div align="center"><sub>Built with GitHub Pages · Made for writing, not configuration.</sub></div>
