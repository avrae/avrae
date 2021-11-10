import random

import discord

from utils.functions import chunk_text, trim_str

MAX_NUM_FIELDS = 25


class EmbedWithAuthor(discord.Embed):
    """An embed with author image and nickname set."""

    def __init__(self, ctx, **kwargs):
        """
        :type ctx: utils.context.AvraeContext
        """
        super().__init__(**kwargs)
        self.set_author(name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)
        self.colour = random.randint(0, 0xffffff)


class HomebrewEmbedWithAuthor(EmbedWithAuthor):
    """An embed with author image, nickname, and homebrew footer set."""

    def __init__(self, ctx, **kwargs):
        super().__init__(ctx, **kwargs)
        self.set_footer(text="Homebrew content.", icon_url="https://avrae.io/assets/img/homebrew.png")


class EmbedWithCharacter(discord.Embed):
    """An embed with character image and name set."""

    def __init__(self, character, name=True, image=True, **kwargs):
        """:param name: bool - If True, sets author name to character name.
        :param image: bool - If True, shows character image as thumb if embedimage setting is true."""
        super().__init__(**kwargs)
        if name: self.set_author(name=character.name)
        if character.options.embed_image and image:
            self.set_thumbnail(url=character.image)
        self.colour = character.get_color()


class EmbedPaginator:
    EMBED_MAX = 6000
    EMBED_FIELD_MAX = 1024
    EMBED_DESC_MAX = 4096
    EMBED_TITLE_MAX = 256
    CONTINUATION_FIELD_TITLE = '** **'

    def __init__(self, first_embed=None, copy_kwargs=('colour',), **embed_options):
        self._current_field_name = ''
        self._current_field_inline = False
        self._current_field = []
        self._field_count = 0

        self._footer_url = None
        self._footer_text = None

        if first_embed is None:
            first_embed = discord.Embed(**embed_options)

        self._embed_count = len(first_embed)
        self._default_embed_options = {c: getattr(first_embed, c) for c in copy_kwargs if hasattr(first_embed, c)}
        self._default_embed_options.update(embed_options)
        self._embeds = [first_embed]

    @property
    def _current(self):
        return self._embeds[-1]

    def add_title(self, value):
        """
        Adds a title to the embed. This appears before any fields, and will raise a ValueError if the current
        embed can't fit the value. Note that this adds the title to the current embed, so you should call this
        first to add it to the first embed.
        """
        if len(value) > self.EMBED_TITLE_MAX or len(value) + self._embed_count > self.EMBED_MAX:
            raise ValueError("The current embed cannot fit this title.")

        self._current.title = value
        self._embed_count += len(value)

    def add_description(self, value):
        """
        Adds a description to the embed. This appears before any fields, and will raise a ValueError if the current
        embed can't fit the value. Note that this adds the description to the current embed, so you should call this
        first to add it to the first embed.
        """
        if len(value) > self.EMBED_DESC_MAX or len(value) + self._embed_count > self.EMBED_MAX:
            raise ValueError("The current embed cannot fit this description.")

        self._current.description = value
        self._embed_count += len(value)

    def add_field(self, name='', value='', inline=False):
        """Add a new field to the current embed."""
        if len(name) > self.EMBED_TITLE_MAX:
            raise ValueError("This value is too large to store in an embed field.")

        if self._current_field:
            self.close_field()

        self._current_field_name = name
        self._current_field_inline = inline
        self.extend_field(value)

    def extend_field(self, value):
        """Add a line of text to the last field in the current embed."""
        if not value:
            return
        chunks = chunk_text(value, max_chunk_size=self.EMBED_FIELD_MAX - 1)

        # if the first chunk is too large to fit in the current field, start a new one
        if self._field_count + len(chunks[0]) + 1 > self.EMBED_FIELD_MAX:
            self.close_field()
            self._current_field_name = self.CONTINUATION_FIELD_TITLE

        # add the rest of the chunks
        for i, chunk in enumerate(chunks):
            self._field_count += len(value) + 1
            self._current_field.append(chunk)
            if i < len(chunks) - 1:  # if not last chunk, add the chunk in a new field
                self.close_field()
                self._current_field_name = self.CONTINUATION_FIELD_TITLE

    def close_field(self):
        """Terminate the current field and write it to the last embed."""
        value = "\n".join(self._current_field)

        if self._embed_count + len(value) + len(self._current_field_name) > self.EMBED_MAX:
            self.close_embed()

        self._current.add_field(name=self._current_field_name, value=value, inline=self._current_field_inline)
        self._embed_count += len(value) + len(self._current_field_name)

        self._current_field_name = ''
        self._current_field_inline = False
        self._current_field = []
        self._field_count = 0

    def set_footer(self, icon_url=None, value=None):
        """Sets the footer on the final embed."""
        self._footer_url = icon_url
        self._footer_text = value

    def close_footer(self):
        """Write the footer to the last embed."""
        current_count = self._embed_count
        kwargs = {}
        if self._footer_url:
            current_count += len(self._footer_url)
            kwargs['icon_url'] = self._footer_url
        if self._footer_text:
            current_count += len(self._footer_text)
            kwargs['text'] = self._footer_text
        if current_count > self.EMBED_MAX:
            self.close_embed()

        # this check is here because of a bug in discord.py 1.7.3 that causes a KeyError in len(embed) if set_footer()
        # is called without a text kwarg (we use len() to run assertions in tests)
        if kwargs:
            self._current.set_footer(**kwargs)

    def close_embed(self):
        """Terminate the current embed and create a new one."""
        self._embeds.append(discord.Embed(**self._default_embed_options))
        self._embed_count = 0

    def __len__(self):
        total = sum(len(e) for e in self._embeds)
        return total + self._embed_count

    @property
    def embeds(self):
        """Returns the rendered list of embeds."""
        if self._field_count:
            self.close_field()
        self.close_footer()
        return self._embeds

    async def send_to(self, destination, **kwargs):
        for embed in self.embeds:
            await destination.send(embed=embed, **kwargs)

    def __repr__(self):
        return f'<EmbedPaginator _current_field_name={self._current_field_name} _field_count={self._field_count} ' \
               f'_embed_count={self._embed_count}>'


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
