"""BazaarDB 数据获取工具 - 配置文件"""

# bazaardb.gg 网站配置
BASE_URL = "https://bazaardb.gg"
API_CARD_URL = f"{BASE_URL}/api/card"
SEARCH_URL = f"{BASE_URL}/search"

# 默认职业（海盗）
DEFAULT_HERO = "Vanessa"

# 搜索参数
# k:vanessa 表示按 Vanessa 职业筛选
SEARCH_QUERY = "k:vanessa"

# 数据类别
CATEGORY_ITEMS = "items"
CATEGORY_SKILLS = "skills"
CATEGORY_EVENTS = "events"
CATEGORY_MONSTERS = "monsters"
CATEGORY_TRAINERS = "trainers"
CATEGORY_MERCHANTS = "merchants"

# 支持的职业列表（含通用分类）
HEROES = [
    "Common",      # 通用
    "Vanessa",     # 海盗
    "Karnok",      # 卡诺克
    "Dooley",      # 杜利
    "Pygmalien",   # 皮格马利安
    "Mak",         # 马克
    "Stelle",      # 斯特尔
    "Jules",       # 朱尔斯
]

# 纯英雄列表（不含 Common 和 All）
HERO_NAMES = [h for h in HEROES if h != "Common"]

# 中文职业名映射
HERO_NAMES_ZH = {
    "Common": "通用",
    "Vanessa": "海盗",
    "Karnok": "卡诺克",
    "Dooley": "杜利",
    "Pygmalien": "皮格马利安",
    "Mak": "马克",
    "Stelle": "斯特尔",
    "Jules": "朱尔斯",
}

# 全部数据（合并所有分类，不单独获取）
ALL_CATEGORY = "All"
ALL_CATEGORY_ZH = "全部"

# 品质等级（从低到高）
TIER_ORDER = ["Bronze", "Silver", "Gold", "Diamond", "Legendary"]
TIER_NAMES_ZH = {
    "Bronze": "铜",
    "Silver": "银",
    "Gold": "金",
    "Diamond": "钻石",
    "Legendary": "传说",
}

# 物品大小
SIZE_NAMES_ZH = {
    "Small": "小型",
    "Medium": "中型",
    "Large": "大型",
}

# 附魔效果
ENCHANTMENT_NAMES_ZH = {
    "Deadly": "致命",
    "Fiery": "火焰",
    "Heavy": "沉重",
    "Icy": "冰霜",
    "Radiant": "光辉",
    "Restorative": "恢复",
    "Shielded": "护盾",
    "Shiny": "闪耀",
    "Toxic": "剧毒",
    "Turbo": "涡轮",
    "Obsidian": "黑曜石",
    "Golden": "黄金",
}

# 请求头（模拟浏览器）
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
    "sec-ch-ua": '"Not/A)Brand";v="8", "Chromium";v="126", "Google Chrome";v="126"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
}

# API 请求头
API_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Referer": BASE_URL,
    "Origin": BASE_URL,
}

# 输出目录
OUTPUT_DIR = "output"

# 请求延迟（秒），避免触发限流
REQUEST_DELAY = 0.5

# 连续空页提前终止阈值
MAX_EMPTY_PAGES = 15

# 最大重试次数
MAX_RETRIES = 3

# 每页最大结果数
PAGE_SIZE = 50
