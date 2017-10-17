import pygsheets

PARENT_FOLDER_ID = '0B7G4hVfa4Trwak1vUWF2U19KaDA'
TEMPLATE_SPREADSHEET_ID = '1etrBJ0qCDXACovYHUM4XvjE0erndThwRLcUQzX6ts8w'
TEMPLATE_WORKSHEET_ID = '1750226729'


def main():
    gc = pygsheets.authorize(service_file='../avrae-0b82f09d7ab3.json')

    template = gc.open_by_key(TEMPLATE_SPREADSHEET_ID) # open template
    new_sheet = gc.create("TESTNew CharacterTEST", parent_id=PARENT_FOLDER_ID) # create new character sheet

    template.sheet1.copy_to(new_sheet.id) # copy character sheet over
    new_sheet.del_worksheet(new_sheet.sheet1) # delete default worksheet
    new_sheet.worksheet().title = "v1.3" # pretty it a little

    email = input("Please enter your Google account email: ")
    new_sheet.share(email, role='writer') # give control to user


if __name__ == '__main__':
    main()