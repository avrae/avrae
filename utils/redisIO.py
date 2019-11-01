"""
Created on Dec 28, 2016

@author: andrew
"""

import json


class RedisIO:
    """
    A simple class to interface with the redis database.
    """

    def __init__(self, _db):
        """
        :type _db: :class:`aioredis.Redis`
        """
        self._db = _db

    async def get(self, key, default=None):
        encoded_data = await self._db.get(key)
        return encoded_data.decode() if encoded_data is not None else default

    async def set(self, key, value, **kwargs):
        return await self._db.set(key, value, **kwargs)

    async def incr(self, key):
        return await self._db.incr(key)

    async def exists(self, *keys):
        return await self._db.exists(*keys)

    async def delete(self, *keys):
        return await self._db.delete(*keys)

    async def setex(self, key, value, expiration):
        return await self._db.setex(key, expiration, value)

    async def setnx(self, key, value):
        return await self._db.setnx(key, value)

    # ==== hashmaps ====
    async def set_dict(self, key, dictionary):
        return await self._db.hmset_dict(key, **dictionary)

    async def get_dict(self, key, dict_key):
        return await self.hget(key, dict_key)

    async def get_whole_dict(self, key, default=None):
        if default is None:
            default = {}
        out = await self._db.hgetall(key, encoding='utf-8')
        if out is None:
            return default
        return out

    async def hget(self, key, field, default=None):
        out = await self._db.hget(key, field, encoding='utf-8')
        return out if out is not None else default

    async def hset(self, key, field, value):
        return await self._db.hset(key, field, value)

    async def hdel(self, key, *fields):
        return await self._db.hdel(key, *fields)

    async def hlen(self, key):
        return await self._db.hlen(key)

    async def hexists(self, hashkey, key):
        return await self._db.hexists(hashkey, key)

    async def hincrby(self, key, field, increment):
        return await self._db.hincrby(key, field, increment)

    async def jhget(self, key, field, default=None):
        data = await self.hget(key, field)
        return json.loads(data) if data is not None else default

    async def jhset(self, key, field, value, **kwargs):
        data = json.dumps(value, **kwargs)
        return await self.hset(key, field, data)

    # ==== json ====
    async def jset(self, key, data, **kwargs):
        return await self.not_json_set(key, data, **kwargs)

    async def jsetex(self, key, data, exp, **kwargs):
        data = json.dumps(data, **kwargs)
        return await self.setex(key, data, exp)

    async def jget(self, key, default=None):
        return await self.not_json_get(key, default)

    async def not_json_set(self, key, data, **kwargs):
        data = json.dumps(data, **kwargs)
        return await self.set(key, data)

    async def not_json_get(self, key, default=None):
        data = await self.get(key)
        return json.loads(data) if data is not None else default

    # ==== lists ====
    async def llen(self, key):
        return await self._db.llen(key)

    async def lindex(self, key, index):
        encoded_data = await self._db.lindex(key, index)
        return encoded_data.decode() if encoded_data is not None else None

    async def rpush(self, key, *values):
        return await self._db.rpush(key, *values)

    # ==== pubsub ====
    async def publish(self, channel, data):
        return await self._db.publish(channel, data)
