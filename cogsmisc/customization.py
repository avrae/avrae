"""
Created on Jan 30, 2017

@author: andrew
"""

import asyncio
import io
import re
import textwrap
from collections import Counter
from math import ceil

import d20
import disnake
from disnake.ext import commands
from disnake.ext.commands import BucketType, NoPrivateMessage

import aliasing.utils
import ui
from aliasing import helpers, personal, workshop
from aliasing.errors import EvaluationError
from aliasing.workshop import WORKSHOP_ADDRESS_RE
from cogs5e.models import embeds
from cogs5e.models.character import Character
from cogs5e.models.embeds import EmbedWithAuthor
from cogs5e.models.errors import InvalidArgument, NoCharacter, NotAllowed
from utils import checks
from utils.constants import DAMAGE_TYPES, SAVE_NAMES, SKILL_NAMES, STAT_ABBREVIATIONS, STAT_NAMES
from utils.functions import a_or_an, confirm, get_selection, search_and_select, user_from_id

ALIASER_ROLES = ("server aliaser", "dragonspeaker")

STAT_MOD_NAMES = ("strengthMod", "dexterityMod", "constitutionMod", "intelligenceMod", "wisdomMod", "charismaMod")

STAT_VAR_NAMES = (
    STAT_NAMES
    + SAVE_NAMES
    + STAT_MOD_NAMES
    + (
        "armor",
        "color",
        "description",
        "hp",
        "image",
        "level",
        "name",
        "proficiencyBonus",
        "spell",
    )
)

SPECIAL_ARGS = {"crit", "nocrit", "hit", "miss", "eadv", "adv", "dis", "pass", "fail", "noconc", "max", "magical"}

# Don't use any iterables with a string as only element. It will add all the chars instead of the string
SPECIAL_ARGS.update(DAMAGE_TYPES, STAT_NAMES, STAT_ABBREVIATIONS, SKILL_NAMES, STAT_VAR_NAMES, SAVE_NAMES)


