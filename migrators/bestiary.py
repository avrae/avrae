import pymongo


async def run(rdb, mdb):
    num_bestiaries = 0
    num_users = 0

    bestiary_keys = rdb._db.keys("*.bestiaries")
    for key in bestiary_keys:
        print()
        num_users += 1
        key = key.decode()
        print(f"Migrating {key}...")

        rdb.set(f"{key}.bak", rdb.get(key))
        print("Backed up!")

        data = rdb.jget(key)

        for _id, bestiary in data.items():
            num_bestiaries += 1
            print(f"Found bestiary: {bestiary['name']} ({_id})")
            owner_id = key[:-11]

            print(f"Adding owner, id, active keys: {owner_id}, {_id}")
            bestiary['owner'] = owner_id
            bestiary['critterdb_id'] = _id
            bestiary['active'] = False

            print("Inserting into MongoDB...")
            result = await mdb.bestiaries.insert_one(bestiary)
            print(result.inserted_id)

    print("Creating compound index on owner|critterdb_id...")
    await mdb.bestiaries.create_index([("owner", pymongo.ASCENDING),
                                       ("critterdb_id", pymongo.ASCENDING)], unique=True)

    print(f"Done! Migrated {num_bestiaries} bestiaries for {num_users} users.")


if __name__ == '__main__':
    from utils.redisIO import RedisIO
    import credentials
    import motor.motor_asyncio
    import asyncio

    rdb = RedisIO(True, credentials.test_redis_url)  # production should run main script
    mdb = motor.motor_asyncio.AsyncIOMotorClient(credentials.test_mongo_url).avrae

    asyncio.get_event_loop().run_until_complete(run(rdb, mdb))
