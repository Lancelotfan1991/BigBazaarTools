"""BazaarDB 数据解析和输出模块

将原始数据转换为结构化的中文输出格式
"""

import json
import os
import logging
from datetime import datetime
from typing import Optional

from config import (
    ENCHANTMENT_NAMES_ZH,
    HERO_NAMES_ZH,
    DEFAULT_HERO,
    OUTPUT_DIR,
    SIZE_NAMES_ZH,
    TIER_NAMES_ZH,
    TIER_ORDER,
)

logger = logging.getLogger(__name__)


def normalize_card(card: dict) -> dict:
    """
    标准化卡片数据，统一字段名（处理 API 返回的 PascalCase 和搜索结果的 lowercase）

    Args:
        card: 原始卡片数据

    Returns:
        标准化后的卡片数据
    """
    normalized = {}

    # 统一 ID 字段
    normalized["id"] = card.get("id") or card.get("Id") or ""

    # 统一名称字段
    title = card.get("Title") or card.get("title") or {}
    if isinstance(title, dict):
        normalized["name"] = title.get("Text", "") or card.get("name", "")
    else:
        normalized["name"] = str(title) or card.get("name", "")

    # 原始英文名
    normalized["name_en"] = card.get("_originalTitleText", "") or normalized["name"]

    # 统一类型
    normalized["type"] = card.get("Type") or card.get("type") or ""
    if not normalized["type"] and isinstance(card.get("tags"), list) and card["tags"]:
        normalized["type"] = card["tags"][0]

    # 统一大小
    size = card.get("Size") or card.get("size") or ""
    normalized["size"] = size
    normalized["size_zh"] = SIZE_NAMES_ZH.get(size, size)

    # 统一品质
    base_tier = card.get("BaseTier") or card.get("base_tier") or ""
    normalized["base_tier"] = base_tier
    normalized["base_tier_zh"] = TIER_NAMES_ZH.get(base_tier, base_tier)

    # 统一英雄/职业
    heroes = card.get("Heroes") or card.get("heroes") or []
    if isinstance(heroes, str):
        heroes = [heroes]
    normalized["heroes"] = heroes
    normalized["heroes_zh"] = [HERO_NAMES_ZH.get(h, h) for h in heroes]

    # 统一标签
    tags = card.get("Tags") or card.get("tags") or []
    normalized["tags"] = tags

    display_tags = card.get("DisplayTags") or card.get("display_tags") or []
    normalized["display_tags"] = display_tags

    hidden_tags = card.get("HiddenTags") or card.get("hidden_tags") or []
    normalized["hidden_tags"] = hidden_tags

    # 基础属性
    base_attrs = card.get("BaseAttributes") or card.get("base_attributes") or {}
    normalized["base_attributes"] = base_attrs

    # 品质层级数据
    tiers = card.get("Tiers") or card.get("tiers") or {}
    normalized["tiers"] = tiers

    # 工具提示
    tooltips = card.get("Tooltips") or card.get("tooltips") or []
    normalized["tooltips"] = tooltips

    tooltip_replacements = card.get("TooltipReplacements") or card.get("tooltip_replacements") or {}
    normalized["tooltip_replacements"] = tooltip_replacements

    # 附魔
    enchantments = card.get("Enchantments") or card.get("enchantments") or {}
    normalized["enchantments"] = enchantments
    # 安全地特换附魔名称（enchantments 可能是嵌套结构）
    try:
        normalized["enchantments_zh"] = {
            ENCHANTMENT_NAMES_ZH.get(k, k): type(v).__name__ for k, v in enchantments.items()
        } if isinstance(enchantments, dict) else {}
    except Exception:
        normalized["enchantments_zh"] = {}

    # 图片
    normalized["art"] = card.get("Art") or card.get("art") or ""
    normalized["art_large"] = card.get("ArtLarge") or card.get("art_large") or ""
    normalized["art_fg"] = card.get("ArtFg") or card.get("art_fg") or ""

    # URI
    normalized["uri"] = card.get("Uri") or card.get("uri") or ""

    # 描述（商人等可能有的描述文本）
    desc = card.get("Description") or card.get("description") or {}
    if isinstance(desc, dict):
        normalized["description"] = desc.get("Text", "")
    else:
        normalized["description"] = str(desc) if desc and desc != '$undefined' else ""

    # 事件描述和选项
    evt_desc = card.get("Description") or card.get("description") or {}
    if isinstance(evt_desc, dict):
        normalized["event_description"] = evt_desc.get("Text", "")
    else:
        normalized["event_description"] = ""

    quests = card.get("Quests") or card.get("quests") or []
    if quests and isinstance(quests, list) and quests != '$undefined':
        normalized["event_options"] = []
        for q in quests:
            if isinstance(q, dict):
                opt = {}
                name = q.get("name") or q.get("Name") or q.get("title") or q.get("Title") or ""
                if isinstance(name, dict):
                    name = name.get("Text", "")
                opt["名称"] = name
                link = q.get("url") or q.get("Url") or q.get("uri") or q.get("Uri") or ""
                opt["链接"] = link
                if opt["名称"]:
                    normalized["event_options"].append(opt)
            elif isinstance(q, str):
                normalized["event_options"].append({"名称": q, "链接": ""})
    else:
        normalized["event_options"] = []

    # 事件选项池（EventOptionPoolTemplates）
    opt_pool = card.get("EventOptionPoolTemplates") or card.get("event_option_pool_templates") or []
    if opt_pool and isinstance(opt_pool, list) and opt_pool != '$undefined':
        for o in opt_pool:
            if isinstance(o, dict):
                opt = {
                    "名称": o.get("title", ""),
                    "图片": o.get("art", ""),
                    "大小": o.get("size", ""),
                    "品质": o.get("tierOverride", ""),
                    "链接": o.get("url", ""),
                }
                if opt["名称"]:
                    normalized["event_options"].append(opt)

    # 掉落来源
    dropped_by = card.get("DroppedBy") or card.get("dropped_by") or []
    normalized["dropped_by"] = dropped_by

    # 转化
    normalized["transform"] = card.get("Transform") or card.get("transform")

    # 怪物信息
    mon_meta = card.get("MonsterMetadata") or card.get("monster_metadata") or {}
    if mon_meta and isinstance(mon_meta, dict) and mon_meta != '$undefined':
        normalized["monster_info"] = {
            "出现天数": mon_meta.get("day"),
            "血量": mon_meta.get("health"),
            "物品栏": [
                {
                    "名称": item.get("title", ""),
                    "图片": item.get("art", ""),
                    "大小": item.get("size", "Small"),
                    "品质": item.get("tierOverride", "Bronze"),
                }
                for item in (mon_meta.get("board") or [])
            ],
        }
    else:
        normalized["monster_info"] = None

    # 战斗奖励
    reward_gold = card.get("RewardCombatGold")
    reward_xp = card.get("RewardCombatXp")
    if reward_gold is not None or reward_xp is not None:
        normalized["battle_reward"] = {}
        if reward_gold is not None:
            normalized["battle_reward"]["金币"] = reward_gold
        if reward_xp is not None:
            normalized["battle_reward"]["经验"] = reward_xp
    else:
        normalized["battle_reward"] = None

    # 保留原始数据
    normalized["_raw"] = card

    return normalized


