import hashlib
import json
import sys
import time

from cogs5e.models.homebrew.bestiary import Bestiary
from cogs5e.models.monster import Monster


def migrate(bestiary):
    sha256 = hashlib.sha256()
    hash_str = json.dumps(bestiary['monsters']).encode() \
               + bestiary['name'].encode() \
               + str(bestiary.get('desc')).encode()
    sha256.update(hash_str)

    active = [bestiary['owner']] if bestiary.get('active') else []
    server_active = []
    for serv_sub in bestiary.get('server_active', []):
        server_active.append({"subscriber_id": bestiary['owner'], "guild_id": serv_sub})
    monsters = [Monster.from_bestiary(m) for m in bestiary['monsters']]
    new_bestiary = Bestiary(None, sha256.hexdigest(), bestiary['critterdb_id'], [bestiary['owner']], active,
                            server_active, bestiary['name'], monsters, bestiary.get('desc'))
    return new_bestiary


def to_dict(bestiary):
    monsters = [m.to_dict() for m in bestiary._monsters]
    return {
        "sha256": bestiary.sha256, "upstream": bestiary.upstream, "subscribers": bestiary.subscribers,
        "active": bestiary.active, "server_active": bestiary.server_active, "name": bestiary.name,
        "desc": bestiary.desc, "monsters": monsters
    }


def local_test(fp):
    f = open(fp)
    print(f"Migrating bestiaries from {fp}...")

    new_bestiaries = {}
    num_monsters = 0
    num_bestiaries = 0
    for line in f:
        bestiary = json.loads(line)
        num_monsters += len(bestiary['monsters'])
        num_bestiaries += 1
        print(f"\nmigrating {bestiary['name']}")
        new_bestiary = migrate(bestiary)
        key = f"{new_bestiary.upstream} {new_bestiary.sha256}"
        if key in new_bestiaries:
            print("exists - merging...")
            # merge
            existing = new_bestiaries[key]
            existing.subscribers.extend(new_bestiary.subscribers)
            existing.active.extend(new_bestiary.active)
            existing.server_active.extend(new_bestiary.server_active)
        else:
            new_bestiaries[key] = new_bestiary
    f.close()

    new_bestiaries = [to_dict(b) for b in new_bestiaries.values()]
    out = fp.split('/')[-1]
    with open(f"temp/new-{out}", 'w') as f:
        json.dump(new_bestiaries, f, indent=2)
    print(f"Done migrating {len(new_bestiaries)} bestiaries (down from {num_bestiaries}).")


async def from_db(mdb):
    import pymongo

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

    # db.bestiaries.createIndex({"upstream": 1, "sha256": 1}, {"unique": true});
    print("Creating compound index on upstream|sha256...")
    await mdb.bestiaries.create_index([("upstream", pymongo.ASCENDING),
                                       ("sha256", pymongo.ASCENDING)], unique=True)

    # db.bestiaries.createIndex({"subscribers": 1});
    print("Creating index on subscribers...")
    await mdb.bestiaries.create_index("subscribers")

    # db.bestiaries.createIndex({"active": 1});
    print("Creating index on active...")
    await mdb.bestiaries.create_index("active")

    # db.bestiaries.createIndex({"server_active.guild_id": 1});
    print("Creating index on server_active.guild_id...")
    await mdb.bestiaries.create_index("server_active.guild_id")

    new_bestiaries = {}
    async for old_bestiary in mdb.old_bestiaries.find({}):
        print(f"\nmigrating {old_bestiary['name']}")
        new_bestiary = migrate(old_bestiary)
        key = f"{new_bestiary.upstream} {new_bestiary.sha256}"
        if key in new_bestiaries:
            print("exists - merging...")
            # merge
            existing = new_bestiaries[key]
            existing.subscribers.extend(new_bestiary.subscribers)
            existing.active.extend(new_bestiary.active)
            existing.server_active.extend(new_bestiary.server_active)
        else:
            new_bestiaries[key] = new_bestiary

    for new_b in new_bestiaries.values():
        await mdb.bestiaries.insert_one(to_dict(new_b))

    num_bestiaries = await mdb.bestiaries.count_documents({})
    print(f"Done migrating! Collapsed {num_old_bestiaries} into {num_bestiaries} bestiaries.")
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
