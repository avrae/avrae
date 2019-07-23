import asyncio
import json
import os
import sys

sys.path.append('..')


import motor.motor_asyncio


import credentials


LOAD_FILES = {
    'conditions': [],
    'names': [],
    'rules': [],
    'srd-backgrounds': [],
    'srd-bestiary': [],
    'srd-classfeats': [],
    'srd-classes': [],
    'srd-feats': [],
    'srd-items': [],
    'srd-races': [],
    'srd-spells': [],

    'itemprops': {},
}


async def run(mdb):
    for basename, default in LOAD_FILES.items():
        data = default
        filepath = os.path.join('..', 'res', f'{basename}.json')
        try:
            with open(filepath, 'r')as f:
                data = json.load(f)
        except FileNotFoundError:
            print(f'File not found: {filepath}')

        print(f'Inserting {len(data)} items for {basename}...', end=' ', flush=True)
        result = await mdb.static_data.update_one(
            { 'key': basename },
            { '$set': { 'object': data } },
            upsert=True
        )
        print(result.upserted_id)

    print()
    print('Creating index on static_data...', end=' ', flush=True)
    await mdb.static_data.create_index("key", unique=True)
    print('done.')


if __name__ == '__main__':
    mdb = None
    if 'test' in sys.argv:
        mdb = motor.motor_asyncio.AsyncIOMotorClient(credentials.test_mongo_url)
    else:
        mdb = motor.motor_asyncio.AsyncIOMotorClient(os.getenv('MONGO_URL', "mongodb://localhost:27017"))

    mdb = motor.motor_asyncio.AsyncIOMotorClient(
        credentials.test_mongo_url if 'test' in sys.argv else "mongodb://localhost:27017").avrae

    asyncio.get_event_loop().run_until_complete(run(mdb))
