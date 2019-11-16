async def run(rdb, mdb):
    num_servers = 0

    old_settings = rdb.jget("lookup_settings", {})
    for guild_id, settings in old_settings.items():
        num_servers += 1
        print(f"Processing lookup settings for {guild_id}...")
        settings['server'] = guild_id

        print("Inserting into MongoDB...")
        result = await mdb.lookupsettings.insert_one(settings)
        print(result.inserted_id)
        print()

    print("Creating index on server...")
    await mdb.lookupsettings.create_index("server", unique=True)

    print(f"Done! Migrated settings for {num_servers} servers.")



if __name__ == '__main__':
    from utils.redisIO import RedisIO
    import credentials
    import motor.motor_asyncio
    import asyncio

    rdb = RedisIO(True, credentials.test_redis_url)  # production should run main script
    mdb = motor.motor_asyncio.AsyncIOMotorClient(credentials.test_mongo_url).avrae

    asyncio.get_event_loop().run_until_complete(run(rdb, mdb))
