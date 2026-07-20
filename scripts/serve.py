#!/usr/bin/env python3
"""
本地预览工具：
1. 将 somePosts/*.md 转为 HTML（生成到临时目录）
2. 生成文章列表 HTML
3. 替换 home.html 的文章列表区域
4. 启动本地 HTTP 服务器预览
所有生成的文件都在 .preview/ 目录下，不会覆盖原文件
"""

import os
import sys
import re
import subprocess
import http.server
import socketserver
import webbrowser
import shutil
from pathlib import Path

# 项目根目录
ROOT_DIR = Path(__file__).parent.parent
os.chdir(ROOT_DIR)

POSTS_DIR = ROOT_DIR / "somePosts"

# ========== 第一步：检查 Pandoc ==========

def check_pandoc():
    """检查 pandoc 是否可用"""
    pandoc_path = shutil.which("pandoc")
    if pandoc_path:
        print(f"  ✓ Pandoc 已找到: {pandoc_path}")
        result = subprocess.run(["pandoc", "--version"], capture_output=True, text=True)
        version_line = result.stdout.split("\n")[0]
        print(f"    版本: {version_line}")
        return True
    else:
        print("  ✗ 未找到 Pandoc")
        print("    请先安装 Pandoc: https://pandoc.org/installing.html")
        return False


# ========== 第二步：准备临时目录 ==========

def prepare_preview_dir():
    """创建 .preview 目录并复制静态文件"""
    preview_dir = ROOT_DIR / ".preview"
    
    # 如果已存在，先删除
    if preview_dir.exists():
        shutil.rmtree(preview_dir)
    
    # 创建目录结构
    (preview_dir / "somePosts").mkdir(parents=True)
    (preview_dir / "images").mkdir()
    
    # 复制 images
    if (ROOT_DIR / "images").exists():
        for f in (ROOT_DIR / "images").iterdir():
            if f.is_file():
                shutil.copy2(f, preview_dir / "images" / f.name)
    
    # 复制 CSS
    if (ROOT_DIR / "style.css").exists():
        shutil.copy2(ROOT_DIR / "style.css", preview_dir / "style.css")
    
    # 复制 index.html
    if (ROOT_DIR / "index.html").exists():
        shutil.copy2(ROOT_DIR / "index.html", preview_dir / "index.html")
    
    # 复制其他静态 HTML
    for f in ROOT_DIR.glob("*.html"):
        if f.name not in ("index.html", "home.html"):
            shutil.copy2(f, preview_dir / f.name)
    
    print(f"  ✓ 已创建临时目录: {preview_dir}")
    return preview_dir


# ========== 第三步：转换 .md -> .html（到临时目录）==========

def convert_md_to_html(preview_dir):
    """将 somePosts/ 下的所有 .md 文件转为 .html 到临时目录"""
    md_files = sorted(POSTS_DIR.glob("*.md"))
    if not md_files:
        print("  没有找到 .md 文件")
        return []
    
    post_list = []
    
    for md_file in md_files:
        filename = md_file.stem
        
        # 提取日期
        date_match = re.match(r'^(\d{4}-\d{2}-\d{2})', filename)
        date_part = date_match.group(1) if date_match else ""
        
        # 提取标题
        title_part = re.sub(r'^\d{4}-\d{2}-\d{2}-', '', filename)
        
        output_html = preview_dir / "somePosts" / f"{filename}.html"
        
        print(f"  Converting: {md_file.name}")
        
        # 调用 pandoc
        cmd = [
            "pandoc",
            str(md_file),
            "-f", "markdown+tex_math_dollars",
            f"--template={ROOT_DIR / 'template.html'}",
            "--metadata", f"title={title_part}",
            "--mathjax",
            "-o", str(output_html)
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"    ✗ 转换失败: {result.stderr}")
            continue
        
        print(f"    ✓ {output_html.name}")
        
        post_list.append((date_part, title_part, f"{filename}.html"))
    
    # 按日期倒序
    post_list.sort(key=lambda x: x[0], reverse=True)
    
    return post_list


# ========== 第四步：提取简介 ==========

def extract_description(md_filename):
    """从 md 文件开头提取第一段 _斜体_ 中的纯文本"""
    filepath = POSTS_DIR / md_filename
    if not filepath.exists():
        return ""
    
    content = filepath.read_text(encoding='utf-8')
    
    match = re.search(r'_(.+?)_', content, re.DOTALL)
    if not match:
        match = re.search(r'\*(.+?)\*', content, re.DOTALL)
    if not match:
        return ""
    
    text = match.group(1)
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'`(.+?)`', r'\1', text)
    text = re.sub(r'~~(.+?)~~', r'\1', text)
    text = re.sub(r'\[(.+?)\]\(.+?\)', r'\1', text)
    text = re.sub(r'!\[.*?\]\(.+?\)', '', text)
    text = text.strip()
    
    if len(text) > 150:
        text = text[:147] + "..."
    
    return text


