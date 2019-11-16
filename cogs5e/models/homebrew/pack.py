import copy

from bson import ObjectId

from cogs5e.models.errors import NoActiveBrew
from utils.functions import search_and_select


class Pack:
    def __init__(self, _id: ObjectId, name: str, owner: dict, editors: list, public: bool, active: list,
                 server_active: list, items: list, image: str, desc: str, subscribers=None, **kwargs):
        if subscribers is None:
            subscribers = []
        self._id = _id
        self.name = name
        self.owner = owner
        self.editors = editors
        self.subscribers = subscribers
        self.public = public
        self.active = active
        self.server_active = server_active
        self.items = items
        self.image = image
        self.desc = desc

    @classmethod
    def from_dict(cls, raw):
        return cls(**raw)

    @classmethod
    async def from_ctx(cls, ctx):
        active_pack = await ctx.bot.mdb.packs.find_one({"active": str(ctx.author.id)})
        if active_pack is None:
            raise NoActiveBrew()
        return cls.from_dict(active_pack)

    @classmethod
    async def from_id(cls, ctx, pack_id):
        pack = await ctx.bot.mdb.packs.find_one({"_id": ObjectId(pack_id)})
        if pack is None:
            raise NoActiveBrew()
        return cls.from_dict(pack)

    def to_dict(self):
        items = self.items  # TODO make Item structured
        return {'name': self.name, 'owner': self.owner, 'editors': self.editors, 'public': self.public,
                'active': self.active, 'server_active': self.server_active, 'items': items, 'image': self.image,
                'desc': self.desc,  # end v1
                'subscribers': self.subscribers}

    @property
    def id(self):
        return self._id

    def get_search_formatted_items(self):
        _items = copy.deepcopy(self.items)
        for i in _items:
            i['srd'] = True
            i['source'] = 'homebrew'
        return _items

    async def commit(self, ctx):
        """Writes a pack object to the database."""
        data = {"$set": self.to_dict()}

        await ctx.bot.mdb.packs.update_one(
            {"_id": self._id}, data
        )

    async def set_active(self, ctx):
        await ctx.bot.mdb.packs.update_many(
            {"active": str(ctx.author.id)},
            {"$pull": {"active": str(ctx.author.id)}}
        )
        await ctx.bot.mdb.packs.update_one(
            {"_id": self._id},
            {"$push": {"active": str(ctx.author.id)}}
        )

    async def toggle_server_active(self, ctx):
        """
        Toggles whether the pack should be active on the contextual server.
        :param ctx: Context
        :return: Whether the pack is now active on the server.
        """
        data = await ctx.bot.mdb.packs.find_one({"_id": self._id}, ["server_active"])
        server_active = data.get('server_active', [])
        if str(ctx.guild.id) in server_active:
            server_active.remove(str(ctx.guild.id))
        else:
            server_active.append(str(ctx.guild.id))
        await ctx.bot.mdb.packs.update_one(
            {"_id": self._id},
            {"$set": {"server_active": server_active}}
        )
        return str(ctx.guild.id) in server_active

    @staticmethod
    def view_query(user_id):
        """Returns the MongoDB query to find all documents a user can set active."""
        return {"$or": [
            {"owner.id": user_id},
            {"editors.id": user_id},
            {"$and": [
                {"subscribers.id": user_id},
                {"public": True}
            ]}
        ]}


async def select_pack(ctx, name):
    available_pack_names = await ctx.bot.mdb.packs.find(
        Pack.view_query(str(ctx.author.id)),
        ['name', '_id']
    ).to_list(None)

    if not available_pack_names:
        raise NoActiveBrew()

    result = await search_and_select(ctx, available_pack_names, name, lambda p: p['name'])
    final_pack = await ctx.bot.mdb.packs.find_one({"_id": result['_id']})

    return Pack.from_dict(final_pack)
