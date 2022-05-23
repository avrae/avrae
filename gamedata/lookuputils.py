"""
Created on Jan 13, 2017

@author: andrew
"""
import itertools
import logging
from typing import Dict, List, TYPE_CHECKING, TypeVar

from cogs5e.models.embeds import EmbedWithAuthor
from cogs5e.models.errors import NoActiveBrew, RequiresLicense
from cogs5e.models.homebrew import Pack, Tome
from cogs5e.models.homebrew.bestiary import Bestiary
from cogsmisc.stats import Stats
from utils.constants import HOMEBREW_EMOJI, HOMEBREW_ICON
from utils.functions import get_selection, search_and_select
from utils.settings.guild import LegacyPreference
from .compendium import compendium

if TYPE_CHECKING:
    from utils.context import AvraeContext
    from gamedata.shared import Sourced

    _SourcedT = TypeVar("_SourcedT", bound=Sourced, covariant=True)

log = logging.getLogger(__name__)


# ==== entitlement search helpers ====
async def available(ctx, entities: List["_SourcedT"], entity_type: str, user_id: int = None) -> List["_SourcedT"]:
    """
    Returns the subset of entities available to the given user in this context.

    :param ctx: The Discord Context.
    :param entities: The compendium list of all available entities.
    :param entity_type: The entity type to get entitlements data for.
    :param user_id: The Discord user ID of the user (optional - if not passed, assumes ctx.author)
    :returns: the list of accessible entities
    """
    if user_id is None:
        user_id = ctx.author.id

    available_ids = await ctx.bot.ddb.get_accessible_entities(ctx, user_id, entity_type)
    if available_ids is None:
        return [e for e in entities if e.is_free]
    return [e for e in entities if e.is_free or e.entitlement_entity_id in available_ids]


def can_access(entity: "Sourced", available_ids: set[int] = None) -> bool:
    return (
        entity.is_free or available_ids is not None and entity.entitlement_entity_id in available_ids or entity.homebrew
    )


async def handle_required_license(ctx, err):
    """
    Logs a unlicensed search and displays a prompt.

    :type ctx: utils.context.AvraeContext
    :type err: cogs5e.models.errors.RequiresLicense
    """
    result = err.entity

    await ctx.bot.mdb.analytics_nsrd_lookup.update_one(
        {"type": result.entity_type, "name": result.name}, {"$inc": {"num_lookups": 1}}, upsert=True
    )

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
                "entitlements-disabled-header", ddb_user.to_ld_dict(), f"{result.name} is not available"
            )
            unavailable_desc = await ctx.bot.ldclient.variation(
                "entitlements-disabled-message", ddb_user.to_ld_dict(), f"{result.name} is currently unavailable"
            )

            embed.title = (
                unavailable_title.replace("$entity_type$", result.entity_type)
                .replace("$entity_name$", result.name)
                .replace("$source$", result.source)
                .replace("$long_source$", long_source_name(result.source))
            )
            embed.description = (
                unavailable_desc.replace("$entity_type$", result.entity_type)
                .replace("$entity_name$", result.name)
                .replace("$source$", result.source)
                .replace("$long_source$", long_source_name(result.source))
            )
        else:
            embed.title = f"Connect your D&D Beyond account to view {result.name}!"
            embed.url = "https://www.dndbeyond.com/account"
            embed.description = (
                "It looks like you don't have your Discord account connected to your D&D Beyond account!\n"
                "Linking your account means that you'll be able to use everything you own on "
                "D&D Beyond in Avrae for free - you can link your accounts "
                "[here](https://www.dndbeyond.com/account)."
            )
            embed.set_footer(
                text="Already linked your account? It may take up to a minute for Avrae to recognize the " "link."
            )
    else:
        embed.title = f"Unlock {result.name} on D&D Beyond to view it here!"
        embed.description = (
            f"To see and search this {result.entity_type}'s full details, unlock **{result.name}** by "
            f"purchasing {long_source_name(result.source)} on D&D Beyond.\n\n"
            f"[Go to Marketplace]({result.marketplace_url})"
        )
        embed.url = result.marketplace_url

        embed.set_footer(text="Already unlocked? It may take up to a minute for Avrae to recognize the purchase.")
    await ctx.send(embed=embed)