def format_date(date_str):
    """将 2026-03-26 格式化为 26 Mar 2026"""
    if not date_str:
        return ""
    try:
        from datetime import datetime
        date_obj = datetime.strptime(date_str, '%Y-%m-%d')
        return date_obj.strftime("%d %b %Y")
    except:
        return date_str


def generate_post_items(items):
    """生成文章列表的 HTML"""
    html_items = []
    
    for date_str, title, filename in items:
        formatted_date = format_date(date_str)
        
        md_filename = filename.replace('.html', '.md')
        description = extract_description(md_filename)
        
        desc_html = f'<p style="font-size: 16px;">{description}</p>' if description else ''
        
        item = f'''
          <div style="display:flex">
            <span style="font-family: Consolas; font-size: 16px; color: #666666; white-space: nowrap;">
              {formatted_date}&nbsp
            </span>
            <div style="display:flex; flex-direction:column; gap:1px">
              <a
                href="somePosts/{filename}"
                style="font-size: 18px; width: fit-content;"
                class="post-title"
                target="main-frame"
              >
                {title}
              </a>
              {desc_html}
            </div>
          </div>'''
        
        html_items.append(item)
    
    return '\n'.join(html_items)


# ========== 第五步：生成 home.html（到临时目录）==========

def generate_home_html(preview_dir, post_items):
    """读取原 home.html，替换文章列表部分，写入临时目录"""
    src_home = ROOT_DIR / "home.html"
    dst_home = preview_dir / "home.html"
    
    content = src_home.read_text(encoding='utf-8')
    
    start_marker = '<!-- POST_LIST_START -->'
    end_marker = '<!-- POST_LIST_END -->'
    
    if start_marker not in content or end_marker not in content:
        print("  ⚠ home.html 中未找到 POST_LIST 标记，直接复制原文件")
        shutil.copy2(src_home, dst_home)
        return
    
    pattern = re.compile(re.escape(start_marker) + r'.*?' + re.escape(end_marker), re.DOTALL)
    new_block = f'{start_marker}{post_items}{end_marker}'
    content = pattern.sub(new_block, content)
    
    dst_home.write_text(content, encoding='utf-8')
    print("  ✓ 已生成 home.html（含最新文章列表）")


# ========== 第六步：处理 about.html ==========

def generate_about_html(preview_dir):
    """处理 about.html"""
    src_about = ROOT_DIR / "about.html"
    md_file = ROOT_DIR / "more_about_me.md"
    dst_about = preview_dir / "about.html"
    
    if src_about.exists():
        # 复制现有的 about.html，修正路径
        content = src_about.read_text(encoding='utf-8')
        content = content.replace('../images/', 'images/')
        content = content.replace('href="../home.html"', 'href="home.html"')
        dst_about.write_text(content, encoding='utf-8')
        print("  ✓ 已复制 about.html")
    elif md_file.exists():
        print("  Converting: more_about_me.md -> about.html")
        cmd = [
            "pandoc",
            str(md_file),
            f"--template={ROOT_DIR / 'template.html'}",
            "--metadata", "title=About Me",
            "-o", str(dst_about)
        ]
        subprocess.run(cmd, capture_output=True, text=True)
        print("  ✓ 已生成 about.html")


# ========== 第七步：启动服务器 ==========

def start_server(preview_dir, port=8000):
    """在临时目录启动 HTTP 服务器"""
    
    class QuietHandler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(preview_dir), **kwargs)
        
        def log_message(self, format, *args):
            pass
    
    try:
        server = socketserver.TCPServer(("", port), QuietHandler)
        print(f"\n{'=' * 50}")
        print(f"  🌐 本地预览地址: http://localhost:{port}")
        print(f"  📁 临时目录: {preview_dir}")
        print(f"  ℹ️  按 Ctrl+C 停止服务器")
        print(f"  💡 修改文件后，重新运行本脚本即可刷新")
        print(f"{'=' * 50}\n")
        
        webbrowser.open(f"http://localhost:{port}")
        server.serve_forever()
    except OSError:
        print(f"  端口 {port} 已被占用，尝试端口 {port+1}...")
        start_server(preview_dir, port + 1)
    except KeyboardInterrupt:
        print("\n  服务器已停止")
        server.server_close()


# ========== 主程序 ==========

def main():
    print("=" * 50)
    print("  🚀 zly3070.github.io 本地预览工具")
    print("  📌 所有生成文件在 .preview/ 目录下")
    print("  📌 不会修改任何原文件")
    print("=" * 50)
    
    print("\n📋 检查环境...")
    if not check_pandoc():
        sys.exit(1)
    
    print("\n📁 准备临时目录...")
    preview_dir = prepare_preview_dir()
    
    print("\n📝 转换 Markdown 文件...")
    post_list = convert_md_to_html(preview_dir)
    
    print("\n📄 生成文章列表...")
    post_items = generate_post_items(post_list) if post_list else ""
    
    print("\n🏠 生成 home.html...")
    generate_home_html(preview_dir, post_items)
    
    print("\n👤 处理 about.html...")
    generate_about_html(preview_dir)
    
    print("\n🌍 启动本地服务器...")
    start_server(preview_dir)


if __name__ == "__main__":
    main()
