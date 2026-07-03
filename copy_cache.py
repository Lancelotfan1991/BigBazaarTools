#!/usr/bin/env python3
"""从现有 output/ 缓存数据快速构建 mobile-app/data/"""
import json, os, re, time
from pathlib import Path

OUTPUT_DIR = Path("output")
MOBILE_DATA_DIR = Path("mobile-app/data")

HEROES = ["Vanessa","Karnok","Dooley","Pygmalien","Mak","Stelle","Jules"]
HERO_NAMES_ZH = {"Vanessa":"海盗","Karnok":"卡诺克","Dooley":"杜利","Pygmalien":"匹格梅林","Mak":"马克","Stelle":"斯特尔","Jules":"朱尔斯"}

os.makedirs(MOBILE_DATA_DIR, exist_ok=True)

index = []
for hero in HEROES:
    hero_zh = HERO_NAMES_ZH.get(hero, hero)
    # 查找最新的格式化数据文件
    pattern = f"*_{hero}_格式化数据_*.json"
    files = list(OUTPUT_DIR.glob(pattern))
    out_path = MOBILE_DATA_DIR / f"{hero}.json"

    has_data = False
    if files:
        latest = max(files, key=os.path.getctime)
        print(f"[{hero}] 从缓存复制: {latest.name}")
        with open(latest, "r", encoding="utf-8") as f:
            data = json.load(f)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        has_data = True
        print(f"  -> {out_path} ({out_path.stat().st_size/1024:.1f} KB)")
    else:
        print(f"[{hero}] 无缓存数据，需运行 python build_data.py --hero {hero}")

    entry = {"name_en": hero, "name_zh": hero_zh, "has_data": has_data}
    if has_data:
        entry["data_time"] = time.strftime("%Y-%m-%d %H:%M", time.localtime(out_path.stat().st_mtime))
    index.append(entry)

with open(MOBILE_DATA_DIR / "heroes.json", "w", encoding="utf-8") as f:
    json.dump(index, f, ensure_ascii=False, indent=2)
print(f"\n职业索引已保存: {MOBILE_DATA_DIR / 'heroes.json'}")
