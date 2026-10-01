#!/usr/bin/env python3
"""
本地预览工具。

流程（和 GitHub Actions 用的完全同一套）：
  1. posts/*.md  ->  posts/*.html        （pandoc + template.html）
  2. 运行 inject_layout.py                （给所有页面注入侧栏/页脚，生成 sitemap）
  3. 生成 post_list.json
  4. 把成品复制到 .preview/ 并在本地起 HTTP 服务

设计说明
--------
* 注入是「就地」做的：源文件本身就变成可独立访问的完整页面，
  这样本地看到的东西和 GitHub Pages 上的完全一致。
* 所有生成物（posts/*.html、index.html、about.html、Recent.html、
  sitemap.xml）都会被 git 跟踪 —— 它们是站点的一部分。
* 改完文件要重新运行本脚本，预览才会更新。
"""

import json
import os
import re
import shutil
import subprocess
import sys
import http.server
import webbrowser
from pathlib import Path

# Windows 的 Python 默认用 GBK 编码往控制台输出，
# 而下面的 print 里有 🚀 ✓ 📁 这些字符，会直接抛 UnicodeEncodeError 崩掉。
# 这里把标准输出/错误流强制成 UTF-8，脚本就能在任何终端里跑。
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

ROOT_DIR = Path(__file__).parent.parent
os.chdir(ROOT_DIR)

POSTS_DIR = ROOT_DIR / "posts"
PREVIEW_DIR = ROOT_DIR / ".preview"


# ========== Pandoc ==========

def check_pandoc():
    path = shutil.which("pandoc")
    if not path:
        print("  ✗ 未找到 Pandoc")
        print("    请先安装: https://pandoc.org/installing.html")
        return False
    print(f"  ✓ Pandoc: {path}")
    return True


# ========== 生成文章 HTML ==========

def convert_posts():
    """posts/*.md -> posts/*.html（用 template.html，正文里保留 $body$）"""
    md_files = sorted(POSTS_DIR.glob("*.md"))
    if not md_files:
        print("  没有找到 .md 文件")
        return []

    post_list = []
    for md_file in md_files:
        stem = md_file.stem
        m = re.match(r"^(\d{4}-\d{2}-\d{2})-(.*)$", stem)
        date_part = m.group(1) if m else ""
        title_part = m.group(2) if m else stem

        print(f"  Converting: {md_file.name}")
        cmd = [
            "pandoc", str(md_file),
            "-f", "markdown+tex_math_dollars",
            f"--template={ROOT_DIR / 'template.html'}",
            "--metadata", f"title={title_part}",
            "--mathjax",
            "-o", str(POSTS_DIR / f"{stem}.html"),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"    ✗ 失败: {result.stderr.strip()[:200]}")
            continue
        post_list.append((date_part, title_part, f"{stem}.html"))

    post_list.sort(key=lambda x: x[0], reverse=True)
    return post_list


# ========== 简介提取 ==========

def extract_description(md_filename: str) -> str:
    """从 md 开头提取第一段 _斜体_（或 *斜体*）作为简介"""
    filepath = POSTS_DIR / md_filename
    if not filepath.exists():
        return ""
    content = filepath.read_text(encoding="utf-8")
    m = re.search(r"_(.+?)_", content, re.DOTALL) or re.search(
        r"\*(.+?)\*", content, re.DOTALL
    )
    if not m:
        return ""
    text = m.group(1)
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"`(.+?)`", r"\1", text)
    text = re.sub(r"~~(.+?)~~", r"\1", text)
    text = re.sub(r"\[(.+?)\]\(.+?\)", r"\1", text)
    text = re.sub(r"!\[.*?\]\(.+?\)", "", text)
    text = text.strip()
    if len(text) > 150:
        text = text[:147] + "..."
    return text


def generate_post_list_json(items, dest: Path):
    data = []
    for date_str, title, filename in items:
        data.append({
            "date": date_str,
            "title": title,
            "description": extract_description(filename.replace(".html", ".md")),
            "filename": filename,
        })
    dest.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"  ✓ post_list.json（{len(data)} 篇）")


# ========== 注入侧栏（委托给 inject_layout.py，和 CI 共用） ==========

