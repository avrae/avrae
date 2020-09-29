import asyncio
import traceback
import uuid

import draconic

import cogs5e.models.character as character_model
from aliasing import evaluators
from aliasing.constants import CVAR_SIZE_LIMIT, GVAR_SIZE_LIMIT, SVAR_SIZE_LIMIT, UVAR_SIZE_LIMIT
from aliasing.errors import AliasNameConflict, CollectableNotFound, CollectableRequiresLicenses, EvaluationError
from aliasing.personal import Alias, Servalias, Servsnippet, Snippet
from aliasing.workshop import WorkshopAlias, WorkshopCollection, WorkshopSnippet
from cogs5e.models.embeds import EmbedWithAuthor
from cogs5e.models.errors import AvraeException, InvalidArgument, NoCharacter, NotAllowed
from gamedata.compendium import compendium
from utils.argparser import argquote, argsplit
from utils.functions import long_source_name, natural_join


async def handle_aliases(ctx):
    # ctx.prefix: the invoking prefix
    # ctx.invoked_with: the first word
    alias = ctx.invoked_with

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

    command_code = await handle_alias_arguments(the_alias.code, ctx)
    char = None
    try:
        char = await character_model.Character.from_ctx(ctx)
    except NoCharacter:
        pass

    try:
        if char:
            ctx.message.content = await parse_with_character(ctx, char, command_code)
        else:
            ctx.message.content = await parse_no_char(ctx, command_code)
    except EvaluationError as err:
        return await handle_alias_exception(ctx, err)
    except Exception as e:
        return await ctx.send(e)

    # send it back around to be reprocessed
    await ctx.bot.process_commands(ctx.message)


async def handle_alias_arguments(command, ctx):
    """Takes an alias name, alias value, and message and handles percent-encoded args.
    Returns: string"""
    prefix = ctx.prefix
    rawargs = ctx.view.read_rest().strip()

    args = argsplit(rawargs)
    tempargs = args[:]
    new_command = command
    if '%*%' in command:
        new_command = new_command.replace('%*%', argquote(rawargs))
        tempargs = []
    if '&*&' in command:
        new_command = new_command.replace('&*&', rawargs.replace("\"", "\\\""))
        tempargs = []
    if '&ARGS&' in command:
        new_command = new_command.replace('&ARGS&', str(args))
        tempargs = []
    for index, value in enumerate(args):
        key = '%{}%'.format(index + 1)
        to_remove = False
        if key in command:
            new_command = new_command.replace(key, argquote(value))
            to_remove = True
        key = '&{}&'.format(index + 1)
        if key in command:
            new_command = new_command.replace(key, value.replace("\"", "\\\""))
            to_remove = True
        if to_remove:
            try:
                tempargs.remove(value)
            except ValueError:
                pass

    quoted_args = ' '.join(map(argquote, tempargs))
    return f"{prefix}{new_command} {quoted_args}".strip()


# getters
async def get_collectable_named(ctx, name, personal_cls, workshop_cls, workshop_sub_meth, is_alias,
                                obj_name, obj_name_pl, obj_command_name):
    binding_key = 'alias_bindings' if is_alias else 'snippet_bindings'

    personal_obj = await personal_cls.get_named(name, ctx)
    # get list of subscription object ids
    subscribed_obj_ids = []
    async for subscription_doc in workshop_sub_meth(ctx):
        for binding in subscription_doc[binding_key]:
            if binding['name'] == name:
                subscribed_obj_ids.append(binding['id'])

    # if only personal, return personal (or none)
    if not subscribed_obj_ids:
        return personal_obj
    # conflicting name errors
    if personal_obj is not None and subscribed_obj_ids:
        raise AliasNameConflict(
            f"I found both a personal {obj_name} and {len(subscribed_obj_ids)} workshop {obj_name}(es) "
            f"named {ctx.prefix}{name}. Use `{ctx.prefix}{obj_command_name} autofix` to automatically assign "
            f"all conflicting {obj_name_pl} unique names, or `{ctx.prefix}{obj_command_name} rename {name} <new name>` "
            f"to manually rename it.")
    if len(subscribed_obj_ids) > 1:
        raise AliasNameConflict(
            f"I found {len(subscribed_obj_ids)} workshop {obj_name_pl} "
            f"named {ctx.prefix}{name}. Use `{ctx.prefix}{obj_command_name} autofix` to automatically assign "
            f"all conflicting {obj_name_pl} unique names, or `{ctx.prefix}{obj_command_name} rename {name} <new name>` "
            f"to manually rename it.")
    # otherwise return the subscribed
    return await workshop_cls.from_id(ctx, subscribed_obj_ids[0])


async def get_personal_alias_named(ctx, name):
    return await get_collectable_named(
        ctx, name,
        personal_cls=Alias, workshop_cls=WorkshopAlias, workshop_sub_meth=WorkshopCollection.my_subs, is_alias=True,
        obj_name="alias", obj_name_pl="aliases", obj_command_name="alias"
    )