def format_tooltip_text(tooltips: list, replacements: dict) -> list:
    """
    格式化工具提示文本，替换变量占位符

    支持两种格式：
    1. {"Content": {"Text": "..."}, "TooltipType": "Passive", "TooltipCondition": null}
    2. {"text": "...", "type": "Active", "condition": null}

    Args:
        tooltips: 工具提示列表
        replacements: 替换映射

    Returns:
        格式化后的文本列表
    """
    formatted = []
    for tooltip in tooltips:
        if isinstance(tooltip, dict):
            # 格式1: bazaardb.gg API 格式
            content = tooltip.get("Content") or {}
            if isinstance(content, dict):
                text = content.get("Text", "")
            else:
                text = str(content) if content else ""
            
            # 格式2: 简化格式
            if not text:
                text = tooltip.get("text", "") or tooltip.get("Text", "")
            
            tip_type = tooltip.get("TooltipType", "") or tooltip.get("type", "") or tooltip.get("Type", "")
            condition = tooltip.get("TooltipCondition", "") or tooltip.get("condition", "") or tooltip.get("Condition", "")

            # 替换占位符
            if replacements and isinstance(replacements, dict):
                for key, value in replacements.items():
                    # 统一处理占位符格式：键可能已含大括号如 "{ability.0}"
                    placeholder = key if key.startswith('{') else f"{{{key}}}"
                    if isinstance(value, dict):
                        tier_order = ["Bronze", "Silver", "Gold", "Diamond", "Legendary"]
                        tier_vals = []
                        for t in tier_order:
                            v = value.get(t)
                            if v is not None:
                                tier_vals.append(str(v))
                        if len(tier_vals) >= 2:
                            text = text.replace(placeholder, " » ".join(tier_vals))
                        elif len(tier_vals) == 1:
                            text = text.replace(placeholder, tier_vals[0])
                        else:
                            fixed_val = value.get("Fixed") or value.get("fixed")
                            if fixed_val is not None:
                                text = text.replace(placeholder, str(fixed_val))
                    else:
                        text = text.replace(placeholder, str(value))

            formatted.append({
                "text": text,
                "type": tip_type,
                "condition": condition if condition else "",
            })
        elif isinstance(tooltip, str):
            formatted.append({"text": tooltip, "type": "", "condition": ""})

    return formatted


