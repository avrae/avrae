"""
Created on Jan 30, 2017

@author: andrew
"""
import asyncio
import re
import textwrap
from collections import Counter

import discord
from discord.ext import commands
from discord.ext.commands import BucketType, NoPrivateMessage

from aliasing import helpers, personal, workshop
from aliasing.errors import EvaluationError
from cogs5e.models import embeds
from cogs5e.models.character import Character
from cogs5e.models.embeds import EmbedWithAuthor
from cogs5e.models.errors import InvalidArgument, NoCharacter, NotAllowed
from utils import checks
from utils.functions import auth_and_chan, confirm
from utils.functions import get_selection, user_from_id

ALIASER_ROLES = ("server aliaser", "dragonspeaker")


class CollectableManagementGroup(commands.Group):
    def __init__(self, func=None, *, personal_cls, workshop_cls, workshop_sub_meth, is_alias, is_server,
                 before_edit_check=None,
                 **kwargs):
        """
        :type func: Coroutine
        :type workshop_sub_meth: Coroutine
        :type is_alias: bool
        :type is_server: bool
        :type before_edit_check: Coroutine[Context, Optional[str]] -> None
        """
        if func is None:
            func = self.create_or_view
        super().__init__(func, **kwargs)
        self.personal_cls = personal_cls
        self.workshop_cls = workshop_cls
        self.workshop_sub_meth = workshop_sub_meth
        self.is_alias = is_alias
        self.is_server = is_server
        self.before_edit_check = before_edit_check

        # helpers
        self.binding_key = 'alias_bindings' if self.is_alias else 'snippet_bindings'
        self.obj_name = 'alias' if self.is_alias else 'snippet'
        self.obj_copy_command = self.obj_name  # when an item is viewed, we show the non-server version of the command
        self.obj_name_pl = 'aliases' if self.is_alias else 'snippets'

        if self.is_server:
            self.obj_name = f'server {self.obj_name}'
            self.obj_name_pl = f'server {self.obj_name_pl}'
            self.owner_from_ctx = lambda ctx: str(ctx.guild.id)
        else:
            self.owner_from_ctx = lambda ctx: str(ctx.author.id)

        # register commands
        self._register_commands()

    def _register_commands(self):
        self.list = self.command(name='list',
                                 help=f'Lists all {self.obj_name_pl}.')(self.list)
        self.delete = self.command(name='delete', aliases=['remove'],
                                   help=f'Deletes a {self.obj_name}.')(self.delete)
        self.subscribe = self.command(
            name='subscribe', aliases=['sub'],
            help='Subscribes to all aliases and snippets in a workshop collection.')(self.subscribe)
        self.autofix = self.command(
            name='autofix', hidden=True,
            help='Ensures that all server and subscribed workshop aliases have unique names.')(self.autofix)
        self.rename = self.command(
            name='rename',
            help=f'Renames a {self.obj_name} or subscribed workshop {self.obj_name} to a new name.')(self.rename)

    # we override the Group copy command since we register commands in __init__
    # and Group.copy() tries to reregister commands
    def copy(self):
        return commands.Command.copy(self)

    def command(self, *args, **kwargs):
        kwargs.setdefault('checks', self.checks)  # inherit all checks of parent command
        return super().command(*args, **kwargs)

    # noinspection PyUnusedLocal
    # d.py passes the cog in as the first argument (which is weird for this custom case)
    async def create_or_view(self, cog, ctx, name=None, *, code=None):
        if name is None:
            return await self.list(ctx)

        if code is None:
            return await self._view(ctx, name)

        if self.before_edit_check:
            await self.before_edit_check(ctx, name)

        obj = self.personal_cls.new(name, code, self.owner_from_ctx(ctx))
        await obj.commit(ctx.bot.mdb)

        out = f'{self.obj_name.capitalize()} `{name}` added.' \
              f'```py\n{ctx.prefix}{self.obj_copy_command} {name} {code}\n```'

        if len(out) > 2000:
            out = f'{self.obj_name.capitalize()} `{name}` added.\n' \
                  f'Command output too long to display.'

        await ctx.send(out)

    async def _view(self, ctx, name):
        collectable = await helpers.get_collectable_named(
            ctx, name, self.personal_cls, self.workshop_cls, self.workshop_sub_meth,
            self.is_alias, self.obj_name, self.obj_name_pl, self.name
        )
        if collectable is None:
            return await ctx.send(f"No {self.obj_name} named {name} found.")
        elif isinstance(collectable, self.personal_cls):  # personal
            out = f'**{name}**: ```py\n{ctx.prefix}{self.obj_copy_command} {collectable.name} {collectable.code}\n```'
            out = out if len(out) <= 2000 else f'**{collectable.name}**:\nCommand output too long to display.'
            return await ctx.send(out)
        else:  # collection
            embed = EmbedWithAuthor(ctx)
            the_collection = await collectable.load_collection(ctx)
            owner = await user_from_id(ctx, the_collection.owner)
            embed.title = f"{ctx.prefix}{name}" if self.is_alias else name
            embed.description = f"From {the_collection.name} by {owner}.\n" \
                                f"[View on Workshop]({the_collection.url})"
            embed.add_field(name="Help", value=collectable.docs or "No documentation.", inline=False)

            if isinstance(collectable, workshop.WorkshopAlias):
                await collectable.load_subcommands(ctx)
                if collectable.subcommands:
                    subcommands = "\n".join(f"**{sc.name}** - {sc.short_docs}" for sc in collectable.subcommands)
                    embed.add_field(name="Subcommands", value=subcommands, inline=False)

            return await ctx.send(embed=embed)

    async def list(self, ctx):
        embed = EmbedWithAuthor(ctx)

        has_at_least_1 = False

        user_objs = await self.personal_cls.get_ctx_map(ctx)
        user_obj_names = list(user_objs.keys())
        if user_obj_names:
            has_at_least_1 = True
            embeds.add_fields_from_long_text(embed, f"Your {self.obj_name_pl.title()}",
                                             ', '.join(sorted(user_obj_names)))

        async for subscription_doc in self.workshop_sub_meth(ctx):
            try:
                the_collection = await workshop.WorkshopCollection.from_id(ctx, subscription_doc['object_id'])
            except workshop.CollectionNotFound:
                continue
            if bindings := subscription_doc[self.binding_key]:
                has_at_least_1 = True
                embed.add_field(name=the_collection.name, value=', '.join(sorted(ab['name'] for ab in bindings)),
                                inline=False)
            else:
                embed.add_field(name=the_collection.name, value=f"This collection has no {self.obj_name_pl}.",
                                inline=False)

        if not has_at_least_1:
            embed.description = f"You have no {self.obj_name_pl}. Check out the [Alias Workshop]" \
                                "(https://avrae.io/dashboard/workshop) to get some, " \
                                "or [make your own](https://avrae.readthedocs.io/en/latest/aliasing/api.html)!"

        return await ctx.send(embed=embed)

    async def delete(self, ctx, name):
        if self.before_edit_check:
            await self.before_edit_check(ctx, name)

        obj = await self.personal_cls.get_named(name, ctx)
        if obj is None:
            return await ctx.send(
                f'{self.obj_name.capitalize()} not found. If this is a workshop {self.obj_name}, you '
                f'can unsubscribe on the Avrae Dashboard at <https://avrae.io/dashboard/workshop/my-subscriptions>.')
        await obj.delete(ctx.bot.mdb)
        await ctx.send(f'{self.obj_name.capitalize()} {name} removed.')

    @checks.feature_flag('command.alias-subscribe.enabled')
    async def subscribe(self, ctx, url):
        coll_match = re.match(r'(?:https?://)?avrae\.io/dashboard/workshop/([0-9a-f]{24})(?:$|/)', url)
        if coll_match is None:
            return await ctx.send("This is not an Alias Workshop link.")

        if self.before_edit_check:
            await self.before_edit_check(ctx)

        collection_id = coll_match.group(1)
        the_collection = await workshop.WorkshopCollection.from_id(ctx, collection_id)
        # private and duplicate logic handled here, also loads aliases/snippets
        if self.is_server:
            await the_collection.set_server_active(ctx)
        else:
            await the_collection.subscribe(ctx)

        embed = EmbedWithAuthor(ctx)
        embed.title = f"Subscribed to {the_collection.name}"
        embed.url = the_collection.url
        embed.description = the_collection.description
        if the_collection.aliases:
            embed.add_field(name="Server Aliases" if self.is_server else "Aliases",
                            value=", ".join(sorted(a.name for a in the_collection.aliases)))
        if the_collection.snippets:
            embed.add_field(name="Server Snippets" if self.is_server else "Snippets",
                            value=", ".join(sorted(a.name for a in the_collection.snippets)))
        await ctx.send(embed=embed)

    async def autofix(self, ctx):
        if self.before_edit_check:
            await self.before_edit_check(ctx)

        name_indices = Counter()
        for name in await self.personal_cls.get_ctx_map(ctx):
            name_indices[name] += 1

        renamed = []

        async for subscription_doc in self.workshop_sub_meth(ctx):
            doc_changed = False
            the_collection = await workshop.WorkshopCollection.from_id(ctx, subscription_doc['object_id'])

            for binding in subscription_doc[self.binding_key]:
                old_name = binding['name']
                if new_index := name_indices[old_name]:
                    new_name = f"{binding['name']}-{new_index}"
                    # do rename
                    binding['name'] = new_name
                    renamed.append(
                        f"`{old_name}` ({the_collection.name}) is now `{new_name}`")
                    doc_changed = True
                name_indices[old_name] += 1

            if doc_changed:  # write the new subscription object to the db
                update_meth = the_collection.update_alias_bindings if self.is_alias \
                    else the_collection.update_snippet_bindings
                await update_meth(ctx, subscription_doc)

        the_renamed = '\n'.join(renamed)
        await ctx.send(f"Renamed {len(renamed)} {self.obj_name_pl}!\n{the_renamed}")

    async def rename(self, ctx, old_name, new_name):
        if self.before_edit_check:
            await self.before_edit_check(ctx)

        self.personal_cls.precreate_checks(new_name, '')

        # list of (name, (alias or sub doc, collection or None))
        choices = []
        if personal_obj := await self.personal_cls.get_named(old_name, ctx):
            choices.append((f"{old_name} ({self.obj_name})",
                            (personal_obj, None)))

        # get list of (subscription object ids, subscription doc)
        async for subscription_doc in self.workshop_sub_meth(ctx):
            the_collection = await workshop.WorkshopCollection.from_id(ctx, subscription_doc['object_id'])
            for binding in subscription_doc[self.binding_key]:
                if binding['name'] == old_name:
                    choices.append((f"{old_name} ({the_collection.name})",
                                    (subscription_doc, the_collection)))

        old_obj, collection = await get_selection(ctx, choices)

        if isinstance(old_obj, self.personal_cls):
            if await self.personal_cls.get_named(new_name, ctx):
                return await ctx.send(f"You already have a {self.obj_name} named {new_name}.")
            await old_obj.rename(ctx.bot.mdb, new_name)
            return await ctx.send(f"Okay, renamed the {self.obj_name} {old_name} to {new_name}.")
        else:  # old_obj is actually a subscription doc
            sub_doc = old_obj
            for binding in sub_doc[self.binding_key]:
                if binding['name'] == old_name:
                    binding['name'] = new_name

            update_meth = collection.update_alias_bindings if self.is_alias else collection.update_snippet_bindings
            await update_meth(ctx, sub_doc)
            return await ctx.send(
                f"Okay, the workshop {self.obj_name} that was bound to {old_name} is now bound to {new_name}.")


