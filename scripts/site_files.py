#!/usr/bin/env python3
"""
「站点文件」清单与复制逻辑 —— 被 build.py（CI 用）和 serve.py（本地预览用）共用。

为什么需要它：
    仓库根目录里除了站点文件，还有 src/、scripts/、.git/ 等不该被公开访问的东西。
    GitHub Pages / 本地预览都只应该看到那份干净的文件集合。

    CI 里 build.py --site-dir _site 会产出一份干净的目录再上传；
    本地 serve.py 用它拼 .preview/。两边用同一份清单，不会漏文件。
"""

import shutil
from pathlib import Path

# 站点根目录下的普通文件
ROOT_FILES = [
    "index.html",
    "about.html",
    "Recent.html",
    "style.css",
    "post_list.json",
    "photos.json",
    "sitemap.xml",
    "robots.txt",
    ".nojekyll",
    # 网站的第一版手写初稿，永久保留的纪念物。
    # 它自包含（内联样式、不依赖 style.css），所以直接原样发布即可。
    # ⚠ 不要删（详见 README 和文件开头的注释）
    "废稿.html",
]

# 要一起搬的目录
DIRS = ["posts", "images"]


def copy_site(root: Path, dest: Path) -> int:
    """
    把站点文件从 root 复制到 dest（dest 会被清空重建）。
    返回复制的文件数。
    """
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)

    count = 0
    for name in ROOT_FILES:
        src = root / name
        if src.exists():
            shutil.copy2(src, dest / name)
            count += 1

    for d in DIRS:
        src_dir = root / d
        if src_dir.is_dir():
            (dest / d).mkdir(exist_ok=True)
            for f in src_dir.iterdir():
                if f.is_file() and not f.name.startswith("."):
                    # posts/ 里只搬 .html，别把 .md 也发到线上
                    if d == "posts" and f.suffix != ".html":
                        continue
                    shutil.copy2(f, dest / d / f.name)
                    count += 1

    return count
