"""
Created on Jan 13, 2017

@author: andrew
"""
import itertools
import logging

from cogs5e.models.errors import NoActiveBrew
from cogs5e.models.homebrew import Tome
from cogs5e.models.homebrew.bestiary import Bestiary
from cogsmisc.stats import Stats
from utils.functions import search_and_select
from . import compendium

HOMEBREW_EMOJI = "<:homebrew:434140566834511872>"
HOMEBREW_ICON = "https://avrae.io/assets/img/homebrew.png"

log = logging.getLogger(__name__)


# ---- helper ----
def get_homebrew_formatted_name(named):
    if named.source == 'homebrew':
        return f"{named.name} ({HOMEBREW_EMOJI})"
    return named.name


# ----- Monster stuff
async def select_monster_full(ctx, name, cutoff=5, return_key=False, pm=False, message=None, list_filter=None,
                              return_metadata=False, extra_choices=None, selectkey=None):
    """
    Gets a Monster from the compendium and active bestiary/ies.
    """
    try:
        bestiary = await Bestiary.from_ctx(ctx)
        await bestiary.load_monsters(ctx)
        custom_monsters = bestiary.monsters
        bestiary_id = bestiary.id
    except NoActiveBrew:
        custom_monsters = []
        bestiary_id = None
    choices = list(itertools.chain(compendium.monster_mash, custom_monsters))
    if ctx.guild:
        async for servbestiary in Bestiary.server_bestiaries(ctx):
            if servbestiary.id == bestiary_id:
                continue
            await servbestiary.load_monsters(ctx)
            choices.extend(servbestiary.monsters)

    await Stats.increase_stat(ctx, "monsters_looked_up_life")

    # #881
    if extra_choices:
        choices.extend(extra_choices)
    if selectkey is None:
        selectkey = get_homebrew_formatted_name

    return await search_and_select(ctx, choices, name, lambda e: e.name, cutoff, return_key, pm, message, list_filter,
                                   selectkey=selectkey, return_metadata=return_metadata)


# ---- SPELL STUFF ----
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


async def get_spell_choices(ctx):
    try:
        tome = await Tome.from_ctx(ctx)
        custom_spells = tome.spells
        tome_id = tome.id
    except NoActiveBrew:
        custom_spells = []
        tome_id = None
    choices = list(itertools.chain(compendium.spells, custom_spells))
    if ctx.guild:
        async for servtome in Tome.server_active(ctx):
            if servtome.id != tome_id:
                choices.extend(servtome.spells)
    return choices
