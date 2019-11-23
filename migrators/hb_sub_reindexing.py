"""
Converts homebrew bestiary, pack, and tome subscriber indices:
removes "subscribers", "active", and "server_active" keys from objects and inserts into subscriber collection

Usage: python hb_sub_reindexing.py [bestiary] [tome] [pack] [test]
"""
import asyncio
import os
import sys

from pymongo import ASCENDING

sys.path.append('..')

import motor.motor_asyncio


async def migrate_bestiaries(mdb):
    objs = []
    async for bestiary in mdb.bestiaries.find():
        _id = bestiary['_id']

        def add_sub(sub_type, id_str, **additional_keys):
            try:
                obj = {"type": sub_type, "subscriber_id": int(id_str), "object_id": _id}
                if additional_keys:
                    obj.update(additional_keys)
                objs.append(obj)
            except (ValueError, TypeError):
                print(f"Cannot interpret {id_str} as an ID")

        for subscriber_id in bestiary.get("subscribers", []):
            add_sub("subscribe", subscriber_id)
        for active_id in bestiary.get("active", []):
            add_sub("active", active_id)
        for guild_doc in bestiary.get("server_active", []):
            # [{"subscriber_id": string, "guild_id": string}, ...]
            add_sub("server_active", guild_doc['guild_id'], provider_id=guild_doc['subscriber_id'])

    # insert
    print(f'Inserting {len(objs)} subscriptions...', end=' ', flush=True)
    result = await mdb.bestiary_subscriptions.insert_many(objs)
    print(len(result.inserted_ids))

    # create new indices
    # db.bestiary_subscriptions.createIndex({"type": 1});
    # db.bestiary_subscriptions.createIndex({"subscriber_id": 1});
    # db.bestiary_subscriptions.createIndex({"object_id": 1});
    # db.bestiary_subscriptions.createIndex({"provider_id": 1});
    print(f'Creating new indices...', end=' ', flush=True)
    await mdb.bestiary_subscriptions.create_index("type")
    await mdb.bestiary_subscriptions.create_index("subscriber_id")
    await mdb.bestiary_subscriptions.create_index("object_id")
    await mdb.bestiary_subscriptions.create_index("provider_id")
    print("OK")

    # delete old indices
    print(f'Deleting old indices...', end=' ', flush=True)
    # db.bestiaries.createIndex({"subscribers": 1});
    # db.bestiaries.createIndex({"active": 1});
    # db.bestiaries.createIndex({"server_active.guild_id": 1});
    for index in ("subscribers_1", "active_1", "server_active.guild_id_1"):
        try:
            await mdb.bestiaries.drop_index(index)
        except:
            print(f"Failed to remove {index}!")
    print("OK")


async def migrate_tomes(mdb):
    await _migrate(mdb.tomes, mdb.tome_subscriptions)


async def migrate_packs(mdb):
    await _migrate(mdb.packs, mdb.pack_subscriptions)


async def _migrate(data_coll, sub_coll):
    objs = []
    async for obj in data_coll.find():
        _id = obj['_id']

        def add_sub(sub_type, id_str):
            try:
                obj = {"type": sub_type, "subscriber_id": int(id_str), "object_id": _id}
                objs.append(obj)
            except (ValueError, TypeError):
                print(f"Cannot interpret {id_str} as an ID")

        for subscriber_doc in obj.get("subscribers", []):
            add_sub("subscribe", subscriber_doc['id'])
        for editor_doc in obj.get("editors", []):
            add_sub("editor", editor_doc['id'])
        for active_id in obj.get("active", []):
            add_sub("active", active_id)
        for guild_id in obj.get("server_active", []):
            add_sub("server_active", guild_id)

        if isinstance(obj['owner'], dict):
            owner_id = int(obj['owner']['id'])
            await data_coll.update_one({"_id": _id}, {"$set": {"owner": owner_id}})

    # insert
    print(f'Inserting {len(objs)} subscriptions...', end=' ', flush=True)
    result = await sub_coll.insert_many(objs)
    print(len(result.inserted_ids))

    # create new indices
    # db.tome_subscriptions.createIndex({"type": 1, "subscriber_id": 1});
    # db.tome_subscriptions.createIndex({"object_id": 1});
    print(f'Creating new indices...', end=' ', flush=True)
    await sub_coll.create_index({"type": ASCENDING, "subscriber_id": ASCENDING})
    await sub_coll.create_index("object_id")
    print("OK")

    # delete old indices
    print(f'Deleting old indices...', end=' ', flush=True)
    # db.tomes.createIndex({"editors.id": 1});
    # db.tomes.createIndex({"subscribers.id": 1});
    # db.tomes.createIndex({"active": 1});
    # db.tomes.createIndex({"server_active": 1});
    for index in ("editors.id_1", "subscribers.id_1", "active_1", "server_active_1"):
        try:
            await data_coll.drop_index(index)
        except:
            print(f"Failed to remove {index}!")
    print("OK")


async def run():
    mdb = None
    if 'test' in sys.argv:
        import credentials

        mdb = motor.motor_asyncio.AsyncIOMotorClient(credentials.test_mongo_url).avrae
    else:
        mclient = motor.motor_asyncio.AsyncIOMotorClient(os.getenv('MONGO_URL', "mongodb://localhost:27017"))
        mdb = mclient[os.getenv('MONGO_DB', "avrae")]

    if 'bestiary' in sys.argv:
        input(f"Reindexing {mdb.name} bestiaries. Press enter to continue.")
        await migrate_bestiaries(mdb)

    if 'tome' in sys.argv:
        input(f"Reindexing {mdb.name} tomes. Press enter to continue.")
        await migrate_tomes(mdb)

    if 'pack' in sys.argv:
        input(f"Reindexing {mdb.name} packs. Press enter to continue.")
        await migrate_packs(mdb)


if __name__ == '__main__':
    asyncio.run(run())
