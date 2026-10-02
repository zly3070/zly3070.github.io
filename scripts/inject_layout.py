#!/usr/bin/env python3
"""
把 _partials/sidebar.html（侧栏 + 页脚）注入到每个页面里，
让每个页面都成为「自带侧栏、可独立访问、真链接」的完整页面。

同时生成 sitemap.xml 和 robots.txt。

设计要点
--------
* 侧栏/页脚只在 _partials/sidebar.html 里维护一份，改一次全站生效。
* {{BASE}} 是到站点根目录的相对前缀：
    根目录的页面（index / about / Recent）用 "./"
    posts/ 里的文章页用 "../"
  这样侧栏里的图片、链接在任何深度都能正确解析。
* 幂等：重复运行结果一致，不会嵌套、不会重复插入。

用法
----
    python scripts/inject_layout.py            # 注入所有页面 + 生成 sitemap/robots
    python scripts/inject_layout.py --check    # 只检查，不写文件
"""

import argparse
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

ROOT = Path(__file__).parent.parent
PARTIALS = ROOT / "_partials"
SIDEBAR = PARTIALS / "sidebar.html"
HOMEPAGE = PARTIALS / "homepage.html"

SITE = "https://zly3070.github.io"

# 根目录页面的 meta description（文章页的从 markdown 里自动抽）
PAGE_DESCRIPTIONS = {
    "index.html": "波球存放思考和摄影的地方",
    "about.html": "关于我：浙江工业大学计算机专业，正在学计算机图形学，喜欢摄影。",
    "Recent.html": "所有文章列表：学习笔记、论文精读、技术思考。",
}

LAYOUT_START = "<!-- LAYOUT_START -->"
LAYOUT_END = "<!-- LAYOUT_END -->"
CONTAINER_START = "<!-- CONTAINER_START -->"
CONTAINER_END = "<!-- CONTAINER_END -->"
CONTENT_SLOT = "<!-- CONTENT_SLOT -->"


def read(path: Path):
    return path.read_text(encoding="utf-8")


def extract_container(html: str):
    """取出页面自己的正文（CONTAINER_START/END 之间），并返回去掉这段后的骨架"""
    m = re.search(
        re.escape(CONTAINER_START) + r"(.*?)" + re.escape(CONTAINER_END),
        html,
        re.DOTALL,
    )
    if not m:
        return None, html
    return m.group(1).strip("\n"), html


def render_layout(sidebar: str, base: str, content: str) -> str:
    """
    把侧栏模板渲染成最终 HTML。

    ⚠ 正文外面必须保留 CONTAINER_START / CONTAINER_END 标记：
       LAYOUT 区域每次注入都会被整体替换，而正文就住在 LAYOUT 里面。
       如果不留标记，第一次注入之后正文就再也找不回来了
       （第二次运行会报「没有 CONTAINER 标记」并跳过所有页面）。

    ⚠ 正文必须先去掉每行左侧缩进再重新缩进：否则每次注入都会在标记上
       再叠一层缩进，文件永远「有变化」，幂等性就没了。
    """
    # 1) 校验骨架，此时还没插正文
    skeleton = sidebar.replace("{{BASE}}", base)
    leftovers = sorted(set(re.findall(r"\{\{[A-Z_]+\}\}", skeleton)))
    if leftovers:
        raise SystemExit(f"✗ 侧栏模板里有没替换的占位符: {leftovers}")

    # 2) 正文里的 {{BASE}} 也要按页面深度替换
    content = content.replace("{{BASE}}", base)

    # 3) 正文各行先去掉缩进（保持内部相对缩进），再统一缩进一级
    lines = content.strip("\n").split("\n")
    # 找出非空行的最小缩进，整体去掉它
    indents = [len(l) - len(l.lstrip()) for l in lines if l.strip()]
    base_indent = min(indents) if indents else 0
    body_lines = [
        ("    " + l[base_indent:]) if l.strip() else "" for l in lines
    ]

    block = (
        "    " + CONTAINER_START + "\n"
        + "\n".join(body_lines)
        + "\n    " + CONTAINER_END
    )

    # 4) 放进内容槽
    skeleton = skeleton.replace("    <!-- CONTENT_SLOT -->", block)
    skeleton = skeleton.replace(CONTENT_SLOT, block)
    return skeleton


