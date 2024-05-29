"""
Created on Dec 28, 2016

@author: andrew
"""

import abc
import json
import logging
import uuid


class RedisIO:
    """
    A simple class to interface with the redis database.
    """

    def __init__(self, _db):
        """
        :type _db: :class:`redis.asyncio.Redis`
        """
        self._db = _db

    async def get(self, key, default=None):
        encoded_data = await self._db.get(key)
        return encoded_data.decode() if encoded_data is not None else default

    async def set(self, key, value, *, ex=None, nx=False, xx=False):
        if nx and xx:
            raise ValueError("'nx' and 'xx' args are mutually exclusive")
        if nx:
            return await self._db.set(key, value, ex=ex, nx=True)
        elif xx:
            return await self._db.set(key, value, ex=ex, xx=True)
        return await self._db.set(key, value, ex=ex)

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

    async def ttl(self, key):
        return await self._db.ttl(key)

    async def iscan(self, match=None, count=None):
        async for key_bin in self._db.scan_iter(match=match, count=count):
            yield key_bin.decode()

    # ==== hashmaps ====
    async def set_dict(self, key, dictionary):
        return await self._db.hset(key, **dictionary)

    async def get_dict(self, key, dict_key):
        return await self.hget(key, dict_key)

    async def get_whole_dict(self, key, default=None):
        if default is None:
            default = {}
        out = await self._db.hgetall(key)

        data = {key.decode("utf-8"): value for key, value in out.items()}

        if data is None:
            return default
        return data

    async def hget(self, key, field, default=None):
        out = await self._db.hget(key, field)
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
    async def subscribe(self, *channels):
        pssub = self._db.client().pubsub()
        await pssub.subscribe(*channels)
        return pssub

    async def publish(self, channel, data):
        return await self._db.publish(channel, data)

    # ==== misc ====
    async def close(self):
        await self._db.close()


class _PubSubMessageBase(abc.ABC):
    def __init__(self, type, id, sender):
        self.type = type
        self.id = id
        self.sender = sender

    @classmethod
    def from_dict(cls, d):
        return cls(**d)

    def to_dict(self):
        return {"type": self.type, "id": self.id, "sender": self.sender}

    def to_json(self):
        return json.dumps(self.to_dict())


class PubSubCommand(_PubSubMessageBase):
    def __init__(self, id, sender, command, args, kwargs):
        super().__init__("cmd", id, sender)
        self.command = command
        self.args = args
        self.kwargs = kwargs

    @classmethod
    def new(cls, bot, command, args=None, kwargs=None):
        if args is None:
            args = []
        if kwargs is None:
            kwargs = {}
        _id = str(uuid.uuid4())
        return cls(_id, bot.cluster_id, command, args, kwargs)

    def to_dict(self):
        inst = super(PubSubCommand, self).to_dict()
        inst.update({"command": self.command, "args": self.args, "kwargs": self.kwargs})
        return inst


class PubSubReply(_PubSubMessageBase):
    def __init__(self, id, sender, reply_to, data):
        super().__init__("reply", id, sender)
        self.reply_to = reply_to
        self.data = data

    @classmethod
    def new(cls, bot, reply_to, data):
        _id = str(uuid.uuid4())
        return cls(_id, bot.cluster_id, reply_to, data)

    def to_dict(self):
        inst = super().to_dict()
        inst.update({"reply_to": self.reply_to, "data": self.data})
        return inst


PS_DESER_MAP = {"cmd": PubSubCommand, "reply": PubSubReply}


def deserialize_ps_msg(message: str):
    data = json.loads(message)
    t = data.pop("type")
    if t not in PS_DESER_MAP:
        raise TypeError(f"{t} is not a valid pubsub message type.")
    return PS_DESER_MAP[t].from_dict(data)


pslogger = logging.getLogger("rdb.pubsub")