def run_inject_layout():
    print("  运行 inject_layout.py（注入侧栏 + 生成 sitemap/robots）...")
    result = subprocess.run(
        [sys.executable, str(ROOT_DIR / "scripts" / "inject_layout.py")],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if result.returncode != 0:
        print("  ✗ 注入失败：")
        print((result.stdout or "")[-2000:])
        print((result.stderr or "")[-2000:])
        return False
    # 只打印汇总行
    for line in (result.stdout or "").splitlines():
        if "完成" in line or "sitemap" in line or "robots" in line:
            print("  " + line.strip())
    return True


# ========== 准备预览目录 ==========

def prepare_preview(items):
    """
    把成品复制到 .preview/。
    源文件本身已经是最终形态（注入过了），所以这里基本就是「照抄」。
    """
    if PREVIEW_DIR.exists():
        shutil.rmtree(PREVIEW_DIR)
    PREVIEW_DIR.mkdir(parents=True)

    # 根目录的静态资源与页面
    for name in ("style.css", "index.html", "about.html", "Recent.html",
                 "sitemap.xml", "robots.txt"):
        src = ROOT_DIR / name
        if src.exists():
            shutil.copy2(src, PREVIEW_DIR / name)

    # post_list.json（稍后写入，先复制旧的占位也行）
    for name in ("photos.json",):
        src = ROOT_DIR / name
        if src.exists():
            shutil.copy2(src, PREVIEW_DIR / name)

    # images/
    if (ROOT_DIR / "images").is_dir():
        shutil.copytree(ROOT_DIR / "images", PREVIEW_DIR / "images")

    # posts/（.md 不用复制）
    (PREVIEW_DIR / "posts").mkdir()
    for f in POSTS_DIR.glob("*.html"):
        shutil.copy2(f, PREVIEW_DIR / "posts" / f.name)

    # 生成 post_list.json 到预览目录
    generate_post_list_json(items, PREVIEW_DIR / "post_list.json")

    print(f"  ✓ 已构建预览目录: {PREVIEW_DIR}")


def check_photos_json():
    """
    照片墙的数据来源是 photos.json。
    这里【只检查、绝不请求 API】—— 配额必须由你手动跑 fetch_photos.py 时消耗。
    """
    src = ROOT_DIR / "photos.json"
    if src.exists():
        try:
            n = len(json.loads(src.read_text(encoding="utf-8")).get("photos", []))
        except Exception:
            n = "?"
        print(f"  ✓ photos.json 已就位（{n} 张，读取本地快照，未消耗 API 配额）")
    else:
        print("  ⚠ 没找到 photos.json，照片墙会是空的")
        print("    想拉取照片请手动运行： python scripts/fetch_photos.py")


# ========== 服务器 ==========

def start_server(port=8000):
    class QuietHandler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(PREVIEW_DIR), **kwargs)

        def log_message(self, format, *args):
            pass

    def make_server(p):
        # 多线程：浏览器加载一个页面会并发抓 html/css/js/图片，
        # 单线程的 TCPServer 遇到一个慢连接就会把整个服务器卡住。
        srv = http.server.ThreadingHTTPServer(("127.0.0.1", p), QuietHandler)
        srv.allow_reuse_address = True
        return srv

    server = None
    for candidate in range(port, port + 10):
        try:
            server = make_server(candidate)
            port = candidate
            break
        except OSError:
            print(f"  端口 {candidate} 已被占用，尝试 {candidate + 1} ...")

    if server is None:
        print(f"  ✗ 端口 {port} ~ {port + 9} 全被占用")
        return

    print(f"\n{'=' * 56}")
    print(f"  🌐 预览地址: http://localhost:{port}")
    print(f"  📁 预览目录: {PREVIEW_DIR}")
    print(f"  ℹ️  按 Ctrl+C 停止")
    print(f"  💡 改完文件要重新运行本脚本")
    print(f"{'=' * 56}\n")

    webbrowser.open(f"http://localhost:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  服务器已停止")
    finally:
        server.server_close()


# ========== 主程序 ==========

def main():
    print("=" * 56)
    print("  zly3070.github.io 本地预览")
    print("  流程：pandoc -> 注入侧栏 -> 生成列表 -> 起服务")
    print("=" * 56)

    print("\n📋 检查环境...")
    if not check_pandoc():
        sys.exit(1)

    print("\n📝 转换 Markdown...")
    items = convert_posts()

    print("\n🧩 注入侧栏 / 生成 sitemap...")
    if not run_inject_layout():
        sys.exit(1)

    print("\n📦 构建预览目录...")
    prepare_preview(items)

    print("\n📷 检查照片墙数据...")
    check_photos_json()

    print("\n🌍 启动服务器...")
    start_server()


if __name__ == "__main__":
    main()
