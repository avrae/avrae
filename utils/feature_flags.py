"""
Asyncio wrapper for launchdarkly client to ensure flag evaluation is not a blocking call.
"""

from typing import Optional, TYPE_CHECKING

import ldclient
# Required for SDK 8.0 and above
from ldclient.config import Config

if TYPE_CHECKING:
    import ddb.auth
    import disnake


class AsyncLaunchDarklyClient(ldclient.LDClient):
    """Works exactly like a normal LDClient, except certain blocking methods run in a separate thread."""

    def __init__(self, loop, sdk_key, *args, **kwargs):
        # config = ldclient.Config(sdk_key=sdk_key, *args, **kwargs) # Deprecated: SDK 7.0 and below
        config = ldclient.set_config(Config(sdk_key=sdk_key, http=HTTPConfig(connect_timeout=5), *args, **kwargs)) # Required for SDK 8.0 and above
        # config = ldclient.get() # Required for SDK 8.0 and above
        super().__init__(config=config)
        self.loop = loop

    async def variation(self, key, user, default):  # run variation evaluation in a separate thread
        return await self.loop.run_in_executor(None, super().variation, key, user, default)

    async def variation_for_discord_user(self, key: str, user: "disnake.User", default):
        """Return a variation for a key given a discord user."""
        # return await self.variation(key, discord_user_to_dict(user), default) # Deprecated: SDK 7.0 and below
        return await self.variation(key, discord_user_to_context(user), default)

    async def variation_for_ddb_user(self, key: str, user: Optional["ddb.auth.BeyondUser"], default, discord_id: int):
        """Return a variation for a key given a DDB user or None."""
        if user is None:
            # user = {"key": str(discord_id), "anonymous": True} # Deprecated: SDK 7.0 and below
            # TODO: Check if second argument is valid for "anonymous" as a -kind- of user
            context = ldclient.Context.create(str(discord_id), True) # Required for SDK 8.0 and above
        else:
            user = user.to_ld_dict()
        return await self.variation(key, user, default)


# Updated from discord_user_to_dict to discord_user_to_context
def discord_user_to_context(user):
    """Converts a Discord user to a context for LD."""
    # return {"key": str(user.id), "name": str(user)} # Deprecated: SDK 7.0 and below
    return ldclient.Context.builder(str(user.id)).name(str(user)).build() # Required for SDK 8.0 and above
