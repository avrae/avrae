import json

OVERRIDES = ('+1', '+2', '+3', 'giant strength', 'ioun stone', 'horn of valhalla', 'vorpal', 'of sharpness',
             'of answering', 'instrument of the bard', 'nine lives', 'frost brand', 'carpet of flying', 'vicious',
             'of wounding', 'of life stealing', 'of protection', 'adamantine', 'of wondrous power', 'luck blade')
TYPES = ('W', 'P', 'ST', 'RD', 'RG', 'WD')


def main():
    with open('items.json') as f:
        items = json.load(f)
    with open('srd-items.txt') as f:
        srd = [s.strip().lower() for s in f.read().split('\n')]

    for item in items:
        if item['name'].lower() in srd or any(i in item['name'].lower() for i in OVERRIDES) or not any(
                i in item.get('type', '').split(',') for i in TYPES):
            item['srd'] = True
        else:
            item['srd'] = False

    for sp in srd:
        if not sp in [s['name'].lower() for s in items]:
            print(sp)

    with open('srdproc.json', 'w') as f:
        json.dump(items, f, indent=2, sort_keys=True)


if __name__ == '__main__':
    main()
