#!/usr/bin/env python3
"""
构建整站 —— 唯一的构建入口。

    python scripts/build.py

做四件事：
    1. pandoc 把 posts/*.md 渲染成 HTML 正文片段
    2. 用 src/ 里的骨架 + 侧栏 + 正文，生成所有页面
    3. 生成 post_list.json / sitemap.xml / robots.txt，复制 style.css
    4. 全程只读 src/，只写产物 —— 你手改产物会被这里覆盖（那是设计如此）

源与产物
--------
    源（只改这些）                        产物（别手改）
    src/page-shell.html     页面骨架  ->  index.html / about.html /
    src/head.html           公共 head     Recent.html / posts/*.html
    src/sidebar.html        侧栏+页脚
    src/page-index.html     首页正文
    src/page-about.html     关于页正文
    src/page-recent.html    最近页正文
    src/page-post.html      文章页片段模板
    src/style.css           样式      ->  style.css
    posts/*.md              文章内容  ->  posts/*.html

占位符
------
    {{HEAD}} {{SIDEBAR}} {{CONTENT}}   骨架里的三个槽
    {{TITLE}} {{DESCRIPTION}} {{CANONICAL}} {{BASE}} {{HEAD_EXTRA}}   head 里的
    $body$                             只有 src/page-post.html 用（pandoc 填）
    {{CONTENT_SLOT}}                   src/sidebar.html 里正文的落脚点
"""

import argparse
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote
from xml.sax.saxutils import escape as xml_escape

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

# ============ 路径 ============

ROOT = Path(__file__).parent.parent
SRC = ROOT / "src"
POSTS = ROOT / "posts"

SHELL = SRC / "page-shell.html"
HEAD = SRC / "head.html"
SIDEBAR = SRC / "sidebar.html"
POST_FRAGMENT = SRC / "page-post.html"
STYLE_SRC = SRC / "style.css"
STYLE_OUT = ROOT / "style.css"

SITE = "https://zly3070.github.io"

# 根目录页面：产物名 -> 正文源文件、标题、描述、页面专属 CSS（可选）
ROOT_PAGES = [
    ("index.html", SRC / "page-index.html",
     "小波球de人间见行", "*啵…啵啾…*", None),
    ("about.html", SRC / "page-about.html", "About",
     "关于我：zjut软工专生，正在学AI，喜欢摄影。",
     SRC / "page-about.css"),
    ("Recent.html", SRC / "page-recent.html", "最近",
     "所有文章列表：学习笔记、论文精读、技术思考。", None),
]


# ============ 基础工具 ============

def read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def write(p: Path, text: str):
    """统一用 LF 写盘 —— Windows 上 Python 默认会写成 CRLF，那会让 git 一直报警告。"""
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8", newline="")


def fill(template: str, **vars) -> str:
    """替换 {{NAME}} 占位符。值里如果还有占位符，会自动再跑一轮。"""
    pattern = re.compile(r"\{\{([A-Z_]+)\}\}")
    for _ in range(6):  # 最多 6 轮，够覆盖嵌套
        if not pattern.search(template):
            break
        template = pattern.sub(lambda m: vars.get(m.group(1), m.group(0)), template)
    left = sorted(set(pattern.findall(template)))
    if left:
        raise SystemExit(f"✗ 这些占位符没被填上: {left}（检查 build.py 的 fill 调用）")
    return template


def dedent(text: str) -> str:
    """去掉一段文本的公共缩进（用于把正文放进骨架）"""
    lines = text.strip("\n").split("\n")
    indents = [len(l) - len(l.lstrip()) for l in lines if l.strip()]
    cut = min(indents) if indents else 0
    return "\n".join(l[cut:] if l.strip() else "" for l in lines)


def strip_outer_comments(text: str) -> str:
    """
    去掉片段开头和结尾的纯注释块。

    为什么必须这么做：HTML 注释不能嵌套。
    src/ 下的片段会被插进 page-shell.html 的 {{HEAD}} / {{SIDEBAR}} 位置，
    如果那个位置在另一个注释里，内层注释的 "-->" 会提前把外层注释闭合，
    导致后面的内容泄漏到注释外面、整个页面结构错乱（踩过这个坑）。

    这条规则针对的是「开头/结尾的整块注释」。片段【内部】的注释一律保留 ——
    那才是给读产物的人看的。

    顺带一提：src/page-shell.html 自己的开头也不能有注释，
    否则 {{HEAD}} 会被插进那个注释里。
    """
    # 1) 剥开头的注释块（可能连续多块）
    while True:
        m = re.match(r"\s*<!--", text)
        if not m:
            break
        end = text.find("-->", m.end())
        if end == -1:
            break
        after = text[end + 3:]
        if not after.strip():
            break  # 整个文件就是注释，别删
        text = after.lstrip("\n")
    # 2) 剥结尾的注释块
    while True:
        if not text.rstrip().endswith("-->"):
            break
        start = text.rstrip().rfind("<!--")
        if start == -1:
            break
        before = text[:start]
        if not before.strip():
            break
        text = before.rstrip("\n") + "\n"
    return text


