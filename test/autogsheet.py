import pygsheets

from cogs5e.funcs.lookupFuncs import *

PARENT_FOLDER_ID = '0B7G4hVfa4Trwak1vUWF2U19KaDA'
TEMPLATE_SPREADSHEET_ID = '1etrBJ0qCDXACovYHUM4XvjE0erndThwRLcUQzX6ts8w'
TEMPLATE_WORKSHEET_ID = '1750226729'


def get_selection(choices):
    """Returns the selected choice, or None. Choices should be a list of two-tuples of (name, choice).
    If length of choices is 1, will return the only choice."""
    if len(choices) < 2:
        if len(choices):
            return choices[0]
        else:
            return ''
    choices = choices[:10] # sanity
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


def main():
    gc = pygsheets.authorize(service_file='./avrae-0b82f09d7ab3.json')

    template = gc.open_by_key(TEMPLATE_SPREADSHEET_ID)  # open template
    new_sheet = gc.create("TESTNew CharacterTEST", parent_id=PARENT_FOLDER_ID)  # create new character sheet

    template.sheet1.copy_to(new_sheet.id)  # copy character sheet over
    new_sheet.del_worksheet(new_sheet.sheet1)  # delete default worksheet
    new_sheet.worksheet().title = "v1.3"  # pretty it a little

    race = None
    while not race:
        result = searchRace(input("What race? "))
        race = do_selection(result)

    _class = None
    while not _class:
        result = searchClass(input("What class? "))
        _class = do_selection(result)


    email = input("Please enter your Google account email: ")
    new_sheet.share(email, role='writer')  # give control to user


if __name__ == '__main__':
    main()
