import random

import discord


class EmbedWithAuthor(discord.Embed):
    """An embed with author image and nickname set."""

    def __init__(self, ctx, **kwargs):
        super(EmbedWithAuthor, self).__init__(**kwargs)
        self.set_author(name=ctx.message.author.display_name, icon_url=ctx.message.author.avatar_url)
        self.colour = random.randint(0, 0xffffff)


class HomebrewEmbedWithAuthor(EmbedWithAuthor):
    """An embed with author image, nickname, and homebrew footer set."""

    def __init__(self, ctx, **kwargs):
        super(HomebrewEmbedWithAuthor, self).__init__(ctx, **kwargs)
        self.set_footer(text="Homebrew content.", icon_url="https://avrae.io/assets/img/homebrew.png")


class EmbedWithCharacter(discord.Embed):
    """An embed with character image and name set."""

    def __init__(self, character, name=True, **kwargs):
        """@:param name: bool - If True, sets author name to character name."""
        super(EmbedWithCharacter, self).__init__(**kwargs)
        if name: self.set_author(name=character.get_name())
        if character.get_setting('embedimage', True):
            self.set_thumbnail(url=character.get_image())
        self.colour = character.get_color()

def add_fields_from_args(embed, _fields):
    """
    Adds fields to an embed.
    :param embed: The embed.
    :param _fields: A list of strings detailing the fields to add, separated by a |.
    :return:
    """
    if type(_fields) == list:
        for f in _fields:
            title = f.split('|')[0] if '|' in f else '\u200b'
            value = "|".join(f.split('|')[1:]) if '|' in f else f
            embed.add_field(name=title, value=value)
    return embed

def add_homebrew_footer(embed):
    embed.set_footer(icon_url="https://avrae.io/assets/img/homebrew.png", text="Homebrew content.")