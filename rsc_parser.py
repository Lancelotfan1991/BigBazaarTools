"""BazaarDB RSC 组件树解析器（生产版）

适配 bazaardb.gg 16.2+ 的新格式（Next.js 全量服务端渲染 RSC 组件树）。
旧版 pageCards JSON 数组已不存在，改由本模块从渲染后的 React 组件树中提取。

RSC 格式说明：
- 每行是 `{hexid}:{json}`，hexid 是 16 进制 chunk 编号
- 引用 "$L{hexid}" 表示"来自 chunk {hexid} 的 React 元素/值"
- React 元素结构：["$", type, key, props]，文本内容在 props.children
- "$undefined"/"$D..."(日期)/"$@..."(promise)/样式路径 等是特殊占位

英雄过滤：搜索 URL 使用标签过滤参数 `t=t:{hero}`（小写），
物品与技能均生效，例如 /search?c=skills&t=t%3Ajules
"""
import json
import re
import sys
from urllib.parse import unquote

# 卡片树嵌套极深，需提高递归上限
sys.setrecursionlimit(100000)

HERO_TAGS = ("Common", "Vanessa", "Pygmalien", "Dooley", "Mak", "Stelle", "Jules", "Karnok", "The Dragons")


def parse_chunks(content: str) -> dict:
    """把 RSC 响应拆成 {chunkId: parsed_value}"""
    chunks = {}
    for m in re.finditer(r'^([0-9a-f]+):(.*)$', content, re.MULTILINE):
        cid, raw = m.group(1), m.group(2)
        try:
            chunks[cid] = json.loads(raw)
        except Exception:
            chunks[cid] = raw
    return chunks


def resolve(node, chunks, _seen=None):
    """递归解析 $L 引用。用 _seen 跟踪当前路径上的引用做环检测，
    不用固定深度限制（卡片树嵌套极深，深层引用必须展开）。"""
    if _seen is None:
        _seen = frozenset()
    if isinstance(node, str):
        if node.startswith('$L'):
            ref = node[2:]
            if ref in _seen:
                return None
            if ref in chunks:
                return resolve(chunks[ref], chunks, _seen | {ref})
            return None
        if node.startswith('$') and node != '$':
            # $undefined / $D... / $@... / 样式路径等占位
            return None
        return node
    if isinstance(node, list):
        return [resolve(x, chunks, _seen) for x in node]
    if isinstance(node, dict):
        return {k: resolve(v, chunks, _seen) for k, v in node.items()}
    return node


def collect_text(node, out):
    """遍历 React 树，只收集 children 里的纯文本/数字"""
    if node is None or isinstance(node, bool):
        return
    if isinstance(node, (int, float)):
        out.append(str(node))
        return
    if isinstance(node, str):
        if node.startswith('$') or node.startswith('var(') or 'module__' in node:
            return
        out.append(node)
        return
    if isinstance(node, list):
        if len(node) >= 4 and node[0] == '$':
            props = node[3]
            if isinstance(props, dict) and 'children' in props:
                collect_text(props['children'], out)
            return
        for x in node:
            collect_text(x, out)
        return
    if isinstance(node, dict):
        if 'children' in node:
            collect_text(node['children'], out)


def find_cards(node, cards):
    """在解析后的树里找到所有卡片容器（key 以 'card:' 开头）"""
    if isinstance(node, list):
        if len(node) >= 4 and node[0] == '$' and isinstance(node[2], str):
            if node[2].startswith('card:'):
                cards.append(node)
        for x in node:
            find_cards(x, cards)
    elif isinstance(node, dict):
        for v in node.values():
            find_cards(v, cards)


def _find_title(n):
    if isinstance(n, list):
        if len(n) >= 4 and n[0] == '$' and n[1] == 'h3':
            props = n[3] if isinstance(n[3], dict) else {}
            cls = props.get('className', '')
            if isinstance(cls, str) and 'title' in cls.lower():
                txt = []
                collect_text(props.get('children'), txt)
                return ''.join(txt).strip()
        for x in n:
            r = _find_title(x)
            if r:
                return r
    elif isinstance(n, dict):
        for v in n.values():
            r = _find_title(v)
            if r:
                return r
    return None


def _find_effects(n, results):
    """收集 tooltip 效果文本，跳过附魔（Enchantment）子树"""
    if isinstance(n, list):
        if len(n) >= 4 and n[0] == '$':
            props = n[3] if isinstance(n[3], dict) else {}
            if 'enchantmentName' in props:
                return
            cls = props.get('className', '')
            if isinstance(cls, str) and 'EnchantmentTooltips' in cls:
                return
            if isinstance(cls, str) and 'primaryRow' in cls:
                txt = []
                collect_text(props.get('children'), txt)
                line = ''.join(txt).strip()
                if line:
                    results.append(line)
                return
        for x in n:
            _find_effects(x, results)
    elif isinstance(n, dict):
        for v in n.values():
            _find_effects(v, results)


