"""
Converts homebrew bestiary, pack, and tome subscriber indices:
removes "subscribers", "active", and "server_active" keys from objects and inserts into subscriber collection

Usage: python hb_sub_reindexing.py [bestiary] [tome] [pack] [test]
"""
import asyncio
import os
import sys

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
    for index in ("subscribers", "active", "server_active.guild_id"):
        try:
            await mdb.bestiaries.drop_index(index)
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


if __name__ == '__main__':
    asyncio.run(run())
