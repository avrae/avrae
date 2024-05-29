import copy
import textwrap
import traceback
import uuid
from contextlib import suppress
from typing import List, TYPE_CHECKING

import disnake
import draconic
from disnake.ext.commands import ArgumentParsingError

from aliasing import evaluators
from aliasing.api.functions import AliasException
from aliasing.constants import CVAR_SIZE_LIMIT, GVAR_SIZE_LIMIT, SVAR_SIZE_LIMIT, UVAR_SIZE_LIMIT, VAR_NAME_LIMIT
from aliasing.errors import AliasNameConflict, CollectableNotFound, CollectableRequiresLicenses, EvaluationError
from aliasing.personal import Alias, Servalias, Servsnippet, Snippet
from aliasing.utils import ExecutionScope
from aliasing.workshop import WorkshopAlias, WorkshopCollection, WorkshopSnippet
from cogs5e.models.embeds import EmbedWithAuthor
from cogs5e.models.errors import AvraeException, InvalidArgument, NoCharacter, NotAllowed
from gamedata.compendium import compendium
from gamedata.lookuputils import long_source_name
from utils.argparser import argquote, argsplit
from utils.functions import natural_join

if TYPE_CHECKING:
    from utils.context import AvraeContext


async def handle_aliases(ctx: "AvraeContext"):
    # ctx.prefix: the invoking prefix
    # ctx.invoked_with: the first word
    alias = ctx.invoked_with
    qualified_name_parts = [alias]
    server_invoker = False

    # personal alias/servalias
    try:
        the_alias = await get_personal_alias_named(ctx, alias)
        if the_alias is None and ctx.guild is not None:
            the_alias = await get_server_alias_named(ctx, alias)
            server_invoker = True
    except AliasNameConflict as anc:
        return await ctx.send(str(anc))

    if not the_alias:
        return

    # workshop alias subcommands
    if isinstance(the_alias, WorkshopAlias):
        # loop into subcommands
        while the_alias:
            ctx.view.skip_ws()
            next_word = ctx.view.get_word()
            if not next_word:
                break
            try:
                the_alias = await the_alias.get_subalias_named(ctx, next_word)
                qualified_name_parts.append(next_word)
            except CollectableNotFound:
                ctx.view.undo()
                break

        # workshop alias: handle entitlements check
        try:
            await workshop_entitlements_check(ctx, the_alias)
        except CollectableRequiresLicenses as e:
            return await handle_alias_required_licenses(ctx, e)

    # analytics
    await the_alias.log_invocation(ctx, server_invoker)

    # setup
    execution_scope = ExecutionScope.SERVER_ALIAS if server_invoker else ExecutionScope.PERSONAL_ALIAS
    try:
        command_code = await handle_alias_arguments(the_alias.code, ctx)
    except ArgumentParsingError as e:
        return await ctx.send(f"Error parsing alias arguments: {e}")
    try:
        char = await ctx.get_character()
    except NoCharacter:
        char = None

    # interpret
    try:
        # do a copy before rewriting the content so we don't mess with cache
        # or references to same message in on_message events
        message_copy = copy.copy(ctx.message)
        message_copy.content = await parse_draconic(
            ctx, command_code, character=char, execution_scope=execution_scope, invoking_object=the_alias
        )
    except EvaluationError as err:
        return await handle_alias_exception(ctx, err)
    except Exception as e:
        return await ctx.send(e)

    # log nlp metadata
    qualified_alias_name = " ".join(qualified_name_parts)
    if nlp := ctx.get_nlp_recorder():
        await nlp.on_alias_resolve(
            ctx=ctx,
            alias_name=qualified_alias_name,
            alias_body=the_alias.code,
            content_before=ctx.message.content,
            content_after=message_copy.content,
            prefix=ctx.prefix,
        )

    # use a reimplementation of await ctx.bot.process_commands(message_copy) to set additional metadata
    new_ctx = await ctx.bot.get_context(message_copy)
    new_ctx.nlp_is_alias = True
    await ctx.bot.invoke(new_ctx)


