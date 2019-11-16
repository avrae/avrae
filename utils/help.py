import itertools

import discord
from discord.ext.commands import Group, HelpCommand


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
        self.in_dms = True

    def get_ending_note(self):
        """Returns help command's ending note. This is mainly useful to override for i18n purposes."""
        command_name = self.invoked_with
        return "An underlined command signifies that the command has subcommands.\n" \
               "Type {0}{1} <command> for more info on a command.\n" \
               "You can also type {0}{1} <category> for more info on a category.".format(self.clean_prefix,
                                                                                         command_name)

    def add_commands(self, commands, *, heading):
        """Adds a list of formatted commands under a field title."""
        if not commands:
            return

        self.embed_paginator.add_field(name=heading)

        for command in commands:
            if isinstance(command, Group):
                name = f"**__{command.name}__**"
            else:
                name = f"**{command.name}**"
            entry = f"{name} - {command.short_doc}"
            self.embed_paginator.extend_field(entry)

    async def send(self):
        """A helper utility to send the page output from :attr:`paginator` to the destination."""
        destination = self.get_destination()
        for embed in self.embed_paginator.embeds:
            await destination.send(embed=embed)

        if not isinstance(self.context.channel, discord.DMChannel) and self.in_dms:
            await self.context.channel.send("I have sent help to your PMs.")

    def add_command_formatting(self, command):
        """A utility function to format the non-indented block of commands and groups.

        Parameters
        ------------
        command: :class:`Command`
            The command to format.
        """

        signature = self.get_command_signature(command)
        self.embed_paginator.add_field(name=signature)

        if command.description:
            self.embed_paginator.extend_field(command.description)

        if command.help:
            try:
                self.embed_paginator.extend_field(command.help)
            except ValueError:
                for line in command.help.splitlines():
                    self.embed_paginator.extend_field(line)

    # ===== HelpCommand overrides =====
    async def command_callback(self, ctx, *, command=None):
        if command and command.endswith("-here"):
            command = command[:-5].strip() or None
            self.in_dms = False
        return await super(AvraeHelp, self).command_callback(ctx, command=command)

    def get_destination(self):
        if self.in_dms:
            return self.context.author
        return self.context.channel

    async def send_bot_help(self, mapping):
        ctx = self.context
        bot = ctx.bot

        if bot.description:
            # <description> portion
            self.embed_paginator.add_description(bot.description)

        no_category = '\u200bUncategorized'

        def get_category(command):
            cog = command.cog
            return cog.qualified_name if cog is not None else no_category

        filtered = await self.filter_commands(bot.commands, sort=True, key=get_category)
        to_iterate = itertools.groupby(filtered, key=get_category)

        # Now we can add the commands to the page.
        for category, commands in to_iterate:
            commands = sorted(commands, key=lambda c: c.name)
            self.add_commands(commands, heading=category)

        note = self.get_ending_note()
        if note:
            self.embed_paginator.add_field("More Help", note)

        await self.send()

    async def send_command_help(self, command):
        self.add_command_formatting(command)
        await self.send()

    async def send_group_help(self, group):
        self.add_command_formatting(group)

        filtered = await self.filter_commands(group.commands, sort=True)
        self.add_commands(filtered, heading="Subcommands")

        if filtered:
            note = self.get_ending_note()
            if note:
                self.embed_paginator.add_field("More Help", note)

        await self.send()

    async def send_cog_help(self, cog):
        if cog.description:
            self.embed_paginator.add_description(cog.description)

        filtered = await self.filter_commands(cog.get_commands(), sort=True)
        self.add_commands(filtered, heading="Commands")

        note = self.get_ending_note()
        if note:
            self.embed_paginator.add_field("More Help", note)

        await self.send()


help_command = AvraeHelp(verify_checks=False,  # allows guild-only commands to be shown in PMs
                         command_attrs=dict(help="Shows the help for the bot or a specific command.\n"
                                                 "__Valid Arguments__\n"
                                                 "-here - Sends help to the channel instead of PMs.",
                                            brief="Shows this message."))
