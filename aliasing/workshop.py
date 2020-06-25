import abc
import enum

from bson import ObjectId

from aliasing.errors import CollectableNotFound, CollectionNotFound
from utils.subscription_mixins import EditorMixin, GuildActiveMixin, SubscriberMixin


class PublicationState(enum.Enum):
    PRIVATE = 'PRIVATE'
    UNLISTED = 'UNLISTED'
    PUBLISHED = 'PUBLISHED'


class WorkshopCollection(SubscriberMixin, GuildActiveMixin, EditorMixin):
    """
    A collection of aliases and snippets.

    Read-only bot-side; all modifications must be made through avrae.io.
    """

    def __init__(self,
                 _id, name, description, image, owner,
                 alias_ids, snippet_ids,
                 publish_state, num_subscribers, num_guild_subscribers, last_edited, created_at, tags):
        """
        :param _id: The MongoDB ID of this collection.
        :type _id: bson.ObjectId
        :param name: The name of this collection.
        :type name: str
        :param description: The description.
        :type description: str
        :param image: The URL to the image for this collection, if applicable.
        :type image: str or None
        :param owner: The owner ID of this collection.
        :type owner: int
        :param alias_ids: A list of alias IDs contained in this collection.
        :type alias_ids: list[ObjectId]
        :param snippet_ids: A list of snippet IDs contained in this collection.
        :type snippet_ids: list[ObjectId]
        :param publish_state: The publication state of this collection.
        :type publish_state: PublicationState
        :param num_subscribers: The approximate number of subscribers of this collection.
        :type num_subscribers: int
        :param num_guild_subscribers: The approximate number of guilds subscribed to this collection.
        :type num_guild_subscribers: int
        :param last_edited: The time this collection was last edited.
        :type last_edited: datetime.datetime
        :param created_at: The time this collection was created.
        :type created_at: datetime.datetime
        :param tags: The tags of this collection
        :type tags: list[str]
        """
        super().__init__(_id)
        self.name = name
        self.description = description
        self.image = image
        self.owner = owner
        self._aliases = None
        self._snippets = None
        self.publish_state = publish_state
        self.approx_num_subscribers = num_subscribers
        self.approx_num_guild_subscribers = num_guild_subscribers
        self.last_edited = last_edited
        self.created_at = created_at
        self.tags = tags
        # lazy-load aliases/snippets
        self._alias_ids = alias_ids
        self._snippet_ids = snippet_ids

    @property
    def aliases(self):
        if self._aliases is None:
            raise AttributeError("Aliases are not loaded yet - run load_aliases() first")
        return self._aliases

    @property
    def snippets(self):
        if self._snippets is None:
            raise AttributeError("Snippets are not loaded yet - run load_snippets() first")
        return self._snippets

    async def load_aliases(self, ctx):
        self._aliases = []
        for alias_id in self._alias_ids:
            self._aliases.append(await WorkshopAlias.from_id(ctx, alias_id, collection=self, parent=None))

    async def load_snippets(self, ctx):
        self._snippets = []
        for snippet_id in self._snippet_ids:
            self._snippets.append(await WorkshopSnippet.from_id(ctx, snippet_id, collection=self))

    # constructors
    @classmethod
    async def from_id(cls, ctx, _id):
        if not isinstance(_id, ObjectId):
            _id = ObjectId(_id)

        raw = await ctx.mdb.workshop_collections.find_one({"_id": _id})
        if raw is None:
            raise CollectionNotFound()

        return cls(raw['_id'], raw['name'], raw['description'], raw['image'], raw['owner'],
                   raw['alias_ids'], raw['snippet_ids'],
                   raw['publish_state'], raw['num_subscribers'], raw['num_guild_subscribers'],
                   raw['last_edited'], raw['created_at'], raw['tags'])

    # helpers
    @classmethod
    async def user_owned_ids(cls, ctx):
        """Returns an async iterator of ObjectIds of objects the contextual user owns."""
        async for obj in ctx.mdb.workshop_collections.find({"owner": ctx.author.id}, ['_id']):
            yield obj['_id']

    def is_owned_by(self, user):
        """Returns whether the member owns the object.
        :type user: :class:`discord.User`"""
        return self.owner == user.id

    @classmethod
    async def user_visible(cls, ctx):
        """Returns an async iterator of WorkshopCollections that the user has subscribed to."""
        async for coll_id in cls.user_owned_ids(ctx):
            try:
                yield await cls.from_id(ctx, coll_id)
            except CollectionNotFound:
                continue
        async for coll_id in cls.my_editable_ids(ctx):
            try:
                yield await cls.from_id(ctx, coll_id)
            except CollectionNotFound:
                continue
        async for coll_id in cls.my_sub_ids(ctx):
            try:
                yield await cls.from_id(ctx, coll_id)
            except CollectionNotFound:
                continue

    @classmethod
    async def server_active(cls, ctx):
        """Returns an async generator of WorkshopCollections that the server has subscribed to."""
        async for tome_id in cls.guild_active_ids(ctx):
            try:
                yield await cls.from_id(ctx, tome_id)
            except CollectionNotFound:
                continue

    @staticmethod
    def sub_coll(ctx):
        return ctx.bot.mdb.workshop_subscriptions


