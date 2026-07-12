#!/usr/bin/env python3
"""
这个脚本的作用：
1. 读取 post_list.txt（Bash 生成的临时文件）
2. 解析出日期、标题、文件名
3. 生成文章列表的 HTML 代码
4. 更新 home.html 中的文章列表区域
"""

import os
import re
from datetime import datetime

# ========== Step1: Read post_list.txt ==========

def read_post_list() -> list:
  """ 从 post_list.txt 读取文章信息
  形如：
  2026-03-26|想学计算机图形学|2026-03-26-想学计算机图形学.html
  2026-03-24|我的第一篇博客|2026-03-24-我的第一篇博客.html
  """
  items = [] # 存放切割后信息

  with open('../post_list.txt', 'r', encoding='utf-8') as f:
    for line in f:
      line = line.strip() #去掉首位空白
      if not line:
        continue # 跳过空行

      parts = line.split('|', 2) # 用 | 分割，返回列表，最多包含 2+1 个元素

      if len(parts) == 3:
        date_str = parts[0]
        title = parts[1]
        filename = parts[2]
        items.append((date_str, title, filename))

    return items

# ========== Step2: Format Date ==========

def format_date(date_str) -> str:
  """
    将 "2026-03-26" 格式化为 "26 Mar 2026"
    月份用英文缩写
  """

  if not date_str:
    return ""
  
  try:
    # str -> datetime
    date_obj = datetime.strptime(date_str, '%Y-%m-%d')
    return date_obj.strftime("%d %b %Y")
  except:
    # 解析失败，返回源字符串
    return date_str

# ========== Step3: Generate HTML Post List ==========

def generate_post_item(items) -> str:
  """
    生成文章列表的 HTML 代码
    每一项的格式：
    <div>
      <span style="font-family: Consolas; font-size: 14px; color: #666666">26 Mar 2026 </span>
      <a href="somePosts/2026-03-26-想学计算机图形学.html" style="font-size: 18px" class="post-link" target="main-frame">想学计算机图形学</a>
    </div>
    """
  html_items = []

  for date_str, title, filename in items:
    formatted_date = format_date(date_str)

    # 生成一条文章列表项
    item = f'''
              <div>
                <span 
                  style="font-family: Consolas; font-size: 14px; color: #666666"
                  >{formatted_date}</span
                  ><a
                    href="somePosts/{filename}"
                    style="font-size: 18px"
                    class="post-link"
                    target="main-frame"
                    >{title}</a
                  >
              </div>'''
    
    html_items.append(item)
    
    # 用换行符拼接所有项
    return '\n'.join(html_items)

# ========== Step4: Update Homehtml ==========

def update_home_html(new_post_items):
  """
    在 home.html 中找到 <!-- POST_LIST_START --> 和 <!-- POST_LIST_END -->
    之间的内容，替换成新的文章列表
  """
   
  # 读取home.html
  with open('../home.html', 'r', encoding='utf-8') as f:
    content = f.read()

  # 定义标记
  start_marker = '<!-- POST_LIST_START -->'
  end_marker = '<!-- POST_LIST_END -->'

  # 检查标记
  if start_marker not in content or end_marker not in content:
    print("错误：home.html中未找到 POST_LIST 标记！")
    print(f"请确保 home.html 中包含：")
    print(f"{start_marker}")
    print(f"{end_marker}")
    return
  
  # 使用正则表达式替换标记之间的内容
  # re.DOTALL 让 . 也能匹配换行符
  pattern = re.compile(
    re.escape(start_marker) + r'.*?' + re.escape(end_marker), re.DOTALL)
  
  # 新的内容块
  new_block = f'''{start_marker}{new_post_items}{end_marker}'''

  # 执行替换
  content = pattern.sub(new_block, content)

  # 写回 home.html
  with open('../home.html', 'w', encoding='utf-8') as f:
    f.write(content)
  
  print("成功更新 home.html 的文章列表")

# ========== 主程序 ==========

if __name__ == '__main__':
  print("开始更新文章列表")

  # 1、读取文章列表
  items = read_post_list()
  print(f"读取到 {len(items)} 篇文章")

  if not items:
    print("没有文章需要更新")
    exit(0)

  # 2、生成 HTML
  post_items = generate_post_item(items)

  # 3、更新 home.html
  update_home_html(post_items)

  print("完成")
