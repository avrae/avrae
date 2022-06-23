import asyncio
import copy
import logging
import urllib.parse
from contextlib import contextmanager
from fnmatch import fnmatchcase

from disnake import Embed
from disnake.http import HTTPClient, Route

from tests.discord_mock_data import MESSAGE_ID, RESPONSES, TEST_CHANNEL_ID, TEST_DMCHANNEL_ID
from tests.utils import message_content_check

log = logging.getLogger(__name__)


class Request:
    def __init__(self, method, url, data=None):
        self.method = method
        self.url = url
        self.data = data

    def __repr__(self):
        return f"{self.method} {self.url}\n{self.data}"


class MockDiscordHTTP(HTTPClient):
    """
    This class handles receiving responses from the bot and keeping it happy.
    It should be used to check that the bot sends what we want.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # set up a way for us to track our requests
        self._request_check_queue = asyncio.Queue()

    # override d.py's request logic to implement our own
    async def request(self, route, *, files=None, header_bypass_delay=None, **kwargs):
        req = Request(route.method, route.url, kwargs.get("data") or kwargs.get("json"))
        log.info(str(req))

        request_route = f"{req.method} {req.url.split(Route.BASE)[-1]}"
        try:
            endpoint = next(k for k in RESPONSES if fnmatchcase(request_route, k))
        except StopIteration:
            raise RuntimeError("Bot requested an endpoint we don't have a test for")

        # ignore typing events
        if not fnmatchcase(request_route, "POST /channels/*/typing"):
            await self._request_check_queue.put(req)

        return RESPONSES[endpoint](req.data)

    # helper functions
    def clear(self):
        self._request_check_queue = asyncio.Queue()

    async def drain(self):
        """Waits until all requests have been sent and clears the queue."""
        to_wait = set()
        to_cancel = set()
        for task in asyncio.all_tasks():
            # note: we compare to repr(task) instead of the task's name since this contains information
            # about the function that created the task
            # if a bunch of tests are suddenly failing, this is often the culprit because of task names changing
            if "disnake" in repr(task):  # tasks started by disnake in reply to an event
                to_wait.add(task)
            elif "Message.delete" in repr(task):  # Messagable.send(..., delete_after=x)
                to_cancel.add(task)

        for task in to_cancel:
            task.cancel()

        try:
            await asyncio.wait_for(asyncio.gather(*to_wait), timeout=10)
        except asyncio.TimeoutError:
            log.info(f"Tasks we were waiting on when we timed out: {to_wait!r}")
            raise
        self.clear()

    async def get_request(self):
        try:
            return await asyncio.wait_for(self._request_check_queue.get(), timeout=10)
        except asyncio.TimeoutError as e:
            raise TimeoutError("Timed out waiting for Avrae response") from e

    async def receive_message(self, content: str = None, *, regex: bool = True, dm=False, embed: Embed = None):
        """
        Assert that the bot sends a message, and that it is the message we expect.
        If a regex is passed, this method returns the match object against the content.
        :param content The text or regex to match the message content against
        :param regex Whether to interpret content checking fields as a regex
        :param dm Whether it was a Direct Message that was received or not
        :param embed An embed to check against
        """
        request = await self.get_request()
        channel = TEST_DMCHANNEL_ID if dm else TEST_CHANNEL_ID

        assert request.method == "POST"
        assert request.url.endswith(f"/channels/{channel}/messages")

        return message_content_check(request, content, regex=regex, embed=embed)

    async def receive_edit(self, content: str = None, *, regex: bool = True, dm=False, embed: Embed = None):
        """
        Assert that the bot edits a message, and that it is the message we expect.
        If a regex is passed, this method returns the match object against the content.
        :param content The text or regex to match the message content against
        :param regex Whether to interpret content checking fields as a regex
        :param dm Whether it was a Direct Message that was edited or not
        :param embed An embed to check against
        """
        request = await self.get_request()
        channel = TEST_DMCHANNEL_ID if dm else TEST_CHANNEL_ID

        assert request.method == "PATCH"
        assert request.url.endswith(f"/channels/{channel}/messages/{MESSAGE_ID}")

        return message_content_check(request, content, regex=regex, embed=embed)

    async def receive_delete(self, dm=False):
        """
        Assert that the bot deletes a message.
        """
        request = await self.get_request()
        channel = TEST_DMCHANNEL_ID if dm else TEST_CHANNEL_ID

        assert request.method == "DELETE"
        assert request.url.endswith(f"/channels/{channel}/messages/{MESSAGE_ID}")

    async def receive_pin(self, dm=False):
        """
        Assert that the bot pins a message.
        """
        request = await self.get_request()
        channel = TEST_DMCHANNEL_ID if dm else TEST_CHANNEL_ID

        assert request.method == "PUT"
        assert request.url.endswith(f"/channels/{channel}/pins/{MESSAGE_ID}")

    async def receive_unpin(self, dm=False):
        """
        Assert that the bot unpins a message.
        """
        request = await self.get_request()
        channel = TEST_DMCHANNEL_ID if dm else TEST_CHANNEL_ID

        assert request.method == "DELETE"
        assert request.url.endswith(f"/channels/{channel}/pins/{MESSAGE_ID}")

    async def receive_reaction(self, emoji, dm=False):
        """
        Assert that the bot sends a reaction.

        For unicode emoji, pass the unicode str; otherwise pass the emoji as ``name:id``
        """
        request = await self.get_request()
        channel = TEST_DMCHANNEL_ID if dm else TEST_CHANNEL_ID
        encoded_emoji = urllib.parse.quote(emoji)

        assert request.method == "PUT"
        assert request.url.endswith(f"/channels/{channel}/messages/{MESSAGE_ID}/reactions/{encoded_emoji}/@me")

    def queue_empty(self):
        return self._request_check_queue.empty()


class MockAsyncLaunchDarklyClient:
    def __init__(self):
        self.flag_store = {}

    @contextmanager
    def flags(self, flags: dict):
        """Async context manager that sets the global value of a feature flag in the context."""
        old_flag_store = copy.deepcopy(self.flag_store)
        self.flag_store.update(flags)
        try:
            yield
        finally:
            self.flag_store = old_flag_store

    async def variation(self, key, user, default):
        return self.flag_store.get(key, default)

    def close(self):
        pass
