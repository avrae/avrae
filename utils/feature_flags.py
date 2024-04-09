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
        """
        Returns a variation for a given key based on a Discord user.

        This method is used to determine the variation for a feature flag key based on the Discord user's information.
        The user's information is converted into a format compatible with LaunchDarkly using the discord_user_to_context method.

        Args:
            key (str): The feature flag key for which the variation is to be determined.
            user ("disnake.User"): The Discord user based on whose information the variation is to be determined.
            default: The default value to return if the feature flag key is not found.

        Returns:
            The variation for the given feature flag key based on the Discord user's information.
        """
        return await self.variation(key, discord_user_to_context(user), default)

    async def variation_for_ddb_user(self, key: str, user: Optional["ddb.auth.BeyondUser"], default, discord_id: int):
        """
        Returns a variation for a given key based on a DDB user or None.

        This method is used to determine the variation for a feature flag key based on the user's information.
        If the user is None, an anonymous context is created using the discord_id.
        If the user is a DDB user, the user's information is converted into a format compatible with LaunchDarkly using the to_ld_dict method.

        Args:
            key (str): The feature flag key for which the variation is to be determined.
            user (Optional["ddb.auth.BeyondUser"]): The DDB user based on whose information the variation is to be determined. If None, an anonymous context is created.
            default: The default value to return if the feature flag key is not found.
            discord_id (int): The discord_id of the user. Used to create an anonymous context if user is None.

        Returns:
            The variation for the given feature flag key based on the user's information.
        """
        if user is None:
            # TODO: Check if second argument is valid for "anonymous" as a -kind- of user
            user = ldclient.Context.create(str(discord_id))
        else:
            user = ldclient.Context.from_dict(user.to_ld_dict())
        return await self.variation(key, user, default)


# Updated from discord_user_to_dict to discord_user_to_context
def discord_user_to_context(user):
    """
    Converts a Discord user to a context for LaunchDarkly.

    This function takes a Discord user as input and converts it into a context that can be used by LaunchDarkly.
    The user's ID is used as the key, and the user's name is used as the name in the context.

    Args:
        user: The Discord user to be converted into a LaunchDarkly context.

    Returns:
        A LaunchDarkly context created from the Discord user's information.
    """
    return ldclient.Context.builder(str(user.id)).name(str(user)).build()