async def handle_alias_arguments(command, ctx):
    """Takes an alias name, alias value, and message and handles percent-encoded args.
    Returns: string"""
    prefix = ctx.prefix
    rawargs = ctx.view.read_rest().strip()

    args = argsplit(rawargs)
    tempargs = args[:]
    new_command = command
    if "%*%" in command:
        new_command = new_command.replace("%*%", argquote(rawargs))
        tempargs = []
    if "&*&" in command:
        new_command = new_command.replace("&*&", rawargs.replace('"', '\\"'))
        tempargs = []
    if "&ARGS&" in command:
        new_command = new_command.replace("&ARGS&", str(args))
        tempargs = []
    for index, value in enumerate(args):
        key = "%{}%".format(index + 1)
        to_remove = False
        if key in command:
            new_command = new_command.replace(key, argquote(value))
            to_remove = True
        key = "&{}&".format(index + 1)
        if key in command:
            new_command = new_command.replace(key, value.replace('"', '\\"'))
            to_remove = True
        if to_remove:
            try:
                tempargs.remove(value)
            except ValueError:
                pass

    quoted_args = " ".join(map(argquote, tempargs))
    return f"{prefix}{new_command} {quoted_args}".strip()


# getters
async def get_collectable_named(
    ctx, name, personal_cls, workshop_cls, workshop_sub_meth, is_alias, obj_name, obj_name_pl, obj_command_name
):
    binding_key = "alias_bindings" if is_alias else "snippet_bindings"

    personal_obj = await personal_cls.get_named(name, ctx)
    # get list of subscription object ids
    subscribed_obj_ids = []
    async for subscription_doc in workshop_sub_meth(ctx):
        for binding in subscription_doc[binding_key]:
            if binding["name"] == name:
                subscribed_obj_ids.append(binding["id"])

    # if only personal, return personal (or none)
    if not subscribed_obj_ids:
        return personal_obj
    # conflicting name errors
    if personal_obj is not None and subscribed_obj_ids:
        subbed_name = obj_name if len(subscribed_obj_ids) == 1 else obj_name_pl
        raise AliasNameConflict(
            f"I found both a local {obj_name} and {len(subscribed_obj_ids)} workshop {subbed_name} "
            f"named {ctx.prefix}{name}. Use `{ctx.prefix}{obj_command_name} autofix` to automatically assign "
            f"all conflicting {obj_name_pl} unique names, or `{ctx.prefix}{obj_command_name} rename {name} <new name>` "
            "to manually rename it."
        )
    if len(subscribed_obj_ids) > 1:
        raise AliasNameConflict(
            f"I found {len(subscribed_obj_ids)} workshop {obj_name_pl} "
            f"named {ctx.prefix}{name}. Use `{ctx.prefix}{obj_command_name} autofix` to automatically assign "
            f"all conflicting {obj_name_pl} unique names, or `{ctx.prefix}{obj_command_name} rename {name} <new name>` "
            "to manually rename it."
        )
    # otherwise return the subscribed
    return await workshop_cls.from_id(ctx, subscribed_obj_ids[0])


async def get_personal_alias_named(ctx, name):
    return await get_collectable_named(
        ctx,
        name,
        personal_cls=Alias,
        workshop_cls=WorkshopAlias,
        workshop_sub_meth=WorkshopCollection.my_subs,
        is_alias=True,
        obj_name="alias",
        obj_name_pl="aliases",
        obj_command_name="alias",
    )


async def get_server_alias_named(ctx, name):
    return await get_collectable_named(
        ctx,
        name,
        personal_cls=Servalias,
        workshop_cls=WorkshopAlias,
        workshop_sub_meth=WorkshopCollection.guild_active_subs,
        is_alias=True,
        obj_name="server alias",
        obj_name_pl="server aliases",
        obj_command_name="servalias",
    )


async def get_personal_snippet_named(ctx, name):
    return await get_collectable_named(
        ctx,
        name,
        personal_cls=Snippet,
        workshop_cls=WorkshopSnippet,
        workshop_sub_meth=WorkshopCollection.my_subs,
        is_alias=False,
        obj_name="snippet",
        obj_name_pl="snippets",
        obj_command_name="snippet",
    )


async def get_server_snippet_named(ctx, name):
    return await get_collectable_named(
        ctx,
        name,
        personal_cls=Servsnippet,
        workshop_cls=WorkshopSnippet,
        workshop_sub_meth=WorkshopCollection.guild_active_subs,
        is_alias=False,
        obj_name="server snippet",
        obj_name_pl="server snippets",
        obj_command_name="servsnippet",
    )


