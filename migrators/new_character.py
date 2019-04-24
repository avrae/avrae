import json

from cogs5e.models.character import Character


def migrate(character):
    name = character['stats']['name']
    sheet_type = character['type']
    import_version = character['version']
    print(f"Migrating {name} - {sheet_type} {import_version}")

    owner = character['owner']
    upstream = character['upstream']
    active = character['active']

    description = character['stats']['description']
    image = character['stats']['image']

    stats = {
        "prof_bonus": character['stats']['proficiencyBonus'], "strength": character['stats']['strength'],
        "dexterity": character['stats']['dexterity'], "constitution": character['stats']['constitution'],
        "intelligence": character['stats']['intelligence'], "wisdom": character['stats']['wisdom'],
        "charisma": character['stats']['charisma']
    }

    # classes
    classes = {}
    for c, l in character['levels'].items():
        if c.endswith("Level"):
            classes[c[:-5]] = l
    levels = {
        "total_level": character['levels']['level'], "classes": classes
    }

    # attacks
    attacks = []
    for a in character['attacks']:
        try:
            bonus = int(a['attackBonus'])
            bonus_calc = None
        except ValueError:
            bonus = None
            bonus_calc = a['attackBonus']
        atk = {
            "name": a['name'], "bonus": bonus, "damage": a['damage'], "details": a['details'],
            "bonus_calc": bonus_calc
        }
        attacks.append(atk)

    # skills and saves
    skills = {}
    saves = {}

    # combat
    resistances = {
        "resist": character['resist'], "immune": character['immune'], "vuln": character['vuln']
    }
    ac = character['armor']
    max_hp = character['hp']
    hp = character['consumables']['hp']['value']
    temp_hp = character['consumables']['temphp']['value']

    cvars = character.get('cvars', {})

    options = {"options": character['settings']}
    overrides = {}
    consumables = []
    death_saves = {}
    spellbook = {}

    live = 'dicecloud' if character['live'] else None
    race = character['race']
    background = character['background']

    char = Character(owner, upstream, active, sheet_type, import_version,
                     name, description, image, stats, levels, attacks, skills,
                     resistances, saves, ac, max_hp, hp, temp_hp, cvars,
                     options, overrides, consumables, death_saves, spellbook, live,
                     race, background)
    return char


def local_test(fp):
    with open(fp) as f:
        characters = json.load(f)

    new_characters = []
    for c in characters:
        new_characters.append(migrate(c).to_dict())

    with open(f"new-{fp}", 'w') as f:
        json.dump(new_characters, f)


def from_db(mdb):
    pass


if __name__ == '__main__':
    local_test("temp/collection_char.json")
