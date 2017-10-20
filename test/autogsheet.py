import pygsheets

from cogs5e.funcs.lookupFuncs import *

PARENT_FOLDER_ID = '0B7G4hVfa4Trwak1vUWF2U19KaDA'
TEMPLATE_SPREADSHEET_ID = '1etrBJ0qCDXACovYHUM4XvjE0erndThwRLcUQzX6ts8w'
TEMPLATE_WORKSHEET_ID = '1750226729'
FEATURES_CELLS = [f"Z{i}" for i in range(45, 57)] + [f"AH{i}" for i in range(45, 57)]

def get_selection(choices):
    """Returns the selected choice, or None. Choices should be a list of two-tuples of (name, choice).
    If length of choices is 1, will return the only choice."""
    if len(choices) < 2:
        if len(choices):
            return choices[0]
        else:
            return ''
    choices = choices[:10]  # sanity
    names = [o[0] for o in choices]
    results = [o[1] for o in choices]
    selectStr = " Which one were you looking for? (Type the number)\n"
    for i, r in enumerate(names):
        selectStr += f"[{i+1}] - {r}\n"
    try:
        index = int(input(selectStr)) - 1
    except ValueError:
        return ''
    return results[index]


def do_selection(result):
    if result is None:
        return ''
    strict = result[1]
    results = result[0]

    if strict:
        return results
    else:
        if len(results) == 1:
            return results[0]
        else:
            return get_selection([(r['name'], r) for r in results])


def do_race(ws, cell_index):
    race = None
    while not race:
        result = searchRace(input("What race? "))
        race = do_selection(result)

    ws.update_cell('T7', race['name'])

    for t in race.get('trait', []):
        name = t['name']
        value = '\n'.join(txt for txt in t['text'] if txt) if isinstance(t['text'], list) else t['text']
        cell = ws.cell(FEATURES_CELLS[cell_index])
        cell.value = name
        cell.note = value
        cell_index += 1

    return cell_index


def do_class_and_level(ws, cell_index):
    _class = None
    while not _class:
        result = searchClass(input("What class? "))
        _class = do_selection(result)

    ws.update_cell('T5', _class['name'])

    level = None
    while not level:
        level = input("What level? ")
        try:
            level = int(level)
            assert 0 < level < 21
        except (AssertionError, ValueError):
            level = None

    ws.update_cell('AL6', str(level))

    features = []
    for level in range(1, level):
        level_features = [f for f in _class['autolevel'] if f['_level'] == str(level)]
        for feature in level_features:
            for f in feature.get('feature', []):
                if not f.get('_optional') and not (
                            f['name'] in ("Starting Proficiencies", "Starting Equipment")):
                    features.append(f)
                elif f['name'] == "Starting Proficiencies":
                    starting_profs = '\n'.join(t for t in f['text'] if t)
                elif f['name'] == "Starting Equipment":
                    starting_items = '\n'.join(t for t in f['text'] if t)
            if not 'feature' in feature:
                pass

    for f in features:
        name = f['name']
        value = '\n'.join(txt for txt in f['text'] if txt) if isinstance(f['text'], list) else f['text']
        cell = ws.cell(FEATURES_CELLS[cell_index])
        cell.value = name
        cell.note = value
        cell_index += 1

    return cell_index


def main():
    gc = pygsheets.authorize(service_file='./avrae-0b82f09d7ab3.json')

    template = gc.open_by_key(TEMPLATE_SPREADSHEET_ID)  # open template
    new_sheet = gc.create("TESTNew CharacterTEST", parent_id=PARENT_FOLDER_ID)  # create new character sheet

    template.sheet1.copy_to(new_sheet.id)  # copy character sheet over
    new_sheet.del_worksheet(new_sheet.sheet1)  # delete default worksheet
    new_sheet.worksheet().title = "v1.3"  # pretty it a little

    feature_cell_index = 0

    feature_cell_index = do_race(new_sheet.worksheet(), feature_cell_index)
    feature_cell_index = do_class_and_level(new_sheet.worksheet(), feature_cell_index)
    email = input("Please enter your Google account email: ")
    new_sheet.share(email, role='writer')  # give control to user


if __name__ == '__main__':
    main()
