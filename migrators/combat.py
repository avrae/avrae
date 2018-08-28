import datetime


async def run(rdb, mdb):
    num_combats = 0

    combat_keys = rdb._db.keys("*.combat")
    for key in combat_keys:
        num_combats += 1
        key = key.decode()
        print(f"Migrating {key}...")

        rdb.set(f"{key}.bak", rdb.get(key))
        print("Backed up!")

        data = rdb.jget(key)

        print(f"Adding lastchanged key...")
        data['lastchanged'] = datetime.datetime.utcnow()

        print("Inserting into MongoDB...")
        result = await mdb.combats.insert_one(data)
        print(result.inserted_id)

    print("Creating index on channel...")
    await mdb.combats.create_index("channel", unique=True)

    print("Creating index on lastchanged with TTL 30 days (2592000 sec)...")
    await mdb.combats.create_index("lastchanged", expireAfterSeconds=2592000)

    print(f"Done! Migrated {num_combats} combats.")


if __name__ == '__main__':
    from utils.redisIO import RedisIO
    import credentials
    import motor.motor_asyncio
    import asyncio

    rdb = RedisIO(True, credentials.test_redis_url)  # production should run main script
    mdb = motor.motor_asyncio.AsyncIOMotorClient(credentials.test_mongo_url).avrae

    asyncio.get_event_loop().run_until_complete(run(rdb, mdb))
