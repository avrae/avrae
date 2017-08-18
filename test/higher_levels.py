import json
import re


def main():
    with open('backup/auto_spells.json', mode='r') as f:
        spells = json.load(f)

    for i, spell in enumerate(spells):
        if isinstance(spell['text'], list):
            text = spell['text']
        else:
            text = spell['text'].splitlines()

        try:
            higherlevel = next(l for l in text if 'at higher levels' in l.lower())
        except StopIteration:
            continue

        if re.search(r'(damage\sincreases?\sby)', higherlevel.lower()):
            higherlevel = ''.join(re.split(r'(damage\sincreases?\sby)', higherlevel, re.IGNORECASE)[1:])
            print(f"{spell['name']}: {higherlevel}")
            spell_level = int(spell['level'])

            higher_level_dict = {}

            if 'for each slot' in higherlevel:
                dice = re.search(r'\d+d\d+', higherlevel).group(0)
                if spell['type'] == 'save':
                    annotation = re.search(r'(\[[^[\]]+\])', spell['save']['damage']).group(1) or ''
                else:
                    annotation = re.search(r'(\[[^[\]]+\])', spell['atk']['damage']).group(1) or ''

                for lvl in range(spell_level+1, 10):
                    ld = re.search(r'(\d+)(d\d+)', dice)
                    lvlDiceNum = int(ld.group(1))
                    lvlDiceVal = ld.group(2)
                    lvlDiff = lvl - spell_level
                    lvlDice = f"{lvlDiceNum*lvlDiff}{lvlDiceVal}"
                    higher_level_dict[str(lvl)] = f'{lvlDice}{annotation}'

            print(higher_level_dict)
            print()

            spells[i]['higher_levels'] = higher_level_dict

    with open('output/auto_spells.json', mode='w') as f:
        json.dump(spells, f, sort_keys=True, indent=4)

if __name__ == '__main__':
    main()
    print('done')