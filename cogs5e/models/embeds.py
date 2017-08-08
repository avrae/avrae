import random

import discord


class EmbedWithAuthor(discord.Embed):
    """An embed with author image and nickname set."""
    def __init__(self, ctx, **kwargs):
        super(EmbedWithAuthor, self).__init__(**kwargs)
        self.set_author(name=ctx.message.author.display_name, icon_url=ctx.message.author.avatar_url)
        self.colour = random.randint(0, 0xffffff)