class CollectableManagementGroup(commands.Group):
    def __init__(
        self,
        func=None,
        *,
        personal_cls,
        workshop_cls,
        workshop_sub_meth,
        is_alias,
        is_server,
        before_edit_check=None,
        **kwargs,
    ):
        """
        :type func: Coroutine
        :type workshop_sub_meth: Coroutine
        :type is_alias: bool
        :type is_server: bool
        :type before_edit_check: Coroutine[Context, Optional[str], bool] -> None
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
        self.binding_key = "alias_bindings" if self.is_alias else "snippet_bindings"
        self.obj_name = "alias" if self.is_alias else "snippet"
        self.obj_copy_command = self.obj_name  # when an item is viewed, we show the non-server version of the command
        self.obj_name_pl = "aliases" if self.is_alias else "snippets"
        self.command_group_name = self.obj_name

        if self.is_server:
            self.obj_name = f"server {self.obj_name}"
            self.obj_name_pl = f"server {self.obj_name_pl}"
            self.command_group_name = f"serv{self.command_group_name}"
            self.owner_from_ctx = lambda ctx: str(ctx.guild.id)
        else:
            self.owner_from_ctx = lambda ctx: str(ctx.author.id)

        # register commands
        self._register_commands()

    def _register_commands(self):
        self.list = self.command(name="list", help=f"Lists all {self.obj_name_pl}.")(self.list)
        self.delete = self.command(name="delete", aliases=["remove"], help=f"Deletes a {self.obj_name}.")(self.delete)
        self.subscribe = self.command(
            name="subscribe", aliases=["sub"], help="Subscribes to all aliases and snippets in a workshop collection."
        )(self.subscribe)
        self.unsubscribe = self.command(
            name="unsubscribe",
            aliases=["unsub"],
            help="Unsubscribes from all aliases and snippets in a given workshop collection.",
        )(self.unsubscribe)
        self.autofix = self.command(
            name="autofix",
            hidden=True,
            help="Ensures that all server and subscribed workshop aliases have unique names.",
        )(self.autofix)
        self.rename = self.command(
            name="rename",
            help=f"Renames {a_or_an(self.obj_name)} or subscribed workshop {self.obj_name} to a new name.",
        )(self.rename)
        if not self.is_server:
            self.serve = self.command(
                name="serve",
                help=(
                    f"Sets {a_or_an(self.obj_name)} as a server {self.obj_name} or subscribes the server to the "
                    "workshop collection it is found in."
                ),
            )(self.serve)

    # we override the Group copy command since we register commands in __init__
    # and Group.copy() tries to reregister commands
    def copy(self):
        return commands.Command.copy(self)

    def command(self, *args, **kwargs):
        kwargs.setdefault("checks", self.checks)  # inherit all checks of parent command
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

        out = (
            f"{self.obj_name.capitalize()} `{name}` added.```py\n{ctx.prefix}{self.obj_copy_command} {name} {code}\n```"
        )

        if len(out) > 2000:
            out = f"{self.obj_name.capitalize()} `{name}` added.\nCommand output too long to display."

        await ctx.send(out)

    async def _view(self, ctx, name):
        collectable = await helpers.get_collectable_named(
            ctx,
            name,
            self.personal_cls,
            self.workshop_cls,
            self.workshop_sub_meth,
            self.is_alias,
            self.obj_name,
            self.obj_name_pl,
            self.name,
        )
        if collectable is None:
            return await ctx.send(f"No {self.obj_name} named {name} found.")
        elif isinstance(collectable, self.personal_cls):  # personal
            await send_long_code_text(
                ctx,
                outside_codeblock=f"**{name}**:",
                inside_codeblock=f"{ctx.prefix}{self.obj_copy_command} {collectable.name} {collectable.code}",
                codeblock_language="py",
            )
            return
        else:  # collection
            embed = EmbedWithAuthor(ctx)
            the_collection = await collectable.load_collection(ctx)
            owner = await user_from_id(ctx, the_collection.owner)
            embed.title = f"{ctx.prefix}{name}" if self.is_alias else name
            embed.description = f"From {the_collection.name} by {owner}.\n[View on Workshop]({the_collection.url})"
            embeds.add_fields_from_long_text(embed, "Help", collectable.docs or "No documentation.")

            if isinstance(collectable, workshop.WorkshopAlias):
                await collectable.load_subcommands(ctx)
                if collectable.subcommands:
                    subcommands = "\n".join(f"**{sc.name}** - {sc.short_docs}" for sc in collectable.subcommands)
                    embed.add_field(name="Subcommands", value=subcommands, inline=False)

            return await ctx.send(embed=embed)

    async def list(self, ctx, page: int = 1):
        ep = embeds.EmbedPaginator(EmbedWithAuthor(ctx))

        collections = []  # tuples (name, bindings)

        # load all the user's aliases
        user_objs = await self.personal_cls.get_ctx_map(ctx)
        user_obj_names = list(user_objs.keys())
        if user_obj_names:
            collections.append((f"Your {self.obj_name_pl.title()}", ", ".join(sorted(user_obj_names))))

        async for subscription_doc in self.workshop_sub_meth(ctx):
            try:
                the_collection = await workshop.WorkshopCollection.from_id(ctx, subscription_doc["object_id"])
            except workshop.CollectionNotFound:
                continue
            if bindings := subscription_doc[self.binding_key]:
                collections.append((the_collection.name, ", ".join(sorted(ab["name"] for ab in bindings))))

        # build the resulting embed
        if collections:
            amt_per_page = 20
            total = len(collections)
            maxpage = ceil(total / amt_per_page)
            page = max(1, min(page, maxpage))
            pages = [collections[i : i + amt_per_page] for i in range(0, total, amt_per_page)]
            for name, bindings_str in pages[page - 1]:
                ep.add_field(name, bindings_str)
            if total > amt_per_page:
                ep.set_footer(value=f"Page [{page}/{maxpage}] | {ctx.prefix}{self.command_group_name} list <page>")
        else:
            ep.add_description(
                f"You have no {self.obj_name_pl}. Check out the [Alias Workshop]"
                "(https://avrae.io/dashboard/workshop) to get some, "
                "or [make your own](https://avrae.readthedocs.io/en/latest/aliasing/api.html)!"
            )

        await ep.send_to(ctx)

    async def delete(self, ctx, name):
        if self.before_edit_check:
            await self.before_edit_check(ctx, name, delete=True)

        obj = await self.personal_cls.get_named(name, ctx)
        if obj is None:
            return await ctx.send(
                f"{self.obj_name.capitalize()} not found. If this is a workshop {self.obj_name}, you "
                "can unsubscribe on the Avrae Dashboard at <https://avrae.io/dashboard/workshop/my-subscriptions> "
                f"or by using `{ctx.prefix}{self.name} unsubscribe <collection name>`."
            )
        await obj.delete(ctx.bot.mdb)
        await ctx.send(f"{self.obj_name.capitalize()} {name} removed.")

    async def subscribe(self, ctx, url):
        coll_match = re.match(WORKSHOP_ADDRESS_RE, url)
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
            embed.add_field(
                name="Server Aliases" if self.is_server else "Aliases",
                value=", ".join(sorted(a.name for a in the_collection.aliases)),
            )
        if the_collection.snippets:
            embed.add_field(
                name="Server Snippets" if self.is_server else "Snippets",
                value=", ".join(sorted(a.name for a in the_collection.snippets)),
            )
        await ctx.send(embed=embed)

    async def unsubscribe(self, ctx, name):
        if self.before_edit_check:
            await self.before_edit_check(ctx)

        # get the collection by URL or name
        coll_match = re.match(WORKSHOP_ADDRESS_RE, name)
        if coll_match is None:
            # load all subscribed collections to search
            subscribed_collections = []
            async for subscription_doc in self.workshop_sub_meth(ctx):
                try:
                    coll = await workshop.WorkshopCollection.from_id(ctx, subscription_doc["object_id"])
                    subscribed_collections.append(coll)
                except workshop.CollectionNotFound:
                    continue
            the_collection = await search_and_select(ctx, subscribed_collections, name, key=lambda c: c.name)
        else:
            collection_id = coll_match.group(1)
            the_collection = await workshop.WorkshopCollection.from_id(ctx, collection_id)

        if self.is_server:
            await the_collection.unset_server_active(ctx)
        else:
            await the_collection.unsubscribe(ctx)

        embed = EmbedWithAuthor(ctx)
        embed.title = f"Unsubscribed from {the_collection.name}"
        embed.url = the_collection.url
        embed.description = the_collection.description
        await ctx.send(embed=embed)

    async def autofix(self, ctx):
        if self.before_edit_check:
            await self.before_edit_check(ctx)

        # counter: how many objects are currently bound to a given name?
        # used to assign index of new name
        name_indices = Counter()
        for name in await self.personal_cls.get_ctx_map(ctx):
            name_indices[name] += 1

        rename_tris = []  # (old name, new name, collection name)
        to_do = []

        async for subscription_doc in self.workshop_sub_meth(ctx):
            doc_changed = False
            the_collection = await workshop.WorkshopCollection.from_id(ctx, subscription_doc["object_id"])

            for binding in subscription_doc[self.binding_key]:
                old_name = binding["name"]
                if new_index := name_indices[old_name]:
                    new_name = f"{binding['name']}-{new_index}"
                    # do rename
                    binding["name"] = new_name
                    rename_tris.append((old_name, new_name, the_collection.name))
                    doc_changed = True
                name_indices[old_name] += 1

            if doc_changed:  # queue writing the new subscription object to the db
                update_meth = (
                    the_collection.update_alias_bindings if self.is_alias else the_collection.update_snippet_bindings
                )
                # this creates a Coroutine object that is not executed until it is awaited by asyncio.gather below
                # the magic of coroutines!
                to_do.append(update_meth(ctx, subscription_doc))

        # confirm mass change
        changes = "\n".join([f"`{old}` ({collection}) -> `{new}`" for old, new, collection in rename_tris])
        response = await confirm(
            ctx,
            (
                f"This will rename {len(rename_tris)} {self.obj_name_pl}. "
                "Do you want to continue? (Reply with yes/no)\n"
                f"{changes}"
            ),
        )
        if not response:
            return await ctx.send("Ok, cancelling.")

        # execute the pending changes
        await asyncio.gather(*to_do)
        the_renamed = "\n".join([f"`{old}` ({collection}) is now `{new}`" for old, new, collection in rename_tris])
        await ctx.send(f"Renamed {len(rename_tris)} {self.obj_name_pl}!\n{the_renamed}")

    async def rename(self, ctx, old_name, new_name):
        if self.before_edit_check:
            await self.before_edit_check(ctx, new_name)

        self.personal_cls.precreate_checks(new_name, "")

        # list of (name, (alias or sub doc, collection or None))
        choices = []
        if personal_obj := await self.personal_cls.get_named(old_name, ctx):
            choices.append((f"{old_name} ({self.obj_name})", (personal_obj, None)))

        # get list of (subscription object ids, subscription doc)
        async for subscription_doc in self.workshop_sub_meth(ctx):
            the_collection = await workshop.WorkshopCollection.from_id(ctx, subscription_doc["object_id"])
            for binding in subscription_doc[self.binding_key]:
                if binding["name"] == old_name:
                    choices.append((f"{old_name} ({the_collection.name})", (subscription_doc, the_collection)))

        result = await get_selection(ctx, choices, key=lambda pair: pair[0])
        _, (old_obj, collection) = result

        if isinstance(old_obj, self.personal_cls):
            if await self.personal_cls.get_named(new_name, ctx):
                return await ctx.send(f"You already have a {self.obj_name} named {new_name}.")
            await old_obj.rename(ctx.bot.mdb, new_name)
            return await ctx.send(f"Okay, renamed the {self.obj_name} {old_name} to {new_name}.")
        else:  # old_obj is actually a subscription doc
            sub_doc = old_obj
            for binding in sub_doc[self.binding_key]:
                if binding["name"] == old_name:
                    binding["name"] = new_name

            update_meth = collection.update_alias_bindings if self.is_alias else collection.update_snippet_bindings
            await update_meth(ctx, sub_doc)
            return await ctx.send(
                f"Okay, the workshop {self.obj_name} that was bound to {old_name} is now bound to {new_name}."
            )

    async def serve(self, ctx, name):
        # get the personal alias/snippet
        if self.is_alias:
            personal_obj = await helpers.get_personal_alias_named(ctx, name)
            check_coro = _servalias_before_edit
        else:
            personal_obj = await helpers.get_personal_snippet_named(ctx, name)
            check_coro = _servsnippet_before_edit

        if personal_obj is None:
            return await ctx.send(f"You do not have {a_or_an(self.obj_name)} named `{name}`.")
        await check_coro(ctx, name)

        # If the alias is a workshop alias we need to get the workshopCollection and set it as active.
        if not isinstance(personal_obj, self.personal_cls):
            await personal_obj.load_collection(ctx)
            collection = personal_obj.collection
            response = await confirm(
                ctx,
                (
                    f"This action will subscribe the server to the `{collection.name}` workshop collection, found at "
                    f"<{collection.url}>. This will add {collection.alias_count} aliases and "
                    f"{collection.snippet_count} snippets to the server. Do you want to continue? (Reply with yes/no)"
                ),
            )
            if not response:
                return await ctx.send("Ok, cancelling.")
            await collection.set_server_active(ctx)  # this loads the aliases/snippets

            embed = EmbedWithAuthor(ctx)
            embed.title = f"Subscribed to {collection.name}"
            embed.url = collection.url
            embed.description = collection.description
            if collection.aliases:
                embed.add_field(name="Server Aliases", value=", ".join(sorted(a.name for a in collection.aliases)))
            if collection.snippets:
                embed.add_field(name="Server Snippets", value=", ".join(sorted(a.name for a in collection.snippets)))
            return await ctx.send(embed=embed)

        # else it's a personal alias/snippet
        if self.is_alias:
            existing_server_obj = await personal.Servalias.get_named(personal_obj.name, ctx)
            server_obj = personal.Servalias.new(personal_obj.name, personal_obj.code, ctx.guild.id)
        else:
            existing_server_obj = await personal.Servsnippet.get_named(personal_obj.name, ctx)
            server_obj = personal.Servsnippet.new(personal_obj.name, personal_obj.code, ctx.guild.id)

        # check if it overwrites anything
        if existing_server_obj is not None and not await confirm(
            ctx,
            (
                f"There is already an existing server {self.obj_name} named `{name}`. Do you want to overwrite it? "
                "(Reply with yes/no)"
            ),
        ):
            return await ctx.send("Ok, aborting.")

        await server_obj.commit(ctx.bot.mdb)
        out = (
            f"Server {self.obj_name} `{server_obj.name}` added."
            f"```py\n{ctx.prefix}{self.obj_copy_command} {server_obj.name} {server_obj.code}\n```"
        )

        if len(out) > 2000:
            out = f"Server {self.obj_name} `{server_obj.name}` added.Command output too long to display."

        await ctx.send(out)


# helpers
async def _can_edit_servaliases(ctx):
    """
    Returns whether a user can edit server aliases in the current context.
    """
    return (
        ctx.author.guild_permissions.administrator
        or any(r.name.lower() in ALIASER_ROLES for r in ctx.author.roles)
        or await ctx.bot.is_owner(ctx.author)
    )


# noinspection PyUnusedLocal
async def _alias_before_edit(ctx, name=None, delete=False):
    if name and name in ctx.bot.all_commands:
        raise InvalidArgument(f"`{name}` is already a builtin command. Try another name.")


# noinspection PyUnusedLocal
async def _servalias_before_edit(ctx, name=None, delete=False):
    if not await _can_edit_servaliases(ctx):
        raise NotAllowed(
            "You do not have permission to edit server aliases. Either __Administrator__ "
            'Discord permissions or a role named "Server Aliaser" or "Dragonspeaker" '
            "is required."
        )
    await _alias_before_edit(ctx, name)


async def _servsnippet_before_edit(ctx, name=None, delete=False):
    if not await _can_edit_servaliases(ctx):
        raise NotAllowed(
            "You do not have permission to edit server snippets. Either __Administrator__ "
            'Discord permissions or a role named "Server Aliaser" or "Dragonspeaker" '
            "is required."
        )
    await _snippet_before_edit(ctx, name, delete)


async def _snippet_before_edit(ctx, name=None, delete=False):
    if delete:
        return
    confirmation = None
    # special arg checking
    if not name:
        return
    name = name.lower()
    if name in SPECIAL_ARGS or name.startswith("-"):
        confirmation = (
            f"**Warning:** Creating a snippet named `{name}` will prevent you from using a built-in argument `{name}`"
            " if one exists.\nAre you sure you want to create this snippet? (Reply with yes/no)"
        )
    # roll string checking
    try:
        d20.parse(name)
    except d20.RollSyntaxError:
        pass
    else:
        confirmation = (
            f"**Warning:** Creating a snippet named `{name}` might cause hidden problems if you try to use the same"
            " roll in other commands.\nAre you sure you want to create this snippet? (Reply with yes/no)"
        )

    if confirmation is not None:
        if not await confirm(ctx, confirmation):
            raise InvalidArgument("Ok, cancelling.")


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
            await self.bot.rdb.jset("default_commands", cmds)

    @commands.command()
    @commands.guild_only()
    async def prefix(self, ctx, prefix: str = None):
        """
        Sets the bot's prefix for this server.

        You must have Manage Server permissions or a role called "Bot Admin" to use this command. Due to a possible Discord conflict, a prefix beginning with `/` will require confirmation.

        Forgot the prefix? Reset it with "@Avrae#6944 prefix !".
        """
        guild_id = str(ctx.guild.id)
        if prefix is None:
            current_prefix = await self.bot.get_guild_prefix(ctx.guild)
            return await ctx.send(
                f"My current prefix is: `{current_prefix}`. You can run commands like "
                f"`{current_prefix}roll 1d20` or by mentioning me!"
            )

        if not await checks.admin_or_permissions(manage_guild=True).predicate(ctx):
            return await ctx.send("You do not have permissions to change the guild prefix.")

        # Check for Discord Slash-command conflict
        if prefix.startswith("/"):
            if not await confirm(
                ctx,
                (
                    "Setting a prefix that begins with / may cause issues. "
                    "Are you sure you want to continue? (Reply with yes/no)"
                ),
            ):
                return await ctx.send("Ok, cancelling.")
        else:
            if not await confirm(
                ctx,
                (
                    f"Are you sure you want to set my prefix to `{prefix}`? This will affect "
                    "everyone on this server! (Reply with yes/no)"
                ),
            ):
                return await ctx.send("Ok, cancelling.")

        # insert into cache
        self.bot.prefixes[guild_id] = prefix

        # update db
        await self.bot.mdb.prefixes.update_one({"guild_id": guild_id}, {"$set": {"prefix": prefix}}, upsert=True)

        await ctx.send(f"Prefix set to `{prefix}` for this server. Use commands like `{prefix}roll` now!")

    @commands.command()
    @commands.max_concurrency(1, BucketType.user)
    async def multiline(self, ctx, *, cmds: str):
        """
        Runs each line as a separate command, with a 1 second delay between commands.

        Usage:
        "!multiline
        !roll 1d20
        !spell Fly
        !monster Rat"
        """
        # Remove the first prefix to simplify loop. Split only on actual new commands
        cmds = cmds.replace(ctx.prefix, "", 1).split(f"\n{ctx.prefix}")
        for c in cmds[:20]:
            ctx.message.content = ctx.prefix + c
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
        name="alias",
        invoke_without_command=True,
        help="""
        Creates a custom user command.
        After an alias has been added, you can run the command with !<alias_name>.
        
        If a user and a server have aliases with the same name, the user alias will take priority.
        Note that aliases cannot call other aliases.
        
        Check out the [Aliasing Basics](https://avrae.readthedocs.io/en/latest/aliasing/aliasing.html) and [Aliasing Documentation](https://avrae.readthedocs.io/en/latest/aliasing/api.html) for more information.
        """,
    )

    @alias.command(name="deleteall", aliases=["removeall"])
    async def alias_deleteall(self, ctx):
        """Deletes ALL user aliases."""
        if not await confirm(
            ctx,
            (
                "This will delete **ALL** of your personal user aliases (it will not affect workshop subscriptions). "
                "Are you *absolutely sure* you want to continue?\n"
                "Type `Yes, I am sure` to confirm."
            ),
            response_check=lambda r: r == "Yes, I am sure",
        ):
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
        name="servalias",
        invoke_without_command=True,
        help="""
        Adds an alias that the entire server can use.
        Requires __Administrator__ Discord permissions or a role called "Server Aliaser" or "Dragonspeaker".
        If a user and a server have aliases with the same name, the user alias will take priority.
        """,
        checks=[guild_only_check],
        aliases=["serveralias"],
    )

    snippet = CollectableManagementGroup(
        personal_cls=personal.Snippet,
        workshop_cls=workshop.WorkshopSnippet,
        workshop_sub_meth=workshop.WorkshopCollection.my_subs,
        is_alias=False,
        is_server=False,
        before_edit_check=_snippet_before_edit,
        name="snippet",
        invoke_without_command=True,
        help="""
        Creates a snippet to use in certain commands.
        Ex: *!snippet sneak -d "2d6[slashing]"* can be used as *!a sword sneak*.

        If a user and a server have snippets with the same name, the user snippet will take priority.

        Check out the [Aliasing Basics](https://avrae.readthedocs.io/en/latest/aliasing/aliasing.html) and [Aliasing Documentation](https://avrae.readthedocs.io/en/latest/aliasing/api.html) for more information.
        """,
    )

    @snippet.command(name="deleteall", aliases=["removeall"])
    async def snippet_deleteall(self, ctx):
        """Deletes ALL user snippets."""
        if not await confirm(
            ctx,
            (
                "This will delete **ALL** of your personal user snippets (it will not affect workshop subscriptions). "
                "Are you *absolutely sure* you want to continue?\n"
                "Type `Yes, I am sure` to confirm."
            ),
            response_check=lambda r: r == "Yes, I am sure",
        ):
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
        name="servsnippet",
        invoke_without_command=True,
        help="""
        Creates a snippet that the entire server can use.
        Requires __Administrator__ Discord permissions or a role called "Server Aliaser" or "Dragonspeaker".
        If a user and a server have snippets with the same name, the user snippet will take priority.
        """,
        checks=[guild_only_check],
        aliases=["serversnippet"],
    )

    @commands.command()
    async def test(self, ctx, *, teststr):
        """Parses `teststr` as if it were in an alias, for testing.
        Note: Not recommended to be used in actual aliases, as it can lead to unexpected behaviour. You will probably want to use `!echo` instead.
        """
        try:
            char = await ctx.get_character()
        except NoCharacter:
            char = None

        try:
            parsed = await helpers.parse_draconic(
                ctx, teststr, character=char, execution_scope=aliasing.utils.ExecutionScope.COMMAND_TEST
            )
        except EvaluationError as err:
            return await helpers.handle_alias_exception(ctx, err)
        await ctx.send(f"{ctx.author.display_name}: {parsed}")

    @commands.command()
    async def tembed(self, ctx, *, teststr):
        """Parses `teststr` as if it were in an alias, for testing, then creates and prints an Embed.
        Note: Not recommended to be used in actual aliases, as it can lead to unexpected behaviour. You will probably want to use `!embed` instead.

        Arguments: -title [title]
        -desc [description text]
        -thumb [image url]
        -image [image url]
        -footer [footer text]
        -f ["Field Title|Field Text"]
        -color [hex color] or `<color>` for character color, leave blank for random color.
        -t [timeout (0..600)]
        """
        try:
            char = await ctx.get_character()
        except NoCharacter:
            char = None

        try:
            parsed = await helpers.parse_draconic(
                ctx, teststr, character=char, execution_scope=aliasing.utils.ExecutionScope.COMMAND_TEST
            )
        except EvaluationError as err:
            return await helpers.handle_alias_exception(ctx, err)

        embed_command = self.bot.get_command("embed")
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

        character: Character = await ctx.get_character()

        if value is None:  # display value
            cvar = character.get_scope_locals().get(name)
            if cvar is None:
                return await ctx.send("This cvar is not defined.")
            return await send_long_code_text(
                ctx, outside_codeblock=f"**{name}**:".replace("_", "\_"), inside_codeblock=cvar
            )

        helpers.set_cvar(character, name, value)

        await character.commit(ctx)
        await ctx.send("Character variable `{}` set to: `{}`".format(name, value))

    @cvar.command(name="remove", aliases=["delete"])
    async def remove_cvar(self, ctx, name):
        """Deletes a cvar from the currently active character."""
        char: Character = await ctx.get_character()
        if name not in char.cvars:
            return await ctx.send("Character variable not found.")

        del char.cvars[name]

        await char.commit(ctx)
        await ctx.send("Character variable {} removed.".format(name))

    @cvar.command(name="deleteall", aliases=["removeall"])
    async def cvar_deleteall(self, ctx):
        """Deletes ALL character variables for the active character."""
        char: Character = await ctx.get_character()
        if not await confirm(
            ctx,
            (
                f"This will delete **ALL** of your character variables for {char.name}. "
                "Are you *absolutely sure* you want to continue?\n"
                "Type `Yes, I am sure` to confirm."
            ),
            response_check=lambda r: r == "Yes, I am sure",
        ):
            return await ctx.send("Unconfirmed. Aborting.")

        char.cvars = {}

        await char.commit(ctx)
        return await ctx.send(f"OK. I have deleted all of {char.name}'s cvars.")

    @cvar.command(name="list")
    async def list_cvar(self, ctx):
        """Lists all cvars for the currently active character."""
        character: Character = await ctx.get_character()
        await ctx.send(
            "{}'s character variables:\n{}".format(character.name, ", ".join(sorted(character.cvars.keys()))).replace(
                "_", "\_"
            )
        )

    @commands.group(invoke_without_command=True, aliases=["uvar"])
    async def uservar(self, ctx, name=None, *, value=None):
        """
        Commands to manage user variables for use in snippets and aliases.
        User variables can be called in the `-phrase` tag by surrounding the variable name with `{}` (calculates) or `<>` (prints).
        Arguments surrounded with `{{}}` will be evaluated as a custom script.
        See https://avrae.io/cheatsheets/aliasing for more help."""
        if name is None:
            return await self.uvar_list(ctx)

        user_vars = await helpers.get_uvars(ctx)

        if value is None:  # display value
            uvar = user_vars.get(name)
            if uvar is None:
                return await ctx.send("This uvar is not defined.")
            return await send_long_code_text(ctx, outside_codeblock=f"**{name}**:", inside_codeblock=uvar)

        if name in STAT_VAR_NAMES or not name.isidentifier():
            return await ctx.send("Could not create uvar: already builtin, or contains invalid character!")

        await helpers.set_uvar(ctx, name, value)
        await ctx.send("User variable `{}` set to: `{}`".format(name, value))

    @uservar.command(name="remove", aliases=["delete"])
    async def uvar_remove(self, ctx, name):
        """Deletes a uvar from the user."""
        result = await self.bot.mdb.uvars.delete_one({"owner": str(ctx.author.id), "name": name})
        if not result.deleted_count:
            return await ctx.send("Uvar does not exist.")
        await ctx.send("User variable {} removed.".format(name))

    @uservar.command(name="list")
    async def uvar_list(self, ctx):
        """Lists all uvars for the user."""
        user_vars = await helpers.get_uvars(ctx)
        await ctx.send("Your user variables:\n{}".format(", ".join(sorted([name for name in user_vars.keys()]))))

    @uservar.command(name="deleteall", aliases=["removeall"])
    async def uvar_deleteall(self, ctx):
        """Deletes ALL user variables."""
        if not await confirm(
            ctx,
            (
                "This will delete **ALL** of your user variables (uvars). "
                "Are you *absolutely sure* you want to continue?\n"
                "Type `Yes, I am sure` to confirm."
            ),
            response_check=lambda r: r == "Yes, I am sure",
        ):
            return await ctx.send("Unconfirmed. Aborting.")

        await self.bot.mdb.uvars.delete_many({"owner": str(ctx.author.id)})
        return await ctx.send("OK. I have deleted all your uvars.")

    @commands.group(invoke_without_command=True, aliases=["svar"])
    @commands.guild_only()
    async def servervar(self, ctx, name=None, *, value=None):
        """
        Commands to manage server variables for use in snippets and aliases.

        Server variables may only be set by those with permissions to create server aliases (see `!help servalias`),
        must be explicitly retrieved in an alias, and are read-only.

        These are usually used to set server-wide defaults for aliases without editing the code.

        See https://avrae.io/cheatsheets/aliasing for more help.
        """
        if name is None:
            return await self.svar_list(ctx)

        if value is None:  # display value
            svar = await helpers.get_svar(ctx, name)
            if svar is None:
                return await ctx.send("This svar is not defined.")
            return await send_long_code_text(ctx, outside_codeblock=f"**{name}**:", inside_codeblock=svar)

        if not await _can_edit_servaliases(ctx):
            return await ctx.send(
                "You do not have permissions to edit server variables. Either __Administrator__ "
                'Discord permissions or a role named "Server Aliaser" or "Dragonspeaker" '
                "is required."
            )

        if name in STAT_VAR_NAMES or not name.isidentifier():
            return await ctx.send("Could not create svar: already builtin, or contains invalid character!")

        await helpers.set_svar(ctx, name, value)
        await ctx.send(f"Server variable `{name}` set to: `{value}`")

    @servervar.command(name="remove", aliases=["delete"])
    @commands.guild_only()
    async def svar_remove(self, ctx, name):
        """Deletes a svar from the server."""
        if not await _can_edit_servaliases(ctx):
            return await ctx.send(
                "You do not have permissions to edit server variables. Either __Administrator__ "
                'Discord permissions or a role named "Server Aliaser" or "Dragonspeaker" '
                "is required."
            )

        result = await self.bot.mdb.svars.delete_one({"owner": ctx.guild.id, "name": name})
        if not result.deleted_count:
            return await ctx.send("Svar does not exist.")
        await ctx.send(f"Server variable {name} removed.")

    @servervar.command(name="list")
    @commands.guild_only()
    async def svar_list(self, ctx):
        """Lists all svars for the server."""
        server_vars = await helpers.get_svars(ctx)
        sorted_vars = ", ".join(sorted(name for name in server_vars.keys()))
        await ctx.send(f"This server's server variables:\n{sorted_vars}")

    @commands.group(invoke_without_command=True, aliases=["gvar"])
    async def globalvar(self, ctx, name=None):
        """Commands to manage global, community variables for use in snippets and aliases.
        If run without a subcommand, shows the value of a global variable.
        Global variables are readable by all users, but only editable by the creator.
        Global variables must be accessed through scripting, with `get_gvar(gvar_id)`.
        See https://avrae.io/cheatsheets/aliasing for more help."""
        if name is None:
            return await self.gvar_list(ctx)

        gvar = await self.bot.mdb.gvars.find_one({"key": name})
        if gvar is None:
            return await ctx.send("This gvar does not exist.")
        await send_long_code_text(
            ctx,
            outside_codeblock=f"**{name}**:\n*Owner: {gvar['owner_name']}*",
            inside_codeblock=gvar["value"],
            too_long_message=(
                "This gvar is too long to display in a single message. I've "
                "attached it here, but you can also view it at "
                f"<https://avrae.io/dashboard/gvars?lookup={name}>."
            ),
        )

    @globalvar.command(name="create")
    async def gvar_create(self, ctx, *, value):
        """Creates a global variable.
        A name will be randomly assigned upon creation."""
        name = await helpers.create_gvar(ctx, value)
        await ctx.send(f"Created global variable `{name}`.")

    @globalvar.command(name="edit")
    async def gvar_edit(self, ctx, name, *, value):
        """Edits a global variable."""
        await helpers.update_gvar(ctx, name, value)
        await ctx.send(f"Global variable `{name}` edited.")

    @globalvar.command(name="editor")
    async def gvar_editor(self, ctx, name, user: disnake.Member = None):
        """Toggles the editor status of a user."""
        gvar = await self.bot.mdb.gvars.find_one({"key": name})
        if gvar is None:
            return await ctx.send("Global variable not found.")

        if user is not None:
            if gvar["owner"] != str(ctx.author.id):
                return await ctx.send("You are not the owner of this variable.")
            else:
                e = gvar.get("editors", [])
                if str(user.id) in e:
                    e.remove(str(user.id))
                    msg = f"Removed {user} from the editor list."
                else:
                    e.append(str(user.id))
                    msg = f"Added {user} to the editor list."
                await self.bot.mdb.gvars.update_one({"key": name}, {"$set": {"editors": e}})
            await ctx.send(f"Global variable `{name}` edited: {msg}")
        else:
            embed = EmbedWithAuthor(ctx)
            embed.title = "Editors"
            editor_mentions = []
            for editor in gvar.get("editors", []):
                editor_mentions.append(f"<@{editor}>")
            embed.description = ", ".join(editor_mentions) or "No editors."
            await ctx.send(embed=embed)

    @globalvar.command(name="remove", aliases=["delete"])
    async def gvar_remove(self, ctx, name):
        """Deletes a global variable."""
        gvar = await self.bot.mdb.gvars.find_one({"key": name})
        if gvar is None:
            return await ctx.send("Global variable not found.")
        elif gvar["owner"] != str(ctx.author.id):
            return await ctx.send("You are not the owner of this variable.")
        else:
            if await confirm(ctx, f"Are you sure you want to delete `{name}`? (Reply with yes/no)"):
                await self.bot.mdb.gvars.delete_one({"key": name})
            else:
                return await ctx.send("Ok, cancelling.")

        await ctx.send("Global variable {} removed.".format(name))

    @globalvar.command(name="list")
    async def gvar_list(self, ctx):
        """Lists all global variables for the user."""
        user_vars = []
        async for gvar in self.bot.mdb.gvars.find({"owner": str(ctx.author.id)}):
            user_vars.append((gvar["key"], gvar["value"]))
        gvar_list = [f"`{k}`: {textwrap.shorten(v, 20)}" for k, v in sorted(user_vars, key=lambda i: i[0])]
        say_list = [""]
        for g in gvar_list:
            if len(g) + len(say_list[-1]) < 1900:
                say_list[-1] += f"\n{g}"
            else:
                say_list.append(g)
        await ctx.send("Your global variables:{}".format(say_list[0]))
        for m in say_list[1:]:
            await ctx.send(m)

    @commands.command(aliases=["servsettings"])
    @commands.guild_only()
    @checks.admin_or_permissions(manage_guild=True)
    async def server_settings(self, ctx):
        """Opens the server settings menu. You must have *Manage Server* permissions to use this command."""
        guild_settings = await ctx.get_server_settings()
        settings_ui = ui.ServerSettingsUI.new(ctx.bot, owner=ctx.author, settings=guild_settings, guild=ctx.guild)
        await settings_ui.send_to(ctx)

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
    #     await ctx.send(file=disnake.File(out, f'{address}.txt'))


async def send_long_code_text(
    destination, outside_codeblock, inside_codeblock, codeblock_language="", too_long_message=None
):
    """Sends *text* to the destination, or if it's too long, embeds it as a txt file and uploads it with a message."""
    if too_long_message is None:
        too_long_message = "This output is too large to fit in a message. I've attached it as a file here."

    text = f"{outside_codeblock} ```{codeblock_language}\n{inside_codeblock}\n```"

    if len(text) < 2000:
        await destination.send(text)
    elif len(inside_codeblock) < 5 * 10e6:
        out = io.StringIO(inside_codeblock)
        await destination.send(f"{outside_codeblock}\n{too_long_message}", file=disnake.File(out, "output.txt"))
    else:
        await destination.send("This output is too large.")


def setup(bot):
    bot.add_cog(Customization(bot))
