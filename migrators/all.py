import asyncio

import motor.motor_asyncio

from migrators import bestiary, character, combat, customization, lookupsettings
from utils.redisIO import RedisIO


async def run(rdb, mdb):
    await bestiary.run(rdb, mdb)
    await character.run(rdb, mdb)
    await combat.run(rdb, mdb)
    await customization.run(rdb, mdb)
    await lookupsettings.run(rdb, mdb)


if __name__ == '__main__':
    rdb = RedisIO()
    mdb = motor.motor_asyncio.AsyncIOMotorClient("mongodb://localhost:27017").avrae

    asyncio.get_event_loop().run_until_complete(run(rdb, mdb))
