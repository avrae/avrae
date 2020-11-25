class GameLogEventContext:
    """
    The context in which a game log event occurred. It is convention to pass this to the handler as ``gctx``.
    """

    def __init__(self, bot, event, guild, channel, character=None):
        """
        :type bot: dbot.Avrae
        :type event: ddb.gamelog.events.GameLogEvent
        :type guild: discord.Guild
        :type channel: discord.TextChannel
        :type character: cogs5e.models.character.Character
        """
        self.bot = bot
        self.event = event
        self.guild = guild
        self.channel = channel
        self.character = character
