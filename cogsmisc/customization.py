"""
Created on Jan 30, 2017

@author: andrew
"""
import asyncio
import textwrap
from collections import Counter

import discord
from discord.ext import commands
from discord.ext.commands import BucketType

from aliasing import helpers, personal, workshop
from cogs5e.models.character import Character
from cogs5e.models.embeds import EmbedWithAuthor
from aliasing.errors import EvaluationError
from utils import checks
from utils.functions import auth_and_chan, clean_content, confirm

ALIASER_ROLES = ("server aliaser", "dragonspeaker")


class Customization(commands.Cog):
    """Commands to help streamline using the bot."""

    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        if self.bot.is_cluster_0:
            cmds = list(self.bot.all_commands.keys())
            await self.bot.rdb.jset('default_commands', cmds)

    @commands.command()
    @commands.guild_only()
    @checks.admin_or_permissions(manage_guild=True)
    async def prefix(self, ctx, prefix: str = None):
        """Sets the bot's prefix for this server.

        You must have Manage Server permissions or a role called "Bot Admin" to use this command.

        Forgot the prefix? Reset it with "@Avrae#6944 prefix !".
        """
        guild_id = str(ctx.guild.id)
        if prefix is None:
            current_prefix = await self.bot.get_server_prefix(ctx.message)
            return await ctx.send(f"My current prefix is: `{current_prefix}`")
        # insert into cache
        self.bot.prefixes[guild_id] = prefix

        # update db
        await self.bot.mdb.prefixes.update_one(
            {"guild_id": guild_id},
            {"$set": {"prefix": prefix}},
            upsert=True
        )

        await ctx.send("Prefix set to `{}` for this server.".format(prefix))

    @commands.command()
    @commands.cooldown(1, 20, BucketType.user)
    @commands.max_concurrency(1, BucketType.user)
    async def multiline(self, ctx, *, cmds: str):
        """Runs each line as a separate command, with a 1 second delay between commands.
        Limited to 1 multiline every 20 seconds, with a max of 20 commands, due to abuse.
        Usage:
        "!multiline
        !roll 1d20
        !spell Fly
        !monster Rat"
        """
        cmds = cmds.splitlines()
        for c in cmds[:20]:
            ctx.message.content = c
            await self.bot.process_commands(ctx.message)
            await asyncio.sleep(1)

    @commands.group(invoke_without_command=True)
    async def alias(self, ctx, alias_name=None, *, cmds=None):
        """
        Creates a custom user command.
        After an alias has been added, you can run the command with !<alias_name>.

        If a user and a server have aliases with the same name, the user alias will take priority.
        Note that aliases cannot call other aliases.

        Check out the [Aliasing Basics](https://avrae.readthedocs.io/en/latest/aliasing/aliasing.html) and [Aliasing Documentation](https://avrae.readthedocs.io/en/latest/aliasing/api.html) for more information.
        """
        if alias_name is None:
            return await self.alias_list(ctx)
        if alias_name in self.bot.all_commands:
            return await ctx.send('There is already a built-in command with that name!')

        if ' ' in alias_name or not alias_name:
            return await ctx.send('Invalid alias name.')

        if cmds is None:
            return await self._view_alias(ctx, alias_name)

        alias = personal.Alias.new(alias_name, cmds.lstrip("!"), str(ctx.author.id))
        await alias.commit(self.bot.mdb)

        out = f'Alias `{ctx.prefix}{alias_name}` added.' \
              f'```py\n{ctx.prefix}alias {alias_name} {cmds.lstrip("!")}\n```'

        out = out if len(out) <= 2000 else f'Alias `{ctx.prefix}{alias_name}` added.\n' \
                                           f'Command output too long to display.\n' \
                                           f'You can view your personal aliases (and more) on the dashboard.\n' \
                                           f'<https://avrae.io/dashboard/aliases>'
        await ctx.send(out)

    @staticmethod
    async def _view_alias(ctx, alias_name):  # todo view workshop alias
        alias = await personal.Alias.get_named(alias_name, ctx)
        if alias is None:
            alias = 'Not defined.'
        else:
            alias = f'{ctx.prefix}alias {alias_name} {alias}'
        out = f'**{alias_name}**: ```py\n{alias}\n```'
        out = out if len(out) <= 2000 else f'**{alias_name}**:\nCommand output too long to display.\n' \
                                           f'You can view your personal aliases (and more) on the dashboard.\n' \
                                           f'<https://avrae.io/dashboard/aliases>'
        return await ctx.send(out)

    @alias.command(name='list')
    async def alias_list(self, ctx):
        """Lists all user aliases."""
        embed = EmbedWithAuthor(ctx)

        has_at_least_1_alias = False

        user_aliases = await personal.Alias.get_ctx_map(ctx)
        user_alias_names = list(user_aliases.keys())
        if user_alias_names:
            has_at_least_1_alias = True
            embed.add_field(name="Your Aliases", value=', '.join(sorted(user_alias_names)), inline=False)

        async for subscription_doc in workshop.WorkshopCollection.my_subs(ctx):
            the_collection = await workshop.WorkshopCollection.from_id(ctx, subscription_doc['object_id'])
            if bindings := subscription_doc['alias_bindings']:
                has_at_least_1_alias = True
                embed.add_field(name=the_collection.name, value=', '.join(sorted(ab['name'] for ab in bindings)),
                                inline=False)
            else:
                embed.add_field(name=the_collection.name, value="This collection has no aliases.", inline=False)

        if not has_at_least_1_alias:
            # todo get link
            embed.description = "You have no aliases. Check out the [Alias Workshop] to get some, " \
                                "or [make your own](https://avrae.readthedocs.io/en/latest/aliasing/api.html)!"

        return await ctx.send(embed=embed)

    @alias.command(name='delete', aliases=['remove'])
    async def alias_delete(self, ctx, alias_name):
        """Deletes a user alias."""
        alias = await personal.Alias.get_named(alias_name, ctx)
        if alias is None:
            return await ctx.send('Alias not found. If this is a workshop alias, you can unsubscribe on the Avrae '
                                  'dashboard.')  # todo link
        await alias.delete(ctx.bot.mdb)
        await ctx.send(f'Alias {alias_name} removed.')

    @alias.command(name='deleteall', aliases=['removeall'])
    async def alias_deleteall(self, ctx):
        """Deletes ALL user aliases."""
        await ctx.send("This will delete **ALL** of your user aliases. "
                       "Are you *absolutely sure* you want to continue?\n"
                       "Type `Yes, I am sure` to confirm.")
        reply = await self.bot.wait_for('message', timeout=30, check=auth_and_chan(ctx))
        if not reply.content == "Yes, I am sure":
            return await ctx.send("Unconfirmed. Aborting.")

        await self.bot.mdb.aliases.delete_many({"owner": str(ctx.author.id)})
        return await ctx.send("OK. I have deleted all your aliases.")

    @alias.command(name='subscribe', aliases=['sub'])
    async def alias_subscribe(self, ctx, alias_id):
        # todo url stuff
        the_collection = await workshop.WorkshopCollection.from_id(ctx, alias_id)
        await the_collection.subscribe(ctx)
        await ctx.send('ok')

    @alias.command(name='autofix', hidden=True)
    async def alias_autofix(self, ctx):
        """Ensures that all personal and subscribed workshop aliases have unique names."""
        name_indices = Counter()
        for name in await personal.Alias.get_ctx_map(ctx):
            name_indices[name] += 1

        renamed = []

        async for subscription_doc in workshop.WorkshopCollection.my_subs(ctx):
            doc_changed = False
            the_collection = await workshop.WorkshopCollection.from_id(ctx, subscription_doc['object_id'])

            for binding in subscription_doc['alias_bindings']:
                old_name = binding['name']
                if new_index := name_indices[old_name]:
                    new_name = f"{binding['name']}-{new_index}"
                    # do rename
                    binding['name'] = new_name
                    renamed.append(
                        f"`{ctx.prefix}{old_name}` ({the_collection.name}) is now `{ctx.prefix}{new_name}`")
                    doc_changed = True
                name_indices[old_name] += 1

            if doc_changed:  # write the new subscription object to the db
                await the_collection.update_alias_bindings(ctx, subscription_doc)

        the_renamed = '\n'.join(renamed)
        await ctx.send(f"Renamed {len(renamed)} aliases!\n{the_renamed}")

    @alias.command(name='rename')
    async def alias_rename(self, ctx, old_name, new_name):
        """Renames a personal or subscribed workshop alias to a new name."""
        # todo

    # todo workshopify stuff below here
    # todo also make stuff below here better oop
    @commands.group(invoke_without_command=True, aliases=['serveralias'])
    @commands.guild_only()
    async def servalias(self, ctx, alias_name=None, *, cmds=None):
        """Adds an alias that the entire server can use.
        Requires __Administrator__ Discord permissions or a role called "Server Aliaser".
        If a user and a server have aliases with the same name, the user alias will take priority."""
        if alias_name is None:
            return await self.servalias_list(ctx)

        server_aliases = await personal.Servalias.get_ctx_map(ctx)
        if alias_name in self.bot.all_commands:
            return await ctx.send('There is already a built-in command with that name!')

        if cmds is None:
            alias = server_aliases.get(alias_name)
            if alias is None:
                alias = 'Not defined.'
            else:
                alias = f'{ctx.prefix}alias {alias_name} {alias}'
            out = f'**{alias_name}**: ```py\n{alias}\n```'
            out = out if len(out) <= 2000 else f'Servalias `{ctx.prefix}{alias_name}`.\n' \
                                               f'Command output too long to display.'
            return await ctx.send(out)

        if not self.can_edit_servaliases(ctx):
            return await ctx.send("You do not have permission to edit server aliases. Either __Administrator__ "
                                  "Discord permissions or a role named \"Server Aliaser\" or \"Dragonspeaker\" "
                                  "is required.")

        alias = personal.Servalias.new(alias_name, cmds.lstrip("!"), str(ctx.guild.id))
        await alias.commit(self.bot.mdb)

        out = f'Server alias `{ctx.prefix}{alias_name}` added.' \
              f'```py\n{ctx.prefix}alias {alias_name} {cmds.lstrip("!")}\n```'
        out = out if len(out) <= 2000 else f'Servalias `{ctx.prefix}{alias_name}` added.\n' \
                                           f'Command output too long to display.'
        await ctx.send(out)

    @servalias.command(name='list')
    @commands.guild_only()
    async def servalias_list(self, ctx):
        """Lists all server aliases."""
        server_aliases = await personal.Servalias.get_ctx_map(ctx)
        aliases = list(server_aliases.keys())
        sorted_aliases = sorted(aliases)
        return await ctx.send('This server\'s aliases:\n{}'.format(', '.join(sorted_aliases)))

    @servalias.command(name='delete', aliases=['remove'])
    @commands.guild_only()
    async def servalias_delete(self, ctx, alias_name):
        """Deletes a server alias.
        Any user with permission to create a server alias can delete one from the server."""
        if not self.can_edit_servaliases(ctx):
            return await ctx.send("You do not have permission to edit server aliases. Either __Administrator__ "
                                  "Discord permissions or a role called \"Server Aliaser\" is required.")
        result = await self.bot.mdb.servaliases.delete_one({"server": str(ctx.guild.id), "name": alias_name})
        if not result.deleted_count:
            return await ctx.send('Server alias not found.')
        await ctx.send('Server alias {} removed.'.format(alias_name))

    @staticmethod
    def can_edit_servaliases(ctx):
        """
        Returns whether a user can edit server aliases in the current context.
        """
        return ctx.author.guild_permissions.administrator or \
               any(r.name.lower() in ALIASER_ROLES for r in ctx.author.roles) or \
               checks.author_is_owner(ctx)

    @commands.group(invoke_without_command=True)
    async def snippet(self, ctx, snipname=None, *, snippet=None):
        """Creates a snippet to use in attack commands.
        Ex: *!snippet sneak -d "2d6[Sneak Attack]"* can be used as *!a sword sneak*."""
        if snipname is None:
            return await self.snippet_list(ctx)
        user_snippets = await personal.Snippet.get_ctx_map(ctx)

        if snippet is None:
            out = f'**{snipname}**:```py\n' \
                  f'{ctx.prefix}snippet {snipname} {user_snippets.get(snipname, "Not defined.")}' \
                  f'\n```'
            out = out if len(out) <= 2000 else f'**{snipname}**:\n' \
                                               f'Command output too long to display.\n' \
                                               f'You can view your personal snippets (and more) on the dashboard.\n' \
                                               f'<https://avrae.io/dashboard/aliases>'
            return await ctx.send(out)

        snippet = personal.Snippet.new(snipname, snippet, str(ctx.author.id))
        await snippet.commit(self.bot.mdb)

        out = f'Snippet {snipname} added.```py\n' \
              f'{ctx.prefix}snippet {snipname} {snippet}\n```'
        out = out if len(out) <= 2000 else f'Snippet {snipname} added.\n' \
                                           f'Command output too long to display.\n' \
                                           f'You can view your personal snippets (and more) on the dashboard.\n' \
                                           f'<https://avrae.io/dashboard/aliases>'
        await ctx.send(out)

    @snippet.command(name='list')
    async def snippet_list(self, ctx):
        """Lists your user snippets."""
        user_snippets = await personal.Snippet.get_ctx_map(ctx)
        await ctx.send('Your snippets:\n{}'.format(', '.join(sorted([name for name in user_snippets.keys()]))))

    @snippet.command(name='delete', aliases=['remove'])
    async def snippet_delete(self, ctx, snippet_name):
        """Deletes a snippet."""
        result = await self.bot.mdb.snippets.delete_one({"owner": str(ctx.author.id), "name": snippet_name})
        if not result.deleted_count:
            return await ctx.send('Snippet not found.')
        await ctx.send('Shortcut {} removed.'.format(snippet_name))

    @snippet.command(name='deleteall', aliases=['removeall'])
    async def snippet_deleteall(self, ctx):
        """Deletes ALL user snippets."""
        await ctx.send("This will delete **ALL** of your user snippets. "
                       "Are you *absolutely sure* you want to continue?\n"
                       "Type `Yes, I am sure` to confirm.")
        reply = await self.bot.wait_for('message', timeout=30, check=lambda m: auth_and_chan(ctx)(m))
        if not reply.content == "Yes, I am sure":
            return await ctx.send("Unconfirmed. Aborting.")

        await self.bot.mdb.snippets.delete_many({"owner": str(ctx.author.id)})
        return await ctx.send("OK. I have deleted all your snippets.")

    @commands.group(invoke_without_command=True)
    @commands.guild_only()
    async def servsnippet(self, ctx, snipname=None, *, snippet=None):
        """Creates a snippet to use in attack macros for the entire server.
        Requires __Administrator__ Discord permissions or a role called "Server Aliaser".
        If a user and a server have snippets with the same name, the user snippet will take priority.
        Ex: *!snippet sneak -d "2d6[Sneak Attack]"* can be used as *!a sword sneak*."""
        if snipname is None:
            return await self.servsnippet_list(ctx)
        server_snippets = await personal.Servsnippet.get_ctx_map(ctx)

        if snippet is None:
            out = f'**{snipname}**:```py\n' \
                  f'{ctx.prefix}snippet {snipname} {server_snippets.get(snipname, "Not defined.")}' \
                  f'\n```'
            out = out if len(out) <= 2000 else f'**{snipname}**:\n' \
                                               f'Command output too long to display.'
            return await ctx.send(out)

        if not self.can_edit_servaliases(ctx):
            return await ctx.send("You do not have permission to edit server snippets. Either __Administrator__ "
                                  "Discord permissions or a role named \"Server Aliaser\" or \"Dragonspeaker\" "
                                  "is required.")

        snippet = personal.Servsnippet.new(snipname, snippet, str(ctx.guild.id))
        await snippet.commit(self.bot.mdb)

        out = f'Server snippet {snipname} added.```py\n' \
              f'{ctx.prefix}snippet {snipname} {snippet}' \
              f'\n```'
        out = out if len(out) <= 2000 else f'Server snippet {snipname} added.\n' \
                                           f'Command output too long to display.'
        await ctx.send(out)

    @servsnippet.command(name='list')
    @commands.guild_only()
    async def servsnippet_list(self, ctx):
        """Lists this server's snippets."""
        server_snippets = await personal.Servsnippet.get_ctx_map(ctx)
        await ctx.send(
            'This server\'s snippets:\n{}'.format(', '.join(sorted([name for name in server_snippets.keys()]))))

    @servsnippet.command(name='delete', aliases=['remove'])
    @commands.guild_only()
    async def servsnippet_delete(self, ctx, snippet_name):
        """Deletes a server snippet.
        Any user that can create a server snippet can delete one."""
        if not self.can_edit_servaliases(ctx):
            return await ctx.send("You do not have permission to edit server snippets. Either __Administrator__ "
                                  "Discord permissions or a role called \"Server Aliaser\" is required.")
        result = await self.bot.mdb.servsnippets.delete_one({"server": str(ctx.guild.id), "name": snippet_name})
        if not result.deleted_count:
            return await ctx.send('Snippet not found.')
        await ctx.send('Server snippet {} removed.'.format(snippet_name))

    @commands.command()
    async def test(self, ctx, *, teststr):
        """Parses `str` as if it were in an alias, for testing."""
        char = await Character.from_ctx(ctx)
        try:
            parsed = await char.parse_cvars(teststr, ctx)
        except EvaluationError as err:
            return await helpers.handle_alias_exception(ctx, err)
        parsed = clean_content(parsed, ctx)
        await ctx.send(f"{ctx.author.display_name}: {parsed}")

    @commands.command()
    async def tembed(self, ctx, *, teststr):
        """Parses `str` as if it were in an alias, for testing, then creates and prints an Embed.
        Arguments: -title [title]
        -desc [description text]
        -thumb [image url]
        -image [image url]
        -footer [footer text]
        -f ["Field Title|Field Text"]
        -color [hex color]
        -t [timeout (0..600)]
        """

        char = await Character.from_ctx(ctx)
        parsed = await char.parse_cvars(teststr, ctx)

        embed_command = self.bot.get_command('embed')
        if embed_command is None:
            return await ctx.send("Error: pbpUtils cog not loaded.")
        else:
            return await ctx.invoke(embed_command, args=parsed)

    @commands.group(invoke_without_command=True)
    async def cvar(self, ctx, name: str = None, *, value=None):
        """Commands to manage character variables for use in snippets and aliases.
        See the [aliasing guide](https://avrae.io/cheatsheets/aliasing) for more help."""
        if name is None:
            return await self.list_cvar(ctx)

        character: Character = await Character.from_ctx(ctx)

        if value is None:  # display value
            cvar = character.get_scope_locals().get(name)
            if cvar is None:
                return await ctx.send("This cvar is not defined.")
            return await ctx.send(f'**{name}**: ```\n{cvar}\n```')

        helpers.set_cvar(character, name, value)

        await character.commit(ctx)
        await ctx.send('Character variable `{}` set to: `{}`'.format(name, value))

    @cvar.command(name='remove', aliases=['delete'])
    async def remove_cvar(self, ctx, name):
        """Deletes a cvar from the currently active character."""
        char: Character = await Character.from_ctx(ctx)
        if name not in char.cvars:
            return await ctx.send('Character variable not found.')

        del char.cvars[name]

        await char.commit(ctx)
        await ctx.send('Character variable {} removed.'.format(name))

    @cvar.command(name='deleteall', aliases=['removeall'])
    async def cvar_deleteall(self, ctx):
        """Deletes ALL character variables for the active character."""
        char: Character = await Character.from_ctx(ctx)

        await ctx.send(f"This will delete **ALL** of your character variables for {char.name}. "
                       "Are you *absolutely sure* you want to continue?\n"
                       "Type `Yes, I am sure` to confirm.")
        try:
            reply = await self.bot.wait_for('message', timeout=30, check=auth_and_chan(ctx))
        except asyncio.TimeoutError:
            reply = None
        if (not reply) or (not reply.content == "Yes, I am sure"):
            return await ctx.send("Unconfirmed. Aborting.")

        char.cvars = {}

        await char.commit(ctx)
        return await ctx.send(f"OK. I have deleted all of {char.name}'s cvars.")

    @cvar.command(name='list')
    async def list_cvar(self, ctx):
        """Lists all cvars for the currently active character."""
        character: Character = await Character.from_ctx(ctx)
        await ctx.send('{}\'s character variables:\n{}'.format(character.name,
                                                               ', '.join(sorted(character.cvars.keys()))))

    @commands.group(invoke_without_command=True, aliases=['uvar'])
    async def uservar(self, ctx, name=None, *, value=None):
        """
        Commands to manage user variables for use in snippets and aliases.
        User variables can be called in the `-phrase` tag by surrounding the variable name with `{}` (calculates) or `<>` (prints).
        Arguments surrounded with `{{}}` will be evaluated as a custom script.
        See http://avrae.io/cheatsheets/aliasing for more help."""
        if name is None:
            return await self.uvar_list(ctx)

        user_vars = await helpers.get_uvars(ctx)

        if value is None:  # display value
            uvar = user_vars.get(name)
            if uvar is None:
                return await ctx.send("This uvar is not defined.")
            return await ctx.send(f'**{name}**: ```\n{uvar}\n```')

        if name in STAT_VAR_NAMES or not name.isidentifier():
            return await ctx.send("Could not create uvar: already builtin, or contains invalid character!")

        await helpers.set_uvar(ctx, name, value)
        await ctx.send('User variable `{}` set to: `{}`'.format(name, value))

    @uservar.command(name='remove', aliases=['delete'])
    async def uvar_remove(self, ctx, name):
        """Deletes a uvar from the user."""
        result = await self.bot.mdb.uvars.delete_one({"owner": str(ctx.author.id), "name": name})
        if not result.deleted_count:
            return await ctx.send("Uvar does not exist.")
        await ctx.send('User variable {} removed.'.format(name))

    @uservar.command(name='list')
    async def uvar_list(self, ctx):
        """Lists all uvars for the user."""
        user_vars = await helpers.get_uvars(ctx)
        await ctx.send('Your user variables:\n{}'.format(', '.join(sorted([name for name in user_vars.keys()]))))

    @uservar.command(name='deleteall', aliases=['removeall'])
    async def uvar_deleteall(self, ctx):
        """Deletes ALL user variables."""
        await ctx.send("This will delete **ALL** of your user variables (uvars). "
                       "Are you *absolutely sure* you want to continue?\n"
                       "Type `Yes, I am sure` to confirm.")
        reply = await self.bot.wait_for('message', timeout=30, check=lambda m: auth_and_chan(ctx)(m))
        if (not reply) or (not reply.content == "Yes, I am sure"):
            return await ctx.send("Unconfirmed. Aborting.")

        await self.bot.mdb.uvars.delete_many({"owner": str(ctx.author.id)})
        return await ctx.send("OK. I have deleted all your uvars.")

    @commands.group(invoke_without_command=True, aliases=['gvar'])
    async def globalvar(self, ctx, name=None):
        """Commands to manage global, community variables for use in snippets and aliases.
        If run without a subcommand, shows the value of a global variable.
        Global variables are readable by all users, but only editable by the creator.
        Global variables must be accessed through scripting, with `get_gvar(gvar_id)`.
        See http://avrae.io/cheatsheets/aliasing for more help."""
        if name is None:
            return await self.gvar_list(ctx)

        gvar = await self.bot.mdb.gvars.find_one({"key": name})
        if gvar is None:
            return await ctx.send("This gvar does not exist.")
        out = f"**{name}**:\n*Owner: {gvar['owner_name']}* ```\n{gvar['value']}\n```"
        if len(out) <= 2000:
            await ctx.send(out)
        else:
            await ctx.send(f"**{name}**:\n*Owner: {gvar['owner_name']}*\nThis gvar is too long to display in Discord.\n"
                           f"You can view it here: <https://avrae.io/dashboard/gvars?lookup={name}>")

    @globalvar.command(name='create')
    async def gvar_create(self, ctx, *, value):
        """Creates a global variable.
        A name will be randomly assigned upon creation."""
        name = await helpers.create_gvar(ctx, value)
        await ctx.send(f"Created global variable `{name}`.")

    @globalvar.command(name='edit')
    async def gvar_edit(self, ctx, name, *, value):
        """Edits a global variable."""
        await helpers.update_gvar(ctx, name, value)
        await ctx.send(f'Global variable `{name}` edited.')

    @globalvar.command(name='editor')
    async def gvar_editor(self, ctx, name, user: discord.Member = None):
        """Toggles the editor status of a user."""
        gvar = await self.bot.mdb.gvars.find_one({"key": name})
        if gvar is None:
            return await ctx.send("Global variable not found.")

        if user is not None:
            if gvar['owner'] != str(ctx.author.id):
                return await ctx.send("You are not the owner of this variable.")
            else:
                e = gvar.get('editors', [])
                if str(user.id) in e:
                    e.remove(str(user.id))
                    msg = f"Removed {user} from the editor list."
                else:
                    e.append(str(user.id))
                    msg = f"Added {user} to the editor list."
                await self.bot.mdb.gvars.update_one({"key": name}, {"$set": {"editors": e}})
            await ctx.send(f'Global variable `{name}` edited: {msg}')
        else:
            embed = EmbedWithAuthor(ctx)
            embed.title = "Editors"
            editor_mentions = []
            for editor in gvar.get('editors', []):
                editor_mentions.append(f"<@{editor}>")
            embed.description = ', '.join(editor_mentions) or "No editors."
            await ctx.send(embed=embed)

    @globalvar.command(name='remove', aliases=['delete'])
    async def gvar_remove(self, ctx, name):
        """Deletes a global variable."""
        gvar = await self.bot.mdb.gvars.find_one({"key": name})
        if gvar is None:
            return await ctx.send("Global variable not found.")
        elif gvar['owner'] != str(ctx.author.id):
            return await ctx.send("You are not the owner of this variable.")
        else:
            if await confirm(ctx, f"Are you sure you want to delete `{name}`?"):
                await self.bot.mdb.gvars.delete_one({"key": name})
            else:
                return await ctx.send("Ok, cancelling.")

        await ctx.send('Global variable {} removed.'.format(name))

    @globalvar.command(name='list')
    async def gvar_list(self, ctx):
        """Lists all global variables for the user."""
        user_vars = []
        async for gvar in self.bot.mdb.gvars.find({"owner": str(ctx.author.id)}):
            user_vars.append((gvar['key'], gvar['value']))
        gvar_list = [f"`{k}`: {textwrap.shorten(v, 20)}" for k, v in sorted(user_vars, key=lambda i: i[0])]
        say_list = ['']
        for g in gvar_list:
            if len(g) + len(say_list[-1]) < 1900:
                say_list[-1] += f'\n{g}'
            else:
                say_list.append(g)
        await ctx.send('Your global variables:{}'.format(say_list[0]))
        for m in say_list[1:]:
            await ctx.send(m)

    # temporary commands to aid testers with lack of dashboard
    # @globalvar.command(name='import', hidden=True)
    # async def gvar_import(self, ctx, destination=None):
    #     """Imports a gvar from a txt file. If an arg is passed, sets the destination gvar, otherwise creates."""
    #     if not ctx.message.attachments:
    #         return await ctx.send("You must upload a TXT file to import.")
    #
    #     attachment = ctx.message.attachments[0]
    #     if attachment.size > 100000:
    #         return await ctx.send("This file is too large.")
    #
    #     data = await attachment.read()
    #     try:
    #         value = data.decode('utf-8')
    #     except:
    #         return await ctx.send("Could not read this file. Are you sure it's a text file?")
    #
    #     if destination:
    #         await helpers.update_gvar(ctx, destination, value)
    #         await ctx.send(f'Global variable `{destination}` edited.')
    #     else:
    #         name = await helpers.create_gvar(ctx, value)
    #         await ctx.send(f"Created global variable `{name}`.")
    #
    # @globalvar.command(name='export', hidden=True)
    # async def gvar_export(self, ctx, address):
    #     """Exports a gvar to a txt file."""
    #     import io
    #     gvar = await self.bot.mdb.gvars.find_one({"key": address})
    #     if gvar is None:
    #         return await ctx.send("This gvar does not exist.")
    #     value = gvar['value']
    #     out = io.StringIO(value)
    #     await ctx.send(file=discord.File(out, f'{address}.txt'))


def setup(bot):
    bot.add_cog(Customization(bot))


STAT_VAR_NAMES = ("armor",
                  "charisma", "charismaMod", "charismaSave",
                  "constitution", "constitutionMod", "constitutionSave",
                  "description",
                  "dexterity", "dexterityMod", "dexteritySave",
                  "hp", "image",
                  "intelligence", "intelligenceMod", "intelligenceSave",
                  "level", "name", "proficiencyBonus",
                  "strength", "strengthMod", "strengthSave",
                  "wisdom", "wisdomMod", "wisdomSave")
