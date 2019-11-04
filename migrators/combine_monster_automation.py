import json

with open('srd-bestiary.json') as f:
    mons = json.load(f)

with open('monsters.json') as f:
    automation = json.load(f)

for monster in mons:
    try:
        monauto = next(m for m in automation if m['name'] == monster['name'])
    except StopIteration:
        print(f"Could not find automation for {monster['name']}")
        continue

    monster['attacks'] = monauto['attacks']

with open('srd-bestiary-out.json', 'w') as f:
    json.dump(mons, f, indent=2)

print("Done!")
