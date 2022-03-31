import base64
import itertools
import os
import time
import uuid

import disnake.ui

from utils import constants
from utils.functions import smart_trim
from ._types import _CombatantGroupT, _CombatantT
from .types import CombatantType


def create_combatant_id():
    """Creates a unique string ID for each combatant."""
    return str(uuid.uuid4())


def create_effect_id():
    """Creates a unique string ID for each effect."""
    return str(uuid.uuid4())


def create_button_interaction_id():
    """Creates a unique string ID for each button interaction in an effect."""
    # there's a 1/2**72 chance of collision but that's ok
    # if 2 button interaction ids ever collide I will personally fly to whoever had the collision and give them a cookie
    # - z, march 30 2022
    return base64.b64encode(os.urandom(9)).decode()


def create_nlp_record_session_id():
    """
    Creates a unique string ID for a NLP recording session. This is comprised of (timestamp)-(uuid) to allow for easy
    sorting by combat start time while ensuring good partitioning in S3.
    """
    return f"{int(time.time())}-{uuid.uuid4()}"


async def nlp_feature_flag_enabled(bot):
    return await bot.ldclient.variation(
        "cog.initiative.upenn_nlp.enabled",
        # since NLP recording is keyed on the server ID, we just use a throwaway key
        {"key": "anonymous", "anonymous": True},
        default=False,
    )


def can_see_combatant_details(author, combatant, combat) -> bool:
    """Returns whether the given author is allowed to see the given combatant's details (e.g. with ``private``)."""
    if combatant.is_private:
        return author.id == combatant.controller_id or author.id == combat.dm_id
    return True


def combatant_interaction_components(combatant: _CombatantT | _CombatantGroupT) -> list[disnake.ui.Button]:
    """Given a combatant, returns a list of components with up to 25 valid interactions for that combatant."""
    if combatant is None:
        return []

    if combatant.type == CombatantType.GROUP:
        buttons = []
        for c in combatant.get_combatants():
            buttons.extend(_combatant_interaction_components_single(c, label_prefix=f"{c.name}: "))
    else:
        buttons = _combatant_interaction_components_single(combatant)

    if len(buttons) > 25:
        buttons = buttons[:25]
    return buttons


def _combatant_interaction_components_single(combatant: _CombatantT, label_prefix=None):
    from .effects.interaction import ButtonInteraction

    buttons = []
    for effect in combatant.get_effects():
        for interaction in effect.interactions:
            if not isinstance(interaction, ButtonInteraction):
                continue

            if label_prefix is not None:
                label = smart_trim(label_prefix + interaction.label, max_len=80, dots="...")
            else:
                label = smart_trim(interaction.label, max_len=80, dots="...")

            interaction_button = disnake.ui.Button(
                label=label,
                style=interaction.style,
                custom_id=f"{constants.B_INIT_EFFECT}{combatant.id}:{effect.id}:{interaction.id}",
            )
            buttons.append(interaction_button)
    return buttons
