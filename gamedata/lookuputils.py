"""
Created on Jan 13, 2017

@author: andrew
"""
import itertools
import logging

from cogs5e.models.embeds import EmbedWithAuthor
from cogs5e.models.errors import NoActiveBrew
from cogs5e.models.homebrew import Pack, Tome
from cogs5e.models.homebrew.bestiary import Bestiary
from cogsmisc.stats import Stats
from utils import constants
from utils.functions import long_source_name, search_and_select
from .compendium import compendium

HOMEBREW_EMOJI = "<:homebrew:434140566834511872>"
HOMEBREW_ICON = "https://avrae.io/assets/img/homebrew.png"

log = logging.getLogger(__name__)


# ==== entitlement search helpers ====
async def available(ctx, entities, entity_type, user_id=None):
    """
    Returns the subset of entities available to the given user in this context.

    :param ctx: The Discord Context.
    :type ctx: discord.ext.commands.Context
    :param entities: The compendium list of all available entities.
    :type entities: list[gamedata.shared.Sourced]
    :param entity_type: The entity type to get entitlements data for.
    :type entity_type: str
    :param user_id: The Discord user ID of the user (optional - if not passed, assumes ctx.author)
    :type user_id: int
    :rtype: list[gamedata.shared.Sourced]
    """
    if user_id is None:
        user_id = ctx.author.id

    available_ids = await ctx.bot.ddb.get_accessible_entities(ctx, user_id, entity_type)
    if available_ids is None:
        return [e for e in entities if e.is_free]
    return [e for e in entities if e.is_free or e.entity_id in available_ids]


def can_access(entity, available_ids=None):
    return entity.is_free \
           or available_ids is not None and entity.entity_id in available_ids \
           or entity.homebrew


async def handle_required_license(ctx, err):
    """
    Logs a unlicensed search and displays a prompt.

    :type ctx: discord.ext.commands.Context
    :type err: cogs5e.models.errors.RequiresLicense
    """
    result = err.entity

    await ctx.bot.mdb.analytics_nsrd_lookup.update_one({"type": result.entity_type, "name": result.name},
                                                       {"$inc": {"num_lookups": 1}},
                                                       upsert=True)

    embed = EmbedWithAuthor(ctx)
    if not err.has_connected_ddb:
        # was the user blocked from nSRD by a feature flag?
        ddb_user = await ctx.bot.ddb.get_ddb_user(ctx, ctx.author.id)
        if ddb_user is None:
            blocked_by_ff = False
        else:
            blocked_by_ff = not (await ctx.bot.ldclient.variation("entitlements-enabled", ddb_user.to_ld_dict(), False))

        if blocked_by_ff:
            # get the message from feature flag
            # replacements:
            # $entity_type$, $entity_name$, $source$, $long_source$
            unavailable_title = await ctx.bot.ldclient.variation(
                "entitlements-disabled-header", ddb_user.to_ld_dict(), f"{result.name} is not available")
            unavailable_desc = await ctx.bot.ldclient.variation(
                "entitlements-disabled-message", ddb_user.to_ld_dict(), f"{result.name} is currently unavailable")

            embed.title = unavailable_title \
                .replace('$entity_type$', result.entity_type) \
                .replace('$entity_name$', result.name) \
                .replace('$source$', result.source) \
                .replace('$long_source$', long_source_name(result.source))
            embed.description = unavailable_desc \
                .replace('$entity_type$', result.entity_type) \
                .replace('$entity_name$', result.name) \
                .replace('$source$', result.source) \
                .replace('$long_source$', long_source_name(result.source))
        else:
            embed.title = f"Connect your D&D Beyond account to view {result.name}!"
            embed.url = "https://www.dndbeyond.com/account"
            embed.description = \
                "It looks like you don't have your Discord account connected to your D&D Beyond account!\n" \
                "Linking your account means that you'll be able to use everything you own on " \
                "D&D Beyond in Avrae for free - you can link your accounts " \
                "[here](https://www.dndbeyond.com/account)."
            embed.set_footer(text="Already linked your account? It may take up to a minute for Avrae to recognize the "
                                  "link.")
    else:
        embed.title = f"Purchase {result.name} on D&D Beyond to view it here!"
        embed.description = \
            f"To see and search this {result.entity_type}'s full details, unlock **{result.name}** by " \
            f"purchasing {long_source_name(result.source)} on D&D Beyond.\n\n" \
            f"[Go to Marketplace]({result.marketplace_url})"
        embed.url = result.marketplace_url

        embed.set_footer(text="Already purchased? It may take up to a minute for Avrae to recognize the "
                              "purchase.")
    await ctx.send(embed=embed)


