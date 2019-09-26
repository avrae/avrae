import json
import sys
import time

from cogs5e.models.character import Character, CustomCounter
from cogs5e.models.sheet.spellcasting import SpellbookSpell
from cogs5e.models.sheet.base import Skill
from utils.constants import SAVE_NAMES, SKILL_NAMES


def migrate(character):
    name = character['stats']['name']
    sheet_type = character.get('type')
    import_version = character.get('version')
    print(f"Migrating {name} - {sheet_type} v{import_version}")

    owner = character['owner']
    upstream = character['upstream']
    active = character['active']

    description = character['stats'].get('description', "No description")
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
    for cls, lvl in list(classes.items())[:]:
        if any(inv in cls for inv in ".$"):
            classes.pop(cls)
    levels = {
        "total_level": character['levels']['level'], "classes": classes
    }

    # attacks
    attacks = []
    for a in character['attacks']:
        try:
            bonus = int(a['attackBonus'])
            bonus_calc = None
        except (ValueError, TypeError):
            bonus = None
            bonus_calc = a['attackBonus']
        atk = {
            "name": a['name'], "bonus": bonus, "damage": a['damage'], "details": a.get('details'),
            "bonus_calc": bonus_calc
        }
        attacks.append(atk)

    # skills and saves
    skills = {}
    for skill_name in SKILL_NAMES:
        value = character['skills'][skill_name]
        skefct = character.get('skill_effects', {}).get(skill_name)
        adv = True if skefct == 'adv' else False if skefct == 'dis' else None
        skl = Skill(value, 0, 0, adv)
        skills[skill_name] = skl.to_dict()

    saves = {}
    for save_name in SAVE_NAMES:
        value = character['saves'][save_name]
        skefct = character.get('skill_effects', {}).get(save_name)
        adv = True if skefct == 'adv' else False if skefct == 'dis' else None
        skl = Skill(value, 0, 0, adv)
        saves[save_name] = skl.to_dict()

    # combat
    resistances = {
        "resist": character.get('resist', []), "immune": character.get('immune', []), "vuln": character.get('vuln', [])
    }
    ac = character.get('armor', 10)
    max_hp = character.get('hp', 4)  # you get 4 hp if your character is that old
    hp = character.get('consumables', {}).get('hp', {}).get('value', max_hp)
    temp_hp = character.get('consumables', {}).get('temphp', {}).get('value', 0)

    cvars = character.get('cvars', {})
    options = {"options": character.get('settings', {})}

    # overrides
    override_attacks = []
    for a in character.get('overrides', {}).get('attacks', []):
        try:
            bonus = int(a['attackBonus'])
            bonus_calc = None
        except (ValueError, TypeError):
            bonus = None
            bonus_calc = a['attackBonus']
        atk = {
            "name": a['name'], "bonus": bonus, "damage": a['damage'], "details": a['details'],
            "bonus_calc": bonus_calc
        }
        override_attacks.append(atk)
    override_spells = []
    for old_spell in character.get('overrides', {}).get('spells', []):
        if isinstance(old_spell, dict):
            spl = SpellbookSpell(old_spell['name'], old_spell['strict'])
        else:
            spl = SpellbookSpell(old_spell, True)
        override_spells.append(spl.to_dict())
    overrides = {
        "desc": character.get('overrides', {}).get('desc'), "image": character.get('overrides', {}).get('image'),
        "attacks": override_attacks, "spells": override_spells
    }

    # other things
    consumables = []
    for cname, cons in character.get('consumables', {}).get('custom', {}).items():
        value = cons['value']
        minv = cons.get('min')
        maxv = cons.get('max')
        reset = cons.get('reset')
        display_type = cons.get('type')
        live_id = cons.get('live')
        counter = CustomCounter(None, cname, value, minv, maxv, reset, display_type, live_id)
        consumables.append(counter.to_dict())

    death_saves = {
        "successes": character.get('consumables', {}).get('deathsaves', {}).get('success', {}).get('value', 0),
        "fails": character.get('consumables', {}).get('deathsaves', {}).get('fail', {}).get('value', 0)
    }

    # spellcasting
    slots = {}
    max_slots = {}
    for l in range(1, 10):
        slots[str(l)] = character.get('consumables', {}).get('spellslots', {}).get(str(l), {}).get('value', 0)
        max_slots[str(l)] = character.get('spellbook', {}).get('spellslots', {}).get(str(l), 0)
    spells = []
    for old_spell in character.get('spellbook', {}).get('spells', []):
        if isinstance(old_spell, dict):
            spl = SpellbookSpell(old_spell['name'], old_spell['strict'])
        else:
            spl = SpellbookSpell(old_spell, True)
        spells.append(spl.to_dict())
    spellbook = {
        "slots": slots, "max_slots": max_slots, "spells": spells,
        "dc": character.get('spellbook', {}).get('dc'), "sab": character.get('spellbook', {}).get('attackBonus'),
        "caster_level": character['levels']['level']
    }

    live = 'dicecloud' if character.get('live') else None
    race = character.get('race')
    background = character.get('background')

    char = Character(owner, upstream, active, sheet_type, import_version,
                     name, description, image, stats, levels, attacks, skills,
                     resistances, saves, ac, max_hp, hp, temp_hp, cvars,
                     options, overrides, consumables, death_saves, spellbook, live,
                     race, background)
    return char


def local_test(fp):
    with open(fp) as f:
        characters = json.load(f)
    print(f"Migrating {len(characters)} characters...")

    new_characters = []
    for c in characters:
        new_characters.append(migrate(c).to_dict())
    out = fp.split('/')[-1]
    with open(f"temp/new-{out}", 'w') as f:
        json.dump(new_characters, f, indent=2)
    print(f"Done migrating {len(new_characters)} characters.")


async def from_db(mdb):
    import pymongo
    from bson import ObjectId

    coll_names = await mdb.list_collection_names()
    if "old_characters" not in coll_names:
        print("Renaming characters to old_characters...")
        await mdb.characters.rename("old_characters")
    else:
        print("Dropping characters_bak and making backup...")
        if "characters_bak" in coll_names:
            await mdb.characters_bak.drop()
        await mdb.characters.rename("characters_bak")

    num_old_chars = await mdb.old_characters.count_documents({})
    print(f"Migrating {num_old_chars} characters...")

    async for old_char in mdb.old_characters.find({}):
        new_char = migrate(old_char).to_dict()
        new_char['_id'] = ObjectId(old_char['_id'])
        try:
            await mdb.characters.insert_one(new_char)
        except:
            pass

    print("Creating compound index on owner|upstream...")
    await mdb.characters.create_index([("owner", pymongo.ASCENDING),
                                       ("upstream", pymongo.ASCENDING)],
                                      unique=True)

    num_chars = await mdb.characters.count_documents({})
    print(f"Done migrating {num_chars}/{num_old_chars} characters.")
    if num_chars == num_old_chars:
        print("It's probably safe to drop the collections old_characters and characters_bak now.")

if __name__ == '__main__':
    import asyncio
    import motor.motor_asyncio
    import credentials

    start = time.time()

    if 'mdb' not in sys.argv:
        local_test("temp/characters.json")
    else:
        input("Running full MDB migration. Press enter to continue.")
        mdb = motor.motor_asyncio.AsyncIOMotorClient(credentials.test_mongo_url
                                                     if 'test' in sys.argv else
                                                     "mongodb://localhost:27017").avrae

        asyncio.get_event_loop().run_until_complete(from_db(mdb))

    end = time.time()
    print(f"Done! Took {end - start} seconds.")
