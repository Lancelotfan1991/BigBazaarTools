#!/usr/bin/env python3
"""数据预获取脚本 - 为移动端 App 准备离线数据

遍历所有职业，从 bazaardb.gg 获取全部物品和技能数据，
保存到 mobile-app/data-s{N}/ 版本化目录供离线 App 使用。

数据目录严格按版本号管理：
- --season 16   输出到 mobile-app/data-s16/
- --season 16.1 输出到 mobile-app/data-s16.1/
- --season s15  输出到 mobile-app/data-s15/

可选 --sync-vue 参数会在 bazaar-vue/public/ 下创建符号链接，
确保两个仓库共享同一份数据。

使用方式:
    python build_data.py --season 16             # 获取 S16 数据
    python build_data.py --season 16.1           # 获取 S16.1 补丁数据
    python build_data.py --season 16.1 --sync-vue  # 获取数据并同步到 vue 项目
    python build_data.py --season 16.1 --hero Vanessa  # 指定赛季+职业
"""

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path

from config import (
    ALL_CATEGORY, ALL_CATEGORY_ZH, HEROES, HERO_NAMES_ZH,
    CATEGORY_EVENTS, CATEGORY_MONSTERS, CATEGORY_TRAINERS, CATEGORY_MERCHANTS,
)
from fetcher import BazaarDBFetcher
from parser import card_to_display

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# bazaar-vue 项目的 public 目录（用于 --sync-vue 符号链接）
VUE_PUBLIC_DIR = Path("../bazaar-vue/public")


def get_data_dir(season: str) -> Path:
    """根据赛季编号返回版本化数据目录

    Args:
        season: 赛季编号（支持整数如 16，或补丁版本如 16.1、's16.1'）。
                始终输出到 data-s{N}/ 目录。

    Returns:
        数据目录 Path 对象
    """
    s = str(season).lstrip('sS')
    return Path(f"mobile-app/data-s{s}")


def sync_to_vue(data_dir: Path, season_label: str):
    """在 bazaar-vue/public/ 下创建符号链接，指向 data_dir

    Args:
        data_dir: 版本化数据目录，如 mobile-app/data-s16.1/
        season_label: 赛季标签，如 S16.1
    """
    import platform

    vue_dir = VUE_PUBLIC_DIR
    if not vue_dir.exists():
        logger.error(f"bazaar-vue 目录不存在: {vue_dir.resolve()}")
        return

    dir_name = data_dir.name  # e.g. data-s16.1
    link_path = vue_dir / dir_name
    target_path = data_dir.resolve()

    # 如果已存在相同的符号链接，跳过
    if link_path.is_symlink():
        existing_target = link_path.resolve()
        if existing_target == target_path:
            logger.info(f"符号链接已存在且正确: {link_path} -> {target_path}")
            return
        # 删除旧链接重建
        if platform.system() == 'Windows':
            os.rmdir(link_path)
        else:
            os.unlink(link_path)
    elif link_path.exists():
        logger.warning(f"{link_path} 是真实目录，跳过（请先删除后重试）")
        return

    # 创建符号链接
    try:
        if platform.system() == 'Windows':
            os.symlink(str(target_path), str(link_path), target_is_directory=True)
        else:
            # Unix: 使用相对路径
            rel_target = os.path.relpath(target_path, link_path.parent)
            os.symlink(rel_target, str(link_path))
        logger.info(f"✅ 已创建符号链接: {link_path} -> {target_path}")
    except OSError as e:
        logger.error(f"创建符号链接失败: {e}")
        logger.error("Windows 下需要管理员权限或开启开发者模式")


def build_all_data(data_dir: Path):
    """合并所有分类数据生成"全部"分类"""
    out_path = data_dir / f"{ALL_CATEGORY}.json"
    all_items = []
    all_skills = []
    seen_item_ids = set()
    seen_skill_ids = set()

    for hero in HEROES:
        data_file = data_dir / f"{hero}.json"
        if not data_file.exists():
            continue
        d = json.load(open(data_file, "r", encoding="utf-8"))
        for item in d.get("物品", []):
            item_id = item.get("英文名", "")
            if item_id and item_id not in seen_item_ids:
                seen_item_ids.add(item_id)
                all_items.append(item)
        for skill in d.get("技能", []):
            skill_id = skill.get("英文名", "")
            if skill_id and skill_id not in seen_skill_ids:
                seen_skill_ids.add(skill_id)
                all_skills.append(skill)

    result = {
        "职业": ALL_CATEGORY_ZH,
        "英文名": ALL_CATEGORY,
        "获取时间": time.strftime("%Y-%m-%d %H:%M:%S"),
        "物品数量": len(all_items),
        "技能数量": len(all_skills),
        "物品": all_items,
        "技能": all_skills,
    }

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    size_kb = out_path.stat().st_size / 1024
    logger.info(f"\n📦 全部数据已合并: {len(all_items)} 物品, {len(all_skills)} 技能")
    logger.info(f"已保存: {out_path} ({size_kb:.1f} KB)")
    return result


