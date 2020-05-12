"""
Asyncio wrapper for launchdarkly client to ensure flag evaluation is not a blocking call.
"""

import ldclient


class AsyncLaunchDarklyClient(ldclient.LDClient):
    """Works exactly like a normal LDClient, except certain blocking methods run in a separate thread."""

    def __init__(self, loop, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.loop = loop

    async def variation(self, key, user, default):  # run variation evaluation in a separate thread
        return await self.loop.run_in_executor(None, super().variation, key, user, default)
