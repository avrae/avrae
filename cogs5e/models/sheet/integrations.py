import abc
import asyncio


class LiveIntegration(abc.ABC):
    def __init__(self, character):
        self.character = character
        self._hp_sync_task = None
        self._slots_sync_task = None
        self._cc_sync_tasks = {}
        self._death_save_sync_task = None

    async def _do_sync_hp(self):
        raise NotImplementedError

    async def _do_sync_slots(self):
        raise NotImplementedError

    async def _do_sync_consumable(self, consumable):
        raise NotImplementedError

    async def _do_sync_death_saves(self):
        raise NotImplementedError

    def sync_hp(self):
        """Create the HP sync task."""
        self._hp_sync_task = self._do_sync_hp()

    def sync_slots(self):
        """Create the spell slot sync task."""
        self._slots_sync_task = self._do_sync_slots()

    def sync_consumable(self, consumable):
        """
        Create the CC sync task (extra care should be taken to ensure that if the same CC is synced twice, it only
        creates one task).

        :type consumable: cogs5e.models.sheet.player.CustomCounter
        """
        if consumable.live_id is None:
            return
        self._cc_sync_tasks[consumable.live_id] = self._do_sync_consumable(consumable)

    def sync_death_saves(self):
        """Creates the death save sync task."""
        self._death_save_sync_task = self._do_sync_death_saves()

    def clear(self):
        self._hp_sync_task = None
        self._slots_sync_task = None
        self._cc_sync_tasks = {}
        self._death_save_sync_task = None

    async def commit(self):
        """Called when the character is committed. Should fire all pending sync tasks."""
        to_await = []
        if self._hp_sync_task is not None:
            to_await.append(self._hp_sync_task)
        if self._slots_sync_task is not None:
            to_await.append(self._slots_sync_task)
        if self._death_save_sync_task is not None:
            to_await.append(self._death_save_sync_task)
        to_await.extend(self._cc_sync_tasks.values())
        await asyncio.gather(*to_await)
        self.clear()
