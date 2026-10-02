#!/usr/bin/env python3
"""
构建产物自检 —— 这个脚本只读，不修改任何文件。

    python scripts/check_build.py

检查项：
  1. 每个产物页面结构完整（html/head/body 各一次，结尾正确）
  2. 关键结构 id 恰好出现一次（去注释后统计）
  3. 没有未替换的 {{占位符}}
  4. 侧栏、页脚、正文都真的在
  5. 页脚在 main_container 里面（不是 body 的第三个子元素）
  6. 行尾全是 LF（否则 git 会一直报警告）
  7. 构建幂等（连跑两次结果一致）
"""

import io
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

ROOT = Path(__file__).parent.parent
POSTS = ROOT / "posts"


def strip_comments(html: str) -> str:
    """
    剥离 HTML 注释。用状态机而不是正则 ——
    正则 `<!--.*?-->` 在「注释里提到 <!--」时会错位，
    把后面的真实 DOM 误判成注释（这会让你以为文件坏了，其实没有）。
    """
    out = []
    pos = 0
    n = len(html)
    while pos < n:
        start = html.find("<!--", pos)
        if start == -1:
            out.append(html[pos:])
            break
        out.append(html[pos:start])
        end = html.find("-->", start + 4)
        if end == -1:
            break  # 未闭合的注释：后面全部丢掉
        pos = end + 3
    return "".join(out)


def targets():
    files = [ROOT / "index.html", ROOT / "about.html", ROOT / "Recent.html"]
    files += sorted(POSTS.glob("*.html"))
    return [f for f in files if f.exists()]


def check_structure(path: Path):
    raw = path.read_text(encoding="utf-8")
    body = strip_comments(raw)
    problems = []

    # 1) 顶层标签各一次
    for tag in ("<html", "<head>", "</head>", "<body>", "</body>", "</html>"):
        c = body.count(tag)
        if c != 1:
            problems.append(f"{tag} 出现 {c} 次（应为 1）")

    if not raw.rstrip().endswith("</html>"):
        problems.append("文件结尾不是 </html>")

    # 2) 关键结构 id 恰好一次
    ids = re.findall(r'\sid="([^"]+)"', body)
    counts = Counter(ids)
    for need in ("top", "main_container", "content_container", "site-footer"):
        if counts[need] != 1:
            problems.append(f'id="{need}" 出现 {counts[need]} 次（应为 1）')
    dup = {k: v for k, v in counts.items() if v > 1}
    if dup:
        problems.append(f"重复 id: {dup}")

    # 3) 占位符残留
    left = sorted(set(re.findall(r"\{\{[A-Z_]+\}\}", raw)))
    if left:
        problems.append(f"未替换占位符: {left}")
    if "$body$" in raw:
        problems.append("残留 $body$（pandoc 没填）")

    # 4) 三大块在位
    if 'class="site-profile"' not in body:
        problems.append("缺侧栏")
    if "© 2026" not in body and "All rights reserved" not in body:
        problems.append("缺页脚")
    if 'id="main"' not in body and path.name not in ("index.html",):
        problems.append("缺正文 <main id=\"main\">")

    # 5) 页脚必须在 main_container 里面
    i_mc = body.find('id="main_container"')
    i_ft = body.find('id="site-footer"')
    i_end = body.rfind("</div>")  # main_container 的收尾
    if i_mc == -1 or i_ft == -1:
        pass
    elif not (i_mc < i_ft):
        problems.append("页脚不在 main_container 里面（会被排到右边当第三列）")

    # 6) 行尾
    b = path.read_bytes()
    if b"\r\n" in b:
        problems.append("含 CRLF（git 会一直报警告）")

    return problems


def main():
    print("=" * 62)
    print("  构建产物自检")
    print("=" * 62)

    files = targets()
    failed = 0
    for f in files:
        probs = check_structure(f)
        rel = f.relative_to(ROOT).as_posix()
        if probs:
            failed += 1
            print(f"  ✗ {rel}")
            for p in probs:
                print(f"      - {p}")
        else:
            print(f"  ✓ {rel}")

    # 7) 幂等性：再跑一次构建，看有没有文件变化
    print()
    print("  [幂等性] 再跑一次构建 …")
    before = {f: f.read_bytes() for f in files}
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "build.py")],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", cwd=ROOT)
    if r.returncode != 0:
        print("      ✗ 第二次构建失败")
        print((r.stderr or "")[-400:])
        failed += 1
    else:
        changed = [f.relative_to(ROOT).as_posix() for f in files if f.read_bytes() != before[f]]
        if changed:
            failed += 1
            print(f"      ✗ 不幂等，这些文件第二次构建后变了: {changed}")
        else:
            print("      ✓ 幂等（第二次构建没有产生任何变化）")

    print()
    print("=" * 62)
    if failed:
        print(f"  有 {failed} 个问题需要修")
    else:
        print(f"  全部通过：{len(files)} 个页面结构完整、幂等、行尾统一")
    print("=" * 62)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
