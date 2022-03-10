import gamedata
from .base import HomebrewContainer


class Tome(HomebrewContainer):
    def __init__(self, spells: list, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.spells = spells

    @classmethod
    def from_dict(cls, raw):
        raw["spells"] = [
            gamedata.Spell.from_homebrew(s, raw["name"]) for s in raw["spells"]
        ]
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

    @classmethod
    def from_dict(cls, raw):
        raw["items"] = [
            gamedata.Item.from_homebrew(s, raw["name"]) for s in raw["items"]
        ]
        return cls(**raw)

    # subscription helpers
    @staticmethod
    def sub_coll(ctx):
        return ctx.bot.mdb.pack_subscriptions

    @staticmethod
    def data_coll(ctx):
        return ctx.bot.mdb.packs
