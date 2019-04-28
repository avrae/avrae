import json

from cogs5e.models.character import Character, CustomCounter
from cogs5e.models.sheet import SpellbookSpell
from cogs5e.models.sheet.base import Skill
from utils.constants import SAVE_NAMES, SKILL_NAMES


def migrate(character):
    name = character['stats']['name']
    sheet_type = character['type']
    import_version = character['version']
    print(f"Migrating {name} - {sheet_type} v{import_version}")

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
        "resist": character['resist'], "immune": character['immune'], "vuln": character['vuln']
    }
    ac = character['armor']
    max_hp = character['hp']
    hp = character['consumables']['hp']['value']
    temp_hp = character['consumables'].get('temphp', {}).get('value', 0)

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
            spl = SpellbookSpell(old_spell, False)
        override_spells.append(spl.to_dict())
    overrides = {
        "desc": character.get('overrides', {}).get('desc'), "image": character.get('overrides', {}).get('image'),
        "attacks": override_attacks, "spells": override_spells
    }

    # other things
    consumables = []
    for cname, cons in character['consumables'].get('custom', {}).items():
        value = cons['value']
        minv = cons.get('min')
        maxv = cons.get('max')
        reset = cons.get('reset')
        display_type = cons.get('type')
        live_id = cons.get('live')
        counter = CustomCounter(None, cname, value, minv, maxv, reset, display_type, live_id)
        consumables.append(counter.to_dict())

    death_saves = {
        "successes": character['consumables']['deathsaves']['success']['value'],
        "fails": character['consumables']['deathsaves']['fail']['value']
    }

    # spellcasting
    slots = {}
    max_slots = {}
    for l in range(1, 10):
        slots[str(l)] = character['consumables']['spellslots'][str(l)]['value']
        max_slots[str(l)] = character['spellbook']['spellslots'][str(l)]
    spells = []
    for old_spell in character['spellbook']['spells']:
        if isinstance(old_spell, dict):
            spl = SpellbookSpell(old_spell['name'], old_spell['strict'])
        else:
            spl = SpellbookSpell(old_spell, False)
        spells.append(spl.to_dict())
    spellbook = {
        "slots": slots, "max_slots": max_slots, "spells": spells,
        "dc": character['spellbook']['dc'], "sab": character['spellbook']['attackBonus'],
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

    new_characters = []
    for c in characters:
        new_characters.append(migrate(c).to_dict())
    out = fp.split('/')[-1]
    with open(f"temp/new-{out}", 'w') as f:
        json.dump(new_characters, f)


def from_db(mdb):
    pass


if __name__ == '__main__':
    local_test("temp/collection_char.json")
