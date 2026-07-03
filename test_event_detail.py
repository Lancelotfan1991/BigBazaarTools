#!/usr/bin/env python3
"""测试获取事件选项的详情"""
import json
import re
import cloudscraper
from config import BASE_URL

url = f"{BASE_URL}/card/1689vff7pjwsxh8lfyw90572h2v/Grab-the-Loot"

headers = {
    "Accept": "text/x-component",
    "RSC": "1",
    "Next-Url": "/card/1689vff7pjwsxh8lfyw90572h2v/Grab-the-Loot",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

s = cloudscraper.create_scraper(browser={"browser": "chrome", "platform": "windows", "desktop": True})
resp = s.get(url, headers=headers, timeout=30)
s.close()

print(f"Status: {resp.status_code}")
print(f"Content length: {len(resp.text)}")

# 保存原始内容
with open("debug_event_detail.txt", "w", encoding="utf-8") as f:
    f.write(resp.text)

# 搜索关键字段
text = resp.text

# 查找 Description
desc_match = re.search(r'"Description":\{"Text":"([^"]*)"\}', text)
if desc_match:
    print(f"\nDescription: {desc_match.group(1)}")

# 查找 Tooltips
tt_match = re.search(r'"Tooltips":\[(.*?)\](?=,"TooltipReplacements")', text, re.DOTALL)
if tt_match:
    tt_text = tt_match.group(1)
    if tt_text:
        print(f"\nTooltips: {tt_text[:500]}")
    else:
        print(f"\nTooltips: (空)")

# 查找 Title
title_match = re.search(r'"Title":\{"Text":"([^"]*)"\}', text)
if title_match:
    print(f"\nTitle: {title_match.group(1)}")

# 查找所有 Text 字段
texts = re.findall(r'"Text":"([^"]{1,200})"', text)
if texts:
    print(f"\n所有 Text 字段 ({len(texts)} 个):")
    for t in texts[:20]:
        print(f"  - {t}")
