# zly3070.github.io

个人站点。手写 HTML/CSS，没有框架，没有 Jekyll（用 `.nojekyll` 关掉）。

线上地址：<https://zly3070.github.io>

---

## 架构：源在 `src/`，产物在根目录

**这条是理解整个仓库的关键：`src/` 下的是源，根目录下的是构建产物。**

```
src/                        ← 【只编辑这里】
  page-shell.html             页面骨架（<head> + <body> 两个槽）
  head.html                   公共 <head>（meta / canonical / CSS 引用）
  sidebar.html                左侧栏 + 右侧容器 + 页脚（全站共用一份）
  page-index.html             首页正文
  page-about.html             关于页正文（含照片墙 + 灯箱）
  page-recent.html            最近页正文（文章列表）
  page-post.html              文章页正文片段模板（pandoc 用）
  style.css                   全站样式

posts/*.md                  ← 【只编辑这里】文章内容（markdown）

        │  python scripts/build.py
        ▼

index.html                  ← 【产物，别手改】改了会被下次构建覆盖
about.html
Recent.html
posts/*.html
style.css                   （从 src/style.css 复制）
post_list.json / sitemap.xml / robots.txt
```

产物**不进 git**（见 `.gitignore`）。原因：本地 pandoc 和 CI 的 pandoc 版本不同，
同一份 markdown 生成的 HTML 有排版差异，跟踪产物会让本地和 CI 互相覆盖，
在 git 里产生永远同步不了的假改动。线上由 CI 在部署前生成。

---

## ⚠️ `废稿.html` 不要删

它是**这个网站的第一版手写 HTML**，整个站点的起点。虽然名字叫「废稿」，
但它是永久保留的纪念物。

它有意的设计：内联样式、不复用 `style.css`、不参与 `build.py` 构建、
不加侧栏 —— 这样它永远能独立打开，不会因为以后改架构而失效。
`robots.txt` 里 Disallow 了它（是给人看的，不是给搜索引擎的）。

---

## 常用命令

```bash
python scripts/serve.py        # 本地预览：构建 + 起 HTTP 服务（最常用）
python scripts/build.py        # 只构建
python scripts/check_build.py  # 自检产物（结构 / 幂等 / 行尾）
python scripts/fetch_photos.py # 拉取 Unsplash 照片墙数据（消耗 API 配额）
```

改完 `src/` 下的源或 `posts/*.md`，**要重新跑 `serve.py`** 预览才会更新。

---

## 怎么改常见的几处

| 想改什么 | 改哪个文件 |
|---|---|
| 全站正文的留白 | `src/style.css` 里的 `#main { padding: ... }` |
| 侧栏（logo、简介、联系方式、友链） | `src/sidebar.html` |
| 页脚 | `src/sidebar.html`（页脚在它里面） |
| 首页的「最近」「项目」 | `src/page-index.html` |
| 关于页 / 照片墙 / 灯箱 | `src/page-about.html` |
| 最近页的文章列表 | `src/page-recent.html` |
| 所有页面的 `<head>`（meta、字体、统计代码） | `src/head.html` |
| 文章页顶部的 `~/` 返回链接 | `src/page-post.html` |
| 某篇文章的内容 | `posts/<日期>-<标题>.md` |
| 页面骨架 / body 结构 | `src/page-shell.html` |

**title / description / canonical 不用手写** —— `build.py` 按页面自动填。

---

## 占位符

`build.py` 认这些标记：

| 占位符 | 用在哪 | 含义 |
|---|---|---|
| `{{HEAD}}` `{{SIDEBAR}}` `{{CONTENT}}` | `page-shell.html` | 骨架的三个槽 |
| `{{TITLE}}` `{{DESCRIPTION}}` `{{CANONICAL}}` | `head.html` | 按页面自动填 |
| `{{BASE}}` | 任意源文件 | 到站点根的相对前缀（`./` 或 `../`） |
| `{{HEAD_EXTRA}}` | `head.html` | 页面额外的 head 内容（文章页插 MathJax） |
| `{{CONTENT_SLOT}}` | `sidebar.html` | 正文的落脚点 |
| `$body$` | `page-post.html` | pandoc 填 markdown 正文 |

---

## 改代码前必读的两个坑

**1. HTML 注释不能嵌套**

`src/` 下的片段会被插进 `page-shell.html` 的 `{{HEAD}}` / `{{SIDEBAR}}` 位置。
片段**开头**的说明性注释必须去掉（`build.py` 的 `read_fragment()` 会自动剥），
否则内层注释的 `-->` 会提前闭合外层注释，内容泄漏成可见文字、页面结构错乱。

所以：`page-shell.html`、`head.html` 这类被插入的片段**不要**在开头写注释。

**2. pandoc 会保留模板里的注释**

`src/page-post.html` 的注释里不要出现字面量 `<main id="main"> ... </main>`。
`build.py` 的 `extract_main()` 已经会先剥注释再找，但保持这个习惯更安全。

---

## 配色与风格

- 正文衬线/无衬线按原样保留，**不要**加圆角卡片和阴影（要的是「文档感」）
- 间距沿用既有数值：23px / 16px / 14px / 6px / 4px
- 侧栏固定 250px，唯一滚动区是 `#main_container`

---

## 部署

推送到 `main` 触发 `.github/workflows/AutoPost.yml`：

```
checkout → 装 pandoc 3.10 → python3 scripts/build.py --site-dir _site
        → python3 scripts/check_build.py（自检不过就不部署）
        → 上传 _site → 部署 GitHub Pages
```

自检会检查：页面结构完整、关键 id 唯一、无残留占位符、构建幂等、行尾统一。
