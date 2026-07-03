#!/usr/bin/env python3
"""职业数据查询工具 - 本地服务器

支持在线获取 bazaardb.gg 全部数据 + 动态查询。
启动后自动打开浏览器，显示职业选择界面。
"""

import http.server
import json
import logging
import os
import re
import socket
import socketserver
import threading
import time
import webbrowser
from pathlib import Path
from urllib.parse import urlparse, parse_qs

from config import HEROES, HERO_NAMES_ZH, OUTPUT_DIR
from fetcher import BazaarDBFetcher
from parser import card_to_display, save_display_data

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger(__name__)

# 全局任务存储
_fetch_tasks = {}
_task_lock = threading.Lock()


class FetchTask:
    """后台获取任务"""

    def __init__(self, hero: str):
        self.hero = hero
        self.hero_zh = HERO_NAMES_ZH.get(hero, hero)
        self.status = "pending"  # pending / fetching / done / error
        self.progress = ""
        self.items_fetched = 0
        self.skills_fetched = 0
        self.items_total = 0
        self.skills_total = 0
        self.phase = ""  # "items" or "skills"
        self.result = None
        self.error = None
        self.start_time = time.time()

    def run(self):
        """在后台线程中执行获取"""
        fetcher = BazaarDBFetcher(method="auto")
        try:
            self.status = "fetching"
            fetcher.connect()

            # 获取物品
            self.phase = "items"
            self.progress = f"正在获取 {self.hero_zh} 的物品数据..."
            items = self._fetch_with_progress(fetcher, "items")
            self.items_fetched = len(items)
            self.items_total = len(items)

            time.sleep(1)

            # 获取技能
            self.phase = "skills"
            self.progress = f"正在获取 {self.hero_zh} 的技能数据..."
            skills = self._fetch_with_progress(fetcher, "skills")
            self.skills_fetched = len(skills)
            self.skills_total = len(skills)

            # 格式化数据
            self.progress = "正在格式化数据..."
            display_items = [card_to_display(item) for item in items]
            display_skills = [card_to_display(skill) for skill in skills]

            self.result = {
                "职业": self.hero_zh,
                "英文名": self.hero,
                "获取时间": time.strftime("%Y-%m-%d %H:%M:%S"),
                "物品数量": len(display_items),
                "技能数量": len(display_skills),
                "物品": display_items,
                "技能": display_skills,
            }

            # 同时保存到本地（缓存）
            try:
                raw_data = {"hero": self.hero, "hero_zh": self.hero_zh, "items": items, "skills": skills}
                save_display_data(raw_data, self.hero, OUTPUT_DIR)
            except Exception as e:
                logger.warning(f"保存本地缓存失败: {e}")

            elapsed = time.time() - self.start_time
            self.progress = f"完成！物品 {len(display_items)} 个，技能 {len(display_skills)} 个，耗时 {elapsed:.1f} 秒"
            self.status = "done"

        except Exception as e:
            self.status = "error"
            self.error = str(e)
            self.progress = f"获取失败: {e}"
            logger.exception(f"获取 {self.hero} 数据失败")
        finally:
            fetcher.close()

    def _fetch_with_progress(self, fetcher, category):
        """带进度报告的分类获取"""
        from urllib.parse import urlencode
        from config import SEARCH_URL, REQUEST_DELAY

        all_cards = []
        current_page = 1
        cat_zh = "物品" if category == "items" else "技能"

        while True:
            params = {"q": f"k:{self.hero.lower()}", "c": category}
            page_url = f"{SEARCH_URL}?{urlencode(params)}&page={current_page}"

            self.progress = f"正在获取{cat_zh}第 {current_page} 页... (已获取 {len(all_cards)} 个)"

            rsc_content = fetcher._fetch_rsc_page(page_url)
            if not rsc_content:
                break

            cards, total, page_idx = fetcher._parse_rsc_page_cards(rsc_content)
            if not cards:
                break

            # 按 Heroes 字段过滤
            filtered = []
            for card in cards:
                heroes = card.get("Heroes") or []
                if self.hero in heroes or "Common" in heroes:
                    filtered.append(card)
            all_cards.extend(filtered)

            self.progress = f"{cat_zh}第 {current_page} 页完成 (本页 {len(cards)} 张, 保留 {len(filtered)} 张, 总计 {len(all_cards)} 个)"

            # 估算是否还有更多页：如果本页原始数据 < 10 或已到达 total/10 的上界
            if len(cards) < 10:
                break

            current_page += 1
            time.sleep(REQUEST_DELAY)

        return all_cards

    def to_status_dict(self):
        return {
            "hero": self.hero,
            "hero_zh": self.hero_zh,
            "status": self.status,
            "progress": self.progress,
            "phase": self.phase,
            "items_fetched": self.items_fetched,
            "skills_fetched": self.skills_fetched,
            "error": self.error,
        }


