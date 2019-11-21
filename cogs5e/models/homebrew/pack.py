import copy

from bson import ObjectId

from cogs5e.models.errors import NoActiveBrew
from cogs5e.models.homebrew.mixins import CommonHomebrewMixin, EditorMixin
from utils.functions import search_and_select


class Pack(CommonHomebrewMixin, EditorMixin):
    def __init__(self, _id: ObjectId, name: str, owner: dict, public: bool,
                 items: list, image: str, desc: str, **_):
        # metadata
        super().__init__(_id)
        self.name = name
        self.owner = owner
        self.public = public

        # todo
        self.editors = editors
        self.subscribers = subscribers

        # content
        self.items = items
        self.image = image
        self.desc = desc

    @classmethod
    def from_dict(cls, raw):
        return cls(**raw)

    @classmethod
    async def from_ctx(cls, ctx):
        active_pack = await cls.active_id(ctx)
        if active_pack is None:
            raise NoActiveBrew()
        return cls.from_id(ctx, active_pack)

    @classmethod
    async def from_id(cls, ctx, pack_id, meta_only=False):
        if not isinstance(pack_id, ObjectId):
            pack_id = ObjectId(pack_id)

        if meta_only:
            pack = await ctx.bot.mdb.packs.find_one({"_id": pack_id}, ['_id', 'name', 'owner', 'public'])
        else:
            pack = await ctx.bot.mdb.packs.find_one({"_id": pack_id})
        if pack is None:
            raise NoActiveBrew()

        if not meta_only:
            return cls.from_dict(pack)
        return pack

    def to_dict(self):
        return {'name': self.name, 'owner': self.owner, 'public': self.public,  # todo
                'items': self.items, 'image': self.image, 'desc': self.desc}

    def get_search_formatted_items(self):
        for i in self.items:
            i['srd'] = True
            i['source'] = 'homebrew'
        return self.items

    async def commit(self, ctx):
        """Writes a pack object to the database."""
        data = {"$set": self.to_dict()}

        await ctx.bot.mdb.packs.update_one(
            {"_id": self.id}, data
        )

    # helper methods
    def is_owned_by(self, user):
        """Returns whether the member owns the pack.
        :type user: :class:`discord.User`"""
        return self.owner['id'] == user.id  # todo

    @staticmethod
    async def user_owned_ids(ctx):
        """Returns an async iterator of ObjectIds of packs the contextual user owns."""
        async for pack in ctx.bot.mdb.packs.find({"owner.id": ctx.author.id}, ['_id']):
            yield pack['_id']

    @staticmethod
    async def user_packs(ctx, meta_only=False):
        """Returns an async iterator of Pack objects (or dicts, if meta_only is set) that the user can set active."""
        async for pack_id in Pack.user_owned_ids(ctx):
            yield await Pack.from_id(ctx, pack_id, meta_only=meta_only)
        async for pack_id in Pack.my_editable_ids(ctx):
            yield await Pack.from_id(ctx, pack_id, meta_only=meta_only)
        async for pack_id in Pack.my_sub_ids(ctx):
            yield await Pack.from_id(ctx, pack_id, meta_only=meta_only)

    @staticmethod
    async def server_packs(ctx, meta_only=False):
        """Returns an async generator of Pack objects (or dicts, if meta_only is set) that the server has active."""
        async for pack_id in Pack.guild_active_ids(ctx):
            yield await Pack.from_id(ctx, pack_id, meta_only=meta_only)

    @staticmethod
    async def num_visible(ctx):
        """Returns the number of packs the contextual user can set active."""
        return sum(1 async for _ in Pack.user_packs(ctx, meta_only=True))

    # subscription helpers
    @staticmethod
    def sub_coll(ctx):
        return ctx.bot.mdb.pack_subscriptions


async def select_pack(ctx, name):
    available_pack_names = [pack async for pack in Pack.user_packs(ctx, meta_only=True)]
    if not available_pack_names:
        raise NoActiveBrew()

    result = await search_and_select(ctx, available_pack_names, name, lambda p: p['name'])
    return await Pack.from_id(ctx, result['_id'])
