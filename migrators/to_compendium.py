import copy
import sys
import time

PACK_CARRYOVER = (
    "name", "owner", "editors", "subscribers", "public", "active", "server_active", "desc", "image", "_id", "items"
)
TOME_CARRYOVER = (
    "name", "owner", "editors", "subscribers", "public", "active", "server_active", "desc", "image", "_id", "spells"
)
COMMENT = {
    "author": {"id": "261302296103747584", "username": "Avrae#4211",
               "avatarUrl": "https://avrae.io/assets/img/AvraeSquare.jpg"},
    "text": "This compendium was automatically migrated.",
    "timestamp": time.time()
}
DEFAULT_COMPENDIUM = {
    "name": "Unknown Compendium",
    "owner": None,
    "editors": [],
    "subscribers": [],
    "public": False,
    "active": [],
    "server_active": [],
    "desc": "An unknown compendium",
    "image": "",
    "created": time.time(),
    "lastEdit": time.time(),

    "backgrounds": [],
    "characterClasses": [],
    "feats": [],
    "items": [],
    "monsters": [],
    "races": [],
    "spells": [],

    "comments": [COMMENT],
    "stargazers": []
}


async def run(mdb):
    num_packs = 0
    num_tomes = 0

    async for pack in mdb.packs.find({}):
        print()
        print(f"Migrating pack {pack['_id']}...")
        num_packs += 1
        for key in pack.copy():
            if key not in PACK_CARRYOVER:
                print(f"Found invalid key: {key}, removing")
                del pack[key]
        comp = copy.deepcopy(DEFAULT_COMPENDIUM)
        comp.update(pack)
        print("Inserting into compendiums...")
        result = await mdb.compendiums.insert_one(comp)
        print(result.inserted_id)

    async for tome in mdb.tomes.find({}):
        print()
        print(f"Migrating tome {tome['_id']}...")
        num_tomes += 1
        for key in tome.copy():
            if key not in TOME_CARRYOVER:
                print(f"Found invalid key: {key}, removing")
                del tome[key]
        comp = copy.deepcopy(DEFAULT_COMPENDIUM)
        comp.update(tome)
        print("Inserting into compendiums...")
        result = await mdb.compendiums.insert_one(comp)
        print(result.inserted_id)

    print()
    print("Creating index on owner.id...")
    await mdb.bestiaries.create_index("owner.id")
    print("Creating index on editors.id...")
    await mdb.bestiaries.create_index("editors.id")
    print("Creating index on subscribers.id...")
    await mdb.bestiaries.create_index("subscribers.id")
    print("Creating index on stargazers.id...")
    await mdb.bestiaries.create_index("stargazers.id")
    print("Creating index on active...")
    await mdb.bestiaries.create_index("active")
    print("Creating index on server_active...")
    await mdb.bestiaries.create_index("server_active")

    print(f"Done! Migrated {num_packs} packs and {num_tomes} tomes.")


if __name__ == '__main__':
    import credentials
    import motor.motor_asyncio
    import asyncio

    mdb = motor.motor_asyncio.AsyncIOMotorClient(
        credentials.test_mongo_url if 'test' in sys.argv else "mongodb://localhost:27017").avrae

    asyncio.get_event_loop().run_until_complete(run(mdb))
