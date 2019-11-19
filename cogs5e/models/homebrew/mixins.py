class MixinBase:
    @staticmethod
    def sub_coll(ctx):
        """Gets the MongoDB collection used to track subscriptions."""
        raise NotImplemented

    async def remove_all_tracking(self, ctx):
        """Removes all subscriber documents associated with this object."""
        pass


class SubscriberMixin(MixinBase):
    """A mixin that offers subscription support."""

    async def subscribe(self, ctx):
        """Adds the contextual author as a subscriber."""
        pass

    async def unsubscribe(self, ctx):
        """Removes the contextual author from subscribers."""
        pass

    async def num_subscribers(self, ctx):
        """Returns the number of subscribers."""
        pass


class ActiveMixin(MixinBase):
    """A mixin that offers user active support."""

    async def set_active(self, ctx):
        """Sets the object as active for the contextual author."""
        pass


class GuildActiveMixin(MixinBase):
    """A mixin that offers guild active support."""

    async def toggle_server_active(self, ctx):
        pass

    async def set_server_active(self, ctx):
        """Sets the object as active for the contextual guild."""
        pass

    async def unset_server_active(self, ctx):
        """Sets the object as inactive for the contextual guild."""
        pass


class EditorMixin(MixinBase):
    """A mixin that offers editor tracking."""
    pass


# ==== utilities ====
class CommonHomebrewMixin(SubscriberMixin, ActiveMixin, GuildActiveMixin):
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
