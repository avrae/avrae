import random

import discord


class EmbedWithAuthor(discord.Embed):
    """An embed with author image and nickname set."""
    def __init__(self, ctx, **kwargs):
        super(EmbedWithAuthor, self).__init__(**kwargs)
        self.set_author(name=ctx.message.author.display_name, icon_url=ctx.message.author.avatar_url)
        self.colour = random.randint(0, 0xffffff)

class EmbedWithCharacter(discord.Embed):
    """An embed with character image and name set."""
    def __init__(self, character, name=True, **kwargs):
        """@:param name: bool - If True, sets author name to character name."""
        super(EmbedWithCharacter, self).__init__(**kwargs)
        if name: self.set_author(name=character.get_name())
        if character.get_setting('embedimage', True):
            self.set_thumbnail(url=character.get_image())
        self.colour = character.get_color()