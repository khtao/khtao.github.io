# 自动化 GitHub Pages 博客脚手架

一个"**写完即发布**"的博客系统：在线编辑器写完文章点保存 → 自动生成 Git 提交 → GitHub Actions 自动构建 → 博客上线。
全程不需要安装 Node、不需要敲 git 命令，手机浏览器也能写。

```
┌──────────────┐   写入 .md    ┌──────────────┐   自动构建    ┌─────────────────┐
│ /admin/ 编辑器 │ ───────────► │ 仓库 main 分支 │ ───────────► │ xxx.github.io   │
│  (浏览器)     │   一次 commit │  (唯一数据源)  │  Actions     │  (静态站点)      │
└──────────────┘               └──────────────┘               └─────────────────┘
```

## 目录结构

```
├── _config.yml                 # 站点主配置（★必改：url / root）
├── _config.fluid.yml           # 主题配置（导航、头图、评论等）
├── package.json                # 依赖清单
├── scaffolds/post.md           # 新文章模板
├── source/
│   ├── _posts/                 # 文章都在这里（.md）
│   ├── about/index.md          # 关于页
│   ├── images/                 # 编辑器上传的图片存这里
│   └── admin/
│       ├── index.html          # ★ 内置 Markdown 编辑器（纯静态 SPA）
│       └── vendor/             # 编辑器依赖（Vditor + js-yaml，已本地化）
└── .github/workflows/
    ├── deploy.yml              # 推送即构建部署 + 手动 + 被定时调用
    └── rebuild.yml             # 每周一定时全量重建（维护用）
```

## 一、上线步骤（约 10 分钟）

### 1. 建仓库并上传代码

在 GitHub 新建仓库（例如 `my-blog`），把本目录所有文件推到 `main` 分支：

```bash
git init && git add . && git commit -m "init blog"
git branch -M main
git remote add origin https://github.com/你的用户名/my-blog.git
git push -u origin main
```

### 2. 开启 GitHub Pages

仓库 **Settings → Pages → Build and deployment → Source** 选择 **GitHub Actions**（不要选"Deploy from a branch"）。

### 3. 改两处必改配置

`_config.yml` 顶部：

| 配置项 | 说明 |
|---|---|
| `url` | `https://你的用户名.github.io/my-blog`（仓库名带后缀时）/ `https://你的用户名.github.io`（仓库名就是 `用户名.github.io`） |
| `root` | 对应填 `/my-blog/` 或 `/`（**末尾斜杠不能少**） |
| `title` / `author` / `description` | 站点信息 |

改完提交推送，Actions 会自动跑第一次构建。成功后访问上面的 `url` 即可看到博客。

### 4. 开始写文章

打开 `https://你的用户名.github.io/my-blog/admin/`，点「⚙️ 仓库设置」填入：

| 字段 | 示例 |
|---|---|
| Owner | `你的用户名` |
| Repo | `my-blog` |
| Branch | `main` |
| Token | 下面一步申请的 PAT |

**申请 Token**：GitHub 右上角头像 → Settings → Developer settings → Personal access tokens → **Fine-grained tokens** → Generate new token
→ 只选这个仓库 → Repository permissions 里把 **Contents** 设为 **Read and write** → 生成后复制（只显示一次）。

> Token 只保存在你自己浏览器的 localStorage，不会发送到任何第三方服务器；换电脑需重新填写。
> 建议给 Token 设 90 天有效期，到期重新生成一个即可。

## 二、编辑器功能

- **新建 / 打开 / 删除**文章，自动读写 `source/_posts/*.md`
- **所见即所得** Markdown 编辑（Vditor，支持即时渲染 / 分屏预览 / 大纲）
- **图片直接粘贴或拖拽**，自动上传到 `source/images/年/月/` 并插入 CDN 链接
- 表单化管理 front-matter：标题、日期、分类、标签、摘要、置顶权重
- `Ctrl / ⌘ + S` 保存；保存后提示跳转到 Actions 看构建进度
- 图片 CDN 默认 jsDelivr，国内访问慢可在设置里换成 raw.githubusercontent.com 或自己的图床

保存 = 一次 Git commit = 触发 Actions ≈ 30～90 秒后博客更新。

## 三、"自动维护"是怎么做到的

| 场景 | 机制 |
|---|---|
| 编辑器保存 / 删除文章 | push 事件触发 `deploy.yml` |
| 本地 `git push` 提交文章 | 同上 |
| 很久没更新也要刷新 | `rebuild.yml` 每周一 11:17（北京时间）定时重建 |
| 想立刻重建 | Actions 页面选中流程 → Run workflow |
| 每次构建 | 自动刷新 `sitemap.xml`、`atom.xml`（RSS）、搜索索引 |

想改定时间：编辑 `rebuild.yml` 里的 `cron`（UTC 时间，默认 `17 3 * * 1`）。
想关掉定时维护：删掉 `rebuild.yml` 即可。

## 四、可选：本地预览

装了 Node.js 的话，可以本地起服务看效果（改主题配置时很方便）：

```bash
npm install
npm run server     # 打开 http://localhost:4000
```

## 五、常见问题

**页面 404 / 样式全丢**
`_config.yml` 的 `root` 填错了。仓库名 `用户名.github.io` → `root: /`；其他仓库名 → `root: /仓库名/`。

**编辑器点保存报错 404**
文章目录设置不对，确认是 `source/_posts`（区分大小写）；或 Token 权限不足（需要 Contents 读写）。

**报错 409 Conflict**
这篇文件在别处被改过（比如本地 git 推过一次），刷新列表重新打开再保存即可。

**构建时报 `Cannot find module 'moment'` 等**
主题脚本依赖未提升到顶层，执行一次 `npm i moment hexo-util hexo-pagination @adobe/css-tools` 后重新推送。

**想要自定义域名**
在 `source/` 下新建文件 `CNAME`，内容写你的域名（如 `blog.example.com`），并在域名服务商处添加一条 CNAME 记录指向 `用户名.github.io`。Pages 里填同域名即可，Actions 会自动签发 HTTPS 证书。

**不想让别人看到编辑器入口**
删掉 `source/admin/index.html` 和 `_config.fluid.yml` 菜单里那行 `写文章` 即可；需要更强保护可套 Cloudflare Access。

**想换主题**
`npm i 主题包名`，改 `_config.yml` 的 `theme:` 即可，编辑器与自动发布流程不受影响。

## 六、技术选型

| 组件 | 选择 | 理由 |
|---|---|---|
| 站点生成 | Hexo 7 | 中文生态好、插件丰富、扫描 `_posts` 自动收录新文章 |
| 主题 | hexo-theme-fluid 1.9 | 响应式、自带搜索/归档/标签、配置友好 |
| CI/CD | GitHub Actions 官方 Pages 流程 | 免密钥、原生集成 |
| 编辑器 | Vditor + GitHub Contents API | 纯静态、无需自建后端，浏览器直连仓库读写；依赖已本地化，离线可用 |
| 文章链接 | hexo-abbrlink | 自动生成短 ID，中文标题也能有干净 URL |

> 编辑器的 Vditor 与 js-yaml 已打包在 `source/admin/vendor/` 下，**不依赖任何 CDN**，国内访问也稳定。
> 若你误删了 vendor，页面会自动回退到 jsDelivr 加载；两者都不可用时降级为纯文本框，仍可正常写文章。
> 想换成自建 CDN：改 `source/admin/index.html` 顶部 `CDN` 常量即可。
