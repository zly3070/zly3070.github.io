#!/usr/bin/env python3
"""
本地预览。

    python scripts/serve.py

做三件事：
    1. 调用 scripts/build.py 构建整站
    2. 把成品复制到 .preview/（连同 images/）
    3. 起一个本地 HTTP 服务器并打开浏览器

为什么需要 .preview/ 这一层：
    仓库根目录里除了站点文件，还有 src/、scripts/、.git/ 等不该被访问的东西。
    .preview/ 只放站点真正需要的文件，和 GitHub Pages 上看到的一致。

⚠ 改完 src/ 下的源或 posts/*.md，要重新运行本脚本预览才会更新。
"""

import http.server
import os
import shutil
import subprocess
import sys
import webbrowser
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

ROOT = Path(__file__).parent.parent
PREVIEW = ROOT / ".preview"

sys.path.insert(0, str(Path(__file__).parent))
import site_files  # noqa: E402  （站点文件清单，和 CI 共用一份）


def build():
    """调用唯一的构建入口"""
    r = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "build.py")],
        cwd=ROOT, text=True, encoding="utf-8", errors="replace",
    )
    return r.returncode == 0


def prepare_preview():
    """把站点文件复制到 .preview/（先整个重建，避免残留旧文件）"""
    n = site_files.copy_site(ROOT, PREVIEW)
    print(f"    ✓ 已复制 {n} 个文件到 .preview/")
    return True


def check_photos_json():
    """照片墙数据。只检查，绝不请求 API —— 配额留给 fetch_photos.py。"""
    src = ROOT / "photos.json"
    if not src.exists():
        print("    ⚠ 没找到 photos.json，照片墙会是空的")
        print("      想拉取照片请手动运行： python scripts/fetch_photos.py")
        return
    try:
        import json
        n = len(json.loads(src.read_text(encoding="utf-8")).get("photos", []))
    except Exception:
        n = "?"
    print(f"    ✓ photos.json 已就位（{n} 张，读的是本地快照，未消耗 API 配额）")


def start_server(port=8000):
    class CleanUrlHandler(http.server.SimpleHTTPRequestHandler):
        """
        让本地预览的 URL 行为和 GitHub Pages 一致。

        页面里的「~/」链接指向目录（根目录页面是 "./"，文章页是 "../"），
        这样地址栏显示的是干净的 zly3070.github.io 而不是 .../index.html。

        但 Python 自带的 SimpleHTTPRequestHandler 遇到目录会做两件坏事：
          - 路径不带斜杠时，跳到一个带斜杠的 URL（/index.html -> /index.html/ 之类）
          - 路径带斜杠时，直接列出目录内容，而不是送 index.html
        GitHub Pages 的行为是「目录请求 -> 送该目录下的 index.html」，
        这里照它实现，本地看到的就是线上看到的样子。
        """

        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(PREVIEW), **kwargs)

        def log_message(self, fmt, *args):
            pass

        def send_head(self):
            path = self.translate_path(self.path)

            # 目录 -> 直接送 index.html（不重定向、不列目录）
            if os.path.isdir(path):
                index = os.path.join(path, "index.html")
                if os.path.isfile(index):
                    orig, self.path = self.path, self.path.rstrip("/") + "/index.html"
                    try:
                        return super().send_head()
                    finally:
                        self.path = orig

            return super().send_head()

    server = None
    for candidate in range(port, port + 10):
        try:
            # 多线程：一个页面会并发抓 html/css/js/图片，
            # 单线程服务器遇到慢连接会把整个服务卡住（踩过）。
            server = http.server.ThreadingHTTPServer(("127.0.0.1", candidate), CleanUrlHandler)
            server.allow_reuse_address = True
            port = candidate
            break
        except OSError:
            print(f"    端口 {candidate} 被占用，试 {candidate + 1} …")

    if server is None:
        print(f"    ✗ 端口 {port}~{port + 9} 全被占用")
        return

    url = f"http://localhost:{port}"
    print()
    print("=" * 56)
    print(f"  🌐 预览地址: {url}")
    print(f"  📁 预览目录: {PREVIEW}")
    print("  ℹ️  按 Ctrl+C 停止")
    print("  💡 改完 src/ 下的源要重新运行本脚本")
    print("=" * 56)
    print()

    webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  服务器已停止")
    finally:
        server.server_close()


def main():
    print("=" * 56)
    print("  zly3070.github.io 本地预览")
    print("  流程：build.py 构建 -> 复制到 .preview -> 起服务")
    print("=" * 56)

    print("\n🔨 构建整站 …")
    if not build():
        print("\n  ✗ 构建失败，已中止")
        sys.exit(1)

    print("\n📦 准备预览目录 …")
    prepare_preview()

    print("\n📷 检查照片墙数据 …")
    check_photos_json()

    print("\n🌍 启动服务器 …")
    start_server()


if __name__ == "__main__":
    main()