def _find_cooldown(n):
    if isinstance(n, list):
        if len(n) >= 4 and n[0] == '$':
            props = n[3] if isinstance(n[3], dict) else {}
            cls = props.get('className', '')
            if isinstance(cls, str) and 'CooldownAbility' in cls and 'value' in cls:
                txt = []
                collect_text(props.get('children'), txt)
                vals = [t for t in txt if re.match(r'^[\d.]+$', t.strip())]
                if vals:
                    return ' » '.join(vals)
        for x in n:
            r = _find_cooldown(x)
            if r:
                return r
    elif isinstance(n, dict):
        for v in n.values():
            r = _find_cooldown(v)
            if r:
                return r
    return None


def _find_multicast(n):
    if isinstance(n, list):
        if len(n) >= 4 and n[0] == '$':
            props = n[3] if isinstance(n[3], dict) else {}
            ch = props.get('children')
            if isinstance(ch, list) and 'Multicast' in ch:
                txt = []
                collect_text(ch, txt)
                vals = [t for t in txt if re.match(r'^\d+$', t.strip())]
                if vals:
                    return ' » '.join(vals)
        for x in n:
            r = _find_multicast(x)
            if r:
                return r
    elif isinstance(n, dict):
        for v in n.values():
            r = _find_multicast(v)
            if r:
                return r
    return None


def extract_card_info(card_node) -> dict:
    """从单张卡片节点提取结构化信息（中文键）"""
    info = {'名称': None, '英雄': None, '品质': None, '标签': [],
            '卡片ID': None, '图标': None, '冷却': None, '多重释放': None, '效果': []}

    def walk(n):
        if isinstance(n, list):
            if len(n) >= 4 and n[0] == '$':
                props = n[3] if isinstance(n[3], dict) else {}
                href = props.get('href', '')
                if isinstance(href, str) and href.startswith('/card/') and not info['卡片ID']:
                    parts = href.split('/')
                    if len(parts) >= 3:
                        info['卡片ID'] = parts[2]
                src = props.get('src', '')
                if isinstance(src, str) and 's.bazaardb.gg' in src and not info['图标']:
                    info['图标'] = src
                # 英雄标签: {"text":"Jules","displayedInGame":false}（无 rawTag / tier）
                if 'text' in props and 'displayedInGame' in props and 'rawTag' not in props and 'tier' not in props:
                    if props.get('text') in HERO_TAGS:
                        info['英雄'] = props['text']
                # 品质: {"tier":"白银+","rawTier":"Silver+"}
                if 'rawTier' in props and not info['品质']:
                    info['品质'] = props.get('rawTier')
                # 显示标签: {"text":"食物","rawTag":"Food","displayedInGame":true}
                if 'rawTag' in props and props.get('displayedInGame'):
                    tag = props.get('rawTag')
                    if tag and tag not in info['标签']:
                        info['标签'].append(tag)
            for x in n:
                walk(x)
        elif isinstance(n, dict):
            for v in n.values():
                walk(v)

    walk(card_node)
    info['名称'] = _find_title(card_node)

    eff = []
    _find_effects(card_node, eff)
    seen = set()
    for e in eff:
        if e not in seen:
            seen.add(e)
            info['效果'].append(e)

    info['冷却'] = _find_cooldown(card_node)
    info['多重释放'] = _find_multicast(card_node)
    return info


def extract_version(content: str, chunks: dict = None) -> str:
    """从 RSC 内容中提取数据版本，如 '16.2 (Jul 17)' / '17.0 (Aug 5)'"""
    if chunks is None:
        chunks = parse_chunks(content)
    for val in chunks.values():
        if isinstance(val, list) and len(val) >= 4 and val[1] == 'code':
            props = val[3]
            if isinstance(props, dict):
                ch = props.get('children')
                if isinstance(ch, list) and any(re.match(r'^\d+\.\d+', str(x)) for x in ch):
                    return ''.join(str(x) for x in ch)
    return None


def extract_total_pages(content: str):
    """提取 totalPages"""
    m = re.search(r'"totalPages":(\d+)', content)
    return int(m.group(1)) if m else None


def parse_search_content(content: str):
    """解析一页搜索结果的 RSC 文本。

    Returns:
        (cards_info, version, total_pages)
        cards_info: 每张卡片的中文键信息 dict 列表（已按卡片 key 去重）
    """
    chunks = parse_chunks(content)
    version = extract_version(content, chunks)
    total_pages = extract_total_pages(content)
    resolved = {cid: resolve(val, chunks) for cid, val in chunks.items()}
    cards = []
    for val in resolved.values():
        find_cards(val, cards)
    seen = set()
    infos = []
    for c in cards:
        key = c[2]
        if key in seen:
            continue
        seen.add(key)
        infos.append(extract_card_info(c))
    return infos, version, total_pages


