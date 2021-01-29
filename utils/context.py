import discord
from discord.ext.commands import Context

from cogs5e.models.character import Character
from cogs5e.models.initiative import Combat

_sentinel = object()


class AvraeContext(Context):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._character = _sentinel
        self._combat = _sentinel

    async def get_character(self):
        """
        Gets the character active in this context.

        :raises NoCharacter: If the context has no character (author has none active).
        :rtype: Character
        """
        if self._character is not _sentinel:
            return self._character
        character = await Character.from_ctx(self)
        self._character = character
        return character

    async def get_combat(self):
        """
        Gets the combat active in this context.

        :raises CombatNotFound: If the context has no character (author has none active).
        :rtype: Combat
        """
        if self._combat is not _sentinel:
            return self._combat
        combat = await Combat.from_ctx(self)
        self._combat = combat
        return combat

    def to_alias_dict(self):
        """Returns a dict representing this context, for use in Draconic."""
        guild = None
        if self.guild:
            guild = {
                'id': self.guild.id,
                'name': self.guild.name
            }

        channel = {
            'name': str(self.channel),
            'id': self.channel.id,
            'topic': self.channel.topic if not isinstance(self.channel, discord.DMChannel) else None,
            'category': None
        }
        if (category := getattr(channel, 'category', None)) is not None:
            channel['category'] = {
                'id': category.id,
                'name': category.name
            }

        author = {
            'id': self.author.id,
            'name': self.author.name,
            'discriminator': self.author.discriminator,
            'display_name': self.author.display_name
        }

        return {
            'guild': guild,
            'channel': channel,
            'author': author,
            'prefix': self.prefix,
            'invoked_with': self.invoked_with
        }