def read_fragment(p: Path) -> str:
    """读一个片段源文件，并去掉它的注释头（见 strip_outer_comments）"""
    return strip_outer_comments(read(p))


def url_for(rel_path: str) -> str:
    """相对路径 -> 合法的规范 URL（百分号编码，处理空格 / & / 中文）"""
    return SITE + "/" + quote(rel_path)


# ============ 页面组装 ============

def render_head(title: str, description: str, canonical: str, base: str,
                head_extra: str = "") -> str:
    raw = read_fragment(HEAD)
    # {{HEAD_EXTRA}} 单独占一行：有内容就留，没内容整行删掉（避免留空行）
    raw = re.sub(
        r"(?m)^[ \t]*\{\{HEAD_EXTRA\}\}[ \t]*\n?",
        (head_extra.rstrip() + "\n") if head_extra.strip() else "",
        raw,
    )
    return fill(
        raw,
        TITLE=title,
        DESCRIPTION=description.replace('"', "&quot;"),
        CANONICAL=canonical,
        BASE=base,
    ).strip("\n")


def render_page(title: str, description: str, out_rel: str, base: str,
                content: str, head_extra: str = "", page_css: Path = None) -> str:
    head = render_head(title, description, url_for(out_rel), base, head_extra)

    # 页面专属 CSS：源在 src/*.css，产物复制到 style-<名字>.css。
    # 用 <link> 而不是内联 <style>，这样它和 style.css 一样能被浏览器缓存。
    css_tag = ""
    if page_css is not None:
        css_out = "style-" + page_css.stem.replace("page-", "") + ".css"
        write(ROOT / css_out, read(page_css))
        css_tag = f'    <link rel="stylesheet" href="{base}{css_out}" />'

    content = fill(dedent(content).replace("{{BASE}}", base))
    sidebar = fill(read_fragment(SIDEBAR), BASE=base, CONTENT_SLOT=content).strip("\n")
    return fill(read_fragment(SHELL), HEAD=head, SIDEBAR=sidebar,
                CONTENT=content, PAGE_CSS=css_tag)

def remove_comments(html: str) -> str:
    """
    剥掉所有 HTML 注释。用状态机而不是 `<!--.*?-->` 正则 ——
    后者在注释里提到 `<!--` 时会错位。
    """
    out, pos, n = [], 0, len(html)
    while pos < n:
        start = html.find("<!--", pos)
        if start == -1:
            out.append(html[pos:])
            break
        out.append(html[pos:start])
        end = html.find("-->", start + 4)
        if end == -1:
            break
        pos = end + 3
    return "".join(out)


def extract_main(fragment: str) -> str:
    """
    从 pandoc 产出的片段里取 <main id="main">...</main>。

    ⚠ 必须先剥注释再找：
      pandoc 会原样保留模板里的注释，而模板的说明注释里正好写了一行
      「（<main id="main"> ... </main>，不含 <html>/<head>）」——
      不剥注释的话正则匹配到的就是注释里那个字面量，
      正文会被替换成 "..."，页面看着就是空的（踩过这个坑，很难查）。
    """
    body = remove_comments(fragment)
    m = re.search(r'(?s)<main id="main">.*?</main>', body)
    if not m:
        raise SystemExit("✗ pandoc 片段里找不到 <main id=\"main\">，检查 src/page-post.html")
    return m.group(0)


# ============ 文章 ============

def parse_post_name(stem: str):
    """'2026-08-09-数据结构' -> ('2026-08-09', '数据结构')"""
    m = re.match(r"^(\d{4}-\d{2}-\d{2})-(.*)$", stem)
    return (m.group(1), m.group(2)) if m else ("", stem)


