"""BazaarDB 数据获取模块

通过 bazaardb.gg 的 RSC（React Server Components）端点获取数据。

核心发现（16.2+ 新格式）：
- 搜索页面使用 Next.js 全量服务端渲染的 RSC 组件树
- 通过 Accept: text/x-component + RSC: 1 头可以获取纯数据
- 旧版 pageCards JSON 数组已不存在，卡片数据渲染在 React 组件树中，
  由 rsc_parser 模块解析
- 英雄过滤使用标签参数 t=t:{hero}（小写），物品与技能均生效
- totalPages 表示总页数，page 参数控制分页（1-indexed）
- 每页 10 张卡片
"""

import json
import logging
import re
import time
from typing import Optional
from urllib.parse import urlencode

import requests

from config import (
    BASE_URL,
    CATEGORY_ITEMS,
    CATEGORY_SKILLS,
    CATEGORY_EVENTS,
    CATEGORY_MONSTERS,
    CATEGORY_TRAINERS,
    CATEGORY_MERCHANTS,
    DEFAULT_HERO,
    HEADERS,
    HERO_NAMES,
    HERO_NAMES_ZH,
    MAX_RETRIES,
    OUTPUT_DIR,
    REQUEST_DELAY,
    SEARCH_URL,
)
from rsc_parser import parse_search_content, extract_total_pages

logger = logging.getLogger(__name__)


def _info_to_record(info: dict, hero: str) -> dict:
    """把 rsc_parser 的中文键卡片信息映射为 parser.normalize_card 可消费的记录。

    Args:
        info: rsc_parser.extract_card_info 的输出（中文键）
        hero: 当前搜索的英雄（作为权威归属，因为使用了 t=t:hero 过滤）
    """
    card_id = info.get("卡片ID") or ""
    name = info.get("名称") or ""

    # 品质：rawTier 形如 "Silver+"/"Gold+"/"Diamond"，去掉末尾 '+' 供中文映射
    raw_tier = info.get("品质") or ""
    base_tier = raw_tier.rstrip("+")

    tags = info.get("标签") or []

    # 英雄归属：t=t:hero 过滤已保证归属，优先用过滤英雄；保留卡面英雄标签作参考
    heroes = [hero]

    # 效果 → tooltips（数值分级 » 已在文本内联，无需 replacements）
    tooltips = [{"text": e, "type": "", "condition": ""} for e in (info.get("效果") or [])]

    # 冷却/多重释放放入 base_attributes（未知键会被 format_base_attributes 原样保留）
    base_attributes = {}
    if info.get("冷却"):
        base_attributes["冷却时间(秒)"] = info["冷却"]
    if info.get("多重释放"):
        base_attributes["多重释放"] = info["多重释放"]

    icon = info.get("图标") or ""

    return {
        "id": card_id,
        "name": name,
        "type": tags[0] if tags else "",
        "size": "",  # 新版全量 SSR 页面不再以文本形式渲染大小
        "base_tier": base_tier,
        "heroes": heroes,
        "tags": tags,
        "display_tags": tags,
        "base_attributes": base_attributes,
        "tooltips": tooltips,
        "tooltip_replacements": {},
        "art": icon,
        "art_large": icon,
        "art_fg": "",
        "uri": f"/card/{card_id}" if card_id else "",
        "_hero_tag": info.get("英雄"),
        "_cooldown": info.get("冷却"),
        "_multicast": info.get("多重释放"),
    }


