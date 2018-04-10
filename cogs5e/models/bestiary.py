from cogs5e.models.errors import NoBestiary
from cogs5e.models.monster import Monster


class Bestiary:
    def __init__(self, _id: str, name:str, monsters: list):
        self.id = _id
        self.name = name
        self.monsters = monsters

    @classmethod
    def from_raw(cls, _id, raw):
        monsters = [Monster.from_bestiary(m) for m in raw['monsters']]
        return cls(_id, raw['name'], monsters)

    @classmethod
    def from_ctx(cls, ctx):
        user_bestiaries = ctx.bot.db.jget(ctx.message.author.id + '.bestiaries', {})
        active_bestiary = ctx.bot.db.jget('active_bestiaries', {}).get(ctx.message.author.id)
        if active_bestiary is None:
            raise NoBestiary()
        bestiary = user_bestiaries[active_bestiary]
        return cls.from_raw(active_bestiary, bestiary)

    def to_dict(self):
        return {'monsters': [m.to_dict() for m in self.monsters], 'name': self.name}

    def commit(self, ctx):
        """Writes a bestiary object to the database, under the contextual author. Returns self."""
        user_bestiaries = ctx.bot.db.jget(ctx.message.author.id + '.bestiaries', {})
        user_bestiaries[self.id] = self.to_dict()  # commit
        ctx.bot.db.jset(ctx.message.author.id + '.bestiaries', user_bestiaries)
        return self

    def set_active(self, ctx):
        """Sets the bestiary as active. Returns self."""
        active_bestiaries = ctx.bot.db.jget('active_bestiaries', {})
        active_bestiaries[ctx.message.author.id] = self.id
        ctx.bot.db.jset('active_bestiaries', active_bestiaries)
        return self
