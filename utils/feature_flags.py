"""
Asyncio wrapper for launchdarkly client to ensure flag evaluation is not a blocking call.
"""

from typing import Optional, TYPE_CHECKING

import ldclient
from ldclient.config import Config

if TYPE_CHECKING:
    import ddb.auth
    import disnake


class AsyncLaunchDarklyClient(ldclient.LDClient):
    """Works exactly like a normal LDClient, except certain blocking methods run in a separate thread."""

    def __init__(self, loop, sdk_key, *args, **kwargs):
        super().__init__(
            config=Config(sdk_key=sdk_key)
        )  # Required for SDK 8.0 and above. *args, **kwargs are not supported
        self.loop = loop

    async def variation(self, key, user, default):  # run variation evaluation in a separate thread
        return await self.loop.run_in_executor(None, super().variation, key, user, default)

    async def variation_for_discord_user(self, key: str, user: "disnake.User", default):
        """Return a variation for a key given a discord user."""
        return await self.variation(key, discord_user_to_context(user), default)

    async def variation_for_ddb_user(self, key: str, user: Optional["ddb.auth.BeyondUser"], default, discord_id: int):
        """Return a variation for a key given a DDB user or None."""
        if user is None:
            # TODO: Check if second argument is valid for "anonymous" as a -kind- of user
            user = ldclient.Context.create(str(discord_id))
        else:
            user = ldclient.Context.create(str(user.to_ld_dict()))
        return await self.variation(key, user, default)


# Updated from discord_user_to_dict to discord_user_to_context
def discord_user_to_context(user):
    """Converts a Discord user to a context for LD."""
    return ldclient.Context.builder(str(user.id)).name(str(user)).build()
