#!/usr/bin/env python3
"""
生成 post_list.json（首页「最近」和 Recent.html 的文章列表数据）。

数据来源有两条，按优先级尝试：
  1) post_list.txt  —— GitHub Actions 里 pandoc 循环时写下的临时文件
                       格式： 日期|标题|文件名
  2) posts/*.html   —— 本地直接跑时没有 post_list.txt，就从文件名解析

文件名格式约定：  YYYY-MM-DD-标题.md / .html
简介提取：正文里第一段 _斜体_ 或 *斜体*

历史说明：这个脚本以前叫「更新 home.html 的文章列表」，
         在 5c7770e 改成前端 fetch json 之后，那段替换逻辑就成了死代码
         （它找的 <!-- POST_LIST_START --> 标记已经不存在了），这里删掉。
"""

import json
import os
import re
import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

ROOT = Path(__file__).parent.parent
os.chdir(ROOT)
POSTS_DIR = ROOT / "posts"
OUT_FILE = ROOT / "post_list.json"


def parse_stem(stem: str):
    """从 'YYYY-MM-DD-标题' 拆出日期和标题"""
    m = re.match(r"^(\d{4}-\d{2}-\d{2})-(.*)$", stem)
    if not m:
        return "", stem
    return m.group(1), m.group(2)


def extract_description(md_path: Path) -> str:
    """第一段 _斜体_ / *斜体* 里的纯文本"""
    if not md_path.exists():
        return ""
    content = md_path.read_text(encoding="utf-8")
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


def read_from_txt():
    """CI 里 pandoc 写的临时清单"""
    f = ROOT / "post_list.txt"
    if not f.exists():
        return None
    items = []
    for line in f.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("|", 2)
        if len(parts) == 3:
            items.append(parts)
    return items or None


def read_from_posts_dir():
    """本地跑：直接扫 posts/*.html"""
    if not POSTS_DIR.is_dir():
        return []
    items = []
    for f in POSTS_DIR.glob("*.html"):
        date, title = parse_stem(f.stem)
        items.append((date, title, f.name))
    return items


def main():
    items = read_from_txt()
    source = "post_list.txt"
    if items is None:
        items = read_from_posts_dir()
        source = "posts/*.html"

    if not items:
        print("没有找到任何文章")
        return

    items.sort(key=lambda x: x[0], reverse=True)

    data = []
    for date_str, title, filename in items:
        data.append({
            "date": date_str,
            "title": title,
            "description": extract_description(
                POSTS_DIR / filename.replace(".html", ".md")
            ),
            "filename": filename,
        })

    OUT_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"已生成 post_list.json（{len(data)} 篇，来源：{source}）")


if __name__ == "__main__":
    main()
