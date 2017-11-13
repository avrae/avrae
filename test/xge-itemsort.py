import json


def main():
    with open('input/items.json', 'r') as f:
        items = json.load(f)
    with open('input/xge-items.json', 'r') as f:
        new_items = json.load(f)

    for item in new_items:
        if item.get('source') == 'XGE':
            items.append(item)

    with open('output/items.json', 'w') as f:
        json.dump(items, f, sort_keys=True, indent=2)


if __name__ == '__main__':
    main()
