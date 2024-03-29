import abc
import asyncio
import logging

log = logging.getLogger(__name__)


class LiveIntegration(abc.ABC):
    """Interface defining how to sync character resources with upstream. Tied to the character object's lifecycle."""

    _inflight_tasks = dict()  # map: key -> task to cancel a task if a new one comes along

    def __init__(self, character):
        self.character = character
        self._key = character.upstream
        self._should_sync_hp = False
        self._should_sync_coins = False
        self._should_sync_slots = False
        self._should_sync_ccs = {}
        self._should_sync_death_saves = False
        self._ctx = None  # set for the duration of a commit, use for access to bot stuff

    async def _do_sync_hp(self):
        raise NotImplementedError

    async def _do_sync_coins(self):
        raise NotImplementedError

    async def _do_sync_slots(self):
        raise NotImplementedError

    async def _do_sync_consumable(self, consumable):
        """:type consumable: cogs5e.models.sheet.player.CustomCounter"""
        raise NotImplementedError

    async def _do_sync_death_saves(self):
        raise NotImplementedError

    def sync_hp(self):
        """Mark that HP should be synced on commit."""
        self._should_sync_hp = True

    def sync_coins(self):
        """Mark that Currency should be synced on commit."""
        self._should_sync_coins = True

    def sync_slots(self):
        """Mark that spell slots should be synced on commit."""
        self._should_sync_slots = True

    def sync_consumable(self, consumable):
        """
        Mark that a given CC should be synced on commit.

        :type consumable: cogs5e.models.sheet.player.CustomCounter
        """
        if consumable.live_id is None:
            return
        self._should_sync_ccs[consumable.live_id] = consumable

    def sync_death_saves(self):
        """Mark that death saves should be synced on commit."""
        self._should_sync_death_saves = True

    def clear(self):
        self._should_sync_hp = False
        self._should_sync_slots = False
        self._should_sync_coins = False
        self._should_sync_ccs = {}
        self._should_sync_death_saves = False

    def _collect_awaitables(self):
        """Returns a list of coroutines to await to complete the sync."""
        to_await = []
        if self._should_sync_hp:
            to_await.append(self._do_sync_hp())
        if self._should_sync_coins:
            to_await.append(self._do_sync_coins())
        if self._should_sync_slots:
            to_await.append(self._do_sync_slots())
        if self._should_sync_death_saves:
            to_await.append(self._do_sync_death_saves())
        for cc in self._should_sync_ccs.values():
            to_await.append(self._do_sync_consumable(cc))
        return to_await

    async def _run_awaitables(self, awaitables):
        """
        Submit the awaitables to the event loop and return their results.
        This is a separate method to allow subclasses to add lower-level error handling and whatnot.
        """
        return await asyncio.gather(*awaitables)

    async def commit(self, ctx):
        """
        Called when the character is committed. Should fire all pending sync tasks.
        Sets self._ctx for the duration of the commit.
        """
        self._ctx = ctx
        try:
            to_await = self._collect_awaitables()
            await self._run_awaitables(to_await)
            self.clear()
        except asyncio.CancelledError:
            pass
        except Exception:
            log.exception("Error in character sync:")
            self._inflight_tasks.pop(self._key, None)
        else:
            self._inflight_tasks.pop(self._key, None)
        finally:
            self._ctx = None

    def commit_soon(self, ctx):
        """Creates a task to commit any updates in this sync instance soon. May cancel a previous pending sync task."""
        # if a task to sync this character already exists, cancel it
        # since this is sync, it operates atomically on _inflight_tasks, so two commit_soon's running on the same
        # instance cannot be in contention
        try:
            self._inflight_tasks.pop(self._key).cancel()
        except KeyError:
            pass
        task = asyncio.create_task(self.commit(ctx))
        self._inflight_tasks[self._key] = task