class WorkshopCollectableObject(abc.ABC):
    def __init__(self, _id, name,
                 code, versions, docs, collection):
        """
        :param _id: The MongoDB ID of this object.
        :type _id: bson.ObjectId
        :param name: The name of this object.
        :type name: str
        :param code: The code of this object.
        :type code: str
        :param versions: A list of code versions of this object.
        :type versions: list[CodeVersion]
        :param docs: The help docs of this object.
        :type docs: str
        :param collection: The top-level Collection this object is a member of.
        :type collection: WorkshopCollection
        """
        self.id = _id
        self.name = name
        self.code = code
        self.versions = versions
        self.docs = docs
        self.collection = collection


class WorkshopAlias(WorkshopCollectableObject):
    def __init__(self, _id, name, code, versions, docs, collection,
                 subcommand_ids, parent):
        """
        :param subcommand_ids: The alias IDs that are a child of this alias.
        :type subcommand_ids: list[ObjectId]
        :param parent: The alias that is a parent of this alias, if applicable.
        :type parent: WorkshopAlias or None
        """
        super().__init__(_id, name, code, versions, docs, collection)
        self._subcommands = None
        self.parent = parent
        # lazy-load subcommands
        self._subcommand_ids = subcommand_ids

    @property
    def subcommands(self):
        if self._subcommands is None:
            raise AttributeError("Subcommands are not loaded yet - run load_subcommands() first")
        return self._subcommands

    async def load_subcommands(self, ctx):
        self._subcommands = []
        for subcommand_id in self._subcommand_ids:
            self._subcommands.append(
                await WorkshopAlias.from_id(ctx, subcommand_id, collection=self.collection, parent=self))

    # constructors
    @classmethod
    async def from_id(cls, ctx, _id, collection, parent):
        if not isinstance(_id, ObjectId):
            _id = ObjectId(_id)

        raw = await ctx.mdb.workshop_aliases.find_one({"_id": _id})
        if raw is None:
            raise CollectableNotFound()

        versions = [CodeVersion.from_dict(cv) for cv in raw['versions']]
        return cls(raw['_id'], raw['name'], raw['code'], versions, raw['docs'], collection,
                   raw['subcommand_ids'], parent)


class WorkshopSnippet(WorkshopCollectableObject):
    @classmethod
    async def from_id(cls, ctx, _id, collection):
        if not isinstance(_id, ObjectId):
            _id = ObjectId(_id)

        raw = await ctx.mdb.workshop_snippets.find_one({"_id": _id})
        if raw is None:
            raise CollectableNotFound()

        versions = [CodeVersion.from_dict(cv) for cv in raw['versions']]
        return cls(raw['_id'], raw['name'], raw['code'], versions, raw['docs'], collection)


class CodeVersion:
    def __init__(self, version, content, created_at, is_current):
        """
        :param version: The version of code.
        :type version: int
        :param content: The content of this version.
        :type content: str
        :param created_at: The time this version was created.
        :type created_at: datetime.datetime
        :param is_current: Whether this version is the current live version.
        :type is_current: bool
        """
        self.version = version
        self.content = content
        self.created_at = created_at
        self.is_current = is_current

    @classmethod
    def from_dict(cls, raw):
        return cls(**raw)

# test_coll = {
#     '_id': ObjectId(), 'name': 'Test Workshop Collection', 'description': "A test collection", 'image': None,
#     'owner': 187421759484592128, 'alias_ids': [], 'snippet_ids': [], 'publish_state': PublicationState.PUBLISHED,
#     'num_subscribers': 0, 'num_guild_subscribers': 0, 'last_edited': datetime.datetime.utcnow(),
#     'created_at': datetime.datetime.utcnow(), 'tags': ['foo']
# }
#
# test_alias = {
#     '_id': ObjectId(), 'name': 'wsalias', 'code': 'echo This is wsalias!', 'versions': [],
#     'docs': "This is a test alias", 'subcommand_ids': []
# }
#
# test_snippet = {
#     '_id': ObjectId(), 'name': 'wssnippet', 'code': '-phrase "This is wssnippet!"', 'versions': [],
#     'docs': "This is a test snippet"
# }
