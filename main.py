#!/usr/bin/env python3
"""BazaarDB 海盗数据获取工具

从 https://bazaardb.gg 获取大巴扎(The Bazaar)游戏中海盗(Karnok)职业的全部物品和技能数据。

使用方式:
    python main.py                        # 获取 Karnok（海盗）的全部物品和技能
    python main.py --hero Vanessa         # 获取凡妮莎的数据
    python main.py --max-pages 5          # 只获取前5页数据（快速测试）
    python main.py --format json csv      # 同时输出 JSON 和 CSV 格式
    python main.py --format raw           # 输出原始数据
"""

import argparse
import logging
import sys
import time

# 确保控制台按 UTF-8 输出，避免 emoji/中文在 Windows CP936 控制台触发编码错误
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

from config import HEROES, HERO_NAMES_ZH, DEFAULT_HERO, OUTPUT_DIR
from fetcher import BazaarDBFetcher
from parser import (
    print_summary,
    save_csv_data,
    save_display_data,
    save_raw_data,
)


def setup_logging(verbose: bool = False):
    """配置日志"""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )


def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description="从 bazaardb.gg 获取大巴扎(The Bazaar)游戏中指定职业的物品和技能数据",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python main.py                          获取海盗(Karnok)的全部物品和技能
  python main.py --hero Vanessa           获取凡妮莎的物品和技能
  python main.py --max-pages 5            只获取前5页（快速测试）
  python main.py --format json csv        同时输出 JSON 和 CSV 格式
  python main.py --format raw             输出原始 API 数据

支持的职业: """ + ", ".join(f"{h}({HERO_NAMES_ZH[h]})" for h in HEROES),
    )

    parser.add_argument(
        "--hero", "-H",
        type=str,
        default=DEFAULT_HERO,
        choices=HEROES,
        help=f"要获取数据的职业（默认: {DEFAULT_HERO} 海盗）",
    )

    parser.add_argument(
        "--method", "-m",
        type=str,
        default="auto",
        choices=["auto", "direct", "cloudscraper"],
        help="数据获取方式（默认: auto 自动选择）",
    )

    parser.add_argument(
        "--max-pages",
        type=int,
        default=None,
        help="最大页数限制（每页约10张卡片，不设置则获取全部）",
    )

    parser.add_argument(
        "--format", "-f",
        type=str,
        nargs="+",
        default=["json"],
        choices=["json", "csv", "raw"],
        help="输出格式（默认: json；可选: json, csv, raw）",
    )

    parser.add_argument(
        "--output", "-o",
        type=str,
        default=OUTPUT_DIR,
        help=f"输出目录（默认: {OUTPUT_DIR}）",
    )

    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="显示详细日志",
    )

    return parser.parse_args()


def main():
    """主函数"""
    args = parse_args()
    setup_logging(args.verbose)

    hero = args.hero
    hero_zh = HERO_NAMES_ZH.get(hero, hero)

    print(f"\n{'=' * 60}")
    print(f"  🏴‍☠️  大巴扎数据获取工具 - BazaarDB Fetcher")
    print(f"  职业: {hero_zh}（{hero}）")
    print(f"  数据来源: https://bazaardb.gg")
    print(f"{'=' * 60}\n")

    # 初始化获取器
    fetcher = BazaarDBFetcher(method=args.method)

    try:
        # 建立连接
        print("🔗 正在连接 bazaardb.gg...")
        fetcher.connect()
        print(f"✅ 已通过 {fetcher.method} 方式连接成功\n")

        # 获取数据
        start_time = time.time()
        data = fetcher.fetch_hero_data(hero=hero, max_pages=args.max_pages)
        elapsed = time.time() - start_time

        print(f"\n⏱️  数据获取完成，耗时 {elapsed:.1f} 秒")

        if not data.get("items") and not data.get("skills"):
            print("\n❌ 未获取到任何数据。可能的原因：")
            print("   1. 网站被 Cloudflare 保护，当前获取方式无法绕过")
            print("   2. 请尝试使用 --method cloudscraper 方式")
            print("   3. 请确保已安装依赖: pip install cloudscraper")
            sys.exit(1)

        # 打印摘要
        print_summary(data)

        # 保存数据
        print("\n💾 正在保存数据...")
        output_dir = args.output

        for fmt in args.format:
            if fmt == "json":
                path = save_display_data(data, hero, output_dir)
                print(f"  ✅ 格式化 JSON 已保存: {path}")
            elif fmt == "csv":
                items_path, skills_path = save_csv_data(data, hero, output_dir)
                print(f"  ✅ 物品 CSV 已保存: {items_path}")
                print(f"  ✅ 技能 CSV 已保存: {skills_path}")
            elif fmt == "raw":
                path = save_raw_data(data, hero, output_dir)
                print(f"  ✅ 原始数据已保存: {path}")

        print(f"\n🎉 完成！所有数据已保存到 {output_dir} 目录")

    except KeyboardInterrupt:
        print("\n\n⚠️  用户中断操作")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ 发生错误: {e}")
        logging.exception("详细错误信息")
        sys.exit(1)
    finally:
        fetcher.close()


if __name__ == "__main__":
    main()