def inject(path: Path, sidebar: str, base: str, content: str, check: bool) -> bool:
    """把一个页面的 LAYOUT 区域换成渲染好的布局。返回是否有变化"""
    html = read(path)
    if LAYOUT_START not in html or LAYOUT_END not in html:
        print(f"  ⚠ {path.name}: 没有 LAYOUT 标记，跳过")
        return False

    rendered = render_layout(sidebar, base, content)

    # 取出页面上现有的 LAYOUT 区域，比较时把空白归一化 ——
    # 否则「缩进差一点」就会被当成「有变化」，每次运行都报更新
    m = re.search(
        re.escape(LAYOUT_START) + r"(.*?)" + re.escape(LAYOUT_END),
        html,
        re.DOTALL,
    )
    existing = m.group(1) if m else ""
    if m and re.sub(r"\s+", " ", existing).strip() == re.sub(r"\s+", " ", rendered).strip():
        return False  # 内容等价，不动文件（保住幂等性）

    block = f"{LAYOUT_START}\n{rendered.strip(chr(10))}\n    {LAYOUT_END}"
    new_html = re.sub(
        re.escape(LAYOUT_START) + r".*?" + re.escape(LAYOUT_END),
        lambda _m: block,
        html,
        count=1,
        flags=re.DOTALL,
    )

    if new_html == html:
        return False
    if not check:
        path.write_text(new_html, encoding="utf-8", newline="")
    return True


def build_sitemap(pages) -> str:
    """
    pages: [(相对路径, 优先级, lastmod)]
    """
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    for rel, priority, lastmod in pages:
        lines += [
            "  <url>",
            f"    <loc>{xml_escape(SITE + '/' + rel)}</loc>",
            f"    <lastmod>{lastmod}</lastmod>",
            f"    <priority>{priority}</priority>",
            "  </url>",
        ]
    lines.append("</urlset>")
    return "\n".join(lines) + "\n"


def build_robots() -> str:
    return (
        "# 全部允许抓取\n"
        "User-agent: *\n"
        "Allow: /\n"
        "\n"
        "# 草稿和模板不是页面，别浪费抓取配额\n"
        "Disallow: /template.html\n"
        "Disallow: /废稿.html\n"
        "Disallow: /_partials/\n"
        "\n"
        f"Sitemap: {SITE}/sitemap.xml\n"
    )


def read_post_list():
    """从 posts/*.html 得到文章列表（按文件名倒序 = 最新在前）"""
    posts_dir = ROOT / "posts"
    if not posts_dir.is_dir():
        return []
    files = sorted(posts_dir.glob("*.html"), key=lambda p: p.name, reverse=True)
    return [p.name for p in files]