def md_description(md: Path) -> str:
    """从 markdown 抽第一段 _斜体_ 作为简介"""
    if not md.exists():
        return ""
    text = read(md)
    m = re.search(r"_(.+?)_", text, re.DOTALL) or re.search(r"\*(.+?)\*", text, re.DOTALL)
    if not m:
        return ""
    t = m.group(1)
    t = re.sub(r"\*\*(.+?)\*\*", r"\1", t)
    t = re.sub(r"`(.+?)`", r"\1", t)
    t = re.sub(r"~~(.+?)~~", r"\1", t)
    t = re.sub(r"\[(.+?)\]\(.+?\)", r"\1", t)
    t = re.sub(r"!\[.*?\]\(.+?\)", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    # 老文章的占位符 "short discrption" 放进搜索结果很难看，丢弃
    if t.lower().replace(" ", "") in ("shortdiscrption", "shortdescription", ""):
        return ""
    return t[:147] + "..." if len(t) > 150 else t


def build_posts():
    """pandoc 渲染正文片段 -> 组成完整文章页。返回 [(日期, 标题, 文件名)]"""
    md_files = sorted(POSTS.glob("*.md"))
    if not md_files:
        print("  ⚠ posts/ 下没有 .md 文件")
        return []

    fragment_tpl = read(POST_FRAGMENT)
    results = []

    for md in md_files:
        date, title = parse_post_name(md.stem)
        out_name = f"{md.stem}.html"

        # 1) pandoc：markdown -> 正文片段
        proc = subprocess.run(
            [
                "pandoc", str(md),
                "-f", "markdown+tex_math_dollars",
                f"--template={POST_FRAGMENT}",
                "--eol=lf",              # Windows 上 pandoc 默认写 CRLF，强制 LF
            ],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        if proc.returncode != 0:
            print(f"    ✗ {md.name}: pandoc 失败\n       {(proc.stderr or '').strip()[:300]}")
            continue
        content = extract_main(proc.stdout)

        # 2) 套上骨架 + 侧栏 + 页脚
        html = render_page(
            title=f"{title} - 波球在这里思考过",
            description=md_description(md),
            out_rel=f"posts/{out_name}",
            base="../",
            content=content,
            head_extra=(
                '    <!-- MathJax：文章里可能有公式 -->\n'
                '    <script src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-svg.js" async></script>'
            ),
        )
        write(POSTS / out_name, html)
        print(f"    ✓ posts/{out_name}")
        results.append((date, title, out_name))

    results.sort(key=lambda x: x[0], reverse=True)
    return results


# ============ sitemap / robots / post_list ============

def sitemap_lastmod(name: str, fallback: str) -> str:
    m = re.match(r"^(\d{4}-\d{2}-\d{2})-", name)
    return m.group(1) if m else fallback


def build_sitemap(posts, today: str) -> str:
    pages = [("index.html", "1.0", today),
             ("Recent.html", "0.8", today),
             ("about.html", "0.7", today)]
    pages += [(f"posts/{n}", "0.6", sitemap_lastmod(n, today)) for _, _, n in posts]
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for rel, prio, lastmod in pages:
        lines += ["  <url>",
                  f"    <loc>{xml_escape(url_for(rel))}</loc>",
                  f"    <lastmod>{lastmod}</lastmod>",
                  f"    <priority>{prio}</priority>",
                  "  </url>"]
    lines.append("</urlset>")
    return "\n".join(lines) + "\n"


def build_robots() -> str:
    return (
        "# 全部允许抓取\n"
        "User-agent: *\n"
        "Allow: /\n"
        "\n"
        "# 草稿、源码目录不是页面，别浪费抓取配额\n"
        "Disallow: /src/\n"
        "Disallow: /scripts/\n"
        "Disallow: /废稿.html\n"
        "\n"
        f"Sitemap: {SITE}/sitemap.xml\n"
    )


def build_post_list(posts):
    data = []
    for date, title, name in posts:
        data.append({
            "date": date,
            "title": title,
            "description": md_description(POSTS / name.replace(".html", ".md")),
            "filename": name,
        })
    write(ROOT / "post_list.json", json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    return len(data)


# ============ 主流程 ============

def main():
    ap = argparse.ArgumentParser(description="构建整站")
    ap.add_argument(
        "--site-dir",
        metavar="DIR",
        help="构建完再复制一份「干净的站点目录」到 DIR（CI 部署用，"
             "只含站点文件，不含 src/ scripts/ .git/）",
    )
    args = ap.parse_args()

    print("=" * 62)
    print("  构建整站：源在 src/ 和 posts/*.md，产物在根目录")
    print("=" * 62)

    for required in (SHELL, HEAD, SIDEBAR, POST_FRAGMENT, STYLE_SRC):
        if not required.exists():
            raise SystemExit(f"✗ 缺源文件: {required.relative_to(ROOT)}")

    print("\n[1/4] 渲染文章")
    posts = build_posts()

    print("\n[2/4] 生成页面")
    for out_name, src_file, title, desc, page_css in ROOT_PAGES:
        if not src_file.exists():
            print(f"    ⚠ 缺 {src_file.relative_to(ROOT)}，跳过 {out_name}")
            continue
        content = dedent(read_fragment(src_file))
        write(ROOT / out_name,
              render_page(title, desc, out_name, "./", content, page_css=page_css))
        extra = f"（+{page_css.name}）" if page_css else ""
        print(f"    ✓ {out_name}{extra}")

    print("\n[3/4] 生成 post_list / sitemap / robots / style.css")
    n = build_post_list(posts)
    print(f"    ✓ post_list.json（{n} 篇）")
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    write(ROOT / "sitemap.xml", build_sitemap(posts, today))
    print(f"    ✓ sitemap.xml（{3 + len(posts)} 个 URL）")
    write(ROOT / "robots.txt", build_robots())
    print("    ✓ robots.txt")
    # 用 write() 而不是 copyfile：保证产物是 LF（copyfile 会原样复制，
    # 万一源在 Windows 上被编辑器改成了 CRLF 就会带过来）
    write(STYLE_OUT, read(STYLE_SRC))
    print("    ✓ style.css")

    print("\n[4/4] 完成")
    print(f"    文章 {len(posts)} 篇，根目录页面 {len(ROOT_PAGES)} 个")

    if args.site_dir:
        import site_files
        dest = (ROOT / args.site_dir).resolve()
        n = site_files.copy_site(ROOT, dest)
        print(f"    ✓ 干净的站点目录: {dest}（{n} 个文件）")

    print("    ⚠ 根目录下的产物不要手改，改 src/ 下的源再跑一次本脚本")


if __name__ == "__main__":
    main()