# cvars
def set_cvar(character, name, value):
    value = str(value)
    if not name.isidentifier():
        raise InvalidArgument(
            "Cvar names must be identifiers (only contain a-z, A-Z, 0-9, _, and not start with a number)."
        )
    elif len(name) > VAR_NAME_LIMIT:
        raise InvalidArgument(f"Cvar name must be shorter than {VAR_NAME_LIMIT} characters.")
    elif name in character.get_scope_locals(True):
        raise InvalidArgument(f"The variable `{name}` is already built in.")
    elif len(value) > CVAR_SIZE_LIMIT:
        raise InvalidArgument(f"Cvars must be shorter than {CVAR_SIZE_LIMIT} characters.")

    character.set_cvar(name, value)


# uvars
async def get_uvars(ctx):
    uvars = {}
    async for uvar in ctx.bot.mdb.uvars.find({"owner": str(ctx.author.id)}):
        uvars[uvar["name"]] = uvar["value"]
    return uvars


async def set_uvar(ctx, name, value):
    value = str(value)
    if not name.isidentifier():
        raise InvalidArgument(
            "Uvar names must be valid identifiers (only contain a-z, A-Z, 0-9, _, and not start with a number)."
        )
    elif len(name) > VAR_NAME_LIMIT:
        raise InvalidArgument(f"Uvar name must be shorter than {VAR_NAME_LIMIT} characters.")
    elif len(value) > UVAR_SIZE_LIMIT:
        raise InvalidArgument(f"Uvars must be shorter than {UVAR_SIZE_LIMIT} characters.")
    await ctx.bot.mdb.uvars.update_one({"owner": str(ctx.author.id), "name": name}, {"$set": {"value": value}}, True)


async def update_uvars(ctx, uvar_dict, changed=None):
    if changed is None:
        for name, value in uvar_dict.items():
            await set_uvar(ctx, name, value)
    else:
        for name in changed:
            if name in uvar_dict:
                await set_uvar(ctx, name, uvar_dict[name])
            else:
                await ctx.bot.mdb.uvars.delete_one({"owner": str(ctx.author.id), "name": name})


# svars
async def get_svars(ctx):
    if ctx.guild is None:
        return {}
    svars = {}
    async for svar in ctx.bot.mdb.svars.find({"owner": ctx.guild.id}):
        svars[svar["name"]] = svar["value"]
    return svars


async def get_svar(ctx, name):
    if ctx.guild is None:
        return None
    svar = await ctx.bot.mdb.svars.find_one({"owner": ctx.guild.id, "name": name})
    if svar is None:
        return None
    return svar["value"]


async def set_svar(ctx, name, value):
    if ctx.guild is None:
        raise NotAllowed("You cannot set a svar in a private message.")
    value = str(value)
    if not name.isidentifier():
        raise InvalidArgument(
            "Svar names must be valid identifiers (only contain a-z, A-Z, 0-9, _, and not start with a number)."
        )
    elif len(name) > VAR_NAME_LIMIT:
        raise InvalidArgument(f"Svar name must be shorter than {VAR_NAME_LIMIT} characters.")
    elif len(value) > SVAR_SIZE_LIMIT:
        raise InvalidArgument(f"Svars must be shorter than {SVAR_SIZE_LIMIT} characters.")
    await ctx.bot.mdb.svars.update_one({"owner": ctx.guild.id, "name": name}, {"$set": {"value": value}}, True)


# gvars
async def create_gvar(ctx, value):
    value = str(value)
    if len(value) > GVAR_SIZE_LIMIT:
        raise InvalidArgument(f"Gvars must be shorter than {GVAR_SIZE_LIMIT} characters.")
    name = str(uuid.uuid4())
    data = {"key": name, "owner": str(ctx.author.id), "owner_name": str(ctx.author), "value": value, "editors": []}
    await ctx.bot.mdb.gvars.insert_one(data)
    return name


async def update_gvar(ctx, gid, value):
    value = str(value)
    gvar = await ctx.bot.mdb.gvars.find_one({"key": gid})
    if gvar is None:
        raise InvalidArgument("Global variable not found.")
    elif gvar["owner"] != str(ctx.author.id) and not str(ctx.author.id) in gvar.get("editors", []):
        raise NotAllowed("You are not allowed to edit this variable.")
    elif len(value) > GVAR_SIZE_LIMIT:
        raise InvalidArgument(f"Gvars must be shorter than {GVAR_SIZE_LIMIT} characters.")
    await ctx.bot.mdb.gvars.update_one({"key": gid}, {"$set": {"value": value}})


