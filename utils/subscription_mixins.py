import abc

from cogs5e.models.errors import NotAllowed


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

    async def is_subscribed(self, ctx):
        """Returns whether the contextual author is subscribed to this object."""
        return (await self.sub_coll(ctx).find_one(
            {"type": "subscribe", "subscriber_id": ctx.author.id, "object_id": self.id})) is not None

    async def subscribe(self, ctx):
        """Adds the contextual author as a subscriber."""
        if await self.is_subscribed(ctx):
            raise NotAllowed("You are already subscribed to this.")

        await self.sub_coll(ctx).insert_one(
            {"type": "subscribe", "subscriber_id": ctx.author.id, "object_id": self.id}
        )

    async def unsubscribe(self, ctx):
        """Removes the contextual author from subscribers."""
        if not await self.is_subscribed(ctx):
            raise NotAllowed("You are not subscribed to this.")

        await self.sub_coll(ctx).delete_many(
            {"type": {"$in": ["subscribe", "active"]}, "subscriber_id": ctx.author.id, "object_id": self.id}
            # unsubscribe, unactive
        )

    async def num_subscribers(self, ctx):
        """Returns the number of subscribers."""
        return await self.sub_coll(ctx).count_documents({"type": "subscribe", "object_id": self.id})

    @classmethod
    async def my_subs(cls, ctx):
        """Returns an async iterator of dicts representing the subscription objects."""
        async for sub in cls.sub_coll(ctx).find({"type": "subscribe", "subscriber_id": ctx.author.id}):
            yield sub

    @classmethod
    async def my_sub_ids(cls, ctx):
        """Returns an async iterator of ObjectIds representing objects the contextual author is subscribed to."""
        async for sub in cls.my_subs(ctx):
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

    async def is_server_active(self, ctx):
        """Returns whether the object is active on this server."""
        return (await self.sub_coll(ctx).find_one(
            {"type": "server_active", "subscriber_id": ctx.guild.id, "object_id": self.id})) is not None

    async def toggle_server_active(self, ctx):
        """Toggles whether the object is active in the contextual guild.
        Returns a bool representing its new activity."""
        if await self.is_server_active(ctx):  # I subscribed and want to unsubscribe
            await self.unset_server_active(ctx)
            return False
        else:  # no one has served this object and I want to
            await self.set_server_active(ctx)
            return True

    async def set_server_active(self, ctx):
        """Sets the object as active for the contextual guild."""
        await self.sub_coll(ctx).insert_one(
            {"type": "server_active", "subscriber_id": ctx.guild.id, "object_id": self.id})

    async def unset_server_active(self, ctx):
        """Sets the object as inactive for the contextual guild."""
        await self.sub_coll(ctx).delete_many(
            {"type": "server_active", "subscriber_id": ctx.guild.id, "object_id": self.id})

    async def num_server_active(self, ctx):
        """Returns the number of guilds that have this object active."""
        return await self.sub_coll(ctx).count_documents({"type": "server_active", "object_id": self.id})

    @classmethod
    async def guild_active_subs(cls, ctx):
        """Returns an async iterator of dicts representing the subscription object."""
        async for sub in cls.sub_coll(ctx).find({"type": "server_active", "subscriber_id": ctx.guild.id}):
            yield sub

    @classmethod
    async def guild_active_ids(cls, ctx):
        """Returns a async iterator of ObjectIds representing the objects active in the contextual server."""
        async for sub in cls.guild_active_subs(ctx):
            yield sub['object_id']


class EditorMixin(MixinBase, abc.ABC):
    """A mixin that offers editor tracking."""

    async def is_editor(self, ctx, user):
        """Returns whether the given user can edit this object."""
        return (await self.sub_coll(ctx).find_one(
            {"type": "editor", "subscriber_id": user.id, "object_id": self.id})) is not None

    async def toggle_editor(self, ctx, user):
        """Toggles whether a user is allowed to edit the given object.
        Returns whether they can after operations.
        :type user: :class:`discord.User`"""
        if not await self.is_editor(ctx, user):
            await self.add_editor(ctx, user)
            return True
        else:
            await self.remove_editor(ctx, user)
            return False

    async def add_editor(self, ctx, user):
        """Adds the user to the editor list of this object."""
        await self.sub_coll(ctx).insert_one({"type": "editor", "subscriber_id": user.id, "object_id": self.id})

    async def remove_editor(self, ctx, user):
        """Removes the user from the editor list of this object."""
        await self.sub_coll(ctx).delete_many({"type": "editor", "subscriber_id": user.id, "object_id": self.id})

    @classmethod
    async def my_editable_ids(cls, ctx):
        """Returns an async iterator of ObjectIds representing objects the contextual author can edit."""
        async for sub in cls.sub_coll(ctx).find({"type": "editor", "subscriber_id": ctx.author.id}):
            yield sub['object_id']


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
