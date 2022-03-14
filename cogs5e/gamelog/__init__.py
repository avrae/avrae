from .character import CharacterHandler
from .cog import GameLog
from .dice import DiceHandler


def _create_event_handlers(bot):
    return (DiceHandler(bot), CharacterHandler(bot))


def setup(bot):
    event_handlers = _create_event_handlers(bot)
    bot.add_cog(GameLog(bot, event_handlers))
