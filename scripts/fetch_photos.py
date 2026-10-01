#!/usr/bin/env python3
"""
从 Unsplash 拉取指定用户最新的一批照片，落成 photos.json。
这份 photos.json 就是"唯一数据源" —— 不是缓存，不需要和 API 对账。

设计原则：
  * 只有这个脚本会碰 api.unsplash.com，且必须你手动运行
  * serve.py / 构建 / 访客 都只读 photos.json，永不请求 API
  * 图片热链接 Unsplash CDN（官方硬性要求），不下载到本地
  * Access Key 只从 .env 读，绝不硬编码、绝不进仓库

用法：
  1) 仓库根目录建 .env，写一行：  UNSPLASH_ACCESS_KEY=你的AccessKey
  2) python scripts/fetch_photos.py             # 默认最多 30 张
     python scripts/fetch_photos.py --limit 12  # 只要 12 张
  3) 核对控制台打印的顺序，是否和 unsplash.com/@你的用户名 页面一致
  4) git add photos.json && git commit
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

# Windows 控制台默认 GBK，中文会崩，强制 UTF-8（和 serve.py 同一个坑）
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

ROOT_DIR = Path(__file__).parent.parent
ENV_FILE = ROOT_DIR / ".env"
OUT_FILE = ROOT_DIR / "photos.json"

USERNAME = "zhoulinyao"          # 你的 Unsplash 用户名
ORDER_BY = "latest"              # latest / oldest / popular
MAX_PER_PAGE = 30                # API 硬上限：一次最多 30 条
UTM = "utm_source=lyon_dev&utm_medium=referral"
THUMB_W = 800                    # 让 CDN 直接给 800px 宽的图，省流量


def read_key():
    """优先环境变量，其次 .env 文件"""
    key = os.environ.get("UNSPLASH_ACCESS_KEY", "").strip()
    src = "环境变量"
    if not key and ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            name, _, value = line.partition("=")
            if name.strip() == "UNSPLASH_ACCESS_KEY":
                key = value.strip().strip('"').strip("'")
                src = ".env"
                break

    if not key:
        print("  ✗ 没找到 UNSPLASH_ACCESS_KEY")
        print("")
        print("    在仓库根目录建 .env，内容一行：")
        print("      UNSPLASH_ACCESS_KEY=你的AccessKey")
        print("")
        print("    key 去哪拿：https://unsplash.com/oauth/applications")
        print("    （.env 已在 .gitignore 里，不会被提交）")
        sys.exit(1)

    # 防呆：Secret Key 只用于 OAuth，照片墙用不到
    if len(key) > 50:
        print("  ⚠ 这个 key 看起来像 Secret Key，照片墙只需要 Access Key。")

    print(f"  ✓ 从{src}读到 Access Key（{key[:6]}...{key[-4:]}）")
    return key


def api_get(url, key):
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"Client-ID {key}")
    req.add_header("Accept-Version", "v1")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            print(f"  ✓ HTTP {resp.status}   本小时剩余配额: "
                  f"{resp.headers.get('X-Ratelimit-Remaining', '?')}/"
                  f"{resp.headers.get('X-Ratelimit-Limit', '?')}")
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        print(f"  ✗ HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:400]}")
        if e.code == 401:
            print("    -> Access Key 无效（要用 Access Key，不是 Secret Key）")
        elif e.code == 403:
            print("    -> 配额用完了（demo 模式 50 次/小时）")
        elif e.code == 404:
            print(f"    -> 用户 '{USERNAME}' 不存在？去 unsplash.com/@{USERNAME} 确认")
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"  ✗ 网络不通: {e.reason}")
        print("    （如果你在国内，可能需要先开代理）")
        sys.exit(1)


def thumb(raw, width, dpr=1):
    """在 urls.raw 上追加 CDN 参数。必须保留原 url 里的 ixid（官方要求，用于统计浏览量）"""
    sep = "&" if "?" in raw else "?"
    u = f"{raw}{sep}w={width}&q=75&fm=jpg&fit=max&auto=format"
    return u + (f"&dpr={dpr}" if dpr > 1 else "")


def with_utm(url):
    if not url:
        return url
    return url + ("&" if "?" in url else "?") + UTM


def simplify(p):
    user = p.get("user") or {}
    return {
        "id": p.get("id"),
        "width": p.get("width"),
        "height": p.get("height"),
        "alt": (p.get("alt_description") or p.get("description") or "").strip(),
        "color": p.get("color") or "#efefef",
        "blur_hash": p.get("blur_hash"),
        "src": thumb(p["urls"]["raw"], THUMB_W),
        "src2x": thumb(p["urls"]["raw"], THUMB_W, dpr=2),
        "page": with_utm((p.get("links") or {}).get("html")),
        "author": user.get("name") or user.get("username") or "",
        "author_url": with_utm((user.get("links") or {}).get("html")),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=MAX_PER_PAGE,
                    help=f"拉几张（1~{MAX_PER_PAGE}，默认 {MAX_PER_PAGE}）")
    ap.add_argument("--order", default=ORDER_BY,
                    choices=["latest", "oldest", "popular"])
    args = ap.parse_args()

    limit = max(1, min(MAX_PER_PAGE, args.limit))

    print("=" * 58)
    print(f"  从 Unsplash 拉取 @{USERNAME} 的照片")
    print(f"  顺序: order_by={args.order}    数量: {limit}")
    print("=" * 58)

    key = read_key()
    url = (f"https://api.unsplash.com/users/{USERNAME}/photos"
           f"?per_page={limit}&order_by={args.order}")
    print(f"  请求: {url}")
    photos = api_get(url, key)

    if not isinstance(photos, list) or not photos:
        print("  ✗ 没拿到任何照片")
        sys.exit(1)

    items = [simplify(p) for p in photos]

    OUT_FILE.write_text(
        json.dumps({
            "username": USERNAME,
            "order_by": args.order,
            "updated": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "profile": with_utm(f"https://unsplash.com/@{USERNAME}"),
            "photos": items,
        }, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print("")
    print(f"  ✓ 写出 {OUT_FILE.name}（{len(items)} 张）")
    print("")
    print("  【请核对】下面这个顺序，要和你在浏览器里")
    print(f"  https://unsplash.com/@{USERNAME} 看到的顺序一致：")
    print("")
    for i, it in enumerate(items, 1):
        print(f"    {i:2}. {it['id']}   {it['width']}x{it['height']}   {it['alt'][:40]}")
    print("")
    print("  对不上的话，试试 --order oldest 或 --order popular 再比一次。")
    print("  下一步：git add photos.json && git commit")


if __name__ == "__main__":
    main()