# snippets
async def parse_snippets(args, ctx, statblock=None, character=None, base_args=None) -> [str]:
    """
    Parses user and server snippets, including any inline scripting.

    :param args: The string to parse. Will be split automatically
    :param ctx: The Context.
    :param statblock: The statblock to populate locals from.
    :param character: If passed, provides the base character to use character-scoped functions against.
    :param base_args: The args to pass through to the snippet code via &ARGS&
    :return: The list of args, with snippets replaced.
    """
    # make args a list of str
    if isinstance(args, str):
        args = argsplit(args)
    if not isinstance(args, list):
        args = list(args)

    original_args = str((base_args or []) + args)

    new_args = []

    # set up the evaluator
    evaluator = await evaluators.ScriptingEvaluator.new(ctx)
    if character is not None:
        evaluator.with_character(character)
    elif statblock is not None:
        evaluator.with_statblock(statblock)

    try:
        for index, arg in enumerate(args):  # parse snippets
            server_invoker = False

            # personal snippet/servsnippet
            the_snippet = await get_personal_snippet_named(ctx, arg)
            if the_snippet is None and ctx.guild is not None:
                the_snippet = await get_server_snippet_named(ctx, arg)
                server_invoker = True

            if isinstance(the_snippet, WorkshopSnippet):
                await workshop_entitlements_check(ctx, the_snippet)

            if the_snippet:
                the_snippet.code = the_snippet.code.replace("&ARGS&", original_args)
                # enter the evaluator
                execution_scope = ExecutionScope.SERVER_SNIPPET if server_invoker else ExecutionScope.PERSONAL_SNIPPET
                new_args += argsplit(
                    await evaluator.transformed_str_async(
                        the_snippet.code, execution_scope=execution_scope, invoking_object=the_snippet
                    )
                )
                # analytics
                await the_snippet.log_invocation(ctx, server_invoker)
                # log nlp metadata
                if nlp := ctx.get_nlp_recorder():
                    await nlp.on_snippet_resolve(
                        ctx=ctx, snippet_name=arg, snippet_body=the_snippet.code, content_after=args[index]
                    )
            else:
                # in case the user is using old-style on the fly templating
                arg = await evaluator.transformed_str_async(arg, execution_scope=ExecutionScope.PERSONAL_SNIPPET)
                new_args.append(arg)
    finally:
        await evaluator.run_commits()
        await send_warnings(ctx, evaluator.warnings)
    return new_args


# transformers
async def parse_draconic(
    ctx,
    program: str,
    statblock=None,
    character=None,
    execution_scope: ExecutionScope = ExecutionScope.UNKNOWN,
    invoking_object=None,
):
    """
    Parses and executes a singular Draconic program in a new interpreter.
    If *statblock* or *character* are passed, uses them to initialize statblock-locals and character-methods in the
    interpreter.
    """
    evaluator = await evaluators.ScriptingEvaluator.new(ctx)
    if character is not None:
        evaluator.with_character(character)
    elif statblock is not None:
        evaluator.with_statblock(statblock)

    try:
        out = await evaluator.transformed_str_async(
            program, execution_scope=execution_scope, invoking_object=invoking_object
        )
    finally:
        await evaluator.run_commits()
        await send_warnings(ctx, evaluator.warnings)
    return out


# ==== errors / warnings ====
async def handle_alias_exception(ctx, err):
    e = err.original
    if isinstance(e, AvraeException):
        return await ctx.channel.send(err)

    if isinstance(e, draconic.DraconicException):
        tb = draconic.utils.format_traceback(e)
    else:
        tb = traceback.format_exception_only(e)

    if isinstance(e, draconic.WrappedException):
        e = e.original

    # send traceback to user
    if not isinstance(e, AliasException) or e.pm_user:
        with suppress(disnake.HTTPException):
            await ctx.author.send(
                "```py\n"
                f"{''.join(tb)}"
                "```"
                "This is an issue in a user-created command; do *not* report this on the official bug tracker."
            )

    # send error message to channel
    try:
        return await ctx.channel.send(err)
    except disnake.HTTPException:
        return await ctx.channel.send(
            f"There was an error, but the error message was too long to send! ({type(e).__name__})"
        )


