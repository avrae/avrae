class AliasContext:
    """
    Used to expose some information about the context, like the guild name, channel name, author name, and
    current prefix to alias authors.

    You can access this in an alias by using the ``ctx`` local.
    """

    def __init__(self, guild, channel, author, prefix, invoked_with):
        self._guild = guild
        self._channel = channel
        self._author = author
        self._prefix = prefix
        self._alias = invoked_with

    @classmethod
    def from_dict(cls, d):
        return cls(
            guild=AliasGuild.from_dict(d['guild']) if d['guild'] is not None else None,
            channel=AliasChannel.from_dict(d['channel']),
            author=AliasAuthor.from_dict(d['author']),
            prefix=d['prefix'],
            invoked_with=d['invoked_with']
        )

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
        return f"<AliasContext guild={self.guild} channel={self.channel} author={self.author} prefix={self.prefix} " \
               f"alias={self.alias}>"


class AliasGuild:
    """
    Represents the Discord guild (server) an alias was invoked in.
    """

    def __init__(self, id: int, name: str):
        self._id = id
        self._name = name

    @classmethod
    def from_dict(cls, d):
        return cls(id=d['id'], name=d['name'])

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


class AliasChannel:
    """
    Represents the Discord channel an alias was invoked in.
    """

    def __init__(self, id: int, name: str, topic, category):
        """
        :type topic: str or None
        :type category: AliasCategory or None
        """
        self._name = name
        self._id = id
        self._topic = topic
        self._category = category

    @classmethod
    def from_dict(cls, d):
        return cls(
            id=d['id'],
            name=d['name'],
            topic=d['topic'],
            category=AliasCategory.from_dict(d['category']) if d['category'] is not None else None
        )

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
        The channel topic.

        :rtype: str
        """
        return self._topic

    @property
    def category(self):
        """
        The category of the channel the alias was run in

        :rtype: :class:`~aliasing.api.context.AliasCategory` or None
        """
        return self._category

    def __str__(self):
        return self.name


class AliasAuthor:
    """
    Represents the Discord user who invoked an alias.
    """

    def __init__(self, id: int, name: str, discriminator: str, display_name: str):
        self._name = name
        self._id = id
        self._discriminator = discriminator
        self._display_name = display_name

    @classmethod
    def from_dict(cls, d):
        return cls(id=d['id'], name=d['name'], discriminator=d['discriminator'], display_name=d['display_name'])

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


class AliasCategory:
    """
    Represents the category of the Discord channel an alias was invoked in.
    """

    def __init__(self, id: int, name: str):
        self._name = name
        self._id = id

    @classmethod
    def from_dict(cls, d):
        return cls(id=d['id'], name=d['name'])

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
