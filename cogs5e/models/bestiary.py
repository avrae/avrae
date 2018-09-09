from cogs5e.models.errors import NoBestiary
from cogs5e.models.monster import Monster


class Bestiary:
    def __init__(self, _id: str, name: str, monsters: list):
        self.id = _id
        self.name = name
        self.monsters = monsters

    @classmethod
    def from_raw(cls, _id, raw):
        monsters = [Monster.from_bestiary(m) for m in raw['monsters']]
        return cls(_id, raw['name'], monsters)

    @classmethod
    async def from_ctx(cls, ctx):
        active_bestiary = await ctx.bot.mdb.bestiaries.find_one({"owner": ctx.message.author.id, "active": True})
        if active_bestiary is None:
            raise NoBestiary()
        return cls.from_raw(active_bestiary['critterdb_id'], active_bestiary)

    def to_dict(self):
        return {'monsters': [m.to_dict() for m in self.monsters], 'name': self.name, 'critterdb_id': self.id}

    async def commit(self, ctx):
        """Writes a bestiary object to the database, under the contextual author. Returns self."""
        data = {"$set": self.to_dict(), "$setOnInsert": {"owner": ctx.message.author.id}}

        await ctx.bot.mdb.bestiaries.update_one(
            {"owner": ctx.message.author.id, "critterdb_id": self.id},
            data,
            True
        )
        return self

    async def set_active(self, ctx):
        await ctx.bot.mdb.bestiaries.update_many(
            {"owner": ctx.message.author.id, "active": True},
            {"$set": {"active": False}}
        )
        await ctx.bot.mdb.bestiaries.update_one(
            {"owner": ctx.message.author.id, "critterdb_id": self.id},
            {"$set": {"active": True}}
        )
        return self