def build_game_data(type_name: str, fetcher: BazaarDBFetcher, data_dir: Path) -> dict:
    """获取并保存游戏数据（事件/怪物/训练师）"""
    names = {
        CATEGORY_EVENTS: "事件",
        CATEGORY_MONSTERS: "怪物",
        CATEGORY_TRAINERS: "训练师",
        CATEGORY_MERCHANTS: "商人",
    }
    name = names.get(type_name, type_name)
    out_path = data_dir / f"{type_name}.json"

    logger.info("=" * 60)
    logger.info(f"开始获取 {name} 数据...")
    logger.info("=" * 60)

    start = time.time()
    raw_cards = fetcher.fetch_game_data(type_name)
    elapsed = time.time() - start

    display_cards = [card_to_display(card) for card in raw_cards]
    logger.info(f"{name}: {len(display_cards)} 条, 耗时 {elapsed:.1f}s")

    result = {
        "职业": name,
        "英文名": type_name,
        "获取时间": time.strftime("%Y-%m-%d %H:%M:%S"),
        "物品数量": len(display_cards),
        "技能数量": 0,
        "物品": display_cards,
        "技能": [],
    }

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    size_kb = out_path.stat().st_size / 1024
    logger.info(f"已保存: {out_path} ({size_kb:.1f} KB)")
    return result


def build_heroes_index(data_dir: Path):
    """生成职业索引文件 heroes.json"""
    index = []
    # 先加"全部"分类
    all_file = data_dir / f"{ALL_CATEGORY}.json"
    all_entry = {
        "name_en": ALL_CATEGORY,
        "name_zh": ALL_CATEGORY_ZH,
        "has_data": all_file.exists(),
    }
    if all_file.exists():
        mtime = all_file.stat().st_mtime
        all_entry["data_time"] = time.strftime("%Y-%m-%d %H:%M", time.localtime(mtime))
    index.append(all_entry)

    for hero in HEROES:
        hero_zh = HERO_NAMES_ZH.get(hero, hero)
        data_file = data_dir / f"{hero}.json"
        has_data = data_file.exists()
        entry = {
            "name_en": hero,
            "name_zh": hero_zh,
            "has_data": has_data,
        }
        if has_data:
            mtime = data_file.stat().st_mtime
            entry["data_time"] = time.strftime("%Y-%m-%d %H:%M", time.localtime(mtime))
        index.append(entry)

    out_path = data_dir / "heroes.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)
    logger.info(f"职业索引已保存: {out_path}")
    return index


def build_hero_data(hero: str, fetcher: BazaarDBFetcher, data_dir: Path):
    """获取单个职业的全部数据并保存"""
    hero_zh = HERO_NAMES_ZH.get(hero, hero)
    out_path = data_dir / f"{hero}.json"

    logger.info("=" * 60)
    logger.info(f"开始获取 {hero_zh}（{hero}）的全部数据...")
    logger.info("=" * 60)

    start = time.time()
    raw = fetcher.fetch_hero_data(hero=hero)
    elapsed_fetch = time.time() - start

    items = raw.get("items", [])
    skills = raw.get("skills", [])
    logger.info(f"获取完成: {len(items)} 物品, {len(skills)} 技能, 耗时 {elapsed_fetch:.1f}s")

    # 格式化
    display_items = [card_to_display(item) for item in items]
    display_skills = [card_to_display(skill) for skill in skills]

    result = {
        "职业": hero_zh,
        "英文名": hero,
        "获取时间": time.strftime("%Y-%m-%d %H:%M:%S"),
        "物品数量": len(display_items),
        "技能数量": len(display_skills),
        "物品": display_items,
        "技能": display_skills,
    }

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    size_kb = out_path.stat().st_size / 1024
    logger.info(f"已保存: {out_path} ({size_kb:.1f} KB)")
    return result


