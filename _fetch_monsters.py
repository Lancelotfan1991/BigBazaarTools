import json, time
from fetcher import BazaarDBFetcher
from parser import card_to_display

print('Fetching monster data...')
f = BazaarDBFetcher()
f.connect()
raw_cards = f.fetch_game_data('monsters')
display_cards = [card_to_display(card) for card in raw_cards]

result = {
    '职业': '怪物',
    '英文名': 'monsters',
    '获取时间': time.strftime('%Y-%m-%d %H:%M:%S'),
    '物品数量': len(display_cards),
    '技能数量': 0,
    '物品': display_cards,
    '技能': [],
}

out = 'e:/Test/bazaar-vue/public/data/monsters.json'
with open(out, 'w', encoding='utf-8') as fp:
    json.dump(result, fp, ensure_ascii=False, indent=2)

# Verify Chinese names
for c in display_cards:
    info = c.get('怪物信息')
    if info and info.get('技能'):
        print(f"示例: {c['名称']}")
        for sk in info['技能']:
            print(f"  技能: {sk['名称']} ({sk.get('英文名','')})")
        break

has_skills = sum(1 for c in display_cards if c.get('怪物信息') and c['怪物信息'].get('技能'))
total_skills = sum(len(c['怪物信息']['技能']) for c in display_cards if c.get('怪物信息') and c['怪物信息'].get('技能'))
print(f'\n怪物总数: {len(display_cards)}')
print(f'有技能: {has_skills}')
print(f'技能总数: {total_skills}')
print(f'Saved to {out}')
