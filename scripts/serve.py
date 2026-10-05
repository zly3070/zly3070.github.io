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


def port_in_use(port: int) -> bool:
    """
    这个端口上是不是已经有东西在服务了。

    不用 bind 来试探 —— Windows 上 SO_REUSEADDR 允许重复绑定，
    bind 成功不代表端口空闲。改成真的去连一下：
    连得上就说明有人在那儿，连不上才认为是空的。

    （注意：不能用 bind 之外的猜测。人家就是因为只靠 bind 的 OSError，
      导致两个服务器同时 LISTEN 在 8000，刷新看到的一直是旧代码。）
    """
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", port)) == 0


def start_server(port=8000):
    class CleanUrlHandler(http.server.SimpleHTTPRequestHandler):
        # ⚠ 字体必须补进 extensions_map，不能在子类里覆写 guess_type。
        #   原因：SimpleHTTPRequestHandler.guess_type() 只查它自己的
        #   extensions_map，【不会】去查系统的 mimetypes 表。
        #   而 Python 标准库里压根没有 .woff2（实测 guess_type 返回 (None, None)），
        #   于是默认给出 application/octet-stream。
        #   GitHub Pages 会正确返回 font/woff2 —— 本地要和线上一致，
        #   否则"本地好的线上坏"这类问题查不出来。
        extensions_map = {
            **http.server.SimpleHTTPRequestHandler.extensions_map,
            ".woff2": "font/woff2",
            ".woff": "font/woff",
            ".webp": "image/webp",
            ".json": "application/json",
            ".svg": "image/svg+xml",
        }
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
        # ⚠ 先主动探测这个端口是否【真的】没人服务，再尝试绑定。
        #
        # 为什么不能只靠 bind 抛 OSError：
        #   Windows 上 allow_reuse_address 会允许第二个服务器绑到同一个端口，
        #   于是两个进程同时 LISTEN，请求被其中任意一个接收。
        #   结果极难查：新代码明明写对了，你刷新页面看到的却还是旧响应
        #   （人家在这上面浪费了大量时间 —— netstat 显示 8000 上有两个 PID）。
        if port_in_use(candidate):
            print(f"    端口 {candidate} 已被占用（探测到有服务在响应），试 {candidate + 1} …")
            continue
        try:
            # 多线程：一个页面会并发抓 html/css/js/图片，
            # 单线程服务器遇到慢连接会把整个服务卡住（踩过）。
            server = http.server.ThreadingHTTPServer(("127.0.0.1", candidate), CleanUrlHandler)
            port = candidate
            break
        except OSError:
            print(f"    端口 {candidate} 绑定失败，试 {candidate + 1} …")

    if server is None:
        print(f"    ✗ 端口 {port}~{port + 9} 全被占用")
        return

    # ⚠ 换过端口就要说清楚，而且要显眼。
    #   否则会出现很难查的状况：旧服务器还在 8000 上跑着，新服务器默默跑到 8001，
    #   用户照旧打开 localhost:8000 —— 看到的始终是旧代码，
    #   于是"明明改了却不生效"（人家在这上面浪费了很多时间）。
    if port != 8000:
        print()
        print("  " + "!" * 52)
        print(f"  ⚠ 8000 被占用，本次预览在 {port} 端口")
        print(f"  ⚠ 请打开 http://localhost:{port} 而不是 localhost:8000")
        print("  ⚠ 用 8000 的话你看到的会是【上一个】还活着的服务器（旧代码）")
        print("  " + "!" * 52)

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