def format_base_attributes(attrs: dict) -> dict:
    """
    格式化基础属性为可读格式

    Args:
        attrs: 原始属性字典

    Returns:
        格式化后的属性字典
    """
    if not attrs:
        return {}

    attr_names = {
        "CooldownMax": "冷却时间(ms)",
        "Multicast": "多重施法",
        "DamageAmount": "伤害值",
        "ShieldAmount": "护盾值",
        "HealAmount": "治疗值",
        "BuyPrice": "购买价格",
        "SellPrice": "出售价格",
        "Custom_0": "自定义属性0",
        "Custom_1": "自定义属性1",
        "Custom_2": "自定义属性2",
        "HasteDuration": "急速持续时间",
        "SlowDuration": "减速持续时间",
        "FreezeDuration": "冻结持续时间",
        "BurnDuration": "灼烧持续时间",
        "PoisonAmount": "中毒层数",
        "ChargeAmount": "充能次数",
    }

    formatted = {}
    for key, value in attrs.items():
        zh_name = attr_names.get(key, key)
        formatted[zh_name] = value

    return formatted


def card_to_display(card: dict) -> dict:
    """
    将卡片数据转换为显示友好的格式

    Args:
        card: 标准化后的卡片数据

    Returns:
        显示用的卡片数据
    """
    normalized = normalize_card(card)

    # 格式化工具提示
    tooltips = format_tooltip_text(normalized["tooltips"], normalized["tooltip_replacements"])

    # 格式化基础属性
    base_attrs = format_base_attributes(normalized["base_attributes"])

    # 格式化品质层级
    tiers_display = {}
    for tier_name, tier_data in normalized["tiers"].items():
        tier_zh = TIER_NAMES_ZH.get(tier_name, tier_name)
        override_attrs = tier_data.get("OverrideAttributes") or tier_data.get("override_attributes") or {}
        tiers_display[tier_zh] = {
            "属性变更": format_base_attributes(override_attrs) if override_attrs else "无变更",
        }

    display = {
        "名称": normalized["name"],
        "英文名": normalized["name_en"],
        "类型": normalized["type"],
        "大小": normalized["size_zh"],
        "基础品质": normalized["base_tier_zh"],
        "所属职业": normalized["heroes_zh"],
        "显示标签": normalized["display_tags"],
        "基础属性": base_attrs,
        "品质层级": tiers_display,
        "效果说明": tooltips,
        "附魔": list(normalized["enchantments_zh"].keys()) if isinstance(normalized["enchantments_zh"], dict) else [],
        "掉落来源": normalized["dropped_by"],
        "图片链接": normalized["art_large"] or normalized["art"],
        "图标链接": normalized["art_fg"] or "",
        "详情链接": f"https://bazaardb.gg{normalized['uri']}" if normalized["uri"] else "",
        "描述": normalized["description"],
        "怪物信息": normalized["monster_info"],
        "战斗奖励": normalized["battle_reward"],
        "事件描述": normalized["event_description"],
        "事件选项": normalized["event_options"],
    }

    return display


