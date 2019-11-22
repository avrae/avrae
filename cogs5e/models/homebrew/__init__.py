from cogs5e.models.spell import Spell
from .base import HomebrewContainer


class Tome(HomebrewContainer):
    def __init__(self, spells: list, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.spells = spells

    @classmethod
    def from_dict(cls, raw):
        raw['spells'] = list(map(Spell.from_dict, raw['spells']))
        return cls(**raw)

    # subscription helpers
    @staticmethod
    def sub_coll(ctx):
        return ctx.bot.mdb.tome_subscriptions

    @staticmethod
    def data_coll(ctx):
        return ctx.bot.mdb.tomes


class Pack(HomebrewContainer):
    def __init__(self, items: list, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.items = items

    def get_search_formatted_items(self):
        for i in self.items:
            i['srd'] = True
            i['source'] = 'homebrew'
        return self.items

    # subscription helpers
    @staticmethod
    def sub_coll(ctx):
        return ctx.bot.mdb.pack_subscriptions

    @staticmethod
    def data_coll(ctx):
        return ctx.bot.mdb.packs
