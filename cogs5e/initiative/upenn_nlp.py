import disnake

from .combat import Combat


class NLPRecorder:
    def __init__(self, bot):
        self.bot = bot

    async def on_combat_start(self, combat: Combat):
        """
        Called with the just-started combat instance after a combat is started in a guild with NLP recording enabled.
        """
        pass

    async def on_guild_message(self, message: disnake.Message):
        """
        Called on every message in a guild channel. If the guild has not opted in to NLP recording, does nothing.
        """
        # is the channel currently being recorded?
        pass

    async def on_combat_commit(self, combat: Combat):
        """
        Called each time a combat that is being recorded is committed.
        """
        pass

    async def on_combat_end(self, combat: Combat):
        """
        Called each time a combat that is being recorded ends.
        """
        pass
