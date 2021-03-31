import abc
import asyncio


class LiveIntegration(abc.ABC):
    """Interface defining how to sync character resources with upstream. Tied to the character object's lifecycle."""

    def __init__(self, character):
        self.character = character
        self._should_sync_hp = False
        self._should_sync_slots = False
        self._should_sync_ccs = {}
        self._should_sync_death_saves = False
        self._ctx = None  # set for the duration of a commit, use for access to bot stuff

    async def _do_sync_hp(self):
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
        self._should_sync_ccs = {}
        self._should_sync_death_saves = False

    async def commit(self, ctx):
        """
        Called when the character is committed. Should fire all pending sync tasks.
        Sets self._ctx for the duration of the commit.
        """
        self._ctx = ctx
        try:
            to_await = []
            if self._should_sync_hp:
                to_await.append(self._do_sync_hp())
            if self._should_sync_slots:
                to_await.append(self._do_sync_slots())
            if self._should_sync_death_saves:
                to_await.append(self._do_sync_death_saves())
            for cc in self._should_sync_ccs.values():
                to_await.append(self._do_sync_consumable(cc))
            await asyncio.gather(*to_await)
            self.clear()
        finally:
            self._ctx = None
