import json


def main():
    with open('input/feats.json', 'r') as f:
        feats = json.load(f)

    xge_feats = [f['name'] for f in feats if f['source'] == 'XGE']

    out = []
    for feat in feats:
        if not feat['source'] == 'XGE' and feat['name'] in xge_feats:
            pass
        else:
            out.append(feat)


    with open('output/feats.json', 'w') as f:
        json.dump(out, f, sort_keys=True, indent=2)


if __name__ == '__main__':
    main()
