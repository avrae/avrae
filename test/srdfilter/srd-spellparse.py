import json


def main():
    with open('spells.json') as f:
        spells = json.load(f)
    with open('srd-spells.txt') as f:
        srd = [s.strip() for s in f.read().split('\n')]

    for spell in spells:
        if spell['name'] in srd:
            spell['srd'] = True
        else:
            spell['srd'] = False

    for sp in srd:
        if not sp in [s['name'] for s in spells]:
            print(sp)

    with open('srdproc.json', 'w') as f:
        json.dump(spells, f, indent=4, sort_keys=True)


if __name__ == '__main__':
    main()