def save_to_json(data: dict, filename: str, output_dir: str = OUTPUT_DIR) -> str:
    """
    保存数据到 JSON 文件

    Args:
        data: 要保存的数据
        filename: 文件名
        output_dir: 输出目录

    Returns:
        保存的文件路径
    """
    os.makedirs(output_dir, exist_ok=True)
    filepath = os.path.join(output_dir, filename)

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    logger.info(f"数据已保存到: {filepath}")
    return filepath


def save_raw_data(data: dict, hero: str = DEFAULT_HERO, output_dir: str = OUTPUT_DIR) -> str:
    """
    保存原始数据到 JSON 文件

    Args:
        data: 原始数据
        hero: 职业名称
        output_dir: 输出目录

    Returns:
        保存的文件路径
    """
    hero_zh = HERO_NAMES_ZH.get(hero, hero)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{hero_zh}_{hero}_原始数据_{timestamp}.json"
    return save_to_json(data, filename, output_dir)


def save_display_data(data: dict, hero: str = DEFAULT_HERO, output_dir: str = OUTPUT_DIR) -> str:
    """
    保存格式化显示数据到 JSON 文件

    Args:
        data: 原始数据
        hero: 职业名称
        output_dir: 输出目录

    Returns:
        保存的文件路径
    """
    hero_zh = HERO_NAMES_ZH.get(hero, hero)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    display_data = {
        "职业": hero_zh,
        "英文名": hero,
        "获取时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "物品数量": len(data.get("items", [])),
        "技能数量": len(data.get("skills", [])),
        "物品": [card_to_display(item) for item in data.get("items", [])],
        "技能": [card_to_display(skill) for skill in data.get("skills", [])],
    }

    filename = f"{hero_zh}_{hero}_格式化数据_{timestamp}.json"
    return save_to_json(display_data, filename, output_dir)


