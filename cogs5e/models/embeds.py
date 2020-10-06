import random

import discord

from utils.functions import trim_str


class EmbedWithAuthor(discord.Embed):
    """An embed with author image and nickname set."""

    def __init__(self, ctx, **kwargs):
        super(EmbedWithAuthor, self).__init__(**kwargs)
        self.set_author(name=ctx.author.display_name, icon_url=ctx.author.avatar_url)
        self.colour = random.randint(0, 0xffffff)


class HomebrewEmbedWithAuthor(EmbedWithAuthor):
    """An embed with author image, nickname, and homebrew footer set."""

    def __init__(self, ctx, **kwargs):
        super(HomebrewEmbedWithAuthor, self).__init__(ctx, **kwargs)
        self.set_footer(text="Homebrew content.", icon_url="https://avrae.io/assets/img/homebrew.png")


class EmbedWithCharacter(discord.Embed):
    """An embed with character image and name set."""

    def __init__(self, character, name=True, image=True, **kwargs):
        """:param name: bool - If True, sets author name to character name.
        :param image: bool - If True, shows character image as thumb if embedimage setting is true."""
        super(EmbedWithCharacter, self).__init__(**kwargs)
        if name: self.set_author(name=character.name)
        if character.get_setting('embedimage', True) and image:
            self.set_thumbnail(url=character.image)
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
            inline = False
            title = f.split('|')[0] if '|' in f else '\u200b'
            value = f.split('|', 1)[1] if '|' in f else f
            if value.endswith('|inline'):
                inline = True
                value = value[:-7]
            embed.add_field(name=title, value=value, inline=inline)
    return embed


def chunk_text(text, max_chunk_size=1024, chunk_on=('\n\n', '\n', '. ', ' '), chunker_i=0):
    """
    Recursively chunks *text* into a list of str, with each element no longer than *max_chunk_size*.
    Prefers splitting on the elements of *chunk_on*, in order.
    """

    if len(text) <= max_chunk_size:  # the chunk is small enough
        return [text]
    if chunker_i >= len(chunk_on):  # we have no more preferred chunk_on characters
        # optimization: instead of merging a thousand characters, just use list slicing
        return [text[:max_chunk_size],
                *chunk_text(text[max_chunk_size:], max_chunk_size, chunk_on, chunker_i + 1)]

    # split on the current character
    chunks = []
    split_char = chunk_on[chunker_i]
    for chunk in text.split(split_char):
        chunk = f"{chunk}{split_char}"
        if len(chunk) > max_chunk_size:  # this chunk needs to be split more, recurse
            chunks.extend(chunk_text(chunk, max_chunk_size, chunk_on, chunker_i + 1))
        elif chunks and len(chunk) + len(chunks[-1]) <= max_chunk_size:  # this chunk can be merged
            chunks[-1] += chunk
        else:
            chunks.append(chunk)

    return chunks


def get_long_field_args(text, title, inline=False, chunk_size=1024):
    """Returns a list of dicts (to pass as kwargs) given a long text."""
    chunks = chunk_text(text, chunk_size)
    if not chunks:
        return []
    out = [{"name": title, "value": chunks[0].strip(), "inline": inline}]
    for chunk in chunks[1:]:
        out.append({"name": "** **", "value": chunk.strip(), "inline": inline})
    return out


def set_maybe_long_desc(embed, desc):
    """
    Sets a description that might be longer than 2048 characters but is less than 5000 characters.
    :param embed: The embed to add the description (and potentially fields) to.
    :param str desc: The description to add. Will overwrite existing description.
    """
    desc = chunk_text(trim_str(desc, 5000))
    embed.description = ''.join(desc[:2]).strip()
    for piece in desc[2:]:
        embed.add_field(name="** **", value=piece.strip(), inline=False)


def add_fields_from_long_text(embed, field_name, text):
    """
    Splits a long text across multiple fields if needed.
    :param embed: The embed to add the fields to.
    :param str text: The text of the fields to add. Will append to existing fields.
    :param str field_name: The name of the first field to add.
    :returns int: The number of fields added.
    """
    fields = get_long_field_args(text, field_name)
    for field in fields:
        embed.add_field(**field)
    return len(fields)