async def get_server_alias_named(ctx, name):
    return await get_collectable_named(
        ctx, name,
        personal_cls=Servalias, workshop_cls=WorkshopAlias, workshop_sub_meth=WorkshopCollection.guild_active_subs,
        is_alias=True,
        obj_name="server alias", obj_name_pl="server aliases", obj_command_name="servalias"
    )


async def get_personal_snippet_named(ctx, name):
    return await get_collectable_named(
        ctx, name,
        personal_cls=Snippet, workshop_cls=WorkshopSnippet, workshop_sub_meth=WorkshopCollection.my_subs,
        is_alias=False,
        obj_name="snippet", obj_name_pl="snippets", obj_command_name="snippet"
    )


async def get_server_snippet_named(ctx, name):
    return await get_collectable_named(
        ctx, name,
        personal_cls=Servsnippet, workshop_cls=WorkshopSnippet, workshop_sub_meth=WorkshopCollection.guild_active_subs,
        is_alias=False,
        obj_name="server snippet", obj_name_pl="server snippets", obj_command_name="servsnippet"
    )


# cvars
def set_cvar(character, name, value):
    value = str(value)
    if not name.isidentifier():
        raise InvalidArgument("Cvar names must be identifiers "
                              "(only contain a-z, A-Z, 0-9, _, and not start with a number).")
    elif name in character.get_scope_locals(True):
        raise InvalidArgument(f"The variable `{name}` is already built in.")
    elif len(value) > CVAR_SIZE_LIMIT:
        raise InvalidArgument(f"Cvars must be shorter than {CVAR_SIZE_LIMIT} characters.")

    character.set_cvar(name, value)


# uvars
async def get_uvars(ctx):
    uvars = {}
    async for uvar in ctx.bot.mdb.uvars.find({"owner": str(ctx.author.id)}):
        uvars[uvar['name']] = uvar['value']
    return uvars


async def set_uvar(ctx, name, value):
    value = str(value)
    if not name.isidentifier():
        raise InvalidArgument("Uvar names must be valid identifiers "
                              "(only contain a-z, A-Z, 0-9, _, and not start with a number).")
    elif len(value) > UVAR_SIZE_LIMIT:
        raise InvalidArgument(f"Uvars must be shorter than {UVAR_SIZE_LIMIT} characters.")
    await ctx.bot.mdb.uvars.update_one(
        {"owner": str(ctx.author.id), "name": name},
        {"$set": {"value": value}},
        True)


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
        svars[svar['name']] = svar['value']
    return svars


async def get_svar(ctx, name):
    if ctx.guild is None:
        return None
    svar = await ctx.bot.mdb.svars.find_one({"owner": ctx.guild.id, "name": name})
    if svar is None:
        return None
    return svar['value']


async def set_svar(ctx, name, value):
    if ctx.guild is None:
        raise NotAllowed("You cannot set a svar in a private message.")
    value = str(value)
    if not name.isidentifier():
        raise InvalidArgument("Svar names must be valid identifiers "
                              "(only contain a-z, A-Z, 0-9, _, and not start with a number).")
    elif len(value) > SVAR_SIZE_LIMIT:
        raise InvalidArgument(f"Svars must be shorter than {SVAR_SIZE_LIMIT} characters.")
    await ctx.bot.mdb.svars.update_one(
        {"owner": ctx.guild.id, "name": name},
        {"$set": {"value": value}},
        True)


# gvars
async def create_gvar(ctx, value):
    value = str(value)
    if len(value) > GVAR_SIZE_LIMIT:
        raise InvalidArgument(f"Gvars must be shorter than {GVAR_SIZE_LIMIT} characters.")
    name = str(uuid.uuid4())
    data = {
        'key': name, 'owner': str(ctx.author.id), 'owner_name': str(ctx.author), 'value': value,
        'editors': []
    }
    await ctx.bot.mdb.gvars.insert_one(data)
    return name


async def update_gvar(ctx, gid, value):
    value = str(value)
    gvar = await ctx.bot.mdb.gvars.find_one({"key": gid})
    if gvar is None:
        raise InvalidArgument("Global variable not found.")
    elif gvar['owner'] != str(ctx.author.id) and not str(ctx.author.id) in gvar.get('editors', []):
        raise NotAllowed("You are not allowed to edit this variable.")
    elif len(value) > GVAR_SIZE_LIMIT:
        raise InvalidArgument(f"Gvars must be shorter than {GVAR_SIZE_LIMIT} characters.")
    await ctx.bot.mdb.gvars.update_one({"key": gid}, {"$set": {"value": value}})


# snippets
async def parse_snippets(args, ctx) -> str:
    """
    Parses user and server snippets.
    :param args: The string to parse. Will be split automatically
    :param ctx: The Context.
    :return: The string, with snippets replaced.
    """
    # make args a list of str
    if isinstance(args, str):
        args = argsplit(args)
    if not isinstance(args, list):
        args = list(args)

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
            args[index] = the_snippet.code
            # analytics
            await the_snippet.log_invocation(ctx, server_invoker)
        elif ' ' in arg:
            args[index] = argquote(arg)
    return " ".join(args)