def save_csv_data(data: dict, hero: str = DEFAULT_HERO, output_dir: str = OUTPUT_DIR) -> tuple:
    """
    保存数据到 CSV 文件（物品和技能分开保存）

    Args:
        data: 原始数据
        hero: 职业名称
        output_dir: 输出目录

    Returns:
        (物品CSV路径, 技能CSV路径)
    """
    import csv

    os.makedirs(output_dir, exist_ok=True)
    hero_zh = HERO_NAMES_ZH.get(hero, hero)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # 保存物品 CSV
    items_filename = f"{hero_zh}_{hero}_物品_{timestamp}.csv"
    items_path = os.path.join(output_dir, items_filename)

    items = data.get("items", [])
    if items:
        with open(items_path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["名称", "英文名", "类型", "大小", "基础品质", "所属职业", "显示标签", "基础属性", "效果说明", "详情链接"])
            for item in items:
                display = card_to_display(item)
                attrs_str = "; ".join(f"{k}={v}" for k, v in display.get("基础属性", {}).items())
                tooltips_str = "; ".join(t.get("text", "") for t in display.get("效果说明", []))
                heroes_str = ", ".join(display.get("所属职业", []))
                tags_str = ", ".join(display.get("显示标签", []))
                writer.writerow([
                    display.get("名称", ""),
                    display.get("英文名", ""),
                    display.get("类型", ""),
                    display.get("大小", ""),
                    display.get("基础品质", ""),
                    heroes_str,
                    tags_str,
                    attrs_str,
                    tooltips_str,
                    display.get("详情链接", ""),
                ])

    # 保存技能 CSV
    skills_filename = f"{hero_zh}_{hero}_技能_{timestamp}.csv"
    skills_path = os.path.join(output_dir, skills_filename)

    skills = data.get("skills", [])
    if skills:
        with open(skills_path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["名称", "英文名", "类型", "大小", "基础品质", "所属职业", "显示标签", "基础属性", "效果说明", "详情链接"])
            for skill in skills:
                display = card_to_display(skill)
                attrs_str = "; ".join(f"{k}={v}" for k, v in display.get("基础属性", {}).items())
                tooltips_str = "; ".join(t.get("text", "") for t in display.get("效果说明", []))
                heroes_str = ", ".join(display.get("所属职业", []))
                tags_str = ", ".join(display.get("显示标签", []))
                writer.writerow([
                    display.get("名称", ""),
                    display.get("英文名", ""),
                    display.get("类型", ""),
                    display.get("大小", ""),
                    display.get("基础品质", ""),
                    heroes_str,
                    tags_str,
                    attrs_str,
                    tooltips_str,
                    display.get("详情链接", ""),
                ])

    return items_path, skills_path


def print_summary(data: dict):
    """打印数据摘要"""
    items = data.get("items", [])
    skills = data.get("skills", [])

    print("\n" + "=" * 60)
    print(f"  🏴‍☠️  {data.get('hero_zh', '海盗')}（{data.get('hero', 'Karnok')}）数据摘要")
    print("=" * 60)

    print(f"\n📦 物品总数: {len(items)}")
    if items:
        # 按大小分类
        size_count = {}
        tier_count = {}
        for item in items:
            norm = normalize_card(item)
            size = norm.get("size_zh", "未知")
            size_count[size] = size_count.get(size, 0) + 1
            tier = norm.get("base_tier_zh", "未知")
            tier_count[tier] = tier_count.get(tier, 0) + 1

        print(f"   按大小: {', '.join(f'{k}={v}' for k, v in sorted(size_count.items()))}")
        print(f"   按品质: {', '.join(f'{k}={v}' for k, v in sorted(tier_count.items()))}")

        # 显示部分物品名称
        print(f"\n   物品列表（前20个）:")
        for i, item in enumerate(items[:20], 1):
            norm = normalize_card(item)
            name = norm.get("name", "未知")
            name_en = norm.get("name_en", "")
            size = norm.get("size_zh", "")
            tier = norm.get("base_tier_zh", "")
            if name_en and name != name_en:
                print(f"   {i:3d}. [{tier}·{size}] {name} ({name_en})")
            else:
                print(f"   {i:3d}. [{tier}·{size}] {name}")
        if len(items) > 20:
            print(f"   ... 还有 {len(items) - 20} 个物品")

    print(f"\n⚡ 技能总数: {len(skills)}")
    if skills:
        tier_count = {}
        for skill in skills:
            norm = normalize_card(skill)
            tier = norm.get("base_tier_zh", "未知")
            tier_count[tier] = tier_count.get(tier, 0) + 1

        print(f"   按品质: {', '.join(f'{k}={v}' for k, v in sorted(tier_count.items()))}")

        print(f"\n   技能列表（前20个）:")
        for i, skill in enumerate(skills[:20], 1):
            norm = normalize_card(skill)
            name = norm.get("name", "未知")
            name_en = norm.get("name_en", "")
            tier = norm.get("base_tier_zh", "")
            if name_en and name != name_en:
                print(f"   {i:3d}. [{tier}] {name} ({name_en})")
            else:
                print(f"   {i:3d}. [{tier}] {name}")
        if len(skills) > 20:
            print(f"   ... 还有 {len(skills) - 20} 个技能")

    print("\n" + "=" * 60)
