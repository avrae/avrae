import discord
from discord.ext.commands import HelpCommand


class EmbedPaginator:
    EMBED_MAX = 6000
    EMBED_FIELD_MAX = 1024
    EMBED_DESC_MAX = 2048
    EMBED_TITLE_MAX = 256

    def __init__(self, **embed_options):
        self._current_field_name = ''
        self._current_field_inline = False
        self._current_field = []
        self._field_count = 0
        self._embed_count = 0

        self._default_embed_options = embed_options
        self._embeds = [discord.Embed(**embed_options)]

    def add_title(self, value):
        """
        Adds a title to the embed. This appears before any fields, and will raise a ValueError if the current
        embed can't fit the value.
        """
        if len(value) > self.EMBED_TITLE_MAX or len(value) + self._embed_count > self.EMBED_MAX:
            raise ValueError("The current embed cannot fit this title.")

        self._embeds[-1].title = value
        self._embed_count += len(value)

    def add_description(self, value):
        """
        Adds a description to the embed. This appears before any fields, and will raise a ValueError if the current
        embed can't fit the value.
        """
        if len(value) > self.EMBED_DESC_MAX or len(value) + self._embed_count > self.EMBED_MAX:
            raise ValueError("The current embed cannot fit this description.")

        self._embeds[-1].description = value
        self._embed_count += len(value)

    def add_field(self, name='', value='', inline=False):
        """Add a new field to the help embed."""
        if len(value) > self.EMBED_FIELD_MAX or len(name) > self.EMBED_TITLE_MAX:
            raise ValueError("This value is too large to store in an embed field.")

        if self._current_field:
            self.close_field()

        self._field_count += len(value) + 1

        self._current_field_name = name
        self._current_field_inline = inline
        self._current_field.append(value)

    def extend_field(self, value):
        """Add a line of text to the last field in the help embed."""
        if len(value) > self.EMBED_FIELD_MAX:
            raise ValueError("This value is too large to store in an embed field.")

        if self._field_count + len(value) + 1 > self.EMBED_FIELD_MAX:
            self.close_field()
            self.add_field("** **", value)  # this creates a field with no title to look somewhat seamless
        else:
            self._field_count += len(value) + 1
            self._current_field.append(value)

    def close_field(self):
        """Terminate the current field and write it to the last embed."""
        value = "\n".join(self._current_field)

        if self._embed_count + len(value) + len(self._current_field_name) > self.EMBED_MAX:
            self.close_embed()

        self._embeds[-1].add_field(name=self._current_field_name, value=value, inline=self._current_field_inline)
        self._embed_count += len(value) + len(self._current_field_name)

        self._current_field_name = ''
        self._current_field_inline = False
        self._current_field = []
        self._field_count = 0

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
        return self._embeds

    def __repr__(self):
        fmt = '<EmbedPaginator _current_field_name={0._current_field_name} _field_count={0._field_count} ' \
              '_embed_count={0._embed_count}>'
        return fmt.format(self)


class AvraeHelp(HelpCommand):
    def __init__(self, **options):
        super().__init__(**options)
        self.embed_paginator = EmbedPaginator()

    def get_ending_note(self):
        """Returns help command's ending note. This is mainly useful to override for i18n purposes."""
        command_name = self.invoked_with
        return "An underlined command signifies that the command has subcommands.\n" \
               "Type {0}{1} command for more info on a command.\n" \
               "You can also type {0}{1} category for more info on a category.".format(self.clean_prefix, command_name)

    def add_indented_commands(self, commands, *, heading, max_size=None):  # todo
        """Indents a list of commands after the specified heading.

        The formatting is added to the :attr:`paginator`.

        The default implementation is the command name indented by
        :attr:`indent` spaces, padded to ``max_size`` followed by
        the command's :attr:`Command.short_doc` and then shortened
        to fit into the :attr:`width`.

        Parameters
        -----------
        commands: Sequence[:class:`Command`]
            A list of commands to indent for output.
        heading: :class:`str`
            The heading to add to the output. This is only added
            if the list of commands is greater than 0.
        max_size: Optional[:class:`int`]
            The max size to use for the gap between indents.
            If unspecified, calls :meth:`get_max_size` on the
            commands parameter.
        """

        if not commands:
            return

        self.paginator.add_line(heading)
        max_size = max_size or self.get_max_size(commands)

        get_width = discord.utils._string_width
        for command in commands:
            name = command.name
            width = max_size - (get_width(name) - len(name))
            entry = '{0}{1:<{width}} {2}'.format(self.indent * ' ', name, command.short_doc, width=width)
            self.paginator.add_line(self.shorten_text(entry))

    async def send(self):
        """A helper utility to send the page output from :attr:`paginator` to the destination."""
        destination = self.get_destination()
        for embed in self.embed_paginator.embeds:
            await destination.send(embed=embed)
        if destination is not self.context.channel:  # todo
            await self.context.channel.send("I have sent help to your PMs.")

    def add_command_formatting(self, command):  # todo
        """A utility function to format the non-indented block of commands and groups.

        Parameters
        ------------
        command: :class:`Command`
            The command to format.
        """

        if command.description:
            self.paginator.add_line(command.description, empty=True)

        signature = self.get_command_signature(command)
        self.paginator.add_line(signature, empty=True)

        if command.help:
            try:
                self.paginator.add_line(command.help, empty=True)
            except RuntimeError:
                for line in command.help.splitlines():
                    self.paginator.add_line(line)
                self.paginator.add_line()

    # ===== HelpCommand overrides =====
    def get_destination(self):
        return self.context.author

    async def prepare_help_command(self, ctx, command=None):
        await super().prepare_help_command(ctx, command)

    async def send_bot_help(self, mapping):  # todo here and below
        ctx = self.context
        bot = ctx.bot

        if bot.description:
            # <description> portion
            self.paginator.add_line(bot.description, empty=True)

        no_category = '\u200b{0.no_category}:'.format(self)

        def get_category(command, *, no_category=no_category):
            cog = command.cog
            return cog.qualified_name + ':' if cog is not None else no_category

        filtered = await self.filter_commands(bot.commands, sort=True, key=get_category)
        max_size = self.get_max_size(filtered)
        to_iterate = itertools.groupby(filtered, key=get_category)

        # Now we can add the commands to the page.
        for category, commands in to_iterate:
            commands = sorted(commands, key=lambda c: c.name) if self.sort_commands else list(commands)
            self.add_indented_commands(commands, heading=category, max_size=max_size)

        note = self.get_ending_note()
        if note:
            self.paginator.add_line()
            self.paginator.add_line(note)

        await self.send()

    async def send_command_help(self, command):
        self.add_command_formatting(command)
        self.paginator.close_page()
        await self.send()

    async def send_group_help(self, group):
        self.add_command_formatting(group)

        filtered = await self.filter_commands(group.commands, sort=self.sort_commands)
        self.add_indented_commands(filtered, heading=self.commands_heading)

        if filtered:
            note = self.get_ending_note()
            if note:
                self.paginator.add_line()
                self.paginator.add_line(note)

        await self.send()

    async def send_cog_help(self, cog):
        if cog.description:
            self.paginator.add_line(cog.description, empty=True)

        filtered = await self.filter_commands(cog.get_commands(), sort=self.sort_commands)
        self.add_indented_commands(filtered, heading=self.commands_heading)

        note = self.get_ending_note()
        if note:
            self.paginator.add_line()
            self.paginator.add_line(note)

        await self.send()


help_command = AvraeHelp()
