import base64
import enum
import os
import time
import uuid
from typing import TYPE_CHECKING, Union

import disnake.ui

from utils import constants
from utils.functions import smart_trim
from .types import CombatantType

import ldclient

if TYPE_CHECKING:
    from utils.context import AvraeContext
    from . import Combatant, CombatantGroup, Combat


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
        ldclient.Context.create("anonymous"),
        default=False,
    )


def can_see_combatant_details(author, combatant, combat) -> bool:
    """Returns whether the given author is allowed to see the given combatant's details (e.g. with ``private``)."""
    if combatant.is_private:
        return author.id == combatant.controller_id or author.id == combat.dm_id
    return True


# ==== interactions ====
class InteractionMessageType(enum.Enum):
    """Used to determine what kind of message a ButtonInteraction is attached to, to help with editing it later."""

    TURN_MESSAGE = "t"
    STATUS_INDIVIDUAL = "i"
    STATUS_GROUP = "g"


def combatant_interaction_components(
    combatant: Union["Combatant", "CombatantGroup"], message_type: InteractionMessageType, promote_to_group=False
) -> list[disnake.ui.Button]:
    """
    Given a combatant, returns a list of components with up to 25 valid interactions for that combatant.

    If the given combatant is in a group and *promote_to_group* is True, returns the components for that combatant's
    group instead.
    """
    if combatant is None:
        return []

    if combatant.type == CombatantType.GROUP:
        buttons = []
        for c in combatant.get_combatants():
            buttons.extend(_combatant_interaction_components_single(c, message_type, label_prefix=f"{c.name}: "))
    elif promote_to_group and (group := combatant.get_group()) is not None:
        return combatant_interaction_components(group, message_type)
    else:
        buttons = _combatant_interaction_components_single(combatant, message_type)

    if len(buttons) > 25:
        buttons = buttons[:25]
    return buttons


def _combatant_interaction_components_single(
    combatant: "Combatant", message_type: InteractionMessageType, label_prefix=None
):
    buttons = []
    for effect in combatant.get_effects():
        for interaction in effect.buttons:
            if label_prefix is not None:
                label = smart_trim(label_prefix + interaction.label, max_len=80, dots="...")
            else:
                label = smart_trim(interaction.label, max_len=80, dots="...")

            interaction_button = disnake.ui.Button(
                label=label,
                style=interaction.style,
                custom_id=f"{constants.B_INIT_EFFECT}{combatant.id}:{effect.id}:{interaction.id}:{message_type.value}",
            )
            buttons.append(interaction_button)
    return buttons


# ==== stringification ===
_status_kwarg_strategies = [
    dict(),
    dict(description=False),
    dict(description=False, parenthetical=False),
    dict(description=False, parenthetical=False, notes=False),
    dict(description=False, parenthetical=False, notes=False, resistances=False),
    dict(description=False, parenthetical=False, notes=False, resistances=False, duration=False, concentration=False),
]


def get_combatant_status_content(
    combatant: Union["Combatant", "CombatantGroup"],
    author: disnake.User,
    show_hidden_attrs: bool = False,
    max_len=2000,
    promote_to_group=False,
) -> str:
    """Given a combatant, return a Markdown-formatted string to display their current status."""
    if promote_to_group and (group := combatant.get_group()) is not None:
        return get_combatant_status_content(group, author, show_hidden_attrs, max_len)

    for strategy in _status_kwarg_strategies:
        result = _get_combatant_status_inner(combatant, author, show_hidden_attrs, **strategy)
        if len(result) <= max_len:
            break
    else:
        return "Unable to create a status message!"
    return result


def _get_combatant_status_inner(
    combatant: Union["Combatant", "CombatantGroup"], author: disnake.User, show_hidden_attrs: bool = False, **kwargs
):
    """Inner helper to constrain the length of the combatant status; kwargs passed to Combatant.get_status()"""
    if not combatant.type == CombatantType.GROUP:
        private = show_hidden_attrs and can_see_combatant_details(author, combatant, combatant.combat)
        status = combatant.get_status(private=private, **kwargs)
        if private and combatant.type == CombatantType.MONSTER:
            status = f"{status}\n* This creature is a {combatant.monster_name}."
    else:
        combat = combatant.combat
        status = "\n".join([
            co.get_status(private=show_hidden_attrs and can_see_combatant_details(author, co, combat), **kwargs)
            for co in combatant.get_combatants()
        ])
    return f"```md\n{status}\n```"


_turn_str_kwarg_strategies = [
    *_status_kwarg_strategies,
    dict(status=False),
]


def get_turn_str_content(combat: "Combat", max_len=2000, combatant: "Combatant" = None, promote_to_group=False) -> str:
    """
    Returns a string for the start-of-turn message for the current combat, ensuring that the total length of the string
    is less than *max_len*.

    If *combatant* is passed, returns the turn str for that combatant, otherwise, returns the turn str for the current
    turn. If the given combatant is in a group and *promote_to_group* is True, returns the turn str for that
    combatant's group instead.
    """
    if promote_to_group and combatant is not None and (group := combatant.get_group()) is not None:
        return get_turn_str_content(combat, max_len, group)

    for strategy in _turn_str_kwarg_strategies:
        if combatant is None:
            result = combat.get_turn_str(**strategy)
        else:
            result = combat.get_turn_str_for(combatant, **strategy)
        if len(result) <= max_len:
            break
    else:
        return "Unable to create a start-of-turn message!"
    return result


async def send_turn_message(ctx: "AvraeContext", combat: "Combat", before: list[str] = None, after: list[str] = None):
    """
    Send the message labelling the current turn of combat to the contextual channel, optionally with some additional
    messages to display to the user *before*/*after* the main combatant string.

    If there is no active combatant, sends the combat summary instead.
    """
    before_str = after_str = ""
    if before:
        before_str = "\n".join(before) + "\n"
    if after:
        after_str = "\n" + "\n".join(after)

    allowed_mentions = None
    components = None
    if combat.current_combatant is not None:
        content = get_turn_str_content(combat, max_len=2000 - (len(before_str) + len(after_str)))
        allowed_mentions = combat.get_turn_str_mentions()
        components = combatant_interaction_components(combat.current_combatant, InteractionMessageType.TURN_MESSAGE)
    else:
        content = combat.get_summary()

    result = before_str + content + after_str

    return await ctx.send(result, allowed_mentions=allowed_mentions, components=components)