# ---- helpers ----
def get_homebrew_formatted_name(named):
    if named.homebrew:
        return f"{named.name} ({HOMEBREW_EMOJI})"
    return named.name


def handle_source_footer(embed, sourced, text=None, add_source_str=True, allow_overwrite=False):
    """
    Handles adding the relevant source icon and source str to the embed's footer.

    :param embed: The embed to operate on.
    :param sourced: The source to pull data from.
    :param str text: Any text prepending the source str.
    :param bool add_source_str: Whether or not to add the source str (e.g. "PHB 168")
    :param bool allow_overwrite: Whether or not to allow overwriting an existing footer text.
    """
    text_pieces = []
    icon_url = embed.Empty
    if text is not None:
        text_pieces.append(text)
    if add_source_str:
        text_pieces.append(sourced.source_str())

    # set icon url and default text
    if sourced.homebrew:
        icon_url = "https://avrae.io/assets/img/homebrew.png"
        text_pieces = text_pieces or ["Homebrew content."]
    elif sourced.source in constants.UA_SOURCES:
        icon_url = "https://media-waterdeep.cursecdn.com/avatars/110/171/636516074887091041.png"
        text_pieces = text_pieces or ["Unearthed Arcana content."]
    elif sourced.source in constants.PARTNERED_SOURCES:
        icon_url = "https://media-waterdeep.cursecdn.com/avatars/11008/904/637274855809570341.png"
        text_pieces = text_pieces or ["Partnered content."]
    elif sourced.source in constants.CR_SOURCES:
        icon_url = "https://media-waterdeep.cursecdn.com/avatars/105/174/636512853628516966.png"
        text_pieces = text_pieces or ["Critical Role content."]
    elif sourced.source in constants.NONCORE_SOURCES:
        text_pieces = text_pieces or ["Noncore content."]

    # do the writing
    text = ' | '.join(text_pieces) or embed.Empty
    if not allow_overwrite:
        if embed.footer.text:
            text = embed.footer.text
        if embed.footer.icon_url:
            icon_url = embed.footer.icon_url

    embed.set_footer(text=text, icon_url=icon_url)


# ---- monster stuff ----
async def select_monster_full(ctx, name, cutoff=5, return_key=False, pm=False, message=None, list_filter=None,
                              return_metadata=False, extra_choices=None, selectkey=None):
    """
    Gets a Monster from the compendium and active bestiary/ies.
    """
    choices = await get_monster_choices(ctx)
    await Stats.increase_stat(ctx, "monsters_looked_up_life")

    # #881
    if extra_choices:
        choices.extend(extra_choices)
    if selectkey is None:
        selectkey = get_homebrew_formatted_name

    return await search_and_select(ctx, choices, name, lambda e: e.name, cutoff, return_key, pm, message, list_filter,
                                   selectkey=selectkey, return_metadata=return_metadata)


async def get_monster_choices(ctx, filter_by_license=True, homebrew=True):
    """
    Gets a list of monsters in the current context for the user to choose from.

    :param ctx: The context.
    :param filter_by_license: Whether to filter out entities the user cannot access.
    :param homebrew: Whether to include homebrew entities.
    """
    if filter_by_license:
        available_monsters = await available(ctx, compendium.monsters, 'monster')
    else:
        available_monsters = compendium.monsters

    if not homebrew:
        return available_monsters

    # personal bestiary
    try:
        bestiary = await Bestiary.from_ctx(ctx)
        await bestiary.load_monsters(ctx)
        custom_monsters = bestiary.monsters
        bestiary_id = bestiary.id
    except NoActiveBrew:
        custom_monsters = []
        bestiary_id = None

    # server bestiaries
    choices = list(itertools.chain(available_monsters, custom_monsters))
    if ctx.guild:
        async for servbestiary in Bestiary.server_bestiaries(ctx):
            if servbestiary.id != bestiary_id:
                await servbestiary.load_monsters(ctx)
                choices.extend(servbestiary.monsters)
    return choices


