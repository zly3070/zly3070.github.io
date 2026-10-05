#!/usr/bin/env python3
"""
下载自托管字体（Roboto Condensed）到仓库的 fonts/ 目录。

    python scripts/fetch_fonts.py

跑一次就够了 —— 字体文件会进 git，以后线上和本地都直接从你的仓库取，
不再依赖 Google 的 CDN。所以之后访客不必翻墙也能看到正确字体。

需要一次性联网（第一次跑的时候要能访问 fonts.gstatic.com）。

为什么不用 Google Fonts 的 CDN：
    本站的设计前提之一就是「访客不必翻墙」。而 fonts.googleapis.com /
    fonts.gstatic.com 在国内多数网络下访问不了，字体就会静默回退，
    侧栏看起来和没设置字体一样。自己托管没有这个问题。

字体来源
--------
Google Fonts 官方仓库的 woff2 文件（Roboto Condensed v31，latin 子集）。
URL 是写死的 —— 好处是版本钉死、结果可复现，缺点是以后想升级要改这里。
"""

import sys
import urllib.request
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

ROOT = Path(__file__).parent.parent
FONTS_DIR = ROOT / "fonts"

# 字重 -> (本地文件名, 下载地址)
# 地址来自 Google Fonts 的 v31 版本（decomposed，latin 子集）。
# 和 src/style.css 里 @font-face 的 url() 必须一一对应。
FONTS = {
    "300 Light": (
        "RobotoCondensed-Light.woff2",
        "https://fonts.gstatic.com/s/robotocondensed/v31/"
        "ieVo2ZhZI2eCN5jzbjEETS9weq8-_d6T_POl0fRJeyXsosBO5Xw.woff2",
    ),
    "400 Regular": (
        "RobotoCondensed-Regular.woff2",
        "https://fonts.gstatic.com/s/robotocondensed/v31/"
        "ieVo2ZhZI2eCN5jzbjEETS9weq8-_d6T_POl0fRJeyWyosBO5Xw.woff2",
    ),
    "600 SemiBold": (
        "RobotoCondensed-SemiBold.woff2",
        "https://fonts.gstatic.com/s/robotocondensed/v31/"
        "ieVo2ZhZI2eCN5jzbjEETS9weq8-_d6T_POl0fRJeyVspcBO5Xw.woff2",
    ),
}

# woff2 文件头魔数：'wOF2'
WOFF2_MAGIC = b"wOF2"


def fetch(url: str, dest: Path) -> str:
    """下载一个字体文件，校验是不是真的 woff2，返回给用户看的结果"""
    if dest.exists() and dest.read_bytes()[:4] == WOFF2_MAGIC:
        return f"已存在，跳过（{dest.stat().st_size:,} 字节）"

    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = resp.read()

    # ⚠ 必须校验。拿不到字体时 gstatic 有时会返回一个 HTML 错误页，
    #   直接写进文件的话，浏览器会把它当坏字体静默忽略 ——
    #   表现和"字体没生效"一模一样，极难查。
    if len(data) < 100 or data[:4] != WOFF2_MAGIC:
        raise ValueError(
            f"下载到的不是 woff2（{len(data)} 字节，开头 {data[:16]!r}）。"
            f"多半是网络被拦了或者返回了错误页。"
        )

    dest.write_bytes(data)
    return f"OK（{len(data):,} 字节）"


def main():
    print("=" * 60)
    print("  下载自托管字体 -> fonts/")
    print("=" * 60)
    print()

    FONTS_DIR.mkdir(exist_ok=True)

    failed = []
    for label, (name, url) in FONTS.items():
        dest = FONTS_DIR / name
        try:
            result = fetch(url, dest)
            print(f"  ✓ {label:<14} {name}")
            print(f"      {result}")
        except Exception as e:
            failed.append(name)
            print(f"  ✗ {label:<14} {name}")
            print(f"      {type(e).__name__}: {e}")

    print()
    print("=" * 60)
    if failed:
        print(f"  有 {len(failed)} 个没下成功：{failed}")
        print()
        print("  常见原因和办法：")
        print("    * 网络被拦 —— 先把代理/梯子打开再跑一次")
        print("    * 手动下载：浏览器打开下面任一地址，另存到 fonts/ 目录")
        for name, url in FONTS.values():
            print(f"        {name}")
        print()
        print("  或者去 Google Fonts 页面下载整包：")
        print("    https://fonts.google.com/specimen/Roboto+Condensed")
        print("    Get font -> Download all -> 解压 -> 从 static/ 里找 .woff2")
        print("    （文件名要改成上面列的那三个，或者改 src/style.css 的 url()）")
    else:
        print(f"  全部就位：fonts/ 下 {len(FONTS)} 个文件")
        print()
        print("  下一步：")
        print("    python scripts/build.py     # 重建，让产物引用它们")
        print("    python scripts/serve.py     # 起预览，F12 看 woff2 是否 200")
    print("=" * 60)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