# ---- helpers ----
def handle_source_footer(
    embed, sourced: "Sourced", text: str = None, add_source_str: bool = True, allow_overwrite: bool = False
):
    """
    Handles adding the relevant source icon and source str to the embed's footer.

    :param embed: The embed to operate on.
    :param sourced: The source to pull data from.
    :param text: Any text prepending the source str.
    :param add_source_str: Whether or not to add the source str (e.g. "PHB 168")
    :param allow_overwrite: Whether or not to allow overwriting an existing footer text.
    """
    text_pieces = []
    icon_url = embed.Empty
    book = compendium.book_by_source(sourced.source)
    if text is not None:
        text_pieces.append(text)
    if add_source_str:
        text_pieces.append(sourced.source_str())

    # set icon url and default text
    if book is None:
        icon_url = HOMEBREW_ICON
        text_pieces = text_pieces or ["Homebrew content."]
    elif book.is_ua:
        icon_url = "https://media-waterdeep.cursecdn.com/avatars/110/171/636516074887091041.png"
        text_pieces = text_pieces or ["Unearthed Arcana content."]
    elif book.is_partnered:
        icon_url = "https://media-waterdeep.cursecdn.com/avatars/11008/904/637274855809570341.png"
        text_pieces = text_pieces or ["Partnered content."]
    elif book.is_cr:
        icon_url = "https://media-waterdeep.cursecdn.com/avatars/105/174/636512853628516966.png"
        text_pieces = text_pieces or ["Critical Role content."]
    elif book.is_noncore:
        text_pieces = text_pieces or ["Noncore content."]

    # add legacy badge
    if sourced.is_legacy:
        text_pieces.append("Legacy content.")

    # do the writing
    text = " | ".join(text_pieces) or embed.Empty
    if not allow_overwrite:
        if embed.footer.text:
            text = embed.footer.text
        if embed.footer.icon_url:
            icon_url = embed.footer.icon_url

    embed.set_footer(text=text, icon_url=icon_url)


def long_source_name(source):
    book = compendium.book_by_source(source)
    if book is None:
        return source
    return book.name


def source_slug(source):
    book = compendium.book_by_source(source)
    if book is None:
        return None
    return book.slug


# ==== search ====
def _create_selector(available_ids: dict[str, set[int]]):
    async def legacy_entity_selector(ctx: "AvraeContext", choices: List["Sourced"], *args, **kwargs) -> "Sourced":
        """Given a choice between only a legacy and non-legacy entity, respect the server's legacy preferences."""
        # if the choices aren't between 2 entities or it's in PMs, defer
        if len(choices) != 2 or ctx.guild is None:
            return await get_selection(ctx, choices, *args, **kwargs)

        # if it's not actually a choice between a legacy and non-legacy entity, defer
        a, b = choices
        if a.is_legacy == b.is_legacy:
            return await get_selection(ctx, choices, *args, **kwargs)

        legacy: "Sourced" = a if a.is_legacy else b
        latest: "Sourced" = a if not a.is_legacy else b

        guild_settings = await ctx.get_server_settings()
        # if the guild setting is to ask, defer
        if guild_settings.legacy_preference == LegacyPreference.ASK:
            return await get_selection(ctx, choices, *args, **kwargs)
        # if the user has access to the preferred entity, return it
        if guild_settings.legacy_preference == LegacyPreference.LATEST and can_access(
            latest, available_ids[latest.entitlement_entity_type]
        ):
            return latest
        elif guild_settings.legacy_preference == LegacyPreference.LEGACY and can_access(
            legacy, available_ids[legacy.entitlement_entity_type]
        ):
            return legacy
        # otherwise defer to asking
        return await get_selection(ctx, choices, *args, **kwargs)

    return legacy_entity_selector


def _create_selectkey(available_ids: dict[str, set[int]]):
    def selectkey(e: "Sourced"):
        if e.homebrew:
            return f"{e.name} ({HOMEBREW_EMOJI} {e.source})"
        entity_source = e.source if not e.is_legacy else f"{e.source}; *legacy*"
        if can_access(e, available_ids[e.entitlement_entity_type]):
            return f"{e.name} ({entity_source})"
        return f"{e.name} ({entity_source})\\*"

    return selectkey


async def add_training_data(mdb, lookup_type, query, result_name, metadata=None, srd=True, could_view=True):
    data = {"type": lookup_type, "query": query, "result": result_name, "srd": srd, "could_view": could_view}
    if metadata:
        data["given_options"] = metadata.get("num_options", 1)
        data["chosen_index"] = metadata.get("chosen_index", 0)
        data["homebrew"] = metadata.get("homebrew", False)
    await mdb.nn_training.insert_one(data)


