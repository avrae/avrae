import discord


class AliasContext:
    """
    Used to expose some information about the context, like the guild name, channel name, author name, and
    current prefix to alias authors.

    You can access this in an alias by using the ``ctx`` local.
    """

    def __init__(self, ctx):
        """
        :type ctx: discord.ext.commands.Context
        """
        self._guild = None if ctx.guild is None else AliasGuild(ctx.guild)
        self._channel = AliasChannel(ctx.channel)
        self._author = AliasAuthor(ctx.author)
        self._prefix = ctx.prefix
        self._alias = ctx.invoked_with

    @property
    def guild(self):
        """
        The discord guild (server) the alias was run in, or None if the alias was run in DMs.

        :rtype: :class:`~aliasing.api.context.AliasGuild` or None
        """
        return self._guild

    @property
    def channel(self):
        """
        The channel the alias was run in.

        :rtype: :class:`~aliasing.api.context.AliasChannel`
        """
        return self._channel

    @property
    def author(self):
        """
        The user that ran the alias.

        :rtype: :class:`~aliasing.api.context.AliasAuthor`
        """
        return self._author

    @property
    def prefix(self):
        """
        The prefix used to run the alias.

        :rtype: str
        """
        return self._prefix

    @property
    def alias(self):
        """
        The name the alias was invoked with.
        Note: When used in a base command, this will return the deepest sub-command, but when used in an alias it will
        return the base command.

        >>> !test {{ctx.alias}}
        'test'

        :rtype: str
        """
        return self._alias

    def __repr__(self):
        return f"<{self.__class__.__name__} guild={self.guild!r} channel={self.channel!r} author={self.author!r} " \
               f"prefix={self.prefix!r} alias={self.alias!r}>"


class AliasGuild:
    """
    Represents the Discord guild (server) an alias was invoked in.
    """

    def __init__(self, guild):
        """
        :type guild: discord.Guild
        """
        self._name = guild.name
        self._id = guild.id

    @property
    def name(self):
        """
        The name of the guild.

        :rtype: str
        """
        return self._name

    @property
    def id(self):
        """
        The ID of the guild.

        :rtype: int
        """
        return self._id

    def __str__(self):
        return self.name

    def __repr__(self):
        return f"<{self.__class__.__name__} name={self.name!r} id={self.id!r}>"


class AliasChannel:
    """
    Represents the Discord channel an alias was invoked in.
    """

    def __init__(self, channel):
        """
        :type channel: discord.TextChannel or discord.DMChannel or discord.Thread
        """
        self._name = str(channel)
        self._id = channel.id
        self._topic = getattr(channel, 'topic', None)
        self._category = AliasCategory(channel.category) if getattr(channel, 'category', None) is not None else None
        self._parent = AliasChannel(channel.parent) if isinstance(channel, discord.Thread) else None

    @property
    def name(self):
        """
        The name of the channel, not including the preceding hash (#).

        :rtype: str
        """
        return self._name

    @property
    def id(self):
        """
        The ID of the channel.

        :rtype: int
        """
        return self._id

    @property
    def topic(self):
        """
        The channel topic. This will be None if the channel is a direct message or thread.

        :rtype: str or None
        """
        return self._topic

    @property
    def category(self):
        """
        The category of the channel the alias was run in

        :rtype: :class:`~aliasing.api.context.AliasCategory` or None
        """
        return self._category

    @property
    def parent(self):
        """
        If this channel is a thread, the thread's parent channel, or None otherwise.

        :rtype: :class:`~aliasing.api.context.AliasChannel` or None
        """
        return self._parent

    def __str__(self):
        return self.name

    def __repr__(self):
        return f"<{self.__class__.__name__} name={self.name!r} id={self.id!r}>"


class AliasAuthor:
    """
    Represents the Discord user who invoked an alias.
    """

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
        """
        The user's username (not including the discriminator).

        :rtype: str
        """
        return self._name

    @property
    def id(self):
        """
        The user's ID.

        :rtype: int
        """
        return self._id

    @property
    def discriminator(self):
        """
        The user's discriminator (number after the hash).

        :rtype: str
        """
        return self._discriminator

    @property
    def display_name(self):
        """
        The user's display name - nickname if applicable, otherwise same as their name.

        :rtype: str
        """
        return self._display_name

    def __str__(self):
        return f"{self.name}#{self.discriminator}"

    def __repr__(self):
        return f"<{self.__class__.__name__} name={self.name!r} id={self.id!r}>"


class AliasCategory:
    """
    Represents the category of the Discord channel an alias was invoked in.
    """

    def __init__(self, category):
        """
        :type channel: discord.ChannelCategory
        """
        self._name = str(category)
        self._id = category.id

    @property
    def name(self):
        """
        The name of the category

        :rtype: str
        """
        return self._name

    @property
    def id(self):
        """
        The ID of the category.

        :rtype: int
        """
        return self._id

    def __str__(self):
        return self.name

    def __repr__(self):
        return f"<{self.__class__.__name__} name={self.name!r} id={self.id!r}>"
