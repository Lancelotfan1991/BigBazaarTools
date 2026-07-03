import json, sys
sys.stdout.reconfigure(encoding='utf-8')
d = json.load(open('mobile-app/data/All.json', 'r', encoding='utf-8'))
items = [i for i in d['物品'] if i.get('英文名') == 'Figurehead']
if items:
    print(json.dumps(items[0], ensure_ascii=False, indent=2))
else:
    print("Not found")