def main():
    parser = argparse.ArgumentParser(description="为移动端 App 预获取全部职业数据")
    parser.add_argument(
        "--hero", "-H", type=str, default=None, choices=HEROES,
        help="只获取指定职业（默认获取全部）",
    )
    parser.add_argument(
        "--method", "-m", type=str, default="auto",
        choices=["auto", "direct", "cloudscraper"],
        help="数据获取方式（默认: auto）",
    )
    parser.add_argument(
        "--season", "-s", type=str, required=True,
        help="赛季/补丁编号（必填），支持 16、16.1、s16.1 等格式，输出到 data-s{N}/",
    )
    parser.add_argument(
        "--sync-vue", action="store_true", default=False,
        help="在 bazaar-vue/public/ 下创建符号链接，共享数据",
    )
    args = parser.parse_args()

    # 确定数据输出目录（始终版本化）
    data_dir = get_data_dir(args.season)
    season_label = f"S{str(args.season).lstrip('sS')}"
    os.makedirs(data_dir, exist_ok=True)

    heroes_to_fetch = [args.hero] if args.hero else HEROES

    print(f"\n{'=' * 60}")
    print(f"  📦 大巴扎数据预获取工具")
    print(f"  赛季: {season_label}")
    print(f"  目标目录: {data_dir.resolve()}")
    print(f"  职业数量: {len(heroes_to_fetch)}")
    print(f"{'=' * 60}\n")

    fetcher = BazaarDBFetcher(method=args.method)
    try:
        fetcher.connect()
        print(f"✅ 已连接 ({fetcher.method})\n")

        total_start = time.time()
        results = {}

        for i, hero in enumerate(heroes_to_fetch, 1):
            hero_zh = HERO_NAMES_ZH.get(hero, hero)
            print(f"\n[{i}/{len(heroes_to_fetch)}] {hero_zh} ({hero})")
            print("-" * 40)

            try:
                data = build_hero_data(hero, fetcher, data_dir)
                results[hero] = data
            except Exception as e:
                logger.error(f"获取 {hero} 失败: {e}")
                results[hero] = None

            if i < len(heroes_to_fetch):
                time.sleep(2)

        total_elapsed = time.time() - total_start

        # 合并全部数据
        all_result = build_all_data(data_dir)

        # 获取游戏数据
        game_results = {}
        for i, (cat, cat_name) in enumerate([
            (CATEGORY_EVENTS, "事件"),
            (CATEGORY_MONSTERS, "怪物"),
            (CATEGORY_TRAINERS, "训练师"),
            (CATEGORY_MERCHANTS, "商人"),
        ]):
            print(f"\n[游戏数据 {i+1}/4] {cat_name}")
            print("-" * 40)
            try:
                game_results[cat] = build_game_data(cat, fetcher, data_dir)
            except Exception as e:
                logger.error(f"获取 {cat_name} 失败: {e}")
                game_results[cat] = None
            if i < 3:
                time.sleep(2)

        # 生成索引
        build_heroes_index(data_dir)

        # 汇总
        print(f"\n{'=' * 60}")
        print(f"  📊 数据获取汇总")
        print(f"{'=' * 60}")
        print(f"  ✅ 全部: {all_result['物品数量']} 物品, {all_result['技能数量']} 技能")
        for hero in heroes_to_fetch:
            hero_zh = HERO_NAMES_ZH.get(hero, hero)
            data = results.get(hero)
            if data:
                print(f"  ✅ {hero_zh}: {data['物品数量']} 物品, {data['技能数量']} 技能")
            else:
                print(f"  ❌ {hero_zh}: 获取失败")
        for cat, cat_name in [("events", "事件"), ("monsters", "怪物"), ("trainers", "训练师"), ("merchants", "商人")]:
            data = game_results.get(cat)
            if data:
                print(f"  ✅ {cat_name}: {data['物品数量']} 条")
            else:
                print(f"  ❌ {cat_name}: 获取失败")

        total_items = sum(d["物品数量"] for d in results.values() if d)
        total_skills = sum(d["技能数量"] for d in results.values() if d)
        print(f"\n  总计: {total_items} 物品, {total_skills} 技能")
        print(f"  耗时: {total_elapsed:.1f} 秒")
        print(f"  赛季: {season_label}")
        print(f"  目录: {data_dir.resolve()}")
        print(f"{'=' * 60}")

        # 同步到 bazaar-vue（创建符号链接）
        if args.sync_vue:
            sync_to_vue(data_dir, season_label)

    finally:
        fetcher.close()


if __name__ == "__main__":
    main()
