import itertools
import re

import disnake
from disnake.ext.commands import Group, HelpCommand

import aliasing.errors
import aliasing.helpers
import aliasing.personal
from cogs5e.models.embeds import EmbedPaginator
from utils.constants import HOMEBREW_ICON
from utils.functions import user_from_id


class AvraeHelp(HelpCommand):
    def __init__(self, **options):
        super().__init__(**options)
        self.embed_paginator = EmbedPaginator(colour=disnake.Colour.blurple())
        self.in_dms = True

    def get_ending_note(self):
        """Returns help command's ending note. This is mainly useful to override for i18n purposes."""
        command_name = self.invoked_with
        return (
            "An underlined command signifies that the command has subcommands.\n"
            f"Type {self.context.clean_prefix}{command_name} <command> for more info on a command.\n"
            f"You can also type {self.context.clean_prefix}{command_name} <category> for more info on a category."
        )

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

        if not isinstance(self.context.channel, disnake.DMChannel) and self.in_dms:
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
            # Strip left spaces (but not tabs) from help docs, as Discord inconsistently does this based on device
            command.help = "\n".join([line.lstrip(" ") for line in command.help.splitlines()])

            # Replace default prefix with the contexts prefix
            # new variable to avoid changing the original
            command_text = re.sub(r"!([aA-zZ0-9]+)", rf"{self.context.clean_prefix}\1", command.help)
            try:
                self.embed_paginator.extend_field(command_text)
            except ValueError:
                for line in command_text.splitlines():
                    self.embed_paginator.extend_field(line)

    def add_help_footer(self):
        self.embed_paginator.set_footer(
            value=(
                "Arguments surrounded in angled brackets (<args>) are mandatory,"
                " while those surrounded in square brackets ([args]) are optional."
                " In either case, don't include the brackets."
            )
        )

    # ===== HelpCommand overrides =====
    async def command_callback(self, ctx, *, command=None):
        if command and command.endswith("-here"):
            command = command[:-5].strip() or None
            self.in_dms = False

        # copied from super impl for custom alias handling
        await self.prepare_help_command(ctx, command)
        bot = ctx.bot

        # add the default footer here, it can be overridden later
        self.add_help_footer()

        if command is None:
            mapping = self.get_bot_mapping()
            return await self.send_bot_help(mapping)

        # Check if it's a cog
        cog = bot.get_cog(command)
        if cog is not None:
            return await self.send_cog_help(cog)

        maybe_coro = disnake.utils.maybe_coroutine

        # If it's not a cog then it's a command.
        # Since we want to have detailed errors when someone
        # passes an invalid subcommand, we need to walk through
        # the command group chain ourselves.
        keys = command.split(" ")
        cmd = bot.all_commands.get(keys[0])
        if cmd is None:
            alias = await aliasing.helpers.get_personal_alias_named(ctx, keys[0])
            if alias is None and ctx.guild is not None:
                alias = await aliasing.helpers.get_server_alias_named(ctx, keys[0])
            if alias is not None:
                return await self.send_alias_help(alias, keys)
            else:
                string = await maybe_coro(self.command_not_found, self.remove_mentions(keys[0]))
                return await self.send_error_message(string)

        for key in keys[1:]:
            try:
                found = cmd.all_commands.get(key)
            except AttributeError:
                string = await maybe_coro(self.subcommand_not_found, cmd, self.remove_mentions(key))
                return await self.send_error_message(string)
            else:
                if found is None:
                    string = await maybe_coro(self.subcommand_not_found, cmd, self.remove_mentions(key))
                    return await self.send_error_message(string)
                cmd = found

        if isinstance(cmd, Group):
            return await self.send_group_help(cmd)
        else:
            return await self.send_command_help(cmd)

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

        no_category = "\u200bUncategorized"

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

    async def send_alias_help(self, alias, full_cmd_path):
        fqp = [full_cmd_path[0]]  # fully qualified path
        ctx = self.context

        self.embed_paginator.set_footer(icon_url=HOMEBREW_ICON, value="User-created command.")

        # is this a personal alias?
        if isinstance(alias, (aliasing.personal.Alias, aliasing.personal.Servalias)):
            name = " ".join(fqp)
            self.embed_paginator.add_field(name=f"{ctx.prefix}{name}")
            self.embed_paginator.extend_field(f"{name} is a personal or server alias and has no help attached.")
            await self.send()
            return

        # is the requested help for a subcommand?
        for key in full_cmd_path[1:]:
            try:
                alias = await alias.get_subalias_named(ctx, key)
            except aliasing.errors.CollectableNotFound:
                return await self.send_error_message(f'The alias "{" ".join(fqp)}" has no subalias "{key}".')
            fqp.append(key)

        # send help
        the_collection = await alias.load_collection(ctx)
        owner = await user_from_id(ctx, the_collection.owner)

        # metadata
        self.embed_paginator.add_field(name=f"{ctx.prefix}{' '.join(fqp)}")
        self.embed_paginator.extend_field(
            f"From {the_collection.name} by {owner}.\n[View on Workshop]({the_collection.url})"
        )

        # docs
        self.embed_paginator.add_field(name="Help")
        alias_docs = alias.docs or "No documentation."
        for line in alias_docs.splitlines():
            self.embed_paginator.extend_field(line)

        # subcommands
        await alias.load_subcommands(ctx)
        if alias.subcommands:
            self.embed_paginator.add_field(name="Subcommands")
            for sc in alias.subcommands:
                self.embed_paginator.extend_field(f"**{sc.name}** - {sc.short_docs}")

        await self.send()


help_command = AvraeHelp(
    verify_checks=False,  # allows guild-only commands to be shown in PMs
    command_attrs=dict(
        help=(
            "Shows the help for the bot or a specific command.\n"
            "__Valid Arguments__\n"
            "-here - Sends help to the channel instead of PMs."
        ),
        brief="Shows this message.",
    ),
)
