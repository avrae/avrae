from bson import ObjectId

from cogs5e.models.errors import NoActiveBrew
from cogs5e.models.homebrew.mixins import CommonHomebrewMixin, EditorMixin
from cogs5e.models.spell import Spell
from utils.functions import search_and_select


class Tome(CommonHomebrewMixin, EditorMixin):
    def __init__(self, _id: ObjectId, name: str, owner: dict, public: bool,
                 spells: list, image: str, desc: str, **_):
        # metadata
        super().__init__(_id)
        self.name = name
        self.owner = owner
        self.public = public

        # todo
        self.editors = editors
        self.subscribers = subscribers
        self.active = active
        self.server_active = server_active

        # content
        self.spells = spells
        self.image = image
        self.desc = desc

    @classmethod
    def from_dict(cls, raw):
        raw['spells'] = list(map(Spell.from_dict, raw['spells']))
        return cls(**raw)

    @classmethod
    async def from_ctx(cls, ctx):
        active_tome = await cls.active_id(ctx)
        if active_tome is None:
            raise NoActiveBrew()
        return cls.from_id(ctx, active_tome)

    @classmethod
    async def from_id(cls, ctx, tome_id, meta_only=False):
        if not isinstance(tome_id, ObjectId):
            tome_id = ObjectId(tome_id)

        if meta_only:
            tome = await ctx.bot.mdb.tomes.find_one({"_id": tome_id}, ['_id', 'name', 'owner', 'public'])
        else:
            tome = await ctx.bot.mdb.tomes.find_one({"_id": tome_id})
        if tome is None:
            raise NoActiveBrew()

        if not meta_only:
            return cls.from_dict(tome)
        return tome

    # helper methods
    def is_owned_by(self, user):
        """Returns whether the member owns the tomr.
        :type user: :class:`discord.User`"""
        return self.owner['id'] == user.id  # todo

    @staticmethod
    async def user_owned_ids(ctx):
        """Returns an async iterator of ObjectIds of tomes the contextual user owns."""
        async for tome in ctx.bot.mdb.tomes.find({"owner.id": ctx.author.id}, ['_id']):  # todo
            yield tome['_id']

    @staticmethod
    async def user_tomes(ctx, meta_only=False):
        """Returns an async iterator of Tome objects (or dicts, if meta_only is set) that the user can set active."""
        async for tome_id in Tome.user_owned_ids(ctx):
            yield await Tome.from_id(ctx, tome_id, meta_only=meta_only)
        async for tome_id in Tome.my_editable_ids(ctx):
            yield await Tome.from_id(ctx, tome_id, meta_only=meta_only)
        async for tome_id in Tome.my_sub_ids(ctx):
            yield await Tome.from_id(ctx, tome_id, meta_only=meta_only)

    @staticmethod
    async def server_tomes(ctx, meta_only=False):
        """Returns an async generator of Tome objects (or dicts, if meta_only is set) that the server has active."""
        async for tome_id in Tome.guild_active_ids(ctx):
            yield await Tome.from_id(ctx, tome_id, meta_only=meta_only)

    @staticmethod
    async def num_visible(ctx):
        """Returns the number of tomes the contextual user can set active."""
        return sum(1 async for _ in Tome.user_tomes(ctx, meta_only=True))

    # subscription helpers
    @staticmethod
    def sub_coll(ctx):
        return ctx.bot.mdb.tome_subscriptions


async def select_tome(ctx, name):
    available_tome_names = [tome async for tome in Tome.user_tomes(ctx, meta_only=True)]
    if not available_tome_names:
        raise NoActiveBrew()

    result = await search_and_select(ctx, available_tome_names, name, lambda p: p['name'])
    return await Tome.from_id(ctx, result['_id'])