# transformers
async def parse_with_character(ctx, character, string):
    evaluator = (await evaluators.ScriptingEvaluator.new(ctx)).with_character(character)
    try:
        out = await asyncio.get_event_loop().run_in_executor(None, evaluator.transformed_str, string)
    finally:
        await evaluator.run_commits()
    return out


async def parse_with_statblock(ctx, statblock, string):
    evaluator = (await evaluators.ScriptingEvaluator.new(ctx)).with_statblock(statblock)
    try:
        out = await asyncio.get_event_loop().run_in_executor(None, evaluator.transformed_str, string)
    finally:
        await evaluator.run_commits()
    return out


async def parse_no_char(ctx, cstr):
    """
    Parses cvars and whatnot without an active character.
    :param cstr: The string to parse.
    :param ctx: The Context to parse the string in.
    :return: The parsed string.
    :rtype: str
    """
    evaluator = await evaluators.ScriptingEvaluator.new(ctx)
    try:
        out = await asyncio.get_event_loop().run_in_executor(None, evaluator.transformed_str, cstr)
    finally:
        await evaluator.run_commits()
    return out


# handler
async def handle_alias_exception(ctx, err):
    e = err.original
    location = f"when parsing expression {err.expression}"
    locinfo = None
    if isinstance(e, AvraeException):
        return await ctx.channel.send(err)
    elif isinstance(e, draconic.InvalidExpression):
        try:
            location = f"on line {e.node.lineno}, col {e.node.col_offset}"
            locinfo = (e.node.lineno, e.node.col_offset)
        except AttributeError:
            pass
    elif isinstance(e, draconic.DraconicSyntaxError):
        location = f"on line {e.lineno}, col {e.offset}"
        locinfo = (e.lineno, e.offset)

    # make a pointer to the error so it looks nice
    point_to_error = ''
    if locinfo:
        line, col = locinfo
        the_line = err.expression.split('\n')[line - 1]
        point_to_error = f"{the_line}\n{' ' * col}^\n"

    if isinstance(e, draconic.AnnotatedException):
        e = e.original

    tb = ''.join(traceback.format_exception(type(e), e, e.__traceback__, limit=0, chain=False))
    try:
        await ctx.author.send(
            f"```py\n"
            f"Error {location}:\n"
            f"{point_to_error}"
            f"{tb}\n"
            f"```"
            f"This is an issue in a user-created command; do *not* report this on the official bug tracker.")
    except:
        pass
    return await ctx.channel.send(err)


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
                entity = compendium.lookup_by_entitlement(entity_type, missing_id)
                if entity is not None:
                    missing.append(entity)

        elif not available_set.issuperset(required_ids):
            # add the missing ids to missing
            for missing_id in set(required_ids).difference(available_set):
                entity = compendium.lookup_by_entitlement(entity_type, missing_id)
                if entity is not None:
                    missing.append(entity)

    if missing:
        raise CollectableRequiresLicenses(missing, ws_obj, has_connected_ddb)


async def handle_alias_required_licenses(ctx, err):
    embed = EmbedWithAuthor(ctx)
    if not err.has_connected_ddb:
        # was the user blocked from nSRD by a feature flag?
        ddb_user = await ctx.bot.ddb.get_ddb_user(ctx, ctx.author.id)
        if ddb_user is None:
            blocked_by_ff = False
        else:
            blocked_by_ff = not (await ctx.bot.ldclient.variation("entitlements-enabled", ddb_user.to_ld_dict(), False))

        if blocked_by_ff:
            embed.title = "D&D Beyond is currently unavailable"
            embed.description = f"I was unable to communicate with D&D Beyond to confirm access to:\n" \
                                f"{', '.join(e.name for e in err.entities)}"
        else:
            embed.title = f"Connect your D&D Beyond account to use this customization!"
            embed.url = "https://www.dndbeyond.com/account"
            embed.description = \
                "This customization requires access to one or more entities that are not in the SRD.\n" \
                "Linking your account means that you'll be able to use everything you own on " \
                "D&D Beyond in Avrae for free - you can link your accounts " \
                "[here](https://www.dndbeyond.com/account)."
            embed.set_footer(text="Already linked your account? It may take up to a minute for Avrae to recognize the "
                                  "link.")
    else:
        if len(err.entities) == 1:
            embed.title = f"Purchase {err.entities[0].name} on D&D Beyond to use this customization!"
            marketplace_url = err.entities[0].marketplace_url
        else:
            embed.title = f"Purchase {len(err.entities)} items on D&D Beyond to use this customization!"
            marketplace_url = "https://www.dndbeyond.com/marketplace"

        missing = natural_join([f"[{e.name}]({e.marketplace_url})" for e in err.entities], "and")
        missing_sources = natural_join({long_source_name(e.source) for e in err.entities}, "and")

        embed.description = \
            f"To use this customization and gain access to more integrations in Avrae, unlock **{missing}** by " \
            f"purchasing {missing_sources} on D&D Beyond.\n\n" \
            f"[Go to Marketplace]({marketplace_url})"
        embed.url = marketplace_url

        embed.set_footer(text="Already purchased? It may take up to a minute for Avrae to recognize the "
                              "purchase.")
    await ctx.send(embed=embed)
