"""
Asyncio wrapper for launchdarkly client to ensure flag evaluation is not a blocking call.
"""
import asyncio

import ldclient


class AsyncLaunchDarklyClient(ldclient.LDClient):
    """Works exactly like a normal LDClient, except certain blocking methods run in a separate thread."""

    async def variation(self, key, user, default):  # run variation evaluation in a separate thread
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, super().variation, key, user, default)
