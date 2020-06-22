class AliasContext:
    """
    Used to expose some information about the context, like the guild name, channel name, author name, and
    current prefix to alias authors.
    """

    def __init__(self, ctx):
        """
        :type ctx: discord.ext.commands.Context
        """
        self._guild = None if ctx.guild is None else AliasGuild(ctx.guild)
        self._channel = AliasChannel(ctx.channel)
        self._author = AliasAuthor(ctx.author)
        self._prefix = ctx.prefix

    @property
    def guild(self):
        return self._guild

    @property
    def channel(self):
        return self._channel

    @property
    def author(self):
        return self._author

    @property
    def prefix(self):
        return self._prefix


class AliasGuild:
    def __init__(self, guild):
        """
        :type guild: discord.Guild
        """
        self._name = guild.name
        self._id = guild.id

    @property
    def name(self):
        return self._name

    @property
    def id(self):
        return self._id

    def __str__(self):
        return self.name


class AliasChannel:
    def __init__(self, channel):
        """
        :type channel: discord.TextChannel
        """
        self._name = channel.name
        self._id = channel.id
        self._topic = channel.topic

    @property
    def name(self):
        return self._name

    @property
    def id(self):
        return self._id

    @property
    def topic(self):
        return self._topic

    def __str__(self):
        return self.name


class AliasAuthor:
    def __init__(self, author):
        """
        :type author: discord.User
        """
        self._name = author.name
        self._id = author.id
        self._discriminator = author.discriminator
        self._display_name = author.display_name

    @property
    def name(self):
        return self._name

    @property
    def id(self):
        return self._id

    @property
    def discriminator(self):
        return self._discriminator

    @property
    def display_name(self):
        return self._display_name

    def __str__(self):
        return f"{self.name}#{self.discriminator}"
