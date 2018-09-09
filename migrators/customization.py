import pymongo


async def migrate_aliases(rdb, mdb):
    num_aliases = 0
    num_users = 0

    aliases = rdb.jget("cmd_aliases")
    for user, useraliases in aliases.items():
        num_users += 1
        print(f"Migrating aliases for {user}...")
        for name, commands in useraliases.items():
            num_aliases += 1
            print(f"Migrating alias {name}...")
            data = {
                "owner": user,
                "name": name,
                "commands": commands
            }
            print("Inserting into aliases...")
            result = await mdb.aliases.insert_one(data)
            print(result.inserted_id)
        print()

    print("Creating compound index on owner|name...")
    await mdb.aliases.create_index([("owner", pymongo.ASCENDING),
                                    ("name", pymongo.ASCENDING)],
                                   unique=True)

    print(f"Done! Migrated {num_aliases} aliases for {num_users} users.\n\n")


async def migrate_servaliases(rdb, mdb):
    num_aliases = 0
    num_servers = 0

    aliases = rdb.jget("serv_aliases")
    for server, servaliases in aliases.items():
        num_servers += 1
        print(f"Migrating servaliases for {server}...")
        for name, commands in servaliases.items():
            num_aliases += 1
            print(f"Migrating servalias {name}...")
            data = {
                "server": server,
                "name": name,
                "commands": commands
            }
            print("Inserting into servaliases...")
            result = await mdb.servaliases.insert_one(data)
            print(result.inserted_id)
        print()

    print("Creating compound index on server|name...")
    await mdb.servaliases.create_index([("server", pymongo.ASCENDING),
                                        ("name", pymongo.ASCENDING)],
                                       unique=True)

    print(f"Done! Migrated {num_aliases} aliases for {num_servers} servers.\n\n")


async def migrate_snippets(rdb, mdb):
    num_snippets = 0
    num_users = 0

    snippets = rdb.jget("damage_snippets")
    for user, usersnippets in snippets.items():
        num_users += 1
        print(f"Migrating snippets for {user}...")
        for name, snippet in usersnippets.items():
            num_snippets += 1
            print(f"Migrating snippet {name}...")
            data = {
                "owner": user,
                "name": name,
                "snippet": snippet
            }
            print("Inserting into snippets...")
            result = await mdb.snippets.insert_one(data)
            print(result.inserted_id)
        print()

    print("Creating compound index on owner|name...")
    await mdb.snippets.create_index([("owner", pymongo.ASCENDING),
                                     ("name", pymongo.ASCENDING)],
                                    unique=True)

    print(f"Done! Migrated {num_snippets} snippets for {num_users} users.\n\n")


async def migrate_servsnippets(rdb, mdb):
    num_snippets = 0
    num_servers = 0

    snippets = rdb.jget("server_snippets", {})
    for server, servsnippets in snippets.items():
        num_servers += 1
        print(f"Migrating snippets for {server}...")
        for name, snippet in servsnippets.items():
            num_snippets += 1
            print(f"Migrating snippet {name}...")
            data = {
                "server": server,
                "name": name,
                "snippet": snippet
            }
            print("Inserting into servsnippets...")
            result = await mdb.servsnippets.insert_one(data)
            print(result.inserted_id)
        print()

    print("Creating compound index on server|name...")
    await mdb.servsnippets.create_index([("server", pymongo.ASCENDING),
                                         ("name", pymongo.ASCENDING)],
                                        unique=True)

    print(f"Done! Migrated {num_snippets} snippets for {num_servers} servers.\n\n")


async def migrate_uvars(rdb, mdb):
    num_vars = 0
    num_users = 0

    users = rdb._db.hkeys("user_vars")
    users = [u.decode() for u in users]
    for user in users:
        num_users += 1
        print(f"Migrating uvars for {user}...")
        uvars = rdb.jhget("user_vars", user)
        for name, value in uvars.items():
            num_vars += 1
            print(f"Migrating uvar {name}...")
            data = {
                "owner": user,
                "name": name,
                "value": value
            }
            print("Inserting into uvars...")
            result = await mdb.uvars.insert_one(data)
            print(result.inserted_id)
        print()

    print("Creating compound index on owner|name...")
    await mdb.uvars.create_index([("owner", pymongo.ASCENDING),
                                  ("name", pymongo.ASCENDING)],
                                 unique=True)

    print(f"Done! Migrated {num_vars} vars for {num_users} users.\n\n")


async def migrate_gvars(rdb, mdb):
    num_gvars = 0

    gvars = rdb.jget("global_vars", {})
    for key, gvar in gvars.items():
        num_gvars += 1
        print(f"Migrating gvar {key}...")

        print("Adding key key...")
        gvar['key'] = key

        print("Inserting into gvars...")
        result = await mdb.gvars.insert_one(gvar)
        print(result.inserted_id)
        print()

    print("Creating index on key...")
    await mdb.gvars.create_index("key",
                                 unique=True)

    print(f"Done! Migrated {num_gvars} gvars.\n\n")


async def run(rdb, mdb):
    await migrate_aliases(rdb, mdb)
    await migrate_servaliases(rdb, mdb)
    await migrate_snippets(rdb, mdb)
    await migrate_servsnippets(rdb, mdb)
    await migrate_uvars(rdb, mdb)
    await migrate_gvars(rdb, mdb)


if __name__ == '__main__':
    from utils.redisIO import RedisIO
    import credentials
    import motor.motor_asyncio
    import asyncio

    rdb = RedisIO(True, credentials.test_redis_url)  # production should run main script
    mdb = motor.motor_asyncio.AsyncIOMotorClient(credentials.test_mongo_url).avrae

    asyncio.get_event_loop().run_until_complete(run(rdb, mdb))