async def search_entities(
    ctx: "AvraeContext", entities: Dict[str, List["_SourcedT"]], query: str, query_type: str = None, **kwargs
) -> "_SourcedT":
    """
    :param ctx: The context to search in.
    :param entities: A dict mapping entitlements entity types to the entities themselves.
    :param query: The name of the entity to search for.
    :param query_type: The type of the object being queried for (default entity type if only one dict key)
    :raises: RequiresLicense if an entity that requires a license is selected
    """
    # sanity checks
    if len(entities) == 0:
        raise ValueError("At least 1 entity type must be passed in")
    if query_type is None and len(entities) != 1:
        raise ValueError("Query type must be passed for multiple entity types")
    elif query_type is None:
        query_type = list(entities.keys())[0]

    # this may take a while, so type
    await ctx.trigger_typing()

    # get licensed objects, mapped by entity type
    available_ids = {k: await ctx.bot.ddb.get_accessible_entities(ctx, ctx.author.id, k) for k in entities}

    result, metadata = await search_and_select(
        ctx,
        list(itertools.chain.from_iterable(entities.values())),
        query,
        lambda e: e.name,
        selectkey=_create_selectkey(available_ids),
        selector=_create_selector(available_ids),
        return_metadata=True,
        **kwargs,
    )

    entity: "Sourced" = result
    entity_entitlement_type = entity.entitlement_entity_type

    # log the query
    await add_training_data(
        ctx.bot.mdb,
        query_type,
        query,
        entity.name,
        metadata=metadata,
        srd=entity.is_free,
        could_view=can_access(entity, available_ids[entity_entitlement_type]),
    )

    # display error if not srd
    if not can_access(entity, available_ids[entity_entitlement_type]):
        raise RequiresLicense(entity, available_ids[entity_entitlement_type] is not None)
    return entity


# ---- monster stuff ----
async def select_monster_full(ctx, name, extra_choices=None, **kwargs):
    """
    Gets a Monster from the compendium and active bestiary/ies.
    """
    choices = await get_monster_choices(ctx)
    await Stats.increase_stat(ctx, "monsters_looked_up_life")

    # #881
    if extra_choices:
        choices.extend(extra_choices)

    return await search_entities(ctx, {"monster": choices}, name, **kwargs)


async def get_monster_choices(ctx, homebrew=True):
    """
    Gets a list of monsters in the current context for the user to choose from.

    :param ctx: The context.
    :param homebrew: Whether to include homebrew entities.
    """
    if not homebrew:
        return compendium.monsters

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
    choices = list(itertools.chain(compendium.monsters, custom_monsters))
    if ctx.guild:
        async for servbestiary in Bestiary.server_bestiaries(ctx):
            if servbestiary.id != bestiary_id:
                await servbestiary.load_monsters(ctx)
                choices.extend(servbestiary.monsters)
    return choices


# ---- spell stuff ----
async def select_spell_full(ctx, name, extra_choices=None, **kwargs):
    """
    Gets a Spell from the compendium and active tome(s).

    :rtype: :class:`gamedata.Spell`
    """
    choices = await get_spell_choices(ctx)
    await Stats.increase_stat(ctx, "spells_looked_up_life")

    # #881
    if extra_choices:
        choices.extend(extra_choices)

    return await search_entities(ctx, {"spell": choices}, name, **kwargs)


async def get_spell_choices(ctx, homebrew=True):
    """
    Gets a list of spells in the current context for the user to choose from.

    :param ctx: The context.
    :param homebrew: Whether to include homebrew entities.
    """
    if not homebrew:
        return compendium.spells

    # personal active tome
    try:
        tome = await Tome.from_ctx(ctx)
        custom_spells = tome.spells
        tome_id = tome.id
    except NoActiveBrew:
        custom_spells = []
        tome_id = None

    # server tomes
    choices = list(itertools.chain(compendium.spells, custom_spells))
    if ctx.guild:
        async for servtome in Tome.server_active(ctx):
            if servtome.id != tome_id:
                choices.extend(servtome.spells)
    return choices


# ---- item stuff ----
async def get_item_entitlement_choice_map(ctx, homebrew=True):
    """
    Gets a list of items in the current context for the user to choose from.

    :param ctx: The context.
    :param homebrew: Whether to include homebrew entities.
    """
    available_items = {
        "adventuring-gear": compendium.adventuring_gear,
        "armor": compendium.armor,
        "magic-item": compendium.magic_items,
        "weapon": compendium.weapons,
    }

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
    choices = custom_items
    if ctx.guild:
        async for servpack in Pack.server_active(ctx):
            if servpack.id != pack_id:
                choices.extend(servpack.items)

    available_items["magic-item"] = compendium.magic_items + choices
    return available_items


# ---- race stuff ----
async def available_races(ctx, filter_by_license=True):
    """
    Gets a list of races in the current context for the user to choose from.

    :param ctx: The context.
    :param filter_by_license: Whether to filter out entities the user cannot access.
    """
    if filter_by_license:
        races = await available(ctx, compendium.races, "race")
        races.extend(await available(ctx, compendium.subraces, "subrace"))
    else:
        races = compendium.races + compendium.subraces

    return races