# ---- spell stuff ----
async def select_spell_full(ctx, name, *args, extra_choices=None, **kwargs):
    """
    Gets a Spell from the compendium and active tome(s).

    :rtype: :class:`~cogs5e.models.spell.Spell`
    """
    choices = await get_spell_choices(ctx)
    await Stats.increase_stat(ctx, "spells_looked_up_life")

    # #881
    if extra_choices:
        choices.extend(extra_choices)
    if 'selectkey' not in kwargs:
        kwargs['selectkey'] = get_homebrew_formatted_name

    return await search_and_select(ctx, choices, name, lambda e: e.name, *args, **kwargs)


async def get_spell_choices(ctx, filter_by_license=True, homebrew=True):
    """
    Gets a list of spells in the current context for the user to choose from.

    :param ctx: The context.
    :param filter_by_license: Whether to filter out entities the user cannot access.
    :param homebrew: Whether to include homebrew entities.
    """
    if filter_by_license:
        available_spells = await available(ctx, compendium.spells, 'spell')
    else:
        available_spells = compendium.spells

    if not homebrew:
        return available_spells

    # personal active tome
    try:
        tome = await Tome.from_ctx(ctx)
        custom_spells = tome.spells
        tome_id = tome.id
    except NoActiveBrew:
        custom_spells = []
        tome_id = None

    # server tomes
    choices = list(itertools.chain(available_spells, custom_spells))
    if ctx.guild:
        async for servtome in Tome.server_active(ctx):
            if servtome.id != tome_id:
                choices.extend(servtome.spells)
    return choices


# ---- item stuff ----
async def get_item_choices(ctx, filter_by_license=True, homebrew=True):
    """
    Gets a list of items in the current context for the user to choose from.

    :param ctx: The context.
    :param filter_by_license: Whether to filter out entities the user cannot access.
    :param homebrew: Whether to include homebrew entities.
    """
    if filter_by_license:
        available_items = await available(ctx, compendium.items, 'magic-item')
    else:
        available_items = compendium.items

    if not homebrew:
        return available_items

    # personal pack
    try:
        pack = await Pack.from_ctx(ctx)
        custom_items = pack.items
        pack_id = pack.id
    except NoActiveBrew:
        custom_items = []
        pack_id = None

    # server packs
    choices = list(itertools.chain(available_items, custom_items))
    if ctx.guild:
        async for servpack in Pack.server_active(ctx):
            if servpack.id != pack_id:
                choices.extend(servpack.items)
    return choices


# ---- race stuff ----
async def get_race_choices(ctx, filter_by_license=True):
    """
    Gets a list of races in the current context for the user to choose from.

    :param ctx: The context.
    :param filter_by_license: Whether to filter out entities the user cannot access.
    """
    if filter_by_license:
        available_races = await available(ctx, compendium.races, 'race')
        available_races.extend(await available(ctx, compendium.subraces, 'subrace'))
    else:
        available_races = compendium.races + compendium.subraces

    return available_races


async def get_rfeat_choices(ctx, filter_by_license=True):
    """
    Gets a list of racefeats in the current context for the user to choose from.

    :param ctx: The context.
    :param filter_by_license: Whether to filter out entities the user cannot access.
    """
    if filter_by_license:
        available_rfeats = await available(ctx, compendium.rfeats, 'race')
        available_rfeats.extend(await available(ctx, compendium.subrfeats, 'subrace'))
    else:
        available_rfeats = compendium.rfeats + compendium.subrfeats

    return available_rfeats