# helpers
def _can_edit_servaliases(ctx):
    """
    Returns whether a user can edit server aliases in the current context.
    """
    return ctx.author.guild_permissions.administrator or \
           any(r.name.lower() in ALIASER_ROLES for r in ctx.author.roles) or \
           checks.author_is_owner(ctx)


async def _alias_before_edit(ctx, name=None):
    if name and name in ctx.bot.all_commands:
        raise InvalidArgument(f"`{name}` is already a builtin command. Try another name.")


async def _servalias_before_edit(ctx, name=None):
    if not _can_edit_servaliases(ctx):
        raise NotAllowed("You do not have permission to edit server aliases. Either __Administrator__ "
                         "Discord permissions or a role named \"Server Aliaser\" or \"Dragonspeaker\" "
                         "is required.")
    await _alias_before_edit(ctx, name)


async def _servsnippet_before_edit(ctx, _=None):
    if not _can_edit_servaliases(ctx):
        raise NotAllowed("You do not have permission to edit server snippets. Either __Administrator__ "
                         "Discord permissions or a role named \"Server Aliaser\" or \"Dragonspeaker\" "
                         "is required.")


def guild_only_check(ctx):
    if ctx.guild is None:
        raise NoPrivateMessage()
    return True


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
    async def prefix(self, ctx, prefix: str = None):
        """Sets the bot's prefix for this server.

        You must have Manage Server permissions or a role called "Bot Admin" to use this command.

        Forgot the prefix? Reset it with "@Avrae#6944 prefix !".
        """
        guild_id = str(ctx.guild.id)
        if prefix is None:
            current_prefix = await self.bot.get_server_prefix(ctx.message)
            return await ctx.send(f"My current prefix is: `{current_prefix}`")

        if not checks._role_or_permissions(ctx, lambda r: r.name.lower() == 'bot admin', manage_guild=True):
            return await ctx.send("You do not have permissions to change the guild prefix.")

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

    # ==== aliases ====
    alias = CollectableManagementGroup(
        personal_cls=personal.Alias,
        workshop_cls=workshop.WorkshopAlias,
        workshop_sub_meth=workshop.WorkshopCollection.my_subs,
        is_alias=True,
        is_server=False,
        before_edit_check=_alias_before_edit,
        name='alias',
        invoke_without_command=True,
        help="""
        Creates a custom user command.
        After an alias has been added, you can run the command with !<alias_name>.
        
        If a user and a server have aliases with the same name, the user alias will take priority.
        Note that aliases cannot call other aliases.
        
        Check out the [Aliasing Basics](https://avrae.readthedocs.io/en/latest/aliasing/aliasing.html) and [Aliasing Documentation](https://avrae.readthedocs.io/en/latest/aliasing/api.html) for more information.
        """)

    @alias.command(name='deleteall', aliases=['removeall'])
    async def alias_deleteall(self, ctx):
        """Deletes ALL user aliases."""
        await ctx.send("This will delete **ALL** of your personal user aliases "
                       "(it will not affect workshop subscriptions). "
                       "Are you *absolutely sure* you want to continue?\n"
                       "Type `Yes, I am sure` to confirm.")
        reply = await self.bot.wait_for('message', timeout=30, check=auth_and_chan(ctx))
        if not reply.content == "Yes, I am sure":
            return await ctx.send("Unconfirmed. Aborting.")

        await self.bot.mdb.aliases.delete_many({"owner": str(ctx.author.id)})
        return await ctx.send("OK. I have deleted all your aliases.")

    # decorator weirdness
    servalias = CollectableManagementGroup(
        personal_cls=personal.Servalias,
        workshop_cls=workshop.WorkshopAlias,
        workshop_sub_meth=workshop.WorkshopCollection.guild_active_subs,
        is_alias=True,
        is_server=True,
        before_edit_check=_servalias_before_edit,
        name='servalias',
        invoke_without_command=True,
        help="""
        Adds an alias that the entire server can use.
        Requires __Administrator__ Discord permissions or a role called "Server Aliaser".
        If a user and a server have aliases with the same name, the user alias will take priority.
        """,
        checks=[guild_only_check], aliases=['serveralias']
    )

    snippet = CollectableManagementGroup(
        personal_cls=personal.Snippet,
        workshop_cls=workshop.WorkshopSnippet,
        workshop_sub_meth=workshop.WorkshopCollection.my_subs,
        is_alias=False,
        is_server=False,
        name='snippet',
        invoke_without_command=True,
        help="""
        Creates a snippet to use in certain commands.
        Ex: *!snippet sneak -d "2d6[Sneak Attack]"* can be used as *!a sword sneak*.

        If a user and a server have snippets with the same name, the user snippet will take priority.

        Check out the [Aliasing Basics](https://avrae.readthedocs.io/en/latest/aliasing/aliasing.html) and [Aliasing Documentation](https://avrae.readthedocs.io/en/latest/aliasing/api.html) for more information.
        """)

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

    servsnippet = CollectableManagementGroup(
        personal_cls=personal.Servsnippet,
        workshop_cls=workshop.WorkshopSnippet,
        workshop_sub_meth=workshop.WorkshopCollection.guild_active_subs,
        is_alias=False,
        is_server=True,
        before_edit_check=_servsnippet_before_edit,
        name='servsnippet',
        invoke_without_command=True,
        help="""
        Creates a snippet that the entire server can use.
        Requires __Administrator__ Discord permissions or a role called "Server Aliaser".
        If a user and a server have snippets with the same name, the user snippet will take priority.
        """,
        checks=[guild_only_check], aliases=['serversnippet']
    )

    @commands.command()
    async def test(self, ctx, *, teststr):
        """Parses `str` as if it were in an alias, for testing."""
        try:
            char = await Character.from_ctx(ctx)
            transformer = helpers.parse_with_character(ctx, char, teststr)
        except NoCharacter:
            transformer = helpers.parse_no_char(ctx, teststr)

        try:
            parsed = await transformer
        except EvaluationError as err:
            return await helpers.handle_alias_exception(ctx, err)
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
        try:
            char = await Character.from_ctx(ctx)
            transformer = helpers.parse_with_character(ctx, char, teststr)
        except NoCharacter:
            transformer = helpers.parse_no_char(ctx, teststr)

        try:
            parsed = await transformer
        except EvaluationError as err:
            return await helpers.handle_alias_exception(ctx, err)

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