def md_description(html_name: str) -> str:
    """
    从同名 .md 里抽第一段 _斜体_ 作为简介，用作 <meta name="description">。
    直接从 markdown 抽，不依赖 post_list.json 是否已生成（避免构建顺序耦合）。
    """
    md = ROOT / "posts" / html_name.replace(".html", ".md")
    if not md.exists():
        return ""
    text = md.read_text(encoding="utf-8")
    m = re.search(r"_(.+?)_", text, re.DOTALL) or re.search(
        r"\*(.+?)\*", text, re.DOTALL
    )
    if not m:
        return ""
    t = m.group(1)
    t = re.sub(r"\*\*(.+?)\*\*", r"\1", t)
    t = re.sub(r"`(.+?)`", r"\1", t)
    t = re.sub(r"~~(.+?)~~", r"\1", t)
    t = re.sub(r"\[(.+?)\]\(.+?\)", r"\1", t)
    t = re.sub(r"!\[.*?\]\(.+?\)", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    # 几篇老文章的占位符是 "short discrption"，放进搜索结果很难看，直接丢弃
    if t.lower().replace(" ", "") in ("shortdiscrption", "shortdescription", ""):
        return ""
    if len(t) > 150:
        t = t[:147] + "..."
    return t


def url_for(rel_path: str) -> str:
    """
    把仓库里的相对路径变成合法的规范 URL。
    必须做百分号编码：文件名里有空格、&、中文，
    直接塞进 href 里是错的（& 会被当成参数分隔符）。
    """
    from urllib.parse import quote

    return SITE + "/" + quote(rel_path)


def patch_head_meta(path: Path, desc: str, canonical: str, check: bool) -> int:
    """
    补齐页面 <head> 里的两个 SEO 标签：
      * <link rel="canonical">  本页唯一正式地址
      * <meta name="description">  搜索结果里的摘要

    已经存在就更新，不存在就插在 <title> 之后。
    返回改了几处（0 表示没动）。
    """
    html = read(path)
    orig = html
    n = 0

    # ---- canonical ----
    m = re.search(r'(<link\s+rel="canonical"\s+href=")([^"]*)(")', html)
    if m:
        if m.group(2) != canonical:
            html = html[: m.start(2)] + canonical + html[m.end(2):]
            n += 1
    else:
        m2 = re.search(r"(<title>.*?</title>\n)", html, re.DOTALL)
        if m2:
            tag = f'    <link rel="canonical" href="{canonical}" />\n'
            html = html[: m2.end(1)] + tag + html[m2.end(1):]
            n += 1

    # ---- description ----
    if desc:
        safe = desc.replace('"', "&quot;")
        m = re.search(r'(<meta\s+name="description"\s+content=")([^"]*)(")', html)
        if m:
            if m.group(2) != desc:
                html = html[: m.start(2)] + safe + html[m.end(2):]
                n += 1
        else:
            m2 = re.search(r"(<title>.*?</title>\n)", html, re.DOTALL)
            if m2:
                tag = f'    <meta name="description" content="{safe}" />\n'
                html = html[: m2.end(1)] + tag + html[m2.end(1):]
                n += 1

    if html == orig:
        return 0
    if not check:
        path.write_text(html, encoding="utf-8", newline="")
    return n


def sitemap_lastmod_for(filename: str, default: str) -> str:
    """
    文章页的 lastmod 用文件名里的日期（YYYY-MM-DD-标题）。
    GitHub Pages 上没法方便地拿到每篇的提交时间，用文章日期更贴切，
    也比「全部写今天」更有信息量。
    """
    m = re.match(r"^(\d{4}-\d{2}-\d{2})-", filename)
    return m.group(1) if m else default


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="只检查，不写文件")
    args = ap.parse_args()

    if not SIDEBAR.exists():
        raise SystemExit(f"✗ 缺 {SIDEBAR.relative_to(ROOT)}")
    sidebar = read(SIDEBAR)

    print("=" * 60)
    print("  注入侧栏 + 生成 sitemap/robots")
    print("=" * 60)

    changed_count = 0

    # ---------- 根目录的页面 ----------
    print("\n[根目录页面]")
    root_pages = [
        ("index.html", HOMEPAGE),   # 首页正文来自 _partials/homepage.html
        ("about.html", None),        # 正文在页面自己的 CONTAINER 里
        ("Recent.html", None),
    ]
    for name, content_source in root_pages:
        path = ROOT / name
        if not path.exists():
            print(f"  - {name}: 不存在，跳过")
            continue
        if content_source is not None:
            if not content_source.exists():
                print(f"  ⚠ {name}: 缺 {content_source.name}，跳过")
                continue
            content = read(content_source).strip("\n")
        else:
            content, _ = extract_container(read(path))
            if content is None:
                print(f"  ⚠ {name}: 没有 CONTAINER 标记，跳过")
                continue
        if inject(path, sidebar, "./", content, args.check):
            changed_count += 1
            print(f"  ✓ {name}")
        else:
            print(f"  = {name}（无变化）")
        # 补 canonical + meta description
        n = patch_head_meta(
            path,
            PAGE_DESCRIPTIONS.get(name, ""),
            url_for(name),
            args.check,
        )
        if n:
            print(f"    ├ 已补 canonical / description（{n} 处）")

    # ---------- posts/ 里的文章 ----------
    print("\n[文章页 posts/]")
    posts = []
    for name in read_post_list():
        path = ROOT / "posts" / name
        content, _ = extract_container(read(path))
        if content is None:
            print(f"  ⚠ posts/{name}: 没有 CONTAINER 标记，跳过")
            continue
        if inject(path, sidebar, "../", content, args.check):
            changed_count += 1
            print(f"  ✓ posts/{name}")
        else:
            print(f"  = posts/{name}（无变化）")
        # 文章页的 description 从同名 .md 抽；canonical 按真实文件名（含编码）
        n = patch_head_meta(
            path,
            md_description(name),
            url_for(f"posts/{name}"),
            args.check,
        )
        if n:
            print(f"    ├ 已补 canonical / description（{n} 处）")
        posts.append(name)

    # ---------- sitemap + robots ----------
    print("\n[sitemap / robots]")
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    pages = [
        ("index.html", "1.0", today),
        ("Recent.html", "0.8", today),
        ("about.html", "0.7", today),
    ]
    # 文章页用文件名里的日期当 lastmod，比全部写今天更有信息量
    pages += [
        (f"posts/{n}", "0.6", sitemap_lastmod_for(n, today)) for n in posts
    ]
    sitemap = build_sitemap(pages)
    robots = build_robots()

    sm_path = ROOT / "sitemap.xml"
    rb_path = ROOT / "robots.txt"
    if not args.check:
        sm_path.write_text(sitemap, encoding="utf-8", newline="")
        rb_path.write_text(robots, encoding="utf-8", newline="")
    print(f"  ✓ sitemap.xml（{len(pages)} 个 URL）")
    print(f"  ✓ robots.txt")

    print("")
    print(f"  完成：{changed_count} 个页面被更新"
          + ("（--check 模式，未写盘）" if args.check else ""))
    print(f"  文章数：{len(posts)}")


if __name__ == "__main__":
    main()