async def send_warnings(ctx, warns: List["evaluators.ScriptingWarning"]):
    if not warns:
        return

    out = []

    for warn in warns:
        warn_msg = warn.msg
        lineinfo = draconic.utils.LineInfo(
            warn.node.lineno, warn.node.col_offset, warn.node.end_lineno, warn.node.end_col_offset
        )
        warn_loc = textwrap.indent(draconic.utils.format_exc_line_pointer(lineinfo, warn.expr), "  ")
        out.append(f"{warn_msg} ```py\nLine {lineinfo.lineno}, col {lineinfo.col_offset}:\n{warn_loc}\n```")

    # send warnings to user
    warn_strs = "\n".join(out)
    with suppress(disnake.HTTPException):
        await ctx.author.send(
            "One or more aliases or snippets raised warnings:\n"
            f"{warn_strs}"
            "This is an issue in a user-created command; please contact the author. Do *not* report this on the "
            "official bug tracker."
        )


# ==== entitlements ====
async def workshop_entitlements_check(ctx, ws_obj):
    """
    :type ws_obj: aliasing.workshop.WorkshopCollectableObject
    """
    entitlements = ws_obj.get_entitlements()

    # this may take a while, so type
    await ctx.trigger_typing()

    # get licensed objects, mapped by entity type
    available_ids = {k: await ctx.bot.ddb.get_accessible_entities(ctx, ctx.author.id, k) for k in entitlements}

    # get a list of all missing entities for the license error
    missing = []
    has_connected_ddb = True

    # run the checks
    for entity_type, required_ids in entitlements.items():
        available_set = available_ids[entity_type]
        if available_set is None:
            # user has not connected DDB account
            has_connected_ddb = False
            # add all ids of this type to missing
            for missing_id in required_ids:
                entity = compendium.lookup_entity(entity_type, missing_id)
                if entity is not None:
                    missing.append(entity)

        elif not available_set.issuperset(required_ids):
            # add the missing ids to missing
            for missing_id in set(required_ids).difference(available_set):
                entity = compendium.lookup_entity(entity_type, missing_id)
                if entity is not None:
                    missing.append(entity)

    if missing:
        raise CollectableRequiresLicenses(missing, ws_obj, has_connected_ddb)


async def handle_alias_required_licenses(ctx, err):
    embed = EmbedWithAuthor(ctx)
    if not err.has_connected_ddb:
        embed.title = f"Connect your D&D Beyond account to use this customization!"
        embed.url = "https://www.dndbeyond.com/account"
        embed.description = (
            "This customization requires access to one or more entities that are not in the SRD.\n"
            "Linking your account means that you'll be able to use everything you own on "
            "D&D Beyond in Avrae for free - you can link your accounts "
            "[here](https://www.dndbeyond.com/account)."
        )
        embed.set_footer(
            text="Already linked your account? It may take up to a minute for Avrae to recognize the link."
        )
    else:
        missing_source_ids = {e.source for e in err.entities}
        if len(err.entities) == 1:  # 1 entity, display entity piecemeal
            embed.title = f"Unlock {err.entities[0].name} on D&D Beyond to use this customization!"
            marketplace_url = err.entities[0].marketplace_url
        elif len(missing_source_ids) == 1:  # 1 source, recommend purchasing source
            missing_source = next(iter(missing_source_ids))
            embed.title = f"Unlock {long_source_name(missing_source)} on D&D Beyond to use this customization!"
            marketplace_url = f"https://www.dndbeyond.com/marketplace?utm_source=avrae&utm_medium=marketplacelink"
        else:  # more than 1 source
            embed.title = f"Unlock {len(missing_source_ids)} sources on D&D Beyond to use this customization!"
            marketplace_url = "https://www.dndbeyond.com/marketplace?utm_source=avrae&utm_medium=marketplacelink"

        missing = natural_join([f"[{e.name}]({e.marketplace_url})" for e in err.entities], "and")
        if len(missing) > 1400:
            missing = f"{len(err.entities)} items"
        missing_sources = natural_join([long_source_name(e) for e in missing_source_ids], "and")

        embed.description = (
            f"To use this customization and gain access to more integrations in Avrae, unlock **{missing}** by "
            f"purchasing {missing_sources} on D&D Beyond.\n\n"
            f"[Go to Marketplace]({marketplace_url})"
        )
        embed.url = marketplace_url

        embed.set_footer(text="Already unlocked? It may take up to a minute for Avrae to recognize the purchase.")
    await ctx.send(embed=embed)
