import json


def main():
    fi = input("Filename of file to remove dupes from: ")
    with open(fi, 'r') as f:
        unsorted_spells = json.load(f)
        unsorted_spells = [s for s in unsorted_spells if s.get('source') == 'XGE']
    with open(fi, 'r') as f:
        spells = json.load(f)

    for spell in spells:
        if spell['name'] in [s['name'] for s in unsorted_spells] and not spell.get('source') == 'XGE':
            print(f"Removed {spell['name']} from {spell.get('source')}")
        else:
            unsorted_spells.append(spell)

    with open(f'output/{fi}', 'w') as f:
        json.dump(unsorted_spells, f, sort_keys=True, indent=2)


if __name__ == '__main__':
    main()
