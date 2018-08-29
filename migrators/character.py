import pymongo


async def run(rdb, mdb):
    num_characters = 0
    num_users = 0

    character_keys = rdb._db.keys("*.characters")
    for key in character_keys:
        num_users += 1
        key = key.decode()
        print(f"Migrating {key}...")

        rdb.set(f"{key}.bak", rdb.get(key))
        print("Backed up!")

        data = rdb.jget(key)

        for _id, character in data.items():
            num_characters += 1
            print(f"Found character: {character['stats']['name']} ({_id})")
            owner_id = key[:-11]

            print(f"Adding owner, upstream, active keys: {owner_id}, {_id}")
            character['owner'] = owner_id
            character['upstream'] = _id
            character['active'] = False

            print("Checking for invalid cvar names...")
            for cvar in character.get('cvars', {}).copy():
                if any(c in cvar for c in '-/()[]\\.^$*+?|{}'):
                    print(f"Deleting cvar {cvar}...")
                    del character['cvars'][cvar]
            for cvar in character.get('stat_cvars', {}).copy():
                if any(c in cvar for c in '-/()[]\\.^$*+?|{}'):
                    print(f"Deleting stat cvar {cvar}...")
                    del character['stat_cvars'][cvar]
            for key in character.get('levels', {}).copy():
                if any(c in key for c in '-/()[]\\.^$*+?|{}'):
                    print(f"Deleting level {key}...")
                    del character['levels'][key]

            print("Inserting into MongoDB...")
            result = await mdb.characters.insert_one(character)
            print(result.inserted_id)
            print()

    print("Creating compound index on owner|upstream...")
    await mdb.characters.create_index([("owner", pymongo.ASCENDING),
                                       ("upstream", pymongo.ASCENDING)],
                                      unique=True)

    active = rdb.jget("active_characters")
    for user, charId in active.items():
        print(f"Setting character {charId} as active...")
        await mdb.characters.update_one({"owner": user, "upstream": charId}, {"$set": {"active": True}})

    print(f"Done! Migrated {num_characters} characters for {num_users} users.")


if __name__ == '__main__':
    from utils.redisIO import RedisIO
    import credentials
    import motor.motor_asyncio
    import asyncio

    rdb = RedisIO(True, credentials.test_redis_url)  # production should run main script
    mdb = motor.motor_asyncio.AsyncIOMotorClient(credentials.test_mongo_url).avrae

    asyncio.get_event_loop().run_until_complete(run(rdb, mdb))
