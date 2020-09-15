import abc

from bson import ObjectId

from cogs5e.models.errors import NoActiveBrew
from utils.functions import search_and_select
from utils.subscription_mixins import CommonHomebrewMixin, EditorMixin


class HomebrewContainer(CommonHomebrewMixin, EditorMixin, abc.ABC):
    def __init__(self, _id: ObjectId, name: str, owner: int, public: bool,
                 image: str, desc: str, **_):
        # metadata
        super().__init__(_id)
        self.name = name
        self.owner = owner
        self.public = public

        # content
        self.image = image
        self.desc = desc

    # abstract methods
    @staticmethod
    def data_coll(ctx):
        raise NotImplementedError

    # instantiators
    @classmethod
    def from_dict(cls, raw):
        return cls(**raw)

    @classmethod
    async def from_ctx(cls, ctx):
        active_id = await cls.active_id(ctx)
        if active_id is None:
            raise NoActiveBrew()
        return await cls.from_id(ctx, active_id)

    @classmethod
    async def from_id(cls, ctx, _id, meta_only=False):
        if not isinstance(_id, ObjectId):
            _id = ObjectId(_id)

        if meta_only:
            obj = await cls.data_coll(ctx).find_one({"_id": _id}, ['_id', 'name', 'owner', 'public'])
        else:
            obj = await cls.data_coll(ctx).find_one({"_id": _id})
        if obj is None:
            raise NoActiveBrew()

        if not meta_only:
            return cls.from_dict(obj)
        return obj

    # helpers
    @classmethod
    async def user_owned_ids(cls, ctx):
        """Returns an async iterator of ObjectIds of objects the contextual user owns."""
        async for obj in cls.data_coll(ctx).find({"owner": ctx.author.id}, ['_id']):
            yield obj['_id']

    def is_owned_by(self, user):
        """Returns whether the member owns the object.
        :type user: :class:`discord.User`"""
        return self.owner == user.id

    @classmethod
    async def user_visible(cls, ctx, meta_only=False):
        """Returns an async iterator of objects (or dicts, if meta_only is set) that the user can set active."""
        async for tome_id in cls.user_owned_ids(ctx):
            try:
                yield await cls.from_id(ctx, tome_id, meta_only=meta_only)
            except NoActiveBrew:
                continue
        async for tome_id in cls.my_editable_ids(ctx):
            try:
                yield await cls.from_id(ctx, tome_id, meta_only=meta_only)
            except NoActiveBrew:
                continue
        async for tome_id in cls.my_sub_ids(ctx):
            try:
                yield await cls.from_id(ctx, tome_id, meta_only=meta_only)
            except NoActiveBrew:
                continue

    @classmethod
    async def server_active(cls, ctx, meta_only=False):
        """Returns an async generator of objects (or dicts, if meta_only is set) that the server has active."""
        async for tome_id in cls.guild_active_ids(ctx):
            try:
                yield await cls.from_id(ctx, tome_id, meta_only=meta_only)
            except NoActiveBrew:
                continue

    @classmethod
    async def num_visible(cls, ctx):
        """Returns the number of tomes the contextual user can set active."""
        return sum([1 async for _ in cls.user_visible(ctx, meta_only=True)])

    @classmethod
    async def select(cls, ctx, name):
        """Searches and selects from all objects visible to a user."""
        available_names = [n async for n in cls.user_visible(ctx, meta_only=True)]
        if not available_names:
            raise NoActiveBrew()

        result = await search_and_select(ctx, available_names, name, lambda p: p['name'])
        return await cls.from_id(ctx, result['_id'])
