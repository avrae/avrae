import abc
import enum

from utils.subscription_mixins import EditorMixin, GuildActiveMixin, SubscriberMixin


class PublicationState(enum.Enum):
    PRIVATE = 'PRIVATE'
    UNLISTED = 'UNLISTED'
    PUBLISHED = 'PUBLISHED'


class WorkshopCollection(SubscriberMixin, GuildActiveMixin, EditorMixin):
    def __init__(self,
                 _id, name, description, image, owner,
                 aliases, snippets,
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
        :param aliases: A list of aliases contained in this collection.
        :type aliases: list[WorkshopAlias]
        :param snippets: A list of snippets contained in this collection.
        :type snippets: list[WorkshopSnippet]
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
        :type tags: TODO
        """
        super().__init__(_id)
        self.name = name
        self.description = description
        self.image = image
        self.owner = owner
        self.aliases = aliases
        self.snippets = snippets
        self.publish_state = publish_state
        self.approx_num_subscribers = num_subscribers
        self.approx_num_guild_subscribers = num_guild_subscribers
        self.last_edited = last_edited
        self.created_at = created_at
        self.tags = tags

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
                 subcommands, parent):
        """
        :param subcommands: The aliases that are a child of this alias.
        :type subcommands: list[WorkshopAlias]
        :param parent: The alias that is a parent of this alias, if applicable.
        :type parent: WorkshopAlias or None
        """
        super().__init__(_id, name, code, versions, docs, collection)
        self.subcommands = subcommands
        self.parent = parent


class WorkshopSnippet(WorkshopCollectableObject):
    def __init__(self, _id, name, code, versions, docs, collection):
        super().__init__(_id, name, code, versions, docs, collection)


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
