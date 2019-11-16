import json
import re
import sys
import time

from cogs5e.models.monster import Monster
from cogs5e.models.sheet.base import BaseStats, Saves, Skills
from cogs5e.models.sheet.spellcasting import Spellbook, SpellbookSpell


def migrate_monster(old_monster):
    def spaced_to_camel(spaced):
        return re.sub(r"\s+(\w)", lambda m: m.group(1).upper(), spaced.lower())

    for old_key in ('raw_saves', 'raw_skills'):
        if old_key in old_monster:
            del old_monster[old_key]

    if 'spellcasting' in old_monster and old_monster['spellcasting']:
        old_spellcasting = old_monster.pop('spellcasting')
        old_monster['spellbook'] = Spellbook({}, {}, [SpellbookSpell(s) for s in old_spellcasting['spells']],
                                             old_spellcasting['dc'], old_spellcasting['attackBonus'],
                                             old_spellcasting['casterLevel']).to_dict()
    else:
        old_monster['spellbook'] = Spellbook({}, {}, []).to_dict()

    base_stats = BaseStats(
        0, old_monster.pop('strength'), old_monster.pop('dexterity'), old_monster.pop('constitution'),
        old_monster.pop('intelligence'), old_monster.pop('wisdom'), old_monster.pop('charisma')
    )
    old_monster['ability_scores'] = base_stats.to_dict()

    old_saves = old_monster.pop('saves')
    saves = Saves.default(base_stats)
    save_updates = {}
    for save, value in old_saves.items():
        if value != saves[save]:
            save_updates[save] = value
    saves.update(save_updates)
    old_monster['saves'] = saves.to_dict()

    old_skills = old_monster.pop('skills')
    skills = Skills.default(base_stats)
    skill_updates = {}
    for skill, value in old_skills.items():
        name = spaced_to_camel(skill)
        if value != skills[name]:
            skill_updates[name] = value
    skills.update(skill_updates)
    old_monster['skills'] = skills.to_dict()

    new_monster = Monster.from_bestiary(old_monster)
    return new_monster


def migrate(bestiary):
    new_monsters = []
    for old_monster in bestiary['monsters']:
        new_monsters.append(migrate_monster(old_monster).to_dict())
    bestiary['monsters'] = new_monsters
    return bestiary


def local_test(fp):
    with open(fp) as f:
        bestiaries = json.load(f)
    num_monsters = sum(len(b['monsters']) for b in bestiaries)
    print(f"Migrating {len(bestiaries)} bestiaries ({num_monsters} monsters)...")

    new_bestiaries = []
    for b in bestiaries:
        print(f"migrating {b['name']}")
        new_bestiaries.append(migrate(b))
    out = fp.split('/')[-1]
    with open(f"temp/new-{out}", 'w') as f:
        json.dump(new_bestiaries, f, indent=2)
    print(f"Done migrating {len(new_bestiaries)} bestiaries.")


async def from_db(mdb):
    import pymongo
    from bson import ObjectId

    coll_names = await mdb.list_collection_names()
    if "old_bestiaries" not in coll_names:
        print("Renaming bestiaries to old_bestiaries...")
        await mdb.bestiaries.rename("old_bestiaries")
    else:
        print("Dropping bestiaries_bak and making backup...")
        if "bestiaries_bak" in coll_names:
            await mdb.bestiaries_bak.drop()
        await mdb.bestiaries.rename("bestiaries_bak")

    num_old_bestiaries = await mdb.old_bestiaries.count_documents({})
    print(f"Migrating {num_old_bestiaries} bestiaries...")

    async for old_bestiary in mdb.old_bestiaries.find({}):
        new_char = migrate(old_bestiary)
        new_char['_id'] = ObjectId(old_bestiary['_id'])
        await mdb.bestiaries.insert_one(new_char)

    print("Creating compound index on owner|critterdb_id...")
    await mdb.bestiaries.create_index([("owner", pymongo.ASCENDING),
                                       ("critterdb_id", pymongo.ASCENDING)], unique=True)

    num_bestiaries = await mdb.old_bestiaries.count_documents({})
    print(f"Done migrating {num_bestiaries}/{num_old_bestiaries} bestiaries.")
    if num_bestiaries == num_old_bestiaries:
        print("It's probably safe to drop the collections old_bestiaries and bestiaries_bak now.")


if __name__ == '__main__':
    import asyncio
    import motor.motor_asyncio
    import credentials

    start = time.time()

    if 'mdb' not in sys.argv:
        local_test("temp/bestiaries.json")
    else:
        input("Running full MDB migration. Press enter to continue.")
        mdb = motor.motor_asyncio.AsyncIOMotorClient(credentials.test_mongo_url
                                                     if 'test' in sys.argv else
                                                     "mongodb://localhost:27017").avrae

        asyncio.get_event_loop().run_until_complete(from_db(mdb))

    end = time.time()
    print(f"Done! Took {end - start} seconds.")