class BazaarDBFetcher:
    """从 bazaardb.gg 获取数据的客户端"""

    def __init__(self, method: str = "auto"):
        """
        初始化数据获取客户端

        Args:
            method: 获取方式，可选 "cloudscraper"（Cloudflare 绕过）,
                    "direct"（直接请求）,
                    "auto"（自动选择可用方式）
        """
        self.method = method
        self.session = None

    def _init_session_cloudscraper(self):
        """初始化 cloudscraper 会话"""
        try:
            import cloudscraper
            scraper = cloudscraper.create_scraper(
                browser={"browser": "chrome", "platform": "windows", "desktop": True}
            )
            scraper.headers.update(HEADERS)
            # 设置代理和重试策略
            adapter = requests.adapters.HTTPAdapter(
                max_retries=requests.adapters.Retry(
                    total=5,
                    backoff_factor=1,
                    status_forcelist=[429, 500, 502, 503, 504],
                )
            )
            scraper.mount("https://", adapter)
            scraper.mount("http://", adapter)
            return scraper
        except ImportError:
            logger.warning("cloudscraper 未安装，请运行: pip install cloudscraper")
            return None

    def _init_session_direct(self) -> requests.Session:
        """初始化直接请求会话"""
        session = requests.Session()
        session.headers.update(HEADERS)
        session.trust_env = False  # 忽略系统代理
        adapter = requests.adapters.HTTPAdapter(
            max_retries=requests.adapters.Retry(
                total=5,
                backoff_factor=1,
                status_forcelist=[429, 500, 502, 503, 504],
            )
        )
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        return session

    def connect(self):
        """建立连接，初始化会话"""
        if self.method == "auto":
            # 优先使用 cloudscraper
            session = self._init_session_cloudscraper()
            if session:
                self.session = session
                self.method = "cloudscraper"
                logger.info("已创建 cloudscraper 会话")
                return

            # 备用：直接请求
            session = self._init_session_direct()
            self.session = session
            self.method = "direct"
            logger.info("已创建直接请求会话")
            return

        elif self.method == "cloudscraper":
            session = self._init_session_cloudscraper()
            if session:
                self.session = session
            else:
                raise RuntimeError("cloudscraper 未安装，请运行: pip install cloudscraper")

        elif self.method == "direct":
            self.session = self._init_session_direct()

        logger.info(f"使用获取方式: {self.method}")

    def close(self):
        """关闭连接和资源"""
        if self.session:
            self.session.close()

    def _fetch_rsc_page(self, url: str, retries: int = MAX_RETRIES) -> Optional[str]:
        """
        获取 RSC 页面数据

        Args:
            url: 目标 URL
            retries: 最大重试次数

        Returns:
            RSC 响应文本
        """
        headers = {
            "Accept": "text/x-component",
            "RSC": "1",
            "Next-Url": url.replace(BASE_URL, ""),
            "User-Agent": HEADERS["User-Agent"],
            # 使用中文获取中文物品名
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }

        def _decode(resp):
            """手动 UTF-8 解码，避免 requests 误判为 ISO-8859-1"""
            return resp.content.decode("utf-8", errors="replace")

        for attempt in range(retries):
            try:
                import cloudscraper
                s = cloudscraper.create_scraper(
                    browser={"browser": "chrome", "platform": "windows", "desktop": True}
                )
                resp = s.get(url, headers=headers, timeout=30)
                s.close()
                if resp.status_code == 200:
                    return _decode(resp)
                elif resp.status_code == 403:
                    logger.warning(f"请求被拒绝 (403)，第 {attempt + 1} 次重试...")
                    time.sleep(REQUEST_DELAY * 3)
                else:
                    logger.warning(f"请求返回状态码 {resp.status_code}")
                    return None
            except requests.exceptions.ProxyError:
                logger.warning(f"代理错误，尝试直连，第 {attempt + 1} 次重试...")
                try:
                    s = requests.Session()
                    s.trust_env = False
                    resp = s.get(url, headers=headers, timeout=30)
                    s.close()
                    if resp.status_code == 200:
                        return _decode(resp)
                except Exception as e2:
                    logger.debug(f"直连也失败: {e2}")
                time.sleep(REQUEST_DELAY)
            except requests.RequestException as e:
                logger.warning(f"请求异常: {e}，第 {attempt + 1} 次重试...")
                time.sleep(REQUEST_DELAY)
        return None

    def _parse_rsc_page_cards(self, rsc_content: str) -> tuple:
        """
        从 RSC 响应中解析 pageCards 数据
    
        支持两种格式：
        1. 纯 RSC 格式（Accept: text/x-component 返回的格式）
        2. HTML 格式（包含 self.__next_f.push 的格式）
    
        Args:
            rsc_content: RSC 响应文本
    
        Returns:
            (cards列表, total数, 当前page)
        """
        cards = []
        total = 0
        page = 0
    
        search_text = rsc_content

        # 格式1: 纯 RSC 格式 - pageCards 直接在文本中
        # 格式2: HTML 格式 - 需要先解码 self.__next_f.push
        if 'pageCards' not in rsc_content and 'self.__next_f.push' in rsc_content:
            # 需要解码 HTML 中的 RSC 数据
            rsc_chunks = re.findall(r'self\.__next_f\.push\(\[1,"(.+?)"\]\)', rsc_content)
            decoded = ""
            for chunk in rsc_chunks:
                try:
                    decoded += chunk.encode().decode('unicode_escape')
                except (UnicodeDecodeError, UnicodeEncodeError):
                    decoded += chunk
            search_text = decoded if decoded else rsc_content
    
        # 提取 pageCards - 在 RSC 格式中，pageCards 是 JSON 数组
        page_cards_match = re.search(
            r'"pageCards":\[(.+?)\],"total"',
            search_text,
            re.DOTALL,
        )
    
        if page_cards_match:
            try:
                cards_json = "[" + page_cards_match.group(1) + "]"
                cards = json.loads(cards_json)
            except json.JSONDecodeError as e:
                logger.debug(f"解析 pageCards JSON 失败: {e}")
                # 尝试修复常见的 JSON 问题
                try:
                    raw = page_cards_match.group(1)
                    cards = json.loads("[" + raw + "]")
                except Exception:
                    logger.error("修复 JSON 也失败")
    
        # 回退：尝试 monsters 格式 ("cards":[...])
        if not cards:
            cards_marker = '"cards":['
            marker_pos = search_text.find(cards_marker)
            if marker_pos >= 0:
                # 逐个提取 JSON 对象（RSC 格式可能包含非标准元素）
                idx = marker_pos + len(cards_marker)
                extracted = []
                while idx < len(search_text):
                    # 跳过空白和逗号
                    while idx < len(search_text) and search_text[idx] in ' ,\n\r\t':
                        idx += 1
                    if idx >= len(search_text) or search_text[idx] == ']':
                        break
                    if search_text[idx] != '{':
                        # 跳过 RSC 引用等非对象元素
                        if search_text[idx] == '"':
                            idx += 1
                            while idx < len(search_text) and search_text[idx] != '"':
                                if search_text[idx] == '\\': idx += 1
                                idx += 1
                            idx += 1
                        else:
                            idx += 1
                        continue
                    # 括号匹配提取单个 JSON 对象
                    depth = 0
                    in_str = False
                    esc = False
                    obj_start = idx
                    obj_end = idx
                    for j in range(idx, len(search_text)):
                        ch = search_text[j]
                        if esc: esc = False; continue
                        if ch == '\\': esc = True; continue
                        if ch == '"': in_str = not in_str; continue
                        if in_str: continue
                        if ch == '{': depth += 1
                        elif ch == '}':
                            depth -= 1
                            if depth == 0:
                                obj_end = j
                                break
                    try:
                        obj = json.loads(search_text[obj_start:obj_end+1])
                        extracted.append(obj)
                    except json.JSONDecodeError:
                        pass
                    idx = obj_end + 1
                if extracted:
                    cards = extracted
                    total = len(cards)
                    logger.info(f"使用 cards 格式解析到 {len(cards)} 条数据")
    
        # 提取 total
        total_match = re.search(r'"total":(\d+)', search_text)
        if total_match:
            total = int(total_match.group(1))
    
        # 提取当前页码
        page_match = re.search(r'"page":(\d+)', search_text)
        if page_match:
            page = int(page_match.group(1))
    
        return cards, total, page

    def _search_cards_raw(self, category: str, query: str, max_pages: int = None) -> list:
        """
        用指定搜索词获取卡片数据（自动分页）

        Args:
            category: 类别 "items" 或 "skills"
            query: 搜索关键词
            max_pages: 最大页数限制

        Returns:
            卡片数据列表（不做 Heroes 过滤）
        """
        params = {
            "q": query,
            "c": category,
        }
        base_search_url = f"{SEARCH_URL}?{urlencode(params)}"

        all_cards = []
        current_page = 1
        empty_pages = 0

        while True:
            page_url = f"{base_search_url}&page={current_page}"
            logger.info(f"获取第 {current_page} 页: {page_url}")

            rsc_content = self._fetch_rsc_page(page_url)
            if not rsc_content:
                logger.warning(f"第 {current_page} 页获取失败，停止分页")
                break

            cards, total, page_idx = self._parse_rsc_page_cards(rsc_content)

            if not cards:
                logger.info(f"第 {current_page} 页无数据，停止分页 (共 {total} 条)")
                break

            all_cards.extend(cards)
            logger.info(f"  获取到 {len(cards)} 张（总计: {len(all_cards)}/{total}）")

            if max_pages and current_page >= max_pages:
                break

            current_page += 1
            time.sleep(REQUEST_DELAY)

        return all_cards

    def search_cards(self, category: str, hero: str = DEFAULT_HERO, max_pages: int = None) -> list:
        """搜索指定英雄 + 分类的卡片数据（使用 t=t:{hero} 标签过滤，自动分页）。

        英雄过滤机制（16.2+）：搜索 URL 用标签参数 t=t:{hero}（小写），
        物品与技能均生效，服务端直接返回该英雄专属卡池，无需再按 Heroes 字段过滤。

        Args:
            category: 类别 "items" 或 "skills"
            hero: 英雄名（含 Common），默认 Vanessa
            max_pages: 最大页数限制（None 表示获取全部）

        Returns:
            标准化记录列表（可直接交给 parser.normalize_card）
        """
        tag_value = f"t:{hero.lower()}"
        params = {"c": category, "t": tag_value}
        base_search_url = f"{SEARCH_URL}?{urlencode(params)}"

        logger.info(f"🔍 搜索 {hero} {category}（过滤 {tag_value}）...")

        seen_ids = set()
        records = []
        current_page = 1
        total_pages = None

        while True:
            page_url = f"{base_search_url}&page={current_page}"
            rsc_content = self._fetch_rsc_page(page_url)
            if not rsc_content:
                logger.warning(f"第 {current_page} 页获取失败，停止分页")
                break

            infos, version, tp = parse_search_content(rsc_content)
            if total_pages is None and tp:
                total_pages = tp
                logger.info(f"  数据版本={version}, 总页数={total_pages}")

            if not infos:
                logger.info(f"第 {current_page} 页无卡片，停止分页")
                break

            page_new = 0
            for info in infos:
                rec = _info_to_record(info, hero)
                cid = rec["id"] or rec["name"]
                if not cid or cid in seen_ids:
                    continue
                seen_ids.add(cid)
                records.append(rec)
                page_new += 1

            logger.info(f"  第 {current_page}/{total_pages or '?'} 页: +{page_new}（累计 {len(records)}）")

            if max_pages and current_page >= max_pages:
                break
            if total_pages and current_page >= total_pages:
                break
            current_page += 1
            time.sleep(REQUEST_DELAY)

        logger.info(f"📦 {hero} {category}: {len(records)} 个")
        return records

    def fetch_hero_data(self, hero: str = DEFAULT_HERO, max_pages: int = None) -> dict:
        """
        获取指定职业的所有物品和技能数据

        Args:
            hero: 职业英文名，默认 Vanessa（海盗）
            max_pages: 最大页数限制（None 表示获取全部）

        Returns:
            包含 items 和 skills 的字典
        """
        hero_zh = HERO_NAMES_ZH.get(hero, hero)

        result = {
            "hero": hero,
            "hero_zh": hero_zh,
            "items": [],
            "skills": [],
        }

        # 搜索物品
        logger.info("=" * 50)
        logger.info(f"开始获取 {hero}（{hero_zh}）的物品数据...")
        logger.info("=" * 50)
        items = self.search_cards(CATEGORY_ITEMS, hero, max_pages)
        result["items"] = items

        time.sleep(REQUEST_DELAY)

        # 搜索技能
        logger.info("=" * 50)
        logger.info(f"开始获取 {hero}（{hero_zh}）的技能数据...")
        logger.info("=" * 50)
        skills = self.search_cards(CATEGORY_SKILLS, hero, max_pages)
        result["skills"] = skills

        return result

    # 向后兼容旧方法名
    def fetch_all_karnok_data(self, **kwargs):
        """已弃用：请使用 fetch_hero_data"""
        return self.fetch_hero_data(**kwargs)

    def fetch_game_data(self, category: str) -> list:
        """
        获取游戏数据（事件/怪物/训练师）

        Args:
            category: "events", "monsters", 或 "trainers"

        Returns:
            卡片数据列表
        """
        category_names = {
            CATEGORY_EVENTS: "事件",
            CATEGORY_MONSTERS: "怪物",
            CATEGORY_TRAINERS: "训练师",
            CATEGORY_MERCHANTS: "商人",
        }
        name = category_names.get(category, category)
        logger.info("=" * 50)
        logger.info(f"开始获取{name}数据...")
        logger.info("=" * 50)

        if category == CATEGORY_MONSTERS:
            # monsters 一次返回全部，只需 page=1
            raw_cards = self._search_cards_raw(category, "", max_pages=1)
        else:
            raw_cards = self._search_cards_raw(category, "")

        # 去重
        seen_ids = set()
        unique_cards = []
        for card in raw_cards:
            card_id = card.get("Id") or card.get("id") or card.get("Name") or card.get("name")
            if card_id and card_id not in seen_ids:
                seen_ids.add(card_id)
                unique_cards.append(card)

        logger.info(f"📦 {name}: {len(unique_cards)} 个")
        return unique_cards
