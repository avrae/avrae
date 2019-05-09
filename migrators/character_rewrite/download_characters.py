import sys

from bson import json_util


async def run(mdb):
    out = []
    async for char in mdb.characters.find({}):
        out.append(char)

    with open("temp/collection_char.json", 'w') as f:
        f.write(json_util.dumps(out))


if __name__ == '__main__':
    import credentials
    import motor.motor_asyncio
    import asyncio

    mdb = motor.motor_asyncio.AsyncIOMotorClient(
        credentials.test_mongo_url if 'test' in sys.argv else "mongodb://localhost:27017").avrae

    asyncio.get_event_loop().run_until_complete(run(mdb))