class ToolboxHandler(http.server.SimpleHTTPRequestHandler):
    """自定义请求处理器"""

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/heroes":
            self._serve_heroes_list()
        elif path.startswith("/api/fetch/"):
            hero_name = path.split("/")[-1]
            self._start_fetch(hero_name)
        elif path.startswith("/api/status/"):
            hero_name = path.split("/")[-1]
            self._serve_fetch_status(hero_name)
        elif path.startswith("/api/result/"):
            hero_name = path.split("/")[-1]
            self._serve_fetch_result(hero_name)
        elif path.startswith("/api/hero/"):
            hero_name = path.split("/")[-1]
            self._serve_hero_data(hero_name)
        else:
            super().do_GET()

    def _serve_heroes_list(self):
        """返回所有支持的职业列表 + 本地缓存状态"""
        data_dir = Path(OUTPUT_DIR)
        cached = {}
        if data_dir.exists():
            for f in data_dir.glob("*格式化数据*.json"):
                match = re.match(r"(.+?)_(.+?)_格式化数据_(\d+)_(\d+)\.json", f.name)
                if match:
                    hero_zh, hero_en = match.group(1), match.group(2)
                    key = hero_en
                    if key not in cached or f.stat().st_ctime > cached[key]["ctime"]:
                        cached[key] = {
                            "name_en": hero_en,
                            "name_zh": hero_zh,
                            "file": f.name,
                            "ctime": f.stat().st_ctime,
                        }

        # 合并配置中的所有职业
        result = []
        for hero in HEROES:
            hero_zh = HERO_NAMES_ZH.get(hero, hero)
            info = {
                "name_en": hero,
                "name_zh": hero_zh,
                "has_cache": hero in cached,
            }
            if hero in cached:
                info["cache_file"] = cached[hero]["file"]
                info["cache_time"] = time.strftime(
                    "%Y-%m-%d %H:%M", time.localtime(cached[hero]["ctime"])
                )
            result.append(info)

        self._json_response(result)

    def _start_fetch(self, hero_name):
        """启动在线获取任务"""
        if hero_name not in HEROES:
            self._json_response({"error": f"不支持的职业: {hero_name}"}, 400)
            return

        with _task_lock:
            # 如果已有正在运行的任务，返回现有任务
            if hero_name in _fetch_tasks:
                task = _fetch_tasks[hero_name]
                if task.status in ("pending", "fetching"):
                    self._json_response({"status": "running", "hero": hero_name})
                    return

            task = FetchTask(hero_name)
            _fetch_tasks[hero_name] = task
            thread = threading.Thread(target=task.run, daemon=True)
            thread.start()

        self._json_response({"status": "started", "hero": hero_name})

    def _serve_fetch_status(self, hero_name):
        """返回获取任务进度"""
        with _task_lock:
            task = _fetch_tasks.get(hero_name)

        if not task:
            self._json_response({"status": "none"})
            return

        self._json_response(task.to_status_dict())

    def _serve_fetch_result(self, hero_name):
        """返回获取结果"""
        with _task_lock:
            task = _fetch_tasks.get(hero_name)

        if not task:
            self._json_response({"error": "没有获取任务"}, 404)
            return

        if task.status == "done" and task.result:
            self._json_response(task.result)
        elif task.status == "error":
            self._json_response({"error": task.error}, 500)
        else:
            self._json_response({"error": "数据尚未就绪", "status": task.status}, 202)

    def _serve_hero_data(self, hero_name):
        """返回本地缓存数据"""
        data_dir = Path(OUTPUT_DIR)
        if not data_dir.exists():
            self._json_response({"error": "output 目录不存在"}, 404)
            return

        pattern = f"*_{hero_name}_格式化数据_*.json"
        files = list(data_dir.glob(pattern))
        if not files:
            self._json_response({"error": f"未找到 {hero_name} 的本地缓存数据"}, 404)
            return

        latest = max(files, key=os.path.getctime)
        try:
            with open(latest, "r", encoding="utf-8") as f:
                data = json.load(f)
            data["_source"] = "cache"
            self._json_response(data)
        except Exception as e:
            self._json_response({"error": f"读取数据失败: {e}"}, 500)

    def _json_response(self, data, code=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        if "/api/" not in str(args[0]):
            super().log_message(format, *args)


class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    """支持多线程的 TCP 服务器"""
    allow_reuse_address = True
    daemon_threads = True


def find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def main():
    os.chdir(Path(__file__).parent)
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    port = find_free_port()

    with ThreadedTCPServer(("", port), ToolboxHandler) as httpd:
        url = f"http://localhost:{port}/toolbox.html"
        print(f"\n{'=' * 60}")
        print(f"  🛠️  大巴扎职业数据查询工具")
        print(f"  📍 地址: {url}")
        print(f"  📁 数据目录: {os.path.abspath(OUTPUT_DIR)}")
        print(f"  🌐 支持在线获取全部数据")
        print(f"\n  按 Ctrl+C 停止服务器")
        print(f"{'=' * 60}\n")

        webbrowser.open(url)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n\n  服务器已停止")


if __name__ == "__main__":
    main()