_GAME_CONTAINER_RE = re.compile(r'Card-module__\w+__card\b')


def _find_game_containers(node, out):
    """在解析后的树里找游戏数据卡片容器（className 含 Card-module__xxx__card）。

    monsters 容器 key 为 UUID 字符串，events 等容器 key 为列表序号（非字符串），
    因此用 id() 做实例去重，最终按 href 去重（同一容器会被多个 chunk 引用展开）。
    命中容器后不再深入，避免嵌套重复。
    """
    if isinstance(node, list):
        if len(node) >= 4 and node[0] == '$' and isinstance(node[3], dict):
            cls = node[3].get('className', '')
            if isinstance(cls, str) and _GAME_CONTAINER_RE.search(cls):
                if id(node) not in out:
                    out[id(node)] = node
                return
        for x in node:
            _find_game_containers(x, out)
    elif isinstance(node, dict):
        for v in node.values():
            _find_game_containers(v, out)


def _first_href(node):
    """子树内第一个 /card/ 链接"""
    if isinstance(node, list):
        for x in node:
            r = _first_href(x)
            if r:
                return r
    elif isinstance(node, dict):
        h = node.get('href')
        if isinstance(h, str) and h.startswith('/card/'):
            return h
        for v in node.values():
            r = _first_href(v)
            if r:
                return r
    return None


def _find_mm(node):
    """子树内第一个怪物元数据块（{'mm': {available,day,health,board,skills}} 的 props）"""
    if isinstance(node, list):
        for x in node:
            r = _find_mm(x)
            if r:
                return r
    elif isinstance(node, dict):
        if isinstance(node.get('mm'), dict):
            return node['mm']
        for v in node.values():
            r = _find_mm(v)
            if r:
                return r
    return None


def extract_game_card_info(container) -> dict:
    """从游戏数据卡片容器提取结构化信息。

    在 extract_card_info 基础上补充：
    - slug: href 末段 URL 解码（中文页为中文名，英文页为英文-连字符）
    - 容器品质: style 里 --gradient-base-tier 变量（游戏卡无 rawTier 组件）
    - 描述: 容器可见文本去掉标题前缀
    - mm: 怪物元数据（仅 monsters）
    - 金币/经验: 战斗奖励（仅 monsters，渲染为 '2 Gold'/'3 XP' 文本）
    """
    info = extract_card_info(container)
    href = _first_href(container)
    info['slug'] = unquote(href.split('/')[-1]) if href else ''
    if not info['卡片ID'] and href:
        parts = href.split('/')
        if len(parts) >= 3:
            info['卡片ID'] = parts[2]

    props = container[3] if isinstance(container[3], dict) else {}
    style = props.get('style') or {}
    gt = style.get('--gradient-base-tier', '')
    if isinstance(gt, str):
        m = re.match(r'var\(--(\w+)-rgb\)', gt)
        if m and not info['品质']:
            info['品质'] = m.group(1).capitalize()

    txt = []
    collect_text(container, txt)
    joined = ''.join(txt).strip()
    name = info['名称'] or ''
    info['描述'] = joined[len(name):].strip() if name and joined.startswith(name) else ''

    info['mm'] = _find_mm(container)
    gold = xp = None
    for i in range(1, len(txt)):
        cur = txt[i].strip()
        prev = txt[i - 1].strip()
        if re.fullmatch(r'\d+', prev):
            if cur == 'Gold':
                gold = int(prev)
            elif cur == 'XP':
                xp = int(prev)
    info['金币'] = gold
    info['经验'] = xp
    return info


def parse_game_content(content: str):
    """解析一页游戏数据（events/monsters/trainers/merchants）的 RSC 文本。

    17.0 起游戏数据改为卡片组件树渲染（旧 pageCards/"cards":[ 格式已废弃），
    monsters 为单页全量（含 mm 元数据块），其余按 totalPages 分页。

    Returns:
        (cards_info, version, total_pages)
    """
    chunks = parse_chunks(content)
    version = extract_version(content, chunks)
    total_pages = extract_total_pages(content)
    resolved = {cid: resolve(val, chunks) for cid, val in chunks.items()}
    containers = {}
    for val in resolved.values():
        _find_game_containers(val, containers)
    # 同一卡片被多个 chunk 引用会展开成不同对象，按 href 去重
    seen_href = set()
    infos = []
    for c in containers.values():
        href = _first_href(c) or ''
        if href and href in seen_href:
            continue
        if href:
            seen_href.add(href)
        infos.append(extract_game_card_info(c))
    return infos, version, total_pages
