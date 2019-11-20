import abc


class MixinBase(abc.ABC):
    def __init__(self, oid):
        """
        :type oid: :class:`bson.ObjectId`
        """
        self.id = oid  # subscribable objects need to know their ObjectId

    @staticmethod
    def sub_coll(ctx):
        """Gets the MongoDB collection used to track subscriptions."""
        raise NotImplementedError

    async def remove_all_tracking(self, ctx):
        """Removes all subscriber documents associated with this object."""
        await self.sub_coll(ctx).delete_many({"object_id": self.id})


class SubscriberMixin(MixinBase, abc.ABC):
    """A mixin that offers subscription support."""

    async def subscribe(self, ctx):
        """Adds the contextual author as a subscriber."""
        await self.sub_coll(ctx).insert_one(
            {"type": "subscribe", "subscriber_id": ctx.author.id, "object_id": self.id}
        )

    async def unsubscribe(self, ctx):
        """Removes the contextual author from subscribers."""
        await self.sub_coll(ctx).delete_many(
            {"type": "subscribe", "subscriber_id": ctx.author.id, "object_id": self.id}
        )

    async def num_subscribers(self, ctx):
        """Returns the number of subscribers."""
        return await self.sub_coll(ctx).count_documents({"type": "subscribe", "object_id": self.id})

    @classmethod
    async def my_sub_ids(cls, ctx):
        """Returns an async iterator of ObjectIds representing objects the contextual author is subscribed to."""
        async for sub in cls.sub_coll(ctx).find({"type": "subscribe", "subscriber_id": ctx.author.id}):
            yield sub['object_id']


class ActiveMixin(MixinBase, abc.ABC):
    """A mixin that offers user active support."""

    async def set_active(self, ctx):
        """Sets the object as active for the contextual author, and removes active status from any other documents."""
        await self.sub_coll(ctx).delete_many(
            {"type": "active", "subscriber_id": ctx.author.id}
        )
        await self.sub_coll(ctx).insert_one(
            {"type": "active", "subscriber_id": ctx.author.id, "object_id": self.id}
        )

    @classmethod
    async def active_id(cls, ctx):
        """Returns the ObjectId of the object the user has set as active, or None if the user does not have any."""
        obj = await cls.sub_coll(ctx).find_one({"type": "active", "subscriber_id": ctx.author.id})
        if obj is not None:
            return obj['object_id']
        return None


class GuildActiveMixin(MixinBase, abc.ABC):
    """A mixin that offers guild active support."""

    async def toggle_server_active(self, ctx):
        """Toggles whether the object is active in the contextual guild.
        Returns a bool representing its new activity."""
        sub_doc = await self.sub_coll(ctx).find_one({"type": "server_active", "subscriber_id": ctx.guild.id})

        if sub_doc is not None:  # I subscribed and want to unsubscribe
            await self.unset_server_active(ctx)
            return False
        else:  # no one has served this object and I want to
            await self.set_server_active(ctx)
            return True

    async def set_server_active(self, ctx):
        """Sets the object as active for the contextual guild."""
        sub_doc = {"type": "server_active", "subscriber_id": ctx.guild.id, "object_id": self.id}
        await self.sub_coll(ctx).insert_one(sub_doc)

    async def unset_server_active(self, ctx):
        """Sets the object as inactive for the contextual guild."""
        await self.sub_coll(ctx).delete_one({"type": "server_active", "subscriber_id": ctx.guild.id})

    @classmethod
    async def guild_active_ids(cls, ctx):
        """Returns a async iterator of ObjectIds representing the objects active in the contextual server."""
        async for sub in cls.sub_coll(ctx).find({"type": "server_active", "subscriber_id": ctx.guild.id}):
            yield sub['object_id']


class EditorMixin(MixinBase, abc.ABC):
    """A mixin that offers editor tracking."""
    pass


# ==== utilities ====
class CommonHomebrewMixin(SubscriberMixin, ActiveMixin, GuildActiveMixin, abc.ABC):
    pass

# ==== notes ====
# base schema
# {
#     "type": str,
#     "object_id": ObjectId,
#     "subscriber_id": int
# }

# SubscriberMixin:  type="subscribe"
# ActiveMixin:      type="active"
# GuildActiveMixin: type="server_active"
# EditorMixin:      type="editor"
