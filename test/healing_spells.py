import json
import re


def main():
    with open('backup/heal_spell_before_parse.json', mode='r') as f:
        auto_spells = json.load(f)

    with open('backup/spells.json', mode='r') as f:
        spells = json.load(f)

    healing_spells = 'Cure Wounds, Healing Word, Mass Cure Wounds, Mass Healing Word, Goodberry, Heal, Prayer of Healing, Aura of Vitality, Regenerate'.split(', ')

    for i, spell in enumerate(spells):
        if not spell['name'].lower() in [h.lower() for h in healing_spells]: continue

        if isinstance(spell['text'], list):
            text = spell['text']
        else:
            text = spell['text'].splitlines()

        spell['damage'] = f"-({spell.get('roll', 'PLACEHOLDER')})[heal]"
        spell['type'] = 'heal'

        try:
            higherlevel = next(l for l in text if 'at higher levels' in l.lower())
        except StopIteration:
            auto_spells.append(spell)
            print(spell)
            continue

        if re.search(r'(healing\sincreases?\sby)', higherlevel.lower()):
            higherlevel = ''.join(re.split(r'(healing\sincreases?\sby)', higherlevel, re.IGNORECASE)[1:])
            print(f"{spell['name']}: {higherlevel}")
            spell_level = int(spell['level'])

            higher_level_dict = {}

            if 'for each slot' in higherlevel:
                dice = re.search(r'\d+d\d+', higherlevel)
                if dice is not None:
                    dice = dice.group(0)
                    annotation = re.search(r'(\[[^[\]]+\])', spell['damage']).group(1) or ''

                    for lvl in range(spell_level+1, 10):
                        ld = re.search(r'(\d+)(d\d+)', dice)
                        lvlDiceNum = int(ld.group(1))
                        lvlDiceVal = ld.group(2)
                        lvlDiff = lvl - spell_level
                        lvlDice = f"{lvlDiceNum*lvlDiff}{lvlDiceVal}"
                        higher_level_dict[str(lvl)] = f'-({lvlDice}{annotation})'

            print(higher_level_dict)
            print()

            spell['higher_levels'] = higher_level_dict

        auto_spells.append(spell)
        print(spell)

    with open('output/auto_spells.json', mode='w') as f:
        json.dump(auto_spells, f, sort_keys=True, indent=2)
    # print(auto_spells)

if __name__ == '__main__':
    main()
    print('done')